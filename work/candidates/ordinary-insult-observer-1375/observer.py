"""Selected ordinary-insult state, bounded read-only two-pass candidate.

No native call, lazy getter, process write, request, injection or automatic probe.
The explicit sample CLI is for a later separately reviewed read-only experiment.
"""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from work import probe_diplomacy_current as legacy

PROFILE='ordinary_insult_selected_state_1375_1'
CONTRACT_SHA='f6def89824c7aefb18c6b2674e77383440851f05de049e3007917f559c42f3ff'
MAX_REPORT=2*1024*1024
MAX_SINGLE=65536
MAX_TOTAL=1048576
MAX_READS=8192
MAX_SLOTS=4096
MAX_MODIFIERS=256
HANDLES={'FRA':0x0100007a00415246,'ENG':0x0100002e00474e45,'POR':0x010000bd00524f50,
         'NAV':0x010000bc0056414e,'FOI':0x0100007900494f46}
FALSE_CLAIMS=('runtime_verified','production_ready','rejection_observed','execution_verified','request_causality_verified','ai_acceptance_verified',
              'world_epoch_verified','whole_world_unchanged_verified','strict_single_player_verified','paused_verified')
LIMITATIONS=[
 'Two matching bounded passes are not atomic; ABA reuse or intervening changes may escape observation.',
 'This selected modifier/trust difference is not request causality, AI acceptance, rejection or production execution proof.',
 'Same roots, dates and full handles do not establish a reliable world epoch.',
 'Unknown objects, missing caches, unstable or unreadable state never imply diplomatic rejection.',
 'Only a newly present ordinary insulted modifier and target trust decrease are matched; refresh/stacking remains unsupported.',
 'Calendar expiry conversion, casus-belli changes and save-container persistence are not matched.',
 'Loaded selected code pins and PE identity are checked; the complete in-memory executable is not hashed.',
]

def require(ok,message):
    if not ok: raise legacy.ProbeError(message)

def integer(value,lo=0,hi=0xffffffff):
    require(type(value) is int and lo<=value<=hi,'Invalid strict bounded integer')
    return value

def pointer(value,nullable=False):
    integer(value,0,0x7fffffffffff)
    if value==0 and nullable:return 0
    require(value>=0x10000 and value%8==0,'Invalid aligned object pointer')
    return value

def addr(value,nullable=False):
    require(type(value) is str and re.fullmatch(r'0x[0-9a-f]+',value) is not None,'Noncanonical pointer string')
    result=int(value,16);require(value==hex(result),'Noncanonical pointer encoding')
    return pointer(result,nullable)

def exact(value,keys):
    require(type(value) is dict and set(value)==set(keys.split()),'Missing or unexpected fields')

def canonical(value):
    # JSON text distinguishes int, bool and float. Non-JSON values cannot hide
    # inside ignored metadata, and each recognized field is also validated.
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError) as exc:raise legacy.ProbeError('Non-JSON evidence') from exc

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while data:=f.read(1024*1024):h.update(data)
    return h.hexdigest()

def load_contract():
    p=HERE/'contract.json';require(0<p.stat().st_size<65536,'Contract size')
    raw=p.read_bytes();require(hashlib.sha256(raw).hexdigest()==CONTRACT_SHA,'Contract changed')
    x=json.loads(raw)
    require(digest(HERE/'report.json')==x['report_sha256'],'Static report changed')
    for name,row in x['dependencies'].items():
        p=ROOT/name;require(p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],'Dependency changed: '+name)
    return x

class Budget:
    def __init__(self,reader):self.reader=reader;self.bytes=0;self.calls=0
    def read(self,location,size):
        integer(location,0x10000,0x7fffffffffff);integer(size,1,MAX_SINGLE)
        require(location+size<=0x800000000000,'Read endpoint overflow')
        require(self.bytes+size<=MAX_TOTAL and self.calls<MAX_READS,'Read budget exceeded')
        self.bytes+=size;self.calls+=1
        raw=self.reader.read(location,size)
        require(type(raw) is bytes and len(raw)==size,'Short or missing read')
        return raw
    def q(self,p):return struct.unpack('<Q',self.read(p,8))[0]
    def i(self,p):return struct.unpack('<i',self.read(p,4))[0]
    def b(self,p):return self.read(p,1)[0]

def code_pins(reader,module,contract):
    for row in contract['instruction_pins']:
        raw=bytes.fromhex(row['bytes'])
        require(reader.read(module+int(row['rva'],16),len(raw))==raw,'Loaded instruction pin changed')

def read_name(reader,location):
    raw=reader.read(location,32);length,capacity=struct.unpack_from('<QQ',raw,16)
    require(0<length<=128 and length<=capacity<=4096,'String length/capacity out of bounds')
    if capacity<16:
        require(length<16,'Bad inline string');data=raw[:16];storage=location
    else:
        storage=pointer(struct.unpack_from('<Q',raw)[0]);data=reader.read(storage,length+1)
    require(data[length]==0,'Unterminated string')
    try:text=data[:length].decode('ascii')
    except UnicodeError as exc:raise legacy.ProbeError('Non-ASCII definition name') from exc
    require(re.fullmatch('[a-z][a-z0-9_]{0,127}',text) is not None,'Invalid definition key')
    return {'location':hex(location),'storage':hex(storage),'length':length,'capacity':capacity,'text':text}

def validate_name(row,location):
    exact(row,'location storage length capacity text')
    require(addr(row['location'])==location,'String location mismatch')
    length=integer(row['length'],1,128);capacity=integer(row['capacity'],length,4096)
    require(type(row['text']) is str and re.fullmatch('[a-z][a-z0-9_]{0,127}',row['text']) is not None
            and len(row['text'])==length,'Definition key/length mismatch')
    storage=addr(row['storage'])
    if capacity<16:require(length<16 and storage==location,'Inline name storage mismatch')

def country(reader,array,count,tag):
    h=HANDLES[tag];slot=(h>>32)&0xffff;require(slot<count,'Fixed country slot exceeds actual database count')
    p=pointer(reader.q(array+slot*8));require(reader.q(p+0x20)==h,'Full country identity mismatch')
    return {'tag':tag,'slot':slot,'address':hex(p),'handle':hex(h)}

def roots(reader,module,target):
    db=pointer(reader.q(module+0x233d8d0));game=pointer(reader.q(module+0x233fe78))
    array=pointer(reader.q(db+0x118));count=integer(reader.i(db+0x124),1,MAX_SLOTS)
    date=integer(reader.i(game+0x1dd0),1,0x7fffffff)
    require(reader.q(game+0x1e60)==HANDLES['FRA'],'Fixed player is not FRA')
    reset=reader.b(game+0x7485);load=reader.q(game+0x74c8)
    require(reset==0 and load==0,'Known reset/load boundary active')
    pair={tag:country(reader,array,count,tag) for tag in ('FRA',target)}
    require(pair['FRA']['address']!=pair[target]['address'],'Country pointer alias')
    return {'module_base':hex(module),'database':hex(db),'world':hex(game),'country_array':hex(array),
        'country_count':count,'raw_date':date,'player_handle':hex(HANDLES['FRA']),
        'world_reset_active':reset,'load_source':hex(load),'pair':pair}

def snapshot(reader,module,target):
    identity=roots(reader,module,target);actor=identity['pair']['FRA'];recipient=identity['pair'][target]
    registry=pointer(reader.q(module+0x233ff08));wrapper=registry+0x2f8
    definition=pointer(reader.q(wrapper))  # Null lazy cache is unsupported, never initialized here.
    definition_row={'registry':hex(registry),'wrapper':hex(wrapper),'pointer':hex(definition),
        'wrapper_name':read_name(reader,wrapper+8),'name':read_name(reader,definition+0x10),
        'opinion':reader.i(definition+0x50),'duration_months':reader.i(definition+0x54),
        'minimum':reader.i(definition+0x5c),'maximum':reader.i(definition+0x60)}
    records=pointer(reader.q(addr(recipient['address'])+0x1510));record=records+actor['slot']*0x48
    header=reader.read(record,0x20);manager=pointer(struct.unpack_from('<Q',header)[0])
    owner,counterpart=struct.unpack_from('<QQ',header,8)
    require(owner==HANDLES[target] and counterpart==HANDLES['FRA'],'Bilateral owner/counterpart mismatch')
    require(reader.q(manager+0x10)==addr(recipient['address']) and reader.q(manager+0x18)==records,'Manager owner/array mismatch')
    data=pointer(reader.q(manager+0x308),True);capacity=reader.i(manager+0x310);count=reader.i(manager+0x314)
    integer(capacity,0,MAX_SLOTS);integer(count,0,capacity);require(count==0 or data!=0,'Null outer array')
    selected=None
    if actor['slot']<count:
        at=data+actor['slot']*24;raw=reader.read(at,24)
        vt,inner,icap,icount=struct.unpack('<QQii',raw)
        require(vt==module+0x1c38348,'Wrong inner container vtable')
        integer(icap,0,MAX_MODIFIERS);integer(icount,0,icap);pointer(inner,True);require(icount==0 or inner!=0,'Null inner array')
        objects=[];seen=set()
        blob=reader.read(inner,icount*8) if icount else b''
        for index in range(icount):
            obj=pointer(struct.unpack_from('<Q',blob,index*8)[0]);require(obj not in seen,'Duplicate modifier object');seen.add(obj)
            head=reader.read(obj,0x10);vtable,kind=struct.unpack_from('<QI',head)
            row={'address':hex(obj),'vtable':hex(vtable),'type_marker':kind,'fields':None}
            if vtable==module+0x1ccf4f8 and kind==0x165:
                tail=reader.read(obj+0x10,0x18)
                d,expiry,multiplier,value=struct.unpack_from('<Qiii',tail)
                row['fields']={'definition':hex(pointer(d)),'expiry_raw_date':expiry,'multiplier':multiplier,
                               'value_milli':value,'flag24':tail[0x14],'flag25':tail[0x15],'flag26':tail[0x16]}
            objects.append(row)
        selected={'address':hex(at),'vtable':hex(vt),'data':hex(inner),'capacity':icap,'count':icount,'objects':objects}
    result={'identity':identity,'target':target,'definition':definition_row,
       'relation':{'records':hex(records),'record':hex(record),'manager':hex(manager),
          'owner_handle':hex(owner),'counterpart_handle':hex(counterpart),'trust':header[0x1e],
          'manager_owner':recipient['address'],'manager_records':hex(records),
          'outer_data':hex(data),'outer_capacity':capacity,'outer_count':count,'selected':selected}}
    require(canonical(roots(reader,module,target))==canonical(identity),'World/date/country identity changed during pass')
    inspect_snapshot(result)
    return result

def inspect_snapshot(sample):
    exact(sample,'identity target definition relation');target=sample['target'];require(target in HANDLES and target!='FRA','Wrong fixed target')
    ident=sample['identity'];exact(ident,'module_base database world country_array country_count raw_date player_handle world_reset_active load_source pair')
    module=addr(ident['module_base'])
    for key in ('database','world','country_array'):addr(ident[key])
    count=integer(ident['country_count'],1,MAX_SLOTS);date=integer(ident['raw_date'],1,0x7fffffff)
    require(ident['player_handle']==hex(HANDLES['FRA']),'Player identity mismatch')
    require(integer(ident['world_reset_active'],0,0)==0 and ident['load_source']=='0x0','Reset/load boundary')
    exact(ident['pair'],'FRA '+target)
    for tag in ('FRA',target):
        c=ident['pair'][tag];exact(c,'tag slot address handle');addr(c['address'])
        require(c['tag']==tag and c['handle']==hex(HANDLES[tag]) and integer(c['slot'],0,count-1)==(HANDLES[tag]>>32)&0xffff,'Country full identity mismatch')
    actor=ident['pair']['FRA'];recipient=ident['pair'][target]
    require(actor['address']!=recipient['address'],'Country alias')
    definition=sample['definition'];exact(definition,'registry wrapper pointer wrapper_name name opinion duration_months minimum maximum')
    registry=addr(definition['registry']);d=addr(definition['pointer'])
    require(addr(definition['wrapper'])==registry+0x2f8,'Definition registry wrapper mismatch')
    validate_name(definition['wrapper_name'],registry+0x300);validate_name(definition['name'],d+0x10)
    require(definition['name']['text']==definition['wrapper_name']['text']=='insulted','Not the ordinary insulted definition')
    for key in ('opinion','duration_months','minimum','maximum'):integer(definition[key],-0x80000000,0x7fffffff)
    require(definition['opinion']==-50 and definition['duration_months']==120 and definition['maximum']==0
            and -1000000<=definition['minimum']<=-50,'Runtime definition differs from selected base-profile semantics')
    rel=sample['relation'];exact(rel,'records record manager owner_handle counterpart_handle trust manager_owner manager_records outer_data outer_capacity outer_count selected')
    records=addr(rel['records']);addr(rel['manager'])
    require(addr(rel['record'])==records+actor['slot']*0x48,'Bilateral record arithmetic')
    require(rel['owner_handle']==hex(HANDLES[target]) and rel['counterpart_handle']==hex(HANDLES['FRA']),'Reversed or wrong full handle')
    require(rel['manager_owner']==recipient['address'] and rel['manager_records']==rel['records'],'Manager owner/records differ')
    integer(rel['trust'],0,100);capacity=integer(rel['outer_capacity'],0,MAX_SLOTS);outer_count=integer(rel['outer_count'],0,capacity)
    outer=addr(rel['outer_data'],True);require(outer_count==0 or outer!=0,'Null outer data')
    selected=rel['selected']
    if actor['slot']>=outer_count:
        require(selected is None,'Out-of-range slot cannot claim observed container')
        return {'status':'unsupported_unmaterialized_container','trust':rel['trust'],'modifier':None}
    exact(selected,'address vtable data capacity count objects')
    require(addr(selected['address'])==outer+actor['slot']*24 and addr(selected['vtable'])==module+0x1c38348,'Inner container address/vtable differs')
    capacity=integer(selected['capacity'],0,MAX_MODIFIERS);n=integer(selected['count'],0,capacity);data=addr(selected['data'],True)
    require(n==0 or data!=0,'Null modifier array');objects=selected['objects'];require(type(objects) is list and len(objects)==n,'Object count mismatch')
    seen=set();matches=[];unknown=False
    for row in objects:
        exact(row,'address vtable type_marker fields');p=addr(row['address']);require(p not in seen,'Duplicate object');seen.add(p)
        v=addr(row['vtable']);kind=integer(row['type_marker']);f=row['fields']
        if v!=module+0x1ccf4f8 or kind!=0x165:
            require(f is None,'Unknown dynamic object was followed');unknown=True;continue
        exact(f,'definition expiry_raw_date multiplier value_milli flag24 flag25 flag26');ptr=addr(f['definition'])
        integer(f['expiry_raw_date'],-0x80000000,0x7fffffff);integer(f['multiplier'],1,0x7fffffff);integer(f['value_milli'],-0x80000000,0x7fffffff)
        for key in ('flag24','flag25','flag26'):integer(f[key],0,1)
        if ptr==d:matches.append(row)
    require(len(matches)<=1,'Ambiguous duplicate insulted modifiers')
    if unknown:return {'status':'unsupported_unknown_modifier_class','trust':rel['trust'],'modifier':None}
    return {'status':'present' if matches else 'absent','trust':rel['trust'],'modifier':matches[0] if matches else None}

def capture(reader,module,target,contract=None):
    require(target in HANDLES and target!='FRA','Unsupported target');pointer(module)
    contract=contract or load_contract();r=Budget(reader);code_pins(r,module,contract)
    passes=[]
    for sequence in range(2):
        start=time.monotonic_ns();value=snapshot(r,module,target);end=time.monotonic_ns()
        passes.append({'sequence':sequence,'started_monotonic_ns':start,'ended_monotonic_ns':end,'snapshot':value})
    require(canonical(passes[0]['snapshot'])==canonical(passes[1]['snapshot']),'Selected fields changed between passes')
    code_pins(r,module,contract)
    return {'passes':passes,'state':inspect_snapshot(passes[0]['snapshot']),
            'budget':{'bytes':r.bytes,'calls':r.calls,'maximum_single':MAX_SINGLE,'maximum_total':MAX_TOTAL,'maximum_calls':MAX_READS}}

def held_identity(reader,pid,creation):
    k=reader.kernel;k.GetProcessId.argtypes=[W.HANDLE];k.GetProcessId.restype=W.DWORD
    k.GetProcessTimes.argtypes=[W.HANDLE]+[C.POINTER(W.FILETIME)]*4;k.GetProcessTimes.restype=W.BOOL
    require(k.GetProcessId(reader.handle)==pid,'Held PID differs')
    times=[W.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(reader.handle,*(C.byref(v) for v in times)):raise C.WinError(C.get_last_error())
    values=[v.dwHighDateTime<<32|v.dwLowDateTime for v in times]
    require(values[0]==creation and values[1]==0,'Held process creation differs or exited')
    return {'pid':pid,'creation_filetime':values[0],'exit_filetime':0,'module_base':hex(reader.base)}

def wrap(observation,source):
    return {'schema_version':1,'profile':PROFILE,'contract_sha256':CONTRACT_SHA,'read_only':True,
        'atomic_snapshot':False,**{k:False for k in FALSE_CLAIMS},'source':source,'observation':observation,'limitations':LIMITATIONS}

def sample_process(pid,creation,executable,target):
    """Explicit future read-only entry. This candidate is tested with mocked handles only."""
    integer(pid,1);require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)>0,'Canonical full creation required')
    require(target in HANDLES and target!='FRA','Unsupported target');contract=load_contract()
    executable=Path(executable).resolve();require(executable==(ROOT.parent/'eu4.exe').resolve(),'Wrong executable path')
    require(digest(executable)==contract['exe_sha256'],'Full executable SHA differs')
    _,signature=legacy.verified_executable(executable);require(canonical(signature)==canonical(contract['pe_signature']),'Disk PE differs')
    reader=legacy.ProcessReader(pid,executable,signature)
    try:
        before=held_identity(reader,pid,int(creation,16));observation=capture(reader,reader.base,target,contract)
        after=held_identity(reader,pid,int(creation,16));require(canonical(before)==canonical(after),'Held identity changed')
        legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature)
        require(digest(executable)==contract['exe_sha256'],'Executable changed while reading')
        report=wrap(observation,{'kind':'held_process_readonly','before':before,'after':after,
            'exe_sha256':contract['exe_sha256'],'module_signature':signature,'expected_creation':creation,
            'rights':['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'],'loaded_full_image_hash_verified':False})
        validated_report(report);return report
    finally:reader.close()

def validated_report(report):
    contract=load_contract()
    exact(report,'schema_version profile contract_sha256 read_only atomic_snapshot source observation limitations '+' '.join(FALSE_CLAIMS))
    require(integer(report['schema_version'],1,1)==1 and report['profile']==PROFILE and report['contract_sha256']==CONTRACT_SHA,'Profile mismatch')
    require(report['read_only'] is True and report['atomic_snapshot'] is False and all(report[k] is False for k in FALSE_CLAIMS),'Overstated observation')
    require(canonical(report['limitations'])==canonical(LIMITATIONS),'Limitations differ')
    source=report['source'];exact(source,'kind before after exe_sha256 module_signature expected_creation rights loaded_full_image_hash_verified')
    require(source['kind']=='held_process_readonly' and source['exe_sha256']==contract['exe_sha256'],'Not held exact-build evidence')
    require(source['rights']==['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'] and source['loaded_full_image_hash_verified'] is False,'RO rights/proof differs')
    creation=source['expected_creation'];require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) is not None and int(creation,16)>0,'Invalid expected creation')
    exact(source['module_signature'],'timestamp size')
    for key,value in contract['pe_signature'].items():require(integer(source['module_signature'][key])==value,'PE signature differs')
    for key in ('before','after'):
        h=source[key];exact(h,'pid creation_filetime exit_filetime module_base')
        integer(h['pid'],1);require(integer(h['creation_filetime'],1,2**64-1)==int(creation,16),'Creation differs')
        integer(h['exit_filetime'],0,0);addr(h['module_base'])
    require(canonical(source['before'])==canonical(source['after']),'Held before/after identity differs')
    obs=report['observation'];exact(obs,'passes state budget');passes=obs['passes'];require(type(passes) is list and len(passes)==2,'Two complete passes required')
    states=[];previous_end=0
    for i,p in enumerate(passes):
        exact(p,'sequence started_monotonic_ns ended_monotonic_ns snapshot');require(integer(p['sequence'],i,i)==i,'Pass ordinal')
        start=integer(p['started_monotonic_ns'],1,2**64-1);end=integer(p['ended_monotonic_ns'],start,2**64-1)
        require(start>=previous_end,'Overlapping/reordered passes');previous_end=end
        states.append(inspect_snapshot(p['snapshot']))
        require(p['snapshot']['identity']['module_base']==source['before']['module_base'],'Module binding differs')
    require(canonical(passes[0]['snapshot'])==canonical(passes[1]['snapshot']),'Typed snapshots differ')
    require(canonical(states[0])==canonical(states[1])==canonical(obs['state']),'Stored state differs from each typed pass')
    budget=obs['budget'];exact(budget,'bytes calls maximum_single maximum_total maximum_calls')
    integer(budget['bytes'],1,MAX_TOTAL);integer(budget['calls'],1,MAX_READS)
    for key,value in (('maximum_single',MAX_SINGLE),('maximum_total',MAX_TOTAL),('maximum_calls',MAX_READS)):
        require(integer(budget[key],value,value)==value,'Budget changed')
    return passes[0]['snapshot'],states[0]

def compare_reports(before,after):
    result={'profile':PROFILE,'contract_sha256':CONTRACT_SHA,'status':'unknown','observed_effect':False,
        **{k:False for k in FALSE_CLAIMS},'errors':[],'limitations':LIMITATIONS}
    try:
        a,old=validated_report(before);b,new=validated_report(after)
        require(canonical(before['source'])==canonical(after['source']),'Different held process/build binding')
        require(canonical(a['identity'])==canonical(b['identity']) and a['target']==b['target'],'World/full handles or date changed')
        require(canonical(a['definition'])==canonical(b['definition']),'Runtime definition changed')
        for key in ('records','record','manager','owner_handle','counterpart_handle','manager_owner','manager_records'):
            require(a['relation'][key]==b['relation'][key],'Relation owner binding changed')
        require(before['observation']['passes'][-1]['ended_monotonic_ns']<=after['observation']['passes'][0]['started_monotonic_ns'],'Before/after order reversed')
        require(old['status']=='absent' and new['status']=='present','Only newly present ordinary modifier is supported')
        require(old['trust']>0 and new['trust']==max(0,old['trust']-5),'Matching target trust decrement absent')
        f=new['modifier']['fields'];date=b['identity']['raw_date']
        require(f['value_milli']==-50000 and f['multiplier']==1 and f['expiry_raw_date']>date
                and all(f[k]==0 for k in ('flag24','flag25','flag26')),'New ordinary modifier defaults differ')
        result.update(status='observed_selected_transition',observed_effect=True,target=b['target'],actor='FRA',
            trust_before=old['trust'],trust_after=new['trust'],modifier=new['modifier'],raw_date=date)
    except (legacy.ProbeError,KeyError,TypeError,ValueError) as exc:result['errors'].append(str(exc))
    return result

def read_report(path):
    path=Path(path);require(0<path.stat().st_size<=MAX_REPORT,'Report size budget')
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    with path.open('rb') as f:raw=f.read(MAX_REPORT+1)
    require(0<len(raw)<=MAX_REPORT,'Report grew beyond size budget')
    return json.loads(raw,object_pairs_hook=pairs),hashlib.sha256(raw).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('describe')
    s=sub.add_parser('sample');s.add_argument('--pid',required=True,type=int);s.add_argument('--creation',required=True)
    s.add_argument('--target',required=True,choices=tuple(x for x in HANDLES if x!='FRA'));s.add_argument('--exe',required=True,type=Path);s.add_argument('--output',required=True,type=Path)
    c=sub.add_parser('compare');c.add_argument('--before',required=True,type=Path);c.add_argument('--after',required=True,type=Path);c.add_argument('--output',required=True,type=Path)
    args=ap.parse_args()
    try:
        if args.command=='describe':print(json.dumps(load_contract()));return 0
        require(not args.output.exists() and args.output.suffix=='.json','CreateNew JSON output required')
        if args.command=='sample':result=sample_process(args.pid,args.creation,args.exe,args.target)
        else:
            a,ah=read_report(args.before);b,bh=read_report(args.after);result=compare_reports(a,b);result['input_hashes']={'before':ah,'after':bh}
        with args.output.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,indent=2);f.write('\n')
        print(json.dumps({'output':str(args.output),'observed_effect':result.get('observed_effect',False),'execution_verified':False}))
        return 0 if args.command=='sample' or result['observed_effect'] else 2
    except (OSError,ValueError,KeyError,TypeError,legacy.ProbeError) as exc:print(str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
