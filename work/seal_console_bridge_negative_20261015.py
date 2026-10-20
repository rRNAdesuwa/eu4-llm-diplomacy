"""Independent32B negative bridge check, separate from the sealed8KiB scope."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget
OUT = ROOT / "work/reports/console-bridge-negative-20261015-r1"
OWNER = ROOT / "work/reports/console-consumer-owner-20261015-r1"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    sha = hashlib.sha256(pe.data).hexdigest()
    assert sha == "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    raw = pe.bytes_at(0x816ab0, 0x20)
    assert raw.hex() == "80b907160000007413488b89300300004881c1e8050000e9d46cc800c3cccccc"
    assert pe.function(0x816ab0) is None
    if args.check:
        data = json.loads((OUT / "manifest.json").read_text())
        for relative, expected in data["source_pins"].items():
            assert pin(ROOT / relative) == expected
        print(json.dumps(dict(status="passed", source_pins=len(data["source_pins"]), new_decoded_bytes=0)))
        return
    assert pin(OWNER / "manifest.json")["sha256"] == "d3d579b43b4563112c60872c56dc34748727500d90fc92a3ab39f70a443aae99"
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    rows = []
    for ins in md.disasm(raw, 0x816ab0):
        row = dict(rva=hex(ins.address), bytes=ins.bytes.hex(), mnemonic=ins.mnemonic, operands=ins.op_str)
        if ins.mnemonic.startswith("j"):
            row["target_rva"] = hex(ins.operands[0].imm)
        rows.append(row)
    assert b"".join(bytes.fromhex(i["bytes"]) for i in rows) == raw
    assert [(i["rva"], i.get("target_rva")) for i in rows if "target_rva" in i] == [
        ("0x816ab7", "0x816acc"), ("0x816ac7", "0x149d7a0")]
    result = dict(schema="EU4-CONSOLE-MINIMAL-BRIDGE-FINDINGS/1", game_sha256=sha,
        evidence_kind="fixed_PE_static_only", start_rva="0x816ab0", end_exclusive_rva="0x816ad0",
        pdata_entry=None, raw_hex=raw.hex(), instructions=rows,
        behavior="If BYTE[entryRCX+1607]==0 return; otherwise RCX=QWORD[entryRCX+330]+5e8 and tail-jump149d7a0.",
        direct_forward_to_816ad0=False, entry_816ad0_owner_is_server_proven=False,
        retained_R4_call_815956_to_816ab0_is_keyconsumer_bridge=False,
        prior_conclusion_preserved="816ad0 assigns RSI=entryRCX and its chained816af6 body gates this+19f1.",
        unresolved="Actual caller/owner type of816ad0 is outside this minimal scope.",
        current_gate_value=None, gate_business_meaning="unknown", target_149d7a0_followed=False,
        resources=dict(this_independent_scope_new_decoded_bytes=32, this_scope_budget_bytes=128,
            previous_sealed_scope_bytes=8192, previous_scope_budget_unchanged=True,
            peak_committed_bytes=check_memory_budget()),
        game_process_accessed=False, keys_sent=0, native_calls=0, memory_written=False)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "findings.json").open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    files = [OUT / "findings.json", Path(__file__), ROOT / "work/discover_diplomacy.py",
        OWNER / "manifest.json", OWNER / "findings.json"]
    manifest = dict(schema="EU4-CONSOLE-MINIMAL-BRIDGE-MANIFEST/1", game_sha256=sha,
        source_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in files},
        this_scope_decoded_bytes=32, this_scope_budget_bytes=128, previous_scope_unchanged=True,
        game_process_accessed=False)
    with (OUT / "manifest.json").open("x", encoding="ascii") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps(dict(manifest=pin(OUT / "manifest.json"), findings=pin(OUT / "findings.json"))))


if __name__ == "__main__":
    main()
