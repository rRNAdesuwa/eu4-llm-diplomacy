"""Offline MSVC/fake-only validation, exact input pins, CREATE_NEW seals.

The Windows job observes/limits only our spawned analysis compiler/test tree.
No game process, DLL, module, executable bytes or OS identity is inspected.
"""
import ctypes
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_FILES = ['input-pins.json', 'pair_component.h', 'pair_component.cpp',
                'test_pair_component.cpp', 'build_test.cmd', 'validate.py',
                'prepare.py', 'README.md', 'profile-registry.json']


def read(path):
    assert path.stat().st_size <= 4 * 1024 * 1024, path
    return path.read_bytes()


def desc(path):
    raw = read(path)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def inputs():
    data = json.loads(read(HERE / 'input-pins.json'))
    result = {}
    for row in data['files']:
        actual = desc(ROOT / row['path'])
        assert actual == {k: row[k] for k in ('bytes', 'sha256')}, row['path']
        result[row['path']] = actual
    return result


def own():
    return {name: desc(HERE / name) for name in SOURCE_FILES}


def seal(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
    with path.open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


class BasicLimit(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', w.DWORD),
                ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]


class IO(ctypes.Structure):
    _fields_ = [(x, ctypes.c_ulonglong) for x in ('ReadOperationCount', 'WriteOperationCount',
                'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimit), ('IoInfo', IO),
                ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(x, ctypes.c_longlong) for x in ('TotalUserTime', 'TotalKernelTime',
                'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')] + [(x, w.DWORD) for x in
                ('TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses')]


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
for name, argtypes, restype in [
    ('CreateJobObjectW', [ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
    ('SetInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
    ('QueryInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
    ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
    ('TerminateJobObject', [w.HANDLE, w.UINT], w.BOOL),
    ('CloseHandle', [w.HANDLE], w.BOOL),
]:
    function = getattr(kernel, name)
    function.argtypes = argtypes
    function.restype = restype
resume = ctypes.WinDLL('ntdll').NtResumeProcess
resume.argtypes = [w.HANDLE]
resume.restype = ctypes.c_long


def require(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def run_build(output):
    job = require(kernel.CreateJobObjectW(None, None))
    limits = ExtendedLimit()
    limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2000  # per-process commit / kill on close
    limits.ProcessMemoryLimit = 768 * 1024 * 1024
    require(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
    script, target = str(HERE / 'build_test.cmd'), str(output / 'build')
    assert not any(c in script+target for c in '\"\r\n&|<>^%')
    # cmd /s /c requires an outer pair around the two already quoted paths.
    # Pass exact Windows command text so list2cmdline does not backslash-escape cmd quotes.
    args = 'cmd.exe /d /s /c ""' + script + '" "' + target + '""'
    child = None
    started = time.monotonic()
    stats = ExtendedLimit()
    accounting = Accounting()
    descendant_cleanup = False
    with (output / 'build-command.stdout').open('xb') as log:
        try:
            # Suspended exact child is assigned before it may spawn any compiler descendants.
            child = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=4)
            require(kernel.AssignProcessToJobObject(job, w.HANDLE(int(child._handle))))
            assert resume(w.HANDLE(int(child._handle))) == 0
            while True:
                require(kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
                if child.poll() is not None:
                    if accounting.ActiveProcesses == 0:
                        break
                    # Only descendants of this completed analysis command are contained.
                    # A compiler helper must not outlive the offline build command.
                    if not descendant_cleanup:
                        require(kernel.TerminateJobObject(job, 126))
                        descendant_cleanup = True
                if time.monotonic() - started > 55:
                    require(kernel.TerminateJobObject(job, 124))
                    raise TimeoutError('55s exact analysis job')
                time.sleep(.02)
            code = child.wait(timeout=5)
            require(kernel.QueryInformationJobObject(job, 9, ctypes.byref(stats), ctypes.sizeof(stats), None))
            assert stats.PeakProcessMemoryUsed < limits.ProcessMemoryLimit
        finally:
            if child is not None and child.poll() is None:
                kernel.TerminateJobObject(job, 125)
                child.wait(timeout=5)
            kernel.CloseHandle(job)  # kill-on-close also contains a failed compiler descendant
    return {'argv': args, 'exit_code': code, 'seconds': round(time.monotonic()-started, 3),
            'job_process_count': accounting.TotalProcesses, 'job_active_processes_final': accounting.ActiveProcesses,
            'per_process_commit_limit': limits.ProcessMemoryLimit, 'peak_process_commit': stats.PeakProcessMemoryUsed,
            'peak_job_commit': stats.PeakJobMemoryUsed, 'all_children_collected': True,
            'completed_command_descendants_terminated': descendant_cleanup,
            'OS_scope': 'only this spawned analysis build/test tree; no game attestation'}


def main():
    label = sys.argv[1] if len(sys.argv) == 2 else 'validation-final'
    assert label.isascii() and label.replace('-', '').isalnum()
    output = HERE / label
    output.mkdir(exist_ok=False)
    before = inputs()
    from prepare import registry
    assert json.loads(read(HERE / 'profile-registry.json')) == registry()
    source_before = own()
    build = run_build(output)
    after = inputs()
    assert json.loads(read(HERE / 'profile-registry.json')) == registry()
    source_after = own()
    passed = build['exit_code'] == 0 and before == after and source_before == source_after
    test_text = (output / 'build/test.stdout').read_text(encoding='utf-8') if (output / 'build/test.stdout').exists() else ''
    print(json.dumps({'passed': passed, 'command': build, 'tests': test_text}, ensure_ascii=True))
    if label != 'validation-final':
        seal(output / 'development-validation.json', {'passed': passed, 'build': build, 'inputs_same': before == after,
                                                     'sources_same': source_before == source_after})
        raise SystemExit(0 if passed else 1)
    assert passed
    assert 'groups=24 native_calls=0 submitted=0 production_ready=false' in test_text
    assert json.loads(read(HERE / 'source-index.json')) == source_before
    limits = {'production_ready': False, 'native_ready': False, 'runtime_verified': False,
              'execution_supported': False, 'sender_implemented': False, 'native_adapter_implemented': False,
              'public_backend_registered': False, 'actual_TAG_resolver_implemented': False,
              'game_process_accessed': False, 'game_native_called': False, 'game_exe_read': False,
              'new_decode_bytes': 0, 'DLL_built': False, 'SQLite_accessed': False,
              'OS_game_attestation_verified': False, 'strict_SP_verified': False, 'world_epoch_verified': False,
              'snapshot_ABA_excluded': False, 'lifetime_lock_verified': False,
              'old_or_formal_files_modified': False, 'all_shells_collected': True, 'remaining_sessions': []}
    validation_hash = seal(HERE / 'validation.json', {'schema_version': 1, 'passed': passed,
        'inputs_before': before, 'inputs_after': after, 'candidate_before': source_before, 'candidate_after': source_after,
        'input_pins_unchanged': before == after, 'candidate_sources_unchanged': source_before == source_after,
        'build': build, 'test_groups': 24, 'limits': limits})
    report_hash = seal(HERE / 'report.json', {'schema_version': 1,
        'purpose': 'fixed_private_core_five_plus_curry_synthetic_no_send_component',
        'status': 'sealed_author_component_pending_independent_review', 'passed': passed,
        'native_families': 6, 'action_modes': 12, 'test_groups': 24,
        'input_files': len(before), 'input_bytes': sum(x['bytes'] for x in before.values()),
        'source_index_sha256': desc(HERE / 'source-index.json')['sha256'],
        'input_pins_sha256': desc(HERE / 'input-pins.json')['sha256'], 'validation_sha256': validation_hash,
        'profile_registry_sha256': desc(HERE / 'profile-registry.json')['sha256'], 'build': build,
        'proof_scope': 'compiled concrete private types/control flow; injected synthetic reader/guard/engine only',
        'full88_evidence': {'core_five': 'static slot mapping only; normal caller closure remains unverified',
                            'curry': 'sealed normal caller/static evidence, not runtime permission'},
        'implemented': ['immutable six-family registry and twelve named pair modes',
            'owned original -> full88(NULL,false) -> independent wrapper clone/command -> command gate -> known no-send cleanup',
            'explicit fields, marriage String32 bounded original / empty clone / dedicated destructor',
            'normal false rejection with known cleanup beyond TTL; uncertainty freezes object keys without retry or guessed dtor',
            'bounded private spy cancellation graph, full generation/backrefs, roots before/after, two complete passes and immediate rebind'],
        'remaining': ['reviewed native ABI/adapter and OS held identity/module/exe attestation',
            'actual authenticated TAG resolver and per-family native preflight receipts',
            'five core normal full88 callers; cancellation readers for vassal/marriage/improve/guarantee/curry; spy entry vtable/type guard not closed',
            'strict SP, epoch and lifetime lock; current snapshot equality does not exclude ABA',
            'durable intent/claim and owned transfer sender; no integration into v19 fixed Host',
            'later independent health/effect observation and separate candidate integration review'],
        'development_record': ['Two finite initial path mistakes (PowerShell wildcard rg and reports path) failed, were corrected, and all shells exited.',
            'Development build1 had cmd path quoting failure; build2 compiled core but rejected signed/unsigned test warning and a compiler helper outlived cmd, so the exact analysis job hit55s and was killed/collected. Warning fixed, vcvars telemetry disabled, completed-command descendants now contained and collected. Preimages/logs retained.',
            'No old candidate or formal source was modified.'],
        'limits': limits})
    review_hash = seal(HERE / 'review.json', {'schema_version': 1, 'passed': passed, 'limits': limits,
        'report_sha256': report_hash, 'validation_sha256': validation_hash,
        'source_index_sha256': desc(HERE / 'source-index.json')['sha256'], 'independent_review_required': True})
    print(json.dumps({'report_sha256': report_hash, 'review_sha256': review_hash,
                      'validation_sha256': validation_hash}, sort_keys=True))


if __name__ == '__main__':
    main()
