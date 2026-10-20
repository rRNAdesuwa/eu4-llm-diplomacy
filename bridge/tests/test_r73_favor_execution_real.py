import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "bridge" / "tests" / "fixtures" / "r73_favor_execution_real.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _case(name: str) -> dict:
    rows = [row for row in FIXTURE["cases"] if row.get("name") == name]
    if len(rows) != 1:
        raise AssertionError(f"missing execution fixture case: {name}")
    row = copy.deepcopy(rows[0])
    raw = row["raw"]
    canonical = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != row["raw_sha256"]:
        raise AssertionError(f"execution raw sha mismatch: {name}")
    return row


class R73FavorExecutionRealTests(unittest.TestCase):
    def test_fixture_has_six_source_hash_bound_final_verified_events(self):
        self.assertEqual(
            "r73_favor_trade_execution_real_fixture_v1", FIXTURE["format"])
        self.assertEqual(6, len(FIXTURE["cases"]))
        self.assertEqual(6, len(FIXTURE["source_reports"]))
        for row in FIXTURE["cases"]:
            self.assertEqual("favor_trade", row["raw"]["family"])
            self.assertTrue(row["raw"]["favor_trade"]["complete"])
            self.assertTrue(row["raw"]["favor_trade"]["verified"])
            self.assertRegex(row["source_report_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(row["source_native_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(row["source_native_line_sha256"], r"^[0-9a-f]{64}$")

    def test_public_result_consumes_each_real_accept_and_reject(self):
        expected_outcomes = {
            "trust_outbound_accept": "accepted",
            "trust_inbound_reject": "rejected",
            "men_inbound_reject": "rejected",
            "men_outbound_accept": "accepted",
            "trust_inbound_accept": "accepted",
            "men_inbound_accept": "accepted",
        }
        for name, expected_outcome in expected_outcomes.items():
            with self.subTest(name=name):
                row = _case(name)
                raw = row["raw"]
                public = ObserverSession._public_native_favor_resource_result(
                    raw, row["request_id"], row["session_id"], row["actor"],
                    row["recipient"], row["phase"], row["date_raw"],
                    row["action_id"], row.get("native_proposal_id"))
                self.assertIsNotNone(public)
                self.assertEqual(expected_outcome, public["native_outcome"])
                self.assertEqual(row["action_id"], public["action_id"])
                self.assertEqual(row["actor"], public["actor"])
                self.assertEqual(row["recipient"], public["recipient"])
                self.assertEqual(row["phase"], public["phase"])
                self.assertTrue(public["favor_trade"]["verified"])
                self.assertEqual(
                    raw["favor_trade"]["kind"], public["favor_trade"]["kind"])

    def test_real_accept_reject_formulas_and_tamper_rejection(self):
        for name in (
                "trust_outbound_accept", "trust_inbound_reject",
                "trust_inbound_accept", "men_outbound_accept",
                "men_inbound_reject", "men_inbound_accept"):
            with self.subTest(name=name):
                row = _case(name)
                payload = row["raw"]["favor_trade"]
                before = payload["before"]
                after = payload["after"]
                amount = payload["amount_raw"]
                accepted = row["native_state"] == 2
                if payload["kind"] == "trust":
                    expected_trust = min(
                        100, before["recipient_trust_raw"] + amount)
                    if accepted:
                        self.assertEqual(
                            expected_trust, after["recipient_trust_raw"])
                        self.assertEqual(
                            before["favors_raw"] - before["cost_raw"],
                            after["favors_raw"],
                        )
                    else:
                        self.assertEqual(before, after)
                else:
                    if accepted:
                        self.assertEqual(
                            before["actor_manpower_raw"] + amount,
                            after["actor_manpower_raw"],
                        )
                        self.assertEqual(
                            before["recipient_manpower_raw"] - amount,
                            after["recipient_manpower_raw"],
                        )
                        self.assertEqual(
                            before["favors_raw"] - before["cost_raw"],
                            after["favors_raw"],
                        )
                    else:
                        self.assertEqual(before, after)

        accepted_men = _case("men_outbound_accept")
        wrong_kind = copy.deepcopy(accepted_men["raw"])
        wrong_kind["favor_trade"]["kind"] = "trust"
        self.assertIsNone(ObserverSession._public_native_favor_resource_result(
            wrong_kind, accepted_men["request_id"], accepted_men["session_id"],
            accepted_men["actor"], accepted_men["recipient"],
            accepted_men["phase"], accepted_men["date_raw"],
            accepted_men["action_id"], accepted_men.get("native_proposal_id")))

        wrong_action = copy.deepcopy(accepted_men["raw"])
        wrong_action["action_id"] = "trade_favors_for_trust"
        self.assertIsNone(ObserverSession._public_native_favor_resource_result(
            wrong_action, accepted_men["request_id"], accepted_men["session_id"],
            accepted_men["actor"], accepted_men["recipient"],
            accepted_men["phase"], accepted_men["date_raw"],
            accepted_men["action_id"], accepted_men.get("native_proposal_id")))

        wrong_delta = copy.deepcopy(accepted_men["raw"])
        wrong_delta["favor_trade"]["after"]["actor_manpower_raw"] += 1
        self.assertIsNone(ObserverSession._public_native_favor_resource_result(
            wrong_delta, accepted_men["request_id"], accepted_men["session_id"],
            accepted_men["actor"], accepted_men["recipient"],
            accepted_men["phase"], accepted_men["date_raw"],
            accepted_men["action_id"], accepted_men.get("native_proposal_id")))


if __name__ == "__main__":
    unittest.main()
