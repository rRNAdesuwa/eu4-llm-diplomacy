"""Operator-only Windows session identity and read-only health checks.

No native function calls, injection, process termination, or memory writes.
Do not expose the operator binding or diagnostics to an LLM.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import hashlib
from pathlib import Path
import sys

EXPECTED_GAME_HASH = "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_identity(pid: int, expected_exe: Path) -> dict:
    if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8 or pid <= 0:
        raise RuntimeError("WINDOWS_X64_SESSION_REQUIRED")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    kernel.GetProcessTimes.restype = W.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
    kernel.K32EnumProcessModulesEx.restype = W.BOOL
    kernel.K32GetModuleFileNameExW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
    kernel.K32GetModuleFileNameExW.restype = W.DWORD
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        name = C.create_unicode_buffer(32768)
        size = W.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, C.byref(size)):
            raise C.WinError(C.get_last_error())
        exe = Path(name.value)
        if exe.resolve() != expected_exe.resolve():
            raise RuntimeError("PROCESS_IMAGE_MISMATCH")
        sha = file_hash(exe)
        if sha != EXPECTED_GAME_HASH:
            raise RuntimeError("UNSUPPORTED_GAME_BUILD")
        created, exited, system, user = (W.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, C.byref(created), C.byref(exited), C.byref(system), C.byref(user)):
            raise C.WinError(C.get_last_error())
        creation = (created.dwHighDateTime << 32) | created.dwLowDateTime
        modules = (W.HMODULE * 1024)()
        needed = W.DWORD()
        if not kernel.K32EnumProcessModulesEx(handle, modules, C.sizeof(modules), C.byref(needed), 3):
            raise C.WinError(C.get_last_error())
        if needed.value > C.sizeof(modules) or not needed.value:
            raise RuntimeError("MODULE_LIST_INVALID")
        bridges = []
        for module in modules[:needed.value // C.sizeof(W.HMODULE)]:
            if not kernel.K32GetModuleFileNameExW(handle, module, name, len(name)):
                raise C.WinError(C.get_last_error())
            path = Path(name.value)
            if path.name.lower().startswith("eu4_bridge"):
                bridges.append({"name": path.name, "path": str(path), "sha256": file_hash(path)})
        return {"pid": pid, "creation_filetime": creation, "game_sha256": sha,
                "session_id": f"{pid}-{creation:x}", "modules": bridges}
    finally:
        kernel.CloseHandle(handle)
