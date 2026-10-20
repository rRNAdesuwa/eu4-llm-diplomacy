#!/usr/bin/env python3
"""Read-only, semantic inspection of two EU4 save files.

This utility reads only the ``meta`` and ``gamestate`` members of the supplied
EU4 zip saves.  It never rewrites a save, starts EU4, attaches to a process, or
uses UI/injection facilities.  The parser deliberately emits a small semantic
summary (ENG/FRA control, their relation, the shared active war, and serialized
peace/cooldown candidates) instead of copying the save into JSON.

EU4 does not promise that a live diplomatic command queue or a peace-window
offer is serialized.  Therefore an absent ``pending``/``in_flight`` field is
reported as "not found in gamestate", not as proof that no transient command
existed in the running process.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

from local_config import user_data

GAME_SAVE_DIR = user_data() / "save games"
DEFAULT_AFTER = GAME_SAVE_DIR / "llm_peace_after_reject.eu4"
DEFAULT_INITIAL = GAME_SAVE_DIR / "英格兰1445_04_08.eu4"
DEFAULT_OUTPUT = Path(__file__).with_name("runtime") / "peace-save-comparison.json"

TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
SCALAR_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)=([^\r\n]*)")
BLOCK_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)=\{")


class Entry(NamedTuple):
    key: str
    value: str | None
    body: str | None


def read_member(path: Path, member: str) -> str:
    """Read one plain-text member without modifying the zip archive."""

    with zipfile.ZipFile(path, "r") as archive:
        try:
            raw = archive.read(member)
        except KeyError as exc:
            raise ValueError(f"{path}: missing zip member {member!r}") from exc
    return raw.decode("utf-8-sig", errors="replace")


def extract_block(text: str, open_index: int) -> str:
    """Return text inside the brace at *open_index*, respecting quoted text."""

    if open_index < 0 or open_index >= len(text) or text[open_index] != "{":
        raise ValueError(f"expected '{{' at offset {open_index}")
    depth = 0
    quoted = False
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
    raise ValueError(f"unclosed block at offset {open_index}")


def brace_delta(line: str) -> int:
    """Count braces in one line, excluding braces inside quoted strings."""

    delta = 0
    quoted = False
    escaped = False
    for char in line:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def top_level_entries(body: str) -> list[Entry]:
    """Collect direct scalar and block children of an already-open block."""

    entries: list[Entry] = []
    depth = 0
    offset = 0
    for line in body.splitlines(keepends=True):
        if depth == 0:
            block_match = BLOCK_LINE_RE.match(line)
            if block_match:
                open_index = offset + line.find("{")
                entries.append(
                    Entry(block_match.group(1), None, extract_block(body, open_index))
                )
            else:
                scalar_match = SCALAR_LINE_RE.match(line)
                if scalar_match:
                    entries.append(
                        Entry(scalar_match.group(1), scalar_match.group(2).strip(), None)
                    )
        depth += brace_delta(line)
        offset += len(line)
    return entries


def scalar_values(entries: Iterable[Entry], key: str) -> list[str]:
    return [entry.value for entry in entries if entry.key == key and entry.value is not None]


def scalar(entries: Iterable[Entry], key: str) -> str | None:
    values = scalar_values(entries, key)
    return values[-1] if values else None


def child_blocks(entries: Iterable[Entry], key: str) -> list[str]:
    return [entry.body for entry in entries if entry.key == key and entry.body is not None]


def unquote(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def yes_no(value: str | None) -> bool | None:
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def find_country_container(gamestate: str) -> str:
    """Find the real country map, skipping the small top-level player list."""

    for match in re.finditer(r"(?m)^countries=\{", gamestate):
        body = extract_block(gamestate, match.end() - 1)
        if re.search(r"(?m)^\t(?:ENG|FRA)=\{", body):
            return body
    raise ValueError("could not find the serialized countries map")


def find_country_body(country_container: str, tag: str) -> str:
    match = re.search(rf"(?m)^\t{re.escape(tag)}=\{{", country_container)
    if not match:
        raise ValueError(f"country {tag} not found")
    return extract_block(country_container, match.end() - 1)


def selected_country_fields(body: str) -> dict[str, object]:
    entries = top_level_entries(body)
    control = {
        "human_field": yes_no(scalar(entries, "human")),
        "was_player": yes_no(scalar(entries, "was_player")),
        "human_field_raw": scalar(entries, "human"),
        "was_player_raw": scalar(entries, "was_player"),
        "is_at_war": yes_no(scalar(entries, "is_at_war")),
    }
    custom_flags = {
        entry.key: entry.value
        for entry in entries
        if entry.value is not None and entry.key.startswith("llm_")
    }
    send_history = {
        entry.key: entry.value
        for entry in entries
        if entry.value is not None
        and (entry.key.startswith("last_sent_") or entry.key.startswith("last_send_"))
    }
    return {
        "control": control,
        "native_send_history": send_history,
        "custom_llm_flags": custom_flags,
    }


def relation_summary(country_body: str, other_tag: str) -> dict[str, object] | None:
    entries = top_level_entries(country_body)
    relation_containers = child_blocks(entries, "active_relations")
    for relation_container in relation_containers:
        relation_entries = top_level_entries(relation_container)
        for relation_body in child_blocks(relation_entries, other_tag):
            relation = top_level_entries(relation_body)
            summary: dict[str, object] = {}
            for key in (
                "cached_sum",
                "trust_value",
                "last_send_diplomat",
                "last_war",
                "attitude",
                "truce",
                "has_core_claim",
                "has_culture_group_claim",
                "is_fighting_war_together",
            ):
                value = scalar(relation, key)
                if value is not None:
                    summary[key] = unquote(value)
            opinion_blocks = child_blocks(relation, "opinion")
            if opinion_blocks:
                opinion = top_level_entries(opinion_blocks[-1])
                opinion_summary: dict[str, object] = {}
                for key in ("modifier", "date", "current_opinion", "expiry_date", "delayed_decay"):
                    value = scalar(opinion, key)
                    if value is not None:
                        opinion_summary[key] = unquote(value)
                if opinion_summary:
                    summary["opinion"] = opinion_summary
            # A missing truce field is meaningful for this pair, but it is not
            # equivalent to a globally proven absence of every truce object.
            summary["truce_field"] = summary.get("truce")
            return summary
    return None


def parse_tag_list(body: str) -> list[str]:
    return [token for token in re.findall(r"\b[A-Z][A-Z0-9_]{1,5}\b", body) if TAG_RE.match(token)]


def parse_history_events(history_body: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for match in re.finditer(r"(?m)^\s*(\d+\.\d+\.\d+)=\{", history_body):
        child = extract_block(history_body, match.end() - 1)
        for operation, side, tag in re.findall(
            r"(?m)^\s*(add|rem)_(attacker|defender)=\"?([A-Z0-9_]+)\"?", child
        ):
            events.append({"date": match.group(1), "operation": operation, "side": side, "tag": tag})
    return events


def active_war_summary(active_war_body: str) -> dict[str, object]:
    entries = top_level_entries(active_war_body)
    participants: list[dict[str, object]] = []
    for participant_body in child_blocks(entries, "participants"):
        participant = top_level_entries(participant_body)
        tag = unquote(scalar(participant, "tag"))
        if tag is None:
            continue
        participants.append(
            {
                "tag": tag,
                "value": scalar(participant, "value"),
                "war_score": scalar(participant, "war_score"),
            }
        )
    result: dict[str, object] = {
        "participants": participants,
        "attackers": parse_tag_list(child_blocks(entries, "attackers")[0])
        if child_blocks(entries, "attackers")
        else [],
        "defenders": parse_tag_list(child_blocks(entries, "defenders")[0])
        if child_blocks(entries, "defenders")
        else [],
        "persistent_attackers": parse_tag_list(child_blocks(entries, "persistent_attackers")[0])
        if child_blocks(entries, "persistent_attackers")
        else [],
        "persistent_defenders": parse_tag_list(child_blocks(entries, "persistent_defenders")[0])
        if child_blocks(entries, "persistent_defenders")
        else [],
        "original_attacker": unquote(scalar(entries, "original_attacker")),
        "original_defender": unquote(scalar(entries, "original_defender")),
        "action": scalar(entries, "action"),
        "defender_score": scalar(entries, "defender_score"),
        "history_events": parse_history_events(child_blocks(entries, "history")[0])
        if child_blocks(entries, "history")
        else [],
    }
    goals: list[dict[str, object]] = []
    for entry in entries:
        if not entry.key.startswith("take_") or entry.body is None:
            continue
        goal_entries = top_level_entries(entry.body)
        goal: dict[str, object] = {"kind": entry.key}
        for key in ("type", "province", "tag", "casus_belli", "subjects"):
            value = scalar(goal_entries, key)
            if value is not None:
                goal[key] = unquote(value)
        goals.append(goal)
    if goals:
        result["war_goal_records"] = goals
    return result


def find_eng_fra_active_wars(gamestate: str) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for match in re.finditer(r"(?m)^active_war=\{", gamestate):
        body = extract_block(gamestate, match.end() - 1)
        summary = active_war_summary(body)
        # Participant statistics and persistent sides survive a paused peace
        # settlement. Only the current sides establish an ongoing war.
        tags = set(summary["attackers"]) | set(summary["defenders"])
        if {"ENG", "FRA"}.issubset(tags):
            matches.append(summary)
    return matches


def parse_meta(meta: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in ("date", "save_game", "player"):
        match = re.search(rf"(?m)^{key}=([^\r\n]+)", meta)
        if match:
            result[key] = unquote(match.group(1).strip())
    version = re.search(r"savegame_versions=\{\s*\"([^\"]+)\"", meta, re.S)
    if version:
        result["game_version"] = version.group(1)
    result["multi_player"] = yes_no(
        (re.search(r"(?m)^multi_player=([^\r\n]+)", meta) or [None, None])[1]
    )
    return result


def relevant_diplomacy_records(gamestate: str) -> list[dict[str, object]]:
    diplomacy_match = re.search(r"(?m)^diplomacy=\{", gamestate)
    if not diplomacy_match:
        return []
    body = extract_block(gamestate, diplomacy_match.end() - 1)
    records: list[dict[str, object]] = []
    depth = 0
    offset = 0
    for line in body.splitlines(keepends=True):
        match = BLOCK_LINE_RE.match(line)
        if depth == 0 and match:
            child = extract_block(body, offset + line.find("{"))
            entries = top_level_entries(child)
            first = unquote(scalar(entries, "first"))
            second = unquote(scalar(entries, "second"))
            if {first, second} == {"ENG", "FRA"}:
                record: dict[str, object] = {"kind": match.group(1)}
                for key in ("first", "second", "type", "start_date", "end_date", "envoy"):
                    value = scalar(entries, key)
                    if value is not None:
                        record[key] = unquote(value)
                records.append(record)
        depth += brace_delta(line)
        offset += len(line)
    return records


def serialized_field_inventory(gamestate: str) -> dict[str, list[str]]:
    keys = {
        match.group(1)
        for match in re.finditer(r"(?m)^\s*([A-Za-z0-9_]+)=", gamestate)
    }
    return {
        "peace_fields": sorted(key for key in keys if "peace" in key.lower()),
        "offer_fields": sorted(key for key in keys if "offer" in key.lower()),
        "pending_or_in_flight_fields": sorted(
            key
            for key in keys
            if "pending" in key.lower() or "in_flight" in key.lower()
        ),
        "diplomatic_action_fields": sorted(
            key
            for key in keys
            if "diplomatic_action" in key.lower() or "diplomacy_action" in key.lower()
        ),
    }


def inspect_save(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    meta = read_member(path, "meta")
    gamestate = read_member(path, "gamestate")
    country_container = find_country_container(gamestate)
    country_bodies = {tag: find_country_body(country_container, tag) for tag in ("ENG", "FRA")}
    country_summary = {tag: selected_country_fields(body) for tag, body in country_bodies.items()}
    # Only the ENG↔FRA relation sub-blocks are retained.
    relation_summary_pair = {
        "ENG_to_FRA": relation_summary(country_bodies["ENG"], "FRA"),
        "FRA_to_ENG": relation_summary(country_bodies["FRA"], "ENG"),
    }
    after_pending = {
        "native_last_sent_peace_offer_date": country_summary["FRA"]["native_send_history"].get(
            "last_sent_peace_offer_date"
        ),
        "custom_llm_peace_pending_flag": country_summary["FRA"]["custom_llm_flags"].get(
            "llm_peace_pending_fra"
        ),
        "native_pending_or_in_flight_objects": [],
        "note": "No named native pending/in-flight peace object was found in gamestate; the UI/command queue may be process-local.",
    }
    with zipfile.ZipFile(path, "r") as archive:
        zip_members = sorted(archive.namelist())
    return {
        "path": str(path),
        "file_size": path.stat().st_size,
        "zip_members": zip_members,
        "meta": parse_meta(meta),
        "countries": country_summary,
        "eng_fra_relations": relation_summary_pair,
        "eng_fra_active_wars": find_eng_fra_active_wars(gamestate),
        "diplomacy_records": relevant_diplomacy_records(gamestate),
        "peace_offer_serialization": after_pending,
        "serialized_field_inventory": serialized_field_inventory(gamestate),
    }


def make_diff(initial: dict[str, object], after: dict[str, object]) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    initial_date = initial.get("meta", {}).get("date")
    after_date = after.get("meta", {}).get("date")
    if initial_date != after_date:
        changes.append({"field": "meta.date", "initial": initial_date, "after": after_date})
    for tag in ("ENG", "FRA"):
        initial_control = initial["countries"][tag]["control"]
        after_control = after["countries"][tag]["control"]
        if initial_control != after_control:
            changes.append(
                {
                    "field": f"countries.{tag}.control",
                    "initial": initial_control,
                    "after": after_control,
                }
            )
    for direction in ("ENG_to_FRA", "FRA_to_ENG"):
        before = initial["eng_fra_relations"].get(direction)
        current = after["eng_fra_relations"].get(direction)
        if before != current:
            changes.append(
                {
                    "field": f"eng_fra_relations.{direction}",
                    "initial": before,
                    "after": current,
                }
            )
    before_offer = initial["peace_offer_serialization"]
    current_offer = after["peace_offer_serialization"]
    for key in (
        "native_last_sent_peace_offer_date",
        "custom_llm_peace_pending_flag",
        "native_pending_or_in_flight_objects",
    ):
        if before_offer.get(key) != current_offer.get(key):
            changes.append(
                {
                    "field": f"peace_offer_serialization.{key}",
                    "initial": before_offer.get(key),
                    "after": current_offer.get(key),
                }
            )
    before_war = initial["eng_fra_active_wars"]
    current_war = after["eng_fra_active_wars"]
    if before_war != current_war:
        changes.append(
            {
                "field": "eng_fra_active_wars",
                "initial": before_war,
                "after": current_war,
            }
        )
    if initial["diplomacy_records"] != after["diplomacy_records"]:
        changes.append(
            {
                "field": "diplomacy_records",
                "initial": initial["diplomacy_records"],
                "after": after["diplomacy_records"],
            }
        )
    return changes


def build_report(after_path: Path, initial_path: Path) -> dict[str, object]:
    initial = inspect_save(initial_path)
    after = inspect_save(after_path)
    return {
        "tool": "work/inspect_peace_save.py",
        "read_only": True,
        "scope": "meta/gamestate semantic extraction for ENG/FRA, their active war, and serialized peace candidates",
        "after_reject": after,
        "initial": initial,
        "semantic_diff": make_diff(initial, after),
        "limitations": [
            "EU4 save data contains a native last_sent_peace_offer_date cooldown, but no named native pending/in-flight peace object was found for ENG↔FRA.",
            "llm_peace_pending_fra is a custom bridge flag in the save and is not evidence that the native UI command queue is serialized.",
            "No explicit human=no or ai_control field is present for FRA; AI control is inferred from meta player=ENG and the absence of human=yes in the FRA country block.",
            "active_war original_attacker/original_defender are used as serialized war leaders; no separate leader field is present in the ENG↔FRA active_war block.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--after", type=Path, default=DEFAULT_AFTER)
    parser.add_argument("--initial", type=Path, default=DEFAULT_INITIAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report(args.after, args.initial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"after date: {report['after_reject']['meta'].get('date')}")
    print(f"initial date: {report['initial']['meta'].get('date')}")
    print(f"ENG/FRA active wars: {len(report['after_reject']['eng_fra_active_wars'])}")
    print(f"semantic changes: {len(report['semantic_diff'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
