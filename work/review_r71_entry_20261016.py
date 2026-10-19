"""Review only the retained inherited fallthrough seed and cached descriptor."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/"
OLD = "work/reports/war-peace-api-20261016-r69-generator-divisor-source/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r71-entry-root-review"
RAW = {}
COUNT = 0


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, value=None):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not rel.startswith("work/deps/")
    assert p.suffix.lower() not in (".exe", ".dll", ".pyd") and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes(); COUNT += len(raw)
    assert COUNT <= 16 * 1024 * 1024
    if value is not None:
        assert pin(raw) == value, rel
    return raw


def obj(rel):
    return json.loads(RAW[rel])


def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    with (OUT / name).open("xb") as f:
        f.write(raw)
    return pin(raw)


assert not OUT.exists()
OUT.mkdir()
RAW[BASE + "source-manifest.json"] = read(BASE + "source-manifest.json", {"bytes": 21135, "sha256": "6f46db3d7acb1b34391b9f821fb2347b507dac2ee18393b64d74d51f2a5b0722"})
source = obj(BASE + "source-manifest.json")
selected_paths = [BASE + n for n in ("entry-seed.json", "produce.py", "budget.json")]
selected_paths += [OLD + n for n in ("capture.json", "owned-code.json", "selected-evidence.json", "manifest.json", "contract.json")]
selected_paths += ["work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json"]
selected_paths += ["work/reports/war-peace-api-20261016-r69-actual-independent-review/" + n for n in ("findings.json", "manifest.json")]
for rel in selected_paths:
    RAW[rel] = read(rel, source["source_pins"][rel])
seed = obj(BASE + "entry-seed.json")
c, owned, chosen = obj(OLD + "capture.json"), obj(OLD + "owned-code.json"), obj(OLD + "selected-evidence.json")
code = bytes.fromhex(owned["raw_hex"])
assert len(code) == 55 and seed["predecessor_owned_raw_hex"] == owned["raw_hex"]
assert seed["predecessor_owned_pin"] == pin(RAW[OLD + "owned-code.json"])
rows = c["analysis"]["instructions"]
assert len(rows) == len(seed["predecessor_rows"]) == 18
at = 0x993570
for ordinal, (row, simplified) in enumerate(zip(rows, seed["predecessor_rows"])):
    raw = bytes.fromhex(row["bytes"])
    assert int(row["rva"], 16) == at and raw == code[at - 0x993570:at - 0x993570 + len(raw)]
    assert simplified == {"ordinal": ordinal, "rva": row["rva"], "raw_hex": row["bytes"], "mnemonic": row["mnemonic"], "operands": row["operands"]}
    at += len(raw)
assert at == 0x9935A7
assert rows[-1]["rva"] == seed["predecessor_last_rva"] == "0x9935a3"
assert rows[-1]["bytes"] == seed["predecessor_last_raw"] == "49c1f803"
assert rows[11]["bytes"] == "e8a187feff"
assert 0x99358A + 5 + struct.unpack("<i", bytes.fromhex(rows[11]["bytes"])[1:])[0] == 0x97BD30
assert rows[14]["bytes"] == "0f84bd000000"
assert 0x993595 + 6 + struct.unpack("<i", bytes.fromhex(rows[14]["bytes"])[2:])[0] == 0x993658
assert [r["bytes"] for r in rows[12:]] == ["4c8be0", "4885c0", "0f84bd000000", "4d8b4578", "4d2b4570", "49c1f803"]
descriptor = seed["cached_next_descriptor"]
assert descriptor == c["next"] and descriptor["raw_hex"] == "a73599004336990008dde701"
begin, end, unwind = struct.unpack("<III", bytes.fromhex(descriptor["raw_hex"]))
assert begin == 0x9935A7 and end == 0x993643 and unwind == 0x1E7DD08
assert end - begin == seed["future_code_bytes"] == 156
assert seed["window"] == [hex(begin), hex(end)] and seed["entry_rva"] == hex(begin)
assert c["selected"]["end_exclusive"] == hex(begin) and c["next"]["begin_rva"] == hex(begin)
assert descriptor["rva"] == "0x249d22c" and descriptor["index"] == 19161
anchors = obj("work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json")
hits = [s for s in anchors["sections"] if int(s["rva"], 16) <= begin and end <= int(s["rva"], 16) + s["raw_size"]]
assert len(hits) == 1 and hits[0]["name"] == ".text"
offset = hits[0]["raw_file_offset"] + begin - int(hits[0]["rva"], 16)
assert offset == seed["future_code_file_offset"] == 10037671
assert c["game_sha256"] == seed["game_sha256"] == anchors["game_sha256"]
review = obj("work/reports/war-peace-api-20261016-r69-actual-independent-review/findings.json")
assert review["sealed"] is True and review["passed"] is True and review["blocking_findings"] == []
assert review["subject_manifest"] == pin(RAW[OLD + "manifest.json"])
assert seed["independent_function_entry"] is False and seed["whole_function_extent_unknown"] is True
assert all(v is False for v in seed["authority"].values())
assert 5 * 8 + 0x30 == 0x58 and -0x90 + 0xB0 == 0x20 and -0x90 + 0x40 == -0x50
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in before.items()}
assert before == after
resources = {"selected_read_bytes": COUNT, "prior_manual_allowance": 1048576,
             "bounded_upper": COUNT + 1048576, "maximum": 16 * 1024 * 1024}
assert resources["bounded_upper"] <= resources["maximum"]
fp = save("findings.json", {"schema": "EU4-R71-INDEPENDENT-FALLTHROUGH-ENTRY-REVIEW/1", "sealed": True,
    "passed": True, "blocking_findings": [], "scope": "raw_fallthrough_fragment_seed_only",
    "entry_seed_pin": before[BASE + "entry-seed.json"], "entry_rva": "0x9935a7",
    "predecessor_last_rva": "0x9935a3", "predecessor_last_raw": "49c1f803",
    "cached_descriptor_raw": descriptor["raw_hex"], "subject_source_manifest": before[BASE + "source-manifest.json"],
    "subject_producer": before[BASE + "produce.py"], "subject_entry_seed": before[BASE + "entry-seed.json"],
    "raw_rows_replayed": 18, "predecessor_owned_bytes": 55, "future_code_bytes": 156,
    "future_code_file_offset": offset, "new_pdata_reads": 0, "independent_function_entry": False,
    "register_limits": "Inherited nonnull post97bd30 RAX/R12, R8 fresh R13-field difference SAR3. R13/R14/RBP/RSI and S69-58 are conditional on the unfollowed callee's normal nonvolatile/stack behavior. RCX/RDX/R9/XMM/DF unknown; no reset formal ABI or inherited D/header zero.",
    "resources": resources, "selected_files_before_after": len(before),
    "native_ready": False, "runtime_capture_authorized": False, "actual_authorized": False, "authorizes_retry": False,
    "limits": ["Only future156B inherited fragment, no JE993658/end993643/callee/data/header/unwind/metadata expansion.",
               "No body bytes acquired; this is retained raw/metadata arithmetic, not an execution, full function, return or effect proof.",
               "R69 full review role/source-peer distinction retained; no engine-body authentication repeated."]})
mp = save("manifest.json", {"sealed": True, "before": before, "after": after, "findings": fp, "resources": resources})
print(json.dumps({"passed": True, "findings": fp, "manifest": mp, "resources": resources}, ensure_ascii=True))
