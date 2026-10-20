import copy
import tempfile
import unittest
from pathlib import Path

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.favor_resources import NATIVE_ACCEPT, NATIVE_REJECT, project_result
from bridge.tests.test_favor_resources_tools import ResourceQuerySession


DATE_RAW = 56553384


def trust_state(trust, favors, cost, complete=True):
    return {"complete": complete, "recipient_trust_raw": trust,
            "favors_raw": favors, "cost_raw": cost}


def men_state(actor, recipient, favors, cost, complete=True):
    return {"complete": complete, "actor_manpower_raw": actor,
            "recipient_manpower_raw": recipient, "favors_raw": favors,
            "cost_raw": cost}


def resource_event(action_id="trade_favors_for_trust", state=2,
                   actor="FRA", recipient="PAP", phase="initiate",
                   proposal_id=None, verified=True):
    if action_id == "trade_favors_for_trust":
        before = trust_state(95, 20000, 7000)
        after = trust_state(100, 13000, 7000) if state == 2 else copy.deepcopy(before)
        kind = "trust"
        amount = 10
    else:
        before = men_state(100, 50, 40000, 10000)
        after = men_state(125, 25, 30000, 10000) if state == 2 else copy.deepcopy(before)
        kind = "men"
        amount = 25
    inbound = phase in ("accept", "reject")
    event = {
        "event": ("native_diplomacy_favor_trade_response_result"
                   if inbound else "native_diplomacy_favor_trade_execution_result"),
        "request_id": "resource-001", "session_id": "resource-session",
        "action_id": action_id, "family": "favor_trade", "actor": actor,
        "recipient": recipient, "phase": phase, "date_raw": DATE_RAW,
        "native_state": state, "outcome": (
            "accepted" if state == 2 and verified else
            "rejected" if state == 1 and verified else "unknown"),
        "execution_verified": True, "request_binding_verified": True,
        "pending_removed": True,
        "favor_trade": {"kind": kind, "before": before, "after": after,
                         "amount_raw": amount, "complete": True,
                         "verified": verified},
    }
    if proposal_id is not None:
        event["native_proposal_id"] = proposal_id
    return event


class ResourceExecutionSession(ResourceQuerySession):
    session_id = "resource-session"
    experiment_id = "resource-experiment"

    def __init__(self):
        super().__init__()
        self.submit_calls = 0

    def submit_trade_favors_for_trust(self, request_id, actor, recipient,
                                      phase, date_raw):
        self.submit_calls += 1
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result",
            "request_id": request_id, "session_id": self.session_id,
            "action_id": "trade_favors_for_trust", "family": "favor_trade",
            "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": date_raw, "submitted": True,
            "native_queue_verified": True, "transport_ring": True,
            "transport_ring_receipt": True, "native_sequence": 7,
            "native_origin": 65535, "native_flags": 0,
        }}

    def read_native_favor_trust_response(self, request_id, actor, recipient,
                                         phase, date_raw):
        event = resource_event()
        event["request_id"] = request_id
        event["session_id"] = self.session_id
        public = ObserverSession._public_native_favor_resource_result(
            event, request_id, self.session_id, actor, recipient, phase,
            date_raw, "trade_favors_for_trust")
        return {"status": public["native_outcome"], "result": public}


class FavorResourceResultTests(unittest.TestCase):
    def test_outbound_result_binds_action_kind_and_proves_trust(self):
        event = resource_event()
        public = ObserverSession._public_native_favor_resource_result(
            event, "resource-001", "resource-session", "FRA", "PAP",
            "initiate", DATE_RAW, "trade_favors_for_trust")
        self.assertEqual("accepted", public["native_outcome"])
        self.assertEqual(5, public["favor_trade"]["trust"]["change_raw"])
        self.assertEqual(7000, public["favor_trade"]["favors"]["spent_raw"])
        crossed = copy.deepcopy(event)
        crossed["favor_trade"]["kind"] = "men"
        self.assertIsNone(ObserverSession._public_native_favor_resource_result(
            crossed, "resource-001", "resource-session", "FRA", "PAP",
            "initiate", DATE_RAW, "trade_favors_for_trust"))

    def test_reject_and_unverified_results_do_not_claim_resource_change(self):
        rejected = resource_event(state=NATIVE_REJECT)
        public = ObserverSession._public_native_favor_resource_result(
            rejected, "resource-001", "resource-session", "FRA", "PAP",
            "initiate", DATE_RAW, "trade_favors_for_trust")
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(0, public["favor_trade"]["favors"]["spent_raw"])
        unknown = resource_event(verified=False)
        public = ObserverSession._public_native_favor_resource_result(
            unknown, "resource-001", "resource-session", "FRA", "PAP",
            "initiate", DATE_RAW, "trade_favors_for_trust")
        self.assertEqual("unknown", public["native_outcome"])
        self.assertIsNone(public["favor_trade"]["trust"]["change_raw"])

    def test_full_execution_is_idempotent_and_does_not_resubmit(self):
        with tempfile.TemporaryDirectory() as temporary:
            journal_path = Path(temporary) / "journal.sqlite3"
            session = ResourceExecutionSession()
            with DurableJournal(journal_path, session.experiment_id,
                                session.session_id) as journal:
                api = DiplomacyTools(journal, session)
                first = api.execute_diplomatic_action(
                    "resource-001", "trade_favors_for_trust", "FRA", "PAP")
                self.assertTrue(first["submitted"])
                self.assertEqual("accepted", first["game_outcome"])
                second = api.execute_diplomatic_action(
                    "resource-001", "trade_favors_for_trust", "FRA", "PAP")
                self.assertTrue(second.pop("idempotent"))
                self.assertEqual(first, second)
                self.assertEqual(1, session.submit_calls)


if __name__ == "__main__":
    unittest.main()
