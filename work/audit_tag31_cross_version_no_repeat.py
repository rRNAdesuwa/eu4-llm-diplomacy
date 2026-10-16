"""Bounded file-only historical dispatch/uncertainty audit for the 53 candidates.

The result is an additional exclusion overlay, not native legality or permission
to publish. It never edits policy, game files, reservations, or frozen evidence.
"""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import decode, digest, read, require
from work.validate_current_diplomacy_1375 import committed_peak

OUT = ROOT/"work/reports/diplomacy-corrective-20261013-r2"
MAX_FILE = 8*1024*1024
MAX_FILES = 1024
TRIGGER_TRUE = ("submitted", "submit_entered", "submit_attempted", "native_dispatch_returned",
                "ownership_uncertain", "session_frozen", "freeze_session")


def walk(value, action=None, context=None, pointer=""):
    context = context or {}
    if isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk(item, action, context, pointer+"/"+str(i))
    elif isinstance(value, dict):
        own = value.get("action", value.get("action_id", value.get("protocol_action_id", action)))
        action = own if isinstance(own, str) else action
        ctx = dict(context)
        for key in ("pid", "creation", "process_creation_filetime", "session", "sequence", "mode", "operation"):
            if key in value and not isinstance(value[key], (list, dict)):
                ctx[key] = value[key]
        if isinstance(value.get("identity"), dict):
            ctx.update(value["identity"])
        if isinstance(value.get("scope"), dict):
            ctx.update({k: v for k, v in value["scope"].items() if not isinstance(v, (list, dict))})
        if isinstance(value.get("command"), dict):
            action = value["command"].get("action", action)
        yield action, ctx, value, pointer
        for key, item in value.items():
            if isinstance(item, (list, dict)):
                yield from walk(item, action, ctx, pointer+"/"+key)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pins = {}
    def pin(path):
        path = (ROOT/path).resolve()
        raw = read(path, MAX_FILE)
        key = path.relative_to(ROOT).as_posix()
        expected = {"bytes": len(raw), "sha256": digest(raw)}
        require(key not in pins or pins[key] == expected, "Historical evidence changed during scan")
        pins[key] = expected
        require(committed_peak() < 768*1024*1024, "Historical audit memory exceeded 768 MiB")
        return raw
    current = decode(pin("work/reports/unified-validation-20261013/current-action-validation.json"))
    ids = {row["action"] for row in current["actions"] if row["remaining_condition_repair_candidate_not_tested"]}
    require(len(ids) == 53, "Frozen candidate scope changed")
    roots = [ROOT/"work/runtime", ROOT/"work/candidates", ROOT/"bridge/native"]
    paths = {p for root in roots for p in root.rglob("*.jsonl")
             if not any(term in p.name.lower() for term in ("mock", "test", "validation"))}
    # Include recorded summaries independently of raw event schemas. Never scan
    # native disassembly, selected state, save files, or arbitrary build outputs.
    paths.update(p for p in (ROOT/"work/runtime").rglob("*.json")
                 if any(term in p.name.lower() for term in ("audit", "finish", "integration", "checkpoint", "dispatch", "results", "terminal"))
                 and "/files/" not in p.as_posix())
    paths.add(ROOT/"bridge/diplomacy_research_evidence.json")
    require(len(paths) <= MAX_FILES, "Historical file inventory exceeds bound")
    inventory, malformed, observations = [], [], []
    for path in sorted(paths):
        if not path.stat().st_size:
            inventory.append({"path": path.relative_to(ROOT).as_posix(), "bytes": 0, "empty": True})
            continue
        raw = pin(path)
        inventory.append({"path": path.relative_to(ROOT).as_posix(), **pins[path.relative_to(ROOT).as_posix()]})
        source = path.relative_to(ROOT).as_posix()
        data_rows = []
        if path.suffix == ".jsonl":
            require(len(raw.splitlines()) <= 65536, "Historical line count exceeds bound")
            for number, line in enumerate(raw.splitlines(), 1):
                try:
                    data_rows.append((number, decode(line)))
                except (ValueError, UnicodeError):
                    malformed.append({"path": source, "line": number})
        else:
            try:
                data_rows.append((None, decode(raw)))
            except (ValueError, UnicodeError):
                malformed.append({"path": source, "line": None})
        # First collect action/sequence identities, then attach result rows that
        # omit action names (modern request_result and dispatch_intent records).
        identities = {}
        for _, item in data_rows:
            for action, ctx, row, _ in walk(item):
                if isinstance(action, str) and type(ctx.get("sequence")) is int and ctx["sequence"] > 0:
                    key = (ctx.get("pid"), ctx.get("creation", ctx.get("process_creation_filetime")), ctx.get("session"), ctx["sequence"])
                    identities.setdefault(key, set()).add(action)
        for number, item in data_rows:
            for action, ctx, row, pointer in walk(item):
                key = (ctx.get("pid"), ctx.get("creation", ctx.get("process_creation_filetime")), ctx.get("session"), ctx.get("sequence"))
                possible = {action} if action in ids else identities.get(key, set()) & ids
                if not possible:
                    continue
                # Older numeric status spaces differ; status=5 alone is not a
                # dispatch claim unless its schema is the native pair-send host.
                triggers = [field for field in TRIGGER_TRUE if row.get(field) is True]
                if row.get("event") == "dispatch_intent":
                    triggers.append("dispatch_intent")
                if row.get("state") in ("dispatched", "unknown_no_retry", "publication_unknown", "claimed"):
                    triggers.append("state="+row["state"])
                if row.get("schema") in ("EU4PAIRSEND/1", "EU4TAGCOMMAND/1") and row.get("status") == 5:
                    triggers.append("native_status_5")
                if row.get("owned_live", 0) or row.get("quarantined", 0):
                    triggers.append("unclosed_owned_or_quarantined")
                # Ordinary per-action audit observations allow a bounded
                # negative search to be reproduced for the unblocked actions.
                scalar = {k: v for k, v in row.items() if not isinstance(v, (list, dict))}
                for selected_action in possible:
                    observations.append({"action": selected_action, "source": source, "line": number,
                        "json_pointer": pointer, "identity_context": ctx, "event": row.get("event"),
                        "triggers": triggers, "scalars": scalar})
        del data_rows, raw
    # Resolve copied/preflight prefixes against all complete recorded streams:
    # a claimed request with no result anywhere remains an additional block.
    def request_key(observation):
        ctx = observation["identity_context"]
        return (ctx.get("pid"), ctx.get("creation", ctx.get("process_creation_filetime")),
                ctx.get("session"), ctx.get("sequence"), observation["action"])
    complete_keys = {request_key(row) for row in observations
                     if row["event"] in ("request_result", "lab_request_complete")}
    unclosed_claims = [row for row in observations if row["event"] in ("request_claimed", "lab_request_claimed")
                      and request_key(row) not in complete_keys]
    for row in unclosed_claims:
        row["triggers"].append("claimed_without_recorded_complete_result")
    # The research ledger contains native_dispatch_returned even when no final
    # selected state was proved. These dispatches still prohibit development retry.
    blockers = [row for row in observations if row["triggers"]]
    blocked_ids = {row["action"] for row in blockers}
    counts = Counter(row["action"] for row in observations)
    safe = sorted(ids-blocked_ids)
    rows = [{"action": action, "candidate_53_member": True,
             "cross_version_no_repeat_blocked": action in blocked_ids,
             "historical_matching_observations": counts[action],
             "block_evidence": [row for row in blockers if row["action"] == action],
             "status": "blocked_by_historical_dispatch_or_uncertainty" if action in blocked_ids else "no_block_found_in_bounded_recorded_history",
             "current_legality_proven": False, "permission_to_publish": False} for action in sorted(ids)]
    # Reconstruct the V30 manifest/DLL/claim/dispatch evidence through the
    # dedicated read-only historical audit instead of relying on prose.
    from bridge.tag_command_audit import recorded_snapshot
    v30_path = ROOT/"bridge/native/tag_command_1375/build-1/build/build.json"
    v30 = decode(pin("work/runtime/tagcommand30-nonplayer-dispatch-37816.json"))
    v30_identity = v30["status"]["identity"]
    snapshot = recorded_snapshot(v30_path, v30_identity)
    v30_receipt = snapshot.status("tag30-por-bri-fleet-1")
    require(v30_receipt["command"]["action"] == "offer_fleet_basing_rights" and v30_receipt["state"] == "dispatched",
            "Known historical V30 fleet dispatch missing")
    pin(v30_path)
    manifest = decode(read(v30_path, MAX_FILE))
    pin(v30_path.parent/manifest["DLL"])
    pin(snapshot.directory/"events.jsonl")
    for filename in ("key-"+digest(b"tag30-por-bri-fleet-1")+".json", "1.request", "1.claim"):
        pin(snapshot.directory/filename)
    v30_events = (snapshot.directory/"events.jsonl").relative_to(ROOT).as_posix()
    v17_events = "work/runtime/native1375-v17/session-22784-01dd56bf28902f93/research-1375.jsonl"
    minimal_names = [v30_events, v17_events, *[(snapshot.directory/name).relative_to(ROOT).as_posix()
        for name in ("key-"+digest(b"tag30-por-bri-fleet-1")+".json", "1.request", "1.claim")]]
    minimal = {"schema": "EU4TAG-HISTORICAL-DISPATCH-EXCLUSIONS/1", "game_sha256": manifest["game_sha256"],
        "purpose": "Additional immutable development no-repeat exclusions; historical dispatch blocks regardless of subsequent rejection or AI refusal.",
        "blocked_actions": ["offer_fleet_basing_rights", "revoke_fleet_basing_rights"],
        "source_pins": {name: pins[name] for name in minimal_names},
        "evidence": [
            {"action": "offer_fleet_basing_rights", "source": v30_events,
             "identity": v30_identity, "request_id": "tag30-por-bri-fleet-1", "sequence": 1,
             "claim_line": 4, "claim_expected": {"event": "request_claimed", "action": "offer_fleet_basing_rights", "actor": "POR", "target": "BRI", "sequence": 1},
             "dispatch_intent_line": 18, "sender_return_line": 20, "result_line": 21,
             "result_expected": {"event": "request_result", "sequence": 1, "submitted": True, "status": 4,
                                 "reason": "normal_dispatch_slot_consumed", "ownership_closed": True}},
            {"action": "revoke_fleet_basing_rights", "source": v17_events,
             "identity": {"pid": 22784, "process_creation_filetime": "01dd56bf28902f93"}, "sequence": 8,
             "claim_line": 537, "claim_expected": {"event": "lab_request_claimed", "action": "revoke_fleet_basing_rights", "actor": "FRA", "target": "POR", "sequence": 8, "mode": "submit"},
             "dispatch_intent_line": 539, "result_line": 540, "result_json_pointer": "/record",
             "result_expected": {"event": "pair_engine_complete", "action_id": "revoke_fleet_basing_rights",
                                 "submit_entered": True, "submit_returned": True, "context_submit_return": True,
                                 "caller_container_consumed": True, "exception": 0}, "request_complete_line": 541}],
        "claims": {"native_dispatch_observed": True, "AI_acceptance_verified": False, "gameplay_effects_verified": False},
        "limitations": ["This small file deliberately contains only the minimum two additional action exclusions, not a complete historical policy.",
                         "Line numbers are one-based JSONL lines and must be checked together with exact bytes/SHA pins.",
                         "The V17 action is associated with sequence 8 by its outer lab_native_record and adjacent claim/completion."]}
    minimal_path = OUT/"historical-dispatch-exclusions.json"
    minimal_path.write_text(json.dumps(minimal, ensure_ascii=True, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    pin(minimal_path)
    require("offer_fleet_basing_rights" in blocked_ids and "revoke_fleet_basing_rights" in blocked_ids,
            "Known historical fleet exclusions not discovered")
    pin("work/audit_tag31_cross_version_no_repeat.py")
    report = {"schema": "EU4TAG31-CROSS-VERSION-NO-REPEAT-AUDIT/1", "file_only": True,
        "game_process_accessed": False, "native_calls": 0, "requests_published": 0,
        "input_candidate_count": 53, "blocked_count": len(blocked_ids), "blocked_actions": sorted(blocked_ids),
        "unblocked_history_candidate_count": len(safe), "unblocked_history_candidates": safe,
        "safe_means": "No historical dispatch/uncertainty was found in the bounded recorded audit inventory; current legality and full test-only checks remain required.",
        "V30_fleet_dispatch_reconstructed": {"manifest": v30_path.relative_to(ROOT).as_posix(), "receipt": v30_receipt},
        "priority_history_status": {action: next(row for row in rows if row["action"] == action)
            for action in ("trade_favors_for_gold", "trade_favors_for_men", "trade_favors_for_sailors", "trade_favors_for_war_prep", "trade_favors_for_heir", "revoke_march")},
        "actions": rows, "inventory": inventory, "scan_file_count": len(inventory),
        "malformed_inputs": malformed, "scan_matching_observations": len(observations),
        "claims_without_any_matching_recorded_complete_result": len(unclosed_claims),
        "limitations": ["Frozen 53 denotes clean rejection in the original final batch, not a complete cross-version no-repeat clearance.",
            "Historical dispatch prohibits retry even after AI refusal or when effects were unknown.",
            "No-block-found is a bounded recorded-history statement, not universal absence or permission to send.",
            "Offline mock/test event files are excluded; native disassembly and selected save files are not historical dispatch records.",
            "This report is an exclusion overlay and does not change frozen evidence or bridge development policy."],
        "peak_committed_bytes": committed_peak(), "source_pins": dict(sorted(pins.items()))}
    require(not malformed, "Historical audit has malformed input; no safe candidate claim can be completed")
    (OUT/"cross-version-no-repeat-audit.json").write_text(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    lines = ["# 53 候选跨版本禁止复测审计", "", f"对{len(inventory)}个有界历史审计输入完成检查；{len(blocked_ids)}项存在历史派发/不确定记录，原53候选须扣除。", "",
             f"阻断：{', '.join(sorted(blocked_ids))}。其余{len(safe)}项仅表示在本次有界历史中未发现阻断，实时合法性仍未验证。", "",
             "V30/PID37816 tag30-por-bri-fleet-1 已由recorded_snapshot重构为dispatched，不能因原最终批次拒绝而再试。V27/PID53332提供驻港权也曾派发。V17/PID22784 seq8撤销驻港权曾submit_entered/returned=true且caller_container_consumed=true，同样禁测。", "",
             "五项人情及revoke_march的单独审计结果见JSON；没有把缺失效果当允许重试。", ""]
    (OUT/"cross-version-no-repeat-audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"blocked": sorted(blocked_ids), "unblocked_count": len(safe), "scan_files": len(inventory),
                      "matching_observations": len(observations), "peak_committed_bytes": report["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
