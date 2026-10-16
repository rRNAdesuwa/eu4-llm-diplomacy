"""New read-only composition of frozen R1 effects, R2 replies and sharing pairs.

Preparation writes only a local observation baseline. It cannot reserve, load,
publish, retry, execute a native function, write memory, save or reload a game.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import time

from bridge.diplomacy_effect_observer import (RuntimeCapture, BudgetReader,
    HeldRPMPort, roots, full_handle, ptr, pins as observer_pins)
from bridge.diplomacy_effect_profiles import profile_catalog
from bridge.diplomacy_reply_observer import (ReplyAwareEffectObserver,
    reply_source_pins)
from bridge.knowledge_effect_reader_v2 import (ACTIONS as KNOWLEDGE_ACTIONS,
    read_knowledge_pair, evaluate_knowledge_effect, verify_manifest as knowledge_source_pins)
from bridge.tag_command_backend import (ROOT, DEFAULT_MANIFEST, GAME_SHA,
    decode, digest, read, require, validate_command)
from bridge.tag_command_audit import recorded_snapshot

SOURCE_MANIFEST = ROOT / "bridge/diplomacy_live_observer_manifest_1375.json"
ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError, struct.error)


def live_source_pins():
    """Verify the new graph and all frozen dependency graphs without a process."""
    raw = read(SOURCE_MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest["schema"] == "EU4DIPLOMACY-LIVE-OBSERVER-MANIFEST/1"
        and manifest["game_sha256"] == GAME_SHA
        and manifest["native_manifest_sha256"] == digest(read(DEFAULT_MANIFEST, 1024*1024)),
        "Live observer/native manifest identity differs")
    result = {}
    for name, expected in manifest["source_pins"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Invalid live source path")
        data = read(ROOT/name, 4*1024*1024)
        actual = {"bytes": len(data), "sha256": digest(data)}
        require(actual == expected, "Live source changed: " + name)
        result[name] = actual
    require({"bridge/diplomacy_live_observer.py", "tools/observe_diplomacy_live.py",
        "bridge/tests/test_diplomacy_live_observer.py",
        "bridge/diplomacy_reply_observer_manifest_1375.json",
        "bridge/knowledge_effect_reader_v2_manifest_1375.json"} <= set(result), "Live graph incomplete")
    observer_pins()
    reply_source_pins()
    knowledge_source_pins()
    result[SOURCE_MANIFEST.relative_to(ROOT).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


def live_catalog():
    pins = live_source_pins()
    rows = deepcopy(profile_catalog())
    for row in rows:
        if row["action"] in KNOWLEDGE_ACTIONS:
            row["frozen_r1_diagnostic"] = {k: deepcopy(row[k]) for k in ("runtime_support", "limitations")}
            row.update(runtime_snapshot_kind="exact_typed_sharing_pair_two_pass",
                completion_stage="active_sharing_pair_observed",
                required_fields=["prepared_absent_exact_pair", "complete_original_dispatch_receipt",
                    "both_directional_indexes", "live_provider_global_bucket", "typed_object_full_endpoints",
                    "removed_byte_28=0", "insertion_failed_byte_29=0", "raw_flag_40=0", "deadline_raw>now_raw"],
                core_support="New LiveDiplomacyObserver; R1 count diagnostic remains supplementary",
                runtime_support=dict(pure_data_predicate=True, native_calls_required=False,
                    core_fields_sufficient_for_selected_effect=False,
                    live_observer_fields_sufficient_for_selected_effect=True,
                    knowledge_pair_effect_layout_resolved=True),
                limitations=["A new exact typed active pair requires a fresh absent baseline and complete dispatch receipt.",
                    "No institution identity is stored in the sharing task; active sharing does not prove adoption.",
                    "World epoch, exclusive external-request causality, AI acceptance and persistence remain unproved."])
            row["source_pins"].update({name: pin for name, pin in pins.items() if name in
                ("bridge/knowledge_effect_reader_v2.py", "bridge/knowledge_effect_reader_v2_manifest_1375.json")})
    return dict(schema="EU4DIPLOMACY-LIVE-CATALOG/1", profiles=rows,
        recipient_reply_profiles=["ask_for_march"], knowledge_pair_profiles=list(KNOWLEDGE_ACTIONS),
        read_only=True, native_calls=0, requests_published=0, saves_written=0,
        all120_effect_profiles_complete=False, source_pins=pins,
        knowledge_institution_completion_verified=False, exact_external_request_id_causality_verified=False,
        limitations=["Active sharing is an observed task, not completed institution adoption.",
            "Consistent external reads do not establish an atomic world epoch or exclusive causality.",
            "No automatic command retry; pending disappearance is not a denial."])


class KnowledgeRuntimeCapture(RuntimeCapture):
    """Use the existing held QUERY/VM_READ port; no new process access method."""
    def __init__(self, identity, backend=None, *, allow_tag_host=False):
        super().__init__(identity, backend)
        require(type(allow_tag_host) is bool, "Explicit tag-host option must be boolean")
        self.allow_tag_host = allow_tag_host

    def __enter__(self):
        self.live_initial_pins = live_source_pins()
        return super().__enter__()

    def capture_knowledge(self, command, binding=None):
        command = validate_command(command, self.backend.actions)
        require(command["action"] in KNOWLEDGE_ACTIONS, "Unsupported knowledge action")
        started = time.perf_counter()
        # The outer budget covers selected-TAG discovery, module headers and the
        # complete inner two-pass decoder; its own cap is not added to this cap.
        r = BudgetReader(HeldRPMPort(self.held))
        canonical = self.held.injector._canonical
        research = [(b, p) for b, p in self.modules if Path(p).name.lower().startswith(
            ("eu4_bridge_", "eu4_pair_", "eu4_spy_", "eu4_tag_command_", "tag_diplomacy"))]
        expected = self.backend.build / self.backend.manifest["DLL"]
        require(not research or (self.allow_tag_host and len(research) == 1
            and canonical(research[0][1]) == canonical(expected)), "Unexpected research module")
        if research:
            header = self.runtime.readonly.pe_header(r.read(ptr(research[0][0]), 8192))
            require(header["machine"] == 0x8664 and header["timestamp"] == self.backend.manifest["PE_timestamp"]
                and header["size_of_image"] == self.backend.manifest["SizeOfImage"], "Loaded build7 header changed")
        root = roots(r, self.base)
        if binding is not None:
            handles = (binding["actor_handle"], binding["target_handle"])
            for handle, tag in zip(handles, (command["actor"], command["target"])):
                full_handle(handle, root["count"], tag=tag)
        else:
            raw = r.read(int(root["array"], 16), root["count"]*8)
            selected = {}
            for address, in struct.iter_unpack("<Q", raw):
                if not address:
                    continue
                handle = r.q(ptr(address)+0x20)
                raw_tag = (handle & 0xffffff).to_bytes(3, "little")
                for tag in (command["actor"], command["target"]):
                    if raw_tag == tag.encode("ascii"):
                        require(tag not in selected, "Duplicate selected TAG")
                        full_handle(handle, root["count"], tag=tag)
                        selected[tag] = handle
            require(set(selected) == {command["actor"], command["target"]}, "Selected TAG unavailable")
            handles = (selected[command["actor"]], selected[command["target"]])
        state = read_knowledge_pair(r, self.base, command["action"], *handles, self.identity)
        if state.get("two_pass_equal") is True:
            require(state["snapshot"]["roots"] == root and roots(r, self.base) == root,
                "Knowledge roots changed since selected-TAG discovery")
        self.held.identity_check()
        require(self.held.modules() == self.modules, "Module set changed during sharing capture")
        require(observer_pins() == self.initial_pins and live_source_pins() == self.live_initial_pins,
            "Live observer sources changed during capture")
        return dict(schema="EU4DIPLOMACY-KNOWLEDGE-CAPTURE/1", identity=self.identity, command=command,
            state=state, captured_utc=datetime.now(timezone.utc).isoformat(), game_sha256=GAME_SHA,
            duration_ms=round((time.perf_counter()-started)*1000, 3),
            rpm_budget=dict(calls=r.calls, bytes=r.bytes, largest_read=r.largest,
                limits=dict(calls=4096, bytes=512*1024, single_read=65536)),
            source_pins=self.live_initial_pins, research_modules=[str(p) for _, p in research],
            native_calls=0, memory_written=False, requests_published=0, saves_written=0,
            atomic_main_thread_snapshot=False, world_epoch_proven=False)


def checked_capture(capture, command, identity):
    require(capture["schema"] == "EU4DIPLOMACY-KNOWLEDGE-CAPTURE/1"
        and capture["identity"] == identity and capture["command"] == command
        and capture["game_sha256"] == GAME_SHA, "Knowledge capture identity/command differs")
    state = capture["state"]
    require(state["schema"] == "EU4DIPLOMACY-KNOWLEDGE-PAIR/2"
        and state["identity"] == identity and state["action"] == command["action"]
        and state["two_pass_equal"] is True and len(state["passes"]) == 2
        and state["passes"][0] == state["passes"][1] == state["snapshot"],
        "Knowledge capture is not two-pass consistent")
    s = state["snapshot"]
    require(s["typed_index_allocation_guards_verified"] is True, "Typed sharing index allocation guards unavailable")
    p = s["pair"]
    require((p["actor_tag"], p["target_tag"]) == (command["actor"], command["target"]),
        "Knowledge selected TAGs differ")
    for key, tag in (("actor_handle", command["actor"]), ("target_handle", command["target"])):
        full_handle(int(p[key], 16), tag=tag)
    provider, recipient = (p["target_handle"], p["actor_handle"]) if command["action"] == "ask_knowledge_sharing" else (p["actor_handle"], p["target_handle"])
    require((s["provider"]["handle"], s["recipient"]["handle"]) == (provider, recipient),
        "Knowledge provider/recipient direction differs")
    require(state["status"] == s["status"]
        and state["exact_pair_active_verified"] == s["exact_pair_active_verified"], "Knowledge state projection differs")
    return state


def write_journal(path, value):
    raw = json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False).encode("ascii")
    require(len(raw) <= 2*1024*1024, "Live journal bound")
    with path.open("xb") as stream:
        require(stream.write(raw) == len(raw), "Short local journal write")
    return {"path": str(path), "bytes": len(raw), "sha256": digest(raw)}


def unknown_effect(reason, exc=None):
    result = dict(schema="EU4DIPLOMACY-KNOWLEDGE-EFFECT/1", status="unknown", selected_effect_verified=False,
        reason=reason, automatic_command_retry=False, AI_acceptance_verified=False,
        exact_external_request_id_causality_verified=False, exclusive_causality_proven=False,
        world_epoch_proven=False, saved_state_verified=False, cold_reload_verified=False,
        institution_completion_verified=False)
    if exc is not None:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    return result


class LiveDiplomacyObserver(ReplyAwareEffectObserver):
    def __init__(self, identity, *, knowledge_capture_factory=KnowledgeRuntimeCapture, **kwargs):
        super().__init__(identity, **kwargs)
        self.knowledge_capture_factory = knowledge_capture_factory

    def prepare(self, command, *, legacy_probe=None):
        command = validate_command(command, self.backend.actions)
        if command["action"] not in KNOWLEDGE_ACTIONS:
            return super().prepare(command, legacy_probe=legacy_probe)
        require(legacy_probe is None, "Knowledge preparation requires a fresh live exact-pair capture")
        initial = live_source_pins()
        directory = self.directory(command["request_id"])
        path = directory / "knowledge-baseline.json"
        require(not path.exists(), "Knowledge baseline already exists; do not replace it")
        session = self.backend.session(self.identity)
        intent = self.backend.key_path(session, command["request_id"])
        lock = session / "publisher.lock"
        require(not intent.exists() and not lock.exists(), "Request already reserved or publisher locked")
        with self.knowledge_capture_factory(self.identity, self.backend, allow_tag_host=self.allow_tag_host) as reader:
            capture = reader.capture_knowledge(command)
        state = checked_capture(capture, command, self.identity)
        require(capture["source_pins"] == initial, "Knowledge preparation sources differ")
        require(state["status"] == "pair_absent_observed" and state["exact_pair_active_verified"] is False,
            "A proven absent exact pair is required before dispatch; current active/unknown state cannot be reused")
        require(not intent.exists() and not lock.exists(), "Publication started during capture; baseline timing unknown")
        require(live_source_pins() == initial, "Live sources changed during preparation")
        manifest_sha = initial[SOURCE_MANIFEST.relative_to(ROOT).as_posix()]["sha256"]
        value = dict(schema="EU4DIPLOMACY-KNOWLEDGE-BASELINE/1", identity=self.identity,
            command=command, capture=capture, source_manifest_sha256=manifest_sha,
            provenance=dict(kind="live_absent_exact_pair_before_publication",
                intent_path=str(intent), publisher_lock_path=str(lock),
                intent_absent_before=True, intent_absent_after=True,
                publisher_lock_absent_before=True, publisher_lock_absent_after=True,
                atomic_publication_lock_held=False, exclusive_causality_proven=False,
                world_epoch_proven=False), recorded_utc=datetime.now(timezone.utc).isoformat())
        directory.mkdir(parents=True, exist_ok=True)
        require(not intent.exists() and not lock.exists(), "Publication started before baseline journal write")
        record = write_journal(path, value)
        return dict(request_id=command["request_id"], baseline=record["path"], bytes=record["bytes"],
            sha256=record["sha256"], pair_status=state["status"], provider=state["snapshot"]["provider"],
            recipient=state["snapshot"]["recipient"], native_calls=0, requests_published=0,
            saves_written=0, memory_written=False, automatic_command_retry=False,
            source_manifest_sha256=manifest_sha)

    def observe(self, request_id, *, record=True):
        status = recorded_snapshot(self.backend.manifest_path, self.identity).status(request_id)
        command = status["command"]
        try:
            initial = live_source_pins()
        except ERRORS as exc:
            result = dict(schema="EU4DIPLOMACY-LIVE-OBSERVATION/1", request_id=request_id,
                identity=self.identity, command=command, transport_state=status["state"],
                audit_sha256=status["audit_sha256"], native_receipt=deepcopy(status), request_state="unknown",
                completion_state="evidence_insufficient", native_calls=0, requests_published=0,
                saves_written=0, memory_written=False, automatic_command_retry=False,
                AI_acceptance_verified=False, persistence_verified=False,
                effect=unknown_effect("Live source graph unavailable; recorded transport retained without capture", exc))
            if record:
                try:
                    directory = self.directory(request_id)
                    directory.mkdir(parents=True, exist_ok=True)
                    result["record"] = write_journal(directory / f"live-observation-{time.time_ns()}.json", result)["path"]
                except ERRORS as journal_exc:
                    result["record_failure"] = {"type": type(journal_exc).__name__, "message": str(journal_exc)}
            return result
        if command["action"] not in KNOWLEDGE_ACTIONS:
            return super().observe(request_id, record=record)
        # Keep the frozen diagnostic as its own fact. It cannot determine this
        # layer's selected sharing-object effect or turn a dispatch into success.
        try:
            result = super().observe(request_id, record=False)
        except ERRORS as exc:
            result = dict(request_id=request_id, identity=self.identity, command=command,
                transport_state=status["state"], audit_sha256=status["audit_sha256"],
                captured_utc=datetime.now(timezone.utc).isoformat(), request_state="unknown",
                native_calls=0, memory_written=False, requests_published=0, saves_written=0,
                automatic_command_retry=False, AI_acceptance_verified=False, persistence_verified=False,
                effect=unknown_effect("Frozen diagnostic unavailable; original recorded transport retained", exc))
        result["schema"] = "EU4DIPLOMACY-LIVE-OBSERVATION/1"
        result["supplement"] = {"r1_knowledge_effect": deepcopy(result["effect"])}
        result["native_receipt"] = deepcopy(status)
        result["effect"] = unknown_effect("No valid before-publication exact-pair baseline and current proof")
        result["completion_state"] = "evidence_insufficient"
        result["knowledge"] = dict(status="unknown", aggregate_counts_used_as_pair_proof=False,
            automatic_command_retry=False, institution_completion_verified=False)
        try:
            require(result["command"] == command and result["transport_state"] == status["state"]
                and result["audit_sha256"] == status["audit_sha256"], "Recorded status changed during frozen diagnostic")
            manifest_sha = initial[SOURCE_MANIFEST.relative_to(ROOT).as_posix()]["sha256"]
            result["source_manifest_sha256"] = manifest_sha
            require(status["state"] == "dispatched" and status["binding"] is not None,
                "No proven dispatched knowledge command; never retry from observation")
            path = self.directory(request_id) / "knowledge-baseline.json"
            raw = read(path, 2*1024*1024)
            before = decode(raw)
            require(before["schema"] == "EU4DIPLOMACY-KNOWLEDGE-BASELINE/1"
                and before["identity"] == self.identity and before["command"] == command
                and before["source_manifest_sha256"] == manifest_sha, "Knowledge baseline identity/source differs")
            provenance = before["provenance"]
            session = self.backend.session(self.identity)
            require(provenance["kind"] == "live_absent_exact_pair_before_publication"
                and provenance["intent_path"] == str(self.backend.key_path(session, request_id))
                and provenance["publisher_lock_path"] == str(session / "publisher.lock")
                and all(provenance[k] is True for k in ("intent_absent_before", "intent_absent_after",
                    "publisher_lock_absent_before", "publisher_lock_absent_after")), "Baseline publication timing unavailable")
            b = checked_capture(before["capture"], command, self.identity)
            require(before["capture"]["source_pins"] == initial
                and b["status"] == "pair_absent_observed" and b["exact_pair_active_verified"] is False,
                "Baseline was not an absent exact-pair observation with current sources")
            with self.knowledge_capture_factory(self.identity, self.backend, allow_tag_host=self.allow_tag_host) as reader:
                capture = reader.capture_knowledge(command, status["binding"])
            a = checked_capture(capture, command, self.identity)
            require(capture["source_pins"] == initial and live_source_pins() == initial, "Knowledge capture sources differ")
            require(recorded_snapshot(self.backend.manifest_path, self.identity).status(request_id) == status,
                "Recorded dispatch changed during knowledge observation")
            effect = evaluate_knowledge_effect(command["action"], b, a, status)
            effect["automatic_command_retry"] = False
            result["effect"] = effect
            result["baseline_sha256"] = digest(raw)
            result["knowledge"] = dict(status=a["status"], selected=a["snapshot"],
                two_pass_equal=a["two_pass_equal"], exact_pair_active_verified=a["exact_pair_active_verified"],
                duration_ms=capture["duration_ms"], rpm_budget=capture["rpm_budget"],
                source_manifest_sha256=manifest_sha, capture_record=None,
                aggregate_counts_used_as_pair_proof=False, institution_completion_verified=False,
                automatic_command_retry=False)
            if effect["selected_effect_verified"]:
                result["completion_state"] = "selected_effect_observed"
            if record:
                directory = self.directory(request_id)
                directory.mkdir(parents=True, exist_ok=True)
                result["knowledge"]["capture_record"] = write_journal(directory / f"knowledge-capture-{time.time_ns()}.json", capture)
        except ERRORS as exc:
            result["effect"] = unknown_effect("Knowledge baseline, source, receipt or current state is unavailable/unproven", exc)
            result["completion_state"] = "evidence_insufficient"
        if record:
            try:
                directory = self.directory(request_id)
                directory.mkdir(parents=True, exist_ok=True)
                result["record"] = write_journal(directory / f"live-observation-{time.time_ns()}.json", result)["path"]
            except ERRORS as exc:
                result["record_failure"] = {"type": type(exc).__name__, "message": str(exc)}
        return result


def make_live_server(observer, *, port=8775, token):
    """Reuse R1 auth, path checks, refusal methods and response-size bound."""
    from bridge.diplomacy_observer_service import make_server
    server = make_server(observer, port=port, token=token)
    original = server.RequestHandlerClass

    class Handler(original):
        def do_GET(self):
            if self.path != "/observer/v1/capabilities":
                return super().do_GET()
            if not self.authorized():
                return self.send_json(403, {"error": "unauthorized"})
            try:
                self.send_json(200, live_catalog())
            except ERRORS as exc:
                self.send_json(409, {"status": "unknown", "message": str(exc), "automatic_command_retry": False})

    server.RequestHandlerClass = Handler
    return server


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify new observer and frozen dependencies; no game access")
    parser.add_argument("--check", required=True, action="store_true")
    parser.parse_args()
    print(json.dumps({"schema": "EU4DIPLOMACY-LIVE-OBSERVER-CHECK/1", "source_pins": len(live_source_pins()),
        "native_calls": 0, "requests_published": 0, "game_process_accessed": False}))
