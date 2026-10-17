"""Run bounded, read-only native Insult queries.

For every repeated recipient the operator records the ordinary-insult query,
the scornful-insult candidate discovery query, and, when ``--insult-id`` is
given, a selected-candidate query.  It never publishes an execution request.
The native result keeps the one-sided Insult fields separate from acceptance
or relationship evidence: ``insult_active``, opinion modifier, prestige and
the candidate list are all returned as observed.
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
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189
_DEFAULT_DATE_RAW = 56463768
_ACTIONS = ("send_insult", "scornful_insult")
_FAMILY = "insult"
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_DEFAULT_RECIPIENTS = ("HOL", "SWE", "NOR", "FOI", "SAV")


class QueryValidationError(RuntimeError):
    """An expected bounded read-only query validation stop."""


def _parse_mapping(values: list[str] | None,
                   allowed: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        tag, state = value.split("=", 1)
        if not _TAG_RE.fullmatch(tag) or state not in allowed:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        if tag in result:
            raise QueryValidationError(f"MAPPING_DUPLICATE:{tag}")
        result[tag] = state
    return result


def _query_insult_set(api: DiplomacyTools, recipient: str,
                      destination: Path,
                      selected_id: int | None = None
                      ) -> dict[str, dict[str, object]]:
    """Query ordinary, discovery, and optional selected Insult variants."""

    requests: list[tuple[str, dict[str, object]]] = [
        ("send_insult", {}),
        ("scornful_insult", (
            {"insult_id": selected_id} if selected_id is not None else {}
        )),
    ]
    result: dict[str, dict[str, object]] = {}
    for action_id, parameters in requests:
        try:
            inspected = api.inspect_diplomatic_action(
                action_id, _ACTOR, recipient, phase="initiate",
                parameters=parameters,
            )
            result_key = (
                "scornful_insult_selected" if action_id == "scornful_insult"
                and selected_id is not None else action_id
            )
            result[result_key] = inspected if isinstance(inspected, dict) else {
                "status": "unknown", "error": "INSPECTION_NOT_OBJECT",
            }
        except Exception as error:
            result_key = (
                "scornful_insult_selected" if action_id == "scornful_insult"
                and selected_id is not None else action_id
            )
            result[result_key] = {
                "status": "unknown", "error_type": type(error).__name__,
                "error": str(error),
            }
    destination.mkdir(parents=True, exist_ok=True)
    for key, value in result.items():
        _write_json(destination / f"{key}.json", value)
    return result


def _int_field(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _insult_query_shape(query: object, action_id: str,
                        expected_id: int,
                        *, discovery: bool = False) -> dict[str, object]:
    """Reduce one public query to bounded, family-specific evidence."""

    if not isinstance(query, dict):
        return {
            "complete": False, "action_id": None, "family": None,
            "insult_id": None, "insult_active": None,
            "insult_state_verified": False,
            "opinion_modifier_raw": None, "actor_prestige_raw": None,
            "prestige_cost_raw": None, "candidates": None,
        }
    parameters = query.get("parameters")
    candidates = parameters.get("candidates") if isinstance(parameters, dict) else None
    legality = query.get("legality")
    legality_status = legality.get("status") if isinstance(legality, dict) else None
    actual_id = query.get("insult_id")
    active = query.get("insult_active")
    session = query.get("session")
    visibility = query.get("visibility")
    coverage = query.get("rule_coverage")
    if not isinstance(coverage, dict):
        coverage = query.get("native_rule_components")
    structural_complete = (
        isinstance(session, dict) and session.get("status") == "ready"
        and isinstance(visibility, dict) and visibility.get("complete") is True
        and isinstance(coverage, dict) and coverage.get("complete") is True
        and isinstance(legality, dict)
        and (legality.get("complete") is True or discovery)
    )
    complete = (
        structural_complete
        and query.get("family") == _FAMILY
        and actual_id == expected_id
        and type(query.get("insult_parameter_selected")) is bool
        and query.get("insult_parameter_selected") is (expected_id != -2)
        and query.get("insult_state_verified") is True
        and type(active) is bool
        and _int_field(query.get("opinion_modifier_raw"))
        and _int_field(query.get("actor_prestige_raw"))
        and (query.get("prestige_cost_raw") is None
             or _int_field(query.get("prestige_cost_raw")))
        and (not discovery or (
            isinstance(candidates, dict)
            and candidates.get("complete") is True
            and isinstance(candidates.get("insult_id"), list)
        ))
    )
    return {
        "complete": complete,
        "action_id": query.get("action_id"),
        "family": query.get("family"),
        "legality_status": legality_status,
        "legality": legality,
        "insult_id": actual_id,
        "insult_parameter_selected": query.get("insult_parameter_selected"),
        "insult_state_verified": query.get("insult_state_verified"),
        "insult_active": active if type(active) is bool else None,
        "opinion_modifier_raw": query.get("opinion_modifier_raw"),
        "actor_prestige_raw": query.get("actor_prestige_raw"),
        "prestige_cost_raw": query.get("prestige_cost_raw"),
        "candidates": candidates,
        "interface_query": (
            query.get("interface_support", {}).get("query")
            if isinstance(query.get("interface_support"), dict) else None
        ),
    }


def _query_set_summary(queries: object, selected_id: int | None = None
                       ) -> dict[str, object]:
    if not isinstance(queries, dict):
        return {
            "complete": False, "action_query_complete": False,
            "scornful_discovery_complete": False,
            "send": {}, "scornful": {},
        }
    send = _insult_query_shape(
        queries.get("send_insult"), "send_insult", -1,
    )
    scornful_key = "scornful_insult_selected" if selected_id is not None else "scornful_insult"
    scornful_expected = selected_id if selected_id is not None else -2
    scornful = _insult_query_shape(
        queries.get(scornful_key), "scornful_insult", scornful_expected,
        discovery=selected_id is None,
    )
    send_complete = send.get("complete") is True
    scornful_complete = scornful.get("complete") is True
    discovery_complete = (
        selected_id is None
        and isinstance(scornful.get("candidates"), dict)
        and scornful["candidates"].get("complete") is True
    )
    return {
        # ``complete`` means both the ordinary action and a selected scornful
        # action are fully validated.  Discovery has no selected legality and
        # therefore has its own flag; a one-sided ordinary execution must not
        # depend on that unrelated discovery result.
        "complete": send_complete and scornful_complete,
        "action_query_complete": send_complete if selected_id is None else scornful_complete,
        "scornful_discovery_complete": discovery_complete,
        "send": send,
        "scornful": scornful,
        "scornful_query_key": scornful_key,
        "selected_id": selected_id,
    }


def _expected_mapping_matches(results: dict[str, dict[str, object]],
                              expected: dict[str, str],
                              field: str) -> bool:
    checks: list[bool] = []
    for tag, wanted in expected.items():
        shape = results.get(tag, {}).get("summary", {})
        send = shape.get("send", {}) if isinstance(shape, dict) else {}
        value = send.get(field) if isinstance(send, dict) else None
        if field == "insult_active":
            checks.append(value is (wanted == "active"))
        else:
            checks.append(value == wanted)
    return all(checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, default=_DEFAULT_DATE_RAW)
    parser.add_argument(
        "--recipient", action="append",
        help="Repeat for each three-letter recipient; defaults HOL,SWE,NOR,FOI,SAV",
    )
    parser.add_argument(
        "--insult-id", type=int,
        help="Optional nonnegative scornful candidate to query in addition to discovery",
    )
    parser.add_argument(
        "--expected-legality", action="append",
        metavar="TAG=available|unavailable|unknown",
        help="Optional ordinary-insult legality expectation",
    )
    parser.add_argument(
        "--expected-insult-active", action="append",
        metavar="TAG=active|absent",
        help="Optional ordinary-insult state expectation",
    )
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "insult-queries")
    recipients = tuple(args.recipient or _DEFAULT_RECIPIENTS)
    report: dict[str, object] = {
        "validator": "run_insult_queries.py",
        "status": "running",
        "mode": "read_only_native_insult_queries",
        "installation": str(installation),
        "actor": _ACTOR,
        "recipients": list(recipients),
        "actions": list(_ACTIONS),
        "family": _FAMILY,
        "selected_insult_id": args.insult_id,
        "expected_date_raw": args.expected_date_raw,
        "artifact": str(artifact),
        "execute_call_count": 0,
        "execution_requested": False,
        "business_submission": False,
        "checks": {},
    }
    try:
        if len(set(recipients)) != len(recipients):
            raise QueryValidationError("RECIPIENT_DUPLICATE")
        if any(not _TAG_RE.fullmatch(tag) or tag == _ACTOR for tag in recipients):
            raise QueryValidationError("RECIPIENT_TAG_INVALID")
        if args.insult_id is not None and not 0 <= args.insult_id <= 2147483647:
            raise QueryValidationError("INSULT_ID_INVALID")
        expected_legality = _parse_mapping(
            args.expected_legality, ("available", "unavailable", "unknown")
        )
        expected_active = _parse_mapping(
            args.expected_insult_active, ("active", "absent")
        )
        report["expected_legality"] = expected_legality
        report["expected_insult_active"] = expected_active

        installation = installation.resolve(strict=True)
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
            artifact / "diplomacy.sqlite3", session.experiment_id,
            session.session_id, global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                query_results[recipient] = _query_insult_set(
                    api, recipient, artifact / "queries" / recipient,
                    args.insult_id,
                )
        _write_json(artifact / "queries.json", query_results)
        report["queries"] = query_results

        recipient_results: dict[str, dict[str, object]] = {}
        for recipient in recipients:
            summary = _query_set_summary(query_results[recipient], args.insult_id)
            send = summary.get("send", {})
            recipient_results[recipient] = {
                "summary": summary,
                "ordinary_legality_status": send.get("legality_status"),
                "expected_legality": expected_legality.get(recipient),
                "legality_matches_expected": (
                    send.get("legality_status") == expected_legality[recipient]
                    if recipient in expected_legality else None
                ),
                "ordinary_insult_active": send.get("insult_active"),
                "expected_insult_active": expected_active.get(recipient),
                "insult_active_matches_expected": (
                    send.get("insult_active") is (expected_active[recipient] == "active")
                    if recipient in expected_active else None
                ),
            }
        report["recipient_results"] = recipient_results
        capabilities = session.installation_capabilities()
        legality_checks = [
            item["legality_matches_expected"]
            for item in recipient_results.values()
            if item["legality_matches_expected"] is not None
        ]
        active_checks = [
            item["insult_active_matches_expected"]
            for item in recipient_results.values()
            if item["insult_active_matches_expected"] is not None
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
            "all_native_insult_queries_complete": all(
                item["summary"].get("complete") is True
                for item in recipient_results.values()
            ),
            "native_insult_query_acknowledged": (
                "native_insult_query" in capabilities
            ),
            "expected_legality_matches": all(legality_checks) if legality_checks else True,
            "expected_insult_active_matches": all(active_checks) if active_checks else True,
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
            "insult_family_separated": all(
                item["summary"].get("send", {}).get("family") == _FAMILY
                and item["summary"].get("scornful", {}).get("family") == _FAMILY
                for item in recipient_results.values()
            ),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
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
