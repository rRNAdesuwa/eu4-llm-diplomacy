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

class PeaceTests(unittest.TestCase):
 def unknown(self,f):
  out=m.observe(CHOSEN,f);self.assertEqual(out['status'],'unknown');self.assertIsNone(out['selected_queue_presence']);self.assertEqual(m.result_code(out),2);self.assertFalse(out['commit_after_context_exit']);return out
 def test_empty_full_capture_closes_and_accounts_entry(self):
  f=FakeLibraries();out=m.observe(CHOSEN,f);self.assertEqual(out['status'],'selected_peace_queue_absent');self.assertEqual(m.result_code(out),0)
  self.assertTrue(f.closed);self.assertFalse(out['close_os_return_checked']);self.assertEqual(out['raw_ordered_read_journal'][0]['requested_bytes'],8192)
  self.assertEqual(out['rpm_budget']['bytes_requested'],sum(x['requested_bytes'] for x in out['raw_ordered_read_journal']))
  self.assertTrue(all(out[k] is False for k in m.FALSE_FLAGS))
 def test_present_retains_raw_state(self):
  f=FakeLibraries([dict(id=0,state=0xffffffff)]);out=m.observe(CHOSEN,f)
  self.assertEqual(m.result_code(out),0);self.assertIs(out['selected_queue_presence'],True)
  item=out['samples'][0]['queue']['selected'][0];self.assertEqual(item['state_raw_u32'],0xffffffff);self.assertEqual(item['native_id_raw_u32'],0)
 def test_multiple_zero_and_repeated_ID_are_not_deduplicated(self):
  out=m.observe(CHOSEN,FakeLibraries([dict(id=0),dict(id=0),dict(id=7),dict(id=7)]))
  self.assertEqual(m.result_code(out),0);self.assertEqual([x['native_id_raw_u32'] for x in out['samples'][0]['queue']['selected']],[0,0,7,7])
 def test_foreign_action_never_reads64(self):
  f=FakeLibraries([dict(vt=0x12340)]);out=m.observe(CHOSEN,f);self.assertEqual(m.result_code(out),0)
  self.assertNotIn((ACTION,64),f.mem.reads);self.assertEqual(f.mem.reads.count((ACTION,8)),4)
 def test_tombstone_bad_action_is_not_dereferenced(self):
  f=FakeLibraries([{}]);f.mem.put(NODE,struct.pack('<Q',5));f.mem.put(NODE+0x18,b'\x01');self.unknown(f)
  self.assertFalse(any(a==5 for a,n in f.mem.reads));self.assertNotIn((ACTION,8),f.mem.reads)
 def test_iteration_nonzero_stops_before_node(self):
  f=FakeLibraries([{}]);f.mem.put(TARGET+0x18ec,b'\x01');self.unknown(f);self.assertNotIn((NODE,25),f.mem.reads)
 def test_bad_previous_link(self):
  f=FakeLibraries([{}]);f.mem.put(NODE+8,struct.pack('<Q',NODE));self.unknown(f)
 def test_bad_tail(self):
  f=FakeLibraries([{}]);f.mem.put(TARGET+0x18e0,struct.pack('<Q',NODE+0x100));self.unknown(f)
 def test_cycle(self):
  f=FakeLibraries([{},{}]);f.mem.put(NODE+0x10,struct.pack('<Q',NODE));self.unknown(f)
 def test_count_mismatch(self):
  f=FakeLibraries([{}]);f.mem.put(TARGET+0x18e8,struct.pack('<I',2));self.unknown(f)
 def test_count_bound(self):
  f=FakeLibraries();f.mem.put(TARGET+0x18e8,struct.pack('<I',129));self.unknown(f)
 def test_actor_original_one_sided_is_unknown(self):
  for row in [dict(a=A,o=T),dict(a=T,o=A)]:self.unknown(FakeLibraries([row]))
 def test_wrong_recipient(self):self.unknown(FakeLibraries([dict(t=A)]))
 def test_marker_mismatch(self):
  f=FakeLibraries([{}]);f.mem.put(ACTION+8,struct.pack('<I',358));self.unknown(f)
 def test_short_read_attempt_stays_in_budget(self):
  f=FakeLibraries([{}]);f.mem.short=(ACTION,64);out=self.unknown(f)
  failed=[x for x in out['raw_ordered_read_journal'] if x['status']=='failed'];self.assertEqual(failed[0]['returned_bytes'],63)
  self.assertGreater(out['rpm_budget']['bytes_requested'],out['rpm_budget']['bytes_returned'])
 def test_two_pass_change_is_unknown(self):
  f=FakeLibraries([{}]);hits=[0]
  def hook(a,n):
   if (a,n)==(TARGET+0x18d8,21):
    hits[0]+=1
    if hits[0]==3:f.mem.put(ACTION+0x34,struct.pack('<I',2))
  f.mem.hook=hook;self.unknown(f)
 def test_table_postcheck_rejects_change(self):
  f=FakeLibraries();hits=[0]
  def hook(a,n):
   if (a,n)==(ARRAY,1380*8):
    hits[0]+=1
    if hits[0]==2:f.mem.put(ARRAY+8,struct.pack('<Q',TARGET))
  f.mem.hook=hook;self.unknown(f)
 def test_loaded_code_mismatch(self):
  f=FakeLibraries();f.mem.put(BASE+CODES[0][0],b'\x00');self.unknown(f)
 def test_unaligned_exact_code_slice_is_budgeted(self):
  f=FakeLibraries();r=f.reader();out=m.code_guard(r,BASE,CODES)
  self.assertEqual(sum(x['bytes'] for x in out),735);self.assertEqual(r.bytes,735);self.assertEqual(r.calls,4)
 def test_budget_call_limit_no_extra_port_read(self):
  f=FakeLibraries();r=f.reader();r.calls=4096
  with self.assertRaisesRegex(ValueError,'budget'):r.read(BASE,8)
  self.assertEqual(f.mem.reads,[])
 def test_budget_byte_limit_no_extra_port_read(self):
  f=FakeLibraries();r=f.reader();r.bytes=512*1024-7
  with self.assertRaisesRegex(ValueError,'budget'):r.read(BASE,8)
  self.assertEqual(f.mem.reads,[])
 def test_lower_pointer_and_span_guard(self):
  f=FakeLibraries();r=f.reader()
  for a,n in [(0xffff,8),(True,8),(BASE,0),(BASE,65537),(2**47-4,8)]:
   with self.assertRaises(ValueError):r.read(a,n)
  self.assertEqual(f.mem.reads,[])
 def test_low_action_pointer_is_unknown(self):
  f=FakeLibraries([{}]);f.mem.put(NODE,struct.pack('<Q',0xffff));self.unknown(f);self.assertFalse(any(a==0xffff for a,n in f.mem.reads))
 def test_source_change_after_close_prevents_commit(self):
  f=FakeLibraries();f.fail_guard=3;self.unknown(f);self.assertTrue(f.closed)
 def test_close_failure_prevents_commit(self):
  f=FakeLibraries();f.close_fail=True;out=self.unknown(f);self.assertFalse(out['normal_context_exit'])
 def test_uncleared_handle_prevents_commit(self):
  f=FakeLibraries();f.clear_handle=False;out=self.unknown(f);self.assertTrue(out['normal_context_exit']);self.assertFalse(out['held_handle_cleared'])
 def test_selection_type_and_epoch_shape(self):
  for changes in [dict(pid=True),dict(pid=0),dict(pid=2**32),dict(creation='0'*16),dict(creation='f'*15),dict(actor='fra'),dict(target='FRA')]:
   with self.assertRaises(ValueError):m.selection(**{**CHOSEN,**changes})
 def test_draft_status_refuses_before_libraries(self):
  factory=mock.Mock(side_effect=AssertionError('Must not construct libraries'))
  out=m.run('status',CHOSEN,library_factory=factory);self.assertEqual(m.result_code(out),2);factory.assert_not_called()
 def test_source_mismatch_refuses_before_libraries(self):
  original=m.json_file(m.MANIFEST);bad=copy.deepcopy(original);bad['source_pins'][m.REL+'/peace_current_pending.py']['sha256']='0'*64
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'manifest.json';p.write_text(json.dumps(bad),encoding='utf-8')
   factory=mock.Mock(side_effect=AssertionError('Must not construct libraries'))
   with mock.patch.object(m,'MANIFEST',p):out=m.run('check',library_factory=factory)
   self.assertEqual(m.result_code(out),2);factory.assert_not_called()
 def test_missing_production_receipt_refuses(self):
  bad=copy.deepcopy(m.json_file(m.MANIFEST));bad.update(sealed=True,runtime_capture_authorized=True)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'manifest.json';p.write_text(json.dumps(bad),encoding='utf-8')
   with mock.patch.object(m,'MANIFEST',p):
    with self.assertRaisesRegex(ValueError,'Review path'):m.verify_sources(runtime=True)
 def test_exit_zero_never_acceptance_and_strict_boolean(self):
  out=m.observe(CHOSEN,FakeLibraries());self.assertEqual(m.result_code(out),0)
  out['selected_queue_presence']=0;self.assertEqual(m.result_code(out),2)
  out['selected_queue_presence']=False;out['peace_completed']=True;self.assertEqual(m.result_code(out),2)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(PeaceTests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 print(json.dumps(dict(schema='EU4-PEACE-NEW-FAKE-TESTS/1',run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
  passed=result.wasSuccessful(),real_game_access=0,PE_disk_access=0,native_calls=0,old_tests_run=0),ensure_ascii=True))
 raise SystemExit(0 if result.wasSuccessful() else 1)
