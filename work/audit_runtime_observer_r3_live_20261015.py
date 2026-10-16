"""Audit retained composed HTTP receipts and raw relation records; file only."""
import ast
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import check_memory_budget
from audit_runtime_observer_live_20261015 import audit_graph, handle_row
from tools.eu4_runtime_observer_r3 import runtime_source_pins, catalog
from bridge.relation_state_service import source_pins as relation_pins, compact_capture as relation_compact
from bridge.war_state_service import source_pins as war_pins, compact_capture as war_compact
from bridge.relation_effect_reader import PROFILES, _capture, _index, _object, evaluate_relation_effect
from bridge.tag_command_backend import read, digest, require, validate_identity

OUT = ROOT / "work/reports/runtime-observer-20261015-r3"
REPORT = OUT / "live-http-verification.json"
SHA = "ec00df0fe3b1bd455c7b68a0504bfb963e1bc7782a2a59662f90e3877e972673"


def pin(path):
    raw = read(path, 16 * 1024 * 1024)
    return dict(bytes=len(raw), sha256=digest(raw))


class RawRecordPort:
    """Read only retained JSON hex ranges, never a process."""
    def __init__(self, ranges):
        self.ranges = ranges
        self.calls = 0

    def read(self, address, size):
        require((address, size) in self.ranges, "Raw replay range is not retained")
        self.calls += 1
        return self.ranges[(address, size)]


def common_capture(capture, response, expected_graph):
    identity = validate_identity(capture["identity"])
    require((identity["pid"], identity["creation"]) == (80340, "01dd5c075fcf8c26"), "Capture process differs")
    require(capture["source_pins"] == expected_graph and capture["two_pass_equal"] is True
        and len(capture["passes"]) == 2, "Capture source/two-pass evidence differs")
    require(capture["native_session_installed"] is False
        and capture["process_identity_authenticated_by_host"] is True, "Host/nonce identity scope differs")
    require(capture["memory_written"] is False and all(type(capture[k]) is int and capture[k] == 0
        for k in ("native_calls", "requests_published", "saves_written", "reloads")), "Capture is not read-only")
    outer = capture["total_rpm_budget"]
    require(0 < outer["calls"] <= 4096 and 0 < outer["bytes"] <= 524288
        and 0 < outer["largest_read"] <= 65536, "Outer read budget differs")
    require(response["runtime_effect_verified"] is False and response["request_causality_verified"] is False
        and response["world_epoch_proven"] is False and response["automatic_command_retry"] is False,
        "Current observation was upgraded to API effect/causality")
    return identity


def main():
    require(pin(REPORT) == {"bytes": 74764, "sha256": SHA}, "Fixed R3 live report changed")
    data = json.loads(read(REPORT, 128 * 1024))
    require(data["schema"] == "EU4-RUNTIME-COMPOSED-LIVE-HTTP/3"
        and (data["pid"], data["creation"]) == (80340, "01dd5c075fcf8c26"), "HTTP report identity/schema differs")
    graphs = dict(composition=runtime_source_pins(), relations=relation_pins(), wars=war_pins())
    require(len(graphs["composition"]) == 94 and data["source_pins"] == graphs["composition"],
        "Retained composed source graph differs")
    inputs = dict(graphs["composition"])
    inputs[REPORT.relative_to(ROOT).as_posix()] = pin(REPORT)
    producer = ROOT / data["producer"]["path"]
    require(pin(producer)["sha256"] == data["producer"]["sha256"], "Live producer changed")
    inputs[producer.relative_to(ROOT).as_posix()] = pin(producer)
    producer_tree = ast.parse(read(producer, 65536).decode("utf-8"))
    calls = {n.func.attr for n in ast.walk(producer_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    require(not {"publish", "load", "install", "WriteProcessMemory", "CreateRemoteThread"} & calls,
        "Live producer gained a game operation")
    require({"shutdown", "server_close", "join", "close"} <= calls, "Producer resource closure calls absent")
    require(any(isinstance(n, ast.Try) and {"server.shutdown()", "server.server_close()", "thread.join(5)"}
        <= {ast.unparse(x) for x in n.finalbody} for n in ast.walk(producer_tree)), "Producer listener finally differs")
    expected = [("GET", "/observer/v1/capabilities", True, 200),
        ("GET", "/observer/v1/relations/offer_alliance/FRA/POR", True, 200),
        ("GET", "/observer/v1/relations/offer_alliance/POR/FRA", True, 200),
        ("GET", "/observer/v1/relations/royal_marriage/ORL/BRI", True, 200),
        ("GET", "/observer/v1/relations/guarantee/FRA/SAV", True, 200),
        ("GET", "/observer/v1/relations/guarantee/SAV/FRA", True, 200),
        ("GET", "/observer/v1/relations/offer_alliance/FRA/ENG", True, 200),
        ("GET", "/observer/v1/wars/ENG/AMG", True, 200),
        ("GET", "/observer/v1/wars/FRA/ENG", True, 200),
        ("GET", "/observer/v1/relations/guarantee/FRA/SAV", False, 403),
        ("POST", "/observer/v1/relations/guarantee/FRA/SAV", True, 405),
        ("GET", "/observer/v1/effects/not-configured", True, 404),
        ("GET", "/observer/v1/relations/guarantee/FRA/SAV?retry=1", True, 422)]
    cases = data["cases"]
    require([(c["method"], c["path"], c["authorized"], c["http_status"]) for c in cases] == expected,
        "Retained13 HTTP cases differ")
    for case in cases:
        encoded = json.dumps(case["response"], ensure_ascii=True, allow_nan=False).encode("ascii")
        require(len(encoded) == case["response_bytes"] <= 262144, "Retained response serialized length differs")
    require(cases[0]["response"] == catalog(effects_enabled=False), "Sessionless capabilities do not reproject exactly")
    require(cases[9]["response"] == dict(error="unauthorized"), "Unauthorized response differs")
    require(cases[10]["response"] == dict(error="read_only_observer", requests_published=0), "Write refusal differs")
    require(cases[11]["response"] == dict(error="request_not_found"), "Sessionless effects404 differs")
    require(cases[12]["response"]["status"] == "unknown"
        and cases[12]["response"]["automatic_command_retry"] is False
        and cases[12]["response"]["native_calls"] == cases[12]["response"]["requests_published"] == 0,
        "Bad query was reported as native rejection/retry")
    relation_expected = ["current_relation_observed", "current_relation_observed", "current_relation_observed",
        "current_relation_observed", "reverse_relation_observed", "pair_absent_observed"]
    relation_results, war_results, roots_seen, raw_captures = [], [], [], []
    prior_time = None
    observer_identities = {}
    for ordinal, case in enumerate(cases[1:9], start=1):
        response = case["response"]
        record = response["record"]
        path = Path(record["path"]).resolve()
        kind = "relations" if ordinal <= 6 else "wars"
        require(path.parent == (OUT / "captures" / kind).resolve(), "Capture path escapes fixed scope")
        require(pin(path) == {k: record[k] for k in ("bytes", "sha256")}, "Complete capture pin differs")
        inputs[path.relative_to(ROOT).as_posix()] = pin(path)
        capture = json.loads(read(path, 256 * 1024))
        raw_captures.append(capture)
        identity = common_capture(capture, response, graphs[kind])
        require(kind not in observer_identities or observer_identities[kind] == identity, "Observer nonce changed between cases")
        observer_identities[kind] = identity
        stamp = datetime.fromisoformat(capture["captured_utc"])
        require(prior_time is None or stamp >= prior_time, "Capture order differs")
        prior_time = stamp
        if kind == "relations":
            require(relation_compact(capture, record) == response, "Relation HTTP body does not match frozen compact capture")
            action, actor, target = case["path"].split("/")[-3:]
            require(capture["action"] == action and capture["status"] == relation_expected[ordinal - 1],
                "Relation action/status differs")
            selected = _capture(capture, action)
            require(capture["passes"][0] == capture["passes"][1] == selected,
                "Relation complete passes differ")
            require((selected["pair"]["actor_tag"], selected["pair"]["target_tag"]) == (actor, target),
                "Relation selected pair differs")
            profile = PROFILES[action]
            base = int(selected["module_base"], 16)
            for role, other in (("actor", "target"), ("target", "actor")):
                handle_row(selected[role])
                index = selected["indexes"][role]
                header, entries = bytes.fromhex(index["header_hex"]), bytes.fromhex(index["entries_hex"])
                ranges = {(int(index["container"], 16), len(header)): header}
                if entries:
                    ranges[(int(index["array"], 16), len(entries))] = entries
                replay = RawRecordPort(ranges)
                projected = _index(replay, base, int(selected[role]["address"], 16) + 0x14f8,
                    profile["index"], selected[other]["slot"], selected["roots"]["count"])
                require(projected == index, "Relation retained index hex replay differs")
            obj = selected["object"]
            if obj is not None:
                object_raw = bytes.fromhex(obj["raw_object_hex"])
                replay = RawRecordPort({(int(obj["address"], 16), len(object_raw)): object_raw})
                require(_object(replay, base, profile, int(obj["address"], 16), selected["actor"], selected["target"],
                    selected["now_raw"]) == obj and replay.calls == 2, "Relation retained object raw replay differs")
                requested = profile["symmetric"] or (obj["first_handle"], obj["second_handle"]) == (
                    selected["actor"]["handle"], selected["target"]["handle"])
                require(obj["requested_direction_matches"] is requested, "Raw object requested direction differs")
            require(capture["global_membership_verified"] is False and capture["world_epoch_proven"] is False
                and capture["atomic_snapshot_proven"] is False and capture["AI_acceptance_verified"] is False,
                "Relation capture overclaims global/cause/atomic proof")
            require(selected["global_membership_verified"] is False and selected["global_membership_status"] == "not_sampled"
                and selected["effective_movement_permission_verified"] is False
                and selected["expiry_or_full_lifecycle_verified"] is False, "Indexed relation scope differs")
            inner = capture["read_budget"]
            require(inner["limits"] == dict(calls=4096, bytes=524288, single_read=65536, index_entries=256)
                and inner["calls"] <= capture["total_rpm_budget"]["calls"]
                and inner["bytes"] <= capture["total_rpm_budget"]["bytes"], "Relation shared budget differs")
            require(evaluate_relation_effect(action, None, capture, {})["status"] == "unknown",
                "Current relation without baseline/receipt became request completion")
            checked = dict(action=action, actor=actor, target=target, status=capture["status"],
                requested_direction_matches=obj["requested_direction_matches"] if obj else None,
                selected_object_address=obj["address"] if obj else None,
                raw_bilateral_indexes_replayed=True, selected_raw_object_replayed=obj is not None,
                current_indexed_membership_only=True)
            roots_seen.append(selected["roots"])
            relation_results.append(checked | dict(record=record, host_capture_duration_ms=capture["duration_ms"],
                outer_rpm_budget=capture["total_rpm_budget"], response_exact_compact_recomputed=True))
        else:
            require(war_compact(capture, record) == response, "War HTTP body does not match frozen compact capture")
            actor, target = case["path"].split("/")[-2:]
            expected_state = "opponents" if ordinal == 7 else "not_currently_opponents"
            require(capture["status"] == "observed" and capture["passes"][0] == capture["passes"][1] == capture["projection"],
                "War complete passes differ")
            require(all(capture[k] is False for k in ("automatic_command_retry", "atomic_main_thread_snapshot",
                "world_epoch_proven", "world_lifetime_lease_proven", "runtime_effect_verified")), "War scope overclaimed")
            require(capture["rpm_budget_used"]["calls"] <= capture["total_rpm_budget"]["calls"]
                and capture["rpm_budget_used"]["bytes"] <= capture["total_rpm_budget"]["bytes"], "War shared budget differs")
            checked = audit_graph(capture["projection"], actor, target, expected_state)
            roots_seen.append(capture["projection"]["roots"])
            war_results.append(checked | dict(record=record, host_capture_duration_ms=capture["duration_ms"],
                outer_rpm_budget=capture["total_rpm_budget"], response_exact_compact_recomputed=True))
    require(all(root == roots_seen[0] for root in roots_seen), "Recorded world roots/date changed across routes")
    root = roots_seen[0]
    require(root["manual_pause"] == 1 and root["date"] == 56461512
        and root["count"] == root["capacity"] == 1380
        and root["reset"] == root["load_source"] == root["recalculating"] == root["ironman"] == 0,
        "Retained host world guards differ")
    require(datetime.fromisoformat(data["verified_utc"]) >= prior_time, "HTTP report predates last record")
    # Both symmetric alliance directions share one object. The reversed
    # guarantee sees that same object but must retain its negative direction.
    for left, right, symmetric in ((raw_captures[0], raw_captures[1], True),
            (raw_captures[3], raw_captures[4], False)):
        a, b = left["snapshot"], right["snapshot"]
        require(a["actor"] == b["target"] and a["target"] == b["actor"]
            and a["object"]["address"] == b["object"]["address"]
            and a["object"]["raw_object_hex"] == b["object"]["raw_object_hex"]
            and a["indexes"]["actor"] == b["indexes"]["target"]
            and a["indexes"]["target"] == b["indexes"]["actor"], "Reverse view does not preserve exact object/index identity")
        require(a["object"]["requested_direction_matches"] is True
            and b["object"]["requested_direction_matches"] is symmetric, "Symmetric/directed reverse status differs")
    journal_files = set((OUT / "captures/relations").glob("*.json")) | set((OUT / "captures/wars").glob("*.json"))
    require(len(journal_files) == 8, "Unexpected capture count for13 routes")
    require(data["listener_closed"] is True and data["server_thread_joined"] is True,
        "Retained producer did not record listener/thread closure")
    require(data["composed_factory"] == "tools.eu4_runtime_observer_r3.compose_server"
        and data["public_entry_process_launched"] is False, "Real composition was mislabeled as public entry launch")
    require(data["memory_written"] is False and data["new_API_effect_tested"] is False
        and data["exact_external_request_id_causality_verified"] is False
        and all(type(data[k]) is int and data[k] == 0 for k in
        ("native_calls", "requests_published", "saves_written", "reloads")), "HTTP acceptance scope differs")
    for path in (Path(__file__), ROOT / "work/audit_runtime_observer_live_20261015.py"):
        inputs[path.relative_to(ROOT).as_posix()] = pin(path)
    result = dict(schema="EU4-RUNTIME-OBSERVER-R3-INDEPENDENT-LIVE-FILE-AUDIT/1", audit_status="passed",
        findings=[], source_pins=inputs, checked_unique_inputs=len(inputs), frozen_R3_source_graph_pin_count=94,
        input_report_sha256=SHA, HTTP_case_count=13, complete_capture_records_verified=8,
        exact_compact_responses_recomputed=8, serialized_response_lengths_recomputed=13,
        relations=relation_results, wars=war_results, recorded_roots=root,
        current_relation_cases_verified=6, current_war_cases_verified=2, new_API_effects_verified=0,
        source_authenticated_listener_closure_and_join_consistent=True,
        actual_listener_probe_by_auditor=False, actual_HTTP_requests_sent_by_auditor=0,
        public_entry_process_launched_by_original_verification=False,
        public_entry_final_manifest_or_CLI_launch_verified_by_this_audit=False,
        timing=dict(relation_host_capture_duration_ms_range=[min(x["host_capture_duration_ms"] for x in relation_results),
            max(x["host_capture_duration_ms"] for x in relation_results)],
            war_host_capture_duration_ms_range=[min(x["host_capture_duration_ms"] for x in war_results),
            max(x["host_capture_duration_ms"] for x in war_results)],
            HTTP_request_round_trip_duration_recorded=False, pure_reader_microbenchmark_used_as_HTTP_timing=False,
            explanation="Host duration excludes some startup/pin work, composition guards, journal and HTTP serialization/transmission; complete HTTP RTT is not retained."),
        request_causality_verified=False, AI_acceptance_verified=False, saved_state_verified=False,
        cold_reload_verified=False, atomic_world_epoch_verified=False, global_relation_membership_verified=False,
        peace_terms_verified=False, peace_completion_verified=False, war_retirement_verified=False,
        complete_raw_RPM_reexecution_performed=False, raw_relation_index_and_object_replay_performed=True,
        old_tests_rerun=False, game_process_accessed=False, native_calls=0, requests_published=0,
        frozen_files_modified=False, resources=dict(peak_committed_bytes=check_memory_budget(),
            memory_limit_bytes=768 * 1024 * 1024),
        limitations=["Eight current observations are not absent-to-present request effects; no pre-publication baseline or original receipt is supplied.",
            "Relation index headers, complete entry arrays and selected object hex replay; relation-record/world bytes and war raw RPM transcript are not retained.",
            "War decoded full global/side/index graphs are checked independently, without claiming raw-memory decoder reexecution.",
            "HTTP no-store/real transport/closed-listener checks are producer source plus receipt evidence, not a new socket test.",
            "This exercises frozen R3.compose_server; final public entry process/manifest remains separate evidence.",
            "Host capture durations are above900ms; the producer did not record total HTTP round-trip latency."])
    output = OUT / "independent-live-http-file-audit.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    markdown = OUT / "independent-live-http-file-audit.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# R3 composed HTTP independent file audit\n\n"
            "All13 retained cases are consistent: sessionless capabilities with empty request effects/3 relation types;6 relation observations;2 war observations;403 authorization refusal;405 write refusal;404 unconfigured effects; and malformed query422 with unknown/no retry. Eight exact record hashes and compact HTTP projections match.\n\n"
            "FRA↔POR alliance shares the same symmetric typed object. ORL→BRI marriage is current. FRA→SAV guarantee and reversed SAV→FRA share one raw object, but the reversed direction remains false/reverse_relation_observed. FRA→ENG alliance is absent in both selected typed indexes. Complete retained index/header/object hex replays. ENG→AMG and FRA→ENG current opponent positive/negative graphs agree with both native indexes and the full four-war scan.\n\n"
            f"{len(inputs)} fixed input/source pins passed, including94 frozen composition pins. Listener closure/thread join are source-consistent retained producer evidence; no new socket or game access was used. This tested frozen R3.compose_server, not a launched final public entry.\n\n"
            "Reported host capture durations are1141.838–1208.371ms for relations and931.607–949.518ms for wars. Full HTTP round-trip latency was not recorded; pure-reader timings must not replace it. No new API effect, exact request cause, AI acceptance, institution completion, global relation lifecycle, peace completion, save or cold reload is established. Old tests were not rerun.\n")
    print(json.dumps(dict(audit=pin(output), markdown=pin(markdown), inputs=len(inputs), cases=13,
        captures=8, new_API_effects=0, game_process_accessed=False)))


if __name__ == "__main__":
    main()
