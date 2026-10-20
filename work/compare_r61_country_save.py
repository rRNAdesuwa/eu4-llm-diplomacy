#!/usr/bin/env python3
"""流式核对 R61 五类国家级议和效果的 before/after 存档字段。

输入 --expectations 是 JSON 列表，例如::

    [
      {"action_id": "release_nation", "country": "TYR", "source": "ENG"},
      {"action_id": "full_annexation", "country": "TYR", "beneficiary": "FRA"},
      {"action_id": "force_vassalization", "country": "TYR", "beneficiary": "FRA"},
      {"action_id": "form_personal_union", "country": "TYR", "beneficiary": "FRA"},
      {"action_id": "grant_independence", "country": "TYR", "source": "ENG"}
    ]

工具只保留目标国家相关的省份 owner/controller 行和 diplomacy 直接关系块。
它不会把 42MB gamestate 读入内存，也不把 treasury 变化归因于议和。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work import inspect_peace_subject_save as subject_parser


TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,5}$")
PROVINCES_RE = re.compile(r"^\s*provinces\s*=\s*\{")
# Province entries are blocks.  Requiring the opening brace prevents a
# scalar at the direct ``provinces`` level from being treated as a province
# and keeps the bounded capture aligned with the serialized block.
PROVINCE_RE = re.compile(r"^\s*(-?\d+)\s*=\s*\{")
DIRECT_FIELD_RE = re.compile(r"^\s*(owner|controller)\s*=\s*(.*?)\s*$")
MAX_PROVINCE_BLOCK_BYTES = 256 * 1024
MAX_TARGET_PROVINCES = 4096
ACTION_IDS = {
    "release_nation",
    "force_vassalization",
    "form_personal_union",
    "grant_independence",
    "full_annexation",
}
SUBJECT_EXPECTED_TYPE = {
    "force_vassalization": "vassal",
    "form_personal_union": "personal_union",
}


def _tag(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a country tag")
    value = value.strip().upper()
    if not TAG_RE.fullmatch(value):
        raise ValueError(f"{field} is not a country tag: {value!r}")
    return value


def _resolve_save(value: Path, label: str) -> Path:
    path = value.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} is not a file: {path}")
    return path


def _source_metadata(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "container": source.get("container"),
        "gamestate_member": source.get("gamestate_member"),
        "sha256_recomputed": False,
    }


def _parse_expectations(raw: str) -> list[dict[str, Any]]:
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        if candidate.stat().st_size > 1024 * 1024:
            raise ValueError("expectations file exceeds 1 MiB")
        value = json.loads(candidate.read_text(encoding="utf-8"))
    else:
        value = json.loads(raw)
    if not isinstance(value, list) or not value:
        raise ValueError("--expectations must be a non-empty JSON list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"expectation {index} is not an object")
        action_id = item.get("action_id")
        if action_id not in ACTION_IDS:
            raise ValueError(f"expectation {index} has unsupported action_id")
        normalized: dict[str, Any] = {
            "action_id": action_id,
            "country": _tag(item.get("country"), f"expectations[{index}].country"),
        }
        for key in ("source", "beneficiary", "overlord"):
            if item.get(key) is not None:
                normalized[key] = _tag(
                    item[key], f"expectations[{index}].{key}"
                )
        if action_id == "release_nation" and "source" not in normalized:
            raise ValueError(f"expectation {index} release_nation needs source")
        if action_id in {
            "force_vassalization",
            "form_personal_union",
            "full_annexation",
        } and "beneficiary" not in normalized:
            raise ValueError(f"expectation {index} needs beneficiary")
        if action_id == "grant_independence" and "source" not in normalized:
            if "overlord" in normalized:
                normalized["source"] = normalized["overlord"]
            elif "beneficiary" in normalized:
                normalized["source"] = normalized["beneficiary"]
        state = item.get("expected_state", "accepted")
        if state not in {"accepted", "rejected", "observed"}:
            raise ValueError(f"expectation {index} has invalid expected_state")
        normalized["expected_state"] = state
        result.append(normalized)
    return result


def _finish_province(
    active: dict[str, Any] | None,
    rows_by_owner: dict[str, list[dict[str, Any]]],
    owner_counts: dict[str, int],
    target_tags: set[str],
    unknown: list[str],
    seen_ids: set[int],
) -> None:
    if active is None:
        return
    if active["truncated"]:
        unknown.append(f"line_{active['start_line']}:province_block_over_limit")
        return
    owner = active.get("owner")
    if owner not in target_tags:
        return
    province_id = int(active["province_id"])
    owner_counts[owner] = owner_counts.get(owner, 0) + 1
    if province_id in seen_ids:
        unknown.append(f"duplicate_target_province:{province_id}")
    seen_ids.add(province_id)
    rows = rows_by_owner.setdefault(owner, [])
    if len(rows) >= MAX_TARGET_PROVINCES:
        unknown.append(f"{owner}:target_province_limit:{MAX_TARGET_PROVINCES}")
        return
    row = {
        "province_id": province_id,
        "serialized_key": active["serialized_key"],
        "owner": owner,
        "controller": active.get("controller"),
        "owner_line": active.get("owner_line"),
        "controller_line": active.get("controller_line"),
        "line_start": active["start_line"],
        "line_end": active.get("end_line"),
        "bytes_seen": active["bytes_seen"],
        "complete": bool(owner and active.get("controller")),
        "unknown": [],
    }
    if not row["complete"]:
        row["unknown"].append("owner_or_controller_missing")
    rows.append(row)


def scan_owned_provinces(path: Path, target_tags: set[str]) -> dict[str, Any]:
    """Stream the province table and retain rows owned by target tags."""

    source = bounded.detect_container(path)
    depth = 0
    line_count = 0
    provinces_found = False
    provinces_complete = False
    provinces_depth: int | None = None
    active: dict[str, Any] | None = None
    unknown: list[str] = []
    rows_by_owner: dict[str, list[dict[str, Any]]] = {
        tag: [] for tag in sorted(target_tags)
    }
    owner_counts: dict[str, int] = {tag: 0 for tag in sorted(target_tags)}
    seen_ids: set[int] = set()

    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth

            if active is not None and line_number != active["start_line"]:
                active["bytes_seen"] += len(
                    line.encode("utf-8", errors="replace")
                )
                if active["bytes_seen"] > MAX_PROVINCE_BLOCK_BYTES:
                    active["truncated"] = True
                elif before == active["block_depth"]:
                    field = DIRECT_FIELD_RE.match(line)
                    if field:
                        key = field.group(1)
                        value = bounded.unquote(field.group(2).strip())
                        active[key] = value
                        active[f"{key}_line"] = line_number

            if not provinces_found and before == 0 and PROVINCES_RE.match(line):
                provinces_found = True
                provinces_depth = before + bounded.brace_delta(line)

            if (
                active is None
                and not provinces_complete
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
                    if province_id:
                        active = {
                            "province_id": province_id,
                            "serialized_key": serialized_key,
                            "start_line": line_number,
                            "end_line": None,
                            "block_depth": before + bounded.brace_delta(line),
                            "bytes_seen": len(
                                line.encode("utf-8", errors="replace")
                            ),
                            "truncated": False,
                            "owner": None,
                            "controller": None,
                        }

            depth += bounded.brace_delta(line)
            if (
                active is not None
                and provinces_depth is not None
                and depth == provinces_depth
                and before >= active["block_depth"]
            ):
                active["end_line"] = line_number
                _finish_province(
                    active,
                    rows_by_owner,
                    owner_counts,
                    target_tags,
                    unknown,
                    seen_ids,
                )
                active = None

            if (
                provinces_found
                and provinces_depth is not None
                and depth == 0
                and before >= provinces_depth
            ):
                provinces_complete = True

    if active is not None:
        unknown.append(f"line_{active['start_line']}:province_incomplete")
        _finish_province(
            active,
            rows_by_owner,
            owner_counts,
            target_tags,
            unknown,
            seen_ids,
        )
    if not provinces_found:
        unknown.append("provinces_block_not_found")
    elif not provinces_complete:
        unknown.append("provinces_block_incomplete")
    if depth != 0:
        unknown.append(f"final_brace_depth:{depth}")
    return {
        "source": _source_metadata(path, source),
        "scan": {
            "line_count": line_count,
            "provinces_block_found": provinces_found,
            "provinces_block_complete": provinces_complete,
            "final_brace_depth": depth,
            "brace_balance_ok": depth == 0,
            "unknown": unknown,
        },
        "owner_counts": owner_counts,
        "rows_by_owner": rows_by_owner,
    }


def scan_subject_relations(path: Path, target_tags: set[str]) -> dict[str, Any]:
    parsed = subject_parser.scan_save(path, target_tags)
    return {
        "source": parsed["source"],
        "scan": parsed["scan"],
        "block_type_counts": parsed["block_type_counts"],
        "records": parsed["records"],
    }


def _row_index(scan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for rows in scan.get("rows_by_owner", {}).values():
        for row in rows:
            result[int(row["province_id"])] = row
    return result


def _owned_rows(scan: dict[str, Any], country: str | None) -> list[dict[str, Any]]:
    if not country:
        return []
    return list(scan.get("rows_by_owner", {}).get(country, []))


def _province_pair_rows(
    before: dict[str, Any], after: dict[str, Any]
) -> list[dict[str, Any]]:
    old = _row_index(before)
    new = _row_index(after)
    return [
        {
            "province_id": province_id,
            "before": old.get(province_id),
            "after": new.get(province_id),
        }
        for province_id in sorted(set(old) | set(new))
    ]


def _relation_pair(
    relation_scan: dict[str, Any], country: str, overlord: str | None
) -> dict[str, Any]:
    records = [
        record
        for record in relation_scan["records"]
        if overlord
        and record.get("first") == overlord
        and record.get("second") == country
    ]
    return {
        "serialization_direction": "first=overlord,second=subject",
        "country": country,
        "overlord": overlord,
        "count": len(records),
        "present": bool(records),
        "subject_types": sorted(
            {
                str(record.get("subject_type"))
                for record in records
                if record.get("subject_type") is not None
            }
        ),
        "records": records,
    }


def _all_overlord_records(
    relation_scan: dict[str, Any], country: str
) -> list[dict[str, Any]]:
    return [
        record
        for record in relation_scan["records"]
        if record.get("second") == country
        and record.get("first") not in {None, country}
    ]


def _base_effect(
    expectation: dict[str, Any],
    before_provinces: dict[str, Any],
    after_provinces: dict[str, Any],
    before_relations: dict[str, Any],
    after_relations: dict[str, Any],
) -> dict[str, Any]:
    action = expectation["action_id"]
    country = expectation["country"]
    source = expectation.get("source")
    beneficiary = expectation.get("beneficiary")
    if action == "grant_independence" and source is None:
        source = expectation.get("overlord")
    pairs = _province_pair_rows(before_provinces, after_provinces)
    result: dict[str, Any] = {
        "action_id": action,
        "roles": {
            "country": country,
            "source": source,
            "beneficiary": beneficiary,
        },
        "expected_state": expectation["expected_state"],
        "province_rows": pairs,
        "checks": {},
    }
    checks = result["checks"]

    if action == "release_nation":
        before_rows = _owned_rows(before_provinces, country)
        after_rows = _owned_rows(after_provinces, country)
        before_source = _owned_rows(before_provinces, source)
        after_source = _owned_rows(after_provinces, source)
        moved = [
            row
            for row in pairs
            if isinstance(row.get("before"), dict)
            and isinstance(row.get("after"), dict)
            and row["before"].get("owner") == source
            and row["after"].get("owner") == country
        ]
        complete_moved = all(
            row["before"].get("complete") and row["after"].get("complete")
            for row in moved
        )
        result["before"] = {
            "country_owned_count": len(before_rows),
            "source_owned_count": len(before_source),
            "country_rows": before_rows,
        }
        result["after"] = {
            "country_owned_count": len(after_rows),
            "source_owned_count": len(after_source),
            "country_rows": after_rows,
        }
        result["moved_rows"] = moved
        checks.update(
            {
                "source_to_country_row_present": bool(moved),
                "moved_rows_owner_controller_complete": complete_moved,
                "country_owned_count_increased": len(after_rows) > len(before_rows),
                "source_owned_count_decreased": len(after_source)
                < len(before_source),
            }
        )
    elif action == "full_annexation":
        before_rows = _owned_rows(before_provinces, country)
        after_rows = _owned_rows(after_provinces, country)
        beneficiary_rows = _owned_rows(after_provinces, beneficiary)
        after_by_id = _row_index(after_provinces)
        moved = [
            {
                "province_id": row["province_id"],
                "before": row,
                "after": after_by_id.get(row["province_id"]),
            }
            for row in before_rows
        ]
        all_moved = bool(before_rows) and all(
            isinstance(row.get("after"), dict)
            and row["after"].get("owner") == beneficiary
            and row["before"].get("complete")
            and row["after"].get("complete")
            for row in moved
        )
        result["before"] = {
            "target_owned_count": len(before_rows),
            "target_rows": before_rows,
        }
        result["after"] = {
            "target_owned_count": len(after_rows),
            "beneficiary_owned_count": len(beneficiary_rows),
            "target_rows": after_rows,
        }
        result["moved_rows"] = moved
        checks.update(
            {
                "target_owned_count_zero_after": len(after_rows) == 0,
                "all_target_provinces_moved_to_beneficiary": all_moved,
            }
        )
    elif action in {"force_vassalization", "form_personal_union"}:
        before_pair = _relation_pair(before_relations, country, beneficiary)
        after_pair = _relation_pair(after_relations, country, beneficiary)
        expected_type = SUBJECT_EXPECTED_TYPE[action]
        result["before"] = before_pair
        result["after"] = after_pair
        checks.update(
            {
                "before_relation_at_most_one": before_pair["count"] <= 1,
                "after_relation_at_most_one": after_pair["count"] <= 1,
                "after_relation_present": after_pair["present"],
                "after_subject_type_expected": (
                    after_pair["subject_types"] == [expected_type]
                ),
                "relation_scan_complete": (
                    not before_relations["scan"]["unknown"]
                    and not after_relations["scan"]["unknown"]
                ),
            }
        )
        if expectation["expected_state"] == "rejected":
            checks["rejected_relation_unchanged"] = (
                before_pair["present"] == after_pair["present"]
                and before_pair["subject_types"]
                == after_pair["subject_types"]
            )
    elif action == "grant_independence":
        before_overlords = _all_overlord_records(before_relations, country)
        after_overlords = _all_overlord_records(after_relations, country)
        result["before"] = {
            "overlord_count": len(before_overlords),
            "overlords": before_overlords,
            "pair": _relation_pair(before_relations, country, source),
        }
        result["after"] = {
            "overlord_count": len(after_overlords),
            "overlords": after_overlords,
            "pair": _relation_pair(after_relations, country, source),
        }
        checks.update(
            {
                "after_no_overlord_relation": len(after_overlords) == 0,
                "relation_scan_complete": (
                    not before_relations["scan"]["unknown"]
                    and not after_relations["scan"]["unknown"]
                ),
            }
        )
    result["status"] = "passed" if all(checks.values()) else "incomplete"
    return result


def compare(
    before_path: Path, after_path: Path, expectations: list[dict[str, Any]]
) -> dict[str, Any]:
    tags = {
        tag
        for expectation in expectations
        for tag in (
            expectation.get("country"),
            expectation.get("source"),
            expectation.get("beneficiary"),
        )
        if tag
    }
    before_provinces = scan_owned_provinces(before_path, tags)
    after_provinces = scan_owned_provinces(after_path, tags)
    before_relations = scan_subject_relations(before_path, tags)
    after_relations = scan_subject_relations(after_path, tags)
    effects = [
        _base_effect(
            expectation,
            before_provinces,
            after_provinces,
            before_relations,
            after_relations,
        )
        for expectation in expectations
    ]
    checks = {
        "before_provinces_scan_complete": (
            before_provinces["scan"]["provinces_block_found"]
            and before_provinces["scan"]["provinces_block_complete"]
            and before_provinces["scan"]["brace_balance_ok"]
            and not before_provinces["scan"]["unknown"]
        ),
        "after_provinces_scan_complete": (
            after_provinces["scan"]["provinces_block_found"]
            and after_provinces["scan"]["provinces_block_complete"]
            and after_provinces["scan"]["brace_balance_ok"]
            and not after_provinces["scan"]["unknown"]
        ),
        "before_relations_scan_complete": (
            before_relations["scan"]["diplomacy_block_found"]
            and before_relations["scan"]["diplomacy_block_complete"]
            and before_relations["scan"]["brace_balance_ok"]
            and not before_relations["scan"]["unknown"]
        ),
        "after_relations_scan_complete": (
            after_relations["scan"]["diplomacy_block_found"]
            and after_relations["scan"]["diplomacy_block_complete"]
            and after_relations["scan"]["brace_balance_ok"]
            and not after_relations["scan"]["unknown"]
        ),
        "all_effect_checks_passed": all(
            effect["status"] == "passed" for effect in effects
        ),
    }
    return {
        "schema": "r61_country_save_compare_v1",
        "status": "passed" if all(checks.values()) else "incomplete",
        "checks": checks,
        "expectations": expectations,
        "before": {
            "source": before_provinces["source"],
            "provinces": before_provinces,
            "relations": before_relations,
        },
        "after": {
            "source": after_provinces["source"],
            "provinces": after_provinces,
            "relations": after_relations,
        },
        "effects": effects,
        "streaming_contract": {
            "complete_save_loaded_into_memory": False,
            "sha256_recomputed": False,
            "province_rows_retained_only_for_target_owners": True,
            "relation_parser": "work/inspect_peace_subject_save.py",
            "treasury_attribution": "not performed; native immediate effects remain authoritative",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument(
        "--expectations",
        required=True,
        help="inline JSON list or path to a JSON list file",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new report directory, or an explicit .json report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before = _resolve_save(args.before, "before save")
    after = _resolve_save(args.after, "after save")
    expectations = _parse_expectations(args.expectations)
    report = compare(before, after, expectations)
    output = args.output
    report_path = output if output.suffix.lower() == ".json" else output / "report.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite report: {report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "output": str(report_path)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
