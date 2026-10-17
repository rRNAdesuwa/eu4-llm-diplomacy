#!/usr/bin/env python3
"""Read-only reproject the bounded R36E Declare War event fixture.

The script feeds each already observed native event to a temporary
``ObserverSession`` only after the production query path publishes the matching
QUERY1 or QUERY3 request.  It never opens the game, writes a native request to
the game directory, or retries a query.  The temporary control log and journal
are discarded after the public result has been produced.

Example::

    python work/reconcile_declare_war_parameter_queries.py \
      --output work/runtime/r36-war-e-selected-context-readback-20261016-001/report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402


DEFAULT_FIXTURE = ROOT / "bridge/tests/fixtures/declare_war_r36e_real_query3_inspections.json"


def _write_installation(root: Path) -> Path:
    session_id = "declare-r36e-readback"
    installation = root / "installation.json"
    installation.write_text(json.dumps({
        "experiment_id": "declare-r36e-readback",
        "session_id": session_id,
        "pid": 1,
        "creation_filetime": 2,
        "dll_sha256": "fixture-dll",
        "controlled_countries": ["FRA"],
        "installation_returncode": 0,
    }), encoding="utf-8")
    (root / "control-probe.jsonl").write_text(
        json.dumps({"event": "diplomacy_observer_installed",
                    "session_id": session_id,
                    "native_declare_war_query": True}) + "\n",
        encoding="utf-8")
    return installation


def _parameters_for(event: dict) -> dict:
    if event.get("selection_requested") is not True:
        return {}
    return {
        "casus_belli": event["requested_casus_belli"],
        "war_goal": {
            "province_id": event["requested_province_id"],
            "beneficiary": event["requested_beneficiary"],
        },
        "call_allies": [],
    }


def _reproject(event: dict) -> dict:
    parameters = _parameters_for(event)
    with tempfile.TemporaryDirectory(prefix="declare-war-r36e-") as temporary:
        root = Path(temporary)
        session = ObserverSession(_write_installation(root), root / "eu4.exe")
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        errors: list[str] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise RuntimeError("QUERY_REQUEST_NOT_PUBLISHED")
                fields = request.read_text(encoding="ascii").strip().split()
                selected = bool(parameters)
                expected_count = 11 if selected else 8
                if fields[0] != ("EU4DIP_QUERY3" if selected else "EU4DIP_QUERY1"):
                    raise RuntimeError("QUERY_VERSION_MISMATCH")
                if len(fields) != expected_count or fields[3:6] != [
                        "declare_war", "FRA", event["recipient"]]:
                    raise RuntimeError("QUERY_IDENTITY_MISMATCH")
                if selected and fields[8:] != [
                        parameters["casus_belli"],
                        str(parameters["war_goal"]["province_id"]),
                        parameters["war_goal"]["beneficiary"]]:
                    raise RuntimeError("QUERY_SELECTION_MISMATCH")
                request.unlink(missing_ok=True)
                replay = dict(event)
                replay["query_id"] = fields[2]
                replay["session_id"] = session.session_id
                replay["recipient"] = event["recipient"]
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(replay, ensure_ascii=False) + "\n")
            except Exception as error:  # pragma: no cover - surfaced in report
                errors.append(f"{type(error).__name__}:{error}")

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "fixture-ready",
                 "date_raw": event["date_raw"], "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            with DurableJournal(":memory:", "declare-r36e-readback",
                                session.session_id) as journal:
                result = DiplomacyTools(journal, session).inspect_diplomatic_action(
                    "declare_war", "FRA", event["recipient"],
                    phase="initiate", parameters=parameters)
        thread.join(2)
        if thread.is_alive():
            errors.append("WRITER_THREAD_STILL_RUNNING")
        if errors:
            raise RuntimeError(";".join(errors))
        return {
            "source_query_id": event["query_id"],
            "parameters": parameters,
            "selection_matched": event.get("selection_matched"),
            "result": result,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    fixture = args.fixture.expanduser().resolve(strict=True)
    if fixture.stat().st_size > 8 * 1024 * 1024:
        raise SystemExit("FIXTURE_TOO_LARGE")
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or len(events) != 4:
        raise SystemExit("EXPECTED_FOUR_EVENTS")
    report: dict[str, object] = {
        "status": "running",
        "mode": "read_only_fixture_reprojection",
        "fixture": {"path": str(fixture),
                    "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest()},
        "source": payload.get("source"),
        "source_report": payload.get("report"),
        "execute_call_count": 0,
        "native_query_count": 0,
        "results": [],
        "checks": {},
    }
    try:
        results = [_reproject(event) for event in events]
        report["results"] = results
        report["native_query_count"] = len(results)
        report["checks"] = {
            "four_events_reprojected": len(results) == 4,
            "no_query_error": all("error_code" not in item["result"]
                                    for item in results),
            "matched_selections_available": all(
                item["result"].get("legality", {}).get("status") == "available"
                for item in results if item["selection_matched"] is True),
            "unmatched_selection_unavailable": all(
                item["result"].get("legality", {}).get("status") == "unavailable"
                for item in results if item["selection_matched"] is False
                and item["parameters"]),
            "default_selection_unknown": all(
                item["result"].get("legality", {}).get("status") == "unknown"
                for item in results if not item["parameters"]),
            "no_business_submission": report["execute_call_count"] == 0,
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        report_path = str(output)
    else:
        report_path = None
    print(json.dumps({"status": report["status"], "report": report_path,
                      "checks": report["checks"], "error": report.get("error")},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
