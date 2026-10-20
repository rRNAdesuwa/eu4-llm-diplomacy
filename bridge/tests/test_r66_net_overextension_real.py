from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import project_event_consequences
from bridge.peace_overextension import (
    project_native_overextension,
    validate_native_overextension,
)


FIXTURE = (Path(__file__).parent / "fixtures" /
           "r66_net_overextension_real.json")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class PeaceNetOverextensionR66RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_compact_and_provenanced(self):
        self.assertLess(FIXTURE.stat().st_size, 300 * 1024)
        self.assertEqual(
            {"demand-white-peace", "demand-province-one",
             "demand-province-many", "offer-province-many"},
            {case["name"] for case in self.data["cases"]},
        )
        for case in self.data["cases"]:
            source = case["source"]
            self.assertTrue(source["path"].endswith("native-events-slice.jsonl"))
            self.assertGreater(source["line"], 0)
            self.assertRegex(source["sha256"], _HEX64)
            self.assertRegex(source["line_sha256"], _HEX64)
            self.assertEqual(case["event"]["event"], source["event"])
            self.assertRegex(source["public"]["sha256"], _HEX64)
            self.assertGreater(source["public"]["bytes"], 0)

    def test_real_native_overextension_projects_negative_and_positive_net(self):
        cases = {case["name"]: case for case in self.data["cases"]}
        for case in self.data["cases"]:
            with self.subTest(case=case["name"]):
                native = case["event"]["native_consequences"]["overextension"]
                self.assertTrue(validate_native_overextension(native))
                projected = project_native_overextension(native)
                self.assertIsNotNone(projected)
                self.assertEqual(case["expected_overextension"], projected)

        one = project_native_overextension(
            cases["demand-province-one"]["event"]["native_consequences"][
                "overextension"])
        assert one is not None
        one_rows = {row["country"]: row for row in one["countries"]}
        self.assertEqual(-120, one_rows["BUR"]["delta_raw"])
        self.assertEqual(-0.12, one_rows["BUR"]["delta_fraction"])
        self.assertEqual(-12.0, one_rows["BUR"]["delta_percentage_points"])
        self.assertEqual(120, one_rows["FRA"]["delta_raw"])

        many = project_native_overextension(
            cases["demand-province-many"]["event"]["native_consequences"][
                "overextension"])
        assert many is not None
        many_rows = {row["country"]: row for row in many["countries"]}
        self.assertEqual(1760, many_rows["FRA"]["gained_raw"])
        self.assertEqual(-120, many_rows["BUR"]["delta_raw"])
        self.assertEqual(0, many_rows["NEV"]["projected_raw"])
        offer = project_native_overextension(
            cases["offer-province-many"]["event"]["native_consequences"][
                "overextension"])
        assert offer is not None
        offer_rows = {row["country"]: row for row in offer["countries"]}
        self.assertEqual(1656, offer_rows["BUR"]["gained_raw"])
        self.assertEqual(1.656, offer_rows["BUR"]["gained_fraction"])

    def test_event_helper_preserves_raw_current_when_selection_is_unmatched(self):
        cases = {case["name"]: case for case in self.data["cases"]}
        for case in self.data["cases"]:
            projected = project_event_consequences(
                case["event"], EU4_ESCAPE_CODEC)
            self.assertIsNotNone(projected)
            assert projected is not None
            self.assertIs(projected["requested_terms_applied"], True)
            self.assertEqual(
                case["expected_overextension"], projected["overextension"])

        unmatched = copy.deepcopy(cases["demand-province-one"]["event"])
        unmatched["native_provinces"]["parameters_matched"] = False
        projected = project_event_consequences(unmatched, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertIs(projected["requested_terms_applied"], False)
        self.assertFalse(projected["overextension"]["available"])
        self.assertFalse(projected["overextension"]["complete"])
        rows = {row["country"]: row for row in projected["overextension"]["countries"]}
        self.assertEqual(120, rows["BUR"]["current_raw"])
        self.assertEqual(-120, rows["BUR"]["delta_raw"])

    def test_semantic_and_full_execution_projection_retain_net_oe(self):
        cases = {case["name"]: case for case in self.data["cases"]}
        for case in self.data["cases"]:
            event = case["event"]
            if event["event"] == "native_peace_empty_offer_inspection":
                semantic = ObserverSession._semantic_peace_empty_offer_inspection(
                    event, EU4_ESCAPE_CODEC)
            else:
                semantic = ObserverSession._semantic_peace_province_offer_inspection(
                    event, EU4_ESCAPE_CODEC)
            self.assertEqual(
                case["expected_overextension"],
                semantic["peace_consequences"]["overextension"],
                case["name"],
            )
            params = case["input"]["parameters"]
            inspection = {
                "interface_support": {},
                "session": {"date_raw": event["date_raw"]},
                "acceptance": {},
                "costs": {},
            }
            projected = DiplomacyTools._apply_peace_execution_inspection(
                inspection, semantic, params)
            public = projected["peace_consequences"]
            self.assertEqual(
                case["expected_overextension"], public["overextension"],
                case["name"],
            )
            self.assertIn("delta_raw", public["overextension"]["countries"][0])
            self.assertNotIn("native_text_hex", json.dumps(public))

    def test_unmatched_projection_reaches_full_tool_as_unavailable(self):
        case = next(case for case in self.data["cases"]
                    if case["name"] == "demand-province-one")
        event = copy.deepcopy(case["event"])
        event["native_provinces"]["parameters_matched"] = False
        semantic = ObserverSession._semantic_peace_province_offer_inspection(
            event, EU4_ESCAPE_CODEC)
        inspection = {
            "interface_support": {},
            "session": {"date_raw": event["date_raw"]},
            "acceptance": {},
            "costs": {},
        }
        projected = DiplomacyTools._apply_peace_execution_inspection(
            inspection, semantic, case["input"]["parameters"])
        consequences = projected["peace_consequences"]
        self.assertIs(projected["parameters"]["complete"], False)
        self.assertIs(consequences["requested_terms_applied"], False)
        self.assertIs(consequences["overextension"]["available"], False)
        self.assertEqual(120, consequences["overextension"]["countries"][0][
            "current_raw"])


if __name__ == "__main__":
    unittest.main()
