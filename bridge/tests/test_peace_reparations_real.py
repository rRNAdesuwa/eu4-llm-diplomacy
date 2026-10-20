import hashlib
import json
import re
import unittest
from pathlib import Path

from bridge.diplomacy import ObserverSession


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_r49_reparations_real_events.json")


class PeaceReparationsR49RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_preserves_source_paths_and_build_identity(self):
        self.assertEqual(1, self.fixture["fixture_version"])
        sources = self.fixture["sources"]
        self.assertEqual(
            "fbbfbc0bea94206859f22257a58fa9605872d2fb289e9f39bd9bf54a048b8fa1",
            sources["a"]["dll_sha256"])
        for name in ("a", "c", "d", "e"):
            source = sources[name]
            for key in ("artifact_root", "build_manifest_path",
                        "build_manifest_sha256", "dll_sha256", "session_id"):
                self.assertTrue(source.get(key), (name, key))
                if key.endswith("sha256"):
                    self.assertRegex(source[key], r"^[0-9a-f]{64}$")
        for case in self.fixture["cases"]:
            self.assertTrue(case["source_ref"])
            line_numbers = case.get("source_lines", [case.get("source_line")])
            line_hashes = case.get("source_line_sha256", [])
            if not isinstance(line_hashes, list):
                line_hashes = [line_hashes]
            self.assertEqual(len(line_numbers), len(line_hashes), case["name"])
            for line, digest in zip(line_numbers, line_hashes):
                self.assertIsInstance(line, int)
                self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_a_real_outbound_submission_and_rejected_execution(self):
        case = next(item for item in self.fixture["cases"]
                    if item["name"] == "a_outbound_reparations_rejected")
        request = case["request"]
        params = request["parameters"]
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            case["submission_event"], request["request_id"],
            request["session_id"], request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params))
        receipt = ObserverSession._public_native_peace_submission_receipt(
            case["submission_event"], request["request_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertEqual("native_peace_submission_result", receipt["event"])
        self.assertEqual("r", receipt["term_mask"])
        self.assertEqual("ENG", receipt["reparations_payer"])
        self.assertEqual("FRA", receipt["reparations_claimant"])

        execution = case["execution_event"]
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params))
        public = ObserverSession._public_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(1, public["native_state"])
        self.assertFalse(public["terms_verified"])
        self.assertFalse(public["effects"]["war_reparations"]["active_before"])
        self.assertFalse(public["effects"]["war_reparations"]["active_after"])
        self.assertFalse(public["effects"]["war_reparations"]["verified"])

    def test_c_real_pending_and_accept_reject_inspections(self):
        pending_case = next(item for item in self.fixture["cases"]
                            if item["name"] == "c_pending_reparations_offer")
        pending = pending_case["event"]
        self.assertEqual("ENG", pending["actor"])
        self.assertEqual("FRA", pending["recipient"])
        self.assertTrue(pending["queue_readable"])
        self.assertEqual("native_executor_pending_block",
                         pending["pending_source"])
        self.assertTrue(ObserverSession._safe_public_peace_value(
            pending["peace"]))

        inspection_cases = [item for item in self.fixture["cases"]
                            if item["name"].startswith("c_")
                            and item["name"].endswith("inspection")]
        self.assertEqual({"accept", "reject"},
                         {item["event"]["phase"] for item in inspection_cases})
        for case in inspection_cases:
            event = case["event"]
            self.assertTrue(ObserverSession._valid_native_inbound_inspection(
                event, event["query_id"], event["session_id"], event["actor"],
                event["phase"], event["native_proposal_id"], event["date_raw"],
                "peace_offer"))
            public = ObserverSession._public_native_inbound_inspection(
                event, event["date_raw"], "peace_offer")
            self.assertEqual("ENG", public["actor"])
            self.assertEqual("FRA", public["recipient"])
            self.assertEqual("war_reparations",
                             public["peace_context"]["terms"][0]["action_id"])
            self.assertEqual("available", case["public_result"]["legality_status"])
            self.assertEqual("available",
                             case["public_result"]["authorization_status"])

    def test_d_real_rejected_response_accepts_false_false_reparations_effect(self):
        case = next(item for item in self.fixture["cases"]
                    if item["name"] == "d_inbound_reparations_rejected")
        inspection = case["inspection_event"]
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            "peace_offer"))
        submission = case["submission_event"]
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"], submission["phase"],
            submission["date_raw"], 1, "peace_offer"))
        response = case["response_event"]
        public = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            1, "peace_offer")
        self.assertIsNotNone(public)
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(1, public["native_state"])
        self.assertTrue(public["pending_removed"])
        self.assertTrue(public["war_before"])
        self.assertTrue(public["war_after"])
        self.assertFalse(public["terms_verified"])
        reparations = public["effects"]["war_reparations"]
        self.assertEqual("FRA", reparations["payer"])
        self.assertEqual("ENG", reparations["claimant"])
        self.assertFalse(reparations["active_before"])
        self.assertFalse(reparations["active_after"])
        self.assertEqual(0, reparations["start_date_raw"])
        self.assertEqual(0, reparations["end_date_raw"])
        self.assertFalse(reparations["verified"])

    def test_e_real_accepted_response_projects_verified_reparations_effect(self):
        case = next(item for item in self.fixture["cases"]
                    if item["name"] == "e_inbound_reparations_accepted")
        inspection = case["inspection_event"]
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            "peace_offer"))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], "peace_offer")
        self.assertEqual("ENG", public_inspection["actor"])
        self.assertEqual("FRA", public_inspection["recipient"])
        self.assertEqual("ENG",
                         public_inspection["peace_context"]["original_actor"])
        self.assertEqual("FRA",
                         public_inspection["peace_context"]["original_recipient"])
        self.assertEqual("war_reparations",
                         public_inspection["peace_context"]["terms"][0]["action_id"])

        submission = case["submission_event"]
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"], submission["phase"],
            submission["date_raw"], 1, "peace_offer"))

        response = case["response_event"]
        public = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            1, "peace_offer")
        self.assertIsNotNone(public)
        self.assertEqual("accepted", public["native_outcome"])
        self.assertEqual(2, public["native_state"])
        self.assertTrue(public["pending_removed"])
        self.assertTrue(public["war_before"])
        self.assertFalse(public["war_after"])
        self.assertTrue(public["terms_verified"])
        self.assertEqual("ENG", public["peace_context"]["original_actor"])
        self.assertEqual("FRA", public["peace_context"]["original_recipient"])
        reparations = public["effects"]["war_reparations"]
        self.assertEqual("FRA", reparations["payer"])
        self.assertEqual("ENG", reparations["claimant"])
        self.assertFalse(reparations["active_before"])
        self.assertTrue(reparations["active_after"])
        self.assertEqual(56545080, reparations["start_date_raw"])
        self.assertEqual(56632680, reparations["end_date_raw"])
        self.assertTrue(reparations["verified"])

        provenance = case["public_result"]
        self.assertEqual("accepted", provenance["status"])
        self.assertEqual(provenance["native_outcome"], public["native_outcome"])
        self.assertEqual(provenance["native_state"], public["native_state"])
        self.assertEqual(provenance["reparations_payer"], reparations["payer"])
        self.assertEqual(provenance["reparations_claimant"], reparations["claimant"])
        self.assertEqual(provenance["start_date_raw"], reparations["start_date_raw"])
        self.assertEqual(provenance["end_date_raw"], reparations["end_date_raw"])
        self.assertTrue(provenance["verified"])


if __name__ == "__main__":
    unittest.main()
