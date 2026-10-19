"""Preserve the too-strict PID-absence guard; accept exact signaled late handle."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'work/archive_pair22_stopped_1375.py';b=p.read_bytes()
old=b"h=k.OpenProcess(0x1000,False,m.PID);m.need(not h and C.get_last_error()==87,'Exact old PID must be absent')"
new=b'''h=k.OpenProcess(0x1000|0x00100000,False,m.PID)
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
else:m.need(C.get_last_error()==87,'PID query must be absent, not unavailable')'''
assert b.count(old)==1;b=b.replace(old,new)
b=b.replace(b'pair22-stopped-archive-50684-20261012a',b'pair22-stopped-archive-r2-50684-20261012a')
b=b.replace(b'process_absence_verified=True,normal_menu_quit_clicked=True',b'process_stopped_verified=True,late_exact_handle_exit=late_exit,normal_menu_quit_clicked=True')
with (ROOT/'work/archive_pair22_stopped_r2_1375.py').open('xb') as f:f.write(b)
print('created fresh archive helper R2')
