"""Only exact isolated compiler/mock child job; no game or DLL execution."""
import ctypes, hashlib, json, subprocess, sys, time
from ctypes import wintypes as w
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def desc(p):
 h=hashlib.sha256();size=0
 with p.open('rb') as f:
  while block:=f.read(1024*1024):h.update(block);size+=len(block)
 return {'bytes':size,'sha256':h.hexdigest()}
def sources():
 from prepare import current
 return current()
def seal(p,v):
 with p.open('xb') as f:f.write((json.dumps(v,indent=2,sort_keys=True)+'\n').encode('ascii'))
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
    limits.BasicLimitInformation.LimitFlags = 0x100 | 0x200 | 0x2000  # per-process + whole job commit / kill on close
    limits.ProcessMemoryLimit = 768 * 1024 * 1024
    limits.JobMemoryLimit = 768 * 1024 * 1024
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
 label=sys.argv[1] if len(sys.argv)==2 else 'validation-final'
 assert label.isascii() and label.replace('-','').isalnum()
 out=HERE/label;out.mkdir(exist_ok=False)
 before=sources()
 # Preserve exact source bytes for this final/subsequent validation attempt.
 for name in before:
  target=out/'source-preimages'/name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write((HERE/name).read_bytes())
 pins=json.loads((HERE/'input-pins.json').read_bytes()) if (HERE/'input-pins.json').exists() else {}
 input_before={k:desc(ROOT/k) for k in pins}
 assert input_before==pins
 build=run_build(out)
 after=sources();input_after={k:desc(ROOT/k) for k in pins}
 outputs={str(x.relative_to(out)).replace('\\','/'):desc(x) for x in sorted(out.rglob('*')) if x.is_file()}
 text=(out/'build/test.stdout').read_text() if (out/'build/test.stdout').exists() else ''
 result={'passed':build['exit_code']==0 and before==after and input_before==input_after,'build':build,'before':before,'after':after,'inputs_before':input_before,'inputs_after':input_after,'outputs':outputs,'tests':text,'native_calls':0,'DLL_built':False,'all_shells_collected':True,'remaining_sessions':[]}
 seal(out/'validation.json',result);print(json.dumps({'passed':result['passed'],'build':build,'tests':text}))
 raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()
