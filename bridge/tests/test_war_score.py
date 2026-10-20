import copy
import unittest

from bridge.war_score import (
    EVENT,
    FAILED_EVENTS,
    attach_live_war_score,
    project_live_war_score,
    unknown_war_score,
    validate_live_war_score_event,
)


IDENTITY = {
    "query_id": "inspect_war_score_001",
    "session_id": "1234-abcdef",
    "action_id": "white_peace",
    "actor": "FRA",
    "recipient": "SAV",
    "phase": "query",
    "date_raw": 56553384,
    "war_id": "war_fra_sav_1",
}


def _event():
    tooltip = "e68898e4ba89e58886"
    return {
        "event": EVENT,
        "family": "war_score",
        **IDENTITY,
        "war_context": {"war_id": "war_fra_sav_1"},
        "score": {
            "mode": "whole_war", "mode_raw": 0, "perspective": "actor",
            "total_raw": 42, "total_available": True,
            "total_unit": "native_war_score_raw", "total_scale": 1,
            "max_score_raw": 100, "max_score_scale": 1,
            "overview_goal_cap_raw": 25000,
            "overview_goal_cap_scale": 1000,
            "goal": {
                "available": True, "cumulative_raw": 12500,
                "cumulative_unit": "native_war_score_raw",
                "cumulative_scale": 1000, "presence_verified": True,
            },
            "daily": {"available": False, "score_raw": None},
            "scale_verified": True, "complete": True, "verified": True,
        },
        "tooltip": {
            "requested": True, "text_hex": tooltip,
            "text_readable": True, "text_truncated": False,
            "text_size": 9, "string_capacity": 15,
            "codec": "configured_native_text_codec", "complete": True,
        },
        "verification": {
            "actor_handle_valid": True, "recipient_handle_valid": True,
            "pair_reference_sets_equal": True, "war_id_bound_to_pair": True,
            "side_vectors_verified": True, "score_perspective_verified": True,
            "goal_direction_verified": True, "complete": True, "verified": True,
        },
    }


class LiveWarScoreTests(unittest.TestCase):
    def test_verified_scales_and_tooltip_project(self):
        event = _event()
        self.assertTrue(validate_live_war_score_event(event, **IDENTITY))
        public = project_live_war_score(event, **IDENTITY)
        self.assertEqual("available", public["status"])
        self.assertEqual(42, public["total"]["raw"])
        self.assertEqual(42, public["total"]["value"])
        self.assertEqual(12.5, public["goal"]["cumulative"]["value"])
        self.assertEqual(25.0, public["overview_goal_cap"]["value"])
        self.assertEqual("战争分", public["tooltip"]["text"])
        self.assertTrue(public["complete"])

    def test_identity_binding_is_strict(self):
        event = _event()
        standalone = copy.deepcopy(event)
        standalone["action_id"] = "live_war_score"
        self.assertTrue(validate_live_war_score_event(standalone, **IDENTITY))
        self.assertIsNone(project_live_war_score(
            event, **{**IDENTITY, "war_id": "other_war"}))
        self.assertIsNone(project_live_war_score(
            event, **{**IDENTITY, "query_id": "other_query"}))
        self.assertIsNone(project_live_war_score(
            event, **{**IDENTITY, "date_raw": IDENTITY["date_raw"] + 1}))

    def test_unavailable_zero_is_rejected_and_missing_is_unknown(self):
        event = _event()
        event["score"]["total_available"] = False
        event["score"]["total_raw"] = 0
        self.assertFalse(validate_live_war_score_event(event, **IDENTITY))
        self.assertEqual("unknown", unknown_war_score()["status"])
        self.assertIsNone(unknown_war_score()["total"]["raw"])

    def test_failure_and_truncated_layers_are_preserved(self):
        failed = _event()
        failed["event"] = next(iter(FAILED_EVENTS))
        failed["error_code"] = "WAR_CONTEXT_STALE"
        failed["complete"] = False
        failed["verified"] = False
        failure = project_live_war_score(failed, **IDENTITY)
        self.assertEqual("failed", failure["status"])
        self.assertEqual("WAR_CONTEXT_STALE", failure["error"])

        truncated = copy.deepcopy(_event())
        truncated["tooltip"]["text_truncated"] = True
        truncated["tooltip"]["complete"] = False
        public = project_live_war_score(truncated, **IDENTITY)
        self.assertEqual("truncated", public["status"])
        self.assertEqual(42, public["total"]["raw"])
        self.assertFalse(public["complete"])

    def test_attach_only_selected_peace_context(self):
        result = {"peace_context": {"war_id": IDENTITY["war_id"], "terms": []}}
        attached = attach_live_war_score(
            result, _event(), enabled=True, **IDENTITY)
        self.assertIs(attached, result)
        self.assertEqual(
            "available", result["peace_context"]["war_context"]["war_score"]["status"])
        self.assertEqual("war_fra_sav_1", result["peace_context"]["war_context"]["war_id"])
        untouched = {"peace_context": {"war_id": IDENTITY["war_id"], "terms": []}}
        attach_live_war_score(
            untouched, _event(), enabled=False, **IDENTITY)
        self.assertNotIn("war_context", untouched["peace_context"])


if __name__ == "__main__":
    unittest.main()
