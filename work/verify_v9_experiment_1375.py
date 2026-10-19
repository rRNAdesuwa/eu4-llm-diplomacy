"""Fixed offline v9 cancellation/save/reload evidence review. No process/UI calls.

Reads bounded reports and the stopped log; re-extracts the preserved save with
the streaming parser. Selected consistency is not request causality, exact
loaded filename, strict single-player provenance, or production readiness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import decode_json
from work import inspect_diplomacy_save as saves
from work import probe_diplomacy_relations_v7_1375 as observer
from work import probe_fixture_pair_v9_1375 as fixture
from work.native import lab_protocol_v9_1375 as lab

RUNTIME = ROOT / "work/runtime"
PID, CREATION, THREAD = 60888, "01dd56890aab4cd6", 21872
WORLD, RELOAD_WORLD = "0x22f8d59a080", "0x2d8c0809020"
RELOAD_PID, RELOAD_CREATION = 54232, "01dd568b5be898da"
INITIAL_DATE, FINAL_DATE = 56456976, 56457192
DLL_SHA = "6C2D8420525E7E3C21F2EB20DFEA9C991B86AF8AC82211F1557F89436FDA896A"
MANIFEST_SHA = "d4406614fdcad03d21350656f23d9a6ae90db12e719f16cad7c6b768a4a5815f"
LOG_SHA = "d93c2fe084ba7e8f48688ffd8c304770afc50868d3b15526045d0b2f947cb53b"
LOG_BYTES = 444931
SAVE_SHA = "A0FD329156118EE8284FE214223609FB73F3EAF55C4C6B81278D4171EE4D9F39"
SAVE_BYTES = 35777015
SAVE_NAME = "llm_diplomacy_1375_v9_cancel_vassal_20261008a.eu4"
SESSION_NAME = f"native1375-v9/session-{PID}-{CREATION}"
FILES = {
    "loader": "native1375-v9/loader-install-60888.json",
    "phases": "native1375-v9/phases-ready-60888.json",
    "on": "native1375-v9/fixture-on-status-1-60888.json",
    "legality": "native1375-v9/cancel-vassal-legality-status-2-60888.json",
    "submit": "native1375-v9/cancel-vassal-status-3-60888.json",
    "final": "native1375-v9/final-status-60888.json",
    "fixture_baseline": "native1375-v9/fixture-baseline-60888.json",
    "fixture_on": "native1375-v9/fixture-after-on-60888.json",
    "fixture_cancel": "native1375-v9/fixture-after-cancel-60888.json",
    "fixture_reload": "native1375-v9/fixture-reload-54232.json",
    "baseline": "relations-v9-baseline-vassal-NAV-60888.json",
    "fixture_relation": "relations-v9-fixture-vassal-NAV-60888.json",
    "before": "relations-v9-before-cancel-vassal-NAV-60888.json",
    "after": "relations-v9-after-cancel-vassal-NAV-60888.json",
    "saved_relation": "relations-v9-saved-cancel-vassal-NAV-60888.json",
    "reload": "relations-v9-reload-cancel-vassal-NAV-54232.json",
    "comparison": "relations-v9-cancel-vassal-NAV-result-60888.json",
    "saved": "save-v9-cancel-vassal-60888.json",
    "copy": "native1375-v9/cancel-vassal-save-copy-60888.json",
    "restart": "test-restart-1375-20261007T184043356Z.json",
    **{f"speed_{seq}": f"native1375-v9/post-cancel-speed-{seq}-60888.json" for seq in range(4, 8)},
}


def json_report(path):
    raw = lab.read_bounded(Path(path), 1024 * 1024)
    return decode_json(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest().upper()


def selected_save_state(report):
    lab.require(report["parsed_complete"] is True and report["read_only"] is True
                and report["evidence_scope"] == "serialized_state_only" and report["runtime_effects_verified"] is False
                and report["actor"] == "FRA" and report["targets"] == ["NAV"], "Incomplete/wrong save extraction")
    lab.require(report["metadata"]["date"]["value"] == "1444.11.20"
                and report["metadata"]["player"]["value"] == "FRA"
                and report["metadata"]["multi_player"]["value"] == "no", "Wrong serialized date/player/premise")
    diplomacy = report["global_diplomacy"]
    lab.require(diplomacy["container_found"] is True and diplomacy["record_counts_scanned"].get("dependency", 0) > 0,
                "No complete global diplomacy/dependency scan")
    selected = []
    for record in diplomacy["records"]:
        fields = {item["key"]: item.get("value") for item in record["entries"] if item.get("key")}
        if {fields.get("first"), fields.get("second")} == {"FRA", "NAV"}:
            selected.append({"kind": record["key"], "fields": fields})
    lab.require(not any(row["kind"] in ("dependency", "alliance") for row in selected),
                "FRA/NAV dependency/alliance still serialized")
    truce = {}
    for actor, target in (("FRA", "NAV"), ("NAV", "FRA")):
        country = report["countries"][actor]
        lab.require(country["status"] == "found" and country["active_relations_container_found"] is True,
                    "Selected country/relation container was not scanned")
        relation = country["relations"][target]
        lab.require(relation["status"] == "found" and len(relation["blocks"]) == 1, "Ambiguous selected relation block")
        values = [item.get("value") for item in relation["blocks"][0]["entries"] if item.get("key") == "truce"]
        lab.require(values == ["yes"], "Selected bilateral truce was not serialized")
        truce[f"{actor}->{target}"] = True
    nav = report["countries"]["NAV"]
    lab.require("overlord" not in nav["field_inventory"] and not any(item.get("key") == "overlord" for item in nav["fields"]),
                "NAV still has a serialized overlord field")
    return {"selected_global_records": selected, "dependency_absent": True, "nav_overlord_field_absent": True,
            "bilateral_truce": truce, "scope": "complete_selected_serialized_sections_only"}


def fixture_state(report, *, pid, creation, world, date, independent, truce):
    lab.require(report["schema"] == "fixed_fixture_pair_v9_1375_observation_v1" and report["read_only"] is True
                and report["layout_evidence_sha256"] == fixture.EVIDENCE_SHA and report["consistent"] is True
                and report["atomic_snapshot"] is False and report["request_causality_verified"] is False,
                "Unreviewed fixture snapshot")
    passes = report["passes"]
    lab.require(len(passes) == 2 and passes[0] == passes[1], "Fixture snapshot is not two consistent passes")
    sample = passes[0]
    live = sample["live"]
    lab.require(live["pid"] == pid and live["creation"] == creation and live["world_cookie"] == world
                and live["raw_date"] == date and int(live["player_handle"], 16) == fixture.HANDLES["FRA"],
                "Fixture world/process identity differs")
    for tag, handle in fixture.HANDLES.items():
        lab.require(int(sample["countries"][tag]["handle"], 16) == handle, "Fixture country full handle differs")
    overlord = int(sample["countries"]["NAV"]["overlord"], 16)
    lab.require((overlord >> 56 == 0) if independent else (overlord == fixture.HANDLES["FRA"]),
                "NAV overlord differs from the expected selected state")
    lab.require(report["nav_independent"] is independent and report["bilateral_no_alliance"] is True
                and report["bilateral_no_truce"] is (not truce), "Fixture summary contradicts expected state")
    for actor, target in (("FRA", "NAV"), ("NAV", "FRA")):
        relation = sample["relations"][f"{actor}->{target}"]
        lab.require(lab.integer(relation["alliance_count"], 0, 4096)
                    and relation["alliance_count"] == len(relation["entries"]), "Unbounded/incomplete alliance index")
        expected_slot = (fixture.HANDLES[target] >> 32) & 0xFFFF
        lab.require(all(lab.integer(item["slot"], 0, 4095) for item in relation["entries"])
                    and not any(item["slot"] == expected_slot for item in relation["entries"])
                    and relation["matching_alliance"] is False, "Unexpected selected alliance")
        flags = relation["truce_flags"]
        lab.require(lab.integer(flags, 0, 255) and bool(flags & 1) is truce
                    and relation["active_truce_bit0"] is truce, "Raw selected truce flags disagree")
    return sample


def verify_prefixes(path, statuses):
    """Bind status snapshots to actual stopped-log prefixes, without retaining log."""
    wanted = {row["log_sha256"]: row for row in statuses}
    matches, digest, total, latest = {}, hashlib.sha256(), 0, None
    with path.open("rb") as stream:
        while raw := stream.readline(lab.MAX_LINE + 1):
            total += len(raw)
            lab.require(total <= lab.MAX_LOG and len(raw) <= lab.MAX_LINE and raw.endswith(b"\n"), "Log framing/budget failed")
            digest.update(raw)
            event = decode_json(raw.decode("utf-8"))
            if event.get("event") == "research_frame":
                latest = event
            current = digest.hexdigest()
            if current in wanted:
                lab.require(wanted[current]["latest_frame"] == latest, "Status frame differs from its exact log prefix")
                matches[current] = total
    lab.require(set(matches) == set(wanted) and total == LOG_BYTES and digest.hexdigest() == LOG_SHA,
                "Status prefix or complete stopped-log hash differs")
    return matches


def relation(report, *, pid, creation, world, date, expected):
    sample, state, times = observer.validated_report(report)
    lab.require(report["source"]["pid"] == pid and report["source"]["process_creation_filetime"] == int(creation, 16)
                and report["action"] == "vassalaction" and report["actor"] == "FRA" and report["target"] == "NAV"
                and sample["game"] == world and sample["current_raw_date"] == date and state["state"] == expected,
                "Relation report identity or selected state differs")
    for tag, handle in fixture.HANDLES.items():
        lab.require(int(sample["pair"][tag]["handle"], 16) == handle, "Relation report country handle differs")
    if expected == "active":
        lab.require(state["object"]["type_name"]["name"] == "vassal"
                    and state["object"]["started_raw_date"] == INITIAL_DATE, "Fixture relation is not the expected new vassal")
    return sample, state, times


def review():
    reports, hashes = {}, {}
    for key, name in FILES.items():
        reports[key], hashes[name] = json_report(RUNTIME / name)
    build, digest = lab.verify_build()
    lab.require(digest == MANIFEST_SHA and build["dll_sha256"] == DLL_SHA,
                "Build differs from the fixed deployed v9 experiment")
    hashes["native1375-v9/build.json"] = digest.upper()
    lab.require(lab.file_hash(fixture.EVIDENCE).lower() == fixture.EVIDENCE_SHA, "Fixture layout evidence changed")
    session = RUNTIME / SESSION_NAME
    metadata = lab.read_session_metadata(session, PID, CREATION)
    lab.require(metadata["window_thread"] == THREAD, "Wrong native game thread")
    evidence = lab.read_evidence(session, metadata)
    lab.require(evidence["log_bytes"] == LOG_BYTES and evidence["log_sha256"] == LOG_SHA,
                "Stopped complete log differs from reviewed bytes")
    lab.require(set(evidence["requests"]) == set(range(1, 8)) and evidence["last_sequence"] == 7
                and not evidence["pending"] and not evidence["lease_pending"], "Extra/missing/uncertain native request")
    hashes[SESSION_NAME + "/research-1375.jsonl"] = LOG_SHA.upper()
    for name in ["session.json", "install.claim", *[item[1] for item in lab.PHASES.values()],
                 "00000000000000000001.fixture-profile", *[f"{seq:020}.{suffix}" for seq in range(1, 8) for suffix in ("claim", "host-intent")],
                 *[f"{seq:020}.lease-pause.claim" for seq in range(4, 8)]]:
        hashes[SESSION_NAME + "/" + name] = lab.file_hash(session / name)
    statuses = [reports[key] for key in ("phases", "on", "legality", "submit", "final")]
    prefixes = verify_prefixes(session / "research-1375.jsonl", statuses)
    for status in statuses:
        lab.require(status["pid"] == PID and status["creation"] == CREATION
                    and status["purpose"] == lab.PURPOSE and status["protocol"] == lab.PROTOCOL
                    and status["dll_sha256"] == DLL_SHA and status["manifest_sha256"] == MANIFEST_SHA
                    and status["phases"] == {key: True for key in lab.PHASES}
                    and status["production_backend_registered"] is False and status["applied_verified"] is False,
                    "Status build/process/phases differ")
    for key, sequence in (("on", 1), ("legality", 2), ("submit", 3)):
        lab.require(reports[key]["request"] == evidence["requests"][sequence], "Status request differs from complete raw log")
    loader = reports["loader"]
    lab.require(loader["pid"] == PID and loader["creation"] == CREATION and loader["purpose"] == lab.PURPOSE
                and loader["dll_sha256"] == DLL_SHA and loader["manifest_sha256"] == MANIFEST_SHA
                and loader["plan_only"] is False and loader["installation"]["bridge_thread_exit_status"] == "0x0"
                and loader["fixture_disk_evidence"]["profile_sha256"] == lab.FIXTURE_PROFILE_SHA256
                and loader["fixture_disk_evidence"]["fixture_definition_files_verified"] is True
                and loader["fixture_disk_evidence"]["installed_before_process_creation"] is True,
                "Loader/install fixture provenance differs")
    on = evidence["requests"][1]
    lab.require(on["request"]["operation"] == "fixture" and on["request"]["action"] == "fixture_on"
                and on["complete"]["reason"] == 0, "Different fixture invocation")
    for field in ("native_invoked", "callback_returned", "callback_success", "result_destroyed", "arguments_unchanged", "callback_flag_restored", "world_identity_unchanged"):
        lab.require(on["complete"][field] is True, "Fixture callback/cleanup incomplete")
    for sequence, mode, status in ((2, "legality_only", 1), (3, "submit", 2)):
        request = evidence["requests"][sequence]
        wire = request["request"]
        core = request["records"][-1]
        lab.require(wire["operation"] == "pair" and wire["mode"] == mode and wire["action"] == "cancel_vassalization"
                    and wire["actor"] == "FRA" and wire["target"] == "NAV"
                    and core["event"] == "pair_engine_complete" and core["status"] == status and core["reason"] == 0
                    and core["thread_id"] == THREAD and core["world"] == WORLD and core["raw_date"] == INITIAL_DATE
                    and core["exception"] == 0 and core["freeze_session"] is False and core["ownership_uncertain"] is False
                    and core["preview_allowed"] is True and core["gate_allowed"] is True and core["original_destroyed"] is True,
                    "Uncertain/wrong native pair operation")
        if mode == "submit":
            lab.require(all(core[name] is True for name in ("submit_entered", "submit_returned", "context_submit_return", "caller_container_consumed")),
                        "Native send/ownership transfer not verified")
        else:
            lab.require(core["submit_entered"] is False and core["submit_returned"] is False
                        and core["command_destroyed_before_dispatch"] is True, "Legality sent or failed cleanup")
    speed_results = []
    for sequence in range(4, 8):
        request = evidence["requests"][sequence]
        wire = request["request"]
        report = reports[f"speed_{sequence}"]
        lab.require(wire["operation"] == "speed" and wire["mode"] == "submit" and wire["speed"] == 5
                    and wire["actor"] == wire["target"] == "FRA" and wire["action"] == "none"
                    and report["status"] == "completed_and_paused", "Different supervised speed request")
        path = session / f"{sequence:020}.supervisor.jsonl"
        raw = lab.read_bounded(path, 65536)
        hashes[SESSION_NAME + "/" + path.name] = hashlib.sha256(raw).hexdigest().upper()
        events = [decode_json(line) for line in raw.decode("utf-8").splitlines()]
        lab.require(len(events) == 2 and events[0]["event"] == "supervisor_armed"
                    and events[1]["event"] == "supervisor_complete" and Path(report["report"]) == path,
                    "Supervisor lacked exact successful boundaries")
        for event in events:
            lab.require(event["pid"] == PID and event["creation"] == CREATION and event["sequence"] == sequence
                        and event["speed"] == 5 and event["retry_allowed"] is False, "Supervisor identity differs")
        before, after = events[0]["before"], events[1]["after"]
        lab.require(events[1]["native_lease_complete"] == request["lease_complete"]
                    and 0 < events[1]["elapsed_seconds"] <= events[0]["deadline_seconds"] == 12
                    and before["paused"] is True and after["paused"] is True
                    and before["native_speed_index"] == after["native_speed_index"] == 0
                    and before["game"] == after["game"] == int(WORLD, 16)
                    and report["before_date"] == before["raw_date"] == INITIAL_DATE + (sequence - 4) * 48
                    and report["after_date"] == after["raw_date"] == INITIAL_DATE + (sequence - 3) * 48,
                    "Supervisor pause/date/lease evidence differs")
        speed_results.append({"sequence": sequence, "before_raw_date": before["raw_date"], "first_paused_raw_date": after["raw_date"]})
    for frame in (reports["final"]["latest_frame"], evidence["latest_frame"]):
        lab.require(frame["last_sequence"] == 7 and frame["paused"] is True and frame["raw_date"] == FINAL_DATE
                    and frame["world_cookie"] == WORLD and frame["native_speed_index"] == 0
                    and frame["session_frozen"] is False and frame["lease_active"] is False, "Wrong final paused frame")
    fixtures = {}
    for key, independent, truce in (("fixture_baseline", True, False), ("fixture_on", False, False), ("fixture_cancel", True, True)):
        fixtures[key] = fixture_state(reports[key], pid=PID, creation=CREATION, world=WORLD,
                                      date=INITIAL_DATE, independent=independent, truce=truce)
    fixture_state(reports["fixture_reload"], pid=RELOAD_PID, creation=RELOAD_CREATION, world=RELOAD_WORLD,
                  date=FINAL_DATE, independent=True, truce=True)
    relations = {}
    for key, expected, date in (("baseline", "absent", INITIAL_DATE), ("fixture_relation", "active", INITIAL_DATE),
                                ("before", "active", INITIAL_DATE), ("after", "absent", INITIAL_DATE),
                                ("saved_relation", "absent", FINAL_DATE)):
        relations[key] = relation(reports[key], pid=PID, creation=CREATION, world=WORLD, date=date, expected=expected)
    order = ("baseline", "fixture_relation", "before", "after", "saved_relation")
    lab.require(all(relations[first][2][1] <= relations[second][2][0] for first, second in zip(order, order[1:])),
                "Relation observation order differs")
    comparison = observer.compare_reports(reports["before"], reports["after"], "cancel")
    lab.require(comparison["observed_effect"] is True and comparison["transition"] == "removed_active_state"
                and all(reports["comparison"].get(key) == value for key, value in comparison.items())
                and reports["comparison"]["inputs"]["before_sha256"] == hashes[FILES["before"]].lower()
                and reports["comparison"]["inputs"]["after_sha256"] == hashes[FILES["after"]].lower(),
                "Stored cancellation comparison is not reproducible")
    saved, copy = reports["saved"], reports["copy"]
    selected = selected_save_state(saved)
    preserved = Path(copy["destination"])
    lab.require(copy["pid"] == PID and copy["creation"] == CREATION and copy["create_new"] is True and copy["bytes_equal"] is True
                and preserved.name == SAVE_NAME and copy["size"] == SAVE_BYTES and copy["sha256"].upper() == SAVE_SHA
                and saved["source"]["path"] == str(preserved) and saved["source"]["sha256"] == SAVE_SHA
                and saved["source"]["size_bytes"] == SAVE_BYTES, "Wrong preserved save/copy identity")
    for path in (Path(copy["source"]), preserved):
        lab.require(path.stat().st_size == SAVE_BYTES and lab.file_hash(path) == SAVE_SHA, "Save bytes changed")
    fresh = saves.inspect_save(preserved, "FRA", ("NAV",))
    lab.require(fresh["source"]["sha256"] == SAVE_SHA and selected_save_state(fresh) == selected
                and all(fresh[key] == saved[key] for key in ("metadata", "countries", "global_diplomacy")),
                "Stored extraction differs from a fresh bounded streaming save parse")
    restart = reports["restart"]
    lab.require(restart["purpose"] == "disposable_1375_test_restart" and restart["expected_pid"] == PID
                and restart["new_pid"] == RELOAD_PID and restart["executable_sha256"] == lab.LOCAL_SHA256
                and restart["save_sha256"] == SAVE_SHA and Path(restart["save"]) == preserved
                and restart["plan_only"] is False and restart["forced_test_process_exit"] is False
                and restart["loaded_save_verified"] is False, "Different restart provenance")
    reloaded = relation(reports["reload"], pid=RELOAD_PID, creation=RELOAD_CREATION, world=RELOAD_WORLD,
                        date=FINAL_DATE, expected="absent")
    lab.require(WORLD != RELOAD_WORLD and CREATION != RELOAD_CREATION
                and relations["saved_relation"][2][1] < reloaded[2][0], "No independently observed later process/world")
    # No raw pointers, missions, or whole-world fields are equated across reload.
    return {"schema_version": 1, "purpose": "v9_cancel_vassal_experiment_evidence_review",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(), "read_only": True,
            "pid": PID, "creation": CREATION, "game_sha256": lab.LOCAL_SHA256, "dll_sha256": DLL_SHA,
            "manifest_sha256": MANIFEST_SHA, "fixture_profile_sha256": lab.FIXTURE_PROFILE_SHA256,
            "phase_checks_passed": True, "fixture_callbacks_completed": ["fixture_on"],
            "fixture_baseline_independent_no_alliance_no_truce": True,
            "fixture_on_vassal_no_alliance_no_truce": True, "pair_submits": 1,
            "last_sequence": 7, "final_paused": True, "final_raw_date": FINAL_DATE,
            "supervised_speed_checkpoints": speed_results,
            "actions": {"cancel_vassalization": {"native_legality_checked": True, "native_dispatch_completed": True,
                "observed_relation_removed": True, "nav_independent_after": True, "bilateral_truce_after": True,
                "saved_result_consistent": True, "saved_reload_state_consistent": True}},
            "save_sha256": SAVE_SHA, "save_bytes": SAVE_BYTES, "saved_selected_state": selected,
            "streamed_save_extraction_reproduced": True,
            "reload": {"pid": RELOAD_PID, "creation": RELOAD_CREATION, "world": RELOAD_WORLD, "raw_date": FINAL_DATE,
                       "selected_dependency_state": "absent", "nav_independent": True, "bilateral_truce": True},
            "complete_log": {"path": SESSION_NAME + "/research-1375.jsonl", "size_bytes": LOG_BYTES, "sha256": LOG_SHA},
            "status_prefix_bytes": prefixes, "input_sha256": hashes,
            "reviewer_sha256": lab.file_hash(Path(__file__)),
            "request_id_causality_verified": False, "whole_world_unchanged_verified": False,
            "exact_loaded_file_path_verified": False, "strict_live_single_player_verified": False,
            "world_generation_verified": False, "production_backend_registered": False,
            "limitations": ["The fixture intentionally establishes the vassal relation before cancellation.",
                "Only selected relations, overlord and truce evidence are compared across processes.",
                "The supervision checkpoint for sequence 7 is 1444.11.19; the final paused save/reload state is 1444.11.20.",
                "No exact request-ID causality, AI acceptance, loaded save path, or whole-world invariance is proved."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RUNTIME / "native1375-v9/experiment-summary-60888.json")
    args = parser.parse_args()
    result = review()
    lab._no_links(args.output)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "actions": result["actions"], "final_raw_date": result["final_raw_date"]}))


if __name__ == "__main__":
    main()
