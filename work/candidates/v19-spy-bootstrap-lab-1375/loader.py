"""Explicit restricted v19 research loader. Importing never opens a process.

Candidate author tests must not invoke main. No stage request is published by
this loader. Duplicate/unknown installation is never retried or unloaded.
"""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import importlib.util
import json
import os
import secrets
import sys

import build_manifest as build
import wire


def load_injector():
    # Verify dependency bytes before ordinary imports, then require their exact
    # origins. These modules' native entrypoints are not run by importing them.
    pins=build.json_value(build.bounded(build.HERE/'predecessor-pins-r2.json',128*1024))
    for name in ('work/native/inject_probe.py','work/probe_native_state.py','work/local_config.py'):
        data=build.bounded(build.ROOT/name,2*1024*1024)
        build.require(name in pins and pins[name]=={'bytes':len(data),'sha256':build.sha(data)},'Pinned loader dependency changed')
    sys.path.insert(0,str(build.ROOT/'work'));sys.path.insert(0,str(build.ROOT/'work/native'))
    import inject_probe
    import probe_native_state
    import local_config
    for module,name in ((inject_probe,'work/native/inject_probe.py'),(probe_native_state,'work/probe_native_state.py'),(local_config,'work/local_config.py')):
        build.require(Path(module.__file__).resolve()==(build.ROOT/name).resolve(),'Foreign cached loader module')
    return inject_probe


def write_new(path,data):
    build.no_links(path)
    with Path(path).open('xb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def held_identity(injector,pid,creation):
    kernel=injector._configure_kernel32()
    kernel.GetProcessTimes.argtypes=[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)]
    kernel.GetProcessTimes.restype=W.BOOL
    handle=kernel.OpenProcess(0x1000|0x0400|0x0010|0x00100000,False,pid)
    if not handle:raise C.WinError(C.get_last_error())
    try:
        path=injector._query_process_path(kernel,handle)
        build.require(injector._canonical(path)==injector._canonical(injector.GAME),'Wrong executable path')
        fields=[W.FILETIME() for _ in range(4)]
        build.require(kernel.GetProcessTimes(handle,*[C.byref(f) for f in fields]),'Process identity unavailable')
        actual=(fields[0].dwHighDateTime<<32)|fields[0].dwLowDateTime
        build.require(f'{actual:016x}'==creation and not fields[1].dwHighDateTime and not fields[1].dwLowDateTime,'Wrong/exited process creation')
        build.require(kernel.WaitForSingleObject(handle,0)==0x102,'Process no longer alive')
        modules=injector._enum_modules(kernel,handle)
        build.require(not any(Path(m.path).name.casefold().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_')) for m in modules),'A research bridge is already present; never hot replace')
        return kernel,handle,path
    except BaseException:
        kernel.CloseHandle(handle);raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--creation',required=True)
    parser.add_argument('--ack-disposable-test',action='store_true',required=True)
    parser.add_argument('--plan-only',action='store_true')
    args=parser.parse_args(argv)
    manifest,manifest_sha=build.verify_build(args.build)
    identity=wire.identity(dict(pid=args.pid,creation=args.creation,session=secrets.token_hex(16),
        dll_sha256=manifest['dll_sha256'],manifest_sha256=manifest_sha))
    packet=wire.encode_boot(identity)
    packet_path=args.build/f'bootstrap-{args.pid}-{args.creation}.request'
    build.require(not packet_path.exists(),'Permanent bootstrap already exists; do not retry this process')
    injector=load_injector();injector._require_windows_x64();injector._verify_game_build(build.GAME_SHA)
    kernel,handle,process_path=held_identity(injector,args.pid,args.creation)
    try:
        report={'schema':'EU4SPYSENDLOAD/1','purpose':build.PURPOSE,'identity':identity,'process_path':process_path,
            'plan_only':args.plan_only,'disposable_test_premise':True,'strict_sp_verified':False,'world_epoch_verified':False,
            'production_ready':False,'automatic_stage':False,'restricted_research_send':True,'stage_request_written':False,
            'bootstrap_sha256':build.sha(packet),'bootstrap_bytes':len(packet)}
        if not args.plan_only:
            # Loader owns this exact permanent file; it is not a stage request.
            write_new(packet_path,packet)
            build.verify_build(args.build)
            build.require(kernel.WaitForSingleObject(handle,0)==0x102,'Process exited before bootstrap')
            call=argparse.Namespace(pid=args.pid,dll=str((args.build/build.DLL).resolve()),timeout_ms=10000,ack_test_save=True)
            report['installation']=injector._run(call,expected_game_hash=build.GAME_SHA)
            build.require(kernel.WaitForSingleObject(handle,0)==0x102,'Process exited during bootstrap')
            report['held_identity_checked_after']=True
        name=f'loader-{args.pid}-{args.creation}'+('-plan.json' if args.plan_only else '.json')
        write_new(args.build/name,(json.dumps(report,sort_keys=True,indent=2)+'\n').encode('ascii'))
        print(json.dumps(report,sort_keys=True));return 0
    finally:
        kernel.CloseHandle(handle)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as exc:
        print(f'v19 restricted loader refused: {exc}; no retry/unload was attempted',file=sys.stderr);raise SystemExit(2)
