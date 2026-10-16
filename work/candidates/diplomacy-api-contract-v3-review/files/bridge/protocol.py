"""Parser for the small EU4LLM line protocol.

The game can prefix a protocol line with its normal log metadata.  The
parser searches for ``EU4LLM|`` anywhere in each line, but validates the
protocol payload exactly after that marker.  This prevents a log prefix from
becoming a way to smuggle extra fields into a snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence


PROTOCOL_PREFIX = "EU4LLM|"
COUNTRY = "FRA"
ACK_STATUSES = frozenset({"applied", "rejected"})

# IDs become part of the request-flag name in generated EU4 script.  Keep
# this intentionally narrower than a general string so neither logs nor run
# files can carry arbitrary script text.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,32}$")
FIELD_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
STATUS_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class ProtocolError(ValueError):
    """Raised when a protocol line or snapshot boundary is invalid."""


class InvalidIdentifierError(ProtocolError):
    """Raised for an ID that cannot safely be used as a protocol identifier."""


class InterleavedSnapshotError(ProtocolError):
    """Raised when two snapshots are active at the same time."""


class IncompleteSnapshotError(ProtocolError):
    """Raised when a log ends while a snapshot is still open."""


@dataclass(frozen=True)
class Snapshot:
    """A complete, validated snapshot emitted by the FRA scripted effect."""

    snapshot_id: str
    country: str
    fields: Mapping[str, str]
    line_start: int | None = None
    line_end: int | None = None

    @property
    def id(self) -> str:
        """Compatibility alias for callers that use ``snapshot.id``."""

        return self.snapshot_id

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.snapshot_id,
            "country": self.country,
            "fields": dict(self.fields),
        }


@dataclass(frozen=True)
class Ack:
    """An action receipt emitted by the game."""

    request_id: str
    status: str
    line: int | None = None

    @property
    def id(self) -> str:
        """Compatibility alias for callers that use ``ack.id``."""

        return self.request_id

    def to_dict(self) -> dict[str, str]:
        return {"request_id": self.request_id, "status": self.status}


@dataclass(frozen=True)
class ParseIssue:
    """A recoverable issue collected when ``parse_log(..., strict=False)``."""

    line: int
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"line": self.line, "message": self.message}


@dataclass(frozen=True)
class ParsedLog:
    """Validated protocol records found in a log."""

    snapshots: tuple[Snapshot, ...] = ()
    acks: tuple[Ack, ...] = ()
    issues: tuple[ParseIssue, ...] = ()

    def to_dict(self, *, include_issues: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "acks": [ack.to_dict() for ack in self.acks],
        }
        if include_issues:
            result["issues"] = [issue.to_dict() for issue in self.issues]
        return result

    def __iter__(self):
        """Iterate snapshots for convenient use in small scripts."""

        return iter(self.snapshots)

    def __len__(self) -> int:
        return len(self.snapshots)


@dataclass
class _OpenSnapshot:
    snapshot_id: str
    country: str
    line_start: int
    fields: dict[str, str] = field(default_factory=dict)


def _validate_id(value: str, *, label: str) -> str:
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise InvalidIdentifierError(
            f"{label} must match [A-Za-z0-9_]{{1,32}}; got {value!r}"
        )
    return value


def _validate_field_key(value: str) -> str:
    if FIELD_KEY_PATTERN.fullmatch(value) is None:
        raise ProtocolError(f"invalid snapshot field key: {value!r}")
    return value


def _extract_payload(line: str) -> str | None:
    """Return the protocol payload, allowing arbitrary text before its marker."""

    marker = line.find(PROTOCOL_PREFIX)
    if marker < 0:
        return None
    # splitlines() removes the line ending, but callers can pass individual
    # lines directly, so remove only line-ending characters here.  Spaces are
    # meaningful in a field value and are therefore preserved.
    return line[marker:].rstrip("\r\n")


def _protocol_error(line_number: int, message: str) -> ProtocolError:
    return ProtocolError(f"line {line_number}: {message}")


def _parse_one(
    payload: str,
    line_number: int,
    active: _OpenSnapshot | None,
    snapshots: list[Snapshot],
    acks: list[Ack],
) -> _OpenSnapshot | None:
    parts = payload.split("|")
    if len(parts) < 2 or parts[0] != "EU4LLM":
        raise _protocol_error(line_number, "malformed EU4LLM line")

    operation = parts[1]
    if operation == "BEGIN":
        if len(parts) != 4:
            raise _protocol_error(line_number, "BEGIN requires id and country")
        if active is not None:
            raise InterleavedSnapshotError(
                f"line {line_number}: BEGIN {parts[2]!r} interleaves snapshot "
                f"{active.snapshot_id!r}"
            )
        snapshot_id = _validate_id(parts[2], label="snapshot ID")
        if parts[3] != COUNTRY:
            raise _protocol_error(
                line_number, f"unsupported snapshot country {parts[3]!r}; expected FRA"
            )
        return _OpenSnapshot(snapshot_id, COUNTRY, line_number)

    if operation == "FIELD":
        if len(parts) != 5:
            raise _protocol_error(line_number, "FIELD requires id, key, and value")
        if active is None:
            raise _protocol_error(line_number, "FIELD appears outside a snapshot")
        field_id = _validate_id(parts[2], label="snapshot ID")
        if field_id != active.snapshot_id:
            raise InterleavedSnapshotError(
                f"line {line_number}: FIELD belongs to {field_id!r}, "
                f"active snapshot is {active.snapshot_id!r}"
            )
        key = _validate_field_key(parts[3])
        if key in active.fields:
            raise _protocol_error(line_number, f"duplicate field {key!r}")
        value = parts[4]
        if any(ord(character) < 0x20 for character in value):
            raise _protocol_error(line_number, "FIELD value contains a control character")
        active.fields[key] = value
        return active

    if operation == "END":
        if len(parts) != 3:
            raise _protocol_error(line_number, "END requires id")
        if active is None:
            raise _protocol_error(line_number, "END appears outside a snapshot")
        end_id = _validate_id(parts[2], label="snapshot ID")
        if end_id != active.snapshot_id:
            raise InterleavedSnapshotError(
                f"line {line_number}: END belongs to {end_id!r}, "
                f"active snapshot is {active.snapshot_id!r}"
            )
        snapshots.append(
            Snapshot(
                active.snapshot_id,
                active.country,
                dict(active.fields),
                active.line_start,
                line_number,
            )
        )
        return None

    if operation == "ACK":
        if len(parts) != 4:
            raise _protocol_error(line_number, "ACK requires request ID and status")
        if active is not None:
            raise InterleavedSnapshotError(
                f"line {line_number}: ACK interleaves snapshot {active.snapshot_id!r}"
            )
        request_id = _validate_id(parts[2], label="request ID")
        status = parts[3]
        if status not in ACK_STATUSES or STATUS_PATTERN.fullmatch(status) is None:
            raise _protocol_error(
                line_number,
                f"invalid ACK status {status!r}; expected one of "
                f"{sorted(ACK_STATUSES)}",
            )
        acks.append(Ack(request_id, status, line_number))
        return active

    raise _protocol_error(line_number, f"unknown operation {operation!r}")


def parse_log(
    source: str | bytes | Iterable[str],
    *,
    strict: bool = True,
) -> ParsedLog:
    """Parse complete snapshots and ACKs from a game log.

    ``strict=True`` (the default) rejects malformed protocol records,
    interleaved snapshots, and a truncated open snapshot.  With
    ``strict=False``, malformed records are dropped and returned in
    ``ParsedLog.issues``; this mode is useful for tailing a log while the
    game is still writing it.  Normal CLI operation remains strict so an
    incomplete snapshot can never be mistaken for current state.
    """

    if isinstance(source, bytes):
        source = source.decode("utf-8")
    if isinstance(source, str):
        lines: Sequence[str] = source.splitlines()
    else:
        lines = list(source)

    snapshots: list[Snapshot] = []
    acks: list[Ack] = []
    issues: list[ParseIssue] = []
    active: _OpenSnapshot | None = None

    for line_number, line in enumerate(lines, start=1):
        payload = _extract_payload(line)
        if payload is None:
            continue
        try:
            active = _parse_one(payload, line_number, active, snapshots, acks)
        except ProtocolError as error:
            if strict:
                raise
            issues.append(ParseIssue(line_number, str(error)))
            # A malformed boundary invalidates the current open snapshot.  It
            # is safer to wait for a fresh BEGIN than to stitch fields across
            # an uncertain boundary.
            active = None

    if active is not None:
        error = IncompleteSnapshotError(
            f"snapshot {active.snapshot_id!r} began on line {active.line_start} "
            "but has no matching END"
        )
        if strict:
            raise error
        issues.append(ParseIssue(active.line_start, str(error)))

    return ParsedLog(tuple(snapshots), tuple(acks), tuple(issues))


def parse_file(path: str | Path, *, strict: bool = True, encoding: str = "utf-8") -> ParsedLog:
    """Read and parse a game log file."""

    # Translation plugins may write non-UTF8 bytes in unrelated engine lines.
    # Decode only our protocol payloads, strictly; never repair corrupted data.
    records = []
    marker = PROTOCOL_PREFIX.encode('ascii')
    for raw in Path(path).read_bytes().splitlines():
        pos = raw.find(marker)
        records.append(raw[pos:].decode(encoding) if pos >= 0 else '')
    return parse_log(records, strict=strict)


def parsed_log_json(parsed: ParsedLog, *, pretty: bool = False, include_issues: bool = False) -> str:
    """Serialize a parsed log for the CLI and small integrations."""

    return json.dumps(
        parsed.to_dict(include_issues=include_issues),
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=True,
    )

