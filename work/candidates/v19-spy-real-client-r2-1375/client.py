"""One explicit fixed stage per invocation. Imports are file-only.
No automatic publication sequence, backend, unload, hot repair or retry.
"""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
import sys
from frozen import b,wire,files,verify_build,verify_sources,require,same,integer
import provenance
import readonly

def proposed(status,identity,stage,now):
    require(type(stage)is str and stage in wire.STAGES,'Only four fixed stages');integer(now,0,2**64-60001)
    same(status['identity'],identity)
    for name in ('source_bound_origin_verified','source_manifest_verified','build_loader_verified'):same(status[name],True)
    same(status['status'],'ready');same(status['preflight_ready'],True)
    sequence=wire.STAGES.index(stage)+1;same(status['next_sequence'],sequence);same(status['claimed_sequence'],sequence-1)
    same(status['authenticated_stages'],3 if sequence==4 else 0)
    integer(status['last_owner_uptime_ms'],0,now);require(now-status['last_owner_uptime_ms']<=2500,'Fresh logged successful owner/startup boundary')
    if sequence==4:require(status.get('startup_only') is not True and status['controller_frames']>=6,'Three later-health proofs')
    return sequence,now+60000

def write_new(path,raw):
    b.no_links(path)
    with Path(path).open('xb') as f:
        written=f.write(raw);require(written==len(raw),'Full durable write');f.flush();os.fsync(f.fileno())

def move_new(source,target):
    readonly.windows();k=C.WinDLL('kernel32',use_last_error=True)
    k.MoveFileExW.argtypes=[W.LPCWSTR,W.LPCWSTR,W.DWORD];k.MoveFileExW.restype=W.BOOL
    # WRITE_THROUGH only, deliberately no REPLACE_EXISTING flag.
    if not k.MoveFileExW(str(source),str(target),0x8):raise C.WinError(C.get_last_error())

class _Actual:
    inspect=staticmethod(provenance.inspect);now=staticmethod(readonly.now_ms)
    write=staticmethod(write_new);move=staticmethod(move_new);build=staticmethod(verify_build)

def _publish(directory,identity,stage,held,io):
    """Private orchestration seam for temp-file tests; CLI cannot replace it."""
    high_water=0
    def now():
        nonlocal high_water
        value=io.now();integer(value,high_water,2**64-60001);high_water=value;return value
    status=io.inspect(directory,identity);held.check(status,directory)
    prepared=now();sequence,expires=proposed(status,identity,stage,prepared);raw=wire.encode_request(identity,stage,expires)
    session=wire.session_path(directory,identity);intent=session/f'{sequence}.publisher-intent.json';temporary=session/f'{sequence}.publisher-pending';target=session/f'{sequence}.request'
    for p in (intent,temporary,target,session/f'{sequence}.claim'):require(not p.exists(),'Existing permanent intent/pending/request/claim; never retry')
    record=dict(schema='EU4SPYSENDPUBLISH/1',identity=identity,stage=stage,sequence=sequence,prepared_uptime_ms=prepared,expires=expires,request_sha256=b.sha(raw),request_bytes=len(raw),
                before_outer_sha256=status['outer_sha256'],before_raw_sha256=status['raw_sha256'],restricted_research_send=True,native_result_unknown=True,
                effect_verified=False,production_ready=False,retry_allowed=False)
    intentraw=b.canonical(record)+b'\n';io.write(intent,intentraw)
    # Only this invocation's newly created exact intent is present. No public
    # ignore-intent or override route exists; failures preserve all files.
    latest=io.inspect(directory,identity);held.check(latest,directory)
    same(proposed(latest,identity,stage,now())[0],sequence)
    require(files.read(intent,8192)==intentraw and not target.exists() and not (session/f'{sequence}.claim').exists(),'Own permanent intent/state changed')
    io.build(directory);require(now()<expires,'Expired before pending file')
    io.write(temporary,raw)
    latest=io.inspect(directory,identity);held.check(latest,directory)
    same(proposed(latest,identity,stage,now())[0],sequence)
    require(files.read(intent,8192)==intentraw and files.read(temporary,1024)==raw and not target.exists() and not (session/f'{sequence}.claim').exists(),'Publication files/state changed')
    require(now()<expires,'Expired before final held identity');held.identity_check()
    final_now=now();same(proposed(latest,identity,stage,final_now)[0],sequence)
    require(final_now<expires,'Expired after final held identity')
    io.move(temporary,target)
    return dict(record,request_written=True,publication_returned=True,native_result=None)

def publish(directory,identity,stage):
    readonly.windows();verify_sources();identity=wire.identity(identity);verify_build(directory)
    held=readonly.Held(identity)
    try:return _publish(Path(directory).resolve(),identity,stage,held,_Actual())
    finally:held.close()

def status(directory,identity,complete=False):
    readonly.windows();verify_sources();held=readonly.Held(identity)
    try:
        value=provenance.inspect(directory,identity,complete);value['live_guard']=held.check(value,directory)
        now=readonly.now_ms();integer(value['last_owner_uptime_ms'],0,now);require(now-value['last_owner_uptime_ms']<=2500,'Fresh live status boundary')
        value['live_identity_verified']=True;return value
    finally:held.close()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--pid',type=int,required=True);p.add_argument('--creation',required=True);p.add_argument('--session',required=True)
    sub=p.add_subparsers(dest='command',required=True);s=sub.add_parser('status');s.add_argument('--complete',action='store_true');stage=sub.add_parser('stage');stage.add_argument('stage',choices=wire.STAGES);stage.add_argument('--ack-disposable-research-send',action='store_true',required=True)
    a=p.parse_args(argv);manifest,digest=verify_build(a.build)
    identity=wire.identity(dict(pid=a.pid,creation=a.creation,session=a.session,dll_sha256=manifest['dll_sha256'],manifest_sha256=digest))
    value=status(a.build,identity,a.complete) if a.command=='status' else publish(a.build,identity,a.stage)
    print(json.dumps(value,sort_keys=True));return 0
if __name__=='__main__':
    raise SystemExit('Untrusted library entry: use the reviewed isolated launcher.py')
