"""Read-only operator validation for an alliance save after a fresh reload.

The game must already be running with the observer installed.  This tool only
reads health, four reviewed snapshots, the two Dissolve selectors, and save
file hashes.  It never publishes a diplomacy action, advances time, saves,
starts a process, or installs a module.  Every artifact is written below a
new ``reload-validation-*`` directory beside the supplied installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe, user_data  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.validate_alliance_queries import (  # noqa: E402
    PROBE_SPECS,
    _run_probe,
    _snapshot_completeness,
)


_HASH_CHUNK_BYTES = 64 * 1024
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_SOURCE_R3_NAME = "llm_diplomacy_observer_returned_20261013_r3.eu4"
_SAVE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.eu4\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_DIPLOMAT_FIELDS = (
    "raw_id_44",
    "active_raw_18",
    "raw_actor_80",
    "raw_recipient_88",
    "raw_action_type_a8",
    "raw_20",
    "raw_24",
    "raw_2c",
)


class ReloadValidationError(RuntimeError):
    """An expected operator validation stop."""


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path, *, maximum: int = _MAX_METADATA_BYTES) -> Any:
    if not path.is_file():
        raise ReloadValidationError(f"FILE_MISSING:{path}")
    if path.stat().st_size > maximum:
        raise ReloadValidationError(f"METADATA_TOO_LARGE:{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReloadValidationError(f"JSON_READ_FAILED:{path}:{type(error).__name__}") from error


def _hash_file(path: Path, *, maximum: int) -> dict[str, object]:
    if not path.is_file():
        raise ReloadValidationError(f"FILE_MISSING:{path}")
    size = path.stat().st_size
    if size > maximum:
        raise ReloadValidationError(f"FILE_TOO_LARGE_FOR_BOUNDED_HASH:{path}")
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise ReloadValidationError(f"FILE_GREW_DURING_HASH:{path}")
                digest.update(chunk)
    except OSError as error:
        raise ReloadValidationError(f"HASH_FAILED:{path}:{type(error).__name__}") from error
    return {"path": str(path), "bytes": total, "sha256": digest.hexdigest()}


def _new_artifact(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        candidate = parent / f"reload-validation-{uuid.uuid4().hex}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise ReloadValidationError("RELOAD_OUTPUT_DIRECTORY_COLLISION")


def _snapshot_record(path: Path, name: str) -> dict[str, object]:
    snapshot = _read_json(path)
    if not isinstance(snapshot, dict) or snapshot.get("read_only") is not True:
        raise ReloadValidationError(f"READONLY_SNAPSHOT_NOT_DECLARED:{name}")
    completeness = _snapshot_completeness(name, snapshot)
    return {
        "status": "ok",
        "name": name,
        "snapshot": snapshot,
        "snapshot_completeness": completeness,
        "snapshot_sha256": _hash_file(path, maximum=_MAX_METADATA_BYTES),
        "snapshot_path": str(path),
    }


def _run_snapshots(session: ObserverSession, output: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    pid = int(session.record["pid"])
    for spec in PROBE_SPECS:
        path = output / f"{spec.name}.json"
        raw = _run_probe(spec, pid, path)
        result[spec.name] = {
            "status": raw.get("status"),
            "name": spec.name,
            "script": str(raw.get("script")) if raw.get("script") is not None else None,
            "snapshot_path": str(path),
            "snapshot_completeness": raw.get("snapshot_completeness"),
            "snapshot_sha256": _hash_file(path, maximum=_MAX_METADATA_BYTES),
            "snapshot": raw.get("snapshot"),
        }
    return result


def _public_snapshot_record(record: dict[str, object]) -> dict[str, object]:
    """Keep report metadata while leaving raw pointer fields in snapshot files."""

    return {
        key: record.get(key)
        for key in ("status", "name", "script", "snapshot_path", "snapshot_completeness", "snapshot_sha256")
    }


def _control_summary(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "date_raw": snapshot.get("date_raw"),
        "player_slot": snapshot.get("player_slot"),
        "paused_flag": snapshot.get("paused_flag"),
    }


def _diplomat_semantics(snapshot: dict[str, object]) -> list[dict[str, object]]:
    countries = snapshot.get("countries")
    if not isinstance(countries, list):
        raise ReloadValidationError("DIPLOMAT_COUNTRIES_NOT_LIST")
    result: list[dict[str, object]] = []
    for country in countries:
        if not isinstance(country, dict) or not isinstance(country.get("tag"), str):
            raise ReloadValidationError("DIPLOMAT_COUNTRY_TAG_MISSING")
        entries = country.get("diplomacy_entries")
        if not isinstance(entries, list):
            raise ReloadValidationError(f"DIPLOMAT_ENTRIES_NOT_LIST:{country.get('tag')}")
        clean_entries = [
            {field: entry.get(field) for field in _DIPLOMAT_FIELDS}
            for entry in entries
            if isinstance(entry, dict)
        ]
        if len(clean_entries) != len(entries):
            raise ReloadValidationError(f"DIPLOMAT_ENTRY_NOT_OBJECT:{country.get('tag')}")
        result.append({
            "countrytag": country["tag"],
            "available_count": country.get("available_diplomat_count"),
            "entries": clean_entries,
        })
    result.sort(key=lambda item: str(item["countrytag"]))
    return result


def _public_inspection(inspection: object) -> dict[str, object]:
    if not isinstance(inspection, dict):
        return {"status": "unknown", "error": "INSPECTION_NOT_OBJECT"}
    coverage = inspection.get("rule_coverage")
    if not isinstance(coverage, dict):
        coverage = inspection.get("native_rule_components")
    coverage_public = {}
    if isinstance(coverage, dict):
        for key in (
            "ui_action_selection", "ui_selection_checked", "native_visibility",
            "complete", "full_rules_complete", "ui_enabled_gate_checked",
        ):
            if key in coverage:
                coverage_public[key] = coverage.get(key)
    return {
        "action_id": inspection.get("action_id"),
        "actor": inspection.get("actor"),
        "recipient": inspection.get("recipient"),
        "phase": inspection.get("phase"),
        "session": {
            "status": (inspection.get("session") or {}).get("status")
            if isinstance(inspection.get("session"), dict) else None,
            "date_raw": (inspection.get("session") or {}).get("date_raw")
            if isinstance(inspection.get("session"), dict) else None,
            "complete": (inspection.get("session") or {}).get("complete")
            if isinstance(inspection.get("session"), dict) else None,
        },
        "visibility": inspection.get("visibility"),
        "rule_coverage": coverage_public,
        "legality": {
            "status": (inspection.get("legality") or {}).get("status")
            if isinstance(inspection.get("legality"), dict) else None,
            "complete": (inspection.get("legality") or {}).get("complete")
            if isinstance(inspection.get("legality"), dict) else None,
        },
        "authorization": {
            "status": (inspection.get("authorization") or {}).get("status")
            if isinstance(inspection.get("authorization"), dict) else None,
            "complete": (inspection.get("authorization") or {}).get("complete")
            if isinstance(inspection.get("authorization"), dict) else None,
        },
        "interface_support": inspection.get("interface_support"),
    }


def _dissolve_checks(queries: dict[str, dict[str, object]],
                     sav_outcome: str = "accepted",
                     extra_expectations: dict[str, bool] | None = None) -> dict[str, bool]:
    expected = {"SAV": "visible" if sav_outcome == "accepted" else "hidden", "LIT": "hidden"}
    if extra_expectations:
        expected.update({tag: "visible" if present else "hidden"
                         for tag, present in extra_expectations.items()})
    checks: dict[str, bool] = {}
    for recipient, expected_status in expected.items():
        item = queries.get(recipient, {})
        visibility = item.get("visibility") if isinstance(item, dict) else None
        status = visibility.get("status") if isinstance(visibility, dict) else None
        complete = visibility.get("complete") is True if isinstance(visibility, dict) else False
        coverage = item.get("rule_coverage") if isinstance(item, dict) else None
        ui_selection = coverage.get("ui_action_selection") if isinstance(coverage, dict) else None
        checks[f"dissolve_{recipient.lower()}_visibility"] = status == expected_status
        checks[f"dissolve_{recipient.lower()}_visibility_complete"] = complete
        checks[f"dissolve_{recipient.lower()}_ui_selection_bound"] = (
            isinstance(ui_selection, bool) and ui_selection == (status == "visible")
        )
    return checks


def _find_source_baseline(before_probes: Path) -> dict[str, object]:
    """Find the immutable save report beside the original execution experiment."""

    root = before_probes.resolve().parent.parent.parent
    candidates: list[dict[str, object]] = []
    for report_path in sorted(root.glob("save-observer-report-*.json")):
        try:
            data = _read_json(report_path, maximum=_MAX_METADATA_BYTES)
        except ReloadValidationError:
            continue
        saves = data.get("backup", {}).get("saves", {}) if isinstance(data, dict) else {}
        if not isinstance(saves, dict):
            continue
        for name, record in saves.items():
            if str(name).casefold() != _SOURCE_R3_NAME.casefold() or not isinstance(record, dict):
                continue
            value = record.get("sha256")
            if isinstance(value, str) and _SHA256_RE.fullmatch(value):
                candidates.append({"report": str(report_path), "sha256": value.lower()})
    hashes = {item["sha256"] for item in candidates}
    if len(hashes) != 1:
        return {"status": "unknown", "reason": "SOURCE_R3_BASELINE_UNIQUE_HASH_NOT_FOUND", "candidates": candidates}
    return {"status": "ok", "baseline": candidates[0]}


def _find_save(name: str) -> Path:
    if not _SAVE_NAME_RE.fullmatch(name) or Path(name).name != name:
        raise ReloadValidationError("SAVE_NAME_MUST_BE_ASCII_BASENAME_EU4")
    directory = user_data() / "save games"
    if not directory.is_dir():
        raise ReloadValidationError(f"SAVE_DIRECTORY_MISSING:{directory}")
    matches = [path for path in directory.iterdir()
               if path.is_file() and path.name.casefold() == name.casefold()]
    if len(matches) != 1:
        raise ReloadValidationError(f"SAVE_NAME_MATCH_COUNT:{name}:{len(matches)}")
    return matches[0]


def _source_check(baseline: dict[str, object]) -> dict[str, object]:
    current_path = user_data() / "save games" / _SOURCE_R3_NAME
    result: dict[str, object] = {"name": _SOURCE_R3_NAME, "current": None, "baseline": baseline}
    try:
        result["current"] = _hash_file(current_path, maximum=_MAX_SAVE_BYTES)
    except ReloadValidationError as error:
        result["error"] = str(error)
    baseline_record = baseline.get("baseline") if isinstance(baseline, dict) else None
    baseline_hash = baseline_record.get("sha256") if isinstance(baseline_record, dict) else None
    current_record = result.get("current")
    current_hash = current_record.get("sha256") if isinstance(current_record, dict) else None
    result["unchanged"] = isinstance(baseline_hash, str) and baseline_hash == current_hash
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--before-probes", type=Path, required=True,
                        help="LIT execution report's immutable after/probes directory")
    parser.add_argument("--save-name", required=True,
                        help="ASCII basename of the independently named save")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--expected-save-sha256")
    parser.add_argument("--sav-outcome", choices=("accepted", "rejected"), default="accepted",
                        help="Expected FRA-SAV relation in the saved response scenario")
    def alliance_expectation(value: str) -> tuple[str, bool]:
        match = re.fullmatch(r"([A-Z0-9]{3})=(present|absent)", value)
        if not match:
            raise argparse.ArgumentTypeError("Use TAG=present or TAG=absent")
        return match[1], match[2] == "present"
    parser.add_argument("--expect-alliance", action="append", type=alliance_expectation, default=[],
                        help="Additional expected FRA relation, such as PRO=absent")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    before_probes = args.before_probes.expanduser().resolve()
    artifact = _new_artifact(installation.parent)
    report: dict[str, object] = {
        "validator": "validate_alliance_reload.py",
        "status": "running",
        "installation": str(installation),
        "before_probes": str(before_probes),
        "save_name": args.save_name,
        "expected_date_raw": args.expected_date_raw,
        "sav_outcome": args.sav_outcome,
        "additional_alliance_expectations": dict(args.expect_alliance),
        "output_directory": str(artifact),
        "native_token_generated": False,
        "business_submission": False,
    }

    try:
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
            raise ReloadValidationError("EXPECTED_DATE_RAW_MUST_BE_INT")
        if args.expected_save_sha256 is not None and not _SHA256_RE.fullmatch(args.expected_save_sha256):
            raise ReloadValidationError("EXPECTED_SAVE_SHA256_INVALID")
        before_files = {
            spec.name: _snapshot_record(before_probes / f"{spec.name}.json", spec.name)
            for spec in PROBE_SPECS
        }
        before_control = _control_summary(before_files["control_state"]["snapshot"])
        before_diplomats = _diplomat_semantics(before_files["diplomats"]["snapshot"])
        before_complete = all(
            entry["snapshot_completeness"].get("complete") is True
            for entry in before_files.values()
            if isinstance(entry.get("snapshot_completeness"), dict)
        ) and len(before_files) == len(PROBE_SPECS)
        report["before"] = {
            "control": before_control,
            "diplomats": before_diplomats,
            "probe_files": {name: _public_snapshot_record(item) for name, item in before_files.items()},
            "snapshot_complete": before_complete,
        }

        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        health_before = wait_runtime_ready(session, restore_minimized=True)
        report["health_before"] = health_before
        if health_before.get("status") != "ready":
            raise ReloadValidationError("SESSION_NOT_READY")
        if health_before.get("date_raw") != args.expected_date_raw:
            raise ReloadValidationError("HEALTH_DATE_MISMATCH")

        after_files = _run_snapshots(session, artifact / "probes")
        after_control = _control_summary(after_files["control_state"]["snapshot"])
        after_diplomats = _diplomat_semantics(after_files["diplomats"]["snapshot"])
        health_after_probes = session.health()
        after_complete = all(
            entry["snapshot_completeness"].get("complete") is True
            for entry in after_files.values()
            if isinstance(entry.get("snapshot_completeness"), dict)
        ) and len(after_files) == len(PROBE_SPECS)
        report["after"] = {
            "control": after_control,
            "diplomats": after_diplomats,
            "probe_files": {name: _public_snapshot_record(item) for name, item in after_files.items()},
            "snapshot_complete": after_complete,
            "health": health_after_probes,
        }

        journal_path = artifact / "diplomacy.sqlite3"
        query_results: dict[str, dict[str, object]] = {}
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in dict.fromkeys(("SAV", "LIT", *dict(args.expect_alliance))):
                try:
                    inspection = api.inspect_diplomatic_action(
                        "dissolve_alliance", "FRA", recipient, phase="initiate", parameters={}
                    )
                    query_results[recipient] = _public_inspection(inspection)
                except Exception as error:
                    query_results[recipient] = {
                        "status": "unknown",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
        _write_json(artifact / "dissolve-queries.json", query_results)
        report["dissolve_queries"] = query_results

        save_path = _find_save(args.save_name)
        save_record = _hash_file(save_path, maximum=_MAX_SAVE_BYTES)
        save_record["expected_sha256"] = args.expected_save_sha256.lower() if args.expected_save_sha256 else None
        save_record["sha256_matches_expected"] = (
            args.expected_save_sha256 is None
            or save_record["sha256"] == args.expected_save_sha256.lower()
        )
        report["save"] = save_record

        source_baseline = _find_source_baseline(before_probes)
        report["source_r3"] = _source_check(source_baseline)

        health_after = session.health()
        report["health_after"] = health_after
        checks: dict[str, bool] = {
            "health_ready": (
                health_before.get("status") == "ready"
                and health_before.get("complete") is True
                and health_after.get("status") == "ready"
                and health_after.get("complete") is True
            ),
            "player_por": after_control.get("player_slot") == 189,
            "paused": after_control.get("paused_flag") == 1,
            "date_matches_expected": after_control.get("date_raw") == args.expected_date_raw,
            "health_date_matches_expected": health_after.get("date_raw") == args.expected_date_raw,
            "snapshot_complete_before": before_complete,
            "snapshot_complete_after": after_complete,
            "diplomat_semantics_preserved": before_diplomats == after_diplomats,
            "save_sha256_present": isinstance(save_record.get("sha256"), str),
            "save_sha256_matches_expected": save_record["sha256_matches_expected"] is True,
            "source_r3_unchanged": report["source_r3"].get("unchanged") is True
            if isinstance(report.get("source_r3"), dict) else False,
        }
        checks.update(_dissolve_checks(query_results, args.sav_outcome, dict(args.expect_alliance)))
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except (ReloadValidationError, KeyError, TypeError, ValueError, OSError) as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    except Exception as error:  # keep the artifact for operator diagnosis
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
