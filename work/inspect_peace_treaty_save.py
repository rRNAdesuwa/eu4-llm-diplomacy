#!/usr/bin/env python3
"""Stream the serialized ``war_reparations`` records from an EU4 save.

EU4 stores a war-reparations relation as a small top-level block::

    war_reparations={
        first="PAYING_COUNTRY"
        second="RECEIVING_COUNTRY"
        end_date=1458.8.14
        start_date=1448.8.14
    }

The reader keeps only these bounded blocks.  It does not load the complete
gamestate into memory and it does not change a save.  The public role names
``payer`` and ``claimant`` are a projection of the serialized ``first`` and
``second`` fields; the raw field mapping is retained in every record so a
native-side interpretation can be reviewed separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded


HASH_CHUNK = 1024 * 1024
MAX_REPARATIONS_CAPTURE = 128 * 1024
MAX_RAW_EXCERPT = 8 * 1024
MAX_REPARATIONS_RECORDS = 1024
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
WAR_REPARATIONS_RE = re.compile(r"^\s*war_reparations\s*=\s*\{")
SERIALIZED_FIELD_NAMES = ("first", "second", "start_date", "end_date")


class TreatySaveParseError(RuntimeError):
    """Raised when a save cannot be inspected within the bounded contract."""


def validate_tag(value: str, option: str) -> str:
    tag = value.strip().upper()
    if not TAG_RE.fullmatch(tag):
        raise argparse.ArgumentTypeError(
            f"{option} must be an uppercase EU4 country tag of 1-6 letters/digits"
        )
    return tag


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _scalar_values(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_scalar_values(item))
        return result
    if value is None:
        return []
    return [str(value)]


def _last_field(fields: dict[str, Any], key: str) -> tuple[str | None, bool]:
    values = _scalar_values(fields.get(key))
    if not values:
        return None, False
    return bounded.unquote(values[-1]), len(values) > 1


def _inline_serialized_fields(body: str) -> dict[str, Any]:
    """Recover the four known scalar fields when a fixture uses one-line blocks."""

    fields: dict[str, Any] = {}
    for key in SERIALIZED_FIELD_NAMES:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(key)}\s*=\s*(\"(?:\\\\.|[^\"])*\"|[^\s}}]+)"
        )
        values = [match.group(1) for match in pattern.finditer(body)]
        if values:
            fields[key] = values[0] if len(values) == 1 else values
    return fields


def _date_tuple(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    text = value.strip().strip('"')
    parts = text.split(".")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
    except ValueError:
        return None
    if year < 0 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return year, month, day


def _date_status(
    save_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    save_key = _date_tuple(save_date)
    start_key = _date_tuple(start_date)
    end_key = _date_tuple(end_date)
    result: dict[str, Any] = {
        "save_date": save_date,
        "start_date": start_date,
        "end_date": end_date,
        "comparison_available": bool(save_key and start_key and end_key),
        "window_contains_save_date": None,
        "status": "unknown",
    }
    if not (save_key and start_key and end_key):
        return result
    # The status is deliberately a serialized date-window observation.  EU4
    # may perform expiry work at a date tick, so callers should use the raw
    # start/end fields when a boundary-day decision matters.
    in_window = start_key <= save_key < end_key
    result["window_contains_save_date"] = in_window
    result["status"] = "active" if in_window else (
        "future" if save_key < start_key else "expired_or_boundary"
    )
    return result


def parse_war_reparations_block(
    text: str,
    *,
    line_start: int,
    line_end: int | None,
    bytes_captured: int,
    bytes_seen: int,
    complete: bool,
    scope_depth: int,
    save_date: str | None,
    index: int,
) -> dict[str, Any]:
    """Parse one bounded serialized block while retaining source field names."""

    record: dict[str, Any] = {
        "index": index,
        "kind": "war_reparations",
        "line_start": line_start,
        "line_end": line_end,
        "scope_depth": scope_depth,
        "scope": "gamestate_top_level" if scope_depth == 1 else "nested_gamestate",
        "complete": bool(complete),
        "bytes_captured": bytes_captured,
        "bytes_seen": bytes_seen,
        "fields": {},
        "payer": None,
        "claimant": None,
        "start_date": None,
        "end_date": None,
        "date_status": _date_status(save_date, None, None),
        "unknown": [],
    }
    if not complete:
        record["unknown"].append("war_reparations_capture_incomplete")
        return record

    try:
        open_index = text.find("{")
        body = bounded.extract_block(text, open_index)
        entries = bounded.top_level_entries(body)
        fields, _blocks = bounded.flatten_entries(entries)
        # The shipped saves put one scalar on each line.  The small fallback
        # also makes the bounded reader safe for compact test fixtures without
        # changing the raw fields retained from the native block.
        fields.update(_inline_serialized_fields(body))
    except Exception as exc:
        record["unknown"].append(f"war_reparations_parse_error:{exc}")
        return record

    raw_fields: dict[str, Any] = {}
    for key, value in fields.items():
        raw_fields[key] = value
    record["fields"] = raw_fields
    first, duplicate_first = _last_field(fields, "first")
    second, duplicate_second = _last_field(fields, "second")
    start_date, duplicate_start = _last_field(fields, "start_date")
    end_date, duplicate_end = _last_field(fields, "end_date")
    record["payer"] = first
    record["claimant"] = second
    record["start_date"] = start_date
    record["end_date"] = end_date
    record["date_status"] = _date_status(save_date, start_date, end_date)
    record["role_mapping"] = {
        "payer": {"serialized_field": "first", "value": first},
        "claimant": {"serialized_field": "second", "value": second},
    }
    if first is None:
        record["unknown"].append("first_not_found")
    if second is None:
        record["unknown"].append("second_not_found")
    if start_date is None:
        record["unknown"].append("start_date_not_found")
    if end_date is None:
        record["unknown"].append("end_date_not_found")
    if duplicate_first:
        record["unknown"].append("duplicate_first")
    if duplicate_second:
        record["unknown"].append("duplicate_second")
    if duplicate_start:
        record["unknown"].append("duplicate_start_date")
    if duplicate_end:
        record["unknown"].append("duplicate_end_date")

    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= MAX_RAW_EXCERPT:
        record["raw_excerpt"] = text
        record["raw_excerpt_truncated"] = False
    else:
        record["raw_excerpt"] = encoded[:MAX_RAW_EXCERPT].decode("utf-8", "replace")
        record["raw_excerpt_truncated"] = True
    return record


class TreatySaveScanner:
    """Single-pass bounded scanner for serialized war-reparations blocks."""

    def __init__(self, save_date_hint: str | None = None):
        self.depth = 0
        self.line_count = 0
        self.header_line: str | None = None
        self.date = save_date_hint
        self.date_line: int | None = None
        self.player: str | None = None
        self.player_line: int | None = None
        self.current: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self.total_records = 0
        self.records_truncated = False
        self.unknown: list[str] = []

    def _finish(self, end_line: int | None, complete: bool) -> None:
        if self.current is None:
            return
        current = self.current
        text = "".join(current["lines"])
        self.total_records += 1
        record = parse_war_reparations_block(
            text,
            line_start=current["start_line"],
            line_end=end_line,
            bytes_captured=sum(
                len(line.encode("utf-8", "replace")) for line in current["lines"]
            ),
            bytes_seen=current["bytes_seen"],
            complete=complete and not current["truncated"],
            scope_depth=current["scope_depth"],
            save_date=self.date,
            index=self.total_records,
        )
        if len(self.records) < MAX_REPARATIONS_RECORDS:
            self.records.append(record)
        else:
            self.records_truncated = True
        self.current = None

    def consume(self, stream: TextIO) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            if line_number == 1:
                self.header_line = line.rstrip("\r\n")
            before = self.depth
            if before == 0:
                date_match = re.match(r"^\s*date\s*=\s*([^\r\n]+)", line)
                if date_match and self.date is None:
                    self.date = bounded.unquote(date_match.group(1).strip())
                    self.date_line = line_number
                player_match = re.match(r"^\s*player\s*=\s*([^\r\n]+)", line)
                if player_match and self.player is None:
                    self.player = bounded.unquote(player_match.group(1).strip())
                    self.player_line = line_number

            if self.current is not None and line_number != self.current["start_line"]:
                current = self.current
                current["bytes_seen"] += len(line.encode("utf-8", "replace"))
                if not current["truncated"]:
                    if current["bytes_seen"] <= MAX_REPARATIONS_CAPTURE:
                        current["lines"].append(line)
                    else:
                        current["truncated"] = True
                        current["lines"] = []

            if self.current is None and WAR_REPARATIONS_RE.match(line):
                self.current = {
                    "start_line": line_number,
                    "scope_depth": before,
                    "lines": [line],
                    "bytes_seen": len(line.encode("utf-8", "replace")),
                    "truncated": False,
                    "block_depth": before + bounded.brace_delta(line),
                }

            delta = bounded.brace_delta(line)
            self.depth += delta
            if (
                self.current is not None
                and self.depth == self.current["scope_depth"]
                and before >= self.current["block_depth"]
            ):
                self._finish(line_number, True)

        if self.current is not None:
            self._finish(None, False)


def scan_save(path: Path, payer: str, claimant: str) -> dict[str, Any]:
    """Scan one save and return all bounded treaty records plus pair matches."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise TreatySaveParseError(f"save path is not a file: {resolved}")
    payer = validate_tag(payer, "payer")
    claimant = validate_tag(claimant, "claimant")
    if payer == claimant:
        raise TreatySaveParseError("payer and claimant must differ")

    source = bounded.detect_container(resolved)
    source["sha256"] = sha256_file(resolved)
    scanner = TreatySaveScanner()
    with bounded.open_gamestate(resolved, source) as stream:
        scanner.consume(stream)

    records = scanner.records
    matches = [
        record
        for record in records
        if record.get("complete")
        and record.get("payer") == payer
        and record.get("claimant") == claimant
    ]
    reverse_matches = [
        record
        for record in records
        if record.get("complete")
        and record.get("payer") == claimant
        and record.get("claimant") == payer
    ]
    unknown = list(scanner.unknown)
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    if scanner.total_records == 0:
        unknown.append("war_reparations_block_not_found")
    if scanner.records_truncated:
        unknown.append(f"war_reparations_record_limit_reached:{MAX_REPARATIONS_RECORDS}")
    for record in records:
        unknown.extend(
            f"record_{record['index']}:{item}" for item in record.get("unknown", [])
        )

    return {
        "source": source,
        "metadata": {
            "first_line": scanner.header_line,
            "date": scanner.date,
            "date_line": scanner.date_line,
            "player": scanner.player,
            "player_line": scanner.player_line,
        },
        "parse": {
            "gamestate_line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "war_reparations_block_count": scanner.total_records,
            "war_reparations_records_complete": not scanner.records_truncated,
            "unknown": unknown,
        },
        "query": {
            "payer": payer,
            "claimant": claimant,
            "exact_pair_present": bool(matches),
            "matching_count": len(matches),
            "reverse_pair_present": bool(reverse_matches),
            "reverse_matching_count": len(reverse_matches),
            "matching_records": matches,
            "reverse_matching_records": reverse_matches,
        },
        "war_reparations": {
            "records": records,
            "total_records": scanner.total_records,
            "records_returned": len(records),
            "records_truncated": scanner.records_truncated,
            "role_fields": {
                "payer": "first",
                "claimant": "second",
                "start_date": "start_date",
                "end_date": "end_date",
            },
        },
    }


def build_payload(save: Path, payer: str, claimant: str) -> dict[str, Any]:
    snapshot = scan_save(save, payer, claimant)
    return {
        "tool": {
            "name": "work/inspect_peace_treaty_save.py",
            "version": 1,
            "streaming": True,
            "whole_gamestate_read": False,
            "hash_chunk_bytes": HASH_CHUNK,
            "war_reparations_capture_limit_bytes": MAX_REPARATIONS_CAPTURE,
            "max_records_returned": MAX_REPARATIONS_RECORDS,
            "serialized_role_mapping": {
                "payer": "first",
                "claimant": "second",
            },
        },
        "save": snapshot,
        "limitations": [
            "R47A 结果存档实际观察到的 war_reparations 块位于 gamestate 顶层，字段为 first、second、start_date、end_date。",
            "payer/claimant 是 first/second 的结构化投影；每条记录保留 fields 和 role_mapping，便于与原生方向合同核对。",
            "date_status 只按保存日期与序列化起止日期做窗口观察；结束日边界不替代原生到期规则。",
            "没有匹配记录表示该存档没有对应方向的序列化 war_reparations，不表示请求一定不合法或尚未结算。",
        ],
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def render_report(payload: dict[str, Any]) -> str:
    save = payload["save"]
    query = save["query"]
    source = save["source"]
    metadata = save["metadata"]
    records = save["war_reparations"]["records"]
    lines = [
        "# 战争赔款存档结构检查",
        "",
        "工具按行扫描 EU4 gamestate，只保留 war_reparations 块；完整存档不进入内存。",
        "",
        f"save={source.get('path')}",
        f"size_bytes={source.get('size_bytes')} sha256={source.get('sha256')}",
        f"container={source.get('container')} gamestate={source.get('gamestate_member')}",
        f"date={metadata.get('date')} player={metadata.get('player')}",
        f"query payer={query['payer']} claimant={query['claimant']}",
        f"exact_pair_present={query['exact_pair_present']} matching_count={query['matching_count']}",
        f"reverse_pair_present={query['reverse_pair_present']} reverse_matching_count={query['reverse_matching_count']}",
        "",
        "## 序列化字段",
        "",
        "- `first` 映射为付款国 `payer`。",
        "- `second` 映射为受益国 `claimant`。",
        "- `start_date` 和 `end_date` 原样保留；`date_status` 只表示保存日期窗口观察。",
        "",
        f"共发现 {save['war_reparations']['total_records']} 个 war_reparations 块，返回 {len(records)} 个。",
        "",
    ]
    for record in records:
        lines.extend([
            f"### 记录 {record['index']}（行 {record['line_start']}–{record['line_end']}）",
            "",
            f"payer={record.get('payer')} claimant={record.get('claimant')} ",
            f"start_date={record.get('start_date')} end_date={record.get('end_date')} ",
            f"date_status={record.get('date_status', {}).get('status')}",
            "",
            f"fields={_json_text(record.get('fields', {}))}",
            "",
        ])
    lines.extend([
        "## 解析完整性",
        "",
        _json_text(save["parse"]),
        "",
        "没有匹配的方向只说明当前存档没有该方向的序列化记录；它不替代原生规则、执行结果或条款接受度判断。",
        "",
    ])
    return "\n".join(lines)


def _output_paths(output: Path) -> tuple[Path, Path]:
    output = output.expanduser().resolve()
    if output.suffix.casefold() == ".json":
        return output, output.with_suffix(".md")
    return output / "peace-treaty-save.json", output / "peace-treaty-save.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--payer", required=True, type=lambda value: validate_tag(value, "--payer"))
    parser.add_argument("--claimant", required=True, type=lambda value: validate_tag(value, "--claimant"))
    parser.add_argument("--output", required=True, type=Path, help="JSON file or output directory")
    args = parser.parse_args(argv)
    try:
        json_path, markdown_path = _output_paths(args.output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        if json_path.exists() or markdown_path.exists():
            raise TreatySaveParseError(f"refusing to overwrite existing output: {json_path}")
        payload = build_payload(
            args.save.expanduser().resolve(),
            args.payer,
            args.claimant,
        )
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(render_report(payload), encoding="utf-8")
        print(json.dumps({
            "json": str(json_path),
            "markdown": str(markdown_path),
            "sha256": payload["save"]["source"].get("sha256"),
            "matching_count": payload["save"]["query"]["matching_count"],
        }, ensure_ascii=False))
        return 0
    except TreatySaveParseError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
