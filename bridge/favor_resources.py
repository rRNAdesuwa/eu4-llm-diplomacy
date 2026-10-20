"""Strict public contracts for native favors-for-trust and favors-for-men.

The native query reports the resource units used by the action.  Trust is the
recipient's trust in the actor; men are the two country manpower balances.  A
result is independently checked from before/after values when the native
settlement is complete and marked verified.  The marker itself never proves a
settlement.
"""
from __future__ import annotations

from typing import Any


TRUST_ACTION_ID = "trade_favors_for_trust"
MEN_ACTION_ID = "trade_favors_for_men"
ACTION_IDS = frozenset((TRUST_ACTION_ID, MEN_ACTION_ID))
TRUST_QUERY_CAPABILITY = "native_favor_trust_query"
TRUST_SUBMISSION_CAPABILITY = "native_favor_trust_submission"
TRUST_RESPONSE_CAPABILITY = "native_inbound_favor_trust_response"
MEN_QUERY_CAPABILITY = "native_favor_men_query"
MEN_SUBMISSION_CAPABILITY = "native_favor_men_submission"
MEN_RESPONSE_CAPABILITY = "native_inbound_favor_men_response"
KINDS = frozenset(("trust", "men"))
NATIVE_REJECT = 1
NATIVE_ACCEPT = 2
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
RESOURCE_SCALE = 1
FAVOR_SCALE = 1000

_QUERY_COMMON_KEYS = frozenset({
    "kind", "amount_raw", "amount_readable", "favor_cost_raw",
    "favors_available_raw", "resource_scale", "complete",
})
_QUERY_KEYS = {
    "trust": _QUERY_COMMON_KEYS | {"recipient_trust_raw"},
    "men": _QUERY_COMMON_KEYS | {
        "actor_manpower_raw", "recipient_manpower_raw",
    },
}
_STATE_KEYS = {
    "trust": frozenset({
        "complete", "recipient_trust_raw", "favors_raw", "cost_raw",
    }),
    "men": frozenset({
        "complete", "actor_manpower_raw", "recipient_manpower_raw",
        "favors_raw", "cost_raw",
    }),
}
_RESULT_KEYS = frozenset({
    "kind", "before", "after", "amount_raw", "complete", "verified",
})

__all__ = [
    "ACTION_IDS", "FAVOR_SCALE", "INT32_MAX", "INT32_MIN", "KINDS",
    "MEN_ACTION_ID", "MEN_QUERY_CAPABILITY", "MEN_RESPONSE_CAPABILITY",
    "MEN_SUBMISSION_CAPABILITY", "NATIVE_ACCEPT", "NATIVE_REJECT",
    "RESOURCE_SCALE", "TRUST_ACTION_ID", "TRUST_QUERY_CAPABILITY",
    "TRUST_RESPONSE_CAPABILITY", "TRUST_SUBMISSION_CAPABILITY",
    "project_query", "project_result", "validate_query", "validate_result",
]


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_int32(value: object) -> bool:
    # ``bool`` is an ``int`` subclass; the exact type check is intentional.
    return type(value) is int and INT32_MIN <= value <= INT32_MAX


def _is_nonnegative_int32(value: object) -> bool:
    return _is_int32(value) and value >= 0


def _checked_add(left: int, right: int) -> int | None:
    value = left + right
    return value if INT32_MIN <= value <= INT32_MAX else None


def _checked_sub(left: int, right: int) -> int | None:
    value = left - right
    return value if INT32_MIN <= value <= INT32_MAX else None


def _public_value(raw: int, scale: int = RESOURCE_SCALE) -> float:
    return raw / scale


def _valid_query_shape(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    kind = value.get("kind")
    if type(kind) is not str or kind not in KINDS or set(value) != _QUERY_KEYS[kind]:
        return False
    if type(value["resource_scale"]) is not int or value["resource_scale"] != RESOURCE_SCALE:
        return False
    if not _is_bool(value["amount_readable"]) or not _is_bool(value["complete"]):
        return False
    for key in ("amount_raw", "favor_cost_raw", "favors_available_raw"):
        if not _is_int32(value[key]):
            return False
    if kind == "trust":
        return _is_int32(value["recipient_trust_raw"])
    return (_is_nonnegative_int32(value["actor_manpower_raw"])
            and _is_nonnegative_int32(value["recipient_manpower_raw"]))


def validate_query(value: object) -> bool:
    """Validate one native trust/men query without trusting native flags."""
    if not _valid_query_shape(value):
        return False
    assert isinstance(value, dict)
    kind = value["kind"]
    if kind == "trust" and not 0 <= value["recipient_trust_raw"] <= 100:
        return False
    # Native queries may be incomplete, but a complete query must expose a
    # readable, nonnegative amount and cost.  Favors themselves can be a
    # signed relation value and are therefore only bounded by int32 here.
    if value["complete"]:
        return (value["amount_readable"] is True
                and value["amount_raw"] >= 0
                and value["favor_cost_raw"] >= 0)
    return True


def _valid_state(value: object, kind: str) -> bool:
    if not isinstance(value, dict) or set(value) != _STATE_KEYS[kind]:
        return False
    if type(value["complete"]) is not bool:
        return False
    if not _is_int32(value["favors_raw"]) or not _is_int32(value["cost_raw"]):
        return False
    if value["cost_raw"] < 0:
        return False
    if kind == "trust":
        return (_is_int32(value["recipient_trust_raw"])
                and 0 <= value["recipient_trust_raw"] <= 100)
    return (_is_nonnegative_int32(value["actor_manpower_raw"])
            and _is_nonnegative_int32(value["recipient_manpower_raw"]))


def _valid_result_shape(value: object, native_state: object) -> bool:
    if (not isinstance(value, dict) or set(value) != _RESULT_KEYS
            or type(value.get("kind")) is not str
            or value.get("kind") not in KINDS
            or type(native_state) is not int
            or native_state not in (NATIVE_REJECT, NATIVE_ACCEPT)
            or not _is_int32(value["amount_raw"])
            or not _is_bool(value["complete"])
            or not _is_bool(value["verified"])):
        return False
    kind = value["kind"]
    if not _valid_state(value["before"], kind) or not _valid_state(value["after"], kind):
        return False
    if value["complete"] and (value["amount_raw"] < 0
                               or not value["before"]["complete"]
                               or not value["after"]["complete"]):
        return False
    # A native verified flag cannot certify an incomplete state.
    if value["verified"] and not value["complete"]:
        return False
    return True


def _validate_settlement(value: dict[str, Any], native_state: int) -> bool:
    if not (value["complete"] and value["verified"]
            and value["before"]["complete"] and value["after"]["complete"]):
        return True
    before = value["before"]
    after = value["after"]
    amount = value["amount_raw"]
    cost = before["cost_raw"]
    if after["cost_raw"] != cost:
        return False
    if native_state == NATIVE_REJECT:
        # A rejected request cannot consume either the resource or the owed
        # favors.  amount_raw may still be a preview amount.
        return all(after[key] == before[key] for key in before)
    if amount < 0:
        return False
    if before["favors_raw"] < cost:
        return False
    favors_after = _checked_sub(before["favors_raw"], cost)
    if favors_after is None or after["favors_raw"] != favors_after:
        return False
    if value["kind"] == "trust":
        if before["recipient_trust_raw"] >= 100:
            return False
        expected_trust = min(100, before["recipient_trust_raw"] + amount)
        return after["recipient_trust_raw"] == expected_trust
    if before["recipient_manpower_raw"] < amount:
        return False
    expected_actor = _checked_add(before["actor_manpower_raw"], amount)
    expected_recipient = _checked_sub(before["recipient_manpower_raw"], amount)
    return (expected_actor is not None and expected_recipient is not None
            and after["actor_manpower_raw"] == expected_actor
            and after["recipient_manpower_raw"] == expected_recipient)


def validate_result(value: object, native_state: object) -> bool:
    """Validate one result, recomputing the settlement independently.

    Unverified/incomplete results are structurally checked and return true so
    callers can preserve an ``unknown`` observation.  A result marked
    verified is accepted only when its arithmetic matches the native contract.
    """
    if not _valid_result_shape(value, native_state):
        return False
    assert isinstance(value, dict)
    if not value["verified"]:
        return True
    assert type(native_state) is int
    return _validate_settlement(value, native_state)


def _project_favors(before: dict[str, Any], after: dict[str, Any], actor: str,
                    recipient: str, complete: bool, settled: bool,
                    accepted: bool) -> dict[str, Any]:
    spent = None
    if settled:
        spent = before["favors_raw"] - after["favors_raw"] if accepted else 0
    return {
        "held_by": actor,
        "owed_by": recipient,
        "available": complete,
        "before_raw": before["favors_raw"] if complete else None,
        "after_raw": after["favors_raw"] if complete else None,
        "spent_raw": spent,
        "cost_raw": before["cost_raw"] if complete else None,
        "unit": "favors",
        "scale": FAVOR_SCALE,
    }


def project_query(value: object, actor: str, recipient: str) -> dict[str, Any] | None:
    """Project a verified-shape native query to public resource fields."""
    if not validate_query(value):
        return None
    assert isinstance(value, dict)
    kind = value["kind"]
    amount_unit = "trust" if kind == "trust" else "men"
    result: dict[str, Any] = {
        "kind": kind,
        "source": "native_rule",
        "complete": value["complete"],
        "amount": {
            "available": value["amount_readable"],
            "raw": value["amount_raw"],
            "value": _public_value(value["amount_raw"]),
            "unit": amount_unit,
            "scale": RESOURCE_SCALE,
        },
        "favors": {
            "available": value["complete"],
            "held_by": actor,
            "owed_by": recipient,
            "current_raw": value["favors_available_raw"],
            "current": _public_value(value["favors_available_raw"], FAVOR_SCALE),
            "cost_raw": value["favor_cost_raw"],
            "cost": _public_value(value["favor_cost_raw"], FAVOR_SCALE),
            "unit": "favors",
            "scale": FAVOR_SCALE,
        },
    }
    if kind == "trust":
        result["amount"].update({
            "trustor": recipient,
            "trusted": actor,
            "direction": "recipient_to_actor",
        })
        result["trust"] = {
            "raw": value["recipient_trust_raw"],
            "value": value["recipient_trust_raw"],
            "unit": "trust",
            "scale": RESOURCE_SCALE,
            "trustor": recipient,
            "trusted": actor,
            "direction": "recipient_to_actor",
        }
    else:
        result["amount"].update({"payer": recipient, "receiver": actor})
        result["manpower"] = {
            "actor": actor,
            "recipient": recipient,
            "actor_raw": value["actor_manpower_raw"],
            "recipient_raw": value["recipient_manpower_raw"],
            "unit": "men",
            "scale": RESOURCE_SCALE,
        }
    return result


def project_result(
        value: dict[str, Any], actor: str, recipient: str, native_state: int,
        controlled_country: str | None = "FRA") -> dict[str, Any] | None:
    """Project a result while exposing changes only after independent proof."""
    if not validate_result(value, native_state):
        return None
    kind = value["kind"]
    before = value["before"]
    after = value["after"]
    settled = (value["complete"] and value["verified"]
               and before["complete"] and after["complete"])
    accepted = settled and native_state == NATIVE_ACCEPT
    rejected = settled and native_state == NATIVE_REJECT
    complete = value["complete"] and before["complete"] and after["complete"]
    result: dict[str, Any] = {
        "kind": kind,
        "complete": value["complete"],
        "verified": settled,
        "native_state": native_state,
        "native_outcome": "accepted" if accepted else "rejected" if rejected else "unknown",
        "amount": {
            "available": value["complete"],
            "raw": value["amount_raw"],
            "value": _public_value(value["amount_raw"]),
            "unit": "trust" if kind == "trust" else "men",
            "scale": RESOURCE_SCALE,
        },
        "favors": _project_favors(before, after, actor, recipient, complete,
                                   settled, accepted),
    }
    if kind == "trust":
        result["amount"].update({
            "trustor": recipient,
            "trusted": actor,
            "direction": "recipient_to_actor",
        })
        change = after["recipient_trust_raw"] - before["recipient_trust_raw"] if settled else None
        result["trust"] = {
            "trustor": recipient,
            "trusted": actor,
            "direction": "recipient_to_actor",
            "before_raw": before["recipient_trust_raw"] if complete else None,
            "after_raw": after["recipient_trust_raw"] if complete else None,
            "change_raw": change,
            "unit": "trust",
            "scale": RESOURCE_SCALE,
        }
    else:
        result["amount"].update({"payer": recipient, "receiver": actor})
        actor_change = (after["actor_manpower_raw"]
                        - before["actor_manpower_raw"] if settled else None)
        recipient_change = (after["recipient_manpower_raw"]
                            - before["recipient_manpower_raw"] if settled else None)
        result["manpower"] = {
            "actor": actor,
            "recipient": recipient,
            "actor_before_raw": before["actor_manpower_raw"] if complete else None,
            "actor_after_raw": after["actor_manpower_raw"] if complete else None,
            "actor_change_raw": actor_change,
            "recipient_before_raw": before["recipient_manpower_raw"] if complete else None,
            "recipient_after_raw": after["recipient_manpower_raw"] if complete else None,
            "recipient_change_raw": recipient_change,
            "unit": "men",
            "scale": RESOURCE_SCALE,
        }
    if controlled_country is not None:
        result["controlled_country"] = controlled_country
    return result
