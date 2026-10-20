from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_rejection import (
    project_native_peace_rejection,
    validate_native_peace_rejection,
)


FIXTURE = (Path(__file__).parent / "fixtures" /
           "r66_warscore_cap_real.json")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class PeaceWarscoreCapR66RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_bounded_and_sources_are_bound(self):
        self.assertLess(FIXTURE.stat().st_size, 200 * 1024)
        self.assertEqual("passed", self.data["report_status"])
        self.assertTrue(all(self.data["report_checks"].values()))
        for key in ("query_event_source", "execution_rejection_source"):
            source = self.data[key]
            self.assertGreater(source["line"], 0)
            self.assertGreater(source["line_bytes"], 0)
            self.assertRegex(source["file_sha256"], _HEX64)
            self.assertRegex(source["line_sha256"], _HEX64)
            self.assertTrue(source["path"].endswith(".jsonl"))

    def test_single_province_positive_public_snapshot_is_available(self):
        public = self.data["single_province_positive"]
        self.assertEqual("available", public["legality"]["status"])
        self.assertIs(public["legality"]["complete"], True)
        rules = public["native_selected_rules"]
        self.assertIs(rules["complete"], True)
        self.assertIs(rules["available"], True)
        self.assertIs(rules["cost_checked"], True)
        self.assertEqual(1, rules["checked_term_count"])
        self.assertEqual(2, rules["selected_term_count"])
        self.assertEqual(15, public["native_provinces"]["selection_delta_raw"])
        self.assertEqual(15, public["native_evaluation"]["aggregate_score_raw"])
        self.assertIs(public["parameters"]["complete"], True)
        self.assertIs(public["peace_context"]["complete"], True)
        self.assertIs(
            public["native_payload"]["serialized_fields_unchanged"], True)

    def test_real_overcap_query_validates_and_projects_full_tool_unavailable(self):
        event = self.data["query_event"]
        context = self.data["input"]["peace_context"]
        term = context["terms"][0]
        selection = {
            "war_id": context["war_id"],
            "direction": context["direction"],
            "province_ids": list(term["province_ids"]),
            "beneficiary": term["beneficiary"],
        }
        self.assertTrue(
            ObserverSession._valid_native_peace_province_offer_inspection(
                event, "cede_province", "FRA", "BUR", "initiate",
                event["date_raw"], selection, event["query_id"],
                event["session_id"]))
        rules = event["native_selected_rules"]
        self.assertTrue(ObserverSession._valid_native_selected_rules(
            rules, event["native_payload"],
            minimum_selected_terms=len(term["province_ids"])))
        self.assertIs(rules["complete"], True)
        self.assertIs(rules["available"], False)
        self.assertEqual(16, rules["checked_term_count"])
        self.assertEqual(17, rules["selected_term_count"])
        self.assertEqual(233, event["native_provinces"]["selection_delta_raw"])

        semantic = ObserverSession._semantic_peace_province_offer_inspection(
            event, EU4_ESCAPE_CODEC)
        inspection = {
            "interface_support": {},
            "session": {"date_raw": event["date_raw"]},
            "acceptance": {},
            "costs": {},
        }
        public = DiplomacyTools._apply_peace_execution_inspection(
            inspection, semantic, self.data["input"])
        expected = self.data["overcap_inspection"]
        self.assertEqual(expected["legality"]["status"],
                         public["legality"]["status"])
        self.assertEqual(expected["legality"]["complete"],
                         public["legality"]["complete"])
        self.assertEqual("unavailable", public["legality"]["status"])
        self.assertEqual(
            "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE",
            public["legality"]["reasons"][0]["code"],
        )
        self.assertIn("超过100%战争分数", public["legality"]["reasons"][0]["text"])
        self.assertEqual(233, public["costs"]["native_evaluation"][
            "aggregate_score_raw"])
        self.assertIs(public["parameters"]["complete"], False)
        self.assertIs(public["native_selected_rules"]["complete"], True)
        self.assertIs(public["native_selected_rules"]["available"], False)
        self.assertIs(public["native_payload"][
            "serialized_fields_unchanged"], True)
        self.assertEqual(
            "§R不能提出超过100%战争分数价值的条件§!\n",
            public["diagnostics"]["selected_term_gate"]["text"],
        )
        rendered = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("term_pointer", rendered)
        self.assertNotIn("province_pointer", rendered)

    def test_incomplete_selected_rules_cannot_promote_to_available(self):
        event = copy.deepcopy(self.data["query_event"])
        event["native_selected_rules"]["complete"] = False
        event["native_selected_rules"]["available"] = True
        self.assertTrue(ObserverSession._valid_native_selected_rules(
            event["native_selected_rules"], event["native_payload"],
            minimum_selected_terms=16))
        semantic = ObserverSession._semantic_peace_province_offer_inspection(
            event, EU4_ESCAPE_CODEC)
        public = DiplomacyTools._apply_peace_execution_inspection(
            {"interface_support": {},
             "session": {"date_raw": event["date_raw"]},
             "acceptance": {}, "costs": {}},
            semantic, self.data["input"])
        self.assertEqual("unknown", public["legality"]["status"])
        self.assertIs(public["legality"]["complete"], False)
        self.assertIs(public["parameters"]["complete"], False)

    def test_malformed_selected_rules_are_rejected(self):
        event = self.data["query_event"]
        malformed = copy.deepcopy(event["native_selected_rules"])
        malformed["diagnostic_hex"] = "0"
        self.assertFalse(ObserverSession._valid_native_selected_rules(
            malformed, event["native_payload"], minimum_selected_terms=16))

        malformed = copy.deepcopy(event["native_selected_rules"])
        malformed["selected_term_count"] = 16
        self.assertFalse(ObserverSession._valid_native_selected_rules(
            malformed, event["native_payload"], minimum_selected_terms=16))

        malformed = copy.deepcopy(event["native_selected_rules"])
        malformed["payload_unchanged"] = False
        self.assertFalse(ObserverSession._valid_native_selected_rules(
            malformed, event["native_payload"], minimum_selected_terms=16))

    def test_native_rejection_is_bound_and_keeps_diagnostic_classification(self):
        event = self.data["execution_rejection"]
        kwargs = {
            "request_id": event["request_id"],
            "session_id": event["session_id"],
            "action_id": event["action_id"],
            "actor": event["actor"],
            "recipient": event["recipient"],
            "phase": event["phase"],
            "date_raw": event["date_raw"],
            "war_id": event["war_id"],
            "direction": event["direction"],
        }
        self.assertTrue(validate_native_peace_rejection(event, **kwargs))
        public = project_native_peace_rejection(event, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("unavailable", public["legality"]["status"])
        self.assertIs(public["legality"]["complete"], False)
        self.assertIs(public["reason"]["complete"], False)
        self.assertIs(public["binding_complete"], True)
        self.assertEqual(
            "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE",
            public["reason_code"],
        )
        self.assertEqual(
            "§R不能提出超过100%战争分数价值的条件§!\n",
            public["diagnostic"]["text"],
        )
        self.assertIs(public["diagnostic"]["complete"], True)
        self.assertNotIn("native_diagnostic_hex", json.dumps(public))

        wrong_request = dict(kwargs, request_id="r66_wrong_request")
        self.assertFalse(validate_native_peace_rejection(event, **wrong_request))

    def test_transaction_and_unified_result_snapshots_keep_false_classification(self):
        selected = self.data["overcap_inspection"]["native_selected_rules"]
        self.assertIs(selected["complete"], True)
        self.assertIs(selected["available"], False)
        self.assertIs(selected["cost_checked"], True)
        self.assertIs(selected["payload_unchanged"], True)
        self.assertIs(self.data["overcap_inspection"]["submitted"], False)
        self.assertEqual("invalidated", self.data["api_result_summary"]["status"])
        self.assertIs(self.data["api_result_summary"]["submitted"], False)
        self.assertEqual(
            "NATIVE_LEGALITY_UNAVAILABLE",
            self.data["api_result_summary"]["result"]["reason"]["code"],
        )
        self.assertIn(
            "超过100%战争分数",
            self.data["api_result_summary"]["result"]["reason"]["text"],
        )
        self.assertEqual("failed", self.data["native_result"]["status"])
        self.assertIs(self.data["native_result"]["submitted"], False)


if __name__ == "__main__":
    unittest.main()
