#!/usr/bin/env python3
"""Stream the serialized ``war_reparations`` records from an EU4 save.

EU4 stores a war-reparations relation as a small top-level block::

    war_reparations={
        first="PAYING_COUNTRY"
        second="RECEIVING_COUNTRY"
        end_date=1458.8.14
        start_date=1448.8.14
    }

The reader keeps only these bounded blocks.  It does not load the complete
gamestate into memory and it does not change a save.  The public role names
``payer`` and ``claimant`` are a projection of the serialized ``first`` and
``second`` fields; the raw field mapping is retained in every record so a
native-side interpretation can be reviewed separately.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded


HASH_CHUNK = 1024 * 1024
MAX_REPARATIONS_CAPTURE = 128 * 1024
MAX_RAW_EXCERPT = 8 * 1024
MAX_REPARATIONS_RECORDS = 1024
MAX_TRADE_POWER_CAPTURE = 128 * 1024
MAX_TRADE_POWER_RECORDS = 1024
MAX_ANNUL_CAPTURE = 128 * 1024
MAX_ANNUL_RECORDS = 1024
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
WAR_REPARATIONS_RE = re.compile(r"^\s*war_reparations\s*=\s*\{")
TRANSFER_TRADE_POWER_RE = re.compile(r"^\s*transfer_trade_power\s*=\s*\{")
ANNUL_TREATIES_RE = re.compile(r"^\s*annul_treaties\s*=\s*\{")
SERIALIZED_FIELD_NAMES = ("first", "second", "start_date", "end_date")
TRADE_POWER_FIELD_NAMES = (
    "amount", "is_enforced", "first", "second", "start_date", "end_date")
TRADE_POWER_AMOUNT_SCALE = 1000


class TreatySaveParseError(RuntimeError):
    """Raised when a save cannot be inspected within the bounded contract."""


def validate_tag(value: str, option: str) -> str:
    tag = value.strip().upper()
    if not TAG_RE.fullmatch(tag):
        raise argparse.ArgumentTypeError(
            f"{option} must be an uppercase EU4 country tag of 1-6 letters/digits"
        )
    return tag


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _scalar_values(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_scalar_values(item))
        return result
    if value is None:
        return []
    return [str(value)]


def _last_field(fields: dict[str, Any], key: str) -> tuple[str | None, bool]:
    values = _scalar_values(fields.get(key))
    if not values:
        return None, False
    return bounded.unquote(values[-1]), len(values) > 1


def _inline_serialized_fields(
    body: str, field_names: tuple[str, ...] = SERIALIZED_FIELD_NAMES
) -> dict[str, Any]:
    """Recover known scalar fields when a fixture uses one-line blocks."""

    fields: dict[str, Any] = {}
    for key in field_names:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(key)}\s*=\s*(\"(?:\\\\.|[^\"])*\"|[^\s}}]+)"
        )
        values = [match.group(1) for match in pattern.finditer(body)]
        if values:
            fields[key] = values[0] if len(values) == 1 else values
    return fields


def _date_tuple(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    text = value.strip().strip('"')
    parts = text.split(".")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
    except ValueError:
        return None
    if year < 0 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return year, month, day


def _date_status(
    save_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    save_key = _date_tuple(save_date)
    start_key = _date_tuple(start_date)
    end_key = _date_tuple(end_date)
    result: dict[str, Any] = {
        "save_date": save_date,
        "start_date": start_date,
        "end_date": end_date,
        "comparison_available": bool(save_key and start_key and end_key),
        "window_contains_save_date": None,
        "status": "unknown",
    }
    if not (save_key and start_key and end_key):
        return result
    # The status is deliberately a serialized date-window observation.  EU4
    # may perform expiry work at a date tick, so callers should use the raw
    # start/end fields when a boundary-day decision matters.
    in_window = start_key <= save_key < end_key
    result["window_contains_save_date"] = in_window
    result["status"] = "active" if in_window else (
        "future" if save_key < start_key else "expired_or_boundary"
    )
    return result


def parse_war_reparations_block(
    text: str,
    *,
    line_start: int,
    line_end: int | None,
    bytes_captured: int,
    bytes_seen: int,
    complete: bool,
    scope_depth: int,
    save_date: str | None,
    index: int,
) -> dict[str, Any]:
    """Parse one bounded serialized block while retaining source field names."""

    record: dict[str, Any] = {
        "index": index,
        "kind": "war_reparations",
        "line_start": line_start,
        "line_end": line_end,
        "scope_depth": scope_depth,
        "scope": "gamestate_top_level" if scope_depth == 1 else "nested_gamestate",
        "complete": bool(complete),
        "bytes_captured": bytes_captured,
        "bytes_seen": bytes_seen,
        "fields": {},
        "payer": None,
        "claimant": None,
        "start_date": None,
        "end_date": None,
        "date_status": _date_status(save_date, None, None),
        "unknown": [],
    }
    if not complete:
        record["unknown"].append("war_reparations_capture_incomplete")
        return record

    try:
        open_index = text.find("{")
        body = bounded.extract_block(text, open_index)
        entries = bounded.top_level_entries(body)
        fields, _blocks = bounded.flatten_entries(entries)
        # The shipped saves put one scalar on each line.  The small fallback
        # also makes the bounded reader safe for compact test fixtures without
        # changing the raw fields retained from the native block.
        fields.update(_inline_serialized_fields(body))
    except Exception as exc:
        record["unknown"].append(f"war_reparations_parse_error:{exc}")
        return record

    raw_fields: dict[str, Any] = {}
    for key, value in fields.items():
        raw_fields[key] = value
    record["fields"] = raw_fields
    first, duplicate_first = _last_field(fields, "first")
    second, duplicate_second = _last_field(fields, "second")
    start_date, duplicate_start = _last_field(fields, "start_date")
    end_date, duplicate_end = _last_field(fields, "end_date")
    record["payer"] = first
    record["claimant"] = second
    record["start_date"] = start_date
    record["end_date"] = end_date
    record["date_status"] = _date_status(save_date, start_date, end_date)
    record["role_mapping"] = {
        "payer": {"serialized_field": "first", "value": first},
        "claimant": {"serialized_field": "second", "value": second},
    }
    if first is None:
        record["unknown"].append("first_not_found")
    if second is None:
        record["unknown"].append("second_not_found")
    if start_date is None:
        record["unknown"].append("start_date_not_found")
    if end_date is None:
        record["unknown"].append("end_date_not_found")
    if duplicate_first:
        record["unknown"].append("duplicate_first")
    if duplicate_second:
        record["unknown"].append("duplicate_second")
    if duplicate_start:
        record["unknown"].append("duplicate_start_date")
    if duplicate_end:
        record["unknown"].append("duplicate_end_date")

    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= MAX_RAW_EXCERPT:
        record["raw_excerpt"] = text
        record["raw_excerpt_truncated"] = False
    else:
        record["raw_excerpt"] = encoded[:MAX_RAW_EXCERPT].decode("utf-8", "replace")
        record["raw_excerpt_truncated"] = True
    return record


def _trade_power_amount_raw(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        amount = Decimal(value.strip().strip('"'))
        scaled = amount * TRADE_POWER_AMOUNT_SCALE
    except (InvalidOperation, ValueError):
        return None
    if (not scaled.is_finite()
            or scaled != scaled.to_integral_value()
            or scaled < 0):
        return None
    raw = int(scaled)
    return raw if raw <= 0x7FFFFFFF else None


def _serialized_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().strip('"').casefold()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    return None


def parse_transfer_trade_power_block(
    text: str,
    *,
    line_start: int,
    line_end: int | None,
    bytes_captured: int,
    bytes_seen: int,
    complete: bool,
    scope_depth: int,
    save_date: str | None,
    index: int,
) -> dict[str, Any]:
    """Parse one bounded serialized ``transfer_trade_power`` block.

    The save format uses ``amount`` and ``is_enforced`` for the two fields
    written by the native treaty serializer.  ``end_date`` is optional in
    observed records; absence is retained as an explicit raw-date absence.
    """

    record: dict[str, Any] = {
        "index": index,
        "kind": "transfer_trade_power",
        "line_start": line_start,
        "line_end": line_end,
        "scope_depth": scope_depth,
        "scope": "gamestate_top_level" if scope_depth == 1 else "nested_gamestate",
        "complete": bool(complete),
        "fields_complete": False,
        "bytes_captured": bytes_captured,
        "bytes_seen": bytes_seen,
        "fields": {},
        "source": None,
        "beneficiary": None,
        "amount_raw": None,
        "amount_scale": TRADE_POWER_AMOUNT_SCALE,
        "enforced": None,
        "start_date_raw": None,
        "end_date_raw": None,
        "raw_dates": {"start_date": None, "end_date": None},
        "unknown": [],
    }
    if not complete:
        record["unknown"].append("transfer_trade_power_capture_incomplete")
        return record

    try:
        open_index = text.find("{")
        body = bounded.extract_block(text, open_index)
        entries = bounded.top_level_entries(body)
        fields, _blocks = bounded.flatten_entries(entries)
        fields.update(_inline_serialized_fields(body, TRADE_POWER_FIELD_NAMES))
    except Exception as exc:
        record["unknown"].append(f"transfer_trade_power_parse_error:{exc}")
        return record

    record["fields"] = dict(fields)
    source, duplicate_source = _last_field(fields, "first")
    beneficiary, duplicate_beneficiary = _last_field(fields, "second")
    amount_text, duplicate_amount = _last_field(fields, "amount")
    enforced_text, duplicate_enforced = _last_field(fields, "is_enforced")
    start_date, duplicate_start = _last_field(fields, "start_date")
    end_date, duplicate_end = _last_field(fields, "end_date")
    amount_raw = _trade_power_amount_raw(amount_text)
    enforced = _serialized_bool(enforced_text)
    record.update({
        "source": source,
        "beneficiary": beneficiary,
        "amount_raw": amount_raw,
        "enforced": enforced,
        "start_date_raw": start_date,
        "end_date_raw": end_date,
        "raw_dates": {"start_date": start_date, "end_date": end_date},
        "role_mapping": {
            "source": {"serialized_field": "first", "value": source},
            "beneficiary": {"serialized_field": "second", "value": beneficiary},
        },
    })
    required = (
        source is not None,
        beneficiary is not None,
        amount_raw is not None,
        enforced is not None,
        start_date is not None,
    )
    record["fields_complete"] = all(required)
    if source is None:
        record["unknown"].append("first_not_found")
    if beneficiary is None:
        record["unknown"].append("second_not_found")
    if amount_text is None:
        record["unknown"].append("amount_not_found")
    elif amount_raw is None:
        record["unknown"].append("amount_invalid")
    if enforced_text is None:
        record["unknown"].append("is_enforced_not_found")
    elif enforced is None:
        record["unknown"].append("is_enforced_invalid")
    if start_date is None:
        record["unknown"].append("start_date_not_found")
    if duplicate_source:
        record["unknown"].append("duplicate_first")
    if duplicate_beneficiary:
        record["unknown"].append("duplicate_second")
    if duplicate_amount:
        record["unknown"].append("duplicate_amount")
    if duplicate_enforced:
        record["unknown"].append("duplicate_is_enforced")
    if duplicate_start:
        record["unknown"].append("duplicate_start_date")
    if duplicate_end:
        record["unknown"].append("duplicate_end_date")

    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= MAX_RAW_EXCERPT:
        record["raw_excerpt"] = text
        record["raw_excerpt_truncated"] = False
    else:
        record["raw_excerpt"] = encoded[:MAX_RAW_EXCERPT].decode("utf-8", "replace")
        record["raw_excerpt_truncated"] = True
    return record


def parse_annul_treaties_block(
    text: str,
    *,
    line_start: int,
    line_end: int | None,
    bytes_captured: int,
    bytes_seen: int,
    complete: bool,
    scope_depth: int,
    save_date: str | None,
    index: int,
) -> dict[str, Any]:
    """Parse one directed serialized annul_treaties block."""
    record: dict[str, Any] = {
        "index": index,
        "kind": "annul_treaties",
        "line_start": line_start,
        "line_end": line_end,
        "scope_depth": scope_depth,
        "scope": "gamestate_top_level" if scope_depth == 1 else "nested_gamestate",
        "complete": bool(complete),
        "fields_complete": False,
        "bytes_captured": bytes_captured,
        "bytes_seen": bytes_seen,
        "fields": {},
        "country": None,
        "partner": None,
        "start_date_raw": None,
        "end_date_raw": None,
        "raw_dates": {"start_date": None, "end_date": None},
        "unknown": [],
    }
    if not complete:
        record["unknown"].append("annul_treaties_capture_incomplete")
        return record
    try:
        open_index = text.find("{")
        body = bounded.extract_block(text, open_index)
        entries = bounded.top_level_entries(body)
        fields, _blocks = bounded.flatten_entries(entries)
        fields.update(_inline_serialized_fields(body, SERIALIZED_FIELD_NAMES))
    except Exception as exc:
        record["unknown"].append(f"annul_treaties_parse_error:{exc}")
        return record
    record["fields"] = dict(fields)
    country, duplicate_country = _last_field(fields, "first")
    partner, duplicate_partner = _last_field(fields, "second")
    start_date, duplicate_start = _last_field(fields, "start_date")
    end_date, duplicate_end = _last_field(fields, "end_date")
    record.update({
        "country": country,
        "partner": partner,
        "start_date_raw": start_date,
        "end_date_raw": end_date,
        "raw_dates": {"start_date": start_date, "end_date": end_date},
        "fields_complete": country is not None and partner is not None
        and start_date is not None,
        "role_mapping": {
            "country": {"serialized_field": "first", "value": country},
            "partner": {"serialized_field": "second", "value": partner},
        },
        "date_status": _date_status(save_date, start_date, end_date),
    })
    for field, value in (("first", country), ("second", partner),
                         ("start_date", start_date)):
        if value is None:
            record["unknown"].append(f"{field}_not_found")
    if duplicate_country:
        record["unknown"].append("duplicate_first")
    if duplicate_partner:
        record["unknown"].append("duplicate_second")
    if duplicate_start:
        record["unknown"].append("duplicate_start_date")
    if duplicate_end:
        record["unknown"].append("duplicate_end_date")
    encoded = text.encode("utf-8", "replace")
    record["raw_excerpt"] = (
        text if len(encoded) <= MAX_RAW_EXCERPT
        else encoded[:MAX_RAW_EXCERPT].decode("utf-8", "replace"))
    record["raw_excerpt_truncated"] = len(encoded) > MAX_RAW_EXCERPT
    return record


class TreatySaveScanner:
    """Single-pass bounded scanner for serialized peace-treaty blocks."""

    def __init__(self, save_date_hint: str | None = None):
        self.depth = 0
        self.line_count = 0
        self.header_line: str | None = None
        self.date = save_date_hint
        self.date_line: int | None = None
        self.player: str | None = None
        self.player_line: int | None = None
        self.current: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self.total_records = 0
        self.records_truncated = False
        self.trade_power_records: list[dict[str, Any]] = []
        self.trade_power_total_records = 0
        self.trade_power_records_truncated = False
        self.annul_records: list[dict[str, Any]] = []
        self.annul_total_records = 0
        self.annul_records_truncated = False
        self.unknown: list[str] = []

    def _finish(self, end_line: int | None, complete: bool) -> None:
        if self.current is None:
            return
        current = self.current
        text = "".join(current["lines"])
        captured_complete = complete and not current["truncated"]
        bytes_captured = sum(
            len(line.encode("utf-8", "replace")) for line in current["lines"]
        )
        if current["kind"] == "war_reparations":
            self.total_records += 1
            record = parse_war_reparations_block(
                text,
                line_start=current["start_line"],
                line_end=end_line,
                bytes_captured=bytes_captured,
                bytes_seen=current["bytes_seen"],
                complete=captured_complete,
                scope_depth=current["scope_depth"],
                save_date=self.date,
                index=self.total_records,
            )
            if len(self.records) < MAX_REPARATIONS_RECORDS:
                self.records.append(record)
            else:
                self.records_truncated = True
        elif current["kind"] == "transfer_trade_power":
            self.trade_power_total_records += 1
            record = parse_transfer_trade_power_block(
                text,
                line_start=current["start_line"],
                line_end=end_line,
                bytes_captured=bytes_captured,
                bytes_seen=current["bytes_seen"],
                complete=captured_complete,
                scope_depth=current["scope_depth"],
                save_date=self.date,
                index=self.trade_power_total_records,
            )
            if len(self.trade_power_records) < MAX_TRADE_POWER_RECORDS:
                self.trade_power_records.append(record)
            else:
                self.trade_power_records_truncated = True
        else:
            self.annul_total_records += 1
            record = parse_annul_treaties_block(
                text,
                line_start=current["start_line"],
                line_end=end_line,
                bytes_captured=bytes_captured,
                bytes_seen=current["bytes_seen"],
                complete=captured_complete,
                scope_depth=current["scope_depth"],
                save_date=self.date,
                index=self.annul_total_records,
            )
            if len(self.annul_records) < MAX_ANNUL_RECORDS:
                self.annul_records.append(record)
            else:
                self.annul_records_truncated = True
        self.current = None

    def consume(self, stream: TextIO) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            if line_number == 1:
                self.header_line = line.rstrip("\r\n")
            before = self.depth
            if before == 0:
                date_match = re.match(r"^\s*date\s*=\s*([^\r\n]+)", line)
                if date_match and self.date is None:
                    self.date = bounded.unquote(date_match.group(1).strip())
                    self.date_line = line_number
                player_match = re.match(r"^\s*player\s*=\s*([^\r\n]+)", line)
                if player_match and self.player is None:
                    self.player = bounded.unquote(player_match.group(1).strip())
                    self.player_line = line_number

            if self.current is not None and line_number != self.current["start_line"]:
                current = self.current
                current["bytes_seen"] += len(line.encode("utf-8", "replace"))
                if not current["truncated"]:
                    capture_limit = (
                        MAX_REPARATIONS_CAPTURE
                        if current["kind"] == "war_reparations"
                        else MAX_TRADE_POWER_CAPTURE
                        if current["kind"] == "transfer_trade_power"
                        else MAX_ANNUL_CAPTURE)
                    if current["bytes_seen"] <= capture_limit:
                        current["lines"].append(line)
                    else:
                        current["truncated"] = True
                        current["lines"] = []

            if self.current is None and (
                    WAR_REPARATIONS_RE.match(line)
                    or TRANSFER_TRADE_POWER_RE.match(line)
                    or ANNUL_TREATIES_RE.match(line)):
                kind = (
                    "war_reparations"
                    if WAR_REPARATIONS_RE.match(line)
                    else "transfer_trade_power"
                    if TRANSFER_TRADE_POWER_RE.match(line)
                    else "annul_treaties")
                self.current = {
                    "kind": kind,
                    "start_line": line_number,
                    "scope_depth": before,
                    "lines": [line],
                    "bytes_seen": len(line.encode("utf-8", "replace")),
                    "truncated": False,
                    "block_depth": before + bounded.brace_delta(line),
                }

            delta = bounded.brace_delta(line)
            self.depth += delta
            if (
                self.current is not None
                and self.depth == self.current["scope_depth"]
                and before >= self.current["block_depth"]
            ):
                self._finish(line_number, True)

        if self.current is not None:
            self._finish(None, False)


def _normalize_pair(
    first: str | None,
    second: str | None,
    first_name: str,
    second_name: str,
) -> tuple[str | None, str | None]:
    """Validate an optional directed country pair."""

    if (first is None) != (second is None):
        raise TreatySaveParseError(
            f"{first_name} and {second_name} must be supplied together"
        )
    if first is None:
        return None, None
    normalized_first = validate_tag(first, first_name)
    normalized_second = validate_tag(second, second_name)
    if normalized_first == normalized_second:
        raise TreatySaveParseError(f"{first_name} and {second_name} must differ")
    return normalized_first, normalized_second


def scan_save(
    path: Path,
    payer: str | None = None,
    claimant: str | None = None,
    *,
    trade_power_source: str | None = None,
    trade_power_beneficiary: str | None = None,
    annul_country: str | None = None,
    annul_partners: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Scan one save and return bounded treaty records plus pair matches.

    The positional ``payer``/``claimant`` query is retained for callers of the
    original war-reparations helper.  The transfer-trade-power query is a
    separate directed pair because its serialized role names and amount fields
    differ from war reparations.
    """

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise TreatySaveParseError(f"save path is not a file: {resolved}")
    payer, claimant = _normalize_pair(payer, claimant, "payer", "claimant")
    trade_power_source, trade_power_beneficiary = _normalize_pair(
        trade_power_source,
        trade_power_beneficiary,
        "trade_power_source",
        "trade_power_beneficiary",
    )
    if (annul_country is None) != (annul_partners is None):
        raise TreatySaveParseError(
            "annul_country and annul_partners must be supplied together")
    if annul_country is not None:
        annul_country = validate_tag(annul_country, "annul_country")
        if (not isinstance(annul_partners, (list, tuple))
                or not 1 <= len(annul_partners) <= 16):
            raise TreatySaveParseError("annul_partners must contain 1..16 tags")
        annul_values = [validate_tag(item, "annul_partner")
                        for item in annul_partners]
        if (len(set(annul_values)) != len(annul_values)
                or annul_values != sorted(annul_values)
                or annul_country in annul_values):
            raise TreatySaveParseError(
                "annul_partners must be sorted, unique, and differ from annul_country")
        annul_partners = annul_values
    if payer is None and trade_power_source is None and annul_country is None:
        raise TreatySaveParseError(
            "at least one directed pair is required: payer/claimant or "
            "trade_power_source/trade_power_beneficiary"
        )

    source = bounded.detect_container(resolved)
    source["sha256"] = sha256_file(resolved)
    scanner = TreatySaveScanner()
    with bounded.open_gamestate(resolved, source) as stream:
        scanner.consume(stream)

    records = scanner.records
    matches = (
        [
            record
            for record in records
            if record.get("complete")
            and record.get("payer") == payer
            and record.get("claimant") == claimant
        ]
        if payer is not None
        else []
    )
    reverse_matches = (
        [
            record
            for record in records
            if record.get("complete")
            and record.get("payer") == claimant
            and record.get("claimant") == payer
        ]
        if payer is not None
        else []
    )
    trade_records = scanner.trade_power_records
    trade_matches = (
        [
            record
            for record in trade_records
            if record.get("complete")
            and record.get("fields_complete")
            and record.get("source") == trade_power_source
            and record.get("beneficiary") == trade_power_beneficiary
        ]
        if trade_power_source is not None
        else []
    )
    trade_reverse_matches = (
        [
            record
            for record in trade_records
            if record.get("complete")
            and record.get("fields_complete")
            and record.get("source") == trade_power_beneficiary
            and record.get("beneficiary") == trade_power_source
        ]
        if trade_power_source is not None
        else []
    )
    annul_records = scanner.annul_records
    exact_annul = (
        [record for record in annul_records
         if record.get("complete") and record.get("fields_complete")
         and record.get("country") == annul_country
         and record.get("partner") in (annul_partners or [])]
        if annul_country is not None else [])
    reverse_annul = (
        [record for record in annul_records
         if record.get("complete") and record.get("fields_complete")
         and record.get("partner") == annul_country
         and record.get("country") in (annul_partners or [])]
        if annul_country is not None else [])
    unknown = list(scanner.unknown)
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    if payer is not None and scanner.total_records == 0:
        unknown.append("war_reparations_block_not_found")
    if payer is not None and scanner.records_truncated:
        unknown.append(f"war_reparations_record_limit_reached:{MAX_REPARATIONS_RECORDS}")
    if trade_power_source is not None and scanner.trade_power_total_records == 0:
        unknown.append("transfer_trade_power_block_not_found")
    if trade_power_source is not None and scanner.trade_power_records_truncated:
        unknown.append(
            "transfer_trade_power_record_limit_reached:"
            f"{MAX_TRADE_POWER_RECORDS}"
        )
    if annul_country is not None and scanner.annul_total_records == 0:
        unknown.append("annul_treaties_block_not_found")
    if annul_country is not None and scanner.annul_records_truncated:
        unknown.append(f"annul_treaties_record_limit_reached:{MAX_ANNUL_RECORDS}")
    for record in records:
        unknown.extend(
            f"record_{record['index']}:{item}" for item in record.get("unknown", [])
        )
    for record in trade_records:
        unknown.extend(
            f"transfer_trade_power_record_{record['index']}:{item}"
            for item in record.get("unknown", [])
        )
    for record in annul_records:
        unknown.extend(
            f"annul_treaties_record_{record['index']}:{item}"
            for item in record.get("unknown", [])
        )

    query = {
        "payer": payer,
        "claimant": claimant,
        "exact_pair_present": bool(matches),
        "matching_count": len(matches),
        "reverse_pair_present": bool(reverse_matches),
        "reverse_matching_count": len(reverse_matches),
        "matching_records": matches,
        "reverse_matching_records": reverse_matches,
        "trade_power_source": trade_power_source,
        "trade_power_beneficiary": trade_power_beneficiary,
        "trade_power_exact_pair_present": bool(trade_matches),
        "trade_power_matching_count": len(trade_matches),
        "trade_power_reverse_pair_present": bool(trade_reverse_matches),
        "trade_power_reverse_matching_count": len(trade_reverse_matches),
        "trade_power_matching_records": trade_matches,
        "trade_power_reverse_matching_records": trade_reverse_matches,
        "annul_country": annul_country,
        "annul_partners": list(annul_partners or []),
        "annul_exact_pair_present": bool(exact_annul),
        "annul_matching_count": len(exact_annul),
        "annul_reverse_pair_present": bool(reverse_annul),
        "annul_reverse_matching_count": len(reverse_annul),
        "annul_matching_records": exact_annul,
        "annul_reverse_matching_records": reverse_annul,
    }
    trade_power_snapshot = {
        "records": trade_records,
        "total_records": scanner.trade_power_total_records,
        "records_returned": len(trade_records),
        "records_truncated": scanner.trade_power_records_truncated,
        "role_fields": {
            "source": "first",
            "beneficiary": "second",
            "amount": "amount",
            "enforced": "is_enforced",
            "start_date": "start_date",
            "end_date": "end_date",
        },
        "amount_scale": TRADE_POWER_AMOUNT_SCALE,
    }
    annul_snapshot = {
        "records": annul_records,
        "total_records": scanner.annul_total_records,
        "records_returned": len(annul_records),
        "records_truncated": scanner.annul_records_truncated,
        "role_fields": {
            "country": "first", "partner": "second",
            "start_date": "start_date", "end_date": "end_date",
        },
    }

    return {
        "source": source,
        "metadata": {
            "first_line": scanner.header_line,
            "date": scanner.date,
            "date_line": scanner.date_line,
            "player": scanner.player,
            "player_line": scanner.player_line,
        },
        "parse": {
            "gamestate_line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "war_reparations_block_count": scanner.total_records,
            "war_reparations_records_complete": not scanner.records_truncated,
            "transfer_trade_power_block_count": scanner.trade_power_total_records,
            "transfer_trade_power_records_complete": not scanner.trade_power_records_truncated,
            "annul_treaties_block_count": scanner.annul_total_records,
            "annul_treaties_records_complete": not scanner.annul_records_truncated,
            "unknown": unknown,
        },
        "query": query,
        "war_reparations": {
            "records": records,
            "total_records": scanner.total_records,
            "records_returned": len(records),
            "records_truncated": scanner.records_truncated,
            "role_fields": {
                "payer": "first",
                "claimant": "second",
                "start_date": "start_date",
                "end_date": "end_date",
            },
        },
        "transfer_trade_power": trade_power_snapshot,
        "annul_treaties": annul_snapshot,
    }


def build_payload(
    save: Path,
    payer: str | None = None,
    claimant: str | None = None,
    *,
    trade_power_source: str | None = None,
    trade_power_beneficiary: str | None = None,
    annul_country: str | None = None,
    annul_partners: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    snapshot = scan_save(
        save,
        payer,
        claimant,
        trade_power_source=trade_power_source,
        trade_power_beneficiary=trade_power_beneficiary,
        annul_country=annul_country,
        annul_partners=annul_partners,
    )
    return {
        "tool": {
            "name": "work/inspect_peace_treaty_save.py",
            "version": 1,
            "streaming": True,
            "whole_gamestate_read": False,
            "hash_chunk_bytes": HASH_CHUNK,
            "war_reparations_capture_limit_bytes": MAX_REPARATIONS_CAPTURE,
            "transfer_trade_power_capture_limit_bytes": MAX_TRADE_POWER_CAPTURE,
            "max_records_returned": MAX_REPARATIONS_RECORDS,
            "serialized_role_mapping": {
                "payer": "first",
                "claimant": "second",
                "trade_power_source": "first",
                "trade_power_beneficiary": "second",
                "trade_power_amount": "amount",
                "trade_power_enforced": "is_enforced",
            },
            "trade_power_amount_scale": TRADE_POWER_AMOUNT_SCALE,
            "annul_treaties_capture_limit_bytes": MAX_ANNUL_CAPTURE,
            "annul_treaties_role_mapping": {
                "country": "first", "partner": "second",
                "start_date": "start_date", "end_date": "end_date",
            },
        },
        "save": snapshot,
        "limitations": [
            "R47A 结果存档实际观察到的 war_reparations 块位于 gamestate 顶层，字段为 first、second、start_date、end_date。",
            "payer/claimant 是 first/second 的结构化投影；每条记录保留 fields 和 role_mapping，便于与原生方向合同核对。",
            "date_status 只按保存日期与序列化起止日期做窗口观察；结束日边界不替代原生到期规则。",
            "没有匹配记录表示该存档没有对应方向的序列化 war_reparations，不表示请求一定不合法或尚未结算。",
            "transfer_trade_power 的 amount 按序列化小数乘 1000 保留为 amount_raw；end_date 缺失时仍保留 raw_dates 并按其余字段判断记录完整。",
            "annul_treaties 按 first/second 保留有向 country/partner；exact 与 reverse 方向分别报告，end_date 缺失时保留为 null。",
        ],
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def render_report(payload: dict[str, Any]) -> str:
    save = payload["save"]
    query = save["query"]
    source = save["source"]
    metadata = save["metadata"]
    records = save["war_reparations"]["records"]
    trade_snapshot = save.get("transfer_trade_power", {
        "records": [], "total_records": 0,
    })
    trade_records = trade_snapshot["records"]
    trade_requested = query.get("trade_power_source") is not None
    trade_visible = trade_requested or bool(trade_records)
    annul_snapshot = save.get("annul_treaties", {
        "records": [], "total_records": 0,
    })
    annul_records = annul_snapshot["records"]
    annul_requested = query.get("annul_country") is not None
    annul_visible = annul_requested or bool(annul_records)
    lines = [
        ("# 和平条约存档结构检查"
         if trade_requested or annul_requested else "# 战争赔款存档结构检查"),
        "",
        (
            "工具按行扫描 EU4 gamestate，只保留相关和平条约块；完整存档不进入内存。"
            if trade_requested or annul_requested
            else "工具按行扫描 EU4 gamestate，只保留 war_reparations 块；完整存档不进入内存。"
        ),
        "",
        f"save={source.get('path')}",
        f"size_bytes={source.get('size_bytes')} sha256={source.get('sha256')}",
        f"container={source.get('container')} gamestate={source.get('gamestate_member')}",
        f"date={metadata.get('date')} player={metadata.get('player')}",
        f"query payer={query['payer']} claimant={query['claimant']}",
        f"exact_pair_present={query['exact_pair_present']} matching_count={query['matching_count']}",
        f"reverse_pair_present={query['reverse_pair_present']} reverse_matching_count={query['reverse_matching_count']}",
        *([
            f"trade_query source={query.get('trade_power_source')} beneficiary={query.get('trade_power_beneficiary')}",
            f"trade_exact_pair_present={query.get('trade_power_exact_pair_present', False)} trade_matching_count={query.get('trade_power_matching_count', 0)}",
            f"trade_reverse_pair_present={query.get('trade_power_reverse_pair_present', False)} trade_reverse_matching_count={query.get('trade_power_reverse_matching_count', 0)}",
        ] if trade_visible else []),
        *([
            f"annul_query country={query.get('annul_country')} partners={query.get('annul_partners', [])}",
            f"annul_exact_pair_present={query.get('annul_exact_pair_present', False)} annul_matching_count={query.get('annul_matching_count', 0)}",
            f"annul_reverse_pair_present={query.get('annul_reverse_pair_present', False)} annul_reverse_matching_count={query.get('annul_reverse_matching_count', 0)}",
        ] if annul_visible else []),
        "",
        "## war_reparations 序列化字段",
        "",
        "- `first` 映射为付款国 `payer`。",
        "- `second` 映射为受益国 `claimant`。",
        "- `start_date` 和 `end_date` 原样保留；`date_status` 只表示保存日期窗口观察。",
        "",
        f"共发现 {save['war_reparations']['total_records']} 个 war_reparations 块，返回 {len(records)} 个。",
        "",
    ]
    for record in records:
        lines.extend([
            f"### 记录 {record['index']}（行 {record['line_start']}–{record['line_end']}）",
            "",
            f"payer={record.get('payer')} claimant={record.get('claimant')} ",
            f"start_date={record.get('start_date')} end_date={record.get('end_date')} ",
            f"date_status={record.get('date_status', {}).get('status')}",
            "",
            f"fields={_json_text(record.get('fields', {}))}",
            "",
        ])
    if trade_visible:
        lines.extend([
            "## transfer_trade_power 序列化字段",
            "",
            "- `first` 映射为关系来源国 `source`，`second` 映射为受益国 `beneficiary`。",
            "- `amount` 是序列化小数；`amount_raw` 为其乘以 1000 的整数投影。",
            "- `is_enforced` 映射为 `enforced`；`end_date` 缺失时 `raw_dates.end_date` 保留为 null。",
            "",
            f"共发现 {trade_snapshot['total_records']} 个 transfer_trade_power 块，返回 {len(trade_records)} 个。",
            "",
        ])
        for record in trade_records:
            lines.extend([
                f"### 记录 {record['index']}（行 {record['line_start']}–{record['line_end']}）",
                "",
                f"source={record.get('source')} beneficiary={record.get('beneficiary')} ",
                f"amount_raw={record.get('amount_raw')} enforced={record.get('enforced')} ",
                f"start_date_raw={record.get('start_date_raw')} end_date_raw={record.get('end_date_raw')}",
                "",
                f"fields={_json_text(record.get('fields', {}))}",
                "",
            ])
    if annul_visible:
        lines.extend([
            "## annul_treaties 序列化字段",
            "",
            "- `first` 映射为关系拥有国 `country`，`second` 映射为被取消条约的 `partner`。",
            "- exact 与 reverse 方向分别报告；`end_date` 缺失时保留为 null。",
            "",
            f"共发现 {annul_snapshot['total_records']} 个 annul_treaties 块，返回 {len(annul_records)} 个。",
            "",
        ])
        for record in annul_records:
            lines.extend([
                f"### 记录 {record['index']}（行 {record['line_start']}–{record['line_end']}）",
                "",
                f"country={record.get('country')} partner={record.get('partner')} ",
                f"start_date_raw={record.get('start_date_raw')} end_date_raw={record.get('end_date_raw')}",
                "",
                f"fields={_json_text(record.get('fields', {}))}",
                "",
            ])
    lines.extend([
        "## 解析完整性",
        "",
        _json_text(save["parse"]),
        "",
        "没有匹配的方向只说明当前存档没有该方向的序列化记录；它不替代原生规则、执行结果或条款接受度判断。",
        "",
    ])
    return "\n".join(lines)


def _output_paths(output: Path) -> tuple[Path, Path]:
    output = output.expanduser().resolve()
    if output.suffix.casefold() == ".json":
        return output, output.with_suffix(".md")
    return output / "peace-treaty-save.json", output / "peace-treaty-save.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--payer", type=lambda value: validate_tag(value, "--payer"))
    parser.add_argument("--claimant", type=lambda value: validate_tag(value, "--claimant"))
    parser.add_argument(
        "--trade-power-source",
        type=lambda value: validate_tag(value, "--trade-power-source"),
    )
    parser.add_argument(
        "--trade-power-beneficiary",
        type=lambda value: validate_tag(value, "--trade-power-beneficiary"),
    )
    parser.add_argument(
        "--annul-country",
        type=lambda value: validate_tag(value, "--annul-country"),
    )
    parser.add_argument(
        "--annul-partners",
        nargs="+",
        type=lambda value: validate_tag(value, "--annul-partner"),
    )
    parser.add_argument("--output", required=True, type=Path, help="JSON file or output directory")
    args = parser.parse_args(argv)
    try:
        if args.payer is None and args.claimant is None and (
                args.trade_power_source is None
                and args.trade_power_beneficiary is None
                and args.annul_country is None):
            raise TreatySaveParseError(
                "at least one directed pair is required: payer/claimant or "
                "trade-power-source/trade-power-beneficiary"
            )
        json_path, markdown_path = _output_paths(args.output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        if json_path.exists() or markdown_path.exists():
            raise TreatySaveParseError(f"refusing to overwrite existing output: {json_path}")
        payload = build_payload(
            args.save.expanduser().resolve(),
            args.payer,
            args.claimant,
            trade_power_source=args.trade_power_source,
            trade_power_beneficiary=args.trade_power_beneficiary,
            annul_country=args.annul_country,
            annul_partners=args.annul_partners,
        )
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(render_report(payload), encoding="utf-8")
        print(json.dumps({
            "json": str(json_path),
            "markdown": str(markdown_path),
            "sha256": payload["save"]["source"].get("sha256"),
            "matching_count": payload["save"]["query"]["matching_count"],
            "trade_power_matching_count": payload["save"]["query"]["trade_power_matching_count"],
            "annul_matching_count": payload["save"]["query"]["annul_matching_count"],
        }, ensure_ascii=False))
        return 0
    except TreatySaveParseError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
