"""Bounded offline validation of the passive alliance wrapper protocol trace.

The protocol observer only records native snapshots.  This validator keeps the
origin/flags/sequence fields and object addresses visible, but never turns a
matching sequence, a serializer callback, or a command entry into authority
or a business result.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_PROBE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_EVENTS = 250_000
MAX_RETAINED = 8_192
MAX_HASH_FILE_BYTES = 64 * 1024 * 1024
HASH_BLOCK_BYTES = 1024 * 1024
MAX_ISSUES = 256

EXPECTED_MANIFEST_VERSION = 10
EXPECTED_R17C_DLL_SHA256 = (
    "e4c14dadfcfe13f967e3d6ca220b0a81e27680af15cad221f1055cd3c8256c87"
)
PROTOCOL_SCHEMA_NAME = "alliance-protocol-observer.inc"
FIELD_SELECTORS = {0xC7, 0xCC, 0xDB, 0x293D}
FIELD_SELECTOR_NAMES = {value: hex(value) for value in FIELD_SELECTORS}
REQUIRED_ACKS = {
    "alliance_lifecycle_observer_installed",
    "alliance_serializer_observer_installed",
    "alliance_field_reader_observer_installed",
    "alliance_wrapper_protocol_observer_installed",
    "diplomacy_observer_installed",
}
PROTOCOL_EVENTS = {
    "native_wrapper_field_read_begin",
    "native_alliance_wrapper_clone",
    "native_alliance_lifecycle",
    "native_alliance_command_entry_observed",
}
LIFECYCLE_KINDS = {
    "clone", "wrapper", "serialization_begin", "destructor",
    "destructor_return",
}
SHAPE_FIELDS = (
    "addr", "readable", "matched", "handles_canonical", "tracked",
    "vtable_rva", "discriminator", "actor10", "mirror18", "recipient20",
    "date28", "date2c", "envoy30", "state34", "variant38", "proposal3c",
)
PAYLOAD_FIELDS = (
    "vtable_rva", "discriminator", "actor10", "mirror18", "recipient20",
    "date28", "date2c", "envoy30", "state34", "variant38", "proposal3c",
)
DROP_EVENT_NAMES = {
    "native_wrapper_protocol_dropped",
    "native_alliance_lifecycle_drop",
    "observation_incomplete",
    "alliance_rules_observation_incomplete",
}


class InputError(ValueError):
    """An input outside the bounded offline contract."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int(value: Any, *, minimum: int | None = None,
         maximum: int | None = None) -> int | None:
    if _is_int(value):
        result = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            result = int(text, 0)
        except ValueError:
            try:
                result = int(text, 10)
            except ValueError:
                return None
    else:
        return None
    if minimum is not None and result < minimum:
        return None
    if maximum is not None and result > maximum:
        return None
    return result


def _address(value: Any) -> int | None:
    return _int(value, minimum=0x10000)


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _load_json(path: Path, limit: int = MAX_METADATA_BYTES) -> Any:
    if not path.is_file():
        raise InputError(f"missing JSON: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InputError(f"cannot stat {path}: {exc}") from exc
    if size > limit:
        raise InputError(f"JSON exceeds bound ({size}>{limit}): {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid JSON {path}: {exc}") from exc


def _sha256(path: Path | None) -> tuple[str | None, str | None]:
    if path is None or not path.is_file():
        return None, "missing"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f"stat:{exc}"
    if size > MAX_HASH_FILE_BYTES:
        return None, f"too_large:{size}"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                block = stream.read(HASH_BLOCK_BYTES)
                if not block:
                    break
                digest.update(block)
    except OSError as exc:
        return None, f"read:{exc}"
    return digest.hexdigest(), None


def _artifact(manifest_path: Path, declared: Any) -> Path | None:
    if not isinstance(declared, str) or not declared:
        return None
    # Runtime manifests can contain another checkout's absolute path.  The
    # supplied experiment directory is the only offline artifact root.
    return manifest_path.parent / Path(declared).name


def _add_issue(issues: list[dict[str, Any]], code: str,
               **details: Any) -> None:
    if len(issues) < MAX_ISSUES:
        item: dict[str, Any] = {"code": code}
        item.update(details)
        issues.append(item)


def _protocol_key(value: Mapping[str, Any] | None, *, lifecycle: bool = False,
                  wrapper: bool = False) -> tuple[int, int, int] | None:
    if not isinstance(value, Mapping):
        return None
    if lifecycle:
        origin = value.get("origin48")
        sequence = value.get("seq4c")
        flags = value.get("rawflag4a")
    elif wrapper:
        origin = value.get("origin")
        sequence = value.get("protocol_sequence")
        flags = value.get("protocol_flags")
    else:
        origin = value.get("origin")
        sequence = value.get("protocol_sequence")
        flags = value.get("protocol_flags")
    origin = _int(origin, minimum=0, maximum=0xFFFF)
    sequence = _int(sequence, minimum=0, maximum=0xFFFFFFFF)
    flags = _int(flags, minimum=0, maximum=0xFF)
    if origin is None or sequence is None or flags is None:
        return None
    return origin, sequence, flags


def _shape(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _payload(wrapper: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(wrapper, Mapping):
        return None
    value = wrapper.get("payload")
    return dict(value) if isinstance(value, Mapping) else None


def _payload_key(value: Mapping[str, Any] | None) -> tuple[Any, ...] | None:
    if not isinstance(value, Mapping):
        return None
    values: list[Any] = []
    for key in PAYLOAD_FIELDS:
        parsed = value.get(key)
        if key in {"vtable_rva"}:
            parsed = _int(parsed)
        elif key in {"discriminator", "actor10", "mirror18", "recipient20",
                     "date28", "date2c", "envoy30", "state34", "variant38",
                     "proposal3c"}:
            parsed = _int(parsed)
        if parsed is None:
            return None
        values.append(parsed)
    return tuple(values)


def _payload_differences(left: Mapping[str, Any] | None,
                         right: Mapping[str, Any] | None) -> list[str]:
    differences: list[str] = []
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return list(PAYLOAD_FIELDS)
    for key in PAYLOAD_FIELDS:
        left_value = _int(left.get(key))
        right_value = _int(right.get(key))
        if left_value is None or right_value is None or left_value != right_value:
            differences.append(key)
    return differences


def _canonical_shape(shape: Mapping[str, Any] | None) -> bool:
    if not isinstance(shape, Mapping):
        return False
    return (
        shape.get("readable") is True
        and shape.get("matched") is True
        and shape.get("handles_canonical") is True
        and _payload_key(shape) is not None
    )


def _compact_shape(shape: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(shape, Mapping):
        return {"readable": False, "missing": list(PAYLOAD_FIELDS)}
    compact = {key: shape.get(key) for key in SHAPE_FIELDS if key in shape}
    missing = [key for key in PAYLOAD_FIELDS if key not in shape]
    if missing:
        compact["missing"] = missing
    return compact


def _wrapper_ref(wrapper: Mapping[str, Any] | None) -> int | None:
    return _address(wrapper.get("addr")) if isinstance(wrapper, Mapping) else None


def _wrapper_action(wrapper: Mapping[str, Any] | None) -> int | None:
    return _address(wrapper.get("action")) if isinstance(wrapper, Mapping) else None


def _source_payload(wrapper: Mapping[str, Any] | None) -> dict[str, Any] | None:
    value = _payload(wrapper)
    if value is None:
        return None
    return value


def _callback(event: Mapping[str, Any]) -> int | None:
    name = event.get("event")
    if name == "native_wrapper_field_read_begin":
        return _int(event.get("callback_sequence"), minimum=1)
    if name == "native_alliance_wrapper_clone":
        return _int(event.get("callback_sequence"), minimum=1)
    if name == "native_alliance_lifecycle":
        return _int(event.get("sequence"), minimum=1)
    if name == "native_alliance_command_entry_observed":
        return _int(event.get("callback_sequence"), minimum=1)
    return None


def _begin_callback(event: Mapping[str, Any]) -> int | None:
    return _int(event.get("begin_callback_sequence"), minimum=1)


def _event_name(event: Mapping[str, Any]) -> str | None:
    value = event.get("event")
    return value if isinstance(value, str) else None


def _event_session(event: Mapping[str, Any]) -> str | None:
    value = event.get("session_id")
    return value if isinstance(value, str) and value else None


def _hex16(value: Any) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    text = value.strip().lower()
    if len(text) != 32:
        return text[:64], False
    try:
        bytes.fromhex(text)
    except ValueError:
        return text[:64], False
    return text, True


def _phase(offset: int, observation: Mapping[str, Any] | None,
           probe_size: int) -> str:
    if not isinstance(observation, Mapping):
        return "observation_report_unknown"
    start = _int(observation.get("log_start_offset"), minimum=0)
    end = _int(observation.get("log_end_offset"), minimum=0)
    if start is None or end is None or start > end or end > probe_size:
        return "observation_report_invalid"
    if offset < start:
        return "before_observation_slice"
    if offset < end:
        return "observed_35day_slice"
    return "after_observation_slice"


def _find_observation_report(installation_path: Path) -> Path | None:
    candidates: list[Path] = []
    try:
        for child in installation_path.parent.iterdir():
            if child.is_dir():
                candidate = child / "observation-report.json"
                if candidate.is_file():
                    candidates.append(candidate)
    except OSError:
        return None
    return sorted(candidates)[0] if candidates else None


def _static_schema(schema_path: Path, issues: list[dict[str, Any]]) -> dict[str, Any]:
    if not schema_path.is_file():
        _add_issue(issues, "PROTOCOL_SCHEMA_MISSING", path=str(schema_path))
        return {"path": str(schema_path), "sha256": None, "verified": False}
    try:
        size = schema_path.stat().st_size
        if size > MAX_SOURCE_BYTES:
            _add_issue(issues, "PROTOCOL_SCHEMA_TOO_LARGE", bytes=size)
            return {"path": str(schema_path), "sha256": None, "verified": False}
        text = schema_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _add_issue(issues, "PROTOCOL_SCHEMA_UNREADABLE", reason=str(exc))
        return {"path": str(schema_path), "sha256": None, "verified": False}
    digest, error = _sha256(schema_path)
    markers = {
        # The C++ source contains escaped JSON format strings, so event names
        # are checked independently of quote/backslash spelling.
        "field_event": "native_wrapper_field_read_begin" in text,
        "clone_event": "native_alliance_wrapper_clone" in text,
        "drop_event": "native_wrapper_protocol_dropped" in text,
        "origin": "origin48" in text and "protocol_flags" in text,
        "selector_fields": all(f"field_id" in text for _ in FIELD_SELECTORS),
    }
    verified = error is None and all(markers.values())
    if not verified:
        _add_issue(issues, "PROTOCOL_SCHEMA_MARKERS_INCOMPLETE", markers=markers)
    return {
        "path": str(schema_path), "size": size, "sha256": digest,
        "markers": markers, "verified": verified,
    }


def _validate_identity(installation: Any, manifest: Any, manifest_path: Path,
                       issues: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(installation, Mapping):
        raise InputError("installation JSON must be an object")
    if not isinstance(manifest, Mapping):
        raise InputError("build manifest JSON must be an object")
    session = installation.get("session_id")
    if not isinstance(session, str) or not session:
        raise InputError("installation.session_id is required")
    manifest_session = manifest.get("session_id")
    if isinstance(manifest_session, str) and manifest_session != session:
        _add_issue(issues, "MANIFEST_SESSION_MISMATCH")
    version = _int(manifest.get("version"), minimum=0)
    if version != EXPECTED_MANIFEST_VERSION:
        _add_issue(issues, "BUILD_VERSION_MISMATCH", expected=EXPECTED_MANIFEST_VERSION,
                   actual=version)
    if manifest.get("compiled") is not True:
        _add_issue(issues, "BUILD_NOT_MARKED_COMPILED")

    install_dll = installation.get("dll_sha256")
    manifest_dll = manifest.get("dll_sha256")
    if not isinstance(install_dll, str) or not isinstance(manifest_dll, str):
        _add_issue(issues, "DLL_HASH_DECLARATION_MISSING")
    elif install_dll.lower() != manifest_dll.lower():
        _add_issue(issues, "DLL_HASH_DECLARATION_MISMATCH")
    if isinstance(manifest_dll, str) and manifest_dll.lower() != EXPECTED_R17C_DLL_SHA256:
        _add_issue(issues, "R17C_DLL_HASH_UNEXPECTED", actual=manifest_dll)

    game_install = installation.get("game_sha256")
    game_manifest = manifest.get("game_sha256")
    if isinstance(game_install, str) and isinstance(game_manifest, str) \
            and game_install.lower() != game_manifest.lower():
        _add_issue(issues, "GAME_HASH_DECLARATION_MISMATCH")

    source_reports: list[dict[str, Any]] = []
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        _add_issue(issues, "MANIFEST_SOURCES_MISSING")
        sources = []
    for item in sources:
        if not isinstance(item, Mapping):
            _add_issue(issues, "SOURCE_ENTRY_INVALID")
            continue
        path = _artifact(manifest_path, item.get("name"))
        actual, error = _sha256(path)
        expected = item.get("sha256")
        verified = isinstance(expected, str) and actual == expected.lower()
        source_reports.append({
            "name": item.get("name"), "path": str(path) if path else None,
            "expected": expected, "actual": actual, "verified": verified,
        })
        if error is not None:
            _add_issue(issues, "SOURCE_HASH_UNVERIFIED", name=item.get("name"), reason=error)
        elif not verified:
            _add_issue(issues, "SOURCE_HASH_MISMATCH", name=item.get("name"),
                       expected=expected, actual=actual)

    dll_path = _artifact(manifest_path, manifest.get("dll"))
    dll_actual, dll_error = _sha256(dll_path)
    dll_verified = isinstance(manifest_dll, str) and dll_actual == manifest_dll.lower()
    if dll_error is not None:
        _add_issue(issues, "DLL_HASH_UNVERIFIED", reason=dll_error)
    elif not dll_verified:
        _add_issue(issues, "DLL_HASH_MISMATCH", expected=manifest_dll, actual=dll_actual)

    modules = installation.get("modules_after_install")
    module_reports: list[dict[str, Any]] = []
    if not isinstance(modules, list):
        _add_issue(issues, "INSTALLATION_MODULES_MISSING")
        modules = []
    for item in modules:
        if not isinstance(item, Mapping):
            continue
        path = _artifact(manifest_path, item.get("path"))
        actual, error = _sha256(path)
        expected = item.get("sha256")
        verified = isinstance(expected, str) and actual == expected.lower()
        module_reports.append({
            "name": item.get("name"), "path": str(path) if path else None,
            "expected": expected, "actual": actual, "verified": verified,
        })
        if error is not None:
            _add_issue(issues, "MODULE_HASH_UNVERIFIED", name=item.get("name"), reason=error)
        elif not verified:
            _add_issue(issues, "MODULE_HASH_MISMATCH", name=item.get("name"),
                       expected=expected, actual=actual)

    return {
        "session_id": session,
        "pid": installation.get("pid"),
        "creation_filetime": installation.get("creation_filetime"),
        "experiment_id": manifest.get("experiment_id", installation.get("experiment_id")),
        "manifest_version": version,
        "manifest_compiled": manifest.get("compiled"),
        "installation_runtime_verified": installation.get("runtime_verified"),
        "game_sha256": game_install,
        "manifest_game_sha256": game_manifest,
        "dll_sha256": manifest_dll,
        "installation_dll_sha256": install_dll,
        "dll_hash": {"path": str(dll_path) if dll_path else None,
                      "actual": dll_actual, "verified": dll_verified},
        "source_hashes": source_reports,
        "module_hashes": module_reports,
        "installation_returncode": installation.get("installation_returncode"),
    }


def _stage_common(event: Mapping[str, Any], line: int, start: int,
                  end: int, phase: str) -> dict[str, Any]:
    return {
        "line": line, "byte_start": start, "byte_end": end, "phase": phase,
        "session_id": _event_session(event),
        "callback_sequence": _callback(event),
        "thread": _int(event.get("thread"), minimum=0),
    }


def _wrapper_report(wrapper: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "address": wrapper.get("addr") if isinstance(wrapper, Mapping) else None,
        "identity": wrapper.get("identity") if isinstance(wrapper, Mapping) else None,
        "readable": wrapper.get("readable") if isinstance(wrapper, Mapping) else None,
        "origin": wrapper.get("origin") if isinstance(wrapper, Mapping) else None,
        "protocol_flags": wrapper.get("protocol_flags") if isinstance(wrapper, Mapping) else None,
        "protocol_sequence": wrapper.get("protocol_sequence") if isinstance(wrapper, Mapping) else None,
        "action": wrapper.get("action") if isinstance(wrapper, Mapping) else None,
        "protocol_key": list(_protocol_key(wrapper, wrapper=True))
        if _protocol_key(wrapper, wrapper=True) is not None else None,
        "payload": _compact_shape(_payload(wrapper)),
        "payload_canonical": _canonical_shape(_payload(wrapper)),
    }


def _field_report(event: Mapping[str, Any], common: Mapping[str, Any],
                  issues: list[dict[str, Any]]) -> dict[str, Any]:
    field_id = _int(event.get("field_id"), minimum=0, maximum=0xFFFFFFFF)
    input_hex, input_valid = _hex16(event.get("input16_hex"))
    source = _shape(event.get("source"))
    source_key = _protocol_key(source, wrapper=True)
    selector_known = field_id in FIELD_SELECTORS if field_id is not None else False
    native_return = _bool(event.get("native_return_observed"))
    if field_id is None:
        pass
    if event.get("input16_readable") is True and not input_valid:
        _add_issue(issues, "WRAPPER_FIELD_INPUT16_INVALID", line=common["line"])
    if native_return is not False:
        _add_issue(issues, "WRAPPER_FIELD_NATIVE_RETURN_NOT_FALSE", line=common["line"])
    record = dict(common)
    record.update({
        "field_id": field_id,
        "field_hex": hex(field_id) if field_id is not None else None,
        "selector_known": selector_known,
        "selector_name": FIELD_SELECTOR_NAMES.get(field_id),
        "context": event.get("context"),
        "caller_return_rva": event.get("caller_return_rva"),
        "input16_readable": event.get("input16_readable") is True,
        "input16_hex": input_hex,
        "input16_valid_hex": input_valid,
        "context_word_readable": event.get("context_word_readable") is True,
        "native_forward_count": event.get("native_forward_count_by_hook_contract"),
        "native_forward_contract": event.get("native_forward_count_by_hook_contract") == 1,
        "native_return_observed": native_return,
        "source": _wrapper_report(source),
        "source_address": source.get("addr") if isinstance(source, Mapping) else None,
        "source_action": source.get("action") if isinstance(source, Mapping) else None,
        "source_protocol_key": list(source_key) if source_key is not None else None,
        # This is deliberately a pre-return snapshot.  It does not certify
        # that the original reader returned or that a native write succeeded.
        "snapshot_scope": "pre_return_local_snapshot",
        "native_return_claimed": False,
    })
    return record


def _serialization_report(event: Mapping[str, Any], common: Mapping[str, Any],
                          issues: list[dict[str, Any]]) -> dict[str, Any]:
    source = _shape(event.get("source"))
    key = _protocol_key(event, lifecycle=True)
    wrapper_address = _address(event.get("out_value"))
    wrapper_action = _address(event.get("wrapper_action"))
    record = dict(common)
    record.update({
        "kind": "serialization_begin",
        "source": _compact_shape(source),
        "source_address": source.get("addr") if isinstance(source, Mapping) else None,
        "source_payload": _compact_shape(source),
        "wrapper_address": hex(wrapper_address) if wrapper_address else event.get("out_value"),
        "wrapper_action": hex(wrapper_action) if wrapper_action else event.get("wrapper_action"),
        "wrapper_identity": event.get("wrapper_identity") is True,
        "wrapper_readable": event.get("wrapper_readable") is True,
        "origin48": event.get("origin48"),
        "seq4c": event.get("seq4c"),
        "rawflag4a": event.get("rawflag4a"),
        "protocol_key": list(key) if key is not None else None,
        "native_forward_contract": event.get("native_forward_count_by_hook_contract") == 1,
        "native_return_observed": _bool(event.get("native_return_observed")),
        "serialization_is_submission": False,
        "authority": False,
    })
    if key is None:
        _add_issue(issues, "SERIALIZATION_PROTOCOL_FIELDS_INCOMPLETE", line=common["line"])
    if record["native_return_observed"] is not False:
        _add_issue(issues, "SERIALIZATION_RETURN_CONTRACT_INVALID", line=common["line"])
    return record


def _clone_report(event: Mapping[str, Any], common: Mapping[str, Any],
                  issues: list[dict[str, Any]]) -> dict[str, Any]:
    source = _shape(event.get("source"))
    target = _shape(event.get("target"))
    begin = _begin_callback(event)
    end = _callback(event)
    source_key = _protocol_key(source, wrapper=True)
    target_key = _protocol_key(target, wrapper=True)
    record = dict(common)
    record.update({
        "begin_callback_sequence": begin,
        "end_callback_sequence": end,
        "source": _wrapper_report(source),
        "target": _wrapper_report(target),
        "source_address": source.get("addr") if isinstance(source, Mapping) else None,
        "target_address": target.get("addr") if isinstance(target, Mapping) else None,
        "source_action": source.get("action") if isinstance(source, Mapping) else None,
        "target_action": target.get("action") if isinstance(target, Mapping) else None,
        "source_protocol_key": list(source_key) if source_key is not None else None,
        "target_protocol_key": list(target_key) if target_key is not None else None,
        "origin_changed": bool(source_key is not None and target_key is not None
                                and source_key[0] != target_key[0]),
        "sequence_changed": bool(source_key is not None and target_key is not None
                                  and source_key[1] != target_key[1]),
        "flags_changed": bool(source_key is not None and target_key is not None
                               and source_key[2] != target_key[2]),
        "opaque_context": event.get("opaque_context"),
        "native_result": event.get("native_result"),
        "native_result_address": _address(event.get("native_result")),
        "native_forward_contract": event.get("native_forward_count_by_hook_contract") == 1,
        "native_return_observed": _bool(event.get("native_return_observed")),
        "submit_receipt": event.get("submit_receipt") is True,
        "authority": False,
    })
    if begin is None or end is None or begin > end:
        _add_issue(issues, "WRAPPER_CLONE_CALLBACK_RANGE_INVALID", line=common["line"])
    if record["native_return_observed"] is not True:
        _add_issue(issues, "WRAPPER_CLONE_RETURN_CONTRACT_INVALID", line=common["line"])
    return record


def _entry_report(event: Mapping[str, Any], common: Mapping[str, Any],
                  issues: list[dict[str, Any]]) -> dict[str, Any]:
    source = _shape(event.get("source"))
    key = _protocol_key(event)
    action = _address(event.get("action"))
    record = dict(common)
    record.update({
        "action": event.get("action"),
        "action_address": action,
        "command": event.get("command"),
        "command_address": _address(event.get("command")),
        "source": _compact_shape(source),
        "source_address": source.get("addr") if isinstance(source, Mapping) else None,
        "source_payload": _compact_shape(source),
        "protocol_key": list(key) if key is not None else None,
        "origin": event.get("origin"),
        "protocol_sequence": event.get("protocol_sequence"),
        "protocol_flags": event.get("protocol_flags"),
        "readable": event.get("readable") is True,
        "action_id": event.get("action_id"),
        "decision_country": None,
        "decision_country_verified": False,
        "business_result": "unknown",
        "authority": False,
    })
    if key is None:
        _add_issue(issues, "COMMAND_ENTRY_PROTOCOL_FIELDS_INCOMPLETE", line=common["line"])
    return record


def _same_key(left: Any, right: Any) -> bool:
    return isinstance(left, list) and isinstance(right, list) and left == right and len(left) == 3


def _same_sequence(left: Any, right: Any) -> bool:
    return (
        isinstance(left, list) and isinstance(right, list)
        and len(left) == 3 and len(right) == 3
        and left[1] == right[1]
    )


def _next_callback(records: list[dict[str, Any]], ordinal: int | None) -> dict[str, Any] | None:
    if ordinal is None:
        return None
    candidates = [item for item in records
                  if isinstance(item.get("callback_sequence"), int)
                  and item["callback_sequence"] > ordinal]
    return min(candidates, key=lambda item: item["callback_sequence"]) if candidates else None


def _correlate(fields: list[dict[str, Any]], clones: list[dict[str, Any]],
               serializations: list[dict[str, Any]], entries: list[dict[str, Any]],
               all_callbacks: list[dict[str, Any]],
               issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chains: list[dict[str, Any]] = []
    for serialization in sorted(serializations, key=lambda item: (item.get("callback_sequence") or 0, item["line"])):
        serial_ord = serialization.get("callback_sequence")
        serial_action = _address(serialization.get("wrapper_action"))
        serial_wrapper = _address(serialization.get("wrapper_address"))
        serial_key = serialization.get("protocol_key")
        candidates: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
        for field in fields:
            field_ord = field.get("callback_sequence")
            if not isinstance(serial_ord, int) or not isinstance(field_ord, int) or field_ord <= serial_ord:
                continue
            if serial_action is None or _address(field.get("source_action")) != serial_action:
                continue
            if serial_wrapper is not None and _address(field.get("source_address")) != serial_wrapper:
                continue
            for clone in clones:
                begin = clone.get("begin_callback_sequence")
                end = clone.get("end_callback_sequence")
                if not isinstance(begin, int) or not isinstance(end, int):
                    continue
                if not (field_ord < begin <= end):
                    continue
                if _address(clone.get("source_action")) != serial_action:
                    continue
                if _address(clone.get("source_address")) != _address(field.get("source_address")):
                    continue
                for entry in entries:
                    entry_ord = entry.get("callback_sequence")
                    if not isinstance(entry_ord, int) or entry_ord <= end:
                        continue
                    if _address(entry.get("action")) != _address(clone.get("target_action")):
                        continue
                    if _address(entry.get("command_address")) != _address(clone.get("target_address")):
                        continue
                    if clone.get("native_result_address") != _address(clone.get("target_address")):
                        continue
                    if _address(entry.get("source_address")) != _address(entry.get("action")):
                        continue
                    serial_payload = serialization.get("source_payload")
                    field_payload = field.get("source", {}).get("payload") if isinstance(field.get("source"), Mapping) else None
                    clone_payload = clone.get("target", {}).get("payload") if isinstance(clone.get("target"), Mapping) else None
                    entry_payload = entry.get("source_payload")
                    payload_diffs = {
                        "serialization_to_field": _payload_differences(serial_payload, field_payload),
                        "field_to_clone_source": _payload_differences(field_payload, clone.get("source", {}).get("payload") if isinstance(clone.get("source"), Mapping) else None),
                        "clone_target_to_entry": _payload_differences(clone_payload, entry_payload),
                    }
                    address_params_complete = all(value is not None for value in (
                        serial_action, serial_wrapper,
                        _address(field.get("source_address")),
                        _address(clone.get("source_address")),
                        _address(clone.get("target_address")),
                        _address(clone.get("target_action")),
                        _address(entry.get("action")),
                    ))
                    params_complete = bool(
                        address_params_complete
                        and serial_key is not None
                        and field.get("source_protocol_key") is not None
                        and clone.get("source_protocol_key") is not None
                        and clone.get("target_protocol_key") is not None
                        and entry.get("protocol_key") is not None
                        and field.get("input16_valid_hex") is True
                        and field.get("input16_readable") is True
                        and clone.get("native_forward_contract") is True
                        and clone.get("native_return_observed") is True
                        and serialization.get("native_forward_contract") is True
                        and serialization.get("native_return_observed") is False
                    )
                    keys = {
                        "serialization_to_field": _same_key(serial_key, field.get("source_protocol_key")),
                        "field_to_clone_source": _same_key(field.get("source_protocol_key"), clone.get("source_protocol_key")),
                        "clone_source_to_target": _same_key(clone.get("source_protocol_key"), clone.get("target_protocol_key")),
                        "clone_target_to_entry": _same_key(clone.get("target_protocol_key"), entry.get("protocol_key")),
                        "serialization_to_entry": _same_key(serial_key, entry.get("protocol_key")),
                    }
                    same_sequence_only = any(
                        _same_sequence(left, right) and not _same_key(left, right)
                        for left, right in (
                            (serial_key, field.get("source_protocol_key")),
                            (field.get("source_protocol_key"), clone.get("source_protocol_key")),
                            (clone.get("target_protocol_key"), entry.get("protocol_key")),
                            (serial_key, entry.get("protocol_key")),
                        )
                    )
                    protocol_continuity = params_complete and all(keys.values())
                    next_callback = _next_callback(all_callbacks, field_ord)
                    candidate = {
                        "record_id": f"serialization-line-{serialization['line']}-entry-line-{entry['line']}",
                        "serialization": serialization,
                        "field_read": field,
                        "wrapper_clone": clone,
                        "command_entry": entry,
                        "callback_order": {
                            "serialization": serial_ord, "field_read": field_ord,
                            "clone_begin": begin, "clone_end": end,
                            "command_entry": entry_ord,
                        },
                        "phase_order": {
                            "serialization": serialization.get("phase"),
                            "field_read": field.get("phase"),
                            "clone": clone.get("phase"),
                            "command_entry": entry.get("phase"),
                        },
                        "next_callback_after_field": {
                            "sequence": next_callback.get("callback_sequence") if next_callback else None,
                            "event": next_callback.get("event") if next_callback else None,
                            "snapshot_before_next_callback": next_callback is not None,
                        },
                        "addresses": {
                            "serialization_wrapper": serialization.get("wrapper_address"),
                            "serialization_action": serialization.get("wrapper_action"),
                            "field_wrapper": field.get("source_address"),
                            "field_action": field.get("source_action"),
                            "clone_source_wrapper": clone.get("source_address"),
                            "clone_target_wrapper": clone.get("target_address"),
                            "clone_target_action": clone.get("target_action"),
                            "entry_action": entry.get("action"),
                            "entry_source_action": entry.get("source_address"),
                        },
                        "protocol": {
                            "serialization_key": serial_key,
                            "field_source_key": field.get("source_protocol_key"),
                            "clone_source_key": clone.get("source_protocol_key"),
                            "clone_target_key": clone.get("target_protocol_key"),
                            "entry_key": entry.get("protocol_key"),
                            "full_key_matches": keys,
                            "same_sequence_only_candidate": same_sequence_only,
                            "clone_origin_changed": clone.get("source_protocol_key") is not None and clone.get("target_protocol_key") is not None and clone.get("source_protocol_key")[0] != clone.get("target_protocol_key")[0],
                            "clone_sequence_changed": clone.get("source_protocol_key") is not None and clone.get("target_protocol_key") is not None and clone.get("source_protocol_key")[1] != clone.get("target_protocol_key")[1],
                            "clone_flags_changed": clone.get("source_protocol_key") is not None and clone.get("target_protocol_key") is not None and clone.get("source_protocol_key")[2] != clone.get("target_protocol_key")[2],
                            "continuity_verified": protocol_continuity,
                        },
                        "payload": {
                            "params_complete": params_complete,
                            "differences": payload_diffs,
                            "all_payloads_canonical": all(
                                isinstance(item, Mapping) and item.get("payload_canonical") is True
                                for item in (serialization.get("source", {}), field.get("source", {}), clone.get("source", {}), clone.get("target", {}))
                            ),
                        },
                        "local_stage_chain_verified": params_complete,
                        "authority": False,
                        "business_result": "unknown",
                        "submit_verified": False,
                        "complete": False,
                        "incomplete_reasons": [],
                    }
                    if not params_complete:
                        candidate["incomplete_reasons"].append("STAGE_PARAMS_INCOMPLETE")
                    if not protocol_continuity:
                        candidate["incomplete_reasons"].append("PROTOCOL_KEY_CONTINUITY_UNVERIFIED")
                    if same_sequence_only:
                        candidate["incomplete_reasons"].append("SEQUENCE_ONLY_CANDIDATE_NOT_AUTHORIZATION")
                    if any(payload_diffs.values()):
                        candidate["incomplete_reasons"].append("PAYLOAD_LAYOUT_CHANGED_OR_UNPROVEN")
                    candidates.append(((entry_ord, int(protocol_continuity), int(params_complete), -field_ord), candidate))
        if candidates:
            chains.append(max(candidates, key=lambda item: item[0])[1])
        else:
            _add_issue(issues, "PROTOCOL_STAGE_CHAIN_NOT_FOUND", line=serialization.get("line"))
    return chains


def _correlate_protocol_stages(fields: list[dict[str, Any]],
                               clones: list[dict[str, Any]],
                               serializations: list[dict[str, Any]],
                               entries: list[dict[str, Any]],
                               all_callbacks: list[dict[str, Any]],
                               issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain every clone as an independent fact and match entries locally.

    The protocol clone hook has an explicit before/after object pair.  A
    command entry can therefore be associated with a clone when its action
    and complete payload match the clone target, even if the earlier
    serializer or wrapper-field callback was flushed by a different queue.
    Such a record is deliberately a partial stage chain until all stages and
    full protocol keys are present.  No sequence-only fallback is used.
    """
    sorted_clones = sorted(clones, key=lambda item: (
        item.get("begin_callback_sequence") or 0, item.get("line", 0)))
    sorted_entries = sorted(entries, key=lambda item: (
        item.get("callback_sequence") or 0, item.get("line", 0)))
    sorted_fields = sorted(fields, key=lambda item: (
        item.get("callback_sequence") or 0, item.get("line", 0)))
    sorted_serializations = sorted(serializations, key=lambda item: (
        item.get("callback_sequence") or 0, item.get("line", 0)))
    records: list[dict[str, Any]] = []
    used_entries: set[int] = set()

    def _strict_full_stage_candidate(clone: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
        begin = clone.get("begin_callback_sequence")
        end = clone.get("end_callback_sequence")
        source_address = _address(clone.get("source_address"))
        source_action = _address(clone.get("source_action"))
        if not isinstance(begin, int) or not isinstance(end, int):
            return None
        for serialization in sorted_serializations:
            serial_ord = serialization.get("callback_sequence")
            serial_wrapper = _address(serialization.get("wrapper_address"))
            serial_action = _address(serialization.get("wrapper_action"))
            if not isinstance(serial_ord, int) or not (serial_ord < begin):
                continue
            if serial_wrapper != source_address or serial_action != source_action:
                continue
            for field in sorted_fields:
                field_ord = field.get("callback_sequence")
                if not isinstance(field_ord, int) or not (serial_ord < field_ord < begin):
                    continue
                if _address(field.get("source_address")) != serial_wrapper:
                    continue
                if _address(field.get("source_action")) != serial_action:
                    continue
                if field.get("input16_valid_hex") is not True:
                    continue
                if field.get("source_protocol_key") is None:
                    continue
                return serialization, field, clone
        return None

    for clone in sorted_clones:
        begin = clone.get("begin_callback_sequence")
        end = clone.get("end_callback_sequence")
        target_action = _address(clone.get("target_action"))
        target_payload = clone.get("target", {}).get("payload") \
            if isinstance(clone.get("target"), Mapping) else None
        entry_candidates = [
            entry for entry in sorted_entries
            if isinstance(end, int)
            and isinstance(entry.get("callback_sequence"), int)
            and entry["callback_sequence"] > end
            and target_action is not None
            and _address(entry.get("action")) == target_action
            and _address(entry.get("command_address")) == _address(clone.get("target_address"))
            and _address(entry.get("source_address")) == _address(entry.get("action"))
            and not _payload_differences(target_payload, entry.get("source_payload"))
            and entry.get("line") not in used_entries
        ]
        entry = entry_candidates[0] if entry_candidates else None
        if entry is not None:
            used_entries.add(entry["line"])

        target_address = _address(clone.get("target_address"))
        native_result_address = _address(clone.get("native_result_address"))
        command_matches_target = bool(
            entry is not None
            and _address(entry.get("command_address")) is not None
            and target_address is not None
            and _address(entry.get("command_address")) == target_address
        )
        native_result_matches_target = bool(
            native_result_address is not None
            and target_address is not None
            and native_result_address == target_address
        )
        same_action_payload_entries = [
            candidate for candidate in sorted_entries
            if isinstance(end, int)
            and isinstance(candidate.get("callback_sequence"), int)
            and candidate["callback_sequence"] > end
            and target_action is not None
            and _address(candidate.get("action")) == target_action
            and _address(candidate.get("source_address")) == _address(candidate.get("action"))
            and not _payload_differences(target_payload, candidate.get("source_payload"))
            and candidate.get("line") not in used_entries
        ]

        full_stage = _strict_full_stage_candidate(clone)
        serialization = full_stage[0] if full_stage else None
        field = full_stage[1] if full_stage else None
        clone_source_key = clone.get("source_protocol_key")
        clone_target_key = clone.get("target_protocol_key")
        entry_key = entry.get("protocol_key") if entry else None
        serial_key = serialization.get("protocol_key") if serialization else None
        field_key = field.get("source_protocol_key") if field else None
        available_keys = [key for key in (serial_key, field_key,
                                          clone_source_key, clone_target_key,
                                          entry_key) if isinstance(key, list)]
        same_sequence_only = any(
            _same_sequence(left, right) and not _same_key(left, right)
            for index, left in enumerate(available_keys)
            for right in available_keys[index + 1:]
        )
        key_matches = {
            "serialization_to_field": _same_key(serial_key, field_key),
            "field_to_clone_source": _same_key(field_key, clone_source_key),
            "clone_source_to_target": _same_key(clone_source_key, clone_target_key),
            "clone_target_to_entry": _same_key(clone_target_key, entry_key),
            "serialization_to_entry": _same_key(serial_key, entry_key),
        }
        payload_differences = {
            "clone_target_to_entry": _payload_differences(
                target_payload, entry.get("source_payload") if entry else None),
        }
        params_complete = bool(
            entry is not None
            and clone.get("source_address") is not None
            and clone.get("target_address") is not None
            and target_action is not None
            and command_matches_target
            and native_result_matches_target
            and _canonical_shape(clone.get("source", {}).get("payload")
                                if isinstance(clone.get("source"), Mapping) else None)
            and _canonical_shape(clone.get("target", {}).get("payload")
                                 if isinstance(clone.get("target"), Mapping) else None)
            and entry.get("protocol_key") is not None
            and clone_source_key is not None
            and clone_target_key is not None
            and clone.get("native_forward_contract") is True
            and clone.get("native_return_observed") is True
            and entry.get("readable") is True
            and not payload_differences["clone_target_to_entry"]
        )
        protocol_continuity = bool(params_complete and all(key_matches.values()))
        next_callback = _next_callback(all_callbacks, field.get("callback_sequence")
                                       if field else begin)
        reasons: list[str] = []
        if entry is None:
            reasons.append("COMMAND_ENTRY_UNMATCHED")
            if same_action_payload_entries:
                reasons.append("COMMAND_WRAPPER_ADDRESS_UNMATCHED")
        elif not command_matches_target:
            reasons.append("COMMAND_WRAPPER_ADDRESS_UNMATCHED")
        if not native_result_matches_target:
            reasons.append("CLONE_NATIVE_RESULT_TARGET_UNVERIFIED")
        if serialization is None:
            reasons.append("SERIALIZATION_STAGE_UNMATCHED")
        if field is None:
            reasons.append("FIELD_READ_STAGE_UNMATCHED")
        if not params_complete:
            reasons.append("STAGE_PARAMS_INCOMPLETE")
        if not protocol_continuity:
            reasons.append("PROTOCOL_KEY_CONTINUITY_UNVERIFIED")
        if same_sequence_only:
            reasons.append("SEQUENCE_ONLY_CANDIDATE_NOT_AUTHORIZATION")
        if any(payload_differences.values()):
            reasons.append("PAYLOAD_LAYOUT_CHANGED_OR_UNPROVEN")
        records.append({
            "record_id": f"clone-line-{clone.get('line')}",
            "serialization": serialization,
            "field_read": field,
            "wrapper_clone": clone,
            "command_entry": entry,
            "callback_order": {
                "serialization": serialization.get("callback_sequence") if serialization else None,
                "field_read": field.get("callback_sequence") if field else None,
                "clone_begin": begin, "clone_end": end,
                "command_entry": entry.get("callback_sequence") if entry else None,
            },
            "phase_order": {
                "serialization": serialization.get("phase") if serialization else None,
                "field_read": field.get("phase") if field else None,
                "clone": clone.get("phase"),
                "command_entry": entry.get("phase") if entry else None,
            },
            "next_callback_after_field": {
                "sequence": next_callback.get("callback_sequence") if next_callback else None,
                "event": next_callback.get("event") if next_callback else None,
                "snapshot_before_next_callback": next_callback is not None,
            },
            "addresses": {
                "serialization_wrapper": serialization.get("wrapper_address") if serialization else None,
                "serialization_action": serialization.get("wrapper_action") if serialization else None,
                "field_wrapper": field.get("source_address") if field else None,
                "field_action": field.get("source_action") if field else None,
                "clone_source_wrapper": clone.get("source_address"),
                "clone_target_wrapper": clone.get("target_address"),
                "clone_target_action": clone.get("target_action"),
                "entry_action": entry.get("action") if entry else None,
                "entry_source_action": entry.get("source_address") if entry else None,
                "entry_command": entry.get("command") if entry else None,
                "clone_native_result": clone.get("native_result"),
            },
            "protocol": {
                "serialization_key": serial_key,
                "field_source_key": field_key,
                "clone_source_key": clone_source_key,
                "clone_target_key": clone_target_key,
                "entry_key": entry_key,
                "full_key_matches": key_matches,
                "same_sequence_only_candidate": same_sequence_only,
                "clone_origin_changed": bool(
                    isinstance(clone_source_key, list) and isinstance(clone_target_key, list)
                    and clone_source_key[0] != clone_target_key[0]),
                "clone_sequence_changed": bool(
                    isinstance(clone_source_key, list) and isinstance(clone_target_key, list)
                    and clone_source_key[1] != clone_target_key[1]),
                "clone_flags_changed": bool(
                    isinstance(clone_source_key, list) and isinstance(clone_target_key, list)
                    and clone_source_key[2] != clone_target_key[2]),
                "continuity_verified": protocol_continuity,
            },
            "payload": {
                "params_complete": params_complete,
                "differences": payload_differences,
                "full_stage_chain": bool(
                    full_stage is not None and entry is not None
                    and command_matches_target and native_result_matches_target
                ),
                "command_matches_clone_target": command_matches_target,
                "native_result_matches_clone_target": native_result_matches_target,
            },
            "clone_entry_local_evidence": entry is not None and params_complete,
            "local_stage_chain_verified": bool(full_stage is not None and entry is not None and params_complete),
            "authority": False,
            "business_result": "unknown",
            "submit_verified": False,
            "complete": False,
            "incomplete_reasons": sorted(set(reasons)),
        })
    if serializations and not any(item["payload"]["full_stage_chain"] for item in records):
        _add_issue(issues, "PROTOCOL_FULL_STAGE_CHAIN_NOT_FOUND")
    return records


def validate_files(installation_path: Path | str, manifest_path: Path | str,
                   probe_path: Path | str, *, schema_path: Path | str | None = None,
                   observation_report_path: Path | str | None = None,
                   fixture_only: bool = False) -> dict[str, Any]:
    installation_path = Path(installation_path)
    manifest_path = Path(manifest_path)
    probe_path = Path(probe_path)
    if not probe_path.is_file():
        raise InputError(f"missing probe JSONL: {probe_path}")
    probe_size = probe_path.stat().st_size
    if probe_size > MAX_PROBE_BYTES:
        raise InputError(f"probe exceeds bound ({probe_size}>{MAX_PROBE_BYTES})")
    issues: list[dict[str, Any]] = []
    installation = _load_json(installation_path)
    manifest = _load_json(manifest_path)
    identity = _validate_identity(installation, manifest, manifest_path, issues)
    session_id = identity["session_id"]
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent / "native" / PROTOCOL_SCHEMA_NAME
    schema = _static_schema(Path(schema_path), issues)

    observation_path = Path(observation_report_path) if observation_report_path else (
        _find_observation_report(installation_path) if not fixture_only else None)
    observation = _load_json(observation_path) if observation_path else None
    if observation_path is not None and not isinstance(observation, Mapping):
        _add_issue(issues, "OBSERVATION_REPORT_INVALID")
    if observation is None and not fixture_only:
        _add_issue(issues, "OBSERVATION_REPORT_MISSING")

    counts: Counter[str] = Counter()
    phases: Counter[str] = Counter()
    session_mismatches: list[dict[str, Any]] = []
    malformed = 0
    events_seen = 0
    truncated = False
    acks: dict[str, dict[str, Any]] = {}
    drops: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    clones: list[dict[str, Any]] = []
    serializations: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    lifecycles: list[dict[str, Any]] = []
    all_callbacks: list[dict[str, Any]] = []
    callback_duplicates: list[int] = []

    with probe_path.open("rb") as stream:
        offset = 0
        for line_number, raw in enumerate(stream, 1):
            start = offset
            offset += len(raw)
            if events_seen >= MAX_EVENTS:
                truncated = True
                _add_issue(issues, "EVENT_LIMIT_REACHED", line=line_number)
                break
            if len(raw) > MAX_LINE_BYTES:
                malformed += 1
                _add_issue(issues, "PROBE_LINE_TOO_LARGE", line=line_number)
                continue
            try:
                event = json.loads(raw.decode("utf-8-sig" if line_number == 1 else "utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                malformed += 1
                _add_issue(issues, "PROBE_LINE_INVALID", line=line_number)
                continue
            if not isinstance(event, Mapping):
                malformed += 1
                _add_issue(issues, "PROBE_EVENT_NOT_OBJECT", line=line_number)
                continue
            event = dict(event)
            events_seen += 1
            name = _event_name(event)
            counts[name or "<missing>"] += 1
            phase = _phase(start, observation, probe_size)
            phases[phase] += 1
            event_session = _event_session(event)
            if event_session is not None and event_session != session_id:
                session_mismatches.append({"line": line_number, "event": name,
                                           "event_session": event_session})
                continue
            if name in REQUIRED_ACKS:
                acks[name] = {
                    "line": line_number,
                    "authority_enabled": event.get("authority_enabled"),
                    "native_arguments_preserved": event.get("native_arguments_preserved"),
                    "submit_receipt": event.get("submit_receipt"),
                    "all_commands_forwarded": event.get("all_commands_forwarded"),
                }
                if name == "alliance_wrapper_protocol_observer_installed":
                    if event.get("authority_enabled") is not False or event.get("native_arguments_preserved") is not True:
                        _add_issue(issues, "PROTOCOL_ACK_INVALID", line=line_number)
                continue
            if name in DROP_EVENT_NAMES:
                dropped = _int(event.get("dropped"), minimum=0)
                if name == "native_wrapper_protocol_dropped":
                    reads = _int(event.get("field_reads"), minimum=0) or 0
                    clones_dropped = _int(event.get("clones"), minimum=0) or 0
                    dropped = reads + clones_dropped if dropped is None else dropped
                    drops.append({"line": line_number, "event": name, "dropped": dropped,
                                  "field_reads": reads, "clones": clones_dropped})
                else:
                    drops.append({"line": line_number, "event": name,
                                  "dropped": dropped if dropped is not None else 1})
                continue
            if name not in PROTOCOL_EVENTS and name != "diplomatic_command_observed":
                continue
            common = _stage_common(event, line_number, start, offset, phase)
            ordinal = common["callback_sequence"]
            if ordinal is not None:
                all_callbacks.append({"event": name, "callback_sequence": ordinal,
                                      "line": line_number, "phase": phase})
            if name == "native_wrapper_field_read_begin":
                if len(fields) < MAX_RETAINED:
                    fields.append(_field_report(event, common, issues))
            elif name == "native_alliance_wrapper_clone":
                if len(clones) < MAX_RETAINED:
                    clones.append(_clone_report(event, common, issues))
            elif name == "native_alliance_lifecycle":
                kind = event.get("kind")
                if kind == "serialization_begin":
                    if len(serializations) < MAX_RETAINED:
                        serializations.append(_serialization_report(event, common, issues))
                elif kind in LIFECYCLE_KINDS:
                    if len(lifecycles) < MAX_RETAINED:
                        item = dict(common)
                        item.update({"kind": kind, "source": _compact_shape(_shape(event.get("source"))),
                                     "wrapper_action": event.get("wrapper_action"),
                                     "origin48": event.get("origin48"), "seq4c": event.get("seq4c"),
                                     "rawflag4a": event.get("rawflag4a")})
                        lifecycles.append(item)
            elif name == "native_alliance_command_entry_observed":
                if len(entries) < MAX_RETAINED:
                    entries.append(_entry_report(event, common, issues))

    ordinals = [item["callback_sequence"] for item in all_callbacks
                if isinstance(item.get("callback_sequence"), int)]
    fields.sort(key=lambda item: (item.get("callback_sequence") or 0, item["line"]))
    clones.sort(key=lambda item: (item.get("begin_callback_sequence") or 0, item["line"]))
    serializations.sort(key=lambda item: (item.get("callback_sequence") or 0, item["line"]))
    entries.sort(key=lambda item: (item.get("callback_sequence") or 0, item["line"]))
    lifecycles.sort(key=lambda item: (item.get("callback_sequence") or 0, item["line"]))
    counts_by_ordinal = Counter(ordinals)
    callback_duplicates = sorted(value for value, count in counts_by_ordinal.items() if count > 1)
    if callback_duplicates:
        _add_issue(issues, "CALLBACK_ORDINAL_DUPLICATE", ordinals=callback_duplicates[:64])
    if session_mismatches:
        _add_issue(issues, "EVENT_SESSION_MISMATCH", count=len(session_mismatches))
    if malformed:
        _add_issue(issues, "PROBE_MALFORMED_LINES", count=malformed)
    if drops and any((item.get("dropped") or 0) > 0 for item in drops):
        _add_issue(issues, "PROBE_DROPPED_EVENTS")
    unknown_selector_counts = Counter(
        item.get("field_id") for item in fields
        if item.get("field_id") is not None and not item.get("selector_known")
    )
    if unknown_selector_counts:
        _add_issue(issues, "WRAPPER_FIELD_SELECTOR_UNKNOWN", counts={
            hex(key): value for key, value in sorted(unknown_selector_counts.items())
        })
    missing_acks = sorted(REQUIRED_ACKS - set(acks))
    for ack in missing_acks:
        _add_issue(issues, "INSTALL_ACK_MISSING", ack=ack)

    # Provide the field-to-next-callback observation without mistaking a
    # pre-return snapshot for a native return or a successful write.
    protocol_callbacks = sorted(all_callbacks, key=lambda item: (item["callback_sequence"], item["line"]))
    for field in fields:
        next_callback = _next_callback(protocol_callbacks, field.get("callback_sequence"))
        field["next_callback_sequence"] = next_callback.get("callback_sequence") if next_callback else None
        field["next_callback_event"] = next_callback.get("event") if next_callback else None
        field["snapshot_before_next_callback"] = next_callback is not None

    chains = _correlate_protocol_stages(fields, clones, serializations, entries,
                                         protocol_callbacks, issues)
    complete_chains = [item for item in chains
                       if item.get("payload", {}).get("full_stage_chain")
                       and item.get("protocol", {}).get("continuity_verified")]
    same_sequence_candidates = sum(
        bool(item.get("protocol", {}).get("same_sequence_only_candidate")) for item in chains
    )
    protocol_key_reads = {
        "serialization": sum(item.get("protocol_key") is not None for item in serializations),
        "field_source": sum(item.get("source_protocol_key") is not None for item in fields),
        "clone_source": sum(item.get("source_protocol_key") is not None for item in clones),
        "clone_target": sum(item.get("target_protocol_key") is not None for item in clones),
        "command_entry": sum(item.get("protocol_key") is not None for item in entries),
    }
    field_counter = Counter(item.get("field_id") for item in fields)
    global_reasons: list[str] = []
    if not schema.get("verified"):
        global_reasons.append("PROTOCOL_SCHEMA_UNVERIFIED")
    if missing_acks:
        global_reasons.append("INSTALL_ACK_INCOMPLETE")
    if session_mismatches:
        global_reasons.append("SESSION_ASSOCIATION_INCOMPLETE")
    if drops and any((item.get("dropped") or 0) > 0 for item in drops):
        global_reasons.append("PROBE_DROPPED_EVENTS")
    if malformed or truncated:
        global_reasons.append("TRACE_TRUNCATED_OR_MALFORMED")
    if callback_duplicates:
        global_reasons.append("CALLBACK_ORDER_UNCERTAIN")
    if not fields:
        global_reasons.append("NO_WRAPPER_FIELD_READS")
    if not clones:
        global_reasons.append("NO_WRAPPER_CLONES")
    if not serializations:
        global_reasons.append("NO_SERIALIZATION_BEGIN")
    if not entries:
        global_reasons.append("NO_COMMAND_ENTRY")
    if not chains:
        global_reasons.append("NO_CLONE_ENTRY_CANDIDATE")
    if chains and not complete_chains:
        global_reasons.append("NO_FULL_PROTOCOL_STAGE_CHAIN")
    if same_sequence_candidates:
        global_reasons.append("SEQUENCE_ONLY_CANDIDATE_NOT_AUTHORIZATION")
    # This observer is passive by contract.  These boundaries are always part
    # of the report even if every callback parameter is readable.
    global_reasons.extend([
        "SERIALIZATION_IS_NOT_SUBMISSION",
        "NO_AUTHORITY_OR_BUSINESS_SUCCESS",
    ])
    global_reasons = list(dict.fromkeys(global_reasons))
    report: dict[str, Any] = {
        "schema": "alliance-protocol-validation/1",
        "date": "2026-10-13",
        "validator": "validate_alliance_protocol",
        "offline_only": True,
        "runtime_this_turn": not fixture_only,
        "fixture_only": fixture_only,
        "game_started_by_validator": False,
        "injection_performed_by_validator": False,
        "inputs": {
            "installation": str(installation_path), "manifest": str(manifest_path),
            "probe": str(probe_path), "observation_report": str(observation_path) if observation_path else None,
        },
        "static_schema": schema,
        "static_contract": {
            "source": str(schema_path),
            "refs": {
                "ProtocolWrapperShape": "3-9",
                "ProtocolReadEvent": "11-18",
                "ProtocolCloneEvent": "20-31",
                "field_observe": "53-73",
                "clone_observe_before_after": "76-103",
                "flush_event_schema": "173-214",
            },
            "field_snapshot_is_pre_return": True,
            "clone_has_before_after_wrapper": True,
            "serialization_or_submit_not_inferred": True,
        },
        "identity": identity,
        "observation_report": {
            "path": str(observation_path) if observation_path else None,
            "log_start_offset": observation.get("log_start_offset") if isinstance(observation, Mapping) else None,
            "log_end_offset": observation.get("log_end_offset") if isinstance(observation, Mapping) else None,
            "status": "bounded_slice_used" if isinstance(observation, Mapping) else "unknown",
        },
        "runtime": {
            "installation_session": session_id,
            "session_mismatch_count": len(session_mismatches),
            "session_mismatches": session_mismatches[:32],
            "acks": acks,
            "missing_acks": missing_acks,
            "event_counts": dict(counts),
            "phase_event_counts": dict(phases),
            "callback_order": {
                "observed": len(ordinals), "unique": len(set(ordinals)),
                "min": min(ordinals) if ordinals else None,
                "max": max(ordinals) if ordinals else None,
                "duplicate_ordinals": callback_duplicates,
                "line_flush_used_for_correlation": False,
            },
            "drops": drops,
            "malformed_lines": malformed,
            "truncated": truncated,
        },
        "field_read": {
            "total": len(fields),
            "selector_set": [hex(value) for value in sorted(FIELD_SELECTORS)],
            "counts_by_selector": {hex(key): value for key, value in sorted(
                ((key, value) for key, value in field_counter.items() if key is not None))},
            "known_selector_count": sum(item.get("selector_known") is True for item in fields),
            "unknown_selector_count": sum(unknown_selector_counts.values()),
            "unknown_selector_counts": {hex(key): value for key, value in sorted(
                unknown_selector_counts.items())},
            "input16_readable_count": sum(item.get("input16_readable") for item in fields),
            "input16_valid_hex_count": sum(item.get("input16_valid_hex") for item in fields),
            "pre_return_snapshot_count": sum(item.get("native_return_observed") is False for item in fields),
            "records": fields,
        },
        "wrapper_clone": {
            "total": len(clones),
            "source_protocol_key_readable_count": protocol_key_reads["clone_source"],
            "target_protocol_key_readable_count": protocol_key_reads["clone_target"],
            "records": clones,
        },
        "serialization_begin": {
            "total": len(serializations),
            "protocol_key_readable_count": protocol_key_reads["serialization"],
            "is_submission": False,
            "records": serializations,
        },
        "command_entry": {
            "total": len(entries),
            "protocol_key_readable_count": protocol_key_reads["command_entry"],
            "decision_country_verified": False,
            "authority": False,
            "records": entries,
        },
        "lifecycle_context": {"total": len(lifecycles), "records": lifecycles},
        "stage_chains": {
            "candidate_count": len(chains),
            "clone_entry_local_evidence_count": sum(
                item.get("clone_entry_local_evidence") is True for item in chains),
            "full_stage_chain_count": sum(
                item.get("payload", {}).get("full_stage_chain") is True for item in chains),
            "complete_count": len(complete_chains),
            "same_sequence_only_candidate_count": same_sequence_candidates,
            "records": chains,
        },
        "protocol_policy": {
            "key_fields": ["origin", "sequence", "flags"],
            "sequence_only_matching": False,
            "sequence_equal_is_candidate_only": True,
            "serialization_begin_is_submission": False,
            "authority_enabled": False,
            "business_success": "unknown",
        },
        "issues": issues,
        "global_incomplete_reasons": global_reasons,
        "acceptance_gate": False,
        "status": "observed_incomplete" if (fields or clones or serializations or entries) else "no_protocol_runtime_evidence",
        "evidence_limits": [
            "Field read events are pre-return wrapper snapshots; they do not prove native return or write success.",
            "Only full origin/sequence/flags keys are compared; sequence equality alone is a candidate.",
            "Serialization_begin is an observation stage, never a submit or queue receipt.",
            "No authority, business success, decision country, or mutation is generated.",
        ],
    }
    return report


def write_json_exclusive(path: Path | str, report: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True,
                  allow_nan=False)
        stream.write("\n")


def render_report(report: Mapping[str, Any]) -> str:
    identity = report.get("identity", {})
    runtime = report.get("runtime", {})
    field = report.get("field_read", {})
    clone = report.get("wrapper_clone", {})
    serialization = report.get("serialization_begin", {})
    entry = report.get("command_entry", {})
    chains = report.get("stage_chains", {})
    reasons = report.get("global_incomplete_reasons", [])
    return "\n".join([
        "# r17c wrapper protocol 离线验收（2026-10-13）",
        "",
        f"实验 `{identity.get('experiment_id')}`，session `{identity.get('session_id')}`，PID `{identity.get('pid')}`。",
        f"runtime_this_turn=`{report.get('runtime_this_turn')}`；验证器未启动游戏、未注入；acceptance gate=`false`。",
        "",
        "## 运行覆盖",
        "",
        f"field read `{field.get('total', 0)}`（已知 selector `{field.get('known_selector_count', 0)}`），wrapper clone `{clone.get('total', 0)}`，serialization_begin `{serialization.get('total', 0)}`，command entry `{entry.get('total', 0)}`。",
        f"callback `{runtime.get('callback_order', {})}`；阶段切片 `{runtime.get('phase_event_counts', {})}`；drops `{runtime.get('drops', [])}`。",
        "",
        "## 阶段链",
        "",
        f"独立 clone `{clone.get('total', 0)}` 条；clone→entry 局部证据 `{chains.get('clone_entry_local_evidence_count', 0)}`，全阶段链 `{chains.get('full_stage_chain_count', 0)}`，完整 key 链 `{chains.get('complete_count', 0)}`；sequence-only 候选 `{chains.get('same_sequence_only_candidate_count', 0)}`。",
        "协议 key 始终按 origin/sequence/flags 三元组比较；field read 只作为 pre-return 局部快照，不声称 native-return。",
        "",
        "## 未完成阶段",
        "",
        *([f"- {reason}" for reason in reasons] or ["- none"]),
        "",
        "serialization_begin 不等于提交/入队；authority、业务成功和决策主体保持 unknown/false。",
        "",
    ])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--observation-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fixture-only", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        report = validate_files(
            args.installation, args.manifest, args.probe,
            schema_path=args.schema, observation_report_path=args.observation_report,
            fixture_only=args.fixture_only,
        )
        output = args.output or args.installation.parent / "r17c-protocol-validation.json"
        markdown = args.report or output.with_suffix(".md")
        write_json_exclusive(output, report)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        with markdown.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render_report(report))
        print(json.dumps({
            "status": report["status"], "acceptance_gate": report["acceptance_gate"],
            "field_reads": report["field_read"]["total"],
            "wrapper_clones": report["wrapper_clone"]["total"],
            "serialization_begin": report["serialization_begin"]["total"],
            "command_entries": report["command_entry"]["total"],
            "candidate_chains": report["stage_chains"]["candidate_count"],
            "clone_entry_local_evidence": report["stage_chains"]["clone_entry_local_evidence_count"],
            "full_stage_chains": report["stage_chains"]["full_stage_chain_count"],
            "output": str(output), "report": str(markdown),
        }, ensure_ascii=False))
        return 0
    except (InputError, OSError, ValueError) as exc:
        print(f"validate_alliance_protocol: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
