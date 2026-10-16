"""Append explicitly chosen console UI code under a shared8KiB budget."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget
DIRECTORY = ROOT/"work/reports/console-key-mapping-20261015-r1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add", nargs="*", default=[])
    parser.add_argument("--table", nargs="*", default=[])
    args = parser.parse_args()
    pe = PE(ROOT.parent/"eu4.exe")
    sha = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    assert hashlib.sha256(pe.data).hexdigest() == sha
    md, cs = make_disassembler(ROOT/"work/deps/capstone-5.0.7")
    assert md and cs.__version__ == "5.0.7"
    path = DIRECTORY/"static.json"
    data = json.loads(path.read_text()) if path.exists() else {"ranges": [], "tables": {}}
    ranges = data["ranges"]
    for item in args.add:
        name, address = item.split("=", 1)
        numbers = [int(x, 0) for x in address.split(":")]
        start = numbers[0]
        interval = pe.function(start)
        end = numbers[1] if len(numbers) == 2 else interval[1]
        assert len(numbers) == 2 or interval[0] == start
        assert 0 < end-start <= 8192
        assert not any(start < int(r["end"], 16) and int(r["start"], 16) < end for r in ranges)
        assert sum(len(bytes.fromhex(r["raw_bytes"])) for r in ranges)+end-start <= 8192
        raw = pe.bytes_at(start, end-start)
        rows = []
        for i in md.disasm(raw, start):
            row = dict(rva=hex(i.address), bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str)
            for o in i.operands:
                if o.type == cs.x86.X86_OP_MEM and o.mem.base == cs.x86.X86_REG_RIP:
                    target = i.address+i.size+o.mem.disp
                    ref = dict(rva=hex(target))
                    try:
                        value = pe.bytes_at(target, 96).split(b"\0", 1)[0]
                        if value and all(32 <= b < 127 for b in value):
                            ref["ascii_candidate"] = value.decode("ascii")
                    except (ValueError, KeyError):
                        pass
                    row.setdefault("rip_references", []).append(ref)
                if o.type == cs.x86.X86_OP_IMM and (i.mnemonic == "call" or i.mnemonic.startswith("j")):
                    row["target_rva"] = hex(o.imm)
            rows.append(row)
        assert sum(len(bytes.fromhex(r["bytes"])) for r in rows) == len(raw)
        ranges.append(dict(name=name, start=hex(start), end=hex(end), raw_bytes=raw.hex(),
            sha256=hashlib.sha256(raw).hexdigest(), instructions=rows))
    for item in args.table:
        name, address = item.split("=", 1)
        start, size = [int(x, 0) for x in address.split(":")]
        assert 0 < size <= 1024 and size % 8 == 0
        raw = pe.bytes_at(start, size)
        data["tables"][name] = dict(rva=hex(start), raw_hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(),
            slots={hex(offset): dict(value=hex(value), rva=hex(value-pe.base), executable=pe.executable(value-pe.base),
                pdata=[hex(x) for x in pe.function(value-pe.base)] if pe.function(value-pe.base) else None)
                for offset in range(0, size, 8) for value in [struct.unpack_from("<Q", raw, offset)[0]]})
    data.update(schema="EU4-CONSOLE-KEYBOARD-STATIC/1", game_sha256=sha, image_base=hex(pe.base),
        evidence_kind="ordinary_capstone_fixed_PE", capstone_version=cs.__version__,
        new_decoded_bytes=sum(len(bytes.fromhex(r["raw_bytes"])) for r in ranges), budget_bytes=8192,
        peak_committed_bytes=check_memory_budget(), game_process_accessed=False, keys_sent=0,
        native_calls=0, memory_written=False,
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    path.write_text(json.dumps(data, indent=2)+"\n", encoding="ascii")
    lines = []
    for r in ranges:
        lines.append(f"RANGE {r['name']} [{r['start']},{r['end']})")
        lines.extend(f"{int(i['rva'],16):08x} {i['bytes']:22} {i['mnemonic']:8} {i['operands']} "+
            " ".join(x.get("ascii_candidate", "") for x in i.get("rip_references", [])) for i in r["instructions"])
    (DIRECTORY/"disassembly.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(dict(ranges=len(ranges), decoded_bytes=data["new_decoded_bytes"],
        tables=list(data["tables"]), peak_committed_bytes=data["peak_committed_bytes"])))


if __name__ == "__main__":
    main()
