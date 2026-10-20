"""Recover the already rejected R61 request from its original native events."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    batch = ROOT / "work/runtime/r61-country-combined-execution-20261019-001"
    report_path = batch / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = batch / "report-evidence"
    output = batch / "reconciliation-001"
    output.mkdir(exist_ok=False)
    request_id = report["prefix"] + "_outbound"
    parameters = report["steps"]["queries"][0]["parameters"]
    installation = Path(report["installation"])
    log = installation.parent / "control-probe.jsonl"
    rows, raw = [], []
    with log.open("rb") as source:
        for number, line in enumerate(source, 1):
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if event.get("request_id") == request_id and event.get("event") in {
                    "native_peace_submission_result", "native_peace_execution_result"}:
                rows.append((number, event))
                raw.append(line)
    receipts = [row for _, row in rows if row["event"] == "native_peace_submission_result"]
    responses = [row for _, row in rows if row["event"] == "native_peace_execution_result"]
    assert len(receipts) == len(responses) == 1
    native, response = receipts[0], responses[0]
    date = native["date_raw"]
    session_id = report["session_id"]
    assert native["session_id"] == response["session_id"] == session_id
    assert response["outcome"] == "rejected"
    assert ObserverSession._valid_native_peace_submission_result(
        native, request_id, session_id, "FRA", "ENG", "initiate", date,
        "release_nation", parameters)
    first = ObserverSession._public_native_peace_submission_receipt(
        native, request_id, "FRA", "ENG", "initiate", date, "release_nation", parameters)
    receipt = DiplomacyTools._public_peace_submission_receipt(
        first, request_id, "FRA", "ENG", "initiate", date, "release_nation", parameters)
    assert receipt is not None
    result = ObserverSession._public_native_peace_execution_result(
        response, request_id, session_id, "FRA", "ENG", "initiate", date,
        "release_nation", parameters)
    assert result is not None and result["native_outcome"] == "rejected"
    database = evidence / "diplomacy.sqlite3"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status,payload_json FROM diplomacy_requests WHERE session_id=? AND request_id=?",
            (session_id, request_id)).fetchone()
        assert row is not None and row[0] == "invalidated"
        payload = json.loads(row[1])
        context = DiplomacyTools._native_submission_context(SimpleNamespace(
            payload=payload, native_receipt=receipt, request_id=request_id, session_id=session_id))
        assert context is not None
        with sqlite3.connect(output / "before.sqlite3") as backup:
            connection.backup(backup)
    shutil.copy2(report_path, output / "before-report.json")
    shutil.copy2(evidence / "native-events-slice.jsonl", output / "before-native-events-slice.jsonl")
    original = b"".join(raw)
    (output / "original-native-receipt-and-response.jsonl").write_bytes(original)
    correction = {"request_id": request_id, "session_id": session_id,
                  "source_log": str(log), "source_lines": [number for number, _ in rows],
                  "source_sha256": hashlib.sha256(original).hexdigest(),
                  "reason": "second receipt projection rejected the empty legacy beneficiary '-'",
                  "native_receipt": receipt, "native_response": result,
                  "business_replayed": False, "status_before": "invalidated"}
    with DurableJournal(database, report["experiment_id"] if "experiment_id" in report else installation.parent.name,
                        session_id, global_request_ids=True) as journal:
        journal.reconcile_rejected(
            request_id, result, receipt,
            expected_reason_code="NATIVE_PEACE_SUBMISSION_RECEIPT_INVALID",
            expected_payload=payload, evidence_content=correction)
        api = DiplomacyTools(journal, ObserverSession(installation, game_exe()))
        public = api.get_diplomatic_result(request_id)
        assert public["status"] == "rejected" and public["submitted"] is True
        write(output / "corrected-public-result.json", public)
    correction["status_after"] = public["status"]
    write(output / "report.json", correction)
    report["status"] = "reconciled_ready_to_resume"
    report["business_attempts"]["outbound"]["reconciliation"] = {
        "report": str(output / "report.json"), "status": public["status"],
        "submitted": public["submitted"], "business_replayed": False}
    write(report_path, report)
    print(json.dumps({"status": public["status"], "submitted": public["submitted"],
                      "business_replayed": False, "report": str(output / "report.json")}))


if __name__ == "__main__":
    main()
