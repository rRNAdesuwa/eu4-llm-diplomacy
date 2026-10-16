"""Exact-build, bounded OFFLINE evidence for the UI named-save path.

No process handles, DLL loading, native calls, save creation or deletion.
This inventory deliberately does not provide a callable save wrapper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

ENTRIES = (
    0x7EB10, 0x7EB40, 0x1174840, 0x1175110, 0x11BD6E0,
    0x5CBEE0, 0x5CBDE0, 0x5C6500, 0x5C9C00, 0x5CA070, 0x5CA280,
    0x5C9680, 0x74BA20, 0x5CDE60, 0x5CE5F0, 0x5C4460, 0x5C44F0,
    0x1718300, 0x17165B0, 0x1715BB0, 0x1A5ED40,
    0x19F8130, 0x19F66C0, 0x19F6790, 0x19F7530, 0x19FAD70,
)
MAX_WINDOW = 0x4000
MAX_INSTRUCTIONS = 4000
MAX_TOTAL_CODE = 256 * 1024


def fact(summary, *anchors, **metadata):
    return {"summary": summary, "evidence_rvas": [hex(x) for x in anchors],
            "runtime_verified": False, **metadata}


FACTS = {
    "ui_named_input": fact(
        "1175110 reads the game_name GUI edit control through virtual+98, copies "
        "its String32 text, calls 1705180/17043c0, and rejects empty text. The UI "
        "binding1174840 also blocks backslash, slash, colon, star, question mark, "
        "angle brackets and vertical bar. This is the real named-save path, not "
        "console savegame callback e7b3e0. Normalizer semantics remain unnamed.",
        0x117513F, 0x1175156, 0x1175194, 0x117519E, 0x11751AB, 0x11751B9,
        0x1174893, 0x117489D, 0x11748D9),
    "ui_existing_file_confirmation": fact(
        "The local UI branch builds a path using5ca070 then calls existence "
        "predicate19f6ea0. Existing paths construct11bd6e0, whose strings are "
        "CONFIRMSAVETITLE/CONFIRMSAVETEXT. The no-existing-file branch reaches "
        "5cbee0 with the leaf-name string and directory-component vector. This "
        "UI check is separate from the writer and does not remove a filesystem race.",
        0x11753E6, 0x11754EC, 0x11754F3, 0x1175533, 0x11BD84F,
        0x11BD902, 0x11755A5, 0x11755BE),
    "named_helper_abi_and_owned_input": fact(
        "5cbee0 takes an owned movable String32 throughRCX, booleansDL/R8B/R9B, "
        "a fifth bool at entryRSP+28 and a pointer to Vector24<String32> at "
        "entryRSP+30. It copies template1fd2e70 into a local request, MOVE-transfers "
        "the incoming32bytes into request+0 and resets the incoming string to "
        "empty SSO; it also destroys that input on normal exit. Do not pass a "
        "host-heap string pretending to own native storage. It calls5cbde0 then "
        "performs UI close/update side effects. The lower dispatcher borrows "
        "the request for this synchronous call; it is not a diplomacy command.",
        0x5CBF09, 0x5CBFF8, 0x5CC007, 0x5CC00F, 0x5CC01A, 0x5CC01E,
        0x5CC022, 0x5CC026, 0x5CC031, 0x5CC045, 0x5CC04E,
        0x5CC069, 0x5CC095, 0x5CC0E6, 0x5CC12F,
        signature_inferred="int named_save(String32* moved_owned_name, bool compression, bool field23, bool backup, bool rotate, const Vector24<String32>* dirs)",
        safe_to_call=False),
    "save_request_layout": fact(
        "The stack request copied by5cbee0 is at least0x41bytes (natural size "
        "0x48 inferred): owned String32+0, flags+20..26, directory String32 vector "
        "+28..3f, error-reporting bool+40. The disk template flags20..26 are "
        "00 00 01 01 01 00 01 and +40=1. Dispatcher chooses local normal5c6500 "
        "when flags20=21=0, local alternate5c7ac0 when20!=0/21=0, and cloud "
        "5c8ba0 when21!=0. Names ironman/cloud are inferred from branch diagnostics; "
        "unknown flags must not be relabelled as safety options.",
        0x5CBF54, 0x5CBF5E, 0x5CBF68, 0x5CBF72, 0x5CBF7C,
        0x5CBF86, 0x5CBF90, 0x5CBFAA, 0x5CBE14, 0x5CBE18,
        0x5CBE25, 0x5CBE35, 0x5CBE7F, 0x5CBE8D,
        template_rva="0x1fd2e70", inferred_size_bytes=72,
        fields={"name": "0x0:String32", "flags": "0x20..0x26:BYTE",
                "dirs": "0x28:Vector24<String32>", "show_error": "0x40:BYTE"}),
    "relative_directory_and_suffix": fact(
        "CRT initializer7eb10 writes literal save games from1c481f0 into "
        "String32 global1fd2f28. 5c9c00 combines optional settings-global "
        "[242bde8]+e0 prefix, the save-games component and caller directory "
        "components. 5ca070 appends slash, leaf name and .eu4. 5ca280 uses5c9680 "
        "to remove a recognized .eu4/.tmp suffix, then appends .tmp. These are "
        "VFS-relative paths; no absolute current user's directory is established "
        "by the on-disk executable alone.",
        0x7EB10, 0x7EB26, 0x7EB2E, 0x5C9C4F, 0x5C9C56,
        0x5C9E1A, 0x5C9F53, 0x5CA110, 0x5CA15E, 0x5CA188,
        0x5CA295, 0x5CA2A2, 0x5CA2C3),
    "not_create_new": fact(
        "5c6500 checks its temporary path and, if present, logs .tmp file "
        "already exists, deleting then calls17165b0. It opens that path with "
        "1718300 mode1/buffer0x20000; mode1 selects19f8130 ->19fa240 and a "
        "registered VFS provider's virtual+48. This route has no observed "
        "CREATE_NEW contract. Final existing file may be backed up, rotated "
        "or deleted before rename. Creating a placeholder at the final path "
        "does not reserve it against the native writer.",
        0x5C6579, 0x5C670A, 0x5C67B9, 0x5C68A8, 0x5C68AB,
        0x5C68B1, 0x1718396, 0x19F8130, 0x19FA368,
        0x5C713E, 0x5C7152, 0x5C7168, 0x5C7349, 0x5C7861,
        native_create_new=False, no_overwrite_verified=False),
    "synchronous_writer_and_join": fact(
        "5c6500 calls74ba20, which calls5cde60. That function may start a TBB "
        "helper, but calls the actual5ce5f0 serialization/compression body "
        "synchronously and joins the helper before returning. Worker callback "
        "5c4460 invokes a server virtual and sleeps50ms; its existence is not "
        "evidence of a detached asynchronous save API. 5c6500 closes the output "
        "via19f66c0 and frees its wrapper before validation/rename. A laboratory "
        "wrapper must budget a potentially long, blocking game-thread call.",
        0x5C68E6, 0x74BB5C, 0x5CDF63, 0x5CDF9A, 0x5CDFC0,
        0x5CE53C, 0x5CE564, 0x5C4469, 0x5C4478,
        0x5C6C4C, 0x5C6C59, 0x5C6F44, 0x5C7888,
        detached_completion_token_identified=False),
    "rename_platform_contract": fact(
        "1715bb0 resolves/normalizes the source filesystem path, UTF8-converts "
        "both names and obtains full paths before calling1a5ed40. The latter "
        "calls imported MoveFileExW with flags2 (COPY_ALLOWED, not REPLACE_EXISTING "
        "and not WRITE_THROUGH). The enclosing save path already has destructive "
        "preparation branches; this rename flag alone does not make saving "
        "atomic no-overwrite or prove flushed durable media completion.",
        0x1715BEA, 0x17160CB, 0x17160FE, 0x171611A, 0x1716136,
        0x171614A, 0x1A5ED44, 0x1A5ED4A,
        platform_documentation="https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw"),
    "zero_return_is_not_file_success": fact(
        "After serializer success,5c6500 setsR12D=0. When final rename returns "
        "false it logs CRITICAL SAVE ERROR and jumps to the same cleanup/return "
        "without changingR12D. Therefore5cbee0 may return0 despite failure to "
        "produce the final filename. 5c6500 also ignores the close return. "
        "A successful native return requires independent file identity, bytes, "
        "content and later reload validation; it cannot be labelled saved.",
        0x5C6C0F, 0x5C6C1D, 0x5C6C4C, 0x5C7888, 0x5C788D,
        0x5C788F, 0x5C78C5, 0x5C797E, 0x5C6F0C, 0x5CC053, 0x5CC12F,
        return_zero_implies_final_file=False),
}


def imports(pe):
    """Bounded PE32+ import inventory; never resolves or loads system libraries."""
    optional = pe.u32(0x3C) + 24
    directory = pe.u32(optional + 112 + 8)
    result = {}
    start = pe.to_offset(directory)
    if start is None:
        raise ValueError("Missing PE import directory")
    for index in range(512):
        original, _, _, name, first = struct.unpack_from("<IIIII", pe.data, start + index * 20)
        if not any((original, name, first)):
            return result
        dll = pe.bytes_at(name, 128).split(b"\0", 1)[0].decode("ascii")
        offset = pe.to_offset(original or first)
        if offset is None:
            raise ValueError("Import thunk outside file")
        for item in range(4096):
            value = pe.u64(offset + item * 8)
            if value == 0:
                break
            symbol = f"ordinal:{value & 0xffff}" if value >> 63 else pe.bytes_at(value + 2, 256).split(b"\0", 1)[0].decode("ascii")
            result[first + item * 8] = f"{dll}!{symbol}"
        else:
            raise ValueError("Too many imports in one DLL")
    raise ValueError("Too many import descriptors")


def generate(exe, deps):
    pe = PE(exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise ValueError("Unsupported executable SHA256")
    md, cs = make_disassembler(deps)
    if md is None:
        raise ValueError("Capstone dependency unavailable")
    imported = imports(pe)
    functions, lookup = {}, {}
    total = 0
    for entry in ENTRIES:
        instructions, edges = bounded_cfg(pe, md, entry, window=MAX_WINDOW, max_instructions=MAX_INSTRUCTIONS)
        rows = []
        for ins in instructions:
            row = {"rva": hex(ins.address), "bytes": ins.bytes.hex(), "instruction": f"{ins.mnemonic} {ins.op_str}".strip()}
            for op in ins.operands:
                if op.type != cs.CS_OP_MEM or op.mem.base != cs.x86_const.X86_REG_RIP:
                    continue
                target = ins.address + ins.size + op.mem.disp
                if target in imported:
                    row["import_symbol"] = imported[target]
                    row["iat_rva"] = hex(target)
                raw = pe.bytes_at(target, 160).split(b"\0", 1)[0]
                if 3 <= len(raw) < 160 and all(32 <= b < 127 for b in raw):
                    row["ascii_reference"] = {"rva": hex(target), "text": raw.decode("ascii")}
            rows.append(row)
            lookup[hex(ins.address)] = row
        size = sum(i.size for i in instructions)
        total += size
        if total > MAX_TOTAL_CODE:
            raise ValueError("Total decoded code budget exceeded")
        functions[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(),
                                  "decoded_bytes": size, "instructions": rows, "edges": edges,
                                  "runtime_verified": False}
        check_memory_budget()
    facts = json.loads(json.dumps(FACTS))
    for name, item in facts.items():
        missing = [r for r in item["evidence_rvas"] if r not in lookup]
        if missing:
            raise ValueError(f"{name}: missing instruction anchors {missing}")
        item["evidence_instructions"] = [lookup[r] for r in item["evidence_rvas"]]
    expected_imports = {
        "0x1a5ed4a": "KERNEL32.dll!MoveFileExW",
        "0x5cdf9a": "tbb.dll!?internal_start@tbb_thread_v3@internal@tbb@@AEAAXP6AIPEAX@Z0@Z",
        "0x5ce53c": "tbb.dll!?join@tbb_thread_v3@internal@tbb@@QEAAXXZ",
    }
    for address, name in expected_imports.items():
        if lookup[address].get("import_symbol") != name:
            raise ValueError(f"Import pin mismatch at {address}")
    if pe.bytes_at(0x1C481F0, 11) != b"save games\0" or pe.bytes_at(0x1FD2E90, 7) != bytes((0, 0, 1, 1, 1, 0, 1)):
        raise ValueError("Directory/default request data changed")
    return {
        "schema_version": 1, "game_sha256": digest,
        "status": "bounded_static_named_save_not_callable",
        "runtime_verified": False, "execution_verified": False,
        "public_backend_registered": False, "native_create_new_verified": False,
        "facts": facts, "functions": functions,
        "default_request_data": {"rva": "0x1fd2e70", "bytes_hex": pe.bytes_at(0x1FD2E70, 0x48).hex()},
        "candidate_private_entry": {"rva": "0x5cbee0", "lower_dispatcher": "0x5cbde0",
            "callable_wrapper_implemented": False, "runtime_abi_verified": False},
        "remaining_requirements": [
            "Verify live configured directory prefix and actual VFS physical write root against the approved test save directory.",
            "Pin/explain all settings and both mutable template flags before choosing the normal local save branch; no cloud or Ironman invocation.",
            "Use only host-generated ASCII llm_test names and approved fixed components; no arbitrary path or script parameters.",
            "Create a durable exclusive attempt claim separate from output names. A final-file placeholder is unsafe because native code can delete or replace it.",
            "Reject any final/tmp/backup/rotation collision and reparse link; a precheck alone has a TOCTOU race, so it does not prove atomic CREATE_NEW.",
            "Develop an independently reviewed isolated namespace/ownership strategy before any save call; do not patch native writer flags casually.",
            "Confirm paused game-thread/world identity before and after a potentially blocking call, and never retry after unknown ownership/exception.",
            "After return verify final file creation identity, completed parse, fresh date/player/relations, hash and absence of temp; then independently reload in a new process.",
            "Native zero return, helper join, close and MoveFileEx return are not a guarantee of media durability or successful reload.",
        ],
        "limits": {"per_entry_bytes": MAX_WINDOW, "per_entry_instructions": MAX_INSTRUCTIONS,
                   "total_code_bytes": MAX_TOTAL_CODE, "memory_guard_mib": 768,
                   "automatic_recursive_call_following": False},
        "summary": {"bounded_entries": len(functions), "decoded_bytes_including_overlaps": total,
                    "facts": len(facts)},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-named-save-1375.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    report = generate(args.exe, args.deps_dir)
    payload = (json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != payload:
            raise SystemExit("Named save report is stale")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    print(json.dumps({"mode": "check" if args.check else "write", "sha256": hashlib.sha256(payload).hexdigest(),
                      "report_bytes": len(payload), **report["summary"]}))


if __name__ == "__main__":
    main()
