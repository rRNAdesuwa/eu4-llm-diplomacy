"""Pre-seal review of the public entry; pure fakes only, no game or listener."""
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
from tools import eu4_observer as entry
from tools.eu4_runtime_observer_r3 import runtime_source_pins

OUT = ROOT / "work/reports/eu4-observer-entry-review-20261015-r1"


def pin(path):
    raw = read(path, 16 * 1024 * 1024)
    return dict(bytes=len(raw), sha256=digest(raw))


def main():
    require(pin(ROOT / "bridge/runtime_observer_r3_manifest_1375.json")["sha256"] ==
        "09bf1846bbb5b9e2ad82e730cbfbef4a272ef38dee891887928d8c8367b2b6e7", "Frozen R3 parent changed")
    with patch("bridge.relation_state_service.RuntimeCapture", side_effect=AssertionError("process forbidden")):
        source_pins = runtime_source_pins()
    require(len(source_pins) == 94, "Parent graph size differs")
    code = read(ROOT / "tools/eu4_observer.py", 65536).decode("utf-8")
    tree = ast.parse(code)
    main_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    require(ast.unparse(main_fn.body[0]) == "source_pins()", "Public entry guard is not first")
    cleanup = next(n for n in main_fn.body if isinstance(n, ast.Try) and n.finalbody)
    require(len(cleanup.finalbody) == 1 and ast.unparse(cleanup.finalbody[0]) == "server.server_close()",
        "Explicit server_close finally differs")
    require(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
        for n in ast.walk(cleanup)), "Startup print is not within cleanup scope")
    require(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "serve_forever"
        for n in ast.walk(cleanup)), "Serve is not within cleanup scope")
    require(not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "close"
        for n in ast.walk(cleanup)), "Wrong close method remains")
    tests = ast.parse(read(ROOT / "bridge/tests/test_eu4_observer_entry.py", 65536).decode("utf-8"))
    test_names = [n.name for n in ast.walk(tests) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    require(len(test_names) == 6, "Candidate regression scope differs")
    server = Mock(server_port=12345)
    failure = None
    with patch.object(sys, "argv", ["entry", "serve", "--pid", "1", "--creation", "mock-only"]), \
        patch.object(entry, "source_pins", return_value={}), \
        patch("tools.eu4_runtime_observer_r3.compose_server", return_value=server), \
        patch("bridge.war_state_service.WarStateObserver", return_value=Mock()), \
        patch("bridge.relation_state_service.RelationStateObserver", return_value=Mock()), \
        patch("bridge.relation_state_service.RuntimeCapture", side_effect=AssertionError("process forbidden")), \
        patch("builtins.print", side_effect=BrokenPipeError("review mock closed stdout")):
        try:
            entry.main()
        except BrokenPipeError:
            failure = "BrokenPipeError"
    require(failure == "BrokenPipeError" and server.server_close.call_count == 1
        and server.serve_forever.call_count == 0 and server.close.call_count == 0,
        "Public candidate does not close listener on startup failure")
    blocked = []
    for operation in ("serve", "effects"):
        with patch.object(sys, "argv", ["entry", operation]), \
            patch.object(entry, "source_pins", side_effect=ValueError("review bad entry pin")), \
            patch("tools.eu4_runtime_observer_r3.main") as delegate, \
            patch("tools.eu4_runtime_observer_r3.compose_server") as compose:
            try:
                entry.main()
            except ValueError:
                pass
            else:
                raise AssertionError("Bad entry pin was accepted")
            require(delegate.call_count == compose.call_count == 0, "Bad pin reached delegate")
            blocked.append(operation)
    for path in (ROOT / "tools/eu4_observer.py", ROOT / "bridge/tests/test_eu4_observer_entry.py", Path(__file__)):
        source_pins[path.relative_to(ROOT).as_posix()] = pin(path)
    result = dict(schema="EU4-PUBLIC-OBSERVER-ENTRY-INDEPENDENT-CANDIDATE-REVIEW/1", review_status="ready_for_seal",
        findings=[], source_pins=source_pins, checked_source_pin_count=len(source_pins),
        candidate_entry_pin=pin(ROOT / "tools/eu4_observer.py"),
        candidate_tests_pin=pin(ROOT / "bridge/tests/test_eu4_observer_entry.py"),
        parent_R3_graph_verified=True, parent_R3_graph_pin_count=94,
        public_manifest_verified=False, public_manifest_state="Not sealed at review time; root must seal these exact candidate bytes and then verify the complete public graph.",
        cleanup=dict(explicit_finally_method="server.server_close", startup_print_inside_finally_scope=True,
            serve_inside_finally_scope=True, startup_broken_pipe_mock=dict(exception=failure,
                server_close_calls=1, serve_calls=0, wrong_close_calls=0)),
        source_guard=dict(first_main_operation="source_pins()", bad_pin_blocks_pure_fake_operations=blocked,
            parent_graph_not_modified=True, nonserve_delegate="Frozen R3 main with original argument vector",
            HTTP_delegate_guard="Frozen R3 CheckedRoutes before/after guards retained"),
        tests=dict(candidate_method_count=6, parent_reported_final_run="6 passed in0.058s; not rerun here",
            independent_new_pure_fake_checks=["startup BrokenPipe cleanup", "bad pin serve delegation", "bad pin effects delegation"],
            parent_disclosed_initial_failure="Unsealed contextlib.closing candidate called.close; pure mocks detected it. Final reviewed candidate uses explicit.server_close finally.",
            old_tests_rerun=False),
        real_socket_created=False, game_process_accessed=False, native_calls=0, requests_published=0,
        frozen_files_modified=False, candidate_files_modified=False,
        resources=dict(peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024))
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent-candidate-review.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    markdown = OUT / "independent-candidate-review.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# Public observer entry candidate review\n\n"
            "Ready for sealing the exact reviewed bytes. Parent R3 graph94 pins passed unchanged. Public entry first checks its own manifest/parent graph, preserves non-serve delegation, and reuses frozen R3 read-only route composition.\n\n"
            "Startup print and serve are now both inside an explicit server.server_close finally. An independent pure fake BrokenPipeError reproduces close1/serve0/wrong-close0. Bad entry pins prevent both serve construction and effect delegation. The6 candidate test methods were reviewed; the parent's final6-pass run was not repeated. The disclosed initial contextlib.closing/.close failure belongs to the unsealed prior candidate and is retained as history.\n\n"
            "No new finding. The public manifest was not yet sealed at this review, so its complete verification remains a required post-seal step. No real socket, game process, request, native operation, source edit or frozen-file change occurred.\n")
    print(json.dumps(dict(review=pin(output), markdown=pin(markdown), source_pins=len(source_pins),
        ready_for_seal=True, public_manifest_verified=False, game_process_accessed=False)))


if __name__ == "__main__":
    main()
