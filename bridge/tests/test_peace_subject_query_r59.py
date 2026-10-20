from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import (
    DiplomacyTools,
    ObserverSession,
    _normalize_peace_subject_query_parameters,
)
from bridge.diplomacy_catalog import ACTIONS
from bridge.native_text import EU4_ESCAPE_CODEC


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"
DATE_RAW = 56549088
QUERY_ID = "inspect_subject_test"
SESSION_ID = "session_subject_test"
REAL_FIXTURE = Path(__file__).parent / "fixtures" / "peace_subject_r59_real.json"


def _common_event(action_id: str, direction: str = "demand") -> dict:
    return {
        "event": "native_peace_subject_offer_query",
        "family": "peace",
        "query_id": QUERY_ID,
        "session_id": SESSION_ID,
        "action_id": action_id,
        "actor": ACTOR,
        "recipient": RECIPIENT,
        "phase": "initiate",
        "date_raw": DATE_RAW,
        "war_id": WAR_ID,
        "direction": direction,
        "identity_scope": "observer_session",
        "query_complete": True,
        "native_offer_inspected": True,
        "pair_at_war": True,
        "unique_shared_war": True,
        "offer_constructed": True,
        "action_constructed": True,
        "participant_copy_verified": True,
        "offer_identity_verified": True,
        "object_unchanged": True,
        "cleanup_verified": True,
        "validity_called": True,
        "common_gate_checked": True,
        "initiation_gate_checked": True,
        "native_validity": True,
        "common_action_gate": True,
        "initiation_gate": True,
        "native_wrapper_gate_checked": True,
        "native_wrapper_gate": True,
        "wrapper_identity_verified": True,
        "wrapper_payload_unchanged": True,
        "native_diagnostic_hex": "",
        "diagnostic_readable": True,
        "diagnostic_truncated": False,
        "common_diagnostic_hex": "",
        "common_diagnostic_readable": True,
        "common_diagnostic_truncated": False,
        "send_diagnostic_hex": "",
        "send_diagnostic_readable": True,
        "send_diagnostic_truncated": False,
        "full_rules_complete": True,
        "reasons_complete": False,
        "submitted": False,
        "peace_context": {"war_id": WAR_ID, "direction": direction,
                           "terms": []},
    }


def _subject_event(*, action_id: str = "release_subject",
                   direction: str = "demand", discovery: bool = False,
                   matched: bool = True) -> tuple[dict, dict]:
    country = None if discovery else "TYR"
    rows = ([{"country": "TYR", "selected": False,
              "record_complete": True},
             {"country": "AUV", "selected": False,
              "record_complete": True}]
            if discovery else
            [{"country": "TYR", "selected": matched,
              "record_complete": True}])
    native = {
        "action_id": action_id,
        "candidates": rows,
        "candidate_count": len(rows),
        "candidate_enumeration_complete": True,
        "selection_requested": not discovery,
        "requested_country": country,
        "requested_candidate_found": matched if not discovery else False,
        "selected_term_count": 1 if matched and not discovery else 0,
        "parameters_matched": matched if not discovery else False,
        "selection_applied": matched if not discovery else False,
        "selection_records_complete": True,
        "action_copy_matched": True,
        "selection_delta_available": matched and not discovery,
        "selection_delta_raw": 8 if matched and not discovery else None,
        "reason_code": None if matched or discovery else
        "NATIVE_PEACE_SUBJECT_CANDIDATE_NOT_FOUND",
    }
    event = _common_event(action_id, direction)
    event["native_subject_terms"] = native
    return event, {
        "action_id": action_id, "war_id": WAR_ID, "direction": direction,
        "country": country, "discovery": discovery,
    }


class _SubjectCapabilitySession:
    def __init__(self, capabilities=None):
        self._capabilities = frozenset(capabilities or {
            "native_peace_subject_terms_query"})

    def health(self) -> dict:
        return {"status": "ready", "state_id": "state", "date_raw": DATE_RAW,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self._capabilities


class PeaceSubjectQueryTests(unittest.TestCase):
    def test_normalizer_discovery_and_selected_shape(self):
        discovery = _normalize_peace_subject_query_parameters(
            "release_subject", ACTOR, RECIPIENT, "initiate", {
                "peace_context": {"war_id": WAR_ID, "terms": []}})
        self.assertTrue(discovery["discovery"])
        selected = _normalize_peace_subject_query_parameters(
            "transfer_subject", ACTOR, RECIPIENT, "initiate", {
                "peace_context": {"war_id": WAR_ID, "direction": "offer",
                                   "terms": [{"action_id": "transfer_subject",
                                              "country": "AUV"}]}})
        self.assertEqual("AUV", selected["country"])
        self.assertEqual("offer", selected["direction"])

    def test_normalizer_rejects_wrong_action_or_extra_fields(self):
        invalid = (
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "transfer_subject", "country": "TYR"}]}},
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "release_subject", "country": "eng"}]}},
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "release_subject", "country": "TYR",
                 "extra": True}]}},
        )
        for parameters in invalid:
            with self.subTest(parameters=parameters):
                with self.assertRaisesRegex(
                        ValueError, "QUERY_PEACE_SUBJECT_PARAMETERS_INVALID"):
                    _normalize_peace_subject_query_parameters(
                        "release_subject", ACTOR, RECIPIENT, "initiate", parameters)

    def test_query16_validation_and_selected_projection(self):
        event, selection = _subject_event()
        self.assertTrue(ObserverSession._valid_native_peace_subject_offer_query(
            event, "release_subject", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))
        projected = ObserverSession._semantic_peace_subject_offer_query(event)
        self.assertEqual(
            [{"action_id": "release_subject", "country": "TYR"}],
            projected["peace_context"]["terms"])
        self.assertEqual(8, projected["native_subject_terms"]["selection_delta_raw"])

    def test_discovery_stays_unknown_and_tampering_fails(self):
        event, selection = _subject_event(discovery=True)
        self.assertTrue(ObserverSession._valid_native_peace_subject_offer_query(
            event, "release_subject", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))
        projected = ObserverSession._semantic_peace_subject_offer_query(event)
        self.assertEqual([], projected["peace_context"]["terms"])
        self.assertFalse(projected["parameters_matched"])
        tampered = copy.deepcopy(event)
        tampered["native_subject_terms"]["candidates"][0]["selected"] = True
        self.assertFalse(ObserverSession._valid_native_peace_subject_offer_query(
            tampered, "release_subject", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))

    def test_missing_candidate_is_unavailable_in_public_projection(self):
        event, selection = _subject_event(matched=False)
        native = ObserverSession._semantic_peace_subject_offer_query(event)
        inspection = {
            "interface_support": {"query": "catalog_only", "execute": "unimplemented"},
            "acceptance": {"items": []},
            "costs": {},
            "authorization": {},
            "session": {},
        }
        public = DiplomacyTools._apply_peace_subject_query(
            inspection, native, {"peace_context": {
                "war_id": WAR_ID, "direction": "demand",
                "terms": [{"action_id": "release_subject", "country": "TYR"}]}},
            selection)
        self.assertEqual("unavailable", public["legality"]["status"])
        self.assertEqual(
            "NATIVE_PEACE_SUBJECT_CANDIDATE_NOT_FOUND",
            public["legality"]["reasons"][0]["code"])
        self.assertEqual("unimplemented", public["interface_support"]["execute"])

    def test_catalog_exposes_query16_country_form_without_execute(self):
        for action_id in ("release_subject", "transfer_subject"):
            described = ACTIONS[action_id].describe()
            definitions = described["parameter_definitions"]
            self.assertEqual(("country",), ACTIONS[action_id].parameters[1:])
            self.assertEqual("peace",
                             described["native_identifier"])
            self.assertEqual(3, len(described["inspection_parameter_forms"]))
            self.assertIn("peace_context.terms[0].country", definitions)
            self.assertEqual("unimplemented",
                             described["phases"]["initiate"]["execute"])

    def test_list_does_not_advertise_subject_execution_from_generic_ack(self):
        tools = DiplomacyTools(
            None,
            _SubjectCapabilitySession({
                "native_peace_subject_terms_query",
                "native_peace_submission",
            }),
        )
        listed = tools.list_diplomatic_actions(
            ACTOR, RECIPIENT, category="peace")
        by_id = {item["action_id"]: item for item in listed["actions"]}
        for action_id in ("release_subject", "transfer_subject"):
            initiate = by_id[action_id]["phases"]["initiate"]
            self.assertEqual(
                "native_peace_subject_offer_query", initiate["selected_query"])
            self.assertEqual("QUERY16", initiate["selected_query_protocol"])
            self.assertEqual("unimplemented", initiate["execute"])


def _load_real_subject_fixture() -> dict:
    return json.loads(REAL_FIXTURE.read_text(encoding="utf-8"))


class _RealSubjectSession:
    """Replay one stored native QUERY16 event through the public route."""

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
        return frozenset({"native_peace_subject_terms_query"})

    def inspect_peace_subject_offer(self, action_id: str, actor: str,
                                    recipient: str, phase: str,
                                    selection: dict) -> dict:
        return ObserverSession._semantic_peace_subject_offer_query(
            copy.deepcopy(self.event), EU4_ESCAPE_CODEC)


class PeaceSubjectR59RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_real_subject_fixture()

    @staticmethod
    def _selection(case: dict) -> dict:
        request = case["input"]
        context = request["parameters"]["peace_context"]
        terms = context["terms"]
        term = terms[0] if terms else None
        return {
            "action_id": request["action_id"],
            "war_id": context["war_id"],
            "direction": context["direction"],
            "country": term["country"] if term else None,
            "discovery": term is None,
        }

    def _validate(self, case: dict, event: dict | None = None) -> None:
        source = event or case["event"]
        request = case["input"]
        self.assertTrue(
            ObserverSession._valid_native_peace_subject_offer_query(
                source, request["action_id"], source["actor"],
                source["recipient"], source["phase"], source["date_raw"],
                self._selection(case), source["query_id"],
                source["session_id"]),
            case["name"],
        )

    def _public_result(self, case: dict) -> dict:
        event = case["event"]
        request = case["input"]
        tools = DiplomacyTools(None, _RealSubjectSession(event))
        return tools.inspect_diplomatic_action(
            request["action_id"], event["actor"], event["recipient"],
            phase=event["phase"], parameters=request["parameters"])

    def test_real_events_validate_and_project_native_selection(self):
        self.assertEqual(10, len(self.fixture["cases"]))
        self.assertRegex(self.fixture["source"]["events_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(self.fixture["source"]["report_sha256"], r"^[0-9a-f]{64}$")
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assertRegex(case["source"]["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(case["source"]["line"], 0)
                self._validate(case)
                projected = ObserverSession._semantic_peace_subject_offer_query(
                    case["event"], EU4_ESCAPE_CODEC)
                native = projected["native_subject_terms"]
                expected = case["expected"]
                self.assertEqual(case["input"]["action_id"], native["action_id"])
                self.assertEqual(expected["candidate_count"],
                                 native["candidate_count"])
                self.assertEqual(expected["candidate_countries"],
                                 [row["country"] for row in native["candidates"]])
                self.assertEqual(expected["selected_term_count"],
                                 native["selected_term_count"])
                self.assertEqual(expected["selection_delta_raw"],
                                 native["selection_delta_raw"])
                evaluation = projected["native_evaluation"]
                self.assertEqual(expected["evaluation_factor_count"],
                                 evaluation["factor_native_count"])
                self.assertEqual(expected["evaluation_score_raw"],
                                 evaluation["score_raw"])
                if expected["country"] is None:
                    self.assertEqual([], projected["peace_context"]["terms"])
                elif expected["legality_status"] == "available":
                    self.assertEqual([{
                        "action_id": case["input"]["action_id"],
                        "country": expected["country"],
                    }], projected["peace_context"]["terms"])
                else:
                    self.assertEqual([], projected["peace_context"]["terms"])
                self.assertNotIn("frame_thread",
                                 json.dumps(projected, ensure_ascii=False))

    def test_real_selected_public_projection_separates_cost_and_factors(self):
        expected = {
            "release_subject-demand-TYR": (-100, 9, 5),
            "release_subject-offer-AUV": (-28, 7, 6),
        }
        for case in self.fixture["cases"]:
            if case["input"]["expected_kind"] != "selected":
                continue
            with self.subTest(case=case["name"]):
                result = self._public_result(case)
                native_total, factor_count, cost_raw = expected[case["name"]]
                self.assertEqual("available", result["legality"]["status"])
                self.assertEqual(
                    "NATIVE_PEACE_SUBJECT_QUERY_RULES_TRUE",
                    result["legality"]["reasons"][0]["code"])
                self.assertEqual(native_total,
                                 result["acceptance"]["native_total"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                self.assertTrue(result["acceptance"]["details_complete"])
                items = result["acceptance"]["items"]
                self.assertEqual(factor_count, len(items))
                self.assertTrue(all(item["text_decoded"] and item["text"]
                                    for item in items))
                native_cost = result["costs"]["native_subject"]
                self.assertEqual(cost_raw,
                                 native_cost["items"][0]["amount_raw"])
                self.assertEqual("native_war_score_raw",
                                 native_cost["items"][0]["unit"])
                self.assertFalse(native_cost["items"][0]["scale_verified"])
                self.assertEqual(
                    cost_raw,
                    result["costs"]["native_evaluation"]["aggregate_score_raw"])
                self.assertTrue(result["parameters"]["complete"])
                self.assertEqual("unimplemented",
                                 result["interface_support"]["execute"])
                self.assertNotIn("frame_thread",
                                 json.dumps(result, ensure_ascii=False))

    def test_real_discovery_and_absent_do_not_predict_acceptance(self):
        for case in self.fixture["cases"]:
            if case["input"]["expected_kind"] == "selected":
                continue
            with self.subTest(case=case["name"]):
                result = self._public_result(case)
                expected = case["expected"]
                self.assertEqual(expected["legality_status"],
                                 result["legality"]["status"])
                self.assertEqual(expected["reason_code"],
                                 result["legality"]["reasons"][0]["code"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                self.assertIsNone(result["acceptance"]["native_total"])
                self.assertEqual([], result["acceptance"]["items"])
                self.assertNotIn("native_subject", result["costs"])
                self.assertNotIn("native_evaluation", result["costs"])
                self.assertEqual([], result["peace_context"]["terms"])
                self.assertFalse(result["parameters"]["complete"])

    def test_real_selected_event_tampering_is_rejected(self):
        selected = next(case for case in self.fixture["cases"]
                        if case["name"] == "release_subject-demand-TYR")
        wrong_count = copy.deepcopy(selected["event"])
        wrong_count["native_subject_terms"]["selected_term_count"] = 0
        self.assertFalse(
            ObserverSession._valid_native_peace_subject_offer_query(
                wrong_count, "release_subject", wrong_count["actor"],
                wrong_count["recipient"], wrong_count["phase"],
                wrong_count["date_raw"], self._selection(selected),
                wrong_count["query_id"], wrong_count["session_id"]))

        wrong_country = copy.deepcopy(selected["event"])
        wrong_country["native_subject_terms"]["candidates"][0]["country"] = "ENG"
        self.assertFalse(
            ObserverSession._valid_native_peace_subject_offer_query(
                wrong_country, "release_subject", wrong_country["actor"],
                wrong_country["recipient"], wrong_country["phase"],
                wrong_country["date_raw"], self._selection(selected),
                wrong_country["query_id"], wrong_country["session_id"]))


if __name__ == "__main__":
    unittest.main()
