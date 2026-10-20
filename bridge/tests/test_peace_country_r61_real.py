from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import (
    COUNTRY_SELECTION_KEYS,
    DiplomacyTools,
    ObserverSession,
)
from bridge.native_text import EU4_ESCAPE_CODEC


FIXTURE = Path(__file__).parent / "fixtures" / "peace_country_r61_real.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _FixtureCountrySession:
    """Replay a stored QUERY18 event through the public query route."""

    def __init__(self, event: dict):
        self.event = event

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": "r61-country-fixture",
            "date_raw": self.event["date_raw"],
            "reasons": [],
            "complete": True,
        }

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({"native_peace_country_terms_query"})

    def inspect_peace_execution(self, action_id: str, actor: str,
                                recipient: str, phase: str,
                                parameters: dict) -> dict:
        return ObserverSession._semantic_peace_combined_country_offer_query(
            copy.deepcopy(self.event), EU4_ESCAPE_CODEC)


def _seed_inspection() -> dict:
    return {
        "interface_support": {},
        "costs": {"status": "unknown", "items": [], "complete": False},
        "session": {},
        "acceptance": {
            "applicability": "applicable",
            "prediction_available": False,
            "native_total": None,
            "unit": "unknown",
            "scale_verified": False,
            "predicted_response": "unknown",
            "details_available": False,
            "items": [],
            "complete": False,
        },
    }


class PeaceCountryR61RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    @staticmethod
    def _expected_selection(case: dict) -> dict:
        request = case["input"]
        parameters = request["parameters"]
        actor = case["event"]["actor"]
        recipient = case["event"]["recipient"]
        fields = ObserverSession._peace_execution_fields(parameters)
        country_fields = ObserverSession._peace_country_execution_fields(
            parameters, actor, recipient)
        assert fields is not None and country_fields is not None
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, trade_power_source,
         trade_power_beneficiary, concede_country, concede_beneficiary,
         annul_country, annul_partners, term_mask) = fields
        expected = {
            "action_id": request["action_id"],
            "war_id": war_id,
            "direction": direction,
            "amount_raw": amount_raw,
            "province_ids": list(province_ids),
            "beneficiary": beneficiary,
            "source": trade_power_source if "t" in term_mask else "-",
            "payer": reparations_payer,
            "claimant": reparations_claimant,
            "conceding_country": concede_country,
            "concede_beneficiary": concede_beneficiary,
            "annul_country": annul_country or "-",
            "annul_partners": list(annul_partners or []),
            "term_mask": term_mask,
            "return_ids": [],
            "return_core_owner": None,
            "revoke_ids": [],
            "revoke_core_owner": None,
            "release_countries": [],
            "transfer_countries": [],
        }
        expected.update(dict(zip(COUNTRY_SELECTION_KEYS, country_fields)))
        # The compact discovery input has an empty ``terms`` list, while the
        # native QUERY18 wire still carries the primary-family mask.  Use the
        # recorded wire value for that case so the replay validates the same
        # native request that produced the event.
        if not expected["term_mask"]:
            expected["term_mask"] = case["event"]["term_mask"]
        return expected

    def _validate(self, case: dict, event: dict | None = None) -> None:
        source = event or case["event"]
        request = case["input"]
        self.assertTrue(
            ObserverSession._valid_native_peace_combined_country_offer_query(
                source, request["action_id"], source["actor"],
                source["recipient"], source["phase"], source["date_raw"],
                self._expected_selection(case), source["query_id"],
                source["session_id"]),
            case["name"],
        )

    def _public_result(self, case: dict) -> dict:
        request = case["input"]
        event = case["event"]
        tools = DiplomacyTools(None, _FixtureCountrySession(event))
        return tools.inspect_diplomatic_action(
            request["action_id"], event["actor"], event["recipient"],
            phase=request.get("phase", event["phase"]),
            parameters=request["parameters"],
        )

    def test_all_real_query_events_validate_and_project(self):
        self.assertEqual(16, len(self.fixture["cases"]))
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                self._validate(case)
                projected = ObserverSession._semantic_peace_combined_country_offer_query(
                    case["event"], EU4_ESCAPE_CODEC)
                self.assertNotIn("frame_thread", json.dumps(projected))
                if "full_annexation" in case["name"]:
                    annex = projected["native_annexation"]
                    self.assertEqual(
                        case["event"]["native_annexation"]["candidate_count"],
                        annex["candidate_count"],
                    )
                    self.assertTrue(all(
                        set(row) == {"province_id", "owner", "beneficiary",
                                     "owner_match", "selected", "readcomplete"}
                        for row in annex["candidates"]
                    ))
                    self.assertNotIn("native_output_country_raw",
                                     json.dumps(projected))
                if case["name"].endswith("-TYR"):
                    self.assertEqual(
                        2, projected["native_selected_rules"]["selected_term_count"])
                    self.assertTrue(projected["native_selected_rules"]["complete"])
                if case["name"].endswith("-ENG"):
                    self.assertEqual(
                        43, projected["native_selected_rules"]["selected_term_count"])

    def test_public_reprojection_preserves_candidate_absence_and_rule_result(self):
        expected = {
            "grant_independence-demand-selected": "unavailable",
            "grant_independence-offer-selected": "unavailable",
            "full_annexation-demand-TYR": "available",
            "full_annexation-demand-ENG": "unavailable",
            "full_annexation-offer-AUV": "unavailable",
            "full_annexation-offer-AMG": "unavailable",
        }
        for case in self.fixture["cases"]:
            result = self._public_result(case)
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    case["expected"]["legality"], result["legality"]["status"])
                self.assertNotEqual(
                    "QUERY_NATIVE_RESULT_INVALID",
                    result["legality"]["reasons"][0]["code"],
                )
                if case["name"] in expected:
                    self.assertEqual(expected[case["name"]],
                                     result["legality"]["status"])
                if case["name"] in {
                        "grant_independence-demand-selected",
                        "grant_independence-offer-selected"}:
                    self.assertEqual(
                        "NATIVE_PEACE_COUNTRY_CANDIDATE_ABSENT",
                        result["legality"]["reasons"][0]["code"],
                    )
                    self.assertTrue(result["legality"]["complete"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                if "full_annexation" in case["name"]:
                    self.assertIn("native_annexation", result)
                    self.assertEqual(
                        case["expected"]["legality"] == "available",
                        result["parameters"]["complete"],
                    )

    def test_discovery_is_not_a_selected_white_peace_prediction(self):
        for case in self.fixture["cases"]:
            if case["input"]["parameters"]["peace_context"]["terms"]:
                continue
            with self.subTest(case=case["name"]):
                result = self._public_result(case)
                self.assertEqual("unknown", result["legality"]["status"])
                self.assertEqual([], result["peace_context"]["terms"])
                self.assertFalse(result["parameters"]["complete"])
                self.assertFalse(result["acceptance"]["prediction_available"])

    def test_tampered_real_records_are_rejected(self):
        grant = next(case for case in self.fixture["cases"]
                     if case["name"] == "grant_independence-demand-selected")
        wrong_grant = copy.deepcopy(grant["event"])
        wrong_grant["native_country_terms"]["grant_independence"][
            "requested_country"] = "FRA"
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_country_offer_query(
                wrong_grant, grant["input"]["action_id"],
                wrong_grant["actor"], wrong_grant["recipient"],
                wrong_grant["phase"], wrong_grant["date_raw"],
                self._expected_selection(grant), wrong_grant["query_id"],
                wrong_grant["session_id"]))

        annex = next(case for case in self.fixture["cases"]
                     if case["name"] == "full_annexation-demand-TYR")
        wrong_annex = copy.deepcopy(annex["event"])
        wrong_annex["native_annexation"]["candidate_match_count"] += 1
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_country_offer_query(
                wrong_annex, annex["input"]["action_id"],
                wrong_annex["actor"], wrong_annex["recipient"],
                wrong_annex["phase"], wrong_annex["date_raw"],
                self._expected_selection(annex), wrong_annex["query_id"],
                wrong_annex["session_id"]))

        large = next(case for case in self.fixture["cases"]
                     if case["name"] == "full_annexation-demand-ENG")
        wrong_rules = copy.deepcopy(large["event"])
        wrong_rules["native_selected_rules"]["selected_term_count"] = 18
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_country_offer_query(
                wrong_rules, large["input"]["action_id"],
                wrong_rules["actor"], wrong_rules["recipient"],
                wrong_rules["phase"], wrong_rules["date_raw"],
                self._expected_selection(large), wrong_rules["query_id"],
                wrong_rules["session_id"]))


if __name__ == "__main__":
    unittest.main()
