#!/usr/bin/env python3
"""Stream bounded FRA/SAV Military Access relation evidence from EU4 saves.

The scanner reuses :mod:`inspect_dissolve_save_pair`'s streaming container and
bounded country capture.  It retains only the FRA and SAV country blocks, the
serialized FRA->SAV/SAV->FRA ``active_relations`` entries, the FRA/SAV
``diplomats`` entries, and fields whose serialized names identify military_access or
military access state.  A save is hashed in chunks; the 38 MB save text is never
loaded as one string.  Unknown relation fields are retained verbatim so the
tool reports the game format instead of assigning a meaning to an unobserved
field.

Pass one or more saves by repeating ``--save``.  The output directory must be
fresh so a later comparison cannot overwrite an earlier evidence package::

    python work/inspect_military_access_save_pair.py \
        --save "...\\llm_diplomacy_military_access_sav_before.eu4" \
        --save "...\\llm_diplomacy_military_access_sav_active.eu4" \
        --save "...\\llm_diplomacy_military_access_sav_revoked.eu4" \
        --label before --label active --label revoked \
        --output-dir work/runtime/r32-military-access-save-effects-20261015-001

Later runs can repeat ``--save`` for the active, 35-day, and stopped saves and
use a different ``--output-dir``.  Values are reported as the raw serialized
strings; this tool does not infer whether a field is a boolean, relation
strength, date, or engine scale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from work import inspect_dissolve_save_pair as bounded
except ModuleNotFoundError:  # direct ``python work/<script>.py`` invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work import inspect_dissolve_save_pair as bounded


TARGET_TAGS = ("FRA", "SAV")
PAIR = frozenset(TARGET_TAGS)
GLOBAL_RELATION_PAIRS = (
    frozenset(("FRA", "SAV")),
    frozenset(("FRA", "BUR")),
    frozenset(("FRA", "GEN")),
    frozenset(("FRA", "CAS")),
)
MILITARY_ACCESS_TOKENS = (
    "military_access",
    "militaryaccess",
    "military",
    "access",
)
MAX_MILITARY_ACCESS_RECORDS = 256
MAX_MILITARY_ACCESS_CAPTURE = 256 * 1024
CONSTRUCTION_RE = re.compile(r"^\s*diplomacy_construction\s*=\s*\{")
RELATION_RE = re.compile(r"^\s*military_access\s*=\s*\{")
MAX_RELATION_CAPTURE = 64 * 1024
FREEENVOY_RE = re.compile(r"free[_]?envoy", re.IGNORECASE)
MAX_FREEENVOY_MATCHES = 128
MAX_FREEENVOY_LINE = 2048
RELATION_EVIDENCE_TOKENS = (
    "opinion",
    "penalty",
    "modifier",
    "cached_sum",
    "expiry",
    "truce",
    "last_war",
    "attitude",
    "start_date",
    "enforce_peace",
)

# Configure only this process's imported scanner.  The existing module on disk
# remains unchanged and all captures stay within its 8 MiB country/256 KiB
# alliance limits.
bounded.TARGET_TAGS = TARGET_TAGS
bounded.PAIR = PAIR
bounded.COUNTRY_RE = re.compile(r"^\s*(FRA|SAV)\s*=\s*\{")


def _is_military_access_field(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in MILITARY_ACCESS_TOKENS)


def _country_entries(capture: bounded.CountryCapture) -> list[bounded.Entry]:
    open_index = capture.text.find("{")
    body = bounded.extract_block(capture.text, open_index)
    return bounded.top_level_entries(body)


def _scalar_text(value: Any) -> str | None:
    """Return one serialized scalar while retaining duplicate values elsewhere."""

    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    return bounded.unquote(str(value))


def _military_access_constructions(
    entries: list[bounded.Entry], path: str = ""
) -> tuple[list[dict[str, Any]], list[str]]:
    """Find bounded diplomacy-construction records for the FRA/SAV pair.

    EU4 serializes the outbound Military Access operation as a
    ``diplomacy_construction`` block nested below a country province.  The
    block has ``action_token=military_accessaction`` and actor/recipient fields; the
    surrounding country block alone does not name the relation.  Walk only
    the already bounded FRA/SAV country capture and retain the complete raw
    block for every matching pair record.
    """

    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    for index, entry in enumerate(entries, 1):
        entry_path = f"{path}.{entry.key}" if path else entry.key
        if entry.body is None:
            continue
        try:
            parsed = bounded.parse_field_body(entry.body)
        except Exception as exc:  # defensive: scanner parser already bounds body
            unknown.append(f"{entry_path}:parse_error:{exc}")
            parsed = {"fields": {}, "blocks": [], "unknown": []}
        fields = parsed.get("fields", {})
        action_token = _scalar_text(fields.get("action_token"))
        actor = _scalar_text(fields.get("actor"))
        recipient = _scalar_text(fields.get("recipient"))
        action_lower = action_token.lower() if action_token is not None else ""
        is_military_access = (
            bool(action_token)
            and ("military" in action_lower and "access" in action_lower)
            and frozenset((actor, recipient)) == PAIR
        )
        if is_military_access:
            if len(records) >= MAX_MILITARY_ACCESS_RECORDS:
                unknown.append("military_access_record_limit_reached")
            else:
                records.append(
                    {
                        "path": entry_path,
                        "entry_key": entry.key,
                        "fields": fields,
                        "blocks": parsed.get("blocks", []),
                        "unknown": parsed.get("unknown", []),
                        "raw_body": entry.body,
                    }
                )
        try:
            children = bounded.top_level_entries(entry.body)
        except bounded.SaveParseError as exc:
            unknown.append(f"{entry_path}:children_parse_error:{exc}")
            continue
        child_records, child_unknown = _military_access_constructions(children, entry_path)
        records.extend(child_records[: max(0, MAX_MILITARY_ACCESS_RECORDS - len(records))])
        unknown.extend(child_unknown)
        if len(records) >= MAX_MILITARY_ACCESS_RECORDS:
            # Continue no deeper than necessary; all retained data is bounded.
            break
    return records, unknown


def _scan_global_military_access_constructions(
    path: Path, source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Stream the root/province construction records for the FRA/SAV pair.

    In the observed save format ``diplomacy_construction`` is serialized under
    province data, outside the country blocks.  A second bounded pass therefore
    collects only those small blocks; it never materializes the gamestate.
    """

    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    line_count = 0
    active: list[str] | None = None
    start_line: int | None = None
    depth = 0
    bytes_captured = 0
    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            if active is None:
                if not CONSTRUCTION_RE.match(line):
                    continue
                active = [line]
                start_line = line_number
                bytes_captured = len(line.encode("utf-8", errors="replace"))
                depth = bounded.brace_delta(line)
                if depth <= 0:
                    unknown.append(f"line_{line_number}:construction_unclosed")
                    active = None
                continue
            active.append(line)
            bytes_captured += len(line.encode("utf-8", errors="replace"))
            if bytes_captured > MAX_MILITARY_ACCESS_CAPTURE:
                unknown.append(f"line_{start_line}:construction_over_limit")
                active = None
                depth = 0
                continue
            depth += bounded.brace_delta(line)
            if depth != 0:
                continue
            text = "".join(active)
            try:
                body = bounded.extract_block(text, text.find("{"))
                parsed = bounded.parse_field_body(body)
            except bounded.SaveParseError as exc:
                unknown.append(f"line_{start_line}:construction_parse_error:{exc}")
                active = None
                depth = 0
                continue
            fields = parsed.get("fields", {})
            action_token = _scalar_text(fields.get("action_token"))
            actor = _scalar_text(fields.get("actor"))
            recipient = _scalar_text(fields.get("recipient"))
            action_lower = action_token.lower() if action_token is not None else ""
            if (bool(action_token) and "military" in action_lower and "access" in action_lower
                    and frozenset((actor, recipient)) == PAIR):
                if len(records) < MAX_MILITARY_ACCESS_RECORDS:
                    records.append({
                        "line_start": start_line,
                        "entry_key": "diplomacy_construction",
                        "actor": actor,
                        "recipient": recipient,
                        "action_token": action_token,
                        "fields": fields,
                        "blocks": parsed.get("blocks", []),
                        "unknown": parsed.get("unknown", []),
                        "raw_body": body,
                    })
                else:
                    unknown.append("military_access_record_limit_reached")
            active = None
            depth = 0
            start_line = None
            bytes_captured = 0
    if active is not None:
        unknown.append(f"line_{start_line}:construction_block_incomplete")
    return records, unknown, {"line_count": line_count, "complete": active is None}


def _scan_global_military_access_relations(
    path: Path, source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Stream the serialized diplomacy ``military_access`` relation blocks.

    These blocks are separate from province ``diplomacy_construction`` records:
    a matching block has ``first=FRA``/``second=SAV`` and relation dates.  The
    complete bounded body is retained so before/active/revoked comparisons can
    show the engine's exact fields without assigning a semantic interpretation.
    """

    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    line_count = 0
    active: list[str] | None = None
    start_line: int | None = None
    depth = 0
    bytes_captured = 0
    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            if active is None:
                if not RELATION_RE.match(line):
                    continue
                active = [line]
                start_line = line_number
                bytes_captured = len(line.encode("utf-8", errors="replace"))
                depth = bounded.brace_delta(line)
                if depth <= 0:
                    unknown.append(f"line_{line_number}:relation_unclosed")
                    active = None
                continue
            active.append(line)
            bytes_captured += len(line.encode("utf-8", errors="replace"))
            if bytes_captured > MAX_RELATION_CAPTURE:
                unknown.append(f"line_{start_line}:relation_over_limit")
                active = None
                depth = 0
                continue
            depth += bounded.brace_delta(line)
            if depth != 0:
                continue
            text = "".join(active)
            try:
                body = bounded.extract_block(text, text.find("{"))
                parsed = bounded.parse_field_body(body)
            except bounded.SaveParseError as exc:
                unknown.append(f"line_{start_line}:relation_parse_error:{exc}")
                active = None
                depth = 0
                continue
            fields = parsed.get("fields", {})
            first = _scalar_text(fields.get("first"))
            second = _scalar_text(fields.get("second"))
            relation_pair = frozenset((first, second))
            if relation_pair in GLOBAL_RELATION_PAIRS:
                if len(records) < MAX_MILITARY_ACCESS_RECORDS:
                    records.append({
                        "line_start": start_line,
                        "entry_key": "military_access",
                        "first": first,
                        "second": second,
                        "pair": [first, second],
                        "fields": fields,
                        "blocks": parsed.get("blocks", []),
                        "unknown": parsed.get("unknown", []),
                        "raw_body": body,
                    })
                else:
                    unknown.append("military_access_relation_limit_reached")
            active = None
            depth = 0
            start_line = None
            bytes_captured = 0
    if active is not None:
        unknown.append(f"line_{start_line}:relation_block_incomplete")
    return records, unknown, {"line_count": line_count, "complete": active is None}


def _scan_freeenvoy_tokens(
    path: Path, source: dict[str, Any]
) -> dict[str, Any]:
    """Record literal ``freeenvoy`` fields without loading the save.

    The observed game files may expose free-envoy bookkeeping under a different
    name.  This scan therefore reports literal matches only and keeps the raw
    line as evidence; diplomat ``action`` fields remain reported separately.
    """

    matches: list[dict[str, Any]] = []
    match_count = 0
    line_count = 0
    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            if not FREEENVOY_RE.search(line):
                continue
            match_count += 1
            if len(matches) < MAX_FREEENVOY_MATCHES:
                matches.append(
                    {
                        "line": line_number,
                        "text": line.rstrip("\r\n")[:MAX_FREEENVOY_LINE],
                    }
                )
    return {
        "pattern": r"free[_]?envoy",
        "match_count": match_count,
        "matches": matches,
        "line_count": line_count,
        "complete": True,
    }


def _relation_evidence_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Select raw relation penalty/date/state fields without interpreting them."""

    return {
        key: value
        for key, value in fields.items()
        if any(token in key.lower() for token in RELATION_EVIDENCE_TOKENS)
    }


def _relation_summary(
    capture: bounded.CountryCapture | None, other: str
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "present": False,
        "country_block_complete": bool(capture and capture.complete),
        "active_relations_block_count": 0,
        "entries": [],
        "unknown": [],
    }
    if capture is None:
        result["unknown"].append("country_block_not_found")
        return result
    if not capture.complete:
        result["unknown"].append("country_block_incomplete")
        return result
    try:
        entries = _country_entries(capture)
    except bounded.SaveParseError as exc:
        result["unknown"].append(f"country_parse_error: {exc}")
        return result

    relation_blocks = [
        entry.body
        for entry in entries
        if entry.key == "active_relations" and entry.body is not None
    ]
    result["active_relations_block_count"] = len(relation_blocks)
    for relation_body in relation_blocks:
        try:
            relation_entries = bounded.top_level_entries(relation_body)
        except bounded.SaveParseError as exc:
            result["unknown"].append(f"active_relations_parse_error: {exc}")
            continue
        for entry in relation_entries:
            if entry.key != other or entry.body is None:
                continue
            parsed = bounded.parse_field_body(entry.body)
            result["present"] = True
            result["entries"].append(
                {
                    "fields": parsed["fields"],
                    "evidence_fields": _relation_evidence_fields(parsed["fields"]),
                    "blocks": parsed["blocks"],
                    "unknown": parsed["unknown"],
                    "raw_body": entry.body,
                }
            )
            result["unknown"].extend(parsed["unknown"])
    return result


def _diplomat_entries(
    entries: list[bounded.Entry],
) -> tuple[list[dict[str, Any]], list[str]]:
    diplomats: list[dict[str, Any]] = []
    unknown: list[str] = []
    for entry in entries:
        if entry.key != "diplomats" or entry.body is None:
            continue
        try:
            envoy_entries = bounded.top_level_entries(entry.body)
        except bounded.SaveParseError as exc:
            unknown.append(f"diplomats_parse_error: {exc}")
            continue
        for envoy in envoy_entries:
            if envoy.body is None:
                continue
            parsed = bounded.parse_field_body(envoy.body)
            diplomats.append(
                {
                    "entry_key": envoy.key,
                    "fields": parsed["fields"],
                    "blocks": parsed["blocks"],
                    "unknown": parsed["unknown"],
                    "raw_body": envoy.body,
                }
            )
            unknown.extend(parsed["unknown"])
    return diplomats, unknown


def _country_summary(
    tag: str, capture: bounded.CountryCapture | None, other: str
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tag": tag,
        "capture": {
            "found": capture is not None,
            "start_line": capture.start_line if capture else None,
            "end_line": capture.end_line if capture else None,
            "complete": capture.complete if capture else False,
            "bytes_captured": capture.bytes_captured if capture else 0,
        },
        "military_access_related_fields": {},
        "military_access_constructions": [],
        "diplomats": [],
        "diplomat_action_records": [],
        "diplomat_records_without_action": [],
        "active_relations": {},
        "unknown": [],
    }
    if capture is None:
        summary["unknown"].append(f"country_{tag}_not_found")
        return summary
    if not capture.complete:
        summary["unknown"].append(f"country_{tag}_capture_incomplete")
        return summary
    try:
        entries = _country_entries(capture)
        fields, _ = bounded.flatten_entries(entries)
    except bounded.SaveParseError as exc:
        summary["unknown"].append(f"country_{tag}_parse_error: {exc}")
        return summary

    summary["military_access_related_fields"] = {
        key: value for key, value in fields.items() if _is_military_access_field(key)
    }
    constructions, construction_unknown = _military_access_constructions(entries)
    summary["military_access_constructions"] = constructions
    summary["unknown"].extend(construction_unknown)
    diplomats, diplomat_unknown = _diplomat_entries(entries)
    summary["diplomats"] = diplomats
    summary["diplomat_action_records"] = [
        {
            "entry_key": diplomat.get("entry_key"),
            "action": diplomat.get("fields", {}).get("action"),
            "fields": diplomat.get("fields", {}),
        }
        for diplomat in diplomats
        if "action" in diplomat.get("fields", {})
    ]
    summary["diplomat_records_without_action"] = [
        {
            "entry_key": diplomat.get("entry_key"),
            "fields": diplomat.get("fields", {}),
            "raw_body": diplomat.get("raw_body", ""),
        }
        for diplomat in diplomats
        if "action" not in diplomat.get("fields", {})
    ]
    summary["unknown"].extend(diplomat_unknown)
    relation = _relation_summary(capture, other)
    summary["active_relations"][f"{tag}->{other}"] = relation
    summary["unknown"].extend(
        f"{tag}->{other}:{item}" for item in relation["unknown"]
    )
    return summary


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _infer_label(path: Path, index: int) -> str:
    """Choose a display label without inferring a relation state from data."""

    lowered = path.name.lower()
    for token, label in (
        ("before", "before"),
        ("active", "active"),
        ("proclaim", "active"),
        ("start", "active"),
        ("revok", "revoked"),
        ("stop", "revoked"),
        ("return", "revoked"),
    ):
        if token in lowered:
            return label
    return f"snapshot-{index + 1}"


def scan_save(path: Path, label: str | None = None, index: int = 0) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    global_constructions, construction_unknown, construction_scan = (
        _scan_global_military_access_constructions(path, source)
    )
    global_relations, relation_unknown, relation_scan = (
        _scan_global_military_access_relations(path, source)
    )
    freeenvoy_scan = _scan_freeenvoy_tokens(path, source)

    unknown: list[str] = []
    countries: dict[str, Any] = {}
    for tag, other in (("FRA", "SAV"), ("SAV", "FRA")):
        countries[tag] = _country_summary(
            tag, scanner.country_captures.get(tag), other
        )
        unknown.extend(f"{tag}:{item}" for item in countries[tag]["unknown"])
    if scanner.duplicate_country_tags:
        unknown.extend(
            f"duplicate_country_tag:{tag}" for tag in scanner.duplicate_country_tags
        )
    if not scanner.countries_found:
        unknown.append("countries_block_not_found")
    elif not scanner.countries_complete:
        unknown.append("countries_block_incomplete")
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    unknown.extend(f"global_military_access:{item}" for item in construction_unknown)
    unknown.extend(f"global_military_access_relation:{item}" for item in relation_unknown)
    relation_pairs: dict[str, list[dict[str, Any]]] = {}
    for relation in global_relations:
        first = relation.get("first")
        second = relation.get("second")
        key = f"{first}->{second}"
        relation_pairs.setdefault(key, []).append(relation)

    return {
        "label": label or _infer_label(path, index),
        "source": source,
        "metadata": {
            "first_line": scanner.header_line,
            "date": scanner.save_date,
        },
        "parse": {
            "gamestate_line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "countries_block_found": scanner.countries_found,
            "countries_block_complete": scanner.countries_complete,
            "diplomacy_block_found": scanner.diplomacy_found,
            "diplomacy_block_complete": scanner.diplomacy_complete,
            "alliance_blocks_scanned": scanner.alliance_blocks_seen,
            "military_access_construction_scan": construction_scan,
            "military_access_relation_scan": relation_scan,
            "freeenvoy_scan": freeenvoy_scan,
            "unknown": unknown,
        },
        "countries": countries,
        "military_access_constructions": global_constructions,
        "military_access_relations": global_relations,
        "military_access_relation_pairs": relation_pairs,
        "freeenvoy_records": freeenvoy_scan,
        "alliance_pair_entry_count": len(scanner.alliance_pair_entries),
    }


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    missing = object()
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key, missing)
        new = after.get(key, missing)
        if old == new:
            continue
        changes.append(
            {
                "field": key,
                "kind": "added" if old is missing else "removed" if new is missing else "changed",
                "before": None if old is missing else old,
                "after": None if new is missing else new,
            }
        )
    return changes


def _relation_fields(relation: dict[str, Any]) -> dict[str, Any] | None:
    entries = relation.get("entries", [])
    if not isinstance(entries, list) or len(entries) != 1:
        return None
    fields = entries[0].get("fields")
    return fields if isinstance(fields, dict) else None


def _comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    country_changes: dict[str, Any] = {}
    for tag in TARGET_TAGS:
        old = before["countries"][tag]
        new = after["countries"][tag]
        country_changes[tag] = {
            "military_access_related_field_changes": _field_changes(
                old.get("military_access_related_fields", {}), new.get("military_access_related_fields", {})
            ),
            "diplomats": {
                "before_count": len(old.get("diplomats", [])),
                "after_count": len(new.get("diplomats", [])),
                "before_entries": old.get("diplomats", []),
                "after_entries": new.get("diplomats", []),
            },
            "diplomat_action_records": {
                "before": old.get("diplomat_action_records", []),
                "after": new.get("diplomat_action_records", []),
            },
            "military_access_constructions": {
                "before_count": len(old.get("military_access_constructions", [])),
                "after_count": len(new.get("military_access_constructions", [])),
                "before_entries": old.get("military_access_constructions", []),
                "after_entries": new.get("military_access_constructions", []),
            },
        }
        for direction in (f"{tag}->{('SAV' if tag == 'FRA' else 'FRA')}",):
            old_relation = old["active_relations"].get(direction, {})
            new_relation = new["active_relations"].get(direction, {})
            old_fields = _relation_fields(old_relation)
            new_fields = _relation_fields(new_relation)
            country_changes[tag]["active_relations"] = {
                direction: {
                    "before_present": old_relation.get("present"),
                    "after_present": new_relation.get("present"),
                    "before_entry_count": len(old_relation.get("entries", [])),
                    "after_entry_count": len(new_relation.get("entries", [])),
                    "field_changes": (
                        _field_changes(old_fields, new_fields)
                        if old_fields is not None and new_fields is not None
                        else []
                    ),
                    "unknown": [] if old_fields is not None and new_fields is not None
                    else ["field_diff_requires_exactly_one_entry_per_side"],
                }
            }
    old_constructions = before.get("military_access_constructions", [])
    new_constructions = after.get("military_access_constructions", [])
    old_fields = old_constructions[0].get("fields") if len(old_constructions) == 1 else None
    new_fields = new_constructions[0].get("fields") if len(new_constructions) == 1 else None
    construction_changes = {
        "before_count": len(old_constructions),
        "after_count": len(new_constructions),
        "field_changes": (
            _field_changes(old_fields, new_fields)
            if isinstance(old_fields, dict) and isinstance(new_fields, dict)
            else []
        ),
        "before_entries": old_constructions,
        "after_entries": new_constructions,
        "unknown": [] if len(old_constructions) <= 1 and len(new_constructions) <= 1
        else ["field_diff_requires_at_most_one_pair_record_per_snapshot"],
    }
    old_relations = before.get("military_access_relations", [])
    new_relations = after.get("military_access_relations", [])
    old_relation_fields = old_relations[0].get("fields") if len(old_relations) == 1 else None
    new_relation_fields = new_relations[0].get("fields") if len(new_relations) == 1 else None
    relation_pair_keys = sorted(
        set(before.get("military_access_relation_pairs", {}))
        | set(after.get("military_access_relation_pairs", {}))
    )
    relation_pair_changes: dict[str, Any] = {}
    for pair_key in relation_pair_keys:
        old_pair = before.get("military_access_relation_pairs", {}).get(pair_key, [])
        new_pair = after.get("military_access_relation_pairs", {}).get(pair_key, [])
        old_pair_fields = old_pair[0].get("fields") if len(old_pair) == 1 else None
        new_pair_fields = new_pair[0].get("fields") if len(new_pair) == 1 else None
        relation_pair_changes[pair_key] = {
            "before_count": len(old_pair),
            "after_count": len(new_pair),
            "before_entries": old_pair,
            "after_entries": new_pair,
            "field_changes": (
                _field_changes(old_pair_fields, new_pair_fields)
                if isinstance(old_pair_fields, dict) and isinstance(new_pair_fields, dict)
                else []
            ),
            "unknown": [] if len(old_pair) <= 1 and len(new_pair) <= 1 else [
                "field_diff_requires_at_most_one_relation_per_direction"
            ],
        }
    relation_changes = {
        "before_count": len(old_relations),
        "after_count": len(new_relations),
        "field_changes": (
            _field_changes(old_relation_fields, new_relation_fields)
            if isinstance(old_relation_fields, dict) and isinstance(new_relation_fields, dict)
            else []
        ),
        "before_entries": old_relations,
        "after_entries": new_relations,
        "by_pair": relation_pair_changes,
        "unknown": [] if len(old_relations) <= 1 and len(new_relations) <= 1
        else ["field_diff_requires_at_most_one_pair_relation_per_snapshot"],
    }
    return {
        "from_label": before.get("label"),
        "to_label": after.get("label"),
        "before_source": before["source"]["sha256"],
        "after_source": after["source"]["sha256"],
        "military_access_constructions": construction_changes,
        "military_access_relations": relation_changes,
        "military_access_relation_pairs": relation_pair_changes,
        "countries": country_changes,
        "interpretation_guard": (
            "All values are raw serialized save fields. A missing field means "
            "absent from the captured FRA/SAV country, pair, or global diplomacy "
            "block only. diplomacy_construction is reported as an envoy-task "
            "record; it is not used as proof of the persisted relation. "
            "This report does not infer a global military_access state or causal "
            "meaning for last_war, truce, or spy_network changes."
        ),
    }


def build_payload(paths: list[Path], labels: list[str] | None = None) -> dict[str, Any]:
    if labels is not None and len(labels) != len(paths):
        raise ValueError("--label must be supplied once for every --save, or omitted")
    snapshots = [
        scan_save(path, labels[index] if labels is not None else None, index)
        for index, path in enumerate(paths)
    ]
    comparisons = [
        {
            "from_index": index,
            "to_index": index + 1,
            **_comparison(snapshots[index], snapshots[index + 1]),
        }
        for index in range(len(snapshots) - 1)
    ]
    payload: dict[str, Any] = {
        "tool": {
            "name": "inspect_military_access_save_pair.py",
            "version": 1,
            "scope": (
                "streaming gamestate scan; FRA/SAV country blocks, exact "
                "FRA<->SAV active_relations, diplomats, global Military Access "
                "relations for FRA/SAV, FRA/BUR, FRA/GEN and FRA/CAS, and raw relation evidence"
            ),
            "scanner_source": "work/inspect_dissolve_save_pair.py",
            "military_access_construction_source": (
                "second bounded gamestate pass; root/province "
                "diplomacy_construction blocks filtered by action_token and pair"
            ),
            "military_access_relation_source": (
                "bounded gamestate pass; diplomacy military_access blocks filtered "
                "by first/second country pair (FRA/SAV, FRA/BUR, FRA/GEN and FRA/CAS)"
            ),
            "freeenvoy_source": (
                "bounded line scan for literal freeenvoy/free_envoy tokens; "
                "raw diplomat action fields are retained separately"
            ),
        },
        "pair": ["FRA", "SAV"],
        "global_relation_pairs_checked": [
            ["FRA", "SAV"],
            ["FRA", "BUR"],
            ["FRA", "GEN"],
            ["FRA", "CAS"],
        ],
        "snapshot_labels": [snapshot["label"] for snapshot in snapshots],
        "snapshots": snapshots,
        "comparisons": comparisons,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload["integrity"] = {
        "canonical_payload_sha256": _sha256_bytes(canonical),
        "source_sha256": {
            str(path.resolve()): snapshot["source"]["sha256"]
            for path, snapshot in zip(paths, snapshots)
        },
    }
    return payload


def _format_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_report(payload: dict[str, Any], json_sha256: str) -> str:
    lines = [
        "# R32 Military Access 存档字段取证",
        "",
        "本报告由 `work/inspect_military_access_save_pair.py` 生成。扫描器流式读取 gamestate，"
        "保留 FRA/SAV 国家块、双方 `active_relations`、外交官原始条目、"
        "全局 `diplomacy.military_access` 关系块和 `diplomacy_construction` 任务块。"
        "全局关系块的 `first`→`second` 是报告中的方向；报告保留原始字段和值，不推测数值尺度。",
        "",
        f"`report.json` SHA-256：`{json_sha256}`",
        f"规范化载荷 SHA-256：`{payload['integrity']['canonical_payload_sha256']}`",
        "",
    ]
    for index, snapshot in enumerate(payload["snapshots"], 1):
        source = snapshot["source"]
        lines.extend([
            f"## 存档 {index}", "",
            f"- 标签：`{snapshot['label']}`",
            f"- 文件：`{source['path']}`",
            f"- SHA-256：`{source['sha256']}`",
            f"- 保存日期：`{snapshot['metadata']['date']}`",
            f"- 容器：`{source['container']}`；大小：`{source['size_bytes']}` 字节",
            f"- gamestate 行数：`{snapshot['parse']['gamestate_line_count']}`；括号平衡：`{snapshot['parse']['brace_balance_ok']}`",
            "",
            "### 全局 diplomacy.military_access",
            "",
        ])
        relations = snapshot.get("military_access_relations", [])
        if relations:
            for relation_index, relation in enumerate(relations, 1):
                lines.append(
                    f"- #{relation_index} 行 {relation.get('line_start')} "
                    f"`{relation.get('first')}→{relation.get('second')}`："
                    f"`{_format_value(relation.get('fields', {}))}`"
                )
        else:
            lines.append("- 未捕获检查方向 FRA→SAV、SAV→FRA、FRA→BUR、GEN→FRA、FRA→GEN、CAS→FRA 或 FRA→CAS 的全局 Military Access 条目。")
        pair_map = snapshot.get("military_access_relation_pairs", {})
        for pair_key in ("FRA->SAV", "SAV->FRA", "FRA->BUR", "GEN->FRA", "FRA->GEN", "CAS->FRA", "FRA->CAS"):
            lines.append(f"- 方向检查 `{pair_key}`：条目数 `{len(pair_map.get(pair_key, []))}`。")
        lines.extend([
            "",
            "### freeenvoy 字面字段与外交官记录",
            "",
        ])
        freeenvoy = snapshot.get("freeenvoy_records", {})
        lines.append(
            f"- 字面匹配 `freeenvoy`/`free_envoy`：`{freeenvoy.get('match_count', 0)}` 条；"
            "匹配行保存在 report.json。"
        )
        lines.append("- `diplomats` 条目及其 `action` 原始值：")
        for tag in TARGET_TAGS:
            action_records = snapshot["countries"][tag].get("diplomat_action_records", [])
            lines.append(f"  - `{tag}`：`{_format_value(action_records)}`")
        lines.append(
            "- `action` 字段缺失的外交官原始记录（作为 free-envoy 结构候选，"
            "不把字段缺失单独解释为引擎可用数）："
        )
        for tag in TARGET_TAGS:
            free_records = snapshot["countries"][tag].get("diplomat_records_without_action", [])
            lines.append(f"  - `{tag}`：`{_format_value(free_records)}`")
        lines.append("")
        lines.append("### FRA/SAV 国家块")
        lines.append("")
        for tag in TARGET_TAGS:
            country = snapshot["countries"][tag]
            lines.extend([
                f"#### {tag}", "",
                f"国家块：found=`{country['capture']['found']}`，complete=`{country['capture']['complete']}`，"
                f"捕获字节=`{country['capture']['bytes_captured']}`。",
                "",
                "国家块内 Military Access 相关字段（原始值）：",
            ])
            fields = country.get("military_access_related_fields", {})
            if fields:
                lines.extend(f"- `{key}` = `{value}`" for key, value in fields.items())
            else:
                lines.append("- 未捕获字段名包含 Military Access 标识的字段。")
            lines.append("active_relations 中的原始关系和惩罚字段：")
            for direction, relation in country.get("active_relations", {}).items():
                lines.append(
                    f"- `{direction}`：present=`{relation['present']}`，条目数=`{len(relation['entries'])}`"
                )
                for entry in relation.get("entries", []):
                    lines.append(f"  - 全部字段：`{_format_value(entry.get('fields', {}))}`")
                    lines.append(f"  - 关系证据字段：`{_format_value(entry.get('evidence_fields', {}))}`")
            lines.append("外交官任务/可用性原始条目：")
            for diplomat in country.get("diplomats", []):
                lines.append(f"- `{diplomat['entry_key']}`：`{_format_value(diplomat.get('fields', {}))}`")
            lines.append("国家块内 diplomacy_construction（仅任务记录，不作为关系存在证明）：")
            constructions = country.get("military_access_constructions", [])
            if constructions:
                for construction in constructions:
                    lines.append(f"- `{construction.get('path')}`：`{_format_value(construction.get('fields', {}))}`")
            else:
                lines.append("- 未捕获 FRA/SAV actor/recipient 的 Military Access 任务记录。")
            lines.append("")
        lines.append("全局 diplomacy_construction（仅外交官任务记录，不作为 Military Access 关系存在证明）：")
        constructions = snapshot.get("military_access_constructions", [])
        if constructions:
            for construction in constructions:
                lines.append(
                    f"- 行 {construction.get('line_start')} `{construction.get('actor')}→{construction.get('recipient')}` "
                    f"action_token=`{construction.get('action_token')}`：`{_format_value(construction.get('fields', {}))}`"
                )
        else:
            lines.append("- 未捕获目标方向的全局 Military Access diplomacy_construction。")
        lines.append("")
    if payload["comparisons"]:
        lines.extend(["## 相邻存档差异", ""])
        for comparison in payload["comparisons"]:
            lines.extend([
                f"### `{comparison['from_label']}` → `{comparison['to_label']}`",
                "",
            ])
            for pair_key, change in comparison.get("military_access_relation_pairs", {}).items():
                lines.append(
                    f"- 全局关系 `{pair_key}` 条目数：`{change['before_count']}` → `{change['after_count']}`。"
                )
                for field_change in change.get("field_changes", []):
                    lines.append(
                        f"  - `{field_change['field']}`：{_format_value(field_change['before'])} → "
                        f"{_format_value(field_change['after'])}"
                    )
            for tag, changes in comparison["countries"].items():
                lines.append(
                    f"- `{tag}` 外交官数量：`{changes['diplomats']['before_count']}` → "
                    f"`{changes['diplomats']['after_count']}`；action 原始记录见 report.json。"
                )
                for direction, relation_change in changes["active_relations"].items():
                    lines.append(
                        f"- `{direction}` active_relations 条目数："
                        f"`{relation_change['before_entry_count']}` → `{relation_change['after_entry_count']}`。"
                    )
                    for field_change in relation_change.get("field_changes", []):
                        lines.append(
                            f"  - `{field_change['field']}`：{_format_value(field_change['before'])} → "
                            f"{_format_value(field_change['after'])}"
                        )
            lines.append("")
    lines.extend([
        "## 解释边界", "",
        "报告只陈述存档中实际序列化的对象、字段和值。全局 `diplomacy.military_access` "
        "条目用于确认关系记录及其 `first`/`second` 方向；`diplomacy_construction` "
        "只表示外交官任务记录，不能单独证明关系存在。`active_relations` 中的 "
        "`opinion.modifier`、`cached_sum`、`truce`、`last_war` 等字段保持原名和原值，"
        "不推测其尺度、因果或撤销含义。没有匹配 `freeenvoy` 字面字段时，只能报告未发现该字面字段；"
        "外交官 `action` 条目仍作为独立原始记录保留。", "",
    ])
    return "\n".join(lines) + "\n"

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream FRA/SAV Military Access fields from one or more EU4 saves."
    )
    parser.add_argument(
        "--save", action="append", required=True, type=Path,
        help="save path; repeat for before/active/revoked snapshots",
    )
    parser.add_argument(
        "--label", action="append",
        help="optional label for each --save, in the same order (before/active/revoked)",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("work/runtime/r32-military-access-save-effects-20261015-001"),
        help="fresh evidence directory; an existing non-empty directory is rejected",
    )
    args = parser.parse_args()
    output_dir: Path = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"output directory is not fresh: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.label and len(args.label) != len(args.save):
        raise SystemExit("--label must be supplied once for every --save, or omitted")
    payload = build_payload(args.save, args.label or None)
    json_path = output_dir / "report.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = render_report(payload, bounded.sha256_file(json_path))
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    print(json_path)
    print(output_dir / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
