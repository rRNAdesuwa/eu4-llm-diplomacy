#!/usr/bin/env python3
"""流式准备 R62 贸易战争 CB 查询背景。

脚本从 R61 Grant Independence 已接受存档复制一份全新 EU4txt 保存，只在
顶层 ``diplomacy`` 块末尾增加一个真实格式的 ``casus_belli`` 记录：
FRA -> ENG、``cb_trade_war_triggered``、当前日期 1455.8.20，并沿用已有
记录的 ``end_date`` 字段布局（1457.8.20）。脚本不启动游戏、不投递外交请求，
也不把 fixture 的写入当成原生合法性证明。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from work.prepare_r61_country_scenes import (
        BLOCK_RE,
        MAX_BLOCK_BYTES,
        brace_delta,
        fields_at_depth,
        iter_block_lines,
        parse_assignment,
        replace_assignment,
        stripped,
    )
except ModuleNotFoundError:  # direct execution from a copied work directory
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work.prepare_r61_country_scenes import (
        BLOCK_RE,
        MAX_BLOCK_BYTES,
        brace_delta,
        fields_at_depth,
        iter_block_lines,
        parse_assignment,
        replace_assignment,
        stripped,
    )


SAVE_DIR = Path(
    r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games"
)
DEFAULT_SOURCE = SAVE_DIR / (
    "llm_diplomacy_peace_country_independence_accepted_20261019_r61.eu4"
)
DEFAULT_OUTPUT = SAVE_DIR / (
    "llm_diplomacy_declarewar_trade_query_20261019_r62.eu4"
)
DEFAULT_RUNTIME = Path(__file__).resolve().parent / "runtime" / (
    "r62-trade-cb-scene-20261019-001"
)

TARGET_TYPE = "cb_trade_war_triggered"
TARGET_FIRST = "FRA"
TARGET_SECOND = "ENG"
TARGET_START_DATE = "1455.8.20"
TARGET_END_DATE = "1457.8.20"
MAX_DIPLOMACY_BLOCK_BYTES = 4 * 1024 * 1024
MAX_HEADER_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash a file in bounded chunks; never materialize a save in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def scan_save_date(path: Path) -> str | None:
    """Read only the header-sized prefix for the save date."""

    consumed = 0
    with path.open("rb") as stream:
        while consumed < MAX_HEADER_BYTES:
            line = stream.readline()
            if not line:
                break
            consumed += len(line)
            assignment = parse_assignment(line)
            if assignment is not None and assignment[0] in {"date", "save_date"}:
                return assignment[1]
    return None


def _field_order(fields: dict[str, tuple[int, str]]) -> list[str]:
    return [key for key, _value in sorted(fields.items(), key=lambda item: item[1][0])]


def _public_cb_record(
    block: list[bytes], line_start: int, line_end: int
) -> dict[str, Any]:
    fields = fields_at_depth(block, 1)
    selected = {
        key: fields[key][1]
        for key in ("type", "first", "second", "start_date", "end_date")
        if key in fields
    }
    return {
        "line_start": line_start,
        "line_end": line_end,
        "bytes": sum(len(line) for line in block),
        "fields": selected,
        "field_order": _field_order(fields),
    }


def scan_diplomacy_casus_belli(path: Path) -> dict[str, Any]:
    """Scan only top-level diplomacy/casus_belli blocks with bounded capture."""

    depth = 0
    line_count = 0
    diplomacy_found = False
    diplomacy_complete = False
    diplomacy_depth: int | None = None
    casus_belli_count = 0
    end_date_count = 0
    target_exact: list[dict[str, Any]] = []
    target_type_count = 0
    template_public: dict[str, Any] | None = None
    template_block: list[bytes] | None = None

    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            line_count += 1
            before = depth
            marker = stripped(line)

            if before == 0 and marker == b"diplomacy={":
                if diplomacy_found:
                    raise ValueError("multiple top-level diplomacy blocks")
                diplomacy_found = True
                diplomacy_depth = before + brace_delta(line)

            if diplomacy_found and before == diplomacy_depth:
                match = BLOCK_RE.match(line)
                if match and match.group("key") == b"casus_belli":
                    block, end_line = iter_block_lines(
                        stream,
                        line,
                        line_count,
                        max_bytes=MAX_DIPLOMACY_BLOCK_BYTES,
                    )
                    line_start = line_count
                    line_count = end_line
                    casus_belli_count += 1
                    fields = fields_at_depth(block, 1)
                    type_value = fields.get("type", (None, None))[1]
                    first = fields.get("first", (None, None))[1]
                    second = fields.get("second", (None, None))[1]
                    if "end_date" in fields:
                        end_date_count += 1
                    public = _public_cb_record(block, line_start, end_line)
                    if (
                        type_value == TARGET_TYPE
                        and first == TARGET_FIRST
                        and second == TARGET_SECOND
                    ):
                        target_exact.append(public)
                    if type_value == TARGET_TYPE:
                        target_type_count += 1
                    if template_block is None and {
                        "type",
                        "first",
                        "second",
                        "start_date",
                        "end_date",
                    }.issubset(fields):
                        template_block = list(block)
                        template_public = public
                    # The captured block is balanced, so the outer depth is
                    # unchanged; continue avoids counting its braces twice.
                    continue

            depth += brace_delta(line)
            if (
                diplomacy_found
                and diplomacy_depth is not None
                and before >= diplomacy_depth
                and depth == 0
            ):
                diplomacy_complete = True

    if template_block is None or template_public is None:
        raise ValueError("no casus_belli template with end_date was found")

    return {
        "path": str(path),
        "line_count": line_count,
        "diplomacy_found": diplomacy_found,
        "diplomacy_complete": diplomacy_complete,
        "final_brace_depth": depth,
        "casus_belli_count": casus_belli_count,
        "end_date_count": end_date_count,
        "target_exact": target_exact,
        "target_type_count": target_type_count,
        "template": template_public,
        "template_block": template_block,
        "complete": diplomacy_found
        and diplomacy_complete
        and depth == 0
        and template_block is not None,
    }


def _make_inserted_block(template: list[bytes]) -> tuple[list[bytes], dict[str, Any]]:
    """Copy a real dated CB block and replace only its direct assignments."""

    fields = fields_at_depth(template, 1)
    required = {"type", "first", "second", "start_date", "end_date"}
    missing = sorted(required.difference(fields))
    if missing:
        raise ValueError(f"CB template misses direct fields: {missing}")

    output = list(template)
    replacements = {
        "type": TARGET_TYPE,
        "first": TARGET_FIRST,
        "second": TARGET_SECOND,
        "end_date": TARGET_END_DATE,
        "start_date": TARGET_START_DATE,
    }
    for key, value in replacements.items():
        index = fields[key][0]
        output[index] = replace_assignment(output[index], key, value)

    after = fields_at_depth(output, 1)
    if any(after[key][1] != value for key, value in replacements.items()):
        raise ValueError("inserted CB fields did not match requested values")
    return output, {
        "fields": {key: after[key][1] for key in _field_order(after) if key in required},
        "field_order": _field_order(after),
        "bytes": sum(len(line) for line in output),
        "line_count": len(output),
    }


def _transform_save(
    source: Path, destination: Path, inserted_block: list[bytes]
) -> dict[str, Any]:
    """Copy source byte-for-byte and insert before diplomacy's closing brace."""

    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"refusing to reuse existing partial output: {partial}")

    depth = 0
    line_count = 0
    output_line_count = 0
    diplomacy_found = False
    diplomacy_depth: int | None = None
    inserted = False
    inserted_before_source_line: int | None = None
    output_digest = hashlib.sha256()
    try:
        with source.open("rb") as stream, partial.open("xb") as raw_out:

            def write_bytes(data: bytes) -> None:
                raw_out.write(data)
                output_digest.update(data)

            while True:
                line = stream.readline()
                if not line:
                    break
                line_count += 1
                before = depth
                marker = stripped(line)
                if before == 0 and marker == b"diplomacy={":
                    if diplomacy_found:
                        raise ValueError("multiple top-level diplomacy blocks")
                    diplomacy_found = True
                    diplomacy_depth = before + brace_delta(line)

                if (
                    diplomacy_found
                    and not inserted
                    and diplomacy_depth is not None
                    and before == diplomacy_depth
                    and marker == b"}"
                ):
                    insertion = b"".join(inserted_block)
                    write_bytes(insertion)
                    output_line_count += len(inserted_block)
                    inserted = True
                    inserted_before_source_line = line_count

                write_bytes(line)
                output_line_count += 1
                depth += brace_delta(line)

            if not diplomacy_found or not inserted:
                raise ValueError("top-level diplomacy close was not found exactly once")
            if depth != 0:
                raise ValueError(f"source brace depth is {depth}, expected 0")
        partial.rename(destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise

    return {
        "source_line_count": line_count,
        "output_line_count": output_line_count,
        "inserted_before_source_line": inserted_before_source_line,
        "inserted_line_count": len(inserted_block),
        "inserted_bytes": sum(len(line) for line in inserted_block),
        "output_sha256": output_digest.hexdigest(),
        "non_inserted_bytes_copied": True,
    }


def _json_scan(scan: dict[str, Any]) -> dict[str, Any]:
    """Drop the private raw template bytes before writing JSON."""

    return {key: value for key, value in scan.items() if key != "template_block"}


def _write_report(runtime: Path, report: dict[str, Any]) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "report.json").open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    mutation = report["mutation"]
    source = report["source"]
    output = report["output"]
    template = report["observed_format"]["template"]
    lines = [
        "# R62 贸易战争 CB 查询背景",
        "",
        "本报告记录一个只用于查询的独立 EU4txt fixture。脚本从 R61 Grant Independence 已接受存档流式复制保存，只在顶层 `diplomacy` 块插入一条 `casus_belli`；没有启动游戏、重载或投递外交请求。",
        "",
        f"- 源存档：`{source['path']}`",
        f"- 源 SHA-256：`{source['sha256']}`，日期 `{source['date']}`，大小 {source['size_bytes']} 字节",
        f"- 新存档：`{output['path']}`",
        f"- 新存档 SHA-256：`{output['sha256']}`，大小 {output['size_bytes']} 字节",
        "",
        "## 实际保存格式与插入内容",
        "",
        f"源存档的 `casus_belli` 共 {mutation['source_casus_belli_count']} 条，其中 {mutation['source_end_date_count']} 条带有 `end_date`。复用的真实模板位于源第 {template['line_start']}–{template['line_end']} 行，字段顺序为 `{', '.join(template['field_order'])}`。",
        "",
        "插入的直接字段为：",
        "",
        "```text",
        "casus_belli={",
        '\ttype="cb_trade_war_triggered"',
        '\tfirst="FRA"',
        '\tsecond="ENG"',
        "\tend_date=1457.8.20",
        "\tstart_date=1455.8.20",
        "}",
        "```",
        "",
        f"插入发生在源第 {mutation['inserted_before_source_line']} 行的 `diplomacy` 关闭行之前；复制了 {mutation['inserted_line_count']} 行、{mutation['inserted_bytes']} 字节。源中原本没有相同 `type/first/second` 组合，生成后恰有一条，CB 总数 {mutation['source_casus_belli_count']}→{mutation['destination_casus_belli_count']}。",
        "",
        "## 完整性",
        "",
        "流式扫描在源和目标中都确认顶层 `diplomacy` 括号闭合；复制路径对插入块以外的每个字节保持原样。国家、战争、关系和军队内容没有被脚本解析后重写。",
        "",
        "`whole_save_loaded=false`；单个 CB 块按有界缓冲读取，未将整份存档加载到内存。",
        "",
    ]
    (runtime / "report.md").write_text("\n".join(lines), encoding="utf-8")


def build_fixture(source: Path, destination: Path, runtime: Path) -> dict[str, Any]:
    if not source.exists():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise ValueError("source and output must be different files")
    source_date = scan_save_date(source)
    if source_date != TARGET_START_DATE:
        raise ValueError(
            f"source save date must be {TARGET_START_DATE}, observed {source_date!r}"
        )
    source_scan = scan_diplomacy_casus_belli(source)
    if not source_scan["complete"]:
        raise ValueError("source diplomacy scan is incomplete")
    if source_scan["target_exact"]:
        raise ValueError(
            "source already contains target FRA->ENG cb_trade_war_triggered: "
            f"{source_scan['target_exact']}"
        )
    inserted_block, inserted = _make_inserted_block(source_scan["template_block"])
    source_sha = sha256_file(source)
    transform = _transform_save(source, destination, inserted_block)
    destination_scan = scan_diplomacy_casus_belli(destination)
    if not destination_scan["complete"]:
        raise ValueError("destination diplomacy scan is incomplete")
    target_rows = destination_scan["target_exact"]
    expected = {
        "type": TARGET_TYPE,
        "first": TARGET_FIRST,
        "second": TARGET_SECOND,
        "end_date": TARGET_END_DATE,
        "start_date": TARGET_START_DATE,
    }
    if len(target_rows) != 1 or target_rows[0]["fields"] != expected:
        raise ValueError(f"destination target CB mismatch: {target_rows}")
    if destination_scan["casus_belli_count"] != source_scan["casus_belli_count"] + 1:
        raise ValueError("destination CB count did not increase by one")
    if destination_scan["end_date_count"] != source_scan["end_date_count"] + 1:
        raise ValueError("destination end_date count did not increase by one")

    output_size = destination.stat().st_size
    report: dict[str, Any] = {
        "schema": "r62.trade_cb_scene.v1",
        "status": "passed",
        "source": {
            "path": str(source),
            "name": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": source_sha,
            "date": source_date,
            "container": "EU4txt_plain",
        },
        "output": {
            "path": str(destination),
            "name": destination.name,
            "size_bytes": output_size,
            "sha256": transform["output_sha256"],
            "date": scan_save_date(destination),
        },
        "observed_format": {
            "template": source_scan["template"],
            "end_date_template": True,
            "date_format": "YYYY.M.D",
        },
        "mutation": {
            "scope": "top_level_diplomacy.casus_belli_only",
            "source_casus_belli_count": source_scan["casus_belli_count"],
            "destination_casus_belli_count": destination_scan["casus_belli_count"],
            "source_end_date_count": source_scan["end_date_count"],
            "destination_end_date_count": destination_scan["end_date_count"],
            "existing_target_count_before": len(source_scan["target_exact"]),
            "target_count_after": len(target_rows),
            "inserted_block": inserted,
            "inserted_before_source_line": transform["inserted_before_source_line"],
            "inserted_line_count": transform["inserted_line_count"],
            "inserted_bytes": transform["inserted_bytes"],
            "non_inserted_bytes_copied": transform["non_inserted_bytes_copied"],
        },
        "checks": {
            "source_date_is_current": source_date == TARGET_START_DATE,
            "source_diplomacy_complete": source_scan["complete"],
            "source_target_absent": len(source_scan["target_exact"]) == 0,
            "target_direction": {
                "first": TARGET_FIRST,
                "second": TARGET_SECOND,
                "matches": True,
            },
            "destination_diplomacy_complete": destination_scan["complete"],
            "destination_target_exact": target_rows[0]["fields"] == expected,
            "casus_belli_count_plus_one": destination_scan["casus_belli_count"]
            == source_scan["casus_belli_count"] + 1,
            "end_date_count_plus_one": destination_scan["end_date_count"]
            == source_scan["end_date_count"] + 1,
            "non_inserted_bytes_copied": True,
        },
        "streaming": {
            "whole_save_loaded": False,
            "source_scan_block_limit_bytes": MAX_DIPLOMACY_BLOCK_BYTES,
            "hash_chunk_bytes": 1024 * 1024,
            "source_line_count": source_scan["line_count"],
            "destination_line_count": destination_scan["line_count"],
        },
    }
    _write_report(runtime, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args(argv)
    report = build_fixture(args.source, args.output, args.runtime)
    print(
        json.dumps(
            {
                "status": report["status"],
                "source": report["source"]["name"],
                "output": report["output"]["name"],
                "target": report["mutation"]["target_count_after"],
                "report": str(args.runtime / "report.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
