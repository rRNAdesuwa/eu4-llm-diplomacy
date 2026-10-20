"""Explicit, bounded Windows x64 loader for the EU4 bridge DLL.

Safety boundary for development builds:

* Nothing runs on import.  The process is selected only by the required
  ``--pid`` argument; there is no process discovery or automatic injection.
* ``--ack-test-save`` is mandatory.  The operator must save a disposable test
  game before this script can request a remote thread.
* The local executable and the target process must both be the exact EU4
  1.37.4 build recorded by ``work/probe_native_state.py``.
* The DLL must be an absolute, existing PE32+ x64 file exporting
  ``BridgeStart``.  An already loaded copy is rejected instead of being
  loaded a second time.
* The only remote writes are the temporary UTF-16 DLL path and the normal
  ``LoadLibraryW``/``BridgeStart`` remote-thread calls.  No game data is
  read or modified by this loader, and it never calls ``FreeLibrary`` on the
  injected DLL.

This is a manual development probe, not a service or a production injector.
Run it only after the game and a disposable test save are ready.  A timeout
is conservative: memory used by a still-running remote loader is retained,
and the script never frees it while the remote thread may still reference it.
"""

from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Iterable


# Reuse the build identity instead of copying it.  The import is deliberately
# resolved relative to this script so invoking the loader from another cwd
# cannot silently select another probe module.
_WORK_DIR = Path(__file__).resolve().parents[1]
if str(_WORK_DIR) not in sys.path:
    sys.path.insert(0, str(_WORK_DIR))
try:
    from probe_native_state import EXPECTED_HASH, GAME  # type: ignore
except (ImportError, AttributeError) as error:  # pragma: no cover - setup error
    raise RuntimeError(
        "Cannot load work/probe_native_state.py; the build identity is unavailable"
    ) from error


BRIDGE_EXPORT = b"BridgeStart"
LOAD_LIBRARY_EX_DONT_RESOLVE_DLL_REFERENCES = 0x00000001
GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT = 0x00000002
GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS = 0x00000004
LIST_MODULES_ALL = 0x03

PROCESS_CREATE_THREAD = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
SYNCHRONIZE = 0x00100000
PROCESS_ACCESS = (
    PROCESS_CREATE_THREAD
    | PROCESS_VM_OPERATION
    | PROCESS_VM_READ
    | PROCESS_VM_WRITE
    | PROCESS_QUERY_INFORMATION
    | SYNCHRONIZE
)

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF


def _ptr(value: object) -> int:
    """Return a pointer-like ctypes value as an integer."""

    if value is None:
        return 0
    nested = getattr(value, "value", value)
    return int(nested or 0)


def _canonical(path: str | Path) -> str:
    """Canonical comparison spelling for local and remote Windows paths."""

    # ``realpath`` is useful for the local DLL and harmless for a remote path;
    # normcase/casefold handles GetModuleFileNameExW's case differences.
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path)))).casefold()


def _win_error(prefix: str) -> RuntimeError:
    error = C.get_last_error()
    if error:
        return RuntimeError(f"{prefix}: {C.WinError(error)}")
    return RuntimeError(prefix)


def _require_windows_x64() -> None:
    if sys.platform != "win32" or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("inject_probe.py requires a 64-bit Windows Python")


def _positive_pid(value: str) -> int:
    try:
        pid = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("PID must be an integer") from error
    if pid <= 0:
        raise argparse.ArgumentTypeError("PID must be positive")
    return pid


def _bounded_timeout(value: str) -> int:
    try:
        timeout = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be an integer in milliseconds") from error
    if not 100 <= timeout <= 60_000:
        raise argparse.ArgumentTypeError("timeout must be between 100 and 60000 milliseconds")
    return timeout


@dataclass(frozen=True)
class RemoteModule:
    handle: int
    path: str


@dataclass(frozen=True)
class LocalExport:
    mapped_base: int
    export_address: int
    export_rva: int
    image_size: int


@dataclass(frozen=True)
class SystemFunction:
    address: int
    owner_base: int
    owner_path: str
    rva: int


def _configure_kernel32() -> C.WinDLL:
    kernel = C.WinDLL("kernel32", use_last_error=True)

    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [
        W.HANDLE,
        W.DWORD,
        W.LPWSTR,
        C.POINTER(W.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [
        W.HANDLE,
        C.POINTER(W.HMODULE),
        W.DWORD,
        C.POINTER(W.DWORD),
        W.DWORD,
    ]
    kernel.K32EnumProcessModulesEx.restype = W.BOOL
    kernel.K32GetModuleFileNameExW.argtypes = [
        W.HANDLE,
        W.HMODULE,
        W.LPWSTR,
        W.DWORD,
    ]
    kernel.K32GetModuleFileNameExW.restype = W.DWORD
    kernel.VirtualAllocEx.argtypes = [
        W.HANDLE,
        C.c_void_p,
        C.c_size_t,
        W.DWORD,
        W.DWORD,
    ]
    kernel.VirtualAllocEx.restype = C.c_void_p
    kernel.VirtualFreeEx.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD]
    kernel.VirtualFreeEx.restype = W.BOOL
    kernel.WriteProcessMemory.argtypes = [
        W.HANDLE,
        C.c_void_p,
        C.c_void_p,
        C.c_size_t,
        C.POINTER(C.c_size_t),
    ]
    kernel.WriteProcessMemory.restype = W.BOOL
    kernel.CreateRemoteThread.argtypes = [
        W.HANDLE,
        C.c_void_p,
        C.c_size_t,
        C.c_void_p,
        C.c_void_p,
        W.DWORD,
        C.POINTER(W.DWORD),
    ]
    kernel.CreateRemoteThread.restype = W.HANDLE
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.GetExitCodeThread.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    kernel.GetExitCodeThread.restype = W.BOOL

    kernel.GetModuleHandleW.argtypes = [W.LPCWSTR]
    kernel.GetModuleHandleW.restype = W.HMODULE
    # The second parameter is intentionally a raw pointer.  With
    # FROM_ADDRESS it is an address, not a string despite the W suffix.
    kernel.GetModuleHandleExW.argtypes = [W.DWORD, C.c_void_p, C.POINTER(W.HMODULE)]
    kernel.GetModuleHandleExW.restype = W.BOOL
    kernel.GetModuleFileNameW.argtypes = [W.HMODULE, W.LPWSTR, W.DWORD]
    kernel.GetModuleFileNameW.restype = W.DWORD
    kernel.GetProcAddress.argtypes = [W.HMODULE, C.c_char_p]
    kernel.GetProcAddress.restype = C.c_void_p
    kernel.LoadLibraryExW.argtypes = [W.LPCWSTR, W.HANDLE, W.DWORD]
    kernel.LoadLibraryExW.restype = W.HMODULE
    kernel.FreeLibrary.argtypes = [W.HMODULE]
    kernel.FreeLibrary.restype = W.BOOL
    return kernel


def _local_path(path: Path) -> Path:
    if not path.is_absolute():
        raise RuntimeError(f"DLL path must be absolute: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"DLL path cannot be resolved: {path}: {error}") from error
    if not resolved.is_file():
        raise RuntimeError(f"DLL path is not a regular file: {resolved}")
    return resolved


def _verify_game_build(expected_hash: str = EXPECTED_HASH) -> None:
    try:
        game = GAME.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"Expected EU4 executable is unavailable: {GAME}: {error}") from error
    digest = hashlib.sha256(game.read_bytes()).hexdigest()
    if digest.casefold() != expected_hash.casefold():
        raise RuntimeError(
            f"Unsupported EU4 executable build at {game}; expected SHA-256 {expected_hash}, "
            f"got {digest}"
        )


def _read_pe32_plus(path: Path) -> tuple[int, int]:
    """Check the DLL PE headers and return (machine, size_of_image)."""

    try:
        data = path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"Cannot read DLL {path}: {error}") from error
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise RuntimeError(f"DLL is not a valid DOS PE image: {path}")
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if pe_offset < 0x40 or pe_offset + 0x58 > len(data):
        raise RuntimeError(f"DLL has an invalid PE header offset: {path}")
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise RuntimeError(f"DLL has no PE signature: {path}")
    machine = int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little")
    optional_size = int.from_bytes(data[pe_offset + 20 : pe_offset + 22], "little")
    optional = pe_offset + 24
    if optional + optional_size > len(data) or optional_size < 0x70:
        raise RuntimeError(f"DLL has an invalid optional PE header: {path}")
    magic = int.from_bytes(data[optional : optional + 2], "little")
    if machine != 0x8664 or magic != 0x20B:
        raise RuntimeError(
            f"DLL must be PE32+ x64 (machine 0x8664/magic 0x20b); "
            f"got machine 0x{machine:x}/magic 0x{magic:x}: {path}"
        )
    size_of_image = int.from_bytes(data[optional + 56 : optional + 60], "little")
    if size_of_image <= 0:
        raise RuntimeError(f"DLL has an invalid SizeOfImage: {path}")
    return machine, size_of_image


def _local_bridge_export(kernel: C.WinDLL, dll: Path, image_size: int) -> LocalExport:
    """Map the DLL without resolving imports and derive BridgeStart's RVA."""

    mapped = kernel.LoadLibraryExW(
        str(dll), None, LOAD_LIBRARY_EX_DONT_RESOLVE_DLL_REFERENCES
    )
    mapped_base = _ptr(mapped)
    if not mapped_base:
        raise _win_error(f"LoadLibraryExW(DONT_RESOLVE_DLL_REFERENCES) failed for {dll}")
    try:
        export = kernel.GetProcAddress(mapped, BRIDGE_EXPORT)
        export_address = _ptr(export)
        if not export_address:
            raise _win_error(f"DLL does not export {BRIDGE_EXPORT.decode()} ({dll})")
        export_rva = export_address - mapped_base
        if export_rva <= 0 or export_rva >= image_size:
            raise RuntimeError(
                f"{BRIDGE_EXPORT.decode()} is outside the mapped x64 DLL image "
                f"(RVA 0x{export_rva:x}, image size 0x{image_size:x})"
            )
        return LocalExport(mapped_base, export_address, export_rva, image_size)
    finally:
        if not kernel.FreeLibrary(mapped):
            # The address/RVA is already captured.  Surface a warning at the
            # call site rather than making the result look like an injection
            # failure solely because the temporary local map could not close.
            pass


def _query_process_path(kernel: C.WinDLL, process: W.HANDLE) -> str:
    buffer = C.create_unicode_buffer(32768)
    length = W.DWORD(len(buffer))
    if not kernel.QueryFullProcessImageNameW(process, 0, buffer, C.byref(length)):
        raise _win_error("QueryFullProcessImageNameW failed")
    return buffer.value


def _module_path(kernel: C.WinDLL, process: W.HANDLE, module: int) -> str:
    buffer = C.create_unicode_buffer(32768)
    length = kernel.K32GetModuleFileNameExW(
        process, W.HMODULE(module), buffer, len(buffer)
    )
    if not length:
        raise _win_error(f"K32GetModuleFileNameExW failed for module 0x{module:x}")
    return buffer.value


def _enum_modules(kernel: C.WinDLL, process: W.HANDLE) -> list[RemoteModule]:
    capacity = 256
    while capacity <= 8192:
        modules = (W.HMODULE * capacity)()
        needed = W.DWORD()
        if not kernel.K32EnumProcessModulesEx(
            process,
            modules,
            C.sizeof(modules),
            C.byref(needed),
            LIST_MODULES_ALL,
        ):
            raise _win_error("K32EnumProcessModulesEx failed")
        if needed.value > C.sizeof(modules):
            capacity *= 2
            continue
        count = needed.value // C.sizeof(W.HMODULE)
        result: list[RemoteModule] = []
        for index in range(count):
            handle = _ptr(modules[index])
            if not handle:
                continue
            result.append(RemoteModule(handle, _module_path(kernel, process, handle)))
        if not result:
            raise RuntimeError("Target process has no readable modules")
        return result
    raise RuntimeError("Target process module list is unexpectedly large")


def _find_module(modules: Iterable[RemoteModule], path: str | Path) -> list[RemoteModule]:
    wanted = _canonical(path)
    return [module for module in modules if _canonical(module.path) == wanted]


def _local_system_function(kernel: C.WinDLL) -> SystemFunction:
    kernel32 = kernel.GetModuleHandleW("kernel32.dll")
    if not _ptr(kernel32):
        raise _win_error("GetModuleHandleW(kernel32.dll) failed")
    address = _ptr(kernel.GetProcAddress(kernel32, b"LoadLibraryW"))
    if not address:
        raise _win_error("GetProcAddress(LoadLibraryW) failed")

    owner = W.HMODULE()
    flags = GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT
    if not kernel.GetModuleHandleExW(flags, C.c_void_p(address), C.byref(owner)):
        raise _win_error("GetModuleHandleExW(FROM_ADDRESS) failed for LoadLibraryW")
    owner_base = _ptr(owner)
    if not owner_base:
        raise RuntimeError("GetModuleHandleExW returned an empty module handle")
    owner_path_buffer = C.create_unicode_buffer(32768)
    path_length = kernel.GetModuleFileNameW(owner, owner_path_buffer, len(owner_path_buffer))
    if not path_length:
        raise _win_error("GetModuleFileNameW failed for the LoadLibraryW owner")
    owner_path = owner_path_buffer.value
    rva = address - owner_base
    if rva <= 0:
        raise RuntimeError(
            f"LoadLibraryW address 0x{address:x} is not inside its owner module {owner_path}"
        )
    return SystemFunction(address, owner_base, owner_path, rva)


def _wait_thread(kernel: C.WinDLL, thread: W.HANDLE, timeout_ms: int, label: str) -> int:
    result = kernel.WaitForSingleObject(thread, timeout_ms)
    if result == WAIT_TIMEOUT:
        raise TimeoutError(f"{label} timed out after {timeout_ms} ms")
    if result == WAIT_FAILED:
        raise _win_error(f"WaitForSingleObject failed while waiting for {label}")
    if result != WAIT_OBJECT_0:
        raise RuntimeError(f"Unexpected wait status 0x{result:x} for {label}")
    exit_code = W.DWORD()
    if not kernel.GetExitCodeThread(thread, C.byref(exit_code)):
        raise _win_error(f"GetExitCodeThread failed for completed {label}")
    return int(exit_code.value)


def _remote_thread(
    kernel: C.WinDLL,
    process: W.HANDLE,
    start_address: int,
    parameter: int = 0,
) -> W.HANDLE:
    thread_id = W.DWORD()
    thread = kernel.CreateRemoteThread(
        process,
        None,
        0,
        C.c_void_p(start_address),
        C.c_void_p(parameter) if parameter else None,
        0,
        C.byref(thread_id),
    )
    if not thread:
        raise _win_error(f"CreateRemoteThread failed at 0x{start_address:x}")
    return thread


def _run(args: argparse.Namespace, *, expected_game_hash: str = EXPECTED_HASH) -> dict[str, object]:
    _require_windows_x64()
    _verify_game_build(expected_game_hash)
    dll = _local_path(Path(args.dll))
    _, image_size = _read_pe32_plus(dll)
    kernel = _configure_kernel32()
    export = _local_bridge_export(kernel, dll, image_size)
    load_library = _local_system_function(kernel)

    if args.pid == os.getpid():
        raise RuntimeError("Refusing to target the loader's own process")

    process = kernel.OpenProcess(PROCESS_ACCESS, False, args.pid)
    if not process:
        raise _win_error(f"OpenProcess failed for PID {args.pid}")

    path_allocation = 0
    load_thread: W.HANDLE | None = None
    bridge_thread: W.HANDLE | None = None
    path_allocation_retained = False
    warnings: list[str] = []
    try:
        process_path = _query_process_path(kernel, process)
        if _canonical(process_path) != _canonical(GAME):
            raise RuntimeError(
                f"PID {args.pid} is not the expected EU4 executable: {process_path}"
            )
        modules_before = _enum_modules(kernel, process)
        known_bridge = [module for module in modules_before
                        if Path(module.path).name.casefold().startswith(('eu4_bridge_', 'eu4_pair_lifecycle_', 'eu4_pair_pipeline_'))]
        if known_bridge:
            raise RuntimeError(
                f"An EU4 bridge DLL is already loaded ({known_bridge[0].path}); "
                "restart the game before installing another build."
            )
        duplicate = _find_module(modules_before, dll)
        if duplicate:
            raise RuntimeError(
                f"Refusing to load DLL already present in target process: {duplicate[0].path}"
            )
        system_matches = _find_module(modules_before, load_library.owner_path)
        if len(system_matches) != 1:
            raise RuntimeError(
                "Could not uniquely match the LoadLibraryW owner module in the target "
                f"process ({load_library.owner_path}; matches={len(system_matches)})"
            )
        remote_system = system_matches[0]
        remote_load_library = remote_system.handle + load_library.rva

        path_buffer = C.create_unicode_buffer(str(dll))
        path_bytes = C.sizeof(path_buffer)
        path_allocation = _ptr(
            kernel.VirtualAllocEx(
                process,
                None,
                path_bytes,
                MEM_COMMIT | MEM_RESERVE,
                PAGE_READWRITE,
            )
        )
        if not path_allocation:
            raise _win_error("VirtualAllocEx failed for the temporary DLL path")
        written = C.c_size_t()
        if not kernel.WriteProcessMemory(
            process,
            C.c_void_p(path_allocation),
            C.cast(path_buffer, C.c_void_p),
            path_bytes,
            C.byref(written),
        ) or written.value != path_bytes:
            raise _win_error(
                f"WriteProcessMemory wrote {written.value} of {path_bytes} DLL path bytes"
            )

        load_thread = _remote_thread(kernel, process, remote_load_library, path_allocation)
        path_allocation_retained = True
        try:
            loader_exit = _wait_thread(kernel, load_thread, args.timeout_ms, "LoadLibraryW")
            path_allocation_retained = False
        except TimeoutError as error:
            # The loader may still dereference the path.  Never free it here.
            path_allocation_retained = True
            raise RuntimeError(f"{error}; temporary path allocation was retained") from error
        finally:
            kernel.CloseHandle(load_thread)
            load_thread = None

        modules_after = _enum_modules(kernel, process)
        dll_matches = _find_module(modules_after, dll)
        if len(dll_matches) != 1:
            raise RuntimeError(
                "LoadLibraryW completed but the DLL was not uniquely found by its module path "
                f"(matches={len(dll_matches)}; thread exit status 0x{loader_exit:x})"
            )
        remote_dll = dll_matches[0]

        # The 32-bit GetExitCodeThread value above is only a diagnostic.  The
        # 64-bit module base used below comes from K32EnumProcessModulesEx.
        remote_bridge = remote_dll.handle + export.export_rva
        bridge_thread = _remote_thread(kernel, process, remote_bridge)
        try:
            bridge_exit = _wait_thread(kernel, bridge_thread, args.timeout_ms, "BridgeStart")
        except TimeoutError as error:
            raise RuntimeError(
                f"{error}; BridgeStart may still be executing, so no DLL unload was attempted"
            ) from error
        finally:
            kernel.CloseHandle(bridge_thread)
            bridge_thread = None

        if bridge_exit != 0:
            raise RuntimeError(
                f"BridgeStart returned {bridge_exit}; DLL remains loaded. "
                "Inspect probe.jsonl; do not retry in this process."
            )

        if path_allocation and not kernel.VirtualFreeEx(
            process, C.c_void_p(path_allocation), 0, MEM_RELEASE
        ):
            warnings.append(
                f"VirtualFreeEx failed for temporary path allocation 0x{path_allocation:x}: "
                f"{C.WinError(C.get_last_error())}"
            )
        path_allocation = 0
        return {
            "pid": args.pid,
            "process": process_path,
            "dll": str(dll),
            "dll_module_base": hex(remote_dll.handle),
            "bridge_rva": hex(export.export_rva),
            "bridge_remote_address": hex(remote_bridge),
            "load_library_owner": load_library.owner_path,
            "load_library_rva": hex(load_library.rva),
            "load_library_remote_address": hex(remote_load_library),
            "load_thread_exit_status": hex(loader_exit),
            "bridge_thread_exit_status": hex(bridge_exit),
            "test_save_acknowledged": True,
            "dll_unloaded": False,
            "warnings": warnings,
        }
    finally:
        if bridge_thread:
            kernel.CloseHandle(bridge_thread)
        if load_thread:
            kernel.CloseHandle(load_thread)
        # A failed CreateRemoteThread has no user of this allocation.  Once a
        # loader thread was started, the timeout path deliberately retains it.
        if path_allocation and not path_allocation_retained:
            kernel.VirtualFreeEx(process, C.c_void_p(path_allocation), 0, MEM_RELEASE)
        kernel.CloseHandle(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=_positive_pid, help="EU4 process ID")
    parser.add_argument(
        "--dll",
        required=True,
        help="absolute path to the x64 DLL exporting BridgeStart",
    )
    parser.add_argument(
        "--ack-test-save",
        required=True,
        action="store_true",
        help="confirm a disposable test game was saved before injection",
    )
    parser.add_argument(
        "--timeout-ms",
        default=10_000,
        type=_bounded_timeout,
        help="bounded wait per remote thread (100..60000 ms; default: 10000)",
    )
    args = parser.parse_args()
    try:
        report = _run(args)
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f"inject_probe: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
