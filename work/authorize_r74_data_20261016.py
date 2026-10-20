"""One fixed22B DATA grant after exact raw, upstream and source reviews."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-current-label-data-20261016-r1/"
OUT = ROOT / "work/reports/server-current-label-data-root-authorization-20261016-r1"
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
    assert COUNT <= 1024 * 1024
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
assert not any((ROOT / (BASE + name)).exists() for name in ("run-authorization.json", "attempt-claim.json", "capture.json", "failure.json"))
source = read(BASE + "source-manifest.json", pair(4424, "f698e1c6a4616280a627ff26a63e56200b2117a19cd56ff2c9259043bd0c77bc"))
read(BASE + "produce.py", pair(18606, "3fcd780d3db3460fad40e43e280bfeb666aa409d93bc322294ace72d6b8f3af3"))
seed = read(BASE + "entry-seed.json", pair(2514, "1467f4d8c5276a08659d0c33be67fb28a826904fe9290ff1abf9d5100e7d865c"))
for name in ("produce.py", "entry-seed.json"):
    assert source["source_pins"][BASE + name] == PINS[BASE + name]
assert seed["data_rva"] == 30777744 and seed["requested_bytes"] == 22 and seed["end_exclusive"] == 30777766
subjects = {"subject_source_manifest": PINS[BASE + "source-manifest.json"], "subject_producer": PINS[BASE + "produce.py"], "subject_entry_seed": PINS[BASE + "entry-seed.json"]}
reviews = {}
for label, folder, fp, mp in (
    ("raw_seed_review", "server-current-label-data-entry-review-20261016-r1", pair(2325, "40ccc51ed55a4f454bc6c9d603baee3f088731e30ff993e302fffa9d5105d18e"), pair(2212, "5869c05ce5d39ce4b1919fb263e8a645c36866c43ef529205257a97a3f082c87")),
    ("upstream_actual_review", "server-vtable-current-reference-owner-actual-independent-review-20261016-r2", pair(5882, "d368133f4b8a96a6e93ad23ba53961180986654950021a99e372abfdabb7f492"), pair(20508, "3929aa5ea3936212bfd530b5609fe301a7201ec03b57c2715a866893eade24ce")),
    ("source_peer_review", "server-current-label-data-source-independent-review-20261016-r1", pair(14578, "255e4dacb2a0fd636e16cb951c1d2878eb453ea0374e4ad5c8f2fa21f695daec"), pair(7874, "934daa1897090fe112d93fbb2c853d62f73757c9130db807ae1e300269017f0a")),
):
    fpath, mpath = "work/reports/" + folder + "/findings.json", "work/reports/" + folder + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    if label == "upstream_actual_review":
        for key, value in seed["upstream_required_subjects"].items():
            assert f[key] == value
    else:
        for key, value in subjects.items():
            assert f[key] == value
        if label == "raw_seed_review":
            assert type(f["data_rva"]) is int and f["data_rva"] == 30777744
            assert type(f["requested_bytes"]) is int and f["requested_bytes"] == 22
    reviews[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
auth = {"schema": "EU4-R74-ROOT-AUTHORIZATION/1", "sealed": True, "explicit_start": True,
    "operation": "one-fixed22B-file-DATA-only", "data_rva": 30777744, "requested_bytes": 22,
    **subjects, "reviews": reviews, "sole_executor": "validation_audit", "single_attempt": True,
    "source_bytes_limit": 4194304, "retained_bytes_limit": 4194304, "software_memory_limit": 805306368, "one_GiB_stop": True,
    "authorizes_retry": False, "native_ready": False, "class_or_mode_verified": False, "host_guard_change_authorized": False,
    "scope": "One fixed22B DATA-only disk read at cached.rdata RVA1d5a190. No sourceNUL/neighbor/callee/code/vslot/header/pdata/unwind, parser/decoder, process/UI/native/request/test expansion. Unknown mapping permits zeroDATA and no fallback. Two fullEXE SHA separately accounted; rawmanifest authorized-buffer-before-parse and source/auth/three reviews before/after; capture after normalfileclose and finalguards. No retry."
}
OUT.mkdir()
ap = save(ROOT / (BASE + "run-authorization.json"), auth)
rp = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [], "before": before, "after": PINS,
    "authorization": ap, "selected_read_bytes": COUNT, "maximum": 1024 * 1024,
    "PE_engine_decoder_game_accesses": 0, "tests_run": 0, "actual_runs": 0, "sole_executor": "validation_audit"})
print(json.dumps({"authorization": ap, "receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
