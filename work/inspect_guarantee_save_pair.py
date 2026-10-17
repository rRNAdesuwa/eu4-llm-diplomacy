#!/usr/bin/env python3
"""Stream bounded FRA/SAV Guarantee relation evidence from EU4 saves.

The scanner reuses :mod:`inspect_dissolve_save_pair`'s streaming container and
bounded country capture.  It retains only the FRA and SAV country blocks, the
serialized FRA->SAV/SAV->FRA ``active_relations`` entries, the FRA/SAV
``diplomats`` entries, and fields whose serialized names identify guarantee or
protection state.  A save is hashed in chunks; the 38 MB save text is never
loaded as one string.  Unknown relation fields are retained verbatim so the
tool reports the game format instead of assigning a meaning to an unobserved
field.

Pass one or more saves by repeating ``--save``.  The output directory must be
fresh so a later comparison cannot overwrite an earlier evidence package::

    python work/inspect_guarantee_save_pair.py \
        --save "...\\llm_diplomacy_guarantee_sav_before.eu4" \
        --save "...\\llm_diplomacy_guarantee_sav_active.eu4" \
        --save "...\\llm_diplomacy_guarantee_sav_revoked.eu4" \
        --label before --label active --label revoked \
        --output-dir work/runtime/r30-guarantee-save-effects-20261015-001

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
GUARANTEE_TOKENS = (
    "guarantee",
    "guaranteed",
    "guaranteeing",
)
MAX_GUARANTEE_RECORDS = 256
MAX_GUARANTEE_CAPTURE = 256 * 1024
CONSTRUCTION_RE = re.compile(r"^\s*diplomacy_construction\s*=\s*\{")
RELATION_RE = re.compile(r"^\s*guarantee\s*=\s*\{")
MAX_RELATION_CAPTURE = 64 * 1024

# Configure only this process's imported scanner.  The existing module on disk
# remains unchanged and all captures stay within its 8 MiB country/256 KiB
# alliance limits.
bounded.TARGET_TAGS = TARGET_TAGS
bounded.PAIR = PAIR
bounded.COUNTRY_RE = re.compile(r"^\s*(FRA|SAV)\s*=\s*\{")


def _is_guarantee_field(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in GUARANTEE_TOKENS)


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


def _guarantee_constructions(
    entries: list[bounded.Entry], path: str = ""
) -> tuple[list[dict[str, Any]], list[str]]:
    """Find bounded diplomacy-construction records for the FRA/SAV pair.

    EU4 serializes the outbound Guarantee operation as a
    ``diplomacy_construction`` block nested below a country province.  The
    block has ``action_token=guaranteeaction`` and actor/recipient fields; the
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
        is_guarantee = (
            action_token is not None
            and "guarantee" in action_token.lower()
            and frozenset((actor, recipient)) == PAIR
        )
        if is_guarantee:
            if len(records) >= MAX_GUARANTEE_RECORDS:
                unknown.append("guarantee_record_limit_reached")
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
        child_records, child_unknown = _guarantee_constructions(children, entry_path)
        records.extend(child_records[: max(0, MAX_GUARANTEE_RECORDS - len(records))])
        unknown.extend(child_unknown)
        if len(records) >= MAX_GUARANTEE_RECORDS:
            # Continue no deeper than necessary; all retained data is bounded.
            break
    return records, unknown


def _scan_global_guarantee_constructions(
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
            if bytes_captured > MAX_GUARANTEE_CAPTURE:
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
            if (action_token is not None and "guarantee" in action_token.lower()
                    and frozenset((actor, recipient)) == PAIR):
                if len(records) < MAX_GUARANTEE_RECORDS:
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
                    unknown.append("guarantee_record_limit_reached")
            active = None
            depth = 0
            start_line = None
            bytes_captured = 0
    if active is not None:
        unknown.append(f"line_{start_line}:construction_block_incomplete")
    return records, unknown, {"line_count": line_count, "complete": active is None}


def _scan_global_guarantee_relations(
    path: Path, source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Stream the serialized diplomacy ``guarantee`` relation blocks.

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
            if frozenset((first, second)) == PAIR:
                if len(records) < MAX_GUARANTEE_RECORDS:
                    records.append({
                        "line_start": start_line,
                        "entry_key": "guarantee",
                        "first": first,
                        "second": second,
                        "fields": fields,
                        "blocks": parsed.get("blocks", []),
                        "unknown": parsed.get("unknown", []),
                        "raw_body": body,
                    })
                else:
                    unknown.append("guarantee_relation_limit_reached")
            active = None
            depth = 0
            start_line = None
            bytes_captured = 0
    if active is not None:
        unknown.append(f"line_{start_line}:relation_block_incomplete")
    return records, unknown, {"line_count": line_count, "complete": active is None}


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
        "guarantee_related_fields": {},
        "guarantee_constructions": [],
        "diplomats": [],
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

    summary["guarantee_related_fields"] = {
        key: value for key, value in fields.items() if _is_guarantee_field(key)
    }
    constructions, construction_unknown = _guarantee_constructions(entries)
    summary["guarantee_constructions"] = constructions
    summary["unknown"].extend(construction_unknown)
    diplomats, diplomat_unknown = _diplomat_entries(entries)
    summary["diplomats"] = diplomats
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
        _scan_global_guarantee_constructions(path, source)
    )
    global_relations, relation_unknown, relation_scan = (
        _scan_global_guarantee_relations(path, source)
    )

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
    unknown.extend(f"global_guarantee:{item}" for item in construction_unknown)
    unknown.extend(f"global_guarantee_relation:{item}" for item in relation_unknown)

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
            "guarantee_construction_scan": construction_scan,
            "guarantee_relation_scan": relation_scan,
            "unknown": unknown,
        },
        "countries": countries,
        "guarantee_constructions": global_constructions,
        "guarantee_relations": global_relations,
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
            "guarantee_related_field_changes": _field_changes(
                old.get("guarantee_related_fields", {}), new.get("guarantee_related_fields", {})
            ),
            "diplomats": {
                "before_count": len(old.get("diplomats", [])),
                "after_count": len(new.get("diplomats", [])),
                "before_entries": old.get("diplomats", []),
                "after_entries": new.get("diplomats", []),
            },
            "guarantee_constructions": {
                "before_count": len(old.get("guarantee_constructions", [])),
                "after_count": len(new.get("guarantee_constructions", [])),
                "before_entries": old.get("guarantee_constructions", []),
                "after_entries": new.get("guarantee_constructions", []),
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
    old_constructions = before.get("guarantee_constructions", [])
    new_constructions = after.get("guarantee_constructions", [])
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
    old_relations = before.get("guarantee_relations", [])
    new_relations = after.get("guarantee_relations", [])
    old_relation_fields = old_relations[0].get("fields") if len(old_relations) == 1 else None
    new_relation_fields = new_relations[0].get("fields") if len(new_relations) == 1 else None
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
        "unknown": [] if len(old_relations) <= 1 and len(new_relations) <= 1
        else ["field_diff_requires_at_most_one_pair_relation_per_snapshot"],
    }
    return {
        "from_label": before.get("label"),
        "to_label": after.get("label"),
        "before_source": before["source"]["sha256"],
        "after_source": after["source"]["sha256"],
        "guarantee_constructions": construction_changes,
        "guarantee_relations": relation_changes,
        "countries": country_changes,
        "interpretation_guard": (
            "All values are raw serialized save fields. A missing field means "
            "absent from the captured FRA/SAV country, pair, or global diplomacy "
            "block only. diplomacy_construction is reported as an envoy-task "
            "record; it is not used as proof of the persisted relation. "
            "This report does not infer a global guarantee state or causal "
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
            "name": "inspect_guarantee_save_pair.py",
            "version": 1,
            "scope": (
                "streaming gamestate scan; FRA/SAV country blocks, exact "
                "FRA<->SAV active_relations, diplomats, and raw Guarantee fields"
            ),
            "scanner_source": "work/inspect_dissolve_save_pair.py",
            "guarantee_construction_source": (
                "second bounded gamestate pass; root/province "
                "diplomacy_construction blocks filtered by action_token and pair"
            ),
            "guarantee_relation_source": (
                "bounded gamestate pass; diplomacy guarantee blocks filtered "
                "by first/second country pair"
            ),
        },
        "pair": ["FRA", "SAV"],
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
        "# R30 Guarantee 存档字段取证",
        "",
        "本报告由 `work/inspect_guarantee_save_pair.py` 生成。扫描器流式读取 gamestate，"
        "保留 FRA/SAV 国家块、双方 `active_relations`、外交官条目、全局 diplomacy.guarantee "
        "关系块和 diplomacy_construction 外交官任务块。"
        "报告保留存档字段原始字符串，不将字段名或数值解释为未经验证的关系语义。",
        "",
        f"`report.json` SHA-256：`{json_sha256}`",
        f"规范化载荷 SHA-256：`{payload['integrity']['canonical_payload_sha256']}`",
        "",
    ]
    for index, snapshot in enumerate(payload["snapshots"], 1):
        source = snapshot["source"]
        lines.extend(
            [
                f"## 存档 {index}",
                "",
                f"- 标签：`{snapshot['label']}`",
                f"- 文件：`{source['path']}`",
                f"- SHA-256：`{source['sha256']}`",
                f"- 保存日期：`{snapshot['metadata']['date']}`",
                f"- 容器：`{source['container']}`；大小：`{source['size_bytes']}` 字节",
                f"- gamestate 行数：`{snapshot['parse']['gamestate_line_count']}`；"
                f"括号平衡：`{snapshot['parse']['brace_balance_ok']}`",
                "",
            ]
        )
        for tag in TARGET_TAGS:
            country = snapshot["countries"][tag]
            lines.append(f"### {tag}")
            lines.append("")
            lines.append(
                f"国家块：found=`{country['capture']['found']}`，"
                f"complete=`{country['capture']['complete']}`，"
                f"捕获字节=`{country['capture']['bytes_captured']}`。"
            )
            lines.append("")
            lines.append("Guarantee/保护相关字段（原始值）：")
            lines.append("")
            fields = country["guarantee_related_fields"]
            if fields:
                for key, value in fields.items():
                    lines.append(f"- `{key}` = `{value}`")
            else:
                lines.append("- 未在该国家块捕获到字段名包含 Guarantee/保护标识的字段。")
            lines.extend(["", "外交官条目：", ""])
            diplomats = country["diplomats"]
            if diplomats:
                for diplomat_index, diplomat in enumerate(diplomats, 1):
                    lines.append(
                        f"- #{diplomat_index} `{diplomat['entry_key']}`："
                        f"`{_format_value(diplomat['fields'])}`"
                    )
            else:
                lines.append("- 未捕获外交官条目。")
            lines.extend(["", "国家块内 Guarantee diplomacy_construction 条目：", ""])
            constructions = country["guarantee_constructions"]
            if constructions:
                for construction_index, construction in enumerate(constructions, 1):
                    lines.append(
                        f"- #{construction_index} `{construction['path']}`："
                        f"`{_format_value(construction['fields'])}`"
                    )
            else:
                lines.append("- 未在该国家块捕获 actor/recipient 为 FRA/SAV 且 action_token 含 Guarantee 的条目。")
            lines.extend(["", "双方 active_relations：", ""])
            for direction, relation in country["active_relations"].items():
                lines.append(
                    f"- `{direction}`：present=`{relation['present']}`，"
                    f"条目数=`{len(relation['entries'])}`"
                )
                for entry in relation["entries"]:
                    lines.append(f"  - 原始字段：`{_format_value(entry['fields'])}`")
            lines.append("")
        lines.append("Guarantee diplomacy_construction（全局省份块流式捕获）：")
        lines.append("")
        constructions = snapshot.get("guarantee_constructions", [])
        if constructions:
            for construction_index, construction in enumerate(constructions, 1):
                lines.append(
                    f"- #{construction_index} 行 {construction.get('line_start')} "
                    f"{construction.get('actor')}→{construction.get('recipient')} "
                    f"action_token=`{construction.get('action_token')}`："
                    f"`{_format_value(construction.get('fields', {}))}`"
                )
        else:
            lines.append("- 未捕获 actor/recipient 为 FRA/SAV 且 action_token 含 Guarantee 的全局条目。")
        lines.append("")
        lines.append("Guarantee 关系条目（全局 diplomacy.guarantee）：")
        lines.append("")
        relations = snapshot.get("guarantee_relations", [])
        if relations:
            for relation_index, relation in enumerate(relations, 1):
                lines.append(
                    f"- #{relation_index} 行 {relation.get('line_start')} "
                    f"{relation.get('first')}→{relation.get('second')}："
                    f"`{_format_value(relation.get('fields', {}))}`"
                )
        else:
            lines.append("- 未捕获 first/second 为 FRA/SAV 的 Guarantee 关系条目。")
        lines.append("")
    if payload["comparisons"]:
        lines.extend(["## 相邻存档差异", ""])
        for comparison in payload["comparisons"]:
            lines.append(
                f"### `{comparison['from_label']}` → `{comparison['to_label']}` "
                f"（存档 {comparison['from_index'] + 1} → 存档 {comparison['to_index'] + 1}）"
            )
            lines.append("")
            construction_change = comparison["guarantee_constructions"]
            lines.append(
                "- 全局 Guarantee diplomacy_construction 数量："
                f"{construction_change['before_count']} → {construction_change['after_count']}。"
            )
            if construction_change["field_changes"]:
                for change in construction_change["field_changes"]:
                    lines.append(
                        f"  - `{change['field']}`：{_format_value(change['before'])} → "
                        f"{_format_value(change['after'])}"
                    )
            else:
                lines.append("  - 无法按单条记录比较字段，完整条目见 report.json。")
            relation_change = comparison["guarantee_relations"]
            lines.append(
                "- 全局 Guarantee 关系条目数量："
                f"{relation_change['before_count']} → {relation_change['after_count']}。"
            )
            if relation_change["field_changes"]:
                for change in relation_change["field_changes"]:
                    lines.append(
                        f"  - `{change['field']}`：{_format_value(change['before'])} → "
                        f"{_format_value(change['after'])}"
                    )
            else:
                lines.append("  - 无法按单条记录比较字段，完整条目见 report.json。")
            for tag, changes in comparison["countries"].items():
                lines.append(f"- `{tag}` Guarantee/保护字段变化：")
                if changes["guarantee_related_field_changes"]:
                    for change in changes["guarantee_related_field_changes"]:
                        lines.append(f"  - `{change['field']}`：{_format_value(change['before'])} → "
                                     f"{_format_value(change['after'])}")
                else:
                    lines.append("  - 无变化。")
                diplomats = changes["diplomats"]
                lines.append(
                    f"- `{tag}` 外交官数量：{diplomats['before_count']} → "
                    f"{diplomats['after_count']}；条目原文见 report.json。"
                )
                constructions = changes["guarantee_constructions"]
                lines.append(
                    f"- `{tag}` Guarantee diplomacy_construction 数量："
                    f"{constructions['before_count']} → {constructions['after_count']}；"
                    "条目原文见 report.json。"
                )
                for direction, relation_change in changes["active_relations"].items():
                    lines.append(f"- `{direction}` active_relations 字段变化：")
                    if relation_change["field_changes"]:
                        for change in relation_change["field_changes"]:
                            lines.append(
                                f"  - `{change['field']}`：{_format_value(change['before'])} → "
                                f"{_format_value(change['after'])}"
                            )
                    else:
                        lines.append("  - 无可比较字段，或双方不是各一个完整条目。")
            lines.append("")
    lines.extend(
        [
            "## 解释边界",
            "",
            "报告只陈述存档中实际序列化的对象、字段和值。Guarantee 相关字段保持"
            "游戏原始名称；`diplomacy_construction` 仅表示外交官任务记录，"
            "全局 `diplomacy.guarantee` 条目才作为关系记录单独报告。"
            "`last_war`、`truce` 和 `spy_network` 的变化不被解释为 Guarantee 撤销的原因。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream FRA/SAV Guarantee fields from one or more EU4 saves."
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
        default=Path("work/runtime/r30-guarantee-save-effects-20261015-001"),
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
