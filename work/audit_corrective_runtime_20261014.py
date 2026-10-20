"""Independent bounded file audit of six favor/march corrective requests.

No live process, runtime adapter, request publication, reservation mutation,
save parsing, or cold reload is performed by this tool.
"""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_audit import recorded_snapshot
from bridge.tag_command_backend import GAME_SHA, decode, digest, read, require, write_new
from bridge.tag_test_policy import clean_rejection, DevelopmentTestHistory
from work.validate_current_diplomacy_1375 import committed_peak

OUT = ROOT/"work/reports/diplomacy-corrective-20261014"


def build():
    pins = {}
    def pin(path, maximum=8*1024*1024):
        path = (ROOT/path).resolve()
        key = path.relative_to(ROOT).as_posix()
        raw = read(path, maximum)
        expected = {"bytes": len(raw), "sha256": digest(raw)}
        require(key not in pins or pins[key] == expected, "Input changed between reads")
        pins[key] = expected
        require(committed_peak() < 768*1024*1024, "Runtime file audit exceeded 768 MiB")
        return raw
    def doc(path):
        return decode(pin(path))
    load, commands, publication, results, before, after = [doc(OUT/(name+".json")) for name in
        ("load", "commands", "publication", "results", "final-before", "after")]
    identity = load["identity"]
    require(identity == publication["identity"] == results["identity"]
            and publication["reused"] is False and len(commands) == 6,
            "Load/publication/result identity or scope mismatch")
    require(publication["published"] == [{**command, "sequence": i+1} for i, command in enumerate(commands)],
            "Publication differs from the six explicit commands")
    require(results["native_call_begins"] == 39 and results["native_results"] == 6
            and results["native_exceptions"] == [] and results["partial_audit_tail"] is False,
            "Incomplete or exceptional audit summary")
    for observation in (before, after):
        require(observation["game_sha256"] == GAME_SHA and observation["schema"] == "EU4TAG-FAVOR-MARCH-RPM/1"
                and observation["two_pass_equal"] is True and len(observation["passes"]) == 2
                and observation["passes"][0] == observation["passes"][1]
                and observation["native_calls"] == observation["requests_published"] == 0
                and observation["memory_written"] is False
                and (observation["pid"], observation["creation"]) == (identity["pid"], identity["creation"]),
                "Selected observer identity/two-pass/read-only proof mismatch")
        for path, sha in observation["source_pins"].items():
            require(digest(pin(path)) == sha, "Observer source changed: " + path)
    left, right = before["passes"][0], after["passes"][0]
    require(all(left["roots"][key] == right["roots"][key] for key in ("date", "current_player", "manual_pause"))
            and left["roots"]["manual_pause"] == 1, "Before/after date/player/pause differs")
    manifest_path = ROOT/"bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json"
    manifest = doc(manifest_path)
    pin(manifest_path.parent/manifest["DLL"])
    snapshot = recorded_snapshot(manifest_path, identity)
    require(snapshot.raw == snapshot.complete and snapshot.summary["audit_sha256"] == results["audit_sha256"],
            "Raw native audit differs from recorded results")
    pin(snapshot.directory/"events.jsonl")
    history = DevelopmentTestHistory(ROOT/"work/runtime/tag-command-development-history-1375")
    all_records = history._records()  # Read only; no acquire/check/reserve call.
    reservations = [r for r in all_records if r["identity"] == identity]
    require(len(reservations) == 6 and not (history.directory/"test-policy.lock").exists(),
            "Expected six completed development reservations")
    previous = doc("work/reports/unified-validation-20261013/current-action-validation.json")
    overlay = doc("work/reports/diplomacy-corrective-20261013-r2/cross-version-no-repeat-audit.json")
    remaining = {row["action"] for row in previous["actions"] if row["remaining_condition_repair_candidate_not_tested"]}
    excluded = set(overlay["blocked_actions"])
    require(len(remaining) == 53 and len(remaining-excluded) == 51
            and excluded == {"offer_fleet_basing_rights", "revoke_fleet_basing_rights"}
            and {c["action"] for c in commands} <= remaining-excluded, "New attempt overlaps a historical block")
    expected_dispatch = {"trade_favors_for_gold", "trade_favors_for_men", "trade_favors_for_sailors",
                         "trade_favors_for_war_prep", "revoke_march"}
    rows = []
    for command, receipt in zip(commands, results["results"]):
        actual = snapshot.status(command["request_id"])
        require(actual == receipt and receipt["command"] == command, "Reconstructed receipt differs")
        selected = [r for r in snapshot.rows if r["sequence"] == receipt["sequence"]]
        calls = [r for r in selected if r["event"] in ("native_call_begin", "native_call_return")]
        dispatch = command["action"] in expected_dispatch
        order = (0, 1, 2, 3, 4, 5, 7) if dispatch else (0, 1, 2, 5)
        require(len(calls) == 2*len(order) and receipt["native_result"]["adapter_call_attempts"] == len(order),
                "Native call count/order mismatch")
        for i, call in enumerate(order):
            entered, returned = calls[2*i:2*i+2]
            require(entered["event"] == "native_call_begin" and entered["call"] == call
                    and returned["event"] == "native_call_return" and returned["call"] == call
                    and returned["normal"] is True and returned["exception"] == 0,
                    "Unproven normal native call pair")
        native = receipt["native_result"]
        require(native["ownership_closed"] is True and native["owned_live"] == native["quarantined"] == native["adapter_fault"] == 0,
                "Ownership not closed")
        reservation = next(r for r in reservations if r["command"] == command)
        require(reservation["sequence"] == receipt["sequence"] and reservation["manifest"] == str(manifest_path)
                and digest(snapshot.raw[:reservation["audit_prefix_bytes"]]) == reservation["audit_prefix_sha256"],
                "Development reservation/audit prefix mismatch")
        pin(history.directory/("attempt-"+digest(command["request_id"].encode("ascii"))+".json"))
        for name in ("key-"+digest(command["request_id"].encode("ascii"))+".json",
                     f"{receipt['sequence']}.request", f"{receipt['sequence']}.claim"):
            pin(snapshot.directory/name)
        if dispatch:
            require(receipt["state"] == "dispatched" and native["submitted"] is True
                    and len([r for r in selected if r["event"] == "dispatch_intent"]) == 1,
                    "Dispatch is not proven")
        else:
            require(command["action"] == "trade_favors_for_heir" and receipt["state"] == "native_rejected"
                    and clean_rejection(native) and history._proven_rejection(reservation)
                    and not any(r["event"] == "dispatch_intent" for r in selected),
                    "Heir rejection is not strictly clean across the complete audit")
        rows.append({"command": command, "sequence": receipt["sequence"], "state": receipt["state"],
            "reason": native["reason"], "normal_native_call_pairs": len(order), "call_order": list(order),
            "ownership_closed": True, "development_reservation_verified": True,
            "strict_clean_rejection": not dispatch, "selected_effect_observed": dispatch,
            "saved_state_verified": False, "cold_reload_verified": False,
            "retry_forbidden": dispatch, "current_legality_proven_for_a_future_attempt": False})
    resources = {}
    field_map = {"trade_favors_for_gold": "treasury_milli", "trade_favors_for_men": "manpower_milli",
                 "trade_favors_for_sailors": "sailors_milli"}
    for action, field in field_map.items():
        a0, b0 = left["selected_resources"]["FRA"][field], left["selected_resources"]["SCO"][field]
        a1, b1 = right["selected_resources"]["FRA"][field], right["selected_resources"]["SCO"][field]
        require(a1-a0 > 0 and b1-b0 == -(a1-a0) and a0+b0 == a1+b1,
                "Selected resource transfer is not conserved: " + field)
        resources[action] = {"field": field, "FRA_before": a0, "FRA_after": a1,
            "SCO_before": b0, "SCO_after": b1, "FRA_delta": a1-a0, "SCO_delta": b1-b0,
            "selected_two_country_total_before": a0+b0, "selected_two_country_total_after": a1+b1,
            "selected_two_country_total_conserved": True}
    lpair, rpair = left["pairs"][0], right["pairs"][0]
    favor0, favor1 = lpair["target_to_actor"]["favors_raw_milli"], rpair["target_to_actor"]["favors_raw_milli"]
    require(favor0 == 98160 and favor1 == 94160 and favor1-favor0 == -4000,
            "Aggregate selected favor cost differs")
    require(all(p["target_to_actor"]["favors_raw_milli"] == favor0 for p in left["pairs"] if p["target_tag"] == "SCO")
            and all(p["target_to_actor"]["favors_raw_milli"] == favor1 for p in right["pairs"] if p["target_tag"] == "SCO"),
            "Duplicated favor pair observations disagree")
    war0, war1 = left["selected_resources"]["SCO"], right["selected_resources"]["SCO"]
    require(war0["war_prep_actor"] == "0x2d2d2d" and war1["war_prep_actor"] == right["countries"]["FRA"]["handle"]
            and war0["war_prep_date"] == 43808760 and war1["war_prep_date"] == 56468208
            and war1["war_prep_date"] > right["roots"]["date"], "Selected war-preparation effect missing")
    lm = next(p for p in left["pairs"] if p["action"] == "revoke_march")["dependency"]
    rm = next(p for p in right["pairs"] if p["action"] == "revoke_march")["dependency"]
    require(lm["object"]["type_name"]["name"] == "march" and rm["object"]["type_name"]["name"] == "vassal"
            and lm["object"]["actor_to_target"] is rm["object"]["actor_to_target"] is True
            and lm["target_overlord_handle"] == rm["target_overlord_handle"] == right["countries"]["FRA"]["handle"],
            "Selected march revocation effect missing or direction changed")
    effect_by_action = {**resources, "trade_favors_for_war_prep": {"before_date_raw": war0["war_prep_date"],
        "after_date_raw": war1["war_prep_date"], "before_actor": war0["war_prep_actor"], "after_actor": war1["war_prep_actor"]},
        "revoke_march": {"before_type": "march", "after_type": "vassal", "overlord_handle": rm["target_overlord_handle"]}}
    for row in rows:
        row["selected_effect"] = effect_by_action.get(row["command"]["action"])
    before_effect = {r["action"] for r in previous["actions"] if r["original_batch"]["historical_selected_state_success"]
                     or r["this_run_selected_effect_verified"]}
    require(len(before_effect) == 39 and not before_effect & expected_dispatch, "New effects overlap earlier coverage")
    remaining_now = remaining-excluded-expected_dispatch
    require(len(remaining_now) == 46 and "trade_favors_for_heir" in remaining_now
            and len(remaining_now-{r["command"]["action"] for r in rows}) == 45, "Remaining candidate arithmetic differs")
    for path in ("work/audit_corrective_runtime_20261014.py", "bridge/tag_command_audit.py", "bridge/tag_test_policy.py"):
        pin(path)
    for name, expected in pins.items():
        require({"bytes": len(raw := read(ROOT/name, 8*1024*1024)), "sha256": digest(raw)} == expected,
                "File evidence changed before report completion")
    return {"schema": "EU4TAG31-FAVOR-MARCH-RUNTIME-FILE-AUDIT/1", "file_only": True, "game_sha256": GAME_SHA,
        "game_process_accessed_by_this_tool": False, "game_calls_by_this_tool": 0, "requests_published_by_this_tool": 0,
        "identity": identity, "audit_sha256": results["audit_sha256"], "audit_rows": len(snapshot.rows),
        "native_call_pairs_verified": 39, "native_call_returns_all_normal_exception_zero": True,
        "all_ownership_closed": True, "development_reservations_verified": 6,
        "states": dict(Counter(row["state"] for row in rows)), "selected_effects_observed": 5,
        "strict_clean_rejection_actions": ["trade_favors_for_heir"], "actions": rows,
        "aggregate_favors": {"direction": "SCO_to_FRA", "before_milli": favor0, "after_milli": favor1,
            "delta_milli": -4000, "four_dispatched_favor_actions": 4,
            "separate_per_request_cost_causality_measured": False},
        "same_date_raw": left["roots"]["date"], "same_player_handle": left["roots"]["current_player"],
        "saved_state_verified": False, "cold_reload_verified": False,
        "coverage_calculation": {"previous_bound_actions_with_selected_effect_evidence": 39,
            "new_distinct_selected_effects": 5, "current_bound_actions_with_selected_effect_evidence": 44,
            "original_final_batch_repair_remainder": 53, "additional_cross_version_dispatch_blocks": 2,
            "new_dispatch_blocks": 5, "remaining_repair_candidates": 46,
            "remaining_rejected_in_this_batch": 1, "remaining_not_tested_in_this_batch": 45},
        "current_partition_120": {"historical_selected_effects": 35, "previous_corrective_selected_effects_and_reload": 4,
            "new_selected_live_effects_pending_save_reload": 5, "old_dispatch_without_selected_effects": 25,
            "additional_historical_fleet_dispatch_blocks": 2, "sparse_rejection_blocks": 2,
            "other_unknown_blocks": 1, "new_clean_heir_rejection": 1, "other_repair_candidates_not_tested_in_this_batch": 45},
        "remaining_repair_actions": sorted(remaining_now),
        "limitations": ["Observed selected live effects only; save and cold reload are pending independent evidence.",
            "The four-point favor drop is an aggregate batch observation, not individually sampled per-request cost attribution.",
            "Resource conservation covers only the three selected fields of FRA/SCO, not all world effects.",
            "Heir full88 returned normal false and cleanup is proven; the actual first failed legality branch is not identified.",
            "Five dispatched actions cannot be repeated; a clean heir rejection is a condition-repair candidate, not an automatic retry."],
        "peak_committed_bytes": committed_peak(), "source_pins": dict(sorted(pins.items()))}


def main():
    data = build()
    require(sum(data["current_partition_120"].values()) == 120, "Partition does not cover 120 bindings")
    write_new(OUT/"runtime-file-audit.json", (json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2)+"\n").encode("utf-8"))
    lines = ["# 六项人情与卫戍国定向补测文件审计", "", "5 项派发、继承人 1 项 full88 正常拒绝。39 对原生调用均正常返回且异常码0，6项所有权全部闭合，6份开发预留及固定审计前缀完整。", "",
        "| 选定效果 | 结果 |", "|---|---|", "| 金币 | FRA +457736 / SCO -457736 raw milli；两国合计守恒 |",
        "| 兵源 | FRA +2040 / SCO -2040 raw milli；两国合计守恒 |", "| 水手 | FRA +126756 / SCO -126756 raw milli；两国合计守恒 |",
        "| 备战 | SCO日期43808760→56468208，备战actor由哨兵改FRA |", "| 撤销卫戍国 | FRA→ORL march→vassal，领主仍FRA |", "",
        "SCO→FRA人情98.160→94.160，合计减少4点；没有逐次采样归因每项扣费。继承人拒绝通过strict clean_rejection及完整跨session调用/清理证明，仍未定位首个失败条件。", "",
        "当前120项中44项有独立历史或本轮选定效果证据（35历史+4前轮+5本轮）。原53修复余项扣2项历史驻港派发和5项新派发，剩46：继承人本轮干净拒绝1，其余45本轮未测。", "",
        "本报告 saved_state_verified=false、cold_reload_verified=false；保存和冷重载须用后续独立证据关联。没有读取进程、发请求或修改旧报告/预留。", ""]
    write_new(OUT/"runtime-file-audit.md", "\n".join(lines).encode("utf-8"))
    print(json.dumps({"states": data["states"], "normal_call_pairs": 39, "reservations": 6,
        "selected_effects": 5, "bound_selected_effect_coverage": 44, "remaining_candidates": 46,
        "source_pins": len(data["source_pins"]), "peak_committed_bytes": data["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
