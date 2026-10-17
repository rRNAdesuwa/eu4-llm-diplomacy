from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import ObserverSession
from bridge.native_text import (
    EU4_ESCAPE_CODEC,
    InvalidNativeText,
    UnknownNativeTextCodec,
    decode_native_text,
    decode_native_text_hex,
    validate_native_text_codec,
)


R10_DIAGNOSTIC_HEX = (
    "108259109c67110e4e102a4e10fd5612b65210a56310d75310864e10116210ec4e"
    "10847612d37510df7610d06310ae8b100cff11b19010484e10116210ec4e102857"
    "10186210894e10f665101f67123153101a4f12975610305210e58b10fd56108476"
    "10f46310a952100230"
)
R10_DIAGNOSTIC_TEXT = "如果一个国家接受了我们的结盟提议，那么我们在战争时期就会得到该国的援助。"


class NativeTextTests(unittest.TestCase):
    def test_four_eu4_escape_markers(self):
        encoded = bytes.fromhex("10 2a 4e 11 0e 4e 12 b6 52 13 0e 52")
        self.assertEqual("\u4e2a\u4e00\u5bb6\u5b00", decode_native_text(encoded, EU4_ESCAPE_CODEC))

    def test_escape_and_ascii_can_be_mixed(self):
        self.assertEqual("OK个!", decode_native_text(b"OK\x10\x2a\x4e!", EU4_ESCAPE_CODEC))
        # A UTF16LE escape may legitimately contain a zero high byte.  It is
        # payload data, whereas a raw zero byte is only a terminal C string.
        self.assertEqual("A", decode_native_text(b"\x10A\x00", EU4_ESCAPE_CODEC))

    def test_primary_eu4dll_r10_fixture_decodes_without_guessing(self):
        self.assertEqual(R10_DIAGNOSTIC_TEXT, decode_native_text_hex(R10_DIAGNOSTIC_HEX, EU4_ESCAPE_CODEC))

    def test_terminal_nul_is_bounded_but_embedded_nul_is_rejected(self):
        self.assertEqual("hello", decode_native_text(b"hello\x00", EU4_ESCAPE_CODEC))
        with self.assertRaises(InvalidNativeText):
            decode_native_text(b"hello\x00world", EU4_ESCAPE_CODEC)

    def test_truncated_marker_is_rejected(self):
        for encoded in (b"\x10", b"\x10\x2a", b"abc\x13\x0e"):
            with self.subTest(encoded=encoded), self.assertRaises(InvalidNativeText):
                decode_native_text(encoded, EU4_ESCAPE_CODEC)

    def test_surrogate_and_overflow_are_rejected(self):
        with self.assertRaises(InvalidNativeText):
            decode_native_text(b"\x10\x00\xd8", EU4_ESCAPE_CODEC)
        with self.assertRaises(InvalidNativeText):
            decode_native_text(b"\x12\xff\xff", EU4_ESCAPE_CODEC)

    def test_utf8_is_strict_and_unknown_codec_never_guesses(self):
        self.assertEqual("格式化条件", decode_native_text("格式化条件".encode("utf-8")))
        with self.assertRaises(InvalidNativeText):
            decode_native_text(b"\xff", "utf8")
        with self.assertRaises(UnknownNativeTextCodec):
            decode_native_text(b"plain", "gbk")
        with self.assertRaises(UnknownNativeTextCodec):
            validate_native_text_codec("UTF8")
        with self.assertRaises(UnknownNativeTextCodec):
            decode_native_text_hex("zz", "gbk")

    def test_observer_uses_explicit_codec_and_defaults_to_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            common = {"experiment_id": "exp", "session_id": "session"}
            utf8_installation = directory / "utf8.json"
            utf8_installation.write_text(json.dumps(common), encoding="utf-8")
            utf8_session = ObserverSession(utf8_installation, directory / "eu4.exe")
            self.assertEqual("utf8", utf8_session.native_text_codec)

            escape_installation = directory / "escape.json"
            escape_installation.write_text(json.dumps({
                **common, "session_id": "escape-session", "native_text_codec": EU4_ESCAPE_CODEC,
            }), encoding="utf-8")
            escape_session = ObserverSession(escape_installation, directory / "eu4.exe")
            self.assertEqual(EU4_ESCAPE_CODEC, escape_session.native_text_codec)
            semantic = escape_session._semantic_inspection({
                "native_diagnostic_hex": R10_DIAGNOSTIC_HEX,
                "diagnostic_readable": True,
                "reason_count": 0,
            }, {
                0: {"text_readable": True, "text_hex": "102a4e", "native_value": 7},
            }, escape_session.native_text_codec)
            self.assertEqual(R10_DIAGNOSTIC_TEXT, semantic["native_diagnostic_text"])
            self.assertTrue(semantic["native_diagnostic_text_decoded"])
            item = semantic["reason_items"][0]
            self.assertEqual("个", item["name"])
            self.assertTrue(item["text_decoded"])
            self.assertFalse(item["text_encoding_verified"])
            self.assertFalse(item["complete"])
            self.assertIsNone(item["native_identifier"])

            bad_installation = directory / "bad.json"
            bad_installation.write_text(json.dumps({
                **common, "session_id": "bad-session", "native_text_codec": "gbk",
            }), encoding="utf-8")
            with self.assertRaises(UnknownNativeTextCodec):
                ObserverSession(bad_installation, directory / "eu4.exe")

    def test_hex_and_size_limits_are_strict(self):
        with self.assertRaises(InvalidNativeText):
            decode_native_text_hex("0")
        with self.assertRaises(InvalidNativeText):
            decode_native_text_hex("zz")
        with self.assertRaises(InvalidNativeText):
            decode_native_text(b"a" * 513)
        with self.assertRaises(InvalidNativeText):
            decode_native_text_hex("61" * 513)


if __name__ == "__main__":
    unittest.main()
