from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import project_event_consequences


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_consequences_r65_families.json")


class _ReplaySession:
    """Replay stored native events through the production public wrappers."""

    def __init__(self, event: dict):
        self.event = event

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": self.event["session_id"],
            "date_raw": self.event["date_raw"],
            "reasons": [],
            "complete": True,
        }

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({
            "native_peace_subject_terms_query",
            "native_peace_core_terms_query",
        })

    def inspect_peace_subject_offer(self, action_id: str, actor: str,
                                    recipient: str, phase: str,
                                    selection: dict) -> dict:
        return ObserverSession._semantic_peace_subject_offer_query(
            copy.deepcopy(self.event), EU4_ESCAPE_CODEC)

    def inspect_peace_core_offer(self, action_id: str, actor: str,
                                 recipient: str, phase: str,
                                 selection: dict) -> dict:
        return ObserverSession._semantic_peace_core_offer_query(
            copy.deepcopy(self.event), EU4_ESCAPE_CODEC)


class PeaceConsequencesR65FamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.cases = {case["name"].removesuffix("-discovery"): case
                     for case in cls.fixture["cases"]}

    @staticmethod
    def _subject_selection(event: dict, country: str | None = None) -> dict:
        return {
            "action_id": event["action_id"],
            "war_id": event["war_id"],
            "direction": event["direction"],
            "country": country,
            "discovery": country is None,
        }

    @staticmethod
    def _core_selection(event: dict, province_ids: list[int] | None = None,
                        owner: str | None = None) -> dict:
        return {
            "action_id": event["action_id"],
            "war_id": event["war_id"],
            "direction": event["direction"],
            "province_ids": list(province_ids or []),
            "core_owner": owner,
        }

    @staticmethod
    def _parameters(event: dict, terms: list[dict]) -> dict:
        return {"peace_context": {
            "war_id": event["war_id"],
            "direction": event["direction"],
            "terms": terms,
        }}

    def _public(self, event: dict, action_id: str,
                parameters: dict) -> dict:
        tools = DiplomacyTools(None, _ReplaySession(event))
        return tools.inspect_diplomatic_action(
            action_id, event["actor"], event["recipient"],
            phase=event["phase"], parameters=parameters)

    def test_real_subject_discovery_validates_and_keeps_unknown_cost_shape(self):
        for action_id in ("release_subject", "transfer_subject"):
            with self.subTest(action_id=action_id):
                case = self.cases[action_id]
                event = case["event"]
                native = event["native_subject_terms"]
                self.assertTrue(
                    ObserverSession._valid_native_peace_subject_offer_query(
                        event, action_id, event["actor"], event["recipient"],
                        event["phase"], event["date_raw"],
                        self._subject_selection(event), event["query_id"],
                        event["session_id"]))
                self.assertEqual(case["expected"]["candidate_count"],
                                 native["candidate_count"])
                self.assertEqual(case["expected"]["candidate_countries"],
                                 [row["country"] for row in native["candidates"]])
                self.assertEqual([], native["requested_countries"])
                projected = project_event_consequences(event, EU4_ESCAPE_CODEC)
                self.assertIsNotNone(projected)
                assert projected is not None
                self.assertIs(projected["requested_terms_applied"], True)
                result = self._public(event, action_id,
                                      case["input"]["parameters"])
                self.assertEqual("unknown", result["legality"]["status"])
                self.assertFalse(result["parameters"]["complete"])
                self.assertEqual("unknown", result["costs"]["status"])
                self.assertFalse(result["costs"]["complete"])
                self.assertNotIn("native_subject", result["costs"])
                self.assertEqual([], result["peace_context"]["terms"])
                self.assertNotIn("frame_thread",
                                 json.dumps(result, ensure_ascii=False))

    def test_requested_countries_conflict_is_rejected_by_production_validator(self):
        for action_id in ("release_subject", "transfer_subject"):
            with self.subTest(action_id=action_id):
                event = copy.deepcopy(self.cases[action_id]["event"])
                # The native record says discovery, but the optional list
                # claims a concrete candidate.  The complete validator must
                # reject that mismatch instead of silently dropping the list.
                event["native_subject_terms"]["requested_countries"] = ["NEV"]
                self.assertFalse(
                    ObserverSession._valid_native_peace_subject_offer_query(
                        event, action_id, event["actor"], event["recipient"],
                        event["phase"], event["date_raw"],
                        self._subject_selection(event), event["query_id"],
                        event["session_id"]))

    def test_selected_but_unmatched_subject_and_core_have_unavailable_costs(self):
        subject = copy.deepcopy(self.cases["release_subject"]["event"])
        native_subject = subject["native_subject_terms"]
        native_subject.update({
            "requested_country": "TYR",
            "requested_countries": ["TYR"],
            "selection_requested": True,
            "requested_candidate_found": False,
            "selected_term_count": 0,
            "parameters_matched": False,
            "selection_applied": False,
            "selection_delta_available": False,
            "selection_delta_raw": None,
            "reason_code": "NATIVE_PEACE_SUBJECT_CANDIDATE_NOT_FOUND",
        })
        self.assertTrue(
            ObserverSession._valid_native_peace_subject_offer_query(
                subject, "release_subject", subject["actor"],
                subject["recipient"], subject["phase"], subject["date_raw"],
                self._subject_selection(subject, "TYR"),
                subject["query_id"], subject["session_id"]))
        subject_projected = project_event_consequences(
            subject, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(subject_projected)
        assert subject_projected is not None
        self.assertIs(subject_projected["requested_terms_applied"], False)
        subject_result = self._public(
            subject, "release_subject",
            self._parameters(subject, [{"action_id": "release_subject",
                                        "country": "TYR"}]))
        self.assertFalse(subject_result["parameters"]["complete"])
        self.assertEqual("unknown", subject_result["costs"]["status"])
        self.assertNotIn("native_subject", subject_result["costs"])

        core = copy.deepcopy(self.cases["return_core"]["event"])
        native_core = core["native_core_terms"]
        native_core.update({
            "requested_core_owner": "FRA",
            "requested_province_ids": [88],
            "selection_requested": True,
            "requested_candidates_found": False,
            "selected_term_count": 0,
            "parameters_matched": False,
            "selection_applied": False,
            "selection_delta_available": False,
            "selection_delta_raw": None,
        })
        self.assertTrue(
            ObserverSession._valid_native_peace_core_offer_query(
                core, "return_core", core["actor"], core["recipient"],
                core["phase"], core["date_raw"],
                self._core_selection(core, [88], "FRA"), core["query_id"],
                core["session_id"]))
        core_projected = project_event_consequences(core, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(core_projected)
        assert core_projected is not None
        self.assertIs(core_projected["requested_terms_applied"], False)
        core_result = self._public(
            core, "return_core",
            self._parameters(core, [{"action_id": "return_core",
                                     "province_ids": [88],
                                     "core_owner": "FRA"}]))
        self.assertFalse(core_result["parameters"]["complete"])
        self.assertEqual("unknown", core_result["costs"]["status"])
        self.assertNotIn("native_core", core_result["costs"])

    def test_full_annex_selection_applied_without_parameters_matched_is_applied(self):
        event = copy.deepcopy(self.cases["full_annexation"]["event"])
        native = event["native_annexation"]
        native["selection_requested"] = True
        native["selection_applied"] = True
        native.pop("parameters_matched", None)
        projected = project_event_consequences(event, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertIs(projected["requested_terms_applied"], True)
        self.assertIsNone(projected["reason_code"])


if __name__ == "__main__":
    unittest.main()
