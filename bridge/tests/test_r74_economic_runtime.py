"""Replay real R74 query records through the public adapter without game calls."""
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession


FIXTURE = json.loads((Path(__file__).parent / "fixtures" /
                     "r74_economic_queries_real.json").read_text(encoding="utf-8"))


class ReplaySession:
    record = {"controlled_countries": ["FRA"]}

    def __init__(self, event):
        self.event = event

    def health(self):
        return {"status": "ready", "date_raw": self.event["date_raw"],
                "state_id": "replay", "reasons": [], "complete": True}

    def installation_capabilities(self):
        return frozenset({"native_gift_query", "native_gift_submission",
                          "native_influence_query", "native_influence_submission"})

    def inspect_send_gift(self, *args):
        return ObserverSession._semantic_inspection(self.event, {}, codec="eu4_escape")

    inspect_influence_nation = inspect_send_gift


class EconomicRuntimeTests(unittest.TestCase):
    def test_real_semantic_query_including_influence_native_cost(self):
        for event in FIXTURE["economic_events"]:
            with self.subTest(action=event["action_id"]):
                action = event["action_id"]
                parameters = ({"ducats": event["native_gift"]["ducats"]}
                              if action == "send_gift" else {})
                public = DiplomacyTools(None, ReplaySession(event)).inspect_diplomatic_action(
                    action, "FRA", "PAP", parameters=parameters)
                self.assertEqual("unavailable", public["legality"]["status"])
                self.assertEqual({"status": "visible", "complete": True}, public["visibility"])
                self.assertIn("外交官", public["legality"]["reasons"][0]["text"])
                self.assertEqual("not_applicable", public["acceptance"]["applicability"])
                if action == "influence_nation":
                    self.assertEqual(73668, public["costs"]["items"][0]["amount_raw"])
                    self.assertEqual(1000, public["costs"]["items"][0]["scale"])

    def test_using_favors_key_survives_both_projection_boundaries(self):
        raw = FIXTURE["favor_reason"]
        semantic = ObserverSession._semantic_reason_item(raw, "eu4_escape", True)
        self.assertTrue(semantic["identifier_verified"])
        items = DiplomacyTools._public_acceptance_items([semantic], True)
        self.assertTrue(items[0]["identifier_verified"])
        self.assertEqual("USING_FAVORS", items[0]["native_identifier"])
        self.assertEqual(50, items[0]["native_value"])
