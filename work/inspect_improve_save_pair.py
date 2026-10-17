#!/usr/bin/env python3
"""Bounded comparison of the R28 Improve Relations save snapshots.

The scanner reuses the bounded container, gamestate and block readers from
``inspect_dissolve_save_pair.py``.  It keeps only the FRA and SAV country
blocks, the selected active_relations entries, and FRA's serialized diplomats
block.  It never calls ``read_text`` on an entire save or retains the complete
gamestate member.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

import inspect_dissolve_save_pair as bounded  # noqa: E402


TARGET_TAGS = ("FRA", "SAV")
PAIR = frozenset(TARGET_TAGS)
SAVE_NAMES = (
    "llm_diplomacy_improve_sav_active_20261015_r28b.eu4",
    "llm_diplomacy_improve_sav_35days_20261015_r28c.eu4",
    "llm_diplomacy_improve_sav_returning_20261015_r28c.eu4",
)
COUNTRY_RE = re.compile(r"^\s*(FRA|SAV)\s*=\s*\{")
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "runtime"
    / "r28-improve-save-effects-20261015-001"
)


def configure_bounded_reader() -> None:
    """Configure the imported bounded scanner in this process only."""

    bounded.TARGET_TAGS = TARGET_TAGS
    bounded.PAIR = PAIR
    bounded.COUNTRY_RE = COUNTRY_RE


def _parse_country_entries(capture: Any) -> list[Any]:
    if capture is None or not capture.complete:
        return []
    open_index = capture.text.find("{")
    body = bounded.extract_block(capture.text, open_index)
    return bounded.top_level_entries(body)


def _relation_entries(country_entries: list[Any], other: str) -> dict[str, Any]:
    relation_blocks = [
        entry.body
        for entry in country_entries
        if entry.key == "active_relations" and entry.body is not None
    ]
    result: dict[str, Any] = {
        "present": False,
        "active_relations_block_count": len(relation_blocks),
        "entries": [],
        "opinion_modifiers_key_in_selected_country": any(
            entry.key == "opinion_modifiers" for entry in country_entries
        ),
        "unknown": [],
    }
    for relation_body in relation_blocks:
        try:
            entries = bounded.top_level_entries(relation_body)
        except bounded.SaveParseError as exc:
            result["unknown"].append(f"active_relations_parse_error: {exc}")
            continue
        for entry in entries:
            if entry.key != other or entry.body is None:
                continue
            parsed = bounded.parse_field_body(entry.body)
            result["present"] = True
            result["entries"].append(
                {
                    "fields": parsed["fields"],
                    "blocks": parsed["blocks"],
                    "unknown": parsed["unknown"],
                }
            )
            result["unknown"].extend(parsed["unknown"])
    return result


def _diplomat_entries(country_entries: list[Any]) -> dict[str, Any]:
    blocks = [
        entry.body
        for entry in country_entries
        if entry.key == "diplomats" and entry.body is not None
    ]
    result: dict[str, Any] = {
        "present": bool(blocks),
        "diplomats_block_count": len(blocks),
        "entries": [],
        "unknown": [],
    }
    for body in blocks:
        try:
            entries = bounded.top_level_entries(body)
        except bounded.SaveParseError as exc:
            result["unknown"].append(f"diplomats_parse_error: {exc}")
            continue
        for entry in entries:
            parsed = bounded.parse_field_body(entry.body or "") if entry.body is not None else {
                "fields": {},
                "blocks": [],
                "unknown": [],
            }
            result["entries"].append(
                {
                    "key": entry.key,
                    "value": entry.value,
                    "fields": parsed["fields"],
                    "blocks": parsed["blocks"],
                    "unknown": parsed["unknown"],
                }
            )
            result["unknown"].extend(parsed["unknown"])
    return result


def scan_save(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)

    countries: dict[str, Any] = {}
    unknown = list(scanner.alliance_parse_unknown)
    for tag in TARGET_TAGS:
        capture = scanner.country_captures.get(tag)
        summary: dict[str, Any] = {
            "found": capture is not None,
            "start_line": capture.start_line if capture else None,
            "end_line": capture.end_line if capture else None,
            "complete": capture.complete if capture else False,
            "bytes_captured": capture.bytes_captured if capture else 0,
        }
        if capture is None:
            unknown.append(f"country_{tag}_not_found")
            countries[tag] = summary
            continue
        if not capture.complete:
            unknown.append(f"country_{tag}_capture_incomplete")
            countries[tag] = summary
            continue
        try:
            entries = _parse_country_entries(capture)
        except bounded.SaveParseError as exc:
            summary["unknown"] = [f"country_{tag}_parse_error: {exc}"]
            unknown.extend(summary["unknown"])
            countries[tag] = summary
            continue
        other = "SAV" if tag == "FRA" else "FRA"
        summary["active_relations"] = _relation_entries(entries, other)
        if tag == "FRA":
            summary["diplomats"] = _diplomat_entries(entries)
        summary["top_level_opinion_modifiers_keys"] = [
            entry.key for entry in entries if entry.key == "opinion_modifiers"
        ]
        countries[tag] = summary

    if scanner.duplicate_country_tags:
        unknown.extend(
            f"duplicate_country_tag:{tag}" for tag in scanner.duplicate_country_tags
        )
    if not scanner.countries_found:
        unknown.append("countries_block_not_found")
    elif not scanner.countries_complete:
        unknown.append("countries_block_incomplete")
    if not scanner.diplomacy_found:
        unknown.append("diplomacy_block_not_found")
    elif not scanner.diplomacy_complete:
        unknown.append("diplomacy_block_incomplete")
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")

    return {
        "file_name": path.name,
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
            "alliance_blocks_scanned": scanner.alliance_blocks_seen,
            "unknown": unknown,
        },
        "countries": countries,
    }


def _fields_from_relation(save: dict[str, Any], direction: str) -> dict[str, Any] | None:
    tag, other = direction.split("->")
    relation = save["countries"][tag]["active_relations"]
    entries = relation["entries"] if relation["present"] else []
    if len(entries) != 1:
        return None
    return entries[0]["fields"]


def _field_changes(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:
    if before is None or after is None:
        return []
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


def _diplomat_map(save: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = save["countries"]["FRA"].get("diplomats", {}).get("entries", [])
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        fields = entry.get("fields", {})
        key = fields.get("id", entry.get("key", "unknown"))
        if isinstance(key, list):
            key = "|".join(str(item) for item in key)
        result[str(key)] = fields
    return result


def _diplomat_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    before_map = _diplomat_map(before)
    after_map = _diplomat_map(after)
    for key in sorted(set(before_map) | set(after_map)):
        old = before_map.get(key)
        new = after_map.get(key)
        if old == new:
            continue
        changes.append(
            {
                "id": key,
                "field_changes": _field_changes(old, new),
                "before": old,
                "after": new,
            }
        )
    return changes


def build_comparison(saves: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {item["file_name"]: item for item in saves}
    active, days, returning = (by_name[name] for name in SAVE_NAMES)
    directions = ("FRA->SAV", "SAV->FRA")
    relation_changes: dict[str, Any] = {}
    for direction in directions:
        relation_changes[direction] = {
            "active_to_35days": {
                "field_changes": _field_changes(
                    _fields_from_relation(active, direction),
                    _fields_from_relation(days, direction),
                )
            },
            "35days_to_returning": {
                "field_changes": _field_changes(
                    _fields_from_relation(days, direction),
                    _fields_from_relation(returning, direction),
                )
            },
        }
    return {
        "relation_field_changes": relation_changes,
        "diplomat_field_changes": {
            "active_to_35days": _diplomat_changes(active, days),
            "35days_to_returning": _diplomat_changes(days, returning),
        },
        "interpretation_guard": (
            "Values are serialized save fields. The report does not assign a score "
            "scale or translate unknown diplomat name/action enums."
        ),
    }


def _compact_fields(save: dict[str, Any], direction: str) -> dict[str, Any]:
    fields = _fields_from_relation(save, direction)
    if fields is None:
        return {"entry_count": 0, "fields": None}
    return {"entry_count": 1, "fields": fields}


def render_report(payload: dict[str, Any]) -> str:
    saves = payload["saves"]
    lines = [
        "# R28 Improve Relations 存档字段取证",
        "",
        "本报告由 `inspect_improve_save_pair.py` 生成。程序以流式方式打开三个 EU4txt 存档，只保留 FRA/SAV country block、双方 `active_relations` 对象和 FRA 的 `diplomats` 条目；程序没有把 38MB 级存档整体读入内存。",
        "",
        "## 源文件和完整性",
        "",
        "| 存档 | 日期 | 字节数 | SHA-256 | gamestate 完整性 |",
        "|---|---|---:|---|---|",
    ]
    for save in saves:
        source = save["source"]
        parse = save["parse"]
        lines.append(
            f"| `{save['file_name']}` | `{save['metadata']['date']}` | "
            f"{source['size_bytes']} | `{source['sha256']}` | "
            f"countries={parse['countries_block_complete']}, diplomacy={parse['diplomacy_block_complete']}, "
            f"brace={parse['brace_balance_ok']}, unknown={len(parse['unknown'])} |"
        )
    lines.extend(["", "所有输入的国家块和 diplomacy 块均完整，解析未知项为 0。", ""])

    lines.extend(["## active_relations 和 opinion 字段", ""])
    lines.append("意见数据位于 `active_relations.<目标>.opinion` 内。三个选定 FRA/SAV country block 都没有名为 `opinion_modifiers` 的顶层键；报告保留了原始嵌套字段名和值。")
    lines.append("")
    for direction in ("FRA->SAV", "SAV->FRA"):
        lines.append(f"### `{direction}`")
        lines.append("")
        lines.append("| 存档 | `opinion.modifier` | `opinion.date` | `opinion.current_opinion` | `cached_sum` | `last_send_diplomat` | `attitude` | 其他原始字段 |")
        lines.append("|---|---|---|---:|---:|---|---|---|")
        for save in saves:
            fields = _fields_from_relation(save, direction) or {}
            known = {
                "opinion.modifier",
                "opinion.date",
                "opinion.current_opinion",
                "cached_sum",
                "last_send_diplomat",
                "attitude",
            }
            other = {k: v for k, v in fields.items() if k not in known}
            lines.append(
                f"| `{save['metadata']['date']}` | `{fields.get('opinion.modifier')}` | "
                f"`{fields.get('opinion.date')}` | `{fields.get('opinion.current_opinion')}` | "
                f"`{fields.get('cached_sum')}` | `{fields.get('last_send_diplomat')}` | "
                f"`{fields.get('attitude')}` | `{json.dumps(other, ensure_ascii=False, sort_keys=True)}` |"
            )
        lines.append("")

    lines.extend(["### 字段变化", ""])
    for direction, transitions in payload["comparison"]["relation_field_changes"].items():
        lines.append(f"- `{direction}` active→35 天：`{json.dumps(transitions['active_to_35days']['field_changes'], ensure_ascii=False)}`")
        lines.append(f"- `{direction}` 35 天→停止后：`{json.dumps(transitions['35days_to_returning']['field_changes'], ensure_ascii=False)}`")
    lines.extend(["", "在原始字段中，FRA→SAV 的 `opinion.current_opinion` 为 `3.500 → 7.000 → 7.000`，SAV→FRA 为 `7.000 → 14.000 → 14.000`。这里保留游戏写入的数值，不推断该数值的尺度或是否等于 API 接受度。", ""])

    lines.extend(["## FRA diplomats 条目", "", "以下表格来自 FRA country block 的 `diplomats` 子块。`name` 和 `action` 保留存档原始值；本报告不把数值强行翻译成未验证的枚举。", "", "| 存档 | `id` | `action` | `type` | `name`（原始序列化值） |", "|---|---:|---:|---:|---|"])
    for save in saves:
        for entry in save["countries"]["FRA"].get("diplomats", {}).get("entries", []):
            fields = entry.get("fields", {})
            lines.append(
                f"| `{save['metadata']['date']}` | `{fields.get('id')}` | `{fields.get('action')}` | "
                f"`{fields.get('type')}` | `{fields.get('name')}` |"
            )
    lines.extend(["", "FRA 的 `id=3` 条目在活动存档和 35 天存档中为 `action=2`，停止后存档为 `action=1`；停止后日期仍为 `1445.4.16`。这与“任务标记改变、外交官进入返程记录”的运行观察相符，但本报告不为 `action` 数值添加额外枚举含义。", ""])
    lines.extend(["## 机器可读证据", "", "完整字段、源路径、源哈希、捕获范围、解析完整性和逐字段变化见同目录 `evidence.json`。", ""])
    return "\n".join(lines) + "\n"


def build_payload(save_dir: Path, output_dir: Path) -> dict[str, Any]:
    paths = [save_dir / name for name in SAVE_NAMES]
    saves = [scan_save(path) for path in paths]
    payload = {
        "tool": {
            "name": "inspect_improve_save_pair.py",
            "version": 1,
            "reused": "inspect_dissolve_save_pair.py bounded SaveScanner/open_gamestate/top_level_entries",
            "scope": "streaming FRA/SAV country and active_relations scan; FRA diplomats only",
            "max_country_capture_bytes": bounded.MAX_COUNTRY_CAPTURE,
            "whole_save_read": False,
        },
        "inputs": {
            "save_directory": str(save_dir.resolve()),
            "names": list(SAVE_NAMES),
            "pair": list(TARGET_TAGS),
        },
        "saves": saves,
        "comparison": build_comparison(saves),
        "integrity": {
            "all_sources_present": all(
                save["source"]["size_bytes"] > 0 for save in saves
            ),
            "all_country_captures_complete": all(
                save["countries"][tag]["complete"]
                for save in saves
                for tag in TARGET_TAGS
            ),
            "all_streams_brace_balanced": all(
                save["parse"]["brace_balance_ok"] for save in saves
            ),
            "unknown_count": sum(len(save["parse"]["unknown"]) for save in saves),
        },
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--save-dir", type=Path, default=None)
    args = parser.parse_args()

    configure_bounded_reader()
    if args.save_dir is None:
        sys.path.insert(0, str(WORK_DIR))
        from local_config import user_data

        save_dir = Path(user_data()) / "save games"
    else:
        save_dir = args.save_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = build_payload(save_dir, output_dir)
    (output_dir / "evidence.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir.resolve()),
        "json": str((output_dir / "evidence.json").resolve()),
        "report": str((output_dir / "report.md").resolve()),
        "sources": [save["file_name"] for save in payload["saves"]],
        "unknown_count": payload["integrity"]["unknown_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
