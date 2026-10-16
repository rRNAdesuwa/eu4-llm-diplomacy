"""Bounded read-only EU4 1.37.5 diplomacy structure probe, live or minidump.

No engine calls, process writes, DLL loading, script submission or UI control.
Raw state is diagnostic evidence, not a validated diplomacy execution backend.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import json
import mmap
from pathlib import Path, PureWindowsPath
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.native_build import LOCAL_SHA256, inspect_build
from work.local_config import game_exe

DATABASE_POINTER_RVA = 0x233D8D0
GAME_POINTER_RVA = 0x233FE78
MAX_SLOTS = 4096
MAX_DIPLOMATS = 256
MAX_READ = 1024 * 1024
MAX_TOTAL_READ = 16 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


class MissingMemory(ProbeError):
    pass


def pointer(value: int) -> int:
    if value < 0x10000 or value >= 0x0000800000000000 or value % 8:
        raise ProbeError(f"Invalid x64 object pointer: {value:#x}")
    return value


class MemoryReader:
    bytes_read = 0

    def _check_read(self, address: int, size: int) -> None:
        if address < 0x10000 or not 0 < size <= MAX_READ or address + size > 0x0000800000000000:
            raise ProbeError("Read outside bounded user memory")
        self.bytes_read += size
        if self.bytes_read > MAX_TOTAL_READ:
            raise ProbeError("Probe read budget exceeded")

    def qword(self, address: int) -> int:
        return int.from_bytes(self.read(address, 8), "little")

    def integer(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little", signed=True)


class DumpReader(MemoryReader):
    def __init__(self, path: Path):
        self.file = Path(path).open("rb")
        self.mapping = None
        self.bytes_read = 0
        try:
            self.mapping = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
            if self.blob(0, 4) != b"MDMP":
                raise ProbeError("Not a Microsoft minidump")
            count, directory = self.unpack("<II", 8)
            if count > 4096:
                raise ProbeError("Too many minidump streams")
            self.streams = {}
            for index in range(count):
                kind, size, offset = self.unpack("<III", directory + index * 12)
                self.check_file_range(offset, size)
                if kind == 0 and size == 0:
                    continue  # UnusedStream directory padding is allowed to repeat.
                if kind in self.streams:
                    raise ProbeError("Duplicate minidump stream")
                self.streams[kind] = (offset, size)
            if 4 not in self.streams:
                raise ProbeError("Minidump has no module list")
            start, size = self.streams[4]
            module_count = self.unpack("<I", start)[0]
            if module_count > 1024 or 4 + module_count * 108 > size:
                raise ProbeError("Invalid or oversized module list")
            self.modules = []
            for index in range(module_count):
                offset = start + 4 + index * 108
                base, image_size, checksum, timestamp, name_offset = self.unpack("<QIIII", offset)
                name_size = self.unpack("<I", name_offset)[0]
                if name_size > 32768 or name_size % 2:
                    raise ProbeError("Invalid minidump module name")
                name = self.blob(name_offset + 4, name_size).decode("utf-16le")
                self.modules.append({"base": base, "size": image_size, "timestamp": timestamp,
                                     "checksum": checksum, "name": name})
            self.regions = []
            for kind in (5, 9, 3):
                if kind not in self.streams:
                    continue
                start, stream_size = self.streams[kind]
                entry_count = self.unpack("<Q" if kind == 9 else "<I", start)[0]
                header_size, entry_size = (16, 16) if kind == 9 else (4, 48 if kind == 3 else 16)
                if entry_count > 65536 or header_size + entry_count * entry_size > stream_size:
                    raise ProbeError("Invalid or oversized memory descriptors")
                file_offset = self.unpack("<Q", start + 8)[0] if kind == 9 else None
                for index in range(entry_count):
                    offset = start + header_size + index * entry_size
                    if kind == 9:
                        address, length = self.unpack("<QQ", offset)
                        region_offset = file_offset
                        file_offset += length
                    else:
                        address, length, region_offset = self.unpack("<QII", offset + (24 if kind == 3 else 0))
                    self.check_file_range(region_offset, length)
                    if length:
                        self.regions.append((address, length, region_offset))
            if not self.regions:
                raise ProbeError("Minidump contains no captured memory")
            self.regions.sort()
        except Exception:
            self.close()
            raise

    def check_file_range(self, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.mapping):
            raise ProbeError("Minidump descriptor extends beyond file")

    def blob(self, offset: int, size: int) -> bytes:
        self.check_file_range(offset, size)
        return self.mapping[offset:offset + size]

    def unpack(self, format: str, offset: int) -> tuple:
        return struct.unpack(format, self.blob(offset, struct.calcsize(format)))

    def read(self, address: int, size: int) -> bytes:
        self._check_read(address, size)
        output = bytearray()
        cursor = address
        while cursor < address + size:
            containing = [(base, length, offset) for base, length, offset in self.regions if base <= cursor < base + length]
            if not containing:
                raise MissingMemory(f"Address {cursor:#x} was not captured in this minidump")
            base, length, offset = max(containing, key=lambda region: region[0] + region[1])
            take = min(address + size - cursor, base + length - cursor)
            output.extend(self.blob(offset + cursor - base, take))
            cursor += take
        return bytes(output)

    def fault(self) -> dict | None:
        if 6 not in self.streams:
            return None
        start, size = self.streams[6]
        if size < 168:
            raise ProbeError("Truncated exception stream")
        thread = self.unpack("<I", start)[0]
        code = self.unpack("<I", start + 8)[0]
        address = self.unpack("<Q", start + 24)[0]
        matches = [module for module in self.modules if module["base"] <= address < module["base"] + module["size"]]
        module = matches[0] if len(matches) == 1 else None
        count = self.unpack("<I", start + 32)[0]
        if count > 15:
            raise ProbeError("Invalid exception parameter count")
        return {"thread_id": thread, "exception_code": hex(code), "exception_address": hex(address),
                "module": module["name"] if module else None,
                "module_relative_offset": hex(address - module["base"]) if module else None,
                "exception_parameters": [hex(self.unpack("<Q", start + 40 + i * 8)[0]) for i in range(count)],
                "interpretation": "Module ownership of the faulting instruction only; root cause and call chain are not established."}

    def close(self) -> None:
        if self.mapping is not None:
            self.mapping.close()
        self.file.close()


def pe_signature(reader, base: int = 0) -> dict:
    """Read only bounded DOS/PE32+ headers from a file or process image."""
    def read(offset, size):
        if hasattr(reader, "seek"):
            reader.seek(offset)
            result = reader.read(size)
        else:
            result = reader.read(base + offset, size)
        if len(result) != size:
            raise ProbeError("Truncated PE header")
        return result
    dos = read(0, 64)
    if dos[:2] != b"MZ":
        raise ProbeError("Missing DOS signature")
    offset = struct.unpack_from("<I", dos, 60)[0]
    if not 64 <= offset <= 1024 * 1024:
        raise ProbeError("Unbounded PE header offset")
    header = read(offset, 24)
    if header[:4] != b"PE\0\0" or struct.unpack_from("<H", header, 4)[0] != 0x8664:
        raise ProbeError("Not an x64 PE image")
    optional_size = struct.unpack_from("<H", header, 20)[0]
    if not 112 <= optional_size <= 4096:
        raise ProbeError("Invalid PE optional header size")
    optional = read(offset + 24, optional_size)
    if optional[:2] != b"\x0b\x02":
        raise ProbeError("Not PE32+")
    return {"timestamp": struct.unpack_from("<I", header, 8)[0],
            "size": struct.unpack_from("<I", optional, 56)[0]}


def verified_executable(executable: Path) -> tuple[dict, dict]:
    build = inspect_build(executable)
    if build.get("sha256") != LOCAL_SHA256:
        raise ProbeError("Unsupported executable SHA-256; only the audited EU4 1.37.5 image is accepted")
    with Path(executable).open("rb") as stream:
        signature = pe_signature(stream)
    return build, signature


def verify_module_signature(module: dict, signature: dict) -> None:
    if module["timestamp"] != signature["timestamp"] or module["size"] != signature["size"]:
        raise ProbeError("Loaded/dumped module timestamp or SizeOfImage differs from the verified executable")


class ProcessReader(MemoryReader):
    def __init__(self, pid: int, executable: Path, signature: dict):
        if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8 or pid <= 0:
            raise ProbeError("Live inspection requires a valid PID and 64-bit Windows Python")
        self.bytes_read = 0
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = W.BOOL
        self.kernel.K32EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
        self.kernel.K32EnumProcessModulesEx.restype = W.BOOL
        self.kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        self.kernel.ReadProcessMemory.restype = W.BOOL
        self.handle = self.kernel.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY_INFORMATION | VM_READ only
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            path = C.create_unicode_buffer(32768)
            length = W.DWORD(len(path))
            if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, path, C.byref(length)):
                raise C.WinError(C.get_last_error())
            if Path(path.value).resolve() != executable.resolve():
                raise ProbeError("PID executable path differs from the verified executable")
            modules = (W.HMODULE * 1024)()
            needed = W.DWORD()
            if not self.kernel.K32EnumProcessModulesEx(self.handle, modules, C.sizeof(modules), C.byref(needed), 3):
                raise C.WinError(C.get_last_error())
            if not needed.value or needed.value > C.sizeof(modules) or needed.value % C.sizeof(W.HMODULE):
                raise ProbeError("Invalid or oversized live module list")
            self.base = pointer(modules[0])
            verify_module_signature(pe_signature(self, self.base), signature)
            # Rehash the queried process path, not merely a caller-supplied filename.
            verified_executable(Path(path.value))
        except Exception:
            self.close()
            raise

    def read(self, address: int, size: int) -> bytes:
        self._check_read(address, size)
        buffer = C.create_string_buffer(size)
        actual = C.c_size_t()
        if not self.kernel.ReadProcessMemory(self.handle, address, buffer, size, C.byref(actual)) or actual.value != size:
            raise MissingMemory(f"Could not read {size} bytes at {address:#x}; Win32 error {C.get_last_error()}")
        return buffer.raw

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def country_identity(reader: MemoryReader, array: int, slot: int, expected_handle: int | None = None) -> dict | None:
    if not 0 <= slot < MAX_SLOTS:
        raise ProbeError("Country slot exceeds the fixed 4096 limit")
    address = reader.qword(array + slot * 8)
    if not address:
        return None
    pointer(address)
    handle = reader.qword(address + 0x20)
    if (handle >> 32) & 0xffff != slot or expected_handle is not None and handle != expected_handle:
        raise ProbeError("Country handle does not match its slot or expected full identity")
    tag = (handle & 0xffffff).to_bytes(3, "little").decode("ascii", errors="replace")
    if not re.fullmatch(r"[A-Z0-9]{3}", tag):
        raise ProbeError("Country handle contains no valid three-character tag")
    return {"slot": slot, "tag": tag, "address": hex(address), "handle": hex(handle), "identity_valid": True}


def diplomat_state(reader: MemoryReader, country: dict) -> dict:
    holder = pointer(reader.qword(int(country["address"], 16) + 0x1480))
    manager = pointer(reader.qword(holder + 0x18))
    begin, end = reader.qword(manager + 0x20), reader.qword(manager + 0x28)
    if begin == end == 0:
        count = 0
    else:
        pointer(begin)
        if end < begin or (end - begin) % 8 or (end - begin) // 8 > MAX_DIPLOMATS:
            raise ProbeError("Diplomat vector invalid or exceeds 256 entries")
        count = (end - begin) // 8
    entries = []
    for index in range(count):
        address = pointer(reader.qword(begin + index * 8))
        state = reader.read(address + 0x18, 1)[0]
        entries.append({"index": index, "address": hex(address), "state_raw_18": state,
                        "state_zero_available_candidate": state == 0})
    return {"manager": hex(manager), "vector_begin": hex(begin), "vector_end": hex(end),
            "entry_count": count, "entries": entries, "state_zero_count": sum(item["state_raw_18"] == 0 for item in entries),
            "interpretation": "State byte zero is the statically identified availability branch; no send legality or live outcome is established."}


def inspect_state(reader: MemoryReader, base: int, *, slots: int = 256, actor: str = "FRA", target: str = "ENG") -> dict:
    if not 1 <= slots <= MAX_SLOTS:
        raise ProbeError("Slot scan must be between 1 and 4096")
    database = pointer(reader.qword(base + DATABASE_POINTER_RVA))
    game = pointer(reader.qword(base + GAME_POINTER_RVA))
    array = pointer(reader.qword(database + 0x118))
    date = reader.integer(game + 0x1DD0)
    player_handle = reader.qword(game + 0x1E60)
    player_slot = (player_handle >> 32) & 0xffff
    player = country_identity(reader, array, player_slot, player_handle)
    if player is None:
        raise ProbeError("Player country object is missing")
    countries, skipped = [], []
    for slot in range(slots):
        try:
            country = country_identity(reader, array, slot)
            if country:
                countries.append(country)
        except ProbeError as exc:
            skipped.append({"slot": slot, "reason": str(exc)})
    if not countries:
        raise ProbeError("No consistent country identities in bounded slot scan")
    report = {"status": "bounded_snapshot", "database_pointer": hex(database), "game_pointer": hex(game), "country_array": hex(array),
              "current_raw_date": date, "player": player, "countries": countries,
              "country_identities_verified": True,
              "slot_scan_limit": slots, "skipped_slots": skipped, "actor": actor, "target": target,
              "game_legality_checked": False, "execution_supported": False,
              "interpretation": "Partial diagnostic snapshot; no country existence, gameplay legality, cost, duration or AI acceptance is inferred."}
    actor_country = next((country for country in countries if country["tag"] == actor), None)
    target_country = next((country for country in countries if country["tag"] == target), None)
    if actor_country:
        try:
            country_identity(reader, array, actor_country["slot"], int(actor_country["handle"], 16))
            report["actor_diplomats"] = diplomat_state(reader, actor_country)
        except ProbeError as exc:
            report["actor_diplomats"] = {"status": "unavailable", "reason": str(exc)}
    else:
        report["actor_diplomats"] = {"status": "unavailable", "reason": "Actor not found in bounded slot scan"}
    if actor_country and target_country:
        try:
            country_identity(reader, array, actor_country["slot"], int(actor_country["handle"], 16))
            country_identity(reader, array, target_country["slot"], int(target_country["handle"], 16))
            relation_array = pointer(reader.qword(int(actor_country["address"], 16) + 0x1510))
            address = relation_array + target_country["slot"] * 0x48 + 0x30
            threshold = reader.integer(address)
            report["relation_cooldown"] = {"address": hex(address), "threshold_raw": threshold,
                                           "current_raw_date": date, "strict_date_comparison": date > threshold,
                                           "interpretation": "Only the raw current-date > threshold comparison; other guards and any bypass are not inspected."}
        except ProbeError as exc:
            report["relation_cooldown"] = {"status": "unavailable", "reason": str(exc)}
    else:
        report["relation_cooldown"] = {"status": "unavailable", "reason": "Actor or target not found in bounded slot scan"}
    # A live campaign can change while read; do not label the result an atomic snapshot.
    try:
        same_globals = reader.qword(base + DATABASE_POINTER_RVA) == database and reader.qword(base + GAME_POINTER_RVA) == game
        same_player = reader.qword(game + 0x1E60) == player_handle
        same_date = reader.integer(game + 0x1DD0) == date
        report["snapshot_consistency"] = {"globals_unchanged": same_globals, "player_unchanged": same_player,
                                          "date_unchanged": same_date, "atomic": False}
    except ProbeError as exc:
        report["snapshot_consistency"] = {"status": "unavailable", "reason": str(exc), "atomic": False}
    report["memory_bytes_requested"] = reader.bytes_read
    return report


def partial_dump_state(reader: MemoryReader, base: int, error: MissingMemory) -> dict:
    """Keep absent dump pages distinct from observed zero/null game fields."""
    report = {"status": "partial_capture", "reason": str(error), "countries": [],
              "country_identities_verified": False, "game_legality_checked": False, "execution_supported": False,
              "fields": {}, "interpretation": "Required heap pages are absent from this minidump; no country/diplomat/cooldown conclusions are available."}
    values = {}
    for label, address in (
        ("database_pointer", base + DATABASE_POINTER_RVA),
        ("game_pointer", base + GAME_POINTER_RVA),
    ):
        try:
            value = reader.qword(address)
            values[label] = pointer(value)
            report["fields"][label] = {"status": "captured", "value": hex(value)}
        except ProbeError as exc:
            report["fields"][label] = {"status": "unavailable", "reason": str(exc)}
    derived = []
    if "database_pointer" in values:
        derived.append(("country_array", values["database_pointer"] + 0x118, 8))
    if "game_pointer" in values:
        derived.extend((("current_raw_date", values["game_pointer"] + 0x1DD0, 4),
                        ("player_handle_raw", values["game_pointer"] + 0x1E60, 8)))
    for label, address, width in derived:
        try:
            value = reader.integer(address) if width == 4 else reader.qword(address)
            report["fields"][label] = {"status": "captured", "value": value if width == 4 else hex(value)}
        except ProbeError as exc:
            report["fields"][label] = {"status": "unavailable", "reason": str(exc)}
    report["memory_bytes_requested"] = reader.bytes_read
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pid", type=int)
    source.add_argument("--dump", type=Path)
    parser.add_argument("--exe", type=Path, help="Defaults to EU4_GAME_ROOT/eu4.exe from local.env")
    parser.add_argument("--slots", type=int, default=256, help="Bounded prefix of country slots, 1..4096; default 256")
    parser.add_argument("--actor", default="FRA")
    parser.add_argument("--target", default="ENG")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reader = None
    try:
        if not all(re.fullmatch(r"[A-Z0-9]{3}", tag) for tag in (args.actor, args.target)):
            raise ProbeError("Actor and target must be three-character uppercase country tags")
        executable = args.exe or game_exe()
        build, signature = verified_executable(executable)
        if args.dump:
            reader = DumpReader(args.dump)
            candidates = [module for module in reader.modules if PureWindowsPath(module["name"]).name.lower() == "eu4.exe"]
            if len(candidates) != 1:
                raise ProbeError("Minidump must contain exactly one eu4.exe module")
            module = candidates[0]
            verify_module_signature(module, signature)
            base = pointer(module["base"])
            source_report = {"kind": "minidump", "path": str(args.dump.resolve()), "fault": reader.fault(),
                             "module_identity": {"name": module["name"], "base": hex(base), "timestamp": module["timestamp"],
                                                 "size_of_image": module["size"], "signature_matches_local_exe": True,
                                                 "dump_image_sha256_available": False},
                             "note": "Dump timestamp/SizeOfImage match the locally hashed build; the complete loaded image is not captured for hashing."}
        else:
            reader = ProcessReader(args.pid, executable, signature)
            base = reader.base
            source_report = {"kind": "live_process", "pid": args.pid, "module_base": hex(base),
                             "access": ["PROCESS_QUERY_INFORMATION", "PROCESS_VM_READ"], "atomic_snapshot": False}
        try:
            state = inspect_state(reader, base, slots=args.slots, actor=args.actor, target=args.target)
        except MissingMemory as exc:
            if not args.dump:
                raise
            state = partial_dump_state(reader, base, exc)
        report = {"schema_version": 1, "read_only": True, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                  "build": build, "source": source_report,
                  "read_budget": {"per_read_max_bytes": MAX_READ, "total_max_bytes": MAX_TOTAL_READ,
                                  "country_slot_max": MAX_SLOTS, "diplomat_entry_max": MAX_DIPLOMATS,
                                  "counter_definition": "Sum of explicit memory-read sizes, including repeated or failed reads; not unique bytes, process RSS, or total OS-internal reads."},
                  "offset_profile": {"database_pointer_rva": hex(DATABASE_POINTER_RVA), "game_pointer_rva": hex(GAME_POINTER_RVA)},
                  "state": state}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "read_only": True, "source": source_report["kind"],
                          "consistent_countries": len(report["state"]["countries"]),
                          "player": report["state"].get("player", {}).get("tag"),
                          "state_status": state.get("status", "bounded_snapshot"), "fault": source_report.get("fault")}))
        return 0
    except (OSError, ValueError, ProbeError, struct.error) as exc:
        print(json.dumps({"error": str(exc), "read_only": True}), file=sys.stderr)
        return 2
    finally:
        if reader:
            reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
