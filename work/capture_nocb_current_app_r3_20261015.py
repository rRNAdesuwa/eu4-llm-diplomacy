"""Current application/server binding snapshot, outside any native callback."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT/'work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-registry-and-dispatch-r2.json'
PRODUCER=ROOT/'work/capture_nocb_registry_dispatch_r2_20261015.py'
OUT=ROOT/'work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-current-app-r3.json'
raw=PRIOR.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='c9ec7d7d8176d53008f00697d9fd224467fe22e937fce48cb910373df2ad0180'
expect=json.loads(raw)['source_pins'][PRODUCER.relative_to(ROOT).as_posix()]
code=PRODUCER.read_bytes()
assert {'bytes':len(code),'sha256':hashlib.sha256(code).hexdigest()}==expect
spec=importlib.util.spec_from_file_location('fixed_registry_dispatch_reader',PRODUCER)
prior=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
old=prior.old

SOURCES=(PRIOR,PRODUCER,ROOT/'work/reports/war-peace-api-20261015-r6-main-frame/war/manifest.json',
         ROOT/'work/reports/war-peace-api-20261015-r6-run-callback/war/manifest.json',Path(__file__).resolve())


def sources():
    result={}
    for p in SOURCES:
        b=p.read_bytes();result[p.relative_to(ROOT).as_posix()]={'bytes':len(b),'sha256':old.digest(b)}
    return result


def sample(reader,base):
    value=prior.sample(reader,base)
    app=int(value['application']['address'],16)
    fields=[]
    for name,offset in (('current',0x40),('pending',0x70),('previous',0x78)):
        b=reader.read(app+offset,8);q=struct.unpack('<Q',b)[0]
        fields.append({'name':name,'offset':hex(offset),'raw_hex':b.hex(),'address':hex(q)})
    current=int(fields[0]['address'],16)
    server=int(value['roots']['server'],16)
    typed=None
    if current:
        old.ptr(current)
        b=reader.read(current,0x10);vt=struct.unpack_from('<Q',b)[0]
        typed={'address':hex(current),'raw_header_hex':b.hex(),'vtable':hex(vt),
               'expected_server_type':vt==base+0x1cb8460,'update_slot_raw_hex':None,
               'update_target':None,'expected_update_target':False}
        if vt==base+0x1cb8460:
            slot=reader.read(vt+0x20,8);target=struct.unpack('<Q',slot)[0]
            typed.update(update_slot_raw_hex=slot.hex(),update_target=hex(target),
                         expected_update_target=target==base+0x8137c0)
    value['application_children']={'fields':fields,'current_typed_header':typed,
        'current_equals_game_server_pointer_value':current==server,
        'current_server_update_binding_matches_static_chain':bool(current==server and typed and
            typed['expected_server_type'] and typed['expected_update_target']),
        'fields_are_current_reads_not_native_stack_witness':True}
    old.require([reader.q(app+offset) for offset in (0x40,0x70,0x78)]==
        [int(f['address'],16) for f in fields], 'Application children changed during sample')
    old.require(reader.q(base+0x242bf50)==app and old.roots(reader,base)==value['roots'],
                'Current application or game roots changed')
    return value


def main():
    old.require(not OUT.exists(),'Exclusive output required')
    initial=sources();backend=old.TagCommandBackend()
    identity={'pid':80340,'creation':'01dd5c075fcf8c26','session':secrets.token_hex(16),
              'dll_sha256':backend.manifest['dll']['sha256'],'manifest_sha256':backend.manifest_sha}
    started=time.perf_counter()
    with old.RuntimeCapture(identity,backend) as cap:
        old.require(not any(Path(p).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_',
            'eu4_tag_command_','tag_diplomacy')) for _,p in cap.modules),'Unexpected research module')
        reader=old.BudgetReader(old.HeldRPMPort(cap.held))
        first,second=sample(reader,cap.base),sample(reader,cap.base)
        old.require(first==second,'Two complete current-app snapshots differ')
        cap.held.identity_check()
        old.require(cap.held.modules()==cap.modules and old.pins()==cap.initial_pins and sources()==initial,
                    'Modules or frozen sources changed')
        base=cap.base
    data={'schema':'EU4-NOCB-CURRENT-APP-READONLY/3','captured_utc':datetime.now(timezone.utc).isoformat(),
          'identity':identity,'identity_purpose':'Fresh read-only nonce, not TAG installation/request',
          'base':hex(base),'source_pins':initial,'observer_source_pins':cap.initial_pins,'samples':[first,second],
          'two_pass_equal':True,'duration_ms_including_host_and_source_checks':round((time.perf_counter()-started)*1000,3),
          'rpm_budget':{'calls':reader.calls,'bytes':reader.bytes,'largest_read':reader.largest},
          'current_application_binding_only':True,'native_callback_observed':False,'native_stack_sampled':False,
          'callback_thread_identity_proved':False,'native_lifetime_authority':False,'native_ready':False,
          'native_calls':0,'requests_published':0,'memory_written':False,'injection_performed':False,
          'hooks_installed':0,'saves_written':0,'reloads':0,'new_API_effect_tested':False}
    with OUT.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(OUT),'sha256':old.digest(OUT.read_bytes()),'two_pass_equal':True,
        'current_server_update_binding_matches_static_chain':first['application_children']['current_server_update_binding_matches_static_chain'],
        'application_children':first['application_children']['fields'],'rpm_budget':data['rpm_budget'],
        'duration_ms':data['duration_ms_including_host_and_source_checks'],'native_ready':False}))


if __name__=='__main__':main()
