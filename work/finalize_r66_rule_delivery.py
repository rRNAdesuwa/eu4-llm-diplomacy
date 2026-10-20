"""Prepare the bounded R66 rule/consequence delivery.

The finalizer is inert when imported.  When run, it validates the two R66
build/install manifests, the real CB and net-overextension query batches, the
invalid-request report, and any explicitly supplied save/test reports.  It
copies only small source/evidence artifacts into a new immutable delivery
directory; EU4 saves, DLLs, control logs, and native binaries stay external.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work" / "runtime"
DEFAULT_OUTPUT = "work/runtime/r66-python-docs-delivery-20261019-001"
DEFAULT_PROGRESS = "work/runtime/r66-progress.json"

DEFAULT_BUILD_A = (
    "work/runtime/diplomacy-query-20261019-r66-rules-netoe-a"
    "/build-manifest.json"
)
DEFAULT_INSTALL_A = (
    "work/runtime/diplomacy-query-20261019-r66-rules-netoe-a"
    "/installation.json"
)
DEFAULT_BUILD_B = (
    "work/runtime/diplomacy-query-20261019-r66-rules-netoe-b"
    "/build-manifest.json"
)
DEFAULT_INSTALL_B = (
    "work/runtime/diplomacy-query-20261019-r66-rules-netoe-b"
    "/installation.json"
)
# C is the repaired cap build.  It is optional until the new native run has
# produced both manifests; when supplied it becomes the current source-hash
# baseline while A/B remain immutable historical references.

DEFAULT_CB = "work/runtime/r66-cb-rule-queries-20261019-002/report.json"
DEFAULT_CB_SOURCE = "work/runtime/r66-cb-rule-queries-20261019-001/report.json"
DEFAULT_NETOE_A = (
    "work/runtime/r66-netoe-consequence-queries-20261019-002/report.json"
)
DEFAULT_NETOE_B = (
    "work/runtime/r66-netoe-consequence-queries-b-20261019-001/report.json"
)
DEFAULT_FAMILY_C = "work/runtime/r66-cap-family-queries-20261019-001/report.json"
DEFAULT_INVALID = "work/runtime/r66-invalid-peace-requests-20261019-001/report.json"
DEFAULT_SAVECHECKS = (
    "work/runtime/r66-overextension-save-check-a-20261019-001/report.json",
    "work/runtime/r66-overextension-save-check-20261019-001/report.json",
)
DEFAULT_SCENE = "work/runtime/r66-noncore-scene-20261019-001/report.json"
DEFAULT_CAP_REPORT = "work/runtime/r66-warscore-cap-20261019-004/report.json"
DEFAULT_EXTRA_REPORTS = (
    "work/runtime/diplomacy-query-20261019-r66-rules-netoe-c"
    "/advance-context-58163b025c584f95b4933a2b94b30b3a/report.json",
    "work/runtime/diplomacy-query-20261019-r66-rules-netoe-b"
    "/advance-context-9670c9497e68408495076043ec5fe8ca/report.json",
)
HISTORICAL_CAP_REPORTS = (
    "work/runtime/r66-warscore-cap-20261019-001/report.json",
    "work/runtime/r66-warscore-cap-20261019-002/report.json",
    "work/runtime/r66-warscore-cap-20261019-003/report.json",
)

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
NATIVE_SOURCE_COUNT = 87

CB_REQUIRED_CHECKS = (
    "before_por_paused",
    "after_por_paused_same_date",
    "catalog_query_peace_term_rules",
    "goal_double_sided_complete",
    "disabled_table_nonempty",
    "selected_requests_matched",
    "unmatched_requests_explicit_unavailable",
    "all_native_public_parity",
    "all_corrected_public_projections_verified",
    "no_business_submission",
)
CB_CASE_CHECKS = (
    "declared_terms_keep_target_evaluation",
    "native_header_and_validator",
    "native_session_query_date_actor_recipient",
    "object_unchanged",
    "peace_options_public_parity",
    "peace_options_valid",
    "public_no_private_fields",
    "selection_echo",
    "selection_matched_or_discovery",
    "unavailable_is_explicit",
)

NETOE_REQUIRED_CHECKS = (
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
NETOE_CASE_CHECKS = (
    "consequence_contract",
    "native_validator",
    "raw_header_contract",
    "raw_public_parity",
    "object_unchanged",
    "public_contract",
    "private_fields_absent",
)

INVALID_REQUIRED_CHECKS = (
    "paused_por_same_date",
    "two_negative_cases",
    "all_public_and_native_reasons",
    "no_business_submission",
)

FAMILY_REQUIRED_CASE_NAMES = (
    "white_peace",
    "demand_ducats",
    "cede_province_88_FRA",
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

FAMILY_REQUIRED_CHECKS = (
    "before_por_paused",
    "after_por_paused_same_date",
    "same_session",
    "catalog_19_query_consequences",
    "all_action_ids_queried",
    "all_required_native_public_parity",
    "public_results_no_private_fields",
    "no_required_unknown_or_invalid",
    "no_business_submission",
)

FAMILY_CASE_CHECKS = (
    "consequence_contract",
    "native_consequences_present",
    "native_validator",
    "native_public_parity",
    "raw_header_contract",
    "raw_public_parity",
    "object_unchanged",
    "public_contract",
    "private_fields_absent",
)

# These are deliberately explicit.  The native source is referenced by the
# immutable A/B manifests and is not copied into the Python delivery.
SOURCE_FILES = (
    "bridge/diplomacy.py",
    "bridge/declarewar_peace_options.py",
    "bridge/peace_overextension.py",
    "bridge/peace_rejection.py",
    "bridge/peace_consequences.py",
    "bridge/tests/test_declarewar_peace_options.py",
    "bridge/tests/test_peace_overextension.py",
    "bridge/tests/test_peace_rejection.py",
    "bridge/tests/test_r66_net_overextension_real.py",
    "bridge/tests/test_r66_warscore_cap_real.py",
    "bridge/tests/fixtures/r66_net_overextension_real.json",
    "bridge/tests/fixtures/r66_warscore_cap_real.json",
    "bridge/tests/test_r66_cb_rule_real.py",
    "bridge/tests/test_r66_peace_rejection_real.py",
    "bridge/tests/fixtures/r66_cb_rule_real.json",
    "bridge/tests/fixtures/r66_peace_rejection_real.json",
    "work/run_r66_cb_rule_queries.py",
    "work/reproject_r66_cb_rules.py",
    "work/run_r66_invalid_peace_requests.py",
    "work/run_peace_consequence_queries.py",
    "work/prepare_r66_noncore_scene.py",
    "work/verify_r66_overextension_save.py",
    "work/run_r66_warscore_cap.py",
    "work/validate_alliance_reload.py",
    "work/finalize_r66_rule_delivery.py",
    "docs/宣战条款与议和净OE预览.md",
    "docs/议和后果接口与运行验收.md",
    "docs/宣战接口与运行验收.md",
    "docs/议和接口与运行验收.md",
    "docs/外交能力矩阵.md",
    "docs/外交接口开发方案.md",
    "docs/外交系统说明.md",
    "docs/外交开发推进复盘.md",
    "docs/外交运行工作流.md",
    "PLAN.md",
    "HANDOFF.md",
    "work/临时prompt/外交系统开发goal.md",
)

# New cap-focused unit/fixture names are included when present.  Keeping the
# discovery local to the two test directories lets the finalizer pick up a
# newly added focused test without scanning runtime or the whole repository.
OPTIONAL_CAP_SOURCE_NAMES = (
    "bridge/tests/test_r66_warscore_cap_real.py",
    "bridge/tests/test_r66_warscore_cap.py",
    "bridge/tests/test_r66_net_overextension_real.py",
    "bridge/tests/test_peace_overextension.py",
    "bridge/tests/fixtures/r66_warscore_cap_real.json",
    "bridge/tests/fixtures/r66_warscore_cap.json",
    "bridge/tests/fixtures/r66_net_overextension_real.json",
)


def delivery_source_files() -> tuple[str, ...]:
    """Return required R66 sources plus present cap-focused tests/fixtures."""
    result = list(SOURCE_FILES)
    for raw in OPTIONAL_CAP_SOURCE_NAMES:
        if (ROOT / raw).is_file() and raw not in result:
            result.append(raw)
    return tuple(result)


class DeliveryError(RuntimeError):
    """Raised before a delivery is created when evidence is incomplete."""


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
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise DeliveryError(f"JSON evidence exceeds bounded limit: {relative_path(path)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DeliveryError(f"invalid JSON evidence: {relative_path(path)}") from exc
    if not isinstance(data, dict):
        raise DeliveryError(f"JSON evidence is not an object: {relative_path(path)}")
    return data


def sha256_stream(path: Path) -> str:
    if not path.is_file():
        raise DeliveryError(f"missing file for bounded hash: {relative_path(path)}")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise DeliveryError(f"file exceeds bounded hash limit: {relative_path(path)}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_and_hash(source: Path, destination: Path) -> dict[str, Any]:
    if source.suffix.lower() in {".dll", ".eu4"}:
        raise DeliveryError(f"refusing to copy binary/save artifact: {relative_path(source)}")
    if not source.is_file():
        raise DeliveryError(f"missing delivery source: {relative_path(source)}")
    if source.stat().st_size > MAX_ARTIFACT_BYTES:
        raise DeliveryError(f"delivery source exceeds bounded limit: {relative_path(source)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0
    with source.open("rb") as src, destination.open("wb") as dst:
        for block in iter(lambda: src.read(64 * 1024), b""):
            dst.write(block)
            digest.update(block)
            written += len(block)
    return {"path": relative_path(source), "bytes": written, "sha256": digest.hexdigest()}


def require_status(report: dict[str, Any], path: str, errors: list[str]) -> None:
    if report.get("status") != "passed":
        errors.append(f"{path}: status is not passed")


def require_true(mapping: Any, key: str, label: str, errors: list[str]) -> None:
    if not isinstance(mapping, dict) or mapping.get(key) is not True:
        errors.append(f"{label}.{key} is not true")


def require_all_boolean_checks(mapping: Any, label: str, errors: list[str]) -> None:
    if not isinstance(mapping, dict):
        errors.append(f"{label} is not an object")
        return
    for key, value in mapping.items():
        if isinstance(value, bool) and value is not True:
            errors.append(f"{label}.{key} is not true")


def existing_evidence_path(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return resolve_path(value).is_file()


def native_slice_ok(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("status") != "ok":
        return False
    # CB's bounded-copy record predates ``complete``; consequence records
    # include it but store the path beside the slice metadata. Validate each
    # producer's actual contract instead of requiring nonexistent fields.
    if value.get("complete", value.get("bounded")) is not True:
        return False
    start, end, size = (value.get(key) for key in
                        ("start_offset", "end_offset", "bytes"))
    if (any(type(item) is not int for item in (start, end, size))
            or start < 0 or not 0 < size <= MAX_ARTIFACT_BYTES
            or end - start != size):
        return False
    digest = value.get("sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)):
        return False
    path = value.get("path")
    return path is None or (existing_evidence_path(path)
                            and resolve_path(path).stat().st_size == size)


def validate_installation(
    installation: dict[str, Any], label: str, dll_sha: str, errors: list[str]
) -> None:
    if installation.get("dll_sha256") != dll_sha:
        errors.append(f"{label}: installation DLL differs from build")
    for key, expected in (
        ("installation_attempted", True),
        ("installation_started", True),
    ):
        if installation.get(key) is not expected:
            errors.append(f"{label}.{key} is not true")
    if installation.get("installation_returncode") != 0:
        errors.append(f"{label}.installation_returncode is not zero")
    modules = installation.get("modules_after_install")
    if isinstance(modules, list) and not any(
        isinstance(item, dict) and item.get("sha256") == dll_sha for item in modules
    ):
        errors.append(f"{label}: no matching loaded module record")


def validate_build_pair(
    build_a_path: str,
    install_a_path: str,
    build_b_path: str,
    install_b_path: str,
    build_c_path: str | None,
    install_c_path: str | None,
    errors: list[str],
) -> dict[str, Any]:
    build_a = read_json(build_a_path)
    install_a = read_json(install_a_path)
    build_b = read_json(build_b_path)
    install_b = read_json(install_b_path)
    build_c: dict[str, Any] | None = None
    install_c: dict[str, Any] | None = None
    if bool(build_c_path) != bool(install_c_path):
        errors.append("C build and installation must be supplied together")
    if build_c_path and install_c_path:
        build_c = read_json(build_c_path)
        install_c = read_json(install_c_path)
    for label, build in (("A build", build_a), ("B build", build_b)):
        if build.get("compiled") is not True:
            errors.append(f"{label}.compiled is not true")
    if build_c is not None:
        if build_c.get("compiled") is not True:
            errors.append("C build.compiled is not true")
    dll_a = build_a.get("dll_sha256")
    dll_b = build_b.get("dll_sha256")
    if not isinstance(dll_a, str) or len(dll_a) != 64:
        errors.append("A build lacks a valid DLL SHA-256")
    if not isinstance(dll_b, str) or len(dll_b) != 64:
        errors.append("B build lacks a valid DLL SHA-256")
    if dll_a != dll_b:
        errors.append("A/B DLL SHA-256 differs")
    validate_installation(install_a, "A installation", dll_a if isinstance(dll_a, str) else "", errors)
    validate_installation(install_b, "B installation", dll_b if isinstance(dll_b, str) else "", errors)
    dll_c = build_c.get("dll_sha256") if build_c is not None else None
    if build_c is not None:
        if not isinstance(dll_c, str) or len(dll_c) != 64:
            errors.append("C build lacks a valid DLL SHA-256")
        validate_installation(
            install_c or {}, "C installation", dll_c if isinstance(dll_c, str) else "", errors
        )

    sources_a = build_a.get("sources")
    sources_b = build_b.get("sources")
    if not isinstance(sources_a, list) or len(sources_a) != NATIVE_SOURCE_COUNT:
        errors.append(f"A build source count is not {NATIVE_SOURCE_COUNT}")
        sources_a = sources_a if isinstance(sources_a, list) else []
    if not isinstance(sources_b, list) or len(sources_b) != NATIVE_SOURCE_COUNT:
        errors.append(f"B build source count is not {NATIVE_SOURCE_COUNT}")
        sources_b = sources_b if isinstance(sources_b, list) else []

    def source_map(entries: list[Any], label: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append(f"{label} contains a non-object source entry")
                continue
            name, digest = entry.get("name"), entry.get("sha256")
            if not isinstance(name, str) or not isinstance(digest, str):
                errors.append(f"{label} source entry lacks name/sha256")
                continue
            result[name] = digest
        return result

    map_a = source_map(sources_a, "A build")
    map_b = source_map(sources_b, "B build")
    if map_a != map_b:
        errors.append("A/B immutable native source names or manifest hashes differ")

    map_c: dict[str, str] = {}
    if build_c is not None:
        sources_c = build_c.get("sources")
        if not isinstance(sources_c, list) or len(sources_c) != NATIVE_SOURCE_COUNT:
            errors.append(f"C build source count is not {NATIVE_SOURCE_COUNT}")
            sources_c = sources_c if isinstance(sources_c, list) else []
        map_c = source_map(sources_c, "C build")
        if map_c.keys() != map_a.keys():
            errors.append("C source names differ from the immutable A/B source set")

    current_manifest = map_c if build_c is not None else map_a
    current_baseline = "C" if build_c is not None else "A"

    # Hash the current source tree once, against C when supplied.  A/B remain
    # immutable historical manifests and are compared by name/hash only.
    current_sources: list[dict[str, Any]] = []
    for name, expected in sorted(current_manifest.items()):
        source = ROOT / "work" / "native" / name
        try:
            actual = sha256_stream(source)
        except DeliveryError as exc:
            errors.append(str(exc))
            actual = None
        matched = actual == expected
        if not matched:
            errors.append(f"current {current_baseline} native source hash mismatch: {name}")
        current_sources.append(
            {
                "name": name,
                "expected_current_sha256": expected,
                "current_sha256": actual,
                "current_manifest": current_baseline,
                "matched_current_manifest": matched,
                "matched_a_manifest": actual == map_a.get(name),
                "matched_b_manifest": map_b.get(name) == actual,
            }
        )
    return {
        "build_a": {"path": relative_path(resolve_path(build_a_path)), "dll_sha256": dll_a},
        "installation_a": relative_path(resolve_path(install_a_path)),
        "build_b": {"path": relative_path(resolve_path(build_b_path)), "dll_sha256": dll_b},
        "installation_b": relative_path(resolve_path(install_b_path)),
        "build_c": (
            {"path": relative_path(resolve_path(build_c_path)), "dll_sha256": dll_c}
            if build_c_path and build_c is not None
            else None
        ),
        "installation_c": relative_path(resolve_path(install_c_path)) if install_c_path else None,
        "current_session_id": (install_c or install_a).get("session_id"),
        "dll_sha256_equal": dll_a == dll_b,
        "current_dll_sha256": dll_c if build_c is not None else dll_a,
        "current_source_manifest": current_baseline,
        "source_count": len(current_manifest),
        "immutable_ab_source_names_and_hashes_equal": map_a == map_b,
        "source_names_equal": map_a.keys() == map_b.keys() and (
            build_c is None or map_c.keys() == map_a.keys()
        ),
        "current_source_hashes_checked_once": True,
        "current_source_hashes_match_current_manifest": bool(current_sources)
        and all(item["matched_current_manifest"] for item in current_sources),
        "old_ab_manifests_preserved_without_current_rehash": True,
        "source_hashes": current_sources,
    }


def validate_cb(report: dict[str, Any], path: str, errors: list[str]) -> dict[str, Any]:
    require_status(report, path, errors)
    require_all_boolean_checks(report.get("checks"), f"{path}.checks", errors)
    for key in CB_REQUIRED_CHECKS:
        require_true(report.get("checks"), key, f"{path}.checks", errors)
    for key, expected in (
        ("query_only", True),
        ("business_submission", False),
        ("save_requested", False),
        ("advance_requested", False),
        ("restart_requested", False),
    ):
        if report.get(key) is not expected:
            errors.append(f"{path}.{key} is not {expected!r}")
    if report.get("execute_call_count") != 0:
        errors.append(f"{path}.execute_call_count is not zero")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        errors.append(f"{path}: expected exactly 9 CB cases")
        cases = cases if isinstance(cases, list) else []
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errors.append(f"{path}.summary is missing")
        summary = {}
    for key, expected in (
        ("case_count", 9),
        ("passed_case_count", 9),
        ("failed_case_count", 0),
    ):
        if summary.get(key) != expected:
            errors.append(f"{path}.summary.{key} is not {expected}")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"{path}: case {index} is not an object")
            continue
        if case.get("status") != "passed":
            errors.append(f"{path}: case {index} status is not passed")
        require_all_boolean_checks(case.get("checks"), f"{path}.case[{index}].checks", errors)
        for key in CB_CASE_CHECKS:
            require_true(case.get("checks"), key, f"{path}.case[{index}].checks", errors)
        if not isinstance(case.get("native_event"), dict):
            errors.append(f"{path}: case {index} has no native event parent")
        if not native_slice_ok(case.get("native_slice")):
            errors.append(f"{path}: case {index} native slice is incomplete")
        if case.get("offline_reprojected") is not True:
            errors.append(f"{path}: case {index} lacks corrected offline projection")
        for key in ("input_path", "public_path"):
            if not existing_evidence_path(case.get(key)):
                errors.append(f"{path}: case {index}.{key} is missing")
    source_report = report.get("source_report")
    if not existing_evidence_path(source_report):
        errors.append(f"{path}: source_report is missing")
    return {
        "path": path,
        "status": report.get("status"),
        "case_count": len(cases),
        "passed_case_count": summary.get("passed_case_count"),
        "source_report": relative_path(resolve_path(source_report)) if isinstance(source_report, str) else None,
        "parent_events_validated": len(cases),
    }


def validate_netoe(
    report: dict[str, Any], path: str, expected_dll: str, errors: list[str]
) -> dict[str, Any]:
    require_status(report, path, errors)
    require_all_boolean_checks(report.get("checks"), f"{path}.checks", errors)
    for key in NETOE_REQUIRED_CHECKS:
        require_true(report.get("checks"), key, f"{path}.checks", errors)
    for key, expected in (
        ("business_submission", False),
        ("save_requested", False),
        ("advance_requested", False),
        ("restart_requested", False),
    ):
        if report.get(key) is not expected:
            errors.append(f"{path}.{key} is not {expected!r}")
    if report.get("execute_call_count") != 0:
        errors.append(f"{path}.execute_call_count is not zero")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        errors.append(f"{path}: expected exactly 12 net-OE cases")
        cases = cases if isinstance(cases, list) else []
    coverage = report.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("valid_case_count") != 12:
        errors.append(f"{path}.coverage.valid_case_count is not 12")
    binding = report.get("build_binding")
    if not isinstance(binding, dict):
        errors.append(f"{path}.build_binding is missing")
    else:
        if binding.get("build_manifest_dll_sha256") != expected_dll:
            errors.append(f"{path}: build binding DLL differs from paired build")
        if binding.get("installation_dll_sha256") != expected_dll:
            errors.append(f"{path}: installation binding DLL differs from paired build")
        if binding.get("installation_matches_build_manifest") is not True:
            errors.append(f"{path}: installation/build binding is not verified")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"{path}: case {index} is not an object")
            continue
        if case.get("error") is not None:
            errors.append(f"{path}: case {index} has error {case.get('error')!r}")
        for key in NETOE_CASE_CHECKS:
            require_true(case, key, f"{path}.case[{index}]", errors)
        if not existing_evidence_path(case.get("native_event_path")):
            errors.append(f"{path}: case {index}.native_event_path is missing")
        if not native_slice_ok(case.get("native_slice")):
            errors.append(f"{path}: case {index} native slice is incomplete")
    return {
        "path": path,
        "status": report.get("status"),
        "case_count": len(cases),
        "valid_case_count": coverage.get("valid_case_count") if isinstance(coverage, dict) else None,
        "uncovered": report.get("uncovered", []),
        "build_dll_sha256": expected_dll,
    }


def validate_invalid(report: dict[str, Any], path: str, errors: list[str]) -> dict[str, Any]:
    require_status(report, path, errors)
    require_all_boolean_checks(report.get("checks"), f"{path}.checks", errors)
    for key in INVALID_REQUIRED_CHECKS:
        require_true(report.get("checks"), key, f"{path}.checks", errors)
    if report.get("business_submission") is not False:
        errors.append(f"{path}.business_submission is not false")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 2:
        errors.append(f"{path}: expected exactly 2 invalid-request cases")
        cases = cases if isinstance(cases, list) else []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"{path}: case {index} is not an object")
            continue
        for key in ("api_reason_verified", "native_reason_verified"):
            require_true(case, key, f"{path}.case[{index}]", errors)
        for key in ("api_submitted", "native_submitted"):
            if case.get(key) is not False:
                errors.append(f"{path}.case[{index}].{key} is not false")
        if not case.get("native_reason_code"):
            errors.append(f"{path}.case[{index}] has no native reason code")
        if not native_slice_ok(case.get("native_slice")):
            errors.append(f"{path}: case {index} native slice is incomplete")
    return {"path": path, "status": report.get("status"), "case_count": len(cases)}


def validate_family_c(
    report: dict[str, Any],
    path: str,
    expected_dll: str,
    errors: list[str],
) -> dict[str, Any]:
    """Require all 19 named actions and their real parent-event evidence."""
    require_status(report, path, errors)
    require_all_boolean_checks(report.get("checks"), f"{path}.checks", errors)
    require_all_boolean_checks(report.get("required_checks"), f"{path}.required_checks", errors)
    for key in FAMILY_REQUIRED_CHECKS:
        require_true(report.get("checks"), key, f"{path}.checks", errors)
        require_true(report.get("required_checks"), key, f"{path}.required_checks", errors)
    for key, expected in (
        ("business_submission", False),
        ("save_requested", False),
        ("advance_requested", False),
        ("restart_requested", False),
    ):
        if report.get(key) is not expected:
            errors.append(f"{path}.{key} is not {expected!r}")
    if report.get("execute_call_count") != 0:
        errors.append(f"{path}.execute_call_count is not zero")
    if report.get("required_case_count") != len(FAMILY_REQUIRED_CASE_NAMES):
        errors.append(f"{path}.required_case_count is not 19")
    if report.get("required_cases_with_native_public_parity") != len(FAMILY_REQUIRED_CASE_NAMES):
        errors.append(f"{path}.required_cases_with_native_public_parity is not 19")
    catalog = report.get("action_catalog")
    if not isinstance(catalog, dict) or catalog.get("required_action_count") != 19:
        errors.append(f"{path}.action_catalog.required_action_count is not 19")
    binding = report.get("build_binding")
    if not isinstance(binding, dict):
        errors.append(f"{path}.build_binding is missing")
    else:
        for key in ("build_manifest_dll_sha256", "installation_dll_sha256"):
            if binding.get(key) != expected_dll:
                errors.append(f"{path}.{key} differs from current C build")
        if binding.get("installation_matches_build_manifest") is not True:
            errors.append(f"{path}: C installation/build binding is not verified")
    cases = report.get("cases")
    if not isinstance(cases, list):
        errors.append(f"{path}.cases is not a list")
        cases = []
    required_cases = [case for case in cases if isinstance(case, dict) and case.get("optional") is not True]
    names = [case.get("name") for case in required_cases]
    if len(required_cases) != 19:
        errors.append(f"{path}: expected 19 required cases, got {len(required_cases)}")
    if set(names) != set(FAMILY_REQUIRED_CASE_NAMES) or len(names) != len(set(names)):
        errors.append(f"{path}: required case names do not match the 19-action catalog")
    for index, case in enumerate(required_cases):
        if case.get("error") is not None:
            errors.append(f"{path}: required case {case.get('name', index)} has an error")
        if case.get("availability") in {"unknown", "invalid"}:
            errors.append(f"{path}: required case {case.get('name', index)} is unknown/invalid")
        for key in FAMILY_CASE_CHECKS:
            require_true(case, key, f"{path}.case[{case.get('name', index)}]", errors)
        if not existing_evidence_path(case.get("native_event_path")):
            errors.append(f"{path}: case {case.get('name', index)} native parent missing")
        if not existing_evidence_path(case.get("public_path")):
            errors.append(f"{path}: case {case.get('name', index)} public projection missing")
        if not native_slice_ok(case.get("native_slice")):
            errors.append(f"{path}: case {case.get('name', index)} native slice incomplete")
    optional_cases = [case for case in cases if isinstance(case, dict) and case.get("optional") is True]
    for index, case in enumerate(optional_cases):
        for key in ("native_consequences_present", "native_validator", "native_public_parity", "object_unchanged", "public_contract", "private_fields_absent", "raw_header_contract", "raw_public_parity"):
            require_true(case, key, f"{path}.optional[{index}]", errors)
        if not native_slice_ok(case.get("native_slice")):
            errors.append(f"{path}: optional case {index} native slice incomplete")
    comparison = report.get("province_88_comparison")
    if not isinstance(comparison, dict):
        errors.append(f"{path}.province_88_comparison is missing")
    else:
        for key in ("offer_orl_queried", "orl_unavailable", "orl_not_applied"):
            require_true(comparison, key, f"{path}.province_88_comparison", errors)
    return {
        "path": path,
        "status": report.get("status"),
        "required_case_count": len(required_cases),
        "optional_case_count": len(optional_cases),
        "required_cases_with_native_public_parity": report.get("required_cases_with_native_public_parity"),
        "build_dll_sha256": expected_dll,
    }


def validate_optional_report(
    report: dict[str, Any], path: str, label: str, errors: list[str]
) -> dict[str, Any]:
    accepted_statuses = {"passed"}
    if label == "advance_context":
        accepted_statuses.add("completed")
    if report.get("status") not in accepted_statuses:
        errors.append(f"{path}: status {report.get('status')!r} is not accepted")
    checks = report.get("checks")
    if isinstance(checks, dict):
        require_all_boolean_checks(checks, f"{path}.checks", errors)
    required = report.get("required_checks")
    if isinstance(required, dict):
        require_all_boolean_checks(required, f"{path}.required_checks", errors)
    if label == "advance_context":
        segments = report.get("segments")
        if not isinstance(segments, list) or not segments:
            errors.append(f"{path}.segments is missing")
        else:
            for index, segment in enumerate(segments):
                if not isinstance(segment, dict) or segment.get("completion_ready") is not True:
                    errors.append(f"{path}.segments[{index}] is not complete")
        if report.get("after_context_ok") is not True:
            errors.append(f"{path}.after_context_ok is not true")
    return {
        "label": label,
        "path": path,
        "status": report.get("status"),
        "top_check_count": len(checks) if isinstance(checks, dict) else 0,
    }


def _has_one_province_selection(report: dict[str, Any]) -> bool:
    """Recognize the positive one-province cap report without guessing values."""
    single_legality = report.get("single_province_legality")
    if isinstance(single_legality, dict) and single_legality.get("status") == "available":
        return True
    parameters = report.get("parameters")
    if isinstance(parameters, dict):
        context = parameters.get("peace_context")
        if isinstance(context, dict):
            terms = context.get("terms")
            if isinstance(terms, list):
                for term in terms:
                    if not isinstance(term, dict):
                        continue
                    ids = term.get("province_ids")
                    if (
                        term.get("action_id") == "cede_province"
                        and isinstance(ids, list)
                        and len(ids) == 1
                    ):
                        return True
    for key in (
        "selected_province_count",
        "province_count",
        "selected_count",
        "selection_count",
    ):
        if report.get(key) == 1:
            return True
    checks = report.get("checks")
    if isinstance(checks, dict):
        for key, value in checks.items():
            if isinstance(key, str) and "one" in key.lower() and value is True:
                return True
    return False


def validate_cap_report(
    report: dict[str, Any],
    path: str,
    expected_dll: str,
    expected_session: str,
    errors: list[str],
    *,
    positive_one_province: bool,
) -> dict[str, Any]:
    """Validate a passed cap report; failed historical attempts are evidence only."""
    require_status(report, path, errors)
    if report.get("session_id") != expected_session:
        errors.append(f"{path}: cap report does not bind current C session")
    checks = report.get("checks")
    require_all_boolean_checks(checks, f"{path}.checks", errors)
    if not isinstance(checks, dict) or not checks:
        errors.append(f"{path}.checks is empty")
    if not positive_one_province:
        for key in ("sixteen_native_provinces", "single_province_available",
                    "query_reports_100_percent_guard",
                    "unified_execution_reports_100_percent_guard",
                    "fresh_native_execution_reports_100_percent_guard",
                    "native_prohibition_bound", "no_business_submission",
                    "paused_por_same_date"):
            require_true(checks, key, f"{path}.checks", errors)
    if report.get("business_submission") is not False:
        errors.append(f"{path}.business_submission is not false")
    for key in ("save_requested", "advance_requested", "restart_requested"):
        if key in report and report.get(key) is not False:
            errors.append(f"{path}.{key} is not false")
    for key in ("api_submitted", "native_submitted"):
        if key in report and report.get(key) is not False:
            errors.append(f"{path}.{key} is not false")
    for key in ("query_native_slice", "execution_native_slice"):
        if key in report and not native_slice_ok(report.get(key)):
            errors.append(f"{path}.{key} is incomplete")
    binding = report.get("build_binding")
    if isinstance(binding, dict):
        for key in ("build_manifest_dll_sha256", "installation_dll_sha256"):
            if binding.get(key) != expected_dll:
                errors.append(f"{path}.{key} differs from current C build")
        if binding.get("installation_matches_build_manifest") is not True:
            errors.append(f"{path}: installation/build binding is not verified")
    one_province = _has_one_province_selection(report)
    if positive_one_province and not one_province:
        errors.append(f"{path}: no explicit one-province positive selection found")
    return {
        "path": path,
        "status": report.get("status"),
        "positive_one_province_requested": positive_one_province,
        "positive_one_province_detected": one_province,
        "check_count": len(checks) if isinstance(checks, dict) else 0,
    }


def validate_tests(
    reports: Iterable[tuple[str, dict[str, Any]]], errors: list[str]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path, report in reports:
        require_status(report, path, errors)
        if report.get("exit_code") not in (None, 0):
            errors.append(f"{path}.exit_code is not zero")
        for key in ("failed_tests", "failed_subtests", "failures"):
            if key in report and report.get(key) not in (None, 0, []):
                errors.append(f"{path}.{key} is nonzero")
        results.append(
            {
                "path": path,
                "status": report.get("status"),
                "passed_tests": report.get("passed_tests", report.get("tests", report.get("passed"))),
                "passed_subtests": report.get("passed_subtests", report.get("subtests", report.get("subtests_passed"))),
            }
        )
    return results


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--progress", default=DEFAULT_PROGRESS)
    parser.add_argument("--build-a", default=DEFAULT_BUILD_A)
    parser.add_argument("--installation-a", default=DEFAULT_INSTALL_A)
    parser.add_argument("--build-b", default=DEFAULT_BUILD_B)
    parser.add_argument("--installation-b", default=DEFAULT_INSTALL_B)
    parser.add_argument("--build-c", default=None)
    parser.add_argument("--installation-c", default=None)
    parser.add_argument("--cb-report", default=DEFAULT_CB)
    parser.add_argument("--netoe-a", default=DEFAULT_NETOE_A)
    parser.add_argument("--netoe-b", default=DEFAULT_NETOE_B)
    parser.add_argument("--family-c", default=DEFAULT_FAMILY_C)
    parser.add_argument("--invalid-report", default=DEFAULT_INVALID)
    parser.add_argument("--savecheck", action="append", default=None)
    parser.add_argument("--cap", dest="cap_reports", action="append", default=None)
    parser.add_argument(
        "--positive-cap",
        dest="positive_cap_reports",
        action="append",
        default=None,
    )
    parser.add_argument("--tests", action="append", default=None)
    parser.add_argument("--extra-report", action="append", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = resolve_path(args.output)
    if output.exists():
        raise DeliveryError(f"refusing to overwrite immutable delivery: {output}")
    errors: list[str] = []

    native = validate_build_pair(
        args.build_a,
        args.installation_a,
        args.build_b,
        args.installation_b,
        args.build_c,
        args.installation_c,
        errors,
    )
    cb = read_json(args.cb_report)
    netoe_a = read_json(args.netoe_a)
    netoe_b = read_json(args.netoe_b)
    family_c = read_json(args.family_c)
    invalid = read_json(args.invalid_report)
    cb_summary = validate_cb(cb, args.cb_report, errors)
    netoe_a_summary = validate_netoe(
        netoe_a, args.netoe_a, native["build_a"]["dll_sha256"], errors
    )
    netoe_b_summary = validate_netoe(
        netoe_b, args.netoe_b, native["build_b"]["dll_sha256"], errors
    )
    family_c_summary = validate_family_c(
        family_c, args.family_c, native["current_dll_sha256"], errors
    )
    invalid_summary = validate_invalid(invalid, args.invalid_report, errors)

    cap_paths = args.cap_reports or (
        [DEFAULT_CAP_REPORT] if resolve_path(DEFAULT_CAP_REPORT).is_file() else []
    )
    positive_cap_paths = args.positive_cap_reports or []
    cap_reports: list[tuple[str, dict[str, Any], bool]] = [
        (path, read_json(path), False) for path in cap_paths
    ] + [
        (path, read_json(path), True) for path in positive_cap_paths
    ]
    cap_summaries = [
        validate_cap_report(
            report,
            path,
            native["current_dll_sha256"],
            native["current_session_id"],
            errors,
            positive_one_province=positive,
        )
        for path, report, positive in cap_reports
    ]

    save_paths = args.savecheck or [
        path for path in DEFAULT_SAVECHECKS if resolve_path(path).is_file()
    ]
    save_reports: list[tuple[str, dict[str, Any]]] = [
        (path, read_json(path)) for path in save_paths
    ]
    save_summaries = [
        validate_optional_report(report, path, "savecheck", errors)
        for path, report in save_reports
    ]

    extra_paths = args.extra_report or [
        path for path in DEFAULT_EXTRA_REPORTS if resolve_path(path).is_file()
    ]
    extra_label = "extra" if args.extra_report else "advance_context"
    extra_reports: list[tuple[str, dict[str, Any]]] = [
        (path, read_json(path)) for path in extra_paths
    ]
    extra_summaries = [
        validate_optional_report(report, path, extra_label, errors)
        for path, report in extra_reports
    ]

    test_paths = args.tests or []
    test_reports = [(path, read_json(path)) for path in test_paths]
    test_summaries = validate_tests(test_reports, errors)

    scene_path = resolve_path(DEFAULT_SCENE)
    scene_report: dict[str, Any] | None = None
    if scene_path.is_file():
        scene_report = read_json(scene_path)
    else:
        errors.append(f"missing R66 non-core scene report: {relative_path(scene_path)}")
    if errors:
        raise DeliveryError("R66 delivery validation failed:\n- " + "\n- ".join(errors))

    evidence_paths: list[str] = [
        args.build_a,
        args.installation_a,
        args.build_b,
        args.installation_b,
        args.cb_report,
        DEFAULT_CB_SOURCE,
        args.netoe_a,
        args.netoe_b,
        args.family_c,
        args.invalid_report,
        DEFAULT_SCENE,
    ]
    if args.build_c and args.installation_c:
        evidence_paths.extend((args.build_c, args.installation_c))
    evidence_paths.extend(
        path for path in HISTORICAL_CAP_REPORTS if resolve_path(path).is_file()
    )
    evidence_paths.extend(cap_paths)
    evidence_paths.extend(positive_cap_paths)
    evidence_paths.extend(save_paths)
    evidence_paths.extend(extra_paths)
    evidence_paths.extend(test_paths)
    evidence_links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in evidence_paths:
        path = resolve_path(raw)
        key = relative_path(path)
        if key in seen:
            continue
        if not path.is_file():
            raise DeliveryError(f"missing evidence before delivery: {key}")
        evidence_links.append(
            {"path": key, "bytes": path.stat().st_size, "sha256": sha256_stream(path), "copied": False}
        )
        seen.add(key)

    tests_pending = not bool(test_paths)
    c_pending = not bool(args.build_c and args.installation_c)
    cap_pending = not bool(cap_reports)
    pending_labels = []
    if c_pending:
        pending_labels.append("cap_build_C")
    if cap_pending:
        pending_labels.append("positive_cap_report")
    if tests_pending:
        pending_labels.append("tests")
    status = "delivered" if not pending_labels else "prepared_pending_" + "_".join(pending_labels)
    scene_save = scene_report.get("destination", {}) if isinstance(scene_report, dict) else {}
    scene_reference = {
        "report": relative_path(scene_path),
        "path": scene_save.get("path") if isinstance(scene_save, dict) else None,
        "sha256": scene_save.get("sha256") if isinstance(scene_save, dict) else None,
        "hash_reused_from_scene_report": True,
        "save_copied": False,
        "hash_recomputed": False,
    }
    remaining_scope = {
        "target_justification_and_war_goal": "pending further native/query coverage",
        "third_country_peace_terms": "pending a real selectable third-country beneficiary case",
        "hundred_point_or_cost_ceiling": (
            "covered by supplied positive cap report" if cap_reports else "pending a passed positive cap report"
        ),
        "release_nation_overextension": "pending dedicated accepted consequence coverage",
        "remaining_goal_phases": "goal remains active; later batches decide concrete scope",
    }
    progress = {
        "stage": "R66",
        "status": status,
        "goal_status": "active",
        "goal_active": True,
        "native": native,
        "cb_rule_queries": cb_summary,
        "netoe_queries": {"A": netoe_a_summary, "B": netoe_b_summary},
        "family_c": family_c_summary,
        "invalid_requests": invalid_summary,
        "warscore_cap": {
            "historical_reports": [relative_path(resolve_path(path)) for path in HISTORICAL_CAP_REPORTS if resolve_path(path).is_file()],
            "reports": cap_summaries,
            "cap_build_pending": c_pending,
            "positive_one_province_pending": cap_pending,
        },
        "savechecks": save_summaries,
        "extra_reports": extra_summaries,
        "tests": test_summaries,
        "tests_pending": tests_pending,
        "scene": scene_reference,
        "remaining_scope": remaining_scope,
        "save_reload_validation": False,
        "no_game_or_rea_run": True,
        "delivery": relative_path(output / "manifest.json"),
    }

    records: list[dict[str, Any]] = []
    output.mkdir(parents=True, exist_ok=False)
    source_files = delivery_source_files()
    for relative in source_files:
        source = ROOT / relative
        records.append(copy_and_hash(source, output / "source" / relative))
    copied_evidence: list[dict[str, Any]] = []
    copied_keys: set[str] = set()
    for raw in evidence_paths:
        source = resolve_path(raw)
        key = relative_path(source)
        if key in copied_keys:
            continue
        copied_evidence.append(copy_and_hash(source, output / "evidence" / key))
        copied_keys.add(key)

    manifest = {
        "status": status,
        "stage": "R66",
        "source_count": len(records),
        "total_source_bytes": sum(item["bytes"] for item in records),
        "sources": records,
        "evidence_copied_once": copied_evidence,
        "evidence_links": evidence_links,
        "native_reference": native,
        "family_c": family_c_summary,
        "warscore_cap_reports": cap_summaries,
        "scene_reference": scene_reference,
        "remaining_scope": remaining_scope,
        "constraints": {
            "save_files_copied": False,
            "dll_copied": False,
            "large_runtime_logs_copied": False,
            "source_save_sha_recomputed": False,
            "goal_status": "active",
        },
        "progress": progress,
    }
    write_json(output / "manifest.json", manifest)
    write_json(resolve_path(args.progress), progress)
    print(
        json.dumps(
            {
                "status": status,
                "manifest": relative_path(output / "manifest.json"),
                "progress": relative_path(resolve_path(args.progress)),
                "source_count": len(records),
                "evidence_count": len(copied_evidence),
                "native_source_count": native["source_count"],
                "cb_case_count": cb_summary["case_count"],
                "netoe_case_counts": [netoe_a_summary["case_count"], netoe_b_summary["case_count"]],
                "family_c_required_case_count": family_c_summary["required_case_count"],
                "cap_report_count": len(cap_summaries),
                "tests_pending": tests_pending,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
