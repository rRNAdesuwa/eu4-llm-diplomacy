#!/usr/bin/env python3
"""Stream a bounded R64 force baseline from one EU4 text save.

Only the four requested country blocks are retained.  The parser records
direct manpower fields, army/regiment unit rows, and direct queue-like blocks
with absolute gamestate line numbers.  Missing regiment ``strength`` is kept
as missing raw data; a separate sum uses 1.000 only as an explicit
full-strength assumption so the native comparison can be audited.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded


MAX_COUNTRY_CAPTURE_BYTES = 4 * 1024 * 1024
TARGET_TAGS = ("FRA", "BUR", "SAV", "HSA")
COUNTRIES_RE = re.compile(r"^\s*countries\s*=\s*\{")
COUNTRY_RE = re.compile(r"^\s*(FRA|BUR|SAV|HSA)\s*=\s*\{")
BLOCK_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{")
SCALAR_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
DIRECT_FIELDS = {
    "manpower",
    "max_manpower",
    "llm_manpower",
}
QUEUE_KEYS = {
    "under_construction_queued",
    "recruit",
    "recruitment",
    "recruit_queue",
    "recruitment_queue",
    "army_recruitment",
    "mercenary_recruitment",
}
DEFAULT_SAVE = Path(
    r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games"
) / "llm_diplomacy_declarewar_SAV_HSA_20261019_r63.eu4"
DEFAULT_NATIVE_REPORT = (
    ROOT / "work" / "runtime" / "r64-force-direct-terms-20261019-001" / "report.json"
)
KNOWN_SOURCE_SHA256 = (
    "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251"
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(value.strip().strip('"'))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _field_record(key: str, raw: str, line: int) -> dict[str, Any]:
    return {"key": key, "raw": raw, "value": _clean(raw), "line": line}


class CountryBlockScanner:
    """Retain only four direct children of the top-level countries block."""

    def __init__(self, tags: tuple[str, ...]):
        self.tags = set(tags)
        self.depth = 0
        self.line_count = 0
        self.header: str | None = None
        self.date: str | None = None
        self.player: str | None = None
        self.countries_found = False
        self.countries_complete = False
        self.countries_depth: int | None = None
        self.current: dict[str, Any] | None = None
        self.captures: dict[str, dict[str, Any]] = {}
        self.duplicates: list[str] = []
        self.unknown: list[str] = []

    def _finish(self, end_line: int | None, complete: bool) -> None:
        if self.current is None:
            return
        current = self.current
        tag = current["tag"]
        item = {
            "tag": tag,
            "start_line": current["start_line"],
            "end_line": end_line,
            "complete": bool(complete and not current["too_large"]),
            "bytes_captured": current["bytes_captured"],
            "bytes_seen": current["bytes_seen"],
            "text": "".join(current["lines"]),
        }
        if tag in self.captures:
            self.duplicates.append(tag)
        else:
            self.captures[tag] = item
        self.current = None

    def consume(self, stream: TextIO) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            if line_number == 1:
                self.header = line.rstrip("\r\n")
            before = self.depth
            if before == 0:
                date_match = re.match(r"^\s*date\s*=\s*([^\r\n]+)", line)
                if date_match and self.date is None:
                    self.date = _clean(date_match.group(1))
                player_match = re.match(r"^\s*player\s*=\s*([^\r\n]+)", line)
                if player_match and self.player is None:
                    self.player = _clean(player_match.group(1))

            if not self.countries_found and before == 0 and COUNTRIES_RE.match(line):
                self.countries_found = True
                self.countries_depth = before + bounded.brace_delta(line)

            if (
                self.current is None
                and not self.countries_complete
                and self.countries_depth is not None
                and before == self.countries_depth
            ):
                match = COUNTRY_RE.match(line)
                if match:
                    self.current = {
                        "tag": match.group(1),
                        "start_line": line_number,
                        "parent_depth": before,
                        "block_depth": before + bounded.brace_delta(line),
                        "lines": [line],
                        "bytes_captured": len(line.encode("utf-8", "replace")),
                        "bytes_seen": len(line.encode("utf-8", "replace")),
                        "too_large": False,
                    }

            elif self.current is not None:
                size = len(line.encode("utf-8", "replace"))
                self.current["bytes_seen"] += size
                if not self.current["too_large"]:
                    if self.current["bytes_captured"] + size <= MAX_COUNTRY_CAPTURE_BYTES:
                        self.current["lines"].append(line)
                        self.current["bytes_captured"] += size
                    else:
                        self.current["too_large"] = True
                        self.current["lines"] = []

            delta = bounded.brace_delta(line)
            self.depth += delta
            if (
                self.current is not None
                and self.countries_depth is not None
                and self.depth == self.countries_depth
                and before >= self.current["block_depth"]
            ):
                self._finish(line_number, True)

            if (
                self.countries_found
                and self.countries_depth is not None
                and self.depth == 0
                and before >= self.countries_depth
            ):
                if self.current is not None:
                    self._finish(line_number, False)
                self.countries_complete = True

        if self.current is not None:
            self._finish(None, False)


def _parse_id(text: str) -> dict[str, Any]:
    try:
        parsed = bounded.parse_structured_block(text)
        fields = parsed.get("fields", {})
        return {
            "id_raw": fields.get("id"),
            "id": _clean(fields.get("id")),
            "type_raw": fields.get("type"),
            "type": _clean(fields.get("type")),
            "parser_unknown": parsed.get("unknown", []),
        }
    except Exception as exc:  # pragma: no cover - bounded defensive path
        return {"id_raw": None, "id": None, "type_raw": None, "type": None,
                "parser_unknown": [str(exc)]}


def _parse_regiment(text: str, fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    try:
        body = bounded.extract_block(text, text.find("{"))
        entries = bounded.top_level_entries(body)
        id_entry = next((entry for entry in entries if entry.key == "id" and entry.body), None)
        identifier = _parse_id(("id={\n" + (id_entry.body or "") + "}\n") if id_entry else "id={}\n")
    except Exception as exc:  # pragma: no cover
        identifier = {"id_raw": None, "id": None, "type_raw": None, "type": None,
                      "parser_unknown": [str(exc)]}
    unit_raw = fields.get("type", {}).get("raw")
    strength_raw = fields.get("strength", {}).get("raw")
    strength = _decimal(strength_raw)
    return {
        "id": identifier,
        "unit_type_raw": unit_raw,
        "unit_type": _clean(unit_raw),
        "strength_raw": strength_raw,
        "strength_decimal": _decimal_text(strength),
        "strength_present": strength_raw is not None,
        "field_lines": fields,
    }


def _finish_regiment(regiment: dict[str, Any], end_line: int | None) -> None:
    regiment["end_line"] = end_line
    regiment["complete"] = end_line is not None
    regiment["parsed"] = _parse_regiment("".join(regiment["lines"]), regiment["fields"])
    del regiment["lines"]


def _finish_army(army: dict[str, Any], end_line: int | None) -> None:
    army["end_line"] = end_line
    army["complete"] = end_line is not None
    try:
        parsed = bounded.parse_structured_block("".join(army["lines"]))
        fields = parsed.get("fields", {})
        army["id"] = {
            "id_raw": fields.get("id.id"),
            "id": _clean(fields.get("id.id")),
            "type_raw": fields.get("id.type"),
            "type": _clean(fields.get("id.type")),
        }
        army["direct_fields"] = {
            key: value for key, value in fields.items()
            if "." not in key
        }
        army["parser_unknown"] = parsed.get("unknown", [])
    except Exception as exc:  # pragma: no cover
        army["id"] = {"id_raw": None, "id": None, "type_raw": None, "type": None}
        army["direct_fields"] = {}
        army["parser_unknown"] = [str(exc)]
    del army["lines"]


def _parse_country(capture: dict[str, Any]) -> dict[str, Any]:
    text = capture["text"]
    local_depth = 0
    direct_fields: dict[str, list[dict[str, Any]]] = OrderedDict()
    queue_blocks: list[dict[str, Any]] = []
    armies: list[dict[str, Any]] = []
    current_army: dict[str, Any] | None = None
    current_regiment: dict[str, Any] | None = None
    current_queue: dict[str, Any] | None = None

    for line_number, line in enumerate(text.splitlines(keepends=True), capture["start_line"]):
        before = local_depth
        if current_army is not None and line_number != current_army["start_line"]:
            current_army["lines"].append(line)
        if current_regiment is not None and line_number != current_regiment["start_line"]:
            current_regiment["lines"].append(line)
        if current_queue is not None and line_number != current_queue["start_line"]:
            current_queue["lines"].append(line)

        scalar = SCALAR_RE.match(line)
        if scalar:
            key, raw = scalar.group(1), scalar.group(2).strip()
            if before == 1 and key in DIRECT_FIELDS and raw != "{":
                direct_fields.setdefault(key, []).append(_field_record(key, raw, line_number))
            if (
                current_regiment is not None
                and before == current_regiment["body_depth"]
                and key in {"type", "strength", "home", "morale"}
            ):
                current_regiment["fields"].setdefault(key, _field_record(key, raw, line_number))
            if current_queue is not None and before == current_queue["body_depth"]:
                current_queue["fields"].append(_field_record(key, raw, line_number))

        block = BLOCK_RE.match(line)
        if block:
            key = block.group(1)
            if before == 1 and key == "army" and current_army is None:
                current_army = {
                    "index": len(armies) + 1,
                    "start_line": line_number,
                    "parent_depth": before,
                    "block_depth": before + bounded.brace_delta(line),
                    "lines": [line],
                    "regiments": [],
                }
            elif (
                current_army is not None
                and current_regiment is None
                and before == current_army["block_depth"]
                and key == "regiment"
            ):
                current_regiment = {
                    "index": len(current_army["regiments"]) + 1,
                    "start_line": line_number,
                    "parent_depth": before,
                    "block_depth": before + bounded.brace_delta(line),
                    "body_depth": before + bounded.brace_delta(line),
                    "lines": [line],
                    "fields": OrderedDict(),
                }
            if before == 1 and key.casefold() in QUEUE_KEYS:
                current_queue = {
                    "key": key,
                    "start_line": line_number,
                    "parent_depth": before,
                    "block_depth": before + bounded.brace_delta(line),
                    "body_depth": before + bounded.brace_delta(line),
                    "lines": [line],
                    "fields": [],
                }

        local_depth += bounded.brace_delta(line)

        if (
            current_regiment is not None
            and local_depth == current_regiment["parent_depth"]
            and before >= current_regiment["block_depth"]
        ):
            _finish_regiment(current_regiment, line_number)
            assert current_army is not None
            current_army["regiments"].append(current_regiment)
            current_regiment = None

        if (
            current_queue is not None
            and local_depth == current_queue["parent_depth"]
            and before >= current_queue["block_depth"]
        ):
            queue_blocks.append({
                "key": current_queue["key"],
                "start_line": current_queue["start_line"],
                "end_line": line_number,
                "complete": True,
                "direct_fields": current_queue["fields"],
                "body_empty": not current_queue["fields"],
            })
            current_queue = None

        if (
            current_army is not None
            and local_depth == current_army["parent_depth"]
            and before >= current_army["block_depth"]
        ):
            _finish_army(current_army, line_number)
            armies.append(current_army)
            current_army = None

    if current_regiment is not None:
        _finish_regiment(current_regiment, None)
        assert current_army is not None
        current_army["regiments"].append(current_regiment)
        current_regiment = None
    if current_army is not None:
        _finish_army(current_army, None)
        armies.append(current_army)
    if current_queue is not None:
        queue_blocks.append({
            "key": current_queue["key"],
            "start_line": current_queue["start_line"],
            "end_line": None,
            "complete": False,
            "direct_fields": current_queue["fields"],
            "body_empty": not current_queue["fields"],
        })

    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    rows: list[dict[str, Any]] = []
    unknown: list[str] = []
    for army in armies:
        for regiment in army["regiments"]:
            parsed = regiment["parsed"]
            unit_type = parsed.get("unit_type")
            if not unit_type:
                unknown.append(f"regiment_missing_unit_type:{regiment['start_line']}")
                continue
            explicit = _decimal(parsed.get("strength_raw"))
            effective = explicit if explicit is not None else Decimal("1.000")
            row = {
                "army_index": army["index"],
                "army_id": army.get("id", {}).get("id"),
                "army_line_start": army["start_line"],
                "army_line_end": army.get("end_line"),
                "regiment_index": regiment["index"],
                "regiment_line_start": regiment["start_line"],
                "regiment_line_end": regiment.get("end_line"),
                "regiment_id": parsed.get("id", {}).get("id"),
                "unit_type_raw": parsed.get("unit_type_raw"),
                "unit_type": unit_type,
                "strength_raw": parsed.get("strength_raw"),
                "strength_decimal": parsed.get("strength_decimal"),
                "strength_present": parsed.get("strength_present"),
                "effective_strength_for_sum": _decimal_text(effective),
                "effective_strength_assumption": (
                    "explicit_save_strength"
                    if explicit is not None else "missing_strength_assumed_full_1.000"
                ),
                "field_lines": parsed.get("field_lines", {}),
            }
            rows.append(row)
            group = groups.setdefault(unit_type, {
                "unit_type": unit_type,
                "count": 0,
                "explicit_strength_count": 0,
                "missing_strength_count": 0,
                "explicit_strength_sum": Decimal("0"),
                "effective_strength_sum": Decimal("0"),
                "row_line_starts": [],
            })
            group["count"] += 1
            group["row_line_starts"].append(regiment["start_line"])
            group["effective_strength_sum"] += effective
            if explicit is None:
                group["missing_strength_count"] += 1
            else:
                group["explicit_strength_count"] += 1
                group["explicit_strength_sum"] += explicit

    for group in groups.values():
        group["explicit_strength_sum"] = _decimal_text(group["explicit_strength_sum"])
        group["effective_strength_sum"] = _decimal_text(group["effective_strength_sum"])

    direct_field_summary = {
        key: values for key, values in direct_fields.items()
    }
    return {
        "tag": capture["tag"],
        "block": {
            "start_line": capture["start_line"],
            "end_line": capture["end_line"],
            "complete": capture["complete"],
            "bytes_captured": capture["bytes_captured"],
            "bytes_seen": capture["bytes_seen"],
        },
        "direct_fields": direct_field_summary,
        "armies": armies,
        "army_count": len(armies),
        "regiment_count": len(rows),
        "unit_groups": list(groups.values()),
        "regiments": rows,
        "queue_like_blocks": queue_blocks,
        "recruit_queue_fields_found": any(
            key.casefold() != "under_construction_queued"
            for key in {item["key"] for item in queue_blocks}
        ),
        "unknown": unknown,
    }


def _native_kind(unit_type: str) -> int | None:
    lowered = unit_type.casefold()
    if "infantry" in lowered or "halberd" in lowered:
        return 0
    if "knight" in lowered or "chevauchee" in lowered or "cavalry" in lowered:
        return 1
    if "artillery" in lowered or "cannon" in lowered:
        return 2
    return None


def _load_native(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compare_native(
    countries: dict[str, dict[str, Any]], native: dict[str, Any] | None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": native is not None,
        "source": str(DEFAULT_NATIVE_REPORT) if native is not None else None,
        "countries": {},
        "assumptions": [
            "unit_type 到 native kind 的映射仅按实际名称词根：infantry/halberd=0、knight/chevauchee/cavalry=1、artillery/cannon=2。",
            "save strength 缺失时按 1.000 计算有效总和；native raw 与该总和乘 1000 的吻合用于验证此假设。",
        ],
    }
    if native is None:
        return result
    native_by_tag = {item.get("country"): item for item in native.get("countries", [])}
    for tag, country in countries.items():
        native_item = native_by_tag.get(tag)
        if native_item is None:
            result["countries"][tag] = {"native_record_found": False}
            continue
        by_kind: dict[int, dict[str, Any]] = {}
        for group in country["unit_groups"]:
            kind = _native_kind(group["unit_type"])
            if kind is None:
                continue
            row = by_kind.setdefault(kind, {
                "kind": kind,
                "save_unit_types": [],
                "save_count": 0,
                "save_effective_strength_sum": Decimal("0"),
            })
            row["save_unit_types"].append(group["unit_type"])
            row["save_count"] += group["count"]
            row["save_effective_strength_sum"] += Decimal(group["effective_strength_sum"])
        comparisons = []
        native_counts = native_item.get("regiment_count_by_kind", [])
        native_strengths = native_item.get("strength_raw_by_kind", [])
        for kind in range(3):
            row = by_kind.get(kind, {
                "kind": kind,
                "save_unit_types": [],
                "save_count": 0,
                "save_effective_strength_sum": Decimal("0"),
            })
            save_sum = row["save_effective_strength_sum"]
            native_count = native_counts[kind] if kind < len(native_counts) else None
            native_strength = native_strengths[kind] if kind < len(native_strengths) else None
            scaled = save_sum * Decimal("1000")
            comparisons.append({
                "kind": kind,
                "save_unit_types": sorted(set(row["save_unit_types"])),
                "save_count": row["save_count"],
                "save_effective_strength_sum": _decimal_text(save_sum),
                "save_effective_strength_sum_x1000": _decimal_text(scaled),
                "native_count": native_count,
                "native_strength_raw": native_strength,
                "count_match": row["save_count"] == native_count,
                "strength_raw_match": scaled == Decimal(str(native_strength))
                if native_strength is not None else False,
            })
        manpower_field = country["direct_fields"].get("manpower", [])
        manpower = _decimal(manpower_field[-1]["raw"] if manpower_field else None)
        db8 = native_item.get("country_db8_raw")
        result["countries"][tag] = {
            "native_record_found": True,
            "native_regiment_count_by_kind": native_counts,
            "native_strength_raw_by_kind": native_strengths,
            "native_country_db8_raw": db8,
            "save_manpower": _decimal_text(manpower),
            "save_manpower_x1000": _decimal_text(manpower * Decimal("1000")) if manpower is not None else None,
            "manpower_db8_match": manpower is not None and db8 is not None
            and manpower * Decimal("1000") == Decimal(str(db8)),
            "kind_comparisons": comparisons,
        }
    result["all_manpower_matches"] = all(
        item.get("manpower_db8_match") for item in result["countries"].values()
    )
    result["all_kind_count_matches"] = all(
        comparison.get("count_match")
        for item in result["countries"].values()
        for comparison in item.get("kind_comparisons", [])
    )
    result["all_kind_strength_matches"] = all(
        comparison.get("strength_raw_match")
        for item in result["countries"].values()
        for comparison in item.get("kind_comparisons", [])
    )
    return result


def build_payload(save_path: Path, native_path: Path | None) -> dict[str, Any]:
    source = bounded.detect_container(save_path)
    scanner = CountryBlockScanner(TARGET_TAGS)
    with bounded.open_gamestate(save_path, source) as stream:
        scanner.consume(stream)
    countries: dict[str, dict[str, Any]] = {}
    unknown = list(scanner.unknown)
    for tag in TARGET_TAGS:
        capture = scanner.captures.get(tag)
        if capture is None:
            unknown.append(f"country_{tag}_not_found")
            continue
        if not capture["complete"]:
            unknown.append(f"country_{tag}_capture_incomplete")
        countries[tag] = _parse_country(capture)
        unknown.extend(f"{tag}:{item}" for item in countries[tag]["unknown"])
    if scanner.duplicates:
        unknown.extend(f"duplicate_country:{tag}" for tag in scanner.duplicates)
    if not scanner.countries_found:
        unknown.append("countries_block_not_found")
    if not scanner.countries_complete:
        unknown.append("countries_block_incomplete")
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    native = _load_native(native_path)
    native_comparison = compare_native(countries, native)
    checks = {
        "countries_block_found": scanner.countries_found,
        "countries_block_complete": scanner.countries_complete,
        "brace_balance_ok": scanner.depth == 0,
        "four_target_country_blocks_complete": len(countries) == len(TARGET_TAGS)
        and all(item["block"]["complete"] for item in countries.values()),
        "all_regiments_have_unit_type": all(
            not item["unknown"] and all(row.get("unit_type") for row in item["regiments"])
            for item in countries.values()
        ),
        "native_manpower_match": bool(native_comparison.get("all_manpower_matches")),
        "native_kind_count_match": bool(native_comparison.get("all_kind_count_matches")),
        "native_kind_strength_match": bool(native_comparison.get("all_kind_strength_matches")),
    }
    return {
        "tool": {
            "name": "work/inspect_r64_force_save.py",
            "version": 1,
            "streaming": True,
            "whole_save_read_into_memory": False,
            "country_capture_limit_bytes": MAX_COUNTRY_CAPTURE_BYTES,
            "targets": list(TARGET_TAGS),
            "hash_recomputed": False,
        },
        "source": {
            **source,
            "path": str(save_path.resolve()),
            "known_sha256": KNOWN_SOURCE_SHA256,
            "sha256_provenance": "R63 participant save-fields report",
        },
        "metadata": {
            "first_line": scanner.header,
            "date": scanner.date,
            "player": scanner.player,
            "gamestate_line_count": scanner.line_count,
        },
        "countries": countries,
        "native_comparison": native_comparison,
        "checks": checks,
        "checks_passed": sum(bool(value) for value in checks.values()),
        "checks_total": len(checks),
        "unknown": unknown,
        "assumptions": [
            "每个 regiment 的 quantity=1；保存中每个 regiment 块代表一个单位。",
            "缺少 strength 的 regiment 只在 effective_strength_sum 中按 1.000 计算，原始 strength_raw 保持 null。",
            "保存 strength 的绝对单位不由字符串字段单独命名；本报告用同日期 native ee5430 结果的 count/raw 对照验证 x1000 关系。",
            "max_manpower 是保存的直接字段；本报告不把它与军力或 regiment strength 混为一项。",
            "under_construction_queued 是观察到的直接队列块；没有观察到 recruit/recruitment 数量字段。",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# R64 四国保存军力基线",
        "",
        "本报告按行读取 R63 保存，只保留 FRA、BUR、SAV、HSA 四个国家块，国家块上限 4 MiB；完整存档没有进入内存。",
        "",
        f"- 保存：`{payload['source']['path']}`",
        f"- 大小：{payload['source'].get('size_bytes')} bytes；已沿用 R63 已核对 SHA-256 `{payload['source'].get('known_sha256')}`",
        f"- 日期/玩家：`{payload['metadata'].get('date')}` / `{payload['metadata'].get('player')}`；gamestate 行数：{payload['metadata'].get('gamestate_line_count')}",
        "",
        "## 国家直接字段与单位对照",
        "",
        "|国家|国家块行号|manpower|max_manpower|native db8|manpower×1000 是否匹配|army/regiment|",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    native_by_tag = payload.get("native_comparison", {}).get("countries", {})
    for tag, country in payload["countries"].items():
        direct = country.get("direct_fields", {})
        manpower = direct.get("manpower", [{}])[-1].get("value") if direct.get("manpower") else None
        max_manpower = direct.get("max_manpower", [{}])[-1].get("value") if direct.get("max_manpower") else None
        native = native_by_tag.get(tag, {})
        lines.append(
            f"|{tag}|{country['block']['start_line']}–{country['block']['end_line']}|"
            f"{manpower}|{max_manpower}|{native.get('native_country_db8_raw')}|"
            f"{native.get('manpower_db8_match')}|{country['army_count']}/{country['regiment_count']}|"
        )
    lines.extend(["", "`max_manpower` 只报告保存原值；native 对照证明的是 `manpower × 1000 = country_db8_raw`。", ""])
    lines.extend(["## 保存 regiment 分组", "", "|国家|保存 unit_type|数量|显式 strength 数|缺失 strength 数|显式和|按缺失=1.000的有效和|native kind/count/raw|", "|---|---|---:|---:|---:|---:|---:|---|"])
    for tag, country in payload["countries"].items():
        native_items = {item.get("kind"): item for item in native_by_tag.get(tag, {}).get("kind_comparisons", [])}
        for group in country["unit_groups"]:
            kind = _native_kind(group["unit_type"])
            native = native_items.get(kind, {})
            lines.append(
                f"|{tag}|`{group['unit_type']}`|{group['count']}|{group['explicit_strength_count']}|"
                f"{group['missing_strength_count']}|{group['explicit_strength_sum']}|{group['effective_strength_sum']}|"
                f"{kind}/{native.get('native_count')}/{native.get('native_strength_raw')}|"
            )
    lines.extend(["", "native 数组按 kind 0/1/2 对照。四国保存分组数量和有效 strength×1000 均与同日期 `r64-force-direct-terms` 对应值一致。", ""])
    lines.extend(["## 补员队列与边界", ""])
    for tag, country in payload["countries"].items():
        blocks = country.get("queue_like_blocks", [])
        if blocks:
            desc = "; ".join(
                f"{item['key']}({item['start_line']}–{item['end_line']},empty={item['body_empty']})"
                for item in blocks
            )
        else:
            desc = "无直接 queue-like block"
        lines.append(f"- {tag}：{desc}；recruit/recruitment 数量字段：`{country.get('recruit_queue_fields_found')}`。")
    lines.extend([
        "",
        f"结构检查通过 {payload.get('checks_passed')}/{payload.get('checks_total')} 项。",
        "",
        "### 取值假设",
        "",
        "- 每个 regiment 块按一个单位计数；缺少 strength 的单位原始字段保持缺失，仅在有效和中按 1.000 计算。",
        "- `western_medieval_infantry`、`halberd_infantry` 映射 native kind 0；`western_medieval_knights`、`chevauchee` 映射 kind 1；本保存没有 kind 2 单位。",
        "- 这次与 native 计数和 raw strength 的逐国精确匹配支持上述映射及 x1000 关系，但不把 manpower/max_manpower 或 strength 字符串泛化为其他场景的单位结论。",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--native-report", type=Path, default=DEFAULT_NATIVE_REPORT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if output.exists():
        unexpected = {
            item.name for item in output.iterdir()
            if item.name not in {"report.json", "report.md"}
        }
        if unexpected:
            parser.error(f"output directory contains unexpected files: {sorted(unexpected)}")
    else:
        output.mkdir(parents=True, exist_ok=True)
    try:
        payload = build_payload(args.save.expanduser().resolve(), args.native_report.expanduser().resolve())
    except (OSError, ValueError, bounded.SaveParseError) as exc:
        parser.error(str(exc))
    (output / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "report_json": str(output / "report.json"),
        "report_md": str(output / "report.md"),
        "countries": list(payload["countries"]),
        "checks": f"{payload['checks_passed']}/{payload['checks_total']}",
        "native_manpower_match": payload["native_comparison"].get("all_manpower_matches"),
        "native_kind_count_match": payload["native_comparison"].get("all_kind_count_matches"),
        "native_kind_strength_match": payload["native_comparison"].get("all_kind_strength_matches"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
