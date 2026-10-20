"""Read-only effect and recipient-reply CLI; never publishes game commands."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import DEFAULT_STORE
from bridge.diplomacy_effect_profiles import profile_catalog
from bridge.tag_command_backend import decode, read, require


def compact(value):
    effect, reply = value.get("effect", {}), value.get("reply", {})
    selected = reply.get("selected", {}).get("pending", {}).get("selected_matches", [])
    return {k: value.get(k) for k in ("request_id", "transport_state", "completion_state", "request_state", "record")} | {
        "effect_status": effect.get("status"),
        "selected_effect_verified": effect.get("selected_effect_verified", False),
        "completion_stage": effect.get("completion_stage"),
        "changes": effect.get("changes", {}),
        "pending_requests": [{k: row.get(k) for k in
            ("native_request_id", "state_raw", "state_label", "actor_handle", "recipient_handle")} for row in selected],
        "correlated_notifications": reply.get("correlated_notifications", []),
        "effect_failure": effect.get("failure"), "reply_failure": reply.get("failure"),
        "native_calls": 0, "requests_published": 0, "saves_written": 0,
        "capture_duration_ms": value.get("capture", {}).get("duration_ms"),
        "reply_capture_duration_ms": reply.get("duration_ms")}


def result_code(result):
    if result.get("effect", {}).get("selected_effect_verified"):
        return 0
    return 3 if result.get("request_state") == "waiting_for_recipient" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--allow-tag-host", action="store_true",
        help="Allow only the exact pinned V31 build-7 research module already loaded")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("catalog")
    serve = sub.add_parser("serve", help="Authenticated read-only loopback HTTP; no publisher")
    serve.add_argument("--port", type=int, default=8775)
    for name in ("status", "watch"):
        p = sub.add_parser(name)
        p.add_argument("--request-id", required=True)
        p.add_argument("--compact", action="store_true")
        if name == "watch":
            p.add_argument("--duration-seconds", type=int, default=30)
            p.add_argument("--interval-ms", type=int, default=1000)
    args = parser.parse_args()
    if args.operation == "catalog":
        print(json.dumps({"schema": "EU4DIPLOMACY-REPLY-CATALOG/1", "effect_profiles": profile_catalog(),
            "recipient_reply_profiles": ["ask_for_march"], "read_only": True,
            "native_calls": 0, "requests_published": 0, "all120_effect_profiles_complete": False}))
        return 0
    require(args.session_file is not None, "--session-file required")
    from bridge.diplomacy_reply_observer import ReplyAwareEffectObserver
    identity = decode(read(args.session_file.resolve(), 32768))["identity"]
    observer = ReplyAwareEffectObserver(identity, store=args.store, allow_tag_host=args.allow_tag_host)
    if args.operation == "serve":
        from bridge.diplomacy_observer_service import make_server
        server = make_server(observer, port=args.port, token=os.environ.get("EU4_OBSERVER_TOKEN"))
        print(f"Read-only reply observer: http://127.0.0.1:{server.server_port}/observer/v1/effects/<request-id>", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.operation == "status":
        result = observer.observe(args.request_id)
        print(json.dumps(compact(result) if args.compact else result, ensure_ascii=False))
        return result_code(result)
    require(1 <= args.duration_seconds <= 300 and 250 <= args.interval_ms <= 10000,
        "Watch duration/interval bounds")
    deadline, last = time.monotonic()+args.duration_seconds, None
    while True:
        result = observer.observe(args.request_id)
        summary = compact(result)
        key = json.dumps({k: v for k, v in summary.items() if k not in
            ("record", "capture_duration_ms", "reply_capture_duration_ms")}, sort_keys=True)
        if key != last:
            print(json.dumps(summary if args.compact else result, ensure_ascii=False), flush=True)
            last = key
        if result.get("completion_state") == "selected_effect_observed" or time.monotonic() >= deadline:
            return result_code(result)
        time.sleep(min(args.interval_ms/1000, max(0, deadline-time.monotonic())))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "unknown", "automatic_command_retry": False,
            "error": str(exc), "native_calls": 0, "requests_published": 0}), file=sys.stderr)
        raise SystemExit(2)
