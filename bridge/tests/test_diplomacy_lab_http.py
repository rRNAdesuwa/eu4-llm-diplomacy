"""Offline research HTTP tests: synthetic files/streams, no sockets or game calls."""
from copy import deepcopy
from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bridge import diplomacy_lab_http as http
from bridge.diplomacy_api import canonical
from work.native import lab_protocol_v9_1375 as lab


class SyntheticRuntime:
    def __init__(self, session):
        self.pid, self.creation = 1234, "01da123456789abc"
        self.calls, self.inspections = 0, 0
        self.failure, self.inspect_failure = None, None
        self.entered, self.release = None, None
        self.snapshot = {"session": Path(session), "manifest_sha256": "a" * 64, "dll_sha256": "B" * 64,
            "metadata": {"pid": self.pid, "process_creation_filetime": self.creation},
            "fixture_disk_evidence": {"fixture_definition_files_verified": True, "engine_registration_verified": False},
            "live": {"pid": self.pid, "creation": self.creation, "world_cookie": "0x10000",
                     "player_handle": "0x0100007a00415246", "raw_date": 56456976},
            "now": 3000,
            "evidence": {"last_sequence": 0, "pending": False, "lease_pending": False, "requests": {},
                         "log_sha256": "c" * 64, "phases": {key: True for key in lab.PHASES},
                         "latest_frame": {"frames": 100, "uptime_ms": 3000, "world_ready": True,
                            "world_cookie": "0x10000", "player_handle": "0x0100007a00415246", "raw_date": 56456976,
                            "paused": True, "mailbox_ready": True, "running_speed_enabled": True,
                            **{key + "_passed": True for key in lab.PHASES}}}}

    def inspect(self):
        self.inspections += 1
        if self.inspect_failure:
            raise self.inspect_failure
        return deepcopy(self.snapshot)

    def publish(self, snapshot, request):
        self.calls += 1
        if self.entered:
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError("Synthetic test release was not signalled")
        if self.failure == "before":
            raise OSError("Synthetic failure before native host intent")
        result = lab.publish_research(snapshot["session"], snapshot["metadata"], snapshot["manifest_sha256"],
            snapshot["evidence"], snapshot["live"], sequence=request["sequence"], operation="pair",
            mode=request["mode"], action=request["action"], actor=request["actor"], target=request["target"],
            ttl_ms=request["ttl_ms"], clock=lambda: snapshot["now"])
        if self.failure == "after":
            raise OSError("Synthetic response loss after publication")
        return result

    def consume(self, sequence=1, *, complete=True, dispatched=False):
        path = self.snapshot["session"] / f"{sequence:020}.request"
        request = lab.decode_request(path.read_bytes())
        path.rename(path.with_suffix(".claim"))
        evidence = self.snapshot["evidence"]
        evidence["last_sequence"] = sequence
        evidence["pending"] = not complete
        evidence["requests"][sequence] = {"request": request, "records": [], "complete":
            {"submit_entered": dispatched, "submit_returned": dispatched, "applied_verified": False} if complete else None}


def fake_history(**_):
    return {"discovery_source": "synthetic_reviewed_history_only", "summary": {"catalogued_actions": 274,
            "static_mapped_actions": 270, "production_executable_actions": 0},
            "catalog_sha256": "d" * 64, "research_index_sha256": "e" * 64,
            "actions": [{"action_id": action, "static": {"mapped": True},
                "observed_effects": {"available": False}, "production": {"ready": False}} for action in lab.ACTIONS]}


class ResearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.session = Path(self.temporary.name)
        # These tests use only a synthetic mailbox and no real game directory.
        self.enterContext(patch.object(lab, "_private_root", lambda path: None))
        self.live = self.enterContext(patch.object(lab, "LiveLabProcess", side_effect=AssertionError("Test accessed a process")))
        self.runtime = SyntheticRuntime(self.session)
        self.service = http.ResearchService(self.runtime, capability_reader=fake_history)
        self.request = {"protocol": lab.PROTOCOL, "pid": self.runtime.pid, "creation": self.runtime.creation,
                        "sequence": 1, "mode": "legality_only", "action": "royal_marriage", "actor": "FRA",
                        "target": "NAV", "ttl_ms": 5000}

    def post(self, **updates):
        return self.service.dispatch("POST", http.PREFIX + "/pair", self.request | updates)

    def test_import_and_capabilities_do_not_access_process_or_enable_production(self):
        status, result = self.service.dispatch("GET", http.PREFIX + "/capabilities")
        self.assertEqual(status, 200)
        self.assertEqual(set(result["http_pair_contract"]["actions"]), set(lab.ACTIONS))
        self.assertEqual(len(result["http_pair_contract"]["actions"]), 10)
        self.assertEqual(result["summary"]["static_mapped_actions"], 270)
        self.assertFalse(result["production"])
        self.assertIsNone(result["live_readiness"])
        self.assertFalse(result["live_process_inspected"])
        self.assertEqual(self.runtime.inspections, 0)
        self.live.assert_not_called()

    def test_ten_actions_both_modes_compile_exact_wire_in_temporary_mailboxes(self):
        for action in lab.ACTIONS:
            for mode in ("legality_only", "submit"):
                with self.subTest(action=action, mode=mode), tempfile.TemporaryDirectory() as directory:
                    runtime = SyntheticRuntime(directory)
                    service = http.ResearchService(runtime, capability_reader=fake_history)
                    status, result = service.dispatch("POST", http.PREFIX + "/pair", self.request | {"action": action, "mode": mode})
                    self.assertEqual(status, 202, result)
                    raw = (Path(directory) / "00000000000000000001.request").read_bytes()
                    self.assertTrue(raw.startswith(b"EU4LAB/2\n"))
                    record = lab.decode_request(raw)
                    self.assertEqual((record["action"], record["mode"], record["operation"]), (action, mode, "pair"))
                    self.assertFalse(result["native_dispatch_verified"])
                    self.assertFalse(result["applied_verified"])

    def test_protocol_identity_and_request_escape_rejections_precede_runtime_access(self):
        invalid = [{"protocol": "EU4PAIR/1"}, {"protocol": "EU4LAB/1"}, {"pid": True}, {"pid": 99},
                   {"creation": "01da123456789abd"}, {"sequence": True}, {"ttl_ms": 0}, {"ttl_ms": 60001},
                   {"sequence": lab.MAX_SEQUENCE + 1}, {"action": "console"}, {"target": "RUS"},
                   {"target": "NAV\ncommand=evil"}, {"actor": "NAV", "mode": "submit"}, {"target": "FRA"},
                   {"mode": "preview"}, {"action": []}, {"target": None}]
        for fields in invalid:
            with self.subTest(fields=fields):
                status, _ = self.post(**fields)
                self.assertIn(status, (409, 422))
        for key in ("dll", "address", "rva", "script", "event", "path", "operation", "speed", "request_id"):
            status, _ = self.post(**{key: "anything"})
            self.assertEqual(status, 422)
        self.assertEqual(self.runtime.inspections, 0)
        self.assertEqual(list(self.session.iterdir()), [])

    def test_disallowed_routes_do_not_touch_runtime_or_bypass_speed_watchdog(self):
        for method, path in (("POST", "/v1/requests"), ("POST", http.PREFIX + "/speed"),
                             ("POST", http.PREFIX + "/fixture"), ("POST", http.PREFIX + "/stage"),
                             ("POST", http.PREFIX + "/reset"), ("GET", http.PREFIX + "/requests/01"),
                             ("POST", http.PREFIX + "/pair?x=1"), ("POST", http.PREFIX + "/%70air")):
            status, result = self.service.dispatch(method, path, self.request)
            self.assertIn(status, (400, 404))
            self.assertTrue(result["research_only"])
        self.assertEqual(self.runtime.inspections, 0)

    def test_duplicate_is_read_only_even_after_service_restart(self):
        self.assertEqual(self.post()[0], 202)
        raw = (self.session / "00000000000000000001.request").read_bytes()
        self.service = http.ResearchService(self.runtime, capability_reader=fake_history)
        status, result = self.post()
        self.assertEqual(status, 200)
        self.assertTrue(result["replayed"])
        self.assertFalse(result["request_written"])
        self.assertEqual(self.runtime.calls, 1)
        self.assertEqual((self.session / "00000000000000000001.request").read_bytes(), raw)

    def test_duplicate_conflict_including_changed_ttl_cannot_extend_deadline(self):
        self.assertEqual(self.post()[0], 202)
        for change in ({"ttl_ms": 6000}, {"target": "ENG"}, {"mode": "submit"}, {"action": "guarantee"}):
            with self.subTest(change=change):
                status, result = self.post(**change)
                self.assertEqual(status, 409)
                self.assertEqual(result["error"]["code"], "sequence_conflict")
        self.assertEqual(self.runtime.calls, 1)

    def test_unknown_before_publication_is_durable_hold_no_retry_or_next_sequence(self):
        self.runtime.failure = "before"
        status, result = self.post()
        self.assertEqual((status, result["error"]["code"]), (502, "publication_unknown"))
        self.assertTrue((self.session / "00000000000000000001.http-intent").exists())
        self.assertFalse(list(self.session.glob("*.request")))
        self.runtime.failure = None
        self.service = http.ResearchService(self.runtime, capability_reader=fake_history)
        self.assertEqual(self.post()[1]["state"], "publication_unknown")
        self.assertEqual(self.post(sequence=2)[1]["error"]["code"], "unresolved_sequence")
        status = self.service.status()
        self.assertFalse(status["pair_publication_ready"])
        self.assertEqual(status["mailbox_holds"], [{"sequence": 1, "state": "publication_unknown"}])
        self.assertEqual(self.runtime.calls, 1)

    def test_lost_response_after_publication_does_not_resend_and_completion_is_not_effect(self):
        self.runtime.failure = "after"
        self.assertEqual(self.post()[0], 502)
        self.runtime.consume(dispatched=True)
        status, result = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(result["state"], "native_completed")
        self.assertTrue(result["native_dispatch_verified"])
        self.assertFalse(result["applied_verified"])
        self.assertFalse(result["ai_acceptance_verified"])
        self.assertEqual(self.runtime.calls, 1)

    def test_claim_without_completion_blocks_next_sequence(self):
        self.post()
        self.runtime.consume(complete=False)
        result = self.service.status(1)
        self.assertEqual(result["state"], "native_dispatch_unknown")
        self.assertFalse(result["automatic_retry"])
        self.assertEqual(self.post(sequence=2)[0], 409)
        self.assertEqual(self.runtime.calls, 1)

    def test_queued_then_expired_or_disappeared_request_is_unknown(self):
        self.post()
        self.assertEqual(self.service.status(1)["state"], "queued")
        self.runtime.snapshot["now"] = 8000
        self.assertEqual(self.service.status(1)["state"], "publication_unknown")
        self.runtime.snapshot["now"] = 3000
        (self.session / "00000000000000000001.request").unlink()
        self.assertEqual(self.service.status(1)["state"], "publication_unknown")
        self.assertEqual(self.runtime.calls, 1)

    def test_explicit_sequence_only_and_next_allowed_after_native_completion(self):
        self.assertEqual(self.post(sequence=2)[0], 409)
        self.assertFalse(list(self.session.iterdir()))
        self.assertEqual(self.post()[0], 202)
        self.runtime.consume()
        self.assertTrue(self.service.status()["pair_publication_ready"])
        self.assertEqual(self.post(sequence=3)[0], 409)
        self.assertEqual(self.post(sequence=2)[0], 202)
        self.assertEqual(self.runtime.calls, 2)

    def test_completed_previous_request_does_not_override_latest_lease_or_pause_guard(self):
        self.assertEqual(self.post()[0], 202)
        self.runtime.consume()
        frame = self.runtime.snapshot["evidence"]["latest_frame"]
        frame["lease_active"] = True
        self.assertEqual(self.service.status(1)["state"], "native_completed")
        self.assertFalse(self.service.status()["pair_publication_ready"])
        self.assertEqual(self.post(sequence=2)[0], 409)
        frame["lease_active"] = False
        frame["paused"] = False
        self.assertEqual(self.post(sequence=2)[0], 409)
        self.assertFalse((self.session / "00000000000000000002.http-intent").exists())
        self.assertEqual(self.runtime.calls, 1)

    def test_all_readiness_guards_precede_intent_reservation(self):
        original = deepcopy(self.runtime.snapshot)
        changes = [lambda x: x["evidence"]["latest_frame"].update(paused=False),
                   lambda x: x["evidence"]["latest_frame"].update(paused=1),
                   lambda x: x["evidence"]["latest_frame"].update(uptime_ms=1),
                   lambda x: x["evidence"]["phases"].update(command=False),
                   lambda x: x["evidence"].update(lease_pending=True),
                   lambda x: x["evidence"].update(pending=True),
                   lambda x: x["live"].update(world_cookie="0x20000"),
                   lambda x: x["live"].update(raw_date=56456977)]
        for change in changes:
            self.runtime.snapshot = deepcopy(original)
            change(self.runtime.snapshot)
            self.assertEqual(self.post()[0], 409)
            self.assertFalse(list(self.session.iterdir()))
        self.assertEqual(self.runtime.calls, 0)

    def test_native_session_guard_failure_is_not_cached_status(self):
        self.assertEqual(self.service.dispatch("GET", http.PREFIX + "/status")[0], 200)
        self.runtime.inspect_failure = lab.LabError("Native lab session is frozen")
        status, result = self.service.dispatch("GET", http.PREFIX + "/status")
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "session_guard_failed")
        self.assertNotIn("latest_frame", result)
        self.assertEqual(self.post()[0], 409)

    def test_concurrent_requests_in_one_instance_never_double_publish(self):
        self.runtime.entered, self.runtime.release = threading.Event(), threading.Event()
        results = []
        worker = threading.Thread(target=lambda: results.append(self.post()))
        worker.start()
        try:
            self.assertTrue(self.runtime.entered.wait(2))
            self.assertEqual(self.post()[1]["error"]["code"], "service_busy")
            self.assertEqual(self.post(target="ENG")[1]["error"]["code"], "service_busy")
        finally:
            self.runtime.release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][0], 202)
        self.assertEqual(self.runtime.calls, 1)

    def test_independent_instances_cannot_replace_reserved_http_intent(self):
        second = http.ResearchService(self.runtime, capability_reader=fake_history)
        self.assertEqual(self.post()[0], 202)
        self.assertEqual(second.dispatch("POST", http.PREFIX + "/pair", self.request)[0], 200)
        self.assertEqual(second.dispatch("POST", http.PREFIX + "/pair", self.request | {"target": "ENG"})[0], 409)
        self.assertEqual(self.runtime.calls, 1)

    def test_actual_atomic_intent_race_cannot_invoke_second_publisher(self):
        competitor = http.ResearchService(self.runtime, capability_reader=fake_history)
        original = http.publish_exclusive
        def race(path, raw):
            original(path, raw)  # Another instance won exactly this reservation.
            return original(path, raw)  # The contender cannot replace it.
        with patch.object(http, "publish_exclusive", side_effect=race):
            status, result = competitor.dispatch("POST", http.PREFIX + "/pair", self.request)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "intent_reservation_failed")
        self.assertEqual(self.runtime.calls, 0)
        self.assertEqual(self.service.status(1)["state"], "publication_unknown")

    def test_foreign_native_reservation_is_never_overwritten(self):
        lab.publish_research(self.session, self.runtime.snapshot["metadata"], "a" * 64,
            self.runtime.snapshot["evidence"], self.runtime.snapshot["live"], sequence=1, operation="pair",
            action="guarantee", actor="FRA", target="ENG", clock=lambda: 3000)
        self.assertEqual(self.post()[1]["error"]["code"], "sequence_reserved")
        self.assertFalse(list(self.session.glob("*.http-intent")))
        self.assertEqual(self.service.status(1)["request"]["action"], "guarantee")
        self.assertFalse(self.service.status()["pair_publication_ready"])
        self.assertEqual(self.runtime.calls, 0)

    def test_unlogged_cli_marker_blocks_readiness_and_new_http_intent(self):
        (self.session / "pair-selftest.request").write_bytes(b"synthetic existing marker")
        result = self.service.status()
        self.assertFalse(result["pair_publication_ready"])
        self.assertEqual(result["mailbox_holds"], [{"sequence": None, "state": "mailbox_request_pending"}])
        self.assertEqual(self.post()[1]["error"]["code"], "unresolved_sequence")
        self.assertEqual(list(self.session.glob("*.http-intent")), [])

    def test_tampered_native_intent_or_claim_binding_fails_closed(self):
        self.post()
        path = self.session / "00000000000000000001.host-intent"
        original = path.read_bytes()
        for fields in ({"protocol": "EU4PAIR/1"}, {"purpose": "restricted_pair_lab_1375_v8"},
                       {"manifest_sha256": "f" * 64}, {"request_sha256": "0" * 64}):
            value = json.loads(original)
            value.update(fields)
            path.write_text(canonical(value), encoding="utf-8")
            status, _ = self.service.dispatch("GET", http.PREFIX + "/requests/1")
            self.assertEqual(status, 409)
        path.write_bytes(original)
        self.runtime.consume()
        self.runtime.snapshot["evidence"]["requests"][1]["request"]["target"] = "ENG"
        self.assertEqual(self.service.dispatch("GET", http.PREFIX + "/requests/1")[0], 409)

    def test_runtime_rechecks_manifest_session_installed_profile_and_held_process(self):
        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.snapshot.return_value = deepcopy(self.runtime.snapshot["live"])
        manifest = {"dll_sha256": "B" * 64, "running_speed_enabled": True}
        with patch.object(lab, "LiveLabProcess", return_value=process) as opened, \
             patch.object(lab, "verify_build", return_value=(manifest, "a" * 64)) as build, \
             patch.object(lab, "session_path", return_value=self.session), \
             patch.object(lab, "read_session_metadata", return_value=self.runtime.snapshot["metadata"]), \
             patch.object(lab, "read_evidence", return_value=self.runtime.snapshot["evidence"]), \
             patch.object(lab, "verify_installed_fixture", return_value={"disk_only": True}) as fixture, \
             patch.object(lab, "uptime_ms", return_value=3000), \
             patch.object(lab, "publish_research") as publish:
            runtime = http.V9ResearchRuntime(self.runtime.pid, self.runtime.creation)
            first = runtime.inspect()
            def fake_publish(*args, **kwargs):
                kwargs["recheck"]()
                return {"status": "published"}
            publish.side_effect = fake_publish
            runtime.publish(first, self.request)
            self.assertEqual(opened.call_count, 2)
            self.assertEqual(process.__exit__.call_count, 2)
            self.assertEqual(fixture.call_count, 3)
            self.assertEqual(build.call_count, 5)
            self.assertFalse(publish.call_args.kwargs.get("watchdog_verified", False))
            build.return_value = manifest, "b" * 64
            with self.assertRaises(http.ResearchError):
                runtime.inspect()
            self.assertEqual(opened.call_count, 2)

    def test_bad_installed_profile_stops_before_publisher(self):
        self.runtime.inspect_failure = lab.LabError("Installed fixture definition differs")
        self.assertEqual(self.post()[0], 409)
        self.assertEqual(self.runtime.calls, 0)
        self.assertFalse(list(self.session.iterdir()))

    def test_invalid_bind_token_or_startup_never_constructs_server(self):
        with patch.object(http, "BoundedResearchServer") as server:
            for config in ({"host": "0.0.0.0", "token": "a" * 32}, {"host": "localhost", "token": "a" * 32},
                           {"token": None}, {"token": "short"}, {"token": "x\n" * 32}, {"port": 0, "token": "a" * 32}):
                with self.assertRaises(http.ResearchError):
                    http.make_server(self.service, **config)
            self.runtime.inspect_failure = lab.LabError("Wrong version")
            with self.assertRaises(http.ResearchError):
                http.make_server(self.service, token="a" * 32)
            server.assert_not_called()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.base = http.BASE
        self.service.dispatch.return_value = 200, dict(http.BASE, ok=True)
        self.handler = object.__new__(http.handler_class(self.service, "a" * 32))
        self.handler.server = SimpleNamespace(server_port=8766)
        self.handler.connection = Mock()
        self.handler._send = Mock()
        self.handler.path = http.PREFIX + "/pair"
        self.headers = [("Host", "127.0.0.1:8766"), ("Authorization", "Bearer " + "a" * 32),
                        ("Content-Type", "application/json"), ("Content-Length", "2")]

    def run_request(self, headers=None, raw=b"{}"):
        self.handler.headers = Message()
        for name, value in self.headers if headers is None else headers:
            self.handler.headers[name] = value
        self.handler.rfile = io.BytesIO(raw)
        self.handler._dispatch("POST")
        return self.handler._send.call_args.args

    def test_authenticated_json_dispatch_is_pure_fake_transport(self):
        self.assertEqual(self.run_request()[0], 200)
        self.service.dispatch.assert_called_once_with("POST", http.PREFIX + "/pair", {})

    def test_origin_host_duplicate_auth_and_wrong_token_rejected(self):
        cases = [self.headers + [("Origin", "")], self.headers + [("Host", "evil.example")],
                 [(k, "evil.example:8766" if k == "Host" else v) for k, v in self.headers],
                 self.headers + [("Authorization", "Bearer " + "a" * 32)],
                 [(k, "Bearer wrong" if k == "Authorization" else v) for k, v in self.headers]]
        for headers in cases:
            self.assertIn(self.run_request(headers)[0], (401, 403))
        self.service.dispatch.assert_not_called()

    def test_length_transfer_and_media_rejections_do_not_reach_service(self):
        for headers in (self.headers + [("Transfer-Encoding", "chunked")],
                        self.headers + [("Content-Length", "2")],
                        [(k, "4097" if k == "Content-Length" else v) for k, v in self.headers],
                        [(k, "02" if k == "Content-Length" else v) for k, v in self.headers],
                        [(k, "text/plain" if k == "Content-Type" else v) for k, v in self.headers]):
            self.assertIn(self.run_request(headers)[0], (400, 411, 413, 415))
        self.service.dispatch.assert_not_called()

    def test_duplicate_json_nan_utf8_and_truncation_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'"\xff"'):
            headers = [(k, str(len(raw)) if k == "Content-Length" else v) for k, v in self.headers]
            self.assertEqual(self.run_request(headers, raw)[0], 400)
        self.assertEqual(self.run_request(raw=b"{")[0], 400)
        self.service.dispatch.assert_not_called()

    def test_body_absolute_deadline_rejects_trickling_client(self):
        with patch.object(http.time, "monotonic", side_effect=[0.0, 0.0, 2.0]):
            self.handler.headers = Message()
            for key, value in self.headers:
                self.handler.headers[key] = value
            self.handler.rfile = Mock()
            self.handler.rfile.read1.return_value = b"{"
            self.handler._dispatch("POST")
        self.assertEqual(self.handler._send.call_args.args[0], 408)
        self.service.dispatch.assert_not_called()

    def test_small_excess_drain_has_fixed_budget_and_never_accepts_body(self):
        raw = b"x" * (http.MAX_BODY + 1)
        headers = [(k, str(len(raw)) if k == "Content-Length" else v) for k, v in self.headers]
        self.assertEqual(self.run_request(headers, raw)[0], 413)
        self.assertEqual(self.handler.rfile.tell(), len(raw))
        huge = [(k, "99999999" if k == "Content-Length" else v) for k, v in self.headers]
        self.assertEqual(self.run_request(huge, raw)[0], 413)
        self.assertEqual(self.handler.rfile.tell(), 0)
        self.service.dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
