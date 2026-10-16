"""Dependency-injected read-only kernel; no process opener, CLI, native call or writer.

This is NOT an end-to-end observer. The owner must hold and verify the existing
full process/player/target/world identity envelope around this kernel. None of
those properties, cache freshness, or engine lifetime is proved here.
"""
import hashlib,json,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPORT_SHA='ebac3cf968e1ae05a1ce58b2399c53034bb03e3a3afad9107e2b5f7201270333'
MAX_BYTES=8192;MAX_READS=256;MAX_SINGLE=64;MAX_COUNT=4096
SELECTED=0x261;EMPTY=0x286;MAX_COST=21474831
FALSE_CLAIMS=('native_call_authorized','production_ready','runtime_verified',
 'identity_verified','cache_freshness_verified','object_lifetime_verified',
 'native_legality_verified','actual_cost_verified','effect_verified')
class ReadError(ValueError):pass
def require(ok,message):
    if not ok:raise ReadError(message)
def integer(x,lo=0,hi=2**64-1):
    require(type(x) is int and lo<=x<=hi,'strict bounded integer');return x
def pointer(x,nullable=False):
    integer(x,0,0x7fffffffffff)
    require((nullable and x==0) or (x>=0x10000 and x%8==0),'aligned pointer');return x
def report():
    with (HERE/'report.json').open('rb') as f:raw=f.read(1024*1024+1)
    require(len(raw)<=1024*1024 and hashlib.sha256(raw).hexdigest()==REPORT_SHA,'report pin')
    return json.loads(raw)
class Budget:
    def __init__(self,reader):self.reader=reader;self.bytes=0;self.reads=[]
    def read(self,p,n):
        integer(p,0x10000,0x7fffffffffff);integer(n,1,MAX_SINGLE)
        require(p+n<=0x800000000000 and self.bytes+n<=MAX_BYTES and len(self.reads)<MAX_READS,'read budget')
        self.bytes+=n;raw=self.reader.read(p,n)
        require(type(raw) is bytes and len(raw)==n,'short or missing read')
        self.reads.append({'address':p,'size':n,'sha256':hashlib.sha256(raw).hexdigest()});return raw
    def q(self,p):return struct.unpack('<Q',self.read(p,8))[0]
    def i(self,p):return struct.unpack('<i',self.read(p,4))[0]
    def b(self,p):return self.read(p,1)[0]
def code_pins(r,base,c):
    # Subset pins do not replace held EXE SHA/module/PE identity verification.
    rows={v['rva']:v for f in c['facts'].values() for v in f['evidence']}
    for key in sorted(rows,key=lambda s:int(s,16)):
        i=rows[key];raw=bytes.fromhex(i['bytes'])
        require(r.read(base+int(key,16),len(raw))==raw,'loaded instruction pin')
    require(r.q(base+0x1c427b8)==base+0x8e6190,'aggregate virtual+48 pin')
def one(r,base,actor,cost_rva):
    x={'cache_state':r.i(actor+0x28c8),'base_milli':r.i(base+cost_rva),
       'transform_root':None,'transform':None,'aggregate':None,'status':None}
    if x['cache_state']!=2:x['status']='unsupported_cache_state';return x
    root=pointer(r.q(base+0x2358080),True);x['transform_root']=root
    if root==0:x['status']='unknown_transform_root';return x
    x['transform']=pointer(r.q(root+0xe4a0),True)
    if x['transform']!=0:x['status']='unsupported_dynamic_transform';return x
    a=actor+0x28d0;vt=r.q(a)
    x['aggregate']={'address':a,'vtable':vt}
    if vt!=base+0x1c42770:x['status']='unsupported_aggregate_vtable';return x
    t=r.i(a+8);dense=r.b(a+0x10);vvt=r.q(a+0x50)
    x['aggregate'].update(type_marker=t,dense=dense,vector_vtable=vvt)
    if t!=0x165 or dense!=1 or vvt!=base+0x1c37fa0:
        x['status']='unsupported_aggregate_layout';return x
    data=pointer(r.q(a+0x58),True);cap=r.i(a+0x60);count=r.i(a+0x64)
    x['aggregate'].update(data=data,capacity=cap,count=count,selected_record=None)
    if not SELECTED<count<=cap<=MAX_COUNT or data==0:
        x['status']='unsupported_vector_bounds';return x
    require(data+count*8<=0x800000000000,'vector span overflow')
    ident,value=struct.unpack('<ii',r.read(data+SELECTED*8,8))
    x['aggregate']['selected_record']={'address':data+SELECTED*8,'id':ident,'value_milli':value}
    # Dense native reads value regardless of id. This deliberately narrower
    # candidate accepts a directly indexed value or the constructor's untouched
    # sentinel. Do not require all default ids to equal their array indexes.
    if ident!=SELECTED and not (ident==EMPTY and value==0):
        x['status']='unsupported_record_identity';return x
    if not -1000<=value<=1000000:x['status']='unsupported_modifier_range';return x
    if not 0<=x['base_milli']<=MAX_COST:x['status']='unsupported_base_range';return x
    cost=x['base_milli']*(1000+value)//1000
    x['status']='dense_null_transform_arithmetic_candidate' if 0<=cost<=MAX_COST else 'unsupported_cost_range'
    return x
def capture(reader,base,actor,family):
    """Two equal local snapshots; this does not open/hold/authenticate a process."""
    pointer(base);pointer(actor)
    require(type(family) is str,'family type');c=report()
    require(family in c['families'],'fixed family')
    r=Budget(reader);code_pins(r,base,c)
    a=one(r,base,actor,c['families'][family]['base_cost_rva'])
    b=one(r,base,actor,c['families'][family]['base_cost_rva'])
    require(a==b,'local two-pass difference')
    cost=None
    if a['status']=='dense_null_transform_arithmetic_candidate':
        cost=a['base_milli']*(1000+a['aggregate']['selected_record']['value_milli'])//1000
    return {'schema_version':1,'family':family,'base':base,'actor':actor,
      'before':a,'after':b,'local_two_pass_equal':True,'final_milli_candidate':cost,
      'claims':{k:False for k in FALSE_CLAIMS},'read_bytes':r.bytes,'reads':r.reads}
