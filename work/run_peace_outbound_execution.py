#!/usr/bin/env python3
"""Execute one parameter-bound outbound Peace action through the public API.

The operator is deliberately single-use.  It discovers the one public
FRA--recipient war context, inspects the selected Peace payload, calls
``execute_diplomatic_action`` exactly once, and polls only that same request
identifier.  It never retries, advances time, saves, installs, or restarts
the game.  A non-terminal or contradictory native result remains unknown in
the report instead of being treated as success.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from bridge.peace_execution import normalize_peace_execution_parameters  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _sha256_file,
    _write_json,
)
from work.run_peace_authority_test import _snapshot_stability  # noqa: E402
from work.run_peace_empty_offer_queries import (  # noqa: E402
    _has_private_fields,
    _public_context_contract,
    _single_discovered_war_id,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_DEFAULT_RECIPIENT = "ENG"
_FAMILY = "peace"
_DISCOVERY_ACTION = "white_peace"
_TRADE_POWER_ACTION = "transfer_trade_power"
_CONCEDE_DEFEAT_ACTION = "concede_defeat"
_ANNUL_TREATIES_ACTION = "annul_treaties"
_HUMILIATE_RIVAL_ACTION = "humiliate_rival"
_SHOW_STRENGTH_ACTION = "show_strength"
_FORCE_RELIGION_ACTION = "force_religion"
_SPECIAL_ACTIONS = (_HUMILIATE_RIVAL_ACTION, _SHOW_STRENGTH_ACTION,
                    _FORCE_RELIGION_ACTION)
_ACTIONS = ("white_peace", "demand_ducats", "cede_province",
            "war_reparations", _TRADE_POWER_ACTION, _CONCEDE_DEFEAT_ACTION,
            _ANNUL_TREATIES_ACTION, *_SPECIAL_ACTIONS)
_DIRECTIONS = ("demand", "offer")
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_WAR_ID_RE = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_POLL_SECONDS = 20.0
_POLL_INTERVAL_SECONDS = 0.20
_MAX_NATIVE_EVENT_BYTES = 8 * 1024 * 1024
_MAX_PROVINCE_IDS = 16
_MIN_PROVINCE_ID = 1
_MAX_PROVINCE_ID = 2_147_483_647
_MAX_ANNUL_PARTNERS = 16


class PeaceExecutionError(RuntimeError):
    """A bounded preflight or report construction failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _recipient_arg(value: str) -> str:
    """Normalize a target tag while preserving the historical ENG default."""

    value = value.upper()
    if (len(value) != 3 or not value.isascii() or not value.isalnum()
            or value == _ACTOR):
        raise argparse.ArgumentTypeError(
            "recipient must be a three-character canonical tag other than FRA")
    return value


def _war_pair_summary_for(probes: object,
                          recipient: str | None = None) -> dict[str, object]:
    """Summarize the FRA/target pair from tag-bound read-only probe rows.

    The legacy probe only emitted reviewed FRA/ENG slots.  Keep that fallback
    for the default ENG run, while requiring explicit tag rows for a smaller
    target such as LEI so an ENG slot can never be mistaken for the target.
    """

    target = _RECIPIENT if recipient is None else recipient
    if not isinstance(probes, dict):
        return {"complete": False, "actor_pair_at_war": None,
                "recipient_pair_at_war": None, "pair_at_war": None,
                "actor": _ACTOR, "recipient": target}
    entry = probes.get("war_state")
    snapshot = entry.get("snapshot") if isinstance(entry, dict) else None
    countries = snapshot.get("countries") if isinstance(snapshot, dict) else None
    if not isinstance(countries, list):
        return {"complete": False, "actor_pair_at_war": None,
                "recipient_pair_at_war": None, "pair_at_war": None,
                "actor": _ACTOR, "recipient": target}
    by_tag = {
        item.get("tag"): item for item in countries
        if isinstance(item, dict) and isinstance(item.get("tag"), str)
    }
    by_slot = {
        item.get("slot"): item for item in countries
        if isinstance(item, dict) and isinstance(item.get("slot"), int)
    }
    actor = by_tag.get(_ACTOR)
    target_item = by_tag.get(target)
    if actor is None and _ACTOR == "FRA":
        actor = by_slot.get(122)
    if target_item is None and target == "ENG":
        target_item = by_slot.get(46)
    actor_value = actor.get("pair_at_war") if isinstance(actor, dict) else None
    target_value = (target_item.get("pair_at_war")
                    if isinstance(target_item, dict) else None)
    complete = type(actor_value) is bool and type(target_value) is bool
    result: dict[str, object] = {
        "complete": complete,
        "actor": _ACTOR,
        "recipient": target,
        "actor_pair_at_war": actor_value,
        "recipient_pair_at_war": target_value,
        "pair_at_war": (actor_value is True and target_value is True)
        if complete else None,
        "both_pair_at_peace": snapshot.get("both_pair_at_peace")
        if isinstance(snapshot, dict) else None,
    }
    # Preserve the old report labels for default ENG artifacts.
    if _ACTOR == "FRA":
        result["fra_pair_at_war"] = actor_value
    if target == "ENG":
        result["eng_pair_at_war"] = target_value
    return result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _output_paths(requested: Path) -> tuple[Path, Path]:
    """Create a new report/evidence location without overwriting artifacts."""

    target = requested.expanduser().resolve()
    if target.exists():
        raise PeaceExecutionError("OUTPUT_ALREADY_EXISTS", str(target))
    if target.suffix.casefold() == ".json":
        report_path = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        evidence = target
        report_path = target / "report.json"
    if evidence.exists() or report_path.exists():
        raise PeaceExecutionError("OUTPUT_ALREADY_EXISTS", str(report_path))
    evidence.mkdir(parents=True, exist_ok=False)
    return report_path, evidence


def _normalize_province_ids(value: object) -> list[int]:
    """Validate and preserve one bounded, duplicate-free province sequence."""

    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= _MAX_PROVINCE_IDS:
        raise PeaceExecutionError("PROVINCE_IDS_INVALID", str(value))
    result: list[int] = []
    for province_id in value:
        if (isinstance(province_id, bool)
                or not isinstance(province_id, int)
                or not _MIN_PROVINCE_ID <= province_id <= _MAX_PROVINCE_ID):
            raise PeaceExecutionError("PROVINCE_ID_INVALID", str(province_id))
        if province_id in result:
            raise PeaceExecutionError("PROVINCE_IDS_DUPLICATE", str(province_id))
        result.append(province_id)
    return result


def _parse_province_ids_csv(value: str) -> list[int]:
    """Parse ``--province-ids`` without silently dropping an empty token."""

    if not isinstance(value, str) or not value.strip():
        raise PeaceExecutionError("PROVINCE_IDS_INVALID", value)
    tokens = value.split(",")
    parsed: list[int] = []
    for token in tokens:
        token = token.strip()
        if not token:
            raise PeaceExecutionError("PROVINCE_IDS_INVALID", value)
        try:
            parsed.append(int(token, 0))
        except ValueError as error:
            raise PeaceExecutionError("PROVINCE_ID_INVALID", token) from error
    return _normalize_province_ids(parsed)


def _trade_power_source_for_direction(direction: str,
                                      source: str | None = None) -> str:
    """Return a canonical trade-power source without guessing third parties."""

    if direction not in _DIRECTIONS:
        raise PeaceExecutionError("PEACE_DIRECTION_INVALID", direction)
    if source is None:
        return _RECIPIENT if direction == "demand" else _ACTOR
    if not isinstance(source, str) or _TAG_RE.fullmatch(source) is None:
        raise PeaceExecutionError("TRADE_POWER_SOURCE_INVALID", str(source))
    return source


def _trade_power_term(direction: str,
                      source: str | None = None) -> dict[str, object]:
    """Build a trade-power term with an explicit or direction default source."""

    return {
        "action_id": _TRADE_POWER_ACTION,
        "source": _trade_power_source_for_direction(direction, source),
        "beneficiary": _ACTOR if direction == "demand" else _RECIPIENT,
    }


def _annul_treaties_term(country: str | None,
                         partners: list[str] | tuple[str, ...] | None,
                         ) -> dict[str, object]:
    """Build the bounded directed annul-treaties term.

    The native candidate list supplies the legal partners.  This helper only
    canonicalizes the operator's explicit selection and never invents a
    default partner.
    """

    if not isinstance(country, str) or _TAG_RE.fullmatch(country) is None:
        raise PeaceExecutionError("ANNUL_COUNTRY_INVALID", str(country))
    if not isinstance(partners, (list, tuple)) or not 1 <= len(partners) <= _MAX_ANNUL_PARTNERS:
        raise PeaceExecutionError("ANNUL_PARTNERS_INVALID", str(partners))
    normalized = [str(item).upper() for item in partners]
    if any(_TAG_RE.fullmatch(item) is None for item in normalized):
        raise PeaceExecutionError("ANNUL_PARTNER_INVALID", str(partners))
    if country in normalized:
        raise PeaceExecutionError("ANNUL_PARTNER_SELF", country)
    if len(set(normalized)) != len(normalized):
        raise PeaceExecutionError("ANNUL_PARTNERS_DUPLICATE", str(partners))
    if normalized != sorted(normalized):
        raise PeaceExecutionError("ANNUL_PARTNERS_UNSORTED", str(partners))
    return {
        "action_id": _ANNUL_TREATIES_ACTION,
        "country": country,
        "treaty_partners": normalized,
    }


def _special_term(action: str, direction: str, country: str | None = None,
                  beneficiary: str | None = None) -> dict[str, object]:
    """Build one direction-bound H/S/F term.

    The public API names the affected country ``country`` and the reference
    or beneficiary country ``beneficiary``.  Defaults follow the payer and
    claimant roles for the selected direction; native legality still decides
    whether the pair is a legal rival, strength target, or religion reference.
    """
    if action not in _SPECIAL_ACTIONS:
        raise PeaceExecutionError("SPECIAL_ACTION_INVALID", action)
    expected_country = _ACTOR if direction == "offer" else _RECIPIENT
    expected_beneficiary = _RECIPIENT if direction == "offer" else _ACTOR
    country = expected_country if country is None else str(country).upper()
    beneficiary = expected_beneficiary if beneficiary is None else str(beneficiary).upper()
    if (_TAG_RE.fullmatch(country) is None
            or _TAG_RE.fullmatch(beneficiary) is None
            or country == beneficiary):
        raise PeaceExecutionError("SPECIAL_PARTIES_INVALID",
                                  f"{country}/{beneficiary}")
    return {"action_id": action, "country": country,
            "beneficiary": beneficiary}


def _build_parameters(action_id: str, war_id: str, amount: str,
                      province_id: int | None, beneficiary: str | None = None,
                      direction: str = "demand", *,
                      province_ids: list[int] | tuple[int, ...] | None = None,
                      with_money: str | None = None,
                      with_reparations: bool = False,
                      with_trade_power: bool = False,
                      trade_power_source: str | None = None,
                      annul_country: str | None = None,
                      annul_partners: list[str] | tuple[str, ...] | None = None,
                      special_country: str | None = None,
                      special_beneficiary: str | None = None,
                      ) -> dict[str, object]:
    """Build and normalize the complete public execution parameter object."""

    if _WAR_ID_RE.fullmatch(war_id) is None:
        raise PeaceExecutionError("WAR_ID_INVALID", war_id)
    if direction not in _DIRECTIONS:
        raise PeaceExecutionError("PEACE_DIRECTION_INVALID", direction)
    if action_id not in _ACTIONS:
        raise PeaceExecutionError("ACTION_INVALID", action_id)
    if (special_country is not None or special_beneficiary is not None) \
            and action_id not in _SPECIAL_ACTIONS:
        raise PeaceExecutionError("SPECIAL_PARTIES_ACTION_INVALID",
                                  action_id)
    if trade_power_source is not None and not (
            action_id == _TRADE_POWER_ACTION or with_trade_power):
        raise PeaceExecutionError(
            "TRADE_POWER_SOURCE_ACTION_INVALID",
            "trade_power_source requires a transfer_trade_power term")
    if (annul_country is None) != (annul_partners is None):
        raise PeaceExecutionError(
            "ANNUL_TERM_INCOMPLETE",
            "annul_country and annul_partners must be supplied together")
    if action_id == _ANNUL_TREATIES_ACTION and (
            annul_country is None or annul_partners is None):
        raise PeaceExecutionError(
            "ANNUL_TERM_REQUIRED",
            "annul_treaties requires explicit annul_country and annul_partners")
    if action_id == "white_peace":
        if (with_money is not None or with_reparations
                or province_ids is not None or with_trade_power):
            raise PeaceExecutionError(
                "WHITE_PEACE_TERMS_INVALID",
                "white_peace cannot include money, provinces, reparations, or trade power")
        terms: list[dict[str, object]] = []
    elif action_id == "demand_ducats":
        if with_money is not None or province_ids is not None:
            raise PeaceExecutionError(
                "MONEY_PRIMARY_COMBINATION_INVALID",
                "demand_ducats cannot add a second money or province term")
        terms = [{
            "action_id": "demand_ducats",
            "amount": amount,
            "payer": _ACTOR if direction == "offer" else _RECIPIENT,
            "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
        }]
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if with_trade_power:
            terms.append(_trade_power_term(direction, trade_power_source))
    elif action_id == "cede_province":
        selected_ids = _normalize_province_ids(
            province_ids if province_ids is not None else [province_id])
        if beneficiary is None:
            beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
        if _TAG_RE.fullmatch(beneficiary) is None:
            raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats",
                "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        terms.append({
            "action_id": "cede_province",
            "province_ids": selected_ids,
            "beneficiary": beneficiary,
        })
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if with_trade_power:
            terms.append(_trade_power_term(direction, trade_power_source))
    elif action_id == "war_reparations":
        if with_reparations:
            raise PeaceExecutionError(
                "REPARATIONS_DUPLICATE_TERM",
                "war_reparations is already the primary term")
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats",
                "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if province_ids is not None:
            selected_ids = _normalize_province_ids(province_ids)
            if beneficiary is None:
                beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
            if _TAG_RE.fullmatch(beneficiary) is None:
                raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
            terms.append({
                "action_id": "cede_province",
                "province_ids": selected_ids,
                "beneficiary": beneficiary,
            })
        terms.append({
            "action_id": "war_reparations",
            "payer": _ACTOR if direction == "offer" else _RECIPIENT,
            "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
        })
        if with_trade_power:
            terms.append(_trade_power_term(direction, trade_power_source))
    elif action_id == _TRADE_POWER_ACTION:
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats",
                "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if province_ids is not None or province_id is not None:
            selected_ids = _normalize_province_ids(
                province_ids if province_ids is not None else [province_id])
            if beneficiary is None:
                beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
            if _TAG_RE.fullmatch(beneficiary) is None:
                raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
            terms.append({
                "action_id": "cede_province",
                "province_ids": selected_ids,
                "beneficiary": beneficiary,
            })
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        terms.append(_trade_power_term(direction, trade_power_source))
    elif action_id == _CONCEDE_DEFEAT_ACTION:
        # C is a direction-bound non-numeric term.  The native legality
        # predicate decides whether it may be combined with m/p/R/T; the
        # public request only needs the canonical parties and term order.
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats",
                "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if province_ids is not None or province_id is not None:
            selected_ids = _normalize_province_ids(
                province_ids if province_ids is not None else [province_id])
            if beneficiary is None:
                beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
            if _TAG_RE.fullmatch(beneficiary) is None:
                raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
            terms.append({
                "action_id": "cede_province",
                "province_ids": selected_ids,
                "beneficiary": beneficiary,
            })
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if with_trade_power:
            terms.append(_trade_power_term(direction, trade_power_source))
        terms.append({
            "action_id": _CONCEDE_DEFEAT_ACTION,
            "conceding_country": _ACTOR if direction == "offer" else _RECIPIENT,
            "beneficiary": _RECIPIENT if direction == "offer" else _ACTOR,
        })
    elif action_id == _ANNUL_TREATIES_ACTION:
        # The native legality predicate decides whether optional m/p/R/T/C
        # combinations are allowed.  The A term itself always comes last in
        # this normalized operator request.
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats", "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if province_ids is not None or province_id is not None:
            selected_ids = _normalize_province_ids(
                province_ids if province_ids is not None else [province_id])
            if beneficiary is None:
                beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
            if _TAG_RE.fullmatch(beneficiary) is None:
                raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
            terms.append({
                "action_id": "cede_province", "province_ids": selected_ids,
                "beneficiary": beneficiary,
            })
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if with_trade_power:
            terms.append(_trade_power_term(direction, trade_power_source))
        terms.append(_annul_treaties_term(annul_country, annul_partners))
    elif action_id in _SPECIAL_ACTIONS:
        # H/S/F are direction-bound non-numeric terms.  Native legality owns
        # rival, strength and religion conditions; optional m/p/R/T terms are
        # retained here so the canonical mask can represent mixed requests.
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats", "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if province_ids is not None or province_id is not None:
            selected_ids = _normalize_province_ids(
                province_ids if province_ids is not None else [province_id])
            if beneficiary is None:
                beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
            if _TAG_RE.fullmatch(beneficiary) is None:
                raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
            terms.append({
                "action_id": "cede_province", "province_ids": selected_ids,
                "beneficiary": beneficiary,
            })
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if with_trade_power:
            terms.append(_trade_power_term(direction, trade_power_source))
        terms.append(_special_term(action_id, direction, special_country,
                                   special_beneficiary))
    else:  # guarded above; keeps the type narrowing explicit for callers
        raise PeaceExecutionError("ACTION_INVALID", action_id)
    if action_id != _ANNUL_TREATIES_ACTION and annul_country is not None:
        terms.append(_annul_treaties_term(annul_country, annul_partners))
    raw = {
        "peace_context": {
            "war_id": war_id,
            "direction": direction,
            "terms": terms,
        }
    }
    try:
        normalized = normalize_peace_execution_parameters(
            action_id, _ACTOR, _RECIPIENT, "initiate", raw)
    except (TypeError, ValueError) as error:
        code = str(error.args[0]) if error.args else "PEACE_PARAMETERS_INVALID"
        raise PeaceExecutionError(code, str(error)) from error
    return normalized


def _query_parameters(action_id: str, execution_parameters: dict[str, object]) -> dict[str, object]:
    """Use the exact parameter shape for both inspection and execution.

    The public Peace adapter now routes an inspection with the complete
    executable context through its precise submission overlay.  Keeping the
    same object for inspection and execution prevents the white-peace legacy
    ``war_id + terms`` shape from being mistaken for an executable request.
    """
    return execution_parameters


def _selected_inspection_contract(value: object, action_id: str,
                                  query_parameters: dict[str, object],
                                  war_id: str) -> dict[str, object]:
    """Check the public selected Peace inspection without inferring legality."""

    if not isinstance(value, dict):
        return {"valid": False, "checks": {"object": False}}
    context = value.get("peace_context")
    session = value.get("session")
    interface = value.get("interface_support")
    checks: dict[str, bool] = {
        "object": True,
        "identity": all(value.get(key) == expected for key, expected in (
            ("action_id", action_id), ("actor", _ACTOR),
            ("recipient", _RECIPIENT), ("family", _FAMILY),
            ("phase", "initiate"))),
        "session_ready": isinstance(session, dict)
        and session.get("status") == "ready"
        and session.get("complete") is True,
        "native_query_interface": isinstance(interface, dict)
        and isinstance(interface.get("query"), str)
        and interface.get("query", "").startswith("native_peace_"),
        "context_object": isinstance(context, dict),
        "context_war_id": isinstance(context, dict)
        and context.get("war_id") == war_id,
        "context_complete": isinstance(context, dict)
        and context.get("complete") is True,
        "context_terms": isinstance(context, dict)
        and isinstance(context.get("terms"), list),
        "pair_at_war": value.get("pair_at_war") is True,
        "no_private_identifiers": not _has_private_fields(value),
        "parameters_recorded": (
            isinstance(value.get("parameters"), dict)
            and value["parameters"].get("requested") == query_parameters),
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "legality": value.get("legality"),
        "authorization": value.get("authorization"),
        "peace_context": context,
        "native_rule_components": value.get("native_rule_components"),
    }


def _poll_result(api: DiplomacyTools, request_id: str) -> dict[str, object]:
    """Poll one request journal entry; never calls execute again."""

    started = _utc_now()
    deadline = started + timedelta(seconds=_POLL_SECONDS)
    history: list[str] = []
    final: object = None
    calls = 0
    while _utc_now() < deadline:
        final = api.get_diplomatic_result(request_id)
        calls += 1
        status = final.get("status") if isinstance(final, dict) else None
        if isinstance(status, str) and (not history or history[-1] != status):
            history.append(status)
        if status in _TERMINAL_STATUSES:
            break
        remaining = max(0.0, (deadline - _utc_now()).total_seconds())
        if remaining <= 0:
            break
        time.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
    completed = _utc_now()
    return {
        "started_utc": _utc_text(started),
        "deadline_utc": _utc_text(deadline),
        "completed_utc": _utc_text(completed),
        "timeout_seconds": _POLL_SECONDS,
        "poll_interval_seconds": _POLL_INTERVAL_SECONDS,
        "calls": calls,
        "status_history": history,
        "terminal": isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES,
        "final": final,
    }


def _public_result(final: object) -> dict[str, object] | None:
    if not isinstance(final, dict):
        return None
    result = final.get("result")
    return result if isinstance(result, dict) else None


def _native_effect_observation(public: dict[str, object]) -> dict[str, object]:
    """Retain effect projections without imposing a schema before native work lands."""

    values = {
        key: public[key]
        for key in ("effects", "native_effects", "peace_effects")
        if key in public
    }
    return {
        "present": bool(values),
        "values": values,
        "schema_validation": "effects_v1",
    }


def _execution_province_ids(report: dict[str, object]) -> list[int]:
    """Extract the normalized cede list from an immutable report."""

    parameters = report.get("parameters")
    execution = parameters.get("execute") if isinstance(parameters, dict) else None
    context = execution.get("peace_context") if isinstance(execution, dict) else None
    terms = context.get("terms") if isinstance(context, dict) else None
    if not isinstance(terms, list):
        return []
    for term in terms:
        if not isinstance(term, dict) or term.get("action_id") != "cede_province":
            continue
        values = term.get("province_ids")
        if not isinstance(values, list):
            return []
        if any(type(value) is not int for value in values):
            return []
        if len(values) != len(set(values)):
            return []
        return list(values)
    return []


def _wire_submission_correlation(report: dict[str, object],
                                  event_path: Path | None = None
                                  ) -> dict[str, object]:
    """Correlate only the exact request/session native receipt.

    ``business_submission`` is the bridge/API acknowledgement.  The native
    receipt is a separate wire observation: a receipt with ``submitted=false``
    still proves that the request reached and was consumed by the DLL, while
    ``transport_verified`` and ``request_binding_verified`` describe whether
    the business transport was accepted.  No unrelated log line contributes
    to these counts.
    """

    metadata = report.get("native_events")
    if event_path is None:
        value = metadata.get("path") if isinstance(metadata, dict) else None
        event_path = Path(value).expanduser().resolve() if isinstance(value, str) else None
    session = report.get("session")
    session_id = session.get("session_id") if isinstance(session, dict) else None
    request_id = report.get("request_id")
    result: dict[str, object] = {
        "status": "unknown",
        "event_path": str(event_path) if event_path is not None else None,
        "session_id": session_id,
        "request_id": request_id,
        "private": True,
        "matching_event_count": 0,
        "wire_publish_count": 0,
        "wire_consume_count": 0,
        "wire_published": None,
        "wire_consumed": None,
        "native_submitted": None,
        "transport_submitted": None,
        "checks": {},
        "events": [],
    }
    checks = result["checks"]
    if not isinstance(checks, dict):  # defensive type narrowing
        checks = {}
        result["checks"] = checks
    checks["event_path_is_file"] = event_path is not None and event_path.is_file()
    if not checks["event_path_is_file"]:
        checks["request_binding"] = False
        checks["single_matching_receipt"] = False
        return result
    try:
        size = event_path.stat().st_size
        checks["event_slice_bounded"] = size <= _MAX_NATIVE_EVENT_BYTES
        if not checks["event_slice_bounded"]:
            return result
        matching: list[dict[str, object]] = []
        with event_path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if (event.get("event") == "native_peace_submission_result"
                        and event.get("session_id") == session_id
                        and event.get("request_id") == request_id):
                    matching.append(event)
                    if len(matching) > 16:
                        break
    except OSError as error:
        checks["event_slice_readable"] = False
        result["error"] = f"{type(error).__name__}: {error}"
        return result

    result["matching_event_count"] = len(matching)
    result["events"] = [{
        key: event.get(key)
        for key in (
            "event", "session_id", "request_id", "family", "action_id",
            "actor", "recipient", "phase", "date_raw", "war_id",
            "direction", "amount_raw", "province_ids", "beneficiary",
            "term_mask", "reparations_payer", "reparations_claimant",
            "trade_power_source", "trade_power_beneficiary",
             "conceding_country", "concede_beneficiary",
             "annul_country", "annul_partners",
            "submitted",
            "transport_verified", "request_binding_verified", "reason",
            "native_origin", "native_sequence")
        if key in event
    } for event in matching]
    checks["event_slice_readable"] = True
    checks["single_matching_receipt"] = len(matching) == 1
    if len(matching) != 1:
        checks["request_binding"] = False
        return result

    event = matching[0]
    expected = {
        "family": "peace",
        "action_id": report.get("action_id"),
        "actor": report.get("actor", _ACTOR),
        "recipient": report.get("recipient", _RECIPIENT),
        "phase": report.get("phase", "initiate"),
        "date_raw": report.get("expected_date_raw"),
        "war_id": report.get("war_id"),
        "direction": report.get("direction"),
    }
    field_checks = {
        key: (event.get(key) == value)
        for key, value in expected.items()
        if value is not None
    }
    expected_ids = _execution_province_ids(report)
    if expected_ids or report.get("action_id") == "cede_province":
        actual_ids = event.get("province_ids")
        field_checks["province_ids"] = (
            isinstance(actual_ids, list)
            and all(type(value) is int for value in actual_ids)
            and len(actual_ids) == len(expected_ids)
            and len(actual_ids) == len(set(actual_ids))
            and set(actual_ids) == set(expected_ids)
        )
    # R48's EXEC2 receipt carries the aggregate mask and the direction-bound
    # reparations roles.  Derive the expected values from the immutable
    # execution context so a receipt cannot be accepted merely because its
    # primary action happened to be ``war_reparations``.
    parameters = report.get("parameters")
    execution = parameters.get("execute") if isinstance(parameters, dict) else None
    expected_native = _expected_native_fields(
        report.get("action_id"), execution) \
        if isinstance(report.get("action_id"), str) and isinstance(execution, dict) else {}
    if expected_native.get("term_mask"):
        field_checks["amount_raw"] = (
            event.get("amount_raw") == expected_native.get("amount_raw"))
    for key in ("beneficiary", "term_mask", "reparations_payer",
                "reparations_claimant", "trade_power_source",
                "trade_power_beneficiary", "conceding_country",
                "concede_beneficiary", "annul_country", "annul_partners"):
        expected_value = expected_native.get(key)
        if expected_value is not None:
            field_checks[key] = event.get(key) == expected_value
    checks.update(field_checks)
    checks["request_binding"] = all(field_checks.values())
    # The exact session/request event proves that the wire reached the DLL;
    # native submitted/transport flags remain separate business results.
    result["wire_published"] = checks["request_binding"]
    result["wire_consumed"] = checks["request_binding"]
    result["wire_publish_count"] = 1 if result["wire_published"] else 0
    result["wire_consume_count"] = 1 if result["wire_consumed"] else 0
    result["native_submitted"] = event.get("submitted") \
        if type(event.get("submitted")) is bool else None
    result["transport_submitted"] = (
        event.get("submitted") is True
        and event.get("transport_verified") is True
        and event.get("request_binding_verified") is True
    ) if result["wire_consumed"] else None
    result["status"] = "observed" if result["wire_consumed"] else "mismatch"
    return result


def _derive_wire_correction(source_report: Path, output: Path) -> dict[str, object]:
    """Write a non-destructive correction artifact for an existing report."""

    if output.exists():
        raise PeaceExecutionError("OUTPUT_ALREADY_EXISTS", str(output))
    payload = _read_json(source_report, maximum=_MAX_NATIVE_EVENT_BYTES)
    if not isinstance(payload, dict):
        raise PeaceExecutionError("SOURCE_REPORT_NOT_OBJECT", str(source_report))
    correlation = _wire_submission_correlation(payload)
    correction = {
        "validator": Path(__file__).name,
        "version": 1,
        "mode": "read_only_wire_submission_correction",
        "source_report": str(source_report.resolve()),
        "source_report_sha256": _sha256_file(source_report),
        "source_status": payload.get("status"),
        "original": {
            "request_publish_count": payload.get("request_publish_count"),
            "business_submission": payload.get("business_submission"),
            "business_submission_count": payload.get("business_submission_count"),
        },
        "wire_submission": correlation,
        "corrected": {
            "request_publish_count": correlation.get("wire_publish_count", 0),
            "wire_publish_count": correlation.get("wire_publish_count", 0),
            "wire_consume_count": correlation.get("wire_consume_count", 0),
            "business_submission_count": (
                1 if payload.get("business_submission") is True else 0),
            "business_transport_submitted": correlation.get("transport_submitted"),
        },
        "note": (
            "request_publish_count now denotes an exact native wire receipt; "
            "business_submission and transport_submitted remain separate."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, correction)
    return correction


def _term_for_action(parameters: dict[str, object], action_id: str) -> dict[str, object] | None:
    context = parameters.get("peace_context")
    terms = context.get("terms") if isinstance(context, dict) else None
    if not isinstance(terms, list):
        return None
    for term in terms:
        if isinstance(term, dict) and term.get("action_id") == action_id:
            return term
    return None


def _effects_contract(public: dict[str, object], action_id: str,
                      parameters: dict[str, object], outcome: object) -> dict[str, object]:
    """Validate the bounded native settlement projection when success is claimed."""

    effects = public.get("effects")
    result: dict[str, object] = {
        "present": isinstance(effects, dict),
        "complete": False,
        "date_unchanged": False,
        "currency_scale": None,
        "terms_verified": public.get("terms_verified"),
        "checks": {},
    }
    if not isinstance(effects, dict):
        result["checks"] = {"object": False}
        result["all"] = (
            outcome not in ("accepted", "executed")
            and _term_for_action(parameters, _TRADE_POWER_ACTION) is None
            and _term_for_action(parameters, _CONCEDE_DEFEAT_ACTION) is None
            and _term_for_action(parameters, _ANNUL_TREATIES_ACTION) is None
            and not any(_term_for_action(parameters, action)
                        for action in _SPECIAL_ACTIONS))
        return result
    result["complete"] = effects.get("complete") is True
    result["date_unchanged"] = effects.get("date_unchanged") is True
    result["currency_scale"] = effects.get("currency_scale")
    checks: dict[str, bool] = {
        "object": True,
        "complete": result["complete"],
        "date_unchanged": result["date_unchanged"],
        "currency_scale_1000": effects.get("currency_scale") == 1000,
    }
    money_term = _term_for_action(parameters, "demand_ducats")
    province_term = _term_for_action(parameters, "cede_province")
    reparations_term = _term_for_action(parameters, "war_reparations")
    trade_power_term = _term_for_action(parameters, _TRADE_POWER_ACTION)
    concede_defeat_term = _term_for_action(parameters, _CONCEDE_DEFEAT_ACTION)
    annul_term = _term_for_action(parameters, _ANNUL_TREATIES_ACTION)
    special_terms = {
        action: _term_for_action(parameters, action)
        for action in _SPECIAL_ACTIONS
    }
    trade_power_contract_all: bool | None = None
    concede_defeat_contract_all: bool | None = None
    annul_contract_all: bool | None = None
    special_contract_all: bool | None = None
    if money_term is not None:
        money = effects.get("money")
        expected_amount = _expected_native_fields(action_id, parameters).get("amount_raw")
        expected_payer = money_term.get("payer")
        checks.update({
            "money_object": isinstance(money, dict),
            "money_verified": isinstance(money, dict) and money.get("verified") is True,
            "money_amount": isinstance(money, dict) and money.get("amount_raw") == expected_amount,
            "money_payer": isinstance(money, dict) and money.get("payer") == expected_payer,
            "money_paid_raw": isinstance(money, dict)
            and isinstance(money.get("paid_raw"), int)
            and not isinstance(money.get("paid_raw"), bool),
            "money_credits": isinstance(money, dict)
            and isinstance(money.get("credits"), list)
            and all(
                isinstance(credit, dict)
                and isinstance(credit.get("country"), str)
                and _TAG_RE.fullmatch(credit["country"]) is not None
                and isinstance(credit.get("amount_raw"), int)
                and not isinstance(credit.get("amount_raw"), bool)
                for credit in money.get("credits", [])
            ),
        })
    if province_term is not None:
        provinces = effects.get("provinces")
        expected_ids = province_term.get("province_ids")
        expected_beneficiary = province_term.get("beneficiary")
        by_id = {
            item.get("province_id"): item
            for item in provinces
            if isinstance(item, dict)
        } if isinstance(provinces, list) else {}
        actual_ids = [
            item.get("province_id") for item in provinces
            if isinstance(item, dict)
        ] if isinstance(provinces, list) else []
        checks.update({
            "province_list": isinstance(provinces, list),
            "province_ids_exact": isinstance(expected_ids, list)
            and all(type(item) is int for item in expected_ids)
            and all(type(item) is int for item in actual_ids)
            and len(actual_ids) == len(expected_ids)
            and len(actual_ids) == len(set(actual_ids))
            and set(actual_ids) == set(expected_ids),
            "province_ids": isinstance(expected_ids, list)
            and all(item in by_id for item in expected_ids),
            "province_beneficiary": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and by_id[item].get("beneficiary") == expected_beneficiary
                    for item in expected_ids),
            "province_verified": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and by_id[item].get("verified") is True
                    for item in expected_ids),
            "province_owner_transition": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and isinstance(by_id[item].get("owner_before"), str)
                    and _TAG_RE.fullmatch(by_id[item]["owner_before"]) is not None
                    and by_id[item]["owner_before"] != expected_beneficiary
                    and by_id[item].get("owner_after") == expected_beneficiary
                    for item in expected_ids),
            "province_effect_fields": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and all(isinstance(by_id[item].get(field), str)
                            and _TAG_RE.fullmatch(by_id[item][field]) is not None
                            for field in ("owner_before", "owner_after",
                                          "controller_before", "controller_after"))
                    for item in expected_ids),
        })
    if reparations_term is not None:
        reparations = effects.get("war_reparations")
        checks.update({
            "war_reparations_object": isinstance(reparations, dict),
            "war_reparations_payer": (
                isinstance(reparations, dict)
                and reparations.get("payer") == reparations_term.get("payer")),
            "war_reparations_claimant": (
                isinstance(reparations, dict)
                and reparations.get("claimant") == reparations_term.get("claimant")),
            "war_reparations_active_before": (
                isinstance(reparations, dict)
                and reparations.get("active_before") is False),
            "war_reparations_active_after": (
                isinstance(reparations, dict)
                and reparations.get("active_after") is True),
            "war_reparations_verified": (
                isinstance(reparations, dict)
                and reparations.get("verified") is True),
        })
        # Native R48 may include the raw treaty window.  The fields are
        # optional for compatibility with the legacy public effect shape, but
        # if either is present the pair must be complete, integral and ordered
        # and an active-after relation must contain the result date.
        date_keys = ("start_date_raw", "end_date_raw")
        has_date = isinstance(reparations, dict) and any(
            key in reparations for key in date_keys)
        if has_date:
            result_date = public.get("date_raw")
            start_date = reparations.get("start_date_raw") \
                if isinstance(reparations, dict) else None
            end_date = reparations.get("end_date_raw") \
                if isinstance(reparations, dict) else None
            valid_dates = (
                type(start_date) is int and type(end_date) is int
                and end_date > start_date)
            checks.update({
                "war_reparations_dates_complete": valid_dates,
                "war_reparations_date_window": (
                    valid_dates
                    and (reparations.get("active_after") is not True
                         or (type(result_date) is int
                             and start_date <= result_date < end_date))),
            })
    if trade_power_term is not None:
        trade_power = effects.get(_TRADE_POWER_ACTION)
        trade_checks: dict[str, bool] = {
            "transfer_trade_power_object": isinstance(trade_power, dict),
            "transfer_trade_power_source": (
                isinstance(trade_power, dict)
                and trade_power.get("source") == trade_power_term.get("source")),
            "transfer_trade_power_beneficiary": (
                isinstance(trade_power, dict)
                and trade_power.get("beneficiary") == trade_power_term.get("beneficiary")),
        }
        if outcome in ("accepted", "executed"):
            result_date = public.get("date_raw")
            start_date = trade_power.get("start_date_raw") \
                if isinstance(trade_power, dict) else None
            amount_raw = trade_power.get("amount_raw") \
                if isinstance(trade_power, dict) else None
            amount_scale = trade_power.get("amount_scale") \
                if isinstance(trade_power, dict) else None
            trade_checks.update({
                "transfer_trade_power_present_before_bool": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("present_before")) is bool),
                "transfer_trade_power_present_after": (
                    isinstance(trade_power, dict)
                    and trade_power.get("present_after") is True),
                "transfer_trade_power_start_date": type(start_date) is int,
                "transfer_trade_power_end_date": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("end_date_raw")) is int),
                "transfer_trade_power_amount": (
                    type(amount_raw) is int and amount_raw > 0),
                "transfer_trade_power_scale": amount_scale == 1000,
                "transfer_trade_power_peace_treaty": (
                    isinstance(trade_power, dict)
                    and trade_power.get("peace_treaty") is True),
                "transfer_trade_power_verified": (
                    isinstance(trade_power, dict)
                    and trade_power.get("verified") is True),
                "transfer_trade_power_start_before_date": (
                    type(start_date) is int and type(result_date) is int
                    and start_date <= result_date),
            })
        elif outcome == "rejected":
            trade_checks.update({
                "transfer_trade_power_present_before_bool": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("present_before")) is bool),
                "transfer_trade_power_present_after_bool": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("present_after")) is bool),
                "transfer_trade_power_start_date": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("start_date_raw")) is int),
                "transfer_trade_power_end_date": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("end_date_raw")) is int),
                "transfer_trade_power_amount": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("amount_raw")) is int),
                "transfer_trade_power_scale": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("amount_scale")) is int),
                "transfer_trade_power_peace_treaty_bool": (
                    isinstance(trade_power, dict)
                    and type(trade_power.get("peace_treaty")) is bool),
                "transfer_trade_power_verified": (
                    isinstance(trade_power, dict)
                    and trade_power.get("verified") is False),
            })
        checks.update(trade_checks)
        trade_power_contract_all = all(trade_checks.values())
    if concede_defeat_term is not None:
        concede = effects.get(_CONCEDE_DEFEAT_ACTION)
        expected_conceding = concede_defeat_term.get("conceding_country")
        expected_beneficiary = concede_defeat_term.get("beneficiary")
        c_checks: dict[str, bool] = {
            "concede_defeat_object": isinstance(concede, dict),
            "concede_defeat_conceding_country": (
                isinstance(concede, dict)
                and concede.get("conceding_country") == expected_conceding),
            "concede_defeat_beneficiary": (
                isinstance(concede, dict)
                and concede.get("beneficiary") == expected_beneficiary),
            "concede_defeat_prestige_scale": (
                isinstance(concede, dict)
                and concede.get("prestige_scale") == 1000),
            "concede_defeat_values_readable": (
                isinstance(concede, dict)
                and concede.get("values_readable") is True),
            "concede_defeat_verified_bool": (
                isinstance(concede, dict)
                and isinstance(concede.get("verified"), bool)),
        }
        prestige_fields = (
            "conceding_prestige_before_raw", "conceding_prestige_after_raw",
            "conceding_prestige_delta_raw", "beneficiary_prestige_before_raw",
            "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw")
        if isinstance(concede, dict):
            c_checks.update({
                f"concede_defeat_{field}": (
                    type(concede.get(field)) is int
                    and not isinstance(concede.get(field), bool))
                for field in prestige_fields
            })
            c_checks.update({
                "concede_defeat_conceding_delta_consistent": (
                    type(concede.get("conceding_prestige_before_raw")) is int
                    and type(concede.get("conceding_prestige_after_raw")) is int
                    and type(concede.get("conceding_prestige_delta_raw")) is int
                    and concede.get("conceding_prestige_delta_raw") ==
                    concede.get("conceding_prestige_after_raw") -
                    concede.get("conceding_prestige_before_raw")),
                "concede_defeat_beneficiary_delta_consistent": (
                    type(concede.get("beneficiary_prestige_before_raw")) is int
                    and type(concede.get("beneficiary_prestige_after_raw")) is int
                    and type(concede.get("beneficiary_prestige_delta_raw")) is int
                    and concede.get("beneficiary_prestige_delta_raw") ==
                    concede.get("beneficiary_prestige_after_raw") -
                    concede.get("beneficiary_prestige_before_raw")),
            })
            if outcome in ("accepted", "executed"):
                c_checks["concede_defeat_verified"] = concede.get("verified") is True
            elif outcome == "rejected":
                # A refusal may itself incur the native defeat/desperation
                # prestige penalty.  Preserve and validate the measured
                # transition; do not impose a fixed zero delta.
                c_checks["concede_defeat_verified"] = concede.get("verified") is False
        concede_defeat_contract_all = all(c_checks.values())
        checks.update(c_checks)
    if annul_term is not None:
        annul_effects = effects.get(_ANNUL_TREATIES_ACTION)
        requested_country = annul_term.get("country")
        requested_partners = annul_term.get("treaty_partners")
        requested_pairs = (
            [(requested_country, partner) for partner in requested_partners]
            if isinstance(requested_country, str)
            and isinstance(requested_partners, list) else [])
        rows = annul_effects if isinstance(annul_effects, list) else []
        row_pairs = [(row.get("country"), row.get("partner"))
                     for row in rows if isinstance(row, dict)]
        a_checks: dict[str, bool] = {
            "annul_treaties_list": isinstance(annul_effects, list),
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
                f"{prefix}_object": isinstance(row, dict),
                f"{prefix}_country": isinstance(row, dict) and row.get("country") == pair[0],
                f"{prefix}_partner": isinstance(row, dict) and row.get("partner") == pair[1],
                f"{prefix}_present_before": isinstance(row, dict) and type(row.get("present_before")) is bool,
                f"{prefix}_present_after": isinstance(row, dict) and type(row.get("present_after")) is bool,
                f"{prefix}_start_date": isinstance(row, dict) and type(row.get("start_date_raw")) is int,
                f"{prefix}_end_date": isinstance(row, dict) and type(row.get("end_date_raw")) is int,
                f"{prefix}_alliance_before": isinstance(row, dict) and type(row.get("alliance_before")) is bool,
                f"{prefix}_alliance_after": isinstance(row, dict) and type(row.get("alliance_after")) is bool,
                f"{prefix}_values_readable": isinstance(row, dict) and row.get("values_readable") is True,
                f"{prefix}_verified": isinstance(row, dict) and row.get("verified") is (outcome in ("accepted", "executed")),
            })
            if outcome in ("accepted", "executed"):
                a_checks[f"{prefix}_applied"] = (
                    isinstance(row, dict)
                    and row.get("present_after") is True
                    and row.get("alliance_after") is False)
        annul_contract_all = all(a_checks.values())
        checks.update(a_checks)
    for special_action, special_term in special_terms.items():
        if special_term is None:
            checks[f"{special_action}_empty"] = effects.get(special_action) is None
            continue
        special = effects.get(special_action)
        s_checks: dict[str, bool] = {
            f"{special_action}_object": isinstance(special, dict),
            f"{special_action}_country": isinstance(special, dict)
            and special.get("country") == special_term.get("country"),
            f"{special_action}_beneficiary": isinstance(special, dict)
            and special.get("beneficiary") == special_term.get("beneficiary"),
            f"{special_action}_values_readable": isinstance(special, dict)
            and special.get("values_readable") is True,
            f"{special_action}_verified_bool": isinstance(special, dict)
            and isinstance(special.get("verified"), bool),
        }
        if special_action == _FORCE_RELIGION_ACTION:
            # F has a distinct effect schema: the native serializer exposes
            # canonical religion keys and before/after values for the target,
            # its beneficiary, and its capital.  It has no prestige or
            # humiliation fields shared by H/S.
            religion_fields = (
                "religion_before", "religion_after",
                "beneficiary_religion_before", "beneficiary_religion_after",
                "capital_religion_before", "capital_religion_after")
            religion_re = re.compile(r"^[A-Za-z0-9_]{1,63}$")
            s_checks[f"{special_action}_fields"] = (
                isinstance(special, dict)
                and set(special) == {
                    "country", "beneficiary", *religion_fields,
                    "values_readable", "verified"})
            for field in religion_fields:
                s_checks[f"{special_action}_{field}"] = (
                    isinstance(special, dict)
                    and isinstance(special.get(field), str)
                    and religion_re.fullmatch(special[field]) is not None)
            if outcome in ("accepted", "executed"):
                s_checks[f"{special_action}_verified"] = (
                    isinstance(special, dict)
                    and special.get("verified") is True)
                s_checks[f"{special_action}_religion_applied"] = (
                    isinstance(special, dict)
                    and special.get("religion_after") ==
                    special.get("beneficiary_religion_after")
                    and special.get("capital_religion_after") ==
                    special.get("beneficiary_religion_after"))
            elif outcome == "rejected":
                s_checks[f"{special_action}_verified"] = (
                    isinstance(special, dict)
                    and special.get("verified") is False)
        else:
            # H/S share the prestige and humiliation transition.  S adds the
            # three bounded power vectors below; H retains the common subset.
            s_checks[f"{special_action}_prestige_scale"] = (
                isinstance(special, dict)
                and special.get("prestige_scale",
                                special.get("prestige_scale1000")) == 1000)
            s_checks[f"{special_action}_humiliated_before_bool"] = (
                isinstance(special, dict)
                and isinstance(special.get("humiliated_before"), bool))
            s_checks[f"{special_action}_humiliated_after_bool"] = (
                isinstance(special, dict)
                and isinstance(special.get("humiliated_after"), bool))
            prestige_fields = (
                "country_prestige_before_raw", "country_prestige_after_raw",
                "country_prestige_delta_raw", "beneficiary_prestige_before_raw",
                "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw")
            for field in prestige_fields:
                s_checks[f"{special_action}_{field}"] = (
                    isinstance(special, dict)
                    and type(special.get(field)) is int
                    and not isinstance(special.get(field), bool))
            if isinstance(special, dict):
                s_checks[f"{special_action}_country_delta_consistent"] = (
                    special.get("country_prestige_delta_raw") ==
                    special.get("country_prestige_after_raw") -
                    special.get("country_prestige_before_raw"))
                s_checks[f"{special_action}_beneficiary_delta_consistent"] = (
                    special.get("beneficiary_prestige_delta_raw") ==
                    special.get("beneficiary_prestige_after_raw") -
                    special.get("beneficiary_prestige_before_raw"))
                if outcome in ("accepted", "executed"):
                    s_checks[f"{special_action}_verified"] = (
                        special.get("verified") is True)
                    s_checks[f"{special_action}_humiliated_after"] = (
                        special.get("humiliated_after") is True)
                elif outcome == "rejected":
                    s_checks[f"{special_action}_verified"] = (
                        special.get("verified") is False)
            if special_action == _SHOW_STRENGTH_ACTION:
                for field in ("powers_before", "powers_after", "powers_delta"):
                    s_checks[f"{special_action}_{field}"] = (
                        isinstance(special, dict)
                        and isinstance(special.get(field), list)
                        and len(special[field]) == 3
                        and all(type(value) is int and not isinstance(value, bool)
                                for value in special[field]))
                s_checks[f"{special_action}_powers_requested"] = (
                    isinstance(special, dict)
                    and type(special.get("powers_requested")) is int
                    and special.get("powers_requested") >= 0)
        checks.update(s_checks)
        special_contract_all = all(s_checks.values()) if special_contract_all is None else (
            special_contract_all and all(s_checks.values()))
    if (money_term is None and province_term is None
            and trade_power_term is None and concede_defeat_term is None
            and not any(special_terms.values())):
        # White peace has no selected money/province term.  The native effect
        # object remains required for a claimed successful settlement, while
        # the empty lists are allowed to carry future effect metadata.
        checks.update({
            "money_empty": effects.get("money") is None,
            "provinces_list": isinstance(effects.get("provinces"), list),
        })
    if reparations_term is None and trade_power_term is None:
        checks["war_reparations_empty"] = effects.get("war_reparations") is None
    if trade_power_term is None:
        checks["transfer_trade_power_empty"] = (
            effects.get(_TRADE_POWER_ACTION) is None)
    if concede_defeat_term is None:
        checks["concede_defeat_empty"] = (
            effects.get(_CONCEDE_DEFEAT_ACTION) is None)
    if annul_term is None:
        checks["annul_treaties_empty"] = effects.get(_ANNUL_TREATIES_ACTION) is None
    result["checks"] = checks
    if outcome in ("accepted", "executed"):
        result["all"] = all(checks.values())
    elif (trade_power_contract_all is not None
          or concede_defeat_contract_all is not None
          or annul_contract_all is not None
          or special_contract_all is not None):
        # R50 rejection carries a typed effect object, but no applied-state
        # transition is required; only its bound rejection contract matters.
        result["all"] = all(value for value in (
            trade_power_contract_all, concede_defeat_contract_all,
            annul_contract_all, special_contract_all)
            if value is not None)
    else:
        result["all"] = True
    return result


def _expected_native_fields(action_id: str, parameters: dict[str, object]) -> dict[str, object]:
    context = parameters.get("peace_context")
    if not isinstance(context, dict):
        return {}
    terms = context.get("terms")
    amount_raw = -1
    province_ids: list[int] = []
    beneficiary: str | None = None
    reparations_payer: str | None = None
    reparations_claimant: str | None = None
    trade_power_source: str | None = None
    trade_power_beneficiary: str | None = None
    concede_defeat_country: str | None = None
    concede_defeat_beneficiary: str | None = None
    annul_country: str | None = None
    annul_partners: list[str] | None = None
    special_actions: set[str] = set()
    term_mask: str = ""
    if isinstance(terms, list):
        for term in terms:
            if not isinstance(term, dict):
                continue
            if term.get("action_id") == "demand_ducats":
                term_mask += "m"
                amount = term.get("amount")
                if isinstance(amount, str) and re.fullmatch(r"[0-9]+\.[0-9]", amount):
                    whole, tenths = amount.split(".")
                    amount_raw = (int(whole) * 10 + int(tenths)) * 100
            elif term.get("action_id") == "cede_province":
                term_mask += "p"
                ids = term.get("province_ids")
                if isinstance(ids, list):
                    province_ids = list(ids)
                beneficiary = term.get("beneficiary") \
                    if isinstance(term.get("beneficiary"), str) else None
            elif term.get("action_id") == "war_reparations":
                term_mask += "r"
                reparations_payer = term.get("payer") \
                    if isinstance(term.get("payer"), str) else None
                reparations_claimant = term.get("claimant") \
                    if isinstance(term.get("claimant"), str) else None
            elif term.get("action_id") == _TRADE_POWER_ACTION:
                term_mask += "t"
                trade_power_source = term.get("source") \
                    if isinstance(term.get("source"), str) else None
                trade_power_beneficiary = term.get("beneficiary") \
                    if isinstance(term.get("beneficiary"), str) else None
            elif term.get("action_id") == _CONCEDE_DEFEAT_ACTION:
                term_mask += "c"
                concede_defeat_country = term.get("conceding_country") \
                    if isinstance(term.get("conceding_country"), str) else None
                concede_defeat_beneficiary = term.get("beneficiary") \
                    if isinstance(term.get("beneficiary"), str) else None
            elif term.get("action_id") == _ANNUL_TREATIES_ACTION:
                term_mask += "a"
                annul_country = term.get("country") \
                    if isinstance(term.get("country"), str) else None
                raw_partners = term.get("treaty_partners")
                if isinstance(raw_partners, list):
                    annul_partners = list(raw_partners)
            elif term.get("action_id") in _SPECIAL_ACTIONS:
                special_actions.add(str(term.get("action_id")))
    canonical_letters = {
        "demand_ducats": "m", "cede_province": "p",
        "war_reparations": "r", _TRADE_POWER_ACTION: "t",
        _CONCEDE_DEFEAT_ACTION: "c", _ANNUL_TREATIES_ACTION: "a",
        _HUMILIATE_RIVAL_ACTION: "h", _SHOW_STRENGTH_ACTION: "s",
        _FORCE_RELIGION_ACTION: "f",
    }
    present_actions = {
        term.get("action_id") for term in terms
        if isinstance(term, dict) and term.get("action_id") in canonical_letters
    } if isinstance(terms, list) else set()
    term_mask = "".join(canonical_letters[action]
                         for action in ("demand_ducats", "cede_province",
                                        "war_reparations", _TRADE_POWER_ACTION,
                                        _CONCEDE_DEFEAT_ACTION,
                                        _ANNUL_TREATIES_ACTION,
                                        _HUMILIATE_RIVAL_ACTION,
                                        _SHOW_STRENGTH_ACTION,
                                        _FORCE_RELIGION_ACTION)
                         if action in present_actions)
    result = {
        "event": "native_peace_execution_result",
        "action_id": action_id,
        "family": _FAMILY,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "phase": "initiate",
        "war_id": context.get("war_id"),
        "direction": context.get("direction"),
        "amount_raw": amount_raw,
        "province_ids": province_ids,
        "beneficiary": beneficiary,
    }
    # The native result exposes the canonical term mask and direction-bound
    # roles when a non-legacy term is present.  Keep the legacy result shape
    # unchanged for money/province-only callers and bind each new field only
    # when it is actually present in the requested context.
    if term_mask and (reparations_payer is not None
                      or trade_power_source is not None
                      or concede_defeat_country is not None
                      or annul_country is not None
                      or special_actions):
        result["term_mask"] = term_mask
    if reparations_payer is not None and reparations_claimant is not None:
        result.update({
            "reparations_payer": reparations_payer,
            "reparations_claimant": reparations_claimant,
        })
    if trade_power_source is not None and trade_power_beneficiary is not None:
        result.update({
            "trade_power_source": trade_power_source,
            "trade_power_beneficiary": trade_power_beneficiary,
        })
    if concede_defeat_country is not None and concede_defeat_beneficiary is not None:
        result.update({
            # These are the native receipt names.  The public request keeps
            # the normalized term names (conceding_country/beneficiary).
            "conceding_country": concede_defeat_country,
            "concede_beneficiary": concede_defeat_beneficiary,
        })
    if annul_country is not None and annul_partners is not None:
        result.update({
            "annul_country": annul_country,
            "annul_partners": annul_partners,
        })
    return result


def _province_id_sequence_matches(actual: object, expected: object) -> bool:
    """Compare selected province IDs as a complete duplicate-free set."""

    if not isinstance(actual, list) or not isinstance(expected, list):
        return False
    if any(type(value) is not int for value in actual + expected):
        return False
    return (len(actual) == len(expected)
            and len(actual) == len(set(actual))
            and len(expected) == len(set(expected))
            and set(actual) == set(expected))


def _result_contract(final: object, action_id: str,
                     parameters: dict[str, object], expected_date_raw: object,
                     before_war: dict[str, object], after_war: dict[str, object]) -> dict[str, object]:
    public = _public_result(final)
    expected = _expected_native_fields(action_id, parameters)
    checks: dict[str, bool] = {
        "public_result": isinstance(public, dict),
        "terminal_status": isinstance(final, dict)
        and final.get("status") in _TERMINAL_STATUSES,
        "binding": False,
        "native_result": False,
        "war_transition": False,
        "proof": False,
        "response_verified": False,
        "terms_verified": False,
        "effects_contract": False,
        "unknown_preserved": False,
    }
    if public is None:
        return {"checks": checks, "all": False, "public": None}
    checks["binding"] = all(
        (_province_id_sequence_matches(public.get(key), value)
         if key == "province_ids" else public.get(key) == value)
        for key, value in expected.items()) \
        and public.get("date_raw") == expected_date_raw \
        and public.get("request_id") == final.get("request_id")
    outcome = public.get("outcome")
    effects_contract = _effects_contract(public, action_id, parameters, outcome)
    checks["effects_contract"] = effects_contract.get("all") is True
    checks["native_result"] = outcome in ("executed", "accepted", "rejected", "unknown")
    if outcome in ("executed", "accepted"):
        expected_after = False
        checks["war_transition"] = (
            before_war.get("complete") is True
            and after_war.get("complete") is True
            and before_war.get("pair_at_war") is True
            and after_war.get("pair_at_war") is False
            and public.get("war_before") is True
            and public.get("war_after") is expected_after)
        checks["proof"] = (
            public.get("response_verified") is True
            and public.get("request_binding_verified") is True
            and public.get("execution_verified") is True
            and public.get("terms_verified") is True)
        checks["response_verified"] = public.get("response_verified") is True
        checks["terms_verified"] = public.get("terms_verified") is True
    elif outcome == "rejected":
        checks["war_transition"] = (
            before_war.get("complete") is True
            and after_war.get("complete") is True
            and before_war.get("pair_at_war") is True
            and after_war.get("pair_at_war") is True
            and public.get("war_before") is True
            and public.get("war_after") is True)
        checks["proof"] = (
            public.get("response_verified") is True
            and public.get("request_binding_verified") is True
            and public.get("execution_verified") is False)
        checks["response_verified"] = public.get("response_verified") is True
        # A refusal is a valid native response with no applied terms.
        checks["terms_verified"] = public.get("terms_verified") is False
    else:
        # A native unknown is retained as evidence, never promoted to a
        # successful transition.  The surrounding report remains unknown.
        checks["unknown_preserved"] = (
            outcome == "unknown"
            and public.get("execution_verified") is False
            and public.get("request_binding_verified") is False)
    # ``unknown_preserved`` is a branch-specific check.  It must not make a
    # proven executed/accepted/rejected result fail merely because the
    # unknown branch is inapplicable.  Conversely, an unknown native outcome
    # remains an incomplete verification even when its evidence is retained.
    if outcome == "unknown":
        checks["all"] = False
    else:
        checks["all"] = all(
            value for key, value in checks.items()
            if key not in ("unknown_preserved", "effects_contract")
        )
        checks["all"] = checks["all"] and checks["effects_contract"]
    return {
        "checks": checks,
        "all": checks["all"],
        "public": public,
        "native_effects": _native_effect_observation(public),
        "effects_contract": effects_contract,
    }


def _control_invariants(before: dict[str, object], after: dict[str, object],
                        expected_date_raw: int, before_probes: object,
                        after_probes: object) -> dict[str, bool]:
    return {
        "before_four_snapshots_complete": _snapshots_complete(before_probes),
        "after_four_snapshots_complete": _snapshots_complete(after_probes),
        "before_por_paused_date": before == {
            "date_raw": expected_date_raw, "paused_flag": 1,
            "player_slot": _PLAYER_SLOT},
        "after_por_paused_same_date": after == before
        and after == {
            "date_raw": expected_date_raw, "paused_flag": 1,
            "player_slot": _PLAYER_SLOT},
    }


def _offline_contract_assertions() -> None:
    war_id = "war_0123456789abcdef_01234567"
    white = _build_parameters("white_peace", war_id, "10.0", 177, _ACTOR)
    money = _build_parameters("demand_ducats", war_id, "10.0", 177, _ACTOR)
    province = _build_parameters("cede_province", war_id, "10.0", 177, _ACTOR)
    offer_money = _build_parameters(
        "demand_ducats", war_id, "10.0", 177, None, "offer")
    offer_province = _build_parameters(
        "cede_province", war_id, "10.0", 177, None, "offer")
    multi_province = _build_parameters(
        "cede_province", war_id, "10.0", 177, _ACTOR,
        province_ids=[177, 178, 185])
    mixed = _build_parameters(
        "cede_province", war_id, "10.0", 177, None, "offer",
        province_ids=[177, 178, 185], with_money="1.0")
    assert white["peace_context"]["terms"] == []
    assert money["peace_context"]["terms"][0]["amount"] == "10.0"
    assert province["peace_context"]["terms"][0]["province_ids"] == [177]
    assert offer_money["peace_context"]["direction"] == "offer"
    assert offer_money["peace_context"]["terms"][0]["payer"] == _ACTOR
    assert offer_money["peace_context"]["terms"][0]["claimant"] == _RECIPIENT
    assert offer_province["peace_context"]["terms"][0]["beneficiary"] == _RECIPIENT
    assert multi_province["peace_context"]["terms"][0]["province_ids"] == [177, 178, 185]
    assert [term["action_id"] for term in mixed["peace_context"]["terms"]] == [
        "demand_ducats", "cede_province"]
    assert mixed["peace_context"]["terms"][0]["amount"] == "1.0"
    trade_only_demand = _build_parameters(
        _TRADE_POWER_ACTION, war_id, "10.0", None, None, "demand")
    trade_only_offer = _build_parameters(
        _TRADE_POWER_ACTION, war_id, "10.0", None, None, "offer")
    assert trade_only_demand["peace_context"]["terms"] == [{
        "action_id": _TRADE_POWER_ACTION,
        "source": _RECIPIENT,
        "beneficiary": _ACTOR,
    }]
    assert trade_only_offer["peace_context"]["terms"] == [{
        "action_id": _TRADE_POWER_ACTION,
        "source": _ACTOR,
        "beneficiary": _RECIPIENT,
    }]
    trade_masks = {
        "t": (_TRADE_POWER_ACTION, {}),
        "mt": ("demand_ducats", {"with_trade_power": True}),
        "pt": ("cede_province", {"with_trade_power": True}),
        "rt": ("war_reparations", {"with_trade_power": True}),
        "mpt": ("cede_province", {
            "with_money": "1.0", "with_trade_power": True}),
        "mrt": ("demand_ducats", {
            "with_reparations": True, "with_trade_power": True}),
        "prt": ("cede_province", {
            "with_reparations": True, "with_trade_power": True}),
        "mprt": ("cede_province", {
            "with_money": "1.0", "with_reparations": True,
            "with_trade_power": True}),
    }
    for mask, (primary, options) in trade_masks.items():
        trade_parameters = _build_parameters(
            primary, war_id, "10.0", 177 if "p" in mask else None,
            _ACTOR, "demand",
            province_ids=[177] if "p" in mask else None, **options)
        assert _expected_native_fields(
            primary, trade_parameters)["term_mask"] == mask
    # Keep the runner's own offline guard aligned with EXEC2's complete
    # reparations matrix.  The primary war_reparations form is what the CLI
    # uses for the combined R48 request, while the other primaries remain
    # valid normalized contexts for compatibility.
    r48_province_ids = [4388, 4111, 4112, 4389, 4118]
    reparations_masks = {
        "r": {},
        "mr": {"with_money": "1.0"},
        "pr": {"province_ids": r48_province_ids, "beneficiary": "ENG"},
        "mpr": {
            "with_money": "1.0", "province_ids": r48_province_ids,
            "beneficiary": "ENG",
        },
    }
    for mask, options in reparations_masks.items():
        beneficiary = options.get("beneficiary")
        builder_options = {
            key: value for key, value in options.items()
            if key != "beneficiary"
        }
        reparations = _build_parameters(
            "war_reparations", war_id, "10.0", None, beneficiary,
            "demand", **builder_options)
        terms = reparations["peace_context"]["terms"]
        assert "".join({
            "demand_ducats": "m", "cede_province": "p",
            "war_reparations": "r",
        }[term["action_id"]] for term in terms) == mask
        assert _expected_native_fields(
            "war_reparations", reparations)["term_mask"] == mask
    annul = _build_parameters(
        _ANNUL_TREATIES_ACTION, war_id, "10.0", None, None, "demand",
        annul_country="FRA", annul_partners=["GEN", "SAV"])
    assert annul["peace_context"]["terms"] == [{
        "action_id": _ANNUL_TREATIES_ACTION,
        "country": "FRA",
        "treaty_partners": ["GEN", "SAV"],
    }]
    annul_expected = _expected_native_fields(_ANNUL_TREATIES_ACTION, annul)
    assert annul_expected["term_mask"] == "a"
    assert annul_expected["annul_country"] == "FRA"
    assert annul_expected["annul_partners"] == ["GEN", "SAV"]
    for special, letter in ((_HUMILIATE_RIVAL_ACTION, "h"),
                            (_SHOW_STRENGTH_ACTION, "s"),
                            (_FORCE_RELIGION_ACTION, "f")):
        special_parameters = _build_parameters(
            special, war_id, "10.0", None, None, "demand")
        assert special_parameters["peace_context"]["terms"] == [{
            "action_id": special, "country": _RECIPIENT,
            "beneficiary": _ACTOR,
        }]
        assert _expected_native_fields(special, special_parameters)["term_mask"] == letter
    try:
        _annul_treaties_term("FRA", ["SAV", "GEN"])
    except PeaceExecutionError as error:
        assert error.code == "ANNUL_PARTNERS_UNSORTED"
    else:
        raise AssertionError("unsorted annul partners were accepted")
    try:
        _parse_province_ids_csv("177,,178")
    except PeaceExecutionError as error:
        assert error.code == "PROVINCE_IDS_INVALID"
    else:
        raise AssertionError("empty province CSV token was accepted")
    query = _query_parameters("white_peace", white)
    assert query == white
    selected = {
        "action_id": "white_peace", "family": "peace", "actor": "FRA",
        "recipient": "ENG", "phase": "initiate",
        "session": {"status": "ready", "complete": True},
        "interface_support": {"query": "native_peace_empty_offer_inspection"},
        "peace_context": {
            "war_id": war_id, "direction": "demand", "complete": True,
            "terms": [],
        },
        "pair_at_war": True, "parameters": {"requested": query},
    }
    assert _selected_inspection_contract(selected, "white_peace", query, war_id)["valid"]
    before_war = {"complete": True, "pair_at_war": True}
    after_war = {"complete": True, "pair_at_war": False}
    final = {
        "status": "executed", "request_id": "offline_peace_001",
        "result": {
            **_expected_native_fields("white_peace", white),
            "date_raw": 1, "request_id": "offline_peace_001",
            "outcome": "executed", "response_verified": True,
            "request_binding_verified": True, "execution_verified": True,
            "terms_verified": True,
            "war_before": True, "war_after": False,
            "effects": {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": None,
                "provinces": [],
            },
        },
    }
    assert _result_contract(final, "white_peace", white, 1,
                            before_war, after_war)["all"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--recipient", type=_recipient_arg,
                        default=_DEFAULT_RECIPIENT,
                        help="议和目标国；默认 ENG，FRA 为固定 actor")
    parser.add_argument("--action", choices=_ACTIONS, required=True)
    parser.add_argument("--direction", choices=_DIRECTIONS, default="demand",
                        help="议和方向；demand 为 actor 向 recipient 索取，offer 为 actor 向 recipient 提供")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="新的报告文件路径，或新的报告目录")
    parser.add_argument("--amount", default="10.0",
                        help="demand_ducats 的金额，默认 10.0 ducats")
    parser.add_argument("--with-money", default=None,
                        help="cede_province 或 war_reparations 主动作追加的金额条款（例如 1.0 ducats）")
    parser.add_argument("--with-reparations", action="store_true",
                        help="给 demand_ducats、cede_province 或 transfer_trade_power 主动作追加战争赔款条款")
    parser.add_argument("--trade-power", action="store_true",
                        help="附加 transfer_trade_power 条款；该 action 本身默认包含此条款")
    parser.add_argument("--trade-power-source", default=None,
                        help="transfer_trade_power 的实际转出国 canonical tag；默认 demand=recipient、offer=FRA")
    parser.add_argument("--annul-country", default=None,
                        help="annul_treaties 的关系拥有国；必须显式指定")
    parser.add_argument("--annul-partners", nargs="+", default=None,
                        help="annul_treaties 的已排序合法伙伴列表（1..16）")
    parser.add_argument("--special-country", default=None,
                        help="humiliate_rival/show_strength/force_religion 的 country；缺省按 direction 推导")
    parser.add_argument("--special-beneficiary", default=None,
                        help="H/S/F 的 beneficiary（force_religion 的宗教参照国）；缺省按 direction 推导")
    parser.add_argument("--province-id", type=int, default=None,
                        help="兼容旧调用：cede_province 的单个省份编号；未给出时默认 177")
    parser.add_argument("--province-ids", default=None,
                        help="cede_province 的省份编号 CSV（1..16 个，例如 177,178,185）；与 --province-id 互斥")
    parser.add_argument("--beneficiary", default=None,
                        help="cede_province 的受益国；默认随 direction 选择 demand=FRA、offer=recipient")
    args = parser.parse_args(argv)
    _offline_contract_assertions()
    global _RECIPIENT
    _RECIPIENT = args.recipient
    os.environ["EU4_WAR_PAIR_RECIPIENT"] = _RECIPIENT
    if _REQUEST_ID_RE.fullmatch(args.request_id) is None:
        parser.error("--request-id must match [A-Za-z0-9_-]{1,64}")
    try:
        if args.with_money is not None and args.action not in (
                "cede_province", "war_reparations", _TRADE_POWER_ACTION,
                _CONCEDE_DEFEAT_ACTION, _ANNUL_TREATIES_ACTION,
                *_SPECIAL_ACTIONS):
            raise PeaceExecutionError(
                "WITH_MONEY_ACTION_INVALID",
                "--with-money only applies when cede_province, war_reparations, transfer_trade_power, or concede_defeat is primary")
        if args.with_reparations and args.action not in (
                "demand_ducats", "cede_province", _TRADE_POWER_ACTION,
                _CONCEDE_DEFEAT_ACTION, _ANNUL_TREATIES_ACTION,
                *_SPECIAL_ACTIONS):
            raise PeaceExecutionError(
                "WITH_REPARATIONS_ACTION_INVALID",
                "--with-reparations only applies when demand_ducats, cede_province, transfer_trade_power, or concede_defeat is primary")
        if args.trade_power and args.action == "white_peace":
            raise PeaceExecutionError(
                "TRADE_POWER_ACTION_INVALID",
                "--trade-power cannot be combined with white_peace")
        if args.trade_power_source is not None:
            _trade_power_source_for_direction(
                args.direction, args.trade_power_source)
            if not (args.action == _TRADE_POWER_ACTION or args.trade_power):
                raise PeaceExecutionError(
                    "TRADE_POWER_SOURCE_ACTION_INVALID",
                    "--trade-power-source requires --trade-power or transfer_trade_power")
        if (args.annul_country is None) != (args.annul_partners is None):
            raise PeaceExecutionError(
                "ANNUL_TERM_INCOMPLETE",
                "--annul-country and --annul-partners must be supplied together")
        if args.action == _ANNUL_TREATIES_ACTION:
            _annul_treaties_term(args.annul_country, args.annul_partners)
        elif args.annul_country is not None:
            # A is also accepted as an explicit mixed term for the existing
            # primary actions; no implicit candidate is selected here.
            _annul_treaties_term(args.annul_country, args.annul_partners)
        if args.province_ids is not None and args.province_id is not None:
            raise PeaceExecutionError(
                "PROVINCE_OPTIONS_CONFLICT", "--province-id and --province-ids are mutually exclusive")
        if args.province_ids is not None:
            if args.action not in ("cede_province", "war_reparations",
                                    _TRADE_POWER_ACTION, _CONCEDE_DEFEAT_ACTION,
                                    _ANNUL_TREATIES_ACTION, *_SPECIAL_ACTIONS):
                raise PeaceExecutionError(
                    "PROVINCE_IDS_ACTION_INVALID",
                    "--province-ids only applies to cede_province, war_reparations, transfer_trade_power, or concede_defeat")
            selected_province_ids = _parse_province_ids_csv(args.province_ids)
        elif args.province_id is not None:
            if args.action not in ("cede_province", "war_reparations",
                                    _TRADE_POWER_ACTION, _CONCEDE_DEFEAT_ACTION,
                                    _ANNUL_TREATIES_ACTION, *_SPECIAL_ACTIONS):
                raise PeaceExecutionError(
                    "PROVINCE_ID_ACTION_INVALID",
                    "--province-id only applies to cede_province, war_reparations, transfer_trade_power, or concede_defeat")
            selected_province_ids = _normalize_province_ids([args.province_id])
        elif args.action in ("white_peace", "demand_ducats", "war_reparations",
                             _TRADE_POWER_ACTION, _CONCEDE_DEFEAT_ACTION,
                             _ANNUL_TREATIES_ACTION, *_SPECIAL_ACTIONS):
            # These primary actions do not implicitly carry a province term.
            # ``None`` also keeps the normalized context distinct from an
            # explicitly supplied (and bounded) province list.
            selected_province_ids = None
        else:
            selected_province_ids = [177]
    except PeaceExecutionError as error:
        parser.error(f"{error.code}: {error.message}")

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "status": "running",
        "mode": "public_peace_outbound_execution",
        "installation": str(args.installation),
        "action_id": args.action,
        "direction": args.direction,
        "trade_power_source_requested": args.trade_power_source,
        "special_country_requested": args.special_country,
        "special_beneficiary_requested": args.special_beneficiary,
        "concede_defeat_requested": args.action == _CONCEDE_DEFEAT_ACTION,
        "annul_treaties_requested": args.action == _ANNUL_TREATIES_ACTION
        or args.annul_country is not None,
        "annul_country_requested": args.annul_country,
        "annul_partners_requested": args.annul_partners,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "family": _FAMILY,
        "phase": "initiate",
        "request_id": args.request_id,
        "execute_call_count": 0,
        "request_publish_count": 0,
        "business_submission_count": 0,
        "wire_publish_count": 0,
        "wire_consume_count": 0,
        "wire_published": None,
        "wire_consumed": None,
        "business_transport_submitted": None,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "installation_requested": False,
        "checks": {},
    }
    log_start: int | None = None
    log_path: Path | None = None
    before: dict[str, dict[str, object]] | None = None
    after: dict[str, dict[str, object]] | None = None
    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        binding = _installation_binding(installation)
        report.update(binding)
        installation_record = _read_json(installation)
        if not isinstance(installation_record, dict):
            raise PeaceExecutionError("INSTALLATION_METADATA_INVALID", str(installation))
        creation_filetime = installation_record.get("creation_filetime")
        if (isinstance(creation_filetime, bool)
                or not isinstance(creation_filetime, int)
                or creation_filetime < 0):
            raise PeaceExecutionError("INSTALLATION_CREATION_INVALID", str(creation_filetime))

        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "creation_filetime": session.record.get("creation_filetime"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        report["preflight_identity"] = {
            "session_matches_installation": session.session_id == installation_record.get("session_id"),
            "creation_matches_installation": session.record.get("creation_filetime") == creation_filetime,
            "dll_matches_installation_and_build": (
                session.record.get("dll_sha256") == binding.get("installation", {}).get("declared_dll_sha256")
                and binding.get("build_binding", {}).get("installation_matches_build_manifest") is True),
        }
        health_before = wait_runtime_ready(session, timeout=30.0, restore_minimized=False)
        before = _run_snapshots(session, evidence / "before" / "probes")
        before_control = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "health": health_before,
            "control": before_control,
            "probes": _public_probe_records(before),
            "war_state": _war_pair_summary_for(before),
        }
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or before_control != {
                    "date_raw": health_before.get("date_raw"),
                    "paused_flag": 1,
                    "player_slot": _PLAYER_SLOT,
                }
                or not _snapshots_complete(before)):
            raise PeaceExecutionError(
                "BASELINE_NOT_READY_POR_PAUSED_SNAPSHOTS",
                "before snapshots did not prove paused POR state")

        log_path = session.directory / "control-probe.jsonl"
        if not log_path.is_file():
            raise PeaceExecutionError("NATIVE_LOG_UNAVAILABLE", str(log_path))
        expected_date_raw = before_control.get("date_raw")
        if isinstance(expected_date_raw, bool) or not isinstance(expected_date_raw, int):
            raise PeaceExecutionError("DATE_RAW_INVALID", str(expected_date_raw))
        report["expected_date_raw"] = expected_date_raw
        report["public_query_has_no_private_identifiers"] = True
        report["public_inspection"] = {}

        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action(
                _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                phase="initiate", parameters={})
            _write_json(evidence / "war-discovery.json", discovery)
            report["war_discovery"] = discovery
            war_id = _single_discovered_war_id(discovery, _ACTOR, _RECIPIENT)
            if war_id is None or _WAR_ID_RE.fullmatch(war_id) is None:
                raise PeaceExecutionError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE",
                    "public white_peace discovery did not return one war id")
            report["war_id"] = war_id
            report["war_context_before"] = discovery.get("war_contexts") \
                if isinstance(discovery, dict) else None
            if _has_private_fields(discovery):
                raise PeaceExecutionError(
                    "PUBLIC_QUERY_CONTAINS_PRIVATE_IDENTIFIER",
                    "war discovery exposed native-only fields")

            execution_parameters = _build_parameters(
                args.action, war_id, args.amount,
                selected_province_ids[0] if selected_province_ids else None,
                args.beneficiary, args.direction,
                province_ids=selected_province_ids,
                with_money=args.with_money,
                with_reparations=args.with_reparations,
                with_trade_power=args.trade_power,
                trade_power_source=args.trade_power_source,
                annul_country=args.annul_country,
                annul_partners=args.annul_partners,
                special_country=args.special_country,
                special_beneficiary=args.special_beneficiary)
            effective_beneficiary = args.beneficiary
            effective_trade_power_source = None
            effective_trade_power_beneficiary = None
            effective_conceding_country = None
            effective_concede_beneficiary = None
            effective_province_ids = list(selected_province_ids or [])
            if args.action in ("cede_province", "war_reparations"):
                effective_term = _term_for_action(
                    execution_parameters, "cede_province")
                if isinstance(effective_term, dict):
                    effective_beneficiary = effective_term.get("beneficiary")
                    term_ids = effective_term.get("province_ids")
                    if isinstance(term_ids, list):
                        effective_province_ids = list(term_ids)
            if args.action == _TRADE_POWER_ACTION and not effective_province_ids:
                effective_term = _term_for_action(
                    execution_parameters, _TRADE_POWER_ACTION)
                if isinstance(effective_term, dict):
                    effective_beneficiary = effective_term.get("beneficiary")
            effective_trade_term = _term_for_action(
                execution_parameters, _TRADE_POWER_ACTION)
            if isinstance(effective_trade_term, dict):
                effective_trade_power_source = effective_trade_term.get("source")
                effective_trade_power_beneficiary = effective_trade_term.get(
                    "beneficiary")
            effective_concede_term = _term_for_action(
                execution_parameters, _CONCEDE_DEFEAT_ACTION)
            if isinstance(effective_concede_term, dict):
                effective_conceding_country = effective_concede_term.get(
                    "conceding_country")
                effective_concede_beneficiary = effective_concede_term.get(
                    "beneficiary")
            effective_annul_country = None
            effective_annul_partners: list[str] = []
            effective_annul_term = _term_for_action(
                execution_parameters, _ANNUL_TREATIES_ACTION)
            if isinstance(effective_annul_term, dict):
                effective_annul_country = effective_annul_term.get("country")
                raw_partners = effective_annul_term.get("treaty_partners")
                if isinstance(raw_partners, list):
                    effective_annul_partners = list(raw_partners)
            effective_special_country = None
            effective_special_beneficiary = None
            effective_special_term = _term_for_action(
                execution_parameters, args.action)
            if args.action in _SPECIAL_ACTIONS and isinstance(effective_special_term, dict):
                effective_special_country = effective_special_term.get("country")
                effective_special_beneficiary = effective_special_term.get("beneficiary")
            query_parameters = _query_parameters(args.action, execution_parameters)
            selected = api.inspect_diplomatic_action(
                args.action, _ACTOR, _RECIPIENT,
                phase="initiate", parameters=query_parameters)
            _write_json(evidence / "selected-inspection.json", selected)
            report["public_inspection"] = selected
            selected_contract = _selected_inspection_contract(
                selected, args.action, query_parameters, war_id)
            report["inspection_contract"] = selected_contract
            report["parameters"] = {
                "query": query_parameters,
                "execute": execution_parameters,
                "amount": args.amount,
                # Keep the old scalar field for artifact readers while the
                # complete list is the authoritative selection contract.
                "province_id": effective_province_ids[0]
                if effective_province_ids else None,
                "province_ids": effective_province_ids,
                "beneficiary": effective_beneficiary,
                "trade_power_source": effective_trade_power_source,
                "trade_power_beneficiary": effective_trade_power_beneficiary,
                "conceding_country": effective_conceding_country,
                "concede_beneficiary": effective_concede_beneficiary,
                "annul_country": effective_annul_country,
                "annul_partners": effective_annul_partners,
                "special_country": effective_special_country,
                "special_beneficiary": effective_special_beneficiary,
                "direction": args.direction,
                "with_money": args.with_money,
                "with_reparations": args.with_reparations,
                "with_trade_power": (
                    args.trade_power or args.action == _TRADE_POWER_ACTION),
            }
            if not selected_contract["valid"]:
                raise PeaceExecutionError(
                    "SELECTED_INSPECTION_INCOMPLETE",
                    "selected public Peace inspection did not prove full context")

            log_start = log_path.stat().st_size
            report["execute_call_count"] = 1
            report["request_attempt_count"] = 1
            try:
                submission = api.execute_diplomatic_action(
                    args.request_id, args.action, _ACTOR, _RECIPIENT,
                    phase="initiate", parameters=execution_parameters)
            except Exception as error:
                submission = {
                    "status": "unknown",
                    "submitted": False,
                    "game_outcome": "unknown",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            report["submission"] = submission
            report["business_submission"] = (
                isinstance(submission, dict) and submission.get("submitted") is True)
            report["business_submission_count"] = (
                1 if report["business_submission"] else 0)
            poll = _poll_result(api, args.request_id)
            report["poll"] = poll
            report["result"] = poll.get("final")
            try:
                after_discovery = api.inspect_diplomatic_action(
                    _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                    phase="initiate", parameters={})
            except Exception as error:
                after_discovery = {
                    "status": "unknown",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            _write_json(evidence / "war-discovery-after.json", after_discovery)
            report["war_discovery_after"] = after_discovery

        after = _run_snapshots(session, evidence / "after" / "probes")
        health_after = session.health()
        after_control = _control_summary(after["control_state"]["snapshot"])
        report["after"] = {
            "health": health_after,
            "control": after_control,
            "probes": _public_probe_records(after),
            "war_state": _war_pair_summary_for(after),
        }
        public = _public_result(report.get("result"))
        before_war = _war_pair_summary_for(before)
        after_war = _war_pair_summary_for(after)
        result_contract = _result_contract(
            report.get("result"), args.action, execution_parameters,
            expected_date_raw, before_war, after_war)
        report["result_contract"] = result_contract
        report["native_effects"] = result_contract.get("native_effects")
        report["effects_contract"] = result_contract.get("effects_contract")
        report["snapshot_observations"] = {
            "semantic_stability": _snapshot_stability(before, after),
            "note": "和平执行可以改变战争状态；稳定性仅记录事实，不作为全快照相等要求。",
        }
        outcome = public.get("outcome") if isinstance(public, dict) else None
        control_checks = _control_invariants(
            before_control, after_control, expected_date_raw, before, after)
        checks: dict[str, bool] = {
            "preflight_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "session_identity_bound": report["preflight_identity"].get(
                "session_matches_installation") is True,
            "creation_identity_bound": report["preflight_identity"].get(
                "creation_matches_installation") is True,
            "dll_identity_bound": report["preflight_identity"].get(
                "dll_matches_installation_and_build") is True,
            "before_four_snapshots_complete": control_checks["before_four_snapshots_complete"],
            "before_war_pair_at_war": before_war.get("complete") is True
            and before_war.get("pair_at_war") is True,
            "public_war_discovery_contract": _public_context_contract(
                discovery, _ACTOR, _RECIPIENT),
            "public_war_discovery_one_war": (
                _single_discovered_war_id(discovery, _ACTOR, _RECIPIENT) == war_id),
            "selected_inspection_contract": selected_contract.get("valid") is True,
            "execute_called_once": report["execute_call_count"] == 1,
            "request_id_bound": isinstance(report.get("request_id"), str),
            "after_four_snapshots_complete": control_checks["after_four_snapshots_complete"],
            "por_paused_same_date": control_checks["after_por_paused_same_date"],
            "after_health_ready": health_after.get("status") == "ready"
            and health_after.get("complete") is True,
            "native_result_contract": result_contract.get("all") is True,
            "after_war_matches_native_result": (
                outcome in ("executed", "accepted", "rejected")
                and result_contract.get("checks", {}).get("war_transition") is True),
            "no_replay_or_world_control": (
                report["execute_call_count"] == 1
                and report["advance_requested"] is False
                and report["save_requested"] is False
                and report["restart_requested"] is False
                and report["installation_requested"] is False),
        }
        report["checks"] = checks
        if outcome == "unknown" or not poll.get("terminal"):
            report["status"] = "unknown"
        else:
            report["status"] = "passed" if all(checks.values()) else "failed"
    except PeaceExecutionError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:  # retain bounded diagnostics for operator review
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_PEACE_OUTBOUND_EXECUTION_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start is not None:
            if log_path is None:
                try:
                    log_path = (Path(str(args.installation)).expanduser().resolve().parent
                                / "control-probe.jsonl")
                except (OSError, ValueError):
                    log_path = None
            if log_path is not None and log_path.is_file() and evidence is not None:
                report["native_events"] = _copy_log_slice(
                    log_path, log_start, evidence / "native-events-slice.jsonl")
        # A native submission-result event is the only evidence used for wire
        # publication/consumption.  It is deliberately kept separate from
        # the API business-submission acknowledgement: a consumed request can
        # still be rejected before business transport is accepted.
        try:
            wire = _wire_submission_correlation(report)
            report["wire_submission"] = wire
            report["wire_published"] = wire.get("wire_published")
            report["wire_consumed"] = wire.get("wire_consumed")
            report["wire_publish_count"] = wire.get("wire_publish_count", 0)
            report["wire_consume_count"] = wire.get("wire_consume_count", 0)
            report["request_publish_count"] = report["wire_publish_count"]
            report["business_transport_submitted"] = wire.get(
                "transport_submitted")
        except Exception as error:  # keep final report even if correlation is unavailable
            report["wire_submission"] = {
                "status": "unknown",
                "error": f"{type(error).__name__}: {error}",
                "wire_publish_count": 0,
                "wire_consume_count": 0,
            }
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path) if report_path is not None else None,
        "request_id": args.request_id,
        "execute_call_count": report.get("execute_call_count"),
        "result_status": (report.get("result") or {}).get("status")
        if isinstance(report.get("result"), dict) else None,
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
