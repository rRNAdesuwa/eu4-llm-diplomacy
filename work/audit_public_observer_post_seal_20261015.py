"""Small post-seal consistency receipt; no process, socket or old test run."""
import ast
from datetime import datetime
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.eu4_observer import source_pins, MANIFEST
from bridge.tag_command_backend import read, digest, require, validate_identity
from bridge.diplomacy_effect_observer import full_handle

DIRECTORY = ROOT / "work/reports/runtime-observer-20261015-r3"
REPORT = DIRECTORY / "public-entry-verification.json"
CANDIDATE_REVIEW = ROOT / "work/reports/eu4-observer-entry-review-20261015-r1/independent-candidate-review.json"


def pin(path):
    raw = read(path, 16 * 1024 * 1024)
    return dict(bytes=len(raw), sha256=digest(raw))


def main():
    require(pin(MANIFEST)["sha256"] == "23c6831a861425c5f3012b583c93c6c1ccf7d10c769f9a23389474d389c9b361",
        "Public sealed manifest differs")
    require(pin(REPORT) == dict(bytes=22509, sha256="658ea5397e61a1d0cd635aa65328b69bb529c2a9895d1ab07339791785bcc38f"),
        "Fixed public acceptance changed")
    require(pin(CANDIDATE_REVIEW)["sha256"] == "912db3d09dfaa1c2b5b9d1855a21a7216bdc7b0ffadfbfa014cddf9eea7a3d5c",
        "Prior candidate review changed")
    report = json.loads(read(REPORT, 65536))
    candidate = json.loads(read(CANDIDATE_REVIEW, 65536))
    checked = source_pins()
    require(len(checked) == 98 and checked == report["source_pins"], "Public full graph differs")
    require(checked["tools/eu4_observer.py"] == candidate["candidate_entry_pin"]
        and checked["bridge/tests/test_eu4_observer_entry.py"] == candidate["candidate_tests_pin"],
        "Reviewed candidate bytes changed during sealing")
    producer = ROOT / report["producer"]["path"]
    require(pin(producer)["sha256"] == report["producer"]["sha256"], "Public verification producer changed")
    producer_tree = ast.parse(read(producer, 65536).decode("utf-8"))
    attrs = {n.func.attr for n in ast.walk(producer_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    require("run" in attrs and not {"publish", "install", "load", "WriteProcessMemory", "CreateRemoteThread"} & attrs,
        "Public verification producer invocation differs")
    expected_args = ["relations", "--pid", "80340", "--creation", "01dd5c075fcf8c26", "status",
        "--action", "guarantee", "--actor", "SAV", "--target", "FRA"]
    require(report["command_arguments"] == expected_args and report["exit_code"] == 0
        and report["child_process_completed"] is True, "Public live CLI completion differs")
    response = report["response"]
    identity = validate_identity(response["identity"])
    require((identity["pid"], identity["creation"]) == (80340, "01dd5c075fcf8c26"), "Response process identity differs")
    require(response["schema"] == "EU4-RELATION-STATE-RESPONSE/1" and response["action"] == "guarantee"
        and response["status"] == "reverse_relation_observed" and response["requested_direction_matches"] is False
        and response["current_relation_observed"] is False and response["two_pass_equal"] is True,
        "Public directional/current state differs")
    pair, obj = response["pair"], response["object"]
    require((pair["actor_tag"], pair["target_tag"]) == ("SAV", "FRA"), "Public selected TAGs differ")
    actor_slot, _ = full_handle(int(pair["actor_handle"], 16), 1380, tag="SAV")
    target_slot, _ = full_handle(int(pair["target_handle"], 16), 1380, tag="FRA")
    raw_object = bytes.fromhex(obj["raw_object_hex"])
    require(len(raw_object) == 72 and struct.unpack_from("<I", raw_object, 8)[0] == 357
        and struct.unpack_from("<QQ", raw_object, 0x10) == (int(pair["target_handle"], 16), int(pair["actor_handle"], 16))
        and raw_object[0x28:0x2a] == b"\0\0" and obj["vtable_rva"] == "0x1c817d8"
        and obj["first_handle"] == pair["target_handle"] and obj["second_handle"] == pair["actor_handle"]
        and obj["requested_direction_matches"] is False, "Raw guarantee direction/lifecycle differs")
    base = struct.unpack_from("<Q", raw_object)[0] - 0x1c817d8
    require(0 < struct.unpack_from("<i", raw_object, 0x20)[0] == obj["started_raw_date"] <= response["now_raw"] == 56461512,
        "Guarantee observed raw date differs")
    for role, wanted in (("actor", target_slot), ("target", actor_slot)):
        index = response["physical_pair_indexes"][role]
        header, entries = bytes.fromhex(index["header_hex"]), bytes.fromhex(index["entries_hex"])
        vt, array, capacity, count = struct.unpack("<QQii", header)
        require(vt == base + 0x1c3a538 and capacity == count == 1
            and array == int(index["array"], 16) and index["count_signed"] == index["capacity_signed"] == 1
            and len(entries) == 16 and digest(entries) == index["records_sha256"]
            and struct.unpack("<i4xQ", entries) == (wanted, int(obj["address"], 16))
            and index["object_pointer"] == obj["address"] and index["selected_member"] is True
            and index["allocation_metadata_guarded"] is True, "Public bilateral index raw evidence differs")
    require(response["record"] is None, "Expected compact-only CLI response")
    stdout = (json.dumps(response) + "\r\n").encode("utf-8")
    require(len(stdout) == 3044 and digest(stdout) == report["stdout_sha256"], "Windows CLI stdout hash does not reconstruct")
    prior_path = DIRECTORY / "captures/relations/relation-guarantee-SAV-FRA-1792008319382748500.json"
    require(pin(prior_path) == dict(bytes=20893, sha256="e251609eb5abf9f5fba062227ed5ead62fa3f1fc40e155418f0b2d190a4655cc"),
        "Prior full reverse capture changed")
    prior = json.loads(read(prior_path, 65536))
    require(prior["passes"][0] == prior["passes"][1] == prior["snapshot"], "Prior complete passes differ")
    prior_selected = prior["snapshot"]
    require(prior_selected["pair"] == pair and prior_selected["object"] == obj
        and prior_selected["indexes"] == response["physical_pair_indexes"]
        and prior_selected["now_raw"] == response["now_raw"], "Public selected fields differ from prior full current-state capture")
    require(response["duration_ms"] == 1300.129 and response["rpm_budget"] == dict(calls=1572, bytes=36620, largest_read=11040),
        "Public host duration/budget differs")
    require(all(response[k] is False for k in ("runtime_effect_verified", "global_membership_verified",
        "request_causality_verified", "AI_acceptance_verified", "world_epoch_proven", "world_lifetime_lease_proven",
        "atomic_snapshot_proven", "automatic_command_retry", "native_session_installed", "memory_written")),
        "Public compact response overclaims effect/identity scope")
    require(report["new_API_effect_tested"] is False and report["memory_written"] is False
        and all(type(report[k]) is int and report[k] == 0 for k in ("native_calls", "requests_published", "saves_written", "reloads")),
        "Public acceptance effects scope differs")
    require(report["file_only_commands_previously_executed"] == [["catalog"], ["effects", "catalog"],
        ["relations", "check"], ["war", "check"]] and report["file_only_command_exit_codes"] == [0, 0, 0, 0],
        "Prior file-only command summary differs")
    require(datetime.fromisoformat(report["verified_utc"]) >= datetime.fromisoformat(response["captured_utc"]),
        "Public report predates capture")
    inputs = [MANIFEST, REPORT, CANDIDATE_REVIEW, producer, prior_path, Path(__file__)]
    receipt = dict(schema="EU4-PUBLIC-OBSERVER-POST-SEAL-INDEPENDENT-RECEIPT/1", status="passed",
        input_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in inputs},
        public_manifest_sha256=pin(MANIFEST)["sha256"], complete_public_source_graph_pin_count=98,
        complete_public_source_graph_canonical_sha256=digest(json.dumps(checked, sort_keys=True).encode("ascii")),
        reviewed_candidate_entry_and_test_bytes_unchanged=True, complete_public_source_graph_verified=True,
        public_live_CLI=dict(exit_code=0, child_completed=True, actor="SAV", target="FRA", action="guarantee",
            status="reverse_relation_observed", requested_direction_matches=False, current_relation_observed=False,
            two_pass_equal_reported=True, compact_response_only=True, complete_new_pass_payload_retained=False,
            selected_raw_object_and_indexes_match_prior_full_capture=True,
            stdout_windows_CRLF_hash_reconstructed=True, stdout_bytes=3044,
            host_capture_duration_ms=1300.129, HTTP_round_trip_duration_recorded=False),
        prior_file_only_commands=dict(count=4, exit_codes=[0, 0, 0, 0],
            evidence_scope="Retained root summary; original command stdout/exit receipts are not embedded in this producer report."),
        tests_rerun=False, cleanup_test_initial_failed_candidate_history_preserved=True,
        new_API_effects_verified=0, saved_state_verified=False, cold_reload_verified=False,
        game_process_accessed_by_auditor=False, HTTP_requests_sent_by_auditor=0, native_calls=0,
        frozen_sources_modified=False)
    output = DIRECTORY / "independent-public-post-seal-receipt.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(dict(receipt=pin(output), source_graph_pins=98, stdout_bytes=3044,
        candidate_unchanged=True, new_API_effects=0, game_process_accessed=False)))


if __name__ == "__main__":
    main()
