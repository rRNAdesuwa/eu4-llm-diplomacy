import hashlib
import json
import unittest
from pathlib import Path
import tempfile

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_catalog import ACTIONS, INBOUND_ACTIONS
from bridge.diplomacy_journal import DurableJournal


WAR_ID = "war_3fead0a5641ef4f5_00000001"


def peace_context():
    return {
        "war_id": WAR_ID,
        "direction": "demand",
        "terms": [{"action_id": "demand_ducats", "amount_raw": 10000,
                   "scale": 1000}],
        "original_actor": "ENG",
        "original_recipient": "FRA",
        "complete": True,
    }


def inbound_inspection(**overrides):
    event = {
        "event": "native_alliance_inbound_inspection",
        "query_id": "peace-query",
        "session_id": "peace-session",
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "phase": "accept",
        "native_proposal_id": 1,
        "date_raw": 56545080,
        "pending_active": True,
        "decision_country": "FRA",
        "decision_country_verified": True,
        "native_validity": True,
        "response_rules_complete": True,
        "reason": "none",
        "war_before": True,
        "native_current_war": True,
        "native_current_war_readable": True,
        "war_active": True,
        "war_readable": True,
        "peace_payload_complete": True,
        "selected_terms_complete": True,
        "term_count": 1,
        "selected_term_count": 1,
        "peace_context": peace_context(),
        "native_proposal_pointer": "private",
    }
    event.update(overrides)
    return event


def inbound_submission(**overrides):
    event = {
        "event": "native_peace_inbound_submission_result",
        "request_id": "peace-request",
        "session_id": "peace-session",
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "decision_country": "FRA",
        "phase": "accept",
        "date_raw": 56545080,
        "submitted": True,
        "transport_verified": True,
        "request_binding_verified": True,
        "native_proposal_id": 1,
    }
    event.update(overrides)
    return event


def inbound_response(**overrides):
    event = {
        "event": "native_peace_inbound_response_result",
        "request_id": "peace-request",
        "session_id": "peace-session",
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "decision_country": "FRA",
        "phase": "accept",
        "date_raw": 56545080,
        "outcome": "accepted",
        "native_state": 2,
        "war_before": True,
        "war_after": False,
        "war_state_verified": True,
        "response_verified": True,
        "request_binding_verified": True,
        "pending_removed": True,
        "terms_verified": True,
        "peace_context": peace_context(),
    }
    event.update(overrides)
    return event


class PeaceInboundToolsTests(unittest.TestCase):
    def test_r44b_real_inspection_replays_bool_current_war_contract(self):
        fixture_path = (Path(__file__).parent / "fixtures" /
                        "peace_inbound_r44b_real_inspection.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["event_count"])
        source = fixture["source"]
        self.assertEqual(6491, source["native_events_size"])
        self.assertEqual(
            "3c71ac063a0a7db83201095ac0553a221e3e90245c1b435eb0364d7236b6430b",
            source["native_events_sha256"])
        event_record = fixture["events"][0]
        event = event_record["event"]
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
        self.assertEqual(event_record["event_sha256"],
                         hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        self.assertEqual("31e6f65296f8df687428a744103bb55724fac15279edc04baab2541d10d9a583",
                         source["dll_sha256"])
        self.assertIs(type(event["native_current_war"]), bool)
        self.assertEqual(event["peace_context"]["war_id"],
                         "war_f4b1c2ad47802221_00000001")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, event["query_id"], event["session_id"], event["actor"],
            event["phase"], event["native_proposal_id"], event["date_raw"],
            "peace_offer"))
        public = ObserverSession._public_native_inbound_inspection(
            event, event["date_raw"], "peace_offer")
        self.assertEqual("peace", public["family"])
        self.assertIs(public["native_current_war"], True)
        self.assertIs(public["war_before"], True)
        self.assertIs(public["war_active"], True)
        self.assertEqual(event["peace_context"]["war_id"],
                         public["peace_context"]["war_id"])
        self.assertEqual("ENG", public["peace_context"]["original_actor"])
        self.assertEqual("FRA", public["peace_context"]["original_recipient"])
        self.assertNotIn("native_proposal_id", public)
        self.assertNotIn("native_proposal_pointer", public)
        self.assertNotIn("token3c", public)
        self.assertNotIn("envoy30", public)
        self.assertNotIn("date28", public)

    def test_r44b_real_reject_replays_handler_submission_and_response(self):
        fixture_path = (Path(__file__).parent / "fixtures" /
                        "peace_inbound_r44b_real_reject.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(3, fixture["event_count"])
        source = fixture["source"]
        self.assertEqual(43716, source["native_events_size"])
        self.assertEqual(
            "7bf5d5fe2521b68076b37fcd4ee39545e2a7f3e7858b3a01f7688b5f17dbae1a",
            source["native_events_sha256"])
        events = {record["event"]["event"]: record
                  for record in fixture["events"]}
        self.assertEqual({"native_peace_handler_return",
                          "native_peace_inbound_submission_result",
                          "native_peace_inbound_response_result"}, set(events))
        for record in fixture["events"]:
            event = record["event"]
            canonical = json.dumps(event, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
            self.assertEqual(record["event_sha256"],
                             hashlib.sha256(canonical.encode("utf-8")).hexdigest())

        handler = events["native_peace_handler_return"]["event"]
        self.assertEqual("44940-1dd5d61a6b20a8a", handler["session_id"])
        self.assertEqual("r44b_reject_eng_peace_003", handler["request_id"])
        self.assertEqual("peace_offer", handler["action_id"])
        self.assertEqual("peace", handler["family"])
        self.assertEqual("ENG", handler["actor"])
        self.assertEqual("FRA", handler["recipient"])
        self.assertEqual("reject", handler["phase"])
        self.assertTrue(handler["handler_consumed"])
        self.assertTrue(handler["peace_payload_complete"])
        self.assertTrue(handler["transport_verified"])
        self.assertEqual(1, handler["native_state"])
        self.assertEqual(1, handler["native_forward_count"])

        submission = events["native_peace_inbound_submission_result"]["event"]
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, source["request_id"], source["session_id"], "ENG", "FRA",
            "reject", 56545080, 1, "peace_offer"))
        receipt = ObserverSession._public_native_inbound_submission_receipt(
            submission, source["request_id"], "ENG", "reject", 56545080,
            "peace_offer")
        self.assertTrue(receipt["submitted"])
        self.assertEqual("peace", receipt["family"])
        self.assertNotIn("native_proposal_id", receipt)

        response = events["native_peace_inbound_response_result"]["event"]
        result = ObserverSession._public_native_inbound_response_result(
            response, source["request_id"], source["session_id"], "ENG", "reject",
            56545080, 1, "peace_offer")
        self.assertIsNotNone(result)
        self.assertEqual("rejected", result["native_outcome"])
        self.assertEqual(1, result["native_state"])
        self.assertTrue(result["war_before"])
        self.assertTrue(result["war_after"])
        self.assertTrue(result["pending_removed"])
        self.assertFalse(result["terms_verified"])
        self.assertEqual("war_f4b1c2ad47802221_00000001",
                         result["peace_context"]["war_id"])
        self.assertEqual("ENG", result["peace_context"]["original_actor"])
        self.assertEqual("FRA", result["peace_context"]["original_recipient"])
        self.assertNotIn("execution_verified", result)
        self.assertNotIn("native_proposal_id", result)

    def test_r44d_real_accept_replays_handler_submission_and_response(self):
        fixture_path = (Path(__file__).parent / "fixtures" /
                        "peace_inbound_r44d_real_accept.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(3, fixture["event_count"])
        source = fixture["source"]
        self.assertEqual(46006, source["native_events_size"])
        self.assertEqual(
            "d798a7c2b904759757e334f383e2ac18bfe8b8a045191ad9ee37a1cfdd14fc74",
            source["native_events_sha256"])
        events = {record["event"]["event"]: record
                  for record in fixture["events"]}
        self.assertEqual({"native_peace_handler_return",
                          "native_peace_inbound_submission_result",
                          "native_peace_inbound_response_result"}, set(events))
        for record in fixture["events"]:
            event = record["event"]
            canonical = json.dumps(event, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
            self.assertEqual(record["event_sha256"],
                             hashlib.sha256(canonical.encode("utf-8")).hexdigest())

        handler = events["native_peace_handler_return"]["event"]
        self.assertEqual("r44d_accept_eng_peace_001", handler["request_id"])
        self.assertEqual("31784-1dd5d6459fb46d2", handler["session_id"])
        self.assertEqual("peace_offer", handler["action_id"])
        self.assertEqual("ENG", handler["actor"])
        self.assertEqual("FRA", handler["recipient"])
        self.assertEqual("accept", handler["phase"])
        self.assertTrue(handler["handler_consumed"])
        self.assertTrue(handler["peace_payload_complete"])
        self.assertTrue(handler["transport_verified"])
        self.assertEqual(2, handler["native_state"])
        self.assertEqual(1, handler["native_forward_count"])

        submission = events["native_peace_inbound_submission_result"]["event"]
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, source["request_id"], source["session_id"], "ENG", "FRA",
            "accept", 56545080, 1, "peace_offer"))
        receipt = ObserverSession._public_native_inbound_submission_receipt(
            submission, source["request_id"], "ENG", "accept", 56545080,
            "peace_offer")
        self.assertTrue(receipt["submitted"])
        self.assertEqual("peace", receipt["family"])
        self.assertNotIn("native_proposal_id", receipt)

        response = events["native_peace_inbound_response_result"]["event"]
        result = ObserverSession._public_native_inbound_response_result(
            response, source["request_id"], source["session_id"], "ENG", "accept",
            56545080, 1, "peace_offer")
        self.assertIsNotNone(result)
        self.assertEqual("accepted", result["native_outcome"])
        self.assertEqual(2, result["native_state"])
        self.assertTrue(result["war_before"])
        self.assertFalse(result["war_after"])
        self.assertTrue(result["pending_removed"])
        self.assertTrue(result["terms_verified"])
        self.assertEqual("war_2a33e3a3fbd9abf1_00000001",
                         result["peace_context"]["war_id"])
        self.assertEqual("ENG", result["peace_context"]["original_actor"])
        self.assertEqual("FRA", result["peace_context"]["original_recipient"])
        self.assertNotIn("execution_verified", result)
        self.assertNotIn("native_proposal_id", result)

    def test_aggregate_catalog_stays_separate_from_40_action_catalog(self):
        self.assertEqual(40, len(ACTIONS))
        self.assertEqual({"peace_offer"}, set(INBOUND_ACTIONS))
        description = INBOUND_ACTIONS["peace_offer"].describe()
        self.assertEqual(["accept", "reject"], list(description["phases"]))
        self.assertEqual("opaque_proposal_id",
                         description["parameter_definitions"]["proposal_id"]["type"])

    def test_realistic_peace_inspection_is_strictly_projected(self):
        event = inbound_inspection()
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, "peace-query", "peace-session", "ENG", "accept", 1,
            56545080, "peace_offer"))
        public = ObserverSession._public_native_inbound_inspection(
            event, 56545080, "peace_offer")
        self.assertEqual("peace", public["family"])
        self.assertEqual(WAR_ID, public["peace_context"]["war_id"])
        self.assertEqual(10000, public["peace_context"]["terms"][0]["amount_raw"])
        self.assertNotIn("native_proposal_id", public)
        self.assertNotIn("native_proposal_pointer", public)
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            {**event, "family": "support_independence"},
            "peace-query", "peace-session", "ENG", "accept", 1,
            56545080, "peace_offer"))
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            {**event, "peace_context": {**peace_context(), "war_id":
                                         "not-a-war-id"}},
            "peace-query", "peace-session", "ENG", "accept", 1,
            56545080, "peace_offer"))
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            {**event, "native_current_war": event["peace_context"]["war_id"]},
            "peace-query", "peace-session", "ENG", "accept", 1,
            56545080, "peace_offer"))

    def test_submission_and_response_use_dedicated_family_events(self):
        submission = inbound_submission()
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, "peace-request", "peace-session", "ENG", "FRA",
            "accept", 56545080, 1, "peace_offer"))
        receipt = ObserverSession._public_native_inbound_submission_receipt(
            submission, "peace-request", "ENG", "accept", 56545080, "peace_offer")
        self.assertEqual("native_peace_inbound_submission_result", receipt["event"])
        self.assertEqual("peace", receipt["family"])
        self.assertNotIn("native_proposal_id", receipt)
        accepted = ObserverSession._public_native_inbound_response_result(
            inbound_response(), "peace-request", "peace-session", "ENG", "accept",
            56545080, 1, "peace_offer")
        self.assertEqual("accepted", accepted["native_outcome"])
        self.assertFalse(accepted["war_after"])
        self.assertTrue(accepted["terms_verified"])
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            inbound_response(event="native_alliance_response_result"),
            "peace-request", "peace-session", "ENG", "accept", 56545080, 1,
            "peace_offer"))
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            inbound_response(family="royal_marriage"),
            "peace-request", "peace-session", "ENG", "accept", 56545080, 1,
            "peace_offer"))

    def test_public_inspection_keeps_original_proposer_direction_and_context(self):
        proposal_id = "a" * 32

        class FakePeaceSession:
            session_id = "peace-session"

            def health(self):
                return {"status": "ready", "state_id": "ready",
                        "date_raw": 56545080, "reasons": [], "complete": True}

            def installation_capabilities(self):
                return frozenset({"native_inbound_alliance",
                                  "native_inbound_peace_response"})

            def read_native_alliance_inbound_offers(self):
                return [{"proposal_id": proposal_id, "action_id": "peace_offer",
                         "family": "peace", "actor": "ENG", "recipient": "FRA",
                         "decision_country": "FRA", "observer_status": "observed_pending"}]

            def _native_alliance_inbound_context(self, public_id):
                if public_id != proposal_id:
                    return None
                return {"actor": "ENG", "recipient": "FRA", "native_proposal_id": 1,
                        "session_id": self.session_id, "action_id": "peace_offer",
                        "family": "peace"}

            def inspect_native_inbound_response(self, query_id, actor, phase,
                                                date_raw, native_proposal_id,
                                                action_id="offer_alliance"):
                return inbound_inspection(query_id=query_id, session_id=self.session_id,
                                          actor=actor, phase=phase, date_raw=date_raw,
                                          native_proposal_id=native_proposal_id)

            def submit_native_inbound_response(self, request_id, actor, recipient,
                                               phase, date_raw, native_proposal_id,
                                               action_id="offer_alliance"):
                event = inbound_submission(request_id=request_id,
                                           session_id=self.session_id,
                                           actor=actor, recipient=recipient,
                                           phase=phase, date_raw=date_raw)
                return {"status": "submitted", "receipt":
                        ObserverSession._public_native_inbound_submission_receipt(
                            event, request_id, actor, phase, date_raw, action_id)}

            def read_native_peace_inbound_response(self, request_id, actor, recipient,
                                                   phase, date_raw, native_proposal_id):
                event = inbound_response(request_id=request_id,
                                         session_id=self.session_id,
                                         actor=actor, recipient=recipient,
                                         phase=phase, date_raw=date_raw)
                result = ObserverSession._public_native_inbound_response_result(
                    event, request_id, self.session_id, actor, phase, date_raw,
                    native_proposal_id, "peace_offer")
                return {"status": result["native_outcome"], "result": result}

        with tempfile.TemporaryDirectory() as temp:
            journal = DurableJournal(":memory:", "peace-api", "peace-session")
            try:
                api = DiplomacyTools(journal, FakePeaceSession())
                listed = api.list_diplomatic_actions(actor="ENG", recipient="FRA")
                self.assertEqual(40, len(listed["actions"]))
                incoming = {item["action_id"] for item in listed["incoming_action_definitions"]}
                self.assertIn("peace_offer", incoming)
                inspection = api.inspect_diplomatic_action(
                    "peace_offer", "ENG", "FRA", "accept",
                    {"proposal_id": proposal_id})
                self.assertEqual("peace", inspection["family"])
                self.assertEqual(WAR_ID, inspection["peace_context"]["war_id"])
                self.assertEqual("ENG", inspection["actor"])
                self.assertEqual("FRA", inspection["recipient"])
                self.assertEqual("available", inspection["authorization"]["status"])
                self.assertTrue(inspection["peace_payload_complete"])
                self.assertNotIn("native_proposal_id", inspection)
                execution = api.execute_diplomatic_action(
                    "peace-response", "peace_offer", "ENG", "FRA", "accept",
                    {"proposal_id": proposal_id})
                self.assertEqual("accepted", execution["status"])
                self.assertEqual("peace", execution["result"]["family"])
                self.assertFalse(execution["result"]["war_after"])
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
