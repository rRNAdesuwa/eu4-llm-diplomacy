"""Command-line interface for the offline bridge tooling."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .compiler import RequestError, compile_json_file
from .protocol import ProtocolError, parse_file, parsed_log_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eu4llm-bridge",
        description="Parse EU4LLM game.log records and compile safe run scripts.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    parse = commands.add_parser("parse", help="parse complete snapshots and ACKs from game.log")
    parse.add_argument("log", type=Path, help="path to game.log")
    parse.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parse.add_argument(
        "--lenient",
        action="store_true",
        help="drop malformed/incomplete records and include issues in JSON",
    )

    compile_command = commands.add_parser(
        "compile", help="compile a JSON request object/list to an EU4 run file"
    )
    compile_command.add_argument("requests", type=Path, help="JSON request file")
    compile_command.add_argument("output", type=Path, help="destination run file")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "parse":
            parsed = parse_file(args.log, strict=not args.lenient)
            print(
                parsed_log_json(
                    parsed,
                    pretty=args.pretty,
                    include_issues=args.lenient,
                )
            )
            return 0
        if args.command == "compile":
            requests = compile_json_file(args.requests, args.output)
            print(f"compiled {len(requests)} request(s) to {args.output}")
            return 0
    except (OSError, UnicodeError, ProtocolError, RequestError) as error:
        print(f"eu4llm-bridge: error: {error}", file=sys.stderr)
        return 2
    parser.error("no command selected")
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via python -m bridge
    raise SystemExit(main())

