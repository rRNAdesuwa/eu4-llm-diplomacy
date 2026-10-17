"""Small offline contract checks for the Declare War authority operator."""

from __future__ import annotations

import unittest

from work.run_declare_war_authority_test import (
    _ACTION,
    _ACTOR,
    _EXPECTED_REASON,
    _RECIPIENT,
    _WIRES,
    _authority_event_summary,
    _war_pair_signature,
)


class DeclareWarAuthorityOperatorTest(unittest.TestCase):
    def test_fixed_wires_are_exact_ascii_lines(self) -> None:
        self.assertEqual(
            _WIRES["transport"],
            "TEST_ONLY FRA_DECLARE_WAR_ENG_WITHOUT_AUTHORITY\n",
        )
        self.assertEqual(
            _WIRES["direct_entry"],
            "TEST_ONLY FRA_DECLARE_WAR_ENG_DIRECT_WITHOUT_AUTHORITY\n",
        )
        for wire in _WIRES.values():
            self.assertEqual(wire.encode("ascii").decode("ascii"), wire)
            self.assertTrue(wire.endswith("\n"))

    def test_war_pair_signature_is_bounded_to_fra_eng(self) -> None:
        signature = _war_pair_signature({
            "current_raw_date": 123,
            "countries": [
                {"slot": 46, "pair_at_war": True,
                 "pairs": [{"slot": 122, "war": "0x2"}]},
                {"slot": 99, "pair_at_war": True,
                 "pairs": [{"slot": 100, "war": "0x3"}]},
                {"slot": 122, "pair_at_war": True,
                 "pairs": [{"slot": 46, "war": "0x2"}]},
            ],
        })
        self.assertEqual(signature["current_raw_date"], 123)
        self.assertEqual([item["slot"] for item in signature["countries"]], [46, 122])
        self.assertEqual(signature["countries"][0]["pairs"][0]["slot"], 122)

    def test_dispatch_and_rejection_contracts_require_no_seed(self) -> None:
        # direct_entry reports the fixture's common ``dispatched`` completion
        # flag, which is initialized true before the direct guarded call.  It
        # does not report transport-dispatcher acceptance.
        for route, accepted in (("transport", True), ("direct_entry", True)):
            session = "100-abc"
            events = [{
                "event": "native_alliance_authority_test_dispatched",
                "session_id": session,
                "action_id": _ACTION,
                "actor": _ACTOR,
                "recipient": _RECIPIENT,
                "phase": "initiate",
                "date_raw": 56462016,
                "dispatch_route": route,
                "dispatcher_accepted": accepted,
                "authority_seed_created": False,
                "casus_belli": "cb_core",
                "war_goal_province": 177,
                "war_goal_beneficiary": "FRA",
            }, {
                "event": "native_alliance_execution_rejected",
                "session_id": session,
                "request_id": "unknown",
                "reason": _EXPECTED_REASON,
                "submitted": False,
            }]
            summary = _authority_event_summary(events, session, 56462016, route)
            self.assertTrue(summary["complete"])
            self.assertTrue(summary["dispatch_contract"])
            self.assertTrue(summary["rejection_contract"])
            self.assertEqual(summary["preflight_failure_count"], 0)
            self.assertEqual(summary["business_events"], [])

        # A direct fixture may also report false when its direct call did not
        # reach the guarded entry; the type check remains strict and the route
        # contract does not confuse that flag with transport acceptance.
        direct_events = [{
            "event": "native_alliance_authority_test_dispatched",
            "session_id": "101-def",
            "action_id": _ACTION,
            "actor": _ACTOR,
            "recipient": _RECIPIENT,
            "phase": "initiate",
            "date_raw": 56462016,
            "dispatch_route": "direct_entry",
            "dispatcher_accepted": False,
            "authority_seed_created": False,
            "casus_belli": "cb_core",
            "war_goal_province": 177,
            "war_goal_beneficiary": "FRA",
        }, {
            "event": "native_alliance_execution_rejected",
            "session_id": "101-def",
            "request_id": "unknown",
            "reason": _EXPECTED_REASON,
            "submitted": False,
        }]
        direct_summary = _authority_event_summary(
            direct_events, "101-def", 56462016, "direct_entry")
        self.assertTrue(direct_summary["complete"])


if __name__ == "__main__":
    unittest.main()
