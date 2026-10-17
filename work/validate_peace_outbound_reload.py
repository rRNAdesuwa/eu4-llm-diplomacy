#!/usr/bin/env python3
"""Validate an outbound Peace result after a fresh read-only reload.

The source execution report and save-observer report are immutable evidence.
This validator attaches to the already running reload installation, captures
the four bounded probes, verifies the saved file by streaming its hash, and
checks the FRA--ENG war state against the source native outcome.  It never
publishes a request, retries an operation, advances time, saves, installs, or
restarts the game.  Diplomat and cooldown records are reported as facts; a
normal change in those records is not treated as a reload failure.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
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
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_peace_inbound_response import _war_pair_summary  # noqa: E402
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
_FAMILY = "peace"
_ACTIONS = frozenset(("white_peace", "demand_ducats", "cede_province"))
_DIRECTIONS = frozenset(("demand", "offer"))
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_MAX_EFFECT_EVENT_BYTES = 8 * 1024 * 1024
_MAX_EFFECT_COUNTRIES = 32
_MAX_EFFECT_PROVINCES = 16
_EFFECT_PROBE_TIMEOUT_SECONDS = 30
_TREASURY_RAW_SCALE = 1000
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
    source_after = _war_pair_summary(probes["after"])
    source_before = _war_pair_summary(probes["before"])
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


def _stream_save_effect_state(save_report: dict[str, object],
                              country_tags: list[str],
                              province_ids: list[int]) -> dict[str, object]:
    """Stream only the affected country/province blocks from the target save."""

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
        return {
            "private": True,
            "status": "ok",
            "streaming": True,
            "path": str(path),
            "sha256": source.get("sha256"),
            "parsed": parsed,
        }
    except Exception as error:  # preserve an unavailable comparison as evidence
        return {
            "private": True,
            "status": "unavailable",
            "path": str(path),
            "reason": f"save_effect_scan_failed:{type(error).__name__}",
        }


def _run_effect_probe(session: ObserverSession, country_tags: list[str],
                      province_ids: list[int], expected_date_raw: object,
                      destination: Path) -> dict[str, object]:
    """Run the fixed-offset probe in a read-only child process."""

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
    return []


def _compare_effect_states(observations: dict[str, object],
                           native_probe: dict[str, object],
                           save_probe: dict[str, object],
                           effects: object,
                           action_id: object,
                           expected_province_ids: list[int] | None = None
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
    checks["private_observations_complete"] = observations.get("all") is True \
        if isinstance(observations, dict) else False
    checks["private_country_count_nonzero"] = bool(tags)
    checks["native_probe_readable"] = (isinstance(native_probe, dict)
                                        and native_probe.get("status") == "ok"
                                        and isinstance(runtime, dict))
    checks["save_probe_readable"] = (isinstance(save_probe, dict)
                                      and save_probe.get("status") == "ok"
                                      and isinstance(parsed, dict))

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
    checks["native_treasury_after_matches_private"] = bool(native_country_checks) \
        and all(native_country_checks.values())
    checks["save_treasury_after_matches_private"] = bool(save_country_checks) \
        and all(save_country_checks.values())

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
    if action_id == "cede_province":
        checks["requested_province_ids_available"] = isinstance(expected_province_ids, list)
        checks["public_province_ids_exact"] = (
            isinstance(expected_province_ids, list)
            and all(type(value) is int for value in public_province_ids)
            and len(public_province_ids) == len(expected_province_ids)
            and len(public_province_ids) == len(set(public_province_ids))
            and set(public_province_ids) == set(expected_province_ids)
        )
    else:
        checks["requested_province_ids_available"] = True
        checks["public_province_ids_exact"] = not public_provinces

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
    }


def _peace_effect_reload_contract(source: dict[str, object],
                                  execution: dict[str, object],
                                  save_report: dict[str, object],
                                  session: ObserverSession,
                                  expected_date_raw: object,
                                  evidence: Path) -> dict[str, object]:
    """Validate accepted non-white consequences when evidence exists."""

    outcome = source.get("outcome")
    action_id = source.get("action_id")
    applicable = outcome in ("accepted", "executed") and action_id in (
        "demand_ducats", "cede_province")
    if not applicable:
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
            endpoint_observations_present)
        observations["all"] = observations.get("all") is True \
            and endpoint_observations_present
    for tag in (actor, recipient):
        if isinstance(tag, str) and _COUNTRY_TAG_RE.fullmatch(tag) and tag not in tags:
            tags.append(tag)
    tags = tags[:_MAX_EFFECT_COUNTRIES]
    effects = source.get("effects")
    terms = _requested_peace_terms(execution)
    money_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "demand_ducats" for term in terms)
    province_term_present = isinstance(terms, list) and any(
        term.get("action_id") == "cede_province" for term in terms)
    mixed_terms = money_term_present and province_term_present
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
        evidence / "probes" / "peace_effect_state.json") if tags else {
            "private": True, "status": "unavailable", "reason": "effect_country_tags_missing"
        }
    save_probe = _stream_save_effect_state(save_report, tags, province_ids) if tags else {
        "private": True, "status": "unavailable", "reason": "effect_country_tags_missing"
    }
    comparison = _compare_effect_states(
        observations, native_probe, save_probe, effects, action_id,
        requested_province_ids)
    checks = dict(comparison.get("checks", {}))
    checks["private_observation_file_contract"] = observations.get("all") is True
    checks["native_effect_probe_contract"] = native_probe.get("status") == "ok"
    checks["save_effect_stream_contract"] = save_probe.get("status") == "ok"
    if mixed_terms:
        # A mixed settlement must retain the source execution contract for
        # the payment and independently prove every requested province after
        # reload.  The country/province checks below compare both live and
        # saved state against the private native after-observations.
        result_contract = execution.get("result_contract")
        effects_contract = (result_contract.get("effects_contract")
                            if isinstance(result_contract, dict) else None)
        checks["mixed_source_effects_contract"] = (
            isinstance(effects_contract, dict)
            and effects_contract.get("all") is True)
        checks["mixed_payment_and_allocation_verified"] = all(
            checks.get(name) is True for name in (
                "native_treasury_after_matches_private",
                "save_treasury_after_matches_private",
                "native_province_effects_match_public_after",
                "save_province_effects_match_public_after"))
    comparison["checks"] = checks
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
    reload = _war_pair_summary(current_probes)
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
    parser.add_argument("--execution-report", type=Path, required=True,
                        help="出站 Peace execution report.json 或其目录")
    parser.add_argument("--save-report", type=Path, required=True,
                        help="对应 save-observer-report-*.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="新的验收报告路径或目录")
    args = parser.parse_args(argv)
    _offline_contract_assertions()

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, object] = {
        "validator": Path(__file__).name,
        "version": 2,
        "status": "running",
        "mode": "read_only_peace_outbound_reload",
        "installation": str(args.installation),
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
