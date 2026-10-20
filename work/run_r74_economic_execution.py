"""Execute one economic action or observe its existing durable request."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.run_peace_consequence_queries import _copy_bounded_slice, _write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--action-id", choices=("send_gift", "influence_nation", "stop_curry_favors"), required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--ducats", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--expect-unavailable", action="store_true")
    parser.add_argument("--expected-reason-text", default="")
    args = parser.parse_args()
    parameters = {"ducats": args.ducats} if args.action_id == "send_gift" else {}
    if (args.action_id == "send_gift") != (args.ducats is not None):
        parser.error("Only send_gift requires --ducats")
    output = args.output.resolve()
    if args.resume:
        if not (output / "diplomacy.sqlite3").is_file():
            raise ValueError("Resume requires the existing request journal")
    else:
        output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    offset = log.stat().st_size
    report = {"status": "running", "session_id": session.session_id,
              "request_id": args.request_id, "action_id": args.action_id,
              "actor": "FRA", "recipient": args.recipient, "parameters": parameters,
              "resume_only": args.resume, "installation": str(args.installation.resolve())}
    path = output / "diplomacy.sqlite3"
    try:
        with DurableJournal(path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            result = (api.get_diplomatic_result(args.request_id) if args.resume
                      else api.execute_diplomatic_action(
                          args.request_id, args.action_id, "FRA", args.recipient,
                          "initiate", parameters))
            report["initial"] = result
            deadline = time.monotonic() + 25
            while (result.get("submitted") is True
                   and result.get("game_outcome") not in ("executed", "accepted", "rejected")
                   and time.monotonic() < deadline):
                time.sleep(.15)
                result = api.get_diplomatic_result(args.request_id)
            report["result"] = result
        with DurableJournal(path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            reopened = DiplomacyTools(journal, session).get_diplomatic_result(args.request_id)
        proof = result.get("result", {})
        reasons = proof.get("inspection", {}).get("legality", {}).get("reasons", [])
        report["checks"] = ({
            "not_submitted": result.get("submitted") is False,
            "invalidated": result.get("status") == "invalidated",
            "native_reason_present": any(
                row.get("source") == "native_rule"
                and args.expected_reason_text in row.get("text", "") for row in reasons),
            "journal_reopen_equal": result == reopened,
        } if args.expect_unavailable else {
            "submitted": result.get("submitted") is True,
            "actual_unilateral_effect": result.get("game_outcome") == "executed",
            "execution_verified": proof.get("execution_verified") is True,
            "request_binding_verified": proof.get("request_binding_verified") is True,
            "journal_reopen_equal": result == reopened,
        })
        report["status"] = "passed" if all(report["checks"].values()) else "incomplete"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    suffix = "resume-" if args.resume else ""
    report["native_slice"] = _copy_bounded_slice(log, offset, output / f"{suffix}native.jsonl")
    _write_json(output / f"{suffix}report.json", report)
    print(json.dumps({key: report.get(key) for key in ("status", "checks", "error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
