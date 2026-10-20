"""Archive the mixed-country-money query, native response and final save once."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
BUILD = "diplomacy-query-20261020-r70-country-money-a"
OUTPUT = RUNTIME / "r70-country-money-delivery-20261020-001"
REPORTS = {
    "build": BUILD + "/build-manifest.json", "installation": BUILD + "/installation.json",
    "queries": "r70-country-money-queries-20261020-007/report.json",
    "execution": "r70-country-money-execution-20261020-001",
    "fields": "r70-country-money-save-fields-20261020-001/report.json",
    "journal": "r70-journal-reopen-20261020-001/report.json",
    "save": BUILD + "/save-observer-report-1792429708814279000.json",
    "advance": BUILD + "/advance-context-bdb62b46c8ed4b638a10014bc1490d6b/report.json",
    "tests": "r70-final-python-unit-20261020-001/report.json",
    "wire": "r70-country-money-wire-20261020-001/result.json",
}
SOURCES = (
    "bridge/diplomacy.py", "bridge/tests/test_r69_country_money_wire.py",
    "bridge/tests/test_r70_country_money_real.py", "bridge/tests/fixtures/r70_country_money_real.json",
    "work/native/test-peace-country-wire.cpp", "work/run_r69_peace_rule_queries.py",
    "work/run_r70_country_money_execution.py", "work/verify_r70_country_money_save.py",
    "tools/confirm_observed_achievement_warning.py", "work/finalize_r70_country_money_delivery.py",
    "docs/议和条款正当性与释放国家净OE.md", "docs/外交开发推进复盘.md",
    "docs/外交系统说明.md", "docs/外交能力矩阵.md", "PLAN.md", "HANDOFF.md",
)


def read(path):
    assert path.is_file() and path.stat().st_size < 16 * 1024 * 1024, str(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    assert not OUTPUT.exists(), "OUTPUT_EXISTS"
    reports = {k: read(RUNTIME / p) for k, p in REPORTS.items()}
    for key in ("queries", "fields", "journal", "tests"):
        assert reports[key]["status"] == "passed", key
    for key in ("queries", "fields", "journal"):
        assert reports[key]["checks"] and all(v is True for v in reports[key]["checks"].values()), key
    build, install, queries = reports["build"], reports["installation"], reports["queries"]
    assert len(build["sources"]) == 88
    assert build["dll_sha256"] == install["dll_sha256"] and install["installation_returncode"] == 0
    assert queries["session_id"] == install["session_id"]
    assert queries["mixed_country_money_preview_supported"] is True
    assert len(queries["cases"]) == 16 and queries["live_query_count"] == 0
    execution = reports["execution"]
    result = execution["steps"]["outbound"]["result"]
    assert execution["status"] == "stage_passed" and execution["through"] == "outbound"
    assert result["request_id"] == "r70_country_money_001_outbound"
    assert result["submitted"] is True and result["status"] == "rejected"
    assert result["result"]["request_binding_verified"] and result["result"]["response_verified"]
    assert reports["save"]["status"] == "success" and reports["advance"]["status"] == "completed"
    assert reports["wire"]["passed"] is True and reports["wire"]["checks"] == 16
    paths = [ROOT / p for p in SOURCES] + [RUNTIME / p for p in REPORTS.values()]
    paths.extend([
        RUNTIME / "r70-final-python-unit-20261020-001/pytest.log",
        RUNTIME / BUILD / "alliance-query.inc", RUNTIME / BUILD / "diplomacy-observer-v10.cpp",
        RUNTIME / "r70-favors-contract-20261020-001/report.md",
        RUNTIME / "r71-favor-gold-vtable-20261020-001/report.md",
        RUNTIME / "r70-warscore-contract-20261020-001/report.md",
        RUNTIME / "r70-gift-influence-contract-20261020-001/report.md",
    ])
    for path in paths:
        assert path.is_file() and path.stat().st_size < 16 * 1024 * 1024, str(path)
    OUTPUT.mkdir()
    files = []
    for path in dict.fromkeys(paths):
        relative = path.relative_to(ROOT)
        target = OUTPUT / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": digest})
    progress = {
        "stage": "R70", "status": "delivered", "goal_status": "active",
        "session_id": install["session_id"], "pid": install["pid"],
        "dll_sha256": build["dll_sha256"], "native_sources": 88,
        "native_query_results": 15, "query_records": 16,
        "actual_outbound_requests": 1, "native_ai_outcome": "rejected",
        "request_id": result["request_id"], "date_raw": 56553384,
        "save": reports["save"]["save"], "save_field_checks": 16,
        "regression": reports["tests"], "wire_checks": 16,
        "journal_reopen_equal": True, "dedicated_save_reload": False,
        "native_source_hashes_recomputed": False,
        "evidence": REPORTS, "delivery": (OUTPUT / "manifest.json").relative_to(ROOT).as_posix(),
        "next": ["以已证明的3bce/1c80980对象接通人情换金币", "获取人情、换信任与人力",
                 "赠款与影响国家", "live战争分、组成明细与战争目标分", "其他旧条款与国家条款混合", "其余阶段、公平信息与常驻模型循环"],
    }
    manifest = {"stage": "R70", "status": "delivered", "progress": progress,
                "files": files, "native_source_reference": build["sources"],
                "historical_family_reference": "r69-peace-family-20261020-001/report.json"}
    progress_path = RUNTIME / "r70-progress.json"
    assert not progress_path.exists(), "PROGRESS_EXISTS"
    for path, value in ((OUTPUT / "manifest.json", manifest), (progress_path, progress)):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "delivered", "manifest": progress["delivery"], "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
