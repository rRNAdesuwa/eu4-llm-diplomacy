#!/usr/bin/env python3
"""Compare Curry Favors task results with independently scanned save storage.

The input event files must contain the original
``native_diplomacy_task_execution_result`` records.  Results are grouped by
the exact ``(actor, recipient)`` pair and the last ``task_after`` value is
used.  The save is read once as a buffered binary stream; it is never loaded
into memory.  Candidate task storage is reported only when the save itself
contains the corresponding fields.  In particular, an absent
``action_token=curry_favors`` block is reported as an evidence gap rather than
being invented as a passing stop result.

An ``action_token`` is not sufficient to call a task active: EU4 keeps the
diplomat's reverse-route construction while it returns after a stop.  The
checker reads the actor and recipient country capitals from the same save and
classifies ``from_province -> to_province`` as outbound active or reverse
returning, following the independently observed R28 improve-relations save
and native state transition.

This checker is deliberately independent of the bridge and native worker.
It does not start a game, query REA, or mutate a save.  A caller may pass an
already-known save SHA-256 reference to avoid hashing the save a second time.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterator


EVENT_NAME = "native_diplomacy_task_execution_result"
EVENT_FAMILY = "curry_favors"
CONSTRUCTION_KEY = "diplomacy_construction"
CURRY_TOKEN = "curry_favors"
MAX_MARKER_HITS = 40
MAX_RECORDS_IN_REPORT = 80
MAX_VALUE_BYTES = 256
MAX_LINE_SNIPPET = 240
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ASSIGNMENT_RE = re.compile(rb"^[ \t]*(?P<key>[A-Za-z0-9_]+)[ \t]*=[ \t]*(?P<value>.*?)[ \t]*$")
MARKER_RE = re.compile(rb"curry|diplomacy_construction", re.IGNORECASE)


def _split_line_ending(line: bytes) -> bytes:
    if line.endswith(b"\r\n"):
        return line[:-2]
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1]
    return line


def _brace_delta(line: bytes) -> int:
    """Count braces outside quoted strings without decoding a save line."""

    quoted = False
    escaped = False
    delta = 0
    for byte in line:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                quoted = False
        elif byte == 0x22:
            quoted = True
        elif byte == 0x7B:
            delta += 1
        elif byte == 0x7D:
            delta -= 1
    return delta


def _is_open(line: bytes, key: str) -> bool:
    return _split_line_ending(line).strip() == key.encode("ascii") + b"={"


def _short_text(value: bytes, limit: int = MAX_VALUE_BYTES) -> str:
    value = value[:limit]
    return value.decode("utf-8", errors="replace")


def _display_line(line: bytes) -> str:
    return _short_text(_split_line_ending(line), MAX_LINE_SNIPPET)


def _unquote(value: bytes) -> str:
    value = value.strip()
    if len(value) >= 2 and value[:1] == b'"' and value[-1:] == b'"':
        value = value[1:-1]
    return _short_text(value)


def _assignment(line: bytes) -> tuple[str, str] | None:
    match = ASSIGNMENT_RE.match(_split_line_ending(line))
    if match is None:
        return None
    return (
        match.group("key").decode("ascii", errors="replace"),
        _unquote(match.group("value")),
    )


@dataclass
class EventRecord:
    sequence: int
    path: str
    item: int
    actor: str
    recipient: str
    task_after: bool
    task_before: bool | None
    native_variant: int | None
    action_id: str | None
    outcome: str | None
    date_raw: int | None
    request_id: object

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "path": self.path,
            "item": self.item,
            "actor": self.actor,
            "recipient": self.recipient,
            "task_before": self.task_before,
            "task_after": self.task_after,
            "native_variant": self.native_variant,
            "action_id": self.action_id,
            "outcome": self.outcome,
            "date_raw": self.date_raw,
            "request_id": self.request_id,
        }


@dataclass
class EventState:
    files: list[dict[str, Any]] = field(default_factory=list)
    events_seen: int = 0
    named_events_seen: int = 0
    selected_events: int = 0
    filtered_other_family: int = 0
    malformed_selected: int = 0
    errors: list[str] = field(default_factory=list)
    selected: list[EventRecord] = field(default_factory=list)
    last_by_pair: "OrderedDict[tuple[str, str], EventRecord]" = field(
        default_factory=OrderedDict
    )


def _iter_json_items(path: Path) -> Iterator[tuple[int, object]]:
    """Yield JSON objects without reading JSONL files as one large string."""

    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    yield line_number, json.loads(line)
        return

    # Reports are small compared with the save.  Raw execution evidence is
    # expected as JSONL, but accepting a small JSON array keeps the checker
    # useful for a saved native-event slice.
    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        value = json.load(stream)
    if isinstance(value, list):
        for index, item in enumerate(value, 1):
            yield index, item
    else:
        yield 1, value


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer when present")
    return value


def _optional_bool(value: object, name: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool when present")
    return value


def collect_events(paths: list[Path]) -> EventState:
    state = EventState()
    sequence = 0
    for raw_path in paths:
        path = raw_path.expanduser().resolve(strict=False)
        file_info: dict[str, Any] = {"path": str(path), "read": False, "items": 0}
        state.files.append(file_info)
        if not path.is_file():
            state.errors.append(f"event file does not exist: {path}")
            continue
        try:
            for item_number, raw_item in _iter_json_items(path):
                file_info["items"] += 1
                state.events_seen += 1
                if not isinstance(raw_item, dict):
                    continue
                if raw_item.get("event") != EVENT_NAME:
                    continue
                state.named_events_seen += 1
                if raw_item.get("family") != EVENT_FAMILY:
                    state.filtered_other_family += 1
                    continue
                try:
                    actor = raw_item.get("actor")
                    recipient = raw_item.get("recipient")
                    task_after = raw_item.get("task_after")
                    if not isinstance(actor, str) or not isinstance(recipient, str):
                        raise ValueError("actor/recipient must be strings")
                    if type(task_after) is not bool:
                        raise ValueError("task_after must be a bool")
                    task_before = _optional_bool(raw_item.get("task_before"), "task_before")
                    native_variant = _optional_int(
                        raw_item.get("native_variant"), "native_variant"
                    )
                    date_raw = _optional_int(raw_item.get("date_raw"), "date_raw")
                    action_id = raw_item.get("action_id")
                    if action_id is not None and not isinstance(action_id, str):
                        raise ValueError("action_id must be a string when present")
                    outcome = raw_item.get("outcome")
                    if outcome is not None and not isinstance(outcome, str):
                        raise ValueError("outcome must be a string when present")
                    if native_variant in (0, 1):
                        variant_after = native_variant == 1
                        if variant_after != task_after:
                            raise ValueError(
                                "native_variant does not agree with task_after "
                                f"({native_variant!r} versus {task_after!r})"
                            )
                except ValueError as exc:
                    state.malformed_selected += 1
                    state.errors.append(f"{path}:{item_number}: {exc}")
                    continue

                sequence += 1
                record = EventRecord(
                    sequence=sequence,
                    path=str(path),
                    item=item_number,
                    actor=actor,
                    recipient=recipient,
                    task_after=task_after,
                    task_before=task_before,
                    native_variant=native_variant,
                    action_id=action_id,
                    outcome=outcome,
                    date_raw=date_raw,
                    request_id=raw_item.get("request_id"),
                )
                state.selected_events += 1
                state.selected.append(record)
                state.last_by_pair[(actor, recipient)] = record
            file_info["read"] = True
        except (OSError, UnicodeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            state.errors.append(f"event file {path}: {exc}")

    if state.selected_events == 0:
        state.errors.append(
            "no native_diplomacy_task_execution_result event with family curry_favors was selected"
        )
    return state


@dataclass
class ConstructionRecord:
    start_line: int
    depth: int
    end_line: int | None = None
    fields: OrderedDict[str, str] = field(default_factory=OrderedDict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "fields": dict(self.fields),
        }


@dataclass
class CountryCapture:
    tag: str
    depth: int
    start_line: int
    end_line: int | None = None
    capital_values: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SaveState:
    source_size: int
    line_count: int
    sha256: str | None
    sha256_source: str
    hash_passes: int
    top_level_date: str | None
    top_level_save_game: str | None
    construction_blocks: list[ConstructionRecord]
    country_capitals: dict[str, list[dict[str, Any]]]
    countries_found: bool
    countries_complete: bool
    countries_scanned: int
    marker_hits: list[dict[str, Any]]
    marker_counts: dict[str, int]
    final_depth: int
    scan_complete: bool
    errors: list[str]


def _marker_kind(line: bytes) -> str | None:
    lowered = line.lower()
    if b"diplomacy_construction" in lowered:
        return CONSTRUCTION_KEY
    if b"curry" in lowered:
        return "curry"
    return None


def scan_save(
    path: Path,
    save_sha256: str | None = None,
    country_tags: set[str] | None = None,
) -> SaveState:
    """Scan the save once, retaining candidate task and capital fields."""

    construction_blocks: list[ConstructionRecord] = []
    country_capitals: dict[str, list[dict[str, Any]]] = {}
    target_country_tags = set(country_tags or ())
    current_country: CountryCapture | None = None
    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    countries_scanned = 0
    marker_hits: list[dict[str, Any]] = []
    marker_counts = {CONSTRUCTION_KEY: 0, "curry": 0}
    current: ConstructionRecord | None = None
    depth = 0
    line_count = 0
    source_size = 0
    top_level_date: str | None = None
    top_level_save_game: str | None = None
    errors: list[str] = []
    digest = hashlib.sha256() if save_sha256 is None else None

    try:
        with path.open("rb", buffering=1024 * 1024) as stream:
            for line_number, line in enumerate(stream, 1):
                line_count = line_number
                source_size += len(line)
                if digest is not None:
                    digest.update(line)
                before = depth

                marker_kind = _marker_kind(line)
                if marker_kind is not None:
                    marker_counts[marker_kind] += 1
                    if len(marker_hits) < MAX_MARKER_HITS:
                        marker_hits.append(
                            {
                                "kind": marker_kind,
                                "line": line_number,
                                "text": _display_line(line),
                            }
                        )

                if before == 0:
                    assignment = _assignment(line)
                    if assignment is not None:
                        key, value = assignment
                        if key == "date" and top_level_date is None:
                            top_level_date = value
                        elif key == "save_game" and top_level_save_game is None:
                            top_level_save_game = value

                if not countries_found and before == 0 and _is_open(line, "countries"):
                    countries_found = True
                    countries_depth = before + _brace_delta(line)

                if (
                    current_country is None
                    and countries_found
                    and not countries_complete
                    and countries_depth is not None
                    and before == countries_depth
                ):
                    for tag in target_country_tags:
                        if _is_open(line, tag):
                            current_country = CountryCapture(
                                tag=tag,
                                depth=before + _brace_delta(line),
                                start_line=line_number,
                            )
                            break

                if current_country is not None and before == current_country.depth:
                    assignment = _assignment(line)
                    if assignment is not None:
                        key, value = assignment
                        if key == "capital":
                            try:
                                capital = int(value)
                            except ValueError:
                                capital = None
                            if capital is not None:
                                current_country.capital_values.append(
                                    {"line": line_number, "raw": capital}
                                )

                if current is None and _is_open(line, CONSTRUCTION_KEY):
                    current = ConstructionRecord(
                        start_line=line_number,
                        depth=before + _brace_delta(line),
                        end_line=None,
                    )

                if current is not None:
                    # The fields used by existing diplomacy_construction
                    # records are direct members of this block.  Nested
                    # structures are intentionally not interpreted.
                    block_depth = current.depth
                    if before == block_depth and not _is_open(line, CONSTRUCTION_KEY):
                        assignment = _assignment(line)
                        if assignment is not None:
                            key, value = assignment
                            if key not in current.fields:
                                current.fields[key] = value

                depth += _brace_delta(line)

                if current is not None:
                    if depth < current.depth:
                        current.end_line = line_number
                        construction_blocks.append(current)
                        current = None

                if current_country is not None and depth < current_country.depth:
                    current_country.end_line = line_number
                    country_capitals[current_country.tag] = list(
                        current_country.capital_values
                    )
                    countries_scanned += 1
                    current_country = None

                if (
                    countries_found
                    and countries_depth is not None
                    and depth < countries_depth
                ):
                    countries_complete = True
            if current is not None:
                errors.append(
                    f"unterminated {CONSTRUCTION_KEY} block starting at line {current.start_line}"
                )
                construction_blocks.append(current)
            if current_country is not None:
                errors.append(
                    f"unterminated country block {current_country.tag} "
                    f"starting at line {current_country.start_line}"
                )
                country_capitals[current_country.tag] = list(
                    current_country.capital_values
                )
                countries_scanned += 1
                current_country = None
        if not countries_found and target_country_tags:
            errors.append("top-level countries block not found")
        if countries_found and not countries_complete:
            errors.append("top-level countries block did not close")
        if depth != 0:
            errors.append(f"final save brace depth is {depth}, expected 0")
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"save scan: {exc}")

    return SaveState(
        source_size=source_size,
        line_count=line_count,
        sha256=save_sha256 if save_sha256 is not None else digest.hexdigest(),
        sha256_source=(
            "caller_provided_reference" if save_sha256 is not None else "single_streaming_pass"
        ),
        hash_passes=0 if save_sha256 is not None else 1,
        top_level_date=top_level_date,
        top_level_save_game=top_level_save_game,
        construction_blocks=construction_blocks,
        country_capitals=country_capitals,
        countries_found=countries_found,
        countries_complete=countries_complete,
        countries_scanned=countries_scanned,
        marker_hits=marker_hits,
        marker_counts=marker_counts,
        final_depth=depth,
        scan_complete=not errors and depth == 0,
        errors=errors,
    )


def _is_curry_record(record: ConstructionRecord) -> bool:
    return record.fields.get("action_token") == CURRY_TOKEN


def _pair_matches(record: ConstructionRecord, actor: str, recipient: str) -> bool:
    return (
        _is_curry_record(record)
        and record.fields.get("actor") == actor
        and record.fields.get("recipient") == recipient
    )


def _int_field(record: ConstructionRecord, key: str) -> int | None:
    value = record.fields.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _unique_capital(save_state: SaveState, tag: str) -> int | None:
    values = save_state.country_capitals.get(tag, [])
    raw_values = {item.get("raw") for item in values}
    if len(raw_values) != 1:
        return None
    value = next(iter(raw_values))
    return value if type(value) is int else None


def _route_state(
    record: ConstructionRecord,
    actor: str,
    recipient: str,
    save_state: SaveState,
) -> tuple[str, dict[str, Any]]:
    """Classify outgoing versus returning diplomat construction.

    R28's independently observed stop/reload evidence establishes that a
    stopped improve-relations diplomat remains in the save with the reverse
    route (recipient province -> actor province) while returning.  Curry uses
    the same diplomacy_construction route fields.  The classifier therefore
    requires both country capitals from the save and never treats an
    action_token alone as an active task.
    """

    from_province = _int_field(record, "from_province")
    to_province = _int_field(record, "to_province")
    actor_capital = _unique_capital(save_state, actor)
    recipient_capital = _unique_capital(save_state, recipient)
    basis = {
        "from_province": from_province,
        "to_province": to_province,
        "actor": actor,
        "recipient": recipient,
        "actor_capital": actor_capital,
        "recipient_capital": recipient_capital,
        "rule": "actor_capital_to_recipient_capital=outbound_active; reverse=returning",
    }
    if None in (from_province, to_province, actor_capital, recipient_capital):
        return "unclassified", basis
    if from_province == actor_capital and to_province == recipient_capital:
        return "outbound_active", basis
    if from_province == recipient_capital and to_province == actor_capital:
        return "returning", basis
    return "other_route", basis


def _annotated_save_record(
    record: ConstructionRecord,
    actor: str | None,
    recipient: str | None,
    save_state: SaveState,
) -> dict[str, Any]:
    result = _save_record_report(record)
    if actor is None or recipient is None:
        result["route_state"] = "unclassified"
        result["route_basis"] = {"reason": "actor/recipient fields missing"}
        return result
    route_state, basis = _route_state(record, actor, recipient, save_state)
    result["route_state"] = route_state
    result["route_basis"] = basis
    return result


def _event_report(record: EventRecord) -> dict[str, Any]:
    return record.as_dict()


def _save_record_report(record: ConstructionRecord) -> dict[str, Any]:
    return record.as_dict()


def _compare(event_state: EventState, save_state: SaveState) -> tuple[list[dict[str, Any]], list[str]]:
    comparisons: list[dict[str, Any]] = []
    errors: list[str] = []
    curry_records = [record for record in save_state.construction_blocks if _is_curry_record(record)]

    for pair, last in event_state.last_by_pair.items():
        actor, recipient = pair
        matches = [record for record in curry_records if _pair_matches(record, actor, recipient)]
        annotated = [
            _annotated_save_record(record, actor, recipient, save_state)
            for record in matches
        ]
        outbound = [
            item for item in annotated if item.get("route_state") == "outbound_active"
        ]
        returning = [
            item for item in annotated if item.get("route_state") == "returning"
        ]
        unclassified = [
            item
            for item in annotated
            if item.get("route_state") not in {"outbound_active", "returning"}
        ]
        prior_start = any(
            record.actor == actor
            and record.recipient == recipient
            and record.task_after
            for record in event_state.selected
            if record.sequence < last.sequence
        )
        if last.task_after:
            match = len(outbound) == 1 and not returning and not unclassified
            evidence = "outbound_active_record_present" if match else "active_record_missing_or_ambiguous"
            if not match:
                if returning and not outbound:
                    errors.append(
                        f"only a returning curry_favors record was observed for active pair "
                        f"{actor}->{recipient}"
                    )
                elif unclassified:
                    errors.append(
                        f"curry_favors route could not be classified for active pair "
                        f"{actor}->{recipient}; country capital or route fields are incomplete"
                    )
                else:
                    errors.append(
                        f"missing unique outbound curry_favors save record for active pair "
                        f"{actor}->{recipient} (found {len(outbound)})"
                    )
        else:
            # A stop leaves a reverse-route construction while the diplomat
            # returns.  R28 established this independently for improve
            # relations (active_raw_18 2 -> returning 1 and the save route
            # recipient -> actor).  Treat that returning record as the
            # persisted stopped state, while an outgoing route is a real
            # contradiction.
            if outbound:
                match = False
                evidence = "outbound_active_record_present_after_stop"
                errors.append(
                    f"outbound curry_favors save record remains for stopped pair "
                    f"{actor}->{recipient}"
                )
            elif len(returning) == 1 and not unclassified:
                match = True
                evidence = "returning_record_after_stop"
            elif unclassified:
                match = False
                evidence = "curry_record_route_unclassified_after_stop"
                errors.append(
                    f"curry_favors save record route is unclassified for stopped pair "
                    f"{actor}->{recipient}; returning state cannot be proven"
                )
            else:
                match = False
                evidence = "active_record_absent_unproven"
                errors.append(
                    f"no curry_favors save record was observed for stopped pair {actor}->{recipient}; "
                    "absence is not treated as a verified persisted field"
                )

        comparisons.append(
            {
                "actor": actor,
                "recipient": recipient,
                "expected_task_after": last.task_after,
                "last_event": _event_report(last),
                "active_records": outbound,
                "returning_records": returning,
                "candidate_records": annotated,
                "active_record_count": len(outbound),
                "returning_record_count": len(returning),
                "unclassified_record_count": len(unclassified),
                "evidence": evidence,
                "match": match,
                "prior_start_event": prior_start,
            }
        )
    return comparisons, errors


def build_report(
    event_state: EventState,
    save_state: SaveState,
    save_path: Path,
    prior_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comparisons, comparison_errors = _compare(event_state, save_state)
    errors = list(event_state.errors) + list(save_state.errors) + comparison_errors
    curry_records = [record for record in save_state.construction_blocks if _is_curry_record(record)]
    identified_fields = sorted(
        {key for record in curry_records for key in record.fields}
    )
    candidate_fields = sorted(
        {
            key
            for record in save_state.construction_blocks
            for key in record.fields
        }
    )

    if not event_state.selected:
        status = "incomplete"
    elif errors:
        # A missing/unknown save field is an evidence gap.  Contradictory
        # positive evidence remains a failed verification.
        hard_failure = any(
            "outbound curry_favors save record remains for stopped pair" in error
            or "only a returning curry_favors record was observed for active pair" in error
            or "does not agree with task_after" in error
            or "actor/recipient must be strings" in error
            for error in errors
        )
        status = "failed" if hard_failure else "incomplete"
    elif comparisons and all(row["match"] for row in comparisons):
        status = "passed"
    else:
        status = "incomplete"

    return {
        "schema": "r72_curry_save_verify_v1",
        "status": status,
        "errors": errors,
        "fields": {
            "event_family": EVENT_FAMILY,
            "event_name": EVENT_NAME,
            "selected_event_count": event_state.selected_events,
            "selected_events": [_event_report(record) for record in event_state.selected],
            "last_task_after_by_actor_recipient": comparisons,
            "save_task_storage": {
                "candidate_container": CONSTRUCTION_KEY,
                "candidate_container_observed": bool(save_state.construction_blocks),
                "selector": "action_token=curry_favors",
                "selector_observed_in_save": bool(curry_records),
                "identified_fields": identified_fields,
                "candidate_fields_seen_in_other_constructions": candidate_fields,
                "identified_record_count": len(curry_records),
                "records": [
                    _annotated_save_record(
                        record,
                        record.fields.get("actor"),
                        record.fields.get("recipient"),
                        save_state,
                    )
                    for record in curry_records[:MAX_RECORDS_IN_REPORT]
                ],
                "records_truncated": len(curry_records) > MAX_RECORDS_IN_REPORT,
                "route_semantics": {
                    "outbound_active": "from_province equals actor capital and to_province equals recipient capital",
                    "returning": "from_province equals recipient capital and to_province equals actor capital",
                    "source": "R28 improve-relations returning save and native state evidence",
                },
                "country_capitals": save_state.country_capitals,
                "absence_is_not_fabricated_as_stop_pass": True,
            },
        },
        "save": {
            "path": str(save_path),
            "size": save_state.source_size,
            "sha256": save_state.sha256,
            "sha256_source": save_state.sha256_source,
            "sha256_passes": save_state.hash_passes,
            "line_count": save_state.line_count,
            "top_level_date": save_state.top_level_date,
            "top_level_save_game": save_state.top_level_save_game,
            "construction_blocks_scanned": len(save_state.construction_blocks),
            "countries_found": save_state.countries_found,
            "countries_complete": save_state.countries_complete,
            "countries_scanned": save_state.countries_scanned,
            "country_capitals": save_state.country_capitals,
            "marker_counts": save_state.marker_counts,
            "marker_hits": save_state.marker_hits,
            "scan_complete": save_state.scan_complete,
            "final_brace_depth": save_state.final_depth,
            "single_streaming_pass": True,
            "event_save_lines_or_offsets_used": False,
        },
        "events": {
            "files": event_state.files,
            "events_seen": event_state.events_seen,
            "named_events_seen": event_state.named_events_seen,
            "selected_family_events": event_state.selected_events,
            "filtered_other_family": event_state.filtered_other_family,
            "malformed_selected": event_state.malformed_selected,
        },
        "prior_report": prior_report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--events", required=True, nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--save-sha256",
        help="known save SHA-256 reference; skips computing a second streaming digest",
    )
    parser.add_argument(
        "--prior-report",
        type=Path,
        help="small prior checker report to reference without overwriting its evidence",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    save_path = args.save.expanduser().resolve(strict=False)
    output = args.output.expanduser().resolve(strict=False)
    if not save_path.is_file():
        raise FileNotFoundError(f"save does not exist: {save_path}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output report: {output}")
    supplied_sha = args.save_sha256.lower() if args.save_sha256 else None
    if supplied_sha is not None and HEX64_RE.fullmatch(supplied_sha) is None:
        raise ValueError("--save-sha256 must be exactly 64 hexadecimal characters")

    event_state = collect_events([path.expanduser().resolve(strict=False) for path in args.events])
    target_tags = {
        tag
        for record in event_state.selected
        for tag in (record.actor, record.recipient)
    }
    save_state = scan_save(save_path, supplied_sha, target_tags)
    prior_report: dict[str, Any] | None = None
    if args.prior_report is not None:
        prior_path = args.prior_report.expanduser().resolve(strict=False)
        if not prior_path.is_file():
            raise FileNotFoundError(f"prior report does not exist: {prior_path}")
        with prior_path.open("r", encoding="utf-8") as stream:
            prior_value = json.load(stream)
        if not isinstance(prior_value, dict):
            raise ValueError("prior report must contain a JSON object")
        prior_fields = prior_value.get("fields")
        prior_report = {
            "path": str(prior_path),
            "status": prior_value.get("status"),
            "errors": prior_value.get("errors", []),
            "comparison_count": (
                len(prior_fields.get("last_task_after_by_actor_recipient", []))
                if isinstance(prior_fields, dict)
                else None
            ),
        }
    report = build_report(event_state, save_state, save_path, prior_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(
            (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
        )
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
