#!/usr/bin/env python3
"""Check R74 Gift/Influence results against one EU4 text save.

The native execution JSON is the source of the expected post-action values;
the save is scanned independently as one bounded binary stream.  Gift checks
cover both country treasuries and independently recompute the actor-to-
recipient delta.  Influence checks cover the payer treasury and the recipient
recipient relation's ``trust_value``.  The native effect also proves an influencer flag.
The static contract did not initially identify its save serializer fields; a
real save closes that gap only through the independently observed
``influenced_by`` and relation ``opinion`` records.

The checker never starts the game, mutates a save, or uses save line offsets
from an event.  Event files are small JSON/JSONL evidence; the save itself is
never loaded into a PowerShell array or a Python string.
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


ROOT = Path(__file__).resolve().parents[1]
GIFT_EVENT = "native_diplomacy_gift_execution_result"
INFLUENCE_EVENT = "native_diplomacy_influence_execution_result"
EVENT_NAMES = frozenset((GIFT_EVENT, INFLUENCE_EVENT))
INFLUENCE_MODIFIER = "great_power_influence"
TRUST_CONTRACT = ROOT / "work/runtime/r74-gift-influence-contract-20261020-001/trust-save-contract.md"
SAVE_SCALE = Decimal(1000)
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
TAG_RE = re.compile(r"^[A-Z0-9]{3}$")
DECIMAL_RE = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
ASSIGNMENT_RE = re.compile(
    rb"^[ \t]*(?P<key>[A-Za-z0-9_]+)[ \t]*=[ \t]*(?P<value>.*?)[ \t]*$"
)
TAG_OPEN_RE = re.compile(rb"^([A-Z0-9]{3})[ \t]*=[ \t]*\{$")
MAX_CANDIDATE_HITS = 160
MAX_RECORDS = 100
MARKER_WORDS = (
    b"influenc",
    b"modifier",
    b"opinion",
    b"expiry",
    b"expire",
    b"end_date",
    b"duration",
)
INFLUENCER_KEYS = frozenset(
    {
        "influencer",
        "influencers",
        "influencer_active",
        "active_influencer",
        "influenced_by",
        "influence_source",
        "active_influence",
    }
)
EXPIRY_KEYS = frozenset(
    {"expiry", "expiry_date", "expiration", "expiration_date", "expires", "end_date"}
)
OPINION_KEYS = frozenset(
    {"opinion_modifier", "opinion_modifier_raw", "influence_modifier", "modifier"}
)


def _split_line_ending(line: bytes) -> bytes:
    if line.endswith(b"\r\n"):
        return line[:-2]
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1]
    return line


def _brace_delta(line: bytes) -> int:
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


def _display_line(line: bytes, limit: int = 320) -> str:
    body = _split_line_ending(line)
    return body[:limit].decode("utf-8", errors="replace")


def _unquote(value: bytes) -> str:
    value = value.strip()
    if len(value) >= 2 and value[:1] == b'"' and value[-1:] == b'"':
        value = value[1:-1]
    return value[:512].decode("utf-8", errors="replace")


def _assignment(line: bytes) -> tuple[str, str] | None:
    match = ASSIGNMENT_RE.match(_split_line_ending(line))
    if match is None:
        return None
    return (
        match.group("key").decode("ascii", errors="replace"),
        _unquote(match.group("value")),
    )


def _is_int(value: object) -> bool:
    return type(value) is int


def _event_int(value: object, name: str, minimum: int | None = None) -> int:
    if not _is_int(value):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} is below {minimum}")
    return value


def _tag(value: object, name: str) -> str:
    if not isinstance(value, str) or TAG_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be an EU4 country tag")
    return value


def _scaled_decimal(value: str, scale: Decimal = SAVE_SCALE) -> tuple[str, int]:
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid save decimal {value!r}") from exc
    if not decimal.is_finite():
        raise ValueError(f"non-finite save decimal {value!r}")
    with localcontext() as context:
        context.prec = max(64, len(decimal.as_tuple().digits) + 16)
        scaled = decimal * scale
        integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError(f"save decimal is not integral at scale {scale}: {value}")
    return str(decimal), int(integral)


def _parse_save_number(line: bytes, key: str, scale: Decimal) -> tuple[str, int] | None:
    body = _split_line_ending(line)
    match = re.match(
        rb"^[ \t]*" + re.escape(key.encode("ascii"))
        + rb"[ \t]*=[ \t]*(?P<value>" + DECIMAL_RE + rb")[ \t]*$",
        body,
    )
    if match is None:
        return None
    return _scaled_decimal(match.group("value").decode("ascii"), scale)


def _parse_scaled_line(line: bytes, key: str) -> tuple[str, int] | None:
    return _parse_save_number(line, key, SAVE_SCALE)


def _parse_raw_line(line: bytes, key: str) -> tuple[str, int] | None:
    # Relation trust_value is a byte-like integer in the save, unlike
    # treasury values which use the game's 1000-unit decimal scale.
    return _parse_save_number(line, key, Decimal(1))


def _parse_int_text(value: str) -> int | None:
    try:
        return int(value, 10)
    except (TypeError, ValueError):
        return None


def _parse_bool_text(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"yes", "true", "1"}:
        return True
    if lowered in {"no", "false", "0"}:
        return False
    return None


def _walk_event_objects(value: object, depth: int = 0) -> Iterator[dict[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, dict):
        if "event" in value:
            yield value
        for item in value.values():
            yield from _walk_event_objects(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_event_objects(item, depth + 1)


def _iter_json_items(path: Path) -> Iterator[tuple[int, object]]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    yield line_number, json.loads(line)
        return
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError(f"refusing large non-JSONL evidence file: {path}")
    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        value = json.load(stream)
    yield 1, value


@dataclass(frozen=True)
class Provenance:
    sequence: int
    path: str
    item: int
    event: str
    actor: str
    recipient: str
    request_id: object
    date_raw: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "path": self.path,
            "item": self.item,
            "event": self.event,
            "actor": self.actor,
            "recipient": self.recipient,
            "request_id": self.request_id,
            "date_raw": self.date_raw,
        }


@dataclass(frozen=True)
class ExpectedValue:
    value: int | bool
    provenance: Provenance

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "event": self.provenance.as_dict()}


@dataclass
class EconomicEvent:
    sequence: int
    path: str
    item: int
    event: str
    kind: str
    action_id: str
    actor: str
    recipient: str
    native_state: int
    outcome: str
    date_raw: int | None
    request_id: object
    before: dict[str, Any]
    after: dict[str, Any]
    ducats: int | None = None
    amount_raw: int | None = None
    cost_raw: int | None = None
    opinion_raw: int | None = None
    duration_months: int | None = None

    @property
    def accepted(self) -> bool:
        return self.native_state in (0, 2)

    def provenance(self) -> Provenance:
        return Provenance(
            self.sequence,
            self.path,
            self.item,
            self.event,
            self.actor,
            self.recipient,
            self.request_id,
            self.date_raw,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "path": self.path,
            "item": self.item,
            "event": self.event,
            "kind": self.kind,
            "action_id": self.action_id,
            "actor": self.actor,
            "recipient": self.recipient,
            "native_state": self.native_state,
            "native_outcome": self.outcome,
            "date_raw": self.date_raw,
            "request_id": self.request_id,
            "before": self.before,
            "after": self.after,
            "ducats": self.ducats,
            "amount_raw": self.amount_raw,
            "cost_raw": self.cost_raw,
            "opinion_raw": self.opinion_raw,
            "duration_months": self.duration_months,
            "accepted": self.accepted,
        }


@dataclass
class EventState:
    files: list[dict[str, Any]] = field(default_factory=list)
    events_seen: int = 0
    named_events_seen: int = 0
    selected_events: int = 0
    malformed_selected: int = 0
    selected: list[EconomicEvent] = field(default_factory=list)
    treasury: OrderedDict[str, ExpectedValue] = field(default_factory=OrderedDict)
    trust: OrderedDict[tuple[str, str], ExpectedValue] = field(default_factory=OrderedDict)
    influencer: OrderedDict[tuple[str, str], ExpectedValue] = field(default_factory=OrderedDict)
    errors: list[str] = field(default_factory=list)


def _malformed(state: EventState, path: Path, item: int, message: str) -> None:
    state.malformed_selected += 1
    state.errors.append(f"{path}:{item}: {message}")


def _state_keys(value: object, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} has unexpected keys")
    if value.get("complete") is not True:
        raise ValueError(f"{name}.complete is not true")
    return value


def _collect_one_event(
    raw: dict[str, Any], path: Path, item: int, state: EventState, sequence: int
) -> EconomicEvent:
    event = raw.get("event")
    kind = "gift" if event == GIFT_EVENT else "influence"
    action_id = "send_gift" if kind == "gift" else "influence_nation"
    if raw.get("family") != kind or raw.get("action_id") != action_id:
        raise ValueError("event family/action does not match its R74 event")
    actor = _tag(raw.get("actor"), "actor")
    recipient = _tag(raw.get("recipient"), "recipient")
    if actor == recipient or actor == "FRA" and recipient == "FRA":
        raise ValueError("event endpoints are not distinct")
    if raw.get("phase") != "initiate":
        raise ValueError("R74 economic actions are initiate-only")
    if raw.get("execution_verified") is not True:
        raise ValueError("execution_verified is not true")
    if raw.get("request_binding_verified") is not True:
        raise ValueError("request_binding_verified is not true")
    native_state = _event_int(raw.get("native_state"), "native_state")
    if native_state not in (0, 1, 2):
        raise ValueError("native_state is outside raw/public R74 domain")
    outcome = raw.get("outcome")
    if not isinstance(outcome, str):
        raise ValueError("outcome is missing")
    date_raw = raw.get("date_raw")
    if date_raw is not None:
        date_raw = _event_int(date_raw, "date_raw")
    payload = raw.get(kind)
    if not isinstance(payload, dict):
        raise ValueError(f"missing {kind} result payload")
    if payload.get("verified") is not True:
        raise ValueError(f"{kind}.verified is not true")
    if payload.get("complete") is not True:
        raise ValueError(f"{kind}.complete is not true")
    if kind == "gift":
        if set(payload) != {"kind", "before", "after", "ducats", "amount_raw", "complete", "verified"}:
            raise ValueError("gift result keys are not the native R74 schema")
        if payload.get("kind") != "gift":
            raise ValueError("gift result kind mismatch")
        ducats = _event_int(payload.get("ducats"), "gift.ducats", 25)
        if ducats > 2147475 or ducats % 25:
            raise ValueError("gift.ducats violates the 25-step/int32 contract")
        amount_raw = _event_int(payload.get("amount_raw"), "gift.amount_raw", 0)
        if amount_raw != ducats * 1000:
            raise ValueError("gift amount_raw is not ducats*1000")
        before = _state_keys(
            payload.get("before"),
            {"complete", "actor_treasury_raw", "recipient_treasury_raw"},
            "gift.before",
        )
        after = _state_keys(
            payload.get("after"),
            {"complete", "actor_treasury_raw", "recipient_treasury_raw"},
            "gift.after",
        )
        before_actor = _event_int(before.get("actor_treasury_raw"), "gift.before.actor_treasury_raw")
        before_recipient = _event_int(
            before.get("recipient_treasury_raw"), "gift.before.recipient_treasury_raw"
        )
        after_actor = _event_int(after.get("actor_treasury_raw"), "gift.after.actor_treasury_raw")
        after_recipient = _event_int(
            after.get("recipient_treasury_raw"), "gift.after.recipient_treasury_raw"
        )
        if native_state in (0, 2):
            if after_actor != before_actor - amount_raw or after_recipient != before_recipient + amount_raw:
                raise ValueError("gift actor/recipient treasury delta is invalid")
            if outcome not in {"accepted", "executed"}:
                raise ValueError("accepted gift has an invalid outcome")
        else:
            if after_actor != before_actor or after_recipient != before_recipient:
                raise ValueError("rejected gift changed treasury")
            if outcome != "rejected":
                raise ValueError("rejected gift has an invalid outcome")
        return EconomicEvent(
            sequence,
            str(path),
            item,
            event,
            kind,
            action_id,
            actor,
            recipient,
            native_state,
            outcome,
            date_raw,
            raw.get("request_id"),
            before,
            after,
            ducats=ducats,
            amount_raw=amount_raw,
        )

    if set(payload) != {
        "kind",
        "before",
        "after",
        "cost_raw",
        "opinion_raw",
        "duration_months",
        "complete",
        "verified",
    }:
        raise ValueError("influence result keys are not the native R74 schema")
    if payload.get("kind") != "influence":
        raise ValueError("influence result kind mismatch")
    cost_raw = _event_int(payload.get("cost_raw"), "influence.cost_raw", 0)
    opinion_raw = _event_int(payload.get("opinion_raw"), "influence.opinion_raw")
    duration_months = _event_int(payload.get("duration_months"), "influence.duration_months")
    before = _state_keys(
        payload.get("before"),
        {"complete", "actor_treasury_raw", "recipient_trust_raw", "influencer_active"},
        "influence.before",
    )
    after = _state_keys(
        payload.get("after"),
        {"complete", "actor_treasury_raw", "recipient_trust_raw", "influencer_active"},
        "influence.after",
    )
    if type(before.get("influencer_active")) is not bool or type(after.get("influencer_active")) is not bool:
        raise ValueError("influence influencer_active must be bool")
    before_actor = _event_int(before.get("actor_treasury_raw"), "influence.before.actor_treasury_raw")
    after_actor = _event_int(after.get("actor_treasury_raw"), "influence.after.actor_treasury_raw")
    before_trust = _event_int(before.get("recipient_trust_raw"), "influence.before.recipient_trust_raw")
    after_trust = _event_int(after.get("recipient_trust_raw"), "influence.after.recipient_trust_raw")
    if native_state in (0, 2):
        if after_actor != before_actor - cost_raw:
            raise ValueError("influence payer treasury delta is invalid")
        if after_trust != min(100, before_trust + 5):
            raise ValueError("influence trust delta is invalid")
        if after.get("influencer_active") is not True:
            raise ValueError("accepted influence did not activate influencer relation")
        if outcome not in {"accepted", "executed"}:
            raise ValueError("accepted influence has an invalid outcome")
    else:
        if (
            after_actor != before_actor
            or after_trust != before_trust
            or after.get("influencer_active") != before.get("influencer_active")
        ):
            raise ValueError("rejected influence changed a persisted resource")
        if outcome != "rejected":
            raise ValueError("rejected influence has an invalid outcome")
    return EconomicEvent(
        sequence,
        str(path),
        item,
        event,
        kind,
        action_id,
        actor,
        recipient,
        native_state,
        outcome,
        date_raw,
        raw.get("request_id"),
        before,
        after,
        cost_raw=cost_raw,
        opinion_raw=opinion_raw,
        duration_months=duration_months,
    )


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
                for raw_event in _walk_event_objects(raw_item):
                    if raw_event.get("event") not in EVENT_NAMES:
                        continue
                    state.named_events_seen += 1
                    try:
                        sequence += 1
                        event = _collect_one_event(raw_event, path, item_number, state, sequence)
                    except ValueError as exc:
                        _malformed(state, path, item_number, str(exc))
                        continue
                    state.selected_events += 1
                    state.selected.append(event)
                    provenance = event.provenance()
                    state.treasury[event.actor] = ExpectedValue(
                        int(event.after["actor_treasury_raw"]), provenance
                    )
                    if event.kind == "gift":
                        # Influence has no recipient treasury field.  Do not
                        # manufacture one from the payer's value: the save
                        # checker must only assert fields independently
                        # present in the native result schema.
                        state.treasury[event.recipient] = ExpectedValue(
                            int(event.after["recipient_treasury_raw"]), provenance
                        )
                    else:
                        state.trust[(event.recipient, event.actor)] = ExpectedValue(
                            int(event.after["recipient_trust_raw"]), provenance
                        )
                        state.influencer[(event.recipient, event.actor)] = ExpectedValue(
                            bool(event.after["influencer_active"]), provenance
                        )
            file_info["read"] = True
        except (OSError, UnicodeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            state.errors.append(f"event file {path}: {exc}")
    if state.selected_events == 0:
        state.errors.append("no complete and verified R74 gift/influence events selected")
    return state


@dataclass
class FieldValue:
    line: int
    decimal: str | None = None
    raw: int | None = None
    text: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"line": self.line, "decimal": self.decimal, "raw": self.raw, "text": self.text}


@dataclass
class CandidateHit:
    line: int
    path: str
    key: str | None
    value: str | None
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "path": self.path,
            "key": self.key,
            "value": self.value,
            "text": self.text,
        }


@dataclass
class OpinionCapture:
    start_line: int
    depth: int
    fields: dict[str, list[FieldValue]] = field(default_factory=dict)
    end_line: int | None = None


@dataclass
class RelationCapture:
    actor: str
    start_line: int
    depth: int
    fields: dict[str, list[FieldValue]] = field(default_factory=dict)
    opinion: OpinionCapture | None = None
    opinions: list[OpinionCapture] = field(default_factory=list)
    candidates: list[CandidateHit] = field(default_factory=list)
    end_line: int | None = None


@dataclass
class CountryCapture:
    tag: str
    start_line: int
    depth: int
    treasury: list[FieldValue] = field(default_factory=list)
    influenced_by: list[FieldValue] = field(default_factory=list)
    active_relations_count: int = 0
    active_depth: int | None = None
    relation: RelationCapture | None = None
    relations: dict[str, RelationCapture] = field(default_factory=dict)
    candidates: list[CandidateHit] = field(default_factory=list)
    end_line: int | None = None


@dataclass
class SaveState:
    path: str
    source_size: int
    line_count: int
    sha256: str
    sha256_source: str
    hash_passes: int
    top_level_date: str | None
    top_level_save_game: str | None
    countries: dict[str, CountryCapture]
    countries_found: bool
    countries_complete: bool
    final_depth: int
    candidate_hits: list[CandidateHit]
    errors: list[str]


def _candidate_key(key: str | None) -> bool:
    if not key:
        return False
    lowered = key.lower()
    return (
        lowered in INFLUENCER_KEYS
        or lowered in EXPIRY_KEYS
        or lowered in OPINION_KEYS
        or any(word.decode("ascii") in lowered for word in MARKER_WORDS)
    )


def _candidate_path(country: CountryCapture, relation: RelationCapture | None, key: str | None) -> str:
    path = f"countries/{country.tag}"
    if relation is not None:
        path += f"/active_relations/{relation.actor}"
    if key:
        path += f"/{key}"
    return path


def _capture_candidate(
    country: CountryCapture,
    relation: RelationCapture | None,
    line_number: int,
    line: bytes,
    key: str | None,
    value: str | None,
    hits: list[CandidateHit],
) -> None:
    if len(hits) >= MAX_CANDIDATE_HITS:
        return
    lowered = line.lower()
    if not _candidate_key(key) and not any(word in lowered for word in MARKER_WORDS):
        return
    hit = CandidateHit(
        line_number,
        _candidate_path(country, relation, key),
        key,
        value,
        _display_line(line),
    )
    hits.append(hit)
    (relation.candidates if relation is not None else country.candidates).append(hit)


def _finish_opinion(relation: RelationCapture, line_number: int) -> None:
    opinion = relation.opinion
    if opinion is None:
        return
    opinion.end_line = line_number
    relation.opinions.append(opinion)
    relation.opinion = None


def _finish_relation(country: CountryCapture, line_number: int) -> None:
    relation = country.relation
    if relation is None:
        return
    if relation.opinion is not None:
        _finish_opinion(relation, line_number)
    relation.end_line = line_number
    if relation.actor in country.relations:
        raise ValueError(f"duplicate relation block {country.tag}.active_relations.{relation.actor}")
    country.relations[relation.actor] = relation
    country.relation = None


EU4_DATE_RE = re.compile(r"^(?P<year>\d+)\.(?P<month>\d{1,2})\.(?P<day>\d{1,2})$")


def _parse_eu4_date(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    match = EU4_DATE_RE.fullmatch(value.strip())
    if match is None:
        return None
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return year, month, day


def _add_months(value: str | None, months: int) -> str | None:
    parsed = _parse_eu4_date(value)
    if parsed is None or months < 0:
        return None
    year, month, day = parsed
    absolute = year * 12 + (month - 1) + months
    return f"{absolute // 12:04d}.{absolute % 12 + 1}.{day}"


def _month_delta(start: str | None, end: str | None) -> int | None:
    first = _parse_eu4_date(start)
    second = _parse_eu4_date(end)
    if first is None or second is None or first[2] != second[2]:
        return None
    return (second[0] * 12 + second[1] - 1) - (first[0] * 12 + first[1] - 1)


def scan_save(path: Path, save_sha256: str | None, target_tags: set[str]) -> SaveState:
    countries: dict[str, CountryCapture] = {}
    countries_found = False
    countries_complete = False
    countries_depth: int | None = None
    current: CountryCapture | None = None
    depth = 0
    line_count = 0
    source_size = 0
    top_level_date: str | None = None
    top_level_save_game: str | None = None
    candidate_hits: list[CandidateHit] = []
    errors: list[str] = []
    digest = hashlib.sha256() if save_sha256 is None else None
    first_line = True
    try:
        with path.open("rb", buffering=1024 * 1024) as stream:
            for line_number, line in enumerate(stream, 1):
                line_count = line_number
                source_size += len(line)
                if digest is not None:
                    digest.update(line)
                before = depth
                if first_line:
                    first_line = False
                    if not line.startswith(b"EU4txt"):
                        errors.append("save does not begin with EU4txt")

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
                    current is None
                    and countries_found
                    and not countries_complete
                    and countries_depth is not None
                    and before == countries_depth
                ):
                    match = TAG_OPEN_RE.match(_split_line_ending(line).strip())
                    if match is not None:
                        tag = match.group(1).decode("ascii")
                        if tag in target_tags:
                            current = CountryCapture(tag, line_number, before + _brace_delta(line))
                            if tag in countries:
                                raise ValueError(f"duplicate target country block {tag}")

                if current is not None:
                    country_depth = current.depth
                    if before == country_depth:
                        assignment = _assignment(line)
                        if assignment is not None:
                            key, value = assignment
                            if key == "treasury":
                                parsed = _parse_scaled_line(line, "treasury")
                                if parsed is not None:
                                    current.treasury.append(FieldValue(line_number, parsed[0], parsed[1]))
                            if key == "influenced_by":
                                current.influenced_by.append(FieldValue(line_number, text=value))
                            if key == "active_relations":
                                current.active_relations_count += 1
                                if current.active_relations_count > 1:
                                    raise ValueError(f"duplicate active_relations block in {current.tag}")
                                current.active_depth = before + _brace_delta(line)
                            _capture_candidate(current, None, line_number, line, key, value, candidate_hits)

                    if current.active_depth is not None:
                        if current.relation is None and before == current.active_depth:
                            match = TAG_OPEN_RE.match(_split_line_ending(line).strip())
                            if match is not None:
                                actor = match.group(1).decode("ascii")
                                if actor in target_tags:
                                    current.relation = RelationCapture(
                                        actor, line_number, before + _brace_delta(line)
                                    )
                        elif current.relation is not None:
                            relation = current.relation
                            if relation.opinion is not None:
                                opinion = relation.opinion
                                if before == opinion.depth:
                                    assignment = _assignment(line)
                                    if assignment is not None:
                                        key, value = assignment
                                        if key == "current_opinion":
                                            try:
                                                parsed = _parse_raw_line(line, "current_opinion")
                                            except ValueError:
                                                # Most opinion entries are decimal
                                                # values (for example -12.574).
                                                # Preserve those as text; only an
                                                # integral value can match the
                                                # native integer opinion result.
                                                parsed = None
                                            if parsed is None:
                                                opinion.fields.setdefault(key, []).append(
                                                    FieldValue(line_number, text=value)
                                                )
                                            else:
                                                opinion.fields.setdefault(key, []).append(
                                                    FieldValue(line_number, parsed[0], parsed[1])
                                                )
                                        elif key in {"modifier", "date", "expiry_date"}:
                                            opinion.fields.setdefault(key, []).append(
                                                FieldValue(line_number, text=value)
                                            )
                                        _capture_candidate(
                                            current, relation, line_number, line, key, value, candidate_hits
                                        )
                                elif any(word in line.lower() for word in MARKER_WORDS):
                                    _capture_candidate(current, relation, line_number, line, None, None, candidate_hits)
                            elif before == relation.depth:
                                assignment = _assignment(line)
                                if assignment is not None:
                                    key, value = assignment
                                    if key == "opinion" and value == "{":
                                        relation.opinion = OpinionCapture(
                                            line_number, before + _brace_delta(line)
                                        )
                                    elif key == "trust_value":
                                        parsed = _parse_raw_line(line, "trust_value")
                                        if parsed is None:
                                            raw = _parse_int_text(value)
                                            if raw is None:
                                                raise ValueError(
                                                    f"invalid trust_value in {current.tag}/{relation.actor}"
                                                )
                                            relation.fields.setdefault(key, []).append(
                                                FieldValue(line_number, value, raw, value)
                                            )
                                        else:
                                            relation.fields.setdefault(key, []).append(
                                                FieldValue(line_number, parsed[0], parsed[1])
                                            )
                                    elif _candidate_key(key):
                                        relation.fields.setdefault(key, []).append(
                                            FieldValue(line_number, text=value)
                                        )
                                    _capture_candidate(
                                        current, relation, line_number, line, key, value, candidate_hits
                                    )
                            elif any(word in line.lower() for word in MARKER_WORDS):
                                _capture_candidate(current, relation, line_number, line, None, None, candidate_hits)

                    elif any(word in line.lower() for word in MARKER_WORDS):
                        _capture_candidate(current, None, line_number, line, None, None, candidate_hits)

                depth += _brace_delta(line)
                if current is not None and current.relation is not None:
                    if (
                        current.relation.opinion is not None
                        and depth < current.relation.opinion.depth
                    ):
                        _finish_opinion(current.relation, line_number)
                    if depth < current.relation.depth:
                        _finish_relation(current, line_number)
                if current is not None and current.active_depth is not None and depth < current.active_depth:
                    current.active_depth = None
                if current is not None and depth < current.depth:
                    current.end_line = line_number
                    countries[current.tag] = current
                    current = None
                if countries_found and countries_depth is not None and depth < countries_depth:
                    countries_complete = True
            if current is not None:
                errors.append(f"unterminated target country block {current.tag}")
                countries[current.tag] = current
            if not countries_found:
                errors.append("top-level countries block not found")
            if countries_found and not countries_complete:
                errors.append("top-level countries block did not close")
            if depth != 0:
                errors.append(f"final save brace depth is {depth}, expected 0")
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"save scan: {exc}")

    return SaveState(
        path=str(path),
        source_size=source_size,
        line_count=line_count,
        sha256=save_sha256 or (digest.hexdigest() if digest is not None else ""),
        sha256_source="caller_provided_reference" if save_sha256 else "single_streaming_pass",
        hash_passes=0 if save_sha256 else 1,
        top_level_date=top_level_date,
        top_level_save_game=top_level_save_game,
        countries=countries,
        countries_found=countries_found,
        countries_complete=countries_complete,
        final_depth=depth,
        candidate_hits=candidate_hits,
        errors=errors,
    )


def _field_report(field: FieldValue | None) -> dict[str, Any]:
    if field is None:
        return {"present": False}
    return {"present": True, **field.as_dict()}


def _expected_report(value: ExpectedValue) -> dict[str, Any]:
    return value.as_dict()


def _treasury_field(country: CountryCapture | None) -> FieldValue | None:
    if country is None or len(country.treasury) != 1:
        return None
    return country.treasury[0]


def _relation_field(relation: RelationCapture | None, key: str) -> FieldValue | None:
    if relation is None:
        return None
    values = relation.fields.get(key, [])
    if len(values) != 1:
        return None
    return values[0]


def _default_trust_field(
    relation: RelationCapture | None, expected: ExpectedValue
) -> tuple[FieldValue | None, str | None]:
    actual = _relation_field(relation, "trust_value")
    if actual is not None:
        return actual, None
    if relation is not None and expected.value == 50 and TRUST_CONTRACT.is_file():
        return (
            FieldValue(0, "50", 50, "omitted"),
            "native_serializer_default_omitted",
        )
    return None, None


def _candidate_values(relation: RelationCapture | None, keys: frozenset[str]) -> list[dict[str, Any]]:
    if relation is None:
        return []
    rows: list[dict[str, Any]] = []
    for key, values in relation.fields.items():
        if key.lower() in keys:
            for value in values:
                rows.append({"key": key, **value.as_dict()})
    return rows


def _opinion_field(opinion: OpinionCapture | None, key: str) -> FieldValue | None:
    if opinion is None:
        return None
    values = opinion.fields.get(key, [])
    if len(values) != 1:
        return None
    return values[0]


def _find_influence_opinion(relation: RelationCapture | None) -> OpinionCapture | None:
    if relation is None:
        return None
    matches: list[OpinionCapture] = []
    for opinion in relation.opinions:
        modifier = _opinion_field(opinion, "modifier")
        if modifier is not None and modifier.text == INFLUENCE_MODIFIER:
            matches.append(opinion)
    return matches[0] if len(matches) == 1 else None


def _influence_save_checks(
    event_state: EventState, save_state: SaveState
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    influencer_checks: list[dict[str, Any]] = []
    opinion_checks: list[dict[str, Any]] = []
    expiry_checks: list[dict[str, Any]] = []
    errors: list[str] = []
    for event in event_state.selected:
        if event.kind != "influence":
            continue
        country = save_state.countries.get(event.recipient)
        actual_influencer = country.influenced_by[0] if country is not None and len(country.influenced_by) == 1 else None
        expected_active = bool(event.after["influencer_active"])
        active_match = (
            actual_influencer is not None and actual_influencer.text == event.actor
            if expected_active
            else actual_influencer is None or actual_influencer.text != event.actor
        )
        influencer_row = {
            "recipient": event.recipient,
            "actor": event.actor,
            "save_path": f"countries/{event.recipient}/influenced_by",
            "expected": {"active": expected_active, "actor": event.actor},
            "actual": _field_report(actual_influencer),
            "match": active_match,
            "event": event.as_dict(),
        }
        influencer_checks.append(influencer_row)
        if not active_match:
            errors.append(f"influenced_by mismatch or absent for {event.recipient}")

        relation = country.relations.get(event.actor) if country is not None else None
        opinion = _find_influence_opinion(relation)
        modifier_field = _opinion_field(opinion, "modifier")
        current_field = _opinion_field(opinion, "current_opinion")
        date_field = _opinion_field(opinion, "date")
        expiry_flag = _opinion_field(opinion, "expiry_date")
        modifier_match = (
            modifier_field is not None
            and modifier_field.text == INFLUENCE_MODIFIER
            and current_field is not None
            and current_field.raw == event.opinion_raw
        )
        opinion_row = {
            "recipient": event.recipient,
            "actor": event.actor,
            "save_path": f"countries/{event.recipient}/active_relations/{event.actor}/opinion",
            "expected": {"modifier": INFLUENCE_MODIFIER, "current_opinion_raw": event.opinion_raw},
            "actual": {
                "modifier": _field_report(modifier_field),
                "current_opinion": _field_report(current_field),
            },
            "match": modifier_match,
            "event": event.as_dict(),
        }
        opinion_checks.append(opinion_row)
        if not modifier_match:
            errors.append(f"great_power_influence opinion mismatch or absent for {event.recipient}.active_relations.{event.actor}")

        expected_date = _add_months(save_state.top_level_date, int(event.duration_months or 0))
        observed_date = date_field.text if date_field is not None else None
        expiry_match = expected_date is not None and observed_date == expected_date
        expiry_row = {
            "recipient": event.recipient,
            "actor": event.actor,
            "save_path": f"countries/{event.recipient}/active_relations/{event.actor}/opinion/date",
            "expected": {
                "execution_date": save_state.top_level_date,
                "duration_months": event.duration_months,
                "expiry_date": expected_date,
            },
            "actual": {
                "date": _field_report(date_field),
                "expiry_date_flag": _field_report(expiry_flag),
                "month_delta": _month_delta(save_state.top_level_date, observed_date),
            },
            "match": expiry_match,
            "event": event.as_dict(),
        }
        expiry_checks.append(expiry_row)
        if not expiry_match:
            errors.append(f"influence expiry date mismatch or absent for {event.recipient}.active_relations.{event.actor}")
    return {
        "influencer_save_checks": influencer_checks,
        "opinion_modifier_save_checks": opinion_checks,
        "expiry_save_checks": expiry_checks,
    }, errors


def _primary_checks(event_state: EventState, save_state: SaveState) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    treasury_checks: list[dict[str, Any]] = []
    for tag, expected in event_state.treasury.items():
        country = save_state.countries.get(tag)
        actual_field = _treasury_field(country)
        actual = _field_report(actual_field)
        match = actual_field is not None and actual_field.raw == expected.value
        row = {
            "country": tag,
            "save_path": f"countries/{tag}/treasury",
            "expected": _expected_report(expected),
            "actual": actual,
            "match": match,
        }
        treasury_checks.append(row)
        if not match:
            errors.append(f"treasury mismatch or absent for {tag}")
        if country is None:
            errors.append(f"missing country block for treasury target {tag}")
        elif len(country.treasury) != 1:
            errors.append(f"expected one direct treasury field for {tag}, found {len(country.treasury)}")

    trust_checks: list[dict[str, Any]] = []
    for (recipient, actor), expected in event_state.trust.items():
        country = save_state.countries.get(recipient)
        relation = country.relations.get(actor) if country is not None else None
        actual_field, source = _default_trust_field(relation, expected)
        actual = _field_report(actual_field)
        if source is not None:
            actual["source"] = source
            actual["contract"] = str(TRUST_CONTRACT.relative_to(ROOT))
        match = actual_field is not None and actual_field.raw == expected.value
        row = {
            "recipient": recipient,
            "actor": actor,
            "save_path": f"countries/{recipient}/active_relations/{actor}/trust_value",
            "expected": _expected_report(expected),
            "actual": actual,
            "match": match,
        }
        trust_checks.append(row)
        if not match:
            errors.append(f"trust_value mismatch or absent for {recipient}.active_relations.{actor}")
        if country is None:
            errors.append(f"missing recipient country block for {recipient}")
        elif country.active_relations_count != 1:
            errors.append(
                f"expected one active_relations block for {recipient}, found {country.active_relations_count}"
            )
        elif relation is None:
            errors.append(f"missing relation block {recipient}.active_relations.{actor}")

    gift_transfers: list[dict[str, Any]] = []
    influence_runtime: list[dict[str, Any]] = []
    for event in event_state.selected:
        if event.kind == "gift":
            before_actor = int(event.before["actor_treasury_raw"])
            before_recipient = int(event.before["recipient_treasury_raw"])
            after_actor = int(event.after["actor_treasury_raw"])
            after_recipient = int(event.after["recipient_treasury_raw"])
            expected_actor = before_actor - int(event.amount_raw or 0) if event.accepted else before_actor
            expected_recipient = before_recipient + int(event.amount_raw or 0) if event.accepted else before_recipient
            match = after_actor == expected_actor and after_recipient == expected_recipient
            gift_transfers.append(
                {
                    "event": event.as_dict(),
                    "delta": {
                        "actor_raw": after_actor - before_actor,
                        "recipient_raw": after_recipient - before_recipient,
                    },
                    "expected_delta": {
                        "actor_raw": -int(event.amount_raw or 0) if event.accepted else 0,
                        "recipient_raw": int(event.amount_raw or 0) if event.accepted else 0,
                    },
                    "match": match,
                }
            )
            if not match:
                errors.append(f"gift event delta mismatch at {event.path}:{event.item}")
        else:
            influence_runtime.append(
                {
                    "event": event.as_dict(),
                    "payer": event.actor,
                    "native_cost_raw": event.cost_raw,
                    "recipient_trust_after_raw": event.after.get("recipient_trust_raw"),
                    "influencer_active_after": event.after.get("influencer_active"),
                    "duration_months": event.duration_months,
                    "opinion_raw": event.opinion_raw,
                    "runtime_effect_proven": event.accepted,
                }
            )

    influence_save_checks, influence_save_errors = _influence_save_checks(event_state, save_state)
    return {
        "treasury_checks": treasury_checks,
        "trust_checks": trust_checks,
        "gift_transfer_checks": gift_transfers,
        "influence_runtime_checks": influence_runtime,
        **influence_save_checks,
    }, errors + influence_save_errors


def _unproven_save_fields(
    event_state: EventState, save_state: SaveState, checks: dict[str, Any]
) -> dict[str, Any]:
    influence_pairs = list(event_state.influencer)
    rows: dict[str, Any] = {}
    for name, keys, explanation, check_key in (
        (
            "influencer_active",
            INFLUENCER_KEYS,
            "countries/<recipient>/influenced_by binds the native active flag to the actor tag",
            "influencer_save_checks",
        ),
        (
            "expiry",
            EXPIRY_KEYS,
            "the relation opinion date is execution date plus native duration_months",
            "expiry_save_checks",
        ),
        (
            "opinion_modifier",
            OPINION_KEYS,
            "the relation opinion block stores modifier=great_power_influence and current_opinion",
            "opinion_modifier_save_checks",
        ),
    ):
        candidates = [
            hit.as_dict()
            for hit in save_state.candidate_hits
            if hit.key is not None and hit.key.lower() in keys
        ]
        check_rows = checks.get(check_key, [])
        if not influence_pairs:
            status = "not_applicable"
        elif check_rows and all(row.get("match") for row in check_rows):
            status = "verified"
        elif check_rows:
            status = "failed"
        else:
            status = "unproven"
        rows[name] = {
            "status": status,
            "pairs": [
                {"recipient": recipient, "actor": actor, "expected": event_state.influencer[(recipient, actor)].as_dict()}
                for recipient, actor in influence_pairs
            ],
            "checks": check_rows,
            "candidate_save_fields": candidates[:MAX_RECORDS],
            "candidate_truncated": len(candidates) > MAX_RECORDS,
            "explanation": explanation,
        }
    return rows


def build_report(
    event_state: EventState,
    save_state: SaveState,
    save_path: Path,
    prior_report: dict[str, Any] | None,
) -> dict[str, Any]:
    checks, check_errors = _primary_checks(event_state, save_state)
    errors = list(event_state.errors) + list(save_state.errors) + check_errors
    gaps = _unproven_save_fields(event_state, save_state, checks)
    has_unproven = any(row["status"] == "unproven" for row in gaps.values())
    has_failed_contract = any(row["status"] == "failed" for row in gaps.values())
    status = "failed" if errors or has_failed_contract else "incomplete" if has_unproven or not event_state.selected else "passed"
    contract = {
        "treasury": {
            "status": "verified",
            "path": "countries/<tag>/treasury",
            "scale": 1000,
        },
        "trust_value": {
            "status": "verified",
            "path": "countries/<recipient>/active_relations/<actor>/trust_value",
            "default_50_omission": TRUST_CONTRACT.is_file(),
            "contract": str(TRUST_CONTRACT.relative_to(ROOT)) if TRUST_CONTRACT.is_file() else None,
        },
        **gaps,
    }
    return {
        "schema": "r74_economic_save_verify_v1",
        "status": status,
        "errors": errors,
        "evidence_gaps": [
            {"field": name, "status": value["status"], "explanation": value["explanation"]}
            for name, value in gaps.items()
            if value["status"] in {"unproven", "failed"}
        ],
        "contract": contract,
        "events": {
            "files": event_state.files,
            "events_seen": event_state.events_seen,
            "named_events_seen": event_state.named_events_seen,
            "selected_events": event_state.selected_events,
            "malformed_selected": event_state.malformed_selected,
            "records": [event.as_dict() for event in event_state.selected[:MAX_RECORDS]],
            "records_truncated": len(event_state.selected) > MAX_RECORDS,
        },
        "checks": checks,
        "save": {
            "path": str(save_path),
            "size": save_state.source_size,
            "sha256": save_state.sha256,
            "sha256_source": save_state.sha256_source,
            "hash_passes": save_state.hash_passes,
            "line_count": save_state.line_count,
            "top_level_date": save_state.top_level_date,
            "top_level_save_game": save_state.top_level_save_game,
            "countries_found": save_state.countries_found,
            "countries_complete": save_state.countries_complete,
            "target_countries_scanned": sorted(save_state.countries),
            "candidate_field_hits": [hit.as_dict() for hit in save_state.candidate_hits],
            "candidate_field_hits_truncated": len(save_state.candidate_hits) >= MAX_CANDIDATE_HITS,
            "final_brace_depth": save_state.final_depth,
            "single_streaming_pass": True,
            "event_save_lines_or_offsets_used": False,
        },
        "prior_report": prior_report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--events", required=True, nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--save-sha256")
    parser.add_argument("--prior-report", type=Path)
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
    target_tags = {tag for event in event_state.selected for tag in (event.actor, event.recipient)}
    save_state = scan_save(save_path, supplied_sha, target_tags)
    prior_report: dict[str, Any] | None = None
    if args.prior_report is not None:
        prior_path = args.prior_report.expanduser().resolve(strict=False)
        if not prior_path.is_file():
            raise FileNotFoundError(f"prior report does not exist: {prior_path}")
        with prior_path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("prior report must contain a JSON object")
        prior_report = {
            "path": str(prior_path),
            "status": value.get("status"),
            "errors": value.get("errors", []),
        }
    report = build_report(event_state, save_state, save_path, prior_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"status": report["status"], "output": str(output), "errors": len(report["errors"])}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
