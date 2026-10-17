"""Validate Insult query state in an already reloaded observer process.

The validator is read-only.  It attaches to the supplied installation, reads
the four reviewed observer snapshots, queries ordinary Insult and scornful
Insult state for one recipient, and optionally hashes a separately named save.
It never publishes a diplomacy request, advances the game, saves, starts a
process, or installs a module.
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
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_insult_queries import (  # noqa: E402
    _query_insult_set,
    _query_set_summary,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
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
_FAMILY = "insult"
_ACTIONS = ("send_insult", "scornful_insult")
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_STATE_FIELDS = (
    "family", "action_id", "insult_id", "insult_parameter_selected",
    "insult_state_verified", "insult_active", "opinion_modifier_raw",
    "actor_prestige_raw", "prestige_cost_raw",
)


class ReloadValidationError(RuntimeError):
    """An expected read-only validation stop."""


def _state_projection(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {field: None for field in _STATE_FIELDS}
    return {field: value.get(field) for field in _STATE_FIELDS}


def _query_state_complete(value: object, action_id: str, expected_id: int) -> bool:
    if not isinstance(value, dict):
        return False
    cost = value.get("prestige_cost_raw")
    return (
        value.get("family") == _FAMILY
        and value.get("action_id") == action_id
        and value.get("insult_id") == expected_id
        and value.get("insult_parameter_selected") is True
        and value.get("insult_state_verified") is True
        and type(value.get("insult_active")) is bool
        and isinstance(value.get("opinion_modifier_raw"), int)
        and not isinstance(value.get("opinion_modifier_raw"), bool)
        and isinstance(value.get("actor_prestige_raw"), int)
        and not isinstance(value.get("actor_prestige_raw"), bool)
        and (cost is None or (isinstance(cost, int) and not isinstance(cost, bool)))
    )


def _query_summary_complete(summary: object, selected_id: int | None) -> bool:
    if not isinstance(summary, dict):
        return False
    send = summary.get("send")
    scornful = summary.get("scornful")
    if not _query_state_complete(send, "send_insult", -1):
        return False
    if selected_id is not None:
        return _query_state_complete(scornful, "scornful_insult", selected_id)
    return (
        isinstance(scornful, dict)
        and isinstance(scornful.get("candidates"), dict)
        and scornful["candidates"].get("complete") is True
    )


def _resource_semantics(snapshot: object) -> dict[str, object]:
    """Summarize the native diplomat resource fields without inferring enums."""

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("countries"), list):
        return {"complete": False, "actor": _ACTOR, "available_count": None,
                "entry_count": None}
    for country in snapshot["countries"]:
        if isinstance(country, dict) and country.get("tag") == _ACTOR:
            entries = country.get("diplomacy_entries")
            available = country.get("available_diplomat_count")
            return {
                "complete": (
                    isinstance(available, int) and not isinstance(available, bool)
                    and isinstance(entries, list)
                ),
                "actor": _ACTOR,
                "available_count": available,
                "entry_count": len(entries) if isinstance(entries, list) else None,
            }
    return {"complete": False, "actor": _ACTOR, "available_count": None,
            "entry_count": None}


def _extract_query_summary(value: object, depth: int = 0) -> dict[str, object] | None:
    if depth > 6 or not isinstance(value, dict):
        return None
    candidate = value.get("query_summary")
    if isinstance(candidate, dict):
        return candidate
    for key in ("after", "result", "observations", "before"):
        found = _extract_query_summary(value.get(key), depth + 1)
        if found is not None:
            return found
    return None


def _extract_control(value: object, depth: int = 0) -> dict[str, object] | None:
    if depth > 6 or not isinstance(value, dict):
        return None
    candidate = value.get("control")
    if isinstance(candidate, dict) and all(
            key in candidate for key in ("date_raw", "player_slot", "paused_flag")):
        return candidate
    for key in ("after", "result", "observations", "before"):
        found = _extract_control(value.get(key), depth + 1)
        if found is not None:
            return found
    return None


def _extract_diplomat_semantics(value: object, depth: int = 0) -> list[dict[str, object]] | None:
    if depth > 6 or not isinstance(value, dict):
        return None
    candidate = value.get("diplomat_semantics")
    if isinstance(candidate, list):
        return candidate
    diplomat = value.get("diplomat")
    if isinstance(diplomat, dict) and isinstance(diplomat.get("semantics"), list):
        return diplomat["semantics"]
    for key in ("after", "result", "observations", "before"):
        found = _extract_diplomat_semantics(value.get(key), depth + 1)
        if found is not None:
            return found
    return None


def _reference_checks(reference: Path, current_summary: dict[str, object],
                      current_control: dict[str, object],
                      current_semantics: list[dict[str, object]]) -> dict[str, object]:
    reference = reference.expanduser().resolve(strict=True)
    candidates = [reference] if reference.is_file() else [
        reference / "report.json",
        reference / "after" / "queries.json",
        reference / "queries.json",
    ]
    payloads: list[tuple[Path, object]] = []
    for path in candidates:
        if path.is_file():
            payloads.append((path, _read_json(path, maximum=_MAX_METADATA_BYTES)))
    if not payloads:
        raise ReloadValidationError(f"REFERENCE_ARTIFACT_NO_METADATA:{reference}")
    reference_summary = None
    reference_control = None
    reference_semantics = None
    source_paths: list[str] = []
    for path, payload in payloads:
        source_paths.append(str(path))
        if reference_summary is None:
            reference_summary = _extract_query_summary(payload)
        if reference_control is None:
            reference_control = _extract_control(payload)
        if reference_semantics is None:
            reference_semantics = _extract_diplomat_semantics(payload)
    query_matches = isinstance(reference_summary, dict) and (
        _state_projection(reference_summary.get("send"))
        == _state_projection(current_summary.get("send"))
        and _state_projection(reference_summary.get("scornful"))
        == _state_projection(current_summary.get("scornful"))
    )
    control_matches = (
        reference_control is None
        or all(current_control.get(key) == reference_control.get(key)
               for key in ("date_raw", "player_slot", "paused_flag"))
    )
    semantics_matches = reference_semantics is None or reference_semantics == current_semantics
    checks = {
        "reference_query_state_matches": query_matches,
        "reference_control_matches": control_matches,
        "reference_diplomat_semantics_matches": semantics_matches,
    }
    return {
        "provided": True,
        "path": str(reference),
        "source_paths": source_paths,
        "query_summary": reference_summary,
        "control": reference_control,
        "diplomat_semantics": reference_semantics,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--recipient", required=True,
                        help="three-letter Insult target, excluding FRA")
    parser.add_argument("--insult-id", type=int,
                        help="optional selected scornful Insult candidate")
    parser.add_argument("--expected-insult-active", choices=("active", "absent"))
    parser.add_argument("--expected-selected-active", choices=("active", "absent"))
    parser.add_argument("--expected-legality",
                        choices=("available", "unavailable", "unknown"))
    parser.add_argument("--expected-available-diplomats", type=int)
    parser.add_argument("--save-path", type=Path)
    parser.add_argument("--expected-save-sha256")
    parser.add_argument("--reference-artifact", type=Path)
    args = parser.parse_args(argv)

    if args.expected_selected_active is not None and args.insult_id is None:
        parser.error("--expected-selected-active requires --insult-id")

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "insult-reload")
    report: dict[str, object] = {
        "validator": "validate_insult_reload.py",
        "status": "running",
        "mode": "read_only_insult_reload_validation",
        "installation": str(installation),
        "actor": _ACTOR,
        "recipient": args.recipient,
        "family": _FAMILY,
        "actions": list(_ACTIONS),
        "selected_insult_id": args.insult_id,
        "expected_date_raw": args.expected_date_raw,
        "expected_insult_active": args.expected_insult_active,
        "expected_selected_active": args.expected_selected_active,
        "expected_legality": args.expected_legality,
        "save_path": str(args.save_path.expanduser().resolve()) if args.save_path else None,
        "expected_save_sha256": args.expected_save_sha256.lower()
        if isinstance(args.expected_save_sha256, str) else None,
        "reference_artifact": str(args.reference_artifact.expanduser().resolve())
        if args.reference_artifact else None,
        "artifact": str(artifact),
        "execute_call_count": 0,
        "execution_requested": False,
        "business_submission": False,
        "checks": {},
    }
    try:
        if not _TAG_RE.fullmatch(args.recipient) or args.recipient == _ACTOR:
            raise ReloadValidationError("RECIPIENT_TAG_INVALID")
        if args.insult_id is not None and not 0 <= args.insult_id <= 2147483647:
            raise ReloadValidationError("INSULT_ID_INVALID")
        if args.expected_save_sha256 is not None and not _SHA256_RE.fullmatch(args.expected_save_sha256):
            raise ReloadValidationError("EXPECTED_SAVE_SHA256_INVALID")
        report.update(_installation_binding(installation))
        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
        session = ObserverSession(installation, executable)
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health_before = wait_runtime_ready(session, restore_minimized=False)
        if health_before.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "after" / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        semantics = _diplomat_semantics(probes["diplomats"]["snapshot"])
        resources = _resource_semantics(probes["diplomats"]["snapshot"])
        health_after = session.health()
        report["after"] = {
            "health_before": health_before,
            "health_after": health_after,
            "control": control,
            "diplomat_semantics": semantics,
            "resources": resources,
            "probes": _public_probe_records(probes),
            "snapshot_complete": _snapshots_complete(probes),
        }
        selected_id = args.insult_id
        with DurableJournal(
            artifact / "diplomacy.sqlite3", session.experiment_id,
            session.session_id, global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            queries = _query_insult_set(
                api, args.recipient, artifact / "after" / "queries", selected_id
            )
        _write_json(artifact / "queries.json", queries)
        summary = _query_set_summary(queries, selected_id)
        report["queries"] = queries
        report["query_summary"] = summary
        if args.save_path is not None:
            save_path = args.save_path.expanduser().resolve(strict=True)
            report["save"] = _hash_file(save_path, maximum=_MAX_SAVE_BYTES)
            report["save"]["provided"] = True
        else:
            report["save"] = {"provided": False, "sha256": None}
        if args.reference_artifact is not None:
            report["reference"] = _reference_checks(
                args.reference_artifact, summary, control, semantics
            )
        else:
            report["reference"] = {"provided": False, "checks": {}}

        send = summary.get("send", {}) if isinstance(summary, dict) else {}
        scornful = summary.get("scornful", {}) if isinstance(summary, dict) else {}
        capabilities = session.installation_capabilities()
        build = report.get("build_binding")
        expected_active = args.expected_insult_active
        expected_selected = args.expected_selected_active
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
            "diplomat_semantics_complete": isinstance(semantics, list),
            "resource_semantics_complete": resources.get("complete") is True,
            "query_set_complete": _query_summary_complete(summary, selected_id),
            "scornful_discovery_complete": (
                selected_id is not None
                or summary.get("scornful_discovery_complete") is True
            ),
            "ordinary_insult_family": (
                isinstance(send, dict) and send.get("family") == _FAMILY
            ),
            "scornful_insult_family": (
                isinstance(scornful, dict) and scornful.get("family") == _FAMILY
            ),
            "native_insult_query_acknowledged": (
                "native_insult_query" in capabilities
            ),
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "source_build_session_bound": (
                isinstance(build, dict)
                and build.get("installation_matches_build_manifest") is True
                and build.get("loaded_dll_sha256") == build.get("installation_dll_sha256")
            ),
            "save_hash_bound": (
                report["save"].get("provided") is not True
                or isinstance(report["save"].get("sha256"), str)
            ),
        }
        if expected_active is not None:
            checks["ordinary_insult_active_expected"] = (
                send.get("insult_active") is (expected_active == "active")
            )
        if args.expected_selected_active is not None:
            checks["selected_insult_active_expected"] = (
                scornful.get("insult_active") is (expected_selected == "active")
            )
        if args.expected_legality is not None:
            checks["ordinary_legality_expected"] = (
                send.get("legality_status") == args.expected_legality
            )
        if args.expected_available_diplomats is not None:
            checks["available_diplomats_expected"] = (
                resources.get("available_count") == args.expected_available_diplomats
            )
        expected_hash = args.expected_save_sha256.lower() if args.expected_save_sha256 else None
        if expected_hash is not None:
            checks["save_hash_expected"] = report["save"].get("sha256") == expected_hash
        reference = report.get("reference")
        if isinstance(reference, dict) and reference.get("provided") is True:
            ref_checks = reference.get("checks")
            if isinstance(ref_checks, dict):
                checks.update({key: value is True for key, value in ref_checks.items()})
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_RELOAD_VALIDATION_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
