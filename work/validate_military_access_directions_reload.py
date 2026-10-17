"""Read-only four-direction Military Access validation after a fresh reload.

The validator observes the paused POR session and queries both Military Access
selectors for each requested actor/recipient direction.  It never publishes
an action, advances time, saves, or installs a module.  The default direction
set is the R32-C/D acceptance set:

* FRA -> SAV: absent
* SAV -> FRA: absent
* CAS -> FRA: active
* FRA -> CAS: absent

The relation is read from ``relationship_state`` for the original direction;
diplomat task state is recorded as context and is never used as relation
evidence.
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
from work.run_military_access_execution import (  # noqa: E402
    _ACTIONS,
    _FAMILY,
    _query_pair_complete,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _query_is_complete,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _hash_file,
    _read_json,
    _run_snapshots,
)


_PLAYER_SLOT = 189  # POR in the controlled experiment.
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_DIRECTION_RE = re.compile(r"([A-Z]{3})->([A-Z]{3})=(active|absent)\Z")
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_DEFAULT_DIRECTIONS: tuple[tuple[str, str, str], ...] = (
    ("FRA", "SAV", "absent"),
    ("SAV", "FRA", "absent"),
    ("CAS", "FRA", "active"),
    ("FRA", "CAS", "absent"),
)


class ReloadValidationError(RuntimeError):
    """An expected bounded validation stop."""


def _parse_direction(value: str) -> tuple[str, str, str]:
    match = _DIRECTION_RE.fullmatch(value.strip().upper())
    if match is None:
        raise argparse.ArgumentTypeError(
            "direction must be ACTOR->RECIPIENT=active|absent"
        )
    actor, recipient, expected = match.groups()
    if actor == recipient:
        raise argparse.ArgumentTypeError("actor and recipient must differ")
    return actor, recipient, expected


def _relation_state(inspection: object) -> dict[str, object]:
    relationship = inspection.get("relationship_state") if isinstance(inspection, dict) else None
    active = relationship.get("military_access_active") if isinstance(relationship, dict) else None
    complete = relationship.get("complete") if isinstance(relationship, dict) else False
    verified = inspection.get("military_access_state_verified") if isinstance(inspection, dict) else None
    if not isinstance(verified, bool) and isinstance(relationship, dict):
        verified = relationship.get("state_verified")
    return {
        "military_access_active": active if type(active) is bool else None,
        "complete": complete is True and type(active) is bool,
        "state_verified": verified if type(verified) is bool else None,
        "source": "relationship_state",
    }


def _query_direction_pair(
    api: DiplomacyTools,
    actor: str,
    recipient: str,
    destination: Path,
) -> dict[str, dict[str, object]]:
    """Inspect both actions for one preserved actor/recipient orientation."""

    result: dict[str, dict[str, object]] = {}
    for action_id in _ACTIONS:
        try:
            inspection = api.inspect_diplomatic_action(
                action_id,
                actor,
                recipient,
                phase="initiate",
                parameters={},
            )
            result[action_id] = inspection if isinstance(inspection, dict) else {
                "status": "unknown",
                "error": "INSPECTION_NOT_OBJECT",
            }
        except Exception as error:
            result[action_id] = {
                "status": "unknown",
                "error_type": type(error).__name__,
                "error": str(error),
            }
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, result)
    return result


def _relation_pair(queries: object, actor: str, recipient: str) -> dict[str, object]:
    if not isinstance(queries, dict):
        return {
            "actor": actor,
            "recipient": recipient,
            "military_access_active": None,
            "complete": False,
            "consistent": False,
            "state_verified": None,
            "source": "relationship_state",
            "by_action": {},
        }
    states = {
        action_id: _relation_state(queries.get(action_id))
        for action_id in _ACTIONS
    }
    values = [states[action_id].get("military_access_active") for action_id in _ACTIONS]
    complete = all(states[action_id].get("complete") is True for action_id in _ACTIONS)
    consistent = complete and values[0] is values[1]
    verified = [states[action_id].get("state_verified") for action_id in _ACTIONS]
    return {
        "actor": actor,
        "recipient": recipient,
        "military_access_active": values[0] if consistent else None,
        "complete": complete,
        "consistent": consistent,
        "state_verified": verified[0] if verified[0] is verified[1] else None,
        "source": "relationship_state",
        "by_action": states,
    }


def _query_summary(
    queries: dict[str, dict[str, object]],
    actor: str,
    recipient: str,
    expected: str,
) -> dict[str, object]:
    relation = _relation_pair(queries, actor, recipient)
    return {
        "actor": actor,
        "recipient": recipient,
        "expected": expected,
        "relation": relation,
        "query_complete": _query_pair_complete(queries),
        "actions": {
            action_id: {
                "action_id": query.get("action_id") if isinstance(query, dict) else None,
                "actor": query.get("actor") if isinstance(query, dict) else None,
                "recipient": query.get("recipient") if isinstance(query, dict) else None,
                "phase": query.get("phase") if isinstance(query, dict) else None,
                "visibility": query.get("visibility") if isinstance(query, dict) else None,
                "legality": query.get("legality") if isinstance(query, dict) else None,
                "relationship_state": query.get("relationship_state") if isinstance(query, dict) else None,
                "query_complete": _query_is_complete(query, action_id),
            }
            for action_id, query in queries.items()
        },
    }


def _save_record(path: Path | None) -> dict[str, object]:
    if path is None:
        return {"provided": False}
    resolved = path.expanduser().resolve(strict=True)
    return {"provided": True, **_hash_file(resolved, maximum=_MAX_SAVE_BYTES)}


def _reference_summary(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve(strict=True)
    report_path = resolved if resolved.is_file() else resolved / "report.json"
    payload = _read_json(report_path)
    if not isinstance(payload, dict):
        raise ReloadValidationError("REFERENCE_REPORT_NOT_OBJECT")
    return {
        "path": str(report_path),
        "status": payload.get("status"),
        "expected_date_raw": payload.get("expected_date_raw"),
        "after_control": (
            payload.get("after", {}).get("control")
            if isinstance(payload.get("after"), dict)
            else None
        ),
        "after_diplomat_semantics": (
            payload.get("after", {}).get("diplomat_semantics")
            if isinstance(payload.get("after"), dict)
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument(
        "--direction",
        action="append",
        type=_parse_direction,
        metavar="ACTOR->RECIPIENT=active|absent",
        help="repeatable direction expectation; defaults to the four R32-C/D directions",
    )
    parser.add_argument("--save-path", type=Path)
    parser.add_argument("--reference-artifact", type=Path)
    args = parser.parse_args(argv)

    directions = tuple(args.direction) if args.direction else _DEFAULT_DIRECTIONS
    if len(set(directions)) != len(directions):
        parser.error("duplicate --direction")
    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "military-access-directions-reload")
    report: dict[str, object] = {
        "validator": "validate_military_access_directions_reload.py",
        "status": "running",
        "mode": "read_only_reload_validation",
        "installation": str(installation),
        "family": _FAMILY,
        "actions": list(_ACTIONS),
        "directions": [
            {"actor": actor, "recipient": recipient, "expected": expected}
            for actor, recipient, expected in directions
        ],
        "expected_date_raw": args.expected_date_raw,
        "save_path": str(args.save_path.expanduser().resolve()) if args.save_path else None,
        "reference_artifact": str(args.reference_artifact.expanduser().resolve())
        if args.reference_artifact else None,
        "artifact": str(artifact),
        "execute_call_count": 0,
        "execution_requested": False,
        "business_submission": False,
        "checks": {},
    }
    try:
        for actor, recipient, _expected in directions:
            if not _TAG_RE.fullmatch(actor) or not _TAG_RE.fullmatch(recipient):
                raise ReloadValidationError("COUNTRY_TAG_INVALID")
        installation = installation.resolve(strict=True)
        report.update(_installation_binding(installation))
        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
        report["save"] = _save_record(args.save_path)
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
            semantics = _diplomat_semantics(probes["diplomats"]["snapshot"])
            semantics_error = None
        except Exception as error:
            semantics = None
            semantics_error = {"type": type(error).__name__, "message": str(error)}

        query_results: dict[str, dict[str, dict[str, object]]] = {}
        query_summaries: list[dict[str, object]] = []
        with DurableJournal(
            artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            for actor, recipient, expected in directions:
                key = f"{actor}->{recipient}"
                queries = _query_direction_pair(
                    api,
                    actor,
                    recipient,
                    artifact / "after" / "queries" / f"{actor}-{recipient}.json",
                )
                query_results[key] = queries
                query_summaries.append(_query_summary(queries, actor, recipient, expected))
        _write_json(artifact / "after" / "queries.json", query_results)
        relation_checks = {
            f"{item['actor']}->{item['recipient']}": item
            for item in query_summaries
        }
        report["after"] = {
            "health": health,
            "control": control,
            "queries": query_results,
            "directions": relation_checks,
            "diplomat_semantics": semantics,
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
        report["reference"] = _reference_summary(args.reference_artifact)
        capabilities = session.installation_capabilities()
        build_binding = report.get("build_binding")
        direction_checks = {}
        for item in query_summaries:
            actor = item["actor"]
            recipient = item["recipient"]
            key = f"{actor}->{recipient}"
            expected_active = item["expected"] == "active"
            relation = item["relation"]
            action_checks = all(
                info.get("query_complete") is True
                and info.get("action_id") in _ACTIONS
                and info.get("actor") == actor
                and info.get("recipient") == recipient
                and info.get("phase") == "initiate"
                for info in item["actions"].values()
            )
            direction_checks[key] = {
                "both_queries_complete": item["query_complete"] is True,
                "action_context_exact": action_checks,
                "relationship_state_complete": relation.get("complete") is True,
                "relationship_state_consistent": relation.get("consistent") is True,
                "expected_relationship_state": (
                    relation.get("military_access_active") is expected_active
                ),
                "relationship_evidence_public": relation.get("source") == "relationship_state",
            }
        report["checks"] = {
            "new_process_ready": health.get("status") == "ready"
            and health.get("complete") is True,
            "health_date_matches_expected": health.get("date_raw") == args.expected_date_raw,
            "date_matches_expected": control.get("date_raw") == args.expected_date_raw,
            "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "four_snapshots_complete": _snapshots_complete(probes),
            "direction_set_complete": set(direction_checks) == {
                f"{actor}->{recipient}" for actor, recipient, _expected in directions
            },
            "direction_relations": all(
                all(checks.values()) for checks in direction_checks.values()
            ),
            "military_access_query_acknowledged": (
                "native_military_access_query" in capabilities
            ),
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "source_build_session_bound": (
                isinstance(build_binding, dict)
                and build_binding.get("installation_matches_build_manifest") is True
                and build_binding.get("loaded_dll_sha256")
                == build_binding.get("installation_dll_sha256")
            ),
            "save_hash_bound": (
                report["save"].get("provided") is not True
                or isinstance(report["save"].get("sha256"), str)
            ),
            "diplomat_semantics_recorded": isinstance(semantics, list),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)
    print(
        json.dumps(
            {"status": report["status"], "artifact": str(artifact)},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
