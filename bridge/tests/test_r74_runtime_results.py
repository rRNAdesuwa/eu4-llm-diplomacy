"""R74 game captures preserve the real settlement and war-score contracts."""
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession
from bridge.war_score import project_live_war_score, validate_live_war_score_event


FIXTURES = Path(__file__).parent / "fixtures"


class RuntimeResultTests(unittest.TestCase):
    def test_actual_gift_and_influence_settlements(self):
        events = json.loads((FIXTURES / "r74_economic_execution_real.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(events))
        for event in events:
            with self.subTest(action=event["action_id"]):
                public = ObserverSession._public_native_gift_influence_result(
                    event, event["request_id"], event["session_id"], event["actor"],
                    event["recipient"], event["phase"], event["date_raw"],
                    event["action_id"], 25 if event["action_id"] == "send_gift" else None)
                self.assertIsNotNone(public)
                self.assertEqual("executed", public["native_outcome"])
                self.assertTrue(public["execution_verified"])
                self.assertTrue(public["request_binding_verified"])

    def test_actual_war_goal_and_chinese_tooltip_share_actor_perspective(self):
        events = json.loads((FIXTURES / "r74_live_war_score_real.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(events))
        for event in events:
            with self.subTest(actor=event["actor"]):
                identity = {key: event[key] for key in (
                    "query_id", "session_id", "action_id", "actor", "recipient",
                    "phase", "date_raw", "war_id")}
                self.assertTrue(validate_live_war_score_event(event, **identity))
                public = project_live_war_score(event, codec="eu4_escape", **identity)
                self.assertTrue(public["complete"])
                self.assertEqual(0, public["total"]["raw"])
                self.assertEqual(1, public["total"]["scale"])
                expected = -400 if event["actor"] == "FRA" else 400
                self.assertEqual(expected, public["goal"]["cumulative"]["raw"])
                self.assertEqual(1000, public["goal"]["cumulative"]["scale"])
                self.assertIn("-0.40" if expected < 0 else "+0.40", public["tooltip"]["text"])
                self.assertIn("阿图瓦", public["tooltip"]["text"])
