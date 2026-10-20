"""Strict public-parameter normalization for the Peace execution wire.

This module normalizes the currently specified Peace terms in either
explicit ``demand`` or ``offer`` direction:
``white_peace``, ``demand_ducats``, ``cede_province`` and
``war_reparations``, ``transfer_trade_power``, ``concede_defeat``,
``annul_treaties``, ``humiliate_rival``, ``show_strength`` and
``force_religion``, ``return_core``, ``revoke_core``, ``release_subject`` and
``transfer_subject``, ``release_nation``, ``force_vassalization``,
``form_personal_union``, ``grant_independence`` and ``full_annexation``.
Native code still
owns war-context lookup, legality, payload construction, authorization and
the actual execution result.  A successful normalization therefore does not
claim that execution is installed or legal.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .peace_country import COUNTRY_TERM_ACTIONS, normalize_country_term


_WAR_ID_RE = re.compile(r"^war_[0-9a-f]{16}_[0-9a-f]{8}$")
_COUNTRY_TAG_RE = re.compile(r"^[A-Z0-9]{3}$")
_MAX_INT32 = 2_147_483_647
_MAX_MONEY_AMOUNT = Decimal("2147483.647")
_MONEY_SCALE = Decimal(1000)
_MONEY_RAW_STEP = 100

_MONEY_ACTION = "demand_ducats"
_PROVINCE_ACTION = "cede_province"
_REPARATIONS_ACTION = "war_reparations"
_TRADE_POWER_ACTION = "transfer_trade_power"
_CONCEDE_DEFEAT_ACTION = "concede_defeat"
_ANNUL_TREATIES_ACTION = "annul_treaties"
_HUMILIATE_RIVAL_ACTION = "humiliate_rival"
_SHOW_STRENGTH_ACTION = "show_strength"
_FORCE_RELIGION_ACTION = "force_religion"
_RETURN_CORE_ACTION = "return_core"
_REVOKE_CORE_ACTION = "revoke_core"
_RELEASE_SUBJECT_ACTION = "release_subject"
_TRANSFER_SUBJECT_ACTION = "transfer_subject"
_RELEASE_NATION_ACTION = "release_nation"
_FORCE_VASSALIZATION_ACTION = "force_vassalization"
_FORM_PERSONAL_UNION_ACTION = "form_personal_union"
_GRANT_INDEPENDENCE_ACTION = "grant_independence"
_FULL_ANNEXATION_ACTION = "full_annexation"
_WHITE_ACTION = "white_peace"
_SUPPORTED_ACTIONS = frozenset(
    {_WHITE_ACTION, _MONEY_ACTION, _PROVINCE_ACTION, _REPARATIONS_ACTION,
     _TRADE_POWER_ACTION, _CONCEDE_DEFEAT_ACTION, _ANNUL_TREATIES_ACTION,
     _HUMILIATE_RIVAL_ACTION, _SHOW_STRENGTH_ACTION,
     _FORCE_RELIGION_ACTION, _RETURN_CORE_ACTION, _REVOKE_CORE_ACTION,
     _RELEASE_SUBJECT_ACTION, _TRANSFER_SUBJECT_ACTION,
     _RELEASE_NATION_ACTION, _FORCE_VASSALIZATION_ACTION,
     _FORM_PERSONAL_UNION_ACTION, _GRANT_INDEPENDENCE_ACTION,
     _FULL_ANNEXATION_ACTION})


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


def _validate_core_term(term: object, action: str) -> dict[str, Any]:
    """Validate one explicitly selected return/revoke-core term.

    The core owner is a native candidate property and may be any canonical
    country.  Direction and war legality remain native decisions; this
    boundary only enforces the bounded public shape and exact action binding.
    """

    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "province_ids", "core_owner"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != action:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    owner = _validate_tag(
        term.get("core_owner"), "PEACE_EXECUTION_CORE_OWNER_INVALID")
    return {
        "action_id": action,
        "province_ids": _validate_province_ids(term.get("province_ids")),
        "core_owner": owner,
    }


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


def _validate_trade_power_term(term: object, actor: str, recipient: str,
                               direction: str) -> dict[str, Any]:
    """Validate the direction-bound, non-numeric trade-power term.

    The native treaty reads the transfer ratio from its own define/term
    state.  It is therefore deliberately absent from the public request.
    ``source`` and ``beneficiary`` are the public names; the native query
    uses the same names in its ``native_trade_power`` object.
    """

    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "source", "beneficiary"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != _TRADE_POWER_ACTION:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    expected_beneficiary = recipient if direction == "offer" else actor
    source = term.get("source")
    if (not isinstance(source, str)
            or _COUNTRY_TAG_RE.fullmatch(source) is None
            or source == expected_beneficiary
            or term.get("beneficiary") != expected_beneficiary):
        _fail("PEACE_EXECUTION_TRADE_POWER_PARTIES_INVALID")
    return {
        "action_id": _TRADE_POWER_ACTION,
        "source": source,
        "beneficiary": expected_beneficiary,
    }


def _validate_concede_defeat_term(term: object, actor: str, recipient: str,
                                  direction: str) -> dict[str, Any]:
    """Validate the direction-bound non-financial defeat term."""

    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "conceding_country", "beneficiary"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != _CONCEDE_DEFEAT_ACTION:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    expected_conceding = actor if direction == "offer" else recipient
    expected_beneficiary = recipient if direction == "offer" else actor
    if (term.get("conceding_country") != expected_conceding
            or term.get("beneficiary") != expected_beneficiary):
        _fail("PEACE_EXECUTION_CONCEDE_DEFEAT_PARTIES_INVALID")
    return {
        "action_id": _CONCEDE_DEFEAT_ACTION,
        "conceding_country": expected_conceding,
        "beneficiary": expected_beneficiary,
    }


def _validate_annul_treaties_term(term: object) -> dict[str, Any]:
    """Validate an explicitly selected annul-treaties term.

    Native candidate selection decides whether the requested country and
    partners are legally cancellable.  The bridge only enforces the public
    shape and canonical ordering: one country, one to sixteen distinct
    canonical partner tags, and no self-partner.
    """

    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) != {"action_id", "country", "treaty_partners"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != _ANNUL_TREATIES_ACTION:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    country = _validate_tag(
        term.get("country"), "PEACE_EXECUTION_ANNUL_COUNTRY_INVALID")
    partners = term.get("treaty_partners")
    if (not isinstance(partners, list)
            or not 1 <= len(partners) <= 16):
        _fail("PEACE_EXECUTION_ANNUL_PARTNERS_INVALID")
    normalized: list[str] = []
    for partner in partners:
        partner_tag = _validate_tag(
            partner, "PEACE_EXECUTION_ANNUL_PARTNERS_INVALID")
        if partner_tag == country or partner_tag in normalized:
            _fail("PEACE_EXECUTION_ANNUL_PARTNERS_INVALID")
        normalized.append(partner_tag)
    if normalized != sorted(normalized):
        _fail("PEACE_EXECUTION_ANNUL_PARTNERS_INVALID")
    return {
        "action_id": _ANNUL_TREATIES_ACTION,
        "country": country,
        "treaty_partners": normalized,
    }


def _validate_special_term(term: object, actor: str, recipient: str,
                           direction: str, action: str) -> dict[str, Any]:
    """Validate one of the direction-bound special peace terms.

    Native owns whether the selected country is a valid rival/target and the
    resulting prestige/religion changes.  The bridge only makes the public
    roles explicit and directionally unambiguous.  As with the concede-defeat
    term, callers may omit the two role fields when constructing a convenient
    direction-bound selection; normalization fills them with their canonical
    values.  Explicit wrong roles are rejected rather than silently repaired.
    """

    if not isinstance(term, dict):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if set(term) - {"action_id", "country", "beneficiary"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    if term.get("action_id") != action:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    expected_country = actor if direction == "offer" else recipient
    expected_beneficiary = recipient if direction == "offer" else actor
    country = term.get("country", expected_country)
    beneficiary = term.get("beneficiary", expected_beneficiary)
    _validate_tag(country, "PEACE_EXECUTION_SPECIAL_COUNTRY_INVALID")
    _validate_tag(beneficiary, "PEACE_EXECUTION_SPECIAL_BENEFICIARY_INVALID")
    if (country != expected_country or beneficiary != expected_beneficiary
            or country == beneficiary):
        _fail("PEACE_EXECUTION_SPECIAL_PARTIES_INVALID")
    return {
        "action_id": action,
        "country": expected_country,
        "beneficiary": expected_beneficiary,
    }


def _validate_subject_term(term: object, action: str) -> dict[str, Any]:
    """Validate one bounded release/transfer-subject selection."""

    if not isinstance(term, dict) or term.get("action_id") != action:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    keys = set(term)
    if keys == {"action_id", "country"}:
        return {
            "action_id": action,
            "country": _validate_tag(
                term.get("country"),
                "PEACE_EXECUTION_SUBJECT_COUNTRIES_INVALID"),
        }
    if keys != {"action_id", "countries"}:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    countries = term.get("countries")
    if not isinstance(countries, list) or not 1 <= len(countries) <= 16:
        _fail("PEACE_EXECUTION_SUBJECT_COUNTRIES_INVALID")
    normalized: list[str] = []
    for country in countries:
        country = _validate_tag(
            country, "PEACE_EXECUTION_SUBJECT_COUNTRIES_INVALID")
        if country in normalized:
            _fail("PEACE_EXECUTION_SUBJECT_COUNTRIES_INVALID")
        normalized.append(country)
    if normalized != sorted(normalized):
        _fail("PEACE_EXECUTION_SUBJECT_COUNTRIES_INVALID")
    if len(normalized) == 1:
        return {"action_id": action, "country": normalized[0]}
    return {"action_id": action, "countries": normalized}


def normalize_peace_execution_parameters(
        action_id: str,
        actor: str,
        recipient: str,
        phase: str,
        parameters: object,
    ) -> dict[str, Any]:
    """Normalize one complete public Peace execution parameter object.

    The returned object is a fresh structure.  For mixed terms, the stable
    wire order is money, province, reparations, trade power, concede defeat,
    annul treaties, special terms, return-core, revoke-core and the five
    country terms.  This preserves the existing money-plus-province order
    while appending the non-numeric terms in canonical
    ``m,p,r,t,c,a,h,s,f,b,v,l,x,n,z,u,i,e`` order.
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
    elif (action_id == _ANNUL_TREATIES_ACTION and terms == []) or (
            action_id in COUNTRY_TERM_ACTIONS and terms == []):
        # An A-primary empty selection is the explicit native candidate
        # discovery form.  It is query-only and must not be treated as a
        # selected white peace or as an executable empty treaty.
        normalized_terms = []
    else:
        if not 1 <= len(terms) <= 18:
            _fail("PEACE_EXECUTION_TERMS_INVALID")
        normalized_terms = []
        money_term: dict[str, Any] | None = None
        province_term: dict[str, Any] | None = None
        reparations_term: dict[str, Any] | None = None
        trade_power_term: dict[str, Any] | None = None
        concede_defeat_term: dict[str, Any] | None = None
        annul_treaties_term: dict[str, Any] | None = None
        humiliate_rival_term: dict[str, Any] | None = None
        show_strength_term: dict[str, Any] | None = None
        force_religion_term: dict[str, Any] | None = None
        return_core_term: dict[str, Any] | None = None
        revoke_core_term: dict[str, Any] | None = None
        release_subject_term: dict[str, Any] | None = None
        transfer_subject_term: dict[str, Any] | None = None
        country_terms: dict[str, dict[str, Any] | None] = {
            country_action: None
            for country_action in COUNTRY_TERM_ACTIONS
        }
        for term in terms:
            if not isinstance(term, dict) or "action_id" not in term:
                _fail("PEACE_EXECUTION_TERM_INVALID")
            term_action = term.get("action_id")
            if (not isinstance(term_action, str)
                    or term_action not in {
                        _MONEY_ACTION, _PROVINCE_ACTION, _REPARATIONS_ACTION,
                        _TRADE_POWER_ACTION, _CONCEDE_DEFEAT_ACTION,
                        _ANNUL_TREATIES_ACTION, _HUMILIATE_RIVAL_ACTION,
                        _SHOW_STRENGTH_ACTION, _FORCE_RELIGION_ACTION,
                        _RETURN_CORE_ACTION, _REVOKE_CORE_ACTION,
                        _RELEASE_SUBJECT_ACTION, _TRANSFER_SUBJECT_ACTION,
                    } | COUNTRY_TERM_ACTIONS):
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
            elif term_action == _REPARATIONS_ACTION:
                if reparations_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                reparations_term = _validate_reparations_term(
                    term, actor, recipient, direction)
            elif term_action == _TRADE_POWER_ACTION:
                if trade_power_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                trade_power_term = _validate_trade_power_term(
                    term, actor, recipient, direction)
            elif term_action == _CONCEDE_DEFEAT_ACTION:
                if concede_defeat_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                concede_defeat_term = _validate_concede_defeat_term(
                    term, actor, recipient, direction)
            elif term_action == _ANNUL_TREATIES_ACTION:
                if annul_treaties_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                annul_treaties_term = _validate_annul_treaties_term(term)
            elif term_action == _HUMILIATE_RIVAL_ACTION:
                if humiliate_rival_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                humiliate_rival_term = _validate_special_term(
                    term, actor, recipient, direction, _HUMILIATE_RIVAL_ACTION)
            elif term_action == _SHOW_STRENGTH_ACTION:
                if show_strength_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                show_strength_term = _validate_special_term(
                    term, actor, recipient, direction, _SHOW_STRENGTH_ACTION)
            elif term_action == _FORCE_RELIGION_ACTION:
                if force_religion_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                force_religion_term = _validate_special_term(
                    term, actor, recipient, direction, _FORCE_RELIGION_ACTION)
            elif term_action == _RETURN_CORE_ACTION:
                if return_core_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                return_core_term = _validate_core_term(term, _RETURN_CORE_ACTION)
            elif term_action == _REVOKE_CORE_ACTION:
                if revoke_core_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                revoke_core_term = _validate_core_term(term, _REVOKE_CORE_ACTION)
            elif term_action == _RELEASE_SUBJECT_ACTION:
                if release_subject_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                release_subject_term = _validate_subject_term(
                    term, _RELEASE_SUBJECT_ACTION)
            elif term_action == _TRANSFER_SUBJECT_ACTION:
                if transfer_subject_term is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                transfer_subject_term = _validate_subject_term(
                    term, _TRANSFER_SUBJECT_ACTION)
            else:
                if country_terms[term_action] is not None:
                    _fail("PEACE_EXECUTION_DUPLICATE_TERM")
                country_terms[term_action] = normalize_country_term(
                    term, term_action, actor, recipient, direction)

        if action_id == _MONEY_ACTION and money_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _PROVINCE_ACTION and province_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _REPARATIONS_ACTION and reparations_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _TRADE_POWER_ACTION and trade_power_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _CONCEDE_DEFEAT_ACTION and concede_defeat_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _ANNUL_TREATIES_ACTION and annul_treaties_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _HUMILIATE_RIVAL_ACTION and humiliate_rival_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _SHOW_STRENGTH_ACTION and show_strength_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _FORCE_RELIGION_ACTION and force_religion_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _RETURN_CORE_ACTION and return_core_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _REVOKE_CORE_ACTION and revoke_core_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _RELEASE_SUBJECT_ACTION and release_subject_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if action_id == _TRANSFER_SUBJECT_ACTION and transfer_subject_term is None:
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        if (action_id in COUNTRY_TERM_ACTIONS
                and country_terms[action_id] is None):
            _fail("PEACE_EXECUTION_ACTION_TERM_MISSING")
        release_countries = (
            [release_subject_term["country"]]
            if release_subject_term is not None and "country" in release_subject_term
            else (list(release_subject_term["countries"])
                  if release_subject_term is not None else []))
        transfer_countries = (
            [transfer_subject_term["country"]]
            if transfer_subject_term is not None and "country" in transfer_subject_term
            else (list(transfer_subject_term["countries"])
                  if transfer_subject_term is not None else []))
        if set(release_countries).intersection(transfer_countries):
            _fail("PEACE_EXECUTION_SUBJECT_COUNTRY_CONFLICT")
        if money_term is not None:
            normalized_terms.append(money_term)
        if province_term is not None:
            normalized_terms.append(province_term)
        if reparations_term is not None:
            normalized_terms.append(reparations_term)
        if trade_power_term is not None:
            normalized_terms.append(trade_power_term)
        if concede_defeat_term is not None:
            normalized_terms.append(concede_defeat_term)
        if annul_treaties_term is not None:
            normalized_terms.append(annul_treaties_term)
        if humiliate_rival_term is not None:
            normalized_terms.append(humiliate_rival_term)
        if show_strength_term is not None:
            normalized_terms.append(show_strength_term)
        if force_religion_term is not None:
            normalized_terms.append(force_religion_term)
        if return_core_term is not None:
            normalized_terms.append(return_core_term)
        if revoke_core_term is not None:
            normalized_terms.append(revoke_core_term)
        if release_subject_term is not None:
            normalized_terms.append(release_subject_term)
        if transfer_subject_term is not None:
            normalized_terms.append(transfer_subject_term)
        for country_action in (
                _RELEASE_NATION_ACTION, _FORCE_VASSALIZATION_ACTION,
                _FORM_PERSONAL_UNION_ACTION, _GRANT_INDEPENDENCE_ACTION,
                _FULL_ANNEXATION_ACTION):
            country_term = country_terms[country_action]
            if country_term is not None:
                normalized_terms.append(country_term)

    return {
        "peace_context": {
            "war_id": war_id,
            "direction": direction,
            "terms": normalized_terms,
        }
    }


__all__ = ["normalize_peace_execution_parameters"]
