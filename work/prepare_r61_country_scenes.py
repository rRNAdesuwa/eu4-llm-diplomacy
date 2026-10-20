#!/usr/bin/env python3
"""从 R56 LEI 战争保存流式准备 R61 国家条款查询场景。

脚本只复制用户指定的 EU4txt 保存，并修改同一份 FRA→LEI active_war 的
真实 war goal，以及 diplomacy 顶层对应的 casus_belli 历史块。它不启动游戏，
不写入 DLL，不注入请求，也不声称新 CB 已经被引擎接受。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


SAVE_DIR = Path(
    r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games"
)
DEFAULT_SOURCE = SAVE_DIR / (
    "llm_diplomacy_peace_religion_small_ready_20261018_r56b.eu4"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "runtime" / (
    "r61-country-scenes-20261019-001"
)

EXPECTED_ATTACKER = "FRA"
EXPECTED_DEFENDER = "LEI"
EXPECTED_SOURCE_GOAL_KEY = "superiority"
EXPECTED_SOURCE_GOAL_TYPE = "superiority_world_crusade"
EXPECTED_SOURCE_CB = "cb_war_against_heresy"
# EU4 stores the definition-specific goal in the inner ``type`` field.
# The outer save block is always the common ``take_capital`` key.
OUTPUT_GOAL_KEY = "take_capital"
EXPECTED_CAPITAL = "374"
MAX_BLOCK_BYTES = 8 * 1024 * 1024
MAX_DIPLOMACY_BLOCK_BYTES = 1024 * 1024
MAX_RELATION_ROWS = 256

SCENES: dict[str, dict[str, str]] = {
    "vassalize": {
        "file_name": "llm_diplomacy_peace_country_vassalize_scene_20261019_r61a.eu4",
        "cb": "cb_vassalize_mission",
        "goal": "take_capital_vassalize",
    },
    "personal_union": {
        "file_name": "llm_diplomacy_peace_country_personal_union_scene_20261019_r61b.eu4",
        "cb": "cb_restore_personal_union",
        "goal": "take_capital_personal_union",
    },
}

ASSIGNMENT_RE = re.compile(
    rb"^\s*(?P<key>[A-Za-z0-9_]+)=(?P<value>\"[^\"]*\"|[^\s]+)(?P<tail>\s*(?:#.*)?)$"
)
BLOCK_RE = re.compile(rb"^\s*(?P<key>[A-Za-z0-9_]+)=\{")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def brace_delta(line: bytes) -> int:
    quoted = False
    escaped = False
    delta = 0
    for byte in line:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte == 123:
            delta += 1
        elif byte == 125:
            delta -= 1
    return delta


def stripped(line: bytes) -> bytes:
    return line.strip()


def parse_assignment(line: bytes) -> tuple[str, str] | None:
    match = ASSIGNMENT_RE.match(line.rstrip(b"\r\n"))
    if match is None:
        return None
    raw = match.group("value")
    if raw.startswith(b'"') and raw.endswith(b'"'):
        value = raw[1:-1].decode("utf-8", "replace")
    else:
        value = raw.decode("utf-8", "replace")
    return match.group("key").decode("ascii"), value


def replace_assignment(line: bytes, key: str, new_value: str) -> bytes:
    body = line.rstrip(b"\r\n")
    ending = line[len(body) :]
    match = ASSIGNMENT_RE.match(body)
    if match is None or match.group("key").decode("ascii") != key:
        raise ValueError(f"cannot replace {key!r} in {line!r}")
    old_literal = match.group("value")
    literal = (
        b'"' + new_value.encode("ascii") + b'"'
        if old_literal.startswith(b'"')
        else new_value.encode("ascii")
    )
    return body[: match.start("value")] + literal + body[match.end("value") :] + ending


def replace_block_key(line: bytes, old_key: str, new_key: str) -> bytes:
    body = line.rstrip(b"\r\n")
    ending = line[len(body) :]
    pattern = re.compile(
        rb"^(?P<prefix>\s*)" + re.escape(old_key.encode("ascii")) + rb"(?P<suffix>\s*=\s*\{)$"
    )
    match = pattern.match(body)
    if match is None:
        raise ValueError(f"cannot replace block key {old_key!r} in {line!r}")
    return match.group("prefix") + new_key.encode("ascii") + match.group("suffix") + ending


def line_ending(line: bytes) -> bytes:
    return b"\r\n" if line.endswith(b"\r\n") else b"\n"


def iter_block_lines(
    stream: Any,
    first_line: bytes,
    first_line_number: int,
    *,
    max_bytes: int,
) -> tuple[list[bytes], int]:
    block = [first_line]
    depth = brace_delta(first_line)
    size = len(first_line)
    line_number = first_line_number
    while depth > 0:
        line = stream.readline()
        if not line:
            raise ValueError(f"unterminated block at line {first_line_number}")
        line_number += 1
        size += len(line)
        if size > max_bytes:
            raise ValueError(
                f"block at line {first_line_number} exceeds bounded size {max_bytes}"
            )
        block.append(line)
        depth += brace_delta(line)
    if depth != 0:
        raise ValueError(f"unbalanced block at line {first_line_number}")
    return block, line_number


def lines_with_depth(block: list[bytes]):
    depth = 0
    for index, line in enumerate(block):
        before = depth
        depth += brace_delta(line)
        yield index, line, before, depth
    if depth != 0:
        raise ValueError("captured block is not balanced")


def fields_at_depth(
    block: list[bytes], depth_wanted: int, start: int = 0, end: int | None = None
) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    limit = len(block) if end is None else end
    for index, line, before, _after in lines_with_depth(block):
        if index < start or index >= limit or before != depth_wanted:
            continue
        assignment = parse_assignment(line)
        if assignment is not None:
            result.setdefault(assignment[0], (index, assignment[1]))
    return result


def child_blocks(block: list[bytes]) -> list[tuple[int, int, str]]:
    entries = list(lines_with_depth(block))
    result: list[tuple[int, int, str]] = []
    for index, line, before, _after in entries:
        if before != 1 or not stripped(line).endswith(b"={"):
            continue
        marker = stripped(line)[:-2].decode("ascii", "replace")
        end = None
        for candidate_index in range(index + 1, len(entries)):
            _candidate, _candidate_line, _candidate_before, candidate_after = entries[
                candidate_index
            ]
            if candidate_after == 1:
                end = candidate_index
                break
        if end is None:
            raise ValueError(f"unterminated child block {marker!r}")
        result.append((index, end, marker))
    return result


def _selected_fields(fields: dict[str, tuple[int, str]], names: set[str]) -> dict[str, str]:
    return {key: fields[key][1] for key in sorted(names) if key in fields}


def _context_hash(block: list[bytes], excluded_start: int, excluded_end: int) -> str:
    digest = hashlib.sha256()
    for index, line in enumerate(block):
        if excluded_start <= index <= excluded_end:
            continue
        digest.update(line)
    return digest.hexdigest()


def _active_context(block: list[bytes]) -> dict[str, Any]:
    top = fields_at_depth(block, 1)
    # ``tag`` also appears inside the peace-goal child (the transformed
    # ``take_capital`` block).  Participant membership is limited to the
    # direct ``participants`` records; collecting every depth>=2 tag would
    # therefore make a target LEI tag look like a new participant.
    tags: list[str] = []
    for child_start, child_end, child_key in child_blocks(block):
        if child_key != "participants":
            continue
        fields = fields_at_depth(block, 2, child_start + 1, child_end)
        value = fields.get("tag", (None, None))[1]
        if value is not None:
            tags.append(value)
    additions: list[str] = []
    for _index, line, before, _after in lines_with_depth(block):
        assignment = parse_assignment(line)
        if assignment is None:
            continue
        key, value = assignment
        if key in {"add_attacker", "add_defender"}:
            additions.append(f"{key}={value}")
    return {
        "original_attacker": top.get("original_attacker", (None, None))[1],
        "original_defender": top.get("original_defender", (None, None))[1],
        "action": top.get("action", (None, None))[1],
        "participant_tags": tags,
        "participant_additions": additions,
    }


def _active_goal_records(block: list[bytes], start_line: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for child_start, child_end, child_key in child_blocks(block):
        fields = fields_at_depth(block, 2, child_start + 1, child_end)
        if "type" not in fields or "casus_belli" not in fields:
            continue
        records.append(
            {
                "key": child_key,
                "start_index": child_start,
                "end_index": child_end,
                "start_line": start_line + child_start,
                "end_line": start_line + child_end,
                "type": fields["type"][1],
                "type_line": start_line + fields["type"][0],
                "province": fields.get("province", (None, None))[1],
                "tag": fields.get("tag", (None, None))[1],
                "casus_belli": fields["casus_belli"][1],
                "casus_belli_line": start_line + fields["casus_belli"][0],
                "fields": _selected_fields(
                    fields, {"type", "province", "tag", "casus_belli"}
                ),
            }
        )
    return records


def summarize_active_block(block: list[bytes], start_line: int) -> dict[str, Any]:
    top = fields_at_depth(block, 1)
    goals = _active_goal_records(block, start_line)
    target_goals = [
        goal
        for goal in goals
        if goal["type"] == EXPECTED_SOURCE_GOAL_TYPE
        and goal["casus_belli"] == EXPECTED_SOURCE_CB
    ]
    return {
        "start_line": start_line,
        "end_line": start_line + len(block) - 1,
        "roles": {
            "original_attacker": top.get("original_attacker", (None, None))[1],
            "original_defender": top.get("original_defender", (None, None))[1],
        },
        "context": _active_context(block),
        "goal_candidates": goals,
        "source_goal_candidates": target_goals,
        "balanced": True,
        "bytes": sum(len(line) for line in block),
        "invariant_sha256": (
            _context_hash(block, target_goals[0]["start_index"], target_goals[0]["end_index"])
            if len(target_goals) == 1
            else None
        ),
    }


def scan_active_wars(path: Path) -> dict[str, Any]:
    depth = 0
    line_count = 0
    blocks: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            line_count += 1
            before = depth
            if before == 0 and stripped(line) == b"active_war={":
                block, end_line = iter_block_lines(
                    stream, line, line_count, max_bytes=MAX_BLOCK_BYTES
                )
                blocks.append(summarize_active_block(block, line_count))
                line_count = end_line
                continue
            depth += brace_delta(line)
    target = [
        block
        for block in blocks
        if block["roles"]
        == {"original_attacker": EXPECTED_ATTACKER, "original_defender": EXPECTED_DEFENDER}
    ]
    return {
        "line_count": line_count,
        "active_war_blocks_seen": len(blocks),
        "target_count": len(target),
        "target": target[0] if len(target) == 1 else None,
        "non_target_invariants": [
            {
                "roles": block["roles"],
                "context": block["context"],
                "goal_candidates": block["goal_candidates"],
                "invariant_sha256": block["invariant_sha256"],
            }
            for block in blocks
            if block not in target
        ],
        "final_brace_depth": depth,
        "complete": depth == 0 and all(block["balanced"] for block in blocks),
    }


SUBJECT_BLOCK_KEYS = {
    "dependency",
    "union",
    "personal_union",
    "vassal",
    "overlord",
    "subject",
    "subject_relation",
    "junior_union",
}


def scan_diplomacy(path: Path) -> dict[str, Any]:
    depth = 0
    line_count = 0
    diplomacy_depth: int | None = None
    diplomacy_found = False
    diplomacy_complete = False
    block_counts: dict[str, int] = {}
    matching_cbs: list[dict[str, Any]] = []
    subject_rows: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            line_count += 1
            before = depth
            marker = stripped(line)
            if before == 0 and marker == b"diplomacy={":
                diplomacy_found = True
                diplomacy_depth = before + brace_delta(line)
            if diplomacy_depth is not None and before == diplomacy_depth:
                match = BLOCK_RE.match(line)
                if match:
                    key = match.group("key").decode("ascii", "replace")
                    if key == "casus_belli" or key in SUBJECT_BLOCK_KEYS:
                        block, end_line = iter_block_lines(
                            stream,
                            line,
                            line_count,
                            max_bytes=MAX_DIPLOMACY_BLOCK_BYTES,
                        )
                        block_counts[key] = block_counts.get(key, 0) + 1
                        fields = fields_at_depth(block, 1)
                        first = fields.get("first", (None, None))[1]
                        second = fields.get("second", (None, None))[1]
                        row = {
                            "block": key,
                            "line_start": line_count,
                            "line_end": end_line,
                            "first": first,
                            "second": second,
                            "fields": _selected_fields(
                                fields,
                                {
                                    "type",
                                    "first",
                                    "second",
                                    "start_date",
                                    "end_date",
                                    "subject_type",
                                },
                            ),
                        }
                        if key == "casus_belli" and first == EXPECTED_ATTACKER and second == EXPECTED_DEFENDER:
                            matching_cbs.append(row)
                        if (
                            key in SUBJECT_BLOCK_KEYS
                            and (first == EXPECTED_DEFENDER or second == EXPECTED_DEFENDER)
                        ):
                            if len(subject_rows) < MAX_RELATION_ROWS:
                                subject_rows.append(row)
                        line_count = end_line
                        continue
            depth += brace_delta(line)
            if (
                diplomacy_found
                and diplomacy_depth is not None
                and before >= diplomacy_depth
                and depth == 0
            ):
                diplomacy_complete = True
    return {
        "line_count": line_count,
        "diplomacy_found": diplomacy_found,
        "diplomacy_complete": diplomacy_complete,
        "final_brace_depth": depth,
        "block_counts": block_counts,
        "matching_casus_belli": matching_cbs,
        "subject_relations_involving_target": subject_rows,
        "subject_relation_rows_truncated": len(subject_rows) >= MAX_RELATION_ROWS,
        "complete": diplomacy_found
        and diplomacy_complete
        and depth == 0
        and len(subject_rows) < MAX_RELATION_ROWS,
    }


def scan_save_date(path: Path) -> str | None:
    consumed = 0
    with path.open("rb") as stream:
        while consumed < 1024 * 1024:
            line = stream.readline()
            if not line:
                break
            consumed += len(line)
            assignment = parse_assignment(line)
            if assignment is not None and assignment[0] in {"date", "save_date"}:
                return assignment[1]
    return None


def scan_country(path: Path) -> dict[str, Any]:
    depth = 0
    line_count = 0
    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    target: dict[str, Any] | None = None
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            line_count += 1
            before = depth
            marker = stripped(line)
            if before == 0 and marker == b"countries={":
                countries_found = True
                countries_depth = before + brace_delta(line)
            if (
                target is None
                and countries_depth is not None
                and before == countries_depth
                and marker == b"LEI={"
            ):
                block, end_line = iter_block_lines(
                    stream, line, line_count, max_bytes=MAX_BLOCK_BYTES
                )
                direct = fields_at_depth(block, 1)
                history = fields_at_depth(block, 2)
                target = {
                    "path": "countries/LEI",
                    "line_start": line_count,
                    "line_end": end_line,
                    "bytes": sum(len(item) for item in block),
                    "direct_fields": _selected_fields(
                        direct,
                        {
                            "government_rank",
                            "government_name",
                            "capital",
                            "religion",
                            "prestige",
                            "treasury",
                        },
                    ),
                    "history_fields": _selected_fields(
                        history, {"government", "religion", "capital"}
                    ),
                }
                line_count = end_line
                continue
            depth += brace_delta(line)
            if (
                countries_found
                and countries_depth is not None
                and depth == 0
                and before >= countries_depth
            ):
                countries_complete = True
    if target is None:
        raise ValueError("LEI country block not found in countries scope")
    direct = target["direct_fields"]
    history = target["history_fields"]
    religion = direct.get("religion")
    government_name = direct.get("government_name", history.get("government"))
    target["identity_checks"] = {
        "religion": religion,
        "religion_is_hussite_christian_fixture": religion == "hussite",
        "government_name": direct.get("government_name"),
        "government_history": history.get("government"),
        "government_is_monarchy": (
            "monarchy" in str(government_name or "")
            or history.get("government") == "monarchy"
        ),
        "capital": direct.get("capital", history.get("capital")),
    }
    return {
        "line_count": line_count,
        "countries_found": countries_found,
        "countries_complete": countries_complete,
        "final_brace_depth": depth,
        "target": target,
        "complete": countries_found and countries_complete and depth == 0,
    }


def _find_source_goal(summary: dict[str, Any]) -> dict[str, Any]:
    candidates = summary["source_goal_candidates"]
    if len(candidates) != 1:
        raise ValueError(
            f"expected one FRA/LEI source goal {EXPECTED_SOURCE_CB}, found {len(candidates)}"
        )
    goal = candidates[0]
    if goal["key"] != EXPECTED_SOURCE_GOAL_KEY:
        raise ValueError(
            f"expected source goal key {EXPECTED_SOURCE_GOAL_KEY}, found {goal['key']}"
        )
    return goal


def transform_active_block(
    block: list[bytes], start_line: int, scene: dict[str, str]
) -> tuple[list[bytes], dict[str, Any]]:
    before = summarize_active_block(block, start_line)
    goal = _find_source_goal(before)
    child_start = goal["start_index"]
    child_end = goal["end_index"]
    fields = fields_at_depth(block, 2, child_start + 1, child_end)
    transformed = list(block[child_start : child_end + 1])
    transformed[0] = replace_block_key(
        transformed[0], EXPECTED_SOURCE_GOAL_KEY, OUTPUT_GOAL_KEY
    )
    transformed[fields["type"][0] - child_start] = replace_assignment(
        transformed[fields["type"][0] - child_start], "type", scene["goal"]
    )
    cb_local = fields["casus_belli"][0] - child_start
    transformed[cb_local] = replace_assignment(
        transformed[cb_local], "casus_belli", scene["cb"]
    )
    insert_at = cb_local
    insertion_indent = transformed[cb_local][: len(transformed[cb_local]) - len(transformed[cb_local].lstrip(b" \t"))]
    ending = line_ending(transformed[cb_local])
    if "province" in fields:
        local = fields["province"][0] - child_start
        transformed[local] = replace_assignment(transformed[local], "province", EXPECTED_CAPITAL)
    else:
        transformed.insert(insert_at, insertion_indent + b"province=" + EXPECTED_CAPITAL.encode("ascii") + ending)
        insert_at += 1
    if "tag" in fields:
        local = fields["tag"][0] - child_start
        transformed[local] = replace_assignment(transformed[local], "tag", EXPECTED_DEFENDER)
    else:
        transformed.insert(insert_at, insertion_indent + b'tag="' + EXPECTED_DEFENDER.encode("ascii") + b'"' + ending)
    output = list(block[:child_start]) + transformed + list(block[child_end + 1 :])
    after = summarize_active_block(output, start_line)
    return output, {
        "selected": True,
        "before": {
            "goal_key": goal["key"],
            "goal_type": goal["type"],
            "province": goal["province"],
            "tag": goal["tag"],
            "casus_belli": goal["casus_belli"],
            "line_start": goal["start_line"],
            "line_end": goal["end_line"],
        },
        "after": {
            "goal_key": after["goal_candidates"][0]["key"],
            "goal_type": after["goal_candidates"][0]["type"],
            "province": after["goal_candidates"][0]["province"],
            "tag": after["goal_candidates"][0]["tag"],
            "casus_belli": after["goal_candidates"][0]["casus_belli"],
            "line_start": after["goal_candidates"][0]["start_line"],
            "line_end": after["goal_candidates"][0]["end_line"],
        },
        "invariant_sha256_before": before["invariant_sha256"],
        "invariant_sha256_after": after["invariant_sha256"],
        "roles_before": before["roles"],
        "roles_after": after["roles"],
        "context_before": before["context"],
        "context_after": after["context"],
    }


def transform_casus_belli_block(
    block: list[bytes], start_line: int, scene: dict[str, str]
) -> tuple[list[bytes], dict[str, Any]]:
    fields = fields_at_depth(block, 1)
    if fields.get("first", (None, None))[1] != EXPECTED_ATTACKER or fields.get("second", (None, None))[1] != EXPECTED_DEFENDER:
        return block, {"selected": False}
    if fields.get("type", (None, None))[1] != EXPECTED_SOURCE_CB:
        return block, {"selected": False}
    type_index = fields["type"][0]
    transformed = list(block)
    transformed[type_index] = replace_assignment(
        transformed[type_index], "type", scene["cb"]
    )
    return transformed, {
        "selected": True,
        "before": {
            "block": "casus_belli",
            "first": EXPECTED_ATTACKER,
            "second": EXPECTED_DEFENDER,
            "type": EXPECTED_SOURCE_CB,
            "fields": _selected_fields(fields, {"type", "first", "second", "start_date", "end_date"}),
            "line_start": start_line,
            "line_end": start_line + len(block) - 1,
        },
        "after": {
            "block": "casus_belli",
            "first": EXPECTED_ATTACKER,
            "second": EXPECTED_DEFENDER,
            "type": scene["cb"],
            "fields": {
                **_selected_fields(fields, {"first", "second", "start_date", "end_date"}),
                "type": scene["cb"],
            },
            "line_start": start_line,
            "line_end": start_line + len(block) - 1,
        },
    }


def rewrite_save(
    source: Path, destination: Path, scene: dict[str, str]
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite destination {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"refusing to reuse partial destination {partial}")
    depth = 0
    diplomacy_depth: int | None = None
    line_count = 0
    active_seen = 0
    active_transformed = 0
    cb_seen = 0
    cb_transformed = 0
    active_change: dict[str, Any] | None = None
    cb_change: dict[str, Any] | None = None
    try:
        with source.open("rb") as stream, partial.open("xb") as target:
            while True:
                line = stream.readline()
                if not line:
                    break
                line_count += 1
                before = depth
                marker = stripped(line)
                if before == 0 and marker == b"active_war={":
                    block, end_line = iter_block_lines(
                        stream, line, line_count, max_bytes=MAX_BLOCK_BYTES
                    )
                    active_seen += 1
                    summary = summarize_active_block(block, line_count)
                    if summary["roles"] == {
                        "original_attacker": EXPECTED_ATTACKER,
                        "original_defender": EXPECTED_DEFENDER,
                    }:
                        if active_change is not None:
                            raise ValueError("duplicate FRA/LEI active_war target")
                        transformed, info = transform_active_block(block, line_count, scene)
                        active_change = info
                        active_transformed += 1
                        target.write(b"".join(transformed))
                    else:
                        target.write(b"".join(block))
                    line_count = end_line
                    continue
                if before == 0 and marker == b"diplomacy={":
                    diplomacy_depth = before + brace_delta(line)
                if diplomacy_depth is not None and before == diplomacy_depth:
                    match = BLOCK_RE.match(line)
                    if match and match.group("key") == b"casus_belli":
                        block, end_line = iter_block_lines(
                            stream,
                            line,
                            line_count,
                            max_bytes=MAX_DIPLOMACY_BLOCK_BYTES,
                        )
                        cb_seen += 1
                        transformed, info = transform_casus_belli_block(
                            block, line_count, scene
                        )
                        if info.get("selected"):
                            if cb_change is not None:
                                raise ValueError("duplicate FRA/LEI history casus_belli target")
                            cb_change = info
                            cb_transformed += 1
                        target.write(b"".join(transformed))
                        line_count = end_line
                        continue
                target.write(line)
                depth += brace_delta(line)
        if depth != 0:
            raise ValueError(f"rewrite final brace depth is {depth}")
        if active_transformed != 1 or cb_transformed != 1:
            raise ValueError(
                f"expected one active_war and one history CB transform, got {active_transformed}/{cb_transformed}"
            )
        os.replace(partial, destination)
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise
    return {
        "line_count": line_count,
        "active_war_blocks_seen": active_seen,
        "active_war_blocks_transformed": active_transformed,
        "casus_belli_blocks_seen": cb_seen,
        "casus_belli_blocks_transformed": cb_transformed,
        "active_change": active_change,
        "history_cb_change": cb_change,
        "final_brace_depth": depth,
        "complete": depth == 0,
    }


def _non_target_invariants_equal(
    before: dict[str, Any], after: dict[str, Any]
) -> bool:
    return before["non_target_invariants"] == after["non_target_invariants"]


def source_contract(source: Path) -> dict[str, Any]:
    active = scan_active_wars(source)
    diplomacy = scan_diplomacy(source)
    country = scan_country(source)
    if not active["complete"] or not diplomacy["complete"] or not country["complete"]:
        raise ValueError("source stream scan is incomplete")
    if active["target_count"] != 1 or active["target"] is None:
        raise ValueError(f"expected one FRA/LEI active_war, found {active['target_count']}")
    if len(active["target"]["source_goal_candidates"]) != 1:
        raise ValueError("source FRA/LEI active_war goal is not unique")
    if len(diplomacy["matching_casus_belli"]) != 1:
        raise ValueError(
            "expected one FRA/LEI history casus_belli, found "
            f"{len(diplomacy['matching_casus_belli'])}"
        )
    if diplomacy["subject_relations_involving_target"]:
        raise ValueError(
            "LEI already has a serialized subject/union relation; PU scene was not produced"
        )
    identity = country["target"]["identity_checks"]
    if not identity["religion_is_hussite_christian_fixture"] or not identity["government_is_monarchy"]:
        raise ValueError(f"LEI is not the requested Christian monarchy fixture: {identity}")
    return {
        "active_war": active,
        "diplomacy": diplomacy,
        "country": country,
        "source_goal": active["target"]["source_goal_candidates"][0],
        "history_casus_belli": diplomacy["matching_casus_belli"][0],
        "no_existing_le_overlord_or_union": True,
    }


def verify_scene(
    source: Path,
    destination: Path,
    scene: dict[str, str],
    source_contract_data: dict[str, Any],
    rewrite_data: dict[str, Any],
) -> dict[str, Any]:
    active = scan_active_wars(destination)
    diplomacy = scan_diplomacy(destination)
    country = scan_country(destination)
    target = active["target"]
    goal = target["goal_candidates"][0] if target and target["goal_candidates"] else None
    history = diplomacy["matching_casus_belli"]
    source_active = source_contract_data["active_war"]
    source_diplomacy = source_contract_data["diplomacy"]
    source_target = source_active["target"]
    source_country = source_contract_data["country"]["target"]
    checks = {
        "destination_active_scan_complete": active["complete"],
        "destination_diplomacy_scan_complete": diplomacy["complete"],
        "destination_country_scan_complete": country["complete"],
        "one_active_war_transformed": active["target_count"] == 1,
        "roles_preserved": bool(target and target["roles"] == source_target["roles"]),
        "participants_preserved": bool(target and target["context"] == source_target["context"]),
        "target_goal_key_is_take_capital": bool(
            goal and goal["key"] == OUTPUT_GOAL_KEY
        ),
        "target_goal_type_verified": bool(goal and goal["type"] == scene["goal"]),
        "target_goal_province_verified": bool(goal and goal["province"] == EXPECTED_CAPITAL),
        "target_goal_tag_verified": bool(goal and goal["tag"] == EXPECTED_DEFENDER),
        "target_goal_cb_verified": bool(goal and goal["casus_belli"] == scene["cb"]),
        "non_target_active_wars_preserved": _non_target_invariants_equal(source_active, active),
        "one_history_cb_transformed": len(history) == 1,
        "history_cb_roles_preserved": bool(
            history
            and history[0]["fields"].get("first") == EXPECTED_ATTACKER
            and history[0]["fields"].get("second") == EXPECTED_DEFENDER
        ),
        "history_cb_verified": bool(
            history and history[0]["fields"].get("type") == scene["cb"]
        ),
        "history_cb_count_preserved": len(history) == len(source_diplomacy["matching_casus_belli"]),
        "subject_relations_unchanged": diplomacy["subject_relations_involving_target"]
        == source_diplomacy["subject_relations_involving_target"],
        "lei_identity_preserved": country["target"]["identity_checks"]
        == source_country["identity_checks"],
        "no_existing_lei_overlord_or_union": not diplomacy["subject_relations_involving_target"],
        "rewrite_stream_complete": rewrite_data["complete"],
    }
    return {
        "scene": scene,
        "output": {
            "path": str(destination),
            "name": destination.name,
            "size_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
        },
        "before": {
            "roles": source_target["roles"],
            "context": source_target["context"],
            "goal": source_target["goal_candidates"][0],
            "history_casus_belli": source_diplomacy["matching_casus_belli"][0],
        },
        "after": {
            "roles": target["roles"] if target else None,
            "context": target["context"] if target else None,
            "goal": goal,
            "history_casus_belli": history[0] if history else None,
        },
        "rewrite": rewrite_data,
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "streaming": {
            "full_save_loaded_into_memory": False,
            "copy_mode": "line-streaming bytes; bounded active_war/diplomacy blocks",
            "max_active_war_block_bytes": MAX_BLOCK_BYTES,
            "max_diplomacy_block_bytes": MAX_DIPLOMACY_BLOCK_BYTES,
            "sha256_recomputed_streaming": True,
        },
    }


def build_report(
    source: Path,
    source_contract_data: dict[str, Any],
    source_sha_before: str,
    source_sha_after: str,
    scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    source_active = source_contract_data["active_war"]["target"]
    source_dip = source_contract_data["diplomacy"]["matching_casus_belli"][0]
    source_country = source_contract_data["country"]["target"]
    checks = {
        "source_unchanged": source_sha_before == source_sha_after,
        "source_stream_complete": (
            source_contract_data["active_war"]["complete"]
            and source_contract_data["diplomacy"]["complete"]
            and source_contract_data["country"]["complete"]
        ),
        "source_roles_fra_attacks_lei": source_active["roles"]
        == {"original_attacker": EXPECTED_ATTACKER, "original_defender": EXPECTED_DEFENDER},
        "source_lei_christian_monarchy": source_country["identity_checks"][
            "religion_is_hussite_christian_fixture"
        ]
        and source_country["identity_checks"]["government_is_monarchy"],
        "source_has_no_lei_subject_or_pu_relation": source_contract_data[
            "no_existing_le_overlord_or_union"
        ],
        "source_history_cb_is_fra_to_lei": source_dip["fields"].get("first")
        == EXPECTED_ATTACKER
        and source_dip["fields"].get("second") == EXPECTED_DEFENDER,
        "all_scene_reports_passed": all(scene["status"] == "passed" for scene in scenes),
    }
    return {
        "schema": "r61-country-scenes-fixture-v1",
        "status": "passed" if all(checks.values()) else "failed",
        "operator_prepared_existing_war_context": True,
        "natural_declaration_or_cb_legality_claim": False,
        "source": {
            "path": str(source),
            "name": source.name,
            "size_bytes": source.stat().st_size,
            "save_date": scan_save_date(source_contract_data_path := source),
            "sha256_before": source_sha_before,
            "sha256_after": source_sha_after,
        },
        "roles": {
            "original_attacker": EXPECTED_ATTACKER,
            "original_defender": EXPECTED_DEFENDER,
            "target_country": EXPECTED_DEFENDER,
            "target_country_path": source_country["path"],
            "target_country_identity": source_country["identity_checks"],
            "capital_province": EXPECTED_CAPITAL,
            "existing_subject_relations_involving_lei": source_contract_data["diplomacy"][
                "subject_relations_involving_target"
            ],
        },
        "source_contract": source_contract_data,
        "scenes": scenes,
        "checks": checks,
        "scope_boundaries": [
            "Only FRA/LEI active_war goal fields and the direct FRA→LEI history casus_belli type are changed.",
            "FRA, LEI, participants, dates, country identity, and all other world state are preserved byte-for-byte outside the selected blocks.",
            "The output is an operator-prepared existing-war context; it does not prove that the game accepts either CB or war goal.",
            "No game, REA, RAM polling, request submission, save loading, or business execution was performed.",
        ],
    }


def scan_save_date_from_contract(path: Path) -> str | None:
    return scan_save_date(path)


def report_markdown(report: dict[str, Any]) -> str:
    source = report["source"]
    roles = report["roles"]
    lines = [
        "# R61 国家条款查询场景夹具",
        "",
        "本夹具从 R56 已存在的 FRA→LEI 暂停战争保存按字节流复制，只替换 active_war 的目标块和 diplomacy 中对应的 FRA→LEI casus_belli 类型。它用于后续原生查询，不表示游戏已经接受新的战争目标或 CB。",
        "",
        f"源档：`{source['path']}`；日期 `{source['save_date']}`；大小 `{source['size_bytes']}` 字节。",
        f"源档 SHA-256：`{source['sha256_before']}`；生成后源档 SHA-256：`{source['sha256_after']}`；源档未被修改：`{report['checks']['source_unchanged']}`。",
        f"原始角色：FRA 进攻 LEI；LEI 国家块路径 `{roles['target_country_path']}`；首都省份 `{roles['capital_province']}`。",
        f"LEI 身份字段：宗教 `{roles['target_country_identity']['religion']}`，政府名 `{roles['target_country_identity']['government_name']}`，政府历史 `{roles['target_country_identity']['government_history']}`；Christian monarchy 检查 `{report['checks']['source_lei_christian_monarchy']}`。",
        f"LEI 现有附属/共主关系记录：`{len(roles['existing_subject_relations_involving_lei'])}`；因此 PU 场景没有改写既有宗主关系。",
        "",
        "| 场景 | active_war goal | history casus_belli | 输出 SHA-256 | 状态 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for scene in report["scenes"]:
        before_goal = scene["before"]["goal"]
        after_goal = scene["after"]["goal"]
        before_cb = scene["before"]["history_casus_belli"]["fields"].get("type")
        after_cb = scene["after"]["history_casus_belli"]["fields"].get("type")
        lines.append(
            f"| `{scene['scene']['file_name']}` | `{before_goal['key']}/{before_goal['type']}` → `{after_goal['key']}/{after_goal['type']}`，province `{after_goal['province']}`，tag `{after_goal['tag']}` | `{before_cb}` → `{after_cb}`，FRA→LEI | `{scene['output']['sha256']}` | `{scene['status']} |"
        )
    lines.extend(
        [
            "",
            "每个输出都保留 FRA/LEI 参战者、战争日期、国家身份和其他 active_war；脚本只在有限大小的 active_war、diplomacy 子块中缓冲，整份保存没有进入内存。后续 root 应在新进程中查询候选，并由 native 决定这些准备好的 CB/war goal 是否可用。",
            "",
            f"总检查状态：`{report['status']}`。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--save-dir", type=Path, default=SAVE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--name-suffix",
        default="",
        help="追加到两个输出存档基本名的后缀；用于保留失败产物而生成纠正后的新保存。",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    save_dir = args.save_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not save_dir.is_dir():
        raise NotADirectoryError(save_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "fixture-manifest.json"
    report_path = output_dir / "report.json"
    report_md_path = output_dir / "report.md"
    for path in (manifest_path, report_path, report_md_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    scenes_to_build = []
    for scene in SCENES.values():
        scene_copy = dict(scene)
        if args.name_suffix:
            stem, suffix = os.path.splitext(scene_copy["file_name"])
            scene_copy["file_name"] = f"{stem}{args.name_suffix}{suffix}"
        scenes_to_build.append(scene_copy)

    for scene in scenes_to_build:
        destination = save_dir / scene["file_name"]
        if destination.exists() or destination.with_name(destination.name + ".partial").exists():
            raise FileExistsError(f"refusing to overwrite destination {destination}")

    source_sha_before = sha256_file(source)
    contract = source_contract(source)
    scenes: list[dict[str, Any]] = []
    for scene in scenes_to_build:
        destination = save_dir / scene["file_name"]
        rewrite_data = rewrite_save(source, destination, scene)
        scenes.append(verify_scene(source, destination, scene, contract, rewrite_data))
    source_sha_after = sha256_file(source)
    report = build_report(source, contract, source_sha_before, source_sha_after, scenes)
    report["source"]["save_date"] = scan_save_date_from_contract(source)
    report["output_directory"] = str(output_dir)
    report["generated_files"] = [scene["output"] for scene in scenes]
    manifest = {
        **report,
        "generated_by": "bounded streaming R61 country scene transformer",
        "source_sha256_recomputed_once_before_and_after": True,
        "no_backup_or_autosave_copy": True,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(report_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "source": str(source),
                "outputs": [scene["output"]["path"] for scene in scenes],
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
