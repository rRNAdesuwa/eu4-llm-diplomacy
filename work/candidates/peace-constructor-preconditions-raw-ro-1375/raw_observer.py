"""Bounded raw-memory reader, with no native calls or constructor authorization.

capture() accepts a read-only reader. sample_process() is an explicit future
entrypoint; importing this module never opens a process. There is no live CLI.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PINS_SHA='e468636ad6d210304112382a5ef44627411caa146e10a63fd55cb41943cf939c'
MAX_TOTAL=16*1024*1024
MAX_READ=64*1024
MAX_READS=8192


class ReadError(ValueError): pass


def require(test,message):
    if not test: raise ReadError(message)


def integer(value,low,high,name):
    require(type(value) is int and low<=value<=high,name+': exact bounded integer required')
    return value


def ptr(value,nullable=False):
    require(type(value) is int,'Pointer must be an exact integer')
    if value==0 and nullable:return None
    integer(value,0x10000,0x7fffffffffff,'pointer')
    require(value%8==0,'Misaligned pointer')
    return value


def hx(value): return None if value is None or value==0 else hex(value)


def request_arguments(actor,recipient,direction):
    require(type(direction) is str and direction in ('demand','concede'),'Invalid direction')
    slots=[]
    for value in (actor,recipient):
        integer(value,1,2**64-1,'Full handle')
        slot=(value>>32)&0xffff;tag=(value&0xffffff).to_bytes(3,'little')
        require(value>>48!=0 and slot<4096 and all(65<=b<=90 for b in tag),'Full handle/TAG/slot invalid')
        slots.append(slot)
    require(slots[0]!=slots[1],'Actor and recipient must be different slots')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(262144),b''):h.update(block)
    return h.hexdigest()


def load_pins():
    require(sha(HERE/'pins.json')==PINS_SHA,'Raw producer pins changed')
    pins=json.loads((HERE/'pins.json').read_bytes())
    for name,digest in pins['inputs'].items():require(sha(ROOT/name)==digest,'Pinned source changed: '+name)
    return pins


class Budget:
    def __init__(self,reader): self.reader=reader;self.bytes=0;self.trace=[]
    def read(self,address,size,label):
        integer(address,0x10000,0x7fffffffffff,'read address');integer(size,1,MAX_READ,'read size')
        require(address+size<=0x800000000000,'Read end overflow')
        require(self.bytes+size<=MAX_TOTAL and len(self.trace)<MAX_READS,'Read budget exceeded')
        self.bytes+=size
        blob=self.reader.read(address,size)
        require(type(blob) is bytes and len(blob)==size,'Missing/short raw memory: '+label)
        self.trace.append({'address':hex(address),'width':size,'label':label,'sha256':hashlib.sha256(blob).hexdigest()})
        return blob
    def q(self,address,label):return struct.unpack('<Q',self.read(address,8,label))[0]
    def i(self,address,label):return struct.unpack('<i',self.read(address,4,label))[0]
    def u(self,address,label):return struct.unpack('<I',self.read(address,4,label))[0]
    def b(self,address,label):return self.read(address,1,label)[0]


class Walker:
    def __init__(self,budget,base,pins):
        self.r=budget;self.base=ptr(base);self.pins=pins;self.size=pins['pe']['image_size'];self.aliases={}
    def global_ptr(self,rva,name):return ptr(self.r.q(self.base+rva,name),True)
    def section(self,address,width):
        offset=address-self.base
        return next((s for s in self.pins['sections'] if s['rva']<=offset and offset+width<=s['rva']+s['size']),None)
    def verify_pins(self):
        for row in self.pins['instruction_pins']:
            raw=bytes.fromhex(row['bytes']);require(self.r.read(self.base+int(row['rva'],16),len(raw),'code pin '+row['rva'])==raw,'Loaded instruction pin differs')
        for slot,row in self.pins['take_colony_vtable']['slots'].items():
            require(self.r.q(self.base+int(row['cell_rva'],16),'goal vtable '+slot)==self.base+int(row['method_rva'],16),'Loaded goal method differs')
    def vtable(self,obj,condition=False):
        value=self.r.q(ptr(obj),'object vtable');ptr(value)
        section=self.section(value,0x38 if condition else 8)
        in_ro=section is not None and section['flags']&0x40000000 and not section['flags']&0xa0000000
        result={'pointer':hex(value),'rva':hex(value-self.base) if section else None,'class_status':'unreviewed_dynamic_class','method30_rva':None}
        if condition and in_ro:
            method=self.r.q(value+0x30,'condition virtual30 address');code=self.section(method,1)
            if code and code['flags']&0x20000000:result['method30_rva']=hex(method-self.base)
            else:result['class_status']='unsupported_method_outside_exact_executable_sections'
        elif condition:result['class_status']='unsupported_vtable_outside_readonly_module_section'
        return result
    def roots(self):
        db=ptr(self.global_ptr(0x233d8d0,'database global'));game=ptr(self.global_ptr(0x233fe78,'game global'))
        array=ptr(self.r.q(db+0x118,'country array'));count=self.r.i(db+0x124,'country pointer-vector signed count')
        integer(count,1,4096,'Country count');date=self.r.i(game+0x1dd0,'current raw date');integer(date,1,2**31-1,'date')
        return {'database':hex(db),'game':hex(game),'country_array':hex(array),'country_count':count,'raw_date':date}
    def handle(self,value,count):
        integer(value,1,2**64-1,'full country handle');slot=(value>>32)&0xffff
        require(slot<0x8000 and slot<count and value>>48!=0,'Stale/bare/out-of-range country handle')
        tag=(value&0xffffff).to_bytes(3,'little');require(all(65<=b<=90 for b in tag),'Invalid handle tag')
        return slot,tag.decode()
    def country(self,roots,handle):
        slot,tag=self.handle(handle,roots['country_count']);array=int(roots['country_array'],16)
        country=ptr(self.r.q(array+slot*8,'country slot pointer'))
        require(self.r.q(country+0x20,'country complete handle')==handle,'Country full identity mismatch')
        return {'handle':f'0x{handle:016x}','slot':slot,'tag':tag,'pointer':hex(country)}
    def variant(self,address):
        value=ptr(self.r.q(address,'government variant pointer'),True)
        if value is None:return {'field_address':hex(address),'pointer':None,'status':'null_native_default_branch_not_reproduced'}
        kind=self.r.i(value,'government variant signed type')
        row={'field_address':hex(address),'pointer':hex(value),'raw_type':kind,'status':'unreviewed_variant_type','storage_byte':None}
        if kind in (0,-1):
            row['storage_byte']=self.r.b(value+8,'government bool variant byte')
            row['status']='recognized_bool_representation' if row['storage_byte'] in (0,1) else 'noncanonical_bool_byte'
        identity=(row['raw_type'],row['storage_byte']);prior=self.aliases.setdefault(('variant',value),identity)
        require(prior==identity,'Aliased variant bytes changed')
        return row
    def government(self,country):
        address=int(country['pointer'],16);instance=ptr(self.r.q(address+0x1420,'country government instance'),True)
        if instance is None:return {'instance':None,'status':'missing_instance_no_getter_called','definition':None,'variants':None,'vtable':None}
        result={'instance':hex(instance),'status':'direct_fields_only_dynamic_class_unreviewed','definition':hx(ptr(self.r.q(instance+0x10,'government definition'),True)),
            'vtable':self.vtable(instance),'variants':{'0x170':self.variant(instance+0x170),'0x110':self.variant(instance+0x110)}}
        comparable={k:v for k,v in result.items() if k!='instance'}
        prior=self.aliases.setdefault(('government',instance),comparable);require(prior==comparable,'Aliased government has inconsistent fields')
        return result
    def relation(self,roots,owner,other):
        table=ptr(self.r.q(int(owner['pointer'],16)+0x1510,'country relation table'));record=table+other['slot']*0x48
        root=ptr(self.r.q(record,'relation root'));counter=self.r.q(record+0x10,'relation counterpart full handle')
        require(counter==int(other['handle'],16),'Relation counterpart full identity differs')
        data=ptr(self.r.q(root+0x50,'war index pointer'),True);count=self.r.i(root+0x5c,'war index signed count');integer(count,0,64,'war index count')
        require(count==0 or data is not None,'Nonempty index has null data')
        rows=[];keys=set();matches=[]
        if count:
            blob=self.r.read(data,count*16,'complete bounded war index')
            for offset in range(0,len(blob),16):
                key,war=struct.unpack_from('<i4xQ',blob,offset);integer(key,0,roots['country_count']-1,'war index key')
                require(key not in keys,'Ambiguous duplicate war-index key');keys.add(key);ptr(war)
                rows.append({'country_slot':key,'war_pointer':hex(war)})
                if key==other['slot']:matches.append(war)
        return {'owner_handle':owner['handle'],'counterpart_handle':other['handle'],'root':hex(root),'data':hx(data),'count':count,'entries':rows},(matches[0] if matches else None)
    def side(self,war,offset,count):
        begin,end=struct.unpack('<QQ',self.r.read(war+offset,16,'war side vector bounds'))
        ptr(begin);ptr(end);require(end>=begin and (end-begin)%8==0 and 1<=(end-begin)//8<=64,'Nonempty bounded war side required')
        handles=list(struct.unpack('<'+'Q'*((end-begin)//8),self.r.read(begin,end-begin,'complete war side full handles')))
        for value in handles:self.handle(value,count)
        require(len(handles)==len(set(handles)),'Duplicate side member')
        return {'begin':hex(begin),'end':hex(end),'handles':[f'0x{x:016x}' for x in handles]},handles
    def conditions(self,owner,offset):
        data=ptr(self.r.q(owner+offset+8,'conditions data'),True);count=self.r.i(owner+offset+0x14,'conditions signed count');integer(count,0,64,'conditions count')
        require(count==0 or data is not None,'Nonempty conditions have null data')
        entries=[]
        if count:
            blob=self.r.read(data,count*8,'complete condition pointers')
            for pos in range(0,len(blob),8):
                obj=ptr(struct.unpack_from('<Q',blob,pos)[0]);vt=self.vtable(obj,True)
                prior=self.aliases.setdefault(('condition',obj),vt);require(prior==vt,'Aliased condition identity changed')
                entries.append({'object':hex(obj),'vtable':vt,'purity_verified':False})
        return {'owner':hex(owner),'container_offset':hex(offset),'data':hx(data),'count':count,'entries':entries}
    def goal(self,game,war):
        obj=ptr(self.r.q(war+0x160,'war goal pointer'),True)
        if obj is None:return {'pointer':None,'status':'null_goal_not_evaluated'}
        vt=self.vtable(obj);result={'pointer':hex(obj),'vtable':vt,'status':'unrecognized_goal_class','conditions':None}
        if vt['rva']!='0x1d1fd90':return result
        result['status']='take_colony_direct_layout';result['definition']=hx(ptr(self.r.q(obj+0x10,'goal definition'),True))
        index=self.r.i(obj+0x18,'goal signed province index');result['province_index']=index
        result['predicate70']=False
        if index<0:result['resolution']='fallback_virtual_family_unreviewed';return result
        begin,end=struct.unpack('<QQ',self.r.read(game+0x1c90,16,'game province vector bounds'))
        require((begin==end==0) or (ptr(begin) and ptr(end) and end>=begin and (end-begin)%8==0),'Province vector bounds')
        require((end-begin)//8<=32768,'Province count budget');result['game_provinces_begin']=hx(begin);result['game_provinces_end']=hx(end)
        if index>=(end-begin)//8:result['resolution']='fallback_virtual_family_unreviewed';return result
        province=ptr(self.r.q(obj+0x30,'goal province pointer'),True);result['province']=hx(province)
        if province is None:result['resolution']='fallback_virtual_family_unreviewed';return result
        marker=self.r.u(province+0x24,'province marker');result['province_marker']=marker
        if marker==0:result['resolution']='fallback_virtual_family_unreviewed';return result
        blocks=ptr(self.r.q(game+0x1ca8,'game province blocks'));field=blocks+index*0x2e10+0x560
        stored=ptr(self.r.q(field,'province block matching pointer'),True)
        result.update(game_province_blocks=hex(blocks),province_block_field_address=hex(field),province_block_pointer=hx(stored),predicate70=stored==province)
        if not result['predicate70']:result['resolution']='fallback_virtual_family_unreviewed';return result
        require(result['definition'] is not None,'Recognized goal has null definition')
        result['resolution']='direct_definition_observed';definition=int(result['definition'],16)
        result['conditions']={hex(offset):self.conditions(definition,offset) for offset in (0x50,0x140,0x288,0x378)}
        return result
    def sample(self,actor,recipient,direction):
        roots=self.roots();self.aliases={}
        left=self.country(roots,actor);right=self.country(roots,recipient)
        require(actor!=recipient and left['pointer']!=right['pointer'],'Distinct country pair required')
        first,war_a=self.relation(roots,left,right);second,war_b=self.relation(roots,right,left)
        require(war_a==war_b,'Reciprocal war indexes disagree')
        caches={key:hx(self.global_ptr(rva,key)) for key,rva in (('nogovernment',0x233fe88),('secondary',0x242bc80),('goal_fallback',0x2340030),('dependency_registry',0x233ffd8))}
        result={'roots':roots,'relations':[first,second],'caches':caches,'war':None,'countries':[],
                'tls':{'status':'unsupported_subject_thread_gs_provenance','gate_a':self.r.b(self.base+0x233ff94,'TLS gate A'),
                       'gate_b':self.r.b(self.base+0x233fed6,'TLS gate B'),'module_index':self.r.u(self.base+0x233c574,'TLS module index')},
                'paused_observation':{'status':'not_collected_not_a_constructor_guard'},'dependency':None}
        if war_a is not None and caches['dependency_registry'] is not None:
            definition=ptr(self.r.q(int(caches['dependency_registry'],16)+0x80,'dependency registry definition'),True)
            result['dependency']={'definition':hx(definition),'conditions':self.conditions(definition,0x40) if definition else None}
        countries={actor:left,recipient:right}
        if war_a is None:
            result['status']='no_matching_war'
            result['dependency']={'status':'not_dereferenced_without_matching_war'}
        else:
            side_a,a=self.side(war_a,0x48,roots['country_count']);side_b,b=self.side(war_a,0x78,roots['country_count'])
            require(not set(a)&set(b),'War sides overlap');members=a+b
            require(len({self.handle(v,roots['country_count'])[0] for v in members})==len(members),'Different handles alias one country slot')
            require((actor in a and recipient in b) or (actor in b and recipient in a),'Pair not on opposite war sides')
            for value in members:countries[value]=self.country(roots,value)
            result['status']='borrowed_war_observed_partial_preconditions'
            result['war']={'pointer':hex(war_a),'vtable':self.vtable(war_a),'side_a':side_a,'side_b':side_b,
                          'goal':self.goal(int(roots['game'],16),war_a),'ownership_verified':False}
            taker,giver=(actor,recipient) if direction=='demand' else (recipient,actor)
            result['negotiating_roles']={'taker':f'0x{taker:016x}','giver':f'0x{giver:016x}',
                'taker_side':'A' if taker in a else 'B',
                'selected_condition_offsets':['0x50','0x140'] if taker in a else ['0x288','0x378']}
        for handle,country in sorted(countries.items()):
            country['government']=self.government(country);result['countries'].append(country)
            require(self.country(roots,handle)=={k:country[k] for k in ('handle','slot','tag','pointer')},'Country identity changed during pass')
        require(self.roots()==roots,'Roots/date changed during pass')
        return result


def capture(reader,base,actor,recipient,direction):
    """Exactly two reader passes. Exceptions/short reads never become absence."""
    request_arguments(actor,recipient,direction)
    pins=load_pins();budget=Budget(reader);walker=Walker(budget,base,pins);walker.verify_pins()
    passes=[]
    for sequence in range(2):
        started=time.monotonic_ns();snapshot=walker.sample(actor,recipient,direction);ended=time.monotonic_ns()
        passes.append({'sequence':sequence,'started_monotonic_ns':started,'ended_monotonic_ns':ended,'snapshot':snapshot})
    require(passes[0]['snapshot']==passes[1]['snapshot'],'Selected fields changed between bounded passes')
    walker.verify_pins()
    return {'schema_version':1,'purpose':'peace_raw_readonly_partial_preconditions','read_only':True,'status':passes[0]['snapshot']['status'],
        'pins_sha256':PINS_SHA,'prior_static_contract_sha256':pins['prior_static_contract_sha256'],
        'binding':{'actor_handle':f'0x{actor:016x}','recipient_handle':f'0x{recipient:016x}','direction':direction},
        'passes':passes,'read_budget':{'maximum_total':MAX_TOTAL,'maximum_single':MAX_READ,'maximum_reads':MAX_READS,'bytes_requested':budget.bytes,'read_count':len(budget.trace)},
        'read_trace':budget.trace,'selected_fields_equal_two_pass':True,'loaded_selected_code_pins_equal':True,
        'schema_projection':{'available':False,'missing':['authenticated_subject_thread_tls','paused_observed','complete_projection_adapter'],
             'reason':'No fabricated thread ID, TLS contents or pause boolean; previous strict envelope is intentionally not emitted.'},
        'runtime_constructor_verified':False,'parameter_constructor_authorized':False,'parameter_selftest_ready':False,
        'condition_purity_verified':False,'world_epoch_verified':False,'object_lifetime_verified':False,'production_ready':False,
        'limitations':['Both passes are non-atomic; ABA reuse and intervening changes may escape observation.',
            'Unknown government/war/condition dynamic classes remain inventory only. No virtual is called.',
            'No matching war is absence in two complete directed indexes, never white peace or diplomatic rejection.',
            'No raw TLS block/TEB/thread query is implemented. Read-only data never authorizes parameter construction.']}


def held_identity(reader,pid,expected_creation):
    """Same QUERY_INFORMATION-only process-time contract as the pinned legacy probe."""
    import ctypes as C
    from ctypes import wintypes as W
    kernel=reader.kernel
    kernel.GetProcessId.argtypes=[W.HANDLE];kernel.GetProcessId.restype=W.DWORD
    kernel.GetProcessTimes.argtypes=[W.HANDLE]+[C.POINTER(W.FILETIME)]*4;kernel.GetProcessTimes.restype=W.BOOL
    require(kernel.GetProcessId(reader.handle)==pid,'Held PID mismatch')
    times=[W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(reader.handle,*(C.byref(value) for value in times)):raise C.WinError(C.get_last_error())
    values=[value.dwHighDateTime<<32|value.dwLowDateTime for value in times]
    require(values[0]==expected_creation and values[1]==0,'Creation differs or process exited')
    return {'pid':pid,'creation_filetime':f'{values[0]:016x}','exit_filetime':0,'module_base':hex(reader.base)}


def sample_process(*,pid,creation,executable,actor,recipient,direction):
    """Future RO entry; tests replace ProcessReader/identity, never open a process."""
    integer(pid,1,2**32-1,'PID')
    request_arguments(actor,recipient,direction)
    require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)>0,'Explicit full creation required')
    pins=load_pins();executable=Path(executable).resolve()
    require(executable==(ROOT.parent/'eu4.exe').resolve() and sha(executable)==pins['exe_sha256'],'Wrong exact executable path/SHA')
    sys.path.insert(0,str(ROOT))
    from work import probe_diplomacy_current as legacy
    build,signature=legacy.verified_executable(executable)
    require(signature=={'timestamp':pins['pe']['timestamp'],'size':pins['pe']['image_size']},'Disk PE signature differs')
    reader=legacy.ProcessReader(pid,executable,signature)
    try:
        before=held_identity(reader,pid,int(creation,16))
        observation=capture(reader,reader.base,actor,recipient,direction)
        require(held_identity(reader,pid,int(creation,16))==before,'Held process identity changed')
        legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature)
        require(sha(executable)==pins['exe_sha256'],'Executable changed while observing')
        observation['read_budget']['process_bytes_including_pe_guards']=reader.bytes_read
        observation['source']={'kind':'held_process_readonly','identity':before,'path':str(executable),'disk_exe_sha256':pins['exe_sha256'],
                              'rights':['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'],'loaded_full_image_hash_verified':False}
        return observation
    finally:reader.close()
