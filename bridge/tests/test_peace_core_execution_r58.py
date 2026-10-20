from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.peace_execution import normalize_peace_execution_parameters


FIXTURE = (Path(__file__).parent / "fixtures" / "peace_core_r58_real.json")


class PeaceCoreExecutionR58Tests(unittest.TestCase):
    def test_query14_only_installation_does_not_send_mixed_query15(self):
        class LegacySession:
            def health(self):
                return {"status": "ready", "state_id": "legacy_core", "date_raw": 56549064,
                        "reasons": [], "complete": True}

            def installation_capabilities(self):
                return frozenset({"native_peace_core_terms_query"})

            def inspect_peace_execution(self, *args):
                raise AssertionError("QUERY15 was not acknowledged by this installation")

        result = DiplomacyTools(None, LegacySession()).inspect_diplomatic_action(
            "return_core", "FRA", "ENG", parameters=self.request["parameters"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("unimplemented", result["interface_support"]["execute"])

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE.exists():
            raise unittest.SkipTest("R58 real QUERY15 fixture is not present")
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.request = cls.fixture["request"]
        cls.report = {"parameters": {"requested": cls.request["parameters"]}}
        cls.event = cls.fixture["query_event"]
        cls.submission = cls.fixture["submission_event"]
        cls.execution = cls.fixture["execution_event"]

    @staticmethod
    def _selection_for(event: dict) -> dict:
        nested = event["native_core_terms"]
        return {
            "action_id": event["action_id"],
            "war_id": event["war_id"],
            "direction": event["direction"],
            "amount_raw": event["native_money"]["requested_amount_raw"],
            "province_ids": [],
            "beneficiary": None,
            "source": "-",
            "payer": "ENG",
            "claimant": "FRA",
            "term_mask": event["term_mask"],
            "annul_country": "-",
            "annul_partners": [],
            "return_ids": list(
                nested["return_core"]["requested_province_ids"]),
            "return_core_owner": nested["return_core"]["requested_core_owner"],
            "revoke_ids": list(
                nested["revoke_core"]["requested_province_ids"]),
            "revoke_core_owner": nested["revoke_core"]["requested_core_owner"],
        }

    def _selection(self) -> dict:
        return self._selection_for(self.event)

    def test_real_query15_projects_complete_mixed_execution(self):
        report, event = self.report, self.event
        parameters = normalize_peace_execution_parameters(
            "return_core", event["actor"], event["recipient"], "initiate",
            report["parameters"]["requested"])
        self.assertTrue(
            ObserverSession._valid_native_peace_combined_core_offer_query(
                event, "return_core", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], self._selection(),
                event["query_id"], event["session_id"]))

        semantic = ObserverSession._semantic_peace_combined_core_offer_query(
            event)
        self.assertTrue(semantic["parameters_matched"])
        self.assertTrue(semantic["native_return_core"]["parameters_matched"])
        self.assertTrue(semantic["native_revoke_core"]["parameters_matched"])
        public = DiplomacyTools._apply_peace_execution_inspection(
            {"interface_support": {},
             "session": {"date_raw": event["date_raw"]},
             "acceptance": {}, "costs": {}},
            semantic, parameters)

        self.assertEqual("available", public["legality"]["status"])
        self.assertTrue(public["parameters"]["complete"])
        self.assertEqual(-100, public["acceptance"]["native_total"])
        self.assertEqual(10, len(public["acceptance"]["items"]))
        self.assertEqual(
            10, public["native_evaluation"]["factor_native_count"])
        self.assertTrue(public["native_payload"]["serialized_fields_complete"])
        self.assertEqual({"return_core", "revoke_core"},
                         set(public["parameters"]["candidates"]))
        self.assertTrue(public["native_rule_components"]["native_term_gate"])

    def test_query15_nested_core_tampering_is_rejected(self):
        tampered = copy.deepcopy(self.event)
        tampered["native_core_terms"]["revoke_core"][
            "requested_core_owner"] = "FRA"
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_core_offer_query(
                tampered, "return_core", tampered["actor"],
                tampered["recipient"], tampered["phase"],
                tampered["date_raw"], self._selection(),
                tampered["query_id"], tampered["session_id"]))

    def test_query15_two_province_selection_and_bad_rows(self):
        event = copy.deepcopy(self.event)
        nested = event["native_core_terms"]["return_core"]
        nested["requested_province_ids"] = [173, 177]
        nested["selected_term_count"] = 2
        nested["selection_delta_raw"] = 11
        for row in nested["candidates"]:
            if row["province_id"] == 177:
                row["core_owner"] = "AMG"
                row["selected"] = True
        selection = self._selection_for(event)
        self.assertTrue(
            ObserverSession._valid_native_peace_combined_core_offer_query(
                event, "return_core", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], selection,
                event["query_id"], event["session_id"]))

        duplicate = copy.deepcopy(event)
        duplicate["native_core_terms"]["return_core"][
            "requested_province_ids"] = [173, 173]
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_core_offer_query(
                duplicate, "return_core", duplicate["actor"],
                duplicate["recipient"], duplicate["phase"],
                duplicate["date_raw"], selection,
                duplicate["query_id"], duplicate["session_id"]))

        mixed_owner = copy.deepcopy(event)
        mixed = mixed_owner["native_core_terms"]["return_core"]
        mixed["candidates"][1]["core_owner"] = "PRO"
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_core_offer_query(
                mixed_owner, "return_core", mixed_owner["actor"],
                mixed_owner["recipient"], mixed_owner["phase"],
                mixed_owner["date_raw"], selection,
                mixed_owner["query_id"], mixed_owner["session_id"]))

    def test_real_submission_and_rejected_execution_are_consumable(self):
        request = self.request
        parameters = normalize_peace_execution_parameters(
            request["action_id"], request["actor"], request["recipient"],
            request["phase"], request["parameters"])
        submission = self.submission
        execution = self.execution
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        public_submission = ObserverSession._public_native_peace_submission_receipt(
            submission, request["request_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], parameters)
        public_execution = ObserverSession._public_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters)
        self.assertEqual([173], public_submission["return_ids"])
        self.assertEqual([175], public_submission["revoke_ids"])
        self.assertEqual("AMG", public_submission["return_core_owner"])
        self.assertEqual("ENG", public_submission["revoke_core_owner"])
        self.assertEqual("rejected", public_execution["outcome"])
        self.assertTrue(public_execution["effects"]["complete"])
        self.assertFalse(public_execution["effects"]["return_core"][0]["verified"])
        self.assertFalse(public_execution["effects"]["revoke_core"][0]["verified"])
        self.assertNotIn("native_origin", public_submission)
        self.assertNotIn("native_flags", public_submission)

    def test_real_inbound_reject_and_accept_consume_core_context_and_effects(self):
        public_results = {}
        for outcome in ("reject", "accept"):
            case = self.fixture["inbound_responses"][outcome]
            event = case["event"]
            context = event["peace_context"]
            self.assertTrue(ObserverSession._valid_inbound_peace_context(
                context, event["actor"], event["recipient"]))
            fields = ObserverSession._inbound_peace_context_fields(
                context, event["actor"], event["recipient"])
            self.assertIsNotNone(fields)
            assert fields is not None
            self.assertEqual([173], fields["return_core_ids"])
            self.assertEqual("AMG", fields["return_core_owner"])
            self.assertEqual([175], fields["revoke_core_ids"])
            self.assertEqual("ENG", fields["revoke_core_owner"])
            public = ObserverSession._public_native_inbound_response_result(
                event, case["request_id"], event["session_id"],
                event["actor"], event["phase"], event["date_raw"],
                1, "peace_offer")
            self.assertIsNotNone(public)
            assert public is not None
            public_results[outcome] = public
            self.assertEqual(case["expected"]["outcome"],
                             public["native_outcome"])
            self.assertEqual(case["expected"]["native_state"],
                             public["native_state"])
            self.assertEqual(case["expected"]["terms_verified"],
                             public["terms_verified"])
            self.assertEqual(case["expected"]["war_after"],
                             public["war_after"])
            self.assertEqual(
                case["expected"]["return_core_verified"],
                public["effects"]["return_core"][0]["verified"])
            self.assertEqual(
                case["expected"]["revoke_core_verified"],
                public["effects"]["revoke_core"][0]["verified"])
            self.assertNotIn("session_id", public)
            self.assertNotIn("native_proposal_id", public)

        accepted = self.fixture["inbound_responses"]["accept"]
        event = accepted["event"]
        self.assertEqual(1000,
                         public_results["accept"]["effects"]["money"]["paid_raw"])
        self.assertTrue(
            public_results["accept"]["effects"]["war_reparations"]["verified"])
        self.assertEqual("AMG", public_results["accept"]["effects"][
            "return_core"][0]["owner_after"])
        self.assertFalse(public_results["accept"]["effects"][
            "revoke_core"][0]["core_owner_present_after"])

        forged_owner = copy.deepcopy(event)
        forged_owner["effects"]["return_core"][0]["target_core_owner"] = "ENG"
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            forged_owner, accepted["request_id"], event["session_id"],
            event["actor"], event["phase"], event["date_raw"],
            1, "peace_offer"))

        forged_province = copy.deepcopy(event)
        forged_province["effects"]["return_core"][0]["province_id"] = 175
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            forged_province, accepted["request_id"], event["session_id"],
            event["actor"], event["phase"], event["date_raw"],
            1, "peace_offer"))

        missing_effect = copy.deepcopy(event)
        missing_effect["effects"].pop("revoke_core")
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            missing_effect, accepted["request_id"], event["session_id"],
            event["actor"], event["phase"], event["date_raw"],
            1, "peace_offer"))

    def test_mixed_normalizer_returns_canonical_core_wire_order(self):
        context = copy.deepcopy(self.report["parameters"]["requested"])
        context["peace_context"]["terms"] = list(
            reversed(context["peace_context"]["terms"]))
        normalized = normalize_peace_execution_parameters(
            "return_core", "FRA", "ENG", "initiate", context)
        self.assertEqual(
            ["demand_ducats", "war_reparations", "return_core",
             "revoke_core"],
            [term["action_id"]
             for term in normalized["peace_context"]["terms"]])
        self.assertEqual(
            [173], normalized["peace_context"]["terms"][2]["province_ids"])
        self.assertEqual(
            "AMG", normalized["peace_context"]["terms"][2]["core_owner"])
        self.assertEqual(
            [175], normalized["peace_context"]["terms"][3]["province_ids"])
        self.assertEqual(
            "ENG", normalized["peace_context"]["terms"][3]["core_owner"])


if __name__ == "__main__":
    unittest.main()
