"""Read an existing peace request after a consumer fix, without submitting it again."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work import run_peace_outbound_execution as outbound


def _matching_execution_event(event_path: Path, request_id: str,
                              session_id: str) -> tuple[dict[str, object], bytes]:
    """Read exactly one bound native execution event from the bounded slice."""

    matches: list[tuple[dict[str, object], bytes]] = []
    with event_path.open("rb") as stream:
        for raw in stream:
            if len(raw) > 64 * 1024:
                continue
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, ValueError):
                continue
            if (isinstance(event, dict)
                    and event.get("event") == "native_peace_execution_result"
                    and event.get("request_id") == request_id
                    and event.get("session_id") == session_id):
                matches.append((event, raw))
                if len(matches) > 1:
                    break
    if len(matches) != 1:
        raise SystemExit("NATIVE_EXECUTION_EVENT_NOT_UNIQUE")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--recipient", type=outbound._recipient_arg, default=None,
        help="议和目标国；缺省从 source report 读取，FRA 为固定 actor")
    args = parser.parse_args()
    source = args.source_report.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    source_bytes = source.read_bytes()
    report = json.loads(source_bytes)
    native = report["native_events"]
    event_path = Path(native["path"])
    if event_path.stat().st_size > 4 * 1024 * 1024:
        raise SystemExit("SOURCE_EVENT_SLICE_TOO_LARGE")
    if hashlib.sha256(event_path.read_bytes()).hexdigest() != native["sha256"]:
        raise SystemExit("SOURCE_EVENT_SLICE_HASH_MISMATCH")
    source_recipient = report.get("recipient")
    recipient = args.recipient if args.recipient is not None else source_recipient
    if (not isinstance(recipient, str)
            or outbound._recipient_arg(recipient) != recipient
            or source_recipient != recipient
            or report.get("actor") != outbound._ACTOR):
        raise SystemExit("SOURCE_RECIPIENT_MISMATCH")
    session_record = report.get("session")
    session_id = session_record.get("session_id") \
        if isinstance(session_record, dict) else None
    if not isinstance(session_id, str):
        raise SystemExit("SOURCE_SESSION_MISSING")
    execution_event, execution_raw = _matching_execution_event(
        event_path, report["request_id"], session_id)
    evidence = output.parent / (output.stem + "-evidence")
    evidence.mkdir(parents=True, exist_ok=False)
    source_journal = event_path.parent / "diplomacy.sqlite3"
    journal_path = evidence / "diplomacy.sqlite3"
    shutil.copy2(source_journal, journal_path)
    installation = report["installation"]
    installation_path = Path(installation["path"])
    if hashlib.sha256(installation_path.read_bytes()).hexdigest() != installation["sha256"]:
        raise SystemExit("SOURCE_INSTALLATION_HASH_MISMATCH")
    # Rebuild a private, read-only observer directory from the source
    # installation and the exact matching event.  The source game process is
    # never contacted; this makes the late-event recovery deterministic even
    # after the original process has exited.
    with tempfile.TemporaryDirectory(prefix="peace-reconcile-") as temporary:
        replay_root = Path(temporary)
        replay_installation = replay_root / "installation.json"
        shutil.copy2(installation_path, replay_installation)
        (replay_root / "control-probe.jsonl").write_bytes(execution_raw)
        session = ObserverSession(replay_installation, replay_root / "eu4.exe")
        if session.session_id != session_id:
            raise SystemExit("SOURCE_SESSION_MISMATCH")
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            result = DiplomacyTools(journal, session).get_diplomatic_result(
                report["request_id"])
    # The runner's expected native fields use a process-global recipient for
    # historical ENG compatibility.  Bind it to the immutable source report
    # before constructing the contract, so LEI (or another canonical target)
    # cannot be compared against an ENG slot.
    outbound._RECIPIENT = recipient
    contract = outbound._result_contract(
        result, report["action_id"], report["parameters"]["execute"],
        report["expected_date_raw"], report["before"]["war_state"],
        report["after"]["war_state"])
    public = outbound._public_result(result)
    outcome = public.get("outcome") if isinstance(public, dict) else None
    report["reconciliation"] = {
        "source_report": str(source),
        "source_report_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_native_events": str(event_path),
        "source_native_events_sha256": native["sha256"],
        "source_execution_event_sha256": hashlib.sha256(execution_raw).hexdigest(),
        "source_execution_event_status": execution_event.get("outcome"),
        "journal_copy": str(journal_path),
        "replay_installation_isolated": True,
        "method": "DiplomacyTools.get_diplomatic_result",
        "execute_call_count": 0,
        "game_control_call_count": 0,
        "source_report_preserved": True,
    }
    report["original_poll"] = report.get("poll")
    report["poll"] = {"calls": 1, "terminal": result.get("status") in
                      ("accepted", "rejected", "executed", "failed", "invalidated"),
                      "final": result}
    report["result"] = result
    report["result_contract"] = contract
    report["native_effects"] = contract.get("native_effects")
    report["effects_contract"] = contract.get("effects_contract")
    report["checks"]["native_result_contract"] = contract.get("all") is True
    report["checks"]["after_war_matches_native_result"] = (
        outcome in ("executed", "accepted", "rejected")
        and contract.get("checks", {}).get("war_transition") is True)
    report["status"] = "passed" if all(report["checks"].values()) else "failed"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "result_status": result.get("status"),
                      "execute_call_count": 0, "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
