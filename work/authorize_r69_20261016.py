"""Exact one-shot static function grant after three frozen independent reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/war-peace-api-20261016-r69-generator-divisor-source/"
OUT = ROOT / "work/reports/war-peace-api-20261016-r69-root-authorization"
PINS = {}
COUNT = 0


def read(rel, expected=None):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and p.stat().st_size <= 4 * 1024 * 1024 and not rel.startswith("work/deps/")
    raw = p.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    value = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        assert value == expected
    if rel in PINS:
        assert value == PINS[rel]
    PINS[rel] = value
    return json.loads(raw) if rel.endswith(".json") else raw


def exact(n, sha):
    return {"bytes": n, "sha256": sha}


def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as f:
        f.write(raw)
    return exact(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "failure.json", "preflight-failure.json"))
OUT.mkdir()
source = read(BASE + "source-manifest.json", exact(21501, "f0540a54cc50a6bf1024863b818dcb61e5a506567e77bbd9a2c5d4af40e853f9"))
for name in ("produce.py", "entry-seed.json"):
    read(BASE + name, source["source_pins"][BASE + name])
groups = {}
for label, directory, findings_pin, manifest_pin in (
    ("raw", "war-peace-api-20261016-r69-entry-root-review", exact(2195, "49efda9942e2a41da1e2463ef2edf593b34a9a5e991a871e9ce81f41dc6ca942"), exact(4728, "79ae13972eee3e5dc2153b91f342b0b5b18d57bf2b798f8a0f01138794017c14")),
    ("upstream_body_review", "war-peace-api-20261016-r62-independent-review", exact(6819, "8efc64a9385ca1472f6d4cf3c913f755ed8cdfffcd5082b1c55e87821aac15ad"), exact(12593, "660065e49bac4d637b609fa218058a79034fd9d5f5f7fe24c1f902f57695d42c")),
    ("source_peer_review", "war-peace-api-20261016-r69-source-independent-review", exact(7276, "0ea573567c7dcf80434605383a73e132c9cdb578b45f6117fe9c68dae652133e"), exact(8591, "c1420c3dd66eceadc0484376647f466b72b23e260208c5b39d49200a1f09d282")),
):
    fpath, mpath = "work/reports/" + directory + "/findings.json", "work/reports/" + directory + "/manifest.json"
    f, m = read(fpath, findings_pin), read(mpath, manifest_pin)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    if label == "raw":
        assert f["entry_seed_pin"] == PINS[BASE + "entry-seed.json"]
        assert f["entry_rva"] == "0x993570" and f["call_site_rva"] == "0x98453d" and f["raw_call"] == "e82ef00000"
        assert f["scope"] == "raw_call_entry_seed_only"
    elif label == "upstream_body_review":
        assert f["subject_manifest"] == source["source_pins"]["work/reports/war-peace-api-20261016-r62-gold-recipient-generator/manifest.json"]
    else:
        assert f["subject_source_manifest"] == PINS[BASE + "source-manifest.json"]
        assert f["subject_producer"] == PINS[BASE + "produce.py"] and f["subject_entry_seed"] == PINS[BASE + "entry-seed.json"]
    groups[label] = {"findings": {"path": fpath, **findings_pin}, "manifest": {"path": mpath, **manifest_pin}}
before = dict(PINS)
for rel, pin in before.items():
    read(rel, pin)
auth = {"schema": "EU4-R69-ROOT-AUTHORIZATION/1", "sealed": True, "entry_rva": "0x993570",
    "source_manifest": PINS[BASE + "source-manifest.json"], "producer_pin": PINS[BASE + "produce.py"],
    "entry_seed_pin": PINS[BASE + "entry-seed.json"], "root_explicit_start_received": True,
    "seed_review_passed": True, "seed_review_path": groups["raw"]["findings"]["path"],
    "seed_review_pin": {k: groups["raw"]["findings"][k] for k in ("bytes", "sha256")},
    "root_review_manifest": groups["raw"]["manifest"],
    "upstream_body_review": groups["upstream_body_review"], "source_peer_review": groups["source_peer_review"],
    "single_attempt": True, "authorizes_retry": False, "native_ready": False,
    "scope": "One fixed 993570 static producer; exact pdata only, <=8192 full body else2048 prefix, <=32 metadata12B, cached mapping, two EXE SHA, fixed source/engine guards. No external callees/data/headers/unwind/virtual slots or game/process/native/tests."}
auth_pin = save(ROOT / (BASE + "run-authorization.json"), auth)
receipt_pin = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [],
    "before": before, "after": PINS, "authorization": auth_pin, "selected_read_bytes": COUNT,
    "maximum": 2 * 1024 * 1024, "PE_engine_decoder_game_accesses": 0, "tests_run": 0})
print(json.dumps({"authorization": auth_pin, "root_receipt": receipt_pin, "selected_read_bytes": COUNT}, ensure_ascii=True))
