"""Independent source review and pure mock cleanup checks; no game or socket."""
import ast
import json
from pathlib import Path
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import check_memory_budget
from bridge.tag_command_backend import read, digest, require
from tools import eu4_runtime_observer_r3 as entry

OUT = ROOT / "work/reports/runtime-observer-r3-review-20261015-r1"
MANIFEST_SHA = "09bf1846bbb5b9e2ad82e730cbfbef4a272ef38dee891887928d8c8367b2b6e7"


def pin(path):
    raw = read(path, 16 * 1024 * 1024)
    return dict(bytes=len(raw), sha256=digest(raw))


def mocked_main_case(failure, *, print_failure=False):
    server = Mock()
    server.server_port = 8775
    if not print_failure:
        server.serve_forever.side_effect = failure
    observed_exception = None
    result = None
    argv = ["entry", "serve", "--pid", "1", "--creation", "readonly-mock"]
    with patch.object(sys, "argv", argv), patch.object(entry, "runtime_source_pins", return_value={}), \
        patch("bridge.war_state_service.WarStateObserver", return_value=Mock()), \
        patch("bridge.relation_state_service.RelationStateObserver", return_value=Mock()), \
        patch("bridge.relation_state_service.RuntimeCapture", side_effect=AssertionError("process forbidden")), \
        patch.object(entry, "compose_server", return_value=server), \
        patch("builtins.print", side_effect=failure if print_failure else None):
        try:
            result = entry.main()
        except (OSError, RuntimeError) as exc:
            observed_exception = type(exc).__name__
    return dict(return_value=result, exception_type=observed_exception,
        startup_print_failed=print_failure, serve_called=server.serve_forever.call_count,
        server_close_called=server.server_close.call_count,
        real_socket_created=False, process_opened=False)


def main():
    require(pin(entry.MANIFEST)["sha256"] == MANIFEST_SHA, "Frozen R3 manifest changed")
    with patch("bridge.relation_state_service.RuntimeCapture", side_effect=AssertionError("process forbidden")):
        source_pins = entry.runtime_source_pins()
        sessionless = entry.catalog(effects_enabled=False)
        configured = entry.catalog(effects_enabled=True)
    require(len(source_pins) == 94, "R3 source graph size differs")
    require(sessionless["profiles"] == [] and sessionless["current_state_is_request_completion"] is False,
        "Sessionless catalog overstates request effects")
    require(len(configured["profiles"]) == 15 and configured["all120_effect_profiles_complete"] is False,
        "Configured catalog scope differs")
    require(len(sessionless["current_indexed_relations"]["actions"]) == 3, "Relation catalog scope differs")
    tree = ast.parse(read(ROOT / "tools/eu4_runtime_observer_r3.py", 65536).decode("utf-8"))
    main_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    require(ast.unparse(main_fn.body[0]) == "runtime_source_pins()", "Main guard ordering differs")
    route_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CheckedRoutes")
    route_read = next(n for n in route_class.body if isinstance(n, ast.FunctionDef) and n.name == "_read")
    guard_lines = [n.lineno for n in ast.walk(route_read) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id == "runtime_source_pins"]
    delegate_line = next(n.lineno for n in ast.walk(route_read) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Call) and isinstance(n.func.func, ast.Name) and n.func.func.id == "getattr")
    require(len(guard_lines) == 2 and min(guard_lines) < delegate_line < max(guard_lines),
        "Delegated read guard ordering differs")
    test_tree = ast.parse(read(ROOT / "bridge/tests/test_runtime_observer_r3.py", 65536).decode("utf-8"))
    test_names = [n.name for n in ast.walk(test_tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    require(len(test_names) == 13, "Retained test count differs")
    mock_cases = dict(startup_broken_pipe=mocked_main_case(BrokenPipeError("mock closed stdout"), print_failure=True),
        serve_runtime_error=mocked_main_case(RuntimeError("mock serve error")),
        serve_keyboard_interrupt=mocked_main_case(KeyboardInterrupt()), normal_serve_return=mocked_main_case(None))
    require(mock_cases["startup_broken_pipe"]["server_close_called"] == 0
        and mock_cases["startup_broken_pipe"]["serve_called"] == 0,
        "Selected frozen cleanup gap no longer reproduces")
    require(all(mock_cases[k]["server_close_called"] == 1 for k in
        ("serve_runtime_error", "serve_keyboard_interrupt", "normal_serve_return")), "Existing serve cleanup differs")
    fake_base = Mock()
    with patch("bridge.war_state_service.make_war_server", return_value=fake_base), \
        patch("bridge.relation_state_service.make_relation_server", side_effect=ValueError("mock decoration failure")):
        try:
            entry.compose_server(Mock(), Mock(), port=0, token="mock-only-token-1234")
        except ValueError:
            pass
        else:
            raise AssertionError("Decoration failure did not propagate")
    require(fake_base.server_close.call_count == 1, "Composition failure does not close base")
    mock_cases["relation_decoration_failure"] = dict(server_close_called=1, exception_type="ValueError",
        real_socket_created=False, process_opened=False)
    for path in (Path(__file__),):
        source_pins[path.relative_to(ROOT).as_posix()] = pin(path)
    result = dict(schema="EU4-RUNTIME-OBSERVER-R3-INDEPENDENT-SOURCE-REVIEW/1",
        review_status="passed_with_low_impact_cleanup_finding", frozen_R3_manifest_sha256=MANIFEST_SHA,
        source_pins=source_pins, checked_source_pin_count=len(source_pins),
        prior_frozen_dependencies_verified=True, main_first_operation="runtime_source_pins()",
        delegated_reads_guarded_before_and_after=True,
        routing=dict(effects="Original request-ID observer; configured session only",
            relations="Current typed-index pair state; three supported actions", wars="Current opponent membership only",
            sessionless_effect_profiles=[], current_state_is_request_completion=False,
            configured_request_effect_profile_count=15, all120_complete=False,
            authentication="Frozen R1 loopback Host/Origin/Bearer checks inherited",
            mutation_routes="Frozen R1 POST/PUT/PATCH/DELETE refusal inherited; no publisher route",
            read_errors_409_422="Outer status unknown, retry false, native_calls0 and requests_published0"),
        pure_mock_cleanup_cases=mock_cases,
        findings=[dict(id="R3-CLEANUP-STARTUP-PRINT", priority="P3",
            file="tools/eu4_runtime_observer_r3.py", line=152,
            issue="Listener is already constructed when startup print executes outside the close finally block.",
            reproduction="Pure mock main: startup print raises BrokenPipeError; serve_forever0, server_close0.",
            impact="A caller retaining the Python process after main raises does not get function-level listener cleanup. A normal CLI process exit lets the OS reclaim the socket.",
            current_success_paths="Normal return, KeyboardInterrupt and serve RuntimeError each close exactly once; decorator failure also closes the base.",
            proposed_narrow_followup="Place startup announcement and serve_forever inside one try/finally in a new entry version; keep frozen R3 unchanged.")],
        tests=dict(retained_R3_test_methods=13, old_tests_rerun=False,
            parent_reported_prior_suite="13 passed in0.633s; not independently rerun here",
            review_new_checks="Five pure mock main/composition lifecycle cases; no live socket or game",
            scope_limit="Normal setUp/tearDown cleanup is visible in the retained loopback tests; setup failure cleanup is not covered by those13 methods."),
        real_HTTP_verification_audited=False, actual_game_accessed=False, real_socket_created=False,
        native_calls=0, requests_published=0, memory_written=False, frozen_files_modified=False,
        resources=dict(peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024))
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent-source-review.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    markdown = OUT / "independent-source-review.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# R3 independent source review\n\n"
            "Source graph94 pins passed. Main guards before forwarding; each HTTP read delegate guards before/after. Frozen R1 authentication and write refusal are inherited. Relations, wars and request effects retain separate meanings; sessionless catalog has no request effects, and current_state_is_request_completion remains false. Configured catalog lists15 request profiles, not120 complete. No publisher path was found.\n\n"
            "P3 cleanup: tools/eu4_runtime_observer_r3.py:152 announces the listener before the try/finally. A pure mock BrokenPipeError at print leaves server_close uncalled; serve is never entered. This is a function-level cleanup gap if the Python process stays alive. CLI exit can reclaim the socket through the OS and is not evidence that finally ran.\n\n"
            "Normal serve return, KeyboardInterrupt, serve RuntimeError and relation-decoration failure each close once in pure mocks. Keep frozen R3 unchanged; a new wrapper can include startup print in its close finally scope. The13 earlier tests were source-reviewed, not rerun. No real socket, game process, request or native operation was used by this review. Actual new R3 HTTP evidence remains for a separate file audit.\n")
    print(json.dumps(dict(review=pin(output), markdown=pin(markdown), source_pins=len(source_pins),
        pure_mock_cases=len(mock_cases), real_socket_created=False, game_process_accessed=False)))


if __name__ == "__main__":
    main()
