#!/usr/bin/env python3
"""Stream Support Independence evidence from EU4 saves.

The scanner reuses the bounded EU4 save container, country capture, and
top-level parser from :mod:`inspect_dissolve_save_pair`.  It reads each save
through a streaming text member and retains only FRA/HOL/SWE/SAV/NOR country
blocks plus bounded Support Independence relation and construction records.
The global ``diplomacy.support_independence`` records are reported separately
from country ``diplomacy_construction`` records: the latter describe an envoy
task and do not prove that a relation persisted.

Values are copied as serialized by the game.  Relation fields whose names
contain ``opinion``, ``truce`` or ``last_war`` are highlighted when present,
but the tool does not assign a unit or causal meaning to them.
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


COUNTRY_TAGS = ("FRA", "HOL", "SWE", "SAV", "NOR")
RELATION_TARGETS = ("HOL", "SWE", "SAV", "NOR")
SUPPORT_PAIRS = {
    frozenset(("FRA", target)) for target in RELATION_TARGETS
}
MAX_RELATION_RECORDS = 256
MAX_RELATION_CAPTURE = 256 * 1024
MAX_CONSTRUCTION_RECORDS = 256
MAX_CONSTRUCTION_CAPTURE = 256 * 1024

COUNTRY_RE = re.compile(r"^\s*(FRA|HOL|SWE|SAV|NOR)\s*=\s*\{")
DIPLOMACY_RE = re.compile(r"^\s*diplomacy\s*=\s*\{")
SUPPORT_RELATION_RE = re.compile(r"^\s*support_independence\s*=\s*\{")
CONSTRUCTION_RE = re.compile(r"^\s*diplomacy_construction\s*=\s*\{")

# Configure only this process's imported scanner.  The bounded scanner still
# captures country blocks under its fixed per-country cap and never loads the
# complete gamestate into memory.
bounded.TARGET_TAGS = COUNTRY_TAGS
bounded.PAIR = frozenset(COUNTRY_TAGS)
bounded.COUNTRY_RE = COUNTRY_RE


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    return bounded.unquote(str(value))


def _country_entries(capture: bounded.CountryCapture) -> list[bounded.Entry]:
    open_index = capture.text.find("{")
    body = bounded.extract_block(capture.text, open_index)
    return bounded.top_level_entries(body)


def _relation_evidence_fields(fields: dict[str, Any]) -> dict[str, Any]:
    tokens = ("opinion", "truce", "last_war")
    return {
        key: value for key, value in fields.items()
        if any(token in key.lower() for token in tokens)
    }


def _support_related_fields(fields: dict[str, Any]) -> dict[str, Any]:
    tokens = ("support_independence", "independence")
    return {
        key: value for key, value in fields.items()
        if ".active_relations." not in key.lower()
        and any(token in key.lower() for token in tokens)
    }


def _diplomat_entries(entries: list[bounded.Entry]) -> tuple[list[dict[str, Any]], list[str]]:
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
            diplomats.append({
                "entry_key": envoy.key,
                "fields": parsed["fields"],
                "blocks": parsed["blocks"],
                "unknown": parsed["unknown"],
                "raw_body": envoy.body,
            })
            unknown.extend(parsed["unknown"])
    return diplomats, unknown


def _support_constructions(
    entries: list[bounded.Entry], path: str = ""
) -> tuple[list[dict[str, Any]], list[str]]:
    """Find FRA->target Support Independence envoy-task records."""

    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    for entry in entries:
        entry_path = f"{path}.{entry.key}" if path else entry.key
        if entry.body is None:
            continue
        if entry.key == "diplomacy_construction":
            parsed = bounded.parse_field_body(entry.body)
            fields = parsed["fields"]
            action = _scalar_text(fields.get("action_token"))
            actor = _scalar_text(fields.get("actor"))
            recipient = _scalar_text(fields.get("recipient"))
            if (action is not None and "support_independence" in action.lower()
                    and actor == "FRA" and recipient in RELATION_TARGETS):
                if len(records) < MAX_CONSTRUCTION_RECORDS:
                    records.append({
                        "path": entry_path,
                        "entry_key": entry.key,
                        "actor": actor,
                        "recipient": recipient,
                        "action_token": action,
                        "fields": fields,
                        "blocks": parsed["blocks"],
                        "unknown": parsed["unknown"],
                        "raw_body": entry.body,
                    })
                else:
                    unknown.append("support_construction_record_limit_reached")
            unknown.extend(parsed["unknown"])
        try:
            children = bounded.top_level_entries(entry.body)
        except bounded.SaveParseError as exc:
            unknown.append(f"{entry_path}:children_parse_error: {exc}")
            continue
        child_records, child_unknown = _support_constructions(children, entry_path)
        room = max(0, MAX_CONSTRUCTION_RECORDS - len(records))
        records.extend(child_records[:room])
        unknown.extend(child_unknown)
        if len(records) >= MAX_CONSTRUCTION_RECORDS:
            break
    return records, unknown


def _active_relation_summary(
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
        entry.body for entry in entries
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
            result["entries"].append({
                "fields": parsed["fields"],
                "evidence_fields": _relation_evidence_fields(parsed["fields"]),
                "blocks": parsed["blocks"],
                "unknown": parsed["unknown"],
                "raw_body": entry.body,
            })
            result["unknown"].extend(parsed["unknown"])
    return result


def _country_summary(
    tag: str, capture: bounded.CountryCapture | None
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
        "support_related_fields": {},
        "diplomats": [],
        "support_constructions": [],
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
    summary["support_related_fields"] = _support_related_fields(fields)
    diplomats, diplomat_unknown = _diplomat_entries(entries)
    summary["diplomats"] = diplomats
    summary["unknown"].extend(diplomat_unknown)
    constructions, construction_unknown = _support_constructions(entries)
    summary["support_constructions"] = constructions
    summary["unknown"].extend(construction_unknown)
    other_tags = RELATION_TARGETS if tag == "FRA" else ("FRA",)
    for other in other_tags:
        relation = _active_relation_summary(capture, other)
        summary["active_relations"][f"{tag}->{other}"] = relation
        summary["unknown"].extend(
            f"{tag}->{other}:{item}" for item in relation["unknown"]
        )
    return summary


def _scan_global_support_relations(
    path: Path, source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Scan only root diplomacy.support_independence blocks."""

    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    line_count = 0
    depth = 0
    diplomacy_depth: int | None = None
    diplomacy_complete = False
    active: list[str] | None = None
    start_line: int | None = None
    active_depth = 0
    bytes_captured = 0

    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if diplomacy_depth is None and before == 0 and DIPLOMACY_RE.match(line):
                diplomacy_depth = before + bounded.brace_delta(line)
            if (not diplomacy_complete and active is None
                    and diplomacy_depth is not None
                    and before == diplomacy_depth
                    and SUPPORT_RELATION_RE.match(line)):
                active = [line]
                start_line = line_number
                active_depth = before + bounded.brace_delta(line)
                depth = active_depth
                bytes_captured = len(line.encode("utf-8", errors="replace"))
                continue
            if active is not None:
                active.append(line)
                bytes_captured += len(line.encode("utf-8", errors="replace"))
                if bytes_captured > MAX_RELATION_CAPTURE:
                    unknown.append(f"line_{start_line}:support_relation_over_limit")
                    active = None
                    start_line = None
                    active_depth = 0
                    bytes_captured = 0
                else:
                    delta = bounded.brace_delta(line)
                    depth += delta
                    if depth == diplomacy_depth and before >= active_depth:
                        text = "".join(active)
                        try:
                            body = bounded.extract_block(text, text.find("{"))
                            parsed = bounded.parse_field_body(body)
                        except bounded.SaveParseError as exc:
                            unknown.append(f"line_{start_line}:support_relation_parse_error: {exc}")
                        else:
                            fields = parsed["fields"]
                            first = _scalar_text(fields.get("first"))
                            second = _scalar_text(fields.get("second"))
                            if frozenset((first, second)) in SUPPORT_PAIRS:
                                if len(records) < MAX_RELATION_RECORDS:
                                    records.append({
                                        "line_start": start_line,
                                        "entry_key": "support_independence",
                                        "first": first,
                                        "second": second,
                                        "action_direction": f"{first}->{second}",
                                        "start_date": _scalar_text(fields.get("start_date")),
                                        "fields": fields,
                                        "evidence_fields": _relation_evidence_fields(fields),
                                        "blocks": parsed["blocks"],
                                        "unknown": parsed["unknown"],
                                        "raw_body": body,
                                    })
                                else:
                                    unknown.append("support_relation_record_limit_reached")
                            unknown.extend(parsed["unknown"])
                        active = None
                        start_line = None
                        active_depth = 0
                        bytes_captured = 0
                    continue
            depth += bounded.brace_delta(line)
            if (diplomacy_depth is not None and depth == 0
                    and before >= diplomacy_depth):
                diplomacy_complete = True
                diplomacy_depth = None

    if active is not None:
        unknown.append(f"line_{start_line}:support_relation_block_incomplete")
    return records, unknown, {
        "line_count": line_count,
        "complete": active is None and diplomacy_complete,
    }


def _scan_global_support_constructions(
    path: Path, source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Scan province/root diplomacy_construction blocks for Support tasks."""

    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    line_count = 0
    depth = 0
    active: list[str] | None = None
    start_line: int | None = None
    parent_depth = 0
    active_depth = 0
    bytes_captured = 0
    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if active is None and CONSTRUCTION_RE.match(line):
                active = [line]
                start_line = line_number
                parent_depth = before
                active_depth = before + bounded.brace_delta(line)
                depth = active_depth
                bytes_captured = len(line.encode("utf-8", errors="replace"))
                continue
            if active is None:
                depth += bounded.brace_delta(line)
                continue
            active.append(line)
            bytes_captured += len(line.encode("utf-8", errors="replace"))
            if bytes_captured > MAX_CONSTRUCTION_CAPTURE:
                unknown.append(f"line_{start_line}:support_construction_over_limit")
                active = None
                start_line = None
                bytes_captured = 0
                depth = parent_depth
                continue
            depth += bounded.brace_delta(line)
            if depth != parent_depth or before < active_depth:
                continue
            text = "".join(active)
            try:
                body = bounded.extract_block(text, text.find("{"))
                parsed = bounded.parse_field_body(body)
            except bounded.SaveParseError as exc:
                unknown.append(f"line_{start_line}:support_construction_parse_error: {exc}")
            else:
                fields = parsed["fields"]
                action = _scalar_text(fields.get("action_token"))
                actor = _scalar_text(fields.get("actor"))
                recipient = _scalar_text(fields.get("recipient"))
                if (action is not None and "support_independence" in action.lower()
                        and actor == "FRA" and recipient in RELATION_TARGETS):
                    if len(records) < MAX_CONSTRUCTION_RECORDS:
                        records.append({
                            "line_start": start_line,
                            "entry_key": "diplomacy_construction",
                            "actor": actor,
                            "recipient": recipient,
                            "action_token": action,
                            "fields": fields,
                            "blocks": parsed["blocks"],
                            "unknown": parsed["unknown"],
                            "raw_body": body,
                        })
                    else:
                        unknown.append("support_construction_record_limit_reached")
                unknown.extend(parsed["unknown"])
            active = None
            start_line = None
            bytes_captured = 0
            depth = parent_depth
    if active is not None:
        unknown.append(f"line_{start_line}:support_construction_block_incomplete")
    return records, unknown, {"line_count": line_count, "complete": active is None}


def scan_save(path: Path, label: str, index: int = 0) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    global_relations, relation_unknown, relation_scan = _scan_global_support_relations(
        path, source
    )
    global_constructions, construction_unknown, construction_scan = (
        _scan_global_support_constructions(path, source)
    )

    countries: dict[str, Any] = {}
    unknown: list[str] = []
    for tag in COUNTRY_TAGS:
        countries[tag] = _country_summary(tag, scanner.country_captures.get(tag))
        unknown.extend(f"{tag}:{item}" for item in countries[tag]["unknown"])
    if scanner.duplicate_country_tags:
        unknown.extend(f"duplicate_country_tag:{tag}" for tag in scanner.duplicate_country_tags)
    if not scanner.countries_found:
        unknown.append("countries_block_not_found")
    elif not scanner.countries_complete:
        unknown.append("countries_block_incomplete")
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    unknown.extend(f"global_support_relation:{item}" for item in relation_unknown)
    unknown.extend(f"global_support_construction:{item}" for item in construction_unknown)
    return {
        "label": label,
        "source": source,
        "metadata": {"first_line": scanner.header_line, "date": scanner.save_date},
        "parse": {
            "gamestate_line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "countries_block_found": scanner.countries_found,
            "countries_block_complete": scanner.countries_complete,
            "diplomacy_block_found": scanner.diplomacy_found,
            "diplomacy_block_complete": scanner.diplomacy_complete,
            "support_relation_scan": relation_scan,
            "support_construction_scan": construction_scan,
            "unknown": unknown,
        },
        "countries": countries,
        "support_relations": global_relations,
        "support_constructions": global_constructions,
    }


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    missing = object()
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key, missing)
        new = after.get(key, missing)
        if old == new:
            continue
        changes.append({
            "field": key,
            "kind": "added" if old is missing else "removed" if new is missing else "changed",
            "before": None if old is missing else old,
            "after": None if new is missing else new,
        })
    return changes


def _one_fields(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(entries) != 1 or not isinstance(entries[0].get("fields"), dict):
        return None
    return entries[0]["fields"]


def _relation_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old_entries = before.get("entries", [])
    new_entries = after.get("entries", [])
    old_fields = _one_fields(old_entries)
    new_fields = _one_fields(new_entries)
    return {
        "before_present": before.get("present", False),
        "after_present": after.get("present", False),
        "before_entry_count": len(old_entries),
        "after_entry_count": len(new_entries),
        "field_changes": _field_changes(old_fields, new_fields)
        if old_fields is not None and new_fields is not None else [],
        "unknown": [] if old_fields is not None and new_fields is not None
        else ["field_diff_requires_exactly_one_entry_per_side"],
    }


def _support_relation_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old_entries = before.get("support_relations", [])
    new_entries = after.get("support_relations", [])
    old_fields = _one_fields(old_entries)
    new_fields = _one_fields(new_entries)
    return {
        "before_count": len(old_entries),
        "after_count": len(new_entries),
        "before_entries": old_entries,
        "after_entries": new_entries,
        "field_changes": _field_changes(old_fields, new_fields)
        if old_fields is not None and new_fields is not None else [],
        "unknown": [] if len(old_entries) <= 1 and len(new_entries) <= 1
        else ["field_diff_requires_at_most_one_support_relation_per_snapshot"],
    }


def _comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    countries: dict[str, Any] = {}
    for tag in COUNTRY_TAGS:
        old = before["countries"][tag]
        new = after["countries"][tag]
        relation_changes: dict[str, Any] = {}
        for direction in old.get("active_relations", {}):
            relation_changes[direction] = _relation_change(
                old["active_relations"].get(direction, {}),
                new["active_relations"].get(direction, {}),
            )
        countries[tag] = {
            "support_related_field_changes": _field_changes(
                old.get("support_related_fields", {}),
                new.get("support_related_fields", {}),
            ),
            "diplomats": {
                "before_count": len(old.get("diplomats", [])),
                "after_count": len(new.get("diplomats", [])),
                "before_entries": old.get("diplomats", []),
                "after_entries": new.get("diplomats", []),
            },
            "support_constructions": {
                "before_count": len(old.get("support_constructions", [])),
                "after_count": len(new.get("support_constructions", [])),
                "before_entries": old.get("support_constructions", []),
                "after_entries": new.get("support_constructions", []),
            },
            "active_relations": relation_changes,
        }
    old_constructions = before.get("support_constructions", [])
    new_constructions = after.get("support_constructions", [])
    old_construction_fields = _one_fields(old_constructions)
    new_construction_fields = _one_fields(new_constructions)
    return {
        "from_label": before["label"],
        "to_label": after["label"],
        "before_source": before["source"]["sha256"],
        "after_source": after["source"]["sha256"],
        "support_relations": _support_relation_change(before, after),
        "support_constructions": {
            "before_count": len(old_constructions),
            "after_count": len(new_constructions),
            "before_entries": old_constructions,
            "after_entries": new_constructions,
            "field_changes": _field_changes(old_construction_fields, new_construction_fields)
            if old_construction_fields is not None and new_construction_fields is not None else [],
            "unknown": [] if len(old_constructions) <= 1 and len(new_constructions) <= 1
            else ["field_diff_requires_at_most_one_support_construction_per_snapshot"],
        },
        "countries": countries,
        "interpretation_guard": (
            "Global diplomacy.support_independence is reported as the persisted "
            "relation candidate. Country diplomacy_construction is an envoy-task "
            "record and is reported separately. Relation, opinion, truce, and "
            "last_war values remain raw serialized fields; missing fields are "
            "absence from the captured pair block only."
        ),
    }


def build_payload(paths: list[Path], labels: list[str]) -> dict[str, Any]:
    if len(paths) != len(labels):
        raise ValueError("one --label is required for every --save")
    snapshots = [scan_save(path, labels[index], index) for index, path in enumerate(paths)]
    payload: dict[str, Any] = {
        "tool": {
            "name": "extract_support_independence_save_effects.py",
            "version": 1,
            "scope": (
                "streaming gamestate scan; FRA/HOL/SWE/SAV/NOR country blocks, "
                "FRA pair active_relations, diplomats, support constructions, "
                "global diplomacy_construction tasks, and global "
                "diplomacy.support_independence records"
            ),
            "scanner_source": "work/inspect_dissolve_save_pair.py",
        },
        "country_tags": list(COUNTRY_TAGS),
        "support_relation_pairs": ["FRA->HOL", "FRA->SWE", "FRA->SAV", "FRA->NOR"],
        "snapshot_labels": labels,
        "snapshots": snapshots,
        "comparisons": [
            {"from_index": index, "to_index": index + 1,
             **_comparison(snapshots[index], snapshots[index + 1])}
            for index in range(len(snapshots) - 1)
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    payload["integrity"] = {
        "canonical_payload_sha256": hashlib.sha256(canonical).hexdigest(),
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
        "# R31 支持独立存档后果取证",
        "",
        "本报告使用有界流式扫描器读取输入的 EU4 存档。扫描器只保留 FRA、HOL、SWE、SAV、NOR 国家块，"
        "相关双方 active_relations、外交官记录、Support Independence 的外交官任务记录，以及全局 "
        "`diplomacy.support_independence` 关系条目。",
        "",
        "全局 `diplomacy.support_independence` 条目单独作为关系证据；"
        "国家块中的 `diplomacy_construction` 仅作为外交官任务证据，不代表关系已经持久化。",
        "关系方向按全局条目的 `first→second` 展示。入站请求的 `actor` 字段不参与支持方命名；"
        "角色名称应以原生业务证据为准。",
        "",
        f"`report.json` SHA-256：`{json_sha256}`",
        f"规范化载荷 SHA-256：`{payload['integrity']['canonical_payload_sha256']}`",
        "",
    ]
    for index, snapshot in enumerate(payload["snapshots"], 1):
        source = snapshot["source"]
        lines.extend([
            f"## 存档 {index}：{snapshot['label']}",
            "",
            f"- 文件：`{source['path']}`",
            f"- SHA-256：`{source['sha256']}`",
            f"- 保存日期：`{snapshot['metadata']['date']}`",
            f"- 容器：`{source['container']}`；大小：`{source['size_bytes']}` 字节",
            f"- gamestate 行数：`{snapshot['parse']['gamestate_line_count']}`；"
            f"括号平衡：`{snapshot['parse']['brace_balance_ok']}`",
            "",
            "### 全局 diplomacy.support_independence",
            "",
        ])
        relations = snapshot.get("support_relations", [])
        if relations:
            for relation in relations:
                lines.append(
                    f"- 行 {relation['line_start']}：原始方向 `{relation['first']}→{relation['second']}`，"
                    f"start_date=`{relation.get('start_date')}`；字段："
                    f"`{_format_value(relation['fields'])}`"
                )
                if relation.get("evidence_fields"):
                    lines.append(f"  - opinion/truce/last_war 字段：`{_format_value(relation['evidence_fields'])}`")
        else:
            lines.append("- 未捕获 first/second 为 FRA 与 HOL、SWE、SAV 或 NOR 的全局关系条目。")
        lines.extend(["", "### 全局 diplomacy_construction（外交官任务）", ""])
        constructions = snapshot.get("support_constructions", [])
        if constructions:
            for construction in constructions:
                lines.append(
                    f"- 行 {construction['line_start']}：原始方向 "
                    f"`{construction['actor']}→{construction['recipient']}`，"
                    f"action_token=`{construction['action_token']}`；字段："
                    f"`{_format_value(construction['fields'])}`"
                )
        else:
            lines.append("- 未捕获 FRA→HOL/SWE/SAV/NOR 的全局 Support Independence 任务记录。")
        lines.extend(["", "### 国家块中的 Support 任务与双方关系", ""])
        for tag in COUNTRY_TAGS:
            country = snapshot["countries"][tag]
            lines.extend([
                f"#### {tag}",
                "",
                f"国家块 found=`{country['capture']['found']}`，complete=`{country['capture']['complete']}`，"
                f"捕获字节=`{country['capture']['bytes_captured']}`。",
                f"外交官条目数量：`{len(country['diplomats'])}`。",
                "",
                "Support 相关国家字段（原始值）：",
                "",
            ])
            if country["support_related_fields"]:
                for key, value in country["support_related_fields"].items():
                    lines.append(f"- `{key}` = `{value}`")
            else:
                lines.append("- 未捕获字段名包含 Support/Independence/opinion/truce/last_war 的国家字段。")
            lines.extend(["", "外交官任务记录：", ""])
            constructions = country["support_constructions"]
            if constructions:
                for construction in constructions:
                    lines.append(
                        f"- `{construction['actor']}→{construction['recipient']}`，"
                        f"action_token=`{construction['action_token']}`，"
                        f"字段：`{_format_value(construction['fields'])}`"
                    )
            else:
                lines.append("- 未捕获 FRA→HOL/SWE/SAV/NOR 的 Support Independence diplomacy_construction。")
            lines.extend(["", "active_relations（原始方向）：", ""])
            for direction, relation in country["active_relations"].items():
                lines.append(
                    f"- `{direction}`：present=`{relation['present']}`，"
                    f"条目数=`{len(relation['entries'])}`"
                )
                for entry in relation["entries"]:
                    lines.append(f"  - 字段：`{_format_value(entry['fields'])}`")
                    if entry.get("evidence_fields"):
                        lines.append(
                            f"  - opinion/truce/last_war 字段：`{_format_value(entry['evidence_fields'])}`"
                        )
            lines.append("")
    if payload["comparisons"]:
        lines.extend(["## 相邻存档差异", ""])
        for comparison in payload["comparisons"]:
            lines.extend([
                f"### `{comparison['from_label']}` → `{comparison['to_label']}`",
                "",
            ])
            support_change = comparison["support_relations"]
            lines.append(
                f"- 全局 Support Independence 关系条目数："
                f"{support_change['before_count']} → {support_change['after_count']}。"
            )
            if support_change["field_changes"]:
                for change in support_change["field_changes"]:
                    lines.append(
                        f"  - `{change['field']}`：{_format_value(change['before'])} → "
                        f"{_format_value(change['after'])}"
                    )
            else:
                lines.append("  - 无法按单条全局关系比较，完整原始条目见 report.json。")
            construction_change = comparison["support_constructions"]
            lines.append(
                f"- 全局 Support Independence diplomacy_construction 数量："
                f"{construction_change['before_count']} → {construction_change['after_count']}。"
            )
            if construction_change["field_changes"]:
                for change in construction_change["field_changes"]:
                    lines.append(
                        f"  - `{change['field']}`：{_format_value(change['before'])} → "
                        f"{_format_value(change['after'])}"
                    )
            for tag, changes in comparison["countries"].items():
                lines.append(
                    f"- `{tag}` Support 相关字段变化："
                    f"{len(changes['support_related_field_changes'])} 项；"
                    f"外交官数量 {changes['diplomats']['before_count']} → "
                    f"{changes['diplomats']['after_count']}；"
                    f"国家块内 Support 任务数量 {changes['support_constructions']['before_count']} → "
                    f"{changes['support_constructions']['after_count']}。"
                )
                for direction, relation_change in changes["active_relations"].items():
                    if relation_change["field_changes"]:
                        lines.append(f"  - `{direction}` active_relations 字段变化：")
                        for change in relation_change["field_changes"]:
                            lines.append(
                                f"    - `{change['field']}`：{_format_value(change['before'])} → "
                                f"{_format_value(change['after'])}"
                            )
            lines.append("")
    lines.extend([
        "## 解释边界",
        "",
        "报告保留游戏实际序列化的 first/second、日期、关系字段和外交官任务字段。"
        "方向按原始 first→second 展示，不把请求 actor 自动命名为支持方。"
        "未出现 opinion、truce 或 last_war 字段时，"
        "只能说明对应捕获的双方 active_relations 条目没有这些字段；报告不推断隐藏对象或撤销原因。",
        "",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream FRA Support Independence save effects.")
    parser.add_argument("--save", action="append", required=True, type=Path,
                        help="save path; repeat for baseline/rejected/active/revoked")
    parser.add_argument("--label", action="append", required=True,
                        help="label for each save, in the same order")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("work/runtime/r31-support-save-effects-20261015-001"),
                        help="fresh evidence directory")
    args = parser.parse_args()
    if len(args.save) != len(args.label):
        raise SystemExit("--label must be supplied once for every --save")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"output directory is not fresh: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(args.save, args.label)
    json_path = args.output_dir / "report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    report_path = args.output_dir / "report.md"
    report_path.write_text(render_report(payload, bounded.sha256_file(json_path)),
                           encoding="utf-8")
    print(json_path)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
