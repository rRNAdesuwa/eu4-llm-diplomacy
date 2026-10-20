#!/usr/bin/env python3
"""Validate an outbound Peace result after a fresh read-only reload.

The source execution report and save-observer report are immutable evidence.
This validator attaches to the already running reload installation, captures
the four bounded probes, verifies the saved file by streaming its hash, and
checks the FRA--recipient war state against the source native outcome.  It never
publishes a request, retries an operation, advances time, saves, installs, or
restarts the game.  Diplomat and cooldown records are reported as facts; a
normal change in those records is not treated as a reload failure.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
from work.local_config import game_exe, get_value  # noqa: E402
from work import inspect_peace_save_pair as _peace_save  # noqa: E402
from work import inspect_peace_treaty_save as _peace_treaty_save  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.peace_reload_capital import (  # noqa: E402
    _native_special_runtime, _bind_special_capital_save_observation,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _hash_file,
    _run_snapshots,
    _write_json,
)


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_DEFAULT_RECIPIENT = "ENG"
_FAMILY = "peace"
_ACTIONS = frozenset((
    "white_peace", "demand_ducats", "cede_province", "war_reparations",
    "transfer_trade_power", "concede_defeat", "annul_treaties",
    "humiliate_rival", "show_strength", "force_religion"))
_DIRECTIONS = frozenset(("demand", "offer"))
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_MAX_EFFECT_EVENT_BYTES = 8 * 1024 * 1024
_MAX_EFFECT_COUNTRIES = 32
_MAX_EFFECT_PROVINCES = 16
_EFFECT_PROBE_TIMEOUT_SECONDS = 30
_TREASURY_RAW_SCALE = 1000
_TRADE_POWER_AMOUNT_RAW = 500
_TRADE_POWER_AMOUNT_SCALE = 1000
_TRADE_POWER_OPEN_END_DATE_RAW = 0x29C77F8
_PRESTIGE_SCALE1000 = 1000
_ANNUL_OPEN_END_DATE_RAW = 0x29C77F8
_SPECIAL_ACTIONS = frozenset(("humiliate_rival", "show_strength", "force_religion"))
_COUNTRY_TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}\Z")
# These are the stable sources present in the R45G immutable build.  The
# manifest may grow (for example, the peace-effects sources were added later),
# but a replacement build must still contain every source that established the
# original ABI.  Keeping the names here makes "61 files" a membership check,
# rather than a count that an unrelated alias could satisfy.
_REQUIRED_SOURCE_NAMES = frozenset({
    "alliance-authority-ledger.h",
    "alliance-entry-observer.inc",
    "alliance-execution-wire.h",
    "alliance-execution.inc",
    "alliance-inbound-inspection-event.h",
    "alliance-inbound-response-wire.h",
    "alliance-inbound.inc",
    "alliance-lifecycle.inc",
    "alliance-pending-membership.h",
    "alliance-protocol-observer.inc",
    "alliance-query.inc",
    "alliance-reason-key-branch.h",
    "alliance-reason-metadata-bind.inc",
    "alliance-reason-metadata.inc",
    "alliance-reason-row.h",
    "alliance-transport.inc",
    "automated-control.inc",
    "control-probe.cpp",
    "declarewar-candidates.inc",
    "declarewar-cost-query.inc",
    "declarewar-execution-preflight.inc",
    "declarewar-execution-state.inc",
    "declarewar-native-payload.inc",
    "declarewar-payload.h",
    "declarewar-query.inc",
    "diplomacy-observer-v10.cpp",
    "entry-patch-transaction.inc",
    "frame_stub.S",
    "inbound-pending-recovery.inc",
    "insult-query.inc",
    "peace-action-native-payload.inc",
    "peace-context-query.inc",
    "peace-empty-offer-query.inc",
    "peace-execution-preflight.inc",
    "peace-execution-wire.h",
    "peace-execution.inc",
    "peace-handler-authority.inc",
    "peace-inbound-context.inc",
    "peace-lifecycle-hooks.inc",
    "peace-money-query.inc",
    "peace-native-payload.inc",
    "peace-offer-evaluation-query.inc",
    "peace-payload-ref.h",
    "peace-payload.h",
    "peace-province-candidates.inc",
    "peace-province-selection.inc",
    "peace-receiver-observer.inc",
    "peace-war-context-query.inc",
    "peace-wrapper-rule-query.inc",
    "popup-control.inc",
    "rival-authority.inc",
    "rival-command-authority.h",
    "rival-command-observer.inc",
    "rival-command-wire.h",
    "rival-execution.inc",
    "rival-query.inc",
    "vassal-inbound-test-context-script.h",
    "vassal-inbound-test-context.inc",
    "vassal-query.inc",
    "vassal-test-context-script.h",
    "vassal-test-context.inc",
})
_REQUIRED_SOURCE_FLOOR = len(_REQUIRED_SOURCE_NAMES)
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class ReloadValidationError(RuntimeError):
    """An expected bounded validation failure."""


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
    """Summarize the FRA/target pair from tag-bound read-only probe rows."""

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
    if _ACTOR == "FRA":
        result["fra_pair_at_war"] = actor_value
    if target == "ENG":
        result["eng_pair_at_war"] = target_value
    return result


def _read_json(path: Path, *, maximum: int = _MAX_METADATA_BYTES) -> object:
    if not path.is_file():
        raise ReloadValidationError(f"FILE_MISSING:{path}")
    try:
        if path.stat().st_size > maximum:
            raise ReloadValidationError(f"METADATA_TOO_LARGE:{path}")
        return json.loads(path.read_text(encoding="utf-8"))
    except ReloadValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReloadValidationError(
            f"JSON_READ_FAILED:{path}:{type(error).__name__}") from error


def _resolve_report(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise ReloadValidationError(f"REPORT_NOT_FILE:{resolved}")
    return resolved


def _output_paths(requested: Path) -> tuple[Path, Path]:
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


def _all_true(value: object) -> bool:
    return (isinstance(value, dict) and bool(value)
            and all(item is True for item in value.values()))


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
        snapshot_path = item.get("snapshot_path")
        if isinstance(snapshot_path, str):
            path = Path(snapshot_path)
            if path.is_file():
                try:
                    snapshot = _read_json(path)
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
        and _snapshots_complete(before_report.get("probes"))
    )
    after_complete = (
        isinstance(after_report, dict)
        and _snapshots_complete(after_report.get("probes"))
    )
    names = {"alliance_state", "control_state", "diplomats", "war_state"}
    return {
        "before": before,
        "after": after,
        "before_complete": before_complete,
        "after_complete": after_complete,
        "four_probe_names": set(after) == names and set(before) == names,
    }


def _public_result(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if isinstance(result, dict):
        if result.get("event") == "native_peace_execution_result":
            return result
        nested = result.get("result")
        if isinstance(nested, dict) and nested.get("event") == "native_peace_execution_result":
            return nested
    if value.get("event") == "native_peace_execution_result":
        return value
    return None


def _public_effects(payload: dict[str, object], result: dict[str, object] | None
                    ) -> object:
    """Return only the public effect summary from either runner schema.

    Older execution reports wrapped the native result once more under
    ``result.result``.  Accepting that wrapper here keeps the reload checker
    compatible without treating private effect observations as public data.
    """

    if isinstance(result, dict) and isinstance(result.get("effects"), dict):
        return result.get("effects")
    wrapper = payload.get("result")
    if isinstance(wrapper, dict):
        effects = wrapper.get("effects")
        if isinstance(effects, dict):
            return effects
        nested = wrapper.get("result")
        if isinstance(nested, dict) and isinstance(nested.get("effects"), dict):
            return nested.get("effects")
    return None


def _source_execution_contract(payload: dict[str, object]) -> dict[str, object]:
    probes = _source_probe_contract(payload)
    result = _public_result(payload.get("result"))
    action_id = payload.get("action_id")
    direction = payload.get("direction", "demand")
    outcome = result.get("outcome") if isinstance(result, dict) else None
    expected_after = (
        False if outcome in ("executed", "accepted")
        else True if outcome == "rejected" else None
    )
    source_after = _war_pair_summary_for(probes["after"])
    source_before = _war_pair_summary_for(probes["before"])
    source_after_control = payload.get("after", {}).get("control", {}) \
        if isinstance(payload.get("after"), dict) else {}
    expected_date = payload.get("expected_date_raw")
    if type(expected_date) is not int and isinstance(source_after_control, dict):
        expected_date = source_after_control.get("date_raw")
    checks: dict[str, bool] = {
        "source_status_passed": payload.get("status") == "passed",
        "source_checks_passed": _all_true(payload.get("checks")),
        "identity": (
            action_id in _ACTIONS
            and payload.get("family") == _FAMILY
            and payload.get("actor") == _ACTOR
            and payload.get("recipient") == _RECIPIENT
            and direction in _DIRECTIONS
            and payload.get("phase") == "initiate"
        ),
        "source_probe_contract": probes["before_complete"] is True
        and probes["after_complete"] is True
        and probes["four_probe_names"] is True,
        "source_result_object": isinstance(result, dict),
        "source_result_identity": isinstance(result, dict)
        and result.get("event") == "native_peace_execution_result"
        and result.get("family") == _FAMILY
        and result.get("action_id") == action_id
        and result.get("actor") == _ACTOR
        and result.get("recipient") == _RECIPIENT
        and result.get("direction") == direction
        and result.get("phase") == "initiate"
        and result.get("request_id") == payload.get("request_id"),
        "source_result_date": isinstance(result, dict)
        and type(expected_date) is int
        and result.get("date_raw") == expected_date,
        "source_result_outcome": outcome in (
            "executed", "accepted", "rejected", "unknown"),
        "source_before_at_war": source_before.get("complete") is True
        and source_before.get("pair_at_war") is True,
        "source_result_binding": isinstance(result, dict)
        and result.get("war_before") is True
        and result.get("request_binding_verified") is True
        and result.get("response_verified") is True
        and result.get("war_after") is expected_after
        if expected_after is not None else False,
        "source_after_war": source_after.get("complete") is True
        and source_after.get("pair_at_war") is expected_after
        if expected_after is not None else False,
        "source_result_contract": (
            isinstance(payload.get("result_contract"), dict)
            and payload["result_contract"].get("all") is True
        ),
    }
    fatal = not all(checks[key] for key in (
        "identity", "source_probe_contract", "source_result_object",
        "source_result_identity", "source_result_date", "source_result_outcome",
        "source_before_at_war"))
    known = outcome in ("executed", "accepted", "rejected")
    verifiable = known and not fatal and all(checks.values())
    return {
        "checks": checks,
        "all": verifiable,
        "fatal": fatal,
        "unknown": not known and not fatal,
        "verifiable": verifiable,
        "action_id": action_id,
        "direction": direction,
        "outcome": outcome,
        "expected_pair_at_war_after": expected_after,
        "expected_date_raw": expected_date,
        "response_verified": result.get("response_verified")
        if isinstance(result, dict) else None,
        "terms_verified": result.get("terms_verified")
        if isinstance(result, dict) else None,
        "effects": _public_effects(payload, result),
        "result": result,
        "source_before": source_before,
        "source_after": source_after,
    }


def _save_contract(save_report: dict[str, object]) -> dict[str, object]:
    save = save_report.get("save")
    reported_hash = save.get("sha256") if isinstance(save, dict) else None
    save_path_value = save.get("path") if isinstance(save, dict) else None
    name = save_report.get("name")
    checks: dict[str, bool] = {
        "report_success": save_report.get("status") == "success",
        "save_object": isinstance(save, dict),
        "name_is_eu4_basename": isinstance(name, str)
        and Path(name).name == name and name.casefold().endswith(".eu4"),
        "reported_hash_valid": isinstance(reported_hash, str)
        and _SHA256_RE.fullmatch(reported_hash) is not None,
        "reported_path_valid": isinstance(save_path_value, str)
        and Path(save_path_value).is_file(),
    }
    actual = None
    if checks["reported_path_valid"]:
        actual = _hash_file(Path(str(save_path_value)), maximum=_MAX_SAVE_BYTES)
    actual_hash = actual.get("sha256") if isinstance(actual, dict) else None
    checks["actual_hash_matches_report"] = (
        checks["reported_hash_valid"] is True
        and isinstance(actual_hash, str)
        and actual_hash.casefold() == str(reported_hash).casefold()
    )
    return {
        "checks": checks,
        "all": all(checks.values()),
        "name": name,
        "reported": {"path": save_path_value, "sha256": reported_hash},
        "actual": actual,
    }


def _read_native_effect_observations(payload: dict[str, object],
                                     request_id: object) -> dict[str, object]:
    """Read matching private effect lines from the bounded execution slice."""

    metadata = payload.get("native_events")
    path_value = metadata.get("path") if isinstance(metadata, dict) else None
    path = Path(path_value).expanduser().resolve() if isinstance(path_value, str) else None
    checks: dict[str, bool] = {
        "metadata_object": isinstance(metadata, dict),
        "path_is_file": path is not None and path.is_file(),
        "slice_complete": isinstance(metadata, dict) and metadata.get("complete") is True,
        "slice_bounded": False,
    }
    observations: list[dict[str, object]] = []
    errors: list[str] = []
    size_bytes: int | None = None
    if path is not None and path.is_file():
        try:
            size_bytes = path.stat().st_size
            checks["slice_bounded"] = size_bytes <= _MAX_EFFECT_EVENT_BYTES
            if checks["slice_bounded"]:
                with path.open("r", encoding="utf-8", errors="replace") as stream:
                    for line_number, line in enumerate(stream, 1):
                        if len(observations) >= _MAX_EFFECT_COUNTRIES:
                            errors.append("effect_observation_limit_reached")
                            break
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(item, dict) or item.get(
                                "event") != "native_peace_effect_observation":
                            continue
                        if item.get("request_id") != request_id:
                            continue
                        tag = item.get("country")
                        if not isinstance(tag, str) or _COUNTRY_TAG_RE.fullmatch(tag) is None:
                            errors.append(f"invalid_country_tag_line:{line_number}")
                            continue
                        valid = (
                            item.get("private") is True
                            and type(item.get("date_before")) is int
                            and type(item.get("date_after")) is int
                            and type(item.get("treasury_before_raw")) is int
                            and type(item.get("treasury_after_raw")) is int
                            and item.get("currency_scale") == _TREASURY_RAW_SCALE
                        )
                        if not valid:
                            errors.append(f"invalid_effect_observation:{line_number}")
                            continue
                        observations.append({
                            "country": tag,
                            "date_before": item["date_before"],
                            "date_after": item["date_after"],
                            "treasury_before_raw": item["treasury_before_raw"],
                            "treasury_after_raw": item["treasury_after_raw"],
                            "currency_scale": item["currency_scale"],
                            "line": line_number,
                        })
        except OSError as error:
            errors.append(f"effect_slice_read_failed:{type(error).__name__}")
    by_country: dict[str, dict[str, object]] = {}
    duplicate_tags: list[str] = []
    for item in observations:
        tag = str(item["country"])
        if tag in by_country:
            duplicate_tags.append(tag)
        by_country[tag] = item
    checks.update({
        "matching_observation_present": bool(observations),
        "unique_country_observations": not duplicate_tags,
    })
    return {
        "private": True,
        "path": str(path) if path is not None else None,
        "size_bytes": size_bytes,
        "request_id": request_id,
        "observations": observations,
        "by_country": by_country,
        "duplicate_countries": duplicate_tags,
        "errors": errors,
        "checks": checks,
        "all": all(checks.values()) and not errors and not duplicate_tags,
    }


def _serialized_treasury_to_raw(value: object) -> int | None:
    """Convert a save's decimal treasury field to the native x1000 integer."""

    if value is None or isinstance(value, bool):
        return None
    try:
        decimal = Decimal(str(value).strip().strip('"'))
    except (InvalidOperation, ValueError):
        return None
    scaled = decimal * _TREASURY_RAW_SCALE
    integral = scaled.to_integral_value()
    if scaled != integral:
        return None
    return int(integral)


def _stream_save_effect_state(
        save_report: dict[str, object], country_tags: list[str],
        province_ids: list[int],
        reparations_pair: tuple[str, str] | None = None,
        trade_power_pair: tuple[str, str] | None = None,
        trade_power_source: str | None = None,
        trade_power_beneficiary: str | None = None,
        annul_treaties_pairs: list[tuple[str, str]] | None = None,
        ) -> dict[str, object]:
    """Stream only the requested effect blocks from the target save.

    Country/province state uses the existing bounded save scanner.  When a
    reparations or transfer-trade-power term is present, the dedicated treaty
    scanner is run against the same save and retains the directed records
    under their serialized block names.  It keeps the raw date/amount fields
    in the reload evidence without loading the complete gamestate.
    """

    if (trade_power_source is None) != (trade_power_beneficiary is None):
        return {"private": True, "status": "unavailable",
                "reason": "trade_power_pair_incomplete"}
    if trade_power_source is not None:
        if trade_power_pair is not None and trade_power_pair != (
                trade_power_source, trade_power_beneficiary):
            return {"private": True, "status": "unavailable",
                    "reason": "trade_power_pair_conflict"}
        trade_power_pair = trade_power_source, trade_power_beneficiary

    save = save_report.get("save")
    path_value = save.get("path") if isinstance(save, dict) else None
    if not isinstance(path_value, str):
        return {"private": True, "status": "unavailable", "reason": "save_path_missing"}
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        return {"private": True, "status": "unavailable", "reason": "save_file_missing",
                "path": str(path)}
    try:
        if path.stat().st_size > _MAX_SAVE_BYTES:
            return {"private": True, "status": "unavailable",
                    "reason": "save_file_exceeds_bound", "path": str(path)}
        source = _peace_save.bounded.detect_container(path)
        source["sha256"] = _peace_save.sha256_file(path)
        # _scan_gamestate uses the same bounded block scanner as the public
        # save-pair tool, but accepts the complete requested tag tuple so a
        # participant's absolute treasury never has to be inferred from a
        # foreign country's public projection.
        parsed = _peace_save._scan_gamestate(
            path, source, tuple(country_tags), tuple(province_ids))
        result: dict[str, object] = {
            "private": True,
            "status": "ok",
            "streaming": True,
            "path": str(path),
            "sha256": source.get("sha256"),
            "parsed": parsed,
        }
        if (reparations_pair is not None or trade_power_pair is not None
                or annul_treaties_pairs is not None):
            payer, claimant = reparations_pair or (None, None)
            source_tag, beneficiary_tag = trade_power_pair or (None, None)
            annul_country = (
                annul_treaties_pairs[0][0]
                if annul_treaties_pairs else None)
            annul_partners = (
                [pair[1] for pair in annul_treaties_pairs]
                if annul_treaties_pairs else None)
            result["treaty_scan"] = _peace_treaty_save.scan_save(
                path,
                payer,
                claimant,
                trade_power_source=source_tag,
                trade_power_beneficiary=beneficiary_tag,
                annul_country=annul_country,
                annul_partners=annul_partners,
            )
            # Keep the historical direct key for R callers while exposing the
            # T scan under its own block name as well.
            treaty_scan = result["treaty_scan"]
            if reparations_pair is not None:
                result["war_reparations"] = treaty_scan
            if trade_power_pair is not None:
                result["transfer_trade_power"] = treaty_scan
            if annul_treaties_pairs is not None:
                result["annul_treaties"] = treaty_scan
        return result
    except Exception as error:  # preserve an unavailable comparison as evidence
        return {
            "private": True,
            "status": "unavailable",
            "path": str(path),
            "reason": f"save_effect_scan_failed:{type(error).__name__}",
        }


def _run_effect_probe(session: ObserverSession, country_tags: list[str],
                      province_ids: list[int], expected_date_raw: object,
                      destination: Path,
                      reparations_pair: tuple[str, str] | None = None,
                      trade_power_pair: tuple[str, str] | None = None,
                      trade_power_source: str | None = None,
                      trade_power_beneficiary: str | None = None,
                      annul_treaties_pairs: list[tuple[str, str]] | None = None,
                      special_action: str | None = None,
                      special_pair: tuple[str, str] | None = None,
                      ) -> dict[str, object]:
    """Run the fixed-offset probe in a read-only child process."""

    if (trade_power_source is None) != (trade_power_beneficiary is None):
        return {"private": True, "status": "unavailable",
                "reason": "trade_power_pair_incomplete"}
    if trade_power_source is not None:
        if trade_power_pair is not None and trade_power_pair != (
                trade_power_source, trade_power_beneficiary):
            return {"private": True, "status": "unavailable",
                    "reason": "trade_power_pair_conflict"}
        trade_power_pair = trade_power_source, trade_power_beneficiary
    if type(expected_date_raw) is not int:
        return {"private": True, "status": "unavailable", "reason": "expected_date_missing"}
    script = Path(__file__).with_name("probe_peace_effect_state.py")
    try:
        python = get_value("EU4_PYTHON")
    except Exception as error:
        return {"private": True, "status": "unavailable",
                "reason": f"eu4_python_unconfigured:{type(error).__name__}"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    argv = [python, "-B", str(script), "--pid", str(session.record["pid"]),
            "--countries", *country_tags]
    if province_ids:
        argv.extend(("--provinces", *(str(value) for value in province_ids)))
    if reparations_pair is not None:
        payer, claimant = reparations_pair
        argv.extend(("--reparations-payer", payer,
                     "--reparations-claimant", claimant))
    if trade_power_pair is not None:
        source_tag, beneficiary_tag = trade_power_pair
        argv.extend(("--trade-power-source", source_tag,
                     "--trade-power-beneficiary", beneficiary_tag))
    if annul_treaties_pairs is not None:
        if not annul_treaties_pairs:
            return {"private": True, "status": "unavailable",
                    "reason": "annul_treaties_pairs_empty"}
        country = annul_treaties_pairs[0][0]
        partners = [pair[1] for pair in annul_treaties_pairs]
        argv.extend(("--annul-country", country,
                     "--annul-partners", *partners))
    if special_action is not None:
        if special_pair is None:
            return {"private": True, "status": "unavailable",
                    "reason": "special_pair_missing"}
        argv.extend(("--special-action", special_action,
                     "--special-country", special_pair[0],
                     "--special-beneficiary", special_pair[1]))
    argv.extend(("--expected-date-raw", str(expected_date_raw), "--output", str(destination)))
    try:
        completed = subprocess.run(
            argv, check=False, timeout=_EFFECT_PROBE_TIMEOUT_SECONDS,
            capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"private": True, "status": "unavailable", "argv": argv,
                "reason": f"effect_probe_failed:{type(error).__name__}"}
    try:
        snapshot = _read_json(destination, maximum=2 * 1024 * 1024)
    except ReloadValidationError as error:
        return {"private": True, "status": "unavailable", "argv": argv,
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2048:],
                "stderr_tail": completed.stderr[-2048:],
                "reason": f"effect_probe_output_invalid:{error}"}
    if not isinstance(snapshot, dict):
        return {"private": True, "status": "unavailable", "argv": argv,
                "reason": "effect_probe_output_not_object"}
    runtime = snapshot.get("runtime")
    return {
        "private": True,
        "status": "ok" if completed.returncode == 0 and isinstance(runtime, dict) else "failed",
        "argv": argv,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2048:],
        "stderr_tail": completed.stderr[-2048:],
        "snapshot_path": str(destination),
        "snapshot_sha256": _hash_file(destination, maximum=2 * 1024 * 1024),
        "snapshot": snapshot,
    }


def _saved_treasury(parsed: object, tag: str) -> int | None:
    if not isinstance(parsed, dict):
        return None
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    treasury = item.get("treasury") if isinstance(item, dict) else None
    raw = treasury.get("raw") if isinstance(treasury, dict) else None
    return _serialized_treasury_to_raw(raw)


def _saved_country_complete(parsed: object, tag: str) -> bool:
    if not isinstance(parsed, dict):
        return False
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    treasury = item.get("treasury") if isinstance(item, dict) else None
    return isinstance(item, dict) and item.get("complete") is True \
        and isinstance(treasury, dict) and treasury.get("found") is True


def _saved_prestige(parsed: object, tag: str) -> int | None:
    if not isinstance(parsed, dict):
        return None
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    if not isinstance(item, dict):
        return None
    raw = item.get("prestige_raw")
    if type(raw) is int and item.get("prestige_scale") == _PRESTIGE_SCALE1000:
        return raw
    prestige = item.get("prestige")
    value = prestige.get("raw") if isinstance(prestige, dict) else None
    return _serialized_treasury_to_raw(value)


def _saved_prestige_complete(parsed: object, tag: str) -> bool:
    if not isinstance(parsed, dict):
        return False
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    prestige = item.get("prestige") if isinstance(item, dict) else None
    return (isinstance(item, dict) and item.get("complete") is True
            and isinstance(prestige, dict) and prestige.get("found") is True
            and _saved_prestige(parsed, tag) is not None)


def _saved_religion(parsed: object, tag: str) -> str | None:
    if not isinstance(parsed, dict):
        return None
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    field = item.get("religion") if isinstance(item, dict) else None
    value = field.get("value") if isinstance(field, dict) else None
    return value if isinstance(value, str) else None


def _saved_capital_religion(parsed: object, tag: str) -> str | None:
    """Read the saved religion of ``tag``'s capital when the scanner exports it.

    The country save scanner gained this field after the original R54
    religion support.  Accept both the direct ``capital_religion`` field and
    the nested ``capital.religion`` shape so this reload validator remains
    bound to the scanner's public private-observation contract rather than
    reaching into raw save text itself.
    """

    if not isinstance(parsed, dict):
        return None
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    if not isinstance(item, dict):
        return None
    field = item.get("capital_religion")
    if field is None:
        capital = item.get("capital")
        field = capital.get("religion") if isinstance(capital, dict) else None
    if isinstance(field, str):
        return field
    value = field.get("value") if isinstance(field, dict) else None
    return value if isinstance(value, str) else None


def _saved_powers(parsed: object, tag: str) -> list[int] | None:
    if not isinstance(parsed, dict):
        return None
    countries = parsed.get("countries")
    item = countries.get(tag) if isinstance(countries, dict) else None
    field = item.get("powers") if isinstance(item, dict) else None
    values = field.get("values") if isinstance(field, dict) else None
    if (isinstance(values, list) and len(values) == 3
            and all(type(value) is int for value in values)):
        return list(values)
    return None


def _saved_humiliation_state(
        parsed: object, country: str, beneficiary: str,
        ) -> dict[str, object] | None:
    """Read the directed H/S relation from the beneficiary country block."""

    if not isinstance(parsed, dict):
        return None
    countries = parsed.get("countries")
    if not isinstance(countries, dict):
        return None
    beneficiary_item = countries.get(beneficiary)
    if not isinstance(beneficiary_item, dict):
        return None
    humiliation = beneficiary_item.get("humiliation")
    if not isinstance(humiliation, dict):
        return None
    relation = humiliation.get("humiliated_countries")
    if not isinstance(relation, dict):
        return None
    tags = relation.get("tags")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        return None
    if beneficiary_item.get("complete") is not True or humiliation.get(
            "relation_readable") is not True:
        return None
    return {
        "country": country,
        "beneficiary": beneficiary,
        "present": country in tags,
        "humiliated_countries": relation,
        "humiliated_rival": humiliation.get("humiliated_rival"),
        "humiliated_power_projection": humiliation.get(
            "humiliated_power_projection", []),
    }


def _compare_special_effect_state(
        native_probe: dict[str, object], save_probe: dict[str, object],
        effects: object, expected_pair: tuple[str, str],
        action: str, outcome: str = "accepted") -> dict[str, object]:
    """Compare bounded H/S/F live values with the public after projection.

    H/S relation membership is read from the beneficiary's bounded country
    block.  A complete block without ``humiliated_countries`` is a readable
    false state, so accepted and rejected reloads can be compared directly.
    """
    effects_dict = effects if isinstance(effects, dict) else {}
    public = effects_dict.get(action)
    runtime = _native_probe_runtime(native_probe)
    native = runtime.get(action) if isinstance(runtime, dict) else None
    if not isinstance(native, dict) and isinstance(runtime, dict):
        native = runtime.get("special")
    parsed = save_probe.get("parsed") if isinstance(save_probe, dict) else None
    country, beneficiary = expected_pair
    checks: dict[str, bool] = {
        "special_public_object": isinstance(public, dict),
        "special_native_object": isinstance(native, dict),
        "special_public_pair": isinstance(public, dict)
        and public.get("country") == country
        and public.get("beneficiary") == beneficiary,
        "special_native_pair": isinstance(native, dict)
        and native.get("country") == country
        and native.get("beneficiary") == beneficiary,
        "special_public_verified": isinstance(public, dict)
        and public.get("verified") is (outcome in ("accepted", "executed")),
        "special_native_complete": isinstance(native, dict)
        and native.get("complete") is True,
    }
    public_country_after = public.get("country_prestige_after_raw") \
        if isinstance(public, dict) else None
    public_beneficiary_after = public.get("beneficiary_prestige_after_raw") \
        if isinstance(public, dict) else None
    save_country = _saved_prestige(parsed, country)
    save_beneficiary = _saved_prestige(parsed, beneficiary)
    if action in {"humiliate_rival", "show_strength"}:
        # H/S carry the prestige contract.  Force Religion deliberately has
        # a different public schema and must not be forced through these
        # integer fields.
        checks.update({
            "special_native_country_prestige_after": (
                isinstance(native, dict)
                and native.get("country_prestige_raw") == public_country_after),
            "special_native_beneficiary_prestige_after": (
                isinstance(native, dict)
                and native.get("beneficiary_prestige_raw") == public_beneficiary_after),
            "special_save_country_prestige_after": (
                _saved_prestige_complete(parsed, country)
                and save_country == public_country_after),
            "special_save_beneficiary_prestige_after": (
                _saved_prestige_complete(parsed, beneficiary)
                and save_beneficiary == public_beneficiary_after),
        })
    if action == "show_strength":
        public_powers = public.get("powers_after") if isinstance(public, dict) else None
        native_powers = native.get("powers") if isinstance(native, dict) else None
        native_values = native_powers.get("values") if isinstance(native_powers, dict) else None
        checks["special_native_powers_after"] = native_values == public_powers
        # Show Strength's native settlement reads the winner/beneficiary
        # powers.  Keep the save comparison on the same endpoint as the
        # public ``powers_after`` projection.
        saved_values = _saved_powers(parsed, beneficiary)
        checks["special_save_powers_after"] = (
            saved_values == public_powers)
    if action == "force_religion":
        checks["special_native_religion_after"] = (
            isinstance(native, dict)
            and native.get("religion") == public.get("religion_after")
            and native.get("beneficiary_religion") == public.get("beneficiary_religion_after")
            and native.get("capital_religion") == public.get("capital_religion_after"))
        checks["special_native_religion_values_readable"] = (
            isinstance(native, dict)
            and native.get("values_readable") is True
            and native.get("religion_readable") is True
            and native.get("beneficiary_religion_readable") is True
            and native.get("capital_religion_readable") is True)
        saved_religion = _saved_religion(parsed, country)
        saved_beneficiary_religion = _saved_religion(parsed, beneficiary)
        saved_capital_religion = _saved_capital_religion(parsed, country)
        checks["special_save_religion_after"] = (
            saved_religion == public.get("religion_after")
            and saved_religion is not None)
        checks["special_save_beneficiary_religion_after"] = (
            saved_beneficiary_religion == public.get("beneficiary_religion_after")
            and saved_beneficiary_religion is not None)
        checks["special_save_capital_religion_after"] = (
            saved_capital_religion == public.get("capital_religion_after")
            and saved_capital_religion is not None)
    if action in {"humiliate_rival", "show_strength"}:
        checks["special_native_humiliated_after"] = (
            isinstance(native, dict)
            and native.get("present", native.get("humiliated")) ==
            public.get("humiliated_after"))
        saved_humiliation = _saved_humiliation_state(
            parsed, country, beneficiary)
        checks["special_save_humiliation_readable"] = (
            isinstance(saved_humiliation, dict))
        checks["special_save_humiliated_after"] = (
            isinstance(saved_humiliation, dict)
            and saved_humiliation.get("present") ==
            public.get("humiliated_after"))
    return {
        "checks": checks,
        "all": all(checks.values()),
        "expected": {"action_id": action, "country": country,
                     "beneficiary": beneficiary},
        "public_effect": public,
        "native_runtime": native,
        "save_country": {country: save_country, beneficiary: save_beneficiary},
        "save_humiliation": (
            _saved_humiliation_state(parsed, country, beneficiary)
            if action in {"humiliate_rival", "show_strength"} else None),
        "save_special_relation_unknown": False,
    }


def _native_country_item(probe: object, tag: str) -> dict[str, object] | None:
    if not isinstance(probe, dict):
        return None
    countries = probe.get("countries")
    if not isinstance(countries, list):
        return None
    return next((item for item in countries
                 if isinstance(item, dict) and item.get("tag") == tag), None)


def _native_probe_runtime(probe: object) -> dict[str, object] | None:
    """Return the runtime payload from the probe wrapper's saved snapshot.

    ``_run_effect_probe`` stores the probe process result under ``snapshot``;
    the country/province arrays therefore live at
    ``private_native_probe.snapshot.runtime``.  Keeping this extraction
    explicit prevents the validator from mistaking the wrapper metadata for
    the runtime state.
    """

    if not isinstance(probe, dict):
        return None
    snapshot = probe.get("snapshot")
    if not isinstance(snapshot, dict):
        return None
    runtime = snapshot.get("runtime")
    return runtime if isinstance(runtime, dict) else None


def _saved_province_item(parsed: object, province_id: int) -> dict[str, object] | None:
    if not isinstance(parsed, dict):
        return None
    provinces = parsed.get("provinces")
    item = provinces.get(str(province_id)) if isinstance(provinces, dict) else None
    return item if isinstance(item, dict) else None


def _saved_province_tag(item: dict[str, object] | None, field: str) -> object:
    if not isinstance(item, dict) or item.get("complete") is not True:
        return None
    fields = item.get("fields")
    entry = fields.get(field) if isinstance(fields, dict) else None
    return entry.get("value") if isinstance(entry, dict) else None


def _requested_peace_terms(execution: dict[str, object]) -> list[dict[str, object]] | None:
    """Read the normalized term list from the immutable execution artifact."""

    parameters = execution.get("parameters")
    context: object = None
    if isinstance(parameters, dict):
        execute = parameters.get("execute")
        query = parameters.get("query")
        candidate = execute if isinstance(execute, dict) else query
        context = candidate.get("peace_context") \
            if isinstance(candidate, dict) else None
    if not isinstance(context, dict):
        return None
    terms = context.get("terms")
    if not isinstance(terms, list) or any(not isinstance(term, dict) for term in terms):
        return None
    return [term for term in terms if isinstance(term, dict)]


def _requested_peace_province_ids(execution: dict[str, object]) -> list[int] | None:
    """Read the normalized cede list from the immutable execution artifact."""

    terms = _requested_peace_terms(execution)
    if terms is None:
        return None
    for term in terms:
        if term.get("action_id") != "cede_province":
            continue
        ids = term.get("province_ids")
        if not isinstance(ids, list) or not ids:
            return None
        if any(type(value) is not int for value in ids):
            return None
        if len(ids) != len(set(ids)):
            return None
        return list(ids)
    return None


def _requested_peace_reparations_pair(
        execution: dict[str, object],
        ) -> tuple[str, str] | None:
    """Read the normalized payer/claimant pair from a reparations term."""

    terms = _requested_peace_terms(execution)
    if terms is None:
        return None
    for term in terms:
        if term.get("action_id") != "war_reparations":
            continue
        payer = term.get("payer")
        claimant = term.get("claimant")
        if (isinstance(payer, str) and _COUNTRY_TAG_RE.fullmatch(payer)
                and isinstance(claimant, str)
                and _COUNTRY_TAG_RE.fullmatch(claimant)
                and payer != claimant):
            return payer, claimant
        return None
    return None


def _requested_peace_trade_power_pair(
        execution: dict[str, object],
        ) -> tuple[str, str] | None:
    """Read the normalized source/beneficiary pair from a T term."""

    terms = _requested_peace_terms(execution)
    if terms is None:
        return None
    for term in terms:
        if term.get("action_id") != "transfer_trade_power":
            continue
        source = term.get("source")
        beneficiary = term.get("beneficiary")
        if (isinstance(source, str) and _COUNTRY_TAG_RE.fullmatch(source)
                and isinstance(beneficiary, str)
                and _COUNTRY_TAG_RE.fullmatch(beneficiary)
                and source != beneficiary):
            return source, beneficiary
        return None
    return None


def _requested_peace_concede_defeat_pair(
        execution: dict[str, object],
        ) -> tuple[str, str] | None:
    """Read the normalized C conceding-country/beneficiary pair."""

    terms = _requested_peace_terms(execution)
    if terms is None:
        return None
    for term in terms:
        if term.get("action_id") != "concede_defeat":
            continue
        conceding = term.get("conceding_country")
        beneficiary = term.get("beneficiary")
        if (isinstance(conceding, str)
                and _COUNTRY_TAG_RE.fullmatch(conceding)
                and isinstance(beneficiary, str)
                and _COUNTRY_TAG_RE.fullmatch(beneficiary)
                and conceding != beneficiary):
            return conceding, beneficiary
        return None
    return None


def _requested_peace_annul_pairs(
        execution: dict[str, object],
        ) -> list[tuple[str, str]] | None:
    """Read the explicit directed country/partner list from the A term."""
    terms = _requested_peace_terms(execution)
    if terms is None:
        return None
    for term in terms:
        if term.get("action_id") != "annul_treaties":
            continue
        country = term.get("country")
        partners = term.get("treaty_partners")
        if (not isinstance(country, str)
                or _COUNTRY_TAG_RE.fullmatch(country) is None
                or not isinstance(partners, list)
                or not 1 <= len(partners) <= 16):
            return None
        if (any(not isinstance(item, str)
                or _COUNTRY_TAG_RE.fullmatch(item) is None
                for item in partners)
                or len(set(partners)) != len(partners)
                or partners != sorted(partners)
                or country in partners):
            return None
        return [(country, partner) for partner in partners]
    return None


def _requested_peace_special_pair(
        execution: dict[str, object], action: str,
        ) -> tuple[str, str] | None:
    terms = _requested_peace_terms(execution)
    if terms is None or action not in _SPECIAL_ACTIONS:
        return None
    for term in terms:
        if term.get("action_id") != action:
            continue
        country = term.get("country")
        beneficiary = term.get("beneficiary")
        if (isinstance(country, str) and _COUNTRY_TAG_RE.fullmatch(country)
                and isinstance(beneficiary, str)
                and _COUNTRY_TAG_RE.fullmatch(beneficiary)
                and country != beneficiary):
            return country, beneficiary
        return None
    return None


def _saved_annul_treaties_snapshot(save_probe: object) -> dict[str, object] | None:
    if not isinstance(save_probe, dict):
        return None
    value = save_probe.get("annul_treaties")
    if not isinstance(value, dict):
        treaty_scan = save_probe.get("treaty_scan")
        if isinstance(treaty_scan, dict):
            value = treaty_scan.get("annul_treaties")
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("save"), dict):
        value = value["save"]
    return value


def _saved_war_reparations_snapshot(
        save_probe: object,
        ) -> dict[str, object] | None:
    """Normalize treaty-parser output retained by ``_stream_save_effect_state``.

    The stream parser is intentionally kept as a complete private observation
    in the save probe.  Accept both its direct ``scan_save`` shape and the
    ``build_payload`` wrapper so offline contract tests can supply either
    artifact without changing the comparison semantics.
    """

    if not isinstance(save_probe, dict):
        return None
    value = save_probe.get("war_reparations")
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("save"), dict):
        value = value["save"]
    return value


def _saved_transfer_trade_power_snapshot(
        save_probe: object,
        ) -> dict[str, object] | None:
    """Normalize the transfer-trade-power scan retained by the save probe."""

    if not isinstance(save_probe, dict):
        return None
    value = save_probe.get("transfer_trade_power")
    if not isinstance(value, dict):
        treaty_scan = save_probe.get("treaty_scan")
        if isinstance(treaty_scan, dict):
            value = treaty_scan.get("transfer_trade_power")
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("save"), dict):
        value = value["save"]
    return value


def _trade_power_open_end(value: object) -> bool:
    """Recognize only the native open-ended trade-power sentinel."""

    if type(value) is int:
        return value == _TRADE_POWER_OPEN_END_DATE_RAW
    if not isinstance(value, str):
        return False
    text = value.strip().strip('"').casefold()
    if text in {"0x29c77f8", "43808760"}:
        return True
    return False


def _trade_power_saved_end_matches(
        native_end: object, public_end: object, saved_end: object,
        ) -> bool:
    """Compare an optional serialized end without inventing a duration.

    The current native relation uses ``0x29c77f8`` for an open-ended treaty.
    A save may omit ``end_date`` for that state.  A present end is accepted
    only when it is the same sentinel or exactly the same scalar supplied by
    the native/public evidence; arbitrary calendar arithmetic is forbidden.
    """

    if type(native_end) is not int:
        return False
    if public_end is not None and public_end != native_end:
        return False
    if native_end == _TRADE_POWER_OPEN_END_DATE_RAW:
        return saved_end is None or _trade_power_open_end(saved_end)
    if saved_end is None:
        return False
    if saved_end == native_end:
        return True
    if public_end is not None and saved_end == public_end:
        return True
    return False


def _compare_trade_power_effect_state(
        native_probe: dict[str, object], save_probe: dict[str, object],
        effects: object, expected_pair: tuple[str, str],
        expected_date_raw: object,
        ) -> dict[str, object]:
    """Compare accepted T source effects with native and serialized state."""

    effects_dict = effects if isinstance(effects, dict) else {}
    public = effects_dict.get("transfer_trade_power")
    public = public if isinstance(public, dict) else None
    expected_source, expected_beneficiary = expected_pair
    runtime = _native_probe_runtime(native_probe)
    native = runtime.get("transfer_trade_power") \
        if isinstance(runtime, dict) else None
    native = native if isinstance(native, dict) else None
    snapshot = _saved_transfer_trade_power_snapshot(save_probe)
    query = snapshot.get("query") if isinstance(snapshot, dict) else None
    records = (query.get("trade_power_matching_records")
               if isinstance(query, dict) else None)
    records = records if isinstance(records, list) else []
    complete_records = [
        record for record in records
        if isinstance(record, dict)
        and record.get("complete") is True
        and record.get("fields_complete") is True
    ]
    public_start = public.get("start_date_raw") if public is not None else None
    public_end = public.get("end_date_raw") if public is not None else None
    native_start = native.get("start_date_raw") if native is not None else None
    native_end = native.get("end_date_raw") if native is not None else None
    native_dates = (
        type(native_start) is int and type(native_end) is int
        and type(expected_date_raw) is int and native_start <= expected_date_raw)
    checks: dict[str, bool] = {
        "public_transfer_trade_power_object": public is not None,
        "public_transfer_trade_power_source": (
            public is not None and public.get("source") == expected_source),
        "public_transfer_trade_power_beneficiary": (
            public is not None
            and public.get("beneficiary") == expected_beneficiary),
        "public_transfer_trade_power_present_before": (
            public is not None and public.get("present_before") is False),
        "public_transfer_trade_power_present_after": (
            public is not None and public.get("present_after") is True),
        "public_transfer_trade_power_start": (
            public is not None and type(public_start) is int
            and type(native_start) is int and public_start == native_start),
        "public_transfer_trade_power_amount": (
            public is not None
            and public.get("amount_raw") == _TRADE_POWER_AMOUNT_RAW),
        "public_transfer_trade_power_scale": (
            public is not None
            and public.get("amount_scale") == _TRADE_POWER_AMOUNT_SCALE),
        "public_transfer_trade_power_peace_treaty": (
            public is not None and public.get("peace_treaty") is True),
        "public_transfer_trade_power_verified": (
            public is not None and public.get("verified") is True),
        "public_transfer_trade_power_end_sentinel": (
            public is not None and _trade_power_open_end(public_end)),
        "native_transfer_trade_power_object": native is not None,
        "native_transfer_trade_power_source": (
            native is not None and native.get("source") == expected_source),
        "native_transfer_trade_power_beneficiary": (
            native is not None
            and native.get("beneficiary") == expected_beneficiary),
        "native_transfer_trade_power_present": (
            native is not None and native.get("present") is True),
        "native_transfer_trade_power_complete": (
            native is not None and native.get("complete") is True),
        "native_transfer_trade_power_start": native_dates,
        "native_transfer_trade_power_amount": (
            native is not None
            and native.get("amount_raw") == _TRADE_POWER_AMOUNT_RAW),
        "native_transfer_trade_power_scale": (
            native is not None
            and native.get("amount_scale") == _TRADE_POWER_AMOUNT_SCALE),
        "native_transfer_trade_power_peace_treaty": (
            native is not None and native.get("peace_treaty") is True),
        "native_transfer_trade_power_end_sentinel": (
            native is not None and _trade_power_open_end(native_end)),
        "save_transfer_trade_power_query_readable": isinstance(query, dict),
        "save_transfer_trade_power_exact_pair": (
            isinstance(query, dict)
            and query.get("trade_power_exact_pair_present") is True),
        "save_transfer_trade_power_records_complete": (
            bool(complete_records) and len(complete_records) == len(records)),
        "save_transfer_trade_power_pair": (
            bool(complete_records)
            and all(record.get("source") == expected_source
                    and record.get("beneficiary") == expected_beneficiary
                    for record in complete_records)),
        "save_transfer_trade_power_amount": (
            bool(complete_records)
            and all(record.get("amount_raw") == _TRADE_POWER_AMOUNT_RAW
                    for record in complete_records)),
        "save_transfer_trade_power_scale": (
            bool(complete_records)
            and all(record.get("amount_scale") == _TRADE_POWER_AMOUNT_SCALE
                    for record in complete_records)),
        "save_transfer_trade_power_enforced": (
            bool(complete_records)
            and all(record.get("enforced") is True
                    for record in complete_records)),
        "save_transfer_trade_power_start": (
            bool(complete_records)
            and all(isinstance(record.get("start_date_raw"), str)
                    and _peace_treaty_save._date_tuple(
                        record.get("start_date_raw")) is not None
                    for record in complete_records)),
        "save_transfer_trade_power_end_normalized": (
            bool(complete_records)
            and all(_trade_power_saved_end_matches(
                native_end, public_end, record.get("end_date_raw"))
                for record in complete_records)),
    }
    return {
        "checks": checks,
        "all": all(checks.values()),
        "expected": {
            "source": expected_source,
            "beneficiary": expected_beneficiary,
            "amount_raw": _TRADE_POWER_AMOUNT_RAW,
            "amount_scale": _TRADE_POWER_AMOUNT_SCALE,
            "open_end_raw": _TRADE_POWER_OPEN_END_DATE_RAW,
        },
        "public_effect": public,
        "native_runtime": native,
        "saved_query": query,
        "saved_records": records,
    }


def _compare_annul_treaties_effect_state(
        native_probe: dict[str, object], save_probe: dict[str, object],
        effects: object, expected_pairs: list[tuple[str, str]],
        outcome: str,
        ) -> dict[str, object]:
    """Compare each directed annul pair without assuming rejection is inert."""
    effects_dict = effects if isinstance(effects, dict) else {}
    public_rows = effects_dict.get("annul_treaties")
    public_rows = public_rows if isinstance(public_rows, list) else []
    runtime = _native_probe_runtime(native_probe)
    native_rows = runtime.get("annul_treaties") if isinstance(runtime, dict) else None
    native_rows = native_rows if isinstance(native_rows, list) else []
    snapshot = _saved_annul_treaties_snapshot(save_probe)
    query = snapshot.get("query") if isinstance(snapshot, dict) else None
    saved_rows = (query.get("annul_matching_records")
                  if isinstance(query, dict) else None)
    saved_rows = saved_rows if isinstance(saved_rows, list) else []
    checks: dict[str, bool] = {
        "annul_treaties_public_list": isinstance(effects_dict.get("annul_treaties"), list),
        "annul_treaties_native_list": isinstance(runtime.get("annul_treaties"), list)
        if isinstance(runtime, dict) else False,
        "annul_treaties_save_query": isinstance(query, dict),
    }
    for index, pair in enumerate(expected_pairs):
        public = next((row for row in public_rows
                       if isinstance(row, dict)
                       and (row.get("country"), row.get("partner")) == pair), None)
        native = next((row for row in native_rows
                       if isinstance(row, dict)
                       and (row.get("country"), row.get("partner")) == pair), None)
        saved = [row for row in saved_rows
                 if isinstance(row, dict)
                 and row.get("country") == pair[0]
                 and row.get("partner") == pair[1]]
        prefix = f"annul_treaties_{index}"
        source_after = public.get("present_after") if isinstance(public, dict) else None
        checks.update({
            f"{prefix}_public_pair": isinstance(public, dict),
            f"{prefix}_public_fields": isinstance(public, dict)
            and type(public.get("present_before")) is bool
            and type(source_after) is bool
            and type(public.get("start_date_raw")) is int
            and type(public.get("end_date_raw")) is int
            and type(public.get("alliance_before")) is bool
            and type(public.get("alliance_after")) is bool
            and public.get("values_readable") is True
            and public.get("verified") is (outcome in ("accepted", "executed")),
            f"{prefix}_native_pair": isinstance(native, dict),
            f"{prefix}_native_present_after": isinstance(native, dict)
            and native.get("present") is source_after,
            f"{prefix}_native_complete": isinstance(native, dict)
            and native.get("complete") is True,
            f"{prefix}_native_dates": isinstance(native, dict)
            and type(native.get("start_date_raw")) is int
            and type(native.get("end_date_raw")) is int,
            f"{prefix}_native_alliance": isinstance(native, dict)
            and type(native.get("alliance")) is bool
            and native.get("alliance") == (
                public.get("alliance_after")
                if isinstance(public, dict) else None),
            f"{prefix}_save_presence": (
                bool(saved) is source_after
                and all(row.get("fields_complete") is True for row in saved)),
        })
        if outcome in ("accepted", "executed"):
            checks[f"{prefix}_accepted_present"] = source_after is True
    checks["annul_treaties_pair_count"] = (
        len(public_rows) == len(expected_pairs)
        and len(native_rows) == len(expected_pairs))
    return {
        "checks": checks,
        "all": all(checks.values()),
        "expected_pairs": expected_pairs,
        "public_effect": public_rows,
        "native_runtime": native_rows,
        "saved_query": query,
        "saved_records": saved_rows,
    }


def _compare_rejected_trade_power_state(
        native_probe: dict[str, object], save_probe: dict[str, object],
        effects: object, expected_pair: tuple[str, str],
        ) -> dict[str, object]:
    """Compare an absent rejected T relation across all three observations."""

    effects_dict = effects if isinstance(effects, dict) else {}
    public = effects_dict.get("transfer_trade_power")
    public = public if isinstance(public, dict) else None
    expected_source, expected_beneficiary = expected_pair
    runtime = _native_probe_runtime(native_probe)
    native = runtime.get("transfer_trade_power") \
        if isinstance(runtime, dict) else None
    native = native if isinstance(native, dict) else None
    snapshot = _saved_transfer_trade_power_snapshot(save_probe)
    query = snapshot.get("query") if isinstance(snapshot, dict) else None
    records = (query.get("trade_power_matching_records")
               if isinstance(query, dict) else None)
    records = records if isinstance(records, list) else []
    source_absent = (
        public is not None
        and public.get("source") == expected_source
        and public.get("beneficiary") == expected_beneficiary
        and public.get("present_before") is False
        and public.get("present_after") is False
        and public.get("start_date_raw") == 0
        and public.get("end_date_raw") == 0
        and public.get("amount_raw") == 0
        # Older source-contract fixtures emitted zero for a non-present
        # amount; the observed rejected T-only report keeps the common
        # fixed-point scale (1000) even though amount_raw is zero.  Both are
        # absence representations, so do not turn this schema difference
        # into a reload failure.
        and public.get("amount_scale") in (0, _TRADE_POWER_AMOUNT_SCALE)
        and public.get("peace_treaty") is False
        and public.get("verified") is False)
    checks: dict[str, bool] = {
        "source_transfer_trade_power_object": public is not None,
        "source_transfer_trade_power_absent": source_absent,
        "native_transfer_trade_power_object": native is not None,
        "native_transfer_trade_power_source": (
            native is not None and native.get("source") == expected_source),
        "native_transfer_trade_power_beneficiary": (
            native is not None
            and native.get("beneficiary") == expected_beneficiary),
        "native_transfer_trade_power_complete": (
            native is not None and native.get("complete") is True),
        "native_transfer_trade_power_present_absent": (
            native is not None and native.get("present") is False),
        "native_transfer_trade_power_amount_zero": (
            native is not None and native.get("amount_raw") == 0),
        "native_transfer_trade_power_peace_treaty_false": (
            native is not None and native.get("peace_treaty") is False),
        "save_transfer_trade_power_query_readable": isinstance(query, dict),
        "save_transfer_trade_power_exact_pair_absent": (
            isinstance(query, dict)
            and query.get("trade_power_exact_pair_present") is False),
        "save_transfer_trade_power_matching_records_absent": not records,
    }
    return {
        "checks": checks,
        "all": all(checks.values()),
        "expected": {
            "source": expected_source,
            "beneficiary": expected_beneficiary,
            "present": False,
        },
        "source_effect": public,
        "native_runtime": native,
        "saved_query": query,
        "saved_records": records,
    }


def _concede_defeat_effect_fields(effect: object) -> tuple[dict[str, object], bool]:
    """Validate the typed C effect without assuming a fixed native delta."""
    value = effect if isinstance(effect, dict) else {}
    fields = (
        "conceding_prestige_before_raw", "conceding_prestige_after_raw",
        "conceding_prestige_delta_raw", "beneficiary_prestige_before_raw",
        "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw")
    checks: dict[str, bool] = {
        "object": isinstance(effect, dict),
        "scale1000": isinstance(effect, dict)
        and effect.get("prestige_scale") == _PRESTIGE_SCALE1000,
        "values_readable": isinstance(effect, dict)
        and effect.get("values_readable") is True,
        "verified_bool": isinstance(effect, dict)
        and isinstance(effect.get("verified"), bool),
    }
    checks.update({
        field: type(value.get(field)) is int
        and not isinstance(value.get(field), bool)
        for field in fields
    })
    checks.update({
        "conceding_delta_consistent": (
            type(value.get("conceding_prestige_before_raw")) is int
            and type(value.get("conceding_prestige_after_raw")) is int
            and type(value.get("conceding_prestige_delta_raw")) is int
            and value.get("conceding_prestige_delta_raw") ==
            value.get("conceding_prestige_after_raw") -
            value.get("conceding_prestige_before_raw")),
        "beneficiary_delta_consistent": (
            type(value.get("beneficiary_prestige_before_raw")) is int
            and type(value.get("beneficiary_prestige_after_raw")) is int
            and type(value.get("beneficiary_prestige_delta_raw")) is int
            and value.get("beneficiary_prestige_delta_raw") ==
            value.get("beneficiary_prestige_after_raw") -
            value.get("beneficiary_prestige_before_raw")),
    })
    return value, all(checks.values())


def _compare_concede_defeat_effect_state(
        native_probe: dict[str, object], save_probe: dict[str, object],
        effects: object, expected_pair: tuple[str, str],
        outcome: object,
        ) -> dict[str, object]:
    """Compare source C prestige values with live and serialized after-state."""
    effects_dict = effects if isinstance(effects, dict) else {}
    public = effects_dict.get("concede_defeat")
    public, public_fields_valid = _concede_defeat_effect_fields(public)
    expected_conceding, expected_beneficiary = expected_pair
    expected_verified = outcome in ("accepted", "executed")
    checks: dict[str, bool] = {
        "public_concede_defeat_object": public_fields_valid,
        "public_concede_defeat_conceding_country": (
            public.get("conceding_country") == expected_conceding),
        "public_concede_defeat_beneficiary": (
            public.get("beneficiary") == expected_beneficiary),
        "public_concede_defeat_verified": (
            public.get("verified") is expected_verified),
    }
    runtime = _native_probe_runtime(native_probe)
    parsed = save_probe.get("parsed") if isinstance(save_probe, dict) else None
    expected_after = {
        expected_conceding: public.get("conceding_prestige_after_raw"),
        expected_beneficiary: public.get("beneficiary_prestige_after_raw"),
    }
    native_checks: dict[str, bool] = {}
    save_checks: dict[str, bool] = {}
    for tag, after_raw in expected_after.items():
        native_item = _native_country_item(runtime, tag)
        native_checks[tag] = (
            isinstance(native_item, dict)
            and native_item.get("prestige_readable") is True
            and native_item.get("prestige_scale") == _PRESTIGE_SCALE1000
            and native_item.get("prestige_raw") == after_raw)
        save_checks[tag] = (
            _saved_prestige_complete(parsed, tag)
            and _saved_prestige(parsed, tag) == after_raw)
    checks["native_concede_defeat_prestige_after_matches_source"] = (
        bool(native_checks) and all(native_checks.values()))
    checks["save_concede_defeat_prestige_after_matches_source"] = (
        bool(save_checks) and all(save_checks.values()))
    return {
        "checks": checks,
        "all": all(checks.values()),
        "expected": {
            "conceding_country": expected_conceding,
            "beneficiary": expected_beneficiary,
            "prestige_scale": _PRESTIGE_SCALE1000,
        },
        "public_effect": public if public_fields_valid else None,
        "native_country_checks": native_checks,
        "save_country_checks": save_checks,
    }


def _compare_effect_states(observations: dict[str, object],
                           native_probe: dict[str, object],
                           save_probe: dict[str, object],
                           effects: object,
                           action_id: object,
                           expected_province_ids: list[int] | None = None,
                           expected_reparations_pair: tuple[str, str] | None = None,
                           expected_trade_power_pair: tuple[str, str] | None = None,
                           expected_concede_defeat_pair: tuple[str, str] | None = None,
                           expected_annul_treaties_pairs: list[tuple[str, str]] | None = None,
                           expected_date_raw: object = None,
                           ) -> dict[str, object]:
    """Compare private native after-values with live and saved state.

    The returned ``private`` section contains absolute treasury readings for
    the operator artifact only.  No caller should copy it to a public API
    response.  Province controller equality is checked as an observed field;
    it is intentionally not required to equal the new owner.
    """

    checks: dict[str, bool] = {}
    private_by_country = observations.get("by_country") \
        if isinstance(observations, dict) else {}
    runtime = _native_probe_runtime(native_probe)
    parsed = save_probe.get("parsed") if isinstance(save_probe, dict) else None
    private_by_country = private_by_country if isinstance(private_by_country, dict) else {}
    tags = sorted(str(tag) for tag in private_by_country)
    effects_dict = effects if isinstance(effects, dict) else {}
    money_requested = action_id == "demand_ducats" \
        or isinstance(effects_dict.get("money"), dict)
    checks["private_observations_complete"] = (
        observations.get("all") is True if isinstance(observations, dict)
        else False) if money_requested else True
    checks["private_country_count_nonzero"] = bool(tags) if money_requested else True
    checks["native_probe_readable"] = (isinstance(native_probe, dict)
                                        and native_probe.get("status") == "ok"
                                        and isinstance(runtime, dict))
    checks["save_probe_readable"] = (isinstance(save_probe, dict)
                                      and save_probe.get("status") == "ok"
                                      and (isinstance(parsed, dict)
                                           or isinstance(
                                               _saved_war_reparations_snapshot(save_probe),
                                               dict)
                                           or isinstance(
                                               _saved_transfer_trade_power_snapshot(save_probe),
                                               dict)
                                           or isinstance(
                                               _saved_annul_treaties_snapshot(save_probe),
                                               dict)))

    native_country_checks: dict[str, bool] = {}
    save_country_checks: dict[str, bool] = {}
    for tag in tags:
        observation = private_by_country[tag]
        after_raw = observation.get("treasury_after_raw") \
            if isinstance(observation, dict) else None
        native_item = _native_country_item(runtime, tag)
        native_country_checks[tag] = (
            isinstance(native_item, dict)
            and native_item.get("treasury_readable") is True
            and native_item.get("currency_scale") == _TREASURY_RAW_SCALE
            and native_item.get("treasury_raw") == after_raw
        )
        save_country_checks[tag] = (
            _saved_country_complete(parsed, tag)
            and _saved_treasury(parsed, tag) == after_raw
        )
    checks["native_treasury_after_matches_private"] = (
        bool(native_country_checks) and all(native_country_checks.values())
        if money_requested else True)
    checks["save_treasury_after_matches_private"] = (
        bool(save_country_checks) and all(save_country_checks.values())
        if money_requested else True)

    public_provinces = effects.get("provinces") if isinstance(effects, dict) else None
    public_provinces = public_provinces if isinstance(public_provinces, list) else []
    public_province_ids = [
        row.get("province_id") for row in public_provinces
        if isinstance(row, dict)
    ]
    native_province_checks: dict[str, bool] = {}
    save_province_checks: dict[str, bool] = {}
    for row in public_provinces:
        if not isinstance(row, dict) or type(row.get("province_id")) is not int:
            continue
        province_id = int(row["province_id"])
        owner_after = row.get("owner_after")
        controller_after = row.get("controller_after")
        native_item = None
        if isinstance(runtime, dict):
            items = runtime.get("provinces")
            if isinstance(items, list):
                native_item = next((item for item in items
                                    if isinstance(item, dict)
                                    and item.get("province_id") == province_id), None)
        native_owner = native_item.get("owner") if isinstance(native_item, dict) else None
        native_controller = native_item.get("controller") \
            if isinstance(native_item, dict) else None
        native_province_checks[str(province_id)] = (
            isinstance(native_item, dict)
            and native_item.get("record_readable") is True
            and isinstance(native_owner, dict)
            and native_owner.get("identity_verified") is True
            and native_owner.get("tag") == owner_after
            and isinstance(native_controller, dict)
            and native_controller.get("identity_verified") is True
            and native_controller.get("tag") == controller_after
        )
        saved_item = _saved_province_item(parsed, province_id)
        save_province_checks[str(province_id)] = (
            isinstance(saved_item, dict)
            and saved_item.get("complete") is True
            and _saved_province_tag(saved_item, "owner") == owner_after
            and _saved_province_tag(saved_item, "controller") == controller_after
        )
    if public_provinces:
        checks["native_province_effects_match_public_after"] = (
            bool(native_province_checks) and all(native_province_checks.values()))
        checks["save_province_effects_match_public_after"] = (
            bool(save_province_checks) and all(save_province_checks.values()))
    else:
        checks["native_province_effects_match_public_after"] = action_id != "cede_province"
        checks["save_province_effects_match_public_after"] = action_id != "cede_province"
    # A mixed settlement can carry a cede term while its primary action is
    # another effect (for example ``war_reparations``).  The normalized
    # requested list, rather than the primary action, decides whether the
    # public province payload must be compared exactly.  Keep the legacy
    # fallback for direct callers that do not provide term context.
    if isinstance(expected_province_ids, list):
        checks["requested_province_ids_available"] = True
        checks["public_province_ids_exact"] = (
            all(type(value) is int for value in public_province_ids)
            and len(public_province_ids) == len(expected_province_ids)
            and len(public_province_ids) == len(set(public_province_ids))
            and set(public_province_ids) == set(expected_province_ids)
        )
    elif action_id == "cede_province":
        checks["requested_province_ids_available"] = False
        checks["public_province_ids_exact"] = False
    else:
        checks["requested_province_ids_available"] = True
        checks["public_province_ids_exact"] = not public_provinces

    reparations_effect = effects_dict.get("war_reparations")
    if expected_reparations_pair is None and isinstance(reparations_effect, dict):
        payer = reparations_effect.get("payer")
        claimant = reparations_effect.get("claimant")
        if (isinstance(payer, str) and _COUNTRY_TAG_RE.fullmatch(payer)
                and isinstance(claimant, str)
                and _COUNTRY_TAG_RE.fullmatch(claimant)
                and payer != claimant):
            expected_reparations_pair = payer, claimant

    trade_power_effect = effects_dict.get("transfer_trade_power")
    if expected_trade_power_pair is None and isinstance(trade_power_effect, dict):
        source_tag = trade_power_effect.get("source")
        beneficiary_tag = trade_power_effect.get("beneficiary")
        if (isinstance(source_tag, str)
                and _COUNTRY_TAG_RE.fullmatch(source_tag)
                and isinstance(beneficiary_tag, str)
                and _COUNTRY_TAG_RE.fullmatch(beneficiary_tag)
                and source_tag != beneficiary_tag):
            expected_trade_power_pair = source_tag, beneficiary_tag

    native_reparations: object = None
    if isinstance(runtime, dict):
        native_reparations = runtime.get("war_reparations")
    saved_reparations = _saved_war_reparations_snapshot(save_probe)
    saved_query = (saved_reparations.get("query")
                   if isinstance(saved_reparations, dict) else None)
    saved_records = (saved_query.get("matching_records")
                     if isinstance(saved_query, dict) else None)
    saved_records = saved_records if isinstance(saved_records, list) else []
    saved_record = next((record for record in saved_records
                         if isinstance(record, dict)
                         and record.get("complete") is True), None)
    if expected_reparations_pair is not None:
        expected_payer, expected_claimant = expected_reparations_pair
        native_start_date = (native_reparations.get("start_date_raw")
                             if isinstance(native_reparations, dict) else None)
        native_end_date = (native_reparations.get("end_date_raw")
                           if isinstance(native_reparations, dict) else None)
        native_dates_valid = (
            type(native_start_date) is int and type(native_end_date) is int
            and native_end_date > native_start_date)
        public_start_date = (reparations_effect.get("start_date_raw")
                             if isinstance(reparations_effect, dict) else None)
        public_end_date = (reparations_effect.get("end_date_raw")
                           if isinstance(reparations_effect, dict) else None)
        public_dates_present = isinstance(reparations_effect, dict) and any(
            key in reparations_effect for key in ("start_date_raw", "end_date_raw"))
        public_dates_match_native = (
            not public_dates_present
            or (native_dates_valid
                and type(public_start_date) is int
                and type(public_end_date) is int
                and public_start_date == native_start_date
                and public_end_date == native_end_date))
        saved_start_date = (saved_record.get("start_date")
                            if isinstance(saved_record, dict) else None)
        saved_end_date = (saved_record.get("end_date")
                          if isinstance(saved_record, dict) else None)
        saved_date_status = (saved_record.get("date_status")
                             if isinstance(saved_record, dict) else None)
        saved_dates_valid = (
            isinstance(saved_start_date, str)
            and _peace_treaty_save._date_tuple(saved_start_date) is not None
            and isinstance(saved_end_date, str)
            and _peace_treaty_save._date_tuple(saved_end_date) is not None)
        checks.update({
            "public_war_reparations_object": isinstance(reparations_effect, dict),
            "public_war_reparations_payer": (
                isinstance(reparations_effect, dict)
                and reparations_effect.get("payer") == expected_payer),
            "public_war_reparations_claimant": (
                isinstance(reparations_effect, dict)
                and reparations_effect.get("claimant") == expected_claimant),
            "public_war_reparations_active_before": (
                isinstance(reparations_effect, dict)
                and reparations_effect.get("active_before") is False),
            "public_war_reparations_active_after": (
                isinstance(reparations_effect, dict)
                and reparations_effect.get("active_after") is True),
            "public_war_reparations_verified": (
                isinstance(reparations_effect, dict)
                and reparations_effect.get("verified") is True),
            "native_war_reparations_object": isinstance(native_reparations, dict),
            "native_war_reparations_pair": (
                isinstance(native_reparations, dict)
                and native_reparations.get("payer") == expected_payer
                and native_reparations.get("claimant") == expected_claimant),
            "native_war_reparations_present": (
                isinstance(native_reparations, dict)
                and native_reparations.get("present") is True),
            "native_war_reparations_active": (
                isinstance(native_reparations, dict)
                and native_reparations.get("active") is True),
            "native_war_reparations_complete": (
                isinstance(native_reparations, dict)
                and native_reparations.get("complete") is True),
            "native_war_reparations_dates": native_dates_valid,
            "public_war_reparations_dates_match_native": public_dates_match_native,
            "save_war_reparations_pair": (
                isinstance(saved_query, dict)
                and saved_query.get("exact_pair_present") is True
                and bool(saved_records)
                and all(isinstance(record, dict)
                        and record.get("payer") == expected_payer
                        and record.get("claimant") == expected_claimant
                        for record in saved_records)),
            "save_war_reparations_complete": isinstance(saved_record, dict),
            # Keep the serialized dates in the returned observation and require
            # both fields so a pair found without its treaty window is not
            # treated as a complete reload proof.
            "save_war_reparations_dates": (
                saved_dates_valid),
            "save_war_reparations_date_window": (
                isinstance(saved_date_status, dict)
                and saved_date_status.get("comparison_available") is True
                and saved_date_status.get("status") == "active"),
        })
    else:
        checks["war_reparations_not_requested"] = reparations_effect is None

    if expected_trade_power_pair is not None:
        trade_comparison = _compare_trade_power_effect_state(
            native_probe, save_probe, effects, expected_trade_power_pair,
            expected_date_raw if expected_date_raw is not None else (
                runtime.get("current_raw_date") if isinstance(runtime, dict) else None))
        checks.update(trade_comparison["checks"])
    else:
        trade_comparison = None
        checks["transfer_trade_power_not_requested"] = trade_power_effect is None

    concede_effect = effects_dict.get("concede_defeat")
    if expected_concede_defeat_pair is not None:
        concede_comparison = _compare_concede_defeat_effect_state(
            native_probe, save_probe, effects,
            expected_concede_defeat_pair,
            "accepted")
        checks.update(concede_comparison["checks"])
    else:
        concede_comparison = None
        checks["concede_defeat_not_requested"] = concede_effect is None

    annul_effect = effects_dict.get("annul_treaties")
    if expected_annul_treaties_pairs is not None:
        annul_comparison = _compare_annul_treaties_effect_state(
            native_probe, save_probe, effects,
            expected_annul_treaties_pairs,
            "accepted")
        checks.update(annul_comparison["checks"])
    else:
        annul_comparison = None
        checks["annul_treaties_not_requested"] = annul_effect is None

    return {
        "private": True,
        "action_id": action_id,
        "checks": checks,
        "all": all(checks.values()),
        "country_tags": tags,
        "native_country_checks": native_country_checks,
        "save_country_checks": save_country_checks,
        "native_province_checks": native_province_checks,
        "save_province_checks": save_province_checks,
        "requested_province_ids": expected_province_ids,
        "public_province_ids": public_province_ids,
        "public_province_count": len(public_provinces),
        "war_reparations": {
            "expected": {
                "payer": expected_reparations_pair[0],
                "claimant": expected_reparations_pair[1],
            } if expected_reparations_pair is not None else None,
            "public_effect": reparations_effect,
            "native_runtime": native_reparations,
            "saved_query": saved_query,
            "saved_records": saved_records,
        },
        "transfer_trade_power": trade_comparison or {
            "expected": None,
            "public_effect": trade_power_effect,
            "native_runtime": (
                runtime.get("transfer_trade_power")
                if isinstance(runtime, dict) else None),
            "saved_query": None,
            "saved_records": [],
        },
        "concede_defeat": concede_comparison or {
            "expected": None,
            "public_effect": concede_effect,
            "native_country_checks": {},
            "save_country_checks": {},
        },
        "annul_treaties": annul_comparison or {
            "expected_pairs": None,
            "public_effect": annul_effect,
            "native_runtime": (
                runtime.get("annul_treaties")
                if isinstance(runtime, dict) else None),
            "saved_query": None,
            "saved_records": [],
        },
    }


def _compare_rejected_reparations_state(
        native_probe: dict[str, object], save_probe: dict[str, object],
        effects: object,
        expected_reparations_pair: tuple[str, str] | None,
        ) -> dict[str, object]:
    """Compare a rejected reparations term with the reloaded relation state.

    A rejected request still carries a real public effect object.  For the
    usual no-baseline case the native probe returns a readable relation record
    with ``complete=True`` and ``present=False``; that is a successful read of
    an absent relation, rather than a failed probe.  If the source says that a
    relation was already active (or supplies a valid treaty window), the
    current process and save must retain that relation instead of inferring
    absence from the rejected outcome.
    """

    effects_dict = effects if isinstance(effects, dict) else {}
    source_reparations = effects_dict.get("war_reparations")
    source_reparations = (source_reparations
                          if isinstance(source_reparations, dict) else None)
    expected_payer, expected_claimant = expected_reparations_pair \
        if expected_reparations_pair is not None else (None, None)

    source_start = (source_reparations.get("start_date_raw")
                    if isinstance(source_reparations, dict) else None)
    source_end = (source_reparations.get("end_date_raw")
                  if isinstance(source_reparations, dict) else None)
    source_dates_complete = (
        type(source_start) is int and type(source_end) is int)
    source_dates_valid = (
        source_dates_complete and source_end > source_start)
    source_active_before = (source_reparations.get("active_before")
                            if isinstance(source_reparations, dict) else None)
    source_active_after = (source_reparations.get("active_after")
                           if isinstance(source_reparations, dict) else None)
    # R48/R49 encodes an absent relation as the complete 0/0 date pair.  A
    # valid window means the relation record is expected to survive even if
    # it is currently inactive.  Other malformed windows are rejected rather
    # than being silently treated as "no relation".
    source_absent_sentinel = (
        source_dates_complete and source_start == 0 and source_end == 0
        and source_active_before is False and source_active_after is False)
    source_relation_expected = (
        source_active_before is True or source_active_after is True
        or source_dates_valid)
    source_dates_match_state = (
        source_dates_valid if source_relation_expected
        else source_absent_sentinel)

    runtime = _native_probe_runtime(native_probe)
    native_reparations = (runtime.get("war_reparations")
                          if isinstance(runtime, dict) else None)
    saved_reparations = _saved_war_reparations_snapshot(save_probe)
    saved_query = (saved_reparations.get("query")
                   if isinstance(saved_reparations, dict) else None)
    saved_records = (saved_query.get("matching_records")
                     if isinstance(saved_query, dict) else None)
    saved_records = saved_records if isinstance(saved_records, list) else []
    complete_saved_records = [
        record for record in saved_records
        if isinstance(record, dict) and record.get("complete") is True
    ]

    checks: dict[str, bool] = {
        "source_war_reparations_object": source_reparations is not None,
        "source_war_reparations_pair": (
            source_reparations is not None
            and source_reparations.get("payer") == expected_payer
            and source_reparations.get("claimant") == expected_claimant),
        "source_war_reparations_active_before": (
            source_reparations is not None
            and isinstance(source_active_before, bool)),
        "source_war_reparations_active_after": (
            source_reparations is not None
            and isinstance(source_active_after, bool)),
        "source_war_reparations_verified_field": (
            source_reparations is not None
            and isinstance(source_reparations.get("verified"), bool)),
        "source_war_reparations_dates_complete": source_dates_complete,
        "source_war_reparations_dates_match_state": source_dates_match_state,
        "native_war_reparations_object": isinstance(native_reparations, dict),
        "native_war_reparations_complete": (
            isinstance(native_reparations, dict)
            and native_reparations.get("complete") is True),
        "native_war_reparations_pair": (
            isinstance(native_reparations, dict)
            and native_reparations.get("payer") == expected_payer
            and native_reparations.get("claimant") == expected_claimant),
        "native_war_reparations_present": (
            isinstance(native_reparations, dict)
            and native_reparations.get("present") is source_relation_expected),
        "native_war_reparations_active": (
            isinstance(native_reparations, dict)
            and native_reparations.get("active") is source_active_after),
    }

    native_start = (native_reparations.get("start_date_raw")
                    if isinstance(native_reparations, dict) else None)
    native_end = (native_reparations.get("end_date_raw")
                  if isinstance(native_reparations, dict) else None)
    checks["native_war_reparations_dates"] = (
        (source_relation_expected
         and type(native_start) is int and type(native_end) is int
         and native_start == source_start and native_end == source_end
         and native_end > native_start)
        or (not source_relation_expected
            and native_start is None and native_end is None))

    checks["save_war_reparations_query_readable"] = isinstance(saved_query, dict)
    actual_exact_pair = (saved_query.get("exact_pair_present")
                         if isinstance(saved_query, dict) else None)
    checks["save_war_reparations_exact_pair_present"] = (
        actual_exact_pair is source_relation_expected)
    if source_relation_expected:
        checks.update({
            "save_war_reparations_exact_pair_matches_source": (
                actual_exact_pair is True),
            "save_war_reparations_records_complete": (
                bool(complete_saved_records)
                and len(complete_saved_records) == len(saved_records)),
            "save_war_reparations_pair": (
                bool(complete_saved_records)
                and all(record.get("payer") == expected_payer
                        and record.get("claimant") == expected_claimant
                        for record in complete_saved_records)),
        })
    else:
        # Keep an absent pair as a positive parser result.  The scanner's
        # ``exact_pair_present=False`` is the evidence being checked, not a
        # reason to downgrade the save scan to unreadable.
        checks.update({
            "save_war_reparations_exact_pair_absent": (
                actual_exact_pair is False),
            "save_war_reparations_matching_records_absent": (
                not saved_records),
        })

    save_dates_valid = True
    save_active_values: list[bool] = []
    if source_relation_expected:
        save_dates_valid = bool(complete_saved_records)
        for record in complete_saved_records:
            start_date = record.get("start_date")
            end_date = record.get("end_date")
            save_dates_valid = save_dates_valid and (
                isinstance(start_date, str)
                and _peace_treaty_save._date_tuple(start_date) is not None
                and isinstance(end_date, str)
                and _peace_treaty_save._date_tuple(end_date) is not None)
            date_status = record.get("date_status")
            status = date_status.get("status") \
                if isinstance(date_status, dict) else None
            if status is not None:
                save_active_values.append(status == "active")
        checks["save_war_reparations_dates"] = save_dates_valid
        checks["save_war_reparations_active_matches_source"] = (
            bool(save_active_values)
            and all(value is source_active_after
                    for value in save_active_values))

    return {
        "private": True,
        "checks": checks,
        "all": all(checks.values()),
        "expected": {
            "payer": expected_payer,
            "claimant": expected_claimant,
            "active_before": source_active_before,
            "active_after": source_active_after,
            "start_date_raw": source_start,
            "end_date_raw": source_end,
            "relation_present": source_relation_expected,
        },
        "source_effect": source_reparations,
        "native_runtime": native_reparations,
        "saved_query": saved_query,
        "saved_records": saved_records,
    }


def _peace_effect_reload_contract(source: dict[str, object],
                                  execution: dict[str, object],
                                  save_report: dict[str, object],
                                  session: ObserverSession,
                                  expected_date_raw: object,
                                  evidence: Path) -> dict[str, object]:
    """Validate non-white consequences after a fresh process reload.

    Accepted/executed settlements use the existing transition comparison.
    Rejected relation terms use a persistence comparison because rejection
    leaves the source relation unchanged and therefore legitimately reports
    ``present=False`` when the baseline had no treaty.
    """

    outcome = source.get("outcome")
    action_id = source.get("action_id")
    effects = source.get("effects")
    terms = _requested_peace_terms(execution)
    money_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "demand_ducats" for term in terms)
    province_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "cede_province" for term in terms)
    reparations_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "war_reparations" for term in terms)
    trade_power_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "transfer_trade_power" for term in terms)
    concede_defeat_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "concede_defeat" for term in terms)
    annul_treaties_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "annul_treaties" for term in terms)
    special_pairs = {
        action: _requested_peace_special_pair(execution, action)
        for action in _SPECIAL_ACTIONS
    }
    special_term_present = any(pair is not None for pair in special_pairs.values())
    reparations_effect_present = (
        isinstance(effects, dict)
        and isinstance(effects.get("war_reparations"), dict))
    trade_power_effect_present = (
        isinstance(effects, dict)
        and isinstance(effects.get("transfer_trade_power"), dict))
    concede_defeat_effect_present = (
        isinstance(effects, dict)
        and isinstance(effects.get("concede_defeat"), dict))
    annul_treaties_effect_present = (
        isinstance(effects, dict)
        and isinstance(effects.get("annul_treaties"), list))
    special_effect_present = {
        action: isinstance(effects, dict)
        and isinstance(effects.get(action), dict)
        for action in _SPECIAL_ACTIONS
    }
    reparations_pair = _requested_peace_reparations_pair(execution)
    trade_power_pair = _requested_peace_trade_power_pair(execution)
    concede_defeat_pair = _requested_peace_concede_defeat_pair(execution)
    annul_treaties_pairs = _requested_peace_annul_pairs(execution)
    mixed_terms = sum((money_term_present, province_term_present,
                       reparations_term_present, trade_power_term_present,
                       concede_defeat_term_present,
                       annul_treaties_term_present, special_term_present)) > 1
    accepted_applicable = (
        outcome in ("accepted", "executed")
        and (action_id in ("demand_ducats", "cede_province", "war_reparations",
                           "transfer_trade_power", "concede_defeat",
                           "annul_treaties", "humiliate_rival",
                           "show_strength", "force_religion")
             or any((money_term_present, province_term_present,
                     reparations_term_present, trade_power_term_present,
                     concede_defeat_term_present,
                     annul_treaties_term_present, special_term_present))))
    rejected_relation_requested = (
        outcome == "rejected"
        and (reparations_term_present or reparations_effect_present
             or trade_power_term_present or trade_power_effect_present
             or concede_defeat_term_present or concede_defeat_effect_present
             or annul_treaties_term_present or annul_treaties_effect_present
             or special_term_present or any(special_effect_present.values())))
    if not accepted_applicable and not rejected_relation_requested:
        return {
            "applicable": False,
            "all": True,
            "action_id": action_id,
            "outcome": outcome,
            "reason": "effects_not_required_for_rejected_unknown_or_white_result",
            "public_summary": {"absolute_treasury_omitted": True},
        }

    request_id = execution.get("request_id")
    observations = _read_native_effect_observations(execution, request_id)
    private_by_country = observations.get("by_country") \
        if isinstance(observations, dict) else {}
    tags = sorted(str(tag) for tag in private_by_country) \
        if isinstance(private_by_country, dict) else []
    actor = execution.get("actor")
    recipient = execution.get("recipient")
    required_endpoint_tags = [tag for tag in (actor, recipient)
                              if isinstance(tag, str)
                              and _COUNTRY_TAG_RE.fullmatch(tag)]
    required_endpoint_tags = list(dict.fromkeys(required_endpoint_tags))
    endpoint_observations_present = (
        isinstance(private_by_country, dict)
        and all(tag in private_by_country for tag in required_endpoint_tags)
    )
    if isinstance(observations.get("checks"), dict):
        observations["checks"]["endpoint_observations_present"] = (
            endpoint_observations_present or not money_term_present)
        observations["all"] = observations.get("all") is True \
            and (endpoint_observations_present or not money_term_present)
    for tag in (actor, recipient):
        if isinstance(tag, str) and _COUNTRY_TAG_RE.fullmatch(tag) and tag not in tags:
            tags.append(tag)
    if annul_treaties_pairs:
        for tag in {item for pair in annul_treaties_pairs for item in pair}:
            if tag not in tags:
                tags.append(tag)
    for pair in special_pairs.values():
        if pair:
            for tag in pair:
                if tag not in tags:
                    tags.append(tag)
    tags = tags[:_MAX_EFFECT_COUNTRIES]
    requested_province_ids = _requested_peace_province_ids(execution)
    province_ids: list[int] = list(requested_province_ids or [])
    if isinstance(effects, dict) and isinstance(effects.get("provinces"), list):
        for row in effects["provinces"]:
            if (isinstance(row, dict) and type(row.get("province_id")) is int
                    and int(row["province_id"]) not in province_ids):
                province_ids.append(int(row["province_id"]))
    if len(province_ids) > _MAX_EFFECT_PROVINCES:
        province_ids = province_ids[:_MAX_EFFECT_PROVINCES]
    native_probe = _run_effect_probe(
        session, tags, province_ids, expected_date_raw,
        evidence / "probes" / "peace_effect_state.json",
        reparations_pair=reparations_pair,
        trade_power_source=(trade_power_pair[0]
                            if trade_power_pair is not None else None),
        trade_power_beneficiary=(trade_power_pair[1]
                                 if trade_power_pair is not None else None),
        annul_treaties_pairs=annul_treaties_pairs,
        special_action=(next((action for action, pair in special_pairs.items()
                              if pair is not None), None)),
        special_pair=(next((pair for pair in special_pairs.values() if pair is not None), None))) if tags else {
            "private": True, "status": "unavailable", "reason": "effect_country_tags_missing"
        }
    save_province_ids = list(province_ids)
    for special_action, special_pair in special_pairs.items():
        if special_pair is None:
            continue
        runtime = _native_special_runtime(native_probe, special_action)
        capital_id = runtime.get("capital_province_id") if isinstance(runtime, dict) else None
        if (isinstance(runtime, dict) and runtime.get("capital_province_id_verified") is True
                and type(capital_id) is int and capital_id not in save_province_ids):
            save_province_ids.append(capital_id)
    save_probe = _stream_save_effect_state(
        save_report, tags, save_province_ids,
        reparations_pair=reparations_pair,
        trade_power_source=(trade_power_pair[0]
                            if trade_power_pair is not None else None),
        trade_power_beneficiary=(trade_power_pair[1]
                                 if trade_power_pair is not None else None),
        annul_treaties_pairs=annul_treaties_pairs) if tags else {
        "private": True, "status": "unavailable", "reason": "effect_country_tags_missing"
    }
    for special_action, special_pair in special_pairs.items():
        if special_pair is not None:
            _bind_special_capital_save_observation(
                save_probe, native_probe, special_action, special_pair[0])
    if outcome == "rejected":
        relation_comparisons: dict[str, dict[str, object]] = {}
        checks: dict[str, bool] = {}
        if reparations_pair is not None:
            reparations_comparison = _compare_rejected_reparations_state(
                native_probe, save_probe, effects, reparations_pair)
            relation_comparisons["war_reparations"] = reparations_comparison
            checks.update(reparations_comparison.get("checks", {}))
        elif reparations_term_present or reparations_effect_present:
            checks["rejected_reparations_pair_available"] = False
        if trade_power_pair is not None:
            trade_comparison = _compare_rejected_trade_power_state(
                native_probe, save_probe, effects, trade_power_pair)
            relation_comparisons["transfer_trade_power"] = trade_comparison
            checks.update(trade_comparison.get("checks", {}))
        elif trade_power_term_present or trade_power_effect_present:
            checks["rejected_trade_power_pair_available"] = False
        if concede_defeat_pair is not None:
            concede_comparison = _compare_concede_defeat_effect_state(
                native_probe, save_probe, effects, concede_defeat_pair,
                "rejected")
            relation_comparisons["concede_defeat"] = concede_comparison
            checks.update(concede_comparison.get("checks", {}))
        elif concede_defeat_term_present or concede_defeat_effect_present:
            checks["rejected_concede_defeat_pair_available"] = False
        if annul_treaties_pairs is not None:
            annul_comparison = _compare_annul_treaties_effect_state(
                native_probe, save_probe, effects, annul_treaties_pairs,
                "rejected")
            relation_comparisons["annul_treaties"] = annul_comparison
            checks.update(annul_comparison.get("checks", {}))
        elif annul_treaties_term_present or annul_treaties_effect_present:
            checks["rejected_annul_treaties_pair_available"] = False
        for special_action, special_pair in special_pairs.items():
            effect_present = special_effect_present[special_action]
            if special_pair is not None:
                special_comparison = _compare_special_effect_state(
                    native_probe, save_probe, effects, special_pair,
                    special_action, "rejected")
                relation_comparisons[special_action] = special_comparison
                checks.update(special_comparison.get("checks", {}))
            elif effect_present or any(
                    isinstance(term, dict)
                    and term.get("action_id") == special_action
                    for term in (terms or [])):
                checks[f"rejected_{special_action}_pair_available"] = False
        checks["private_observation_file_contract"] = (
            observations.get("all") is True if money_term_present else True)
        checks["native_effect_probe_contract"] = (
            isinstance(native_probe, dict)
            and native_probe.get("status") == "ok")
        checks["save_effect_stream_contract"] = (
            isinstance(save_probe, dict)
            and save_probe.get("status") == "ok")
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        if (mixed_terms and (money_term_present or province_term_present)
                and not concede_defeat_term_present):
            # This R49 branch proves the reparations relation.  Keep source
            # evidence for money/province terms visible, but do not turn a
            # mixed rejected request into a false pass until those other
            # persistence baselines have their own comparison contract.
            checks["rejected_money_effect_unapplied_in_source"] = (
                not money_term_present
                or (isinstance(effects, dict)
                    and effects.get("money") is None))
            checks["rejected_province_effects_unapplied_in_source"] = (
                not province_term_present
                or (isinstance(effects, dict)
                    and isinstance(effects.get("provinces"), list)
                    and not effects.get("provinces")))
            checks["rejected_mixed_effect_persistence_scope"] = False
        comparison = {
            "private": True,
            "checks": checks,
            "all": all(checks.values()),
            "war_reparations": relation_comparisons.get("war_reparations"),
            "transfer_trade_power": relation_comparisons.get("transfer_trade_power"),
            "concede_defeat": relation_comparisons.get("concede_defeat"),
            "annul_treaties": relation_comparisons.get("annul_treaties"),
            "humiliate_rival": relation_comparisons.get("humiliate_rival"),
            "show_strength": relation_comparisons.get("show_strength"),
            "force_religion": relation_comparisons.get("force_religion"),
        }
        return {
            "applicable": True,
            "all": comparison["all"],
            "action_id": action_id,
            "outcome": outcome,
            "request_id": request_id,
            "private_effect_observation": observations,
            "private_native_probe": native_probe,
            "private_save_effect_scan": save_probe,
            "comparison": comparison,
            "public_summary": {
                "absolute_treasury_omitted": True,
                "province_ids": province_ids,
                "requested_province_ids": requested_province_ids,
                "mixed_terms": mixed_terms,
                "money_term_present": money_term_present,
                "province_term_present": province_term_present,
                "reparations_term_present": reparations_term_present,
                "trade_power_term_present": trade_power_term_present,
                 "concede_defeat_term_present": concede_defeat_term_present,
                "annul_treaties_term_present": annul_treaties_term_present,
                "humiliate_rival_term_present": special_pairs["humiliate_rival"] is not None,
                "show_strength_term_present": special_pairs["show_strength"] is not None,
                "force_religion_term_present": special_pairs["force_religion"] is not None,
                "rejected_reparations_only": reparations_term_present and not mixed_terms,
                "rejected_trade_power_only": trade_power_term_present and not mixed_terms,
                "reparations_pair": {
                    "payer": reparations_pair[0],
                    "claimant": reparations_pair[1],
                } if reparations_pair is not None else None,
                "trade_power_pair": {
                    "source": trade_power_pair[0],
                    "beneficiary": trade_power_pair[1],
                } if trade_power_pair is not None else None,
                 "concede_defeat_pair": {
                     "conceding_country": concede_defeat_pair[0],
                     "beneficiary": concede_defeat_pair[1],
                 } if concede_defeat_pair is not None else None,
                "annul_treaties_pairs": [
                    {"country": pair[0], "partner": pair[1]}
                    for pair in annul_treaties_pairs
                ] if annul_treaties_pairs is not None else None,
                "special_pairs": {
                    action: {"country": pair[0], "beneficiary": pair[1]}
                    if pair is not None else None
                    for action, pair in special_pairs.items()
                },
                "effect_summary_present": isinstance(effects, dict),
            },
        }
    comparison = _compare_effect_states(
        observations, native_probe, save_probe, effects, action_id,
        requested_province_ids, reparations_pair, trade_power_pair,
        expected_concede_defeat_pair=concede_defeat_pair,
        expected_annul_treaties_pairs=annul_treaties_pairs,
        expected_date_raw=expected_date_raw)
    checks = dict(comparison.get("checks", {}))
    special_comparisons: dict[str, dict[str, object]] = {}
    for special_action, special_pair in special_pairs.items():
        if special_pair is not None:
            special_comparison = _compare_special_effect_state(
                native_probe, save_probe, effects, special_pair,
                special_action, "accepted")
            special_comparisons[special_action] = special_comparison
            checks.update(special_comparison.get("checks", {}))
        else:
            checks[f"{special_action}_not_requested"] = not special_effect_present[special_action]
    checks["private_observation_file_contract"] = (
        observations.get("all") is True if money_term_present else True)
    checks["native_effect_probe_contract"] = native_probe.get("status") == "ok"
    checks["save_effect_stream_contract"] = save_probe.get("status") == "ok"
    if reparations_term_present or concede_defeat_term_present or mixed_terms:
        # A mixed settlement must retain the source execution contract for
        # every requested effect and independently prove every requested
        # province/reparations relation after reload.  The country/province
        # checks below compare both live and saved state against the private
        # native after-observations.
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        checks["mixed_source_effects_contract"] = checks["source_effects_contract"]
    if trade_power_term_present:
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        checks["trade_power_source_effects_contract"] = checks[
            "source_effects_contract"]
    if concede_defeat_term_present:
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        checks["concede_defeat_source_effects_contract"] = checks[
            "source_effects_contract"]
    if annul_treaties_term_present:
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        checks["annul_treaties_source_effects_contract"] = checks[
            "source_effects_contract"]
    if special_term_present:
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        checks["special_source_effects_contract"] = checks["source_effects_contract"]
    if mixed_terms:
        checks["mixed_payment_and_allocation_verified"] = all(
            checks.get(name) is True for name in (
                "native_treasury_after_matches_private",
                "save_treasury_after_matches_private",
                "native_province_effects_match_public_after",
                "save_province_effects_match_public_after"))
    comparison["checks"] = checks
    comparison["special"] = special_comparisons
    comparison["all"] = all(checks.values())
    return {
        "applicable": True,
        "all": comparison["all"],
        "action_id": action_id,
        "outcome": outcome,
        "request_id": request_id,
        "private_effect_observation": observations,
        "private_native_probe": native_probe,
        "private_save_effect_scan": save_probe,
        "comparison": comparison,
        "public_summary": {
            "absolute_treasury_omitted": True,
            "province_ids": province_ids,
            "requested_province_ids": requested_province_ids,
            "mixed_terms": mixed_terms,
            "money_term_present": money_term_present,
            "province_term_present": province_term_present,
            "reparations_term_present": reparations_term_present,
            "trade_power_term_present": trade_power_term_present,
            "concede_defeat_term_present": concede_defeat_term_present,
            "annul_treaties_term_present": annul_treaties_term_present,
            "reparations_pair": {
                "payer": reparations_pair[0],
                "claimant": reparations_pair[1],
            } if reparations_pair is not None else None,
            "trade_power_pair": {
                "source": trade_power_pair[0],
                "beneficiary": trade_power_pair[1],
            } if trade_power_pair is not None else None,
            "concede_defeat_pair": {
                "conceding_country": concede_defeat_pair[0],
                "beneficiary": concede_defeat_pair[1],
            } if concede_defeat_pair is not None else None,
            "annul_treaties_pairs": [
                {"country": pair[0], "partner": pair[1]}
                for pair in annul_treaties_pairs
            ] if annul_treaties_pairs is not None else None,
            "special_pairs": {
                action: {"country": pair[0], "beneficiary": pair[1]}
                if pair is not None else None
                for action, pair in special_pairs.items()
            },
            "effect_summary_present": isinstance(effects, dict),
        },
    }


def _source_map(value: object) -> dict[str, str] | None:
    if not isinstance(value, list) or len(value) < _REQUIRED_SOURCE_FLOOR:
        return None
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        digest = item.get("sha256")
        if not isinstance(name, str) or not name.strip() \
                or not isinstance(digest, str):
            return None
        if _SHA256_RE.fullmatch(digest) is None or name in result:
            return None
        result[name] = digest.casefold()
    if len(result) < _REQUIRED_SOURCE_FLOOR:
        return None
    if not _REQUIRED_SOURCE_NAMES.issubset(result):
        return None
    return result


def _binding_contract(source: dict[str, object], current: dict[str, object],
                      current_session_dll: object) -> dict[str, object]:
    source_manifest = source.get("build_manifest")
    current_manifest = current.get("build_manifest")
    source_map = _source_map(
        source_manifest.get("sources") if isinstance(source_manifest, dict) else None)
    current_map = _source_map(
        current_manifest.get("sources") if isinstance(current_manifest, dict) else None)
    source_build = source.get("build_binding")
    current_build = current.get("build_binding")
    source_session = source.get("session")
    source_dll = source_session.get("dll_sha256") if isinstance(source_session, dict) else None
    current_install = current.get("installation")
    current_declared = (
        current_install.get("declared_dll_sha256")
        if isinstance(current_install, dict) else None)
    checks = {
        # Require the stable R45G source set on both sides.  Additional effect
        # sources are allowed, but are covered by the full map equality below.
        "source_has_required_source_set": source_map is not None,
        "reload_has_required_source_set": current_map is not None,
        # Compatibility labels retained for consumers of the previous report
        # schema; their value now means the stable-set check above, not merely
        # a list length check.
        "source_has_required_source_floor": source_map is not None,
        "reload_has_required_source_floor": current_map is not None,
        "source_reload_source_hashes_equal": source_map is not None
        and source_map == current_map,
        "source_build_matches_dll": isinstance(source_build, dict)
        and source_build.get("installation_matches_build_manifest") is True,
        "reload_build_matches_dll": isinstance(current_build, dict)
        and current_build.get("installation_matches_build_manifest") is True,
        "source_reload_dll_equal": isinstance(source_dll, str)
        and isinstance(current_session_dll, str)
        and source_dll.casefold() == current_session_dll.casefold(),
        "reload_loaded_dll_matches_installation": isinstance(current_session_dll, str)
        and isinstance(current_declared, str)
        and current_session_dll.casefold() == current_declared.casefold(),
    }
    return {
        "checks": checks,
        "all": all(checks.values()),
        "source_dll_sha256": source_dll,
        "reload_dll_sha256": current_session_dll,
        "reload_declared_dll_sha256": current_declared,
        "source_source_count": len(source_map) if source_map is not None else None,
        "reload_source_count": len(current_map) if current_map is not None else None,
        "required_source_floor": _REQUIRED_SOURCE_FLOOR,
        "required_source_names_count": len(_REQUIRED_SOURCE_NAMES),
    }


def _control_contract(source: dict[str, object], save_report: dict[str, object],
                      health: dict[str, object], current_control: dict[str, object],
                      current_probes: object, source_probes: dict[str, object]
                      ) -> dict[str, object]:
    source_after = source.get("after") if isinstance(source.get("after"), dict) else {}
    source_control = source_after.get("control") if isinstance(source_after, dict) else {}
    save_probe = save_report.get("probe_after") if isinstance(save_report, dict) else {}
    save_signature = save_probe.get("signature") if isinstance(save_probe, dict) else {}
    expected_date = source.get("expected_date_raw")
    if type(expected_date) is not int and isinstance(source_control, dict):
        expected_date = source_control.get("date_raw")
    source_before = source.get("before") if isinstance(source.get("before"), dict) else {}
    source_before_control = source_before.get("control") \
        if isinstance(source_before, dict) else {}
    checks = {
        "source_date_integer": type(expected_date) is int,
        "source_before_por_paused": isinstance(source_before_control, dict)
        and source_before_control.get("paused_flag") == 1
        and source_before_control.get("player_slot") == _PLAYER_SLOT,
        "source_after_por_paused": isinstance(source_control, dict)
        and source_control.get("paused_flag") == 1
        and source_control.get("player_slot") == _PLAYER_SLOT,
        "source_before_after_same_date": isinstance(source_before_control, dict)
        and isinstance(source_control, dict)
        and source_before_control.get("date_raw") == source_control.get("date_raw"),
        "health_ready": health.get("status") == "ready"
        and health.get("complete") is True,
        "health_date_matches_source": health.get("date_raw") == expected_date,
        "control_date_matches_source": current_control.get("date_raw") == expected_date,
        "save_probe_date_matches_source": save_signature.get("date_raw") == expected_date,
        "por_player_slot": current_control.get("player_slot") == _PLAYER_SLOT,
        "paused": current_control.get("paused_flag") == 1,
        "four_reload_probes_complete": _snapshots_complete(current_probes),
        "four_source_probes_complete": _snapshots_complete(source_probes),
    }
    return {
        "checks": checks,
        "all": all(checks.values()),
        "source_control": source_control,
        "save_signature": save_signature,
        "reload_control": current_control,
    }


def _war_contract(source_summary: dict[str, object], current_probes: object
                  ) -> dict[str, object]:
    source_before = source_summary.get("source_before", {})
    source_after = source_summary.get("source_after", {})
    reload = _war_pair_summary_for(current_probes)
    expected = source_summary.get("expected_pair_at_war_after")
    known = expected in (True, False)
    checks = {
        "source_before_complete": source_before.get("complete") is True,
        "source_after_complete": source_after.get("complete") is True,
        "reload_complete": reload.get("complete") is True,
        "source_before_at_war": source_before.get("pair_at_war") is True,
        "source_after_matches_result": known
        and source_after.get("pair_at_war") is expected,
        "reload_matches_result": known
        and reload.get("pair_at_war") is expected,
        "source_reload_war_match": source_after.get("pair_at_war")
        == reload.get("pair_at_war"),
    }
    return {
        "checks": checks,
        "all": known and all(checks.values()),
        "expected_pair_at_war_after": expected,
        "source_before": source_before,
        "source_after": source_after,
        "reload": reload,
    }


def _diplomat_observation(source_probes: dict[str, object],
                          current_probes: object) -> dict[str, object]:
    def read(records: object) -> object:
        if not isinstance(records, dict):
            return None
        item = records.get("diplomats")
        snapshot = item.get("snapshot") if isinstance(item, dict) else None
        if not isinstance(snapshot, dict):
            return None
        try:
            return _diplomat_semantics(snapshot)
        except Exception as error:  # preserve observation failure as data
            return {"error": type(error).__name__, "message": str(error)}

    source_value = read(source_probes)
    reload_value = read(current_probes)
    return {
        "source_after": source_value,
        "reload": reload_value,
        "available": isinstance(source_value, list) and isinstance(reload_value, list),
        "semantic_equal_observation": source_value == reload_value
        if isinstance(source_value, list) and isinstance(reload_value, list) else None,
        "comparison_is_observational_only": True,
        "note": "外交官可用数、任务记录和归途/冷却字段只记录事实，不作为重载通过条件。",
    }


def _source_unknown_preserved(summary: dict[str, object]) -> bool:
    """Accept either a verifiable known outcome or an explicitly unknown one."""

    outcome = summary.get("outcome")
    known = outcome in ("executed", "accepted", "rejected")
    if known:
        return summary.get("verifiable") is True and summary.get("unknown") is False
    return summary.get("unknown") is True and summary.get("verifiable") is False


def _offline_contract_assertions() -> None:
    """Regression-test the known/unknown source-result distinction."""

    assert _source_unknown_preserved({
        "outcome": "rejected", "verifiable": True, "unknown": False,
    })
    assert _source_unknown_preserved({
        "outcome": "unknown", "verifiable": False, "unknown": True,
    })
    assert not _source_unknown_preserved({
        "outcome": "rejected", "verifiable": False, "unknown": False,
    })
    assert not _source_unknown_preserved({
        "outcome": "unknown", "verifiable": True, "unknown": False,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="新进程 installation.json")
    parser.add_argument("--recipient", type=_recipient_arg,
                        default=_DEFAULT_RECIPIENT,
                        help="议和目标国；默认 ENG，FRA 为固定 actor")
    parser.add_argument("--execution-report", type=Path, required=True,
                        help="出站 Peace execution report.json 或其目录")
    parser.add_argument("--save-report", type=Path, required=True,
                        help="对应 save-observer-report-*.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="新的验收报告路径或目录")
    args = parser.parse_args(argv)
    _offline_contract_assertions()
    global _RECIPIENT
    _RECIPIENT = args.recipient
    os.environ["EU4_WAR_PAIR_RECIPIENT"] = _RECIPIENT

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, object] = {
        "validator": Path(__file__).name,
        "version": 2,
        "status": "running",
        "mode": "read_only_peace_outbound_reload",
        "installation": str(args.installation),
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "execution_report": str(args.execution_report),
        "save_report": str(args.save_report),
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
        execution = _read_json(execution_path)
        save_report = _read_json(save_report_path)
        if not isinstance(execution, dict):
            raise ReloadValidationError("EXECUTION_REPORT_NOT_OBJECT")
        if not isinstance(save_report, dict):
            raise ReloadValidationError("SAVE_REPORT_NOT_OBJECT")
        if execution.get("actor") != _ACTOR or execution.get("recipient") != _RECIPIENT:
            raise ReloadValidationError("RECIPIENT_MISMATCH")

        source = _source_execution_contract(execution)
        source_probes = _source_probe_contract(execution)
        save = _save_contract(save_report)
        report["source"] = {
            "path": str(execution_path),
            "sha256": _hash_file(execution_path, maximum=_MAX_METADATA_BYTES),
            "summary": source,
        }
        report["save"] = {
            "path": str(save_report_path),
            "sha256": _hash_file(save_report_path, maximum=_MAX_METADATA_BYTES),
            "summary": save,
        }
        if source.get("fatal") is True:
            raise ReloadValidationError("SOURCE_EXECUTION_IDENTITY_OR_PROBES_INVALID")
        if source.get("unknown") is not True and source.get("verifiable") is not True:
            raise ReloadValidationError("SOURCE_EXECUTION_CONTRACT_FAILED")
        if not save["all"]:
            raise ReloadValidationError("SAVE_REPORT_OR_HASH_CONTRACT_FAILED")

        current_binding = _installation_binding(installation)
        report["reload_binding"] = current_binding
        session = ObserverSession(installation, game_exe())
        source_session = execution.get("session")
        source_session_id = source_session.get("session_id") \
            if isinstance(source_session, dict) else None
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "creation_filetime": session.record.get("creation_filetime"),
            "dll_sha256": session.record.get("dll_sha256"),
            "source_session_id": source_session_id,
            "new_process": isinstance(source_session_id, str)
            and session.session_id != source_session_id,
        }
        report["build_binding"] = _binding_contract(
            execution, current_binding, session.record.get("dll_sha256"))
        health = wait_runtime_ready(session, restore_minimized=False)
        probes = _run_snapshots(session, evidence / "probes")
        current_control_snapshot = probes.get("control_state", {}).get("snapshot")
        current_control = _control_summary(current_control_snapshot) \
            if isinstance(current_control_snapshot, dict) else {}
        report["after"] = {
            "health": health,
            "control": current_control,
            "probes": _public_probe_records(probes),
        }

        control = _control_contract(
            execution, save_report, health, current_control, probes,
            source_probes["after"])
        war = _war_contract(source, probes)
        diplomats = _diplomat_observation(source_probes["after"], probes)
        effects = _peace_effect_reload_contract(
            source, execution, save_report, session,
            source.get("expected_date_raw"), evidence)
        report["comparisons"] = {
            "control": control,
            "war": war,
            "diplomats_and_cooldowns": diplomats,
            "peace_effects": effects,
            "source_outcome": source.get("outcome"),
            "action_id": source.get("action_id"),
        }
        report["checks"] = {
            "source_execution_contract": source.get("verifiable") is True,
            "source_unknown_preserved": _source_unknown_preserved(source),
            "save_hash_contract": save["all"],
            "new_process_identity": report["session"].get("new_process") is True,
            "same_immutable_dll_and_manifest_sources": report["build_binding"].get("all") is True,
            "control_boundary": control["all"],
            "war_state_matches_source_outcome": war["all"],
            "diplomat_observation_recorded": diplomats["available"] is True,
            "peace_effects_match_source_private_and_save": effects["all"],
            "no_business_replay_or_world_control": (
                report["business_submission"] is False
                and report["advance_requested"] is False
                and report["save_requested"] is False
                and report["restart_requested"] is False
                and report["installation_requested"] is False
            ),
        }
        if source.get("unknown") is True:
            report["status"] = "unknown"
        else:
            report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:  # retain a bounded diagnostic, never replay work
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_PEACE_OUTBOUND_RELOAD_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path) if report_path is not None else None,
        "action_id": report.get("comparisons", {}).get("action_id")
        if isinstance(report.get("comparisons"), dict) else None,
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
