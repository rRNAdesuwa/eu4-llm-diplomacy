from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.tests.test_peace_country_r61_real import (
    PeaceCountryR61RealTests,
    _FixtureCountrySession,
)


FIXTURE = Path(__file__).parent / "fixtures" / "peace_country_r61_c003_real.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PeaceCountryR61C003RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    @staticmethod
    def _expected_selection(case: dict) -> dict:
        # Keep the canonical QUERY18 field derivation in one place.  The
        # shared helper also restores the primary mask for discovery inputs,
        # whose public terms list is intentionally empty.
        return PeaceCountryR61RealTests._expected_selection(case)

    def _public_result(self, case: dict) -> dict:
        event = case["event"]
        request = case["input"]
        tools = DiplomacyTools(None, _FixtureCountrySession(event))
        return tools.inspect_diplomatic_action(
            request["action_id"], event["actor"], event["recipient"],
            phase=event["phase"], parameters=request["parameters"],
        )

    def _validate(self, case: dict, event: dict | None = None) -> None:
        source = event or case["event"]
        request = case["input"]
        expected = self._expected_selection(case)
        self.assertTrue(
            ObserverSession._valid_native_peace_combined_country_offer_query(
                source, request["action_id"], source["actor"],
                source["recipient"], source["phase"], source["date_raw"],
                expected, source["query_id"], source["session_id"],
            ),
            case["name"],
        )

    def test_all_c003_native_events_validate_and_project(self) -> None:
        self.assertEqual(19, len(self.fixture["cases"]))
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                self._validate(case)
                result = self._public_result(case)
                expected = case["expected"]
                self.assertEqual(
                    expected["legality"], result["legality"]["status"])
                self.assertEqual(
                    expected["reason_code"],
                    result["legality"]["reasons"][0]["code"],
                )
                self.assertNotEqual(
                    "QUERY_NATIVE_RESULT_INVALID",
                    result["legality"]["reasons"][0]["code"],
                )
                self.assertEqual(
                    expected["parameters_complete"],
                    result["parameters"]["complete"],
                )
                self.assertNotIn("frame_thread", json.dumps(result))

    def test_release_discovery_allows_same_country_from_multiple_sources(self) -> None:
        case = next(
            case for case in self.fixture["cases"]
            if case["name"] == "release_nation-offer-discover")
        raw = case["event"]["native_country_terms"]["release_nation"]
        self.assertEqual(8, raw["candidate_count"])
        self.assertEqual(
            3,
            sum(row["country"] == "GUY" for row in raw["candidates"]),
        )
        projected = ObserverSession._semantic_peace_combined_country_offer_query(
            copy.deepcopy(case["event"]), EU4_ESCAPE_CODEC)
        public = projected["native_country_terms"]["release_nation"]
        self.assertEqual(8, len(public["candidates"]))
        self.assertEqual(
            {"FRA", "AMG", "FOI"},
            {row["source"] for row in public["candidates"]
             if row["country"] == "GUY"},
        )

    def test_duplicate_country_source_pair_is_rejected(self) -> None:
        case = next(
            case for case in self.fixture["cases"]
            if case["name"] == "release_nation-offer-discover")
        tampered = copy.deepcopy(case["event"])
        record = tampered["native_country_terms"]["release_nation"]
        record["candidates"].append(copy.deepcopy(record["candidates"][0]))
        record["candidate_count"] += 1
        self.assertFalse(
            ObserverSession._valid_native_peace_combined_country_offer_query(
                tampered, case["input"]["action_id"], tampered["actor"],
                tampered["recipient"], tampered["phase"], tampered["date_raw"],
                self._expected_selection(case), tampered["query_id"],
                tampered["session_id"],
            ))


if __name__ == "__main__":
    unittest.main()
