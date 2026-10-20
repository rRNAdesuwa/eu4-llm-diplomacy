"""Validation and legality projection for native diplomat availability.

The native observer may optionally report the three legacy flat diplomat
context fields.  This module keeps that observation separate from action
execution: a verified count of zero can explain why an initiating action is
unavailable, while a positive count never proves that a particular diplomat
has been allocated to the action.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_CONTEXT_FIELDS = (
    "diplomat_context_readable",
    "diplomat_required",
    "available_diplomat_count",
)
_MAX_AVAILABLE_DIPLOMATS = 256

NATIVE_DIPLOMAT_UNAVAILABLE = "NATIVE_DIPLOMAT_UNAVAILABLE"
NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE = "NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE"


def _is_bool(value: object) -> bool:
    """Return whether *value* is a real JSON boolean, excluding integers."""

    return type(value) is bool


def _is_available_count(value: object) -> bool:
    """Return whether *value* is a bounded native diplomat count."""

    return (type(value) is int
            and 0 <= value <= _MAX_AVAILABLE_DIPLOMATS)


def _has_context_fields(event: Mapping[str, Any]) -> bool:
    return any(field in event for field in _CONTEXT_FIELDS)


def validate_native_diplomat_context(event: object) -> bool:
    """Validate the optional legacy-flat native diplomat context.

    A producer may omit the entire context for backwards compatibility.  Once
    any of the three fields is emitted, all three fields must be present and
    correctly typed.  An unreadable context may explicitly carry ``None`` for
    its count; a readable context must carry a bounded integer count.
    """

    if not isinstance(event, Mapping):
        return False
    if not _has_context_fields(event):
        return True
    if not all(field in event for field in _CONTEXT_FIELDS):
        return False

    readable = event.get("diplomat_context_readable")
    required = event.get("diplomat_required")
    count = event.get("available_diplomat_count")
    if not _is_bool(readable) or not _is_bool(required):
        return False
    if readable is False and count is None:
        return True
    return _is_available_count(count)


def project_native_diplomat_context(event: object) -> dict[str, Any] | None:
    """Project a valid native context into the public diplomat resource.

    No context is represented as ``None`` for legacy events.  A present but
    malformed context is an explicit producer error and raises ``ValueError``
    rather than being guessed into a usable resource.
    """

    if (isinstance(event, Mapping)
            and not _has_context_fields(event)):
        return None
    if not validate_native_diplomat_context(event):
        raise ValueError("INVALID_NATIVE_DIPLOMAT_CONTEXT")

    # ``validate_native_diplomat_context`` has established that this is a
    # mapping with all three fields present.  Keep the explicit checks here so
    # type checkers and future callers cannot turn an unreadable context into
    # a claimed count.
    assert isinstance(event, Mapping)
    readable = event["diplomat_context_readable"]
    count = event["available_diplomat_count"]
    return {
        "native_requirement": event["diplomat_required"],
        "available_count": count if readable is True else None,
        "availability_verified": readable,
        "allocation_verified": False,
        "source": "native_rule",
        "complete": readable,
    }


def _reason(code: str, text: str, source: str,
            complete: bool = False) -> dict[str, Any]:
    return {"code": code, "text": text, "source": source,
            "complete": complete}


def _append_reason(legality: dict[str, Any], item: dict[str, Any]) -> None:
    """Append one reason unless the same code is already present."""

    reasons = legality.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
        legality["reasons"] = reasons
    code = item["code"]
    if any(isinstance(existing, Mapping) and existing.get("code") == code
           for existing in reasons):
        return
    reasons.append(item)


def apply_diplomat_legality(inspection: dict[str, Any]) -> dict[str, Any]:
    """Apply the verified diplomat gate to an in-memory inspection.

    Only initiation inspections with a public ``resources.diplomats`` record
    are considered.  The function mutates and returns ``inspection`` so it can
    be inserted into existing inspection pipelines without changing ownership
    or authorization semantics.
    """

    if not isinstance(inspection, dict) or inspection.get("phase") != "initiate":
        return inspection

    resources = inspection.get("resources")
    if not isinstance(resources, Mapping) or "diplomats" not in resources:
        return inspection
    diplomats = resources.get("diplomats")
    if not isinstance(diplomats, Mapping):
        return inspection

    # A non-required action must retain its existing legality regardless of
    # whether the optional native context is readable or reports zero.
    if diplomats.get("native_requirement") is not True:
        return inspection

    availability_verified = diplomats.get("availability_verified") is True
    count = diplomats.get("available_count")
    count_verified = _is_available_count(count)

    legality = inspection.get("legality")
    if not isinstance(legality, dict):
        legality = {"status": "unknown", "reasons": []}
        inspection["legality"] = legality

    if availability_verified and count_verified and count == 0:
        _append_reason(
            legality,
            _reason(
                NATIVE_DIPLOMAT_UNAVAILABLE,
                "此动作需要空闲外交官，但当前可用外交官数量为0。",
                "native_rule",
                True,
            ),
        )
        legality["status"] = "unavailable"
        return inspection

    if not availability_verified or not count_verified:
        legality["complete"] = False
        _append_reason(
            legality,
            _reason(
                NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE,
                "原生外交官上下文不可读，无法确认此动作需要的空闲外交官数量。",
                "runtime_error",
                False,
            ),
        )
        # A previous concrete prohibition remains authoritative.  Otherwise
        # the unreadable resource can only leave legality unknown.
        if legality.get("status") != "unavailable":
            legality["status"] = "unknown"

    return inspection


__all__ = [
    "NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE",
    "NATIVE_DIPLOMAT_UNAVAILABLE",
    "apply_diplomat_legality",
    "project_native_diplomat_context",
    "validate_native_diplomat_context",
]
