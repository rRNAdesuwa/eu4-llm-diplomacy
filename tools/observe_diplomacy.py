"""Read-only diplomacy effects CLI. Never injects, publishes, saves or reloads."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import DEFAULT_STORE, EffectObserver
from bridge.diplomacy_effect_profiles import profile_catalog
from bridge.tag_command_backend import decode, read, require


def compact(value):
    effect = value.get("effect", {})
    return {k: value.get(k) for k in ("request_id", "transport_state", "completion_state", "record")} | {
        "effect_status": effect.get("status"), "selected_effect_verified": effect.get("selected_effect_verified", False),
        "completion_stage": effect.get("completion_stage"), "changes": effect.get("changes", {}),
        "failure": effect.get("failure"), "native_calls": 0, "saves_written": 0,
        "capture_duration_ms": value.get("capture", {}).get("duration_ms"),
        "rpm_calls": value.get("capture", {}).get("rpm_budget", {}).get("calls")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("catalog")
    serve = sub.add_parser("serve", help="Read-only loopback HTTP API; no command publication endpoints")
    serve.add_argument("--port", type=int, default=8775)
    prepare = sub.add_parser("prepare", help="Capture a baseline before publication; does not publish")
    prepare.add_argument("--commands", type=Path, required=True)
    prepare.add_argument("--legacy-probe", type=Path, help="Explicitly import an existing two-pass pre-dispatch probe")
    for name in ("status", "watch"):
        p = sub.add_parser(name)
        p.add_argument("--request-id", required=True)
        p.add_argument("--compact", action="store_true")
        if name == "watch":
            p.add_argument("--duration-seconds", type=int, default=30)
            p.add_argument("--interval-ms", type=int, default=1000)
    args = parser.parse_args()
    if args.operation == "catalog":
        print(json.dumps({"schema": "EU4DIPLOMACY-OBSERVER-CATALOG/1", "profiles": profile_catalog(),
            "native_calls": 0, "requests_published": 0, "all120_effect_profiles_complete": False}, ensure_ascii=False))
        return 0
    require(args.session_file is not None, "--session-file required")
    identity = decode(read(args.session_file.resolve(), 32768))["identity"]
    observer = EffectObserver(identity, store=args.store)
    if args.operation == "serve":
        from bridge.diplomacy_observer_service import make_server
        server = make_server(observer, port=args.port, token=os.environ.get("EU4_OBSERVER_TOKEN"))
        print(f"Read-only effect observer: http://127.0.0.1:{server.server_port}/observer/v1/capabilities", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.operation == "prepare":
        commands = decode(read(args.commands.resolve(), 65536))
        require(type(commands) is list and 1 <= len(commands) <= 8, "At most eight bounded observation baselines")
        require(len({c["request_id"] for c in commands}) == len(commands), "Duplicate baseline request")
        results = [observer.prepare(c, legacy_probe=args.legacy_probe) for c in commands]
        print(json.dumps({"baselines": results, "native_calls": 0, "requests_published": 0}))
        return 0
    if args.operation == "status":
        result = observer.observe(args.request_id)
        print(json.dumps(compact(result) if args.compact else result, ensure_ascii=False))
        return 0 if result.get("effect", {}).get("selected_effect_verified") else 2
    require(1 <= args.duration_seconds <= 300 and 250 <= args.interval_ms <= 10000, "Watch duration/interval bounds")
    deadline = time.monotonic()+args.duration_seconds
    last = None
    while True:
        result = observer.observe(args.request_id)
        summary = compact(result)
        key = json.dumps({k: v for k, v in summary.items() if k not in
                          ("record", "capture_duration_ms", "rpm_calls")}, sort_keys=True)
        if key != last:
            print(json.dumps(summary if args.compact else result, ensure_ascii=False), flush=True)
            last = key
        if result.get("completion_state") == "selected_effect_observed":
            return 0
        if time.monotonic() >= deadline:
            return 0 if result.get("effect", {}).get("selected_effect_verified") else 2
        time.sleep(min(args.interval_ms/1000, max(0, deadline-time.monotonic())))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "unknown", "automatic_command_retry": False,
            "error": str(exc), "native_calls": 0, "requests_published": 0}), file=sys.stderr)
        raise SystemExit(2)
