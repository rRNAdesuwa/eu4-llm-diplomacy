"""Bounded decoding for text returned by the native diplomacy observer.

The observer records text as hex so the operator log stays JSON-safe.  The
codec is an operator/configuration decision: an unknown value is an error and
is never guessed from the bytes.  ``eu4_escape`` follows the public EU4dll
escape_tool implementation (markers 0x10..0x13).
"""
from __future__ import annotations

import re
from typing import Final


DEFAULT_NATIVE_TEXT_CODEC: Final[str] = "utf8"
EU4_ESCAPE_CODEC: Final[str] = "eu4_escape"
MAX_NATIVE_TEXT_BYTES: Final[int] = 512
_ESCAPE_MARKERS = frozenset((0x10, 0x11, 0x12, 0x13))


class NativeTextError(ValueError):
    """Base class for configured-codec and text-shape failures."""


class UnknownNativeTextCodec(NativeTextError):
    """The operator supplied a codec that this bridge does not implement."""


class InvalidNativeText(NativeTextError):
    """The bytes are truncated, malformed, out of bounds, or contain NULs."""


def validate_native_text_codec(codec: object) -> str:
    """Validate and return the exact configured codec name.

    Only the two explicit operator values are accepted.  In particular,
    spelling/case variants are not silently mapped to a different codec.
    """

    if codec == DEFAULT_NATIVE_TEXT_CODEC or codec == EU4_ESCAPE_CODEC:
        return codec
    raise UnknownNativeTextCodec(f"unsupported native text codec: {codec!r}")


def _strip_nul_terminator(data: bytes) -> bytes:
    """Accept only a terminal NUL run; reject embedded/trailing garbage."""

    try:
        index = data.index(0)
    except ValueError:
        return data
    if any(data[index:]):
        raise InvalidNativeText("NUL is only allowed as the final terminator")
    return data[:index]


def _validate_codepoint(codepoint: int) -> str:
    # EU4dll's converter is UCS2 based.  Do not manufacture a surrogate or an
    # astral character from malformed marker bytes.
    if codepoint < 0 or codepoint > 0xFFFF:
        raise InvalidNativeText("escaped code point overflows UCS2")
    if 0xD800 <= codepoint <= 0xDFFF:
        raise InvalidNativeText("escaped code point is a surrogate")
    if codepoint == 0:
        raise InvalidNativeText("NUL is not a text character")
    return chr(codepoint)


def _decode_eu4_escape(data: bytes) -> str:
    result: list[str] = []
    index = 0
    while index < len(data):
        marker = data[index]
        if marker == 0:
            if any(data[index:]):
                raise InvalidNativeText("NUL is only allowed as the final terminator")
            break
        if marker in _ESCAPE_MARKERS:
            if index + 3 > len(data):
                raise InvalidNativeText("truncated EU4 escape marker")
            low = data[index + 1]
            high = data[index + 2]
            codepoint = (high << 8) | low
            if marker == 0x11:
                codepoint -= 0x0E
            elif marker == 0x12:
                codepoint += 0x900
            elif marker == 0x13:
                codepoint += 0x8F2
            result.append(_validate_codepoint(codepoint))
            index += 3
            continue
        if marker < 0x80:
            result.append(chr(marker))
        else:
            # Non-marker bytes are copied by EU4dll's helper.  The supported
            # observer fixtures use ordinary ASCII here; preserve the native
            # byte value instead of guessing a second character encoding.
            result.append(chr(marker))
        index += 1
    return "".join(result)


def _validate_max_bytes(max_bytes: object, upper_bound: int = 8192) -> int:
    if (isinstance(upper_bound, bool) or not isinstance(upper_bound, int)
            or not 1 <= upper_bound <= 16384):
        raise InvalidNativeText("invalid native text upper bound")
    if (isinstance(max_bytes, bool) or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= upper_bound):
        raise InvalidNativeText(
            f"native text max_bytes must be an integer in the range 1..{upper_bound}")
    return max_bytes


def decode_native_text(
        data: bytes | bytearray | memoryview,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC,
        max_bytes: int = MAX_NATIVE_TEXT_BYTES,
        *, max_bytes_limit: int = 8192) -> str:
    """Decode bounded native bytes using the explicitly selected codec.

    A terminal NUL is treated as a C-style terminator only when the remainder
    is entirely NUL bytes.  Embedded NULs, malformed UTF-8, incomplete escape
    triples, surrogate code points, and UCS2 overflow all raise
    :class:`InvalidNativeText`.  The historical default is 512 bytes; callers
    may raise the bound for a known native field up to ``max_bytes_limit``
    (8192 bytes by default).
    """

    selected = validate_native_text_codec(codec)
    limit = _validate_max_bytes(max_bytes, max_bytes_limit)
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise InvalidNativeText("native text must be bytes-like")
    raw = bytes(data)
    if len(raw) > limit:
        raise InvalidNativeText(f"native text exceeds {limit} bytes")
    if selected == DEFAULT_NATIVE_TEXT_CODEC:
        try:
            raw = _strip_nul_terminator(raw)
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise InvalidNativeText("invalid UTF-8 native text") from error
        if "\x00" in text:
            raise InvalidNativeText("NUL is not a text character")
        return text
    return _decode_eu4_escape(raw)


def decode_native_text_hex(
        encoded: str,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC,
        max_bytes: int = MAX_NATIVE_TEXT_BYTES,
        *, max_bytes_limit: int = 8192) -> str:
    """Decode a bounded hex payload emitted by the observer log."""

    selected = validate_native_text_codec(codec)
    limit = _validate_max_bytes(max_bytes, max_bytes_limit)
    if (not isinstance(encoded, str) or len(encoded) % 2
            or len(encoded) > limit * 2):
        raise InvalidNativeText("native text hex is malformed or too large")
    if not re.fullmatch(r"[0-9A-Fa-f]*", encoded):
        raise InvalidNativeText("native text hex is not hexadecimal")
    try:
        raw = bytes.fromhex(encoded)
    except ValueError as error:
        raise InvalidNativeText("native text hex is not hexadecimal") from error
    return decode_native_text(raw, selected, max_bytes=limit,
                              max_bytes_limit=max_bytes_limit)


__all__ = [
    "DEFAULT_NATIVE_TEXT_CODEC",
    "EU4_ESCAPE_CODEC",
    "MAX_NATIVE_TEXT_BYTES",
    "InvalidNativeText",
    "NativeTextError",
    "UnknownNativeTextCodec",
    "decode_native_text",
    "decode_native_text_hex",
    "validate_native_text_codec",
]
