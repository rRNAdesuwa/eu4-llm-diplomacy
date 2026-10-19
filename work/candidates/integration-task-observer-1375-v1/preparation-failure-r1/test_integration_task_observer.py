"""Only this candidate's new owned byte-graph/failure tests; no actual process."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import types
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import integration_task_observer as cli
for n,h in cli.FIXED.items():assert cli.pin(cli.ROOT/n)['sha256']==h
DIRECT=cli.exact_compile(cli.DIRECT,cli.pin(cli.ROOT/cli.DIRECT))
R24=DIRECT.exact_compile(DIRECT.R24,DIRECT.pin(cli.ROOT/DIRECT.R24))
HOST=DIRECT.exact_compile(DIRECT.HOST,DIRECT.pin(cli.ROOT/DIRECT.HOST))
CODES=cli.code_buffers()
path=cli.ROOT/cli.OBSERVER;raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==cli.FIXED[cli.OBSERVER]
NAMES={'ptr','full_handle','BudgetReader','roots','country','relation','index'}
tree=ast.parse(raw,str(path));nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in NAMES]
assert {n.name for n in nodes}==NAMES
NS=dict(struct=struct,re=re,require=cli.require,COUNTRY_VT=0x1c574a0,SENTINEL=0x2d2d2d,
 LIMITS=dict(calls=4096,bytes=512*1024,single_read=65536,index_entries=256),digest=lambda b:hashlib.sha256(b).hexdigest())
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),NS)
BASE,TABLE,A,T,P,IA,IT=0x180000000,0x300000,0x400000,0x500000,0x900000,0xa00000,0xa10000
G,D,S,PAUSE,OUTER=0x1000000,0x1100000,0x1200000,0x1300000,0x1400000
def handle(tag,slot,generation=1):return (generation<<56)|(slot<<32)|int.from_bytes(tag.encode('ascii'),'little')
AH,TH=handle('FRA',8),handle('AUV',19)
CHOSEN=dict(pid=12345,creation='0000000000000001',actor='FRA',target='AUV')

class Memory:
 def __init__(self,present=True):
  self.blocks={};self.reads=[];self.counts={};self.hook=None
  table=bytearray(1380*8);struct.pack_into('<Q',table,8*8,A);struct.pack_into('<Q',table,19*8,T);self.put(TABLE,table)
  for address,h,slot,other,otherslot,arr in ((A,AH,8,TH,19,IA),(T,TH,19,AH,8,IT)):
   header=bytearray(0x28);struct.pack_into('<QI',header,0,BASE+0x1c574a0,357);struct.pack_into('<Q',header,0x20,h);self.put(address,header)
   relation=bytearray(0x30);vec=address+0x3000
   struct.pack_into('<QI',relation,0,BASE+0x1c4f5f8,357);struct.pack_into('<QQQQ',relation,0x10,address,vec,vec+64*0x48,vec+64*0x48)
   self.put(address+0x14f8,relation);records=bytearray(64*0x48)
   struct.pack_into('<QQQ',records,otherslot*0x48,address+0x14f8,h,other);self.put(vec,records)
   self.put(address+0x14f8+0x200,struct.pack('<Qii',arr,1,1) if present else bytes(16))
   self.put(arr,struct.pack('<i4xQ',otherslot,P))
  task=bytearray(0x48);struct.pack_into('<Q',task,0,BASE+cli.VT);struct.pack_into('<I',task,8,0xabcdef)
  struct.pack_into('<QQI',task,0x10,AH,TH,0xfedcba98);self.put(P,task)
  self.put(BASE+0x233fe78,struct.pack('<Q',G));self.put(BASE+0x233d8d0,struct.pack('<Q',D))
  game=bytearray(0x7500);struct.pack_into('<Q',game,0,BASE+0x1cb00c8);struct.pack_into('<i',game,0x1dd0,123456)
  struct.pack_into('<Q',game,0x1e00,S);struct.pack_into('<Q',game,0x1e60,AH);struct.pack_into('<Q',game,0x1e68,0x2d2d2d)
  self.put(G,game);db=bytearray(0x128);struct.pack_into('<Qii',db,0x118,TABLE,1380,1380);self.put(D,db)
  server=bytearray(0x420);struct.pack_into('<Q',server,0,BASE+0x1cb8460);struct.pack_into('<Q',server,0x418,PAUSE);self.put(S,server)
  pause=bytearray(0x58);pause[0x48]=1;struct.pack_into('<Q',pause,0x50,S);self.put(PAUSE,pause)
  self.put(BASE+0x242bf50,struct.pack('<Q',OUTER));outer=bytearray(0x88)
  struct.pack_into('<Q',outer,0,BASE+0x1c48bf8);struct.pack_into('<Q',outer,0x10,BASE+0x1c48c80);struct.pack_into('<Q',outer,0x40,S);self.put(OUTER,outer)
  self.put(BASE+HOST.ENTRY_RVA,HOST.PREFIX)
  for rva,b in CODES:self.put(BASE+rva,struct.pack('<Q',BASE+cli.LEAF) if b is None else b)
 def put(self,address,raw):self.blocks[address]=bytes(raw)
 def change(self,address,offset,raw):
  b=bytearray(self.blocks[address]);b[offset:offset+len(raw)]=raw;self.blocks[address]=bytes(b)
 def read(self,address,size):
  self.reads.append((address,size));key=(address,size);self.counts[key]=self.counts.get(key,0)+1
  for begin,b in self.blocks.items():
   if begin<=address and address+size<=begin+len(b):
    value=b[address-begin:address-begin+size]
    return self.hook(address,size,value,self.counts[key]) if self.hook else value
  raise ValueError('Synthetic unmapped span '+hex(address)+'/'+str(size))

class FakeLibraries:
 def __init__(self,present=True,close_error=False,stuck=False,fail_guard=0,research=False):
  self.memory=Memory(present);self.codes=CODES;self.direct=DIRECT;self.r24=R24;self.host=HOST
  self.enters=self.closes=self.guards=self.identities=0;self.fail_guard=fail_guard;owner=self
  class Held:
   def __init__(self,cap):self.cap=cap;self.handle=123;self.injector=types.SimpleNamespace(GAME=cli.GAME)
   def identity_check(self):owner.identities+=1
   def modules(self):return self.cap.modules
  class Capture:
   def __init__(self,identity,backend):
    owner.identity=copy.deepcopy(identity);self.base=BASE;self.initial_pins={'fake':True};self.modules=[(BASE,str(cli.GAME))]
    if research:self.modules.append((0x50000000,'C:/fake/tag_diplomacy.dll'))
    self.held=Held(self)
   def __enter__(self):owner.enters+=1;return self
   def __exit__(self,*_):
    owner.closes+=1
    if not stuck:self.held.handle=None
    if close_error:raise ValueError('Synthetic close failure')
  backend=types.SimpleNamespace(manifest={'dll':{'sha256':'a'*64}},manifest_sha='b'*64)
  self.module=types.SimpleNamespace(**{n:NS[n] for n in NAMES},COUNTRY_VT=0x1c574a0,
   HeldRPMPort=lambda _:self.memory,RuntimeCapture=Capture,TagCommandBackend=lambda:backend,pins=lambda:{'fake':True})
 def guard(self):
  self.guards+=1
  if self.guards==self.fail_guard:raise ValueError('Synthetic source mutation')
 def observer(self):self.guard();return self.module
 def evidence(self):return {'synthetic':True,'old_fixed_pid_authority_reused':False}

class Tests(unittest.TestCase):
 def unknown(self,out):
  self.assertEqual(cli.result_code(out),2,out);self.assertEqual(out['status'],'unknown');self.assertIsNone(out['selected_task_present'])
  self.assertFalse(out['commit_after_context_exit'])
 def test_present_and_absent_current_only(self):
  for present in (True,False):
   lib=FakeLibraries(present);out=cli.observe(CHOSEN,lib)
   self.assertEqual(cli.result_code(out),0,out['errors']);self.assertIs(out['selected_task_present'],present)
   self.assertEqual(out['status'],'selected_task_present' if present else 'selected_index_absent')
   self.assertEqual((lib.enters,lib.closes),(1,1));self.assertTrue(out['held_handle_cleared'])
   for k in cli.FALSE_FLAGS:self.assertIs(out[k],False)
 def test_loaded_base_relocation_marker_and_raw20(self):
  lib=FakeLibraries();out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
  task=out['samples'][0]['task'];self.assertEqual(task['raw_u32_at_20'],0xfedcba98);self.assertFalse(task['marker_357_required'])
  self.assertEqual(out['code_before'][2]['raw_hex'],struct.pack('<Q',BASE+cli.LEAF).hex())
  self.assertNotEqual(BASE,0x140000000);self.assertEqual(lib.identity['pid'],12345)
  self.assertEqual(lib.identity['creation'],CHOSEN['creation']);self.assertRegex(lib.identity['session'],'^[0-9a-f]{32}$')
 def test_reverse_input_and_endpoint_order_are_supported(self):
  lib=FakeLibraries();lib.memory.change(P,0x10,struct.pack('<QQ',TH,AH))
  out=cli.observe({**CHOSEN,'actor':'AUV','target':'FRA'},lib)
  self.assertEqual(cli.result_code(out),0,out['errors']);self.assertEqual(out['samples'][0]['task']['endpoint_10'],hex(TH))
 def test_other_vtable_removed_or_reused_full_endpoint_is_unknown(self):
  for off,raw in ((0,struct.pack('<Q',BASE+0x1cde020)),(0x28,b'\1'),(0x10,struct.pack('<Q',handle('FRA',8,2)))):
   lib=FakeLibraries();lib.memory.change(P,off,raw);self.unknown(cli.observe(CHOSEN,lib))
 def test_one_sided_or_different_pointer_is_unknown(self):
  lib=FakeLibraries();lib.memory.put(T+0x16f8,bytes(16));self.unknown(cli.observe(CHOSEN,lib))
  lib=FakeLibraries();lib.memory.put(IT,struct.pack('<i4xQ',8,P+0x100));self.unknown(cli.observe(CHOSEN,lib))
 def test_duplicate_negative_capacity_or_key_fail(self):
  for header,entries in ((struct.pack('<Qii',IA,2,2),struct.pack('<i4xQ',19,P)*2),
    (struct.pack('<Qii',IA,-1,1),struct.pack('<i4xQ',19,P)),(struct.pack('<Qii',IA,1,1),struct.pack('<i4xQ',-1,P))):
   lib=FakeLibraries();lib.memory.put(A+0x16f8,header);lib.memory.put(IA,entries);self.unknown(cli.observe(CHOSEN,lib))
 def test_misaligned_task_pointer_is_unknown(self):
  lib=FakeLibraries();lib.memory.put(IA,struct.pack('<i4xQ',19,P+1));lib.memory.put(IT,struct.pack('<i4xQ',8,P+1))
  self.unknown(cli.observe(CHOSEN,lib))
 def test_complete_pair_root_owner_and_other_handle_guards(self):
  for address,off,raw in ((A+0x14f8,0x10,struct.pack('<Q',T)),
    (A+0x3000,19*0x48+0x10,struct.pack('<Q',handle('AUV',19,2))),
    (A+0x3000,19*0x48,struct.pack('<Q',T+0x14f8))):
   lib=FakeLibraries();lib.memory.change(address,off,raw);self.unknown(cli.observe(CHOSEN,lib))
 def test_country1510_or_typed_header_changes_fail(self):
  for address,off,raw in ((A+0x14f8,0x18,struct.pack('<Q',A+0x3008)),(A,0,struct.pack('<Q',BASE+1)),
    (T,0x20,struct.pack('<Q',handle('AUV',20)))):
   lib=FakeLibraries();lib.memory.change(address,off,raw);self.unknown(cli.observe(CHOSEN,lib))
 def test_table_a_to_b_during_country_resolution_fails(self):
  lib=FakeLibraries();alt=T+0x10000;lib.memory.put(alt,lib.memory.blocks[T])
  lib.memory.hook=lambda a,s,b,n:struct.pack('<Q',alt) if (a,s)==(TABLE+19*8,8) else b
  self.unknown(cli.observe(CHOSEN,lib))
 def test_two_tables_and_raw_task_changes_do_not_commit(self):
  lib=FakeLibraries();lib.memory.hook=lambda a,s,b,n: b[:8]+struct.pack('<Q',A)+b[16:] if (a,s,n)==(TABLE,1380*8,2) else b
  self.unknown(cli.observe(CHOSEN,lib))
  lib=FakeLibraries();lib.memory.hook=lambda a,s,b,n:b[:0x20]+struct.pack('<I',1)+b[0x24:] if (a,s,n)==(P,0x48,2) else b
  self.unknown(cli.observe(CHOSEN,lib))
 def test_loaded_code_and_relocated_slot_mismatch_before_or_after(self):
  for offset in (0x51b6e0,0xa6a780,cli.SLOT,cli.LEAF):
   for when in (1,2):
    lib=FakeLibraries();lib.memory.hook=lambda a,s,b,n:bytes(len(b)) if a==BASE+offset and n==when else b
    out=cli.observe(CHOSEN,lib);self.unknown(out);self.assertEqual(lib.closes,1)
 def test_short_rpm_records_failure_and_closes(self):
  lib=FakeLibraries();lib.memory.hook=lambda a,s,b,n:b[:-1] if a==P else b
  out=cli.observe(CHOSEN,lib);self.unknown(out)
  self.assertTrue(any(e['status']=='failed' for e in out['raw_ordered_read_journal']));self.assertEqual(lib.closes,1)
 def test_shared_budget_includes_host_code_and_tables(self):
  lib=FakeLibraries();out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
  journal=out['raw_ordered_read_journal'];budget=out['budget_accounting']['shared']
  self.assertEqual(len(journal),budget['calls']);self.assertEqual(sum(e['bytes'] for e in journal),budget['bytes'])
  self.assertEqual([e['ordinal'] for e in journal],list(range(1,len(journal)+1)))
  self.assertEqual({e['stage'] for e in journal},{'host_before','code_before','sample_1','sample_2','code_after','host_after'})
  self.assertEqual(lib.memory.counts[(TABLE,1380*8)],2)
  self.assertLessEqual(budget['calls'],4096);self.assertLessEqual(budget['bytes'],512*1024)
 def test_shared_budget_exhaustion_is_unknown(self):
  prior=NS['LIMITS'];NS['LIMITS']={**prior,'calls':50}
  try:self.unknown(cli.observe(CHOSEN,FakeLibraries()))
  finally:NS['LIMITS']=prior
 def test_pause_or_research_module_is_unknown(self):
  lib=FakeLibraries();lib.memory.change(PAUSE,0x48,b'\0');self.unknown(cli.observe(CHOSEN,lib))
  lib=FakeLibraries(research=True);self.unknown(cli.observe(CHOSEN,lib));self.assertEqual(lib.memory.reads,[])
 def test_host_after_change_is_unknown(self):
  lib=FakeLibraries();lib.memory.hook=lambda a,s,b,n:struct.pack('<Q',S+8) if (a,s,n)==(OUTER+0x40,8,2) else b
  out=cli.observe(CHOSEN,lib);self.unknown(out);self.assertTrue(out['selected_two_pass_equal'])
 def test_source_pre_and_postclose_guards(self):
  for when in (1,4):
   lib=FakeLibraries(fail_guard=when);out=cli.observe(CHOSEN,lib);self.unknown(out)
   self.assertEqual(lib.enters,0 if when==1 else 1)
   if when==4:self.assertTrue(out['normal_context_exit'])
 def test_close_failure_or_uncleared_handle_is_unknown(self):
  for kw in ({'close_error':True},{'stuck':True}):
   lib=FakeLibraries(**kw);out=cli.observe(CHOSEN,lib);self.unknown(out);self.assertEqual(lib.closes,1)
 def test_draft_runtime_denied_before_library_construction(self):
  self.assertFalse(cli.verify_sources()['runtime_capture_authorized'])
  out=cli.run('status',CHOSEN,library_factory=lambda *_:self.fail('draft must reject before library'))
  self.assertEqual(cli.result_code(out),2);self.assertIn('production seal',out['errors'][0]['message'])
 def test_invalid_identity_rejected_before_files(self):
  for key,value in (('pid',True),('pid',0),('pid',1<<32),('creation','0'*16),('creation','F'*16),('target','FRA'),('actor','frA')):
   with patch.object(cli,'verify_sources',side_effect=AssertionError('must not read')):
    self.assertEqual(cli.result_code(cli.run('status',{**CHOSEN,key:value})),2)
 def test_source_mutation_rejected_before_exact_import(self):
  original=cli.pin
  def changed(path):
   p=original(path)
   if Path(path)==HERE/'README.md':p={**p,'sha256':'0'*64}
   return p
  with patch.object(cli,'pin',side_effect=changed):
   out=cli.run('check',library_factory=lambda *_:self.fail('changed source must reject'))
   self.assertEqual(cli.result_code(out),2)
 def test_strict_exit_mapping_never_confuses_absence_or_effect(self):
  out=cli.observe(CHOSEN,FakeLibraries(False));self.assertEqual(cli.result_code(out),0)
  for key,value in (('selected_task_present',0),('selected_task_present',True),('selected_effect_verified',True),('commit_after_context_exit',1)):
   self.assertEqual(cli.result_code({**out,key:value}),2)
 def test_absence_does_not_read_task_or_type_other_entries(self):
  lib=FakeLibraries(False);out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
  self.assertNotIn((P,0x48),lib.memory.reads)

if __name__=='__main__':unittest.main(verbosity=2)
