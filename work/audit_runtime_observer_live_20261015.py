"""Independent source/retained-HTTP audit; no process, HTTP or test execution."""
import ast
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.eu4_runtime_observer_r2 import runtime_source_pins
from bridge.war_state_service import source_pins, compact_capture
from bridge.diplomacy_effect_observer import full_handle
from bridge.tag_command_backend import read, digest, require, validate_identity

DIRECTORY = ROOT/"work/reports/runtime-observer-20261015-r1"
HTTP_REPORT = DIRECTORY/"live-http-verification.json"
HTTP_SHA = "3a309cf429e5face9bb58b313eca7bc02eb2e6b3a0c55e8d21a812c4ce669dbf"
RUNTIME_SHA = "5fc4ce72fe0fabd23d4a62fc3359594faa4f7962935d27b1cb89844fee85a03d"
OLD_HOST_SHA = "a7eb83536a173da571b15fd2ba33112856d08f06c5065cdb8f8cc7bd265fe1cb"
OLD_FILES = {
    "bridge/war_state_service.py": {"bytes": 11783, "sha256": "37146b8aed9902ed14ff7e83feb8a42338fef9b378b91402b0b68758b4f04a29"},
    "tools/observe_war_runtime.py": {"bytes": 3275, "sha256": "946728d30e02d99ea16017aa2ae6270822c810f13c008357fd99b127d20d5768"},
    "tools/eu4_runtime_observer.py": {"bytes": 3794, "sha256": "a28a65895a9a563f4d8fe22776bac2d8a06f025ffb1d66044ca5ef4bc94a47ed"},
    "bridge/tests/test_war_state_service.py": {"bytes": 7745, "sha256": "0e7e099c2265e9f0dad0676493d5478b1b55818e8447f988fc22177a2ba095c5"}}


def pinned(path, maximum=4*1024*1024):
    raw = read(path, maximum)
    return raw, {"bytes": len(raw), "sha256": digest(raw)}


def handle_row(row):
    slot, tag = full_handle(int(row["handle"], 16), 1380, tag=row["tag"])
    require(row["slot"] == slot and row["tag"] == tag, "Complete country handle/slot differs")
    address = int(row["address"], 16)
    require(0x10000 <= address and address+0x28 <= 2**47 and address % 8 == 0, "Country address invalid")
    return slot


def audit_graph(p, actor_tag, target_tag, expected_state):
    require(p["schema"] == "EU4-WAR-PAIR-GRAPH/2" and p["pair_state"] == expected_state,
        "Projection schema/current state differs")
    require(p["actor"]["tag"] == actor_tag and p["target"]["tag"] == target_tag, "Selected pair differs")
    actor, target = p["actor"], p["target"]
    handle_row(actor); handle_row(target)
    r = p["roots"]
    require(r["count"] == r["capacity"] == 1380 and r["manual_pause"] == 1
        and r["reset"] == r["load_source"] == r["recalculating"] == r["ironman"] == 0,
        "Root/pause/load guards differ")
    require(r["date"] == 56461512, "Checkpoint date differs")
    require(p["complete_current_global_scan"] is True and p["global_war_count"] == len(p["wars"]) == 4
        and 4 <= p["global_war_capacity"] <= 512, "Complete global war extent differs")
    require(p["physical_pair_indexes"] == len(p["relation_indexes"]) == 2, "Index alias count differs")
    require(all(p[k] is False for k in ("historical_war_pointer_input_supported", "war_retired_proven",
        "peace_terms_verified", "peace_completion_verified", "request_causality_verified", "queue_removal_is_completion")),
        "Current membership improperly claims completion/lifetime")
    wars, opposing = {}, []
    for w in p["wars"]:
        address = int(w["current_war_address"], 16)
        require(w["current_war_address"] not in wars and address % 8 == 0
            and 0x10000 <= address and address+0x218 <= 2**47, "Global war address invalid/duplicate")
        require(w["vtable_rva"] == "0x1d1f768" and w["marker"] == 357
            and 0 < w["started_raw_date"] <= r["date"], "Typed war/date differs")
        require(w["outcome_is_retirement"] is False and w["goal_definition_layout_validated"] is False,
            "Outcome/goal evidence overclaimed")
        sides = []
        for side, vector_name in (("attackers", "attacker_vector"), ("defenders", "defender_vector")):
            values = w[side]
            slots = {handle_row(x) for x in values}
            require(0 < len(slots) == len(values) <= 64, "War side member extent/uniqueness differs")
            begin, end, cap = [int(x, 16) for x in w[vector_name]]
            require(0x10000 <= begin < end <= cap <= 2**47 and begin % 8 == end % 8 == cap % 8 == 0
                and end-begin == len(values)*8 and (cap-begin)//8 <= 64, "War side vector shape differs")
            sides.append({x["handle"]: x["slot"] for x in values})
        a, b = sides
        require(not (set(a.values()) & set(b.values())) and w["primary_attacker_handle"] in a
            and w["primary_defender_handle"] in b, "War leader/side identities differ")
        ah, th = actor["handle"], target["handle"]
        is_opposing = (ah in a and th in b) or (ah in b and th in a)
        require(w["selected_pair_opponents"] is is_opposing, "War selected-pair flag differs")
        if is_opposing:
            opposing.append(w)
        wars[w["current_war_address"]] = (w, a, b)
    require(len(opposing) <= 1 and p["selected_war"] == (opposing[0] if opposing else None),
        "Selected current war differs from complete opposing sides")
    require(bool(opposing) == (expected_state == "opponents"), "Current absence/opposition inconsistent")
    selected_address = opposing[0]["current_war_address"] if opposing else None
    for ix, owner, other in zip(p["relation_indexes"], (actor, target), (target, actor)):
        owner_address = int(owner["address"], 16)
        require(ix["owner_handle"] == owner["handle"] and int(ix["root"], 16) == owner_address+0x14F8
            and int(ix["object"], 16) == owner_address+0x14F8+0x48
            and int(ix["data_field"], 16) == int(ix["country_data_alias"], 16) == owner_address+0x1548,
            "Relation-root/country war-index alias differs")
        require(ix["independent_physical_indexes"] == 1 and 0 <= ix["count"] == len(ix["entries"]) <= ix["capacity"] <= 64,
            "Signed index capacity/count differs")
        require(ix["relation_byte46_is_war_membership"] is False and ix["native_war_membership_predicate_rva"] == "0xa68a00"
            and ix["relation_byte46_mask4"] == bool(ix["relation_byte46_raw"] & 4), "Diagnostic byte/predicate boundary differs")
        entries = ix["entries"]
        require(len({x["other_slot"] for x in entries}) == len(entries), "Duplicate counterpart key")
        for entry in entries:
            require(entry["current_war_address"] in wars, "Indexed war not globally current")
            _, attackers, defenders = wars[entry["current_war_address"]]
            require((owner["handle"] in attackers and entry["other_slot"] in defenders.values())
                or (owner["handle"] in defenders and entry["other_slot"] in attackers.values()),
                "Index counterpart not an opposing side member")
        matches = [x["current_war_address"] for x in entries if x["other_slot"] == other["slot"]]
        require(matches == ([selected_address] if selected_address else [])
            and ix["target_match"] is bool(matches), "Selected bilateral index/global membership differs")
    return dict(pair_state=expected_state, actor=actor, target=target, global_wars=4,
        selected_war_address=selected_address, selected_side_counts={side: len(opposing[0][side]) if opposing else 0
            for side in ("attackers", "defenders")}, full_member_graph_consistent=True,
        bilateral_native_index_predicate_matches=True, byte46_membership_not_assumed=True)


def main():
    runtime_file = ROOT/"bridge/runtime_observer_manifest_1375.json"
    require(pinned(runtime_file)[1]["sha256"] == RUNTIME_SHA, "Fixed new runtime manifest differs")
    require(pinned(ROOT/"bridge/war_state_service_manifest_1375.json")[1]["sha256"] == OLD_HOST_SHA,
        "Frozen old host manifest changed")
    checked = runtime_source_pins()
    for name, expected in OLD_FILES.items():
        require(checked[name] == expected, "Frozen original source changed: "+name)
    entry_raw, _ = pinned(ROOT/"tools/eu4_runtime_observer_r2.py")
    entry_ast = ast.parse(entry_raw.decode("utf-8"))
    function = next(x for x in entry_ast.body if isinstance(x, ast.FunctionDef) and x.name == "main")
    first = function.body[0]
    require(isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name) and first.value.func.id == "runtime_source_pins",
        "Unified new entry no longer verifies sources before every delegate")
    require(isinstance(function.body[1], ast.ImportFrom) and function.body[1].module == "tools.eu4_runtime_observer",
        "Frozen wrapper imported before source verification")
    guard_raw, _ = pinned(ROOT/"bridge/tests/test_runtime_observer_guard.py")
    tests_ast = ast.parse(guard_raw.decode("utf-8"))
    guard_methods = [x.name for x in ast.walk(tests_ast) if isinstance(x, ast.FunctionDef) and x.name.startswith("test_")]
    require(len(guard_methods) == 6, "New regression scope differs")
    http_raw, http_pin = pinned(HTTP_REPORT)
    require(http_pin["sha256"] == HTTP_SHA, "Fixed real HTTP receipt differs")
    d = json.loads(http_raw)
    require(d["schema"] == "EU4-RUNTIME-OBSERVER-LIVE-HTTP/1"
        and (d["pid"], d["creation"]) == (80340, "01dd5c075fcf8c26"), "HTTP source target/schema differs")
    host_pins = source_pins()
    require(d["source_pins"] == host_pins, "Retained HTTP host source pins differ")
    inputs = dict(checked)
    inputs[HTTP_REPORT.relative_to(ROOT).as_posix()] = http_pin
    producer_path = ROOT/d["producer"]["path"]
    producer_raw, producer_pin = pinned(producer_path)
    require(producer_pin == {k: d["producer"][k] for k in ("bytes", "sha256")}, "HTTP producer differs")
    inputs[producer_path.relative_to(ROOT).as_posix()] = producer_pin
    producer_ast = ast.parse(producer_raw.decode("utf-8"))
    attribute_calls = {x.func.attr for x in ast.walk(producer_ast) if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)}
    require(not {"publish", "load", "WriteProcessMemory", "CreateRemoteThread", "install"} & attribute_calls,
        "HTTP verification producer unexpectedly invokes a game operation")
    require({"shutdown", "server_close", "join"} <= attribute_calls, "Producer closure calls absent")
    expected = [("GET", "/observer/v1/capabilities", True, 200),
        ("GET", "/observer/v1/wars/ENG/AMG", True, 200),
        ("GET", "/observer/v1/wars/FRA/ENG", True, 200),
        ("GET", "/observer/v1/wars/ENG/AMG", False, 403),
        ("POST", "/observer/v1/wars/ENG/AMG", True, 405),
        ("GET", "/observer/v1/effects/not-configured", True, 404)]
    require(len(d["cases"]) == len(expected), "HTTP case count differs")
    require([(x["method"], x["path"], x["authorized"], x["http_status"]) for x in d["cases"]] == expected,
        "Retained HTTP route/status cases differ")
    capabilities = d["cases"][0]["response"]
    require(capabilities["profiles"] == [] and capabilities["all120_effect_profiles_complete"] is False
        and capabilities["war_state"]["current_pair_state"] is True
        and capabilities["war_state"]["requires_injected_DLL"] is False
        and capabilities["war_state"]["peace_API_completion_verified"] is False
        and capabilities["war_state"]["source_manifest_sha256"] == OLD_HOST_SHA,
        "Sessionless capabilities overclaim effects")
    results, capture_roots, session = [], [], None
    for case, actor, target, expected_state in ((d["cases"][1], "ENG", "AMG", "opponents"),
            (d["cases"][2], "FRA", "ENG", "not_currently_opponents")):
        response = case["response"]
        record = response["record"]
        path = Path(record["path"])
        require(path.parent.resolve() == (DIRECTORY/"captures").resolve(), "Capture journal path escapes intended directory")
        raw, capture_pin = pinned(path)
        require(capture_pin == {k: record[k] for k in ("bytes", "sha256")}, "Capture journal identity differs")
        inputs[path.relative_to(ROOT).as_posix()] = capture_pin
        c = json.loads(raw)
        identity = validate_identity(c["identity"])
        require((identity["pid"], identity["creation"]) == (80340, "01dd5c075fcf8c26"), "Capture target differs")
        require(session is None or identity == session, "HTTP observer nonce/session changed between cases")
        session = identity
        require(c["source_pins"] == host_pins and c["status"] == "observed" and c["two_pass_equal"] is True
            and c["passes"][0] == c["passes"][1] == c["projection"], "Complete two-pass capture/source differs")
        require(compact_capture(c, record) == response, "HTTP response not exact frozen compact projection of journal")
        require(c["process_identity_authenticated_by_host"] is True
            and c["process_identity_authenticated_by_this_module"] is False
            and c["native_session_installed"] is False, "Host/decoder identity scope differs")
        require(all(c[k] is False for k in ("memory_written", "automatic_command_retry", "atomic_main_thread_snapshot",
            "world_epoch_proven", "world_lifetime_lease_proven", "runtime_effect_verified")), "Capture scope overclaimed")
        require(all(type(c[k]) is int and c[k] == 0 for k in ("native_calls", "requests_published", "saves_written", "reloads")),
            "Capture has non-read-only effects")
        budget = c["total_rpm_budget"]
        require(0 < budget["calls"] <= 4096 and 0 < budget["bytes"] <= 512*1024
            and 0 < budget["largest_read"] <= 65536
            and 0 <= c["rpm_budget_used"]["calls"] <= budget["calls"]
            and 0 <= c["rpm_budget_used"]["bytes"] <= budget["bytes"], "Shared memory budget differs")
        checked_graph = audit_graph(c["projection"], actor, target, expected_state)
        capture_roots.append(c["projection"]["roots"])
        results.append(checked_graph | dict(record=record, outer_rpm_budget=budget,
            duration_ms=c["duration_ms"], response_exact_compact_recomputed=True, complete_passes_equal=True,
            native_effect_completion_verified=False))
    require(capture_roots[0] == capture_roots[1], "Checkpoint roots/date changed between HTTP observations")
    require(d["listener_closed"] is True and d["server_thread_joined"] is True, "Producer did not record listener closure")
    require(d["memory_written"] is False and d["active_knowledge_effect_tested"] is False
        and d["new_war_peace_API_effect_tested"] is False
        and all(type(d[k]) is int and d[k] == 0 for k in ("native_calls", "requests_published", "saves_written", "reloads")),
        "Live receipt effects scope differs")
    inputs[Path(__file__).relative_to(ROOT).as_posix()] = pinned(Path(__file__))[1]
    result = dict(schema="EU4-RUNTIME-OBSERVER-INDEPENDENT-FILE-AUDIT/1", status="passed",
        source_pins=inputs, checked_unique_inputs=len(inputs),
        entry_fix=dict(previous_finding="P2 specialist forward bypasses wrapper source pins",
            status="fixed_in_new_r2_entry", first_main_operation="runtime_source_pins()",
            new_manifest_sha256=RUNTIME_SHA, old_manifest_sha256=OLD_HOST_SHA,
            original_files_unchanged=OLD_FILES, regression_test_methods=guard_methods,
            root_reported_regression_tests_passed=6, audit_tests_rerun=False),
        real_HTTP=dict(input_report_sha256=HTTP_SHA, cases=[dict(method=x[0], path=x[1], authorized=x[2], status=x[3]) for x in expected],
            sessionless_capabilities_truthful=True, exact_compact_responses_recomputed=2,
            captures=results, listener_closure_report_and_source_consistent=True,
            actual_listener_probe_by_auditor=False, source_host_manifest_sha256=OLD_HOST_SHA),
        findings=[], current_membership_cases_verified=2, new_API_effects_verified=0,
        institute_adoption_completed_verified=False, native_session_installed=False,
        peace_terms_verified=False, peace_completion_verified=False, war_retirement_verified=False,
        exact_external_request_causality_verified=False, saved_state_verified=False, cold_reload_verified=False,
        audit_game_process_accessed=False, audit_HTTP_requests_sent=0, audit_native_calls=0,
        audit_memory_written=False, audit_requests_published=0, automatic_command_retry=False,
        limitations=["Live HTTP receipt covers the unchanged old war host service, not an actual run of the new R2 CLI entry.",
            "Original wrapper is preserved with its historical bypass; use the new checked R2 entry.",
            "Complete decoded graphs were independently checked; no complete raw RPM transcript permits raw decoder replay.",
            "Listener closure and no-store/HTTP transport checks are retained producer evidence, not a new socket probe.",
            "Current opponents/absence are not declaration/peace API completion, object retirement, exact request causality or saved persistence.",
            "Capture durations847.451/837.940ms include host work; they do not satisfy a100ms sampling bound."])
    output = DIRECTORY/"independent-file-audit.json"
    raw = (json.dumps(result, ensure_ascii=True, indent=2)+"\n").encode("ascii")
    with output.open("xb") as stream:
        stream.write(raw)
    markdown = DIRECTORY/"independent-file-audit.md"
    text = ("# Independent runtime observer file audit\n\n"
        "P2 is fixed in the new checked R2 entry: source verification is the first main operation, before import/forwarding. The old a7eb manifest and all four original source files match their earlier pins. Six regression methods cover refused forwarding and argument retention; tests were not rerun by this audit.\n\n"
        "The retained live HTTP report has six consistent cases: sessionless capabilities with no effect profiles; ENG→AMG opponents200; FRA→ENG current absence200; unauthenticated403; POST405; unconfigured effects404. Both complete journal hashes match and both responses exactly match a fresh pure compact projection. The four-war full side graph and bilateral indexes agree; two complete passes match for each case.\n\n"
        f"{len(inputs)} unique fixed input/source pins passed. Positive sample:1827 reads/92113B,847.451ms; negative sample:1823 reads/90257B,837.940ms. Both stay within4096 reads/512KiB. Source-authenticated producer records listener closed and thread joined; the auditor opened no socket or process.\n\n"
        "These are current-state observations, not new war/peace API effects, peace terms, retirement or saved/cold-reload proof. The HTTP acceptance used the unchanged old service; the new R2 CLI fix was reviewed from files, not misreported as real HTTP execution. No frozen file was changed.\n")
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print(json.dumps({"path": str(output), "bytes": len(raw), "sha256": digest(raw),
        "markdown": {"path": str(markdown), **pinned(markdown)[1]}, "fixed_inputs": len(inputs),
        "findings": 0, "game_process_accessed": False, "HTTP_requests_sent": 0}))


if __name__ == "__main__":
    main()
