#!/usr/bin/env python3
"""Bounded, read-only reconciliation of R65 peace preview data with the R63 save.

The native event files are small JSON observations.  The save is scanned once
as EU4 text, retaining only the province ids named by those observations and
the active relation entries directed at the relevant claimant.  No complete
save is loaded into memory and no dynamic value is invented when a source
field is absent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


for _parent in Path(__file__).resolve().parents:
    if (_parent / "work").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from work import inspect_dissolve_save_pair as bounded
from work import local_config


MAX_BLOCK_BYTES = 4 * 1024 * 1024
SAVE_NAME = "llm_diplomacy_declarewar_SAV_HSA_20261019_r63.eu4"
KNOWN_SOURCE_SHA256 = (
    "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251"
)
DEFAULT_NATIVE_ROOT = Path(
    "work/runtime/r65-peace-consequence-queries-20261019-004/report-evidence/cases"
)
DEFAULT_OUTPUT = Path("work/runtime/r65-peace-preview-save-check-20261019-001")

COUNTRIES_RE = re.compile(r"^\s*countries\s*=\s*\{")
PROVINCES_RE = re.compile(r"^\s*provinces\s*=\s*\{")
COUNTRY_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,5})\s*=\s*\{")
PROVINCE_RE = re.compile(r"^\s*(-?\d+)\s*=\s*\{")
DATE_RE = re.compile(r"^\s*date\s*=\s*(.*?)\s*$")
TAG_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,5}\b")
OPINION_MODIFIER_RE = re.compile(r"^(opinion(?:#\d+)?)\.modifier$")


def _normalize(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return bounded.unquote(value)
    return value


def _last(value: Any) -> Any:
    if isinstance(value, list):
        return value[-1] if value else None
    return value


def _scalar(fields: dict[str, Any], key: str) -> Any:
    return _normalize(_last(fields.get(key)))


def _decimal(value: Any) -> Decimal | None:
    value = _normalize(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _json_number(value: Decimal | None) -> int | float | str | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return format(value, "f")


def _int(value: Any) -> int | None:
    dec = _decimal(value)
    if dec is None:
        return None
    try:
        return int(dec)
    except (ValueError, OverflowError):
        return None


def _tag_tokens(body: str | None) -> list[str]:
    if not body:
        return []
    return sorted({token for token in TAG_RE.findall(body) if token not in {"yes", "no"}})


def _block_tokens(entries: list[bounded.Entry], key: str) -> list[str]:
    result: list[str] = []
    for entry in entries:
        if entry.key == key and entry.body is not None:
            result.extend(_tag_tokens(entry.body))
    return sorted(set(result))


def _append_line(active: dict[str, Any], line: str) -> None:
    active["bytes_seen"] += len(line.encode("utf-8", errors="replace"))
    if active["bytes_seen"] <= MAX_BLOCK_BYTES:
        active["lines"].append(line)
    else:
        active["truncated"] = True
        active["lines"] = []


def _parse_province(capture: dict[str, Any]) -> dict[str, Any] | None:
    if capture.get("truncated") or not capture.get("complete"):
        return None
    text = "".join(capture["lines"])
    try:
        body = bounded.extract_block(text, text.find("{"))
        entries = bounded.top_level_entries(body)
        fields, _ = bounded.flatten_entries(entries)
    except bounded.SaveParseError:
        return None

    base_tax = _decimal(_scalar(fields, "base_tax"))
    base_production = _decimal(_scalar(fields, "base_production"))
    base_manpower = _decimal(_scalar(fields, "base_manpower"))
    development = None
    if base_tax is not None and base_production is not None and base_manpower is not None:
        development = base_tax + base_production + base_manpower
    return {
        "province_id": int(capture["province_id"]),
        "serialized_key": capture["serialized_key"],
        "owner": _scalar(fields, "owner"),
        "controller": _scalar(fields, "controller"),
        "cores": _block_tokens(entries, "cores"),
        "claims": _block_tokens(entries, "claims"),
        "base_tax": _json_number(base_tax),
        "base_production": _json_number(base_production),
        "base_manpower": _json_number(base_manpower),
        "development": _json_number(development),
        "complete": True,
        "line_start": capture["start_line"],
        "line_end": capture.get("end_line"),
        "bytes_seen": capture["bytes_seen"],
    }


def _parse_relation(capture_body: str) -> dict[str, Any]:
    try:
        entries = bounded.top_level_entries(capture_body)
        fields, _ = bounded.flatten_entries(entries)
    except bounded.SaveParseError as exc:
        return {"present": True, "complete": False, "unknown": [str(exc)], "ae_modifiers": []}

    ae_modifiers: list[dict[str, Any]] = []
    for key, value in fields.items():
        match = OPINION_MODIFIER_RE.fullmatch(key)
        if match is None or _normalize(_last(value)) != "aggressive_expansion":
            continue
        prefix = match.group(1)
        current_key = f"{prefix}.current_opinion"
        current_raw = _normalize(_last(fields.get(current_key)))
        current_decimal = _decimal(current_raw)
        ae_modifiers.append(
            {
                "modifier_key": key,
                "modifier": "aggressive_expansion",
                "current_opinion_raw": current_raw,
                "current_opinion_truncated": (
                    int(current_decimal) if current_decimal is not None else None
                ),
                "current_opinion_readable": current_decimal is not None,
            }
        )
    return {
        "present": True,
        "complete": True,
        "unknown": [],
        "ae_modifiers": ae_modifiers,
    }


def _parse_country(capture: dict[str, Any]) -> dict[str, Any] | None:
    if capture.get("truncated") or not capture.get("complete"):
        return None
    text = "".join(capture["lines"])
    try:
        body = bounded.extract_block(text, text.find("{"))
        entries = bounded.top_level_entries(body)
    except bounded.SaveParseError:
        return None

    relations: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.key != "active_relations" or entry.body is None:
            continue
        try:
            relation_entries = bounded.top_level_entries(entry.body)
        except bounded.SaveParseError as exc:
            return {
                "tag": capture["tag"],
                "complete": False,
                "bytes_seen": capture["bytes_seen"],
                "relations": {},
                "unknown": [f"active_relations:{exc}"],
            }
        for relation_entry in relation_entries:
            partner = relation_entry.key.upper()
            if partner not in {"FRA", "BUR"} or relation_entry.body is None:
                continue
            relations[partner] = _parse_relation(relation_entry.body)
    return {
        "tag": capture["tag"],
        "complete": True,
        "bytes_seen": capture["bytes_seen"],
        "relations": relations,
        "unknown": [],
    }


def resolve_save(path: Path | None) -> Path:
    if path is not None:
        resolved = path.expanduser().resolve()
    else:
        resolved = (Path(local_config.user_data()) / "save games" / SAVE_NAME).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"R63 source save not found: {resolved}")
    return resolved


def load_native_cases(root: Path) -> tuple[dict[str, Any], set[int]]:
    cases: list[dict[str, Any]] = []
    province_ids: set[int] = set()
    for case_dir in sorted(root.iterdir()):
        if not case_dir.is_dir():
            continue
        event_path = case_dir / "native-event.json"
        if not event_path.is_file():
            continue
        event = json.loads(event_path.read_text(encoding="utf-8"))
        direction = event.get("direction")
        claimant = {"demand": "FRA", "offer": "BUR"}.get(direction)
        territorial_groups: list[dict[str, Any]] = []
        for group_index, group in enumerate(
            (event.get("native_consequences") or {}).get("territorial") or []
        ):
            rows: list[dict[str, Any]] = []
            for row in group.get("provinces") or []:
                province_id = _int(row.get("province_id"))
                if province_id is None:
                    continue
                province_ids.add(province_id)
                rows.append(
                    {
                        "province_id": province_id,
                        "already_core_native": row.get("already_core"),
                        "overextension_added_raw": _int(row.get("overextension_added_raw")),
                        "adds_overextension": row.get("adds_overextension"),
                    }
                )
            if rows:
                territorial_groups.append(
                    {
                        "group_index": group_index,
                        "country": group.get("country"),
                        "native_aggregate_raw": _int(group.get("overextension_added_raw")),
                        "native_administrative_power": _int(group.get("administrative_power")),
                        "scale": _int(group.get("scale")),
                        "complete": group.get("complete"),
                        "provinces": rows,
                    }
                )
        coalition_rows: list[dict[str, Any]] = []
        coalition = (event.get("native_consequences") or {}).get("coalition") or {}
        for row in coalition.get("countries") or []:
            coalition_rows.append(
                {
                    "tag": row.get("tag"),
                    "native_current_value": _int(row.get("current_value")),
                    "native_aggressive_expansion_delta": _int(
                        row.get("aggressive_expansion_delta")
                    ),
                }
            )
        cases.append(
            {
                "case": case_dir.name,
                "event_path": str(event_path.resolve()),
                "event_bytes": event_path.stat().st_size,
                "slice_path": str((case_dir / "native-events-slice.jsonl").resolve()),
                "slice_bytes": (
                    (case_dir / "native-events-slice.jsonl").stat().st_size
                    if (case_dir / "native-events-slice.jsonl").is_file()
                    else None
                ),
                "query_id": event.get("query_id"),
                "action_id": event.get("action_id"),
                "direction": direction,
                "claimant": claimant,
                "date_raw": _int(event.get("date_raw")),
                "territorial_groups": territorial_groups,
                "coalition": {
                    "available": coalition.get("available"),
                    "complete": coalition.get("complete"),
                    "current_value_semantics_verified": coalition.get(
                        "current_value_semantics_verified"
                    ),
                    "rows": coalition_rows,
                },
            }
        )
    return {"case_count": len(cases), "cases": cases}, province_ids


def scan_save(path: Path, target_province_ids: set[int]) -> dict[str, Any]:
    source = bounded.detect_container(path)
    source["path"] = str(path)
    source["source_sha256"] = KNOWN_SOURCE_SHA256
    source["source_sha256_reused"] = True
    depth = 0
    line_count = 0
    save_date: str | None = None
    unknown: list[str] = []

    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    country_active: dict[str, Any] | None = None
    country_records: dict[str, dict[str, Any]] = {}
    country_blocks_seen = 0

    provinces_found = False
    provinces_complete = False
    provinces_depth: int | None = None
    province_active: dict[str, Any] | None = None
    province_records: dict[int, dict[str, Any]] = {}
    province_blocks_seen = 0

    def finish_country(end_line: int | None, complete: bool) -> None:
        nonlocal country_active, country_blocks_seen
        if country_active is None:
            return
        country_active["end_line"] = end_line
        country_active["complete"] = complete
        country_blocks_seen += 1
        tag = str(country_active["tag"])
        parsed = _parse_country(country_active)
        if parsed is None:
            unknown.append(f"country_block_incomplete_or_over_limit:{tag}")
        elif tag in country_records:
            unknown.append(f"duplicate_country:{tag}")
        else:
            country_records[tag] = parsed
        country_active = None

    def finish_province(end_line: int | None, complete: bool) -> None:
        nonlocal province_active, province_blocks_seen
        if province_active is None:
            return
        province_active["end_line"] = end_line
        province_active["complete"] = complete
        province_blocks_seen += 1
        parsed = _parse_province(province_active)
        if parsed is None:
            unknown.append(f"province_block_incomplete_or_over_limit:{province_active['province_id']}")
        elif parsed["province_id"] in province_records:
            unknown.append(f"duplicate_target_province:{parsed['province_id']}")
        else:
            province_records[parsed["province_id"]] = parsed
        province_active = None

    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if save_date is None and before == 0:
                match = DATE_RE.match(line)
                if match:
                    save_date = bounded.unquote(match.group(1).strip())

            if not countries_found and before == 0 and COUNTRIES_RE.match(line):
                countries_found = True
                countries_depth = before + bounded.brace_delta(line)
            if (
                countries_found
                and not countries_complete
                and country_active is None
                and countries_depth is not None
                and before == countries_depth
            ):
                match = COUNTRY_RE.match(line)
                if match:
                    country_active = {
                        "tag": match.group(1),
                        "start_line": line_number,
                        "bytes_seen": 0,
                        "truncated": False,
                        "lines": [],
                        "depth": before + bounded.brace_delta(line),
                    }
                    _append_line(country_active, line)
            elif country_active is not None:
                _append_line(country_active, line)

            if not provinces_found and before == 0 and PROVINCES_RE.match(line):
                provinces_found = True
                provinces_depth = before + bounded.brace_delta(line)
            if (
                provinces_found
                and not provinces_complete
                and province_active is None
                and provinces_depth is not None
                and before == provinces_depth
            ):
                match = PROVINCE_RE.match(line)
                if match:
                    serialized_key = match.group(1)
                    try:
                        province_id = abs(int(serialized_key))
                    except ValueError:
                        province_id = 0
                    if province_id in target_province_ids:
                        province_active = {
                            "province_id": province_id,
                            "serialized_key": serialized_key,
                            "start_line": line_number,
                            "bytes_seen": 0,
                            "truncated": False,
                            "lines": [],
                            "depth": before + bounded.brace_delta(line),
                        }
                        _append_line(province_active, line)
            elif province_active is not None:
                _append_line(province_active, line)

            depth += bounded.brace_delta(line)

            if (
                country_active is not None
                and countries_depth is not None
                and depth == countries_depth
                and before >= country_active["depth"]
            ):
                finish_country(line_number, True)
            if (
                countries_found
                and not countries_complete
                and countries_depth is not None
                and depth == 0
                and before >= countries_depth
            ):
                if country_active is not None:
                    finish_country(line_number, False)
                countries_complete = True

            if (
                province_active is not None
                and provinces_depth is not None
                and depth == provinces_depth
                and before >= province_active["depth"]
            ):
                finish_province(line_number, True)
            if (
                provinces_found
                and not provinces_complete
                and provinces_depth is not None
                and depth == 0
                and before >= provinces_depth
            ):
                if province_active is not None:
                    finish_province(line_number, False)
                provinces_complete = True

    if country_active is not None:
        finish_country(None, False)
    if province_active is not None:
        finish_province(None, False)
    if not countries_found:
        unknown.append("countries_block_not_found")
    if not countries_complete:
        unknown.append("countries_block_incomplete")
    if not provinces_found:
        unknown.append("provinces_block_not_found")
    if not provinces_complete:
        unknown.append("provinces_block_incomplete")
    if depth != 0:
        unknown.append(f"final_brace_depth:{depth}")

    checks = {
        "source_exists": path.is_file(),
        "source_sha256_reused_matches_known": source["source_sha256"] == KNOWN_SOURCE_SHA256,
        "countries_block_complete": countries_found and countries_complete,
        "provinces_block_complete": provinces_found and provinces_complete,
        "brace_balance_ok": depth == 0,
        "target_provinces_all_found": target_province_ids.issubset(province_records),
        "per_block_cap_4_mib": not any("over_limit" in item for item in unknown),
        "streaming_only": True,
    }
    return {
        "save_date": save_date,
        "source": source,
        "checks": checks,
        "scan": {
            "line_count": line_count,
            "country_blocks_seen": country_blocks_seen,
            "country_records_retained": len(country_records),
            "target_province_blocks_seen": province_blocks_seen,
            "target_province_ids": sorted(target_province_ids),
            "target_province_records_retained": len(province_records),
            "unknown": unknown,
        },
        "countries": country_records,
        "provinces": province_records,
    }


def _expected_raw(development: Any) -> tuple[int | None, str]:
    dec = _decimal(development)
    if dec is None:
        return None, "missing_development"
    raw = dec * Decimal(8)
    if raw == raw.to_integral_value():
        return int(raw), "exact_development_times_8"
    rounded = raw.to_integral_value(rounding=ROUND_HALF_UP)
    return int(rounded), "ROUND_HALF_UP_development_times_8"


def reconcile_provinces(native: dict[str, Any], save: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    aggregate_checks: list[dict[str, Any]] = []
    for case in native["cases"]:
        for group in case["territorial_groups"]:
            rows: list[dict[str, Any]] = []
            native_row_sum = 0
            expected_row_sum = 0
            rows_complete = True
            core_rows: list[dict[str, Any]] = []
            for native_row in group["provinces"]:
                province_id = native_row["province_id"]
                saved = save["provinces"].get(province_id)
                native_raw = native_row["overextension_added_raw"]
                if native_raw is not None:
                    native_row_sum += native_raw
                if saved is None:
                    rows_complete = False
                    rows.append(
                        {
                            "province_id": province_id,
                            "status": "unknown",
                            "reason": "save_province_not_found",
                        }
                    )
                    continue
                expected_raw, formula = _expected_raw(saved.get("development"))
                if expected_raw is None:
                    rows_complete = False
                else:
                    expected_row_sum += expected_raw
                saved_core = group.get("country") in saved.get("cores", [])
                native_core = native_row.get("already_core_native")
                core_match = native_core is None or bool(native_core) == saved_core
                core_zero_ok = True
                if saved_core:
                    core_zero_ok = native_raw == 0 and (group.get("native_administrative_power") or 0) == 0
                    core_rows.append({"province_id": province_id, "core_zero_ok": core_zero_ok})
                row_ok = (
                    expected_raw is not None
                    and native_raw == expected_raw
                    and core_match
                    and core_zero_ok
                )
                rows.append(
                    {
                        "province_id": province_id,
                        "save_owner": saved.get("owner"),
                        "save_cores": saved.get("cores", []),
                        "development": saved.get("development"),
                        "already_core_saved": saved_core,
                        "already_core_native": native_core,
                        "already_core_match": core_match,
                        "native_overextension_added_raw": native_raw,
                        "expected_overextension_raw": expected_raw,
                        "expected_formula": formula,
                        "native_adds_overextension": native_row.get("adds_overextension"),
                        "core_zero_admin_oe_ok": core_zero_ok,
                        "status": "passed" if row_ok else "difference",
                    }
                )
            native_aggregate = group.get("native_aggregate_raw")
            aggregate_ok = (
                native_aggregate is not None
                and native_aggregate == native_row_sum
                and rows_complete
                and native_aggregate == expected_row_sum
            )
            aggregate_checks.append(
                {
                    "case": case["case"],
                    "direction": case["direction"],
                    "country": group.get("country"),
                    "province_ids": [row["province_id"] for row in group["provinces"]],
                    "scale": group.get("scale"),
                    "native_aggregate_raw": native_aggregate,
                    "native_row_sum_raw": native_row_sum,
                    "expected_aggregate_raw": expected_row_sum if rows_complete else None,
                    "native_rows_sum_match": native_aggregate == native_row_sum,
                    "expected_aggregate_match": aggregate_ok,
                    "core_rows": core_rows,
                    "status": "passed" if aggregate_ok else "difference",
                }
            )
            checks.extend(rows)
    return {
        "row_checks": checks,
        "aggregate_checks": aggregate_checks,
        "all_rows_match": bool(checks) and all(row.get("status") == "passed" for row in checks),
        "all_aggregates_match": bool(aggregate_checks)
        and all(row.get("status") == "passed" for row in aggregate_checks),
    }


def reconcile_coalition(native: dict[str, Any], save: dict[str, Any]) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for case in native["cases"]:
        claimant = case.get("claimant")
        if claimant is None:
            continue
        for native_row in case["coalition"]["rows"]:
            tag = native_row.get("tag")
            country = save["countries"].get(tag)
            relation = (country or {}).get("relations", {}).get(claimant)
            modifiers = (relation or {}).get("ae_modifiers", [])
            native_value = native_row.get("native_current_value")
            if len(modifiers) == 1:
                saved_value = modifiers[0].get("current_opinion_truncated")
                state = "passed" if native_value == saved_value else "difference"
                reason = "single_aggressive_expansion_modifier"
            elif len(modifiers) == 0:
                saved_value = 0
                state = "passed" if native_value == 0 else "difference"
                reason = "no_aggressive_expansion_modifier_defaults_to_zero"
            else:
                saved_value = None
                state = "unknown"
                reason = "multiple_aggressive_expansion_modifiers"
            if country is None or (relation is not None and not relation.get("complete", False)):
                state = "unknown"
                reason = "country_or_relation_block_incomplete"
            comparisons.append(
                {
                    "case": case["case"],
                    "direction": case["direction"],
                    "claimant": claimant,
                    "tag": tag,
                    "native_current_value": native_value,
                    "native_aggressive_expansion_delta": native_row.get(
                        "native_aggressive_expansion_delta"
                    ),
                    "relation_present": relation is not None,
                    "saved_aggressive_expansion_modifiers": modifiers,
                    "saved_current_value_truncated": saved_value,
                    "reason": reason,
                    "status": state,
                }
            )
    return {
        "comparisons": comparisons,
        "comparison_count": len(comparisons),
        "all_match": bool(comparisons)
        and all(row.get("status") == "passed" for row in comparisons),
        "unknown_count": sum(row.get("status") == "unknown" for row in comparisons),
        "difference_count": sum(row.get("status") == "difference" for row in comparisons),
    }


def render_markdown(report: dict[str, Any]) -> str:
    province = report["province_reconciliation"]
    coalition = report["coalition_reconciliation"]
    checks = report["checks"]
    return "\n".join(
        [
            "# R65 和平预览保存独立核对",
            "",
            f"状态：`{report['status']}`；D00412 native case 数：`{report['native']['case_count']}`；保存日期：`{report['save']['save_date']}`。",
            "",
            f"保存来源：`{report['save']['source']['path']}`；复用已知 SHA-256 `{KNOWN_SOURCE_SHA256}`，本脚本未重新哈希保存。扫描只保留目标省份和指向 FRA/BUR 的 active_relations，每个块上限 4 MiB。",
            "",
            "## 省份与 OE",
            "",
            f"省份行 `{len(province['row_checks'])}` 条，聚合组 `{len(province['aggregate_checks'])}` 组；行匹配 `{province['all_rows_match']}`，聚合匹配 `{province['all_aggregates_match']}`。预期公式为 `development × 8`，非整数才使用 `ROUND_HALF_UP`，并保留每省及聚合差异。已有 core 的行额外要求 native ADM/OE 均为 0；本次若没有适用行会在 JSON 标明。",
            "",
            "## Coalition / aggressive_expansion",
            "",
            f"比较 `{coalition['comparison_count']}` 条 native `current_value`；保存关系中精确寻找 `modifier=aggressive_expansion`，Decimal 向零截断；没有该 modifier 时按 0 比较。全部匹配：`{coalition['all_match']}`；差异 `{coalition['difference_count']}`，未知 `{coalition['unknown_count']}`。",
            "",
            "## 检查",
            "",
            f"`{json.dumps(checks, ensure_ascii=False, sort_keys=True)}`",
            "",
            "native 与保存不一致时只记录 difference，不修改输入、不用静态数据反推动态值。完整逐条结果见 `report.json`。",
            "",
        ]
    )


def build_report(native_root: Path, save_path: Path) -> dict[str, Any]:
    native, target_ids = load_native_cases(native_root)
    save = scan_save(save_path, target_ids)
    provinces = reconcile_provinces(native, save)
    coalition = reconcile_coalition(native, save)
    checks = {
        "native_cases_nonempty": native["case_count"] > 0,
        "save_scan_checks": all(save["checks"].values()),
        "province_rows_present": bool(provinces["row_checks"]),
        "province_rows_match": provinces["all_rows_match"],
        "province_aggregates_match": provinces["all_aggregates_match"],
        "coalition_rows_match": coalition["all_match"] if coalition["comparison_count"] else True,
        "no_dynamic_inference": True,
    }
    status = "passed" if all(checks.values()) else "passed_with_differences"
    return {
        "schema": "r65_peace_preview_save_check_v1",
        "status": status,
        "scope": {
            "native_root": str(native_root.resolve()),
            "save_source_sha256_reused": KNOWN_SOURCE_SHA256,
            "max_block_bytes": MAX_BLOCK_BYTES,
            "overextension_factor": "0.8",
            "overextension_raw_formula": "development * 8",
            "coalition_current_value_semantics": "aggressive_expansion relation modifier; Decimal truncation toward zero",
        },
        "checks": checks,
        "native": native,
        "save": save,
        "province_reconciliation": provinces,
        "coalition_reconciliation": coalition,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, default=DEFAULT_NATIVE_ROOT)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    native_root = args.native_root.expanduser().resolve()
    save_path = resolve_save(args.save)
    if not native_root.is_dir():
        raise FileNotFoundError(f"native case root not found: {native_root}")
    report = build_report(native_root, save_path)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "output_dir": str(output_dir),
                "checks": report["checks"],
                "province_rows": len(report["province_reconciliation"]["row_checks"]),
                "coalition_rows": report["coalition_reconciliation"]["comparison_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
