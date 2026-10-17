#!/usr/bin/env python3
"""Read-only validation of an inbound Vassalization result after reload.

The reference artifact is the original inbound response report.  This
validator checks its actor/decision/native response binding, hashes the
explicit save path, and queries the fresh process for FRA's relation to the
original proposer.  It never submits a response, creates a proposal,
advances, saves, restarts, or installs a process.
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
from work.run_royal_marriage_execution import _installation_binding  # noqa: E402
from work.run_royal_marriage_execution import _snapshots_complete  # noqa: E402
from work.run_vassalization_execution import (  # noqa: E402
    _ACTIONS,
    _FAMILY,
    _query_pair_complete,
    _relation_pair,
)
from work.run_vassalization_queries import _query_vassalization_pair  # noqa: E402
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _hash_file,
    _new_artifact,
    _read_json,
    _run_snapshots,
    _write_json,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189
_RECIPIENT = "SAV"
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class ReloadValidationError(RuntimeError):
    """A bounded validation failure with a stable report code."""


def _resolve_report(path: Path) -> Path:
    path = path.expanduser().resolve(strict=True)
    if path.is_dir():
        path = (path / "report.json").resolve(strict=True)
    if not path.is_file():
        raise ReloadValidationError(f"REPORT_NOT_FILE:{path}")
    return path


def _all_true(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and all(item is True for item in value.values())


def _source_result(payload: dict[str, object]) -> dict[str, object]:
    """Check the response report without trusting its overall label alone."""

    decision = payload.get("decision")
    expected_state = 2 if decision == "accept" else 1 if decision == "reject" else None
    expected_active = decision == "accept"
    proposal = payload.get("proposal")
    native = payload.get("native_response_event")
    if not isinstance(native, dict):
        poll = payload.get("poll")
        final = poll.get("final") if isinstance(poll, dict) else None
        result = final.get("result") if isinstance(final, dict) else None
        native = result if isinstance(result, dict) else None
    selector = payload.get("selector")
    source_recipient = payload.get("recipient")
    if not isinstance(source_recipient, str) and isinstance(proposal, dict):
        source_recipient = proposal.get("recipient")
    if not isinstance(source_recipient, str) and isinstance(native, dict):
        source_recipient = native.get("recipient")
    checks: dict[str, bool] = {
        "report_status_passed": payload.get("status") == "passed",
        "checks_complete": _all_true(payload.get("checks")),
        "native_response_check_complete": _all_true(payload.get("native_response_check")),
        "public_response_check_complete": _all_true(payload.get("public_response_check")),
        "action_family": payload.get("action_id") == "offer_vassalization"
        and payload.get("family") == _FAMILY,
        "decision_supported": decision in ("accept", "reject"),
        "source_actor_recipient": payload.get("actor") == _RECIPIENT
        and source_recipient == "FRA",
        "proposal_binding": isinstance(proposal, dict)
        and proposal.get("action_id") == "offer_vassalization"
        and proposal.get("family") == _FAMILY
        and proposal.get("actor") == _RECIPIENT
        and proposal.get("recipient") == "FRA"
        and proposal.get("decision_country") == "FRA",
        "response_binding": isinstance(native, dict)
        and native.get("event") == "native_diplomacy_relation_response_result"
        and native.get("action_id") == "offer_vassalization"
        and native.get("family") == _FAMILY
        and native.get("actor") == _RECIPIENT
        and native.get("recipient") == "FRA"
        and native.get("phase") == decision
        and native.get("request_id") == payload.get("request_id")
        and native.get("session_id") == payload.get("session_id")
        and native.get("native_variant") == 1
        and native.get("native_state") == expected_state
        and native.get("pending_removed") is True
        and native.get("vassalization_before") is False
        and native.get("vassalization_after") is expected_active,
        "selector_present": isinstance(selector, dict),
    }
    selector_roles: dict[str, object] = {}
    if isinstance(selector, dict):
        selector_roles = {
            "actor": selector.get("actor"),
            "recipient": selector.get("recipient"),
            "action_id": selector.get("action_id"),
            "actor_is_overlord": selector.get("actor_is_overlord"),
            "actor_is_subject": selector.get("actor_is_subject"),
            "subject_type": selector.get("subject_type"),
            "prestige_raw": selector.get("prestige_raw"),
            "date_raw": (selector.get("session") or {}).get("date_raw")
            if isinstance(selector.get("session"), dict) else None,
        }
        checks["selector_binding"] = (
            selector_roles["actor"] == _ACTOR
            and selector_roles["recipient"] == _RECIPIENT
            and selector_roles["action_id"] == "cancel_vassalization"
        )
        checks["selector_roles"] = (
            selector_roles["actor_is_overlord"] is False
            and selector_roles["actor_is_subject"] is expected_active
            and selector_roles["subject_type"] == ("vassal" if expected_active else None)
        )
    else:
        checks["selector_binding"] = False
        checks["selector_roles"] = False
    return {
        "checks": checks,
        "all": all(checks.values()),
        "decision": decision,
        "expected_active": expected_active,
        "expected_state": expected_state,
        "proposal": proposal,
        "native_response": native,
        "selector": selector,
        "selector_roles": selector_roles,
        "source_session_id": payload.get("session_id"),
        "source_date_raw": native.get("date_raw") if isinstance(native, dict) else None,
    }


def _query_relation(query: object) -> dict[str, object]:
    if not isinstance(query, dict):
        return {}
    relationship = query.get("relationship_state")
    relation = relationship if isinstance(relationship, dict) else {}
    return {
        "vassal_active": query.get("vassal_active", relation.get("vassal_active")),
        "actor_is_overlord": query.get("actor_is_overlord"),
        "actor_is_subject": query.get("actor_is_subject"),
        "subject_type": query.get("subject_type"),
        "complete": relation.get("complete") is True,
    }


def _query_contract(queries: object, expected_date: int,
                    expected_active: bool) -> dict[str, object]:
    checks: dict[str, bool] = {
        "pair_complete": _query_pair_complete(queries),
        "two_actions": isinstance(queries, dict)
        and all(isinstance(queries.get(action), dict) for action in _ACTIONS),
    }
    rows: dict[str, object] = {}
    for action in _ACTIONS:
        query = queries.get(action) if isinstance(queries, dict) else None
        relation = _query_relation(query)
        rows[action] = relation
        if not isinstance(query, dict):
            checks[f"{action}_object"] = False
            checks[f"{action}_binding"] = False
            checks[f"{action}_date"] = False
            checks[f"{action}_relation"] = False
            continue
        checks[f"{action}_object"] = True
        checks[f"{action}_binding"] = all(
            query.get(field) == expected for field, expected in (
                ("action_id", action), ("family", _FAMILY),
                ("actor", _ACTOR), ("recipient", _RECIPIENT),
                ("phase", "initiate"),
            )
        )
        session = query.get("session")
        checks[f"{action}_date"] = isinstance(session, dict) and session.get("date_raw") == expected_date
        checks[f"{action}_relation"] = (
            relation.get("complete") is True
            and relation.get("vassal_active") is expected_active
        )
        checks[f"{action}_roles"] = (
            relation.get("actor_is_overlord") is False
            and relation.get("actor_is_subject") is expected_active
            and relation.get("subject_type") == ("vassal" if expected_active else None)
        )
    return {"checks": checks, "all": all(checks.values()), "rows": rows,
            "relation": _relation_pair(queries)}


def _source_diplomat(value: object) -> object:
    if isinstance(value, dict):
        after = value.get("after")
        if isinstance(after, dict):
            return after.get("diplomat_semantics") or after.get("diplomat", {}).get("semantics") \
                if isinstance(after.get("diplomat"), dict) else after.get("diplomat_semantics")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="新进程的 installation.json")
    parser.add_argument("--reference-artifact", type=Path, required=True,
                        help="原始 run_alliance_inbound_response report 或其目录")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--save-path", type=Path, required=True)
    parser.add_argument("--expected-save-sha256", required=True)
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent)
    report: dict[str, object] = {
        "validator": "validate_vassalization_inbound_reload.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_vassalization_inbound_reload",
        "installation": str(installation),
        "reference_artifact": str(args.reference_artifact),
        "expected_date_raw": args.expected_date_raw,
        "save_path": str(args.save_path),
        "expected_save_sha256": str(args.expected_save_sha256).lower(),
        "artifact": str(artifact),
        "execute_call_count": 0,
        "execution_requested": False,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "installation_requested": False,
        "checks": {},
    }
    try:
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
            raise ReloadValidationError("EXPECTED_DATE_RAW_INVALID")
        if _SHA256_RE.fullmatch(args.expected_save_sha256) is None:
            raise ReloadValidationError("EXPECTED_SAVE_SHA256_INVALID")
        reference_path = _resolve_report(args.reference_artifact)
        source_payload = _read_json(reference_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(source_payload, dict):
            raise ReloadValidationError("REFERENCE_REPORT_NOT_OBJECT")
        source = _source_result(source_payload)
        report["source"] = {
            "path": str(reference_path),
            "sha256": _hash_file(reference_path, maximum=_MAX_METADATA_BYTES),
            "summary": source,
            "installation": source_payload.get("installation"),
            "manifest": source_payload.get("manifest"),
            "session_id": source_payload.get("session_id"),
        }
        if not source["all"]:
            raise ReloadValidationError("REFERENCE_RESPONSE_CONTRACT_FAILED")
        if source["source_date_raw"] != args.expected_date_raw:
            raise ReloadValidationError("REFERENCE_DATE_MISMATCH")

        save_path = args.save_path.expanduser().resolve(strict=True)
        save = _hash_file(save_path, maximum=_MAX_SAVE_BYTES)
        save["expected_sha256"] = args.expected_save_sha256.lower()
        save["sha256_matches_expected"] = (
            save.get("sha256", "").casefold() == args.expected_save_sha256.casefold()
        )
        report["save"] = save

        binding = _installation_binding(installation)
        report.update(binding)
        executable = game_exe().expanduser().resolve(strict=True)
        report["runtime"] = {"game_executable": str(executable),
                              "bytes": executable.stat().st_size,
                              "source_binding": "local_config.game_exe"}
        session = ObserverSession(installation, executable)
        current_session = {"experiment_id": session.experiment_id,
                           "session_id": session.session_id,
                           "pid": session.record.get("pid"),
                           "dll_sha256": session.record.get("dll_sha256")}
        report["session"] = current_session
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "probes")
        control_snapshot = probes.get("control_state", {}).get("snapshot")
        control = _control_summary(control_snapshot) if isinstance(control_snapshot, dict) else {}
        diplomat_snapshot = probes.get("diplomats", {}).get("snapshot")
        try:
            diplomat = _diplomat_semantics(diplomat_snapshot) if isinstance(diplomat_snapshot, dict) else None
            diplomat_error = None
        except Exception as error:  # preserve a bounded diagnostic in the report
            diplomat = None
            diplomat_error = {"type": type(error).__name__, "message": str(error)}
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            queries = _query_vassalization_pair(api, _RECIPIENT,
                                                artifact / "queries.json")
        query = _query_contract(queries, args.expected_date_raw,
                                bool(source["expected_active"]))
        report["after"] = {
            "health": health,
            "control": control,
            "queries": queries,
            "query_contract": query,
            "diplomat_semantics": diplomat,
            "diplomat_semantics_error": diplomat_error,
            "snapshots": {
                name: {key: item.get(key) for key in (
                    "status", "snapshot_path", "snapshot_completeness", "snapshot_sha256")}
                for name, item in probes.items()
            },
        }
        source_roles = source["selector_roles"] if isinstance(source["selector_roles"], dict) else {}
        source_diplomat = _source_diplomat(source_payload)
        current_cancel = queries.get("cancel_vassalization") if isinstance(queries, dict) else None
        current_prestige = current_cancel.get("prestige_raw") if isinstance(current_cancel, dict) else None
        source_prestige = source_roles.get("prestige_raw")
        report["comparisons"] = {
            "source_session_id": source["source_session_id"],
            "reload_session_id": session.session_id,
            "new_session": session.session_id != source["source_session_id"],
            "date_boundary": {
                "source_response_date_raw": source["source_date_raw"],
                "reload_health_date_raw": health.get("date_raw"),
                "reload_control_date_raw": control.get("date_raw"),
                "expected_date_raw": args.expected_date_raw,
            },
            "source_selector_roles": source_roles,
            "reload_relation": query.get("relation"),
            "prestige": {
                "source_selector_raw": source_prestige,
                "reload_cancel_raw": current_prestige,
                "same_when_available": (
                    source_prestige is None or current_prestige == source_prestige
                ),
            },
            "diplomat_semantics": {
                "source_present": isinstance(source_diplomat, list),
                "reload_present": isinstance(diplomat, list),
                "same_when_saved": (
                    source_diplomat is None or diplomat == source_diplomat
                ),
            },
        }
        checks = dict(source["checks"])
        checks.update({
            "source_response_contract": source["all"],
            "new_process_ready": health.get("status") == "ready" and health.get("complete") is True,
            "health_date_matches": health.get("date_raw") == args.expected_date_raw,
            "control_date_matches": control.get("date_raw") == args.expected_date_raw,
            "player_slot_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "four_snapshots_complete": _snapshots_complete(probes),
            "query_contract_complete": query["all"],
            "expected_relation_and_roles": query["all"],
            "new_process_identity": session.session_id != source["source_session_id"],
            "save_hash_matches_expected": save.get("sha256_matches_expected") is True,
            "same_selector_prestige_when_present": report["comparisons"]["prestige"]["same_when_available"],
            "same_saved_diplomat_semantics_when_present": report["comparisons"]["diplomat_semantics"]["same_when_saved"],
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
                and report["advance_requested"] is False
                and report["save_requested"] is False
                and report["installation_requested"] is False
            ),
        })
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_VASSALIZATION_INBOUND_RELOAD_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
