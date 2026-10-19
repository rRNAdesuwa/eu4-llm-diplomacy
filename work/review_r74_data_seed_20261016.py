"""Replay three retained RIP loads and one cached22B DATA mapping, no PE."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-current-label-data-20261016-r1/"
R72 = "work/reports/server-vtable-current-reference-owner-20261016-r2/"
OUT = ROOT / "work/reports/server-current-label-data-entry-review-20261016-r1"
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
    assert COUNT <= 3 * 1024 * 1024
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
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "attempt-claim.json", "capture.json", "failure.json"))
source = read(BASE + "source-manifest.json", pair(4424, "f698e1c6a4616280a627ff26a63e56200b2117a19cd56ff2c9259043bd0c77bc"))
read(BASE + "produce.py", pair(18606, "3fcd780d3db3460fad40e43e280bfeb666aa409d93bc322294ace72d6b8f3af3"))
seed = read(BASE + "entry-seed.json", pair(2514, "1467f4d8c5276a08659d0c33be67fb28a826904fe9290ff1abf9d5100e7d865c"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]


def prior(rel):
    return read(rel, source["source_pins"][rel])


rawseed = prior(seed["machine_seed_source"]["path"])
anchors = prior(seed["cached_section_source"]["path"])
upstream = prior(seed["upstream_R72_full_review"]["path"])
prior("work/reports/server-vtable-current-reference-owner-actual-independent-review-20261016-r2/manifest.json")
selected = read(R72 + "actual-selected-evidence.json", pair(502893, "6613fc625042220870a30ca3a1a5c4096c6f4e555cd3d4320f5372f42e0ea529"))
owned = read(R72 + "owned-code.json", pair(4824, "03bd9c4022e7812acc2b4dc77e2470af8da5b3954e2ef20fb26db0ef59809d18"))
assert upstream["sealed"] is True and upstream["passed"] is True and upstream["blocking_findings"] == []
assert upstream["subject_selected_evidence"] == PINS[R72 + "actual-selected-evidence.json"]
assert upstream["subject_owned"] == PINS[R72 + "owned-code.json"]
for field, value in seed["upstream_required_subjects"].items():
    assert upstream[field] == value
assert seed["data_rva"] == 0x1d5a190 and seed["requested_bytes"] == 22 and seed["end_exclusive"] == 0x1d5a1a6
assert seed["RIP_loads"] == rawseed["RIP_loads"]
assert rawseed["contiguous_requested_range"] == ["0x1d5a190", "0x1d5a1a6"] and rawseed["requested_bytes"] == 22
assert owned["window"] == ["0x10d23c0", "0x10d2bfd"]
raw = bytes.fromhex(owned["raw_hex"])
assert len(raw) == 2109
rows = {row["rva"]: row for row in selected["instructions"]}
context = rawseed["machine_context"]
assert {k: context[k] for k in ("bytes", "sha256")} == PINS[R72 + "actual-selected-evidence.json"]
for row in context["selected_rows"]:
    assert rows[row["rva"]] == row
    address = int(row["rva"], 16)
    value = bytes.fromhex(row["bytes"])
    assert raw[address - 0x10d23c0:address - 0x10d23c0 + len(value)] == value
cursor = 0x1d5a190
arithmetic = []
for item in seed["RIP_loads"]:
    address = int(item["site"], 16)
    value = bytes.fromhex(item["raw_hex"])
    row = rows[item["site"]]
    assert row["bytes"] == item["raw_hex"]
    assert raw[address - 0x10d23c0:address - 0x10d23c0 + len(value)] == value
    target = address + len(value) + struct.unpack("<i", value[-4:])[0]
    assert target == int(item["source_rva"], 16) == cursor
    assert any(op["rip_target_rva"] == hex(target) and op["width_bytes"] == item["bytes"] for op in row["memory_operands"])
    arithmetic.append({"site": address, "raw_hex": item["raw_hex"], "target_rva": target, "width": item["bytes"]})
    cursor += item["bytes"]
assert cursor == 0x1d5a1a6
sections = [s for s in anchors["sections"] if int(s["rva"], 16) <= 0x1d5a190 and 0x1d5a1a6 <= int(s["rva"], 16) + s["raw_size"]]
assert len(sections) == 1 and sections[0]["name"] == ".rdata"
section = sections[0]
header = bytes.fromhex(section["section_header_raw_hex"])
assert len(header) == 40 and header[:8].rstrip(b"\0") == b".rdata"
assert struct.unpack_from("<IIII", header, 8) == (section["virtual_size"], int(section["rva"], 16), section["raw_size"], section["raw_file_offset"])
file_offset = section["raw_file_offset"] + 0x1d5a190 - int(section["rva"], 16)
assert file_offset == seed["prepared_cached_mapping_plan"]["file_offset"] == 30774160
assert seed["prepared_cached_mapping_plan"]["section_header_raw_hex"] == section["section_header_raw_hex"]
assert file_offset + 22 <= seed["target_bytes"] == 38462504
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
OUT.mkdir()
f = {"schema": "EU4-R74-INDEPENDENT-RAW-DATA-SEED-REVIEW/1", "sealed": True, "passed": True, "blocking_findings": [],
    "scope": "raw_three_RIP_loads_and_cached_DATA_mapping_only",
    "subject_source_manifest": PINS[BASE + "source-manifest.json"], "subject_producer": PINS[BASE + "produce.py"],
    "subject_entry_seed": PINS[BASE + "entry-seed.json"], "data_rva": 0x1d5a190, "requested_bytes": 22,
    "end_exclusive": 0x1d5a1a6, "cached_file_offset": file_offset, "cached_section": ".rdata",
    "RIP_arithmetic": arithmetic, "retained_context_rows_equal_raw_owned": len(context["selected_rows"]),
    "precision_notes": ["Only fixed16+4+2 source loads are justified; data content remains unread. No extra sourceNUL, neighbor or different span.",
        "Destination copying, SIL0 and scanning are retained conditional machine-use context. Priorcallee/nonvolatile/alias premises remain; a string-shaped use does not establish a type/class/mode or host compatibility.",
        "R72 fullreview and rawbytes are pinned retained witnesses, not a repeated PE/engine/decoder authentication. Cached40B sectionheader is replayed from file evidence, no new targetheader read.",
        "Only rawseed/mapping gate passes here. Sourcepeer and new root once-grant remain separate; no actual claim or authorization created."],
    "resources": {"selected_read_bytes": COUNT, "manual_prior_inspection_allowance": 262144, "maximum": 4 * 1024 * 1024},
    "PE_engine_decoder_game_operations": 0, "author_programs_or_tests_run": 0,
    "actual_authorized": False, "authorizes_retry": False, "native_ready": False, "class_or_mode_verified": False,
    "host_guard_change_authorized": False, "selected_effect_verified": False, "world_lease": False, "atomic_snapshot": False}
assert COUNT + 262144 <= 4 * 1024 * 1024
fp = save(OUT / "findings.json", f)
mp = save(OUT / "manifest.json", {"schema": "EU4-R74-RAW-SEED-REVIEW-MANIFEST/1", "sealed": True, "passed": True,
    "pins": before, "findings": fp, "before_after_equal": True, "selected_read_bytes": COUNT,
    "manual_prior_inspection_allowance": 262144, "maximum": 4 * 1024 * 1024, "actual_authorized": False})
print(json.dumps({"findings": fp, "manifest": mp, "selected_read_bytes": COUNT, "files": len(PINS)}, ensure_ascii=True))
