#!/usr/bin/env python3
"""Read-only province owner/controller candidate evidence for the R45 build.

The live part reads only the verified EU4 module, the database country table,
the game province-array bounds, and the requested province records.  It never
scans the heap, calls an engine method, or writes process memory.  The static
part streams the selected baseline save and retains only a bounded excerpt for
provinces whose serialized ``owner`` and ``controller`` differ.
"""

from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from local_config import game_exe, user_data
except ModuleNotFoundError:
    from work.local_config import game_exe, user_data

WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))
import inspect_dissolve_save_pair as bounded


EXPECTED_HASH = "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77"
DATABASE_POINTER_RVA = 0x233D8B0
GAME_POINTER_RVA = 0x233FE58
COUNTRY_TABLE_OFFSET = 0x118
CURRENT_DATE_OFFSET = 0x1DD0
PROVINCE_BEGIN_OFFSET = 0x1C90
PROVINCE_END_OFFSET = 0x1C98
PROVINCE_BASE_OFFSET = 0x1CA8
PROVINCE_RECORD_STRIDE = 0x2E10
PROVINCE_ID_OFFSET = 0x20
PROVINCE_FIELD_468_OFFSET = 0x468
PROVINCE_FIELD_470_OFFSET = 0x470
MAX_PROVINCE_COUNT = 1_000_000
MAX_READ_BYTES = 1 << 20
MAX_BASELINE_EXCERPT_BYTES = 16 * 1024
MAX_BASELINE_CANDIDATES = 16
BASELINE_NAME = "llm_diplomacy_peace_outbound_ready_20261016_r45a.eu4"
TAG_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


class ProbeError(RuntimeError):
    """A stale or structurally inconsistent native read."""


def binary_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_requested_ids(values: list[str]) -> list[int]:
    if not 1 <= len(values) <= 16:
        raise argparse.ArgumentTypeError("--province-ids requires 1..16 IDs")
    result: list[int] = []
    for raw in values:
        try:
            value = int(raw, 0)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"invalid province ID: {raw}") from error
        if value < 0 or value > 1_000_000:
            raise argparse.ArgumentTypeError(f"province ID out of bounded range: {value}")
        if value in result:
            raise argparse.ArgumentTypeError(f"duplicate province ID: {value}")
        result.append(value)
    return result


def brace_delta(line: str) -> int:
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
        elif char == '"':
            quoted = True
        elif char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _short_text(raw: str, limit: int = MAX_BASELINE_EXCERPT_BYTES) -> tuple[str, bool]:
    encoded = raw.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return raw, False
    half = max(1, (limit - 32) // 2)
    clipped = encoded[:half] + b"\n...<excerpt truncated>...\n" + encoded[-half:]
    return clipped[:limit].decode("utf-8", errors="replace"), True


def _scan_top_level_province_fields(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    field_lines: list[str] = []
    depth = 0
    scalar = re.compile(r"\s*(?<![A-Za-z0-9_])(owner|controller)\s*=\s*\"?([A-Z0-9_]+)\"?")
    quoted = False
    escaped = False
    for line in lines:
        position = 0
        found_on_line = False
        while position < len(line):
            char = line[position]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                position += 1
                continue
            if char == '"':
                quoted = True
                position += 1
                continue
            if depth == 1:
                match = scalar.match(line, position)
                if match:
                    fields[match.group(1)] = match.group(2)
                    found_on_line = True
                    position = match.end()
                    continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            position += 1
        if found_on_line:
            field_lines.append(line.rstrip("\r\n"))
    return fields, field_lines


def _top_level_province_fields(lines: list[str]) -> dict[str, str]:
    return _scan_top_level_province_fields(lines)[0]


def scan_baseline_save(path: Path) -> dict[str, object]:
    """Stream the baseline gamestate and retain only differing owner/controller rows."""

    result: dict[str, object] = {
        "path": str(path.resolve()),
        "found": path.is_file(),
        "candidate_limit": MAX_BASELINE_CANDIDATES,
        "candidates": [],
    }
    if not path.is_file():
        result["error"] = "baseline save not found"
        return result
    result["size_bytes"] = path.stat().st_size
    source = bounded.detect_container(path)
    source["sha256"] = bounded.sha256_file(path)
    result["source"] = source
    line_count = 0
    province_block_found = False
    province_block_complete = False
    candidate_count = 0
    unknown: list[str] = []
    depth = 0
    province_depth: int | None = None
    active: dict[str, object] | None = None

    def finish_active(item: dict[str, object], end_line: int) -> None:
        nonlocal candidate_count
        lines = item["lines"]
        fields, field_lines = _scan_top_level_province_fields(lines)
        owner = fields.get("owner")
        controller = fields.get("controller")
        if owner is None or controller is None or owner == controller:
            return
        candidate_count += 1
        if len(result["candidates"]) >= MAX_BASELINE_CANDIDATES:
            return
        raw = "".join(lines)
        excerpt, excerpt_truncated = _short_text(raw)
        result["candidates"].append({
            "province_key": item["province_key"],
            "start_line": item["start_line"],
            "end_line": end_line,
            "owner_raw": owner,
            "controller_raw": controller,
            "fields_excerpt": field_lines,
            "raw_excerpt": excerpt,
            "raw_excerpt_truncated": bool(item["truncated"] or excerpt_truncated),
        })

    try:
        with bounded.open_gamestate(path, source) as stream:
            for line_number, line in enumerate(stream, 1):
                line_count = line_number
                before = depth
                if province_depth is None and before == 0 and re.match(
                    r"^\s*provinces\s*=\s*\{", line
                ):
                    province_block_found = True
                    province_depth = before + brace_delta(line)
                if province_depth is not None and active is None and before == province_depth:
                    match = re.match(r"^\s*(-?\d+)\s*=\s*\{", line)
                    if match:
                        active = {
                            "province_key": int(match.group(1)),
                            "start_line": line_number,
                            "depth": brace_delta(line),
                            "lines": [line],
                            "bytes": len(line.encode("utf-8", errors="replace")),
                            "truncated": False,
                        }
                        if active["depth"] == 0:
                            finish_active(active, line_number)
                            active = None
                elif active is not None:
                    encoded_size = len(line.encode("utf-8", errors="replace"))
                    if active["bytes"] + encoded_size <= MAX_BASELINE_EXCERPT_BYTES:
                        active["lines"].append(line)
                        active["bytes"] += encoded_size
                    else:
                        active["truncated"] = True
                    active["depth"] += brace_delta(line)
                    if active["depth"] == 0:
                        finish_active(active, line_number)
                        active = None
                delta = brace_delta(line)
                depth += delta
                if province_depth is not None and depth == 0:
                    province_block_complete = True
                    province_depth = None
            if active is not None:
                unknown.append("last_province_block_incomplete")
    except (OSError, KeyError, bounded.SaveParseError, ProbeError) as error:
        unknown.append(f"scan_error:{error}")
    if province_block_found and not province_block_complete:
        unknown.append("provinces_block_incomplete")
    result.update({
        "gamestate_line_count": line_count,
        "provinces_block_found": province_block_found,
        "provinces_block_complete": province_block_complete,
        "different_owner_controller_count": candidate_count,
        "candidate_limit_reached": candidate_count > MAX_BASELINE_CANDIDATES,
        "unknown": unknown,
        "streaming": True,
    })
    return result


def _configure_kernel() -> C.WinDLL:
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
    kernel.K32EnumProcessModulesEx.restype = W.BOOL
    kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    kernel.ReadProcessMemory.restype = W.BOOL
    return kernel


def _runtime_probe(pid: int, province_ids: list[int], expected_date_raw: int) -> dict[str, object]:
    if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8:
        raise ProbeError("requires 64-bit Windows Python")
    game_path = game_exe().resolve()
    if binary_sha256(game_path) != EXPECTED_HASH:
        raise ProbeError("unsupported executable build")
    kernel = _configure_kernel()
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        image_path = C.create_unicode_buffer(32768)
        length = W.DWORD(len(image_path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, image_path, C.byref(length)):
            raise C.WinError(C.get_last_error())
        if Path(image_path.value).resolve() != game_path:
            raise ProbeError("PID does not match the configured game executable")
        modules = (W.HMODULE * 1024)()
        needed = W.DWORD()
        if not kernel.K32EnumProcessModulesEx(handle, modules, C.sizeof(modules), C.byref(needed), 3):
            raise C.WinError(C.get_last_error())
        if not needed.value or needed.value > C.sizeof(modules):
            raise ProbeError("invalid module list")
        base = int(modules[0])

        def read(address: int, size: int) -> bytes:
            if not isinstance(address, int) or address < 0x10000 or size <= 0 or size > MAX_READ_BYTES:
                raise ProbeError("invalid bounded process read")
            buffer = C.create_string_buffer(size)
            actual = C.c_size_t()
            if not kernel.ReadProcessMemory(handle, address, buffer, size, C.byref(actual)):
                raise C.WinError(C.get_last_error())
            if actual.value != size:
                raise ProbeError("short process read")
            return buffer.raw

        def qword(address: int) -> int:
            return int.from_bytes(read(address, 8), "little")

        def integer(address: int, size: int = 4, signed: bool = True) -> int:
            return int.from_bytes(read(address, size), "little", signed=signed)

        if read(base, 2) != b"MZ":
            raise ProbeError("invalid module base")
        database = qword(base + DATABASE_POINTER_RVA)
        game = qword(base + GAME_POINTER_RVA)
        if not database or not game:
            raise ProbeError("game/database world is not initialized")
        current_date = integer(game + CURRENT_DATE_OFFSET)
        date_match = current_date == expected_date_raw
        if not date_match:
            raise ProbeError(
                f"raw date mismatch: expected {expected_date_raw}, observed {current_date}"
            )
        country_table = qword(database + COUNTRY_TABLE_OFFSET)
        begin = qword(game + PROVINCE_BEGIN_OFFSET)
        end = qword(game + PROVINCE_END_OFFSET)
        province_base = qword(game + PROVINCE_BASE_OFFSET)
        if end < begin or (end - begin) % 8:
            raise ProbeError("invalid province begin/end pair")
        count = (end - begin) // 8
        if count > MAX_PROVINCE_COUNT:
            raise ProbeError("province count exceeds bounded limit")
        if count and not province_base:
            raise ProbeError("province base is null for nonempty array")
        span = count * PROVINCE_RECORD_STRIDE
        span_end = province_base + span
        if span_end < province_base:
            raise ProbeError("province span overflows")

        def canonical_country(raw: int) -> dict[str, object]:
            value: dict[str, object] = {"raw_handle": hex(raw), "identity_verified": False, "tag": None}
            if not raw:
                value["reason"] = "zero_handle"
                return value
            slot = (raw >> 32) & 0xFFFF
            value["slot"] = slot
            if slot >= 4096:
                value["reason"] = "slot_out_of_bound"
                return value
            country = qword(country_table + slot * 8)
            value["country_pointer"] = hex(country)
            if not country:
                value["reason"] = "country_slot_empty"
                return value
            identity = qword(country + 0x20)
            value["identity_handle"] = hex(identity)
            if identity != raw:
                value["reason"] = "handle_identity_mismatch"
                return value
            tag_raw = (raw & 0xFFFFFF).to_bytes(3, "little")
            if any(byte not in TAG_BYTES for byte in tag_raw):
                value["reason"] = "noncanonical_tag_bytes"
                return value
            value["tag"] = tag_raw.decode("ascii")
            value["identity_verified"] = True
            return value

        records: list[dict[str, object]] = []
        for requested_id in province_ids:
            item: dict[str, object] = {"requested_province_id": requested_id}
            if requested_id >= count:
                item.update({"status": "out_of_array_bounds", "record": None})
                records.append(item)
                continue
            offset = requested_id * PROVINCE_RECORD_STRIDE
            record = province_base + offset
            if record < province_base or span_end - record < PROVINCE_RECORD_STRIDE:
                item.update({"status": "record_span_invalid", "record": None})
                records.append(item)
                continue
            stored_id = integer(record + PROVINCE_ID_OFFSET)
            item.update({"record": hex(record), "stored_province_id": stored_id})
            if stored_id != requested_id:
                item["status"] = "record_id_mismatch"
                records.append(item)
                continue
            field_468 = qword(record + PROVINCE_FIELD_468_OFFSET)
            field_470 = qword(record + PROVINCE_FIELD_470_OFFSET)
            item.update({
                "status": "ok",
                "field_468": canonical_country(field_468),
                "field_470": canonical_country(field_470),
                "semantic_labels": {
                    "field_468": "owner_or_controller_candidate_unresolved",
                    "field_470": "owner_or_controller_candidate_unresolved",
                },
            })
            records.append(item)
        return {
            "pid": pid,
            "read_only": True,
            "writes_performed": False,
            "native_methods_invoked": False,
            "binary_sha256": EXPECTED_HASH,
            "module_base": hex(base),
            "database_pointer": hex(database),
            "game_pointer": hex(game),
            "country_table": hex(country_table),
            "current_raw_date": current_date,
            "expected_raw_date": expected_date_raw,
            "date_match": date_match,
            "province_array": {
                "begin": hex(begin),
                "end": hex(end),
                "base": hex(province_base),
                "count": count,
                "record_stride": hex(PROVINCE_RECORD_STRIDE),
                "span_end": hex(span_end),
                "bounds_valid": True,
                "source": "game = *(image_base+0x233fe58); database = *(image_base+0x233d8b0)",
            },
            "records": records,
            "checks": {
                "pid_executable_matches": True,
                "build_hash_matches": True,
                "date_matches": date_match,
                "province_bounds_valid": True,
                "requested_record_ids_match": all(item.get("status") == "ok" for item in records),
            },
        }
    finally:
        kernel.CloseHandle(handle)


def default_baseline_path() -> Path:
    return user_data() / "save games" / BASELINE_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--province-ids", required=True, nargs="+")
    parser.add_argument("--expected-date-raw", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline-save", type=Path, default=None,
                        help=f"streaming baseline save (default: {BASELINE_NAME})")
    args = parser.parse_args()
    try:
        province_ids = parse_requested_ids(args.province_ids)
        baseline_path = args.baseline_save or default_baseline_path()
        baseline = scan_baseline_save(baseline_path)
        report = {
            "tool": "probe_peace_province_effects.py",
            "version": 1,
            "scope": "bounded read-only province record evidence",
            "requested_province_ids": province_ids,
            "baseline": baseline,
            "runtime": _runtime_probe(args.pid, province_ids, args.expected_date_raw),
        }
        report["status"] = "passed" if all(report["runtime"]["checks"].values()) else "failed"
    except Exception as error:
        report = {
            "tool": "probe_peace_province_effects.py",
            "version": 1,
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "status": report["status"],
        "baseline_different_owner_controller_count": baseline.get("different_owner_controller_count"),
        "requested_province_ids": province_ids,
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
