from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_country_r61_combined_rejected_real.json")


class PeaceCountryR61CombinedRejectedRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.request = cls.fixture["request"]
        cls.events = cls.fixture["events"]

    def _source_path(self, entry: dict) -> Path:
        return ROOT / Path(entry["path"])

    def _assert_event_source(self, name: str) -> dict:
        source = self.fixture["sources"]["events"]
        path = self._source_path(source)
        self.assertTrue(path.is_file(), path)
        self.assertEqual(source["size"], path.stat().st_size)
        self.assertEqual(source["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        line_meta = next(
            row for row in source["line_records"]
            if row["event"] == self.events[name]["event"])
        raw = path.read_bytes().splitlines()[line_meta["line"] - 1]
        self.assertEqual(line_meta["bytes"], len(raw))
        self.assertEqual(line_meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        self.assertEqual(self.events[name], event)
        return event

    @staticmethod
    def _assert_public_private_fields_absent(value: object) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        for marker in ("session_id", "native_origin", "native_flags",
                       "native_sequence", "query_id", "frame_thread",
                       "token3c", "date28", "date2c"):
            if marker in serialized:
                raise AssertionError(f"private marker leaked: {marker}")

    def test_fixture_source_manifest_binds_original_control_lines(self):
        source = self.fixture["sources"]["events"]
        original = source["original_control_log"]
        self.assertEqual([6795, 6839], original["source_lines"])
        self.assertEqual(
            "f1f1c62c394d0f37ce7cc1d8296dff390a9728f568975bc9f62d52bb80875729",
            original["selected_source_sha256"])
        submission = self._assert_event_source("submission")
        execution = self._assert_event_source("execution")
        self.assertEqual(submission["request_id"], self.request["request_id"])
        self.assertEqual(execution["request_id"], self.request["request_id"])

    def test_real_receipt_two_layer_projection_and_submission_context(self):
        request = self.request
        event = self._assert_event_source("submission")
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            event, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            event["date_raw"], request["action_id"], request["parameters"]))

        native_public = ObserverSession._public_native_peace_submission_receipt(
            event, request["request_id"], request["actor"],
            request["recipient"], request["phase"], event["date_raw"],
            request["action_id"], request["parameters"])
        self.assertIsNotNone(native_public)
        assert native_public is not None
        self.assertTrue(native_public["submitted"])
        self.assertEqual("ne", native_public["term_mask"])
        self.assertEqual("FLY", native_public["release_nation_country"])
        self.assertEqual("ENG", native_public["release_nation_source"])
        self.assertEqual("TYR", native_public["annex_country"])
        self.assertEqual("FRA", native_public["annex_beneficiary"])
        self.assertNotIn("session_id", native_public)

        public = DiplomacyTools._public_peace_submission_receipt(
            native_public, request["request_id"], request["actor"],
            request["recipient"], request["phase"], event["date_raw"],
            request["action_id"], request["parameters"])
        self.assertEqual(native_public, public)

        record = SimpleNamespace(
            payload={
                "action_id": request["action_id"],
                "actor": request["actor"],
                "recipient": request["recipient"],
                "phase": request["phase"],
                "parameters": request["parameters"],
            },
            native_receipt=public,
            request_id=request["request_id"],
            session_id=request["session_id"],
        )
        context = DiplomacyTools._native_submission_context(record)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(
            ("FRA", "ENG", "initiate", event["date_raw"]), context[:4])
        self.assertEqual(
            request["parameters"]["peace_context"],
            context[4]["peace_context"])
        self._assert_public_private_fields_absent(public)

        forged = copy.deepcopy(native_public)
        forged["annex_beneficiary"] = "ENG"
        self.assertIsNone(DiplomacyTools._public_peace_submission_receipt(
            forged, request["request_id"], request["actor"],
            request["recipient"], request["phase"], event["date_raw"],
            request["action_id"], request["parameters"]))

    def test_real_rejected_execution_public_projection_and_effect_binding(self):
        request = self.request
        event = self._assert_event_source("execution")
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            event, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            event["date_raw"], request["action_id"], request["parameters"]))
        public = ObserverSession._public_native_peace_execution_result(
            event, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            event["date_raw"], request["action_id"], request["parameters"])
        self.assertIsNotNone(public)
        assert public is not None
        expected = self.fixture["expected"]
        self.assertEqual(expected["native_state"], public["native_state"])
        self.assertEqual(expected["native_outcome"], public["native_outcome"])
        self.assertEqual(expected["term_mask"], public["term_mask"])
        self.assertFalse(public["execution_verified"])
        self.assertFalse(public["terms_verified"])
        self.assertTrue(public["response_verified"])
        self.assertEqual(
            expected["selected_country_terms"]["release_nation"]["country"],
            public["release_nation_country"])
        self.assertEqual(
            expected["selected_country_terms"]["release_nation"]["source"],
            public["release_nation_source"])
        self.assertEqual(
            expected["selected_country_terms"]["full_annexation"]["country"],
            public["annex_country"])
        self.assertEqual(
            expected["selected_country_terms"]["full_annexation"]["beneficiary"],
            public["annex_beneficiary"])
        country_terms = public["effects"]["country_terms"]
        self.assertTrue(country_terms["release_nation"]["unchanged"])
        self.assertFalse(country_terms["release_nation"]["verified"])
        self.assertTrue(country_terms["full_annexation"]["unchanged"])
        self.assertFalse(country_terms["full_annexation"]["verified"])
        self._assert_public_private_fields_absent(public)

        forged = copy.deepcopy(event)
        forged["annex_beneficiary"] = "ENG"
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            forged, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            event["date_raw"], request["action_id"], request["parameters"]))

    def test_replays_invalidated_sqlite_as_rejected_without_execute(self):
        request = self.request
        submission = self._assert_event_source("submission")
        execution = self._assert_event_source("execution")
        receipt = ObserverSession._public_native_peace_submission_receipt(
            submission, request["request_id"], request["actor"],
            request["recipient"], request["phase"], submission["date_raw"],
            request["action_id"], request["parameters"])
        result = ObserverSession._public_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            execution["date_raw"], request["action_id"], request["parameters"])
        self.assertIsNotNone(receipt)
        self.assertIsNotNone(result)
        assert receipt is not None and result is not None

        source_db = self._source_path(
            self.fixture["sources"]["journal_before_reconciliation"])
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / "diplomacy.sqlite3"
            shutil.copy2(source_db, db)
            with DurableJournal(
                    db, self.fixture["request"]["experiment_id"],
                    request["session_id"], global_request_ids=True) as journal:
                before = journal.get_request(request["request_id"])
                self.assertEqual("invalidated", before.status)
                reconciled = journal.reconcile_rejected(
                    request["request_id"], result, receipt,
                    expected_reason_code=self.fixture["expected"]["reason_code"],
                    expected_payload={
                        "action_id": request["action_id"],
                        "actor": request["actor"],
                        "recipient": request["recipient"],
                        "phase": request["phase"],
                        "parameters": request["parameters"],
                    },
                    evidence_content={
                        "reconciled_from": "invalidated",
                        "native_receipt": receipt,
                        "native_response": result,
                    },
                    event_id="r61-real-reconcile-test:" + request["request_id"],
                )
                self.assertEqual("rejected", reconciled.status)
                recovered = DiplomacyTools(journal, None).get_diplomatic_result(
                    request["request_id"])
        self.assertEqual("rejected", recovered["status"])
        self.assertTrue(recovered["submitted"])
        self.assertEqual("rejected", recovered["game_outcome"])
        self.assertEqual(result, recovered["result"])
        self.assertEqual("ne", recovered["result"]["term_mask"])
        self.assertEqual(1, recovered["result"]["native_state"])


if __name__ == "__main__":
    unittest.main()
