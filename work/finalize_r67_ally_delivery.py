"""Archive R67's ally-beneficiary run, reusing the unchanged R66 implementation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
DIRECTORY = "diplomacy-query-20261019-r67-ally-occupations-d"
OUTPUT = RUNTIME / "r67-ally-delivery-20261019-001"
SOURCES = (
    "work/prepare_r67_ally_occupations_scene.py",
    "work/run_r67_ally_peace_queries.py",
    "work/run_r67_ally_blocked_execution.py",
    "work/verify_r67_ally_save.py",
    "work/finalize_r67_ally_delivery.py",
    "bridge/tests/test_r67_ally_peace_real.py",
    "bridge/tests/fixtures/r67_ally_peace_real.json",
    "docs/盟主为参战国选择议和省份.md",
    "docs/宣战条款与议和净OE预览.md",
    "docs/议和接口与运行验收.md",
    "docs/外交能力矩阵.md",
    "docs/外交系统说明.md",
    "docs/外交开发推进复盘.md",
    "PLAN.md", "HANDOFF.md",
    "work/runtime/r67-beneficiary-contract-20261019-001/beneficiary-conclusion.md",
)
REPORTS = {
    "baseline_delivery": "r66-python-docs-delivery-20261019-001/manifest.json",
    "baseline_tests": "r66-final-python-unit-20261019-001/report.json",
    "build_c": "diplomacy-query-20261019-r66-rules-netoe-c/build-manifest.json",
    "build": DIRECTORY + "/build-manifest.json",
    "installation": DIRECTORY + "/installation.json",
    "scene": "r67-ally-occupations-scene-20261019-001/report.json",
    "queries": "r67-ally-peace-queries-20261019-001/report.json",
    "blocked_execution": "r67-ally-blocked-execution-20261019-001/report.json",
    "outbound": "r67-ally-outbound-execution-20261019-001/report.json",
    "save": DIRECTORY + "/save-observer-report-1792418738767816800.json",
    "save_fields": "r67-ally-save-fields-20261019-001/report.json",
    "fixture_tests": "r67-python-fixture-unit-20261019-001/report.json",
}


def require(value: object, text: str) -> None:
    if not value:
        raise RuntimeError(text)


def read(path: Path) -> dict:
    require(path.stat().st_size <= 16 * 1024 * 1024, "REPORT_TOO_LARGE:" + str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    require(path.stat().st_size <= 16 * 1024 * 1024, "ARTIFACT_TOO_LARGE:" + str(path))
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def all_checks(report: dict, name: str) -> None:
    checks = report.get("checks")
    require(isinstance(checks, dict) and bool(checks)
            and all(value is True for value in checks.values()), "CHECKS_NOT_PASSED:" + name)


def main() -> None:
    require(not OUTPUT.exists(), "IMMUTABLE_DELIVERY_EXISTS")
    reports = {key: read(RUNTIME / value) for key, value in REPORTS.items()}
    for key in ("queries", "blocked_execution", "outbound", "save_fields", "fixture_tests", "baseline_tests"):
        require(reports[key].get("status") == "passed", "REPORT_NOT_PASSED:" + key)
    for key in ("queries", "blocked_execution", "outbound", "save_fields"):
        all_checks(reports[key], key)
    require(reports["scene"].get("status") == "prepared", "SCENE_NOT_PREPARED")
    require(reports["save"].get("status") == "success", "SAVE_NOT_COMPLETE")
    require(len(reports["queries"]["cases"]) == 4, "FOUR_QUERY_CASES_REQUIRED")
    require(len(reports["save_fields"]["checks"]) == 26, "SAVE_FIELD_COVERAGE_INCOMPLETE")
    build, original, install = (reports[key] for key in ("build", "build_c", "installation"))
    require(build["sources"] == original["sources"] and len(build["sources"]) == 87,
            "IMMUTABLE_NATIVE_SOURCE_SET_CHANGED")
    require(build["dll_sha256"] == original["dll_sha256"] == install["dll_sha256"],
            "DLL_BINDING_DIFFERS")
    require(build.get("construction_mode") == "reused_immutable_build"
            and install.get("installation_returncode") == 0, "BUILD_OR_INSTALL_NOT_REUSED")
    for key in ("queries", "blocked_execution"):
        require(reports[key]["session_id"] == install["session_id"], "SESSION_DIFFERS:" + key)
    outgoing = reports["outbound"]
    require(outgoing["session"]["session_id"] == install["session_id"], "OUTBOUND_SESSION_DIFFERS")
    require(outgoing["execute_call_count"] == outgoing["business_submission_count"] == 1,
            "ONE_ACTUAL_SUBMISSION_REQUIRED")
    require(outgoing["result"]["status"] == "rejected" and outgoing["result"]["submitted"] is True,
            "NATIVE_AI_REJECTION_MISSING")
    terms = outgoing["parameters"]["execute"]["peace_context"]["terms"]
    require(any(term.get("action_id") == "cede_province" and term.get("beneficiary") == "ORL"
                and term.get("province_ids") == [88] for term in terms), "ORL_TERM_MISSING")
    require(any(term.get("action_id") == "demand_ducats" and term.get("claimant") == "FRA"
                and term.get("payer") == "BUR" and term.get("amount") == "1.0" for term in terms),
            "MONEY_ROLES_DIFFER")
    require(reports["blocked_execution"]["business_submission"] is False, "ILLEGAL_SUBMISSION")
    require(reports["fixture_tests"]["tests"] == 4
            and reports["fixture_tests"]["exit_code"] == 0, "NEW_FIXTURE_TESTS_FAILED")
    require(reports["baseline_tests"]["passed"] == 803
            and reports["baseline_tests"]["subtests_passed"] == 625, "BASELINE_TESTS_DIFFER")
    production = [entry for entry in reports["baseline_delivery"]["sources"]
                  if entry["path"].startswith("bridge/") and "/tests/" not in entry["path"]]
    require(bool(production), "BASELINE_PRODUCTION_BINDING_MISSING")
    require(all(digest(ROOT / entry["path"]) == entry["sha256"] for entry in production),
            "PRODUCTION_CHANGED_REUSED_TESTS_INVALID")
    # Validate every input before creating the immutable delivery directory.
    for value in SOURCES:
        require((ROOT / value).is_file(), "MISSING_SOURCE:" + value)
    OUTPUT.mkdir()
    records = []
    for relative in (*SOURCES, *("work/runtime/" + value for value in REPORTS.values())):
        source = ROOT / relative
        destination = OUTPUT / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append({"path": relative, "bytes": source.stat().st_size, "sha256": digest(destination)})
    progress = {
        "stage": "R67", "status": "delivered", "goal_status": "active",
        "installation": "work/runtime/" + REPORTS["installation"],
        "dll_sha256": build["dll_sha256"], "native_sources": 87,
        "new_native_build": False, "query_cases": 4, "query_checks": 9,
        "blocked_execution_checks": 7, "outbound_checks": 17,
        "outbound_submissions": 1, "native_outcome": "rejected",
        "save_field_checks": 26, "new_fixture_tests": 4,
        "reused_full_regression": {"tests": 803, "subtests": 625,
                                   "production_hashes_match": True},
        "save_reference": reports["save"]["save"], "save_hash_recomputed": False,
        "save_reload_validation": False,
        "next": ["具体对象的CB正当/不正当条款", "释放国家完整净OE", "剩余阶段、公平信息与模型循环"],
        "delivery": str((OUTPUT / "manifest.json").relative_to(ROOT)).replace("\\", "/"),
    }
    manifest = {"stage": "R67", "status": "delivered", "goal_status": "active",
                "progress": progress, "files": records, "saves_copied": False,
                "dlls_copied": False, "native_source_hashes_recomputed": False}
    for path, value in ((OUTPUT / "manifest.json", manifest),
                        (RUNTIME / "r67-progress.json", progress)):
        require(not path.exists(), "REFUSE_OVERWRITE:" + str(path))
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "delivered", "manifest": progress["delivery"],
                      "artifact_count": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
