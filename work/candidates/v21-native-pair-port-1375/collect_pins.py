"""Fixed offline PE byte reads only; no decode, process access, or execution."""
import hashlib,json,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EXE=ROOT.parent/'eu4.exe'
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PROFILES=[(0x1c7fd20,0x51fa00,0x129450,0x4e99d0,0x51f4a0),(0x1c80ab0,0x4f07d0,0x4ed5b0,0x4e99d0,0x4ef7b0),
 (0x1c7dd68,0x574b20,0x129450,0x4e99d0,0x5746d0),(0x1c7fe50,0x5224c0,0x129450,0x4e99d0,0x521f00),
 (0x1c7cc48,0x586200,0x129450,0x586330,0x5858e0),(0x1c7aef8,0x5ae2b0,0x129450,0x4e99d0,0x5ae110)]
def digest(p):
 h=hashlib.sha256();size=0
 with p.open('rb') as f:
  while block:=f.read(1024*1024):h.update(block);size+=len(block)
 return {'bytes':size,'sha256':h.hexdigest()}
def seal(p,value):
 with p.open('xb') as f:f.write(value)
def generate():
 before=digest(EXE);assert before['sha256']==SHA
 with EXE.open('rb') as f:
  h=f.read(4096);pe=struct.unpack_from('<I',h,0x3c)[0];assert pe+264<=len(h) and h[pe:pe+4]==b'PE\0\0'
  machine,nsects,stamp=struct.unpack_from('<HHI',h,pe+4);opt=struct.unpack_from('<H',h,pe+20)[0]
  assert machine==0x8664 and stamp==0x66fe6ab9 and 1<=nsects<=32
  assert struct.unpack_from('<H',h,pe+24)[0]==0x20b
  base=struct.unpack_from('<Q',h,pe+48)[0];assert struct.unpack_from('<I',h,pe+80)[0]==0x25e0000
  start=pe+24+opt;assert start+nsects*40<=len(h)
  sections=[struct.unpack_from('<IIII',h,start+i*40+8) for i in range(nsects)]
  def read(rva,n):
   assert 0<n<=64
   matches=[(va,raw,off) for virt,va,raw,off in sections if va<=rva and rva-va+n<=raw]
   assert len(matches)==1;va,raw,off=matches[0];offset=off+rva-va;f.seek(offset);b=f.read(n);assert len(b)==n
   return b,offset
  code=[]
  for rva in sorted({0x35d210,0x4e9930,0x4e8630,0x4e7470}|{r for p in PROFILES for r in p[1:]}):
   # Four-byte complete trivial setter is pinned whole. Other 32-byte pins
   # identify bounded entry bytes, not whole-function correctness.
   b,o=read(rva,4 if rva==0x4e99d0 else 32);code.append({'rva':rva,'file_offset':o,'hex':b.hex()})
  slots=[]
  for vt,clone,dtor,setter,full in PROFILES:
   for off,value in [(0,dtor),(0x40,0x4e9930),(0x88,full),(0xb0,clone)]:
    b,o=read(vt+off,8);assert int.from_bytes(b,'little')==base+value
    slots.append({'rva':vt+off,'target':value,'hex':b.hex(),'file_offset':o})
  for off,value in [(0,0x4e7470),(0x40,0x4e8630)]:
   b,o=read(0x1c814b0+off,8);assert int.from_bytes(b,'little')==base+value
   slots.append({'rva':0x1c814b0+off,'target':value,'hex':b.hex(),'file_offset':o})
 after=digest(EXE);assert before==after
 data={'schema':1,'exe':str(EXE),'before':before,'after':after,'preferred_image_base':base,'code':code,'slots':slots,
       'decode_bytes':0,'process_accessed':False,'compiled_platform_executed':False,'prefix_is_whole_function_proof':False}
 header='#pragma once\n#include <cstdint>\nnamespace v21port {\nstruct CodePin {std::uint32_t rva;const char* hex;};\ninline constexpr CodePin kCodePins[]={\n'
 header+=''.join(' {0x%x,"%s"},\n'%(p['rva'],p['hex']) for p in code)+'};\n}\n'
 return data,header.encode('ascii')
if __name__=='__main__':
 data,header=generate();seal(HERE/'native_pins.h',header);seal(HERE/'pin-provenance.json',(json.dumps(data,indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps({'code_pins':len(data['code']),'slots':len(data['slots']),'bytes':sum(len(x['hex'])//2 for x in data['code']+data['slots']),'before_after_same':True,'new_decode':0}))
