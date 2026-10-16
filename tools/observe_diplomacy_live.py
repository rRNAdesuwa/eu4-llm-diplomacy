"""Read-only diplomacy effects, recipient replies and exact sharing-pair CLI."""
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
from bridge.diplomacy_live_observer import LiveDiplomacyObserver, live_catalog, make_live_server
from bridge.tag_command_backend import decode, read, require


def compact(value):
    effect, reply, knowledge = value.get("effect", {}), value.get("reply", {}), value.get("knowledge", {})
    selected = reply.get("selected", {}).get("pending", {}).get("selected_matches", [])
    pair = knowledge.get("selected", {})
    return {k: value.get(k) for k in ("request_id", "transport_state", "completion_state", "request_state", "record")} | {
        "effect_status": effect.get("status"), "selected_effect_verified": effect.get("selected_effect_verified", False),
        "completion_stage": effect.get("completion_stage"), "changes": effect.get("changes", {}),
        "pending_requests": [{k: row.get(k) for k in
            ("native_request_id", "state_raw", "state_label", "actor_handle", "recipient_handle")} for row in selected],
        "correlated_notifications": reply.get("correlated_notifications", []),
        "knowledge_pair_status": knowledge.get("status"), "knowledge_pair": pair.get("pair"),
        "knowledge_provider": pair.get("provider"), "knowledge_recipient": pair.get("recipient"),
        "knowledge_object": pair.get("object"), "institution_completion_verified": False,
        "effect_failure": effect.get("failure"), "reply_failure": reply.get("failure"),
        "native_calls": 0, "requests_published": 0, "saves_written": 0, "automatic_command_retry": False,
        "capture_duration_ms": value.get("capture", {}).get("duration_ms"),
        "reply_capture_duration_ms": reply.get("duration_ms"), "knowledge_capture_duration_ms": knowledge.get("duration_ms")}


def result_code(value):
    if value.get("effect", {}).get("selected_effect_verified"):
        return 0
    return 3 if value.get("request_state") == "waiting_for_recipient" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--allow-tag-host", action="store_true",
        help="Permit only the exact pinned build-7 research DLL already loaded")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("catalog")
    prepare = sub.add_parser("prepare", help="Capture before dispatch; writes only an immutable local baseline")
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument("--action", required=True)
    prepare.add_argument("--actor", required=True)
    prepare.add_argument("--target", required=True)
    serve = sub.add_parser("serve", help="Authenticated read-only loopback HTTP; no prepare/publisher endpoint")
    serve.add_argument("--port", type=int, default=8775)
    for name in ("status", "watch"):
        item = sub.add_parser(name)
        item.add_argument("--request-id", required=True)
        item.add_argument("--compact", action="store_true")
        if name == "watch":
            item.add_argument("--duration-seconds", type=int, default=30)
            item.add_argument("--interval-ms", type=int, default=1000)
    args = parser.parse_args()
    if args.operation == "catalog":
        print(json.dumps(live_catalog(), ensure_ascii=False))
        return 0
    require(args.session_file is not None, "--session-file required")
    identity = decode(read(args.session_file.resolve(), 32768))["identity"]
    observer = LiveDiplomacyObserver(identity, store=args.store, allow_tag_host=args.allow_tag_host)
    if args.operation == "prepare":
        value = observer.prepare({"request_id": args.request_id, "action": args.action,
            "actor": args.actor, "target": args.target})
        print(json.dumps(value, ensure_ascii=False))
        return 0
    if args.operation == "serve":
        server = make_live_server(observer, port=args.port, token=os.environ.get("EU4_OBSERVER_TOKEN"))
        print(f"Read-only live observer: http://127.0.0.1:{server.server_port}/observer/v1/effects/<request-id>", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.operation == "status":
        value = observer.observe(args.request_id)
        print(json.dumps(compact(value) if args.compact else value, ensure_ascii=False))
        return result_code(value)
    require(1 <= args.duration_seconds <= 300 and 250 <= args.interval_ms <= 10000,
        "Watch duration/interval bounds")
    deadline, previous = time.monotonic()+args.duration_seconds, None
    while True:
        value = observer.observe(args.request_id)
        summary = compact(value)
        key = json.dumps({k: v for k, v in summary.items() if k not in
            ("record", "capture_duration_ms", "reply_capture_duration_ms", "knowledge_capture_duration_ms")}, sort_keys=True)
        if key != previous:
            print(json.dumps(summary if args.compact else value, ensure_ascii=False), flush=True)
            previous = key
        if value.get("completion_state") in ("selected_effect_observed", "in_progress") or time.monotonic() >= deadline:
            return result_code(value)
        time.sleep(min(args.interval_ms/1000, max(0, deadline-time.monotonic())))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "unknown", "automatic_command_retry": False,
            "error": str(exc), "native_calls": 0, "requests_published": 0}), file=sys.stderr)
        raise SystemExit(2)
