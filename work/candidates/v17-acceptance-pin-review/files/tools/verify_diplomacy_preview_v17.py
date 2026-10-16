"""Bounded offline verification of the twenty-family, seventy-two-case native preview.

Reads evidence files only. Native allowed=false is a valid legality result;
neither allowed=true nor this verification means AI acceptance or execution.
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
from tools import verify_diplomacy_lifecycle_v17 as lifecycle

require = lifecycle.require
integer = lifecycle.integer
MAX_LOG_BYTES = lifecycle.MAX_LOG_BYTES
MAX_LINE_BYTES = lifecycle.MAX_LINE_BYTES
TARGETS = ("ENG", "POR")
EXPECTED = {(action, target, value) for action in lifecycle.ACTIONS for target in TARGETS
            for value in ((True,) if action in lifecycle.POSITIVE_ONLY else (True, False))}
PREVIEW_SOURCE = "work/native/pair-preview-1375.cpp"
PURPOSES = {"lifecycle_and_preview_no_send", lifecycle.PIPELINE_PURPOSE}


def country_handle(value, tag):
    require(isinstance(value, str) and lifecycle.POINTER.fullmatch(value), "Missing or malformed country handle")
    number = int(value, 16)
    require(0 < number < 2**64 and number >> 56 != 0, "Country handle lacks its generation/type byte")
    require((number >> 32) & 0xFFFF < 4096, "Country handle slot is out of range")
    require((number & 0xFFFFFF).to_bytes(3, "little") == tag.encode("ascii"), "Country handle does not identify its declared tag")
    return number


class PreviewSession(lifecycle.Session):
    def __init__(self, event, line, pid):
        super().__init__(event, line, pid)
        self.preview_phase = "waiting"
        self.preview_cases = {}
        self.preview_case_count = 0
        self.preview_complete_line = None
        self.preview_begin_line = None
        self.handles = {}
        self.raw_dates = set()
        self.check(event.get("preview_automatic") is False, "Preview must require an explicit marker", line)

    def accept(self, event, line):
        super().accept(event, line)
        name = event.get("event")
        if name == "pair_preview_begin":
            self.check(self.phase == "complete" and self.suite_complete and set(self.lifecycle) == set(lifecycle.ACTIONS),
                       "Preview began before its own session completed all lifecycle checks", line)
            self.check(self.preview_phase == "waiting", "Duplicate or out-of-order preview begin", line)
            self.check(self.complete_line is not None and self.last_frame is not None
                       and self.last_frame["line"] > self.complete_line and self.last_frame["world_ready"] is True,
                       "Preview requires a later healthy frame after lifecycle completion", line)
            self.check(event.get("send_enabled") is False and event.get("submitted") is False,
                       "Preview begin must disable sending and submission", line)
            self.preview_begin_line, self.preview_phase = line, "testing"
        elif name == "pair_preview_case":
            self.check(self.preview_phase == "testing", "Preview case outside a started preview", line)
            self.preview_case_count += 1
            self.check(type(event.get("case_index")) is int and event["case_index"] == self.preview_case_count
                       and 1 <= event["case_index"] <= 72, "Case indices must be exactly 1..72 in order", line)
            action, target, value = event.get("action"), event.get("target"), event.get("value")
            valid_key = isinstance(action, str) and action in lifecycle.ACTIONS and isinstance(target, str) and target in TARGETS and type(value) is bool
            self.check(valid_key, "Unknown action, target or non-boolean preview value", line)
            self.check(not valid_key or (action, target, value) in EXPECTED, "Unaudited cancellation mode", line)
            self.check(event.get("actor") == "FRA", "Preview actor must be FRA", line)
            self.check(type(value) is bool and event.get("mode") == ("positive" if value else "cancel"), "Mode does not match the exact boolean value", line)
            self.check(type(event.get("thread_id")) is int and event["thread_id"] == self.window_thread, "Preview case ran outside the window thread", line)
            for flag in ("state_verified", "initialized", "destroyed"):
                self.check(event.get(flag) is True, f"Preview {flag} must be true", line)
            self.check(type(event.get("allowed")) is bool, "Native allowed must be boolean (false is a valid result)", line)
            self.check(type(event.get("exception")) is int and event["exception"] == 0, "Preview exception must be integer zero", line)
            self.check(event.get("submitted") is False, "Preview case must have submitted=false", line)
            self.check(type(event.get("fixed_subsidy_amount_milli")) is int and event["fixed_subsidy_amount_milli"] == (1000 if action == "warsubsidy" else 0), "Fixed subsidy amount evidence differs", line)
            self.check(type(event.get("fixed_subsidy_duration_years")) is int and event["fixed_subsidy_duration_years"] == (10 if action == "warsubsidy" else 0), "Fixed subsidy years evidence differs", line)
            self.check(lifecycle.fixed_extra_valid(event, action), "Fixed gift/trade/insult evidence differs", line)
            date = event.get("current_raw_date")
            if self.check(integer(date, -0x80000000, 0x7FFFFFFF), "Preview date is missing or invalid", line):
                self.raw_dates.add(date)
            if valid_key:
                key = (action, target, value)
                self.check(key not in self.preview_cases, "Duplicate action/target/value combination", line)
                for tag, field in (("FRA", "actor_handle"), (target, "target_handle")):
                    try:
                        handle = country_handle(event.get(field), tag)
                        self.check(tag not in self.handles or self.handles[tag] == handle, "Country handle changed within the preview", line)
                        self.handles[tag] = handle
                    except lifecycle.EvidenceError as exc:
                        self.check(False, str(exc), line)
                self.preview_cases[key] = {"line": line, **{k: event.get(k) for k in (
                    "case_index", "action", "mode", "value", "actor", "target", "actor_handle", "target_handle",
                    "current_raw_date", "state_verified", "initialized", "allowed", "exception", "destroyed", "thread_id", "submitted")}}
        elif name == "pair_preview_all_cases_complete":
            self.check(self.preview_phase == "testing", "Unexpected native preview suite completion", line)
            self.check(self.preview_case_count == 72 and set(self.preview_cases) == EXPECTED, "Native suite must contain exactly the seventy-two required combinations", line)
            legal = sum(case["allowed"] is True for case in self.preview_cases.values())
            rejected = sum(case["allowed"] is False for case in self.preview_cases.values())
            for field, expected in (("cases", 72), ("accepted", legal), ("rejected", rejected)):
                self.check(type(event.get(field)) is int and event[field] == expected, f"Native completion {field} does not match case records", line)
            self.check(type(event.get("thread_id")) is int and event["thread_id"] == self.window_thread, "Native preview completion ran outside the window thread", line)
            self.check(event.get("submitted") is False, "Native preview completion must have submitted=false", line)
            self.preview_phase = "suite_complete"
        elif name == "pair_preview_complete":
            self.check(self.preview_phase == "suite_complete", "Preview completion lacks its complete native suite", line)
            self.check(event.get("passed") is True and event.get("submitted") is False, "Preview wrapper did not report a no-send success", line)
            self.preview_complete_line, self.preview_phase = line, "complete"
        elif name in ("pair_preview_rejected", "pair_preview_request_rejected"):
            self.check(False, "Preview attempt was rejected", line)

    def finish(self):
        result = super().finish()
        result["preview_event_records"] = result.pop("ignored_preview_events")
        self.check(self.preview_phase == "complete", "No completed preview sequence", self.end_line)
        self.check(self.preview_case_count == 72 and set(self.preview_cases) == EXPECTED, "Seventy-two distinct preview combinations are required", self.end_line)
        self.check(len(self.raw_dates) == 1, "Preview cases must share one raw date", self.end_line)
        self.check(self.last_frame is not None and self.preview_complete_line is not None
                   and self.last_frame["line"] > self.preview_complete_line and self.last_frame["world_ready"] is True
                   and self.last_event == "research_frame", "A healthy final frame after preview completion is required", self.end_line)
        result.update(passed=self.error_count == 0, error_count=self.error_count, errors=self.errors,
                      preview_begin_line=self.preview_begin_line, preview_complete_line=self.preview_complete_line,
                      cases=list(self.preview_cases.values()), case_count=self.preview_case_count,
                      legal_count=sum(case["allowed"] is True for case in self.preview_cases.values()),
                      rejected_count=sum(case["allowed"] is False for case in self.preview_cases.values()),
                      country_handles={tag: hex(value) for tag, value in self.handles.items()}, raw_dates=sorted(self.raw_dates))
        return result


def read_session(path: Path, pid: int):
    """v17 requires its sibling metadata and permanent phase claims, even offline."""
    from work.native import lab_protocol_v17_1375 as lab
    path=Path(path)
    require(path.name=="research-1375.jsonl","Use the exact private v17 session log")
    raw=lab.decode_json(lab.read_bounded(path.parent/"session.json",4096).decode())
    metadata=lab.read_session_metadata(path.parent,pid,raw.get("process_creation_filetime"))
    evidence=lab.read_evidence(path.parent,metadata)
    proof=evidence["phase_proofs"].get('preview')
    require(proof is not None and proof["passed"] is True,"Missing complete v17 phase proof")
    return proof,{"name":path.name,"size_bytes":evidence["log_bytes"],"sha256":evidence["log_sha256"],
        "read_kind":"fixed_size_log_snapshot_with_private_metadata_and_claims"}


def identities(report):
    countries = report.get("state", {}).get("countries")
    require(isinstance(countries, list) and len(countries) <= 4096, "Probe country identities are unavailable")
    selected = {}
    for row in countries:
        require(isinstance(row, dict), "Malformed probe country row")
        tag = row.get("tag")
        if tag not in ("FRA", *TARGETS):
            continue
        require(tag not in selected and row.get("identity_valid") is True, "Ambiguous or unverified probe country identity")
        handle = country_handle(row.get("handle"), tag)
        require(type(row.get("slot")) is int and row["slot"] == (handle >> 32) & 0xFFFF, "Probe country slot disagrees with handle")
        selected[tag] = hex(handle)
    require(set(selected) == {"FRA", *TARGETS}, "Probe must identify FRA, ENG and POR")
    return selected


def verify(log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    return lifecycle.verify_phase("preview",log,pid,before,after,build_manifest)


def main(argv=None):
    """Read an explicitly identified v17 session; never opens a game process."""
    from work.native import lab_protocol_v17_1375 as lab
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid",type=int,required=True)
    parser.add_argument("--creation",required=True)
    args=parser.parse_args(argv)
    try:
        manifest,manifest_sha=lab.verify_build()
        session=lab.session_path(lab.OUTPUT,args.pid,args.creation)
        metadata=lab.read_session_metadata(session,args.pid,args.creation)
        result=lab.read_evidence(session,metadata)
        proof=result["phase_proofs"].get("preview")
        print(json.dumps({"purpose":lab.PURPOSE,"phase":"preview","proof":proof,
            "dll_sha256":manifest["dll_sha256"],"manifest_sha256":manifest_sha,
            "log_sha256":result["log_sha256"],"game_process_accessed":False,
            "applied_verified":False,"production_backend_registered":False},indent=2))
        return 0 if proof and proof["passed"] else 1
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print(str(error),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
