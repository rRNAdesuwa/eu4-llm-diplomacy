"""Offline, exact-build, bounded cancellation ABI evidence for five actions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg


def fact(text, *rvas, **fields):
    return dict(summary=text, evidence_rvas=[hex(r) for r in rvas], runtime_verified=False, **fields)


PROFILES = [
    {"name": "improve_relation", "token": 0x2ddb, "vtable_rva": 0x1c7dd68,
     "public_cancel_id": "stop_improving_relations", "size": 0x40,
     "setter_rva": 0x4e99d0, "validity_rva": 0x574460, "uses_envoy_rva": 0x4e4d50,
     "reply_rva": 0x8f450, "cancel_envoy": "leave -1; active relation+0x30 owns mission association",
     "cancel_uses_new_envoy": False, "cancel_checks_common_cooldown": False},
    {"name": "spy_network", "token": 0x3378, "vtable_rva": 0x1c7cc48,
     "public_cancel_id": "stop_building_spy_network", "size": 0x40,
     "setter_rva": 0x586330, "validity_rva": 0x5856a0, "uses_envoy_rva": 0x4e4d50,
     "reply_rva": 0x8f450, "cancel_envoy": "resolve the existing active spy mission entry+0x44 into action+0x30",
     "cancel_uses_new_envoy": False, "cancel_checks_common_cooldown": False},
    {"name": "guaranteeaction", "token": 0x2941, "vtable_rva": 0x1c7fe50,
     "public_cancel_id": "revoke_guarantee", "size": 0x40,
     "setter_rva": 0x4e99d0, "validity_rva": 0x521ad0, "uses_envoy_rva": 0x8f440,
     "reply_rva": 0x8f450, "cancel_envoy": "leave -1; ordinary command allocates a new envoy trip",
     "cancel_uses_new_envoy": True, "cancel_checks_common_cooldown": True},
    {"name": "royal_marriage", "token": 0x28df, "vtable_rva": 0x1c80ab0,
     "public_cancel_id": "break_marriage", "size": 0x68,
     "setter_rva": 0x4e99d0, "validity_rva": 0x4ef3b0, "uses_envoy_rva": 0x8f440,
     "reply_rva": 0x4e4d50, "cancel_envoy": "leave -1; ordinary command allocates a new envoy trip",
     "cancel_uses_new_envoy": True, "cancel_checks_common_cooldown": True,
     "derived_fields": "factory-initialized EngineString32 at +0x40 and force byte +0x60 remain at defaults; clone reconstructs both defaults"},
    {"name": "vassalaction", "token": 0x2940, "vtable_rva": 0x1c7fd20,
     "public_cancel_id": "cancel_vassalization", "size": 0x40,
     "setter_rva": 0x4e99d0, "validity_rva": 0x51f020, "uses_envoy_rva": 0x8f440,
     "reply_rva": 0x51fa90, "cancel_envoy": "leave -1; ordinary command allocates a new envoy trip",
     "cancel_uses_new_envoy": True, "cancel_checks_common_cooldown": True,
     "excluded_public_id": "break_vassalization",
     "subject_type_limit": "dependency+0x40 must match *(subject_registry+0x58) vassal or *(subject_registry+0x60) client_vassal; registry global RVA 0x233ffd8",
     "permitted_subject_types": ["vassal", "client_vassal"]},
]

FACTS = {
    "fresh_initialization": fact(
        "Create a fresh object using the exact native token and null definition. Set actor=original "
        "to the initiating country's full current handle, recipient to target full handle, dates to "
        "current rawdate, envoy=-1 initially, type=0, flag39=0,id=0. Set cancel via +0xe0 after handles "
        "are populated, or reproduce its reviewed lookup. Do not reuse a prior action/response object.",
        0x1d59bd, 0x1d59c1, 0x1d59c5, 0x1d59c9, 0x1d59cd, 0x1d59d1,
        0x1d59d9, 0x1d59dd, 0x1d59e4, 0x586336,
        common_fields={"actor": [0x10, 8], "original": [0x18, 8], "target": [0x20, 8],
                       "date": [0x28, 4], "command_date": [0x2c, 4], "envoy": [0x30, 4],
                       "type": [0x34, 4], "value": [0x38, 1], "flag": [0x39, 1], "id": [0x3c, 4]}),
    "spy_setter": fact(
        "The spy +0xe0 override 586330 writes value and, for false, checks actor->target relation "
        "bit8 then scans the ACTOR diplomat vector. It requires entry status BYTE==2, nonnull mission, "
        "mission virtual+0x70==1, nonnull mission+0xa0 task, task virtual+0x70==0x3378 and matching "
        "target slot. It writes matching entry+0x44 DWORD into action+0x30. Other four setters only "
        "write value. Signature is void(action*,bool), not a boolean success result.",
        0x586336, 0x586379, 0x586384, 0x586395, 0x5863c9, 0x5863cf,
        0x5863db, 0x5863de, 0x5863e6, 0x5863f8, 0x5863fb, 0x586412, 0x586421, 0x586424,
        setter_signature="void __fastcall(void* action, bool value)",
        action_envoy_offset=0x30, diplomat_id_offset=0x44, diplomat_status_offset=0x18,
        mission_pointer_offset=0x10, mission_task_offset=0xa0, task_target_offset=0x20),
    "spy_false_positive_preview_risk": fact(
        "Spy false validity checks relation bit8 and subject restrictions but does not resolve envoy "
        "ID. Therefore writing value=false while leaving envoy=-1 can pass native preview/gate "
        "yet fail to stop the active task. Common cancellation later locates a diplomat only by "
        "action+0x30. A safe adapter must verify a unique matching live mission and resolved ID; "
        "do not equate setter return or preview success with successful cancellation.",
        0x5857b5, 0x5857b9, 0x5857bb, 0x58587f,
        0x4eafad, 0x4eaff4, 0x4eb007, 0x4eb013, 0x4eb03a),
    "improve_cancel_envoy": fact(
        "Improve false needs no existing envoy ID in action: base setter only stores value. "
        "False validity requires the outgoing improve relation; effect looks it up and removes it. "
        "The relation base destructor obtains mission from relation+0x30 and calls return path "
        "25a3c0(mission,-1), if server exists, its virtual+0x140 is false, game+0x7485==0 and "
        "mission+0x48 entry pointer exists. Do not independently return that envoy a second time.",
        0x4e99d0, 0x574608, 0x57463c, 0x574658,
        0x573c0b, 0x573c16, 0x573c23, 0xa5bb26, 0xa5bb35, 0xa5bb3f,
        0xa5bb47, 0xa5bb50, 0xa5bb57, 0xa5bb5c,
        unresolved="Meaning of server virtual+0x140 and game+0x7485 is not inferred; these predicates can suppress the destructor's envoy-return path."),
    "cancel_return_observation": fact(
        "25a3c0 rewrites mission+0x20 to current rawdate, +0x24 to return-arrival date, calls25a680 "
        "to remove/destroy spy task and clears mission+0xa0, then writes associated entry status1. "
        "Busy/returning status1 after cancellation is expected; free-count recovery is delayed. "
        "Spy's accumulated relation+0x18 WORD is not cleared by this task teardown.",
        0x25a638, 0x25a641, 0x25a647, 0x25a66e,
        0x25a69c, 0x25a6ab, 0x25a6c5, 0x25a6c7, 0xaf0a14),
    "new_envoy_and_cooldown_modes": fact(
        "Uses-envoy virtual+0x100 returns value for improve/spy, constant true for guarantee/marriage/vassal. "
        "Thus improve/spy false skip new-envoy allocation and common cooldown, while the other three "
        "cancel modes still use a fresh envoy and normal cooldown. Cancellation is not a universal "
        "free-resource operation. Generic preview must use third argument false and command gate "
        "must remain enabled. These are explicit native mode predicates, not a bypass patch.",
        0x4e4d50, 0x8f440, 0x4ea007, 0x4ea121, 0x4e864f, 0x4e8657,
        0x4e7c86, 0x4e7c90, 0x4e7cec,
        normal_preview_signature="bool(action*,reason_or_null,bool ignore_common_checks=false)"),
    "guarantee_cancel_direction": fact(
        "False guarantee validity finds a nonnull guarantee index entry, but bilateral index presence "
        "alone does not prove actor is guarantor. Adapter should require active relation+0x10 actor "
        "and +0x18 target before exposing revoke_guarantee. Revoke runs removal directly without "
        "an AI acceptance reply; it may incur other native rule effects/costs.",
        0x521b3a, 0x521e68, 0x521e91, 0x520e89, 0x520e8d, 0x5214d5),
    "marriage_cancel": fact(
        "False marriage still evaluates scripted allow conditions and requires existing marriage. "
        "Normal state0/valuefalse takes cancellation rather than request/accept/reject. It needs "
        "a new envoy/cooldown but no target AI acceptance. Retain factory defaults for owned string "
        "and +0x60 force; clone rebuilds these defaults rather than copying a forced override.",
        0x4ef613, 0x4ef641, 0x4ef698, 0x4eed24, 0x4eee31, 0x4eee3c,
        0x4f0850, 0x4f0858, 0x4f085c, 0x4f0864),
    "vassal_cancel": fact(
        "False vassal requires the indexed dependency pointer and one of two native subject-definition "
        "singletons (registry global233ffd8 +58=vassal/+60=client_vassal), then checks relation+45 mask1 truce, conditional "
        "negative prestige, and rejects when actor.overlord==target. This is overlord cancellation, "
        "not subject declaration of independence, and not every subject type. Read dependency+40 "
        "definition and its name; do not accept only a generic subject flag.",
        0x51f086, 0x51f08d, 0x51f091, 0x51f33f, 0x51f393, 0x51f397, 0x51f39c,
        0x51f3a1, 0x51f3e3, 0x51f3ec, 0x51f435, 0x51f453, 0x51f467,
        registry_global_rva="0x233ffd8", permitted_definition_pointer_offsets=[0x58, 0x60],
        singleton_names_statically_verified=True),
    "subject_definition_identity": fact(
        "Registry initialization constructs the exact names vassal and client_vassal and resolves "
        "them through b238b0->b23df0 into registry+58/+60. Dependency serializer reads definition "
        "from relation+40 and its EngineString32 name at definition+10. Definition construction "
        "passes definition+10 to 95110 with counted string length; 95110 writes QWORD length at "
        "name+10, QWORD capacity at name+18, and NUL at data+length. Capacity<16 selects inline "
        "name bytes; otherwise name+0 is the data pointer. Bound length/capacity and require NUL "
        "before treating a read-only observed type name as identity evidence.",
        0xb23ad0, 0xb23ad8, 0xb23ae1, 0xb23af0, 0xb23af8,
        0xb23bcf, 0xb23bd7, 0xb23be4, 0xb23bed, 0xb23bfb, 0xb23c06,
        0xb238e3, 0xb238e8, 0xb23e58,
        0xa62b6c, 0xa62b75, 0xa62b86, 0xa62b8d,
        0xb23439, 0xb2344f, 0xb23453, 0xb23465, 0xb23468, 0xb2346e,
        0x95140, 0x9514c, 0x951a4, 0x951ab, 0x951ba,
        definition_name_offset=0x10, name_length_offset=0x10, name_capacity_offset=0x18,
        name_length_width=8, name_capacity_width=8, inline_capacity_limit_exclusive=16,
        registry_offsets={"vassal": 0x58, "client_vassal": 0x60}),
    "spy_task_list_observation": fact(
        "Target spy owner task list count+500 is DWORD; node+18 is BYTE removed flag. "
        "Owner+504 nonzero causes removal to mark a node instead of unlinking/freeing and "
        "decrementing count immediately. Marked nodes must not be treated as active and their "
        "task pointer may already be stale. List can include other task tokens (2dde check in "
        "add), so only linked active spy task objects of the expected vtable/token establish "
        "the observed mission. A list count alone is never proof of spy activation/removal.",
        0xa22009, 0xa2200c, 0xa22059, 0xa2205d, 0xa2206d,
        0xa220d9, 0xa220e2, 0xa22130,
        owner_count_offset=0x500, owner_count_width=4,
        owner_deferred_removal_flag_offset=0x504, node_removed_offset=0x18,
        node_removed_width=1),
    "reply_modes": fact(
        "All five normal cancellation variants are unilateral according to +0xd0. Positive marriage "
        "and vassal require native reply handling and must not be initialized as state2 to force "
        "acceptance. Other positive three and all five false variants do not request AI acceptance. "
        "Human/non-AI response routing uses target control state, not merely target!=current player.",
        0x51fa90, 0x51fa96, 0x4e4d50, 0x4e8125, 0x4e812d,
        0x4e81c1, 0x4e81d0, 0x4e82a9,
        cancel_requires_ai_reply=False, positive_reply_actions=["royal_marriage", "vassalaction"]),
    "nonplayer_scope": fact(
        "Common preview indexes actor and recipient from the action's full handles, checks existence, "
        "cooldown/resources and the per-type method. This bounded entry has no equality requirement "
        "against game.current_player. Native AI call sites construct actor=original from AI-owned "
        "country data. This supports candidate nonplayer construction, but does not prove host/client "
        "authority or dispatch for arbitrary countries. Current FRA-only experiments cannot certify "
        "an unrestricted actor API; keep separate world/identity/authorization gates.",
        0x4e9d30, 0x4e9d4d, 0x4e9d51, 0x4e9d75, 0x4e9d92, 0x4ea1a8,
        0x1d59a4, 0x1d59bd, 0x1d59c1,
        multiplayer_mode_verified_by_transport_vtable=False),
    "fresh_dates_clone": fact(
        "Clone copies actor/original/target/envoy/state/value/id, resets flag39, and initially sets "
        "both dates from source+28. Command wrapper then writes clone+2c=current game date. Never "
        "reuse an earlier proposal ID or fabricate response type to cancel a different request.",
        0x574b54, 0x574b72, 0x574b79, 0x574b80, 0x574b88, 0x574b8d,
        0x4e9940, 0x4e9950, 0x4e995c),
}

ENTRIES = [0x586330, 0x4e99d0, 0x574460, 0x5856a0, 0x521ad0, 0x4ef3b0, 0x51f020,
           0x4e9d00, 0x4e8630, 0x4e7c50, 0x4ea820, 0x4e4d50, 0x8f440, 0x8f450,
           0x51fa90, 0x573050, 0xa73740, 0xa5bb00, 0x25a3c0, 0x25a680,
           0xaf09e0, 0x4ed640, 0x520900, 0x4f07d0, 0x1d5930, 0x574b20, 0x4e9930,
           0xa21fc0, 0xa220b0, 0xa62b40, 0xb231f0, 0xb23ab0, 0xb238b0,
           0xb23df0, 0x95110]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-pair-cancel-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit(f"wrong executable SHA: {digest}")
    md, _ = make_disassembler(args.deps_dir)
    functions, all_ins = {}, {}
    for entry in ENTRIES:
        ins, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        records = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                    "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        all_ins.update({r["rva"]: r for r in records})
        functions[hex(entry)] = {"prefix16": pe.bytes_at(entry, 16).hex(), "instructions": records,
                                "decoded_bytes": sum(len(i.bytes) for i in ins), "edges": edges,
                                "runtime_verified": False}
        check_memory_budget()
    for name, claim in FACTS.items():
        absent = [r for r in claim["evidence_rvas"] if r not in all_ins]
        if absent:
            raise SystemExit(f"{name}: non-instruction anchors {absent}")
        claim["evidence_instructions"] = [all_ins[r] for r in claim["evidence_rvas"]]
    for profile in PROFILES:
        profile["runtime_verified"] = False
        profile["native_slot_checks"] = []
        for slot, key in [(0xe0, "setter_rva"), (0x80, "validity_rva"),
                          (0x100, "uses_envoy_rva"), (0xd0, "reply_rva")]:
            actual = pe.u64(pe.to_offset(profile["vtable_rva"] + slot)) - pe.base
            assert actual == profile[key], (profile["name"], hex(slot), hex(actual))
            profile["native_slot_checks"].append({"slot": hex(slot), "target_rva": hex(actual)})
    literals = []
    for rva, expected in [(0x1c52470, "vassal"), (0x1c52478, "client_vassal")]:
        actual = pe.bytes_at(rva, len(expected) + 1)
        assert actual == expected.encode("ascii") + b"\0", (hex(rva), actual)
        literals.append({"rva": hex(rva), "text": expected, "bytes": actual.hex()})
    report = {"schema_version": 1, "binary_sha256": digest,
              "analysis_kind": "reviewed_bounded_static_no_process_access", "runtime_verified": False,
              "profiles": PROFILES, "facts": FACTS, "functions": functions,
              "subject_name_literal_checks": literals,
              "limits": {"per_entry_window_bytes": 0x4000, "per_entry_max_instructions": 4000,
                         "memory_guard_mib": 768, "calls_followed_automatically": False},
              "limitations": ["No cancellation has been executed by this analysis.",
                              "Cancellation parameters are construction evidence, not proof of end-to-end authority or effects.",
                              "Local transport vtable does not independently establish single-player session mode.",
                              "Subject singleton name resolution is static; loaded mods and live relation type still require read-only observation."],
              "summary": {"profiles": len(PROFILES), "facts": len(FACTS), "functions": len(functions),
                          "decoded_bytes_including_overlaps": sum(f["decoded_bytes"] for f in functions.values())}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), **report["summary"]}))


if __name__ == "__main__":
    main()
