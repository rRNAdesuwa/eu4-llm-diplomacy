"""JSON-lines entry point. Operator binding is separate from semantic input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "work"))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from local_config import game_exe

TOOLS = ("list_diplomatic_actions", "inspect_diplomatic_action", "execute_diplomatic_action", "get_diplomatic_result")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-session", type=Path)
    parser.add_argument("--offline-directory", type=Path, default=ROOT / "work/runtime/diplomacy-offline")
    parser.add_argument("--journal", type=Path, default=ROOT / "work/runtime/diplomacy-service/requests.sqlite3")
    parser.add_argument("--input-file", type=Path)
    args = parser.parse_args()
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


if __name__ == "__main__":
    main()
