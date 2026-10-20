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
import support_heir_current_observer as cli
for n,h in cli.FIXED.items():assert cli.pin(cli.ROOT/n)['sha256']==h
DIRECT=cli.exact_compile(cli.DIRECT,cli.pin(cli.ROOT/cli.DIRECT))
R24=DIRECT.exact_compile(DIRECT.R24,DIRECT.pin(cli.ROOT/DIRECT.R24))
HOST=DIRECT.exact_compile(DIRECT.HOST,DIRECT.pin(cli.ROOT/DIRECT.HOST))
CODES=cli.code_buffers()
path=cli.ROOT/cli.OBSERVER;raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==cli.FIXED[cli.OBSERVER]
NAMES={'ptr','full_handle','BudgetReader','roots','country','relation'}
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
   self.put(address+0x14f8+0x140,struct.pack('<Qii',arr,1,1) if present else bytes(16))
   self.put(arr,struct.pack('<i4xQ',otherslot,P))
  task=bytearray(0x40);struct.pack_into('<Q',task,0,BASE+cli.VT);struct.pack_into('<I',task,8,357)
  struct.pack_into('<QQI',task,0x10,AH,TH,0xfedcba98);struct.pack_into('<I',task,0x24,123);struct.pack_into('<QII',task,0x30,0x12345678,0xffffffff,91);self.put(P,task)
  self.put(BASE+0x233fe78,struct.pack('<Q',G));self.put(BASE+0x233d8d0,struct.pack('<Q',D))
  game=bytearray(0x7500);struct.pack_into('<Q',game,0,BASE+0x1cb00c8);struct.pack_into('<i',game,0x1dd0,123456)
  struct.pack_into('<Q',game,0x1e00,S);struct.pack_into('<Q',game,0x1e60,AH);struct.pack_into('<Q',game,0x1e68,0x2d2d2d)
  self.put(G,game);db=bytearray(0x128);struct.pack_into('<Qii',db,0x118,TABLE,1380,1380);self.put(D,db)
  server=bytearray(0x420);struct.pack_into('<Q',server,0,BASE+0x1cb8460);struct.pack_into('<Q',server,0x418,PAUSE);self.put(S,server)
  pause=bytearray(0x58);pause[0x48]=1;struct.pack_into('<Q',pause,0x50,S);self.put(PAUSE,pause)
  self.put(BASE+0x242bf50,struct.pack('<Q',OUTER));outer=bytearray(0x88)
  struct.pack_into('<Q',outer,0,BASE+0x1c48bf8);struct.pack_into('<Q',outer,0x10,BASE+0x1c48c80);struct.pack_into('<Q',outer,0x40,S);self.put(OUTER,outer)
  self.put(BASE+HOST.ENTRY_RVA,HOST.PREFIX)
  for rva,b in CODES:self.put(BASE+rva,b)
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


def put_index(lib,side,entries):
 country,arr=(A,IA) if side=='left' else (T,IT)
 lib.memory.put(country+0x14f8+0x140,struct.pack('<Qii',arr,len(entries),len(entries)) if entries else bytes(16))
 if entries:lib.memory.put(arr,b''.join(struct.pack('<i4xQ',k,v) for k,v in entries))


class SupportTests(unittest.TestCase):
 def unknown(self,out):
  self.assertEqual(cli.result_code(out),2,out);self.assertEqual(out['status'],'unknown')
  self.assertIsNone(out['selected_task_present']);self.assertFalse(out['commit_after_context_exit'])

 def test_missing_null_combinations_preserve_key_presence(self):
  for left_present in (False,True):
   for right_present in (False,True):
    lib=FakeLibraries(False)
    put_index(lib,'left',[(19,0)] if left_present else [])
    put_index(lib,'right',[(8,0)] if right_present else [])
    out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
    self.assertEqual(out['status'],'selected_task_absent');self.assertIs(out['selected_task_present'],False)
    sample=out['samples'][0]
    self.assertIs(sample['forward_index']['key_present'],left_present)
    self.assertIs(sample['reverse_index']['key_present'],right_present)
    self.assertEqual(sample['forward_index']['lookup_zero_reason'],'matched_null_value' if left_present else 'missing_key')
    self.assertNotIn((P,0x40),lib.memory.reads)

 def test_null_nonnull_and_different_nonnull_are_unknown(self):
  for left,right in ((0,P),(P,0),(P,P+0x100)):
   lib=FakeLibraries();put_index(lib,'left',[(19,left)]);put_index(lib,'right',[(8,right)])
   self.unknown(cli.observe(CHOSEN,lib))
   self.assertNotIn((P,0x40),lib.memory.reads)

 def test_present_raw_fields_and_unlabeled_reversed_endpoints(self):
  lib=FakeLibraries();lib.memory.change(P,0x10,struct.pack('<QQ',TH,AH))
  out=cli.observe({**CHOSEN,'actor':'AUV','target':'FRA'},lib)
  self.assertEqual(cli.result_code(out),0,out['errors']);self.assertIs(out['selected_task_present'],True)
  t=out['samples'][0]['task'];self.assertEqual(t['endpoint1_at_10'],hex(TH))
  self.assertEqual((t['raw_u32_at_08'],t['raw_u32_at_20'],t['raw_u32_at_24'],t['raw_u64_at_30'],t['raw_u32_at_38'],t['raw_u32_at_3c']),
   (357,0xfedcba98,123,'0x12345678',0xffffffff,91))
  self.assertNotIn('supporter',t);self.assertNotIn('date',t);self.assertFalse(t['endpoint_business_roles_verified'])
  for k in cli.FALSE_FLAGS:self.assertIs(out[k],False)
  self.assertEqual((lib.identity['pid'],lib.identity['creation']),(CHOSEN['pid'],CHOSEN['creation']))
  self.assertRegex(lib.identity['session'],'^[0-9a-f]{32}$')

 def test_extra_object_guards_are_unknown_not_absence(self):
  for off,b in ((0,struct.pack('<Q',BASE+0x1c816d8)),(8,struct.pack('<I',356)),(0x28,b'\1'),
   (0x10,struct.pack('<Q',handle('FRA',8,2)))):
   lib=FakeLibraries();lib.memory.change(P,off,b);self.unknown(cli.observe(CHOSEN,lib))

 def test_nullable_index_still_requires_bounds_uniqueness_and_pointer_shape(self):
  cases=[(struct.pack('<Qii',IA,2,2),struct.pack('<i4xQ',19,0)*2),
   (struct.pack('<Qii',IA,1,1),struct.pack('<i4xQ',-1,0)),
   (struct.pack('<Qii',IA,-1,0),b''),
   (struct.pack('<Qii',IA,0,1),struct.pack('<i4xQ',19,0)),
   (struct.pack('<Qii',IA,1,1),struct.pack('<i4xQ',19,P+1))]
  for header,entries in cases:
   lib=FakeLibraries(False);lib.memory.put(A+0x14f8+0x140,header)
   if entries:lib.memory.put(IA,entries)
   self.unknown(cli.observe(CHOSEN,lib))

 def test_unselected_entries_are_not_typed_or_dereferenced(self):
  lib=FakeLibraries(False);put_index(lib,'left',[(17,P),(19,0)]);put_index(lib,'right',[(17,0)])
  lib.memory.change(P,0,struct.pack('<Q',BASE+0x1c816d8))
  out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
  self.assertNotIn((P,0x40),lib.memory.reads)

 def test_null_absence_cannot_hide_row_or_table_rebinding(self):
  for change in ('row','table'):
   lib=FakeLibraries(False)
   if change=='row':lib.memory.change(A+0x3000,19*0x48+0x10,struct.pack('<Q',handle('AUV',19,2)))
   else:
    alt=T+0x10000;lib.memory.put(alt,lib.memory.blocks[T])
    lib.memory.hook=lambda a,s,b,n:struct.pack('<Q',alt) if (a,s)==(TABLE+19*8,8) else b
   self.unknown(cli.observe(CHOSEN,lib))

 def test_equal_zero_values_with_changed_key_presence_fail_two_pass(self):
  lib=FakeLibraries(False);put_index(lib,'left',[(19,0)]);put_index(lib,'right',[(8,0)])
  def change(a,s,b,n):
   if (a,s)==(IA,16) and n==2:return struct.pack('<i4xQ',17,0)
   return b
  lib.memory.hook=change;self.unknown(cli.observe(CHOSEN,lib))

 def test_raw_object_change_or_short_read_cannot_commit(self):
  for short in (False,True):
   lib=FakeLibraries()
   lib.memory.hook=lambda a,s,b,n:b[:-1] if short and a==P else b[:0x24]+struct.pack('<I',124)+b[0x28:] if (a,s,n)==(P,0x40,2) else b
   out=cli.observe(CHOSEN,lib);self.unknown(out);self.assertEqual(lib.closes,1)

 def test_both_exact_loaded_code_ranges_guard_pre_and_post(self):
  for offset in (0x595120,0xa69ab0):
   for when in (1,2):
    lib=FakeLibraries();lib.memory.hook=lambda a,s,b,n:bytes(len(b)) if a==BASE+offset and n==when else b
    self.unknown(cli.observe(CHOSEN,lib));self.assertEqual(lib.closes,1)

 def test_zero_result_never_commits_after_source_or_close_failure(self):
  for kw in ({'fail_guard':1},{'fail_guard':4},{'close_error':True},{'stuck':True}):
   lib=FakeLibraries(False,**kw);out=cli.observe(CHOSEN,lib);self.unknown(out)
   if kw.get('fail_guard')==1:self.assertEqual(lib.enters,0)
   else:self.assertEqual(lib.closes,1)

 def test_shared_journal_accounts_nullable_index_and_8616_loaded_bytes(self):
  lib=FakeLibraries(False);put_index(lib,'left',[(19,0)]);put_index(lib,'right',[(8,0)])
  out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
  rows=out['raw_ordered_read_journal'];b=out['budget_accounting']['shared']
  self.assertEqual((len(rows),sum(r['bytes'] for r in rows)),(b['calls'],b['bytes']))
  self.assertEqual(sum(r['bytes'] for r in rows if r['stage'] in ('code_before','code_after')),8616)
  self.assertEqual(lib.memory.counts[(TABLE,1380*8)],2)
  self.assertEqual([r['ordinal'] for r in rows],list(range(1,len(rows)+1)))
  self.assertLessEqual(b['calls'],4096);self.assertLessEqual(b['bytes'],512*1024)
  prior=NS['LIMITS'];NS['LIMITS']={**prior,'calls':50}
  try:self.unknown(cli.observe(CHOSEN,FakeLibraries(False)))
  finally:NS['LIMITS']=prior

 def test_draft_gate_and_top_level_review_shape_without_nested_candidate(self):
  out=cli.run('status',CHOSEN,library_factory=lambda *_:self.fail('draft must reject before Libraries'))
  self.assertEqual(cli.result_code(out),2);self.assertIn('production seal',out['errors'][0]['message'])
  original=cli.json_file;m=original(cli.MANIFEST)
  synthetic={**m,'sealed':True,'runtime_capture_authorized':True,
   'independent_source_review':dict(path=cli.R50_REVIEW,**cli.pin(cli.ROOT/cli.R50_REVIEW))}
  # Only verify the metadata shape against a synthetic in-memory manifest. No runtime factory is constructed.
  with patch.object(cli,'json_file',side_effect=lambda p:synthetic if Path(p)==cli.MANIFEST else original(p)):
   self.assertTrue(cli.verify_sources(runtime=True)['sealed'])
  self.assertNotIn('independent_reviews',m)

 def test_identity_and_changed_sources_reject_before_libraries(self):
  for key,value in (('pid',True),('pid',0),('pid',1<<32),('creation','0'*16),('creation','F'*16),('target','FRA')):
   with patch.object(cli,'verify_sources',side_effect=AssertionError('No file check expected')):
    self.assertEqual(cli.result_code(cli.run('status',{**CHOSEN,key:value})),2)
  original=cli.pin
  def changed(path):
   value=original(path)
   return {**value,'sha256':'0'*64} if Path(path)==HERE/'README.md' else value
  with patch.object(cli,'pin',side_effect=changed):
   out=cli.run('check',library_factory=lambda *_:self.fail('Sources changed before library'))
   self.assertEqual(cli.result_code(out),2)

 def test_current_zero_is_successful_observation_not_effect(self):
  out=cli.observe(CHOSEN,FakeLibraries(False));self.assertEqual(cli.result_code(out),0)
  for key,value in (('selected_task_present',0),('selected_task_present',True),('selected_effect_verified',True),('commit_after_context_exit',1)):
   self.assertEqual(cli.result_code({**out,key:value}),2)
  self.assertEqual(out['requests_published'],0)


if __name__=='__main__':unittest.main(verbosity=2)

