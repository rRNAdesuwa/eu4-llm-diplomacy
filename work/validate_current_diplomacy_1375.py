"""Reproducible file-only audit of all current TAG diplomacy bindings.

This tool has no runtime, load, publish, reservation, or game-state operations.
It preserves the distinction between historical dispatch, selected state, and
an individually verified effect. It never authorizes a new test by itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_audit import recorded_snapshot
from bridge.tag_command_backend import TagCommandBackend, GAME_SHA, decode, digest, read, require
from bridge.tag_test_policy import clean_rejection
from tools.plan_diplomacy_gap_tests import success_ledger

OUT = ROOT / "work/reports/unified-validation-20261013"
FINAL = "work/runtime/tag31-integration-final-20261013.json"
EXPECTED_FINAL_SHA = "704e9106db4eaf8ffd2a5eb9e23055862a7529130ebed3c54bd49cf82c2936ee"


def committed_peak():
    if sys.platform != "win32":
        return None
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    require(ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb),
        "Cannot verify process memory bound")
    require(counters.PeakPagefileUsage < 1024**3, "Analysis memory exceeded 1 GiB")
    return counters.PeakPagefileUsage


def build():
    pins = {}
    def pin(path, maximum=16*1024*1024):
        path = (ROOT / path).resolve()
        relative = path.relative_to(ROOT).as_posix()
        raw = read(path, maximum)
        expected = {"bytes": len(raw), "sha256": digest(raw)}
        require(relative not in pins or pins[relative] == expected, "Input changed between reads: " + relative)
        pins[relative] = expected
        committed_peak()
        return raw
    def document(path):
        return decode(pin(path))

    backend = TagCommandBackend()  # Files only; runtime remains None.
    require(backend.runtime is None and len(backend.actions) == 120, "Current binding scope changed")
    pin(backend.manifest_path)
    pin(backend.build / backend.manifest["DLL"])
    for name, expected in backend.manifest["source_pins"].items():
        require(digest(pin(name)) == expected["sha256"], "Current native source pin mismatch")
    final = document(FINAL)
    require(pins[FINAL]["sha256"] == EXPECTED_FINAL_SHA, "Closed original integration evidence changed")
    require(final["completed_without_unattempted_requests"] is True
            and final["planned"] == 120 and len(final["results"]) == 120,
            "Original integration is not complete")
    closed = document("bridge/tag_test_history_1375.json")
    require(closed["source"] == FINAL and closed["source_sha256"] == EXPECTED_FINAL_SHA
            and closed["game_sha256"] == GAME_SHA and closed["final_integration_closed"] is True
            and closed["effect_success_claimed"] is False
            and closed["requests"] == [{"command": r["command"], "state": r["state"]} for r in final["results"]],
            "Closed history differs from original results")
    policy = document("work/reports/diplomacy-no-repeat-test-policy-1375.json")
    for name, expected in policy["source_pins"].items():
        require(digest(pin(name)) == expected, "Historical selected-state source changed: " + name)
    regenerated, _ = success_ledger()
    require(regenerated == policy and policy["blocked_count"] == 38, "Historical success ledger changed")

    snapshots, fragment_evidence = {}, []
    manifest_candidates = list((ROOT / "bridge/native/tag_diplomacy_1375_v31").glob("build-*/build/build.json"))
    require(len(manifest_candidates) <= 32, "Historical build search bound")
    for fragment in final["fragments"]:
        identity = fragment["identity"]
        matches = [path for path in manifest_candidates if digest(read(path, 1024*1024)) == identity["manifest_sha256"]]
        require(len(matches) == 1, "Historical manifest is ambiguous or absent")
        manifest_path = matches[0]
        manifest = decode(pin(manifest_path))
        pin(manifest_path.parent / manifest["DLL"])
        snapshot = recorded_snapshot(manifest_path, identity)
        require(snapshot.raw == snapshot.complete and snapshot.summary["audit_sha256"] == fragment["audit_sha256"],
                "Historical audit is partial or differs from merged evidence")
        require(snapshot.summary["terminal"] == fragment["terminal"]
                and sum(r["event"] == "native_call_begin" for r in snapshot.rows) == fragment["native_call_begins"],
                "Historical audit summary differs")
        pin(snapshot.directory / "events.jsonl")
        snapshots[identity["session"]] = snapshot
        fragment_evidence.append({"manifest": manifest_path.relative_to(ROOT).as_posix(),
            "identity": identity, "audit": (snapshot.directory / "events.jsonl").relative_to(ROOT).as_posix(),
            "audit_rows": len(snapshot.rows), "native_call_begins": fragment["native_call_begins"],
            "terminal": fragment["terminal"], "historical_sources_not_claimed_runnable": True})

    effects_paths = ["work/runtime/tag31-effects-diff-20261013.json",
                     "work/runtime/tag31-effects-rivals-coalition-diff-20261013.json"]
    effects = [document(path) for path in effects_paths]
    require(all(e["file_only"] is True and e["gameplay_causality_proven"] is False
                and e["AI_acceptance_all_verified"] is False for e in effects), "Effect evidence was promoted")
    require(len({(e["before_save_sha256"], e["after_save_sha256"]) for e in effects}) == 1,
            "Selected-state comparisons use different saves")
    candidate_file = document("work/runtime/tag31-corrective-candidates-20261013.json")
    bindings = {row["action"]: row for row in backend.bindings}
    require(set(bindings) == {r["command"]["action"] for r in final["results"]}, "Old/new action scope differs")
    rows = []
    for old in final["results"]:
        command = old["command"]
        action = command["action"]
        snapshot = snapshots[old["identity"]["session"]]
        actual = snapshot.status(command["request_id"])
        require(actual == old, "Reconstructed historical receipt differs: " + action)
        key = "key-" + digest(command["request_id"].encode("ascii")) + ".json"
        for name in (key, f"{old['sequence']}.request", f"{old['sequence']}.claim"):
            path = snapshot.directory / name
            if path.exists():
                pin(path)
        selected = [r for r in snapshot.rows if r["sequence"] == old["sequence"]]
        calls = [r for r in selected if r["event"] in ("native_call_begin", "native_call_return")]
        clean = old["state"] == "native_rejected" and clean_rejection(old["native_result"])
        complete_cleanup = False
        if clean:
            expected = ([0, 1, 2, 5] if old["native_result"]["reason"] == "full88_normal_false"
                        else [0, 1, 2, 3, 4, 5, 6])
            require(old["binding"] is not None and len(calls) == 2*len(expected)
                    and old["native_result"]["adapter_call_attempts"] == len(expected)
                    and not any(r["event"] == "dispatch_intent" for r in selected), "Incomplete rejection audit: " + action)
            for index, call in enumerate(expected):
                begin, returned = calls[2*index:2*index+2]
                require(begin["event"] == "native_call_begin" and begin["call"] == call
                        and returned["event"] == "native_call_return" and returned["call"] == call
                        and returned["normal"] is True and returned["exception"] == 0,
                        "Cleanup call sequence is not proven normal: " + action)
            reject_call = 2 if old["native_result"]["reason"] == "full88_normal_false" else 4
            require(next(r for r in calls if r["event"] == "native_call_return" and r["call"] == reject_call)["boolean"] is False,
                    "Missing normal false condition: " + action)
            complete_cleanup = True
        historical = policy["blocked_actions"].get(action, [])
        group = ("historical_success_no_retry" if historical else
                 "clean_rejection_repair_candidate" if clean else
                 "dispatched_no_retry" if old["state"] == "dispatched" else
                 "unknown_no_retry" if old["state"] == "unknown_no_retry" else "sparse_rejection_blocked")
        pair_observations = []
        for path, effect in zip(effects_paths, effects):
            pair = {command["actor"], command["target"]}
            for direction, records in effect["global_diplomacy"].items():
                for index, record in enumerate(records):
                    values = {entry["key"]: entry.get("value") for entry in record["entries"]}
                    if {values.get("first"), values.get("second")} == pair:
                        pair_observations.append({"source": path, "pointer": f"/global_diplomacy/{direction}/{index}",
                            "change": direction, "record_key": record["key"], "fields": values})
        rows.append({"action": action, "binding": bindings[action], "previous_command": command,
            "old_state": old["state"], "old_reason": (old["native_result"] or {}).get("reason"),
            "old_identity": old["identity"], "old_sequence": old["sequence"], "audit_sha256": old["audit_sha256"],
            "recorded_receipt_reconstructed": True, "clean_rejection_fields": clean,
            "complete_normal_rejection_cleanup_calls": complete_cleanup,
            "native_call_begins": sum(r["event"] == "native_call_begin" for r in selected),
            "dispatch_intent_observed": any(r["event"] == "dispatch_intent" for r in selected),
            "historical_selected_state_success": bool(historical), "historical_success_evidence": historical,
            "historical_success_is_not_this_batch_effect_attribution": True,
            "policy_group": group, "eligible_for_condition_repair_planning": group == "clean_rejection_repair_candidate",
            "new_dispatch_authorized_by_this_report": False, "current_pair_conditions_evaluated": False,
            "original_request_id_may_be_reused": False,
            "this_batch_individual_AI_acceptance_verified": False,
            "this_batch_individual_effect_verified": False, "individual_effect_validation_still_missing": True,
            "same_pair_serialized_observations_not_attributed_to_request": pair_observations})
    candidates = {r["action"] for r in rows if r["eligible_for_condition_repair_planning"]}
    require(candidates == {r["action"] for r in candidate_file["candidates"]}
            and candidate_file["source_sha256"] == EXPECTED_FINAL_SHA and len(candidates) == 57,
            "Corrective candidate list differs from independently audited results")
    tests = document("work/reports/unified-validation-20261013/python-tests.json")
    test_stderr = pin("work/reports/unified-validation-20261013/python-tests.stderr").decode("utf-8")
    require(tests["exit_code"] == 0 and tests["game_calls"] == 0
            and "Ran 80 tests" in test_stderr and "\nOK" in test_stderr, "Current offline test receipt is not passing")
    for name in ("work/validate_current_diplomacy_1375.py", "bridge/tag_command_audit.py",
                 "bridge/tag_test_policy.py", "bridge/tag_command_backend.py", "tools/plan_diplomacy_gap_tests.py"):
        pin(name)
    # Recheck all bounded sources before publishing an evidence-only output.
    for name, expected in list(pins.items()):
        require({"bytes": len(raw := read(ROOT/name, 16*1024*1024)), "sha256": digest(raw)} == expected,
                "Source changed before report completion: " + name)
    require(backend.runtime is None, "A runtime adapter was unexpectedly constructed")
    return {"schema": "EU4TAG31-UNIFIED-FILE-VALIDATION/1", "file_only": True, "game_sha256": GAME_SHA,
        "game_calls": 0, "game_state_reads": 0, "requests_published": 0, "development_ledger_writes": 0,
        "original_batch_may_be_repeated": False, "current_binding_count": len(rows),
        "excluded_lookup_count": len(backend.excluded), "current_native_manifest": backend.manifest_path.relative_to(ROOT).as_posix(),
        "current_manifest_sha256": backend.manifest_sha, "current_dll_sha256": backend.manifest["dll"]["sha256"],
        "current_native_source_pin_count": len(backend.manifest["source_pins"]),
        "historical_original_states": dict(Counter(r["old_state"] for r in rows)),
        "policy_groups": dict(Counter(r["policy_group"] for r in rows)),
        "historical_success_ledger_count": 38, "historical_successes_in_current_bindings": sum(r["historical_selected_state_success"] for r in rows),
        "historical_successes_outside_current_bindings": sorted(set(policy["blocked_actions"])-set(bindings)),
        "clean_rejections": sum(r["complete_normal_rejection_cleanup_calls"] for r in rows),
        "offline_python_tests": {"count": 80, "passed": True, "rerun_by_this_tool": False,
                                 "receipt": "work/reports/unified-validation-20261013/python-tests.json"},
        "fragments": fragment_evidence, "selected_state_effect_evidence": effects_paths,
        "limitations": ["Dispatch does not prove AI acceptance or gameplay effect.",
            "Historical selected-state success is an independent fact and cannot be attributed to the original final batch.",
            "Same-pair save changes are not request causality; combined start/stop and unrelated action changes can share a pair.",
            "All 120 still lack complete individual effect acceptance for this batch; historical success rows keep their separate selected-state evidence.",
            "The 57 candidates require repaired conditions, current runtime checks, a fresh ID and --test-only; this report publishes nothing.",
            "Two lease rejections lack full cleanup proof and remain blocked.",
            "Historical build source pins are not claimed executable after later source changes."],
        "peak_committed_bytes": committed_peak(), "source_pins": dict(sorted(pins.items())), "actions": rows}


def markdown(report):
    groups = report["policy_groups"]
    lines = ["# 当前 120 个外交行动统一文件验证", "",
        "固定 EU4 1.37.5 二进制；本报告核查文件证据，没有读取游戏进程、创建开发预留或发送请求。",
        "原唯一批次：41 派发、77 拒绝、2 未知。派发不等于 AI 接受或效果通过。", "",
        "当前 build-7 的 44 个原生源码 pin、manifest、DLL，以及三个旧构建的 manifest / DLL / 完整审计和 120 份请求回执均重新核对。80 项现有离线 Python 检查通过，本工具没有重复运行它们。", "",
        f"历史成功台账 38 项，其中 35 项属于当前绑定。优先按成功禁测分类：35 成功禁测、{groups['dispatched_no_retry']} 其他派发禁测、57 干净拒绝修复候选、2 稀疏拒绝阻断、1 其他未知阻断。", "",
        "75 项正常拒绝的完整调用/清理得到验证；其中 18 项已有历史成功，剩余 57 项可做条件修复规划。候选不表示实时合法，不得重复原 request_id 或原全量批次。", "",
        "原批次的 120 项均未取得完整逐项 AI 接受与效果验收；历史选定状态成功独立保留，不归因于本批次。同 pair 存档变化仅作索引。", "",
        "| 行动 | 类别 | 原结果 | 干净拒绝/清理 | 独立历史成功 | 补测分组 | 本批次逐项效果 |",
        "|---|---|---|---|---|---|---|"]
    labels = {"historical_success_no_retry": "历史成功禁测", "clean_rejection_repair_candidate": "修条件后新 ID 定向候选",
              "dispatched_no_retry": "已派发禁测", "unknown_no_retry": "未知禁测", "sparse_rejection_blocked": "证据稀疏阻断"}
    for row in report["actions"]:
        lines.append(f"| `{row['action']}` | {row['binding']['category']} | {row['old_state']} | {'是' if row['complete_normal_rejection_cleanup_calls'] else '未证明'} | {'是' if row['historical_selected_state_success'] else '无台账'} | {labels[row['policy_group']]} | 待完整验收 |")
    lines += ["", "完整旧请求、来源散列、审计身份、逐项清理和独立历史证据见 `action-validation.json`。", "",
              "复现：`python -B work/validate_current_diplomacy_1375.py --check`。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check deterministic report contents without rewriting")
    args = parser.parse_args()
    report = build()
    encoded = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    text = markdown(report).encode("utf-8")
    if args.check:
        existing = decode(read(OUT/"action-validation.json", 4*1024*1024))
        # Peak memory is process-specific telemetry, not a deterministic input.
        existing.pop("peak_committed_bytes")
        deterministic = dict(report)
        deterministic.pop("peak_committed_bytes")
        require(existing == deterministic and read(OUT/"action-validation.md", 256*1024) == text,
                "Unified validation report is stale")
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT/"action-validation.json").write_bytes(encoded)
        (OUT/"action-validation.md").write_bytes(text)
    print(json.dumps({"bindings": len(report["actions"]), "old_states": report["historical_original_states"],
        "policy_groups": report["policy_groups"], "game_calls": 0, "source_pins": len(report["source_pins"]),
        "peak_committed_bytes": report["peak_committed_bytes"], "check": args.check}, sort_keys=True))


if __name__ == "__main__":
    main()
