"""Tiny offline interpreter for ONLY the saved constructor instructions.

Synthetic byte memory; it cannot open processes or call/authorize native code.
It deliberately cannot interpret arbitrary CFGs, calls, previews or queues.
"""
import json,re,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=0x140000000;RSP=0x10000;AI=0x20000;COUNTRY=0x30000;GAME=0x40000
NAMES=('sabotage_reputation','sow_discontent','slander_merchants','sabotage_recruitment','corrupt_officials')

def integer(v,lo,hi):
 if type(v)is not int or not lo<=v<=hi:raise ValueError('strict integer')
 return v
def handle(v):
 integer(v,0,2**64-1)
 if not v>>56 or (v>>32)&0xffff>=4096:raise ValueError('synthetic full handle')
 return v
def report():
 with (HERE/'report.json').open('rb') as f:b=f.read(1024*1024+1)
 if len(b)>1024*1024:raise ValueError('report bound')
 return json.loads(b)
def family(name):
 if type(name)is not str or name not in NAMES:raise ValueError('fixed family')
 return next(f for f in report()['families'] if f['name']==name)

def replay(name,actor,target,date,score_mode=False,*,instructions=None):
 f=family(name);handle(actor);handle(target);integer(date,1,2**31-1)
 if actor==target:raise ValueError('distinct countries')
 if type(score_mode)is not bool:raise ValueError('score bool')
 # Direct-dispatch RBP = current RSP+100; helper R11 = entry RSP = current+68.
 regs={'rsp':RSP,'rbp':RSP+0x100,'r11':RSP+0x68,'rcx':AI,'rdx':COUNTRY,
       'r14':COUNTRY,'rsi':AI,'rdi':actor,'r13':0,'r8':int(score_mode)}
 mem={p:0xa5 for p in range(RSP,RSP+0x300)}
 def put(addr,n,value):
  for i,b in enumerate((value&((1<<(8*n))-1)).to_bytes(n,'little')):mem[addr+i]=b
 def get(addr,n):
  try:return int.from_bytes(bytes(mem[addr+i] for i in range(n)),'little')
  except KeyError as e:raise ValueError('unknown synthetic read')from e
 put(AI+0x28,8,actor);put(COUNTRY+0x20,8,target);put(BASE+0x233fe78,8,GAME);put(GAME+0x1dd0,4,date)
 def register(s):
  if s.startswith('e')and s in ['eax','ebx','ecx','edx','esi','edi','ebp','esp']:return 'r'+s[1:],32
  if re.fullmatch(r'r\d+d',s):return s[:-1],32
  return s,64
 def readreg(s):
  key,bits=register(s)
  if key not in regs:raise ValueError('uninitialized synthetic register '+s)
  return regs[key]&((1<<bits)-1)
 def address(s,row):
  if s.startswith('rip '):
   b=bytes.fromhex(row['bytes']);return BASE+int(row['rva'],16)+len(b)+struct.unpack('<i',b[-4:])[0]
  m=re.fullmatch(r'(\w+)(?: ([+-]) (0x[0-9a-f]+|\d+))?',s)
  if not m:raise ValueError('unsupported address')
  offset=int(m[3],0)if m[3]else 0
  return readreg(m[1])+(-offset if m[2]=='-'else offset)
 def operand(s,row):
  m=re.fullmatch(r'(byte|word|dword|qword) ptr \[(.+)\]',s)
  if m:return get(address(m[2],row),{'byte':1,'word':2,'dword':4,'qword':8}[m[1]])
  if re.fullmatch(r'-?(?:0x[0-9a-f]+|\d+)',s):return int(s,0)
  return readreg(s)
 def assign(s,row,value):
  m=re.fullmatch(r'(byte|word|dword|qword) ptr \[(.+)\]',s)
  if m:
   a=address(m[2],row);n={'byte':1,'word':2,'dword':4,'qword':8}[m[1]]
   start=RSP+f['normal_caller']['action_rsp_offset']
   if not start<=a or a+n>start+64:raise ValueError('constructor write outside selected action')
   put(a,n,value);return
  key,bits=register(s);regs[key]=value&((1<<bits)-1)
 seq=f['initialization_instructions']if instructions is None else instructions
 for row in seq:
  op,rest=row['instruction'].split(' ',1);a,b=rest.split(', ',1)
  if op=='mov':assign(a,row,operand(b,row))
  elif op=='xor'and a==b:assign(a,row,0)
  elif op=='lea'and b.startswith('[rip '):assign(a,row,address(b[1:-1],row))
  else:raise ValueError('unsupported synthetic instruction '+op)
 start=RSP+f['normal_caller']['action_rsp_offset']
 return bytes(mem[start+i] for i in range(64))

def inspect(name,raw,actor,target,date):
 f=family(name);handle(actor);handle(target);integer(date,1,2**31-1)
 if type(raw)is not bytes or len(raw)!=64:raise ValueError('exact bytes64')
 expected={0:('Q',BASE+int(f['vtable_rva'],16)),8:('I',357),16:('Q',actor),24:('Q',actor),
           32:('Q',target),40:('i',date),44:('i',date),48:('i',-1),52:('I',0),56:('B',1),57:('B',0),60:('I',0)}
 for off,(fmt,value)in expected.items():
  if struct.unpack_from('<'+fmt,raw,off)[0]!=value:raise ValueError('field differs '+hex(off))
 return {'normal_constructor_model_matches':True,'token':f['token'],
         'native_call_authorized':False,'runtime_verified':False,'production_ready':False}
