"""Bounded offline verification of the five-family, twenty-case native preview.

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
from tools import verify_diplomacy_lifecycle as lifecycle

require = lifecycle.require
integer = lifecycle.integer
MAX_LOG_BYTES = lifecycle.MAX_LOG_BYTES
MAX_LINE_BYTES = lifecycle.MAX_LINE_BYTES
TARGETS = ("ENG", "POR")
EXPECTED = {(action, target, value) for action in lifecycle.ACTIONS for target in TARGETS for value in (True, False)}
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
                       and 1 <= event["case_index"] <= 20, "Case indices must be exactly 1..20 in order", line)
            action, target, value = event.get("action"), event.get("target"), event.get("value")
            valid_key = isinstance(action, str) and action in lifecycle.ACTIONS and isinstance(target, str) and target in TARGETS and type(value) is bool
            self.check(valid_key, "Unknown action, target or non-boolean preview value", line)
            self.check(event.get("actor") == "FRA", "Preview actor must be FRA", line)
            self.check(type(value) is bool and event.get("mode") == ("positive" if value else "cancel"), "Mode does not match the exact boolean value", line)
            self.check(type(event.get("thread_id")) is int and event["thread_id"] == self.window_thread, "Preview case ran outside the window thread", line)
            for flag in ("state_verified", "initialized", "destroyed"):
                self.check(event.get(flag) is True, f"Preview {flag} must be true", line)
            self.check(type(event.get("allowed")) is bool, "Native allowed must be boolean (false is a valid result)", line)
            self.check(type(event.get("exception")) is int and event["exception"] == 0, "Preview exception must be integer zero", line)
            self.check(event.get("submitted") is False, "Preview case must have submitted=false", line)
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
            self.check(self.preview_case_count == 20 and set(self.preview_cases) == EXPECTED, "Native suite must contain exactly the twenty required combinations", line)
            legal = sum(case["allowed"] is True for case in self.preview_cases.values())
            rejected = sum(case["allowed"] is False for case in self.preview_cases.values())
            for field, expected in (("cases", 20), ("accepted", legal), ("rejected", rejected)):
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
        self.check(self.preview_case_count == 20 and set(self.preview_cases) == EXPECTED, "Twenty distinct preview combinations are required", self.end_line)
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
    """Use one bounded log snapshot for both lifecycle and preview validation."""
    selected, active, lines = None, False, 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(0, 2)
        remaining = size = stream.tell()
        stream.seek(0)
        require(size <= MAX_LOG_BYTES, f"Log exceeds {MAX_LOG_BYTES} bytes")
        while remaining:
            raw = stream.readline(min(MAX_LINE_BYTES + 1, remaining))
            require(raw, "Log was truncated during the read")
            remaining -= len(raw)
            digest.update(raw)
            lines += 1
            require(len(raw) <= MAX_LINE_BYTES, f"Log line {lines} exceeds {MAX_LINE_BYTES} bytes")
            try:
                require(raw.endswith(b"\n"), "Unterminated/truncated JSONL record")
                event = lifecycle.decode(raw)
            except lifecycle.EvidenceError as exc:
                if active:
                    selected.end_line, selected.last_event = lines, "invalid_json"
                    selected.check(False, str(exc), lines)
                continue
            if event.get("event") == "research_hook_installed":
                if active and not integer(event.get("pid"), 1):
                    selected.check(False, "Malformed subsequent installation boundary", lines)
                active = type(event.get("pid")) is int and event["pid"] == pid
                if active:
                    selected = PreviewSession(event, lines, pid)
            elif active:
                selected.accept(event, lines)
    require(selected is not None, "No research_hook_installed session for the requested PID")
    return selected.finish(), {"name": path.name, "size_bytes": size, "sha256": digest.hexdigest().upper(),
                               "lines": lines, "read_kind": "fixed_size_log_snapshot"}


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
    result = {"schema_version": 1, "verification_scope": "native_legality_preview", "read_only_analysis": True,
              "status": "failed", "runtime_verified": False, "execution_verified": False,
              "diplomatic_submission_verified": False, "ai_acceptance_verified": False,
              "settlement_verified": False, "all_game_state_unchanged_verified": False,
              "entire_dll_no_send_verified": False, "pid": pid, "inputs": {}, "errors": [], "limitations": [
                  "Native allowed is a legality result, not AI acceptance, a diplomatic submission or settlement. Native completion's historical accepted field is reported only as legal_count.",
                  "Before/after equality covers selected player/country identities, raw date, one directional relation cooldown and actor diplomat entries only. Snapshots are non-atomic and do not prove unchanged total game state.",
                  "Logs lack a DLL fingerprint and event timestamps. The supplied manifest does not independently bind the loaded DLL or prove all recorded events lie between the capture times.",
                  "Only this recorded no-submission phase is verified. A pipeline DLL may contain a separately triggered sender; actual send events invalidate this report."]}
    try:
        require(integer(pid, 1), "PID must be a positive integer")
        require(Path(before).resolve() != Path(after).resolve(), "Before and after must be separate captured report files")
        manifest, result["inputs"]["build_manifest"] = lifecycle.read_document(Path(build_manifest))
        require(manifest.get("purpose") in PURPOSES, "Manifest is not an accepted preview research profile")
        game_hash = lifecycle.hash_value(manifest.get("game_sha256"))
        require(game_hash == lifecycle.LOCAL_SHA256, "Manifest build is outside the audited preview profile")
        dll_hash = lifecycle.hash_value(manifest.get("dll_sha256"))
        sources = manifest.get("source_sha256")
        require(isinstance(sources, dict) and lifecycle.required_sources(manifest["purpose"], {PREVIEW_SOURCE}) <= set(sources), "Manifest must identify every source required by its research profile")
        for value in sources.values():
            lifecycle.hash_value(value)
        built_at = lifecycle.time_value(manifest.get("built_at_utc"), "built_at_utc")
        result["build"] = {"game_sha256": game_hash, "dll_sha256": dll_hash, "purpose": manifest["purpose"],
                           "loaded_dll_identity_verified": False, "manifest_hashes_format_valid": True}
        result["session"], result["inputs"]["log"] = read_session(Path(log), pid)
        initial_report, result["inputs"]["before"] = lifecycle.read_document(Path(before))
        final_report, result["inputs"]["after"] = lifecycle.read_document(Path(after))
        initial = lifecycle.snapshot_projection(initial_report, pid, game_hash)
        final = lifecycle.snapshot_projection(final_report, pid, game_hash)
        initial["country_handles"], final["country_handles"] = identities(initial_report), identities(final_report)
        require(initial["actor"] == "FRA" and initial["target"] == "ENG", "This profile requires the FRA→ENG diagnostic snapshot")
        require(initial["captured_at"] < final["captured_at"], "After capture must be strictly later than before capture")
        require(built_at <= final["captured_at"], "Manifest was built after the after snapshot")
        fields = ("module_base", "actor", "target", "player", "country_handles", "current_raw_date", "relation_cooldown", "actor_diplomats")
        comparisons = {key: {"equal": initial[key] == final[key], "before": initial[key], "after": final[key]} for key in fields}
        result["snapshot_comparison"] = {"before_captured_at_utc": initial["captured_at"].isoformat(), "after_captured_at_utc": final["captured_at"].isoformat(),
                                          "fields": comparisons, "all_compared_fields_equal": all(row["equal"] for row in comparisons.values()), "atomic": False}
        session = result["session"]
        result["summary"] = {"case_count": session["case_count"], "legal_count": session["legal_count"],
                             "rejected_count": session["rejected_count"], "result_meaning": "native_legality_only"}
        if not session["passed"]:
            result["errors"].append("Latest specified PID session did not pass its lifecycle and preview checks")
        for key, row in comparisons.items():
            if not row["equal"]:
                result["errors"].append(f"Before/after field changed: {key}")
        if session["raw_dates"] != [initial["current_raw_date"]]:
            result["errors"].append("Preview raw dates do not match the diagnostic snapshots")
        if session["country_handles"] != initial["country_handles"]:
            result["errors"].append("Preview country handles do not match the diagnostic snapshots")
        if not result["errors"]:
            result.update(status="passed", runtime_verified=True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        result["errors"].append(str(exc))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("log", "before", "after", "build-manifest", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args(argv)
    inputs = (args.log, args.before, args.after, args.build_manifest)
    same_input = args.output.resolve() in {path.resolve() for path in inputs}
    if args.output.exists():
        same_input = same_input or any(path.exists() and os.path.samefile(args.output, path) for path in inputs)
    if same_input:
        print(json.dumps({"status": "failed", "runtime_verified": False, "execution_verified": False,
                          "error": "Output must not overwrite input evidence"}), file=sys.stderr)
        return 2
    result = verify(args.log, args.pid, args.before, args.after, args.build_manifest)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"status": "failed", "runtime_verified": False, "execution_verified": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "status": result["status"], "verification_scope": result["verification_scope"],
                      "runtime_verified": result["runtime_verified"], "execution_verified": False,
                      "legal_count": result.get("session", {}).get("legal_count"), "rejected_count": result.get("session", {}).get("rejected_count"), "errors": result["errors"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
