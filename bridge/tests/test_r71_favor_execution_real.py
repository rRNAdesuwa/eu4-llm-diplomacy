"""Targeted replay tests for the real R71 favor-for-gold execution evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession
from bridge.favor_trade import ACTION_ID, validate_query, validate_result
from bridge.native_text import EU4_ESCAPE_CODEC


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "bridge/tests/fixtures/r71_favor_execution_real.json"


class R71FavorExecutionRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.outbound = cls.fixture["outbound"]
        cls.execution = cls.outbound["execution_result"]
        cls.inbound = cls.fixture["inbound_accept"]
        cls.inbound_reject = cls.fixture["inbound_reject"]

    def _public_execution(self, event: dict) -> dict | None:
        return ObserverSession._public_native_favor_gold_result(
            event,
            self.fixture["request_id"],
            self.fixture["session_id"],
            self.fixture["actor"],
            self.fixture["recipient"],
            self.fixture["phase"],
            self.fixture["date_raw"],
        )

    def test_real_submission_and_accepted_execution_replay(self) -> None:
        submission = self.outbound["submission_result"]
        self.assertTrue(ObserverSession._valid_native_submission_result(
            submission,
            self.fixture["request_id"],
            self.fixture["session_id"],
            self.fixture["actor"],
            self.fixture["recipient"],
            self.fixture["phase"],
            self.fixture["date_raw"],
            ACTION_ID,
        ))

        raw_trade = self.execution["favor_trade"]
        self.assertTrue(validate_result(raw_trade, self.execution["native_state"]))
        expected = self.fixture["outbound_expected"]
        before = raw_trade["before"]
        after = raw_trade["after"]
        self.assertEqual(after["actor_treasury_raw"] - before["actor_treasury_raw"],
                         expected["amount_raw"])
        self.assertEqual(before["recipient_treasury_raw"] - after["recipient_treasury_raw"],
                         expected["amount_raw"])
        self.assertEqual(before["favors_raw"] - after["favors_raw"],
                         expected["favors_cost_raw"])

        public = self._public_execution(self.execution)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(public["native_outcome"], expected["native_outcome"])
        self.assertEqual(public["native_state"], expected["native_state"])
        trade = public["favor_trade"]
        self.assertEqual(trade["amount"]["raw"], expected["amount_raw"])
        self.assertEqual(trade["amount"]["value"], expected["amount_value"])
        self.assertEqual(trade["transfer"]["raw"], expected["amount_raw"])
        self.assertEqual(trade["favors"]["before_raw"], expected["favors_before_raw"])
        self.assertEqual(trade["favors"]["after_raw"], expected["favors_after_raw"])
        self.assertEqual(trade["controlled_treasury"]["before_raw"],
                         expected["actor_treasury_before_raw"])
        self.assertEqual(trade["controlled_treasury"]["after_raw"],
                         expected["actor_treasury_after_raw"])

    def test_payment_and_favor_tampering_is_rejected(self) -> None:
        mutations = {
            "amount": lambda event: event["favor_trade"].__setitem__(
                "amount_raw", event["favor_trade"]["amount_raw"] + 1),
            "recipient_payment": lambda event: event["favor_trade"]["after"].__setitem__(
                "recipient_treasury_raw",
                event["favor_trade"]["after"]["recipient_treasury_raw"] + 1),
            "favors": lambda event: event["favor_trade"]["after"].__setitem__(
                "favors_raw", event["favor_trade"]["after"]["favors_raw"] + 1),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                tampered = copy.deepcopy(self.execution)
                mutate(tampered)
                self.assertFalse(validate_result(
                    tampered["favor_trade"], tampered["native_state"]))
                self.assertIsNone(self._public_execution(tampered))

    def test_positive_query_replays_acceptance_factors_141_50_91(self) -> None:
        query = self.fixture["query_positive"]
        inspection = query["inspection"]
        self.assertTrue(validate_query(inspection["native_favor_trade"]))
        reasons = {
            item["index"]: item for item in query["reason_items"]
        }
        semantic = ObserverSession._semantic_inspection(
            inspection, reasons, codec=EU4_ESCAPE_CODEC)
        expected = query["expected"]
        self.assertEqual(semantic["native_total_raw"], expected["native_total_raw"])
        self.assertEqual(semantic["acceptance_threshold_raw"],
                         expected["acceptance_threshold_raw"])
        self.assertTrue(semantic["native_would_accept"])
        self.assertEqual(
            [item["native_value"] for item in semantic["reason_items"]],
            expected["reason_values"],
        )
        self.assertEqual(
            [item["name"] for item in semantic["reason_items"]],
            expected["reason_names"],
        )
        self.assertEqual(semantic["native_diagnostic_text"],
                         expected["diagnostic_text"])
        self.assertEqual(semantic["favor_trade"]["amount"]["raw"], 12927)
        self.assertEqual(semantic["favor_trade"]["favors"]["current_raw"], 33632)

    def test_real_inbound_accept_replay_exposes_only_controlled_fra_treasury(self) -> None:
        inbound = self.inbound
        inspection = inbound["inspection"]
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection,
            inspection["query_id"],
            inbound["session_id"],
            inbound["actor"],
            inbound["phase"],
            inbound["native_proposal_id"],
            inbound["date_raw"],
            ACTION_ID,
        ))
        self.assertTrue(ObserverSession._valid_native_submission_result(
            inbound["submission_result"],
            inbound["request_id"],
            inbound["session_id"],
            inbound["actor"],
            inbound["recipient"],
            inbound["phase"],
            inbound["date_raw"],
            ACTION_ID,
        ))
        raw_trade = inbound["response_result"]["favor_trade"]
        expected = inbound["expected"]
        self.assertTrue(validate_result(raw_trade, inbound["response_result"]["native_state"]))
        self.assertEqual(
            raw_trade["before"]["recipient_treasury_raw"]
            - raw_trade["after"]["recipient_treasury_raw"],
            expected["amount_raw"],
        )
        self.assertEqual(
            raw_trade["before"]["favors_raw"] - raw_trade["after"]["favors_raw"],
            expected["favors_cost_raw"],
        )

        public = ObserverSession._public_native_favor_gold_result(
            inbound["response_result"], inbound["request_id"],
            inbound["session_id"], inbound["actor"], inbound["recipient"],
            inbound["phase"], inbound["date_raw"], inbound["native_proposal_id"],
        )
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(public["native_outcome"], expected["native_outcome"])
        self.assertEqual(public["native_state"], expected["native_state"])
        self.assertTrue(public["pending_removed"])
        trade = public["favor_trade"]
        self.assertEqual(trade["amount"]["raw"], expected["amount_raw"])
        self.assertEqual(trade["amount"]["value"], expected["amount_value"])
        self.assertEqual(trade["amount"]["payer"], "FRA")
        self.assertEqual(trade["amount"]["receiver"], "SAV")
        self.assertEqual(trade["favors"]["before_raw"], expected["favors_before_raw"])
        self.assertEqual(trade["favors"]["after_raw"], expected["favors_after_raw"])
        self.assertEqual(trade["favors"]["held_by"], "SAV")
        self.assertEqual(trade["favors"]["owed_by"], "FRA")
        controlled = trade["controlled_treasury"]
        self.assertEqual(controlled["country"], expected["controlled_country"])
        self.assertEqual(controlled["before_raw"], expected["controlled_treasury_before_raw"])
        self.assertEqual(controlled["after_raw"], expected["controlled_treasury_after_raw"])

        def keys(value: object) -> set[str]:
            if isinstance(value, dict):
                return set(value) | {key for item in value.values() for key in keys(item)}
            if isinstance(value, list):
                return {key for item in value for key in keys(item)}
            return set()

        public_keys = keys(public)
        self.assertNotIn("actor_treasury_raw", public_keys)
        self.assertNotIn("recipient_treasury_raw", public_keys)

    def test_inbound_payment_and_favor_tampering_is_rejected(self) -> None:
        inbound = self.inbound
        mutations = {
            "recipient_payment": lambda event: event["favor_trade"]["after"].__setitem__(
                "recipient_treasury_raw",
                event["favor_trade"]["after"]["recipient_treasury_raw"] + 1),
            "favors": lambda event: event["favor_trade"]["after"].__setitem__(
                "favors_raw", event["favor_trade"]["after"]["favors_raw"] + 1),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                tampered = copy.deepcopy(inbound["response_result"])
                mutate(tampered)
                self.assertFalse(validate_result(
                    tampered["favor_trade"], tampered["native_state"]))
                self.assertIsNone(ObserverSession._public_native_favor_gold_result(
                    tampered, inbound["request_id"], inbound["session_id"],
                    inbound["actor"], inbound["recipient"], inbound["phase"],
                    inbound["date_raw"], inbound["native_proposal_id"],
                ))

    def test_real_inbound_reject_keeps_treasury_and_favors_unchanged(self) -> None:
        inbound = self.inbound_reject
        inspection = inbound["inspection"]
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection,
            inspection["query_id"],
            inbound["session_id"],
            inbound["actor"],
            inbound["phase"],
            inbound["native_proposal_id"],
            inbound["date_raw"],
            ACTION_ID,
        ))
        self.assertTrue(ObserverSession._valid_native_submission_result(
            inbound["submission_result"],
            inbound["request_id"],
            inbound["session_id"],
            inbound["actor"],
            inbound["recipient"],
            inbound["phase"],
            inbound["date_raw"],
            ACTION_ID,
        ))
        raw_response = inbound["response_result"]
        raw_trade = raw_response["favor_trade"]
        expected = inbound["expected"]
        self.assertTrue(validate_result(raw_trade, raw_response["native_state"]))
        self.assertEqual(raw_response["native_state"], expected["native_state"])
        self.assertEqual(raw_trade["before"], raw_trade["after"])
        self.assertEqual(raw_trade["before"]["favors_raw"], expected["favors_before_raw"])
        self.assertEqual(raw_trade["after"]["favors_raw"], expected["favors_after_raw"])

        public = ObserverSession._public_native_favor_gold_result(
            raw_response, inbound["request_id"], inbound["session_id"],
            inbound["actor"], inbound["recipient"], inbound["phase"],
            inbound["date_raw"], inbound["native_proposal_id"],
        )
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(public["native_outcome"], expected["native_outcome"])
        self.assertEqual(public["native_state"], expected["native_state"])
        self.assertTrue(public["pending_removed"])
        trade = public["favor_trade"]
        self.assertEqual(trade["transfer"]["raw"], expected["transfer_raw"])
        self.assertEqual(trade["favors"]["before_raw"], expected["favors_before_raw"])
        self.assertEqual(trade["favors"]["after_raw"], expected["favors_after_raw"])
        self.assertEqual(trade["favors"]["spent_raw"], 0)
        controlled = trade["controlled_treasury"]
        self.assertEqual(controlled["country"], expected["controlled_country"])
        self.assertEqual(controlled["before_raw"], expected["controlled_treasury_before_raw"])
        self.assertEqual(controlled["after_raw"], expected["controlled_treasury_after_raw"])
        self.assertNotIn("actor_treasury_raw", json.dumps(public, ensure_ascii=False))
        self.assertNotIn("recipient_treasury_raw", json.dumps(public, ensure_ascii=False))

    def test_fixture_is_self_contained_and_bounded(self) -> None:
        self.assertLess(FIXTURE_PATH.stat().st_size, 1_000_000)
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("C:\\Users\\", text)
        self.assertEqual(self.fixture["format"], "r71_favor_execution_real_fixture_v1")


if __name__ == "__main__":
    unittest.main()
