import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


WAR_ID = "war_3fead0a5641ef4f5_00000001"
DATE_RAW = 56545080


def peace_context(terms, *, direction="demand", actor="ENG", recipient="FRA"):
    return {
        "war_id": WAR_ID,
        "direction": direction,
        "terms": terms,
        "original_actor": actor,
        "original_recipient": recipient,
        "complete": True,
    }


def reparations_context(*, multi_beneficiary=False):
    provinces = [{"action_id": "cede_province", "province_id": 101,
                  "beneficiary": "ENG"}]
    if multi_beneficiary:
        provinces.append({"action_id": "cede_province", "province_id": 102,
                          "beneficiary": "SWE"})
    return peace_context([
        {"action_id": "demand_ducats", "amount_raw": 10000,
         "scale": 1000, "payer": "FRA", "claimant": "ENG"},
        *provinces,
        {"action_id": "war_reparations", "payer": "FRA", "claimant": "ENG"},
    ])


def effects_for(context, *, reparations_verified=True,
                province_verified=True, money_verified=True):
    terms = context["terms"]
    money_term = next((term for term in terms
                       if term["action_id"] == "demand_ducats"), None)
    money = None
    if money_term is not None:
        money = {
            "amount_raw": money_term["amount_raw"],
            "payer": "FRA",
            "paid_raw": money_term["amount_raw"] if money_verified else 0,
            "credits": [{"country": "ENG",
                          "amount_raw": money_term["amount_raw"]}],
            "verified": money_verified,
        }
    provinces = []
    for term in terms:
        if term["action_id"] != "cede_province":
            continue
        ids = ([term["province_id"]] if "province_id" in term
               else term["province_ids"])
        for province_id in ids:
            beneficiary = term["beneficiary"]
            provinces.append({
                "province_id": province_id,
                "beneficiary": beneficiary,
                "owner_before": "FRA",
                "owner_after": beneficiary,
                "controller_before": "FRA",
                "controller_after": beneficiary,
                "verified": province_verified,
            })
    reparations_term = next((term for term in terms
                             if term["action_id"] == "war_reparations"), None)
    result = {
        "complete": True,
        "date_unchanged": True,
        "currency_scale": 1000,
        "money": money,
        "provinces": provinces,
    }
    if reparations_term is not None:
        result["war_reparations"] = {
            "payer": "FRA",
            "claimant": "ENG",
            "active_before": False,
            "active_after": True,
            "verified": reparations_verified,
        }
    return result


def inbound_inspection(context, **overrides):
    event = {
        "event": "native_alliance_inbound_inspection",
        "query_id": "peace-query",
        "session_id": "peace-session",
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "phase": "accept",
        "native_proposal_id": 1,
        "date_raw": DATE_RAW,
        "pending_active": True,
        "decision_country": "FRA",
        "decision_country_verified": True,
        "native_validity": True,
        "response_rules_complete": True,
        "reason": "none",
        "war_before": True,
        "native_current_war": True,
        "native_current_war_readable": True,
        "war_active": True,
        "war_readable": True,
        "peace_payload_complete": True,
        "selected_terms_complete": True,
        "term_count": len(context["terms"]),
        "selected_term_count": len(context["terms"]),
        "peace_context": context,
    }
    event.update(overrides)
    return event


def inbound_response(context, effects=None, **overrides):
    event = {
        "event": "native_peace_inbound_response_result",
        "request_id": "peace-request",
        "session_id": "peace-session",
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "decision_country": "FRA",
        "phase": "accept",
        "date_raw": DATE_RAW,
        "outcome": "accepted",
        "native_state": 2,
        "war_before": True,
        "war_after": False,
        "war_state_verified": True,
        "response_verified": True,
        "request_binding_verified": True,
        "pending_removed": True,
        "terms_verified": True,
        "peace_context": context,
    }
    if effects is not None:
        event["effects"] = effects
    event.update(overrides)
    return event


class PeaceReparationsInboundTests(unittest.TestCase):
    def test_context_accepts_native_rows_and_reduces_roles(self):
        context = reparations_context()
        self.assertTrue(ObserverSession._valid_inbound_peace_context(
            context, "ENG", "FRA"))
        fields = ObserverSession._inbound_peace_context_fields(
            context, "ENG", "FRA")
        self.assertEqual(10000, fields["amount_raw"])
        self.assertEqual([101], fields["province_ids"])
        self.assertEqual("ENG", fields["beneficiary"])
        self.assertEqual("FRA", fields["reparations_payer"])
        self.assertEqual("ENG", fields["reparations_claimant"])

    def test_context_keeps_old_white_money_and_grouped_province_shapes(self):
        white = peace_context([],)
        money = peace_context([{"action_id": "demand_ducats",
                                "amount_raw": 10000, "scale": 1000}])
        grouped = peace_context([{"action_id": "cede_province",
                                  "province_ids": [101, 102],
                                  "beneficiary": "ENG"}])
        for context in (white, money, grouped):
            self.assertTrue(ObserverSession._valid_inbound_peace_context(
                context, "ENG", "FRA"))
        fields = ObserverSession._inbound_peace_context_fields(
            grouped, "ENG", "FRA")
        self.assertEqual([101, 102], fields["province_ids"])

    def test_context_rejects_duplicate_or_misbound_reparations(self):
        context = reparations_context()
        bad_role = {**context, "terms": [*context["terms"][:-1],
            {"action_id": "war_reparations", "payer": "ENG", "claimant": "FRA"}]}
        duplicate = {**context, "terms": [*context["terms"],
            {"action_id": "war_reparations", "payer": "FRA", "claimant": "ENG"}]}
        wrong_original = {**context, "original_actor": "SWE"}
        self.assertFalse(ObserverSession._valid_inbound_peace_context(
            bad_role, "ENG", "FRA"))
        self.assertFalse(ObserverSession._valid_inbound_peace_context(
            duplicate, "ENG", "FRA"))
        self.assertFalse(ObserverSession._valid_inbound_peace_context(
            wrong_original, "ENG", "FRA"))

    def test_inspection_binds_original_proposer_roles(self):
        event = inbound_inspection(reparations_context())
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, "peace-query", "peace-session", "ENG", "accept", 1,
            DATE_RAW, "peace_offer"))
        bad = inbound_inspection({**reparations_context(), "original_actor": "SWE"})
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            bad, "peace-query", "peace-session", "ENG", "accept", 1,
            DATE_RAW, "peace_offer"))

    def test_accept_requires_verified_effects_and_projects_public_result(self):
        context = reparations_context()
        effects = effects_for(context)
        effects["money"]["private_address"] = "native-pointer"
        # Private keys are rejected before they can cross the public result.
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            inbound_response(context, effects), "peace-request", "peace-session",
            "ENG", "accept", DATE_RAW, 1, "peace_offer"))
        effects = effects_for(context)
        result = ObserverSession._public_native_inbound_response_result(
            inbound_response(context, effects), "peace-request", "peace-session",
            "ENG", "accept", DATE_RAW, 1, "peace_offer")
        self.assertEqual("accepted", result["native_outcome"])
        self.assertTrue(result["terms_verified"])
        self.assertEqual("FRA", result["effects"]["war_reparations"]["payer"])
        self.assertNotIn("private_address", result["effects"]["money"])

        missing = ObserverSession._public_native_inbound_response_result(
            inbound_response(context), "peace-request", "peace-session",
            "ENG", "accept", DATE_RAW, 1, "peace_offer")
        self.assertEqual("unknown", missing["native_outcome"])
        self.assertFalse(missing["terms_verified"])

    def test_effect_roles_follow_context_direction_not_response_actor(self):
        context = reparations_context()
        effects = effects_for(context)
        effects["money"]["payer"] = "ENG"
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            inbound_response(context, effects), "peace-request", "peace-session",
            "ENG", "accept", DATE_RAW, 1, "peace_offer"))

    def test_reject_allows_unverified_effect_observation_but_not_verified_treaty(self):
        context = reparations_context()
        effects = effects_for(context, reparations_verified=False,
                              province_verified=False, money_verified=False)
        event = inbound_response(context, effects, phase="reject", outcome="rejected",
                                 native_state=1, war_after=True,
                                 terms_verified=False)
        result = ObserverSession._public_native_inbound_response_result(
            event, "peace-request", "peace-session", "ENG", "reject",
            DATE_RAW, 1, "peace_offer")
        self.assertEqual("rejected", result["native_outcome"])
        effects["war_reparations"]["verified"] = True
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            {**event, "effects": effects}, "peace-request", "peace-session",
            "ENG", "reject", DATE_RAW, 1, "peace_offer"))

    def test_multiple_beneficiaries_are_unknown_until_a_safe_effects_shape_exists(self):
        context = reparations_context(multi_beneficiary=True)
        effects = effects_for(context)
        result = ObserverSession._public_native_inbound_response_result(
            inbound_response(context, effects), "peace-request", "peace-session",
            "ENG", "accept", DATE_RAW, 1, "peace_offer")
        self.assertEqual("unknown", result["native_outcome"])
        self.assertFalse(result["terms_verified"])

    def test_list_advertises_independent_reparations_query_and_execution(self):
        class FakeSession:
            def health(self):
                return {"status": "ready", "state_id": "ready",
                        "date_raw": DATE_RAW, "reasons": [], "complete": True}

            def installation_capabilities(self):
                return frozenset({"native_peace_reparations_query",
                                  "native_peace_reparations_execution"})

        journal = DurableJournal(":memory:", "peace-r", "peace-session")
        try:
            listed = DiplomacyTools(journal, FakeSession()).list_diplomatic_actions(
                category="peace_term")
        finally:
            journal.close()
        reparations = next(item for item in listed["actions"]
                           if item["action_id"] == "war_reparations")
        initiate = reparations["phases"]["initiate"]
        self.assertEqual("native_peace_reparations_offer_inspection",
                         initiate["selected_query"])
        self.assertEqual("native_peace_reparations_execution",
                         initiate["execute"])


if __name__ == "__main__":
    unittest.main()
