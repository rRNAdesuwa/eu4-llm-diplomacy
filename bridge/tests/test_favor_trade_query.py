import unittest

from bridge.diplomacy import DiplomacyTools
from bridge.favor_trade import validate_query, project_query


RAW = {"kind": "gold", "amount_raw": 10500, "amount_readable": True,
       "favor_cost_raw": 10000, "favors_available_raw": 15000,
       "actor_treasury_raw": 100000, "recipient_treasury_raw": 200000,
       "resource_scale": 1000, "complete": True}


class QuerySession:
    record = {"controlled_countries": ["FRA"]}

    def __init__(self, enabled=True, diplomats=1):
        self.enabled, self.diplomats = enabled, diplomats
        self.calls = []

    def health(self):
        return {"status": "ready", "date_raw": 56553384, "state_id": "query-state",
                "reasons": [], "complete": True}

    def installation_capabilities(self):
        return frozenset({"native_queries_enabled", "native_favor_gold_query",
                          "native_favor_gold_submission"} if self.enabled else {})

    def inspect_alliance(self, action, actor, recipient, phase, *args, **kwargs):
        self.calls.append((action, actor, recipient, phase))
        return {"action_id": action, "family": "favor_trade", "date_raw": 56553384,
                "actor": actor, "recipient": recipient, "phase": phase,
                "ui_selection_checked": True, "native_visibility": True,
                "ui_enabled_gate_checked": True, "common_action_gate": True,
                "display_predicate": True, "initiation_gate": True, "tooltip_gate": True,
                "validity_called": True, "native_validity": True, "full_rules_complete": True,
                "diagnostic_readable": True, "native_diagnostic_text": "",
                "diplomat_context_readable": True, "diplomat_required": True,
                "available_diplomat_count": self.diplomats, "score_applicable": False,
                "score_available": False, "acceptance_predicate_available": False,
                "reason_count": 0, "reason_items": [], "reason_container_readable": False,
                "favor_trade": project_query(RAW, actor, recipient), "submitted": False}


class FavorTradeQueryTests(unittest.TestCase):
    def test_strict_amount_and_favor_scale(self):
        self.assertTrue(validate_query(RAW))
        self.assertFalse(validate_query({**RAW, "favor_cost_raw": True}))
        self.assertFalse(validate_query({**RAW, "resource_scale": 1}))
        projected = project_query(RAW, "FRA", "PAP")
        self.assertEqual(10.5, projected["amount"]["value"])
        self.assertEqual(("PAP", "FRA"),
                         (projected["amount"]["payer"], projected["amount"]["receiver"]))
        self.assertEqual((15, 10),
                         (projected["favors"]["current"], projected["favors"]["cost"]))
        self.assertNotIn("treasury", projected)
        self.assertNotIn("recipient_treasury_raw", str(projected))

    def test_full_tools_query_keeps_native_amount_and_favor_cost(self):
        session = QuerySession()
        result = DiplomacyTools(None, session).inspect_diplomatic_action(
            "trade_favors_for_gold", "FRA", "PAP")
        self.assertEqual(1, len(session.calls))
        self.assertEqual("available", result["legality"]["status"])
        self.assertEqual(10.5, result["favor_trade"]["amount"]["value"])
        self.assertEqual(10, result["costs"]["items"][0]["amount"])
        self.assertEqual("available", result["authorization"]["status"])

    def test_old_installation_does_not_gain_query_by_catalog_registration(self):
        session = QuerySession(enabled=False)
        result = DiplomacyTools(None, session).inspect_diplomatic_action(
            "trade_favors_for_gold", "FRA", "PAP")
        self.assertEqual([], session.calls)
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("unimplemented", result["interface_support"]["execute"])

    def test_diplomat_rule_and_no_external_amount(self):
        tools = DiplomacyTools(None, QuerySession(diplomats=0))
        result = tools.inspect_diplomatic_action("trade_favors_for_gold", "FRA", "PAP")
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertTrue(any(r["code"] == "NATIVE_DIPLOMAT_UNAVAILABLE"
                            for r in result["legality"]["reasons"]))
        with self.assertRaisesRegex(ValueError, "FAVOR_TRADE_PARAMETERS_UNSUPPORTED"):
            tools.inspect_diplomatic_action("trade_favors_for_gold", "FRA", "PAP",
                                             parameters={"amount": 100})


if __name__ == "__main__":
    unittest.main()
