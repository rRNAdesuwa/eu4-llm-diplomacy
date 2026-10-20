"""Raw admission of the expected-vtable reference; no PE/engine/decoder."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-expected-vtable-reference-owner-20261016-r1/"
OLD = "work/reports/server-vtable-rip-reference-seeds-20261016-r1/"
UP = "work/reports/server-vtable-rip-scan-independent-review-20261016-r1/"
CACHE = "work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json"
OUT = ROOT / "work/reports/server-expected-vtable-reference-owner-entry-review-20261016-r2"
RAW = {}
COUNT = 0
PRIOR_FAILED_INTAKE = 452861
REPAIR_SOURCE_INTAKE = 31027


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, expected):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not rel.startswith("work/deps/") and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes(); COUNT += len(raw)
    assert COUNT <= 3 * 1024 * 1024 and pin(raw) == expected, rel
    return raw


def obj(rel):
    return json.loads(RAW[rel])


def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    with (OUT / name).open("xb") as f:
        f.write(raw)
    return pin(raw)


assert not OUT.exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "owned-code.json", "failure.json"))
RAW[BASE + "source-manifest.json"] = read(BASE + "source-manifest.json", {"bytes": 23809, "sha256": "504bcef76418cab394f46caa8905e1ee5953f45eb73c55653608b0950fb3cea0"})
source = obj(BASE + "source-manifest.json")
paths = [BASE + n for n in ("entry-seed.json", "produce.py", "budget.json")]
paths += [OLD + n for n in ("capture.json", "scan-selected-evidence.json", "scan-contract.json", "scan-final-manifest.json")]
paths += [UP + n for n in ("findings.json", "manifest.json")] + [CACHE]
for rel in paths:
    RAW[rel] = read(rel, source["source_pins"][rel])
assert pin(RAW[BASE + "produce.py"]) == {"bytes": 26813, "sha256": "e3d223a5d25980230dd6f30b119273b9f0744a8b2e72141d5da9ebb0db70519b"}
assert pin(RAW[BASE + "entry-seed.json"]) == {"bytes": 7346, "sha256": "100a6d07e63983a9106a57b9e4eb8e8815ae6468c93bc6c3a56c9bd0f78d4901"}
seed, capture, selected = obj(BASE + "entry-seed.json"), obj(OLD + "capture.json"), obj(OLD + "scan-selected-evidence.json")
assert seed["sealed"] is True and seed["source_only"] is True and seed["actual_authorized"] is False
assert seed["anchor_site_rva"] == "0x8032de" and seed["raw_anchor7_hex"] == "488d057b514b01" and seed["target_vtable_rva"] == "0x1cb8460"
row = capture["raw_encoding_scan"]["candidates"][0]
assert seed["selected_candidate_owned"] == selected["candidates"][0]
assert all(seed["selected_candidate_owned"][key] == value for key, value in row.items())
site, target, raw = 0x8032de, 0x1cb8460, bytes.fromhex("488d057b514b01")
assert len(raw) == 7 and raw[:3] == b"\x48\x8d\x05"
disp = struct.unpack("<i", raw[3:])[0]
assert disp == seed["signed_disp32"] == row["signed_disp32"] == 21713275
assert site + 7 + disp == target and row["site_rva"] == site and row["target_rva"] == target
assert all(row[k] is False for k in ("instruction_boundary_verified", "xref_verified", "function_or_constructor_verified"))
for key, rel in (("capture_source", OLD + "capture.json"), ("candidate_source", OLD + "scan-selected-evidence.json"), ("upstream_scan_final_manifest", OLD + "scan-final-manifest.json")):
    assert seed[key]["path"] == rel and {k: seed[key][k] for k in ("bytes", "sha256")} == pin(RAW[rel])
anchors = obj(CACHE)
assert capture["game_sha256"] == seed["game_sha256"] == anchors["game_sha256"] and capture["game_bytes"] == seed["game_bytes"] == anchors["game_bytes"] == 38462504
hits = [s for s in anchors["sections"] if int(s["rva"], 16) <= site and site + 7 <= int(s["rva"], 16) + s["raw_size"]]
assert len(hits) == 1 and hits[0]["name"] == ".text"
offset = hits[0]["raw_file_offset"] + site - int(hits[0]["rva"], 16)
assert offset == row["file_offset"] == 0x8026de
chunk_index = (offset - 1024) // 65536
event = capture["accounting"]["text_scan_reads"][chunk_index]
assert chunk_index == seed["selected_candidate_owned"]["selected_chunk_index"] == 128
assert event["sha256"] == seed["selected_candidate_owned"]["chunk_raw_sha256"] and event["file_offset"] <= offset and offset + 7 <= event["file_offset"] + event["returned_bytes"]
review = obj(UP + "findings.json")
assert review["sealed"] is True and review["passed"] is True and review["blocking_findings"] == []
for key, rel in (("subject_capture_pin", OLD + "capture.json"), ("subject_contract_pin", OLD + "scan-contract.json"), ("subject_scan_final_manifest_pin", OLD + "scan-final-manifest.json")):
    assert review[key] == pin(RAW[rel]) == seed["future_gate_upstream_exact_subjects"][key]
assert seed["raw_encoding_is_not_instruction_boundary"] is True and seed["class_or_mode_verified"] is False and seed["host_guard_change_authorized"] is False and seed["native_ready"] is False
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in before.items()}
assert before == after and COUNT + 1048576 + PRIOR_FAILED_INTAKE + REPAIR_SOURCE_INTAKE <= 4 * 1024 * 1024
resources = {"selected_read_bytes": COUNT, "manual_prior_inspection_allowance": 1048576, "prior_failed_completed_intake_derived": PRIOR_FAILED_INTAKE, "repair_source_intake": REPAIR_SOURCE_INTAKE, "maximum": 4 * 1024 * 1024}
OUT.mkdir()
fp = save("findings.json", {"schema": "EU4-R76-R2-INDEPENDENT-RAW-ANCHOR-REVIEW/1", "sealed": True, "passed": True, "blocking_findings": [],
    "scope": "raw_encoding_anchor_seed_only", "entry_seed_pin": before[BASE + "entry-seed.json"],
    "anchor_site_rva": "0x8032de", "raw_anchor7_hex": "488d057b514b01", "target_vtable_rva": "0x1cb8460",
    "subject_source_manifest": before[BASE + "source-manifest.json"], "subject_producer": before[BASE + "produce.py"], "subject_entry_seed": before[BASE + "entry-seed.json"],
    "selected_files_before_after": len(before), "signed_disp32": disp, "raw_RIP_arithmetic_replayed": True, "cached_file_offset": offset, "chunk_index": chunk_index,
    "future_scope": "Only unique containing interval/all7bytes and adjacent-disjoint premise, at most32metadata12B; code fromselected.begin full<=8192 elsefirst2048. Missing or unreached anchor staysunknown with no movedwindow/anchorqueue or otherref/callee/data/header/unwind/vslot follow.",
    "resources": resources, "instruction_boundary_verified": False, "function_or_constructor_verified": False,
    "class_or_mode_verified": False, "host_guard_change_authorized": False, "native_ready": False, "actual_authorized": False, "authorizes_retry": False,
    "limits": ["Raw7 inclusion/chunk identity and fullscan are pinned producer witnesses, not a repeated PE scan.", "R72 receiver/context and R74 resource text do not prove this candidate receiver/class/mode/host compatibility.", "Only rawseed gate passes; new complete sourcepeer and rootonce grant are separate. NoPE/engine/decoder/program/tests/game operation here."]})
mp = save("manifest.json", {"sealed": True, "passed": True, "before": before, "after": after, "findings": fp, "resources": resources})
print(json.dumps({"findings": fp, "manifest": mp, "resources": resources}, ensure_ascii=True))
