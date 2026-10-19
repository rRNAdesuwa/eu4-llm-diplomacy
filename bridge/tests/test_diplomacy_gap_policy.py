"""No game calls: enforce the user's skip rule across historical naming changes."""
import unittest

from tools.plan_diplomacy_gap_tests import plan, success_ledger


class GapPolicyTests(unittest.TestCase):
    def test_historical_lab_alias_and_all_spy_effects_are_excluded(self):
        ledger, _ = success_ledger()
        self.assertEqual(ledger["blocked_count"], 38)
        actions = ["request_trade_power", "transfer_trade_power", "corrupt_officials",
                   "sabotage_reputation", "sow_discontent", "slander_merchants", "sabotage_recruitment"]
        for action in actions:
            result = plan([action])
            self.assertEqual(result["unverified_candidates"], [])
            self.assertEqual(len(result["skipped_successful"]), 1)
            self.assertEqual(result["requests_published"], 0)

    def test_duplicate_alias_or_unknown_action_cannot_create_an_extra_case(self):
        for actions in (["request_trade_power", "transfer_trade_power"], ["made_up_action"]):
            with self.assertRaises(ValueError):
                plan(actions)
        self.assertIn("curry_favors", plan(["curry_favors"])["skipped_successful"])
        self.assertIn("insult", plan(["insult"])["skipped_successful"])
        for action in ("stop_currying_favors", "support_independence", "form_coalition"):
            self.assertIn(action, plan([action])["skipped_successful"])


if __name__ == "__main__":
    unittest.main()
