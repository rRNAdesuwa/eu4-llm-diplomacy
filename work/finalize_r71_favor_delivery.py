"""Create the bounded, reviewable R71 favor-trade delivery archive.

The finalizer is deliberately fail-closed.  It verifies the small reports and
JSONL evidence that already exist, copies the raw native JSONL beside the
reports, and records the final save hash without opening or copying the save.
It never recomputes the 89 native source hashes; those are referenced from the
E build manifest.

Run only after the release documents have been updated:

    python work/finalize_r71_favor_delivery.py --docs-ready
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work" / "runtime"
OUTPUT = RUNTIME / "r71-favor-delivery-20261020-001"
PROGRESS_PATH = RUNTIME / "r71-progress.json"
MAX_SMALL_BYTES = 16 * 1024 * 1024

E_BUILD = RUNTIME / "diplomacy-observer-20261020-r71-favor-gold-e"
D_BUILD = RUNTIME / "diplomacy-observer-20261020-r71-favor-gold-d"
H_BUILD = RUNTIME / "diplomacy-query-20261020-r71-favor-gold-h"

DOCS = (
    "docs/人情外交接口.md",
    "docs/外交能力矩阵.md",
    "docs/外交系统说明.md",
    "docs/外交接口开发方案.md",
    "docs/外交开发推进复盘.md",
    "PLAN.md",
    "HANDOFF.md",
)

# The three completed native runs are intentionally explicit: both report and
# raw JSONL are required in the archive, not merely an index or a hash.
MAIN_RUNS = {
    "outbound": {
        "dir": "work/runtime/r71-favor-outbound-20261020-002",
        "request_id": "r71_d_favor_outbound_pap_002",
        "actor": "FRA",
        "recipient": "PAP",
        "phase": "initiate",
        "outcome": "accepted",
        "native_state": 2,
        "pending_removed": False,
        "event": "native_diplomacy_favor_trade_execution_result",
        "amount_raw": 12927,
        "favor_before": 33632,
        "favor_after": 23632,
        "payer": "PAP",
        "receiver": "FRA",
        "controlled_treasury_before": 1000000,
        "controlled_treasury_after": 1012927,
    },
    "inbound_accept": {
        "dir": "work/runtime/r71-favor-inbound-accept-20261020-001",
        "request_id": "r71_g_favor_accept_sav_001",
        "actor": "SAV",
        "recipient": "FRA",
        "phase": "accept",
        "outcome": "accepted",
        "native_state": 2,
        "pending_removed": True,
        "event": "native_diplomacy_favor_trade_response_result",
        "amount_raw": 41508,
        "favor_before": 20231,
        "favor_after": 10231,
        "payer": "FRA",
        "receiver": "SAV",
        "controlled_treasury_before": 1000000,
        "controlled_treasury_after": 958492,
    },
    "inbound_reject": {
        "dir": "work/runtime/r71-favor-inbound-reject-20261020-001",
        "request_id": "r71_h_favor_reject_lit_001",
        "actor": "LIT",
        "recipient": "FRA",
        "phase": "reject",
        "outcome": "rejected",
        "native_state": 1,
        "pending_removed": True,
        "event": "native_diplomacy_favor_trade_response_result",
        "amount_raw": 41508,
        "favor_before": 20000,
        "favor_after": 20000,
        "payer": "FRA",
        "receiver": "LIT",
        "controlled_treasury_before": 958492,
        "controlled_treasury_after": 958492,
    },
}

INVALID_REPORT = "work/runtime/r71-favor-invalid-execution-20261020-002/report.json"
INVALID_NATIVE = "work/runtime/r71-favor-invalid-execution-20261020-002/native.jsonl"

# These report directories are small, self-contained query evidence.  In
# particular, the baseline re-projection keeps all eight public/native-event
# fixtures and its source batch; C003 and D004 retain their control snapshots
# and raw PAP/G​EN/SAV/LIT/ORL query evidence.
QUERY_DIRS = (
    "work/runtime/r71-favor-queries-20261020-001",
    "work/runtime/r71-favor-queries-20261020-002",
    "work/runtime/r71-favor-queries-20261020-003",
    "work/runtime/r71-favor-queries-20261020-004",
)

SCENE_DIRS = (
    "work/runtime/r71-favor-inbound-batch-20261020-001",
    "work/runtime/r71-favor-inbound-batch-20261020-002",
    "work/runtime/r71-favor-inbound-batch-20261020-003",
)

REPORT_FILES = (
    "work/runtime/r71-favor-inbound-final-save-20261020-001.json",
    "work/runtime/r71-favor-outbound-save-20261020-001.json",
    "work/runtime/r71-favor-inbound-accept-save-20261020-001.json",
    "work/runtime/r71-autosaves-restored-20261020-001.json",
    "work/runtime/r71-final-python-unit-20261020-002/report.json",
    "work/runtime/r71-final-python-unit-20261020-002/stdout.txt",
    "work/runtime/r71-final-python-unit-20261020-002/stderr.txt",
    "work/runtime/r71-favor-real-tests-20261020-001/report.json",
    "work/runtime/r71-favor-real-tests-20261020-001/pytest-output.txt",
    "work/runtime/r71-favor-scene-20261020-001/report.json",
    "work/runtime/r71-favor-budget-scene-20261020-001.json",
    "work/runtime/r71-favor-cache-scene-20261020-001.json",
    "work/runtime/r71-favor-inbound-ready-scene-20261020-001.json",
)

SAVE_REPORTS = (
    "work/runtime/r71-favor-inbound-final-save-20261020-001.json",
    "work/runtime/r71-favor-outbound-save-20261020-001.json",
    "work/runtime/r71-favor-inbound-accept-save-20261020-001.json",
)

STATIC_CONTRACT_FILES = (
    "work/runtime/r71-favor-family-contract-20261020-001/report.md",
    "work/runtime/r71-favor-family-contract-20261020-001/key-findings.md",
    "work/runtime/r71-favor-gold-vtable-20261020-001/report.md",
    "work/runtime/r71-curry-contract-20261020-001/report.md",
    "work/runtime/r71-favor-reason-contract-20261020-001/report.md",
    "work/runtime/r71-favor-reason-contract-20261020-001/report.json",
    "work/runtime/r71-favor-budget-contract-20261020-001/report.md",
    "work/runtime/r71-favor-save-baseline-20261020-001/report.md",
    "work/runtime/r71-favor-save-baseline-20261020-001/scan.json",
)

BUILD_FILES = (
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-e/build-manifest.json",
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-e/installation.json",
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-e/alliance-query.inc",
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-e/diplomacy-observer-v10.cpp",
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-d/build-manifest.json",
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-d/installation.json",
    "work/runtime/diplomacy-observer-20261020-r71-favor-gold-d/alliance-query.inc",
    "work/runtime/diplomacy-query-20261020-r71-favor-gold-h/build-manifest.json",
    "work/runtime/diplomacy-query-20261020-r71-favor-gold-h/installation.json",
    "work/runtime/diplomacy-query-20261020-r71-favor-gold-h/alliance-query.inc",
)

SOURCE_FILES = (
    "bridge/diplomacy.py",
    "bridge/diplomacy_catalog.py",
    "bridge/favor_trade.py",
    "bridge/tests/fixtures/r71_favor_execution_real.json",
    "bridge/tests/fixtures/r71_favor_queries_real.json",
    "bridge/tests/test_r71_favor_execution_real.py",
    "bridge/tests/test_r71_favor_queries_reproject.py",
    "work/reproject_r71_favor_queries.py",
    "work/finalize_r71_favor_delivery.py",
)


def _small(path: Path) -> Path:
    if not path.is_file():
        raise AssertionError(f"MISSING_FILE: {path}")
    if path.stat().st_size >= MAX_SMALL_BYTES:
        raise AssertionError(f"FILE_TOO_LARGE: {path} ({path.stat().st_size})")
    return path


def read_json(path: Path) -> dict[str, Any]:
    _small(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AssertionError(f"JSON_OBJECT_REQUIRED: {path}")
    return value


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_passed(report: dict[str, Any], label: str) -> None:
    require(report.get("status") == "passed", f"{label}: status={report.get('status')!r}")


def require_true_checks(report: dict[str, Any], label: str, key: str = "checks") -> None:
    checks = report.get(key)
    require(isinstance(checks, dict) and checks, f"{label}: missing {key}")
    require(all(value is True for value in checks.values()), f"{label}: false check")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    _small(path)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        require(isinstance(value, dict), f"{path}:{line_number}: JSON object required")
        rows.append(value)
    return rows


def verify_main_run(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    run_dir = ROOT / spec["dir"]
    report_path = run_dir / "report.json"
    native_path = run_dir / "native.jsonl"
    report = read_json(report_path)
    require_passed(report, label)
    require_true_checks(report, label)
    require(report.get("request_id") == spec["request_id"], f"{label}: request id")
    require(report.get("actor") == spec["actor"], f"{label}: actor")
    require(report.get("recipient") == spec["recipient"], f"{label}: recipient")
    require(report.get("phase") == spec["phase"], f"{label}: phase")
    require(report.get("native_slice", {}).get("status") == "ok", f"{label}: native slice")

    outer = report.get("result")
    require(isinstance(outer, dict), f"{label}: missing public result")
    require(outer.get("request_id") == spec["request_id"], f"{label}: result request id")
    require(outer.get("status") == spec["outcome"], f"{label}: result status")
    require(outer.get("submitted") is True, f"{label}: submitted")
    require(outer.get("game_outcome") == spec["outcome"], f"{label}: game outcome")
    native = outer.get("result")
    require(isinstance(native, dict), f"{label}: missing native result")
    for key in ("request_binding_verified", "response_verified", "execution_verified"):
        require(native.get(key) is True, f"{label}: {key}")
    require(native.get("family") == "favor_trade", f"{label}: family")
    require(native.get("event") == spec["event"], f"{label}: event")
    require(native.get("native_state") == spec["native_state"], f"{label}: native state")
    require(native.get("pending_removed") is spec["pending_removed"], f"{label}: pending")

    trade = native.get("favor_trade")
    require(isinstance(trade, dict), f"{label}: favor_trade")
    amount = trade.get("amount", {})
    favors = trade.get("favors", {})
    treasury = trade.get("controlled_treasury", {})
    require(amount.get("raw") == spec["amount_raw"], f"{label}: amount")
    require(amount.get("payer") == spec["payer"], f"{label}: payer")
    require(amount.get("receiver") == spec["receiver"], f"{label}: receiver")
    require(favors.get("before_raw") == spec["favor_before"], f"{label}: favor before")
    require(favors.get("after_raw") == spec["favor_after"], f"{label}: favor after")
    require(treasury.get("before_raw") == spec["controlled_treasury_before"], f"{label}: treasury before")
    require(treasury.get("after_raw") == spec["controlled_treasury_after"], f"{label}: treasury after")

    events = read_jsonl(native_path)
    selected = [
        event
        for event in events
        if event.get("event") == spec["event"] and event.get("request_id") == spec["request_id"]
    ]
    require(len(selected) == 1, f"{label}: native result event count={len(selected)}")
    event = selected[0]
    require(event.get("action_id") == "trade_favors_for_gold", f"{label}: native action")
    require(event.get("family") == "favor_trade", f"{label}: native family")
    require(event.get("actor") == spec["actor"], f"{label}: native actor")
    require(event.get("recipient") == spec["recipient"], f"{label}: native recipient")
    require(event.get("phase") == spec["phase"], f"{label}: native phase")
    require(event.get("native_state") == spec["native_state"], f"{label}: native event state")
    require(event.get("pending_removed") is spec["pending_removed"], f"{label}: native event pending")
    return {
        "report": report_path.relative_to(ROOT).as_posix(),
        "native": native_path.relative_to(ROOT).as_posix(),
        "request_id": spec["request_id"],
        "outcome": spec["outcome"],
        "event": spec["event"],
        "native_state": spec["native_state"],
        "request_binding_verified": True,
        "response_verified": True,
        "journal_reopen_equal": True,
    }


def verify_invalid() -> dict[str, Any]:
    report = read_json(ROOT / INVALID_REPORT)
    require_passed(report, "invalid_execution")
    require_true_checks(report, "invalid_execution")
    checks = report["checks"]
    for key in ("invalidated", "native_rule_reason", "unsubmitted", "journal_reopen_equal"):
        require(checks.get(key) is True, f"invalid_execution: {key}")
    result = report.get("result", {})
    require(result.get("request_id") == "r71_favor_invalid_gen_002", "invalid_execution: request")
    require(result.get("submitted") is False, "invalid_execution: submitted")
    require(result.get("game_outcome") == "unknown", "invalid_execution: outcome")
    events = read_jsonl(ROOT / INVALID_NATIVE)
    require(len(events) == 1 and events[0].get("native_validity") is False, "invalid_execution: native validity")
    return {
        "report": INVALID_REPORT,
        "native": INVALID_NATIVE,
        "request_id": result["request_id"],
        "native_validity": False,
        "unsubmitted": True,
    }


def verify_queries() -> dict[str, Any]:
    baseline = read_json(RUNTIME / "r71-favor-queries-20261020-002/report.json")
    require_passed(baseline, "queries_baseline_reproject")
    require_true_checks(baseline, "queries_baseline_reproject", "public_checks")
    require(len(baseline.get("cases", [])) == 8, "queries_baseline_reproject: eight cases")
    require(baseline.get("api_call_count") == 0, "queries_baseline_reproject: api calls")
    require(baseline.get("game_query_count") == 0, "queries_baseline_reproject: game queries")
    require(baseline.get("native_query_call_count") == 0, "queries_baseline_reproject: native queries")
    require(baseline.get("execute_call_count") == 0, "queries_baseline_reproject: execute calls")
    require(baseline.get("game_contact") is False, "queries_baseline_reproject: game contact")
    require(baseline.get("availability", {}).get("all_cases_unavailable") is True, "queries_baseline_reproject: availability")
    require(all(case.get("legality", {}).get("status") == "unavailable" for case in baseline["cases"]), "queries_baseline_reproject: case status")
    require(baseline.get("health_source_reused") is True, "queries_baseline_reproject: health reuse")

    c003 = read_json(RUNTIME / "r71-favor-queries-20261020-003/report.json")
    d004 = read_json(RUNTIME / "r71-favor-queries-20261020-004/report.json")
    require_passed(c003, "queries_c003")
    require_passed(d004, "queries_d004")
    require_true_checks(c003, "queries_c003")
    require_true_checks(d004, "queries_d004")
    require(len(c003.get("cases", [])) == 4, "queries_c003: four cases")
    require(len(d004.get("cases", [])) == 1, "queries_d004: one case")
    pap = d004["cases"][0]
    require(pap.get("name") == "trade_favors_for_gold_PAP", "queries_d004: PAP case")
    acceptance = pap.get("acceptance", {})
    require(acceptance.get("native_total") == 141, "queries_d004: native total")
    require(acceptance.get("items", [{}])[0].get("native_value") == 50, "queries_d004: favors factor")
    require(acceptance.get("items", [{}, {}])[1].get("native_value") == 91, "queries_d004: opinion factor")
    return {
        "baseline_reprojected_cases": 8,
        "c003_cases": 4,
        "d004_cases": 1,
        "api_calls": 0,
        "game_queries": 0,
        "native_queries": 0,
        "baseline_all_unavailable": True,
        "pap_acceptance_factors": [141, 50, 91],
        "reports": [
            "work/runtime/r71-favor-queries-20261020-002/report.json",
            "work/runtime/r71-favor-queries-20261020-003/report.json",
            "work/runtime/r71-favor-queries-20261020-004/report.json",
        ],
    }


def verify_save_report(path: str, expected_field_count: int | None = None) -> dict[str, Any]:
    report = read_json(ROOT / path)
    require_passed(report, path)
    require(report.get("errors") == [], f"{path}: errors")
    for key in ("favors_checks", "treasury_checks"):
        checks = report.get(key)
        require(isinstance(checks, list), f"{path}: {key}")
        require(all(item.get("match") is True for item in checks), f"{path}: {key} mismatch")
    count = len(report.get("favors_checks", [])) + len(report.get("treasury_checks", []))
    if expected_field_count is not None:
        require(count == expected_field_count, f"{path}: field count={count}")
    return {
        "path": path,
        "status": report["status"],
        "errors": [],
        "field_checks": count,
        "save_sha256": report.get("save", {}).get("sha256"),
        "save_size": report.get("save", {}).get("size"),
        "save_copied": False,
    }


def verify_final_save() -> dict[str, Any]:
    report = read_json(ROOT / "work/runtime/r71-favor-inbound-final-save-20261020-001.json")
    require_passed(report, "final_save")
    require(report.get("schema") == "r71_favor_save_verify_v1", "final_save: schema")
    require(report.get("errors") == [], "final_save: errors")
    events = report.get("events", {})
    require(events.get("selected_complete_verified") == 2, "final_save: selected events")
    require(events.get("named_events_seen") == 2, "final_save: named events")
    require(events.get("filtered_incomplete_or_unverified") == 0, "final_save: filtered events")
    require(events.get("malformed_selected") == 0, "final_save: malformed events")
    save = report.get("save", {})
    require(save.get("sha256") == "f736539b7802943a943d878c2ae1ef2f0f2647487d749897766b867da005fc2f", "final_save: sha256")
    require(isinstance(save.get("size"), int) and save["size"] > 40_000_000, "final_save: save size")
    fields = verify_save_report("work/runtime/r71-favor-inbound-final-save-20261020-001.json", 5)
    fields["events"] = {
        "selected_complete_verified": events["selected_complete_verified"],
        "named_events_seen": events["named_events_seen"],
        "filtered_incomplete_or_unverified": events["filtered_incomplete_or_unverified"],
        "malformed_selected": events["malformed_selected"],
    }
    fields["save_sha256"] = save["sha256"]
    fields["save_size"] = save["size"]
    return fields


def _source_reference(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"name": item.get("name") or item.get("path"), "sha256": item.get("sha256")}
        for item in items
    ]


def verify_builds() -> dict[str, Any]:
    e_manifest = read_json(E_BUILD / "build-manifest.json")
    d_manifest = read_json(D_BUILD / "build-manifest.json")
    h_manifest = read_json(H_BUILD / "build-manifest.json")
    h_install = read_json(H_BUILD / "installation.json")
    d_install = read_json(D_BUILD / "installation.json")
    e_install = read_json(E_BUILD / "installation.json")
    require(len(e_manifest.get("sources", [])) == 89, "builds: E source count")
    require(e_manifest.get("dll_sha256") == "a1730c5a961e7b43b13f6f14d4a43733e45ce2651c83efdda17a043b2c38d638", "builds: E DLL")
    require(d_manifest.get("dll_sha256") == "33d4eaa0d61d2cd270812c8cb530da1c867d8a00ea38b002fe5dff9eef5af683", "builds: D DLL")
    require(h_manifest.get("dll_sha256") == e_manifest["dll_sha256"], "builds: H lineage")
    require(d_manifest["dll_sha256"] != e_manifest["dll_sha256"], "builds: distinct D lineage")
    require(h_install.get("dll_sha256") == e_manifest["dll_sha256"], "builds: H install DLL")
    require(h_install.get("installation_returncode") == 0, "builds: H install")
    require(d_install.get("dll_sha256") == d_manifest["dll_sha256"], "builds: D install DLL")
    e_sources = _source_reference(e_manifest["sources"])
    d_sources = _source_reference(d_manifest["sources"])
    require(all(item["name"] and item["sha256"] for item in e_sources), "builds: E source references")
    require(all(item["name"] and item["sha256"] for item in d_sources), "builds: D source references")
    return {
        "e_dll_sha256": e_manifest["dll_sha256"],
        "d_dll_sha256": d_manifest["dll_sha256"],
        "h_dll_sha256": h_manifest["dll_sha256"],
        "native_sources": len(e_manifest["sources"]),
        "native_source_hashes_recomputed": False,
        "h_installation_returncode": h_install["installation_returncode"],
        "e_session_id": e_install["session_id"],
        "d_session_id": d_install["session_id"],
        "h_session_id": h_install["session_id"],
        "source_reference": e_sources,
        "d_source_reference": d_sources,
        "source_hash_differences": [
            item["name"]
            for item in e_sources
            if next((d["sha256"] for d in d_sources if d["name"] == item["name"]), None) != item["sha256"]
        ],
    }


def verify_regressions() -> dict[str, Any]:
    unit = read_json(RUNTIME / "r71-final-python-unit-20261020-002/report.json")
    require_passed(unit, "full_python_unit")
    require(unit.get("exit_code") == 0, "full_python_unit: exit code")
    require("870 passed" in unit.get("summary", "") and "653 subtests passed" in unit.get("summary", ""), "full_python_unit: summary")
    real = read_json(RUNTIME / "r71-favor-real-tests-20261020-001/report.json")
    require_passed(real, "real_fixture_tests")
    require(real.get("exit_code") == 0, "real_fixture_tests: exit code")
    require(real.get("game_contact") is False and real.get("rea_calls") == 0, "real_fixture_tests: external contact")
    require(isinstance(real.get("fixture_bytes"), int) and real["fixture_bytes"] < 1_000_000, "real_fixture_tests: fixture size")
    autosaves = read_json(ROOT / "work/runtime/r71-autosaves-restored-20261020-001.json")
    require_passed(autosaves, "autosaves_restored")
    return {
        "full_python_unit": unit,
        "real_fixture_tests": {
            "status": real["status"],
            "exit_code": real["exit_code"],
            "fixture_bytes": real["fixture_bytes"],
            "game_contact": real["game_contact"],
            "rea_calls": real["rea_calls"],
        },
        "autosaves_restored": autosaves,
    }


def iter_archive_files() -> Iterable[Path]:
    explicit = list(DOCS) + list(REPORT_FILES) + list(STATIC_CONTRACT_FILES) + list(BUILD_FILES) + list(SOURCE_FILES)
    for run in MAIN_RUNS.values():
        explicit.extend((f"{run['dir']}/report.json", f"{run['dir']}/native.jsonl"))
    explicit.extend((INVALID_REPORT, INVALID_NATIVE))
    seen: set[Path] = set()
    for relative in explicit:
        path = ROOT / relative
        if path not in seen:
            seen.add(path)
            yield path
    for directory in QUERY_DIRS + SCENE_DIRS:
        base = ROOT / directory
        _small(base / "report.json") if directory.endswith("queries-20261020-001") else None
        if not base.is_dir():
            raise AssertionError(f"MISSING_DIRECTORY: {base}")
        for path in sorted(base.rglob("*")):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path
    # Preserve the exact source-file snapshots used by the two R71 native
    # lineages.  Their existing manifest hashes are carried into the archive;
    # the finalizer does not rescan or recompute the 89-source manifests.
    for build_dir in (E_BUILD, D_BUILD):
        build_manifest = read_json(build_dir / "build-manifest.json")
        for item in build_manifest.get("sources", []):
            path = build_dir / (item.get("name") or item.get("path", ""))
            if path not in seen:
                seen.add(path)
                yield path


def copy_and_hash(paths: Iterable[Path], trusted_hashes: dict[str, str] | None = None) -> list[dict[str, Any]]:
    trusted_hashes = trusted_hashes or {}
    files: list[dict[str, Any]] = []
    for source in paths:
        _small(source)
        relative = source.relative_to(ROOT)
        target = OUTPUT / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        digest = trusted_hashes.get(relative.as_posix())
        if digest is None:
            with target.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": digest})
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-ready",
        action="store_true",
        help="confirm that the release documents are ready to copy and hash",
    )
    args = parser.parse_args()
    if not args.docs_ready:
        raise SystemExit("DOCS_NOT_READY: rerun with --docs-ready after docs/PLAN/HANDOFF are final")
    require(not OUTPUT.exists(), "OUTPUT_EXISTS")
    require(not PROGRESS_PATH.exists(), "PROGRESS_EXISTS")
    for relative in DOCS:
        _small(ROOT / relative)

    actual_runs = {label: verify_main_run(label, spec) for label, spec in MAIN_RUNS.items()}
    invalid = verify_invalid()
    queries = verify_queries()
    final_save = verify_final_save()
    outbound_save = verify_save_report("work/runtime/r71-favor-outbound-save-20261020-001.json", 3)
    inbound_accept_save = verify_save_report("work/runtime/r71-favor-inbound-accept-save-20261020-001.json", 3)
    builds = verify_builds()
    regressions = verify_regressions()

    trusted_source_hashes = {}
    for build_dir, references in (
        (E_BUILD, builds["source_reference"]),
        (D_BUILD, builds["d_source_reference"]),
    ):
        for reference in references:
            trusted_source_hashes[(build_dir / reference["name"]).relative_to(ROOT).as_posix()] = reference["sha256"]
    files = copy_and_hash(iter_archive_files(), trusted_source_hashes)
    progress = {
        "stage": "R71",
        "status": "delivered",
        "goal_status": "active",
        "actual_requests": len(actual_runs),
        "actual_native_outcomes": {label: value["outcome"] for label, value in actual_runs.items()},
        "request_ids": [value["request_id"] for value in actual_runs.values()],
        "request_binding_verified": all(value["request_binding_verified"] for value in actual_runs.values()),
        "response_verified": all(value["response_verified"] for value in actual_runs.values()),
        "journal_reopen_equal": all(value["journal_reopen_equal"] for value in actual_runs.values()),
        "invalid_execution": invalid,
        "queries": queries,
        "build_lineage": builds,
        "save": {
            "sha256": final_save["save_sha256"],
            "size": final_save["save_size"],
            "path": "work/runtime/r71-favor-inbound-final-save-20261020-001.json:save.path",
            "copied": False,
            "field_checks": final_save["field_checks"],
            "errors": [],
        },
        "save_checkers": {
            "final": final_save,
            "outbound": outbound_save,
            "inbound_accept": inbound_accept_save,
        },
        "regression": regressions["full_python_unit"],
        "real_fixture_regression": regressions["real_fixture_tests"],
        "autosaves_restored": regressions["autosaves_restored"],
        "dedicated_save_reload": False,
        "native_source_hashes_recomputed": False,
        "evidence": {
            "outbound": "work/runtime/r71-favor-outbound-20261020-002",
            "inbound_accept": "work/runtime/r71-favor-inbound-accept-20261020-001",
            "inbound_reject": "work/runtime/r71-favor-inbound-reject-20261020-001",
            "invalid_execution": INVALID_REPORT,
            "queries": queries["reports"],
            "final_save": "work/runtime/r71-favor-inbound-final-save-20261020-001.json",
        },
        "delivery": (OUTPUT / "manifest.json").relative_to(ROOT).as_posix(),
        "next": [
            "获取人情、换取信任与人力（Curry/trust/men）",
            "赠款与影响国家（gift/influence）",
            "live战争分、组成明细与战争目标分（warscore）",
        ],
    }
    manifest = {
        "stage": "R71",
        "status": "delivered",
        "progress": progress,
        "files": files,
        "native_source_reference": builds["source_reference"],
        "native_d_source_reference": builds["d_source_reference"],
        "native_source_hash_differences": builds["source_hash_differences"],
        "save_hash_reference": {
            "report": "work/runtime/r71-favor-inbound-final-save-20261020-001.json",
            "sha256": final_save["save_sha256"],
            "copied": False,
        },
        "docs_copied_after_explicit_ready": list(DOCS),
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "delivered", "manifest": progress["delivery"], "files": len(files), "errors": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
