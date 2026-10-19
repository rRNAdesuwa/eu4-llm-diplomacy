"""Append explicit exact-build ordinary Capstone ranges under a 32KiB scope."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget

SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
OUT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--add", nargs="+", required=True, help="name=RVA or name=RVA:exclusiveEnd for explicit leaf")
    args = ap.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    assert md is not None and cs.__version__ == "5.0.7"
    previous = OUT / "static.json"
    report = json.loads(previous.read_text()) if previous.exists() else {"ranges": []}
    ranges = report["ranges"]
    for item in args.add:
        name, address = item.split("=", 1)
        values = [int(x, 0) for x in address.split(":")]
        start = values[0]
        if len(values) == 2:
            end = values[1]
        else:
            f = pe.function(start)
            assert f and f[0] == start, name
            end = f[1]
        assert 0 < end-start <= 16384
        assert not any(start < int(r["end_rva_exclusive"], 16) and int(r["start_rva"], 16) < end for r in ranges)
        assert sum(int(r["end_rva_exclusive"], 16)-int(r["start_rva"], 16) for r in ranges)+end-start <= 32768
        raw = pe.bytes_at(start, end-start)
        rows = []
        for i in md.disasm(raw, start):
            row = {"rva": hex(i.address), "bytes": i.bytes.hex(), "mnemonic": i.mnemonic, "operands": i.op_str}
            for o in i.operands:
                if o.type == cs.x86.X86_OP_MEM and o.mem.base == cs.x86.X86_REG_RIP:
                    target = i.address+i.size+o.mem.disp
                    ref = {"rva": hex(target)}
                    try:
                        data = pe.bytes_at(target, 96).split(b"\0", 1)[0]
                        if data and all(32 <= b < 127 for b in data): ref["ascii_candidate"] = data.decode("ascii")
                    except (KeyError, ValueError): pass
                    row.setdefault("rip_references", []).append(ref)
            if i.mnemonic.startswith("j") or i.mnemonic == "call":
                for o in i.operands:
                    if o.type == cs.x86.X86_OP_IMM: row["direct_target_rva"] = hex(o.imm)
            rows.append(row)
        assert sum(len(bytes.fromhex(r["bytes"])) for r in rows) == len(raw)
        ranges.append({"name": name, "start_rva": hex(start), "end_rva_exclusive": hex(end),
            "range_sha256": hashlib.sha256(raw).hexdigest(), "instructions": rows})
    tables = {}
    for name, vt, effect in (("knowledge_sharing", 0x1C7F320, 0x528120), ("ask_knowledge_sharing", 0x1C7F0C0, 0x52BE20)):
        raw = pe.bytes_at(vt, 0x128)
        slots = {hex(o): hex(struct.unpack_from("<Q", raw, o)[0]-pe.base) for o in range(0, len(raw), 8)}
        assert int(slots["0x48"], 16) == effect
        tables[name] = {"vtable_rva": hex(vt), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "slots": slots}
    task_vt = pe.bytes_at(0x1CDE0A0, 0x80)
    task_slots = {hex(o): hex(struct.unpack_from("<Q", task_vt, o)[0]-pe.base) for o in range(0, len(task_vt), 8)}
    assert task_slots["0x40"] == "0xa70470" and task_slots["0x48"] == "0x529fa0"
    lines = []
    for r in ranges:
        lines.append(f"RANGE {r['name']} [{r['start_rva']},{r['end_rva_exclusive']})")
        lines.extend(f"{int(i['rva'],16):08x} {i['bytes']:22} {i['mnemonic']:8} {i['operands']} "
                     +" ".join(ref.get("ascii_candidate", "") for ref in i.get("rip_references", [])) for i in r["instructions"])
    asm = OUT / "disassembly.txt"
    asm.write_text("\n".join(lines)+"\n", encoding="utf-8")
    report = dict(schema="EU4DIPLOMACY-KNOWLEDGE-EFFECT-STATIC/1", game_sha256=SHA, game_bytes=len(pe.data),
        image_base=hex(pe.base), evidence_kind="ordinary_capstone_file_analysis", capstone_version=cs.__version__,
        ranges=ranges, action_vtables=tables, knowledge_object_vtable={"rva": "0x1cde0a0", "bytes": len(task_vt),
            "sha256": hashlib.sha256(task_vt).hexdigest(), "slots": task_slots, "allocation_bytes": 0x48},
        native_calls=0, game_process_accessed=False,
        decoded_bytes=sum(int(r["end_rva_exclusive"],16)-int(r["start_rva"],16) for r in ranges),
        peak_committed_bytes=check_memory_budget(), source_pins={"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "decoder_sha256": hashlib.sha256((ROOT/"work/discover_diplomacy.py").read_bytes()).hexdigest(),
            "disassembly_sha256": hashlib.sha256(asm.read_bytes()).hexdigest()},
        limitations=["Only explicit bounded ranges are decoded; no game function/process is accessed.",
            "Static field meaning is distinct from observed current pair effects; all unresolved lifecycle paths remain unknown."])
    previous.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"ranges": len(ranges), "decoded_bytes": report["decoded_bytes"], "peak_committed_bytes": report["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
