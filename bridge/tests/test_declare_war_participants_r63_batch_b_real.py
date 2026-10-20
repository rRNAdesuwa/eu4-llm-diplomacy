from __future__ import annotations

import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession


FIXTURE = (Path(__file__).parent / "fixtures"
           / "declare_war_r63_participants_b_real.json")


class DeclareWarParticipantsR63BatchBRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.cases = {case["name"]: case for case in payload["cases"]}

    def test_real_b_cases_validate_and_project(self) -> None:
        self.assertEqual(5, len(self.cases))
        for name, case in self.cases.items():
            event = case["inspection"]
            rows = case["participant_events"]
            parameters = case["parameters"]
            selection = ObserverSession._normalize_declare_war_selection(
                parameters, actor=event["actor"], recipient=event["recipient"])
            self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
                event, "declare_war", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], event["query_id"],
                event["session_id"], selection, rows), name)
            public = ObserverSession._semantic_declare_war_inspection(
                event, "eu4_escape", rows)
            participants = public.get("participants")
            self.assertIsInstance(participants, dict, name)
            assert isinstance(participants, dict)
            self.assertEqual(case["expected"]["candidate_count"],
                             len(participants["candidates"]), name)
            self.assertEqual(case["expected"]["selection_allowed"],
                             participants["selection"]["allowed"], name)
            self.assertEqual(case["expected"]["selected_countries"],
                             [row["country"] for row in participants["candidates"]
                              if row["selected"]], name)
            self.assertEqual(case["expected"]["promise_countries"],
                             [row["country"] for row in participants["candidates"]
                              if row["promise_land"]], name)

    def test_mor_no_casus_belli_is_complete_without_candidate_clone(self) -> None:
        case = self.cases["MOR-no-casus-belli"]
        event = case["inspection"]
        self.assertEqual("no_casus_belli", event["requested_casus_belli"])
        self.assertEqual([], event["candidates"])
        self.assertTrue(event["full_rules_complete"])
        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape", case["participant_events"])
        self.assertEqual(11, len(public["participants"]["candidates"]))

    def test_real_candidate_counts_and_sav_promise_factor(self) -> None:
        self.assertEqual(13, self.cases[
            "ENG-cb-1-cb_conquest-167-ORL-co-SWE"]["expected"]["candidate_count"])
        self.assertEqual(19, self.cases[
            "BUR-cb-1-cb_conquest-88-ORL-co-HSA"]["expected"]["candidate_count"])
        call = self.cases["ENG-cb-1-cb_conquest-167-ORL-call-SAV"]
        promise = self.cases["ENG-cb-1-cb_conquest-167-ORL-promise-SAV"]
        self.assertEqual(-166, call["expected"]["sav_factor"]["native_total_raw"])
        self.assertEqual(-1166, promise["expected"]["sav_factor"]["native_total_raw"])
        self.assertEqual(
            promise["expected"]["sav_factor"]["native_total_raw"]
            - call["expected"]["sav_factor"]["native_total_raw"], -1000)
        self.assertEqual(-1000, promise["expected"]["sav_factor"]["reason_values"][0])


if __name__ == "__main__":
    unittest.main()
