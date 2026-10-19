"""Load only the recorded 1.37.5 explicit-marker research pipeline DLL.

No custom DLL path, hash bypass, arbitrary native submission or automatic experiment. A
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
from record_pipeline_build import SOURCES
from work.local_config import user_data

OUTPUT = ROOT / "work/runtime/native1375-v5"
DLL = OUTPUT / "eu4_pair_pipeline_1375.dll"
MANIFEST = OUTPUT / "build.json"
BASELINE_SHA256 = "276F88AFECDBC1F1A24ED6314845351B1BA5640715B7ED1FD14513B3376664FB"


def verify_baseline() -> dict:
    # Serialized evidence plus the user's load confirmation is the experiment's
    # single-player premise; server/transport vtables alone do not prove it.
    baseline = user_data() / "save games/llm_diplomacy_1375_baseline.eu4"
    with baseline.open("rb") as stream:
        head = stream.read(4096)
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
    if (digest != BASELINE_SHA256 or not head.startswith(b"EU4txt\n")
            or b"\nmulti_player=no\n" not in head or b'\nplayer="FRA"\n' not in head
            or b"\ndate=1444.11.11\n" not in head or b"\nspeed=0\n" not in head):
        raise RuntimeError("Saved paused single-player FRA baseline differs from the audited experiment")
    return {"path": str(baseline), "sha256": digest, "serialized_multi_player": False,
            "serialized_player": "FRA", "serialized_date": "1444.11.11",
            "live_multiplayer_mode_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=_positive_pid)
    parser.add_argument("--ack-test-save", required=True, action="store_true")
    parser.add_argument("--timeout-ms", type=_bounded_timeout, default=10000)
    args = parser.parse_args()
    try:
        baseline = verify_baseline()
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with DLL.open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest().upper()
        if (manifest.get("game_sha256") != LOCAL_SHA256 or manifest.get("dll_sha256") != digest
                or manifest.get("purpose") != "research_pair_pipeline_with_explicit_submit"):
            raise RuntimeError("Pipeline DLL does not match the recorded local build")
        if set(manifest.get("source_sha256", {})) != set(SOURCES):
            raise RuntimeError("Pipeline source manifest is incomplete or has unexpected entries")
        for relative, expected in manifest["source_sha256"].items():
            source = ROOT / relative
            if hashlib.sha256(source.read_bytes()).hexdigest().upper() != expected:
                raise RuntimeError(f"Source changed after build: {relative}")
        if any((OUTPUT / name).exists() for name in ("pair-selftest.request", "pair-preview.request", "pair-command.request",
                                                         "pair-submit-improve.request", "pair-submit-improve.attempt.json")):
            raise RuntimeError("Stale research request exists; inspect before installation")
        args.dll = str(DLL.resolve())
        report = _run(args, expected_game_hash=LOCAL_SHA256)
        report.update(purpose="research_pair_pipeline_with_explicit_submit", selftest_automatic=False, preview_automatic=False, command_automatic=False, submit_automatic=False, dll_sha256=digest)
        report["baseline"] = baseline
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"inject_pipeline_1375: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
