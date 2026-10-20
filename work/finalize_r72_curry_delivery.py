"""Create the bounded R72 Curry delivery archive.

The finalizer consumes only the already-recorded R72 reports, raw JSONL,
immutable Python snapshot, and the two immutable native build manifests.  It
does not read current production sources, copy the 43 MB save, recompute the
89 native-source hashes, contact the game, or invoke REA.  It is deliberately
fail-closed and requires the explicit --docs-ready gate before it copies the
seven release documents.

Run after the release documents have been finalized:

    python work/finalize_r72_curry_delivery.py --docs-ready
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work" / "runtime"
OUTPUT = RUNTIME / "r72-curry-delivery-20261020-001"
PROGRESS_PATH = RUNTIME / "r72-progress.json"
MAX_SMALL_BYTES = 16 * 1024 * 1024

A_BUILD = RUNTIME / "diplomacy-observer-20261020-r72-curry-a"
B_BUILD = RUNTIME / "diplomacy-observer-20261020-r72-curry-b"
SNAPSHOT_MANIFEST = OUTPUT / "python-source-snapshot.json"

DOCS = (
    "docs/人情外交接口.md",
    "docs/外交能力矩阵.md",
    "docs/外交系统说明.md",
    "docs/外交接口开发方案.md",
    "docs/外交开发推进复盘.md",
    "PLAN.md",
    "HANDOFF.md",
)

QUERY_DIR = "work/runtime/r72-curry-queries-20261020-001"
BASELINE_EXEC_DIR = "work/runtime/r72-curry-execution-20261020-001"
EXEC_DIR = "work/runtime/r72-curry-execution-20261020-002"
AUTHORITY_DIR = "work/runtime/r72-curry-authority-20261020-001"
INVALID_DIR = "work/runtime/r72-curry-invalid-20261020-001"
FINAL_SAVE_REPORT = "work/runtime/r72-curry-final-save-20261020-002.json"
PRIOR_SAVE_REPORT = "work/runtime/r72-curry-final-save-20261020-001.json"
SAVE_OBSERVER_REPORT = (
    "work/runtime/diplomacy-observer-20261020-r72-curry-b/"
    "save-observer-report-1792439224967711000.json"
)
PYTHON_UNIT_DIR = "work/runtime/r72-final-python-unit-20261020-003"

EXPECTED_A_DLL = "3de30aa5ef60d381b0d562f8990e6c2971ac884421bbf3b9a6835cec3da3a180"
EXPECTED_B_DLL = "701ae856bccf405dc7e9eb54068dd2cd6717efde897263549ef220e2a4796538"
EXPECTED_SAVE_SHA = "0184ae0b25c97ce0511303dcd141cb0bc0ef711d738335d6240fae522e675b68"
EXPECTED_SAVE_SIZE = 43_063_044
EXPECTED_SAVE_DATE = "1456.1.2"
EXPECTED_REQUESTS = (
    "r72_b_curry_start_pap_001",
    "r72_b_curry_start_sav_001",
    "r72_b_curry_stop_pap_001",
)

STATIC_CONTRACT_FILES = (
    "work/runtime/r72-favor-family-init-20261020-001/report.md",
    "work/runtime/r72-favor-resource-contract-20261020-001/report.md",
    "work/runtime/r72-gift-war-xrefs-20261020-001/contract.md",
    "work/runtime/r72-gift-war-xrefs-20261020-001/report.md",
    "work/runtime/r72-gift-war-xrefs-20261020-001/report.json",
    "work/runtime/r72-gift-war-xrefs-20261020-001/rea-gift-rule/run.json",
    "work/runtime/r72-gift-war-xrefs-20261020-001/rea-influence-effect/run.json",
    "work/runtime/r72-gift-war-xrefs-20261020-001/rea-war-overview-update/run.json",
    "work/runtime/r72-gift-war-xrefs-20261020-001/rea-war-score-tooltip/run.json",
)

# Reports and raw JSONL are listed explicitly so the archive contains the
# evidence itself rather than an index which would require the live workspace.
EVIDENCE_FILES = (
    f"{QUERY_DIR}/report.json",
    f"{QUERY_DIR}/native.jsonl",
    f"{QUERY_DIR}/control-before.json",
    f"{QUERY_DIR}/control-after.json",
    f"{BASELINE_EXEC_DIR}/report.json",
    f"{BASELINE_EXEC_DIR}/native.jsonl",
    f"{BASELINE_EXEC_DIR}/control-before.json",
    f"{EXEC_DIR}/report.json",
    f"{EXEC_DIR}/native.jsonl",
    f"{EXEC_DIR}/control-before.json",
    f"{EXEC_DIR}/control-after.json",
    f"{AUTHORITY_DIR}/report.json",
    f"{AUTHORITY_DIR}/native.jsonl",
    f"{INVALID_DIR}/report.json",
    f"{INVALID_DIR}/native.jsonl",
    FINAL_SAVE_REPORT,
    PRIOR_SAVE_REPORT,
    SAVE_OBSERVER_REPORT,
    f"{PYTHON_UNIT_DIR}/report.json",
    f"{PYTHON_UNIT_DIR}/pytest-output.txt",
)

BUILD_FILES = (
    "work/runtime/diplomacy-observer-20261020-r72-curry-a/build-manifest.json",
    "work/runtime/diplomacy-observer-20261020-r72-curry-a/installation.json",
    "work/runtime/diplomacy-observer-20261020-r72-curry-b/build-manifest.json",
    "work/runtime/diplomacy-observer-20261020-r72-curry-b/installation.json",
)


def _small(path: Path) -> Path:
    if not path.is_file():
        raise AssertionError(f"MISSING_FILE: {path}")
    size = path.stat().st_size
    if size >= MAX_SMALL_BYTES:
        raise AssertionError(f"FILE_TOO_LARGE: {path} ({size})")
    return path


def read_json(path: Path) -> dict[str, Any]:
    _small(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON_OBJECT_REQUIRED: {path}")
    return value


def read_json_list(path: Path) -> list[dict[str, Any]]:
    _small(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AssertionError(f"JSON_OBJECT_LIST_REQUIRED: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    _small(path)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AssertionError(f"{path}:{line_number}: JSON_OBJECT_REQUIRED")
        rows.append(value)
    return rows


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_passed(report: dict[str, Any], label: str) -> None:
    require(report.get("status") == "passed", f"{label}: status={report.get('status')!r}")


def require_true_checks(report: dict[str, Any], label: str, key: str = "checks") -> None:
    checks = report.get(key)
    require(isinstance(checks, dict) and checks, f"{label}: missing {key}")
    require(all(value is True for value in checks.values()), f"{label}: false check")


def sha256_file(path: Path) -> str:
    _small(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key:
                found.append(child)
            found.extend(_nested_values(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_nested_values(child, key))
    return found


def validate_python_snapshot() -> dict[str, Any]:
    entries = read_json_list(SNAPSHOT_MANIFEST)
    require(len(entries) == 10, f"python snapshot: expected 10 files, got {len(entries)}")
    seen: set[str] = set()
    files: list[dict[str, Any]] = []
    for entry in entries:
        relative = entry.get("path")
        require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "python snapshot: unsafe path")
        require(relative not in seen, f"python snapshot: duplicate {relative}")
        seen.add(relative)
        target = OUTPUT / "files" / Path(relative)
        _small(target)
        expected_bytes = entry.get("bytes")
        expected_sha = entry.get("sha256")
        require(target.stat().st_size == expected_bytes, f"python snapshot: size {relative}")
        actual_sha = sha256_file(target)
        require(actual_sha == expected_sha, f"python snapshot: hash {relative}")
        files.append({"path": _relative(target), "bytes": target.stat().st_size, "sha256": actual_sha})
    return {"manifest": _relative(SNAPSHOT_MANIFEST), "count": len(files), "files": files}


def verify_query_batch(a_install: dict[str, Any]) -> dict[str, Any]:
    report_path = ROOT / QUERY_DIR / "report.json"
    native_path = ROOT / QUERY_DIR / "native.jsonl"
    report = read_json(report_path)
    require_passed(report, "curry_queries")
    require_true_checks(report, "curry_queries")
    require(report.get("session_id") == a_install.get("session_id"), "curry_queries: A session")
    require(report.get("native_slice", {}).get("status") == "ok", "curry_queries: native slice")
    queries = report.get("queries")
    require(isinstance(queries, dict) and set(queries) == {"PAP", "SAV", "LIT", "GEN"}, "curry_queries: four targets")
    for recipient in ("PAP", "SAV", "LIT", "GEN"):
        pair = queries[recipient]
        require(set(pair) == {"curry_favors", "stop_curry_favors"}, f"curry_queries: pair {recipient}")
        for action_id, inspection in pair.items():
            require(inspection.get("family") == "curry_favors", f"curry_queries: family {recipient}/{action_id}")
            require(inspection.get("actor") == "FRA", f"curry_queries: actor {recipient}/{action_id}")
            require(inspection.get("recipient") == recipient, f"curry_queries: recipient {recipient}/{action_id}")
            require(inspection.get("action_id") == action_id, f"curry_queries: action {recipient}/{action_id}")
    events = read_jsonl(native_path)
    inspections = [event for event in events if event.get("event") == "native_alliance_inspection"]
    require(len(inspections) == 8, f"curry_queries: inspection count={len(inspections)}")
    require(all(event.get("family") == "curry_favors" for event in inspections), "curry_queries: native family")
    return {
        "report": _relative(report_path),
        "native": _relative(native_path),
        "session_id": a_install["session_id"],
        "targets": 4,
        "inspection_records": len(inspections),
        "checks": report["checks"],
        "queries_consumed": True,
    }


def verify_baseline_execution(a_install: dict[str, Any]) -> dict[str, Any]:
    report_path = ROOT / BASELINE_EXEC_DIR / "report.json"
    native_path = ROOT / BASELINE_EXEC_DIR / "native.jsonl"
    report = read_json(report_path)
    require(report.get("status") == "failed", "curry_baseline: failure must be preserved")
    require(report.get("session_id") == a_install.get("session_id"), "curry_baseline: A session")
    operations = report.get("operations")
    require(isinstance(operations, list) and len(operations) == 1, "curry_baseline: one request")
    result = operations[0].get("result", {})
    require(result.get("request_id") == "r72_a_curry_start_pap_001", "curry_baseline: request")
    require(result.get("submitted") is False and result.get("status") == "invalidated", "curry_baseline: invalidated")
    events = read_jsonl(native_path)
    rejected = [event for event in events if event.get("event") == "native_alliance_execution_rejected"]
    require(len(rejected) == 1 and rejected[0].get("reason") == "NATIVE_RELATION_BASELINE_UNVERIFIED", "curry_baseline: reason")
    return {
        "report": _relative(report_path),
        "native": _relative(native_path),
        "request_id": "r72_a_curry_start_pap_001",
        "status": "failed_preserved",
        "reason": rejected[0]["reason"],
    }


def verify_execution(b_install: dict[str, Any]) -> dict[str, Any]:
    report_path = ROOT / EXEC_DIR / "report.json"
    native_path = ROOT / EXEC_DIR / "native.jsonl"
    report = read_json(report_path)
    require_passed(report, "curry_execution")
    require_true_checks(report, "curry_execution")
    require(report.get("session_id") == b_install.get("session_id"), "curry_execution: B session")
    require(report.get("native_slice", {}).get("status") == "ok", "curry_execution: native slice")
    operations = report.get("operations")
    require(isinstance(operations, list) and len(operations) == 3, "curry_execution: three requests")
    expected = {
        "r72_b_curry_start_pap_001": ("curry_favors", "PAP", 1, False, True),
        "r72_b_curry_start_sav_001": ("curry_favors", "SAV", 1, False, True),
        "r72_b_curry_stop_pap_001": ("stop_curry_favors", "PAP", 0, True, False),
    }
    native_results: dict[str, dict[str, Any]] = {}
    for operation in operations:
        public = operation.get("result", {})
        native = public.get("result", {})
        request_id = native.get("request_id") or public.get("request_id")
        require(request_id in expected, f"curry_execution: unexpected request {request_id}")
        action_id, recipient, variant, before, after = expected[request_id]
        require(public.get("submitted") is True and public.get("status") == "executed", f"curry_execution: public {request_id}")
        require(native.get("event") == "native_diplomacy_task_execution_result", f"curry_execution: event {request_id}")
        require(native.get("family") == "curry_favors", f"curry_execution: family {request_id}")
        require(native.get("action_id") == action_id, f"curry_execution: action {request_id}")
        require(native.get("actor") == "FRA" and native.get("recipient") == recipient, f"curry_execution: endpoint {request_id}")
        require(native.get("native_variant") == variant and native.get("native_state") == 0, f"curry_execution: variant/state {request_id}")
        require(native.get("task_before") is before and native.get("task_after") is after, f"curry_execution: task state {request_id}")
        require(native.get("native_outcome") == "executed" and native.get("execution_verified") is True, f"curry_execution: outcome {request_id}")
        require(native.get("request_binding_verified") is True, f"curry_execution: binding {request_id}")
        evidence = public.get("evidence")
        require(
            isinstance(evidence, list)
            and {item.get("type") for item in evidence} == {"native_submission", "native_execution_consequence"},
            f"curry_execution: response evidence {request_id}",
        )
        native_results[request_id] = native
    require(set(native_results) == set(EXPECTED_REQUESTS), "curry_execution: request set")
    rows = read_jsonl(native_path)
    result_events = [event for event in rows if event.get("event") == "native_diplomacy_task_execution_result"]
    submission_events = [event for event in rows if event.get("event") == "native_alliance_submission_result"]
    require(len(result_events) == 3 and len(submission_events) == 3, "curry_execution: raw result/submission count")
    require({event.get("request_id") for event in result_events} == set(EXPECTED_REQUESTS), "curry_execution: raw request set")
    journal = _nested_values(report, "journal_reopen_equal")
    require(journal.count(True) == 3, f"curry_execution: journal reopen checks={journal}")
    return {
        "report": _relative(report_path),
        "native": _relative(native_path),
        "session_id": b_install["session_id"],
        "request_ids": list(EXPECTED_REQUESTS),
        "outcomes": {request_id: native["native_outcome"] for request_id, native in native_results.items()},
        "raw_submission_events": len(submission_events),
        "raw_result_events": len(result_events),
        "request_binding_verified": True,
        "response_verified": True,
        "response_evidence_verified": True,
        "journal_reopen_equal": True,
    }


def verify_authority() -> dict[str, Any]:
    report_path = ROOT / AUTHORITY_DIR / "report.json"
    native_path = ROOT / AUTHORITY_DIR / "native.jsonl"
    report = read_json(report_path)
    require_passed(report, "curry_authority")
    cases = report.get("cases")
    require(isinstance(cases, list) and len(cases) == 2, "curry_authority: two cases")
    require({case.get("token") for case in cases} == {"WITHOUT_AUTHORITY", "DIRECT_WITHOUT_AUTHORITY"}, "curry_authority: token isolation")
    for case in cases:
        checks = case.get("checks")
        require(isinstance(checks, dict) and all(value is True for value in checks.values()), "curry_authority: case checks")
        require(case.get("before", {}).get("relationship_state", {}).get("task_active") is True, "curry_authority: before task")
        require(case.get("after", {}).get("relationship_state", {}).get("task_active") is True, "curry_authority: after task")
    rows = read_jsonl(native_path)
    rejected = [event for event in rows if event.get("event") == "native_alliance_execution_rejected"]
    require(len(rejected) == 2, "curry_authority: raw rejection count")
    require(all(event.get("reason") == "UNAUTHORIZED_FRA_CURRY_FAVORS_TASK" for event in rejected), "curry_authority: raw reason")
    dispatched = [event for event in rows if event.get("event") == "native_alliance_authority_test_dispatched"]
    require({event.get("dispatch_route") for event in dispatched} == {"transport", "direct_entry"}, "curry_authority: routes")
    return {
        "report": _relative(report_path),
        "native": _relative(native_path),
        "cases": 2,
        "tokens": ["WITHOUT_AUTHORITY", "DIRECT_WITHOUT_AUTHORITY"],
        "rejections": len(rejected),
        "task_still_active": True,
    }


def verify_invalid() -> dict[str, Any]:
    report_path = ROOT / INVALID_DIR / "report.json"
    native_path = ROOT / INVALID_DIR / "native.jsonl"
    report = read_json(report_path)
    require_passed(report, "curry_invalid")
    cases = report.get("cases")
    require(isinstance(cases, list) and len(cases) == 2, "curry_invalid: two cases")
    expected = {
        "r72_b_invalid_sav_001": ("curry_favors", "SAV", "NATIVE_DIPLOMAT_UNAVAILABLE"),
        "r72_b_invalid_pap_001": ("stop_curry_favors", "PAP", "NATIVE_LEGALITY_UNAVAILABLE"),
    }
    for case in cases:
        request_id = case.get("request_id")
        require(request_id in expected, f"curry_invalid: request {request_id}")
        action_id, recipient, code = expected[request_id]
        require(case.get("action_id") == action_id and case.get("recipient") == recipient, f"curry_invalid: endpoint {request_id}")
        checks = case.get("checks")
        require(isinstance(checks, dict) and all(value is True for value in checks.values()), f"curry_invalid: checks {request_id}")
        result = case.get("result", {})
        inner = result.get("result", {})
        reason = inner.get("reason", {})
        require(result.get("submitted") is False and result.get("status") == "invalidated", f"curry_invalid: unsubmitted {request_id}")
        require(reason.get("code") == code, f"curry_invalid: reason code {request_id}")
        require(isinstance(reason.get("text"), str) and any("\u4e00" <= char <= "\u9fff" for char in reason["text"]), f"curry_invalid: Chinese reason {request_id}")
    rows = read_jsonl(native_path)
    inspections = [event for event in rows if event.get("event") == "native_alliance_inspection"]
    require(len(inspections) == 2, "curry_invalid: raw inspection count")
    require(all(event.get("family") == "curry_favors" and event.get("native_validity") is False for event in inspections), "curry_invalid: native validity")
    return {
        "report": _relative(report_path),
        "native": _relative(native_path),
        "cases": 2,
        "request_ids": list(expected),
        "native_inspection_records": len(inspections),
        "unsubmitted": True,
        "journal_reopen_equal": True,
    }


def verify_final_save() -> dict[str, Any]:
    report_path = ROOT / FINAL_SAVE_REPORT
    prior_path = ROOT / PRIOR_SAVE_REPORT
    report = read_json(report_path)
    prior = read_json(prior_path)
    require_passed(report, "curry_final_save")
    require(report.get("schema") == "r72_curry_save_verify_v1", "curry_final_save: schema")
    require(report.get("errors") == [], "curry_final_save: errors")
    require(report.get("prior_report", {}).get("status") == "failed", "curry_final_save: prior failure retained")
    require(report.get("prior_report", {}).get("path", "").endswith("r72-curry-final-save-20261020-001.json"), "curry_final_save: prior path")
    require(prior.get("status") == "failed", "curry_final_save: prior report file")
    fields = report.get("fields", {})
    require(fields.get("event_family") == "curry_favors", "curry_final_save: family")
    require(fields.get("event_name") == "native_diplomacy_task_execution_result", "curry_final_save: event")
    require(fields.get("selected_event_count") == 3, "curry_final_save: selected event count")
    selected = {event.get("request_id"): event for event in fields.get("selected_events", [])}
    require(set(selected) == set(EXPECTED_REQUESTS), "curry_final_save: selected requests")
    require(selected["r72_b_curry_start_pap_001"].get("task_after") is True, "curry_final_save: PAP start")
    require(selected["r72_b_curry_start_sav_001"].get("task_after") is True, "curry_final_save: SAV start")
    require(selected["r72_b_curry_stop_pap_001"].get("task_after") is False, "curry_final_save: PAP stop")
    pairs = {(item.get("actor"), item.get("recipient")): item for item in fields.get("last_task_after_by_actor_recipient", [])}
    require(set(pairs) == {("FRA", "PAP"), ("FRA", "SAV")}, "curry_final_save: pair set")
    pap = pairs[("FRA", "PAP")]
    sav = pairs[("FRA", "SAV")]
    require(pap.get("expected_task_after") is False and pap.get("match") is True, "curry_final_save: PAP match")
    require(pap.get("active_record_count") == 0 and pap.get("returning_record_count") == 1 and pap.get("evidence") == "returning_record_after_stop", "curry_final_save: PAP returning")
    require(sav.get("expected_task_after") is True and sav.get("match") is True, "curry_final_save: SAV match")
    require(sav.get("active_record_count") == 1 and sav.get("returning_record_count") == 0 and sav.get("evidence") == "outbound_active_record_present", "curry_final_save: SAV active")
    save = report.get("save", {})
    require(save.get("sha256") == EXPECTED_SAVE_SHA, "curry_final_save: SHA")
    require(save.get("size") == EXPECTED_SAVE_SIZE, "curry_final_save: size")
    require(save.get("top_level_date") == EXPECTED_SAVE_DATE, "curry_final_save: date")
    require(save.get("single_streaming_pass") is True and save.get("sha256_passes") == 0, "curry_final_save: bounded scan metadata")
    require(save.get("event_save_lines_or_offsets_used") is False, "curry_final_save: event offset independence")
    require(save.get("countries_complete") is True and save.get("countries_found") is True, "curry_final_save: country markers")
    return {
        "report": _relative(report_path),
        "prior_report": _relative(prior_path),
        "status": report["status"],
        "errors": [],
        "save_sha256": save["sha256"],
        "save_size": save["size"],
        "save_date": save["top_level_date"],
        "selected_events": fields["selected_event_count"],
        "pair_checks": len(pairs),
        "route_semantics": fields.get("save_task_storage", {}).get("route_semantics", {}),
        "save_copied": False,
    }


def verify_save_observer(b_install: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / SAVE_OBSERVER_REPORT
    report = read_json(path)
    require(report.get("status") == "success", "save_observer: status")
    require(report.get("session", {}).get("session_id") == b_install.get("session_id"), "save_observer: session")
    require(report.get("session", {}).get("dll_sha256") == EXPECTED_B_DLL, "save_observer: B DLL")
    save = report.get("save", {})
    inspection = save.get("inspection", {})
    require(save.get("sha256") == EXPECTED_SAVE_SHA, "save_observer: SHA")
    require(inspection.get("valid") is True and inspection.get("file_size") == EXPECTED_SAVE_SIZE, "save_observer: save inspection")
    require(inspection.get("date") == EXPECTED_SAVE_DATE and inspection.get("player") == "POR", "save_observer: save date/player")
    restore = report.get("restore", {})
    require(restore.get("errors") == [] and restore.get("rotating_restore_count") == 3, "save_observer: restore")
    require(restore.get("unknown_new_save_files") == [] and restore.get("unknown_new_save_metadata") == [], "save_observer: restore scope")
    return {
        "report": _relative(path),
        "status": report["status"],
        "session_id": b_install["session_id"],
        "save_sha256": save["sha256"],
        "save_size": inspection["file_size"],
        "save_date": inspection["date"],
        "player": inspection["player"],
        "autosaves_restored": restore["rotating_restore_count"],
        "errors": [],
        "save_copied": False,
    }


def verify_python_unit() -> dict[str, Any]:
    report_path = ROOT / PYTHON_UNIT_DIR / "report.json"
    report = read_json(report_path)
    require_passed(report, "python_unit")
    require(report.get("exit_code") == 0, "python_unit: exit code")
    require(report.get("summary") == "894 passed, 666 subtests passed in 13.05s", "python_unit: count")
    return {
        "report": _relative(report_path),
        "status": report["status"],
        "exit_code": report["exit_code"],
        "summary": report["summary"],
    }


def verify_builds() -> dict[str, Any]:
    identities: dict[str, dict[str, Any]] = {}
    for label, build_dir, expected_dll in (("query_a", A_BUILD, EXPECTED_A_DLL), ("execution_b", B_BUILD, EXPECTED_B_DLL)):
        manifest_path = build_dir / "build-manifest.json"
        installation_path = build_dir / "installation.json"
        manifest = read_json(manifest_path)
        installation = read_json(installation_path)
        sources = manifest.get("sources")
        require(isinstance(sources, list) and len(sources) == 89, f"builds: {label} source count")
        require(manifest.get("compiled") is True, f"builds: {label} compiled")
        require(manifest.get("dll_sha256") == expected_dll, f"builds: {label} DLL")
        require(installation.get("installation_returncode") == 0, f"builds: {label} install")
        require(installation.get("dll_sha256") == expected_dll, f"builds: {label} install DLL")
        require(isinstance(installation.get("session_id"), str) and installation["session_id"], f"builds: {label} session")
        require(installation.get("ready_reason") == "verified_load_confirmation", f"builds: {label} ready")
        identities[label] = {
            "experiment_id": manifest.get("experiment_id"),
            "dll_sha256": expected_dll,
            "session_id": installation["session_id"],
            "source_count": len(sources),
            "build_manifest": _relative(manifest_path),
            "installation": _relative(installation_path),
            "manifest_sha256": sha256_file(manifest_path),
            "installation_sha256": sha256_file(installation_path),
            "source_hashes_recomputed": False,
        }
    a_sources = read_json(A_BUILD / "build-manifest.json").get("sources", [])
    b_sources = read_json(B_BUILD / "build-manifest.json").get("sources", [])
    a_refs = {x.get("name"): x.get("sha256") for x in a_sources}
    b_refs = {x.get("name"): x.get("sha256") for x in b_sources}
    require(set(a_refs) == set(b_refs), "builds: source-name set")
    source_differences = sorted(name for name in a_refs if a_refs[name] != b_refs[name])
    require(source_differences == ["alliance-execution.inc"], f"builds: unexpected source differences {source_differences}")
    return {
        "query_a": identities["query_a"],
        "execution_b": identities["execution_b"],
        "native_sources": 89,
        "source_hash_differences": source_differences,
        "native_source_hashes_recomputed": False,
        "lineage_distinct": EXPECTED_A_DLL != EXPECTED_B_DLL,
    }


def verify_static_contracts() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for relative in STATIC_CONTRACT_FILES:
        path = ROOT / relative
        if path.name == "run.json":
            report = read_json(path)
            require(report.get("exit_code") == 0 and report.get("database_unchanged") is True, f"static contract: {relative}")
        else:
            _small(path)
        results.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return {"files": results, "rea_runs": 4, "database_unchanged": True}


def build_real_fixture(query_native: list[dict[str, Any]], execution_native: list[dict[str, Any]]) -> tuple[Path, Path, dict[str, Any]]:
    test_dir = OUTPUT / "files" / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = test_dir
    query_events = [row for row in query_native if row.get("event") == "native_alliance_inspection"]
    execution_events = [
        row
        for row in execution_native
        if row.get("event") in {"native_alliance_submission_result", "native_diplomacy_task_execution_result"}
    ]
    require(len(query_events) == 8, "fixture: query events")
    require(len(execution_events) == 6, "fixture: submission/result events")
    fixture = {
        "schema": "r72_curry_real_native_fixture_v1",
        "sources": {
            "query": _relative(ROOT / QUERY_DIR / "native.jsonl"),
            "execution": _relative(ROOT / EXEC_DIR / "native.jsonl"),
        },
        "query_events": query_events,
        "execution_events": execution_events,
    }
    fixture_path = fixture_dir / "r72_curry_real_native.json"
    fixture_text = json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"
    if fixture_path.exists():
        require(fixture_path.read_text(encoding="utf-8") == fixture_text, "fixture: existing content differs")
    else:
        fixture_path.write_text(fixture_text, encoding="utf-8")
    test_path = test_dir / "test_r72_curry_real_native_fixture.py"
    test_text = '''"""Small, self-contained R72 Curry raw-event fixture test."""

import json
from pathlib import Path


def test_r72_curry_raw_query_submission_result_contract():
    fixture = json.loads((Path(__file__).with_name("r72_curry_real_native.json")).read_text(encoding="utf-8"))
    assert fixture["schema"] == "r72_curry_real_native_fixture_v1"
    queries = fixture["query_events"]
    assert len(queries) == 8
    assert {row["recipient"] for row in queries} == {"PAP", "SAV", "LIT", "GEN"}
    assert {row["action_id"] for row in queries} == {"curry_favors", "stop_curry_favors"}
    assert all(row["event"] == "native_alliance_inspection" and row["family"] == "curry_favors" for row in queries)
    results = fixture["execution_events"]
    assert len(results) == 6
    submissions = [row for row in results if row["event"] == "native_alliance_submission_result"]
    executions = [row for row in results if row["event"] == "native_diplomacy_task_execution_result"]
    assert len(submissions) == 3 and len(executions) == 3
    assert {row["request_id"] for row in executions} == {
        "r72_b_curry_start_pap_001",
        "r72_b_curry_start_sav_001",
        "r72_b_curry_stop_pap_001",
    }
    assert {row["family"] for row in executions} == {"curry_favors"}
    assert all(row["outcome"] == "executed" for row in executions)
    assert {row["native_variant"] for row in executions} == {0, 1}
'''
    if test_path.exists():
        require(test_path.read_text(encoding="utf-8") == test_text, "fixture test: existing content differs")
    else:
        test_path.write_text(test_text, encoding="utf-8")
    return fixture_path, test_path, {
        "query_events": len(query_events),
        "submission_events": len([row for row in execution_events if row.get("event") == "native_alliance_submission_result"]),
        "result_events": len([row for row in execution_events if row.get("event") == "native_diplomacy_task_execution_result"]),
    }


def run_fixture_test(test_path: Path) -> dict[str, Any]:
    output_path = test_path.parent / "r72_curry_fixture_pytest.txt"
    command = [sys.executable, "-m", "pytest", str(test_path), "-q"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    combined = (completed.stdout or "") + (completed.stderr or "")
    output_path.write_text(combined, encoding="utf-8")
    require(completed.returncode == 0, f"fixture test: exit={completed.returncode}: {combined[-1000:]}")
    require("1 passed" in combined, f"fixture test: unexpected output {combined!r}")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "summary": "1 passed",
        "output": _relative(output_path),
    }


def copy_small(source: Path, relative_target: str, trusted_sha256: str | None = None) -> dict[str, Any]:
    _small(source)
    target = OUTPUT / "files" / Path(relative_target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(target.is_file(), f"ARCHIVE_TARGET_NOT_FILE: {target}")
        require(target.stat().st_size == source.stat().st_size, f"ARCHIVE_TARGET_SIZE: {target}")
    else:
        shutil.copyfile(source, target)
    digest = sha256_file(target)
    if trusted_sha256 is not None:
        require(digest == trusted_sha256, f"ARCHIVE_TARGET_HASH: {target}")
    return {"path": _relative(target), "bytes": target.stat().st_size, "sha256": digest}


def archive_files(paths: Iterable[str]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative in paths:
        if relative in seen:
            continue
        seen.add(relative)
        files.append(copy_small(ROOT / relative, relative))
    return files


def snapshot_archive_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    # Snapshot files were staged before R72 finalization.  They are validated
    # in place and never copied from current production sources.
    return [{"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"]} for item in snapshot["files"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-ready", action="store_true", help="confirm release documents are ready to copy/hash")
    args = parser.parse_args()
    if not args.docs_ready:
        raise SystemExit("DOCS_NOT_READY: rerun with --docs-ready after docs/PLAN/HANDOFF are final")
    require(not (OUTPUT / "manifest.json").exists(), "ARCHIVE_ALREADY_FINALIZED")
    require(not PROGRESS_PATH.exists(), "PROGRESS_ALREADY_EXISTS")
    for relative in DOCS:
        _small(ROOT / relative)

    snapshot = validate_python_snapshot()
    a_install = read_json(A_BUILD / "installation.json")
    b_install = read_json(B_BUILD / "installation.json")
    builds = verify_builds()
    queries = verify_query_batch(a_install)
    baseline = verify_baseline_execution(a_install)
    execution = verify_execution(b_install)
    authority = verify_authority()
    invalid = verify_invalid()
    final_save = verify_final_save()
    save_observer = verify_save_observer(b_install)
    python_unit = verify_python_unit()
    static_contracts = verify_static_contracts()

    query_native = read_jsonl(ROOT / QUERY_DIR / "native.jsonl")
    execution_native = read_jsonl(ROOT / EXEC_DIR / "native.jsonl")
    fixture_path, fixture_test_path, fixture_counts = build_real_fixture(query_native, execution_native)
    fixture_test = run_fixture_test(fixture_test_path)

    # Copy the seven documents only after the explicit gate above.  The staged
    # Python snapshot is represented by its immutable manifest and entries.
    paths = list(DOCS) + list(EVIDENCE_FILES) + list(STATIC_CONTRACT_FILES) + list(BUILD_FILES) + [
        _relative(Path(__file__)),
    ]
    files = archive_files(paths)
    for archive_path in (
        fixture_path,
        fixture_test_path,
        OUTPUT / "files" / "tests" / "r72_curry_fixture_pytest.txt",
    ):
        files.append({"path": _relative(archive_path), "bytes": archive_path.stat().st_size, "sha256": sha256_file(archive_path)})
    files.extend(snapshot_archive_entries(snapshot))
    # Avoid duplicate entries if a future snapshot path happens to overlap one
    # of the explicit archive paths.
    unique_files: list[dict[str, Any]] = []
    unique_paths: set[str] = set()
    for item in files:
        if item["path"] not in unique_paths:
            unique_paths.add(item["path"])
            unique_files.append(item)

    progress = {
        "schema": "r72_curry_progress_v1",
        "stage": "R72",
        "status": "delivered",
        "goal_status": "active",
        "actual_requests": len(execution["request_ids"]),
        "actual_native_outcomes": execution["outcomes"],
        "request_ids": execution["request_ids"],
        "request_binding_verified": execution["request_binding_verified"],
        "response_verified": execution["response_verified"],
        "journal_reopen_equal": execution["journal_reopen_equal"],
        "query": queries,
        "baseline_failure_preserved": baseline,
        "authority": authority,
        "invalid_execution": invalid,
        "save": final_save,
        "save_observer": save_observer,
        "python_regression": python_unit,
        "real_fixture_test": {**fixture_counts, **fixture_test},
        "build_lineage": builds,
        "python_source_snapshot": snapshot,
        "native_source_hashes_recomputed": False,
        "save_copied": False,
        "errors": [],
        "evidence": {
            "queries": QUERY_DIR,
            "baseline_execution": BASELINE_EXEC_DIR,
            "execution": EXEC_DIR,
            "authority": AUTHORITY_DIR,
            "invalid_execution": INVALID_DIR,
            "final_save": FINAL_SAVE_REPORT,
            "prior_final_save": PRIOR_SAVE_REPORT,
            "save_observer": SAVE_OBSERVER_REPORT,
            "python_regression": PYTHON_UNIT_DIR,
        },
        "next": [
            "trade_favors_for_trust / trade_favors_for_men",
            "gift / influence",
            "warscore",
            "R73 Trust/Men、赠款/影响和战争分继续研究；当前未宣称已运行能力",
        ],
        "delivery": _relative(OUTPUT / "manifest.json"),
    }
    manifest = {
        "schema": "r72_curry_delivery_manifest_v1",
        "stage": "R72",
        "status": "delivered",
        "progress": progress,
        "files": unique_files,
        "python_source_snapshot": snapshot,
        "native_build_identity": builds,
        "save_hash_reference": {
            "report": FINAL_SAVE_REPORT,
            "sha256": EXPECTED_SAVE_SHA,
            "size": EXPECTED_SAVE_SIZE,
            "date": EXPECTED_SAVE_DATE,
            "copied": False,
        },
        "docs_copied_after_explicit_ready": list(DOCS),
        "constraints": {
            "api_calls": 0,
            "game_queries": 0,
            "rea_calls": 0,
            "native_source_hashes_recomputed": False,
            "save_copied": False,
            "save_rescanned": False,
            "current_production_read_as_r72": False,
        },
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "delivered", "manifest": _relative(OUTPUT / "manifest.json"), "progress": _relative(PROGRESS_PATH), "files": len(unique_files), "errors": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()

