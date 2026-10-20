from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
DATE_RAW = 56549000
ACTOR = "FRA"
RECIPIENT = "ENG"
REAL_QUERY_FIXTURE = (
    Path(__file__).parent / "fixtures" /
    "peace_subject_execution_r60_real_query.json")
REAL_RESULTS_FIXTURE = (
    Path(__file__).parent / "fixtures" /
    "peace_subject_execution_r60_real_results.json")


def _context(terms: list[dict], direction: str = "offer") -> dict:
    return {
        "peace_context": {
            "war_id": WAR_ID,
            "direction": direction,
            "terms": terms,
        }
    }


def _subject_row(country: str, beneficiary: str | None, *,
                 source_before: tuple[bool, bool, str | None],
                 source_after: tuple[bool, bool, str | None],
                 beneficiary_before: tuple[bool, bool, str | None],
                 beneficiary_after: tuple[bool, bool, str | None],
                 verified: bool) -> dict:
    source_active_before, source_overlord_before, source_type_before = source_before
    source_active_after, source_overlord_after, source_type_after = source_after
    beneficiary_active_before, beneficiary_overlord_before, beneficiary_type_before = (
        beneficiary_before)
    beneficiary_active_after, beneficiary_overlord_after, beneficiary_type_after = (
        beneficiary_after)
    return {
        "country": country,
        "source": ACTOR,
        "beneficiary": beneficiary,
        "source_relation_active_before": source_active_before,
        "source_relation_active_after": source_active_after,
        "source_is_overlord_before": source_overlord_before,
        "source_is_overlord_after": source_overlord_after,
        "source_subject_type_before": source_type_before,
        "source_subject_type_after": source_type_after,
        "beneficiary_relation_active_before": beneficiary_active_before,
        "beneficiary_relation_active_after": beneficiary_active_after,
        "beneficiary_is_overlord_before": beneficiary_overlord_before,
        "beneficiary_is_overlord_after": beneficiary_overlord_after,
        "beneficiary_subject_type_before": beneficiary_type_before,
        "beneficiary_subject_type_after": beneficiary_type_after,
        "source_relation_active": source_active_after,
        "source_is_overlord": source_overlord_after,
        "source_subject_type": source_type_after,
        "beneficiary_relation_active": beneficiary_active_after,
        "beneficiary_is_overlord": beneficiary_overlord_after,
        "beneficiary_subject_type": beneficiary_type_after,
        "complete": True,
        "values_readable": True,
        "verified": verified,
    }


def _subject_effect(name: str, row: dict, *, unchanged: bool,
                    verified: bool) -> dict:
    return {
        "requested": True,
        "count": 1,
        "complete": True,
        "rows": [row],
        "unchanged": unchanged,
        "verified": verified,
    }


class PeaceSubjectExecutionR60Tests(unittest.TestCase):
    def test_normalizer_canonicalizes_both_subject_families_and_wire_fields(self):
        parameters = normalize_peace_execution_parameters(
            "release_subject", ACTOR, RECIPIENT, "initiate",
            _context([
                {"action_id": "transfer_subject", "countries": ["AUV", "LEI"]},
                {"action_id": "release_subject", "country": "TYR"},
            ]))
        self.assertEqual(
            ["release_subject", "transfer_subject"],
            [term["action_id"] for term in parameters["peace_context"]["terms"]])
        self.assertEqual("lx", ObserverSession._peace_execution_fields(parameters)[-1])
        self.assertEqual((['TYR'], ['AUV', 'LEI']),
                         ObserverSession._peace_subject_execution_fields(parameters))

    def test_normalizer_accepts_full_thirteen_family_contract(self):
        terms = [
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": RECIPIENT, "claimant": ACTOR},
            {"action_id": "cede_province", "province_ids": [10],
             "beneficiary": ACTOR},
            {"action_id": "war_reparations", "payer": RECIPIENT,
             "claimant": ACTOR},
            {"action_id": "transfer_trade_power", "source": "UTR",
             "beneficiary": ACTOR},
            {"action_id": "concede_defeat", "conceding_country": RECIPIENT,
             "beneficiary": ACTOR},
            {"action_id": "annul_treaties", "country": RECIPIENT,
             "treaty_partners": ["GEN"]},
            {"action_id": "humiliate_rival", "country": RECIPIENT,
             "beneficiary": ACTOR},
            {"action_id": "show_strength", "country": RECIPIENT,
             "beneficiary": ACTOR},
            {"action_id": "force_religion", "country": RECIPIENT,
             "beneficiary": ACTOR},
            {"action_id": "return_core", "province_ids": [173],
             "core_owner": "AMG"},
            {"action_id": "revoke_core", "province_ids": [175],
             "core_owner": "ENG"},
            {"action_id": "release_subject", "country": "LEI"},
            {"action_id": "transfer_subject", "country": "AUV"},
        ]
        parameters = normalize_peace_execution_parameters(
            "release_subject", ACTOR, RECIPIENT, "initiate",
            _context(terms, direction="demand"))
        self.assertEqual("mprtcahsfbvlx",
                         ObserverSession._peace_execution_fields(parameters)[-1])

    def test_subject_shape_rejects_ambiguous_or_overlapping_countries(self):
        with self.assertRaisesRegex(ValueError, "SUBJECT_COUNTRIES"):
            normalize_peace_execution_parameters(
                "release_subject", ACTOR, RECIPIENT, "initiate",
                _context([{"action_id": "release_subject",
                           "countries": ["LEI", "LEI"]}]))
        with self.assertRaisesRegex(ValueError, "TERM_INVALID"):
            normalize_peace_execution_parameters(
                "release_subject", ACTOR, RECIPIENT, "initiate",
                _context([{"action_id": "release_subject", "country": "LEI",
                           "countries": ["LEI"]}]))
        with self.assertRaisesRegex(ValueError, "SUBJECT_COUNTRY_CONFLICT"):
            normalize_peace_execution_parameters(
                "release_subject", ACTOR, RECIPIENT, "initiate",
                _context([
                    {"action_id": "release_subject", "country": "LEI"},
                    {"action_id": "transfer_subject", "country": "LEI"},
                ]))

    def test_submission_receipt_binds_subject_csvs_and_public_projection(self):
        parameters = normalize_peace_execution_parameters(
            "release_subject", ACTOR, RECIPIENT, "initiate",
            _context([
                {"action_id": "release_subject", "countries": ["LEI", "TYR"]},
                {"action_id": "transfer_subject", "country": "AUV"},
            ]))
        event = {
            "event": "native_peace_submission_result",
            "family": "peace", "request_id": "r60_subject_receipt",
            "session_id": "s60", "action_id": "release_subject",
            "actor": ACTOR, "recipient": RECIPIENT, "phase": "initiate",
            "date_raw": DATE_RAW, "war_id": WAR_ID, "direction": "offer",
            "amount_raw": -1, "province_ids": [], "beneficiary": "-",
            "term_mask": "lx", "release_subject_countries": "LEI,TYR",
            "transfer_subject_countries": "AUV", "submitted": True,
            "transport_verified": True, "request_binding_verified": True,
        }
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            event, "r60_subject_receipt", "s60", ACTOR, RECIPIENT,
            "initiate", DATE_RAW, "release_subject", parameters))
        public = ObserverSession._public_native_peace_submission_receipt(
            event, "r60_subject_receipt", ACTOR, RECIPIENT, "initiate",
            DATE_RAW, "release_subject", parameters)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("LEI,TYR", public["release_subject_countries"])
        self.assertEqual("AUV", public["transfer_subject_countries"])
        self.assertNotIn("session_id", public)

    def test_submission_receipt_survives_public_projection_and_context_reload(self):
        fixture = json.loads(REAL_QUERY_FIXTURE.read_text(encoding="utf-8"))
        request = fixture["input"]
        parameters = request["parameters"]
        request_id = "r60_subject_receipt_reload"
        session_id = "s60_subject_receipt_reload"
        event = {
            "event": "native_peace_submission_result",
            "family": "peace",
            "request_id": request_id,
            "session_id": session_id,
            "action_id": request["action_id"],
            "actor": request["actor"],
            "recipient": request["recipient"],
            "phase": request["phase"],
            "date_raw": request["date_raw"],
            "war_id": parameters["peace_context"]["war_id"],
            "direction": parameters["peace_context"]["direction"],
            "amount_raw": 1000,
            "province_ids": [],
            "beneficiary": "-",
            "term_mask": "mrlx",
            "reparations_payer": "ENG",
            "reparations_claimant": "FRA",
            "release_subject_countries": "TYR",
            "transfer_subject_countries": "LEI",
            "submitted": True,
            "transport_verified": True,
            "request_binding_verified": True,
        }
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            event, request_id, session_id, request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], parameters))
        native_public = ObserverSession._public_native_peace_submission_receipt(
            event, request_id, request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            parameters)
        self.assertIsNotNone(native_public)
        assert native_public is not None
        self.assertEqual("TYR", native_public["release_subject_countries"])
        self.assertEqual("LEI", native_public["transfer_subject_countries"])

        public = DiplomacyTools._public_peace_submission_receipt(
            native_public, request_id, request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            parameters)
        self.assertEqual(native_public, public)

        record = SimpleNamespace(
            payload={
                "action_id": request["action_id"],
                "actor": request["actor"],
                "recipient": request["recipient"],
                "phase": request["phase"],
                "parameters": parameters,
            },
            native_receipt=public,
            request_id=request_id,
            session_id=session_id,
        )
        context = DiplomacyTools._native_submission_context(record)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(("FRA", "ENG", "initiate", request["date_raw"]),
                         context[:4])
        restored_terms = context[4]["peace_context"]["terms"]
        self.assertEqual(
            [{"action_id": "release_subject", "country": "TYR"},
             {"action_id": "transfer_subject", "country": "LEI"}],
            [term for term in restored_terms
             if term["action_id"] in {"release_subject", "transfer_subject"}])

        wrong_csv = copy.deepcopy(native_public)
        wrong_csv["transfer_subject_countries"] = "TYR"
        self.assertIsNone(DiplomacyTools._public_peace_submission_receipt(
            wrong_csv, request_id, request["actor"], request["recipient"],
            request["phase"], request["date_raw"], request["action_id"],
            parameters))
        record.native_receipt = wrong_csv
        self.assertIsNone(DiplomacyTools._native_submission_context(record))

    def test_rejected_and_accepted_subject_effects_are_validated(self):
        parameters = normalize_peace_execution_parameters(
            "release_subject", ACTOR, RECIPIENT, "initiate",
            _context([
                {"action_id": "release_subject", "country": "LEI"},
                {"action_id": "transfer_subject", "country": "AUV"},
            ]))

        rejected_release = _subject_row(
            "LEI", None, source_before=(True, True, "vassal"),
            source_after=(True, True, "vassal"),
            beneficiary_before=(None, None, None),
            beneficiary_after=(None, None, None), verified=False)
        rejected_transfer = _subject_row(
            "AUV", RECIPIENT, source_before=(True, True, "vassal"),
            source_after=(True, True, "vassal"),
            beneficiary_before=(False, False, None),
            beneficiary_after=(False, False, None), verified=False)
        rejected_effects = {
            "complete": True, "date_unchanged": True, "currency_scale": 1000,
            "money": None, "provinces": [], "war_reparations": None,
            "release_subject": _subject_effect(
                "release_subject", rejected_release, unchanged=True, verified=False),
            "transfer_subject": _subject_effect(
                "transfer_subject", rejected_transfer, unchanged=True, verified=False),
        }
        rejected = {
            "event": "native_peace_execution_result", "family": "peace",
            "request_id": "r60_rejected", "session_id": "s60",
            "action_id": "release_subject", "actor": ACTOR,
            "recipient": RECIPIENT, "phase": "initiate", "date_raw": DATE_RAW,
            "war_id": WAR_ID, "direction": "offer", "amount_raw": -1,
            "province_ids": [], "beneficiary": "-", "term_mask": "lx",
            "release_subject_countries": "LEI", "transfer_subject_countries": "AUV",
            "native_state": 1, "outcome": "rejected", "response_verified": True,
            "request_binding_verified": True, "execution_verified": False,
            "terms_verified": False, "war_before": True, "war_after": True,
            "effects": rejected_effects,
        }
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            rejected, "r60_rejected", "s60", ACTOR, RECIPIENT, "initiate",
            DATE_RAW, "release_subject", parameters))
        public_rejected = ObserverSession._public_native_peace_execution_result(
            rejected, "r60_rejected", "s60", ACTOR, RECIPIENT, "initiate",
            DATE_RAW, "release_subject", parameters)
        self.assertIsNotNone(public_rejected)
        assert public_rejected is not None
        self.assertFalse(public_rejected["effects"]["release_subject"]["verified"])

        accepted_release = _subject_row(
            "LEI", None, source_before=(True, True, "vassal"),
            source_after=(False, False, None),
            beneficiary_before=(None, None, None),
            beneficiary_after=(None, None, None), verified=True)
        accepted_transfer = _subject_row(
            "AUV", RECIPIENT, source_before=(True, True, "vassal"),
            source_after=(False, False, None),
            beneficiary_before=(False, False, None),
            beneficiary_after=(True, True, "march"), verified=True)
        accepted = copy.deepcopy(rejected)
        accepted.update({
            "request_id": "r60_accepted", "native_state": 2,
            "outcome": "accepted", "execution_verified": True,
            "terms_verified": True, "war_after": False,
            "effects": {
                "complete": True, "date_unchanged": True,
                "currency_scale": 1000, "money": None, "provinces": [],
                "war_reparations": None,
                "release_subject": _subject_effect(
                    "release_subject", accepted_release,
                    unchanged=False, verified=True),
                "transfer_subject": _subject_effect(
                    "transfer_subject", accepted_transfer,
                    unchanged=False, verified=True),
            },
        })
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            accepted, "r60_accepted", "s60", ACTOR, RECIPIENT, "initiate",
            DATE_RAW, "release_subject", parameters))
        accepted["effects"]["transfer_subject"]["rows"][0]["country"] = "ENG"
        self.assertFalse(ObserverSession._valid_native_peace_execution_result(
            accepted, "r60_accepted", "s60", ACTOR, RECIPIENT, "initiate",
            DATE_RAW, "release_subject", parameters))

    def test_inbound_subject_context_merges_canonical_multi_country_terms(self):
        context = {
            "war_id": WAR_ID, "direction": "offer", "complete": True,
            "original_actor": "ENG", "original_recipient": "FRA",
            "terms": [
                {"action_id": "transfer_subject", "country": "AUV"},
                {"action_id": "release_subject", "country": "LEI"},
                {"action_id": "release_subject", "country": "TYR"},
            ],
        }
        fields = ObserverSession._inbound_peace_context_fields(
            context, "ENG", "FRA")
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual(["LEI", "TYR"], fields["release_subject_countries"])
        self.assertEqual(["AUV"], fields["transfer_subject_countries"])
        public = ObserverSession._canonicalize_inbound_peace_context(context)
        self.assertEqual(
            [{"action_id": "transfer_subject", "country": "AUV"},
             {"action_id": "release_subject", "countries": ["LEI", "TYR"]}],
            public["terms"])

    def test_real_query17_subject_rules_do_not_inflate_legacy_rule_count(self):
        fixture = json.loads(REAL_QUERY_FIXTURE.read_text(encoding="utf-8"))
        event = fixture["event"]
        request = fixture["input"]
        parameters = request["parameters"]
        context = parameters["peace_context"]
        terms = context["terms"]
        selection = {
            "action_id": request["action_id"],
            "war_id": context["war_id"],
            "direction": context["direction"],
            "term_mask": event["term_mask"],
            "release_countries": [
                term.get("country") for term in terms
                if term.get("action_id") == "release_subject"],
            "transfer_countries": [
                term.get("country") for term in terms
                if term.get("action_id") == "transfer_subject"],
        }
        self.assertTrue(
            ObserverSession._valid_native_peace_combined_subject_offer_query(
                event, request["action_id"], request["actor"],
                request["recipient"], request["phase"], request["date_raw"],
                selection, event["query_id"], event["session_id"]))
        # The native R record counts money+reparations (2).  Subject terms
        # have their own complete nested records and must not inflate it to 4.
        self.assertEqual(2, event["native_reparations"]["rule_term_count"])
        self.assertEqual(
            fixture["expected"]["term_rule_state"],
            ObserverSession._peace_selected_term_rule_state(event, terms))
        self.assertEqual(
            fixture["expected"]["wrapper_rule_state"],
            ObserverSession._peace_wrapper_rule_state(event))

        semantic = ObserverSession._semantic_peace_combined_subject_offer_query(
            event, EU4_ESCAPE_CODEC)
        inspection = {
            "interface_support": {
                "query": "native_peace_execution_inspection",
                "execute": "native_peace_subject_terms_execution",
            },
            "acceptance": {"items": []},
            "costs": {},
            "authorization": {},
            "session": {},
        }
        projected = DiplomacyTools._apply_peace_execution_inspection(
            inspection, semantic, parameters)
        self.assertEqual(fixture["expected"]["legality_status"],
                         projected["legality"]["status"])
        self.assertTrue(projected["parameters"]["complete"])
        self.assertTrue(projected["peace_context"]["complete"])
        self.assertEqual(
            fixture["expected"]["native_total"],
            projected["acceptance"]["native_total"])
        self.assertEqual(
            fixture["expected"]["evaluation_factor_count"],
            len(projected["acceptance"]["items"]))
        subject_cost = projected["costs"]["native_subject"]["items"]
        self.assertEqual(
            fixture["expected"]["subject_costs"],
            {item["action_id"]: item["amount_raw"] for item in subject_cost})

    def test_real_reject_accept_effects_require_every_selected_term(self):
        fixture = json.loads(REAL_RESULTS_FIXTURE.read_text(encoding="utf-8"))
        request = fixture["request"]
        parameters = request["parameters"]
        outbound = fixture["events"]["outbound"]
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            outbound, outbound["request_id"], outbound["session_id"],
            outbound["actor"], outbound["recipient"], outbound["phase"],
            outbound["date_raw"], outbound["action_id"], parameters))
        public_outbound = ObserverSession._public_native_peace_execution_result(
            outbound, outbound["request_id"], outbound["session_id"],
            outbound["actor"], outbound["recipient"], outbound["phase"],
            outbound["date_raw"], outbound["action_id"], parameters)
        self.assertIsNotNone(public_outbound)
        assert public_outbound is not None
        self.assertEqual(fixture["expected"]["outbound"]["outcome"],
                         public_outbound["native_outcome"])
        self.assertFalse(public_outbound["terms_verified"])
        self.assertFalse(public_outbound["effects"]["money"]["verified"])
        self.assertFalse(public_outbound["effects"]["war_reparations"][
            "verified"])
        for name in ("release_subject", "transfer_subject"):
            self.assertFalse(public_outbound["effects"][name]["verified"])

        for name in ("reject", "accept"):
            event = fixture["events"][name]
            public = ObserverSession._public_native_inbound_response_result(
                event, event["request_id"], event["session_id"],
                event["actor"], event["phase"], event["date_raw"],
                12345, "peace_offer")
            self.assertIsNotNone(public, name)
            assert public is not None
            expected = fixture["expected"][name]
            self.assertEqual(expected["native_outcome"],
                             public["native_outcome"])
            self.assertEqual(expected["terms_verified"],
                             public["terms_verified"])
            self.assertEqual(expected["war_after"], public["war_after"])
            effect_names = ("money", "war_reparations",
                            "release_subject", "transfer_subject")
            self.assertEqual(
                expected["effects_verified"],
                all(public["effects"][effect].get("verified") is True
                    for effect in effect_names))
            if name == "accept":
                # Native summary retains false, while the strict effects
                # revalidation promotes the public aggregate to verified.
                self.assertFalse(public["native_terms_verified"])
                self.assertEqual("validated_native_effects",
                                 public["terms_verification_source"])
                self.assertEqual(1000,
                                 public["effects"]["money"]["paid_raw"])

        accepted = fixture["events"]["accept"]
        for label, mutate in (
                ("subject", lambda e: e["effects"]["release_subject"][
                    "rows"][0].update({"country": "LEI"})),
                ("money", lambda e: e["effects"]["money"].update(
                    {"paid_raw": 999})),
                ("reparations", lambda e: e["effects"]["war_reparations"].update(
                    {"active_after": False})),
                ("row_binding", lambda e: e["effects"]["transfer_subject"][
                    "rows"][0].update({"source": "FRA"})),):
            tampered = copy.deepcopy(accepted)
            mutate(tampered)
            with self.subTest(effect=label):
                self.assertIsNone(
                    ObserverSession._public_native_inbound_response_result(
                        tampered, tampered["request_id"],
                        tampered["session_id"], tampered["actor"],
                        tampered["phase"], tampered["date_raw"],
                        12345, "peace_offer"))


if __name__ == "__main__":
    unittest.main()
