"""Only new fake/owned-file tests; no observer or native process import."""
from pathlib import Path
import contextlib
import copy
import hashlib
import io
import json
import re
import struct
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
m=types.ModuleType('_peace_candidate_tested');m.__file__=str(HERE/'peace_current_pending.py')
exec(compile(Path(m.__file__).read_bytes(),m.__file__,'exec'),m.__dict__)
# These frozen modules contain only definitions at import. Their mains/Libraries are never called here.
direct=m.exact_compile(m.DIRECT,dict(bytes=16856,sha256=m.FIXED[m.DIRECT]))
R24='work/capture_direct_truce_flags_20261015.py'
r24=m.exact_compile(R24,dict(bytes=len((m.ROOT/R24).read_bytes()),sha256='1677ccf7f03b93c44d3bb5313bae3350605f51c58855f381f5b516504f4bb904'))
CODES=m.code_buffers()
BASE=0x140000000
ARRAY=0x500000
ACTOR=0x600000
TARGET=0x610000
NODE=0x800000
ACTION=0x700000
def handle(tag,slot):return (1<<56)|(slot<<32)|int.from_bytes(tag.encode(),'little')
A=handle('FRA',1);T=handle('ENG',2)
CHOSEN=dict(pid=1234,creation='0000000000000001',actor='FRA',target='ENG')

class Memory:
 def __init__(self):self.blocks=[];self.reads=[];self.hook=None;self.short=None
 def put(self,a,b):
  for addr,raw in self.blocks:
   if addr<=a and a+len(b)<=addr+len(raw):raw[a-addr:a-addr+len(b)]=b;return
  self.blocks.append((a,bytearray(b)))
 def read(self,a,n):
  self.reads.append((a,n))
  if self.hook:self.hook(a,n)
  for addr,b in reversed(self.blocks):
   if addr<=a and a+n<=addr+len(b):
    raw=bytes(b[a-addr:a-addr+n]);return raw[:-1] if self.short==(a,n) else raw
  raise ValueError('Fake unmapped read '+hex(a)+'/'+str(n))

class FakeLibraries:
 def __init__(self,rows=()):
  self.mem=Memory();self.guard_calls=0;self.fail_guard=None;self.close_fail=False;self.clear_handle=True
  self.codes=CODES;self.direct=direct;self.r24=r24;self.closed=False;self.runtime_created=0;self.disk_calls=0
  self.mem.put(BASE,bytes(8192));self.mem.put(BASE+0x233e064,struct.pack('<i',-1))
  for off,raw in CODES:self.mem.put(BASE+off,raw)
  table=bytearray(1380*8);struct.pack_into('<QQ',table,8,ACTOR,TARGET);self.mem.put(ARRAY,table)
  for addr,h in [(ACTOR,A),(TARGET,T)]:
   b=bytearray(40);struct.pack_into('<QI',b,0,BASE+0x1c574a0,357);struct.pack_into('<Q',b,0x20,h);self.mem.put(addr,b)
  self.install(rows)
  fixture=self
  class Held:
   def __init__(self,identity):
    self.handle=42;self.identity=identity;self.injector=types.SimpleNamespace(GAME=m.GAME,_canonical=lambda p:str(Path(p).resolve()).lower());fixture.held=self
   def identity_check(self):return None
   def modules(self):return [(BASE,str(m.GAME))]
   def close(self):
    if fixture.close_fail:raise ValueError('Fake close failure')
    fixture.closed=True
    if fixture.clear_handle:self.handle=None
  class ParentCapture:
   def __init__(self,identity,backend):self.identity=identity;self.backend=backend;self.held=None
   def __exit__(self,*args):
    if self.held:self.held.close()
  class Backend:
   manifest={'dll':{'sha256':'d'*64}};manifest_sha='e'*64
   def verify(self):return self.manifest
  def runtime():
   fixture.runtime_created+=1
   return types.SimpleNamespace(readonly=types.SimpleNamespace(Held=Held,disk_identity=lambda _:dict(fake=True),pe_header=lambda raw:dict(fake=len(raw)==8192)))
  def full_handle(h,count=1380,tag=None):
   m.require(type(h) is int and 0<h<2**64,'Handle type')
   slot=(h>>32)&65535;raw=(h&0xffffff).to_bytes(3,'little')
   m.require(h>>56!=0 and (h>>48)&255==0 and (h>>24)&255==0 and 0<slot<min(count,32768) and re.fullmatch(rb'[A-Z0-9]{3}',raw),'Full handle')
   actual=raw.decode();m.require(tag is None or actual==tag,'TAG mismatch');return slot,actual
  def roots(r,base):
   r.read(BASE+0x100,8)
   return dict(count=1380,array=hex(ARRAY),manual_pause=1,date=100)
  def country(r,base,root,h,tag=None):
   slot,name=full_handle(h,root['count'],tag);addr=m.pointer(r.q(ARRAY+slot*8));b=r.read(addr,40)
   m.require(struct.unpack_from('<Q',b)[0]==BASE+0x1c574a0 and struct.unpack_from('<I',b,8)[0]==357 and struct.unpack_from('<Q',b,32)[0]==h,'Typed full country')
   return dict(address=hex(addr),handle=hex(h),tag=name,slot=slot)
  self.obs=types.SimpleNamespace(RuntimeCapture=ParentCapture,WindowsRuntime=runtime,TagCommandBackend=Backend,
   HeldRPMPort=lambda held:self.mem,pins=lambda:dict(fake='source'),roots=roots,ptr=m.pointer,full_handle=full_handle,country=country,COUNTRY_VT=0x1c574a0)
  def host_sample(cap,proxy):
   cap.held.identity_check();r=proxy.BudgetReader(None);a=proxy.roots(r,BASE);b=proxy.roots(r,BASE)
   m.require(a==b,'Fake host roots changed');return dict(roots=a,rpm_budget=dict(calls=r.calls,bytes=r.bytes,largest=r.largest))
  self.host=types.SimpleNamespace(host_sample=host_sample)
 def install(self,rows):
  count=len(rows);self.mem.put(TARGET+0x18d8,struct.pack('<QQIB',NODE if count else 0,NODE+(count-1)*0x100 if count else 0,count,0))
  for i,row in enumerate(rows):
   node=NODE+i*0x100;action=ACTION+i*0x100
   self.mem.put(node,struct.pack('<QQQB',action,NODE+(i-1)*0x100 if i else 0,NODE+(i+1)*0x100 if i+1<count else 0,0))
   b=bytearray(64);struct.pack_into('<QI',b,0,BASE+row.get('vt',m.VT),357)
   struct.pack_into('<QQQ',b,0x10,row.get('a',A),row.get('o',A),row.get('t',T))
   struct.pack_into('<II',b,0x34,row.get('state',0),0);struct.pack_into('<I',b,0x3c,row.get('id',0));self.mem.put(action,b)
 def observer(self):return self.obs
 def guard(self):
  self.guard_calls+=1
  if self.guard_calls==self.fail_guard:raise ValueError('Fake source changed')
 def disk_guard(self):self.disk_calls+=1;return dict(fake='fixed disk')
 def evidence(self):return dict(fake=True)
 def reader(self):
  r=m.SharedReader();r.bind(self.mem,r24.AlignedPort(self.mem));return r
 def queue(self):return m.queue_sample(self.reader(),BASE,dict(address=hex(TARGET)),A,T)

class ScalarV2Tests(unittest.TestCase):
 def retain(self,name,out,f):
  self.assertTrue(f.closed)
  self.assertTrue(all(out[k] is False for k in m.FALSE_FLAGS))
  self.assertFalse(out['close_os_return_checked'])
  self.assertEqual(out['rpm_budget']['bytes_requested'],sum(x['requested_bytes'] for x in out['raw_ordered_read_journal']))
  p=HERE/'offline-r1'/('fake-'+name+'.json')
  with p.open('x',encoding='utf-8',newline='\n') as stream:json.dump(out,stream,ensure_ascii=True,sort_keys=True,indent=2);stream.write('\n')
 def scalar_rows(self,out):
  return [x for x in out['raw_ordered_read_journal'] if x['address']==hex(BASE+0x233e064)]
 def success(self,name,value,present):
  f=FakeLibraries([dict(id=0,state=0xffffffff)] if present else [])
  f.mem.put(BASE+0x233e064,struct.pack('<i',value));out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),0);self.assertIs(out['selected_queue_presence'],present)
  self.assertTrue(out['commit_after_context_exit']);self.assertTrue(out['selected_two_pass_equal'])
  self.assertEqual(len(self.scalar_rows(out)),2)
  for sample in out['samples']:
   self.assertEqual(sample['unclassified_scalar'],dict(rva='0x233e064',raw_hex=struct.pack('<i',value).hex(),i32=value,u32=value&0xffffffff,semantics='unknown'))
  if present:
   row=out['samples'][0]['queue']['selected'][0];self.assertEqual(row['native_id_raw_u32'],0);self.assertEqual(row['state_raw_u32'],0xffffffff)
  self.retain(name,out,f)
 def test_01_minus_one_absent(self):self.success('minus-one-absent',-1,False)
 def test_02_one_absent(self):self.success('one-absent',1,False)
 def test_03_one_present(self):self.success('one-present',1,True)
 def test_04_scalar_changes(self):
  f=FakeLibraries();f.mem.put(BASE+0x233e064,struct.pack('<i',1));calls=[]
  def hook(a,n):
   if (a,n)==(BASE+0x233e064,4):
    calls.append(1)
    if len(calls)==2:f.mem.put(a,struct.pack('<i',2))
  f.mem.hook=hook;out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),2);self.assertIsNone(out['selected_queue_presence']);self.assertFalse(out['commit_after_context_exit'])
  self.assertEqual([s['unclassified_scalar']['i32'] for s in out['samples']],[1,2])
  self.assertTrue(any(e['message']=='Two complete passes differ' for e in out['errors']))
  self.retain('scalar-change',out,f)
 def test_05_short_scalar(self):
  f=FakeLibraries();f.mem.put(BASE+0x233e064,struct.pack('<i',1));f.mem.short=(BASE+0x233e064,4);out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),2);self.assertIsNone(out['selected_queue_presence']);self.assertFalse(out['commit_after_context_exit'])
  rows=self.scalar_rows(out);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['requested_bytes'],4);self.assertEqual(rows[0]['returned_bytes'],3);self.assertEqual(rows[0]['status'],'failed')
  self.assertNotIn((TARGET+0x18d8,21),f.mem.reads);self.retain('short-scalar',out,f)
 def test_06_structural_refusal(self):
  f=FakeLibraries([dict(id=0)]);f.mem.put(BASE+0x233e064,struct.pack('<i',1));f.mem.put(NODE+24,b'\x01');f.mem.put(NODE,struct.pack('<Q',1))
  out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),2);self.assertIsNone(out['selected_queue_presence']);self.assertFalse(out['commit_after_context_exit'])
  self.assertTrue(any('Tombstone' in e['message'] for e in out['errors']));self.assertFalse(any(a==1 for a,n in f.mem.reads))
  self.assertEqual(self.scalar_rows(out)[0]['raw_hex'],'01000000');self.retain('structural-refusal',out,f)

if __name__=='__main__':unittest.main(verbosity=2)
