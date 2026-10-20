from __future__ import annotations

import copy
import unittest

from bridge.declarewar_participants import (
    PARTICIPANT_EVENT,
    project_participants,
    validate_participants,
)


QUERY_ID = "participant_query_001"
SESSION_ID = "participant_session_001"
ACTOR = "FRA"
RECIPIENT = "POR"
DATE_RAW = 56550000


def _reason(index: int, text: str, *, readable: bool = True,
            truncated: bool = False, value: int = 1) -> dict:
    return {
        "index": index,
        "value": value,
        "text_hex": text.encode("utf-8").hex(),
        "readable": readable,
        "truncated": truncated,
    }


def _event(index: int, country: str, *, selected: bool,
           promise_land: bool, side: str = "attacker",
           context_complete: bool = True, score_available: bool = True,
           reasons_complete: bool = True, diagnostic: str = "可加入") -> dict:
    reasons = [_reason(0, "接受", value=4)] if score_available else []
    return {
        "event": PARTICIPANT_EVENT,
        "query_id": QUERY_ID,
        "session_id": SESSION_ID,
        "actor": ACTOR,
        "recipient": RECIPIENT,
        "date_raw": DATE_RAW,
        "index": index,
        "side": side,
        "country": country,
        "related_country": RECIPIENT if side == "attacker" else ACTOR,
        "join_reason_raw": 7 + index,
        "automatic": index == 1,
        "selected": selected,
        "promise_land": promise_land,
        "promise_available": True,
        "legality_checked": context_complete,
        "native_legality": context_complete,
        "diagnostic_hex": diagnostic.encode("utf-8").hex(),
        "diagnostic_readable": context_complete,
        "diagnostic_truncated": False,
        "score_available": score_available,
        "native_total_raw": 5 - index,
        "acceptance_threshold_raw": 1,
        "reason_count": len(reasons),
        "reasons": reasons,
        "reasons_complete": reasons_complete,
        "context_complete": context_complete,
    }


def _parent(*, complete: bool = True, selection_applied: bool = True,
            selection_allowed: bool = True, candidate_count: int = 4,
            call_allies: str = "ENG", promise: str = "ENG",
            co_belligerents: str = "AUV", called: bool = True,
            action_unchanged: bool = True) -> dict:
    return {
        "called": called,
        "complete": complete,
        "selection_applied": selection_applied,
        "selection_allowed": selection_allowed,
        "action_unchanged": action_unchanged,
        "candidate_count": candidate_count,
        "requested_call_allies_csv": call_allies,
        "requested_promise_land_to_csv": promise,
        "requested_co_belligerents_csv": co_belligerents,
    }


SELECTION = {
    "call_allies": ["ENG"],
    "promise_land_to": ["ENG"],
    "co_belligerents": ["AUV"],
}
EVENTS = [
    _event(0, "ENG", selected=True, promise_land=True),
    _event(1, "SWE", selected=False, promise_land=False,
           context_complete=False, score_available=False,
           reasons_complete=False, diagnostic="未完成"),
    _event(2, "AUV", selected=True, promise_land=False,
           side="defender"),
    # A country may participate on both sides; uniqueness is (side, country).
    _event(3, "ENG", selected=False, promise_land=False,
           side="defender"),
]


class DeclareWarParticipantsTests(unittest.TestCase):
    def test_complete_parent_and_rows_bind_selection_and_identity(self):
        parent = _parent()
        self.assertTrue(validate_participants(
            parent, EVENTS, QUERY_ID, SESSION_ID, ACTOR, RECIPIENT,
            DATE_RAW, SELECTION))
        self.assertTrue(validate_participants(
            parent, EVENTS, QUERY_ID, SESSION_ID, ACTOR, RECIPIENT,
            DATE_RAW, copy.deepcopy(SELECTION)))

    def test_projection_decodes_public_values_and_separates_completeness(self):
        public = project_participants(_parent(), EVENTS)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("native_declare_war_participants", public["source"])
        self.assertTrue(public["complete"])
        self.assertTrue(public["enumeration_complete"])
        self.assertFalse(public["legality_complete"])
        self.assertEqual(
            SELECTION,
            {key: public["selection"][key] for key in (
                "call_allies", "promise_land_to", "co_belligerents")},
        )
        first = public["candidates"][0]
        self.assertEqual("可加入", first["diagnostic"]["text"])
        self.assertEqual(5, first["willingness"]["native_total_raw"])
        self.assertEqual(1, first["willingness"]["acceptance_threshold_raw"])
        self.assertEqual(4, first["willingness"]["reasons"][0]["value"])
        self.assertTrue(first["complete"])
        incomplete = public["candidates"][1]
        self.assertFalse(incomplete["willingness"]["complete"])
        self.assertFalse(incomplete["complete"])
        serialized = str(public)
        self.assertNotIn("text_hex", serialized)
        self.assertNotIn("native_pointer", serialized)

    def test_tampered_binding_or_shape_is_rejected_without_raising(self):
        parent = _parent()
        cases = []
        changed = copy.deepcopy(parent)
        changed["requested_call_allies_csv"] = "SWE"
        cases.append((changed, EVENTS))
        changed_events = copy.deepcopy(EVENTS)
        changed_events[0]["selected"] = False
        cases.append((parent, changed_events))
        changed_events = copy.deepcopy(EVENTS)
        changed_events[1]["query_id"] = "other-query"
        cases.append((parent, changed_events))
        changed_events = copy.deepcopy(EVENTS)
        changed_events[2]["index"] = 3
        cases.append((parent, changed_events))
        changed = copy.deepcopy(parent)
        changed["candidate_count"] = 2
        cases.append((changed, EVENTS))
        changed = copy.deepcopy(parent)
        changed["called"] = False
        cases.append((changed, EVENTS))
        changed_events = copy.deepcopy(EVENTS)
        changed_events[0]["reasons"][0]["text_hex"] = "zz"
        cases.append((parent, changed_events))
        for native, events in cases:
            self.assertFalse(validate_participants(
                native, events, QUERY_ID, SESSION_ID, ACTOR, RECIPIENT,
                DATE_RAW, SELECTION))

    def test_same_country_cross_side_is_allowed_but_side_binding_is_strict(self):
        self.assertTrue(validate_participants(
            _parent(), EVENTS, QUERY_ID, SESSION_ID, ACTOR, RECIPIENT,
            DATE_RAW, SELECTION))

        duplicate_side = copy.deepcopy(EVENTS)
        duplicate_side[3]["side"] = "attacker"
        duplicate_side[3]["related_country"] = RECIPIENT
        self.assertFalse(validate_participants(
            _parent(), duplicate_side, QUERY_ID, SESSION_ID, ACTOR, RECIPIENT,
            DATE_RAW, SELECTION))

        wrong_side = copy.deepcopy(EVENTS)
        wrong_side[2]["side"] = "attacker"
        wrong_side[2]["related_country"] = RECIPIENT
        self.assertFalse(validate_participants(
            _parent(), wrong_side, QUERY_ID, SESSION_ID, ACTOR, RECIPIENT,
            DATE_RAW, SELECTION))

        defender_promise = copy.deepcopy(EVENTS)
        defender_promise[2]["promise_land"] = True
        self.assertFalse(validate_participants(
            _parent(), defender_promise, QUERY_ID, SESSION_ID, ACTOR,
            RECIPIENT, DATE_RAW, SELECTION))

    def test_empty_discovery_has_complete_enumeration_but_no_rows(self):
        parent = _parent(
            candidate_count=0, selection_applied=False,
            selection_allowed=False, call_allies="-", promise="-",
            co_belligerents="-",
        )
        self.assertTrue(validate_participants(
            parent, [], "discovery-query", "discovery-session", ACTOR,
            RECIPIENT, DATE_RAW))
        public = project_participants(parent, [])
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual([], public["candidates"])
        self.assertTrue(public["enumeration_complete"])
        self.assertTrue(public["legality_complete"])

    def test_incomplete_text_is_safe_and_codec_is_explicit(self):
        events = copy.deepcopy(EVENTS)
        events[0]["diagnostic_hex"] = "ff"
        public = project_participants(_parent(), events)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertIsNone(public["candidates"][0]["diagnostic"]["text"])
        self.assertFalse(public["candidates"][0]["diagnostic"]["complete"])
        self.assertIsNone(project_participants(_parent(), EVENTS, "gbk"))


if __name__ == "__main__":
    unittest.main()
