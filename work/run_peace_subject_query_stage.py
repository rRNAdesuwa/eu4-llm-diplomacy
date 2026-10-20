"""Install one prepared DLL, load the war scene and run a subject-query batch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-name", default="llm_diplomacy_peace_utr_trade_inbound_ready_20261018_r51d.eu4")
    parser.add_argument("--install-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("STAGE_ALREADY_STARTED")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = args.manifest.resolve(strict=True)
    installation = manifest.parent / "installation.json"
    if installation.exists():
        raise SystemExit("BUILD_DIRECTORY_ALREADY_INSTALLED")
    state = {"status": "running", "manifest": str(manifest), "steps": [],
             "save_reload_validation": False, "scenario_save": args.save_name}

    def persist():
        output.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run(name, command):
        step = {"phase": name, "command": command, "status": "started"}
        state["steps"].append(step)
        persist()
        print(json.dumps({"phase": name, "status": "started"}), flush=True)
        target = output.parent / (name + ".log")
        with target.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        step.update(exit_code=result.returncode, status="passed" if result.returncode == 0 else "failed")
        persist()
        if result.returncode:
            raise RuntimeError(f"{name}_EXIT_{result.returncode}:{target}")
        return target.read_text(encoding="utf-8")

    try:
        text = run("start-scenario", ["pwsh", "-NoProfile", "-NonInteractive", "-File",
                   "work/native/restart-game.ps1", "-SavedTestGame", "-SaveName", args.save_name])
        match = re.search(r"Game restarted; new PID: (\d+)", text)
        if match is None:
            raise RuntimeError("NEW_PID_MISSING")
        state.update(pid=int(match[1]), installation=str(installation))
        persist()
        run("install", [sys.executable, "-B", "tools/start_diplomacy_observer.py", "--pid", match[1],
                        "--manifest", str(manifest), "--confirm-load-warning",
                        "--native-text-codec", "eu4_escape", "--wait-ready", "180"])
        if args.install_only:
            state.update(status="installed")
        else:
            batch = manifest.parent / "subject-query-batch-001/report.json"
            state["batch_report"] = str(batch)
            persist()
            run("queries", [sys.executable, "-B", "work/run_peace_subject_queries.py", "--installation",
                            str(installation), "--output", str(batch)])
            report = json.loads(batch.read_text(encoding="utf-8"))
            state.update(status="passed", session_id=report["session_id"])
    except Exception as error:
        state.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        persist()
    print(json.dumps({key: state.get(key) for key in ("status", "pid", "session_id", "error")}))
    return 0 if state["status"] in {"passed", "installed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
