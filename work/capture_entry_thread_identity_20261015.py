"""Current OS thread identity crosscheck; never reads retained Q/heap addresses."""
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT/'work/candidates/frida-entry-observer-1375-v1/capture_once.py'
CAPTURE = ROOT/'work/reports/war-peace-api-20261015-r12-entry-live/capture.json'
PAYLOAD = ROOT/'work/reports/war-peace-api-20261015-r12-entry-live/owned-payload.json'
OUT = ROOT/'work/reports/war-peace-api-20261015-r12-entry-live/current-thread-identity.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_host():
    raw = HOST.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e'
    module = types.ModuleType('frozen_entry_host_for_current_thread')
    module.__file__ = str(HOST)
    exec(compile(raw,str(HOST),'exec'),module.__dict__)
    return module


def ft(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def main():
    assert not OUT.exists()
    host = load_host()
    initial = host.verify_manifest()
    assert initial['manifest_sha256'] == 'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166'
    assert digest(CAPTURE) == 'cd96099990856fde385a8499f7e3c1d0a303ed11d6460947d45dab0c9ce83a6b'
    retained = json.loads(CAPTURE.read_bytes())
    assert retained['status'] == 'structural_match'
    source = json.loads(PAYLOAD.read_bytes())
    tid = source['observation']['thread_id']
    assert type(tid) is int and 0 < tid <= 0xFFFFFFFF
    sys.path.insert(0,str(ROOT))
    try:
        observer = host.load_local('bridge/diplomacy_effect_observer.py',initial)
    finally:
        sys.path.pop(0)
    backend = observer.TagCommandBackend()
    identity = dict(pid=80340,creation='01dd5c075fcf8c26',session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
    with observer.RuntimeCapture(identity,backend) as cap:
        held = cap.held
        window_tid = held.window_thread()
        kernel = held.kernel
        kernel.OpenThread.argtypes, kernel.OpenThread.restype = [W.DWORD,W.BOOL,W.DWORD],W.HANDLE
        kernel.GetProcessIdOfThread.argtypes, kernel.GetProcessIdOfThread.restype = [W.HANDLE],W.DWORD
        kernel.GetThreadTimes.argtypes = [W.HANDLE,*([C.POINTER(W.FILETIME)]*4)]
        kernel.GetThreadTimes.restype = W.BOOL
        handle = kernel.OpenThread(0x0800|0x00100000,False,tid)
        host.require(bool(handle),'Selected query-only thread unavailable')
        try:
            owner = kernel.GetProcessIdOfThread(handle)
            times = [W.FILETIME() for _ in range(4)]
            host.require(owner == identity['pid'] and kernel.GetThreadTimes(handle,
                *(C.byref(x) for x in times)), 'Selected thread owner/time differs')
            host.require(ft(times[1]) == 0 and kernel.WaitForSingleObject(handle,0) == 0x102,
                'Selected thread exited')
            held.identity_check()
            host.require(held.modules() == cap.modules and host.verify_manifest() == initial,
                'Process/modules/sources changed')
            created = ft(times[0])
        finally:
            kernel.CloseHandle(handle)
    start = datetime.fromisoformat(retained['captured_utc'])
    delta = start-datetime(1601,1,1,tzinfo=timezone.utc)
    start_ft = (delta.days*86400+delta.seconds)*10000000+delta.microseconds*10
    result = dict(schema='EU4-ENTRY-CURRENT-THREAD-IDENTITY/1',
        observed_utc=datetime.now(timezone.utc).isoformat(),
        source_pins={str(p.relative_to(ROOT)).replace('\\','/'):host.pin(p) for p in
            (HOST,CAPTURE,PAYLOAD,Path(__file__).resolve())},
        host_manifest_sha256=initial['manifest_sha256'],pid=80340,creation=identity['creation'],
        identity_purpose='Fresh query-only nonce, not TAG installation/request',
        observed_callback_tid=tid,current_visible_unowned_game_window_tid=window_tid,
        selected_current_thread_owner_pid=owner,selected_current_thread_creation=format(created,'016x'),
        selected_current_thread_alive=True,callback_tid_matches_current_window_thread=tid == window_tid,
        thread_creation_predates_capture_start=created <= start_ft,
        retained_capture_started_utc=retained['captured_utc'],
        retained_stack_or_heap_dereferenced=False,thread_suspended=False,thread_context_modified=False,
        Frida_called=False,native_game_calls=0,game_fields_written=0,requests_published=0,saves=0,reloads=0,
        historical_thread_interval_or_owner_lease_proven=False,native_ready=False,lifetime_lease=False,
        limitations=['Current query of one TID under the same held game process.',
            'Matching the current window thread and earlier creation time is not a world or object lease.',
            'Capture start is the host wall-clock timestamp, not an independent native event timestamp.'])
    host.write_new(OUT,result)
    print(json.dumps(dict(output=str(OUT),sha256=digest(OUT),tid=tid,
        window_tid=window_tid,matches=result['callback_tid_matches_current_window_thread'],
        predates=result['thread_creation_predates_capture_start'],native_ready=False)))


if __name__ == '__main__':
    main()
