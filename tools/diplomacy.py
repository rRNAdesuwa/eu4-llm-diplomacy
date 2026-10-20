"""JSON-lines diplomacy tools, with compatible V1/V2/V3 research commands."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy_api import APIError, DEFAULT_CATALOG, DEFAULT_DATABASE, DiplomacyAPI, decode_json
from work.local_config import get_path


def legacy_main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-version", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--url", help="HTTP service base URL; omitted means a local offline API")
    parser.add_argument("--game-exe", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--queue-db", type=Path, default=DEFAULT_DATABASE)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities")
    sub.add_parser("describe").add_argument("action")
    for verb in ("preview", "submit", "validate", "request"):
        sub.add_parser(verb).add_argument("file", help="JSON file, or - for stdin")
    for verb in ("status", "audit", "reconcile"):
        sub.add_parser(verb).add_argument("request_id")
    args = parser.parse_args(argv)
    api = None
    try:
        if args.api_version in (2, 3) and args.command not in ("describe", "validate", "request"):
            raise APIError("version_command", f"V{args.api_version} supports only describe, validate and request drafts", 400)
        if args.api_version == 1 and args.command in ("validate", "request"):
            raise APIError("version_command", "validate/request require --api-version 2 or 3; V1 retains preview/submit", 400)
        if args.api_version in (2, 3) and (args.game_exe is not None or args.catalog != DEFAULT_CATALOG or args.queue_db != DEFAULT_DATABASE):
            raise APIError("version_option", f"V{args.api_version} has fixed evidence and no executable or queue database option", 400)
        body = None
        if args.api_version in (2, 3) and args.command in ("validate", "request"):
            if args.file == "-":
                source = getattr(sys.stdin, "buffer", sys.stdin).read(16 * 1024 + 1)
                if isinstance(source, str):
                    source = source.encode("utf-8")
            else:
                with Path(args.file).open("rb") as stream:
                    source = stream.read(16 * 1024 + 1)
            if len(source) > 16 * 1024:
                raise APIError("request_budget", f"V{args.api_version} request body exceeds 16 KiB", 413)
            body = decode_json(source.decode("utf-8"))
        elif args.command in ("preview", "submit"):
            source = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8-sig")
            body = decode_json(source)
        elif args.command == "reconcile":
            body = {}
        if args.url:
            route = ({"describe": f"/v{args.api_version}/actions/" + quote(getattr(args, "action", ""), safe=""),
                      "validate": f"/v{args.api_version}/validate", "request": f"/v{args.api_version}/requests"} if args.api_version in (2, 3) else {"capabilities": "/v1/capabilities", "describe": "/v1/actions/" + quote(getattr(args, "action", ""), safe=""),
                     "preview": "/v1/preview", "submit": "/v1/requests",
                     "status": "/v1/requests/" + quote(getattr(args, "request_id", ""), safe=""),
                     "reconcile": "/v1/requests/" + quote(getattr(args, "request_id", ""), safe="") + "/reconcile",
                     "audit": "/v1/requests/" + quote(getattr(args, "request_id", ""), safe="") + "/events"})[args.command]
            headers = {"Content-Type": "application/json"}
            token = os.environ.get("EU4_DIPLOMACY_TOKEN")
            if token:
                headers["Authorization"] = "Bearer " + token
            request = Request(args.url.rstrip("/") + route,
                              data=json.dumps(body).encode("utf-8") if body is not None else None, headers=headers)
            try:
                response = urlopen(request, timeout=30)
            except HTTPError as exc:
                response = exc
            with response:
                result = decode_json(response.read().decode("utf-8"))
                exit_code = 0 if response.status < 400 else 2
        elif args.api_version in (2, 3):
            contract = DiplomacyAPI.contract(version=args.api_version)
            result = contract.describe(args.action) if args.command == "describe" else getattr(contract, args.command)(body)
            exit_code = 2 if result.get("status") == "unsupported" else 0
        else:
            game_root = get_path("EU4_GAME_ROOT", required=False)
            executable = args.game_exe or (game_root / "eu4.exe" if game_root else None)
            api = DiplomacyAPI(args.catalog, args.queue_db, executable)
            if args.command == "capabilities":
                result = api.capabilities()
            elif args.command == "describe":
                result = api.describe(args.action)
            elif args.command in ("preview", "submit"):
                result = getattr(api, args.command)(body)
            else:
                result = getattr(api, args.command)(args.request_id)
            exit_code = 2 if result.get("status") in ("unsupported", "dispatch_unknown", "failed", "rejected") else 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code
    except APIError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, URLError, ValueError) as exc:
        print(json.dumps({"error": {"code": "client_error", "message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if api:
            api.close()


TOOLS = ("list_diplomatic_actions", "inspect_diplomatic_action", "execute_diplomatic_action", "get_diplomatic_result")


def jsonl_main(argv: list[str]) -> int:
    from bridge.diplomacy import DiplomacyTools, ObserverSession
    from bridge.diplomacy_journal import DurableJournal
    from work.local_config import game_exe

    parser = argparse.ArgumentParser(description=__doc__, epilog="Research commands remain available: capabilities, describe, preview, submit, validate, request, status, audit, reconcile. Use --legacy --help for their options.")
    parser.add_argument("--operator-session", type=Path)
    parser.add_argument("--offline-directory", type=Path, default=ROOT / "work/runtime/diplomacy-offline")
    parser.add_argument("--journal", type=Path, default=ROOT / "work/runtime/diplomacy-service/requests.sqlite3")
    parser.add_argument("--input-file", type=Path)
    args = parser.parse_args(argv)
    session = ObserverSession(args.operator_session, game_exe()) if args.operator_session else None
    directory = session.directory if session else args.offline_directory
    directory.mkdir(parents=True, exist_ok=True)
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    journal = DurableJournal(args.journal,
        experiment_id=session.experiment_id if session else "offline", session_id=session.session_id if session else "offline",
        global_request_ids=True)
    try:
        api = DiplomacyTools(journal, session)
        source = args.input_file.open(encoding="utf-8-sig") if args.input_file else sys.stdin
        try:
            for line in source:
                if not line.strip():
                    continue
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict) or set(request) != {"tool", "arguments"}:
                        raise ValueError("EXPECTED_TOOL_AND_ARGUMENTS")
                    if request["tool"] not in TOOLS or not isinstance(request["arguments"], dict):
                        raise ValueError("UNKNOWN_TOOL_OR_INVALID_ARGUMENTS")
                    result = getattr(api, request["tool"])(**request["arguments"])
                except (ValueError, TypeError) as error:
                    result = {"error": {"code": "INVALID_TOOL_REQUEST", "text": str(error)}, "submitted": False}
                print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
        finally:
            if args.input_file:
                source.close()
    finally:
        journal.close()
    return 0


LEGACY_COMMANDS = frozenset(("capabilities", "describe", "preview", "submit", "validate", "request", "status", "audit", "reconcile"))
LEGACY_OPTIONS = frozenset(("--api-version", "--url", "--game-exe", "--catalog", "--queue-db"))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--legacy":
        return legacy_main(arguments[1:])
    if arguments and (arguments[0] in LEGACY_COMMANDS or
                      any(value.split("=", 1)[0] in LEGACY_OPTIONS for value in arguments)):
        return legacy_main(arguments)
    return jsonl_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
