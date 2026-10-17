#!/usr/bin/env python3
"""Stream and compare serialized Declare War active_war blocks in two EU4 saves.

The parser retains only requested actor/recipient country blocks and matching
active_war blocks. It preserves source keys and bounded text excerpts. It does
not claim that an unproven save key is the native Declare War payload meaning.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

try:
    from work import inspect_dissolve_save_pair as bounded
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work import inspect_dissolve_save_pair as bounded

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "work" / "runtime" / "declarewar-save-reader-20261016-r36-001"
MAX_WAR_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_RAW_EXCERPT_BYTES = 64 * 1024
MAX_REPORT_EXCERPT_BYTES = 8 * 1024
MAX_SELECTED_FIELDS = 512
MAX_FIELD_CHANGES = 256
MAX_WAR_RECORDS = 64
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
ACTIVE_WAR_RE = re.compile(r"^\s*active_war\s*=\s*\{")
COUNTRY_FIELD_KEYS = {
    "is_at_war", "last_war", "last_war_ended", "last_sent_peace_offer_date",
}


class WarReaderError(RuntimeError):
    pass


def validate_tag(value: str, option: str) -> str:
    tag = value.strip().upper()
    if not TAG_RE.fullmatch(tag):
        raise argparse.ArgumentTypeError(
            f"{option} must be an uppercase country tag of 1-6 letters/digits"
        )
    return tag


def scalar_values(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(scalar_values(item))
        return result
    if value is None:
        return []
    return [str(value)]


def last_value(fields: dict[str, Any], key: str) -> str | None:
    values = scalar_values(fields.get(key))
    return values[-1] if values else None


def unquoted(value: str | None) -> str | None:
    return bounded.unquote(value) if value is not None else None


def short_raw(text: str, limit: int = MAX_RAW_EXCERPT_BYTES) -> tuple[str, bool]:
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= limit:
        return text, False
    first = limit // 2
    last = limit - first
    clipped = encoded[:first] + b"\n...<raw excerpt truncated>...\n" + encoded[-last:]
    return clipped.decode("utf-8", "replace"), True


def filtered_fields(fields: dict[str, Any], predicate: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(fields):
        if len(result) >= MAX_SELECTED_FIELDS:
            break
        if predicate(key.casefold(), key):
            result[key] = fields[key]
    return result


def selected_war_fields(fields: dict[str, Any]) -> dict[str, Any]:
    def include(lowered: str, key: str) -> bool:
        if "losses" in lowered or "members" in lowered:
            return False
        if key in {
            "name", "original_attacker", "original_defender", "action",
            "outcome", "is_coalition", "attacker_score", "defender_score",
            "war_score", "start_date", "end_date", "stalled_years",
        }:
            return True
        return any(
            token in lowered
            for token in (
                "attacker", "defender", "casus_belli", "goal", "province",
                "war_score", "score", "start_date", "end_date", "join_date",
                "next_", "last_", "stalled",
            )
        )
    return filtered_fields(fields, include)


def candidate_fields(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "date_candidates": filtered_fields(
            fields,
            lambda lowered, key: (
                key in {"action", "date", "start_date", "end_date"}
                or lowered.endswith(".date")
                or any(token in lowered for token in ("start_date", "end_date", "join_date"))
                or lowered.startswith("next_")
            ),
        ),
        "casus_belli_candidates": filtered_fields(
            fields, lambda lowered, key: "casus_belli" in lowered
        ),
        "war_goal_candidates": filtered_fields(
            fields,
            lambda lowered, key: (
                "goal" in lowered
                or (lowered.startswith("take_") and key.endswith(".type"))
            ),
        ),
        "target_province_candidates": filtered_fields(
            fields,
            lambda lowered, key: key == "province" or lowered.endswith(".province"),
        ),
    }


def tags_in_text(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in re.findall(r"\b[A-Z][A-Z0-9_]{1,5}\b", text):
        if TAG_RE.fullmatch(token) and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def entry_bodies(entries: Iterable[Any], key: str) -> list[str]:
    return [
        entry.body for entry in entries
        if entry.key == key and entry.body is not None
    ]


def side_tags(entries: Iterable[Any], key: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for body in entry_bodies(entries, key):
        for tag in tags_in_text(body):
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
    return result


def participant_records(entries: Iterable[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        if entry.key != "participants" or entry.body is None:
            continue
        nested = bounded.top_level_entries(entry.body)
        fields, blocks = bounded.flatten_entries(nested)
        selected = {
            key: value for key, value in fields.items()
            if "losses" not in key.casefold() and "members" not in key.casefold()
        }
        result.append({
            "tag": unquoted(last_value(fields, "tag")),
            "fields": selected,
            "blocks": [
                block for block in blocks
                if "losses" not in block.casefold()
                and "members" not in block.casefold()
            ],
        })
    return result


def war_goal_records(entries: Iterable[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        lowered = entry.key.casefold()
        if entry.body is None or not (
            lowered.startswith("take_") or lowered in {"war_goal", "goal"}
        ):
            continue
        nested = bounded.top_level_entries(entry.body)
        fields, blocks = bounded.flatten_entries(nested)
        result.append({"kind": entry.key, "fields": fields, "blocks": blocks})
    return result


def parse_active_war_block(
    text: str,
    actor: str,
    recipient: str,
    line_start: int = 1,
    line_end: int | None = None,
    bytes_captured: int | None = None,
) -> dict[str, Any] | None:
    try:
        parsed = bounded.parse_structured_block(text)
        body = bounded.extract_block(text, text.find("{"))
        entries = bounded.top_level_entries(body)
    except Exception as exc:
        raise WarReaderError(f"active_war parse failed at line {line_start}: {exc}") from exc
    fields = parsed.get("fields", {})
    raw_tags: set[str] = set()
    for value in fields.values():
        for scalar in scalar_values(value):
            raw_tags.update(tags_in_text(unquoted(scalar) or ""))
    attackers = side_tags(entries, "attackers")
    defenders = side_tags(entries, "defenders")
    persistent_attackers = side_tags(entries, "persistent_attackers")
    persistent_defenders = side_tags(entries, "persistent_defenders")
    # Some saves carry country tags only in the side blocks (for example an
    # active war with no participant records).  Include those serialized
    # sides in the pair test instead of requiring a participant/original-side
    # scalar to repeat the tags.
    serialized_tags = (
        raw_tags
        | set(attackers)
        | set(defenders)
        | set(persistent_attackers)
        | set(persistent_defenders)
    )
    if actor not in serialized_tags or recipient not in serialized_tags:
        return None
    pair_currently_active = (
        (actor in attackers and recipient in defenders)
        or (actor in defenders and recipient in attackers)
    )
    raw_excerpt, raw_truncated = short_raw(text)
    name_raw = last_value(fields, "name")
    name_value = unquoted(name_raw)
    candidates = candidate_fields(fields)
    return {
        "line_start": line_start,
        "line_end": line_end,
        "bytes_captured": bytes_captured or len(text.encode("utf-8", "replace")),
        "serialized_pair_match": True,
        "pair_currently_active": pair_currently_active,
        "current_sides": {
            "attackers": attackers,
            "defenders": defenders,
            "all_current_tags": sorted(set(attackers) | set(defenders)),
            "persistent_attackers": persistent_attackers,
            "persistent_defenders": persistent_defenders,
        },
        "original_sides": {
            "original_attacker": unquoted(last_value(fields, "original_attacker")),
            "original_defender": unquoted(last_value(fields, "original_defender")),
        },
        "name": {
            "raw": name_raw,
            "decoded_text": name_value,
            "utf8_hex": name_value.encode("utf-8", "replace").hex()
            if name_value is not None else None,
        },
        "serialized_fields": selected_war_fields(fields),
        "date_candidates": candidates["date_candidates"],
        "casus_belli_candidates": candidates["casus_belli_candidates"],
        "war_goal_candidates": candidates["war_goal_candidates"],
        "target_province_candidates": candidates["target_province_candidates"],
        "participants": participant_records(entries),
        "war_goal_records": war_goal_records(entries),
        "serialized_block_paths": parsed.get("blocks", []),
        "parser_unknown": parsed.get("unknown", []),
        "raw_excerpt": raw_excerpt,
        "raw_excerpt_sha256": hashlib.sha256(
            raw_excerpt.encode("utf-8", "replace")
        ).hexdigest(),
        "raw_excerpt_truncated": raw_truncated,
        "raw_excerpt_limit_bytes": MAX_RAW_EXCERPT_BYTES,
    }


class ActiveWarScanner:
    def __init__(self, actor: str, recipient: str) -> None:
        self.actor = actor
        self.recipient = recipient
        self.depth = 0
        self.line_count = 0
        self.current: dict[str, Any] | None = None
        self.blocks_seen = 0
        self.records: list[dict[str, Any]] = []
        self.unknown: list[str] = []

    def finish(self, end_line: int | None, complete: bool) -> None:
        current = self.current
        self.current = None
        if current is None:
            return
        if not complete:
            self.unknown.append(f"active_war_unclosed_at_line_{current['line_start']}")
            return
        if current["too_large"]:
            self.unknown.append(
                f"active_war_lines_{current['line_start']}_{end_line}_exceeded_{MAX_WAR_CAPTURE_BYTES}_bytes"
            )
            return
        try:
            record = parse_active_war_block(
                "".join(current["lines"]),
                self.actor,
                self.recipient,
                current["line_start"],
                end_line,
                current["bytes_captured"],
            )
        except WarReaderError as exc:
            self.unknown.append(str(exc))
            return
        if record is not None:
            if len(self.records) >= MAX_WAR_RECORDS:
                self.unknown.append("matching_active_war_record_limit_reached")
            else:
                self.records.append(record)

    def consume(self, stream: Any) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            before = self.depth
            if self.current is None and ACTIVE_WAR_RE.match(line):
                self.blocks_seen += 1
                self.current = {
                    "line_start": line_number,
                    "parent_depth": before,
                    "block_depth": before + bounded.brace_delta(line),
                    "lines": [],
                    "bytes_captured": 0,
                    "too_large": False,
                }
            if self.current is not None:
                encoded_size = len(line.encode("utf-8", "replace"))
                self.current["bytes_captured"] += encoded_size
                if not self.current["too_large"]:
                    if self.current["bytes_captured"] <= MAX_WAR_CAPTURE_BYTES:
                        self.current["lines"].append(line)
                    else:
                        self.current["too_large"] = True
                        self.current["lines"] = []
            self.depth += bounded.brace_delta(line)
            if (
                self.current is not None
                and self.depth == self.current["parent_depth"]
                and before >= self.current["block_depth"]
            ):
                self.finish(line_number, True)
        if self.current is not None:
            self.finish(None, False)


def configure_country_reader(tags: tuple[str, str]) -> None:
    bounded.TARGET_TAGS = tags
    bounded.PAIR = frozenset(tags)
    bounded.COUNTRY_RE = re.compile(
        r"^\s*(" + "|".join(re.escape(tag) for tag in tags) + r")\s*=\s*\{"
    )


def selected_country_fields(fields: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(fields):
        lowered = key.casefold()
        if key in COUNTRY_FIELD_KEYS or any(
            token in lowered for token in ("war", "diplom", "prestige", "stability")
        ):
            result[key] = fields[key]
        if len(result) >= MAX_SELECTED_FIELDS:
            break
    return result


def scan_country_context(
    path: Path, source: dict[str, Any], tags: tuple[str, str]
) -> dict[str, Any]:
    configure_country_reader(tags)
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    countries: dict[str, Any] = {}
    for tag in tags:
        capture = scanner.country_captures.get(tag)
        item: dict[str, Any] = {
            "found": capture is not None,
            "start_line": capture.start_line if capture else None,
            "end_line": capture.end_line if capture else None,
            "complete": bool(capture and capture.complete),
            "bytes_captured": capture.bytes_captured if capture else 0,
            "selected_fields": {},
            "pair_active_relation": None,
        }
        if capture is not None and capture.complete:
            try:
                body = bounded.extract_block(capture.text, capture.text.find("{"))
                entries = bounded.top_level_entries(body)
                fields, blocks = bounded.flatten_entries(entries)
                item["selected_fields"] = selected_country_fields(fields)
                item["block_paths"] = [
                    block for block in blocks if "history" not in block.casefold()
                ][:MAX_SELECTED_FIELDS]
                other = tags[1] if tag == tags[0] else tags[0]
                item["pair_active_relation"] = bounded.active_relation_result(
                    capture, other
                )
            except Exception as exc:
                item["parse_error"] = str(exc)
        countries[tag] = item
    unknown: list[str] = []
    for tag in tags:
        item = countries[tag]
        if not item["found"]:
            unknown.append(f"country_{tag}_not_found")
        elif not item["complete"]:
            unknown.append(f"country_{tag}_capture_incomplete")
    if scanner.duplicate_country_tags:
        unknown.extend(f"duplicate_country_tag:{tag}" for tag in scanner.duplicate_country_tags)
    if not scanner.countries_found:
        unknown.append("countries_block_not_found")
    elif not scanner.countries_complete:
        unknown.append("countries_block_incomplete")
    return {
        "first_line": scanner.header_line,
        "date": scanner.save_date,
        "line_count": scanner.line_count,
        "countries_block_found": scanner.countries_found,
        "countries_block_complete": scanner.countries_complete,
        "alliance_pair_entry_count": len(scanner.alliance_pair_entries),
        "countries": countries,
        "unknown": unknown,
    }


def scan_active_wars(
    path: Path, source: dict[str, Any], actor: str, recipient: str
) -> dict[str, Any]:
    scanner = ActiveWarScanner(actor, recipient)
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    return {
        "line_count": scanner.line_count,
        "final_brace_depth": scanner.depth,
        "brace_balance_ok": scanner.depth == 0,
        "active_war_blocks_seen": scanner.blocks_seen,
        "matching_active_wars": scanner.records,
        "unknown": scanner.unknown,
    }


def serialized_save_date(path: Path, source: dict[str, Any]) -> str | None:
    """Read only the small ZIP meta member when one is available."""

    if source.get("container") != "zip":
        return None
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = {info.filename.casefold(): info.filename for info in archive.infolist()}
            member = names.get("meta")
            if member is None:
                return None
            with archive.open(member, "r") as raw:
                with io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace") as stream:
                    for line in stream:
                        match = re.match(r"^\s*date\s*=\s*([^\r\n]+)", line)
                        if match:
                            return bounded.unquote(match.group(1).strip())
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    return None


def scan_save(
    path: Path,
    actor: str,
    recipient: str,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise WarReaderError(f"save path is not a file: {resolved}")
    source = bounded.detect_container(resolved)
    source["sha256"] = bounded.sha256_file(resolved)
    source["expected_sha256"] = expected_sha256
    source["sha256_matches_expected"] = (
        source["sha256"].casefold() == expected_sha256.casefold()
        if expected_sha256 else None
    )
    tags = (actor, recipient)
    country = scan_country_context(resolved, source, tags)
    wars = scan_active_wars(resolved, source, actor, recipient)
    save_date = serialized_save_date(resolved, source) or country["date"]
    return {
        "source": source,
        "metadata": {"first_line": country["first_line"], "date": save_date},
        "parse": {
            "gamestate_line_count": max(country["line_count"], wars["line_count"]),
            "final_brace_depth": wars["final_brace_depth"],
            "brace_balance_ok": (
                country["countries_block_complete"] and wars["brace_balance_ok"]
            ),
            "countries_block_found": country["countries_block_found"],
            "countries_block_complete": country["countries_block_complete"],
            "active_war_scan_complete": wars["brace_balance_ok"],
            "unknown": country["unknown"] + wars["unknown"],
        },
        "country_context": country,
        "war_scan": wars,
    }


def identity_value(record: dict[str, Any], key: str) -> Any:
    values = scalar_values(record.get("serialized_fields", {}).get(key))
    return unquoted(values[-1]) if values else None


def war_identity(record: dict[str, Any]) -> tuple[Any, ...]:
    def normalized(mapping: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True))
            for key, value in mapping.items()
        ))
    return (
        identity_value(record, "original_attacker"),
        identity_value(record, "original_defender"),
        identity_value(record, "action"),
        normalized(record.get("casus_belli_candidates", {})),
        normalized(record.get("target_province_candidates", {})),
        identity_value(record, "name"),
    )


def record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "line_start", "line_end", "bytes_captured",
            "pair_currently_active", "current_sides", "original_sides",
            "name", "serialized_fields", "date_candidates",
            "casus_belli_candidates", "war_goal_candidates",
            "target_province_candidates", "participants", "war_goal_records",
        )
    }


def field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes.append({"field": key, "before": old, "after": new})
            if len(changes) >= MAX_FIELD_CHANGES:
                break
    return changes


def compare_scans(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    def grouped(records: list[dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
        result: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for record in records:
            result.setdefault(war_identity(record), []).append(record)
        return result

    left = grouped(before["war_scan"]["matching_active_wars"])
    right = grouped(after["war_scan"]["matching_active_wars"])
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    for identity in sorted(set(left) | set(right), key=repr):
        old_items = left.get(identity, [])
        new_items = right.get(identity, [])
        common = min(len(old_items), len(new_items))
        for index in range(common):
            old = old_items[index]
            new = new_items[index]
            retained.append({
                "identity": list(identity),
                "occurrence": index,
                "before": record_summary(old),
                "after": record_summary(new),
                "field_changes": field_changes(
                    old.get("serialized_fields", {}),
                    new.get("serialized_fields", {}),
                ),
                "current_side_changes": old.get("current_sides") != new.get("current_sides"),
                "pair_active_before": old.get("pair_currently_active"),
                "pair_active_after": new.get("pair_currently_active"),
            })
        for record in new_items[common:]:
            added.append({"identity": list(identity), "after": record_summary(record)})
        for record in old_items[common:]:
            removed.append({"identity": list(identity), "before": record_summary(record)})
    old_records = before["war_scan"]["matching_active_wars"]
    new_records = after["war_scan"]["matching_active_wars"]
    return {
        "before_matching_block_count": len(old_records),
        "after_matching_block_count": len(new_records),
        "before_currently_active_count": sum(bool(item["pair_currently_active"]) for item in old_records),
        "after_currently_active_count": sum(bool(item["pair_currently_active"]) for item in new_records),
        "added": added,
        "retained": retained,
        "removed": removed,
    }


def json_text(value: Any, limit: int | None = None) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if limit is not None and len(text.encode("utf-8")) > limit:
        return short_raw(text, limit)[0]
    return text


def render_report(payload: dict[str, Any]) -> str:
    pair = payload["pair"]
    context = payload.get("run_context", {})
    lines = [
        "# Declare War 存档战争对照取证",
        "",
        "工具按行扫描两个 EU4 gamestate，只保留请求 actor/recipient 国家块和同时包含两个 tag 的 active_war 块。完整存档与完整 gamestate 不进入内存。",
        "",
        f"actor={pair['actor']} recipient={pair['recipient']}",
        f"purpose={context.get('purpose', 'business_pair')}",
        str(context.get("note", "")),
        "当前参战状态只依据 active_war 内的 attackers/defenders；participants、persistent_* 和 history 单独保留。",
        "action、start_date、take_*.casus_belli、take_*.type、take_*.province 按存档键名输出，未证明语义的字段称为候选。",
        "",
    ]
    for label in ("before", "after"):
        side = payload[label]
        source = side["source"]
        records = side["war_scan"]["matching_active_wars"]
        lines.extend([
            f"## {label}",
            "",
            f"file={source['path']}",
            f"size_bytes={source.get('size_bytes')} sha256={source.get('sha256')}",
            f"container={source.get('container')} gamestate={source.get('gamestate_member')}",
            f"save_date={side['metadata'].get('date')} gamestate_lines={side['parse'].get('gamestate_line_count')}",
            f"countries_complete={side['parse'].get('countries_block_complete')} "
            f"active_war_brace_balance={side['war_scan'].get('brace_balance_ok')}",
            f"matching_active_war_blocks={len(records)} "
            f"currently_active_pair_blocks={sum(bool(item['pair_currently_active']) for item in records)}",
            "",
            "country_context:",
        ])
        for tag, item in side["country_context"]["countries"].items():
            lines.append(
                f"- {tag}: found={item['found']} complete={item['complete']} "
                f"lines={item['start_line']}-{item['end_line']} "
                f"fields={json_text(item.get('selected_fields'))}"
            )
        lines.append("")
        if not records:
            lines.append("没有观察到同时包含两个请求 tag 的 active_war 块。")
        for index, record in enumerate(records, 1):
            lines.extend([
                f"### war_block_{index} lines={record.get('line_start')}-{record.get('line_end')}",
                f"pair_currently_active={record.get('pair_currently_active')}",
                f"original_sides={json_text(record.get('original_sides'))}",
                f"name={json_text(record.get('name'))}",
                f"date_candidates={json_text(record.get('date_candidates'))}",
                f"casus_belli_candidates={json_text(record.get('casus_belli_candidates'))}",
                f"war_goal_candidates={json_text(record.get('war_goal_candidates'))}",
                f"target_province_candidates={json_text(record.get('target_province_candidates'))}",
                f"current_sides={json_text(record.get('current_sides'))}",
                f"participants={json_text(record.get('participants'))}",
                "serialized_fields:",
                json_text(record.get("serialized_fields")),
                "bounded_raw_excerpt_json:",
                json_text(record.get("raw_excerpt", ""), MAX_REPORT_EXCERPT_BYTES),
                "",
            ])
    comparison = payload["comparison"]
    lines.extend([
        "## before_after_diff",
        "",
        f"before_blocks={comparison['before_matching_block_count']} "
        f"after_blocks={comparison['after_matching_block_count']}",
        f"before_currently_active={comparison['before_currently_active_count']} "
        f"after_currently_active={comparison['after_currently_active_count']}",
        f"added={len(comparison['added'])} retained={len(comparison['retained'])} removed={len(comparison['removed'])}",
        "added:",
        json_text(comparison["added"]),
        "retained:",
        json_text(comparison["retained"]),
        "removed:",
        json_text(comparison["removed"]),
        "",
        "## boundaries",
        "",
        f"active_war_capture_limit_bytes={MAX_WAR_CAPTURE_BYTES}",
        f"raw_excerpt_limit_bytes={MAX_RAW_EXCERPT_BYTES}",
        "name 保留 raw、decoded_text 和 UTF-8 hex；工具不自行翻译内部编码。",
        "存档字段候选不能替代 native Declare War +0x48 owned payload 或完整 CB/war goal 证明。",
        "本报告证明序列化存档内容，不证明请求提交、规则合法性、战争结果或重载。",
        "",
    ])
    return "\n".join(lines)


def build_payload(
    before_path: Path,
    after_path: Path,
    actor: str,
    recipient: str,
    expected_before_sha256: str | None = None,
    expected_after_sha256: str | None = None,
    purpose: str = "business_pair",
) -> dict[str, Any]:
    before = scan_save(before_path, actor, recipient, expected_before_sha256)
    after = scan_save(after_path, actor, recipient, expected_after_sha256)
    return {
        "tool": {
            "name": "work/inspect_declare_war_save_pair.py",
            "version": 1,
            "streaming": True,
            "whole_gamestate_read": False,
            "country_capture_limit_bytes": bounded.MAX_COUNTRY_CAPTURE,
            "active_war_capture_limit_bytes": MAX_WAR_CAPTURE_BYTES,
            "raw_excerpt_limit_bytes": MAX_RAW_EXCERPT_BYTES,
            "sha256": "streamed_source_file",
            "scanner_helper": "work/inspect_dissolve_save_pair.py",
        },
        "pair": {"actor": actor, "recipient": recipient},
        "run_context": {
            "purpose": purpose,
            "note": (
                "schema_sample 只用于证明实际 active_war 键名和 parser 行为，"
                "不属于 Declare War native query/execution 运行验收。"
                if purpose == "schema_sample"
                else "business_pair 由调用者提供的 before/after 存档组成；序列化结果仍不等于 native 执行证明。"
            ),
        },
        "before": before,
        "after": after,
        "comparison": compare_scans(before, after),
        "limitations": [
            "active_war 历史块可能在 attackers/defenders 为空时继续保留；工具同时输出 current_sides 和 serialized block。",
            "name 或其他值可能使用内部编码；没有本地化映射时不翻译。",
            "未知键只作为候选字段输出，不替代 native Declare War payload 合同。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--actor", default="FRA", type=lambda value: validate_tag(value, "--actor"))
    parser.add_argument("--recipient", default="ENG", type=lambda value: validate_tag(value, "--recipient"))
    parser.add_argument("--expected-before-sha256")
    parser.add_argument("--expected-after-sha256")
    parser.add_argument(
        "--purpose",
        choices=("business_pair", "schema_sample"),
        default="business_pair",
        help="标记本次输出是业务 before/after 对照还是已知历史 schema 样本",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    if args.actor == args.recipient:
        parser.error("--actor and --recipient must differ")
    output = args.output_dir.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory is not fresh: {output}")
    output.mkdir(parents=True, exist_ok=True)
    try:
        payload = build_payload(
            args.before.expanduser().resolve(),
            args.after.expanduser().resolve(),
            args.actor,
            args.recipient,
            args.expected_before_sha256,
            args.expected_after_sha256,
            args.purpose,
        )
    except (OSError, WarReaderError, bounded.SaveParseError) as exc:
        parser.error(str(exc))
    (output / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output),
        "report_json": str(output / "report.json"),
        "report_md": str(output / "report.md"),
        "before_sha256": payload["before"]["source"]["sha256"],
        "after_sha256": payload["after"]["source"]["sha256"],
        "before_matching_wars": payload["comparison"]["before_matching_block_count"],
        "after_matching_wars": payload["comparison"]["after_matching_block_count"],
        "added": len(payload["comparison"]["added"]),
        "retained": len(payload["comparison"]["retained"]),
        "removed": len(payload["comparison"]["removed"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

