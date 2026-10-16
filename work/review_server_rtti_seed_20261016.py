"""Independent retained-file DATA-entry review; no target or parser execution."""
import ast
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
HERE = "work/reports/server-vtable-rtti-20261016-r1/"
OUT = ROOT / "work/reports/server-vtable-rtti-data-seed-review-20261016-r1"
LIMIT = 16 * 1024 * 1024
READ = 0
RAW = {}


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, expected=None):
    global READ
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and path != ROOT
    size = path.stat().st_size
    assert size <= 4 * 1024 * 1024 and READ + size <= LIMIT
    raw = path.read_bytes()
    READ += len(raw)
    assert len(raw) == size
    if expected is not None:
        assert pin(raw) == expected, rel
    return raw


def obj(rel):
    return json.loads(RAW[rel])


def save(name, value):
    raw = (json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n").encode()
    with (OUT / name).open("xb") as f:
        f.write(raw)
    return pin(raw)


assert not OUT.exists(), "independent review already attempted"
OUT.mkdir()
expected = {
    HERE + "source-manifest.json": {"bytes": 3887, "sha256": "da6e70ee360f4f233e908ad61fc72f22c457136ddab4c71afcdc0e78f64b7605"},
    HERE + "final-manifest.json": {"bytes": 5396, "sha256": "b817406cad3e887cc532fabffcce055100c4b8ad4f3d564aad40ef3daef14eac"},
    HERE + "entry-seed.json": {"bytes": 4517, "sha256": "63f16776e439a3e7ebc69a5c57d184a83c2cc5a46783cb372cbc181a9bb50eaf"},
}
for rel, value in tuple(expected.items()):
    RAW[rel] = read(rel, value)
source = obj(HERE + "source-manifest.json")
delivery = obj(HERE + "final-manifest.json")
assert source["sealed"] is True and delivery["sealed"] is True
assert len(source["source_pins"]) == 18 and len(delivery["source_pins"]) == 27
for graph in (source["source_pins"], delivery["source_pins"]):
    for rel, value in graph.items():
        if rel in expected:
            assert expected[rel] == value
        expected[rel] = value
        if rel not in RAW:
            RAW[rel] = read(rel, value)
assert source["runtime_capture_authorized"] is False and source["native_ready"] is False
seed = obj(HERE + "entry-seed.json")
capture_rel = "work/reports/peace-current-pending-observer-live-20261016-r1/capture.json"
capture = obj(capture_rel)
assert seed["capture_pin"] == pin(RAW[capture_rel])
assert seed["capture_final_manifest_pin"] == pin(RAW["work/reports/peace-current-pending-observer-live-20261016-r1/final-manifest.json"])
assert capture["status"] == "unknown" and capture["samples"] == []
assert capture["precheck"] is None and capture["postcheck"] is None
assert capture["selected_queue_presence"] is None and capture["commit_after_context_exit"] is False
journal = capture["raw_ordered_read_journal"]
assert len(journal) == 19
for witness in seed["captured_raw_witnesses"]:
    assert witness == journal[witness["ordinal"] - 1]
base = int(journal[0]["address"], 16)
assert base == int(seed["live_base_for_arithmetic_only"], 16)
qword = lambda row: int.from_bytes(bytes.fromhex(row["raw_hex"]), "little")
game = qword(journal[1])
assert int(journal[1]["address"], 16) == base + 0x233FE78
assert int(journal[6]["address"], 16) == game + 0x1E00
server = qword(journal[6])
assert int(journal[7]["address"], 16) == server
assert journal[7]["raw_hex"] == seed["captured_vtable_raw"]
candidate = qword(journal[7]) - base
assert candidate == seed["captured_vtable_rva"] == 0x1D5A8C8
assert seed["vtable_rvas"] == [0x1CB8460, candidate]
for before, after in ((1, 12), (6, 17), (7, 18)):
    assert journal[before]["address"] == journal[after]["address"]
    assert journal[before]["raw_hex"] == journal[after]["raw_hex"]
observer = RAW["bridge/diplomacy_effect_observer.py"].decode("utf-8")
roots = next(x for x in ast.parse(observer).body if isinstance(x, ast.FunctionDef) and x.name == "roots")
assert 'require(r.q(server) == base+0x1CB8460, "Single player server type changed")' in ast.get_source_segment(observer, roots)
assert seed["frozen_expected_vtable_rva"] == 0x1CB8460
anchors_rel = "work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json"
anchors = obj(anchors_rel)
profile = seed["mapping_profile"]
assert seed["target_sha256"] == anchors["game_sha256"] == capture["game_sha256"]
assert seed["target_bytes"] == anchors["game_bytes"] == profile["game_bytes"] == 38462504
optional = bytes.fromhex(anchors["PE_header_reads"][2]["raw_hex"])
assert len(optional) == 240 and struct.unpack_from("<H", optional)[0] == 0x20B
preferred = struct.unpack_from("<Q", optional, 24)[0]
assert preferred == 0x140000000 == profile["preferred_image_base"]
base_evidence = seed["preferred_base_evidence"]
assert base_evidence["raw_hex"] == optional[24:32].hex()
assert base_evidence["unsigned_little_endian"] == preferred
assert base_evidence["source_pin"] == pin(RAW[anchors_rel])
table = bytes.fromhex(anchors["PE_header_reads"][3]["raw_hex"])
assert len(table) == 40 * len(profile["sections"]) == 280
for i, section in enumerate(profile["sections"]):
    raw = table[i * 40:(i + 1) * 40]
    assert raw.hex() == anchors["sections"][i]["section_header_raw_hex"]
    name = raw[:8].split(b"\0")[0].decode("ascii")
    _, rva, raw_size, raw_offset = struct.unpack_from("<IIII", raw, 8)
    assert section == {"name": name, "rva": rva, "raw_size": raw_size, "raw_file_offset": raw_offset}
plans = []
for vt in seed["vtable_rvas"]:
    hits = [s for s in profile["sections"] if s["rva"] <= vt - 8 and vt <= s["rva"] + s["raw_size"]]
    assert len(hits) == 1 and hits[0]["name"] == ".rdata"
    s = hits[0]
    plans.append({"vtable_rva": hex(vt), "locator_slot_rva": hex(vt - 8),
                  "file_offset": s["raw_file_offset"] + vt - 8 - s["rva"], "requested_bytes": 8,
                  "section": s["name"], "next_two_addresses_unknown_before_actual": True})
assert [x["file_offset"] for x in plans] == [30111320, 30776000]
live = seed["live_review"]
review = obj(live["findings"]["path"])
assert review["sealed"] is True and review["passed"] is True and review["blocking_findings"] == []
assert review["subject_capture_pin"] == seed["capture_pin"]
assert review["subject_final_manifest_pin"] == seed["capture_final_manifest_pin"]
assert all(seed[k] is False for k in ("raw_RTTI_names_currently_known", "runtime_host_supported", "host_guard_change_authorized", "native_ready"))
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in expected.items()}
assert before == after
resources = {"selected_read_bytes": READ, "prior_manual_allowance": 1024 * 1024,
             "bounded_upper": READ + 1024 * 1024, "maximum": LIMIT}
assert resources["bounded_upper"] <= LIMIT
findings = {
    "schema": "EU4-SERVER-VTABLE-RTTI-INDEPENDENT-DATA-SEED-REVIEW/1", "sealed": True,
    "passed": True, "blocking_findings": [], "subject_source_manifest": before[HERE + "source-manifest.json"],
    "subject_entry_seed": before[HERE + "entry-seed.json"], "source_pins_checked": 18,
    "delivery_pins_checked": 27, "selected_files_before_after": len(before),
    "raw_arithmetic": {"module_base_arithmetic_only": hex(base), "game": hex(game), "server": hex(server),
                       "captured_first_qword": hex(qword(journal[7])), "captured_candidate_rva": hex(candidate),
                       "frozen_expected_rva": "0x1cb8460", "preferred_disk_base": hex(preferred)},
    "initial_DATA_plans": plans, "subsequent_plan": "Each selected chain stops unless preferred VA, unique file mapping, signature1, pSelf and bounded printable NUL name hold; COL24 and TypeDescriptor16+at most128 follow only their selected chain.",
    "maximum_DATA_reads": 6, "maximum_DATA_requested_bytes": 352, "hard_DATA_byte_ceiling": 512,
    "resources": resources, "source_and_delivery_guard_equal": True,
    "authority": {"DATA_execution_authorized_by_this_review": False, "tests_run": 0,
                  "process_accesses": 0, "new_PE_reads": 0, "decoder_imports": 0,
                  "native_ready": False, "host_guard_change_authorized": False, "runtime_identity_verified": False,
                  "single_or_multiplayer_semantics_verified": False, "retry_authorized": False},
    "limits": ["Retained unknown path authenticates addresses and arithmetic only; no loaded-world, pause, queue, mode or effect result.",
               "R27 cached disk optional-header and section bytes were independently replayed; no new target acquisition.",
               "This review admits a future bounded DATA seed only. Independent source review, first owned fixtures and an explicit root one-shot DATA grant remain required.",
               "No virtual slots, CHD, base arrays, code, header, pdata, unwind or alternate scan are included."]}
fp = save("findings.json", findings)
mp = save("manifest.json", {"sealed": True, "schema": "EU4-RTTI-DATA-SEED-REVIEW-MANIFEST/1",
                          "before": before, "after": after, "findings": fp, "resources": resources})
print(json.dumps({"passed": True, "findings": fp, "manifest": mp, "resources": resources}, ensure_ascii=True))
