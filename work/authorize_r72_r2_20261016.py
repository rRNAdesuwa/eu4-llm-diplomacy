"""Bind one R72 R2 containing-fragment acquisition to three passed reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-vtable-current-reference-owner-20261016-r2/"
OUT = ROOT / "work/reports/server-vtable-current-reference-owner-root-authorization-20261016-r2"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected):
    global COUNT
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and not rel.startswith("work/deps/")
    assert path.stat().st_size <= 4 * 1024 * 1024
    raw = path.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    actual = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert actual == expected, rel
    assert rel not in PINS or PINS[rel] == actual
    PINS[rel] = actual
    return json.loads(raw) if rel.endswith(".json") else raw


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE + name)).exists() for name in (
    "run-authorization.json", "claim.json", "capture.json", "owned-code.json", "failure.json"))
source = read(BASE + "source-manifest.json", pair(24090, "ba3735d36f60978d6bfff31c6740eabacd3427b7944832d888999882db52a6c4"))
read(BASE + "produce.py", pair(26805, "902a2908148870876719f8b086553ea553e87cf9000703af61787be87d9a875d"))
read(BASE + "entry-seed.json", pair(4236, "0ad3aeb8e360b020b238185778a3d0d1718b24323b00d44b4267bec25da749af"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]
groups = {}
for label, directory, fp, mp in (
    ("raw", "server-vtable-current-reference-owner-entry-review-20261016-r2",
     pair(2114, "8d7ed1e0093f72e8451886d92086ae953475f1007b05aff27521c347d36814f4"),
     pair(4733, "23eb03d7e983cdd4298585a55202a7f6ed6795496babcec32ecf8c39d01f04a3")),
    ("upstream_scan_review", "server-vtable-rip-scan-independent-review-20261016-r1",
     pair(2257, "bc8f828d2d71621ccc30959f81afd684d3d8d2b6f0189474fceb3a601646aedb"),
     pair(17965, "d9f438ec46b226b867cecf5f9ce3ccf22388a93cd23a7a82e57ea624941d8ee3")),
    ("source_peer_review", "server-vtable-current-reference-owner-source-independent-review-20261016-r2",
     pair(7896, "0d379a3bbd3879d948e0ff9dd8cacf2453855e9ddcafb5977c592da88a4fc3cc"),
     pair(15775, "9875840d31adc6c69ba1f59ada5e0004a1aeddf582c431bac6bf754915357556")),
):
    fpath = "work/reports/" + directory + "/findings.json"
    mpath = "work/reports/" + directory + "/manifest.json"
    findings, manifest = read(fpath, fp), read(mpath, mp)
    assert findings["sealed"] is True and findings["passed"] is True
    assert findings["blocking_findings"] == [] and manifest["sealed"] is True
    if label == "raw":
        assert findings["scope"] == "raw_encoding_anchor_seed_only"
        assert findings["anchor_site_rva"] == "0x10d24e3"
        assert findings["raw_anchor7_hex"] == "488d05de83c800"
        assert findings["target_vtable_rva"] == "0x1d5a8c8"
        assert findings["entry_seed_pin"] == PINS[BASE + "entry-seed.json"]
    elif label == "upstream_scan_review":
        assert findings["subject_capture_pin"] == pair(183377, "a1617598ee9590932e87f3fa59859b56cf8c97830fed6d1d10fd0bd83bed39ea")
        assert findings["subject_contract_pin"] == pair(7770, "d36ef8c7109830e91da79f7b6f8c01f133e867de8c41af05e2d0c8393473f83e")
        assert findings["subject_scan_final_manifest_pin"] == pair(17554, "eef0e71e6a3eedc9d85ac016436d64b0d4e3bc9164177fe9c97059e0d56aff13")
    else:
        assert findings["subject_source_manifest"] == PINS[BASE + "source-manifest.json"]
        assert findings["subject_producer"] == PINS[BASE + "produce.py"]
        assert findings["subject_entry_seed"] == PINS[BASE + "entry-seed.json"]
    groups[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
before = dict(PINS)
for rel, expected in before.items():
    read(rel, expected)
authorization = {
    "schema": "EU4-R72-ROOT-AUTHORIZATION/1", "sealed": True,
    "operation": "one-containing-pdata-fragment-only",
    "anchor_site_rva": "0x10d24e3", "raw_anchor7_hex": "488d05de83c800", "target_vtable_rva": "0x1d5a8c8",
    "source_manifest": PINS[BASE + "source-manifest.json"], "producer_pin": PINS[BASE + "produce.py"],
    "entry_seed_pin": PINS[BASE + "entry-seed.json"],
    "root_explicit_start_received": True, "seed_review_passed": True,
    "seed_review_path": groups["raw"]["findings"]["path"],
    "seed_review_pin": {k: groups["raw"]["findings"][k] for k in ("bytes", "sha256")},
    "root_review_manifest": groups["raw"]["manifest"],
    "upstream_scan_review": groups["upstream_scan_review"], "source_peer_review": groups["source_peer_review"],
    "sole_executor": "validation_audit", "single_attempt": True, "authorizes_retry": False,
    "R1_remains_blocked": True, "metadata_record_limit": 32, "metadata_record_bytes": 12,
    "code_window": "Only unique containing selected.begin: complete extent<=8192, else first2048; missing anchor remains unknown, no second window or independent anchor CFG seed.",
    "source_bytes_limit": 33554432, "retained_bytes_limit": 16777216,
    "software_memory_limit": 805306368, "one_GiB_stop": True,
    "source_engine_pre_post_guards": True, "two_EXE_SHA256": True,
    "native_ready": False, "host_guard_change_authorized": False, "reader_adoption_allowed": False,
    "scope": "One disk-only containing-fragment acquisition and retained sealing. No additional reference, callee, virtual slot, context, header, unwind, data, process, UI, save, native call, request or test. Capture only after normal targetfile close and final guards."
}
OUT.mkdir()
ap = save(ROOT / (BASE + "run-authorization.json"), authorization)
rp = save(OUT / "receipt.json", {
    "sealed": True, "passed": True, "blocking_findings": [], "before": before, "after": PINS,
    "authorization": ap, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024,
    "PE_engine_decoder_game_accesses": 0, "tests_run": 0, "actual_runs": 0,
    "sole_executor": "validation_audit", "authorizes_retry": False
})
print(json.dumps({"authorization": ap, "receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
