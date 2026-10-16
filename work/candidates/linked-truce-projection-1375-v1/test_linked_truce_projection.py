"""New owned byte graphs and pure boundary tests only; no actual capture."""
import ast
import copy
import hashlib
from pathlib import Path
import re
import struct
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import linked_truce_projection as cli
for n,h in cli.FIXED.items():assert cli.pin(cli.ROOT/n)['sha256']==h
DIRECT=cli.exact_compile(cli.DIRECT,cli.pin(cli.ROOT/cli.DIRECT))
R24=DIRECT.exact_compile(DIRECT.R24,DIRECT.pin(cli.ROOT/DIRECT.R24))
CODES=cli.code_buffers()
OBSERVER_PATH=cli.ROOT/'bridge/diplomacy_effect_observer.py'
raw=OBSERVER_PATH.read_bytes();assert hashlib.sha256(raw).hexdigest()==cli.FIXED['bridge/diplomacy_effect_observer.py']
NAMES={'ptr','full_handle','BudgetReader','country','relation','index','dependency_key'}
tree=ast.parse(raw,str(OBSERVER_PATH))
definitions=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in NAMES]
assert {n.name for n in definitions}==NAMES
NS=dict(struct=struct,re=re,require=cli.require,COUNTRY_VT=0x1c574a0,
 LIMITS=dict(calls=4096,bytes=512*1024,single_read=65536,index_entries=256),
 digest=lambda b:hashlib.sha256(b).hexdigest())
exec(compile(ast.Module(body=definitions,type_ignores=[]),str(OBSERVER_PATH),'exec'),NS)
BASE,TABLE,A,T,L,OBJ,U=0x140000000,0x30000,0x40000,0x50000,0x60000,0x90000,0xa0000
def handle(tag,slot):return (1<<56)|(slot<<32)|int.from_bytes(tag.encode('ascii'),'little')
AH,TH,LH=handle('FRA',8),handle('AUV',19),handle('POR',27)
CHOSEN=dict(pid=12345,creation='0000000000000001',actor='FRA',target='AUV')


class Memory:
 def __init__(self,mode='A',direct=False,linked_cache=False,flag=None):
  self.blocks={};self.reads=[];self.hook=None;self.counts={}
  self.mode=mode;self.linked=AH if mode=='B' or mode=='self' else LH
  self.linked_address=A if self.linked==AH else L
  table=bytearray(1380*8)
  for address,h,slot in ((A,AH,8),(T,TH,19),(L,LH,27)):struct.pack_into('<Q',table,slot*8,address)
  self.table=bytes(table);self.put(TABLE,self.table)
  objects=((A,AH,8),(T,TH,19),(L,LH,27))
  for address,h,slot in objects:
   country=bytearray(0x28);struct.pack_into('<QI',country,0,BASE+0x1c574a0,357);struct.pack_into('<Q',country,0x20,h)
   self.put(address,country)
   link=cli.SENTINEL if address!=T or mode=='A' else self.linked
   self.put(address+0x18f0,struct.pack('<Q',link))
   root=bytearray(0x30);vec=address+0x3000
   struct.pack_into('<QI',root,0,BASE+0x1c4f5f8,357)
   struct.pack_into('<QQQQ',root,0x10,address,vec,vec+64*0x48,vec+64*0x48)
   self.put(address+0x14f8,root)
   records=bytearray(64*0x48)
   for otheraddr,other,otherslot in objects:
    struct.pack_into('<QQQ',records,otherslot*0x48,address+0x14f8,h,other)
    if address==A and other==TH:records[otherslot*0x48+0x45]=int(direct)
    if address==A and other==self.linked:records[otherslot*0x48+0x45]=int(linked_cache)
   self.put(vec,records)
   selected=None
   if mode!='A' and address==T:selected=(8 if self.linked==AH else 27)
   elif mode!='A' and address==self.linked_address:selected=19
   if selected is None:self.put(address+0x14f8+0x128,bytes(16))
   else:
    array=0xb0000+slot*0x100
    self.put(address+0x14f8+0x128,struct.pack('<Qii',array,1,1))
    self.put(array,struct.pack('<i4xQ',selected,OBJ))
  body=bytearray(0x48);struct.pack_into('<Q',body,0,BASE+0x1c81758)
  struct.pack_into('<I',body,8,0xabcdef) # dependency marker is deliberately not357
  struct.pack_into('<QQ',body,0x10,TH,self.linked);struct.pack_into('<Q',body,0x40,U)
  self.put(OBJ,body)
  key=bytearray(32);key[:7]=b'vassal\0';struct.pack_into('<QQ',key,16,6,15)
  self.put(U+0x10,key)
  self.put(U+0x11a,bytes([int(mode=='B') if flag is None else flag]))
  self.put(U+0x228,bytes(4))
  for rva,b in CODES:self.put(BASE+rva,b)
 def put(self,address,raw):self.blocks[address]=bytes(raw)
 def change(self,address,offset,raw):
  b=bytearray(self.blocks[address]);b[offset:offset+len(raw)]=raw;self.blocks[address]=bytes(b)
 def read(self,address,size):
  self.reads.append((address,size));self.counts[(address,size)]=self.counts.get((address,size),0)+1
  for begin,b in self.blocks.items():
   if begin<=address and address+size<=begin+len(b):
    raw=b[address-begin:address-begin+size]
    return self.hook(address,size,raw,self.counts[(address,size)]) if self.hook else raw
  raise ValueError('Synthetic read span missing '+hex(address)+'/'+str(size))


class FakeLibraries:
 def __init__(self,mode='A',direct=False,linked_cache=False,flag=None,close_error=False,stuck=False,fail_guard=0):
  self.memory=Memory(mode,direct,linked_cache,flag);self.codes=CODES;self.r24=R24;self.direct=DIRECT
  self.guards=self.enters=self.closes=0;self.fail_guard=fail_guard
  self.root=dict(array=hex(TABLE),count=1380,manual_pause=1,date=123)
  owner=self
  class Runtime:
   def __init__(self,identity,backend):
    owner.identity=copy.deepcopy(identity);self.base=BASE;self.initial_pins={'fake':True}
    self.held=types.SimpleNamespace(handle=123,injector=types.SimpleNamespace(GAME=cli.GAME))
    self.modules=[(BASE,str(cli.GAME))]
   def __enter__(self):owner.enters+=1;return self
   def __exit__(self,*_):
    owner.closes+=1
    if not stuck:self.held.handle=None
    if close_error:raise ValueError('Synthetic close failure')
  backend=types.SimpleNamespace(manifest={'dll':{'sha256':'a'*64}},manifest_sha='b'*64)
  self.module=types.SimpleNamespace(**{n:NS[n] for n in NAMES},COUNTRY_VT=0x1c574a0,DEPENDENCY_VT=0x1c81758,
   roots=lambda *_:copy.deepcopy(self.root),pins=lambda:{'fake':True},HeldRPMPort=lambda _:self.memory,
   RuntimeCapture=Runtime,TagCommandBackend=lambda:backend)
  self.host=types.SimpleNamespace(host_sample=lambda *_:dict(roots=copy.deepcopy(self.root),rpm_budget=dict(calls=0,bytes=0,largest=0)))
 def guard(self):
  self.guards+=1
  if self.guards==self.fail_guard:raise ValueError('Synthetic source mutation')
 def observer(self):self.guard();return self.module
 def evidence(self):return {'synthetic':True,'old_fixed_pid_authority_reused':False}


class ProjectionTests(unittest.TestCase):
 def assert_unknown(self,out):
  self.assertEqual(cli.result_code(out),2,out);self.assertIsNone(out['selected_native_return_projection']);self.assertFalse(out['commit_after_context_exit'])
 def test_A_true_and_false_success_and_no_action_claims(self):
  for state in (False,True):
   lib=FakeLibraries('A',state);out=cli.observe(CHOSEN,lib)
   self.assertEqual(cli.result_code(out),0,out['errors']);self.assertIs(out['selected_native_return_projection'],state)
   self.assertEqual(out['path'],'A_target_exact_sentinel');self.assertEqual((lib.enters,lib.closes),(1,1))
   for k in ('actual_native_predicate_evaluated','selected_effect_verified','peace_completion_verified','expiry_verified','native_ready','lifetime_lease','atomic_snapshot'):
    self.assertIs(out[k],False)
   self.assertEqual(out['native_game_calls'],0)
 def test_B_dependency_profile_uses_no_definition_type_or_marker_guess(self):
  for state in (False,True):
   lib=FakeLibraries('B',state);out=cli.observe(CHOSEN,lib)
   self.assertEqual(cli.result_code(out),0,out['errors']);self.assertIs(out['selected_native_return_projection'],state)
   dep=out['samples'][0]['dependency'];self.assertFalse(dep['definition_exact_class_size_vtable_proven'])
   self.assertEqual(dep['definition_key'],'vassal');self.assertEqual(out['path'],'B_linked_actor_byte11a_nonzero')
   self.assertNotIn((U,8),lib.memory.reads)
 def test_C_clear_linked_cache_yields_direct_false_and_true(self):
  for state in (False,True):
   lib=FakeLibraries('C',state);out=cli.observe(CHOSEN,lib)
   self.assertEqual(cli.result_code(out),0,out['errors']);self.assertIs(out['selected_native_return_projection'],state)
   self.assertEqual(out['path'],'C_independent_actor_zero_header_clear_linked_cache')
   self.assertEqual(out['samples'][0]['facts']['loaded_K'],15)
   for off in (0x30,0x38,0x48,0x50):self.assertNotIn((U+0x1c8+off,8),lib.memory.reads)
 def test_C_set_linked_cache_unknown_even_when_direct_true(self):
  lib=FakeLibraries('C',True,True);out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
  self.assertIn('clear',out['unsupported_reason']);self.assertEqual(lib.closes,1)
 def test_C_selfpair_is_unknown_without_self_record_read(self):
  lib=FakeLibraries('self',True,flag=0);out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
  self.assertNotIn((A+0x3000+8*0x48,0x48),lib.memory.reads)
 def test_nonempty_header_is_unknown_not_false(self):
  lib=FakeLibraries('C');lib.memory.change(U+0x228,2,b'\1');out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
  self.assertEqual(out['samples'][0]['facts']['definition_header']['0x62'],1)
 def test_actor_non_sentinel_does_not_use_empty_header_fallback(self):
  lib=FakeLibraries('C');lib.memory.put(A+0x18f0,struct.pack('<Q',LH));out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
  self.assertNotIn((U+0x229,1),lib.memory.reads)
 def test_zero_target_link_is_not_sentinel(self):
  lib=FakeLibraries('A');lib.memory.put(T+0x18f0,bytes(8));out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
  self.assertEqual(lib.closes,1)
 def test_dependency_bad_type_removed_or_endpoint_rejected(self):
  for off,raw in ((0,struct.pack('<Q',BASE+0x1234)),(0x28,b'\1'),(0x10,struct.pack('<Q',AH))):
   lib=FakeLibraries('C');lib.memory.change(OBJ,off,raw);out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
 def test_dependency_bilateral_mismatch_or_duplicate_index_rejected(self):
  lib=FakeLibraries('C');array=0xb0000+27*0x100;lib.memory.put(array,struct.pack('<i4xQ',19,OBJ+0x100));self.assert_unknown(cli.observe(CHOSEN,lib))
  lib=FakeLibraries('C');array=0xb0000+19*0x100
  lib.memory.put(T+0x14f8+0x128,struct.pack('<Qii',array,2,2));lib.memory.put(array,struct.pack('<i4xQ',27,OBJ)*2)
  self.assert_unknown(cli.observe(CHOSEN,lib))
 def test_dependency_key_terminator_and_unknown_definition_pointer(self):
  lib=FakeLibraries('C');lib.memory.change(U+0x10,6,b'x');self.assert_unknown(cli.observe(CHOSEN,lib))
  lib=FakeLibraries('C');lib.memory.change(OBJ,0x40,bytes(8));self.assert_unknown(cli.observe(CHOSEN,lib))
 def test_two_pass_raw_projection_difference_rejected(self):
  lib=FakeLibraries('B')
  lib.memory.hook=lambda a,s,b,n: b'\0' if (a,s,n)==(U+0x11a,1,2) else b
  self.assert_unknown(cli.observe(CHOSEN,lib));self.assertEqual(lib.closes,1)
 def test_loaded_K_change_after_sample_blocks_commit(self):
  lib=FakeLibraries('C')
  lib.memory.hook=lambda a,s,b,n:struct.pack('<Q',16) if (a,s,n)==(BASE+0x1dc1c98,8,2) else b
  out=cli.observe(CHOSEN,lib);self.assert_unknown(out);self.assertTrue(out['selected_two_pass_equal'])
 def test_loaded_code_mismatch_and_short_read_close(self):
  for short in (False,True):
   lib=FakeLibraries('A')
   lib.memory.hook=lambda a,s,b,n: b[:-1] if short and a==BASE+0x506d70 else (bytes(len(b)) if not short and a==BASE+0x506d70 else b)
   self.assert_unknown(cli.observe(CHOSEN,lib));self.assertEqual(lib.closes,1)
 def test_context_close_failure_or_uncleared_handle_never_commits(self):
  for kw in ({'close_error':True},{'stuck':True}):
   lib=FakeLibraries('A',**kw);out=cli.observe(CHOSEN,lib);self.assert_unknown(out);self.assertTrue(out['selected_two_pass_equal']);self.assertEqual(lib.closes,1)
 def test_source_guard_after_normal_close_blocks_commit(self):
  lib=FakeLibraries('A',fail_guard=4);out=cli.observe(CHOSEN,lib);self.assert_unknown(out)
  self.assertTrue(out['normal_context_exit']);self.assertEqual(lib.closes,1)
 def test_raw_order_journal_and_budget_are_replayable(self):
  lib=FakeLibraries('C',True);out=cli.observe(CHOSEN,lib);self.assertEqual(cli.result_code(out),0,out['errors'])
  journal=out['raw_ordered_read_journal'];self.assertEqual([e['ordinal'] for e in journal],list(range(1,len(journal)+1)))
  self.assertEqual(len(journal),out['budget_accounting']['selected']['calls'])
  self.assertEqual(sum(len(bytes.fromhex(e['raw_hex'])) for e in journal),out['budget_accounting']['selected']['bytes'])
  self.assertEqual([e['stage'] for e in journal[:5]],['code_before']*5)
  self.assertEqual([e['stage'] for e in journal[-5:]],['code_after']*5)
  self.assertEqual(len(bytes.fromhex(out['samples'][0]['country_pointer_table_raw_hex'])),1380*8)
  self.assertEqual(out['budget_accounting']['entry_PE_identity_bytes_excluded_from_selected'],8192)
  self.assertEqual(lib.identity['pid'],12345);self.assertNotEqual(lib.identity['pid'],80340)
 def test_budget_and_alignment_failure_do_not_escalate(self):
  prior=NS['LIMITS'];NS['LIMITS']={**prior,'bytes':3000}
  try:self.assert_unknown(cli.observe(CHOSEN,FakeLibraries('A')))
  finally:NS['LIMITS']=prior
  lib=FakeLibraries('C');lib.memory.change(OBJ,0x40,struct.pack('<Q',U+1));self.assert_unknown(cli.observe(CHOSEN,lib))
 def test_pure_missing_and_malformed_values_are_unknown(self):
  good=dict(actor_handle=hex(AH),target_handle=hex(TH),direct_pair_cache_flag_set=False,target_linked_handle=hex(cli.SENTINEL))
  self.assertIs(cli.project_facts(good)['selected_native_return_projection'],False)
  for key,value in (('direct_pair_cache_flag_set',0),('actor_handle',AH),('target_linked_handle','0x0')):
   bad={**good,key:value};self.assertFalse(cli.project_facts(bad)['supported'])
  b=dict(actor_handle=hex(AH),target_handle=hex(TH),direct_pair_cache_flag_set=True,target_linked_handle=hex(AH),dependency_guarded=True,dependency_key='vassal',definition_byte_11a=True)
  self.assertFalse(cli.project_facts(b)['supported'])
 def test_draft_manifest_status_rejected_before_libraries_or_process(self):
  m=cli.verify_sources();self.assertFalse(m['sealed'])
  out=cli.run('status',CHOSEN,library_factory=lambda *_:self.fail('draft cannot construct libraries'))
  self.assertEqual(cli.result_code(out),2);self.assertIn('source-ready',out['errors'][0]['message'])
 def test_bad_selection_is_rejected_before_source_or_libraries(self):
  for k,v in (('pid',True),('pid',1<<32),('creation','0'*16),('target','FRA')):
   with patch.object(cli,'verify_sources',side_effect=AssertionError('must not read')):
    out=cli.run('status',{**CHOSEN,k:v},library_factory=lambda *_:self.fail('bad selection'))
   self.assertEqual(cli.result_code(out),2)


if __name__=='__main__':unittest.main(verbosity=2)
