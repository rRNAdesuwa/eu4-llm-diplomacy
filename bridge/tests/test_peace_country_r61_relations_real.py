from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from bridge.diplomacy import (
    COUNTRY_SELECTION_KEYS,
    DiplomacyTools,
    ObserverSession,
)
from bridge.native_text import EU4_ESCAPE_CODEC


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_country_r61_relations_real.json")


class PeaceCountryR61RelationsRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        source = cls.fixture["source"]
        cls.source_path = ROOT / Path(source["events_path"])
        cls.source_bytes = cls.source_path.read_bytes()
        cls.source_lines = cls.source_bytes.splitlines()

    def _assert_source_event(self, key: str) -> dict:
        source = self.fixture["source"]
        self.assertTrue(self.source_path.is_file(), self.source_path)
        self.assertEqual(source["events_size"], len(self.source_bytes))
        self.assertEqual(source["events_sha256"],
                         hashlib.sha256(self.source_bytes).hexdigest())
        meta = source["line_records"][key]
        raw = self.source_lines[meta["line"] - 1]
        self.assertEqual(meta["bytes"], len(raw))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        if key == "query":
            self.assertEqual(self.fixture["query"]["event"], event)
        elif key.startswith("outbound"):
            self.assertEqual(
                self.fixture["outbound"][
                    "event" if key == "outbound_submission" else "result_event"],
                event)
        else:
            case_name = "reject" if "reject" in key else "accept"
            case = self.fixture["inbound_cases"][case_name]
            event_key = {
                "reject_inspection": "inspection",
                "reject_submission": "submission",
                "reject_response": "response",
                "accept_inspection": "inspection",
                "accept_submission": "submission",
                "accept_response": "response",
            }[key]
            self.assertEqual(case[event_key], event)
        return event

    def _assert_union_source_event(self, key: str) -> dict:
        source = self.fixture["union_source"]
        source_path = ROOT / Path(source["events_path"])
        source_bytes = source_path.read_bytes()
        source_lines = source_bytes.splitlines()
        self.assertTrue(source_path.is_file(), source_path)
        self.assertEqual(source["events_size"], len(source_bytes))
        self.assertEqual(source["events_sha256"],
                         hashlib.sha256(source_bytes).hexdigest())
        meta = source["line_records"][key]
        raw = source_lines[meta["line"] - 1]
        self.assertEqual(meta["bytes"], len(raw))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        if key == "query":
            self.assertEqual(self.fixture["union"]["query"]["event"], event)
        elif key.startswith("outbound"):
            self.assertEqual(
                self.fixture["union"]["outbound"][
                    "event" if key == "outbound_submission" else "result_event"],
                event)
        else:
            case_name = "reject" if "reject" in key else "accept"
            case = self.fixture["union"]["inbound_cases"][case_name]
            event_key = {
                "reject_inspection": "inspection",
                "reject_submission": "submission",
                "reject_response": "response",
                "accept_inspection": "inspection",
                "accept_submission": "submission",
                "accept_response": "response",
            }[key]
            self.assertEqual(case[event_key], event)
        return event

    def _assert_independence_source_event(self, key: str) -> dict:
        source = self.fixture["independence_source"]
        source_path = ROOT / Path(source["events_path"])
        source_bytes = source_path.read_bytes()
        source_lines = source_bytes.splitlines()
        self.assertTrue(source_path.is_file(), source_path)
        self.assertEqual(source["events_size"], len(source_bytes))
        self.assertEqual(source["events_sha256"],
                         hashlib.sha256(source_bytes).hexdigest())
        meta = source["line_records"][key]
        raw = source_lines[meta["line"] - 1]
        self.assertEqual(meta["bytes"], len(raw))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        self.assertEqual(self.fixture["independence"]["query"]["event"], event)
        return event

    def _assert_grant_positive_source_event(self, key: str) -> dict:
        source = self.fixture["grant_positive_source"]
        source_path = ROOT / Path(source["events_path"])
        source_bytes = source_path.read_bytes()
        source_lines = source_bytes.splitlines()
        self.assertTrue(source_path.is_file(), source_path)
        self.assertEqual(source["events_size"], len(source_bytes))
        self.assertEqual(source["events_sha256"],
                         hashlib.sha256(source_bytes).hexdigest())
        meta = source["line_records"][key]
        raw = source_lines[meta["line"] - 1]
        self.assertEqual(meta["bytes"], len(raw))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        if key == "query":
            self.assertEqual(self.fixture["grant_positive"]["query"]["event"],
                             event)
        elif key.startswith("outbound"):
            self.assertEqual(
                self.fixture["grant_positive"]["outbound"][
                    "event" if key == "outbound_submission" else "result_event"],
                event)
        else:
            case_name = ("inbound_reject" if "reject" in key
                         else "inbound_accept")
            case = self.fixture["grant_positive"][case_name]
            self.assertEqual(case[
                {"reject_inspection": "inspection",
                 "reject_submission": "submission",
                 "reject_response": "response",
                 "accept_inspection": "inspection",
                 "accept_submission": "submission",
                 "accept_response": "response"}[key]], event)
        return event

    def _assert_grant_004_source_event(self, key: str) -> dict:
        source = self.fixture["grant_004_source"]
        source_path = ROOT / Path(source["events_path"])
        source_bytes = source_path.read_bytes()
        source_lines = source_bytes.splitlines()
        self.assertTrue(source_path.is_file(), source_path)
        self.assertEqual(source["events_size"], len(source_bytes))
        self.assertEqual(source["events_sha256"],
                         hashlib.sha256(source_bytes).hexdigest())
        meta = source["line_records"][key]
        raw = source_lines[meta["line"] - 1]
        self.assertEqual(meta["bytes"], len(raw))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        event = json.loads(raw.decode("utf-8"))
        case = self.fixture["grant_004"]
        if key == "query":
            self.assertEqual(case["query"]["event"], event)
        elif key == "outbound_submission":
            self.assertEqual(case["outbound"]["event"], event)
        elif key == "outbound_result":
            self.assertEqual(case["outbound"]["result_event"], event)
        else:
            case_name = "reject" if key.startswith("reject_") else "accept"
            inbound = case[f"inbound_{case_name}"]
            event_key = {
                "reject_inspection": "inspection",
                "reject_submission": "submission",
                "reject_response": "response",
                "accept_inspection": "inspection",
                "accept_submission": "submission",
                "accept_response": "response",
            }[key]
            self.assertEqual(inbound[event_key], event)
        return event

    @staticmethod
    def _selection(event: dict, parameters: dict) -> dict:
        fields = ObserverSession._peace_execution_fields(parameters)
        country_fields = ObserverSession._peace_country_execution_fields(
            parameters, event["actor"], event["recipient"])
        assert fields is not None and country_fields is not None
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, trade_power_source,
         trade_power_beneficiary, concede_country, concede_beneficiary,
         annul_country, annul_partners, term_mask) = fields
        selection = {
            "action_id": parameters["peace_context"]["terms"][0]["action_id"],
            "war_id": war_id,
            "direction": direction,
            "amount_raw": amount_raw,
            "province_ids": list(province_ids),
            "beneficiary": beneficiary,
            "source": trade_power_source if "t" in term_mask else "-",
            "payer": reparations_payer,
            "claimant": reparations_claimant,
            "conceding_country": concede_country,
            "concede_beneficiary": concede_beneficiary,
            "annul_country": annul_country or "-",
            "annul_partners": list(annul_partners or []),
            "term_mask": term_mask,
            "return_ids": [], "return_core_owner": None,
            "revoke_ids": [], "revoke_core_owner": None,
            "release_countries": [], "transfer_countries": [],
        }
        selection.update(dict(zip(COUNTRY_SELECTION_KEYS, country_fields)))
        return selection

    @staticmethod
    def _assert_public(value: object, *, query_identity: bool = False) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        markers = ["native_proposal_id", "frame_thread", "native_origin",
                   "native_flags", "native_sequence", "token3c", "date28",
                   "date2c"]
        if not query_identity:
            markers.extend(("session_id", "query_id"))
        for marker in markers:
            if marker in serialized:
                raise AssertionError(f"private marker leaked: {marker}")

    def test_real_query_projection_and_force_vassal_receipt_binding(self):
        query = self._assert_source_event("query")
        params = self.fixture["query"]["input"]["normalized_parameters"]
        selection = self._selection(query, params)
        self.assertTrue(ObserverSession._valid_native_peace_combined_country_offer_query(
            query, query["action_id"], query["actor"], query["recipient"],
            query["phase"], query["date_raw"], selection,
            query["query_id"], query["session_id"]))
        public_query = ObserverSession._semantic_peace_combined_country_offer_query(
            query, EU4_ESCAPE_CODEC)
        self.assertTrue(public_query["query_complete"])
        self.assertTrue(public_query["full_rules_complete"])
        self.assertTrue(public_query["parameters_matched"])
        self.assertEqual("z", public_query["term_mask"])
        vassal = public_query["native_country_terms"]["force_vassalization"]
        self.assertEqual("LEI", vassal["requested_country"])
        self.assertEqual("FRA", vassal["candidates"][0]["extra30"]
                         if "extra30" in vassal["candidates"][0] else "FRA")
        self.assertEqual(11, vassal["selection_delta_raw"])
        self.assertTrue(public_query["native_selected_rules"]["available"])
        self._assert_public(public_query, query_identity=True)

        submission = self._assert_source_event("outbound_submission")
        request = self.fixture["query"]["input"]
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, self.fixture["outbound"]["request_id"],
            submission["session_id"], request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params))
        native_public = ObserverSession._public_native_peace_submission_receipt(
            submission, self.fixture["outbound"]["request_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertIsNotNone(native_public)
        assert native_public is not None
        self.assertEqual("LEI", native_public["vassal_country"])
        self.assertEqual("FRA", native_public["vassal_beneficiary"])
        public = DiplomacyTools._public_peace_submission_receipt(
            native_public, self.fixture["outbound"]["request_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertEqual(native_public, public)
        record = SimpleNamespace(
            payload={"action_id": request["action_id"],
                     "actor": request["actor"],
                     "recipient": request["recipient"],
                     "phase": request["phase"], "parameters": params},
            native_receipt=public,
            request_id=self.fixture["outbound"]["request_id"],
            session_id=submission["session_id"],
        )
        context = DiplomacyTools._native_submission_context(record)
        self.assertIsNotNone(context)
        self._assert_public(public)

    def test_real_outbound_rejection_preserves_vassal_relation(self):
        result = self._assert_source_event("outbound_result")
        request = self.fixture["query"]["input"]
        params = self.fixture["query"]["input"]["normalized_parameters"]
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            result, self.fixture["outbound"]["request_id"],
            result["session_id"], request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params))
        public = ObserverSession._public_native_peace_execution_result(
            result, self.fixture["outbound"]["request_id"], result["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("rejected", public["native_outcome"])
        effect = public["effects"]["country_terms"]["force_vassalization"]
        self.assertEqual("LEI", effect["country"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertTrue(effect["unchanged"])
        self.assertFalse(effect["verified"])
        self.assertFalse(effect["relation_active_after"])
        self.assertFalse(effect["is_overlord_after"])
        self._assert_public(public)

        forged = copy.deepcopy(result)
        forged["effects"]["country_terms"]["force_vassalization"]["verified"] = True
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            forged, self.fixture["outbound"]["request_id"],
            forged["session_id"], request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params))

    def _replay_inbound_case(self, name: str, *, accepted: bool) -> dict:
        case = self.fixture["inbound_cases"][name]
        inspection = self._assert_source_event(f"{name}_inspection")
        submission = self._assert_source_event(f"{name}_submission")
        response = self._assert_source_event(f"{name}_response")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            inspection["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"],
            submission["phase"], submission["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"]))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], inspection["action_id"])
        self.assertEqual(
            [{"action_id": "force_vassalization", "country": "LEI",
              "beneficiary": "FRA"}],
            public_inspection["peace_context"]["terms"])
        public_submission = ObserverSession._public_native_inbound_submission_receipt(
            submission, submission["request_id"], submission["actor"],
            submission["phase"], submission["date_raw"],
            inspection["action_id"])
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"])
        self.assertIsNotNone(public_submission)
        self.assertIsNotNone(public_result)
        assert public_result is not None
        expected = case["expected"]
        self.assertEqual(expected["outcome"], public_result["native_outcome"])
        self.assertEqual(expected["native_state"], public_result["native_state"])
        self.assertEqual(expected["war_after"], public_result["war_after"])
        self.assertEqual(expected["terms_verified"], public_result["terms_verified"])
        effect = public_result["effects"]["country_terms"]["force_vassalization"]
        self.assertEqual("LEI", effect["country"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertEqual(expected["relation_active_before"], effect["relation_active_before"])
        self.assertEqual(expected["relation_active_after"], effect["relation_active_after"])
        self.assertEqual(expected["is_overlord_after"], effect["is_overlord_after"])
        self.assertEqual(expected["subject_type_after"], effect["subject_type_after"])
        self.assertEqual(expected["unchanged"], effect["unchanged"])
        self.assertEqual(expected["verified"], effect["verified"])
        self._assert_public({"inspection": public_inspection,
                             "submission": public_submission,
                             "result": public_result})
        return response

    def test_real_inbound_reject_and_accept_vassal_effects(self):
        self._replay_inbound_case("reject", accepted=False)
        self._replay_inbound_case("accept", accepted=True)

    def test_real_inbound_effect_role_tampering_is_rejected(self):
        for name in ("reject", "accept"):
            response = self._replay_inbound_case(name, accepted=name == "accept")
            case = self.fixture["inbound_cases"][name]
            tamperers = (
                ("country", lambda event: event["effects"]["country_terms"][
                    "force_vassalization"].update({"country": "FRA"})),
                ("beneficiary", lambda event: event["effects"]["country_terms"][
                    "force_vassalization"].update({"beneficiary": "LEI"})),
                ("verified", lambda event: event["effects"]["country_terms"][
                    "force_vassalization"].update({
                        "verified": not event["effects"]["country_terms"][
                            "force_vassalization"]["verified"]})),)
            for label, mutate in tamperers:
                forged = copy.deepcopy(response)
                mutate(forged)
                with self.subTest(case=name, tamper=label):
                    self.assertIsNone(
                        ObserverSession._public_native_inbound_response_result(
                            forged, forged["request_id"], forged["session_id"],
                            forged["actor"], forged["phase"], forged["date_raw"],
                            case["native_proposal_id"], forged["action_id"]))

    def test_real_query_projection_and_personal_union_receipt_binding(self):
        query = self._assert_union_source_event("query")
        params = self.fixture["union"]["query"]["input"][
            "normalized_parameters"]
        selection = self._selection(query, params)
        self.assertTrue(ObserverSession._valid_native_peace_combined_country_offer_query(
            query, query["action_id"], query["actor"], query["recipient"],
            query["phase"], query["date_raw"], selection,
            query["query_id"], query["session_id"]))
        public_query = ObserverSession._semantic_peace_combined_country_offer_query(
            query, EU4_ESCAPE_CODEC)
        self.assertTrue(public_query["query_complete"])
        self.assertTrue(public_query["full_rules_complete"])
        self.assertTrue(public_query["parameters_matched"])
        self.assertEqual("u", public_query["term_mask"])
        union = public_query["native_country_terms"]["form_personal_union"]
        self.assertEqual("LEI", union["requested_country"])
        self.assertEqual(60, union["selection_delta_raw"])
        self.assertTrue(public_query["native_selected_rules"]["available"])
        self._assert_public(public_query, query_identity=True)

        submission = self._assert_union_source_event("outbound_submission")
        request = self.fixture["union"]["query"]["input"]
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, self.fixture["union"]["outbound"]["request_id"],
            submission["session_id"], request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params))
        native_public = ObserverSession._public_native_peace_submission_receipt(
            submission, self.fixture["union"]["outbound"]["request_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertIsNotNone(native_public)
        assert native_public is not None
        self.assertEqual("LEI", native_public["union_country"])
        self.assertEqual("FRA", native_public["union_beneficiary"])
        public = DiplomacyTools._public_peace_submission_receipt(
            native_public, self.fixture["union"]["outbound"]["request_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], params)
        self.assertEqual(native_public, public)
        record = SimpleNamespace(
            payload={"action_id": request["action_id"],
                     "actor": request["actor"], "recipient": request["recipient"],
                     "phase": request["phase"], "parameters": params},
            native_receipt=public,
            request_id=self.fixture["union"]["outbound"]["request_id"],
            session_id=submission["session_id"],
        )
        context = DiplomacyTools._native_submission_context(record)
        self.assertIsNotNone(context)
        self._assert_public(public)

    def test_real_outbound_rejection_preserves_personal_union_relation(self):
        result = self._assert_union_source_event("outbound_result")
        request = self.fixture["union"]["query"]["input"]
        params = self.fixture["union"]["query"]["input"][
            "normalized_parameters"]
        request_id = self.fixture["union"]["outbound"]["request_id"]
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            result, request_id, result["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params))
        public = ObserverSession._public_native_peace_execution_result(
            result, request_id, result["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("rejected", public["native_outcome"])
        effect = public["effects"]["country_terms"]["form_personal_union"]
        self.assertEqual("LEI", effect["country"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertTrue(effect["unchanged"])
        self.assertFalse(effect["verified"])
        self.assertFalse(effect["relation_active_after"])
        self.assertFalse(effect["is_overlord_after"])
        self._assert_public(public)

        forged = copy.deepcopy(result)
        forged["effects"]["country_terms"]["form_personal_union"][
            "verified"] = True
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            forged, request_id, forged["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params))

    def _replay_union_inbound_case(self, name: str) -> dict:
        case = self.fixture["union"]["inbound_cases"][name]
        inspection = self._assert_union_source_event(f"{name}_inspection")
        submission = self._assert_union_source_event(f"{name}_submission")
        response = self._assert_union_source_event(f"{name}_response")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            inspection["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"], submission["phase"],
            submission["date_raw"], inspection["native_proposal_id"],
            inspection["action_id"]))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], inspection["action_id"])
        self.assertEqual(
            [{"action_id": "form_personal_union", "country": "LEI",
              "beneficiary": "FRA"}],
            public_inspection["peace_context"]["terms"])
        public_submission = ObserverSession._public_native_inbound_submission_receipt(
            submission, submission["request_id"], submission["actor"],
            submission["phase"], submission["date_raw"], inspection["action_id"])
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"])
        self.assertIsNotNone(public_submission)
        self.assertIsNotNone(public_result)
        assert public_result is not None
        expected = case["expected"]
        self.assertEqual(expected["outcome"], public_result["native_outcome"])
        self.assertEqual(expected["native_state"], public_result["native_state"])
        self.assertEqual(expected["war_after"], public_result["war_after"])
        self.assertEqual(expected["terms_verified"], public_result["terms_verified"])
        effect = public_result["effects"]["country_terms"]["form_personal_union"]
        self.assertEqual("LEI", effect["country"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertEqual(expected["relation_active_before"], effect["relation_active_before"])
        self.assertEqual(expected["relation_active_after"], effect["relation_active_after"])
        self.assertEqual(expected["is_overlord_after"], effect["is_overlord_after"])
        self.assertEqual(expected["subject_type_after"], effect["subject_type_after"])
        self.assertEqual(expected["unchanged"], effect["unchanged"])
        self.assertEqual(expected["verified"], effect["verified"])
        self._assert_public({"inspection": public_inspection,
                             "submission": public_submission,
                             "result": public_result})
        return response

    def test_real_inbound_reject_and_accept_personal_union_effects(self):
        self._replay_union_inbound_case("reject")
        self._replay_union_inbound_case("accept")

    def test_real_personal_union_effect_role_tampering_is_rejected(self):
        for name in ("reject", "accept"):
            response = self._replay_union_inbound_case(name)
            case = self.fixture["union"]["inbound_cases"][name]
            forged = copy.deepcopy(response)
            forged["effects"]["country_terms"]["form_personal_union"].update(
                {"country": "FRA"})
            with self.subTest(case=name):
                self.assertIsNone(
                    ObserverSession._public_native_inbound_response_result(
                        forged, forged["request_id"], forged["session_id"],
                        forged["actor"], forged["phase"], forged["date_raw"],
                        case["native_proposal_id"], forged["action_id"]))

    def test_real_grant_independence_candidate_absence_is_unavailable(self):
        query = self._assert_independence_source_event("query")
        case = self.fixture["independence"]
        params = case["query"]["input"]["normalized_parameters"]
        selection = self._selection(query, params)
        self.assertTrue(ObserverSession._valid_native_peace_combined_country_offer_query(
            query, query["action_id"], query["actor"], query["recipient"],
            query["phase"], query["date_raw"], selection,
            query["query_id"], query["session_id"]))
        public_query = ObserverSession._semantic_peace_combined_country_offer_query(
            query, EU4_ESCAPE_CODEC)
        independence = public_query["native_country_terms"]["grant_independence"]
        self.assertEqual(case["expected"]["candidate_count"],
                         independence["candidate_count"])
        self.assertTrue(independence["candidate_enumeration_complete"])
        self.assertEqual(case["expected"]["requested_country"],
                         independence["requested_country"])
        self.assertFalse(independence["requested_candidate_found"])
        self.assertEqual(case["expected"]["reason_code"],
                         independence["reason_code"])
        self.assertFalse(public_query["parameters_matched"])
        self.assertFalse(public_query["full_rules_complete"])
        self._assert_public(public_query, query_identity=True)

        inspection = {
            "interface_support": {},
            "costs": {"status": "unknown", "items": [], "complete": False},
            "session": {},
            "acceptance": {
                "applicability": "applicable",
                "prediction_available": False,
                "native_total": None,
                "unit": "unknown",
                "scale_verified": False,
                "predicted_response": "unknown",
                "details_available": False,
                "items": [],
                "complete": False,
            },
        }
        projected = DiplomacyTools._apply_peace_execution_inspection(
            inspection, query, params)
        self.assertEqual(case["expected"]["legality"],
                         projected["legality"]["status"])
        self.assertEqual(case["expected"]["reason_code"],
                         projected["legality"]["reasons"][0]["code"])
        self.assertTrue(projected["legality"]["complete"])
        self.assertEqual(case["expected"]["parameters_complete"],
                         projected["parameters"]["complete"])
        self.assertEqual(0, projected["parameters"]["candidates"][
            "grant_independence"]["candidate_count"])
        self.assertTrue(projected["parameters"]["candidates"][
            "grant_independence"]["candidates_complete"])
        self.assertFalse(projected["acceptance"]["prediction_available"])
        self._assert_public(projected)

    def test_real_grant_independence_query_and_outbound_rejection(self):
        query = self._assert_grant_positive_source_event("query")
        case = self.fixture["grant_positive"]
        params = case["query"]["input"]["normalized_parameters"]
        selection = self._selection(query, params)
        self.assertTrue(ObserverSession._valid_native_peace_combined_country_offer_query(
            query, query["action_id"], query["actor"], query["recipient"],
            query["phase"], query["date_raw"], selection,
            query["query_id"], query["session_id"]))
        public_query = ObserverSession._semantic_peace_combined_country_offer_query(
            query, EU4_ESCAPE_CODEC)
        grant = public_query["native_country_terms"]["grant_independence"]
        self.assertTrue(public_query["query_complete"])
        self.assertTrue(public_query["full_rules_complete"])
        self.assertTrue(public_query["parameters_matched"])
        self.assertEqual("ENG", grant["requested_country"])
        self.assertEqual(30, grant["selection_delta_raw"])
        self.assertTrue(public_query["native_selected_rules"]["available"])
        self._assert_public(public_query, query_identity=True)

        submission = self._assert_grant_positive_source_event(
            "outbound_submission")
        request = case["query"]["input"]
        request_id = case["outbound"]["request_id"]
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, request_id, submission["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params))
        receipt = ObserverSession._public_native_peace_submission_receipt(
            submission, request_id, request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual("ENG", receipt["independence_country"])
        public_receipt = DiplomacyTools._public_peace_submission_receipt(
            receipt, request_id, request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params)
        self.assertEqual(receipt, public_receipt)
        self._assert_public(public_receipt)

        result = self._assert_grant_positive_source_event("outbound_result")
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            result, request_id, result["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params))
        public = ObserverSession._public_native_peace_execution_result(
            result, request_id, result["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params)
        self.assertIsNotNone(public)
        assert public is not None
        effect = public["effects"]["country_terms"]["grant_independence"]
        self.assertEqual("FRA", effect["country"])
        self.assertEqual("ENG", effect["overlord"])
        self.assertTrue(effect["unchanged"])
        self.assertFalse(effect["verified"])
        self.assertEqual(1, effect["overlord_count_before"])
        self.assertEqual(1, effect["overlord_count_after"])
        corrections = public.get("effect_flag_corrections", [])
        self.assertTrue(any(
            item.get("field") ==
            "effects.country_terms.grant_independence.unchanged"
            and item.get("native_value") is False
            and item.get("value") is True
            for item in corrections))
        self._assert_public(public)

        for field, mutate in (
                ("relation_active_after", lambda effect: effect.update(
                    {"relation_active_after": False, "unchanged": True})),
                ("overlord_count_after", lambda effect: effect.update(
                    {"overlord_count_after": 2, "unchanged": True}))):
            forged = copy.deepcopy(result)
            mutate(forged["effects"]["country_terms"]["grant_independence"])
            with self.subTest(tamper=field):
                self.assertIsNone(ObserverSession._public_native_peace_execution_result(
                    forged, request_id, forged["session_id"], request["actor"],
                    request["recipient"], request["phase"], request["date_raw"],
                    request["action_id"], params))

    def test_real_grant_independence_inbound_rejection_recomputes_unchanged(self):
        case = self.fixture["grant_positive"]["inbound_reject"]
        inspection = self._assert_grant_positive_source_event("reject_inspection")
        submission = self._assert_grant_positive_source_event("reject_submission")
        response = self._assert_grant_positive_source_event("reject_response")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            inspection["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"], submission["phase"],
            submission["date_raw"], inspection["native_proposal_id"],
            inspection["action_id"]))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], inspection["action_id"])
        self.assertEqual(
            [{"action_id": "grant_independence"}],
            public_inspection["peace_context"]["terms"])
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"])
        self.assertIsNotNone(public_result)
        assert public_result is not None
        self.assertEqual("rejected", public_result["native_outcome"])
        self.assertFalse(public_result["terms_verified"])
        effect = public_result["effects"]["country_terms"]["grant_independence"]
        self.assertEqual(case["expected"]["effect"]["country"], effect["country"])
        self.assertEqual(case["expected"]["effect"]["overlord"], effect["overlord"])
        self.assertTrue(effect["unchanged"])
        self.assertFalse(effect["verified"])
        self.assertEqual(1, effect["overlord_count_before"])
        self.assertEqual(1, effect["overlord_count_after"])
        self.assertTrue(any(
            item.get("field") ==
            "effects.country_terms.grant_independence.unchanged"
            and item.get("native_value") is False
            and item.get("value") is True
            for item in public_result.get("effect_flag_corrections", [])))
        self._assert_public({"inspection": public_inspection,
                             "result": public_result})

        for field, mutate in (
                ("relation_active_after", lambda effect: effect.update(
                    {"relation_active_after": False, "unchanged": True})),
                ("overlord_count_after", lambda effect: effect.update(
                    {"overlord_count_after": 2, "unchanged": True}))):
            forged = copy.deepcopy(response)
            mutate(forged["effects"]["country_terms"]["grant_independence"])
            with self.subTest(tamper=field):
                self.assertIsNone(
                    ObserverSession._public_native_inbound_response_result(
                        forged, forged["request_id"], forged["session_id"],
                        forged["actor"], forged["phase"], forged["date_raw"],
                        case["native_proposal_id"], forged["action_id"]))

    def test_real_grant_independence_accept_with_unverified_effect_stays_unknown(self):
        case = self.fixture["grant_positive"]["inbound_accept"]
        inspection = self._assert_grant_positive_source_event("accept_inspection")
        submission = self._assert_grant_positive_source_event("accept_submission")
        response = self._assert_grant_positive_source_event("accept_response")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            inspection["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"], submission["phase"],
            submission["date_raw"], inspection["native_proposal_id"],
            inspection["action_id"]))
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"])
        self.assertIsNotNone(public_result)
        assert public_result is not None
        self.assertEqual("unknown", public_result["native_outcome"])
        self.assertEqual(2, public_result["native_state"])
        self.assertFalse(public_result["terms_verified"])
        self.assertFalse(public_result["war_after"])
        effect = public_result["effects"]["country_terms"]["grant_independence"]
        self.assertEqual(case["expected"]["effect"]["country"], effect["country"])
        self.assertEqual(case["expected"]["effect"]["overlord"], effect["overlord"])
        self.assertTrue(effect["unchanged"])
        self.assertFalse(effect["verified"])
        self.assertEqual(1, effect["overlord_count_before"])
        self.assertEqual(1, effect["overlord_count_after"])
        self.assertTrue(any(
            item.get("field") ==
            "effects.country_terms.grant_independence.unchanged"
            and item.get("native_value") is False
            and item.get("value") is True
            for item in public_result.get("effect_flag_corrections", [])))
        self._assert_public(public_result)

    def _replay_grant_004_inbound_case(self, name: str) -> dict:
        case = self.fixture["grant_004"][f"inbound_{name}"]
        inspection = self._assert_grant_004_source_event(f"{name}_inspection")
        submission = self._assert_grant_004_source_event(f"{name}_submission")
        response = self._assert_grant_004_source_event(f"{name}_response")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            inspection["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"],
            submission["phase"], submission["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"]))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], inspection["action_id"])
        self.assertEqual(
            [{"action_id": "grant_independence"}],
            public_inspection["peace_context"]["terms"])
        public_submission = (
            ObserverSession._public_native_inbound_submission_receipt(
                submission, submission["request_id"], submission["actor"],
                submission["phase"], submission["date_raw"],
                inspection["action_id"]))
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], inspection["action_id"])
        self.assertIsNotNone(public_submission)
        self.assertIsNotNone(public_result)
        assert public_result is not None
        expected = case["expected"]
        for field in ("native_state", "outcome", "war_before", "war_after",
                      "terms_verified", "pending_removed"):
            public_field = "native_outcome" if field == "outcome" else field
            self.assertEqual(expected[field], public_result[public_field])
        effect = public_result["effects"]["country_terms"][
            "grant_independence"]
        for field in ("country", "overlord", "overlord_count_before",
                      "overlord_count_after", "verified"):
            self.assertEqual(expected[field], effect[field])
        self.assertTrue(effect["overlord_scan_complete_before"])
        self.assertTrue(effect["overlord_scan_complete_after"])
        self.assertTrue(effect["no_other_overlords_before"])
        self.assertTrue(effect["no_other_overlords_after"])
        self._assert_public({"inspection": public_inspection,
                             "submission": public_submission,
                             "result": public_result})
        return response

    def test_real_grant_004_zero_overlord_query_and_execution_paths(self):
        case = self.fixture["grant_004"]
        query = self._assert_grant_004_source_event("query")
        params = case["query"]["input"]["normalized_parameters"]
        selection = self._selection(query, params)
        self.assertTrue(ObserverSession._valid_native_peace_combined_country_offer_query(
            query, query["action_id"], query["actor"], query["recipient"],
            query["phase"], query["date_raw"], selection,
            query["query_id"], query["session_id"]))
        public_query = ObserverSession._semantic_peace_combined_country_offer_query(
            query, EU4_ESCAPE_CODEC)
        expected_query = case["query"]["expected"]
        self.assertTrue(public_query["query_complete"])
        self.assertEqual(expected_query["full_rules_complete"],
                         public_query["full_rules_complete"])
        self.assertTrue(public_query["parameters_matched"])
        grant = public_query["native_country_terms"]["grant_independence"]
        self.assertEqual(expected_query["country"], grant["requested_country"])
        self.assertEqual(expected_query["candidate_count"],
                         grant["candidate_count"])
        self.assertTrue(grant["requested_candidate_found"])
        self.assertEqual(expected_query["selection_delta_raw"],
                         grant["selection_delta_raw"])
        self.assertEqual(expected_query["factors"],
                         public_query["native_evaluation"]["factor_native_count"])
        self.assertTrue(public_query["native_selected_rules"]["complete"])
        self.assertTrue(public_query["native_selected_rules"]["available"])
        self._assert_public(public_query, query_identity=True)

        submission = self._assert_grant_004_source_event(
            "outbound_submission")
        request = dict(case["query"]["input"])
        request.update({field: query[field]
                        for field in ("actor", "recipient", "phase",
                                      "date_raw", "action_id")})
        params = request["normalized_parameters"]
        request_id = case["outbound"]["request_id"]
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, request_id, submission["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params))
        receipt = ObserverSession._public_native_peace_submission_receipt(
            submission, request_id, request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            params)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual("ENG", receipt["independence_country"])
        self._assert_public(receipt)

        result = self._assert_grant_004_source_event("outbound_result")
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            result, request_id, result["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params))
        public_result = ObserverSession._public_native_peace_execution_result(
            result, request_id, result["session_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], params)
        self.assertIsNotNone(public_result)
        assert public_result is not None
        expected_outbound = case["outbound"]["expected"]
        self.assertEqual(expected_outbound["outcome"],
                         public_result["native_outcome"])
        self.assertEqual(expected_outbound["native_state"],
                         public_result["native_state"])
        self.assertEqual(expected_outbound["war_after"],
                         public_result["war_after"])
        effect = public_result["effects"]["country_terms"][
            "grant_independence"]
        for field in ("country", "overlord", "overlord_count_before",
                      "overlord_count_after", "verified"):
            self.assertEqual(expected_outbound[field], effect[field])
        self.assertTrue(effect["overlord_scan_complete_before"])
        self.assertTrue(effect["overlord_scan_complete_after"])
        self.assertTrue(effect["no_other_overlords_before"])
        self.assertTrue(effect["no_other_overlords_after"])
        self._assert_public(public_result)

        self._replay_grant_004_inbound_case("reject")
        self._replay_grant_004_inbound_case("accept")

    def test_grant_effect_allows_independent_before_and_requires_zero_after(self):
        def grant_effect(after_count: int) -> dict:
            return {
                "country": "FRA",
                "overlord": "ENG",
                "relation_active_before": False,
                "relation_active_after": False,
                "is_overlord_before": False,
                "is_overlord_after": False,
                "subject_type_before": None,
                "subject_type_after": None,
                "overlord_count_before": 0,
                "overlord_count_after": after_count,
                "overlord_scan_complete_before": True,
                "overlord_scan_complete_after": True,
                "no_other_overlords_before": True,
                "no_other_overlords_after": True,
                "complete": True,
                "values_readable": True,
                "unchanged": after_count == 0,
                "verified": True,
                "reason_code": None,
            }

        def effects(after_count: int) -> dict:
            return {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": None,
                "provinces": [],
                "country_terms": {
                    "release_nation": None,
                    "force_vassalization": None,
                    "form_personal_union": None,
                    "grant_independence": grant_effect(after_count),
                    "full_annexation": None,
                },
            }

        kwargs = {
            "grant_independence_country": "FRA",
            "grant_independence_overlord": "ENG",
            "grant_independence_requested": True,
        }
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            effects(0), "demand", -1, [], None, "ENG", "FRA", 56549832,
            True, **kwargs))
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            effects(1), "demand", -1, [], None, "ENG", "FRA", 56549832,
            True, **kwargs))


if __name__ == "__main__":
    unittest.main()
