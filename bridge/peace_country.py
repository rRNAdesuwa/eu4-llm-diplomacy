"""Pure validation and selection helpers for R61 country peace terms.

The native adapter owns candidate enumeration, legality, cost and settlement.
This module only validates the public country-shaped term payloads and derives
the nine bounded country fields used by the later QUERY18/EXEC10 adapter.
"""

from __future__ import annotations

import re
from typing import Any


COUNTRY_TAG_RE = re.compile(r"^[A-Z0-9]{3}$")

COUNTRY_TERM_ACTIONS = frozenset({
    "release_nation",
    "force_vassalization",
    "form_personal_union",
    "grant_independence",
    "full_annexation",
})

COUNTRY_TERM_MASKS = {
    "release_nation": "n",
    "force_vassalization": "z",
    "form_personal_union": "u",
    "grant_independence": "i",
    "full_annexation": "e",
}

COUNTRY_TERM_CANONICAL_ORDER = (
    "release_nation",
    "force_vassalization",
    "form_personal_union",
    "grant_independence",
    "full_annexation",
)

PEACE_TERM_MASK_ORDER = "mprtcahsfbvlxnzuie"
PEACE_TERM_CANONICAL_ORDER = (
    "demand_ducats",
    "cede_province",
    "war_reparations",
    "transfer_trade_power",
    "concede_defeat",
    "annul_treaties",
    "humiliate_rival",
    "show_strength",
    "force_religion",
    "return_core",
    "revoke_core",
    "release_subject",
    "transfer_subject",
    "release_nation",
    "force_vassalization",
    "form_personal_union",
    "grant_independence",
    "full_annexation",
)

COUNTRY_SELECTION_KEYS = (
    "release_nation_country",
    "release_nation_source",
    "vassal_country",
    "union_country",
    "independence_country",
    "annex_country",
    "vassal_beneficiary",
    "union_beneficiary",
    "annex_beneficiary",
)


def _fail(code: str) -> None:
    raise ValueError(code)


def _tag(value: object, code: str) -> str:
    if not isinstance(value, str) or COUNTRY_TAG_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _roles(actor: object, recipient: object, direction: object) -> tuple[str, str]:
    actor_tag = _tag(actor, "PEACE_EXECUTION_ACTOR_INVALID")
    recipient_tag = _tag(recipient, "PEACE_EXECUTION_RECIPIENT_INVALID")
    if actor_tag == recipient_tag:
        _fail("PEACE_EXECUTION_RECIPIENT_INVALID")
    if direction not in ("demand", "offer"):
        _fail("PEACE_EXECUTION_DIRECTION_INVALID")
    # The country that pays/concedes in the offer context is the actor for an
    # offer and the recipient for a demand.  The treaty claimant is the other
    # side.  Native legality still decides whether a third-country role is
    # accepted when a caller supplies it explicitly.
    offer_payer = actor_tag if direction == "offer" else recipient_tag
    claimant = recipient_tag if direction == "offer" else actor_tag
    return offer_payer, claimant


def normalize_country_term(
        term: object,
        action_id: str,
        actor: object,
        recipient: object,
        direction: object,
    ) -> dict[str, Any]:
    """Normalize one of the five R61 country terms.

    ``country`` is the affected country for annexation, vassalization and
    union.  Release Nation uses ``country`` plus an optional ``source``;
    missing source defaults to the offer payer.  The other three terms use an
    optional ``beneficiary`` defaulting to the treaty claimant.  Grant
    Independence intentionally has no public country field: its internal
    selected country is derived by :func:`extract_country_selection`.
    """

    if action_id not in COUNTRY_TERM_ACTIONS:
        _fail("PEACE_EXECUTION_COUNTRY_ACTION_INVALID")
    if not isinstance(term, dict) or term.get("action_id") != action_id:
        _fail("PEACE_EXECUTION_TERM_INVALID")
    offer_payer, claimant = _roles(actor, recipient, direction)

    if action_id == "grant_independence":
        if set(term) != {"action_id"}:
            _fail("PEACE_EXECUTION_TERM_INVALID")
        return {"action_id": action_id}

    if action_id == "release_nation":
        if set(term) not in (
                {"action_id", "country"},
                {"action_id", "country", "source"},
        ):
            _fail("PEACE_EXECUTION_TERM_INVALID")
        country = _tag(
            term.get("country"), "PEACE_EXECUTION_RELEASE_NATION_COUNTRY_INVALID")
        source = _tag(
            term.get("source", offer_payer),
            "PEACE_EXECUTION_RELEASE_NATION_SOURCE_INVALID")
        if source == country:
            _fail("PEACE_EXECUTION_RELEASE_NATION_PARTIES_INVALID")
        return {"action_id": action_id, "country": country, "source": source}

    if set(term) not in (
            {"action_id", "country"},
            {"action_id", "country", "beneficiary"},
    ):
        _fail("PEACE_EXECUTION_TERM_INVALID")
    country = _tag(
        term.get("country"), "PEACE_EXECUTION_COUNTRY_INVALID")
    beneficiary = _tag(
        term.get("beneficiary", claimant),
        "PEACE_EXECUTION_COUNTRY_BENEFICIARY_INVALID")
    if country == beneficiary:
        _fail("PEACE_EXECUTION_COUNTRY_PARTIES_INVALID")
    return {
        "action_id": action_id,
        "country": country,
        "beneficiary": beneficiary,
    }


# A descriptive alias makes the helper's role obvious to the native adapter
# without duplicating validation logic.
validate_country_term = normalize_country_term


def country_mask_for_terms(
        terms: object,
        *,
        primary_action: str | None = None,
    ) -> str:
    """Return canonical ``nzuie`` letters for selected or discovery terms.

    An empty term list is a discovery request only when ``primary_action`` is
    one of the five country actions.  In that form the returned mask contains
    exactly the primary action's letter; no country selection is fabricated.
    """

    if not isinstance(terms, list):
        _fail("PEACE_EXECUTION_COUNTRY_TERMS_INVALID")
    actions: set[str] = set()
    for term in terms:
        if not isinstance(term, dict):
            _fail("PEACE_EXECUTION_TERM_INVALID")
        action = term.get("action_id")
        if action in COUNTRY_TERM_ACTIONS:
            if action in actions:
                _fail("PEACE_EXECUTION_DUPLICATE_TERM")
            actions.add(action)
    if not actions and primary_action is not None:
        if primary_action not in COUNTRY_TERM_ACTIONS:
            _fail("PEACE_EXECUTION_COUNTRY_ACTION_INVALID")
        actions.add(primary_action)
    return "".join(
        COUNTRY_TERM_MASKS[action]
        for action in COUNTRY_TERM_CANONICAL_ORDER
        if action in actions
    )


def extract_country_selection(
        terms: object,
        actor: object,
        recipient: object,
        direction: object,
    ) -> dict[str, str]:
    """Extract the nine wire-ready country fields from normalized terms.

    Missing fields are the literal ``"-"`` placeholder required by the
    QUERY18/EXEC10 wire.  ``grant_independence`` maps internally to the offer
    payer, while exposing no public country parameter.  Existing non-country
    terms are ignored; duplicate country families and malformed selected
    terms are rejected.
    """

    if not isinstance(terms, list):
        _fail("PEACE_EXECUTION_COUNTRY_TERMS_INVALID")
    offer_payer, _ = _roles(actor, recipient, direction)
    result = {key: "-" for key in COUNTRY_SELECTION_KEYS}
    seen: set[str] = set()
    for term in terms:
        if not isinstance(term, dict):
            _fail("PEACE_EXECUTION_TERM_INVALID")
        action = term.get("action_id")
        if action not in COUNTRY_TERM_ACTIONS:
            continue
        if action in seen:
            _fail("PEACE_EXECUTION_DUPLICATE_TERM")
        seen.add(action)
        normalized = normalize_country_term(
            term, action, actor, recipient, direction)
        if action == "release_nation":
            result["release_nation_country"] = normalized["country"]
            result["release_nation_source"] = normalized["source"]
        elif action == "force_vassalization":
            result["vassal_country"] = normalized["country"]
            result["vassal_beneficiary"] = normalized["beneficiary"]
        elif action == "form_personal_union":
            result["union_country"] = normalized["country"]
            result["union_beneficiary"] = normalized["beneficiary"]
        elif action == "grant_independence":
            result["independence_country"] = offer_payer
        elif action == "full_annexation":
            result["annex_country"] = normalized["country"]
            result["annex_beneficiary"] = normalized["beneficiary"]
    return result


def extract_country_selection_from_parameters(
        parameters: object,
        actor: object,
        recipient: object,
    ) -> dict[str, str] | None:
    """Convenience wrapper for a complete ``peace_context`` object."""

    if not isinstance(parameters, dict):
        return None
    context = parameters.get("peace_context")
    if not isinstance(context, dict):
        return None
    direction = context.get("direction", "demand")
    return extract_country_selection(
        context.get("terms"), actor, recipient, direction)


__all__ = [
    "COUNTRY_TAG_RE",
    "COUNTRY_TERM_ACTIONS",
    "COUNTRY_TERM_MASKS",
    "COUNTRY_TERM_CANONICAL_ORDER",
    "PEACE_TERM_MASK_ORDER",
    "PEACE_TERM_CANONICAL_ORDER",
    "COUNTRY_SELECTION_KEYS",
    "normalize_country_term",
    "validate_country_term",
    "country_mask_for_terms",
    "extract_country_selection",
    "extract_country_selection_from_parameters",
]
