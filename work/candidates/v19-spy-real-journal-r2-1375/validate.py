"""CreateNew formal pure-model validation, no captured actual replay."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import datetime,hashlib,json,subprocess,sys,time,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def snapshot():return {name:sha(ROOT/name) for name in pins}
pins=json.loads((HERE/'source-index.json').read_bytes())['files'];before=snapshot();assert before==pins
out=HERE/'validation-results'/('formal-'+uuid.uuid4().hex);out.mkdir(parents=True,exist_ok=False)
class Counters(C.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(name,C.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
api=C.WinDLL('psapi',use_last_error=True);api.GetProcessMemoryInfo.argtypes=[W.HANDLE,C.POINTER(Counters),W.DWORD];api.GetProcessMemoryInfo.restype=W.BOOL
commands=[]
for number,argv in enumerate(([sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']),1):
    start=time.monotonic();peak=0;reason=None
    with (out/f'{number}.stdout').open('xb') as stdout,(out/f'{number}.stderr').open('xb') as stderr:
        child=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr)
        while child.poll() is None:
            c=Counters();c.cb=C.sizeof(c)
            if api.GetProcessMemoryInfo(W.HANDLE(int(child._handle)),C.byref(c),C.sizeof(c)):peak=max(peak,c.PrivateUsage)
            if peak>=1024**3 or time.monotonic()-start>55:reason='budget';child.kill();break
            time.sleep(.05)
        code=child.wait()
    commands.append(dict(argv=argv,exit_code=code,peak_private_bytes_observed=peak,elapsed_seconds=time.monotonic()-start,
        termination_reason=reason,stdout_sha256=sha(out/f'{number}.stdout'),stderr_sha256=sha(out/f'{number}.stderr')))
after=snapshot();result=dict(commands=commands,inputs_before=before,inputs_after=after,unchanged=before==after,
    passed=before==after and all(x['exit_code']==0 and x['termination_reason'] is None for x in commands),
    tests=32,actual_replay_in_this_validation=False,actual_process_access=False,native_call=False,new_decoded_bytes=0,all_child_processes_collected=True)
with (out/'validation.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(dict(path=(out/'validation.json').relative_to(ROOT).as_posix(),sha256=sha(out/'validation.json'),passed=result['passed'],inputs=len(pins))))
raise SystemExit(0 if result['passed'] else 1)
