"""Bounded read-only runtime evidence for the native incoming alliance route.

The static route report names the machine fields and branch RVAs for this
exact EU4 build.  This probe only reads those fields from an identity-bound
process.  It never calls a native function, writes memory, publishes a
control request, or assigns a player/AI meaning to the observed values.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy_session import probe_identity
from local_config import game_exe


EXPECTED_HASH = "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77"
DATABASE_POINTER_RVA = 0x233D8B0
GAME_POINTER_RVA = 0x233FE58
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_COUNTRY_SLOTS = 4096
MAX_ROSTER_COUNT = 4096
HASH_BLOCK_BYTES = 1024 * 1024
STATIC_ROUTE_DEFAULT = (
    Path(__file__).parent
    / "runtime/alliance-static-20261013/incoming-authority-route-20261013-r17.json"
)
FOCUS_TAGS = {"FRA": 122, "POR": 189, "SAV": 46, "LIT": None}


class ProbeError(RuntimeError):
    """A failed identity or bounded read-only probe precondition."""


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError:
            try:
                return int(value.strip(), 10)
            except ValueError:
                return None
    return None


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise ProbeError(f"missing JSON: {path}")
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise ProbeError(f"JSON exceeds bound: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"invalid JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(HASH_BLOCK_BYTES)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _hex(value: int | None) -> str | None:
    return hex(value) if isinstance(value, int) else None


def _valid_pointer(value: int | None) -> bool:
    return isinstance(value, int) and 0x10000 <= value < 0x00007FFF00000000


def _tag(handle: int | None) -> str | None:
    if not isinstance(handle, int):
        return None
    raw = (handle & 0xFFFFFF).to_bytes(3, "little")
    if not all(0x20 <= byte <= 0x7E for byte in raw):
        return None
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def _tri_and(values: list[bool | None]) -> bool | None:
    if any(value is False for value in values):
        return False
    if all(value is True for value in values):
        return True
    return None


def _read_static_route(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = _load_json(path)
    if not isinstance(document, dict):
        raise ProbeError("static route report is not an object")
    pe = document.get("pe")
    if not isinstance(pe, Mapping) or str(pe.get("sha256", "")).lower() != EXPECTED_HASH:
        raise ProbeError("static route PE hash does not match the supported game")
    route = document.get("recipient_route")
    if not isinstance(route, Mapping):
        raise ProbeError("static route recipient_route is missing")
    required = {
        "roster_begin_field": "[global+0x1d48]",
        "roster_end_field": "[global+0x1d50]",
        "roster_element": "DWORD[roster_begin + recipient_id*4]",
        "country_table_field": "[country_db+0x118]",
        "recipient_packed_field": "[R8+0x20]",
    }
    for key, expected in required.items():
        if route.get(key) != expected:
            raise ProbeError(f"static route field mismatch: {key}")
    return document, {
        "path": str(path),
        "sha256": _sha256(path),
        "pe_sha256": str(pe.get("sha256")).lower(),
        "rva_start": route.get("decision_interval", {}).get("rva_start")
        if isinstance(route.get("decision_interval"), Mapping) else None,
        "roster_begin_field": required["roster_begin_field"],
        "roster_end_field": required["roster_end_field"],
        "roster_element": required["roster_element"],
        "secondary_callee_rva": "0x2cd5a0",
        "secondary_helper_rva": "0xb52e0",
        "branch_queue_rva": "0x4e8235",
        "branch_continuation_rva": "0x4e8333",
        "branch_clone_response_rva": "0x4e81c5",
    }


def _guard_identity(pid: int, operator_session: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    installation = _load_json(operator_session)
    if not isinstance(installation, Mapping):
        raise ProbeError("operator session is not an object")
    expected_pid = _parse_int(installation.get("pid"))
    expected_creation = _parse_int(installation.get("creation_filetime"))
    if expected_pid != pid or expected_creation is None:
        raise ProbeError("operator session PID/creation mismatch")
    expected_game_hash = str(installation.get("game_sha256", "")).lower()
    expected_dll_hash = str(installation.get("dll_sha256", "")).lower()
    if expected_game_hash != EXPECTED_HASH or not expected_dll_hash:
        raise ProbeError("operator session build hash mismatch")
    identity = probe_identity(pid, game_exe())
    expected_session = installation.get("session_id")
    expected = {
        "pid": pid,
        "creation_filetime": expected_creation,
        "game_sha256": EXPECTED_HASH,
        "session_id": expected_session,
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ProbeError("exact process identity changed")
    modules = identity.get("modules")
    if not isinstance(modules, list) or len(modules) != 1:
        raise ProbeError("observer module identity is not unique")
    if str(modules[0].get("sha256", "")).lower() != expected_dll_hash:
        raise ProbeError("observer module hash changed")
    return dict(installation), identity


class ReadOnlyProcess:
    """A VM_READ-only handle with bounded scalar reads."""

    def __init__(self, pid: int):
        if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8:
            raise ProbeError("WINDOWS_X64_SESSION_REQUIRED")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.kernel.K32EnumProcessModulesEx.argtypes = [
            W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD
        ]
        self.kernel.K32EnumProcessModulesEx.restype = W.BOOL
        self.kernel.ReadProcessMemory.argtypes = [
            W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)
        ]
        self.kernel.ReadProcessMemory.restype = W.BOOL
        self.handle = self.kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        self._closed = False
        modules = (W.HMODULE * 1024)()
        needed = W.DWORD()
        if not self.kernel.K32EnumProcessModulesEx(
            self.handle, modules, C.sizeof(modules), C.byref(needed), 3
        ):
            self.close()
            raise C.WinError(C.get_last_error())
        if not needed.value or needed.value > C.sizeof(modules):
            self.close()
            raise ProbeError("module list invalid")
        self.base = int(modules[0])
        if not _valid_pointer(self.base):
            self.close()
            raise ProbeError("invalid game module base")

    def close(self) -> None:
        if not self._closed:
            self.kernel.CloseHandle(self.handle)
            self._closed = True

    def __enter__(self) -> "ReadOnlyProcess":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def read(self, address: int, size: int) -> bytes:
        if not _valid_pointer(address) or not 0 < size <= 1024 * 1024:
            raise ProbeError("invalid bounded read")
        buffer = C.create_string_buffer(size)
        actual = C.c_size_t()
        if not self.kernel.ReadProcessMemory(
            self.handle, C.c_void_p(address), buffer, size, C.byref(actual)
        ) or actual.value != size:
            raise C.WinError(C.get_last_error())
        return buffer.raw

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little", signed=False)

    def i32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little", signed=True)

    def qword(self, address: int) -> int:
        return int.from_bytes(self.read(address, 8), "little", signed=False)


def _safe(fn: Any) -> tuple[Any, str | None]:
    try:
        return fn(), None
    except (OSError, ProbeError, ValueError) as exc:
        return None, str(exc)


def _country_record(process: ReadOnlyProcess, array: int, slot: int) -> dict[str, Any]:
    record: dict[str, Any] = {"slot": slot, "pointer": None, "handle": None, "tag": None}
    if not 0 <= slot < MAX_COUNTRY_SLOTS:
        record["error"] = "slot_out_of_bounds"
        return record
    pointer, error = _safe(lambda: process.qword(array + slot * 8))
    if error:
        record["error"] = error
        return record
    record["pointer"] = _hex(pointer)
    if not _valid_pointer(pointer):
        record["error"] = "country_pointer_unreadable"
        return record
    handle, error = _safe(lambda: process.qword(pointer + 0x20))
    if error:
        record["error"] = error
        return record
    record["handle"] = _hex(handle)
    record["tag"] = _tag(handle)
    encoded_slot = ((handle or 0) >> 32) & 0xFFFF
    record["handle_slot"] = encoded_slot
    record["canonical_handle_verified"] = encoded_slot == slot
    if encoded_slot == slot:
        same_pointer, same_error = _safe(lambda: process.qword(array + encoded_slot * 8))
        record["canonical_handle_verified"] = (
            same_error is None and same_pointer == pointer
        )
    return record


def _scan_country_db(process: ReadOnlyProcess, array: int) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    records: list[dict[str, Any]] = []
    by_tag: dict[str, list[dict[str, Any]]] = {}
    for slot in range(MAX_COUNTRY_SLOTS):
        record = _country_record(process, array, slot)
        if record.get("pointer") is None and record.get("error"):
            # A read failure beyond the live country table is a bounded stop;
            # null entries remain part of the scan and do not terminate it.
            if record.get("error") != "country_pointer_unreadable":
                break
            continue
        if record.get("tag") is None:
            continue
        records.append(record)
        by_tag.setdefault(str(record["tag"]), []).append(record)
    return records, by_tag


def _state_snapshot(process: ReadOnlyProcess, game: int, base: int, array: int,
                    by_tag: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"read_only": True}
    player_handle, player_error = _safe(lambda: process.qword(game + 0x1E60))
    date_raw, date_error = _safe(lambda: process.i32(game + 0x1DD0))
    speed, speed_error = _safe(lambda: process.i32(game + 0x1E08))
    snapshot.update({
        "date_raw": date_raw,
        "speed_raw": speed,
        "player_handle": _hex(player_handle),
        "player_slot": ((player_handle or 0) >> 32) & 0xFFFF if player_handle is not None else None,
        "player_tag": _tag(player_handle),
    })
    errors = {
        "player_handle": player_error,
        "date_raw": date_error,
        "speed_raw": speed_error,
    }
    server, server_error = _safe(lambda: process.qword(game + 0x1E00))
    snapshot["server"] = _hex(server)
    snapshot["server_error"] = server_error
    paused_flag: int | None = None
    pause_object: int | None = None
    getter_rva: int | None = None
    if server is not None and _valid_pointer(server):
        vtable, vtable_error = _safe(lambda: process.qword(server))
        getter, getter_error = _safe(lambda: process.qword(vtable + 0x100)) if vtable else (None, "missing_server_vtable")
        getter_rva = getter - base if getter is not None else None
        if getter_rva == 0x802500:
            pause_object, pause_error = _safe(lambda: process.qword(server + 0x418))
            if pause_object and _valid_pointer(pause_object):
                paused_flag, paused_error = _safe(lambda: process.u8(pause_object + 0x48))
                errors["paused_flag"] = paused_error
            else:
                errors["pause_object"] = pause_error if pause_object is None else "pause_object_invalid"
        else:
            errors["pause_getter"] = getter_error or "pause_getter_rva_unverified"
        if vtable_error:
            errors["server_vtable"] = vtable_error
    else:
        errors["server"] = server_error or "server_invalid"
    snapshot.update({
        "pause_object": _hex(pause_object),
        "pause_getter_rva": _hex(getter_rva),
        "paused_flag": paused_flag,
        "paused_verified": getter_rva == 0x802500 and paused_flag in (0, 1),
    })
    if player_handle is not None:
        slot = ((player_handle >> 32) & 0xFFFF)
        player_country = next((item for item in by_tag.get(_tag(player_handle) or "", [])
                               if item.get("slot") == slot), None)
        snapshot["player_canonical_handle_verified"] = bool(
            player_country and player_country.get("handle") == _hex(player_handle)
            and player_country.get("canonical_handle_verified") is True
        )
    else:
        snapshot["player_canonical_handle_verified"] = False
    snapshot["errors"] = {key: value for key, value in errors.items() if value}
    return snapshot


def _secondary_route(process: ReadOnlyProcess, game: int, array: int,
                     country: Mapping[str, Any], roster_value: int | None,
                     roster_count: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "country_slot": country.get("slot"),
        "country_tag": country.get("tag"),
        "country_pointer": country.get("pointer"),
        "roster_value": _hex(roster_value),
        "roster_value_semantics": "unknown; static route only proves zero/nonzero branch use",
        "machine_expected_branch": {"rva": None, "status": "unknown", "semantic": "unknown"},
    }
    pointer = _parse_int(country.get("pointer"))
    if pointer is None or not _valid_pointer(pointer):
        result["secondary_predicate"] = None
        result["unknown_reasons"] = ["country_pointer_unreadable"]
        return result
    node, node_error = _safe(lambda: process.qword(pointer + 0x3D0))
    result["country_3d0_pointer"] = _hex(node)
    if node_error:
        result["secondary_predicate"] = None
        result["unknown_reasons"] = ["country_3d0_unreadable"]
        return result
    if not node:
        secondary = False
        result.update({
            "secondary_predicate": secondary,
            "secondary_predicate_source": "2cd5a0 null country+0x3d0 returns AL=0",
        })
    elif not _valid_pointer(node):
        secondary = None
        result["secondary_predicate"] = None
        result["unknown_reasons"] = ["country_3d0_invalid"]
    else:
        flag_raw, flag_error = _safe(lambda: process.u32(node + 0x80))
        packed_handle, handle_error = _safe(lambda: process.qword(node + 0x20))
        flag_byte = (flag_raw & 0xFF) if flag_raw is not None else None
        flag_truth: bool | None
        if flag_raw is None:
            flag_truth = None
        elif flag_raw == 0:
            flag_truth = False
        elif flag_byte:
            flag_truth = True
        else:
            flag_truth = None
        resolved_slot = ((packed_handle or 0) >> 32) & 0xFFFF if packed_handle is not None else None
        resolved_country: dict[str, Any] | None = None
        if resolved_slot is not None and resolved_slot < MAX_COUNTRY_SLOTS:
            resolved_country = _country_record(process, array, resolved_slot)
        resolved_pointer = _parse_int(resolved_country.get("pointer")) if resolved_country else None
        resolved_2458, resolved_2458_error = _safe(
            lambda: process.qword(resolved_pointer + 0x2458)
        ) if resolved_pointer and _valid_pointer(resolved_pointer) else (None, "resolved_country_unreadable")
        resolved_2458_byte, resolved_2458_byte_error = _safe(
            lambda: process.u8(resolved_2458 + 0x18)
        ) if resolved_2458 and _valid_pointer(resolved_2458) else (None, "resolved_2458_unreadable")
        global_74d0, global_error = _safe(lambda: process.u8(game + 0x74D0))
        result.update({
            "node_pointer": _hex(node),
            "node_flag_80_raw_u32": flag_raw,
            "node_flag_80_low_byte": flag_byte,
            "node_handle_20": _hex(packed_handle),
            "resolved_slot": resolved_slot,
            "resolved_handle_tag": _tag(packed_handle),
            "resolved_country": resolved_country,
            "resolved_country_2458_pointer": _hex(resolved_2458),
            "resolved_country_2458_18_byte": resolved_2458_byte,
            "global_74d0_byte": global_74d0,
            "flag_truth_for_static_predicate": flag_truth,
            "resolved_2458_18_truth": (resolved_2458_byte != 0)
            if resolved_2458_byte is not None else None,
            "global_74d0_truth": (global_74d0 != 0) if global_74d0 is not None else None,
            "static_flag_width_note": "raw u32 plus low byte retained; route artifact does not state load width",
        })
        secondary = _tri_and([
            flag_truth,
            (resolved_2458_byte != 0) if resolved_2458_byte is not None else None,
            (global_74d0 != 0) if global_74d0 is not None else None,
        ])
        result["secondary_predicate"] = secondary
        errors = {
            "flag_80": flag_error,
            "node_handle_20": handle_error,
            "resolved_2458": resolved_2458_error,
            "resolved_2458_18": resolved_2458_byte_error,
            "global_74d0": global_error,
        }
        result["unknown_reasons"] = [key for key, value in errors.items() if value]
        if secondary is False and not result["unknown_reasons"]:
            result["secondary_predicate_source"] = "all static b52e0 conditions read; at least one condition false"
        elif secondary is True:
            result["secondary_predicate_source"] = "all static b52e0 conditions read true"
        else:
            result["secondary_predicate_source"] = "one or more static b52e0 conditions remain unknown"
    if roster_count is None or roster_value is None:
        return result
    if roster_count == 0 or roster_value != 0:
        result["machine_expected_branch"] = {
            "rva": "0x4e8235", "status": "derived", "semantic": "unknown",
            "condition": "roster_count == 0 or roster_entry != 0",
        }
    elif result.get("secondary_predicate") is False:
        result["machine_expected_branch"] = {
            "rva": "0x4e8333", "status": "derived", "semantic": "unknown",
            "condition": "roster_entry == 0 and 0x2cd5a0 result == 0",
        }
    elif result.get("secondary_predicate") is True:
        result["machine_expected_branch"] = {
            "rva": "0x4e81c5", "status": "derived", "semantic": "unknown",
            "condition": "roster_entry == 0 and 0x2cd5a0 result != 0",
        }
    else:
        result["machine_expected_branch"]["condition"] = "roster_entry == 0; secondary result unknown"
    return result


def _stable_snapshot(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("date_raw", "player_handle", "player_slot", "player_tag", "paused_flag")
    comparisons = {field: before.get(field) == after.get(field) for field in fields}
    return {"fields": comparisons, "stable": all(comparisons.values())}


def _write_json_exclusive(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _render_markdown(report: Mapping[str, Any]) -> str:
    identity = report.get("identity", {})
    roster = report.get("roster", {})
    state = report.get("runtime_state_guard", {})
    lines = [
        "# r17c incoming alliance route runtime evidence (2026-10-13)",
        "",
        f"session `{identity.get('session_id')}`, PID `{identity.get('pid')}`, "
        f"game SHA `{identity.get('game_sha256')}`; read-only=`true`.",
        "No native callee was invoked, no memory was written, and no control request or submission was made.",
        "",
        "## Identity and state guard",
        "",
        f"Before/after pause, POR and date fields stable: `{state.get('stable')}`; "
        f"POR identity verified: `{state.get('por_identity_verified')}`.",
        f"Before `{state.get('before', {}).get('date_raw')}` / after `{state.get('after', {}).get('date_raw')}` raw date; "
        f"paused `{state.get('before', {}).get('paused_flag')}` → `{state.get('after', {}).get('paused_flag')}`.",
        "",
        "## Runtime roster",
        "",
        f"Roster begin `{roster.get('begin')}`, end `{roster.get('end')}`, count `{roster.get('count')}`; "
        "only nonzero DWORD entries are listed. Their business meaning remains unknown.",
    ]
    entries = roster.get("nonzero_entries", [])
    if entries:
        lines.extend(["", "| slot | value | canonical handle | tag | canonical verification |", "|---:|---:|---|---|---|"])
        for item in entries:
            lines.append(
                f"| {item.get('slot')} | `{item.get('value')}` | `{item.get('canonical_handle')}` | "
                f"`{item.get('tag')}` | `{item.get('canonical_handle_verified')}` |"
            )
    else:
        lines.extend(["", "No nonzero roster entries were readable."])
    lines.extend(["", "## Focus country route fields", ""])
    for tag, item in report.get("focus_countries", {}).items():
        branch = item.get("machine_expected_branch", {})
        lines.append(
            f"- `{tag}` actual slot `{item.get('actual_slot')}`; "
            f"secondary predicate `{item.get('secondary_predicate')}`; "
            f"machine branch `{branch.get('rva')}` ({branch.get('status')}, semantic unknown)."
        )
    lines.extend([
        "",
        "The +0x3d0 → +0x80/+0x20 → resolved-country +0x2458/+0x18 → global +0x74d0 values are retained in JSON.",
        "A derived branch is only the static machine condition; it is not a player/AI classification, authority proof, or business result.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--operator-session", type=Path, required=True)
    parser.add_argument("--static-route", type=Path, default=STATIC_ROUTE_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.pid <= 0:
        raise ProbeError("invalid PID")
    installation, identity = _guard_identity(args.pid, args.operator_session)
    static_document, static_binding = _read_static_route(args.static_route)
    with ReadOnlyProcess(args.pid) as process:
        if process.read(process.base, 2) != b"MZ":
            raise ProbeError("invalid game module base")
        database = process.qword(process.base + DATABASE_POINTER_RVA)
        game = process.qword(process.base + GAME_POINTER_RVA)
        if not _valid_pointer(database) or not _valid_pointer(game):
            raise ProbeError("game world is not initialized")
        array = process.qword(database + 0x118)
        if not _valid_pointer(array):
            raise ProbeError("country array is unreadable")
        country_records, by_tag = _scan_country_db(process, array)
        before = _state_snapshot(process, game, process.base, array, by_tag)

        roster_begin = process.qword(game + 0x1D48)
        roster_end = process.qword(game + 0x1D50)
        empty_roster = roster_begin == 0 and roster_end == 0
        if (not empty_roster and not _valid_pointer(roster_begin)) or roster_end < roster_begin or (roster_end - roster_begin) % 4:
            raise ProbeError("roster range is invalid")
        roster_count = (roster_end - roster_begin) // 4
        if roster_count > MAX_ROSTER_COUNT:
            raise ProbeError("roster exceeds 4096 DWORD bound")
        roster_values: list[int] = []
        nonzero: list[dict[str, Any]] = []
        for slot in range(roster_count):
            value = process.u32(roster_begin + slot * 4)
            roster_values.append(value)
            if value:
                country = _country_record(process, array, slot)
                nonzero.append({
                    "slot": slot,
                    "value": _hex(value),
                    "value_raw_u32": value,
                    "canonical_handle": country.get("handle"),
                    "tag": country.get("tag"),
                    "canonical_handle_verified": country.get("canonical_handle_verified", False),
                    "canonical_country_pointer": country.get("pointer"),
                    "meaning": "unknown DWORD; static evidence proves only zero/nonzero route selection",
                })

        focus: dict[str, dict[str, Any]] = {}
        for tag, expected_slot in FOCUS_TAGS.items():
            candidates = by_tag.get(tag, [])
            exact = next((item for item in candidates if expected_slot is not None and item.get("slot") == expected_slot), None)
            chosen = exact or (candidates[0] if candidates else None)
            record: dict[str, Any] = {
                "requested_tag": tag,
                "expected_slot": expected_slot,
                "actual_slot": chosen.get("slot") if chosen else None,
                "pointer": chosen.get("pointer") if chosen else None,
                "handle": chosen.get("handle") if chosen else None,
                "tag": chosen.get("tag") if chosen else None,
                "slot_matches_expected": (chosen is not None and expected_slot is not None and chosen.get("slot") == expected_slot),
                "canonical_handle_verified": chosen.get("canonical_handle_verified") if chosen else False,
            }
            actual_slot = chosen.get("slot") if chosen else None
            roster_value = roster_values[actual_slot] if actual_slot is not None and actual_slot < len(roster_values) else None
            route = _secondary_route(process, game, array, chosen or record, roster_value, roster_count)
            record.update(route)
            focus[tag] = record
        after = _state_snapshot(process, game, process.base, array, by_tag)

    before_por = before.get("player_tag") == "POR" and before.get("player_slot") == 189
    after_por = after.get("player_tag") == "POR" and after.get("player_slot") == 189
    report: dict[str, Any] = {
        "artifact": "alliance-route-runtime-new-r17c",
        "runtime_this_turn": True,
        "read_only": True,
        "native_methods_invoked": False,
        "memory_written": False,
        "business_submission": False,
        "identity": {
            "pid": identity.get("pid"),
            "creation_filetime": identity.get("creation_filetime"),
            "session_id": identity.get("session_id"),
            "game_sha256": identity.get("game_sha256"),
            "modules": identity.get("modules"),
            "installation": str(args.operator_session),
            "installation_dll_sha256": installation.get("dll_sha256"),
        },
        "static_binding": static_binding,
        "module_base": _hex(process.base),
        "database_pointer": _hex(database),
        "game_pointer": _hex(game),
        "country_array": _hex(array),
        "country_db_tag_scan": {
            "max_slots": MAX_COUNTRY_SLOTS,
            "tagged_records": len(country_records),
            "focus_tags": list(FOCUS_TAGS),
            "meaning": "canonical handle/tag lookup only; no AI/player semantic assignment",
        },
        "runtime_state_guard": {
            "before": before,
            "after": after,
            "stable": _stable_snapshot(before, after)["stable"],
            "comparisons": _stable_snapshot(before, after)["fields"],
            "por_identity_verified": before_por and after_por,
            "pause_getter_rva_expected": "0x802500",
        },
        "roster": {
            "global_pointer": _hex(game),
            "begin": _hex(roster_begin),
            "end": _hex(roster_end),
            "count": roster_count,
            "bounded_count_verified": roster_count <= MAX_ROSTER_COUNT,
            "nonzero_entries": nonzero,
            "all_values_zero": not nonzero,
            "entry_meaning": "unknown; only machine zero/nonzero use is statically bound",
        },
        "focus_countries": focus,
        "unknowns": [
            "roster DWORD business meaning and ownership semantics",
            "0x2cd5a0/0xb52e0 semantic name and player/AI interpretation",
            "whether any derived branch implies authority, acceptance, or submission",
        ],
    }
    _write_json_exclusive(args.output, report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        stream.write(_render_markdown(report))
    print(json.dumps({
        "output": str(args.output),
        "report": str(args.report),
        "read_only": True,
        "roster_count": roster_count,
        "nonzero_entries": len(nonzero),
        "por_identity_verified": report["runtime_state_guard"]["por_identity_verified"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ProbeError, RuntimeError) as exc:
        print(f"Alliance route probe: {exc}", file=sys.stderr)
        raise SystemExit(2)
