from __future__ import annotations

import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.peace_country import COUNTRY_SELECTION_KEYS


WAR_ID = "war_7623d81f6ab9879c_00000001"
PARAMETERS = {
    "peace_context": {
        "war_id": WAR_ID,
        "direction": "offer",
        "terms": [],
    },
}


class _CountryOfferProbeSession(ObserverSession):
    """Minimal session double that retains the QUERY18 wire selection."""

    def __init__(self) -> None:
        self.country_query = None

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": "probe-state",
            "date_raw": 56552760,
            "reasons": [],
            "complete": True,
        }

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({
            "native_peace_country_terms_query",
            "native_peace_submission",
        })

    def inspect_alliance(self, action_id: str, actor: str, recipient: str,
                         phase: str, required_capabilities=None, **kwargs):
        self.country_query = {
            "action_id": action_id,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "required_capabilities": required_capabilities,
            "event": kwargs.get("inspection_event"),
            "selection": kwargs.get("peace_combined_country_offer"),
        }
        return {
            "event": "native_peace_combined_country_offer_query",
            "query_complete": False,
            "parameters_matched": False,
        }


class R69CountryOfferDiscoveryTests(unittest.TestCase):
    def test_empty_offer_release_uses_query18_country_leaf(self) -> None:
        session = _CountryOfferProbeSession()
        tools = DiplomacyTools(None, session)

        result = tools.inspect_diplomatic_action(
            "release_nation", "FRA", "BUR", parameters=PARAMETERS)

        query = session.country_query
        self.assertIsInstance(query, dict)
        assert isinstance(query, dict)
        self.assertEqual(
            "native_peace_combined_country_offer_query", query["event"])
        self.assertEqual("release_nation", query["action_id"])
        self.assertEqual("offer", query["selection"]["direction"])
        self.assertEqual(WAR_ID, query["selection"]["war_id"])
        self.assertEqual("n", query["selection"]["term_mask"])
        self.assertTrue(all(
            query["selection"][key] == "-"
            for key in COUNTRY_SELECTION_KEYS))
        self.assertEqual(
            PARAMETERS, result["parameters"]["requested"])
        self.assertNotEqual(
            "NATIVE_RULE_QUERY_UNIMPLEMENTED",
            result["legality"]["reasons"][0]["code"])


if __name__ == "__main__":
    unittest.main()
