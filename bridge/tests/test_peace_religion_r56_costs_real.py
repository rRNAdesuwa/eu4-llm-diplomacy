from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.peace_costs import project_special_cost_comparisons
from bridge.diplomacy import DiplomacyTools, ObserverSession


FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_religion_r56_costs.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PeaceReligionR56CostProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    def _source_path(self) -> Path:
        return REPOSITORY_ROOT / self.fixture["source"]["native_events_path"]

    def _assert_real_event(self, case: dict[str, object]) -> dict[str, object]:
        source = self.fixture["source"]
        path = self._source_path()
        self.assertTrue(path.is_file(), path)
        self.assertEqual(source["native_events_bytes"], path.stat().st_size)
        self.assertEqual(
            source["native_events_sha256"],
            hashlib.sha256(path.read_bytes()).hexdigest())
        raw = path.read_bytes().splitlines()[case["source_line"] - 1]
        self.assertEqual(case["source_line_bytes"], len(raw))
        self.assertEqual(
            case["source_line_sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        self.assertEqual(case["event"], event)
        return event

    def test_two_real_cost_events_project_raw_comparisons(self):
        cases = self.fixture["cases"]
        self.assertEqual(2, len(cases))
        for case in cases:
            with self.subTest(case=case["name"]):
                event = self._assert_real_event(case)
                projection = project_special_cost_comparisons(event)
                self.assertEqual(case["expected"], projection)
                self.assertEqual(
                    case["rule_available"],
                    event["native_force_religion"]["rule_available"])
                self.assertFalse(projection["scale_verified"])

        demand = cases[0]["expected"]
        offer = cases[1]["expected"]
        self.assertTrue(demand["within_limit"])
        self.assertFalse(offer["within_limit"])
        self.assertTrue(cases[0]["rule_available"])
        self.assertFalse(cases[1]["rule_available"])

    def test_all_three_special_action_names_use_the_same_strict_projection(self):
        source_event = self.fixture["cases"][0]["event"]
        for action_id in ("humiliate_rival", "show_strength", "force_religion"):
            with self.subTest(action_id=action_id):
                event = copy.deepcopy(source_event)
                native = event.pop("native_force_religion")
                event["action_id"] = action_id
                event["native_" + action_id] = native
                projection = project_special_cost_comparisons(event)
                self.assertIsNotNone(projection)
                self.assertEqual(action_id, projection["action_id"])
                self.assertEqual(8, projection["total_raw"])

    def test_rule_unavailable_does_not_hide_readable_cost(self):
        event = self.fixture["cases"][1]["event"]
        self.assertFalse(event["native_force_religion"]["rule_available"])
        projection = project_special_cost_comparisons(event)
        self.assertIsNotNone(projection)
        self.assertEqual(270, projection["total_raw"])
        self.assertFalse(projection["within_limit"])
        self.assertEqual("native_rule", projection["source"])
        self.assertEqual("native_war_score_raw", projection["unit"])
        self.assertFalse(projection["scale_verified"])

    def test_real_comparisons_reach_public_inspection_costs(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                event = case["event"]
                native = ObserverSession._semantic_peace_special_offer_inspection(event)
                comparison = native["native_cost_comparisons"]
                self.assertEqual([case["expected"]], comparison)
                term = event["native_force_religion"]
                parameters = {"peace_context": {
                    "war_id": event["war_id"], "direction": event["direction"],
                    "terms": [{"action_id": "force_religion", "country": term["country"],
                               "beneficiary": term["beneficiary"]}]}}
                inspection = {"interface_support": {}, "session": {}, "acceptance": {}, "costs": {}}
                public = DiplomacyTools._apply_peace_execution_inspection(inspection, native, parameters)
                self.assertEqual(comparison, public["costs"]["native_rule_comparisons"])
                self.assertEqual("available" if case["rule_available"] else "unavailable",
                                 public["legality"]["status"])

    def test_tampered_arithmetic_restore_or_payload_is_rejected(self):
        original = self.fixture["cases"][0]["event"]
        for field, value in (
                ("total_raw", 9),
                ("cost_transaction_restored", False),
                ("cost_payload_unchanged", False)):
            with self.subTest(field=field):
                event = copy.deepcopy(original)
                event["native_force_religion"][field] = value
                self.assertIsNone(project_special_cost_comparisons(event))

    def test_missing_or_wrongly_typed_cost_fields_are_rejected_without_zero_fill(self):
        original = self.fixture["cases"][0]["event"]
        for field in (
                "base_or_existing_raw", "selected_delta_raw", "total_raw",
                "limit_raw", "unit_scale"):
            with self.subTest(field=field):
                event = copy.deepcopy(original)
                del event["native_force_religion"][field]
                self.assertIsNone(project_special_cost_comparisons(event))

        event = copy.deepcopy(original)
        event["native_force_religion"]["selected_delta_raw"] = True
        self.assertIsNone(project_special_cost_comparisons(event))
        event = copy.deepcopy(original)
        event["native_force_religion"]["unit_scale_verified"] = "false"
        self.assertIsNone(project_special_cost_comparisons(event))

    def test_out_of_scope_event_is_ignored(self):
        event = copy.deepcopy(self.fixture["cases"][0]["event"])
        event["action_id"] = "demand_ducats"
        self.assertIsNone(project_special_cost_comparisons(event))


if __name__ == "__main__":
    unittest.main()
