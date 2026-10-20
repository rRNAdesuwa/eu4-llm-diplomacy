"""Recover the R60 receipt projection from its retained native receipt only."""
from pathlib import Path
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession


def main():
    directory = ROOT / "work/runtime/r60-subject-execution-batch-20261019-001"
    evidence = directory / "report-evidence"
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    request = report["prefix"] + "_outbound"
    events = [json.loads(line) for line in
              (evidence / "native-events-slice.jsonl").open(encoding="utf-8")]
    receipts = [row for row in events if row.get("request_id") == request
                and row.get("event") == "native_peace_submission_result"]
    assert len(receipts) == 1
    native = receipts[0]
    parameters = report["steps"]["queries"][0]["parameters"]
    assert ObserverSession._valid_native_peace_submission_result(
        native, request, report["session_id"], "FRA", "ENG", "initiate",
        native["date_raw"], "release_subject", parameters)
    first = ObserverSession._public_native_peace_submission_receipt(
        native, request, "FRA", "ENG", "initiate", native["date_raw"],
        "release_subject", parameters)
    corrected = DiplomacyTools._public_peace_submission_receipt(
        first, request, "FRA", "ENG", "initiate", native["date_raw"],
        "release_subject", parameters)
    assert corrected is not None
    database = evidence / "diplomacy.sqlite3"
    backup = evidence / "diplomacy-before-receipt-repair.sqlite3"
    assert not backup.exists()
    with sqlite3.connect(database) as connection:
        with sqlite3.connect(backup) as target:
            connection.backup(target)
        row = connection.execute(
            "SELECT status, native_receipt_json FROM diplomacy_requests "
            "WHERE session_id=? AND request_id=?",
            (report["session_id"], request)).fetchone()
        assert row is not None and row[0] == "submitted"
        old = json.loads(row[1])
        missing = {"release_subject_countries", "transfer_subject_countries"}
        assert old == {key: value for key, value in corrected.items()
                       if key not in missing}
        correction = {"request_id": request, "source_event": native,
                      "old_receipt": old, "corrected_receipt": corrected,
                      "changed_status": False, "business_replayed": False}
        (evidence / "receipt-projection-correction.json").write_text(
            json.dumps(correction, ensure_ascii=False, indent=2), encoding="utf-8")
        cursor = connection.execute(
            "UPDATE diplomacy_requests SET native_receipt_json=? "
            "WHERE session_id=? AND request_id=? AND status='submitted' "
            "AND native_receipt_json=?",
            (json.dumps(corrected, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")), report["session_id"], request, row[1]))
        assert cursor.rowcount == 1
    print("Corrected two omitted receipt fields from original native evidence")


if __name__ == "__main__":
    main()
