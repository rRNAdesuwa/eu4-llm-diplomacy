from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import (
    project_native_consequences,
    validate_native_consequences,
)


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_consequences_r65_d_real.json")


def _selection(case: dict) -> dict:
    context = case["input"]["parameters"]["peace_context"]
    terms = context["terms"]
    if not terms:
        return context
    term = terms[0]
    return {
        "war_id": context["war_id"],
        "direction": context["direction"],
        "province_ids": list(term["province_ids"]),
        "beneficiary": term["beneficiary"],
    }


class PeaceConsequencesR65RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_bounded_and_has_source_provenance(self):
        self.assertLess(FIXTURE.stat().st_size, 500 * 1024)
        self.assertTrue(self.data["source_report"].endswith("report.json"))
        self.assertRegex(self.data["source_report_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(6, len(self.data["cases"]))
        for case in self.data["cases"]:
            source = case["source"]
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(source["line"], 0)
            self.assertEqual(source["event"], case["event"]["event"])

    def test_real_six_events_validate_and_project_fraction_units(self):
        expected_names = {
            "demand-white-peace", "demand-province-one",
            "demand-province-two", "demand-province-many",
            "offer-province-one", "offer-province-many",
        }
        self.assertEqual(expected_names,
                         {case["name"] for case in self.data["cases"]})
        for case in self.data["cases"]:
            with self.subTest(case=case["name"]):
                event = case["event"]
                native = event["native_consequences"]
                self.assertTrue(validate_native_consequences(native))
                public = project_native_consequences(native, EU4_ESCAPE_CODEC)
                self.assertIsNotNone(public)
                assert public is not None
                for row in public["territorial"]:
                    self.assertEqual("fraction", row["overextension_unit"])
                    scale = row["scale"]
                    self.assertAlmostEqual(
                        row["overextension_added_raw"] / scale,
                        row["overextension_added_fraction"])
                    self.assertAlmostEqual(
                        row["overextension_added_raw"] * 100 / scale,
                        row["overextension_added_percentage_points"])
                    for province in row["provinces"]:
                        self.assertEqual("fraction",
                                         province["overextension_unit"])
                        self.assertAlmostEqual(
                            province["overextension_added_raw"] / scale,
                            province["overextension_added_fraction"])
                        self.assertAlmostEqual(
                            province["overextension_added_raw"] * 100 / scale,
                            province["overextension_added_percentage_points"])

    def test_real_selected_and_white_validators_keep_direction_and_values(self):
        for case in self.data["cases"]:
            event = case["event"]
            request = case["input"]
            context = request["parameters"]["peace_context"]
            with self.subTest(case=case["name"]):
                if event["event"] == "native_peace_empty_offer_inspection":
                    valid = ObserverSession._valid_native_peace_empty_offer_inspection(
                        event, "white_peace", request["actor"],
                        request["recipient"], request["phase"],
                        event["date_raw"], context["war_id"],
                        event["query_id"], event["session_id"],
                        expected_direction=request["direction"])
                else:
                    valid = ObserverSession._valid_native_peace_province_offer_inspection(
                        event, "cede_province", request["actor"],
                        request["recipient"], request["phase"],
                        event["date_raw"], _selection(case),
                        event["query_id"], event["session_id"])
                self.assertTrue(valid)

    def test_many_province_consequence_values_and_full_tool_projection(self):
        case = next(case for case in self.data["cases"]
                    if case["name"] == "demand-province-many")
        event = case["event"]
        request = case["input"]
        semantic = ObserverSession._semantic_peace_province_offer_inspection(
            event, EU4_ESCAPE_CODEC)
        consequences = semantic["peace_consequences"]
        self.assertEqual(288, consequences["diplomatic_power"]["value"])
        self.assertEqual(78, consequences["coalition"]["native_count"])
        self.assertEqual(78, len(consequences["coalition"]["countries"]))
        row = next(item for item in consequences["territorial"]
                   if item["country"] == "FRA")
        self.assertEqual(1100, row["administrative_power"])
        self.assertEqual(1760, row["overextension_added_raw"])
        self.assertEqual(1000, row["scale"])
        self.assertEqual("fraction", row["overextension_unit"])
        self.assertAlmostEqual(1.76, row["overextension_added_fraction"])
        self.assertAlmostEqual(176.0,
                               row["overextension_added_percentage_points"])
        self.assertEqual(16, len(row["provinces"]))

        inspection = {
            "interface_support": {},
            "session": {"date_raw": event["date_raw"]},
            "acceptance": {},
            "costs": {},
        }
        projected = DiplomacyTools._apply_peace_execution_inspection(
            inspection, semantic, request["parameters"])
        public = projected["peace_consequences"]
        self.assertEqual("native_peace_consequences", public["source"])
        self.assertEqual(176.0, public["territorial"][0][
            "overextension_added_percentage_points"])
        self.assertNotIn("native_text_hex", json.dumps(public))

    def test_public_derivation_changes_when_real_raw_changes(self):
        case = next(case for case in self.data["cases"]
                    if case["name"] == "demand-province-one")
        native = copy.deepcopy(case["event"]["native_consequences"])
        native["territorial"][0]["overextension_added_raw"] = 130
        public = project_native_consequences(native, EU4_ESCAPE_CODEC)
        self.assertEqual(0.13, public["territorial"][0][
            "overextension_added_fraction"])
        self.assertEqual(13.0, public["territorial"][0][
            "overextension_added_percentage_points"])


if __name__ == "__main__":
    unittest.main()
