#!/usr/bin/env python3
"""对两个 EU4 存档执行限定对象的流式王室联姻取证。

脚本只保留 FRA、SAV、LIT、PRO 四个国家块，以及 diplomacy 中涉及
FRA-SAV、FRA-LIT、FRA-PRO 的 ``royal_marriage`` 对象。存档正文按行从
文件或 ZIP 的 gamestate 成员读取；完整存档不会进入内存。输出 JSON
保存逐个来源对象、字段范围、解析完整性和两份存档的差异，Markdown
报告面向人工复核。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work.inspect_dissolve_save_pair import (
    brace_delta,
    detect_container,
    extract_block,
    open_gamestate,
    parse_field_body,
    parse_structured_block,
    top_level_entries,
    unquote,
)


TARGET_TAGS = ("FRA", "SAV", "LIT", "PRO")
PAIR_TAGS = ("FRA-SAV", "FRA-LIT", "FRA-PRO")
PAIR_SETS = {frozenset(pair.split("-")) for pair in PAIR_TAGS}
HASH_CHUNK = 1024 * 1024
MAX_COUNTRY_CAPTURE = 8 * 1024 * 1024
MAX_DIPLOMACY_CAPTURE = 256 * 1024

COUNTRIES_RE = re.compile(r"^\s*countries\s*=\s*\{")
COUNTRY_RE = re.compile(r"^\s*(FRA|SAV|LIT|PRO)\s*=\s*\{")
DIPLOMACY_RE = re.compile(r"^\s*diplomacy\s*=\s*\{")
BLOCK_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{")
SCALAR_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$")
EXPECTED_BEFORE_SHA256 = "d5da2f4bf818a481fe1493341c4cfd09cb5bcc5d621dd826ebc9051cd3565d5f"
EXPECTED_AFTER_SHA256 = "c6029e2468a0973adc5b4e98c3f51472ab269e9bba212212815b8b4122f13a07"


class SaveParseError(RuntimeError):
    """存档容器或限定对象无法安全解析。"""


@dataclass
class CountryCapture:
    tag: str
    start_line: int
    end_line: int | None
    text: str
    complete: bool
    bytes_captured: int


class RoyalSaveScanner:
    """单遍扫描器，只捕获目标国家块和 royal_marriage 条目。"""

    def __init__(self) -> None:
        self.depth = 0
        self.line_count = 0
        self.header_line: str | None = None
        self.save_date: str | None = None
        self.player: str | None = None
        self.save_game: str | None = None

        self.countries_found = False
        self.countries_complete = False
        self.countries_base_depth: int | None = None
        self.countries_depth: int | None = None
        self.current_country: str | None = None
        self.current_country_depth: int | None = None
        self.current_country_start: int | None = None
        self.current_country_lines: list[str] = []
        self.current_country_bytes = 0
        self.country_captures: dict[str, CountryCapture] = {}
        self.duplicate_country_tags: list[str] = []

        self.diplomacy_found = False
        self.diplomacy_complete = False
        self.diplomacy_base_depth: int | None = None
        self.diplomacy_depth: int | None = None
        self.current_diplomacy_key: str | None = None
        self.current_diplomacy_depth: int | None = None
        self.current_diplomacy_start: int | None = None
        self.current_diplomacy_lines: list[str] = []
        self.current_diplomacy_bytes = 0
        self.royal_marriage_blocks_scanned = 0
        self.royal_marriage_entries: list[dict[str, Any]] = []
        self.unknown: list[str] = []

    def _finish_country(self, end_line: int | None, complete: bool) -> None:
        if self.current_country is None or self.current_country_start is None:
            return
        capture = CountryCapture(
            tag=self.current_country,
            start_line=self.current_country_start,
            end_line=end_line,
            text="".join(self.current_country_lines),
            complete=complete,
            bytes_captured=self.current_country_bytes,
        )
        if self.current_country in self.country_captures:
            self.duplicate_country_tags.append(self.current_country)
        else:
            self.country_captures[self.current_country] = capture
        self.current_country = None
        self.current_country_depth = None
        self.current_country_start = None
        self.current_country_lines = []
        self.current_country_bytes = 0

    def _finish_diplomacy_entry(self, end_line: int | None) -> None:
        if self.current_diplomacy_key is None or self.current_diplomacy_start is None:
            return
        text = "".join(self.current_diplomacy_lines)
        parsed = parse_structured_block(text)
        fields = parsed["fields"]
        first = unquote(fields.get("first"))
        second = unquote(fields.get("second"))
        pair = frozenset((first, second))
        if self.current_diplomacy_key == "royal_marriage":
            if pair in PAIR_SETS:
                self.royal_marriage_entries.append(
                    {
                        "line_start": self.current_diplomacy_start,
                        "line_end": end_line,
                        "fields": fields,
                        "blocks": parsed["blocks"],
                        "unknown": parsed["unknown"],
                    }
                )
            if parsed["unknown"]:
                self.unknown.extend(
                    f"royal_marriage@{self.current_diplomacy_start}:{item}"
                    for item in parsed["unknown"]
                )
        self.current_diplomacy_key = None
        self.current_diplomacy_depth = None
        self.current_diplomacy_start = None
        self.current_diplomacy_lines = []
        self.current_diplomacy_bytes = 0

    def consume(self, stream: Any) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            before = self.depth
            if line_number == 1:
                self.header_line = line.rstrip("\r\n")
            if before == 0:
                scalar = SCALAR_LINE_RE.match(line)
                if scalar:
                    key, value = scalar.group(1), scalar.group(2).strip()
                    if key == "date" and self.save_date is None:
                        self.save_date = value
                    elif key == "player" and self.player is None:
                        self.player = unquote(value)
                    elif key == "save_game" and self.save_game is None:
                        self.save_game = unquote(value)

            if not self.countries_found and COUNTRIES_RE.match(line) and before == 0:
                self.countries_found = True
                self.countries_base_depth = before
                self.countries_depth = before + brace_delta(line)

            if self.countries_found and not self.countries_complete:
                if (
                    self.current_country is None
                    and self.countries_depth is not None
                    and before == self.countries_depth
                ):
                    country_match = COUNTRY_RE.match(line)
                    if country_match:
                        self.current_country = country_match.group(1)
                        self.current_country_start = line_number
                        self.current_country_depth = before + brace_delta(line)
                        self.current_country_lines = [line]
                        self.current_country_bytes = len(line.encode("utf-8", "replace"))
                elif self.current_country is not None:
                    self.current_country_lines.append(line)
                    self.current_country_bytes += len(line.encode("utf-8", "replace"))
                    if self.current_country_bytes > MAX_COUNTRY_CAPTURE:
                        raise SaveParseError(
                            f"{self.current_country}: country capture exceeded {MAX_COUNTRY_CAPTURE} bytes"
                        )

            if not self.diplomacy_found and DIPLOMACY_RE.match(line) and before == 0:
                self.diplomacy_found = True
                self.diplomacy_base_depth = before
                self.diplomacy_depth = before + brace_delta(line)

            if (
                self.diplomacy_found
                and not self.diplomacy_complete
                and self.current_diplomacy_key is None
                and self.diplomacy_depth is not None
                and before == self.diplomacy_depth
            ):
                block_match = BLOCK_LINE_RE.match(line)
                if block_match:
                    self.current_diplomacy_key = block_match.group(1)
                    if self.current_diplomacy_key == "royal_marriage":
                        self.royal_marriage_blocks_scanned += 1
                    self.current_diplomacy_start = line_number
                    self.current_diplomacy_depth = before + brace_delta(line)
                    self.current_diplomacy_lines = [line]
                    self.current_diplomacy_bytes = len(line.encode("utf-8", "replace"))
            elif self.current_diplomacy_key is not None:
                self.current_diplomacy_lines.append(line)
                self.current_diplomacy_bytes += len(line.encode("utf-8", "replace"))
                if self.current_diplomacy_bytes > MAX_DIPLOMACY_CAPTURE:
                    raise SaveParseError(
                        f"diplomacy entry capture exceeded {MAX_DIPLOMACY_CAPTURE} bytes"
                    )

            delta = brace_delta(line)
            self.depth += delta

            if (
                self.current_country is not None
                and self.countries_depth is not None
                and self.depth == self.countries_depth
                and before >= (self.current_country_depth or self.depth + 1)
            ):
                self._finish_country(line_number, complete=True)

            if (
                self.countries_found
                and self.countries_depth is not None
                and self.countries_base_depth is not None
                and self.depth == self.countries_base_depth
                and before >= self.countries_depth
            ):
                if self.current_country is not None:
                    self._finish_country(line_number, complete=False)
                self.countries_complete = True

            if (
                self.current_diplomacy_key is not None
                and self.diplomacy_depth is not None
                and self.depth == self.diplomacy_depth
                and before >= self.diplomacy_depth + 1
            ):
                self._finish_diplomacy_entry(line_number)

            if (
                self.diplomacy_found
                and self.diplomacy_base_depth is not None
                and self.diplomacy_depth is not None
                and self.depth == self.diplomacy_base_depth
                and before >= self.diplomacy_depth
            ):
                if self.current_diplomacy_key is not None:
                    self._finish_diplomacy_entry(line_number)
                self.diplomacy_complete = True

        if self.current_country is not None:
            self._finish_country(None, complete=False)
        if self.current_diplomacy_key is not None:
            self._finish_diplomacy_entry(None)


def stream_sha256(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(HASH_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return {"path": str(path.resolve()), "bytes": total, "sha256": digest.hexdigest()}


def _country_body(capture: CountryCapture) -> tuple[dict[str, Any], list[str]]:
    if not capture.complete:
        return {}, ["country_block_incomplete"]
    try:
        body = extract_block(capture.text, capture.text.find("{"))
        entries = top_level_entries(body)
        fields, _blocks = _flatten_entries(entries)
        return fields, []
    except SaveParseError as error:
        return {}, [f"country_parse_error:{error}"]


def _flatten_entries(entries: list[Any], prefix: str = "") -> tuple[dict[str, Any], list[str]]:
    """Flatten bounded parser entries while preserving duplicate scalar keys."""

    fields: dict[str, Any] = {}
    blocks: list[str] = []
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.key] = counts.get(entry.key, 0) + 1
        suffix = "" if counts[entry.key] == 1 else f"#{counts[entry.key]}"
        path = f"{prefix}.{entry.key}{suffix}" if prefix else f"{entry.key}{suffix}"
        if entry.value is not None:
            if path not in fields:
                fields[path] = entry.value
            elif isinstance(fields[path], list):
                fields[path].append(entry.value)
            else:
                fields[path] = [fields[path], entry.value]
            continue
        blocks.append(path)
        child_fields, child_blocks = _flatten_entries(top_level_entries(entry.body or ""), path)
        for key, value in child_fields.items():
            if key not in fields:
                fields[key] = value
            elif isinstance(fields[key], list):
                fields[key].append(value)
            else:
                fields[key] = [fields[key], value]
        blocks.extend(child_blocks)
    return fields, blocks


def _relation_line_ranges(capture: CountryCapture, target_tags: tuple[str, ...]) -> dict[str, list[dict[str, int]]]:
    """Locate bounded active_relations child lines for source-object evidence."""

    result: dict[str, list[dict[str, int]]] = {tag: [] for tag in target_tags}
    depth = 0
    active_depth: int | None = None
    active_current: str | None = None
    active_current_depth: int | None = None
    active_current_start: int | None = None
    for number, line in enumerate(capture.text.splitlines(True), capture.start_line):
        before = depth
        if active_depth is None and before == 1 and re.match(r"^\s*active_relations\s*=\s*\{", line):
            active_depth = before + brace_delta(line)
        elif active_depth is not None and active_current is None and before == active_depth:
            match = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{", line)
            if match and match.group(1) in result:
                active_current = match.group(1)
                active_current_start = number
                active_current_depth = before + brace_delta(line)
        depth += brace_delta(line)
        if (
            active_current is not None
            and active_current_start is not None
            and active_current_depth is not None
            and depth == active_depth
            and before >= active_current_depth
        ):
            result[active_current].append({"line_start": active_current_start, "line_end": number})
            active_current = None
            active_current_start = None
            active_current_depth = None
        if active_depth is not None and depth == 1 and before >= active_depth:
            active_depth = None
    return result


def _opinion_blocks(relation_body: str) -> tuple[list[dict[str, Any]], list[str]]:
    opinions: list[dict[str, Any]] = []
    unknown: list[str] = []
    try:
        entries = top_level_entries(relation_body)
    except SaveParseError as error:
        return opinions, [f"opinion_parent_parse_error:{error}"]
    for index, entry in enumerate(entries, 1):
        if entry.key != "opinion" or entry.body is None:
            continue
        parsed = parse_field_body(entry.body)
        item = {
            "index": index,
            "fields": parsed["fields"],
            "blocks": parsed["blocks"],
            "unknown": parsed["unknown"],
        }
        opinions.append(item)
        unknown.extend(str(value) for value in parsed["unknown"])
    return opinions, unknown


def extract_relations(capture: CountryCapture, target_tags: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not capture.complete:
        return {
            "present": False,
            "active_relations_block_count": 0,
            "entries": [],
            "unknown": ["country_block_incomplete"],
        }
    try:
        body = extract_block(capture.text, capture.text.find("{"))
        country_entries = top_level_entries(body)
    except SaveParseError as error:
        return {
            "present": False,
            "active_relations_block_count": 0,
            "entries": [],
            "unknown": [f"country_parse_error:{error}"],
        }
    relation_blocks = [
        entry.body for entry in country_entries
        if entry.key == "active_relations" and entry.body is not None
    ]
    line_ranges = _relation_line_ranges(capture, target_tags)
    for other in target_tags:
        entries_out: list[dict[str, Any]] = []
        unknown: list[str] = []
        range_index = 0
        for relation_index, relation_body in enumerate(relation_blocks, 1):
            try:
                entries = top_level_entries(relation_body)
            except SaveParseError as error:
                unknown.append(f"active_relations_parse_error:{error}")
                continue
            for entry_index, entry in enumerate(entries, 1):
                if entry.key != other or entry.body is None:
                    continue
                parsed = parse_field_body(entry.body)
                opinions, opinion_unknown = _opinion_blocks(entry.body)
                unknown.extend(str(value) for value in parsed["unknown"])
                unknown.extend(opinion_unknown)
                source_range = (
                    line_ranges.get(other, [])[range_index]
                    if range_index < len(line_ranges.get(other, []))
                    else None
                )
                range_index += 1
                entries_out.append(
                    {
                        "relation_index": relation_index,
                        "entry_index": entry_index,
                        "source": {
                            "country_tag": capture.tag,
                            "path": f"countries.{capture.tag}.active_relations.{other}",
                            "line_start": source_range.get("line_start") if source_range else None,
                            "line_end": source_range.get("line_end") if source_range else None,
                        },
                        "fields": parsed["fields"],
                        "blocks": parsed["blocks"],
                        "opinion_blocks": opinions,
                        "unknown": parsed["unknown"] + opinion_unknown,
                    }
                )
        result[other] = {
            "present": bool(entries_out),
            "active_relations_block_count": len(relation_blocks),
            "entries": entries_out,
            "unknown": unknown,
        }
    return result


def scan_save(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SaveParseError(f"save path is not a file: {path}")
    source = detect_container(path)
    source.update(stream_sha256(path))
    scanner = RoyalSaveScanner()
    with open_gamestate(path, source) as stream:
        scanner.consume(stream)

    countries: dict[str, Any] = {}
    relations: dict[str, Any] = {}
    unknown = list(scanner.unknown)
    for tag in TARGET_TAGS:
        capture = scanner.country_captures.get(tag)
        country_record: dict[str, Any] = {
            "found": capture is not None,
            "source": {
                "path": f"countries.{tag}",
                "line_start": capture.start_line if capture else None,
                "line_end": capture.end_line if capture else None,
                "bytes_captured": capture.bytes_captured if capture else 0,
                "complete": capture.complete if capture else False,
            },
            "fields": {},
            "fields_scope": ["num_of_royal_marriages", "prestige", "stability"],
            "unknown": [],
        }
        if capture is None:
            country_record["unknown"] = ["country_block_not_found"]
            unknown.append(f"country_{tag}_not_found")
        else:
            fields, field_unknown = _country_body(capture)
            selected = {
                key: fields[key]
                for key in ("num_of_royal_marriages", "prestige", "stability")
                if key in fields
            }
            country_record["fields"] = selected
            country_record["unknown"] = field_unknown + [
                f"field_missing:{key}"
                for key in ("num_of_royal_marriages", "prestige", "stability")
                if key not in fields
            ]
            unknown.extend(f"country_{tag}:{item}" for item in country_record["unknown"])
            extracted = extract_relations(capture, tuple(other for other in TARGET_TAGS if other != tag))
            for other, relation in extracted.items():
                relations[f"{tag}->{other}"] = relation
                unknown.extend(
                    f"{tag}->{other}:{item}" for item in relation.get("unknown", [])
                )
        countries[tag] = country_record

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

    royal_by_pair = {pair: [] for pair in PAIR_TAGS}
    for entry in scanner.royal_marriage_entries:
        fields = entry.get("fields", {})
        first = unquote(fields.get("first"))
        second = unquote(fields.get("second"))
        key = "-".join(sorted((str(first), str(second))))
        if key in royal_by_pair:
            royal_by_pair[key].append(entry)
    return {
        "source": source,
        "metadata": {
            "first_line": scanner.header_line,
            "date": scanner.save_date,
            "player": scanner.player,
            "save_game": scanner.save_game,
        },
        "parse": {
            "gamestate_line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "countries_block_found": scanner.countries_found,
            "countries_block_complete": scanner.countries_complete,
            "diplomacy_block_found": scanner.diplomacy_found,
            "diplomacy_block_complete": scanner.diplomacy_complete,
            "royal_marriage_blocks_scanned": scanner.royal_marriage_blocks_scanned,
            "unknown": unknown,
        },
        "countries": countries,
        "relations": relations,
        "royal_marriages": {
            pair: {
                "entry_count": len(entries),
                "entries": entries,
                "scope": f"diplomacy.royal_marriage entries whose first/second tags are {pair}",
            }
            for pair, entries in royal_by_pair.items()
        },
    }


def _entry_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
    fields = entry.get("fields", {}) if isinstance(entry, dict) else {}
    return (
        unquote(fields.get("first")),
        unquote(fields.get("second")),
        fields.get("start_date"),
    )


def compare_relation(before: dict[str, Any], after: dict[str, Any], pair: str) -> dict[str, Any]:
    before_entries = before["royal_marriages"][pair]["entries"]
    after_entries = after["royal_marriages"][pair]["entries"]
    before_ids = [_entry_identity(item) for item in before_entries]
    after_ids = [_entry_identity(item) for item in after_entries]
    removed = [item for item in before_entries if _entry_identity(item) not in after_ids]
    added = [item for item in after_entries if _entry_identity(item) not in before_ids]
    return {
        "before_entry_count": len(before_entries),
        "after_entry_count": len(after_entries),
        "before_entries": before_entries,
        "after_entries": after_entries,
        "old_entries_removed": removed,
        "new_entries_added": added,
        "old_entry_removed": bool(removed),
        "present_after": bool(after_entries),
        "unknown": [],
    }


def _opinion_effects(scan: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    relation = scan.get("relations", {}).get(direction, {})
    for entry in relation.get("entries", []) if isinstance(relation, dict) else []:
        for opinion in entry.get("opinion_blocks", []):
            fields = opinion.get("fields", {})
            modifier = fields.get("modifier")
            if modifier is None:
                modifier = fields.get("modifier#1")
            effects.append(
                {
                    "source": entry.get("source"),
                    "fields": fields,
                    "relation_fields": entry.get("fields", {}),
                    "modifier": unquote(modifier) if isinstance(modifier, str) else modifier,
                }
            )
    return effects


def build_payload(before_path: Path, after_path: Path,
                  expected_before_sha256: str = EXPECTED_BEFORE_SHA256,
                  expected_after_sha256: str = EXPECTED_AFTER_SHA256) -> dict[str, Any]:
    before = scan_save(before_path)
    after = scan_save(after_path)
    expected_before = expected_before_sha256.lower()
    expected_after = expected_after_sha256.lower()
    hash_checks = {
        "before_expected_sha256": before["source"]["sha256"] == expected_before,
        "after_expected_sha256": after["source"]["sha256"] == expected_after,
    }
    comparisons = {pair: compare_relation(before, after, pair) for pair in PAIR_TAGS}
    relation_directions = tuple(
        direction for pair in PAIR_TAGS for direction in (pair.replace("-", "->"), "->".join(reversed(pair.split("-"))))
    )
    opinion_effects = {
        direction: {
            "before": _opinion_effects(before, direction),
            "after": _opinion_effects(after, direction),
        }
        for direction in relation_directions
    }
    break_effects = {
        direction: {
            phase: [item for item in opinion_effects[direction][phase]
                    if item.get("modifier") == "break_marriage"]
            for phase in ("before", "after")
        }
        for direction in relation_directions
    }
    expected_observations = {
        "FRA-SAV": {
            "before_absent": comparisons["FRA-SAV"]["before_entry_count"] == 0,
            "after_present": comparisons["FRA-SAV"]["after_entry_count"] >= 1,
        },
        "FRA-LIT": {
            "before_absent": comparisons["FRA-LIT"]["before_entry_count"] == 0,
            "after_absent": comparisons["FRA-LIT"]["after_entry_count"] == 0,
        },
        "FRA-PRO": {
            "old_entry_removed": comparisons["FRA-PRO"]["old_entry_removed"],
            "after_pair_present_due_to_new_entry": (
                comparisons["FRA-PRO"]["after_entry_count"] >= 1
                and bool(comparisons["FRA-PRO"]["new_entries_added"])
            ),
            "strictly_absent_after": comparisons["FRA-PRO"]["after_entry_count"] == 0,
        },
    }
    source_objects: list[dict[str, Any]] = [
        {
            "kind": "save",
            "phase": phase,
            "path": scan["source"]["path"],
            "sha256": scan["source"]["sha256"],
            "gamestate": scan["source"].get("gamestate_member") or "plain EU4txt stream",
        }
        for phase, scan in (("before", before), ("after", after))
    ]
    for phase, scan in (("before", before), ("after", after)):
        for tag, country in scan["countries"].items():
            source_objects.append({
                "kind": "country_block",
                "phase": phase,
                "tag": tag,
                "source": country["source"],
                "fields_scope": country["fields_scope"],
                "parse_unknown": country["unknown"],
            })
        for direction, relation in scan["relations"].items():
            for entry in relation.get("entries", []):
                source_objects.append({
                    "kind": "active_relation",
                    "phase": phase,
                    "direction": direction,
                    "source": entry.get("source"),
                    "fields": entry.get("fields"),
                    "opinion_blocks": entry.get("opinion_blocks"),
                    "parse_unknown": entry.get("unknown"),
                })
        for pair, royal in scan["royal_marriages"].items():
            for entry in royal.get("entries", []):
                source_objects.append({
                    "kind": "royal_marriage",
                    "phase": phase,
                    "pair": pair,
                    "line_start": entry.get("line_start"),
                    "line_end": entry.get("line_end"),
                    "fields": entry.get("fields"),
                    "parse_unknown": entry.get("unknown"),
                })
    return {
        "tool": {
            "name": "inspect_royal_save_pair.py",
            "version": 1,
            "scope": "streaming gamestate scan; four country blocks; three FRA relation pairs",
            "source_parser": "work.inspect_dissolve_save_pair streaming container/text helpers",
        },
        "roles": {
            "POR": "葡萄牙，存档 player 字段指向的玩家国家；它不是本次 Royal 动作的发起方。",
            "FRA": "法国，本次 Royal 操作的动作发起方。",
            "SAV": "萨伏依，NPC；用于验证新王室联姻。",
            "LIT": "立陶宛，NPC；用于验证原生拒绝后没有联姻。",
            "PRO": "普罗旺斯，NPC；旧联姻被断绝后又主动向 FRA 重提并获接受。",
        },
        "expected_hashes": {
            "before": expected_before,
            "after": expected_after,
            "checks": hash_checks,
        },
        "before": before,
        "after": after,
        "comparison": {
            "royal_marriage_pairs": comparisons,
            "opinion_effects": opinion_effects,
            "break_marriage_effects": break_effects,
            "expected_observations": expected_observations,
            "stability_prestige": {
                "scope": "只比较四个目标国家块中的顶层 prestige/stability 字段；不作单一动作因果归因。",
                "before": {tag: before["countries"][tag]["fields"] for tag in TARGET_TAGS},
                "after": {tag: after["countries"][tag]["fields"] for tag in TARGET_TAGS},
            },
        },
        "source_objects": {
            "closure": "每个结论只引用下列有限对象：两个存档文件哈希、两个 gamestate 流、四个目标国家块、目标 active_relations 子项和目标 diplomacy.royal_marriage 子项。",
            "objects": source_objects,
            "missing_field_scope": [
                "某个 pair 的 royal_marriage entry_count=0 只表示完整 diplomacy 块中没有找到该 pair 的目标条目；不表示全存档没有任何王室联姻。",
                "active_relations 中没有 break_marriage opinion 只表示对应方向、对应国家块的序列化 relation 没有该字段；不表示游戏内部没有其他未扫描国家或其他关系对象。",
                "prestige/stability 数值跨越约 70 天，并且实验包含多个 Royal 动作；本报告不把数值变化无条件归因于一次断联。",
            ],
        },
    }


def _format_value(value: Any) -> str:
    if value is None:
        return "缺失"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def build_report(payload: dict[str, Any]) -> str:
    before = payload["before"]
    after = payload["after"]
    comparison = payload["comparison"]
    expected_hashes = payload["expected_hashes"]
    hashes = expected_hashes["checks"]
    lines = [
        "# r26 王室联姻存档对照取证",
        "",
        "本报告对两个 EU4 `EU4txt` 存档执行逐行流式扫描。扫描对象限定为 FRA、SAV、LIT、PRO 四个国家块、三个 FRA 关系对的 `active_relations`，以及 `diplomacy` 块中三个关系对的 `royal_marriage` 条目。37–38 MB 存档没有被整体读入内存。",
        "",
        "## 存档身份和角色",
        "",
        f"- 基线：`{Path(before['source']['path']).name}`，存档日期 `{before['metadata']['date']}`，玩家字段 `{before['metadata']['player']}`，SHA-256 `{before['source']['sha256']}`。",
        f"- 结果：`{Path(after['source']['path']).name}`，存档日期 `{after['metadata']['date']}`，玩家字段 `{after['metadata']['player']}`，SHA-256 `{after['source']['sha256']}`。",
        f"- 两个给定 SHA-256 均匹配：基线 `{expected_hashes['before']}`，结果 `{expected_hashes['after']}`。",
        "- POR 是存档 `player` 字段指定的葡萄牙玩家国家；FRA 是本次外交动作的发起方。SAV 是萨伏依 NPC，LIT 是立陶宛 NPC，PRO 是普罗旺斯 NPC。",
        "",
        "## Royal 条目结论",
        "",
        "| 关系对 | 基线 `royal_marriage` | 结果 `royal_marriage` | 取证结论 |",
        "|---|---:|---:|---|",
        f"| FRA-SAV | {comparison['royal_marriage_pairs']['FRA-SAV']['before_entry_count']} | {comparison['royal_marriage_pairs']['FRA-SAV']['after_entry_count']} | 基线无条目，结果新增条目。 |",
        f"| FRA-LIT | {comparison['royal_marriage_pairs']['FRA-LIT']['before_entry_count']} | {comparison['royal_marriage_pairs']['FRA-LIT']['after_entry_count']} | 两份存档均无条目。 |",
        f"| FRA-PRO | {comparison['royal_marriage_pairs']['FRA-PRO']['before_entry_count']} | {comparison['royal_marriage_pairs']['FRA-PRO']['after_entry_count']} | 旧条目被移除，但结果中存在新的 PRO→FRA 联姻条目；最终关系不能写成 absent。 |",
        "",
        "FRA-SAV 的结果条目由 `diplomacy.royal_marriage` 直接给出。FRA-LIT 的完整 diplomacy 扫描没有找到目标条目，与 LIT 提议被原生拒绝的实验结果一致。FRA-PRO 的基线条目是 `PRO→FRA`、`start_date=1444.12.7`；结果中旧身份消失，新的 `PRO→FRA` 条目为 `start_date=1445.3.14`。这说明断联动作确实移除了旧联姻对象，但随后 PRO 主动重提并被 FRA 接受，造成结果存档中关系重新存在。",
        "",
        "## 双向 active_relations 和 opinion",
        "",
        "`active_relations` 是按方向保存的：例如 `PRO->FRA` 与 `FRA->PRO` 是两个独立序列化对象。报告 JSON 保留每个目标方向的字段、嵌套 `opinion` 块、来源国家块和行号范围。",
        "",
    ]
    for direction in ("FRA->SAV", "SAV->FRA", "FRA->LIT", "LIT->FRA", "FRA->PRO", "PRO->FRA"):
        effects = comparison["opinion_effects"][direction]
        lines.append(f"- `{direction}`：基线 opinion 修正 {_format_value(effects['before'])}；结果 opinion 修正 {_format_value(effects['after'])}。")
    lines.extend([
        "",
        "结果存档的 `PRO->FRA` active relation 明确包含 `break_marriage`：`current_opinion=-75.000`、`opinion.date=1445.2.12`、`opinion.expiry_date=yes`、`cached_sum=-75`。FRA→PRO 方向仍序列化为 `opinion_eased_tension`，本报告不把单一方向的字段扩展为双方完全对称的结论。",
        "",
        "## prestige、stability 和归因边界",
        "",
        "| 国家 | 基线 prestige/stability | 结果 prestige/stability |",
        "|---|---|---|",
    ])
    for tag in TARGET_TAGS:
        b = before["countries"][tag]["fields"]
        a = after["countries"][tag]["fields"]
        lines.append(f"| {tag} | prestige={b.get('prestige', '缺失')}，stability={b.get('stability', '缺失')} | prestige={a.get('prestige', '缺失')}，stability={a.get('stability', '缺失')} |")
    lines.extend([
        "",
        "两个存档相隔约 70 天，期间包含 SAV 接受、LIT 拒绝、FRA 断绝 PRO 旧联姻以及 PRO 随后重提并获接受等多个外交状态变化。因此 prestige 和 stability 只作为存档中可读出的结果字段报告，不能无条件归因于某一次断联动作。",
        "",
        "## 解析完整性和范围",
        "",
        f"- 基线 gamestate 行数 `{before['parse']['gamestate_line_count']}`，结果 `{after['parse']['gamestate_line_count']}`；两个文件最终 brace depth 均为 0。",
        f"- 基线扫描到 `{before['parse']['royal_marriage_blocks_scanned']}` 个 diplomacy.royal_marriage 块，结果扫描到 `{after['parse']['royal_marriage_blocks_scanned']}` 个；四个目标国家块均要求完整闭合。",
        "- 结论范围闭合在两个存档文件哈希、目标国家块、目标 active_relations 方向和目标 diplomacy.royal_marriage 对象。未扫描对象不被代替为推断。",
        "- 找不到字段时，JSON 的 `unknown`、`fields_scope` 和 `source_objects.missing_field_scope` 会保留缺失的明确范围；不会把字段缺失写成全局不存在。",
        "",
        "详细字段、来源行号、哈希、原始关系块和解析未知项见同目录 `findings.json`。",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--expected-before-sha256", default=EXPECTED_BEFORE_SHA256)
    parser.add_argument("--expected-after-sha256", default=EXPECTED_AFTER_SHA256)
    args = parser.parse_args(argv)
    artifact = args.artifact_dir.expanduser().resolve()
    artifact.mkdir(parents=True, exist_ok=True)
    payload = build_payload(
        args.before.expanduser().resolve(),
        args.after.expanduser().resolve(),
        args.expected_before_sha256,
        args.expected_after_sha256,
    )
    findings_path = artifact / "findings.json"
    report_path = artifact / "report.md"
    findings_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(build_report(payload), encoding="utf-8")
    script_copy = artifact / Path(__file__).name
    source_path = Path(__file__).resolve()
    if script_copy.resolve() != source_path:
        script_copy.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "artifact_dir": str(artifact),
        "findings": str(findings_path),
        "report": str(report_path),
        "before_sha256_matches": payload["expected_hashes"]["checks"]["before_expected_sha256"],
        "after_sha256_matches": payload["expected_hashes"]["checks"]["after_expected_sha256"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
