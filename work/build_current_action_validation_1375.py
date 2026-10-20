"""Project the frozen 120-action audit plus four independently verified effects."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import GAME_SHA, decode, digest, read, require
from work.validate_current_diplomacy_1375 import committed_peak

OUT = ROOT/"work/reports/unified-validation-20261013"


def projection(sample):
    p = sample["passes"][0]
    return {"date": p["roots"]["date"], "player": p["roots"]["current_player"],
        "countries": {tag: {"slot": c["slot"], "handle": c["handle"]} for tag, c in p["countries"].items()},
        "pairs": [{"action": item["action"], "actor": item["actor_tag"], "target": item["target_tag"],
            "trust": item["target_to_actor"]["trust_raw_byte"], "favors_milli": item["target_to_actor"]["favors_raw_milli"],
            "dependency_type": item["dependency"]["object"]["type_name"]["name"] if item["dependency"]["object"] else None,
            "dependency_actor_to_target": item["dependency"]["object"]["actor_to_target"] if item["dependency"]["object"] else None,
            "actor_overlord": item["dependency"]["actor_overlord_handle"],
            "target_overlord": item["dependency"]["target_overlord_handle"]} for item in p["pairs"]]}


def build():
    pins = {}
    def pin(path):
        path = (ROOT/path).resolve()
        raw = read(path, 8*1024*1024)
        pins[path.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
        return raw
    def doc(path):
        return decode(pin(path))
    original = doc(OUT/"action-validation.json")
    selected = doc(OUT/"corrective-effect-evidence.json")
    reload = doc(OUT/"cold-reload-verification.json")
    after = doc(OUT/"prerequisites-after-submit.json")
    cold = doc(OUT/"prerequisites-cold-reload.json")
    require(original["schema"] == "EU4TAG31-UNIFIED-FILE-VALIDATION/1" and original["current_binding_count"] == 120
            and original["game_sha256"] == selected["game_sha256"] == cold["game_sha256"] == GAME_SHA,
            "Wrong frozen action/effect scope")
    require(selected["selected_live_effects_observed"] == selected["selected_serialized_effects_observed"] == 4
            and selected["cold_reload_verified"] is False and selected["normal_native_call_pairs"] == 28,
            "Original selected-effect evidence changed")
    for name, sha in reload["source_pins"].items():
        require(digest(pin(OUT/name)) == sha, "Cold-reload source changed: " + name)
    require(reload["cold_reload_verified"] is True and reload["selected_effects_persisted"] is True
            and reload["commands_resent"] == reload["runtime_native_calls_in_reload"] == 0
            and reload["new_process_without_research_dll"] is True,
            "Cold reload did not prove selected persistence without redispatch")
    require(cold["two_pass_equal"] is True and len(cold["passes"]) == 2
            and cold["passes"][0] == cold["passes"][1] and cold["research_modules"] == []
            and cold["native_calls"] == cold["requests_published"] == 0
            and cold["passes"][0]["roots"]["manual_pause"] == 1
            and (cold["pid"], cold["creation"]) != (after["pid"], after["creation"]),
            "Cold-reload sample is not a distinct paused read-only process")
    require(projection(after) == projection(cold) == reload["projection_before"] == reload["projection_after"],
            "Independent selected-state projection does not match")
    effects = {row["command"]["action"]: row for row in selected["actions"]}
    require(len(effects) == 4, "Duplicate corrective action")
    rows = []
    for old in original["actions"]:
        action = old["action"]
        latest = effects.get(action)
        if latest:
            require(old["policy_group"] == "clean_rejection_repair_candidate"
                    and latest["command"]["request_id"] != old["previous_command"]["request_id"]
                    and latest["native_dispatch_verified"] is True and latest["selected_live_effect_observed"] is True
                    and latest["selected_serialized_effect_observed"] is True,
                    "Corrective effect is not a new clean-rejection attempt")
        group = "this_run_selected_effect_and_reload_verified" if latest else old["policy_group"]
        rows.append({"action": action, "binding": old["binding"],
            "original_batch": {k: old[k] for k in ("previous_command", "old_state", "old_reason", "old_identity",
                "old_sequence", "audit_sha256", "policy_group", "historical_selected_state_success",
                "this_batch_individual_AI_acceptance_verified", "this_batch_individual_effect_verified")},
            "current_validation_group": group,
            "this_run_tested": bool(latest), "this_run_selected_effect_verified": bool(latest),
            "this_run_cold_reload_verified": bool(latest),
            "corrective_attempt": latest, "historical_success_evidence": old["historical_success_evidence"],
            "remaining_condition_repair_candidate_not_tested": group == "clean_rejection_repair_candidate",
            "development_retry_forbidden": group != "clean_rejection_repair_candidate",
            "original_request_id_may_be_reused": False,
            "validation_scope": "Configured test Mod/save and selected fields; no general legal-pair or delayed lifecycle claim."})
    groups = dict(Counter(row["current_validation_group"] for row in rows))
    require(groups == {"historical_success_no_retry": 35, "dispatched_no_retry": 25,
                       "clean_rejection_repair_candidate": 53, "sparse_rejection_blocked": 2,
                       "unknown_no_retry": 1, "this_run_selected_effect_and_reload_verified": 4},
            "Current action groups differ from the frozen matrix plus four new effects")
    first_exit = doc(OUT/"exit-before-reload.json")
    second_exit = doc(OUT/"exit-after-reload.json")
    require(first_exit["exit_observed"] is True and first_exit["exit_code"] == 0
            and second_exit["exit_observed"] is False and second_exit["wait_status"] == 258,
            "Exit observation receipts changed")
    pin("work/build_current_action_validation_1375.py")
    pin("work/validate_current_diplomacy_1375.py")
    for name, expected in pins.items():
        require({"bytes": len(raw := read(ROOT/name, 8*1024*1024)), "sha256": digest(raw)} == expected,
                "Projection input changed during read")
    return {"schema": "EU4TAG31-CURRENT-ACTION-VALIDATION/1", "file_only": True, "game_sha256": GAME_SHA,
        "game_calls_by_this_tool": 0, "game_state_reads_by_this_tool": 0, "requests_published_by_this_tool": 0,
        "current_binding_count": 120, "lookup_excluded_count": 27, "current_validation_groups": groups,
        "this_run_new_distinct_actions_tested": 4, "this_run_selected_effect_and_cold_reload_passed": 4,
        "remaining_repair_candidates_not_tested": 53, "original_batch_states_unchanged": original["historical_original_states"],
        "historical_success_ledger_count_unchanged": 38, "historical_successes_in_current_bindings_unchanged": 35,
        "current_bound_actions_with_historical_or_this_run_selected_effect_evidence": 39,
        "original_matrix_file_preserved": "work/reports/unified-validation-20261013/action-validation.json",
        "original_corrective_effect_evidence_cold_flag_preserved": False,
        "new_cold_reload_evidence": "work/reports/unified-validation-20261013/cold-reload-verification.json",
        "cold_reload_process": {"pid": cold["pid"], "creation": cold["creation"], "without_research_dll": True,
                                "same_selected_effect_state": True, "read_only_native_calls": 0},
        "exit_observations": {"first_process": {"pid": first_exit["pid"], "exit_observed": True, "exit_code": 0},
            "reload_process": {"pid": second_exit["pid"], "exit_observed": False, "observer_timed_out": True,
                               "exit_code_zero_not_proven": True}},
        "current_process_absence_verified_by_this_tool": False,
        "limitations": ["This run exercised four repaired clean-rejection actions, not all 120 a second time.",
            "The other 53 repair candidates remain untested; original dispatched/unknown/historical-success groups remain blocked.",
            "Selected cold-reload persistence does not verify every effect, delayed lifecycle, or unmodified-game legality.",
            "The second process exit observer timed out; no exit-code-zero claim is made for it.",
            "All frozen input reports and policy/bridge registrations remain unchanged."],
        "peak_committed_bytes": committed_peak(), "source_pins": dict(sorted(pins.items())), "actions": rows}


def markdown(d):
    lines = ["# 当前外交行动验证状态", "", "当前 120 绑定均已纳入统一文件审计；本轮仅对其中 4 个干净拒绝修复候选进行了新 ID 实机定向补测。", "",
        "4 项所选实时效果、保存结果和新进程冷重载持久性全部通过：人情换信任、设卫戍国、释放索尤尔加尔、解除贸易保护国。其余 53 个修复候选未实测。", "",
        "| 当前分组 | 数量 |", "|---|---:|", "| 本轮所选效果和冷重载通过 | 4 |", "| 仍待修复条件/未实测候选 | 53 |",
        "| 历史成功禁测 | 35 |", "| 其他原派发禁测 | 25 |", "| 稀疏拒绝阻断 | 2 |", "| 其他未知禁测 | 1 |", "",
        "旧唯一批次41派发/77拒绝/2未知及历史38成功台账保持原义；新增4项证据单独关联，不改旧矩阵或旧效果报告的 cold=false。", "",
        "冷重载进程69532的双遍暂停样本无研究DLL，四项投影与派发后样本一致。第一进程退出码0已观察；第二进程退出observer超时，未证明退出码0。", "",
        "| 行动 | 类别 | 本轮实测/冷重载 | 当前分组 |", "|---|---|---|---|"]
    labels = {"this_run_selected_effect_and_reload_verified": "本轮选定效果+冷重载通过", "clean_rejection_repair_candidate": "53候选之一，未实测",
              "historical_success_no_retry": "历史成功禁测", "dispatched_no_retry": "原派发禁测", "sparse_rejection_blocked": "稀疏拒绝阻断", "unknown_no_retry": "未知禁测"}
    for row in d["actions"]:
        lines.append(f"| `{row['action']}` | {row['binding']['category']} | {'通过' if row['this_run_cold_reload_verified'] else '本轮未测'} | {labels[row['current_validation_group']]} |")
    return "\n".join(lines+["", "完整逐项原始状态、4项新增证据及来源pin见 current-action-validation.json。", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    text = markdown(data).encode("utf-8")
    if args.check:
        old = decode(read(OUT/"current-action-validation.json", 2*1024*1024))
        old.pop("peak_committed_bytes")
        deterministic = dict(data)
        deterministic.pop("peak_committed_bytes")
        require(old == deterministic and read(OUT/"current-action-validation.md", 256*1024) == text,
                "Current action validation is stale")
    else:
        (OUT/"current-action-validation.json").write_text(json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2)+"\n", encoding="utf-8")
        (OUT/"current-action-validation.md").write_bytes(text)
    print(json.dumps({"groups": data["current_validation_groups"], "source_pins": len(data["source_pins"]),
                      "peak_committed_bytes": data["peak_committed_bytes"], "check": args.check}))


if __name__ == "__main__":
    main()
