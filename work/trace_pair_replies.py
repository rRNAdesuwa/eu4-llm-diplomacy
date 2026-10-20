"""Bounded, exact-build offline evidence for normal diplomatic AI replies."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

ENTRIES = [0x4e7c50, 0x4e8630, 0x4ea1e0, 0x2cd570, 0xb52e0, 0x76b480,
           0x360970, 0x3607c0, 0x3608d0, 0x2ee280, 0xcf4e0,
           0x51fab0, 0x38e6e0, 0x4f0bf0, 0x4ef3b0, 0x51f020,
           0x4e4d50, 0x51fa90, 0x8f450,
           0x4ed640, 0x51d810, 0x8bf160, 0x8c0460, 0x8d4660,
           0x8c1b10, 0x8c07b0, 0x80e670, 0x1241af0, 0x1af350]


def fact(summary, *anchors, **extra):
    return dict(summary=summary, anchors=list(anchors), **extra)


FACTS = {
    "ai_reply_is_generated_during_execute": fact(
        "After initial action settlement, command execute requires state0 and action+d0=true. "
        "It selects immediate AI evaluation only if game.control vector is nonempty, target slot "
        "DWORD is0, and target country2cd570 returns true. It clones, calls+b8, writes state1 or2, "
        "wraps and enqueues a reply command. This decision path contains no pause/date-arrival "
        "test and is not deferred to a daily AI update. The reply is another command, so this "
        "does not prove same-frame delivery or a paused command-pump contract.",
        0x4e8054, 0x4e805d, 0x4e8125, 0x4e8142, 0x4e8149, 0x4e8159,
        0x4e816c, 0x4e8188, 0x4e818f, 0x4e819b, 0x4e81c1, 0x4e81d0,
        0x4e81e7, 0x4e81ed,
        game_control_begin=0x1d48, game_control_end=0x1d50, control_entry_width=4,
        reply_states={"request": 0, "rejected": 1, "accepted": 2},
        paused_delivery_runtime_verified=False),
    "normal_reply_mode": fact(
        "Marriage+d0 returns the value byte; vassal+d0 returns state0 && value. Their+f0 "
        "method is the constant-false8f450, so the immediate AI branch normally calls+b8 "
        "rather than selecting its unconditional acceptance branch. False/cancel modes do "
        "not negotiate AI consent.",
        0x4e4d50, 0x51fa90, 0x51fa96, 0x8f450, 0x4e81af, 0x4e81b7,
        positive_actions=["royal_marriage", "vassalaction"], cancel_requires_reply=False),
    "native_ai_gate": fact(
        "2cd570 requires country+3d0 nonnull and b52e0 true. b52e0 requires that object's "
        "+80 byte be nonzero, resolves its country handle+20 through the country DB, requires "
        "resolved country+2458 object's byte+18==0, and game+74d0!=0. Preserve these native "
        "gates. The field names beyond their read predicate are not independently established. "
        "A false gate on the control-slot0 route returns without adding a human pending node.",
        0x2cd574, 0x2cd580, 0xb52e0, 0xb52e9, 0xb5307, 0xb530e, 0xb5321,
        0x4e818f,
        country_ai_object_offset=0x3d0, ai_object_handle_offset=0x20,
        ai_object_flag_offset=0x80, country_secondary_offset=0x2458,
        secondary_flag_offset=0x18, game_flag_offset=0x74d0),
    "native_score_is_separate_from_legality": fact(
        "Both actions use+b8=4ea1e0, which invokes derived+120 and accepts signed score>=1. "
        "Marriage score is4f0bf0; vassal51fab0 delegates to country38e6e0. Both contain a "
        "game+23a1/current-player override returning99999; it must not be enabled/used as a "
        "test shortcut. Legality does not imply AI acceptance. This report records score "
        "code and label evidence without replacing the complete native scoring formula.",
        0x4ea256, 0x4ea261, 0x4ea269, 0x4f0c36, 0x4f0c8a,
        0x51faca, 0x51fb20, 0x51fb55,
        acceptance_threshold=1, marriage_score_rva="0x4f0bf0", vassal_score_rva="0x51fab0",
        vassal_country_score_rva="0x38e6e0", force_or_cheat_implemented=False),
    "reply_rechecks_rules_and_skips_initial_cooldown": fact(
        "Command gate skips the initial cooldown comparison when state!=0; it still invokes "
        "derived validity+80. Command execute also invokes derived validity+80 before effects. "
        "Thus accepted score only creates an accepted reply; changed legality can still prevent "
        "its effect. Never initialize a user request as state2 or bypass validity/cooldown.",
        0x4e8646, 0x4e864a, 0x4e869c, 0x4e8775, 0x4e7c71, 0x4e7c80,
        validity_rvas={"royal_marriage": "0x4ef3b0", "vassalaction": "0x51f020"}),
    "pending_queue_and_request_id": fact(
        "The other route adds a recipient pending node only for a non-special state0, reply-required "
        "clone with requestID0. It allocates an ID and stores current rawdate in+2c. AI immediate "
        "clones take the earlier route and can retain requestID0: a nonzero ID is not universal. "
        "Observe pending nodes by full handles/token/value/state/date/ID with bounded stable traversal.",
        0x4e8225, 0x4e8251, 0x4e8262, 0x4e827e, 0x4e82a4, 0x4e82a9,
        0x4e82b9, 0x4e82cd, 0x4e82d0, 0x4e82d4, 0x4e82d8, 0x4e82dc,
        0x4e82ec, 0x4e82fc,
        country_fields={"head": 0x18d8, "tail": 0x18e0, "count_dword": 0x18e8, "iteration_byte": 0x18ec},
        node_fields={"action": 0, "previous": 8, "next": 0x10, "deleted_byte": 0x18},
        action_request_id_dword=0x3c, action_queue_rawdate_dword=0x2c),
    "queue_disappearance_is_not_rejection": fact(
        "Reply execution removes a pending ID from actor or target via360970. That method destroys "
        "the action before marking node+18 if iteration is active; marked nodes can retain dangling "
        "action pointers. Skip marked nodes without dereferencing their action. Separate3607c0 "
        "prunes invalid/nonpending actions and3608d0 clears the whole list. None is rejection evidence.",
        0x4e801c, 0x4e804b, 0x360993, 0x3609bb, 0x3609bd, 0x3609c6,
        0x360a1e, 0x3607f5, 0x36081e, 0x360848, 0x36090e, 0x36095b),
    "three_day_ai_queue_expiry": fact(
        "Country update2ee280 has a separate cleanup branch gated by game+7484!=0 and control-slot0. "
        "It copies action+2c, adds3*24 raw units throughcf4e0, and destroys/removes the node only "
        "when current rawdate is strictly greater. This branch does not write reply state1 or emit "
        "a rejection. Its full scheduler frequency is not established here.",
        0x2ef4b8, 0x2ef4bf, 0x2f0401, 0x2f0416, 0x2f041d, 0x2f0443,
        0x2f044c, 0x2f0458, 0x2f0463, 0x2f0469, 0x2f0487, 0x2f04be,
        0xcf4e0, 0xcf4e3, 0xcf4e6, expiry_rawdate_delta=72,
        scheduler_frequency_verified=False),
    "accept_reject_notification_keys": fact(
        "Marriage and vassal effect branches distinguish state2 acceptance from state1 rejection. "
        "For original actor matching the current player they resolve ROYMARACCEPT/ROYMARREJECT "
        "or VASALLACCEPT/VASALLREJECT and dispatch an8d4660 message through8c1b10. Recipient "
        "and third-party perspectives use WE/OTHER variants. Exact messages are positive "
        "evidence of reply-effect processing, but message absence is not a negative result.",
        0x4edb77, 0x4edb7a, 0x4edf9c, 0x4ee7e4, 0x4ee827, 0x4ee8ad,
        0x4ee902, 0x4ee90d, 0x4eea18, 0x4eeb78, 0x51dce2, 0x51dce5,
        0x51ddf7, 0x51e195, 0x51e19e, 0x51e1dc, 0x51e25f, 0x51e2ab,
        0x51e2b6, 0x51e3a7, 0x51e543,
        keys={"marriage_accept": ["ROYMARACCEPT", "ROYMARWEACCEPT", "ROYMARACCEPTOTHER"],
              "marriage_reject": ["ROYMARREJECT", "ROYMARWEREJECT", "ROYMARREJECTOTHER"],
              "vassal_accept": ["VASALLACCEPT", "VASALLWEACCEPT", "VASALLACCEPTOTHER"],
              "vassal_reject": ["VASALLREJECT", "VASALLWEREJECT", "VASALLREJECTOTHER"]}),
    "message_identity_fields": fact(
        "8d4660 stores definition+8, actor handle+28, target handle+30 and game rawdate+88. "
        "Definition lookup8c0460 compares its EngineString32 at+38. Message moves1af350 preserve "
        "these identity fields. Standard message vtable is1c426e0; callback-owning history "
        "variant is1cc1ca0. No per-request ID is preserved in these identified fields; notification "
        "correlation is pair/type/date and new history-node observation, not exact request-ID proof.",
        0x4ed6b0, 0x4ed83f, 0x4ee8e5, 0x4ee8f4,
        0x51d87f, 0x51d9d7, 0x51e28e, 0x51e29d,
        0x8d4681, 0x8d46bc, 0x8d46c0, 0x8d474f, 0x8d4756,
        0x8c04e3, 0x8c04f3, 0x8c04f7, 0x8c0501, 0x8c0f0d,
        0x1af361, 0x1af393, 0x1af39b, 0x1af407,
        message_fields={"definition": 8, "actor_handle": 0x28, "target_handle": 0x30, "rawdate_dword": 0x88},
        definition_name_string32_offset=0x38, correlation="pair_type_date_new_node_not_request_id"),
    "message_history_readonly_path": fact(
        "When server+1178 is nonnull, pinned server virtual+228=80e670 forwards to server+12d0 "
        "history manager1241af0. Its head+10/tail+18/count DWORD+20 list stores 28-byte nodes: "
        "message+0, shared-control+8, previous+10,next+18,removed BYTE+20. Insertion keeps the "
        "message alive through shared ownership and caps normal count at200 by removing oldest nodes. "
        "Do not invoke methods or alter shared-reference counts in an observer.",
        0x80e670, 0x80e67a, 0x80e684, 0x1241b17, 0x1241b51, 0x1241b5f,
        0x1241bf4, 0x1241bf8, 0x1241c1f, 0x1241c22, 0x1241c26,
        0x1241c2a, 0x1241c2e, 0x1241c32, 0x1241c3c, 0x1241c49,
        0x1241c4d, 0x1241c65, 0x1241c82, 0x1241c87,
        server_vtable_rva="0x1cb8460", server_history_offset=0x12d0, server_ui_guard_offset=0x1178,
        manager_fields={"head": 0x10, "tail": 0x18, "count_dword": 0x20, "iteration_byte": 0x24},
        node_fields={"message": 0, "shared_control": 8, "previous": 0x10, "next": 0x18, "removed_byte": 0x20},
        node_size=0x28, normal_history_cap=200),
    "notification_filtering_limits": fact(
        "8c07b0 can drop presentation when observer/special player mode, missing server, handler+48=0, "
        "game+74e0=0 or settings lookup fails. History insertion additionally requires settings+11. "
        "Popup/pause settings+12/+13 are separate from history. Therefore a response can execute "
        "without visible or retained notification. The report does not change message settings.",
        0x8c07f5, 0x8c0802, 0x8c080f, 0x8c0819, 0x8c0826, 0x8c0831,
        0x8c0842, 0x8c0848, 0x8c0e24, 0x8c0fb1,
        history_optional=True, missing_message_outcome="unknown"),
}


def inspect(pe, md, entry):
    instructions, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
    records = []
    for i in instructions:
        row = dict(rva=hex(i.address), bytes=i.bytes.hex(), instruction=f"{i.mnemonic} {i.op_str}".strip())
        for op in i.operands:
            if op.type == 3 and i.reg_name(op.mem.base) == "rip":
                target = i.address + i.size + op.mem.disp
                row["rip_target"] = hex(target)
                try:
                    raw = pe.bytes_at(target, 128).split(b"\0", 1)[0]
                    if len(raw) >= 3 and all(32 <= x < 127 for x in raw): row["ascii_candidate"] = raw.decode("ascii")
                except (ValueError, KeyError):
                    pass
        records.append(row)
    return dict(prefix32=pe.bytes_at(entry, 32).hex(), instructions=records, edges=edges,
                decoded_bytes=sum(len(i.bytes) for i in instructions), runtime_verified=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--inspect", type=lambda x: int(x, 0), nargs="*")
    ap.add_argument("--offset-refs", type=lambda x: int(x, 0), nargs="*")
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-pair-replies-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA: raise SystemExit("executable SHA256 mismatch")
    md, _ = make_disassembler(args.deps_dir)
    if args.offset_refs:
        for offset in args.offset_refs:
            needle = struct.pack("<I", offset)
            hits = []
            position = 0
            while (position := pe.data.find(needle, position)) != -1:
                try:
                    rva = pe.to_rva(position)
                    fn = pe.function(rva)
                    if fn: hits.append(dict(candidate_rva=hex(rva), function=hex(fn[0])))
                except ValueError: pass
                position += 1
            print(json.dumps(dict(displacement_candidate=hex(offset), refs=hits)))
        return
    if args.inspect is not None:
        for entry in args.inspect:
            print("FUNCTION", hex(entry))
            for row in inspect(pe, md, entry)["instructions"]:
                print(row["rva"], row["instruction"], row.get("ascii_candidate", ""))
        return
    # Explicitly resolve one known 16-case switch. Never follow arbitrary indirect branches.
    switch_entries = sorted({pe.u32(pe.to_offset(0x8c1d14 + i * 4)) for i in range(16)})
    if not all(0x8c1b69 <= entry <= 0x8c1c94 for entry in switch_entries):
        raise SystemExit("message switch targets outside reviewed function")
    functions = {}
    records = {}
    for entry in sorted(set(ENTRIES + switch_entries)):
        f = inspect(pe, md, entry)
        functions[hex(entry)] = f
        records.update((r["rva"], r) for r in f["instructions"])
        check_memory_budget()
    for name, fact in FACTS.items():
        fact["runtime_verified"] = False
        fact["evidence_instructions"] = [records[hex(r)] for r in fact["anchors"]]
    vtable_checks = {}
    for name, address, expected in [("base_message", 0x8d4674, 0x1c426e0),
                                    ("moved_message", 0x1af353, 0x1c426e0),
                                    ("history_callback_message", 0x8c0f02, 0x1cc1ca0)]:
        i = next(md.disasm(pe.bytes_at(address, 16), address, count=1))
        target = i.address + i.size + i.operands[-1].mem.disp
        assert i.mnemonic == "lea" and target == expected
        vtable_checks[name] = dict(instruction_rva=hex(address), instruction_bytes=i.bytes.hex(),
                                  computed_vtable_rva=hex(target),
                                  destructor_rva=hex(pe.u64(pe.to_offset(target)) - pe.base))
    assert pe.u64(pe.to_offset(0x1cb8460 + 0x228)) - pe.base == 0x80e670
    action_slots = {}
    for name, vt, score in [("royal_marriage", 0x1c80ab0, 0x4f0bf0), ("vassalaction", 0x1c7fd20, 0x51fab0)]:
        slots = {hex(slot): hex(pe.u64(pe.to_offset(vt + slot)) - pe.base) for slot in [0x48, 0x80, 0xb8, 0xd0, 0xf0, 0x120]}
        assert slots["0xb8"] == "0x4ea1e0" and slots["0xf0"] == "0x8f450" and slots["0x120"] == hex(score)
        action_slots[name] = dict(vtable_rva=hex(vt), slots=slots)
    report = dict(schema_version=1, binary=dict(sha256=digest, preferred_base=hex(pe.base)),
                  runtime_verified=False, evidence_level="reviewed_bounded_static_control_flow",
                  scope="Normal AI/pending diplomatic replies; no process access or native calls",
                  limits=dict(window_bytes=0x4000, max_instructions_per_entry=4000,
                              memory_guard_mib=768, calls_followed_automatically=False),
                  facts=FACTS, functions=functions, vtable_checks=vtable_checks, action_slots=action_slots,
                  explicit_message_switch=dict(table_rva="0x8c1d14", entries=[hex(x) for x in switch_entries]),
                  score_label_candidates={hex(e): sorted({r["ascii_candidate"] for r in functions[hex(e)]["instructions"]
                                                          if r.get("ascii_candidate", "").startswith("DIPLO_")})
                                          for e in [0x4f0bf0, 0x38e6e0]},
                  limitations=["No native functions called and no process accessed.",
                               "No paused command-pump scheduler proof or complete UI/AI scheduling reconstruction.",
                               "Message settings can suppress or evict history; missing nodes are never rejection evidence.",
                               "A new notification has pair/type/date correlation but no recovered exact request ID.",
                               "Full scoring formula is not reimplemented and no state/force/cheat fields are written."])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(path=str(args.output), sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                          functions=len(functions), bytes=args.output.stat().st_size)))


if __name__ == "__main__": main()
