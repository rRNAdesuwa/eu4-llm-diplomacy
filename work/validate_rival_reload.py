"""Read-only Rival validation after loading a saved game in a new process.

The source report supplies the recipients, date, relation state, and build
provenance.  This validator starts no process and emits no control, save, or
execution request.  It takes one bounded four-snapshot boundary, inspects
``set_rival`` and ``remove_rival`` for every source recipient, and compares
the relation fields independently from the action-legality result.
"""
from __future__ import annotations

import argparse
import json
import os
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
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _write_json,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_rival_queries import (  # noqa: E402
    _ACTIONS,
    _FAMILY,
    _query_rival_pair,
    _rival_query_shape,
    _scan_native_events,
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
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_RIVAL_STATE_FIELDS = (
    "rival_active",
    "rival_since_date_raw",
    "rival_count",
    "max_rivals",
    "diplomatic_power_raw",
    "at_war",
)


class ReloadValidationError(RuntimeError):
    """An expected bounded read-only validation stop."""


def _resolve_report(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise ReloadValidationError(f"SOURCE_QUERY_REPORT_NOT_FILE:{resolved}")
    return resolved


def _valid_tag(value: object) -> bool:
    return isinstance(value, str) and _TAG_RE.fullmatch(value) is not None


def _strict_int(value: object) -> bool:
    return type(value) is int


def _normal_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return os.path.normcase(os.path.normpath(value))


def _source_recipients(payload: dict[str, object]) -> tuple[str, ...]:
    values = payload.get("recipients")
    if not isinstance(values, list) or not values:
        raise ReloadValidationError("SOURCE_RECIPIENTS_MISSING")
    recipients: list[str] = []
    for value in values:
        if not _valid_tag(value) or value == _ACTOR or value in recipients:
            raise ReloadValidationError("SOURCE_RECIPIENTS_INVALID")
        recipients.append(value)
    return tuple(recipients)


def _source_summary(path: Path, payload: dict[str, object],
                    recipients: tuple[str, ...]) -> dict[str, object]:
    source_control = payload.get("control")
    source_session = payload.get("session")
    source_binding = payload.get("build_binding")
    source_build = payload.get("build_manifest")
    source_runtime = payload.get("source")
    source_checks = payload.get("checks")
    expected_date = payload.get("expected_date_raw")
    control_shape = (
        isinstance(source_control, dict)
        and _strict_int(source_control.get("date_raw"))
        and source_control.get("player_slot") == _PLAYER_SLOT
        and source_control.get("paused_flag") == 1
        and source_control.get("date_raw") == expected_date
    )
    session_shape = (
        isinstance(source_session, dict)
        and isinstance(source_session.get("session_id"), str)
        and bool(source_session.get("session_id"))
        and isinstance(source_session.get("dll_sha256"), str)
        and _SHA256_RE.fullmatch(source_session["dll_sha256"]) is not None
    )
    build_shape = (
        isinstance(source_binding, dict)
        and source_binding.get("installation_matches_build_manifest") is True
        and isinstance(source_binding.get("installation_dll_sha256"), str)
        and isinstance(source_binding.get("build_manifest_dll_sha256"), str)
        and source_binding.get("installation_dll_sha256", "").casefold()
        == source_binding.get("build_manifest_dll_sha256", "").casefold()
    )
    runtime_shape = (
        isinstance(source_runtime, dict)
        and isinstance(source_runtime.get("game_executable"), str)
        and _strict_int(source_runtime.get("bytes"))
    )
    passed_checks = (
        isinstance(source_checks, dict)
        and bool(source_checks)
        and all(value is True for value in source_checks.values())
    )
    return {
        "path": str(path),
        "report_sha256": _hash_file(path, maximum=_MAX_METADATA_BYTES),
        "status": payload.get("status"),
        "validator": payload.get("validator"),
        "actor": payload.get("actor"),
        "family": payload.get("family"),
        "actions": payload.get("actions"),
        "recipients": list(recipients),
        "expected_date_raw": expected_date,
        "control": source_control,
        "session": source_session,
        "source": source_runtime,
        "build_binding": source_binding,
        "build_manifest": source_build,
        "diplomat_semantics": payload.get("diplomat_semantics"),
        "save": payload.get("save"),
        "native_events": payload.get("native_events"),
        "checks": {
            "report_status_passed": payload.get("status") == "passed",
            "source_checks_passed": passed_checks,
            "source_actor_fra": payload.get("actor") == _ACTOR,
            "source_family_rival": payload.get("family") == _FAMILY,
            "source_actions_exact": set(payload.get("actions", [])) == set(_ACTIONS),
            "source_control_shape": control_shape,
            "source_session_shape": session_shape,
            "source_build_shape": build_shape,
            "source_runtime_shape": runtime_shape,
        },
    }


def _rival_state(query: object) -> dict[str, object]:
    if not isinstance(query, dict):
        return {
            "complete": False,
            "values": {field: None for field in _RIVAL_STATE_FIELDS},
            "relationship_state": None,
        }
    relationship = query.get("relationship_state")
    relationship_active = (
        relationship.get("rival_active")
        if isinstance(relationship, dict) else None
    )
    values = {field: query.get(field) for field in _RIVAL_STATE_FIELDS}
    relationship_consistent = (
        isinstance(relationship, dict)
        and relationship.get("complete") is True
        and relationship_active is values["rival_active"]
        and relationship.get("rival_since_date_raw") == values["rival_since_date_raw"]
    )
    value_types = (
        type(values["rival_active"]) is bool
        and (_strict_int(values["rival_since_date_raw"]))
        and all(_strict_int(values[field]) for field in ("rival_count", "max_rivals", "diplomatic_power_raw"))
        and type(values["at_war"]) is bool
    )
    return {
        "complete": (
            query.get("rival_state_verified") is True
            and relationship_consistent
            and value_types
        ),
        "values": values,
        "relationship_state": relationship,
    }


def _legality_summary(query: object) -> dict[str, object]:
    if not isinstance(query, dict):
        return {"present": False, "status": None, "complete": None}
    legality = query.get("legality")
    if not isinstance(legality, dict):
        return {"present": False, "status": None, "complete": None}
    return {
        "present": True,
        "status": legality.get("status"),
        "complete": legality.get("complete"),
        "native_command_validity": query.get("native_command_validity"),
        "reasons": legality.get("reasons"),
    }


def _compact_shape(shape: object) -> dict[str, object]:
    if not isinstance(shape, dict):
        return {"complete": False}
    return {
        "complete": shape.get("complete") is True,
        "action_id": shape.get("action_id"),
        "family": shape.get("family"),
        "actor": shape.get("actor"),
        "recipient": shape.get("recipient"),
        "phase": shape.get("phase"),
        "session_status": shape.get("session_status"),
        "session_date_raw": shape.get("session_date_raw"),
        "rival_state_verified": shape.get("rival_state_verified"),
        "native_command_validity": shape.get("native_command_validity"),
        "full_rules_complete": shape.get("full_rules_complete"),
        "native_action_available": shape.get("native_action_available"),
        "pointer_keys": shape.get("pointer_keys"),
    }


def _query_comparison(source_payload: dict[str, object],
                      current_queries: dict[str, dict[str, object]],
                      recipients: tuple[str, ...],
                      expected_date: int) -> dict[str, object]:
    source_queries = source_payload.get("queries")
    if not isinstance(source_queries, dict):
        raise ReloadValidationError("SOURCE_QUERIES_MISSING")
    comparisons: dict[str, object] = {}
    for recipient in recipients:
        source_pair = source_queries.get(recipient)
        current_pair = current_queries.get(recipient)
        if not isinstance(source_pair, dict) or not isinstance(current_pair, dict):
            comparisons[recipient] = {
                "actions": {},
                "all_relation_states_match": False,
                "all_query_shapes_complete": False,
            }
            continue
        action_records: dict[str, object] = {}
        relation_matches: list[bool] = []
        shape_matches: list[bool] = []
        for action in _ACTIONS:
            source_query = source_pair.get(action)
            current_query = current_pair.get(action)
            source_shape = _rival_query_shape(
                source_query, action, recipient, expected_date
            )
            current_shape = _rival_query_shape(
                current_query, action, recipient, expected_date
            )
            source_state = _rival_state(source_query)
            current_state = _rival_state(current_query)
            state_match = (
                source_state.get("complete") is True
                and current_state.get("complete") is True
                and source_state.get("values") == current_state.get("values")
            )
            shape_match = (
                source_shape.get("complete") is True
                and current_shape.get("complete") is True
            )
            relation_matches.append(state_match)
            shape_matches.append(shape_match)
            action_records[action] = {
                "source_shape": _compact_shape(source_shape),
                "reload_shape": _compact_shape(current_shape),
                "source_relation_state": source_state,
                "reload_relation_state": current_state,
                "relation_state_matches": state_match,
                # Legality is deliberately retained as a separate observation;
                # it is not used as relation-state evidence.
                "source_legality": _legality_summary(source_query),
                "reload_legality": _legality_summary(current_query),
                "legality_separate_from_relation": (
                    _legality_summary(current_query).get("present") is True
                ),
            }
        comparisons[recipient] = {
            "actions": action_records,
            "all_relation_states_match": all(relation_matches),
            "all_query_shapes_complete": all(shape_matches),
            "source_expected_rival": (
                source_payload.get("expected_rival", {}).get(recipient)
                if isinstance(source_payload.get("expected_rival"), dict) else None
            ),
        }
    return comparisons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="new process installation.json")
    parser.add_argument("--source-query-report", type=Path, required=True,
                        help="passed run_rival_queries report.json or its artifact directory")
    parser.add_argument("--save-path", type=Path, required=True,
                        help="save loaded by the new process")
    parser.add_argument("--expected-save-sha256", required=True,
                        help="expected SHA-256 of --save-path")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "rival-reload")
    report: dict[str, object] = {
        "validator": "validate_rival_reload.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_rival_reload_validation",
        "installation": str(installation),
        "source_query_report": str(args.source_query_report.expanduser().resolve()),
        "save_path": str(args.save_path.expanduser().resolve()),
        "expected_save_sha256": args.expected_save_sha256,
        "artifact": str(artifact),
        "actor": _ACTOR,
        "family": _FAMILY,
        "actions": list(_ACTIONS),
        "execute_call_count": 0,
        "execution_requested": False,
        "advance_requested": False,
        "save_requested": False,
        "installation_requested": False,
        "business_submission": False,
        "checks": {},
    }
    log_path = installation.parent / "control-probe.jsonl"
    log_start_offset: int | None = None
    recipients: tuple[str, ...] = ()
    expected_date: int | None = None
    source_payload: dict[str, object] | None = None
    try:
        expected_hash = str(args.expected_save_sha256).strip()
        if _SHA256_RE.fullmatch(expected_hash) is None:
            raise ReloadValidationError("EXPECTED_SAVE_SHA256_INVALID")
        source_report_path = _resolve_report(args.source_query_report)
        source_value = _read_json(source_report_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(source_value, dict):
            raise ReloadValidationError("SOURCE_QUERY_REPORT_NOT_OBJECT")
        source_payload = source_value
        recipients = _source_recipients(source_payload)
        expected_value = source_payload.get("expected_date_raw")
        if not _strict_int(expected_value):
            raise ReloadValidationError("SOURCE_EXPECTED_DATE_INVALID")
        expected_date = expected_value
        source = _source_summary(source_report_path, source_payload, recipients)
        report["source_query"] = source
        source_checks = source.get("checks")
        if not isinstance(source_checks, dict) or not all(source_checks.values()):
            raise ReloadValidationError("SOURCE_QUERY_REPORT_NOT_PASSED")

        report.update(_installation_binding(installation))
        executable = game_exe().expanduser().resolve(strict=True)
        current_exe_bytes = executable.stat().st_size
        report["source_runtime"] = {
            "game_executable": str(executable),
            "bytes": current_exe_bytes,
            "source_binding": "local_config.game_exe",
        }
        save_path = args.save_path.expanduser().resolve(strict=True)
        report["save"] = {
            "provided": True,
            **_hash_file(save_path, maximum=_MAX_SAVE_BYTES),
            "expected_sha256": expected_hash.lower(),
        }
        report["save"]["sha256_matches_expected"] = (
            report["save"].get("sha256", "").casefold() == expected_hash.casefold()
        )

        session = ObserverSession(installation, executable)
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")

        probes = _run_snapshots(session, artifact / "after" / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        try:
            diplomat_semantics = _diplomat_semantics(probes["diplomats"]["snapshot"])
            diplomat_semantics_error = None
        except Exception as error:
            diplomat_semantics = None
            diplomat_semantics_error = {
                "type": type(error).__name__, "message": str(error),
            }
        report["after"] = {
            "health": health,
            "control": control,
            "diplomat_semantics": diplomat_semantics,
            "diplomat_semantics_error": diplomat_semantics_error,
            "probes": {
                name: {
                    "status": item.get("status"),
                    "snapshot_path": item.get("snapshot_path"),
                    "snapshot_completeness": item.get("snapshot_completeness"),
                    "snapshot_sha256": item.get("snapshot_sha256"),
                }
                for name, item in probes.items()
            },
            "four_snapshot_boundary": "before_queries",
        }

        try:
            log_start_offset = log_path.stat().st_size
        except OSError as error:
            raise ReloadValidationError(f"NATIVE_LOG_UNAVAILABLE:{error}") from error
        report["log_start_offset"] = log_start_offset

        query_results: dict[str, dict[str, object]] = {}
        with DurableJournal(
            artifact / "diplomacy.sqlite3", session.experiment_id,
            session.session_id, global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                query_results[recipient] = _query_rival_pair(
                    api, recipient, artifact / "after" / "queries" / f"{recipient}.json"
                )
        _write_json(artifact / "after" / "queries.json", query_results)
        report["after"]["queries"] = query_results
        report["relation_comparison"] = _query_comparison(
            source_payload, query_results, recipients, expected_date
        )

        build_binding = report.get("build_binding")
        source_query = report.get("source_query")
        source_session = source_query.get("session") if isinstance(source_query, dict) else None
        source_runtime = source_query.get("source") if isinstance(source_query, dict) else None
        source_binding = source_query.get("build_binding") if isinstance(source_query, dict) else None
        source_build = source_query.get("build_manifest") if isinstance(source_query, dict) else None
        current_dll = session.record.get("dll_sha256")
        source_dll = source_session.get("dll_sha256") if isinstance(source_session, dict) else None
        source_manifest_dll = (
            source_binding.get("build_manifest_dll_sha256")
            if isinstance(source_binding, dict) else None
        )
        if source_manifest_dll is None and isinstance(source_build, dict):
            source_manifest_dll = source_build.get("dll_sha256")
        current_manifest_dll = (
            build_binding.get("build_manifest_dll_sha256")
            if isinstance(build_binding, dict) else None
        )
        same_executable = (
            isinstance(source_runtime, dict)
            and _normal_path(source_runtime.get("game_executable"))
            == _normal_path(str(executable))
            and source_runtime.get("bytes") == current_exe_bytes
        )
        same_dll = (
            isinstance(source_dll, str)
            and isinstance(current_dll, str)
            and source_dll.casefold() == current_dll.casefold()
        )
        same_build_dll = (
            isinstance(source_manifest_dll, str)
            and isinstance(current_manifest_dll, str)
            and source_manifest_dll.casefold() == current_manifest_dll.casefold()
        )
        new_session = (
            isinstance(source_session, dict)
            and isinstance(source_session.get("session_id"), str)
            and source_session.get("session_id") != session.session_id
        )
        source_control = source_query.get("control") if isinstance(source_query, dict) else None
        source_semantics = source_query.get("diplomat_semantics") if isinstance(source_query, dict) else None
        control_matches = (
            isinstance(source_control, dict)
            and all(control.get(field) == source_control.get(field)
                    for field in ("date_raw", "player_slot", "paused_flag"))
        )
        semantics_comparable = isinstance(source_semantics, list)
        semantics_matches = (
            not semantics_comparable
            or (isinstance(diplomat_semantics, list) and diplomat_semantics == source_semantics)
        )
        relation_comparison = report.get("relation_comparison")
        relation_ok = (
            isinstance(relation_comparison, dict)
            and len(relation_comparison) == len(recipients)
            and all(
                isinstance(item, dict)
                and item.get("all_relation_states_match") is True
                and item.get("all_query_shapes_complete") is True
                for item in relation_comparison.values()
            )
        )
        report["provenance_comparison"] = {
            "same_executable": same_executable,
            "same_dll": same_dll,
            "same_build_dll": same_build_dll,
            "new_session": new_session,
            "source_session_id": source_session.get("session_id") if isinstance(source_session, dict) else None,
            "reload_session_id": session.session_id,
            "source_control": source_control,
            "reload_control": control,
            "control_matches_source": control_matches,
            "diplomat_semantics_saved_in_source": semantics_comparable,
            "diplomat_semantics_matches_source": semantics_matches,
        }
        report["checks"] = {
            "source_query_report_passed": True,
            "new_process_ready": health.get("status") == "ready" and health.get("complete") is True,
            "player_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "date_matches_source": control.get("date_raw") == expected_date
            and health.get("date_raw") == expected_date,
            "four_snapshots_complete": _snapshots_complete(probes),
            "control_matches_source": control_matches,
            "diplomat_semantics_matches_source": semantics_matches,
            "source_and_reload_use_different_sessions": new_session,
            "same_executable_immutable_metadata": same_executable,
            "same_loaded_dll": same_dll,
            "same_build_dll": same_build_dll,
            "reload_installation_matches_build": (
                isinstance(build_binding, dict)
                and build_binding.get("installation_matches_build_manifest") is True
                and build_binding.get("loaded_dll_sha256") == current_dll
            ),
            "all_source_recipients_queried": relation_comparison is not None
            and set(relation_comparison) == set(recipients),
            "rival_relation_states_match_source": relation_ok,
            "save_hash_matches_expected": report["save"].get("sha256_matches_expected") is True,
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "no_advance_save_or_install": (
                report["advance_requested"] is False
                and report["save_requested"] is False
                and report["installation_requested"] is False
            ),
        }
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if log_start_offset is not None and expected_date is not None:
            native_slice_path = artifact / "native-events-slice.jsonl"
            report["native_events"] = _copy_log_slice(
                log_path, log_start_offset, native_slice_path
            )
            native_events = report.get("native_events")
            if isinstance(native_events, dict) and native_events.get("status") == "ok":
                try:
                    report["native_event_summary"] = _scan_native_events(
                        native_slice_path, expected_date, recipients,
                        str(report.get("session", {}).get("session_id", "")),
                    )
                except (OSError, UnicodeError, ValueError) as error:
                    report["native_event_summary"] = {
                        "complete": False,
                        "error": {"type": type(error).__name__, "message": str(error)},
                    }
                report.setdefault("checks", {})["native_event_slice_complete"] = (
                    report.get("native_event_summary", {}).get("complete") is True
                )
            else:
                report.setdefault("checks", {})["native_event_slice_complete"] = False
        else:
            report.setdefault("checks", {})["native_event_slice_complete"] = False
        if report.get("status") != "failed":
            checks = report.get("checks")
            report["status"] = "passed" if isinstance(checks, dict) and all(checks.values()) else "failed"
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
