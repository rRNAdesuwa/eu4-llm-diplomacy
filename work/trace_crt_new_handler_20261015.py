"""Bounded offline CRT new-handler startup evidence; no process or native access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget, make_disassembler

OUT = ROOT / "work/reports/war-peace-api-20261015-r6-crt"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
RANGES = (
    (0x1a34018, 0x1a340c4, "cookie initializer; pdata boundary"),
    (0x1a337c8, 0x1a337da, "PE entrypoint; pdata boundary"),
    (0x1a33654, 0x1a337c5, "entrypoint tail target; pdata boundary"),
    (0x1a330c0, 0x1a33109, "CRT initialization caller; pdata boundary"),
    (0x1a63928, 0x1a6393b, "direct call target; tail branch ends leaf"),
    (0x1a72ebc, 0x1a72f3c, "initializer loop; pdata boundary"),
    (0x1a63844, 0x1a63881, "initializer pair target; pdata boundary"),
    (0x1a63974, 0x1a6397c, "direct call target; single store and RET leaf"),
)
SOURCES = (
    "work/discover_diplomacy.py",
    "work/reports/war-peace-api-20261015-r6/war/disassembly.json",
    "work/reports/war-peace-api-20261015-r6/war/manual-boundary.json",
    "work/reports/war-peace-api-20261015-r6/war/manifest.json",
    "work/trace_crt_new_handler_20261015.py",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)}


def scan(pe):
    # Candidate scan, not a whole-program instruction decode. Only conventional
    # RIP-relative reg MOV/LEA/XOR/XCHG are covered; aliases/other forms unknown.
    pattern = re.compile(rb"[\x40-\x4f]?[\x8b\x89\x8d\x33\x31\x87]"
                         rb"[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....", re.S)
    rip = []
    calls = {entry: [] for entry in (0x1a63974, 0x1a63844, 0x1a34018)}
    for section in pe.sections:
        if not section["flags"] & 0x20000000:
            continue
        lo, hi = section["raw"], section["raw"] + section["size"]
        for match in pattern.finditer(pe.data, lo, hi):
            raw = match.group()
            rva = pe.to_rva(match.start())
            target = rva + len(raw) + struct.unpack("<i", raw[-4:])[0]
            opcode = raw[1] if 0x40 <= raw[0] <= 0x4f else raw[0]
            if target != 0x233d0c8 and not (target == 0x1fc16b8 and opcode in (0x89, 0x87)):
                continue
            f = pe.function(rva)
            rip.append({"rva": hex(rva), "target_rva": hex(target), "bytes": raw.hex(),
                        "pdata": [hex(x) for x in f] if f else None,
                        "evidence": "byte_pattern_candidate_until_boundary_replay"})
        for match in re.finditer(b"\xe8", pe.data[lo:hi]):
            off = lo + match.start()
            if off + 5 > hi:
                continue
            rva = pe.to_rva(off)
            target = rva + 5 + struct.unpack_from("<i", pe.data, off + 1)[0]
            if target in calls:
                f = pe.function(rva)
                calls[target].append({"rva": hex(rva), "bytes": pe.data[off:off+5].hex(),
                                      "pdata": [hex(x) for x in f] if f else None})
        check_memory_budget()
    pointers = {}
    for rva in (0x233d0c8, 0x1a63974, 0x1a63844, 0x1a34018):
        needle = struct.pack("<Q", pe.base + rva)
        rows, start = [], 0
        while True:
            off = pe.data.find(needle, start)
            if off < 0:
                break
            rows.append({"file_offset": hex(off), "rva": hex(pe.to_rva(off))})
            start = off + 1
        pointers[hex(rva)] = rows
    return {"rip_candidates": rip,
            "e8_candidates": {hex(k): v for k, v in calls.items()},
            "absolute_preferred_va_candidates": pointers,
            "limits": ["Conventional RIP reg MOV/LEA/XOR/XCHG only.",
                       "No completeness claim for indirect/aliased stores, modified modules, or runtime code.",
                       "E8 bytes and absolute qwords are candidates until instruction/table context is retained."]}


def retained_getter(pe):
    old = json.loads((ROOT / SOURCES[1]).read_bytes())
    f = next(f for f in old["functions"] if f["entry_rva"] == "0x1a639ac")
    for row in f["instructions"]:
        raw = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw
    return {"source": SOURCES[1], "entry_rva": f["entry_rva"],
            "instructions": f["instructions"], "new_decoded_bytes": 0}


def produce(pe):
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    assert md is not None and cs.__version__ == "5.0.7"
    functions, total = [], 0
    for start, end, authority in RANGES:
        raw = pe.bytes_at(start, end - start)
        rows = list(md.disasm(raw, start))
        assert b"".join(i.bytes for i in rows) == raw
        total += len(raw)
        assert total <= 8192
        functions.append({"entry_rva": hex(start), "end_rva": hex(end),
                          "boundary_authority": authority, "bytes": raw.hex(), "sha256": sha(raw),
                          "instructions": [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                                            "mnemonic": i.mnemonic, "operands": i.op_str} for i in rows]})
        check_memory_budget()
    pos = pe.u32(0x3c)
    ep = pe.u32(pos + 24 + 16)
    assert ep == 0x1a337c8
    table_start, table_end = 0x1c29de0, 0x1c29ee0
    table = pe.bytes_at(table_start, table_end - table_start)
    return {"evidence_type": "ordinary_offline_capstone_and_PE_replay_not_REA_runtime",
            "game_sha256": SHA, "game_bytes": len(pe.data), "preferred_image_base": hex(pe.base),
            "pe_entrypoint_rva": hex(ep), "capstone_version": cs.__version__,
            "new_unique_decoded_bytes": total, "decode_budget_bytes": 8192,
            "functions": functions, "reused_getter": retained_getter(pe),
            "initializer_pairs": {"start_rva": hex(table_start), "end_rva": hex(table_end),
                                  "stride_bytes": 16, "bytes": table.hex(), "sha256": sha(table),
                                  "selected_entry_rva": "0x1c29df0", "selected_init_rva": "0x1a63844",
                                  "selected_uninit_rva": None},
            "guard_dispatch": {"slot_rva": "0x1b67860", "bytes": pe.bytes_at(0x1b67860, 8).hex(),
                               "target_rva": "0x1a79a30", "target_bytes": pe.bytes_at(0x1a79a30, 2).hex()},
            "scan": scan(pe), "source_pins": [pin(ROOT / x) for x in SOURCES],
            "process_accessed": False, "native_calls": 0, "requests_published": 0,
            "runtime_handler_null_proved": False, "native_ready": False,
            "peak_committed_bytes": check_memory_budget()}


def write_new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert sha(pe.data) == SHA and len(pe.data) == 38462504 and pe.base == 0x140000000
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_bytes())
        for p in manifest["files"]:
            assert pin(ROOT / p["path"]) == p
        data = json.loads((OUT / "evidence.json").read_bytes())
        for p in data["source_pins"]:
            assert pin(ROOT / p["path"]) == p
        assert scan(pe) == data["scan"]
        assert retained_getter(pe) == data["reused_getter"]
        total = 0
        for f in data["functions"]:
            raw = bytes.fromhex(f["bytes"])
            assert pe.bytes_at(int(f["entry_rva"], 16), len(raw)) == raw and sha(raw) == f["sha256"]
            assert b"".join(bytes.fromhex(x["bytes"]) for x in f["instructions"]) == raw
            total += len(raw)
        assert total == data["new_unique_decoded_bytes"] == 848
        table = data["initializer_pairs"]
        assert pe.bytes_at(int(table["start_rva"], 16), 256) == bytes.fromhex(table["bytes"])
        print(json.dumps({"check": "passed", "new_decode_on_check": 0, "replayed_instruction_bytes": total,
                          "source_pins": len(data["source_pins"]), "peak_committed_bytes": check_memory_budget()}))
        return
    OUT.mkdir(parents=True, exist_ok=False)
    data = produce(pe)
    write_new(OUT / "evidence.json", (json.dumps(data, indent=2) + "\n").encode())
    text = "\n\n".join("### " + f["entry_rva"] + "\n" + "\n".join(
        f'{i["rva"]} {i["bytes"]:24} {i["mnemonic"]} {i["operands"]}' for i in f["instructions"])
        for f in data["functions"]) + "\n"
    write_new(OUT / "disassembly.txt", text.encode())
    manifest = {"schema": "eu4-r6-crt-startup-evidence-v1", "native_ready": False,
                "files": [pin(OUT / "evidence.json"), pin(OUT / "disassembly.txt"), pin(Path(__file__).resolve())]}
    write_new(OUT / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print(json.dumps({"report": str(OUT), "manifest_sha256": sha((OUT / "manifest.json").read_bytes()),
                      "new_unique_decoded_bytes": data["new_unique_decoded_bytes"],
                      "peak_committed_bytes": data["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
