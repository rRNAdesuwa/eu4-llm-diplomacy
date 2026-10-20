#!/usr/bin/env python3
"""Validate a saved Peace response after a fresh read-only reload.

The source execution and save-observer reports are immutable evidence.  This
validator starts no process, publishes no request, advances no date, and
does not save the game.  It reads the already running observer installation,
captures the four bounded probes, verifies the saved file hash, and checks
the new process's native pending-recovery summary.  The historical public
incoming catalog is deliberately not used to decide whether a pending offer
is active.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
import work.run_peace_inbound_response as _peace_response  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_peace_inbound_response import (  # noqa: E402
    _find_public_response,
    _peace_context_contract,
    _public_effect_contract,
    _run_role_snapshots,
    _war_pair_summary,
)
from work.peace_reload_capital import (
    _native_special_runtime, _bind_special_capital_save_observation,
)
from work.validate_peace_outbound_reload import (  # noqa: E402
    _compare_effect_states,
    _compare_concede_defeat_effect_state,
    _compare_annul_treaties_effect_state,
    _compare_special_effect_state,
    _compare_rejected_reparations_state,
    _compare_rejected_trade_power_state,
    _run_effect_probe,
    _stream_save_effect_state,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _hash_file,
    _read_json,
    _run_snapshots,
    _write_json,
)


_ACTOR = "ENG"
_RECIPIENT = "FRA"
_FAMILY = "peace"
_ACTION = "peace_offer"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_EVENT_LOG_BYTES = 10 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_COUNTRY_TAG_RE = re.compile(r"[A-Z][A-Z0-9_]{1,5}\Z")


class ReloadValidationError(RuntimeError):
    """A bounded validation failure with a stable diagnostic code."""


def _resolve_report(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise ReloadValidationError(f"REPORT_NOT_FILE:{resolved}")
    return resolved


def _all_true(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and all(item is True for item in value.values())


def _output_paths(requested: Path) -> tuple[Path, Path]:
    """Return an untouched report path and a fresh evidence directory."""

    target = requested.expanduser().resolve()
    if target.exists():
        raise ReloadValidationError(f"OUTPUT_ALREADY_EXISTS:{target}")
    if target.suffix.casefold() == ".json":
        report_path = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        evidence = target
        report_path = target / "report.json"
    if evidence.exists() or report_path.exists():
        raise ReloadValidationError(f"OUTPUT_ALREADY_EXISTS:{report_path}")
    evidence.mkdir(parents=True, exist_ok=False)
    return report_path, evidence


def _source_probe_set(payload: dict[str, object], phase: str) -> dict[str, dict[str, object]]:
    section = payload.get(phase)
    records = section.get("probes") if isinstance(section, dict) else None
    if not isinstance(records, dict):
        return {}
    result: dict[str, dict[str, object]] = {}
    for name, record in records.items():
        if not isinstance(record, dict):
            continue
        item = dict(record)
        path = item.get("snapshot_path")
        if isinstance(path, str):
            snapshot_path = Path(path)
            if snapshot_path.is_file():
                try:
                    snapshot = _read_json(snapshot_path, maximum=_MAX_METADATA_BYTES)
                except ReloadValidationError:
                    snapshot = None
                if isinstance(snapshot, dict):
                    item["snapshot"] = snapshot
        result[str(name)] = item
    return result


def _source_probe_contract(payload: dict[str, object]) -> dict[str, object]:
    before = _source_probe_set(payload, "before")
    after = _source_probe_set(payload, "after")
    before_report = payload.get("before")
    after_report = payload.get("after")
    before_complete = (
        isinstance(before_report, dict)
        and isinstance(before_report.get("probes"), dict)
        and _snapshots_complete(before_report["probes"])
    )
    after_complete = (
        isinstance(after_report, dict)
        and isinstance(after_report.get("probes"), dict)
        and _snapshots_complete(after_report["probes"])
    )
    return {
        "before": before,
        "after": after,
        "before_complete": before_complete,
        "after_complete": after_complete,
        "four_probe_names": set(after) == {"alliance_state", "control_state", "diplomats", "war_state"},
    }


def _source_public_response(payload: dict[str, object]) -> dict[str, object] | None:
    """Return the response projection from the immutable result artifact."""

    result = payload.get("result")
    response = _find_public_response(result)
    if isinstance(response, dict):
        return response
    # Keep a compatibility fallback for reports written before the nested
    # result traversal was added.  This is still the projection extracted from
    # the result artifact, never a reconstruction from request body terms.
    public = payload.get("public_response")
    if isinstance(public, dict) and isinstance(public.get("peace_context"), dict):
        return public
    if (isinstance(result, dict) and isinstance(result.get("peace_context"), dict)
            and result.get("action_id") == _ACTION):
        return result
    return None


def _execution_roles(payload: dict[str, object]) -> tuple[str, str] | None:
    """Derive proposer/decision-country from immutable response evidence."""

    candidates: list[object] = [payload]
    for key in ("execution", "result", "public_response"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value)
            context = value.get("peace_context")
            if isinstance(context, dict):
                candidates.append(context)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        actor = item.get("actor", item.get("proposer",
                                            item.get("original_actor")))
        recipient = item.get("recipient", item.get("original_recipient"))
        if (isinstance(actor, str) and _COUNTRY_TAG_RE.fullmatch(actor)
                and isinstance(recipient, str)
                and _COUNTRY_TAG_RE.fullmatch(recipient)
                and actor != recipient):
            return actor, recipient
    return None


def _source_effect_contract(
        response: object, decision: object,
        trade_power_pair: tuple[str, str] | None = None,
        ) -> dict[str, object]:
    """Validate source R/T/C roles and effects from the public result object."""

    response_object = response if isinstance(response, dict) else None
    context = response_object.get("peace_context") \
        if isinstance(response_object, dict) else None
    context_checks = _peace_context_contract(
        context, str(decision), trade_power_pair)
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
    nonwhite_ids = {
        term.get("action_id") for term in terms if isinstance(term, dict)
        and term.get("action_id") != "white_peace"
    }
    effects = response_object.get("effects") \
        if isinstance(response_object, dict) else None
    reparations = effects.get("war_reparations") \
        if isinstance(effects, dict) else None
    trade_power = effects.get("transfer_trade_power") \
        if isinstance(effects, dict) else None
    concede_defeat = effects.get("concede_defeat") \
        if isinstance(effects, dict) else None
    annul_treaties = effects.get("annul_treaties") \
        if isinstance(effects, dict) else None
    reparations_pair = None
    if r_terms:
        payer = r_terms[0].get("payer")
        claimant = r_terms[0].get("claimant")
        if (isinstance(payer, str) and _COUNTRY_TAG_RE.fullmatch(payer)
                and isinstance(claimant, str)
                and _COUNTRY_TAG_RE.fullmatch(claimant)
                and payer != claimant):
            reparations_pair = (payer, claimant)
    requested_trade_power_pair = None
    if t_terms:
        source = t_terms[0].get("source")
        beneficiary = t_terms[0].get("beneficiary")
        if (isinstance(source, str) and _COUNTRY_TAG_RE.fullmatch(source)
                and isinstance(beneficiary, str)
                and _COUNTRY_TAG_RE.fullmatch(beneficiary)
                and source != beneficiary):
            requested_trade_power_pair = source, beneficiary
    concede_defeat_pair = None
    if c_terms:
        conceding = c_terms[0].get("conceding_country")
        beneficiary = c_terms[0].get("beneficiary")
        if (isinstance(conceding, str) and _COUNTRY_TAG_RE.fullmatch(conceding)
                and isinstance(beneficiary, str)
                and _COUNTRY_TAG_RE.fullmatch(beneficiary)
                and conceding != beneficiary):
            concede_defeat_pair = conceding, beneficiary
    annul_treaties_pairs: list[tuple[str, str]] | None = None
    if a_terms:
        country = a_terms[0].get("country")
        partners = a_terms[0].get("treaty_partners")
        if (isinstance(country, str)
                and _COUNTRY_TAG_RE.fullmatch(country) is not None
                and isinstance(partners, list)
                and 1 <= len(partners) <= 16
                and all(isinstance(item, str)
                        and _COUNTRY_TAG_RE.fullmatch(item) is not None
                        for item in partners)
                and len(set(partners)) == len(partners)
                and partners == sorted(partners)
                and country not in partners):
            annul_treaties_pairs = [(country, partner) for partner in partners]
    special_pairs: dict[str, tuple[str, str] | None] = {}
    for action, action_terms in (("humiliate_rival", h_terms),
                                 ("show_strength", s_terms),
                                 ("force_religion", f_terms)):
        if action_terms:
            country = action_terms[0].get("country")
            beneficiary = action_terms[0].get("beneficiary")
            if (isinstance(country, str) and _COUNTRY_TAG_RE.fullmatch(country)
                    and isinstance(beneficiary, str)
                    and _COUNTRY_TAG_RE.fullmatch(beneficiary)
                    and country != beneficiary):
                special_pairs[action] = country, beneficiary
            else:
                special_pairs[action] = None
    mixed = len(nonwhite_ids) > 1
    supported_mixed = (
        ("concede_defeat" in nonwhite_ids
         and nonwhite_ids <= {
             "demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties",
             "humiliate_rival", "show_strength", "force_religion"})
        or nonwhite_ids <= {
            "war_reparations", "transfer_trade_power", "concede_defeat",
            "annul_treaties", "humiliate_rival", "show_strength",
            "force_religion"})
    effect_contract = _public_effect_contract(
        response_object, str(decision), trade_power_pair)
    checks: dict[str, bool] = {
        "response_object": response_object is not None,
        "context_contract": all(context_checks.values()),
        "context_scope_supported": context_checks.get("effect_scope_supported") is True,
        "reparations_term_unique": len(r_terms) == 1 if r_terms else True,
        "reparations_pair": reparations_pair is not None if r_terms else True,
        "trade_power_term_unique": len(t_terms) == 1 if t_terms else True,
        "trade_power_pair": requested_trade_power_pair is not None if t_terms else True,
        "concede_defeat_term_unique": len(c_terms) == 1 if c_terms else True,
        "concede_defeat_pair": concede_defeat_pair is not None if c_terms else True,
        "annul_treaties_unique": len(a_terms) == 1 if a_terms else True,
        "annul_treaties_pair": (
            annul_treaties_pairs is not None if a_terms else True),
        "special_unique": all(len(items) <= 1 for items in (h_terms, s_terms, f_terms)),
        "special_pairs": all(
            special_pairs.get(action) is not None
            for action, items in (("humiliate_rival", h_terms),
                                  ("show_strength", s_terms),
                                  ("force_religion", f_terms)) if items),
        "mixed_scope_rejected": not mixed or supported_mixed,
        "public_effect_contract": effect_contract.get("all") is True,
    }
    if r_terms:
        accepted = decision == "accept"
        checks.update({
            "effects_object": isinstance(effects, dict),
            "reparations_object": isinstance(reparations, dict),
            "reparations_roles": (
                isinstance(reparations, dict) and reparations_pair is not None
                and reparations.get("payer") == reparations_pair[0]
                and reparations.get("claimant") == reparations_pair[1]),
            "reparations_state_fields": (
                isinstance(reparations, dict)
                and isinstance(reparations.get("active_before"), bool)
                and isinstance(reparations.get("active_after"), bool)
                and isinstance(reparations.get("verified"), bool)),
            "reparations_dates_complete": (
                isinstance(reparations, dict)
                and type(reparations.get("start_date_raw")) is int
                and type(reparations.get("end_date_raw")) is int),
            "reparations_outcome_state": (
                isinstance(reparations, dict)
                and reparations.get("verified") is accepted
                and (not accepted or (
                    reparations.get("active_before") is False
                    and reparations.get("active_after") is True))),
        })
    if t_terms:
        accepted = decision == "accept"
        checks.update({
            "transfer_trade_power_object": isinstance(trade_power, dict),
            "transfer_trade_power_roles": (
                isinstance(trade_power, dict)
                and requested_trade_power_pair is not None
                and trade_power.get("source") == requested_trade_power_pair[0]
                and trade_power.get("beneficiary") == requested_trade_power_pair[1]),
            "transfer_trade_power_outcome_state": (
                isinstance(trade_power, dict)
                and trade_power.get("verified") is accepted),
        })
    if c_terms:
        accepted = decision == "accept"
        c_fields = (
            "conceding_prestige_before_raw", "conceding_prestige_after_raw",
            "conceding_prestige_delta_raw", "beneficiary_prestige_before_raw",
            "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw")
        checks.update({
            "concede_defeat_object": isinstance(concede_defeat, dict),
            "concede_defeat_roles": (
                isinstance(concede_defeat, dict)
                and concede_defeat_pair is not None
                and concede_defeat.get("conceding_country") == concede_defeat_pair[0]
                and concede_defeat.get("beneficiary") == concede_defeat_pair[1]),
            "concede_defeat_scale1000": (
                isinstance(concede_defeat, dict)
                and concede_defeat.get("prestige_scale") == 1000),
            "concede_defeat_values_readable": (
                isinstance(concede_defeat, dict)
                and concede_defeat.get("values_readable") is True),
            "concede_defeat_verified": (
                isinstance(concede_defeat, dict)
                and concede_defeat.get("verified") is accepted),
        })
        checks.update({
            f"concede_defeat_{field}": (
                isinstance(concede_defeat, dict)
                and type(concede_defeat.get(field)) is int
                and not isinstance(concede_defeat.get(field), bool))
            for field in c_fields
        })
        checks.update({
            "concede_defeat_conceding_delta_consistent": (
                isinstance(concede_defeat, dict)
                and type(concede_defeat.get("conceding_prestige_before_raw")) is int
                and type(concede_defeat.get("conceding_prestige_after_raw")) is int
                and type(concede_defeat.get("conceding_prestige_delta_raw")) is int
                and concede_defeat.get("conceding_prestige_delta_raw") ==
                concede_defeat.get("conceding_prestige_after_raw") -
                concede_defeat.get("conceding_prestige_before_raw")),
            "concede_defeat_beneficiary_delta_consistent": (
                isinstance(concede_defeat, dict)
                and type(concede_defeat.get("beneficiary_prestige_before_raw")) is int
                and type(concede_defeat.get("beneficiary_prestige_after_raw")) is int
                and type(concede_defeat.get("beneficiary_prestige_delta_raw")) is int
                and concede_defeat.get("beneficiary_prestige_delta_raw") ==
                concede_defeat.get("beneficiary_prestige_after_raw") -
                concede_defeat.get("beneficiary_prestige_before_raw")),
        })
    if a_terms:
        accepted = decision == "accept"
        rows = annul_treaties if isinstance(annul_treaties, list) else []
        expected_pairs = set(annul_treaties_pairs or [])
        row_pairs = {(row.get("country"), row.get("partner"))
                     for row in rows if isinstance(row, dict)}
        a_checks: dict[str, bool] = {
            "annul_treaties_object": isinstance(annul_treaties, list),
            "annul_treaties_pairs_exact": (
                len(rows) == len(expected_pairs) and row_pairs == expected_pairs),
        }
        for index, pair in enumerate(annul_treaties_pairs or []):
            row = next((item for item in rows
                        if isinstance(item, dict)
                        and (item.get("country"), item.get("partner")) == pair), None)
            prefix = f"annul_treaties_{index}"
            a_checks.update({
                f"{prefix}_dates": isinstance(row, dict)
                and type(row.get("start_date_raw")) is int
                and type(row.get("end_date_raw")) is int,
                f"{prefix}_values": isinstance(row, dict)
                and type(row.get("present_before")) is bool
                and type(row.get("present_after")) is bool
                and type(row.get("alliance_before")) is bool
                and type(row.get("alliance_after")) is bool
                and row.get("values_readable") is True,
                f"{prefix}_verified": isinstance(row, dict)
                and row.get("verified") is accepted,
            })
            if accepted:
                a_checks[f"{prefix}_applied"] = (
                    isinstance(row, dict)
                    and row.get("present_after") is True
                    and row.get("alliance_after") is False)
        checks.update(a_checks)
    special_effects = {action: effects.get(action) if isinstance(effects, dict) else None
                       for action in ("humiliate_rival", "show_strength", "force_religion")}
    for action, items in (("humiliate_rival", h_terms),
                          ("show_strength", s_terms),
                          ("force_religion", f_terms)):
        if not items:
            continue
        effect = special_effects[action]
        pair = special_pairs.get(action)
        accepted = decision == "accept"
        checks.update({
            f"{action}_object": isinstance(effect, dict),
            f"{action}_pair": isinstance(effect, dict) and pair is not None
            and effect.get("country") == pair[0]
            and effect.get("beneficiary") == pair[1],
            f"{action}_values_readable": isinstance(effect, dict)
            and effect.get("values_readable") is True,
            f"{action}_verified": isinstance(effect, dict)
            and effect.get("verified") is accepted,
        })
    if not c_terms:
        checks["legacy_non_reparations_scope"] = True
    return {
        "checks": checks,
        "all": all(checks.values()),
        "applicable": bool(r_terms or t_terms or c_terms or a_terms
                            or h_terms or s_terms or f_terms),
        "mixed": mixed,
        "context": context,
        "effects": effects,
        "reparations_pair": reparations_pair,
        "reparations_effect": reparations,
        "trade_power_pair": requested_trade_power_pair,
        "trade_power_effect": trade_power,
        "concede_defeat_pair": concede_defeat_pair,
        "concede_defeat_effect": concede_defeat,
        "annul_treaties_pairs": annul_treaties_pairs,
        "annul_treaties_effect": annul_treaties,
        "special_pairs": special_pairs,
        "special_effects": special_effects,
        "source_date_raw": response_object.get("date_raw")
        if isinstance(response_object, dict) else None,
        "public_response": response_object,
    }


def _source_contract(
        payload: dict[str, object],
        trade_power_pair: tuple[str, str] | None = None,
        ) -> dict[str, object]:
    native = payload.get("native_response")
    response_event = native.get("response_event") if isinstance(native, dict) else None
    result = payload.get("result")
    checks = payload.get("checks")
    decision = payload.get("decision")
    expected_after = decision == "reject"
    response = _source_public_response(payload)
    effects = _source_effect_contract(response, decision, trade_power_pair)
    # The explicit decision is the only source for the expected war transition.
    checks_out: dict[str, bool] = {
        "status_passed": payload.get("status") == "passed",
        "checks_passed": _all_true(checks),
        "action_family": payload.get("action_id") == _ACTION
        and payload.get("family") == _FAMILY,
        "actor_recipient": payload.get("actor") == _ACTOR
        and payload.get("recipient") == _RECIPIENT,
        "decision_supported": decision in ("accept", "reject"),
        "result_object": isinstance(result, dict),
        "result_effect_contract": effects.get("all") is True,
        "native_response_contract": isinstance(native, dict)
        and native.get("contract") is True
        and native.get("full_payload") is True
        and native.get("response_verified") is True
        and native.get("request_binding_verified") is True
        and native.get("handler_forwarded") is True
        and native.get("handler_consumed") is True
        and native.get("pending_removed") is True,
        "response_binding": isinstance(response_event, dict)
        and response_event.get("event") == "native_peace_inbound_response_result"
        and response_event.get("family") == _FAMILY
        and response_event.get("action_id") == _ACTION
        and response_event.get("actor") == _ACTOR
        and response_event.get("recipient") == _RECIPIENT
        and response_event.get("phase") == decision
        and response_event.get("request_id") == payload.get("request_id")
        and response_event.get("session_id") == (
            payload.get("session", {}).get("session_id")
            if isinstance(payload.get("session"), dict) else None
        )
        and response_event.get("war_before") is True
        and response_event.get("war_after") is (expected_after if decision in ("accept", "reject") else None),
    }
    return {
        "checks": checks_out,
        "all": all(checks_out.values()),
        "decision": decision,
        "expected_pair_at_war_after": False if decision == "accept" else True if decision == "reject" else None,
        "source_session_id": payload.get("session", {}).get("session_id")
        if isinstance(payload.get("session"), dict) else None,
        "source_date_raw": (
            payload.get("after", {}).get("control", {}).get("date_raw")
            if isinstance(payload.get("after"), dict)
            and isinstance(payload["after"].get("control"), dict) else None
        ),
        "native_response": native,
        "public_response": response,
        "peace_context": effects.get("context"),
        "effects": effects.get("effects"),
        "effects_summary": effects,
        "reparations_pair": effects.get("reparations_pair"),
        "trade_power_pair": effects.get("trade_power_pair"),
        "concede_defeat_pair": effects.get("concede_defeat_pair"),
        "annul_treaties_pairs": effects.get("annul_treaties_pairs"),
        "source_result_date_raw": effects.get("source_date_raw"),
    }


def _save_contract(save_report: dict[str, object]) -> dict[str, object]:
    save = save_report.get("save")
    reported_hash = save.get("sha256") if isinstance(save, dict) else None
    save_path = save.get("path") if isinstance(save, dict) else None
    name = save_report.get("name")
    checks = {
        "report_success": save_report.get("status") == "success",
        "save_object": isinstance(save, dict),
        "name_is_eu4_basename": isinstance(name, str)
        and Path(name).name == name and name.casefold().endswith(".eu4"),
        "reported_hash_valid": isinstance(reported_hash, str)
        and _SHA256_RE.fullmatch(reported_hash) is not None,
        "reported_path_valid": isinstance(save_path, str)
        and Path(save_path).is_file(),
    }
    current = None
    if checks["reported_path_valid"]:
        current = _hash_file(Path(str(save_path)), maximum=_MAX_SAVE_BYTES)
    actual_hash = current.get("sha256") if isinstance(current, dict) else None
    checks["actual_hash_matches_report"] = (
        checks["reported_hash_valid"] is True
        and actual_hash is not None
        and str(actual_hash).casefold() == str(reported_hash).casefold()
    )
    return {
        "checks": checks,
        "all": all(checks.values()),
        "name": name,
        "reported": {"path": save_path, "sha256": reported_hash},
        "actual": current,
    }


def _source_map(value: object) -> dict[str, str] | None:
    """Validate and normalize a complete manifest source map.

    Manifest size is deliberately not part of the contract.  Builds may add
    sources while retaining the same ABI, so completeness means that every
    listed row has a non-empty unique name and a legal SHA-256 digest.
    """

    if not isinstance(value, list) or not value:
        return None
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        digest = item.get("sha256")
        if (not isinstance(name, str) or not name.strip()
                or not isinstance(digest, str)):
            return None
        if _SHA256_RE.fullmatch(digest) is None or name in result:
            return None
        result[name] = digest.casefold()
    return result if result else None


def _binding_contract(source: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    source_manifest = source.get("build_manifest")
    current_manifest = current.get("build_manifest")
    source_map = _source_map(source_manifest.get("sources") if isinstance(source_manifest, dict) else None)
    current_map = _source_map(current_manifest.get("sources") if isinstance(current_manifest, dict) else None)
    source_build = source.get("build_binding")
    current_build = current.get("build_binding")
    source_dll = source.get("session", {}).get("dll_sha256") if isinstance(source.get("session"), dict) else None
    current_installation = current.get("installation")
    current_dll = (
        current_installation.get("declared_dll_sha256")
        if isinstance(current_installation, dict)
        else None
    )
    if not isinstance(current_dll, str) and isinstance(current_build, dict):
        current_dll = current_build.get("installation_dll_sha256")
    checks = {
        "source_manifest_map_complete": source_map is not None,
        "reload_manifest_map_complete": current_map is not None,
        "source_reload_source_hashes_equal": (
            source_map is not None and current_map is not None
            and source_map == current_map),
        "source_build_matches_dll": isinstance(source_build, dict)
        and source_build.get("installation_matches_build_manifest") is True,
        "reload_build_matches_dll": isinstance(current_build, dict)
        and current_build.get("installation_matches_build_manifest") is True,
        "dll_sha256_equal": isinstance(source_dll, str)
        and isinstance(current_dll, str)
        and source_dll.casefold() == current_dll.casefold(),
    }
    return {
        "checks": checks,
        "all": all(checks.values()),
        "source_dll_sha256": source_dll,
        "reload_dll_sha256": current_dll,
        "source_source_count": len(source_map) if source_map is not None else None,
        "reload_source_count": len(current_map) if current_map is not None else None,
    }


_QUEUE_DESCRIPTOR_FIELDS = (
    "action_id", "family", "actor", "recipient", "decision_country",
)


def _queue_descriptor(event: dict[str, object]) -> dict[str, object]:
    """Project one restored queue entry to stable semantic fields.

    Proposal ids and native pointers are process-local.  The reload contract
    therefore compares action/family/roles, while retaining the full selected
    event in the bounded evidence file when a caller needs to inspect it.
    """

    return {key: event.get(key) for key in _QUEUE_DESCRIPTOR_FIELDS}


def _queue_descriptor_key(value: dict[str, object]) -> tuple[object, ...]:
    return tuple(value.get(key) for key in _QUEUE_DESCRIPTOR_FIELDS)


def _source_other_queue(
        execution: dict[str, object], actor: str, recipient: str,
        ) -> dict[str, object]:
    """Read the source process's restored queue set without replaying it.

    The source response report exposes the response outcome, but its public
    catalog may lag behind the native queue.  The source process's bounded
    control-probe log records every saved-pending entry restored before that
    response.  Removing the target peace entry from that set leaves the
    natural entries that should still exist after a fresh reload.
    """

    installation = execution.get("installation")
    installation_path: object = (
        installation.get("path") if isinstance(installation, dict) else installation)
    if not isinstance(installation_path, str):
        return {
            "available": False,
            "reason": "source_installation_path_missing",
            "expected_other_queue": [],
        }
    log_path = Path(installation_path).expanduser().resolve().parent / "control-probe.jsonl"
    if not log_path.is_file():
        return {
            "available": False,
            "reason": "source_recovery_log_missing",
            "path": str(log_path),
            "expected_other_queue": [],
        }
    size = log_path.stat().st_size
    if size > _MAX_EVENT_LOG_BYTES:
        return {
            "available": False,
            "reason": "source_recovery_log_too_large",
            "path": str(log_path),
            "bytes": size,
            "expected_other_queue": [],
        }
    source_session = execution.get("session")
    source_session_id = (
        source_session.get("session_id")
        if isinstance(source_session, dict) else None)
    digest = hashlib.sha256()
    restored: list[dict[str, object]] = []
    invalid_lines = 0
    line_count = 0
    with log_path.open("rb") as stream:
        for raw in stream:
            line_count += 1
            digest.update(raw)
            if len(raw) > 256 * 1024:
                invalid_lines += 1
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid_lines += 1
                continue
            if not isinstance(event, dict):
                continue
            if event.get("event") != "native_diplomacy_inbound_pending_restored":
                continue
            if (isinstance(source_session_id, str)
                    and event.get("session_id") != source_session_id):
                continue
            restored.append(event)
    target = {
        "action_id": _ACTION,
        "family": _FAMILY,
        "actor": actor,
        "recipient": recipient,
    }
    other: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for event in restored:
        descriptor = _queue_descriptor(event)
        is_target = all(
            descriptor.get(key) == value for key, value in target.items())
        if is_target:
            continue
        key = _queue_descriptor_key(descriptor)
        if key in seen:
            continue
        seen.add(key)
        other.append(descriptor)
    return {
        "available": True,
        "path": str(log_path),
        "bytes": size,
        "sha256": digest.hexdigest(),
        "line_count": line_count,
        "invalid_line_count": invalid_lines,
        "source_session_id": source_session_id,
        "restored_event_count": len(restored),
        "target_entries_removed_from_expected": sum(
            1 for event in restored
            if all(_queue_descriptor(event).get(key) == value
                   for key, value in target.items())),
        "expected_other_queue": other,
    }


def _stream_recovery_log(
        path: Path, session_id: str, expected_date: int, output: Path,
        actor: str, recipient: str,
        source_queue: dict[str, object],
        ) -> dict[str, object]:
    """Read only the bounded native recovery records from the fresh process."""

    if not path.is_file():
        raise ReloadValidationError(f"RECOVERY_LOG_MISSING:{path}")
    size = path.stat().st_size
    if size > _MAX_EVENT_LOG_BYTES:
        raise ReloadValidationError(f"RECOVERY_LOG_TOO_LARGE:{path}:{size}")
    digest = hashlib.sha256()
    installed = False
    installed_index = -1
    scan_events: list[dict[str, object]] = []
    restored_target: list[dict[str, object]] = []
    restored_all: list[dict[str, object]] = []
    current_events = 0
    invalid_lines = 0
    line_count = 0
    selected: list[dict[str, object]] = []
    with path.open("rb") as stream:
        for index, raw in enumerate(stream):
            line_count += 1
            digest.update(raw)
            if len(raw) > 256 * 1024:
                invalid_lines += 1
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid_lines += 1
                continue
            if not isinstance(event, dict):
                continue
            event_session = event.get("session_id")
            if event.get("event") == "diplomacy_observer_installed" and event_session == session_id:
                installed = True
                installed_index = index
                selected.append({"event": event, "line": index})
            if event_session == session_id:
                current_events += 1
            if index <= installed_index:
                continue
            event_name = event.get("event")
            if event_name == "native_diplomacy_saved_pending_scan_complete":
                scan_events.append(event)
                selected.append({"event": event, "line": index})
            elif (
                event_name == "native_diplomacy_inbound_pending_restored"
                and event_session == session_id
            ):
                restored_all.append(event)
                if (
                    event.get("action_id") == _ACTION
                    and event.get("family") == _FAMILY
                    and event.get("actor") == actor
                    and event.get("recipient") == recipient
                ):
                    restored_target.append(event)
                selected.append({"event": event, "line": index})
    scan = scan_events[-1] if scan_events else None
    expected_available = source_queue.get("available") is True
    expected_other = source_queue.get("expected_other_queue", [])
    if not isinstance(expected_other, list):
        expected_other = []
    current_queue = [_queue_descriptor(event) for event in restored_all]
    expected_keys = sorted(_queue_descriptor_key(item) for item in expected_other
                           if isinstance(item, dict))
    current_keys = sorted(_queue_descriptor_key(item) for item in current_queue)
    expected_count = len(expected_keys)
    if expected_available:
        queue_matches = (
            isinstance(scan, dict)
            and scan.get("native_queue_count") == expected_count
            and scan.get("restored_count") == expected_count
            and current_keys == expected_keys
        )
    else:
        # Legacy reports did not preserve the source process's restored queue
        # set; retain the old empty-queue fallback only for those reports.
        queue_matches = (
            isinstance(scan, dict)
            and scan.get("native_queue_count") == 0
            and scan.get("restored_count") == 0
            and not current_queue
        )
    scan_checks = {
        "observer_install_matches_session": installed,
        "scan_event_present": isinstance(scan, dict),
        "scan_date_matches": isinstance(scan, dict) and scan.get("date_raw") == expected_date,
        "queue_readable": isinstance(scan, dict) and scan.get("queue_readable") is True,
        "list_integrity": isinstance(scan, dict) and scan.get("list_integrity") is True,
        "queue_unchanged": isinstance(scan, dict) and scan.get("native_queue_unchanged") is True,
        # Reports predating the source-queue evidence use the documented
        # empty-queue fallback; current reports must carry the source set.
        "source_other_queue_available": (
            expected_available or source_queue.get("available") is False),
        "native_queue_matches_source": queue_matches,
        "restored_queue_matches_source": queue_matches,
        "target_not_restored": not restored_target,
    }
    selected_path = output / "native-recovery-events.json"
    _write_json(selected_path, {
        "session_id": session_id,
        "log": {"path": str(path), "bytes": size, "sha256": digest.hexdigest(),
                "line_count": line_count, "invalid_line_count": invalid_lines,
                "bounded": True},
        "selected": selected,
        "scan": scan,
        "target_restored_events": restored_target,
        "restored_queue_events": current_queue,
        "source_queue": source_queue,
    })
    return {
        "checks": scan_checks,
        "all": all(scan_checks.values()),
        "log": {"path": str(path), "bytes": size, "sha256": digest.hexdigest(),
                "line_count": line_count, "invalid_line_count": invalid_lines,
                "current_session_event_count": current_events, "bounded": True},
        "scan": scan,
        "target_restored_events": restored_target,
        "restored_queue_events": current_queue,
        "source_queue": source_queue,
        "selected_path": str(selected_path),
    }


def _war_contract(source: dict[str, object], current_probes: object,
                  expected_after: bool) -> dict[str, object]:
    source_probes = _source_probe_contract(source)
    before = _war_pair_summary(source_probes["before"])
    after = _war_pair_summary(source_probes["after"])
    current = _war_pair_summary(current_probes)
    checks = {
        "source_before_complete": before.get("complete") is True,
        "source_after_complete": after.get("complete") is True,
        "reload_complete": current.get("complete") is True,
        "source_before_at_war": before.get("pair_at_war") is True,
        "source_after_matches_decision": after.get("pair_at_war") is expected_after,
        "reload_matches_decision": current.get("pair_at_war") is expected_after,
        "source_reload_war_match": after.get("pair_at_war") == current.get("pair_at_war"),
    }
    return {"checks": checks, "all": all(checks.values()),
            "source_before": before, "source_after": after, "reload": current}


def _control_contract(source: dict[str, object], save_report: dict[str, object],
                      health: dict[str, object], current_control: dict[str, object],
                      probes: object) -> dict[str, object]:
    source_after = source.get("after") if isinstance(source.get("after"), dict) else {}
    source_control = source_after.get("control") if isinstance(source_after, dict) else {}
    save_probe = save_report.get("probe_after") if isinstance(save_report, dict) else {}
    save_signature = save_probe.get("signature") if isinstance(save_probe, dict) else {}
    expected_date = source_control.get("date_raw") if isinstance(source_control, dict) else None
    checks = {
        "source_date_integer": type(expected_date) is int,
        "health_ready": health.get("status") == "ready" and health.get("complete") is True,
        "health_date_matches_source": health.get("date_raw") == expected_date,
        "control_date_matches_source": current_control.get("date_raw") == expected_date,
        "save_probe_date_matches_source": save_signature.get("date_raw") == expected_date,
        "por_player_slot": current_control.get("player_slot") == _PLAYER_SLOT,
        "paused": current_control.get("paused_flag") == 1,
        "four_reload_probes_complete": _snapshots_complete(probes),
    }
    return {"checks": checks, "all": all(checks.values()),
            "source_control": source_control, "save_signature": save_signature,
            "reload_control": current_control}


def _peace_effect_reload_contract(source: dict[str, object],
                                  execution: dict[str, object],
                                  save_report: dict[str, object],
                                  session: ObserverSession,
                                  expected_date_raw: object,
                                  evidence: Path) -> dict[str, object]:
    """Compare inbound R/T/C results with one native probe and one save scan.

    The source effect object is taken from the public response projection.  A
    rejected R or T term is compared as an unchanged relation, so a complete
    absent native record and an empty save query are valid observations.  The
    decision itself never supplies the expected state.
    """

    summary = source.get("effects_summary")
    if not isinstance(summary, dict):
        return {"applicable": False, "all": False,
                "reason": "source_effect_summary_missing"}
    if summary.get("applicable") is not True:
        return {
            "applicable": False,
            "all": True,
            "reason": "supported_effect_terms_not_requested_legacy_scope",
            "source_effect_summary": summary,
        }
    reparations_pair = summary.get("reparations_pair")
    trade_power_pair = summary.get("trade_power_pair")
    concede_defeat_pair = summary.get("concede_defeat_pair")
    annul_treaties_pairs = summary.get("annul_treaties_pairs")
    special_pairs = summary.get("special_pairs")
    if not isinstance(special_pairs, dict):
        special_pairs = {}
    normalized_special_pairs: dict[str, tuple[str, str]] = {}
    for action, value in special_pairs.items():
        if (isinstance(value, (list, tuple)) and len(value) == 2
                and all(isinstance(tag, str) for tag in value)):
            normalized_special_pairs[action] = tuple(value)
        elif isinstance(value, dict):
            country = value.get("country")
            beneficiary = value.get("beneficiary")
            if isinstance(country, str) and isinstance(beneficiary, str):
                normalized_special_pairs[action] = country, beneficiary
    special_pairs = normalized_special_pairs
    if isinstance(reparations_pair, list):
        reparations_pair = tuple(reparations_pair)
    if isinstance(trade_power_pair, list):
        trade_power_pair = tuple(trade_power_pair)
    if isinstance(concede_defeat_pair, list):
        concede_defeat_pair = tuple(concede_defeat_pair)
    if isinstance(annul_treaties_pairs, list):
        annul_treaties_pairs = [
            tuple(item) for item in annul_treaties_pairs
            if isinstance(item, (list, tuple)) and len(item) == 2]
    if not (isinstance(reparations_pair, tuple) and len(reparations_pair) == 2
            and all(isinstance(tag, str) for tag in reparations_pair)):
        reparations_pair = None
    if not (isinstance(trade_power_pair, tuple) and len(trade_power_pair) == 2
            and all(isinstance(tag, str) for tag in trade_power_pair)):
        trade_power_pair = None
    if not (isinstance(concede_defeat_pair, tuple)
            and len(concede_defeat_pair) == 2
            and all(isinstance(tag, str) for tag in concede_defeat_pair)):
        concede_defeat_pair = None
    if not (isinstance(annul_treaties_pairs, list)
            and annul_treaties_pairs
            and all(isinstance(pair, tuple) and len(pair) == 2
                    and all(isinstance(tag, str) for tag in pair)
                    for pair in annul_treaties_pairs)):
        annul_treaties_pairs = None
    effects = summary.get("effects")
    if (reparations_pair is None and trade_power_pair is None
            and concede_defeat_pair is None
            and annul_treaties_pairs is None and not special_pairs):
        return {"applicable": True, "all": False,
                "reason": "source_effect_pair_missing",
                "source_effect_summary": summary}
    tags = list(dict.fromkeys(
        list(reparations_pair or ()) + list(trade_power_pair or ())
        + list(concede_defeat_pair or ())
        + [tag for pair in (annul_treaties_pairs or []) for tag in pair]
        + [tag for pair in special_pairs.values() for tag in pair]))
    native_probe = _run_effect_probe(
        session, tags, [], expected_date_raw,
        evidence / "probes" / "peace_effect_state.json",
        reparations_pair=reparations_pair,
        trade_power_source=(trade_power_pair[0]
                            if trade_power_pair is not None else None),
        trade_power_beneficiary=(trade_power_pair[1]
                                 if trade_power_pair is not None else None),
        annul_treaties_pairs=annul_treaties_pairs,
        special_action=(next(iter(special_pairs), None)),
        special_pair=(next(iter(special_pairs.values()), None)))
    capital_province_ids: list[int] = []
    if special_pairs:
        special_action = next(iter(special_pairs))
        special_value = next(iter(special_pairs.values()))
        special_runtime = _native_special_runtime(native_probe, special_action)
        capital_id = (
            special_runtime.get("capital_province_id")
            if isinstance(special_runtime, dict)
            and special_runtime.get("capital_province_id_verified") is True
            else None)
        if type(capital_id) is int:
            capital_province_ids.append(capital_id)
    save_probe = _stream_save_effect_state(
        save_report, tags, capital_province_ids, reparations_pair=reparations_pair,
        trade_power_source=(trade_power_pair[0]
                            if trade_power_pair is not None else None),
        trade_power_beneficiary=(trade_power_pair[1]
                                 if trade_power_pair is not None else None),
        annul_treaties_pairs=annul_treaties_pairs)
    if special_pairs:
        special_action = next(iter(special_pairs))
        special_value = next(iter(special_pairs.values()))
        _bind_special_capital_save_observation(
            save_probe, native_probe, special_action, special_value[0])
    decision = source.get("decision")
    if decision == "reject":
        relation_comparisons: dict[str, dict[str, object]] = {}
        relation_checks: dict[str, bool] = {}
        if reparations_pair is not None:
            reparations_comparison = _compare_rejected_reparations_state(
                native_probe, save_probe, effects, reparations_pair)
            relation_comparisons["war_reparations"] = reparations_comparison
            relation_checks.update(reparations_comparison.get("checks", {}))
        elif summary.get("reparations_pair") is not None:
            relation_checks["rejected_reparations_pair_available"] = False
        if trade_power_pair is not None:
            trade_power_comparison = _compare_rejected_trade_power_state(
                native_probe, save_probe, effects, trade_power_pair)
            relation_comparisons["transfer_trade_power"] = trade_power_comparison
            relation_checks.update(trade_power_comparison.get("checks", {}))
        elif summary.get("trade_power_pair") is not None:
            relation_checks["rejected_trade_power_pair_available"] = False
        if concede_defeat_pair is not None:
            concede_comparison = _compare_concede_defeat_effect_state(
                native_probe, save_probe, effects, concede_defeat_pair,
                "rejected")
            relation_comparisons["concede_defeat"] = concede_comparison
            relation_checks.update(concede_comparison.get("checks", {}))
        elif summary.get("concede_defeat_pair") is not None:
            relation_checks["rejected_concede_defeat_pair_available"] = False
        if annul_treaties_pairs is not None:
            annul_comparison = _compare_annul_treaties_effect_state(
                native_probe, save_probe, effects, annul_treaties_pairs,
                "rejected")
            relation_comparisons["annul_treaties"] = annul_comparison
            relation_checks.update(annul_comparison.get("checks", {}))
        elif summary.get("annul_treaties_pairs") is not None:
            relation_checks["rejected_annul_treaties_pair_available"] = False
        for action, pair in special_pairs.items():
            comparison = _compare_special_effect_state(
                native_probe, save_probe, effects, pair, action, "rejected")
            relation_comparisons[action] = comparison
            relation_checks.update(comparison.get("checks", {}))
        comparison = {
            "checks": relation_checks,
            "all": all(relation_checks.values()),
            **relation_comparisons,
        }
    elif decision == "accept":
        # The shared accepted comparison checks each requested R/T/C effect,
        # including C prestige values and each serialized relation.
        primary_action = (
            "annul_treaties" if annul_treaties_pairs is not None
            else "transfer_trade_power" if trade_power_pair is not None
            else "war_reparations" if reparations_pair is not None
            else "concede_defeat")
        comparison = _compare_effect_states(
            {"all": True, "by_country": {}}, native_probe, save_probe,
            effects, primary_action, [], reparations_pair, trade_power_pair,
            expected_concede_defeat_pair=concede_defeat_pair,
            expected_annul_treaties_pairs=annul_treaties_pairs,
            expected_date_raw=expected_date_raw)
        special_comparisons: dict[str, dict[str, object]] = {}
        for action, pair in special_pairs.items():
            special_comparisons[action] = _compare_special_effect_state(
                native_probe, save_probe, effects, pair, action, "accepted")
            comparison.setdefault("checks", {}).update(
                special_comparisons[action].get("checks", {}))
        comparison["special"] = special_comparisons
    else:
        comparison = {"checks": {"decision_supported": False}, "all": False}
    checks = dict(comparison.get("checks", {}))
    checks["native_effect_probe_contract"] = (
        isinstance(native_probe, dict) and native_probe.get("status") == "ok")
    checks["save_effect_stream_contract"] = (
        isinstance(save_probe, dict) and save_probe.get("status") == "ok")
    checks["source_effects_contract"] = summary.get("all") is True
    if summary.get("mixed") is True:
        # R/T/C is compared by each dedicated relation contract.  If C is
        # mixed with money/province, the shared payment/allocation comparison
        # remains responsible for those additional effects.
        checks["mixed_relation_persistence_scope"] = all(
            (not present) or pair is not None
            for present, pair in (
                (summary.get("reparations_pair") is not None, reparations_pair),
                (summary.get("trade_power_pair") is not None, trade_power_pair),
                (summary.get("concede_defeat_pair") is not None,
                 concede_defeat_pair)))
    comparison["checks"] = checks
    comparison["all"] = all(checks.values())
    return {
        "applicable": True,
        "all": comparison["all"],
        "decision": decision,
        "request_id": execution.get("request_id"),
        "tags": tags,
        "province_ids": capital_province_ids,
        "reparations_pair": (
            {"payer": reparations_pair[0], "claimant": reparations_pair[1]}
            if reparations_pair is not None else None),
        "trade_power_pair": (
            {"source": trade_power_pair[0],
             "beneficiary": trade_power_pair[1]}
            if trade_power_pair is not None else None),
        "concede_defeat_pair": (
            {"conceding_country": concede_defeat_pair[0],
             "beneficiary": concede_defeat_pair[1]}
            if concede_defeat_pair is not None else None),
        "annul_treaties_pairs": [
            {"country": pair[0], "partner": pair[1]}
            for pair in annul_treaties_pairs
        ] if annul_treaties_pairs is not None else None,
        "special_pairs": {
            action: {"country": pair[0], "beneficiary": pair[1]}
            for action, pair in special_pairs.items()
        },
        "private_native_probe": native_probe,
        "private_save_effect_scan": save_probe,
        "comparison": comparison,
        "source_effect_summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    global _ACTOR, _RECIPIENT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="新进程 installation.json")
    parser.add_argument("--execution-report", type=Path, required=True,
                        help="已完成 Peace 入站响应 report.json 或其目录")
    parser.add_argument("--save-report", type=Path, required=True,
                        help="对应 save-observer-report-*.json")
    parser.add_argument("--trade-power-source", default=None,
                        help="可选的 transfer_trade_power source 绑定，例如 FRA")
    parser.add_argument("--trade-power-beneficiary", default=None,
                        help="可选的 transfer_trade_power beneficiary 绑定，例如 ENG")
    parser.add_argument("--output", type=Path, required=True,
                        help="新的报告文件路径，或新的报告目录")
    args = parser.parse_args(argv)
    if bool(args.trade_power_source) != bool(args.trade_power_beneficiary):
        parser.error("trade-power-source and trade-power-beneficiary must be supplied together")
    trade_power_pair: tuple[str, str] | None = None
    if args.trade_power_source is not None:
        if (_COUNTRY_TAG_RE.fullmatch(args.trade_power_source) is None
                or _COUNTRY_TAG_RE.fullmatch(args.trade_power_beneficiary) is None
                or args.trade_power_source == args.trade_power_beneficiary):
            parser.error("trade-power source and beneficiary must be distinct country tags")
        trade_power_pair = args.trade_power_source, args.trade_power_beneficiary

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, object] = {
        "validator": "validate_peace_inbound_reload.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_peace_inbound_reload",
        "installation": str(args.installation),
        "execution_report": str(args.execution_report),
        "save_report": str(args.save_report),
        "trade_power_source": args.trade_power_source,
        "trade_power_beneficiary": args.trade_power_beneficiary,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "installation_requested": False,
        "checks": {},
    }
    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        execution_path = _resolve_report(args.execution_report)
        save_report_path = _resolve_report(args.save_report)
        execution = _read_json(execution_path, maximum=_MAX_METADATA_BYTES)
        save_report = _read_json(save_report_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(execution, dict):
            raise ReloadValidationError("EXECUTION_REPORT_NOT_OBJECT")
        if not isinstance(save_report, dict):
            raise ReloadValidationError("SAVE_REPORT_NOT_OBJECT")

        roles = _execution_roles(execution)
        if roles is None:
            raise ReloadValidationError("SOURCE_PEACE_ROLES_UNREADABLE")
        _ACTOR, _RECIPIENT = roles
        # The imported response contracts resolve their legacy defaults in
        # that module's globals.  Bind them to the immutable execution roles
        # before validating context/effects and before running a war probe.
        _peace_response._ACTOR = _ACTOR
        _peace_response._RECIPIENT = _RECIPIENT
        report["proposer"] = _ACTOR
        report["actor"] = _ACTOR
        report["recipient"] = _RECIPIENT

        source = _source_contract(execution, trade_power_pair)
        source_queue = _source_other_queue(execution, _ACTOR, _RECIPIENT)
        source_probes = _source_probe_contract(execution)
        save = _save_contract(save_report)
        report["source"] = {
            "path": str(execution_path),
            "sha256": _hash_file(execution_path, maximum=_MAX_METADATA_BYTES),
            "actor": _ACTOR,
            "recipient": _RECIPIENT,
            "summary": source,
            "probe_contract": {key: source_probes[key] for key in
                                ("before_complete", "after_complete", "four_probe_names")},
        }
        report["save"] = {
            "path": str(save_report_path),
            "sha256": _hash_file(save_report_path, maximum=_MAX_METADATA_BYTES),
            "summary": save,
        }
        report["source_queue"] = source_queue
        if not source["all"]:
            raise ReloadValidationError("SOURCE_RESPONSE_CONTRACT_FAILED")
        if not save["all"]:
            raise ReloadValidationError("SAVE_REPORT_OR_HASH_CONTRACT_FAILED")
        if evidence is None:
            raise ReloadValidationError("EVIDENCE_PATH_MISSING")

        installation = installation.resolve(strict=True)
        current_binding = _installation_binding(installation)
        report["reload_binding"] = current_binding
        report["build_binding"] = _binding_contract(execution, current_binding)

        session = ObserverSession(installation, game_exe())
        source_session_id = source.get("source_session_id")
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
            "source_session_id": source_session_id,
            "new_process": isinstance(source_session_id, str)
            and session.session_id != source_session_id,
        }
        health = wait_runtime_ready(session, restore_minimized=False)
        probes = _run_role_snapshots(session, evidence / "probes", _ACTOR)
        current_control_snapshot = probes.get("control_state", {}).get("snapshot")
        current_control = _control_summary(current_control_snapshot) \
            if isinstance(current_control_snapshot, dict) else {}
        report["after"] = {
            "health": health,
            "control": current_control,
            "snapshots": {
                name: {key: item.get(key) for key in
                       ("status", "snapshot_path", "snapshot_completeness", "snapshot_sha256")}
                for name, item in probes.items()
            },
        }
        expected_after = source.get("expected_pair_at_war_after") is True
        war = _war_contract(execution, probes, expected_after)
        control = _control_contract(execution, save_report, health, current_control, probes)
        expected_date_raw = control["source_control"].get("date_raw") \
            if isinstance(control.get("source_control"), dict) else None
        peace_effects = _peace_effect_reload_contract(
            source, execution, save_report, session, expected_date_raw, evidence)
        report["peace_effects"] = peace_effects
        recovery = _stream_recovery_log(
            installation.parent / "control-probe.jsonl",
            session.session_id,
            int(expected_date_raw),
            evidence,
            _ACTOR,
            _RECIPIENT,
            source_queue,
        )
        binding = report["build_binding"]
        checks = {
            "source_response_contract": source["all"],
            "save_hash_contract": save["all"],
            "new_process_identity": report["session"].get("new_process") is True,
            "same_immutable_dll_and_source_map": isinstance(binding, dict)
            and binding.get("all") is True,
            "control_boundary": control["all"],
            "war_state_matches_decision": war["all"],
            "peace_effects_match_source_native_and_save": peace_effects["all"],
            "native_recovery_summary_and_empty_current_queue": recovery["all"],
            "native_recovery_summary_and_source_queue": recovery["all"],
            "no_business_replay": report["business_submission"] is False
            and report["advance_requested"] is False
            and report["save_requested"] is False
            and report["restart_requested"] is False
            and report["installation_requested"] is False,
        }
        report["comparisons"] = {
            "control": control,
            "war": war,
            "peace_effects": peace_effects,
            "recovery": recovery,
            "source_queue": source_queue,
            "decision": source.get("decision"),
            "historical_catalog_ignored": True,
        }
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:  # preserve a bounded diagnostic, never replay work
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_PEACE_INBOUND_RELOAD_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({"status": report["status"], "report": str(report_path)
                      if report_path is not None else None}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
