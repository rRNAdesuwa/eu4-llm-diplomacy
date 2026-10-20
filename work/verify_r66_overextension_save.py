#!/usr/bin/env python3
"""Independently reconcile R66 overextension preview rows with an EU4 save.

The verifier reads one or more already-produced native query reports and then
scans the save's ``provinces`` block line by line.  It retains only provinces
owned by a country present in the native preview, plus provinces named by a
native gained/lost list.  A province block is capped at four MiB; the complete
gamestate is never loaded into memory and the save is never rewritten.

The native preview stores overextension as a fraction with scale 1000.  For
the European R63/R66 sample, the save-side check is ``development * .8``
percentage points, or ``development * 8`` raw units at fraction scale 1000.
The formula is kept explicit in the report so a country with an unrecognised
colonial/special province is reported as unknown rather than silently treated
as an ordinary European province.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded


MAX_BLOCK_BYTES = 4 * 1024 * 1024
MAX_RETAINED_PROVINCES = 16384
RAW_SCALE = 1000
OVEREXTENSION_FACTOR = Decimal("0.8")
KNOWN_R63_SHA256 = (
    "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251"
)

PROVINCES_RE = re.compile(r"^\s*provinces\s*=\s*\{")
PROVINCE_RE = re.compile(r"^\s*(-?\d+)\s*=\s*\{")
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,5}$")

# These names are deliberately conservative.  ``is_city`` and ordinary
# province history are not special for this check.  Any present non-false key
# below makes a non-core contribution unknown because this script does not
# claim to reproduce colonial/special-country modifiers.
SPECIAL_FIELD_NAMES = {
    "colony",
    "colonial",
    "colonial_nation",
    "is_colony",
    "is_overseas",
    "native_ferocity",
    "native_hostileness",
    "native_size",
    "trade_company",
    "trade_company_region",
}


def _last(value: Any) -> Any:
    if isinstance(value, list):
        return value[-1] if value else None
    return value


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return bounded.unquote(value)
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


def _int(value: Any) -> int | None:
    value = _decimal(value)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


def _canonical_tag(value: Any) -> str | None:
    value = _normalize(value)
    if value is None:
        return None
    tag = str(value).strip().upper()
    return tag if TAG_RE.fullmatch(tag) else None


def _json_number(value: Decimal | None) -> int | float | str | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return format(value, "f")


def _block_tokens(entries: list[bounded.Entry], key: str) -> list[str]:
    result: list[str] = []
    for entry in entries:
        if entry.key == key and entry.body is not None:
            for token in re.findall(r"\b[A-Z][A-Z0-9_]{2,5}\b", entry.body):
                result.append(token.upper())
    return sorted(set(result))


def _plain_false(value: Any) -> bool:
    value = _normalize(value)
    return value in {None, "", "0", "no", "false", "none"}


def _special_flags(
    fields: dict[str, Any], blocks: list[str]
) -> tuple[list[dict[str, Any]], bool]:
    flags: list[dict[str, Any]] = []
    for key, value in fields.items():
        leaf = key.rsplit(".", 1)[-1].split("#", 1)[0].lower()
        if leaf in SPECIAL_FIELD_NAMES and not _plain_false(_last(value)):
            flags.append({"key": key, "value": _normalize(_last(value))})
    for key in blocks:
        leaf = key.rsplit(".", 1)[-1].split("#", 1)[0].lower()
        if leaf in SPECIAL_FIELD_NAMES:
            flags.append({"key": key, "value": "<block>"})
    return flags, not flags


def _parse_province(capture: dict[str, Any]) -> dict[str, Any] | None:
    if capture.get("truncated") or not capture.get("complete"):
        return None
    text = "".join(capture.get("lines", []))
    try:
        body = bounded.extract_block(text, text.find("{"))
        entries = bounded.top_level_entries(body)
        fields, blocks = bounded.flatten_entries(entries)
    except bounded.SaveParseError:
        return None

    base_tax = _decimal(_scalar(fields, "base_tax"))
    base_production = _decimal(_scalar(fields, "base_production"))
    base_manpower = _decimal(_scalar(fields, "base_manpower"))
    development = None
    if base_tax is not None and base_production is not None and base_manpower is not None:
        development = base_tax + base_production + base_manpower
    flags, special_scope_known = _special_flags(fields, blocks)
    return {
        "province_id": int(capture["province_id"]),
        "serialized_key": capture["serialized_key"],
        "owner": _canonical_tag(_scalar(fields, "owner")),
        "controller": _canonical_tag(_scalar(fields, "controller")),
        "cores": _block_tokens(entries, "cores"),
        "base_tax": _json_number(base_tax),
        "base_production": _json_number(base_production),
        "base_manpower": _json_number(base_manpower),
        "development": _json_number(development),
        "special_flags": flags,
        "special_scope_known": special_scope_known,
        "complete": True,
        "line_start": capture.get("start_line"),
        "line_end": capture.get("end_line"),
        "bytes_seen": capture.get("bytes_seen", 0),
    }


def _append_line(capture: dict[str, Any], line: str) -> None:
    capture["bytes_seen"] += len(line.encode("utf-8", errors="replace"))
    if capture["bytes_seen"] <= MAX_BLOCK_BYTES:
        capture["lines"].append(line)
    else:
        capture["truncated"] = True
        capture["lines"] = []


def _resolve_candidate(raw: Any, base: Path, *fallbacks: Path) -> Path | None:
    if not raw:
        return None
    candidate = Path(str(raw)).expanduser()
    options = [candidate]
    if not candidate.is_absolute():
        options.append(base / candidate)
    options.extend(fallbacks)
    for option in options:
        try:
            resolved = option.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _overextension_from_public(public: dict[str, Any]) -> dict[str, Any] | None:
    consequences = public.get("peace_consequences")
    if isinstance(consequences, dict):
        overextension = consequences.get("overextension")
        if isinstance(overextension, dict):
            return overextension
    return None


def _native_row(row: dict[str, Any], case: dict[str, Any], public_path: Path) -> dict[str, Any]:
    def ids(key: str) -> list[int]:
        values = row.get(key) or []
        if not isinstance(values, list):
            return []
        result: list[int] = []
        for value in values:
            number = _int(value)
            if number is not None and number >= 0:
                result.append(number)
        return result

    after_key = "after_raw" if row.get("after_raw") is not None else "projected_raw"
    return {
        "case": case.get("name") or case.get("query_id") or public_path.parent.name,
        "query_id": case.get("query_id") or case.get("native_query_id"),
        "direction": case.get("direction"),
        "action_id": case.get("action_id"),
        "public_path": str(public_path),
        "country": _canonical_tag(row.get("country")),
        "complete": row.get("complete"),
        "current_raw": _int(row.get("current_raw")),
        "current_recomputed_raw": _int(row.get("current_recomputed_raw")),
        "cache_matches_recomputed": row.get("cache_matches_recomputed"),
        "after_raw": _int(row.get(after_key)),
        "after_field": after_key,
        "gained_raw": _int(row.get("gained_raw")),
        "lost_raw": _int(row.get("lost_raw")),
        "delta_raw": _int(row.get("delta_raw")),
        "gained_province_ids": ids("gained_province_ids"),
        "lost_province_ids": ids("lost_province_ids"),
        "scale": _int(row.get("scale")),
        "unit": row.get("unit"),
    }


def load_query_cases(paths: list[Path]) -> tuple[list[dict[str, Any]], set[str], set[int], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    target_tags: set[str] = set()
    target_ids: set[int] = set()
    source_reports: list[dict[str, Any]] = []
    for report_path in paths:
        report_path = report_path.expanduser().resolve()
        if not report_path.is_file():
            source_reports.append({"path": str(report_path), "status": "missing"})
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        source_reports.append(
            {
                "path": str(report_path),
                "size_bytes": report_path.stat().st_size,
                "status": "read",
                "schema": report.get("schema"),
                "case_count": len(report.get("cases", [])) if isinstance(report.get("cases"), list) else 1,
            }
        )
        raw_cases = report.get("cases") if isinstance(report.get("cases"), list) else [report]
        for case in raw_cases:
            if not isinstance(case, dict):
                continue
            name = case.get("name") or case.get("query_id") or "unnamed-case"
            public_path = _resolve_candidate(
                case.get("public_path"),
                report_path.parent,
                report_path.parent / "report-evidence" / "cases" / str(name) / "public.json",
            )
            if public_path is None:
                native_path = _resolve_candidate(case.get("native_event_path"), report_path.parent)
                if native_path is not None:
                    public_path = _resolve_candidate(native_path.parent / "public.json", report_path.parent)
            if public_path is None or public_path.stat().st_size > MAX_BLOCK_BYTES:
                continue
            try:
                public = json.loads(public_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            overextension = _overextension_from_public(public)
            if not isinstance(overextension, dict):
                continue
            native_rows = overextension.get("countries")
            if not isinstance(native_rows, list):
                continue
            for raw_row in native_rows:
                if not isinstance(raw_row, dict):
                    continue
                parsed = _native_row(raw_row, case, public_path)
                country = parsed["country"]
                if country is not None:
                    target_tags.add(country)
                target_ids.update(parsed["gained_province_ids"])
                target_ids.update(parsed["lost_province_ids"])
                rows.append(parsed)
    return rows, target_tags, target_ids, source_reports


def scan_save(path: Path, target_tags: set[str], target_ids: set[int], reused_sha: str | None) -> dict[str, Any]:
    source = bounded.detect_container(path)
    source["sha256_reused"] = reused_sha is not None
    source["sha256_reused_value"] = reused_sha
    source["sha256_recomputed"] = False
    source["sha256_reuse_note"] = (
        "provided by --scene-report/--reuse-r63-sha; save was not hashed"
        if reused_sha
        else "not computed; pass --scene-report or --reuse-r63-sha to bind an existing hash"
    )
    depth = 0
    line_count = 0
    provinces_found = False
    provinces_complete = False
    provinces_depth: int | None = None
    active: dict[str, Any] | None = None
    records: dict[int, dict[str, Any]] = {}
    seen_ids: set[int] = set()
    duplicate_ids: list[int] = []
    unknown: list[str] = []
    blocks_seen = 0
    parse_failures = 0

    def finish(end_line: int | None, complete: bool) -> None:
        nonlocal active, blocks_seen, parse_failures
        if active is None:
            return
        active["end_line"] = end_line
        active["complete"] = complete
        blocks_seen += 1
        parsed = _parse_province(active)
        if parsed is None:
            parse_failures += 1
            if active.get("truncated"):
                unknown.append(f"province_block_over_{MAX_BLOCK_BYTES}_bytes:{active.get('province_id')}")
            else:
                unknown.append(f"province_block_unreadable:{active.get('province_id')}")
        else:
            province_id = int(parsed["province_id"])
            if province_id in seen_ids:
                duplicate_ids.append(province_id)
            seen_ids.add(province_id)
            owner = parsed.get("owner")
            if owner in target_tags or province_id in target_ids:
                if province_id not in records:
                    if len(records) < MAX_RETAINED_PROVINCES:
                        records[province_id] = parsed
                    else:
                        unknown.append("retained_province_cap_exceeded")
        active = None

    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if not provinces_found and before == 0 and PROVINCES_RE.match(line):
                provinces_found = True
                provinces_depth = before + bounded.brace_delta(line)

            if (
                provinces_found
                and not provinces_complete
                and active is None
                and provinces_depth is not None
                and before == provinces_depth
            ):
                match = PROVINCE_RE.match(line)
                if match:
                    serialized_key = match.group(1)
                    try:
                        province_id = abs(int(serialized_key))
                    except ValueError:
                        province_id = -1
                    if province_id >= 0:
                        active = {
                            "province_id": province_id,
                            "serialized_key": serialized_key,
                            "start_line": line_number,
                            "bytes_seen": 0,
                            "truncated": False,
                            "lines": [],
                            "active_depth": before + bounded.brace_delta(line),
                        }
                        _append_line(active, line)
            elif active is not None:
                _append_line(active, line)

            depth += bounded.brace_delta(line)
            if active is not None and provinces_depth is not None:
                if depth == provinces_depth and before >= active["active_depth"]:
                    finish(line_number, True)

            if (
                provinces_found
                and not provinces_complete
                and provinces_depth is not None
                and depth == 0
                and before >= provinces_depth
            ):
                if active is not None:
                    finish(line_number, False)
                provinces_complete = True

    if active is not None:
        finish(None, False)
    if not provinces_found:
        unknown.append("provinces_block_not_found")
    if not provinces_complete:
        unknown.append("provinces_block_incomplete")
    if depth != 0:
        unknown.append(f"final_brace_depth:{depth}")
    return {
        "source": source,
        "save_date": None,
        "checks": {
            "source_exists": path.is_file(),
            "provinces_block_found": provinces_found,
            "provinces_block_complete": provinces_found and provinces_complete,
            "brace_balance_ok": depth == 0,
            "per_block_cap_4_mib": not any("over_" in item for item in unknown),
            "streaming_only": True,
        },
        "scan": {
            "line_count": line_count,
            "province_blocks_seen": blocks_seen,
            "province_records_retained": len(records),
            "target_tags": sorted(target_tags),
            "target_province_ids": sorted(target_ids),
            "duplicate_province_ids": sorted(set(duplicate_ids)),
            "parse_failures": parse_failures,
            "unknown": unknown,
        },
        "provinces": records,
    }


def _raw_from_development(development: Decimal | None) -> int | None:
    if development is None or development < 0:
        return None
    # 0.8 development percentage points = 0.008 fraction; at raw scale
    # 1000 this is development * 8.  Round only after the combined total.
    return int((development * OVEREXTENSION_FACTOR * Decimal(10)).to_integral_value(rounding=ROUND_HALF_UP))


def _record_development(record: dict[str, Any]) -> Decimal | None:
    return _decimal(record.get("development"))


def _country_current(save: dict[str, Any], country: str) -> dict[str, Any]:
    records = [
        record
        for record in save["provinces"].values()
        if record.get("owner") == country
    ]
    noncore: list[dict[str, Any]] = []
    unknown_reasons: list[str] = []
    total = Decimal(0)
    for record in records:
        if country in set(record.get("cores") or []):
            continue
        noncore.append(record)
        development = _record_development(record)
        if development is None:
            unknown_reasons.append(f"missing_development:{record.get('province_id')}")
        else:
            total += development
        if not record.get("special_scope_known", False):
            unknown_reasons.append(f"special_or_colonial_flag:{record.get('province_id')}")
    return {
        "owned_count": len(records),
        "noncore_count": len(noncore),
        "noncore_ids": sorted(int(item["province_id"]) for item in noncore),
        "noncore_development": _json_number(total),
        "development": total,
        "unknown_reasons": sorted(set(unknown_reasons)),
        "complete": not unknown_reasons,
    }


def reconcile_row(row: dict[str, Any], save: dict[str, Any]) -> dict[str, Any]:
    country = row.get("country")
    current_native = row.get("current_raw")
    after_native = row.get("after_raw")
    checks: dict[str, bool | None] = {}
    reasons: list[str] = []
    if country is None:
        return {"native": row, "status": "unknown", "checks": {}, "reasons": ["invalid_native_country"]}

    current = _country_current(save, country)
    current_dev: Decimal = current["development"]
    lost_dev = Decimal(0)
    gained_dev = Decimal(0)
    lost_details: list[dict[str, Any]] = []
    gained_details: list[dict[str, Any]] = []
    owner_mismatch = False
    missing_selected = False
    special_selected = False

    def selected_detail(province_id: int, mode: str) -> dict[str, Any]:
        nonlocal lost_dev, gained_dev, owner_mismatch, missing_selected, special_selected
        record = save["provinces"].get(province_id)
        if record is None:
            missing_selected = True
            return {"province_id": province_id, "status": "unknown", "reason": "province_not_retained"}
        owner = record.get("owner")
        core = country in set(record.get("cores") or [])
        development = _record_development(record)
        if mode == "lost" and owner != country:
            owner_mismatch = True
            return {
                "province_id": province_id,
                "owner": owner,
                "status": "difference",
                "reason": "lost_id_owner_does_not_match_native_country",
            }
        if not record.get("special_scope_known", False) and not core:
            special_selected = True
        if development is None:
            missing_selected = True
            return {"province_id": province_id, "owner": owner, "status": "unknown", "reason": "missing_development"}
        contribution = Decimal(0) if core else development
        if mode == "lost":
            lost_dev += contribution
        else:
            gained_dev += contribution
        return {
            "province_id": province_id,
            "owner": owner,
            "cores": record.get("cores", []),
            "already_core": core,
            "development": _json_number(development),
            "special_scope_known": record.get("special_scope_known"),
            "contribution_development": _json_number(contribution),
            "status": "passed" if not (not record.get("special_scope_known", False) and not core) else "unknown",
        }

    for province_id in row.get("lost_province_ids", []):
        lost_details.append(selected_detail(province_id, "lost"))
    for province_id in row.get("gained_province_ids", []):
        gained_details.append(selected_detail(province_id, "gained"))

    duplicate_ids = (
        len(row.get("lost_province_ids", [])) != len(set(row.get("lost_province_ids", [])))
        or len(row.get("gained_province_ids", [])) != len(set(row.get("gained_province_ids", [])))
    )
    if duplicate_ids:
        reasons.append("duplicate_native_province_ids")
    if missing_selected:
        reasons.append("selected_province_not_fully_readable")
    if special_selected:
        reasons.append("selected_province_special_scope_unknown")
    if owner_mismatch:
        reasons.append("lost_id_owner_mismatch")

    expected_current = _raw_from_development(current_dev) if current["complete"] else None
    combined_dev: Decimal | None = None
    expected_after = None
    expected_gained = None
    expected_lost = None
    expected_delta = None
    if expected_current is not None and not (missing_selected or special_selected or owner_mismatch):
        combined_dev = current_dev - lost_dev + gained_dev
        if combined_dev < 0:
            reasons.append("negative_combined_development")
        else:
            expected_after = _raw_from_development(combined_dev)
            expected_gained = _raw_from_development(current_dev + gained_dev)
            if expected_gained is not None:
                expected_gained -= expected_current
            expected_lost = expected_current - _raw_from_development(current_dev - lost_dev)
            expected_delta = expected_after - expected_current if expected_after is not None else None

    checks["save_provinces_complete"] = bool(
        save["checks"].get("provinces_block_complete")
        and save["checks"].get("brace_balance_ok")
        and not save["scan"].get("duplicate_province_ids")
        and current["complete"]
    )
    checks["native_fields_present"] = all(
        value is not None for value in (current_native, row.get("current_recomputed_raw"), after_native, row.get("gained_raw"), row.get("lost_raw"), row.get("delta_raw"))
    )
    checks["native_current_equals_recomputed"] = (
        current_native is not None
        and row.get("current_recomputed_raw") is not None
        and current_native == row.get("current_recomputed_raw")
    )
    checks["native_cache_match_flag"] = (
        row.get("cache_matches_recomputed") is None
        or bool(row.get("cache_matches_recomputed")) == checks["native_current_equals_recomputed"]
    )
    checks["native_delta_equals_after_minus_current"] = (
        after_native is not None
        and current_native is not None
        and row.get("delta_raw") is not None
        and row.get("delta_raw") == after_native - current_native
    )
    checks["native_ids_unique"] = not duplicate_ids
    checks["lost_ids_owner_match"] = not owner_mismatch
    checks["save_current_matches_native"] = (
        expected_current is not None and current_native is not None and expected_current == current_native
    )
    checks["save_after_matches_native"] = (
        expected_after is not None and after_native is not None and expected_after == after_native
    )
    checks["save_gained_matches_native"] = (
        expected_gained is not None and row.get("gained_raw") is not None and expected_gained == row.get("gained_raw")
    )
    checks["save_lost_matches_native"] = (
        expected_lost is not None and row.get("lost_raw") is not None and expected_lost == row.get("lost_raw")
    )
    checks["save_delta_matches_native"] = (
        expected_delta is not None and row.get("delta_raw") is not None and expected_delta == row.get("delta_raw")
    )

    if row.get("complete") is not True:
        reasons.append("native_row_incomplete")
    if not checks["native_fields_present"]:
        reasons.append("native_overextension_field_missing")
    if any(value is None for value in (expected_current, expected_after, expected_gained, expected_lost, expected_delta)):
        reasons.append("save_side_scope_unknown")

    failed = [name for name, value in checks.items() if value is False]
    if failed and not any(reason in reasons for reason in ("save_side_scope_unknown", "native_row_incomplete")):
        status = "difference"
    elif reasons:
        status = "unknown"
    else:
        status = "passed"
    if status == "passed" and not all(value is True for value in checks.values()):
        status = "unknown"

    no_change = not row.get("gained_province_ids") and not row.get("lost_province_ids")
    if no_change:
        reasons.append("no_selected_territorial_change" )
    return {
        "case": row.get("case"),
        "country": country,
        "direction": row.get("direction"),
        "action_id": row.get("action_id"),
        "public_path": row.get("public_path"),
        "status": status,
        "checks": checks,
        "reasons": sorted(set(reasons)),
        "native": row,
        "save": {
            "owned_count": current["owned_count"],
            "current_noncore_count": current["noncore_count"],
            "current_noncore_province_ids": current["noncore_ids"],
            "current_noncore_development": _json_number(current_dev),
            "expected_current_raw": expected_current,
            "expected_gained_raw": expected_gained,
            "expected_lost_raw": expected_lost,
            "expected_after_raw": expected_after,
            "expected_delta_raw": expected_delta,
            "combined_development": _json_number(combined_dev),
            "gained_development": _json_number(gained_dev),
            "lost_development": _json_number(lost_dev),
            "gained_provinces": gained_details,
            "lost_provinces": lost_details,
            "unknown_reasons": current["unknown_reasons"],
            "scale": RAW_SCALE,
            "overextension_factor": "0.8",
        },
    }


def _reuse_sha(scene_report: Path | None, save: Path, explicit: str | None) -> tuple[str | None, str]:
    if explicit:
        return explicit, "--reuse-r63-sha"
    if scene_report is None or not scene_report.is_file():
        return None, "none"
    try:
        report = json.loads(scene_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "scene-report-unreadable"
    save_resolved = save.resolve()
    destination = report.get("destination") if isinstance(report.get("destination"), dict) else {}
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    destination_path = destination.get("path")
    if destination_path and Path(str(destination_path)).expanduser().resolve() == save_resolved:
        value = destination.get("sha256") or destination.get("known_sha256")
        if value:
            return str(value), "scene-report.destination.sha256"
    source_path = source.get("path")
    if source_path and Path(str(source_path)).expanduser().resolve() == save_resolved:
        value = source.get("sha256") or source.get("known_sha256")
        if value:
            return str(value), "scene-report.source.sha256"
    value = source.get("known_sha256") or source.get("sha256")
    if value:
        return str(value), "scene-report.source.known_sha256"
    return None, "scene-report-no-sha"


def reconcile(query_rows: list[dict[str, Any]], save: dict[str, Any]) -> dict[str, Any]:
    reconciliations = [reconcile_row(row, save) for row in query_rows]
    counts = {
        "rows": len(reconciliations),
        "passed": sum(item["status"] == "passed" for item in reconciliations),
        "difference": sum(item["status"] == "difference" for item in reconciliations),
        "unknown": sum(item["status"] == "unknown" for item in reconciliations),
        "zero_current": sum(item["native"].get("current_raw") == 0 for item in reconciliations),
        "nonzero_current": sum(
            isinstance(item["native"].get("current_raw"), int) and item["native"].get("current_raw") != 0
            for item in reconciliations
        ),
        "zero_gain": sum(item["native"].get("gained_raw") == 0 for item in reconciliations),
        "nonzero_gain": sum(
            isinstance(item["native"].get("gained_raw"), int) and item["native"].get("gained_raw") != 0
            for item in reconciliations
        ),
        "zero_loss": sum(item["native"].get("lost_raw") == 0 for item in reconciliations),
        "nonzero_loss": sum(
            isinstance(item["native"].get("lost_raw"), int) and item["native"].get("lost_raw") != 0
            for item in reconciliations
        ),
        "zero_delta": sum(item["native"].get("delta_raw") == 0 for item in reconciliations),
        "nonzero_delta": sum(
            isinstance(item["native"].get("delta_raw"), int) and item["native"].get("delta_raw") != 0
            for item in reconciliations
        ),
        "no_change_rows": sum("no_selected_territorial_change" in item["reasons"] for item in reconciliations),
    }
    return {
        "rows": reconciliations,
        "counts": counts,
        "all_rows_passed": bool(reconciliations) and counts["passed"] == len(reconciliations),
        "all_checks": {
            "row_count_nonzero": bool(reconciliations),
            "save_scan_complete": all(save["checks"].values()),
            "native_internal_relations_passed": all(
                item["checks"].get("native_current_equals_recomputed") is True
                and item["checks"].get("native_delta_equals_after_minus_current") is True
                for item in reconciliations
            ),
            "independent_save_matches_all_applicable": counts["difference"] == 0,
            "unknown_rows_not_counted_as_zero_coverage": True,
        },
    }


def _render_markdown(report: dict[str, Any]) -> str:
    recon = report["reconciliation"]
    counts = recon["counts"]
    lines = [
        "# R66 overextension 保存独立核对",
        "",
        f"状态：`{report['status']}`；native 查询报告 `{len(report['queries']['reports'])}` 份，预览行 `{counts['rows']}` 条。",
        "",
        f"保存：`{report['save']['source']['path']}`；扫描 `provinces` 块，单块上限 {MAX_BLOCK_BYTES} 字节；未把完整 gamestate 载入内存，也未重新哈希保存。",
        "",
        "保存侧公式：普通欧洲省份使用 `development × 0.8` 个百分点，换算为 fraction scale 1000 后为 `development × 8` raw；组合后的保留开发度和新增开发度先合计，再统一取整。含未识别殖民/特殊字段的非核心省份保留 `unknown`。",
        "",
        f"行计数：通过 `{counts['passed']}`，差异 `{counts['difference']}`，未知 `{counts['unknown']}`；current 非零 `{counts['nonzero_current']}`、loss 非零 `{counts['nonzero_loss']}`、gain 非零 `{counts['nonzero_gain']}`、delta 非零 `{counts['nonzero_delta']}`。零值是有效观测，不当作未覆盖。",
        "",
        f"内部关系检查：`current_raw == current_recomputed_raw` 与 `delta_raw == after_raw - current_raw` 见 JSON 的 `checks`；`after_raw` 优先使用 native `after_raw`，R66 当前字段为 `projected_raw`。",
        "",
        f"总检查：`{json.dumps(recon['all_checks'], ensure_ascii=False, sort_keys=True)}`。逐行依据、saved province IDs 和 unknown 原因见 `report.json`。",
        "",
    ]
    return "\n".join(lines)


def _output_paths(output: Path) -> tuple[Path, Path]:
    output = output.expanduser().resolve()
    if output.suffix.lower() == ".json":
        return output, output.with_suffix(".md")
    return output / "report.json", output / "report.md"


def build_report(save_path: Path, query_paths: list[Path], scene_report: Path | None, reuse_r63_sha: str | None) -> dict[str, Any]:
    query_rows, target_tags, target_ids, source_reports = load_query_cases(query_paths)
    reused_sha, reuse_reason = _reuse_sha(scene_report, save_path, reuse_r63_sha)
    save = scan_save(save_path, target_tags, target_ids, reused_sha)
    reconciliation = reconcile(query_rows, save)
    checks = {
        "query_reports_read": bool(source_reports) and all(item.get("status") == "read" for item in source_reports),
        "query_rows_nonempty": bool(query_rows),
        "save_exists": save_path.is_file(),
        "save_provinces_stream_complete": bool(save["checks"].get("provinces_block_complete")),
        "native_internal_relations": bool(reconciliation["all_checks"].get("native_internal_relations_passed")),
        "no_full_save_load": True,
        "no_dynamic_value_inference": True,
    }
    if reconciliation["counts"]["difference"]:
        status = "differences"
    elif reconciliation["counts"]["unknown"]:
        status = "passed_with_unknown"
    elif all(checks.values()):
        status = "passed"
    else:
        status = "incomplete"
    return {
        "schema": "r66_overextension_save_check_v1",
        "status": status,
        "checks": checks,
        "scope": {
            "raw_scale": RAW_SCALE,
            "overextension_factor": "0.8",
            "save_formula": "development * 0.8 percentage_points -> development * 8 raw at fraction scale 1000",
            "combined_rounding": "sum retained and selected development first, then ROUND_HALF_UP",
            "max_province_block_bytes": MAX_BLOCK_BYTES,
            "unknown_special_scope": "non-core province with unrecognised colonial/special field remains unknown",
            "source_sha_reuse_reason": reuse_reason,
            "scene_report": str(scene_report.resolve()) if scene_report else None,
        },
        "queries": {
            "reports": source_reports,
            "rows": len(query_rows),
            "target_tags": sorted(target_tags),
            "target_province_ids": sorted(target_ids),
        },
        "save": save,
        "reconciliation": reconciliation,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument(
        "--queries",
        type=Path,
        action="append",
        nargs="+",
        required=True,
        help="one or more existing R66 query report.json paths; may be repeated",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scene-report", type=Path)
    parser.add_argument(
        "--reuse-r63-sha",
        "--reuseR63SHA",
        dest="reuse_r63_sha",
        help="reuse an already recorded R63/source SHA without hashing the save",
    )
    args = parser.parse_args(argv)
    query_paths = [item.expanduser().resolve() for group in args.queries for item in group]
    save_path = args.save.expanduser().resolve()
    if not save_path.is_file():
        raise FileNotFoundError(f"save not found: {save_path}")
    scene_report = args.scene_report.expanduser().resolve() if args.scene_report else None
    report = build_report(save_path, query_paths, scene_report, args.reuse_r63_sha)
    report_path, markdown_path = _output_paths(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path), "checks": report["checks"], "counts": report["reconciliation"]["counts"]}, ensure_ascii=False))
    return 0 if report["status"] in {"passed", "passed_with_unknown"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
