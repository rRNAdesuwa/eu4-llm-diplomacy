"""Explicit three-stage no-send research client. No automatic stage/retry loop.

Importing is file-only. Publishing requires the exact process creation, a fresh
source-bound owner health, and a permanent CREATE_NEW intent. The native owner
thread remains the final identity/world/TTL authority. Unknown publication is
never repeated. This is unrelated to the production diplomacy backend.
"""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
import sys
import build_manifest as b
import wire
import real_capture
import loader


def now_ms():
    require_windows();kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.GetTickCount64.restype=C.c_uint64;return kernel.GetTickCount64()


def require_windows():b.require(os.name=='nt' and C.sizeof(C.c_void_p)==8,'Windows x64 only')


def process_guard(identity):
    """Held query-only process identity; no game memory/native calls."""
    injector=loader.load_injector();kernel=injector._configure_kernel32()
    kernel.GetProcessTimes.argtypes=[W.HANDLE,*([C.POINTER(W.FILETIME)]*4)];kernel.GetProcessTimes.restype=W.BOOL
    handle=kernel.OpenProcess(0x1000|0x00100000,False,identity['pid'])
    if not handle:raise C.WinError(C.get_last_error())
    try:
        times=[W.FILETIME() for _ in range(4)]
        b.require(kernel.GetProcessTimes(handle,*[C.byref(x) for x in times]),'Missing exact creation')
        creation=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        b.require(f'{creation:016x}'==identity['creation'] and not times[1].dwHighDateTime and not times[1].dwLowDateTime,'Different/exited process')
        b.require(injector._canonical(injector._query_process_path(kernel,handle))==injector._canonical(injector.GAME),'Unexpected image')
        b.require(kernel.WaitForSingleObject(handle,0)==0x102,'Process exited')
        return kernel,handle
    except BaseException:kernel.CloseHandle(handle);raise


def proposed_request(status,identity,stage,now):
    b.require(stage in wire.p.STAGES and type(now)is int and 0<=now<=2**64-60001,'Fixed stage/time')
    b.require(status.get('source_manifest_verified') is True and status.get('source_bound_private_capture') is True,'Verified private capture required')
    b.require(b.exact(status.get('identity'),identity),'Exact requested identity')
    health=status['latest_health'];sequence=wire.p.STAGES.index(stage)+1
    b.require(health['event']=='health' and type(health['uptime_ms'])is int and 0<=now-health['uptime_ms']<=2500,'Fresh independently returned owner health')
    b.require(type(status['claimed_sequence'])is int and status['claimed_sequence']==sequence-1
              and type(status['completed_stages'])is int and status['completed_stages']==sequence-1
              and status['completed'] is False,'Only next explicit stage after later health')
    return dict(identity,purpose=wire.p.PURPOSE,game_sha256=wire.p.GAME_SHA256,profile=wire.p.PROFILE,
                sequence=sequence,expires=now+60000,stage=stage,actor='FRA',target='ENG',value=True,state=0,envoy=-1)


def publish(directory,identity,stage):
    require_windows();identity=wire.identity(identity);directory=b.no_links(directory).resolve()
    # The public entry has no injected observer or ACK callback.
    kernel,handle=process_guard(identity)
    try:
        status=real_capture.inspect(directory,identity)
        request=proposed_request(status,identity,stage,now_ms());raw=wire.p.encode(request)
        session=wire.session_path(directory,identity);sequence=request['sequence']
        intent=session/f'{sequence}.publisher-intent.json';temporary=session/f'{sequence}.publisher-pending';target=session/f'{sequence}.request'
        b.require(not target.exists() and not (session/f'{sequence}.claim').exists(),'Existing request/claim; never retry')
        record={'schema':'EU4SPYPUBLISH/1','identity':identity,'stage':stage,'sequence':sequence,'expires':request['expires'],
                'request_sha256':b.sha(raw),'request_bytes':len(raw),'before_outer_sha256':status['outer_sha256'],
                'before_raw_sha256':status['raw_sha256'],'no_send':True,'retry_allowed':False}
        loader.write_new(intent,b.canonical(record)+b'\n')
        # This invocation alone owns this permanent intent. It does not regard
        # its own file as a foreign rearm; all native state is revalidated.
        latest=real_capture.inspect(directory,identity)
        proposed_request(latest,identity,stage,now_ms())
        b.require(kernel.WaitForSingleObject(handle,0)==0x102 and now_ms()<request['expires'],'Process/TTL changed before publish')
        b.verify_build(directory)
        loader.write_new(temporary,raw)
        b.require(kernel.WaitForSingleObject(handle,0)==0x102 and now_ms()<request['expires'],'Process/TTL changed before atomic publication')
        # Windows rename is atomic and refuses an existing destination. Never
        # use replace/overwrite. The native handle/claim still decides acceptance.
        os.rename(temporary,target)
        return dict(record,request_written=True,native_result_unknown=True,production_ready=False)
    finally:kernel.CloseHandle(handle)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--creation',required=True);parser.add_argument('--session',required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('status');stage=commands.add_parser('stage');stage.add_argument('stage',choices=wire.p.STAGES)
    args=parser.parse_args(argv);manifest,manifest_sha=b.verify_build(args.build)
    identity=wire.identity(dict(pid=args.pid,creation=args.creation,session=args.session,dll_sha256=manifest['dll_sha256'],manifest_sha256=manifest_sha))
    result=real_capture.inspect(args.build,identity) if args.command=='status' else publish(args.build,identity,args.stage)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as exc:
        print(f'v18 no-send client refused: {exc}; no retry',file=sys.stderr);raise SystemExit(2)
