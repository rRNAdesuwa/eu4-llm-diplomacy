"""Pure injectable-reader TAG resolution; no OS/process/native entrypoint.
The result is two bounded equal observations, never an execution capability.
"""
import hashlib
import json
import re
import struct
import layout as p

class ResolutionError(ValueError):pass
class Unsupported(ResolutionError):pass

def require(ok,why):
    if not ok:raise ResolutionError(why)
def integer(x,low=0,high=2**64-1):
    require(type(x)is int and low<=x<=high,'Exact bounded integer');return x
def pointer(x,nullable=False):
    integer(x,0,2**47-1);require((nullable and x==0) or (x>=0x10000 and x%8==0),'Aligned user pointer');return x
def exact(x,keys):require(type(x)is dict and set(x)==set(keys.split()),'Exact keys')
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def validate_request(request):
    exact(request,'tags');tags=request['tags']
    require(type(tags)is list and 1<=len(tags)<=p.MAX_TAGS,'Bounded TAG list')
    require(all(type(x)is str and re.fullmatch('[A-Z0-9]{3}',x) for x in tags),'Exact uppercase ASCII three-character TAG')
    require(len(set(tags))==len(tags),'Duplicate requested TAG');return tuple(tags)

class Budget:
    def __init__(self,reader):self.reader=reader;self.calls=0;self.bytes=0
    def read(self,address,size):
        integer(address,0x10000,2**47-1);integer(size,1,p.MAX_SINGLE)
        require(address+size<=2**47 and self.calls<p.MAX_CALLS and self.bytes+size<=p.MAX_TOTAL,'Read budget/range')
        self.calls+=1;self.bytes+=size
        try:raw=self.reader.read(address,size)
        except Exception as exc:raise ResolutionError('Unavailable read; cannot infer absence') from exc
        require(type(raw)is bytes and len(raw)==size,'Exact bytes, no short or missing read');return raw
    def u64(self,address):return struct.unpack('<Q',self.read(address,8))[0]
    def i32(self,address):return struct.unpack('<i',self.read(address,4))[0]
    def byte(self,address):return self.read(address,1)[0]

def check_code(r,base):
    pointer(base);require(base%65536==0 and base+0x25e0000<2**47,'Internal image base range')
    for rva,h in p.CODE_PINS:
        expected=bytes.fromhex(h);require(r.read(base+rva,len(expected))==expected,'Exact selected loaded instruction bytes')

def roots(r,base):
    database=pointer(r.u64(base+p.DATABASE_RVA));game=pointer(r.u64(base+p.GAME_RVA))
    array=pointer(r.u64(database+0x118));capacity=integer(r.i32(database+0x120),1,p.MAX_COUNTRIES)
    count=integer(r.i32(database+0x124),1,capacity)
    require(array+count*8<=2**47,'Lookup array extent')
    date=integer(r.i32(game+0x1dd0),1,2**31-1)
    # Byte 1e66 overlaps current-handle bits48..55. Only ordinary selector0
    # is supported; the separately evidenced variant7 is not extrapolated.
    current=r.u64(game+0x1e60);selector=r.byte(game+0x1e66);alternate_flag=r.byte(game+0x1e6f)
    alternate_raw=r.u64(game+0x1e68)
    require(selector==((current>>48)&255),'Current handle/selector changed during read')
    require(alternate_flag==(alternate_raw>>56),'Alternate handle/selector changed during read')
    if selector!=0:raise Unsupported('Only ordinary current-player selector0; variant7/other unsupported')
    reset=r.byte(game+0x7485);load=r.u64(game+0x74c8)
    require(reset==0 and load==0,'Known reset/load exclusion')
    return dict(base=base,database=database,game=game,array=array,capacity=capacity,count=count,date=date,
                current_player=current,selector=selector,alternate_flag=alternate_flag,alternate_raw=alternate_raw,effective_player=current,reset=reset,load_source=load)

def decode_handle(handle,slot,count):
    integer(handle);integer(slot,0,count-1)
    require(((handle>>32)&65535)==slot,'Handle ordinal differs from lookup slot')
    # Research-profile filters, not general statements about valid EU4 types.
    require(handle>>56!=0 and ((handle>>48)&255)==0 and ((handle>>24)&255)==0,'Unsupported generation/type/reserved-byte profile')
    text=(handle&0xffffff).to_bytes(3,'little').decode('ascii',errors='strict')
    require(re.fullmatch('[A-Z0-9]{3}',text) is not None,'Country handle TAG bytes')
    return text

def inspect_pass(s):
    exact(s,'roots entries array_sha256')
    z=s['roots'];exact(z,'base database game array capacity count date current_player selector alternate_flag alternate_raw effective_player reset load_source')
    for key in ('base','database','game','array'):pointer(z[key])
    require(z['base']%65536==0 and z['base']+0x25e0000<2**47,'Base bounds')
    cap=integer(z['capacity'],1,p.MAX_COUNTRIES);count=integer(z['count'],1,cap);integer(z['date'],1,2**31-1)
    require(z['array']+count*8<=2**47,'Array extent')
    current=integer(z['current_player']);integer(z['effective_player']);require(z['effective_player']==current,'Ordinary effective player')
    integer(z['selector'],0,0);require(((current>>48)&255)==0,'Ordinary selector profile')
    alt=integer(z['alternate_raw']);require(integer(z['alternate_flag'],0,255)==alt>>56,'Alternate overlap')
    integer(z['reset'],0,0);integer(z['load_source'],0,0)
    rows=s['entries'];require(type(rows)is list and len(rows)==count,'Complete bounded slot census')
    addresses=set();handles=set();tags=set();packed=bytearray();player=None
    for slot,row in enumerate(rows):
        exact(row,'slot address vtable marker handle tag reserved_sentinel')
        require(integer(row['slot'],0,count-1)==slot,'Slot order/ordinal')
        address=pointer(row['address'],True);packed+=struct.pack('<Q',address)
        require(type(row['reserved_sentinel'])is bool,'Sentinel bool')
        if address==0:
            require(all(row[k] is None for k in ('vtable','marker','handle','tag')) and row['reserved_sentinel'] is False,'Null slot has no object fields');continue
        require(address not in addresses,'Aliased country pointer');addresses.add(address)
        require(pointer(row['vtable'])==z['base']+p.COUNTRY_VTABLE_RVA and integer(row['marker'])==p.COUNTRY_MARKER,'Country type header')
        handle=integer(row['handle']);require(handle not in handles,'Duplicate full handle');handles.add(handle)
        if slot==0 and handle==p.INVALID_HANDLE:
            require(row['reserved_sentinel'] is True and row['tag'] is None,'Exact slot0 sentinel');continue
        require(slot!=0 and row['reserved_sentinel'] is False,'Nonempty slot0 must be the exact reserved sentinel')
        try:tag=decode_handle(handle,slot,count)
        except UnicodeError as exc:raise ResolutionError('Non-ASCII country TAG') from exc
        require(type(row['tag'])is str and row['tag']==tag and tag not in tags,'Exact unique country TAG');tags.add(tag)
        if handle==current:player=row
    require(type(s['array_sha256'])is str and s['array_sha256']==hashlib.sha256(packed).hexdigest(),'Reconstructed full lookup array hash')
    require(player is not None and ((current>>32)&65535)==player['slot'],'Current/effective player resolves to the same complete object handle')
    return True

def one_pass(r,base):
    before=roots(r,base);data=r.read(before['array'],before['count']*8);rows=[];addresses=set()
    for slot in range(before['count']):
        address=pointer(struct.unpack_from('<Q',data,slot*8)[0],True)
        row=dict(slot=slot,address=address,vtable=None,marker=None,handle=None,tag=None,reserved_sentinel=False)
        if address:
            require(address not in addresses,'Aliased object before dereference');addresses.add(address)
            header=r.read(address,12);vt,marker=struct.unpack('<QI',header)
            if vt!=base+p.COUNTRY_VTABLE_RVA or marker!=p.COUNTRY_MARKER:
                raise Unsupported('Unknown country header; derived handle is not read')
            handle=r.u64(address+0x20);row.update(vtable=vt,marker=marker,handle=handle)
            if slot==0 and handle==p.INVALID_HANDLE:row['reserved_sentinel']=True
            else:
                require(slot!=0,'Nonempty slot0 must be the exact reserved sentinel')
                try:row['tag']=decode_handle(handle,slot,before['count'])
                except UnicodeError as exc:raise ResolutionError('Non-ASCII country TAG') from exc
        rows.append(row)
    require(r.read(before['array'],before['count']*8)==data,'Lookup pointer array changed inside pass')
    require(canonical(roots(r,base))==canonical(before),'Roots/date/current/effective player changed inside pass')
    result=dict(roots=before,entries=rows,array_sha256=hashlib.sha256(data).hexdigest());inspect_pass(result);return result

def public_result(result):
    exact(result,'schema requested passes bindings read_budget stable_two_pass atomic flags')
    require(result['schema']=='EU4CURRENTCOUNTRY/1','Result schema');requested=validate_request({'tags':result['requested']})
    require(type(result['passes'])is list and len(result['passes'])==2,'Exactly two passes')
    for s in result['passes']:inspect_pass(s)
    require(canonical(result['passes'][0])==canonical(result['passes'][1]),'Typed entire pass comparison')
    require(result['stable_two_pass'] is True and result['atomic'] is False,'Stability only, never atomic')
    exact(result['flags'],'runtime_verified production_ready native_authorized strict_sp_verified world_epoch_verified aba_excluded full_exe_identity_verified gameplay_existence_verified')
    require(all(v is False for v in result['flags'].values()),'No promotion')
    exact(result['read_budget'],'calls bytes');integer(result['read_budget']['calls'],1,p.MAX_CALLS);integer(result['read_budget']['bytes'],1,p.MAX_TOTAL)
    # Successful producer performs four root samples (12 fields/63B each),
    # four complete pointer-array reads, two guarded object reads per pass,
    # and the selected pins before/after. Bind declared cost to that contract.
    z=result['passes'][0];nonempty=sum(e['address']!=0 for e in z['entries'])
    require(result['read_budget']['calls']==52+4*nonempty+2*len(p.CODE_PINS),'Read-call accounting')
    require(result['read_budget']['bytes']==252+32*z['roots']['count']+40*nonempty+2*sum(len(bytes.fromhex(h)) for _,h in p.CODE_PINS),'Read-byte accounting')
    entries={e['tag']:e for e in result['passes'][0]['entries'] if e['tag'] is not None};bindings=[]
    for tag in requested:
        require(tag in entries,'Requested TAG not found in this supported bounded census; not proof of nonexistence')
        e=entries[tag];bindings.append(dict(tag=tag,slot=e['slot'],full_handle=f"0x{e['handle']:016x}"))
    require(canonical(result['bindings'])==canonical(bindings),'Derived binding mismatch/type')
    return dict(schema='EU4CURRENTCOUNTRYBINDINGS/1',bindings=bindings,raw_date=result['passes'][0]['roots']['date'],current_player_full_handle=f"0x{result['passes'][0]['roots']['current_player']:016x}",
                effective_player_full_handle=f"0x{result['passes'][0]['roots']['effective_player']:016x}",stable_two_pass=True,atomic=False,**result['flags'])

def resolve(reader,module_base,request):
    tags=validate_request(request);pointer(module_base);r=Budget(reader)
    check_code(r,module_base);a=one_pass(r,module_base);b=one_pass(r,module_base);check_code(r,module_base)
    require(canonical(a)==canonical(b),'Country table or handles changed between complete passes')
    bytag={e['tag']:e for e in a['entries'] if e['tag'] is not None};bindings=[]
    for tag in tags:
        require(tag in bytag,'Requested TAG unavailable; no absence/gameplay inference')
        e=bytag[tag];bindings.append(dict(tag=tag,slot=e['slot'],full_handle=f"0x{e['handle']:016x}"))
    result=dict(schema='EU4CURRENTCOUNTRY/1',requested=list(tags),passes=[a,b],bindings=bindings,read_budget=dict(calls=r.calls,bytes=r.bytes),stable_two_pass=True,atomic=False,
                flags=dict.fromkeys('runtime_verified production_ready native_authorized strict_sp_verified world_epoch_verified aba_excluded full_exe_identity_verified gameplay_existence_verified'.split(),False))
    public_result(result);return result
