"""Read current opposing-war graph by complete country identities; no sender."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.diplomacy_effect_observer import RuntimeCapture, BudgetReader, HeldRPMPort, roots, country, full_handle, pins
from bridge.tag_command_backend import TagCommandBackend, read, decode, digest, require
from bridge.war_peace_memory_observer_r2 import capture_war_pair

MANIFEST=ROOT/'work/reports/war-peace-api-20261015-r7-r2/observer/manifest.json'
MANIFEST_SHA='7f844951adb72c5843088f00172310642f9ef1f5efe12c1157b5260242227d8c'


def source_pins():
    raw=read(MANIFEST,65536)
    require(digest(raw)==MANIFEST_SHA,'Fixed R7 manifest differs')
    result={str(MANIFEST.relative_to(ROOT)):{'bytes':len(raw),'sha256':digest(raw)}}
    for row in decode(raw)['files']:
        relative=Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts,'Manifest path bound')
        data=read(ROOT/relative,4*1024*1024)
        require(len(data)==row['bytes'] and digest(data)==row['sha256'],'R7 candidate source differs')
        result[row['path']]={'bytes':len(data),'sha256':digest(data)}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--creation',required=True)
    p.add_argument('--actor',required=True)
    p.add_argument('--target',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    require(re.fullmatch('[A-Z0-9]{3}',a.actor) and re.fullmatch('[A-Z0-9]{3}',a.target) and a.actor!=a.target,'Distinct country tags required')
    require(not a.output.exists(),'Exclusive capture destination required')
    backend=TagCommandBackend()
    identity=dict(pid=a.pid,creation=a.creation,session=secrets.token_hex(16),
        dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
    initial=source_pins()
    started=time.perf_counter()
    with RuntimeCapture(identity,backend) as cap:
        require(not any(Path(path).name.lower().startswith(('eu4_tag_command_','eu4_bridge_','eu4_pair_','eu4_spy_','tag_diplomacy'))
            for _,path in cap.modules),'This standalone probe requires no research module')
        r=BudgetReader(HeldRPMPort(cap.held))
        root=roots(r,cap.base)
        require(root['manual_pause']==1,'Expected manually paused test checkpoint')
        raw=r.read(int(root['array'],16),root['count']*8)
        selected={}
        for address, in struct.iter_unpack('<Q',raw):
            if not address:continue
            handle=r.q(address+0x20)
            tag=(handle&0xffffff).to_bytes(3,'little')
            for name in (a.actor,a.target):
                if tag==name.encode('ascii'):
                    require(name not in selected,'Duplicate selected country tag')
                    full_handle(handle,root['count'],tag=name)
                    selected[name]=country(r,cap.base,root,handle,name)
        require(set(selected)=={a.actor,a.target},'Selected country unavailable')
        result=capture_war_pair(r,cap.base,root,selected[a.actor],selected[a.target])
        cap.held.identity_check()
        require(cap.held.modules()==cap.modules and pins()==cap.initial_pins,'Process modules/source changed')
        require(source_pins()==initial,'R7 source changed during capture')
        result.update(identity=identity,identity_purpose='Read-only observation nonce; not a TAG installation',
            native_session_installed=False,process_identity_authenticated_by_host=True,
            captured_utc=datetime.now(timezone.utc).isoformat(),source_pins=initial,
            host_source_pin={'bytes':Path(__file__).stat().st_size,'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            total_rpm_budget=dict(calls=r.calls,bytes=r.bytes,largest=r.largest),
            duration_ms=round((time.perf_counter()-started)*1000,3),saves_written=0,reloads=0)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    projection=result.get('projection') or {}
    print(json.dumps({k:result[k] for k in ('status','native_calls','runtime_effect_verified','two_pass_equal','duration_ms')} |
        {k:projection.get(k) for k in ('pair_state','global_war_count','physical_pair_indexes')} |
        {'failure':result.get('failure'),'output':str(a.output)}))
    return 0 if result['status']=='observed' else 2


if __name__=='__main__':
    raise SystemExit(main())
