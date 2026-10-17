"""Validate Support Independence state in an already reloaded process.

This read-only validator checks POR paused/date identity, four observer
snapshots, both native Support Independence inspections, and the public
relationship_state.  It never publishes an execution request and does not
infer a continuing relation from diplomat task records.
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
from work.run_royal_marriage_execution import _snapshots_complete  # noqa: E402
from work.run_support_independence_execution import (  # noqa: E402
    _ACTIONS,
    _DEFAULT_DATE_RAW,
    _FAMILY,
    _installation_binding,
    _new_artifact,
    _query_pair_complete,
    _query_support_pair,
    _relation_pair,
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
_MAX_SAVE_BYTES = 256 * 1024 * 1024


class ReloadValidationError(RuntimeError):
    """An expected read-only validation stop."""


def _reference_record(reference: Path) -> dict[str, object]:
    reference = reference.expanduser().resolve(strict=True)
    report_path = reference if reference.is_file() else reference / "report.json"
    payload = _read_json(report_path)
    if not isinstance(payload, dict):
        raise ReloadValidationError("REFERENCE_REPORT_NOT_OBJECT")
    after = payload.get("after") if isinstance(payload.get("after"), dict) else {}
    queries = after.get("queries") if isinstance(after.get("queries"), dict) else None
    relation = _relation_pair(queries) if queries is not None else None
    if relation is None and isinstance(after.get("relation"), dict):
        relation = after["relation"]
    control = after.get("control") if isinstance(after.get("control"), dict) else {}
    resources = after.get("diplomat_semantics")
    if resources is None and isinstance(after.get("diplomat"), dict):
        resources = after["diplomat"].get("semantics")
    return {
        "path": str(report_path),
        "status": payload.get("status"),
        "date_raw": control.get("date_raw"),
        "relation": relation,
        "resource_semantics": resources,
    }


def _save_record(path: Path | None) -> dict[str, object]:
    if path is None:
        return {"provided": False}
    resolved = path.expanduser().resolve(strict=True)
    return {"provided": True, "sha256": _hash_file(resolved, maximum=_MAX_SAVE_BYTES)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--expected-support", choices=("active", "absent"), required=True)
    parser.add_argument("--save-path", type=Path)
    parser.add_argument("--reference-artifact", type=Path)
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "support-independence-reload")
    expected_active = args.expected_support == "active"
    report: dict[str, object] = {
        "validator": "validate_support_independence_reload.py",
        "status": "running",
        "mode": "read_only_reload_validation",
        "installation": str(installation),
        "actor": _ACTOR,
        "recipient": args.recipient,
        "family": _FAMILY,
        "actions": list(_ACTIONS),
        "expected_date_raw": args.expected_date_raw,
        "expected_support": args.expected_support,
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
        if not _TAG_RE.fullmatch(args.recipient):
            raise ReloadValidationError("RECIPIENT_TAG_INVALID")
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
        except Exception as exc:
            semantics = None
            semantics_error = {"type": type(exc).__name__, "message": str(exc)}
        with DurableJournal(
            artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            queries = _query_support_pair(
                api, args.recipient, artifact / "after" / "queries.json"
            )
        relation = _relation_pair(queries)
        report["after"] = {
            "health": health,
            "control": control,
            "queries": queries,
            "relation": relation,
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
        report["query_legality"] = {
            action_id: (
                queries.get(action_id, {}).get("legality", {}).get("status")
                if isinstance(queries.get(action_id), dict)
                and isinstance(queries.get(action_id, {}).get("legality"), dict)
                else None
            )
            for action_id in _ACTIONS
        }
        capabilities = session.installation_capabilities()
        reference = None
        if args.reference_artifact is not None:
            reference = _reference_record(args.reference_artifact)
            current_date = control.get("date_raw")
            reference_date = reference.get("date_raw")
            comparable = (
                isinstance(current_date, int)
                and isinstance(reference_date, int)
                and current_date == reference_date
            )
            reference_relation = reference.get("relation")
            reference_resources = reference.get("resource_semantics")
            relation_equal = (
                comparable
                and isinstance(reference_relation, dict)
                and reference_relation.get("support_independence_active")
                == relation.get("support_independence_active")
            )
            resource_equal = (
                comparable
                and isinstance(reference_resources, list)
                and isinstance(semantics, list)
                and reference_resources == semantics
            )
            reference["comparison"] = {
                "comparable_same_date": comparable,
                "relation_equal": relation_equal if comparable else None,
                "resource_equal": resource_equal if comparable else None,
                "resource_comparison_available": (
                    isinstance(reference_resources, list) and isinstance(semantics, list)
                ),
                "skipped_for_date_mismatch": not comparable,
            }
        report["reference"] = reference
        build_binding = report.get("build_binding")
        checks = {
            "new_process_ready": health.get("status") == "ready"
            and health.get("complete") is True,
            "health_date_matches_expected": health.get("date_raw") == args.expected_date_raw,
            "date_matches_expected": control.get("date_raw") == args.expected_date_raw,
            "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "four_snapshots_complete": _snapshots_complete(probes),
            "query_pair_complete": _query_pair_complete(queries),
            "query_relation_consistent": relation.get("consistent") is True,
            "expected_relationship_state": (
                relation.get("support_independence_active") is expected_active
            ),
            "support_query_acknowledged": "native_support_independence_query" in capabilities,
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
            "relationship_state_is_explicit_evidence": (
                relation.get("source") == "relationship_state"
                and relation.get("complete") is True
            ),
            "save_hash_bound": (
                report["save"].get("provided") is not True
                or isinstance(report["save"].get("sha256"), dict)
            ),
        }
        if isinstance(reference, dict):
            comparison = reference.get("comparison")
            if isinstance(comparison, dict) and comparison.get("comparable_same_date") is True:
                checks["reference_relation_matches_same_date"] = comparison.get("relation_equal") is True
                if comparison.get("resource_comparison_available") is True:
                    checks["reference_resources_match_same_date"] = comparison.get("resource_equal") is True
            else:
                checks["reference_comparison_deferred_date_mismatch"] = True
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
