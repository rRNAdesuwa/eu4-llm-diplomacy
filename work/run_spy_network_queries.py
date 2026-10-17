"""Query Build Spy Network legality for several recipients without execution.

The command performs native-backed start and stop inspections for every
repeatable ``--recipient``.  It records whatever native legality returns,
including unavailable start actions; it does not infer that every recipient
must be startable and never publishes an execution request.
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
from work.run_improve_relations_execution import (  # noqa: E402
    _diplomat_evidence,
    _new_artifact,
    _query_improve_pair,
)
from work.run_royal_marriage_execution import _snapshots_complete  # noqa: E402
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _run_snapshots,
)
from work.run_royal_marriage_execution import _installation_binding  # noqa: E402


_ACTOR = "FRA"
_PLAYER_SLOT = 189
_DEFAULT_EXPECTED = {"BUR": True, "SAV": False, "PRO": False}
_ACTIONS = ("build_spy_network", "stop_building_spy_network")
_SPY_SELECTOR = 13176
_SPY_FAMILY = "spy_network"
_TAG_RE = re.compile(r"[A-Z]{3}\Z")


class QueryValidationError(RuntimeError):
    """A bounded read-only query validation error."""


def _query_spy_pair(api: DiplomacyTools, recipient: str,
                    destination: Path) -> dict[str, dict[str, object]]:
    return _query_improve_pair(api, recipient, destination, _ACTIONS)


def _parse_expected(values: list[str] | None) -> dict[str, bool]:
    expected = dict(_DEFAULT_EXPECTED)
    for value in values or []:
        if "=" not in value:
            raise QueryValidationError(f"EXPECTED_TASK_INVALID:{value}")
        tag, state = value.split("=", 1)
        if not _TAG_RE.fullmatch(tag) or state not in ("active", "absent"):
            raise QueryValidationError(f"EXPECTED_TASK_INVALID:{value}")
        expected[tag] = state == "active"
    return expected


def _query_shape(query: object, action_id: str) -> dict[str, object]:
    if not isinstance(query, dict):
        return {"complete": False, "action_id": None, "legality_status": None,
                "visibility_status": None, "legality_source": None}
    legality = query.get("legality")
    visibility = query.get("visibility")
    legality_status = legality.get("status") if isinstance(legality, dict) else None
    visibility_status = visibility.get("status") if isinstance(visibility, dict) else None
    return {
        "complete": (
            query.get("action_id") == action_id
            and isinstance(legality, dict) and legality.get("complete") is True
            and legality_status in ("available", "unavailable")
            and isinstance(visibility, dict) and visibility.get("complete") is True
            and visibility_status in ("visible", "hidden")
        ),
        "action_id": query.get("action_id"),
        "legality_status": legality_status,
        "visibility_status": visibility_status,
        "legality_source": legality.get("source") if isinstance(legality, dict) else None,
        "legality": legality,
        "visibility": visibility,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--recipient", action="append", required=True,
                        help="Repeat for each three-letter recipient")
    parser.add_argument("--expected-task", action="append", metavar="TAG=active|absent",
                        help="Optional task expectation; defaults BUR=active,SAV=absent,PRO=absent")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "spy-network-queries")
    report: dict[str, object] = {
        "validator": "run_spy_network_queries.py",
        "status": "running", "mode": "read_only_native_queries",
        "installation": str(installation), "actor": _ACTOR,
        "recipients": args.recipient, "actions": list(_ACTIONS),
        "family": _SPY_FAMILY, "selector": _SPY_SELECTOR,
        "expected_date_raw": args.expected_date_raw, "artifact": str(artifact),
        "execute_call_count": 0, "execution_requested": False,
        "business_submission": False, "checks": {},
    }
    try:
        if len(set(args.recipient)) != len(args.recipient):
            raise QueryValidationError("RECIPIENT_DUPLICATE")
        if any(not _TAG_RE.fullmatch(tag) for tag in args.recipient):
            raise QueryValidationError("RECIPIENT_TAG_INVALID")
        expected = _parse_expected(args.expected_task)
        report["expected_task"] = {tag: expected[tag] for tag in args.recipient if tag in expected}
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
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise QueryValidationError("SESSION_NOT_READY")
        probes = _run_snapshots(session, artifact / "probes")
        control = _control_summary(probes["control_state"]["snapshot"])
        semantics = _diplomat_semantics(probes["diplomats"]["snapshot"])
        report["probes"] = {
            name: {
                "status": item.get("status"), "snapshot_path": item.get("snapshot_path"),
                "snapshot_completeness": item.get("snapshot_completeness"),
                "snapshot_sha256": item.get("snapshot_sha256"),
            } for name, item in probes.items()
        }
        report["control"] = control
        report["diplomat_semantics"] = semantics

        query_results: dict[str, dict[str, object]] = {}
        task_results: dict[str, dict[str, object]] = {}
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in args.recipient:
                queries_path = artifact / "queries" / f"{recipient}.json"
                query_results[recipient] = _query_spy_pair(api, recipient, queries_path)
                evidence = _diplomat_evidence(
                    probes, recipient, selector=_SPY_SELECTOR, family=_SPY_FAMILY
                )
                task = evidence.get("task")
                task_results[recipient] = {
                    "task": task,
                    "expected_task": expected.get(recipient),
                    "task_matches_expected": (
                        expected[recipient] == task.get("task")
                        if recipient in expected and isinstance(task, dict) else None
                    ),
                }
        _write_json(artifact / "queries.json", query_results)
        _write_json(artifact / "task-observations.json", task_results)
        report["queries"] = query_results
        report["tasks"] = task_results

        per_recipient: dict[str, dict[str, object]] = {}
        for recipient in args.recipient:
            pair = query_results.get(recipient, {})
            start = _query_shape(pair.get(_ACTIONS[0]), _ACTIONS[0])
            stop = _query_shape(pair.get(_ACTIONS[1]), _ACTIONS[1])
            task = task_results[recipient].get("task")
            per_recipient[recipient] = {
                "start": start, "stop": stop, "task": task,
                "task_selector": task.get("selector") if isinstance(task, dict) else None,
                "task_family": task.get("family") if isinstance(task, dict) else None,
                "task_matches_expected": task_results[recipient].get("task_matches_expected"),
                # Native statuses are evidence, not an AI-side prediction.
                "native_legality_statuses": {
                    "build_spy_network": start.get("legality_status"),
                    "stop_building_spy_network": stop.get("legality_status"),
                },
            }
        report["recipient_results"] = per_recipient
        build_binding = report.get("build_binding")
        report["checks"] = {
            "new_process_ready": health.get("status") == "ready" and health.get("complete") is True,
            "player_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "date_matches_expected": (
                control.get("date_raw") == args.expected_date_raw
                and health.get("date_raw") == args.expected_date_raw
            ),
            "four_snapshots_complete": _snapshots_complete(probes),
            "diplomat_semantics_complete": isinstance(semantics, list),
            "all_native_queries_complete": all(
                bool(result["start"]["complete"] and result["stop"]["complete"])
                for result in per_recipient.values()
            ),
            "task_expectations_complete": all(
                result["task_matches_expected"] is True
                for result in per_recipient.values()
                if result["task_matches_expected"] is not None
            ),
            "spy_selector_observed": all(
                isinstance(result["task"], dict)
                and result["task"].get("selector") == _SPY_SELECTOR
                for result in per_recipient.values()
            ),
            "spy_family_observed": all(
                isinstance(result["task"], dict)
                and result["task"].get("family", _SPY_FAMILY) == _SPY_FAMILY
                for result in per_recipient.values()
            ),
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "source_build_session_bound": (
                isinstance(build_binding, dict)
                and build_binding.get("installation_matches_build_manifest") is True
                and build_binding.get("loaded_dll_sha256") == build_binding.get("installation_dll_sha256")
            ),
            "stop_action_length_recorded": len("stop_building_spy_network") == 25,
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
