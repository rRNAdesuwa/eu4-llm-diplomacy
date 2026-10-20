#!/usr/bin/env python3
"""Read bounded native Peace effect state from a running EU4 process.

This probe is deliberately narrower than the normal diplomacy probes.  It
reads the current date, the verified country treasury and prestige fields, and
the verified owner/controller fields for requested provinces.  The optional
``--province-cores`` flag also reads their bounded core-country vectors.  It
never calls an engine method and opens the process with query/read permissions only.  Raw pointers
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
from typing import Callable

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
PROVINCE_CORES_BEGIN_OFFSET = 0x490
PROVINCE_CORES_END_OFFSET = 0x498
MAX_PROVINCE_CORE_COUNT = 256
TREASURY_OFFSET = 0xBB0
PRESTIGE_OFFSET = 0xCF8
PRESTIGE_SCALE1000 = 1000
POWERS_OFFSETS = (0x260, 0x264, 0x268)
HUMILIATED_BEGIN_OFFSET = 0x2408
HUMILIATED_COUNT_OFFSET = 0x2414
RELIGION_PTR_OFFSET = 0xF30
CAPITAL_PTR_OFFSET = 0x14B0
CAPITAL_RELIGION_PTR_OFFSET = 0x448
RELIGION_STRING_OFFSET = 0x90
RELIGION_STRING_SIZE_OFFSET = 0xA0
RELIGION_STRING_CAPACITY_OFFSET = 0xA8
MAX_RELIGION_KEY = 63
MAX_COUNTRY_SLOTS = 256
MAX_COUNTRY_REQUESTS = 32
MAX_PROVINCE_REQUESTS = 16
MAX_PROVINCE_COUNT = 1_000_000
MAX_READ_BYTES = 1 << 20
MAX_RELATION_COUNT = 4096
TRADE_POWER_RELATION_VTABLE_RVA = 0x1C571F0
TRADE_POWER_RELATION_DISCRIMINATOR = 0x165
TRADE_POWER_RELATION_VECTOR_OFFSET = 0x228
TRADE_POWER_AMOUNT_SCALE = 1000
ANNUL_RELATION_VTABLE_RVA = 0x1CB3B48
ANNUL_RELATION_DISCRIMINATOR = 0x165
ANNUL_RELATION_VECTOR_OFFSET = 0x180
ALLIANCE_RELATION_BEGIN_OFFSET = 0x80
ALLIANCE_RELATION_COUNT_OFFSET = 0x8C
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,5}$")
TAG_BYTES = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")


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


def _trade_power_relation_entry(
    source_entry: dict[str, object],
    beneficiary_entry: dict[str, object],
    qword: Callable[[int], int],
    integer: Callable[[int, int, bool], int],
) -> int:
    """Return the source country's current trade relation pointer.

    The country row indexed by the beneficiary slot owns a relation vector at
    ``country+0x228``.  The vector stores ``{beneficiary_slot, treaty_ptr}``
    records with a 16-byte stride.  A missing candidate is a valid, complete
    absence observation; malformed rows remain probe failures.
    """

    source = int(source_entry["pointer"])
    source_handle = int(source_entry["handle"])
    beneficiary_handle = int(beneficiary_entry["handle"])
    beneficiary_slot = (beneficiary_handle >> 32) & 0xFFFF
    if not 0 <= beneficiary_slot < MAX_COUNTRY_SLOTS:
        raise ProbeError("trade power beneficiary slot is out of bounds")

    rows = qword(source + 0x1510)
    if not rows:
        raise ProbeError("trade power country relation rows are null")
    row = rows + beneficiary_slot * 0x48
    owner = qword(row)
    if (not owner or qword(row + 8) != source_handle
            or qword(row + 0x10) != beneficiary_handle):
        raise ProbeError("trade power relation endpoints changed")

    data = qword(owner + TRADE_POWER_RELATION_VECTOR_OFFSET + 8)
    capacity = integer(owner + TRADE_POWER_RELATION_VECTOR_OFFSET + 0x10, 4, True)
    count = integer(owner + TRADE_POWER_RELATION_VECTOR_OFFSET + 0x14, 4, True)
    if (count < 0 or count > MAX_RELATION_COUNT or capacity < count
            or (count and not data)):
        raise ProbeError("invalid bounded trade power relation array")

    found = 0
    for index in range(count):
        item = data + index * 16
        other_slot = integer(item, 4, True)
        candidate = qword(item + 8)
        if other_slot != beneficiary_slot:
            continue
        if found or not candidate:
            raise ProbeError("ambiguous trade power relation")
        found = candidate
    return found


def _read_trade_power_state(
    source_entry: dict[str, object],
    beneficiary_entry: dict[str, object],
    base: int,
    current_date: int,
    qword: Callable[[int], int],
    integer: Callable[[int, int, bool], int],
) -> dict[str, object]:
    """Read one bounded source-to-beneficiary trade-power state."""

    state: dict[str, object] = {
        "source": source_entry["tag"],
        "beneficiary": beneficiary_entry["tag"],
        "present": False,
        "start_date_raw": 0,
        "end_date_raw": 0,
        "amount_raw": 0,
        "amount_scale": TRADE_POWER_AMOUNT_SCALE,
        "peace_treaty": False,
        "complete": False,
    }
    entry = _trade_power_relation_entry(source_entry, beneficiary_entry, qword, integer)
    if not entry:
        # Absence is a complete observation and does not require traversing a
        # reverse/beneficiary-owned relation list.
        state["complete"] = True
        return state

    table = qword(entry)
    discriminator = integer(entry + 8, 4, True)
    actual_source = qword(entry + 0x10)
    actual_beneficiary = qword(entry + 0x18)
    if (table != base + TRADE_POWER_RELATION_VTABLE_RVA
            or discriminator != TRADE_POWER_RELATION_DISCRIMINATOR
            or actual_source != int(source_entry["handle"])
            or actual_beneficiary != int(beneficiary_entry["handle"])):
        raise ProbeError("trade power treaty identity or endpoints changed")

    start_date = integer(entry + 0x20, 4, True)
    end_date = integer(entry + 0x24, 4, True)
    amount = integer(entry + 0x40, 4, True)
    enforced = integer(entry + 0x44, 1, False)
    if enforced > 1:
        raise ProbeError("trade power peace-treaty flag is invalid")
    state.update({
        "present": True,
        "start_date_raw": start_date,
        "end_date_raw": end_date,
        "amount_raw": amount,
        "peace_treaty": bool(enforced),
        # Native completeness is date-start readability.  The end field may
        # be the open-ended sentinel 0x29c77f8 and is intentionally not treated
        # as a fixed-duration expiry by this probe.
        "complete": start_date <= current_date,
    })
    return state


def _annul_relation_entry(
    country_entry: dict[str, object],
    partner_entry: dict[str, object],
    qword: Callable[[int], int],
    integer: Callable[[int, int, bool], int],
) -> int:
    """Find one directed annul relation in the owner+0x180 pair vector."""
    rows = qword(int(country_entry["pointer"]) + 0x1510)
    if not rows:
        raise ProbeError("annul country relation rows are null")
    row = rows + int(partner_entry["slot"]) * 0x48
    owner = qword(row)
    if (not owner or qword(row + 8) != int(country_entry["handle"])
            or qword(row + 0x10) != int(partner_entry["handle"])):
        raise ProbeError("annul relation endpoints changed")
    data = qword(owner + ANNUL_RELATION_VECTOR_OFFSET + 8)
    capacity = integer(owner + ANNUL_RELATION_VECTOR_OFFSET + 0x10, 4, True)
    count = integer(owner + ANNUL_RELATION_VECTOR_OFFSET + 0x14, 4, True)
    if (count < 0 or count > MAX_RELATION_COUNT or capacity < count
            or (count and not data)):
        raise ProbeError("invalid bounded annul relation array")
    found = 0
    for index in range(count):
        item = data + index * 16
        if integer(item, 4, True) != int(partner_entry["slot"]):
            continue
        candidate = qword(item + 8)
        if found or not candidate:
            raise ProbeError("ambiguous annul relation")
        found = candidate
    return found


def _subject_relation_entry(country_entry, partner_entry, qword, integer):
    """Read the verified subject pair vector, independent of native observers."""
    rows = qword(int(country_entry["pointer"]) + 0x1510)
    if not rows:
        raise ProbeError("subject relation rows are null")
    row = rows + int(partner_entry["slot"]) * 0x48
    owner = qword(row)
    if (not owner or qword(row + 8) != int(country_entry["handle"])
            or qword(row + 0x10) != int(partner_entry["handle"])):
        raise ProbeError("subject relation endpoints changed")
    begin = qword(owner + 0x128)
    count = integer(owner + 0x134, 4, True)
    if not 0 <= count <= MAX_RELATION_COUNT or (count and not begin):
        raise ProbeError("invalid bounded subject relation array")
    found = 0
    for index in range(count):
        item = begin + index * 16
        if integer(item, 4, True) != int(partner_entry["slot"]):
            continue
        candidate = qword(item + 8)
        if found or not candidate:
            raise ProbeError("ambiguous subject relation")
        found = candidate
    return found


def _read_subject_state(source, target, qword, integer, read):
    forward = _subject_relation_entry(source, target, qword, integer)
    reverse = _subject_relation_entry(target, source, qword, integer)
    if forward != reverse:
        raise ProbeError("subject relation directions disagree")
    result = {"source": source["tag"], "country": target["tag"],
              "relation_active": bool(forward), "source_is_overlord": False,
              "subject_type": None, "complete": True}
    if not forward:
        return result
    subject = qword(forward + 0x18)
    if subject not in (int(source["handle"]), int(target["handle"])):
        raise ProbeError("subject association endpoint changed")
    descriptor = qword(forward + 0x40)
    if not descriptor:
        raise ProbeError("subject type descriptor is null")
    size = integer(descriptor + 0x20, 8, False)
    capacity = integer(descriptor + 0x28, 8, False)
    if not 1 <= size <= 64 or capacity < size or capacity > 65536:
        raise ProbeError("subject type string bounds are invalid")
    text = descriptor + 0x10 if capacity < 16 else qword(descriptor + 0x10)
    raw = read(text, size)
    if any(byte < 0x20 or byte > 0x7e or byte in (34, 92) for byte in raw):
        raise ProbeError("subject type key contains invalid bytes")
    result.update(source_is_overlord=subject == int(target["handle"]),
                  subject_type=raw.decode("ascii"))
    return result


def _read_alliance_state(
        country_entry: dict[str, object],
        partner_entry: dict[str, object],
        qword: Callable[[int], int],
        integer: Callable[[int, int, bool], int],
        ) -> tuple[bool, bool]:
    """Read the verified alliance membership vector for one directed pair."""
    rows = qword(int(country_entry["pointer"]) + 0x1510)
    if not rows:
        return False, False
    row = rows + int(partner_entry["slot"]) * 0x48
    owner = qword(row)
    if not owner or qword(row + 0x10) != int(partner_entry["handle"]):
        return False, False
    begin = qword(owner + ALLIANCE_RELATION_BEGIN_OFFSET)
    count = integer(owner + ALLIANCE_RELATION_COUNT_OFFSET, 4, True)
    if count < 0 or count > MAX_RELATION_COUNT or (count and not begin):
        return False, False
    slots = {
        integer(begin + index * 16, 4, True)
        for index in range(count)
    }
    return int(partner_entry["slot"]) in slots, True


def _read_annul_state(
        country_entry: dict[str, object],
        partner_entry: dict[str, object],
        base: int,
        current_date: int,
        qword: Callable[[int], int],
        integer: Callable[[int, int, bool], int],
        ) -> dict[str, object]:
    state: dict[str, object] = {
        "country": country_entry["tag"], "partner": partner_entry["tag"],
        "present": False, "start_date_raw": 0, "end_date_raw": 0,
        "alliance": False, "alliance_readable": False, "complete": False,
    }
    relation = _annul_relation_entry(country_entry, partner_entry, qword, integer)
    alliance, alliance_readable = _read_alliance_state(
        country_entry, partner_entry, qword, integer)
    state["alliance"] = alliance
    state["alliance_readable"] = alliance_readable
    if not relation:
        state["complete"] = alliance_readable
        return state
    table = qword(relation)
    discr = integer(relation + 8, 4, True)
    actual_country, actual_partner = qword(relation + 0x10), qword(relation + 0x18)
    if (table != base + ANNUL_RELATION_VTABLE_RVA
            or discr != ANNUL_RELATION_DISCRIMINATOR
            or actual_country != int(country_entry["handle"])
            or actual_partner != int(partner_entry["handle"])):
        raise ProbeError("annul treaty identity or endpoints changed")
    start_date = integer(relation + 0x20, 4, True)
    end_date = integer(relation + 0x24, 4, True)
    state.update({
        "present": True, "start_date_raw": start_date,
        "end_date_raw": end_date,
        "complete": start_date <= current_date and alliance_readable,
        "private_record_pointer": hex(relation),
    })
    return state


def _read_religion_key(
        religion_pointer: int,
        read: Callable[[int, int], bytes],
        integer: Callable[[int, int, bool], int],
        ) -> tuple[str | None, bool]:
    """Read one bounded SSO religion key (at most 63 ASCII identifier bytes)."""
    if not religion_pointer:
        return None, False
    size = integer(religion_pointer + RELIGION_STRING_SIZE_OFFSET, 8, False)
    capacity = integer(religion_pointer + RELIGION_STRING_CAPACITY_OFFSET, 8, False)
    if size > MAX_RELIGION_KEY or capacity < size or capacity > 4096:
        raise ProbeError("religion SSO bounds are invalid")
    if size == 0:
        return "", True
    # This is the engine's std::string-like SSO layout.  Keys with capacity
    # <= 15 are stored inline at +0x90; long keys store a pointer at +0x90
    # and the bytes at that bounded heap address.  Do not read the inline
    # bytes for the long representation: those bytes are the pointer itself.
    data_pointer = religion_pointer + RELIGION_STRING_OFFSET
    if capacity > 15:
        data_pointer = integer(religion_pointer + RELIGION_STRING_OFFSET,
                               8, False)
        if not data_pointer:
            raise ProbeError("long religion key has a null data pointer")
    raw = read(data_pointer, size)
    if len(raw) != size or any(byte not in TAG_BYTES for byte in raw):
        raise ProbeError("religion key contains non-identifier bytes")
    return raw.decode("ascii"), True


def _read_country_religions(
        entry: dict[str, object],
        qword: Callable[[int], int],
        read: Callable[[int, int], bytes],
        integer: Callable[[int, int, bool], int],
        province_base: int | None = None,
        province_count: int | None = None,
        ) -> dict[str, object]:
    pointer = int(entry["pointer"])
    religion_ptr = qword(pointer + RELIGION_PTR_OFFSET)
    religion, readable = _read_religion_key(religion_ptr, read, integer)
    capital_ptr = qword(pointer + CAPITAL_PTR_OFFSET)
    capital_religion_ptr = (
        qword(capital_ptr + CAPITAL_RELIGION_PTR_OFFSET)
        if capital_ptr else 0)
    capital_religion, capital_readable = _read_religion_key(
        capital_religion_ptr, read, integer)
    # ``country+0x14B0`` is the capital's province record pointer.  The
    # existing bounded province table uses the same record stride and stores
    # its canonical id at ``province+0x20`` (validated below); derive the id
    # only after both the table bounds and the in-record id agree.  This keeps
    # the new evidence tied to the established table/index contract rather
    # than accepting an arbitrary integer adjacent to the country object.
    capital_province_id: int | None = None
    capital_province_id_verified = False
    if (capital_ptr and province_base is not None
            and province_count is not None and province_count >= 0):
        offset = capital_ptr - province_base
        if (0 <= offset < province_count * PROVINCE_RECORD_STRIDE
                and offset % PROVINCE_RECORD_STRIDE == 0):
            candidate = offset // PROVINCE_RECORD_STRIDE
            stored_id = integer(capital_ptr + PROVINCE_ID_OFFSET, 4, True)
            if stored_id == candidate and 0 <= candidate < province_count:
                capital_province_id = candidate
                capital_province_id_verified = True
    return {
        "religion": religion,
        "capital_religion": capital_religion,
        "capital_province_id": capital_province_id,
        "capital_province_id_verified": capital_province_id_verified,
        "religion_readable": readable,
        "capital_religion_readable": capital_readable,
    }


def _read_powers(entry: dict[str, object], integer: Callable[[int, int, bool], int]) -> dict[str, object]:
    values = [integer(int(entry["pointer"]) + offset, 4, True)
              for offset in POWERS_OFFSETS]
    return {
        "values": values,
        # Monarch points are serialized/read as integer points.  The 1000
        # scale belongs to prestige and money fields, not this native row.
        "scale": 1,
        "readable": all(type(value) is int for value in values),
    }


def _read_humiliated_state(
        country_entry: dict[str, object],
        beneficiary_entry: dict[str, object],
        qword: Callable[[int], int],
        integer: Callable[[int, int, bool], int],
        ) -> dict[str, object]:
    # Native stores the winner's/beneficiary's humiliated-country vector.
    # Read that vector from the beneficiary, then match the defeated country's
    # handle.  Reading country_entry and looking for the beneficiary reverses
    # the relation and can report false after an accepted humiliation.
    pointer = int(beneficiary_entry["pointer"])
    begin = qword(pointer + HUMILIATED_BEGIN_OFFSET)
    count = integer(pointer + HUMILIATED_COUNT_OFFSET, 4, True)
    if count < 0 or count > MAX_RELATION_COUNT or (count and not begin):
        raise ProbeError("invalid bounded humiliated-rival list")
    handles = [qword(begin + index * 8) for index in range(count)]
    if len(set(handles)) != len(handles):
        raise ProbeError("duplicate humiliated-rival handles")
    present = int(country_entry["handle"]) in handles
    return {
        "present": present,
        "humiliated": present,
        "count": count,
        "complete": True,
    }


def _country_lookup_entry(tag: str, slot: int, pointer: int,
                          handle: int) -> dict[str, object]:
    """Build the canonical bounded lookup entry used by relation readers."""

    return {
        "tag": tag,
        "slot": slot,
        "pointer": pointer,
        "handle": handle,
    }


def _read_province_cores(
        province: int, qword: Callable[[int], int],
        canonical: Callable[[int], dict[str, object]],
        ) -> dict[str, object]:
    """Read the core handle vector identified in native RemoveAsCore.

    This observes only province+0x490/+0x498.  The second deletion container
    at +0x4a8 has a separate, currently unverified layout and is not read.
    """
    begin = qword(province + PROVINCE_CORES_BEGIN_OFFSET)
    end = qword(province + PROVINCE_CORES_END_OFFSET)
    if (end < begin or (end - begin) % 8
            or (end - begin) // 8 > MAX_PROVINCE_CORE_COUNT
            or (end != begin and begin < 0x10000)):
        raise ProbeError("invalid bounded province core vector")
    handles = [qword(begin + index * 8)
               for index in range((end - begin) // 8)]
    if len(set(handles)) != len(handles):
        raise ProbeError("duplicate province core country handles")
    countries = [canonical(raw) for raw in handles]
    complete = all(item.get("identity_verified") is True for item in countries)
    return {
        "count": len(handles),
        "countries": countries,
        "tags": [item["tag"] for item in countries
                 if item.get("identity_verified") is True],
        "complete": complete,
        "vector_readable": True,
        "begin_field_offset": hex(PROVINCE_CORES_BEGIN_OFFSET),
        "end_field_offset": hex(PROVINCE_CORES_END_OFFSET),
    }


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
                   expected_date_raw: int, reparations_payer: str | None = None,
                   reparations_claimant: str | None = None,
                   trade_power_source: str | None = None,
                   trade_power_beneficiary: str | None = None,
                   annul_country: str | None = None,
                   annul_partners: list[str] | None = None,
                   special_action: str | None = None,
                   special_country: str | None = None,
                   special_beneficiary: str | None = None,
                   province_cores: bool = False,
                   subject_pairs: list[tuple[str, str]] | None = None) -> dict[str, object]:
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
            # Treaty readers receive these entries directly, so retain the
            # canonical tag along with the pointer/handle identity.
            country_by_tag[tag] = _country_lookup_entry(
                tag, slot, country, identity)

        country_records: list[dict[str, object]] = []
        for tag in countries:
            item: dict[str, object] = {
                "tag": tag,
                "field_offset": hex(TREASURY_OFFSET),
                "currency_scale": 1000,
                "treasury_readable": False,
                "treasury_raw": None,
                "prestige_field_offset": hex(PRESTIGE_OFFSET),
                "prestige_scale": PRESTIGE_SCALE1000,
                "prestige_readable": False,
                "prestige_raw": None,
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
            try:
                item["prestige_raw"] = integer(
                    int(entry["pointer"]) + PRESTIGE_OFFSET)
                item["prestige_readable"] = True
            except (OSError, ProbeError) as error:
                item["reason"] = f"prestige_read_failed:{type(error).__name__}"
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
            if province_cores:
                try:
                    item["cores"] = _read_province_cores(record, qword, canonical)
                except (OSError, ProbeError) as error:
                    item["cores"] = {
                        "complete": False,
                        "vector_readable": False,
                        "reason": f"core_vector_read_failed:{type(error).__name__}:{error}",
                    }
            province_records.append(item)

        reparations = None
        if reparations_payer is not None:
            payer_entry = country_by_tag.get(reparations_payer)
            claimant_entry = country_by_tag.get(reparations_claimant)
            if payer_entry is None or claimant_entry is None:
                raise ProbeError("reparations endpoints missing from bounded country table")

            def relation_entry(source: dict, other: dict) -> int:
                rows = qword(int(source["pointer"]) + 0x1510)
                row = rows + int(other["slot"]) * 0x48
                if (qword(row + 8) != int(source["handle"])
                        or qword(row + 0x10) != int(other["handle"])):
                    raise ProbeError("reparations relation endpoints changed")
                owner = qword(row)
                begin = qword(owner + 0x98)
                capacity = integer(owner + 0xA0)
                count = integer(owner + 0xA4)
                if not 0 <= count <= 4096 or capacity < count or (count and not begin):
                    raise ProbeError("invalid bounded reparations relation array")
                found = 0
                for index in range(count):
                    item = begin + index * 16
                    if integer(item) != int(other["slot"]):
                        continue
                    candidate = qword(item + 8)
                    if found or not candidate:
                        raise ProbeError("ambiguous reparations relation")
                    found = candidate
                return found

            forward = relation_entry(payer_entry, claimant_entry)
            reverse = relation_entry(claimant_entry, payer_entry)
            if forward != reverse:
                raise ProbeError("reparations forward/reverse records disagree")
            reparations = {
                "payer": reparations_payer, "claimant": reparations_claimant,
                "active": False, "present": False, "complete": True,
                "start_date_raw": None, "end_date_raw": None,
            }
            if forward:
                if (qword(forward) != base + 0x1CDDEE0
                        or integer(forward + 8) != 0x165):
                    raise ProbeError("reparations treaty identity changed")
                first, second = qword(forward + 0x10), qword(forward + 0x18)
                start_date = integer(forward + 0x20)
                end_date = integer(forward + 0x24)
                if end_date <= start_date:
                    raise ProbeError("invalid reparations treaty dates")
                wanted = (int(payer_entry["handle"]), int(claimant_entry["handle"]))
                if (first, second) == wanted:
                    reparations.update({
                        "active": start_date <= current_date < end_date,
                        "present": True, "start_date_raw": start_date,
                        "end_date_raw": end_date, "private_record_pointer": hex(forward),
                    })
                elif (first, second) != wanted[::-1]:
                    raise ProbeError("reparations treaty endpoints changed")

        trade_power = None
        if trade_power_source is not None:
            source_entry = country_by_tag.get(trade_power_source)
            beneficiary_entry = country_by_tag.get(trade_power_beneficiary)
            if source_entry is None or beneficiary_entry is None:
                raise ProbeError("trade power endpoints missing from bounded country table")
            trade_power = _read_trade_power_state(
                source_entry, beneficiary_entry, base, current_date, qword, integer)

        special = None
        if special_action is not None:
            if special_action not in {"humiliate_rival", "show_strength", "force_religion"}:
                raise ProbeError("unknown special peace action")
            if not special_country or not special_beneficiary:
                raise ProbeError("special country and beneficiary are required")
            country_entry = country_by_tag.get(special_country)
            beneficiary_entry = country_by_tag.get(special_beneficiary)
            if country_entry is None or beneficiary_entry is None:
                raise ProbeError("special endpoints missing from bounded country table")
            country_pointer = int(country_entry["pointer"])
            beneficiary_pointer = int(beneficiary_entry["pointer"])
            special = {
                "action_id": special_action,
                "country": special_country,
                "beneficiary": special_beneficiary,
                "humiliated": None,
                "country_prestige_raw": integer(country_pointer + PRESTIGE_OFFSET),
                "beneficiary_prestige_raw": integer(beneficiary_pointer + PRESTIGE_OFFSET),
                "prestige_scale": PRESTIGE_SCALE1000,
                "prestige_scale1000": PRESTIGE_SCALE1000,
                "values_readable": True,
                "complete": True,
            }
            if special_action in {"humiliate_rival", "show_strength"}:
                special.update(_read_humiliated_state(
                    country_entry, beneficiary_entry, qword, integer))
            if special_action == "show_strength":
                # Native show-strength settlement transfers the requested
                # power from the defeated country to the beneficiary.  The
                # effect's powers_after therefore belongs to the beneficiary
                # (the winner), not to ``country``.
                special["powers"] = _read_powers(beneficiary_entry, integer)
                special["powers_requested"] = None
            if special_action == "force_religion":
                country_religion = _read_country_religions(
                    country_entry, qword, read, integer,
                    province_base, count)
                beneficiary_religion = _read_country_religions(
                    beneficiary_entry, qword, read, integer,
                    province_base, count)
                special.update({
                    "religion": country_religion["religion"],
                    "capital_religion": country_religion["capital_religion"],
                    "capital_province_id": country_religion[
                        "capital_province_id"],
                    "capital_province_id_verified": country_religion[
                        "capital_province_id_verified"],
                    "beneficiary_religion": beneficiary_religion["religion"],
                    "religion_readable": country_religion["religion_readable"],
                    "capital_religion_readable": country_religion[
                        "capital_religion_readable"],
                    "beneficiary_religion_readable": beneficiary_religion[
                        "religion_readable"],
                })
            for item in country_records:
                if item.get("tag") == special_country:
                    item.update({
                        "religion": special.get("religion"),
                        "capital_religion": special.get("capital_religion"),
                        "capital_province_id": special.get(
                            "capital_province_id"),
                        "capital_province_id_verified": special.get(
                            "capital_province_id_verified"),
                        "special_state_readable": True,
                    })
                elif item.get("tag") == special_beneficiary:
                    item.update({
                        "powers": special.get("powers"),
                        "religion": special.get("beneficiary_religion"),
                        "special_state_readable": True,
                    })

        annul_treaties = None
        if annul_country is not None:
            country_entry = country_by_tag.get(annul_country)
            if country_entry is None:
                raise ProbeError("annul country missing from bounded country table")
            if not isinstance(annul_partners, list) or not annul_partners:
                raise ProbeError("annul treaty partners are required")
            annul_treaties = []
            for partner in annul_partners:
                partner_entry = country_by_tag.get(partner)
                if partner_entry is None:
                    raise ProbeError(
                        f"annul partner missing from bounded country table: {partner}")
                annul_treaties.append(_read_annul_state(
                    country_entry, partner_entry, base, current_date,
                    qword, integer))

        subject_relations = []
        for source_tag, target_tag in subject_pairs or []:
            source_entry = country_by_tag.get(source_tag)
            target_entry = country_by_tag.get(target_tag)
            if source_entry is None or target_entry is None:
                raise ProbeError("subject endpoint missing from bounded country table")
            subject_relations.append(_read_subject_state(
                source_entry, target_entry, qword, integer, read))

        special_results = {
            "humiliate_rival": special if special_action == "humiliate_rival" else None,
            "show_strength": special if special_action == "show_strength" else None,
            "force_religion": special if special_action == "force_religion" else None,
        }
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
            "war_reparations": reparations,
            "transfer_trade_power": trade_power,
            "annul_treaties": annul_treaties,
            "subject_relations": subject_relations,
            "special": special,
            **special_results,
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
                    item.get("treasury_readable") is True
                    and item.get("prestige_readable") is True
                    and item.get("prestige_scale") == PRESTIGE_SCALE1000
                    for item in country_records),
                "province_requests_readable": all(
                    item.get("record_readable") is True for item in province_records),
                "province_cores_requests_readable": (
                    not province_cores or all(
                        isinstance(item.get("cores"), dict)
                        and item["cores"].get("complete") is True
                        for item in province_records)),
                "reparations_request_readable": (
                    reparations is None or reparations["complete"] is True),
                "trade_power_request_readable": (
                    trade_power is None or trade_power["complete"] is True),
                "annul_treaties_request_readable": (
                    annul_treaties is None
                    or all(item.get("complete") is True
                           for item in annul_treaties)),
                "special_request_readable": (
                    special is None or special.get("complete") is True),
            },
        }
    finally:
        kernel.CloseHandle(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--countries", required=True, nargs="+")
    parser.add_argument("--provinces", nargs="*", default=[])
    parser.add_argument("--province-cores", action="store_true",
                        help="also read each requested province's bounded core list")
    parser.add_argument("--reparations-payer")
    parser.add_argument("--reparations-claimant")
    parser.add_argument("--trade-power-source")
    parser.add_argument("--trade-power-beneficiary")
    parser.add_argument("--annul-country")
    parser.add_argument("--annul-partners", nargs="+")
    parser.add_argument("--subject-pair", action="append", default=[],
                        help="read one source:subject relation; repeat for up to 16 pairs")
    parser.add_argument("--special-action",
                        choices=("humiliate_rival", "show_strength", "force_religion"))
    parser.add_argument("--special-country")
    parser.add_argument("--special-beneficiary")
    parser.add_argument("--expected-date-raw", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        countries = parse_tags(args.countries)
        provinces = parse_province_ids(args.provinces)
        if args.province_cores and not provinces:
            raise ProbeError("--province-cores requires at least one requested province")
        if bool(args.reparations_payer) != bool(args.reparations_claimant):
            raise ProbeError("reparations payer and claimant must be supplied together")
        payer = claimant = None
        if args.reparations_payer:
            payer, claimant = parse_tags([args.reparations_payer, args.reparations_claimant])
        if bool(args.trade_power_source) != bool(args.trade_power_beneficiary):
            raise ProbeError(
                "trade power source and beneficiary must be supplied together")
        source = beneficiary = None
        if args.trade_power_source:
            source, beneficiary = parse_tags(
                [args.trade_power_source, args.trade_power_beneficiary])
        annul_country = None
        annul_partners = None
        if (args.annul_country is None) != (args.annul_partners is None):
            raise ProbeError(
                "annul country and partners must be supplied together")
        if args.annul_country is not None:
            annul_values = parse_tags([args.annul_country] + args.annul_partners)
            annul_country, annul_partners = annul_values[0], annul_values[1:]
            if not 1 <= len(annul_partners) <= 16:
                raise ProbeError("annul partners must contain 1..16 tags")
            if (len(set(annul_partners)) != len(annul_partners)
                    or annul_partners != sorted(annul_partners)
                    or annul_country in annul_partners):
                raise ProbeError("annul partners must be sorted and unique")
            for tag in (annul_country, *annul_partners):
                if tag not in countries:
                    countries.append(tag)
        if (args.special_country is None) != (args.special_beneficiary is None):
            raise ProbeError("special country and beneficiary must be supplied together")
        special_action = args.special_action
        special_country = special_beneficiary = None
        if special_action is not None:
            if args.special_country is None:
                raise ProbeError("special country and beneficiary are required")
            special_values = parse_tags([args.special_country, args.special_beneficiary])
            special_country, special_beneficiary = special_values
            for tag in (special_country, special_beneficiary):
                if tag not in countries:
                    countries.append(tag)
            if special_country == special_beneficiary:
                raise ProbeError("special country and beneficiary must differ")
        subject_pairs = []
        if len(args.subject_pair) > 16:
            raise ProbeError("subject pairs must contain at most 16 pairs")
        for pair in args.subject_pair:
            values = pair.split(":")
            if len(values) != 2:
                raise ProbeError("subject pair must be SOURCE:SUBJECT")
            left, right = parse_tags(values)
            if left == right or (left, right) in subject_pairs:
                raise ProbeError("subject pair must have distinct endpoints and be unique")
            subject_pairs.append((left, right))
            for tag in (left, right):
                if tag not in countries:
                    countries.append(tag)
        subject_options = {"subject_pairs": subject_pairs} if subject_pairs else {}
        runtime = _runtime_probe(args.pid, countries, provinces, args.expected_date_raw,
                                 payer, claimant, source, beneficiary,
                                 annul_country, annul_partners,
                                 special_action, special_country,
                                 special_beneficiary, args.province_cores, **subject_options)
        report: dict[str, object] = {
            "tool": "probe_peace_effect_state.py",
            "version": 1,
            "scope": "bounded read-only country treasury/prestige and province effect state",
            "requested_countries": countries,
            "requested_provinces": provinces,
            "requested_province_cores": args.province_cores,
            "requested_trade_power": {
                "source": source,
                "beneficiary": beneficiary,
            },
            "requested_annul_treaties": {
                "country": annul_country,
                "partners": annul_partners or [],
            },
            "requested_special": {
                "action": special_action,
                "country": special_country,
                "beneficiary": special_beneficiary,
            },
            "runtime": runtime,
            "read_only": True,
            "status": "passed" if all(runtime["checks"].values()) else "failed",
        }
    except Exception as error:
        report = {
            "tool": "probe_peace_effect_state.py",
            "version": 1,
            "scope": "bounded read-only country treasury/prestige and province effect state",
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
