"""Run read-only native Support Independence inspections.

The operator queries both support_independence and
revoke_support_independence for every repeated recipient.  Native legality,
visibility, and relationship_state are recorded exactly as returned; the
operator never assumes that a target is qualified or willing and never
publishes an execution request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import _write_json  # noqa: E402
from work.run_royal_marriage_execution import _installation_binding, _query_is_complete, _snapshots_complete  # noqa: E402
from work.validate_alliance_reload import _control_summary, _diplomat_semantics, _run_snapshots  # noqa: E402
from work.run_support_independence_execution import (  # noqa: E402
    _ACTIONS,
    _DEFAULT_DATE_RAW,
    _FAMILY,
    _new_artifact,
    _query_pair_complete,
    _query_support_pair,
    _relation_pair,
    _relation_state,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_DEFAULT_RECIPIENTS = ("HOL", "SWE", "NOR", "FOI", "SAV")


class QueryValidationError(RuntimeError):
    """A bounded read-only query validation error."""


def _parse_mapping(values: list[str] | None, allowed: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        tag, state = value.split("=", 1)
        if not _TAG_RE.fullmatch(tag) or state not in allowed:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        result[tag] = state
    return result


def _query_shape(query: object, action_id: str) -> dict[str, object]:
    if not isinstance(query, dict):
        return {
            "complete": False,
            "action_id": None,
            "legality_status": None,
            "visibility_status": None,
            "relationship_state": _relation_state(None),
        }
    legality = query.get("legality")
    visibility = query.get("visibility")
    legality_status = legality.get("status") if isinstance(legality, dict) else None
    visibility_status = visibility.get("status") if isinstance(visibility, dict) else None
    return {
        "complete": (
            _query_is_complete(query, action_id)
            and isinstance(legality, dict)
            and legality_status in ("available", "unavailable")
            and isinstance(visibility, dict)
            and visibility_status in ("visible", "hidden")
            and _relation_state(query).get("complete") is True
        ),
        "action_id": query.get("action_id"),
        "legality_status": legality_status,
        "visibility_status": visibility_status,
        "legality": legality,
        "visibility": visibility,
        "relationship_state": _relation_state(query),
        "interface_query": (
            query.get("interface_support", {}).get("query")
            if isinstance(query.get("interface_support"), dict) else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, default=_DEFAULT_DATE_RAW)
    parser.add_argument(
        "--recipient", action="append",
        help="Repeat for each three-letter recipient; defaults HOL,SWE,NOR,FOI,SAV",
    )
    parser.add_argument(
        "--expected-legality", action="append", metavar="TAG=available|unavailable",
        help="Optional native legality expectation; omitted targets remain observational",
    )
    parser.add_argument(
        "--expected-support", action="append", metavar="TAG=active|absent",
        help="Optional relationship_state expectation",
    )
    args = parser.parse_args(argv)

    recipients = tuple(args.recipient or _DEFAULT_RECIPIENTS)
    artifact = _new_artifact(
        args.installation.expanduser().resolve().parent, "support-independence-queries"
    )
    report: dict[str, object] = {
        "validator": "run_support_independence_queries.py",
        "status": "running",
        "mode": "read_only_native_queries",
        "installation": str(args.installation.expanduser().resolve()),
        "actor": _ACTOR,
        "recipients": list(recipients),
        "actions": list(_ACTIONS),
        "family": _FAMILY,
        "expected_date_raw": args.expected_date_raw,
        "artifact": str(artifact),
        "execute_call_count": 0,
        "execution_requested": False,
        "business_submission": False,
        "checks": {},
    }
    try:
        installation = args.installation.expanduser().resolve(strict=True)
        if len(set(recipients)) != len(recipients):
            raise QueryValidationError("RECIPIENT_DUPLICATE")
        if any(not _TAG_RE.fullmatch(tag) for tag in recipients):
            raise QueryValidationError("RECIPIENT_TAG_INVALID")
        expected_legality = _parse_mapping(
            args.expected_legality, ("available", "unavailable")
        )
        expected_support = _parse_mapping(args.expected_support, ("active", "absent"))
        report["expected_legality"] = {
            tag: expected_legality[tag] for tag in recipients if tag in expected_legality
        }
        report["expected_support"] = {
            tag: expected_support[tag] for tag in recipients if tag in expected_support
        }
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
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise QueryValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        try:
            semantics = _diplomat_semantics(probes["diplomats"]["snapshot"])
            semantics_error = None
        except Exception as exc:
            semantics = None
            semantics_error = {"type": type(exc).__name__, "message": str(exc)}
        report["probes"] = {
            name: {
                "status": item.get("status"),
                "snapshot_path": item.get("snapshot_path"),
                "snapshot_completeness": item.get("snapshot_completeness"),
                "snapshot_sha256": item.get("snapshot_sha256"),
            }
            for name, item in probes.items()
        }
        report["control"] = control
        report["diplomat_semantics"] = semantics
        report["diplomat_semantics_error"] = semantics_error

        query_results: dict[str, dict[str, dict[str, object]]] = {}
        with DurableJournal(
            artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                query_results[recipient] = _query_support_pair(
                    api, recipient, artifact / "queries" / f"{recipient}.json"
                )
        _write_json(artifact / "queries.json", query_results)
        report["queries"] = query_results

        recipient_results: dict[str, dict[str, object]] = {}
        for recipient in recipients:
            pair = query_results[recipient]
            start = _query_shape(pair.get(_ACTIONS[0]), _ACTIONS[0])
            stop = _query_shape(pair.get(_ACTIONS[1]), _ACTIONS[1])
            relation = _relation_pair(pair)
            observed_legality = start.get("legality_status")
            recipient_results[recipient] = {
                "support": start,
                "revoke": stop,
                "relation": relation,
                "native_legality_status": observed_legality,
                "expected_legality": expected_legality.get(recipient),
                "legality_matches_expected": (
                    observed_legality == expected_legality[recipient]
                    if recipient in expected_legality else None
                ),
                "expected_support": expected_support.get(recipient),
                "support_matches_expected": (
                    relation.get("support_independence_active")
                    is (expected_support[recipient] == "active")
                    if recipient in expected_support else None
                ),
            }
        report["recipient_results"] = recipient_results
        capabilities = session.installation_capabilities()
        legality_checks = [
            item["legality_matches_expected"]
            for item in recipient_results.values()
            if item["legality_matches_expected"] is not None
        ]
        relation_checks = [
            item["support_matches_expected"]
            for item in recipient_results.values()
            if item["support_matches_expected"] is not None
        ]
        build_binding = report.get("build_binding")
        report["checks"] = {
            "new_process_ready": health.get("status") == "ready"
            and health.get("complete") is True,
            "player_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "date_matches_expected": (
                control.get("date_raw") == args.expected_date_raw
                and health.get("date_raw") == args.expected_date_raw
            ),
            "four_snapshots_complete": _snapshots_complete(probes),
            "all_native_queries_complete": all(
                _query_pair_complete(query_results[tag]) for tag in recipients
            ),
            "all_relationship_states_complete": all(
                recipient_results[tag]["relation"].get("complete") is True
                and recipient_results[tag]["relation"].get("consistent") is True
                for tag in recipients
            ),
            "support_query_acknowledged": "native_support_independence_query" in capabilities,
            "expected_legality_matches": all(legality_checks) if legality_checks else True,
            "expected_support_matches": all(relation_checks) if relation_checks else True,
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
            "relation_evidence_source_is_relationship_state": all(
                item["relation"].get("source") == "relationship_state"
                for item in recipient_results.values()
            ),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
