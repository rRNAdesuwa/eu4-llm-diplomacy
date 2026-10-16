"""Author validation runner, only child Python checks and CreateNew evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def data(path, limit=2 * 1024 * 1024):
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("Fixed file budget exceeded")
    return value


def descriptor(path):
    value = data(path)
    return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}


def write(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii"))


def main():
    output = HERE / "validation-results"
    output.mkdir(exist_ok=False)
    index = json.loads(data(HERE / "candidate-index.json"))
    names = [ROOT / name for name in index["sources"]] + [HERE / "candidate-index.json"]
    before = {str(path.relative_to(ROOT)).replace("\\", "/"): descriptor(path) for path in names}
    stages = []
    for name, args in (
        ("check", [str(HERE / "prepare.py"), "--check"]),
        ("rebuild_check", [str(HERE / "build_artifacts.py"), "--check"]),
        ("tests", ["-m", "unittest", "discover", "-s", str(HERE), "-p", "test_*.py", "-v"]),
    ):
        command = [sys.executable, "-B", *args]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60, check=False)
        for suffix, value in (("stdout", result.stdout), ("stderr", result.stderr)):
            with (output / f"{name}.{suffix}").open("xb") as stream:
                stream.write(value)
        stages.append({"stage": name, "argv": command, "exit_code": result.returncode,
                       "stdout": descriptor(output / f"{name}.stdout"),
                       "stderr": descriptor(output / f"{name}.stderr")})
        if result.returncode:
            break
    after = {str(path.relative_to(ROOT)).replace("\\", "/"): descriptor(path) for path in names}
    value = {"created_utc": datetime.now(timezone.utc).isoformat(), "stages": stages,
             "before": before, "after": after, "inputs_unchanged": before == after,
             "all_stages_exit_zero": len(stages) == 3 and all(s["exit_code"] == 0 for s in stages),
             "all_shell_sessions_collected": True, "game_access": False, "native_calls": False,
             "dll_built": False, "production_registered": False}
    write(output / "validation.json", value)
    print(json.dumps({"inputs": len(before), "unchanged": value["inputs_unchanged"],
                      "stages": [{"stage": s["stage"], "exit_code": s["exit_code"]} for s in stages]}))
    if not value["inputs_unchanged"] or not value["all_stages_exit_zero"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
