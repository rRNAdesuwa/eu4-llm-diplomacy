import copy
import json
import unittest

from bridge.diplomacy import ObserverSession


ACTION = "trade_favors_for_trust"
ACTOR = "PAP"
RECIPIENT = "FRA"
REQUEST_ID = "trust-inbound-001"
SESSION_ID = "trust-inbound-session"
QUERY_ID = "trust-query-001"
DATE_RAW = 56553384
PROPOSAL_ID = 77


def query_payload():
    return {
        "kind": "trust", "amount_raw": 10, "amount_readable": True,
        "favor_cost_raw": 7000, "favors_available_raw": 20000,
        "recipient_trust_raw": 95, "resource_scale": 1, "complete": True,
    }


def state_payload(trust=95, favors=20000, cost=7000):
    return {"complete": True, "recipient_trust_raw": trust,
            "favors_raw": favors, "cost_raw": cost}


def inspection_event():
    return {
        "event": "native_alliance_inbound_inspection", "query_id": QUERY_ID,
        "session_id": SESSION_ID, "action_id": ACTION, "family": "favor_trade",
        "actor": ACTOR, "recipient": RECIPIENT, "phase": "accept",
        "native_proposal_id": PROPOSAL_ID, "date_raw": DATE_RAW,
        "pending_active": True, "decision_country": RECIPIENT,
        "decision_country_verified": True, "native_validity": True,
        "response_rules_complete": True, "reason": "none", "extra60": 0,
        "favor_trade": query_payload(),
    }


def submission_event():
    return {
        "event": "native_alliance_submission_result", "request_id": REQUEST_ID,
        "session_id": SESSION_ID, "action_id": ACTION, "family": "favor_trade",
        "actor": ACTOR, "recipient": RECIPIENT, "phase": "accept",
        "date_raw": DATE_RAW, "native_proposal_id": PROPOSAL_ID,
        "submitted": True, "native_queue_verified": True,
        "transport_ring": True, "transport_ring_receipt": True,
        "native_sequence": 7, "native_origin": 65535, "native_flags": 0,
        "favor_trade": {
            "kind": "trust", "before": state_payload(), "after": None,
            "amount_raw": 10, "complete": True, "verified": False,
        },
    }


def response_event(phase="accept", native_state=2):
    before = state_payload()
    after = state_payload(100, 13000) if native_state == 2 else copy.deepcopy(before)
    return {
        "event": "native_diplomacy_favor_trade_response_result",
        "request_id": REQUEST_ID, "session_id": SESSION_ID,
        "action_id": ACTION, "family": "favor_trade", "actor": ACTOR,
        "recipient": RECIPIENT, "phase": phase, "date_raw": DATE_RAW,
        "native_proposal_id": PROPOSAL_ID, "native_state": native_state,
        "native_variant": 1,
        "outcome": "accepted" if native_state == 2 else "rejected",
        "execution_verified": True, "request_binding_verified": True,
        "pending_removed": True,
        "favor_trade": {"kind": "trust", "before": before, "after": after,
                         "amount_raw": 10, "complete": True, "verified": True},
    }


class FavorResourceInboundTests(unittest.TestCase):
    def test_inspection_validates_direction_and_projects_favor_cost(self):
        event = inspection_event()
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, QUERY_ID, SESSION_ID, ACTOR, "accept", PROPOSAL_ID,
            DATE_RAW, ACTION))
        public = ObserverSession._public_native_inbound_inspection(
            event, DATE_RAW, ACTION)
        self.assertEqual("trust", public["favor_trade"]["kind"])
        self.assertEqual("recipient_to_actor",
                         public["favor_trade"]["trust"]["direction"])
        self.assertEqual(7, public["costs"]["items"][0]["amount"])
        self.assertEqual(1000, public["costs"]["items"][0]["scale"])
        self.assertNotIn("recipient_trust_raw", json.dumps(public))

    def test_submission_receipt_requires_matching_kind_and_hides_preview(self):
        event = submission_event()
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            event, REQUEST_ID, SESSION_ID, ACTOR, RECIPIENT, "accept",
            DATE_RAW, PROPOSAL_ID, ACTION))
        receipt = ObserverSession._public_native_inbound_submission_receipt(
            event, REQUEST_ID, ACTOR, "accept", DATE_RAW, ACTION)
        self.assertEqual("favor_trade", receipt["family"])
        self.assertNotIn("favor_trade", receipt)
        crossed = copy.deepcopy(event)
        crossed["favor_trade"]["kind"] = "men"
        self.assertFalse(ObserverSession._valid_native_inbound_submission_result(
            crossed, REQUEST_ID, SESSION_ID, ACTOR, RECIPIENT, "accept",
            DATE_RAW, PROPOSAL_ID, ACTION))

    def test_accept_and_reject_response_bind_proposal_and_prove_trust(self):
        accepted = ObserverSession._public_native_inbound_response_result(
            response_event(), REQUEST_ID, SESSION_ID, ACTOR, "accept", DATE_RAW,
            PROPOSAL_ID, ACTION)
        self.assertEqual("accepted", accepted["native_outcome"])
        self.assertEqual(5, accepted["favor_trade"]["trust"]["change_raw"])
        rejected = ObserverSession._public_native_inbound_response_result(
            response_event("reject", 1), REQUEST_ID, SESSION_ID, ACTOR,
            "reject", DATE_RAW, PROPOSAL_ID, ACTION)
        self.assertEqual("rejected", rejected["native_outcome"])
        bad = copy.deepcopy(response_event())
        bad["native_proposal_id"] = PROPOSAL_ID + 1
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            bad, REQUEST_ID, SESSION_ID, ACTOR, "accept", DATE_RAW,
            PROPOSAL_ID, ACTION))


if __name__ == "__main__":
    unittest.main()
