"""Offline supplemental v8 marriage-removal save/reload evidence review.

Reads pinned reports and existing save files only. No UI, process or engine calls.
The original v8 experiment summary remains immutable and retains reload=false.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_relations_v7_1375 as observer
from work.native import lab_protocol_v8_1375 as lab
from work.local_config import user_data

RUNTIME = ROOT / "work/runtime"
SAVE_SHA = "0000E4218F266CA3F29E2A3695FA16F4A8F405B91168C2C15F9E14070DC49571"
SAVE_SIZE = 35901769
OLD_CREATION = "01dd5681d5d0e053"
NEW_CREATION = "01dd568c4bc812d0"
SUMMARY_SHA = "F322EFBA785D009D007695D7B0D38E553D2D759E418C0CB14CBE48D8AA481D06"
VASSAL_BEFORE_SHA = "F6BA8F96D55B599829E0BD4E744CE59A08AC4B807DFE6DAD86B1624BA9900983"
SAVE_NAME = "llm_diplomacy_1375_v8_break_marriage_20261008a.eu4"
FILES = {
    "summary": "native1375-v8/experiment-summary-39216.json",
    "save": "save-v8-break-marriage-39216.json",
    "copy": "native1375-v8/break-marriage-save-copy-39216.json",
    "restart": "test-restart-1375-20261007T184725795Z.json",
    "installed": "fixture-v8-reload-install-20261008a.json",
    "binding": "native1375-v8/reload-binding-20276.json",
    "marriage_before": "relations-v8-after-break-marriage-NAV-39216.json",
    "vassal_before": "relations-v8-after-ui-vassal-NAV-39216.json",
    "marriage_reloaded": "relations-v8-reloaded-break-marriage-NAV-20276.json",
    "vassal_reloaded": "relations-v8-reloaded-vassal-NAV-20276.json",
}


def aware_time(value):
    lab.require(isinstance(value, str), "Missing evidence timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    lab.require(result.tzinfo is not None, "Naive evidence timestamp")
    return result


def filetime(value):
    lab.require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{16}", value), "Malformed process creation")
    return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(value, 16) // 10)


def selected_fields(record):
    lab.require(isinstance(record, dict) and isinstance(record.get("entries"), list), "Malformed diplomacy record")
    result = {}
    for item in record["entries"]:
        lab.require(isinstance(item, dict), "Malformed diplomacy field")
        key = item.get("key")
        if key is not None:
            lab.require(isinstance(key, str) and key not in result, "Duplicate diplomacy scalar")
            result[key] = item.get("value")
    return result


def read_reports():
    reports, hashes = {}, {}
    for key, name in FILES.items():
        raw = lab.read_bounded(RUNTIME / name, 1024 * 1024)
        reports[key] = lab.decode_json(raw.decode("utf-8-sig"))
        lab.require(isinstance(reports[key], dict), "Report is not a JSON object")
        hashes[name] = hashlib.sha256(raw).hexdigest().upper()
    return reports, hashes


def verify_save_files(reports):
    # Reports cannot choose arbitrary files to hash. The two reviewed basenames
    # must remain ordinary files in the configured save directory.
    saved, restart, copy = (reports[key] for key in ("save", "restart", "copy"))
    root = user_data() / "save games"
    preserved = root / SAVE_NAME
    original = root / "法兰西1444_11_17.eu4"
    for claimed, expected in ((saved["source"]["path"], preserved), (copy["source"], original),
                              (copy["preserved"], preserved), (restart["save"], preserved)):
        lab.require(isinstance(claimed, str) and Path(claimed).absolute() == expected.absolute(), "Unexpected save path")
    for path in (original, preserved):
        lab._no_links(path)
        lab.require(path.is_file() and path.stat().st_size == SAVE_SIZE and lab.file_hash(path) == SAVE_SHA,
                    "Preserved save bytes changed")


def validate_reports(reports, hashes, manifest, manifest_sha):
    """Pure report validation. Disk save verification remains a required caller step."""
    summary = reports["summary"]
    lab.require(hashes[FILES["summary"]] == SUMMARY_SHA and hashes[FILES["vassal_before"]] == VASSAL_BEFORE_SHA,
                "Reviewed immutable v8 premise differs")
    lab.require(summary["schema_version"] == 1 and summary["purpose"] == "v8_experiment_evidence_review"
                and summary["read_only"] is True and summary["pid"] == 39216 and summary["creation"] == OLD_CREATION
                and summary["game_sha256"] == lab.LOCAL_SHA256 and summary["dll_sha256"] == manifest["dll_sha256"]
                and summary["manifest_sha256"] == manifest_sha and summary["fixture_profile_sha256"] == lab.FIXTURE_PROFILE_SHA256
                and summary["save_sha256"] == SAVE_SHA and summary["phase_checks_passed"] is True,
                "Supplement does not belong to the reviewed v8 experiment")
    marriage_summary = summary["actions"]["break_marriage"]
    lab.require(all(marriage_summary[key] is True for key in ("native_dispatch_completed", "observed_relation_removed", "saved_result_consistent"))
                and marriage_summary["saved_reload_state_consistent"] is False,
                "Original summary premise changed; never rewrite or upgrade it in place")
    for key in ("save", "copy", "marriage_before"):
        lab.require(hashes[FILES[key]] == summary["input_sha256"][FILES[key]], "Original summary input binding differs")
    saved, restart, copy = reports["save"], reports["restart"], reports["copy"]
    lab.require(saved["parsed_complete"] is True and saved["read_only"] is True
                and saved["evidence_scope"] == "serialized_state_only"
                and saved["source"]["sha256"] == SAVE_SHA, "Incomplete or different save extraction")
    lab.require(saved["source"]["size_bytes"] == SAVE_SIZE and saved["source"]["gamestate_bytes"] == SAVE_SIZE
                and saved["source"]["format"] == "plain_text" and saved["source"]["gamestate_sha256"] == SAVE_SHA
                and saved["actor"] == "FRA" and saved["targets"] == ["NAV"]
                and saved["global_diplomacy"]["container_found"] is True,
                "Wrong save extraction scope")
    lab.require(copy["sha256"] == SAVE_SHA and type(copy["size"]) is int and copy["size"] == SAVE_SIZE
                and copy["byte_identical"] is True and copy["overwrite"] is False, "Copy provenance differs")
    lab.require(restart["expected_pid"] == 54232 and restart["new_pid"] == 20276
                and restart["forced_test_process_exit"] is False and restart["plan_only"] is False
                and restart["save_sha256"] == SAVE_SHA and restart["loaded_save_verified"] is False
                and restart["purpose"] == "disposable_1375_test_restart" and restart["executable_sha256"] == lab.LOCAL_SHA256
                and restart["startup_option"] == "-continue=<verified test filename>",
                "Different restart provenance")
    lab.require(Path(restart["save"]).name == SAVE_NAME
                and saved["metadata"]["date"]["value"] == "1444.11.17"
                and saved["metadata"]["player"]["value"] == "FRA"
                and saved["metadata"]["multi_player"]["value"] == "no", "Different serialized premise")
    install = reports["installed"]
    lab.require(install["installed"] is True and install["enabled"] is True
                and install["fixture_profile"] == "v8"
                and install["fixture_profile_sha256"] == lab.FIXTURE_PROFILE_SHA256,
                "Reload used another selected fixture profile")
    binding = reports["binding"]
    live, fixture = binding["live"], binding["fixture_disk_evidence"]
    lab.require(binding["pid"] == 20276 and binding["creation"] == NEW_CREATION and binding["bridge_loaded"] is False
                and binding["read_only"] is True and live["pid"] == fixture["pid"] == binding["pid"]
                and live["creation"] == fixture["creation"] == binding["creation"]
                and fixture["installed_before_process_creation"] is True
                and fixture["fixture_definition_files_verified"] is True and fixture["engine_registration_verified"] is False
                and type(fixture["files_checked"]) is int and fixture["files_checked"] == 7
                and isinstance(fixture["enabled_mod_configuration_sha256"], str)
                and re.fullmatch(r"[0-9A-F]{64}", fixture["enabled_mod_configuration_sha256"])
                and fixture["profile_sha256"] == lab.FIXTURE_PROFILE_SHA256
                and type(live["raw_date"]) is int and live["raw_date"] == 56457120
                and int(live["player_handle"], 16) == observer.HANDLES["FRA"],
                "Missing read-only reload binding")
    created = filetime(binding["creation"])
    launched = aware_time(restart["launched_at_utc"])
    saved_at = aware_time(saved["captured_at_utc"])
    lab.require(filetime(OLD_CREATION) < saved_at < created and abs((launched-created).total_seconds()) <= 5,
                "Restart/capture chronology differs from the identified process")
    selected = []
    for record in saved["global_diplomacy"]["records"]:
        values = selected_fields(record)
        if {values.get("first"), values.get("second")} == {"FRA", "NAV"}:
            selected.append((record["key"], values))
    lab.require(not any(kind == "royal_marriage" for kind, _ in selected), "Marriage remains serialized")
    dependencies = [value for kind,value in selected if kind == "dependency"]
    lab.require(len(dependencies) == 1 and dependencies[0].get("first") == "FRA"
                and dependencies[0].get("second") == "NAV" and dependencies[0].get("subject_type") == "vassal"
                and dependencies[0].get("start_date") == "1444.11.13", "Expected single preserved vassal dependency")
    observed = {}
    previous_old = previous_new = old_source = new_source = None
    for key, action, expected in (("marriage", "royal_marriage", "absent"),
                                  ("vassal", "vassalaction", "active")):
        before, after = reports[key + "_before"], reports[key + "_reloaded"]
        old, old_state, old_times = observer.validated_report(before)
        new, new_state, new_times = observer.validated_report(after)
        lab.require(before["action"] == after["action"] == action and before["target"] == after["target"] == "NAV"
                    and before["source"]["pid"] == 39216 and after["source"]["pid"] == 20276
                    and after["source"]["process_creation_filetime"] == int(binding["creation"], 16)
                    and before["source"]["process_creation_filetime"] == int(summary["creation"], 16)
                    and before["source"]["process_creation_filetime"] < after["source"]["process_creation_filetime"]
                    and filetime(OLD_CREATION) <= old_times[0] <= old_times[1] <= saved_at
                    and old_times[1] < new_times[0] and max(created, launched) <= new_times[0],
                    "Missing separate process/world observation")
        # A new process may reuse every virtual address. PID+creation establishes
        # process separation; address inequality is neither required nor sufficient.
        lab.require(int(new["game"],16) == int(live["world_cookie"],16)
                    and int(new["player"]["handle"],16) == int(live["player_handle"],16)
                    and new["player"]["tag"] == old["player"]["tag"] == "FRA"
                    and int(old["player"]["handle"],16) == observer.HANDLES["FRA"]
                    and old["current_raw_date"] <= new["current_raw_date"], "Live binding/sample state differs")
        if previous_new is not None:
            for field in ("module_base", "database", "game", "country_array", "player", "pair"):
                lab.require(new[field] == previous_new[field] and old[field] == previous_old[field],
                            "Selected relation reports belong to different worlds or countries")
            lab.require(before["source"] == old_source and after["source"] == new_source,
                        "Selected relation reports have different process sources")
        previous_old, previous_new, old_source, new_source = old, new, before["source"], after["source"]
        lab.require(old_state["state"] == new_state["state"] == expected
                    and new["current_raw_date"] == 56457120, "Reloaded selected relation differs")
        if key == "vassal":
            lab.require(new_state["object"]["started_raw_date"] == 56457024,
                        "Serialized 1444.11.13 dependency start differs from live state")
            for field in ("actor_handle", "target_handle", "started_raw_date", "removed"):
                lab.require(old_state["object"][field] == new_state["object"][field], "Dependency fields differ")
            lab.require(old_state["object"]["type_name"]["name"]
                        == new_state["object"]["type_name"]["name"] == "vassal", "Dependency type differs")
        observed[action] = {"expected_state": expected, "reloaded_state": new_state,
                            "saved_reload_state_consistent": True, "reloaded_source": after["source"]}
    return {"purpose": "v8_marriage_removal_supplemental_reload_review", "read_only": True,
            "schema_version": 1, "reviewed_at_utc": datetime.now(timezone.utc).isoformat(), "input_sha256": hashes,
            "original_summary_sha256": SUMMARY_SHA, "original_summary_unchanged": True,
            "old_pid": 39216, "old_creation": OLD_CREATION, "reloaded_pid": 20276, "reloaded_creation": NEW_CREATION,
            "game_sha256": lab.LOCAL_SHA256, "separate_process_identity_verified": True,
            "world_generation_verified": False,
            "save_sha256": SAVE_SHA, "dll_sha256": manifest["dll_sha256"], "manifest_sha256": manifest_sha,
            "saved_reload_state_consistent": True, "actions": observed,
            "exact_loaded_file_path_verified": False, "request_id_causality_verified": False,
            "whole_world_unchanged_verified": False, "production_backend_registered": False,
            "limitations": ["Two consistent read passes are not an atomic or causal game-thread observation.",
                            "The restart argument and matching state do not independently identify the loaded filename.",
                            "Only the selected marriage absence and vassal identity are checked."]}


def review():
    reports, hashes = read_reports()
    manifest, manifest_sha = lab.verify_build()
    result = validate_reports(reports, hashes, manifest, manifest_sha)
    verify_save_files(reports)
    result["preserved_save_bytes_verified"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review()
    lab._no_links(args.output)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(json.dumps({"output": str(args.output), "saved_reload_state_consistent": True}))


if __name__ == "__main__":
    main()
