"""Raw encoding anchor admission only; no code, metadata, parser or engine access."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-vtable-current-reference-owner-20261016-r2/"
OLD = "work/reports/server-vtable-rip-reference-seeds-20261016-r1/"
OUT = ROOT / "work/reports/server-vtable-current-reference-owner-entry-review-20261016-r2"
RAW = {}
COUNT = 0


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, expected=None):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not rel.startswith("work/deps/")
    assert p.suffix.lower() not in (".exe", ".dll", ".pyd") and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes(); COUNT += len(raw)
    assert COUNT <= 16 * 1024 * 1024
    if expected is not None:
        assert pin(raw) == expected, rel
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
RAW[BASE + "source-manifest.json"] = read(BASE + "source-manifest.json", {"bytes": 24090, "sha256": "ba3735d36f60978d6bfff31c6740eabacd3427b7944832d888999882db52a6c4"})
source = obj(BASE + "source-manifest.json")
paths = [BASE + n for n in ("entry-seed.json", "produce.py", "budget.json")]
paths += [OLD + n for n in ("capture.json", "scan-selected-evidence.json", "scan-contract.json", "scan-final-manifest.json")]
paths += ["work/reports/server-vtable-rip-scan-independent-review-20261016-r1/" + n for n in ("findings.json", "manifest.json")]
paths += ["work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json"]
for rel in paths:
    RAW[rel] = read(rel, source["source_pins"][rel])
seed = obj(BASE + "entry-seed.json")
capture = obj(OLD + "capture.json")
chosen = obj(OLD + "scan-selected-evidence.json")
assert seed["sealed"] is True and seed["source_only"] is True and seed["actual_authorized"] is False
assert seed["anchor_site_rva"] == "0x10d24e3" and seed["raw_anchor7_hex"] == "488d05de83c800"
assert seed["target_vtable_rva"] == "0x1d5a8c8"
row = capture["raw_encoding_scan"]["candidates"][2]
assert seed["selected_candidate_owned"] == chosen["candidates"][2]
for key, value in row.items():
    assert seed["selected_candidate_owned"][key] == value
site, target = int(seed["anchor_site_rva"], 16), int(seed["target_vtable_rva"], 16)
raw = bytes.fromhex(seed["raw_anchor7_hex"])
assert len(raw) == 7 and raw[0] in (0x48, 0x4C) and raw[1] == 0x8D and raw[2] & 0xC7 == 5
disp = struct.unpack("<i", raw[3:])[0]
assert disp == seed["signed_disp32"] == row["signed_disp32"] and site + 7 + disp == target
assert row["site_rva"] == site and row["target_rva"] == target
assert all(row[k] is False for k in ("instruction_boundary_verified", "xref_verified", "function_or_constructor_verified"))
for key, rel in (("capture_source", OLD + "capture.json"), ("candidate_source", OLD + "scan-selected-evidence.json"),
                 ("upstream_scan_contract", OLD + "scan-contract.json"), ("upstream_scan_final_manifest", OLD + "scan-final-manifest.json")):
    assert seed[key]["path"] == rel
    assert {k: seed[key][k] for k in ("bytes", "sha256")} == pin(RAW[rel])
anchors = obj("work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json")
assert capture["game_sha256"] == seed["game_sha256"] == anchors["game_sha256"]
assert capture["game_bytes"] == seed["game_bytes"] == anchors["game_bytes"] == 38462504
hits = [s for s in anchors["sections"] if int(s["rva"], 16) <= site and site + 7 <= int(s["rva"], 16) + s["raw_size"]]
assert len(hits) == 1 and hits[0]["name"] == ".text"
offset = hits[0]["raw_file_offset"] + site - int(hits[0]["rva"], 16)
assert offset == row["file_offset"] == 17635555
chunk_index = (offset - 1024) // 65536
event = capture["accounting"]["text_scan_reads"][chunk_index]
assert chunk_index == seed["selected_candidate_owned"]["selected_chunk_index"] == 269
assert event["sha256"] == seed["selected_candidate_owned"]["chunk_raw_sha256"]
assert event["file_offset"] <= offset and offset + 7 <= event["file_offset"] + event["returned_bytes"]
review = obj("work/reports/server-vtable-rip-scan-independent-review-20261016-r1/findings.json")
assert review["sealed"] is True and review["passed"] is True and review["blocking_findings"] == []
for key, rel in (("subject_capture_pin", OLD + "capture.json"), ("subject_contract_pin", OLD + "scan-contract.json"),
                 ("subject_scan_final_manifest_pin", OLD + "scan-final-manifest.json")):
    assert review[key] == pin(RAW[rel]) == seed["future_gate_upstream_exact_subjects"][key]
assert seed["upstream_raw_encoding_is_not_instruction_boundary"] is True
assert seed["constructor_class_mode_layout_or_guard_verified"] is False and seed["native_ready"] is False
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in before.items()}
assert before == after
resources = {"selected_read_bytes": COUNT, "prior_manual_allowance": 1048576,
             "bounded_upper": COUNT + 1048576, "maximum": 16 * 1024 * 1024}
assert resources["bounded_upper"] <= resources["maximum"]
fp = save("findings.json", {"schema": "EU4-R72-R2-INDEPENDENT-RAW-ANCHOR-REVIEW/1", "sealed": True,
    "passed": True, "blocking_findings": [], "scope": "raw_encoding_anchor_seed_only",
    "entry_seed_pin": before[BASE + "entry-seed.json"], "anchor_site_rva": "0x10d24e3",
    "raw_anchor7_hex": "488d05de83c800", "target_vtable_rva": "0x1d5a8c8",
    "subject_source_manifest": before[BASE + "source-manifest.json"], "subject_producer": before[BASE + "produce.py"],
    "subject_entry_seed": before[BASE + "entry-seed.json"], "selected_files_before_after": len(before),
    "signed_disp32": disp, "raw_RIP_arithmetic_replayed": True, "cached_file_offset": offset,
    "instruction_boundary_verified": False, "xref_verified": False, "function_or_constructor_verified": False,
    "future_scope": "At most32 metadata12B records for the unique containing interval, neighbors disjoint under ordered-pdata premise. One selected.begin code span: full if<=8192 else2048 prefix; missing anchor remains unknown, never move window or queue anchor independently.",
    "resources": resources, "native_ready": False, "actual_authorized": False, "authorizes_retry": False,
    "limits": ["This review binds R2 subjects only; original R1 source blocker remains closed-to-execution.",
               "Raw7/chunk identity is inherited pinned producer witness; no independent target reopen or full scan.",
               "Future metadata owner, selected span and CFG reachability are unknown. No actual class, mode, layout, store receiver or compatible host guard is established.",
               "Source peer must separately pass the R2 raw-buffer pin-before-engine correction. No PE, engine, decoder, parser, producer, test or game operation here."]})
mp = save("manifest.json", {"sealed": True, "before": before, "after": after, "findings": fp, "resources": resources})
print(json.dumps({"passed": True, "findings": fp, "manifest": mp, "resources": resources}, ensure_ascii=True))
