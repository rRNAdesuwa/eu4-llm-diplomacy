from __future__ import annotations

import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_catalog import ACTIONS
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
DATE_RAW = 56548944


def _term(action_id: str, direction: str = "demand") -> dict[str, object]:
    if action_id == "demand_ducats":
        return {"action_id": action_id, "amount": "10.0",
                "payer": "ENG", "claimant": "FRA"}
    if action_id == "cede_province":
        return {"action_id": action_id, "province_ids": [177],
                "beneficiary": "FRA"}
    if action_id == "war_reparations":
        return {"action_id": action_id, "payer": "ENG", "claimant": "FRA"}
    if action_id == "transfer_trade_power":
        return {"action_id": action_id, "source": "ENG",
                "beneficiary": "FRA"}
    return {"action_id": "concede_defeat", "conceding_country": "ENG",
            "beneficiary": "FRA"}


def _c_effect(*, verified: bool, conceding_after: int = 5000) -> dict[str, object]:
    return {
        "conceding_country": "ENG",
        "beneficiary": "FRA",
        "conceding_prestige_before_raw": 10000,
        "conceding_prestige_after_raw": conceding_after,
        "conceding_prestige_delta_raw": conceding_after - 10000,
        "beneficiary_prestige_before_raw": 8000,
        "beneficiary_prestige_after_raw": 9000 if verified else 8000,
        "beneficiary_prestige_delta_raw": 1000 if verified else 0,
        "prestige_scale": 1000,
        "values_readable": True,
        "verified": verified,
    }


class PeaceConcedeDefeatTests(unittest.TestCase):
    def test_normalizer_maps_c_roles_and_canonicalizes_all_five_terms(self):
        parameters = {
            "peace_context": {
                "war_id": WAR_ID,
                "direction": "demand",
                "terms": [
                    _term("transfer_trade_power"),
                    _term("concede_defeat"),
                    _term("cede_province"),
                    _term("demand_ducats"),
                    _term("war_reparations"),
                ],
            },
        }
        normalized = normalize_peace_execution_parameters(
            "concede_defeat", "FRA", "ENG", "initiate", parameters)
        context = normalized["peace_context"]
        self.assertEqual("mprtc", "".join({
            "demand_ducats": "m", "cede_province": "p",
            "war_reparations": "r", "transfer_trade_power": "t",
            "concede_defeat": "c",
        }[term["action_id"]] for term in context["terms"]))
        self.assertEqual(
            {"action_id": "concede_defeat", "conceding_country": "ENG",
             "beneficiary": "FRA"}, context["terms"][-1])

        offered = normalize_peace_execution_parameters(
            "concede_defeat", "FRA", "ENG", "initiate", {
                "peace_context": {
                    "war_id": WAR_ID, "direction": "offer",
                    "terms": [{
                        "action_id": "concede_defeat",
                        "conceding_country": "FRA", "beneficiary": "ENG",
                    }],
                },
            })
        self.assertEqual("FRA", offered["peace_context"]["terms"][0][
            "conceding_country"])

    def test_normalizer_rejects_wrong_c_roles_and_more_than_eighteen_terms(self):
        wrong = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand",
            "terms": [{"action_id": "concede_defeat",
                       "conceding_country": "FRA", "beneficiary": "ENG"}],
        }}
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_CONCEDE_DEFEAT_PARTIES_INVALID"):
            normalize_peace_execution_parameters(
                "concede_defeat", "FRA", "ENG", "initiate", wrong)
        too_many = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand",
            "terms": [_term("demand_ducats"), _term("cede_province"),
                       _term("war_reparations"), _term("transfer_trade_power"),
                       _term("concede_defeat"),
                       {"action_id": "annul_treaties", "country": "ENG",
                        "treaty_partners": ["FRA"]},
                       {"action_id": "humiliate_rival", "country": "ENG",
                        "beneficiary": "FRA"},
                       {"action_id": "show_strength", "country": "ENG",
                        "beneficiary": "FRA"},
                       {"action_id": "force_religion", "country": "ENG",
                        "beneficiary": "FRA"},
                       {"action_id": "return_core", "province_ids": [173],
                        "core_owner": "AMG"},
                       {"action_id": "revoke_core", "province_ids": [175],
                        "core_owner": "ENG"},
                       {"action_id": "return_core", "province_ids": [177],
                        "core_owner": "AMG"},
                       {"action_id": "release_subject", "country": "TYR"},
                       {"action_id": "transfer_subject", "country": "LEI"},
                       {"action_id": "release_nation", "country": "TYR"},
                       {"action_id": "force_vassalization", "country": "LEI"},
                       {"action_id": "form_personal_union", "country": "SCO"},
                       {"action_id": "grant_independence"},
                       {"action_id": "full_annexation", "country": "AUV"},
                       {"action_id": "unsupported_peace_term"}],
        }}
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_TERMS_INVALID"):
            normalize_peace_execution_parameters(
                "concede_defeat", "FRA", "ENG", "initiate", too_many)

    def test_query11_c_branch_binds_roles_and_source_slot(self):
        session = object.__new__(ObserverSession)
        session.installation_capabilities = lambda: frozenset({
            "native_peace_concede_defeat_query",
        })
        captured: dict[str, object] = {}
        session.inspect_alliance = lambda *args, **kwargs: captured.update(
            {"args": args, "kwargs": kwargs}) or {"ok": True}
        result = session.inspect_peace_concede_defeat_offer(
            "concede_defeat", "FRA", "ENG", "initiate", {
                "action_id": "concede_defeat", "war_id": WAR_ID,
                "direction": "demand", "amount_raw": -1,
                "province_ids": [], "beneficiary": None,
                "source": "-", "conceding_country": "ENG",
                "concede_beneficiary": "FRA", "term_mask": "c",
            })
        self.assertEqual({"ok": True}, result)
        selection = captured["kwargs"]["peace_concede_defeat_offer"]
        self.assertEqual("c", selection["term_mask"])
        self.assertEqual("-", selection["source"])
        self.assertEqual("ENG", selection["conceding_country"])
        self.assertEqual("FRA", selection["concede_beneficiary"])
        self.assertEqual(
            "native_peace_concede_defeat_offer_inspection",
            captured["kwargs"]["inspection_event"])

    def test_c_effect_accept_and_rejected_penalty_preserve_delta_contract(self):
        base = {
            "complete": True, "date_unchanged": True,
            "currency_scale": 1000, "money": None, "provinces": [],
            "concede_defeat": _c_effect(verified=True),
        }
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            base, "demand", -1, [], None, "FRA", "ENG", DATE_RAW, True,
            concede_defeat_country="ENG", concede_defeat_beneficiary="FRA",
            concede_defeat_requested=True))
        rejected = {**base, "concede_defeat": _c_effect(
            verified=False, conceding_after=-5000)}
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            rejected, "demand", -1, [], None, "FRA", "ENG", DATE_RAW, False,
            concede_defeat_country="ENG", concede_defeat_beneficiary="FRA",
            concede_defeat_requested=True))
        malformed = {**rejected, "concede_defeat": {
            **rejected["concede_defeat"],
            "conceding_prestige_delta_raw": 0,
        }}
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            malformed, "demand", -1, [], None, "FRA", "ENG", DATE_RAW, False,
            concede_defeat_country="ENG", concede_defeat_beneficiary="FRA",
            concede_defeat_requested=True))

    def test_catalog_exposes_c_roles_and_eighteen_term_contract(self):
        described = ACTIONS["concede_defeat"].describe()
        terms = described["parameter_definitions"]["peace_context.terms"]
        self.assertEqual(18, terms["max_length"])
        self.assertEqual("concede_defeat", terms["primary_action_id"])
        self.assertEqual(
            ("conceding_country", "beneficiary"),
            ACTIONS["concede_defeat"].parameters[1:])
        self.assertEqual("recipient", described["parameter_definitions"][
            "peace_context.terms[0].conceding_country"]["equals_by_direction"][
                "demand"])


if __name__ == "__main__":
    unittest.main()
