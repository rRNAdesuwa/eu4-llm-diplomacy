"""Strict public-parameter normalization for the Peace execution wire.

This module normalizes the currently specified Peace terms in either
explicit ``demand`` or ``offer`` direction:
``white_peace``, ``demand_ducats``, ``cede_province`` and
``war_reparations``.  Native code still
owns war-context lookup, legality, payload construction, authorization and
the actual execution result.  A successful normalization therefore does not
claim that execution is installed or legal.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any


_WAR_ID_RE = re.compile(r"^war_[0-9a-f]{16}_[0-9a-f]{8}$")
_COUNTRY_TAG_RE = re.compile(r"^[A-Z0-9]{3}$")
_MAX_INT32 = 2_147_483_647
_MAX_MONEY_AMOUNT = Decimal("2147483.647")
_MONEY_SCALE = Decimal(1000)
_MONEY_RAW_STEP = 100

_MONEY_ACTION = "demand_ducats"
_PROVINCE_ACTION = "cede_province"
_REPARATIONS_ACTION = "war_reparations"
_WHITE_ACTION = "white_peace"
_SUPPORTED_ACTIONS = frozenset(
    {_WHITE_ACTION, _MONEY_ACTION, _PROVINCE_ACTION, _REPARATIONS_ACTION})


def _fail(code: str) -> None:
    """Raise a stable, machine-readable validation error."""

    raise ValueError(code)


def _normalize_amount(value: object) -> str:
    """Return one-decimal ducats after validating native raw precision."""

    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        _fail("PEACE_EXECUTION_MONEY_AMOUNT_INVALID")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        _fail("PEACE_EXECUTION_MONEY_AMOUNT_INVALID")

    # Compare before multiplication.  This rejects huge Decimal exponents
    # without constructing an oversized native raw integer.
    if (not amount.is_finite() or amount <= 0
            or amount > _MAX_MONEY_AMOUNT):
        _fail("PEACE_EXECUTION_MONEY_AMOUNT_INVALID")
    # The active Decimal context may have only 28 significant digits.  Build
    # amount*10 from the Decimal tuple instead of multiplying by 1000 under
    # that context; otherwise a long value such as 10.000...001 could round
    # to a seemingly valid tenth of a ducat.
    sign, digits, exponent = amount.as_tuple()
    scaled_tenths = Decimal((sign, digits, exponent + 1))
    if scaled_tenths != scaled_tenths.to_integral_value():
        _fail("PEACE_EXECUTION_MONEY_AMOUNT_INVALID")
    tenths = int(scaled_tenths)
    raw = tenths * 100
    if raw <= 0 or raw > _MAX_INT32 or raw % _MONEY_RAW_STEP != 0:
        _fail("PEACE_EXECUTION_MONEY_AMOUNT_INVALID")
    return f"{tenths // 10}.{tenths % 10}"


def _validate_tag(value: object, code: str) -> str:
    if not isinstance(value, str) or _COUNTRY_TAG_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _validate_province_ids(value: object) -> list[int]:
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        _fail("PEACE_EXECUTION_PROVINCE_IDS_INVALID")
    result: list[int] = []
    for province_id in value:
        if (isinstance(province_id, bool)
                or not isinstance(province_id, int)
                or not 1 <= province_id <= _MAX_INT32):
            _fail("PEACE_EXECUTION_PROVINCE_IDS_INVALID")
        if province_id in result:
            _fail("PEACE_EXECUTION_PROVINCE_IDS_INVALID")
        result.append(province_id)
    return result


def _validate_money_term(term: object, actor: str, recipient: str,
                         direction: str) -> dict[str, Any]:
    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "amount", "payer", "claimant"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != _MONEY_ACTION:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    expected_payer = actor if direction == "offer" else recipient
    expected_claimant = recipient if direction == "offer" else actor
    if (term.get("payer") != expected_payer
            or term.get("claimant") != expected_claimant):
        _fail("PEACE_EXECUTION_MONEY_PARTIES_INVALID")
    return {
        "action_id": _MONEY_ACTION,
        "amount": _normalize_amount(term.get("amount")),
        "payer": expected_payer,
        "claimant": expected_claimant,
    }


def _validate_province_term(term: object) -> dict[str, Any]:
    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "province_ids", "beneficiary"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != _PROVINCE_ACTION:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    beneficiary = _validate_tag(
        term.get("beneficiary"), "PEACE_EXECUTION_BENEFICIARY_INVALID")
    return {
        "action_id": _PROVINCE_ACTION,
        "province_ids": _validate_province_ids(term.get("province_ids")),
        "beneficiary": beneficiary,
    }


def _validate_reparations_term(term: object, actor: str, recipient: str,
                               direction: str) -> dict[str, Any]:
    """Validate the direction-bound, non-numeric reparations term."""

    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "payer", "claimant"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != _REPARATIONS_ACTION:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    expected_payer = actor if direction == "offer" else recipient
    expected_claimant = recipient if direction == "offer" else actor
    if (term.get("payer") != expected_payer
            or term.get("claimant") != expected_claimant):
        _fail("PEACE_EXECUTION_REPARATIONS_PARTIES_INVALID")
    return {
        "action_id": _REPARATIONS_ACTION,
        "payer": expected_payer,
        "claimant": expected_claimant,
    }


def normalize_peace_execution_parameters(
        action_id: str,
        actor: str,
        recipient: str,
        phase: str,
        parameters: object,
    ) -> dict[str, Any]:
    """Normalize one complete public Peace execution parameter object.

    The returned object is a fresh structure.  For mixed terms, the stable
    wire order is money, province, reparations.  This preserves the existing
    money-plus-province order while appending the new non-numeric term.
    ``ValueError.args[0]``
    is one of the stable ``PEACE_EXECUTION_*`` codes below.
    """

    if not isinstance(action_id, str) or action_id not in _SUPPORTED_ACTIONS:
        _fail("PEACE_EXECUTION_ACTION_INVALID")
    if actor != "FRA":
        _fail("PEACE_EXECUTION_ACTOR_INVALID")
    if (not isinstance(actor, str)
            or _COUNTRY_TAG_RE.fullmatch(actor) is None):
        _fail("PEACE_EXECUTION_ACTOR_INVALID")
    if (not isinstance(recipient, str)
            or _COUNTRY_TAG_RE.fullmatch(recipient) is None
            or recipient == actor):
        _fail("PEACE_EXECUTION_RECIPIENT_INVALID")
    if phase != "initiate":
        _fail("PEACE_EXECUTION_PHASE_INVALID")

    if not isinstance(parameters, dict) or set(parameters) != {"peace_context"}:
        _fail("PEACE_EXECUTION_PARAMETERS_REQUIRED")
    context = parameters.get("peace_context")
    if (not isinstance(context, dict)
            or set(context) != {"war_id", "direction", "terms"}):
        _fail("PEACE_EXECUTION_CONTEXT_INVALID")
    war_id = context.get("war_id")
    if not isinstance(war_id, str) or _WAR_ID_RE.fullmatch(war_id) is None:
        _fail("PEACE_EXECUTION_WAR_ID_INVALID")
    direction = context.get("direction")
    if direction not in ("demand", "offer"):
        _fail("PEACE_EXECUTION_DIRECTION_INVALID")
    terms = context.get("terms")
    if not isinstance(terms, list):
        _fail("PEACE_EXECUTION_TERMS_INVALID")

    if action_id == _WHITE_ACTION:
        if terms != []:
            _fail("PEACE_EXECUTION_WHITE_TERMS_INVALID")
        normalized_terms: list[dict[str, Any]] = []
    else:
        if not 1 <= len(terms) <= 3:
            _fail("PEACE_EXECUTION_TERMS_INVALID")
        normalized_terms = []
        money_term: dict[str, Any] | None = None
        province_term: dict[str, Any] | None = None
        reparations_term: dict[str, Any] | None = None
        for term in terms:
            if not isinstance(term, dict) or "action_id" not in term:
                _fail("PEACE_EXECUTION_TERM_INVALID")
            term_action = term.get("action_id")
            if (not isinstance(term_action, str)
                    or term_action not in {
                        _MONEY_ACTION, _PROVINCE_ACTION, _REPARATIONS_ACTION}):
                _fail("PEACE_EXECUTION_TERM_UNKNOWN")
            if term_action == _MONEY_ACTION:
                if money_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                money_term = _validate_money_term(
                    term, actor, recipient, direction)
            elif term_action == _PROVINCE_ACTION:
                if province_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                province_term = _validate_province_term(term)
            else:
                if reparations_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                reparations_term = _validate_reparations_term(
                    term, actor, recipient, direction)

        if action_id == _MONEY_ACTION and money_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _PROVINCE_ACTION and province_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _REPARATIONS_ACTION and reparations_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if money_term is not None:
            normalized_terms.append(money_term)
        if province_term is not None:
            normalized_terms.append(province_term)
        if reparations_term is not None:
            normalized_terms.append(reparations_term)

    return {
        "peace_context": {
            "war_id": war_id,
            "direction": direction,
            "terms": normalized_terms,
        }
    }


__all__ = ["normalize_peace_execution_parameters"]
