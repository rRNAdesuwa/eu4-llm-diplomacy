"""Answer one pending Peace offer through the public inbound-response API.

The operator is deliberately single-use.  It discovers exactly one opaque
``peace_offer`` proposal from the observed proposer to the controlled country, inspects the
proposal, calls the public response operation once, and polls that same
request id.  It never fabricates a proposal id, retries a request, advances
time, saves the game, or starts a game process.

``--output`` is the report JSON path.  A sibling ``*-evidence`` directory is
created for the four before/after probes, public request records, and the
bounded native-log slice.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal, UnknownRequestError  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _poll_result,
    _sha256_file,
    _write_json,
)
from work.run_peace_authority_test import _snapshot_stability  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _run_snapshots,
)


_ACTION = "peace_offer"
_FAMILY = "peace"
_ACTOR = "ENG"  # legacy default; main replaces from the observed proposal
_RECIPIENT = "FRA"  # legacy default; main replaces from the observed proposal
_PLAYER_SLOT = 189  # POR in the paused observer fixture
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_PUBLIC_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_POLL_SECONDS = 20.0
_DISCOVERY_SECONDS = 10.0
_REMOVAL_SECONDS = 5.0
_MAX_LOG_BYTES = 8 * 1024 * 1024
_MAX_LINE_BYTES = 256 * 1024
_COUNTRY_TAG_RE = re.compile(r"[A-Z][A-Z0-9_]{1,5}\Z")
_TRADE_POWER_AMOUNT_RAW = 500
_TRADE_POWER_AMOUNT_SCALE = 1000
_TRADE_POWER_OPEN_END_RAW = 0x29C77F8
_RESPONSE_EVENTS = frozenset({
    "native_diplomacy_relation_response_result",
    "native_peace_response_result",
    "native_peace_inbound_response_result",
    "native_alliance_response_result",
})
_HANDLER_EVENTS = frozenset({
    "native_peace_response_entry",
    "native_peace_handler_entry",
    "native_peace_inbound_response_entry",
    "native_diplomacy_inbound_response_entry",
})


class PeaceInboundResponseError(RuntimeError):
    """A bounded operator stop with a stable report code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _public_catalog(value: object) -> dict[str, object]:
    """Return the public catalog without adding private native context."""

    if not isinstance(value, dict):
        return {"status": "unknown", "incoming_proposals": [],
                "incoming_proposals_complete": False}
    proposals = value.get("incoming_proposals")
    if not isinstance(proposals, list):
        proposals = []
    return {
        "incoming_proposals": proposals,
        "incoming_proposals_complete": value.get("incoming_proposals_complete"),
        "action_count": value.get("action_count"),
        "category": value.get("category"),
    }


def _peace_proposals(catalog: object, actor: str | None = None,
                     recipient: str | None = None) -> list[dict[str, object]]:
    if not isinstance(catalog, dict):
        return []
    rows = catalog.get("incoming_proposals")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("action_id") == _ACTION
                and row.get("family") == _FAMILY
                and (actor is None or row.get("actor") == actor)
                and (recipient is None or row.get("recipient") == recipient)
                and row.get("decision_country") == row.get("recipient")
                and row.get("observer_status") == "observed_pending"):
            result.append(row)
    return result


def _proposal_contract(proposal: object) -> bool:
    """Validate an observed proposal while retaining its actual roles."""

    if not isinstance(proposal, dict):
        return False
    actor = proposal.get("actor")
    recipient = proposal.get("recipient")
    return (
        isinstance(proposal.get("proposal_id"), str)
        and _PUBLIC_ID_RE.fullmatch(proposal["proposal_id"]) is not None
        and proposal.get("action_id") == _ACTION
        and proposal.get("family") == _FAMILY
        and isinstance(actor, str) and _COUNTRY_TAG_RE.fullmatch(actor) is not None
        and isinstance(recipient, str) and _COUNTRY_TAG_RE.fullmatch(recipient) is not None
        and actor != recipient
        and proposal.get("decision_country") == recipient
        and proposal.get("phase") == "initiate"
        and proposal.get("observer_status") == "observed_pending"
    )


def _peace_context_contract(
        context: object, decision: str | None = None,
        trade_power_pair: tuple[str, str] | None = None,
        ) -> dict[str, bool]:
    """Validate the public context carried by an inbound Peace observation.

    The context is the source of term roles.  In particular, a demand made by
    ENG against FRA pays reparations from FRA to ENG; the response actor alone
    is not used to infer that pair.  Legacy white, money, and province-only
    contexts remain accepted.  R+T is validated as a supported mixed treaty.
    A C term may accompany the existing money/province/R/T terms; native
    legality remains authoritative for those combinations.
    """

    checks = {
        "object": isinstance(context, dict),
        "identity": False,
        "complete": False,
        "selected_terms_complete": False,
        "terms_shape": False,
        "reparations_roles": True,
        "reparations_unique": True,
        "trade_power_roles": True,
        "trade_power_unique": True,
        "concede_defeat_roles": True,
        "concede_defeat_unique": True,
        "annul_treaties_roles": True,
        "annul_treaties_unique": True,
        "special_roles": True,
        "special_unique": True,
        "effect_scope_supported": False,
    }
    if not isinstance(context, dict):
        return checks
    direction = context.get("direction")
    terms = context.get("terms")
    context_actor = context.get("original_actor")
    context_recipient = context.get("original_recipient")
    if (not isinstance(context_actor, str)
            or _COUNTRY_TAG_RE.fullmatch(context_actor) is None):
        context_actor = _ACTOR
    if (not isinstance(context_recipient, str)
            or _COUNTRY_TAG_RE.fullmatch(context_recipient) is None):
        context_recipient = _RECIPIENT
    checks["identity"] = (
        context.get("war_id") is not None
        and direction in ("demand", "offer")
        and context.get("original_actor") == context_actor
        and context.get("original_recipient") == context_recipient
        and context_actor != context_recipient
    )
    checks["complete"] = context.get("complete") is True
    # Older public projections did not carry this optional field.  The
    # inspection/response contract still proves it at the top level.
    checks["selected_terms_complete"] = (
        context.get("selected_terms_complete", True) is True)
    if not isinstance(terms, list):
        return checks
    action_ids: list[object] = []
    r_terms: list[dict[str, object]] = []
    t_terms: list[dict[str, object]] = []
    c_terms: list[dict[str, object]] = []
    a_terms: list[dict[str, object]] = []
    special_terms: dict[str, list[dict[str, object]]] = {
        "humiliate_rival": [], "show_strength": [], "force_religion": []}
    valid_shape = True
    for term in terms:
        if not isinstance(term, dict) or not isinstance(term.get("action_id"), str):
            valid_shape = False
            continue
        action_id = term.get("action_id")
        action_ids.append(action_id)
        if action_id not in {"white_peace", "demand_ducats", "cede_province",
                             "war_reparations", "transfer_trade_power",
                             "concede_defeat", "annul_treaties",
                             "humiliate_rival", "show_strength",
                             "force_religion"}:
            valid_shape = False
        if action_id == "war_reparations":
            r_terms.append(term)
        if action_id == "transfer_trade_power":
            t_terms.append(term)
        if action_id == "concede_defeat":
            c_terms.append(term)
        if action_id == "annul_treaties":
            a_terms.append(term)
        if action_id in special_terms:
            special_terms[action_id].append(term)
    checks["terms_shape"] = valid_shape
    checks["reparations_unique"] = len(r_terms) <= 1
    expected_payer = context_actor if direction == "offer" else context_recipient
    expected_claimant = context_recipient if direction == "offer" else context_actor
    if r_terms:
        checks["reparations_roles"] = (
            len(r_terms) == 1
            and r_terms[0].get("payer") == expected_payer
            and r_terms[0].get("claimant") == expected_claimant
            and _COUNTRY_TAG_RE.fullmatch(str(r_terms[0].get("payer"))) is not None
            and _COUNTRY_TAG_RE.fullmatch(str(r_terms[0].get("claimant"))) is not None
        )
    if t_terms:
        # A native peace candidate may transfer a third country's power.
        # Direction fixes its beneficiary; the selected context fixes source.
        expected_source = t_terms[0].get("source")
        expected_beneficiary = expected_claimant
        checks["trade_power_roles"] = (
            len(t_terms) == 1
            and expected_source != expected_beneficiary
            and t_terms[0].get("beneficiary") == expected_beneficiary
            and _COUNTRY_TAG_RE.fullmatch(str(t_terms[0].get("source"))) is not None
            and _COUNTRY_TAG_RE.fullmatch(str(t_terms[0].get("beneficiary"))) is not None
        )
        if trade_power_pair is not None:
            checks["trade_power_roles"] = (
                checks["trade_power_roles"]
                and (expected_source, expected_beneficiary) == trade_power_pair)
    elif trade_power_pair is not None:
        checks["trade_power_roles"] = False
    checks["trade_power_unique"] = len(t_terms) <= 1
    checks["concede_defeat_unique"] = len(c_terms) <= 1
    if c_terms:
        checks["concede_defeat_roles"] = (
            len(c_terms) == 1
            and c_terms[0].get("conceding_country") == expected_payer
            and c_terms[0].get("beneficiary") == expected_claimant
            and _COUNTRY_TAG_RE.fullmatch(
                str(c_terms[0].get("conceding_country"))) is not None
            and _COUNTRY_TAG_RE.fullmatch(
                str(c_terms[0].get("beneficiary"))) is not None
            and expected_payer != expected_claimant)
    checks["annul_treaties_unique"] = len(a_terms) <= 1
    if a_terms:
        annul_country = a_terms[0].get("country")
        raw_partners = a_terms[0].get("treaty_partners")
        checks["annul_treaties_roles"] = (
            len(a_terms) == 1
            and isinstance(annul_country, str)
            and _COUNTRY_TAG_RE.fullmatch(annul_country) is not None
            and isinstance(raw_partners, list)
            and 1 <= len(raw_partners) <= 16
            and all(isinstance(item, str)
                    and _COUNTRY_TAG_RE.fullmatch(item) is not None
                    for item in raw_partners)
            and len(set(raw_partners)) == len(raw_partners)
            and raw_partners == sorted(raw_partners)
            and annul_country not in raw_partners)
    checks["special_unique"] = all(
        len(items) <= 1 for items in special_terms.values())
    expected_country = context_actor if direction == "offer" else context_recipient
    expected_special_beneficiary = context_recipient if direction == "offer" else context_actor
    for special_id, items in special_terms.items():
        if items:
            checks["special_roles"] = checks["special_roles"] and (
                len(items) == 1
                and items[0].get("country") == expected_country
                and items[0].get("beneficiary") == expected_special_beneficiary
                and _COUNTRY_TAG_RE.fullmatch(str(items[0].get("country"))) is not None
                and _COUNTRY_TAG_RE.fullmatch(str(items[0].get("beneficiary"))) is not None
                and expected_country != expected_special_beneficiary)
    nonwhite_ids = {item for item in action_ids if item != "white_peace"}
    supported_ids = {"demand_ducats", "cede_province", "war_reparations",
                     "transfer_trade_power", "concede_defeat",
                     "annul_treaties", "humiliate_rival", "show_strength",
                     "force_religion"}
    checks["effect_scope_supported"] = (
        len(nonwhite_ids) <= 9 and nonwhite_ids <= supported_ids
        and checks["terms_shape"] and checks["reparations_roles"]
        and checks["reparations_unique"] and checks["trade_power_roles"]
        and checks["trade_power_unique"] and checks["concede_defeat_roles"]
        and checks["concede_defeat_unique"]
        and checks["annul_treaties_roles"]
        and checks["annul_treaties_unique"]
        and checks["special_roles"] and checks["special_unique"])
    return checks


def _trade_power_open_end(value: object) -> bool:
    """Recognize the native open-ended transfer-trade-power sentinel."""

    if type(value) is int:
        return value == _TRADE_POWER_OPEN_END_RAW
    if not isinstance(value, str):
        return False
    return value.strip().strip('"').casefold() in {"0x29c77f8", "43808760"}


def _public_effect_contract(
        final: object, decision: str,
        trade_power_pair: tuple[str, str] | None = None,
        ) -> dict[str, object]:
    """Check each requested effect, including money/province mixtures."""

    response = _find_public_response(final)
    context = response.get("peace_context") if isinstance(response, dict) else None
    context_checks = _peace_context_contract(context, decision, trade_power_pair)
    terms = context.get("terms") if isinstance(context, dict) else None
    terms = terms if isinstance(terms, list) else []
    r_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "war_reparations"]
    t_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "transfer_trade_power"]
    c_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "concede_defeat"]
    a_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "annul_treaties"]
    h_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "humiliate_rival"]
    s_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "show_strength"]
    f_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "force_religion"]
    m_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "demand_ducats"]
    p_terms = [term for term in terms if isinstance(term, dict)
               and term.get("action_id") == "cede_province"]
    if not r_terms and not t_terms and not c_terms and not a_terms and not h_terms and not s_terms and not f_terms and not m_terms and not p_terms:
        return {
            "applicable": False,
            "all": context_checks.get("effect_scope_supported") is True,
            "reason": "supported_effect_terms_not_requested",
            "checks": context_checks,
            "context": context,
        }

    effects = response.get("effects") if isinstance(response, dict) else None
    reparations = effects.get("war_reparations") \
        if isinstance(effects, dict) else None
    trade_power = effects.get("transfer_trade_power") \
        if isinstance(effects, dict) else None
    expected_payer = r_terms[0].get("payer") if r_terms else None
    expected_claimant = r_terms[0].get("claimant") if r_terms else None
    expected_source = t_terms[0].get("source") if t_terms else None
    expected_beneficiary = t_terms[0].get("beneficiary") if t_terms else None
    expected_conceding = c_terms[0].get("conceding_country") if c_terms else None
    expected_c_beneficiary = c_terms[0].get("beneficiary") if c_terms else None
    expected_annul_country = a_terms[0].get("country") if a_terms else None
    expected_annul_partners = a_terms[0].get("treaty_partners") if a_terms else []
    special_terms = [("humiliate_rival", h_terms), ("show_strength", s_terms),
                     ("force_religion", f_terms)]
    checks: dict[str, bool] = {
        "context_scope_supported": context_checks.get("effect_scope_supported") is True,
        "effects_object": isinstance(effects, dict),
        "effects_complete": isinstance(effects, dict) and effects.get("complete") is True,
        "effects_date_unchanged": isinstance(effects, dict)
        and effects.get("date_unchanged") is True,
        "effects_currency_scale": isinstance(effects, dict)
        and effects.get("currency_scale") == 1000,
        "effects_money_empty": (
            isinstance(effects, dict)
            and ((not m_terms and effects.get("money") is None)
                 or (m_terms and isinstance(effects.get("money"), dict)))),
        "effects_provinces_empty": isinstance(effects, dict)
        and ((not p_terms and effects.get("provinces") == [])
             or (p_terms and isinstance(effects.get("provinces"), list))),
        "outcome": isinstance(response, dict)
        and response.get("native_outcome") == (
            "accepted" if decision == "accept" else "rejected"),
        "terms_verified": isinstance(response, dict)
        and response.get("terms_verified") is (decision == "accept"),
    }
    if m_terms or p_terms:
        fields = ObserverSession._inbound_peace_context_fields(context, _ACTOR, _RECIPIENT)
        numeric_effects = dict(effects) if isinstance(effects, dict) else None
        if numeric_effects is not None and fields is not None:
            # The public projection retains nullable unrequested fields; the
            # strict native validator expects only selected optional objects.
            for key, requested in (
                    ("transfer_trade_power", fields["trade_power_requested"]),
                    ("concede_defeat", fields["concede_defeat_requested"]),
                    ("annul_treaties", fields["annul_treaties_requested"])):
                if not requested and numeric_effects.get(key) is None:
                    numeric_effects.pop(key, None)
        checks["money_province_full_effects"] = (
            fields is not None and not fields["beneficiary_ambiguous"]
            and ObserverSession._valid_native_peace_effects(
                numeric_effects, fields["direction"], fields["amount_raw"],
                fields["province_ids"], fields["beneficiary"], _ACTOR, _RECIPIENT,
                response.get("date_raw"), decision == "accept",
                reparations_payer=fields["reparations_payer"],
                reparations_claimant=fields["reparations_claimant"],
                reparations_requested=fields["reparations_requested"],
                trade_power_source=fields["trade_power_source"],
                trade_power_beneficiary=fields["trade_power_beneficiary"],
                trade_power_requested=fields["trade_power_requested"],
                concede_defeat_country=fields["concede_defeat_country"],
                concede_defeat_beneficiary=fields["concede_defeat_beneficiary"],
                concede_defeat_requested=fields["concede_defeat_requested"],
                annul_country=fields["annul_country"],
                annul_partners=fields["annul_partners"],
                annul_treaties_requested=fields["annul_treaties_requested"]))
    if r_terms:
        checks.update({
            "reparations_object": isinstance(reparations, dict),
            "reparations_pair": isinstance(reparations, dict)
            and reparations.get("payer") == expected_payer
            and reparations.get("claimant") == expected_claimant,
            "reparations_state_fields": isinstance(reparations, dict)
            and isinstance(reparations.get("active_before"), bool)
            and isinstance(reparations.get("active_after"), bool)
            and isinstance(reparations.get("verified"), bool),
        })
        if decision == "accept":
            checks.update({
                "reparations_verified": isinstance(reparations, dict)
                and reparations.get("verified") is True,
                "reparations_active_before": isinstance(reparations, dict)
                and reparations.get("active_before") is False,
                "reparations_active_after": isinstance(reparations, dict)
                and reparations.get("active_after") is True,
            })
        else:
            checks["reparations_verified"] = (
                isinstance(reparations, dict)
                and reparations.get("verified") is False)
    if t_terms:
        result_date = response.get("date_raw") if isinstance(response, dict) else None
        start_date = trade_power.get("start_date_raw") \
            if isinstance(trade_power, dict) else None
        end_date = trade_power.get("end_date_raw") \
            if isinstance(trade_power, dict) else None
        if decision == "accept":
            checks.update({
                "transfer_trade_power_object": isinstance(trade_power, dict),
                "transfer_trade_power_pair": (
                    isinstance(trade_power, dict)
                    and trade_power.get("source") == expected_source
                    and trade_power.get("beneficiary") == expected_beneficiary),
                "transfer_trade_power_present_before": (
                    isinstance(trade_power, dict)
                    and trade_power.get("present_before") is False),
                "transfer_trade_power_present_after": (
                    isinstance(trade_power, dict)
                    and trade_power.get("present_after") is True),
                "transfer_trade_power_start": (
                    type(start_date) is int and type(result_date) is int
                    and start_date <= result_date),
                "transfer_trade_power_end_sentinel": _trade_power_open_end(end_date),
                "transfer_trade_power_amount": (
                    isinstance(trade_power, dict)
                    and trade_power.get("amount_raw") == _TRADE_POWER_AMOUNT_RAW),
                "transfer_trade_power_scale": (
                    isinstance(trade_power, dict)
                    and trade_power.get("amount_scale") == _TRADE_POWER_AMOUNT_SCALE),
                "transfer_trade_power_peace_treaty": (
                    isinstance(trade_power, dict)
                    and trade_power.get("peace_treaty") is True),
                "transfer_trade_power_verified": (
                    isinstance(trade_power, dict)
                    and trade_power.get("verified") is True),
            })
        else:
            checks.update({
                "transfer_trade_power_object": isinstance(trade_power, dict),
                "transfer_trade_power_pair": (
                    isinstance(trade_power, dict)
                    and trade_power.get("source") == expected_source
                    and trade_power.get("beneficiary") == expected_beneficiary),
                "transfer_trade_power_present_before": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("present_before")) is bool),
                "transfer_trade_power_present_after": (
                    isinstance(trade_power, dict)
                    and trade_power.get("present_after") is False),
                "transfer_trade_power_dates": (
                    isinstance(trade_power, dict)
                    and type(start_date) is int and type(end_date) is int),
                "transfer_trade_power_amount": (
                    isinstance(trade_power, dict)
                    and trade_power.get("amount_raw") == 0),
                "transfer_trade_power_scale": (
                    isinstance(trade_power, dict)
                    and trade_power.get("amount_scale") in (0, _TRADE_POWER_AMOUNT_SCALE)),
                "transfer_trade_power_peace_treaty": (
                    isinstance(trade_power, dict)
                    and trade_power.get("peace_treaty") is False),
                "transfer_trade_power_verified": (
                    isinstance(trade_power, dict)
                    and trade_power.get("verified") is False),
            })
    concede = effects.get("concede_defeat") if isinstance(effects, dict) else None
    if c_terms:
        c_checks: dict[str, bool] = {
            "concede_defeat_object": isinstance(concede, dict),
            "concede_defeat_conceding_country": (
                isinstance(concede, dict)
                and concede.get("conceding_country") == expected_conceding),
            "concede_defeat_beneficiary": (
                isinstance(concede, dict)
                and concede.get("beneficiary") == expected_c_beneficiary),
            "concede_defeat_prestige_scale": (
                isinstance(concede, dict)
                and concede.get("prestige_scale") == 1000),
            "concede_defeat_values_readable": (
                isinstance(concede, dict)
                and concede.get("values_readable") is True),
            "concede_defeat_verified": (
                isinstance(concede, dict)
                and concede.get("verified") is (decision == "accept")),
        }
        c_fields = (
            "conceding_prestige_before_raw", "conceding_prestige_after_raw",
            "conceding_prestige_delta_raw", "beneficiary_prestige_before_raw",
            "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw")
        c_checks.update({
            f"concede_defeat_{field}": (
                isinstance(concede, dict)
                and type(concede.get(field)) is int
                and not isinstance(concede.get(field), bool))
            for field in c_fields
        })
        c_checks.update({
            "concede_defeat_conceding_delta_consistent": (
                isinstance(concede, dict)
                and type(concede.get("conceding_prestige_before_raw")) is int
                and type(concede.get("conceding_prestige_after_raw")) is int
                and type(concede.get("conceding_prestige_delta_raw")) is int
                and concede.get("conceding_prestige_delta_raw") ==
                concede.get("conceding_prestige_after_raw") -
                concede.get("conceding_prestige_before_raw")),
            "concede_defeat_beneficiary_delta_consistent": (
                isinstance(concede, dict)
                and type(concede.get("beneficiary_prestige_before_raw")) is int
                and type(concede.get("beneficiary_prestige_after_raw")) is int
                and type(concede.get("beneficiary_prestige_delta_raw")) is int
                and concede.get("beneficiary_prestige_delta_raw") ==
                concede.get("beneficiary_prestige_after_raw") -
                concede.get("beneficiary_prestige_before_raw")),
        })
        checks.update(c_checks)
    annul_effects = effects.get("annul_treaties") if isinstance(effects, dict) else None
    requested_pairs = [(expected_annul_country, partner)
                       for partner in expected_annul_partners
                       if isinstance(expected_annul_partners, list)]
    if a_terms:
        rows = annul_effects if isinstance(annul_effects, list) else []
        row_pairs = [(row.get("country"), row.get("partner"))
                     for row in rows if isinstance(row, dict)]
        a_checks: dict[str, bool] = {
            "annul_treaties_object": isinstance(annul_effects, list),
            "annul_treaties_pairs_exact": (
                len(rows) == len(requested_pairs)
                and len(row_pairs) == len(set(row_pairs))
                and set(row_pairs) == set(requested_pairs)),
        }
        for index, pair in enumerate(requested_pairs):
            row = next((item for item in rows
                        if isinstance(item, dict)
                        and (item.get("country"), item.get("partner")) == pair), None)
            prefix = f"annul_treaties_{index}"
            a_checks.update({
                f"{prefix}_country": isinstance(row, dict) and row.get("country") == pair[0],
                f"{prefix}_partner": isinstance(row, dict) and row.get("partner") == pair[1],
                f"{prefix}_present_before": isinstance(row, dict) and type(row.get("present_before")) is bool,
                f"{prefix}_present_after": isinstance(row, dict) and type(row.get("present_after")) is bool,
                f"{prefix}_start_date": isinstance(row, dict) and type(row.get("start_date_raw")) is int,
                f"{prefix}_end_date": isinstance(row, dict) and type(row.get("end_date_raw")) is int,
                f"{prefix}_alliance_before": isinstance(row, dict) and type(row.get("alliance_before")) is bool,
                f"{prefix}_alliance_after": isinstance(row, dict) and type(row.get("alliance_after")) is bool,
                f"{prefix}_values_readable": isinstance(row, dict) and row.get("values_readable") is True,
                f"{prefix}_verified": isinstance(row, dict) and row.get("verified") is (decision == "accept"),
            })
            if decision == "accept":
                a_checks[f"{prefix}_applied"] = (
                    isinstance(row, dict)
                    and row.get("present_after") is True
                    and row.get("alliance_after") is False)
        checks.update(a_checks)
    for special_id, requested_terms in special_terms:
        if not requested_terms:
            continue
        effect = effects.get(special_id) if isinstance(effects, dict) else None
        expected_country = requested_terms[0].get("country")
        expected_beneficiary = requested_terms[0].get("beneficiary")
        prefix = special_id
        required_fields = (
            "country", "beneficiary", "values_readable", "verified")
        special_checks: dict[str, bool] = {
            f"{prefix}_object": isinstance(effect, dict),
            f"{prefix}_country": isinstance(effect, dict)
            and effect.get("country") == expected_country,
            f"{prefix}_beneficiary": isinstance(effect, dict)
            and effect.get("beneficiary") == expected_beneficiary,
            f"{prefix}_values_readable": isinstance(effect, dict)
            and effect.get("values_readable") is True,
            f"{prefix}_verified": isinstance(effect, dict)
            and effect.get("verified") is (decision == "accept"),
        }
        if special_id in {"humiliate_rival", "show_strength"}:
            prestige_fields = (
                "country_prestige_before_raw", "country_prestige_after_raw",
                "country_prestige_delta_raw", "beneficiary_prestige_before_raw",
                "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw")
            special_checks[f"{prefix}_prestige_scale"] = (
                isinstance(effect, dict)
                and effect.get("prestige_scale",
                               effect.get("prestige_scale1000")) == 1000)
            special_checks[f"{prefix}_humiliated_before"] = (
                isinstance(effect, dict) and isinstance(effect.get("humiliated_before"), bool))
            special_checks[f"{prefix}_humiliated_after"] = (
                isinstance(effect, dict) and isinstance(effect.get("humiliated_after"), bool))
            for field in prestige_fields:
                special_checks[f"{prefix}_{field}"] = (
                    isinstance(effect, dict) and type(effect.get(field)) is int
                    and not isinstance(effect.get(field), bool))
            if isinstance(effect, dict):
                special_checks[f"{prefix}_country_delta_consistent"] = (
                    effect.get("country_prestige_delta_raw") ==
                    effect.get("country_prestige_after_raw") -
                    effect.get("country_prestige_before_raw"))
                special_checks[f"{prefix}_beneficiary_delta_consistent"] = (
                    effect.get("beneficiary_prestige_delta_raw") ==
                    effect.get("beneficiary_prestige_after_raw") -
                    effect.get("beneficiary_prestige_before_raw"))
            if decision == "accept":
                special_checks[f"{prefix}_applied"] = (
                    isinstance(effect, dict) and effect.get("humiliated_after") is True)
        if special_id == "show_strength":
            for field in ("powers_before", "powers_after", "powers_delta"):
                special_checks[f"{prefix}_{field}"] = (
                    isinstance(effect, dict) and isinstance(effect.get(field), list)
                    and len(effect[field]) == 3
                    and all(type(value) is int and not isinstance(value, bool)
                            for value in effect[field]))
            special_checks[f"{prefix}_powers_requested"] = (
                isinstance(effect, dict) and type(effect.get("powers_requested")) is int
                and effect.get("powers_requested") >= 0)
        if special_id == "force_religion":
            religion_re = re.compile(r"^[A-Za-z0-9_]{0,63}$")
            for field in ("religion_before", "religion_after",
                          "beneficiary_religion_before", "beneficiary_religion_after",
                          "capital_religion_before", "capital_religion_after"):
                special_checks[f"{prefix}_{field}"] = (
                    isinstance(effect, dict)
                    and isinstance(effect.get(field), str)
                    and religion_re.fullmatch(effect[field]) is not None)
            if decision == "accept" and isinstance(effect, dict):
                special_checks[f"{prefix}_religion_applied"] = (
                    effect.get("religion_after") == effect.get("beneficiary_religion_after")
                    and effect.get("capital_religion_after") == effect.get("beneficiary_religion_after"))
        checks.update(special_checks)
    return {
        "applicable": True,
        "all": all(checks.values()),
        "reason": "peace_effect_contract",
        "checks": checks,
        "context": context,
        "effects": effects,
        "reparations_pair": (
            (expected_payer, expected_claimant) if r_terms else None),
        "trade_power_pair": (
            (expected_source, expected_beneficiary) if t_terms else None),
        "concede_defeat_pair": (
            (expected_conceding, expected_c_beneficiary) if c_terms else None),
        "annul_treaties_pairs": requested_pairs if a_terms else [],
    }


def _inspection_contract(inspection: object, proposal_id: str,
                         decision: str,
                         trade_power_pair: tuple[str, str] | None = None,
                         ) -> dict[str, bool]:
    """Check the public binding and the Peace-specific war precondition."""

    if not isinstance(inspection, dict):
        return {"object": False, "binding": False, "war_before": False,
                "response_rules": False, "payload": False,
                "preflight_available": False}
    parameters = inspection.get("parameters")
    requested = parameters.get("requested") if isinstance(parameters, dict) else None
    actual = parameters.get("actual") if isinstance(parameters, dict) else None
    legality = inspection.get("legality")
    authorization = inspection.get("authorization")
    context_checks = _peace_context_contract(
        inspection.get("peace_context"), decision, trade_power_pair)
    return {
        "object": True,
        "binding": (
            inspection.get("action_id") == _ACTION
            and inspection.get("family") == _FAMILY
            and inspection.get("actor") == _ACTOR
            and inspection.get("recipient") == _RECIPIENT
            and inspection.get("phase") == decision
            and isinstance(requested, dict)
            and requested.get("proposal_id") == proposal_id
            and (actual is None or (
                isinstance(actual, dict) and actual.get("proposal_id") == proposal_id))
            and inspection.get("decision_country") == _RECIPIENT
            and inspection.get("decision_country_verified") is True
        ),
        "war_before": inspection.get("war_before") is True,
        "response_rules": (
            isinstance(inspection.get("native_inbound_inspection"), dict)
            and inspection["native_inbound_inspection"].get("response_rules_complete") is True
        ),
        "payload": (
            inspection.get("peace_payload_complete") is True
            and inspection.get("selected_terms_complete") is True
        ),
        "preflight_available": (
            isinstance(legality, dict) and legality.get("status") == "available"
            and isinstance(authorization, dict)
            and authorization.get("status") == "available"
        ),
        "peace_context": all(context_checks.values()),
        "peace_context_identity": context_checks["identity"],
        "peace_context_terms": context_checks["terms_shape"],
        "peace_reparations_roles": context_checks["reparations_roles"],
        "peace_trade_power_roles": context_checks["trade_power_roles"],
        "peace_concede_defeat_roles": context_checks["concede_defeat_roles"],
        "peace_annul_treaties_roles": context_checks["annul_treaties_roles"],
        "effect_scope_supported": context_checks["effect_scope_supported"],
    }


def _read_events(path: Path) -> list[dict[str, object]]:
    """Read at most one bounded, newline-delimited native-log slice."""

    events: list[dict[str, object]] = []
    if not path.is_file():
        return events
    consumed = 0
    pending = b""
    with path.open("rb") as stream:
        while consumed < _MAX_LOG_BYTES:
            chunk = stream.read(min(64 * 1024, _MAX_LOG_BYTES - consumed))
            if not chunk:
                break
            consumed += len(chunk)
            pending += chunk
            lines = pending.split(b"\n")
            pending = lines.pop()
            for raw in lines:
                if not raw or len(raw) > _MAX_LINE_BYTES:
                    continue
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    events.append(value)
    return events


def _pending_roles_from_log(path: Path, session_id: str) -> tuple[str, str] | None:
    """Derive the pending Peace roles from the current native observation."""

    for event in reversed(_read_events(path)):
        if (event.get("session_id") == session_id
                and event.get("event") == "native_alliance_inbound_offer"
                and event.get("family") == _FAMILY
                and isinstance(event.get("actor"), str)
                and isinstance(event.get("recipient"), str)
                and event.get("actor") != event.get("recipient")
                and event.get("decision_country") == event.get("recipient")):
            return str(event["actor"]), str(event["recipient"])
    return None


def _run_role_snapshots(session: ObserverSession, output: Path,
                        target: str) -> dict[str, dict[str, object]]:
    """Run the reviewed probes with the actual FRA/target pair bound."""

    previous = os.environ.get("EU4_WAR_PAIR_RECIPIENT")
    os.environ["EU4_WAR_PAIR_RECIPIENT"] = target
    try:
        return _run_snapshots(session, output)
    finally:
        if previous is None:
            os.environ.pop("EU4_WAR_PAIR_RECIPIENT", None)
        else:
            os.environ["EU4_WAR_PAIR_RECIPIENT"] = previous


def _event_matches(event: object, request_id: str, session_id: str,
                   decision: str, *, require_action: bool = True) -> bool:
    if not isinstance(event, dict):
        return False
    if (event.get("request_id") != request_id
            or event.get("session_id") != session_id
            or event.get("phase") != decision):
        return False
    if require_action and event.get("action_id") != _ACTION:
        return False
    if event.get("action_id") not in (None, _ACTION):
        return False
    if event.get("family") not in (None, _FAMILY):
        return False
    if event.get("actor") not in (None, _ACTOR):
        return False
    if event.get("recipient") not in (None, _RECIPIENT):
        return False
    return True


def _bool_from_events(events: list[dict[str, object]], keys: tuple[str, ...]) -> bool | None:
    for event in events:
        for key in keys:
            value = event.get(key)
            if isinstance(value, bool):
                return value
            if key.endswith("_count") and isinstance(value, int) and not isinstance(value, bool):
                return value > 0
    return None


def _payload_complete_from_events(events: list[dict[str, object]]) -> bool | None:
    direct = _bool_from_events(events, (
        "peace_payload_complete", "payload_complete", "native_payload_complete",
        "response_payload_complete", "source_payload_complete", "full_payload",
    ))
    if direct is not None:
        return direct
    for event in events:
        for key in ("peace_payload", "payload", "source_payload", "loaded_payload"):
            payload = event.get(key)
            if isinstance(payload, dict) and isinstance(payload.get("complete"), bool):
                return payload.get("complete")
    return None


def _native_response_contract(events: list[dict[str, object]], request_id: str,
                             session_id: str, decision: str) -> dict[str, object]:
    response_events = [
        event for event in events
        if event.get("event") in _RESPONSE_EVENTS
        and _event_matches(event, request_id, session_id, decision)
    ]
    handler_events = [
        event for event in events
        if (event.get("event") in _HANDLER_EVENTS
            or (isinstance(event.get("event"), str)
                and event["event"].startswith("native_peace_")
                and ("response" in event["event"] or "handler" in event["event"])))
        and _event_matches(event, request_id, session_id, decision,
                           require_action=False)
    ]
    response = response_events[0] if response_events else None
    handler_pool = handler_events + response_events
    expected_after = decision == "reject"
    response_contract = (
        isinstance(response, dict)
        and response.get("action_id") == _ACTION
        and response.get("family") == _FAMILY
        and response.get("actor") == _ACTOR
        and response.get("recipient") == _RECIPIENT
        and response.get("response_verified") is True
        and response.get("request_binding_verified") is True
        and response.get("pending_removed") is True
        and response.get("war_before") is True
        and response.get("war_after") is expected_after
    )
    forwarded = _bool_from_events(handler_pool, (
        "handler_forwarded", "native_handler_forwarded", "native_forwarded",
        "forwarded", "call_redirected", "native_forward_count", "forward_count",
    ))
    consumed = _bool_from_events(handler_pool, (
        "handler_consumed", "native_handler_consumed", "response_consumed",
        "pending_consumed", "consumed", "native_consume_count", "consume_count",
    ))
    payload_complete = _payload_complete_from_events(handler_pool)
    return {
        "response_event": response,
        "response_event_count": len(response_events),
        "handler_event_count": len(handler_events),
        "response_event_contract": response_contract,
        "response_verified": isinstance(response, dict)
        and response.get("response_verified") is True,
        "request_binding_verified": isinstance(response, dict)
        and response.get("request_binding_verified") is True,
        "pending_removed": isinstance(response, dict)
        and response.get("pending_removed") is True,
        "war_before": isinstance(response, dict) and response.get("war_before") is True,
        "war_after": (response.get("war_after") if isinstance(response, dict) else None),
        "handler_event_present": bool(handler_events) or any(
            key in response for key in (
                "handler_forwarded", "handler_consumed", "native_forwarded",
                "native_handler_consumed", "payload_complete",
                "peace_payload_complete")
        ) if isinstance(response, dict) else bool(handler_events),
        "handler_forwarded": forwarded is True,
        "handler_consumed": consumed is True,
        "full_payload": payload_complete is True,
        "contract": (
            response_contract and forwarded is True and consumed is True
            and payload_complete is True
        ),
    }


def _find_public_response(final: object) -> dict[str, object] | None:
    """Find the public response projection without treating inspection as result."""

    pending: list[object] = [final]
    seen: set[int] = set()
    while pending:
        value = pending.pop(0)
        if not isinstance(value, dict) or id(value) in seen:
            continue
        seen.add(id(value))
        if (value.get("action_id") == _ACTION
                and ("war_before" in value or "war_after" in value
                     or "pending_removed" in value)):
            return value
        for key in ("result", "response", "native_result"):
            child = value.get(key)
            if isinstance(child, dict):
                pending.append(child)
    return None


def _public_response_contract(final: object, decision: str,
                              proposal_id: str,
                              trade_power_pair: tuple[str, str] | None = None,
                              ) -> dict[str, bool]:
    response = _find_public_response(final)
    expected_after = decision == "reject"
    effect_contract = _public_effect_contract(
        final, decision, trade_power_pair)
    return {
        "object": isinstance(response, dict),
        "action_and_family": isinstance(response, dict)
        and response.get("action_id") == _ACTION
        and response.get("family") == _FAMILY,
        "proposal_id_bound": isinstance(response, dict)
        and response.get("proposal_id", proposal_id) == proposal_id,
        "war_before": isinstance(response, dict) and response.get("war_before") is True,
        "war_after": isinstance(response, dict)
        and response.get("war_after") is expected_after,
        "pending_removed": isinstance(response, dict)
        and response.get("pending_removed") is True,
        "response_verified": isinstance(response, dict)
        and response.get("response_verified") is True
        and response.get("request_binding_verified") is True,
        "peace_context": isinstance(effect_contract.get("checks"), dict)
        and effect_contract.get("checks", {}).get("context_scope_supported") is True
        if effect_contract.get("applicable") is True else (
            isinstance(effect_contract.get("checks"), dict)
            and effect_contract.get("checks", {}).get("effect_scope_supported") is True),
        "effects_contract": effect_contract.get("all") is True,
    }


def _war_pair_summary(probes: object, actor: str | None = None,
                      recipient: str | None = None) -> dict[str, object]:
    """Extract the actual Peace pair from the bounded war-probe schema."""

    actor = actor or _ACTOR
    recipient = recipient or _RECIPIENT
    if not isinstance(probes, dict):
        return {"complete": False, "actor": actor, "recipient": recipient,
                "fra_pair_at_war": None, "eng_pair_at_war": None,
                "actor_pair_at_war": None, "recipient_pair_at_war": None,
                "pair_at_war": None}
    entry = probes.get("war_state")
    snapshot = entry.get("snapshot") if isinstance(entry, dict) else None
    countries = snapshot.get("countries") if isinstance(snapshot, dict) else None
    if not isinstance(countries, list):
        return {"complete": False, "actor": actor, "recipient": recipient,
                "fra_pair_at_war": None, "eng_pair_at_war": None,
                "actor_pair_at_war": None, "recipient_pair_at_war": None,
                "pair_at_war": None}
    by_slot: dict[int, dict[str, object]] = {}
    by_tag: dict[str, dict[str, object]] = {}
    for country in countries:
        if not isinstance(country, dict):
            continue
        slot = country.get("slot")
        if isinstance(slot, int) and not isinstance(slot, bool):
            by_slot[slot] = country
        tag = country.get("tag")
        if isinstance(tag, str):
            by_tag[tag] = country
    # Current probe emits tags; the slot fallback preserves old ENG/FRA
    # artifacts produced before the dynamic pair probe was added.
    fra = by_tag.get("FRA") or by_slot.get(122)
    eng = by_tag.get("ENG") or by_slot.get(46)
    actor_row = by_tag.get(actor)
    recipient_row = by_tag.get(recipient)
    if actor_row is None and actor == "ENG":
        actor_row = eng
    if recipient_row is None and recipient == "FRA":
        recipient_row = fra
    fra_value = fra.get("pair_at_war") if isinstance(fra, dict) else None
    eng_value = eng.get("pair_at_war") if isinstance(eng, dict) else None
    actor_value = actor_row.get("pair_at_war") if isinstance(actor_row, dict) else None
    recipient_value = recipient_row.get("pair_at_war") if isinstance(recipient_row, dict) else None
    complete = type(actor_value) is bool and type(recipient_value) is bool
    return {
        "complete": complete,
        "actor": actor,
        "recipient": recipient,
        "actor_pair_at_war": actor_value,
        "recipient_pair_at_war": recipient_value,
        "fra_pair_at_war": fra_value,
        "eng_pair_at_war": eng_value,
        "pair_at_war": (actor_value is True and recipient_value is True)
        if complete else None,
        "both_pair_at_peace": snapshot.get("both_pair_at_peace")
        if isinstance(snapshot, dict) else None,
    }


def _wait_for_catalog(api: DiplomacyTools, seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + seconds
    catalog: dict[str, object] = {}
    while time.monotonic() < deadline:
        value = api.list_diplomatic_actions(recipient=_RECIPIENT)
        catalog = _public_catalog(value)
        if not _peace_proposals(catalog):
            break
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    return catalog


def _output_paths(output: Path) -> tuple[Path, Path]:
    report_path = output.expanduser().resolve()
    if report_path.exists():
        raise PeaceInboundResponseError("OUTPUT_EXISTS", str(report_path))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = report_path.parent / f"{report_path.stem}-evidence"
    if artifact.exists():
        raise PeaceInboundResponseError("EVIDENCE_DIRECTORY_EXISTS", str(artifact))
    artifact.mkdir()
    return report_path, artifact


def main(argv: list[str] | None = None) -> int:
    global _ACTOR, _RECIPIENT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--decision", choices=("accept", "reject"), required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--trade-power-source", default=None,
                        help="可选的 transfer_trade_power source 绑定，例如 FRA")
    parser.add_argument("--trade-power-beneficiary", default=None,
                        help="可选的 transfer_trade_power beneficiary 绑定，例如 ENG")
    parser.add_argument("--output", type=Path, required=True,
                        help="unique report JSON path; sibling evidence directory is created")
    args = parser.parse_args(argv)
    if _REQUEST_ID_RE.fullmatch(args.request_id) is None:
        parser.error("request-id must contain only ASCII letters, digits, '_' or '-' (1..64)")
    if bool(args.trade_power_source) != bool(args.trade_power_beneficiary):
        parser.error("trade-power-source and trade-power-beneficiary must be supplied together")
    trade_power_pair: tuple[str, str] | None = None
    if args.trade_power_source is not None:
        if (_COUNTRY_TAG_RE.fullmatch(args.trade_power_source) is None
                or _COUNTRY_TAG_RE.fullmatch(args.trade_power_beneficiary) is None
                or args.trade_power_source == args.trade_power_beneficiary):
            parser.error("trade-power source and beneficiary must be distinct country tags")
        trade_power_pair = args.trade_power_source, args.trade_power_beneficiary

    try:
        output, artifact = _output_paths(args.output)
    except PeaceInboundResponseError as error:
        parser.error(f"{error.code}: {error.message}")
    installation = args.installation.expanduser().resolve(strict=True)
    log = installation.parent / "control-probe.jsonl"
    report: dict[str, object] = {
        "validator": Path(__file__).name,
        "version": 1,
        "status": "running",
        "mode": "public_peace_inbound_response",
        "installation_path": str(installation),
        "output": str(output),
        "artifact": str(artifact),
        "action_id": _ACTION,
        "family": _FAMILY,
        "proposer": None,
        "actor": None,
        "recipient": None,
        "decision": args.decision,
        "request_id": args.request_id,
        "trade_power_source": args.trade_power_source,
        "trade_power_beneficiary": args.trade_power_beneficiary,
        "execute_call_count": 0,
        "request_publish_count": 0,
        "checks": {},
    }
    session: ObserverSession | None = None
    log_start: int | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    before_catalog: dict[str, object] | None = None
    after_catalog: dict[str, object] | None = None
    proposal: dict[str, object] | None = None
    inspection: dict[str, object] | None = None
    execution: dict[str, object] | None = None
    final: dict[str, object] | None = None
    try:
        session = ObserverSession(installation, game_exe())
        report["installation"] = _sha256_file(installation)
        manifest = installation.parent / "build-manifest.json"
        if manifest.is_file():
            report["manifest"] = _sha256_file(manifest)
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        report.update(_installation_binding(installation))
        log_start = log.stat().st_size
        report["log_start_offset"] = log_start
        health = wait_runtime_ready(session, restore_minimized=True)
        # The native pending record is available before the public catalog is
        # opened.  Use it to bind the war probe to LEI (or the legacy ENG
        # proposer) instead of silently reading the ENG slot.
        pending_roles = _pending_roles_from_log(log, session.session_id)
        if pending_roles is not None:
            _ACTOR, _RECIPIENT = pending_roles
            report["proposer"] = _ACTOR
            report["actor"], report["recipient"] = _ACTOR, _RECIPIENT
        before_probe_target = _ACTOR
        before = _run_role_snapshots(session, artifact / "before-probes", _ACTOR)
        before_control = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "health": health,
            "control": before_control,
            "probes": _public_probe_records(before),
        }
        if (health.get("status") != "ready"
                or not _snapshots_complete(before)
                or before_control.get("player_slot") != _PLAYER_SLOT
                or before_control.get("paused_flag") != 1
                or health.get("date_raw") != before_control.get("date_raw")):
            raise PeaceInboundResponseError(
                "BASELINE_NOT_READY_POR_PAUSED",
                "before probes did not prove a paused POR session at one date")
        if "native_inbound_peace_response" not in session.installation_capabilities():
            raise PeaceInboundResponseError(
                "INBOUND_PEACE_RESPONSE_CAPABILITY_MISSING",
                "installation does not advertise the Peace inbound-response adapter")

        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            try:
                journal.lookup_request(args.request_id)
            except UnknownRequestError:
                report["request_id_unique"] = True
            else:
                raise PeaceInboundResponseError(
                    "REQUEST_ID_NOT_UNIQUE", args.request_id)
            api = DiplomacyTools(journal, session)
            # Enumerate the bounded incoming catalog without assuming that
            # the proposer is ENG.  The observed row supplies both roles.
            before_catalog = _public_catalog(api.list_diplomatic_actions())
            _write_json(artifact / "before-proposals.json", before_catalog)
            deadline = time.monotonic() + _DISCOVERY_SECONDS
            matches: list[dict[str, object]] = []
            while time.monotonic() < deadline:
                catalog = _public_catalog(api.list_diplomatic_actions())
                matches = _peace_proposals(catalog)
                if matches:
                    break
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
            if len(matches) != 1 or not _proposal_contract(matches[0]):
                raise PeaceInboundResponseError(
                    "UNIQUE_PEACE_PROPOSAL_NOT_FOUND",
                    f"expected one valid observed peace_offer, found {len(matches)}")
            proposal = matches[0]
            # Bind every subsequent inspection, response, native-event and
            # effect check to the actual pending row.  This is deliberately
            # derived from the catalog/context, rather than a CLI role hint.
            observed_actor = proposal.get("actor")
            observed_recipient = proposal.get("recipient")
            if (not isinstance(observed_actor, str)
                    or not isinstance(observed_recipient, str)):
                raise PeaceInboundResponseError(
                    "PROPOSAL_ROLES_UNREADABLE",
                    "pending peace proposal did not expose actor/recipient")
            _ACTOR, _RECIPIENT = observed_actor, observed_recipient
            report["proposer"] = _ACTOR
            report["actor"] = _ACTOR
            report["recipient"] = _RECIPIENT
            if before_probe_target != _ACTOR:
                # The log may lag the public catalog by one bounded poll;
                # replace only the read-only before snapshot with the actual
                # pair before any response call is made.
                before = _run_role_snapshots(
                    session, artifact / "before-probes", _ACTOR)
                before_control = _control_summary(before["control_state"]["snapshot"])
                report["before"]["control"] = before_control
                report["before"]["probes"] = _public_probe_records(before)
            proposal_id = proposal["proposal_id"]
            report["proposal"] = proposal
            parameters = {"proposal_id": proposal_id}
            inspection = api.inspect_diplomatic_action(
                _ACTION, _ACTOR, _RECIPIENT, phase=args.decision,
                parameters=parameters)
            _write_json(artifact / "inspection.json", inspection)
            report["inspection"] = inspection
            inspection_checks = _inspection_contract(
                inspection, proposal_id, args.decision, trade_power_pair)
            report["inspection_checks"] = inspection_checks
            if not all(inspection_checks.values()):
                raise PeaceInboundResponseError(
                    "PEACE_INSPECTION_CONTRACT_INCOMPLETE",
                    json.dumps(inspection_checks, sort_keys=True))
            execution = api.execute_diplomatic_action(
                args.request_id, _ACTION, _ACTOR, _RECIPIENT,
                phase=args.decision, parameters=parameters)
            report["execute_call_count"] = 1
            report["request_publish_count"] = 1 if execution.get("submitted") is True else 0
            _write_json(artifact / "execution.json", execution)
            report["execution"] = execution
            if execution.get("submitted") is True:
                poll = _poll_result(api, args.request_id)
            else:
                poll = {"calls": 1, "status_history": [execution.get("status")],
                        "terminal": False,
                        "final": api.get_diplomatic_result(args.request_id)}
            report["poll"] = poll
            final = poll.get("final") if isinstance(poll, dict) else None
            if not isinstance(final, dict):
                final = api.get_diplomatic_result(args.request_id)
            _write_json(artifact / "result.json", final)
            report["result"] = final
            report["public_response"] = _find_public_response(final)
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as reopened:
            persisted = DiplomacyTools(reopened, session).get_diplomatic_result(
                args.request_id)
        report["persisted"] = persisted
        # Re-open a proper journal for the removal observation so the SQLite
        # connection is always closed deterministically.
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as after_journal:
            after_catalog = _wait_for_catalog(
                DiplomacyTools(after_journal, session), _REMOVAL_SECONDS)
        _write_json(artifact / "after-proposals.json", after_catalog)
        report["after_proposals"] = after_catalog
        report["after_pending_matches"] = _peace_proposals(after_catalog)
        after = _run_role_snapshots(session, artifact / "after-probes", _ACTOR)
        after_control = _control_summary(after["control_state"]["snapshot"])
        report["after"] = {
            "health": session.health(),
            "control": after_control,
            "probes": _public_probe_records(after),
        }
    except PeaceInboundResponseError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:  # keep a reviewable artifact for bridge failures
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
            native_path = artifact / "native-events-slice.jsonl"
            events = _read_events(native_path)
            session_id = session.session_id if session is not None else ""
            native = _native_response_contract(
                events, args.request_id, session_id, args.decision)
            report["native_response"] = native
        else:
            report["native_events"] = {
                "status": "not_started",
                "path": str(artifact / "native-events-slice.jsonl"),
                "bytes": 0,
            }
            native = {"contract": False, "response_event_count": 0,
                      "handler_event_count": 0}
            report["native_response"] = native

        before_control = report.get("before", {}).get("control") \
            if isinstance(report.get("before"), dict) else None
        after_control = report.get("after", {}).get("control") \
            if isinstance(report.get("after"), dict) else None
        public = report.get("public_response")
        public_checks = _public_response_contract(
            report.get("result"), args.decision,
            proposal.get("proposal_id") if isinstance(proposal, dict)
            else "", trade_power_pair)
        report["public_response_checks"] = public_checks
        effect_contract = _public_effect_contract(
            report.get("result"), args.decision, trade_power_pair)
        report["result_contract"] = {
            "checks": {
                "public_response": all(public_checks.values()),
                "effects_contract": effect_contract.get("all") is True,
            },
            "all": all(public_checks.values()) and effect_contract.get("all") is True,
            "peace_context": effect_contract.get("context"),
            "effects": effect_contract.get("effects"),
            "effects_contract": effect_contract,
        }
        expected_outcome = "accepted" if args.decision == "accept" else "rejected"
        final_value = report.get("result")
        final_status = final_value.get("status") if isinstance(final_value, dict) else None
        final_game_outcome = (
            final_value.get("game_outcome") if isinstance(final_value, dict) else None)
        stability = _snapshot_stability(before, after) if before and after else {}
        report["snapshot_stability"] = stability
        report["war_state_transition"] = {
            "before": _war_pair_summary(before),
            "after": _war_pair_summary(after),
            "expected_pair_at_war_after": args.decision == "reject",
        }
        # Diplomat queues and ordinary alliance rows are recorded for review;
        # an accepted Peace response may legitimately change them, so neither
        # is converted into a no-delta assertion here.
        report["allowed_probe_deltas"] = {
            "alliance_state_unchanged": stability.get("alliance_state_unchanged"),
            "diplomats_unchanged": stability.get("diplomats_unchanged"),
            "war_state_unchanged": stability.get("war_state_unchanged"),
        }
        war_before_probe = report["war_state_transition"]["before"]
        war_after_probe = report["war_state_transition"]["after"]
        report["checks"] = {
            "request_id_unique": report.get("request_id_unique") is True,
            "before_four_probes_complete": before is not None and _snapshots_complete(before),
            "after_four_probes_complete": after is not None and _snapshots_complete(after),
            "inspection_contract": all(report.get("inspection_checks", {}).values())
            if isinstance(report.get("inspection_checks"), dict) else False,
            "peace_context_contract": (
                isinstance(report.get("result_contract"), dict)
                and report["result_contract"].get("effects_contract", {}).get("all") is True
                if isinstance(report.get("result_contract"), dict) else False),
            "result_effect_contract": (
                isinstance(report.get("result_contract"), dict)
                and report["result_contract"].get("all") is True
                if isinstance(report.get("result_contract"), dict) else False),
            "war_before": native.get("war_before") is True
            or public_checks.get("war_before") is True,
            "decision_outcome": final_status == expected_outcome
            and final_game_outcome == expected_outcome,
            "war_after": native.get("war_after") == (args.decision == "reject")
            or public_checks.get("war_after") is True,
            "war_state_transition": (
                isinstance(war_before_probe, dict)
                and isinstance(war_after_probe, dict)
                and war_before_probe.get("complete") is True
                and war_after_probe.get("complete") is True
                and war_before_probe.get("pair_at_war") is True
                and war_after_probe.get("pair_at_war")
                is (args.decision == "reject")
            ),
            # The native response is authoritative for queue removal.  The
            # public catalog is a bounded observer cursor and may retain a
            # previously seen opaque row, so keep that observation separate.
            "pending_removed": native.get("pending_removed") is True,
            "request_bound": native.get("request_binding_verified") is True
            and public_checks.get("response_verified") is True,
            "native_response_verified": native.get("response_verified") is True,
            "native_handler_forwarded": native.get("handler_forwarded") is True,
            "native_handler_consumed": native.get("handler_consumed") is True,
            "native_full_payload": native.get("full_payload") is True,
            "native_response_contract": native.get("contract") is True,
            "native_event_slice_complete": (
                isinstance(report.get("native_events"), dict)
                and report.get("native_events", {}).get("status") == "ok"
                and report.get("native_events", {}).get("complete") is True),
            "execute_once": report.get("execute_call_count") == 1,
            "poll_same_request": (
                isinstance(report.get("poll"), dict)
                and report.get("poll", {}).get("calls", 0) >= 1
                and report.get("request_id") == args.request_id),
            "por_paused_same_date": (
                isinstance(before_control, dict) and isinstance(after_control, dict)
                and before_control == after_control
                and before_control.get("player_slot") == _PLAYER_SLOT
                and before_control.get("paused_flag") == 1),
            # The current public catalog deliberately reports a bounded
            # observation as ``incoming_proposals_complete: false``.  The
            # removal claim is therefore bound to the native pending event
            # plus the successfully read public catalog, rather than treating
            # that bounded-catalog marker as a full-world enumeration claim.
            "public_pending_catalog_read": isinstance(after_catalog, dict),
        }
        if report.get("status") == "running":
            report["status"] = "passed" if all(report["checks"].values()) else "failed"
        _write_json(output, report)

    print(json.dumps({
        "status": report["status"],
        "report": str(output),
        "artifact": str(artifact),
        "request_id": args.request_id,
        "execute_call_count": report.get("execute_call_count"),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
