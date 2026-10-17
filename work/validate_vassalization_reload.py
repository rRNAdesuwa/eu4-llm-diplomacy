"""Validate one Vassalization result after a read-only save reload.

The game and the observer installation must already be running when this
validator is called.  The validator reads the supplied save hash, starts no
process, and performs only the two native Vassalization queries.  It never
publishes, retries, advances, saves, or installs a diplomacy operation.

The execution artifact is the source of truth for the actor, recipient,
operation family, terminal native result, after relation, and after diplomat
task semantics. The reload is compared at the same paused date, including
diplomat availability and the saved start and return dates. Process addresses
are excluded because the new process reconstructs the objects.
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
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _query_is_complete,
    _snapshots_complete,
)
from work.run_vassalization_execution import (  # noqa: E402
    _ACTIONS,
    _FAMILY,
    _QUERY_CAPABILITY,
    _query_vassalization_pair,
    _query_pair_complete,
    _relation_pair,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _find_save,
    _hash_file,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_DIPLOMAT_DATE_FIELDS = frozenset()
_DIPLOMAT_SEMANTIC_FIELDS = (
    "raw_id_44",
    "active_raw_18",
    "raw_actor_80",
    "raw_recipient_88",
    "raw_action_type_a8",
    "raw_2c",
    "raw_20",
    "raw_24",
)


class ReloadValidationError(RuntimeError):
    """An expected bounded validation stop."""


def _resolve_report(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise ReloadValidationError(f"EXECUTION_REPORT_NOT_FILE:{resolved}")
    return resolved


def _source_diplomat_semantics(after: dict[str, object]) -> object:
    value = after.get("diplomat_semantics")
    if value is None and isinstance(after.get("diplomat"), dict):
        value = after["diplomat"].get("semantics")
    return value


def _compact_diplomat_semantics(value: object) -> list[dict[str, object]] | None:
    """Compare saved task identity, availability and dates without addresses."""

    if not isinstance(value, list):
        return None
    result: list[dict[str, object]] = []
    for country in value:
        if not isinstance(country, dict) or not isinstance(country.get("countrytag"), str):
            return None
        entries = country.get("entries")
        if not isinstance(entries, list):
            return None
        compact_entries: list[dict[str, object]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            compact_entries.append({
                field: entry.get(field) for field in _DIPLOMAT_SEMANTIC_FIELDS
            })
        result.append({
            "countrytag": country["countrytag"],
            "available_count": country.get("available_count"),
            "entries": compact_entries,
        })
    result.sort(key=lambda item: str(item["countrytag"]))
    return result


def _relation_public(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "vassal_active": None,
            "actor_is_overlord": None,
            "actor_is_subject": None,
            "subject_type": None,
        }
    return {
        field: value.get(field)
        for field in (
            "vassal_active",
            "actor_is_overlord",
            "actor_is_subject",
            "subject_type",
        )
    }


def _relation_comparison(source: object, current: object) -> dict[str, object]:
    """Compare both action rows and the aggregate relation state."""

    source_dict = source if isinstance(source, dict) else {}
    current_dict = current if isinstance(current, dict) else {}
    by_action: dict[str, object] = {}
    action_matches: list[bool] = []
    for action_id in _ACTIONS:
        source_state = (
            source_dict.get("by_action", {}).get(action_id)
            if isinstance(source_dict.get("by_action"), dict)
            else None
        )
        current_state = (
            current_dict.get("by_action", {}).get(action_id)
            if isinstance(current_dict.get("by_action"), dict)
            else None
        )
        if not isinstance(source_state, dict):
            source_state = {}
        if not isinstance(current_state, dict):
            current_state = {}
        source_public = _relation_public(source_state)
        current_public = _relation_public(current_state)
        equal = (
            source_state.get("complete") is True
            and current_state.get("complete") is True
            and source_state.get("public_fields_complete") is True
            and current_state.get("public_fields_complete") is True
            and source_public == current_public
        )
        action_matches.append(equal)
        by_action[action_id] = {
            "source": source_public,
            "reload": current_public,
            "match": equal,
            "source_complete": source_state.get("complete") is True,
            "reload_complete": current_state.get("complete") is True,
        }
    source_aggregate = _relation_public(source_dict)
    current_aggregate = _relation_public(current_dict)
    aggregate_match = source_aggregate == current_aggregate
    return {
        "source": source_aggregate,
        "reload": current_aggregate,
        "aggregate_match": aggregate_match,
        "by_action": by_action,
        "all_action_rows_match": all(action_matches),
        "match": aggregate_match and all(action_matches),
    }


def _query_identity_match(source_queries: object, current_queries: object,
                          recipient: str) -> bool:
    if not isinstance(source_queries, dict) or not isinstance(current_queries, dict):
        return False
    for action_id in _ACTIONS:
        source = source_queries.get(action_id)
        current = current_queries.get(action_id)
        if not isinstance(source, dict) or not isinstance(current, dict):
            return False
        expected = {
            "action_id": action_id,
            "actor": _ACTOR,
            "recipient": recipient,
            "family": _FAMILY,
            "phase": "initiate",
        }
        if any(source.get(key) != value or current.get(key) != value
               for key, value in expected.items()):
            return False
    return True


def _public_result(payload: dict[str, object]) -> dict[str, object] | None:
    """Find the terminal native result without treating a pending submission as final."""

    candidates: list[object] = []
    reopened = payload.get("reopened_result")
    if isinstance(reopened, dict):
        candidates.append(reopened.get("result"))
    result_checks = payload.get("result_checks")
    if isinstance(result_checks, dict):
        candidates.append(result_checks.get("public_result"))
    poll = payload.get("poll")
    if isinstance(poll, dict):
        final = poll.get("final")
        if isinstance(final, dict):
            candidates.append(final.get("result"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def _source_result_contract(payload: dict[str, object], recipient: str,
                            expected_active: bool) -> dict[str, object]:
    action_id = payload.get("action_id")
    expected_outcome = payload.get("expected_outcome")
    public = _public_result(payload)
    result_checks = payload.get("result_checks")
    checks: dict[str, bool] = {
        "report_status_passed": payload.get("status") == "passed",
        "result_checks_all": (
            isinstance(result_checks, dict) and result_checks.get("all") is True
        ),
        "action_supported": action_id in _ACTIONS,
        "outcome_supported": (
            (action_id == "offer_vassalization" and expected_outcome in ("accepted", "rejected"))
            or (action_id == "cancel_vassalization" and expected_outcome == "executed")
        ),
        "terminal_result_present": isinstance(public, dict),
    }
    if not isinstance(public, dict):
        checks.update({
            "binding": False,
            "relation": False,
            "native": False,
            "proof": False,
            "event": False,
            "prestige": action_id != "cancel_vassalization",
        })
        return {"checks": checks, "public_result": None, "prestige": {}}

    checks["binding"] = all(
        public.get(field) == expected
        for field, expected in (
            ("action_id", action_id),
            ("actor", _ACTOR),
            ("recipient", recipient),
            ("family", _FAMILY),
            ("phase", "initiate"),
        )
    )
    checks["relation"] = public.get("vassalization_after") is expected_active
    if action_id == "offer_vassalization":
        expected_state = 2 if expected_outcome == "accepted" else 1
        checks["native"] = (
            public.get("native_variant") == 1
            and public.get("native_state") == expected_state
            and public.get("outcome") == expected_outcome
        )
        checks["proof"] = (
            public.get("response_verified") is True
            and public.get("request_binding_verified") is True
        )
        checks["event"] = public.get("event") == "native_diplomacy_relation_response_result"
        checks["prestige"] = True
    else:
        checks["native"] = (
            public.get("native_variant") == 0
            and public.get("native_state") == 0
            and public.get("outcome") == "executed"
        )
        checks["proof"] = (
            public.get("execution_verified") is True
            and public.get("request_binding_verified") is True
        )
        checks["event"] = public.get("event") == "native_diplomacy_relation_execution_result"
        before = public.get("prestige_before_raw")
        after = public.get("prestige_after_raw")
        scale = public.get("prestige_scale", public.get("scale1000"))
        delta = public.get("prestige_delta_raw")
        checks["prestige"] = (
            type(before) is int and type(after) is int
            and type(scale) is int and scale == 1000
            and type(delta) is int and delta == after - before
        )
    checks["all"] = all(checks.values())
    return {
        "checks": checks,
        "public_result": public,
        "prestige": {
            "before_raw": public.get("prestige_before_raw"),
            "after_raw": public.get("prestige_after_raw"),
            "scale": public.get("prestige_scale", public.get("scale1000")),
            "delta_raw": public.get("prestige_delta_raw"),
        },
    }


def _prestige_reload_check(source_payload: dict[str, object],
                           source_after_queries: object,
                           current_queries: object) -> dict[str, object]:
    """Check Cancel's native prestige contract at the same save boundary."""

    source_result = _source_result_contract(
        source_payload,
        str(source_payload.get("recipient")),
        expected_active=False,
    )
    source_prestige = source_result.get("prestige")
    source_cancel = (
        source_after_queries.get("cancel_vassalization")
        if isinstance(source_after_queries, dict) else None
    )
    current_cancel = (
        current_queries.get("cancel_vassalization")
        if isinstance(current_queries, dict) else None
    )
    current_items = current_cancel.get("costs", {}).get("items", []) \
        if isinstance(current_cancel, dict) and isinstance(current_cancel.get("costs"), dict) else []
    current_cost = next(
        (item for item in current_items
         if isinstance(item, dict) and item.get("resource") == "prestige"),
        None,
    )
    source_items = source_cancel.get("costs", {}).get("items", []) \
        if isinstance(source_cancel, dict) and isinstance(source_cancel.get("costs"), dict) else []
    source_cost = next(
        (item for item in source_items
         if isinstance(item, dict) and item.get("resource") == "prestige"),
        None,
    )
    current_delta = current_cancel.get("cancel_prestige_delta_raw") \
        if isinstance(current_cancel, dict) else None
    source_delta = source_cancel.get("cancel_prestige_delta_raw") \
        if isinstance(source_cancel, dict) else None
    checks = {
        "source_result_prestige_verified": (
            isinstance(source_result.get("checks"), dict)
            and source_result["checks"].get("prestige") is True
        ),
        "reload_cost_verified": (
            isinstance(current_cancel, dict)
            and current_cancel.get("cancel_prestige_cost_verified") is True
            and type(current_delta) is int
            and current_cancel.get("prestige_scale") == 1000
        ),
        "reload_cost_item_verified": (
            isinstance(current_cost, dict)
            and current_cost.get("resource") == "prestige"
            and current_cost.get("amount_raw") == abs(current_delta)
            if type(current_delta) is int else False
        ),
        "query_cost_same_as_execution_after": (
            type(source_delta) is int and type(current_delta) is int
            and source_delta == current_delta
        ),
        "query_prestige_after_same_as_execution": (
            isinstance(source_cancel, dict)
            and isinstance(current_cancel, dict)
            and type(source_cancel.get("prestige_raw")) is int
            and type(current_cancel.get("prestige_raw")) is int
            and source_cancel.get("prestige_raw") == current_cancel.get("prestige_raw")
        ),
        "result_after_matches_query": (
            type(source_prestige.get("after_raw")) is int
            and isinstance(current_cancel, dict)
            and type(current_cancel.get("prestige_raw")) is int
            and source_prestige.get("after_raw") == current_cancel.get("prestige_raw")
        ),
        "cost_item_same_at_save_boundary": (
            isinstance(source_cost, dict) and isinstance(current_cost, dict)
            and source_cost.get("amount_raw") == current_cost.get("amount_raw")
            and source_cost.get("scale") == current_cost.get("scale")
        ),
    }
    return {
        "checks": checks,
        "source": source_prestige,
        "source_query": source_cancel,
        "reload_query": current_cancel,
    }


def _source_after(payload: dict[str, object]) -> dict[str, object]:
    after = payload.get("after")
    if not isinstance(after, dict):
        raise ReloadValidationError("EXECUTION_AFTER_MISSING")
    queries = after.get("queries")
    if not isinstance(queries, dict):
        raise ReloadValidationError("EXECUTION_AFTER_QUERIES_MISSING")
    relation = _relation_pair(queries)
    control = after.get("control") if isinstance(after.get("control"), dict) else {}
    semantics = _source_diplomat_semantics(after)
    return {
        "control": control,
        "queries": queries,
        "relation": relation,
        "diplomat_semantics": semantics,
        "diplomat_semantics_compact": _compact_diplomat_semantics(semantics),
        "baseline": after.get("baseline"),
    }


def _lower_hash(value: object) -> str | None:
    return value.casefold() if isinstance(value, str) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="new process installation.json")
    parser.add_argument("--execution-artifact", type=Path, required=True,
                        help="passed vassalization execution report or artifact directory")
    parser.add_argument("--save-name", required=True,
                        help="save basename in the configured EU4 save directory")
    parser.add_argument("--save-sha256", required=True,
                        help="expected SHA-256 for --save-name")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--expected-active", choices=("active", "absent"), required=True)
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    execution_report_path = args.execution_artifact.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "vassalization-reload")
    expected_active = args.expected_active == "active"
    report: dict[str, object] = {
        "validator": "validate_vassalization_reload.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_vassalization_reload_validation",
        "installation": str(installation),
        "execution_artifact": str(execution_report_path),
        "actor": _ACTOR,
        "family": _FAMILY,
        "expected_date_raw": args.expected_date_raw,
        "expected_active": args.expected_active,
        "save_name": args.save_name,
        "expected_save_sha256": args.save_sha256.lower(),
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
            raise ReloadValidationError("EXPECTED_DATE_RAW_MUST_BE_INT")
        if _SHA256_RE.fullmatch(args.save_sha256) is None:
            raise ReloadValidationError("EXPECTED_SAVE_SHA256_INVALID")
        execution_report_path = _resolve_report(execution_report_path)
        source_payload = _read_json(execution_report_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(source_payload, dict):
            raise ReloadValidationError("EXECUTION_REPORT_NOT_OBJECT")
        source_after = _source_after(source_payload)
        recipient = source_payload.get("recipient")
        if not isinstance(recipient, str) or _TAG_RE.fullmatch(recipient) is None or recipient == _ACTOR:
            raise ReloadValidationError("SOURCE_RECIPIENT_INVALID")
        if source_payload.get("family") != _FAMILY:
            raise ReloadValidationError("SOURCE_FAMILY_MISMATCH")
        report["recipient"] = recipient
        report["action_id"] = source_payload.get("action_id")
        report["source"] = {
            "path": str(execution_report_path),
            "report_sha256": _hash_file(execution_report_path, maximum=_MAX_METADATA_BYTES),
            "status": source_payload.get("status"),
            "action_id": source_payload.get("action_id"),
            "expected_outcome": source_payload.get("expected_outcome"),
            "expected_date_raw": source_payload.get("expected_date_raw"),
            "actor": source_payload.get("actor"),
            "recipient": recipient,
            "family": source_payload.get("family"),
            "session": source_payload.get("session"),
            "build_binding": source_payload.get("build_binding"),
            "after_control": source_after["control"],
            "after_relation": source_after["relation"],
            "after_diplomat_semantics": source_after["diplomat_semantics"],
            "after_diplomat_semantics_compact": source_after["diplomat_semantics_compact"],
        }
        source_result = _source_result_contract(source_payload, recipient, expected_active)
        report["source"]["result_contract"] = source_result

        report.update(_installation_binding(installation))
        executable = game_exe().expanduser().resolve(strict=True)
        report["runtime"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
        save_path = _find_save(args.save_name)
        save_record = _hash_file(save_path, maximum=_MAX_SAVE_BYTES)
        save_record["provided"] = True
        save_record["name"] = args.save_name
        save_record["expected_sha256"] = args.save_sha256.lower()
        save_record["sha256_matches_expected"] = (
            save_record.get("sha256", "").casefold() == args.save_sha256.casefold()
        )
        report["save"] = save_record

        session = ObserverSession(installation, executable)
        current_session = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        report["session"] = current_session
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "after" / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        try:
            semantics = _diplomat_semantics(probes["diplomats"]["snapshot"])
            semantics_error = None
        except Exception as error:
            semantics = None
            semantics_error = {"type": type(error).__name__, "message": str(error)}
        with DurableJournal(
            artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            queries = _query_vassalization_pair(
                api, recipient, artifact / "after" / "queries.json"
            )
        relation = _relation_pair(queries)
        compact_semantics = _compact_diplomat_semantics(semantics)
        report["after"] = {
            "health": health,
            "control": control,
            "queries": queries,
            "relation": relation,
            "diplomat_semantics": semantics,
            "diplomat_semantics_compact": compact_semantics,
            "diplomat_semantics_error": semantics_error,
            "probes": {
                name: {
                    "status": item.get("status"),
                    "snapshot_path": item.get("snapshot_path"),
                    "snapshot_completeness": item.get("snapshot_completeness"),
                    "snapshot_sha256": item.get("snapshot_sha256"),
                }
                for name, item in probes.items()
            },
        }
        capabilities = session.installation_capabilities()
        source_session = source_payload.get("session")
        source_binding = source_payload.get("build_binding")
        current_binding = report.get("build_binding")
        source_loaded_dll = (
            source_binding.get("loaded_dll_sha256")
            if isinstance(source_binding, dict) else None
        )
        if not isinstance(source_loaded_dll, str) and isinstance(source_session, dict):
            source_loaded_dll = source_session.get("dll_sha256")
        current_loaded_dll = current_session.get("dll_sha256")
        source_after_control = source_after["control"]
        source_relation = source_after["relation"]
        source_queries = source_after["queries"]
        source_semantics = source_after["diplomat_semantics"]
        relation_comparison = _relation_comparison(source_relation, relation)
        diplomat_comparison = {
            "available_count_ignored": False,
            "date_fields_ignored": sorted(_DIPLOMAT_DATE_FIELDS),
            "source_compact": source_after["diplomat_semantics_compact"],
            "reload_compact": compact_semantics,
            "semantic_fields_compared": list(_DIPLOMAT_SEMANTIC_FIELDS),
            "match": (
                isinstance(source_after["diplomat_semantics_compact"], list)
                and isinstance(compact_semantics, list)
                and source_after["diplomat_semantics_compact"] == compact_semantics
            ),
        }
        report["comparisons"] = {
            "query_identity": _query_identity_match(source_queries, queries, recipient),
            "relation": relation_comparison,
            "diplomat_semantics": diplomat_comparison,
            "date_boundary": {
                "source_after_date_raw": source_after_control.get("date_raw"),
                "reload_date_raw": control.get("date_raw"),
                "expected_date_raw": args.expected_date_raw,
                "same_saved_date": source_after_control.get("date_raw") == control.get("date_raw") == args.expected_date_raw,
            },
        }
        prestige = None
        if source_payload.get("action_id") == "cancel_vassalization":
            prestige = _prestige_reload_check(source_payload, source_queries, queries)
            report["prestige"] = prestige

        source_checks = source_payload.get("checks")
        source_checks_passed = isinstance(source_checks, dict) and all(
            value is True for value in source_checks.values()
        )
        source_build = source_binding if isinstance(source_binding, dict) else {}
        current_build = current_binding if isinstance(current_binding, dict) else {}
        checks: dict[str, bool] = {
            "source_execution_report_passed": source_payload.get("status") == "passed",
            "source_execution_checks_passed": source_checks_passed,
            "source_result_contract_passed": all(source_result["checks"].values()),
            "new_process_ready": (
                health.get("status") == "ready" and health.get("complete") is True
            ),
            "health_date_matches_expected": health.get("date_raw") == args.expected_date_raw,
            "date_matches_expected": control.get("date_raw") == args.expected_date_raw,
            "same_saved_date_boundary": (
                source_after_control.get("date_raw") == control.get("date_raw") == args.expected_date_raw
            ),
            "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "four_snapshots_complete": _snapshots_complete(probes),
            "query_pair_complete": _query_pair_complete(queries),
            "query_relation_consistent": (
                relation.get("consistent") is True
                and relation.get("roles_consistent") is True
                and relation.get("subject_type_consistent") is True
                and relation.get("public_fields_complete") is True
            ),
            "expected_relationship_state": relation.get("vassal_active") is expected_active,
            "query_result_identity_matches_execution_after": (
                report["comparisons"].get("query_identity") is True
            ),
            "relation_roles_and_type_match_execution_after": (
                relation_comparison.get("match") is True
            ),
            "diplomat_task_semantics_match_execution_after": (
                diplomat_comparison.get("match") is True
            ),
            "vassalization_query_acknowledged": _QUERY_CAPABILITY in capabilities,
            "same_immutable_dll": (
                isinstance(current_build, dict)
                and current_build.get("installation_matches_build_manifest") is True
                and _lower_hash(current_build.get("loaded_dll_sha256"))
                == _lower_hash(current_build.get("installation_dll_sha256"))
                and isinstance(source_loaded_dll, str)
                and _lower_hash(current_build.get("loaded_dll_sha256")) == source_loaded_dll.casefold()
                and _lower_hash(source_build.get("installation_dll_sha256")) == source_loaded_dll.casefold()
            ),
            "new_process_identity": (
                isinstance(source_session, dict)
                and isinstance(source_session.get("session_id"), str)
                and bool(source_session.get("session_id"))
                and isinstance(current_session.get("session_id"), str)
                and bool(current_session.get("session_id"))
                and current_session.get("session_id") != source_session.get("session_id")
            ),
            "save_hash_matches_expected": report["save"].get("sha256_matches_expected") is True,
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
                and report["advance_requested"] is False
                and report["save_requested"] is False
                and report["installation_requested"] is False
            ),
        }
        if source_payload.get("action_id") == "cancel_vassalization":
            prestige_checks = prestige.get("checks") if isinstance(prestige, dict) else {}
            if isinstance(prestige_checks, dict):
                checks.update({
                    "cancel_prestige_contract_verified": all(
                        value is True for value in prestige_checks.values()
                    ),
                })
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_VASSALIZATION_RELOAD_VALIDATION_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
