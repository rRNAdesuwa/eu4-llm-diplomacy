"""Narrow two alternate console-predicate consumers; fixed file only."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget

OUT = ROOT / "work/reports/console-alternate-consumers-20261015-r1"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw = path.read_bytes()
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    assert md and cs.__version__ == "5.0.7"
    previous = ROOT / "work/reports/console-key-mapping-20261015-r1"
    assert pin(previous / "manifest.json")["sha256"] == "270fcf8cfbbb638f51da6dc00f5e63981e9f56fb3adbd54560a1312c2b18bec1"
    for relative, expected in json.loads((previous / "manifest.json").read_text())["source_pins"].items():
        assert pin(ROOT / relative) == expected, relative
    ranges = []
    for start, end in ((0x816af6, 0x8171e0), (0x14ea150, 0x14ea3c9)):
        assert pe.function(start)[:2] == (start, end)
        raw = pe.bytes_at(start, end - start)
        rows = []
        for ins in md.disasm(raw, start):
            row = dict(rva=hex(ins.address), bytes=ins.bytes.hex(), mnemonic=ins.mnemonic, operands=ins.op_str)
            for op in ins.operands:
                if op.type == cs.x86.X86_OP_IMM and (ins.mnemonic == "call" or ins.mnemonic.startswith("j")):
                    row["target_rva"] = hex(op.imm)
                if op.type == cs.x86.X86_OP_MEM and op.mem.base == cs.x86.X86_REG_RIP:
                    target = ins.address + ins.size + op.mem.disp
                    ref = dict(rva=hex(target))
                    try:
                        value = pe.bytes_at(target, 96).split(b"\0", 1)[0]
                        if value and all(32 <= b < 127 for b in value):
                            ref["ascii_candidate"] = value.decode("ascii")
                    except (ValueError, KeyError):
                        pass
                    row.setdefault("rip_references", []).append(ref)
            rows.append(row)
        decoded = sum(len(bytes.fromhex(i["bytes"])) for i in rows)
        ranges.append(dict(start=hex(start), end=hex(end), raw_bytes=raw.hex(),
            sha256=hashlib.sha256(raw).hexdigest(), linear_decoded_bytes=decoded,
            undisassembled_tail_bytes=len(raw) - decoded, instructions=rows))
    accounted = sum(len(bytes.fromhex(r["raw_bytes"])) for r in ranges)
    assert accounted == 2403 and accounted + 5758 == 8161 <= 8192
    result = dict(schema="EU4-CONSOLE-ALTERNATE-CONSUMERS-STATIC/1", game_sha256=SHA,
        ranges=ranges, new_decode_accounted_bytes=accounted, previous_scope_bytes=5758,
        shared_scope_accounted_bytes=8161, scope_budget_bytes=8192,
        evidence_kind="ordinary_capstone_fixed_PE", capstone_version=cs.__version__,
        peak_committed_bytes=check_memory_budget(), game_process_accessed=False,
        keys_sent=0, native_calls=0, memory_written=False,
        producer=pin(Path(__file__)))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "static.json").open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    lines = []
    for item in ranges:
        lines.append(f"RANGE [{item['start']},{item['end']})")
        lines.extend(f"{i['rva']} {i['bytes']:22} {i['mnemonic']:8} {i['operands']} " +
            " ".join(x.get("ascii_candidate", "") for x in i.get("rip_references", [])) for i in item["instructions"])
    (OUT / "disassembly.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"scope_bytes": 8161, "ranges": [{k: r[k] for k in
        ("start", "end", "linear_decoded_bytes", "undisassembled_tail_bytes")} for r in ranges]}))


if __name__ == "__main__":
    main()
