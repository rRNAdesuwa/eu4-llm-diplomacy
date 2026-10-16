"""Synthetic file transport only: no game reads, DLL calls or real mailbox writes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from bridge import native_pair_backend as pair
from bridge.diplomacy_api import DEFAULT_CATALOG, DiplomacyAPI, canonical


class SimulatedHostCrash(BaseException):
    pass


class NativePairBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "synthetic-mailbox"
        self.store = pair.initialize_mailbox(self.root)
        self.session_id, self.nonce = "1" * 32, "2" * 32
        self.now = 10000
        self.session = self.root / "sessions" / self.session_id
        self.session.mkdir()
        for name in ("inbox", "claimed", "effects"):
            (self.session / name).mkdir()
        self.request = {"request_id": "synthetic-001", "action": "improve_relations",
                        "parameters": {"actor": "FRA", "target": "ENG"}}
        self.build = {"sha256": pair.LOCAL_SHA256, "status": "static_analysis_only"}
        self.entry = dict(self.request["parameters"], action=self.request["action"],
                          verifier_id="synthetic_test_only", evidence_sha256="e" * 64)
        self.experiment = {"schema_version": 1, "protocol": pair.PROTOCOL, "purpose": "native_pair_mailbox_verified",
                           "game_sha256": pair.LOCAL_SHA256, "dll_sha256": "D" * 64,
                           "world_generation_method": "native_load_counter_v1", "world_generation_verified": True,
                           "actions": [dict(self.entry, dispatch_verified=True, effects_verified=True, reload_verified=True)]}
        self.experiment_hash = self.write_json(self.root / "experiment.json", self.experiment)
        self.whitelist = {"schema_version": 1, "protocol": pair.PROTOCOL, "game_sha256": pair.LOCAL_SHA256,
                          "dll_sha256": "D" * 64, "experiment_sha256": self.experiment_hash, "entries": [self.entry]}
        self.whitelist_hash = self.write_json(self.root / "whitelist.json", self.whitelist)
        self.base = {"store_id": self.store, "native_session_id": self.session_id, "host_nonce": self.nonce,
                     "pid": 1234, "process_creation_filetime": "0000000000000001", "world_generation": 3,
                     "game_sha256": pair.LOCAL_SHA256.lower(), "dll_sha256": "d" * 64,
                     "experiment_sha256": self.experiment_hash, "whitelist_sha256": self.whitelist_hash}
        self.health = dict(window_thread=456, frame_sequence=100, uptime_ms=self.now,
                           **{key: key != "thread_changed" for key in pair.BOOL_FIELDS})
        self.write_record("handshake.request", "handshake_request", dict(self.base, challenge_uptime_ms=9900))
        self.write_record("handshake.response", "handshake_response", dict(self.base, **self.health))
        self.write_record("heartbeat.record", "heartbeat", dict(self.base, **self.health))
        self.live = {key: self.base[key] for key in ("pid", "process_creation_filetime", "world_generation")}
        self.live.update(window_thread=456, game_sha256=pair.LOCAL_SHA256, dll_sha256="D" * 64,
                         process_identity_verified=True, loaded_dll_identity_verified=True,
                         world_generation_verified=True, single_player_verified=True, paused=True, observed_uptime_ms=self.now)
        self.backend = self.new_backend()
        self.events = []

    @staticmethod
    def write_json(path, value):
        raw = (canonical(value) + "\n").encode()
        path.write_bytes(raw)
        return pair.sha(raw)

    def write_record(self, name, operation, value):
        (self.session / name).write_bytes(pair.encode_record(operation, value))

    @staticmethod
    def verify_effect(request, binding, raw):
        value = json.loads(raw)
        if value.get("synthetic_test_only") is not True:
            return {}
        return {"binding": binding, "game_effects_verified": True, "verifier_id": "synthetic_test_only"}

    def new_backend(self):
        return pair.NativePairBackend(self.root, store_id=self.store, session_id=self.session_id, host_nonce=self.nonce,
                                      experiment_sha256=self.experiment_hash, whitelist_sha256=self.whitelist_hash,
                                      live_identity_probe=lambda: self.live, effect_verifier=self.verify_effect,
                                      clock=lambda: self.now)

    def capability(self, backend=None, parameters=None):
        return (backend or self.backend).capability({"action_id": self.request["action"]}, self.build,
                                                    self.request["parameters"] if parameters is None else parameters)

    def submit(self):
        receipt = self.backend.submit(self.request, self.build)
        self.wire = pair.decode_record((self.session / "inbox/1.request").read_bytes(), "submit")
        return receipt

    def append_event(self, name, data=None, *, wire=None):
        wire = wire or self.wire
        event = {key: wire[key] for key in pair.BASE + pair.MANIFEST_BINDING + ("sequence", "request_id", "request_sha256", "action", "actor", "target")}
        event.update(protocol=pair.PROTOCOL, event_sequence=len(self.events) + 1, uptime_ms=self.now,
                     utc="2026-10-08T00:00:00Z", event=name, data=data or {},
                     previous_event_sha256=self.events[-1]["event_sha256"] if self.events else "0" * 64)
        event["event_sha256"] = pair.sha(canonical(event).encode())
        self.events.append(event)
        self.flush_events()

    def flush_events(self):
        (self.session / "native-events.jsonl").write_text("".join(canonical(event) + "\n" for event in self.events), encoding="utf-8")

    def claim(self):
        (self.session / "inbox/1.request").rename(self.session / "claimed/1.request")
        self.append_event("received")
        self.append_event("claimed")

    def dispatch(self):
        self.claim()
        self.append_event("legality_result", {"allowed": True})
        self.append_event("dispatch_intent", {"ownership_known": True})
        self.append_event("dispatch_returned", {"returned": True, "container_consumed": True, "exception": 0, "ownership_known": True})

    def apply_effect(self):
        effect_hash = self.write_json(self.session / "effects/1.json", {"synthetic_test_only": True})
        self.append_event("effect_observed", {"effect_report_sha256": effect_hash})

    def make_api(self, *, production_catalog=False):
        catalog = DEFAULT_CATALOG
        if not production_catalog:
            catalog = Path(self.temp.name) / "synthetic-catalog.json"
            self.write_json(catalog, {"schema_version": 1, "actions": [{"action_id": "improve_relations", "parameter_status": "specified",
                "parameters": {"type": "object", "additionalProperties": False, "required": ["actor", "target"],
                               "properties": {key: {"type": "string", "const": value} for key, value in self.request["parameters"].items()}},
                "execution": {"status": "runtime_verified", "backend": self.backend.name, "supported_builds": [pair.LOCAL_SHA256]}}]})
        api = DiplomacyAPI(catalog, Path(self.temp.name) / "api.sqlite3", backend=self.backend, build_probe=lambda: self.build)
        self.addCleanup(api.close)
        return api

    def test_default_is_inert_and_requires_new_native_handshake(self):
        missing = Path(self.temp.name) / "never-created"
        backend = pair.NativePairBackend(missing)
        self.assertEqual(self.capability(backend)["reason_code"], "requires_new_native_handshake")
        self.assertFalse(missing.exists())
        self.assertTrue(self.capability()["ready"])

    def test_real_catalog_remains_unsupported_with_even_synthetic_ready_backend(self):
        api = self.make_api(production_catalog=True)
        result = api.submit(self.request)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(list((self.session / "inbox").iterdir()), [])

    def test_ready_requires_independent_live_identity_and_effect_verifiers(self):
        self.backend.live_identity_probe = None
        self.assertEqual(self.capability()["reason_code"], "requires_live_identity_verifier")
        self.backend.live_identity_probe = lambda: self.live
        self.backend.effect_verifier = None
        self.assertEqual(self.capability()["reason_code"], "requires_effect_verifier")

    def test_exact_experiment_and_tuple_gates(self):
        self.assertFalse(self.capability(parameters={"actor": "ENG", "target": "FRA"})["ready"])
        self.assertFalse(self.capability(parameters={"actor": "FRA", "target": "POR"})["ready"])
        self.backend.experiment_sha256 = None
        self.assertEqual(self.capability()["reason_code"], "empty_execution_whitelist")
        self.backend.experiment_sha256 = self.experiment_hash
        with (self.root / "experiment.json").open("ab") as stream:
            stream.write(b" ")
        self.assertEqual(self.capability()["reason_code"], "manifest_mismatch")

    def test_stale_heartbeat_reused_pid_world_or_dll_mismatch_refused(self):
        for key, value in (("process_creation_filetime", "0000000000000002"), ("world_generation", 4),
                           ("dll_sha256", "A" * 64), ("window_thread", 457), ("single_player_verified", False)):
            with self.subTest(key=key):
                old = self.live[key]
                self.live[key] = value
                self.assertEqual(self.capability()["reason_code"], "live_identity_mismatch")
                self.live[key] = old
        self.now += pair.FRESH_MS + 1
        self.assertEqual(self.capability()["reason_code"], "stale_handshake")

    def test_pause_required_in_both_native_handshake_and_heartbeat(self):
        for filename,kind in (("handshake.response","handshake_response"),("heartbeat.record","heartbeat")):
            with self.subTest(filename=filename):
                normal=dict(self.base,**self.health)
                self.write_record(filename,kind,dict(normal,paused=False))
                self.assertEqual(self.capability()["reason_code"],"world_not_paused")
                self.assertEqual(list((self.session/"inbox").iterdir()),[])
                # Earlier draft records have the wrong exact field set, even
                # if their remaining bytes and checksum were once valid.
                raw=pair.encode_record(kind,normal).replace(b"paused=true\n",b"")
                (self.session/filename).write_bytes(raw)
                self.assertFalse(self.capability()["ready"])
                for invalid in (1,"true",None):
                    with self.assertRaises(pair.MailboxError):
                        pair.encode_record(kind,dict(normal,paused=invalid))
                self.write_record(filename,kind,normal)
        self.assertTrue(self.capability()["ready"])

    def test_independent_pause_evidence_must_be_explicit_true(self):
        for paused in (False,1,"true",None):
            with self.subTest(paused=paused):
                self.live["paused"]=paused
                self.assertEqual(self.capability()["reason_code"],"live_identity_mismatch")
        self.live.pop("paused")
        self.assertEqual(self.capability()["reason_code"],"live_identity_mismatch")
        self.live["paused"]=True
        self.assertTrue(self.capability()["ready"])

    def test_pause_change_after_reservation_never_publishes_or_auto_retries(self):
        original=self.backend._preflight
        def observe(*args,**kwargs):
            if kwargs.get("check_pending") is False:
                self.live["paused"]=False
            return original(*args,**kwargs)
        with mock.patch.object(self.backend,"_preflight",side_effect=observe),self.assertRaises(pair.MailboxError):
            self.backend.submit(self.request,self.build)
        self.assertEqual(list((self.session/"inbox").iterdir()),[])
        self.live["paused"]=True
        with self.assertRaises(pair.MailboxError) as raised:
            self.backend.submit(self.request,self.build)
        self.assertEqual(raised.exception.code,"dispatch_unknown")
        self.assertEqual(list((self.session/"inbox").iterdir()),[])

    def test_readonly_status_survives_later_unpause_without_new_publication(self):
        receipt=self.submit();self.dispatch()
        self.live["paused"]=False
        self.write_record("heartbeat.record","heartbeat",dict(self.base,**dict(self.health,paused=False)))
        self.assertFalse(self.capability()["ready"])
        self.assertEqual(self.backend.status(self.request,receipt)["status"],"dispatched")
        self.assertEqual(list((self.session/"inbox").iterdir()),[])

    def test_checksum_duplicate_extra_fields_nonascii_and_crossline_rejected(self):
        receipt = self.submit()
        raw = (self.session / "inbox/1.request").read_bytes()
        self.assertEqual(pair.encode_record("submit", pair.decode_record(raw, "submit")), raw)
        variants = [raw[:-1], raw + b"\n", raw.replace(b"actor=FRA", b"actor=ENG"),
                    raw.replace(b"actor=FRA\n", b"actor=FRA\nactor=FRA\n"), raw.replace(b"actor=FRA\n", b"pointer=0x123\n"),
                    b"\xef\xbb\xbf" + raw, raw.replace(b"FRA", b"\xffRA"), raw.replace(b"\n", b"\r\n"),
                    raw.replace(b"sequence=1\n", b"sequence=01\n"), b"x" * (pair.MAX_RECORD + 1)]
        for variant in variants:
            with self.subTest(size=len(variant)), self.assertRaises(pair.MailboxError):
                pair.decode_record(variant, "submit")
        self.assertEqual(receipt["status"], "queued")

    def test_client_cannot_supply_pointer_rva_or_bad_action_shape(self):
        for changed in (dict(self.request, action=[]), dict(self.request, request_id="../x"),
                        dict(self.request, parameters={"actor": "FRA", "target": "ENG", "pointer": 123}),
                        dict(self.request, parameters={"actor": "FRA", "target": "FRA"})):
            with self.assertRaises(pair.MailboxError):
                self.backend.submit(changed, self.build)

    def test_publish_duplicate_after_restart_returns_original_no_new_file(self):
        receipt = self.submit()
        restarted = self.new_backend()
        self.assertEqual(restarted.submit(self.request, self.build), receipt)
        self.assertEqual([p.name for p in (self.session / "inbox").iterdir()], ["1.request"])
        with self.assertRaises(pair.MailboxError) as raised:
            restarted.submit(dict(self.request, parameters={"actor": "FRA", "target": "POR"}), self.build)
        self.assertEqual(raised.exception.code, "request_id_conflict")

    def test_atomic_publication_never_overwrites_or_consumes_temporary(self):
        final = self.session / "inbox/1.request"
        final.write_bytes(b"legacy-stale-file")
        with self.assertRaises(OSError):
            self.backend.submit(self.request, self.build)
        self.assertEqual(final.read_bytes(), b"legacy-stale-file")
        self.assertTrue(list(final.parent.glob("*.tmp")))
        with self.assertRaises(pair.MailboxError) as raised:
            self.new_backend().submit(self.request, self.build)
        self.assertEqual(raised.exception.code, "dispatch_unknown")

    def test_missing_or_changed_store_and_ledger_never_recreated(self):
        ledger = self.root / "ledger.sqlite3"
        ledger.rename(self.root / "old-ledger.sqlite3")
        self.assertEqual(self.capability()["reason_code"], "ledger_missing")
        self.assertFalse(ledger.exists())
        (self.root / "old-ledger.sqlite3").rename(ledger)
        self.write_json(self.root / "store.json", {"schema_version": 1, "store_id": "wrong"})
        self.assertEqual(self.capability()["reason_code"], "store_mismatch")
        with self.assertRaises(pair.MailboxError):
            pair.initialize_mailbox(self.root)

    def test_path_escape_and_hardlink_refused(self):
        with self.assertRaises(pair.MailboxError):
            pair._safe(self.root, "../outside")
        artifact = self.root / "hardlink-target"
        artifact.write_bytes(b"x")
        os.link(artifact, self.root / "second-link")
        with self.assertRaises(pair.MailboxError):
            pair.read_bounded(artifact, 100)

    def test_ack_cannot_direct_read_to_an_external_path(self):
        receipt = self.submit()
        self.claim()
        self.events[-1]["data"] = {"path": "C:/sensitive"}
        self.events[-1]["event_sha256"] = pair.sha(canonical({k: v for k, v in self.events[-1].items() if k != "event_sha256"}).encode())
        self.flush_events()
        state = self.backend.status(self.request, receipt)
        self.assertEqual(state["status"], "dispatch_unknown")
        self.assertIn("paths are never accepted", state["observation_error"])

    def test_readonly_status_claim_and_expiry_do_not_republish(self):
        receipt = self.submit()
        ledger_before = (self.root / "ledger.sqlite3").read_bytes()
        tree_before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "queued")
        self.assertEqual({str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, tree_before)
        self.claim()
        state = self.backend.status(self.request, receipt)
        self.assertEqual(state["status"], "dispatch_unknown")
        self.assertFalse(state["automatic_retry"])
        self.assertFalse(self.capability()["ready"])
        self.assertEqual((self.root / "ledger.sqlite3").read_bytes(), ledger_before)
        self.assertEqual(list((self.session / "inbox").iterdir()), [])

    def test_expired_unclaimed_request_is_unknown_not_failed(self):
        receipt = self.submit()
        self.now += 5001
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatch_unknown")

    def test_dispatched_requires_return_and_applied_independent_proof(self):
        receipt = self.submit()
        self.dispatch()
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatched")
        self.apply_effect()
        self.backend.effect_verifier = None
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatched")
        self.backend.effect_verifier = self.verify_effect
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "applied")

    def test_effect_report_same_identity_is_required(self):
        receipt = self.submit()
        self.dispatch()
        self.apply_effect()
        self.backend.effect_verifier = lambda r, b, raw: {"binding": dict(b, world_generation=999), "game_effects_verified": True, "verifier_id": "synthetic_test_only"}
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatch_unknown")

    def test_legality_rejection_cannot_be_followed_by_dispatch(self):
        receipt = self.submit()
        self.claim()
        self.append_event("legality_result", {"allowed": False})
        self.append_event("dispatch_intent", {"ownership_known": True})
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatch_unknown")

    def test_explicit_rejection_closes_request_and_allocates_next_sequence(self):
        receipt = self.submit()
        self.claim()
        self.append_event("rejected_before_dispatch", {"reason_code": "legality_failed", "dispatch_excluded": True, "ownership_known": True})
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "rejected")
        next_receipt = self.backend.submit(dict(self.request, request_id="synthetic-002"), self.build)
        self.assertEqual(next_receipt["binding"]["sequence"], 2)

    def test_ownership_exception_after_intent_is_unknown_not_safe_failure(self):
        receipt = self.submit()
        self.claim()
        self.append_event("legality_result", {"allowed": True})
        self.append_event("dispatch_intent", {"ownership_known": True})
        self.append_event("session_fault", {"reason_code": "seh", "dispatch_may_have_occurred": False, "ownership_known": True})
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatch_unknown")

    def test_corrupt_truncated_oversized_or_rebound_events_are_unknown(self):
        receipt = self.submit()
        self.dispatch()
        path = self.session / "native-events.jsonl"
        original = path.read_bytes()
        for raw in (original[:-1], original.replace(b'"pid":1234', b'"pid":1235'),
                    original.replace(b'"event_sequence":1', b'"event_sequence":2'),
                    b"x" * (pair.MAX_JOURNAL + 1)):
            path.write_bytes(raw)
            self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatch_unknown")

    def test_reconcile_recovers_publication_after_host_crash_without_writing(self):
        api = self.make_api()
        publish = pair.publish_exclusive
        def crash_after_publish(path, raw):
            publish(path, raw)
            raise SimulatedHostCrash()
        with mock.patch.object(pair, "publish_exclusive", side_effect=crash_after_publish):
            with self.assertRaises(SimulatedHostCrash):
                api.submit(self.request)
        self.assertEqual(api.status(self.request["request_id"])["status"], "dispatching")
        self.wire = pair.decode_record((self.session / "inbox/1.request").read_bytes(), "submit")
        self.dispatch()
        self.apply_effect()
        snapshot = {str(p): p.read_bytes() for p in self.session.rglob("*") if p.is_file()}
        recovered = api.reconcile(self.request["request_id"])
        self.assertEqual(recovered["status"], "applied", recovered)
        self.assertEqual({str(p): p.read_bytes() for p in self.session.rglob("*") if p.is_file()}, snapshot)
        with self.assertRaises(pair.MailboxError):
            self.new_backend().submit(self.request, self.build)

    def test_api_unknown_hold_survives_restart_and_blocks_new_id(self):
        api = self.make_api()
        self.assertEqual(api.submit(self.request)["status"], "queued")
        self.wire = pair.decode_record((self.session / "inbox/1.request").read_bytes(), "submit")
        self.claim()
        self.assertEqual(api.status(self.request["request_id"])["status"], "dispatch_unknown")
        api.close()
        restarted = self.make_api()
        result = restarted.submit(dict(self.request, request_id="cannot-bypass-hold"))
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("backend_execution_held", {b["code"] for b in result["result"]["blockers"]})

    def test_two_backends_racing_publish_at_most_one_file(self):
        backends = [self.new_backend(), self.new_backend()]
        def send(backend):
            try:
                return backend.submit(self.request, self.build)
            except pair.MailboxError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, backends))
        self.assertTrue(any(isinstance(result, dict) and result["status"] == "queued" for result in results), results)
        self.assertEqual([p.name for p in (self.session / "inbox").glob("*.request")], ["1.request"])
        with closing(sqlite3.connect(self.root / "ledger.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_duplicate_is_global_across_sessions_even_without_fresh_handshake(self):
        receipt = self.submit()
        backend = self.new_backend()
        backend.session_id = "f" * 32
        self.assertEqual(backend.submit(self.request, self.build), receipt)
        self.assertFalse((self.root / "sessions" / backend.session_id).exists())

    def test_crash_before_publication_preserves_reservation_and_never_retries(self):
        with mock.patch.object(pair, "publish_exclusive", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.backend.submit(self.request, self.build)
        with self.assertRaises(pair.MailboxError) as raised:
            self.new_backend().submit(self.request, self.build)
        self.assertEqual(raised.exception.code, "dispatch_unknown")
        row = self.backend._load_request(self.request)
        self.assertEqual(self.backend._observe(row)["status"], "dispatch_unknown")
        self.assertEqual(list((self.session / "inbox").iterdir()), [])

    def test_reconcile_rejects_another_api_dispatch_identity(self):
        self.submit()
        with self.assertRaises(pair.MailboxError):
            self.backend.reconcile(self.request, {"result": {"dispatch_context": {"identity": {}}}})

    def test_failed_native_return_preserves_unknown_ownership(self):
        receipt = self.submit()
        self.claim()
        self.append_event("legality_result", {"allowed": True})
        self.append_event("dispatch_intent", {"ownership_known": True})
        self.append_event("dispatch_returned", {"returned": False, "container_consumed": False, "exception": 0xc0000005, "ownership_known": False})
        state = self.backend.status(self.request, receipt)
        self.assertEqual(state["status"], "dispatch_unknown")
        self.assertEqual(state["uncertainty"], "ownership_unknown")
        self.assertFalse(self.capability()["ready"])

    def test_research_manifest_cannot_enable_ready(self):
        self.experiment["purpose"] = "research_single_send"
        self.backend.experiment_sha256 = self.write_json(self.root / "experiment.json", self.experiment)
        self.assertEqual(self.capability()["reason_code"], "requires_new_native_handshake")

    def test_malformed_manifest_is_a_capability_rejection(self):
        self.whitelist["entries"][0]["action"] = []
        self.backend.whitelist_sha256 = self.write_json(self.root / "whitelist.json", self.whitelist)
        self.assertFalse(self.capability()["ready"])

    def test_known_predispatch_failure_still_revokes_native_session(self):
        receipt = self.submit()
        self.claim()
        self.append_event("session_fault", {"reason_code": "world_lost", "dispatch_may_have_occurred": False, "ownership_known": True})
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "failed")
        self.assertEqual(self.capability()["reason_code"], "native_session_fault")

    def test_unsolicited_other_request_ack_revokes_capability(self):
        self.submit()
        other = dict(self.request, request_id="not-in-durable-ledger")
        wire = dict(self.wire, sequence=2, request_id=other["request_id"], request_sha256=pair.sha(canonical(other).encode()))
        self.append_event("received", wire=wire)
        self.assertFalse(self.capability()["ready"])
        self.assertIn("durable host intent", self.backend._observe(self.backend._load_request(self.request))["observation_error"])

    def test_all_handshake_and_session_gates_remain_required(self):
        for key in pair.BOOL_FIELDS:
            health = dict(self.health)
            health[key] = not health[key]
            self.write_record("heartbeat.record", "heartbeat", dict(self.base, **health))
            with self.subTest(key=key):
                self.assertEqual(self.capability()["reason_code"], "world_not_paused" if key == "paused" else "requires_new_native_handshake")
        self.write_record("heartbeat.record", "heartbeat", dict(self.base, **self.health))
        base = dict(self.base, host_nonce="3" * 32)
        self.write_record("heartbeat.record", "heartbeat", dict(base, **self.health))
        self.assertEqual(self.capability()["reason_code"], "handshake_mismatch")

    def test_verifier_errors_do_not_leave_ready_or_claim_applied(self):
        def broken(*args):
            raise RuntimeError("synthetic verifier failure")
        self.backend.live_identity_probe = broken
        self.assertFalse(self.capability()["ready"])
        self.backend.live_identity_probe = lambda: self.live
        receipt = self.submit()
        self.dispatch()
        self.apply_effect()
        self.backend.effect_verifier = broken
        self.assertEqual(self.backend.status(self.request, receipt)["status"], "dispatch_unknown")


if __name__ == "__main__":
    unittest.main()
