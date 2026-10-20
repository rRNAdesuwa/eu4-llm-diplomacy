"""Freeze the R65 peace-consequence delivery after final evidence passes.

The finalizer is deliberately inert when imported.  Running it validates the
immutable D build, the final query/save/family/test reports, then creates a
new delivery directory exactly once.  Native DLLs and EU4 saves remain
external evidence; the save hash is carried through from the save checker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work" / "runtime"
DEFAULT_OUTPUT = "work/runtime/r65-python-docs-delivery-20261019-001"
DEFAULT_BUILD = (
    "work/runtime/diplomacy-query-20261019-r65-peace-consequences-d"
    "/build-manifest.json"
)
DEFAULT_INSTALLATION = (
    "work/runtime/diplomacy-query-20261019-r65-peace-consequences-d"
    "/installation.json"
)
DEFAULT_MAIN = "work/runtime/r65-peace-consequence-queries-20261019-004/report.json"
DEFAULT_SAVECHECK = "work/runtime/r65-peace-preview-save-check-20261019-001/report.json"
DEFAULT_FAMILIES = "work/runtime/r65-peace-consequence-families-20261019-003/report.json"
DEFAULT_TESTS = "work/runtime/r65-final-python-unit-20261019-004/report.json"
DEFAULT_PROGRESS = "work/runtime/r65-progress.json"

MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
NATIVE_SOURCE_COUNT = 85
SAVE_SHA = "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251"

# This is the stable R65 common-peace action catalog.  The family report may
# contain extra duplicate province rows, but every action below needs one
# complete native parent/validator/parity/unchanged observation.
REQUIRED_ACTIONS = (
    "white_peace",
    "demand_ducats",
    "cede_province",
    "war_reparations",
    "transfer_trade_power",
    "concede_defeat",
    "annul_treaties",
    "humiliate_rival",
    "show_strength",
    "force_religion",
    "return_core",
    "revoke_core",
    "release_subject",
    "transfer_subject",
    "release_nation",
    "force_vassalization",
    "form_personal_union",
    "grant_independence",
    "full_annexation",
)

# These are the source/document artifacts that belong in the R65 Python
# delivery.  Native files are verified against the D build manifest below,
# rather than copied into the bundle.
SOURCE_FILES = (
    "bridge/diplomacy.py",
    "bridge/diplomacy_catalog.py",
    "bridge/native_text.py",
    "bridge/peace_consequences.py",
    "bridge/peace_costs.py",
    "bridge/peace_execution.py",
    "bridge/peace_core.py",
    "bridge/peace_country.py",
    "bridge/tests/test_peace_consequences_r65.py",
    "bridge/tests/test_peace_consequences_r65_real.py",
    "bridge/tests/test_peace_consequences_r65_orl_negative.py",
    "bridge/tests/test_peace_consequences_r65_families.py",
    "bridge/tests/test_start_diplomacy_observer.py",
    "bridge/tests/fixtures/peace_consequences_r65_d_real.json",
    "bridge/tests/fixtures/peace_consequences_r65_orl_negative.json",
    "bridge/tests/fixtures/peace_consequences_r65_families.json",
    "tools/start_diplomacy_observer.py",
    "work/run_peace_consequence_queries.py",
    "work/run_peace_consequence_family_queries.py",
    "work/reproject_r65_family_queries.py",
    "work/verify_r65_peace_preview_save.py",
    "work/probe_frame_thread_context.py",
    "work/analyze_native_crash.py",
    "work/finalize_r65_peace_delivery.py",
    "docs/议和后果接口与运行验收.md",
    "docs/外交开发推进复盘.md",
    "docs/外交能力矩阵.md",
    "docs/外交接口开发方案.md",
    "docs/外交系统说明.md",
    "docs/外交运行工作流.md",
    "PLAN.md",
    "HANDOFF.md",
    "work/临时prompt/外交系统开发goal.md",
)


class DeliveryError(RuntimeError):
    """Raised before any delivery output is created."""


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def read_json(value: str | Path) -> dict[str, Any]:
    path = resolve_path(value)
    if not path.is_file():
        raise DeliveryError(f"missing JSON evidence: {relative_path(path)}")
    if path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise DeliveryError(
            f"JSON evidence exceeds bounded read limit: {relative_path(path)}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DeliveryError(f"invalid JSON evidence: {relative_path(path)}") from exc
    if not isinstance(data, dict):
        raise DeliveryError(f"JSON evidence is not an object: {relative_path(path)}")
    return data


def sha256_stream(path: Path) -> str:
    if not path.is_file():
        raise DeliveryError(f"missing file for hash: {relative_path(path)}")
    if path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise DeliveryError(
            f"file exceeds bounded hash limit: {relative_path(path)}"
        )
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_and_hash(source: Path, destination: Path) -> dict[str, Any]:
    """Copy a small artifact and hash the bytes in the same streaming pass."""
    if source.suffix.lower() in {".dll", ".eu4"}:
        raise DeliveryError(f"refusing to copy binary/save artifact: {source}")
    if not source.is_file():
        raise DeliveryError(f"missing delivery source: {relative_path(source)}")
    size = source.stat().st_size
    if size > MAX_EVIDENCE_BYTES:
        raise DeliveryError(
            f"delivery source exceeds bounded copy limit: {relative_path(source)}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0
    with source.open("rb") as source_stream, destination.open("wb") as target:
        for block in iter(lambda: source_stream.read(64 * 1024), b""):
            target.write(block)
            digest.update(block)
            written += len(block)
    return {
        "path": relative_path(source),
        "bytes": written,
        "sha256": digest.hexdigest(),
    }


def require_true(mapping: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    if mapping.get(key) is not True:
        errors.append(f"{label}.{key} is not true")


def require_status(report: dict[str, Any], path: str, errors: list[str]) -> None:
    if report.get("status") != "passed":
        errors.append(f"{path}: status is not passed")


def _path_is_evidence(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = resolve_path(value)
    return path.is_file() and path.suffix.lower() not in {".dll", ".eu4"}


def _native_parent_proof(case: dict[str, Any]) -> bool:
    """Require a real event parent/slice, not a copied public projection."""
    event_path = (
        case.get("native_event_path")
        or case.get("parent_event_path")
        or case.get("native_event")
    )
    if not _path_is_evidence(event_path):
        return False
    native_slice = case.get("native_slice")
    if not isinstance(native_slice, dict):
        return False
    return native_slice.get("complete") is True and native_slice.get("status") == "ok"


def _family_case_complete(
    case: dict[str, Any], *, require_native_consequences: bool = True
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if case.get("error") is not None:
        missing.append("error")
    if case.get("availability") in {"unknown", "invalid"}:
        missing.append(f"availability={case.get('availability')}")
    if not _native_parent_proof(case):
        missing.append("native_parent")
    required = (
        "native_validator",
        "raw_header_contract",
        "raw_public_parity",
        "object_unchanged",
        "consequence_contract",
        "public_contract",
        "private_fields_absent",
    )
    if require_native_consequences:
        required = (*required[:4], "native_consequences_present", *required[4:])
    for key in required:
        if case.get(key) is not True:
            missing.append(key)
    # Newer state-evidence reports may expose the parent proof explicitly.
    # When present, it is mandatory; the event/slice check above remains the
    # compatibility proof for the existing family schema.
    for key in (
        "parent_validator",
        "parent_contract",
        "parent_context_verified",
        "native_parent_verified",
    ):
        if key in case and case.get(key) is not True:
            missing.append(key)
    if "native_public_parity" in case and case.get("native_public_parity") is not True:
        missing.append("native_public_parity")
    return not missing, missing


def validate_build(
    build_path: str, installation_path: str, errors: list[str]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    build = read_json(build_path)
    installation = read_json(installation_path)
    if build.get("compiled") is not True:
        errors.append("D build manifest is not compiled")
    sources = build.get("sources")
    if not isinstance(sources, list) or len(sources) != NATIVE_SOURCE_COUNT:
        errors.append(
            f"D build source count is {len(sources) if isinstance(sources, list) else 'invalid'}, "
            f"expected {NATIVE_SOURCE_COUNT}"
        )
        sources = sources if isinstance(sources, list) else []
    dll_sha = build.get("dll_sha256")
    if not isinstance(dll_sha, str) or len(dll_sha) != 64:
        errors.append("D build manifest lacks a valid DLL SHA-256")
    if installation.get("dll_sha256") != dll_sha:
        errors.append("D installation DLL SHA differs from D build")
    if installation.get("installation_attempted") is not True:
        errors.append("D installation was not attempted")
    if installation.get("installation_started") is not True:
        errors.append("D installation did not start")
    if installation.get("installation_returncode") != 0:
        errors.append("D installation return code is not zero")
    installed_modules = installation.get("modules_after_install")
    if isinstance(installed_modules, list):
        if not any(
            isinstance(module, dict) and module.get("sha256") == dll_sha
            for module in installed_modules
        ):
            errors.append("D installation has no matching loaded module record")

    verified_sources: list[dict[str, Any]] = []
    for entry in sources:
        if not isinstance(entry, dict):
            errors.append("D build source entry is not an object")
            continue
        name, expected = entry.get("name"), entry.get("sha256")
        if not isinstance(name, str) or not isinstance(expected, str):
            errors.append("D build source entry lacks name/sha256")
            continue
        source = ROOT / "work" / "native" / name
        try:
            actual = sha256_stream(source)
        except DeliveryError as exc:
            errors.append(str(exc))
            actual = None
        if actual != expected:
            errors.append(f"native source hash mismatch: {name}")
        verified_sources.append(
            {"name": name, "sha256": expected, "actual_sha256": actual, "matched": actual == expected}
        )
    return build, installation, verified_sources


def validate_main(report: dict[str, Any], path: str, errors: list[str]) -> dict[str, Any]:
    require_status(report, path, errors)
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        errors.append(f"{path}: expected exactly 12 cases")
        cases = cases if isinstance(cases, list) else []
    required_checks = (
        "before_por_paused",
        "after_por_paused_same_date",
        "same_session_and_date",
        "discovery_one_war",
        "no_business_submission",
        "case_consequence_validators",
        "case_native_validators",
        "case_object_unchanged",
        "case_public_contracts",
        "case_raw_headers",
        "case_raw_public_parity",
        "public_queries_no_private_identifiers",
        "before_health_ready",
        "after_health_ready",
        "case_count_nonzero",
    )
    checks = report.get("checks", {})
    if not isinstance(checks, dict):
        errors.append(f"{path}.checks is not an object")
        checks = {}
    for key in required_checks:
        require_true(checks, key, f"{path}.checks", errors)
    for key, value in checks.items():
        if isinstance(value, bool) and value is not True:
            errors.append(f"{path}.checks.{key} is not true")
    if report.get("business_submission") is not False:
        errors.append(f"{path}: business_submission must be false")
    if report.get("execute_call_count") not in (0, None):
        errors.append(f"{path}: execute_call_count is nonzero")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"{path}: case {index} is not an object")
            continue
        ok, missing = _family_case_complete(case, require_native_consequences=False)
        if not ok:
            errors.append(
                f"{path}: main case {case.get('action_id', index)} incomplete: "
                + ",".join(missing)
            )
    return {
        "path": path,
        "status": report.get("status"),
        "case_count": len(cases),
        "check_count": len(checks) if isinstance(checks, dict) else 0,
    }


def validate_save(report: dict[str, Any], path: str, errors: list[str]) -> dict[str, Any]:
    require_status(report, path, errors)
    checks = report.get("checks", {})
    for key, value in (checks.items() if isinstance(checks, dict) else ()):
        if value is not True:
            errors.append(f"{path}.checks.{key} is not true")
    province = report.get("province_reconciliation")
    coalition = report.get("coalition_reconciliation")
    province = province if isinstance(province, dict) else {}
    coalition = coalition if isinstance(coalition, dict) else {}
    rows = province.get("row_checks")
    aggregates = province.get("aggregate_checks")
    comparisons = coalition.get("comparisons")
    rows = rows if isinstance(rows, list) else []
    aggregates = aggregates if isinstance(aggregates, list) else []
    comparisons = comparisons if isinstance(comparisons, list) else []
    if len(rows) != 38:
        errors.append(f"{path}: expected 38 province rows, got {len(rows)}")
    if len(comparisons) != 125:
        errors.append(f"{path}: expected 125 coalition rows, got {len(comparisons)}")
    if coalition.get("comparison_count") != 125:
        errors.append(f"{path}: coalition comparison_count is not 125")
    if province.get("all_rows_match") is not True:
        errors.append(f"{path}: all_rows_match is not true")
    if province.get("all_aggregates_match") is not True:
        errors.append(f"{path}: all_aggregates_match is not true")
    if coalition.get("all_match") is not True:
        errors.append(f"{path}: coalition all_match is not true")
    if coalition.get("difference_count") != 0 or coalition.get("unknown_count") != 0:
        errors.append(f"{path}: coalition differences or unknowns remain")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{path}: province row {index} is not an object")
            continue
        for key in ("already_core_match", "native_adds_overextension", "core_zero_admin_oe_ok"):
            if row.get(key) is not True:
                errors.append(f"{path}: province row {index}.{key} is not true")
    for index, row in enumerate(aggregates):
        if not isinstance(row, dict):
            errors.append(f"{path}: aggregate row {index} is not an object")
            continue
        for key in ("expected_aggregate_match", "native_rows_sum_match"):
            if row.get(key) is not True:
                errors.append(f"{path}: aggregate row {index}.{key} is not true")
    for index, row in enumerate(comparisons):
        if not isinstance(row, dict):
            errors.append(f"{path}: coalition row {index} is not an object")
            continue
        if row.get("status") not in {"matched", "match", "ok", "passed"}:
            errors.append(f"{path}: coalition row {index} is not matched")
    source = report.get("save", {}).get("source", {})
    source_sha = source.get("source_sha256") if isinstance(source, dict) else None
    if source_sha != SAVE_SHA:
        errors.append(f"{path}: source save SHA is not the known R63 SHA")
    return {
        "path": path,
        "status": report.get("status"),
        "province_row_count": len(rows),
        "province_aggregate_count": len(aggregates),
        "coalition_row_count": len(comparisons),
        "source_save_sha256": source_sha,
        "source_save_path": source.get("path") if isinstance(source, dict) else None,
    }


def validate_families(
    reports: Iterable[tuple[str, dict[str, Any]]], errors: list[str]
) -> dict[str, Any]:
    family_results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, report in reports:
        require_status(report, path, errors)
        checks = report.get("checks", {})
        if not isinstance(checks, dict):
            errors.append(f"{path}.checks is not an object")
            checks = {}
        for key, value in checks.items():
            if isinstance(value, bool) and value is not True:
                errors.append(f"{path}.checks.{key} is not true")
        required_checks = report.get("required_checks")
        if not isinstance(required_checks, dict):
            errors.append(f"{path}.required_checks is missing")
            required_checks = {}
        for key, value in required_checks.items():
            if value is not True:
                errors.append(f"{path}.required_checks.{key} is not true")
        if report.get("required_case_count") != len(REQUIRED_ACTIONS):
            errors.append(
                f"{path}.required_case_count is not {len(REQUIRED_ACTIONS)}"
            )
        if report.get("required_cases_with_native_public_parity") != len(REQUIRED_ACTIONS):
            errors.append(
                f"{path}.required_cases_with_native_public_parity is not "
                f"{len(REQUIRED_ACTIONS)}"
            )
        action_ids = report.get("action_ids")
        if not isinstance(action_ids, list):
            action_ids = [
                case.get("action_id")
                for case in report.get("cases", [])
                if isinstance(case, dict) and case.get("action_id")
            ]
        seen.update(item for item in action_ids if isinstance(item, str))
        cases = report.get("cases", [])
        cases = cases if isinstance(cases, list) else []
        complete_actions: list[str] = []
        per_action: dict[str, Any] = {}
        for action in REQUIRED_ACTIONS:
            candidates = [
                case for case in cases
                if isinstance(case, dict)
                and case.get("action_id", case.get("action")) == action
                and case.get("optional") is not True
            ]
            good = []
            for case in candidates:
                ok, missing = _family_case_complete(case)
                if ok:
                    good.append(case)
            if good:
                complete_actions.append(action)
            else:
                per_action[action] = {
                    "candidate_count": len(candidates),
                    "missing": (
                        _family_case_complete(candidates[0])[1]
                        if candidates else ["missing_action"]
                    ),
                }
                errors.append(f"{path}: action {action} lacks a complete native case")
        family_results.append(
            {
                "path": path,
                "status": report.get("status"),
                "case_count": len(cases),
                "complete_action_count": len(complete_actions),
                "complete_actions": complete_actions,
                "incomplete_actions": per_action,
            }
        )
    missing_catalog = sorted(set(REQUIRED_ACTIONS) - seen)
    if missing_catalog:
        errors.append("family reports omit action IDs: " + ",".join(missing_catalog))
    if not reports:
        errors.append("no --families report was supplied")
    complete = bool(reports) and not missing_catalog and all(
        not result["incomplete_actions"] for result in family_results
    )
    return {
        "required_action_count": len(REQUIRED_ACTIONS),
        "required_actions": list(REQUIRED_ACTIONS),
        "observed_action_ids": sorted(seen),
        "reports": family_results,
        "complete": complete,
    }


def validate_tests(
    reports: Iterable[tuple[str, dict[str, Any]]], errors: list[str]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not reports:
        errors.append("no --tests report was supplied")
    for path, report in reports:
        require_status(report, path, errors)
        if "exit_code" in report and report.get("exit_code") != 0:
            errors.append(f"{path}: exit_code is not zero")
        for key in ("failed_tests", "failed_subtests"):
            if key in report and report.get(key) not in (0, None):
                errors.append(f"{path}: {key} is nonzero")
        results.append(
            {
                "path": path,
                "status": report.get("status"),
                "passed_tests": report.get("passed_tests"),
                "passed_subtests": report.get("passed_subtests"),
            }
        )
    return results


def evidence_record(path: str) -> dict[str, Any]:
    absolute = resolve_path(path)
    if absolute.suffix.lower() in {".dll", ".eu4"}:
        raise DeliveryError(f"evidence path may not be a DLL/save: {path}")
    return {
        "path": relative_path(absolute),
        "bytes": absolute.stat().st_size,
        "sha256": sha256_stream(absolute),
        "copied": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--build", default=DEFAULT_BUILD)
    parser.add_argument("--installation", default=DEFAULT_INSTALLATION)
    parser.add_argument("--main", default=DEFAULT_MAIN)
    parser.add_argument("--savecheck", default=DEFAULT_SAVECHECK)
    parser.add_argument("--families", action="append", default=None)
    parser.add_argument("--tests", action="append", default=None)
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    family_paths = args.families or [DEFAULT_FAMILIES]
    test_paths = args.tests or [DEFAULT_TESTS]
    output = resolve_path(args.output)
    if output.exists():
        raise DeliveryError(f"refusing to overwrite immutable delivery: {output}")

    errors: list[str] = []
    build, installation, native_sources = validate_build(
        args.build, args.installation, errors
    )
    main_report = read_json(args.main)
    main_binding = main_report.get("build_binding")
    if not isinstance(main_binding, dict):
        errors.append(f"{args.main}: build_binding is missing")
    else:
        if main_binding.get("build_manifest_dll_sha256") != build.get("dll_sha256"):
            errors.append(f"{args.main}: build binding DLL differs from D build")
        if main_binding.get("installation_matches_build_manifest") is not True:
            errors.append(f"{args.main}: installation/build binding is not verified")
    save_report = read_json(args.savecheck)
    family_reports = [(path, read_json(path)) for path in family_paths]
    test_reports = [(path, read_json(path)) for path in test_paths]
    main_summary = validate_main(main_report, args.main, errors)
    save_summary = validate_save(save_report, args.savecheck, errors)
    family_summary = validate_families(family_reports, errors)
    test_summary = validate_tests(test_reports, errors)
    if errors:
        raise DeliveryError("R65 delivery validation failed:\n- " + "\n- ".join(errors))

    # Validate and collect report hashes before creating the output directory.
    evidence_paths = [args.build, args.installation, args.main, args.savecheck]
    evidence_paths.extend(family_paths)
    evidence_paths.extend(test_paths)
    evidence: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for path in evidence_paths:
        record = evidence_record(path)
        if record["path"] not in seen_evidence:
            evidence.append(record)
            seen_evidence.add(record["path"])

    records: list[dict[str, Any]] = []
    output.mkdir(parents=True, exist_ok=False)
    try:
        for relative in SOURCE_FILES:
            source = ROOT / relative
            destination = output / "source" / relative
            records.append(copy_and_hash(source, destination))
        copied_evidence: list[dict[str, Any]] = []
        for path in evidence_paths:
            source = resolve_path(path)
            key = relative_path(source)
            if key in {record["path"] for record in copied_evidence}:
                continue
            destination = output / "evidence" / key
            copied_evidence.append(copy_and_hash(source, destination))

        save_source = save_report.get("save", {}).get("source", {})
        source_save_sha = (
            save_source.get("source_sha256")
            if isinstance(save_source, dict)
            else None
        )
        progress = {
            "stage": "R65",
            "status": "r65_peace_consequence_delivery_archived",
            "goal_status": "active",
            "goal_active": True,
            "main_query": main_summary,
            "save_check": save_summary,
            "family_contract": family_summary,
            "tests": test_summary,
            "native": {
                "build_manifest": relative_path(resolve_path(args.build)),
                "installation": relative_path(resolve_path(args.installation)),
                "dll_sha256": build.get("dll_sha256"),
                "source_count": len(native_sources),
                "source_hashes_match_d_build_once": all(
                    item["matched"] for item in native_sources
                ),
                "dll_copied": False,
            },
            "source_save": {
                "path": save_source.get("path") if isinstance(save_source, dict) else None,
                "sha256": source_save_sha,
                "known_sha256": SAVE_SHA,
                "sha256_reused": source_save_sha == SAVE_SHA,
                "copied": False,
                "hash_recomputed": False,
            },
            "delivery": relative_path(output / "manifest.json"),
            "save_reload_validation": False,
            "no_game_or_rea_run": True,
        }
        manifest = {
            "status": "delivered",
            "stage": "R65",
            "source_count": len(records),
            "total_bytes": sum(item["bytes"] for item in records),
            "sources": records,
            "evidence_copied_once": copied_evidence,
            "evidence_links": evidence,
            "native_source_hashes": native_sources,
            "native_reference": {
                "build_manifest": relative_path(resolve_path(args.build)),
                "installation": relative_path(resolve_path(args.installation)),
                "dll_sha256": build.get("dll_sha256"),
                "source_count": len(native_sources),
                "dll_copied": False,
            },
            "save_reference": progress["source_save"],
            "constraints": {
                "save_files_copied": False,
                "dll_copied": False,
                "large_runtime_logs_copied": False,
                "save_sha_recomputed": False,
                "goal_status": "active",
            },
            "progress": progress,
        }
        write_json(output / "manifest.json", manifest)
        write_json(ROOT / DEFAULT_PROGRESS, progress)
    except Exception:
        # Do not silently leave an apparently complete bundle after a partial
        # copy.  The immutable output is deliberately left for inspection and
        # a later run must choose a new output path.
        raise

    print(
        json.dumps(
            {
                "status": "delivered",
                "manifest": relative_path(output / "manifest.json"),
                "progress": DEFAULT_PROGRESS,
                "source_count": len(records),
                "native_source_count": len(native_sources),
                "family_required_actions": len(REQUIRED_ACTIONS),
                "save_province_rows": save_summary["province_row_count"],
                "save_coalition_rows": save_summary["coalition_row_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
