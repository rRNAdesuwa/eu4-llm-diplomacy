from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_country_r61_combined_response_real.json")


class PeaceCountryR61CombinedResponseRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        source = cls.fixture["source"]
        cls.source_path = ROOT / Path(source["events_path"])
        cls.source_bytes = cls.source_path.read_bytes()
        cls.source_lines = cls.source_bytes.splitlines()

    def _assert_source(self, case_name: str, event_name: str) -> dict:
        source = self.fixture["source"]
        self.assertTrue(self.source_path.is_file(), self.source_path)
        self.assertEqual(source["events_size"], len(self.source_bytes))
        self.assertEqual(source["events_sha256"],
                         hashlib.sha256(self.source_bytes).hexdigest())
        case = self.fixture["cases"][case_name]
        meta = case["source_lines"][event_name]
        raw = self.source_lines[meta["line"] - 1]
        self.assertEqual(meta["bytes"], len(raw))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        self.assertEqual(case[event_name], event)
        return event

    @staticmethod
    def _assert_no_private(value: object) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        for marker in ("session_id", "query_id", "native_proposal_id",
                       "date28", "date2c", "envoy30", "token3c",
                       "native_origin", "native_flags", "native_sequence"):
            if marker in serialized:
                raise AssertionError(f"private marker leaked: {marker}")

    def _replay_case(self, case_name: str, *, accepted: bool) -> dict:
        case = self.fixture["cases"][case_name]
        inspection = self._assert_source(case_name, "inspection")
        submission = self._assert_source(case_name, "submission")
        response = self._assert_source(case_name, "response")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            inspection["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"],
            submission["phase"], submission["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"]))

        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], inspection["action_id"])
        context = public_inspection["peace_context"]
        self.assertTrue(context["complete"])
        self.assertTrue(context["selected_terms_complete"])
        self.assertEqual(
            [{"action_id": "release_nation", "country": "FLY", "source": "ENG"},
             {"action_id": "full_annexation", "country": "TYR", "beneficiary": "FRA"}],
            context["terms"])
        self.assertFalse(context["full_annex_proof"]["preflight_proof_reused"])

        public_submission = ObserverSession._public_native_inbound_submission_receipt(
            submission, submission["request_id"], submission["actor"],
            submission["phase"], submission["date_raw"],
            inspection["action_id"])
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"])
        self.assertIsNotNone(public_submission)
        self.assertIsNotNone(public_result)
        assert public_result is not None
        expected = case["expected"]
        self.assertEqual(expected["outcome"], public_result["native_outcome"])
        self.assertEqual(expected["native_state"], public_result["native_state"])
        self.assertEqual(expected["war_before"], public_result["war_before"])
        self.assertEqual(expected["war_after"], public_result["war_after"])
        self.assertEqual(expected["terms_verified"], public_result["terms_verified"])
        self.assertEqual(expected["pending_removed"], public_result["pending_removed"])
        result_context = public_result["peace_context"]
        self.assertTrue(result_context["complete"])
        self.assertTrue(result_context["selected_terms_complete"])
        self.assertTrue(result_context["full_annex_proof"]["preflight_proof_reused"])
        self.assertTrue(result_context["full_annex_proof"]["request_identity_matches"])
        self.assertEqual("PREFLIGHT_PROOF_REUSED",
                         result_context["full_annex_proof"]["reason"])

        terms = public_result["effects"]["country_terms"]
        for action_id in ("release_nation", "full_annexation"):
            effect = terms[action_id]
            effect_expected = expected["country_effects"][action_id]
            self.assertEqual(effect_expected["country"], effect["country"])
            self.assertEqual(effect_expected["unchanged"], effect["unchanged"])
            self.assertEqual(effect_expected["verified"], effect["verified"])
            self.assertTrue(effect["complete"])
            self.assertTrue(effect["values_readable"])
        self._assert_no_private({
            "inspection": public_inspection,
            "submission": public_submission,
            "result": public_result,
        })
        return response

    def test_real_reject_and_accept_two_layer_public_projection(self):
        self._replay_case("reject", accepted=False)
        self._replay_case("accept", accepted=True)

    def test_real_response_preflight_reuse_and_effect_binding_reject_tampering(self):
        for case_name in ("reject", "accept"):
            with self.subTest(case=case_name):
                response = self._replay_case(
                    case_name, accepted=case_name == "accept")
                case = self.fixture["cases"][case_name]
                inspection = case["inspection"]
                for label, mutate in (
                        ("proof_identity", lambda event: event[
                            "peace_context"]["full_annex_proof"].update(
                                {"request_identity_matches": False})),
                        ("release_country", lambda event: event["effects"][
                            "country_terms"]["release_nation"].update(
                                {"country": "SCO"})),
                        ("annex_beneficiary", lambda event: event["effects"][
                            "country_terms"]["full_annexation"].update(
                                {"beneficiary": "ENG"}))):
                    forged = copy.deepcopy(response)
                    mutate(forged)
                    with self.subTest(tamper=label):
                        self.assertIsNone(
                            ObserverSession._public_native_inbound_response_result(
                                forged, forged["request_id"],
                                forged["session_id"], forged["actor"],
                                forged["phase"], forged["date_raw"],
                                inspection["native_proposal_id"],
                                inspection["action_id"]))

    def test_source_manifest_retains_distinct_d_and_e_request_lines(self):
        self.assertNotEqual(
            self.fixture["cases"]["reject"]["request_id"],
            self.fixture["cases"]["accept"]["request_id"])
        self.assertEqual(
            self.fixture["cases"]["reject"]["source_lines"]["response"]["line"],
            661)
        self.assertEqual(
            self.fixture["cases"]["accept"]["source_lines"]["response"]["line"],
            2451)
        self.assertEqual("rejected", self.fixture["cases"]["reject"]["expected"]["outcome"])
        self.assertEqual("accepted", self.fixture["cases"]["accept"]["expected"]["outcome"])


if __name__ == "__main__":
    unittest.main()
