"""Validate Build Spy Network state in an already reloaded process.

This validator is read-only.  It checks the four observer snapshots, the
selector-13176 task record, native start/stop query legality, optional save
binding, and an optional prior after-state.  It never publishes an execution
request or controls the game.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import _write_json  # noqa: E402
from work.run_improve_relations_execution import (  # noqa: E402
    _diplomat_evidence,
    _new_artifact,
    _query_improve_pair,
    _query_task_transition,
    _task_observation,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _hash_file,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189
_ACTIONS = ("build_spy_network", "stop_building_spy_network")
_SPY_SELECTOR = 13176
_SPY_FAMILY = "spy_network"
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024


class ReloadValidationError(RuntimeError):
    """An expected read-only validation stop."""


def _query_spy_pair(api: DiplomacyTools, recipient: str,
                    destination: Path) -> dict[str, dict[str, object]]:
    return _query_improve_pair(api, recipient, destination, _ACTIONS)


def _task_evidence(snapshot: object, recipient: str) -> dict[str, object]:
    return _task_observation(
        snapshot, _ACTOR, recipient, _SPY_SELECTOR, _SPY_FAMILY
    )


def _task_projection(task: object) -> list[dict[str, object]]:
    if not isinstance(task, dict):
        return []
    matched = task.get("matched_entries")
    if not isinstance(matched, list):
        return []
    projection: list[dict[str, object]] = []
    for item in matched:
        if not isinstance(item, dict) or not isinstance(item.get("entry"), dict):
            continue
        entry = item["entry"]
        projection.append({
            "countrytag": item.get("countrytag"),
            "active": item.get("active"),
            "record_present": item.get("record_present"),
            "raw_action_type_a8": entry.get("raw_action_type_a8"),
            "raw_20": entry.get("raw_20"),
            "raw_24": entry.get("raw_24"),
            "raw_2c": entry.get("raw_2c"),
        })
    projection.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    return projection


def _task_shape(task: object, expected_task: bool) -> dict[str, object]:
    if not isinstance(task, dict):
        return {
            "evidence_complete": False, "expected_state": False,
            "active_entry_identity": False, "selector": None,
            "family": None, "matched_count": 0, "active_count": 0,
            "projection": [],
        }
    matched = task.get("matched_entries")
    matched_items = matched if isinstance(matched, list) else []
    active_items = [
        item for item in matched_items
        if isinstance(item, dict) and item.get("active") is True
    ]
    active_identity = any(
        isinstance(item, dict)
        and isinstance(item.get("entry"), dict)
        and item["entry"].get("raw_action_type_a8") == _SPY_SELECTOR
        and item.get("record_present") is True
        for item in active_items
    )
    return {
        "evidence_complete": task.get("evidence_complete") is True,
        "expected_state": task.get("task") is expected_task,
        "active_entry_identity": active_identity if expected_task else not active_items,
        "selector": task.get("selector"),
        "family": task.get("family", _SPY_FAMILY),
        "matched_count": len(matched_items), "active_count": len(active_items),
        "projection": _task_projection(task),
    }


def _is_snapshot(value: object, kind: str) -> bool:
    if not isinstance(value, dict):
        return False
    if kind == "diplomats":
        return isinstance(value.get("countries"), list)
    return "date_raw" in value and "player_slot" in value


def _extract_snapshot(value: object, kind: str, depth: int = 0) -> dict[str, object] | None:
    if depth > 6 or not isinstance(value, dict):
        return None
    if _is_snapshot(value, kind):
        return value
    keys = (
        ("snapshot", "diplomats_snapshot", "diplomat_snapshot")
        if kind == "diplomats" else
        ("snapshot", "control_snapshot", "control_state_snapshot")
    )
    for key in keys:
        found = _extract_snapshot(value.get(key), kind, depth + 1)
        if found is not None:
            return found
    for key in ("after", "observations", "result", "before"):
        found = _extract_snapshot(value.get(key), kind, depth + 1)
        if found is not None:
            return found
    return None


def _extract_task_record(value: object, depth: int = 0) -> dict[str, object] | None:
    if depth > 6 or not isinstance(value, dict):
        return None
    task = value.get("task")
    if isinstance(task, dict) and ("evidence_complete" in task or "matched_entries" in task):
        return task
    for key in ("after", "observations", "result", "before"):
        found = _extract_task_record(value.get(key), depth + 1)
        if found is not None:
            return found
    return None


def _reference_checks(reference: Path, current_task: object,
                      current_control: dict[str, object], recipient: str,
                      expected_task: bool) -> dict[str, object]:
    reference = reference.expanduser().resolve(strict=True)
    candidates = [reference] if reference.is_file() else [
        reference / "report.json",
        reference / "after" / "probes" / "diplomats.json",
        reference / "after" / "probes" / "control_state.json",
    ]
    payloads: list[tuple[Path, object]] = []
    for path in candidates:
        if path.is_file():
            payloads.append((path, _read_json(path, maximum=_MAX_METADATA_BYTES)))
    if not payloads:
        raise ReloadValidationError(f"REFERENCE_ARTIFACT_NO_METADATA:{reference}")
    diplomat_snapshot = None
    control_snapshot = None
    for _, payload in payloads:
        if diplomat_snapshot is None:
            diplomat_snapshot = _extract_snapshot(payload, "diplomats")
        if control_snapshot is None:
            control_snapshot = _extract_snapshot(payload, "control")
    reference_task = (
        _task_evidence(diplomat_snapshot, recipient)
        if diplomat_snapshot is not None else None
    )
    if reference_task is None:
        reference_task = next(
            (_extract_task_record(payload) for _, payload in payloads), None
        )
    current_shape = _task_shape(current_task, expected_task)
    reference_shape = _task_shape(reference_task, expected_task)
    current_projection = _task_projection(current_task)
    reference_projection = _task_projection(reference_task)
    if control_snapshot is not None:
        reference_control = _control_summary(control_snapshot)
        control_matches = all(
            current_control.get(key) == reference_control.get(key)
            for key in ("date_raw", "player_slot", "paused_flag")
        )
    else:
        reference_control = None
        control_matches = True
    checks = {
        "reference_task_shape": (
            reference_shape["evidence_complete"] is True
            and reference_shape["expected_state"] is True
            and reference_shape["active_entry_identity"] is True
            and reference_shape["selector"] == _SPY_SELECTOR
        ),
        "reference_task_state_matches": (
            isinstance(reference_task, dict)
            and isinstance(current_task, dict)
            and current_task.get("task") == reference_task.get("task")
        ),
        "reference_task_projection_matches": current_projection == reference_projection,
        "reference_control_matches": control_matches,
    }
    return {
        "provided": True, "path": str(reference),
        "source_paths": [str(path) for path, _ in payloads],
        "task": reference_task, "task_shape": reference_shape,
        "control": reference_control, "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--expected-task", choices=("active", "absent"), required=True)
    parser.add_argument("--save-path", type=Path)
    parser.add_argument("--reference-artifact", type=Path)
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "spy-network-reload")
    expected_task = args.expected_task == "active"
    report: dict[str, object] = {
        "validator": "validate_spy_network_reload.py",
        "status": "running", "mode": "read_only_reload_validation",
        "installation": str(installation), "actor": _ACTOR,
        "recipient": args.recipient, "family": _SPY_FAMILY,
        "selector": _SPY_SELECTOR, "actions": list(_ACTIONS),
        "expected_date_raw": args.expected_date_raw,
        "expected_task": args.expected_task,
        "save_path": str(args.save_path.expanduser().resolve()) if args.save_path else None,
        "reference_artifact": str(args.reference_artifact.expanduser().resolve())
        if args.reference_artifact else None,
        "artifact": str(artifact), "execute_call_count": 0,
        "execution_requested": False, "business_submission": False, "checks": {},
    }
    try:
        if not _TAG_RE.fullmatch(args.recipient):
            raise ReloadValidationError("RECIPIENT_TAG_INVALID")
        report.update(_installation_binding(installation))
        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable), "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
        session = ObserverSession(installation, executable)
        report["session"] = {
            "experiment_id": session.experiment_id, "session_id": session.session_id,
            "pid": session.record.get("pid"), "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health_before = wait_runtime_ready(session, restore_minimized=False)
        if health_before.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "after" / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        diplomat_snapshot = probes["diplomats"]["snapshot"]
        semantics = _diplomat_semantics(diplomat_snapshot)
        diplomat = _diplomat_evidence(
            probes, args.recipient, selector=_SPY_SELECTOR, family=_SPY_FAMILY
        )
        task = diplomat.get("task")
        task_shape = _task_shape(task, expected_task)
        health_after = session.health()
        report["after"] = {
            "health_before": health_before, "health_after": health_after,
            "control": control, "diplomat_semantics": semantics,
            "task": task, "task_shape": task_shape,
            "probe_files": {
                name: {
                    "status": item.get("status"), "snapshot_path": item.get("snapshot_path"),
                    "snapshot_completeness": item.get("snapshot_completeness"),
                    "snapshot_sha256": item.get("snapshot_sha256"),
                } for name, item in probes.items()
            },
            "snapshot_complete": _snapshots_complete(probes),
        }
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            queries = _query_spy_pair(api, args.recipient, artifact / "after" / "queries.json")
        report["queries"] = queries
        if args.save_path is not None:
            save_path = args.save_path.expanduser().resolve(strict=True)
            save = _hash_file(save_path, maximum=_MAX_SAVE_BYTES)
            save["provided"] = True
            report["save"] = save
        else:
            report["save"] = {"provided": False, "sha256": None}
        if args.reference_artifact is not None:
            report["reference"] = _reference_checks(
                args.reference_artifact, task, control, args.recipient, expected_task
            )
        else:
            report["reference"] = {"provided": False, "checks": {}}

        build_binding = report.get("build_binding")
        build_bound = (
            isinstance(build_binding, dict)
            and build_binding.get("installation_matches_build_manifest") is True
            and build_binding.get("loaded_dll_sha256") == build_binding.get("installation_dll_sha256")
        )
        query_complete = True
        for action in _ACTIONS:
            inspection = queries.get(action)
            legality = inspection.get("legality") if isinstance(inspection, dict) else None
            query_complete = query_complete and (
                isinstance(inspection, dict)
                and inspection.get("action_id") == action
                and isinstance(legality, dict)
                and legality.get("complete") is True
            )
        checks: dict[str, bool] = {
            "new_process_ready": (
                health_before.get("status") == "ready"
                and health_before.get("complete") is True
                and health_after.get("status") == "ready"
                and health_after.get("complete") is True
            ),
            "player_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "date_matches_expected": (
                control.get("date_raw") == args.expected_date_raw
                and health_after.get("date_raw") == args.expected_date_raw
            ),
            "four_snapshots_complete": _snapshots_complete(probes),
            "diplomat_snapshot_complete": (
                isinstance(probes["diplomats"].get("snapshot_completeness"), dict)
                and probes["diplomats"]["snapshot_completeness"].get("complete") is True
            ),
            "diplomat_semantics_complete": isinstance(semantics, list),
            "task_evidence_complete": task_shape["evidence_complete"],
            "task_state_expected": task_shape["expected_state"],
            "active_task_identity": task_shape["active_entry_identity"],
            "task_selector_13176": task_shape["selector"] == _SPY_SELECTOR,
            "task_family_spy_network": task_shape["family"] == _SPY_FAMILY,
            "query_pair_complete": query_complete,
            "query_task_legality_transition": _query_task_transition(
                queries, expected_task, _ACTIONS
            ),
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "source_build_session_bound": build_bound,
            "save_hash_bound": (
                report["save"].get("provided") is not True
                or isinstance(report["save"].get("sha256"), str)
            ),
        }
        reference = report.get("reference")
        if isinstance(reference, dict) and reference.get("provided") is True:
            reference_checks = reference.get("checks")
            if isinstance(reference_checks, dict):
                checks.update({key: value is True for key, value in reference_checks.items()})
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
