"""Publication failures use fake sessions and never inspect or call EU4."""
import http.client
import contextlib
import io
import json
import threading
import unittest
from unittest.mock import Mock, patch

from bridge.tag_command_backend import PublicationUnknownError
from bridge.tag_command_service import make_server
from bridge.tests import test_tag_command_backend as fixtures


class FailingRuntime(fixtures.FakeRuntime):
    def __init__(self, *, fail_at=None, error=None, expire_at=None, before_check=None):
        super().__init__()
        self.fail_at, self.error = fail_at, error
        self.expire_at, self.before_check = expire_at, before_check

    def check(self, identity, build, manifest, owner=None):
        super().check(identity, build, manifest, owner)
        if self.before_check is not None:
            self.before_check(len(self.checks))
        if len(self.checks) == self.fail_at:
            raise self.error

    def now(self):
        return 60100 if self.expire_at is not None and len(self.checks) >= self.expire_at else 100


class TagCommandPublicationFailureTests(unittest.TestCase):
    event = fixtures.TagCommandTests.event

    def setUp(self):
        fixtures.TagCommandTests.setUp(self)
        self.commands = [self.command, dict(self.command, request_id="publication-second",
                                          actor="ENG", action="trade_favors_for_men")]
        self.backend.status = Mock(wraps=self.backend.status)

    def use_runtime(self, **kwargs):
        self.runtime = FailingRuntime(**kwargs)
        self.backend.runtime = self.runtime

    def http_publish(self, commands=None):
        server = make_server(self.backend, self.identity, port=0, token="offline-publication-test")
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.01})
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            connection.request("POST", "/native/v1/batches",
                               json.dumps(self.commands if commands is None else commands),
                               {"Authorization":"Bearer offline-publication-test",
                                "Content-Type":"application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def assert_partial_publication(self, status, value):
        self.assertEqual(status, 409)
        self.assertEqual(value["error"], "publication_unknown")
        self.assertEqual(value["state"], "publication_unknown")
        self.assertFalse(value["automatic_retry"])
        self.assertFalse(value["gameplay_effects_verified"])
        self.assertEqual(value["results"], [
            {"request_id":self.commands[0]["request_id"], "sequence":1, "publication_stage":"published"},
            {"request_id":self.commands[1]["request_id"], "sequence":2, "publication_stage":"pending_retained"},
        ])
        self.assertTrue((self.directory / "1.request").exists())
        self.assertFalse((self.directory / "2.request").exists())
        self.assertTrue((self.directory / "publisher.lock").exists())
        self.assertEqual(len(list(self.directory.glob("key-*.json"))), 2)
        # Error reporting must not guess results from a possibly unreadable audit.
        self.assertEqual(self.backend.status.call_count, 1)
        self.assertTrue(all("native_result" not in row for row in value["results"]))

    def test_value_error_after_first_publication_returns_unknown_and_retains_lock(self):
        self.use_runtime(fail_at=3, error=ValueError("Manual pause changed"))
        self.assert_partial_publication(*self.http_publish())
        self.assertTrue((self.directory / "2.pending").exists())
        checks = len(self.runtime.checks)
        status, value = self.http_publish()
        self.assertEqual(status, 409)
        self.assertFalse(value["automatic_retry"])
        self.assertEqual(len(self.runtime.checks), checks)
        self.assertEqual(len(list(self.directory.glob("*.request"))), 1)

    def test_expiry_after_first_publication_returns_unknown(self):
        self.use_runtime(expire_at=3)
        status, value = self.http_publish()
        self.assert_partial_publication(status, value)
        self.assertIn("Expired before publication", value["message"])

    def test_late_missing_file_returns_unknown_without_reading_native_results(self):
        def remove_late_files(checks):
            if checks == 3:
                (self.directory / "2.pending").unlink()
                (self.directory / "events.jsonl").unlink()
        self.use_runtime(before_check=remove_late_files)
        self.assert_partial_publication(*self.http_publish())

    def test_backend_exposes_typed_error_with_last_publisher_stages(self):
        self.use_runtime(fail_at=3, error=ValueError("Manual pause changed"))
        with self.assertRaises(PublicationUnknownError) as caught:
            self.backend.publish(self.identity, self.commands)
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assert_partial_publication(409, caught.exception.result)

    def test_cli_preserves_partial_publication_details_and_failure_exit_code(self):
        from tools.tag_command import main
        self.use_runtime(fail_at=3, error=ValueError("Manual pause changed"))
        session = self.path / "offline-session.json"
        session.write_text(json.dumps({"identity":self.identity}))
        commands = self.path / "offline-batch.json"
        commands.write_text(json.dumps(self.commands))
        output = io.StringIO()
        with patch("tools.tag_command.TagCommandBackend", return_value=self.backend), \
             patch("sys.argv", ["tag_command.py", "batch", "--session-file", str(session),
                                "--commands", str(commands)]), contextlib.redirect_stdout(output):
            self.assertEqual(main(), 2)
        self.assert_partial_publication(409, json.loads(output.getvalue()))

    def test_prepublication_runtime_value_error_remains_422(self):
        self.use_runtime(fail_at=1, error=ValueError("Manual pause required"))
        status, value = self.http_publish()
        self.assertEqual((status, value["error"]), (422, "invalid_or_refused"))
        self.assertFalse((self.directory / "publisher.lock").exists())
        self.assertFalse(list(self.directory.glob("key-*.json")))

    def test_prepublication_missing_file_remains_404(self):
        self.use_runtime(fail_at=1, error=FileNotFoundError("Missing preflight file"))
        status, value = self.http_publish()
        self.assertEqual((status, value["error"]), (404, "not_found"))
        self.assertFalse((self.directory / "publisher.lock").exists())
        self.assertFalse(list(self.directory.glob("key-*.json")))

    def test_invalid_command_remains_422_before_runtime_or_reservation(self):
        self.use_runtime()
        status, value = self.http_publish([dict(self.command, action="unknown")])
        self.assertEqual((status, value["error"]), (422, "invalid_or_refused"))
        self.assertEqual(self.runtime.checks, [])
        self.assertFalse((self.directory / "publisher.lock").exists())
        self.assertFalse(list(self.directory.glob("key-*.json")))


if __name__ == "__main__":
    unittest.main()
