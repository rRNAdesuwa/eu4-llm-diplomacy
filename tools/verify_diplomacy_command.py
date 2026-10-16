"""Offline verification of the twenty-case command wrapper/gate lifecycle phase.

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
from tools import verify_diplomacy_lifecycle as lifecycle
from tools import verify_diplomacy_preview as preview

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
                                   and prior.preview_case_count == 20 and set(prior.preview_cases) == preview.EXPECTED,
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
                if active and not lifecycle.integer(event.get("pid"), 1):
                    selected.check(False, "Malformed subsequent installation boundary", lines)
                active = type(event.get("pid")) is int and event["pid"] == pid
                if active:
                    selected = CommandSession(event, lines, pid)
            elif active:
                selected.accept(event, lines)
    require(selected is not None, "No research_hook_installed session for the requested PID")
    return selected.finish(), {"name": path.name, "size_bytes": size, "sha256": digest.hexdigest().upper(),
                               "lines": lines, "read_kind": "fixed_size_log_snapshot"}


def verify(log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    result = {"schema_version": 1, "verification_scope": SCOPE, "read_only_analysis": True,
              "status": "failed", "runtime_verified": False, "execution_verified": False,
              "diplomatic_submission_verified": False, "ai_acceptance_verified": False, "settlement_verified": False,
              "clone_deallocation_independently_observed": False, "all_game_state_unchanged_verified": False,
              "entire_dll_no_send_verified": False, "pid": pid, "inputs": {}, "errors": [], "limitations": [
                  "Only the recorded wrapper, distinct clone fields, command gate and destructor-return lifecycle is evaluated. A true gate result is not submission, AI acceptance or settlement.",
                  "Clone lifetime is inferred from the pinned owning command-destructor path. Individual clone deallocation is not independently instrumented or observed.",
                  "The pipeline DLL may contain a separately triggered sender. This report covers only the no-submission log snapshot; actual send or unknown events are rejected.",
                  "Snapshots compare selected player/country identities, raw date, one directional cooldown and actor diplomat entries only, not total game-state immutability.",
                  "Logs lack DLL fingerprints and event timestamps; the manifest cannot independently bind the loaded DLL or place all events between snapshot capture times."]}
    try:
        require(lifecycle.integer(pid, 1), "PID must be a positive integer")
        require(Path(before).resolve() != Path(after).resolve(), "Before and after must be separate captured report files")
        manifest, result["inputs"]["build_manifest"] = lifecycle.read_document(Path(build_manifest))
        require(manifest.get("purpose") == lifecycle.PIPELINE_PURPOSE, "Manifest is not the audited explicit-marker pipeline profile")
        game_hash = lifecycle.hash_value(manifest.get("game_sha256"))
        require(game_hash == lifecycle.LOCAL_SHA256, "Manifest build is outside the audited command profile")
        dll_hash = lifecycle.hash_value(manifest.get("dll_sha256"))
        sources = manifest.get("source_sha256")
        require(isinstance(sources, dict) and lifecycle.required_sources(manifest["purpose"]) <= set(sources),
                "Manifest must identify all six pipeline sources, including the explicit sender")
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
        initial["country_handles"], final["country_handles"] = preview.identities(initial_report), preview.identities(final_report)
        require(initial["actor"] == "FRA" and initial["target"] == "ENG" and initial["player"]["tag"] == "FRA", "Command profile requires player/actor FRA and diagnostic target ENG")
        require(initial["captured_at"] < final["captured_at"], "After capture must be strictly later than before capture")
        require(built_at <= final["captured_at"], "Manifest was built after the after snapshot")
        fields = ("module_base", "actor", "target", "player", "country_handles", "current_raw_date", "relation_cooldown", "actor_diplomats")
        comparisons = {key: {"equal": initial[key] == final[key], "before": initial[key], "after": final[key]} for key in fields}
        result["snapshot_comparison"] = {"before_captured_at_utc": initial["captured_at"].isoformat(), "after_captured_at_utc": final["captured_at"].isoformat(),
                                          "fields": comparisons, "all_compared_fields_equal": all(row["equal"] for row in comparisons.values()), "atomic": False}
        session = result["session"]
        result["summary"] = {"case_count": session["case_count"], "legal_count": session["legal_count"], "rejected_count": session["rejected_count"],
                             "result_meaning": "native_command_gate_only", "clone_lifetime_observation": CLONE_OBSERVATION}
        if not session["passed"]:
            result["errors"].append("Latest specified PID session did not pass the prerequisite and command checks")
        for key, row in comparisons.items():
            if not row["equal"]:
                result["errors"].append(f"Before/after field changed: {key}")
        for phase in (session["prior_lifecycle_and_preview"], session["command_phase"]):
            if phase["raw_dates"] != [initial["current_raw_date"]] or phase["country_handles"] != initial["country_handles"]:
                result["errors"].append("Phase dates/country handles differ from the diagnostic snapshots")
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
    try:
        same_input = args.output.resolve() in {path.resolve() for path in inputs}
        if args.output.exists():
            same_input = same_input or any(path.exists() and os.path.samefile(args.output, path) for path in inputs)
        require(not same_input, "Output must not overwrite input evidence")
        if args.output.exists():
            previous, _ = lifecycle.read_document(args.output)
            require(previous.get("verification_scope") in (None, SCOPE), "Output must not replace another phase's verification report")
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "runtime_verified": False, "execution_verified": False, "error": str(exc)}), file=sys.stderr)
        return 2
    result = verify(args.log, args.pid, args.before, args.after, args.build_manifest)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"status": "failed", "runtime_verified": False, "execution_verified": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "status": result["status"], "verification_scope": SCOPE,
                      "runtime_verified": result["runtime_verified"], "execution_verified": False,
                      "summary": result.get("summary"), "errors": result["errors"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
