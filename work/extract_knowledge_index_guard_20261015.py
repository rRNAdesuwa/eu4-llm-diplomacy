"""Replay retained narrow native instructions against the fixed PE; no decoding."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget


def pin(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    source = ROOT / "work/reports/war-peace-api-20261015-r4/peace/lifecycle/analysis.json"
    assert source.stat().st_size < 10*1024*1024
    data = json.loads(source.read_text(encoding="utf-8"))
    pe = PE(ROOT.parent / "eu4.exe")
    sha = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
    assert hashlib.sha256(pe.data).hexdigest() == sha == data["game_sha256"]
    functions = {}
    for key in ("0x289b50", "0x28d810"):
        rows = data["functions"][key]["instructions"]
        for row in rows:
            raw = bytes.fromhex(row["bytes"])
            assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw
        functions[key] = {"retained_json_pointer": "/functions/"+key,
            "instructions": rows, "replayed_bytes": sum(len(bytes.fromhex(row["bytes"])) for row in rows)}
    vt = pe.bytes_at(0x1C3A538, 64)
    output = ROOT / "work/reports/knowledge-effect-observer-20261015-r1/index-guard"
    output.mkdir(parents=True, exist_ok=True)
    report = dict(schema="EU4DIPLOMACY-KNOWLEDGE-INDEX-GUARD-STATIC/1", game_sha256=sha,
        evidence_kind="retained_ordinary_instructions_replayed_against_fixed_PE", image_base=hex(pe.base),
        retained_source={"path": str(source), **pin(source)}, functions=functions,
        index_vtable={"rva": "0x1c3a538", "raw_hex": vt.hex(), "sha256": hashlib.sha256(vt).hexdigest(),
            "slots": {hex(i): hex(struct.unpack_from("<Q", vt, i)[0]-pe.base) for i in range(0, 64, 8)}},
        layout={"root_offsets": ["0x2b8", "0x2d0"], "container_bytes": 24,
            "vtable_qword": 0, "array_qword": 8, "capacity_signed_dword": 16, "count_signed_dword": 20,
            "entry_stride": 16, "counterpart_slot_signed_dword": 0, "object_pointer_qword": 8},
        evidence={"constructor_vtable_load": "0x289e3d", "recipient_vtable_store": "0x289e44",
            "recipient_array_zero": "0x289e4b", "recipient_capacity_count_zero": "0x289e52",
            "provider_vtable_store": "0x289e59", "provider_array_zero": "0x289e60",
            "provider_capacity_count_zero": "0x289e67", "capacity_read": "0x28d8c2",
            "required_count_capacity_comparison": "0x28d8d0", "reserve_call": "0x28d901",
            "used_count_read": "0x28d906", "used_count_increment_store": "0x28d91c"},
        newly_decoded_bytes=0, earlier_knowledge_new_decode_budget_used=28117,
        earlier_knowledge_new_decode_budget_limit=32768, peak_committed_bytes=check_memory_budget(),
        source_pins={str(Path(__file__).relative_to(ROOT)).replace("\\", "/"): pin(Path(__file__)),
            "work/discover_diplomacy.py": pin(ROOT/"work/discover_diplomacy.py")},
        game_process_accessed=False, native_calls=0, memory_written=False,
        limitations=["Replays two retained bounded functions, not a whole-file scan or new REA decompilation.",
            "Typed capacity guards bound reads; external consistent reads still do not prove a world epoch."])
    raw = (json.dumps(report, ensure_ascii=True, indent=2)+"\n").encode("ascii")
    path = output / "static.json"
    with path.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "replayed_bytes": sum(f["replayed_bytes"] for f in functions.values()), "newly_decoded_bytes": 0,
        "peak_committed_bytes": report["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
