from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.peace_consequences import (
    project_native_consequences,
    validate_native_consequences,
)


WAR_ID = "war_0123456789abcdef_01234567"


def _consequences(*, complete: bool = True) -> dict:
    return {
        "called": True,
        "offer_identity_verified": True,
        "complete": complete,
        "diplomatic_power": {
            "country": "FRA", "available": True, "value": 27,
            "unit": "power_points",
        },
        "aggressive_expansion": {
            "available": True, "maximum_raw": 1250, "scale": 1000,
            "native_text_hex": "4145", "text_readable": True,
            "text_truncated": False, "coalition_possible": True,
        },
        "coalition": {
            "available": True, "complete": True, "native_count": 2,
            "current_value_semantics_verified": False,
            "countries": [
                {"tag": "SAV", "aggressive_expansion_delta": 18,
                 "current_value": 44},
                {"tag": "BUR", "aggressive_expansion_delta": 9,
                 "current_value": 31},
            ],
        },
        "territorial": [{
            "country": "FRA", "called": True, "complete": True,
            "truncated": False, "administrative_power": 40,
            "overextension_added_raw": 750, "scale": 1000,
            "provinces": [{
                "province_id": 177, "administrative_power": 40,
                "already_core": False, "adds_overextension": True,
                "overextension_added_raw": 750,
            }],
        }],
    }


def _empty_event() -> dict:
    event = json.loads((Path(__file__).parent / "fixtures" /
                        "peace_empty_offer_inspection.json").read_text(
                            encoding="utf-8"))["event"]
    event["native_consequences"] = _consequences()
    return event


class PeaceConsequencesR65Tests(unittest.TestCase):
    def test_validator_and_projection_keep_raw_units_and_opaque_coalition_value(self):
        value = _consequences()
        self.assertTrue(validate_native_consequences(value))
        public = project_native_consequences(value)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("native_peace_consequences", public["source"])
        self.assertEqual(1250, public["aggressive_expansion"]["maximum_raw"])
        self.assertEqual(1000, public["aggressive_expansion"]["scale"])
        self.assertEqual(1.25, public["aggressive_expansion"]["maximum"])
        self.assertEqual("AE", public["aggressive_expansion"]["text"])
        self.assertEqual(44, public["coalition"]["countries"][0]["current_value"])
        self.assertFalse(public["coalition"][
            "current_value_semantics_verified"])
        self.assertIsNone(public["coalition"]["countries"][0][
            "current_aggressive_expansion_modifier"])
        self.assertNotIn("native_text_hex", json.dumps(public))
        self.assertEqual(750, public["territorial"][0]["overextension_added_raw"])

    def test_verified_coalition_marker_exposes_modifier_without_total_opinion_claim(self):
        value = _consequences()
        value["coalition"]["current_value_semantics_verified"] = True
        self.assertTrue(validate_native_consequences(value))
        public = project_native_consequences(value)
        self.assertTrue(public["coalition"]["current_value_semantics_verified"])
        row = public["coalition"]["countries"][0]
        self.assertEqual(44, row["current_value"])
        self.assertEqual(44, row["current_aggressive_expansion_modifier"])

    def test_malformed_present_record_is_rejected_without_partial_projection(self):
        cases = []
        value = _consequences()
        value["coalition"]["countries"][1]["tag"] = "SAV"
        cases.append(value)
        value = _consequences()
        value["coalition"]["current_value_semantics_verified"] = "true"
        cases.append(value)
        value = _consequences()
        value["territorial"][0]["provinces"][0]["province_id"] = 0
        cases.append(value)
        value = _consequences()
        value["aggressive_expansion"]["native_text_hex"] = "0"
        cases.append(value)
        value = _consequences()
        del value["coalition"]
        cases.append(value)
        for malformed in cases:
            with self.subTest(malformed=malformed):
                self.assertFalse(validate_native_consequences(malformed))
                self.assertIsNone(project_native_consequences(malformed))

    def test_coalition_count_is_pre_filter_length_and_overflow_stays_incomplete(self):
        filtered = _consequences()
        filtered["coalition"]["native_count"] = 3
        filtered["coalition"]["countries"] = filtered["coalition"][
            "countries"][:2]
        self.assertTrue(validate_native_consequences(filtered))
        projected = project_native_consequences(filtered)
        self.assertEqual(3, projected["coalition"]["native_count"])
        self.assertEqual(2, len(projected["coalition"]["countries"]))

        overflow = _consequences(complete=False)
        overflow["coalition"].update({
            "native_count": 4096, "available": False, "complete": False,
        })
        self.assertTrue(validate_native_consequences(overflow))
        self.assertFalse(project_native_consequences(overflow)["complete"])
        invalid_overflow = copy.deepcopy(overflow)
        invalid_overflow["coalition"]["available"] = True
        self.assertFalse(validate_native_consequences(invalid_overflow))
        too_large = copy.deepcopy(overflow)
        too_large["coalition"]["native_count"] = 4097
        self.assertFalse(validate_native_consequences(too_large))

    def test_sixteen_kib_ae_text_and_empty_readable_text_are_valid(self):
        large = _consequences()
        large["aggressive_expansion"].update({
            "native_text_hex": "41" * 16384,
            "text_readable": True,
        })
        self.assertTrue(validate_native_consequences(large))
        public = project_native_consequences(large)
        self.assertEqual(16384, len(public["aggressive_expansion"]["text"]))
        empty = _consequences()
        empty["aggressive_expansion"].update({
            "native_text_hex": "", "text_readable": True,
        })
        self.assertTrue(validate_native_consequences(empty))
        self.assertEqual("", project_native_consequences(empty)[
            "aggressive_expansion"]["text"])
        oversized = _consequences()
        oversized["aggressive_expansion"]["native_text_hex"] = "41" * 16385
        self.assertFalse(validate_native_consequences(oversized))

    def test_well_shaped_partial_observation_projects_as_incomplete(self):
        partial = _consequences(complete=False)
        partial["coalition"].update({"available": False, "complete": False})
        partial["territorial"][0].update({"complete": False, "truncated": True})
        self.assertTrue(validate_native_consequences(partial))
        public = project_native_consequences(partial)
        self.assertFalse(public["complete"])
        self.assertFalse(public["coalition"]["complete"])
        self.assertTrue(public["territorial"][0]["truncated"])

    def test_common_query_validator_and_semantic_projection_attach_once(self):
        event = _empty_event()
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], WAR_ID, event["query_id"], event["session_id"]))
        semantic = ObserverSession._semantic_peace_empty_offer_inspection(event)
        self.assertEqual("FRA", semantic["peace_consequences"][
            "diplomatic_power"]["country"])
        self.assertEqual(2, len(semantic["peace_consequences"][
            "coalition"]["countries"]))

        malformed = copy.deepcopy(event)
        malformed["native_consequences"]["territorial"][0][
            "administrative_power"] = -1
        self.assertFalse(ObserverSession._valid_native_peace_empty_offer_inspection(
            malformed, "white_peace", "FRA", "ENG", "initiate",
            malformed["date_raw"], WAR_ID, malformed["query_id"],
            malformed["session_id"]))

    def test_execution_tool_projection_preserves_optional_field_for_all_common_paths(self):
        event = _empty_event()
        semantic = ObserverSession._semantic_peace_empty_offer_inspection(event)
        projected = DiplomacyTools._apply_peace_execution_inspection(
            {"interface_support": {},
             "session": {"date_raw": event["date_raw"]},
             "acceptance": {}, "costs": {}},
            semantic,
            {"peace_context": {"war_id": WAR_ID,
                               "direction": "demand", "terms": []}})
        self.assertIn("peace_consequences", projected)
        self.assertEqual("native_peace_consequences",
                         projected["peace_consequences"]["source"])

    def test_execution_result_rejects_malformed_consequences_and_projects_valid_one(self):
        parameters = {"peace_context": {"war_id": WAR_ID,
            "direction": "demand", "terms": [{
                "action_id": "demand_ducats", "amount": "10.0",
                "payer": "ENG", "claimant": "FRA"}]}}
        event = {
            "event": "native_peace_execution_result", "family": "peace",
            "session_id": "peace-session", "request_id": "r65-consequence",
            "action_id": "demand_ducats", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "date_raw": 43, "war_id": WAR_ID,
            "direction": "demand", "amount_raw": 10000,
            "province_ids": [], "beneficiary": "-", "native_state": 0,
            "outcome": "executed", "war_before": True, "war_after": False,
            "response_verified": True, "request_binding_verified": True,
            "execution_verified": True, "terms_verified": False,
            "native_consequences": _consequences(),
        }
        public = ObserverSession._public_native_peace_execution_result(
            event, "r65-consequence", "peace-session", "FRA", "ENG",
            "initiate", 43, "demand_ducats", parameters)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(1.25, public["peace_consequences"][
            "aggressive_expansion"]["maximum"])
        tampered = copy.deepcopy(event)
        tampered["native_consequences"]["coalition"]["countries"][0][
            "current_value_semantics_verified"] = True
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            tampered, "r65-consequence", "peace-session", "FRA", "ENG",
            "initiate", 43, "demand_ducats", parameters))

    def test_legacy_event_without_consequences_remains_projectable(self):
        event = _empty_event()
        del event["native_consequences"]
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], WAR_ID, event["query_id"], event["session_id"]))
        semantic = ObserverSession._semantic_peace_empty_offer_inspection(event)
        self.assertNotIn("peace_consequences", semantic)


if __name__ == "__main__":
    unittest.main()
