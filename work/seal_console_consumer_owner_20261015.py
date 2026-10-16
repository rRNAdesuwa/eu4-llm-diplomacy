"""Seal31B chained prologue and replay old caller evidence; no game access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget
OUT = ROOT / "work/reports/console-consumer-owner-20261015-r1"
PRIOR = ROOT / "work/reports/console-alternate-consumers-20261015-r1"
R4 = ROOT / "work/reports/war-peace-api-20261015-r4/war/explore-157ffe0.json"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_text())
        for relative, expected in manifest["source_pins"].items():
            assert pin(ROOT / relative) == expected, relative
        data = json.loads((OUT / "findings.json").read_text())
        assert pe.bytes_at(0x816ad0, 31).hex() == data["new_prologue"]["raw_hex"]
        print(json.dumps(dict(status="passed", new_decoded_bytes=0, source_pins=len(manifest["source_pins"]))))
        return
    assert pin(PRIOR / "manifest.json")["sha256"] == "8c73607b93e64a65d1a599917f38caecfa9c3d1404ba1002736013aedfa69b82"
    for relative, expected in json.loads((PRIOR / "manifest.json").read_text())["source_pins"].items():
        assert pin(ROOT / relative) == expected
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    raw = pe.bytes_at(0x816ad0, 31)
    rows = [dict(rva=hex(i.address), bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str)
        for i in md.disasm(raw, 0x816ad0)]
    assert b"".join(bytes.fromhex(i["bytes"]) for i in rows) == raw
    assert any(i["rva"] == "0x816ae0" and i["bytes"] == "488bf1" for i in rows)
    unwind_rva = pe.function(0x816af6)[2]
    unwind = pe.bytes_at(unwind_rva, 24)
    assert unwind[0] & 7 == 1 and unwind[0] >> 3 == 4
    chain_offset = 4 + ((unwind[2] + 1) & ~1) * 2
    chain = struct.unpack_from("<III", unwind, chain_offset)
    assert chain == (0x816ad0, 0x816af6, 0x1e030c4)
    retained = json.loads(R4.read_bytes())
    old_rows = []
    for function in retained["functions"]:
        if function["entry_rva"] == "0x8137c0":
            for key, value in function.items():
                if isinstance(value, list):
                    old_rows += [i for i in value if isinstance(i, dict) and
                        i.get("rva") in ("0x815953", "0x815956")]
    assert len(old_rows) == 2
    for i in old_rows:
        assert pe.bytes_at(int(i["rva"], 16), len(bytes.fromhex(i["bytes"]))).hex() == i["bytes"]
    result = dict(schema="EU4-CONSOLE-CONSUMER-OWNER-FINDINGS/1",
        game_sha256=hashlib.sha256(pe.data).hexdigest(), evidence_kind="fixed_PE_static_only",
        new_prologue=dict(start="0x816ad0", end_exclusive="0x816aef", raw_hex=raw.hex(), instructions=rows,
            selected_this_assignment_rva="0x816ae0", conclusion="RSI is RCX=this at entry816ad0."),
        unwind_chain=dict(rva=hex(unwind_rva), raw_hex=unwind.hex(),
            version=1, flags=4, chained_pdata=[hex(i) for i in chain],
            conclusion="The816af6 body is chained to the816ad0 prologue."),
        retained_R4_caller=dict(path=R4.relative_to(ROOT).as_posix(), source_pin=pin(R4), instructions=old_rows,
            conclusion="Retained8137c0 frame passes R13 in RCX to816ab0, not directly to816ad0."),
        owner_is_entry_this=True, owner_equals_game_server_proven=False,
        unresolved_bridge="816ab0 to816ad0 has no retained decoded proof in the selected evidence.",
        gate="BYTE[this+19f1]==0 is required by the selected map-side toggle.",
        current_gate_value=None, gate_business_meaning="unknown", business_ironman_claimed=False,
        resources=dict(new_prologue_bytes=31, previous_shared_scope_bytes=8161,
            shared_scope_accounted_bytes=8192, shared_scope_limit=8192,
            peak_committed_bytes=check_memory_budget()),
        game_process_accessed=False, native_calls=0, keys_sent=0, memory_written=False)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "findings.json").open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    files = [OUT / "findings.json", Path(__file__), ROOT / "work/discover_diplomacy.py",
        R4, PRIOR / "manifest.json", PRIOR / "findings.json"]
    manifest = dict(schema="EU4-CONSOLE-CONSUMER-OWNER-MANIFEST/1",
        source_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in files},
        shared_scope_bytes=8192, game_process_accessed=False)
    with (OUT / "manifest.json").open("x", encoding="ascii") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps(dict(manifest=pin(OUT / "manifest.json"), findings=pin(OUT / "findings.json"))))


if __name__ == "__main__":
    main()
