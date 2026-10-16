"""Reproduce exact-build, bounded console test-control ABI evidence offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors

CALLBACKS = {"gamespeed": (0x1fce998, 0xe913a0), "savegame": (0x1fc74b8, 0xe7b3e0),
             "run": (0x1fc2558, 0xe4f1d0), "date": (0x1fc2918, 0xe56bb0)}
FUNCTIONS = [0x7579f0, 0x7e01b0, 0x7e0250, 0x95660, 0x6eaa10, 0x8024d0, 0x80ff80,
             0x811aa0, 0x847e30, 0x848350, 0x1558480, 0x1558700, 0x776d80, 0x74a260, 0x74b8a0]


def fact(summary, *rvas, **extra):
    return dict(summary=summary, evidence_rvas=[hex(r) for r in rvas], runtime_verified=False, **extra)


FACTS = {
    "gamespeed_abi": fact(
        "Callback takes an explicit Result40 output pointer in RCX and a read-only vector in RDX. "
        "Result has success BYTE0 and owned String32 at+8; String32 has 16 inline bytes, QWORD "
        "length+10 and QWORD capacity+18. Callback returns the output pointer in RAX. Argument "
        "count is (end-begin)/32 and must equal1. One SSO String32 with one ASCII digit0..5, "
        "length1/capacity15/NUL, in a three-pointer vector is sufficient; no dispatcher needed.",
        0xe913c0, 0xe913c3, 0xe913ce, 0xe913d1, 0xe913d5, 0xe913d9,
        0xe91407, 0xe9140a, 0xe91411, 0xe91415, 0xe914bc, 0xe914c9, 0xe916af,
        signature="Result40* __fastcall(Result40*, const Vector24<String32>*)",
        result_size=40, result_message_offset=8, string_size=32, vector_size=24,
        allowed_integer_inputs=[0, 1, 2, 3, 4, 5]),
    "speed_index_and_pause": fact(
        "Callback accepts unsigned numeric0..5 then calls7579f0, which clamps to0..4 and writes "
        "game+1e08. Therefore inputs4/5 both mean native index4; input1 means index1 (displayed "
        "as index+1), not UI speed1. Callback then uses7e01b0 and toggles7e0250 only when desired "
        "pause differs: input0 requests paused, positive input requests unpaused. Native speed "
        "index alone is not a pause indicator. A success byte reports callback processing, "
        "not evidence that a month passed or a diplomatic action applied.",
        0xe914d0, 0xe914d3, 0xe914de, 0x7579f7, 0x757a00, 0x757a09, 0x757a0d, 0x757a13,
        0xe914e3, 0xe914ef, 0xe91504, 0xe91510, 0xe91515,
        game_speed_offset=0x1e08, width=4, input_to_native_index=[0, 1, 2, 3, 4, 4]),
    "pause_predicate": fact(
        "Server+100 pinned8024d0 returns server+418 pause manager. Predicate7e01b0 returns "
        "true if manager+48 BYTE is set; otherwise it calls6eaa10(manager+50 server), returning "
        "false for native multiplayer=true; otherwise nonempty vector manager+0..+8 implies "
        "paused. Toggle7e0250 changes manager+48 and may clear its pause vector. Read-only "
        "observe reproduces the bounded predicate and never calls these native functions. "
        "This does not turn6eaa10=false into a strict offline-session proof.",
        0x8024d0, 0x7e01b6, 0x7e01cd, 0x7e01d1, 0x7e01da, 0x7e01de,
        0x7e01ee, 0x7e01f3, 0x7e0282, 0x7e02bb, 0x7e02c2,
        manager_offset=0x418, manager_manual_pause_offset=0x48, manager_server_offset=0x50,
        manager_vector_begin_offset=0, manager_vector_end_offset=8),
    "result_ownership": fact(
        "A normally returned Result40 owns its message String32. Validate result pointer, bool "
        "and bounded String32 before calling pinned95660 on result+8. Stack argument String32 "
        "contains only SSO bytes and is not allocated or modified by the callback. An exception "
        "leaves ownership uncertain: no destructor, retry or second native call should follow.",
        0xe91575, 0xe91579, 0xe916af, 0x95660,
        string_destructor_rva="0x95660", post_exception_cleanup=False),
    "savegame_not_filename_api": fact(
        "The savegame callback never reads its argument vector. It constructs a size78 command "
        "with token2df4 savegamecommand and vtable1cba3b8, sends through context transport, and "
        "sets result.success=true even if the transport path is skipped. No filename is supplied. "
        "This is not a safe named-save API and success cannot prove a file exists.",
        0xe7b433, 0xe7b470, 0xe7b47f, 0xe7b486, 0xe7b4de, 0xe7b4e2, 0xe7b553, 0xe7b556,
        callback_reads_filename=False, final_output_path_identified=False,
        overwrite_behavior_verified=False, implemented_in_test_module=False),
    "save_nested_object_is_checksum_settings": fact(
        "The command+50 embedded object vtable1cb1f50 serializes hard_check, local_check, "
        "randomlog, hotjoinlog, randomlog_stack and randomlog_frames; it must not be called "
        "a filename SaveInfo. Command execute847e30 prepares world/checksum state then creates "
        "ready_after_hotjoin token2dd1. This bounded chain does not establish a final filesystem "
        "writer, naming template, collision handling or no-overwrite guarantee. Saving remains "
        "unimplemented until those properties and completion are independently observed.",
        0xe7b492, 0xe7b499, 0x155849c, 0x15584c0, 0x15584e4, 0x1558508,
        0x155852b, 0x1558574, 0x847f6f, 0x848019, 0x8480c2, 0x84811b),
    "load_flags_not_epoch": fact(
        "Read-only observation also returns game+7485 reset BYTE and whether game+74c8 "
        "load-source pointer is nonnull. These are rejection signals when active, not a "
        "monotonic generation nor proof that every load transition has been observed.",
        0x74a289, 0x74b1e8, 0x74b8c8, 0x74ba03),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-test-controls-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit(f"wrong executable SHA: {digest}")
    md, _ = make_disassembler(args.deps_dir)
    funcs, lookup = {}, {}
    for entry in list(dict.fromkeys([v[1] for v in CALLBACKS.values()] + FUNCTIONS)):
        ins, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                 "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        funcs[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(), "instructions": rows,
                             "edges": edges, "decoded_bytes": sum(len(i.bytes) for i in ins),
                             "runtime_verified": False}
        lookup.update({r["rva"]: r for r in rows})
        check_memory_budget()
    for name, claim in FACTS.items():
        missing = [x for x in claim["evidence_rvas"] if x not in lookup]
        if missing:
            raise SystemExit(f"{name}: noninstruction anchors {missing}")
        claim["evidence_instructions"] = [lookup[x] for x in claim["evidence_rvas"]]
    entries = {}
    for name, (slot, callback) in CALLBACKS.items():
        assert pe.u64(pe.to_offset(slot)) == pe.base + callback
        name_rva = pe.u64(pe.to_offset(slot - 0x30)) - pe.base
        actual_name = pe.bytes_at(name_rva, 64).split(b"\0")[0].decode("ascii")
        assert actual_name == name, (name, actual_name)
        entries[name] = {"registration_function_slot": hex(slot), "callback": hex(callback),
                         "registration_name_rva": hex(name_rva), "name_verified": actual_name,
                         "instructions": funcs[hex(callback)]["instructions"],
                         "runtime_verified": False}
    tokens = token_descriptors(pe)
    report = {"schema_version": 2, "game_sha256": digest, "runtime_verified": False,
              "status": "reviewed_bounded_static_no_process_access", "entries": entries,
              "functions": funcs, "facts": FACTS,
              "nested_checksum_tokens": {hex(i): tokens[i] for i in range(0x2cf, 0x2d5)},
              "implemented_private_controls": ["gamespeed_integer_0_to_5", "read_only_observe"],
              "not_implemented": ["savegame", "run", "date", "arbitrary_console_or_script"],
              "limits": {"per_entry_window_bytes": 0x4000, "per_entry_max_instructions": 4000,
                         "memory_guard_mib": 768, "calls_followed_automatically": False},
              "summary": {"functions": len(funcs), "facts": len(FACTS),
                          "decoded_bytes_including_overlaps": sum(f["decoded_bytes"] for f in funcs.values())}}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), **report["summary"]}))


if __name__ == "__main__":
    main()
