"""Bounded private read/typed layout model. No process API, native call or permission."""
from dataclasses import dataclass
import struct

GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
COST_RVA=0x233db7c
AMOUNT_RVA=0x233db80
MAX_POINTER=0x7fffffffffff

def integer(x,lo,hi):
    if type(x) is not int or not lo<=x<=hi:raise ValueError('strict integer range')
    return x

def pointer(x):
    return integer(x,0x10000,MAX_POINTER)

def handle(x):
    integer(x,1,2**64-1)
    if x>>56==0 or ((x>>32)&0xffff)>=4096 or x&0xffffff==0x2d2d2d:
        raise ValueError('full country handle shape')
    return x

@dataclass(frozen=True)
class Context:
    """Typed external evidence container, NOT a claim that this module held a process."""
    pid:int;creation:int;module:int;game:int;database:int;array:int;count:int
    player:int;date:int;image_sha256:str

def context(c):
    if type(c) is not Context:raise ValueError('context type')
    integer(c.pid,1,0xffffffff);integer(c.creation,1,2**64-1)
    for p in (c.module,c.game,c.database,c.array):pointer(p)
    if c.module+0x25e0000>MAX_POINTER:raise ValueError('image extent')
    integer(c.count,1,4096);handle(c.player);integer(c.date,0,0x7fffffff)
    if ((c.player>>32)&0xffff)>=c.count:raise ValueError('player slot bound')
    if type(c.image_sha256) is not str or c.image_sha256!=GAME_SHA:raise ValueError('exact image identity')
    return c

class Reader:
    """Shared small budget. Caller supplies bytes; this class never opens a process."""
    def __init__(self,read):
        if not callable(read):raise ValueError('reader callable')
        self.read=read;self.calls=0;self.bytes=0
    def get(self,address,size):
        pointer(address);integer(size,1,16)
        if address+size-1>MAX_POINTER or self.calls>=48 or self.bytes+size>384:
            raise ValueError('read budget/address extent')
        self.calls+=1;self.bytes+=size
        value=self.read(address,size)
        if type(value) is not bytes or len(value)!=size:raise ValueError('exact byte read')
        return value
    def u64(self,address):return struct.unpack('<Q',self.get(address,8))[0]
    def i32(self,address):return struct.unpack('<i',self.get(address,4))[0]

def observed_context(reader,c):
    context(c)
    # Existing exact-build global/root/handle layout; no lazy getter is called.
    game=reader.u64(c.module+0x233fe78);db=reader.u64(c.module+0x233d8d0)
    if game!=c.game or db!=c.database:raise ValueError('root changed')
    array=reader.u64(db+0x118);count=reader.i32(db+0x124)
    if array!=c.array or count!=c.count:raise ValueError('database changed')
    if reader.u64(game+0x1e60)!=c.player or reader.i32(game+0x1dd0)!=c.date:
        raise ValueError('player/date changed')
    player_ptr=reader.u64(array+((c.player>>32)&0xffff)*8);pointer(player_ptr)
    if reader.u64(player_ptr+0x20)!=c.player:raise ValueError('player full generation changed')

def trust_defaults(first,second):
    """Two captured adjacent DWORDs. Stock text 10/5 never supplies missing bytes."""
    if type(first) is not bytes or type(second) is not bytes or len(first)!=8 or len(second)!=8:
        raise ValueError('two exact 8-byte captures')
    if first!=second:raise ValueError('defaults changed between reads')
    cost,amount=struct.unpack('<ii',first)
    # Conservative encoding domain, not a statement of the engine's entire legal domain.
    supported=0<=cost<=2147483 and 0<=amount<=100
    return {'cost_units':cost,'trust_points':amount,'favor_milli_candidate':cost*1000 if supported else None,
            'supported_encoding_domain':supported,'native_permission':None,'execution_verified':False,
            'production_ready':False}

def capture_defaults(read,c):
    """Private injected-reader candidate; external held PE/SHA/module checks remain required."""
    context(c);r=Reader(read);observed_context(r,c)
    first=r.get(c.module+COST_RVA,8)
    observed_context(r,c)
    second=r.get(c.module+COST_RVA,8)
    observed_context(r,c)
    out=trust_defaults(first,second)
    return {'context':c,'defaults':out,'read_calls':r.calls,'read_bytes':r.bytes,
            'held_process_implemented':False,'ABA_excluded':False,'native_permission':None}

@dataclass(frozen=True)
class Country:
    pointer:int;full_handle:int

def resolve(reader,c,h):
    handle(h);slot=(h>>32)&0xffff
    if slot>=c.count:raise ValueError('country slot outside database')
    ptr=reader.u64(c.array+slot*8);pointer(ptr)
    actual=reader.u64(ptr+0x20)
    if actual!=h:raise ValueError('country full generation mismatch')
    return Country(ptr,h)

def third_selection(read,c,actor,target,third):
    """Resolve current full handles twice, then describe the GUI's QWORD +40 representation."""
    context(c)
    for h in (actor,target,third):handle(h)
    if actor!=c.player:raise ValueError('private current-player profile')
    if len({(h>>32)&0xffff for h in (actor,target,third)})!=3:
        raise ValueError('private profile requires three distinct countries')
    r=Reader(read);observed_context(r,c)
    before=tuple(resolve(r,c,h) for h in (actor,target,third))
    observed_context(r,c)
    after=tuple(resolve(r,c,h) for h in (actor,target,third))
    observed_context(r,c)
    if before!=after:raise ValueError('country allocation/handle changed')
    # Two country trios are enclosed by three context checks; still not atomic or lifetime-safe.
    return {'actor':before[0],'target':before[1],'third':before[2],
            'action_extension_offset':0x40,'action_extension_bytes':struct.pack('<Q',third),
            'normal_gui_selection_static':True,'native_predicates_evaluated':False,
            'native_permission':None,'read_calls':r.calls,'read_bytes':r.bytes,
            'held_process_implemented':False,'ABA_excluded':False,'production_ready':False}
