"""Bound only a newly spawned CLI tree; never assign or stop the target game.

Win64 structure/limit layout follows the previously reviewed offline job helper
work/review-results/v21-pair-r2-action-catalog-20261008a/job_helper.py.
No environment values are logged. Child startup is suspended until containment.
"""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import time


class BasicLimit(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
        ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', w.DWORD),
        ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]


class IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount',
        'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class Extended(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimit), ('IoInfo', IO),
        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in ('TotalUserTime', 'TotalKernelTime',
        'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')] + [(name, w.DWORD) for name in
        ('TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses')]


def _api():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, arguments, result in [
        ('CreateJobObjectW', [ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        ('SetInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        ('QueryInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
        ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
        ('TerminateJobObject', [w.HANDLE, w.UINT], w.BOOL),
        ('CloseHandle', [w.HANDLE], w.BOOL)]:
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    resume = ctypes.WinDLL('ntdll').NtResumeProcess
    resume.argtypes, resume.restype = [w.HANDLE], ctypes.c_long
    return kernel, resume


def _require(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def run_cli_tree(argv, cwd, stdout_path, stderr_path, *, timeout_seconds=45, memory_limit=768*1024*1024):
    """Return a collected-job receipt or retain its explicit error in the receipt.

    This helper only receives a command from its reviewed caller. The target
    game's existing PID is never assigned to this job. Frida's target agent is
    not a child process and is governed by REA detach plus the host postchecks.
    """
    if (type(argv) is not list or not argv or not all(type(x) is str and x and '\0' not in x for x in argv)
            or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 45
            or type(memory_limit) is not int or not 16*1024*1024 <= memory_limit <= 768*1024*1024):
        raise ValueError('Invalid contained CLI bounds')
    kernel, resume = _api()
    job = _require(kernel.CreateJobObjectW(None, None))
    child = None
    accounting, peak = Accounting(), Extended()
    error, exit_code, descendant_cleanup = None, None, False
    started = time.monotonic()
    try:
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x8 | 0x100 | 0x200 | 0x2000
        limits.BasicLimitInformation.ActiveProcessLimit = 8
        limits.ProcessMemoryLimit = limits.JobMemoryLimit = memory_limit
        _require(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        with Path(stdout_path).open('xb') as stdout, Path(stderr_path).open('xb') as stderr:
            try:
                child = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr,
                    creationflags=0x00000004 | subprocess.CREATE_NO_WINDOW)
                _require(kernel.AssignProcessToJobObject(job, w.HANDLE(int(child._handle))))
                if resume(w.HANDLE(int(child._handle))) != 0:
                    raise RuntimeError('Could not resume exact contained CLI child')
                completed_at = None
                while True:
                    _require(kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
                    if accounting.TotalProcesses > 8:
                        raise RuntimeError('Contained CLI child-count bound')
                    if child.poll() is not None:
                        if accounting.ActiveProcesses == 0:
                            break
                        completed_at = completed_at or time.monotonic()
                        if time.monotonic()-completed_at >= 1:
                            _require(kernel.TerminateJobObject(job, 126))
                            descendant_cleanup = True
                    if time.monotonic()-started > timeout_seconds:
                        raise TimeoutError('Contained CLI exceeded its wall-clock bound')
                    if any(Path(p).stat().st_size > 2*1024*1024 for p in (stdout_path, stderr_path)):
                        raise RuntimeError('Contained CLI output bound')
                    time.sleep(0.02)
                exit_code = child.wait(timeout=5)
                # A fast child may exit between polls. Its final files still
                # must pass the acceptance bound before a successful receipt.
                if any(Path(p).stat().st_size > 2*1024*1024 for p in (stdout_path, stderr_path)):
                    raise RuntimeError('Contained CLI final output bound')
            except BaseException as exc:
                error = dict(type=type(exc).__name__, message=str(exc))
                if child is not None:
                    # Exact job created above, containing only our CLI tree.
                    kernel.TerminateJobObject(job, 124)
                    if child.poll() is None:
                        child.kill()  # Also collects an unassigned suspended startup failure.
                    exit_code = child.wait(timeout=5)
            finally:
                try:
                    if child is not None and child.poll() is None:
                        kernel.TerminateJobObject(job, 125)
                        child.kill()
                        child.wait(timeout=5)
                    # Termination is asynchronous; observe zero contained
                    # members before reporting cleanup, rather than merely
                    # closing handles. A failed query remains an error.
                    cleanup_deadline = time.monotonic()+5
                    while True:
                        _require(kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
                        if accounting.ActiveProcesses == 0 or time.monotonic() >= cleanup_deadline:
                            break
                        time.sleep(0.02)
                    _require(kernel.QueryInformationJobObject(job, 9, ctypes.byref(peak), ctypes.sizeof(peak), None))
                    _require(kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
                finally:
                    # Statistics/cleanup-query failure must not bypass our
                    # direct process handle close. It never implies active=0.
                    if child is not None:
                        child._handle.Close()
    finally:
        kernel.CloseHandle(job)
    return dict(exit_code=exit_code, error=error, seconds=round(time.monotonic()-started, 3),
        job_total_processes=accounting.TotalProcesses, job_active_processes_final=accounting.ActiveProcesses,
        peak_process_commit=peak.PeakProcessMemoryUsed, peak_job_commit=peak.PeakJobMemoryUsed,
        memory_limit=memory_limit, direct_child_collected=child is not None,
        hard_active_process_limit=8, cumulative_process_refusal_bound=8,
        per_stream_output_acceptance_bound=2*1024*1024,
        output_writer_may_overshoot_before_refusal=True,
        completed_command_descendants_terminated=descendant_cleanup,
        existing_target_game_assigned_to_job=False, target_cleanup_proven_by_job=False,
        environment_logged=False)
