#!/usr/bin/env python3
"""Stream a bounded before/after comparison for EU4 peace-operation saves.

The tool reads only the requested country blocks and province blocks from each
``EU4txt``/ZIP gamestate.  It keeps the serialized treasury, owner,
controller, and core fields together with their gamestate line numbers.  An
optional bounded active-war scan is included when the existing war scanner can
find a block containing both requested countries.

The comparison reports serialized observations and arithmetic deltas.  It
does not attribute a treasury or province change to the peace operation: the
two saves may be separated by normal game time and other game events.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work.inspect_declare_war_save_pair import compare_scans, scan_active_wars


DEFAULT_OUTPUT = ROOT / "work" / "runtime" / "peace-save-pair-20261016-001" / "report.json"
HASH_CHUNK = 1024 * 1024
MAX_COUNTRY_CAPTURE = 8 * 1024 * 1024
MAX_PROVINCE_CAPTURE = 1024 * 1024
MAX_CORE_TAGS = 256
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
COUNTRIES_RE = re.compile(r"^\s*countries\s*=\s*\{")
PROVINCES_RE = re.compile(r"^\s*provinces\s*=\s*\{")
COUNTRY_RE_TEMPLATE = r"^\s*({tags})\s*=\s*\{{"
PROVINCE_RE = re.compile(r"^\s*(-?\d+)\s*=\s*\{")
DIRECT_SCALAR_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
BLOCK_START_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{")
CORE_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{1,5}\b")


class PeaceSaveParseError(RuntimeError):
    """Raised when a save cannot be inspected within the bounded contract."""


@dataclass
class BlockCapture:
    key: str
    serialized_key: str | None
    start_line: int
    end_line: int | None
    text: str
    complete: bool
    bytes_captured: int
    bytes_seen: int
    truncated: bool = False


def validate_tag(value: str, option: str) -> str:
    value = value.strip().upper()
    if not TAG_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"{option} must be an EU4 country tag")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _capture_scalar_line(capture: BlockCapture, key: str) -> list[dict[str, Any]]:
    """Return direct scalar occurrences and absolute gamestate line numbers."""

    result: list[dict[str, Any]] = []
    local_depth = 0
    for index, line in enumerate(capture.text.splitlines(), 0):
        before = local_depth
        match = DIRECT_SCALAR_RE.match(line)
        if before == 1 and match and match.group(1) == key:
            raw = match.group(2).strip()
            result.append(
                {
                    "field_name": key,
                    "raw": raw,
                    "value": bounded.unquote(raw),
                    "line": capture.start_line + index,
                }
            )
        local_depth += bounded.brace_delta(line)
    return result


def _capture_top_block(capture: BlockCapture, key: str) -> dict[str, Any] | None:
    """Capture one direct nested block, retaining raw text and line range."""

    local_depth = 0
    active: list[str] | None = None
    active_start: int | None = None
    active_depth: int | None = None
    for index, line in enumerate(capture.text.splitlines(), 0):
        before = local_depth
        if active is None and before == 1:
            match = BLOCK_START_RE.match(line)
            if match and match.group(1) == key:
                active = [line]
                active_start = capture.start_line + index
                active_depth = before + bounded.brace_delta(line)
            elif match:
                # Nested sibling starts are still accounted for by the depth
                # update below; only the requested block is retained.
                pass
        elif active is not None:
            active.append(line)
        local_depth += bounded.brace_delta(line)
        if (
            active is not None
            and active_depth is not None
            and local_depth == 1
            and before >= active_depth
        ):
            return {
                "field_name": key,
                "line_start": active_start,
                "line_end": capture.start_line + index,
                "raw": "".join(active),
            }
    return None


def _parse_cores(capture: BlockCapture) -> dict[str, Any]:
    block = _capture_top_block(capture, "cores")
    if block is None:
        return {
            "field_name": "cores",
            "found": False,
            "tags": [],
            "line_start": None,
            "line_end": None,
            "raw": None,
            "unknown": ["cores_block_not_found"],
        }
    raw = str(block["raw"])
    open_index = raw.find("{")
    close_index = raw.rfind("}")
    body = raw[open_index + 1 : close_index if close_index > open_index else None]
    tags: list[str] = []
    for token in CORE_TOKEN_RE.findall(body):
        if token not in tags:
            tags.append(token)
        if len(tags) >= MAX_CORE_TAGS:
            break
    unknown: list[str] = []
    if len(tags) >= MAX_CORE_TAGS:
        unknown.append(f"cores_tag_limit_reached:{MAX_CORE_TAGS}")
    return {
        "field_name": "cores",
        "found": True,
        "tags": tags,
        "line_start": block["line_start"],
        "line_end": block["line_end"],
        "raw": raw,
        "unknown": unknown,
    }


def _field_occurrence(capture: BlockCapture, key: str) -> dict[str, Any]:
    occurrences = _capture_scalar_line(capture, key)
    if not occurrences:
        return {
            "field_name": key,
            "found": False,
            "raw": None,
            "value": None,
            "line": None,
            "occurrences": [],
            "unknown": [f"{key}_not_found"],
        }
    unknown: list[str] = []
    if len(occurrences) > 1:
        unknown.append(f"duplicate_{key}_fields:{len(occurrences)}")
    item = dict(occurrences[-1])
    item.update({"found": True, "occurrences": occurrences, "unknown": unknown})
    return item


def _parse_country(capture: BlockCapture | None, tag: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "tag": tag,
        "found": capture is not None,
        "start_line": capture.start_line if capture else None,
        "end_line": capture.end_line if capture else None,
        "complete": bool(capture and capture.complete),
        "bytes_captured": capture.bytes_captured if capture else 0,
        "bytes_seen": capture.bytes_seen if capture else 0,
        "treasury": None,
        "unknown": [],
    }
    if capture is None:
        item["unknown"].append("country_block_not_found")
        return item
    if not capture.complete:
        item["unknown"].append("country_capture_incomplete")
        return item
    treasury = _field_occurrence(capture, "treasury")
    item["treasury"] = treasury
    item["unknown"].extend(treasury["unknown"])
    return item


def _parse_province(capture: BlockCapture | None, province_id: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "province_id": province_id,
        "serialized_id": capture.serialized_key if capture else None,
        "found": capture is not None,
        "start_line": capture.start_line if capture else None,
        "end_line": capture.end_line if capture else None,
        "complete": bool(capture and capture.complete),
        "bytes_captured": capture.bytes_captured if capture else 0,
        "bytes_seen": capture.bytes_seen if capture else 0,
        "fields": {},
        "unknown": [],
    }
    if capture is None:
        item["unknown"].append("province_block_not_found")
        return item
    if not capture.complete:
        item["unknown"].append("province_capture_incomplete")
        return item
    for key in ("owner", "controller", "previous_controller"):
        field = _field_occurrence(capture, key)
        item["fields"][key] = field
        item["unknown"].extend(field["unknown"])
    cores = _parse_cores(capture)
    item["fields"]["cores"] = cores
    item["unknown"].extend(cores["unknown"])
    return item


class PeaceSaveScanner:
    """Single-pass scanner for dynamic country and province targets."""

    def __init__(self, country_tags: tuple[str, str], province_ids: tuple[int, ...]):
        self.country_tags = country_tags
        self.province_ids = set(province_ids)
        tag_pattern = "|".join(re.escape(tag) for tag in country_tags)
        self.country_re = re.compile(COUNTRY_RE_TEMPLATE.format(tags=tag_pattern))
        self.depth = 0
        self.line_count = 0
        self.header_line: str | None = None
        self.date: str | None = None
        self.player: str | None = None
        self.date_line: int | None = None
        self.player_line: int | None = None
        self.countries_found = False
        self.countries_complete = False
        self.countries_depth: int | None = None
        self.provinces_found = False
        self.provinces_complete = False
        self.provinces_depth: int | None = None
        self.current: dict[str, Any] | None = None
        self.captures: dict[str, dict[str, BlockCapture]] = {"countries": {}, "provinces": {}}
        # Current EU4 gamestates serialize the main province table with a
        # negative key (for example ``-177``) even though the public province
        # identifier is 177.  Accept either spelling and retain the exact
        # serialized key in the capture metadata.
        self.province_key_map: dict[str, int] = {}
        for province_id in self.province_ids:
            self.province_key_map[str(province_id)] = province_id
            if province_id:
                self.province_key_map[str(-province_id)] = province_id
        self.duplicates: list[str] = []
        self.unknown: list[str] = []

    def _finish(self, end_line: int | None, complete: bool) -> None:
        if self.current is None:
            return
        text = "".join(self.current["lines"])
        cap = BlockCapture(
            key=self.current["key"],
            serialized_key=self.current.get("serialized_key"),
            start_line=self.current["start_line"],
            end_line=end_line,
            text=text,
            complete=complete and not self.current["truncated"],
            bytes_captured=sum(len(line.encode("utf-8", "replace")) for line in self.current["lines"]),
            bytes_seen=self.current["bytes_seen"],
            truncated=self.current["truncated"],
        )
        group = self.current["group"]
        if cap.key in self.captures[group]:
            self.duplicates.append(f"duplicate_{group}:{cap.key}")
        else:
            self.captures[group][cap.key] = cap
        self.current = None

    def _start_capture(
        self,
        group: str,
        key: str,
        line_number: int,
        line: str,
        before: int,
        serialized_key: str | None = None,
    ) -> None:
        self.current = {
            "group": group,
            "key": key,
            "start_line": line_number,
            "serialized_key": serialized_key,
            "lines": [line],
            "bytes_seen": len(line.encode("utf-8", "replace")),
            "truncated": False,
            "block_depth": before + bounded.brace_delta(line),
        }

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
                self.current["bytes_seen"] += len(line.encode("utf-8", "replace"))
                cap_limit = (
                    MAX_COUNTRY_CAPTURE
                    if self.current["group"] == "countries"
                    else MAX_PROVINCE_CAPTURE
                )
                if not self.current["truncated"]:
                    if self.current["bytes_seen"] <= cap_limit:
                        self.current["lines"].append(line)
                    else:
                        self.current["truncated"] = True
                        self.current["lines"] = []

            if not self.countries_found and before == 0 and COUNTRIES_RE.match(line):
                self.countries_found = True
                self.countries_depth = before + bounded.brace_delta(line)
            if not self.provinces_found and before == 0 and PROVINCES_RE.match(line):
                self.provinces_found = True
                self.provinces_depth = before + bounded.brace_delta(line)

            if (
                self.current is None
                and not self.countries_complete
                and self.countries_depth is not None
                and before == self.countries_depth
            ):
                match = self.country_re.match(line)
                if match:
                    self._start_capture("countries", match.group(1), line_number, line, before)
            if (
                self.current is None
                and not self.provinces_complete
                and self.provinces_depth is not None
                and before == self.provinces_depth
            ):
                match = PROVINCE_RE.match(line)
                if match:
                    serialized_key = match.group(1)
                    province_id = self.province_key_map.get(serialized_key)
                    if province_id is not None:
                        self._start_capture(
                            "provinces",
                            str(province_id),
                            line_number,
                            line,
                            before,
                            serialized_key,
                        )

            delta = bounded.brace_delta(line)
            self.depth += delta

            if self.current is not None:
                block_depth = self.current["block_depth"]
                parent_depth = self.countries_depth if self.current["group"] == "countries" else self.provinces_depth
                if parent_depth is not None and self.depth == parent_depth and before >= block_depth:
                    self._finish(line_number, True)

            if self.countries_found and self.countries_depth is not None and self.depth == 0 and before >= self.countries_depth:
                self.countries_complete = True
            if self.provinces_found and self.provinces_depth is not None and self.depth == 0 and before >= self.provinces_depth:
                self.provinces_complete = True

        if self.current is not None:
            self._finish(None, False)


def _scan_gamestate(path: Path, source: dict[str, Any], tags: tuple[str, str], province_ids: tuple[int, ...]) -> dict[str, Any]:
    scanner = PeaceSaveScanner(tags, province_ids)
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    countries = {
        tag: _parse_country(scanner.captures["countries"].get(tag), tag)
        for tag in tags
    }
    provinces = {
        str(province_id): _parse_province(
            scanner.captures["provinces"].get(str(province_id)), province_id
        )
        for province_id in province_ids
    }
    unknown = list(scanner.unknown)
    for tag, item in countries.items():
        unknown.extend(f"country_{tag}:{value}" for value in item["unknown"])
    for province_id, item in provinces.items():
        unknown.extend(f"province_{province_id}:{value}" for value in item["unknown"])
    unknown.extend(scanner.duplicates)
    if not scanner.countries_found:
        unknown.append("countries_block_not_found")
    elif not scanner.countries_complete:
        unknown.append("countries_block_incomplete")
    if province_ids:
        if not scanner.provinces_found:
            unknown.append("provinces_block_not_found")
        elif not scanner.provinces_complete:
            unknown.append("provinces_block_incomplete")
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    return {
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
            "countries_block_found": scanner.countries_found,
            "countries_block_complete": scanner.countries_complete,
            "provinces_block_found": scanner.provinces_found,
            "provinces_block_complete": scanner.provinces_complete if province_ids else None,
            "unknown": unknown,
        },
        "countries": countries,
        "provinces": provinces,
    }


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip().strip('"'))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _treasury_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old = before.get("treasury") or {}
    new = after.get("treasury") or {}
    old_raw = old.get("raw")
    new_raw = new.get("raw")
    old_number = _decimal(old_raw)
    new_number = _decimal(new_raw)
    delta = new_number - old_number if old_number is not None and new_number is not None else None
    return {
        "field_name": "treasury",
        "before": {"raw": old_raw, "line": old.get("line")},
        "after": {"raw": new_raw, "line": new.get("line")},
        "delta": _decimal_text(delta),
        "numeric_comparison_available": delta is not None,
        "interpretation": "serialized treasury observation; delta is not attributed solely to the peace operation",
    }


def _province_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "province_id": before.get("province_id", after.get("province_id")),
        "before_found": bool(before.get("found")),
        "after_found": bool(after.get("found")),
        "field_changes": {},
        "changed": False,
    }
    for key in ("owner", "controller", "previous_controller", "cores"):
        old = (before.get("fields") or {}).get(key, {})
        new = (after.get("fields") or {}).get(key, {})
        old_value = old.get("value") if key != "cores" else old.get("tags")
        new_value = new.get("value") if key != "cores" else new.get("tags")
        changed = old_value != new_value
        result["field_changes"][key] = {
            "changed": changed,
            "before": old,
            "after": new,
        }
        result["changed"] = result["changed"] or changed
    return result


def _war_scan(path: Path, source: dict[str, Any], actor: str, recipient: str) -> dict[str, Any]:
    try:
        return scan_active_wars(path, source, actor, recipient)
    except Exception as exc:  # preserve save evidence even if the optional scan is malformed
        return {
            "line_count": None,
            "final_brace_depth": None,
            "brace_balance_ok": False,
            "active_war_blocks_seen": None,
            "matching_active_wars": [],
            "unknown": [f"active_war_scan_error:{exc}"],
        }


def scan_save(path: Path, actor: str, recipient: str, province_ids: tuple[int, ...]) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise PeaceSaveParseError(f"save path is not a file: {resolved}")
    source = bounded.detect_container(resolved)
    source["sha256"] = sha256_file(resolved)
    parsed = _scan_gamestate(resolved, source, (actor, recipient), province_ids)
    parsed["source"] = source
    parsed["war_scan"] = _war_scan(resolved, source, actor, recipient)
    parsed["parse"]["unknown"].extend(parsed["war_scan"].get("unknown", []))
    return parsed


def _war_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    try:
        return compare_scans({"war_scan": before["war_scan"]}, {"war_scan": after["war_scan"]})
    except Exception as exc:
        return {"unknown": [f"active_war_compare_error:{exc}"]}


def compare_pair(before: dict[str, Any], after: dict[str, Any], actor: str, recipient: str, province_ids: tuple[int, ...]) -> dict[str, Any]:
    countries = {
        tag: {
            "treasury": _treasury_delta(before["countries"].get(tag, {}), after["countries"].get(tag, {}))
        }
        for tag in (actor, recipient)
    }
    provinces = {
        str(province_id): _province_diff(
            before["provinces"].get(str(province_id), {"province_id": province_id}),
            after["provinces"].get(str(province_id), {"province_id": province_id}),
        )
        for province_id in province_ids
    }
    return {
        "countries": countries,
        "provinces": provinces,
        "war": _war_comparison(before, after),
        "attribution": "Observed before/after serialization only. Treasury, ownership, controller, core, and war changes are not assigned solely to the peace operation.",
    }


def parse_province_ids(values: list[str] | None, repeated: list[int] | None) -> tuple[int, ...]:
    result: list[int] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                try:
                    result.append(int(part))
                except ValueError as exc:
                    raise PeaceSaveParseError(f"invalid province id: {part!r}") from exc
    result.extend(repeated or [])
    unique: list[int] = []
    for province_id in result:
        if province_id not in unique:
            unique.append(province_id)
    if len(unique) > 16:
        raise PeaceSaveParseError("at most 16 province ids may be requested")
    return tuple(unique)


def build_payload(baseline: Path, result: Path, actor: str, recipient: str, province_ids: tuple[int, ...]) -> dict[str, Any]:
    before = scan_save(baseline, actor, recipient, province_ids)
    after = scan_save(result, actor, recipient, province_ids)
    return {
        "tool": {
            "name": "work/inspect_peace_save_pair.py",
            "version": 1,
            "streaming": True,
            "whole_gamestate_read": False,
            "hash_chunk_bytes": HASH_CHUNK,
            "country_capture_limit_bytes": MAX_COUNTRY_CAPTURE,
            "province_capture_limit_bytes": MAX_PROVINCE_CAPTURE,
            "active_war_capture_limit_bytes": 2 * 1024 * 1024,
            "treasury_field_name": "treasury",
            "scanner_helpers": [
                "work/inspect_dissolve_save_pair.py",
                "work/inspect_declare_war_save_pair.py",
            ],
        },
        "pair": {
            "actor": actor,
            "recipient": recipient,
            "province_ids": list(province_ids),
        },
        "before": before,
        "after": after,
        "comparison": compare_pair(before, after, actor, recipient, province_ids),
        "limitations": [
            "treasury 的明确序列化字段名是 treasury；ai.treasury 等嵌套字段不计入本报告。",
            "treasury delta 是两个存档之间的数值差，不代表议和操作单独产生的金额变化。",
            "province owner/controller/cores 只报告所选省份；缺失、未闭合或超过边界的块保留在 unknown。",
            "active_war 只作为可复用的序列化战争关系观察，不替代 native 和平执行结果。",
        ],
    }


def _json_text(value: Any, limit: int | None = None) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    if limit is not None and len(text.encode("utf-8")) > limit:
        encoded = text.encode("utf-8")[:limit]
        return encoded.decode("utf-8", errors="ignore") + "\n...[truncated]"
    return text


def render_report(payload: dict[str, Any]) -> str:
    pair = payload["pair"]
    lines = [
        "# 和平操作前后存档对照",
        "",
        "工具按行扫描 EU4txt 或 ZIP gamestate，只保留 actor/recipient 国家块和请求省份块；完整 gamestate 不进入内存。",
        "",
        f"actor={pair['actor']} recipient={pair['recipient']} province_ids={pair['province_ids']}",
        "treasury 字段名为国家块内的 treasury；报告中的 delta 只表示两个存档的序列化差值。",
        "",
    ]
    for label in ("before", "after"):
        side = payload[label]
        source = side["source"]
        metadata = side["metadata"]
        lines.extend([
            f"## {label}",
            "",
            f"file={source['path']}",
            f"size_bytes={source.get('size_bytes')} sha256={source.get('sha256')}",
            f"container={source.get('container')} gamestate={source.get('gamestate_member')}",
            f"date={metadata.get('date')} player={metadata.get('player')}",
            f"gamestate_lines={side['parse'].get('gamestate_line_count')} brace_balance_ok={side['parse'].get('brace_balance_ok')}",
            "",
            "countries:",
        ])
        for tag, country in side["countries"].items():
            treasury = country.get("treasury") or {}
            lines.append(
                f"- {tag}: lines={country.get('start_line')}-{country.get('end_line')} "
                f"complete={country.get('complete')} treasury={treasury.get('raw')} "
                f"treasury_line={treasury.get('line')}"
            )
        lines.append("")
        lines.append("provinces:")
        for province_id, province in side["provinces"].items():
            fields = province.get("fields", {})
            owner = fields.get("owner", {}).get("value")
            controller = fields.get("controller", {}).get("value")
            cores = fields.get("cores", {}).get("tags", [])
            lines.append(
                f"- {province_id}: lines={province.get('start_line')}-{province.get('end_line')} "
                f"complete={province.get('complete')} owner={owner} controller={controller} cores={cores}"
            )
        lines.append("")
        lines.append(f"parse_unknown={_json_text(side['parse'].get('unknown'))}")
        lines.append("")
    lines.extend([
        "## before_after",
        "",
        "countries:",
        _json_text(payload["comparison"]["countries"]),
        "",
        "provinces:",
        _json_text(payload["comparison"]["provinces"]),
        "",
        "war_serialization:",
        _json_text(payload["comparison"]["war"]),
        "",
        payload["comparison"]["attribution"],
        "",
        "## boundaries",
        "",
        "本报告不把时间间隔内的 treasury、owner、controller、cores 或战争变化归因于单一议和操作；unknown 集中记录字段缺失、块未闭合和可选战争扫描问题。",
        "",
    ])
    return "\n".join(lines)


def _output_paths(output: Path) -> tuple[Path, Path]:
    output = output.expanduser().resolve()
    if output.suffix.casefold() == ".json":
        return output, output.with_suffix(".md")
    return output / "peace-save-pair.json", output / "peace-save-pair.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--actor", required=True, type=lambda value: validate_tag(value, "--actor"))
    parser.add_argument("--recipient", required=True, type=lambda value: validate_tag(value, "--recipient"))
    parser.add_argument("--province-id", action="append", type=int, default=[], help="request one province; repeat at most 16 times")
    parser.add_argument("--province-ids", action="append", default=[], help="comma-separated province ids; at most 16 total")
    parser.add_argument("--output", required=True, type=Path, help="JSON output path, or directory when no .json suffix is used")
    args = parser.parse_args(argv)
    if args.actor == args.recipient:
        parser.error("--actor and --recipient must differ")
    try:
        province_ids = parse_province_ids(args.province_ids, args.province_id)
        json_path, markdown_path = _output_paths(args.output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        if json_path.exists() or markdown_path.exists():
            raise PeaceSaveParseError(f"refusing to overwrite existing output: {json_path}")
        payload = build_payload(
            args.baseline.expanduser().resolve(),
            args.result.expanduser().resolve(),
            args.actor,
            args.recipient,
            province_ids,
        )
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(render_report(payload), encoding="utf-8")
        print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "sha256": {"baseline": payload["before"]["source"]["sha256"], "result": payload["after"]["source"]["sha256"]}}, ensure_ascii=False))
        return 0
    except PeaceSaveParseError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
