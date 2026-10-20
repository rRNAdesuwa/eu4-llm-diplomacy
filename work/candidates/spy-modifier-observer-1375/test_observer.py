"""Sparse-memory tests only: no real process, CLI, native call or filesystem publish."""
import copy,json,struct,unittest
from unittest.mock import patch
from pathlib import Path
import observer as o
REAL_SHA=o.sha
def mock_disk_sha(path):
 return o.EXE_SHA if Path(path).resolve()==(o.ROOT.parent/'eu4.exe').resolve() else REAL_SHA(path)

class Memory:
 def __init__(self):self.data={};self.reads=[];self.hook=None
 def put(self,p,b):self.data.update({p+i:v for i,v in enumerate(b)})
 def q(self,p,v):self.put(p,struct.pack('<Q',v))
 def i(self,p,v):self.put(p,struct.pack('<i',v))
 def b(self,p,v):self.put(p,bytes([v]))
 def read(self,p,n):
  self.reads.append((p,n))
  if self.hook:self.hook(p,n)
  try:return bytes(self.data[p+i] for i in range(n))
  except KeyError as e:raise o.ReadError('unmapped mock byte') from e

class Fixture:
 BASE=0x140000000;GAME=0x70000000;DB=0x70100000;ARRAY=0x70200000
 ACTOR=0x71000000;TARGET=0x71100000;REG=0x72000000;DEFAULT=0x72100000
 DEF=0x72200000;NAME=0x72300000;CAP=0x73000000;REL=0x73100000
 AGG=0x73200000;TRANSROOT=0x73300000;NODE=0x74000000;OBJ=0x74100000
 def __init__(self,family='corrupt_officials'):
  self.family=family;self.c=o.contract();self.p=self.c['families'][family];self.m=Memory();m=self.m;b=self.BASE
  for row in self.c['instruction_pins']:m.put(b+int(row['rva'],16),bytes.fromhex(row['bytes']))
  m.q(b+0x233d8d0,self.DB);m.q(b+0x233fe78,self.GAME);m.q(self.DB+0x118,self.ARRAY);m.i(self.DB+0x124,300)
  m.i(self.GAME+0x1dd0,56456976);m.q(self.GAME+0x1e60,o.HANDLES['FRA']);m.b(self.GAME+0x7485,0);m.q(self.GAME+0x74c8,0)
  for tag,addr in [('FRA',self.ACTOR),('ENG',self.TARGET)]:
   m.q(self.ARRAY+((o.HANDLES[tag]>>32)&65535)*8,addr);m.q(addr+0x20,o.HANDLES[tag]);m.q(addr+0x18f0,0)
  m.q(b+0x242bd08,self.REG);m.q(b+0x2458c68,self.DEFAULT);m.q(self.REG+self.p['registry_slot'],self.DEF);m.b(self.REG+self.p['registry_slot']+8,1)
  # Synthetic readonly vtable: registry/name/constant90 contract, no claim that
  # this is the actual runtime concrete definition subtype.
  m.q(self.DEF,b+0x1c48378);m.q(b+0x1c48378+0x90,b+0x8f440)
  self.name(self.DEF+0x158,self.p['definition_key'],self.NAME)
  m.q(self.ACTOR+0x2440,self.CAP);m.b(self.CAP+self.p['capability_offset'],1)
  m.q(self.ACTOR+0x1510,self.REL);slot=(o.HANDLES['ENG']>>32)&65535;self.record=self.REL+slot*0x48
  m.q(self.record+8,o.HANDLES['FRA']);m.q(self.record+0x10,o.HANDLES['ENG']);m.put(self.record+0x18,struct.pack('<h',10000))
  m.i(b+self.p['base_cost_rva'],25000);m.i(b+self.p['duration_rva'],60 if self.p['duration_to_days']==30 else 1825)
  m.i(self.ACTOR+0x28c8,0);m.q(b+0x2358080,self.TRANSROOT);m.q(self.TRANSROOT+0xe4a0,0)
  a=self.ACTOR+0x28d0;m.b(a+0x10,0);m.q(a+0x58,self.AGG);m.i(a+0x64,1);m.put(self.AGG,struct.pack('<ii',0x261,0))
  m.q(self.TARGET+0x1f0,0);m.q(self.TARGET+0x1f8,0);m.i(self.TARGET+0x200,0)
 def name(self,address,text,storage):
  raw=bytearray(32);data=text.encode()
  if len(data)<16:raw[:len(data)+1]=data+b'\0';struct.pack_into('<QQ',raw,16,len(data),15)
  else:struct.pack_into('<Q',raw,0,storage);struct.pack_into('<QQ',raw,16,len(data),max(31,len(data)));self.m.put(storage,data+b'\0')
  self.m.put(address,bytes(raw))
 def modifier(self,*,vt=None,assoc=0,expiry=None,flag=0):
  self.m.q(self.TARGET+0x1f0,self.NODE);self.m.q(self.TARGET+0x1f8,self.NODE);self.m.i(self.TARGET+0x200,1)
  self.m.put(self.NODE,struct.pack('<QQQB',self.OBJ,0,0,flag))
  self.m.q(self.OBJ,vt or self.BASE+0x1ce8040)
  self.m.i(self.OBJ+8,0x165);self.m.q(self.OBJ+0x30,self.DEF);self.m.q(self.OBJ+0x38,assoc)
  duration=60 if self.p['duration_to_days']==30 else 1825
  self.m.i(self.OBJ+0x44,expiry if expiry is not None else 56456976+duration*self.p['duration_to_days']*24)
 def capture(self):return o.capture(self.m,self.BASE,family=self.family,target='ENG')
 def snap(self):return self.capture()['snapshot']

class SparseTests(unittest.TestCase):
 def test_five_exact_families(self):
  for f in o.contract()['families']:
   with self.subTest(f=f):
    x=Fixture(f).capture();self.assertTrue(x['selected']['complete_selected_absence_supported']);self.assertEqual(x['snapshot']['cost']['final_milli_candidate'],25000)
    self.assertLess(x['read_budget']['bytes'],20000);self.assertTrue(all(x[k] is False for k in o.FALSE_CLAIMS))
 def test_same_day_new_modifier_and_cost(self):
  f=Fixture();before=f.snap();f.modifier();f.m.put(f.record+0x18,struct.pack('<h',7500));after=f.snap()
  out=o.compare_snapshots(before,after);self.assertEqual(out['new_exact_expiry_count'],1);self.assertTrue(out['static_cost_delta_matches']);self.assertTrue(out['before_absent']);self.assertFalse(out['request_causality_verified'])
 def test_cost_modifier_sparse_half(self):
  f=Fixture();f.m.put(f.AGG,struct.pack('<ii',0x261,-500));self.assertEqual(f.snap()['cost']['final_milli_candidate'],12500)
 def test_cost_sparse_missing_id(self):
  f=Fixture();f.m.put(f.AGG,struct.pack('<ii',5,123));self.assertEqual(f.snap()['cost']['final_milli_candidate'],25000)
 def test_lazy_cost_no_aggregate_reads(self):
  f=Fixture();f.m.i(f.ACTOR+0x28c8,1);x=f.snap();self.assertIsNone(x['cost']['aggregate']);self.assertIsNone(x['cost']['final_milli_candidate']);self.assertFalse(any(p==f.AGG for p,n in f.m.reads))
 def test_dynamic_transform_unknown(self):
  f=Fixture();f.m.q(f.TRANSROOT+0xe4a0,0x75000000);x=f.snap();self.assertIsNone(x['cost']['final_milli_candidate']);self.assertFalse(any(p==0x75000000 for p,n in f.m.reads))
 def test_dense_never_indexes_payload(self):
  f=Fixture();f.m.b(f.ACTOR+0x28e0,1);f.m.q(f.ACTOR+0x2928,0);x=f.snap();self.assertIsNone(x['cost']['final_milli_candidate'])
 def test_capability_absent_or_zero_not_legality(self):
  f=Fixture();f.m.q(f.ACTOR+0x2440,0);self.assertIsNone(f.snap()['capability']['raw'])
  f=Fixture();f.m.b(f.CAP+f.p['capability_offset'],0);x=f.capture();self.assertEqual(x['snapshot']['capability']['raw'],0);self.assertFalse(x['native_legality_verified'])
 def test_registry_default_and_uninitialized(self):
  for mode in ('default','flag','null','method','name'):
   f=Fixture()
   if mode=='default':f.m.q(f.REG+f.p['registry_slot'],f.DEFAULT)
   if mode=='flag':f.m.b(f.REG+f.p['registry_slot']+8,0)
   if mode=='null':f.m.q(f.REG+f.p['registry_slot'],0)
   if mode=='method':f.m.q(f.BASE+0x1c48378+0x90,f.BASE+0x8f450)
   if mode=='name':f.name(f.DEF+0x158,'wrong',f.NAME)
   with self.subTest(mode=mode),self.assertRaises(o.ReadError):f.capture()
 def test_string_sso_and_heap(self):
  f=Fixture();f.name(0x76000000,'short',0x76100000);r=o.Budget(f.m);self.assertEqual(o.read_name(r,0x76000000)['text'],'short');self.assertEqual(o.read_name(r,f.DEF+0x158)['text'],'corrupt_officials')
 def test_string_bounds_terminator(self):
  for change in ('length','capacity','nul'):
   f=Fixture()
   if change=='length':f.m.q(f.DEF+0x168,129)
   if change=='capacity':f.m.q(f.DEF+0x170,8)
   if change=='nul':f.m.b(f.NAME+len(f.p['definition_key']),65)
   with self.subTest(change=change),self.assertRaises(o.ReadError):f.capture()
 def test_identity_rejections(self):
  for addr,value,width in [(Fixture.GAME+0x1e60,o.HANDLES['ENG'],8),(Fixture.TARGET+0x20,0x474e45,8),(Fixture.DB+0x124,40,4),(Fixture.TARGET+0x18f0,o.HANDLES['FRA'],8),(Fixture.GAME+0x7485,1,1)]:
   f=Fixture();getattr(f.m,{8:'q',4:'i',1:'b'}[width])(addr,value)
   with self.subTest(addr=addr),self.assertRaises(o.ReadError):f.capture()
 def test_relation_direction_and_negative_network(self):
  f=Fixture();f.m.q(f.record+8,o.HANDLES['ENG'])
  with self.assertRaises(o.ReadError):f.capture()
  f=Fixture();f.m.put(f.record+0x18,struct.pack('<h',-1))
  with self.assertRaises(o.ReadError):f.capture()
 def test_unknown_object_not_dereferenced_or_absent(self):
  f=Fixture();f.modifier(vt=f.BASE+0x1c48000);x=f.capture();self.assertTrue(x['selected']['unknown_objects_or_selected_semantics']);self.assertFalse(x['selected']['complete_selected_absence_supported']);self.assertFalse(any(f.OBJ<p<f.OBJ+0x50 for p,n in f.m.reads))
 def test_removed_flag_rejected_before_object(self):
  f=Fixture();f.modifier(flag=1)
  with self.assertRaises(o.ReadError):f.capture()
  self.assertFalse(any(p==f.OBJ for p,n in f.m.reads))
 def test_expired_present_is_not_absence(self):
  f=Fixture();f.modifier(expiry=56456975);x=f.capture();self.assertFalse(x['selected']['matching'][0]['active_by_expiry_comparison']);self.assertFalse(x['selected']['complete_selected_absence_supported'])
 def test_selected_association_or_invalid_expiry_unknown(self):
  for kw in ({'assoc':0x76000000},{'expiry':-1},{'expiry':0}):
   f=Fixture();f.modifier(**kw);self.assertTrue(f.capture()['selected']['unknown_objects_or_selected_semantics'])
 def test_list_structural_bounds(self):
  for mode in ('count','cycle','prev','tail','type'):
   f=Fixture();f.modifier()
   if mode=='count':f.m.i(f.TARGET+0x200,257)
   if mode=='cycle':f.m.q(f.NODE+0x10,f.NODE)
   if mode=='prev':f.m.q(f.NODE+8,f.NODE)
   if mode=='tail':f.m.q(f.TARGET+0x1f8,f.NODE+32)
   if mode=='type':f.m.i(f.OBJ+8,0)
   with self.subTest(mode=mode),self.assertRaises(o.ReadError):f.capture()
 def test_two_pass_change(self):
  f=Fixture();hits=0
  def hook(p,n):
   nonlocal hits
   if p==f.GAME+0x1dd0:
    hits+=1
    if hits==3:f.m.i(p,56457000)
  f.m.hook=hook
  with self.assertRaises(o.ReadError):f.capture()
 def test_code_pin_change(self):
  f=Fixture();f.m.b(f.BASE+int(f.c['instruction_pins'][0]['rva'],16),0)
  with self.assertRaises(o.ReadError):f.capture()
 def test_positive_only_and_fixed_arguments(self):
  for kwargs in ({'value':False},{'value':1},{'family':'steal_technology'},{'target':'FRA'},{'target':True}):
   f=Fixture()
   with self.subTest(kwargs=kwargs),self.assertRaises(o.ReadError):o.capture(f.m,f.BASE,**kwargs)
 def test_budget_shortread_pointer(self):
  f=Fixture();r=o.Budget(f.m)
  for p,n in [(True,8),(0x10000,False),(0x10000,65537),(0x7fffffffffff,2)]:
   with self.assertRaises(o.ReadError):r.read(p,n)
  r.bytes=o.MAX_TOTAL
  with self.assertRaises(o.ReadError):r.read(f.GAME,1)
  r=o.Budget(f.m);r.trace=[None]*o.MAX_READS
  with self.assertRaises(o.ReadError):r.read(f.GAME,1)
  class Short:
   def read(self,p,n):return b''
  with self.assertRaises(o.ReadError):o.Budget(Short()).read(0x10000,1)
 def test_all_imported_int_fields_reject_bool_float(self):
  f=Fixture();f.modifier();original=f.snap();paths=[]
  def walk(x,p):
   if type(x) is int:paths.append(p)
   elif type(x) is dict:
    for k,v in x.items():walk(v,p+[k])
   elif type(x) is list:
    for k,v in enumerate(x):walk(v,p+[k])
  walk(original,[]);self.assertGreater(len(paths),60)
  for path in paths:
   for conversion in (bool,float):
    bad=copy.deepcopy(original);parent=bad
    for k in path[:-1]:parent=parent[k]
    parent[path[-1]]=conversion(parent[path[-1]])
    with self.subTest(path=path,conversion=conversion),self.assertRaises(o.ReadError):o.inspect(bad)
 def test_missing_extra_keys_rejected(self):
  x=Fixture().snap()
  for key in x:
   bad=copy.deepcopy(x);del bad[key]
   with self.assertRaises(o.ReadError):o.inspect(bad)
  bad=copy.deepcopy(x);bad['legality']=True
  with self.assertRaises(o.ReadError):o.inspect(bad)
 def test_comparison_rejects_cross_day_family_and_forged_cost(self):
  before=Fixture().snap()
  for change in ('date','family','cost'):
   after=copy.deepcopy(before)
   if change=='date':after['identity']['date']+=24;after['cost']['expected_expiry']+=24
   if change=='family':after['family']='sow_discontent'
   if change=='cost':after['cost']['final_milli_candidate']=0
   with self.subTest(change=change),self.assertRaises(o.ReadError):o.compare_snapshots(before,after)
 def test_no_refresh_claim_and_wrong_expiry(self):
  f=Fixture();before=f.snap();f.modifier(expiry=56456976+5);out=o.compare_snapshots(before,f.snap());self.assertEqual(out['new_exact_expiry_count'],0);self.assertFalse(out['refresh_or_stacking_verified'])
 def test_expiry_overflow(self):
  f=Fixture();f.m.i(f.GAME+0x1dd0,2**31-2)
  with self.assertRaises(o.ReadError):f.capture()
 def test_sparse_duplicate_and_limit(self):
  f=Fixture();f.m.i(f.ACTOR+0x2934,4097)
  with self.assertRaises(o.ReadError):f.capture()
  f=Fixture();f.m.i(f.ACTOR+0x2934,2);f.m.put(f.AGG,struct.pack('<iiii',0x261,0,0x261,0))
  with self.assertRaises(o.ReadError):f.capture()

class FutureWrapperTests(unittest.TestCase):
 def setup_mocks(self):
  import sys
  sys.path.insert(0,str(o.ROOT));from work import probe_diplomacy_current as legacy
  f=Fixture();f.m.base=f.BASE;f.m.bytes_read=100;f.m.close=lambda:setattr(f.m,'closed',True);f.m.closed=False
  sig={'timestamp':f.c['pe']['timestamp'],'size':f.c['pe']['image_size']}
  return f,legacy,sig
 def test_future_wrapper_success_and_identity_twice(self):
  f,l,sig=self.setup_mocks();identity={'pid':1,'creation_filetime':'0000000000000001','exit_filetime':0,'module_base':f.BASE}
  with patch.object(o,'sha',side_effect=mock_disk_sha),patch.object(l,'verified_executable',return_value=({},sig)),patch.object(l,'ProcessReader',return_value=f.m),patch.object(l,'pe_signature',return_value=sig),patch.object(l,'verify_module_signature'),patch.object(o,'held_identity',return_value=identity) as held:
   result=o.sample_process(pid=1,creation='0000000000000001',executable=o.ROOT.parent/'eu4.exe');self.assertEqual(held.call_count,2);self.assertEqual(result['source_kind'],'held_process_readonly');self.assertFalse(result['runtime_verified'])
  self.assertTrue(f.m.closed)
 def test_future_wrapper_post_failure_closes(self):
  f,l,sig=self.setup_mocks()
  with patch.object(o,'sha',side_effect=mock_disk_sha),patch.object(l,'verified_executable',return_value=({},sig)),patch.object(l,'ProcessReader',return_value=f.m),patch.object(o,'held_identity',side_effect=[{'pid':1},{'pid':2}]):
   with self.assertRaises(o.ReadError):o.sample_process(pid=1,creation='0000000000000001',executable=o.ROOT.parent/'eu4.exe')
  self.assertTrue(f.m.closed)
 def test_invalid_identity_before_open(self):
  f,l,sig=self.setup_mocks()
  with patch.object(l,'ProcessReader') as open_:
   for pid,creation in [(True,'0000000000000001'),(1,'1'),(1,'0000000000000000')]:
    with self.assertRaises(o.ReadError):o.sample_process(pid=pid,creation=creation,executable=o.ROOT.parent/'eu4.exe')
   open_.assert_not_called()
if __name__=='__main__':unittest.main()
