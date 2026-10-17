#!/usr/bin/env python3
"""Stream a bounded FRA/PRO diplomacy comparison from two EU4 saves.

The positional arguments are the save-before path and the save-after path.
The utility hashes each source by streaming bytes, then scans only the
serialized ``countries``/``diplomacy`` structures needed for FRA and PRO.
It never reads a complete gamestate member into memory.  For a ZIP save the
``gamestate`` member is opened with :meth:`ZipFile.open`; for an ``EU4txt``
save the file is wrapped in a streaming text decoder.

The JSON result contains the exact FRA/PRO alliance entries (if present), the
complete serialized FRA->PRO and PRO->FRA ``active_relations`` pair blocks,
field-by-field differences, source hashes, and parse-completeness indicators.
An absent ``truce`` or expiry field is reported as absent from that serialized
pair block only.  It is never promoted to a claim about every truce in the
save.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, TextIO


PAIR = frozenset(("FRA", "PRO"))
TARGET_TAGS = ("FRA", "PRO")
HASH_CHUNK = 1024 * 1024
# A normal country block in these saves is tens of KB.  This cap prevents a
# malformed save from turning the bounded-country strategy into a gamestate
# capture.
MAX_COUNTRY_CAPTURE = 8 * 1024 * 1024
MAX_ALLIANCE_CAPTURE = 256 * 1024

COUNTRIES_RE = re.compile(r"^\s*countries\s*=\s*\{")
COUNTRY_RE = re.compile(r"^\s*(FRA|PRO)\s*=\s*\{")
DIPLOMACY_RE = re.compile(r"^\s*diplomacy\s*=\s*\{")
ALLIANCE_RE = re.compile(r"^\s*alliance\s*=\s*\{")
BLOCK_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{")
SCALAR_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$")


class SaveParseError(RuntimeError):
    """Raised for an input/container that cannot be inspected safely."""


@dataclass(frozen=True)
class Entry:
    key: str
    value: str | None
    body: str | None


@dataclass
class CountryCapture:
    tag: str
    start_line: int
    end_line: int | None
    text: str
    complete: bool
    bytes_captured: int


def brace_delta(line: str) -> int:
    """Count braces outside quoted strings on one decoded line."""

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


def extract_block(text: str, open_index: int) -> str:
    """Return the text inside a brace, respecting quoted strings."""

    if open_index < 0 or open_index >= len(text) or text[open_index] != "{":
        raise SaveParseError(f"expected '{{' at offset {open_index}")
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
    raise SaveParseError(f"unclosed block at offset {open_index}")


def top_level_entries(body: str) -> list[Entry]:
    """Collect direct scalar/block children of a bounded block body."""

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


def unquote(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def add_value(mapping: dict[str, Any], key: str, value: str) -> None:
    """Keep duplicate serialized scalar keys instead of silently overwriting."""

    if key not in mapping:
        mapping[key] = value
    elif isinstance(mapping[key], list):
        mapping[key].append(value)
    else:
        mapping[key] = [mapping[key], value]


def flatten_entries(entries: list[Entry], prefix: str = "") -> tuple[dict[str, Any], list[str]]:
    """Flatten all scalar fields and preserve nested block paths."""

    fields: dict[str, Any] = {}
    blocks: list[str] = []
    block_counts: dict[str, int] = {}
    for entry in entries:
        count = block_counts.get(entry.key, 0) + 1
        block_counts[entry.key] = count
        suffix = "" if count == 1 else f"#{count}"
        path = f"{prefix}.{entry.key}{suffix}" if prefix else f"{entry.key}{suffix}"
        if entry.value is not None:
            add_value(fields, path, entry.value)
            continue
        blocks.append(path)
        children = top_level_entries(entry.body or "")
        child_fields, child_blocks = flatten_entries(children, path)
        for key, value in child_fields.items():
            add_value(fields, key, value) if key in fields else fields.__setitem__(key, value)
        blocks.extend(child_blocks)
    return fields, blocks


def parse_field_body(body: str) -> dict[str, Any]:
    """Parse a bounded relation/alliance body without touching the gamestate."""

    try:
        entries = top_level_entries(body)
        fields, blocks = flatten_entries(entries)
    except SaveParseError as exc:
        return {
            "fields": {},
            "blocks": [],
            "unknown": [f"parse_error: {exc}"],
        }
    return {
        "fields": fields,
        "blocks": blocks,
        # Every non-empty target field is retained.  This list is reserved for
        # malformed/unsupported structures and is intentionally explicit.
        "unknown": [],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def detect_container(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SaveParseError(f"cannot stat save {path}: {exc}") from exc
    with path.open("rb") as handle:
        magic = handle.read(8)
    if magic.startswith(b"PK"):
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            info = choose_gamestate_info(infos, path)
            return {
                "path": str(path.resolve()),
                "size_bytes": size,
                "container": "zip",
                "header": magic.hex(),
                "gamestate_member": info.filename,
                "gamestate_member_size_bytes": info.file_size,
                "gamestate_member_compressed_bytes": info.compress_size,
            }
    if magic.startswith(b"EU4txt"):
        return {
            "path": str(path.resolve()),
            "size_bytes": size,
            "container": "plain",
            "header": magic[:6].decode("ascii", errors="replace"),
            "gamestate_member": None,
        }
    raise SaveParseError(
        f"{path}: unsupported save header {magic!r}; expected EU4txt or ZIP/PK"
    )


def choose_gamestate_info(
    infos: list[zipfile.ZipInfo], path: Path
) -> zipfile.ZipInfo:
    exact = [info for info in infos if Path(info.filename).name.lower() == "gamestate"]
    if not exact:
        exact = [
            info
            for info in infos
            if "gamestate" in Path(info.filename).name.lower()
        ]
    if not exact:
        names = ", ".join(info.filename for info in infos[:20])
        raise SaveParseError(f"{path}: ZIP has no gamestate member (members: {names})")
    return exact[0]


@contextlib.contextmanager
def open_gamestate(path: Path, source: dict[str, Any]) -> Iterator[TextIO]:
    """Yield a streaming gamestate text reader."""

    if source["container"] == "plain":
        with path.open("rb") as raw:
            with io.TextIOWrapper(
                raw, encoding="utf-8-sig", errors="replace", newline=""
            ) as text:
                yield text
        return

    with zipfile.ZipFile(path, "r") as archive:
        info = archive.getinfo(source["gamestate_member"])
        with archive.open(info, "r") as raw:
            with io.TextIOWrapper(
                raw, encoding="utf-8-sig", errors="replace", newline=""
            ) as text:
                yield text


class SaveScanner:
    """Single-pass scanner retaining only two country blocks and pair alliances."""

    def __init__(self) -> None:
        self.depth = 0
        self.line_count = 0
        self.header_line: str | None = None
        self.save_date: str | None = None

        self.countries_found = False
        self.countries_complete = False
        self.countries_base_depth: int | None = None
        self.countries_depth: int | None = None
        self.current_country: str | None = None
        self.current_country_depth: int | None = None
        self.current_country_start: int | None = None
        self.current_country_lines: list[str] = []
        self.current_country_bytes = 0
        self.country_captures: dict[str, CountryCapture] = {}
        self.duplicate_country_tags: list[str] = []

        self.diplomacy_found = False
        self.diplomacy_complete = False
        self.diplomacy_base_depth: int | None = None
        self.diplomacy_depth: int | None = None
        self.current_alliance_lines: list[str] | None = None
        self.current_alliance_start: int | None = None
        self.current_alliance_bytes = 0
        self.alliance_pair_entries: list[dict[str, Any]] = []
        self.alliance_blocks_seen = 0
        self.alliance_parse_unknown: list[str] = []

    def _finish_country(self, end_line: int | None, complete: bool) -> None:
        if self.current_country is None or self.current_country_start is None:
            return
        text = "".join(self.current_country_lines)
        capture = CountryCapture(
            tag=self.current_country,
            start_line=self.current_country_start,
            end_line=end_line,
            text=text,
            complete=complete,
            bytes_captured=self.current_country_bytes,
        )
        if self.current_country in self.country_captures:
            self.duplicate_country_tags.append(self.current_country)
        else:
            self.country_captures[self.current_country] = capture
        self.current_country = None
        self.current_country_depth = None
        self.current_country_start = None
        self.current_country_lines = []
        self.current_country_bytes = 0

    def _finish_alliance(self, end_line: int | None) -> None:
        if self.current_alliance_lines is None or self.current_alliance_start is None:
            return
        text = "".join(self.current_alliance_lines)
        self.alliance_blocks_seen += 1
        parsed = parse_structured_block(text)
        fields = parsed["fields"]
        first = unquote(fields.get("first"))
        second = unquote(fields.get("second"))
        if frozenset((first, second)) == PAIR:
            self.alliance_pair_entries.append(
                {
                    "line_start": self.current_alliance_start,
                    "line_end": end_line,
                    "fields": fields,
                    "blocks": parsed["blocks"],
                    "unknown": parsed["unknown"],
                }
            )
        if parsed["unknown"]:
            self.alliance_parse_unknown.extend(parsed["unknown"])
        self.current_alliance_lines = None
        self.current_alliance_start = None
        self.current_alliance_bytes = 0

    def consume(self, stream: TextIO) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            if line_number == 1:
                self.header_line = line.rstrip("\r\n")
            before = self.depth

            if self.save_date is None and before == 0:
                date_match = re.match(r"^\s*date\s*=\s*([^\r\n]+)", line)
                if date_match:
                    self.save_date = date_match.group(1).strip()

            if (
                not self.countries_found
                and COUNTRIES_RE.match(line)
                and before == 0
            ):
                self.countries_found = True
                self.countries_base_depth = before
                self.countries_depth = before + brace_delta(line)

            if self.countries_found and not self.countries_complete:
                if (
                    self.current_country is None
                    and self.countries_depth is not None
                    and before == self.countries_depth
                ):
                    country_match = COUNTRY_RE.match(line)
                    if country_match and country_match.group(1) in TARGET_TAGS:
                        self.current_country = country_match.group(1)
                        self.current_country_start = line_number
                        self.current_country_depth = before + brace_delta(line)
                        self.current_country_lines = [line]
                        self.current_country_bytes = len(line.encode("utf-8", "replace"))
                elif self.current_country is not None:
                    self.current_country_lines.append(line)
                    self.current_country_bytes += len(line.encode("utf-8", "replace"))
                    if self.current_country_bytes > MAX_COUNTRY_CAPTURE:
                        raise SaveParseError(
                            f"{self.current_country}: bounded capture exceeded "
                            f"{MAX_COUNTRY_CAPTURE} bytes"
                        )

            if not self.diplomacy_found and DIPLOMACY_RE.match(line) and before == 0:
                self.diplomacy_found = True
                self.diplomacy_base_depth = before
                self.diplomacy_depth = before + brace_delta(line)

            if (
                self.diplomacy_found
                and not self.diplomacy_complete
                and self.current_alliance_lines is None
                and self.diplomacy_depth is not None
                and before == self.diplomacy_depth
                and ALLIANCE_RE.match(line)
            ):
                self.current_alliance_start = line_number
                self.current_alliance_lines = [line]
                self.current_alliance_bytes = len(line.encode("utf-8", "replace"))

            if self.current_alliance_lines is not None and line_number != self.current_alliance_start:
                self.current_alliance_lines.append(line)
                self.current_alliance_bytes += len(line.encode("utf-8", "replace"))
                if self.current_alliance_bytes > MAX_ALLIANCE_CAPTURE:
                    raise SaveParseError(
                        f"alliance block exceeded {MAX_ALLIANCE_CAPTURE} bytes"
                    )

            delta = brace_delta(line)
            self.depth += delta

            if (
                self.current_country is not None
                and self.countries_depth is not None
                and self.depth == self.countries_depth
                and before >= (self.current_country_depth or self.depth + 1)
            ):
                self._finish_country(line_number, complete=True)

            if (
                self.countries_found
                and self.countries_depth is not None
                and self.countries_base_depth is not None
                and self.depth == self.countries_base_depth
                and before >= self.countries_depth
            ):
                if self.current_country is not None:
                    self._finish_country(line_number, complete=False)
                self.countries_complete = True

            if (
                self.current_alliance_lines is not None
                and self.diplomacy_depth is not None
                and self.depth == self.diplomacy_depth
                and before >= self.diplomacy_depth + 1
            ):
                self._finish_alliance(line_number)

            if (
                self.diplomacy_found
                and self.diplomacy_base_depth is not None
                and self.diplomacy_depth is not None
                and self.depth == self.diplomacy_base_depth
                and before >= self.diplomacy_depth
            ):
                if self.current_alliance_lines is not None:
                    self._finish_alliance(line_number)
                self.diplomacy_complete = True

        if self.current_country is not None:
            self._finish_country(None, complete=False)
        if self.current_alliance_lines is not None:
            self._finish_alliance(None)


def parse_structured_block(text: str) -> dict[str, Any]:
    open_index = text.find("{")
    try:
        body = extract_block(text, open_index)
        return parse_field_body(body)
    except SaveParseError as exc:
        return {"fields": {}, "blocks": [], "unknown": [f"parse_error: {exc}"]}


def active_relation_result(capture: CountryCapture | None, other: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "present": False,
        "country_block_complete": bool(capture and capture.complete),
        "active_relations_block_count": 0,
        "entries": [],
        "unknown": [],
    }
    if capture is None:
        result["unknown"].append("country_block_not_found")
        return result
    if not capture.complete:
        result["unknown"].append("country_block_unclosed_or_bounded_capture_incomplete")
        return result
    try:
        open_index = capture.text.find("{")
        country_body = extract_block(capture.text, open_index)
        country_entries = top_level_entries(country_body)
    except SaveParseError as exc:
        result["unknown"].append(f"country_parse_error: {exc}")
        return result

    relation_blocks = [
        entry.body
        for entry in country_entries
        if entry.key == "active_relations" and entry.body is not None
    ]
    result["active_relations_block_count"] = len(relation_blocks)
    for relation_body in relation_blocks:
        try:
            entries = top_level_entries(relation_body)
        except SaveParseError as exc:
            result["unknown"].append(f"active_relations_parse_error: {exc}")
            continue
        for entry in entries:
            if entry.key != other or entry.body is None:
                continue
            parsed = parse_field_body(entry.body)
            result["present"] = True
            result["entries"].append(
                {
                    "fields": parsed["fields"],
                    "blocks": parsed["blocks"],
                    "unknown": parsed["unknown"],
                }
            )
            result["unknown"].extend(parsed["unknown"])
    return result


def scan_save(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SaveParseError(f"save path is not a file: {path}")
    source = detect_container(path)
    source["sha256"] = sha256_file(path)
    scanner = SaveScanner()
    with open_gamestate(path, source) as stream:
        scanner.consume(stream)

    country_summaries: dict[str, Any] = {}
    relation_summaries: dict[str, Any] = {}
    unknown: list[str] = []
    for tag in TARGET_TAGS:
        capture = scanner.country_captures.get(tag)
        country_summaries[tag] = {
            "found": capture is not None,
            "start_line": capture.start_line if capture else None,
            "end_line": capture.end_line if capture else None,
            "complete": capture.complete if capture else False,
            "bytes_captured": capture.bytes_captured if capture else 0,
        }
        if capture is None:
            unknown.append(f"country_{tag}_not_found")
        elif not capture.complete:
            unknown.append(f"country_{tag}_capture_incomplete")
        for other in TARGET_TAGS:
            if tag == other:
                continue
            key = f"{tag}->{other}"
            relation_summaries[key] = active_relation_result(capture, other)
            unknown.extend(
                f"{key}:{item}" for item in relation_summaries[key]["unknown"]
            )

    if scanner.duplicate_country_tags:
        unknown.extend(f"duplicate_country_tag:{tag}" for tag in scanner.duplicate_country_tags)
    if scanner.alliance_parse_unknown:
        unknown.extend(scanner.alliance_parse_unknown)
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
        "source": source,
        "metadata": {
            "first_line": scanner.header_line,
            "date": scanner.save_date,
        },
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
        "countries": country_summaries,
        "relations": relation_summaries,
        "alliance_exact_pair": {
            "pair": ["FRA", "PRO"],
            "entry_count": len(scanner.alliance_pair_entries),
            "entries": scanner.alliance_pair_entries,
        },
    }


def first_relation_fields(scan: dict[str, Any], direction: str) -> dict[str, Any] | None:
    relation = scan["relations"][direction]
    entries = relation["entries"]
    if len(entries) != 1:
        return None
    return entries[0]["fields"]


def relation_field_changes(before: dict[str, Any], after: dict[str, Any], direction: str) -> dict[str, Any]:
    before_relation = before["relations"][direction]
    after_relation = after["relations"][direction]
    before_fields = first_relation_fields(before, direction)
    after_fields = first_relation_fields(after, direction)
    changes: list[dict[str, Any]] = []
    if before_fields is None or after_fields is None:
        return {
            "before_present": before_relation["present"],
            "after_present": after_relation["present"],
            "before_entry_count": len(before_relation["entries"]),
            "after_entry_count": len(after_relation["entries"]),
            "field_changes": changes,
            "unknown": ["field_diff_requires_exactly_one_entry_per_side"],
        }
    missing = object()
    for key in sorted(set(before_fields) | set(after_fields)):
        old = before_fields.get(key, missing)
        new = after_fields.get(key, missing)
        if old == new:
            continue
        if old is missing:
            kind = "added"
            old_value: Any = None
        elif new is missing:
            kind = "removed"
            old_value = old
        else:
            kind = "changed"
            old_value = old
        changes.append(
            {
                "field": key,
                "kind": kind,
                "before": old_value,
                "after": None if new is missing else new,
            }
        )
    return {
        "before_present": before_relation["present"],
        "after_present": after_relation["present"],
        "before_entry_count": len(before_relation["entries"]),
        "after_entry_count": len(after_relation["entries"]),
        "field_changes": changes,
        "unknown": [],
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "alliance_exact_pair": {
            "before_entry_count": before["alliance_exact_pair"]["entry_count"],
            "after_entry_count": after["alliance_exact_pair"]["entry_count"],
            "before_entries": before["alliance_exact_pair"]["entries"],
            "after_entries": after["alliance_exact_pair"]["entries"],
            "unknown": [],
        },
        "relations": {
            direction: relation_field_changes(before, after, direction)
            for direction in ("FRA->PRO", "PRO->FRA")
        },
        "interpretation_guard": (
            "A missing field means absent from that serialized pair block only; "
            "it is not evidence that every global truce object is absent."
        ),
    }


def build_payload(before_path: Path, after_path: Path) -> dict[str, Any]:
    before = scan_save(before_path)
    after = scan_save(after_path)
    return {
        "tool": {
            "name": "inspect_dissolve_save_pair.py",
            "version": 1,
            "scope": "FRA/PRO pair only; streaming gamestate scan",
        },
        "pair": ["FRA", "PRO"],
        "before": before,
        "after": after,
        "comparison": compare(before, after),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream and compare the serialized EU4 FRA/PRO alliance/relation pair."
    )
    parser.add_argument("before", type=Path, help="save before the dissolve")
    parser.add_argument("after", type=Path, help="save after the dissolve")
    parser.add_argument(
        "--json-out",
        type=Path,
        help="optional JSON output path; otherwise JSON is written to stdout",
    )
    args = parser.parse_args()
    payload = build_payload(args.before, args.after)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
