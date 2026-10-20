from __future__ import annotations

import copy
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession, _PEACE_EXECUTION_ACTIONS
from bridge.diplomacy_catalog import ACTIONS
from bridge.peace_core import (
    CoreQueryError, build_query14_wire, normalize_core_query_parameters,
    project_native_core_terms, validate_native_core_offer_query)


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"
DATE_RAW = 56548944
QUERY_ID = "inspect_core_test"
SESSION_ID = "session_core_test"


def _common_event(action_id: str, direction: str = "demand") -> dict:
    return {
        "event": "native_peace_core_offer_query",
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
        "peace_context": {
            "war_id": WAR_ID, "direction": direction, "terms": []},
    }


def _core_event(*, action_id: str = "return_core", discovery: bool = False,
                matched: bool = True) -> tuple[dict, dict]:
    if discovery:
        ids: list[int] = []
        owner = None
        rows = [{
            "province_id": 173, "name": "Straßburg".encode().hex(), "name_readable": True,
            "core_owner": "AMG", "province_owner": "ENG",
            "selected": False, "record_complete": True,
        }]
        native = {
            "action_id": action_id, "candidate_count": 1,
            "candidate_enumeration_complete": True, "candidates": rows,
            "requested_core_owner": owner, "requested_province_ids": ids,
            "selection_requested": False, "requested_candidates_found": False,
            "selected_term_count": 0, "parameters_matched": False,
            "selection_applied": False, "selection_records_complete": True,
            "action_copy_matched": True, "selection_delta_available": False,
            "selection_delta_raw": None,
        }
    else:
        ids = [173, 177]
        owner = "ENG"
        rows = [{
            "province_id": province_id, "name": f"Province {province_id}".encode().hex(),
            "name_readable": True, "core_owner": owner,
            "province_owner": "ENG", "selected": matched,
            "record_complete": True,
        } for province_id in ids]
        native = {
            "action_id": action_id, "candidate_count": len(rows),
            "candidate_enumeration_complete": True, "candidates": rows,
            "requested_core_owner": owner, "requested_province_ids": ids,
            "selection_requested": True,
            "requested_candidates_found": matched,
            "selected_term_count": len(ids) if matched else 0,
            "parameters_matched": matched, "selection_applied": matched,
            "selection_records_complete": True,
            "action_copy_matched": True,
            "selection_delta_available": matched,
            "selection_delta_raw": 10 if matched else None,
        }
    event = _common_event(action_id)
    event["native_core_terms"] = native
    event["full_rules_complete"] = True
    return event, {
        "action_id": action_id, "war_id": WAR_ID, "direction": "demand",
        "province_ids": ids, "core_owner": owner,
        "discovery": discovery,
    }


class _NoCoreCapabilitySession:
    def health(self) -> dict:
        return {"status": "ready", "state_id": "state", "date_raw": DATE_RAW,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset()


class _CoreCapabilitySession(_NoCoreCapabilitySession):
    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({"native_peace_core_terms_query"})

    def inspect_peace_core_offer(self, action_id: str, actor: str,
                                 recipient: str, phase: str,
                                 selection: dict) -> dict:
        event, _ = _core_event(
            action_id=action_id, discovery=not selection["province_ids"])
        return ObserverSession._semantic_peace_core_offer_query(event)


class PeaceCoreQueryTests(unittest.TestCase):
    def test_normalizer_accepts_discovery_and_selected_without_role_binding(self):
        discovery = normalize_core_query_parameters(
            "return_core", ACTOR, RECIPIENT, "initiate", {
                "peace_context": {"war_id": WAR_ID, "terms": []}})
        self.assertTrue(discovery["discovery"])
        selected = normalize_core_query_parameters(
            "revoke_core", ACTOR, RECIPIENT, "initiate", {
                "peace_context": {"war_id": WAR_ID, "direction": "offer",
                                   "terms": [{
                                       "action_id": "revoke_core",
                                       "province_ids": [175, 177],
                                       "core_owner": "AMG",
                                   }]}})
        self.assertEqual("AMG", selected["core_owner"])
        self.assertEqual([175, 177], selected["province_ids"])

    def test_normalizer_rejects_malformed_core_parameters(self):
        invalid = (
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "revoke_core", "province_ids": [],
                 "core_owner": "ENG"}]}},
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "return_core", "province_ids": [1, 1],
                 "core_owner": "ENG"}]}},
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "return_core", "province_ids": [1],
                 "core_owner": "eng"}]}},
            {"peace_context": {"war_id": WAR_ID, "terms": [
                {"action_id": "return_core", "province_ids": [1],
                 "core_owner": "ENG", "extra": True}]}},
        )
        for parameters in invalid:
            with self.subTest(parameters=parameters):
                with self.assertRaisesRegex(
                        CoreQueryError, "QUERY_PEACE_CORE_PARAMETERS_INVALID"):
                    normalize_core_query_parameters(
                        "return_core", ACTOR, RECIPIENT, "initiate", parameters)

    def test_query14_wire_uses_empty_placeholders_and_no_execution_fields(self):
        selection = normalize_core_query_parameters(
            "return_core", ACTOR, RECIPIENT, "initiate", {
                "peace_context": {"war_id": WAR_ID, "terms": []}})
        wire = build_query14_wire(
            0x1234, QUERY_ID, ACTOR, RECIPIENT, DATE_RAW, 999, selection)
        self.assertEqual(
            f"EU4DIP_QUERY14 1234 {QUERY_ID} return_core FRA ENG {DATE_RAW} 999 "
            f"{WAR_ID} demand - -\n", wire)
        self.assertNotIn("term_mask", wire)
        self.assertNotIn("amount", wire)

    def test_discovery_validation_and_projection_keep_legality_unselected(self):
        event, selection = _core_event(discovery=True)
        self.assertTrue(ObserverSession._valid_native_peace_core_offer_query(
            event, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))
        projected = ObserverSession._semantic_peace_core_offer_query(event)
        self.assertEqual([], projected["peace_context"]["terms"])
        self.assertFalse(projected["parameters_matched"])
        self.assertEqual(1, projected["native_core_terms"]["candidate_count"])
        self.assertEqual("Straßburg", projected["native_core_terms"]["candidates"][0]["name"])

    def test_selected_validation_projection_and_delta_are_same_event(self):
        event, selection = _core_event()
        self.assertTrue(validate_native_core_offer_query(
            event, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID,
            common_validator=lambda common: ObserverSession
            ._valid_native_peace_empty_offer_inspection(
                common, "white_peace", ACTOR, RECIPIENT, "initiate", DATE_RAW,
                WAR_ID, QUERY_ID, SESSION_ID)))
        projected = ObserverSession._semantic_peace_core_offer_query(event)
        self.assertEqual(
            [{"action_id": "return_core", "province_ids": [173, 177],
              "core_owner": "ENG"}], projected["peace_context"]["terms"])
        public = projected["native_core_terms"]
        self.assertEqual(10, public["selection_delta_raw"])
        self.assertTrue(public["selection_delta_available"])

    def test_tampered_core_row_or_request_copy_is_rejected(self):
        event, selection = _core_event()
        wrong_count = copy.deepcopy(event)
        wrong_count["native_core_terms"]["selected_term_count"] = 1
        self.assertFalse(ObserverSession._valid_native_peace_core_offer_query(
            wrong_count, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))
        tampered = copy.deepcopy(event)
        tampered["native_core_terms"]["candidates"][0]["core_owner"] = "FRA"
        self.assertFalse(ObserverSession._valid_native_peace_core_offer_query(
            tampered, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))
        tampered = copy.deepcopy(event)
        tampered["native_core_terms"]["requested_province_ids"] = [177]
        self.assertFalse(ObserverSession._valid_native_peace_core_offer_query(
            tampered, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))
        tampered = copy.deepcopy(event)
        tampered["native_core_terms"]["candidate_count"] = 1
        self.assertFalse(ObserverSession._valid_native_peace_core_offer_query(
            tampered, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, QUERY_ID, SESSION_ID))

    def test_catalog_and_execution_boundary_requires_core_capability_ack(self):
        shared_action_ids = [
            "demand_ducats", "cede_province", "war_reparations",
            "transfer_trade_power", "concede_defeat", "annul_treaties",
            "humiliate_rival", "show_strength", "force_religion",
            "return_core", "revoke_core", "release_subject",
            "transfer_subject", "release_nation", "force_vassalization",
            "form_personal_union", "grant_independence", "full_annexation",
        ]
        for action_id in ("return_core", "revoke_core"):
            description = ACTIONS[action_id].describe()
            terms = description["parameter_definitions"]["peace_context.terms"]
            self.assertEqual(18, terms["max_length"])
            self.assertEqual(shared_action_ids, terms["allowed_action_ids"])
            self.assertEqual("unimplemented",
                             description["phases"]["initiate"]["execute"])
            self.assertIn(action_id, _PEACE_EXECUTION_ACTIONS)
        tools = DiplomacyTools(None, _NoCoreCapabilitySession())
        actions = {row["action_id"]: row for row in tools.list_diplomatic_actions(
            category="peace")["actions"]}
        for action_id in ("return_core", "revoke_core"):
            initiate = actions[action_id]["phases"]["initiate"]
            self.assertEqual("unimplemented", initiate["query"])
            self.assertEqual("unimplemented", initiate["execute"])

    def test_public_inspection_routes_query_only_core_selection(self):
        tools = DiplomacyTools(None, _CoreCapabilitySession())
        result = tools.inspect_diplomatic_action(
            "return_core", ACTOR, RECIPIENT, parameters={
                "peace_context": {"war_id": WAR_ID, "direction": "demand",
                                   "terms": [{
                                       "action_id": "return_core",
                                       "province_ids": [173, 177],
                                       "core_owner": "ENG",
                                   }]}})
        self.assertEqual("native_peace_core_offer_query",
                         result["interface_support"]["query"])
        self.assertEqual("available", result["legality"]["status"])
        self.assertEqual("unimplemented", result["interface_support"]["execute"])
        self.assertEqual("ENG", result["native_core_terms"][
            "requested_core_owner"])

    def test_projector_drops_native_private_fields(self):
        event, _ = _core_event()
        event["native_core_terms"]["candidates"][0]["private_rva"] = 123
        # The strict event validator rejects an unexpected private field before
        # projection; projection itself only copies the documented public row.
        self.assertFalse(ObserverSession._valid_native_peace_core_offer_query(
            event, "return_core", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            _core_event()[1], QUERY_ID, SESSION_ID))
        public = project_native_core_terms(_core_event()[0]["native_core_terms"])
        self.assertNotIn("private_rva", public["candidates"][0])


if __name__ == "__main__":
    unittest.main()
