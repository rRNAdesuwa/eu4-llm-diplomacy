from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.declarewar_participants import project_participants
from bridge.diplomacy import ObserverSession


FIXTURE = (Path(__file__).parent / "fixtures"
           / "declare_war_r63_participants_real.json")


class DeclareWarParticipantsR63RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_real_rows_are_sorted_by_native_index_before_validation_and_projection(self) -> None:
        cases = self.fixture["cases"]
        self.assertEqual(7, len(cases))
        for case in cases:
            event = case["inspection"]
            rows = case["participant_events"]
            self.assertEqual("native_declare_war_inspection", event["event"])
            self.assertGreater(len(rows), 0)
            # A's native output is defenders-first even though indexes retain
            # the original attacker/defender enumeration order.
            self.assertEqual(5, rows[0]["index"])

            parameters = case["parameters"]
            expected_selection = (
                None if not parameters else
                ObserverSession._normalize_declare_war_selection(
                    parameters, actor=event["actor"],
                    recipient=event["recipient"]))
            self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
                event, "declare_war", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], event["query_id"],
                event["session_id"], expected_selection, rows))

            public = ObserverSession._semantic_declare_war_inspection(
                event, "eu4_escape", rows)
            participants = public.get("participants")
            self.assertIsInstance(participants, dict, case["name"])
            assert isinstance(participants, dict)
            self.assertEqual(event["native_participants"]["candidate_count"],
                             participants["candidate_count"])
            self.assertEqual(
                list(range(len(rows))),
                [candidate["index"] for candidate in participants["candidates"]],
                case["name"],
            )
            self.assertEqual(
                event["native_participants"]["selection_allowed"],
                participants["selection"]["allowed"],
            )

    def test_real_empty_selection_still_projects_candidate_rows(self) -> None:
        discovery = next(case for case in self.fixture["cases"]
                         if case["name"].endswith("discovery"))
        event = discovery["inspection"]
        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape", discovery["participant_events"])
        participants = public["participants"]
        self.assertEqual([], participants["selection"]["call_allies"])
        self.assertEqual([], participants["selection"]["promise_land_to"])
        self.assertEqual([], participants["selection"]["co_belligerents"])
        self.assertEqual(event["native_participants"]["candidate_count"],
                         len(participants["candidates"]))

    def test_real_duplicate_index_is_rejected_after_ordering(self) -> None:
        case = self.fixture["cases"][1]
        event = case["inspection"]
        rows = copy.deepcopy(case["participant_events"])
        rows[1]["index"] = rows[0]["index"]
        self.assertIsNone(project_participants(
            event["native_participants"], rows, "eu4_escape"))


if __name__ == "__main__":
    unittest.main()
