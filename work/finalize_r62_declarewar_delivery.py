"""集中交付 R62 宣战查询的 Python 生产、证据夹具和人类文档。

脚本只在 A 的离线校正、B 的实际批次和最终 Python 回归都通过后运行。
它不会复制存档、DLL 或大型运行日志；native 构建通过 B 的 immutable
build-manifest 引用。脚本可重复检查输入，但交付目录本身只允许创建一次，
避免覆盖已冻结的交付物。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work" / "runtime"
DELIVERY = RUNTIME / "r62-python-docs-delivery-20261019-001"

FINAL_PYTHON = "work/runtime/r62-final-python-unit-20261019-001/report.json"
A_BATCH = "work/runtime/r62-declarewar-details-query-batch-20261019-001/report.json"
A_RECONCILIATION = (
    "work/runtime/r62-declarewar-details-query-reconciliation-20261019-001/report.json"
)
B_BATCH = "work/runtime/r62-declarewar-details-query-batch-20261019-002/report.json"
B_BUILD = (
    "work/runtime/diplomacy-query-20261019-r62-declarewar-details-b"
    "/build-manifest.json"
)
B_INSTALLATION = (
    "work/runtime/diplomacy-query-20261019-r62-declarewar-details-b"
    "/installation.json"
)
TRADE_SCENE = "work/runtime/r62-trade-cb-scene-20261019-001/report.json"


def read_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError(f"JSON source exceeds 10 MiB: {relative}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_hash_cache: dict[Path, str] = {}


def sha256_small(path: Path) -> str:
    size = path.stat().st_size
    if size > 10 * 1024 * 1024:
        raise ValueError(f"delivery source exceeds 10 MiB: {path} ({size} bytes)")
    if path not in _hash_cache:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        _hash_cache[path] = digest.hexdigest()
    return _hash_cache[path]


def require_passed(relative: str) -> dict[str, Any]:
    report = read_json(relative)
    if report.get("status") != "passed":
        raise RuntimeError(f"required R62 evidence is not passed: {relative}")
    return report


def update_progress(
    final_python: dict[str, Any],
    a_batch: dict[str, Any],
    a_reconciliation: dict[str, Any],
    b_batch: dict[str, Any],
    b_build: dict[str, Any],
) -> dict[str, Any]:
    path = RUNTIME / "r62-progress.json"
    if path.exists():
        current = read_json("work/runtime/r62-progress.json")
    else:
        current = {}

    summary = a_reconciliation.get("summary", {})
    b_summary = b_batch.get("summary") or {
        "query_count": len(b_batch.get("cases", [])),
        "recipients": b_batch.get("recipients", []),
        "status": b_batch.get("status"),
    }
    current.update(
        {
            "stage": "R62",
            "status": "stage_completed_query_scope_goal_active",
            "goal_status": "active",
            "peace_actions_executed": 19,
            "peace_actions_total": 19,
            "declare_war_query_scope": "completed current details query batch; execution remains separate scope",
            "native": {
                **current.get("native", {}),
                "current_build_manifest": B_BUILD,
                "current_dll_sha256": b_build.get("dll_sha256"),
                "compiled_source_count": len(b_build.get("sources", [])),
            },
            "current_installation": {
                "installation": B_INSTALLATION,
                "role": "R62 B details-query batch; no save reload",
            },
            "query_evidence": {
                "a_raw_batch": A_BATCH,
                "a_offline_reconciliation": A_RECONCILIATION,
                "a_summary": summary,
                "b_actual_batch": B_BATCH,
                "b_summary": b_summary,
                "trade_cb_fixture": TRADE_SCENE,
            },
            "final_python_tests": {
                "report": FINAL_PYTHON,
                "status": final_python.get("status"),
                "passed_tests": final_python.get("passed_tests"),
                "passed_subtests": final_python.get("passed_subtests"),
            },
            "save_fixture": {
                "report": TRADE_SCENE,
                "purpose": "top-level FRA->ENG cb_trade_war_triggered query background",
                "loaded_for_query": False,
                "reload_validation": False,
            },
            "delivery": {
                "bundle": "work/runtime/r62-python-docs-delivery-20261019-001/manifest.json",
                "native_reference": B_BUILD,
                "native_dll_is_external": True,
            },
            "save_reload_validation": False,
            "per_step_global_memory_checks": False,
            "remaining_declare_war_scope": [
                "non-empty ally selection and promise-land parameters",
                "full war-goal legality and acceptance factors",
                "military/manpower and post-war consequences",
            ],
            "r62_history_preserved": True,
        }
    )
    write_json(path, current)
    return current


def replace_handoff(
    final_python: dict[str, Any],
    a_reconciliation: dict[str, Any],
    b_batch: dict[str, Any],
    b_build: dict[str, Any],
) -> None:
    path = ROOT / "HANDOFF.md"
    old = path.read_text(encoding="utf-8")
    r61 = old.index("## R61")
    existing_r62 = old.find("## R62")
    start = existing_r62 if existing_r62 != -1 and existing_r62 < r61 else r61
    passed_tests = final_python.get("passed_tests", "见最终报告")
    passed_subtests = final_python.get("passed_subtests", "见最终报告")
    summary = a_reconciliation.get("summary", {})
    b_status = b_batch.get("status")
    dll_sha = b_build.get("dll_sha256", "见 B build-manifest")
    current = f'''## R62：宣战理由与战争目标查询交付（2026-10-19）

R62 新增了宣战界面的只读查询结果。葡萄牙（POR）仍是界面玩家，法国（FRA）是桥接行动国；查询目标覆盖英格兰（ENG）、勃艮第（BUR）和摩洛哥（MOR）。公开结果提供 CB 名称与说明、战争目标名称与说明、禁用议和条件说明以及完整宣战描述；本批没有把查询背景当成宣战执行。

A 批次的原始事件通过离线校正保留为可审查证据：{summary.get('raw_native_verified_count', '见报告')} 个 raw native 查询验证了请求头、行动国、目标国、阶段、日期和前后状态，{summary.get('native_unavailable_unknown_count', '见报告')} 个摩洛哥查询继续保持 unknown。这里的 MOR unknown 来自桥接层 `alliance_query_country` 只检查前 256 个槽位；它不是游戏判定“摩洛哥不存在”，R63 将改为覆盖原生国家数据库范围。B 批次的 {len(b_batch.get('cases', []))} 个查询报告状态为 `{b_status}`，使用同一批量查询接口验证非空贸易 CB 背景下的 details 分支。宣战查询不改变战争、存档或日期。

R62 还准备了一个独立查询场景：新存档 `llm_diplomacy_declarewar_trade_query_20261019_r62.eu4` 在顶层 `diplomacy` 中增加 FRA→ENG、`cb_trade_war_triggered`、1455.8.20 至 1457.8.20 的一条 `casus_belli`。该存档只用于建立查询背景，没有加载或重载验收；详细字段、SHA 和流式完整性见[场景报告](work/runtime/r62-trade-cb-scene-20261019-001/report.json)。

当前 B 构建的 DLL SHA-256 为 `{dll_sha}`，不可变源码清单见[{B_BUILD}]({B_BUILD})。R62 最终 Python 回归报告为[{FINAL_PYTHON}]({FINAL_PYTHON})，通过 {passed_tests} 项测试和 {passed_subtests} 项子测试。交付包包含本批 Python 生产代码、R62 测试与夹具、查询/离线校正/场景脚本、人类文档、PLAN、复盘、矩阵和进度；存档与 DLL 保留在各自证据路径，不复制进交付包。

当前完整 goal 仍 active，常用议和实际执行保持 19/19。R62 还未完成非空盟友选择、许诺土地、完整正当性与接受因素、军力/人力和战后后果。后续工作沿当前 native 合同继续扩展这些查询，保持同一安装和场景批量执行；不因 Python 投影修复或查询背景准备新增专门重载。

R63 的下一步入口是[盟友选择合同报告](work/runtime/r63-ally-selection-contract-20261019-001/report.md)：其中已定位盟友选择使用的三个容器及因素路径，后续需要在原生数据库范围内补齐非空盟友和完整因素读取。

'''
    path.write_text(old[:start] + current + old[r61:], encoding="utf-8")


def delivery_sources() -> list[str]:
    return [
        # Python production and focused tests.
        "bridge/diplomacy.py",
        "bridge/native_text.py",
        "bridge/declarewar_details.py",
        "bridge/tests/test_declarewar_details.py",
        "bridge/tests/test_declarewar_details_r62_real.py",
        "bridge/tests/test_native_text.py",
        "bridge/tests/fixtures/declarewar_details_r62_real.json",
        # R62 operators and offline reconciliation.
        "work/run_declarewar_details_queries.py",
        "work/reconcile_declare_war_parameter_queries.py",
        "work/reconcile_declare_war_execution.py",
        "work/prepare_r62_trade_cb_scene.py",
        "work/finalize_r62_declarewar_delivery.py",
        # Human-facing references.
        "docs/history/R62宣战理由与战争目标说明.md",
        "docs/宣战接口与运行验收.md",
        "docs/外交能力矩阵.md",
        "docs/外交接口开发方案.md",
        "docs/外交系统说明.md",
        "docs/外交开发推进复盘.md",
        "PLAN.md",
        "HANDOFF.md",
        # Small machine-readable evidence kept with the delivery bundle.
        A_RECONCILIATION,
        A_BATCH,
        B_BATCH,
        TRADE_SCENE,
        "work/runtime/r62-trade-cb-scene-20261019-001/report.md",
        "work/runtime/r62-declarewar-scope-20261019-001/report.md",
        "work/runtime/r62-declarewar-warex-scale-20261019-001/report.json",
        "work/runtime/r62-declarewar-warex-scale-20261019-001/report.md",
        "work/runtime/r62-cb-definition-reference-20261019-001/report.json",
        "work/runtime/r62-cb-definition-reference-20261019-001/report.md",
        "work/runtime/r62-progress.json",
    ]


def build_delivery_manifest(b_build: dict[str, Any]) -> dict[str, Any]:
    if DELIVERY.exists():
        raise FileExistsError(f"delivery directory already exists: {DELIVERY}")
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
    manifest = {
        "status": "delivered",
        "stage": "R62",
        "constraints": {
            "dll_copied": False,
            "save_files_copied": False,
            "large_runtime_logs_copied": False,
            "save_sha_recomputed": False,
            "goal_status": "active",
        },
        "evidence": {
            "final_python": FINAL_PYTHON,
            "installation": B_INSTALLATION,
            "a_raw_batch": A_BATCH,
            "a_offline_reconciliation": A_RECONCILIATION,
            "b_actual_batch": B_BATCH,
            "trade_cb_fixture": TRADE_SCENE,
            "warex_scale": "work/runtime/r62-declarewar-warex-scale-20261019-001/report.json",
            "cb_definition_reference": "work/runtime/r62-cb-definition-reference-20261019-001/report.json",
        },
        "native_manifests": [
            {
                "copy": False,
                "path": B_BUILD,
                "dll_sha256": b_build.get("dll_sha256"),
                "game_sha256": b_build.get("game_sha256"),
                "source_count": len(b_build.get("sources", [])),
                "reason": "R62 delivery references immutable B native sources; DLL and native source tree remain external.",
            }
        ],
        "sources": records,
        "source_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "native_reference": {
            "build_manifest": B_BUILD,
            "dll_external": True,
        },
        "save_files_external": True,
        "large_runtime_logs_external": True,
    }
    write_json(DELIVERY / "manifest.json", manifest)
    return manifest


def main() -> int:
    # Validate all final evidence before changing HANDOFF/progress or creating
    # the delivery bundle. This keeps a partial delivery from looking complete.
    final_python = require_passed(FINAL_PYTHON)
    a_reconciliation = require_passed(A_RECONCILIATION)
    b_batch = require_passed(B_BATCH)
    trade_scene = require_passed(TRADE_SCENE)
    if not trade_scene.get("checks", {}).get("destination_target_exact", False):
        raise RuntimeError("trade CB fixture lacks exact destination target check")
    a_batch = read_json(A_BATCH)  # failed source is preserved as historical evidence
    b_build = read_json(B_BUILD)
    if not b_build.get("compiled"):
        raise RuntimeError("B build manifest is not compiled")
    if not (ROOT / B_INSTALLATION).is_file():
        raise FileNotFoundError(B_INSTALLATION)

    update_progress(final_python, a_batch, a_reconciliation, b_batch, b_build)
    replace_handoff(final_python, a_reconciliation, b_batch, b_build)

    # HANDOFF/progress are now included in the frozen source list.
    manifest = build_delivery_manifest(b_build)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "source_count": manifest["source_count"],
                "total_bytes": manifest["total_bytes"],
                "manifest": str(DELIVERY / "manifest.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
