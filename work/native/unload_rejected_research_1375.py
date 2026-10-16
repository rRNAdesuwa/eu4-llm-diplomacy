"""One audited failed-install cleanup, NOT a general hot-unload facility.

Only PID 39708, the recorded v3 module base/hash, and its three pre-patch
stage-36 refusals are accepted. No installed hook may be removed by this tool.
The normal injector continues to forbid replacing a loaded bridge.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import inject_probe as loader
from bridge.native_build import LOCAL_SHA256

PID = 39708
MODULE_BASE = 0x7FFF49BD0000
DLL_SHA = "8C4F4198309F5330C1A2D327576A8661B2A15C08C7D3E3507D4BEFD39278A3E1"
DIRECTORY = ROOT / "work/runtime/native1375-v3"
DLL = DIRECTORY / "eu4_pair_lifecycle_1375.dll"
LOG = DIRECTORY / "research-1375.jsonl"
REPORT = DIRECTORY / "unload-audited-refusal-39708.json"
FRAME_RVA = 0x10A6EC0
PREFIX = bytes.fromhex("4c89442418555357488d6c24b04881ec50010000")


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def check_evidence():
    require(not REPORT.exists(), "Cleanup report already exists; do not automatically retry")
    require(hashlib.sha256(DLL.read_bytes()).hexdigest().upper() == DLL_SHA, "Audited DLL hash differs")
    require(LOG.stat().st_size <= 65536, "Unexpected log size")
    rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()]
    require(len(rows) == 3, "Expected only the three audited installation refusals")
    for attempt, row in enumerate(rows, 1):
        required = {"event": "research_hook_refused", "pid": PID, "result": 21,
                    "attempt": attempt, "max_attempts": 3, "retrying": attempt < 3,
                    "prefix_unchanged": True, "stage": 36, "error": 5, "thread": 11932,
                    "collected": 150, "suspended": 60, "resume_failures": 0,
                    "resume_error": 0, "resume_thread": 0, "rip": "0x0", "submitted": False}
        require(row == required, "Refusal evidence differs from the reviewed failed-install case")
    for name in ("pair-selftest.request", "pair-preview.request"):
        require(not (DIRECTORY / name).exists(), "An experiment marker exists")


def read_bytes(kernel, process, address, size):
    buffer = C.create_string_buffer(size)
    actual = C.c_size_t()
    require(kernel.ReadProcessMemory(process, C.c_void_p(address), buffer, size, C.byref(actual))
            and actual.value == size, "Cannot verify remote frame bytes")
    return buffer.raw


def system_free_library(kernel, modules):
    local = kernel.GetModuleHandleW("kernel32.dll")
    address = loader._ptr(kernel.GetProcAddress(local, b"FreeLibrary"))
    require(address != 0, "FreeLibrary unavailable")
    owner = W.HMODULE()
    require(kernel.GetModuleHandleExW(loader.GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
                                     | loader.GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                     C.c_void_p(address), C.byref(owner)), "Cannot identify system export owner")
    path = C.create_unicode_buffer(32768)
    require(kernel.GetModuleFileNameW(owner, path, len(path)), "Cannot identify system DLL path")
    matches = loader._find_module(modules, path.value)
    require(len(matches) == 1, "Cannot match the system export owner in target")
    return matches[0].handle + address - loader._ptr(owner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unload", action="store_true", help="perform this one audited cleanup after preflight")
    args = parser.parse_args()
    process = None
    kernel = None
    report = {"pid": PID, "dll_sha256": DLL_SHA, "module_base": hex(MODULE_BASE),
              "scope": "one_audited_pre_patch_refusal", "unloaded": False,
              "gameplay_calls": False, "output_handle_leak_until_process_exit": True}
    try:
        loader._require_windows_x64()
        loader._verify_game_build(LOCAL_SHA256)
        check_evidence()
        kernel = loader._configure_kernel32()
        kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        kernel.ReadProcessMemory.restype = W.BOOL
        access = loader.PROCESS_ACCESS if args.unload else loader.PROCESS_QUERY_INFORMATION | loader.PROCESS_VM_READ
        process = kernel.OpenProcess(access, False, PID)
        require(process, "Audited process is unavailable")
        require(loader._canonical(loader._query_process_path(kernel, process)) == loader._canonical(loader.GAME),
                "PID no longer identifies the audited game")
        modules = loader._enum_modules(kernel, process)
        matches = loader._find_module(modules, DLL)
        require(len(matches) == 1 and matches[0].handle == MODULE_BASE, "Audited module path/base not present")
        bridges = [m for m in modules if Path(m.path).name.casefold().startswith(("eu4_bridge_", "eu4_pair_lifecycle_"))]
        require(len(bridges) == 1, "Another bridge is loaded")
        games = loader._find_module(modules, loader.GAME)
        require(len(games) == 1, "Game module identity is ambiguous")
        frame = games[0].handle + FRAME_RVA
        require(read_bytes(kernel, process, frame, len(PREFIX)) == PREFIX, "Frame code is patched; never unload")
        report["preflight_passed"] = True
        if args.unload:
            entry = system_free_library(kernel, modules)
            require(read_bytes(kernel, process, frame, len(PREFIX)) == PREFIX, "Frame changed before cleanup")
            report["state"] = "unload_started_no_retry"
            REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            thread = loader._remote_thread(kernel, process, entry, MODULE_BASE)
            try:
                report["free_library_return"] = loader._wait_thread(kernel, thread, 10000, "audited rejected-module FreeLibrary")
            finally:
                kernel.CloseHandle(thread)
            require(report["free_library_return"] == 1, "FreeLibrary did not return expected TRUE; do not retry")
            require(not loader._find_module(loader._enum_modules(kernel, process), DLL), "Module remains loaded; do not retry")
            require(read_bytes(kernel, process, frame, len(PREFIX)) == PREFIX, "Unexpected frame bytes after cleanup")
            report.update(unloaded=True, state="unloaded_verified")
            REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({**report, "error": str(error)}), file=sys.stderr)
        return 2
    finally:
        if kernel and process:
            kernel.CloseHandle(process)


if __name__ == "__main__":
    raise SystemExit(main())
