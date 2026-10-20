#!/usr/bin/env python3
"""Verify R71 favor-trade event states against one EU4 text save.

The event inputs are read in command-line order.  Only verified, complete
``native_diplomacy_favor_trade_execution_result`` and
``native_diplomacy_favor_trade_response_result`` events contribute state.  For
each event the ``after`` state is applied in order; the last treasury value for
each actor/recipient country and the last ``favors_raw`` value for
``recipient.active_relations.actor`` become the expected save values.

The save is then scanned independently with a single binary streaming pass.
No event-provided save line or byte offset is used.  Save decimal fields are
converted with Decimal * 1000 and compared as exact integers.  The checker is
read-only with respect to the save and writes only the requested JSON report.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Iterator


EVENT_NAMES = frozenset(
    {
        "native_diplomacy_favor_trade_execution_result",
        "native_diplomacy_favor_trade_response_result",
    }
)
SAVE_SCALE = Decimal(1000)
DECIMAL_RE = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


def stripped(line: bytes) -> bytes:
    return line.strip()


def is_open(line: bytes, key: str) -> bool:
    return stripped(line) == key.encode("ascii") + b"={"


def brace_delta(line: bytes) -> int:
    """Count structural braces while ignoring quoted strings."""

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


def split_line_ending(line: bytes) -> tuple[bytes, bytes]:
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1], line[-1:]
    return line, b""


def display_line(line: bytes) -> str:
    body, _ending = split_line_ending(line)
    return body.decode("utf-8", errors="replace")


def decimal_to_raw(value: Decimal) -> int:
    """Convert a save decimal to an exact integer in the native 1000 scale."""

    with localcontext() as context:
        context.prec = max(64, len(value.as_tuple().digits) + 16)
        scaled = value * SAVE_SCALE
        integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError(f"save value is not integral at scale 1000: {value}")
    return int(integral)


def parse_scaled_field(line: bytes, key: str) -> tuple[Decimal, int] | None:
    body, _ending = split_line_ending(line)
    pattern = re.compile(
        rb"^[ \t]*"
        + re.escape(key.encode("ascii"))
        + rb"[ \t]*=[ \t]*(?P<value>"
        + DECIMAL_RE
        + rb")[ \t]*$"
    )
    match = pattern.match(body)
    if match is None:
        return None
    try:
        value = Decimal(match.group("value").decode("ascii"))
    except (UnicodeDecodeError, InvalidOperation) as exc:
        raise ValueError(f"invalid {key} value in save line {line!r}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite {key} value in save line {line!r}")
    return value, decimal_to_raw(value)


def parse_event_value(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"event {name} must be an integer, got {value!r}")
    return value


@dataclass
class EventProvenance:
    sequence: int
    path: str
    item: int
    event: str
    actor: str
    recipient: str
    request_id: object = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "path": self.path,
            "item": self.item,
            "event": self.event,
            "actor": self.actor,
            "recipient": self.recipient,
            "request_id": self.request_id,
        }


@dataclass
class FinalEventValue:
    raw: int
    provenance: EventProvenance


@dataclass
class EventState:
    treasury: OrderedDict[str, FinalEventValue] = field(default_factory=OrderedDict)
    favors: OrderedDict[tuple[str, str], FinalEventValue] = field(
        default_factory=OrderedDict
    )
    files: list[dict[str, Any]] = field(default_factory=list)
    events_seen: int = 0
    named_events_seen: int = 0
    selected_events: int = 0
    filtered_incomplete: int = 0
    malformed_selected: int = 0
    errors: list[str] = field(default_factory=list)


def _iter_json_file(path: Path) -> Iterator[tuple[int, object]]:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                yield line_number, json.loads(line)
        return

    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        value = json.load(stream)
    if isinstance(value, list):
        for index, item in enumerate(value, 1):
            yield index, item
    else:
        yield 1, value


def _record_malformed(state: EventState, path: Path, item: int, message: str) -> None:
    state.malformed_selected += 1
    state.errors.append(f"{path}:{item}: {message}")


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
            for item_number, raw_event in _iter_json_file(path):
                file_info["items"] += 1
                state.events_seen += 1
                if not isinstance(raw_event, dict):
                    continue
                event_name = raw_event.get("event")
                if event_name not in EVENT_NAMES:
                    continue
                state.named_events_seen += 1
                trade = raw_event.get("favor_trade")
                if not isinstance(trade, dict):
                    _record_malformed(state, path, item_number, "missing favor_trade object")
                    continue
                if type(trade.get("complete")) is not bool or type(trade.get("verified")) is not bool:
                    _record_malformed(
                        state, path, item_number, "favor_trade.complete/verified must be bool"
                    )
                    continue
                if not (trade["complete"] and trade["verified"]):
                    state.filtered_incomplete += 1
                    continue
                actor = raw_event.get("actor")
                recipient = raw_event.get("recipient")
                if not isinstance(actor, str) or not isinstance(recipient, str):
                    _record_malformed(state, path, item_number, "actor/recipient missing")
                    continue
                if raw_event.get("family") not in (None, "favor_trade"):
                    _record_malformed(state, path, item_number, "event family is not favor_trade")
                    continue
                after = trade.get("after")
                if not isinstance(after, dict) or type(after.get("complete")) is not bool:
                    _record_malformed(state, path, item_number, "verified event has invalid after state")
                    continue
                if not after["complete"]:
                    _record_malformed(state, path, item_number, "verified event after.complete is false")
                    continue
                try:
                    actor_treasury = parse_event_value(
                        after.get("actor_treasury_raw"), "after.actor_treasury_raw"
                    )
                    recipient_treasury = parse_event_value(
                        after.get("recipient_treasury_raw"), "after.recipient_treasury_raw"
                    )
                    favors = parse_event_value(after.get("favors_raw"), "after.favors_raw")
                except ValueError as exc:
                    _record_malformed(state, path, item_number, str(exc))
                    continue

                sequence += 1
                provenance = EventProvenance(
                    sequence=sequence,
                    path=str(path),
                    item=item_number,
                    event=event_name,
                    actor=actor,
                    recipient=recipient,
                    request_id=raw_event.get("request_id"),
                )
                state.selected_events += 1
                state.treasury[actor] = FinalEventValue(actor_treasury, provenance)
                state.treasury[recipient] = FinalEventValue(recipient_treasury, provenance)
                state.favors[(recipient, actor)] = FinalEventValue(favors, provenance)
            file_info["read"] = True
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            state.errors.append(f"event file {path}: {exc}")
    if state.selected_events == 0:
        state.errors.append("no complete and verified favor_trade events selected")
    return state


@dataclass
class RelationCapture:
    actor: str
    start_line: int
    depth: int
    favors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CountryCapture:
    tag: str
    start_line: int
    depth: int
    treasury: list[dict[str, Any]] = field(default_factory=list)
    active_relations_count: int = 0
    active_depth: int | None = None
    relation: RelationCapture | None = None
    relations: dict[str, dict[str, Any]] = field(default_factory=dict)
    end_line: int | None = None


@dataclass
class SaveState:
    countries: dict[str, CountryCapture]
    line_count: int
    source_size: int
    sha256: str
    countries_found: bool
    countries_complete: bool
    countries_start_line: int | None
    countries_end_line: int | None
    final_depth: int
    errors: list[str]
    hash_passes: int = 1


def _finish_relation(country: CountryCapture, line_number: int) -> None:
    relation = country.relation
    if relation is None:
        return
    if relation.actor in country.relations:
        raise ValueError(
            f"duplicate relation block in {country.tag}.active_relations.{relation.actor}"
        )
    if len(relation.favors) > 1:
        raise ValueError(
            f"duplicate favors fields in {country.tag}.active_relations.{relation.actor}"
        )
    if relation.favors:
        country.relations[relation.actor] = {
            "start_line": relation.start_line,
            "end_line": line_number,
            "favors": relation.favors[0],
        }
    else:
        country.relations[relation.actor] = {
            "start_line": relation.start_line,
            "end_line": line_number,
            "favors": None,
        }
    country.relation = None


def _finish_country(country: CountryCapture, line_number: int) -> None:
    country.end_line = line_number


def scan_save(path: Path, treasury_tags: set[str], relation_targets: dict[str, set[str]]) -> SaveState:
    countries: dict[str, CountryCapture] = {}
    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    countries_start_line: int | None = None
    countries_end_line: int | None = None
    current: CountryCapture | None = None
    line_count = 0
    source_size = 0
    depth = 0
    digest = hashlib.sha256()
    errors: list[str] = []
    target_tags = set(treasury_tags) | set(relation_targets)
    for actors in relation_targets.values():
        target_tags.update(actors)

    try:
        with path.open("rb", buffering=1024 * 1024) as stream:
            for line_number, line in enumerate(stream, 1):
                line_count = line_number
                source_size += len(line)
                digest.update(line)
                before = depth

                if not countries_found and before == 0 and is_open(line, "countries"):
                    countries_found = True
                    countries_start_line = line_number
                    countries_depth = before + brace_delta(line)

                if (
                    current is None
                    and countries_found
                    and not countries_complete
                    and countries_depth is not None
                    and before == countries_depth
                ):
                    for tag in target_tags:
                        if is_open(line, tag):
                            if tag in countries:
                                raise ValueError(f"duplicate top-level country block: {tag}")
                            current = CountryCapture(tag, line_number, before + brace_delta(line))
                            break

                if current is not None:
                    country_depth = current.depth
                    if before == country_depth:
                        treasury = parse_scaled_field(line, "treasury")
                        if treasury is not None:
                            value, raw_value = treasury
                            current.treasury.append(
                                {
                                    "line_number": line_number,
                                    "decimal": str(value),
                                    "raw": raw_value,
                                    "original_line": display_line(line),
                                }
                            )
                        if is_open(line, "active_relations"):
                            current.active_relations_count += 1
                            if current.active_relations_count > 1:
                                raise ValueError(
                                    f"duplicate direct active_relations in country {current.tag}"
                                )
                            current.active_depth = before + brace_delta(line)

                    if current.active_depth is not None:
                        if current.relation is None and before == current.active_depth:
                            for actor in relation_targets.get(current.tag, set()):
                                if is_open(line, actor):
                                    current.relation = RelationCapture(
                                        actor, line_number, before + brace_delta(line)
                                    )
                                    break
                        elif current.relation is not None and before == current.relation.depth:
                            favors = parse_scaled_field(line, "favors")
                            if favors is not None:
                                value, raw_value = favors
                                current.relation.favors.append(
                                    {
                                        "line_number": line_number,
                                        "decimal": str(value),
                                        "raw": raw_value,
                                        "original_line": display_line(line),
                                    }
                                )

                depth += brace_delta(line)

                if current is not None and current.relation is not None and depth < current.relation.depth:
                    _finish_relation(current, line_number)
                if current is not None and current.active_depth is not None and depth < current.active_depth:
                    current.active_depth = None
                if current is not None and depth < current.depth:
                    _finish_country(current, line_number)
                    countries[current.tag] = current
                    current = None
                if countries_found and countries_depth is not None and depth < countries_depth:
                    countries_complete = True
                    countries_end_line = line_number

        if current is not None:
            errors.append(f"unterminated target country block: {current.tag}")
        if not countries_found:
            errors.append("top-level countries block not found")
        if not countries_complete:
            errors.append("top-level countries block did not close")
        if depth != 0:
            errors.append(f"final save brace depth is {depth}, expected 0")
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"save scan: {exc}")

    return SaveState(
        countries=countries,
        line_count=line_count,
        source_size=source_size,
        sha256=digest.hexdigest(),
        countries_found=countries_found,
        countries_complete=countries_complete,
        countries_start_line=countries_start_line,
        countries_end_line=countries_end_line,
        final_depth=depth,
        errors=errors,
    )


def _expected_value_report(value: FinalEventValue) -> dict[str, Any]:
    return {
        "raw": value.raw,
        "value": str(Decimal(value.raw) / SAVE_SCALE),
        "event": value.provenance.as_dict(),
    }


def _actual_field_report(field: dict[str, Any] | None) -> dict[str, Any]:
    if field is None:
        return {"present": False, "raw": None, "value": None, "save_line": None, "original_line": None}
    return {
        "present": True,
        "raw": field["raw"],
        "value": field["decimal"],
        "save_line": field["line_number"],
        "original_line": field["original_line"],
    }


def _treasury_field(country: CountryCapture | None) -> dict[str, Any] | None:
    if country is None or len(country.treasury) != 1:
        return None
    return country.treasury[0]


def compare(event_state: EventState, save_state: SaveState, save_path: Path) -> dict[str, Any]:
    errors = list(event_state.errors) + list(save_state.errors)
    treasury_checks: list[dict[str, Any]] = []
    for tag, expected in event_state.treasury.items():
        country = save_state.countries.get(tag)
        field = _treasury_field(country)
        actual = _actual_field_report(field)
        match = actual["present"] and actual["raw"] == expected.raw
        row = {
            "identity": {"country": tag, "field": "countries/%s/treasury" % tag},
            "expected": _expected_value_report(expected),
            "actual": actual,
            "match": match,
            "country_block": (
                {"start_line": country.start_line, "end_line": country.end_line}
                if country is not None
                else None
            ),
        }
        treasury_checks.append(row)
        if not match:
            errors.append(f"treasury mismatch for {tag}")
        if country is None:
            errors.append(f"missing country block for treasury target {tag}")
        elif len(country.treasury) != 1:
            errors.append(
                f"expected one direct treasury field for {tag}, found {len(country.treasury)}"
            )

    favors_checks: list[dict[str, Any]] = []
    for (recipient, actor), expected in event_state.favors.items():
        country = save_state.countries.get(recipient)
        relation = country.relations.get(actor) if country is not None else None
        field = relation.get("favors") if relation is not None else None
        actual = _actual_field_report(field)
        match = actual["present"] and actual["raw"] == expected.raw
        row = {
            "identity": {
                "recipient": recipient,
                "actor": actor,
                "save_path": f"countries/{recipient}/active_relations/{actor}/favors",
                "direction": f"{recipient} -> {actor}",
            },
            "expected": _expected_value_report(expected),
            "actual": actual,
            "match": match,
            "relation_block": (
                {"start_line": relation["start_line"], "end_line": relation["end_line"]}
                if relation is not None
                else None
            ),
        }
        favors_checks.append(row)
        if not match:
            errors.append(f"favors mismatch for {recipient}.active_relations.{actor}")
        if country is None:
            errors.append(f"missing recipient country block for {recipient}")
        elif country.active_relations_count != 1:
            errors.append(
                f"expected one active_relations block for {recipient}, found {country.active_relations_count}"
            )
        elif relation is None:
            errors.append(f"missing relation block {recipient}.active_relations.{actor}")

    report = {
        "schema": "r71_favor_save_verify_v1",
        "status": "passed" if not errors and treasury_checks and favors_checks else "failed",
        "save": {
            "path": str(save_path),
            "size": save_state.source_size,
            "sha256": save_state.sha256,
            "sha256_passes": save_state.hash_passes,
            "line_count": save_state.line_count,
        },
        "events": {
            "files": event_state.files,
            "events_seen": event_state.events_seen,
            "named_events_seen": event_state.named_events_seen,
            "selected_complete_verified": event_state.selected_events,
            "filtered_incomplete_or_unverified": event_state.filtered_incomplete,
            "malformed_selected": event_state.malformed_selected,
        },
        "save_scan": {
            "countries_found": save_state.countries_found,
            "countries_complete": save_state.countries_complete,
            "countries_start_line": save_state.countries_start_line,
            "countries_end_line": save_state.countries_end_line,
            "final_brace_depth": save_state.final_depth,
            "independent_save_locations": True,
            "event_save_lines_or_offsets_used": False,
            "decimal_scale": 1000,
        },
        "treasury_checks": treasury_checks,
        "favors_checks": favors_checks,
        "errors": errors,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--events", required=True, nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    save_path = args.save.expanduser().resolve(strict=False)
    output = args.output.expanduser().resolve(strict=False)
    if not save_path.is_file():
        raise FileNotFoundError(f"save does not exist: {save_path}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    event_state = collect_events(args.events)
    relation_targets: dict[str, set[str]] = {}
    for recipient, actor in event_state.favors:
        relation_targets.setdefault(recipient, set()).add(actor)
    save_state = scan_save(save_path, set(event_state.treasury), relation_targets)
    report = compare(event_state, save_state, save_path)
    report_bytes = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    with output.open("xb") as stream:
        stream.write(report_bytes)
    print(json.dumps({"status": report["status"], "output": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
