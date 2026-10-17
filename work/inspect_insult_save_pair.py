#!/usr/bin/env python3
"""Stream bounded Insult evidence from one or more EU4 saves.

Use ``--save`` repeatedly and give the same number of ``--label`` values.  A
typical comparison is labelled ``before``, ``ordinary`` and ``scornful``.  The
scanner hashes every save in chunks, captures only the actor and recipient
country blocks, and reports their two directed ``active_relations`` entries,
opinion blocks, country prestige, and serialized FRA diplomat records.

Example::

    python work/inspect_insult_save_pair.py \
        --save before.eu4 --save ordinary.eu4 --save scornful.eu4 \
        --label before --label ordinary --label scornful \
        --recipient SAV --output-dir work/runtime/r33-insult-save-effects-001

The output retains raw serialized values and source paths.  It does not assign
an engine scale to an opinion or prestige number and does not treat a missing
field as proof that the field is absent everywhere in the save.
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
except ModuleNotFoundError:  # direct ``python work/<script>.py`` invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work import inspect_dissolve_save_pair as bounded


ACTOR = "FRA"
TARGET_TAGS = (ACTOR, "SAV")
PAIR = frozenset(TARGET_TAGS)
COUNTRY_RE = re.compile(r"^\s*(FRA|SAV)\s*=\s*\{")
INSULT_TOKENS = ("insult", "scorn", "侮辱", "轻蔑")
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "runtime"
    / "r33-insult-save-effects-20261015-001"
)
_TOP_LEVEL_COUNTRY_FIELDS = (
    "prestige", "stability", "num_of_royal_marriages",
)


def configure_bounded_reader(actor: str, recipient: str) -> None:
    """Configure the imported bounded scanner for this process only."""

    global TARGET_TAGS, PAIR, COUNTRY_RE
    TARGET_TAGS = (actor, recipient)
    PAIR = frozenset(TARGET_TAGS)
    COUNTRY_RE = re.compile(
        rf"^\s*({re.escape(actor)}|{re.escape(recipient)})\s*=\s*\{{"
    )
    bounded.TARGET_TAGS = TARGET_TAGS
    bounded.PAIR = PAIR
    bounded.COUNTRY_RE = COUNTRY_RE


def _parse_country_entries(capture: Any) -> list[Any]:
    if capture is None or not capture.complete:
        return []
    open_index = capture.text.find("{")
    body = bounded.extract_block(capture.text, open_index)
    return bounded.top_level_entries(body)


def _unquote(value: object) -> object:
    return bounded.unquote(str(value)) if isinstance(value, str) else value


def _top_level_fields(entries: list[Any], keys: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for entry in entries:
        if entry.key not in keys or entry.value is None:
            continue
        value = _unquote(entry.value)
        if entry.key not in result:
            result[entry.key] = value
        elif isinstance(result[entry.key], list):
            result[entry.key].append(value)
        else:
            result[entry.key] = [result[entry.key], value]
    return result


def _contains_insult(value: object) -> bool:
    text = str(value).casefold()
    return any(token.casefold() in text for token in INSULT_TOKENS)


def _insult_related_fields(fields: object) -> dict[str, object]:
    if not isinstance(fields, dict):
        return {}
    return {
        str(key): value
        for key, value in fields.items()
        if _contains_insult(key) or _contains_insult(value)
    }


def _opinion_blocks(relation_body: str) -> list[dict[str, Any]]:
    opinions: list[dict[str, Any]] = []
    try:
        entries = bounded.top_level_entries(relation_body)
    except bounded.SaveParseError:
        return opinions
    for index, entry in enumerate(entries, 1):
        if entry.key != "opinion" or entry.body is None:
            continue
        parsed = bounded.parse_field_body(entry.body)
        fields = parsed.get("fields", {})
        modifier = None
        if isinstance(fields, dict):
            modifier = fields.get("modifier")
            if modifier is None:
                modifier = fields.get("modifier#1")
        opinions.append({
            "index": index,
            "fields": fields,
            "blocks": parsed.get("blocks", []),
            "unknown": parsed.get("unknown", []),
            "modifier": _unquote(modifier),
            "insult_related_fields": _insult_related_fields(fields),
            "source": "active_relations.<target>.opinion",
        })
    return opinions


def _relation_record(country_entries: list[Any], other: str,
                     country_tag: str) -> dict[str, Any]:
    relation_blocks = [
        entry.body
        for entry in country_entries
        if entry.key == "active_relations" and entry.body is not None
    ]
    result: dict[str, Any] = {
        "source": f"countries.{country_tag}.active_relations.{other}",
        "present": False,
        "active_relations_block_count": len(relation_blocks),
        "entries": [],
        "unknown": [],
    }
    for relation_body in relation_blocks:
        try:
            entries = bounded.top_level_entries(relation_body)
        except bounded.SaveParseError as error:
            result["unknown"].append(f"active_relations_parse_error:{error}")
            continue
        for entry in entries:
            if entry.key != other or entry.body is None:
                continue
            parsed = bounded.parse_field_body(entry.body)
            fields = parsed.get("fields", {})
            opinions = _opinion_blocks(entry.body)
            record = {
                "source": f"countries.{country_tag}.active_relations.{other}",
                "fields": fields,
                "blocks": parsed.get("blocks", []),
                "unknown": parsed.get("unknown", []),
                "opinion_blocks": opinions,
                "insult_related_fields": _insult_related_fields(fields),
            }
            result["present"] = True
            result["entries"].append(record)
            result["unknown"].extend(parsed.get("unknown", []))
    return result


def _diplomat_entries(country_entries: list[Any]) -> dict[str, Any]:
    blocks = [
        entry.body
        for entry in country_entries
        if entry.key == "diplomats" and entry.body is not None
    ]
    result: dict[str, Any] = {
        "present": bool(blocks),
        "diplomats_block_count": len(blocks),
        "entries": [],
        "unknown": [],
    }
    for body in blocks:
        try:
            entries = bounded.top_level_entries(body)
        except bounded.SaveParseError as error:
            result["unknown"].append(f"diplomats_parse_error:{error}")
            continue
        for entry in entries:
            parsed = bounded.parse_field_body(entry.body or "") if entry.body is not None else {
                "fields": {}, "blocks": [], "unknown": [],
            }
            result["entries"].append({
                "key": entry.key,
                "value": _unquote(entry.value),
                "fields": parsed.get("fields", {}),
                "blocks": parsed.get("blocks", []),
                "unknown": parsed.get("unknown", []),
            })
            result["unknown"].extend(parsed.get("unknown", []))
    return result


def _top_level_named_blocks(country_entries: list[Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in country_entries:
        if entry.key not in names or entry.body is None:
            continue
        parsed = bounded.parse_field_body(entry.body)
        fields = parsed.get("fields", {})
        result.append({
            "key": entry.key,
            "fields": fields,
            "blocks": parsed.get("blocks", []),
            "unknown": parsed.get("unknown", []),
            "insult_related_fields": _insult_related_fields(fields),
        })
    return result


def scan_save(path: Path, actor: str = ACTOR, recipient: str = "SAV",
              label: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise bounded.SaveParseError(f"save path is not a file: {path}")
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    scanner = bounded.SaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)

    countries: dict[str, Any] = {}
    unknown = list(scanner.alliance_parse_unknown)
    for tag in (actor, recipient):
        capture = scanner.country_captures.get(tag)
        country: dict[str, Any] = {
            "tag": tag,
            "capture": {
                "found": capture is not None,
                "start_line": capture.start_line if capture else None,
                "end_line": capture.end_line if capture else None,
                "complete": capture.complete if capture else False,
                "bytes_captured": capture.bytes_captured if capture else 0,
            },
            "fields": {},
            "active_relations": {},
            "diplomats": {"present": False, "diplomats_block_count": 0,
                          "entries": [], "unknown": []},
            "opinion_modifiers": [],
            "unknown": [],
        }
        if capture is None:
            country["unknown"].append("country_block_not_found")
            unknown.append(f"country_{tag}_not_found")
            countries[tag] = country
            continue
        if not capture.complete:
            country["unknown"].append("country_block_capture_incomplete")
            unknown.append(f"country_{tag}_capture_incomplete")
            countries[tag] = country
            continue
        try:
            entries = _parse_country_entries(capture)
        except bounded.SaveParseError as error:
            country["unknown"].append(f"country_parse_error:{error}")
            unknown.extend(country["unknown"])
            countries[tag] = country
            continue
        country["fields"] = _top_level_fields(entries, _TOP_LEVEL_COUNTRY_FIELDS)
        other = recipient if tag == actor else actor
        direction = f"{tag}->{other}"
        country["active_relations"][direction] = _relation_record(entries, other, tag)
        country["diplomats"] = _diplomat_entries(entries)
        country["opinion_modifiers"] = _top_level_named_blocks(
            entries, ("opinion_modifiers", "opinion_modifier")
        )
        country["unknown"].extend(country["active_relations"][direction].get("unknown", []))
        country["unknown"].extend(country["diplomats"].get("unknown", []))
        countries[tag] = country

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
    return {
        "label": label or path.stem,
        "file_name": path.name,
        "source": source,
        "metadata": {"first_line": scanner.header_line, "date": scanner.save_date},
        "parse": {
            "gamestate_line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "countries_block_found": scanner.countries_found,
            "countries_block_complete": scanner.countries_complete,
            "diplomacy_block_found": scanner.diplomacy_found,
            "diplomacy_block_complete": scanner.diplomacy_complete,
            "alliance_blocks_scanned": scanner.alliance_blocks_seen,
            "unknown": unknown,
        },
        "countries": countries,
        "scope": {
            "actor": actor,
            "recipient": recipient,
            "directions": [f"{actor}->{recipient}", f"{recipient}->{actor}"],
            "country_fields": list(_TOP_LEVEL_COUNTRY_FIELDS),
        },
    }


def _relation_entries(save: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    tag, other = direction.split("->", 1)
    country = save.get("countries", {}).get(tag, {})
    relation = country.get("active_relations", {}).get(direction, {})
    entries = relation.get("entries", []) if isinstance(relation, dict) else []
    return entries if isinstance(entries, list) else []


def _opinion_projection(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        for opinion in entry.get("opinion_blocks", []):
            if isinstance(opinion, dict):
                result.append({
                    "source": opinion.get("source"),
                    "modifier": opinion.get("modifier"),
                    "fields": opinion.get("fields", {}),
                    "insult_related_fields": opinion.get("insult_related_fields", {}),
                })
    return result


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    missing = object()
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key, missing)
        new = after.get(key, missing)
        if old == new:
            continue
        changes.append({
            "field": key,
            "kind": "added" if old is missing else "removed" if new is missing else "changed",
            "before": None if old is missing else old,
            "after": None if new is missing else new,
        })
    return changes


def _country_field_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for tag in TARGET_TAGS:
        old = before.get("countries", {}).get(tag, {}).get("fields", {})
        new = after.get("countries", {}).get(tag, {}).get("fields", {})
        result[tag] = {
            "before": old,
            "after": new,
            "field_changes": _field_changes(old if isinstance(old, dict) else {},
                                             new if isinstance(new, dict) else {}),
        }
    return result


def _direction_comparison(before: dict[str, Any], after: dict[str, Any],
                          direction: str) -> dict[str, Any]:
    before_entries = _relation_entries(before, direction)
    after_entries = _relation_entries(after, direction)
    old_fields = before_entries[0].get("fields", {}) if before_entries else {}
    new_fields = after_entries[0].get("fields", {}) if after_entries else {}
    old_related = before_entries[0].get("insult_related_fields", {}) if before_entries else {}
    new_related = after_entries[0].get("insult_related_fields", {}) if after_entries else {}
    return {
        "before_entry_count": len(before_entries),
        "after_entry_count": len(after_entries),
        "before_fields": old_fields,
        "after_fields": new_fields,
        "field_changes": _field_changes(
            old_fields if isinstance(old_fields, dict) else {},
            new_fields if isinstance(new_fields, dict) else {},
        ),
        "insult_related_before": old_related,
        "insult_related_after": new_related,
        "insult_related_field_changes": _field_changes(
            old_related if isinstance(old_related, dict) else {},
            new_related if isinstance(new_related, dict) else {},
        ),
        "opinion_before": _opinion_projection(before_entries),
        "opinion_after": _opinion_projection(after_entries),
    }


def _comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    directions = tuple(
        f"{left}->{right}" for left, right in (
            (TARGET_TAGS[0], TARGET_TAGS[1]),
            (TARGET_TAGS[1], TARGET_TAGS[0]),
        )
    )
    return {
        "from_label": before.get("label"),
        "to_label": after.get("label"),
        "from_source_sha256": before.get("source", {}).get("sha256"),
        "to_source_sha256": after.get("source", {}).get("sha256"),
        "country_field_changes": _country_field_changes(before, after),
        "directions": {
            direction: _direction_comparison(before, after, direction)
            for direction in directions
        },
    }


def _find_label(saves: list[dict[str, Any]], names: tuple[str, ...]) -> dict[str, Any] | None:
    for save in saves:
        label = str(save.get("label", "")).casefold()
        if any(name in label for name in names):
            return save
    return None


def _scenario_comparisons(saves: list[dict[str, Any]]) -> dict[str, Any]:
    before = _find_label(saves, ("before", "baseline", "初始"))
    ordinary = _find_label(saves, ("ordinary", "send", "normal", "普通"))
    scornful = _find_label(saves, ("scornful", "scorn", "轻蔑"))
    result: dict[str, Any] = {
        "selected_labels": {
            "before": before.get("label") if before else None,
            "ordinary": ordinary.get("label") if ordinary else None,
            "scornful": scornful.get("label") if scornful else None,
        },
        "comparisons": {},
        "selection_complete": before is not None and ordinary is not None and scornful is not None,
    }
    for left_name, left, right_name, right in (
        ("before", before, "ordinary", ordinary),
        ("before", before, "scornful", scornful),
        ("ordinary", ordinary, "scornful", scornful),
    ):
        if left is not None and right is not None:
            result["comparisons"][f"{left_name}_to_{right_name}"] = _comparison(left, right)
    return result


def build_payload(paths: list[Path], labels: list[str], actor: str,
                  recipient: str) -> dict[str, Any]:
    configure_bounded_reader(actor, recipient)
    saves = [
        scan_save(path, actor, recipient, labels[index])
        for index, path in enumerate(paths)
    ]
    comparisons = [
        _comparison(saves[index], saves[index + 1])
        for index in range(len(saves) - 1)
    ]
    return {
        "tool": {
            "name": "inspect_insult_save_pair.py",
            "version": 1,
            "scope": (
                "streaming gamestate scan; actor/recipient country blocks, "
                "both active_relations directions, opinion blocks, country "
                "prestige and actor diplomats"
            ),
            "scanner_source": "work/inspect_dissolve_save_pair.py",
            "whole_save_read": False,
            "raw_values_preserved": True,
        },
        "pair": [actor, recipient],
        "snapshot_labels": [save["label"] for save in saves],
        "saves": saves,
        "comparisons": comparisons,
        "scenario_comparisons": _scenario_comparisons(saves),
        "integrity": {
            "all_sources_present": all(save["source"].get("size_bytes", 0) > 0 for save in saves),
            "all_target_country_captures_complete": all(
                save["countries"][tag]["capture"]["complete"]
                for save in saves for tag in (actor, recipient)
            ),
            "all_streams_brace_balanced": all(
                save["parse"]["brace_balance_ok"] for save in saves
            ),
            "unknown_count": sum(len(save["parse"].get("unknown", [])) for save in saves),
        },
    }


def _format(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_report(payload: dict[str, Any]) -> str:
    actor, recipient = payload["pair"]
    lines = [
        "# Insult 普通与轻蔑侮辱存档取证",
        "",
        "本报告由 `inspect_insult_save_pair.py` 生成。扫描器逐个流式读取 EU4 存档，"
        f"只保留 `{actor}` 与 `{recipient}` 国家块、双方 `active_relations`、意见块、"
        f"`{actor}` 的威望和外交官记录。报告表格中的数值是游戏原始序列化值。",
        "",
        "## 存档完整性",
        "",
        "| 标签 | 文件 | 日期 | 字节数 | SHA-256 | 国家块完整 | 括号平衡 | 未知项 |",
        "|---|---|---|---:|---|---|---|---:|",
    ]
    for save in payload["saves"]:
        source = save["source"]
        parse = save["parse"]
        lines.append(
            f"| `{save['label']}` | `{save['file_name']}` | `{save['metadata'].get('date')}` | "
            f"{source.get('size_bytes')} | `{source.get('sha256')}` | "
            f"{parse.get('countries_block_complete')} | {parse.get('brace_balance_ok')} | "
            f"{len(parse.get('unknown', []))} |"
        )
    lines.extend(["", "## 威望和外交官记录", ""])
    for save in payload["saves"]:
        country = save["countries"][actor]
        lines.append(
            f"- `{save['label']}` `{actor}.prestige` = "
            f"`{country.get('fields', {}).get('prestige')}`；外交官条目数 = "
            f"`{len(country.get('diplomats', {}).get('entries', []))}`。"
        )
    lines.extend(["", "## 双向意见和 Insult 相关字段", ""])
    for direction in (f"{actor}->{recipient}", f"{recipient}->{actor}"):
        lines.append(f"### `{direction}`")
        lines.append("")
        lines.append("| 存档 | 条目数 | `opinion.modifier` | Insult 相关字段 | 全部关系字段 |")
        lines.append("|---|---:|---|---|---|")
        for save in payload["saves"]:
            entries = _relation_entries(save, direction)
            opinions = _opinion_projection(entries)
            related = [entry.get("insult_related_fields", {}) for entry in entries]
            fields = [entry.get("fields", {}) for entry in entries]
            modifiers = [opinion.get("modifier") for opinion in opinions]
            lines.append(
                f"| `{save['label']}` | {len(entries)} | `{_format(modifiers)}` | "
                f"`{_format(related)}` | `{_format(fields)}` |"
            )
        lines.append("")
    lines.extend(["## 普通与轻蔑对照", ""])
    scenario = payload["scenario_comparisons"]
    selected = scenario["selected_labels"]
    lines.append(
        f"选择的标签：before=`{selected['before']}`，ordinary=`{selected['ordinary']}`，"
        f"scornful=`{selected['scornful']}`；三类标签完整=`{scenario['selection_complete']}`。"
    )
    lines.append("")
    for name, comparison in scenario["comparisons"].items():
        lines.append(f"### `{name}`")
        lines.append("")
        for direction, data in comparison.get("directions", {}).items():
            lines.append(
                f"- `{direction}`：意见字段变化 `"
                f"{_format(data.get('field_changes', []))}`；"
                f"Insult 相关变化 `{_format(data.get('insult_related_field_changes', []))}`。"
            )
        for tag, data in comparison.get("country_field_changes", {}).items():
            lines.append(
                f"- `{tag}` 国家字段变化：`{_format(data.get('field_changes', []))}`。"
            )
        lines.append("")
    lines.extend([
        "## 证据范围",
        "",
        "`active_relations.<目标>.opinion` 保存了扫描到的意见字段和原始 `modifier` 值；"
        "国家块顶层 `prestige` 保存了行为者和目标国家的原始威望字段。"
        "报告按存档标签比较普通和轻蔑场景，保留字段变化与源路径，便于与运行时查询中的 "
        "`opinion_modifier_raw`、`actor_prestige_raw` 对照。",
        "",
        "某个字段在选定国家块或关系块中未出现，只说明本次有界扫描范围内没有找到该字段；"
        "报告不会把缺失字段扩展为整个存档或游戏规则层面的结论。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="append", required=True, type=Path,
                        help="save path; repeat for before/ordinary/scornful snapshots")
    parser.add_argument("--label", action="append", required=True,
                        help="label for each --save, in the same order")
    parser.add_argument("--recipient", required=True,
                        help="three-letter Insult target, excluding FRA")
    parser.add_argument("--actor", default=ACTOR,
                        help="three-letter actor; defaults FRA")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    if len(args.save) != len(args.label) or len(args.save) < 2:
        parser.error("supply at least two --save values and one matching --label per save")
    if not re.fullmatch(r"[A-Z]{3}", args.actor) or not re.fullmatch(r"[A-Z]{3}", args.recipient):
        parser.error("--actor and --recipient must be three uppercase ASCII letters")
    if args.actor == args.recipient:
        parser.error("--recipient must differ from --actor")
    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"output directory is not fresh: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(args.save, args.label, args.actor, args.recipient)
    evidence_path = output_dir / "evidence.json"
    report_path = output_dir / "report.md"
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "evidence": str(evidence_path),
        "report": str(report_path),
        "labels": payload["snapshot_labels"],
        "unknown_count": payload["integrity"]["unknown_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
