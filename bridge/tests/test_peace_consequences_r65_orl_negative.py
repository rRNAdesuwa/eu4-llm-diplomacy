from __future__ import annotations

import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import project_event_consequences


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_consequences_r65_orl_negative.json")


class PeaceConsequencesR65OrlNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.case = cls.data["case"]
        cls.event = cls.case["event"]
        cls.request = cls.case["input"]

    def test_fixture_provenance_and_native_miss_are_preserved(self):
        self.assertLess(FIXTURE.stat().st_size, 500 * 1024)
        source = self.data["source"]
        self.assertEqual(191, source["line"])
        self.assertEqual(self.event["query_id"], source["query_id"])
        self.assertEqual(self.event["event"], source["event"])
        self.assertEqual(
            "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT",
            self.event["native_provinces"]["reason_code"],
        )
        self.assertIs(self.event["native_provinces"]["parameters_matched"], False)
        self.assertEqual([], self.event["native_provinces"]["selected_province_ids"])

    def test_event_consequences_with_unmatched_request_are_not_available(self):
        public = project_event_consequences(self.event, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertIs(public["requested_terms_applied"], False)
        self.assertFalse(public["complete"])
        self.assertEqual(
            "NATIVE_PEACE_REQUESTED_TERMS_NOT_APPLIED",
            public["reason_code"],
        )
        self.assertEqual("constructed_offer", public["scope"])
        self.assertFalse(public["diplomatic_power"]["available"])
        self.assertFalse(public["aggressive_expansion"]["available"])
        self.assertIsNone(public["aggressive_expansion"]["maximum"])
        self.assertFalse(public["coalition"]["available"])
        self.assertFalse(public["coalition"]["complete"])
        self.assertTrue(public["territorial"])
        self.assertTrue(all(not row["complete"]
                            for row in public["territorial"]))
        # Raw zeroes remain diagnostic observations, not an available offer.
        self.assertTrue(all(row["overextension_added_raw"] == 0
                            for row in public["territorial"]))

    def test_semantic_and_execution_projection_clear_actual_parameters(self):
        semantic = ObserverSession._semantic_peace_province_offer_inspection(
            self.event, EU4_ESCAPE_CODEC)
        consequences = semantic["peace_consequences"]
        self.assertIs(consequences["requested_terms_applied"], False)
        self.assertFalse(consequences["complete"])

        inspection = {
            "interface_support": {},
            "session": {"date_raw": self.event["date_raw"]},
            "acceptance": {},
            "costs": {},
        }
        projected = DiplomacyTools._apply_peace_execution_inspection(
            inspection, semantic, self.request["parameters"])
        parameters = projected["parameters"]
        self.assertIsNone(parameters["actual"])
        self.assertFalse(parameters["complete"])
        self.assertEqual(
            "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT",
            parameters["candidates"]["reason_code"],
        )
        self.assertEqual(23, parameters["candidates"]["candidate_count"])
        self.assertEqual(0, parameters["candidates"]["matching_candidate_count"])
        candidate = next(row for row in parameters["candidates"]["candidates"]
                         if row.get("province_id") == 88)
        self.assertFalse(candidate["selected"])
        self.assertNotIn("native_text_hex", json.dumps(projected,
                                                        ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
