from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC


FIXTURE = Path(__file__).parent / "fixtures" / "peace_core_r57_real.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _FixtureCoreSession:
    """Return one stored semantic event through the public query route."""

    def __init__(self, event: dict):
        self.event = event

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": "r57-fixture",
            "date_raw": self.event["date_raw"],
            "reasons": [],
            "complete": True,
        }

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({"native_peace_core_terms_query"})

    def inspect_peace_core_offer(self, action_id: str, actor: str,
                                 recipient: str, phase: str,
                                 selection: dict) -> dict:
        self.assert_selection = selection
        return ObserverSession._semantic_peace_core_offer_query(
            copy.deepcopy(self.event), EU4_ESCAPE_CODEC)


class PeaceCoreR57RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    @staticmethod
    def _selection(case: dict) -> dict:
        request = case["input"]
        context = request["parameters"]["peace_context"]
        terms = context["terms"]
        term = terms[0] if terms else None
        return {
            "action_id": request["action_id"],
            "war_id": context["war_id"],
            "direction": context.get("direction", "demand"),
            "province_ids": list(term["province_ids"]) if term else [],
            "core_owner": term["core_owner"] if term else None,
            "discovery": term is None,
        }

    def _validate(self, case: dict, event: dict | None = None) -> None:
        request = case["input"]
        source = event or case["event"]
        self.assertTrue(
            ObserverSession._valid_native_peace_core_offer_query(
                source, request["action_id"], source["actor"],
                source["recipient"], source["phase"], source["date_raw"],
                self._selection(case), source["query_id"],
                source["session_id"]),
            case["name"],
        )

    def _public_result(self, case: dict) -> dict:
        event = case["event"]
        parameters = case["input"]["parameters"]
        tools = DiplomacyTools(None, _FixtureCoreSession(event))
        return tools.inspect_diplomatic_action(
            case["input"]["action_id"], event["actor"], event["recipient"],
            phase=case["input"].get("phase", event["phase"]),
            parameters=parameters,
        )

    def test_all_real_query_events_validate_and_semantic_projection(self):
        self.assertEqual(14, len(self.fixture["cases"]))
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                self._validate(case)
                projected = ObserverSession._semantic_peace_core_offer_query(
                    case["event"], EU4_ESCAPE_CODEC)
                native = projected["native_core_terms"]
                self.assertEqual(case["input"]["action_id"], native["action_id"])
                self.assertTrue(native["candidate_enumeration_complete"])
                self.assertEqual(
                    native["candidate_count"], len(native["candidates"]))
                self.assertTrue(all(
                    row["name_readable"] and isinstance(row["name"], str)
                    for row in native["candidates"]))
                self.assertNotIn("frame_thread",
                                 json.dumps(projected, ensure_ascii=False))
                if case["input"]["expected_kind"] == "discovery":
                    self.assertEqual([], projected["peace_context"]["terms"])
                    self.assertFalse(projected["parameters_matched"])
                elif case["input"]["expected_kind"] == "selected":
                    self.assertTrue(projected["parameters_matched"])
                    self.assertEqual(
                        len(self._selection(case)["province_ids"]),
                        native["selected_term_count"])
                else:
                    self.assertFalse(projected["parameters_matched"])
                    self.assertEqual([], projected["peace_context"]["terms"])

    def test_selected_public_apply_separates_evaluation_and_core_cost(self):
        expected = {
            "revoke-demand-175-eng": (-100, 9, 8, 8),
            "revoke-offer-167-fra": (-28, 7, 6, 6),
            "revoke-offer-167-168-fra": (-23, 7, 11, 11),
            "return-demand-173-amg": (-100, 10, 7, 7),
            "return-demand-177-pro": (-100, 10, 8, 8),
            "return-offer-204-pro": (-26, 7, 8, 8),
        }
        for case in self.fixture["cases"]:
            if case["input"]["expected_kind"] != "selected":
                continue
            with self.subTest(case=case["name"]):
                native_total, factor_count, core_cost, aggregate = expected[
                    case["name"]]
                result = self._public_result(case)
                self.assertEqual("available", result["legality"]["status"])
                self.assertEqual(native_total,
                                 result["acceptance"]["native_total"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                self.assertTrue(result["acceptance"]["details_complete"])
                items = result["acceptance"]["items"]
                self.assertEqual(factor_count, len(items))
                self.assertTrue(all(item["text_decoded"] and item["text"]
                                    for item in items))
                native_cost = result["costs"]["native_core"]
                self.assertEqual(core_cost,
                                 native_cost["items"][0]["amount_raw"])
                self.assertEqual("native_war_score_raw",
                                 native_cost["items"][0]["unit"])
                self.assertFalse(native_cost["items"][0]["scale_verified"])
                self.assertEqual(
                    aggregate,
                    result["costs"]["native_evaluation"]["aggregate_score_raw"])
                self.assertEqual(
                    self._selection(case)["province_ids"],
                    result["native_core_terms"]["requested_province_ids"])
                self.assertEqual(
                    self._selection(case)["core_owner"],
                    result["native_core_terms"]["requested_core_owner"])
                self.assertTrue(result["parameters"]["complete"])
                self.assertNotIn("frame_thread",
                                 json.dumps(result, ensure_ascii=False))

    def test_discovery_and_unmatched_requests_do_not_predict_white_acceptance(self):
        for case in self.fixture["cases"]:
            if case["input"]["expected_kind"] == "selected":
                continue
            with self.subTest(case=case["name"]):
                result = self._public_result(case)
                self.assertEqual(case["expected_legality"],
                                 result["legality"]["status"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                self.assertIsNone(result["acceptance"]["native_total"])
                self.assertEqual([], result["acceptance"]["items"])
                self.assertNotIn("native_core", result["costs"])
                self.assertNotIn("native_evaluation", result["costs"])
                self.assertEqual([], result["peace_context"]["terms"])
                self.assertFalse(result["parameters"]["complete"])

    def test_real_selection_count_and_core_owner_tampering_is_rejected(self):
        selected = next(case for case in self.fixture["cases"]
                        if case["name"] == "revoke-offer-167-168-fra")
        wrong_count = copy.deepcopy(selected["event"])
        wrong_count["native_core_terms"]["selected_term_count"] = 1
        self.assertFalse(
            ObserverSession._valid_native_peace_core_offer_query(
                wrong_count, "revoke_core", wrong_count["actor"],
                wrong_count["recipient"], wrong_count["phase"],
                wrong_count["date_raw"], self._selection(selected),
                wrong_count["query_id"], wrong_count["session_id"]))

        wrong_owner = copy.deepcopy(selected["event"])
        wrong_owner["native_core_terms"]["candidates"][0]["core_owner"] = "ENG"
        self.assertFalse(
            ObserverSession._valid_native_peace_core_offer_query(
                wrong_owner, "revoke_core", wrong_owner["actor"],
                wrong_owner["recipient"], wrong_owner["phase"],
                wrong_owner["date_raw"], self._selection(selected),
                wrong_owner["query_id"], wrong_owner["session_id"]))


if __name__ == "__main__":
    unittest.main()
