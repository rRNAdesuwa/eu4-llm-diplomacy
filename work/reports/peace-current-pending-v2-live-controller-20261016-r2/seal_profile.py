"""One retained-only delivery seal; does not execute runtime or any test case."""
from pathlib import Path
import hashlib, json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READS = []


def pin(raw): return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path, expected=None):
    assert path.name != "local.env" or "fictional-fixtures" in path.parts
    size = path.stat().st_size
    assert size <= 4194304 and sum(x["bytes"] for x in READS) + size <= 8388608
    raw = path.read_bytes(); p = pin(raw)
    READS.append({"path": path.relative_to(ROOT).as_posix(), **p})
    if expected is not None: assert p == expected
    return raw


def write(name, value):
    raw = value.encode("utf-8") if isinstance(value, str) else (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
    with (HERE / name).open("xb") as f: f.write(raw)
    return {"path": (HERE / name).relative_to(ROOT).as_posix(), **pin(raw)}


def main():
    basepin = {"bytes": 8861, "sha256": "803d619df53c33b8698e78283c3ad223a61319c87b4a40ccaae732997d225127"}
    base = json.loads(read(HERE / "source-manifest.json", basepin))
    inputs = {n: pin(read(ROOT / n, p)) for n, p in base["source_pins"].items()}
    names = ["source-manifest.json", "source-preparation.json", "source-build-claim.json", "adapter-test-claim.json", "adapter-job-claim.json",
             "adapter-first-receipt.json", "adapter-first-run.json", "adapter-job.json", "adapter-stdout.txt", "adapter-stderr.txt", "seal_profile.py"]
    retained = {}; objects = {}
    for n in names:
        raw = read(HERE / n); retained[(HERE / n).relative_to(ROOT).as_posix()] = pin(raw)
        if n.endswith(".json"): objects[n] = json.loads(raw)
    for label in ("case1", "case2", "case3", "case4", "case5_0", "case5_1", "case6", "case7", "case8"):
        p = HERE / "fictional-fixtures" / label / "local.env"
        retained[p.relative_to(ROOT).as_posix()] = pin(read(p))
    prep = objects["source-preparation.json"]
    test = objects["adapter-first-receipt.json"]
    run = objects["adapter-first-run.json"]
    job = objects["adapter-job.json"]
    assert test["passed"] and len(test["results"]) == 8 and test["failure"] is None
    assert all(x["passed"] and x["runs"] == 1 for x in test["results"])
    assert run["passed"] and run["source_prepost_equal"] and job["exit_code"] == 0
    assert job["job_active_processes_final"] == 0 and job["direct_child_collected"] is True
    assert retained[(HERE / "adapter-stderr.txt").relative_to(ROOT).as_posix()]["bytes"] == 0
    source_total = prep["source_total_with_manual_upper"] + run["runner_explicit_returned"] + test["source_returned"] + test["fictional_snapshot_returned"]
    assert source_total <= 33554432
    report = """# Configuration text adapter R2 — source and first offline cases

The new exact-path configuration adapter and all eight new fictional cases are
source-frozen. First new tests passed once each; independent source review and
a separate future /2 live grant are still required. No actual configuration
open/stat/hash/read, old suite, CLI/status, PID/UI, target PE, native call, request,
save or reload occurred in this scope. R1 failure and sources are unchanged.

The unchanged Meter/ReadPort and GameMeter retain binary/host/game budgets.
The additional adapter validates exact root/local.env text-open options and
regular <=64KiB file metadata, then reserves size+1, charges actual raw returned
bytes, verifies the root raw pin before utf-8-sig strict decode, privately checks
the exact frozen KEY grammar, and returns a read-only virtual universal-newline
stream. Syntax/encoding/read failures use generic redacted exceptions without
raw_line/value/decoder fragments. Virtual reads add zero physical bytes; at most
16 snapshots may open. The new current-result validation requires accepted,
exact-pin, normally closed configuration streams. Runtime selection is fixed.

Tests cover BOM/unicode/newline equivalence, full-request reservation, changed
hash/size, oversize/aliases/write/options/other text refusal, syntax/encoding
redaction, close/16-snapshot bound, short/read-error accounting, and unchanged
binary delegation. Tests use only fictional files owned by this namespace;
only donor Meter/ReadPort AST class definitions are executed, never donor main.

The complete runtime controller/child were not executed. AST checks preserve
the original GameMeter and existing controller validation helpers. New changes
are adapter dispatch and ledger, configuration closure, new build identity,
schema /2 and four-subject peer/config binding. This is not an R1 retry.

Unknowns remain: this does not certify arbitrary configuration value semantics,
all downstream value use, all Mods, world compatibility, complete explicit/API
I/O coverage, OS loader/cache I/O, or target lifetime. No global stdout scrubber
is claimed; the observed malformed-parser path is prevented before raw_line can
be formatted. No actual config values exist in these artifacts. The inherited
delegated API limitations remain. A future required unmetered route blocks live.
Current queue presence remains separate from original-request/AI/peace effects.

Budget accounting separates source/new-test reads from retained sealing.
Earlier manual source reads have a conservative200,000B envelope (including
the bounded PowerShell tail whose internal read size is not separately metered),
not a fabricated measured OS total. All explicit counted reads and new Job
results are retained. No source or test failure occurred in this new scope.
"""
    rp = write("report.md", report); retained[rp["path"]] = {k: rp[k] for k in ("bytes", "sha256")}
    ap = write("read-accounting.json", {"schema": "EU4-TEXT-CONFIG-R2-DELIVERY-ACCOUNTING/1", "source_build_explicit": prep["explicit_source_returned"],
       "source_manual_reserved_upper": prep["manual_source_upper_bound"], "new_test_runner_explicit": run["runner_explicit_returned"],
       "new_test_source_explicit": test["source_returned"], "new_fictional_snapshot_returned": test["fictional_snapshot_returned"],
       "source_upper_including_manual_and_tests": source_total, "source_cap": 33554432,
       "retained_read_events_before_publication": READS, "retained_returned_before_publication": sum(x["bytes"] for x in READS),
       "retained_cap": 8388608, "whole_OS_IO_proven": False, "real_config_operations": 0, "new_cases": 8, "cases_repeated": 0,
       "old_tests": 0, "CLI_runs": 0, "runtime_controller_runs": 0, "runtime_child_runs": 0, "target_reads": 0})
    retained[ap["path"]] = {k: ap[k] for k in ("bytes", "sha256")}
    author = write("author-manifest.json", {"schema": "EU4-TEXT-CONFIG-R2-SOURCE-DELIVERY/1", "sealed": True,
       "stage": "source_ready_pending_independent_peer_and_distinct_runtime_grant", "source_manifest": {"path": (HERE / "source-manifest.json").relative_to(ROOT).as_posix(), **basepin},
       "source_pins": inputs, "retained_pins": retained, "new_tests_passed": 8, "runtime_authorized": False,
       "native_ready": False, "selected_effect_verified": False, "live_grant_created": False, "independent_review_pending": True})
    for p in (rp, ap, author): assert pin(read(ROOT / p["path"])) == {k:p[k] for k in ("bytes", "sha256")}
    verification = write("delivery-filecheck.json", {"passed": True, "source_count": len(inputs), "retained_count": len(retained),
       "author_manifest": author, "retained_read_bytes_including_publication_check": sum(x["bytes"] for x in READS),
       "retained_cap": 8388608, "all_pin_checks_passed": True, "author_runtime_or_test_reexecuted": False})
    delivery = write("delivery.json", {"source_manifest": {"path": (HERE / "source-manifest.json").relative_to(ROOT).as_posix(), **basepin},
       "author_manifest": author, "verification": verification, "report": rp, "read_accounting": ap,
       "source_ready_pending_peer": True, "runtime_authorized": False, "status_runs": 0,
       "eight_new_cases_first_pass": True, "job": job, "shell_parent_must_collect": True})
    print(json.dumps({"source_manifest": basepin, "author_manifest": author, "verification": verification, "delivery": delivery,
          "source_upper_with_manual_tests": source_total, "retained_read_bytes": sum(x["bytes"] for x in READS),
          "new_cases": 8, "runtime_authorized": False, "source_pins": {n:p for n,p in inputs.items() if n.startswith(HERE.relative_to(ROOT).as_posix())}}, ensure_ascii=True))


if __name__ == "__main__": main()
