from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_catalog import ACTIONS
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"
DATE_RAW = 56548944
OPEN_END = 0x29C77F8
REAL_QUERY_FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_trade_power_r50_real_query.json")


def _trade_term(direction: str) -> dict[str, str]:
    return {
        "action_id": "transfer_trade_power",
        "source": ACTOR if direction == "offer" else RECIPIENT,
        "beneficiary": RECIPIENT if direction == "offer" else ACTOR,
    }


def _money_term(direction: str) -> dict[str, str]:
    return {
        "action_id": "demand_ducats",
        "amount": "10.0",
        "payer": ACTOR if direction == "offer" else RECIPIENT,
        "claimant": RECIPIENT if direction == "offer" else ACTOR,
    }


def _province_term(direction: str) -> dict[str, object]:
    return {
        "action_id": "cede_province",
        "province_ids": [177],
        "beneficiary": ACTOR if direction == "demand" else RECIPIENT,
    }


def _reparations_term(direction: str) -> dict[str, str]:
    return {
        "action_id": "war_reparations",
        "payer": ACTOR if direction == "offer" else RECIPIENT,
        "claimant": RECIPIENT if direction == "offer" else ACTOR,
    }


def _parameters(mask: str, direction: str = "demand",
                primary: str = "transfer_trade_power") -> dict[str, object]:
    terms: list[dict[str, object]] = []
    if "m" in mask:
        terms.append(_money_term(direction))
    if "p" in mask:
        terms.append(_province_term(direction))
    if "r" in mask:
        terms.append(_reparations_term(direction))
    if "t" in mask:
        terms.append(_trade_term(direction))
    return normalize_peace_execution_parameters(
        primary, ACTOR, RECIPIENT, "initiate", {
            "peace_context": {
                "war_id": WAR_ID,
                "direction": direction,
                "terms": terms,
            },
        })


def _real_query_selection(case: dict[str, object]) -> dict[str, object]:
    request = case["request"]
    event = case["event"]
    context = request["parameters"]["peace_context"]
    terms = context["terms"]
    by_action = {term["action_id"]: term for term in terms}
    direction = context["direction"]
    trade = by_action["transfer_trade_power"]
    money = by_action.get("demand_ducats")
    province = by_action.get("cede_province")
    reparations = by_action.get("war_reparations")
    return {
        "action_id": request["action_id"],
        "war_id": context["war_id"],
        "direction": direction,
        "amount_raw": (
            (int(money["amount"].split(".")[0]) * 10
             + int(money["amount"].split(".")[1])) * 100
            if money is not None else -1),
        "province_ids": list(province["province_ids"])
        if province is not None else [],
        "beneficiary": province["beneficiary"] if province is not None else None,
        "source": trade["source"],
        "trade_power_beneficiary": trade["beneficiary"],
        "payer": reparations["payer"] if reparations is not None else None,
        "claimant": reparations["claimant"] if reparations is not None else None,
        "term_mask": event["term_mask"],
    }


class PeaceTradePowerBridgeTests(unittest.TestCase):
    def test_normalization_canonicalizes_every_query9_mask_and_direction(self):
        primary_by_mask = {
            "t": "transfer_trade_power",
            "mt": "demand_ducats",
            "pt": "cede_province",
            "rt": "war_reparations",
            "mpt": "cede_province",
            "mrt": "demand_ducats",
            "prt": "cede_province",
            "mprt": "cede_province",
        }
        for direction in ("demand", "offer"):
            for mask, primary in primary_by_mask.items():
                with self.subTest(direction=direction, mask=mask):
                    normalized = _parameters(mask, direction, primary)
                    terms = normalized["peace_context"]["terms"]
                    self.assertEqual(
                        mask,
                        "".join({
                            "demand_ducats": "m",
                            "cede_province": "p",
                            "war_reparations": "r",
                            "transfer_trade_power": "t",
                        }[term["action_id"]] for term in terms))
                    trade = terms[-1]
                    self.assertEqual(_trade_term(direction), trade)
                    self.assertEqual(mask, ObserverSession._peace_execution_fields(
                        normalized)[-1])

    def test_trade_term_has_no_public_ratio_or_amount_and_binds_direction(self):
        with self.assertRaisesRegex(ValueError,
                                   "PEACE_EXECUTION_TERM_INVALID"):
            normalize_peace_execution_parameters(
                "transfer_trade_power", ACTOR, RECIPIENT, "initiate", {
                    "peace_context": {
                        "war_id": WAR_ID,
                        "direction": "demand",
                        "terms": [{
                            **_trade_term("demand"),
                            "amount": "0.5",
                        }],
                    },
                })
        invalid = _trade_term("demand")
        invalid["source"] = ACTOR
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_TRADE_POWER_PARTIES_INVALID"):
            normalize_peace_execution_parameters(
                "transfer_trade_power", ACTOR, RECIPIENT, "initiate", {
                    "peace_context": {
                        "war_id": WAR_ID, "direction": "demand",
                        "terms": [invalid],
                    },
                })

    def test_catalog_exposes_source_beneficiary_and_eighteen_term_contract(self):
        description = ACTIONS["transfer_trade_power"].describe()
        self.assertEqual("peace_term", description["category"])
        definitions = description["parameter_definitions"]
        terms = definitions["peace_context.terms"]
        self.assertEqual(18, terms["max_length"])
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties",
             "humiliate_rival", "show_strength", "force_religion",
             "return_core", "revoke_core", "release_subject",
             "transfer_subject", "release_nation", "force_vassalization",
             "form_personal_union", "grant_independence", "full_annexation"],
            terms["canonical_order"])
        self.assertEqual(["transfer_trade_power"], terms["required_action_ids"])
        self.assertEqual(
            {"source", "beneficiary"},
            {
                field.rsplit(".", 1)[-1]
                for field in definitions
                if field.startswith("peace_context.terms[0].")
                and field.rsplit(".", 1)[-1] in {"source", "beneficiary"}
            })
        self.assertNotIn("amount", definitions)

    def test_accepted_and_rejected_effects_bind_trade_power_contract(self):
        parameters = _parameters("t", "demand")
        fields = ObserverSession._peace_execution_fields(parameters)
        self.assertIsNotNone(fields)
        (war_id, direction, amount_raw, province_ids, beneficiary,
         reparations_payer, reparations_claimant, source,
         trade_beneficiary, concede_country, concede_beneficiary,
         annul_country, annul_partners, term_mask) = fields
        self.assertEqual((WAR_ID, "demand", -1, [], None, None, None,
                          "ENG", "FRA", None, None, None, None, "t"), fields)
        self.assertIsNone(concede_country)
        self.assertIsNone(concede_beneficiary)
        self.assertIsNone(annul_country)
        self.assertIsNone(annul_partners)
        event = {
            "event": "native_peace_execution_result",
            "family": "peace",
            "session_id": "trade-power-session",
            "request_id": "trade-power-accepted",
            "action_id": "transfer_trade_power",
            "actor": ACTOR,
            "recipient": RECIPIENT,
            "phase": "initiate",
            "date_raw": DATE_RAW,
            "war_id": war_id,
            "direction": direction,
            "amount_raw": amount_raw,
            "province_ids": province_ids,
            "beneficiary": beneficiary,
            "term_mask": term_mask,
            "trade_power_source": source,
            "trade_power_beneficiary": trade_beneficiary,
            "native_state": 0,
            "outcome": "executed",
            "war_before": True,
            "war_after": False,
            "response_verified": True,
            "request_binding_verified": True,
            "execution_verified": True,
            "terms_verified": True,
            "effects": {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": None,
                "provinces": [],
                "war_reparations": None,
                "transfer_trade_power": {
                    "source": RECIPIENT,
                    "beneficiary": ACTOR,
                    "present_before": False,
                    "present_after": True,
                    "start_date_raw": DATE_RAW - 1,
                    "end_date_raw": OPEN_END,
                    "amount_raw": 500,
                    "amount_scale": 1000,
                    "peace_treaty": True,
                    "verified": True,
                },
            },
        }
        public = ObserverSession._public_native_peace_execution_result(
            event, event["request_id"], event["session_id"], ACTOR, RECIPIENT,
            "initiate", DATE_RAW, "transfer_trade_power", parameters)
        self.assertIsNotNone(public)
        self.assertEqual(1000, public["effects"]["transfer_trade_power"][
            "amount_scale"])
        self.assertEqual(OPEN_END, public["effects"]["transfer_trade_power"][
            "end_date_raw"])

        rejected = copy.deepcopy(event)
        rejected.update({
            "request_id": "trade-power-rejected",
            "native_state": 1,
            "outcome": "rejected",
            "war_after": True,
            "execution_verified": False,
            "terms_verified": False,
        })
        rejected["effects"]["transfer_trade_power"].update({
            "present_after": False,
            "amount_raw": 0,
            "amount_scale": 0,
            "peace_treaty": False,
            "verified": False,
            "start_date_raw": 0,
            "end_date_raw": 0,
        })
        public_rejected = ObserverSession._public_native_peace_execution_result(
            rejected, rejected["request_id"], rejected["session_id"], ACTOR,
            RECIPIENT, "initiate", DATE_RAW, "transfer_trade_power", parameters)
        self.assertIsNotNone(public_rejected)
        self.assertFalse(public_rejected["effects"]["transfer_trade_power"][
            "verified"])

        bad_scale = copy.deepcopy(event)
        bad_scale["effects"]["transfer_trade_power"]["amount_scale"] = 999
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            bad_scale, bad_scale["request_id"], bad_scale["session_id"], ACTOR,
            RECIPIENT, "initiate", DATE_RAW, "transfer_trade_power", parameters))

    def test_inbound_context_and_accepted_effect_use_source_beneficiary_roles(self):
        context = {
            "war_id": WAR_ID,
            "direction": "demand",
            "terms": [{
                "action_id": "transfer_trade_power",
                "source": "FRA",
                "beneficiary": "ENG",
            }],
            "original_actor": "ENG",
            "original_recipient": "FRA",
            "complete": True,
        }
        self.assertTrue(ObserverSession._valid_inbound_peace_context(
            context, "ENG", "FRA"))
        fields = ObserverSession._inbound_peace_context_fields(
            context, "ENG", "FRA")
        self.assertEqual("FRA", fields["trade_power_source"])
        self.assertEqual("ENG", fields["trade_power_beneficiary"])
        event = {
            "event": "native_peace_inbound_response_result",
            "request_id": "inbound-trade-power",
            "session_id": "inbound-trade-session",
            "action_id": "peace_offer",
            "family": "peace",
            "actor": "ENG",
            "recipient": "FRA",
            "decision_country": "FRA",
            "phase": "accept",
            "date_raw": DATE_RAW,
            "native_state": 2,
            "outcome": "accepted",
            "war_before": True,
            "war_after": False,
            "war_state_verified": True,
            "response_verified": True,
            "request_binding_verified": True,
            "pending_removed": True,
            "terms_verified": True,
            "peace_context": context,
            "effects": {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": None,
                "provinces": [],
                "war_reparations": None,
                "transfer_trade_power": {
                    "source": "FRA",
                    "beneficiary": "ENG",
                    "present_before": False,
                    "present_after": True,
                    "start_date_raw": DATE_RAW - 1,
                    "end_date_raw": OPEN_END,
                    "amount_raw": 500,
                    "amount_scale": 1000,
                    "peace_treaty": True,
                    "verified": True,
                },
            },
        }
        public = ObserverSession._public_native_inbound_response_result(
            event, event["request_id"], event["session_id"], "ENG", "accept",
            DATE_RAW, 1, "peace_offer")
        self.assertIsNotNone(public)
        self.assertEqual("FRA", public["effects"]["transfer_trade_power"][
            "source"])
        self.assertEqual("ENG", public["effects"]["transfer_trade_power"][
            "beneficiary"])

    def test_real_r50_query9_fixture_replays_partial_and_complete_public_views(self):
        fixture = json.loads(REAL_QUERY_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(5, len(fixture["cases"]))
        for case in fixture["cases"]:
            with self.subTest(name=case["name"]):
                event = case["event"]
                request = case["request"]
                selection = _real_query_selection(case)
                self.assertTrue(
                    ObserverSession._valid_native_peace_trade_power_offer_inspection(
                        event, request["action_id"], request["actor"],
                        request["recipient"], request["phase"],
                        event["date_raw"], selection, event["query_id"],
                        event["session_id"]))
                projected = ObserverSession._semantic_peace_trade_power_offer_inspection(
                    event)
                self.assertNotIn("frame_thread", json.dumps(projected))
                self.assertNotIn('"private"', json.dumps(projected))
                self.assertEqual(event["term_mask"], projected["term_mask"])
                self.assertEqual(
                    event["native_trade_power"]["selected"],
                    projected["native_trade_power"]["selected"])

                execution = DiplomacyTools._apply_peace_execution_inspection(
                    {
                        "interface_support": {},
                        "session": {"date_raw": event["date_raw"]},
                        "acceptance": {},
                        "costs": {},
                    }, projected, request["parameters"])
                self.assertNotEqual(
                    "QUERY_NATIVE_RESULT_INVALID",
                    execution["legality"]["reasons"][0]["code"])
                if case["name"] == "trade-demand":
                    native_trade = projected["native_trade_power"]
                    self.assertFalse(native_trade["candidate_found"])
                    self.assertFalse(native_trade["selection_available"])
                    self.assertFalse(native_trade["selected"])
                    self.assertFalse(native_trade["parameters_matched"])
                    self.assertEqual(
                        "NATIVE_PEACE_TRADE_POWER_CANDIDATE_NOT_FOUND",
                        native_trade["reason_code"])
                    self.assertEqual([], projected["peace_context"]["terms"])
                    self.assertEqual("unknown", execution["legality"]["status"])
                elif case["name"] == "all-four-term-kinds":
                    self.assertEqual(
                        ["demand_ducats", "cede_province", "war_reparations",
                         "transfer_trade_power"],
                        [term["action_id"] for term in
                         projected["peace_context"]["terms"]])
                    self.assertTrue(projected["native_reparations"]["selected"])
                    self.assertTrue(projected["native_trade_power"]["selected"])
                    self.assertEqual("available", execution["legality"]["status"])

    def test_real_candidate_miss_shape_is_accepted_for_query8_reparations(self):
        fixture = json.loads(REAL_QUERY_FIXTURE.read_text(encoding="utf-8"))
        source = next(case["event"] for case in fixture["cases"]
                      if case["name"] == "trade-demand")
        event = copy.deepcopy(source)
        event["event"] = "native_peace_reparations_offer_inspection"
        event["action_id"] = "war_reparations"
        event["term_mask"] = "r"
        trade = event.pop("native_trade_power")
        event["native_reparations"] = {
            key: value for key, value in trade.items()
            if key not in ("source", "beneficiary")
        }
        event["native_reparations"]["reason_code"] = (
            "NATIVE_PEACE_REPARATIONS_CANDIDATE_NOT_FOUND")
        event["native_reparations"]["payer"] = "ENG"
        event["native_reparations"]["claimant"] = "FRA"
        expected = {
            "action_id": "war_reparations",
            "war_id": event["war_id"],
            "direction": "demand",
            "amount_raw": -1,
            "province_ids": [],
            "beneficiary": None,
            "payer": "ENG",
            "claimant": "FRA",
            "term_mask": "r",
        }
        self.assertTrue(
            ObserverSession._valid_native_peace_reparations_offer_inspection(
                event, "war_reparations", "FRA", "ENG", "initiate",
                event["date_raw"], expected, event["query_id"],
                event["session_id"]))


if __name__ == "__main__":
    unittest.main()
