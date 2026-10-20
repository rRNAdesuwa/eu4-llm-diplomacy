"""Bounded offline runner; separate CLI/delta receipts, never old 46-test log."""
import argparse
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation-delta',action='store_true')
    args=parser.parse_args()
    name='installation-delta-run' if args.installation_delta else 'cli-test-run'
    test='test_relation_request_observer.py' if args.installation_delta else 'test_relation_request_cli.py'
    command=[sys.executable,'-m','unittest','discover','-s',str(HERE),'-p',test,'-v']
    if args.installation_delta:command+=['-k','installation']
    get_memory=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    get_memory.restype=wintypes.BOOL
    start=time.monotonic();peak=0;reason=None
    log=HERE/(name+'.log')
    with log.open('wb') as output:
        child=subprocess.Popen(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                counter=Counters();counter.cb=ctypes.sizeof(counter)
                if not get_memory(wintypes.HANDLE(int(child._handle)),ctypes.byref(counter),counter.cb):
                    if child.poll() is None:
                        reason='Memory-bound inspection unavailable';child.terminate();break
                peak=max(peak,counter.PagefileUsage,counter.PeakPagefileUsage)
                if peak>LIMIT or time.monotonic()-start>600:
                    reason='One GiB committed-memory or 600-second wall bound exceeded';child.terminate();break
                time.sleep(.1)
        finally:
            try:code=child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill();code=child.wait(timeout=10)
    def pin(path):
        data=path.read_bytes()
        return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    source_names=['relation_request_observer.py',test,'run_cli_tests.py']
    if not args.installation_delta:source_names+=['relation_request_cli.py','CLI.md']
    report=dict(schema='EU4-RELATION-REQUEST-CANDIDATE-DELTA-TEST/1',scope=name,candidate_unsealed=True,
        command=command,cwd=str(ROOT),exit_code=code,termination_reason=reason,
        elapsed_seconds=round(time.monotonic()-start,3),peak_committed_bytes=peak,
        committed_memory_limit_bytes=LIMIT,all_child_processes_collected=True,
        tests_are_synthetic=True,game_process_accessed=False,native_calls=0,requests_published=0,
        sources={name:pin(HERE/name) for name in source_names},log=pin(log))
    (HERE/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return code if reason is None else 1


if __name__=='__main__':
    raise SystemExit(main())
