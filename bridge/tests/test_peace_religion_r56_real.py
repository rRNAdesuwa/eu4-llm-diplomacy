from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_religion_r56_real.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PeaceReligionR56RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    def _source_path(self, name: str) -> Path:
        return REPOSITORY_ROOT / self.fixture["sources"][name]["path"]

    def _assert_source_hash(self, name: str) -> None:
        source = self.fixture["sources"][name]
        path = self._source_path(name)
        self.assertTrue(path.is_file(), path)
        self.assertEqual(source["size"], path.stat().st_size)
        self.assertEqual(source["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def _assert_event_source(self, name: str) -> dict[str, object]:
        record = self.fixture[name]
        self._assert_source_hash("native_events")
        raw = self._source_path("native_events").read_bytes().splitlines()[
            record["source_line"] - 1]
        self.assertEqual(record["source_line_bytes"], len(raw))
        self.assertEqual(record["source_line_sha256"],
                         hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        self.assertEqual(record["event"], event)
        return event

    def _inbound_source_path(self, source_name: str, name: str) -> Path:
        return (REPOSITORY_ROOT /
                self.fixture["inbound_sources"][source_name][name]["path"])

    def _assert_inbound_source_hash(self, source_name: str, name: str) -> None:
        source = self.fixture["inbound_sources"][source_name][name]
        path = self._inbound_source_path(source_name, name)
        self.assertTrue(path.is_file(), path)
        self.assertEqual(source["size"], path.stat().st_size)
        self.assertEqual(source["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def _assert_inbound_event(self, case_name: str,
                              event_name: str) -> dict[str, object]:
        case = self.fixture["inbound_cases"][case_name]
        record = case[event_name]
        source_name = case["source"]
        self._assert_inbound_source_hash(source_name, "native_events")
        raw = self._inbound_source_path(
            source_name, "native_events").read_bytes().splitlines()[
                record["source_line"] - 1]
        self.assertEqual(record["source_line_bytes"], len(raw))
        self.assertEqual(record["source_line_sha256"],
                         hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        self.assertEqual(record["event"], event)
        return event

    @staticmethod
    def _assert_public_private_fields_absent(value: object) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        for marker in ("session_id", "native_proposal_id", "query_id",
                       "token3c", "date28", "date2c", "envoy30",
                       "native_action", "native_node", "proposal3c",
                       "created2c", "treasury_before_raw",
                       "treasury_after_raw"):
            if marker in serialized:
                raise AssertionError(f"private marker leaked: {marker}")

    def test_real_submission_and_rejected_force_religion_bind_leI_roles(self):
        request = self.fixture["request"]
        submission = self._assert_event_source("submission_event")
        execution = self._assert_event_source("execution_event")
        parameters = request["parameters"]

        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        self.assertEqual("force_religion", submission["action_id"])
        self.assertEqual("f", submission["term_mask"])
        self.assertEqual("-", submission["beneficiary"])

        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        public = ObserverSession._public_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters)
        self.assertIsNotNone(public)
        assert public is not None
        expected = self.fixture["expected"]
        self.assertEqual(expected["term_mask"], public["term_mask"])
        self.assertEqual(expected["native_state"], public["native_state"])
        self.assertEqual(expected["native_outcome"], public["native_outcome"])
        self.assertTrue(public["response_verified"])
        self.assertTrue(public["request_binding_verified"])
        self.assertFalse(public["execution_verified"])
        self.assertFalse(public["terms_verified"])
        self.assertTrue(public["war_before"])
        self.assertTrue(public["war_after"])
        self.assertEqual(
            [{"action_id": "force_religion", "country": "LEI",
              "beneficiary": "FRA"}], public["special_terms"])
        self.assertEqual(expected["force_religion"],
                         public["effects"]["force_religion"])
        effect = public["effects"]["force_religion"]
        self.assertEqual("LEI", effect["country"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertTrue(effect["values_readable"])
        self.assertFalse(effect["verified"])
        self.assertEqual("hussite", effect["religion_before"])
        self.assertEqual("hussite", effect["religion_after"])
        self.assertEqual("catholic", effect["beneficiary_religion_after"])
        self.assertEqual("hussite", effect["capital_religion_after"])
        self.assertNotIn("session_id", json.dumps(public, ensure_ascii=False))
        self.assertNotIn("native_origin", json.dumps(public, ensure_ascii=False))

    def test_rejects_noncanonical_religion_identifiers(self):
        request = self.fixture["request"]
        execution = self.fixture["execution_event"]["event"]
        forged = copy.deepcopy(execution)
        forged["effects"]["force_religion"]["religion_after"] = "catholic!"
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            forged, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], request["parameters"]))

        forged = copy.deepcopy(execution)
        forged["effects"]["force_religion"]["religion_after"] = 5
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            forged, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], request["parameters"]))

    def test_replays_late_native_rejection_from_copied_sqlite_without_execute(self):
        request = self.fixture["request"]
        execution = self.fixture["execution_event"]["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": self.fixture["sources"]["experiment_id"],
                "session_id": request["session_id"],
                "native_text_codec": self.fixture["sources"]["native_text_codec"],
            }, separators=(",", ":")), encoding="utf-8")
            shutil.copy2(self._source_path("sqlite"), root / "diplomacy.sqlite3")
            # The source operator's late event is copied into a bounded local
            # response log.  This exercises the production result consumer
            # against the original journal and never writes an execute wire.
            (root / "control-probe.jsonl").write_text(
                json.dumps(execution, separators=(",", ":")) + "\n",
                encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            journal = DurableJournal(
                root / "diplomacy.sqlite3",
                experiment_id=self.fixture["sources"]["experiment_id"],
                session_id=request["session_id"],
            )
            try:
                result = DiplomacyTools(journal, session).get_diplomatic_result(
                    request["request_id"])
            finally:
                journal.close()
        self.assertEqual("rejected", result["status"])
        self.assertEqual("rejected", result["game_outcome"])
        self.assertTrue(result["submitted"])
        self.assertEqual("f", result["result"]["term_mask"])
        self.assertEqual(1, result["result"]["native_state"])
        self.assertFalse(result["result"]["execution_verified"])
        self.assertFalse(result["result"]["terms_verified"])
        self.assertEqual(
            self.fixture["expected"]["force_religion"],
            result["result"]["effects"]["force_religion"])

    def test_real_inbound_d_reject_and_e_accept_force_religion(self):
        for source_name in ("d", "e"):
            for name in ("report", "native_events", "installation",
                         "build_manifest", "sqlite", "save_observer"):
                with self.subTest(source=source_name, file=name):
                    self._assert_inbound_source_hash(source_name, name)
            source = self.fixture["inbound_sources"][source_name]
            self.assertEqual(source["dll_sha256"],
                             source["build_manifest_dll_sha256"])

        for case_name in ("d_reject", "e_accept"):
            case = self.fixture["inbound_cases"][case_name]
            inspection = self._assert_inbound_event(
                case_name, "inspection_event")
            submission = self._assert_inbound_event(
                case_name, "submission_event")
            response = self._assert_inbound_event(
                case_name, "response_event")

            self.assertTrue(ObserverSession._valid_native_inbound_inspection(
                inspection, inspection["query_id"], case["session_id"],
                case["actor"], case["phase"], case["native_proposal_id"],
                case["date_raw"], case["action_id"]))
            public_inspection = ObserverSession._public_native_inbound_inspection(
                inspection, case["date_raw"], case["action_id"])
            context = public_inspection["peace_context"]
            self.assertTrue(context["complete"])
            self.assertTrue(context["selected_terms_complete"])
            self.assertEqual(case["peace_context"], context)
            self.assertEqual(18, inspection["term_count"])
            self.assertEqual(2, inspection["selected_term_count"])
            self.assertEqual([{
                "action_id": "force_religion",
                "country": "LEI",
                "beneficiary": "FRA",
            }], context["terms"])

            self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
                submission, case["request_id"], case["session_id"],
                case["actor"], case["recipient"], case["phase"],
                case["date_raw"], case["native_proposal_id"],
                case["action_id"]))
            public_submission = ObserverSession._public_native_inbound_submission_receipt(
                submission, case["request_id"], case["actor"],
                case["phase"], case["date_raw"], case["action_id"])
            public_result = ObserverSession._public_native_inbound_response_result(
                response, case["request_id"], case["session_id"],
                case["actor"], case["phase"], case["date_raw"],
                case["native_proposal_id"], case["action_id"])
            self.assertIsNotNone(public_submission)
            self.assertIsNotNone(public_result)
            assert public_result is not None
            expected = case["expected"]
            self.assertEqual(expected["native_state"],
                             public_result["native_state"])
            self.assertEqual(expected["native_outcome"],
                             public_result["native_outcome"])
            self.assertEqual(expected["pending_removed"],
                             public_result["pending_removed"])
            self.assertEqual(expected["terms_verified"],
                             public_result["terms_verified"])
            self.assertTrue(public_result["response_verified"])
            self.assertTrue(public_result["request_binding_verified"])
            self.assertEqual(expected["war_before"],
                             public_result["war_before"])
            self.assertEqual(expected["war_after"],
                             public_result["war_after"])
            self.assertEqual(case["peace_context"],
                             public_result["peace_context"])

            effect = public_result["effects"]["force_religion"]
            self.assertEqual(expected["effects"], effect)
            self.assertEqual("LEI", effect["country"])
            self.assertEqual("FRA", effect["beneficiary"])
            self.assertTrue(effect["values_readable"])
            self.assertEqual(
                case_name == "e_accept", effect["verified"])
            if case_name == "e_accept":
                self.assertEqual("catholic", effect["religion_after"])
                self.assertEqual("catholic",
                                 effect["capital_religion_after"])
                self.assertEqual("catholic",
                                 effect["beneficiary_religion_after"])
            else:
                self.assertEqual("hussite", effect["religion_after"])
                self.assertEqual("hussite",
                                 effect["capital_religion_after"])
                self.assertEqual("catholic",
                                 effect["beneficiary_religion_after"])
            self._assert_public_private_fields_absent({
                "inspection": public_inspection,
                "submission": public_submission,
                "result": public_result,
            })

    def test_forged_inbound_force_religion_effects_are_rejected(self):
        for case_name in ("d_reject", "e_accept"):
            case = self.fixture["inbound_cases"][case_name]
            response = copy.deepcopy(case["response_event"]["event"])
            if case_name == "d_reject":
                response["effects"]["force_religion"]["verified"] = True
            else:
                response["effects"]["force_religion"]["beneficiary"] = "LEI"
            self.assertIsNone(ObserverSession._public_native_inbound_response_result(
                response, case["request_id"], case["session_id"],
                case["actor"], case["phase"], case["date_raw"],
                case["native_proposal_id"], case["action_id"]))

    def test_real_fixture_manifest_and_original_timeout_are_recorded(self):
        for name in ("report", "native_events", "installation", "build_manifest",
                     "dll", "sqlite", "save_observer"):
            with self.subTest(source=name):
                self._assert_source_hash(name)
        self.assertEqual(self.fixture["sources"]["dll_sha256"],
                         self.fixture["sources"]["build_manifest_dll_sha256"])
        report = json.loads(self._source_path("report").read_text(encoding="utf-8"))
        self.assertEqual("unknown", report["status"])
        self.assertEqual(1, report["execute_call_count"])
        self.assertTrue(report["business_submission"])


if __name__ == "__main__":
    unittest.main()
