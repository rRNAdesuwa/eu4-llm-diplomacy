"""Archive the R68 runtime batch, final regression and source snapshots once."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
BUILD_A = "diplomacy-query-20261019-r68-diplomat-a"
BUILD_B = "diplomacy-query-20261019-r68-diplomat-b"
OUTPUT = RUNTIME / "r68-diplomat-delivery-20261019-001"
SOURCES = (
    "bridge/diplomacy.py", "bridge/diplomat_availability.py", "bridge/peace_rejection.py",
    "bridge/tests/test_diplomat_availability.py", "bridge/tests/test_diplomat_availability_integration.py",
    "bridge/tests/test_r68_diplomat_real.py", "bridge/tests/fixtures/r68_diplomat_real.json",
    "bridge/tests/test_r68_annex_partial_candidates.py",
    "work/run_r68_diplomat_batch.py", "work/verify_r68_diplomat_saves.py",
    "work/finalize_r68_diplomat_delivery.py",
    "docs/外交官可用性与失败原因.md", "docs/外交能力矩阵.md", "docs/外交系统说明.md",
    "docs/外交开发推进复盘.md", "docs/外交运行工作流.md", "PLAN.md", "HANDOFF.md",
)
REPORTS = {
    "build_a": BUILD_A + "/build-manifest.json",
    "install_a": BUILD_A + "/installation.json",
    "build_b": BUILD_B + "/build-manifest.json",
    "install_b": BUILD_B + "/installation.json",
    "occupy": "r68-diplomat-batch-20261019-001/occupy/report.json",
    "zero": "r68-diplomat-batch-20261019-002/zero/report.json",
    "recall": "r68-diplomat-batch-20261019-002/recall/report.json",
    "recovered": "r68-diplomat-batch-20261019-002/recovered/report.json",
    "journal": "r68-journal-reopen-20261019-001/report.json",
    "fields": "r68-diplomat-save-fields-20261019-002/report.json",
    "family": "r68-zero-peace-family-20261019-002/report.json",
    "save_zero": BUILD_A + "/save-observer-report-1792420478848425900.json",
    "save_returned": BUILD_B + "/save-observer-report-1792420921666356800.json",
    "tests": "r68-final-python-unit-20261019-001/report.json",
}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def read(path):
    require(path.stat().st_size < 16 * 1024 * 1024, "INPUT_TOO_LARGE")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    require(not OUTPUT.exists(), "DELIVERY_EXISTS")
    reports = {k: read(RUNTIME / p) for k, p in REPORTS.items()}
    for key in ("occupy", "zero", "recall", "recovered", "journal", "fields", "family", "tests"):
        require(reports[key].get("status") == "passed", "REPORT_NOT_PASSED:" + key)
    for key in ("occupy", "zero", "recall", "recovered", "fields"):
        require(reports[key].get("checks") and all(v is True for v in reports[key]["checks"].values()), "CHECK_FAILED:" + key)
    a, b, install = reports["build_a"], reports["build_b"], reports["install_b"]
    require(len(a["sources"]) == len(b["sources"]) == 87, "SOURCE_COVERAGE_DIFFERS")
    require(b["dll_sha256"] == install["dll_sha256"] and install["installation_returncode"] == 0, "DLL_BINDING_FAILED")
    require(a["dll_sha256"] != b["dll_sha256"], "TWO_BUILDS_REQUIRED")
    for key in ("zero", "recall", "recovered"):
        require(reports[key]["session_id"] == install["session_id"], "SESSION_DIFFERS:" + key)
    require(len(reports["zero"]["cases"]) == 21 and len(reports["zero"]["checks"]) == 63, "ZERO_BATCH_COVERAGE_DIFFERS")
    require(len(reports["zero"]["native_rejections"]) == 3 and all(
        row["result"].get("reason_code") == "NATIVE_DIPLOMAT_UNAVAILABLE"
        and row["result"].get("submitted") is False
        and row["result"].get("binding_complete") is True
        for row in reports["zero"]["native_rejections"]), "NATIVE_REJECTIONS_INCOMPLETE")
    require(all(e["result"].get("submitted") is False for e in reports["zero"]["executions"]), "ILLEGAL_SUBMISSION")
    require(len(reports["fields"]["checks"]) == 11, "SAVE_FIELD_COVERAGE_DIFFERS")
    require(all(r["equal"] for r in reports["journal"]["cases"]), "DURABLE_RESULTS_DIFFER")
    require(reports["tests"]["exit_code"] == 0, "REGRESSION_FAILED")
    for key in ("save_zero", "save_returned"):
        require(reports[key].get("status") == "success", "SAVE_FAILED:" + key)
    source_paths = [ROOT / p for p in SOURCES]
    source_paths.extend(sorted((ROOT / "bridge/tests/fixtures").glob("r68*annex*.json")))
    source_paths.extend(sorted((ROOT / "work").glob("reproject_r68*.py")))
    source_paths.extend(RUNTIME / p for p in REPORTS.values())
    source_paths.append(RUNTIME / "r68-final-python-unit-20261019-001/pytest.log")
    # Native source identities were captured by the successful B build. Copy
    # the seven changed immutable build inputs without hashing all 87 again.
    for name in ("alliance-execution.inc", "declarewar-query.inc", "declarewar-execution-preflight.inc",
                 "peace-empty-offer-query.inc", "peace-execution-preflight.inc", "insult-query.inc", "vassal-query.inc"):
        source_paths.append(RUNTIME / BUILD_B / name)
    for path in source_paths:
        require(path.is_file() and path.stat().st_size < 16 * 1024 * 1024, "MISSING_OR_LARGE_INPUT:" + str(path))
    OUTPUT.mkdir()
    records = []
    for path in dict.fromkeys(source_paths):
        relative = path.relative_to(ROOT)
        destination = OUTPUT / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        with destination.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        records.append({"path": relative.as_posix(), "bytes": destination.stat().st_size, "sha256": digest})
    progress = {
        "stage": "R68", "status": "delivered", "goal_status": "active",
        "session_id": install["session_id"], "installation": REPORTS["install_b"],
        "dll_sha256": b["dll_sha256"], "native_sources": 87,
        "query_cases": 21, "zero_checks": 63, "save_field_checks": 11,
        "actual_operations": ["start_improve_MLO", "stop_improve_MLO"],
        "blocked_api_executions": 3, "blocked_fresh_native_executions": 3,
        "free_diplomats": {"before": 1, "occupied": 0, "returned": 2},
        "final_date_raw": 56552760,
        "regression": reports["tests"],
        "save_references": {k: reports[k]["save"] for k in ("save_zero", "save_returned")},
        "save_reload_validation": False, "native_source_hashes_recomputed": False,
        "deferred_error_branches": [
            "候选或参与者读取失败早于宣战外交官原因，随下一相关native构建调整错误优先级",
            "非必需动作的外交官上下文读取失败分支，随下一相关native构建处理"],
        "next": ["具体对象CB正当性", "释放国家完整净OE", "剩余阶段、公平信息与常驻模型循环"],
        "delivery": (OUTPUT / "manifest.json").relative_to(ROOT).as_posix(),
    }
    manifest = {"stage": "R68", "status": "delivered", "goal_status": "active",
                "progress": progress, "files": records,
                "native_source_reference": b["sources"], "saves_copied": False, "dlls_copied": False}
    for path, value in ((OUTPUT / "manifest.json", manifest), (RUNTIME / "r68-progress.json", progress)):
        require(not path.exists(), "REFUSE_OVERWRITE:" + str(path))
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "delivered", "manifest": progress["delivery"], "files": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
