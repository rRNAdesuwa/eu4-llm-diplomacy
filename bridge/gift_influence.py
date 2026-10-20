"""Strict Python contracts for the native Gift and Influence actions.

The native adapter owns the rule and cost calculation for these two actions.
This module only normalizes the public request, validates the bounded native
payload, and independently checks the settlement arithmetic.  In particular,
the influence cost is carried through from native data; Python never derives a
cost from opinion or duration.
"""
from __future__ import annotations

from typing import Any


GIFT_ACTION_ID = "send_gift"
INFLUENCE_ACTION_ID = "influence_nation"
ACTION_IDS = frozenset((GIFT_ACTION_ID, INFLUENCE_ACTION_ID))

GIFT_QUERY_CAPABILITY = "native_gift_query"
GIFT_SUBMISSION_CAPABILITY = "native_gift_submission"
INFLUENCE_QUERY_CAPABILITY = "native_influence_query"
INFLUENCE_SUBMISSION_CAPABILITY = "native_influence_submission"

GIFT_QUERY_WIRE = "EU4DIP_QUERY20"
INFLUENCE_QUERY_WIRE = "EU4DIP_QUERY21"
GIFT_SUBMISSION_WIRE = "EU4DIP_EXECUTE_GIFT"
INFLUENCE_SUBMISSION_WIRE = "EU4DIP_EXECUTE_INFLUENCE"
GIFT_EXECUTION_EVENT = "native_diplomacy_gift_execution_result"
INFLUENCE_EXECUTION_EVENT = "native_diplomacy_influence_execution_result"
SUBMISSION_EVENT = "native_alliance_submission_result"

NATIVE_REJECT = 1
# The native effect path uses state 0 while proving the immediate mutation.
# The current worker serializes a verified mutation as public state 2, so both
# values are accepted at this Python boundary and normalize to ``executed``.
NATIVE_EXECUTED = 0
NATIVE_ACCEPT = 2
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
GIFT_DUCATS_MIN = 25
GIFT_DUCATS_MAX = 2_147_475
GIFT_DUCATS_STEP = 25
GIFT_SCALE = 1000
TRUST_SCALE = 1

_GIFT_QUERY_REQUIRED = frozenset({
    "kind", "ducats", "amount_raw", "amount_readable", "resource_scale",
    "actor_treasury_raw", "recipient_treasury_raw", "complete",
})
_GIFT_QUERY_OPTIONAL = frozenset({
    "native_costs", "native_description", "native_diagnostic",
})
_INFLUENCE_QUERY_REQUIRED = frozenset({
    "kind", "opinion_raw", "duration_months", "complete",
})
_INFLUENCE_QUERY_OPTIONAL = frozenset({
    "native_costs", "costs", "cost_raw", "native_description",
    "native_diagnostic",
})
_GIFT_STATE_KEYS = frozenset({
    "complete", "actor_treasury_raw", "recipient_treasury_raw",
})
_INFLUENCE_STATE_KEYS = frozenset({
    "complete", "actor_treasury_raw", "recipient_trust_raw",
    "influencer_active",
})
_GIFT_RESULT_KEYS = frozenset({
    "kind", "before", "after", "ducats", "amount_raw", "complete", "verified",
})
_INFLUENCE_RESULT_KEYS = frozenset({
    "kind", "before", "after", "cost_raw", "opinion_raw", "duration_months",
    "complete", "verified",
})

__all__ = [
    "ACTION_IDS", "GIFT_ACTION_ID", "INFLUENCE_ACTION_ID",
    "GIFT_QUERY_CAPABILITY", "GIFT_SUBMISSION_CAPABILITY",
    "INFLUENCE_QUERY_CAPABILITY", "INFLUENCE_SUBMISSION_CAPABILITY",
    "GIFT_QUERY_WIRE", "INFLUENCE_QUERY_WIRE", "GIFT_SUBMISSION_WIRE",
    "INFLUENCE_SUBMISSION_WIRE", "GIFT_EXECUTION_EVENT",
    "INFLUENCE_EXECUTION_EVENT", "SUBMISSION_EVENT", "NATIVE_EXECUTED",
    "NATIVE_ACCEPT", "NATIVE_REJECT", "INT32_MIN", "INT32_MAX", "GIFT_DUCATS_MIN",
    "GIFT_DUCATS_MAX", "GIFT_DUCATS_STEP", "GIFT_SCALE", "TRUST_SCALE",
    "gift_amount_raw", "normalize_gift_parameters",
    "normalize_influence_parameters", "validate_gift_query",
    "validate_influence_query", "validate_query", "project_gift_query",
    "project_influence_query", "project_query", "validate_gift_result",
    "validate_influence_result", "validate_result", "project_gift_result",
    "project_influence_result", "project_result",
]


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_int32(value: object) -> bool:
    return _is_int(value) and INT32_MIN <= value <= INT32_MAX


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_tag(value: object) -> bool:
    return isinstance(value, str) and len(value) == 3 and value.isupper()


def _checked_add(left: int, right: int) -> int | None:
    value = left + right
    return value if INT32_MIN <= value <= INT32_MAX else None


def _checked_sub(left: int, right: int) -> int | None:
    value = left - right
    return value if INT32_MIN <= value <= INT32_MAX else None


def gift_amount_raw(ducats: object) -> int:
    """Return the native raw gift amount, rejecting every invalid public value."""

    if (not _is_int(ducats) or ducats < GIFT_DUCATS_MIN
            or ducats > GIFT_DUCATS_MAX or ducats % GIFT_DUCATS_STEP):
        raise ValueError("GIFT_DUCATS_INVALID")
    raw = ducats * GIFT_SCALE
    if raw > INT32_MAX:
        raise ValueError("GIFT_AMOUNT_OVERFLOW")
    return raw


def normalize_gift_parameters(parameters: object) -> dict[str, int]:
    """Normalize the only public Gift parameter: integer ducats."""

    if not isinstance(parameters, dict) or set(parameters) != {"ducats"}:
        raise ValueError("GIFT_PARAMETERS_REQUIRED")
    ducats = parameters.get("ducats")
    if type(ducats) is not int:
        raise ValueError("GIFT_DUCATS_INTEGER")
    if ducats < GIFT_DUCATS_MIN:
        raise ValueError("GIFT_DUCATS_MINIMUM")
    if ducats > GIFT_DUCATS_MAX:
        raise ValueError("GIFT_DUCATS_MAXIMUM")
    if ducats % GIFT_DUCATS_STEP:
        raise ValueError("GIFT_DUCATS_MULTIPLE_OF_25")
    amount_raw = ducats * GIFT_SCALE
    if amount_raw > INT32_MAX:
        raise ValueError("GIFT_AMOUNT_OVERFLOW")
    return {"ducats": ducats}


def normalize_influence_parameters(parameters: object) -> dict[str, Any]:
    if parameters is None:
        return {}
    if not isinstance(parameters, dict) or parameters:
        raise ValueError("INFLUENCE_PARAMETERS_UNSUPPORTED")
    return {}


def _valid_optional_keys(value: dict, required: frozenset[str], optional: frozenset[str]) -> bool:
    return required <= value.keys() and set(value) <= required | optional


def validate_gift_query(value: object) -> bool:
    if not isinstance(value, dict) or not _valid_optional_keys(
            value, _GIFT_QUERY_REQUIRED, _GIFT_QUERY_OPTIONAL):
        return False
    if value.get("kind") != "gift" or value.get("resource_scale") != GIFT_SCALE:
        return False
    if (not _is_int(value.get("ducats"))
            or not GIFT_DUCATS_MIN <= value["ducats"] <= GIFT_DUCATS_MAX
            or value["ducats"] % GIFT_DUCATS_STEP):
        return False
    if value.get("amount_raw") != value["ducats"] * GIFT_SCALE:
        return False
    if value["amount_raw"] > INT32_MAX or value["amount_raw"] < 0:
        return False
    if (not _is_bool(value["amount_readable"])
            or not _is_bool(value["complete"])
            or not _is_int32(value["actor_treasury_raw"])
            or not _is_int32(value["recipient_treasury_raw"])):
        return False
    for key in ("native_description", "native_diagnostic"):
        if key in value and value[key] is not None and not isinstance(value[key], str):
            return False
    if "native_costs" in value and value["native_costs"] is not None \
            and not isinstance(value["native_costs"], (dict, list, tuple)):
        return False
    return (not value["complete"]
            or value["amount_readable"] is True)


def validate_influence_query(value: object) -> bool:
    if not isinstance(value, dict) or not _valid_optional_keys(
            value, _INFLUENCE_QUERY_REQUIRED, _INFLUENCE_QUERY_OPTIONAL):
        return False
    if value.get("kind") != "influence":
        return False
    if (not _is_int32(value["opinion_raw"])
            or not _is_int32(value["duration_months"])
            or not _is_bool(value["complete"])):
        return False
    if "cost_raw" in value and value["cost_raw"] is not None \
            and (not _is_int32(value["cost_raw"]) or value["cost_raw"] < 0):
        return False
    for key in ("native_description", "native_diagnostic"):
        if key in value and value[key] is not None and not isinstance(value[key], str):
            return False
    for key in ("native_costs", "costs"):
        if key in value and value[key] is not None \
                and not isinstance(value[key], (dict, list, tuple)):
            return False
    return True


def validate_query(action_id: str, value: object) -> bool:
    if action_id == GIFT_ACTION_ID:
        return validate_gift_query(value)
    if action_id == INFLUENCE_ACTION_ID:
        return validate_influence_query(value)
    return False


def _copy_native_explanation(value: dict) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("native_costs", "costs", "cost_raw", "native_description",
                "native_diagnostic"):
        if key in value:
            result[key] = value[key]
    return result


def project_gift_query(value: object, actor: str, recipient: str) -> dict[str, Any] | None:
    if not validate_gift_query(value) or not _is_tag(actor) or not _is_tag(recipient):
        return None
    assert isinstance(value, dict)
    result: dict[str, Any] = {
        "kind": "gift", "source": "native_rule", "complete": value["complete"],
        "amount": {
            "ducats": value["ducats"], "raw": value["amount_raw"],
            "value": value["amount_raw"] / GIFT_SCALE, "unit": "ducats",
            "scale": GIFT_SCALE, "payer": actor, "receiver": recipient,
        },
        # The recipient balance is retained in the validator as private native
        # evidence.  The public query only exposes the controlled actor's
        # spendable treasury, matching the existing favor/gold projection.
        "controlled_treasury": {
            "country": actor, "raw": value["actor_treasury_raw"],
            "unit": "ducats", "scale": GIFT_SCALE,
        },
    }
    native = _copy_native_explanation(value)
    if native:
        result["native"] = native
    return result


def project_influence_query(value: object, actor: str, recipient: str) -> dict[str, Any] | None:
    if not validate_influence_query(value) or not _is_tag(actor) or not _is_tag(recipient):
        return None
    assert isinstance(value, dict)
    result: dict[str, Any] = {
        "kind": "influence", "source": "native_rule", "complete": value["complete"],
        "opinion": {
            "raw": value["opinion_raw"], "value": value["opinion_raw"],
            "unit": "opinion", "scale": TRUST_SCALE,
        },
        "duration": {
            "months": value["duration_months"], "unit": "months", "scale": 1,
        },
    }
    native = _copy_native_explanation(value)
    if native:
        result["native"] = native
    return result


def project_query(action_id: str, value: object,
                  actor: str, recipient: str) -> dict[str, Any] | None:
    if action_id == GIFT_ACTION_ID:
        return project_gift_query(value, actor, recipient)
    if action_id == INFLUENCE_ACTION_ID:
        return project_influence_query(value, actor, recipient)
    return None


def _valid_gift_state(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == _GIFT_STATE_KEYS
            and _is_bool(value["complete"])
            and _is_int32(value["actor_treasury_raw"])
            and _is_int32(value["recipient_treasury_raw"]))


def _valid_influence_state(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == _INFLUENCE_STATE_KEYS
            and _is_bool(value["complete"])
            and _is_int32(value["actor_treasury_raw"])
            and _is_int(value["recipient_trust_raw"])
            and 0 <= value["recipient_trust_raw"] <= 100
            and _is_bool(value["influencer_active"]))


def validate_gift_result(value: object, native_state: object) -> bool:
    if (not isinstance(value, dict) or set(value) != _GIFT_RESULT_KEYS
            or value.get("kind") != "gift"
            or native_state not in (NATIVE_EXECUTED, NATIVE_REJECT, NATIVE_ACCEPT)
            or not _is_int(value.get("ducats"))
            or not _is_int(value.get("amount_raw"))
            or not _is_bool(value.get("complete"))
            or not _is_bool(value.get("verified"))
            or not _valid_gift_state(value.get("before"))
            or not _valid_gift_state(value.get("after"))):
        return False
    if (value["ducats"] < GIFT_DUCATS_MIN
            or value["ducats"] > GIFT_DUCATS_MAX
            or value["ducats"] % GIFT_DUCATS_STEP
            or value["amount_raw"] != value["ducats"] * GIFT_SCALE
            or value["amount_raw"] > INT32_MAX
            or value["amount_raw"] < 0):
        return False
    if value["complete"] and not (value["before"]["complete"]
                                   and value["after"]["complete"]):
        return False
    if value["verified"] and not value["complete"]:
        return False
    if not value["verified"]:
        return True
    before, after = value["before"], value["after"]
    if native_state == NATIVE_REJECT:
        return before == after
    actor_after = _checked_sub(before["actor_treasury_raw"], value["amount_raw"])
    recipient_after = _checked_add(before["recipient_treasury_raw"], value["amount_raw"])
    return (actor_after is not None and recipient_after is not None
            and after["actor_treasury_raw"] == actor_after
            and after["recipient_treasury_raw"] == recipient_after)


def validate_influence_result(value: object, native_state: object) -> bool:
    if (not isinstance(value, dict) or set(value) != _INFLUENCE_RESULT_KEYS
            or value.get("kind") != "influence"
            or native_state not in (NATIVE_EXECUTED, NATIVE_REJECT, NATIVE_ACCEPT)
            or not _is_int32(value.get("cost_raw"))
            or value["cost_raw"] < 0
            or not _is_int32(value.get("opinion_raw"))
            or not _is_int32(value.get("duration_months"))
            or not _is_bool(value.get("complete"))
            or not _is_bool(value.get("verified"))
            or not _valid_influence_state(value.get("before"))
            or not _valid_influence_state(value.get("after"))):
        return False
    if value["complete"] and not (value["before"]["complete"]
                                   and value["after"]["complete"]):
        return False
    if value["verified"] and not value["complete"]:
        return False
    if not value["verified"]:
        return True
    before, after = value["before"], value["after"]
    if native_state == NATIVE_REJECT:
        return before == after
    actor_after = _checked_sub(before["actor_treasury_raw"], value["cost_raw"])
    expected_trust = min(100, before["recipient_trust_raw"] + 5)
    return (actor_after is not None
            and after["actor_treasury_raw"] == actor_after
            and after["recipient_trust_raw"] == expected_trust
            and after["influencer_active"] is True)


def validate_result(action_id: str, value: object, native_state: object) -> bool:
    if action_id == GIFT_ACTION_ID:
        return validate_gift_result(value, native_state)
    if action_id == INFLUENCE_ACTION_ID:
        return validate_influence_result(value, native_state)
    return False


def project_gift_result(value: object, actor: str, recipient: str,
                        native_state: int, controlled_country: str = "FRA") -> dict[str, Any] | None:
    if not validate_gift_result(value, native_state) or not _is_tag(actor) or not _is_tag(recipient):
        return None
    assert isinstance(value, dict)
    before, after = value["before"], value["after"]
    settled = value["complete"] and value["verified"]
    accepted = settled and native_state in (NATIVE_EXECUTED, NATIVE_ACCEPT)
    rejected = settled and native_state == NATIVE_REJECT
    result: dict[str, Any] = {
        "kind": "gift", "complete": value["complete"], "verified": settled,
        "native_state": native_state,
        "native_outcome": "executed" if accepted else "rejected" if rejected else "unknown",
        "amount": {"ducats": value["ducats"], "raw": value["amount_raw"],
                   "value": value["amount_raw"] / GIFT_SCALE, "unit": "ducats",
                   "scale": GIFT_SCALE, "payer": actor, "receiver": recipient},
        "transfer": {
            "actor": actor, "recipient": recipient,
            "actor_change_raw": (after["actor_treasury_raw"] - before["actor_treasury_raw"])
                if settled else None,
            "recipient_change_raw": (after["recipient_treasury_raw"] - before["recipient_treasury_raw"])
                if settled else None,
            "unit": "ducats", "scale": GIFT_SCALE,
        },
    }
    if controlled_country == actor:
        key = "actor_treasury_raw"
    elif controlled_country == recipient:
        key = "recipient_treasury_raw"
    else:
        key = None
    if key is not None:
        result["controlled_treasury"] = {
            "country": controlled_country, "unit": "ducats", "scale": GIFT_SCALE,
            "before_raw": before[key] if before["complete"] else None,
            "after_raw": after[key] if after["complete"] else None,
        }
    return result


def project_influence_result(value: object, actor: str, recipient: str,
                             native_state: int, controlled_country: str = "FRA") -> dict[str, Any] | None:
    if (not validate_influence_result(value, native_state)
            or not _is_tag(actor) or not _is_tag(recipient)):
        return None
    assert isinstance(value, dict)
    before, after = value["before"], value["after"]
    settled = value["complete"] and value["verified"]
    accepted = settled and native_state in (NATIVE_EXECUTED, NATIVE_ACCEPT)
    rejected = settled and native_state == NATIVE_REJECT
    result: dict[str, Any] = {
        "kind": "influence", "complete": value["complete"], "verified": settled,
        "native_state": native_state,
        "native_outcome": "executed" if accepted else "rejected" if rejected else "unknown",
        "cost": {"raw": value["cost_raw"], "value": value["cost_raw"] / GIFT_SCALE,
                 "unit": "ducats", "scale": GIFT_SCALE, "payer": actor,
                 "source": "native_rule"},
        "opinion": {
            "raw": value["opinion_raw"], "value": value["opinion_raw"],
            "unit": "opinion", "scale": TRUST_SCALE,
        },
        "duration": {"months": value["duration_months"], "unit": "months", "scale": 1},
        "trust": {
            "trustor": recipient, "trusted": actor, "direction": "recipient_to_actor",
            "before_raw": before["recipient_trust_raw"] if before["complete"] else None,
            "after_raw": after["recipient_trust_raw"] if after["complete"] else None,
            "change_raw": (after["recipient_trust_raw"] - before["recipient_trust_raw"])
                if settled else None,
            "unit": "trust", "scale": TRUST_SCALE,
        },
        "influencer": {
            "actor": actor, "recipient": recipient,
            "before_active": before["influencer_active"] if before["complete"] else None,
            "after_active": after["influencer_active"] if after["complete"] else None,
            "unit": "flag",
        },
    }
    if controlled_country == actor:
        result["controlled_treasury"] = {
            "country": controlled_country, "unit": "ducats", "scale": GIFT_SCALE,
            "before_raw": before["actor_treasury_raw"] if before["complete"] else None,
            "after_raw": after["actor_treasury_raw"] if after["complete"] else None,
        }
    return result


def project_result(action_id: str, value: object, actor: str, recipient: str,
                   native_state: int, controlled_country: str = "FRA") -> dict[str, Any] | None:
    if action_id == GIFT_ACTION_ID:
        return project_gift_result(value, actor, recipient, native_state, controlled_country)
    if action_id == INFLUENCE_ACTION_ID:
        return project_influence_result(value, actor, recipient, native_state, controlled_country)
    return None
