"""Grant one inherited156B fragment acquisition after three exact reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r71-root-authorization"
PINS = {}
COUNT = 0


def read(rel, expected):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and not rel.startswith("work/deps/") and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes(); COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    value = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert value == expected, rel
    if rel in PINS:
        assert PINS[rel] == value
    PINS[rel] = value
    return json.loads(raw) if rel.endswith(".json") else raw


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as f:
        f.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "failure.json", "preflight-failure.json"))
OUT.mkdir()
source = read(BASE + "source-manifest.json", pair(21135, "6f46db3d7acb1b34391b9f821fb2347b507dac2ee18393b64d74d51f2a5b0722"))
for name in ("produce.py", "entry-seed.json"):
    read(BASE + name, source["source_pins"][BASE + name])
groups = {}
for label, directory, fp, mp in (
    ("raw", "war-peace-api-20261016-r71-entry-root-review", pair(1999, "90c2a816b1b17252a603e2044cdb511d7a4bda6fa13a46749f58091ffcba02e2"), pair(5179, "7e9f93e6e2798917d0ca7f99e01a229104d1a4a1f0b0cb381aa02c7d632d0ea3")),
    ("upstream_body_review", "war-peace-api-20261016-r69-actual-independent-review", pair(6300, "529f00a30baeba2c1f600018455c1e050f6061429951da8ce2daf9c44de17f56"), pair(13503, "bceee11bb0cc11bb648d0b2e8d65b9862df971ecc10e161118ee762e3acf8058")),
    ("source_peer_review", "war-peace-api-20261016-r71-source-independent-review", pair(5825, "8b190f124f09a6a9d56195d9a4c192ccc2178f835f21e08f39d95b87cb1e40af"), pair(13536, "0a9f11edeb25bb881abf7dd6fa4f5cc0cd12b4e09f88b63a3ae90cd5bdc82925")),
):
    fpath, mpath = "work/reports/" + directory + "/findings.json", "work/reports/" + directory + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    if label == "raw":
        assert f["entry_seed_pin"] == PINS[BASE + "entry-seed.json"] and f["entry_rva"] == "0x9935a7"
        assert f["predecessor_last_rva"] == "0x9935a3" and f["predecessor_last_raw"] == "49c1f803"
        assert f["cached_descriptor_raw"] == "a73599004336990008dde701" and f["scope"] == "raw_fallthrough_fragment_seed_only"
    elif label == "upstream_body_review":
        assert f["subject_manifest"] == source["source_pins"]["work/reports/war-peace-api-20261016-r69-generator-divisor-source/manifest.json"]
    else:
        assert f["subject_source_manifest"] == PINS[BASE + "source-manifest.json"]
        assert f["subject_producer"] == PINS[BASE + "produce.py"] and f["subject_entry_seed"] == PINS[BASE + "entry-seed.json"]
    groups[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
auth = {"schema": "EU4-R71-ROOT-AUTHORIZATION/1", "sealed": True, "entry_rva": "0x9935a7",
    "window": ["0x9935a7", "0x993643"], "source_manifest": PINS[BASE + "source-manifest.json"],
    "producer_pin": PINS[BASE + "produce.py"], "entry_seed_pin": PINS[BASE + "entry-seed.json"],
    "root_explicit_start_received": True, "seed_review_passed": True,
    "seed_review_path": groups["raw"]["findings"]["path"],
    "seed_review_pin": {k: groups["raw"]["findings"][k] for k in ("bytes", "sha256")},
    "root_review_manifest": groups["raw"]["manifest"], "upstream_body_review": groups["upstream_body_review"],
    "source_peer_review": groups["source_peer_review"], "single_attempt": True, "authorizes_retry": False,
    "native_ready": False, "independent_function_entry": False, "new_code_bytes": 156, "new_pdata_bytes": 0,
    "scope": "One inherited fallthrough fragment156B, cached R69 next descriptor, fixed source/engine guards, two EXE SHA and closed file before capture. No formal ABI reset, no JE993658/end993643/callee/data/header/unwind/virtualslot expansion or process/native/tests."}
ap = save(ROOT / (BASE + "run-authorization.json"), auth)
rp = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [], "before": before,
    "after": PINS, "authorization": ap, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024,
    "PE_engine_decoder_game_accesses": 0, "tests_run": 0})
print(json.dumps({"authorization": ap, "root_receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
