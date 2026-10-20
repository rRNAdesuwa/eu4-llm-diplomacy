import copy
import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.tests.test_favor_trade_query import QuerySession


def response(state=2, actor="FRA", recipient="PAP", phase="initiate"):
    before = {"complete": True, "actor_treasury_raw": 100000,
              "recipient_treasury_raw": 200000, "favors_raw": 15000, "cost_raw": 10000}
    after = {**before}
    if state == 2:
        after.update(actor_treasury_raw=110500, recipient_treasury_raw=189500, favors_raw=5000)
    return {"event": "native_diplomacy_favor_trade_execution_result" if phase == "initiate"
            else "native_diplomacy_favor_trade_response_result", "request_id": "gold_001",
            "session_id": "gold-session", "action_id": "trade_favors_for_gold",
            "family": "favor_trade", "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": 56553384, "native_state": state,
            "outcome": "accepted" if state == 2 else "rejected", "native_variant": 1,
            "execution_verified": True, "request_binding_verified": True,
            "pending_removed": phase != "initiate",
            "favor_trade": {"before": before, "after": after, "amount_raw": 10500,
                            "complete": True, "verified": True}}


def project(event, proposal=None):
    return ObserverSession._public_native_favor_gold_result(
        event, "gold_001", "gold-session", event["actor"], event["recipient"],
        event["phase"], 56553384, proposal)


class ExecutionSession(QuerySession):
    session_id = "gold-session"
    experiment_id = "gold-contract"

    def __init__(self, state=2):
        super().__init__()
        self.state, self.submit_calls = state, 0

    def submit_trade_favors_for_gold(self, request, actor, recipient, phase, date):
        self.submit_calls += 1
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result", "request_id": request,
            "action_id": "trade_favors_for_gold", "actor": actor, "recipient": recipient,
            "phase": phase, "date_raw": date, "submitted": True, "native_queue_verified": True,
            "transport_ring": True, "native_sequence": 7, "native_origin": 65535, "native_flags": 0}}

    def read_native_favor_gold_response(self, request, actor, recipient, phase, date):
        public = project(response(self.state))
        return {"status": public["native_outcome"], "result": public}


class FavorTradeResultTests(unittest.TestCase):
    def test_accepted_and_rejected_have_independent_resource_proof(self):
        for state, outcome, amount, spent in [(2, "accepted", 10500, 10000), (1, "rejected", 0, 0)]:
            with self.subTest(state=state):
                result = project(response(state))
                self.assertEqual(outcome, result["native_outcome"])
                self.assertEqual(amount, result["favor_trade"]["transfer"]["raw"])
                self.assertEqual(spent, result["favor_trade"]["favors"]["spent_raw"])
                self.assertEqual("FRA", result["favor_trade"]["controlled_treasury"]["country"])
                self.assertNotIn("recipient_treasury_raw", json.dumps(result))

    def test_claimed_success_requires_both_balances_and_favor_cost(self):
        for key in ("actor_treasury_raw", "recipient_treasury_raw", "favors_raw", "cost_raw"):
            bad = response()
            bad["favor_trade"]["after"][key] += 1
            with self.subTest(key=key):
                self.assertIsNone(project(bad))
        bad = response(1)
        bad["favor_trade"]["after"]["favors_raw"] -= 1
        self.assertIsNone(project(bad))

    def test_inbound_bound_decision_and_own_treasury_only(self):
        result = project(response(2, "LIT", "FRA", "accept"), 77)
        self.assertEqual(189500, result["favor_trade"]["controlled_treasury"]["after_raw"])
        self.assertIsNone(project(response(1, "LIT", "FRA", "accept"), 77))
        self.assertIsNone(project(response(2, "LIT", "FRA", "accept")))
        bad = response()
        bad["request_id"] = "another_request"
        self.assertIsNone(project(bad))

    def test_full_api_execution_result_persists_and_duplicate_does_not_resubmit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.sqlite3"
            session = ExecutionSession()
            with DurableJournal(path, session.experiment_id, session.session_id) as journal:
                api = DiplomacyTools(journal, session)
                first = api.execute_diplomatic_action(
                    "gold_001", "trade_favors_for_gold", "FRA", "PAP")
                self.assertTrue(first["submitted"])
                self.assertEqual("accepted", first["game_outcome"])
                duplicate = api.execute_diplomatic_action(
                    "gold_001", "trade_favors_for_gold", "FRA", "PAP")
                self.assertIs(duplicate.pop("idempotent"), True)
                self.assertEqual(first, duplicate)
                self.assertEqual(1, session.submit_calls)
                stored = copy.deepcopy(api.get_diplomatic_result("gold_001"))
            with DurableJournal(path, session.experiment_id, session.session_id) as journal:
                self.assertEqual(stored, DiplomacyTools(journal, session).get_diplomatic_result("gold_001"))


if __name__ == "__main__":
    unittest.main()
