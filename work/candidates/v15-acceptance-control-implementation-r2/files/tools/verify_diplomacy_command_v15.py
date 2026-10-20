"""Offline verification of the seventy-two-case command wrapper/gate lifecycle phase.

No process access or engine calls. Requires lifecycle and preview evidence from
the same latest PID session. A false native gate result is a completed check,
not a failed experiment; a true result does not prove execution or AI acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import verify_diplomacy_lifecycle_v15 as lifecycle
from tools import verify_diplomacy_preview_v15 as preview

require = lifecycle.require
MAX_LOG_BYTES = lifecycle.MAX_LOG_BYTES
MAX_LINE_BYTES = lifecycle.MAX_LINE_BYTES
SCOPE = "command_lifecycle_only"
COMMAND_SOURCE = "work/native/pair-command-1375.cpp"
TRUE_FIELDS = ("wrapper_return_matches", "command_verified", "command_fields_verified", "clone_distinct",
               "clone_fields_verified", "original_fields_verified", "gate_called", "identities_after_gate",
               "command_destructor_returned", "original_destructor_returned")
CLONE_OBSERVATION = "pinned_command_destructor_path_only"
EVENT_TRANSLATION = {name: name.replace("pair_command_", "pair_preview_", 1) for name in lifecycle.COMMAND_EVENTS}


class CommandSession:
    """Two independent phase validators, each consuming the same stream once.

The second validator reuses the preview matrix/identity/thread checks on
explicitly translated command records. Command-only ownership checks are
additional; no preview record is ever translated into command evidence.
"""
    def __init__(self, event, line, pid):
        self.prior = preview.PreviewSession(event, line, pid)
        self.command = preview.PreviewSession({**event, "preview_automatic": event.get("command_automatic")}, line, pid)
        self.command.check(event.get("command_automatic") is False, "Command phase requires an explicit marker", line)

    @property
    def end_line(self):
        return self.command.end_line

    @end_line.setter
    def end_line(self, value):
        self.prior.end_line = self.command.end_line = value

    @property
    def last_event(self):
        return self.command.last_event

    @last_event.setter
    def last_event(self, value):
        self.prior.last_event = self.command.last_event = value

    def check(self, condition, message, line):
        self.prior.check(condition, message, line)
        return self.command.check(condition, message, line)

    def accept(self, event, line):
        name = event.get("event")
        if name in EVENT_TRANSLATION:
            if name == "pair_command_begin":
                prior = self.prior
                self.command.check(prior.error_count == 0 and prior.preview_phase == "complete"
                                   and prior.preview_case_count == 72 and set(prior.preview_cases) == preview.EXPECTED,
                                   "Command began before successful lifecycle and preview in this session", line)
                self.command.check(prior.last_frame is not None and prior.preview_complete_line is not None
                                   and prior.last_frame["line"] > prior.preview_complete_line
                                   and prior.last_frame["world_ready"] is True,
                                   "Command requires a later healthy frame after preview completion", line)
            self.prior.accept(event, line)  # Known later phase; never proves the earlier phases.
            translated = {**event, "event": EVENT_TRANSLATION[name]}
            if name == "pair_command_case":
                for flag in TRUE_FIELDS:
                    self.command.check(event.get(flag) is True, f"Command {flag} must be true", line)
                self.command.check(event.get("ownership_uncertain") is False, "Command ownership must be certain", line)
                self.command.check(event.get("clone_lifetime_observation") == CLONE_OBSERVATION,
                                   "Clone lifetime observation must identify the pinned destructor path only", line)
                # This synthetic validation flag means both returned normally;
                # output retains the raw command fields and never calls it an
                # independent observation of the clone's deallocation.
                translated["destroyed"] = (event.get("command_destructor_returned") is True
                                            and event.get("original_destructor_returned") is True)
            self.command.accept(translated, line)
            if name == "pair_command_case":
                action, target, value = event.get("action"), event.get("target"), event.get("value")
                if isinstance(action, str) and isinstance(target, str) and type(value) is bool:
                    key = (action, target, value)
                    if key in self.command.preview_cases:
                        record = self.command.preview_cases[key]
                        record.pop("destroyed", None)
                        for flag in (*TRUE_FIELDS, "ownership_uncertain", "clone_lifetime_observation"):
                            record[flag] = event.get(flag)
            return
        self.prior.accept(event, line)
        if name not in lifecycle.PREVIEW_EVENTS:
            # Lifecycle and frame events are required separately by both
            # validators; actual submission/unknown events fail both.
            self.command.accept(event, line)

    def finish(self):
        prior, command = self.prior.finish(), self.command.finish()
        command["command_begin_line"] = command.pop("preview_begin_line")
        command["command_complete_line"] = command.pop("preview_complete_line")
        command["command_event_records"] = command.pop("preview_event_records")
        command.pop("ignored_command_events", None)
        errors = prior["errors"] + command["errors"]
        return {"pid": command["pid"], "install_line": command["install_line"], "window_thread": command["window_thread"],
                "prior_lifecycle_and_preview": prior, "command_phase": command,
                "case_count": command["case_count"], "legal_count": command["legal_count"], "rejected_count": command["rejected_count"],
                "country_handles": command["country_handles"], "raw_dates": command["raw_dates"],
                "passed": prior["passed"] and command["passed"], "error_count": prior["error_count"] + command["error_count"],
                "errors": errors[:lifecycle.MAX_ERRORS]}


def read_session(path: Path, pid: int):
    """v15 requires its sibling metadata and permanent phase claims, even offline."""
    from work.native import lab_protocol_v15_1375 as lab
    path=Path(path)
    require(path.name=="research-1375.jsonl","Use the exact private v15 session log")
    raw=lab.decode_json(lab.read_bounded(path.parent/"session.json",4096).decode())
    metadata=lab.read_session_metadata(path.parent,pid,raw.get("process_creation_filetime"))
    evidence=lab.read_evidence(path.parent,metadata)
    proof=evidence["phase_proofs"].get('command')
    require(proof is not None and proof["passed"] is True,"Missing complete v15 phase proof")
    return proof,{"name":path.name,"size_bytes":evidence["log_bytes"],"sha256":evidence["log_sha256"],
        "read_kind":"fixed_size_log_snapshot_with_private_metadata_and_claims"}


def verify(log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    return lifecycle.verify_phase("command",log,pid,before,after,build_manifest)


def main(argv=None):
    """Read an explicitly identified v15 session; never opens a game process."""
    from work.native import lab_protocol_v15_1375 as lab
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid",type=int,required=True)
    parser.add_argument("--creation",required=True)
    args=parser.parse_args(argv)
    try:
        manifest,manifest_sha=lab.verify_build()
        session=lab.session_path(lab.OUTPUT,args.pid,args.creation)
        metadata=lab.read_session_metadata(session,args.pid,args.creation)
        result=lab.read_evidence(session,metadata)
        proof=result["phase_proofs"].get("command")
        print(json.dumps({"purpose":lab.PURPOSE,"phase":"command","proof":proof,
            "dll_sha256":manifest["dll_sha256"],"manifest_sha256":manifest_sha,
            "log_sha256":result["log_sha256"],"game_process_accessed":False,
            "applied_verified":False,"production_backend_registered":False},indent=2))
        return 0 if proof and proof["passed"] else 1
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print(str(error),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
