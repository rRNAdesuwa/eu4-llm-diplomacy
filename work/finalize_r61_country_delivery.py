"""Prepare the R61 country-term delivery bundle and final handoff section.

The script intentionally stops before delivery if the final Python report has
not passed.  It copies source, test, fixture, script, and documentation files
only; save files, DLLs, and native source trees remain external evidence.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work" / "runtime"
DELIVERY = RUNTIME / "r61-python-docs-delivery-20261019-001"

FINAL_PYTHON = "work/runtime/r61-final-python-unit-20261019-002/report.json"
F_BUILD = "work/runtime/diplomacy-query-20261019-r61-country-f/build-manifest.json"
G_INSTALLATION = (
    "work/runtime/diplomacy-query-20261019-r61-country-independence-g/installation.json"
)


def read_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_small(path: Path) -> str:
    size = path.stat().st_size
    if size > 10 * 1024 * 1024:
        raise ValueError(f"delivery source exceeds 10 MiB: {path} ({size} bytes)")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_passed(relative: str) -> dict[str, Any]:
    report = read_json(relative)
    if report.get("status") != "passed":
        raise RuntimeError(f"required evidence is not passed: {relative}")
    return report


def update_progress(final_python: dict[str, Any], f_build: dict[str, Any]) -> dict[str, Any]:
    path = RUNTIME / "r61-progress.json"
    current = read_json("work/runtime/r61-progress.json")
    current.update(
        {
            "status": "stage_completed_full_goal_active",
            "goal_status": "active",
            "actual_peace_execution_coverage": "19/19",
            "save_reload_validation": False,
            "native": {
                **current.get("native", {}),
                "protocol": "QUERY18/EXEC10",
                "country_term_count": 5,
                "compiled_sources": len(f_build.get("sources", [])),
                "current_build": F_BUILD,
                "current_dll_sha256": f_build.get("dll_sha256"),
                "source_changes_pending_build": None,
            },
            "final_python_tests": {
                "report": FINAL_PYTHON,
                "status": final_python.get("status"),
                "passed_tests": final_python.get("passed_tests"),
                "passed_subtests": final_python.get("passed_subtests"),
            },
            "current_installation": {
                "installation": G_INSTALLATION,
                "pid": 24932,
                "session_id": "24932-1dd5f9a1d0d2063",
                "dll_sha256": f_build.get("dll_sha256"),
                "role": "G final runtime; POR player, paused",
            },
            "r61_delivery": {
                "execution_coverage": "19/19",
                "save_field_reports": [
                    "work/runtime/r61-country-combined-save-fields-20261019-001/report.json",
                    "work/runtime/r61-country-vassal-save-fields-20261019-001/report.json",
                    "work/runtime/r61-country-union-save-fields-20261019-001/report.json",
                    "work/runtime/r61-country-independence-save-fields-20261019-001/report.json",
                ],
                "independence_declaration_fields": "work/runtime/r61-native-independence-declaration-fields-20261019-001/report.json",
                "grant_report": "work/runtime/r61-country-independence-execution-20261019-004/report.json",
                "delivery_bundle": "work/runtime/r61-python-docs-delivery-20261019-001/manifest.json",
                "native_reference": F_BUILD,
                "old_grant_unknown_report_preserved": "work/runtime/r61-country-independence-execution-20261019-003/report.json",
                "no_business_replay": True,
            },
            "r62_scope_retained": True,
        }
    )
    write_json(path, current)
    return current


def replace_handoff(final_python: dict[str, Any], f_build: dict[str, Any]) -> None:
    path = ROOT / "HANDOFF.md"
    old = path.read_text(encoding="utf-8")
    start = old.index("## R61")
    end = old.index("## R60", start)
    dll_sha = f_build["dll_sha256"]
    passed_tests = final_python.get("passed_tests", "记录于最终报告")
    passed_subtests = final_python.get("passed_subtests", "记录于最终报告")
    current = f'''## R61：五项国家议和条款与独立宣战完成（2026-10-19）

R61 已完成五项国家级议和条款的统一查询、执行和结果读取，常用议和实际执行覆盖 **19/19**；完整 goal 仍保持 active。组合条款、强迫附庸、共主邦联和承认独立均有真实拒绝/接受结果。Grant004 通过，且独立宣战保存字段核对确认了新的 FRA→ENG 战争结构。

本批角色和后果如下：英国（ENG）是提议或被提议的一方，法国（FRA）是主要受控决策国；释放国家场景由英国释放 FLY，完全吞并场景由法国取得 TYR 的全部省份；强迫附庸和共主邦联场景由法国接收 LEI；承认独立场景由法国脱离英国宗主关系。组合和约、vassal、personal union、Grant Independence 的结果报告均为 `passed`，四组保存字段报告各通过 5/5 检查，独立宣战保存字段报告通过 8/8 检查。

当前 G 进程为 PID `24932`、session `24932-1dd5f9a1d0d2063`，安装记录为[{G_INSTALLATION}](work/runtime/diplomacy-query-20261019-r61-country-independence-g/installation.json)。POR 是界面玩家，游戏保持暂停；本批使用 F 构建的 DLL，SHA-256 为 `{dll_sha}`，包含 78 份 native 源码。原生源码不在本交付包内，F 构建清单作为不可变来源引用：[{F_BUILD}](work/runtime/diplomacy-query-20261019-r61-country-f/build-manifest.json)。

实际证据入口：组合执行报告为[combined](work/runtime/r61-country-combined-execution-d-20261019-001/report.json)，强迫附庸为[vassal](work/runtime/r61-country-vassal-execution-20261019-001/report.json)，共主邦联为[union](work/runtime/r61-country-union-execution-20261019-001/report.json)，Grant004 为[grant](work/runtime/r61-country-independence-execution-20261019-004/report.json)。四份保存字段报告位于 `r61-country-combined-save-fields-20261019-001`、`r61-country-vassal-save-fields-20261019-001`、`r61-country-union-save-fields-20261019-001` 和 `r61-country-independence-save-fields-20261019-001`。独立宣战的 8/8 字段核对见[r61-native-independence-declaration-fields-20261019-001](work/runtime/r61-native-independence-declaration-fields-20261019-001/report.json)：after 只选中 FRA 攻击 ENG 的当前战争，外层目标为 `defend_capital`，内部类型为 `defend_capital_independence`，CB 为 `cb_independence_war`，active_war 直接层为 `subject_type=vassal`；旧已结束战争未混入当前结果，ENG→FRA dependency 从 1 条变为 0 条。

Grant003 的法国接受结果保留为失败证据：该实验结束了战争并移除 pending，但 ENG→FRA vassal 仍保留，因此公开结果为 unknown，未重放。Grant004 使用真实独立宣战场景通过了最终语义检查。历史 001/002/003 场景、原始事件和离线纠正均保留，便于区分场景构造错误、消费者修复和真实原生结果。

最终 Python 回归报告为[{FINAL_PYTHON}]({FINAL_PYTHON})，通过 {passed_tests} 项测试和 {passed_subtests} 项子测试。交付清单为[r61-python-docs-delivery-20261019-001](work/runtime/r61-python-docs-delivery-20261019-001/manifest.json)，其中包含本批 Python 生产代码、R61 fixtures/tests、场景/运行/比较脚本、R61 人类说明、复盘、PLAN 与 HANDOFF；save、DLL 和大型运行日志继续由各自 evidence 路径保存。

继续范围属于 R62 及完整 goal：宣战候选与盟友选择、更多国家条款组合、议和费用与接受因素、战后信息、公平信息、常驻模型和长期循环仍按后续批次推进。用户确定的批量流程继续有效：同一安装和场景复用进程，兼容条款集中执行并集中核对保存字段；只在安装新 DLL 时使用新进程，不为 Python 投影修复或本批已完成的保存字段核对另开专门重载进程。

'''
    path.write_text(old[:start] + current + old[end:], encoding="utf-8")


def delivery_sources() -> list[str]:
    return [
        # Python production used by the R61 query/execution path.
        "bridge/diplomacy.py",
        "bridge/diplomacy_catalog.py",
        "bridge/diplomacy_session.py",
        "bridge/peace_execution.py",
        "bridge/peace_core.py",
        "bridge/peace_costs.py",
        "bridge/peace_country.py",
        # R61 real fixtures and focused/real tests.
        "bridge/tests/test_peace_country_r61.py",
        "bridge/tests/test_peace_country_effects_r61.py",
        "bridge/tests/test_peace_country_r61_real.py",
        "bridge/tests/test_peace_country_r61_relations_real.py",
        "bridge/tests/test_peace_country_r61_c003_real.py",
        "bridge/tests/test_peace_country_r61_combined_response_real.py",
        "bridge/tests/test_peace_country_r61_combined_rejected_real.py",
        "bridge/tests/test_peace_country_r61_inbound_full_annex_real.py",
        "bridge/tests/test_peace_execution_parameters.py",
        "bridge/tests/test_peace_inbound_tools.py",
        "bridge/tests/test_peace_outbound_runner_contract.py",
        "bridge/tests/fixtures/declare_war_r61_no_province_cb_real.json",
        "bridge/tests/fixtures/peace_country_r61_real.json",
        "bridge/tests/fixtures/peace_country_r61_relations_real.json",
        "bridge/tests/fixtures/peace_country_r61_c003_real.json",
        "bridge/tests/fixtures/peace_country_r61_combined_response_real.json",
        "bridge/tests/fixtures/peace_country_r61_combined_rejected_real.json",
        "bridge/tests/fixtures/peace_country_r61_inbound_full_annex_real.json",
        # R61 scenario, operator, and bounded save comparison scripts.
        "work/check_peace_parameters_r61.py",
        "work/compare_r61_country_save.py",
        "work/inspect_peace_subject_save.py",
        "work/inspect_r61_independence_declaration.py",
        "work/prepare_r61_country_scenes.py",
        "work/prepare_r61_independence_scene.py",
        "work/prepare_r61_independence_declaration_scene.py",
        "work/probe_r61_independence_war.py",
        "work/reconcile_r61_country_outbound.py",
        "work/run_peace_country_queries.py",
        "work/run_peace_country_execution_batch.py",
        "work/finalize_r61_country_delivery.py",
        # Human-facing state and project scope.
        "docs/history/R61五项国家议和条款的参数与查询.md",
        "docs/外交开发推进复盘.md",
        "PLAN.md",
        "HANDOFF.md",
        "work/runtime/r61-progress.json",
    ]


def make_bundle(final_python: dict[str, Any], f_build: dict[str, Any]) -> dict[str, Any]:
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to overwrite delivery bundle: {DELIVERY}")
    DELIVERY.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for relative in delivery_sources():
        source = ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(relative)
        destination = DELIVERY / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append(
            {
                "path": relative,
                "bytes": source.stat().st_size,
                "sha256": sha256_small(source),
            }
        )

    evidence = {
        "query_batch": "work/runtime/r61-country-query-batch-20261019-003/report.json",
        "executions": [
            "work/runtime/r61-country-combined-execution-d-20261019-001/report.json",
            "work/runtime/r61-country-vassal-execution-20261019-001/report.json",
            "work/runtime/r61-country-union-execution-20261019-001/report.json",
            "work/runtime/r61-country-independence-execution-20261019-004/report.json",
        ],
        "save_fields": [
            "work/runtime/r61-country-combined-save-fields-20261019-001/report.json",
            "work/runtime/r61-country-vassal-save-fields-20261019-001/report.json",
            "work/runtime/r61-country-union-save-fields-20261019-001/report.json",
            "work/runtime/r61-country-independence-save-fields-20261019-001/report.json",
        ],
        "independence_declaration": "work/runtime/r61-native-independence-declaration-fields-20261019-001/report.json",
        "final_python": FINAL_PYTHON,
        "installation": G_INSTALLATION,
    }
    manifest = {
        "status": "delivered",
        "stage": "R61",
        "source_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "sources": records,
        "evidence": evidence,
        "native_manifests": [
            {
                "path": F_BUILD,
                "copy": False,
                "dll_sha256": f_build.get("dll_sha256"),
                "game_sha256": f_build.get("game_sha256"),
                "source_count": len(f_build.get("sources", [])),
                "reason": "R61 delivery references the immutable F 78-source build; native sources are not copied here.",
            }
        ],
        "constraints": {
            "save_files_copied": False,
            "dll_copied": False,
            "large_runtime_logs_copied": False,
            "save_sha_recomputed": False,
            "goal_status": "active",
            "r62_scope_retained": True,
        },
    }
    write_json(DELIVERY / "manifest.json", manifest)
    return manifest


def main() -> None:
    final_python = assert_passed(FINAL_PYTHON)
    f_build = read_json(F_BUILD)
    if f_build.get("dll_sha256") != "313a386af8b949eaea0243c910757bf9dbe1a4bfbb099e8c4138637225153f88":
        raise RuntimeError("unexpected F build DLL SHA")
    for relative in (
        "work/runtime/r61-country-combined-execution-d-20261019-001/report.json",
        "work/runtime/r61-country-vassal-execution-20261019-001/report.json",
        "work/runtime/r61-country-union-execution-20261019-001/report.json",
        "work/runtime/r61-country-independence-execution-20261019-004/report.json",
        "work/runtime/r61-country-combined-save-fields-20261019-001/report.json",
        "work/runtime/r61-country-vassal-save-fields-20261019-001/report.json",
        "work/runtime/r61-country-union-save-fields-20261019-001/report.json",
        "work/runtime/r61-country-independence-save-fields-20261019-001/report.json",
        "work/runtime/r61-native-independence-declaration-fields-20261019-001/report.json",
    ):
        assert_passed(relative)
    replace_handoff(final_python, f_build)
    progress = update_progress(final_python, f_build)
    manifest = make_bundle(final_python, f_build)
    print(json.dumps({
        "status": manifest["status"],
        "source_count": manifest["source_count"],
        "total_bytes": manifest["total_bytes"],
        "delivery": str(DELIVERY / "manifest.json"),
        "progress": str(RUNTIME / "r61-progress.json"),
        "handoff": str(ROOT / "HANDOFF.md"),
        "execution_coverage": progress["actual_peace_execution_coverage"],
        "final_python": FINAL_PYTHON,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
