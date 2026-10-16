"""File-only stopped session archive, preserving original paths and failures."""
import ctypes as C,hashlib,json,types
from ctypes import wintypes as W
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'work/run_pair22_session_1375.py'
m=types.ModuleType('_archive_root');m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
c=m.verified_client();manifest=c.manifest();graph=c.graph()
k=C.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
h=k.OpenProcess(0x1000|0x00100000,False,m.PID)
late_exit=None
if h:
    k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];k.WaitForSingleObject.restype=W.DWORD
    k.GetProcessTimes.argtypes=[W.HANDLE,*([C.POINTER(W.FILETIME)]*4)];k.GetProcessTimes.restype=W.BOOL
    k.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)];k.GetExitCodeProcess.restype=W.BOOL
    k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
    try:
        t=[W.FILETIME() for _ in range(4)];code=W.DWORD()
        m.need(k.WaitForSingleObject(h,0)==0 and k.GetProcessTimes(h,*[C.byref(x) for x in t]) and k.GetExitCodeProcess(h,C.byref(code)),'Exact late handle must be signaled')
        creation=(t[0].dwHighDateTime<<32)|t[0].dwLowDateTime;exited=(t[1].dwHighDateTime<<32)|t[1].dwLowDateTime
        m.need(f'{creation:016x}'==m.CREATION and exited>creation,'Late handle creation/exit')
        late_exit=dict(creation=m.CREATION,exit_FILETIME=exited,exit_code=int(code.value),normal=code.value==0,held_through_lifetime=False)
    finally:k.CloseHandle(h)
else:m.need(C.get_last_error()==87,'PID query must be absent, not unavailable')
OUT=ROOT/'work/runtime/pair22-stopped-archive-r2-50684-20261012a';OUT.mkdir(exist_ok=False)
paths={Path(x) for x in graph.snapshot}
paths.update(ROOT/x for x in manifest['source_pins']);paths.update(ROOT/x for x in json.loads((m.HERE/'input-pins.json').read_bytes()))
paths.update(m.HERE/x for x in json.loads((m.HERE/'source-index.json').read_bytes()))
paths.update(m.HERE/x for x in ['source-index.json','input-pins.json','review.json'])
paths.update(c.BUILD/x for x in ['build.json',manifest['DLL'],f'loader-intent-{m.PID}-{m.CREATION}.json',f'bootstrap-{m.PID}-{m.CREATION}.request',f'loader-{m.PID}-{m.CREATION}.json'])
session=c.BUILD/f'pair22-{m.PID}-{m.CREATION}-60c7109d7d019ebd0fae0ba52e986fd8';paths.update(x for x in session.iterdir() if x.is_file())
paths.update(x for x in m.OUT.iterdir() if x.is_file());paths.update([p,ROOT/'work/diagnose_pair22_lease_1375.py',ROOT/'work/wait_pair22_exit_1375.py',Path(__file__)])
files={};total=0
for path in sorted(paths):
    data=m.bounded(path,4*1024*1024);total+=len(data);m.need(total<=40*1024*1024 and len(files)<512,'Archive budget')
    relative=path.relative_to(ROOT).as_posix();target=OUT/'files'/relative;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(data)
    m.need(hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(data).digest(),'Archive verification')
    files[relative]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
m.dump_new(OUT/'archive.json',dict(schema='EU4PAIR22STOPPEDARCHIVE/1',pid=m.PID,creation=m.CREATION,session='60c7109d7d019ebd0fae0ba52e986fd8',files=files,total_bytes=total,
    process_stopped_verified=True,late_exact_handle_exit=late_exit,normal_menu_quit_clicked=True,quit_confirmation_clicked=True,held_exit_watcher_timed_out=True,held_normal_exit_verified=False,
    native_call_attempts=0,claimed_sequences=[1],unclaimed_published_sequences=[2,3,4,5,6],retried=False,production_ready=False))
print(json.dumps(dict(files=len(files),bytes=total,archive_sha256=hashlib.sha256((OUT/'archive.json').read_bytes()).hexdigest())))
