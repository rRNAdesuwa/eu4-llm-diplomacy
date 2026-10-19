"""Real loopback HTTP tests with a pure observer; never open a game process."""
from copy import deepcopy
import http.client
import json
import threading
import unittest

from bridge.diplomacy_observer_service import make_server


TOKEN = "offline-observer-test-token-123"
PREFIX = "/observer/v1/effects/"
CATALOG = "/observer/v1/capabilities"


class PureObserver:
    """Only returns supplied data: no backend, files, RPM or native calls."""

    def __init__(self):
        self.calls = []
        self.responses = {}
        self.errors = {}

    def observe(self, request_id):
        self.calls.append(request_id)
        if request_id in self.errors:
            raise self.errors[request_id]
        if request_id not in self.responses:
            raise FileNotFoundError(request_id)
        return deepcopy(self.responses[request_id])


def observation(request_id="known-request", *, verified=True, stage="selected_effect_observed"):
    return {
        "schema": "EU4DIPLOMACY-OBSERVATION/1",
        "request_id": request_id,
        "transport_state": "dispatched",
        "completion_state": stage,
        "native_calls": 0,
        "memory_written": False,
        "requests_published": 0,
        "saves_written": 0,
        "automatic_command_retry": False,
        "persistence_verified": False,
        "AI_acceptance_verified": False,
        "effect": {
            "schema": "EU4DIPLOMACY-EFFECT/1",
            "status": "observed" if verified else "unknown",
            "selected_effect_verified": verified,
            "completion_stage": stage,
        },
    }


class ObserverHTTPTests(unittest.TestCase):
    def setUp(self):
        self.observer = PureObserver()
        self.observer.responses["known-request"] = observation()
        self.server = make_server(self.observer, port=0, token=TOKEN)
        self.worker = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            name="offline-diplomacy-observer-http-test",
        )
        self.addCleanup(self.stop_server)
        self.worker.start()

    def stop_server(self):
        try:
            if self.worker.is_alive():
                self.server.shutdown()
        finally:
            try:
                self.server.server_close()
            finally:
                if self.worker.ident is not None:
                    self.worker.join(3)
        self.assertFalse(self.worker.is_alive(), "Temporary HTTP worker leaked")
        self.assertEqual(self.server.socket.fileno(), -1, "Temporary listening socket leaked")

    def headers(self, host=None):
        return [
            ("Host", host if host is not None else f"127.0.0.1:{self.server.server_port}"),
            ("Authorization", "Bearer " + TOKEN),
        ]

    def call(self, method, path, *, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for name, value in self.headers() if headers is None else headers:
                connection.putheader(name, value)
            if body is not None:
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            raw = response.read(256 * 1024 + 1024)
            response_headers = dict(response.getheaders())
            value = json.loads(raw) if response_headers.get("Content-Type", "").startswith("application/json") else raw
            return response.status, value, response_headers, raw
        finally:
            connection.close()

    def assert_json(self, result, status):
        code, value, headers, raw = result
        self.assertEqual(code, status)
        self.assertEqual(headers.get("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(int(headers["Content-Length"]), len(raw))
        return value

    def test_binds_only_ipv4_loopback_with_temporary_port(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertGreater(self.server.server_port, 0)

    def test_catalog_never_touches_observer(self):
        value = self.assert_json(self.call("GET", CATALOG), 200)
        self.assertEqual(value["schema"], "EU4DIPLOMACY-OBSERVER-CATALOG/1")
        self.assertTrue(value["read_only"])
        self.assertFalse(value["all120_effect_profiles_complete"])
        self.assertTrue(value["profiles"])
        self.assertTrue(all("required_fields" in p for p in value["profiles"]))
        self.assertEqual([value[k] for k in ("native_calls", "saves_written", "requests_published")], [0, 0, 0])
        self.assertEqual(self.observer.calls, [])

    def test_exact_effect_result_is_forwarded_once(self):
        value = self.assert_json(self.call("GET", PREFIX + "known-request"), 200)
        self.assertEqual(value, self.observer.responses["known-request"])
        self.assertEqual(self.observer.calls, ["known-request"])

    def test_localhost_authority_is_allowed(self):
        self.assert_json(self.call("GET", CATALOG, headers=self.headers(f"localhost:{self.server.server_port}")), 200)
        self.assertEqual(self.observer.calls, [])

    def test_unknown_request_is_not_retried(self):
        value = self.assert_json(self.call("GET", PREFIX + "missing-request"), 404)
        self.assertEqual(value["error"], "request_not_found")
        self.assertEqual(self.observer.calls, ["missing-request"])

    def test_capture_unknown_preserves_dispatched_and_failure(self):
        retained = observation(verified=False, stage="evidence_insufficient")
        retained["effect"]["failure"] = {"type": "OSError", "message": "Selected memory unavailable"}
        self.observer.responses["known-request"] = retained
        value = self.assert_json(self.call("GET", PREFIX + "known-request"), 200)
        self.assertEqual(value, retained)
        self.assertEqual(value["transport_state"], "dispatched")
        self.assertFalse(value["effect"]["selected_effect_verified"])
        self.assertFalse(value["automatic_command_retry"])
        self.assertEqual(self.observer.calls, ["known-request"])

    def test_annex_in_progress_is_not_relabelled_completed(self):
        retained = observation(stage="in_progress")
        self.observer.responses["known-request"] = retained
        value = self.assert_json(self.call("GET", PREFIX + "known-request"), 200)
        self.assertEqual(value["completion_state"], "in_progress")
        self.assertFalse(value["persistence_verified"])
        self.assertFalse(value["AI_acceptance_verified"])

    def test_missing_wrong_and_duplicate_authorization_are_refused(self):
        valid_host = self.headers()[0]
        cases = [
            [valid_host],
            [valid_host, ("Authorization", "Bearer wrong-token-123456")],
            [valid_host, ("Authorization", "bearer " + TOKEN)],
            self.headers() + [("Authorization", "Bearer " + TOKEN)],
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                self.assert_json(self.call("GET", PREFIX + "known-request", headers=headers), 403)
        self.assertEqual(self.observer.calls, [])

    def test_missing_duplicate_and_external_host_are_refused(self):
        cases = [
            [("Authorization", "Bearer " + TOKEN)],
            self.headers() + [self.headers()[0]],
            self.headers(""),
            self.headers("example.invalid"),
            self.headers("127.0.0.1.example.invalid"),
            self.headers("[::1]"),
            self.headers(f"127.0.0.1:{self.server.server_port % 65535 + 1}"),
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                self.assert_json(self.call("GET", PREFIX + "known-request", headers=headers), 403)
        self.assertEqual(self.observer.calls, [])

    def test_origin_header_presence_is_always_refused(self):
        origins = [
            [("Origin", "https://example.invalid")],
            [("Origin", "null")],
            [("Origin", "")],
            [("Origin", ""), ("Origin", "https://example.invalid")],
        ]
        for extra in origins:
            with self.subTest(origins=extra):
                self.assert_json(self.call("GET", PREFIX + "known-request", headers=self.headers() + extra), 403)
        self.assertEqual(self.observer.calls, [])

    def test_malformed_host_authority_is_refused_before_observation(self):
        for host in ("attacker@localhost", "localhost/extra", "localhost?x", "localhost#x", "localhost:bogus", "[broken"):
            with self.subTest(host=host):
                code, value, _, _ = self.call("GET", PREFIX + "known-request", headers=self.headers(host))
                self.assertIn(code, (403, 422))
                self.assertIsInstance(value, dict)
        self.assertEqual(self.observer.calls, [])

    def test_all_explicit_write_methods_refuse_without_observation(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in (PREFIX + "known-request", "/native/v1/commands", CATALOG):
                with self.subTest(method=method, path=path):
                    value = self.assert_json(self.call(method, path, body=b'{"action":"annex_vassal"}'), 405)
                    self.assertEqual(value["error"], "read_only_observer")
                    self.assertEqual(value["requests_published"], 0)
        self.assertEqual(self.observer.calls, [])

    def test_unauthenticated_write_methods_are_refused_without_observation(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assert_json(self.call(method, PREFIX + "known-request", headers=[self.headers()[0]], body=b"ignored"), 403)
        self.assertEqual(self.observer.calls, [])

    def test_write_origin_and_malformed_host_are_refused_without_observation(self):
        for headers in (
            self.headers() + [("Origin", "")],
            self.headers("attacker@localhost"),
            self.headers("[broken"),
        ):
            with self.subTest(headers=headers):
                self.assert_json(self.call("POST", PREFIX + "known-request", headers=headers), 403)
        self.assertEqual(self.observer.calls, [])

    def test_other_methods_are_non_successful_and_never_observe(self):
        for method in ("HEAD", "OPTIONS", "TRACE", "CONNECT"):
            with self.subTest(method=method):
                code, _, _, _ = self.call(method, PREFIX + "known-request")
                self.assertIn(code, (405, 501))
        self.assertEqual(self.observer.calls, [])

    def test_queries_fragments_and_overlong_path_are_refused_before_observation(self):
        for path in (PREFIX + "known-request?x=1", PREFIX + "known-request#fragment", PREFIX + "x" * 600):
            with self.subTest(path=path):
                value = self.assert_json(self.call("GET", path), 422)
                self.assertEqual(value["error"], "invalid_or_refused")
        self.assertEqual(self.observer.calls, [])

    def test_malformed_request_ids_are_refused_before_observation(self):
        for request_id in ("", "nested/id", "..%2fknown-request", "%6bnown-request", "id+suffix", "x" * 97):
            with self.subTest(request_id=request_id):
                self.assert_json(self.call("GET", PREFIX + request_id), 422)
        self.assertEqual(self.observer.calls, [])

    def test_bounded_id_punctuation_is_forwarded_unchanged(self):
        request_id = "r3.request_id:1-" + "x" * 80
        self.assertEqual(len(request_id), 96)
        self.observer.responses[request_id] = observation(request_id)
        value = self.assert_json(self.call("GET", PREFIX + request_id), 200)
        self.assertEqual(value["request_id"], request_id)
        self.assertEqual(self.observer.calls, [request_id])

    def test_unknown_endpoint_and_absolute_uri_do_not_observe(self):
        for path in ("/", "/native/v1/commands/known-request", "/observer/v1/effects", "http://localhost" + PREFIX + "known-request"):
            with self.subTest(path=path):
                code, _, _, _ = self.call("GET", path)
                self.assertIn(code, (404, 422))
        self.assertEqual(self.observer.calls, [])

    def test_observer_validation_error_is_structured_without_retry(self):
        self.observer.errors["known-request"] = ValueError("Evidence identity mismatch")
        value = self.assert_json(self.call("GET", PREFIX + "known-request"), 422)
        self.assertEqual(value["error"], "invalid_or_refused")
        self.assertEqual(self.observer.calls, ["known-request"])

    def test_outer_io_failure_is_unknown_without_automatic_retry(self):
        for failure in (OSError("Evidence unavailable"), RuntimeError("State unstable")):
            with self.subTest(failure=type(failure).__name__):
                self.observer.errors["known-request"] = failure
                value = self.assert_json(self.call("GET", PREFIX + "known-request"), 409)
                self.assertEqual(value["status"], "unknown")
                self.assertFalse(value["automatic_command_retry"])
        self.assertEqual(self.observer.calls, ["known-request", "known-request"])

    def test_non_json_finite_result_is_refused(self):
        self.observer.responses["known-request"]["invalid"] = float("nan")
        value = self.assert_json(self.call("GET", PREFIX + "known-request"), 422)
        self.assertEqual(value["error"], "invalid_or_refused")
        self.assertEqual(self.observer.calls, ["known-request"])

    def test_oversized_result_is_refused(self):
        self.observer.responses["known-request"]["oversized"] = "x" * (256 * 1024)
        value = self.assert_json(self.call("GET", PREFIX + "known-request"), 422)
        self.assertEqual(value["error"], "invalid_or_refused")
        self.assertEqual(self.observer.calls, ["known-request"])


class ObserverServerArgumentTests(unittest.TestCase):
    def test_invalid_bind_arguments_fail_before_server_allocation(self):
        for port in (-1, 65536, True, "8775"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    make_server(PureObserver(), port=port, token=TOKEN)
        for token in (None, "short", "x" * 257, "non-ascii-秘密-token"):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    make_server(PureObserver(), port=0, token=token)


if __name__ == "__main__":
    unittest.main()
