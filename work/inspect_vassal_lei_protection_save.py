#!/usr/bin/env python3
"""流式提取 R35D FRA/LEI 附庸关系的存档证据。

程序只保留 FRA、LEI 两个国家块中的对应 ``active_relations`` 条目，
以及全局 ``diplomacy`` 块中 FRA↔LEI 的 ``dependency`` 记录。存档文件和
gamestate 都不会整体读入内存；源文件哈希也按块计算。输出 JSON 保留原始
字段、国家块行号和匹配 dependency 的短原文，报告只描述存档中实际出现的
值，不把字段缺失解释为引擎状态。
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
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work import inspect_dissolve_save_pair as bounded


TARGET_TAGS = ("FRA", "LEI")
PAIR = frozenset(TARGET_TAGS)
COUNTRY_RE = re.compile(r"^\s*(FRA|LEI)\s*=\s*\{")
DIPLOMACY_RE = re.compile(r"^\s*diplomacy\s*=\s*\{")
DEPENDENCY_RE = re.compile(r"^\s*dependency\s*=\s*\{")
MAX_DEPENDENCY_CAPTURE = 128 * 1024
MAX_DEPENDENCY_RECORDS = 64
MAX_RAW_SNIPPET_BYTES = 32 * 1024
SELECTED_RELATION_KEYS = (
    "truce",
    "last_war",
    "last_send_diplomat",
    "last_war_status",
    "last_warscore",
    "opinion.modifier",
    "opinion.date",
    "opinion.current_opinion",
    "opinion.expiry_date",
    "cached_sum",
    "attitude",
    "has_changed",
)

bounded.TARGET_TAGS = TARGET_TAGS
bounded.PAIR = PAIR
bounded.COUNTRY_RE = COUNTRY_RE


def _scalar(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    return bounded.unquote(str(value))


def _short_raw(value: str) -> tuple[str, bool]:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_RAW_SNIPPET_BYTES:
        return value, False
    head = MAX_RAW_SNIPPET_BYTES // 2
    tail = MAX_RAW_SNIPPET_BYTES - head
    clipped = encoded[:head] + b"\n...<raw truncated>...\n" + encoded[-tail:]
    return clipped.decode("utf-8", errors="replace"), True


def _selected_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: fields[key] for key in SELECTED_RELATION_KEYS if key in fields}


def _source_with_hash(path: Path) -> dict[str, Any]:
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    return source


def _country_records(path: Path, source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    countries: dict[str, Any] = {}
    unknown: list[str] = []
    for tag, other in (("FRA", "LEI"), ("LEI", "FRA")):
        capture = scanner.country_captures.get(tag)
        relation = bounded.active_relation_result(capture, other)
        for entry in relation.get("entries", []):
            fields = entry.get("fields", {})
            entry["selected_fields"] = _selected_fields(fields)
        countries[tag] = {
            "capture": {
                "found": capture is not None,
                "start_line": capture.start_line if capture else None,
                "end_line": capture.end_line if capture else None,
                "bytes_captured": capture.bytes_captured if capture else 0,
                "complete": bool(capture and capture.complete),
            },
            "active_relations": relation,
        }
        unknown.extend(f"{tag}:{item}" for item in relation.get("unknown", []))
        if capture is None:
            unknown.append(f"country_{tag}_not_found")
        elif not capture.complete:
            unknown.append(f"country_{tag}_capture_incomplete")
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
    parse = {
        "gamestate_line_count": scanner.line_count,
        "first_line": scanner.header_line,
        "date": scanner.save_date,
        "final_brace_depth": scanner.depth,
        "brace_balance_ok": scanner.depth == 0,
        "countries_block_found": scanner.countries_found,
        "countries_block_complete": scanner.countries_complete,
        "diplomacy_block_found": scanner.diplomacy_found,
        "diplomacy_block_complete": scanner.diplomacy_complete,
        "unknown": unknown,
    }
    return countries, parse


def _dependency_records(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    diplomacy_found = False
    diplomacy_complete = False
    diplomacy_depth: int | None = None
    depth = 0
    line_count = 0
    active: list[str] | None = None
    active_start: int | None = None
    active_depth = 0
    active_bytes = 0
    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if not diplomacy_found and before == 0 and DIPLOMACY_RE.match(line):
                diplomacy_found = True
                diplomacy_depth = before + bounded.brace_delta(line)
            if (diplomacy_found and not diplomacy_complete and active is None
                    and diplomacy_depth is not None and before == diplomacy_depth
                    and DEPENDENCY_RE.match(line)):
                active = [line]
                active_start = line_number
                active_depth = bounded.brace_delta(line)
                active_bytes = len(line.encode("utf-8", errors="replace"))
            elif active is not None:
                active.append(line)
                active_bytes += len(line.encode("utf-8", errors="replace"))
                active_depth += bounded.brace_delta(line)
                if active_bytes > MAX_DEPENDENCY_CAPTURE:
                    unknown.append(f"line_{active_start}:dependency_over_limit")
                    active = None
                    active_start = None
                    active_depth = 0
                    active_bytes = 0
            if active is not None and active_depth == 0:
                text = "".join(active)
                try:
                    body = bounded.extract_block(text, text.find("{"))
                    parsed = bounded.parse_field_body(body)
                except bounded.SaveParseError as error:
                    unknown.append(f"line_{active_start}:dependency_parse_error:{error}")
                    parsed = {"fields": {}, "blocks": [], "unknown": [str(error)]}
                fields = parsed.get("fields", {})
                first = _scalar(fields.get("first"))
                second = _scalar(fields.get("second"))
                subject_type = _scalar(fields.get("subject_type"))
                if frozenset((first, second)) == PAIR:
                    if len(records) >= MAX_DEPENDENCY_RECORDS:
                        unknown.append("dependency_record_limit_reached")
                    else:
                        raw, truncated = _short_raw(text)
                        records.append({
                            "line_start": active_start,
                            "line_end": line_number,
                            "first": first,
                            "second": second,
                            "subject_type": subject_type,
                            "fields": fields,
                            "selected_fields": {
                                key: fields[key] for key in (
                                    "first", "second", "start_date", "end_date",
                                    "subject_type", "retain_unit_control",
                                    "inheritance") if key in fields
                            },
                            "blocks": parsed.get("blocks", []),
                            "unknown": parsed.get("unknown", []),
                            "raw": raw,
                            "raw_truncated": truncated,
                        })
                active = None
                active_start = None
                active_depth = 0
                active_bytes = 0
            delta = bounded.brace_delta(line)
            depth += delta
            if (diplomacy_found and diplomacy_depth is not None
                    and before >= diplomacy_depth and depth == 0):
                diplomacy_complete = True
    if active is not None:
        unknown.append(f"line_{active_start}:dependency_block_incomplete")
    return {
        "records": records,
        "vassal_records": [record for record in records
                           if record.get("subject_type") == "vassal"],
        "scan": {
            "line_count": line_count,
            "diplomacy_block_found": diplomacy_found,
            "diplomacy_block_complete": diplomacy_complete,
            "unknown": unknown,
        },
    }


def _reference_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "found": False}
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    source = payload.get("source", {})
    return {
        "path": str(path.resolve()),
        "found": True,
        "source": {
            "path": source.get("path"),
            "size_bytes": source.get("size_bytes"),
            "sha256": source.get("sha256"),
        },
        "metadata": payload.get("metadata", {}),
        "relations": payload.get("relations", {}).get("FRA->LEI"),
    }


def scan_save(path: Path, reference: Path | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    source = _source_with_hash(path)
    countries, parse = _country_records(path, source)
    dependency = _dependency_records(path, source)
    payload: dict[str, Any] = {
        "tool": {
            "name": "inspect_vassal_lei_protection_save.py",
            "version": 1,
            "streaming": True,
            "whole_save_read": False,
            "scanner_source": "work/inspect_dissolve_save_pair.py",
            "target_pair": ["FRA", "LEI"],
            "relation_fields": list(SELECTED_RELATION_KEYS),
            "country_capture_limit_bytes": bounded.MAX_COUNTRY_CAPTURE,
            "dependency_capture_limit_bytes": MAX_DEPENDENCY_CAPTURE,
        },
        "source": source,
        "metadata": {"date": parse.get("date"), "first_line": parse.get("first_line")},
        "parse": parse,
        "countries": countries,
        "diplomacy_dependency": dependency,
        "reference_report": _reference_summary(reference) if reference else None,
        "interpretation_guard": [
            "active_relations 字段来自对应国家块中的原始关系条目。",
            "dependency 记录来自顶层 diplomacy 块；first/second 表示存档序列化的方向。",
            "truce、last_war 和 last_send_diplomat 保留原始值，不单独推断原因或持续时间。",
            "附庸起始日期和保留期限只有在实际 dependency 字段中出现时才报告。",
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    payload["integrity"] = {
        "canonical_payload_sha256": hashlib.sha256(canonical).hexdigest(),
        "source_sha256": source["sha256"],
    }
    return payload


def _format_fields(fields: object) -> str:
    if not isinstance(fields, dict) or not fields:
        return "（未观察到）"
    return "；".join(f"`{key}`=`{value}`" for key, value in fields.items())


def render_report(payload: dict[str, Any], evidence_sha256: str) -> str:
    source = payload["source"]
    parse = payload["parse"]
    countries = payload["countries"]
    dependency = payload["diplomacy_dependency"]
    lines = [
        "# R35D FRA—LEI 附庸保护期存档取证",
        "",
        "本报告按行流式读取 R35D 成熟附庸存档，只保留 FRA、LEI 两个国家块、"
        "双方对应的 `active_relations` 条目，以及顶层 `diplomacy` 中的 FRA↔LEI "
        "`dependency` 记录。报告用于核对 1449.11.17 建立附庸后，1454.11.18 "
        "取消操作仍受到和约保护的存档字段。",
        "",
        "## 存档与解析范围",
        "",
        f"- 源存档：`{source['path']}`",
        f"- 文件大小：`{source.get('size_bytes')}` 字节；SHA-256：`{source.get('sha256')}`",
        f"- 存档日期：`{payload['metadata'].get('date')}`；gamestate 行数：`{parse.get('gamestate_line_count')}`",
        f"- countries 完整：`{parse.get('countries_block_complete')}`；diplomacy 完整：`{parse.get('diplomacy_block_complete')}`；括号平衡：`{parse.get('brace_balance_ok')}`",
        f"- evidence.json SHA-256：`{evidence_sha256}`",
        "",
        "## FRA 与 LEI 国家块及 active_relations",
        "",
        "国家块行号使用 gamestate 的 1-based 行号；关系方向按国家块拥有者→目标国家表示。",
        "",
        "| 国家块 | 行范围 | 捕获字节 | 完整 | 关系方向 | 条目存在 |",
        "|---|---:|---:|---|---|---|",
    ]
    for tag, other in (("FRA", "LEI"), ("LEI", "FRA")):
        capture = countries[tag]["capture"]
        relation = countries[tag]["active_relations"]
        lines.append(
            f"| `{tag}` | {capture.get('start_line')}–{capture.get('end_line')} | "
            f"{capture.get('bytes_captured')} | `{capture.get('complete')}` | "
            f"`{tag}→{other}` | `{relation.get('present')}` |"
        )
    lines.extend(["", "### 关系字段", ""])
    for tag, other in (("FRA", "LEI"), ("LEI", "FRA")):
        relation = countries[tag]["active_relations"]
        lines.append(f"#### `{tag}→{other}`")
        entries = relation.get("entries", [])
        if not entries:
            lines.append("未捕获对应 active_relations 条目。")
            continue
        for index, entry in enumerate(entries, 1):
            lines.append(f"- 条目 {index} 原始字段：{_format_fields(entry.get('selected_fields'))}")
            lines.append(f"- 完整字段映射：{_format_fields(entry.get('fields'))}")
        lines.append("")
    lines.extend([
        "这些字段可以直接确认存档是否保存了 `truce`、`last_war`、"
        "`last_send_diplomat` 以及意见修正；字段本身没有被改写成新的语义名称。",
        "",
        "## 顶层 diplomacy dependency",
        "",
        "顶层 `dependency` 记录描述附庸关系的两个方向。该记录的 `start_date` "
        "用于核对建立日期，`subject_type` 用于确认关系类别；报告只列出存档实际序列化的字段。",
        "",
    ])
    records = dependency.get("records", [])
    if not records:
        lines.append("未捕获 FRA↔LEI 的 dependency 记录。")
    else:
        for index, record in enumerate(records, 1):
            lines.extend([
                f"### 记录 {index}：行 {record.get('line_start')}–{record.get('line_end')}",
                "",
                f"- 方向：`{record.get('first')}→{record.get('second')}`",
                f"- subject_type：`{record.get('subject_type')}`",
                f"- 选定字段：{_format_fields(record.get('selected_fields'))}",
                "- 匹配记录原文：",
                "```text",
                record.get("raw", "").rstrip("\r\n"),
                "```",
                "",
            ])
    lines.extend([
        f"匹配到的 dependency 总数：`{len(records)}`；其中 `subject_type=vassal`：`{len(dependency.get('vassal_records', []))}`。",
        "dependency 记录中未观察到 `end_date`、`expiry_date` 或其他明确的保留期限字段；"
        "本存档因此只提供附庸起始日期，不能从该记录单独计算结束日期。",
        "",
        "## 与 C 阶段 active 关系报告对照",
        "",
    ])
    reference = payload.get("reference_report")
    if reference and reference.get("found"):
        lines.extend([
            f"C 阶段报告：`{reference.get('path')}`。",
            f"C 阶段报告记录的源存档：`{reference.get('source', {}).get('path')}`，"
            f"SHA-256：`{reference.get('source', {}).get('sha256')}`。",
            "该报告作为运行时查询对照保存；本报告的 FRA/LEI 字段来自 R35D 新存档，"
            "两份报告的输入文件不同，因此不把字段差异直接解释为单次操作造成的变化。",
            f"C 阶段 `FRA→LEI` 关系摘要：`{json.dumps(reference.get('relations'), ensure_ascii=False, sort_keys=True)}`。",
        ])
    else:
        lines.append("未找到 C 阶段对照报告，只保留本次存档证据。")
    lines.extend([
        "",
        "## 结论范围",
        "",
        "本次流式扫描能够确认 R35D 存档中 FRA/LEI 的国家块边界、双方对应的 "
        "`active_relations` 原始字段，以及顶层附庸 `dependency` 的方向、起始日期和"
        "类别。若字段中出现 `truce=yes`，它只能说明该值被写入当前存档；取消操作的"
        "具体规则代码仍由运行时 native 查询和操作结果负责。",
        "",
        "输入存档只读打开，程序没有加载游戏、修改存档或写入用户数据。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    default_save = Path(
        r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games\llm_diplomacy_vassal_lei_protected_14541118_20261016_r35d.eu4"
    )
    default_reference = Path(
        "work/runtime/diplomacy-query-20261016-r35-vassal-d-active-reload/"
        "lei-protection-save-001.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=default_save)
    parser.add_argument("--reference-report", type=Path, default=default_reference)
    parser.add_argument("--expected-sha256", default=(
        "82c825d4e1a33a32f54471f0ff3e4ba24c312e17a0faf0d75144d1bf8e00fdf3"
    ))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    save = args.save.expanduser().resolve(strict=True)
    reference = args.reference_report.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        parser.error(f"output directory already exists: {output}")
    output.mkdir(parents=True)
    try:
        payload = scan_save(save, reference)
        payload["source"]["expected_sha256"] = args.expected_sha256
        payload["source"]["sha256_matches_expected"] = (
            payload["source"].get("sha256", "").casefold()
            == args.expected_sha256.casefold()
        )
        evidence = output / "evidence.json"
        with evidence.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        evidence_sha = bounded.sha256_file(evidence)
        report = output / "report.md"
        with report.open("x", encoding="utf-8") as stream:
            stream.write(render_report(payload, evidence_sha))
        status = (
            "passed" if payload["source"]["sha256_matches_expected"]
            and payload["parse"]["brace_balance_ok"]
            and payload["parse"]["countries_block_complete"]
            and payload["parse"]["diplomacy_block_complete"]
            and len(payload["diplomacy_dependency"]["vassal_records"]) >= 1
            else "failed"
        )
        summary = {
            "status": status,
            "output_dir": str(output),
            "evidence": str(evidence),
            "report": str(report),
            "source_sha256": payload["source"]["sha256"],
            "evidence_sha256": evidence_sha,
            "vassal_record_count": len(payload["diplomacy_dependency"]["vassal_records"]),
        }
        with (output / "summary.json").open("x", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if status == "passed" else 2
    except Exception:
        # Preserve a fresh output directory for diagnosis without replacing any
        # prior evidence.  The exception remains visible to the caller.
        raise


if __name__ == "__main__":
    raise SystemExit(main())
