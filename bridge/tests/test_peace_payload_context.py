from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import ObserverSession

try:
    import test_peace_tools as _peace_tools
except ModuleNotFoundError:
    from bridge.tests import test_peace_tools as _peace_tools  # type: ignore

REAL_PAYLOAD_FIXTURE = (Path(__file__).parent / "fixtures" /
                        "peace_payload_r40b_real_inspections.json")


class PeacePayloadContextTests(unittest.TestCase):
    """Regression coverage for the public R40 peace payload projections."""

    def setUp(self) -> None:
        # Reuse the established fixture and QUERY4/public reader harness
        # without inheriting the full PeaceToolsTests suite.
        self._harness = _peace_tools.PeaceToolsTests()
        self._harness.setUp()

    def tearDown(self) -> None:
        self._harness.tearDown()

    @staticmethod
    def _base_event() -> dict:
        return json.loads(
            Path(_peace_tools.EMPTY_OFFER_FIXTURE).read_text(encoding="utf-8")
        )["event"]

    @staticmethod
    def _war_context() -> dict:
        return {
            "war_context_resolved": True,
            "side_a_members": ["FRA"],
            "side_a_count": 1,
            "side_b_members": ["ENG", "SAV"],
            "side_b_count": 2,
            "participant_lists_complete": True,
            "selected_side": "side_a",
            "actor_side": "side_a",
            "recipient_side": "side_b",
            "actor_side_verified": True,
            "recipient_side_verified": True,
            "actor_recipient_opposite": True,
            "offer_identity_verified": True,
            "offer_vectors_readable": True,
            "primary_offer_mapping_verified": True,
            "derived_offer_mapping_verified": True,
            "offer_vector_mapping_verified": True,
            "roles_verified": False,
            "leaders_verified": False,
            "context_complete": False,
            # These fields are native-only and must not reach the public
            # semantic projection.
            "side_a_native_ref": "0xprivate-a",
            "side_b_participantvectoroffset": "0xprivate-b",
        }

    @staticmethod
    def _complete_payload() -> dict:
        return {
            "schema": "native_peace_serialized_fields_v1",
            "capture_available": True,
            "serialized_fields_complete": True,
            "source_copy_equal": True,
            "serialized_fields_unchanged": True,
            "source_owner_verified": True,
            "action_owner_verified": True,
            "term_count": 2,
            "selected_term_count": 1,
            "unsupported_term_count": 0,
            "selected_index_complete": True,
            "authority_bound": False,
            # Native addresses and raw serialized bytes are private.
            "native_ref": "0xprivate-offer",
            "source_address": "0xprivate-source",
            "raw_serialized_tail": "private",
        }

    def _event_with_payload(self, payload: dict | None = None) -> dict:
        event = self._base_event()
        event["native_war_context"] = self._war_context()
        event["native_payload"] = (
            self._complete_payload() if payload is None else payload
        )
        return event

    def _run_public_query(self, event: dict) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._harness._installation(
                root, empty_offer_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            return self._harness._run_empty_offer_query(session, event)

    def test_r40b_real_payload_events_replay_through_public_reader(self) -> None:
        fixture = json.loads(REAL_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(2, fixture["event_count"])
        self.assertEqual(
            ["46780-1dd5d2adc49edf3"],
            fixture["provenance"]["session_ids"])
        self.assertEqual(
            "f3a6e301a9b8925f6d037566bed3590e591db2cb0420615de5bd09ac3c89e4d6",
            fixture["provenance"]["dll_sha256"])
        events = {event["action_id"]: event for event in fixture["events"]}
        white = events["white_peace"]
        money = events["demand_ducats"]

        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            white, "white_peace", "FRA", "ENG", "initiate",
            white["date_raw"], white["war_id"], white["query_id"],
            white["session_id"]))
        self.assertTrue(ObserverSession._valid_native_peace_money_offer_inspection(
            money, "demand_ducats", "FRA", "ENG", "initiate",
            money["date_raw"], {
                "war_id": money["war_id"], "direction": "demand",
                "amount_raw": 10000, "payer": "ENG", "claimant": "FRA"},
            money["query_id"], money["session_id"]))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._harness._installation(
                    root, empty_offer_ack=True, evaluation_ack=True),
                root / "eu4.exe")
            white_result = self._harness._run_empty_offer_query(session, white)
        self.assertTrue(white_result["native_payload"][
            "serialized_fields_complete"])
        self.assertEqual(87, white_result["native_payload"]["term_count"])
        self.assertEqual(-45, white_result["native_evaluation"]["native_total"])
        self.assertEqual(0, white_result["costs"]["native_evaluation"][
            "aggregate_score_raw"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._harness._installation(
                    root, money_offer_ack=True, evaluation_ack=True),
                root / "eu4.exe")
            money_result = self._harness._run_money_query(
                session, money, amount="10.0")
        self.assertTrue(money_result["native_payload"][
            "serialized_fields_complete"])
        self.assertEqual(87, money_result["native_payload"]["term_count"])
        self.assertEqual(-100, money_result["acceptance"]["native_total"])
        self.assertEqual(1, money_result["costs"]["native_evaluation"][
            "aggregate_score_raw"])
        self.assertEqual(
            money_result["peace_context"]["terms"],
            money_result["parameters"]["actual"]["peace_context"]["terms"])

        public_text = json.dumps(
            {"white": white_result, "money": money_result}, ensure_ascii=False)
        for private_key in (
                "native_ref", "source_address", "raw_serialized_tail",
                "native_caller", "participantvectoroffset", "private"):
            self.assertNotIn(private_key, public_text)

    def test_complete_side_and_payload_project_publicly_without_private_fields(
            self) -> None:
        event = self._event_with_payload()

        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))
        result = self._run_public_query(event)

        context = result["native_war_context"]
        self.assertEqual(["FRA"], context["side_a_members"])
        self.assertEqual(["ENG", "SAV"], context["side_b_members"])
        self.assertTrue(context["offer_vector_mapping_verified"])
        self.assertFalse(context["context_complete"])

        payload = result["native_payload"]
        self.assertTrue(payload["capture_available"])
        self.assertTrue(payload["serialized_fields_complete"])
        self.assertTrue(payload["source_copy_equal"])
        self.assertTrue(payload["serialized_fields_unchanged"])
        self.assertEqual(2, payload["term_count"])
        self.assertEqual(1, payload["selected_term_count"])

        public_text = json.dumps(result, ensure_ascii=False)
        for private_key in (
                "side_a_native_ref", "side_b_participantvectoroffset",
                "native_ref", "source_address", "raw_serialized_tail",
                "frame_thread", "participantvectoroffset"):
            self.assertNotIn(private_key, public_text)

    def test_war_context_rejects_wrong_membership_and_duplicate_tags(self) -> None:
        event = self._event_with_payload()
        wrong_membership = dict(event["native_war_context"])
        wrong_membership["side_a_members"] = ["ENG"]
        wrong_membership["side_a_count"] = 1
        self.assertFalse(ObserverSession._valid_native_peace_war_context(
            wrong_membership, "FRA", "ENG"))

        duplicate_tag = dict(event["native_war_context"])
        duplicate_tag["side_b_members"] = ["ENG", "ENG"]
        duplicate_tag["side_b_count"] = 2
        self.assertFalse(ObserverSession._valid_native_peace_war_context(
            duplicate_tag, "FRA", "ENG"))

    def test_unsupported_term_keeps_payload_partial_and_equal_fields_null(
            self) -> None:
        payload = self._complete_payload()
        payload.update({
            "serialized_fields_complete": False,
            "source_copy_equal": None,
            "serialized_fields_unchanged": None,
            "selected_index_complete": False,
            "unsupported_term_count": 1,
        })
        event = self._event_with_payload(payload)

        self.assertTrue(ObserverSession._valid_native_peace_payload(payload))
        projected = ObserverSession._semantic_peace_payload(payload)
        self.assertFalse(projected["serialized_fields_complete"])
        self.assertIsNone(projected["source_copy_equal"])
        self.assertIsNone(projected["serialized_fields_unchanged"])

        result = self._run_public_query(event)
        public_payload = result["native_payload"]
        self.assertFalse(public_payload["serialized_fields_complete"])
        self.assertEqual(1, public_payload["unsupported_term_count"])
        self.assertIsNone(public_payload["source_copy_equal"])
        self.assertIsNone(public_payload["serialized_fields_unchanged"])


if __name__ == "__main__":
    unittest.main()
