#!/usr/bin/env python3
"""流式检查两个旧宿敌存档是否适合作为和平运行基线。

该工具复用 :mod:`work.inspect_rival_save` 的有限国家块解析，并额外逐行
捕获有限大小的 ``active_war`` 块。工具不会把 ZIP 的 gamestate 成员读入
内存，也不会启动游戏或修改存档。输出中的 ``is_at_war``、宿敌字段、日期、
外交点字段和战争参与块都保留存档中的实际键名和值；它们只用于准备运行
上下文，不是 R34 Rival 接口的完成证据。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work import inspect_rival_save as rival
from work.local_config import user_data


DEFAULT_SAVE_NAMES = (
    "llm_authorized_whitepeace_v7.eu4",
    "llm_ai_whitepeace_accepted.eu4",
)
DEFAULT_OUTPUT_DIR = ROOT / "work" / "runtime" / "r34-rival-peace-baseline-20261016-001"
ACTIVE_WAR_RE = re.compile(r"^\s*active_war\s*=\s*\{")
MAX_ACTIVE_WAR_CAPTURE = 2 * 1024 * 1024


def _date_tuple(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def _scalar_values(value: Any) -> list[str]:
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_scalar_values(item))
        return values
    if value is None:
        return []
    return [str(value)]


def _unquoted(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _war_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Keep exact fields useful for identifying the current war sides."""

    tokens = (
        "participant",
        "attacker",
        "defender",
        "original",
        "war_score",
        "action",
        "goal",
        "casus_belli",
        "start_date",
    )
    return {
        key: value
        for key, value in fields.items()
        if any(token in key.casefold() for token in tokens)
    }


def scan_active_wars(path: Path) -> dict[str, Any]:
    """Stream all bounded ``active_war`` blocks and retain FRA-related ones."""

    source = bounded.detect_container(path)
    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    depth = 0
    line_count = 0
    current: dict[str, Any] | None = None

    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if current is None and ACTIVE_WAR_RE.match(line):
                current = {
                    "line_start": line_number,
                    "parent_depth": before,
                    "block_depth": before + bounded.brace_delta(line),
                    "lines": [],
                    "bytes_captured": 0,
                    "too_large": False,
                }

            if current is not None:
                encoded_length = len(line.encode("utf-8", "replace"))
                current["bytes_captured"] += encoded_length
                if not current["too_large"]:
                    if current["bytes_captured"] <= MAX_ACTIVE_WAR_CAPTURE:
                        current["lines"].append(line)
                    else:
                        current["too_large"] = True
                        current["lines"] = []

            depth += bounded.brace_delta(line)
            if (
                current is not None
                and depth == current["parent_depth"]
                and before >= current["block_depth"]
            ):
                line_start = current["line_start"]
                line_end = line_number
                if current["too_large"]:
                    unknown.append(
                        f"active_war_lines_{line_start}_{line_end}_exceeded_"
                        f"{MAX_ACTIVE_WAR_CAPTURE}_bytes"
                    )
                else:
                    text = "".join(current["lines"])
                    parsed = bounded.parse_structured_block(text)
                    fields = parsed.get("fields", {})
                    scalar_values = [
                        _unquoted(item)
                        for value in fields.values()
                        for item in _scalar_values(value)
                    ]
                    involves_fra = "FRA" in scalar_values
                    if involves_fra:
                        records.append(
                            {
                                "line_start": line_start,
                                "line_end": line_end,
                                "bytes_captured": current["bytes_captured"],
                                "involves_fra": True,
                                "fields": _war_fields(fields),
                                "blocks": parsed.get("blocks", []),
                                "unknown": parsed.get("unknown", []),
                            }
                        )
                    unknown.extend(parsed.get("unknown", []))
                current = None

    if current is not None:
        unknown.append(f"active_war_unclosed_at_line_{current['line_start']}")
    if depth != 0:
        unknown.append(f"final_brace_depth:{depth}")
    return {
        "source": source,
        "line_count": line_count,
        "final_brace_depth": depth,
        "brace_balance_ok": depth == 0,
        "active_wars_involving_fra": records,
        "unknown": sorted(set(unknown)),
    }


def read_meta_fields(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    """Read only the small ``meta`` member to obtain the serialized save date."""

    fields: dict[str, Any] = {}
    if source.get("container") == "zip":
        with zipfile.ZipFile(path, "r") as archive:
            try:
                raw_stream = archive.open("meta", "r")
            except KeyError:
                return {"unknown": ["meta_member_not_found"]}
            with raw_stream:
                with io.TextIOWrapper(
                    raw_stream, encoding="utf-8-sig", errors="replace"
                ) as stream:
                    for line in stream:
                        match = re.match(
                            r"^\s*(date|save_game|player)\s*=\s*([^\r\n]+)",
                            line,
                        )
                        if match:
                            fields[match.group(1)] = match.group(2).strip()
        return fields
    return {"unknown": ["plain_save_has_no_separate_meta_member"]}


def _fra_summary(
    scan: dict[str, Any], wars: dict[str, Any], save_date: Any
) -> dict[str, Any]:
    country = scan["countries"]["FRA"]
    fields = country.get("all_flattened_fields", {})
    resources = country.get("resource_fields", {})
    diplomatic_candidates = {
        key: value
        for key, value in resources.items()
        if any(
            token in key.casefold()
            for token in ("diplomacy", "diplomatic", "diplo_", "point")
        )
    }
    diplomatic_balance_fields = {
        key: value
        for key, value in fields.items()
        if any(
            token in key.casefold()
            for token in (
                "diplomatic_points",
                "diplomatic_power",
                "diplo_points",
                "diplo_power",
                "monarch_power",
            )
        )
    }
    war_related_fields = {
        key: value
        for key, value in fields.items()
        if any(token in key.casefold() for token in ("war", "battle", "participant"))
    }
    is_at_war = fields.get("is_at_war")
    active = wars["active_wars_involving_fra"]
    parse_unknown = list(scan["parse"].get("unknown", [])) + list(wars["unknown"])
    if is_at_war == "no" and not active and not parse_unknown:
        suitable: bool | None = True
        reason = "FRA 的原始 is_at_war=no，且未捕获涉及 FRA 的 active_war。"
    elif is_at_war == "yes" or active:
        suitable = False
        reason = "FRA 的原始战争状态或 active_war 证据表明仍存在战争参与。"
    else:
        suitable = None
        reason = "战争状态字段或战争块解析不完整，不能把该存档判作和平基线。"
    last_war_ended = fields.get("last_war_ended")
    context_candidate = False
    context_reason = "没有足够的 FRA 当前战争字段支持和平上下文候选判定。"
    if not active and not parse_unknown:
        current_date_tuple = _date_tuple(save_date)
        last_war_tuple = _date_tuple(last_war_ended)
        if current_date_tuple is not None and last_war_tuple is not None:
            context_candidate = last_war_tuple <= current_date_tuple
            context_reason = (
                f"未捕获涉及 FRA 的 active_war，且 last_war_ended={last_war_ended} "
                f"不晚于存档日期 {save_date}。"
            )
        elif not active:
            context_candidate = True
            context_reason = "未捕获涉及 FRA 的 active_war，但缺少可比较的当前战争日期；仍需运行时复核。"
    return {
        "is_at_war_raw": is_at_war,
        "current_rival_fields": country["rival"].get("direct_rival_fields", {}),
        "rival_date_fields": country["rival"].get("serialized_rival_date_fields", {}),
        "rival_end_date_candidates": country["rival"].get(
            "serialized_rival_end_date_candidates", {}
        ),
        "diplomatic_point_candidates": diplomatic_candidates,
        "diplomatic_point_balance_fields": diplomatic_balance_fields,
        "war_related_country_fields": war_related_fields,
        "resource_fields": resources,
        "active_wars_involving_fra": active,
        "peace_baseline_suitable": suitable,
        "peace_baseline_reason": reason,
        "peace_context_candidate": context_candidate,
        "peace_context_reason": context_reason,
        "parse_unknown": parse_unknown,
        "country_capture": country["capture"],
    }


def inspect_one(path: Path) -> dict[str, Any]:
    scan = rival.scan_save(path, expected_sha256="")
    wars = scan_active_wars(path)
    meta = read_meta_fields(path, scan["source"])
    metadata = {**scan["metadata"], **meta}
    return {
        "source": scan["source"],
        "metadata": metadata,
        "parse": scan["parse"],
        "fra": _fra_summary(scan, wars, metadata.get("date")),
        "war_scan": wars,
        "tool": {
            "rival_parser": "work/inspect_rival_save.py",
            "active_war_parser": "work/inspect_rival_peace_baselines.py",
            "streaming": True,
            "whole_gamestate_read": False,
            "active_war_capture_limit_bytes": MAX_ACTIVE_WAR_CAPTURE,
        },
    }


def _render_map(mapping: dict[str, Any]) -> list[str]:
    if not mapping:
        return ["（未观察到）"]
    return [f"- `{key}` = `{json.dumps(value, ensure_ascii=False)}`" for key, value in mapping.items()]


def render_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# R34B Rival 和平运行基线准备取证",
        "",
        "本报告对两个旧存档执行只读、流式解析。报告用于选择后续 Rival 实验的",
        "和平上下文，不计入 R34B 新接口的完成证据。宿敌、日期、外交点和战争参与",
        "字段均按存档原始键名记录；没有把字段缺失解释成机制结论。",
        "",
        "## 判定口径",
        "",
        "只有在 `countries.FRA.is_at_war=no`、没有捕获涉及 FRA 的 `active_war`、",
        "且两个流式解析器都没有完整性错误时，工具才把存档标为适合作为和平基线。",
        "该判定只表示存档适合准备运行上下文，不代表 Rival 接口已经执行或验收。",
        "",
    ]
    for result in results:
        source = result["source"]
        fra = result["fra"]
        lines.extend([
            f"## `{Path(source['path']).name}`",
            "",
            f"- 源路径：`{source['path']}`",
            f"- 文件大小：`{source.get('size_bytes')}` bytes；SHA-256：`{source.get('sha256')}`",
            f"- gamestate：`{source.get('gamestate_member')}`；存档日期：`{result['metadata'].get('date')}`",
            f"- gamestate 行数：`{result['parse'].get('gamestate_line_count')}`；括号平衡：`{result['parse'].get('brace_balance_ok')}`",
            f"- FRA 国家块：`{fra['country_capture']}`",
            "",
            "### FRA 战争参与",
            "",
            f"- 原始 `is_at_war`：`{fra['is_at_war_raw']}`",
            f"- 涉及 FRA 的 `active_war` 数量：`{len(fra['active_wars_involving_fra'])}`",
            "- FRA 国家块中的战争相关原始字段：",
            *_render_map(fra["war_related_country_fields"]),
        ])
        if fra["active_wars_involving_fra"]:
            for war in fra["active_wars_involving_fra"]:
                lines.extend([
                    "",
                    f"- 行 {war['line_start']}–{war['line_end']}，捕获 `{war['bytes_captured']}` bytes：",
                    *[f"  - `{key}` = `{json.dumps(value, ensure_ascii=False)}`" for key, value in war["fields"].items()],
                ])
        else:
            lines.append("- 未捕获涉及 FRA 的 `active_war` 块。")
        lines.extend([
            "",
            "### FRA 当前宿敌与日期",
            "",
            *(_render_map(fra["current_rival_fields"])),
            "",
            "宿敌日期字段：",
            *(_render_map(fra["rival_date_fields"])),
            "",
            "宿敌结束日期候选字段：",
            *(_render_map(fra["rival_end_date_candidates"])),
            "",
            "### FRA 外交点候选字段",
            "",
            "明确的外交点余额键：",
            *_render_map(fra["diplomatic_point_balance_fields"]),
            "",
            "名称含外交或 points 的其他原始键（不能单独解释为外交点余额）：",
            *_render_map(fra["diplomatic_point_candidates"]),
            "",
            f"严格和平基线判定：`{fra['peace_baseline_suitable']}`。{fra['peace_baseline_reason']}",
            f"和平上下文候选：`{fra['peace_context_candidate']}`。{fra['peace_context_reason']}",
            "",
            f"解析未知项数量：`{len(fra['parse_unknown'])}`。",
            "",
        ])
    lines.extend([
        "## 证据边界",
        "",
        "两个旧存档只用于准备运行上下文。R34B 的接口完成证据仍来自新进程中的",
        "Rival 查询事件、候选谓词结果、日期/暂停绑定和公共查询报告；本报告不替代",
        "那些运行时证据。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save",
        action="append",
        type=Path,
        help="旧存档路径；可重复。默认读取两个 whitepeace 存档。",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    paths = args.save or [user_data() / "save games" / name for name in DEFAULT_SAVE_NAMES]
    output = args.output_dir.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory is not fresh: {output}")
    output.mkdir(parents=True, exist_ok=True)
    results = [inspect_one(path.expanduser().resolve()) for path in paths]
    evidence = {
        "tool": "work/inspect_rival_peace_baselines.py",
        "purpose": "R34B Rival 和平运行上下文准备；不作为接口完成证据",
        "sources": results,
    }
    (output / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(render_report(results), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output),
        "evidence": str(output / "evidence.json"),
        "report": str(output / "report.md"),
        "sources": [
            {
                "path": item["source"]["path"],
                "sha256": item["source"]["sha256"],
                "date": item["metadata"].get("date"),
                "is_at_war_raw": item["fra"]["is_at_war_raw"],
                "active_war_count": len(item["fra"]["active_wars_involving_fra"]),
                "peace_baseline_suitable": item["fra"]["peace_baseline_suitable"],
                "peace_context_candidate": item["fra"]["peace_context_candidate"],
            }
            for item in results
        ],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
