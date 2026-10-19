"""Offline review of a finalized, explicitly inventoried v12 research session.

No process APIs, mailbox publication, or network calls. The manifest must be
finalized only after an exact held-handle exit observation. Save/reload claims
are optional, independently checked selected-state comparisons, never causality.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import canonical, decode_json
from work.native import lab_protocol_v12_1375 as lab
from work import probe_pair_extension_v11_1375 as observer
from work.inspect_diplomacy_save import inspect_save
from tools.verify_diplomacy_lifecycle_v12 import verify_phase

PID, CREATION, THREAD = 17676, "01dd56989186135c", 48456
WORLD = "0x1fb2c9cf0d0"
DLL_SHA = "465A20166E1DD04EA7360F6EA83ED02E3AFEE59A26048B1651EE6862F118CEBD"
MANIFEST_SHA = "652fb6901a43d3918397209a165c2ccd3adb5fd64dbe8b8757391f24d1797914"
PREFLIGHT_SHA = "3a95e5a85403c944ddb633baecba8e2c347e84d53602d26c7cf27f569a6b8f18"
PREFIX_SHA = "d324fb4e14f96f5a34c79c16ad7739c3c405fb2c9f62e0e9d8ef90269ed3d45d"
PREFIX_BYTES = 184298
MAX_ARTIFACTS, MAX_TOTAL, MAX_MANIFEST = 384, 64 * 1024 * 1024, 512 * 1024
MAX_SAVE = 512 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
require = lab.require
# Only these independently understood observers can support an effect claim.
EFFECTS = {
    "request_trade_power": ("transfer_trade_power", "positive"),
    "cancel_trade_power_transfer": ("transfer_trade_power", "cancel"),
    "steer_trade": ("steer_trade", "positive"),
    "cancel_steer_trade": ("steer_trade", "cancel"),
    "send_gift": ("giftaction", "positive"),
    "warn": ("warningaction", "positive"),
    "form_coalition": ("form_coalition", "positive"),
    "leave_coalition": ("form_coalition", "cancel"),
    "support_independence": ("support_independence_action", "positive"),
    "cancel_independence_support": ("support_independence_action", "cancel"),
}


def exact_int(value, minimum=0, maximum=2**63 - 1):
    return type(value) is int and minimum <= value <= maximum


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded(path, limit=lab.MAX_LOG):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "Input exceeds bounded read: " + str(path))
    return data


def relative_path(root, name):
    require(isinstance(name, str) and "\\" not in name and ":" not in name,
            "Expected canonical repository-relative path")
    parts = PurePosixPath(name)
    require(not parts.is_absolute() and parts.parts and all(p not in (".", "..") for p in parts.parts)
            and str(parts) == name, "Noncanonical input path")
    root = Path(root).resolve()
    path = root.joinpath(*parts.parts)
    require(path.resolve().is_relative_to(root), "Input escaped repository")
    cursor = path
    while cursor != root:
        require(not cursor.is_symlink() and not cursor.is_junction(), "Linked input path forbidden")
        cursor = cursor.parent
    return path


class Inputs:
    """Content-addressed, bounded artifacts; reject unused evidence too."""
    def __init__(self, root, entries):
        require(type(entries) is dict and 1 <= len(entries) <= MAX_ARTIFACTS, "Artifact count budget failed")
        self.root, self.entries, self.used = root, entries, set()
        paths, total = set(), 0
        for key, row in entries.items():
            require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", key), "Invalid artifact key")
            require(type(row) is dict and set(row) == {"path", "size_bytes", "sha256"}, "Invalid artifact descriptor")
            relative_path(root, row["path"])
            require(row["path"] not in paths, "Duplicate artifact path")
            paths.add(row["path"])
            require(exact_int(row["size_bytes"], 1, lab.MAX_LOG) and isinstance(row["sha256"], str)
                    and HEX.fullmatch(row["sha256"]), "Artifact size/hash invalid")
            total += row["size_bytes"]
        require(total <= MAX_TOTAL, "Aggregate artifact budget exceeded")

    def raw(self, key):
        require(key in self.entries, "Missing artifact reference: " + str(key))
        row = self.entries[key]
        data = bounded(relative_path(self.root, row["path"]), row["size_bytes"])
        require(len(data) == row["size_bytes"] and sha(data) == row["sha256"], "Artifact changed: " + key)
        self.used.add(key)
        return data

    def doc(self, key):
        return decode_json(self.raw(key).decode("utf-8-sig"))

    def selected(self, ref):
        require(type(ref) is dict and set(ref) == {"input", "select"} and type(ref["select"]) is list
                and len(ref["select"]) <= 6, "Invalid JSON selection")
        value = self.doc(ref["input"])
        for step in ref["select"]:
            require((type(value) is dict and type(step) is str and step in value)
                    or (type(value) is list and exact_int(step, 0, len(value) - 1)), "Missing selected evidence")
            value = value[step]
        require(type(value) is dict, "Selected evidence is not an object")
        return value


def identity(row, creation_key="creation"):
    require(type(row.get("pid")) is int and row["pid"] == PID and row.get(creation_key) == CREATION,
            "Foreign/incomplete process identity")


def validate_exit(document):
    row = document.get("exact_process_exit_observation", document)
    identity(row)
    require(row.get("exit_observed") is True and row.get("method") == "held_handle_wait_and_getprocesstimes"
            and exact_int(row.get("process_exit_filetime"), int(CREATION, 16) + 1, 2**64 - 1),
            "Finalization requires exact held-handle process exit")
    return row


def validate_status(status, row=None):
    identity(status)
    require(status.get("purpose") == lab.PURPOSE and status.get("protocol") == lab.PROTOCOL
            and status.get("dll_sha256") == DLL_SHA and status.get("manifest_sha256") == MANIFEST_SHA
            and status.get("applied_verified") is False and status.get("production_backend_registered") is False
            and isinstance(status.get("log_sha256"), str) and HEX.fullmatch(status["log_sha256"]),
            "Status build/evidence boundary differs")
    if row is not None:
        require(status.get("request") == row or status.get("native") == row, "Status differs from final native history")


def validate_host(host, wire, row=None):
    identity(host)
    require(set(host) == {"protocol", "purpose", "pid", "creation", "manifest_sha256", "request_sha256", "body_ascii", "automatic_retry"}
            and host["protocol"] == lab.PROTOCOL and host["purpose"] == lab.PURPOSE
            and host["manifest_sha256"] == MANIFEST_SHA and host["automatic_retry"] is False
            and host["body_ascii"].encode("ascii") == wire and host["request_sha256"] == sha(wire), "Host intent/claim differ")
    if row is not None:
        require(lab.decode_request(wire) == row["request"], "Host intent/native request differ")


def validate_pair(row, outcome):
    """A completed legality test is never a diplomatic submit/effect."""
    request, records, complete = row["request"], row["records"], row["complete"]
    identity(request)
    require(request["operation"] == "pair" and outcome in ("dispatched", "legality_allowed", "legality_rejected", "guard_rejected"), "Invalid pair outcome")
    submit = outcome == "dispatched"
    require(request["mode"] == ("submit" if submit else "legality_only"), "Mode/outcome differs")
    require([r.get("event") for r in records] == (["pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete"]
            if submit else ["pair_engine_begin", "pair_engine_complete"]), "Unexpected native ownership boundaries")
    final = records[-1]
    for record in records:
        identity(record, "process_creation_filetime")
        require(record.get("thread_id") == THREAD and type(record["thread_id"]) is int and record.get("world") == WORLD
                and record.get("action_id") == request["action"] and record.get("actor") == request["actor"]
                and record.get("target") == request["target"], "Foreign native pair/thread/world")
        for tag, field in ((request["actor"], "actor_handle"), (request["target"], "target_handle")):
            require(int(record[field], 16) == observer.HANDLES[tag], "Native full country handle differs")
        fixed = {"fixed_subsidy_amount_milli": 1000 if request["action"] in ("give_subsidies", "cancel_subsidies") else 0,
                 "fixed_subsidy_duration_years": 10 if request["action"] in ("give_subsidies", "cancel_subsidies") else 0,
                 "fixed_gift_amount_milli": 25000 if request["action"] == "send_gift" else 0,
                 "fixed_transfer_fraction_milli": 500 if request["action"] in ("request_trade_power", "cancel_trade_power_transfer") else 0,
                 "fixed_insult_index": -1 if request["action"] == "insult" else 0}
        require(all(type(record.get(k)) is int and record[k] == v for k, v in fixed.items()), "Fixed native scalar differs")
    require(type(final.get("exception")) is int and final["exception"] == 0
            and final.get("ownership_uncertain") is False and final.get("freeze_session") is False
            and final.get("applied_verified") is False and final.get("retry_allowed") is False
            and final.get("submit_entered") is submit and final.get("submit_returned") is submit,
            "Uncertain native completion/ownership")
    if outcome == "guard_rejected":
        require(type(final.get("reason")) is int and final["reason"] == 13
                and type(final.get("status")) is int and final["status"] == 0 and final.get("phase") == 3
                and all(final.get(k) is False for k in ("preview_called", "preview_allowed", "gate_called", "gate_allowed",
                                                       "original_destroyed", "command_destroyed_before_dispatch"))
                and final.get("context_submit_return") is None and final.get("caller_container_consumed") is None,
                "Expected bounded pre-allocation guard rejection; no native legality claim")
    elif outcome == "legality_rejected":
        require(type(final.get("reason")) is int and final["reason"] in (17, 18)
                and type(final.get("status")) is int and final["status"] == 1 and final.get("preview_called") is True
                and final.get("original_destroyed") is True
                and final.get("context_submit_return") is None and final.get("caller_container_consumed") is None,
                "Rejection lacks its native boundary")
        require((final["reason"] == 17 and final.get("phase") == 6 and final.get("preview_allowed") is False
                 and final.get("gate_called") is False and final.get("gate_allowed") is False
                 and final.get("command_destroyed_before_dispatch") is False)
                or (final["reason"] == 18 and final.get("phase") == 8 and final.get("preview_allowed") is True
                    and final.get("gate_called") is True and final.get("gate_allowed") is False
                    and final.get("command_destroyed_before_dispatch") is True), "Rejection cleanup/phase differs")
    else:
        require(type(final.get("status")) is int and final["status"] == (2 if submit else 1)
                and type(final.get("reason")) is int and final["reason"] == 0
                and final.get("preview_called") is True and final.get("preview_allowed") is True
                and final.get("gate_called") is True and final.get("gate_allowed") is True
                and final.get("original_destroyed") is True
                and final.get("command_destroyed_before_dispatch") is (not submit)
                and final.get("context_submit_return") is (True if submit else None)
                and final.get("caller_container_consumed") is (True if submit else None), "Dispatch/legality was not completed")
    require(all(type(complete.get(k)) is type(final[k]) and complete[k] == final[k]
                for k in ("status", "reason", "submit_entered", "submit_returned", "ownership_uncertain")),
            "Host/native completion differs")
    return final


def validate_publication(document, host, sequence):
    identity(document)
    require(document.get("research_only") is True and document.get("protocol") == lab.PROTOCOL
            and document.get("status") == "published" and document.get("sequence") == sequence
            and type(document["sequence"]) is int and document.get("phase") is None
            and document.get("request_sha256") == host["request_sha256"]
            and document.get("automatic_retry") is False and document.get("native_dispatch_verified") is False
            and document.get("applied_verified") is False and document.get("production_backend_registered") is False,
            "Initial CLI publication receipt differs")


def validate_http(report, row, intent, host):
    request = row["request"]
    expected = {k: request[k] for k in ("pid", "creation", "sequence", "mode", "action", "actor", "target")}
    expected.update(protocol=lab.PROTOCOL, ttl_ms=5000)
    require(report.get("request") == expected and report.get("server_closed") is True
            and report.get("server_thread_joined") is True and report.get("automatic_retry") is False
            and report.get("token_written_to_disk") is False and report.get("effect_verified") is False
            and report.get("ai_acceptance_verified") is False and report.get("exit_code") == 0,
            "HTTP report boundary differs")
    require(intent.get("kind") == "eu4_lab_v12_research_http" and intent.get("request") == expected
            and intent.get("request_sha256") == sha(canonical(expected).encode("ascii"))
            and intent.get("manifest_sha256") == MANIFEST_SHA and intent.get("automatic_retry") is False,
            "HTTP durable intent differs")
    seq = request["sequence"]
    steps = report["steps"]
    require([(e["method"], e["route"], e["http_status"]) for e in steps] == [
        ("GET", "/research/v12/status", 200), ("POST", "/research/v12/pair", 202),
        ("GET", f"/research/v12/requests/{seq}", 200), ("POST", "/research/v12/pair", 200)], "HTTP sequence differs")
    for step in steps:
        response = step["response"]
        identity(response)
        require(response.get("purpose") == lab.PURPOSE and response.get("protocol") == lab.PROTOCOL
                and response.get("production") is False and response.get("research_only") is True
                and response.get("production_backend_registered") is False and response.get("applied_verified") is False,
                "HTTP response overclaims readiness/effects")
    first, queried, replay = [e["response"] for e in steps[1:]]
    require(first.get("request_written") is True and first.get("replayed") is False
            and replay.get("request_written") is False and replay.get("replayed") is True, "HTTP wrote duplicate request")
    for response in (first, queried, replay):
        require(response.get("request_sha256") == host["request_sha256"] and response.get("sequence") == seq, "HTTP wire differs")
    for response in (queried, replay):
        require(response.get("native") == row and response.get("request") == request
                and response.get("state") == "native_completed", "HTTP/native result differs")
    return steps[0]["response"]


def validate_supervisor(events, row):
    require(len(events) == 2 and events[0].get("event") == "supervisor_armed"
            and events[1].get("event") == "supervisor_complete", "Incomplete or interrupted speed supervision")
    for event in events:
        identity(event)
        require(event.get("sequence") == row["request"]["sequence"] and event.get("speed") == row["request"]["speed"]
                and event.get("retry_allowed") is False, "Supervisor belongs to another request")
    for sample in (events[0]["before"], events[1]["after"]):
        require(sample.get("game") == int(WORLD, 16) and sample.get("player") == observer.HANDLES["FRA"]
                and sample.get("paused") is True and sample.get("native_speed_index") == 0, "Speed did not finish in matching paused world")
    require(events[1].get("native_lease_complete") == row["lease_complete"], "Supervisor/native lease differs")


def validate_effect(case, row, before, after, comparison, input_hashes):
    action = row["request"]["action"]
    require(action in EFFECTS and row["request"]["mode"] == "submit", "Unsupported selected effect family/mode")
    family, direction = EFFECTS[action]
    # These expectations come from the pinned experiment contract, never from observed deltas.
    expected = {"expected_amount_milli": 25000 if action == "send_gift" else None,
                "expected_fraction_milli": 500 if family == "transfer_trade_power" else None}
    require(case.get("expected") == {k: v for k, v in expected.items() if v is not None}, "Missing/altered independent fixed expectation")
    recomputed = observer.compare_reports(before, after, direction, **expected)
    require(comparison == dict(recomputed, inputs=input_hashes) and recomputed.get("observed_effect") is True
            and recomputed.get("transition") == ("exact_selected_economic_delta" if action == "send_gift"
                else "removed_selected_state" if direction == "cancel" else "added_selected_state"),
            "Selected effect cannot be independently reproduced; absence alone is not a cancellation")
    for report in (before, after):
        sample, _, _ = observer.validated_report(report)
        identity({"pid": report["source"]["pid"], "creation": f'{report["source"]["process_creation_filetime"]:016x}'})
        require(sample["game"] == WORLD and report["action"] == family and report["target"] == row["request"]["target"],
                "Effect snapshot belongs to another process/world/pair/family")
    require(after["observation"]["passes"][0]["current_raw_date"] == row["records"][-1]["raw_date"], "Effect after-date differs from dispatch")
    return recomputed


def semantic_state(state):
    """Only serialized relationship identity; process addresses are intentionally excluded."""
    require(state.get("state") in ("active", "absent"), "Persistence only supports selected relation state")
    if state["state"] == "absent":
        return {"state": "absent"}
    obj = state["object"]
    fields = ("type_marker", "first_handle", "second_handle", "started_raw_date", "removed", "fraction_milli", "extra_flag")
    return {"state": "active", **{k: int(obj[k], 16) if k.endswith("handle") else obj[k] for k in fields if k in obj}}


def validate_saved_relation(document, family, target, expected_state, start_date):
    require(document.get("parsed_complete") is True and document.get("read_only") is True
            and document.get("evidence_scope") == "serialized_state_only" and document.get("runtime_effects_verified") is False
            and document.get("actor") == "FRA" and target in document.get("targets", [])
            and document.get("global_diplomacy", {}).get("container_found") is True,
            "Save is not a complete selected diplomacy extraction")
    require(family in ("transfer_trade_power", "steer_trade", "warningaction"), "Persistence matcher for this family is not implemented")
    serialized_key = "warning" if family == "warningaction" else family
    found = []
    for record in document["global_diplomacy"]["records"]:
        if record["key"] != serialized_key:
            continue
        values = {}
        for entry in record["entries"]:
            key = entry["key"]
            require(key not in values and "value" in entry, "Ambiguous nested/duplicate serialized relation field")
            values[key] = entry["value"]
        if {values.get("first"), values.get("second")} == {"FRA", target}:
            found.append(values)
    if expected_state == "absent":
        require(found == [] and start_date is None, "Selected canceled relation remains/has invented start date")
    else:
        require(expected_state == "active" and len(found) == 1, "Missing/duplicate selected saved relation")
        value = found[0]
        first, second = ("FRA", target) if family == "warningaction" else (target, "FRA")
        require(value.get("first") == first and value.get("second") == second and value.get("start_date") == start_date,
                "Saved selected direction/start differs")
        if family == "warningaction":
            require(set(value) == {"first", "second", "start_date"}, "Unknown serialized warning variant")
        else:
            require(value.get("is_enforced") == "no", "Saved trade relation flag differs")
        if family == "transfer_trade_power":
            require(value.get("amount") == "0.500", "Saved fraction differs from fixed 500 milli")


def stream_save_hash(path, size, digest):
    require(exact_int(size, 1, MAX_SAVE) and isinstance(digest, str) and HEX.fullmatch(digest), "Save size/hash invalid")
    total, hasher = 0, hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            total += len(block)
            require(total <= size, "Save exceeds pinned size")
            hasher.update(block)
    require(total == size and hasher.hexdigest() == digest, "Save bytes differ")


def validate_save_copy(saved, spec):
    require(Path(saved["source"]["path"]).name == spec["filename"], "Extraction destination filename differs")
    if "copy_evidence" not in saved:
        return
    proof = saved["copy_evidence"]
    require(type(proof) is dict and set(proof) == {"source", "destination_create_new", "source_identity_before_after_equal", "size_bytes", "sha256", "source_stat"}
            and isinstance(proof["source"], str) and 1 <= len(proof["source"]) <= 2048
            and Path(proof["source"]).name != spec["filename"]
            and proof["destination_create_new"] is True and proof["source_identity_before_after_equal"] is True
            and type(proof["size_bytes"]) is int and proof["size_bytes"] == spec["size_bytes"]
            and proof["sha256"].lower() == spec["sha256"] and type(proof["source_stat"]) is list
            and len(proof["source_stat"]) == 3 and all(exact_int(x, 0, 2**64-1) for x in proof["source_stat"])
            and proof["source_stat"][0] == spec["size_bytes"], "Bounded preserved-copy record differs")
    # The original source path/stat is recorded provenance, not a fresh re-read.


def validate_launch(launch, spec, reload):
    require(type(launch.get("new_pid")) is int and launch["new_pid"] == reload["pid"]
            and launch.get("executable_sha256") == lab.LOCAL_SHA256
            and launch.get("save_sha256", "").lower() == spec["sha256"]
            and Path(launch.get("save", "")).name == spec["filename"] and launch.get("loaded_save_verified") is False,
            "Launch evidence does not select the pinned preserved save")
    if launch.get("purpose") == "disposable_save_cold_reload_read_only":
        require(type(launch.get("schema_version")) is int and launch["schema_version"] == 1
                and launch.get("previous_eu4_process_absent") is True and launch.get("native_injected") is False
                and launch.get("creation") == reload["creation"]
                and type(launch.get("process_creation_filetime")) is int
                and launch["process_creation_filetime"] == int(reload["creation"], 16),
                "Cold-launch complete process identity or no-injection premise differs")
    else:
        require(launch.get("purpose") == "disposable_1375_test_restart" and launch.get("plan_only") is False,
                "Unsupported launch contract")


def timestamp_filetime(value):
    time = datetime.fromisoformat(value)
    require(time.tzinfo is not None, "Capture time lacks timezone")
    delta = time.astimezone(timezone.utc) - datetime(1601, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10000000 + delta.microseconds * 10


def validate_reload_identity(document, stopped, observed, reload):
    """Bind separate held identity and clean exit; no pause/epoch inference."""
    pid, created = reload["pid"], int(reload["creation"], 16)
    require(type(stopped.get("pid")) is int and stopped["pid"] == pid and stopped.get("creation") == reload["creation"]
            and type(stopped.get("process_creation_filetime")) is int and stopped["process_creation_filetime"] == created
            and stopped.get("kind") == "exact_process_exit_observation" and stopped.get("read_only") is True
            and stopped.get("method") == "held_handle_wait_and_getprocesstimes" and stopped.get("exit_observed") is True
            and exact_int(stopped.get("process_exit_filetime"), created + 1, 2**64 - 1)
            and all(type(stopped.get(k)) is int and stopped[k] == 0 for k in ("before_exit_filetime", "wait_status", "exit_code"))
            and stopped.get("executable_sha256") == lab.LOCAL_SHA256
            and stopped.get("access") == "QUERY_LIMITED_INFORMATION | SYNCHRONIZE"
            and stopped.get("process_stop_requested_by_observer") is False, "Reload held-exit identity/normal completion differs")
    sample, _, observation_times = observer.validated_report(observed)
    source, state = document["source"], document["state"]
    require(type(document.get("schema_version")) is int and document["schema_version"] == 1 and document.get("read_only") is True
            and document["build"].get("sha256") == lab.LOCAL_SHA256
            and document["offset_profile"] == {"database_pointer_rva": "0x233d8d0", "game_pointer_rva": "0x233fe78"}
            and source.get("kind") == "live_process" and type(source.get("pid")) is int and source["pid"] == pid
            and type(source.get("process_creation_filetime")) is int and source["process_creation_filetime"] == created
            and type(source.get("process_exit_filetime")) is int and source["process_exit_filetime"] == 0
            and source.get("access") == ["PROCESS_QUERY_INFORMATION", "PROCESS_VM_READ"]
            and source.get("held_identity_verified_before_and_after") is True
            and source.get("module_base") == observed["source"]["module_base"], "Reload identity report scope differs")
    require(state.get("status") == "bounded_snapshot" and state.get("game_pointer") == sample["game"] == reload["world"]
            and state.get("database_pointer") == sample["database"] and state.get("country_array") == sample["country_array"]
            and type(state.get("current_raw_date")) is int and state["current_raw_date"] == sample["current_raw_date"] == reload["raw_date"]
            and state.get("player") == sample["player"]
            and state.get("snapshot_consistency") == {"globals_unchanged": True, "player_unchanged": True, "date_unchanged": True, "atomic": False},
            "Reload separate identity/sample roots, player or date differ")
    countries = state["countries"]
    require(type(countries) is list and len(countries) <= 4096, "Identity country budget exceeded")
    for tag in ("FRA", observed["target"]):
        require([c for c in countries if c.get("tag") == tag] == [sample["pair"][tag]], "Reload selected full country identity differs")
    identities = document["identity_before_and_after"]
    require(type(identities) is list and len(identities) == 2 and identities[0] == identities[1], "Reload held identity changed")
    expected = {"pid": pid, "creation": reload["creation"], "world_cookie": reload["world"],
                "player_handle": identities[0].get("player_handle"), "raw_date": reload["raw_date"]}
    require(canonical(identities[0]) == canonical(expected) and int(expected["player_handle"], 16) == observer.HANDLES["FRA"],
            "Reload held identity differs from selected observer")
    start, end = [timestamp_filetime(document[k]) for k in ("capture_started_at_utc", "captured_at_utc")]
    require(created <= start <= end < stopped["process_exit_filetime"]
            and all(created <= timestamp_filetime(t.isoformat()) < stopped["process_exit_filetime"] for t in observation_times),
            "Capture lies outside the exact held process lifetime")


def validate_persistence(spec, case, row, after, inputs, save_root):
    require(save_root is not None, "Persistence review needs explicit --save-root")
    require(set(spec) == {"filename", "size_bytes", "sha256", "report", "pre_save", "saved_date", "start_date", "reload"}, "Persistence descriptor differs")
    filename = spec["filename"]
    require(isinstance(filename, str) and re.fullmatch(r"llm_diplomacy_1375_v12_[A-Za-z0-9_]+\.eu4", filename), "Not a preserved v12 test-save filename")
    path = relative_path(Path(save_root), filename)
    stream_save_hash(path, spec["size_bytes"], spec["sha256"])
    saved = inputs.doc(spec["report"])
    validate_save_copy(saved, spec)
    recomputed = inspect_save(path, actor="FRA", targets=tuple(saved["targets"]))
    def normalized(value):
        value = json.loads(json.dumps(value))
        value.pop("captured_at_utc", None)
        value.pop("copy_evidence", None)
        value["source"].pop("path", None)
        return value
    require(normalized(saved) == normalized(recomputed), "Stored save extraction cannot be reproduced")
    require(saved["source"]["sha256"].lower() == spec["sha256"] and saved["source"]["size_bytes"] == spec["size_bytes"]
            and saved["metadata"]["date"]["value"] == spec["saved_date"] and saved["metadata"]["player"]["value"] == "FRA", "Saved identity/date differs")
    family = EFFECTS[row["request"]["action"]][0]
    target = row["request"]["target"]
    pre_save = inputs.doc(spec["pre_save"])
    sample, state, times = observer.validated_report(pre_save)
    _, after_state, after_times = observer.validated_report(after)
    identity({"pid": pre_save["source"]["pid"], "creation": f'{pre_save["source"]["process_creation_filetime"]:016x}'})
    require(sample["game"] == WORLD and pre_save["action"] == family and pre_save["target"] == target
            and after_times[1] <= times[0] and semantic_state(state) == semantic_state(after_state), "Pre-save selected state differs from effect after-state")
    validate_saved_relation(saved, family, target, state["state"], spec["start_date"])
    result = {"saved_state_consistent": True, "save_sha256": spec["sha256"], "saved_date": spec["saved_date"],
              "saved_reload_state_consistent": False, "exact_loaded_file_path_verified": False}
    if spec["reload"] is not None:
        reload = spec["reload"]
        require(set(reload) == {"snapshot", "launch", "identity", "exit", "pid", "creation", "world", "raw_date"}, "Reload descriptor differs")
        observed = inputs.doc(reload["snapshot"])
        new, new_state, new_times = observer.validated_report(observed)
        source = observed["source"]
        require(exact_int(reload["pid"], 1) and reload["pid"] != PID and isinstance(reload["creation"], str)
                and re.fullmatch(r"[0-9a-f]{16}", reload["creation"]) and int(reload["creation"], 16) > int(CREATION, 16)
                and source["pid"] == reload["pid"] and source["process_creation_filetime"] == int(reload["creation"], 16)
                and new["game"] == reload["world"] and new["current_raw_date"] == reload["raw_date"]
                and observed["action"] == family and observed["target"] == target
                and times[1] < new_times[0] and semantic_state(new_state) == semantic_state(state), "Reload selected state/independent identity differs")
        launch = inputs.doc(reload["launch"])
        validate_launch(launch, spec, reload)
        validate_reload_identity(inputs.doc(reload["identity"]), inputs.doc(reload["exit"]), observed, reload)
        result.update(saved_reload_state_consistent=True, reload_pid=reload["pid"], reload_creation=reload["creation"])
    return result


def review(manifest, *, root=ROOT, save_root=None):
    require(type(manifest) is dict and manifest.get("schema_version") == 1 and type(manifest["schema_version"]) is int
            and manifest.get("purpose") == "v12_finalized_experiment_case_manifest" and manifest.get("finalized") is True,
            "Not a finalized v12 case manifest; live/incomplete logs are not reviewable")
    require(set(manifest) == {"schema_version", "purpose", "finalized", "inputs", "exit", "preflight", "session_files", "final_status", "requests", "cases"}, "Unexpected manifest fields")
    inputs = Inputs(root, manifest["inputs"])
    exit_proof = validate_exit(inputs.doc(manifest["exit"]))
    build, build_sha = lab.verify_build(root=root, output=Path(root)/"work/runtime/native1375-v12")
    require(build_sha == MANIFEST_SHA and build["dll_sha256"] == DLL_SHA, "Different frozen v12 build")
    preflight = inputs.doc(manifest["preflight"])
    require(inputs.entries[manifest["preflight"]]["sha256"] == PREFLIGHT_SHA, "Different fixed no-send preflight summary")
    # Recheck every summary input independently, including its immutable six-file mirror.
    indexed = {row["path"]: key for key, row in inputs.entries.items()}
    for name, digest in preflight["input_sha256"].items():
        name = name.replace("\\", "/")
        require(name in indexed and sha(inputs.raw(indexed[name])) == digest.lower(), "Preflight input missing/changed")
    prefix_dir = Path(root)/"work/runtime/native1375-v12/preflight-only-17676"
    for phase in lab.PHASES:
        proof = verify_phase(phase, prefix_dir/"research-1375.jsonl", PID,
            Path(root)/"work/runtime/native1375-v12/preflight-identity-before-17676.json",
            Path(root)/"work/runtime/native1375-v12/preflight-identity-after-17676.json",
            Path(root)/"work/runtime/native1375-v12/build.json")
        review_path = preflight["phases"][phase]["review"].replace("\\", "/")
        require(proof == inputs.doc(indexed[review_path]), "Preflight detailed replay differs")
    files = manifest["session_files"]
    require(type(files) is dict and 6 <= len(files) <= MAX_ARTIFACTS
            and all(re.fullmatch(r"(?:session\.json|install\.claim|research-1375\.jsonl|phase-(?:lifecycle|preview|command)\.claim(?:\.host-intent)?|[0-9]{20}\.(?:host-intent|http-intent|claim|fixture-profile|lease-pause\.claim|supervisor\.jsonl|publisher-output\.txt))", name) for name in files), "Invalid session artifact inventory")
    session_rel = f"work/runtime/native1375-v12/session-{PID}-{CREATION}"
    for name, key in files.items():
        require(key in inputs.entries and inputs.entries[key]["path"] == session_rel + "/" + name, "Session file rebound to another location")
    session_path = relative_path(root, session_rel)
    actual_files = set()
    for entry in session_path.iterdir():
        require(entry.is_file() and len(actual_files) < MAX_ARTIFACTS, "Unexpected session directory or file budget")
        actual_files.add(entry.name)
    require(actual_files == set(files), "Final session inventory hides files, pending requests, or later claims")
    require(type(manifest["requests"]) is list and 1 <= len(manifest["requests"]) <= 128, "Request inventory budget failed")
    require([r.get("sequence") for r in manifest["requests"]] == list(range(1, len(manifest["requests"]) + 1))
            and all(type(r["sequence"]) is int for r in manifest["requests"]), "Request inventory must contain every sequence exactly once")
    statuses = []
    final_status = inputs.selected(manifest["final_status"])
    validate_status(final_status)
    statuses.append(final_status)
    with tempfile.TemporaryDirectory(prefix="eu4-v12-offline-review-") as temporary:
        mirror = Path(temporary)
        for name, key in files.items():
            (mirror/name).write_bytes(inputs.raw(key))
        metadata = lab.read_session_metadata(mirror, PID, CREATION)
        require(metadata["window_thread"] == THREAD, "Wrong game thread")
        evidence = lab.read_evidence(mirror, metadata)
        rows = evidence["requests"]
        require(set(rows) == set(range(1, len(manifest["requests"]) + 1)) and all(evidence["phases"].values())
                and all(evidence[k] is False for k in ("pending", "lease_pending", "input_wait_pending")), "Session incomplete/unknown or inventory incomplete")
        # The last CLI status normally predates clean UI exit by a few frames.
        # Its exact prefix is verified below; final state comes from the stopped log.
        require(final_status["last_sequence"] == evidence["last_sequence"]
                and all(final_status[k] is False for k in ("pending", "lease_pending")), "Final status has not completed the final request")
        frame = evidence["latest_frame"]
        require(frame["world_cookie"] == WORLD and frame["paused"] is True and frame["lease_active"] is False
                and frame["session_frozen"] is False and frame["world_changed"] is False and frame["thread_changed"] is False,
                "Final world is not healthy and paused")
        required_files = {"session.json", "install.claim", "research-1375.jsonl", *[p[1] for p in lab.PHASES.values()],
                          *[p[1]+".host-intent" for p in lab.PHASES.values()]}
        for _, claim, wire in lab.PHASES.values():
            validate_host(inputs.doc(files[claim+".host-intent"]), wire)
        inventory = []
        for item in manifest["requests"]:
            require(set(item) == {"sequence", "request", "outcome", "publication", "status"}, "Unexpected request inventory fields")
            seq, row = item["sequence"], rows[item["sequence"]]
            expected = {k: row["request"][k] for k in ("operation", "mode", "action", "actor", "target", "speed")}
            require(canonical(item["request"]) == canonical(expected), "Explicit request inventory differs from native log")
            prefix = f"{seq:020}"
            for suffix in ("host-intent", "claim"):
                required_files.add(prefix+"."+suffix)
            host = inputs.doc(files[prefix+".host-intent"])
            validate_host(host, inputs.raw(files[prefix+".claim"]), row)
            if expected["operation"] == "pair":
                validate_pair(row, item["outcome"])
            elif expected["operation"] == "fixture":
                require(item["outcome"] == "fixture_callback_returned", "Fixture is not a diplomatic effect")
                required_files.add(prefix+".fixture-profile")
            else:
                require(item["outcome"] == "completed_and_paused" and expected["speed"] > 0, "Unsupported speed outcome")
                required_files.update({prefix+".lease-pause.claim", prefix+".supervisor.jsonl", prefix+".publisher-output.txt"})
                events = [decode_json(line) for line in inputs.raw(files[prefix+".supervisor.jsonl"]).decode("utf-8").splitlines()]
                validate_supervisor(events, row)
                publisher = inputs.doc(files[prefix+".publisher-output.txt"])
                validate_status(publisher)
                validate_publication(publisher["publication"], host, seq)
                statuses.append(publisher)
            publication = item["publication"]
            require(set(publication) == {"kind", "evidence"} and publication["kind"] in ("cli", "http", "supervised_speed"), "Publication descriptor differs")
            if publication["kind"] == "cli":
                validate_publication(inputs.selected(publication["evidence"]), host, seq)
            elif publication["kind"] == "http":
                require(expected["operation"] == "pair", "HTTP only supports pairs")
                required_files.add(prefix+".http-intent")
                statuses.append(validate_http(inputs.selected(publication["evidence"]), row, inputs.doc(files[prefix+".http-intent"]), host))
            else:
                require(expected["operation"] == "speed", "Speed receipt cannot prove a pair submit")
                receipt = inputs.selected(publication["evidence"])
                require(receipt.get("status") == "completed_and_paused" and receipt.get("before_date") == events[0]["before"]["raw_date"]
                        and receipt.get("after_date") == events[1]["after"]["raw_date"], "Speed receipt differs from durable supervision")
            if item["status"] is not None:
                status = inputs.selected(item["status"])
                validate_status(status, row)
                statuses.append(status)
            else:
                require(expected["operation"] == "speed" or publication["kind"] == "http", "Missing independent per-request status")
            core = row["records"][-1]
            inventory.append({"sequence": seq, **expected, "outcome": item["outcome"], "request_sha256": host["request_sha256"],
                              "native_status": core.get("status"), "native_reason": core.get("reason"),
                              "native_preview_called": core.get("preview_called", False),
                              "native_command_gate_called": core.get("gate_called", False)})
        require(set(files) == required_files, "Unexpected/missing session artifacts; cannot hide pending claims/intents")
        wanted = {status["log_sha256"] for status in statuses}
        matched, digest, size, last_frame = {}, hashlib.sha256(), 0, None
        with (mirror/"research-1375.jsonl").open("rb") as stream:
            while line := stream.readline(lab.MAX_LINE + 1):
                require(len(line) <= lab.MAX_LINE and line.endswith(b"\n"), "Invalid log framing")
                size += len(line); digest.update(line)
                event = decode_json(line.decode("utf-8"))
                if event.get("event") == "research_frame":
                    last_frame = event
                if size == PREFIX_BYTES:
                    require(digest.hexdigest() == PREFIX_SHA, "No-send prefix differs from complete log")
                    matched["preflight"] = size
                if digest.hexdigest() in wanted:
                    for status in statuses:
                        if status["log_sha256"] == digest.hexdigest():
                            require(status["latest_frame"] == last_frame, "Status frame does not belong to its exact prefix")
                    matched[digest.hexdigest()] = size
        require(set(matched) == wanted | {"preflight"}, "Missing stopped-log status/preflight prefixes")
    require(type(manifest["cases"]) is list and len(manifest["cases"]) <= 128, "Effect case budget failed")
    effects, seen = [], set()
    for case in manifest["cases"]:
        require(set(case) == {"sequence", "before", "after", "comparison", "expected", "persistence"}
                and exact_int(case["sequence"], 1) and case["sequence"] in rows and case["sequence"] not in seen, "Invalid/duplicate effect case")
        seq = case["sequence"]; seen.add(seq)
        row = rows[seq]
        validate_pair(row, "dispatched")
        before, after, comparison = [inputs.doc(case[k]) for k in ("before", "after", "comparison")]
        observed = validate_effect(case, row, before, after, comparison,
            {k+"_sha256": inputs.entries[case[k]]["sha256"] for k in ("before", "after")})
        persistence = None if case["persistence"] is None else validate_persistence(case["persistence"], case, row, after, inputs, save_root)
        effects.append({"sequence": seq, "action": row["request"]["action"], "target": row["request"]["target"],
                        "observed_effect": True, "transition": observed["transition"], "persistence": persistence,
                        "request_causality_verified": False, "ai_acceptance_verified": False})
    require(inputs.used == set(inputs.entries), "Unreferenced evidence is not silently accepted")
    return {"schema_version": 1, "purpose": "v12_finalized_experiment_evidence_review", "read_only": True,
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(), "review_status": "reviewed_stopped_session",
            "pid": PID, "creation": CREATION, "dll_sha256": DLL_SHA, "manifest_sha256": MANIFEST_SHA,
            "fixture_profile_sha256": lab.FIXTURE_PROFILE_SHA256, "exact_process_exit_observation": exit_proof,
            "complete_log": inputs.entries[files["research-1375.jsonl"]], "final_paused_raw_date": frame["raw_date"],
            "historical_no_send_preflight_passed": True, "phase_case_counts": {"lifecycle": 20, "preview": 72, "command": 72},
            "requests": inventory, "pair_submits": sum(r["operation"] == "pair" and r["mode"] == "submit" for r in inventory),
            "selected_effects": effects, "selected_effect_count": len(effects),
            "production_backend_registered": False, "production_execution_verified": False,
            "strict_live_single_player_verified": False, "world_generation_verified": False,
            "request_id_causality_verified": False, "whole_world_unchanged_verified": False, "exact_loaded_file_path_verified": False,
            "manifest_content_sha256": sha(canonical(manifest).encode("utf-8")), "input_artifacts": inputs.entries,
            "reviewer_sha256": sha(Path(__file__).read_bytes()),
            "limitations": ["Whole-file pins attest these supplied records, not authenticated provenance or atomic engine snapshots.",
                "Save/reload checks, when present, cover only selected serialized relations and full country handles.",
                "Native return and consumed ownership do not prove AI acceptance, request-ID causality, strict SP origin or world epoch."]}


def without_review_time(value):
    return {k: v for k, v in value.items() if k != "reviewed_at_utc"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    result = review(decode_json(bounded(args.manifest, MAX_MANIFEST).decode("utf-8")), save_root=args.save_root)
    if args.check:
        require(without_review_time(decode_json(bounded(args.output).decode("utf-8"))) == without_review_time(result), "Stored review differs from recomputation")
    else:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps({"output": str(args.output), "checked": args.check, "review_status": result["review_status"],
                      "pair_submits": result["pair_submits"], "selected_effect_count": result["selected_effect_count"]}))


if __name__ == "__main__":
    main()
