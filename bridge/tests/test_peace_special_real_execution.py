from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_special_r54_real_execution.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PeaceSpecialR54RealExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    def _check_optional_source(self, name: str) -> None:
        source = self.fixture["sources"][name]
        path = REPOSITORY_ROOT / source["path"]
        if path.exists():
            self.assertEqual(source["size"], path.stat().st_size)
            self.assertEqual(source["sha256"],
                             hashlib.sha256(path.read_bytes()).hexdigest())

    def _check_event(self, name: str) -> dict[str, object]:
        record = self.fixture[name]
        self._check_optional_source("native_events")
        path = REPOSITORY_ROOT / self.fixture["sources"]["native_events"]["path"]
        if path.exists():
            lines = path.read_bytes().splitlines()
            raw = lines[record["source_line"] - 1]
            self.assertEqual(record["source_line_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["event"], json.loads(raw.decode("utf-8")))
        return record["event"]

    def _temporary_session(self, root: Path) -> ObserverSession:
        request = self.fixture["request"]
        session_id = request["session_id"]
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": self.fixture["sources"]["experiment_id"],
            "session_id": session_id,
            "native_text_codec": "eu4_escape",
        }, separators=(",", ":")), encoding="utf-8")
        lines = [
            json.dumps(self.fixture["submission_event"]["event"],
                       ensure_ascii=False, separators=(",", ":")),
            json.dumps(self.fixture["execution_event"]["event"],
                       ensure_ascii=False, separators=(",", ":")),
        ]
        (root / "control-probe.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        return ObserverSession(installation, root / "eu4.exe")

    def _journal_with_submitted_request(self, root: Path) -> DurableJournal:
        request = self.fixture["request"]
        source_sqlite = REPOSITORY_ROOT / self.fixture["sources"]["sqlite"]["path"]
        database = root / "diplomacy.sqlite3"
        if source_sqlite.exists():
            # Replay the captured submitted record itself when the runtime
            # evidence tree is present.  The copy keeps this test read-only
            # with respect to the real A2 journal; the fallback below keeps
            # the fixture portable when work/runtime is not checked out.
            shutil.copy2(source_sqlite, database)
            return DurableJournal(
                database,
                experiment_id=self.fixture["sources"]["experiment_id"],
                session_id=request["session_id"],
            )
        journal = DurableJournal(
            database,
            experiment_id=self.fixture["sources"]["experiment_id"],
            session_id=request["session_id"],
        )
        journal.register(request["request_id"], {
            "action_id": request["action_id"],
            "actor": request["actor"],
            "recipient": request["recipient"],
            "phase": request["phase"],
            "parameters": request["parameters"],
        })
        for status in ("queued", "consumed", "constructed"):
            journal.transition(request["request_id"], status)
        claim = journal.claim_submission(
            request["request_id"],
            submission_id="native_" + request["request_id"],
        )
        self.assertTrue(claim.claimed)
        journal.mark_submitted(
            request["request_id"], claim.claim_token,
            self.fixture["original_journal"]["receipt"],
        )
        return journal

    def test_real_submission_and_rejected_h_result_are_bound_and_private_safe(self):
        request = self.fixture["request"]
        parameters = request["parameters"]
        submission = self._check_event("submission_event")
        execution = self._check_event("execution_event")
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        public = ObserverSession._public_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters)
        self.assertIsNotNone(public)
        self.assertEqual("h", public["term_mask"])
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(1, public["native_state"])
        self.assertTrue(public["response_verified"])
        self.assertFalse(public["execution_verified"])
        self.assertFalse(public["terms_verified"])
        self.assertTrue(public["war_before"])
        self.assertTrue(public["war_after"])
        effect = public["effects"]["humiliate_rival"]
        self.assertEqual("ENG", effect["country"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertFalse(effect["humiliated_before"])
        self.assertFalse(effect["humiliated_after"])
        self.assertTrue(effect["values_readable"])
        self.assertFalse(effect["verified"])
        self.assertNotIn("session_id", json.dumps(public))
        self.assertNotIn("native_origin", json.dumps(public))

    def test_get_result_reconciles_existing_native_event_without_resubmission(self):
        request = self.fixture["request"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._temporary_session(root)
            journal = self._journal_with_submitted_request(root)
            try:
                tools = DiplomacyTools(journal, session)
                result = tools.get_diplomatic_result(request["request_id"])
                self.assertEqual("rejected", result["status"])
                self.assertEqual("rejected", result["game_outcome"])
                self.assertTrue(result["submitted"])
                self.assertEqual(
                    "rejected", journal.lookup_request(request["request_id"]).status)
                self.assertEqual(
                    "rejected", result["result"]["native_outcome"])
                self.assertEqual("h", result["result"]["term_mask"])
                self.assertEqual(2, len(journal.list_evidence_for_record(
                    journal.lookup_request(request["request_id"]))))
            finally:
                journal.close()

    def test_h_result_with_forged_verified_effect_is_rejected(self):
        request = self.fixture["request"]
        event = json.loads(json.dumps(self.fixture["execution_event"]["event"]))
        event["effects"]["humiliate_rival"]["verified"] = True
        self.assertFalse(ObserverSession._valid_native_peace_execution_result(
            event, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], request["parameters"]))


if __name__ == "__main__":
    unittest.main()
