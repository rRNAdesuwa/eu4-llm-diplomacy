"""Offline contract/transport tests; these do not assert native game execution."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from bridge.diplomacy_api import APIError, DEFAULT_CATALOG, DiplomacyAPI, decode_json
from bridge.diplomacy_service import MAX_BODY, MAX_REJECT_DRAIN, make_server


LEGACY_HASH = "B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77"
CURRENT_HASH = "9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A"


class RecordingBackend:
    """Test double only. It never reads or writes a game process."""
    name = "legacy_v9"

    def __init__(self):
        self.calls = []
        self.fail = False
        self.ready = True
        self.observation = {"status": "queued", "evidence": [{"kind": "test_queue"}]}

    def capability(self, action, build, parameters):
        return {"ready": self.ready, "reason": "Test readiness"}

    def submit(self, request, build):
        self.calls.append(request)
        if self.fail:
            raise OSError("simulated timeout after dispatch")
        return {"status": "queued", "external_id": request["request_id"], "evidence": [{"kind": "test_queue"}]}

    def status(self, request, receipt):
        return self.observation


class DiplomacyAPITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps({"schema_version": 1, "actions": [{
            "action_id": "whitepeace", "name_zh": "白和平", "parameter_status": "specified",
            "parameters": {"type": "object", "additionalProperties": False, "required": ["actor", "target"],
                           "properties": {"actor": {"type": "string", "const": "FRA"},
                                          "target": {"type": "string", "const": "ENG"},
                                          "amount": {"type": "integer", "minimum": 0, "maximum": 10}}},
            "execution": {"status": "legacy_build_verified", "backend": "legacy_v9", "supported_builds": [LEGACY_HASH]}
        }, {"action_id": "improve_relations", "parameter_status": "specified",
            "parameters": {"type": "object", "properties": {}},
            "execution": {"status": "unimplemented", "backend": None, "supported_builds": []}}
        ]}), encoding="utf-8")
        self.backend = RecordingBackend()
        self.build = {"sha256": LEGACY_HASH, "status": "legacy_experiments_verified"}
        self.api = DiplomacyAPI(self.catalog, self.root / "queue.db", backend=self.backend, build_probe=lambda: self.build)
        self.request = {"request_id": "req-1", "action": "whitepeace", "parameters": {"actor": "FRA", "target": "ENG"}}

    def tearDown(self):
        self.api.close()
        self.temp.cleanup()

    def assert_error(self, code, request):
        with self.assertRaises(APIError) as raised:
            self.api.submit(request)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.backend.calls, [])

    def test_current_build_cannot_dispatch_legacy_action(self):
        self.build = {"sha256": CURRENT_HASH, "status": "static_analysis_only"}
        result = self.api.submit(self.request)
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["game_effects_verified"])
        self.assertIn("unsupported_build", [b["code"] for b in result["result"]["blockers"]])
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.api.audit("req-1")["events"][0]["event"], "unsupported")

    def test_unimplemented_and_absent_backend_fail_closed(self):
        self.api.backend = None
        result = self.api.submit({"request_id": "static", "action": "improve_relations", "parameters": {}})
        self.assertEqual(result["status"], "unsupported")
        codes = {b["code"] for b in result["result"]["blockers"]}
        self.assertIn("action_unimplemented", codes)
        self.assertIn("backend_unavailable", codes)

    def test_unknown_build_and_probe_failure_fail_closed(self):
        self.build = {"sha256": None, "status": "unknown_build"}
        self.assertFalse(self.api.preview(self.request)["execution_allowed"])
        self.api.build_probe = lambda: (_ for _ in ()).throw(OSError("test read failure"))
        self.assertFalse(self.api.preview(self.request)["execution_allowed"])

    def test_unknown_fields_targets_and_bool_integer_rejected_before_dispatch(self):
        self.assert_error("invalid_request", dict(self.request, script="x"))
        for parameters in ({"actor": "FRA", "target": "ENG", "script": "declare_war"},
                           {"actor": "FRA", "target": "POR"},
                           {"actor": "FRA", "target": "ENG", "amount": True},
                           {"actor": "FRA", "target": "ENG", "amount": 11},
                           {"actor": "FRA"}):
            self.assert_error("invalid_parameters", dict(self.request, parameters=parameters))
        self.assert_error("invalid_request_id", dict(self.request, request_id="../unsafe"))
        self.assert_error("unknown_action", dict(self.request, action="raw_script"))

    def test_partial_parameter_contract_is_not_executable(self):
        self.api.actions["whitepeace"]["parameter_status"] = "partial"
        self.assertEqual(self.api.submit(self.request)["status"], "unsupported")
        self.assertEqual(self.backend.calls, [])

    def test_preview_is_contract_only_and_does_not_dispatch_or_queue(self):
        result = self.api.preview(self.request)
        self.assertTrue(result["schema_valid"])
        self.assertFalse(result["game_legality_checked"])
        self.assertEqual(result["preview_kind"], "contract_only")
        self.assertEqual(self.backend.calls, [])
        with self.assertRaises(APIError):
            self.api.status("req-1")

    def test_request_id_is_durable_and_conflicting_payload_rejected(self):
        self.assertEqual(self.api.submit(self.request)["status"], "queued")
        self.api.close()
        self.api = DiplomacyAPI(self.catalog, self.root / "queue.db", backend=self.backend, build_probe=lambda: self.build)
        self.assertTrue(self.api.submit(self.request)["replayed"])
        with self.assertRaises(APIError) as raised:
            self.api.submit(dict(self.request, parameters={"actor": "FRA", "target": "ENG", "amount": 1}))
        self.assertEqual(raised.exception.code, "request_id_conflict")
        self.assertEqual(len(self.backend.calls), 1)

    def test_two_service_instances_cannot_dispatch_same_id_twice(self):
        other = DiplomacyAPI(self.catalog, self.root / "queue.db", backend=self.backend, build_probe=lambda: self.build)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda api: api.submit(self.request), (self.api, other)))
            self.assertEqual(len(self.backend.calls), 1)
            self.assertEqual(sum(not result["replayed"] for result in results), 1)
        finally:
            other.close()

    def test_uncertain_dispatch_never_retries(self):
        self.backend.fail = True
        self.assertEqual(self.api.submit(self.request)["status"], "dispatch_unknown")
        self.assertTrue(self.api.submit(self.request)["replayed"])
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual([e["event"] for e in self.api.audit("req-1")["events"]], ["dispatching", "dispatch_unknown"])

    def test_queued_is_not_applied_and_effect_proof_required(self):
        self.assertFalse(self.api.submit(self.request)["game_effects_verified"])
        self.backend.observation = {"status": "applied", "evidence": ["only consumed"]}
        result = self.api.status("req-1")
        self.assertEqual(result["status"], "queued")
        self.assertIn("observation_error", result)
        self.backend.observation = {"status": "applied", "evidence": ["test fixture observed effects"], "game_effects_verified": True}
        self.assertTrue(self.api.status("req-1")["game_effects_verified"])

    def test_backend_readiness_rechecked_on_submit(self):
        self.assertTrue(self.api.preview(self.request)["execution_allowed"])
        self.backend.ready = False
        self.assertEqual(self.api.submit(self.request)["status"], "unsupported")
        self.assertEqual(self.backend.calls, [])

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for text in ('{"action":"a","action":"b"}', '{"x": NaN}', '{"x": Infinity}'):
            with self.assertRaises(APIError):
                decode_json(text)

    def test_stale_observation_cannot_overwrite_terminal_state(self):
        self.api.submit(self.request)
        self.backend.observation = {"status": "applied", "evidence": ["fixture proof"], "game_effects_verified": True}
        self.api.status("req-1")
        # Simulates a queued observation begun by another service before the applied result.
        self.api._transition("req-1", "dispatched", {"receipt": {}}, expected_status="queued")
        self.assertEqual(self.api.status("req-1")["status"], "applied")

    def test_legacy_constraints_cannot_be_bypassed_by_broad_schema(self):
        action = self.api.actions["whitepeace"]
        action["parameters"]["properties"]["actor"] = {"type": "string"}
        action["execution"]["constraints"] = {"actor": "FRA"}
        result = self.api.submit(dict(self.request, parameters={"actor": "POR", "target": "ENG"}))
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(self.backend.calls, [])


class HTTPTransportTest(unittest.TestCase):
    def setUp(self):
        DiplomacyAPITest.setUp(self)
        self.api.backend = None
        self.server = make_server(self.api, port=0, token="test-secret")
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        DiplomacyAPITest.tearDown(self)

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        request_headers = {"Authorization": "Bearer test-secret", "Content-Type": "application/json"}
        request_headers.update(headers or {})
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_http_discovery_preview_unsupported_and_audit(self):
        self.assertEqual(self.call("GET", "/v1/capabilities")[0], 200)
        self.assertEqual(self.call("GET", "/v1/actions/whitepeace")[0], 200)
        self.assertEqual(self.call("POST", "/v1/preview", json.dumps(self.request))[0], 200)
        status, result = self.call("POST", "/v1/requests", json.dumps(self.request))
        self.assertEqual(status, 501)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(self.call("GET", "/v1/requests/req-1")[1]["status"], "unsupported")
        self.assertEqual(len(self.call("GET", "/v1/requests/req-1/events")[1]["events"]), 1)

    def test_http_boundary_rejections(self):
        self.assertEqual(self.call("GET", "/v1/capabilities", headers={"Authorization": "Bearer wrong"})[0], 401)
        self.assertEqual(self.call("GET", "/v1/capabilities", headers={"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.call("GET", "/v1/capabilities", headers={"Host": "rebind.example"})[0], 403)
        self.assertEqual(self.call("POST", "/v1/preview", "{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.call("POST", "/v1/preview", "x" * (MAX_BODY + 1))[0], 413)
        self.assertEqual(self.call("POST", "/v1/preview", '{"x":1,"x":2}')[0], 400)
        self.assertEqual(self.call("GET", "/v1/requests/not-there")[0], 404)

    def test_remote_bind_requires_explicit_opt_in_and_token(self):
        for options in ({}, {"allow_remote": True}, {"allow_remote": True, "token": "short"}):
            with self.assertRaises(ValueError):
                make_server(self.api, "0.0.0.0", 0, **options)

    def test_small_oversize_uploads_return_413_without_connection_reset(self):
        # This used to fail intermittently on Windows when closing a socket
        # with the already-sent request body still in its receive buffer.
        for attempt in range(8):
            for length in (MAX_BODY + 1, MAX_REJECT_DRAIN):
                with self.subTest(attempt=attempt, length=length):
                    status, result = self.call("POST", "/v1/requests", "x" * length)
                    self.assertEqual(status, 413)
                    self.assertEqual(result["error"]["code"], "body_too_large")
        self.assertEqual(self.api.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)
        self.assertEqual(self.backend.calls, [])

    def test_oversize_headers_without_body_do_not_hold_the_connection(self):
        # The 2-second client timeout is well above the discard deadline and
        # below the normal 10-second body timeout. No body bytes are sent.
        for declared_length in (MAX_BODY + 1, MAX_REJECT_DRAIN + 1, 1 << 40):
            with self.subTest(declared_length=declared_length):
                status, result = self.call("POST", "/v1/preview", headers={"Content-Length": str(declared_length)})
                self.assertEqual(status, 413)
                self.assertEqual(result["error"]["code"], "body_too_large")


class RealCatalogTest(unittest.TestCase):
    def test_requested_diplomacy_types_have_truthful_public_contracts(self):
        with tempfile.TemporaryDirectory() as temp:
            api = DiplomacyAPI(DEFAULT_CATALOG, Path(temp) / "queue.db",
                               build_probe=lambda: {"sha256": CURRENT_HASH, "status": "static_analysis_only"})
            try:
                capabilities = api.capabilities()
                self.assertTrue(capabilities["actions"])
                self.assertFalse(any(action["execution_allowed"] for action in capabilities["actions"]))
                for action in ("offer_vassalization", "cancel_vassalization", "royal_marriage", "break_marriage",
                               "improve_relations", "stop_improving_relations", "guarantee", "revoke_guarantee",
                               "build_spy_network", "stop_building_spy_network"):
                    request = {"request_id": action, "action": action, "parameters": {"actor": "FRA", "target": "ENG"}}
                    self.assertFalse(api.preview(request)["execution_allowed"])
                    self.assertEqual(api.submit(request)["status"], "unsupported")
                    self.assertEqual(api.describe(action)["execution"]["status"], "unimplemented")
                with self.assertRaises(APIError):
                    api.preview({"request_id": "newline-tag", "action": "improve_relations",
                                 "parameters": {"actor": "FRA\n", "target": "ENG"}})
            finally:
                api.close()


if __name__ == "__main__":
    unittest.main()
