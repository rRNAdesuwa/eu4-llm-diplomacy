"""One bounded raw-encoding scan grant; not a native or runtime authorization."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "work/reports/server-vtable-rip-reference-seeds-20261016-r1/"
OUT = ROOT / "work/reports/server-vtable-rip-root-authorization-20261016-r1"
PINS = {}
COUNT = 0


def read(rel, expected=None):
    global COUNT
    p = (ROOT / rel).resolve()
    assert p.is_relative_to(ROOT) and p.stat().st_size <= 4 * 1024 * 1024 and not rel.startswith("work/deps/")
    raw = p.read_bytes(); COUNT += len(raw)
    assert COUNT <= 8 * 1024 * 1024
    value = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
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
assert not any((ROOT / (BASE + n)).exists() for n in ("run-authorization.json", "claim.json", "capture.json", "failure.json"))
OUT.mkdir()
source = read(BASE + "source-manifest.json", pair(3108, "d26b5aad451b7b54e35aac84b5b7eb69f76268668131d2c2a49b8d42fc8b8963"))
for rel, value in source["source_pins"].items():
    read(rel, value)
subjects = {"subject_source_manifest": PINS[BASE + "source-manifest.json"], "subject_producer": PINS[BASE + "produce.py"],
            "subject_parser": PINS[BASE + "encoding_scan.py"], "subject_entry_seed": PINS[BASE + "entry-seed.json"]}
seed = read(BASE + "entry-seed.json", subjects["subject_entry_seed"])
reviews = {}
for label, directory, fp, mp in (
    ("upstream_DATA_review", "server-vtable-rtti-data-independent-review-20261016-r1", pair(2255, "246bb5ca660dd6c8fe90850b0e682f88f5bfc1a3c3a36d6db216debb0c8b10a7"), pair(18625, "b1900a941813140e8ca5063a885a7456e0608850ffa3f07c104dd6919a0fe331")),
    ("entry_seed_review", "server-vtable-rip-entry-independent-review-20261016-r1", pair(4113, "b4db168785f80dad3794ce5be7f4f1403fa4f30c4b0a4a28b7cc4a312c87684b"), pair(6992, "6ca26865448f21c4e84f72b943a3f95ae6ee4d16f809b4d764ec4eee3d662b16")),
    ("source_peer_review", "server-vtable-rip-reference-source-independent-review-20261016-r1", pair(7662, "52f47131eee864250dbccb6989b21bb4a95f98d376f4a3c3f482f175b1bd0f53"), pair(8397, "ab93963116bcd89740ccdc6c73dc1cc40f72ef688bd8f7d01a1f90687414d47f")),
):
    fpath, mpath = "work/reports/" + directory + "/findings.json", "work/reports/" + directory + "/manifest.json"
    f, m = read(fpath, fp), read(mpath, mp)
    assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
    expected = ({"subject_capture_pin": seed["upstream_capture_pin"], "subject_data_final_manifest_pin": seed["upstream_data_final_manifest_pin"], "subject_contract_pin": seed["upstream_contract_pin"]}
                if label == "upstream_DATA_review" else {k: subjects[k] for k in ("subject_source_manifest", "subject_entry_seed")} if label == "entry_seed_review" else subjects)
    assert all(f[k] == v for k, v in expected.items())
    reviews[label] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
tdir = "work/reports/server-vtable-rip-reference-first-fixtures-20261016-r1/"
t = read(tdir + "receipt.json", pair(22102, "7d2c5fbd3a5c0df53e317588c0bf6a3e321e8705734169907759b3e60328a288"))
tm = read(tdir + "manifest.json", pair(5566, "a93e36ef5bb090544284888b309582781161429e358eabba186e6a5eabc31da9"))
assert t["sealed"] is True and t["passed"] is True and t["blocking_findings"] == []
assert t["first_suite_executions"] == 1 and t["first_test_method_count"] == 10 and t["prior_test_suite_repetitions"] == 0
assert t["test_methods_expected"] == t["test_method_lines_seen_once"] and t["source_pre"] == t["source_post"]
assert t["job"]["exit_code"] == 0 and t["job"]["error"] is None and t["job"]["job_active_processes_final"] == 0
assert t["job"]["direct_child_collected"] is True and t["all_owned_job_processes_collected"] is True and t["all_shells_collected"] is True
for rel, value in tm["source_pins"].items():
    read(rel, value)
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
auth = {"schema": "EU4-R70-ROOT-AUTHORIZATION/1", "sealed": True, "explicit_start": True,
    "operation": "bounded-text-RIP-encoding-candidates-only", "target_vtable_rvas": [0x1CB8460, 0x1D5A8C8],
    **subjects, "reviews": reviews,
    "first_owned_fixture_receipt": {"path": tdir + "receipt.json", **PINS[tdir + "receipt.json"]},
    "first_owned_fixture_manifest": {"path": tdir + "manifest.json", **PINS[tdir + "manifest.json"]},
    "max_text_physical_bytes": 28724736, "max_scanner_input_bytes": 28727364, "max_text_chunks": 439,
    "candidate_limit_per_target": 8, "candidate_limit_total": 16, "target_full_SHA_passes": 2,
    "context_pdata_header_unwind_callee_virtualslot_reads_authorized": False,
    "process_or_native_operations_authorized": False, "host_guard_change_authorized": False,
    "authorizes_retry": False, "native_ready": False,
    "scope": "One existing frozen producer scan of the cached .text raw span; seven-byte RIP-LEA encoding candidates only, carry6 reused in memory, overflow stops selected scanning unknown. Before/after target SHA and fixed source/review guards, normal target close before commit. No instruction-boundary, class, mode or effect proof."}
ap = save(ROOT / (BASE + "run-authorization.json"), auth)
rp = save(OUT / "receipt.json", {"sealed": True, "passed": True, "blocking_findings": [], "before": before, "after": PINS,
    "root_authorization": ap, "selected_source_read_bytes": COUNT, "maximum": 8 * 1024 * 1024,
    "tests_rerun": 0, "target_PE_reads": 0, "process_accesses": 0})
print(json.dumps({"authorization": ap, "root_receipt": rp, "selected_source_read_bytes": COUNT}, ensure_ascii=True))
