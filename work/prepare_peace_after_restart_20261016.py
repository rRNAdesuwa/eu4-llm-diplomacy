"""Prepare one fixed new-process read after explicit user restart and observed pause."""
from pathlib import Path
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/peace-current-pending-observer-live-after-restart-20261016-r2'
ORIGIN = ROOT / 'work/reports/peace-current-pending-observer-live-20261016-r1/capture_once.py'
PID = 98548

def pin(b):
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

k = ctypes.WinDLL('kernel32', use_last_error=True)
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
k.GetProcessTimes.restype = W.BOOL
k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
k.QueryFullProcessImageNameW.restype = W.BOOL
k.CloseHandle.argtypes = [W.HANDLE]
k.CloseHandle.restype = W.BOOL
h = k.OpenProcess(0x1000, False, PID)
if not h:
    raise ctypes.WinError(ctypes.get_last_error())
try:
    times = [W.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(h, *[ctypes.byref(t) for t in times]):
        raise ctypes.WinError(ctypes.get_last_error())
    creation = f'{(times[0].dwHighDateTime << 32) | times[0].dwLowDateTime:016x}'
    path_buf = ctypes.create_unicode_buffer(32768)
    count = W.DWORD(len(path_buf))
    if not k.QueryFullProcessImageNameW(h, 0, path_buf, ctypes.byref(count)):
        raise ctypes.WinError(ctypes.get_last_error())
    assert path_buf.value.lower() == str(ROOT.parent / 'eu4.exe').lower()
finally:
    assert k.CloseHandle(h)

original = ORIGIN.read_bytes()
assert len(original) < 65536
text = original.decode('utf-8')
assert text.count('38076') == 2 and text.count('01dd5cac0b1ad003') == 2
text = text.replace('38076', str(PID)).replace('01dd5cac0b1ad003', creation)
text = text.replace('FIRST-LIVE', 'AFTER-RESTART-LIVE-R2')
text = text.replace('second_status_attempt=False', 'second_status_attempt=True')
now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
assert text.count('2026-10-15T18:46:04.2554391Z') == 1
text = text.replace('2026-10-15T18:46:04.2554391Z', now)
needle = "no_effect_profile_promotion=True,no_all120_claim=True,independent_live_replay_pending=True)"
assert text.count(needle) == 1
text = text.replace(needle, "no_effect_profile_promotion=True,no_all120_claim=True,independent_live_replay_pending=True,\n  after_user_requested_restart=True,prior_process_pid=38076,prior_status_frozen_unknown=True,\n  UI_preparation_separate_from_this_controller=True,observed_UI_date='1445-05-19',observed_UI_paused=True)")
derived = text.encode('utf-8')
compile(derived, 'capture_once.py', 'exec')
assert ORIGIN.read_bytes() == original
OUT.mkdir(exist_ok=False)
with (OUT / 'capture_once.py').open('xb') as f:
    f.write(derived)
record = {
    'schema': 'EU4-NEW-PROCESS-READONLY-PREPARATION/1',
    'selection': {'pid': PID, 'creation': creation, 'actor': 'FRA', 'target': 'ENG'},
    'OS_inventory_UTC': now,
    'image_path_checked': path_buf.value,
    'OS_query_handle_close_checked': True,
    'user_requested_restart': True,
    'old_pid_absent_before_launch': True,
    'old_stop_command_did_not_execute': 'Get-Process38076 returned not found before mutation',
    'old_ownership_or_effect_promoted': False,
    'UI_preparation': 'Computer Use observed primary-screen main menu, clicked Continue and achievement confirmation, then observed France1445-05-19 with pause banner.',
    'prior_status_remains': 'unknown, prior PID38076, no world samples',
    'original_controller': {'path': ORIGIN.relative_to(ROOT).as_posix(), **pin(original)},
    'derived_controller': pin(derived),
    'derivation': ['only fixedPID/creation/inventoryUTC', 'schema labels identify after-restart scope', 'historical second status and UI preparation are disclosed'],
    'status_attempt_limit_in_new_controller': 1,
    'automatic_retry': False,
    'RPM_limit': {'calls': 4096, 'bytes': 524288, 'single_read': 65536},
    'Job_limit': {'memory': 805306368, 'seconds': 45},
    'new_diplomacy_requests': 0,
    'new_native_game_calls': 0,
    'Frida_or_DLL_install': False,
    'current_status_only': True,
    'effect_and_original_request_proof': False,
}
b = (json.dumps(record, ensure_ascii=True, indent=2) + '\n').encode()
with (OUT / 'preparation.json').open('xb') as f:
    f.write(b)
print(json.dumps({'prepared': True, 'selection': record['selection'], 'controller': pin(derived), 'preparation': pin(b)}, ensure_ascii=True))
