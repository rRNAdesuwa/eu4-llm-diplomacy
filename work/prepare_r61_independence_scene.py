#!/usr/bin/env python3
"""从 R60b 既有 FRA--ENG 战争流式准备 Grant Independence 场景。

这个工具只修改 EU4 文本保存中的一个 active_war、对应的 FRA->ENG
casus_belli，以及顶层 diplomacy 中新增的 ENG->FRA vassal dependency。它
不会启动游戏、注入请求或宣称原生合法性；目标是给后续原生查询提供明确
的操作员准备背景。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from work.prepare_r61_country_scenes import (
        BLOCK_RE,
        MAX_BLOCK_BYTES,
        brace_delta,
        child_blocks,
        fields_at_depth,
        iter_block_lines,
        line_ending,
        parse_assignment,
        replace_assignment,
        replace_block_key,
        stripped,
    )
except ModuleNotFoundError:  # direct execution from a copied work directory
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work.prepare_r61_country_scenes import (
        BLOCK_RE,
        MAX_BLOCK_BYTES,
        brace_delta,
        child_blocks,
        fields_at_depth,
        iter_block_lines,
        line_ending,
        parse_assignment,
        replace_assignment,
        replace_block_key,
        stripped,
    )


SAVE_DIR = Path(
    r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games"
)
DEFAULT_SOURCE = Path(__file__).resolve().parent / "runtime" / (
    "r60-subject-transfer-scene-20261019-002"
) / "llm_diplomacy_peace_utr_trade_subject_scene_20261019_r60b.eu4"
DEFAULT_OUTPUT = SAVE_DIR / (
    "llm_diplomacy_peace_country_independence_scene_20261019_r61c.eu4"
)
DEFAULT_RUNTIME = Path(__file__).resolve().parent / "runtime" / (
    "r61-independence-scene-20261019-001"
)

ATTACKER = "FRA"
DEFENDER = "ENG"
SOURCE_GOAL_KEY = "take_core"
SOURCE_GOAL_TYPE = "take_core"
SOURCE_CB = "cb_core"
TARGET_GOAL_KEY = "defend_capital"
TARGET_GOAL_TYPE = "defend_capital_independence"
TARGET_CB = "cb_independence_war"
SUBJECT_TEMPLATE_FIRST = "ENG"
SUBJECT_TEMPLATE_SECOND = "TYR"
SUBJECT_DATE = "1452.2.2"  # copied from the existing ENG->TYR vassal block
SUBJECT_TYPE = "vassal"
SUBJECT_KEYS = {
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
    "dependency",
}
MAX_DIPLOMACY_BLOCK_BYTES = 4 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def selected(fields: dict[str, tuple[int, str]], names: set[str]) -> dict[str, str]:
    return {key: fields[key][1] for key in sorted(names) if key in fields}


def context_hash(
    block: list[bytes],
    excluded_start: int,
    excluded_end: int,
    *,
    ignored_direct_fields: set[str] | None = None,
) -> str:
    ignored_indices: set[int] = set()
    if ignored_direct_fields:
        direct = fields_at_depth(block, 1)
        ignored_indices = {
            fields[0]
            for key, fields in direct.items()
            if key in ignored_direct_fields
        }
    digest = hashlib.sha256()
    for index, line in enumerate(block):
        if (excluded_start <= index <= excluded_end) or index in ignored_indices:
            continue
        digest.update(line)
    return digest.hexdigest()


def active_context(block: list[bytes]) -> dict[str, Any]:
    top = fields_at_depth(block, 1)
    tags: list[str] = []
    for child_start, child_end, child_key in child_blocks(block):
        if child_key != "participants":
            continue
        child_fields = fields_at_depth(block, 2, child_start + 1, child_end)
        tag = child_fields.get("tag", (None, None))[1]
        if tag is not None:
            tags.append(tag)
    additions: list[str] = []
    for _index, line in enumerate(block):
        assignment = parse_assignment(line)
        if assignment is not None and assignment[0] in {
            "add_attacker",
            "add_defender",
        }:
            additions.append(f"{assignment[0]}={assignment[1]}")
    return {
        "original_attacker": top.get("original_attacker", (None, None))[1],
        "original_defender": top.get("original_defender", (None, None))[1],
        "action": top.get("action", (None, None))[1],
        "participant_tags": tags,
        "participant_additions": additions,
    }


def goal_records(block: list[bytes], start_line: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for child_start, child_end, child_key in child_blocks(block):
        fields = fields_at_depth(block, 2, child_start + 1, child_end)
        if "type" not in fields or "casus_belli" not in fields:
            continue
        record = {
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
            "fields": selected(fields, {"type", "province", "tag", "casus_belli"}),
        }
        records.append(record)
    return records


def summarize_active(block: list[bytes], start_line: int) -> dict[str, Any]:
    top = fields_at_depth(block, 1)
    goals = goal_records(block, start_line)
    return {
        "start_line": start_line,
        "end_line": start_line + len(block) - 1,
        "roles": {
            "original_attacker": top.get("original_attacker", (None, None))[1],
            "original_defender": top.get("original_defender", (None, None))[1],
        },
        "direct_fields": {
            "subject_type": top.get("subject_type", (None, None))[1],
            "subject_type_scope": "active_war_direct",
        },
        "context": active_context(block),
        "goal_candidates": goals,
        "balanced": True,
        "bytes": sum(len(line) for line in block),
        "invariant_sha256": (
            context_hash(
                block,
                goals[0]["start_index"],
                goals[0]["end_index"],
                # R61 adds the explicitly requested active_war direct field;
                # keep the non-goal invariant comparable while checking the
                # field and its scope separately below.
                ignored_direct_fields={"subject_type"},
            )
            if len(goals) == 1
            else None
        ),
    }


def non_direct_subject_type_occurrences(block: list[bytes]) -> list[tuple[int, str]]:
    """Capture subject_type assignments outside active_war's direct layer."""

    direct = fields_at_depth(block, 1)
    direct_indices = {
        fields[0] for key, fields in direct.items() if key == "subject_type"
    }
    occurrences: list[tuple[int, str]] = []
    for index, line in enumerate(block):
        assignment = parse_assignment(line)
        if assignment is not None and assignment[0] == "subject_type" and index not in direct_indices:
            occurrences.append((index, assignment[1]))
    return occurrences


def ensure_active_war_subject_type(
    block: list[bytes],
) -> tuple[list[bytes], dict[str, Any]]:
    """Set only active_war's direct subject_type field to vassal.

    The line is inserted immediately before the active_war closing brace, so
    it cannot become a participant, goal, or country field.  An unexpected
    existing direct value is rejected rather than silently repurposed.
    """

    direct = fields_at_depth(block, 1)
    existing = direct.get("subject_type")
    if existing is not None:
        if existing[1] != SUBJECT_TYPE:
            raise ValueError(
                "active_war direct subject_type has unexpected value "
                f"{existing[1]!r}"
            )
        return list(block), {
            "scope": "active_war_direct",
            "before": existing[1],
            "after": existing[1],
            "line_index": existing[0],
            "inserted": False,
        }
    if len(block) < 2 or stripped(block[-1]) != b"}":
        raise ValueError("active_war block has no bounded closing line")
    indent = b"\t"
    if direct:
        first_index = min(fields[0] for fields in direct.values())
        direct_line = block[first_index]
        indent = direct_line[: len(direct_line) - len(direct_line.lstrip())]
        if not indent:
            indent = b"\t"
    subject_line = (
        indent + b'subject_type="' + SUBJECT_TYPE.encode("ascii") + b'"'
        + line_ending(block[-1])
    )
    output = list(block[:-1]) + [subject_line, block[-1]]
    after_direct = fields_at_depth(output, 1)
    after = after_direct.get("subject_type")
    if after is None or after[1] != SUBJECT_TYPE:
        raise ValueError("failed to add active_war direct subject_type")
    return output, {
        "scope": "active_war_direct",
        "before": None,
        "after": after[1],
        "line_index": after[0],
        "inserted": True,
    }


def goal_semantics(goal: dict[str, Any]) -> dict[str, Any]:
    """Return goal content without line offsets, which move after insertion."""

    return {
        "key": goal.get("key"),
        "type": goal.get("type"),
        "province": goal.get("province"),
        "tag": goal.get("tag"),
        "casus_belli": goal.get("casus_belli"),
        "fields": goal.get("fields", {}),
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
                blocks.append(summarize_active(block, line_count))
                line_count = end_line
                continue
            depth += brace_delta(line)
    target = [
        item
        for item in blocks
        if item["roles"]
        == {"original_attacker": ATTACKER, "original_defender": DEFENDER}
    ]
    non_target = [
        {
            "roles": item["roles"],
            "context": item["context"],
            "goal_candidates": [
                goal_semantics(goal) for goal in item["goal_candidates"]
            ],
            "invariant_sha256": item["invariant_sha256"],
        }
        for item in blocks
        if item not in target
    ]
    return {
        "line_count": line_count,
        "active_war_blocks_seen": len(blocks),
        "target_count": len(target),
        "target": target[0] if len(target) == 1 else None,
        "non_target_invariants": non_target,
        "final_brace_depth": depth,
        "complete": depth == 0 and all(item["balanced"] for item in blocks),
    }


def scan_diplomacy(path: Path) -> dict[str, Any]:
    depth = 0
    line_count = 0
    diplomacy_found = False
    diplomacy_complete = False
    diplomacy_depth: int | None = None
    target_cbs: list[dict[str, Any]] = []
    target_pair_cbs: list[dict[str, Any]] = []
    subject_rows: list[dict[str, Any]] = []
    block_counts: dict[str, int] = {}
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
            if diplomacy_found and before == diplomacy_depth:
                match = BLOCK_RE.match(line)
                if match:
                    key = match.group("key").decode("ascii", "replace")
                    if key == "casus_belli" or key in SUBJECT_KEYS:
                        block, end_line = iter_block_lines(
                            stream,
                            line,
                            line_count,
                            max_bytes=MAX_DIPLOMACY_BLOCK_BYTES,
                        )
                        line_count = end_line
                        block_counts[key] = block_counts.get(key, 0) + 1
                        fields = fields_at_depth(block, 1)
                        first = fields.get("first", (None, None))[1]
                        second = fields.get("second", (None, None))[1]
                        if key == "casus_belli":
                            row = {
                                "block": key,
                                "line_start": line_count - len(block) + 1,
                                "line_end": line_count,
                                "first": first,
                                "second": second,
                                "fields": selected(
                                    fields,
                                    {
                                        "type",
                                        "first",
                                        "second",
                                        "start_date",
                                        "end_date",
                                    },
                                ),
                            }
                            if first == ATTACKER and second == DEFENDER:
                                target_cbs.append(row)
                            if {first, second} & {ATTACKER, DEFENDER}:
                                target_pair_cbs.append(row)
                        elif first is not None and second is not None:
                            subject_rows.append(
                                {
                                    "block": key,
                                    "line_start": line_count - len(block) + 1,
                                    "line_end": line_count,
                                    "first": first,
                                    "second": second,
                                    "subject_type": fields.get(
                                        "subject_type", (None, None)
                                    )[1],
                                    "fields": selected(
                                        fields,
                                        {
                                            "first",
                                            "second",
                                            "start_date",
                                            "end_date",
                                            "subject_type",
                                        },
                                    ),
                                }
                            )
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
        "matching_casus_belli": target_cbs,
        "target_pair_casus_belli": target_pair_cbs,
        "subject_relations": subject_rows,
        "complete": diplomacy_found and diplomacy_complete and depth == 0,
    }


def scan_country(path: Path, tag: str = ATTACKER) -> dict[str, Any]:
    depth = 0
    line_count = 0
    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    target: dict[str, Any] | None = None
    marker = (tag + "={").encode("ascii")
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            line_count += 1
            before = depth
            stripped_line = stripped(line)
            if before == 0 and stripped_line == b"countries={":
                countries_found = True
                countries_depth = before + brace_delta(line)
            if (
                target is None
                and countries_depth is not None
                and before == countries_depth
                and stripped_line == marker
            ):
                block, end_line = iter_block_lines(
                    stream, line, line_count, max_bytes=MAX_BLOCK_BYTES
                )
                direct = fields_at_depth(block, 1)
                history = fields_at_depth(block, 2)
                target = {
                    "path": f"countries/{tag}",
                    "line_start": line_count,
                    "line_end": end_line,
                    "bytes": sum(len(item) for item in block),
                    "direct_fields": selected(
                        direct,
                        {
                            "capital",
                            "government_name",
                            "government_rank",
                            "religion",
                            "treasury",
                        },
                    ),
                    "history_fields": selected(
                        history, {"capital", "government", "religion"}
                    ),
                }
                line_count = end_line
                continue
            depth += brace_delta(line)
            if (
                countries_found
                and countries_depth is not None
                and before >= countries_depth
                and depth == 0
            ):
                countries_complete = True
    if target is None:
        raise ValueError(f"{tag} country block not found in countries scope")
    direct = target["direct_fields"]
    history = target["history_fields"]
    target["identity"] = {
        "capital": direct.get("capital") or history.get("capital"),
        "religion": direct.get("religion") or history.get("religion"),
        "government_name": direct.get("government_name"),
        "government_history": history.get("government"),
        "treasury": direct.get("treasury"),
    }
    return {
        "line_count": line_count,
        "countries_found": countries_found,
        "countries_complete": countries_complete,
        "final_brace_depth": depth,
        "target": target,
        "complete": countries_found and countries_complete and depth == 0,
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


def graph_has_path(rows: list[dict[str, Any]], source: str, target: str) -> list[str] | None:
    graph: dict[str, set[str]] = {}
    for row in rows:
        first = row.get("first")
        second = row.get("second")
        if first and second:
            graph.setdefault(first, set()).add(second)
    stack: list[tuple[str, list[str]]] = [(source, [source])]
    visited: set[str] = set()
    while stack:
        node, path = stack.pop()
        if node == target:
            return path
        if node in visited:
            continue
        visited.add(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt not in visited:
                stack.append((nxt, path + [nxt]))
    return None


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_contract(source: Path) -> dict[str, Any]:
    active = scan_active_wars(source)
    diplomacy = scan_diplomacy(source)
    country = scan_country(source, ATTACKER)
    if not active["complete"] or active["target_count"] != 1:
        raise ValueError("source must have exactly one complete FRA->ENG active_war")
    if not diplomacy["complete"]:
        raise ValueError("source diplomacy scan is incomplete")
    if not country["complete"]:
        raise ValueError("source FRA country scan is incomplete")
    active_target = active["target"]
    goals = [
        goal
        for goal in active_target["goal_candidates"]
        if goal["key"] == SOURCE_GOAL_KEY
        and goal["type"] == SOURCE_GOAL_TYPE
        and goal["casus_belli"] == SOURCE_CB
    ]
    if len(goals) != 1:
        raise ValueError(f"expected one source take_core/cb_core goal, found {len(goals)}")
    matching = [
        row
        for row in diplomacy["matching_casus_belli"]
        if row["fields"].get("type") == SOURCE_CB
    ]
    if len(matching) != 1:
        raise ValueError(f"expected one FRA->ENG cb_core, found {len(matching)}")
    subject_rows = diplomacy["subject_relations"]
    fra_as_subject = [row for row in subject_rows if row["second"] == ATTACKER]
    eng_fra = [
        row
        for row in subject_rows
        if row["first"] == DEFENDER and row["second"] == ATTACKER
    ]
    if fra_as_subject:
        raise ValueError(f"FRA already has an overlord relation: {fra_as_subject}")
    if eng_fra:
        raise ValueError(f"ENG->FRA subject relation already exists: {eng_fra}")
    cycle_path = graph_has_path(subject_rows, ATTACKER, DEFENDER)
    if cycle_path is not None:
        raise ValueError(f"ENG->FRA would create a subject cycle via {cycle_path}")
    template = [
        row
        for row in subject_rows
        if row["block"] == "dependency"
        and row["first"] == SUBJECT_TEMPLATE_FIRST
        and row["second"] == SUBJECT_TEMPLATE_SECOND
        and row.get("subject_type") == SUBJECT_TYPE
    ]
    if len(template) != 1:
        raise ValueError(f"expected one ENG->TYR vassal template, found {len(template)}")
    capital = country["target"]["identity"].get("capital")
    if not capital or not capital.isdigit():
        raise ValueError(f"FRA direct capital is not readable: {capital!r}")
    return {
        "active_war": active,
        "diplomacy": diplomacy,
        "country": country,
        "source_goal": goals[0],
        "source_casus_belli": matching[0],
        "dependency_template": template[0],
        "cycle_path_fra_to_eng": cycle_path,
        "fra_has_existing_overlord": bool(fra_as_subject),
        "eng_fra_subject_exists": bool(eng_fra),
        "fra_capital": capital,
    }


def transform_active(
    block: list[bytes], start_line: int, fra_capital: str
) -> tuple[list[bytes], dict[str, Any]]:
    before = summarize_active(block, start_line)
    non_direct_subject_before = non_direct_subject_type_occurrences(block)
    goals = [
        goal
        for goal in before["goal_candidates"]
        if goal["key"] == SOURCE_GOAL_KEY
        and goal["type"] == SOURCE_GOAL_TYPE
        and goal["casus_belli"] == SOURCE_CB
    ]
    if len(goals) != 1:
        raise ValueError(f"target active_war source goal count is {len(goals)}")
    goal = goals[0]
    child_start = goal["start_index"]
    child_end = goal["end_index"]
    fields = fields_at_depth(block, 2, child_start + 1, child_end)
    transformed = list(block[child_start : child_end + 1])
    transformed[0] = replace_block_key(
        transformed[0], SOURCE_GOAL_KEY, TARGET_GOAL_KEY
    )
    transformed[fields["type"][0] - child_start] = replace_assignment(
        transformed[fields["type"][0] - child_start], "type", TARGET_GOAL_TYPE
    )
    transformed[fields["province"][0] - child_start] = replace_assignment(
        transformed[fields["province"][0] - child_start], "province", fra_capital
    )
    transformed[fields["casus_belli"][0] - child_start] = replace_assignment(
        transformed[fields["casus_belli"][0] - child_start], "casus_belli", TARGET_CB
    )
    output = list(block[:child_start]) + transformed + list(block[child_end + 1 :])
    output, subject_type_rewrite = ensure_active_war_subject_type(output)
    non_direct_subject_after = non_direct_subject_type_occurrences(output)
    after = summarize_active(output, start_line)
    target_after = [
        item for item in after["goal_candidates"] if item["key"] == TARGET_GOAL_KEY
    ]
    if len(target_after) != 1:
        raise ValueError("transformed active_war target goal was not readable")
    if non_direct_subject_before != non_direct_subject_after:
        raise ValueError(
            "active_war transformation changed a nested subject_type field"
        )
    if after["direct_fields"]["subject_type"] != SUBJECT_TYPE:
        raise ValueError("active_war direct subject_type is not vassal after rewrite")
    return output, {
        "selected": True,
        "before": {
            "key": goal["key"],
            "type": goal["type"],
            "province": goal["province"],
            "casus_belli": goal["casus_belli"],
            "line_start": goal["start_line"],
            "line_end": goal["end_line"],
        },
        "after": {
            "key": target_after[0]["key"],
            "type": target_after[0]["type"],
            "province": target_after[0]["province"],
            "casus_belli": target_after[0]["casus_belli"],
            "line_start": target_after[0]["start_line"],
            "line_end": target_after[0]["end_line"],
        },
        "roles_before": before["roles"],
        "roles_after": after["roles"],
        "context_before": before["context"],
        "context_after": after["context"],
        "subject_type": {
            **subject_type_rewrite,
            "non_direct_before": non_direct_subject_before,
            "non_direct_after": non_direct_subject_after,
            "non_direct_unchanged": True,
        },
        "invariant_sha256_before": before["invariant_sha256"],
        "invariant_sha256_after": after["invariant_sha256"],
    }


def mutate_dependency(block: list[bytes]) -> tuple[list[bytes], dict[str, str]]:
    fields = fields_at_depth(block, 1)
    if fields.get("first", (None, None))[1] != SUBJECT_TEMPLATE_FIRST:
        raise ValueError("dependency template first is not ENG")
    if fields.get("second", (None, None))[1] != SUBJECT_TEMPLATE_SECOND:
        raise ValueError("dependency template second is not TYR")
    if fields.get("subject_type", (None, None))[1] != SUBJECT_TYPE:
        raise ValueError("dependency template is not vassal")
    transformed = list(block)
    index = fields["second"][0]
    transformed[index] = replace_assignment(transformed[index], "second", ATTACKER)
    return transformed, {
        "first": SUBJECT_TEMPLATE_FIRST,
        "second_before": SUBJECT_TEMPLATE_SECOND,
        "second_after": ATTACKER,
        "start_date": fields.get("start_date", (None, SUBJECT_DATE))[1],
        "subject_type": fields["subject_type"][1],
    }


def transform_diplomacy(
    block: list[bytes], start_line: int
) -> tuple[list[bytes], dict[str, Any]]:
    children = child_blocks(block)
    cb_candidates: list[tuple[int, int]] = []
    template_children: list[tuple[int, int]] = []
    child_fields: dict[tuple[int, int], dict[str, tuple[int, str]]] = {}
    for child_start, child_end, key in children:
        fields = fields_at_depth(block, 2 if key == "casus_belli" else 2, child_start + 1, child_end)
        child_fields[(child_start, child_end)] = fields
        if key == "casus_belli":
            if (
                fields.get("first", (None, None))[1] == ATTACKER
                and fields.get("second", (None, None))[1] == DEFENDER
                and fields.get("type", (None, None))[1] == SOURCE_CB
            ):
                cb_candidates.append((child_start, child_end))
        if (
            key == "dependency"
            and fields.get("first", (None, None))[1] == SUBJECT_TEMPLATE_FIRST
            and fields.get("second", (None, None))[1] == SUBJECT_TEMPLATE_SECOND
            and fields.get("subject_type", (None, None))[1] == SUBJECT_TYPE
        ):
            template_children.append((child_start, child_end))
    if len(cb_candidates) != 1:
        raise ValueError(f"FRA->ENG cb_core block count in rewrite is {len(cb_candidates)}")
    if len(template_children) != 1:
        raise ValueError(f"ENG->TYR vassal template count in rewrite is {len(template_children)}")
    cb_span = cb_candidates[0]
    template_span = template_children[0]
    cb_fields = child_fields[cb_span]
    transformed_cb = list(block[cb_span[0] : cb_span[1] + 1])
    type_local = cb_fields["type"][0] - cb_span[0]
    transformed_cb[type_local] = replace_assignment(
        transformed_cb[type_local], "type", TARGET_CB
    )
    transformed_template, dependency_mutation = mutate_dependency(
        list(block[template_span[0] : template_span[1] + 1])
    )
    output: list[bytes] = []
    cursor = 0
    for child_start, child_end, key in children:
        output.extend(block[cursor:child_start])
        if (child_start, child_end) == cb_span:
            output.extend(transformed_cb)
        else:
            output.extend(block[child_start : child_end + 1])
        if (child_start, child_end) == template_span:
            output.extend(transformed_template)
        cursor = child_end + 1
    output.extend(block[cursor:])
    return output, {
        "history_cb": {
            "before": {
                "first": ATTACKER,
                "second": DEFENDER,
                "type": SOURCE_CB,
                "line_start": start_line + cb_span[0],
                "line_end": start_line + cb_span[1],
                "fields": selected(
                    cb_fields, {"first", "second", "type", "start_date", "end_date"}
                ),
            },
            "after": {
                "first": ATTACKER,
                "second": DEFENDER,
                "type": TARGET_CB,
                "line_start": start_line + cb_span[0],
                "line_end": start_line + cb_span[1],
            },
        },
        "new_dependency": {
            "line_after_template": start_line + template_span[1],
            "first": SUBJECT_TEMPLATE_FIRST,
            "second": ATTACKER,
            "subject_type": SUBJECT_TYPE,
            "start_date": dependency_mutation["start_date"],
            "template_first": SUBJECT_TEMPLATE_FIRST,
            "template_second": SUBJECT_TEMPLATE_SECOND,
        },
    }


class HashingWriter:
    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes_written = 0
        self.lines_written = 0

    def write(self, data: bytes) -> None:
        self.stream.write(data)
        self.digest.update(data)
        self.bytes_written += len(data)
        self.lines_written += data.count(b"\n")


def rewrite_save(
    source: Path, destination: Path, fra_capital: str
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"refusing to overwrite {partial}")
    depth = 0
    line_count = 0
    active_count = 0
    diplomacy_count = 0
    active_rewrite: dict[str, Any] | None = None
    diplomacy_rewrite: dict[str, Any] | None = None
    try:
        with source.open("rb") as stream, partial.open("xb") as output_stream:
            writer = HashingWriter(output_stream)
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
                    summary = summarize_active(block, line_count)
                    if summary["roles"] == {
                        "original_attacker": ATTACKER,
                        "original_defender": DEFENDER,
                    }:
                        active_count += 1
                        transformed, active_rewrite = transform_active(
                            block, line_count, fra_capital
                        )
                        writer.write(b"".join(transformed))
                    else:
                        writer.write(b"".join(block))
                    line_count = end_line
                    continue
                if before == 0 and marker == b"diplomacy={":
                    block, end_line = iter_block_lines(
                        stream,
                        line,
                        line_count,
                        max_bytes=MAX_DIPLOMACY_BLOCK_BYTES,
                    )
                    diplomacy_count += 1
                    transformed, diplomacy_rewrite = transform_diplomacy(
                        block, line_count
                    )
                    writer.write(b"".join(transformed))
                    line_count = end_line
                    continue
                writer.write(line)
                depth += brace_delta(line)
        if active_count != 1 or diplomacy_count != 1:
            raise ValueError(
                f"rewrite found active_war={active_count}, diplomacy={diplomacy_count}"
            )
        os.replace(partial, destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    return {
        "size_bytes": destination.stat().st_size,
        "sha256": writer.digest.hexdigest(),
        "line_count": writer.lines_written,
        "active_war": active_rewrite,
        "diplomacy": diplomacy_rewrite,
    }


def relation_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("block"),
        row.get("first"),
        row.get("second"),
        row.get("subject_type"),
        canonical(row.get("fields", {})),
    )


def verify_scene(
    source: Path,
    destination: Path,
    contract: dict[str, Any],
    rewrite: dict[str, Any],
) -> dict[str, Any]:
    before_active = contract["active_war"]
    before_dip = contract["diplomacy"]
    before_country = contract["country"]
    after_active = scan_active_wars(destination)
    after_dip = scan_diplomacy(destination)
    after_country = scan_country(destination, ATTACKER)
    before_target = before_active["target"]
    after_target = after_active["target"]
    before_goal = contract["source_goal"]
    after_goals = [
        goal
        for goal in (after_target or {}).get("goal_candidates", [])
        if goal["key"] == TARGET_GOAL_KEY
    ]
    after_cb = [
        row
        for row in after_dip["matching_casus_belli"]
        if row["fields"].get("type") == TARGET_CB
    ]
    new_subjects = [
        row
        for row in after_dip["subject_relations"]
        if row["block"] == "dependency"
        and row["first"] == DEFENDER
        and row["second"] == ATTACKER
        and row.get("subject_type") == SUBJECT_TYPE
    ]
    source_relations = sorted(
        relation_signature(row) for row in before_dip["subject_relations"]
    )
    filtered_after = [
        row for row in after_dip["subject_relations"] if row not in new_subjects
    ]
    after_existing_relations = sorted(relation_signature(row) for row in filtered_after)
    checks = {
        "source_active_scan_complete": before_active["complete"],
        "source_diplomacy_scan_complete": before_dip["complete"],
        "source_country_scan_complete": before_country["complete"],
        "destination_active_scan_complete": after_active["complete"],
        "destination_diplomacy_scan_complete": after_dip["complete"],
        "destination_country_scan_complete": after_country["complete"],
        "source_sha_stable": sha256_file(source) == contract["source_sha256_before"],
        "one_target_active_war": after_active["target_count"] == 1,
        "roles_preserved": bool(after_target)
        and after_target["roles"] == before_target["roles"]
        == {"original_attacker": ATTACKER, "original_defender": DEFENDER},
        "active_war_direct_subject_type_vassal": bool(after_target)
        and after_target.get("direct_fields", {}).get("subject_type")
        == SUBJECT_TYPE,
        "active_war_subject_type_scope_direct": bool(after_target)
        and after_target.get("direct_fields", {}).get("subject_type_scope")
        == "active_war_direct",
        "active_war_nested_subject_types_unchanged": rewrite["active_war"][
            "subject_type"
        ]["non_direct_unchanged"],
        "participants_preserved": bool(after_target)
        and after_target["context"]["participant_tags"]
        == before_target["context"]["participant_tags"]
        and after_target["context"]["participant_additions"]
        == before_target["context"]["participant_additions"],
        "target_goal_verified": len(after_goals) == 1
        and after_goals[0]["type"] == TARGET_GOAL_TYPE
        and after_goals[0]["casus_belli"] == TARGET_CB
        and after_goals[0]["province"] == contract["fra_capital"],
        "active_non_goal_context_preserved": (
            rewrite["active_war"]["invariant_sha256_before"]
            == rewrite["active_war"]["invariant_sha256_after"]
        ),
        "non_target_active_wars_preserved": canonical(
            before_active["non_target_invariants"]
        )
        == canonical(after_active["non_target_invariants"]),
        "one_history_cb_transformed": len(after_cb) == 1,
        "history_cb_roles_preserved": bool(after_cb)
        and after_cb[0]["first"] == ATTACKER
        and after_cb[0]["second"] == DEFENDER,
        "subject_relations_unchanged_except_new": source_relations
        == after_existing_relations,
        "new_eng_fra_vassal_exactly_one": len(new_subjects) == 1,
        "new_dependency_date_before_war": bool(new_subjects)
        and new_subjects[0]["fields"].get("start_date") < before_target["context"]["action"],
        "fra_identity_preserved": after_country["target"]["identity"]
        == before_country["target"]["identity"],
        "fra_capital_is_real_root_country_field": after_country["target"][
            "identity"
        ]["capital"]
        == contract["fra_capital"],
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "source": {
            "path": str(source),
            "size_bytes": source.stat().st_size,
            "sha256": contract["source_sha256_before"],
        },
        "output": {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "sha256": rewrite["sha256"],
        },
        "before": {
            "active_war": before_target,
            "history_casus_belli": contract["source_casus_belli"],
            "fra_country": before_country["target"],
            "subject_relations": before_dip["subject_relations"],
        },
        "after": {
            "active_war": after_target,
            "history_casus_belli": after_cb,
            "fra_country": after_country["target"],
            "subject_relations": after_dip["subject_relations"],
        },
        "rewrite": rewrite,
        "streaming": {
            "source_scan_complete": before_active["complete"]
            and before_dip["complete"]
            and before_country["complete"],
            "destination_scan_complete": after_active["complete"]
            and after_dip["complete"]
            and after_country["complete"],
        },
    }


def report_markdown(report: dict[str, Any]) -> str:
    scene = report["scene"]
    checks = report["checks"]
    failed = [key for key, value in checks.items() if not value]
    lines = [
        "# R61 Grant Independence 场景",
        "",
        "这是操作员准备的 EU4 文本保存背景，未启动游戏、未注入业务请求，不能单独证明原生 CB 已载入或合法。",
        "",
        f"- 源：`{report['source']['path']}`，日期 `{report['source']['save_date']}`，SHA-256 `{report['source']['sha256']}`。",
        f"- 新保存：`{report['output']['path']}`，SHA-256 `{report['output']['sha256']}`。",
        f"- 角色：FRA 原攻击方，ENG 原防守方；FRA 首都省 `{report['roles']['fra_capital']}`。",
        "",
        "## 精确变更",
        "",
        f"- active_war：外层目标键 ` {scene['active_war']['before']['key']} ` / 内部 type ` {scene['active_war']['before']['type']} `、`{scene['active_war']['before']['casus_belli']}` → 外层键 `defend_capital`、内部 type `defend_capital_independence`、`cb_independence_war`，province 改为 FRA 真实首都。",
        "- active_war 直接层新增 `subject_type=\"vassal\"`；转换器验证该字段位于 active_war 直接层，并核对参与者、目标块和国家块没有被写入该字段。",
        "- diplomacy：仅将 FRA→ENG 的历史 `casus_belli` 类型改为 `cb_independence_war`。",
        "- diplomacy：复制既有 ENG→TYR `subject_type=vassal` 块，新增 ENG→FRA `subject_type=vassal`，沿用源 start_date 1452.2.2，早于战争 1455.5.1；其它附属关系保留。",
        "",
        f"检查状态：`{report['status']}`；通过 {sum(checks.values())}/{len(checks)}。",
    ]
    if failed:
        lines.append(f"失败检查：{', '.join(failed)}。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    # Keep the historical full-path option for existing 001/r61c invocations.
    # New fixtures can instead choose a directory and a filename independently.
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="historical explicit output path; cannot be combined with --output-dir/--save-name",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"directory for a new save (default: {DEFAULT_OUTPUT.parent})",
    )
    parser.add_argument(
        "--save-name",
        default=None,
        help=f"new save filename (default: {DEFAULT_OUTPUT.name})",
    )
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    source = args.source.resolve()
    if args.output is not None:
        if args.output_dir is not None or args.save_name is not None:
            parser.error("--output cannot be combined with --output-dir or --save-name")
        destination = args.output.resolve()
    else:
        output_dir = (args.output_dir or DEFAULT_OUTPUT.parent).resolve()
        save_name = args.save_name or DEFAULT_OUTPUT.name
        save_path = Path(save_name)
        if (
            not save_name
            or save_path.name != save_name
            or save_name in {".", ".."}
        ):
            parser.error("--save-name must be a single non-empty filename")
        destination = (output_dir / save_path).resolve()
    runtime = args.runtime.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() or destination.with_name(destination.name + ".partial").exists():
        raise FileExistsError(f"refusing to overwrite output {destination}")
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "report.md", "fixture-manifest.json"):
        if (runtime / name).exists():
            raise FileExistsError(f"refusing to overwrite {runtime / name}")
    source_sha_before = sha256_file(source)
    contract = source_contract(source)
    contract["source_sha256_before"] = source_sha_before
    rewrite = rewrite_save(source, destination, contract["fra_capital"])
    source_sha_after = sha256_file(source)
    contract["source_sha256_after"] = source_sha_after
    scene = verify_scene(source, destination, contract, rewrite)
    report = {
        "schema": "r61_independence_scene_v1",
        "status": scene["status"],
        "checks": scene["checks"],
        "source": {
            "path": str(source),
            "name": source.name,
            "size_bytes": source.stat().st_size,
            "save_date": scan_save_date(source),
            "sha256": source_sha_before,
            "sha256_after": source_sha_after,
        },
        "output": scene["output"],
        "scene": scene["rewrite"],
        "roles": {
            "original_attacker": ATTACKER,
            "original_defender": DEFENDER,
            "independence_subject": ATTACKER,
            "independence_overlord": DEFENDER,
            "fra_capital": contract["fra_capital"],
        },
        "source_contract": {
            "active_war": contract["active_war"],
            "diplomacy": contract["diplomacy"],
            "fra_country": contract["country"]["target"],
            "source_goal": contract["source_goal"],
            "source_casus_belli": contract["source_casus_belli"],
            "dependency_template": contract["dependency_template"],
            "fra_has_existing_overlord": contract["fra_has_existing_overlord"],
            "eng_fra_subject_exists": contract["eng_fra_subject_exists"],
            "cycle_path_fra_to_eng": contract["cycle_path_fra_to_eng"],
        },
        "before": scene["before"],
        "after": scene["after"],
        "streaming": scene["streaming"],
        "operator_prepared_fixture_only": True,
        "engine_loaded": False,
        "legality_proven": False,
    }
    report["checks"]["source_sha_unchanged_after_write"] = source_sha_before == source_sha_after
    report["status"] = "passed" if all(report["checks"].values()) else "failed"
    report["generated_files"] = [str(destination)]
    manifest = {
        **report,
        "generated_by": "bounded streaming R61 independence scene transformer",
        "no_backup_or_autosave_copy": True,
    }
    (runtime / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (runtime / "fixture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (runtime / "report.md").write_text(report_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "source": str(source),
                "output": str(destination),
                "report": str(runtime / "report.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
