from __future__ import annotations

import copy
import unittest

from bridge.native_text import EU4_ESCAPE_CODEC, UnknownNativeTextCodec
from bridge.peace_rejection import (
    MAX_DIAGNOSTIC_BYTES,
    project_native_peace_rejection,
    validate_native_peace_rejection,
)


REQUEST = {
    "request_id": "r66-reject-001",
    "session_id": "session-66",
    "action_id": "cede_province",
    "actor": "FRA",
    "recipient": "ENG",
    "phase": "initiate",
    "date_raw": 56549064,
    "war_id": "war_0123456789abcdef_00000001",
    "direction": "demand",
}


def _event(*, diagnostic: str = "", readable: bool = False,
           truncated: bool = False, diagnostic_complete: bool = False,
           failure_complete: bool = True,
           reason_source: str = "native_rule",
           reason_stage: str = "province_selection") -> dict:
    return {
        "event": "native_peace_execution_rejected",
        "family": "peace",
        **REQUEST,
        "submitted": False,
        "reason_code": "NATIVE_PEACE_PROVINCE_SELECTION_UNAVAILABLE",
        "reason_stage": reason_stage,
        "reason_source": reason_source,
        "native_diagnostic_hex": diagnostic.encode("utf-8").hex(),
        "native_diagnostic_readable": readable,
        "native_diagnostic_truncated": truncated,
        "native_diagnostic_complete": diagnostic_complete,
        "failure_complete": failure_complete,
        "complete": failure_complete,
    }


class PeaceRejectionTests(unittest.TestCase):
    def test_native_rule_rejection_decodes_diagnostic_and_maps_legality(self):
        diagnostic = "原生规则拒绝了该省份条款"
        event = _event(
            diagnostic=diagnostic, readable=True, diagnostic_complete=True)
        self.assertTrue(validate_native_peace_rejection(event, **REQUEST))
        public = project_native_peace_rejection(event)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(diagnostic, public["reason"]["text"])
        self.assertEqual("native_rule", public["reason"]["source"])
        self.assertEqual("province_selection", public["reason"]["stage"])
        self.assertFalse(public["reason"]["complete"])
        self.assertEqual("unavailable", public["legality"]["status"])
        self.assertTrue(public["diagnostic"]["complete"])
        self.assertFalse(public["submitted"])
        self.assertTrue(public["binding_complete"])
        self.assertNotIn("session_id", public)
        self.assertNotIn("native_diagnostic_hex", public)

    def test_runtime_failure_uses_explicit_stage_fallback_and_stays_unknown(self):
        event = _event(
            readable=False, failure_complete=False,
            reason_source="runtime_error", reason_stage="action_copy")
        public = project_native_peace_rejection(event)
        self.assertIsNotNone(public)
        assert public is not None
        text = public["reason"]["text"]
        self.assertIn("FRA", text)
        self.assertIn("ENG", text)
        self.assertIn("cede_province", text)
        self.assertIn("复制检查", text)
        self.assertIn("未能提交", text)
        self.assertEqual("unknown", public["legality"]["status"])
        self.assertFalse(public["reason"]["complete"])
        self.assertIsNone(public["diagnostic"]["text"])

    def test_binding_mismatches_are_rejected(self):
        event = _event(diagnostic="拒绝", readable=True,
                       diagnostic_complete=True)
        for field, value in (
                ("request_id", "different"),
                ("session_id", "other-session"),
                ("war_id", "war_fedcba9876543210_00000001"),
                ("direction", "offer"),
                ("date_raw", REQUEST["date_raw"] + 1),
                ("recipient", "SWE")):
            with self.subTest(field=field):
                mismatch = copy.deepcopy(event)
                mismatch[field] = value
                self.assertFalse(
                    validate_native_peace_rejection(mismatch, **REQUEST))

    def test_malformed_core_fields_and_diagnostic_are_rejected(self):
        event = _event()
        cases = []
        malformed = copy.deepcopy(event)
        malformed["submitted"] = True
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["native_diagnostic_hex"] = "0"
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["native_diagnostic_hex"] = "aa" * (MAX_DIAGNOSTIC_BYTES + 1)
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["reason_code"] = "lower-case"
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["reason_stage"] = "not-a-stage"
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["reason_source"] = "native"
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["direction"] = []
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["reason_source"] = []
        cases.append(malformed)
        malformed = copy.deepcopy(event)
        malformed["complete"] = not malformed["failure_complete"]
        cases.append(malformed)
        for malformed in cases:
            with self.subTest(malformed=malformed):
                self.assertFalse(
                    validate_native_peace_rejection(malformed, **REQUEST))
                self.assertIsNone(project_native_peace_rejection(malformed))

    def test_unknown_fields_are_forward_compatible_and_codec_is_explicit(self):
        event = _event(diagnostic="拒绝", readable=True,
                       diagnostic_complete=True)
        event["future_native_flag"] = {"opaque": True}
        self.assertTrue(validate_native_peace_rejection(event, **REQUEST))
        self.assertIsNotNone(project_native_peace_rejection(event))
        with self.assertRaises(UnknownNativeTextCodec):
            project_native_peace_rejection(event, "gbk")

    def test_eu4_escape_diagnostic_decodes_with_configured_codec(self):
        event = _event(diagnostic="EU4", readable=True,
                       diagnostic_complete=True)
        # ASCII bytes are valid for both configured codecs; this still proves
        # the projector passes the explicitly selected codec through.
        public = project_native_peace_rejection(event, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("EU4", public["diagnostic"]["text"])


if __name__ == "__main__":
    unittest.main()
