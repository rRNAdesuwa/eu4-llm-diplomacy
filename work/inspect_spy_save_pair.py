#!/usr/bin/env python3
"""Stream bounded FRA/SAV Spy Network evidence from EU4 saves.

The scanner reuses :mod:`inspect_dissolve_save_pair`'s streaming container and
bounded country capture.  It retains only the FRA and SAV country blocks, the
serialized FRA->SAV/SAV->FRA ``active_relations`` entries, the FRA/SAV
``diplomats`` entries, and fields whose serialized names identify Spy Network
or espionage state.  A save is hashed in chunks; the 38 MB save text is never
loaded as one string.

Pass one or more saves by repeating ``--save``.  The output directory must be
fresh so a later comparison cannot overwrite an earlier evidence package::

    python work/inspect_spy_save_pair.py \
        --save "...\\llm_diplomacy_spy_sav_active_20261015_r29a.eu4" \
        --output-dir work/runtime/r29-spy-save-effects-20261015-001

Later runs can repeat ``--save`` for the active, 35-day, and stopped saves and
use a different ``--output-dir``.  Values are reported as the raw serialized
strings; this tool does not assign a scale to ``spy_network`` values.
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
SPY_TOKENS = (
    "spy",
    "espion",
    "discov",
    "counterspy",
    "counter_espion",
    "reveal",
)

# Configure only this process's imported scanner.  The existing module on disk
# remains unchanged and all captures stay within its 8 MiB country/256 KiB
# alliance limits.
bounded.TARGET_TAGS = TARGET_TAGS
bounded.PAIR = PAIR
bounded.COUNTRY_RE = re.compile(r"^\s*(FRA|SAV)\s*=\s*\{")


def _is_spy_field(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in SPY_TOKENS)


def _country_entries(capture: bounded.CountryCapture) -> list[bounded.Entry]:
    open_index = capture.text.find("{")
    body = bounded.extract_block(capture.text, open_index)
    return bounded.top_level_entries(body)


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
        "spy_related_fields": {},
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

    summary["spy_related_fields"] = {
        key: value for key, value in fields.items() if _is_spy_field(key)
    }
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


def scan_save(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)

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

    return {
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
            "unknown": unknown,
        },
        "countries": countries,
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
            "spy_related_field_changes": _field_changes(
                old.get("spy_related_fields", {}), new.get("spy_related_fields", {})
            ),
            "diplomats": {
                "before_count": len(old.get("diplomats", [])),
                "after_count": len(new.get("diplomats", [])),
                "before_entries": old.get("diplomats", []),
                "after_entries": new.get("diplomats", []),
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
    return {
        "before_source": before["source"]["sha256"],
        "after_source": after["source"]["sha256"],
        "countries": country_changes,
        "interpretation_guard": (
            "All values are raw serialized save fields. A missing field means "
            "absent from the captured FRA/SAV country or pair block only; this "
            "report does not infer a global spy-network scale or hidden state."
        ),
    }


def build_payload(paths: list[Path]) -> dict[str, Any]:
    snapshots = [scan_save(path) for path in paths]
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
            "name": "inspect_spy_save_pair.py",
            "version": 1,
            "scope": (
                "streaming gamestate scan; FRA/SAV country blocks, exact "
                "FRA<->SAV active_relations, diplomats, and raw Spy fields"
            ),
            "scanner_source": "work/inspect_dissolve_save_pair.py",
        },
        "pair": ["FRA", "SAV"],
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
        "# R29 Spy Network 存档字段取证",
        "",
        "本报告由 `work/inspect_spy_save_pair.py` 生成。扫描器流式读取 gamestate，"
        "只保留 FRA/SAV 国家块、双方 `active_relations`、外交官条目及原始 Spy 相关字段。"
        "报告保留存档字段原始字符串，不对 `spy_network` 数值赋予单位或比例解释。",
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
            lines.append("Spy/侦破相关字段（原始值）：")
            lines.append("")
            fields = country["spy_related_fields"]
            if fields:
                for key, value in fields.items():
                    lines.append(f"- `{key}` = `{value}`")
            else:
                lines.append("- 未在该国家块捕获到字段名包含 Spy/侦破标识的字段。")
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
            lines.extend(["", "双方 active_relations：", ""])
            for direction, relation in country["active_relations"].items():
                lines.append(
                    f"- `{direction}`：present=`{relation['present']}`，"
                    f"条目数=`{len(relation['entries'])}`"
                )
                for entry in relation["entries"]:
                    lines.append(f"  - 原始字段：`{_format_value(entry['fields'])}`")
            lines.append("")
    if payload["comparisons"]:
        lines.extend(["## 相邻存档差异", ""])
        for comparison in payload["comparisons"]:
            lines.append(
                f"### 存档 {comparison['from_index'] + 1} → 存档 {comparison['to_index'] + 1}"
            )
            lines.append("")
            for tag, changes in comparison["countries"].items():
                lines.append(f"- `{tag}` Spy 字段变化：")
                if changes["spy_related_field_changes"]:
                    for change in changes["spy_related_field_changes"]:
                        lines.append(f"  - `{change['field']}`：{_format_value(change['before'])} → "
                                     f"{_format_value(change['after'])}")
                else:
                    lines.append("  - 无变化。")
                diplomats = changes["diplomats"]
                lines.append(
                    f"- `{tag}` 外交官数量：{diplomats['before_count']} → "
                    f"{diplomats['after_count']}；条目原文见 report.json。"
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
            "报告只陈述存档中实际序列化的对象、字段和值。`our_spy_network`、"
            "`their_spy_network`、`active_relations.*.spy_network` 和"
            "`is_building_spy_network` 保持原字段名；未出现字段仅表示对应捕获块中未出现。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream FRA/SAV Spy Network fields from one or more EU4 saves."
    )
    parser.add_argument(
        "--save", action="append", required=True, type=Path,
        help="save path; repeat for active/after/stopped snapshots",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("work/runtime/r29-spy-save-effects-20261015-001"),
        help="fresh evidence directory; an existing non-empty directory is rejected",
    )
    args = parser.parse_args()
    output_dir: Path = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"output directory is not fresh: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(args.save)
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
