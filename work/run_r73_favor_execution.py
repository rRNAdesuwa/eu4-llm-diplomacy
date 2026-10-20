"""Submit one favor exchange, or resume its existing journal without sending."""
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
from work.run_peace_consequence_queries import _write_json, _copy_bounded_slice


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installation", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--request-id", required=True)
    p.add_argument("--action-id", choices=["trade_favors_for_trust", "trade_favors_for_men"],
                   default="trade_favors_for_trust")
    p.add_argument("--actor", default="FRA")
    p.add_argument("--recipient", required=True)
    p.add_argument("--phase", choices=["initiate", "accept", "reject"], default="initiate")
    p.add_argument("--proposal-id")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--expect-unavailable", action="store_true")
    p.add_argument("--expected-reason-text", default="1458")
    args = p.parse_args()
    output = args.output.resolve()
    if args.resume:
        if not (output / "diplomacy.sqlite3").is_file():
            raise ValueError("Resume requires the existing request journal")
    else:
        output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    report = {"status": "running", "session_id": session.session_id,
              "request_id": args.request_id, "actor": args.actor, "recipient": args.recipient,
              "action_id": args.action_id, "phase": args.phase, "resume_only": args.resume,
              "installation": str(args.installation.resolve())}
    _write_json(output / ("resume-report.json" if args.resume else "report.json"), report)
    path = output / "diplomacy.sqlite3"
    try:
        with DurableJournal(path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            if args.resume:
                result = api.get_diplomatic_result(args.request_id)
            else:
                if args.phase != "initiate" and args.proposal_id is None:
                    pending = [row for row in api.list_diplomatic_actions()["incoming_proposals"]
                               if row.get("action_id") == args.action_id
                               and row.get("actor") == args.actor
                               and row.get("recipient") == args.recipient]
                    if len(pending) != 1:
                        raise ValueError("Expected exactly one matching inbound proposal")
                    args.proposal_id = pending[0]["proposal_id"]
                parameters = {"proposal_id": args.proposal_id} if args.phase != "initiate" else {}
                result = api.execute_diplomatic_action(
                    args.request_id, args.action_id, args.actor, args.recipient,
                    args.phase, parameters)
            report["initial"] = result
            deadline = time.monotonic() + 25
            while (result.get("submitted") is True
                   and result.get("game_outcome") not in ("accepted", "rejected")
                   and time.monotonic() < deadline):
                time.sleep(0.15)
                result = api.get_diplomatic_result(args.request_id)
            report["result"] = result
        with DurableJournal(path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            reopened = DiplomacyTools(journal, session).get_diplomatic_result(args.request_id)
        report["checks"] = ({
            "unsubmitted": result.get("submitted") is False,
            "invalidated": result.get("status") == "invalidated",
            "native_rule_reason": any(
                row.get("source") == "native_rule" and args.expected_reason_text in row.get("text", "")
                for row in result.get("result", {}).get("inspection", {}).get(
                    "legality", {}).get("reasons", [])),
            "journal_reopen_equal": result == reopened,
        } if args.expect_unavailable else {
            "submitted": result.get("submitted") is True,
            "actual_response": result.get("game_outcome") in ("accepted", "rejected"),
            "journal_reopen_equal": result == reopened,
        })
        report["status"] = "passed" if all(report["checks"].values()) else "incomplete"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    report["native_slice"] = _copy_bounded_slice(
        log, start, output / ("resume-native.jsonl" if args.resume else "native.jsonl"))
    _write_json(output / ("resume-report.json" if args.resume else "report.json"), report)
    print(json.dumps({key: report.get(key) for key in ("status", "checks", "error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
