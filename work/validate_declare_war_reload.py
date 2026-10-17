#!/usr/bin/env python3
"""Validate a saved Declare War result in a new observer process.

The game and the observer installation must already be running.  This
validator hashes the supplied save, reads the four bounded snapshots and one
parameter-bound native query, and compares the source execution's war-result
pair with the reloaded FRA/ENG war association.  It never executes, retries,
advances, saves, installs, or restarts a game operation.
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
from work.run_declare_war_execution import (  # noqa: E402
    _ACTION,
    _ACTOR,
    _FAMILY,
    _PLAYER_SLOT,
    _TAG_RE,
    _declare_war_query_complete,
    _native_result_auxiliary_contract,
    _query_declare_war,
    _query_identity,
    _war_state_pair,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
    _public_probe_records,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _find_save,
    _hash_file,
    _read_json,
    _run_snapshots,
)


_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024


class ReloadValidationError(RuntimeError):
    """An expected bounded reload validation stop."""


def _resolve_report(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise ReloadValidationError(f"EXECUTION_REPORT_NOT_FILE:{resolved}")
    return resolved


def _public_result(payload: dict[str, object]) -> dict[str, object] | None:
    candidates: list[object] = []
    for key in ("reopened_result", "final_result"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value.get("result"))
    checks = payload.get("result_checks")
    if isinstance(checks, dict):
        candidates.append(checks.get("public_result"))
    poll = payload.get("poll")
    if isinstance(poll, dict) and isinstance(poll.get("final"), dict):
        candidates.append(poll["final"].get("result"))
    for value in candidates:
        if isinstance(value, dict):
            return value
    return None


def _result_pair(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"war_id": None, "stability_before_raw": None, "stability_after_raw": None}
    return {
        "war_id": value.get("war_id"),
        "stability_before_raw": value.get("stability_before_raw"),
        "stability_after_raw": value.get("stability_after_raw"),
    }


def _source_parameters(payload: dict[str, object]) -> dict[str, object]:
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        raise ReloadValidationError("SOURCE_PARAMETERS_MISSING")
    try:
        normalized = ObserverSession._normalize_declare_war_selection(parameters)
    except (TypeError, ValueError) as error:
        raise ReloadValidationError(f"SOURCE_PARAMETERS_INVALID:{error}") from error
    if normalized is None:
        raise ReloadValidationError("SOURCE_PARAMETERS_INVALID")
    return parameters


def _source_after(payload: dict[str, object]) -> dict[str, object]:
    after = payload.get("after")
    if not isinstance(after, dict):
        raise ReloadValidationError("SOURCE_AFTER_MISSING")
    control = after.get("control")
    if not isinstance(control, dict):
        raise ReloadValidationError("SOURCE_AFTER_CONTROL_MISSING")
    war_state = after.get("war_state_pair")
    if not isinstance(war_state, dict):
        raise ReloadValidationError("SOURCE_AFTER_WAR_STATE_PAIR_MISSING")
    return {"control": control, "war_state_pair": war_state}


def _source_contract(payload: dict[str, object], recipient: str,
                     parameters: dict[str, object]) -> dict[str, object]:
    public = _public_result(payload)
    result_checks = payload.get("result_checks")
    checks: dict[str, bool] = {
        "report_status_passed": payload.get("status") == "passed",
        "result_checks_all": isinstance(result_checks, dict) and result_checks.get("all") is True,
        "action_supported": payload.get("action_id") == _ACTION,
        "recipient_bound": payload.get("recipient") == recipient,
        "family_bound": payload.get("family") == _FAMILY,
        "terminal_result_present": isinstance(public, dict),
    }
    if not isinstance(public, dict):
        return {"checks": checks, "public_result": None, "war_result_pair": {}}
    goal = parameters.get("war_goal", {})
    auxiliary = _native_result_auxiliary_contract(public)
    checks.update({
        "event_bound": public.get("event") == "native_declare_war_execution_result",
        "parameters_bound": all(public.get(field) == expected for field, expected in (
            ("action_id", _ACTION), ("family", _FAMILY), ("actor", _ACTOR),
            ("recipient", recipient), ("phase", "initiate"),
            ("casus_belli", parameters.get("casus_belli")),
            ("war_goal_province", goal.get("province_id")),
            ("war_goal_beneficiary", goal.get("beneficiary")),
        )),
        "executed_result": (
            public.get("outcome") == "executed"
            and public.get("war_before") is False
            and public.get("war_after") is True
            and public.get("execution_verified") is True
            and public.get("request_binding_verified") is True
        ),
        # The native result may deliberately leave these auxiliary values
        # null when their verified flags are false.  Keep the historical
        # check names as aliases while validating the nullable contract.
        "war_identity_contract": auxiliary["war_identity_contract"],
        "stability_contract": auxiliary["stability_contract"],
        "war_id_integer": auxiliary["war_identity_contract"],
        "stability_integer": auxiliary["stability_contract"],
    })
    return {"checks": checks, "public_result": public, "war_result_pair": _result_pair(public)}


def _result_pair_consistency(payload: dict[str, object], public: dict[str, object]) -> dict[str, object]:
    """Compare the saved public result and the journal-reopen result."""

    source_pair = _result_pair(public)
    reopened = payload.get("reopened_result")
    reopened_public = reopened.get("result") if isinstance(reopened, dict) else None
    reopened_pair = _result_pair(reopened_public)
    return {
        "source": source_pair,
        "reopened": reopened_pair,
        "match": source_pair == reopened_pair,
        "stability_comparison_scope": "native_execution_result_persisted_across_journal_reopen",
    }


def _query_contract(query: object, recipient: str, parameters: dict[str, object]) -> dict[str, bool]:
    selected = query.get("parameters") if isinstance(query, dict) else None
    return {
        "identity": _query_identity(query, recipient, parameters),
        "session_ready": isinstance(query, dict)
        and isinstance(query.get("session"), dict)
        and query["session"].get("status") == "ready",
        "query_complete": _declare_war_query_complete(query, parameters),
        "requested_parameters_preserved": isinstance(selected, dict)
        and selected.get("requested") == parameters,
    }


def _war_state_comparison(source_pair: dict[str, object], current_pair: dict[str, object],
                          public: dict[str, object], recipient: str) -> dict[str, object]:
    supported = recipient == "ENG"
    source_at_war = source_pair.get("pair_at_war")
    current_at_war = current_pair.get("pair_at_war")
    return {
        "scope": "FRA_ENG",
        "recipient_supported": supported,
        "source_pair_at_war": source_at_war,
        "reload_pair_at_war": current_at_war,
        "pair_match": supported and source_at_war is current_at_war,
        "source_war_handles": source_pair.get("war_handles", []),
        "reload_war_handles": current_pair.get("war_handles", []),
        "execution_war_id": public.get("war_id"),
        "execution_stability_before_raw": public.get("stability_before_raw"),
        "execution_stability_after_raw": public.get("stability_after_raw"),
        "war_id_and_stability_source": "native_declare_war_execution_result",
        "reload_war_association_source": "probe_war_pair",
        "note": (
            "probe_war_pair exposes opaque native war handles, while the native result exposes the integer war_id and stability pair; they are recorded separately and never compared as if they had the same representation."
        ),
    }


def _lower(value: object) -> str | None:
    return value.casefold() if isinstance(value, str) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="already-running new-process installation.json")
    parser.add_argument("--execution-artifact", type=Path, required=True,
                        help="passed Declare War execution report or artifact directory")
    parser.add_argument("--save-name", required=True,
                        help="save basename in the configured EU4 save directory")
    parser.add_argument("--save-sha256", required=True,
                        help="expected SHA-256 for --save-name")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--expected-war-id", type=int, default=None)
    parser.add_argument("--expected-stability-after-raw", type=int, default=None)
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    execution_report_path = args.execution_artifact.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "declare-war-reload")
    report: dict[str, object] = {
        "validator": "validate_declare_war_reload.py", "version": 1,
        "status": "running", "mode": "read_only_declare_war_reload_validation",
        "installation": str(installation), "execution_artifact": str(execution_report_path),
        "actor": _ACTOR, "family": _FAMILY, "expected_date_raw": args.expected_date_raw,
        "expected_war_id": args.expected_war_id,
        "expected_stability_after_raw": args.expected_stability_after_raw,
        "save_name": args.save_name, "expected_save_sha256": args.save_sha256.lower(),
        "artifact": str(artifact), "execute_call_count": 0,
        "execution_requested": False, "business_submission": False,
        "advance_requested": False, "save_requested": False,
        "installation_requested": False, "checks": {},
    }
    try:
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
            raise ReloadValidationError("EXPECTED_DATE_RAW_MUST_BE_INT")
        if _SHA256_RE.fullmatch(args.save_sha256) is None:
            raise ReloadValidationError("EXPECTED_SAVE_SHA256_INVALID")
        execution_report_path = _resolve_report(execution_report_path)
        source_payload = _read_json(execution_report_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(source_payload, dict):
            raise ReloadValidationError("EXECUTION_REPORT_NOT_OBJECT")
        recipient = source_payload.get("recipient")
        if not isinstance(recipient, str) or _TAG_RE.fullmatch(recipient) is None or recipient == _ACTOR:
            raise ReloadValidationError("SOURCE_RECIPIENT_INVALID")
        if source_payload.get("family") != _FAMILY or source_payload.get("action_id") != _ACTION:
            raise ReloadValidationError("SOURCE_DECLARE_WAR_IDENTITY_MISMATCH")
        parameters = _source_parameters(source_payload)
        source_after = _source_after(source_payload)
        source_result = _source_contract(source_payload, recipient, parameters)
        public = source_result.get("public_result")
        if not isinstance(public, dict):
            raise ReloadValidationError("SOURCE_RESULT_MISSING")
        report["recipient"] = recipient
        report["parameters"] = parameters
        report["source"] = {
            "path": str(execution_report_path),
            "status": source_payload.get("status"),
            "report_sha256": _hash_file(execution_report_path, maximum=_MAX_METADATA_BYTES),
            "request_id": source_payload.get("request_id"),
            "expected_outcome": source_payload.get("expected_outcome"),
            "expected_date_raw": source_payload.get("expected_date_raw"),
            "session": source_payload.get("session"),
            "build_binding": source_payload.get("build_binding"),
            "after_control": source_after["control"],
            "after_war_state_pair": source_after["war_state_pair"],
            "result_contract": source_result,
        }
        report.update(_installation_binding(installation))
        executable = game_exe().expanduser().resolve(strict=True)
        save_path = _find_save(args.save_name)
        save_record = _hash_file(save_path, maximum=_MAX_SAVE_BYTES)
        save_record.update({"provided": True, "name": args.save_name,
                            "expected_sha256": args.save_sha256.lower(),
                            "sha256_matches_expected": save_record.get("sha256", "").casefold() == args.save_sha256.casefold()})
        report["save"] = save_record
        session = ObserverSession(installation, executable)
        current_session = {"experiment_id": session.experiment_id, "session_id": session.session_id,
                           "pid": session.record.get("pid"), "dll_sha256": session.record.get("dll_sha256")}
        report["session"] = current_session
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "after" / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        current_war = _war_state_pair(probes["war_state"]["snapshot"], recipient)
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            query = _query_declare_war(api, recipient, parameters, artifact / "after" / "query.json")
        report["after"] = {
            "health": health, "control": control, "query": query,
            "war_state_pair": current_war, "probes": _public_probe_records(probes),
        }
        query_checks = _query_contract(query, recipient, parameters)
        source_result_pair = source_result["war_result_pair"]
        reopened_pair = _result_pair(
            source_payload.get("reopened_result", {}).get("result")
            if isinstance(source_payload.get("reopened_result"), dict) else None
        )
        result_pair = _result_pair_consistency(source_payload, public)
        war_comparison = _war_state_comparison(source_after["war_state_pair"], current_war, public, recipient)
        report["comparisons"] = {
            "date_boundary": {
                "source_after_date_raw": source_after["control"].get("date_raw"),
                "reload_date_raw": control.get("date_raw"),
                "expected_date_raw": args.expected_date_raw,
                "same_saved_date": source_after["control"].get("date_raw") == control.get("date_raw") == args.expected_date_raw,
            },
            "query": query_checks,
            "war_state_pair": war_comparison,
            "war_result_pair": result_pair,
        }
        source_binding = source_payload.get("build_binding")
        current_binding = report.get("build_binding")
        source_session = source_payload.get("session")
        source_loaded_dll = source_binding.get("loaded_dll_sha256") if isinstance(source_binding, dict) else None
        if not isinstance(source_loaded_dll, str) and isinstance(source_session, dict):
            source_loaded_dll = source_session.get("dll_sha256")
        current_loaded_dll = current_session.get("dll_sha256")
        checks: dict[str, bool] = {
            "source_execution_report_passed": source_payload.get("status") == "passed",
            "source_execution_checks_passed": isinstance(source_payload.get("checks"), dict)
            and all(value is True for value in source_payload["checks"].values()),
            "source_result_contract_passed": all(source_result["checks"].values()),
            "new_process_ready": health.get("status") == "ready" and health.get("complete") is True,
            "health_date_matches_expected": health.get("date_raw") == args.expected_date_raw,
            "date_matches_expected": control.get("date_raw") == args.expected_date_raw,
            "same_saved_date_boundary": source_after["control"].get("date_raw") == control.get("date_raw") == args.expected_date_raw,
            "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "four_snapshots_complete": _snapshots_complete(probes),
            "declare_war_query_acknowledged": "native_declare_war_query" in session.installation_capabilities(),
            "query_identity_matches_parameters": query_checks["identity"] and query_checks["requested_parameters_preserved"],
            "war_state_pair_supported": war_comparison["recipient_supported"] is True,
            "war_state_pair_matches": war_comparison["pair_match"] is True,
            "war_result_pair_persisted": result_pair["match"] is True,
            "same_immutable_dll": (
                isinstance(current_binding, dict)
                and current_binding.get("installation_matches_build_manifest") is True
                and isinstance(current_loaded_dll, str)
                and _lower(current_loaded_dll) == _lower(current_binding.get("installation_dll_sha256"))
                and isinstance(source_loaded_dll, str)
                and _lower(current_loaded_dll) == source_loaded_dll.casefold()
                and _lower(source_binding.get("installation_dll_sha256") if isinstance(source_binding, dict) else None) == source_loaded_dll.casefold()
            ),
            "new_process_identity": (
                isinstance(source_session, dict) and isinstance(source_session.get("session_id"), str)
                and isinstance(current_session.get("session_id"), str)
                and source_session.get("session_id") != current_session.get("session_id")
            ),
            "save_hash_matches_expected": report["save"].get("sha256_matches_expected") is True,
            "no_execution_request_published": report["execute_call_count"] == 0
            and report["execution_requested"] is False and report["business_submission"] is False
            and report["advance_requested"] is False and report["save_requested"] is False
            and report["installation_requested"] is False,
        }
        if args.expected_war_id is not None:
            checks["expected_war_id_matches"] = public.get("war_id") == args.expected_war_id
        if args.expected_stability_after_raw is not None:
            checks["expected_stability_after_matches"] = public.get("stability_after_raw") == args.expected_stability_after_raw
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_DECLARE_WAR_RELOAD_VALIDATION_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
