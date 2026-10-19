#!/usr/bin/env python3
"""Bounded, read-only extraction of serialized EU4 diplomacy evidence.

Never reads a whole save/country into memory, starts a process, or modifies a
save. Values are byte-preserving Latin-1 token text, not localized game text.
Missing fields do not establish that a relationship or live envoy task is absent.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

CHUNK = 64 * 1024
MAX_STREAM = 512 * 1024 * 1024
MAX_TOKEN = 64 * 1024
MAX_DEPTH = 128
MAX_CAPTURE = 128 * 1024
MAX_RETAINED = 4 * 1024 * 1024
MAX_CAPTURE_NODES = 4096
MAX_RETAINED_NODES = 32768
MAX_RECORDS = 4096
MAX_KEYS = 2048
TAG = re.compile(r"[A-Z][A-Z0-9]{2}\Z")
ATOM = re.compile(rb'[^\s={}#"]+')
QUOTED = re.compile(rb'"(?:[^"\\]|\\.)*"', re.S)
SPACE = re.compile(rb'\s+')
RELATED = re.compile(r"diplomat|diplomac|spy|relation|envoy|vassal|liberty|subject|marriage|guarantee|allies|overlord|last_sent_|last_send_")
CONTROL = {"human", "was_player", "is_at_war"}
EFFECT_FIELDS = {"modifier", "flags", "cb", "treasury", "manpower", "sailors",
                 "prestige", "stability", "heir", "monarch", "rival",
                 "coalition_target", "coalition_date", "coalition_friends"}


class SaveError(ValueError):
    pass


class BoundedReader:
    def __init__(self, source):
        self.source = source
        self.count = 0
        self.sha256 = hashlib.sha256()

    def read(self, count):
        if not 0 <= count <= CHUNK:
            raise SaveError("read exceeds bounded chunk size")
        raw = self.source.read(min(count, MAX_STREAM - self.count + 1))
        self.count += len(raw)
        if self.count > MAX_STREAM:
            raise SaveError("gamestate exceeds streaming byte budget")
        self.sha256.update(raw)
        return raw


def _zip_directory_guard(source, size):
    # ZipFile otherwise loads an unbounded central directory before infolist().
    source.seek(max(0, size - 65557))
    tail = source.read(min(size, 65557))
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) - position < 22:
        raise SaveError("ZIP end record missing")
    _, disk, directory_disk, disk_entries, entries, directory_size, offset, comment = struct.unpack_from("<4s4H2IH", tail, position)
    if position + 22 + comment != len(tail):
        raise SaveError("ZIP end record/comment is inconsistent")
    if disk or directory_disk or disk_entries != entries:
        raise SaveError("multi-disk ZIP is unsupported")
    if entries > 128 or directory_size > 1024 * 1024:
        raise SaveError("ZIP central directory exceeds bounds (ZIP64 unsupported)")
    if offset + directory_size > size - len(tail) + position:
        raise SaveError("ZIP central directory extends past end record")
    source.seek(0)


@contextmanager
def open_gamestate(path):
    with path.open("rb") as source:
        magic = source.read(7)
        source.seek(0)
        if magic.startswith(b"EU4bin"):
            raise SaveError("EU4bin is unsupported; a text save is required")
        if magic.startswith(b"PK\x03\x04"):
            _zip_directory_guard(source, path.stat().st_size)
            with zipfile.ZipFile(source, "r") as archive:
                members = [info for info in archive.infolist() if info.filename == "gamestate"]
                if len(members) != 1:
                    raise SaveError("ZIP must contain exactly one gamestate member")
                member = members[0]
                if member.flag_bits & 1 or member.file_size > MAX_STREAM:
                    raise SaveError("encrypted or oversized gamestate is unsupported")
                with archive.open(member, "r") as stream:
                    yield BoundedReader(stream), "zip_gamestate"
        elif magic.startswith(b"EU4txt"):
            yield BoundedReader(source), "plain_text"
        else:
            raise SaveError("unrecognized save signature; expected EU4txt or ZIP")


def tokens(reader):
    """Yield (kind, bytes, line, byte offset); only one chunk/token buffered."""
    signature = reader.read(6)
    if signature == b"EU4bin":
        raise SaveError("EU4bin gamestate is unsupported")
    if signature != b"EU4txt":
        raise SaveError("gamestate must begin with EU4txt")
    buffer = b""
    position = 0
    offset = 6
    line = 1
    eof = False
    while True:
        if position == len(buffer):
            buffer = b""
            position = 0
        if not buffer and not eof:
            buffer = reader.read(CHUNK)
            eof = not buffer
        if not buffer:
            return
        start = position
        first = buffer[start]
        kind = "atom"
        complete = True
        if first in b" \t\r\n\v\f":
            match = SPACE.match(buffer, start)
            end = match.end()
            kind = "skip"
        elif first == 35:
            found = buffer.find(b"\n", start)
            end = len(buffer) if found < 0 else found + 1
            complete = found >= 0 or eof
            kind = "skip"
        elif first in b"={}":
            end = start + 1
            kind = chr(first)
        else:
            match = (QUOTED if first == 34 else ATOM).match(buffer, start)
            end = match.end() if match else len(buffer)
            complete = match is not None and (first == 34 or end < len(buffer) or eof)
            if not complete and eof:
                raise SaveError(f"invalid or unterminated token at byte {offset}")
        if end - start > MAX_TOKEN:
            raise SaveError(f"token/comment exceeds {MAX_TOKEN} bytes")
        if not complete:
            buffer = buffer[start:]
            position = 0
            more = reader.read(CHUNK)
            eof = not more
            buffer += more
            continue
        raw = buffer[start:end]
        token_line, token_offset = line, offset
        line += raw.count(b"\n")
        offset += len(raw)
        position = end
        if kind != "skip":
            yield kind, raw, token_line, token_offset


def events(reader):
    """Parse Clausewitz assignments and lists without retaining skipped blocks."""
    stream = iter(tokens(reader))
    pending = None
    depth = 0
    while True:
        current = pending if pending is not None else next(stream, None)
        pending = None
        if current is None:
            if depth:
                raise SaveError("unclosed block at end of gamestate")
            return
        kind, raw, line, offset = current
        if kind == "}":
            if not depth:
                raise SaveError(f"unexpected closing brace at byte {offset}")
            depth -= 1
            yield "end", None, current
            continue
        if kind == "{":
            key = None
            value = current
        elif kind == "atom":
            following = next(stream, None)
            if following is None or following[0] != "=":
                yield "bare", None, current
                pending = following
                continue
            key = raw.decode("latin-1").strip('"')
            if len(raw) > 256:
                raise SaveError("assignment key exceeds 256-byte budget")
            value = next(stream, None)
            if value is None or value[0] not in ("atom", "{"):
                raise SaveError(f"missing assignment value for {key!r} at byte {offset}")
        else:
            raise SaveError(f"unexpected '=' at byte {offset}")
        if value[0] == "{":
            depth += 1
            if depth > MAX_DEPTH:
                raise SaveError("nesting exceeds depth budget")
            yield "start", key, current
        else:
            yield "scalar", key, value


def scalar_entry(key, token):
    raw = token[1].decode("latin-1")
    return {"key": key, "value": raw[1:-1] if raw.startswith('"') and raw.endswith('"') else raw,
            "raw_value": raw, "line": token[2], "byte_offset": token[3]}


class Capture:
    def __init__(self, key, token, destination):
        self.root = {"key": key, "entries": [], "line": token[2], "byte_offset": token[3]}
        self.stack = [self.root]
        self.destination = destination
        self.bytes = len(token[1]) + 1
        self.nodes = 1

    def add(self, event, key, token):
        self.bytes += len(token[1]) + len(key or "") + 1
        if self.bytes > MAX_CAPTURE:
            raise SaveError("selected/candidate block exceeds capture byte budget")
        if event == "end":
            self.stack.pop()
            return not self.stack
        self.nodes += 1
        if self.nodes > MAX_CAPTURE_NODES:
            raise SaveError("selected/candidate block exceeds node budget")
        entry = scalar_entry(key, token)
        if event == "start":
            entry = {"key": key, "entries": [], "line": token[2], "byte_offset": token[3]}
        self.stack[-1]["entries"].append(entry)
        if event == "start":
            self.stack.append(entry)
        return False


def mentions_tags(block, tags):
    for entry in block["entries"]:
        if "entries" in entry:
            if mentions_tags(entry, tags):
                return True
        elif entry["value"] in tags:
            return True
    return False


def extract(reader, actor, targets, effect_fields=False):
    tags = tuple(dict.fromkeys([actor, *targets]))
    countries = {tag: {"status": "not_found", "fields": [], "field_inventory": [],
                       "diplomats": {"status": "not_found", "blocks": []},
                       "relations": {other: {"status": "not_found", "blocks": []} for other in tags if other != tag},
                       "active_relations_container_found": False} for tag in tags}
    report = {"metadata": {}, "countries": countries,
              "global_diplomacy": {"container_found": False, "records": [], "record_counts_scanned": {}},
              "selected_serialized_bytes": 0}
    inventories = {tag: set() for tag in tags}
    scanned = Counter()
    path = []
    capture = None
    retained = 0
    records = 0
    nodes = 0

    def retain(item, size, destination, count=1):
        nonlocal retained, records, nodes
        retained += size
        records += 1
        nodes += count
        if retained > MAX_RETAINED or records > MAX_RECORDS or nodes > MAX_RETAINED_NODES:
            raise SaveError("retained evidence exceeds byte/record budget")
        destination.append(item)

    for event, key, token in events(reader):
        if capture:
            if capture.add(event, key, token):
                if capture.destination is None:
                    if mentions_tags(capture.root, tags):
                        retain(capture.root, capture.bytes, report["global_diplomacy"]["records"], capture.nodes)
                else:
                    retain(capture.root, capture.bytes, capture.destination, capture.nodes)
                capture = None
        elif event in ("start", "scalar"):
            if key is not None and len(path) == 2 and path[0] == "countries" and path[1] in countries:
                country = countries[path[1]]
                inventories[path[1]].add(key)
                if len(inventories[path[1]]) > MAX_KEYS:
                    raise SaveError("country field inventory exceeds key budget")
                if key == "active_relations":
                    country["active_relations_container_found"] = event == "start"
                elif key == "diplomats" and event == "start":
                    country["diplomats"]["status"] = "found"
                    capture = Capture(key, token, country["diplomats"]["blocks"])
                elif key in CONTROL or RELATED.search(key) or (effect_fields and key in EFFECT_FIELDS):
                    if event == "start":
                        capture = Capture(key, token, country["fields"])
                    else:
                        retain(scalar_entry(key, token), len(token[1]) + len(key), country["fields"])
            elif event == "start" and len(path) == 1 and path[0] == "countries" and key in countries:
                country = countries[key]
                if country["status"] == "found":
                    raise SaveError(f"duplicate selected country block {key}")
                country.update(status="found", line=token[2], byte_offset=token[3])
            elif event == "start" and len(path) == 3 and path[0] == "countries" and path[1] in countries and path[2] == "active_relations":
                relations = countries[path[1]]["relations"]
                if key in relations:
                    relations[key]["status"] = "found"
                    capture = Capture(key, token, relations[key]["blocks"])
            elif event == "start" and path == ["diplomacy"]:
                if key is None:
                    raise SaveError("unnamed global diplomacy record is unsupported")
                scanned[key] += 1
                if len(scanned) > MAX_KEYS:
                    raise SaveError("diplomacy record type inventory exceeds key budget")
                capture = Capture(key, token, None)
            elif not path:
                if key == "diplomacy" and event == "start":
                    report["global_diplomacy"]["container_found"] = True
                elif key in ("date", "player", "save_game", "multi_player") and event == "scalar":
                    if key in report["metadata"]:
                        raise SaveError(f"duplicate metadata field {key}")
                    report["metadata"][key] = scalar_entry(key, token)
                elif key in ("savegame_version", "savegame_versions") and event == "start":
                    destination = report["metadata"].setdefault(key, [])
                    capture = Capture(key, token, destination)
        if event == "start":
            path.append(key)
        elif event == "end":
            path.pop()
    for tag, country in countries.items():
        country["field_inventory"] = sorted(inventories[tag])
    report["global_diplomacy"]["record_counts_scanned"] = dict(sorted(scanned.items()))
    report["selected_serialized_bytes"] = retained
    report["retained_nodes"] = nodes
    return report


def inspect_save(path: Path, actor="FRA", targets=("ENG", "POR"), *, effect_fields=False):
    path = Path(path).resolve(strict=True)
    targets = tuple(dict.fromkeys(targets))
    if not TAG.fullmatch(actor) or not targets or len(targets) > 16 or any(not TAG.fullmatch(tag) or tag == actor for tag in targets):
        raise SaveError("use a three-character actor and 1–16 distinct other target tags")
    before = path.stat()
    if not path.is_file() or before.st_size > MAX_STREAM:
        raise SaveError("save is not a regular file or exceeds input size budget")
    with open_gamestate(path) as (reader, encoding):
        report = extract(reader, actor, targets, effect_fields)
        game_hash = reader.sha256.hexdigest().upper()
        game_size = reader.count
    # Hash the physical archive too, using a separate bounded pass (plain text
    # already has the exact file digest from the complete parsing pass).
    source_hash = game_hash
    if encoding == "zip_gamestate":
        digest = hashlib.sha256()
        hashed = 0
        with path.open("rb") as source:
            while raw := source.read(CHUNK):
                hashed += len(raw)
                if hashed > MAX_STREAM:
                    raise SaveError("physical archive exceeds streaming byte budget")
                digest.update(raw)
        source_hash = digest.hexdigest().upper()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise SaveError("save changed during inspection; retry after saving has finished")
    return {"schema_version": 1, "tool": "work/inspect_diplomacy_save.py", "read_only": True,
            "evidence_scope": "serialized_state_only", "runtime_effects_verified": False,
            "parsed_complete": True, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(path), "size_bytes": before.st_size, "sha256": source_hash,
                       "format": encoding, "gamestate_bytes": game_size, "gamestate_sha256": game_hash},
            "actor": actor, "targets": list(targets), "text_encoding": "Latin-1 reversible byte mapping; not localization decoding",
            "selected_effect_fields": sorted(EFFECT_FIELDS) if effect_fields else [],
            "limits": {"chunk_bytes": CHUNK, "stream_bytes": MAX_STREAM, "token_bytes": MAX_TOKEN,
                       "capture_bytes": MAX_CAPTURE, "retained_serialized_bytes": MAX_RETAINED, "depth": MAX_DEPTH,
                       "capture_nodes": MAX_CAPTURE_NODES, "retained_nodes": MAX_RETAINED_NODES},
            "limitations": ["Only selected countries, their pair relations, related direct fields, and global diplomacy records mentioning selected tags are retained.",
                            "not_found means no matching serialized field was observed; it does not prove a diplomatic relationship or live task is absent.",
                            "Envoy fields are serialized evidence, not a verified interpretation of native envoy state or task availability.",
                            "No running process or action result is inspected; effect verification requires separate before/after and reload evidence.",
                            "Quoted token values preserve backslash escapes; raw_value preserves original token spelling."], **report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--actor", default="FRA")
    parser.add_argument("--target", action="append", help="Repeat for targets; defaults to ENG and POR")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--effect-fields", action="store_true", help="Also retain selected countries' modifiers, flags, CBs and basic resources")
    args = parser.parse_args(argv)
    try:
        source = args.save.resolve(strict=True)
        output = args.output.resolve()
        if source == output or (output.exists() and output.samefile(source)):
            raise SaveError("output must not overwrite the input save")
        report = inspect_save(source, args.actor, args.target or ("ENG", "POR"), effect_fields=args.effect_fields)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, SaveError, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(2, f"inspection failed: {error}\n")
    print(json.dumps({"output": str(output), "evidence_scope": report["evidence_scope"],
                      "countries": {key: value["status"] for key, value in report["countries"].items()},
                      "global_records": len(report["global_diplomacy"]["records"])}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
