"""Verify the R74 live-war query against the bounded R70 save snapshot.

The save is evidence for the serialized war identity, sides, target province,
and goal-control state.  It is not used to infer the native score algorithm or
to decode the native tooltip.  The optional query report is joined by the
opaque native ``war_id`` and session/query identity supplied by the native
inspection event; the save itself has no such opaque id.

This checker reads the plain/zip gamestate through the existing streaming
active-war and province scanners.  It keeps only the FRA--BUR war and target
province 88, and never hashes, rewrites, or loads the complete save.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work import verify_r67_ally_save as save_scan
from work.inspect_declare_war_save_pair import scan_active_wars


EXPECTED_SHA256 = (
    "ffa91dbd2a2d544b18d586a895bb9b0c2b90e94ece47b2c74507555b8f58c2e0"
)
EXPECTED_ACTOR = "FRA"
EXPECTED_RECIPIENT = "BUR"
EXPECTED_GOAL_PROVINCE = "88"
MAX_QUERY_REPORT_BYTES = 16 * 1024 * 1024
MAX_TOOLTIP_HEX_BYTES = 2 * 8192
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")


def _load_json(path: Path, *, max_bytes: int = MAX_QUERY_REPORT_BYTES) -> Any:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.stat().st_size > max_bytes:
        raise ValueError(f"JSON_INPUT_OVER_LIMIT:{resolved}:{max_bytes}")
    return json.loads(resolved.read_text(encoding="utf-8-sig"))


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return _scalar(value[-1]) if value else None
    text = str(value).strip()
    return bounded.unquote(text) if text else None


def _jsonable(value: Any) -> Any:
    """Keep report values bounded and JSON serializable."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _read_save_metadata(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"date": None, "player": None}
    with bounded.open_gamestate(path, source) as stream:
        for index, line in enumerate(stream):
            if index >= 32:
                break
            date_match = re.match(r"^\s*date\s*=\s*(.*?)\s*$", line)
            player_match = re.match(r"^\s*player\s*=\s*(.*?)\s*$", line)
            if date_match and metadata["date"] is None:
                metadata["date"] = _scalar(date_match.group(1))
            if player_match and metadata["player"] is None:
                metadata["player"] = _scalar(player_match.group(1))
    return metadata


def _scan_target_province(
    path: Path, source: dict[str, Any], province_id: int
) -> dict[str, Any]:
    scanner = save_scan.ProvinceScanner((province_id,))
    with bounded.open_gamestate(path, source) as stream:
        for line in stream:
            scanner.consume_line(line)
    return scanner.finish()


def _goal_from_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("serialized_fields", {})
    goal_records = record.get("war_goal_records", [])
    selected: dict[str, Any] = {}
    selected_kind: str | None = None
    for item in goal_records:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", ""))
        if kind == "take_province" or selected_kind is None:
            selected_kind = kind or selected_kind
            selected = item.get("fields", {}) if isinstance(item.get("fields"), dict) else {}
        if kind == "take_province":
            break
    if not selected:
        selected = {
            key.split(".", 1)[1]: value
            for key, value in fields.items()
            if key.startswith("take_province.")
        }
        selected_kind = "take_province" if selected else None
    return {
        "kind": selected_kind,
        "fields_raw": _jsonable(selected),
        "casus_belli": _scalar(selected.get("casus_belli")),
        "type": _scalar(selected.get("type")),
        "province": _scalar(selected.get("province")),
        "subjects": _scalar(selected.get("subjects")),
        "present_in_save": bool(selected),
    }


def _participant_summary(record: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in record.get("participants", []):
        if not isinstance(item, dict):
            continue
        tag = _scalar(item.get("tag"))
        if not tag or TAG_RE.fullmatch(tag) is None:
            continue
        fields = item.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        result.append({
            "tag": tag,
            "value_text": _scalar(fields.get("value")),
            "war_score_text": _scalar(fields.get("war_score")),
            "promised_land": _scalar(fields.get("promised_land")),
        })
    return result


def _war_summary(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("serialized_fields", {})
    original = record.get("original_sides", {})
    current = record.get("current_sides", {})
    return {
        "line_start": record.get("line_start"),
        "line_end": record.get("line_end"),
        "bytes_captured": record.get("bytes_captured"),
        "pair_currently_active": record.get("pair_currently_active"),
        "original_sides": {
            "attacker": original.get("original_attacker"),
            "defender": original.get("original_defender"),
        },
        "current_sides": {
            "attackers": list(current.get("attackers", [])),
            "defenders": list(current.get("defenders", [])),
            "persistent_attackers": list(current.get("persistent_attackers", [])),
            "persistent_defenders": list(current.get("persistent_defenders", [])),
        },
        "action": fields.get("action"),
        "war_name_raw": record.get("name", {}).get("raw"),
        "war_name_utf8_hex": record.get("name", {}).get("utf8_hex"),
        "goal": _goal_from_record(record),
        "serialized_score_fields": {
            "defender_score_text": fields.get("defender_score"),
            "attacker_score_text": fields.get("attacker_score"),
            "war_score_text": fields.get("war_score"),
            "stalled_years_text": fields.get("stalled_years"),
            "participant_war_score_text": {
                key: value for key, value in fields.items()
                if "participant" in key and key.endswith(".war_score")
            },
            "scale_verified": False,
            "interpretation": "serialized_decimal_text_only",
        },
        "participants": _participant_summary(record),
        "tooltip_save_components": {
            "goal_fields": _jsonable(record.get("war_goal_records", [])),
            "action": fields.get("action"),
            "defender_score": fields.get("defender_score"),
            "sides": {
                "attackers": list(current.get("attackers", [])),
                "defenders": list(current.get("defenders", [])),
            },
            "participant_values": [
                {"tag": row["tag"], "value_text": row["value_text"]}
                for row in _participant_summary(record)
            ],
            "participant_war_scores": [
                {"tag": row["tag"], "war_score_text": row["war_score_text"]}
                for row in _participant_summary(record)
            ],
            "save_proves_textual_components_only": True,
        },
    }


def _iter_event_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("event") == "native_live_war_score_inspection":
            yield value
        live = value.get("live_war_score")
        if isinstance(live, dict):
            yield from _iter_event_dicts(live)
        for child in value.values():
            if child is live:
                continue
            yield from _iter_event_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_event_dicts(child)


def _event_from_jsonl(path: Path) -> list[dict[str, Any]]:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.stat().st_size > MAX_QUERY_REPORT_BYTES:
        raise ValueError(f"JSONL_INPUT_OVER_LIMIT:{resolved}:{MAX_QUERY_REPORT_BYTES}")
    result: list[dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            value = json.loads(line)
            result.extend(_iter_event_dicts(value))
    return result


def _load_query_events(path: Path) -> list[dict[str, Any]]:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.suffix.casefold() == ".jsonl":
        events = _event_from_jsonl(resolved)
        references: list[Path] = []
    else:
        document = _load_json(resolved)
        events = list(_iter_event_dicts(document))
        references = []
        if isinstance(document, dict):
            for case in document.get("cases", []):
                if not isinstance(case, dict):
                    continue
                candidate = case.get("native_events_path")
                if isinstance(candidate, str) and candidate:
                    reference = Path(candidate)
                    if not reference.is_absolute():
                        reference = resolved.parent / reference
                    references.append(reference)
    for reference in references:
        if reference.exists():
            events.extend(_event_from_jsonl(reference) if reference.suffix.casefold() == ".jsonl"
                           else list(_iter_event_dicts(_load_json(reference))))
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for event in events:
        key = (
            event.get("query_id"), event.get("actor"), event.get("recipient"),
            event.get("war_id"), event.get("date_raw"),
        )
        unique[key] = event
    return list(unique.values())


def _tooltip_summary(event: dict[str, Any]) -> dict[str, Any]:
    tooltip = event.get("tooltip")
    if not isinstance(tooltip, dict):
        score = event.get("score")
        tooltip = score.get("tooltip", {}) if isinstance(score, dict) else {}
    result = {
        key: tooltip.get(key)
        for key in (
            "requested", "text_readable", "text_truncated", "text_size",
            "string_capacity", "codec", "complete",
        )
        if key in tooltip
    }
    text_hex = tooltip.get("text_hex")
    if isinstance(text_hex, str) and len(text_hex) <= MAX_TOOLTIP_HEX_BYTES:
        result["text_hex"] = text_hex
        result["text_hex_sha256"] = hashlib.sha256(
            text_hex.encode("ascii", "replace")).hexdigest()
        result["text_decoded"] = None
    elif text_hex is not None:
        result["text_hex_omitted"] = True
    return result


def _query_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    score = event.get("score")
    if not isinstance(score, dict):
        score = {}
    goal = score.get("goal")
    if not isinstance(goal, dict):
        goal = {}
    total_keys = (
        "total_raw", "total_available", "total_complete", "total_unit",
        "total_scale", "max_score_raw", "max_score_scale",
        "overview_goal_cap_raw", "overview_goal_cap_scale", "scale_verified",
    )
    score_summary = {key: score.get(key) for key in total_keys if key in score}
    score_summary["goal"] = {
        key: goal.get(key)
        for key in (
            "called", "return_is_out_pointer", "out_written", "presence",
            "presence_verified", "present", "inapplicable", "available",
            "cumulative_raw", "cumulative_unit", "cumulative_scale", "complete",
        )
        if key in goal
    }
    score_summary["tooltip"] = _tooltip_summary(event)
    return {
        "event": event.get("event"),
        "family": event.get("family"),
        "action_id": event.get("action_id"),
        "phase": event.get("phase"),
        "actor": event.get("actor"),
        "recipient": event.get("recipient"),
        "date_raw": event.get("date_raw"),
        "query_id": event.get("query_id"),
        "session_id": event.get("session_id"),
        "war_id": event.get("war_id"),
        "war_context": _jsonable(event.get("war_context", {})),
        "score": score_summary,
        "native_calls": _jsonable(event.get("native_calls", {})),
        "verification": _jsonable(event.get("verification", {})),
        "error": event.get("error"),
    }


def _query_binding(
    events: list[dict[str, Any]], war: dict[str, Any], province: dict[str, Any]
) -> dict[str, Any]:
    selected = [
        event for event in events
        if event.get("actor") in {EXPECTED_ACTOR, EXPECTED_RECIPIENT}
        and event.get("recipient") in {EXPECTED_ACTOR, EXPECTED_RECIPIENT}
        and event.get("actor") != event.get("recipient")
    ]
    summaries = [_query_event_summary(event) for event in selected]
    current = war.get("current_sides", {})
    attackers = set(current.get("attackers", []))
    defenders = set(current.get("defenders", []))
    target_controller = province.get("controller")
    control_side = (
        "attacker" if target_controller in attackers else
        "defender" if target_controller in defenders else "unknown"
    )
    direction_rows: list[dict[str, Any]] = []
    for event, summary in zip(selected, summaries):
        score = summary.get("score", {})
        goal = score.get("goal", {})
        actor = event.get("actor")
        actor_side = (
            "attacker" if actor in attackers else
            "defender" if actor in defenders else "unknown"
        )
        native_context = event.get("war_context")
        if not isinstance(native_context, dict):
            native_context = {}
        raw = goal.get("cumulative_raw")
        direction_rows.append({
            "actor": actor,
            "recipient": event.get("recipient"),
            "actor_side_from_save": actor_side,
            "native_actor_side": native_context.get("actor_side"),
            "native_recipient_side": native_context.get("recipient_side"),
            "native_sides_opposite": native_context.get("actor_recipient_opposite"),
            "goal_cumulative_raw": raw,
            "goal_cumulative_scale": goal.get("cumulative_scale"),
            "goal_presence": goal.get("presence"),
            "goal_present": goal.get("present"),
            "sign_observed": (
                "negative" if isinstance(raw, (int, float)) and raw < 0 else
                "positive" if isinstance(raw, (int, float)) and raw > 0 else
                "zero_or_unreadable"
            ),
            "tooltip_text_decoded": False,
        })
    ids = {event.get("war_id") for event in selected if event.get("war_id")}
    pair = {
        (event.get("actor"), event.get("recipient"))
        for event in selected
    }
    forward = next((row for row in direction_rows
                    if row["actor"] == EXPECTED_ACTOR
                    and row["recipient"] == EXPECTED_RECIPIENT), None)
    reverse = next((row for row in direction_rows
                    if row["actor"] == EXPECTED_RECIPIENT
                    and row["recipient"] == EXPECTED_ACTOR), None)
    direction_observed = {
        "save_goal_control_side": control_side,
        "native_forward": forward,
        "native_reverse": reverse,
        "formula_inferred": False,
        "interpretation": (
            "The save fixes the target controller and sides; native goal signs "
            "are recorded as observations. No total-score or tooltip formula "
            "is reconstructed here."
        ),
    }
    checks = {
        "query_events_found": bool(selected),
        "one_opaque_war_id": len(ids) == 1,
        "query_pair_directions_present": {
            (EXPECTED_ACTOR, EXPECTED_RECIPIENT),
            (EXPECTED_RECIPIENT, EXPECTED_ACTOR),
        }.issubset(pair),
        "query_context_matches_saved_sides": all(
            row["actor_side_from_save"] in {"attacker", "defender"}
            and row.get("native_actor_side") in {"side_a", "side_b"}
            and row.get("native_recipient_side") in {"side_a", "side_b"}
            and row.get("native_actor_side") != row.get("native_recipient_side")
            and row.get("native_sides_opposite") is True
            for row in direction_rows
        ),
        "goal_direction_observed": (
            isinstance(forward, dict) and isinstance(reverse, dict)
            and forward.get("goal_present") is True
            and reverse.get("goal_present") is True
            and isinstance(forward.get("goal_cumulative_raw"), (int, float))
            and isinstance(reverse.get("goal_cumulative_raw"), (int, float))
            and forward["goal_cumulative_raw"] < 0
            and reverse["goal_cumulative_raw"] > 0
            and control_side == "defender"
        ),
        "tooltip_metadata_complete": all(
            row.get("score", {}).get("tooltip", {}).get("complete") is True
            and row.get("score", {}).get("tooltip", {}).get("text_truncated") is False
            for row in summaries
        ) if summaries else False,
    }
    return {
        "supplied": True,
        "event_count": len(selected),
        "opaque_war_ids": sorted(str(item) for item in ids),
        "save_opaque_war_id_match": "unavailable_save_has_no_native_id",
        "events": summaries,
        "direction_observation": direction_observed,
        "checks": checks,
    }


def _resolve_save(args: argparse.Namespace) -> tuple[Path, dict[str, Any] | None]:
    report: dict[str, Any] | None = None
    if args.save_report:
        report = _load_json(args.save_report)
        if not isinstance(report, dict):
            raise ValueError("SAVE_REPORT_NOT_OBJECT")
        save = report.get("save")
        if not isinstance(save, dict) or not isinstance(save.get("path"), str):
            raise ValueError("SAVE_REPORT_MISSING_SAVE_PATH")
        path = Path(save["path"])
    elif args.save:
        path = args.save
    else:
        raise ValueError("ONE_OF_SAVE_REPORT_OR_SAVE_REQUIRED")
    return path.expanduser().resolve(strict=True), report


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    path, save_report = _resolve_save(args)
    source = bounded.detect_container(path)
    metadata = _read_save_metadata(path, source)
    active = scan_active_wars(path, source, EXPECTED_ACTOR, EXPECTED_RECIPIENT)
    matching = active.get("matching_active_wars", [])
    war = _war_summary(matching[0]) if len(matching) == 1 else {
        "matching_count": len(matching),
        "records": [],
    }
    province_scan = _scan_target_province(
        path, source, int(EXPECTED_GOAL_PROVINCE))
    province_state = province_scan.get("targets", {}).get(EXPECTED_GOAL_PROVINCE, {})
    target_owner = province_state.get("owner")
    target_controller = province_state.get("controller")
    current = war.get("current_sides", {})
    attackers = set(current.get("attackers", []))
    defenders = set(current.get("defenders", []))
    target_control_side = (
        "attacker" if target_controller in attackers else
        "defender" if target_controller in defenders else "unknown"
    )
    goal = war.get("goal", {})
    saved_sha = None
    if isinstance(save_report, dict):
        save = save_report.get("save")
        if isinstance(save, dict):
            saved_sha = save.get("sha256")
    checks = {
        "save_container_detected": source.get("container") in {"plain", "text", "zip"},
        "war_scan_complete": active.get("brace_balance_ok") is True
        and not active.get("unknown"),
        "one_matching_active_war": len(matching) == 1,
        "pair_currently_active": war.get("pair_currently_active") is True,
        "original_attacker_FRA": war.get("original_sides", {}).get("attacker") == EXPECTED_ACTOR,
        "original_defender_BUR": war.get("original_sides", {}).get("defender") == EXPECTED_RECIPIENT,
        "current_FRA_attacker": EXPECTED_ACTOR in attackers,
        "current_BUR_defender": EXPECTED_RECIPIENT in defenders,
        "goal_present": goal.get("present_in_save") is True,
        "goal_province_88": goal.get("province") == EXPECTED_GOAL_PROVINCE,
        "province_scan_complete": province_scan.get("provinces_block_complete") is True
        and not province_scan.get("unknown"),
        "goal_target_owner_BUR": target_owner == EXPECTED_RECIPIENT,
        "goal_target_controller_BUR": target_controller == EXPECTED_RECIPIENT,
        "goal_target_is_defender_controlled": target_control_side == "defender",
        "historical_sha_matches_report": (
            saved_sha is None or saved_sha == EXPECTED_SHA256
        ),
    }
    result: dict[str, Any] = {
        "schema": "r74-war-save-contract-v1",
        "status": "passed" if all(checks.values()) else "incomplete",
        "source": {
            "save_path": str(path),
            "container": source.get("container"),
            "size_bytes": path.stat().st_size,
            "historical_sha256": EXPECTED_SHA256,
            "sha256_from_save_report": saved_sha,
            "source_hash_recomputed": False,
            "hash_note": "Historical SHA supplied by R70 evidence; this checker does not rehash the save.",
        },
        "snapshot": metadata,
        "war": {
            "matching_count": len(matching),
            "scan_complete": checks["war_scan_complete"],
            "unknown": active.get("unknown", []),
            **war,
        },
        "target_province": {
            "province_id": int(EXPECTED_GOAL_PROVINCE),
            "complete": province_state.get("complete") is True,
            "owner": target_owner,
            "controller": target_controller,
            "control_side": target_control_side,
            "direct_fields": province_state.get("direct_fields", {}),
            "scan": {
                "line_count": province_scan.get("line_count"),
                "line_start": province_state.get("line_start"),
                "line_end": province_state.get("line_end"),
                "unknown": province_scan.get("unknown", []),
            },
        },
        "tooltip_contract": {
            "save_components": war.get("tooltip_save_components", {}),
            "native_query_components": None,
            "decoded_tooltip_text": None,
            "formula_inference": False,
            "note": (
                "Save fields independently establish sides, goal province, "
                "controller, serialized defender_score and participant rows. "
                "Native total/goal/tooltip values remain query evidence; no "
                "score algorithm is reconstructed from the save."
            ),
        },
        "checks": checks,
        "query_binding": {
            "supplied": False,
            "reason": "No --query-report supplied.",
        },
    }
    if args.query_report:
        events = _load_query_events(args.query_report)
        binding = _query_binding(events, war, {
            "owner": target_owner,
            "controller": target_controller,
        })
        result["query_binding"] = binding
        result["tooltip_contract"]["native_query_components"] = binding.get("events")
        result["status"] = (
            "passed"
            if all(checks.values()) and all(binding.get("checks", {}).values())
            else "incomplete"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--save-report", type=Path)
    group.add_argument("--save", type=Path)
    parser.add_argument("--query-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"OUTPUT_EXISTS:{args.output}")
    report = _build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "checks": report["checks"],
        "query_checks": report["query_binding"].get("checks", {}),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
