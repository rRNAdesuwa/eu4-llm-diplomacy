"""Review unclaimed commands from a terminal session. File-only; never sends.

Requires a previously captured integration report and the exact immutable audit.
An entered, claimed, rejected, dispatched, or uncertain command is excluded.
The resulting list is a review artifact, not an automatic recovery operation.
"""
import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_audit import recorded_snapshot
from bridge.tag_command_backend import decode, digest, encode, read, require, validate_command, write_new


def prepare(snapshot, commands, evidence):
    require(snapshot.raw == snapshot.complete, "Partial audit tail; continuation forbidden")
    require(snapshot.summary["terminal"], "Session is not terminal")
    require(not (snapshot.directory / "publisher.lock").exists(), "Uncertain publisher; inspect first")
    require(evidence["schema"] == "EU4TAG31-INTEGRATION/1" and evidence["file_only"] is True
            and evidence["identity"] == snapshot.identity and evidence["terminal"] is True
            and evidence["unknown_must_not_be_retried"] is True
            and evidence["audit_sha256"] == digest(snapshot.raw), "Captured evidence mismatch")
    require(type(commands) is list and 1 <= len(commands) <= snapshot.limit,
            "Original plan size bound")
    commands = [validate_command(c, snapshot.actions) for c in commands]
    require(len({c["request_id"] for c in commands}) == len(commands), "Duplicate planned request_id")
    require(evidence["planned"] == len(commands) == len(evidence["results"]),
            "Captured plan length mismatch")
    remaining, excluded = [], []
    states = Counter()
    for sequence, (command, captured) in enumerate(zip(commands, evidence["results"]), 1):
        current = snapshot.status(command["request_id"])
        require(current == captured and current["command"] == command and current["sequence"] == sequence,
                "Captured request result mismatch")
        states[current["state"]] += 1
        selected = [r for r in snapshot.rows if r["sequence"] == sequence]
        claim = snapshot.directory / f"{sequence}.claim"
        # The conservative criterion is no audit entry at all, no claim file,
        # and a complete, validated publication packet. A missing result alone
        # never makes a command eligible for continuation.
        if current["state"] == "not_dispatched":
            require(not selected and not claim.exists(), "Unproven unclaimed command")
            require((snapshot.directory / f"{sequence}.request").exists(), "Missing original publication")
            remaining.append(command)
        else:
            excluded.append({"original_sequence": sequence, "command": command,
                             "state": current["state"],
                             "native_call_begins": sum(r["event"] == "native_call_begin" for r in selected),
                             "may_resend": False})
    require(dict(states) == evidence["states"], "Captured state totals mismatch")
    require(sum(r["event"] == "native_call_begin" for r in snapshot.rows) == evidence["native_call_begins"],
            "Captured native call total mismatch")
    require(remaining, "No provably unclaimed commands remain")
    review = {
        "schema": "EU4TAG-CONTINUATION-REVIEW/1", "file_only": True, "publishes": False,
        "original_identity": snapshot.identity, "original_audit_sha256": digest(snapshot.raw),
        "original_commands_sha256": digest(encode(commands)),
        "captured_evidence_sha256": digest(encode(evidence)),
        "remaining_commands_sha256": digest(encode(remaining)),
        "original_count": len(commands), "remaining_count": len(remaining),
        "excluded_count": len(excluded), "excluded": excluded,
        "idempotency_keys_preserved": True, "only_unclaimed_commands": True,
        "source_pins_verified": False, "old_build_executable": False,
        "automatic_resume": False, "gameplay_effects_verified": False,
        "execution_prerequisites": [
            "Preserve the current game by saving it before exit.",
            "Exit the original process; do not hot-replace or reuse its terminal host.",
            "Load the preserved save in a fresh process with a currently verified build.",
            "Confirm explicit manual pause before publishing the reviewed remainder once.",
        ],
    }
    return remaining, review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--session-file", type=Path, required=True)
    p.add_argument("--commands", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    identity = decode(read(args.session_file, 32768))["identity"]
    commands_raw, evidence_raw = read(args.commands, 65536), read(args.evidence, 2 * 1024 * 1024)
    remaining, review = prepare(recorded_snapshot(args.manifest, identity),
                                decode(commands_raw), decode(evidence_raw))
    review.update(original_commands_file_sha256=digest(commands_raw),
                  captured_evidence_file_sha256=digest(evidence_raw))
    require(args.output.resolve() != args.report.resolve()
            and not args.output.exists() and not args.report.exists(), "Output already exists or paths overlap")
    write_new(args.output, encode(remaining))
    write_new(args.report, encode(review))
    print(__import__("json").dumps({k: v for k, v in review.items() if k != "excluded"}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(f"Continuation review refused: {error}; no command was sent", file=sys.stderr)
        raise SystemExit(2)
