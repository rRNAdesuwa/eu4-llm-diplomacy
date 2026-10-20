"""Sparse fixtures only. All operating-system reader entries are mocked."""
import copy, json, struct, sys, unittest
from pathlib import Path
from unittest.mock import patch
import observer as o

class Memory:
 def __init__(self):self.data={};self.reads=[];self.hook=None;self.bytes_read=0;self.closed=False
 def put(self,p,b):self.data.update({p+i:v for i,v in enumerate(b)})
 def q(self,p,v):self.put(p,struct.pack('<Q',v))
 def i(self,p,v):self.put(p,struct.pack('<i',v))
 def b(self,p,v):self.put(p,bytes([v]))
 def read(self,p,n):
  self.reads.append((p,n));self.bytes_read+=n
  if self.hook:self.hook(p,n)
  try:return bytes(self.data[p+i] for i in range(n))
  except KeyError as e:raise o.ReadError('unmapped sparse memory') from e
 def close(self):self.closed=True

class Fixture:
 BASE=0x140000000;GAME=0x70000000;DB=0x70100000;ARRAY=0x70200000
 FRA=0x71000000;NAV=0x71100000;SUBJECTS=0x71200000
 LEFT=0x72000000;RIGHT=0x72100000;LROOT=0x72200000;RROOT=0x72300000;LINDEX=0x72400000;RINDEX=0x72500000
 REL=0x72600000;DEF=0x73000000;REG=0x74000000;SENTINEL=0x74100000;BUCKETS=0x74200000;VECTOR=0x74300000;NODE=0x74400000
 def __init__(self,relocated=False):
  self.m=Memory();self.c=o.contract()
  if relocated:self.BASE=0x145000000
  m=self.m;b=self.BASE;m.base=b
  for x in self.c['instruction_pins']:m.put(b+int(x['rva'],16),bytes.fromhex(x['bytes']))
  for x in self.c['data_pins']:
   raw=bytes.fromhex(x['bytes'])
   for j in range(0,len(raw),8):m.q(b+int(x['rva'],16)+j,struct.unpack_from('<Q',raw,j)[0]-0x140000000+b)
  m.q(b+0x233d8d0,self.DB);m.q(b+0x233fe78,self.GAME);m.q(self.DB+0x118,self.ARRAY);m.i(self.DB+0x124,300)
  m.i(self.GAME+0x1dd0,56456976);m.q(self.GAME+0x1e60,o.FRA);m.b(self.GAME+0x7485,0);m.q(self.GAME+0x74c8,0)
  for tag,p,h,overlord in [('FRA',self.FRA,o.FRA,0),('NAV',self.NAV,o.NAV,o.FRA)]:
   m.q(self.ARRAY+((h>>32)&65535)*8,p);m.q(p+0x20,h);m.q(p+0x18f0,overlord)
  m.q(self.FRA+0x1a18,self.SUBJECTS);m.q(self.FRA+0x1a20,self.SUBJECTS+8);m.q(self.SUBJECTS,o.NAV)
  for p,records,root,index,owner,other in [(self.FRA,self.LEFT,self.LROOT,self.LINDEX,o.FRA,o.NAV),(self.NAV,self.RIGHT,self.RROOT,self.RINDEX,o.NAV,o.FRA)]:
   m.q(p+0x1510,records);record=records+((other>>32)&65535)*0x48;m.q(record,root);m.q(record+8,owner);m.q(record+0x10,other)
   m.q(root+0x128,index);m.i(root+0x134,1);m.put(index,struct.pack('<I4xQ',(other>>32)&65535,self.REL))
  m.q(self.REL,b+0x1c81758);m.i(self.REL+8,0x165);m.q(self.REL+0x10,o.FRA);m.q(self.REL+0x18,o.NAV);m.i(self.REL+0x20,56456976);m.b(self.REL+0x28,0);m.q(self.REL+0x40,self.DEF)
  m.q(self.DEF,b+0x1ce7488);m.i(self.DEF+8,0x165);self.name(self.DEF+0x10,'vassal');m.i(self.DEF+0x30,0);m.q(self.DEF+0x38,self.DEF);m.b(self.DEF+0x14f,1);m.b(self.DEF+0x15a,1)
  m.q(b+0x233ffd8,self.REG);m.q(self.REG+8,self.SENTINEL);m.q(self.REG+0x10,1);m.q(self.REG+0x18,self.BUCKETS);m.q(self.REG+0x30,7);m.q(self.REG+0x38,8)
  m.q(self.REG+0x40,self.VECTOR);m.q(self.REG+0x48,self.VECTOR+8);m.q(self.REG+0x50,self.VECTOR+8);m.q(self.VECTOR,self.DEF);m.q(self.REG+0x58,self.DEF)
  bucket=self.BUCKETS+(o.fnv1('vassal')&7)*16;m.q(bucket,self.NODE);m.q(bucket+8,self.NODE)
  m.q(self.NODE,self.SENTINEL);m.q(self.NODE+8,self.SENTINEL);self.name(self.NODE+0x10,'vassal');m.q(self.NODE+0x30,self.DEF)
  m.i(self.NAV+0x2864,0);m.i(self.NAV+0x1344,1)
 def name(self,address,text,heap=0x75000000):
  raw=bytearray(32);b=text.encode()
  if len(b)<16:raw[:len(b)+1]=b+b'\0';struct.pack_into('<QQ',raw,16,len(b),15)
  else:struct.pack_into('<QQQQ',raw,0,heap,0,len(b),max(31,len(b)));self.m.put(heap,b+b'\0')
  self.m.put(address,raw)
 def capture(self):return o.capture(self.m,self.BASE)
 def snap(self):return self.capture()['snapshot']
 def independent(self):
  self.m.q(self.NAV+0x18f0,0);self.m.q(self.FRA+0x1a20,self.SUBJECTS)
  self.m.i(self.LROOT+0x134,0);self.m.i(self.RROOT+0x134,0)

class Tests(unittest.TestCase):
 def test_valid_raw_chain_not_authority(self):
  f=Fixture();r=f.capture();s=r['snapshot'];self.assertEqual(s['scope_status'],'direct_subject_graph_observed');self.assertEqual(s['definition']['name']['text'],'vassal');self.assertEqual(s['registry']['lookup']['nodes'][0]['value'],f.DEF)
  self.assertEqual(r['entitlement'],'unsupported_tls_and_lazy_query');self.assertTrue(all(r[k] is False for k in o.FALSE_CLAIMS));self.assertLess(r['read_budget']['bytes'],20000)
 def test_aslr_vtables_relocated(self):
  f=Fixture(True);self.assertEqual(f.snap()['relation']['vtable'],f.BASE+0x1c81758)
 def test_six_focus_values_and_separate_flags(self):
  for focus in range(6):
   f=Fixture();f.m.i(f.NAV+0x2864,focus);f.m.b(f.DEF+0x14f,focus%2);f.m.b(f.DEF+0x15a,(focus+1)%2);s=f.snap();self.assertEqual(s['focus'],focus);self.assertNotEqual(s['definition']['uses_military_focus'],s['definition']['can_set_mil_focus'])
 def test_independent_target_explicit_outside_scope_no_registry_read(self):
  f=Fixture();f.independent();s=f.snap();self.assertEqual(s['scope_status'],'outside_fixed_direct_subject_scope');self.assertIsNone(s['definition']);self.assertFalse(any(p==f.BASE+0x233ffd8 for p,n in f.m.reads))
  with self.assertRaises(o.ReadError):o.compare_snapshots(s,s)
 def test_partial_graph_fail_closed(self):
  for field,value,width in [(Fixture.NAV+0x18f0,0,8),(Fixture.FRA+0x1a20,Fixture.SUBJECTS,8),(Fixture.LROOT+0x134,0,4),(Fixture.RINDEX+8,Fixture.REL+8,8)]:
   f=Fixture();getattr(f.m,{8:'q',4:'i'}[width])(field,value)
   with self.subTest(field=field),self.assertRaises(o.ReadError):f.capture()
 def test_relation_role_generation_removed_type(self):
  for field,value,width in [(Fixture.REL+0x10,o.NAV,8),(Fixture.REL+0x18,o.NAV^(3<<56),8),(Fixture.REL+0x28,1,1),(Fixture.REL+8,0,4),(Fixture.REL,Fixture.BASE+0x1c817d8,8)]:
   f=Fixture();getattr(f.m,{8:'q',4:'i',1:'b'}[width])(field,value)
   with self.subTest(field=field),self.assertRaises(o.ReadError):f.capture()
 def test_relation_record_owner_and_counterpart(self):
  for delta,value in [(8,o.NAV),(16,o.NAV^(2<<56))]:
   f=Fixture();f.m.q(f.LEFT+((o.NAV>>32)&65535)*0x48+delta,value)
   with self.assertRaises(o.ReadError):f.capture()
 def test_unknown_definition_never_dereferenced_further(self):
  f=Fixture();f.m.q(f.DEF,f.BASE+0x1ce7490)
  with self.assertRaisesRegex(o.ReadError,'unsupported definition'):f.capture()
  self.assertEqual([(p,n) for p,n in f.m.reads if f.DEF<=p<f.DEF+0x160],[(f.DEF,8)])
 def test_definition_index_self_cache_identity(self):
  for p,v,width in [(Fixture.DEF+0x30,1,4),(Fixture.DEF+0x38,Fixture.DEF+8,8),(Fixture.REG+0x58,Fixture.DEF+8,8),(Fixture.VECTOR,Fixture.DEF+8,8)]:
   f=Fixture();getattr(f.m,{8:'q',4:'i'}[width])(p,v)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_missing_name_map_sentinel_or_wrong_key(self):
  for case in ('first','last','value','name'):
   f=Fixture();bucket=f.BUCKETS+(o.fnv1('vassal')&7)*16
   if case=='first':f.m.q(bucket,f.SENTINEL)
   elif case=='last':f.m.q(bucket+8,f.SENTINEL)
   elif case=='value':f.m.q(f.NODE+0x30,f.DEF+8)
   else:f.name(f.NODE+0x10,'march')
   with self.subTest(case=case),self.assertRaises(o.ReadError):f.capture()
 def test_collision_chain_complete_lookup(self):
  f=Fixture();other=next('x'+str(i) for i in range(100) if o.fnv1('x'+str(i))&7==o.fnv1('vassal')&7)
  # Two registered definitions; only selected definition is dereferenced.
  otherdef=f.DEF+0x1000;node=f.NODE+0x100;bucket=f.BUCKETS+(o.fnv1('vassal')&7)*16
  f.m.q(f.REG+0x10,2);f.m.q(f.REG+0x48,f.VECTOR+16);f.m.q(f.REG+0x50,f.VECTOR+16);f.m.q(f.VECTOR+8,otherdef)
  f.m.q(bucket+8,node);f.m.q(node,f.SENTINEL);f.m.q(node+8,f.NODE);f.name(node+0x10,other);f.m.q(node+0x30,otherdef);f.m.q(f.NODE,node)
  self.assertEqual(len(f.snap()['registry']['lookup']['nodes']),2);self.assertFalse(any(p==otherdef for p,n in f.m.reads))
  f.m.q(f.NODE,f.SENTINEL)
  with self.assertRaisesRegex(o.ReadError,'reciprocal'):f.capture()
 def test_registry_and_vector_limits_before_payload(self):
  for p,v in [(Fixture.REG+0x10,4097),(Fixture.REG+0x38,4097),(Fixture.REG+0x30,6),(Fixture.REG+0x48,Fixture.VECTOR+4097*8),(Fixture.REG+0x50,Fixture.VECTOR+4097*8)]:
   f=Fixture();f.m.q(p,v)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_hash_cycle_and_duplicate_key(self):
  for case in ('cycle','duplicate'):
   f=Fixture();f.m.q(f.REG+0x10,2);f.m.q(f.REG+0x48,f.VECTOR+16);f.m.q(f.REG+0x50,f.VECTOR+16);f.m.q(f.VECTOR+8,f.DEF+0x1000)
   bucket=f.BUCKETS+(o.fnv1('vassal')&7)*16;f.m.q(bucket,f.NODE+0x100)
   if case=='cycle':f.m.q(f.NODE+8,f.NODE)
   else:
    f.m.q(f.NODE+8,f.NODE+0x100);f.m.q(f.NODE+0x100,f.NODE);f.m.q(f.NODE+0x108,f.SENTINEL);f.name(f.NODE+0x110,'vassal');f.m.q(f.NODE+0x130,f.DEF+0x1000)
   with self.subTest(case=case),self.assertRaises(o.ReadError):f.capture()
 def test_subject_vector_duplicates_and_bound(self):
  for case in ('duplicate','limit','misalign','slot','generation'):
   f=Fixture()
   if case=='duplicate':f.m.q(f.FRA+0x1a20,f.SUBJECTS+16);f.m.q(f.SUBJECTS+8,o.NAV)
   elif case=='limit':f.m.q(f.FRA+0x1a20,f.SUBJECTS+257*8)
   elif case=='misalign':f.m.q(f.FRA+0x1a20,f.SUBJECTS+9)
   elif case=='slot':f.m.q(f.SUBJECTS,(o.NAV&~(65535<<32))|(301<<32))
   else:f.m.q(f.SUBJECTS,o.NAV^(3<<56))
   with self.subTest(case=case),self.assertRaises(o.ReadError):f.capture()
 def test_db_country_bounds_and_player(self):
  for p,v,width in [(Fixture.DB+0x124,100,4),(Fixture.DB+0x124,4097,4),(Fixture.NAV+0x20,o.NAV^(3<<56),8),(Fixture.GAME+0x1e60,o.NAV,8),(Fixture.GAME+0x7485,1,1),(Fixture.GAME+0x74c8,0x123000,8)]:
   f=Fixture();getattr(f.m,{8:'q',4:'i',1:'b'}[width])(p,v)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_index_limits_duplicates_and_real_db_slot(self):
  for case in ('limit','duplicate','badslot'):
   f=Fixture()
   if case=='limit':f.m.i(f.LROOT+0x134,4097)
   elif case=='duplicate':f.m.i(f.LROOT+0x134,2);f.m.put(f.LINDEX+16,struct.pack('<I4xQ',(o.NAV>>32)&65535,f.REL))
   else:f.m.put(f.LINDEX,struct.pack('<I4xQ',300,f.REL))
   with self.subTest(case=case),self.assertRaises(o.ReadError):f.capture()
 def test_names_strict_sso_and_heap(self):
  f=Fixture();r=o.Budget(f.m);f.name(0x76000000,'long_subject_identifier',0x76100000);self.assertEqual(o.support.read_name(r,0x76000000)['text'],'long_subject_identifier')
  for case in ('length','capacity','nul','nonascii'):
   f=Fixture()
   if case=='length':f.m.q(f.DEF+0x20,129)
   elif case=='capacity':f.m.q(f.DEF+0x28,3)
   elif case=='nul':f.m.b(f.DEF+0x16,65)
   else:f.m.b(f.DEF+0x10,255)
   with self.subTest(case=case),self.assertRaises(o.ReadError):f.capture()
 def test_all_imported_int_fields_reject_bool_float(self):
  original=Fixture().snap();paths=[]
  def walk(x,path):
   if type(x) is int:paths.append(path)
   elif type(x) is dict:
    for k,v in x.items():walk(v,path+[k])
   elif type(x) is list:
    for k,v in enumerate(x):walk(v,path+[k])
  walk(original,[]);self.assertEqual(len(paths),86)
  for path in paths:
   for convert in (bool,float):
    bad=copy.deepcopy(original);x=bad
    for k in path[:-1]:x=x[k]
    x[path[-1]]=convert(x[path[-1]])
    with self.subTest(path=path,type=convert),self.assertRaises(o.ReadError):o.inspect(bad)
 def test_all_nested_missing_extra_keys(self):
  original=Fixture().snap();paths=[]
  def walk(x,path):
   if type(x) is dict:
    paths.append(path)
    for k,v in x.items():walk(v,path+[k])
   elif type(x) is list:
    for k,v in enumerate(x):walk(v,path+[k])
  walk(original,[])
  for path in paths:
   bad=copy.deepcopy(original);x=bad
   for k in path:x=x[k]
   x['extra']=True
   with self.subTest(path=path),self.assertRaises(o.ReadError):o.inspect(bad)
   bad=copy.deepcopy(original);x=bad
   for k in path:x=x[k]
   del x[next(iter(x))]
   with self.subTest(path=path),self.assertRaises(o.ReadError):o.inspect(bad)
 def test_focus_outside_enum_and_nonboolean_flags(self):
  for p,v,width in [(Fixture.NAV+0x2864,-1,4),(Fixture.NAV+0x2864,6,4),(Fixture.DEF+0x14f,2,1),(Fixture.DEF+0x15a,255,1)]:
   f=Fixture();getattr(f.m,{4:'i',1:'b'}[width])(p,v)
   with self.subTest(p=p,v=v),self.assertRaises(o.ReadError):f.capture()
 def test_two_pass_date_focus_definition_change(self):
  for case in ('date','focus','definition'):
   f=Fixture();hits=0
   def hook(p,n):
    nonlocal hits
    if p==f.BASE+0x233d8d0:
     hits+=1
     if hits==3:
      if case=='date':f.m.i(f.GAME+0x1dd0,56457000)
      elif case=='focus':f.m.i(f.NAV+0x2864,1)
      else:f.m.b(f.DEF+0x15a,0)
   f.m.hook=hook
   with self.subTest(case=case),self.assertRaises(o.ReadError):f.capture()
 def test_final_code_pin_rechecked(self):
  f=Fixture();p=f.BASE+int(f.c['instruction_pins'][0]['rva'],16);hits=0
  def hook(a,n):
   nonlocal hits
   if a==p:
    hits+=1
    if hits==2:f.m.b(p,f.m.data[p]^1)
  f.m.hook=hook
  with self.assertRaisesRegex(o.ReadError,'loaded code pin'):f.capture()
 def test_budget_and_shortread(self):
  f=Fixture();r=o.Budget(f.m);r.bytes=o.support.MAX_TOTAL
  with self.assertRaises(o.ReadError):r.read(f.GAME,1)
  r=o.Budget(f.m);r.trace=[None]*o.support.MAX_READS
  with self.assertRaises(o.ReadError):r.read(f.GAME,1)
  class Bad:
   def read(self,p,n):return b''
  with self.assertRaises(o.ReadError):o.Budget(Bad()).read(0x10000,1)
 def test_same_day_compare_focus_only_not_effect(self):
  f=Fixture();before=f.snap();f.m.i(f.NAV+0x2864,5);out=o.compare_snapshots(before,f.snap());self.assertTrue(out['changed']);self.assertTrue(all(out[k] is False for k in o.FALSE_CLAIMS))
  for key in ('date','world'):
   after=copy.deepcopy(before);after['identity']['date' if key=='date' else 'game']+=24 if key=='date' else 8
   with self.assertRaises(o.ReadError):o.compare_snapshots(before,after)
 def test_unknown_raw_functions_not_called_or_read(self):
  f=Fixture();f.capture()
  forbidden=[f.BASE+0x233ff94,f.BASE+0x233ff20,f.BASE+0x233fed6]
  self.assertFalse(any(p in forbidden for p,n in f.m.reads));self.assertFalse(hasattr(f.m,'write'))

class FutureWrapper(unittest.TestCase):
 def setup(self):
  sys.path.insert(0,str(o.ROOT));from work import probe_diplomacy_current as legacy
  f=Fixture();sig={'timestamp':f.c['pe']['timestamp'],'size':f.c['pe']['image_size']};return f,legacy,sig
 def test_success_mocked_no_os(self):
  f,l,sig=self.setup();real=o.sha;identity={'pid':1,'creation_filetime':'0000000000000001','module_base':f.BASE,'exit_filetime':0}
  with patch.object(o,'sha',side_effect=lambda p:o.EXE_SHA if Path(p).name=='eu4.exe' else real(p)),patch.object(l,'verified_executable',return_value=({},sig)),patch.object(l,'ProcessReader',return_value=f.m),patch.object(l,'pe_signature',return_value=sig),patch.object(l,'verify_module_signature'),patch.object(o.support,'held_identity',return_value=identity) as held:
   r=o.sample_process(pid=1,creation='0000000000000001',executable=o.ROOT.parent/'eu4.exe');self.assertEqual(held.call_count,2);self.assertFalse(r['runtime_verified'])
  self.assertTrue(f.m.closed)
 def test_post_failures_close_mocked_handle(self):
  for mode in ('identity','pe','disk','read'):
   f,l,sig=self.setup();real=o.sha;calls=0
   def sha(p):
    nonlocal calls
    if Path(p).name!='eu4.exe':return real(p)
    calls+=1;return '0'*64 if mode=='disk' and calls==2 else o.EXE_SHA
   if mode=='read':f.m.q(f.NAV+0x20,0)
   with patch.object(o,'sha',side_effect=sha),patch.object(l,'verified_executable',return_value=({},sig)),patch.object(l,'ProcessReader',return_value=f.m),patch.object(l,'pe_signature',return_value=sig),patch.object(l,'verify_module_signature',side_effect=o.ReadError('mock PE') if mode=='pe' else None),patch.object(o.support,'held_identity',side_effect=[{'pid':1},{'pid':2}] if mode=='identity' else None,return_value={'pid':1}):
    with self.subTest(mode=mode),self.assertRaises(o.ReadError):o.sample_process(pid=1,creation='0000000000000001',executable=o.ROOT.parent/'eu4.exe')
   self.assertTrue(f.m.closed)
 def test_invalid_identity_never_open(self):
  f,l,sig=self.setup()
  with patch.object(l,'ProcessReader') as opened:
   for pid,creation in [(True,'0000000000000001'),(1,'1'),(1,'0000000000000000'),(1,'000000000000000G')]:
    with self.assertRaises(o.ReadError):o.sample_process(pid=pid,creation=creation,executable=o.ROOT.parent/'eu4.exe')
   opened.assert_not_called()

if __name__=='__main__':unittest.main()
