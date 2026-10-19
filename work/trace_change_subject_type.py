"""Bounded, disk-only EU4 1.37.5 change_subject_type evidence.

The effect factory is a large switch. Decode only the exact routing blocks and
case, plus bounded small callees. This is not an implementation or a runtime test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg


# Exact block ends exclude neighboring cases and jump-table data.
BLOCKS = [
    (0x5dec50, 0x5dec90), (0x5e16d0, 0x5e16e3),
    (0x5e1b52, 0x5e1b65), (0x5e1e4b, 0x5e1e5e),
    (0x5e2233, 0x5e2246), (0x5e26d4, 0x5e26e7),
    (0x5e2ad8, 0x5e2aeb), (0x5e307a, 0x5e308d),
    (0x5e3408, 0x5e341b), (0x5e39fe, 0x5e3a40),
    (0x5e3d04, 0x5e3d21), (0x5e4304, 0x5e432a),
    (0x5e4f05, 0x5e4f33), (0x205cd5, 0x205d90),
    (0x1403af0, 0x1403b18), (0x1403c8f, 0x1403ca2),
    (0x140423a, 0x1404252),
]
FUNCTIONS = [0x5de6c0, 0x5de770, 0xdda5d0, 0xdda140, 0xdda590,
             0x43ebd0, 0x8f440, 0x5ef140, 0x5ed800]
TOKENS = {
    "change_subject_type": (0x3bc6, 0x22c4680),
    "subject_type": (0x352a, 0x21e1088),
    "set_country_subject_type": (0x3bb3, 0x22c1fe8),
    "upgrade_subject_type": (0x3bb9, 0x22c2c18),
}


def fact(summary, *rvas, **extra):
    return {"summary": summary, "evidence_rvas": [hex(r) for r in rvas],
            "runtime_verified": False, **extra}


FACTS = {
    "factory": fact(
        "Generic effect factory5dec50 compares token3bc6 through the recorded routing "
        "blocks. Its final two-level switch selects5e3d04, allocates0x58 and calls "
        "5de6c0. Constructor installs vtable1c9e978. The object is appended to "
        "container+10, parsed through virtual+18, and token is assigned to DWORD+28. "
        "The post-parse helper5ef140 only writes+28; it does not replace the object.",
        0x5e3a11, 0x5e3a2c, 0x5e3a34, 0x5e3d04, 0x5e3d16,
        0x5de6ce, 0x5e4312, 0x5e4322, 0x5e4f12, 0x5ef140,
        size="0x58", vtable_rva="0x1c9e978"),
    "subject_type_field": fact(
        "Parser dda5d0 accepts token352a(subject_type), passes object+38 to the "
        "native String32 parser170b790. Constructor initializes its length+48=0 "
        "and capacity+50=15. This proves a parsed name field, not a validated "
        "dependency definition or an arbitrary-type conversion capability.",
        0xdda5d3, 0xdda5e4, 0x5de6da, 0x5de6e1, 0x5de6e8,
        offset="0x38", width=32, storage="EngineString32"),
    "apply_slot": fact(
        "Base effect container5ed800 iterates child pointers+10..+18 and invokes "
        "virtual+78 with the unchanged scope and flag. For the constructed object "
        "that slot is dda140. Slot+98 is outside this vtable and is not an apply method.",
        0x5ed815, 0x5ed840, 0x5ed851,
        apply_slot="0x78", apply_rva="0xdda140", vtable_size_bound="0x98"),
    "disk_apply_diagnostic_only": fact(
        "The fully bounded dda140 body chooses the country handle at scope+44 or "
        "+2c according to byte+4b and tests its high byte. Invalid scope logs a "
        "scope diagnostic. The valid-country branch emits the literal 'Script "
        "should DLC check Mandate of Heaven OR Art of War OR Leviathan.' and exits. "
        "No read of the parsed subject_type field+38, dependency lookup or relation "
        "type/date/truce write is present in this decoded body. This is the behavior "
        "of the pinned disk function; it does not establish the behavior of a "
        "different runtime implementation or an untraced ordinary DLC dispatch.",
        0xdda165, 0xdda16f, 0xdda176, 0xdda17a, 0xdda180,
        0xdda471, 0xdda4ce, 0xdda515, 0xdda520, 0xdda556,
        diagnostic_string_rva="0x1d23e60", source_path_rva="0x1d23ec8"),
    "initialization_does_not_resolve_gap": fact(
        "Base constructor5de770 registers effect pointers with global233fe48. "
        "The recorded startup loop invokes virtual+50 on those objects. This "
        "object has8f440(ret) at+50, so that specific initialization route does "
        "not supply a replacement converter. No claim is made about every other "
        "unexamined runtime initialization route.",
        0x5de7bb, 0x205cd5, 0x205d63, 0x205d6a, 0x8f440),
    "other_tokens_are_not_aliases": fact(
        "set_country_subject_type3bb3 and upgrade_subject_type3bb9 route to the "
        "factory's default/scripted-effect fallback5e4b04, not this change_subject_type "
        "case. Token name similarity is not evidence that they provide callable "
        "conversion alternatives. The stock upgrade_subject_type key also appears "
        "as a boolean property in subject definitions.", 0x5e3a2c, 0x5e3a34),
    "preservation_unresolved": fact(
        "The successful type-changing implementation has not been identified. "
        "Whether appanage->vassal is supported, whether the dependency is reused, "
        "and whether dependency start date or bilateral truce changes are all "
        "unresolved. Existing vassal creation behavior must not be substituted "
        "for change_subject_type semantics.",
        dependency_identity_preserved=None, dependency_start_date_preserved=None,
        bilateral_truce_preserved=None, appanage_to_vassal_supported=None),
}


def rows(pe, instructions):
    result = []
    for ins in instructions:
        row = {"rva": hex(ins.address), "bytes": ins.bytes.hex(),
               "instruction": (ins.mnemonic + " " + ins.op_str).rstrip()}
        for op in ins.operands:
            if op.type == 3 and ins.reg_name(op.mem.base) == "rip":
                target = ins.address + ins.size + op.mem.disp
                row["rip_target"] = hex(target)
                raw = pe.bytes_at(target, 160).split(b"\0")[0]
                if raw and all(32 <= ch < 127 or ch in (9, 10, 13) for ch in raw):
                    row["ascii"] = raw.decode("ascii")
        result.append(row)
    return result


def make_report(pe, md, game_dir):
    tokens = {}
    for name, (token, descriptor) in TOKENS.items():
        assert struct.unpack("<I", pe.bytes_at(descriptor, 4))[0] == token
        assert pe.bytes_at(descriptor + 4, len(name) + 1) == name.encode() + b"\0"
        tokens[name] = {"token": hex(token), "descriptor_rva": hex(descriptor)}
    dispatch = {}
    for name in ("change_subject_type", "set_country_subject_type", "upgrade_subject_type"):
        token = TOKENS[name][0]
        index = token - 0x3b42
        byte_rva = 0x5e6314 + index
        mapped = pe.bytes_at(byte_rva, 1)[0]
        target_rva = 0x5e62a0 + 4 * mapped
        target = struct.unpack("<I", pe.bytes_at(target_rva, 4))[0]
        assert target == (0x5e3d04 if name == "change_subject_type" else 0x5e4b04)
        dispatch[name] = {"index": hex(index), "byte_table_rva": hex(byte_rva),
                          "mapped_index": mapped, "target_table_rva": hex(target_rva),
                          "case_rva": hex(target)}
    vtable = {hex(slot): hex(pe.u64(pe.to_offset(0x1c9e978 + slot)) - pe.base)
              for slot in range(0, 0x98, 8)}
    assert vtable["0x20"] == "0xdda5d0"
    assert vtable["0x50"] == "0x8f440"
    assert vtable["0x78"] == "0xdda140"
    functions = {}
    for entry in FUNCTIONS:
        instructions, edges = bounded_cfg(pe, md, entry, window=0x2000, max_instructions=2000)
        functions[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(),
                                 "instructions": rows(pe, instructions), "edges": edges,
                                 "decoded_bytes": sum(ins.size for ins in instructions)}
    blocks = {}
    for start, end in BLOCKS:
        instructions = list(md.disasm(pe.bytes_at(start, end-start), start))
        assert sum(ins.size for ins in instructions) == end-start, hex(start)
        blocks[hex(start)] = {"end_rva_exclusive": hex(end),
                              "instructions": rows(pe, instructions),
                              "decoded_bytes": end-start}
    stock = game_dir / "events/ColonialNation.txt"
    raw = stock.read_bytes()
    lines = raw.decode("utf-8-sig").splitlines()
    excerpt = "\n".join(lines[4653:4682])
    assert "id = colonial_nation.185" in excerpt
    assert 'has_dlc = "Leviathan"' in excerpt
    assert "is_subject_of_type = private_enterprise" in excerpt
    assert "change_subject_type = {" in excerpt and "subject_type = crown_colony" in excerpt
    return {"binary_sha256": hashlib.sha256(pe.data).hexdigest(),
            "scope": "bounded_offline_change_subject_type", "runtime_verified": False,
            "tokens": tokens, "factory_dispatch": dispatch, "vtable_rva": "0x1c9e978",
            "vtable_slots": vtable, "facts": FACTS,
            "stock_evidence": {"path": "events/ColonialNation.txt", "sha256": hashlib.sha256(raw).hexdigest(),
                               "first_line": 4654, "last_line": 4682, "excerpt": excerpt,
                               "establishes": "country/subject scope syntax with a crown_colony argument",
                               "does_not_establish": "arbitrary type support or start/truce preservation"},
            "functions": functions, "factory_and_startup_blocks": blocks,
            "total_decoded_bytes": sum(item["decoded_bytes"] for item in (*functions.values(), *blocks.values())),
            "limits": {"process_access": False, "native_calls": False, "game_or_mod_writes": False,
                       "max_function_window_bytes": 0x2000, "max_instructions_per_function": 2000,
                       "whole_factory_disassembly": False, "max_committed_memory_bytes": 768*1024*1024}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=Path("../eu4.exe"))
    parser.add_argument("--game-dir", type=Path, default=Path(".."))
    parser.add_argument("--output", type=Path, default=Path("work/reports/native-change-subject-type-1375.json"))
    parser.add_argument("--deps-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(args.exe)
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError("Exact-build SHA256 mismatch")
    md, _ = make_disassembler(args.deps_dir)
    report = make_report(pe, md, args.game_dir)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    check_memory_budget()
    if args.check:
        if args.output.read_bytes() != payload:
            raise ValueError("Reproduced report differs")
    else:
        args.output.write_bytes(payload)
    print(json.dumps({"report_sha256": hashlib.sha256(payload).hexdigest(),
                      "functions": len(report["functions"]), "blocks": len(BLOCKS),
                      "decoded_bytes": report["total_decoded_bytes"], "check": args.check,
                      "runtime_verified": False}))


if __name__ == "__main__":
    main()
