#!/usr/bin/env python3
"""流式提取 EU4 存档中的宿敌、资源和外交官原始字段。

该工具面向 R34 的单份基线存档，也可以用同一命令扫描后续 before/after
存档。工具按行读取 ``gamestate``，只在内存中保留指定国家块；不会把完整
存档或完整 gamestate 成员读入内存。输出 JSON 保留序列化字段的原始键和值、
国家块行号、相关原文短片段以及源文件 SHA-256，便于后续按同一键名比较。

``rival``、``ai.rival`` 和 ``history.historical_rival`` 在存档中是不同的
结构。工具分别保留三类路径，不把 ``ai.rival`` 排名推断成当前已选宿敌，也
不为缺失的结束日期或其他游戏语义补值。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from work import inspect_dissolve_save_pair as bounded
except ModuleNotFoundError:  # direct invocation from an unusual working directory
    sys.path.insert(0, str(ROOT))
    from work import inspect_dissolve_save_pair as bounded


TARGET_TAGS = ("FRA", "POR", "ENG", "BUR", "CAS", "ARA", "AUS")
EXPECTED_SHA256 = (
    "470d9546c4183ce481d0e0d02f843c7c11749f5b3bc475b89cd636742acfa825"
)
DEFAULT_SAVE = Path(
    r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games\llm_diplomacy_insults_returned_20261015_r33c.eu4"
)
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "runtime"
    / "r34-rival-save-baseline-20261016-001"
)

COUNTRY_RE = re.compile(r"^\s*(FRA|POR|ENG|BUR|CAS|ARA|AUS)\s*=\s*\{")
SCALAR_RE = re.compile(r"^\s*([A-Za-z0-9_#]+)\s*=\s*(.*?)\s*$")
BLOCK_RE = re.compile(r"^\s*([A-Za-z0-9_#]+)\s*=\s*\{")
RIVAL_TOKEN_RE = re.compile(r"rival", re.IGNORECASE)
MAX_RAW_SNIPPET_BYTES = 16 * 1024

# These are literal key-name filters.  They select fields already serialized by
# the save; they do not claim that every selected field has one game-level
# meaning.  The complete flattened field map remains in the evidence JSON.
RESOURCE_KEY_TOKENS = (
    "prestige",
    "stability",
    "diplom",
    "power_projection",
    "great_power",
    "manpower",
    "points",
)


def _configure_bounded_reader() -> None:
    """Configure the shared bounded scanner for this process."""

    bounded.TARGET_TAGS = TARGET_TAGS
    bounded.PAIR = frozenset(("FRA", "POR"))
    bounded.COUNTRY_RE = COUNTRY_RE


def _parse_country_entries(capture: Any) -> list[Any]:
    if capture is None or not capture.complete:
        return []
    open_index = capture.text.find("{")
    body = bounded.extract_block(capture.text, open_index)
    return bounded.top_level_entries(body)


def _field_groups(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Partition exact flattened paths without dropping any rival field."""

    direct: dict[str, Any] = {}
    historical: dict[str, Any] = {}
    ai_ranking: dict[str, Any] = {}
    other: dict[str, Any] = {}
    dates: dict[str, Any] = {}
    end_date_candidates: dict[str, Any] = {}
    for key, value in fields.items():
        lowered = key.casefold()
        if "rival" not in lowered:
            continue
        if lowered.startswith("ai.rival"):
            ai_ranking[key] = value
        elif "historical_rival" in lowered:
            historical[key] = value
        elif lowered.startswith("rival"):
            direct[key] = value
            if lowered.endswith(".date") or lowered.endswith(".start_date"):
                dates[key] = value
            if "end" in lowered and "date" in lowered:
                end_date_candidates[key] = value
        else:
            other[key] = value
    return {
        "direct_rival_fields": direct,
        "historical_rival_fields": historical,
        "ai_rival_ranking_fields": ai_ranking,
        "other_rival_related_fields": other,
        "serialized_rival_date_fields": dates,
        "serialized_rival_end_date_candidates": end_date_candidates,
    }


def _resource_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in fields.items()
        if any(token in key.casefold() for token in RESOURCE_KEY_TOKENS)
    }


def _short_raw(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= MAX_RAW_SNIPPET_BYTES:
        return text, False
    head = MAX_RAW_SNIPPET_BYTES // 2
    tail = MAX_RAW_SNIPPET_BYTES - head
    shortened = encoded[:head] + b"\n...<raw snippet truncated>...\n" + encoded[-tail:]
    return shortened.decode("utf-8", "replace"), True


def _rival_raw_fragments(capture: Any) -> list[dict[str, Any]]:
    """Retain exact short lines and blocks whose serialized key contains rival."""

    if capture is None or not capture.complete:
        return []
    lines = capture.text.splitlines(keepends=True)
    fragments: list[dict[str, Any]] = []
    index = 0
    depth = 0
    while index < len(lines):
        line = lines[index]
        global_line = capture.start_line + index
        block_match = BLOCK_RE.match(line)
        if block_match and RIVAL_TOKEN_RE.search(block_match.group(1)):
            block_key = block_match.group(1)
            start = index
            before = depth
            block_depth = before + bounded.brace_delta(line)
            index += 1
            depth = block_depth
            while index < len(lines):
                nested_line = lines[index]
                depth_before = depth
                depth += bounded.brace_delta(nested_line)
                index += 1
                if depth == before and depth_before >= block_depth:
                    break
            raw, truncated = _short_raw("".join(lines[start:index]))
            fragments.append(
                {
                    "kind": "block",
                    "serialized_key": block_key,
                    "line_start": capture.start_line + start,
                    "line_end": capture.start_line + index - 1,
                    "raw": raw,
                    "truncated": truncated,
                }
            )
            continue

        scalar_match = SCALAR_RE.match(line)
        if scalar_match and RIVAL_TOKEN_RE.search(scalar_match.group(1)):
            raw, truncated = _short_raw(line)
            fragments.append(
                {
                    "kind": "scalar",
                    "serialized_key": scalar_match.group(1),
                    "line_start": global_line,
                    "line_end": global_line,
                    "raw": raw,
                    "truncated": truncated,
                }
            )
        depth += bounded.brace_delta(line)
        index += 1
    return fragments


def _diplomat_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key.casefold().startswith("diplomats.")}


def _country_record(tag: str, capture: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "tag": tag,
        "capture": {
            "found": capture is not None,
            "start_line": capture.start_line if capture else None,
            "end_line": capture.end_line if capture else None,
            "complete": bool(capture and capture.complete),
            "bytes_captured": capture.bytes_captured if capture else 0,
        },
        "all_flattened_fields": {},
        "all_block_paths": [],
        "rival": {
            "direct_rival_fields": {},
            "historical_rival_fields": {},
            "ai_rival_ranking_fields": {},
            "other_rival_related_fields": {},
            "serialized_rival_date_fields": {},
            "serialized_rival_end_date_candidates": {},
        },
        "resource_fields": {},
        "diplomat_fields": {},
        "raw_rival_fragments": [],
        "unknown": [],
    }
    if capture is None:
        record["unknown"].append("country_block_not_found")
        return record
    if not capture.complete:
        record["unknown"].append("country_block_capture_incomplete")
        return record
    try:
        entries = _parse_country_entries(capture)
        fields, blocks = bounded.flatten_entries(entries)
    except bounded.SaveParseError as exc:
        record["unknown"].append(f"country_parse_error:{exc}")
        return record
    record["all_flattened_fields"] = fields
    record["all_block_paths"] = blocks
    record["rival"] = _field_groups(fields)
    record["resource_fields"] = _resource_fields(fields)
    record["diplomat_fields"] = _diplomat_fields(fields)
    record["raw_rival_fragments"] = _rival_raw_fragments(capture)
    return record


def scan_save(path: Path, expected_sha256: str = EXPECTED_SHA256) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    _configure_bounded_reader()
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    source["expected_sha256"] = expected_sha256 or None
    source["sha256_matches_expected"] = (
        source["sha256"].casefold() == expected_sha256.casefold()
        if expected_sha256
        else None
    )
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)

    countries = {
        tag: _country_record(tag, scanner.country_captures.get(tag))
        for tag in TARGET_TAGS
    }
    unknown = list(scanner.alliance_parse_unknown)
    for tag, country in countries.items():
        if not country["capture"]["found"]:
            unknown.append(f"country_{tag}_not_found")
        elif not country["capture"]["complete"]:
            unknown.append(f"country_{tag}_capture_incomplete")
        unknown.extend(f"{tag}:{item}" for item in country.get("unknown", []))
    if scanner.duplicate_country_tags:
        unknown.extend(f"duplicate_country_tag:{tag}" for tag in scanner.duplicate_country_tags)
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
        "tool": {
            "name": "inspect_rival_save.py",
            "version": 1,
            "streaming": True,
            "whole_save_read": False,
            "target_tags": list(TARGET_TAGS),
            "max_country_capture_bytes": bounded.MAX_COUNTRY_CAPTURE,
            "resource_key_tokens": list(RESOURCE_KEY_TOKENS),
            "raw_snippet_cap_bytes": MAX_RAW_SNIPPET_BYTES,
            "scanner_source": "work/inspect_dissolve_save_pair.py",
        },
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
        "scope_notes": [
            "rival.* 是国家块中直接序列化的宿敌条目；其 date 字段按原键名保留。",
            "ai.rival.* 是 AI 评分/排名结构，报告单独列出，不推断为当前已选宿敌。",
            "history.historical_rival 是历史字段，报告单独列出。",
            "未观察到 end_date 的结果只适用于目标国家块中含 rival 的字段范围。",
            "resource_fields 按实际键名 token 筛选；完整字段仍保存在 all_flattened_fields。",
        ],
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _report_value(value: object) -> str:
    """Render a raw serialized scalar without adding a second quote layer."""

    if isinstance(value, str):
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            return value
        return value
    return _json(value)


def _format_field_map(fields: object) -> str:
    if not isinstance(fields, dict) or not fields:
        return "（未观察到）"
    return "\n".join(f"- `{key}` = `{_report_value(value)}`" for key, value in fields.items())


def render_report(payload: dict[str, Any]) -> str:
    source = payload["source"]
    parse = payload["parse"]
    lines = [
        "# R34 宿敌基线存档流式取证",
        "",
        "本报告由 `work/inspect_rival_save.py` 生成。工具逐行读取 gamestate，"
        "只保留 FRA、POR、ENG、BUR、CAS、ARA、AUS 七个国家块；完整存档没有进入内存。"
        "JSON 证据中的键和值均来自存档原文解析。国家块中的 `rival.country` 表示"
        "该国家指向的直接 `rival` 条目；`ai.rival.id/value` 仍按独立排名结构记录。",
        "",
        "## 存档与解析完整性",
        "",
        f"- 源文件：`{source['path']}`",
        f"- 容器：`{source.get('container')}`；gamestate：`{source.get('gamestate_member')}`",
        f"- 文件字节数：`{source.get('size_bytes')}`；SHA-256：`{source.get('sha256')}`",
        f"- 预期 SHA-256：`{source.get('expected_sha256')}`；匹配：`{source.get('sha256_matches_expected')}`",
        f"- 存档日期：`{payload['metadata'].get('date')}`；gamestate 行数：`{parse.get('gamestate_line_count')}`",
        f"- countries 完整：`{parse.get('countries_block_complete')}`；括号平衡：`{parse.get('brace_balance_ok')}`；"
        f"diplomacy 完整：`{parse.get('diplomacy_block_complete')}`",
        "",
        "## 国家块边界",
        "",
        "下表行号是 gamestate 的 1-based 行号；字节数是该国家块的 UTF-8 捕获大小。",
        "",
        "| 国家 | 起始行 | 结束行 | 捕获字节 | 完整 |",
        "|---|---:|---:|---:|---|",
    ]
    for tag in TARGET_TAGS:
        capture = payload["countries"][tag]["capture"]
        lines.append(
            f"| `{tag}` | {capture.get('start_line')} | {capture.get('end_line')} | "
            f"{capture.get('bytes_captured')} | `{capture.get('complete')}` |"
        )

    lines.extend([
        "",
        "## 宿敌字段",
        "",
        "`rival.*`、`ai.rival.*` 和 `history.historical_rival` 是存档中的不同字段组。"
        "下列内容保留实际键名，不把 AI 排名、历史宿敌或缺失字段解释成运行时关系。",
        "",
    ])
    for tag in TARGET_TAGS:
        country = payload["countries"][tag]
        rival = country["rival"]
        lines.extend([
            f"### `{tag}`",
            "",
            "直接 `rival` 字段：",
            _format_field_map(rival.get("direct_rival_fields")),
            "",
            "宿敌日期字段（实际序列化键）：",
            _format_field_map(rival.get("serialized_rival_date_fields")),
            "",
            "结束日期候选（只按键名检索）：",
            _format_field_map(rival.get("serialized_rival_end_date_candidates")),
            "",
            "历史宿敌字段：",
            _format_field_map(rival.get("historical_rival_fields")),
            "",
            "`ai.rival` 排名字段：",
            _format_field_map(rival.get("ai_rival_ranking_fields")),
            "",
            "含宿敌键名的原文片段：",
        ])
        fragments = country.get("raw_rival_fragments", [])
        if not fragments:
            lines.append("（未观察到）")
        else:
            for fragment in fragments:
                raw = fragment.get("raw", "").rstrip("\r\n")
                lines.append(
                    f"- `{fragment.get('kind')}` `{fragment.get('serialized_key')}` "
                    f"行 {fragment.get('line_start')}–{fragment.get('line_end')}："
                )
                lines.append("```text")
                lines.append(raw)
                lines.append("```")
        lines.append("")

    lines.extend(["## 威望、外交和其他资源键", ""])
    lines.append(
        "以下字段由实际键名中的 `prestige`、`stability`、`diplom`、"
        "`power_projection`、`great_power`、`manpower` 或 `points` 文字筛选；"
        "数值保持存档原始文本，不转换游戏内部比例。"
    )
    lines.append("")
    for tag in TARGET_TAGS:
        country = payload["countries"][tag]
        lines.extend([
            f"### `{tag}` 资源字段",
            "",
            _format_field_map(country.get("resource_fields")),
            "",
            f"外交官相关字段（`diplomats.*`）：{len(country.get('diplomat_fields', {}))} 个，",
            "完整键值保存在 `evidence.json` 的 `countries.{tag}.diplomat_fields`。",
            "",
        ])

    lines.extend([
        "## 证据范围与后续比较方式",
        "",
        "`evidence.json` 保留每个目标国家的 `all_flattened_fields`、块路径、宿敌分组、"
        "外交官字段、国家块行号和含宿敌键名的原文片段。后续 before/after 存档可以使用"
        "相同脚本和相同国家标签，按 `rival.country`、`rival.date`、资源键值和行号边界"
        "进行字段级比较。",
        "",
        "本次目标国家块中如果没有 `rival.end_date` 或其他结束日期键，证据只记录该有界"
        "字段范围内未观察到该键；报告不会据此推断宿敌机制的完整生命周期。",
        "",
        f"未知项数量：`{len(parse.get('unknown', []))}`。如需逐项复核，请查看"
        " `evidence.json` 的 `parse.unknown`。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE,
                        help="EU4 存档路径；默认读取 R34 指定基线存档")
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256,
                        help="可选源文件 SHA-256；空字符串可关闭匹配检查")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="新鲜输出目录；非空目录会拒绝写入")
    args = parser.parse_args(argv)

    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"output directory is not fresh: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = scan_save(args.save.expanduser().resolve(), args.expected_sha256)
    except (OSError, bounded.SaveParseError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    evidence_path = output_dir / "evidence.json"
    report_path = output_dir / "report.md"
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "evidence": str(evidence_path),
        "report": str(report_path),
        "source_sha256": payload["source"].get("sha256"),
        "sha256_matches_expected": payload["source"].get("sha256_matches_expected"),
        "date": payload["metadata"].get("date"),
        "line_count": payload["parse"].get("gamestate_line_count"),
        "unknown_count": len(payload["parse"].get("unknown", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
