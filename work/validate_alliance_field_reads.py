"""Offline, bounded validation of the passive alliance field-reader trace.

This validator consumes an installation record, a build manifest, and a
control-probe JSONL.  It never opens the game process and never imports the
bridge/native implementation.  Field reads are grouped by the full action
address, context address, and native callback ordinal.  A country-looking
three-byte tag is never used as an identity key and a local vtable/layout
match is never promoted to an endpoint or decision-country assertion.

The r16c observer records a field read before the original method returns.  A
field group therefore describes local decode evidence only.  A command entry
is correlated only through an ordered local field/group -> clone -> entry
chain with the same full action layout.  Protocol sequence values, outgoing
serializer records, submission, and business results are deliberately kept
outside that correlation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator, Mapping


MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_PROBE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_EVENTS = 250_000
MAX_HASH_FILE_BYTES = 64 * 1024 * 1024
HASH_BLOCK_BYTES = 1024 * 1024
MAX_ISSUES = 256

EXPECTED_GAME_SHA256 = "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77"
EXPECTED_MANIFEST_VERSION = 10
ALLIANCE_VTABLE_RVA = 0x1C80720
EXPECTED_CALLER_RETURN_RVA = {
    0x2AAB1F + 5: {"call_site_rva": 0x2AAB1F, "target_rva": 0x3D2350},
    0x2AB95C + 5: {"call_site_rva": 0x2AB95C, "target_rva": 0x3D2350},
    0x2D618B + 5: {"call_site_rva": 0x2D618B, "target_rva": 0x3D2350},
    0x2EDBFA + 5: {"call_site_rva": 0x2EDBFA, "target_rva": 0x3D2350},
    0x2EE021 + 5: {"call_site_rva": 0x2EE021, "target_rva": 0x3D2350},
    0x6CF08D + 5: {"call_site_rva": 0x6CF08D, "target_rva": 0x3D2350},
    0x766CC8 + 5: {"call_site_rva": 0x766CC8, "target_rva": 0x3D2350},
}

# These are the actual field ids observed in the 1.37.4 action vtable path.
# In particular, 0x3ec is the variant field.  Do not silently revive the old
# ec3 typo as a field id.
FIELD_LAYOUT: dict[int, dict[str, Any]] = {
    0xE1: {"name": "state34", "offset": "0x34"},
    0x2931: {"name": "actor10", "offset": "0x10"},
    0x2D87: {"name": "mirror18", "offset": "0x18"},
    0x2932: {"name": "recipient20", "offset": "0x20"},
    0x284D: {"name": "date28", "offset": "0x28"},
    0x3EC: {"name": "variant38", "offset": "0x38", "note": "actual variant field; not 0xec3"},
    0x2A2E: {"name": "date2c", "offset": "0x2c"},
    0x2AD6: {"name": "envoy30", "offset": "0x30"},
    0x0B: {"name": "proposal3c", "offset": "0x3c"},
}
EXPECTED_FIELD_IDS = tuple(FIELD_LAYOUT)
EXPECTED_FIELD_ID_SET = set(EXPECTED_FIELD_IDS)
LAYOUT_FIELDS = (
    "vtable_rva", "discriminator", "actor10", "mirror18", "recipient20",
    "date28", "date2c", "envoy30", "state34", "variant38", "proposal3c",
)
SHAPE_FIELDS = (
    "addr", "readable", "matched", "handles_canonical", "tracked",
    *LAYOUT_FIELDS,
)
REQUIRED_ACKS = {
    "diplomacy_observer_installed",
    "alliance_lifecycle_observer_installed",
    "alliance_serializer_observer_installed",
    "alliance_field_reader_observer_installed",
    "direct_break_entry_observer_installed",
}


class InputError(ValueError):
    """Raised for an input that exceeds the bounded offline contract."""


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


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _address(value: Any) -> int | None:
    return _int(value, minimum=0x10000)


def _load_json(path: Path, limit: int = MAX_METADATA_BYTES) -> Any:
    if not path.is_file():
        raise InputError(f"missing JSON: {path}")
    size = path.stat().st_size
    if size > limit:
        raise InputError(f"JSON exceeds bound ({size}>{limit}): {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid JSON {path}: {exc}") from exc


def _stream_sha256(path: Path | None) -> tuple[str | None, str | None]:
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


def _declared_artifact(manifest_path: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    # Runtime manifests may retain an absolute build path.  Offline replay
    # resolves only the basename beside the supplied manifest.
    return manifest_path.parent / Path(value).name


def _compact_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"readable": False, "missing": list(LAYOUT_FIELDS)}
    compact = {key: value.get(key) for key in SHAPE_FIELDS if key in value}
    missing = [key for key in LAYOUT_FIELDS if key not in value]
    if missing:
        compact["missing"] = missing
    return compact


def _shape_number(value: Any) -> int | None:
    return _int(value)


def _shape_layout_key(shape: Mapping[str, Any] | None) -> tuple[Any, ...] | None:
    if not isinstance(shape, Mapping):
        return None
    values: list[Any] = []
    for key in LAYOUT_FIELDS:
        number = _shape_number(shape.get(key))
        if number is None:
            return None
        values.append(number)
    return tuple(values)


def _shape_layout_complete(shape: Mapping[str, Any] | None) -> bool:
    return _shape_layout_key(shape) is not None


def _shape_layout_equal(left: Mapping[str, Any] | None,
                        right: Mapping[str, Any] | None) -> bool:
    left_key = _shape_layout_key(left)
    right_key = _shape_layout_key(right)
    return left_key is not None and left_key == right_key


def _shape_layout_differences(left: Mapping[str, Any] | None,
                              right: Mapping[str, Any] | None) -> list[str]:
    """Return full-layout fields that differ or cannot be read.

    A mismatch is evidence to retain, not a reason to silently discard an
    otherwise observable address/callback chain.  The caller reports the
    chain as locally correlated while keeping layout continuity incomplete.
    """
    differences: list[str] = []
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return list(LAYOUT_FIELDS)
    for key in LAYOUT_FIELDS:
        left_value = _shape_number(left.get(key))
        right_value = _shape_number(right.get(key))
        if left_value is None or right_value is None or left_value != right_value:
            differences.append(key)
    return differences


def _dummy_handle(value: Any) -> bool:
    if isinstance(value, str) and value.strip().upper() == "---":
        return True
    parsed = _int(value)
    return parsed == 0x2D2D2D


def _endpoint_identity(shape: Mapping[str, Any] | None) -> tuple[bool, str | None]:
    if not isinstance(shape, Mapping):
        return False, "shape_missing"
    for key in ("readable", "matched", "handles_canonical"):
        if shape.get(key) is not True:
            return False, f"{key}_not_verified"
    actor = shape.get("actor10")
    mirror = shape.get("mirror18")
    recipient = shape.get("recipient20")
    if any(_dummy_handle(value) for value in (actor, mirror, recipient)):
        return False, "dummy_country_handle"
    actor_number = _shape_number(actor)
    mirror_number = _shape_number(mirror)
    recipient_number = _shape_number(recipient)
    if actor_number is None or mirror_number is None or recipient_number is None:
        return False, "country_handle_unreadable"
    if actor_number != mirror_number:
        return False, "actor_mirror_mismatch"
    return True, None


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


def _callback_ordinal(event: Mapping[str, Any]) -> int | None:
    name = event.get("event")
    if name == "native_alliance_lifecycle":
        return _int(event.get("callback_sequence", event.get("sequence")), minimum=1)
    if name in {
        "native_alliance_field_read_begin",
        "native_alliance_command_entry_observed",
        "native_direct_break_entry",
    }:
        return _int(event.get("callback_sequence"), minimum=1)
    return None


def _event_session(event: Mapping[str, Any]) -> str | None:
    value = event.get("session_id")
    return value if isinstance(value, str) else None


def _add_issue(issues: list[dict[str, Any]], code: str,
               **detail: Any) -> None:
    if len(issues) < MAX_ISSUES:
        item: dict[str, Any] = {"code": code}
        item.update(detail)
        issues.append(item)


def _find_observation_report(installation_path: Path) -> Path | None:
    parent = installation_path.parent
    candidates: list[Path] = []
    try:
        for child in parent.iterdir():
            if child.is_dir():
                candidate = child / "observation-report.json"
                if candidate.is_file():
                    candidates.append(candidate)
    except OSError:
        return None
    return sorted(candidates)[0] if candidates else None


def _validate_identity(installation: Any, manifest: Any,
                       manifest_path: Path, issues: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(installation, Mapping):
        raise InputError("installation JSON must be an object")
    if not isinstance(manifest, Mapping):
        raise InputError("build manifest JSON must be an object")
    session = installation.get("session_id")
    if not isinstance(session, str) or not session:
        raise InputError("installation.session_id is required")

    installation_sha = installation.get("dll_sha256")
    manifest_sha = manifest.get("dll_sha256")
    if isinstance(installation_sha, str) and isinstance(manifest_sha, str):
        if installation_sha.lower() != manifest_sha.lower():
            _add_issue(issues, "DLL_HASH_DECLARATION_MISMATCH")
    elif not isinstance(installation_sha, str) or not isinstance(manifest_sha, str):
        _add_issue(issues, "DLL_HASH_DECLARATION_MISSING")

    version = _int(manifest.get("version"), minimum=0)
    if version != EXPECTED_MANIFEST_VERSION:
        _add_issue(issues, "BUILD_VERSION_MISMATCH", expected=EXPECTED_MANIFEST_VERSION,
                   actual=version)
    if manifest.get("compiled") is not True:
        _add_issue(issues, "BUILD_NOT_MARKED_COMPILED", actual=manifest.get("compiled"))

    manifest_game_sha = manifest.get("game_sha256")
    installation_game_sha = installation.get("game_sha256")
    if (isinstance(manifest_game_sha, str) and isinstance(installation_game_sha, str)
            and manifest_game_sha.lower() != installation_game_sha.lower()):
        _add_issue(issues, "GAME_HASH_DECLARATION_MISMATCH")
    if (isinstance(installation_game_sha, str)
            and installation_game_sha.lower() != EXPECTED_GAME_SHA256):
        _add_issue(issues, "GAME_HASH_UNEXPECTED", actual=installation_game_sha)

    source_reports: list[dict[str, Any]] = []
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        _add_issue(issues, "MANIFEST_SOURCES_MISSING")
        sources = []
    for item in sources:
        if not isinstance(item, Mapping):
            _add_issue(issues, "SOURCE_ENTRY_INVALID")
            continue
        expected = item.get("sha256")
        path = _declared_artifact(manifest_path, item.get("name"))
        actual, error = _stream_sha256(path)
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

    dll_path = _declared_artifact(manifest_path, manifest.get("dll"))
    actual_dll_sha, dll_error = _stream_sha256(dll_path)
    dll_verified = isinstance(manifest_sha, str) and actual_dll_sha == manifest_sha.lower()
    if dll_error is not None:
        _add_issue(issues, "DLL_HASH_UNVERIFIED", reason=dll_error)
    elif not dll_verified:
        _add_issue(issues, "DLL_HASH_MISMATCH", expected=manifest_sha, actual=actual_dll_sha)

    module_reports: list[dict[str, Any]] = []
    modules = installation.get("modules_after_install")
    if not isinstance(modules, list):
        _add_issue(issues, "INSTALLATION_MODULES_MISSING")
        modules = []
    for item in modules:
        if not isinstance(item, Mapping):
            continue
        path = _declared_artifact(manifest_path, item.get("path"))
        actual, error = _stream_sha256(path)
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
        "pid": _int(installation.get("pid"), minimum=1),
        "creation_filetime": installation.get("creation_filetime"),
        "experiment_id": manifest.get("experiment_id", installation.get("experiment_id")),
        "manifest_version": version,
        "manifest_compiled": manifest.get("compiled"),
        "game_sha256": installation_game_sha,
        "manifest_game_sha256": manifest_game_sha,
        "expected_game_sha256": EXPECTED_GAME_SHA256,
        "dll_sha256": manifest_sha,
        "installation_dll_sha256": installation_sha,
        "dll_hash": {"path": str(dll_path) if dll_path else None,
                      "actual": actual_dll_sha, "verified": dll_verified},
        "source_hashes": source_reports,
        "module_hashes": module_reports,
        "installation_returncode": installation.get("installation_returncode"),
        "runtime_verified_flag": installation.get("runtime_verified"),
    }


def _field_record(event: Mapping[str, Any], line: int, start: int, end: int,
                  phase: str) -> dict[str, Any]:
    field_id = _int(event.get("field_id"), minimum=0, maximum=0xFFFFFFFF)
    meaning = FIELD_LAYOUT.get(field_id or -1)
    source = event.get("source") if isinstance(event.get("source"), Mapping) else {}
    endpoint, endpoint_reason = _endpoint_identity(source)
    input_hex = event.get("input16_hex")
    if not isinstance(input_hex, str):
        input_hex = None
    if input_hex is not None:
        input_hex = input_hex[:32]
    callback = _callback_ordinal(event)
    source_missing = [key for key in LAYOUT_FIELDS if key not in source]
    return {
        "line": line,
        "byte_start": start,
        "byte_end": end,
        "phase": phase,
        "callback_sequence": callback,
        "thread": _int(event.get("thread"), minimum=0),
        "field_id": field_id,
        "field_hex": hex(field_id) if field_id is not None else None,
        "field_name": meaning.get("name") if meaning else None,
        "field_offset": meaning.get("offset") if meaning else None,
        "field_note": meaning.get("note") if meaning else None,
        "context": event.get("context"),
        "caller_return_rva": event.get("caller_return_rva"),
        "input16_readable": event.get("input16_readable") is True,
        "input16_hex": input_hex,
        "context_word_readable": event.get("context_word_readable") is True,
        "native_forward_contract": event.get("native_forward_count_by_hook_contract") == 1,
        "source": _compact_shape(source),
        "source_layout_complete": not source_missing and _shape_layout_complete(source),
        "source_layout_missing": source_missing,
        "source_endpoint_identity": endpoint,
        "source_endpoint_reason": endpoint_reason,
        "source_dummy_handles": any(_dummy_handle(source.get(key))
                                     for key in ("actor10", "mirror18", "recipient20")),
        "source_matched": event.get("source", {}).get("matched") is True
        if isinstance(event.get("source"), Mapping) else False,
    }


def _group_fields(records: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        source = record["source"]
        action = source.get("addr")
        key = (action, record.get("context"), record.get("caller_return_rva"))
        groups[key].append(record)

    result: list[dict[str, Any]] = []
    for key, members in sorted(groups.items(), key=lambda item: min(
            (record.get("callback_sequence") or 0) for record in item[1])):
        members.sort(key=lambda record: (record.get("callback_sequence") or 0,
                                         record.get("line") or 0))
        ids = [record.get("field_id") for record in members]
        counts = Counter(ids)
        present = set(ids)
        missing = sorted(EXPECTED_FIELD_ID_SET - present)
        unknown = sorted(field for field in present - EXPECTED_FIELD_ID_SET
                         if field is not None)
        duplicates = sorted(field for field, count in counts.items()
                            if field is not None and count > 1)
        unresolved = sorted({record["field_id"] for record in members
                             if (not record["input16_readable"]
                                 or not record["source_layout_complete"]
                                 or not record["source_matched"])})
        dummy_callbacks = [record["callback_sequence"] for record in members
                           if record["source_dummy_handles"]]
        latest = members[-1]["source"] if members else {}
        endpoint, endpoint_reason = _endpoint_identity(latest)
        set_complete = not missing and not duplicates and not unknown
        decode_complete = set_complete and not unresolved and all(
            record["context_word_readable"] and record["native_forward_contract"]
            for record in members
        )
        semantic_complete = decode_complete and endpoint
        if not set_complete:
            _add_issue(issues, "FIELD_SET_INCOMPLETE", action=key[0],
                       context=key[1], missing=missing, duplicates=duplicates)
        if unresolved:
            _add_issue(issues, "FIELD_LOCAL_UNRESOLVED", action=key[0],
                       context=key[1], fields=unresolved)
        result.append({
            "group_id": f"{key[0]}|{key[1]}|{key[2]}",
            "action_address": key[0],
            "context": key[1],
            "caller_return_rva": key[2],
            "phase_counts": dict(Counter(record["phase"] for record in members)),
            "callback_range": [members[0].get("callback_sequence"),
                               members[-1].get("callback_sequence")] if members else [None, None],
            "field_ids_in_callback_order": ids,
            "field_counts": {str(field): count for field, count in counts.items()},
            "missing_field_ids": missing,
            "duplicate_field_ids": duplicates,
            "unknown_field_ids": unknown,
            "unresolved_field_ids": unresolved,
            "dummy_source_callbacks": dummy_callbacks,
            "source_layout_complete_count": sum(record["source_layout_complete"] for record in members),
            "source_endpoint_identity_count": sum(record["source_endpoint_identity"] for record in members),
            "latest_source": latest,
            "latest_endpoint_identity_verified": endpoint,
            "latest_endpoint_identity_reason": endpoint_reason,
            "field_set_complete": set_complete,
            "field_decode_complete": decode_complete,
            "semantic_endpoint_complete": semantic_complete,
            "records": members,
        })
    return result


def _lifecycle_shape(event: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    value = event.get(name)
    return value if isinstance(value, Mapping) else None


def _causal_correlations(groups: list[dict[str, Any]], entries: list[dict[str, Any]],
                         lifecycles: list[dict[str, Any]],
                         issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clones: list[dict[str, Any]] = []
    destructors: defaultdict[int, list[int]] = defaultdict(list)
    for event in lifecycles:
        ordinal = _callback_ordinal(event)
        if ordinal is None:
            continue
        kind = event.get("kind")
        source = _lifecycle_shape(event, "source")
        target = _lifecycle_shape(event, "target")
        if kind == "clone":
            source_addr = _address(source.get("addr")) if source else None
            target_addr = _address(target.get("addr")) if target else None
            if source_addr is not None and target_addr is not None:
                clones.append({"ordinal": ordinal, "source_addr": source_addr,
                               "target_addr": target_addr, "source": source,
                               "target": target, "phase": event.get("phase")})
        elif kind in {"destructor", "destructor_return"} and source:
            address = _address(source.get("addr"))
            if address is not None and kind == "destructor":
                destructors[address].append(ordinal)
    clones.sort(key=lambda item: item["ordinal"])

    correlations: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: (_callback_ordinal(item) or 0,
                                                   item.get("line", 0))):
        entry_ordinal = _callback_ordinal(entry)
        entry_action = _address(entry.get("action"))
        entry_shape = entry.get("source") if isinstance(entry.get("source"), Mapping) else {}
        # (field-group end, exact-layout score, clone ordinal, group, clone)
        # keeps the address/callback chain even when a later native mutation
        # changes one layout field before the command-entry snapshot.
        candidates: list[tuple[int, int, int, dict[str, Any], dict[str, Any] | None]] = []
        for group in groups:
            action = _address(group.get("action_address"))
            callback_range = group.get("callback_range") or [None, None]
            group_end = _int(callback_range[1], minimum=1)
            if action is None or entry_action is None or entry_ordinal is None or group_end is None:
                continue
            if group_end >= entry_ordinal:
                continue
            if action == entry_action:
                layout_equal = _shape_layout_equal(group.get("latest_source"), entry_shape)
                candidates.append((group_end, int(layout_equal), group_end, group, None))
            for clone in clones:
                if not (group_end < clone["ordinal"] < entry_ordinal):
                    continue
                if clone["target_addr"] != entry_action:
                    continue
                if action not in {clone["source_addr"], clone["target_addr"]}:
                    continue
                blocked = False
                for address in (action, clone["target_addr"]):
                    if any(group_end < destroyed < clone["ordinal"]
                           for destroyed in destructors.get(address, ())):
                        blocked = True
                        break
                if not blocked:
                    layout_equal = _shape_layout_equal(clone["target"], entry_shape)
                    candidates.append((group_end, int(layout_equal), clone["ordinal"], group, clone))

        entry_endpoint, entry_reason = _endpoint_identity(entry_shape)
        if candidates:
            _, layout_score, _, group, clone = max(
                candidates, key=lambda item: (item[0], item[1], item[2]))
            clone_target_layout = bool(clone and _shape_layout_equal(clone["target"], entry_shape))
            layout_left = clone["target"] if clone else group.get("latest_source")
            layout_differences = _shape_layout_differences(layout_left, entry_shape)
            correlations.append({
                "entry_line": entry.get("line"),
                "entry_callback_sequence": entry_ordinal,
                "entry_action_address": entry.get("action"),
                "entry_phase": entry.get("phase"),
                "entry_source": _compact_shape(entry_shape),
                "entry_endpoint_identity_verified": entry_endpoint,
                "entry_endpoint_identity_reason": entry_reason,
                "field_group_id": group["group_id"],
                "field_action_address": group["action_address"],
                "field_callback_range": group["callback_range"],
                "field_decode_complete": group["field_decode_complete"],
                "field_semantic_endpoint_complete": group["semantic_endpoint_complete"],
                "clone": {
                    "sequence": clone["ordinal"] if clone else None,
                    "phase": clone.get("phase"),
                    "source_address": hex(clone["source_addr"]) if clone else None,
                    "target_address": hex(clone["target_addr"]) if clone else None,
                    "target_layout_matches_entry_source": clone_target_layout,
                    "source_layout_complete": bool(clone and _shape_layout_complete(clone["source"])),
                    "target_layout_complete": bool(clone and _shape_layout_complete(clone["target"])),
                } if clone else None,
                "causal_local_evidence": True,
                "layout_continuity_verified": bool(layout_score),
                "layout_differences": layout_differences,
                "same_sequence_used_for_correlation": False,
                "outgoing_transport_associated": False,
                "submit_verified": False,
                "decision_country_verified": False,
                "source_unknown": True,
            })
        else:
            _add_issue(issues, "FIELD_ENTRY_CHAIN_NOT_FOUND",
                       entry_callback_sequence=entry_ordinal,
                       action=entry.get("action"))
            correlations.append({
                "entry_line": entry.get("line"),
                "entry_callback_sequence": entry_ordinal,
                "entry_action_address": entry.get("action"),
                "entry_phase": entry.get("phase"),
                "entry_source": _compact_shape(entry_shape),
                "entry_endpoint_identity_verified": entry_endpoint,
                "entry_endpoint_identity_reason": entry_reason,
                "field_group_id": None,
                "field_action_address": None,
                "field_callback_range": None,
                "field_decode_complete": False,
                "field_semantic_endpoint_complete": False,
                "clone": None,
                "causal_local_evidence": False,
                "layout_continuity_verified": False,
                "layout_differences": list(LAYOUT_FIELDS),
                "same_sequence_used_for_correlation": False,
                "outgoing_transport_associated": False,
                "submit_verified": False,
                "decision_country_verified": False,
                "source_unknown": True,
            })
    return correlations


def _direct_break_report(events: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: (_callback_ordinal(item) or 0,
                                                  item.get("line", 0))):
        caller = _int(event.get("caller_return_rva"), minimum=0)
        expected = EXPECTED_CALLER_RETURN_RVA.get(caller or -1)
        owner_country = event.get("owner_is_country") is True
        input_canonical = event.get("input_canonical") is True
        flag = _int(event.get("native_flag"), minimum=0, maximum=255)
        verified = bool(expected and event.get("direct_call_bytes_verified") is True
                        and event.get("owner_readable") is True
                        and owner_country and input_canonical and flag is not None)
        if not verified:
            _add_issue(issues, "DIRECT_BREAK_CALLER_UNVERIFIED",
                       caller_return_rva=event.get("caller_return_rva"))
        result.append({
            "line": event.get("line"),
            "byte_start": event.get("byte_start"),
            "byte_end": event.get("byte_end"),
            "phase": event.get("phase"),
            "callback_sequence": _callback_ordinal(event),
            "caller_return_rva": event.get("caller_return_rva"),
            "known_caller": expected is not None,
            "expected_call_site_rva": hex(expected["call_site_rva"]) if expected else None,
            "expected_target_rva": hex(expected["target_rva"]) if expected else None,
            "e8_target_verified_by_native_event": bool(
                expected and event.get("direct_call_bytes_verified") is True),
            "owner": event.get("owner"),
            "owner_handle": event.get("owner_handle"),
            "input_handle": event.get("input_handle"),
            "owner_readable": event.get("owner_readable") is True,
            "owner_is_country": owner_country,
            "input_canonical": input_canonical,
            "native_flag": flag,
            "date_readable": event.get("date_readable") is True,
            "date_raw": event.get("date_raw"),
            "decision_country_verified": False,
            "caller_source": None,
            "business_result": "unknown",
            "verified": verified,
        })
    return result


def validate_files(installation_path: Path | str, manifest_path: Path | str,
                   probe_path: Path | str, *, observation_report_path: Path | str | None = None,
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

    observation_path = Path(observation_report_path) if observation_report_path else (
        _find_observation_report(installation_path) if not fixture_only else None)
    observation = _load_json(observation_path, MAX_METADATA_BYTES) if observation_path else None
    if observation_path is not None and not isinstance(observation, Mapping):
        _add_issue(issues, "OBSERVATION_REPORT_INVALID")
    if observation is None and not fixture_only:
        _add_issue(issues, "OBSERVATION_REPORT_MISSING")

    counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()
    session_mismatches: list[dict[str, Any]] = []
    field_records: list[dict[str, Any]] = []
    direct_events: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    lifecycles: list[dict[str, Any]] = []
    drops: list[dict[str, Any]] = []
    acknowledgements: set[str] = set()
    callback_ordinals: list[tuple[int, str, int]] = []
    malformed_lines = 0
    lines = 0

    with probe_path.open("rb") as stream:
        offset = 0
        for raw in stream:
            lines += 1
            start = offset
            offset += len(raw)
            if lines > MAX_EVENTS:
                raise InputError(f"probe event bound exceeded: {MAX_EVENTS}")
            if len(raw) > MAX_LINE_BYTES:
                _add_issue(issues, "PROBE_LINE_TOO_LARGE", line=lines, bytes=len(raw))
                continue
            try:
                event = json.loads(raw.decode("utf-8-sig"))
            except (UnicodeError, json.JSONDecodeError):
                malformed_lines += 1
                _add_issue(issues, "PROBE_LINE_INVALID", line=lines)
                continue
            if not isinstance(event, Mapping):
                _add_issue(issues, "PROBE_EVENT_NOT_OBJECT", line=lines)
                continue
            event = dict(event)
            event["line"] = lines
            event["byte_start"] = start
            event["byte_end"] = offset
            name = event.get("event")
            if not isinstance(name, str):
                _add_issue(issues, "PROBE_EVENT_NAME_MISSING", line=lines)
                continue
            counts[name] += 1
            phase = _phase(start, observation, probe_size)
            phase_counts[phase] += 1
            event_session = _event_session(event)
            if event_session is not None and event_session != session_id:
                session_mismatches.append({"line": lines, "event": name,
                                           "event_session": event_session})
                continue
            if name in REQUIRED_ACKS:
                acknowledgements.add(name)
            ordinal = _callback_ordinal(event)
            if ordinal is not None and name in {
                "native_alliance_field_read_begin", "native_alliance_lifecycle",
                "native_alliance_command_entry_observed", "native_direct_break_entry",
            }:
                callback_ordinals.append((ordinal, name, lines))
            if name == "native_alliance_field_read_begin":
                record = _field_record(event, lines, start, offset, phase)
                field_records.append(record)
            elif name == "native_direct_break_entry":
                event["phase"] = phase
                event["line"] = lines
                event["byte_start"] = start
                event["byte_end"] = offset
                direct_events.append(event)
            elif name == "native_alliance_command_entry_observed":
                event["phase"] = phase
                event["byte_start"] = start
                event["byte_end"] = offset
                entries.append(event)
            elif name == "native_alliance_lifecycle":
                event["phase"] = phase
                event["byte_start"] = start
                event["byte_end"] = offset
                lifecycles.append(event)
            if "drop" in name or name == "observation_incomplete":
                dropped = _int(event.get("dropped"), minimum=0)
                drops.append({"line": lines, "event": name, "dropped": dropped})

    if malformed_lines:
        _add_issue(issues, "PROBE_MALFORMED_LINES", count=malformed_lines)
    if session_mismatches:
        _add_issue(issues, "EVENT_SESSION_MISMATCH", count=len(session_mismatches))
    if not (acknowledgements & {"alliance_field_reader_observer_installed"}):
        _add_issue(issues, "FIELD_READER_INSTALL_ACK_MISSING")
    if not (acknowledgements & {"direct_break_entry_observer_installed"}):
        _add_issue(issues, "DIRECT_BREAK_INSTALL_ACK_MISSING")
    if drops and any((item["dropped"] or 0) > 0 for item in drops):
        _add_issue(issues, "PROBE_DROPPED_EVENTS")

    duplicate_ordinals = [ordinal for ordinal, count in Counter(
        item[0] for item in callback_ordinals).items() if count > 1]
    if duplicate_ordinals:
        _add_issue(issues, "CALLBACK_ORDINAL_DUPLICATE", ordinals=sorted(duplicate_ordinals))
    groups = _group_fields(field_records, issues)
    causal = _causal_correlations(groups, entries, lifecycles, issues)
    direct = _direct_break_report(direct_events, issues)

    field_counts = Counter(record["field_id"] for record in field_records)
    unresolved_counts = Counter(field_id for group in groups
                                for field_id in group["unresolved_field_ids"])
    actual_variant_count = field_counts.get(0x3EC, 0)
    old_ec3_count = field_counts.get(0xEC3, 0)
    phase_field_counts = Counter(record["phase"] for record in field_records)
    source_layout_count = sum(record["source_layout_complete"] for record in field_records)
    endpoint_count = sum(group["latest_endpoint_identity_verified"] for group in groups)
    semantic_count = sum(group["semantic_endpoint_complete"] for group in groups)
    all_input_readable = all(record["input16_readable"] for record in field_records)
    all_context_readable = all(record["context_word_readable"] for record in field_records)

    incomplete_reasons: list[str] = []
    if len(field_records) != len(EXPECTED_FIELD_IDS) * len(groups) or not groups:
        incomplete_reasons.append("FIELD_EVENT_COUNT_OR_GROUP_COUNT_INCOMPLETE")
    if any(group["missing_field_ids"] or group["duplicate_field_ids"] for group in groups):
        incomplete_reasons.append("FIELD_SET_INCOMPLETE")
    if unresolved_counts:
        incomplete_reasons.append("FIELD_LOCAL_UNRESOLVED")
    if semantic_count != len(groups):
        incomplete_reasons.append("DUMMY_OR_LOCAL_LAYOUT_CANNOT_COMPLETE_ENDPOINT")
    if len(causal) != len(entries) or not all(item["causal_local_evidence"] for item in causal):
        incomplete_reasons.append("FIELD_TO_COMMAND_ENTRY_CAUSAL_CHAIN_PARTIAL")
    if any(not item["layout_continuity_verified"] for item in causal):
        incomplete_reasons.append("FIELD_ENTRY_LAYOUT_CONTINUITY_PARTIAL")
    if not direct or not all(item["verified"] for item in direct):
        incomplete_reasons.append("DIRECT_BREAK_CALLER_COVERAGE_INCOMPLETE")
    if actual_variant_count == 0 or old_ec3_count:
        incomplete_reasons.append("VARIANT_FIELD_ID_MAPPING_UNVERIFIED")
    if drops and any((item["dropped"] or 0) > 0 for item in drops):
        incomplete_reasons.append("PROBE_DROPPED_EVENTS")
    # These are intentional hard boundaries of this passive observer.
    incomplete_reasons.extend([
        "NO_SUBMIT_OR_QUEUE_RECEIPT",
        "OUTGOING_TRANSPORT_NOT_ASSOCIATED",
        "DECISION_COUNTRY_UNKNOWN",
        "BUSINESS_RESULT_UNKNOWN",
    ])
    # Preserve order while removing duplicate reason names.
    incomplete_reasons = list(dict.fromkeys(incomplete_reasons))

    health_events = [event for event in []]  # populated below from compact pass if needed
    callback_summary = {
        "observed": len(callback_ordinals),
        "unique": len(set(item[0] for item in callback_ordinals)),
        "duplicate_ordinals": sorted(duplicate_ordinals),
        "min": min((item[0] for item in callback_ordinals), default=None),
        "max": max((item[0] for item in callback_ordinals), default=None),
        "line_order_used_for_correlation": False,
    }
    report: dict[str, Any] = {
        "schema": "alliance-field-read-validation/1",
        "date": "2026-10-13",
        "runtime_this_turn": True,
        "fixture_only": fixture_only,
        "game_started_by_validator": False,
        "injection_performed_by_validator": False,
        "installation": str(installation_path),
        "manifest": str(manifest_path),
        "probe": str(probe_path),
        "observation_report": {
            "path": str(observation_path) if observation_path else None,
            "log_start_offset": observation.get("log_start_offset") if isinstance(observation, Mapping) else None,
            "log_end_offset": observation.get("log_end_offset") if isinstance(observation, Mapping) else None,
            "status": "bounded_slice_used" if isinstance(observation, Mapping) else "unknown",
        },
        "identity": identity,
        "session_check": {
            "installation_session": session_id,
            "mismatch_count": len(session_mismatches),
            "mismatches": session_mismatches[:32],
            "acknowledgements": sorted(acknowledgements),
            "required_acknowledgements": sorted(REQUIRED_ACKS),
        },
        "event_counts": dict(counts),
        "phase_event_counts": dict(phase_counts),
        "phase_field_counts": dict(phase_field_counts),
        "callback_order": callback_summary,
        "field_mapping": {
            str(field_id): {"field_hex": hex(field_id), **meaning}
            for field_id, meaning in FIELD_LAYOUT.items()
        },
        "field_reads": {
            "total": len(field_records),
            "expected_field_ids": [hex(field_id) for field_id in EXPECTED_FIELD_IDS],
            "counts_by_id": {hex(field_id): count for field_id, count in sorted(field_counts.items())},
            "expected_each_count": len(groups),
            "actual_variant_field_0x3ec_count": actual_variant_count,
            "legacy_mislabel_0xec3_count": old_ec3_count,
            "source_layout_complete_count": source_layout_count,
            "source_layout_complete": source_layout_count == len(field_records),
            "input16_all_readable": all_input_readable,
            "context_all_readable": all_context_readable,
            "group_count": len(groups),
            "field_set_complete_group_count": sum(group["field_set_complete"] for group in groups),
            "field_decode_complete_group_count": sum(group["field_decode_complete"] for group in groups),
            "latest_endpoint_identity_verified_group_count": endpoint_count,
            "semantic_endpoint_complete_group_count": semantic_count,
            "unresolved_field_counts": {hex(field_id): count for field_id, count in sorted(unresolved_counts.items())},
            "dummy_source_snapshot_group_count": sum(bool(group["dummy_source_callbacks"]) for group in groups),
            "groups": groups,
        },
        "field_to_command_entry": {
            "count": len(causal),
            "causal_local_evidence_count": sum(item["causal_local_evidence"] for item in causal),
            "same_sequence_used_for_correlation": False,
            "outgoing_transport_associated": False,
            "submit_verified": False,
            "records": causal,
        },
        "direct_break": {
            "known_static_caller_count": len(EXPECTED_CALLER_RETURN_RVA),
            "observed_count": len(direct),
            "verified_count": sum(item["verified"] for item in direct),
            "decision_country_verified": False,
            "caller_source": "unknown",
            "records": direct,
        },
        "drops": drops,
        "issues": issues,
        "global_incomplete_reasons": incomplete_reasons,
        "acceptance_gate": False,
        "status": "observed_incomplete" if field_records else "no_field_runtime_evidence",
        "stage_status": {
            "field_read_observation": "verified" if field_records and not any(
                group["missing_field_ids"] for group in groups) else "incomplete",
            "field_semantic_decode": "incomplete" if unresolved_counts else "verified",
            "field_to_command_local_causality": (
                "verified" if causal and all(item["layout_continuity_verified"] for item in causal)
                else "partial" if causal else "unknown"),
            "direct_break_caller_identity": "verified" if direct and all(item["verified"] for item in direct) else "incomplete",
            "serialization": "unknown",
            "queue_submit": "unknown",
            "decision_country": "unknown",
            "business_result": "unknown",
        },
        "evidence_limits": [
            "Field events are pre-return passive observations; no authority or mutation is inferred.",
            "Dummy --- snapshots and local matched layouts are retained but do not complete endpoint identity.",
            "The 0x3ec field is variant38; 0xec3 is not accepted as its alias.",
            "Callback ordinals establish local order only. Protocol sequence integers are not used as outgoing correlations.",
            "No submission, queue delivery, decision country, or business result is claimed.",
        ],
    }
    return report


def write_json_exclusive(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def render_report(report: Mapping[str, Any]) -> str:
    identity = report.get("identity", {})
    fields = report.get("field_reads", {})
    direct = report.get("direct_break", {})
    causal = report.get("field_to_command_entry", {})
    reasons = report.get("global_incomplete_reasons", [])
    phase_counts = report.get("phase_field_counts", {})
    mapping = report.get("field_mapping", {})
    unresolved = fields.get("unresolved_field_counts", {})
    lines = [
        "# r16c 字段读取离线验证（2026-10-13）",
        "",
        f"实验 `{identity.get('experiment_id')}`，session `{identity.get('session_id')}`，PID `{identity.get('pid')}`。",
        f"`runtime_this_turn=true`；验证器未启动游戏、未注入。状态：**{report.get('status')}**，acceptance gate：**false**。",
        "",
        "## 读取覆盖",
        "",
        f"共 `{fields.get('total', 0)}` 条 field read，分组 `{fields.get('group_count', 0)}` 个；阶段计数：`{phase_counts}`。",
        f"每组九字段完整集合 `{fields.get('field_set_complete_group_count', 0)}`，source layout 完整 `{fields.get('source_layout_complete_count', 0)}`，最新非 dummy endpoint 形状 `{fields.get('latest_endpoint_identity_verified_group_count', 0)}`。",
        f"`0x3ec`（`variant38`）出现 `{fields.get('actual_variant_field_0x3ec_count', 0)}` 次；错误别名 `0xec3` 出现 `{fields.get('legacy_mislabel_0xec3_count', 0)}` 次。",
        f"字段局部未解析：`{unresolved}`；dummy 快照仅作为局部记录保留，未用于 endpoint 完整性。",
        "",
        "字段映射：" + ", ".join(
            f"`{key}`→`{value.get('name')}@{value.get('offset')}`"
            for key, value in mapping.items()
        ) + "。",
        "",
        "## 局部因果链",
        "",
        f"发现 `{causal.get('causal_local_evidence_count', 0)}/{causal.get('count', 0)}` 条 field decode→clone→command entry 的本地 callback 链；完整 layout 连续性按记录单独核对。只记录 action/node/layout/callback 证据；未使用 same protocol sequence 关联 outgoing，也未声称 submit。",
        "",
        "## direct break",
        "",
        f"观察 `{direct.get('observed_count', 0)}` 条，已核对已知七 caller/E8 目标 `{direct.get('verified_count', 0)}` 条；owner_is_country、input_canonical、native_flag 均原样保留。decision country 与 caller source 仍 unknown。",
        "",
        "## 未完成阶段",
        "",
        "- " + "\n- ".join(str(reason) for reason in reasons),
        "",
        "序列化、队列提交、决策主体和业务结果均保持 unknown；这是被动 field reader 的边界。",
        "",
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--observation-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fixture-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = validate_files(
            args.installation, args.manifest, args.probe,
            observation_report_path=args.observation_report,
            fixture_only=args.fixture_only,
        )
        output = args.output or args.installation.parent / "r16c-field-read-validation.json"
        markdown = args.report or output.with_suffix(".md")
        write_json_exclusive(output, report)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        with markdown.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render_report(report))
        print(json.dumps({
            "status": report["status"],
            "acceptance_gate": report["acceptance_gate"],
            "field_events": report["field_reads"]["total"],
            "field_groups": report["field_reads"]["group_count"],
            "causal_local_chains": report["field_to_command_entry"]["causal_local_evidence_count"],
            "direct_break_verified": report["direct_break"]["verified_count"],
            "output": str(output),
            "report": str(markdown),
        }, ensure_ascii=False))
        return 0
    except (InputError, OSError) as exc:
        print(f"validate_alliance_field_reads: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
