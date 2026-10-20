"""Offline, bounded verification of the 1.37.5 lifecycle-only experiment.

Reads JSON/JSONL evidence only. Never opens a game process or invokes an engine
function. A passing result verifies the recorded factory/clone/destruction
experiment, not diplomatic execution or absence of all game-state changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.native_build import LOCAL_SHA256

MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_ERRORS = 100
FRAME_RVA = "0x10a6ec0"
ACTIONS = {'vassalaction': 64, 'royal_marriage': 104, 'improve_relation': 64, 'guaranteeaction': 64, 'spy_network': 64, 'allianceaction': 64, 'milaccess': 64, 'offermilaccess': 64, 'fleet_access': 64, 'offer_fleet_access': 64, 'embargoaction': 64, 'warsubsidy': 72, 'warningaction': 64, 'insultaction': 72, 'form_coalition': 64, 'support_independence_action': 64, 'transfer_trade_power': 72, 'steer_trade': 64, 'giftaction': 72, 'trade_favors_for_gold': 64}
POSITIVE_ONLY = frozenset(('warningaction', 'insultaction', 'giftaction', 'trade_favors_for_gold'))
PREVIEW_EVENTS = {"pair_preview_case", "pair_preview_all_cases_complete", "pair_preview_rejected",
                  "pair_preview_begin", "pair_preview_complete"}
COMMAND_EVENTS = {"pair_command_case", "pair_command_all_cases_complete", "pair_command_rejected",
                  "pair_command_begin", "pair_command_complete", "pair_command_request_rejected"}
PIPELINE_PURPOSE = "research_pair_pipeline_with_explicit_submit"
PURPOSES = {"lifecycle_only_no_send", "lifecycle_and_preview_no_send", PIPELINE_PURPOSE}
SOURCES = {"work/native/research-frame-1375.cpp", "work/native/research-frame-1375.asm",
           "work/native/pair-probe-1375.cpp"}
PIPELINE_SOURCES = {"work/native/research-pipeline-1375.cpp", "work/native/research-frame-1375.asm",
                    "work/native/pair-probe-1375.cpp", "work/native/pair-preview-1375.cpp",
                    "work/native/pair-command-1375.cpp", "work/native/pair-submit-experiment-1375.cpp"}
HASH = re.compile(r"[0-9a-fA-F]{64}\Z")
TAG = re.compile(r"[A-Z0-9]{3}\Z")
POINTER = re.compile(r"0x[0-9a-fA-F]+\Z")


class EvidenceError(ValueError):
    pass


def required_sources(purpose: str, additional=()) -> set[str]:
    """Pipeline manifests identify the sender too, even for a no-send phase."""
    return PIPELINE_SOURCES if purpose == PIPELINE_PURPOSE else SOURCES | set(additional)


def decode(data: bytes):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise EvidenceError(f"Duplicate JSON key: {key}")
            value[key] = item
        return value

    def constant(value):
        raise EvidenceError(f"Invalid JSON numeric constant: {value}")

    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceError(f"Invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("Expected a JSON object")
    return value


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def integer(value, minimum=0, maximum=0xFFFFFFFF):
    return type(value) is int and minimum <= value <= maximum


def hash_value(value):
    require(isinstance(value, str) and HASH.fullmatch(value), "Missing or invalid SHA-256")
    return value.upper()


def time_value(value, label):
    try:
        require(isinstance(value, str), f"{label} is not a timestamp")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None and result.utcoffset() is not None, f"{label} has no UTC offset")
        return result
    except ValueError as exc:
        raise EvidenceError(f"Invalid {label}: {exc}") from exc


def read_document(path: Path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    require(len(data) <= MAX_JSON_BYTES, f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path.name}")
    return decode(data), {"name": path.name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}


def fixed_extra_valid(event, action):
    expected = {"fixed_gift_amount_milli": 25000 if action == "giftaction" else 0,
                "fixed_transfer_fraction_milli": 500 if action == "transfer_trade_power" else 0,
                "fixed_insult_index": -1 if action == "insultaction" else 0}
    return all(type(event.get(k)) is int and event[k] == v for k, v in expected.items())


class Session:
    def __init__(self, event, line, pid):
        self.pid, self.start_line = pid, line
        self.end_line = line
        self.window_thread = event.get("window_thread")
        self.errors = []
        self.error_count = 0
        self.frames = 0
        self.last_frame_count = 0
        self.last_frame = None
        self.last_event = event.get("event")
        self.phase = "installed"
        self.lifecycle = {}
        self.complete_line = None
        self.suite_complete = False
        self.ignored_preview_events = 0
        self.ignored_command_events = 0
        self.check(integer(pid, 1), "pid must be a positive integer", line)
        self.check(integer(self.window_thread, 1), "Invalid window_thread", line)
        self.check(event.get("send_enabled") is False, "Hook must have send_enabled=false", line)
        self.check(event.get("selftest_automatic") is False, "Hook must have selftest_automatic=false", line)
        self.check(event.get("frame_rva") == FRAME_RVA, "Unexpected frame_rva profile", line)

    def check(self, condition, message, line):
        if not condition:
            self.error_count += 1
            if len(self.errors) < MAX_ERRORS:
                self.errors.append({"line": line, "reason": message})
        return bool(condition)

    def accept(self, event, line):
        self.end_line, self.last_event = line, event.get("event")
        name = event.get("event")
        if "pid" in event:
            self.check(type(event["pid"]) is int and event["pid"] == self.pid, "Foreign/malformed PID inside selected session", line)
        if "submitted" in event:
            self.check(event["submitted"] is False, "Session event must not submit a diplomatic action", line)
        if "send_enabled" in event:
            self.check(event["send_enabled"] is False, "Session event must have sending disabled", line)
        if name in COMMAND_EVENTS:
            self.check(event.get("submitted") is False, "Later command phase must explicitly have submitted=false", line)
            self.ignored_command_events += 1  # Independent phase, never lifecycle proof.
        elif name in PREVIEW_EVENTS:
            self.ignored_preview_events += 1  # Never contributes lifecycle proof.
        elif name == "research_frame":
            self.frames += 1
            self.check(type(event.get("pid")) is int and event.get("pid") == self.pid, "Frame PID missing or mismatched", line)
            self.check(type(event.get("thread")) is int and event.get("thread") == self.window_thread, "Frame is not on the installed window thread", line)
            self.check(event.get("thread_changed") is False, "Frame reports changed or unknown thread identity", line)
            self.check(event.get("send_enabled") is False, "Frame send_enabled must be false", line)
            self.check(type(event.get("world_ready")) is bool, "Frame world_ready must be boolean", line)
            count = event.get("frames")
            if self.check(integer(count, 1, 0x7FFFFFFF), "Invalid frame counter", line):
                self.check(count > self.last_frame_count, "Frame counter did not strictly increase", line)
                self.last_frame_count = count
            self.last_frame = {"line": line, "pid": event.get("pid"), "thread": event.get("thread"),
                               "frames": count, "world_ready": event.get("world_ready"),
                               "thread_changed": event.get("thread_changed"), "send_enabled": event.get("send_enabled")}
        elif name == "pair_selftest_begin":
            self.check(self.phase == "installed", "Duplicate or out-of-order selftest begin", line)
            self.check(event.get("send_enabled") is False, "Selftest begin must have send_enabled=false", line)
            self.check(self.last_frame is not None and self.last_frame["world_ready"] is True and self.last_frame_count >= 100,
                       "Selftest has no prior ready frame at counter >=100", line)
            self.phase = "testing"
        elif name == "pair_lifecycle":
            self.check(self.phase == "testing", "Lifecycle record outside a started selftest", line)
            action = event.get("action")
            if not self.check(isinstance(action, str) and action in ACTIONS, "Unknown lifecycle action", line):
                return
            self.check(action not in self.lifecycle, "Duplicate lifecycle action", line)
            self.check(type(event.get("thread_id")) is int and event.get("thread_id") == self.window_thread, "Lifecycle ran outside the window thread", line)
            self.check(type(event.get("size")) is int and event.get("size") == ACTIONS[action], "Lifecycle object size differs from audited profile", line)
            for key in ("factory_fields_ok", "clone_fields_ok", "original_destroyed", "clone_destroyed"):
                self.check(event.get(key) is True, f"{action}: {key} must be true", line)
            self.check(type(event.get("exception")) is int and event["exception"] == 0, f"{action}: missing or nonzero exception", line)
            self.check(event.get("submitted") is False, f"{action}: submitted must be false", line)
            self.check(type(event.get("fixed_subsidy_amount_milli")) is int and event["fixed_subsidy_amount_milli"] == (1000 if action == "warsubsidy" else 0), "Fixed subsidy amount evidence differs", line)
            self.check(type(event.get("fixed_subsidy_duration_years")) is int and event["fixed_subsidy_duration_years"] == (10 if action == "warsubsidy" else 0), "Fixed subsidy years evidence differs", line)
            self.check(fixed_extra_valid(event, action), "Fixed gift/trade/insult evidence differs", line)
            expected_state = 2 if action == "form_coalition" else 0
            for stage in ("factory", "clone", "retained_original"):
                self.check(event.get(stage + "_contract_checked") is True,
                           f"{action}: {stage} contract was not fully checked", line)
                self.check(type(event.get(stage + "_state")) is int and event[stage + "_state"] == expected_state,
                           f"{action}: {stage} default state differs", line)
                self.check(type(event.get(stage + "_contract_failure_mask")) is int and event[stage + "_contract_failure_mask"] == 0,
                           f"{action}: {stage} contract failure mask is missing or nonzero", line)
            self.lifecycle[action] = {"line": line, **event}
        elif name == "pair_lifecycle_complete":
            self.check(self.phase == "testing", "Unexpected lifecycle suite completion", line)
            self.check(set(self.lifecycle) == set(ACTIONS), "Suite does not contain exactly the twenty required actions", line)
            self.check(type(event.get("passed")) is int and event["passed"] == 20, "Lifecycle suite passed count must be 20", line)
            self.check(event.get("submitted") is False, "Lifecycle suite must have submitted=false", line)
            self.suite_complete = True
            self.phase = "suite_complete"
        elif name == "pair_selftest_complete":
            self.check(self.phase == "suite_complete", "Selftest completion missing its lifecycle suite completion", line)
            self.check(event.get("passed") is True, "Selftest did not report passed=true", line)
            self.check(event.get("submitted") is False, "Selftest completion must have submitted=false", line)
            self.complete_line = line
            self.phase = "complete"
        else:
            self.check(False, f"Unexpected/rejected session event: {name!r}", line)

    def finish(self):
        self.check(self.phase == "complete" and self.suite_complete, "No successful complete selftest sequence", self.end_line)
        self.check(set(self.lifecycle) == set(ACTIONS), "Twenty distinct lifecycle records are required", self.end_line)
        self.check(self.frames > 0, "No research frames were recorded", self.end_line)
        final_healthy = (self.last_frame is not None and self.complete_line is not None
                         and self.last_frame["line"] > self.complete_line
                         and self.last_frame["world_ready"] is True
                         and self.last_frame["thread_changed"] is False
                         and self.last_frame["thread"] == self.window_thread
                         and self.last_event == "research_frame")
        self.check(final_healthy, "A healthy final frame after completion is required", self.end_line)
        return {"pid": self.pid, "install_line": self.start_line, "session_end_line": self.end_line,
                "window_thread": self.window_thread, "frame_records": self.frames, "last_frame": self.last_frame,
                "ignored_preview_events": self.ignored_preview_events,
                "ignored_command_events": self.ignored_command_events,
                "selftest_complete_line": self.complete_line, "lifecycle": self.lifecycle,
                "passed": self.error_count == 0, "error_count": self.error_count, "errors": self.errors}


def read_session(path: Path, pid: int):
    """v17 requires its sibling metadata and permanent phase claims, even offline."""
    from work.native import lab_protocol_v17_1375 as lab
    path=Path(path)
    require(path.name=="research-1375.jsonl","Use the exact private v17 session log")
    raw=lab.decode_json(lab.read_bounded(path.parent/"session.json",4096).decode())
    metadata=lab.read_session_metadata(path.parent,pid,raw.get("process_creation_filetime"))
    evidence=lab.read_evidence(path.parent,metadata)
    proof=evidence["phase_proofs"].get('lifecycle')
    require(proof is not None and proof["passed"] is True,"Missing complete v17 phase proof")
    return proof,{"name":path.name,"size_bytes":evidence["log_bytes"],"sha256":evidence["log_sha256"],
        "read_kind":"fixed_size_log_snapshot_with_private_metadata_and_claims"}


def pointer_value(value, label, *, zero=False):
    require(isinstance(value, str) and POINTER.fullmatch(value), f"Invalid {label} pointer")
    number = int(value, 16)
    require((zero and number == 0) or 0x10000 <= number < 0x0000800000000000, f"Out-of-range {label} pointer")
    return number


def snapshot_projection(report, pid, game_hash):
    require(report.get("schema_version") == 1 and type(report["schema_version"]) is int, "Unsupported probe schema")
    require(report.get("read_only") is True, "Probe report is not read-only")
    source = report.get("source", {})
    require(source.get("kind") == "live_process" and type(source.get("pid")) is int and source["pid"] == pid, "Probe is not from the requested live PID")
    require(hash_value(report.get("build", {}).get("sha256")) == game_hash, "Probe executable hash differs from manifest")
    if "executable_sha256" in report.get("build", {}):
        require(hash_value(report["build"]["executable_sha256"]) == game_hash, "Conflicting probe executable hashes")
    captured = time_value(report.get("captured_at_utc"), "captured_at_utc")
    state = report.get("state", {})
    require(state.get("status") == "bounded_snapshot" and state.get("country_identities_verified") is True, "Probe snapshot is partial or country identities are unverified")
    consistency = state.get("snapshot_consistency", {})
    require(all(consistency.get(key) is True for key in ("globals_unchanged", "player_unchanged", "date_unchanged")), "Probe changed during its own capture")
    require(all(isinstance(state.get(key), str) and TAG.fullmatch(state[key]) for key in ("actor", "target")), "Probe actor/target tags are missing or invalid")
    raw_date = state.get("current_raw_date")
    require(integer(raw_date, -0x80000000, 0x7FFFFFFF), "Probe raw date is missing or invalid")
    player = state.get("player", {})
    require(player.get("identity_valid") is True and integer(player.get("slot"), 0, 4095), "Player identity is not verified")
    require(isinstance(player.get("tag"), str) and TAG.fullmatch(player["tag"]), "Player tag is invalid")
    require(isinstance(player.get("handle"), str) and POINTER.fullmatch(player["handle"]), "Player handle is missing")
    handle = int(player["handle"], 16)
    require(0 < handle < 2**64 and (handle >> 32) & 0xFFFF == player["slot"], "Player full handle does not match its slot")
    require((handle & 0xFFFFFF).to_bytes(3, "little") == player["tag"].encode("ascii"), "Player full handle does not match its tag")
    diplomats = state.get("actor_diplomats", {})
    count, entries = diplomats.get("entry_count"), diplomats.get("entries")
    require(integer(count, 0, 256) and isinstance(entries, list) and len(entries) == count, "Diplomat data unavailable or malformed")
    projected_entries = []
    for index, entry in enumerate(entries):
        require(isinstance(entry, dict) and type(entry.get("index")) is int and entry["index"] == index, "Diplomat entries are not indexed consistently")
        raw = entry.get("state_raw_18")
        require(integer(raw, 0, 255), "Diplomat state byte is invalid")
        require(entry.get("state_zero_available_candidate") is (raw == 0), "Diplomat availability summary disagrees with raw byte")
        projected_entries.append({"index": index, "address": pointer_value(entry.get("address"), "diplomat"), "state_raw_18": raw})
    require(type(diplomats.get("state_zero_count")) is int and diplomats["state_zero_count"] == sum(entry["state_raw_18"] == 0 for entry in projected_entries), "Diplomat zero-state count disagrees with entries")
    begin = pointer_value(diplomats.get("vector_begin"), "diplomat vector_begin", zero=True)
    end = pointer_value(diplomats.get("vector_end"), "diplomat vector_end", zero=True)
    require(end - begin == count * 8 and (count == 0 or begin != 0), "Diplomat vector boundaries disagree with count")
    cooldown = state.get("relation_cooldown", {})
    threshold = cooldown.get("threshold_raw")
    require(integer(threshold, -0x80000000, 0x7FFFFFFF), "Cooldown threshold unavailable or malformed")
    require(type(cooldown.get("current_raw_date")) is int and cooldown["current_raw_date"] == raw_date, "Cooldown date disagrees with snapshot date")
    require(cooldown.get("strict_date_comparison") is (raw_date > threshold), "Cooldown comparison disagrees with raw values")
    return {"captured_at": captured, "module_base": pointer_value(source.get("module_base"), "module base"),
            "actor": state["actor"], "target": state["target"],
            "player": {"slot": player["slot"], "tag": player["tag"], "handle": handle,
                       "address": pointer_value(player.get("address"), "player")},
            "current_raw_date": raw_date,
            "relation_cooldown": {"address": pointer_value(cooldown.get("address"), "cooldown"), "threshold_raw": threshold,
                                  "current_raw_date": raw_date, "strict_date_comparison": cooldown["strict_date_comparison"]},
            "actor_diplomats": {"manager": pointer_value(diplomats.get("manager"), "diplomat manager"),
                                "vector_begin": begin, "vector_end": end, "entry_count": count,
                                "entries": projected_entries, "state_zero_count": diplomats["state_zero_count"]}}


def verify_phase(phase, log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    """Verify a v17 phase prefix plus same-process bounded diagnostic snapshots.

    The on-disk v17 DLL/source manifest and permanent session claims are checked.
    This function never opens a process and does not identify the actually loaded
    DLL independently. Requests after preflight require their own result review.
    """
    from work.native import lab_protocol_v17_1375 as lab
    from tools import verify_diplomacy_preview_v17 as preview
    scopes={"lifecycle":"lifecycle_only", "owned_peace":"default_owned_peace_lifecycle_only", "preview":"native_legality_preview", "command":"command_lifecycle_only"}
    result={"schema_version":1, "verification_scope":scopes.get(phase,"unknown"), "read_only_analysis":True,
            "status":"failed", "runtime_verified":False, "execution_verified":False,
            "diplomatic_submission_verified":False, "ai_acceptance_verified":False, "settlement_verified":False,
            "clone_deallocation_independently_observed":False, "all_game_state_unchanged_verified":False,
            "entire_dll_no_send_verified":False, "pid":pid, "inputs":{}, "errors":[],
            "limitations":["This verifies recorded no-send preflight only; no diplomatic effect or AI acceptance is proved.",
                "Snapshots compare bounded selected fields and are non-atomic; their timestamps do not bracket individual log events.",
                "The disk manifest and claims do not independently identify the actually loaded DLL."]}
    try:
        require(phase in scopes and integer(pid,1), "Unknown phase or invalid PID")
        log, before, after, build_manifest=map(Path,(log,before,after,build_manifest))
        require(log.name == "research-1375.jsonl" and build_manifest.name == "build.json", "Use the v17 session log and build manifest")
        require(before.resolve() != after.resolve(), "Before and after must be separate captured report files")
        manifest,manifest_sha=lab.verify_build(output=build_manifest.parent)
        require(manifest["purpose"] == lab.PURPOSE and set(manifest["source_sha256"]) == set(lab.SOURCES), "Expected the exact v17 twenty-source build")
        game_hash=hash_value(manifest["game_sha256"])
        initial_report,result["inputs"]["before"]=read_document(before)
        final_report,result["inputs"]["after"]=read_document(after)
        created=initial_report["source"].get("process_creation_filetime")
        require(integer(created,1,2**64-1) and type(final_report["source"].get("process_creation_filetime")) is int
                and final_report["source"]["process_creation_filetime"] == created,
                "Diagnostic reports lack the same complete process creation identity")
        for report in (initial_report,final_report):
            require(report["source"].get("process_exit_filetime") == 0 and type(report["source"].get("process_exit_filetime")) is int,
                    "Diagnostic report lacks an active-process exit identity")
        metadata=lab.read_session_metadata(log.parent,pid,f"{created:016x}")
        evidence=lab.read_evidence(log.parent,metadata)
        require(not evidence["requests"], "Verify the preserved preflight-only prefix; later requests require a separate review")
        proof=evidence["phase_proofs"].get(phase)
        require(proof is not None and proof["passed"] is True, "The exact v17 session phase did not pass")
        result["session"]=proof
        result["inputs"]["log"]={"name":log.name,"sha256":evidence["log_sha256"]}
        result["inputs"]["build_manifest"]={"name":build_manifest.name,"sha256":manifest_sha}
        result["build"]={"game_sha256":game_hash,"dll_sha256":manifest["dll_sha256"],"purpose":manifest["purpose"],
                          "source_and_dll_disk_hashes_verified":True,"loaded_dll_identity_verified":False}
        initial=snapshot_projection(initial_report,pid,game_hash)
        final=snapshot_projection(final_report,pid,game_hash)
        require(initial["captured_at"] < final["captured_at"], "After capture must be later than before")
        require(time_value(manifest["built_at_utc"],"built_at_utc") <= final["captured_at"], "Build postdates the final snapshot")
        require(initial["player"]["tag"] == initial["actor"] == "FRA" and initial["target"] == "ENG", "Diagnostic snapshot must use player/actor FRA and target ENG")
        fields=["module_base","actor","target","player","current_raw_date","relation_cooldown","actor_diplomats"]
        if phase in ("preview", "command"):
            initial["country_handles"]=preview.identities(initial_report)
            final["country_handles"]=preview.identities(final_report)
            fields.append("country_handles")
            phases=(proof["prior_lifecycle_and_preview"],proof["command_phase"]) if phase == "command" else (proof,)
            for item in phases:
                require(item["raw_dates"] == [initial["current_raw_date"]] and item["country_handles"] == initial["country_handles"],
                        "Phase dates/country handles differ from the diagnostic snapshots")
        if phase == "owned_peace":
            require(proof["frame_identity"]["raw_date"] == initial["current_raw_date"]
                and int(proof["frame_identity"]["player_handle"],16) == initial["player"]["handle"],
                "Owned-peace frame identity/date differs from bounded snapshots")
        comparisons={key:{"equal":initial[key] == final[key],"before":initial[key],"after":final[key]} for key in fields}
        result["snapshot_comparison"]={"fields":comparisons,"all_compared_fields_equal":all(v["equal"] for v in comparisons.values()),
            "before_captured_at_utc":initial["captured_at"].isoformat(),"after_captured_at_utc":final["captured_at"].isoformat(),"atomic":False}
        require(result["snapshot_comparison"]["all_compared_fields_equal"], "A bounded diagnostic field changed")
        result.update(status="passed",runtime_verified=True)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,RuntimeError) as exc:
        result["errors"].append(str(exc))
    return result


def verify(log: Path, pid: int, before: Path, after: Path, build_manifest: Path):
    return verify_phase("lifecycle",log,pid,before,after,build_manifest)


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
        proof=result["phase_proofs"].get("lifecycle")
        print(json.dumps({"purpose":lab.PURPOSE,"phase":"lifecycle","proof":proof,
            "dll_sha256":manifest["dll_sha256"],"manifest_sha256":manifest_sha,
            "log_sha256":result["log_sha256"],"game_process_accessed":False,
            "applied_verified":False,"production_backend_registered":False},indent=2))
        return 0 if proof and proof["passed"] else 1
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print(str(error),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
