from __future__ import annotations

import copy
import unittest

from bridge.declarewar_details import (
    FIELD_MAX_BYTES,
    project_declare_war_details,
    valid_declare_war_details,
)
from bridge.native_text import (
    EU4_ESCAPE_CODEC,
    InvalidNativeText,
    UnknownNativeTextCodec,
    decode_native_text_hex,
)


class DeclareWarDetailsTests(unittest.TestCase):
    @staticmethod
    def _record(text: str, *, applicable: bool = True,
               called: bool = True, return_verified: bool = True,
               readable: bool = True, truncated: bool = False) -> dict:
        return {
            "applicable": applicable,
            "called": called,
            "return_verified": return_verified,
            "text_hex": text.encode("utf-8").hex() if applicable else "",
            "readable": readable,
            "truncated": truncated,
        }

    @classmethod
    def _details(cls, *, no_cb: bool = False) -> dict:
        return {
            "called": True,
            "action_unchanged": True,
            "complete": True,
            "casus_belli_name": cls._record("cb_core"),
            "casus_belli_description": cls._record("Core claim"),
            "war_goal_name": cls._record(
                "Conquest", applicable=not no_cb,
                called=not no_cb, return_verified=not no_cb,
                readable=not no_cb),
            "war_goal_description": cls._record(
                "Conquer the target", applicable=not no_cb,
                called=not no_cb, return_verified=not no_cb,
                readable=not no_cb),
            "disabled_peace_terms_description": cls._record("Disabled terms"),
            "declaration_description": cls._record("Declare war"),
        }

    def test_complete_details_project_with_explicit_codec(self):
        raw = self._details()
        self.assertTrue(valid_declare_war_details(raw))
        public = project_declare_war_details(raw)
        self.assertEqual({
            "source": "native_declare_war_dialog",
            "complete": True,
            "casus_belli": {
                "name": "cb_core",
                "description": "Core claim",
                "complete": True,
            },
            "war_goal": {
                "applicable": True,
                "name": "Conquest",
                "description": "Conquer the target",
                "complete": True,
            },
            "peace_conditions": {
                "disabled_terms_description": "Disabled terms",
                "complete": True,
            },
            "description": "Declare war",
            "description_complete": True,
        }, public)

    def test_no_cb_goal_uses_only_the_explicit_inapplicable_sentinel(self):
        raw = self._details(no_cb=True)
        self.assertTrue(valid_declare_war_details(raw))
        public = project_declare_war_details(raw, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertTrue(public["complete"])
        self.assertEqual({
            "applicable": False, "name": None, "description": None,
            "complete": True,
        }, public["war_goal"])

        malformed = copy.deepcopy(raw)
        malformed["war_goal_description"]["applicable"] = True
        malformed["war_goal_description"]["text_hex"] = "goal".encode().hex()
        self.assertFalse(valid_declare_war_details(malformed))
        self.assertIsNone(project_declare_war_details(malformed))

    def test_complete_is_the_native_applicable_record_conjunction(self):
        raw = self._details()
        raw["declaration_description"]["truncated"] = True
        raw["complete"] = False
        self.assertTrue(valid_declare_war_details(raw))
        public = project_declare_war_details(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertFalse(public["complete"])
        self.assertIsNone(public["description"])
        self.assertFalse(public["description_complete"])

        mismatch = self._details()
        mismatch["complete"] = False
        self.assertFalse(valid_declare_war_details(mismatch))
        self.assertIsNone(project_declare_war_details(mismatch))

    def test_corrupt_text_is_safe_but_keeps_structural_validation(self):
        raw = self._details()
        raw["casus_belli_name"]["text_hex"] = "ff"
        self.assertTrue(valid_declare_war_details(raw))
        public = project_declare_war_details(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertIsNone(public["casus_belli"]["name"])
        self.assertFalse(public["casus_belli"]["complete"])
        self.assertFalse(public["complete"])

    def test_each_native_field_bound_and_optional_decoder_limit_is_bounded(self):
        self.assertEqual({
            "casus_belli_name": 512,
            "casus_belli_description": 2048,
            "war_goal_name": 512,
            "war_goal_description": 2048,
            "disabled_peace_terms_description": 4096,
            "declaration_description": 8192,
        }, FIELD_MAX_BYTES)
        raw = self._details()
        raw["casus_belli_name"]["text_hex"] = (b"a" * 512).hex()
        raw["declaration_description"]["text_hex"] = (b"d" * 8192).hex()
        self.assertTrue(valid_declare_war_details(raw))
        self.assertEqual("a" * 512,
                         decode_native_text_hex("61" * 512))
        self.assertEqual("d" * 8192,
                         decode_native_text_hex("64" * 8192, max_bytes=8192))
        with self.assertRaises(InvalidNativeText):
            decode_native_text_hex("61" * 513)
        with self.assertRaises(InvalidNativeText):
            decode_native_text_hex("64" * 8192, max_bytes=8193)

        too_long = copy.deepcopy(self._details())
        too_long["casus_belli_name"]["text_hex"] = (b"a" * 513).hex()
        self.assertFalse(valid_declare_war_details(too_long))
        self.assertIsNone(project_declare_war_details(too_long))

    def test_shape_and_codec_failures_are_not_guessed(self):
        raw = self._details()
        raw["extra"] = True
        self.assertFalse(valid_declare_war_details(raw))
        self.assertIsNone(project_declare_war_details(raw))
        with self.assertRaises(UnknownNativeTextCodec):
            project_declare_war_details(self._details(), "gbk")


if __name__ == "__main__":
    unittest.main()
