"""Bounded offline candidate verification; never imports a process adapter."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LIMIT=1024*1024*1024


class Counters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize',
        'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]


def main():
    command=[sys.executable,'-m','unittest','discover','-s',str(HERE),
             '-p','test_relation_request_observer.py','-v']
    get_memory=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    get_memory.restype=wintypes.BOOL
    start=time.monotonic();peak=0;reason=None
    log=HERE/'test-run.log'
    with log.open('wb') as output:
        child=subprocess.Popen(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                counter=Counters();counter.cb=ctypes.sizeof(counter)
                if not get_memory(wintypes.HANDLE(int(child._handle)),ctypes.byref(counter),counter.cb):
                    if child.poll() is None:
                        reason='Memory-bound inspection unavailable'
                        child.terminate()
                        break
                peak=max(peak,counter.PagefileUsage,counter.PeakPagefileUsage)
                if peak>LIMIT or time.monotonic()-start>600:
                    reason='One GiB committed-memory or 600-second wall bound exceeded'
                    child.terminate()
                    break
                time.sleep(.1)
        finally:
            try:code=child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill();code=child.wait(timeout=10)
    def pin(path):
        data=path.read_bytes()
        return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    report=dict(schema='EU4-RELATION-REQUEST-CANDIDATE-TEST/1',candidate_unsealed=True,
        command=command,cwd=str(ROOT),exit_code=code,termination_reason=reason,
        elapsed_seconds=round(time.monotonic()-start,3),peak_committed_bytes=peak,
        committed_memory_limit_bytes=LIMIT,all_child_processes_collected=True,
        tests_are_synthetic=True,game_process_accessed=False,native_calls=0,requests_published=0,
        sources={path.name:pin(path) for path in (HERE/'relation_request_observer.py',
            HERE/'test_relation_request_observer.py',Path(__file__).resolve())},log=pin(log))
    (HERE/'test-run.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return code if reason is None else 1


if __name__=='__main__':
    raise SystemExit(main())
