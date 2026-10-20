"""Pure fake WinAPI/Popen probes; no real child, process lookup or game."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

def probe(module, *, output_bytes=0, query_failure=False):
    events=[]
    class Handle:
        def __int__(self):return 77
        def Close(self):events.append('child_handle_close')
    class Child:
        _handle=Handle()
        def poll(self):return 0
        def wait(self,timeout=None):events.append('wait');return 0
        def kill(self):events.append('kill')
    class Kernel:
        def CreateJobObjectW(self,*args):events.append('job_created');return 123
        def SetInformationJobObject(self,job,kind,raw,size):
            value=ctypes.cast(raw,ctypes.POINTER(module.Extended)).contents
            self.flags=value.BasicLimitInformation.LimitFlags
            self.limit=value.BasicLimitInformation.ActiveProcessLimit
            events.append('limits_set');return 1
        def AssignProcessToJobObject(self,*args):events.append('assigned');return 1
        def QueryInformationJobObject(self,job,kind,raw,size,returned):
            if query_failure:
                ctypes.set_last_error(5)
                return 0
            if kind==1:
                value=ctypes.cast(raw,ctypes.POINTER(module.Accounting)).contents
                value.TotalProcesses=1;value.ActiveProcesses=0
            else:
                value=ctypes.cast(raw,ctypes.POINTER(module.Extended)).contents
                value.PeakJobMemoryUsed=4096;value.PeakProcessMemoryUsed=4096
            return 1
        def TerminateJobObject(self,*args):events.append('job_terminated');return 1
        def CloseHandle(self,*args):events.append('job_closed');return 1
    kernel=Kernel()
    def popen(argv,**kwargs):
        assert kwargs['creationflags'] & 4
        events.append('spawn_suspended')
        kwargs['stdout'].write(b'x'*output_bytes);kwargs['stdout'].flush()
        return Child()
    def resume(handle):events.append('resumed');return 0
    with tempfile.TemporaryDirectory(prefix='offline-fake-job-',dir=ROOT/'work/reports/frida-entry-job-review-20261015-r1') as directory:
        at=Path(directory);error=None;value=None
        with patch.object(module,'_api',return_value=(kernel,resume)), \
             patch.object(module.subprocess,'Popen',side_effect=popen):
            try:value=module.run_cli_tree(['never-executed'],ROOT,at/'stdout.txt',at/'stderr.txt')
            except BaseException as exc:error=type(exc).__name__+': '+str(exc)
        return dict(fake_only=True,output_bytes=(at/'stdout.txt').stat().st_size,
            limit_flags=hex(kernel.flags),hard_active_limit=kernel.limit,
            source_enforced_active_cap=bool(kernel.flags & 8) and kernel.limit==8,
            helper_result=value,exception=error,events=events,
            explicit_child_handle_closes=events.count('child_handle_close'),
            job_closes=events.count('job_closed'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true')
    args=parser.parse_args()
    old=load(ROOT/'work/reports/frida-entry-job-review-20261015-r1/reviewed-preimage/job_tree.py','review_old_job')
    new=load(ROOT/'work/reports/frida-entry-job-review-20261015-r1/reviewed-r2-preimage/job_tree.py','review_r2_job')
    result={'old_fast_output':probe(old,output_bytes=2*1024*1024+1),
        'new_fast_output':probe(new,output_bytes=2*1024*1024+1),
        'new_query_failure':probe(new,query_failure=True)}
    assert result['old_fast_output']['helper_result']['error'] is None
    assert result['new_fast_output']['helper_result']['error']['type']=='RuntimeError'
    assert result['new_query_failure']['explicit_child_handle_closes']==0
    assert result['new_query_failure']['job_closes']==1
    pins={}
    for p in (Path(__file__),Path(old.__file__),Path(new.__file__)):
        raw=p.read_bytes();pins[p.relative_to(ROOT).as_posix()]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    record=dict(schema='EU4-JOB-TREE-INDEPENDENT-BOUNDARY-COUNTEREXAMPLES/1',
        source_pins=pins,cases=result,game_accessed=False,real_children_started=0,
        process_handles_queried=0,job_WinAPI_called=False)
    if args.record:
        path=ROOT/'work/reports/frida-entry-job-review-20261015-r1/boundary-counterexamples-r2.json'
        with path.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(record,stream,indent=2);stream.write('\n')
        raw=path.read_bytes()
        print(json.dumps(dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))
    else:print(json.dumps(record,indent=2))
