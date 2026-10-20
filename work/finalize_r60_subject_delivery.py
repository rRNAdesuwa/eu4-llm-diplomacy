"""Write one R60 evidence index and one source/document delivery bundle."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
hashes = {}


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    if path not in hashes:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                h.update(chunk)
        hashes[path] = h.hexdigest()
    return hashes[path]


def main():
    batch_path = "work/runtime/r60-subject-execution-batch-20261019-001/report.json"
    save_path = "work/runtime/r60-subject-save-fields-20261019-001/report.json"
    tests_path = "work/runtime/r60-final-python-unit-20261019-002/report.json"
    b_path = "work/runtime/diplomacy-query-20261019-r60-subject-combined-b/build-manifest.json"
    c_path = "work/runtime/diplomacy-query-20261019-r60-subject-summary-c/build-manifest.json"
    batch, saved, tests, b, c = map(read, (batch_path, save_path, tests_path, b_path, c_path))
    assert batch["status"] == tests["status"] == "passed"
    assert saved["status"] == "passed"
    assert all(batch["business_attempts"][key]["poll"]["final"]["status"] == status
               for key, status in (("outbound", "rejected"), ("reject", "rejected"), ("accept", "accepted")))

    # The batch's bounded event slice grew during its three responses. Bind
    # fixture provenance to its final bytes, retaining the earlier capture hash.
    fixture_paths = [
        "bridge/tests/fixtures/peace_subject_execution_r60_real_query.json",
        "bridge/tests/fixtures/peace_subject_execution_r60_real_results.json"]
    for relative in fixture_paths:
        fixture = read(relative)
        source = fixture["source"]
        if "native_events_path" in source:
            path_key, hash_key = "native_events_path", "native_events_sha256"
        else:
            path_key, hash_key = "path", "sha256"
        actual = digest(ROOT / source[path_key])
        if source[hash_key] != actual:
            source["initial_capture_sha256"] = source[hash_key]
            source[hash_key] = actual
            source["source_finalized_after_batch"] = True
        if "report_path" in source:
            actual_report = digest(ROOT / source["report_path"])
            if source["report_sha256"] != actual_report:
                source["initial_report_capture_sha256"] = source["report_sha256"]
                source["report_sha256"] = actual_report
        write(ROOT / relative, fixture)

    handoff = ROOT / "HANDOFF.md"
    old = handoff.read_text(encoding="utf-8")
    start, end = old.index("## R60"), old.index("## R59")
    current = f'''## R60：两项附属条款完成组合执行与集中保存（2026-10-19）

`release_subject`、`transfer_subject`已接入统一list/inspect/execute/result，与1金币和战争赔款合成一份和约。一个进程完成英国原生AI拒绝、法国明确拒绝和法国明确接受；接受解除ENG→TYR、ENG→LEI，新增FRA→LEI的vassal关系，支付金币、建立十年赔款并结束战争。实际议和执行覆盖 **14/19**；完整goal仍active。人类用法、具体国家角色、金币分配和问题修正见[R60说明](docs/history/R60释放与转移附属国的组合议和.md)。

当前运行仍为B：PID{batch['pid']}，session `{batch['session_id']}`，DLL SHA `{b['dll_sha256']}`，POR玩家暂停于1455.6.18/raw56549832。正确场景002 `r60b.eu4`已实际载入；001的advisor同名TAG范围错误保留为失败证据，从未载入。一次安装、同进程批量执行；等待外交官冷却直接采用原生提示的1455.6.18，正常推进32日。最后集中保存一次，无专门重载验收，也无逐步整机RAM检查。

[实际批次]({batch_path})passed，[独立关系终态](work/runtime/r60-subject-execution-batch-20261019-001/report-evidence/after-effects.json)与[保存字段16/16]({save_path})一致。最终保存 `llm_diplomacy_peace_subject_combined_accepted_20261019_r60.eu4` SHA `c110e8d9b824472a5aa777b3bd164ab479fefa9b4a27ed7b7b3ea435d99d3ea6`；赔款1455.6.18至1465.6.18。历史war块仍序列化存在，但双方当前参战关系已结束；不要以war块消失作为结束条件。三份轮转自动保存已恢复。

本批修复：2048字节参数缓冲和动态结果缓冲；subject从旧rule_term_count中独立校验；journal恢复动作名单和第二层receipt投影补两族CSV。原outbound的两个遗漏字段由原生回执严格核对后补回，修正前sqlite与更正记录保留，没有重放业务。B原生subject总标志初始化错误使单项effects全true而terms_verified=false；公开层对全部关系前后值、金币和赔款严格重算为true，同时保留native_terms_verified=false、来源validated_native_effects。C已修原生初始化并完整-Werror编译，SHA `{c['dll_sha256']}`，74源；[C构建]({c_path})仅供下一批安装，当前B不热替换、不重复注入。

真实query及三种结果已加入fixture；最终[Python回归]({tests_path})通过{tests['passed_tests']}项测试、{tests['passed_subtests']}项子测试。首次全套的旧11条款目录断言失败保留；当前非白条款合同13类。源码和文档集中交付见[本批bundle](work/runtime/r60-python-docs-delivery-20261019-001/manifest.json)，阶段索引见[r60-progress.json](work/runtime/r60-progress.json)。流程复盘见§48。

下一批继续完全吞并、释放国家、强迫附庸、共主邦联、承认独立，按已证实原生家族批量接线。全吞并已有R59 `982050/982170/9765a0`全部失地与结算证据；ReleaseNation候选可能由97d350创建；GrantIndependence语义仍需确认。常用外交其余阶段、公平信息、常驻模型和长期循环等原始目标继续保留。新DLL如需安装使用新进程；Python及checker修复复用原事件，集中保存字段核对，不新增专门重载。

'''
    handoff.write_text(old[:start] + current + old[end:], encoding="utf-8")

    progress = {
        "stage": "R60", "status": "stage_completed_full_goal_active",
        "goal_status": "active", "peace_actions_executed": 14, "peace_actions_total": 19,
        "runtime_build": b_path, "compiled_next_build": c_path,
        "compiled_next_build_installed": False,
        "session_id": batch["session_id"], "pid": batch["pid"],
        "batch": batch_path, "save_fields": save_path, "final_python_tests": tests_path,
        "save_reload_validation": False, "per_step_global_memory_checks": False,
        "new_actions": ["release_subject", "transfer_subject"],
        "combined_terms": batch["clause_actions"],
        "native_acceptance_summary_flag": False,
        "public_terms_verification": "strict_validation_of_original_native_effects",
        "runtime_failure_records_preserved": True,
        "remaining_peace_actions": ["full_annexation", "release_nation", "force_vassalization",
                                    "form_personal_union", "grant_independence"],
        "other_original_goal_scope_retained": True,
        "tool_sessions": "root sessions terminal; completed agent handoffs have no active sessions"}
    write(RUNTIME / "r60-progress.json", progress)

    source_files = [
        "bridge/diplomacy.py", "bridge/peace_execution.py", "bridge/diplomacy_catalog.py",
        "bridge/tests/test_peace_subject_execution_r60.py",
        "bridge/tests/test_peace_annul_treaties.py", "bridge/tests/test_peace_concede_defeat.py",
        "bridge/tests/test_peace_core_query.py", "bridge/tests/test_peace_reparations.py",
        "bridge/tests/test_peace_special_terms.py", "bridge/tests/test_peace_trade_power.py",
        *fixture_paths, "work/run_peace_subject_execution_batch.py",
        "work/probe_peace_effect_state.py", "work/run_peace_subject_query_stage.py",
        "work/inspect_peace_subject_save.py", "work/compare_r60_subject_save.py",
        "work/repair_r60_subject_receipt.py", "work/finalize_r60_subject_delivery.py",
        "work/native/test-peace-effect-summary.cpp", "work/native/test-peace-subject-effects.cpp",
        "docs/history/R60释放与转移附属国的组合议和.md", "docs/外交能力矩阵.md",
        "docs/外交接口开发方案.md", "docs/外交系统说明.md", "docs/外交开发推进复盘.md",
        "HANDOFF.md", "work/runtime/r60-progress.json", b_path, c_path]
    out = RUNTIME / "r60-python-docs-delivery-20261019-001"
    out.mkdir(exist_ok=False)
    records = []
    for relative in source_files:
        source = ROOT / relative
        assert source.is_file(), relative
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append({"path": relative, "bytes": source.stat().st_size,
                        "sha256": digest(source)})
    manifest = {"status": "delivered", "sources": records,
                "source_count": len(records), "total_bytes": sum(x["bytes"] for x in records),
                "native_source_archive": {"runtime_b": b_path, "compiled_c": c_path},
                "runtime_b_source_changes_in_c": ["peace-effect-state.inc"]}
    write(out / "manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("status", "source_count", "total_bytes")}))


if __name__ == "__main__":
    main()
