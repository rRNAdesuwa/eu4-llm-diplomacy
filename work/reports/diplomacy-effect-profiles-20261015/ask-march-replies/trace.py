"""Exact-build bounded ordinary Capstone evidence for ask-for-march replies."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget

SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
FUNCTIONS = (("ask_march_effect48", 0x5156F0), ("ask_march_score120", 0x516980),
             ("ask_march_clone_b0", 0x5168F0), ("designate_march_effect48", 0x513650),
             ("message_constructor", 0x8D4660), ("command_execute", 0x4E7C50),
             ("pending_remove_id", 0x360970), ("pending_prune", 0x3607C0),
             ("pending_clear", 0x3608D0))
LEAVES = (("ask_march_token98", 0x515EF0, 0x515EF6),
          ("reply_required_d0", 0x8F440, 0x8F443), ("unconditional_accept_f0", 0x8F450, 0x8F453))


def main():
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    md, cs = make_disassembler(Path(tempfile.gettempdir()) / "eu4-native-analysis-deps")
    selected = []
    for name, start in FUNCTIONS:
        f = pe.function(start)
        assert f and f[0] == start and 0 < f[1] - start <= 8192
        selected.append((name, start, f[1]))
    selected.extend(LEAVES)
    assert sum(end - start for _, start, end in selected) <= 16384
    ranges, lines = [], []
    for name, start, end in selected:
        raw = pe.bytes_at(start, end - start)
        instructions = []
        lines.append(f"RANGE {name} [{start:#x},{end:#x})")
        for i in md.disasm(raw, start):
            row = {"rva": hex(i.address), "bytes": i.bytes.hex(), "mnemonic": i.mnemonic, "operands": i.op_str}
            for o in i.operands:
                if o.type == cs.x86.X86_OP_MEM and o.mem.base == cs.x86.X86_REG_RIP:
                    target = i.address + i.size + o.mem.disp
                    ref = {"rva": hex(target)}
                    try:
                        data = pe.bytes_at(target, 96).split(b"\0", 1)[0]
                        if data and all(32 <= c < 127 for c in data):
                            ref["ascii_candidate"] = data.decode("ascii")
                    except (KeyError, ValueError):
                        pass
                    row.setdefault("rip_references", []).append(ref)
            if i.mnemonic.startswith("j") or i.mnemonic == "call":
                for o in i.operands:
                    if o.type == cs.x86.X86_OP_IMM:
                        row["direct_target_rva"] = hex(o.imm)
            instructions.append(row)
            refs = " ".join(r.get("ascii_candidate", "") for r in row.get("rip_references", []))
            lines.append(f"{i.address:08x} {i.bytes.hex():22} {i.mnemonic:8} {i.op_str} {refs}")
        assert sum(len(bytes.fromhex(i["bytes"])) for i in instructions) == len(raw)
        ranges.append({"name": name, "start_rva": hex(start), "end_rva_exclusive": hex(end),
                       "range_sha256": hashlib.sha256(raw).hexdigest(), "instructions": instructions})
    vt = pe.bytes_at(0x1C80440, 0x128)
    slots = {hex(o): hex(struct.unpack_from("<Q", vt, o)[0] - pe.base) for o in range(0, len(vt), 8)}
    assert slots["0x48"] == "0x5156f0" and slots["0x98"] == "0x515ef0" and slots["0xb0"] == "0x5168f0"
    out = Path(__file__).parent
    assembly = out / "disassembly.txt"
    assembly.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {"schema": "EU4DIPLOMACY-ASK-MARCH-REPLY-STATIC/1", "game_sha256": SHA,
        "game_bytes": len(pe.data), "image_base": hex(pe.base), "evidence_kind": "ordinary_capstone_file_analysis",
        "ranges": ranges, "ask_march_vtable": {"rva": "0x1c80440", "bytes": len(vt),
            "sha256": hashlib.sha256(vt).hexdigest(), "slots": slots},
        "native_calls": 0, "game_process_accessed": False, "runtime_verified": False,
        "peak_committed_bytes": check_memory_budget(),
        "source_pins": {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "decoder_sha256": hashlib.sha256((ROOT / "work/discover_diplomacy.py").read_bytes()).hexdigest(),
            "disassembly_sha256": hashlib.sha256(assembly.read_bytes()).hexdigest()},
        "limitations": ["No native function is called; this is fixed-file static evidence.",
            "Pending queue presence is separate from acceptance, rejection, applied relationship and exact external request causality.",
            "Notification absence and pending disappearance remain unknown; neither proves refusal."]}
    (out / "static.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ranges": len(ranges), "decoded_bytes": sum(e - s for _, s, e in selected),
        "instructions": sum(len(r["instructions"]) for r in ranges), "peak_committed_bytes": report["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
