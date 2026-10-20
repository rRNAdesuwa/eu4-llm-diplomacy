"""Independent retained-only scan replay. No target, scanner or test execution."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-vtable-rip-reference-seeds-20261016-r1/"
OUT = ROOT / "work/reports/server-vtable-rip-scan-independent-review-20261016-r1"
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
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode()
    with (OUT / name).open("xb") as f:
        f.write(raw)
    return pin(raw)


assert not OUT.exists()
OUT.mkdir()
expected = {
    BASE + "scan-final-manifest.json": {"bytes": 17554, "sha256": "eef0e71e6a3eedc9d85ac016436d64b0d4e3bc9164177fe9c97059e0d56aff13"},
    BASE + "scan-delivery-manifest.json": {"bytes": 2615, "sha256": "5100a271efdbaefb87625e490bb387714dbbe3ae3cc830dda3b5e866b02c08c5"},
}
for rel, value in tuple(expected.items()):
    RAW[rel] = read(rel, value)
for name, count in (("scan-final-manifest.json", 36), ("scan-delivery-manifest.json", 12)):
    m = obj(BASE + name)
    assert m["sealed"] is True and len(m["source_pins"]) == count
    for rel, value in m["source_pins"].items():
        if rel in expected:
            assert expected[rel] == value
        expected[rel] = value
        if rel not in RAW:
            RAW[rel] = read(rel, value)
c = obj(BASE + "capture.json")
assert pin(RAW[BASE + "capture.json"]) == {"bytes": 183377, "sha256": "a1617598ee9590932e87f3fa59859b56cf8c97830fed6d1d10fd0bd83bed39ea"}
source = obj(BASE + "source-manifest.json")
assert c["sealed"] is True and c["source_guard_equal"] is True
assert c["source_pre"] == c["source_post"] == source["source_pins"] and len(c["source_pre"]) == 14
for rel, value in c["source_pre"].items():
    assert pin(RAW[rel]) == value
auth = obj(BASE + "run-authorization.json")
assert c["admission"]["authorization_pin"] == pin(RAW[BASE + "run-authorization.json"])
assert c["admission"]["reviews"] == auth["reviews"]
assert all(c["subjects"][k] == auth[k] for k in c["subjects"])
assert c["subjects"]["subject_source_manifest"] == pin(RAW[BASE + "source-manifest.json"])
assert obj(BASE + "claim.json")["subjects"] == c["subjects"]
assert obj(BASE + "claim.json")["single_attempt"] is True
for group in auth["reviews"].values():
    f, m = obj(group["findings"]["path"]), obj(group["manifest"]["path"])
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
assert obj(auth["first_owned_fixture_receipt"]["path"])["first_test_method_count"] == 10
assert obj(auth["first_owned_fixture_receipt"]["path"])["first_suite_executions"] == 1
scan, ac = c["raw_encoding_scan"], c["accounting"]
assert scan["status"] == "bounded_raw_encoding_scan_complete" and scan["complete_selected_segment_scan"] is True
assert scan["overflow"] is None and scan["per_target_retained_counts"] == {"0x1cb8460": 2, "0x1d5a8c8": 2}
assert scan["text_rva"] == 4096 and scan["text_file_offset"] == 1024 and scan["text_raw_size"] == 28724736
chunks = ac["text_scan_reads"]
assert len(chunks) == scan["chunk_count"] == 439
offset, reused, starts = 1024, 0, 0
for i, event in enumerate(chunks):
    size = 65536 if i < 438 else 19968
    carry = 0 if i == 0 else 6
    assert event["file_offset"] == offset and event["rva"] == offset + 3072
    assert event["requested_bytes"] == event["returned_bytes"] == size and event["complete"] is True
    assert event["carry_bytes_before"] == carry
    assert len(bytes.fromhex(event["head6_hex"])) == len(bytes.fromhex(event["tail6_hex"])) == 6
    assert re.fullmatch("[0-9a-f]{64}", event["sha256"])
    offset += size; reused += carry; starts += size + carry - 6
assert offset - 1024 == scan["file_bytes_consumed"] == ac["text_scan_returned_bytes"] == 28724736
assert reused == scan["memory_carry_reused_bytes_not_file_reads"] == 2628
assert scan["scanner_input_bytes_including_reused_carry"] == 28727364
assert starts == scan["complete_7byte_window_starts_examined"] == 28724730
wanted = [(0x8032DE, "488d057b514b01", 0x1CB8460), (0x80B58F, "488d05cace4a01", 0x1CB8460),
          (0x10D24E3, "488d05de83c800", 0x1D5A8C8), (0x10D2C1F, "488d05a27cc800", 0x1D5A8C8)]
assert len(scan["candidates"]) == 4
replayed = []
for row, (site, raw_hex, target) in zip(scan["candidates"], wanted):
    raw = bytes.fromhex(row["raw7_hex"])
    assert len(raw) == 7 and row["raw7_hex"] == raw_hex and row["site_rva"] == site
    assert raw[0] in (0x48, 0x4C) and raw[1] == 0x8D and raw[2] & 0xC7 == 5
    displacement = struct.unpack("<i", raw[3:])[0]
    assert row["signed_disp32"] == displacement and site + 7 + displacement == target == row["target_rva"]
    assert row["file_offset"] == site - 3072 and 1024 <= row["file_offset"] <= offset - 7
    assert all(row[k] is False for k in ("instruction_boundary_verified", "xref_verified", "function_or_constructor_verified"))
    replayed.append({"site_rva": hex(site), "raw7_hex": raw_hex, "signed_disp32": displacement,
                     "arithmetic_target_rva": hex(target), "instruction_boundary_verified": False,
                     "raw_bytes_inclusion_and_complete_search_are_producer_witness": True})
sha = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
assert c["game_bytes"] == 38462504 and c["game_sha256"] == sha
for item in (c["before_SHA"], c["after_SHA"]):
    assert item["complete"] is True and item["sha256"] == sha and item["returned_bytes"] == 38462504
assert ac["full_PE_SHA_reads"] == [c["before_SHA"], c["after_SHA"]]
assert ac["full_PE_SHA_returned_bytes"] == 76925008 and c["all_target_PE_returned_bytes"] == 105649744
assert ac["source_returned_bytes"] == sum(x["returned_bytes"] for x in ac["source_reads"]) == 372845
for event in ac["source_reads"]:
    assert event["complete"] is True and event["returned_bytes"] == event["expected_bytes"]
    assert {"bytes": event["returned_bytes"], "sha256": event["sha256"]} == pin(RAW[event["path"]])
assert c["normal_target_context_exit"] is True and c["commit_after_target_close_and_final_guards"] is True
for key in ("new_context_header_pdata_unwind_callee_virtualslot_reads", "new_decoder_engine_imports", "game_process_accesses", "Frida_operations", "native_game_calls", "requests", "tests"):
    assert c[key] == 0
for key in ("instruction_boundary_verified", "xref_verified", "function_constructor_verified", "RTTI_absence_verified", "class_or_mode_verified", "host_guard_change_authorized", "native_ready", "world_lease", "atomic_snapshot", "authorizes_retry", "further_actual_authorized", "hard_Job_installed_by_driver"):
    assert c[key] is False
r = obj(BASE + "scan-acquisition-receipt.json")
assert r["sealed"] is True and r["passed"] is True and r["first_producer_executions"] == 1
assert r["pre"] == r["post"] and r["pre_post_equal"] is True and r["failure_files"] == []
job = r["job"]
assert job["exit_code"] == 0 and job["error"] is None and job["job_active_processes_final"] == 0
assert job["job_total_processes"] == 2 and job["direct_child_collected"] is True
assert job["peak_job_commit"] < job["memory_limit"] == 768 * 1024 * 1024
assert r["all_owned_children_collected"] is True and r["all_shells_collected"] is True
assert pin(RAW[BASE + "scan-producer.stdout.json"]) == r["stdout"]
assert pin(RAW[BASE + "scan-producer.stderr.txt"]) == r["stderr"] and r["stderr"]["bytes"] == 0
contract = obj(BASE + "scan-contract.json")
assert contract["sealed"] is True and contract["subject_capture_pin"] == pin(RAW[BASE + "capture.json"])
assert contract["candidate_count"] == 4 and all(v is False for v in contract["authority"].values())
assert obj(BASE + "scan-filecheck.json")["passed"] is True
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in expected.items()}
assert before == after
resources = {"selected_read_bytes": COUNT, "prior_manual_allowance": 1048576,
             "bounded_upper": COUNT + 1048576, "maximum": 16 * 1024 * 1024}
assert resources["bounded_upper"] <= resources["maximum"]
rp = save("raw-replay.json", {"sealed": True, "candidates": replayed, "journal_chunks": 439,
    "physical_text_bytes": 28724736, "carry_reused_not_file_reads": 2628, "scanner_input_bytes": 28727364,
    "two_SHA_bytes_separate": 76925008, "new_target_PE_reads": 0, "native_ready": False})
fp = save("findings.json", {"schema": "EU4-R70-RIP-ENCODING-SCAN-INDEPENDENT-REVIEW/1", "sealed": True,
    "passed": True, "blocking_findings": [], "subject_capture_pin": before[BASE + "capture.json"],
    "subject_scan_final_manifest_pin": before[BASE + "scan-final-manifest.json"],
    "subject_contract_pin": before[BASE + "scan-contract.json"], "selected_files_pre_post": len(before),
    "author_manifest_pins": 36, "delivery_pins": 12, "retained_candidate_count": 4, "raw_replay": rp,
    "raw_arithmetic_replayed": True, "source_and_delivery_pins_equal": True, "resources": resources,
    "authority": contract["authority"],
    "limits": ["Raw7/disp32/RIP arithmetic and journal continuity/counts are independently replayed from retained data.",
               "Full-scan completeness, exact candidate-byte inclusion in the target, chunk SHA values and target before/after authentication remain fixed-producer witnesses; no target re-scan.",
               "Raw candidates do not prove instruction boundary, xref, constructor, class, runtime mode, layout or host compatibility. No vtable guard changes.",
               "All current selected source and delivery files were hashed before and after; no recursive older source graph or engine body read.",
               "No scanner, fixture, producer, game query, native operation or original request repeated. Next containing-metadata fragment requires a new explicit scope and grant."]})
mp = save("manifest.json", {"sealed": True, "before": before, "after": after, "findings": fp, "raw_replay": rp, "resources": resources})
print(json.dumps({"passed": True, "findings": fp, "manifest": mp, "resources": resources}, ensure_ascii=True))
