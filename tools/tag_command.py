"""Inject/load, submit, and inspect explicit actor -> target native diplomacy commands."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.tag_command_backend import DEFAULT_MANIFEST, PublicationUnknownError, TagCommandBackend, decode, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="operation",required=True)
    sub.add_parser("capabilities")
    lookup = sub.add_parser("lookup", help="Read a native API mapping, including excluded research labels")
    lookup.add_argument("--action", required=True)
    search = sub.add_parser("search", help="Search TAG bindings and exclusions without game access")
    search.add_argument("--query", default="")
    search.add_argument("--category")
    search.add_argument("--support", choices=("bound","excluded"))
    search.add_argument("--offset", type=int, default=0)
    search.add_argument("--limit", type=int, default=20)
    conditions = sub.add_parser("conditions", help="Read documented conditions; does not inspect or call the game")
    conditions.add_argument("--action", required=True)
    load = sub.add_parser("load")
    load.add_argument("--pid",type=int,required=True)
    load.add_argument("--creation",required=True)
    for name in ("submit","batch","status","audit","serve"):
        p = sub.add_parser(name)
        p.add_argument("--session-file",type=Path,required=True)
        if name == "submit":
            for key in ("request-id","actor","target","action"):
                p.add_argument("--"+key,required=True)
        if name == "batch":
            p.add_argument("--commands",type=Path,required=True)
        if name in ("submit","batch"):
            p.add_argument("--test-only",action="store_true",help="Reject successes, uncertain actions, and original final-pass IDs; allow new tests only for proven clean rejections")
            p.add_argument("--ttl-ms",type=int,help="Shared batch deadline; default scales with command count")
        elif name in ("status", "audit"):
            p.add_argument("--request-id")
        else:
            p.add_argument("--port",type=int,default=8774)
    args = parser.parse_args()
    if args.operation == "audit":
        from bridge.tag_command_audit import recorded_snapshot
        identity = decode(read(args.session_file.resolve(),32768))["identity"]
        result = recorded_snapshot(args.manifest,identity).status(args.request_id)
        result.update(evidence_only=True,source_pins_verified=False,automatic_retry=False)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0
    backend = TagCommandBackend(args.manifest)
    exit_code = 0
    if args.operation == "capabilities":
        result = backend.capabilities()
    elif args.operation == "lookup":
        from bridge.tag_action_lookup import lookup_action
        result = lookup_action(backend, args.action)
    elif args.operation == "search":
        from bridge.tag_action_lookup import search_actions
        result = search_actions(backend, query=args.query, category=args.category,
                                support=args.support, offset=args.offset, limit=args.limit)
    elif args.operation == "conditions":
        from bridge.tag_action_conditions import action_conditions
        result = action_conditions(backend, args.action)
    elif args.operation == "load":
        result = backend.load(args.pid,args.creation)
    else:
        identity = decode(read(args.session_file.resolve(),32768))["identity"]
        if args.operation == "status":
            result = backend.status(identity,args.request_id)
        elif args.operation == "serve":
            from bridge.tag_command_service import make_server
            server = make_server(backend,identity,port=args.port,token=os.environ.get("EU4_DIPLOMACY_TOKEN"))
            print(f"TAG command API: http://127.0.0.1:{server.server_port}/native/v1/commands",flush=True)
            try:
                server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        else:
            commands = decode(read(args.commands.resolve(),65536)) if args.operation == "batch" else [
                {"request_id":args.request_id,"actor":args.actor,"target":args.target,"action":args.action}]
            try:
                result = backend.publish(identity,commands,ttl_ms=args.ttl_ms,test_only=args.test_only)
            except PublicationUnknownError as error:
                result = error.result
                exit_code = 2
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as error:
        print(f"TAG command refused: {error}; retain intents and inspect, never resend an unknown outcome",file=sys.stderr)
        raise SystemExit(2)
