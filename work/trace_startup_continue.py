"""Reproduce bounded offline evidence for EU4 1.37.5 startup save selection.

Reads only the exact disk PE. No process, command line, user metadata or save is
read or changed. Indirect character-dispatch branches are explicitly enumerated.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

ENTRIES = [0x8757e0, 0x1719120, 0x1719300, 0x1719920, 0x1719b50, 0x1719c40,
           0x5d1050, 0x5d1670, 0x2043a0, 0x2111c0]


def fact(summary, *rvas, **details):
    return {"summary": summary, "evidence_rvas": [hex(rva) for rva in rvas],
            "runtime_verified": False, **details}


FACTS = {
    "argument_grammar": fact(
        "Startup passes argc/argv to1719120. It joins argv[1:] with spaces and sends "
        "the text to1719300. The parser strips a leading dash, double dash or slash "
        "in key-start state. '=' while reading the key switches to value state unless "
        "followed by space. Thus -continue=basename.eu4 is valid syntax. A double-quoted "
        "span is copied without quotes; do not infer shell quoting from this inner parser.",
        0x87588c, 0x171920a, 0x171922b, 0x171924f, 0x171926b,
        0x1719445, 0x1719453, 0x1719460, 0x1719470, 0x171948d,
        syntax_example="-continue=llm_verified_baseline.eu4"),
    "named_continue": fact(
        "1719b50 looks up key 'continue' and copies its String32 value from a sorted "
        "64-byte key/value entry. Startup sets233fe9c, constructs literal 'save games/' "
        "then appends the value and assigns String32 global1fd3a08. A reviewed local "
        "save basename including.eu4 is the direct intended argument. Passing an "
        "absolute path or a second save games/ prefix does not bypass this prefix.",
        0x876865, 0x87686f, 0x87687c, 0x8768ad, 0x8768bc, 0x8768dc, 0x8768e9,
        0x8768f6, 0x8768fd, 0x1719b50, 0x1719c40,
        key="continue", prefix="save games/", path_string_rva="0x1fd3a08",
        selection_flag_rva="0x233fe9c", accepts_explicit_local_basename=True),
    "last_save_precedence": fact(
        "continuelastsave is checked by presence (lookup index !=-1); its value is "
        "unused. It reads continue_game.json via5d1670. When the result validity "
        "byte+80 is true, it copies String32 filename+60 AS IS into1fd3a08 and sets "
        "233fe9c. That flag skips the later continue lookup. Do not combine the flags "
        "when selecting a fixed save, or assume last-save metadata points to a test save.",
        0x876558, 0x876577, 0x8765dd, 0x876686, 0x87668b, 0x876695,
        0x87669c, 0x8766ca, 0x8766d1, 0x876853,
        key="continuelastsave", value_semantics="presence_only", precedence="before_continue"),
    "continue_metadata": fact(
        "5d1670 reads virtual filesystem path continue_game.json, parses JSON and "
        "looks up title,desc,date,filename using case-insensitive key comparisons. "
        "Outputs are four String32 fields at0/20/40/60 and a validity byte80. The "
        "writer5d1050 emits those same keys to continue_game.temp and moves it into "
        "continue_game.json. The filename field is a VFS-relative save path, not "
        "a -continue basename; this report does not modify the metadata or claim "
        "every malformed/missing-field case is accepted.",
        0x5d16ab, 0x5d1840, 0x5d18e0, 0x5d1970, 0x5d1a00,
        0x5d10b6, 0x5d10d3, 0x5d10f0, 0x5d110d, 0x5d1460, 0x5d1467,
        filename="continue_game.json", temporary_filename="continue_game.temp",
        example={"title": "Research baseline", "desc": "France", "date": "1444.11.11",
                 "filename": "save games/llm_verified_baseline.eu4"}),
    "consumer_requires_nonempty_path": fact(
        "2043a0 checks path String32 length at1fd3a18. Nonzero branches directly "
        "to204e9a, passes1fd3a08 to2111c0. That routine checks the VFS path and reads "
        "it via1710440 before further load/session setup, including5ccca0/5ccfe0. "
        "Parameter parsing alone is not evidence of successful map loading; normal "
        "startup, VFS, save validation and session checks still apply.",
        0x204b8e, 0x204b96, 0x204e9a, 0x204ea4,
        0x21126e, 0x211288, 0x21154c, 0x21163e),
}


def encode(pe, md, entry, extra_entries=()):
    found, edges = {}, []
    for start in (entry, *extra_entries):
        ins, links = bounded_cfg(pe, md, start, window=0x4000, max_instructions=4000)
        found.update({item.address: item for item in ins})
        edges.extend(links)
    rows = []
    for address, item in sorted(found.items()):
        row = {"rva": hex(address), "bytes": item.bytes.hex(),
               "instruction": (item.mnemonic + " " + item.op_str).rstrip()}
        for op in item.operands:
            if op.type == 3 and item.reg_name(op.mem.base) == "rip":
                target = address + item.size + op.mem.disp
                row["rip_target"] = hex(target)
                raw = pe.bytes_at(target, 160).split(b"\0")[0]
                if raw and all(32 <= char < 127 or char in (9, 10, 13) for char in raw):
                    row["ascii"] = raw.decode("ascii")
        rows.append(row)
    return {"entry_rva": hex(entry), "prefix32": pe.bytes_at(entry, 32).hex(),
            "extra_dispatch_entries": [hex(value) for value in extra_entries],
            "decoded_bytes": sum(item.size for item in found.values()),
            "instructions": rows, "edges": edges, "runtime_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=Path("../eu4.exe"))
    parser.add_argument("--output", type=Path, default=Path("work/reports/native-startup-continue-1375.json"))
    parser.add_argument("--deps-dir", type=Path)
    args = parser.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise ValueError("Exact-build SHA256 mismatch")
    md, _ = make_disassembler(args.deps_dir)
    dispatch = {}
    for char in range(62):
        index = pe.bytes_at(0x1719758 + char, 1)[0]
        target = struct.unpack("<I", pe.bytes_at(0x171973c + index * 4, 4))[0]
        if not 0x1719300 <= target < 0x1719770:
            raise ValueError("Unexpected command-line character dispatch target")
        dispatch[str(char)] = hex(target)
    switch_entries = sorted({int(value, 16) for value in dispatch.values()})
    functions = {hex(entry): encode(pe, md, entry, switch_entries if entry == 0x1719300 else ())
                 for entry in ENTRIES}
    report = {"binary_sha256": digest, "scope": "bounded_offline_startup_save_selection",
              "runtime_verified": False, "facts": FACTS, "character_dispatch": dispatch,
              "functions": functions, "function_count": len(functions),
              "total_decoded_bytes": sum(fn["decoded_bytes"] for fn in functions.values()),
              "limits": {"window_bytes_per_entry": 0x4000, "instruction_limit_per_entry": 4000,
                         "process_access": False, "user_file_access": False,
                         "native_calls": False, "modifications_to_game_or_saves": False}}
    check_memory_budget()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "function_count": len(functions), "decoded_bytes": report["total_decoded_bytes"]}))


if __name__ == "__main__":
    main()
