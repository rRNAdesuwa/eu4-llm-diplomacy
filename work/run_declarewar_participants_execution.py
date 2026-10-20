"""Execute one combined participant plan and collect its native result."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.declarewar_selection import normalize_participant_selection, country_csv
from work.local_config import game_exe


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pair(session: ObserverSession, recipient: str, output: Path) -> dict:
    env = dict(os.environ, EU4_WAR_PAIR_RECIPIENT=recipient)
    subprocess.run([sys.executable, str(ROOT / "work/probe_war_pair.py"),
                    "--pid", str(session.record["pid"]), "--output", str(output)],
                   env=env, capture_output=True, text=True, timeout=20, check=True)
    return json.loads(output.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--casus-belli", required=True)
    parser.add_argument("--province-id", type=int, required=True)
    parser.add_argument("--beneficiary", required=True)
    parser.add_argument("--call-ally", action="append", default=[])
    parser.add_argument("--promise-land-to", action="append", default=[])
    parser.add_argument("--co-belligerent", action="append", default=[])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selection = normalize_participant_selection({
        "call_allies": args.call_ally, "promise_land_to": args.promise_land_to,
        "co_belligerents": args.co_belligerent}, recipient=args.recipient)
    parameters = {"casus_belli": args.casus_belli,
                  "war_goal": {"province_id": args.province_id, "beneficiary": args.beneficiary},
                  **selection}
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "request_id": args.request_id,
              "parameters": parameters, "actor": "FRA", "recipient": args.recipient,
              "execute_call_count": 0, "automatic_resubmission": False}
    checks = {}
    try:
        report["health_before"] = session.health()
        before = pair(session, args.recipient, output / "before-war-pair.json")
        report["before_war_pair"] = before
        if not before.get("both_pair_at_peace"):
            raise RuntimeError("REQUESTED_PAIR_ALREADY_AT_WAR")
        with DurableJournal(output / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            # execute_diplomatic_action performs the current native inspection.
            # The operator adds no duplicate preflight query.
            report["execute_call_count"] = 1
            result = api.execute_diplomatic_action(args.request_id, "declare_war", "FRA",
                                                   args.recipient, parameters=parameters)
            report["submission"] = result
            deadline = time.monotonic() + 20
            while True:
                result = api.get_diplomatic_result(args.request_id)
                if result.get("status") in {"executed", "rejected", "invalidated", "expired", "conflict"} \
                        or time.monotonic() >= deadline:
                    break
                time.sleep(0.2)
            report["result"] = result
        after = pair(session, args.recipient, output / "after-war-pair.json")
        report["after_war_pair"] = after
        report["health_after"] = session.health()
        public = result.get("result", {})
        checks["public_execution"] = result.get("status") == "executed" and public.get("outcome") == "executed"
        checks["participant_echo"] = all(public.get(field) == values for field, values in selection.items())
        checks["native_execution_proof"] = public.get("execution_verified") is True and public.get("request_binding_verified") is True
        checks["war_transition"] = before["both_pair_at_peace"] is True and all(
            row.get("pair_at_war") is True for row in after["countries"])
        checks["same_paused_date_and_player"] = before["current_raw_date"] == after["current_raw_date"] \
            and before["player_slot"] == after["player_slot"] == 189
        with DurableJournal(output / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            reopened = DiplomacyTools(journal, session).get_diplomatic_result(args.request_id)
            report["reopened_result"] = reopened
            checks["journal_result"] = reopened.get("result") == result.get("result") and reopened.get("status") == result.get("status")
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        end = log.stat().st_size
        if 0 <= end - start <= 16 * 1024 * 1024:
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(end - start)
            (output / "native-events-slice.jsonl").write_bytes(raw)
            events = []
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("request_id") == args.request_id and event.get("session_id") == session.session_id:
                    events.append(event)
            report["native_events"] = events
            for event_name in ("native_declare_war_submission_result", "native_declare_war_execution_result"):
                bound = [event for event in events if event.get("event") == event_name]
                checks[event_name] = len(bound) == 1 and all(
                    bound[0].get(field + "_csv") == country_csv(tags)
                    for field, tags in selection.items())
        report["checks"] = checks
        report["status"] = "passed" if checks and all(checks.values()) and "error" not in report else "failed"
        write(output / "report.json", report)
    print(json.dumps({"status": report["status"], "failed": [key for key, value in checks.items() if not value],
                      "error": report.get("error"), "report": str(output / "report.json")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
