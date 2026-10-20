"""Corrupted/partial receipts must never authorize a repeated native action."""
import copy
import json
import unittest

from bridge.tag_command_audit import AuditSnapshot, recorded_snapshot
from bridge.tag_command_backend import TagCommandBackend, decode, digest, encode, read
from bridge.tests import test_tag_command_backend as fixtures
from tools.plan_tag_command_continuation import prepare


class TagCommandAuditTests(unittest.TestCase):
    event = fixtures.TagCommandTests.event

    def setUp(self):
        fixtures.TagCommandTests.setUp(self)

    def snapshot(self):
        return AuditSnapshot(self.directory, self.identity, purpose=self.backend.purpose,
                             actions=self.backend.actions, limit=self.backend.limit)

    def evidence(self, commands):
        snapshot = self.snapshot()
        from collections import Counter
        results = [snapshot.status(c["request_id"]) for c in commands]
        return {"schema": "EU4TAG31-INTEGRATION/1", "file_only": True,
                "identity": self.identity, "terminal": True, "unknown_must_not_be_retried": True,
                "audit_sha256": digest(snapshot.raw), "planned": len(commands), "results": results,
                "states": dict(Counter(r["state"] for r in results)),
                "native_call_begins": sum(r["event"] == "native_call_begin" for r in snapshot.rows)}

    def terminal_plan(self):
        commands = [self.command, dict(self.command, request_id="unclaimed-2", action="trade_favors_for_men")]
        self.backend.publish(self.identity, commands)
        (self.directory / "1.claim").write_bytes((self.directory / "1.request").read_bytes())
        self.event("request_claimed", 1, action=self.command["action"], actor="POR", target="BRI", expires=60100)
        self.event("native_call_begin", 1, call=1)
        self.event("terminal", 1, unknown_no_retry=True)
        return commands

    def test_only_unclaimed_remainder_is_kept_with_original_ids(self):
        commands = self.terminal_plan()
        remaining, review = prepare(self.snapshot(), commands, self.evidence(commands))
        self.assertEqual(remaining, commands[1:])
        self.assertEqual(review["excluded"][0]["state"], "unknown_no_retry")
        self.assertFalse(review["excluded"][0]["may_resend"])
        self.assertFalse(review["publishes"])
        self.assertEqual(len(list(self.directory.glob("*.request"))), 2)

    def test_claim_without_audit_is_not_proof_of_unclaimed(self):
        commands = self.terminal_plan()
        evidence = self.evidence(commands)
        (self.directory / "2.claim").write_bytes((self.directory / "2.request").read_bytes())
        with self.assertRaisesRegex(ValueError, "Unproven unclaimed"):
            prepare(self.snapshot(), commands, evidence)

    def test_partial_tail_stale_evidence_and_publisher_uncertainty_refuse(self):
        commands = self.terminal_plan()
        evidence = self.evidence(commands)
        changed = copy.deepcopy(evidence)
        changed["audit_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Captured evidence mismatch"):
            prepare(self.snapshot(), commands, changed)
        (self.directory / "publisher.lock").write_bytes(b"unknown publisher")
        with self.assertRaisesRegex(ValueError, "Uncertain publisher"):
            prepare(self.snapshot(), commands, evidence)
        (self.directory / "publisher.lock").unlink()
        with (self.directory / "events.jsonl").open("ab") as stream:
            stream.write(b'{"event":"native_call_begin"')
        with self.assertRaisesRegex(ValueError, "Partial audit tail"):
            prepare(self.snapshot(), commands, evidence)

    def test_published_packet_and_intent_are_checked_even_without_claim(self):
        commands = self.terminal_plan()
        evidence = self.evidence(commands)
        (self.directory / "2.request").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Published request changed"):
            prepare(self.snapshot(), commands, evidence)

    def test_altered_captured_result_does_not_authorize_continuation(self):
        commands = self.terminal_plan()
        evidence = self.evidence(commands)
        evidence["results"][0]["state"] = "not_dispatched"
        with self.assertRaisesRegex(ValueError, "Captured request result mismatch"):
            prepare(self.snapshot(), commands, evidence)

    def test_audit_after_terminal_or_from_another_thread_is_refused(self):
        self.terminal_plan()
        self.event("native_call_begin", 2, call=1)
        with self.assertRaisesRegex(ValueError, "continued after terminal"):
            self.snapshot()
        self.rows.pop()
        self.rows[-1]["thread"] = 99
        (self.directory / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.rows))
        with self.assertRaisesRegex(ValueError, "Non-owner native audit"):
            self.snapshot()

    def test_old_source_mismatch_is_readable_but_never_runnable(self):
        path = self.path / "build.json"
        manifest = decode(read(path, 1024 * 1024))
        next(iter(manifest["source_pins"].values()))["sha256"] = "0" * 64
        path.write_bytes(encode(manifest))
        self.identity["manifest_sha256"] = digest(path.read_bytes())
        self.rows = []
        self.event("bootstrap_verified", 0)
        self.event("hook_installed", 0)
        snapshot = recorded_snapshot(path, self.identity)
        self.assertTrue(snapshot.status()["hook_installed"])
        self.assertFalse(hasattr(snapshot, "publish"))
        self.assertFalse(hasattr(snapshot, "load"))
        with self.assertRaisesRegex(ValueError, "Build source changed"):
            TagCommandBackend(path)


if __name__ == "__main__":
    unittest.main()
