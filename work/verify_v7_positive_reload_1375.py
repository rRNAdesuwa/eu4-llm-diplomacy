"""Reproduce the bounded v7 FRA/NAV save-and-new-process evidence review.

Reads existing reports and hashes two existing saves. No engine/process/UI calls.
This verifies matching selected state, not request causality or the loaded path.
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
from work import probe_diplomacy_relations_v7_1375 as observer
from work.native import lab_protocol_v7_1375 as lab

RUNTIME = ROOT / "work/runtime"
SAVE_SHA = "F6A56C25FD366522C5F625BAFF086B33F02473EDCD34AAE3E3C2984D30436FB8"
PRESERVED_NAME = "llm_diplomacy_1375_v7_marriage_vassal_20261008a.eu4"
FILES = {
    "save": "save-v7-marriage-vassal-20261008a.json",
    "restart": "test-restart-1375-20261007T171801515Z.json",
    "marriage_before": "relations-v7-after-marriage-NAV-57404.json",
    "vassal_before": "relations-v7-after-vassal-NAV-57404.json",
    "marriage_reloaded": "relations-v7-reloaded-marriage-NAV-33256.json",
    "vassal_reloaded": "relations-v7-reloaded-vassal-NAV-33256.json",
}


def read(path):
    raw = lab.read_bounded(path, 1024 * 1024)
    return json.loads(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest().upper()


def review():
    reports, hashes = {}, {}
    for key, name in FILES.items():
        reports[key], hashes[name] = read(RUNTIME / name)
    saved, restart = reports["save"], reports["restart"]
    lab.require(saved["read_only"] is True and saved["parsed_complete"] is True
                and saved["evidence_scope"] == "serialized_state_only", "Incomplete save extraction")
    lab.require(saved["source"]["sha256"] == SAVE_SHA
                and lab.file_hash(Path(saved["source"]["path"])) == SAVE_SHA, "Source save changed")
    preserved = Path(restart["save"])
    lab.require(preserved.name == PRESERVED_NAME and restart["save_sha256"] == SAVE_SHA
                and lab.file_hash(preserved) == SAVE_SHA, "Restart save changed")
    lab.require(restart["expected_pid"] == 57404 and restart["new_pid"] == 33256
                and restart["plan_only"] is False and restart["loaded_save_verified"] is False,
                "Different restart provenance")
    lab.require(saved["metadata"]["date"]["value"] == "1444.11.13"
                and saved["metadata"]["player"]["value"] == "FRA"
                and saved["metadata"]["multi_player"]["value"] == "no", "Different save premise")
    serialized = {}
    for record in saved["global_diplomacy"]["records"]:
        values = {entry["key"]: entry.get("value") for entry in record.get("entries", []) if entry.get("key")}
        if values.get("first") == "FRA" and values.get("second") == "NAV":
            lab.require(record["key"] not in serialized, "Duplicate selected serialized relation")
            serialized[record["key"]] = values
    lab.require(serialized.get("royal_marriage", {}).get("start_date") == "1444.11.11"
                and serialized.get("dependency", {}).get("start_date") == "1444.11.13"
                and serialized["dependency"]["subject_type"] == "vassal", "Saved relations do not match")
    actions = {}
    for key, native_name in (("marriage", "royal_marriage"), ("vassal", "vassalaction")):
        before, reloaded = reports[key + "_before"], reports[key + "_reloaded"]
        old_sample, old_state, old_times = observer.validated_report(before)
        new_sample, new_state, new_times = observer.validated_report(reloaded)
        lab.require(before["action"] == reloaded["action"] == native_name
                    and before["target"] == reloaded["target"] == "NAV", "Different selected action")
        lab.require(before["source"]["pid"] == 57404 and reloaded["source"]["pid"] == 33256
                    and before["source"]["process_creation_filetime"] != reloaded["source"]["process_creation_filetime"]
                    and old_sample["game"] != new_sample["game"] and old_times[1] < new_times[0],
                    "No independently observed new process/world")
        lab.require(old_state["state"] == new_state["state"] == "active", "Selected relation is not active")
        for field in ("actor_handle", "target_handle", "started_raw_date", "removed"):
            lab.require(old_state["object"][field] == new_state["object"][field], "Relation identity fields differ")
        lab.require(new_sample["current_raw_date"] == 56457024, "Different reload date")
        if key == "vassal":
            lab.require(old_state["object"]["type_name"]["name"]
                        == new_state["object"]["type_name"]["name"] == "vassal", "Different dependency type")
        actions[native_name] = {"saved_reload_state_consistent": True, "serialized": serialized[
            "royal_marriage" if key == "marriage" else "dependency"],
            "reloaded_relation": new_state["object"], "reloaded_source": reloaded["source"]}
    return {"schema_version": 1, "purpose": "v7_positive_pair_save_reload_evidence_review",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(), "read_only": True,
            "saved_reload_state_consistent": True, "actor": "FRA", "target": "NAV",
            "save_sha256": SAVE_SHA, "input_sha256": hashes, "actions": actions,
            "exact_loaded_file_path_verified": False, "request_id_causality_verified": False,
            "whole_world_unchanged_verified": False, "production_backend_registered": False,
            "limitations": ["Only selected relations are compared; snapshots are bounded and not atomic.",
                            "Restart selected the audited save; the exact loaded filename is not independently read from the engine.",
                            "The test fixture intentionally changes diplomat count, reputation and opinions."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review()
    lab._no_links(args.output)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "saved_reload_state_consistent": True}))


if __name__ == "__main__":
    main()
