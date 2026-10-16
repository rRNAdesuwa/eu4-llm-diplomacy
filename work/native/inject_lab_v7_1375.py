"""Explicit v7 research loader; installs no marker and submits no operation.

Never hot-replace any bridge. Current world provenance remains an isolated-test
premise, separate from the two audited on-disk save files.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v7_1375 as lab
from work.native import inject_probe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=inject_probe._positive_pid)
    parser.add_argument("--creation", help="Optional exact 16-lower-hex process creation identity")
    parser.add_argument("--ack-test-save", action="store_true", required=True)
    parser.add_argument("--test-save", choices=tuple(lab.TEST_SAVES), default="llm_diplomacy_1375_baseline.eu4")
    parser.add_argument("--timeout-ms", type=inject_probe._bounded_timeout, default=10000)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest, manifest_sha = lab.verify_build()
        save = lab.verify_test_save(args.test_save)
        with lab.LiveLabProcess(args.pid, expected_creation=args.creation, require_loaded=False) as process:
            live = process.snapshot()
            fixture_disk_evidence = lab.verify_installed_fixture(manifest,args.pid,process.creation)
            session = lab.OUTPUT / f"session-{args.pid}-{process.creation}"
            lab._no_links(session)
            lab.require(not session.exists(), "This process already has a v7 session/failed installation; never rearm")
            report = {"purpose": lab.PURPOSE, "pid": args.pid, "creation": process.creation,
                      "dll_sha256": manifest["dll_sha256"], "manifest_sha256": manifest_sha,
                      "test_save_premise": save, "live_observation": live, "plan_only": args.plan_only,
                      "fixture_disk_evidence": fixture_disk_evidence,
                      "selftest_automatic": False, "preview_automatic": False, "command_automatic": False,
                      "submit_automatic": False, "production_backend_registered": False}
            if not args.plan_only:
                # Keep the identified read-only handle alive across _run, so a
                # stale PID cannot silently become a different process object.
                args.dll = str((lab.OUTPUT / lab.DLL_NAME).resolve())
                report["installation"] = inject_probe._run(args, expected_game_hash=lab.LOCAL_SHA256)
            print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"inject_lab_v7_1375: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
