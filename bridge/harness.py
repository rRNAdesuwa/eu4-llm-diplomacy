"""No-API Codex CLI planning harness for the EU4LLM bridge.

This module only plans and writes reviewable local artifacts.  It never opens
the game, submits a console command, reads API credentials, or executes model
output as code.  A model response is reduced to fixed supported decisions
and then passed through the existing bridge compiler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from .compiler import RequestError, compile_request
from .protocol import ID_PATTERN, ProtocolError, Snapshot, parse_file


SCHEMA_PATH = Path(__file__).with_name("decision.schema.json")
DEFAULT_CODEX = "codex"
DEFAULT_OUTPUT_DIR = Path("work") / "runtime"
DEFAULT_TIMEOUT = 120.0
DECISION_ACTIONS = frozenset({"hold", "improve_relations", "declare_war"})
_MAX_TEXT_LENGTH = 20_000
_MODEL_KEYS = frozenset({"reply", "strategy", "action", "target", "request_id"})


class HarnessError(RuntimeError):
    """Raised when planning or local artifact generation cannot continue."""


@dataclass(frozen=True)
class Decision:
    """A validated model decision with a harness-generated request ID."""

    reply: str
    strategy: str
    action: str
    target: str
    request_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "reply": self.reply,
            "strategy": self.strategy,
            "action": self.action,
            "target": self.target,
            "request_id": self.request_id,
        }


@dataclass(frozen=True)
class HarnessArtifacts:
    """Paths written by a harness invocation."""

    prompt_path: Path | None = None
    decision_path: Path | None = None
    request_path: Path | None = None
    run_path: Path | None = None

    def to_dict(self) -> dict[str, str]:
        return {
            key: str(value)
            for key, value in {
                "prompt": self.prompt_path,
                "decision": self.decision_path,
                "request": self.request_path,
                "run": self.run_path,
            }.items()
            if value is not None
        }


def _text(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise HarnessError(f"decision field {name!r} must be a string")
    if len(value) > _MAX_TEXT_LENGTH:
        raise HarnessError(f"decision field {name!r} is too long")
    return value


def generate_request_id() -> str:
    """Generate a safe request ID outside the model response."""

    # Keep the result short enough for the bridge compiler's 32-character
    # identifier limit while retaining practical per-run uniqueness.
    request_id = "req_" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + "_" + secrets.token_hex(4)
    if ID_PATTERN.fullmatch(request_id) is None:  # pragma: no cover - defensive
        raise HarnessError("internal request ID generation produced an invalid ID")
    return request_id


def latest_snapshot(log_path: str | Path) -> Snapshot:
    """Parse a log strictly and return its latest complete FRA snapshot."""

    parsed = parse_file(log_path, strict=True)
    if not parsed.snapshots:
        raise HarnessError(f"no complete FRA snapshot found in {log_path}")
    return parsed.snapshots[-1]


def build_prompt(snapshot: Snapshot, message: str) -> str:
    """Build a bounded planning prompt from validated state and user text."""

    if not isinstance(snapshot, Snapshot):
        raise TypeError("snapshot must be a bridge.protocol.Snapshot")
    required = {"treasury", "manpower_raw", "stability", "year", "ai", "war", "locked"}
    if required - set(snapshot.fields):
        raise HarnessError(f"incomplete snapshot: missing {sorted(required - set(snapshot.fields))}")
    for key in required:
        try:
            number = Decimal(snapshot.fields[key])
        except (InvalidOperation, ValueError):
            raise HarnessError(f"invalid snapshot number: {key}") from None
        if not number.is_finite():
            raise HarnessError(f"non-finite snapshot number: {key}")
    for key in ("ai", "war", "locked"):
        if snapshot.fields[key] not in ("0", "1"):
            raise HarnessError(f"invalid snapshot flag: {key}")
    if snapshot.country != "FRA" or snapshot.fields["ai"] != "1":
        raise HarnessError("planning requires an AI-controlled FRA snapshot")
    if not isinstance(message, str) or not message.strip():
        raise HarnessError("diplomatic message must be non-empty text")
    if len(message) > _MAX_TEXT_LENGTH:
        raise HarnessError("diplomatic message is too long")

    state = {
        "id": snapshot.snapshot_id,
        "country": snapshot.country,
        "fields": {
            key: snapshot.fields[key]
            for key in ("treasury", "manpower_raw", "stability", "year", "ai", "war", "locked")
            if key in snapshot.fields
        },
    }
    state_json = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        "You are a constrained diplomatic planning assistant for a single-player EU4 bridge.\n"
        "Return exactly one JSON object matching the supplied output schema.\n"
        "Allowed action values are hold, improve_relations and declare_war, targeting ENG. "
        "declare_war is fixed to FRA reconquest of Maine (177), cb_core. The game "
        "requires AI FRA, active diplomacy lock, independence, the CB and an ENG-owned "
        "FRA core in 177, with no existing FRA-ENG war, truce or alliance. It never "
        "unlocks native AI diplomacy. Never propose unlock, lock, console commands, "
        "scripts, arbitrary CBs, provinces, targets or code.\n"
        "The request ID is generated by the harness after your response; do not "
        "rely on a model-supplied request ID.\n"
        "The snapshot contains only the validated fields below. Diplomacy and "
        "foreign intelligence are incomplete, so avoid inventing facts.\n\n"
        "Respond in Chinese as France's diplomatic representative. improve_relations "
        "only adds a scripted opinion modifier; it cannot arrange peace or send a diplomat. "
        "The snapshot does not establish war prerequisites. Choose declare_war only "
        "when the player's message explicitly asks for this reconquest; otherwise "
        "use hold or improve_relations. The game checks prerequisites at execution.\n"
        "<player_diplomatic_message>\n"
        + message
        + "\n</player_diplomatic_message>\n\n"
        "<latest_fra_snapshot_json>\n"
        + state_json
        + "\n</latest_fra_snapshot_json>\n"
    )


def validate_decision(raw: Mapping[str, Any], *, request_id: str | None = None) -> Decision:
    """Validate model JSON and attach a harness-generated ID.

    A model-provided ``request_id`` is accepted only for schema compatibility,
    validated as an identifier, and ignored.  Callers should pass an
    externally generated ``request_id``; omitting it generates one here.
    """

    if not isinstance(raw, Mapping):
        raise HarnessError("Codex response must be a JSON object")
    unknown = set(raw) - _MODEL_KEYS
    if unknown:
        raise HarnessError(f"Codex response has unknown field(s): {sorted(unknown)!r}")
    missing = {"reply", "strategy", "action", "target"} - set(raw)
    if missing:
        raise HarnessError(f"Codex response is missing field(s): {sorted(missing)!r}")

    reply = _text(raw["reply"], name="reply")
    strategy = _text(raw["strategy"], name="strategy")
    action = raw["action"]
    if not isinstance(action, str) or action not in DECISION_ACTIONS:
        raise HarnessError(f"action must be one of {sorted(DECISION_ACTIONS)!r}")
    target = raw["target"]
    if target != "ENG":
        raise HarnessError("target is restricted to ENG")

    if "request_id" in raw:
        model_id = raw["request_id"]
        if not isinstance(model_id, str) or ID_PATTERN.fullmatch(model_id) is None:
            raise HarnessError("model request_id is invalid; IDs must be generated externally")
    resolved_id = request_id or generate_request_id()
    if ID_PATTERN.fullmatch(resolved_id) is None:
        raise HarnessError("external request_id is invalid")
    return Decision(reply, strategy, action, target, resolved_id)


def _invoke_codex(
    prompt: str,
    *,
    output_dir: Path,
    codex: str = DEFAULT_CODEX,
    timeout: float = DEFAULT_TIMEOUT,
) -> Mapping[str, Any]:
    """Invoke Codex CLI with no shell and return its JSON output."""

    if not isinstance(codex, str) or not codex:
        raise HarnessError("codex executable must be a non-empty path or command")
    if timeout <= 0:
        raise HarnessError("timeout must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=".codex-decision-",
            dir=output_dir,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        command = [
            codex,
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--output-schema",
            str(SCHEMA_PATH),
            "-o",
            str(temporary_path),
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HarnessError(f"Codex CLI timed out after {timeout:g} seconds") from error
        except OSError as error:
            raise HarnessError(f"could not start Codex CLI: {error}") from error
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()
            if len(detail) > 500:
                detail = detail[:500] + "..."
            raise HarnessError(
                f"Codex CLI exited with status {completed.returncode}"
                + (f": {detail}" if detail else "")
            )
        if temporary_path is None or not temporary_path.exists():
            raise HarnessError("Codex CLI did not write its -o output file")
        try:
            decoded = json.loads(temporary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise HarnessError(f"Codex output is not valid UTF-8 JSON: {error}") from error
        if not isinstance(decoded, Mapping):
            raise HarnessError("Codex output must be a JSON object")
        return decoded
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _request_for_decision(decision: Decision) -> dict[str, str]:
    if decision.action in ("improve_relations", "declare_war"):
        return {
            "id": decision.request_id,
            "action": decision.action,
            "target": "ENG",
        }
    # hold is deliberately compiled as a repeatable read-only snapshot so the
    # artifact remains executable without granting the model another action.
    return {"id": decision.request_id, "action": "snapshot"}


def run_harness(
    *,
    log_path: str | Path,
    message: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    codex: str = DEFAULT_CODEX,
    timeout: float = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> HarnessArtifacts:
    """Plan once and write local review artifacts; never submit them to EU4."""

    snapshot = latest_snapshot(log_path)
    prompt = build_prompt(snapshot, message)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    if dry_run:
        prompt_path = destination / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        return HarnessArtifacts(prompt_path=prompt_path)

    raw_decision = _invoke_codex(
        prompt,
        output_dir=destination,
        codex=codex,
        timeout=timeout,
    )
    decision = validate_decision(raw_decision)
    request = _request_for_decision(decision)
    try:
        run_script = compile_request(request)
    except RequestError as error:
        raise HarnessError(f"could not compile generated request: {error}") from error

    decision_path = destination / "decision.json"
    request_path = destination / "request.json"
    run_path = destination / "run.txt"
    decision_path.write_text(
        json.dumps(decision.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    run_path.write_text(run_script, encoding="utf-8", newline="\n")
    return HarnessArtifacts(
        decision_path=decision_path,
        request_path=request_path,
        run_path=run_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bridge.harness",
        description="Plan from the latest EU4LLM snapshot through the local Codex CLI.",
    )
    parser.add_argument("--log", required=True, type=Path, help="path to game.log")
    parser.add_argument("--message", required=True, help="player diplomatic message")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--codex", default=DEFAULT_CODEX, help="Codex executable path")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="write prompt.txt without invoking Codex or writing action artifacts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifacts = run_harness(
            log_path=args.log,
            message=args.message,
            output_dir=args.output_dir,
            codex=args.codex,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
    except (HarnessError, ProtocolError, RequestError, OSError, UnicodeError) as error:
        print(f"eu4llm-harness: error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(artifacts.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

