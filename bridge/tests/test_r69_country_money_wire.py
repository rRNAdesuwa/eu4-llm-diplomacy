from __future__ import annotations

import unittest

from bridge.diplomacy import ObserverSession
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_7623d81f6ab9879c_00000001"
PARAMETERS = {
    "peace_context": {
        "war_id": WAR_ID,
        "direction": "demand",
        "terms": [
            {"action_id": "release_nation", "country": "PIC", "source": "BUR"},
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": "BUR", "claimant": "FRA"},
        ],
    },
}


class _CountryMoneyProbeSession(ObserverSession):
    """Capture accidental QUERY18 routing without touching a native session."""

    def __init__(self) -> None:
        self.inspect_calls: list[dict] = []
        self.capabilities = frozenset()

    def installation_capabilities(self):
        return self.capabilities

    def inspect_alliance(self, *args, **kwargs):
        self.inspect_calls.append({"args": args, "kwargs": kwargs})
        return {"event": "wire-would-have-been-published"}


class R69CountryMoneyWireTests(unittest.TestCase):
    def test_country_money_combo_is_rejected_before_query18(self) -> None:
        normalized = normalize_peace_execution_parameters(
            "release_nation", "FRA", "BUR", "initiate", PARAMETERS)
        fields = ObserverSession._peace_execution_fields(normalized)
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual(1000, fields[2])
        self.assertEqual("mn", fields[-1])

        session = _CountryMoneyProbeSession()
        result = session.inspect_peace_execution(
            "release_nation", "FRA", "BUR", "initiate", PARAMETERS)

        self.assertEqual(
            {"error_code": "NATIVE_PEACE_EXECUTION_MIXED_INSPECTION_UNAVAILABLE"},
            result,
        )
        self.assertEqual([], session.inspect_calls)

    def test_new_producer_routes_same_complete_country_money_selection(self) -> None:
        session = _CountryMoneyProbeSession()
        session.capabilities = frozenset({
            "native_peace_country_terms_query", "native_peace_country_money_query"})
        result = session.inspect_peace_execution(
            "release_nation", "FRA", "BUR", "initiate", PARAMETERS)
        self.assertEqual("wire-would-have-been-published", result["event"])
        self.assertEqual(1, len(session.inspect_calls))
        query = session.inspect_calls[0]["kwargs"]["peace_combined_country_offer"]
        self.assertEqual("mn", query["term_mask"])
        self.assertEqual(1000, query["amount_raw"])
        self.assertEqual("PIC", query["release_nation_country"])
        self.assertEqual("BUR", query["release_nation_source"])


if __name__ == "__main__":
    unittest.main()
