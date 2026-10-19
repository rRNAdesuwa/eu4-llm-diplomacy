"""Grant one12B pdata slot and at most24B NULL successor after three reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r75-null-successor-fragment/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r75-root-authorization"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not rel.startswith("work/deps/") and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes(); COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    actual = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert actual == expected and (rel not in PINS or PINS[rel] == actual), rel
    PINS[rel] = actual
    return json.loads(raw) if rel.endswith(".json") else raw


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as f:
        f.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "owned-code.json", "failure.json"))
source = read(BASE + "source-manifest.json", pair(22012, "5e44ed379c98638b701d89d2c6e4d24ae991f0fd16c3f9c94d0a9e77a45fe2e6"))
read(BASE + "produce.py", pair(24926, "f2f620d849526ad639303436d70d82d4dede5c6372556d0a50aff06873253f0f"))
read(BASE + "entry-seed.json", pair(12644, "9a2d0ff680202f537998dd786a6b77401eb50532d16ddec1ff04f14ff01bfba1"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]
groups = {}
for label, folder, fp, mp in (
    ("root_raw_entry_review", "war-peace-api-20261016-r75-entry-independent-review", pair(4321, "59bc6a3e05eb8dac98f98aaf5ad0434fd24f2a3890d3c7077a3cf3654d0280e3"), pair(4682, "8614ea47d98395ada29522678886a7cfd9cd98c3b76fc259dd02723fc48afa22")),
    ("upstream_actual_review", "war-peace-api-20261016-r69-actual-independent-review", pair(6300, "529f00a30baeba2c1f600018455c1e050f6061429951da8ce2daf9c44de17f56"), pair(13503, "bceee11bb0cc11bb648d0b2e8d65b9862df971ecc10e161118ee762e3acf8058")),
    ("source_peer_review", "war-peace-api-20261016-r75-source-independent-review", pair(4925, "6c780ac51ba5c440d86270754865c80d89b462e094c4c5738dc1b22468a1e86a"), pair(8706, "e0011c7161f925c2140afd1d33ef0188c912b9240e0af613ccb383449868292f")),
):
    fpath, mpath = "work/reports/" + folder + "/findings.json", "work/reports/" + folder + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    if label == "upstream_actual_review":
        assert f["subject_manifest"] == pair(27579, "3ca9f6aff9c0ceffd0d0096a4ace1a1f7ff294b36acb0f88ed0c3a0f9f9ec69b")
        assert f["subject_capture"] == pair(82235, "16125c7d31832311ef0b67019b01011b2703699f05408feb33ca881692f14c65")
    else:
        assert f["subject_source_manifest"] == PINS[BASE + "source-manifest.json"] and f["subject_producer"] == PINS[BASE + "produce.py"] and f["subject_entry_seed"] == PINS[BASE + "entry-seed.json"]
        if label == "root_raw_entry_review":
            assert f["scope"] == "retained_null_edge_and_one_metadata_slot_only" and f["entry_rva"] == "0x993658"
            assert f["branch_site_rva"] == "0x993595" and f["raw_branch_hex"] == "0f84bd000000" and type(f["pdata_record_index"]) is int and f["pdata_record_index"] == 19163
    groups[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
auth = {"schema": "EU4-R75-ROOT-AUTHORIZATION/1", "sealed": True, "operation": "one-fixed-null-successor-metadata-and-fragment",
    "entry_rva": "0x993658", "branch_site_rva": "0x993595", "raw_branch_hex": "0f84bd000000",
    "pdata_record_index": 19163, "pdata_record_rva": "0x249d244", "pdata_record_bytes": 12, "max_code_bytes": 24,
    "source_manifest": PINS[BASE + "source-manifest.json"], "producer_pin": PINS[BASE + "produce.py"], "entry_seed_pin": PINS[BASE + "entry-seed.json"],
    "root_explicit_start_received": True, **groups, "sole_executor": "validation_audit", "single_attempt": True, "authorizes_retry": False,
    "source_bytes_limit": 33554432, "retained_bytes_limit": 16777216, "software_memory_limit": 805306368, "one_GiB_stop": True,
    "native_ready": False, "independent_function_entry": False, "selected_effect_verified": False,
    "scope": "One new fixedmetadata19163/12B, cachedneighbors19162/19164, then only exactbegin993658 positive interval disjoint and<=24B fullread. Otherwiseunknown0code; nobinarysearch/neighbor/prefix/fallback. InheritedNULLedge, noABI reset/D0header assumption. Nooutsidecode/callee/data/header/unwind/vslot/process/native/request/test. Rawmanifest authorizedbuffer-first prepost, twoEXESHA, normalfileclose before capture, oneclaim/noretry."
}
OUT.mkdir()
ap = save(ROOT / (BASE + "run-authorization.json"), auth)
rp = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [], "before": before, "after": PINS,
    "authorization": ap, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024, "actual_runs": 0,
    "PE_engine_decoder_game_accesses": 0, "tests_run": 0, "sole_executor": "validation_audit"})
print(json.dumps({"authorization": ap, "receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
