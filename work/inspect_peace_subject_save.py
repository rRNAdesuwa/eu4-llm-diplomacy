#!/usr/bin/env python3
"""流式比较两个 EU4 存档中的议和附属关系块。

只读取每个存档的 ``diplomacy`` 直接关系块，不把 gamestate 或省份表整体
载入内存。关系块按 ``block/first/second`` 对齐，完整保留解析出的关系字段，
因此 ``appanage`` 等实际 ``subject_type`` 不会被归并成 ``vassal``。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from work import inspect_dissolve_save_pair as bounded
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work import inspect_dissolve_save_pair as bounded


# These are the serialized subject/union relation names.  Ordinary alliances,
# royal marriages and trade relations are intentionally outside this contract.
SUBJECT_BLOCK_KEYS = {
    "annex",
    "client_state",
    "colony",
    "dependency",
    "dominion",
    "force_vassal",
    "forcevassal",
    "free_city",
    "integrate",
    "junior_union",
    "march",
    "overlord",
    "personal_union",
    "protectorate",
    "puppet",
    "release",
    "royal_union",
    "subject",
    "subject_relation",
    "tributary",
    "union",
    "vassal",
}
BLOCK_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{")
DIPLOMACY_RE = re.compile(r"^\s*diplomacy\s*=\s*\{")
CAPTURE_LIMIT = 128 * 1024
RAW_LIMIT = 24 * 1024


def _scalar(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[-1] if value else None
    if value is None:
        return None
    return bounded.unquote(str(value))


def _raw_excerpt(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= RAW_LIMIT:
        return text, False
    half = RAW_LIMIT // 2
    clipped = encoded[:half] + b"\n...<raw truncated>...\n" + encoded[-half:]
    return clipped.decode("utf-8", errors="replace"), True


def _pair_from_fields(fields: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return the serialized endpoints without assuming which is overlord."""

    for left_key, right_key in (
        ("first", "second"),
        ("overlord", "subject"),
        ("country", "subject"),
        ("country", "partner"),
        ("owner", "subject"),
        ("from", "to"),
    ):
        left = _scalar(fields.get(left_key))
        right = _scalar(fields.get(right_key))
        if left and right:
            return left, right
    return None, None


def scan_save(path: Path, target_countries: set[str]) -> dict[str, Any]:
    """Stream one save and retain only subject blocks touching targets."""

    source = bounded.detect_container(path)
    depth = 0
    line_count = 0
    diplomacy_found = False
    diplomacy_complete = False
    diplomacy_depth: int | None = None
    active: list[str] | None = None
    active_key: str | None = None
    active_start: int | None = None
    active_depth = 0
    active_bytes = 0
    records: list[dict[str, Any]] = []
    block_type_counts: dict[str, int] = {}
    unknown: list[str] = []

    with bounded.open_gamestate(path, source) as stream:
        for line_number, line in enumerate(stream, 1):
            line_count = line_number
            before = depth
            if not diplomacy_found and before == 0 and DIPLOMACY_RE.match(line):
                diplomacy_found = True
                diplomacy_depth = before + bounded.brace_delta(line)

            if active is None and not diplomacy_complete:
                match = BLOCK_RE.match(line)
                direct_diplomacy = (
                    diplomacy_depth is not None and before == diplomacy_depth
                )
                if match and (direct_diplomacy or before == 0):
                    key = match.group(1)
                    if key in SUBJECT_BLOCK_KEYS:
                        block_type_counts[key] = block_type_counts.get(key, 0) + 1
                        active = [line]
                        active_key = key
                        active_start = line_number
                        active_depth = bounded.brace_delta(line)
                        active_bytes = len(line.encode("utf-8", errors="replace"))
            elif active is not None:
                active.append(line)
                active_bytes += len(line.encode("utf-8", errors="replace"))
                active_depth += bounded.brace_delta(line)
                if active_bytes > CAPTURE_LIMIT:
                    unknown.append(f"line_{active_start}:{active_key}_over_limit")
                    active = None
                    active_key = None
                    active_start = None
                    active_depth = 0
                    active_bytes = 0

            if active is not None and active_depth == 0:
                text = "".join(active)
                try:
                    body = bounded.extract_block(text, text.find("{"))
                    parsed = bounded.parse_field_body(body)
                except bounded.SaveParseError as exc:
                    parsed = {"fields": {}, "blocks": [], "unknown": [str(exc)]}
                fields = parsed.get("fields", {})
                first, second = _pair_from_fields(fields)
                if first in target_countries or second in target_countries:
                    raw, truncated = _raw_excerpt(text)
                    records.append(
                        {
                            "block": active_key,
                            "line_start": active_start,
                            "line_end": line_number,
                            "first": first,
                            "second": second,
                            "subject_type": _scalar(fields.get("subject_type")),
                            "fields": fields,
                            "blocks": parsed.get("blocks", []),
                            "unknown": parsed.get("unknown", []),
                            "raw": raw,
                            "raw_truncated": truncated,
                        }
                    )
                active = None
                active_key = None
                active_start = None
                active_depth = 0
                active_bytes = 0

            depth += bounded.brace_delta(line)
            if (
                diplomacy_found
                and diplomacy_depth is not None
                and before >= diplomacy_depth
                and depth == 0
            ):
                diplomacy_complete = True

    if active is not None:
        unknown.append(f"line_{active_start}:{active_key}_incomplete")
    return {
        "source": {
            "path": str(path),
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "container": source.get("container"),
            "gamestate_member": source.get("gamestate_member"),
            "sha256_recomputed": False,
        },
        "scan": {
            "line_count": line_count,
            "diplomacy_block_found": diplomacy_found,
            "diplomacy_block_complete": diplomacy_complete,
            "final_brace_depth": depth,
            "brace_balance_ok": depth == 0,
            "unknown": unknown,
        },
        "block_type_counts": block_type_counts,
        "records": records,
    }


def _record_key(record: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (str(record.get("block")), record.get("first"), record.get("second"))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _index(records: list[dict[str, Any]]) -> dict[tuple[str, str | None, str | None], list[dict[str, Any]]]:
    indexed: dict[tuple[str, str | None, str | None], list[dict[str, Any]]] = {}
    for record in records:
        indexed.setdefault(_record_key(record), []).append(record)
    for values in indexed.values():
        values.sort(key=lambda record: _canonical(record.get("fields", {})))
    return indexed


def compare_records(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    before_index = _index(before)
    after_index = _index(after)
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unchanged = 0
    for key in sorted(set(before_index) | set(after_index), key=str):
        old = before_index.get(key, [])
        new = after_index.get(key, [])
        common = min(len(old), len(new))
        for index in range(common):
            old_fields = old[index].get("fields", {})
            new_fields = new[index].get("fields", {})
            if _canonical(old_fields) == _canonical(new_fields):
                unchanged += 1
            else:
                changed.append(
                    {
                        "key": list(key),
                        "before": old[index],
                        "after": new[index],
                    }
                )
        removed.extend(old[common:])
        added.extend(new[common:])
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged,
        "before_record_count": len(before),
        "after_record_count": len(after),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--country", action="append", required=True, dest="countries")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    countries = {str(tag).strip().upper() for tag in args.countries if str(tag).strip()}
    if not countries:
        raise SystemExit("--country requires at least one non-empty tag")
    if not args.before.is_file():
        raise FileNotFoundError(args.before)
    if not args.after.is_file():
        raise FileNotFoundError(args.after)
    before = scan_save(args.before, countries)
    after = scan_save(args.after, countries)
    checks = {
        "before_diplomacy_complete": before["scan"]["diplomacy_block_found"]
        and before["scan"]["diplomacy_block_complete"]
        and before["scan"]["brace_balance_ok"]
        and not before["scan"]["unknown"],
        "after_diplomacy_complete": after["scan"]["diplomacy_block_found"]
        and after["scan"]["diplomacy_block_complete"]
        and after["scan"]["brace_balance_ok"]
        and not after["scan"]["unknown"],
        "target_country_filter_nonempty": bool(countries),
    }
    report = {
        "schema": "peace_subject_save_compare_v1",
        "status": "passed" if all(checks.values()) else "incomplete",
        "checks": checks,
        "target_countries": sorted(countries),
        "before": before,
        "after": after,
        "difference": compare_records(before["records"], after["records"]),
        "interpretation": {
            "relation_scope": "只比较 diplomacy 直接附属/联合关系块；active_relations、province、alliance、royal_marriage 等不作为附属关系判据。",
            "field_semantics": "保留 parser 展平的全部字段；subject_type 使用存档实际值，例如 appanage 不改写为 vassal。",
            "absence": "没有匹配关系块只表示本次流式扫描未捕获该序列化块，不独立断言关系或原生合法性不存在。",
            "comparison": "按 block/first/second 对齐；同一具体关系块的字段变化列入 changed，新增和消失分别列入 added/removed。",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
