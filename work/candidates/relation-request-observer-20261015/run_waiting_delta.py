"""Run only waiting-state CLI regressions; preserve the original 37-test log."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_cli_tests import Counters

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LIMIT=1024*1024*1024


def main():
    command=[sys.executable,'-m','unittest','discover','-s',str(HERE),
             '-p','test_relation_request_cli.py','-v','-k','waiting']
    get_memory=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    get_memory.restype=wintypes.BOOL
    start=time.monotonic();peak=0;reason=None
    log=HERE/'waiting-delta-run.log'
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
    names=['relation_request_cli.py','test_relation_request_cli.py','run_cli_tests.py','run_waiting_delta.py',
           'relation_request_observer.py','CLI-waiting-delta.md']
    evidence=ROOT/'work/reports/war-peace-api-20261015-r10-checkpoint/cli-pending-scalar-boundary-r1.json'
    report=dict(schema='EU4-RELATION-CLI-WAITING-DELTA/1',candidate_unsealed=True,
        command=command,cwd=str(ROOT),exit_code=code,termination_reason=reason,
        elapsed_seconds=round(time.monotonic()-start,3),peak_committed_bytes=peak,
        committed_memory_limit_bytes=LIMIT,all_child_processes_collected=True,
        tests_are_synthetic=True,game_process_accessed=False,native_calls=0,requests_published=0,
        sources={name:pin(HERE/name) for name in names},log=pin(log),
        independent_counterexample=pin(evidence),preimage=pin(HERE/'preaudit-cli-9c23/preimage.json'))
    (HERE/'waiting-delta-run.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return code if reason is None else 1


if __name__=='__main__':
    raise SystemExit(main())
