"""First independent retained-file replay of the two unknown RTTI chains."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-vtable-rtti-20261016-r1/"
OUT = ROOT / "work/reports/server-vtable-rtti-data-independent-review-20261016-r1"
READ = 0
RAW = {}


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, expected=None):
    global READ
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and p != ROOT
    assert p.suffix.lower() not in (".exe", ".dll", ".pyd") and not rel.startswith("work/deps/")
    assert p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes()
    READ += len(raw)
    assert READ <= 16 * 1024 * 1024
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
expected = {
    BASE + "data-final-manifest.json": {"bytes": 18410, "sha256": "150f9de9c3845a6b20bc37480dda2f310336580491b5acd6273b84f4d4622297"},
    BASE + "data-delivery-manifest.json": {"bytes": 2427, "sha256": "02bf6a2549ce93bf5b799d4bb0da38fbfdcff151e2f0857ebd363d1613c76fd0"},
}
for rel, value in tuple(expected.items()):
    RAW[rel] = read(rel, value)
for name, count in (("data-final-manifest.json", 40), ("data-delivery-manifest.json", 12)):
    graph = obj(BASE + name)
    assert graph["sealed"] is True and len(graph["source_pins"]) == count
    for rel, value in graph["source_pins"].items():
        if rel in expected:
            assert expected[rel] == value
        expected[rel] = value
        if rel not in RAW:
            RAW[rel] = read(rel, value)
c = obj(BASE + "capture.json")
contract = obj(BASE + "data-contract.json")
assert c["sealed"] is True and c["source_guard_equal"] is True
assert c["source_pre"] == c["source_post"]
source = obj(BASE + "source-manifest.json")
assert c["source_pre"] == source["source_pins"] and len(c["source_pre"]) == 18
for rel, value in c["source_pre"].items():
    assert pin(RAW[rel]) == value
auth = obj(BASE + "run-authorization.json")
assert c["authorization"]["auth_pin"] == pin(RAW[BASE + "run-authorization.json"])
assert c["authorization"]["reviews"] == auth["reviews"]
assert all(c["subjects"][k] == auth[k] for k in c["subjects"])
assert c["subjects"]["subject_source_manifest"] == pin(RAW[BASE + "source-manifest.json"])
assert obj(BASE + "attempt-claim.json")["subjects"] == c["subjects"]
assert obj(BASE + "attempt-claim.json")["single_attempt"] is True
assert obj(BASE + "root-data-invocation-claim.json")["authorization_pin"] == c["authorization"]["auth_pin"]
for group in auth["reviews"].values():
    f, m = obj(group["findings"]["path"]), obj(group["manifest"]["path"])
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
assert obj(auth["first_owned_fixture_receipt"]["path"])["first_test_method_count"] == 12
assert obj(auth["first_owned_fixture_receipt"]["path"])["first_suite_executions"] == 1
ac = c["accounting"]
events = ac["DATA_reads"]
assert len(events) == 2 and ac["DATA_returned_bytes"] == c["DATA_unique_file_bytes"] == 16
assert c["DATA_overlap_returned_bytes"] == 0
seed = obj(BASE + "entry-seed.json")
profile = seed["mapping_profile"]
preferred = profile["preferred_image_base"]
projection = []
for event, chain, raw_expected, target_expected in zip(events, c["chains"], ("60ae494101000000", "90d26e4001000000"), (0x149AE60, 0x6ED290)):
    vt = chain["vtable_rva"]
    assert vt in (0x1CB8460, 0x1D5A8C8) and event["rva"] == vt - 8
    assert event["requested_bytes"] == event["returned_bytes"] == 8 and event["complete"] is True
    assert event["raw_hex"] == raw_expected and event["section"] == ".rdata"
    hits = [s for s in profile["sections"] if s["rva"] <= vt - 8 and vt <= s["rva"] + s["raw_size"]]
    assert len(hits) == 1 and hits[0]["name"] == ".rdata"
    assert event["file_offset"] == hits[0]["raw_file_offset"] + vt - 8 - hits[0]["rva"]
    va = int.from_bytes(bytes.fromhex(raw_expected), "little")
    target = va - preferred
    assert target == target_expected
    targets = [s for s in profile["sections"] if s["rva"] <= target and target + 24 <= s["rva"] + s["raw_size"]]
    assert len(targets) == 1 and targets[0]["name"] == ".text"
    assert chain["status"] == "unknown" and chain["chain_stopped_without_alternate_search"] is True
    assert chain["unknown_reason"] == "selected DATA profile excludes code/other sections"
    assert "locator" not in chain and "COL" not in chain and "evaluation" not in chain
    projection.append({"vtable_rva": hex(vt), "read": event, "preferred_va": hex(va),
                       "arithmetic_target_rva": hex(target), "cached_segment": ".text",
                       "target_read": False, "raw_RTTI_name": None, "status": "unknown"})
assert [x["vtable_rva"] for x in c["chains"]] == seed["vtable_rvas"]
assert contract["raw_RTTI_names"] == [] and contract["subject_capture_pin"] == pin(RAW[BASE + "capture.json"])
assert contract["status"] == "both_selected_chains_unknown_after_first_QWORD"
assert c["normal_target_file_context_exit"] is True and c["commit_after_target_close_and_final_guards"] is True
sha = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
assert c["game_bytes"] == 38462504 and c["game_sha256"] == sha
for item in (c["PE_before"], c["PE_after"]):
    assert item["complete"] is True and item["sha256"] == sha and item["returned_bytes"] == 38462504
assert ac["PE_full_SHA_reads"] == [c["PE_before"], c["PE_after"]]
assert ac["PE_full_SHA_returned_bytes"] == 76925008
assert ac["source_returned_bytes"] == sum(x["returned_bytes"] for x in ac["source_read_attempts"]) == 433161
for event in ac["source_read_attempts"]:
    assert event["complete"] is True and event["returned_bytes"] == event["expected_bytes"]
    assert {"bytes": event["returned_bytes"], "sha256": event["sha256"]} == pin(RAW[event["path"]])
for key in ("code_reads", "header_reads", "pdata_reads", "unwind_reads", "virtual_function_slot_reads", "class_hierarchy_reads", "searches", "game_native_calls", "Frida_operations", "requests_published", "tests_run"):
    assert c[key] == 0
for key in ("runtime_identity_verified", "class_layout_verified", "vtable_compatibility_verified", "single_or_multiplayer_semantics_verified", "host_guard_change_authorized", "native_ready", "lease_verified", "atomic_snapshot", "selected_effect_verified", "request_effect_authenticated", "hard_job_object_installed"):
    assert c[key] is False
receipt = obj(BASE + "data-acquisition-receipt.json")
assert receipt["sealed"] is True and receipt["passed"] is True and receipt["first_producer_executions"] == 1
assert receipt["pre"] == receipt["post"] and receipt["pre_post_equal"] is True and receipt["failure_files"] == []
job = receipt["job"]
assert job["exit_code"] == 0 and job["error"] is None and job["job_active_processes_final"] == 0
assert job["job_total_processes"] == 2 and job["direct_child_collected"] is True
assert job["peak_job_commit"] < 768 * 1024 * 1024 and job["memory_limit"] == 768 * 1024 * 1024
assert receipt["all_owned_children_collected"] is True and receipt["all_shells_collected"] is True
assert pin(RAW[BASE + "data-producer.stdout.json"]) == receipt["stdout"]
assert pin(RAW[BASE + "data-producer.stderr.txt"]) == receipt["stderr"] and receipt["stderr"]["bytes"] == 0
assert obj(BASE + "data-filecheck.json")["passed"] is True
delivery = obj(BASE + "data-delivery-receipt.json")
assert delivery["all_first_pass"] is True and delivery["all_owned_children_and_shells_collected"] is True
assert all(v is False for v in contract["authority"].values())
before = {rel: pin(raw) for rel, raw in RAW.items()}
after = {rel: pin(read(rel, value)) for rel, value in expected.items()}
assert before == after
resources = {"selected_read_bytes": READ, "prior_manual_allowance": 1048576,
             "bounded_upper": READ + 1048576, "maximum": 16 * 1024 * 1024}
assert resources["bounded_upper"] <= resources["maximum"]
raw_pin = save("raw-replay.json", {"sealed": True, "projection": projection, "target_PE_bytes_retained_witness": 76925024,
               "new_target_PE_reads": 0, "native_ready": False})
findings_pin = save("findings.json", {"schema": "EU4-SERVER-VTABLE-RTTI-DATA-INDEPENDENT-REVIEW/1",
    "sealed": True, "passed": True, "blocking_findings": [],
    "subject_capture_pin": before[BASE + "capture.json"],
    "subject_data_final_manifest_pin": before[BASE + "data-final-manifest.json"],
    "subject_contract_pin": before[BASE + "data-contract.json"],
    "selected_files_pre_post": len(before), "author_actual_manifest_pins": 40, "delivery_pins": 12,
    "two_chains_unknown": True, "DATA_read_attempts": 2, "DATA_requested_and_returned_bytes": 16,
    "COL_TypeDescriptor_name_reads": 0, "raw_RTTI_names": [], "raw_replay": raw_pin,
    "authority": contract["authority"], "resources": resources,
    "limits": ["Two selected raw QWORDs map arithmetically into cached .text; target bytes were not read.",
               "No COL, TypeDescriptor, RTTI absence, class name, instruction boundary, mode or compatible host layout is established.",
               "Driver two-SHA/source/close and external Job statistics are retained execution witnesses; this review accessed no PE, process, engine or parser execution.",
               "Source graph and selected author/delivery files were independently hashed before and after. No recursive historical source closure.",
               "Current peace status remains unknown at the unchanged host guard. No second status, original request or new native operation was run."]})
manifest_pin = save("manifest.json", {"sealed": True, "schema": "EU4-RTTI-DATA-INDEPENDENT-REVIEW-MANIFEST/1",
    "before": before, "after": after, "resources": resources, "findings": findings_pin, "raw_replay": raw_pin})
print(json.dumps({"passed": True, "findings": findings_pin, "manifest": manifest_pin, "resources": resources}, ensure_ascii=True))
