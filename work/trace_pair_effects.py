"""Reproduce bounded offline evidence for five EU4 1.37.5 diplomacy effects.

No process access, native calls, injected code or runtime assertions. Reads the
disk PE, checks its exact SHA, and disassembles only the reviewed entry points.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg


def fact(summary, *evidence, **details):
    return dict(summary=summary, evidence_rvas=[hex(x) for x in evidence],
                runtime_verified=False, **details)


FACTS = {
    "relation_lookup": fact(
        "country+0x1510 is the relation-record array; record stride 0x48. "
        "record+0 points to the owner's index root, record+0x10 is the other country handle. "
        "Each selected index uses 16-byte elements {int32 country_slot at +0, relation pointer at +8}.",
        0xa6a350, 0xa6a353, 0xa6a35c, 0xa6a363, 0xa6a376, 0xa6a386,
        record_stride=0x48, root_pointer_offset=0, other_handle_offset=0x10,
        item_stride=16, item_slot_offset=0, item_pointer_offset=8,
        indexes={
            "royal_marriage": {"pointer_offset": 0x68, "count_offset": 0x74, "getter_rva": "0xa68be0"},
            "vassal": {"pointer_offset": 0x128, "count_offset": 0x134, "getter_rva": "0xa69970"},
            "guarantee": {"pointer_offset": 0x1a0, "count_offset": 0x1ac, "getter_rva": "0xa6a050"},
            "improve_outgoing": {"pointer_offset": 0x1d0, "count_offset": 0x1dc, "getter_rva": "0xa6a350"},
            "improve_incoming": {"pointer_offset": 0x1e8, "count_offset": 0x1f4,
                                 "evidence": "setter a6a390 uses root+1e0 container; getter a6a450"},
        }),
    "relation_common": fact(
        "Effect relationship objects have actor at +0x10, target at +0x18 and start rawdate at +0x20. "
        "+0x28 is written zero by apply and one by removal. Removal can immediately free the object; "
        "re-resolve the index after each snapshot instead of retaining a removed pointer.",
        0x520e89, 0x520e8d, 0x520e91, 0xa5f2bb, 0xa5f36f,
        actor_offset=0x10, target_offset=0x18, start_date_offset=0x20, removed_byte_offset=0x28,
        sizes={"improve": 0x48, "guarantee": 0x48, "marriage": 0x40, "vassal": 0x90},
        vtable_rvas={"improve": "0x1c81658", "guarantee": "0x1c817d8",
                     "marriage": "0x1c80be0", "vassal": "0x1c81758"}),
    "improve_apply": fact(
        "value=true creates the improve relation; actor->target outgoing index and target->actor "
        "incoming index reference the same directional object. Common settlement links its +0x30 "
        "to the actor's selected diplomat mission. This is stronger evidence than free-count decline.",
        0x573070, 0x573114, 0x573118, 0x57311c, 0x573129, 0x573135,
        0xa73593, 0xa735d4, 0xa73718, 0x4eae63, 0x4eaf12,
        mission_pointer_offset=0x30, actor_index="improve_outgoing", target_index="improve_incoming"),
    "improve_cancel": fact(
        "value=false finds the actor->target outgoing relation, unregisters it, clears outgoing "
        "and reverse incoming indexes, sets removed and frees the 0x48 object. Opinion accumulated "
        "before cancellation is a separate quantity and is not proof that the task still exists.",
        0x573c0b, 0x573c16, 0x573c23, 0x573c30, 0xa7379a, 0xa737da, 0xa737df),
    "guarantee_apply_cancel": fact(
        "value=true creates actor-guarantees-target object; both bilateral guarantee indexes "
        "reference it, so map membership alone cannot establish direction. value=false removes "
        "the indexed object. Verify object actor/target handles and +0x28=0 while it is registered.",
        0x520e3d, 0x520e89, 0x520e8d, 0x520ea6, 0x520eb2,
        0xa5f275, 0xa5f2b6, 0xa5f2bb, 0x52144a, 0x5214d5, 0xa5f32a, 0xa5f36a, 0xa5f36f),
    "marriage_accept_cancel": fact(
        "Positive marriage only creates the relation for action+0x34==2 (accepted response). "
        "state=1 takes rejection handling; initial state=0,value=true does not create marriage. "
        "Initial state=0,value=false removes the marriage from both indexes.",
        0x4edb77, 0x4edb7a, 0x4edb83, 0x4edbc7, 0x4edbcb, 0x4edbd6,
        0x4ee7e4, 0x4eed24, 0x4eee31, 0x4eee3c, 0xa5eb15, 0xa5eb52, 0xa5f00c),
    "vassal_accept_cancel": fact(
        "Positive vassal action only creates dependency for state=2,value=true. Creation passes "
        "actor as overlord and target as subject. Its 0x90 relation has a subject-definition pointer "
        "at +0x40. Cancel value=false removes the existing relation and refreshes both countries' "
        "overlord fields. A dependency-type name is needed to distinguish vassal from other subjects.",
        0x51dce2, 0x51dce5, 0x51dcee, 0x51dd37, 0x51dd3a, 0x51dd3d,
        0x4e5d55, 0x4e5da2, 0x4e5da6, 0x4e5dc3, 0xa601c4, 0xa601cc,
        0x51e6fe, 0x51ed90, 0x51ed9b, 0xa61b41, 0xa61b54, 0xa61b5c, 0xa61b64,
        type_definition_pointer_offset=0x40, type_name_engine_string_offset=0x10),
    "overlord_observation": fact(
        "country+0x18f0 is refreshed from directional dependency objects: first invalidated, then "
        "set to the country whose handle matches relationship+0x10. +0x18f7 is the handle validity byte. "
        "Observe target.overlord==actor together with the correct active dependency relation/type; "
        "actor's subject vector at +0x1a18..+0x1a20 is updated too.",
        0x36c7b3, 0x36c855, 0x36c861, 0x36c89d, 0x36c96d, 0x36c9bf, 0x36c9df,
        country_overlord_handle_offset=0x18f0, subject_vector_begin_offset=0x1a18,
        subject_vector_end_offset=0x1a20),
    "envoy_mission_identity": fact(
        "Actor diplomat manager vector contains entry pointers; entry+0x44 is ID and +0x10 mission. "
        "Mission vtable is 0x1c4b2b8, +0x80 actor, +0x88 target, +0xa8 action token, +0x50 envoy ID, "
        "+0x48 entry pointer. Initial +0x20 comes from action date; +0x24 is computed travel end. "
        "These dates are overwritten when returning, not immutable send timestamps.",
        0x4e758a, 0x4e7595, 0x4e75f0, 0x4e77bc, 0x4e77c3,
        0x4e780e, 0x4e7811, 0x4e7879, 0x4e787c, 0x25a638, 0x25a641,
        mission_vtable_rva="0x1c4b2b8", entry_mission_offset=0x10, entry_status_byte_offset=0x18,
        entry_id_offset=0x44, actor_offset=0x80, target_offset=0x88, action_token_offset=0xa8,
        envoy_id_offset=0x50, entry_pointer_offset=0x48, start_date_offset=0x20,
        travel_end_date_offset=0x24, spy_task_pointer_offset=0xa0,
        tokens={"improve_relation": "0x2ddb", "spy_network": "0x3378",
                "guaranteeaction": "0x2941", "royal_marriage": "0x28df", "vassalaction": "0x2940"}),
    "envoy_status_limit": fact(
        "Creation can set status byte 1; settlement of persistent missions sets 2. Returning "
        "missions can remain present/busy. Status and count are supporting observations only, "
        "not an action-type discriminator or proof of acceptance.",
        0x4e77d7, 0x4eacec, 0x25a647),
    "spy_apply": fact(
        "Common settlement creates token 0x3378 task vtable 0x1ce3ba0,size 0x50, links mission+0xa0, "
        "writes task+0x2c envoy ID and task+0x18 actor, task+0x20 target. Setter ORs 0x08 in "
        "actor->target relation+0x46. The target country's +0x14b0 object owns task list head+0x4f0, "
        "tail+0x4f8,count+0x500. This object must not be mistaken for the country itself.",
        0x4ebd9e, 0xaf04b5, 0xaf050c, 0xaf0531, 0x4eaf57, 0x4eaf61,
        0x4eaf6e, 0x4eaf81, 0xaf096b, 0xaf0995, 0xa2204a, 0xa22063, 0xa2206d, 0xa2208b,
        task_vtable_rva="0x1ce3ba0", task_size=0x50, owner_pointer_offset=0x10,
        actor_offset=0x18, target_offset=0x20, removed_byte_offset=0x28, envoy_id_offset=0x2c,
        relation_active_byte_offset=0x46, relation_active_mask=8,
        country_list_owner_pointer_offset=0x14b0, list_head_offset=0x4f0,
        list_tail_offset=0x4f8, list_count_offset=0x500),
    "spy_growth_cancel": fact(
        "Task+0x58 virtual af0880 updates actor->target relation+0x18 signed WORD and clamps to "
        "0..10000. Public/display scaling is not proven by this function alone. Cancellation calls "
        "return path 25a3c0, then 25a680 removes task from list, calls task+0x80 (af09e0 clears bit8), "
        "destroys task and clears mission+0xa0. This does not zero accumulated network size.",
        0xaf0922, 0xaf0933, 0xaf0938, 0xaf0949, 0x4eb03a, 0x25a647,
        0x25a69c, 0x25a6ab, 0x25a6c5, 0x25a6c7, 0xaf0a14,
        relation_size_offset=0x18, width_bytes=2, signed=True, stored_range=[0, 10000]),
    "reply_state_machine": fact(
        "For state=0,response-required actions, the AI path clones then calls +0xb8; that wrapper "
        "calls +0x120 and returns score>=1. It writes response clone+0x34 = 1 + accepted, wraps and "
        "submits a response command. State 1 is rejection and 2 acceptance. Guarantee/improve/spy "
        "have +0xd0=false; marriage+0xd0 returns value; vassal returns state==0 && value. "
        "The two negotiated actions may also be queued for a human reply.",
        0x4e81c1, 0x4e81c9, 0x4e81cb, 0x4e81ce, 0x4e81d0, 0x4e81e7, 0x4e81ed,
        0x4ea256, 0x4ea261, 0x4ea269, 0x51fa90, 0x51fa96,
        action_state_offset=0x34, request_state=0, rejected_state=1, accepted_state=2,
        ai_score_rvas={"vassalaction": "0x51fab0", "royal_marriage": "0x4f0bf0"},
        limitation="AI score functions include native game rules and optional console-cheat branch; do not replace them with a hardcoded acceptance formula."),
    "pending_reply_queue": fact(
        "Human/pending recipient country queue uses +0x18d8 head,+0x18e0 tail,+0x18e8 DWORDcount. "
        "Node +0 action,+8 previous,+0x10 next,+0x18 deleted byte. Queued clone receives +0x3c "
        "ID and +0x2c current rawdate. A matching queued state=0 action means pending, not accepted. "
        "Queue disappearance without observing a response is not proof of rejection.",
        0x4e82a9, 0x4e82b9, 0x4e82bc, 0x4e82cd, 0x4e82d0, 0x4e82d4,
        0x4e82d8, 0x4e82dc, 0x4e82ec, 0x4e82f6, 0x4e82fc,
        country_head_offset=0x18d8, country_tail_offset=0x18e0, country_count_offset=0x18e8,
        node_action_offset=0, node_previous_offset=8, node_next_offset=0x10, node_deleted_offset=0x18,
        action_id_offset=0x3c, action_command_date_offset=0x2c),
    "non_proofs": fact(
        "Transport return, consumed command container, cooldown update, fewer free diplomats, "
        "dirty cache byte and absence of a relationship are not individually effect/accept/reject proof. "
        "Several relationship setters OR relation+0x46 with 4 and set country+0x2884=1 on both "
        "addition and removal; these are refresh markers, not active guarantee/marriage bits.",
        0xa69f30, 0xa69f5d, 0xa68b37, 0xa68b5a),
}

ENTRIES = [
    0x4ea820, 0x4e7c50, 0x4ea1e0, 0x4ebd80, 0x4e7550, 0x257a40,
    0x25a3c0, 0x25a680, 0x6ff570, 0x573050, 0xa73540, 0xa73740,
    0xa6a250, 0xa6a350, 0xa6a390, 0xa6a450, 0x520900, 0x4e4b60,
    0xa5f230, 0xa5f2d0, 0xa69ed0, 0xa6a050, 0x4ed640, 0x4ef2f0,
    0xa5e270, 0xa5eaa0, 0xa68a80, 0xa68be0, 0x51d810, 0x51fa90,
    0x51fab0, 0x4f0bf0, 0x4e6e00, 0x4e5630, 0xa5ff20, 0xa61420,
    0xa61900, 0x28bd00, 0xa69970, 0x36c730, 0x585640, 0xaf04a0,
    0xaf0960, 0xaf09e0, 0xaf0880, 0xaf06d0, 0xa21fc0,
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-pair-effects-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit(f"wrong executable SHA: {digest}")
    md, _ = make_disassembler(args.deps_dir)
    # Resolve RIP-relative LEAs mechanically; do not trust hand-added addresses.
    vtable_checks = {}
    for name, rva, expected in [
        ("improve", 0x5730e4, 0x1c81658), ("guarantee", 0x4e4ba8, 0x1c817d8),
        ("marriage", 0x4ef338, 0x1c80be0), ("vassal", 0x4e5d4b, 0x1c81758),
        ("mission", 0x257a58, 0x1c4b2b8), ("spy_task", 0xaf0531, 0x1ce3ba0),
    ]:
        instruction = next(md.disasm(pe.bytes_at(rva, 16), rva, count=1))
        assert instruction.mnemonic == "lea" and "rip" in instruction.op_str
        target = instruction.address + instruction.size + instruction.operands[-1].mem.disp
        assert target == expected, (name, hex(target), hex(expected))
        vtable_checks[name] = {"constructor_instruction_rva": hex(rva),
                              "constructor_instruction_bytes": instruction.bytes.hex(),
                              "computed_vtable_rva": hex(target),
                              "deleting_destructor_rva": hex(pe.u64(pe.to_offset(target)) - pe.base)}
    functions = {}
    all_instructions = {}
    for entry in ENTRIES:
        ins, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        records = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                    "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        all_instructions.update({record["rva"]: record for record in records})
        functions[hex(entry)] = {"prefix16": pe.bytes_at(entry, 16).hex(),
                                 "decoded_bytes": sum(len(i.bytes) for i in ins),
                                 "instructions": records, "edges": edges,
                                 "runtime_verified": False}
        check_memory_budget()
    for name, claim in FACTS.items():
        absent = [r for r in claim["evidence_rvas"] if r not in all_instructions]
        if absent:
            raise SystemExit(f"{name}: non-instruction evidence anchors {absent}")
        claim["evidence_instructions"] = [all_instructions[r] for r in claim["evidence_rvas"]]
    report = {
        "schema_version": 1, "binary": {"sha256": digest, "preferred_base": hex(pe.base)},
        "evidence_level": "reviewed_bounded_static_control_flow", "runtime_verified": False,
        "scope": "five core effects; no process access and no engine calls",
        "limits": {"per_entry_window_bytes": 0x4000, "per_entry_max_instructions": 4000,
                   "memory_guard_mib": 768, "calls_followed_automatically": False,
                   "note": "Direct branches inside the bounded window are followed; indirect calls and branches remain evidence edges. UI/script side effects are not exhaustively modeled."},
        "facts": FACTS, "vtable_checks": vtable_checks, "functions": functions,
        "summary": {"facts": len(FACTS), "functions": len(functions),
                    "decoded_bytes_including_overlapping_entries": sum(f["decoded_bytes"] for f in functions.values())},
        "acceptance_requirements": [
            "Pin executable/module, validate full current country handles and re-resolve all pointers each snapshot.",
            "Record before/after same-pair relationship objects, vtables, actor/target, active byte, start rawdate and type.",
            "For persistent missions, correlate selected diplomat ID, mission token/handles, relationship/task pointer and active bit.",
            "For negotiated actions, record pending action ID and observed response state; persistent relationship proves resulting state only.",
            "A cancelled relation/task must disappear from its live indexes; do not dereference the freed prior pointer.",
            "Bound every vector/list count, verify stable snapshots and readable pointers; uncertain/inconsistent reads stay unknown.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "bytes": args.output.stat().st_size, **report["summary"]}))


if __name__ == "__main__":
    main()
