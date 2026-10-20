"""Validation and safe projection for native Peace rejection records.

``native_peace_execution_rejected`` is emitted before a business submission.
The record is useful evidence that a fresh native preparation failed, but it
does not claim that every native rule was evaluated.  In particular,
``failure_complete`` describes the failure reason record, while ``complete``
describes the binding of the rejection event itself.

The event carries a bounded native diagnostic as hex.  The public projection
decodes it only with the configured bridge codec and never exposes the raw
hex, session id, request id, or native addresses.  A native-rule source maps
to ``legality.status == "unavailable"``; transport/runtime and bridge-policy
failures remain ``unknown``.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Final

from .native_text import (
    DEFAULT_NATIVE_TEXT_CODEC,
    InvalidNativeText,
    decode_native_text_hex,
    validate_native_text_codec,
)


REJECTION_EVENT: Final = "native_peace_execution_rejected"
PEACE_FAMILY: Final = "peace"
PHASE: Final = "initiate"
MAX_REASON_CODE_LENGTH: Final = 127
MAX_REASON_STAGE_LENGTH: Final = 63
MAX_DIAGNOSTIC_BYTES: Final = 1024
_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1
_WAR_ID_RE: Final = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TAG_RE: Final = re.compile(r"[A-Z0-9]{3}\Z")
_REASON_CODE_RE: Final = re.compile(r"[A-Z0-9_]{1,127}\Z")
_REASON_STAGE_RE: Final = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")

_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset({
    "event", "family", "session_id", "request_id", "action_id",
    "actor", "recipient", "phase", "date_raw", "war_id", "direction",
    "submitted", "reason_code", "reason_stage", "reason_source",
    "native_diagnostic_hex", "native_diagnostic_readable",
    "native_diagnostic_truncated", "native_diagnostic_complete",
    "failure_complete", "complete",
})
_REASON_SOURCES: Final[frozenset[str]] = frozenset({
    "native_rule", "runtime_error", "bridge_policy",
})
_DIRECTIONS: Final[frozenset[str]] = frozenset({"demand", "offer"})


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_int32(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and _INT32_MIN <= value <= _INT32_MAX)


def _is_identifier(value: object, maximum: int) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        return False
    # JSON/native identifiers are single-line tokens.  Keep the character
    # policy deliberately broad so future request IDs remain compatible.
    return all(ord(char) >= 0x20 and char != "\x7f" for char in value)


def _is_hex(value: object) -> bool:
    return (isinstance(value, str)
            and len(value) % 2 == 0
            and len(value) <= MAX_DIAGNOSTIC_BYTES * 2
            and re.fullmatch(r"[0-9A-Fa-f]*", value) is not None)


def _valid_context_value(event: Mapping[str, object], field: str,
                         expected: object, maximum: int | None = None) -> bool:
    actual = event.get(field)
    if actual != expected:
        return False
    return maximum is None or _is_identifier(actual, maximum)


def validate_native_peace_rejection(
        event: object, *, request_id: str, session_id: str,
        action_id: str, actor: str, recipient: str, phase: str,
        date_raw: int, war_id: str, direction: str) -> bool:
    """Strictly validate and bind one native rejection event.

    Extra event members are accepted for forward compatibility.  The event's
    two completeness flags are independent of the native rule verdict:
    ``failure_complete`` is the reason-record completeness and ``complete``
    is the outer binding completeness.  A partial but well-shaped record is
    therefore valid and projects with ``binding_complete=False``.
    """

    if not isinstance(event, Mapping) or not _REQUIRED_FIELDS.issubset(event):
        return False
    if (event.get("event") != REJECTION_EVENT
            or event.get("family") != PEACE_FAMILY
            or event.get("phase") != PHASE
            or phase != PHASE
            or not isinstance(direction, str)
            or direction not in _DIRECTIONS
            or event.get("direction") != direction
            or event.get("submitted") is not False):
        return False

    if (not _is_identifier(request_id, 127)
            or not _is_identifier(session_id, 127)
            or not _is_identifier(action_id, 127)
            or not _is_identifier(actor, 3)
            or not _is_identifier(recipient, 3)
            or actor != event.get("actor")
            or recipient != event.get("recipient")
            or actor == recipient
            or not _TAG_RE.fullmatch(actor)
            or not _TAG_RE.fullmatch(recipient)):
        return False
    if (not _valid_context_value(event, "request_id", request_id, 127)
            or not _valid_context_value(event, "session_id", session_id, 127)
            or not _valid_context_value(event, "action_id", action_id, 127)):
        return False
    if (not _is_int32(date_raw) or event.get("date_raw") != date_raw
            or not _is_int32(event.get("date_raw"))):
        return False
    if (not isinstance(war_id, str)
            or _WAR_ID_RE.fullmatch(war_id) is None
            or event.get("war_id") != war_id):
        return False

    reason_code = event.get("reason_code")
    reason_stage = event.get("reason_stage")
    reason_source = event.get("reason_source")
    if (not isinstance(reason_code, str)
            or len(reason_code) > MAX_REASON_CODE_LENGTH
            or _REASON_CODE_RE.fullmatch(reason_code) is None
            or not isinstance(reason_stage, str)
            or len(reason_stage) > MAX_REASON_STAGE_LENGTH
            or _REASON_STAGE_RE.fullmatch(reason_stage) is None
            or not isinstance(reason_source, str)
            or reason_source not in _REASON_SOURCES):
        return False
    for field in (
            "native_diagnostic_readable", "native_diagnostic_truncated",
            "native_diagnostic_complete", "failure_complete", "complete"):
        if not _is_bool(event.get(field)):
            return False
    # Native emits these two outer flags together.  Mismatching them would
    # make the public binding claim ambiguous, so reject that shape.
    if event.get("complete") is not event.get("failure_complete"):
        return False
    return _is_hex(event.get("native_diagnostic_hex"))


def valid_native_peace_rejection(
        event: object, *, request_id: str, session_id: str,
        action_id: str, actor: str, recipient: str, phase: str,
        date_raw: int, war_id: str, direction: str) -> bool:
    """Compatibility spelling for callers using ``valid_*`` helpers."""

    return validate_native_peace_rejection(
        event,
        request_id=request_id,
        session_id=session_id,
        action_id=action_id,
        actor=actor,
        recipient=recipient,
        phase=phase,
        date_raw=date_raw,
        war_id=war_id,
        direction=direction,
    )


_STAGE_TEXT: Final[dict[str, str]] = {
    "diplomat_availability": "空闲外交官检查",
    "game_context": "游戏上下文",
    "war_context": "战争上下文",
    "offer_constructor": "议和提议构造",
    "offer_participants": "议和参与方",
    "money_selection": "金钱条款选择",
    "province_selection": "省份条款选择",
    "reparations_selection": "赔款条款选择",
    "trade_power_selection": "贸易权条款选择",
    "concede_defeat_selection": "承认战败条款选择",
    "annul_selection": "废除条约条款选择",
    "special_selection": "特殊条款选择",
    "subject_selection": "附庸条款选择",
    "country_selection": "国家条款选择",
    "annex_selection": "吞并条款选择",
    "selected_rules": "已选条款规则检查",
    "action_copy": "提议复制检查",
    "action_war_context": "提议战争上下文检查",
    "native_abi": "原生接口检查",
    "request_storage": "请求存储检查",
    "offer_snapshot": "提议快照检查",
    "lifecycle": "议和生命周期检查",
}
_SOURCE_TEXT: Final[dict[str, str]] = {
    "native_rule": "原生规则",
    "runtime_error": "运行时",
    "bridge_policy": "桥接策略",
}


def _fallback_reason_text(event: Mapping[str, object]) -> str:
    if event["reason_code"] == "NATIVE_DIPLOMAT_UNAVAILABLE":
        return "此议和操作需要空闲外交官，但执行前复检时可用外交官数量为0。"
    if event["reason_code"] == "NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE":
        return "执行前无法读取外交官状态，不能确认是否有空闲外交官可供议和。"
    source = _SOURCE_TEXT.get(str(event["reason_source"]), "原生")
    stage = _STAGE_TEXT.get(str(event["reason_stage"]),
                             str(event["reason_stage"]))
    action = str(event["action_id"])
    actor = str(event["actor"])
    recipient = str(event["recipient"])
    direction = str(event["direction"])
    if event["reason_source"] == "runtime_error":
        verb = "未能提交"
    else:
        verb = "拒绝了"
    return (f"{source}在{stage}阶段{verb}{actor}向{recipient}提交的"
            f"{action}议和请求（{direction}方向）。")


def _project_diagnostic(event: Mapping[str, object], codec: str) -> dict:
    readable = event["native_diagnostic_readable"] is True
    truncated = event["native_diagnostic_truncated"] is True
    text: str | None = None
    if readable and not truncated:
        try:
            text = decode_native_text_hex(
                event["native_diagnostic_hex"], codec,
                max_bytes=MAX_DIAGNOSTIC_BYTES)
        except InvalidNativeText:
            text = None
    return {
        "text": text,
        "text_decoded": text is not None,
        "readable": readable,
        "truncated": truncated,
        "complete": (
            event["native_diagnostic_complete"] is True
            and text is not None
        ),
    }


def project_native_peace_rejection(
        event: object,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict | None:
    """Project a structurally valid rejection into safe public fields."""

    if not isinstance(event, Mapping):
        return None
    # Projection has no expected request context; validate the intrinsic
    # record through the same strict shape checks with its own binding values.
    if not validate_native_peace_rejection(
            event,
            request_id=event.get("request_id"),
            session_id=event.get("session_id"),
            action_id=event.get("action_id"),
            actor=event.get("actor"),
            recipient=event.get("recipient"),
            phase=event.get("phase"),
            date_raw=event.get("date_raw"),
            war_id=event.get("war_id"),
            direction=event.get("direction")):
        return None
    selected_codec = validate_native_text_codec(codec)
    diagnostic = _project_diagnostic(event, selected_codec)
    native_text = diagnostic["text"]
    reason_text = (native_text if isinstance(native_text, str) and native_text
                   else _fallback_reason_text(event))
    source = event["reason_source"]
    return {
        "reason": {
            "code": event["reason_code"],
            "text": reason_text,
            "source": source,
            "stage": event["reason_stage"],
            "complete": False,
        },
        "diagnostic": diagnostic,
        "legality": {
            "status": "unavailable" if source == "native_rule" else "unknown",
            "complete": False,
        },
        "reason_code": event["reason_code"],
        "submitted": False,
        "binding_complete": event["complete"],
    }


__all__ = [
    "MAX_DIAGNOSTIC_BYTES",
    "MAX_REASON_CODE_LENGTH",
    "MAX_REASON_STAGE_LENGTH",
    "PEACE_FAMILY",
    "PHASE",
    "REJECTION_EVENT",
    "project_native_peace_rejection",
    "validate_native_peace_rejection",
    "valid_native_peace_rejection",
]
