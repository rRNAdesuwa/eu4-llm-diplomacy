import copy
import json
import unittest

from bridge.diplomacy import ObserverSession


ACTION = "trade_favors_for_gold"
ACTOR = "LIT"
RECIPIENT = "FRA"
REQUEST_ID = "gold_inbound_001"
SESSION_ID = "gold-inbound-session"
QUERY_ID = "gold-query-001"
DATE_RAW = 56553384
NATIVE_PROPOSAL_ID = 77


def query_payload():
    return {
        "kind": "gold",
        "amount_raw": 10500,
        "amount_readable": True,
        "favor_cost_raw": 10000,
        "favors_available_raw": 15000,
        "actor_treasury_raw": 100000,
        "recipient_treasury_raw": 200000,
        "resource_scale": 1000,
        "complete": True,
    }


def state_payload(actor_treasury=100000, recipient_treasury=200000,
                  favors=15000, cost=10000):
    return {
        "complete": True,
        "actor_treasury_raw": actor_treasury,
        "recipient_treasury_raw": recipient_treasury,
        "favors_raw": favors,
        "cost_raw": cost,
    }


def inspection_event():
    return {
        "event": "native_alliance_inbound_inspection",
        "query_id": QUERY_ID,
        "session_id": SESSION_ID,
        "action_id": ACTION,
        "family": "favor_trade",
        "actor": ACTOR,
        "recipient": RECIPIENT,
        "phase": "accept",
        "native_proposal_id": NATIVE_PROPOSAL_ID,
        "date_raw": DATE_RAW,
        "pending_active": True,
        "decision_country": RECIPIENT,
        "decision_country_verified": True,
        "native_validity": True,
        "response_rules_complete": True,
        "reason": "none",
        "extra60": 0,
        "favor_trade": query_payload(),
    }


def submission_event():
    return {
        "event": "native_alliance_submission_result",
        "request_id": REQUEST_ID,
        "session_id": SESSION_ID,
        "action_id": ACTION,
        "family": "favor_trade",
        "actor": ACTOR,
        "recipient": RECIPIENT,
        "phase": "accept",
        "date_raw": DATE_RAW,
        "native_proposal_id": NATIVE_PROPOSAL_ID,
        "submitted": True,
        "native_queue_verified": True,
        "transport_ring": True,
        "transport_ring_receipt": True,
        "native_sequence": 7,
        "native_origin": 65535,
        "native_flags": 0,
        "favor_trade": {
            "before": state_payload(),
            "after": None,
            "amount_raw": 10500,
            "complete": True,
            "verified": False,
        },
    }


def offer_event():
    return {
        "event": "native_alliance_inbound_offer",
        "session_id": SESSION_ID,
        "proposal_id": NATIVE_PROPOSAL_ID,
        "action_id": ACTION,
        "family": "favor_trade",
        "extra60": 0,
        "phase": "initiate",
        "actor": ACTOR,
        "mirror": ACTOR,
        "recipient": RECIPIENT,
        "date28": 1,
        "date2c": 2,
        "envoy30": 3,
        "state34": 0,
        "variant38": 1,
        "proposal3c": 4,
        "token3c": 5,
        "created2c": 6,
        "queue_before_count": 0,
        "queue_after_count": 1,
        "queue_readable": True,
        "list_integrity": True,
        "new_entry": True,
        "payload_readable": True,
        "decision_country": RECIPIENT,
        "decision_country_verified": True,
        "pending_source": "native_executor_pending_block",
        "source_verified": True,
        "call_redirected": True,
        "business_result": "pending_observed",
    }


def response_event(phase="accept", native_state=2):
    before = state_payload()
    after = state_payload(110500, 189500, 5000) if native_state == 2 else before
    return {
        "event": "native_diplomacy_favor_trade_response_result",
        "request_id": REQUEST_ID,
        "session_id": SESSION_ID,
        "action_id": ACTION,
        "family": "favor_trade",
        "actor": ACTOR,
        "recipient": RECIPIENT,
        "phase": phase,
        "date_raw": DATE_RAW,
        "native_proposal_id": NATIVE_PROPOSAL_ID,
        "native_state": native_state,
        "native_variant": 1,
        "outcome": "accepted" if native_state == 2 else "rejected",
        "execution_verified": True,
        "request_binding_verified": True,
        "pending_removed": True,
        "favor_trade": {
            "before": before,
            "after": after,
            "amount_raw": 10500,
            "complete": True,
            "verified": True,
        },
    }


class FavorTradeInboundTests(unittest.TestCase):
    def test_pending_offer_binds_favor_trade_family(self):
        event = offer_event()
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            event, SESSION_ID))
        crossed = copy.deepcopy(event)
        crossed["family"] = "alliance"
        self.assertFalse(ObserverSession._valid_native_inbound_offer_event(
            crossed, SESSION_ID))

    def test_inspection_validates_and_projects_query_without_raw_balances(self):
        event = inspection_event()
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, QUERY_ID, SESSION_ID, ACTOR, "accept", NATIVE_PROPOSAL_ID,
            DATE_RAW, ACTION))

        public = ObserverSession._public_native_inbound_inspection(
            event, DATE_RAW, ACTION)
        self.assertEqual("favor_trade", public["family"])
        self.assertEqual("gold", public["favor_trade"]["kind"])
        self.assertEqual(10.5, public["favor_trade"]["amount"]["value"])
        self.assertEqual(10.0, public["costs"]["items"][0]["amount"])
        self.assertNotIn("recipient_treasury_raw", json.dumps(public))

    def test_inspection_rejects_incomplete_or_cross_family_query(self):
        missing_scale = inspection_event()
        missing_scale["favor_trade"].pop("resource_scale")
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            missing_scale, QUERY_ID, SESSION_ID, ACTOR, "accept",
            NATIVE_PROPOSAL_ID, DATE_RAW, ACTION))

        crossed = inspection_event()
        crossed["family"] = "peace"
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            crossed, QUERY_ID, SESSION_ID, ACTOR, "accept",
            NATIVE_PROPOSAL_ID, DATE_RAW, ACTION))

        wrong_extra = inspection_event()
        wrong_extra["extra60"] = 1
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            wrong_extra, QUERY_ID, SESSION_ID, ACTOR, "accept",
            NATIVE_PROPOSAL_ID, DATE_RAW, ACTION))

        bool_extra = inspection_event()
        bool_extra["extra60"] = False
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            bool_extra, QUERY_ID, SESSION_ID, ACTOR, "accept",
            NATIVE_PROPOSAL_ID, DATE_RAW, ACTION))

    def test_submission_receipt_binds_family_and_drops_private_state(self):
        event = submission_event()
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            event, REQUEST_ID, SESSION_ID, ACTOR, RECIPIENT, "accept",
            DATE_RAW, NATIVE_PROPOSAL_ID, ACTION))

        receipt = ObserverSession._public_native_inbound_submission_receipt(
            event, REQUEST_ID, ACTOR, "accept", DATE_RAW, ACTION)
        self.assertIsInstance(receipt, dict)
        self.assertEqual("favor_trade", receipt["family"])
        self.assertNotIn("favor_trade", receipt)
        self.assertNotIn("recipient_treasury_raw", json.dumps(receipt))

        reduced = copy.deepcopy(event)
        reduced.pop("native_proposal_id")
        reduced.pop("favor_trade")
        reduced_receipt = ObserverSession._public_native_inbound_submission_receipt(
            reduced, REQUEST_ID, ACTOR, "accept", DATE_RAW, ACTION)
        self.assertEqual("favor_trade", reduced_receipt["family"])

        malformed = copy.deepcopy(event)
        malformed["favor_trade"]["after"] = state_payload()
        self.assertFalse(ObserverSession._valid_native_inbound_submission_result(
            malformed, REQUEST_ID, SESSION_ID, ACTOR, RECIPIENT, "accept",
            DATE_RAW, NATIVE_PROPOSAL_ID, ACTION))

    def test_response_projects_controlled_french_treasury_only(self):
        event = response_event()
        public = ObserverSession._public_native_inbound_response_result(
            event, REQUEST_ID, SESSION_ID, ACTOR, "accept", DATE_RAW,
            NATIVE_PROPOSAL_ID, ACTION)
        self.assertEqual("accepted", public["native_outcome"])
        self.assertEqual("FRA", public["favor_trade"]["controlled_treasury"]["country"])
        self.assertEqual(189500, public["favor_trade"]["controlled_treasury"]["after_raw"])
        self.assertNotIn("recipient_treasury_raw", json.dumps(public))

        rejected = ObserverSession._public_native_inbound_response_result(
            response_event("reject", 1), REQUEST_ID, SESSION_ID, ACTOR,
            "reject", DATE_RAW, NATIVE_PROPOSAL_ID, ACTION)
        self.assertEqual("rejected", rejected["native_outcome"])

    def test_response_requires_bound_proposal_and_native_event(self):
        event = response_event()
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            event, REQUEST_ID, SESSION_ID, ACTOR, "accept", DATE_RAW, None, ACTION))

        crossed = copy.deepcopy(event)
        crossed["family"] = "peace"
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            crossed, REQUEST_ID, SESSION_ID, ACTOR, "accept", DATE_RAW,
            NATIVE_PROPOSAL_ID, ACTION))

    def test_gold_inbound_response_wrapper_is_exposed(self):
        self.assertTrue(hasattr(
            ObserverSession, "read_native_favor_gold_inbound_response"))


if __name__ == "__main__":
    unittest.main()
