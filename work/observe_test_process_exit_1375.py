"""Observe exit through one held process handle; never stop or alter a process."""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

SHA = '9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--creation', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout-seconds', type=int, default=180)
    a = p.parse_args()
    if a.pid <= 0 or len(a.creation) != 16 or not 1 <= a.timeout_seconds <= 300:
        raise ValueError('Invalid exact process identity or timeout')
    expected_creation = int(a.creation, 16)
    exe = Path(__file__).resolve().parents[2] / 'eu4.exe'
    digest = hashlib.sha256()
    with exe.open('rb') as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    if digest.hexdigest().upper() != SHA:
        raise ValueError('Unexpected executable')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.GetProcessTimes.argtypes = [W.HANDLE,*([C.POINTER(W.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = W.BOOL
    kernel.WaitForSingleObject.argtypes = [W.HANDLE,W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE,C.POINTER(W.DWORD)]
    kernel.GetExitCodeProcess.restype = W.BOOL
    with a.output.open('x', encoding='utf-8', newline='\n') as dst:
        handle = kernel.OpenProcess(0x1000 | 0x00100000, False, a.pid)
        if not handle:
            raise OSError(C.get_last_error(), 'Cannot hold exact process')
        try:
            def times():
                values = [W.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(C.byref(v) for v in values)):
                    raise OSError(C.get_last_error(), 'Cannot read held process times')
                return [(v.dwHighDateTime << 32) | v.dwLowDateTime for v in values]
            path = C.create_unicode_buffer(32768)
            length = W.DWORD(len(path))
            if not kernel.QueryFullProcessImageNameW(handle, 0, path, C.byref(length)) or Path(path.value).resolve() != exe.resolve():
                raise ValueError('Held process executable path differs')
            before = times()
            if before[0] != expected_creation or before[1] != 0 or kernel.WaitForSingleObject(handle, 0) != 258:
                raise ValueError('Process was already exited or creation differs')
            print(json.dumps({'status':'holding_exact_process_for_exit','pid':a.pid,'creation':a.creation}), flush=True)
            deadline = time.monotonic() + a.timeout_seconds
            wait_status = 258
            while wait_status == 258 and time.monotonic() < deadline:
                wait_status = kernel.WaitForSingleObject(handle, 250)
            after = times()
            exited = wait_status == 0 and after[0] == expected_creation and after[1] > expected_creation
            code = W.DWORD()
            if not kernel.GetExitCodeProcess(handle, C.byref(code)):
                raise OSError(C.get_last_error(), 'Cannot read held exit code')
            report = {'schema_version':1,'kind':'exact_process_exit_observation',
                'method':'held_handle_wait_and_getprocesstimes','read_only':True,
                'pid':a.pid,'creation':a.creation,'process_creation_filetime':after[0],
                'process_exit_filetime':after[1],'exit_observed':exited,
                'before_exit_filetime':before[1],'wait_status':wait_status,'exit_code':code.value,
                'executable':str(exe),'executable_sha256':SHA,
                'access':'QUERY_LIMITED_INFORMATION | SYNCHRONIZE',
                'observed_at_utc':datetime.now(timezone.utc).isoformat(),
                'process_stop_requested_by_observer':False}
            json.dump(report,dst,indent=2); dst.write('\n')
            print(json.dumps(report), flush=True)
            return 0 if exited else 2
        finally:
            kernel.CloseHandle(handle)


if __name__ == '__main__':
    raise SystemExit(main())
