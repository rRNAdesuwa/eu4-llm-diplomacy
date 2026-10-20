"""Grant one21B inherited branch fragment after three exact passed reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r73-root-authorization"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected):
    global COUNT
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and not rel.startswith("work/deps/") and path.stat().st_size <= 4 * 1024 * 1024
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
assert not any((ROOT / (BASE + name)).exists() for name in ("run-authorization.json", "claim.json", "capture.json", "owned-code.json", "failure.json", "preflight-failure.json"))
source = read(BASE + "source-manifest.json", pair(24203, "7d06b37f47bdda3a77898f185434994d5f4f0c85d0e856eb0e9fe30bd877ca3f"))
read(BASE + "produce.py", pair(23386, "d23bc4861c7d1a2fe17ecfde2090eda3ee77a9c87cbf9f45649817b51705800b"))
seed = read(BASE + "entry-seed.json", pair(21609, "34014d40471b0f79a9ed37a5013461e4afa1a31d43e22f4558080375a6ca3ca4"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]
assert seed["window"] == ["0x993643", "0x993658"] and seed["new_pdata_bytes"] == 0
groups = {}
for label, folder, fp, mp in (
    ("raw", "war-peace-api-20261016-r73-entry-root-review", pair(2515, "7fb5775b39a1c715f2d44a4475fda1d52b23fcacac2f4e117615f9b02b0b03f4"), pair(2649, "2dafb89a56acab3bf03c2be22f9b3385f2e7d6ee9f40cb2972a11020117545e4")),
    ("upstream_body_review", "war-peace-api-20261016-r71-actual-independent-review", pair(8035, "40dbb7199f02244bcf1f95dba475db87171a81e226b7e0238004f788312cb045"), pair(12660, "9bcd6706361cb07936763b868f9f384e399194f4900f774ef91fe042c2eb3a96")),
    ("source_peer_review", "war-peace-api-20261016-r73-source-independent-review", pair(4775, "6bec005ad6564656891e5b69928476dfba8846f4cb84eb454f1d70d4215aec92"), pair(16907, "7f5f59b865bb785a4678f291a6103c86e5c73080c364c05b845cecf38cc33e56")),
):
    fpath, mpath = "work/reports/" + folder + "/findings.json", "work/reports/" + folder + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    if label == "raw":
        assert f["entry_seed_pin"] == PINS[BASE + "entry-seed.json"] and f["entry_rva"] == "0x993643"
        assert f["branch_rva"] == "0x9935b2" and f["branch_raw"] == "0f8e8b000000"
        assert f["cached_descriptor_raw"] == "433699005836990024dde701" and f["scope"] == "raw_inherited_branch_fragment_seed_only"
    elif label == "upstream_body_review":
        assert f["subject_manifest"] == source["source_pins"]["work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/actual-manifest.json"]
    else:
        assert f["subject_source_manifest"] == PINS[BASE + "source-manifest.json"]
        assert f["subject_producer"] == PINS[BASE + "produce.py"] and f["subject_entry_seed"] == PINS[BASE + "entry-seed.json"]
    groups[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
auth = {"schema": "EU4-R73-ROOT-AUTHORIZATION/1", "sealed": True, "entry_rva": "0x993643", "window": ["0x993643", "0x993658"],
    "source_manifest": PINS[BASE + "source-manifest.json"], "producer_pin": PINS[BASE + "produce.py"], "entry_seed_pin": PINS[BASE + "entry-seed.json"],
    "root_explicit_start_received": True, "seed_review_passed": True,
    "seed_review_path": groups["raw"]["findings"]["path"], "seed_review_pin": {k: groups["raw"]["findings"][k] for k in ("bytes", "sha256")},
    "root_review_manifest": groups["raw"]["manifest"], "upstream_body_review": groups["upstream_body_review"], "source_peer_review": groups["source_peer_review"],
    "sole_executor": "diplomacy_static", "single_attempt": True, "authorizes_retry": False, "native_ready": False,
    "independent_function_entry": False, "new_code_bytes": 21, "new_pdata_bytes": 0,
    "source_bytes_limit": 33554432, "retained_bytes_limit": 16777216, "software_memory_limit": 805306368, "one_GiB_stop": True,
    "scope": "One inherited JLE successor21B from cached R69 descriptor, no fallback. R73 authorized rawmanifest buffer-before-parse source/engine guards, two EXE SHA, normal targetfile close before capture. No formal ABI reset, end993658/NULLpath/callee/data/header/unwind/vslot/process/native/test/request expansion. Preserve all failures, no retry."
}
OUT.mkdir()
ap = save(ROOT / (BASE + "run-authorization.json"), auth)
rp = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [], "before": before, "after": PINS,
    "authorization": ap, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024, "actual_runs": 0,
    "PE_engine_decoder_game_accesses": 0, "tests_run": 0, "sole_executor": "diplomacy_static"})
print(json.dumps({"authorization": ap, "receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
