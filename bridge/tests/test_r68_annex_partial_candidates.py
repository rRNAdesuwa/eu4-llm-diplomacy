from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession
from bridge.diplomat_availability import (
    apply_diplomat_legality,
    project_native_diplomat_context,
)
from bridge.native_text import EU4_ESCAPE_CODEC
from work import run_peace_consequence_family_queries as family


FIXTURE = (Path(__file__).parent / "fixtures" /
           "r68_annex_partial_candidates_real.json")


class R68AnnexPartialCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.event = json.loads(FIXTURE.read_text(encoding="utf-8"))

    @staticmethod
    def _selection(event: dict, *, country: str | None = None,
                   beneficiary: str | None = None) -> dict:
        return {
            "action_id": "full_annexation",
            "war_id": event["war_id"],
            "direction": event["direction"],
            "term_mask": "e",
            "release_nation_country": None,
            "release_nation_source": None,
            "vassal_country": None,
            "vassal_beneficiary": None,
            "union_country": None,
            "union_beneficiary": None,
            "independence_country": None,
            "annex_country": country,
            "annex_beneficiary": beneficiary,
        }

    def _valid(self, event: dict, selection: dict) -> bool:
        return ObserverSession._valid_native_peace_combined_country_offer_query(
            event, "full_annexation", event["actor"], event["recipient"],
            event["phase"], event["date_raw"], selection,
            event["query_id"], event["session_id"])

    def test_partial_discovery_validates_and_projects_unavailable(self):
        event = self.event
        native = event["native_annexation"]
        self.assertEqual(8, native["candidate_match_count"])
        self.assertEqual(11, native["target_owned_count"])
        self.assertFalse(native["candidate_matches_complete"])
        self.assertTrue(self._valid(event, self._selection(event)))

        parameters = {"peace_context": {
            "war_id": event["war_id"], "direction": event["direction"],
            "terms": [],
        }}
        public = family._recover_public_projection(
            event, parameters, EU4_ESCAPE_CODEC)
        self.assertIsInstance(public, dict)
        assert isinstance(public, dict)
        public["resources"] = {
            "diplomats": project_native_diplomat_context(event),
        }
        apply_diplomat_legality(public)
        self.assertEqual(0, public["resources"]["diplomats"]["available_count"])
        self.assertEqual("unavailable", public["legality"]["status"])
        self.assertFalse(public["parameters"]["complete"])
        self.assertFalse(public["native_annexation"]["complete"])
        self.assertTrue(event["object_unchanged"])

    def test_complete_candidate_count_mismatch_is_rejected(self):
        event = copy.deepcopy(self.event)
        native = event["native_annexation"]
        native["candidate_match_count"] = 10
        self.assertFalse(self._valid(event, self._selection(event)))

    def test_selected_incomplete_candidate_set_is_rejected(self):
        event = copy.deepcopy(self.event)
        native = event["native_annexation"]
        native["selection_requested"] = True
        native["selection_applied"] = True
        native["candidates"][2]["selected"] = True
        selection = self._selection(event, country="BUR", beneficiary="FRA")
        self.assertFalse(self._valid(event, selection))


if __name__ == "__main__":
    unittest.main()
