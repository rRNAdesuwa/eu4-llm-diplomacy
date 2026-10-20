from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_rejection import (
    project_native_peace_rejection,
    validate_native_peace_rejection,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "r66_peace_rejection_real.json"


class R66PeaceRejectionRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    @staticmethod
    def _source_path(meta: dict) -> Path:
        return ROOT / Path(meta["path"])

    def _read_source(self, meta: dict) -> object:
        path = self._source_path(meta)
        self.assertTrue(path.is_file(), path)
        raw_file = path.read_bytes()
        self.assertEqual(meta["bytes"], len(raw_file))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw_file).hexdigest())
        lines = raw_file.splitlines()
        raw_line = lines[meta["line"] - 1]
        self.assertEqual(meta["line_bytes"], len(raw_line))
        self.assertEqual(meta["line_sha256"],
                         hashlib.sha256(raw_line).hexdigest())
        return json.loads(raw_line.decode("utf-8"))

    def _read_public(self, meta: dict) -> object:
        path = self._source_path(meta)
        self.assertTrue(path.is_file(), path)
        raw_file = path.read_bytes()
        self.assertEqual(meta["bytes"], len(raw_file))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw_file).hexdigest())
        return json.loads(raw_file.decode("utf-8"))

    def test_real_rejection_binding_decode_and_public_completeness(self):
        report = self.fixture["source_report"]
        report_path = self._source_path(report)
        self.assertEqual(report["sha256"],
                         hashlib.sha256(report_path.read_bytes()).hexdigest())

        for name, case in self.fixture["cases"].items():
            with self.subTest(case=name):
                event = self._read_source(case["source"]["native"])
                public = self._read_public(case["source"]["public"])
                self.assertEqual(case["event"], event)
                self.assertEqual(case["public_rejection"], public)
                request = case["request"]
                self.assertTrue(validate_native_peace_rejection(
                    event, **request))
                projected = project_native_peace_rejection(
                    event, EU4_ESCAPE_CODEC)
                self.assertIsNotNone(projected)
                assert projected is not None
                self.assertEqual(case["expected"]["reason_code"],
                                 projected["reason_code"])
                self.assertTrue(projected["binding_complete"])
                self.assertEqual(projected["reason"], public["reason"])
                self.assertEqual(projected["diagnostic"], public["diagnostic"])
                self.assertEqual(projected["legality"], public["legality"])
                self.assertEqual(projected["submitted"], public["submitted"])
                self.assertEqual("failed", public["status"])
                # A complete binding records the failure, but is not a proof
                # that the entire native rule universe was exhausted.
                self.assertTrue(public["binding_complete"])
                self.assertFalse(public["reason"]["complete"])
                self.assertFalse(public["legality"]["complete"])
                self.assertNotIn("session_id", json.dumps(public))
                self.assertNotIn("native_diagnostic_hex", json.dumps(public))

    @staticmethod
    def _installation(root: Path, session_id: str) -> Path:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r66-rejection-real",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 116444736000000000,
            "dll_sha256": "fixture",
        }), encoding="utf-8")
        (root / "control-probe.jsonl").write_text(
            json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": session_id,
                "native_peace_submission": True,
            }) + "\n", encoding="utf-8")
        return installation

    def test_fake_submit_rejection_is_journaled_and_readable_without_resend(self):
        """Exercise the invalidation/reopen path with the observed rejection only."""

        case = self.fixture["cases"]["white_cooldown"]
        event = case["event"]
        public = case["public_rejection"]
        parameters = {
            "peace_context": {
                "war_id": event["war_id"],
                "direction": event["direction"],
                "terms": [],
            },
        }
        inspection = {
            "action_id": event["action_id"],
            "actor": event["actor"],
            "recipient": event["recipient"],
            "phase": event["phase"],
            "session": {
                "status": "ready", "date_raw": event["date_raw"],
                "state_id": "r66-rejection-fixture",
            },
            "parameters": {"requested": parameters, "complete": True},
            "legality": {"status": "available", "reasons": [],
                          "complete": True},
            "authorization": {"status": "available", "complete": True},
            "interface_support": {"query": "native_peace_execution_inspection",
                                   "execute": "native_peace_submission",
                                   "complete": True},
        }
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            session_id = "r66-rejection-replay"
            session = ObserverSession(self._installation(temp, session_id),
                                      temp / "eu4.exe")
            journal = DurableJournal(":memory:", "r66-rejection-real",
                                     session.session_id)
            tools = DiplomacyTools(journal, session)
            native_rejection = copy.deepcopy(public)
            native_rejection["status"] = "failed"
            with patch.object(tools, "inspect_diplomatic_action",
                              return_value=inspection), \
                    patch.object(session, "submit_peace",
                                 return_value=native_rejection) as submitter:
                result = tools.execute_diplomatic_action(
                    "r66_replay_white_001", event["action_id"],
                    event["actor"], event["recipient"], event["phase"],
                    parameters)
            try:
                self.assertEqual("invalidated", result["status"])
                self.assertFalse(result["submitted"])
                self.assertEqual(1, submitter.call_count)
                stored = result["result"]
                self.assertEqual(
                    event["reason_code"], stored["reason"]["code"])
                self.assertFalse(stored["reason"]["complete"])
                self.assertEqual(
                    event["reason_code"],
                    stored["native_rejection"]["reason"]["code"])
                self.assertTrue(stored["native_rejection"]["binding_complete"])
                self.assertFalse(stored["native_rejection"]["legality"]["complete"])
                reopened = tools.get_diplomatic_result("r66_replay_white_001")
                self.assertEqual("invalidated", reopened["status"])
                self.assertFalse(reopened["submitted"])
                self.assertEqual(stored, reopened["result"])
                evidence = journal.list_evidence_for_record(
                    journal.lookup_request("r66_replay_white_001"))
                self.assertTrue(any(
                    item.evidence_type == "native_submission_failure"
                    for item in evidence))
                self.assertFalse((temp / "diplomacy-peace-execute.req").exists())
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
