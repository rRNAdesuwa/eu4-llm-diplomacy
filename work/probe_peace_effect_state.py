#!/usr/bin/env python3
"""Read bounded native Peace effect state from a running EU4 process.

This probe is deliberately narrower than the normal diplomacy probes.  It
reads the current date, the verified country treasury field, and the verified
owner/controller fields for requested provinces.  It never calls an engine
method and opens the process with query/read permissions only.  Raw pointers
and handles are evidence for the private reload report; callers must not put
them in the public diplomacy projection.
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
    from local_config import game_exe
except ModuleNotFoundError:
    from work.local_config import game_exe


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
PROVINCE_OWNER_OFFSET = 0x468
PROVINCE_CONTROLLER_OFFSET = 0x470
TREASURY_OFFSET = 0xBB0
MAX_COUNTRY_SLOTS = 256
MAX_COUNTRY_REQUESTS = 32
MAX_PROVINCE_REQUESTS = 16
MAX_PROVINCE_COUNT = 1_000_000
MAX_READ_BYTES = 1 << 20
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
TAG_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


class ProbeError(RuntimeError):
    """A bounded read or structural validation failed."""


def binary_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_tags(values: list[str]) -> list[str]:
    if not 1 <= len(values) <= MAX_COUNTRY_REQUESTS:
        raise argparse.ArgumentTypeError(
            f"--countries requires 1..{MAX_COUNTRY_REQUESTS} tags")
    result: list[str] = []
    for value in values:
        tag = value.strip().upper()
        if not TAG_RE.fullmatch(tag):
            raise argparse.ArgumentTypeError(f"invalid country tag: {value}")
        if tag in result:
            raise argparse.ArgumentTypeError(f"duplicate country tag: {tag}")
        result.append(tag)
    return result


def parse_province_ids(values: list[str]) -> list[int]:
    if len(values) > MAX_PROVINCE_REQUESTS:
        raise argparse.ArgumentTypeError(
            f"--provinces accepts at most {MAX_PROVINCE_REQUESTS} IDs")
    result: list[int] = []
    for value in values:
        try:
            province_id = int(value, 0)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"invalid province ID: {value}") from error
        if not 0 <= province_id <= MAX_PROVINCE_COUNT:
            raise argparse.ArgumentTypeError(f"province ID out of bounds: {province_id}")
        if province_id in result:
            raise argparse.ArgumentTypeError(f"duplicate province ID: {province_id}")
        result.append(province_id)
    return result


def _configure_kernel() -> C.WinDLL:
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [
        W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [
        W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
    kernel.K32EnumProcessModulesEx.restype = W.BOOL
    kernel.ReadProcessMemory.argtypes = [
        W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    kernel.ReadProcessMemory.restype = W.BOOL
    return kernel


def _runtime_probe(pid: int, countries: list[str], provinces: list[int],
                   expected_date_raw: int) -> dict[str, object]:
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
            raise ProbeError("PID does not match configured game executable")
        modules = (W.HMODULE * 1024)()
        needed = W.DWORD()
        if not kernel.K32EnumProcessModulesEx(
                handle, modules, C.sizeof(modules), C.byref(needed), 3):
            raise C.WinError(C.get_last_error())
        if not needed.value or needed.value > C.sizeof(modules):
            raise ProbeError("invalid module list")
        base = int(modules[0])

        def read(address: int, size: int) -> bytes:
            if (not isinstance(address, int) or address < 0x10000
                    or size <= 0 or size > MAX_READ_BYTES):
                raise ProbeError("invalid bounded process read")
            buffer = C.create_string_buffer(size)
            actual = C.c_size_t()
            if not kernel.ReadProcessMemory(
                    handle, address, buffer, size, C.byref(actual)):
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
        country_table = qword(database + COUNTRY_TABLE_OFFSET)
        if not country_table:
            raise ProbeError("country table is null")

        country_by_tag: dict[str, dict[str, object]] = {}
        for slot in range(MAX_COUNTRY_SLOTS):
            country = qword(country_table + slot * 8)
            if not country:
                continue
            try:
                identity = qword(country + 0x20)
            except (OSError, ProbeError):
                continue
            encoded_slot = (identity >> 32) & 0xFFFF
            tag_bytes = (identity & 0xFFFFFF).to_bytes(3, "little")
            if encoded_slot != slot or any(byte not in TAG_BYTES for byte in tag_bytes):
                continue
            tag = tag_bytes.decode("ascii")
            country_by_tag[tag] = {
                "slot": slot,
                "pointer": country,
                "handle": identity,
            }

        country_records: list[dict[str, object]] = []
        for tag in countries:
            item: dict[str, object] = {
                "tag": tag,
                "field_offset": hex(TREASURY_OFFSET),
                "currency_scale": 1000,
                "treasury_readable": False,
                "treasury_raw": None,
                "identity_verified": False,
            }
            entry = country_by_tag.get(tag)
            if entry is None:
                item["reason"] = "country_not_found_in_bounded_table"
                country_records.append(item)
                continue
            item.update({
                "slot": entry["slot"],
                "raw_handle": hex(int(entry["handle"])),
                "country_pointer": hex(int(entry["pointer"])),
                "identity_verified": True,
            })
            try:
                item["treasury_raw"] = integer(
                    int(entry["pointer"]) + TREASURY_OFFSET)
                item["treasury_readable"] = True
            except (OSError, ProbeError) as error:
                item["reason"] = f"treasury_read_failed:{type(error).__name__}"
            country_records.append(item)

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
        span_end = province_base + count * PROVINCE_RECORD_STRIDE
        if span_end < province_base:
            raise ProbeError("province span overflows")

        def canonical(raw: int) -> dict[str, object]:
            value: dict[str, object] = {
                "raw_handle": hex(raw), "tag": None, "identity_verified": False,
            }
            entry = None
            for candidate in country_by_tag.values():
                if int(candidate["handle"]) == raw:
                    entry = candidate
                    break
            if entry is None:
                value["reason"] = "country_handle_not_in_bounded_table"
                return value
            value.update({
                "tag": next(tag for tag, item in country_by_tag.items() if item is entry),
                "slot": entry["slot"],
                "identity_verified": True,
            })
            return value

        province_records: list[dict[str, object]] = []
        for province_id in provinces:
            item: dict[str, object] = {
                "province_id": province_id,
                "record_readable": False,
                "owner": None,
                "controller": None,
            }
            if province_id >= count:
                item["reason"] = "province_id_out_of_array_bounds"
                province_records.append(item)
                continue
            record = province_base + province_id * PROVINCE_RECORD_STRIDE
            if record < province_base or span_end - record < PROVINCE_RECORD_STRIDE:
                item["reason"] = "record_span_invalid"
                province_records.append(item)
                continue
            stored_id = integer(record + PROVINCE_ID_OFFSET)
            item["stored_province_id"] = stored_id
            if stored_id != province_id:
                item["reason"] = "record_id_mismatch"
                province_records.append(item)
                continue
            owner_raw = qword(record + PROVINCE_OWNER_OFFSET)
            controller_raw = qword(record + PROVINCE_CONTROLLER_OFFSET)
            item.update({
                "record_readable": True,
                "owner": canonical(owner_raw),
                "controller": canonical(controller_raw),
                "owner_field_offset": hex(PROVINCE_OWNER_OFFSET),
                "controller_field_offset": hex(PROVINCE_CONTROLLER_OFFSET),
            })
            province_records.append(item)

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
            "countries": country_records,
            "provinces": province_records,
            "province_array": {
                "begin": hex(begin), "end": hex(end), "base": hex(province_base),
                "count": count, "record_stride": hex(PROVINCE_RECORD_STRIDE),
                "bounds_valid": True,
            },
            "checks": {
                "pid_executable_matches": True,
                "build_hash_matches": True,
                "date_matches": date_match,
                "country_requests_readable": all(
                    item.get("treasury_readable") is True for item in country_records),
                "province_requests_readable": all(
                    item.get("record_readable") is True for item in province_records),
            },
        }
    finally:
        kernel.CloseHandle(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--countries", required=True, nargs="+")
    parser.add_argument("--provinces", nargs="*", default=[])
    parser.add_argument("--expected-date-raw", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        countries = parse_tags(args.countries)
        provinces = parse_province_ids(args.provinces)
        runtime = _runtime_probe(args.pid, countries, provinces, args.expected_date_raw)
        report: dict[str, object] = {
            "tool": "probe_peace_effect_state.py",
            "version": 1,
            "scope": "bounded read-only country treasury and province effect state",
            "requested_countries": countries,
            "requested_provinces": provinces,
            "runtime": runtime,
            "read_only": True,
            "status": "passed" if all(runtime["checks"].values()) else "failed",
        }
    except Exception as error:
        report = {
            "tool": "probe_peace_effect_state.py",
            "version": 1,
            "scope": "bounded read-only country treasury and province effect state",
            "read_only": True,
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "status": report["status"], "read_only": True,
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
