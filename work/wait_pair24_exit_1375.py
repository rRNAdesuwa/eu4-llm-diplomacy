"""Bounded held-handle exit receipt for this exact finished V24 process only."""
import ctypes as C,json,sys,types
from ctypes import wintypes as W
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'work/run_pair24_session_r2_1375.py'
m=types.ModuleType('_exit_root');m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
client=m.verified_client();manifest=client.manifest();ro=client.graph().local('readonly.py')
id=client.identity(m.PID,m.CREATION,'dfd56862d97a41dd56e3595228011b3a',manifest);h=ro.Held(id)
try:
    h.identity_check();print('held exact V24 process; waiting <=55 seconds',flush=True)
    result=h.kernel.WaitForSingleObject(h.handle,55000);receipt=dict(identity=id,wait_result=int(result),exited=result==0,normal_exit_verified=False)
    if result==0:
        code=W.DWORD();h.kernel.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)];h.kernel.GetExitCodeProcess.restype=W.BOOL
        times=[W.FILETIME() for _ in range(4)]
        m.need(h.kernel.GetExitCodeProcess(h.handle,C.byref(code)) and h.kernel.GetProcessTimes(h.handle,*[C.byref(x) for x in times]),'Held exit details')
        creation=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime;exit_time=(times[1].dwHighDateTime<<32)|times[1].dwLowDateTime
        m.need(f'{creation:016x}'==m.CREATION and exit_time>creation,'Held creation/exit timestamp')
        receipt.update(exit_code=int(code.value),exit_FILETIME=exit_time,normal_exit_verified=code.value==0)
    m.dump_new(m.OUT/'held-exit.json',receipt);print(json.dumps(receipt));raise SystemExit(0 if receipt['normal_exit_verified'] else 1)
finally:h.close()
