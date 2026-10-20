"""Record hashes after a successful local explicit-marker research pipeline DLL build."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bridge.native_build import LOCAL_SHA256

SOURCES = ("work/native/research-pipeline-1375.cpp", "work/native/research-frame-1375.asm",
           "work/native/pair-probe-1375.cpp", "work/native/pair-preview-1375.cpp",
           "work/native/pair-command-1375.cpp", "work/native/pair-submit-experiment-1375.cpp")


def main():
    directory = ROOT / "work/runtime/native1375-v5"
    dll = directory / "eu4_pair_pipeline_1375.dll"
    report = {"purpose": "research_pair_pipeline_with_explicit_submit", "game_sha256": LOCAL_SHA256,
              "built_at_utc": datetime.now(timezone.utc).isoformat(),
              "dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest().upper(),
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest().upper() for name in SOURCES},
              "runtime_verified": False}
    (directory / "build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dll_sha256": report["dll_sha256"], "runtime_verified": False}))


if __name__ == "__main__":
    main()
