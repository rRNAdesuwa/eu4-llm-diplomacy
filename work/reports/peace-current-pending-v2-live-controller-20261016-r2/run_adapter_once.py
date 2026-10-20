"""One fresh Job for only eight new fictional adapter cases. Never a live runner."""
from pathlib import Path
import hashlib, json, sys, types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READS = []


def pin(raw): return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path, expected=None):
    size = path.stat().st_size
    assert size <= 4194304 and sum(x["bytes"] for x in READS) + size <= 8388608
    b = path.read_bytes(); p = pin(b); READS.append({"path": str(path), **p})
    if expected is not None: assert p == expected
    return b


def save(name, value):
    with (HERE / name).open("x", encoding="ascii", newline="\n") as f:
        json.dump(value, f, ensure_ascii=True, sort_keys=True, indent=2); f.write("\n")


def main():
    assert len(sys.argv) == 2 and len(sys.argv[1]) == 64
    save("adapter-job-claim.json", {"source_manifest_sha256": sys.argv[1], "one_job": True, "no_retry": True})
    raw = read(HERE / "source-manifest.json"); assert pin(raw)["sha256"] == sys.argv[1]
    m = json.loads(raw); before = {n: pin(read(ROOT / n, p)) for n, p in m["source_pins"].items()}
    jobname = "work/candidates/frida-entry-observer-1375-v1/job_tree.py"
    code = read(ROOT / jobname, m["source_pins"][jobname])
    jobs = types.ModuleType("_frozen_new_adapter_job"); jobs.__file__ = str(ROOT / jobname)
    exec(compile(code, jobs.__file__, "exec"), jobs.__dict__)
    argv = [sys.executable, "-I", "-B", str(HERE / "test_text_config_adapter.py")]
    job = jobs.run_cli_tree(argv, ROOT, HERE / "adapter-stdout.txt", HERE / "adapter-stderr.txt", timeout_seconds=45, memory_limit=805306368)
    save("adapter-job.json", job)
    after = {n: pin(read(ROOT / n, p)) for n, p in m["source_pins"].items()}
    assert before == after and pin(read(HERE / "source-manifest.json"))["sha256"] == sys.argv[1]
    stdout = read(HERE / "adapter-stdout.txt"); stderr = read(HERE / "adapter-stderr.txt")
    receipt = json.loads(read(HERE / "adapter-first-receipt.json"))
    ok = job["exit_code"] == 0 and job["error"] is None and job["job_active_processes_final"] == 0 and job["direct_child_collected"] is True and receipt["passed"] is True and len(receipt["results"]) == 8
    result = {"passed": ok, "job": job, "source_prepost_equal": True, "read_events": READS,
              "runner_explicit_returned": sum(x["bytes"] for x in READS), "test_source_returned": receipt["source_returned"],
              "new_cases": receipt["new_case_count"], "old_tests": 0, "CLI_runs": 0, "real_env_operations": 0,
              "game_reads": 0, "native_calls": 0, "automatic_retry": False, "stderr_bytes": len(stderr),
              "stdout_pin": pin(stdout), "stderr_pin": pin(stderr)}
    save("adapter-first-run.json", result)
    print(json.dumps({"passed": ok, "cases": receipt["new_case_count"], "job": job, "runner_explicit_returned": result["runner_explicit_returned"], "test_source_returned": result["test_source_returned"]}, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__": raise SystemExit(main())
