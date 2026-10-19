"""Bind completed reviews and first fixtures to one selected offline DATA attempt."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-vtable-rtti-20261016-r1/"
OUT = ROOT / "work/reports/server-vtable-rtti-data-root-authorization-20261016-r1"
COUNT = 0
PINS = {}


def read(rel, expected=None):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and p != ROOT and p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 8 * 1024 * 1024
    value = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        assert value == expected, rel
    if rel in PINS:
        assert PINS[rel] == value
    PINS[rel] = value
    return json.loads(raw) if rel.endswith(".json") else raw


def fixed(size, sha):
    return {"bytes": size, "sha256": sha}


def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    with path.open("xb") as f:
        f.write(raw)
    return fixed(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not (ROOT / (BASE + "run-authorization.json")).exists()
assert not any((ROOT / (BASE + n)).exists() for n in ("attempt-claim.json", "capture.json", "failure.json"))
OUT.mkdir()
source = read(BASE + "source-manifest.json", fixed(3887, "da6e70ee360f4f233e908ad61fc72f22c457136ddab4c71afcdc0e78f64b7605"))
for rel, pin in source["source_pins"].items():
    read(rel, pin)
subjects = {"subject_source_manifest": PINS[BASE + "source-manifest.json"],
            "subject_producer": PINS[BASE + "produce.py"],
            "subject_parser": PINS[BASE + "rtti_parser.py"],
            "subject_entry_seed": PINS[BASE + "entry-seed.json"]}
seed = read(BASE + "entry-seed.json", subjects["subject_entry_seed"])
reviews = {}
for group, directory, fp, mp in (
    ("live_failure_review", "peace-current-pending-observer-live-independent-20261016-r1", fixed(2962, "3facf20fc83e51a1567d5f87dc83d4d0b9f5c4dd819b7e59980ea0f1ea87d5a4"), fixed(12474, "b7fb6575c472f5b13ef4561cbb5314a8a03721d8c56b9393ca0b75bcc389028f")),
    ("data_seed_review", "server-vtable-rtti-data-seed-review-20261016-r1", fixed(2697, "33c7f423d876db85db9eef0ed73455504f79f2ec405379bd76be7e22c0864750"), fixed(10865, "82089c2c126f125a6502ae8bbd1fbee59d5a58f736e2186de796ee5b44ae9b53")),
    ("source_peer_review", "server-vtable-rtti-source-independent-review-20261016-r1", fixed(9856, "7037208db8bffc5f5bb3626f29d413a21a7ea43f2358fa21f390b5aebeb52610"), fixed(7925, "3d21c4ccc717715603df8ed6d1d879aff5b9f7679c952db3b444385095b68bf0")),
):
    fpath, mpath = "work/reports/" + directory + "/findings.json", "work/reports/" + directory + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    expected = ({"subject_capture_pin": seed["capture_pin"], "subject_final_manifest_pin": seed["capture_final_manifest_pin"]}
                if group == "live_failure_review" else
                {k: subjects[k] for k in ("subject_source_manifest", "subject_entry_seed")} if group == "data_seed_review" else subjects)
    assert all(f[k] == v for k, v in expected.items())
    reviews[group] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
tdir = "work/reports/server-vtable-rtti-first-fixtures-20261016-r1/"
receipt = read(tdir + "receipt.json", fixed(26445, "4a0314878e3b628c6ccd489963ac7f7cdf2355ffe52d2eda5d42c943929c7abb"))
tm = read(tdir + "manifest.json", fixed(6298, "9643b702abdf911f2e2fd9773f303d5a14ac537c2899cec0a658e347a2e3b338"))
assert receipt["sealed"] is True and receipt["passed"] is True and receipt["blocking_findings"] == []
assert receipt["first_suite_executions"] == 1 and receipt["first_test_method_count"] == 12
assert receipt["test_methods_expected"] == receipt["test_method_lines_seen_once"]
assert receipt["source_pre"] == receipt["source_post"] and receipt["source_pre_post_equal"] is True
assert receipt["job"]["exit_code"] == 0 and receipt["job"]["error"] is None
assert receipt["job"]["job_active_processes_final"] == 0 and receipt["job"]["direct_child_collected"] is True
assert receipt["all_owned_job_processes_collected"] is True and receipt["all_shells_collected"] is True
for rel, pin in tm["source_pins"].items():
    read(rel, pin)
before = dict(PINS)
for rel, pin in before.items():
    read(rel, pin)
assert before == PINS
auth = {"schema": "EU4-SERVER-VTABLE-RTTI-ROOT-AUTHORIZATION/1", "sealed": True, "explicit_start": True,
        "operation": "single-file-DATA-only", "vtable_rvas": [0x1CB8460, 0x1D5A8C8], **subjects,
        "reviews": reviews, "first_owned_fixture_receipt": {"path": tdir + "receipt.json", **PINS[tdir + "receipt.json"]},
        "first_owned_fixture_manifest": {"path": tdir + "manifest.json", **PINS[tdir + "manifest.json"]},
        "max_DATA_read_attempts": 6, "max_DATA_requested_bytes": 352, "hard_DATA_byte_ceiling": 512,
        "target_full_SHA_passes": 2, "alternate_or_expanded_chain_authorized": False,
        "process_access_authorized": False, "host_guard_change_authorized": False,
        "native_ready": False, "authorizes_retry": False,
        "scope": "One exclusive existing producer run, selected disk RTTI chains only, two target SHA passes, source guards, closed target before publication; invalid chains stop unknown. No code/header/pdata/unwind/virtual-slot/CHD/engine/game access."}
auth_pin = save(ROOT / (BASE + "run-authorization.json"), auth)
receipt_pin = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [],
                  "source_pins_pre": before, "source_pins_post": PINS, "root_authorization": auth_pin,
                  "selected_source_read_bytes": COUNT, "limit": 8 * 1024 * 1024,
                  "tests_rerun": 0, "PE_reads": 0, "process_accesses": 0})
print(json.dumps({"root_authorization": auth_pin, "root_receipt": receipt_pin, "selected_source_read_bytes": COUNT}, ensure_ascii=True))
