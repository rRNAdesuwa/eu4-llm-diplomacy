from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC


FIXTURE = (Path(__file__).parent / "fixtures" /
           "r70_country_money_real.json")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_CASES = {
    "release_PIC_money", "release_offer_money",
    "annex_BUR_release_PIC_money",
}


def _empty_execution_inspection() -> dict:
    return {
        "interface_support": {},
        "session": {},
        "acceptance": {},
        "costs": {},
    }


class CountryMoneyR70RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_bounded_and_offline_provenanced(self) -> None:
        self.assertLess(FIXTURE.stat().st_size, 1 * 1024 * 1024)
        self.assertEqual("r70_country_money_real_v1",
                         self.fixture["schema"])
        source = self.fixture["offline_source"]
        self.assertTrue(source["source_report"].endswith("report.json"))
        self.assertEqual(_CASES, set(source["selection"]))
        self.assertEqual(_CASES,
                         {case["name"] for case in self.fixture["cases"]})
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assertNotIn("public", case)
                self.assertEqual(
                    case["event"]["event"], case["source"]["event"])
                self.assertTrue(case["source"]["path"].endswith(
                    "native-event.json"))
                self.assertGreater(case["source"]["bytes"], 0)
                self.assertRegex(case["source"]["sha256"], _HEX64)
                self.assertEqual(case["event"]["war_id"],
                                 case["parameters"]["peace_context"]
                                 ["war_id"])
                self.assertEqual(case["event"]["direction"],
                                 case["parameters"]["peace_context"]
                                 ["direction"])

    def test_raw_country_money_records_validate_and_project(self) -> None:
        for case in self.fixture["cases"]:
            event = case["event"]
            expected = case["expected_selection"]
            with self.subTest(case=case["name"]):
                self.assertTrue(
                    ObserverSession._valid_native_peace_combined_country_offer_query(
                        event, event["action_id"], event["actor"],
                        event["recipient"], event["phase"], event["date_raw"],
                        expected, event["query_id"], event["session_id"],
                    ))

                money = event["native_money"]
                self.assertEqual(1000, money["requested_amount_raw"])
                self.assertEqual(1000, money["source_amount_raw"])
                self.assertEqual(1000, money["action_amount_raw"])
                self.assertEqual(event["direction"], money["direction"])
                release = event["native_country_terms"]["release_nation"]
                self.assertEqual(1, release["selected_term_count"])
                self.assertTrue(release["selection_applied"])

                projected = ObserverSession._semantic_peace_combined_country_offer_query(
                    event, EU4_ESCAPE_CODEC)
                self.assertEqual(event["term_mask"], projected["term_mask"])
                public_money = projected["native_money"]
                self.assertEqual(1000, public_money["requested_amount_raw"])
                self.assertEqual(event["direction"], public_money["direction"])
                public_release = projected["native_country_terms"][
                    "release_nation"]
                selected = [row for row in public_release["candidates"]
                            if row["selected"]]
                self.assertEqual(1, len(selected))
                self.assertEqual(expected["release_nation_country"],
                                 selected[0]["country"])
                self.assertEqual(expected["release_nation_source"],
                                 selected[0]["source"])

                if case["name"] == "annex_BUR_release_PIC_money":
                    annex = event["native_annexation"]
                    self.assertEqual(23, annex["candidate_count"])
                    self.assertEqual(9, annex["candidate_match_count"])
                    self.assertEqual(11, annex["target_owned_count"])
                    self.assertFalse(annex["selection_applied"])
                    self.assertFalse(event["native_evaluation"]["called"])
                    self.assertFalse(projected["parameters_matched"])
                    self.assertEqual([], projected["peace_context"]["terms"])
                    self.assertFalse(projected["peace_consequences"]
                                     ["requested_terms_applied"])
                else:
                    self.assertTrue(projected["parameters_matched"])
                    self.assertTrue(projected["parameters_complete"])
                    self.assertTrue(projected["peace_consequences"]
                                    ["requested_terms_applied"])

    def test_full_execution_projection_preserves_both_money_directions(self) -> None:
        for name in ("release_PIC_money", "release_offer_money"):
            case = next(case for case in self.fixture["cases"]
                        if case["name"] == name)
            event = case["event"]
            projected = ObserverSession._semantic_peace_combined_country_offer_query(
                event, EU4_ESCAPE_CODEC)
            execution = DiplomacyTools._apply_peace_execution_inspection(
                _empty_execution_inspection(), projected, case["parameters"])

            with self.subTest(case=name):
                self.assertEqual(
                    "native_peace_execution_inspection",
                    execution["interface_support"]["query"])
                self.assertEqual(case["parameters"],
                                 execution["parameters"]["requested"])
                self.assertEqual(case["parameters"],
                                 execution["parameters"]["actual"])
                self.assertEqual(case["parameters"]["peace_context"]["terms"],
                                 execution["peace_context"]["terms"])
                self.assertEqual(1000, execution["native_money"]
                                 ["requested_amount_raw"])
                self.assertEqual(event["direction"],
                                 execution["native_money"]["direction"])
                self.assertTrue(execution["peace_consequences"]
                                ["requested_terms_applied"])
                self.assertIn("native_country", execution["costs"])
                self.assertIn("native_evaluation", execution["costs"])
                self.assertNotIn("frame_thread", json.dumps(execution))

    def test_unapplied_annex_companion_stays_valid_without_runtime_error(self) -> None:
        case = next(case for case in self.fixture["cases"]
                    if case["name"] == "annex_BUR_release_PIC_money")
        event = case["event"]
        projected = ObserverSession._semantic_peace_combined_country_offer_query(
            event, EU4_ESCAPE_CODEC)
        execution = DiplomacyTools._apply_peace_execution_inspection(
            _empty_execution_inspection(), projected, case["parameters"])

        self.assertFalse(event["native_annexation"]["selection_applied"])
        self.assertFalse(event["native_evaluation"]["called"])
        self.assertFalse(projected["parameters_matched"])
        self.assertIsNone(execution["parameters"]["actual"])
        self.assertFalse(execution["parameters"]["complete"])
        consequences = execution["peace_consequences"]
        self.assertFalse(consequences["requested_terms_applied"])
        self.assertEqual("NATIVE_PEACE_REQUESTED_TERMS_NOT_APPLIED",
                         consequences["reason_code"])
        self.assertFalse(execution["acceptance"]["prediction_available"])
        self.assertFalse(execution["acceptance"]["details_available"])
        self.assertFalse(execution["costs"]["native_evaluation"]
                         ["aggregate_score_available"])

        reasons = execution["legality"]["reasons"]
        self.assertTrue(reasons)
        self.assertTrue(all(reason.get("source") != "runtime_error"
                            for reason in reasons))
        self.assertTrue(all(not reason["code"].startswith("QUERY_")
                            for reason in reasons))


if __name__ == "__main__":
    unittest.main()
