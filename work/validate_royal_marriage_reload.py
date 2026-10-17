"""Validate one named save after a fresh Royal Marriage reload.

The game must already be running with the supplied installation.  This tool
only reads the new process, the four reviewed snapshots, native Royal query
results, and save/source hashes.  It never submits an action, advances time,
saves, starts a process, or installs a module.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import _write_json  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _break_selector_relation,
    _installation_binding,
    _inspect_royal_pair,
    _query_is_complete,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    PROBE_SPECS,
    ReloadValidationError,
    _control_summary,
    _diplomat_semantics,
    _find_save,
    _find_source_baseline,
    _hash_file,
    _read_json,
    _run_snapshots,
    _snapshot_record,
    _source_check,
)


_PLAYER_SLOT = 189  # POR in the controlled r3 experiment
_ROYAL_ACTIONS = ("offer_royal_marriage", "break_royal_ties")
_TAG_EXPECTATION_RE = re.compile(r"([A-Z]{3})=(present|absent)\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class ReloadValidationErrorLocal(RuntimeError):
    """An expected validation stop local to this Royal validator."""


def _expectation(value: str) -> tuple[str, bool]:
    match = _TAG_EXPECTATION_RE.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError("Use TAG=present or TAG=absent")
    return match.group(1), match.group(2) == "present"


def _query_records(api: DiplomacyTools, tags: list[str]) -> dict[str, dict[str, object]]:
    return {recipient: _inspect_royal_pair(api, recipient) for recipient in tags}


def _query_pairs_complete(pair: object) -> bool:
    if not isinstance(pair, dict):
        return False
    return all(_query_is_complete(pair.get(action_id), action_id)
               for action_id in _ROYAL_ACTIONS)


def _marriage_checks(queries: object, expectations: dict[str, bool]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if not expectations:
        checks["marriage_expectations_supplied"] = False
        return checks
    checks["marriage_expectations_supplied"] = True
    if not isinstance(queries, dict):
        for tag in expectations:
            checks[f"{tag.lower()}_query_pair_complete"] = False
            checks[f"{tag.lower()}_break_visibility"] = False
        return checks
    for tag, expected_present in expectations.items():
        pair = queries.get(tag)
        break_query = pair.get("break_royal_ties") if isinstance(pair, dict) else None
        selector = _break_selector_relation(break_query)
        expected_status = "visible" if expected_present else "hidden"
        prefix = tag.lower()
        checks[f"{prefix}_query_pair_complete"] = _query_pairs_complete(pair)
        checks[f"{prefix}_break_visibility"] = selector.get("visibility_status") == expected_status
        checks[f"{prefix}_break_visibility_complete"] = selector.get("visibility_complete") is True
        checks[f"{prefix}_break_selector_independent"] = (
            selector.get("ui_action_selection_bool") is True
            and selector.get("royal_marriage") is expected_present
            and selector.get("selector_consistent") is True
        )
        acceptance = break_query.get("acceptance") if isinstance(break_query, dict) else None
        checks[f"{prefix}_break_single_side_acceptance"] = (
            isinstance(acceptance, dict)
            and acceptance.get("applicability") == "not_applicable"
            and acceptance.get("complete") is True
        )
    return checks


def _public_probe_records(records: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        name: {
            "status": item.get("status"),
            "snapshot_path": item.get("snapshot_path"),
            "snapshot_completeness": item.get("snapshot_completeness"),
            "snapshot_sha256": item.get("snapshot_sha256"),
        }
        for name, item in records.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--before-probes", type=Path, required=True,
                        help="Royal execution before/probes directory")
    parser.add_argument("--save-name", required=True,
                        help="ASCII basename of the independently named save")
    parser.add_argument("--expected-save-sha256", required=True)
    parser.add_argument("--source-r3-sha256",
                        help="Previously recorded SHA-256 of the original R3 scenario")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--expect-marriage", action="append", type=_expectation, required=True,
                        help="Expected Royal relation, for example SAV=present")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    before_probes = args.before_probes.expanduser().resolve()
    artifact = installation.parent / ("royal-marriage-reload-" + uuid.uuid4().hex)
    artifact.mkdir(parents=True)
    expectations = dict(args.expect_marriage)
    report: dict[str, object] = {
        "validator": "validate_royal_marriage_reload.py",
        "status": "running",
        "installation_path": str(installation),
        "before_probes": str(before_probes),
        "save_name": args.save_name,
        "expected_save_sha256": args.expected_save_sha256.lower(),
        "expected_date_raw": args.expected_date_raw,
        "expected_marriage": expectations,
        "artifact": str(artifact),
        "checks": {},
    }

    try:
        if not _SHA256_RE.fullmatch(args.expected_save_sha256):
            raise ReloadValidationErrorLocal("EXPECTED_SAVE_SHA256_INVALID")
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
            raise ReloadValidationErrorLocal("EXPECTED_DATE_RAW_MUST_BE_INT")

        before_files = {
            spec.name: _snapshot_record(before_probes / f"{spec.name}.json", spec.name)
            for spec in PROBE_SPECS
        }
        before_control = _control_summary(before_files["control_state"]["snapshot"])
        before_diplomats = _diplomat_semantics(before_files["diplomats"]["snapshot"])
        before_complete = _snapshots_complete(before_files)
        report["before"] = {
            "control": before_control,
            "diplomats": before_diplomats,
            "snapshot_complete": before_complete,
            "probe_files": _public_probe_records(before_files),
        }

        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        binding = report.get("build_binding")
        if isinstance(binding, dict):
            binding["loaded_dll_sha256"] = session.record.get("dll_sha256")

        health_before = wait_runtime_ready(session, restore_minimized=True)
        if health_before.get("status") != "ready":
            raise ReloadValidationErrorLocal("SESSION_NOT_READY")
        if health_before.get("date_raw") != args.expected_date_raw:
            raise ReloadValidationErrorLocal("HEALTH_DATE_MISMATCH")

        after_files = _run_snapshots(session, artifact / "after" / "probes")
        after_control = _control_summary(after_files["control_state"]["snapshot"])
        after_diplomats = _diplomat_semantics(after_files["diplomats"]["snapshot"])
        health_after = session.health()
        report["after"] = {
            "control": after_control,
            "diplomats": after_diplomats,
            "snapshot_complete": _snapshots_complete(after_files),
            "probe_files": _public_probe_records(after_files),
            "health": health_after,
        }

        query_results: dict[str, dict[str, object]] = {}
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            query_results = _query_records(api, list(expectations))
        _write_json(artifact / "royal-queries.json", query_results)
        report["royal_queries"] = query_results

        save_path = _find_save(args.save_name)
        save_record = _hash_file(save_path, maximum=256 * 1024 * 1024)
        save_record["expected_sha256"] = args.expected_save_sha256.lower()
        save_record["sha256_matches_expected"] = (
            save_record.get("sha256") == args.expected_save_sha256.lower()
        )
        report["save"] = save_record

        if args.source_r3_sha256:
            if not _SHA256_RE.fullmatch(args.source_r3_sha256):
                raise ReloadValidationErrorLocal("SOURCE_R3_SHA256_INVALID")
            source_baseline = {"status": "ok", "baseline": {
                "sha256": args.source_r3_sha256.lower(),
                "source": "operator_supplied_original_scenario_hash"}}
        else:
            source_baseline = _find_source_baseline(before_probes)
        report["source_r3"] = _source_check(source_baseline)

        checks: dict[str, bool] = {
            "new_process_ready": (
                health_before.get("status") == "ready"
                and health_before.get("complete") is True
                and health_after.get("status") == "ready"
                and health_after.get("complete") is True
            ),
            "player_por": after_control.get("player_slot") == _PLAYER_SLOT,
            "paused": after_control.get("paused_flag") == 1,
            "date_matches_expected": (
                after_control.get("date_raw") == args.expected_date_raw
                and health_after.get("date_raw") == args.expected_date_raw
            ),
            "date_same_as_before": after_control.get("date_raw") == before_control.get("date_raw"),
            "snapshot_complete_before": before_complete,
            "snapshot_complete_after": _snapshots_complete(after_files),
            "diplomat_semantics_preserved": before_diplomats == after_diplomats,
            "save_sha256_present": isinstance(save_record.get("sha256"), str),
            "save_sha256_matches_expected": save_record.get("sha256_matches_expected") is True,
            "source_r3_unchanged": (
                isinstance(report.get("source_r3"), dict)
                and report["source_r3"].get("unchanged") is True
            ),
            "build_dll_source_bound": (
                isinstance(report.get("build_binding"), dict)
                and report["build_binding"].get("installation_matches_build_manifest") is True
                and report["build_binding"].get("loaded_dll_sha256")
                == report["build_binding"].get("installation_dll_sha256")
            ),
        }
        checks.update(_marriage_checks(query_results, expectations))
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except (ReloadValidationError, ReloadValidationErrorLocal, KeyError, TypeError,
            ValueError, OSError) as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    except Exception as error:  # retain artifact for operator diagnosis
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
