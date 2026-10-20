import copy
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.gift_influence import (
    GIFT_ACTION_ID, INFLUENCE_ACTION_ID, GIFT_QUERY_CAPABILITY,
    GIFT_SUBMISSION_CAPABILITY, INFLUENCE_QUERY_CAPABILITY,
    INFLUENCE_SUBMISSION_CAPABILITY, validate_gift_query,
    validate_influence_query, validate_gift_result, validate_influence_result,
)


DATE = 56553384


def _gift_query():
    return {
        "kind": "gift", "ducats": 25, "amount_raw": 25000,
        "amount_readable": True, "resource_scale": 1000,
        "actor_treasury_raw": 100000, "recipient_treasury_raw": 200000,
        "complete": True,
    }


def _influence_query():
    return {
        "kind": "influence", "opinion_raw": 5, "duration_months": 60,
        "native_costs": {"resource": "ducats", "amount_raw": 10000},
        "native_description": "native cost", "complete": True,
    }


def _gift_event(state=2, *, request_id="gift_1", outcome="accepted"):
    before = {"complete": True, "actor_treasury_raw": 100000,
              "recipient_treasury_raw": 200000}
    after = dict(before)
    if state in (0, 2):
        after.update(actor_treasury_raw=75000, recipient_treasury_raw=225000)
    payload = {"kind": "gift", "before": before, "after": after,
               "ducats": 25, "amount_raw": 25000,
               "complete": True, "verified": True}
    return {
        "event": "native_diplomacy_gift_execution_result",
        "request_id": request_id, "session_id": "gift-session",
        "action_id": GIFT_ACTION_ID, "family": "gift", "actor": "FRA",
        "recipient": "PAP", "phase": "initiate", "date_raw": DATE,
        "native_state": state, "outcome": outcome,
        "execution_verified": True, "request_binding_verified": True,
        "gift": payload,
    }


class GiftInfluenceQuerySession:
    record = {"controlled_countries": ["FRA"]}
    session_id = "gift-session"
    experiment_id = "r74-gift"

    def __init__(self, capabilities=None):
        self.calls = []
        self.capabilities = frozenset(capabilities or {
            GIFT_QUERY_CAPABILITY, GIFT_SUBMISSION_CAPABILITY,
            INFLUENCE_QUERY_CAPABILITY, INFLUENCE_SUBMISSION_CAPABILITY,
        })

    def health(self):
        return {"status": "ready", "date_raw": DATE, "state_id": "s",
                "reasons": [], "complete": True}

    def installation_capabilities(self):
        return self.capabilities

    def inspect_send_gift(self, action, actor, recipient, phase, ducats):
        self.calls.append((action, actor, recipient, phase, ducats))
        event = {"event": "native_alliance_inspection", "action_id": action,
                 "family": "gift", "actor": actor, "recipient": recipient,
                 "phase": phase, "date_raw": DATE,
                 "native_validity": True, "common_action_gate": True,
                 "initiation_gate": True, "full_rules_complete": True,
                 "score_applicable": False, "score_available": False,
                 "acceptance_predicate_available": False,
                 "native_gift": {**_gift_query(), "ducats": ducats,
                                 "amount_raw": ducats * 1000}}
        return event

    def inspect_influence_nation(self, action, actor, recipient, phase):
        self.calls.append((action, actor, recipient, phase))
        return {"event": "native_alliance_inspection", "action_id": action,
                "family": "influence", "actor": actor, "recipient": recipient,
                "phase": phase, "date_raw": DATE,
                "native_validity": True, "common_action_gate": True,
                "initiation_gate": True, "full_rules_complete": True,
                 "score_applicable": False, "score_available": False,
                 "acceptance_predicate_available": False,
                "native_influence": _influence_query()}


class GiftExecutionSession(GiftInfluenceQuerySession):
    def __init__(self):
        super().__init__({GIFT_QUERY_CAPABILITY, GIFT_SUBMISSION_CAPABILITY})
        self.submit_calls = 0

    def submit_send_gift(self, request_id, actor, recipient, phase, date_raw, *, ducats):
        self.submit_calls += 1
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result", "request_id": request_id,
            "action_id": GIFT_ACTION_ID, "family": "gift", "actor": actor,
            "recipient": recipient, "phase": phase, "date_raw": date_raw,
            "submitted": True, "native_queue_verified": True,
            "transport_ring": True, "native_sequence": 7,
            "native_origin": 65535, "native_flags": 0,
            "ducats": ducats, "amount_raw": ducats * 1000,
        }}

    def read_native_gift_execution(self, request_id, actor, recipient, phase,
                                   date_raw, ducats):
        event = _gift_event(request_id=request_id)
        event["session_id"] = self.session_id
        event["date_raw"] = date_raw
        return {"status": "executed", "result":
                ObserverSession._public_native_gift_influence_result(
                    event, request_id, self.session_id, actor, recipient,
                    phase, date_raw, GIFT_ACTION_ID, ducats)}


class InfluenceExecutionSession(GiftInfluenceQuerySession):
    def __init__(self):
        super().__init__({INFLUENCE_QUERY_CAPABILITY,
                          INFLUENCE_SUBMISSION_CAPABILITY})
        self.submit_calls = 0

    def submit_influence_nation(self, request_id, actor, recipient, phase, date_raw):
        self.submit_calls += 1
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result", "request_id": request_id,
            "action_id": INFLUENCE_ACTION_ID, "family": "influence", "actor": actor,
            "recipient": recipient, "phase": phase, "date_raw": date_raw,
            "submitted": True, "native_queue_verified": True,
            "transport_ring": True, "native_sequence": 8,
            "native_origin": 65535, "native_flags": 0,
        }}

    def read_native_influence_execution(self, request_id, actor, recipient, phase,
                                        date_raw):
        event = _influence_event(request_id=request_id)
        event["session_id"] = self.session_id
        event["date_raw"] = date_raw
        return {"status": "executed", "result":
                ObserverSession._public_native_gift_influence_result(
                    event, request_id, self.session_id, actor, recipient,
                    phase, date_raw, INFLUENCE_ACTION_ID)}


def _influence_event(state=2, *, request_id="influence_1", outcome="accepted"):
    before = {"complete": True, "actor_treasury_raw": 100000,
              "recipient_trust_raw": 98, "influencer_active": False}
    after = dict(before)
    if state in (0, 2):
        after.update(actor_treasury_raw=90000,
                     recipient_trust_raw=100, influencer_active=True)
    payload = {"kind": "influence", "before": before, "after": after,
               "cost_raw": 10000, "opinion_raw": 5,
               "duration_months": 60, "complete": True, "verified": True}
    return {
        "event": "native_diplomacy_influence_execution_result",
        "request_id": request_id, "session_id": "gift-session",
        "action_id": INFLUENCE_ACTION_ID, "family": "influence", "actor": "FRA",
        "recipient": "PAP", "phase": "initiate", "date_raw": DATE,
        "native_state": state, "outcome": outcome,
        "execution_verified": True, "request_binding_verified": True,
        "influence": payload,
    }


class GiftInfluenceTests(unittest.TestCase):
    def test_catalog_and_request_contract(self):
        tools = DiplomacyTools(None, None)
        by_id = {x["action_id"] for x in tools.list_diplomatic_actions()["actions"]}
        self.assertIn(GIFT_ACTION_ID, by_id)
        self.assertIn(INFLUENCE_ACTION_ID, by_id)
        with self.assertRaisesRegex(ValueError, "GIFT_DUCATS_MULTIPLE_OF_25"):
            tools.inspect_diplomatic_action(GIFT_ACTION_ID, "FRA", "PAP",
                                            parameters={"ducats": 26})
        with self.assertRaisesRegex(ValueError, "GIFT_DUCATS_INTEGER"):
            tools.inspect_diplomatic_action(GIFT_ACTION_ID, "FRA", "PAP",
                                            parameters={"ducats": True})
        with self.assertRaisesRegex(ValueError, "INFLUENCE_PARAMETERS_UNSUPPORTED"):
            tools.inspect_diplomatic_action(INFLUENCE_ACTION_ID, "FRA", "PAP",
                                            parameters={"months": 60})
        with self.assertRaisesRegex(ValueError, "GIFT_INITIATE_ONLY"):
            tools.inspect_diplomatic_action(GIFT_ACTION_ID, "FRA", "PAP", "accept",
                                            parameters={"ducats": 25})

    def test_native_query_preserves_native_amount_and_influence_cost(self):
        session = GiftInfluenceQuerySession()
        tools = DiplomacyTools(None, session)
        gift = tools.inspect_diplomatic_action(
            GIFT_ACTION_ID, "FRA", "PAP", parameters={"ducats": 25})
        self.assertEqual("available", gift["legality"]["status"])
        self.assertEqual(25, gift["gift"]["amount"]["ducats"])
        self.assertEqual(100000, gift["gift"]["controlled_treasury"]["raw"])
        self.assertNotIn("recipient_raw", gift["gift"]["controlled_treasury"])
        self.assertEqual("not_applicable", gift["acceptance"]["applicability"])
        influence = tools.inspect_diplomatic_action(
            INFLUENCE_ACTION_ID, "FRA", "PAP")
        self.assertEqual("available", influence["legality"]["status"])
        self.assertEqual(60, influence["influence"]["duration"]["months"])
        self.assertEqual(10000,
                         influence["influence"]["native"]["native_costs"]["amount_raw"])

    def test_support_and_authorization_are_separate_from_query(self):
        session = GiftInfluenceQuerySession({GIFT_SUBMISSION_CAPABILITY})
        result = DiplomacyTools(None, session).inspect_diplomatic_action(
            GIFT_ACTION_ID, "FRA", "PAP", parameters={"ducats": 25})
        self.assertEqual(GIFT_SUBMISSION_CAPABILITY,
                         result["interface_support"]["execute"])
        self.assertEqual("available", result["authorization"]["status"])
        self.assertEqual("catalog_only", result["interface_support"]["query"])
        self.assertEqual("unknown", result["legality"]["status"])

    def test_result_arithmetic_and_clamp_are_independent(self):
        gift = _gift_event()
        public = ObserverSession._public_native_gift_influence_result(
            gift, "gift_1", "gift-session", "FRA", "PAP", "initiate", DATE,
            GIFT_ACTION_ID, 25)
        self.assertEqual("executed", public["native_outcome"])
        self.assertEqual(-25000, public["gift"]["transfer"]["actor_change_raw"])
        tampered = copy.deepcopy(gift)
        tampered["gift"]["after"]["actor_treasury_raw"] += 1
        self.assertIsNone(ObserverSession._public_native_gift_influence_result(
            tampered, "gift_1", "gift-session", "FRA", "PAP", "initiate", DATE,
            GIFT_ACTION_ID, 25))
        raw_zero = _gift_event(state=0, outcome="executed")
        raw_public = ObserverSession._public_native_gift_influence_result(
            raw_zero, "gift_1", "gift-session", "FRA", "PAP", "initiate", DATE,
            GIFT_ACTION_ID, 25)
        self.assertEqual("executed", raw_public["native_outcome"])
        rejected = _gift_event(state=1, outcome="rejected")
        rejected_public = ObserverSession._public_native_gift_influence_result(
            rejected, "gift_1", "gift-session", "FRA", "PAP", "initiate", DATE,
            GIFT_ACTION_ID, 25)
        self.assertEqual("rejected", rejected_public["native_outcome"])
        self.assertEqual(0, rejected_public["gift"]["transfer"]["actor_change_raw"])
        influence_before = {"complete": True, "actor_treasury_raw": 100000,
                            "recipient_trust_raw": 98, "influencer_active": False}
        influence_after = {"complete": True, "actor_treasury_raw": 90000,
                           "recipient_trust_raw": 100, "influencer_active": True}
        influence_payload = {
            "kind": "influence", "before": influence_before,
            "after": influence_after, "cost_raw": 10000, "opinion_raw": 5,
            "duration_months": 60, "complete": True, "verified": True,
        }
        self.assertTrue(validate_influence_result(influence_payload, 2))
        influence = _influence_event()
        influence_public = ObserverSession._public_native_gift_influence_result(
            influence, "influence_1", "gift-session", "FRA", "PAP", "initiate", DATE,
            INFLUENCE_ACTION_ID)
        self.assertEqual("executed", influence_public["native_outcome"])
        self.assertEqual(100, influence_public["influence"]["trust"]["after_raw"])
        self.assertTrue(validate_influence_result(influence["influence"], 0))
        self.assertTrue(validate_gift_query(_gift_query()))
        self.assertTrue(validate_influence_query(_influence_query()))
        self.assertTrue(validate_gift_result(_gift_event()["gift"], 2))

    def test_execution_is_idempotent_and_binds_amount(self):
        session = GiftExecutionSession()
        with tempfile.TemporaryDirectory() as temporary:
            journal_path = Path(temporary) / "journal.sqlite3"
            with DurableJournal(journal_path, session.experiment_id,
                                session.session_id) as journal:
                api = DiplomacyTools(journal, session)
                first = api.execute_diplomatic_action(
                    "gift_1", GIFT_ACTION_ID, "FRA", "PAP",
                    parameters={"ducats": 25})
                self.assertTrue(first["submitted"])
                self.assertEqual("executed", first["game_outcome"])
                duplicate = api.execute_diplomatic_action(
                    "gift_1", GIFT_ACTION_ID, "FRA", "PAP",
                    parameters={"ducats": 25})
                self.assertTrue(duplicate.pop("idempotent"))
                self.assertEqual(first, duplicate)
                self.assertEqual(1, session.submit_calls)

    def test_influence_execution_uses_native_cost_and_is_idempotent(self):
        session = InfluenceExecutionSession()
        with tempfile.TemporaryDirectory() as temporary:
            journal_path = Path(temporary) / "journal.sqlite3"
            with DurableJournal(journal_path, session.experiment_id,
                                session.session_id) as journal:
                api = DiplomacyTools(journal, session)
                first = api.execute_diplomatic_action(
                    "influence_1", INFLUENCE_ACTION_ID, "FRA", "PAP")
                self.assertTrue(first["submitted"])
                self.assertEqual("executed", first["game_outcome"])
                self.assertEqual(100,
                                 first["result"]["influence"]["trust"]["after_raw"])
                duplicate = api.execute_diplomatic_action(
                    "influence_1", INFLUENCE_ACTION_ID, "FRA", "PAP")
                self.assertTrue(duplicate.pop("idempotent"))
                self.assertEqual(first, duplicate)
                self.assertEqual(1, session.submit_calls)


if __name__ == "__main__":
    unittest.main()
