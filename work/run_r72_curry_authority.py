"""Exercise two fixed, ungranted Curry stop routes in the test scene."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from work.local_config import game_exe
from work.run_peace_consequence_queries import _copy_bounded_slice, _write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    api = DiplomacyTools(None, session)
    log = session.directory / "control-probe.jsonl"
    request = session.directory / "diplomacy-authority-test.req"
    start = log.stat().st_size
    report = {"status": "running", "session_id": session.session_id, "cases": []}
    try:
        for suffix in ("WITHOUT_AUTHORITY", "DIRECT_WITHOUT_AUTHORITY"):
            before = api.inspect_diplomatic_action("stop_curry_favors", "FRA", "SAV")
            if before.get("task_active") is not True or before["legality"]["status"] != "available":
                raise ValueError("SAV must have a legally stoppable Curry task")
            if request.exists():
                raise ValueError("An operator request already exists")
            offset = log.stat().st_size
            temporary = request.with_suffix(".r72-tmp")
            with temporary.open("xb") as stream:
                stream.write(f"TEST_ONLY FRA_STOP_CURRY_SAV_{suffix}\n".encode("ascii"))
            os.replace(temporary, request)
            deadline = time.monotonic() + 5
            events = []
            while time.monotonic() < deadline:
                with log.open("rb") as stream:
                    stream.seek(offset)
                    lines = stream.read(128 * 1024).splitlines()
                events = []
                for line in lines:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("session_id") == session.session_id:
                        events.append(event)
                if any(event.get("event") == "native_alliance_authority_test_dispatched"
                       for event in events):
                    break
                time.sleep(0.1)
            after = api.inspect_diplomatic_action("stop_curry_favors", "FRA", "SAV")
            checks = {
                "ungranted_attempt_observed": any(
                    event.get("event") == "native_alliance_authority_test_dispatched"
                    and event.get("authority_seed_created") is False
                    for event in events),
                "authority_denial_observed": any(
                    "UNAUTHORIZED_FRA_CURRY_FAVORS_TASK" in json.dumps(event)
                    for event in events),
                "task_still_active": after.get("task_active") is True,
            }
            report["cases"].append({"token": suffix, "before": before, "after": after,
                                    "events": events, "checks": checks})
            if not all(checks.values()):
                raise ValueError("The ungranted route was not conclusively rejected")
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    report["native_slice"] = _copy_bounded_slice(log, start, args.output / "native.jsonl")
    _write_json(args.output / "report.json", report)
    print(json.dumps({"status": report["status"], "cases": [row["checks"] for row in report["cases"]],
                      "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
