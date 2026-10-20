"""Sparse memory only; every possible OS reader entry in wrapper tests is mocked."""
import copy,importlib.util,json,struct,sys,unittest
from pathlib import Path
from unittest.mock import patch
import observer as o

spec=importlib.util.spec_from_file_location('_toggle_parent_fixture',o.ROOT/'work/candidates/subject-military-focus-observer-1375/test_observer.py')
parent=importlib.util.module_from_spec(spec)
saved=sys.modules['observer'];sys.modules['observer']=o.mil
try:spec.loader.exec_module(parent)
finally:sys.modules['observer']=saved

class Fixture(parent.Fixture):
 RB=0x76000000;RV=0x76010000;RN=0x76020000;MS=0x77000000;MV=0x77100000;MN=0x77200000
 def __init__(self,relocated=False):
  super().__init__(relocated);self.config=o.contract();m=self.m;b=self.BASE
  for x in self.config['instruction_pins']:m.put(b+int(x['rva'],16),bytes.fromhex(x['bytes']))
  for x in self.config['vtable_pins']:
   raw=bytes.fromhex(x['bytes'])
   for i in range(0,len(raw),8):m.q(b+int(x['rva'],16)+i,struct.unpack_from('<Q',raw,i)[0]-0x140000000+b)
  fs=self.config['families'];m.i(b+0x1fd5228,3);m.i(b+0x1fd522c,4);m.q(b+0x1fd5230,self.RB)
  m.q(b+0x23581c8,self.RV);m.q(b+0x23581d0,self.RV+24);m.q(b+0x23581d8,self.RV+24)
  for k in range(4):m.q(self.RB+k*8,0)
  self.addresses={};self.regnodes={}
  for i,(name,f) in enumerate(fs.items()):
   p=b+int(f['singleton_rva'],16);node=self.RN+i*32;self.addresses[name]=p;self.regnodes[name]=node
   m.q(self.RV+i*8,p);m.q(p,b+int(f['vtable_rva'],16));m.i(p+8,f['token']);m.b(p+12,1);m.b(p+13,0)
   bucket=self.RB+f['token']%4*8;old=struct.unpack('<Q',m.read(bucket,8))[0];m.q(bucket,node);m.q(node,p);m.q(node+8,old)
  m.i(self.NAV+0x78,0);m.i(self.FRA+0x1344,1);m.i(self.FRA+0x2258,2);m.b(self.NAV+0x289b,0)
  self.map_entries([(f['token'],1) for f in fs.values()]);m.reads=[];m.bytes_read=0
 def map_entries(self,entries):
  m=self.m;m.q(self.DEF+0x470,self.MS);m.q(self.DEF+0x478,len(entries));m.q(self.DEF+0x480,self.MV);m.q(self.DEF+0x488,self.MV+128);m.q(self.DEF+0x490,self.MV+128);m.q(self.DEF+0x498,7);m.q(self.DEF+0x4a0,8)
  for k in range(16):m.q(self.MV+k*8,self.MS)
  groups={};self.mapnodes=[]
  for i,(token,allowed) in enumerate(entries):
   p=self.MN+i*32;self.mapnodes.append(p);groups.setdefault(o.token_hash(token)&7,[]).append((p,token,allowed))
  for bucket,rows in groups.items():
   m.q(self.MV+bucket*16,rows[0][0]);m.q(self.MV+bucket*16+8,rows[-1][0])
   for i,(p,t,v) in enumerate(rows):
    m.q(p,rows[i+1][0] if i+1<len(rows) else self.MS);m.q(p+8,rows[i-1][0] if i else self.MS);m.i(p+16,t);m.b(p+20,v)
 def capture(self):return o.capture(self.m,self.BASE)
 def snap(self):return self.capture()['snapshot']

class Tests(unittest.TestCase):
 def test_valid_three_raw_states_not_authorization(self):
  r=Fixture().capture();self.assertTrue(o.validated_report(r));self.assertEqual(len(r['passes']),2)
  self.assertTrue(all(r[k] is False for k in o.FALSE_CLAIMS));self.assertTrue(all(v['definition_allows'] and not v['current'] for v in r['snapshot']['states'].values()))
 def test_aslr_all_known_vtables_relocated(self):
  f=Fixture(True);self.assertTrue(o.validated_report(f.capture()))
 def test_unknown_registered_vtable_short_circuits_before_token(self):
  f=Fixture();p=f.addresses['divert_trade'];f.m.q(p,f.BASE+0x123450)
  with self.assertRaisesRegex(o.ReadError,'singleton vtable'):f.capture()
  self.assertNotIn((p+8,4),f.m.reads)
 def test_unregistered_pointer_not_dereferenced(self):
  f=Fixture();f.m.q(f.RV,0x79900000)
  with self.assertRaisesRegex(o.ReadError,'enumeration'):f.capture()
  self.assertFalse(any(p==0x79900000 for p,n in f.m.reads))
 def test_registered_token_mismatch_rejects(self):
  f=Fixture();f.m.i(f.addresses['scutage']+8,1)
  with self.assertRaisesRegex(o.ReadError,'token differs'):f.capture()
 def test_direct_or_unqueued_modes_rejected(self):
  for off,val in ((12,0),(13,1),(12,2),(13,2)):
   f=Fixture();f.m.b(f.addresses['scutage']+off,val)
   with self.subTest(off=off,val=val),self.assertRaises(o.ReadError):f.capture()
 def test_singleton_bucket_absent_even_vector_present_rejected(self):
  f=Fixture();token=f.config['families']['scutage']['token'];f.m.q(f.RB+(token%4)*8,0)
  with self.assertRaisesRegex(o.ReadError,'missing/duplicate'):f.capture()
 def test_registration_cycle_rejected(self):
  f=Fixture();p=f.regnodes['scutage'];f.m.q(p+8,p)
  with self.assertRaisesRegex(o.ReadError,'limit/cycle'):f.capture()
 def test_registration_vector_limits_precede_payload(self):
  for off,val in ((0x1fd5228,42),(0x1fd522c,0),(0x1fd522c,4097)):
   f=Fixture();f.m.i(f.BASE+off,val)
   with self.subTest(off=off,val=val),self.assertRaises(o.ReadError):f.capture()
 def test_permission_empty_map_is_raw_false_not_unsupported_success(self):
  f=Fixture();f.map_entries([]);r=f.capture();self.assertTrue(o.validated_report(r))
  self.assertTrue(all(not x['found'] and not x['allowed'] for x in r['snapshot']['permission_map']['lookups'].values()));self.assertFalse(r['native_call_authorized'])
 def test_permission_missing_and_false_entry_distinguished(self):
  f=Fixture();t=f.config['families']['scutage']['token'];f.map_entries([(t,0)]);s=f.snap()
  self.assertTrue(s['permission_map']['lookups']['scutage']['found']);self.assertFalse(s['states']['scutage']['definition_allows']);self.assertFalse(s['permission_map']['lookups']['divert_trade']['found'])
 def test_permission_collision_chain_complete(self):
  f=Fixture();tokens=[x['token'] for x in f.config['known_singletons']];target=f.config['families']['scutage']['token'];group=[x for x in tokens if o.token_hash(x)&7==o.token_hash(target)&7]
  self.assertGreater(len(group),1);f.map_entries([(x,1) for x in group]);s=f.snap();self.assertEqual(len(s['permission_map']['lookups']['scutage']['nodes']),len(group))
 def test_permission_mask_capacity_size_and_halfempty_reject(self):
  for off,val in ((0x498,6),(0x4a0,7),(0x478,0),(0x478,4097),(0x490,0x77100000+65544)):
   f=Fixture();f.m.q(f.DEF+off,val)
   with self.subTest(off=off,val=val),self.assertRaises(o.ReadError):f.capture()
  f=Fixture();t=f.config['families']['scutage']['token'];f.m.q(f.MV+(o.token_hash(t)&7)*16,f.MS)
  with self.assertRaisesRegex(o.ReadError,'half-empty'):f.capture()
 def test_permission_unknown_wrongbucket_duplicate_badbool(self):
  for kind in ('unknown','wrongbucket','duplicate','badbool'):
   f=Fixture();t=f.config['families']['scutage']['token'];node=next(p for p in f.mapnodes if struct.unpack('<i',f.m.read(p+16,4))[0]==t)
   if kind=='duplicate':f.map_entries([(t,1),(t,0)])
   elif kind=='badbool':f.m.b(node+20,2)
   else:f.m.i(node+16,0x7fffffff if kind=='unknown' else next(x['token'] for x in f.config['known_singletons'] if o.token_hash(x['token'])&7!=o.token_hash(t)&7))
   with self.subTest(kind=kind),self.assertRaises(o.ReadError):f.capture()
 def test_permission_broken_backlink_and_cycle_rejected(self):
  f=Fixture();t=f.config['families']['scutage']['token'];ts=[x['token'] for x in f.config['known_singletons'] if o.token_hash(x['token'])&7==o.token_hash(t)&7];f.map_entries([(x,1) for x in ts]);f.m.q(f.mapnodes[-1]+8,f.mapnodes[-1])
  with self.assertRaises(o.ReadError):f.capture()
 def test_current_masks_and_local_gates_are_only_raw_conditions(self):
  f=Fixture();f.m.i(f.NAV+0x78,0x52);f.m.i(f.FRA+0x2258,0);f.m.b(f.NAV+0x289b,1);r=f.capture();states=r['snapshot']['states']
  self.assertTrue(all(x['current'] for x in states.values()));self.assertFalse(states['scutage']['family_local_condition']);self.assertTrue(states['embargo_rivals']['family_local_condition']);self.assertFalse(r['permission_map_authorizes_native'])
 def test_changed_raw_state_on_second_pass_rejected(self):
  f=Fixture();reads=[0]
  def hook(p,n):
   if p==f.NAV+0x78:
    reads[0]+=1
    if reads[0]==2:f.m.i(p,16)
  f.m.hook=hook
  with self.assertRaisesRegex(o.ReadError,'two-pass'):f.capture()
 def test_outside_graph_does_not_dereference_toggle_registry(self):
  f=Fixture();f.independent();r=f.capture();self.assertTrue(o.validated_report(r));self.assertIsNone(r['snapshot']['states']);self.assertNotIn((f.BASE+0x1fd5228,4),f.m.reads)
 def test_all_new_integer_fields_reject_bool_and_float(self):
  s=Fixture().snap();paths=[]
  def walk(v,p=()):
   if type(v) is dict:
    for k,x in v.items():walk(x,p+(k,))
   elif type(v) is list:
    for i,x in enumerate(v):walk(x,p+(i,))
   elif type(v) is int:paths.append((p,v))
  for k in ('registrations','permission_map','raw_fields'):walk(s[k],(k,))
  self.assertGreater(len(paths),100)
  for path,value in paths:
   for bad in (True,float(value)):
    x=copy.deepcopy(s);parent=x
    for k in path[:-1]:parent=parent[k]
    parent[path[-1]]=bad
    with self.subTest(path=path,bad=bad),self.assertRaises((ValueError,TypeError)):o.inspect(x)
 def test_imported_pass_and_summary_schema_fail_closed(self):
  r=Fixture().capture()
  for mutate in ('pass','summary','extra','flag','derived'):
   x=copy.deepcopy(r)
   if mutate=='pass':x['passes'][1]['raw_fields']['subject_flags']=16
   elif mutate=='summary':x['snapshot']['raw_fields']['subject_flags']=True
   elif mutate=='extra':x['passes'][0]['raw_fields']['unknown']=0
   elif mutate=='flag':x['effect_verified']=0
   else:x['passes'][0]['states']['scutage']['current']=0
   with self.subTest(mutate=mutate),self.assertRaises(o.ReadError):o.validated_report(x)
 def test_permission_truncated_import_cannot_claim_missing(self):
  s=Fixture().snap();q=s['permission_map']['lookups']['scutage'];q['nodes']=[];q['found']=False;q['allowed']=False;s['states']['scutage']['definition_allows']=False
  with self.assertRaisesRegex(o.ReadError,'incomplete'):o.inspect(s)
 def test_budget_shortread_and_pin_failure_rejected(self):
  f=Fixture();original=f.m.read
  with patch.object(f.m,'read',side_effect=lambda p,n:original(p,n)[:-1]):
   with self.assertRaises(o.ReadError):f.capture()
  f=Fixture();pin=f.config['instruction_pins'][0];f.m.b(f.BASE+int(pin['rva'],16),0)
  with self.assertRaises(o.ReadError):f.capture()
 def test_same_day_compare_keeps_side_effects_and_causality_false(self):
  a=Fixture();before=a.snap();a.m.i(a.NAV+0x78,0x52|0x20);after=a.snap();r=o.compare_snapshots(before,after)
  self.assertEqual(r['other_flag_bits_changed'],0x20);self.assertTrue(all(not x['before'] and x['after'] for x in r['states'].values()));self.assertFalse(r['effect_verified']);self.assertFalse(r['side_effects_verified'])
 def test_compare_changed_date_graph_or_permission_is_rejected(self):
  before=Fixture().snap()
  for kind in ('date','permission','gate'):
   f=Fixture()
   if kind=='date':f.m.i(f.GAME+0x1dd0,56457000)
   elif kind=='permission':f.map_entries([])
   else:f.m.i(f.FRA+0x2258,3)
   with self.subTest(kind=kind),self.assertRaisesRegex(o.ReadError,'comparison'):o.compare_snapshots(before,f.snap())

class WrapperTests(unittest.TestCase):
 def setup(self):
  sys.path.insert(0,str(o.ROOT));from work import probe_diplomacy_current as legacy
  f=Fixture();sig=dict(timestamp=f.config['pe']['timestamp'],size=f.config['pe']['image_size']);identity=dict(pid=1,creation_filetime='0000000000000001',exit_filetime=0,module_base=f.BASE)
  return f,legacy,sig,identity
 def test_all_os_entries_mocked_valid_wrapper_closes(self):
  f,l,sig,identity=self.setup()
  with patch.object(l,'verified_executable',return_value=({},sig)),patch.object(l,'ProcessReader',return_value=f.m),patch.object(l,'pe_signature',return_value=sig),patch.object(l,'verify_module_signature'),patch.object(o.mil.support,'held_identity',return_value=identity) as held:
   r=o.sample_process(pid=1,creation='0000000000000001',executable=o.ROOT.parent/'eu4.exe')
  self.assertEqual(held.call_count,2);self.assertTrue(f.m.closed);self.assertTrue(o.validated_report(r));self.assertFalse(r['native_call_authorized'])
 def test_first_or_second_identity_failure_closes(self):
  for first in (True,False):
   f,l,sig,identity=self.setup();calls=[o.ReadError('identity')] if first else [identity,o.ReadError('identity')]
   with patch.object(l,'verified_executable',return_value=({},sig)),patch.object(l,'ProcessReader',return_value=f.m),patch.object(o.mil.support,'held_identity',side_effect=calls):
    with self.assertRaises(o.ReadError):o.sample_process(pid=1,creation='0000000000000001',executable=o.ROOT.parent/'eu4.exe')
   self.assertTrue(f.m.closed)
 def test_bad_pid_creation_rejected_before_open(self):
  f,l,sig,identity=self.setup()
  for pid,creation in [(True,'0000000000000001'),(1.0,'0000000000000001'),(1,1),(1,'0000000000000000'),(1,'000000000000000A')]:
   with patch.object(l,'ProcessReader',side_effect=AssertionError('must not open')) as opened:
    with self.assertRaises(o.ReadError):o.sample_process(pid=pid,creation=creation,executable=o.ROOT.parent/'eu4.exe')
    opened.assert_not_called()
if __name__=='__main__':unittest.main()
