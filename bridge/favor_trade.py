"""Validate and project native favor exchange values without action addresses."""
from __future__ import annotations
from typing import Any

QUERY_CAPABILITY = "native_favor_gold_query"
SUBMISSION_CAPABILITY = "native_favor_gold_submission"
RESPONSE_CAPABILITY = "native_inbound_favor_gold_response"
ACTION_ID = "trade_favors_for_gold"


def validate_query(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "kind", "amount_raw", "amount_readable", "favor_cost_raw", "favors_available_raw",
        "actor_treasury_raw", "recipient_treasury_raw", "resource_scale", "complete",
    }:
        return False
    if value["kind"] != "gold" or value["resource_scale"] != 1000:
        return False
    for key in ("amount_readable", "complete"):
        if type(value[key]) is not bool:
            return False
    for key in ("amount_raw", "favor_cost_raw", "favors_available_raw",
                "actor_treasury_raw", "recipient_treasury_raw"):
        if type(value[key]) is not int or not -2147483648 <= value[key] <= 2147483647:
            return False
    return not value["complete"] or (
        value["amount_readable"] and value["amount_raw"] >= 0 and value["favor_cost_raw"] >= 0)


def project_query(value: object, actor: str, recipient: str) -> dict[str, Any] | None:
    if not validate_query(value):
        return None
    assert isinstance(value, dict)
    return {
        "kind": "gold", "source": "native_rule", "complete": value["complete"],
        "amount": {"available": value["amount_readable"], "raw": value["amount_raw"],
                   "value": value["amount_raw"] / 1000, "unit": "ducats", "scale": 1000,
                   "payer": recipient, "receiver": actor},
        "favors": {"available": value["complete"], "held_by": actor, "owed_by": recipient,
                   "current_raw": value["favors_available_raw"],
                   "current": value["favors_available_raw"] / 1000,
                   "cost_raw": value["favor_cost_raw"], "cost": value["favor_cost_raw"] / 1000,
                   "unit": "favors", "scale": 1000},
    }


def validate_result(value: object, native_state: object) -> bool:
    """Validate the observed settlement independently of the native proof flag."""
    if (not isinstance(value, dict) or set(value) != {
            "before", "after", "amount_raw", "complete", "verified"}
            or type(native_state) is not int or native_state not in (0, 1, 2)
            or type(value["complete"]) is not bool
            or type(value["verified"]) is not bool
            or type(value["amount_raw"]) is not int
            or not 0 <= value["amount_raw"] <= 2147483647):
        return False
    for name in ("before", "after"):
        row = value[name]
        if (not isinstance(row, dict) or set(row) != {
                "complete", "actor_treasury_raw", "recipient_treasury_raw",
                "favors_raw", "cost_raw"} or type(row["complete"]) is not bool):
            return False
        if any(type(row[key]) is not int or not -2147483648 <= row[key] <= 2147483647
               for key in row if key != "complete"):
            return False
    before, after = value["before"], value["after"]
    if value["complete"] and not (before["complete"] and after["complete"]):
        return False
    if not value["verified"]:
        return True
    if not value["complete"] or before["cost_raw"] < 0:
        return False
    if native_state == 1:
        return before == after
    if native_state != 2:
        return False
    amount = value["amount_raw"]
    return (after["actor_treasury_raw"] - before["actor_treasury_raw"] == amount
            and before["recipient_treasury_raw"] - after["recipient_treasury_raw"] == amount
            and before["favors_raw"] - after["favors_raw"] == before["cost_raw"]
            and after["cost_raw"] == before["cost_raw"])


def project_result(value: dict, actor: str, recipient: str,
                   controlled_country: str = "FRA") -> dict[str, Any]:
    """Expose the transfer and the controlled country's own balance."""
    before, after = value["before"], value["after"]
    complete = value["complete"]
    balance_key = ("actor_treasury_raw" if controlled_country == actor
                   else "recipient_treasury_raw" if controlled_country == recipient else None)
    result = {
        "kind": "gold", "complete": complete, "verified": value["verified"],
        "amount": {"raw": value["amount_raw"], "value": value["amount_raw"] / 1000,
                   "unit": "ducats", "scale": 1000, "payer": recipient, "receiver": actor},
        "transfer": {"available": complete,
                     "raw": after["actor_treasury_raw"] - before["actor_treasury_raw"]
                     if complete else None, "unit": "ducats", "scale": 1000},
        "favors": {"held_by": actor, "owed_by": recipient, "available": complete,
                   "before_raw": before["favors_raw"] if before["complete"] else None,
                   "after_raw": after["favors_raw"] if after["complete"] else None,
                   "spent_raw": before["favors_raw"] - after["favors_raw"] if complete else None,
                   "cost_raw": before["cost_raw"] if before["complete"] else None,
                   "unit": "favors", "scale": 1000},
    }
    if balance_key is not None:
        result["controlled_treasury"] = {
            "country": controlled_country, "unit": "ducats", "scale": 1000,
            "before_raw": before[balance_key] if before["complete"] else None,
            "after_raw": after[balance_key] if after["complete"] else None}
    return result
