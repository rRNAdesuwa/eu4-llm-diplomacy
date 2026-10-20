"""Bind one expected-vtable containing owner to three passed reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-expected-vtable-reference-owner-20261016-r1/"
OUT = ROOT / "work/reports/server-expected-vtable-reference-owner-root-authorization-20261016-r1"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected):
    global COUNT
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and not rel.startswith("work/deps/") and path.stat().st_size <= 4 * 1024 * 1024
    raw = path.read_bytes(); COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    value = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert value == expected and (rel not in PINS or PINS[rel] == value), rel
    PINS[rel] = value
    return json.loads(raw) if rel.endswith(".json") else raw


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as f:
        f.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "owned-code.json", "failure.json"))
source = read(BASE + "source-manifest.json", pair(23809, "504bcef76418cab394f46caa8905e1ee5953f45eb73c55653608b0950fb3cea0"))
read(BASE + "produce.py", pair(26813, "e3d223a5d25980230dd6f30b119273b9f0744a8b2e72141d5da9ebb0db70519b"))
read(BASE + "entry-seed.json", pair(7346, "100a6d07e63983a9106a57b9e4eb8e8815ae6468c93bc6c3a56c9bd0f78d4901"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]
groups = {}
for label, folder, fp, mp in (
    ("raw", "server-expected-vtable-reference-owner-entry-review-20261016-r2", pair(2103, "56eb1c68aa37e1ba7f5cd8ac298652db0fa267dd7ef4f849bfd7913f51ef86bc"), pair(4827, "1c588de1c88510e6ea2813245e3a0bde19aaef3161bc6697216261c721211294")),
    ("upstream_scan_review", "server-vtable-rip-scan-independent-review-20261016-r1", pair(2257, "bc8f828d2d71621ccc30959f81afd684d3d8d2b6f0189474fceb3a601646aedb"), pair(17965, "d9f438ec46b226b867cecf5f9ce3ccf22388a93cd23a7a82e57ea624941d8ee3")),
    ("source_peer_review", "server-expected-vtable-reference-owner-source-independent-review-20261016-r1", pair(21819, "96d998932908496f884127f3179c4a400dddfea2cc8b60fd9d0d1775242306aa"), pair(16915, "e6817e1e64912cda4c15200d4f8ab0aa1284270404ce82a551d965730d21e2a7")),
):
    fpath, mpath = "work/reports/" + folder + "/findings.json", "work/reports/" + folder + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    if label == "raw":
        assert f["scope"] == "raw_encoding_anchor_seed_only" and f["anchor_site_rva"] == "0x8032de" and f["raw_anchor7_hex"] == "488d057b514b01" and f["target_vtable_rva"] == "0x1cb8460"
        assert f["entry_seed_pin"] == PINS[BASE + "entry-seed.json"]
    elif label == "upstream_scan_review":
        assert f["subject_capture_pin"] == pair(183377, "a1617598ee9590932e87f3fa59859b56cf8c97830fed6d1d10fd0bd83bed39ea")
        assert f["subject_contract_pin"] == pair(7770, "d36ef8c7109830e91da79f7b6f8c01f133e867de8c41af05e2d0c8393473f83e")
        assert f["subject_scan_final_manifest_pin"] == pair(17554, "eef0e71e6a3eedc9d85ac016436d64b0d4e3bc9164177fe9c97059e0d56aff13")
    else:
        assert f["subject_source_manifest"] == PINS[BASE + "source-manifest.json"] and f["subject_producer"] == PINS[BASE + "produce.py"] and f["subject_entry_seed"] == PINS[BASE + "entry-seed.json"]
    groups[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
auth = {"schema": "EU4-R76-ROOT-AUTHORIZATION/1", "sealed": True, "operation": "one-containing-pdata-fragment-only",
    "anchor_site_rva": "0x8032de", "raw_anchor7_hex": "488d057b514b01", "target_vtable_rva": "0x1cb8460",
    "source_manifest": PINS[BASE + "source-manifest.json"], "producer_pin": PINS[BASE + "produce.py"], "entry_seed_pin": PINS[BASE + "entry-seed.json"],
    "root_explicit_start_received": True, "seed_review_passed": True,
    "seed_review_path": groups["raw"]["findings"]["path"], "seed_review_pin": {k: groups["raw"]["findings"][k] for k in ("bytes", "sha256")},
    "root_review_manifest": groups["raw"]["manifest"], "upstream_scan_review": groups["upstream_scan_review"], "source_peer_review": groups["source_peer_review"],
    "sole_executor": "diplomacy_static", "single_attempt": True, "authorizes_retry": False, "source_bytes_limit": 33554432,
    "retained_bytes_limit": 16777216, "software_memory_limit": 805306368, "one_GiB_stop": True,
    "native_ready": False, "host_guard_change_authorized": False, "reader_adoption_allowed": False,
    "scope": "One disk-only containing fragment for8032de. At most32metadata12B; selectedbegin full<=8192 elsefirst2048. Uncovered/unreached anchor remainsunknown, no movedwindow/anchorqueue. Nootherref/callee/data/GUIfile/vslot/header/unwind/process/UI/native/request/test follow. TwoEXESHA, rawmanifest pin-before-parse and allsource/auth/reviews before/after, normal targetclose before capture, oneclaim/noretry."
}
OUT.mkdir()
ap = save(ROOT / (BASE + "run-authorization.json"), auth)
rp = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [], "before": before, "after": PINS,
    "authorization": ap, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024, "actual_runs": 0,
    "PE_engine_decoder_game_accesses": 0, "tests_run": 0, "sole_executor": "diplomacy_static"})
print(json.dumps({"authorization": ap, "receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
