import unittest

from bridge.diplomacy import DiplomacyTools
from bridge.favor_resources import (
    MEN_QUERY_CAPABILITY,
    MEN_SUBMISSION_CAPABILITY,
    MEN_RESPONSE_CAPABILITY,
    TRUST_QUERY_CAPABILITY,
    TRUST_SUBMISSION_CAPABILITY,
    TRUST_RESPONSE_CAPABILITY,
    project_query,
)


class ResourceQuerySession:
    record = {"controlled_countries": ["FRA"]}
    session_id = "resource-query-session"
    experiment_id = "resource-query-experiment"

    def __init__(self):
        self.calls = []
        self.capabilities = {
            "native_queries_enabled", TRUST_QUERY_CAPABILITY,
            TRUST_SUBMISSION_CAPABILITY, TRUST_RESPONSE_CAPABILITY,
            MEN_QUERY_CAPABILITY, MEN_SUBMISSION_CAPABILITY,
            MEN_RESPONSE_CAPABILITY,
        }

    def health(self):
        return {"status": "ready", "date_raw": 56553384,
                "state_id": "resource-state", "reasons": [], "complete": True}

    def installation_capabilities(self):
        return frozenset(self.capabilities)

    def inspect_alliance(self, action, actor, recipient, phase, *args, **kwargs):
        self.calls.append((action, actor, recipient, phase, args))
        kind = "trust" if action == "trade_favors_for_trust" else "men"
        if kind == "trust":
            raw = {
                "kind": "trust", "amount_raw": 10, "amount_readable": True,
                "favor_cost_raw": 7000, "favors_available_raw": 20000,
                "recipient_trust_raw": 95, "resource_scale": 1, "complete": True,
            }
        else:
            raw = {
                "kind": "men", "amount_raw": 25, "amount_readable": True,
                "favor_cost_raw": 10000, "favors_available_raw": 40000,
                "actor_manpower_raw": 100, "recipient_manpower_raw": 50,
                "resource_scale": 1, "complete": True,
            }
        return {
            "action_id": action, "family": "favor_trade", "date_raw": 56553384,
            "actor": actor, "recipient": recipient, "phase": phase,
            "ui_selection_checked": True, "native_visibility": True,
            "ui_enabled_gate_checked": True, "common_action_gate": True,
            "display_predicate": True, "initiation_gate": True,
            "tooltip_gate": True, "validity_called": True,
            "native_validity": True, "full_rules_complete": True,
            "diagnostic_readable": True, "native_diagnostic_text": "",
            "diplomat_context_readable": True, "diplomat_required": True,
            "available_diplomat_count": 1, "score_applicable": False,
            "score_available": False, "acceptance_predicate_available": False,
            "reason_count": 0, "reason_items": [],
            "reason_container_readable": False,
            "favor_trade": project_query(raw, actor, recipient),
            "submitted": False,
        }


class FavorResourceToolsTests(unittest.TestCase):
    def test_catalog_and_inspection_cover_both_resource_families(self):
        session = ResourceQuerySession()
        api = DiplomacyTools(None, session)
        catalog = api.list_diplomatic_actions()
        by_id = {entry["action_id"]: entry for entry in catalog["actions"]}
        self.assertTrue({"trade_favors_for_trust", "trade_favors_for_men"} <= by_id.keys())
        for action_id, query_cap, submission_cap, response_cap in (
                ("trade_favors_for_trust", TRUST_QUERY_CAPABILITY,
                 TRUST_SUBMISSION_CAPABILITY, TRUST_RESPONSE_CAPABILITY),
                ("trade_favors_for_men", MEN_QUERY_CAPABILITY,
                 MEN_SUBMISSION_CAPABILITY, MEN_RESPONSE_CAPABILITY)):
            action = by_id[action_id]
            self.assertEqual("diplomatic_action", action["category"])
            self.assertEqual(query_cap, action["phases"]["initiate"]["query"])
            self.assertEqual(submission_cap, action["phases"]["initiate"]["execute"])
            for phase in ("accept", "reject"):
                self.assertEqual("native_inbound_response_inspection",
                                 action["phases"][phase]["query"])
                self.assertEqual("native_inbound_response",
                                 action["phases"][phase]["execute"])
                self.assertIn(response_cap.upper(),
                              action["phases"][phase]["reason_code"])

    def test_trust_and_men_queries_use_native_payload_and_public_units(self):
        session = ResourceQuerySession()
        api = DiplomacyTools(None, session)
        trust = api.inspect_diplomatic_action(
            "trade_favors_for_trust", "FRA", "PAP")
        men = api.inspect_diplomatic_action(
            "trade_favors_for_men", "FRA", "SAV")
        self.assertEqual("available", trust["legality"]["status"])
        self.assertEqual("trust", trust["favor_trade"]["kind"])
        self.assertEqual(10, trust["favor_trade"]["amount"]["value"])
        self.assertEqual(1000, trust["favor_trade"]["favors"]["scale"])
        self.assertEqual(7, trust["favor_trade"]["favors"]["cost"])
        self.assertNotIn("payer", trust["favor_trade"]["amount"])
        self.assertEqual("men", men["favor_trade"]["kind"])
        self.assertEqual((100, 50), (
            men["favor_trade"]["manpower"]["actor_raw"],
            men["favor_trade"]["manpower"]["recipient_raw"]))
        self.assertEqual(2, len(session.calls))
        self.assertEqual("trade_favors_for_men", session.calls[-1][0])

    def test_parameters_are_empty_and_non_fra_query_stays_unknown(self):
        session = ResourceQuerySession()
        api = DiplomacyTools(None, session)
        with self.assertRaisesRegex(ValueError, "FAVOR_TRADE_PARAMETERS_UNSUPPORTED"):
            api.inspect_diplomatic_action(
                "trade_favors_for_trust", "FRA", "PAP", parameters={"amount": 2})
        result = api.inspect_diplomatic_action(
            "trade_favors_for_men", "PAP", "FRA")
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("unimplemented", result["interface_support"]["execute"])
        self.assertEqual([], session.calls)


if __name__ == "__main__":
    unittest.main()
