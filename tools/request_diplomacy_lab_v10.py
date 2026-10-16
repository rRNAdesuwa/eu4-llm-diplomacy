"""Explicit session-bound EU4LAB/2 research requests; default is a read-only plan.

Not the production diplomacy API. --publish is required for every stage/pair/
speed request. Status only reads; it never retries an unknown native result.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v10_1375 as lab


def positive(text):
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("Must be positive")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=positive)
    parser.add_argument("--creation", help="Exact 16-lower-hex process creation identity")
    sub = parser.add_subparsers(dest="operation", required=True)
    discovery = sub.add_parser("capabilities", help="Offline catalog, research entrypoints and reviewed historical effects; never opens a process")
    discovery.add_argument("--action", help="One catalog action_id, or control.speed")
    discovery.add_argument("--research-only", action="store_true", help="Reviewed historical entrypoints and speed control; v10 candidate scope is reported separately")
    status = sub.add_parser("status")
    status.add_argument("--sequence", type=positive)
    stage = sub.add_parser("stage")
    stage.add_argument("phase", choices=tuple(lab.PHASES))
    stage.add_argument("--publish", action="store_true")
    pair = sub.add_parser("pair")
    pair.add_argument("action", choices=sorted(lab.ACTIONS))
    pair.add_argument("--actor", choices=lab.TAGS, default="FRA")
    pair.add_argument("--target", choices=lab.TAGS, required=True)
    pair.add_argument("--mode", choices=("legality_only", "submit"), default="legality_only")
    speed = sub.add_parser("speed")
    speed.add_argument("speed", type=int, choices=range(6))
    speed.add_argument("--watchdog-parent", type=positive)
    speed.add_argument("--watchdog-creation")
    fixture = sub.add_parser("fixture", help="Explicit fixed FRA test fixture only; no arbitrary console or script string")
    fixture.add_argument("action", choices=lab.FIXTURE_ACTIONS)
    for operation in (pair, speed, fixture):
        operation.add_argument("--sequence", type=positive, required=True)
        operation.add_argument("--ttl-ms", type=positive, default=5000)
        operation.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "capabilities":
            lab.require(args.pid is None and args.creation is None, "Offline capabilities does not accept a live process identity; use status separately")
            from bridge.diplomacy_research_capabilities import capabilities
            historical = capabilities(action_id=args.action, research_only=args.research_only)
            historical.update(invoked_cli_protocol=lab.PROTOCOL, v10_live_readiness=None,
                v10_candidate={"action_ids": sorted(lab.ACTIONS), "fixed_research_parameters": lab.FIXED_RESEARCH_PARAMETERS,
                               "runtime_verified": False, "production_backend_registered": False})
            print(json.dumps(historical, ensure_ascii=True, indent=2))
            return 0
        lab.require(args.pid is not None and args.creation is not None, "Live operations require both --pid and --creation")
        manifest, manifest_sha = lab.verify_build()
        with ExitStack() as resources:
            process = resources.enter_context(lab.LiveLabProcess(args.pid, expected_creation=args.creation))
            watchdog_check = None
            if args.operation == "speed" and args.speed > 0 and args.publish:
                watchdog_check = resources.enter_context(lab.watchdog_parent(args.watchdog_parent, args.watchdog_creation))
            session = lab.session_path(lab.OUTPUT, args.pid, process.creation)
            metadata = lab.read_session_metadata(session, args.pid, process.creation)
            def fixture_check():
                return lab.verify_installed_fixture(manifest,args.pid,process.creation)
            def refresh():
                # Revalidate the same manifest and loaded process identity before
                # publication. Nothing in the log selects a filename or address.
                _, current_sha = lab.verify_build()
                lab.require(current_sha == manifest_sha, "Manifest changed during this request")
                if watchdog_check:
                    watchdog_check()
                current_evidence = lab.read_evidence(session, metadata)
                lab.require(current_evidence["latest_frame"].get("running_speed_enabled") is manifest["running_speed_enabled"],
                            "Native running-speed gate differs from the pinned build")
                return current_evidence, process.snapshot()
            evidence, live = refresh()
            summary = {"purpose": lab.PURPOSE, "protocol": lab.PROTOCOL, "pid": args.pid, "creation": process.creation,
                       "dll_sha256": manifest["dll_sha256"], "manifest_sha256": manifest_sha,
                       "latest_frame": evidence["latest_frame"], "phases": evidence["phases"],
                       "last_sequence": evidence["last_sequence"], "pending": evidence["pending"],
                       "lease_pending": evidence["lease_pending"], "log_sha256": evidence["log_sha256"],
                       "applied_verified": False, "production_backend_registered": False}
            if args.operation == "pair":
                summary["fixed_research_parameters"] = lab.FIXED_RESEARCH_PARAMETERS.get(args.action, {})
            if args.operation == "fixture":
                summary["fixture_disk_evidence"] = fixture_check()
            if args.operation == "status":
                summary["read_only"] = True
                if args.sequence is not None:
                    summary["request"] = evidence["requests"].get(args.sequence)
                    lab.require(summary["request"] is not None, "No native record for this sequence; do not infer rejection or retry")
            else:
                keywords = {"phase": args.phase} if args.operation == "stage" else {
                    "sequence": args.sequence, "operation": args.operation, "ttl_ms": args.ttl_ms,
                    "mode": args.mode if args.operation == "pair" else "submit",
                    "action": args.action if args.operation in ("pair", "fixture") else "none",
                    "actor": args.actor if args.operation == "pair" else "FRA",
                    "target": args.target if args.operation == "pair" else "FRA",
                    "speed": args.speed if args.operation == "speed" else 0}
                lab.check_ready(evidence, live, lab.uptime_ms(), phase=keywords.get("phase"), operation=keywords.get("operation"))
                if args.operation != "stage":
                    lab.prepare_request(metadata, evidence, now=lab.uptime_ms(), **keywords)
                if args.publish:
                    summary["publication"] = lab.publish_research(session, metadata, manifest_sha, evidence, live,
                                                                 recheck=refresh, watchdog_verified=watchdog_check is not None,
                                                                 fixture_check=fixture_check if args.operation == "fixture" else None, **keywords)
                else:
                    summary.update(plan_only=True, requested=keywords, request_written=False)
            print(json.dumps(summary, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"request_diplomacy_lab_v10: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
