"""Independent retained-byte review of the inherited JLE target; no decoder/PE."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/"
R69 = "work/reports/war-peace-api-20261016-r69-generator-divisor-source/"
R71 = "work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r73-entry-root-review"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected):
    global COUNT
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and not path.is_relative_to((ROOT / "work/deps").resolve())
    assert path.stat().st_size <= 4 * 1024 * 1024
    raw = path.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    value = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert value == expected, rel
    assert rel not in PINS or PINS[rel] == value
    PINS[rel] = value
    return json.loads(raw) if rel.endswith(".json") else raw


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "failure.json"))
source = read(BASE + "source-manifest.json", pair(24203, "7d06b37f47bdda3a77898f185434994d5f4f0c85d0e856eb0e9fe30bd877ca3f"))
read(BASE + "produce.py", pair(23386, "d23bc4861c7d1a2fe17ecfde2090eda3ee77a9c87cbf9f45649817b51705800b"))
seed = read(BASE + "entry-seed.json", pair(21609, "34014d40471b0f79a9ed37a5013461e4afa1a31d43e22f4558080375a6ca3ca4"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]


def prior(rel):
    return read(rel, source["source_pins"][rel])


capture = prior(R69 + "capture.json")
selected = prior(R71 + "actual-selected-evidence.json")
owned = prior(R71 + "owned-code.json")
contract = prior(R71 + "actual-contract.json")
body_manifest = prior(R71 + "actual-manifest.json")
findings = prior("work/reports/war-peace-api-20261016-r71-actual-independent-review/findings.json")
peer_manifest = prior("work/reports/war-peace-api-20261016-r71-actual-independent-review/manifest.json")
anchors_rel = "work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json"
anchors = prior(anchors_rel)
assert findings["sealed"] is True and findings["passed"] is True and findings["blocking_findings"] == []
assert peer_manifest["sealed"] is True and body_manifest["sealed"] is True
assert findings["subject_manifest"] == PINS[R71 + "actual-manifest.json"]
assert findings["subject_owned"] == PINS[R71 + "owned-code.json"]
assert findings["subject_selected"] == PINS[R71 + "actual-selected-evidence.json"]
assert findings["subject_contract"] == PINS[R71 + "actual-contract.json"]
assert seed["scope_kind"] == "inherited_branch_target_fragment"
assert seed["entry_rva"] == "0x993643" and seed["window"] == ["0x993643", "0x993658"]
assert seed["new_pdata_bytes"] == 0 and seed["new_metadata_needed"] is False
raw = bytes.fromhex(owned["raw_hex"])
assert len(raw) == 156 and owned["window"] == ["0x9935a7", "0x993643"]
short = selected["rows"][:4]
assert short == seed["R71_short_entry_to_branch_rows"]
expected = [(0x9935a7, "4c897c2478"), (0x9935ac, "4d63f8"), (0x9935af, "4585c0"), (0x9935b2, "0f8e8b000000")]
assert [(int(v["rva"], 16), v["bytes"]) for v in short] == expected
for at, text in expected:
    value = bytes.fromhex(text)
    assert raw[at - 0x9935a7:at - 0x9935a7 + len(value)] == value
branch = bytes.fromhex(expected[-1][1])
assert 0x9935b2 + len(branch) + struct.unpack("<i", branch[2:])[0] == 0x993643
assert capture["analysis"]["instructions"] == seed["R69_nonnull_predecessor_rows"]
assert capture["analysis"]["instructions"][-1]["rva"] == "0x9935a3"
assert capture["analysis"]["instructions"][-1]["bytes"] == "49c1f803"
descriptor = capture["pdata_requests"][14]
assert descriptor == seed["cached_descriptor"]
assert descriptor["index"] == 19162 and descriptor["rva"] == "0x249d238"
assert descriptor["file_offset"] == 37139000
assert descriptor["raw_hex"] == "433699005836990024dde701"
assert struct.unpack("<III", bytes.fromhex(descriptor["raw_hex"])) == (0x993643, 0x993658, 0x1e7dd24)
assert capture["game_sha256"] == anchors["game_sha256"] == seed["game_sha256"]
assert capture["game_bytes"] == anchors["game_bytes"] == seed["game_bytes"] == 38462504


def offset(rva, size, expected_section):
    candidates = [s for s in anchors["sections"] if int(s["rva"], 16) <= rva and rva + size <= int(s["rva"], 16) + s["raw_size"]]
    assert len(candidates) == 1 and candidates[0]["name"] == expected_section
    s = candidates[0]
    return s["raw_file_offset"] + rva - int(s["rva"], 16)


assert offset(0x249d238, 12, ".pdata") == 37139000
assert offset(0x993643, 21, ".text") == seed["future_code_file_offset"] == 10037827
assert -0x58 + 0x78 == 0x20
before = dict(PINS)
for rel, expected_pin in before.items():
    read(rel, expected_pin)
OUT.mkdir()
f = {"schema": "EU4-R73-INDEPENDENT-RAW-BRANCH-SEED-REVIEW/1", "sealed": True, "passed": True, "blocking_findings": [],
    "scope": "raw_inherited_branch_fragment_seed_only", "entry_rva": "0x993643", "window": ["0x993643", "0x993658"],
    "entry_seed_pin": PINS[BASE + "entry-seed.json"], "subject_entry_seed": PINS[BASE + "entry-seed.json"],
    "subject_source_manifest": PINS[BASE + "source-manifest.json"], "subject_producer": PINS[BASE + "produce.py"],
    "branch_rva": "0x9935b2", "branch_raw": "0f8e8b000000", "cached_descriptor_raw": descriptor["raw_hex"],
    "future_code_file_offset": 10037827, "selected_new_code_bytes": 21, "new_pdata_bytes": 0,
    "raw_branch_descriptor_and_cached_mappings_replayed": True,
    "inherited_state": "Only R69 nonnull continuation through R71 first four rows: F=S69-58 if priorCALL balances; R15=signextend low32R8<=0; RAX/R12 retain nonzero postCALL bits. No new function ABI or positive-path saves/body/calls at this target.",
    "precision_notes": [
        "MOV QWORD[F+78],R15 writes prior currentR15. F+78=S69+20 is an address identity, not a read/copy of the old memory value at S69+20; seed prose is interpreted only this way.",
        "R13/R14/RBP/RSI and frame correspondence need normal nonvolatile/stack premises; unknown97bd30 and aliases can change D/header/memory. Initial D0 or headerzeros are not current invariants.",
        "Only the21B fixed successor is selected. No new metadata, end993658, NULLbranch, callee, data, header, unwind, vslot, PE or decoder read; futurebytes and return remain unknown.",
        "R71 independent review and old raw capture are pinned retained witnesses, not a repeated producer/engine/PE authentication. Legacy R71 late manifest check does not exclude externalABA; R73 sourcepeer separately checks its new rawbuffer guard."
    ],
    "resources": {"selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024},
    "PE_engine_decoder_game_operations": 0, "author_programs_or_tests_run": 0,
    "actual_authorized": False, "authorizes_retry": False, "independent_entry_callable": False,
    "native_ready": False, "selected_effect_verified": False, "world_lease": False, "atomic_snapshot": False}
fp = save(OUT / "findings.json", f)
mp = save(OUT / "manifest.json", {"schema": "EU4-R73-RAW-SEED-REVIEW-MANIFEST/1", "sealed": True, "passed": True,
    "pins": before, "before_after_equal": True, "findings": fp, "selected_read_bytes": COUNT,
    "maximum": 2 * 1024 * 1024, "source_closure_reauthenticated": False, "actual_authorized": False})
print(json.dumps({"findings": fp, "manifest": mp, "selected_read_bytes": COUNT, "flat_files": len(PINS)}, ensure_ascii=True))
