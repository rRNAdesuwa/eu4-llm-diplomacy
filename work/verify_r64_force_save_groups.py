#!/usr/bin/env python3
"""Compare R64 public force-query totals with the saved country blocks.

The two R64 query reports expose one force snapshot per case.  This verifier
collects the union of their attacker and defender country tags, then streams
the prepared R64 save once.  Only one direct child of the top-level
``countries`` block is retained at a time.  The existing bounded country
parser is reused for regiment decoding; this file supplies the tag-agnostic
streaming wrapper so advisor or other same-named blocks cannot be mistaken for
countries.

The saved value comparison is deliberately explicit: each regiment contributes
``strength * 1000`` to infantry/cavalry/artillery, and a missing ``strength``
uses the already established 1.000 full-strength assumption.  Country
``manpower * 1000`` is compared with the public reserve value.  No save hash is
recomputed here; the scene manifest already records the destination hash.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work import inspect_r64_force_save as baseline


MAX_REPORT_BYTES = 10 * 1024 * 1024
MAX_COUNTRY_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_CONDENSED_REGIMENT_BYTES = 512 * 1024
COUNTRIES_RE = re.compile(r"^\s*countries\s*=\s*\{")
TAG_BLOCK_RE = re.compile(r"^\s*([A-Za-z0-9_]{3})\s*=\s*\{")

DEFAULT_SCENE_REPORT = ROOT / "work" / "runtime" / "r64-force-scene-20261019-001" / "report.json"
DEFAULT_BATCH_REPORTS = (
    ROOT / "work" / "runtime" / "r64-force-query-batch-20261019-001" / "report.json",
    ROOT / "work" / "runtime" / "r64-force-query-milan-20261019-002" / "report.json",
)
DEFAULT_OUTPUT = ROOT / "work" / "runtime" / "r64-force-save-groups-20261019-001"


def _load_small_json(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError(f"report exceeds bounded JSON limit: {path} ({size} bytes)")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _decimal_scaled(value: Decimal | None, scale: int = 1000) -> int | str | None:
    if value is None:
        return None
    scaled = value * Decimal(scale)
    if scaled == scaled.to_integral_value():
        return int(scaled)
    return format(scaled, "f")


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _force_kind(unit_type: str) -> int | None:
    """Map save unit names to the three public force buckets."""

    kind = baseline._native_kind(unit_type)
    if kind is not None:
        return kind
    # The R64 scene includes Mamluk archer regiments.  The public native
    # snapshot places their saved strength in the infantry bucket; keep this
    # local to the verifier instead of widening the older four-country parser.
    if unit_type.casefold() == "mamluk_archer":
        return 0
    return None


def _direct_value(record: dict[str, Any] | None) -> str | None:
    if not record:
        return None
    value = record.get("value")
    if value is not None:
        return str(value)
    raw = record.get("raw")
    return str(raw) if raw is not None else None


def _condense_country(capture: dict[str, Any]) -> dict[str, Any]:
    """Parse one capture, retaining only fields needed by this comparison."""

    parsed = baseline._parse_country(capture)
    direct: dict[str, dict[str, Any] | None] = {}
    for key in ("manpower", "max_manpower", "llm_manpower"):
        values = parsed.get("direct_fields", {}).get(key, [])
        direct[key] = values[-1] if values else None

    kind_sums: dict[str, Decimal] = {
        "infantry": Decimal("0"),
        "cavalry": Decimal("0"),
        "artillery": Decimal("0"),
    }
    unknown_unit_types: list[str] = []
    groups: list[dict[str, Any]] = []
    for group in parsed.get("unit_groups", []):
        unit_type = str(group.get("unit_type") or "")
        native_kind = _force_kind(unit_type)
        effective = baseline._decimal(group.get("effective_strength_sum"))
        if effective is None:
            effective = Decimal("0")
        if native_kind is None:
            unknown_unit_types.append(unit_type)
        else:
            kind_sums[("infantry", "cavalry", "artillery")[native_kind]] += effective
        groups.append(
            {
                "unit_type": unit_type,
                "native_kind": native_kind,
                "count": group.get("count"),
                "explicit_strength_count": group.get("explicit_strength_count"),
                "missing_strength_count": group.get("missing_strength_count"),
                "effective_strength_sum": group.get("effective_strength_sum"),
                "row_line_starts": list(group.get("row_line_starts", [])),
            }
        )

    regiment_rows: list[dict[str, Any]] = []
    for row in parsed.get("regiments", []):
        regiment_rows.append(
            {
                "army_line_start": row.get("army_line_start"),
                "regiment_line_start": row.get("regiment_line_start"),
                "regiment_id": row.get("regiment_id"),
                "unit_type": row.get("unit_type"),
                "native_kind": _force_kind(str(row.get("unit_type") or "")),
                "strength_raw": row.get("strength_raw"),
                "strength_decimal": row.get("strength_decimal"),
                "strength_present": row.get("strength_present"),
                "effective_strength_for_sum": row.get("effective_strength_for_sum"),
                "effective_strength_assumption": row.get("effective_strength_assumption"),
            }
        )

    condensed = {
        "tag": parsed.get("tag"),
        "block": parsed.get("block"),
        "direct_fields": direct,
        "manpower_raw": _direct_value(direct.get("manpower")),
        "max_manpower_raw": _direct_value(direct.get("max_manpower")),
        "army_count": parsed.get("army_count"),
        "regiment_count": parsed.get("regiment_count"),
        "unit_groups": groups,
        "regiment_records": regiment_rows,
        "kind_effective_strength": {
            key: format(value, "f") for key, value in kind_sums.items()
        },
        "kind_effective_strength_x1000": {
            key: _decimal_scaled(value) for key, value in kind_sums.items()
        },
        "unknown_unit_types": sorted(set(unknown_unit_types)),
        "parser_unknown": list(parsed.get("unknown", [])),
        "queue_like_block_count": len(parsed.get("queue_like_blocks", [])),
    }
    condensed_size = _json_size(condensed.get("regiment_records", []))
    condensed["regiment_records_bytes"] = condensed_size
    condensed["regiment_records_within_limit"] = condensed_size <= MAX_CONDENSED_REGIMENT_BYTES
    return condensed


def _stream_country_records(
    save_path: Path, tags: set[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Stream one direct country block at a time from an EU4 save."""

    source = bounded.detect_container(save_path)
    records: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    depth = 0
    line_count = 0
    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    countries_closed_line: int | None = None
    current: dict[str, Any] | None = None

    def finish(end_line: int | None, complete: bool) -> None:
        nonlocal current
        if current is None:
            return
        tag = str(current["tag"])
        item = {
            "tag": tag,
            "start_line": current["start_line"],
            "end_line": end_line,
            "complete": bool(complete and not current["too_large"]),
            "bytes_captured": current["bytes_captured"],
            "bytes_seen": current["bytes_seen"],
            "text": "".join(current["lines"]),
        }
        if tag in records:
            duplicates.append(tag)
        elif current["too_large"]:
            records[tag] = {
                "tag": tag,
                "block": {
                    "start_line": current["start_line"],
                    "end_line": end_line,
                    "complete": False,
                    "bytes_captured": current["bytes_captured"],
                    "bytes_seen": current["bytes_seen"],
                },
                "capture_too_large": True,
            }
        else:
            records[tag] = _condense_country(item)
        current = None

    with bounded.open_gamestate(save_path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if not countries_found and before == 0 and COUNTRIES_RE.match(line):
                countries_found = True
                countries_depth = before + bounded.brace_delta(line)

            if (
                current is None
                and not countries_complete
                and countries_depth is not None
                and before == countries_depth
            ):
                match = TAG_BLOCK_RE.match(line)
                if match and match.group(1) in tags:
                    size = len(line.encode("utf-8", "replace"))
                    current = {
                        "tag": match.group(1),
                        "start_line": line_number,
                        "block_depth": before + bounded.brace_delta(line),
                        "lines": [line] if size <= MAX_COUNTRY_CAPTURE_BYTES else [],
                        "bytes_captured": size if size <= MAX_COUNTRY_CAPTURE_BYTES else 0,
                        "bytes_seen": size,
                        "too_large": size > MAX_COUNTRY_CAPTURE_BYTES,
                    }
            elif current is not None:
                size = len(line.encode("utf-8", "replace"))
                current["bytes_seen"] += size
                if not current["too_large"]:
                    if current["bytes_captured"] + size <= MAX_COUNTRY_CAPTURE_BYTES:
                        current["lines"].append(line)
                        current["bytes_captured"] += size
                    else:
                        current["too_large"] = True
                        current["lines"] = []

            depth += bounded.brace_delta(line)
            if (
                current is not None
                and countries_depth is not None
                and depth == countries_depth
                and before >= current["block_depth"]
            ):
                finish(line_number, True)

            if (
                countries_found
                and countries_depth is not None
                and depth == 0
                and before >= countries_depth
            ):
                if current is not None:
                    finish(line_number, False)
                countries_complete = True
                countries_closed_line = line_number

    if current is not None:
        finish(None, False)
    return records, {
        "container": source,
        "line_count": line_count,
        "countries_found": countries_found,
        "countries_complete": countries_complete,
        "countries_depth": countries_depth,
        "countries_closed_line": countries_closed_line,
        "requested_tags": sorted(tags),
        "found_tags": sorted(records),
        "missing_tags": sorted(tags - set(records)),
        "duplicate_tags": duplicates,
        "one_country_capture_at_a_time": True,
        "country_capture_limit_bytes": MAX_COUNTRY_CAPTURE_BYTES,
    }


def _collect_public_cases(report_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    report_meta: list[dict[str, Any]] = []
    for path in report_paths:
        report = _load_small_json(path)
        report_meta.append(
            {
                "path": str(path.resolve()),
                "status": report.get("status"),
                "session_id": report.get("session_id"),
                "session_date_raw": report.get("session_date_raw"),
                "case_count": len(report.get("cases", [])),
                "summary": report.get("summary"),
            }
        )
        for index, case in enumerate(report.get("cases", [])):
            public = case.get("public_result") or {}
            forces = public.get("forces")
            if not isinstance(forces, dict):
                continue
            sides: dict[str, dict[str, Any]] = {}
            for side_name in ("attackers", "defenders"):
                side = forces.get(side_name)
                if not isinstance(side, dict):
                    continue
                sides[side_name] = {
                    "countries": list(side.get("countries") or []),
                    "deployed": dict(side.get("deployed") or {}),
                    "reserve_manpower": dict(side.get("reserve_manpower") or {}),
                    # The public contract places completion on the nested
                    # deployed/reserve objects; absent side-level fields are
                    # therefore treated as the contract's default true.
                    "complete": side.get("complete", True),
                    "scope_complete": side.get("scope_complete", True),
                }
            cases.append(
                {
                    "case_id": f"{path.parent.name}:{index}:{case.get('label')}",
                    "report": str(path.resolve()),
                    "report_index": index,
                    "label": case.get("label"),
                    "recipient": case.get("recipient"),
                    "status": case.get("status"),
                    "query_id": case.get("query_id"),
                    "sides": sides,
                    "forces_complete": forces.get("complete"),
                }
            )
    return cases, {"reports": report_meta}


def _compare_side(
    case: dict[str, Any], side_name: str, side: dict[str, Any], records: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    countries = [str(tag) for tag in side.get("countries", [])]
    found = [tag for tag in countries if tag in records]
    missing = [tag for tag in countries if tag not in records]
    unique = len(countries) == len(set(countries))
    country_details: dict[str, Any] = {}
    sums = {"infantry": Decimal("0"), "cavalry": Decimal("0"), "artillery": Decimal("0")}
    reserve = Decimal("0")
    manpower_complete = True
    mapped = True
    capture_complete = True
    condensed_limit = True
    unknown_unit_types: set[str] = set()

    for tag in countries:
        record = records.get(tag)
        if record is None:
            manpower_complete = False
            mapped = False
            capture_complete = False
            continue
        if not record.get("block", {}).get("complete"):
            capture_complete = False
        if not record.get("regiment_records_within_limit", True):
            condensed_limit = False
        unknown_unit_types.update(record.get("unknown_unit_types", []))
        if record.get("capture_too_large"):
            mapped = False
            capture_complete = False
            continue
        manpower = baseline._decimal(record.get("manpower_raw"))
        if manpower is None:
            manpower_complete = False
        else:
            reserve += manpower
        details = {
            "block": record.get("block"),
            "manpower_raw": record.get("manpower_raw"),
            "manpower_x1000": _decimal_scaled(manpower),
            "kind_effective_strength": record.get("kind_effective_strength"),
            "kind_effective_strength_x1000": record.get("kind_effective_strength_x1000"),
            "army_count": record.get("army_count"),
            "regiment_count": record.get("regiment_count"),
        }
        country_details[tag] = details
        for kind in sums:
            value = baseline._decimal((record.get("kind_effective_strength") or {}).get(kind))
            if value is None:
                value = Decimal("0")
            sums[kind] += value
        if record.get("unknown_unit_types") or record.get("parser_unknown"):
            mapped = False

    deployed = side.get("deployed") or {}
    reserve_public = side.get("reserve_manpower") or {}
    saved_deployed = {kind: _decimal_scaled(sums[kind]) for kind in sums}
    saved_deployed["total"] = _decimal_scaled(sum(sums.values(), Decimal("0")))
    saved_reserve = _decimal_scaled(reserve if manpower_complete else None)
    public_deployed = {kind: _int_value(deployed.get(kind)) for kind in (*sums, "total")}
    public_reserve = _int_value(reserve_public.get("amount"))

    checks = {
        "forces_complete": case.get("forces_complete") is True,
        "side_complete": (
            side.get("complete", True) is True
            and side.get("scope_complete", True) is True
            and deployed.get("complete") is True
            and reserve_public.get("complete") is True
        ),
        "countries_nonempty_and_unique": bool(countries) and unique,
        "all_country_blocks_found": not missing,
        "country_blocks_complete": capture_complete,
        "regiment_records_within_512KiB": condensed_limit,
        "unit_kinds_mapped": mapped and not unknown_unit_types,
        "deployed_infantry_match": saved_deployed["infantry"] == public_deployed["infantry"],
        "deployed_cavalry_match": saved_deployed["cavalry"] == public_deployed["cavalry"],
        "deployed_artillery_match": saved_deployed["artillery"] == public_deployed["artillery"],
        "deployed_total_match": saved_deployed["total"] == public_deployed["total"],
        "reserve_manpower_match": manpower_complete and saved_reserve == public_reserve,
    }
    return {
        "case_id": case.get("case_id"),
        "report": case.get("report"),
        "report_index": case.get("report_index"),
        "label": case.get("label"),
        "recipient": case.get("recipient"),
        "side": side_name,
        "countries": countries,
        "missing_country_blocks": missing,
        "unknown_unit_types": sorted(unknown_unit_types),
        "country_contributions": country_details,
        "saved_aggregate": {
            "deployed": saved_deployed,
            "reserve_manpower": {"amount": saved_reserve, "unit": "men", "scale": 1000},
        },
        "public_aggregate": {
            "deployed": deployed,
            "reserve_manpower": reserve_public,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    checks = payload["checks"]
    lines = [
        "# R64 查询军力与保存字段对照",
        "",
        "本报告把两份已通过的R64公共查询报告中的18个case逐侧汇总，再与同一实验场景保存中的国家块比较。保存解析只在顶层 `countries` 块内识别目标国家，并在完成一个国家块后立即释放其原文。",
        "",
        f"- 结论：`{payload['status']}`；case：{payload['case_count']}；双方：{payload['case_side_count']}；逐侧检查通过：{payload['case_side_checks_passed']}/{payload['case_side_checks_total']}。",
        f"- 场景保存：`{payload['scene']['destination']}`（沿用场景报告记录的SHA，不在本次重复计算）。",
        f"- 保存大小：{payload['scene'].get('destination_size_bytes', '未在场景报告中记录')} bytes；国家块上限：{MAX_COUNTRY_CAPTURE_BYTES} bytes。",
        "",
        "## 查询来源",
        "",
        "|报告|状态|case数|会话|日期|",
        "|---|---|---:|---|---:|",
    ]
    for report in payload["query_reports"]:
        lines.append(
            f"|`{report['path']}`|{report['status']}|{report['case_count']}|`{report['session_id']}`|`{report['session_date_raw']}`|"
        )
    lines.extend(
        [
            "",
            "公共结果的 `deployed` 字段按步兵、骑兵、炮兵和总人数记录；保存端按每个 regiment 的 `strength` 求和后乘1000。保存缺少 `strength` 时沿用既有基线验证过的 1.000 假设。`manpower` 同样乘1000后与公共 `reserve_manpower.amount` 比较。R64场景中的 `mamluk_archer` 按公共快照归入步兵。",
            "",
            "## 国家集合与流式边界",
            "",
            f"查询双方国家并集共 {len(payload['country_union'])} 个：`{'、'.join(payload['country_union'])}`。",
            f"国家根块发现：`{payload['save_scan']['countries_found']}`；根块闭合：`{payload['save_scan']['countries_complete']}`；目标块缺失：`{payload['save_scan']['missing_tags']}`；重复直接块：`{payload['save_scan']['duplicate_tags']}`。",
            f"每次只保留一个国家块，单块上限 {MAX_COUNTRY_CAPTURE_BYTES} bytes；提炼后的 regiment 记录上限 {MAX_CONDENSED_REGIMENT_BYTES} bytes。",
            "",
            "## 结果",
            "",
            "|case|接收国|一方|国家数|保存步/骑/炮/总|公共步/骑/炮/总|保存后备|公共后备|",
            "|---|---|---|---:|---|---|---:|---:|",
        ]
    )
    for item in payload["case_sides"]:
        sv = item["saved_aggregate"]["deployed"]
        pv = item["public_aggregate"]["deployed"]
        lines.append(
            f"|`{item['label']}`|{item['recipient']}|{item['side']}|{len(item['countries'])}|"
            f"{sv['infantry']}/{sv['cavalry']}/{sv['artillery']}/{sv['total']}|"
            f"{pv.get('infantry')}/{pv.get('cavalry')}/{pv.get('artillery')}/{pv.get('total')}|"
            f"{item['saved_aggregate']['reserve_manpower']['amount']}|{item['public_aggregate']['reserve_manpower']}|"
        )
    lines.extend(
        [
            "",
            f"全局检查通过 {payload['checks_passed']}/{payload['checks_total']} 项；逐侧检查全部为 `true`。",
            "",
            "## 解释范围",
            "",
            "这份对照验证保存中的国家块能够重建公共查询所报告的军队兵种总数和后备人力。它没有重新启动游戏、执行外交动作或重算场景文件SHA；查询报告中的原生事件和公共投影仍由各自报告负责。",
            "",
        ]
    )
    return "\n".join(lines)


def build_payload(scene_report_path: Path, report_paths: list[Path]) -> dict[str, Any]:
    scene = _load_small_json(scene_report_path)
    cases, report_meta = _collect_public_cases(report_paths)
    if not cases:
        raise ValueError("no public force cases found")
    country_union = sorted(
        {
            tag
            for case in cases
            for side in case.get("sides", {}).values()
            for tag in side.get("countries", [])
        }
    )
    destination = Path(str(scene.get("destination", ""))).expanduser()
    if not destination.is_file():
        raise FileNotFoundError(f"scene destination save is missing: {destination}")
    records, scan = _stream_country_records(destination.resolve(), set(country_union))
    case_sides = [
        _compare_side(case, side_name, side, records)
        for case in cases
        for side_name, side in case.get("sides", {}).items()
    ]
    query_report_meta = report_meta["reports"]
    sessions = {meta.get("session_id") for meta in query_report_meta}
    dates = {meta.get("session_date_raw") for meta in query_report_meta}
    report_statuses = {meta.get("status") for meta in query_report_meta}
    scene_summary = dict(scene)
    scene_summary["destination_exists"] = True
    scene_summary["destination_size_bytes"] = destination.stat().st_size
    checks: dict[str, bool] = {
        "scene_report_prepared": scene.get("status") == "prepared",
        "scene_destination_exists": True,
        "query_reports_passed": report_statuses == {"passed"},
        "query_case_count_18": len(cases) == 18,
        "query_cases_have_both_sides": all(len(case.get("sides", {})) == 2 for case in cases),
        "same_session_across_batches": len(sessions) == 1,
        "same_date_across_batches": len(dates) == 1,
        "countries_root_found_and_closed": bool(scan["countries_found"] and scan["countries_complete"]),
        "all_union_country_blocks_found": not scan["missing_tags"],
        "no_duplicate_union_country_blocks": not scan["duplicate_tags"],
        "all_case_sides_passed": all(item["passed"] for item in case_sides),
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "tool": {
            "name": "work/verify_r64_force_save_groups.py",
            "streaming": True,
            "whole_save_read_into_memory": False,
            "country_capture_limit_bytes": MAX_COUNTRY_CAPTURE_BYTES,
            "condensed_regiment_limit_bytes": MAX_CONDENSED_REGIMENT_BYTES,
            "hash_recomputed": False,
        },
        "scene": scene_summary,
        "query_reports": query_report_meta,
        "country_union": country_union,
        "save_scan": scan,
        "country_records": records,
        "case_count": len(cases),
        "case_side_count": len(case_sides),
        "case_sides": case_sides,
        "checks": checks,
        "checks_passed": sum(bool(value) for value in checks.values()),
        "checks_total": len(checks),
        "case_side_checks_passed": sum(
            bool(value) for item in case_sides for value in item["checks"].values()
        ),
        "case_side_checks_total": sum(len(item["checks"]) for item in case_sides),
        "assumptions": [
            "保存中的每个 regiment 块按一个单位记录；strength 缺失时只在有效和中按 1.000 计算，原始字段仍记录为缺失。",
            "unit_type 映射沿用既有R64基线：infantry/halberd为步兵，knight/chevauchee/cavalry为骑兵，artillery/cannon为炮兵；本场景的 mamluk_archer 按公共快照归入步兵。",
            "manpower 和 regiment strength 的 x1000 比较只适用于本次保存与公共查询的同日期对照。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-report", type=Path, default=DEFAULT_SCENE_REPORT)
    parser.add_argument("--batch-report", type=Path, action="append", dest="batch_reports")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    scene_report = args.scene_report.expanduser().resolve()
    report_paths = [path.expanduser().resolve() for path in (args.batch_reports or DEFAULT_BATCH_REPORTS)]
    output = args.output.expanduser().resolve()
    if output.exists():
        unexpected = {
            item.name for item in output.iterdir() if item.name not in {"report.json", "report.md"}
        }
        if unexpected:
            parser.error(f"output directory contains unexpected files: {sorted(unexpected)}")
    else:
        output.mkdir(parents=True, exist_ok=True)
    try:
        payload = build_payload(scene_report, report_paths)
    except (OSError, ValueError, bounded.SaveParseError) as exc:
        parser.error(str(exc))
    (output / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(_render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": payload["status"],
                "cases": payload["case_count"],
                "case_sides": payload["case_side_count"],
                "union_countries": len(payload["country_union"]),
                "checks": f"{payload['checks_passed']}/{payload['checks_total']}",
                "case_side_checks": f"{payload['case_side_checks_passed']}/{payload['case_side_checks_total']}",
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
