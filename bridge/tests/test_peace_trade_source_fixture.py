from __future__ import annotations

import unittest

from work.run_peace_inbound_fixture import _fixture_wire, _native_trade_power_contract
from work.run_peace_inbound_response import _peace_context_contract


class TradeSourceFixtureTests(unittest.TestCase):
    def test_response_binds_actual_third_source_separately_from_negotiating_payer(self):
        context = {"war_id": "war_0123456789abcdef_01234567", "direction": "offer",
                   "original_actor": "ENG", "original_recipient": "FRA",
                   "complete": True, "selected_terms_complete": True,
                   "terms": [{"action_id": "transfer_trade_power", "source": "UTR",
                              "beneficiary": "FRA"}]}
        self.assertTrue(all(_peace_context_contract(
            context, "accept", ("UTR", "FRA")).values()))
        self.assertFalse(_peace_context_contract(
            context, "accept", ("ENG", "FRA"))["trade_power_roles"])
        context["terms"][0]["source"] = "FRA"
        self.assertFalse(_peace_context_contract(context, "accept")["trade_power_roles"])

    def test_operator_can_propose_third_country_transfer_without_deciding_for_fra(self):
        self.assertEqual(
            _fixture_wire("transfer_trade_power", "offer", "UTR"),
            "TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_OFFER_PENDING UTR\n")
        self.assertEqual(
            _fixture_wire("transfer_trade_power", "demand", None),
            "TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_PENDING\n")

    def test_explicit_source_requires_matching_fixture_and_canonical_other_country(self):
        for term, direction, source in [
                ("transfer_trade_power", "offer", None),
                ("transfer_trade_power", "offer", "FRA"),
                ("transfer_trade_power", "offer", "utr"),
                ("transfer_trade_power", "offer", "UTR\n"),
                ("transfer_trade_power", "demand", "UTR"),
                ("war_reparations", "offer", "UTR")]:
            with self.subTest(term=term, direction=direction, source=source):
                with self.assertRaises(ValueError):
                    _fixture_wire(term, direction, source)

    def test_native_shape_binds_source_and_direction_and_allows_war_specific_candidates(self):
        dispatch = [{"trade_power_requested": True, "reparations_requested": False,
                     "direction": "offer", "trade_power_source": "UTR"}]
        peace = {"complete": True, "term_count": 84, "selected_term_count": 2,
                 "participant_counts": [6, 4, 6, 4], "flag40": 1,
                 "direction41": 0, "preview208": 0}
        pending = [{"peace": peace}]
        self.assertTrue(_native_trade_power_contract(
            dispatch, pending, direction="offer", source="UTR"))
        self.assertFalse(_native_trade_power_contract(
            dispatch, pending, direction="offer", source="ENG"))
        self.assertFalse(_native_trade_power_contract(
            dispatch, pending, direction="demand", source="UTR"))
        peace["selected_term_count"] = 1
        self.assertFalse(_native_trade_power_contract(
            dispatch, pending, direction="offer", source="UTR"))


if __name__ == "__main__":
    unittest.main()
