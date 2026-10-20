from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import (
    project_event_consequences,
    project_native_consequences,
    validate_native_consequences,
)
from bridge.peace_justification import validate_native_justification
from bridge.peace_overextension import validate_native_overextension


FIXTURE = (Path(__file__).parent / "fixtures" /
           "r69_peace_rules_real.json")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_CASE_NAMES = {
    "demand_white", "demand_money", "cede_FRA_88",
    "release_PIC", "release_HAI", "release_LUX",
}


def _selected_term(public: dict, action_id: str) -> dict:
    rows = [row for row in public["justification"]["terms"]
            if row.get("action_id") == action_id and row.get("selected") is True]
    if len(rows) != 1:
        raise AssertionError(
            f"expected one selected {action_id} row, got {len(rows)}")
    return rows[0]


class PeaceRulesR69RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_bounded_and_offline_provenanced(self):
        self.assertLess(FIXTURE.stat().st_size, 1 * 1024 * 1024)
        source = self.data["offline_source"]
        self.assertTrue(source["source_report"].endswith("report.json"))
        self.assertRegex(source["source_report_sha256"], _HEX64)
        self.assertEqual(sorted(_CASE_NAMES), sorted(source["selection"]))
        self.assertEqual(_CASE_NAMES,
                         {case["name"] for case in self.data["cases"]})
        for case in self.data["cases"]:
            self.assertNotIn("public", case)
            source = case["source"]
            self.assertTrue(source["path"].endswith("native-event.json"))
            self.assertGreater(source["bytes"], 0)
            self.assertRegex(source["sha256"], _HEX64)
            self.assertEqual(case["event"]["event"], source["event"])

    def test_raw_rules_project_to_current_public_contract(self):
        expected_status = {
            "demand_white": "not_applicable",
            "demand_money": "unjustified",
            "cede_FRA_88": "justified",
            "release_PIC": "unjustified",
            "release_HAI": "unjustified",
            "release_LUX": "unjustified",
        }
        expected_release_country = {
            "release_PIC": "PIC",
            "release_HAI": "HAI",
            "release_LUX": "LUX",
        }
        expected_dip = {
            "demand_white": 0,
            "demand_money": 0,
            "cede_FRA_88": 0,
            "release_PIC": 65,
            "release_HAI": 89,
            "release_LUX": 24,
        }

        for case in self.data["cases"]:
            with self.subTest(case=case["name"]):
                event = case["event"]
                native = event["native_consequences"]
                self.assertTrue(validate_native_consequences(native))
                self.assertTrue(validate_native_justification(
                    native["justification"]))
                self.assertTrue(validate_native_overextension(
                    native["overextension"]))

                # The fixture carries native evidence only.  Both public
                # projections are recomputed here from that evidence.
                raw_projection = project_native_consequences(
                    native, EU4_ESCAPE_CODEC)
                self.assertIsNotNone(raw_projection)
                public = project_event_consequences(
                    event, EU4_ESCAPE_CODEC)
                self.assertIsNotNone(public)
                assert public is not None
                self.assertTrue(public["requested_terms_applied"])
                self.assertEqual(expected_status[case["name"]],
                                 public["justification"]
                                 ["selected_terms_status"])
                self.assertEqual(expected_dip[case["name"]],
                                 public["diplomatic_power"]["value"])
                self.assertTrue(public["overextension"]["complete"])

                if case["name"] == "demand_white":
                    # The native default zero-money row remains native-selected,
                    # while the current event projector excludes it publicly.
                    row = next(row for row in public["justification"]["terms"]
                               if row.get("action_id") == "demand_ducats")
                    self.assertTrue(row["native_selected"])
                    self.assertFalse(row["selected"])
                    self.assertEqual(
                        "NATIVE_ZERO_DEFAULT_MONEY_TERM",
                        row["selection_reason_code"])
                elif case["name"] == "demand_money":
                    row = _selected_term(public, "demand_ducats")
                    self.assertEqual("unjustified", row["status"])
                elif case["name"] == "cede_FRA_88":
                    row = _selected_term(public, "cede_province")
                    self.assertEqual(88, row["province_id"])
                    self.assertEqual("FRA", row["object_country"])
                    self.assertEqual("justified", row["status"])
                else:
                    row = _selected_term(public, "release_nation")
                    self.assertEqual(expected_release_country[case["name"]],
                                     row["object_country"])
                    self.assertEqual("unjustified", row["status"])

    def test_release_pic_projects_native_net_overextension(self):
        case = next(case for case in self.data["cases"]
                    if case["name"] == "release_PIC")
        public = project_event_consequences(case["event"], EU4_ESCAPE_CODEC)
        self.assertIsNotNone(public)
        assert public is not None
        countries = {row["country"]: row
                     for row in public["overextension"]["countries"]}
        bur = countries["BUR"]
        pic = countries["PIC"]
        self.assertEqual(120, bur["current_raw"])
        self.assertEqual(0, bur["projected_raw"])
        self.assertEqual([88, 89], bur["lost_province_ids"])
        self.assertEqual(0, pic["gained_raw"])
        self.assertEqual(0, pic["projected_raw"])
        self.assertEqual([88, 89], pic["gained_province_ids"])

    def test_cede_fra_88_replays_through_full_tools_projection(self):
        case = next(case for case in self.data["cases"]
                    if case["name"] == "cede_FRA_88")
        event = case["event"]
        semantic = ObserverSession._semantic_peace_province_offer_inspection(
            event, EU4_ESCAPE_CODEC)
        self.assertEqual(
            "justified",
            semantic["peace_consequences"]["justification"]
            ["selected_terms_status"],
        )
        parameters = {
            "peace_context": {
                "war_id": event["war_id"],
                "direction": event["direction"],
                "terms": [{
                    "action_id": "cede_province",
                    "province_ids": list(
                        event["native_provinces"]["requested_province_ids"]),
                    "beneficiary": event["native_provinces"]
                    ["requested_beneficiary"],
                }],
            },
        }
        inspection = {
            "interface_support": {},
            "session": {"date_raw": event["date_raw"]},
            "acceptance": {},
            "costs": {},
        }
        projected = DiplomacyTools._apply_peace_execution_inspection(
            inspection, semantic, parameters)
        self.assertEqual("native_peace_execution_inspection",
                         projected["interface_support"]["query"])
        self.assertIn("parameters", projected)
        self.assertEqual(parameters, projected["parameters"]["requested"])
        self.assertEqual(
            "justified",
            projected["peace_consequences"]["justification"]
            ["selected_terms_status"],
        )
        self.assertEqual(0, projected["peace_consequences"]
                         ["diplomatic_power"]["value"])
        self.assertEqual([88], next(row for row in projected[
            "peace_consequences"]["overextension"]["countries"]
            if row["country"] == "BUR")["lost_province_ids"])
        self.assertNotIn("native_text_hex", json.dumps(projected[
            "peace_consequences"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
