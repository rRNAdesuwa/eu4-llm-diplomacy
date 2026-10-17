"""Observe one reviewed 35-day test advance; never submit diplomacy.

Operator-only CLI. Uses the existing fixed native controller in the exact
observer session. Each run preserves snapshots and an independent log slice.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import ObserverSession
from bridge.diplomacy_session import file_hash
from work.local_config import get_value
from work.observer_runtime_ready import wait_runtime_ready
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--days", type=int, choices=(1, 5, 35), default=35)
    args = parser.parse_args()
    installation = args.installation.resolve()
    session = ObserverSession(installation, Path(get_value("EU4_GAME_ROOT")) / "eu4.exe")
    directory = installation.parent / ("lifecycle-observation-" + uuid.uuid4().hex)
    directory.mkdir()
    ack = session._installation_ack() or {}
    report = {"session_id": session.session_id, "business_submission": False,
              "authority_enabled": ack.get("authority_lock_enabled") is True,
              "authority_scope": ack.get("authority_scope"), "own_diplomatic_request": False,
              "status": "unknown", "installation": str(installation)}
    published = False
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready" or health.get("date_raw") != args.expected_date_raw:
            raise RuntimeError("OBSERVER_NOT_READY_AT_EXPECTED_DATE")
        before = {spec.name: _run_probe(spec, session.record["pid"],
                  directory / "before" / (spec.name + ".json")) for spec in PROBE_SPECS}
        control = before["control_state"]["snapshot"]
        if (control.get("date_raw") != args.expected_date_raw or control.get("paused_flag") != 1
                or control.get("player_slot") != 189
                or not all(p["snapshot_completeness"]["complete"] for p in before.values())):
            raise RuntimeError("BASELINE_NOT_COMPLETE_PAUSED_POR")
        save(directory / "before.json", before)
        log = installation.parent / "control-probe.jsonl"
        offset = log.stat().st_size
        report["log_start_offset"] = offset
        pending = installation.parent / ("control-pending-" + uuid.uuid4().hex)
        request = installation.parent / "game-control.request"
        try:
            with pending.open("xb") as stream:
                stream.write(f"TEST_ONLY advance_{args.days}_days\n".encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
            if session.health().get("status") != "ready":
                raise RuntimeError("SESSION_CHANGED_BEFORE_PUBLICATION")
            os.link(pending, request)
            published = True
        finally:
            pending.unlink(missing_ok=True)
        report["fixed_control_request_published"] = True
        print(json.dumps({"state": "observing", "output": str(directory)}), flush=True)
        completion = None
        deadline = time.monotonic() + 145
        with log.open("rb") as source, (directory / "observed-events.jsonl").open("xb") as evidence:
            source.seek(offset)
            while time.monotonic() < deadline and completion is None:
                while True:
                    position = source.tell()
                    raw = source.readline(16385)
                    if not raw or not raw.endswith(b"\n"):
                        source.seek(position)
                        break
                    if len(raw) > 16384:
                        raise RuntimeError("NATIVE_EVENT_EXCEEDS_BOUNDED_LINE")
                    evidence.write(raw)
                    event = json.loads(raw)
                    if event.get("event") == "control_advance_complete":
                        completion = event
                evidence.flush()
                if completion is None:
                    time.sleep(1)
            report["log_end_offset"] = source.tell()
        report["completion"] = completion
        if completion is None:
            raise RuntimeError("ADVANCE_COMPLETION_UNOBSERVED")
        after = {spec.name: _run_probe(spec, session.record["pid"],
                 directory / "after" / (spec.name + ".json")) for spec in PROBE_SPECS}
        save(directory / "after.json", after)
        after_control = after["control_state"]["snapshot"]
        # A completed date advance may precede the second paused heartbeat.
        # Wait for that existing session instead of classifying a healthy
        # exact-date completion from a single immediate health sample.
        report["health_after"] = wait_runtime_ready(session)
        report["paused_after"] = after_control.get("paused_flag") == 1
        report["date_raw_after"] = after_control.get("date_raw")
        report["target_date_raw"] = args.expected_date_raw + args.days * 24
        report["status"] = "observed" if (completion.get("reached") is True
            and completion.get("paused_command_success") is True and report["paused_after"]
            and report["date_raw_after"] == report["target_date_raw"]
            and report["health_after"].get("status") == "ready") else "incomplete"
        report["events_sha256"] = file_hash(directory / "observed-events.jsonl")
    except Exception as error:
        report["error"] = str(error)
        report["fixed_control_request_published"] = published
    finally:
        save(directory / "observation-report.json", report)
    print(json.dumps({"status": report["status"], "output": str(directory)}), flush=True)
    return 0 if report["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
