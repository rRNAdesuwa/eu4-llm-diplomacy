"""Archive the R69 native rule queries, final regression and small sources once."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
BUILD = "diplomacy-query-20261019-r69-justification-netoe-a"
SOURCES = (
    "bridge/diplomacy.py", "bridge/peace_execution.py", "bridge/peace_consequences.py",
    "bridge/peace_justification.py", "bridge/tests/test_peace_justification.py",
    "bridge/tests/test_r69_country_offer_discovery.py", "bridge/tests/test_r69_peace_rules_real.py",
    "bridge/tests/fixtures/r69_peace_rules_real.json", "work/run_r69_peace_rule_queries.py",
    "work/prepare_r69_release_oe_scene.py", "work/verify_r69_release_oe_preview.py",
    "work/finalize_r69_rule_delivery.py", "work/native/build-diplomacy-observer.ps1",
    "docs/议和条款正当性与释放国家净OE.md", "docs/外交能力矩阵.md",
    "docs/外交系统说明.md", "docs/外交开发推进复盘.md", "PLAN.md", "HANDOFF.md",
)


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def read(path):
    require(path.is_file() and path.stat().st_size < 16 * 1024 * 1024, "INPUT_MISSING_OR_LARGE:" + str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--fields", type=Path, required=True)
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), "DELIVERY_EXISTS")
    paths = {k: getattr(args, k).resolve() for k in ("queries", "fields", "family", "tests")}
    paths.update(build=RUNTIME / BUILD / "build-manifest.json", install=RUNTIME / BUILD / "installation.json")
    reports = {k: read(p) for k, p in paths.items()}
    for key in ("queries", "fields", "family", "tests"):
        require(reports[key].get("status") == "passed", "REPORT_NOT_PASSED:" + key)
    for key in ("queries", "fields", "family"):
        require(reports[key].get("checks") and all(v is True for v in reports[key]["checks"].values()), "CHECK_FAILED:" + key)
    build, install, queries = reports["build"], reports["install"], reports["queries"]
    require(len(build["sources"]) == 88, "SOURCE_COVERAGE_DIFFERS")
    require(build["dll_sha256"] == install["dll_sha256"] and install["installation_returncode"] == 0, "DLL_BINDING_FAILED")
    require(queries["session_id"] == install["session_id"], "QUERY_SESSION_DIFFERS")
    require(queries["business_submission"] is False, "UNEXPECTED_BUSINESS_SUBMISSION")
    require(reports["family"]["required_case_count"] == 19, "FAMILY_COVERAGE_DIFFERS")
    require(reports["tests"]["exit_code"] == 0, "REGRESSION_FAILED")
    required_names = {"release_PIC", "release_HAI", "release_LUX", "release_offer_selected", "release_PIC_money", "cede_FRA_88"}
    require(required_names <= {c["name"] for c in queries["cases"]}, "QUERY_COVERAGE_DIFFERS")
    source_paths = [ROOT / p for p in SOURCES]
    source_paths.extend(sorted((ROOT / "bridge/tests").glob("test_r69*wire*.py")))
    source_paths.extend(paths.values())
    source_paths.append(paths["tests"].parent / "pytest.log")
    # The build already hashed all 88 source inputs. Preserve its changed inputs
    # directly; Python-only corrections reuse the same installed DLL.
    for name in ("peace-justification-query.inc", "peace-overextension-query.inc", "peace-consequences-query.inc",
                 "declarewar-execution-preflight.inc", "alliance-execution.inc"):
        source_paths.append(RUNTIME / BUILD / name)
    source_paths.extend([
        RUNTIME / "r69-cb-contract-20261019-001/direction-correction.md",
        RUNTIME / "r69-release-oe-contract-20261019-001/report.json",
    ])
    for path in source_paths:
        require(path.is_file() and path.stat().st_size < 16 * 1024 * 1024, "INPUT_MISSING_OR_LARGE:" + str(path))
    output.mkdir()
    files = []
    for path in dict.fromkeys(source_paths):
        relative = path.relative_to(ROOT)
        destination = output / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        with destination.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"path": relative.as_posix(), "bytes": destination.stat().st_size, "sha256": digest})
    progress = {
        "stage": "R69", "status": "delivered", "goal_status": "active",
        "session_id": install["session_id"], "pid": install["pid"],
        "dll_sha256": build["dll_sha256"], "native_sources": 88,
        "query_cases": len(queries["cases"]), "checks": queries["checks"],
        "native_consequence_previews": sum(c["raw_consequences_valid"] for c in queries["cases"]),
        "unsupported_combinations": queries["unsupported_combinations"],
        "family_calls": reports["family"]["query_call_count"], "family_required": 19,
        "regression": reports["tests"], "business_submission": False,
        "new_save": False, "date_advance": False, "dedicated_save_reload": False,
        "source_save_reference": "r68-diplomat-delivery-20261019-001/manifest.json",
        "source_save_sha256": "ba85ef985d29dd1f4a8a4aa2263640af77d9c2784f979c6f84548d168bf2f091",
        "native_source_hashes_recomputed": False,
        "evidence": {k: p.relative_to(ROOT).as_posix() for k, p in paths.items()},
        "next": ["下一次相关DLL构建补国家条款与金币等旧条款混合查询执行", "获取人情及兑换信任、金币、人力", "赠送礼物与影响国家", "战争分及明细和战争目标累计分", "其余阶段、公平信息与常驻模型循环"],
        "delivery": (output / "manifest.json").relative_to(ROOT).as_posix(),
    }
    manifest = {"stage": "R69", "status": "delivered", "progress": progress,
                "files": files, "native_source_reference": build["sources"]}
    progress_path = RUNTIME / "r69-progress.json"
    require(not progress_path.exists(), "PROGRESS_EXISTS")
    for path, value in ((output / "manifest.json", manifest), (progress_path, progress)):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "delivered", "manifest": progress["delivery"], "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
