"""Operator-only runtime validation for the read-only alliance query path.

The validator is deliberately separate from the bridge and the native source.
It binds one previously installed observer to its process identity, takes
read-only before/after snapshots, exercises the four semantic bridge methods,
and then sends bounded negative protocol cases to the observer's request
channel.  A request is never retried after a timeout: an unobserved request is
recorded as ``unknown`` and the run stops.

This file is an operator tool.  Its output may contain the installation path,
process identity, request wire and native log evidence.  It must not be used
as an LLM-facing tool or as an execution adapter.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "work") not in sys.path:
    sys.path.insert(0, str(ROOT / "work"))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from bridge.diplomacy_session import probe_identity  # noqa: E402
from local_config import game_exe, get_value  # noqa: E402


DEFAULT_TIMEOUT_SECONDS = 10.0
PROBE_TIMEOUT_SECONDS = 30.0
MAX_LOG_CHUNK = 256 * 1024
FILETIME_UNIX_EPOCH = 116444736000000000
FILETIME_TICKS_PER_SECOND = 10_000_000

EXPECTED_NATIVE_REASON_CODES = {
    "creation_wrong": "QUERY_SESSION_CHANGED",
    "expiry_past": "QUERY_EXPIRED",
    "expiry_over_60_seconds": "QUERY_EXPIRY_OUT_OF_RANGE",
    "date_wrong": "QUERY_GAME_CONTEXT_CHANGED",
    "duplicate_id_seed": "QUERY_GAME_CONTEXT_CHANGED",
    "duplicate_id": "QUERY_ID_DUPLICATE",
    "unsupported_action": "QUERY_ACTION_UNSUPPORTED",
    "zzz_country": "QUERY_COUNTRY_RESOLUTION_UNAVAILABLE",
    "malformed_wire": "QUERY_WIRE_INVALID",
}

# r11 did not expose the UI selector result and therefore remains a supported
# legacy fixture.  r12 exposes the selector only for the initiate phase of the
# Offer/Cancel alliance family.  Keep the five original pairs stable so that a
# legacy report cannot accidentally pass as a UI coverage report, then add the
# two PRO pairs only when the new native coverage fields are present.
BASE_ALLIANCE_INSPECTION_PAIRS = (
    ("offer_alliance", "SAV"),
    ("offer_alliance", "ENG"),
    ("offer_alliance", "POR"),
    ("dissolve_alliance", "SAV"),
    ("dissolve_alliance", "SCO"),
)

UI_COVERED_EXTRA_PAIRS = (
    ("offer_alliance", "PRO"),
    ("dissolve_alliance", "PRO"),
)

UI_COVERED_EXPECTATIONS = {
    ("offer_alliance", "SAV"): {
        "visibility": "visible", "legality": "available", "native_visibility": True,
    },
    ("offer_alliance", "ENG"): {
        "visibility": "visible", "legality": "unavailable", "native_visibility": True,
    },
    ("offer_alliance", "POR"): {
        "visibility": "visible", "legality": "available", "native_visibility": True,
    },
    ("offer_alliance", "LIT"): {
        "visibility": "visible", "legality": "available", "native_visibility": True,
    },
    ("dissolve_alliance", "SAV"): {
        "visibility": "hidden", "legality": "unavailable", "native_visibility": False,
    },
    ("dissolve_alliance", "SCO"): {
        "visibility": "hidden", "legality": "unavailable", "native_visibility": False,
    },
    ("offer_alliance", "PRO"): {
        "visibility": "hidden", "legality": "unavailable", "native_visibility": False,
    },
    ("dissolve_alliance", "PRO"): {
        "visibility": "visible", "legality": "available", "native_visibility": True,
    },
}

UI_COVERAGE_FIELDS = (
    "ui_selection_checked",
    "native_visibility",
    "ui_enabled_gate_checked",
    "full_rules_complete",
)

# r13 exposes a native current acceptance predicate for external recipients.
# Keep the additional LIT query conditional so an r12 installation, whose
# acceptance prediction remains unknown, continues to validate as legacy.
R13_ACCEPTANCE_EXPECTATIONS = {
    ("offer_alliance", "SAV"): "accept",
    ("offer_alliance", "LIT"): "reject",
}

R13_NO_PREDICTION_PAIRS = (
    ("offer_alliance", "POR"),
    ("dissolve_alliance", "SAV"),
    ("dissolve_alliance", "SCO"),
    ("dissolve_alliance", "PRO"),
)

class ValidationStop(RuntimeError):
    """A controlled stop which must be preserved in the validation report."""

    def __init__(self, code: str, message: str, stage: str, *, unknown: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.unknown = unknown


@dataclass(frozen=True)
class ProbeSpec:
    """A discovered read-only probe and its stable report name."""

    name: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class NativeCase:
    name: str
    query_id: str
    wire: str
    expected_reason_code: str
    setup_only: bool = False


class ValidationObserverSession(ObserverSession):
    """ObserverSession that keeps its temporary queue probe under validation output.

    ``ObserverSession.alliance_objects`` is already read-only, but its legacy
    temporary JSON path is the installation directory.  Redirecting only that
    temporary path avoids touching an immutable r9/r10 evidence directory;
    ``inspect_alliance`` still uses the real installation directory for the
    observer request and log channel.
    """

    def __init__(self, installation: Path, game_path: Path, queue_output: Path):
        super().__init__(installation, game_path)
        self._queue_output = queue_output
        self._queue_output.mkdir(parents=True, exist_ok=True)

    def alliance_objects(self, actor: str, recipient: str) -> dict:
        original = self.directory
        self.directory = self._queue_output
        try:
            return super().alliance_objects(actor, recipient)
        finally:
            self.directory = original


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="\n") as stream:
        stream.write(value)


def _unique_output_directory(root: Path) -> Path:
    """Create an output directory without ever reusing an evidence path."""

    root.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        candidate = root / f"validation-alliance-{_utc_stamp()}-{uuid.uuid4().hex[:12]}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError("VALIDATION_OUTPUT_DIRECTORY_COLLISION")


def _read_install_ack(log_path: Path, session_id: str) -> dict[str, Any] | None:
    """Read the same bounded installation acknowledgement as ObserverSession."""

    try:
        with log_path.open("rb") as stream:
            header = stream.read(64 * 1024)
    except OSError:
        return None
    for raw_line in header.splitlines()[:16]:
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and event.get("event") == "diplomacy_observer_installed" \
                and event.get("session_id") == session_id:
            return event
    return None


def _read_first_event(log_path: Path, event_name: str) -> dict[str, Any] | None:
    try:
        with log_path.open("rb") as stream:
            header = stream.read(64 * 1024)
    except OSError:
        return None
    for raw_line in header.splitlines()[:64]:
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and event.get("event") == event_name:
            return event
    return None


def _require_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationStop("INSTALLATION_RECORD_INVALID", f"{name} must be an integer", "preflight")
    return value


def _preflight(installation: Path, expected_date_raw: int, output: Path) -> dict[str, Any]:
    """Prove identity, observer health and execution lock before any query token."""

    if sys.platform != "win32":
        raise ValidationStop("WINDOWS_X64_SESSION_REQUIRED", "EU4 observer validation requires Windows x64", "preflight")
    try:
        raw_record = json.loads(installation.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationStop("INSTALLATION_RECORD_INVALID", str(error), "preflight") from error
    if not isinstance(raw_record, dict):
        raise ValidationStop("INSTALLATION_RECORD_INVALID", "installation JSON is not an object", "preflight")
    record = raw_record
    if record.get("installation_returncode") != 0:
        raise ValidationStop("INSTALLATION_NOT_CONFIRMED", "observer installation did not return zero", "preflight")

    try:
        pid = _require_int(record.get("pid"), "pid")
        creation_filetime = _require_int(record.get("creation_filetime"), "creation_filetime")
        expected_session_id = str(record["session_id"])
        expected_dll_sha256 = str(record["dll_sha256"]).lower()
    except KeyError as error:
        raise ValidationStop("INSTALLATION_RECORD_INVALID", f"missing {error.args[0]}", "preflight") from error

    try:
        executable = game_exe()
        actual_identity = probe_identity(pid, executable)
    except Exception as error:  # probe_identity intentionally reports only operator-side details
        raise ValidationStop("OBSERVER_PROCESS_IDENTITY_UNAVAILABLE", str(error), "preflight") from error

    checks = {
        "pid_matches": actual_identity.get("pid") == pid,
        "creation_matches": actual_identity.get("creation_filetime") == creation_filetime,
        "session_matches": actual_identity.get("session_id") == expected_session_id,
        "game_hash_matches": actual_identity.get("game_sha256") == str(record.get("game_sha256", "")).lower(),
    }
    modules = actual_identity.get("modules") or []
    checks["single_observer_module"] = len(modules) == 1
    checks["observer_dll_hash_matches"] = bool(modules) and str(modules[0].get("sha256", "")).lower() == expected_dll_sha256
    if not all(checks.values()):
        raise ValidationStop("OBSERVER_IDENTITY_MISMATCH", json.dumps(checks, ensure_ascii=False), "preflight")

    log_path = installation.resolve().parent / "control-probe.jsonl"
    ack = _read_install_ack(log_path, expected_session_id)
    if ack is None:
        raise ValidationStop("INSTALLATION_ACK_NOT_FOUND", "no matching observer installation ack", "preflight")
    capabilities = ValidationObserverSession(installation.resolve(), executable, output / "bridge-queue-probes").installation_capabilities()
    if "native_alliance_inspection" not in capabilities:
        raise ValidationStop("NATIVE_QUERY_CAPABILITY_NOT_ACKNOWLEDGED", "alliance query capability is not acknowledged", "preflight")
    if ack.get("native_execution_enabled") is not False:
        raise ValidationStop("NATIVE_EXECUTION_STATUS_UNVERIFIED", "observer execution lock is not explicitly false", "preflight")
    trace = _read_first_event(log_path, "command_execution_trace_installed")
    if trace is not None and trace.get("mutates_actions") is not False:
        raise ValidationStop("OBSERVER_TRACE_MUTATION_UNVERIFIED", "command observer does not declare mutates_actions=false", "preflight")

    session = ValidationObserverSession(installation.resolve(), executable, output / "bridge-queue-probes")
    health = session.health()
    if health.get("status") != "ready":
        raise ValidationStop("OBSERVER_FRAME_HEALTH_NOT_READY", json.dumps(health, ensure_ascii=False), "preflight")
    if health.get("date_raw") != expected_date_raw:
        raise ValidationStop("EXPECTED_DATE_MISMATCH", json.dumps({"health": health, "expected": expected_date_raw}, ensure_ascii=False), "preflight")

    request_path = session.directory / "diplomacy-query.request"
    if request_path.exists():
        # Never remove or reuse another operator's pending request.
        raise ValidationStop("QUERY_CHANNEL_BUSY", str(request_path), "preflight", unknown=True)
    try:
        with log_path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            log_size = stream.tell()
            if log_size:
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    raise ValidationStop("QUERY_LOG_INCOMPLETE", "control log has an incomplete final line", "preflight", unknown=True)
    except ValidationStop:
        raise
    except OSError as error:
        raise ValidationStop("QUERY_LOG_UNAVAILABLE", str(error), "preflight") from error

    return {
        "record": record,
        "session": session,
        "actual_identity": actual_identity,
        "health": health,
        "ack": ack,
        "capabilities": sorted(capabilities),
        "checks": checks,
        "log_path": log_path,
        "request_path": request_path,
        "log_size_before_tokens": log_size,
        "native_token_generated": False,
    }


PROBE_SPECS = (
    ProbeSpec("control_state", ("probe_control_state.py",)),
    ProbeSpec("alliance_state", ("probe_alliance_state.py",)),
    ProbeSpec("diplomats", ("probe_diplomat_state.py",)),
    ProbeSpec("war_state", ("probe_war_pair.py",)),
)


def _discover_probe(spec: ProbeSpec) -> Path:
    # These are the four reviewed, build-specific probes.  Do not silently
    # substitute a generic or unknown CLI: a missing exact probe is unknown.
    candidate = ROOT / "work" / spec.candidates[0]
    if candidate.is_file():
        return candidate
    raise ValidationStop("READONLY_PROBE_NOT_FOUND", f"{spec.name}: {candidate}", "probe")


def _contains_read_error(value: Any) -> bool:
    if isinstance(value, dict):
        if "read_error" in value:
            return True
        return any(_contains_read_error(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_read_error(child) for child in value)
    return False


def _snapshot_completeness(kind: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Require bounded containers to be complete before comparing them."""

    checks: dict[str, bool] = {}
    if kind == "control_state":
        checks["date_present"] = isinstance(snapshot.get("date_raw"), int) \
            and not isinstance(snapshot.get("date_raw"), bool)
        checks["player_slot_present"] = isinstance(snapshot.get("player_slot"), int) \
            and not isinstance(snapshot.get("player_slot"), bool)
        return {"complete": all(checks.values()), "checks": checks}
    countries = snapshot.get("countries")
    checks["countries_list"] = isinstance(countries, list) and bool(countries)
    if not checks["countries_list"]:
        return {"complete": False, "checks": checks}
    if kind == "alliance_state":
        checks["queue_truncated_false"] = all(
            isinstance(item, dict) and item.get("queue_truncated") is False
            for item in countries
        )
        checks["no_read_error"] = not _contains_read_error(snapshot)
    elif kind == "diplomats":
        checks["queue_truncated_false"] = all(
            isinstance(item, dict) and item.get("ai_queue_truncated") is False
            for item in countries
        )
        checks["no_diplomacy_vector_overflow"] = all(
            isinstance(item, dict)
            and item.get("diplomacy_vector_invalid_or_exceeds_256") is not True
            for item in countries
        )
        checks["no_read_error"] = not _contains_read_error(snapshot)
    elif kind == "war_state":
        checks["pairs_are_lists"] = all(
            isinstance(item, dict) and isinstance(item.get("pairs"), list)
            for item in countries
        )
        checks["no_read_error"] = not _contains_read_error(snapshot)
    else:
        checks["known_probe_kind"] = False
    return {"complete": all(checks.values()), "checks": checks}


def _run_probe(spec: ProbeSpec, pid: int, destination: Path) -> dict[str, Any]:
    script = _discover_probe(spec)
    try:
        python = get_value("EU4_PYTHON")
    except Exception as error:
        raise ValidationStop("EU4_PYTHON_UNCONFIGURED", str(error), "probe") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    argv = [python, "-B", str(script), "--pid", str(pid), "--output", str(destination)]
    try:
        completed = subprocess.run(argv, check=True, timeout=PROBE_TIMEOUT_SECONDS,
                                   capture_output=True, text=True)
        snapshot = json.loads(destination.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired as error:
        raise ValidationStop("READONLY_PROBE_TIMEOUT", spec.name, "probe", unknown=True) from error
    except (subprocess.CalledProcessError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        raise ValidationStop("READONLY_PROBE_FAILED", f"{spec.name}: {detail[-2048:]}", "probe") from error
    if not isinstance(snapshot, dict) or snapshot.get("read_only") is not True:
        raise ValidationStop("READONLY_PROBE_NOT_DECLARED", spec.name, "probe")
    completeness = _snapshot_completeness(spec.name, snapshot)
    return {
        "status": "ok",
        "name": spec.name,
        "script": str(script),
        "argv": argv,
        "stdout_tail": completed.stdout[-2048:],
        "snapshot_path": str(destination),
        "snapshot": snapshot,
        "snapshot_completeness": completeness,
    }


def _run_baseline_probes(ctx: dict[str, Any], output: Path, expected_date_raw: int) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for spec in PROBE_SPECS:
        snapshots[spec.name] = _run_probe(
            spec,
            int(ctx["record"]["pid"]),
            output / "probes" / "before" / f"{spec.name}.json",
        )
    checks: dict[str, bool] = {}
    alliance = snapshots["alliance_state"]["snapshot"]
    diplomats = snapshots["diplomats"]["snapshot"]
    wars = snapshots["war_state"]["snapshot"]
    control = snapshots["control_state"]["snapshot"]
    for kind, entry in snapshots.items():
        checks[f"{kind}_snapshot_complete"] = entry.get("snapshot_completeness", {}).get("complete") is True
    checks["control_date_matches"] = control.get("date_raw") == expected_date_raw
    checks["control_player_slot_is_por"] = control.get("player_slot") == 189
    checks["control_is_paused"] = control.get("paused_flag") == 1
    checks["alliance_date_matches"] = alliance.get("date_raw") == expected_date_raw
    checks["alliance_player_is_por"] = alliance.get("player") == "POR"
    diplomat_countries = {item.get("tag") for item in diplomats.get("countries", []) if isinstance(item, dict)}
    checks["diplomat_tags_include_fra_eng_por"] = {"FRA", "ENG", "POR"}.issubset(diplomat_countries)
    checks["diplomat_date_matches"] = diplomats.get("current_raw_date") == expected_date_raw
    checks["war_date_matches"] = wars.get("current_raw_date") == expected_date_raw
    war_countries = {item.get("slot") for item in wars.get("countries", []) if isinstance(item, dict)}
    checks["war_probe_has_fra_eng_slots"] = war_countries == {122, 46}
    # These fields are the actual bounded queue/association payloads used in
    # the before/after comparison; their absence would make a no-delta claim
    # impossible.
    checks["alliance_actions_present"] = all(isinstance(item.get("actions"), list)
                                              for item in alliance.get("countries", []) if isinstance(item, dict))
    checks["diplomat_queues_present"] = all(isinstance(item.get("ai_queue"), list)
                                             and isinstance(item.get("diplomacy_entries"), list)
                                             for item in diplomats.get("countries", []) if isinstance(item, dict))
    checks["diplomat_resource_fields_valid"] = all(
        (
            isinstance(item.get("available_diplomat_count"), int)
            and not isinstance(item.get("available_diplomat_count"), bool)
            and 0 <= item["available_diplomat_count"] <= 256
        )
        if item.get("diplomacy_vector_invalid_or_exceeds_256") is not True
        else item.get("available_diplomat_count") is None
        for item in diplomats.get("countries", []) if isinstance(item, dict)
    )
    checks["war_pairs_present"] = all(isinstance(item.get("pairs"), list)
                                       for item in wars.get("countries", []) if isinstance(item, dict))
    alliance_countries = {item.get("country") for item in alliance.get("countries", []) if isinstance(item, dict)}
    checks["alliance_tags_include_fra_eng_por"] = {"FRA", "ENG", "POR"}.issubset(alliance_countries)
    if not all(checks.values()):
        raise ValidationStop("BASELINE_SNAPSHOT_MISMATCH", json.dumps(checks, ensure_ascii=False), "before_probe")
    return {"probes": snapshots, "checks": checks}


def _stable_summary(kind: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Remove addresses and volatile counters before comparing snapshots."""

    if kind == "alliance_state":
        countries = []
        for country in snapshot.get("countries", []):
            if not isinstance(country, dict):
                continue
            actions = []
            for action in country.get("actions", []):
                if not isinstance(action, dict):
                    continue
                actions.append({key: action.get(key) for key in (
                    "identification", "action_id", "native_action_id", "discriminator",
                    "variant_raw", "actor_field", "recipient_field", "state_raw",
                    "date_field_28", "date_field_2c", "complete")})
            countries.append({"country": country.get("country"),
                              "actions": actions,
                              "queue_truncated": country.get("queue_truncated"),
                              "country_handle_raw": country.get("handle", country.get("candidate_handle"))})
        return {"date_raw": snapshot.get("date_raw"), "player": snapshot.get("player"),
                "countries": countries}
    if kind == "diplomats":
        countries = []
        for country in snapshot.get("countries", []):
            if not isinstance(country, dict):
                continue
            queue = []
            for item in country.get("ai_queue", []):
                if not isinstance(item, dict):
                    continue
                queue.append({key: item.get(key) for key in (
                    "vtable_rva", "is_peace_action", "raw_28", "state", "raw_30", "preview_flag",
                    "raw_actor_10", "raw_recipient_20", "actor", "recipient")})
            entries = []
            for entry in country.get("diplomacy_entries", []):
                if not isinstance(entry, dict):
                    continue
                entries.append({key: entry.get(key) for key in (
                    "raw_id_44", "active_raw_18", "raw_action_type_a8", "raw_20",
                    "raw_24", "raw_2c", "raw_actor_80", "raw_recipient_88",
                    "actor", "recipient", "record_vtable_rva")})
            countries.append({"tag": country.get("tag"),
                              "country_handle_raw": country.get("handle"),
                              "ai_queue": queue,
                              "diplomacy_entries": entries,
                              "diplomacy_control_raw_14": country.get("diplomacy_control_raw_14"),
                              "ai_queue_truncated": country.get("ai_queue_truncated"),
                              "diplomacy_vector_invalid_or_exceeds_256": country.get(
                                  "diplomacy_vector_invalid_or_exceeds_256", False),
                              "available_diplomat_count": country.get("available_diplomat_count")})
        return {"current_raw_date": snapshot.get("current_raw_date"), "countries": countries}
    if kind == "war_state":
        countries = []
        for country in snapshot.get("countries", []):
            if not isinstance(country, dict):
                continue
            pairs = [{"slot": pair.get("slot")} for pair in country.get("pairs", [])
                     if isinstance(pair, dict)]
            countries.append({"slot": country.get("slot"), "pairs": pairs,
                              "pair_at_war": country.get("pair_at_war")})
        return {"current_raw_date": snapshot.get("current_raw_date"),
                "both_pair_at_peace": snapshot.get("both_pair_at_peace"),
                "countries": countries}
    if kind == "control_state":
        return {"date_raw": snapshot.get("date_raw"),
                "player_slot": snapshot.get("player_slot"),
                "paused_flag": snapshot.get("paused_flag")}
    raise ValueError(f"unknown probe kind {kind!r}")


def _find_query_error(value: Any) -> str | None:
    if isinstance(value, dict):
        error_code = value.get("error_code")
        if isinstance(error_code, str) and error_code.startswith("QUERY_"):
            return error_code
        for child in value.values():
            found = _find_query_error(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_query_error(child)
            if found:
                return found
    return None


def _require_positive_inspection(label: str, result: Any,
                                 expected_date_raw: int) -> None:
    """Require an actual native inspection for every semantic case.

    This is the r11-compatible baseline.  It deliberately does not infer UI
    visibility or complete legality from the read-only queue probes.
    """

    if not isinstance(result, dict):
        raise ValidationStop("POSITIVE_INSPECTION_INCOMPLETE", f"{label}: result is not an object",
                             "semantic", unknown=True)
    query_error = _find_query_error(result)
    if query_error:
        raise ValidationStop("POSITIVE_INSPECTION_NATIVE_ERROR",
                             f"{label}: {query_error}", "semantic", unknown=True)
    session = result.get("session")
    components = result.get("native_rule_components")
    checks = {
        "session_ready": isinstance(session, dict) and session.get("status") == "ready",
        "session_date_matches": isinstance(session, dict) and session.get("date_raw") == expected_date_raw,
        "partial_native_rules": isinstance(result.get("interface_support"), dict)
            and result["interface_support"].get("query") == "partial_native_rules",
        "native_rule_components_present": isinstance(components, dict),
        "specific_validity_query_called": isinstance(components, dict)
            and components.get("specific_validity_query_called") is True,
    }
    if not all(checks.values()):
        raise ValidationStop("POSITIVE_INSPECTION_INCOMPLETE",
                             f"{label}: {json.dumps(checks, ensure_ascii=False)}",
                             "semantic", unknown=True)


def _ui_field(result: dict[str, Any], name: str) -> tuple[Any, bool]:
    """Return a native UI coverage field without guessing its location.

    The r12 adapter publishes these fields with ``native_rule_components``.
    The small fallback to a dedicated ``ui_coverage`` object or the result
    root keeps the validator tolerant of the reviewed JSON-lines envelope,
    while still requiring all four fields once any marker is present.
    """

    components = result.get("native_rule_components")
    coverage = result.get("ui_coverage")
    for source in (components, coverage, result):
        if isinstance(source, dict) and name in source:
            return source[name], True
    return None, False


def _has_ui_coverage(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return any(_ui_field(result, name)[1] for name in UI_COVERAGE_FIELDS)


def _acceptance(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    value = result.get("acceptance")
    return value if isinstance(value, dict) else None


def _has_r13_extensions(result: Any) -> bool:
    """Detect the reviewed r13 fields without treating r12 ``unknown`` as a result."""

    acceptance = _acceptance(result)
    if isinstance(acceptance, dict) and any(
        key in acceptance for key in (
            "prediction_basis", "native_would_accept", "actual_response_verified",
        )
    ):
        return True
    # Resource output is also new in r13.  Its presence must not silently
    # downgrade a report to the r12 unknown-prediction contract.
    return isinstance(result, dict) and "resources" in result


def _require_r13_resources(label: str, result: Any) -> None:
    """Require the native diplomat context to remain an explicitly read-only resource."""

    resources = result.get("resources") if isinstance(result, dict) else None
    diplomats = resources.get("diplomats") if isinstance(resources, dict) else None
    count = diplomats.get("available_count") if isinstance(diplomats, dict) else None
    checks = {
        "resources_object": isinstance(resources, dict),
        "diplomats_object": isinstance(diplomats, dict),
        "native_requirement_bool": isinstance(diplomats, dict)
            and isinstance(diplomats.get("native_requirement"), bool),
        "available_count_bounded": isinstance(count, int) and not isinstance(count, bool)
            and 0 <= count <= 256,
        "availability_verified": isinstance(diplomats, dict)
            and diplomats.get("availability_verified") is True,
        "allocation_not_claimed": isinstance(diplomats, dict)
            and diplomats.get("allocation_verified") is False,
        "resource_source_native": isinstance(diplomats, dict)
            and diplomats.get("source") == "native_rule",
        "resource_incomplete_until_allocation": isinstance(diplomats, dict)
            and diplomats.get("complete") is False,
    }
    if not all(checks.values()):
        raise ValidationStop(
            "R13_RESOURCE_FIELDS_INCOMPLETE",
            f"{label}: {json.dumps(checks, ensure_ascii=False, sort_keys=True)}",
            "semantic", unknown=True,
        )


def _require_r13_native_acceptance(label: str, result: Any,
                                   expected_response: str) -> None:
    """Require a native current acceptance check, never a claimed response."""

    acceptance = _acceptance(result)
    components = result.get("native_rule_components") if isinstance(result, dict) else None
    expected_bool = expected_response == "accept"
    checks = {
        "acceptance_object": isinstance(acceptance, dict),
        "prediction_available": isinstance(acceptance, dict)
            and acceptance.get("prediction_available") is True,
        "predicted_response": isinstance(acceptance, dict)
            and acceptance.get("predicted_response") == expected_response,
        "prediction_basis": isinstance(acceptance, dict)
            and acceptance.get("prediction_basis") == "native_current_acceptance_check",
        "native_would_accept_bool": isinstance(acceptance, dict)
            and isinstance(acceptance.get("native_would_accept"), bool),
        "native_would_accept_matches": isinstance(acceptance, dict)
            and acceptance.get("native_would_accept") is expected_bool,
        "actual_response_not_verified": isinstance(acceptance, dict)
            and acceptance.get("actual_response_verified") is False,
        "acceptance_still_incomplete": isinstance(acceptance, dict)
            and acceptance.get("complete") is False,
        "scale_still_unverified": isinstance(acceptance, dict)
            and acceptance.get("scale_verified") is False,
        "native_total_integer": isinstance(acceptance, dict)
            and isinstance(acceptance.get("native_total"), int)
            and not isinstance(acceptance.get("native_total"), bool),
        "native_threshold_integer": isinstance(acceptance, dict)
            and isinstance(acceptance.get("native_threshold"), int)
            and not isinstance(acceptance.get("native_threshold"), bool),
        "component_gate_matches": isinstance(components, dict)
            and components.get("acceptance_gate") is expected_bool,
    }
    if not all(checks.values()):
        raise ValidationStop(
            "R13_ACCEPTANCE_PREDICATE_MISMATCH",
            f"{label}: {json.dumps(checks, ensure_ascii=False, sort_keys=True)}",
            "semantic", unknown=True,
        )


def _require_no_ai_prediction(label: str, result: Any) -> None:
    """Ensure a player-controlled or cancel action exposes no AI prediction."""

    acceptance = _acceptance(result)
    components = result.get("native_rule_components") if isinstance(result, dict) else None
    checks = {
        "acceptance_object": isinstance(acceptance, dict),
        "prediction_unavailable": isinstance(acceptance, dict)
            and acceptance.get("prediction_available") is False,
        "prediction_is_unknown_or_not_applicable": isinstance(acceptance, dict)
            and acceptance.get("predicted_response") in ("unknown", "not_applicable"),
        "no_prediction_basis": isinstance(acceptance, dict)
            and acceptance.get("prediction_basis") is None,
        "no_native_would_accept": isinstance(acceptance, dict)
            and acceptance.get("native_would_accept") is None,
        "actual_response_not_verified": isinstance(acceptance, dict)
            and acceptance.get("actual_response_verified") is not True,
        "no_acceptance_gate": not isinstance(components, dict)
            or "acceptance_gate" not in components,
    }
    if not all(checks.values()):
        raise ValidationStop(
            "R13_UNEXPECTED_AI_PREDICTION",
            f"{label}: {json.dumps(checks, ensure_ascii=False, sort_keys=True)}",
            "semantic", unknown=True,
        )


def _require_ui_covered_inspection(label: str, result: Any,
                                   expected_date_raw: int,
                                   expected: dict[str, Any]) -> None:
    """Require the reviewed r12 UI selector and legality semantics.

    The native visibility bool is included in the effective gate check so a
    hidden Offer/Cancel cannot be reported as legally available merely because
    its executor validity happened to be true.  Acceptance remains a separate
    incomplete result: readable reason names/values do not establish scale or
    a final AI response.
    """

    _require_positive_inspection(label, result, expected_date_raw)
    checks: dict[str, bool] = {}

    values: dict[str, Any] = {}
    for name in UI_COVERAGE_FIELDS:
        value, present = _ui_field(result, name)
        values[name] = value
        checks[f"{name}_present"] = present
    checks["ui_selection_checked"] = values["ui_selection_checked"] is True
    checks["ui_enabled_gate_checked"] = values["ui_enabled_gate_checked"] is True
    checks["full_rules_complete"] = values["full_rules_complete"] is True
    checks["native_visibility_bool"] = isinstance(values["native_visibility"], bool)
    checks["native_visibility_matches_expected"] = (
        values["native_visibility"] == expected["native_visibility"]
    )

    # reasons_complete is expected to remain false in r12: the selector and
    # gate coverage is complete, while localized reason completeness is not.
    reasons_complete, reasons_present = _ui_field(result, "reasons_complete")
    checks["reasons_not_claimed_complete"] = not reasons_present or reasons_complete is not True

    visibility = result.get("visibility")
    checks["visibility_object"] = isinstance(visibility, dict)
    checks["visibility_status"] = isinstance(visibility, dict) \
        and visibility.get("status") == expected["visibility"]
    checks["visibility_complete"] = isinstance(visibility, dict) \
        and visibility.get("complete") is True

    legality = result.get("legality")
    checks["legality_object"] = isinstance(legality, dict)
    checks["legality_status"] = isinstance(legality, dict) \
        and legality.get("status") == expected["legality"]
    checks["legality_complete"] = isinstance(legality, dict) \
        and legality.get("complete") is True

    # All actual rule gates must be booleans.  Optional UI-enabled fields are
    # included if the adapter publishes their value; the *_checked field above
    # is only a coverage marker and is never treated as the value itself.
    gate_values: list[Any] = [values["native_visibility"]]
    for name in ("common_action_gate", "initiation_gate", "executor_validity"):
        value, present = _ui_field(result, name)
        checks[f"{name}_bool"] = present and isinstance(value, bool)
        gate_values.append(value)
    for name in ("ui_enabled_gate", "ui_enabled"):
        value, present = _ui_field(result, name)
        if present:
            checks[f"{name}_bool"] = isinstance(value, bool)
            gate_values.append(value)
    if all(isinstance(value, bool) for value in gate_values):
        derived_legality = "available" if all(gate_values) else "unavailable"
        checks["legality_matches_all_gates"] = derived_legality == expected["legality"]
    else:
        checks["legality_matches_all_gates"] = False

    acceptance = result.get("acceptance")
    checks["acceptance_object"] = isinstance(acceptance, dict)
    if result.get("action_id") == "dissolve_alliance":
        # Dissolve has no acceptance score or response prediction.  The
        # adapter marks that applicability explicitly, and this is complete
        # once it has also proved that no clauses/total were produced.
        checks["acceptance_not_applicable"] = (
            isinstance(acceptance, dict)
            and acceptance.get("applicability") == "not_applicable"
        )
        checks["acceptance_complete"] = (
            isinstance(acceptance, dict)
            and acceptance.get("complete") is True
        )
        checks["acceptance_prediction_not_applicable"] = (
            isinstance(acceptance, dict)
            and acceptance.get("predicted_response") == "not_applicable"
        )
        checks["acceptance_items_empty"] = (
            isinstance(acceptance, dict)
            and acceptance.get("items") == []
        )
        checks["acceptance_native_total_none"] = (
            isinstance(acceptance, dict)
            and acceptance.get("native_total") is None
        )
        _, acceptance_gate_present = _ui_field(result, "acceptance_gate")
        checks["acceptance_gate_absent"] = not acceptance_gate_present
        checks["prediction_unavailable"] = (
            isinstance(acceptance, dict)
            and acceptance.get("prediction_available") is False
        )
        checks["prediction_basis_absent"] = (
            isinstance(acceptance, dict)
            and acceptance.get("prediction_basis") is None
        )
        checks["native_would_accept_absent"] = (
            isinstance(acceptance, dict)
            and acceptance.get("native_would_accept") is None
        )
        checks["actual_response_not_verified"] = (
            isinstance(acceptance, dict)
            and acceptance.get("actual_response_verified") is not True
        )
    else:
        if _has_r13_extensions(result) and isinstance(acceptance, dict) \
                and "prediction_basis" in acceptance:
            # r13's predicate is a native current check.  It remains a
            # prediction and must explicitly carry actual_response_verified=false.
            checks["acceptance_incomplete"] = acceptance.get("complete") is False
            checks["acceptance_scale_unverified"] = acceptance.get("scale_verified") is False
            checks["acceptance_prediction_native_check"] = (
                acceptance.get("prediction_basis") == "native_current_acceptance_check"
                and acceptance.get("predicted_response") in ("accept", "reject")
                and isinstance(acceptance.get("native_would_accept"), bool)
                and acceptance.get("actual_response_verified") is False
            )
        else:
            # r12 Offer acceptance remains intentionally incomplete: reason
            # values do not establish a verified scale or final AI response.
            checks["acceptance_incomplete"] = (
                isinstance(acceptance, dict)
                and acceptance.get("complete") is not True
            )
            checks["acceptance_scale_unverified"] = (
                isinstance(acceptance, dict)
                and acceptance.get("scale_verified") is False
            )
            checks["acceptance_prediction_not_final"] = (
                isinstance(acceptance, dict)
                and acceptance.get("predicted_response") in ("unknown", "not_applicable")
            )

    if not all(checks.values()):
        raise ValidationStop(
            "UI_COVERAGE_SEMANTICS_MISMATCH",
            f"{label}: {json.dumps(checks, ensure_ascii=False, sort_keys=True)}",
            "semantic", unknown=True,
        )


def _require_r13_contract(inspections: dict[str, Any], expected_date_raw: int) -> None:
    """Validate the r13 acceptance/resource additions without calling execution."""

    for action_id, recipient in R13_ACCEPTANCE_EXPECTATIONS:
        label = f"{action_id}:FRA->{recipient}"
        result = inspections.get(label)
        if result is None:
            raise ValidationStop("R13_REQUIRED_PAIR_MISSING", label, "semantic", unknown=True)
        _require_positive_inspection(label, result, expected_date_raw)
        _require_r13_resources(label, result)
        _require_r13_native_acceptance(
            label, result, R13_ACCEPTANCE_EXPECTATIONS[(action_id, recipient)],
        )

    # Every r13 inspection must carry the bounded resource context, including
    # the player-controlled and dissolve cases where prediction is suppressed.
    for label, result in inspections.items():
        _require_r13_resources(label, result)

    for action_id, recipient in R13_NO_PREDICTION_PAIRS:
        label = f"{action_id}:FRA->{recipient}"
        result = inspections.get(label)
        if result is None:
            raise ValidationStop("R13_REQUIRED_PAIR_MISSING", label, "semantic", unknown=True)
        _require_no_ai_prediction(label, result)


def _call_semantic(label: str, function: Callable[[], Any]) -> Any:
    try:
        return function()
    except Exception as error:
        # A failed read is unknown to the operator; it is never a rule result.
        return {"status": "unknown", "error_code": "SEMANTIC_CALL_FAILED",
                "operation": label, "error_type": type(error).__name__, "error": str(error)}


def _run_semantic_api(ctx: dict[str, Any], output: Path) -> dict[str, Any]:
    session: ObserverSession = ctx["session"]
    journal_path = output / "diplomacy.sqlite3"
    with DurableJournal(journal_path, ctx["session"].experiment_id,
                        ctx["session"].session_id, global_request_ids=True) as journal:
        api = DiplomacyTools(journal, session)
        listing = _call_semantic(
            "list_diplomatic_actions",
            lambda: api.list_diplomatic_actions(actor="FRA", recipient="SAV"),
        )
        list_count = len(listing.get("actions", [])) if isinstance(listing, dict) \
            and isinstance(listing.get("actions"), list) else None
        if list_count != 39:
            raise ValidationStop("ACTION_CATALOG_COUNT_MISMATCH", f"expected 39, got {list_count}", "semantic")

        inspections: dict[str, Any] = {}
        for action_id, recipient in BASE_ALLIANCE_INSPECTION_PAIRS:
            label = f"{action_id}:FRA->{recipient}"
            result = _call_semantic(
                label,
                lambda action_id=action_id, recipient=recipient:
                    api.inspect_diplomatic_action(action_id, "FRA", recipient, phase="initiate"),
            )
            inspections[label] = result
            _require_positive_inspection(label, result, ctx["health"]["date_raw"])

        ui_coverage_flags = [_has_ui_coverage(result) for result in inspections.values()]
        r13_mode = any(_has_r13_extensions(result) for result in inspections.values())
        ui_coverage_mode = "legacy_unknown"
        if r13_mode and not any(ui_coverage_flags):
            raise ValidationStop(
                "R13_UI_COVERAGE_MISSING",
                "r13 resource/predicate fields appeared without the reviewed UI coverage fields",
                "semantic", unknown=True,
            )
        if any(ui_coverage_flags):
            # A partial UI rollout is unknown, not a reason to silently mix
            # r11 semantics with r12 fields or omit a required pair.
            if not all(ui_coverage_flags):
                raise ValidationStop(
                    "UI_COVERAGE_PARTIAL",
                    "UI coverage fields appeared for only part of the base inspection set",
                    "semantic", unknown=True,
                )
            ui_coverage_mode = "native_selector"
            for action_id, recipient in BASE_ALLIANCE_INSPECTION_PAIRS:
                label = f"{action_id}:FRA->{recipient}"
                _require_ui_covered_inspection(
                    label, inspections[label], ctx["health"]["date_raw"],
                    UI_COVERED_EXPECTATIONS[(action_id, recipient)],
                )
            for action_id, recipient in UI_COVERED_EXTRA_PAIRS:
                label = f"{action_id}:FRA->{recipient}"
                result = _call_semantic(
                    label,
                    lambda action_id=action_id, recipient=recipient:
                        api.inspect_diplomatic_action(action_id, "FRA", recipient, phase="initiate"),
                )
                inspections[label] = result
                _require_ui_covered_inspection(
                    label, result, ctx["health"]["date_raw"],
                    UI_COVERED_EXPECTATIONS[(action_id, recipient)],
                )
            if r13_mode:
                # LIT is intentionally queried only after the r13 marker is
                # observed.  r12 has no final prediction and must remain a
                # valid legacy run without manufacturing a new query.
                action_id, recipient = "offer_alliance", "LIT"
                label = f"{action_id}:FRA->{recipient}"
                result = _call_semantic(
                    label,
                    lambda: api.inspect_diplomatic_action(
                        action_id, "FRA", recipient, phase="initiate"),
                )
                inspections[label] = result
                _require_ui_covered_inspection(
                    label, result, ctx["health"]["date_raw"],
                    UI_COVERED_EXPECTATIONS[(action_id, recipient)],
                )
                _require_r13_contract(inspections, ctx["health"]["date_raw"])

        # The implementation is deliberately unimplemented.  One request ID
        # proves the durable idempotency and conflict semantics without ever
        # reaching native transport.
        request_id = "validation_exec_" + uuid.uuid4().hex[:24]
        first = _call_semantic(
            "execute_first",
            lambda: api.execute_diplomatic_action(request_id, "offer_alliance", "FRA", "ENG"),
        )
        retry = _call_semantic(
            "execute_retry_same_payload",
            lambda: api.execute_diplomatic_action(request_id, "offer_alliance", "FRA", "ENG"),
        )
        conflict = _call_semantic(
            "execute_retry_different_payload",
            lambda: api.execute_diplomatic_action(request_id, "offer_alliance", "FRA", "SAV"),
        )
        persistent = _call_semantic(
            "get_diplomatic_result",
            lambda: api.get_diplomatic_result(request_id),
        )
        execute_checks = {
            "first_submitted_false": isinstance(first, dict) and first.get("submitted") is False,
            "first_status_invalidated": isinstance(first, dict) and first.get("status") == "invalidated",
            "first_game_outcome_unknown": isinstance(first, dict) and first.get("game_outcome") == "unknown",
            "retry_submitted_false": isinstance(retry, dict) and retry.get("submitted") is False,
            "retry_idempotent": isinstance(retry, dict) and retry.get("idempotent") is True,
            "conflict_submitted_false": isinstance(conflict, dict) and conflict.get("submitted") is False,
            "different_payload_conflict": isinstance(conflict, dict)
                and conflict.get("status") == "conflict"
                and isinstance(conflict.get("reason"), dict)
                and conflict["reason"].get("code") == "REQUEST_ID_PAYLOAD_CONFLICT",
            "persistent_status_invalidated": isinstance(persistent, dict)
                and persistent.get("status") == "invalidated",
            "persistent_submitted_false": isinstance(persistent, dict)
                and persistent.get("submitted") is False,
            "invalidated_not_ai_rejection": all(
                not (isinstance(item, dict) and item.get("status") == "rejected")
                for item in (first, retry, conflict, persistent)
            ),
        }
        if not all(execute_checks.values()):
            raise ValidationStop("EXECUTION_SEMANTICS_MISMATCH", json.dumps(execute_checks, ensure_ascii=False), "semantic")
        result = {
            "list": {"count": list_count, "result": listing},
            "inspections": inspections,
            "ui_coverage": {
                "mode": ui_coverage_mode,
                "base_pair_count": len(BASE_ALLIANCE_INSPECTION_PAIRS),
                "extra_pair_count": len(UI_COVERED_EXTRA_PAIRS) if ui_coverage_mode == "native_selector" else 0,
                "r13_native_acceptance": r13_mode,
                "r13_acceptance_pair_count": len(R13_ACCEPTANCE_EXPECTATIONS) if r13_mode else 0,
                "legacy_unknown_supported": ui_coverage_mode == "legacy_unknown",
            },
            "execute": {
                "request_id": request_id,
                "first": first,
                "retry_same_payload": retry,
                "retry_different_payload": conflict,
                "persistent": persistent,
                "checks": execute_checks,
                "interpretation": {
                    "submitted": False,
                    "business_result": "unknown",
                    "invalidated_is_bridge_unimplemented": True,
                    "ai_rejection_claimed": False,
                },
            },
            "journal_path": str(journal_path),
            "journal_request_count": len(journal.list_requests()),
        }
    _write_json(output / "semantic-results.json", result)
    return result


def _filetime_now() -> int:
    return time.time_ns() // 100 + FILETIME_UNIX_EPOCH


def _wire(creation: int, query_id: str, action: str, actor: str,
          recipient: str, date_raw: int, expiry: int) -> str:
    # alliance-query.inc parses creation as hexadecimal and expiry as decimal.
    return f"EU4DIP_QUERY1 {creation:x} {query_id} {action} {actor} {recipient} {date_raw} {expiry}\n"


def _build_native_cases(ctx: dict[str, Any], expected_date_raw: int) -> list[NativeCase]:
    record = ctx["record"]
    creation = int(record["creation_filetime"])
    now = _filetime_now()
    # Keep normal requests below the native 60-second upper bound while
    # leaving enough margin for the complete negative-case sequence.  A query
    # that actually reaches this expiry is still observed as unknown.
    future = now + 59 * FILETIME_TICKS_PER_SECOND
    nonce = uuid.uuid4().hex[:12]
    duplicate_id = f"vaq_duplicate_{nonce}"
    return [
        NativeCase("creation_wrong", f"vaq_creation_{nonce}",
                   _wire(creation + 1, f"vaq_creation_{nonce}", "offer_alliance", "FRA", "SAV", expected_date_raw, future),
                   EXPECTED_NATIVE_REASON_CODES["creation_wrong"]),
        NativeCase("expiry_past", f"vaq_expired_{nonce}",
                   _wire(creation, f"vaq_expired_{nonce}", "offer_alliance", "FRA", "SAV", expected_date_raw, now - FILETIME_TICKS_PER_SECOND),
                   EXPECTED_NATIVE_REASON_CODES["expiry_past"]),
        NativeCase("expiry_over_60_seconds", f"vaq_long_{nonce}",
                   _wire(creation, f"vaq_long_{nonce}", "offer_alliance", "FRA", "SAV", expected_date_raw,
                         now + 120 * FILETIME_TICKS_PER_SECOND),
                   EXPECTED_NATIVE_REASON_CODES["expiry_over_60_seconds"]),
        NativeCase("date_wrong", f"vaq_date_{nonce}",
                   _wire(creation, f"vaq_date_{nonce}", "offer_alliance", "FRA", "SAV", expected_date_raw + 1, future),
                   EXPECTED_NATIVE_REASON_CODES["date_wrong"]),
        NativeCase("duplicate_id_seed", duplicate_id,
                   _wire(creation, duplicate_id, "offer_alliance", "FRA", "SAV", expected_date_raw + 1, future),
                   EXPECTED_NATIVE_REASON_CODES["duplicate_id_seed"], setup_only=True),
        NativeCase("duplicate_id", duplicate_id,
                   _wire(creation, duplicate_id, "offer_alliance", "FRA", "SAV", expected_date_raw + 1, future),
                   EXPECTED_NATIVE_REASON_CODES["duplicate_id"]),
        NativeCase("unsupported_action", f"vaq_action_{nonce}",
                   _wire(creation, f"vaq_action_{nonce}", "unsupported_action", "FRA", "SAV", expected_date_raw, future),
                   EXPECTED_NATIVE_REASON_CODES["unsupported_action"]),
        NativeCase("zzz_country", f"vaq_zzz_{nonce}",
                   _wire(creation, f"vaq_zzz_{nonce}", "offer_alliance", "ZZZ", "SAV", expected_date_raw, future),
                   EXPECTED_NATIVE_REASON_CODES["zzz_country"]),
        NativeCase("malformed_wire", "invalid", "EU4DIP_QUERY1 malformed\n",
                   EXPECTED_NATIVE_REASON_CODES["malformed_wire"]),
    ]


def _append_exclusive(path: Path, text: str) -> None:
    """Create the fixed observer request without replacing an existing file."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
            stream.write(text)
    except BaseException:
        # fdopen owns the descriptor after entering the with block.  If
        # fdopen itself failed, close it before propagating.
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _read_matching_events(log_path: Path, cursor: int, session_id: str,
                          query_id: str, deadline: float) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        try:
            size = log_path.stat().st_size
        except OSError as error:
            return {"status": "unknown", "reason_code": "QUERY_LOG_UNAVAILABLE",
                    "error": str(error), "events": events, "cursor": cursor}
        if size < cursor:
            return {"status": "unknown", "reason_code": "QUERY_LOG_TRUNCATED",
                    "events": events, "cursor": cursor}
        try:
            with log_path.open("rb") as stream:
                stream.seek(cursor)
                chunk = stream.read(min(MAX_LOG_CHUNK, max(0, size - cursor)))
        except OSError as error:
            return {"status": "unknown", "reason_code": "QUERY_LOG_UNAVAILABLE",
                    "error": str(error), "events": events, "cursor": cursor}
        newline = chunk.rfind(b"\n")
        if newline >= 0:
            complete = chunk[:newline + 1]
            line_cursor = cursor
            for raw_line in complete.splitlines(keepends=True):
                line_start = line_cursor
                line_cursor += len(raw_line)
                try:
                    event = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("session_id") != session_id or event.get("query_id") != query_id:
                    continue
                captured = {"event": event, "offset_start": line_start,
                            "offset_end": line_cursor}
                events.append(captured)
                name = event.get("event")
                if name == "native_alliance_inspection_failed":
                    return {"status": "matched", "events": events, "event": captured,
                            "cursor": line_cursor}
                if name == "native_alliance_inspection":
                    return {"status": "unexpected_result", "events": events,
                            "event": captured, "cursor": line_cursor}
            cursor = line_cursor
        time.sleep(0.02)
    return {"status": "unknown", "reason_code": "QUERY_OBSERVATION_TIMEOUT",
            "events": events, "cursor": cursor}


def _run_native_case(ctx: dict[str, Any], output: Path, case: NativeCase,
                     timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    session: ObserverSession = ctx["session"]
    request_path: Path = ctx["request_path"]
    log_path: Path = ctx["log_path"]
    case_dir = output / "native" / case.name
    case_dir.mkdir(parents=True, exist_ok=False)
    wire_path = case_dir / "typed-wire.txt"
    _write_text(wire_path, case.wire, encoding="ascii")
    try:
        start_offset = log_path.stat().st_size
    except OSError as error:
        result = {"status": "unknown", "case": case.name, "query_id": case.query_id,
                  "expected_reason_code": case.expected_reason_code,
                  "reason_code": "QUERY_LOG_UNAVAILABLE", "error": str(error),
                  "wire_path": str(wire_path), "setup_only": case.setup_only}
        _write_json(case_dir / "result.json", result)
        return result
    if request_path.exists():
        result = {"status": "unknown", "case": case.name, "query_id": case.query_id,
                  "expected_reason_code": case.expected_reason_code,
                  "reason_code": "QUERY_CHANNEL_BUSY", "wire_path": str(wire_path),
                  "log_offset_start": start_offset, "setup_only": case.setup_only}
        _write_json(case_dir / "result.json", result)
        return result
    try:
        _append_exclusive(request_path, case.wire)
    except FileExistsError:
        # Another operator owns the channel; never overwrite or remove it.
        result = {"status": "unknown", "case": case.name, "query_id": case.query_id,
                  "expected_reason_code": case.expected_reason_code,
                  "reason_code": "QUERY_CHANNEL_BUSY", "wire_path": str(wire_path),
                  "log_offset_start": start_offset, "setup_only": case.setup_only}
        _write_json(case_dir / "result.json", result)
        return result
    except OSError as error:
        result = {"status": "unknown", "case": case.name, "query_id": case.query_id,
                  "expected_reason_code": case.expected_reason_code,
                  "reason_code": "QUERY_REQUEST_WRITE_FAILED", "error": str(error),
                  "wire_path": str(wire_path), "log_offset_start": start_offset,
                  "setup_only": case.setup_only}
        _write_json(case_dir / "result.json", result)
        return result

    ctx["native_token_generated"] = True
    observed = _read_matching_events(
        log_path, start_offset, session.session_id, case.query_id,
        time.monotonic() + timeout_seconds,
    )
    result: dict[str, Any] = {
        "case": case.name,
        "query_id": case.query_id,
        "expected_reason_code": case.expected_reason_code,
        "wire_path": str(wire_path),
        "request_path": str(request_path),
        "log_path": str(log_path),
        "log_offset_start": start_offset,
        "setup_only": case.setup_only,
        "request_consumed": not request_path.exists(),
        **observed,
    }
    if observed.get("status") == "matched":
        event = observed.get("event", {}).get("event", {})
        reason_code = event.get("reason_code") if isinstance(event, dict) else None
        result["reason_code"] = reason_code
        result["reason_match"] = reason_code == case.expected_reason_code
        result["submitted"] = event.get("submitted") if isinstance(event, dict) else None
        result["submitted_false"] = result["submitted"] is False
        if not result["reason_match"] or not result["submitted_false"]:
            result["status"] = "unknown"
            result["stop_reason"] = ("QUERY_REASON_CODE_MISMATCH"
                                      if not result["reason_match"]
                                      else "QUERY_FAILURE_SUBMITTED_UNEXPECTEDLY")
    else:
        # Timeout, truncation and any unexpected result are not a rejection.
        result["status"] = "unknown"
        result["stop_reason"] = observed.get("reason_code", observed.get("status"))
    _write_json(case_dir / "result.json", result)
    return result


def _run_native_negative_cases(ctx: dict[str, Any], output: Path,
                               expected_date_raw: int) -> dict[str, Any]:
    cases = _build_native_cases(ctx, expected_date_raw)
    results: list[dict[str, Any]] = []
    stopped = False
    stop_reason = None
    for case in cases:
        result = _run_native_case(ctx, output, case)
        results.append(result)
        if result.get("status") != "matched" or result.get("reason_match") is not True:
            stopped = True
            stop_reason = result.get("stop_reason", result.get("reason_code"))
            break
    summary = {
        "protocol_source": str(ROOT / "work/native/alliance-query.inc"),
        "expected_reason_codes": EXPECTED_NATIVE_REASON_CODES,
        "cases": results,
        "all_observed_reason_codes_match": bool(results) and all(
            item.get("status") == "matched" and item.get("reason_match") is True
            and item.get("submitted_false") is True
            for item in results
        ) and len(results) == len(cases),
        "stopped_on_unknown_or_mismatch": stopped,
        "stop_reason": stop_reason,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "interpretation": {
            "failure_events_are_protocol_guards": True,
            "failure_events_are_ai_rejections": False,
            "unobserved_request_is_unknown": True,
            "request_is_never_replayed_after_timeout": True,
        },
    }
    _write_json(output / "native" / "summary.json", summary)
    return summary


def _run_after_probes(ctx: dict[str, Any], output: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for spec in PROBE_SPECS:
        try:
            entry = _run_probe(
                spec,
                int(ctx["record"]["pid"]),
                output / "probes" / "after" / f"{spec.name}.json",
            )
            if entry.get("snapshot_completeness", {}).get("complete") is not True:
                entry["status"] = "unknown"
                entry["error_code"] = "SNAPSHOT_INCOMPLETE"
            result[spec.name] = entry
        except ValidationStop as error:
            result[spec.name] = {"status": "unknown", "error_code": error.code,
                                 "error": error.message, "stage": error.stage}
    return result


def _business_submission_evidence(ctx: dict[str, Any], semantic: dict[str, Any],
                                  native: dict[str, Any], before: dict[str, Any],
                                  after: dict[str, Any]) -> dict[str, Any]:
    before_stable = {kind: _stable_summary(kind, item["snapshot"])
                     for kind, item in before["probes"].items()}
    after_stable = {
        kind: _stable_summary(kind, item["snapshot"])
        for kind, item in after.items()
        if isinstance(item, dict) and item.get("status") == "ok" and "snapshot" in item
    }
    stable_equal = set(before_stable) == set(after_stable) and before_stable == after_stable
    before_resource = {
        item.get("tag"): {
            "available_diplomat_count": item.get("available_diplomat_count"),
            "diplomacy_control_raw_14": item.get("diplomacy_control_raw_14"),
            "diplomacy_vector_invalid_or_exceeds_256": item.get(
                "diplomacy_vector_invalid_or_exceeds_256", False),
        }
        for item in before.get("probes", {}).get("diplomats", {}).get("snapshot", {}).get("countries", [])
        if isinstance(item, dict)
    }
    after_resource = {
        item.get("tag"): {
            "available_diplomat_count": item.get("available_diplomat_count"),
            "diplomacy_control_raw_14": item.get("diplomacy_control_raw_14"),
            "diplomacy_vector_invalid_or_exceeds_256": item.get(
                "diplomacy_vector_invalid_or_exceeds_256", False),
        }
        for item in after.get("diplomats", {}).get("snapshot", {}).get("countries", [])
        if isinstance(item, dict)
    }
    resource_equal = before_resource == after_resource
    execute = semantic.get("execute", {})
    execute_unsubmitted = all(
        isinstance(execute.get(name), dict) and execute[name].get("submitted") is False
        for name in ("first", "retry_same_payload", "retry_different_payload", "persistent")
    )
    native_failures_unsubmitted = all(
        item.get("status") == "matched" and item.get("submitted") is False
        for item in native.get("cases", []) if item.get("status") == "matched"
    )
    ack_locked = ctx["ack"].get("native_execution_enabled") is False
    return {
        "observer_native_execution_enabled": ctx["ack"].get("native_execution_enabled"),
        "observer_all_commands_forwarded": ctx["ack"].get("all_commands_forwarded"),
        "execute_results_submitted_false": execute_unsubmitted,
        "native_failure_events_submitted_false": native_failures_unsubmitted,
        "stable_before_after_equal": stable_equal,
        "diplomat_resource_before_after_equal": resource_equal,
        "diplomat_resources_before": before_resource,
        "diplomat_resources_after": after_resource,
        "stable_before": before_stable,
        "stable_after": after_stable,
        "volatile_fields_ignored": [
            "object", "pointer", "handle", "record", "war", "pid",
            "ai_queue_count_raw", "event_sequence", "log_offsets",
        ],
        "frame_query_read_only_source_contract": True,
        "mutable_tls_or_ring_cache_is_not_world_mutation": True,
        "proves_no_business_submission": bool(
            ack_locked and execute_unsubmitted and native_failures_unsubmitted
            and stable_equal and resource_equal
        ),
        "claim_scope": "The validator never calls a business executor; an unstable or missing after snapshot remains unknown.",
    }


def run_validation(installation: Path, expected_date_raw: int,
                   output_root: Path | None = None) -> tuple[Path, dict[str, Any], int]:
    output_root = output_root or ROOT / "work" / "runtime"
    output = _unique_output_directory(output_root)
    report: dict[str, Any] = {
        "validator": "validate_alliance_queries.py",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "installation": str(installation.resolve()),
        "expected_date_raw": expected_date_raw,
        "output_directory": str(output),
        "native_token_generated": False,
        "status": "running",
    }
    _write_json(output / "validation-report.json", report)
    ctx: dict[str, Any] | None = None
    try:
        ctx = _preflight(installation.resolve(), expected_date_raw, output)
        report["preflight"] = {
            "checks": ctx["checks"],
            "health": ctx["health"],
            "ack": ctx["ack"],
            "capabilities": ctx["capabilities"],
            "actual_identity": ctx["actual_identity"],
        }
        _write_json(output / "preflight.json", report["preflight"])

        before = _run_baseline_probes(ctx, output, expected_date_raw)
        _write_json(output / "probes" / "before-summary.json", before["checks"])
        report["before_probes"] = before
        semantic = _run_semantic_api(ctx, output)
        native = _run_native_negative_cases(ctx, output, expected_date_raw)
        if native.get("stopped_on_unknown_or_mismatch"):
            report.update({"status": "unknown", "stop_stage": "native_protocol",
                           "stop_reason": native.get("stop_reason")})
            report["native_token_generated"] = bool(ctx.get("native_token_generated"))
            report["semantic"] = semantic
            report["native"] = native
            _write_json(output / "validation-report.json", report)
            return output, report, 3
        after = _run_after_probes(ctx, output)
        report["semantic"] = semantic
        report["native"] = native
        report["before_probes"] = before
        report["after_probes"] = after
        report["business_submission_evidence"] = _business_submission_evidence(
            ctx, semantic, native, before, after,
        )
        report["native_token_generated"] = bool(ctx.get("native_token_generated"))
        report["status"] = "passed" if report["business_submission_evidence"]["proves_no_business_submission"] else "unknown"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_json(output / "validation-report.json", report)
        return output, report, 0 if report["status"] == "passed" else 3
    except ValidationStop as error:
        report.update({"status": "unknown" if error.unknown else "stopped",
                       "stop_stage": error.stage, "stop_code": error.code,
                       "stop_message": error.message,
                       "native_token_generated": bool(ctx and ctx.get("native_token_generated")),
                       "finished_at_utc": datetime.now(timezone.utc).isoformat()})
        _write_json(output / "validation-report.json", report)
        return output, report, 3
    except Exception as error:  # preserve an operator artifact even for unexpected local failures
        report.update({"status": "stopped", "stop_stage": "unexpected",
                       "stop_code": type(error).__name__, "stop_message": str(error),
                       "native_token_generated": bool(ctx and ctx.get("native_token_generated")),
                       "finished_at_utc": datetime.now(timezone.utc).isoformat()})
        _write_json(output / "validation-report.json", report)
        return output, report, 3


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path,
                        help="operator installation.json for the already loaded observer")
    parser.add_argument("--expected-date-raw", required=True, type=int,
                        help="raw date read by the observer health event")
    parser.add_argument("--output-root", type=Path, default=None,
                        help="optional parent for the unique validation-* directory")
    args = parser.parse_args(list(argv) if argv is not None else None)
    output, report, code = run_validation(args.installation, args.expected_date_raw, args.output_root)
    # Keep stdout free of wires, PIDs and native diagnostics; the operator can
    # open validation-report.json for the detailed evidence.
    print(json.dumps({"output_directory": str(output), "status": report.get("status"),
                      "exit_code": code, "native_token_generated": report.get("native_token_generated", False)},
                     ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
