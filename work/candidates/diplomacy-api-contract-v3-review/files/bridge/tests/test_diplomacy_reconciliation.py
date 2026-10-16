"""Recovery infrastructure tests with a synthetic backend; never native proofs."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import threading
import unittest
from unittest import mock

from bridge.diplomacy_api import APIError, DiplomacyAPI, canonical
from bridge.tests import test_diplomacy_api as fixtures
from tools import diplomacy as cli


class SimulatedHostCrash(BaseException):
    pass


class RecoveryBackend(fixtures.RecordingBackend):
    """Only synthetic in-memory evidence. Does not create mailbox files."""
    identity = {"store_id": "fixture-store", "session_id": "fixture-session", "pid": 123,
                "process_creation_filetime": "0000000000000001", "world_generation": 1,
                "game_sha256": fixtures.LEGACY_HASH, "dll_sha256": "A" * 64,
                "experiment_sha256": "B" * 64, "whitelist_sha256": "C" * 64}
    evidence = [{"kind": "synthetic_test_only", "reference": "memory://fixture", "sha256": "D" * 64}]

    def __init__(self):
        super().__init__()
        self.recovery_calls = []
        self.recovery = None
        self.crash = False

    def capability(self, action, build, parameters):
        return {"ready": self.ready, "dispatch_identity": dict(self.identity)}

    def binding(self, request):
        return dict(self.identity, request_id=request["request_id"],
                    request_sha256=hashlib.sha256(canonical(request).encode()).hexdigest(),
                    backend=self.name, external_id=request["request_id"], sequence=1)

    def outcome(self, request, state="queued"):
        result = {"status": state, "binding": self.binding(request), "evidence": self.evidence,
                  "dispatch_outcome_known": True, "ownership_known": True}
        if state == "dispatch_unknown":
            result.update(reason_code="native_dispatch_unknown", automatic_retry=False,
                          uncertainty="ownership_unknown", ownership_known=False)
        if state == "applied":
            result["game_effects_verified"] = True
        return result

    def receipt(self, request):
        return dict(self.outcome(request), external_id=request["request_id"])

    def submit(self, request, build):
        self.calls.append(request)
        if self.crash:
            raise SimulatedHostCrash()
        if self.fail:
            raise OSError("synthetic failure; publication may have occurred")
        return self.receipt(request)

    def reconcile(self, request, prior_record):
        self.recovery_calls.append((request, prior_record))
        if isinstance(self.recovery, Exception):
            raise self.recovery
        return self.recovery


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        fixtures.DiplomacyAPITest.setUp(self)
        self.backend = RecoveryBackend()
        self.api.backend = self.backend

    def tearDown(self):
        fixtures.DiplomacyAPITest.tearDown(self)

    def submit_queued(self):
        result = self.api.submit(self.request)
        self.assertEqual(result["status"], "queued", result)
        return result

    def become_unknown(self):
        self.submit_queued()
        self.backend.observation = self.backend.outcome(self.request, "dispatch_unknown")
        result = self.api.status(self.request["request_id"])
        self.assertEqual(result["status"], "dispatch_unknown", result)
        return result

    def test_native_unknown_holds_backend_and_survives_restart_without_resubmit(self):
        record = self.become_unknown()
        self.assertEqual(record["result"]["observation"]["reason_code"], "native_dispatch_unknown")
        self.assertFalse(record["game_effects_verified"])
        self.api.close()
        self.api = DiplomacyAPI(self.catalog, self.root / "queue.db", backend=self.backend, build_probe=lambda: self.build)
        self.assertTrue(self.api.submit(self.request)["replayed"])
        blocked = self.api.submit(dict(self.request, request_id="new-id-cannot-bypass"))
        self.assertEqual(blocked["status"], "unsupported")
        self.assertIn("backend_execution_held", [entry["code"] for entry in blocked["result"]["blockers"]])
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(self.backend.recovery_calls, [])

    def test_dispatching_crash_recovery_restores_original_receipt_without_submit(self):
        self.backend.crash = True
        with self.assertRaises(SimulatedHostCrash):
            self.api.submit(self.request)
        record = self.api.status("req-1", refresh=False)
        self.assertEqual(record["status"], "dispatching")
        self.assertEqual(record["result"]["dispatch_context"]["identity"], self.backend.identity)
        self.backend.recovery = dict(self.backend.outcome(self.request), receipt=self.backend.receipt(self.request))
        result = self.api.reconcile("req-1")
        self.assertEqual(result["status"], "queued")
        self.assertTrue(result["reconciled"])
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(len(self.backend.recovery_calls), 1)
        self.assertEqual(self.api.db.execute("SELECT COUNT(*) FROM execution_holds").fetchone()[0], 0)

    def test_unknown_can_resolve_only_with_known_ownership_and_same_identity(self):
        self.become_unknown()
        self.backend.recovery = self.backend.outcome(self.request, "applied")
        self.backend.recovery["ownership_known"] = False
        with self.assertRaises(APIError):
            self.api.reconcile("req-1")
        self.assertEqual(self.api.status("req-1")["status"], "dispatch_unknown")
        self.backend.recovery["ownership_known"] = True
        result = self.api.reconcile("req-1")
        self.assertEqual(result["status"], "applied")
        self.assertTrue(result["game_effects_verified"])
        self.assertEqual(len(self.backend.calls), 1)
        self.assertTrue(self.api.preview(dict(self.request, request_id="later"))["execution_allowed"])

    def test_wrong_process_session_digest_or_build_cannot_reconcile(self):
        self.become_unknown()
        for key, value in (("request_id", "another"), ("request_sha256", "0" * 64), ("backend", "other"),
                           ("external_id", "other"), ("session_id", "new-session"), ("pid", 124),
                           ("process_creation_filetime", "0000000000000002"), ("world_generation", 2),
                           ("sequence", 2), ("game_sha256", fixtures.CURRENT_HASH), ("dll_sha256", "E" * 64),
                           ("whitelist_sha256", "F" * 64)):
            with self.subTest(key=key):
                self.backend.recovery = self.backend.outcome(self.request, "rejected")
                self.backend.recovery["binding"][key] = value
                with self.assertRaises(APIError) as error:
                    self.api.reconcile("req-1")
                self.assertEqual(error.exception.code, "reconciliation_refused")
                self.assertEqual(self.api.status("req-1")["status"], "dispatch_unknown")
        self.assertEqual(len(self.backend.calls), 1)

    def test_unknown_status_requires_no_retry_and_artifact_evidence(self):
        self.submit_queued()
        for mutation in ({"automatic_retry": True}, {"evidence": []}, {"evidence": ["invented proof"]},
                         {"reason_code": "timeout"}, {"binding": {}}, {"game_effects_verified": True}):
            with self.subTest(mutation=mutation):
                self.backend.observation = dict(self.backend.outcome(self.request, "dispatch_unknown"), **mutation)
                result = self.api.status("req-1")
                self.assertEqual(result["status"], "queued")
                self.assertIn("observation_error", result)
        self.assertEqual(len(self.backend.calls), 1)

    def test_changed_identity_is_rejected_even_before_receipt_is_recovered(self):
        self.backend.fail = True
        self.assertEqual(self.api.submit(self.request)["status"], "dispatch_unknown")
        self.backend.recovery = self.backend.outcome(self.request, "dispatched")
        self.backend.recovery["binding"]["pid"] = 124
        self.backend.recovery["receipt"] = self.backend.receipt(self.request)
        with self.assertRaises(APIError):
            self.api.reconcile("req-1")
        self.assertEqual(self.api.status("req-1")["status"], "dispatch_unknown")

    def test_dispatch_unknown_cannot_regress_to_queued(self):
        self.become_unknown()
        self.backend.recovery = self.backend.outcome(self.request)
        with self.assertRaises(APIError):
            self.api.reconcile("req-1")
        self.assertEqual(self.api.status("req-1")["status"], "dispatch_unknown")

    def test_recovery_applied_needs_effect_evidence_and_original_receipt(self):
        self.backend.fail = True
        self.api.submit(self.request)
        self.backend.recovery = self.backend.outcome(self.request, "applied")
        with self.assertRaises(APIError):
            self.api.reconcile("req-1")
        self.backend.recovery["receipt"] = self.backend.receipt(self.request)
        self.backend.recovery["game_effects_verified"] = False
        with self.assertRaises(APIError):
            self.api.reconcile("req-1")
        self.backend.recovery["game_effects_verified"] = True
        self.assertTrue(self.api.reconcile("req-1")["game_effects_verified"])
        self.assertEqual(len(self.backend.calls), 1)

    def test_read_failure_does_not_change_state_and_is_audited(self):
        self.become_unknown()
        self.backend.recovery = OSError("synthetic unreadable journal")
        with self.assertRaises(APIError) as error:
            self.api.reconcile("req-1")
        self.assertEqual(error.exception.code, "reconciliation_refused")
        self.assertEqual(self.api.audit("req-1")["events"][-1]["event"], "reconciliation_refused")
        self.assertEqual(self.api.status("req-1")["status"], "dispatch_unknown")

    def test_missing_backend_or_unknown_request_never_creates_or_replays(self):
        with self.assertRaises(APIError) as error:
            self.api.reconcile("not-present")
        self.assertEqual(error.exception.code, "request_not_found")
        self.submit_queued()
        self.api.backend = None
        with self.assertRaises(APIError) as error:
            self.api.reconcile("req-1")
        self.assertEqual(error.exception.code, "reconciliation_unavailable")
        self.assertEqual(len(self.backend.calls), 1)

    def test_terminal_results_are_immutable_and_do_not_call_recovery(self):
        self.api.backend = None
        self.assertEqual(self.api.submit(self.request)["status"], "unsupported")
        self.api.backend = self.backend
        result = self.api.reconcile("req-1")
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["reconciled"])
        self.assertEqual(self.backend.recovery_calls, [])

    def test_concurrent_dispatch_has_durable_hold_before_backend_call(self):
        entered, release = threading.Event(), threading.Event()
        original_submit = self.backend.submit
        def wait_submit(request, build):
            entered.set()
            self.assertTrue(release.wait(3))
            return original_submit(request, build)
        self.backend.submit = wait_submit
        other = DiplomacyAPI(self.catalog, self.root / "queue.db", backend=self.backend, build_probe=lambda: self.build)
        errors = []
        def submit():
            try:
                self.api.submit(self.request)
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=submit)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            result = other.submit(dict(self.request, request_id="parallel-other-id"))
            self.assertEqual(result["status"], "unsupported")
            self.assertEqual(other.status("req-1", refresh=False)["status"], "dispatching")
        finally:
            release.set()
            thread.join(3)
            other.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(self.backend.calls), 1)

    def test_recovery_rejects_historical_record_without_pre_dispatch_identity(self):
        self.api.backend = fixtures.RecordingBackend()
        self.api.submit(self.request)
        self.api.backend = self.backend
        self.backend.recovery = self.backend.outcome(self.request, "applied")
        with self.assertRaises(APIError):
            self.api.reconcile("req-1")
        self.assertEqual(self.api.status("req-1", refresh=False)["status"], "queued")

    def test_cli_reconcile_uses_read_only_method(self):
        self.submit_queued()
        self.backend.recovery = self.backend.outcome(self.request, "rejected")
        with mock.patch.object(cli, "DiplomacyAPI", return_value=self.api), mock.patch.object(self.api, "close"), contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(["reconcile", "req-1"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "rejected")
        self.assertEqual(len(self.backend.calls), 1)


class ReconciliationHTTPTests(unittest.TestCase):
    setUp = fixtures.HTTPTransportTest.setUp
    tearDown = fixtures.HTTPTransportTest.tearDown
    call = fixtures.HTTPTransportTest.call

    def test_http_never_accepts_client_evidence_or_creates_missing_request(self):
        status, result = self.call("POST", "/v1/requests/missing/reconcile", "{}")
        self.assertEqual(status, 404)
        self.assertEqual(result["error"]["code"], "request_not_found")
        self.assertEqual(self.call("POST", "/v1/requests/req-1/reconcile", '{"status":"applied"}')[0], 422)
        self.call("POST", "/v1/requests", json.dumps(self.request))
        status, result = self.call("POST", "/v1/requests/req-1/reconcile", "{}")
        self.assertEqual(status, 501)
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["reconciled"])
        self.assertEqual(self.backend.calls, [])


if __name__ == "__main__":
    unittest.main()
