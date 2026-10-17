"""Run one bounded operator alliance execution experiment.

The script assumes an already installed observer and an already paused POR
baseline.  It never starts the game, advances the date, saves, tags, or
installs a module.  One request is published through the bridge; a timeout or
failure is recorded and is never replayed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import get_value
from work.observer_runtime_ready import wait_runtime_ready
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


_HASH_CHUNK_BYTES = 64 * 1024
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_LOG_SLICE_CHUNK_BYTES = 64 * 1024
_MAX_LOG_SLICE_BYTES = 8 * 1024 * 1024
_POLL_SECONDS = 20.0


class ExperimentStop(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _sha256_file(path: Path, *, maximum: int = _MAX_METADATA_BYTES) -> dict:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ExperimentStop("METADATA_TOO_LARGE", str(path))
            digest.update(chunk)
    return {"path": str(path), "bytes": total, "sha256": digest.hexdigest()}


def _compact_probe(raw: dict, destination: Path) -> dict:
    """Keep the snapshot file as the full record and the report bounded."""

    return {
        "status": raw.get("status"),
        "name": raw.get("name"),
        "script": str(raw.get("script")) if raw.get("script") is not None else None,
        "snapshot_path": str(destination),
        "snapshot_completeness": raw.get("snapshot_completeness"),
        "snapshot_sha256": _sha256_file(destination),
    }


def _run_probes(pid: int, destination: Path) -> tuple[dict, dict | None]:
    reports: dict[str, dict] = {}
    control: dict | None = None
    for spec in PROBE_SPECS:
        path = destination / (spec.name + ".json")
        try:
            raw = _run_probe(spec, pid, path)
            snapshot = raw.get("snapshot")
            if spec.name == "control_state" and isinstance(snapshot, dict):
                control = {
                    "date_raw": snapshot.get("date_raw"),
                    "player_slot": snapshot.get("player_slot"),
                    "paused_flag": snapshot.get("paused_flag"),
                }
            reports[spec.name] = _compact_probe(raw, path)
        except Exception as error:
            reports[spec.name] = {
                "status": "unknown", "snapshot_path": str(path),
                "error_type": type(error).__name__, "error": str(error),
            }
    return reports, control


def _query_pair(api: DiplomacyTools, recipient: str, destination: Path) -> dict:
    result: dict[str, dict] = {}
    for action_id in ("offer_alliance", "dissolve_alliance"):
        try:
            inspected = api.inspect_diplomatic_action(
                action_id, "FRA", recipient, phase="initiate")
            result[action_id] = inspected if isinstance(inspected, dict) else {
                "status": "unknown", "error": "INSPECTION_NOT_OBJECT",
            }
        except Exception as error:
            result[action_id] = {
                "status": "unknown", "error_type": type(error).__name__,
                "error": str(error),
            }
    _write_json(destination, result)
    return result


def _dissolve_selector_check(inspection: object, outcome: str | None) -> dict:
    """Use the reviewed Dissolve visibility selector as alliance membership."""

    visibility = inspection.get("visibility") if isinstance(inspection, dict) else None
    status = visibility.get("status") if isinstance(visibility, dict) else None
    complete = isinstance(visibility, dict) and visibility.get("complete") is True
    coverage = inspection.get("rule_coverage") if isinstance(inspection, dict) else None
    if not isinstance(coverage, dict) and isinstance(inspection, dict):
        coverage = inspection.get("native_rule_components")
    ui_selection = coverage.get("ui_action_selection") if isinstance(coverage, dict) else None
    expected_status = (
        "visible" if outcome == "accepted" else "hidden"
        if outcome == "rejected" else None
    )
    visible_after = status == "visible" if status in ("visible", "hidden") else None
    return {
        "observed": status in ("visible", "hidden"),
        "visibility_status": status,
        "visibility_complete": complete,
        "ui_action_selection": ui_selection,
        "ui_action_selection_bool": isinstance(ui_selection, bool),
        "alliance_after": visible_after,
        "visible_after": visible_after,
        "outcome_reference": outcome,
        "expected_visibility_status": expected_status,
        "consistent": (complete and expected_status is not None
                       and status == expected_status
                       and isinstance(ui_selection, bool)
                       and ui_selection == (status == "visible")),
    }


def _poll_result(api: DiplomacyTools, request_id: str) -> dict:
    deadline = time.monotonic() + _POLL_SECONDS
    calls = 0
    status_history: list[str] = []
    final: dict | None = None
    while time.monotonic() < deadline:
        final = api.get_diplomatic_result(request_id)
        calls += 1
        status = final.get("status") if isinstance(final, dict) else None
        if isinstance(status, str) and (not status_history or status_history[-1] != status):
            status_history.append(status)
        if status in ("accepted", "rejected"):
            break
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    return {
        "calls": calls,
        "status_history": status_history,
        "terminal": isinstance(final, dict)
        and final.get("status") in ("accepted", "rejected"),
        "final": final,
    }


def _copy_log_slice(log: Path, start: int, destination: Path) -> dict:
    digest = hashlib.sha256()
    copied = 0
    try:
        with log.open("rb") as source, destination.open("xb") as evidence:
            source.seek(0, 2)
            initial_size = source.tell()
            if initial_size < start:
                return {"status": "unknown", "reason": "LOG_TRUNCATED", "start_offset": start}
            source.seek(start)
            while copied < _MAX_LOG_SLICE_BYTES:
                chunk = source.read(min(_LOG_SLICE_CHUNK_BYTES,
                                        _MAX_LOG_SLICE_BYTES - copied))
                if not chunk:
                    break
                evidence.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
            source.seek(0, 2)
            end_size = source.tell()
    except OSError as error:
        return {"status": "unknown", "reason": "LOG_SLICE_FAILED", "error": str(error)}
    return {
        "status": "ok", "path": str(destination), "start_offset": start,
        "end_offset": start + copied, "bytes": copied,
        "bounded": copied >= _MAX_LOG_SLICE_BYTES,
        "complete": end_size <= start + copied,
        "sha256": digest.hexdigest(),
    }


def _stable_result(result: object) -> dict:
    if not isinstance(result, dict):
        return {"status": None, "submitted": False, "game_outcome": "unknown", "result": None}
    return {
        "status": result.get("status"),
        "submitted": result.get("submitted"),
        "game_outcome": result.get("game_outcome"),
        "result": result.get("result"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--recipient", choices=("SAV", "LIT"), required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--expected-outcome", choices=("accepted", "rejected"), required=True)
    args = parser.parse_args()

    installation = args.installation.expanduser().resolve()
    artifact = installation.parent / ("alliance-execution-" + uuid.uuid4().hex)
    artifact.mkdir(parents=True)
    report: dict = {
        "status": "unknown", "request_id": args.request_id,
        "recipient": args.recipient, "expected_outcome": args.expected_outcome,
        "installation": None, "manifest": None, "observations": {},
        "checks": {}, "artifact": str(artifact),
    }
    log_start: int | None = None
    log_path = installation.parent / "control-probe.jsonl"
    journal_path = artifact / "diplomacy.sqlite3"

    try:
        report["installation"] = _sha256_file(installation)
        manifest = installation.parent / "build-manifest.json"
        report["manifest"] = _sha256_file(manifest)
        record = json.loads(installation.read_text(encoding="utf-8"))
        report["installation"]["declared_dll_sha256"] = record.get("dll_sha256")

        game_root = Path(get_value("EU4_GAME_ROOT"))
        session = ObserverSession(installation, game_root / "eu4.exe")
        report["session_id"] = session.session_id
        report["experiment_id"] = session.experiment_id
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start

        health = wait_runtime_ready(session, restore_minimized=True)
        capabilities = sorted(session.installation_capabilities())
        report["preflight"] = {"health": health, "capabilities": capabilities}
        if health.get("status") != "ready":
            raise ExperimentStop("SESSION_NOT_READY", json.dumps(health, ensure_ascii=False))

        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            before_probes, control = _run_probes(int(session.record["pid"]), artifact / "before" / "probes")
            before_queries = _query_pair(api, args.recipient, artifact / "before" / "queries.json")
            before_date = control.get("date_raw") if isinstance(control, dict) else None
            baseline = {
                "health_ready": health.get("status") == "ready",
                "player_slot_is_por": isinstance(control, dict) and control.get("player_slot") == 189,
                "paused": isinstance(control, dict) and control.get("paused_flag") == 1,
                "date_present": isinstance(before_date, int) and not isinstance(before_date, bool),
                "health_date_matches_probe": health.get("date_raw") == before_date,
                "probe_snapshots_complete": bool(before_probes)
                and all(item.get("snapshot_completeness", {}).get("complete") is True
                        for item in before_probes.values()),
            }
            report["before"] = {
                "queries": before_queries, "probes": before_probes,
                "control": control, "baseline": baseline,
            }
            if not all(baseline.values()):
                raise ExperimentStop("BASELINE_NOT_READY_POR_PAUSED", json.dumps(baseline, ensure_ascii=False))
            if "native_offer_submission" not in capabilities:
                raise ExperimentStop("NATIVE_OFFER_SUBMISSION_CAPABILITY_MISSING", "installation ack")

            execution = api.execute_diplomatic_action(
                args.request_id, "offer_alliance", "FRA", args.recipient)
            report["observations"]["submission"] = {
                "observed": execution.get("submitted") is True,
                "status": execution.get("status"),
                "business_outcome": False,
            }
            report["execution"] = execution
            if execution.get("submitted") is True:
                poll = _poll_result(api, args.request_id)
            else:
                poll = {"calls": 1, "status_history": [], "terminal": False,
                        "final": api.get_diplomatic_result(args.request_id)}
            final_result = poll.get("final")
            report["poll"] = {
                "calls": poll["calls"], "status_history": poll["status_history"],
                "terminal": poll["terminal"], "final": final_result,
            }
            report["observations"]["response"] = {
                "observed": isinstance(final_result, dict)
                and final_result.get("status") in ("accepted", "rejected"),
                "status": final_result.get("status") if isinstance(final_result, dict) else None,
                "business_outcome": True,
            }

            after_probes, after_control = _run_probes(int(session.record["pid"]), artifact / "after" / "probes")
            after_queries = _query_pair(api, args.recipient, artifact / "after" / "queries.json")
            after_health = session.health()
            after_date = after_control.get("date_raw") if isinstance(after_control, dict) else None
            after_baseline = {
                "health_ready": after_health.get("status") == "ready",
                "health_date_same": after_health.get("date_raw") == before_date,
                "player_slot_is_por": isinstance(after_control, dict)
                and after_control.get("player_slot") == 189,
                "paused": isinstance(after_control, dict)
                and after_control.get("paused_flag") == 1,
                "date_same": after_date == before_date,
                "probe_snapshots_complete": bool(after_probes)
                and all(item.get("snapshot_completeness", {}).get("complete") is True
                        for item in after_probes.values()),
            }
            report["after"] = {
                "queries": after_queries, "probes": after_probes,
                "control": after_control, "health": after_health,
                "baseline": after_baseline,
            }
            observed_outcome = (
                final_result.get("game_outcome")
                if isinstance(final_result, dict)
                and final_result.get("game_outcome") in ("accepted", "rejected")
                else None
            )
            expected_selector = _dissolve_selector_check(
                after_queries.get("dissolve_alliance"), observed_outcome)
            report["observations"]["postcondition"] = {
                "observed": bool(after_queries),
                "dissolve_selector": expected_selector,
            }

            stable = _stable_result(final_result)

        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(args.request_id)
        report["reopened_result"] = reopened_result
        reopened_stable = _stable_result(reopened_result)
        report["observations"]["persistence"] = {
            "observed": stable == reopened_stable,
            "same_result": stable == reopened_stable,
        }

        final = report["poll"].get("final")
        selector = report["observations"]["postcondition"]["dissolve_selector"]
        report["checks"] = {
            "submitted_true": report["observations"]["submission"]["observed"],
            "expected_outcome_observed": isinstance(final, dict)
            and final.get("status") == args.expected_outcome
            and final.get("game_outcome") == args.expected_outcome,
            "dissolve_selector_alliance_after_consistent": selector.get("consistent") is True,
            "after_baseline_unchanged": all(report["after"]["baseline"].values()),
            "reopened_same_result": report["observations"]["persistence"]["same_result"],
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_OPERATOR_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl")
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
