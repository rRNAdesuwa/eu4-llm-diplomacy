"""Build one immutable observer DLL with a timeout and owned-process cleanup."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psutil


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--reason-metadata", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.experiment):
        parser.error("Invalid experiment name")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        parser.error("PowerShell is required")
    evidence = ROOT / "work/runtime" / ("build-supervision-" + uuid.uuid4().hex)
    evidence.mkdir()
    command = [shell, "-NoProfile", "-NonInteractive", "-File",
               str(ROOT / "work/native/build-diplomacy-observer.ps1"),
               "-Experiment", args.experiment]
    if args.reason_metadata:
        command.append("-ReasonMetadata")
    known = {}
    reason = "completed"
    started = time.monotonic()
    with (evidence / "build.log").open("xb") as log:
        process = psutil.Popen(command, cwd=ROOT, stdout=log, stderr=log,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        known[process.pid] = process.create_time()
        while process.poll() is None:
            try:
                children = process.children(recursive=True)
                for child in [process, *children]:
                    try:
                        known[child.pid] = child.create_time()
                    except psutil.NoSuchProcess:
                        continue
                if time.monotonic() - started > 120:
                    reason = "build_timeout"
            except psutil.NoSuchProcess:
                # The owned PowerShell process can exit between poll() and
                # children(). Collect its actual exit code below.
                break
            except (psutil.AccessDenied, OSError) as error:
                reason = "process_tree_observation_failed:" + type(error).__name__
            if reason != "completed":
                break
            time.sleep(0.2)
        if reason != "completed":
            # Every PID came from this exact owned tree.  Recheck creation time
            # to prevent terminating an unrelated process after PID reuse.
            owned = []
            for pid, creation in known.items():
                try:
                    child = psutil.Process(pid)
                    if child.create_time() == creation:
                        child.terminate()
                        owned.append(child)
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(owned, timeout=3)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(alive, timeout=3)
        returncode = process.wait(timeout=5)
    report = {"experiment": args.experiment, "command": command,
              "returncode": returncode, "reason": reason,
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "build_manifest": str(ROOT / "work/runtime" / args.experiment / "build-manifest.json")}
    (evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({**report, "supervision_evidence": str(evidence)}, ensure_ascii=False))
    return 0 if reason == "completed" and returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
