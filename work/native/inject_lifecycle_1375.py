"""Load only the recorded 1.37.5 lifecycle/legality research DLL.

No custom DLL path, hash bypass, native submission or automatic experiment. A
disposable saved campaign is required. The old loader CLI remains 1.37.4-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bridge.native_build import LOCAL_SHA256
from inject_probe import _run, _positive_pid, _bounded_timeout

OUTPUT = ROOT / "work/runtime/native1375-v4"
DLL = OUTPUT / "eu4_pair_lifecycle_1375.dll"
MANIFEST = OUTPUT / "build.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=_positive_pid)
    parser.add_argument("--ack-test-save", required=True, action="store_true")
    parser.add_argument("--timeout-ms", type=_bounded_timeout, default=10000)
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with DLL.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest().upper()
        if (manifest.get("game_sha256") != LOCAL_SHA256 or manifest.get("dll_sha256") != digest
                or manifest.get("purpose") != "lifecycle_and_preview_no_send"):
            raise RuntimeError("Lifecycle DLL does not match the recorded local build")
        for relative, expected in manifest["source_sha256"].items():
            source = ROOT / relative
            if hashlib.sha256(source.read_bytes()).hexdigest().upper() != expected:
                raise RuntimeError(f"Source changed after build: {relative}")
        if any((OUTPUT / name).exists() for name in ("pair-selftest.request", "pair-preview.request")):
            raise RuntimeError("Stale research request exists; inspect before installation")
        args.dll = str(DLL.resolve())
        report = _run(args, expected_game_hash=LOCAL_SHA256)
        report.update(purpose="lifecycle_and_preview_no_send", selftest_automatic=False, preview_automatic=False, dll_sha256=digest)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"inject_lifecycle_1375: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
