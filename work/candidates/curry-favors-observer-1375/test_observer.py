import copy,importlib.util,json,struct,sys,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('curry_test_observer',HERE/'observer.py');o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)

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
  except KeyError as e:raise o.ReadError('unmapped mock memory') from e
 def close(self):self.closed=True

class Fixture:
 BASE=0x140000000;GAME=0x70000000;DB=0x70100000;ARRAY=0x70200000;FRA=0x71000000;POR=0x71100000
 RECORDS=0x72000000;ROOT=0x72100000;INDEX=0x72200000;REL=0x72300000
 HOLDER=0x73000000;MANAGER=0x73100000;VECTOR=0x73200000;ENTRY=0x73300000;MISSION=0x73400000
 DATE=56456976
 def __init__(self,active=True,relocated=False):
  self.m=Memory();m=self.m;c=o.contract()
  if relocated:self.BASE=0x145000000
  b=self.BASE;m.base=b
  for x in c['instruction_pins']:m.put(b+int(x['rva'],16),bytes.fromhex(x['bytes']))
  for x in c['vtable_pins']:m.q(b+int(x['rva'],16),struct.unpack('<Q',bytes.fromhex(x['bytes']))[0]-0x140000000+b)
  m.q(b+0x233d8d0,self.DB);m.q(b+0x233fe78,self.GAME);m.q(self.DB+0x118,self.ARRAY);m.i(self.DB+0x124,300)
  m.i(self.GAME+0x1dd0,self.DATE);m.q(self.GAME+0x1e60,o.FRA);m.b(self.GAME+0x7485,0);m.q(self.GAME+0x74c8,0)
  for address,h in [(self.FRA,o.FRA),(self.POR,o.POR)]:
   m.q(self.ARRAY+((h>>32)&65535)*8,address);m.q(address+0x20,h);m.q(address+0x18f0,0)
  m.q(self.FRA+0x1510,self.RECORDS);r=self.RECORDS+((o.POR>>32)&65535)*0x48;m.q(r,self.ROOT);m.q(r+8,o.FRA);m.q(r+16,o.POR)
  m.q(self.ROOT+0x158,self.INDEX);m.i(self.ROOT+0x160,1);m.i(self.ROOT+0x164,int(active));m.put(self.INDEX,struct.pack('<I4xQ',(o.POR>>32)&65535,self.REL))
  m.q(self.REL,b+0x1c7b178);m.i(self.REL+8,0x165);m.q(self.REL+0x10,o.FRA);m.q(self.REL+0x18,o.POR);m.i(self.REL+0x20,self.DATE);m.b(self.REL+0x28,0);m.q(self.REL+0x30,self.MISSION)
  m.q(self.FRA+0x1480,self.HOLDER);m.q(self.FRA+0x1488,self.HOLDER+32);m.q(self.FRA+0x1490,self.HOLDER+32);m.q(self.HOLDER+0x18,self.MANAGER);m.q(self.MANAGER,b+0x1cac380);m.i(self.MANAGER+8,0x165);m.i(self.MANAGER+0x10,0x2746);m.b(self.MANAGER+0x14,3);m.q(self.MANAGER+0x16,o.FRA)
  m.q(self.MANAGER+0x20,self.VECTOR);m.q(self.MANAGER+0x28,self.VECTOR+8);m.q(self.MANAGER+0x30,self.VECTOR+8);m.q(self.VECTOR,self.ENTRY)
  self.entry(self.ENTRY,0,self.MISSION if active else 0,2 if active else 0)
  m.q(self.MISSION,b+0x1c4b2b8);m.i(self.MISSION+8,0x182);m.q(self.MISSION+0x48,self.ENTRY);m.i(self.MISSION+0x50,0);m.q(self.MISSION+0x80,o.FRA);m.q(self.MISSION+0x88,o.POR);m.i(self.MISSION+0xa8,o.TOKEN)
 def entry(self,p,eid,mission,status):
  m=self.m;m.q(p,self.BASE+0x1cac2f0);m.i(p+8,0x165);m.b(p+0x40,3);m.i(p+0x44,eid);m.q(p+0x10,mission);m.b(p+0x18,status)
 def capture(self):return o.capture(self.m,self.BASE)
 def snap(self):return self.capture()['passes'][0]

class Tests(unittest.TestCase):
 def test_active_complete_two_pass_graph(self):
  f=Fixture();r=f.capture();self.assertTrue(o.inspect_capture(r));self.assertEqual(r['state']['status'],'active_relation_mission_graph');self.assertEqual(len(r['passes']),2);self.assertTrue(all(r[k] is False for k in o.FALSE_CLAIMS));self.assertLess(r['read_budget']['bytes'],12000)
 def test_absent_not_rejected_or_cancel_effect(self):
  r=Fixture(False).capture();self.assertTrue(r['state']['complete_selected_absence']);self.assertFalse(r['effect_verified']);self.assertNotIn('rejected',json.dumps(r['state']))
 def test_aslr(self):
  f=Fixture(relocated=True);self.assertEqual(f.snap()['relation']['vtable'],f.BASE+0x1c7b178)
 def test_entry_vtable_unknown_shortcircuits_derived(self):
  f=Fixture(False);f.m.q(f.ENTRY,f.BASE+0x1cac300);r=f.capture();self.assertEqual(r['state']['status'],'unknown_selected_graph')
  self.assertEqual([(p,n) for p,n in f.m.reads if f.ENTRY<=p<f.ENTRY+0x48],[(f.ENTRY,8)]*2)
 def test_entry_kind_unknown_shortcircuits_mission_and_ID(self):
  f=Fixture(False);f.m.b(f.ENTRY+0x40,2);r=f.capture();self.assertFalse(r['state']['complete_selected_absence'])
  self.assertFalse(any(p in (f.ENTRY+0x10,f.ENTRY+0x18,f.ENTRY+0x44) for p,n in f.m.reads))
 def test_manager_unknown_shortcircuits_vector(self):
  f=Fixture(False);f.m.q(f.MANAGER,f.BASE+0x1cac388);r=f.capture();self.assertEqual(r['state']['status'],'unknown_selected_graph');self.assertFalse(any(p==f.MANAGER+0x20 for p,n in f.m.reads))
 def test_mission_unknown_shortcircuits_derived(self):
  f=Fixture();f.m.q(f.MISSION,f.BASE+0x1c4b300);r=f.capture();self.assertFalse(r['state']['active_graph_observed']);self.assertEqual([(p,n) for p,n in f.m.reads if f.MISSION<=p<f.MISSION+0xf8],[(f.MISSION,8)]*2)
 def test_relation_unknown_shortcircuits_derived(self):
  f=Fixture();f.m.q(f.REL,f.BASE+0x1c81658);r=f.capture();self.assertEqual(r['state']['status'],'unknown_selected_graph');self.assertEqual([(p,n) for p,n in f.m.reads if f.REL<=p<f.REL+0x40],[(f.REL,8)]*2)
 def test_removed_relation_no_mission_deref(self):
  f=Fixture();f.m.b(f.REL+0x28,1);r=f.capture();self.assertEqual(r['state']['status'],'unknown_selected_graph');self.assertFalse(any(p==f.REL+0x30 for p,n in f.m.reads))
 def test_marker_types_are_distinct(self):
  for p,value in [(Fixture.MISSION+8,0x165),(Fixture.ENTRY+8,0x182),(Fixture.MANAGER+8,0),(Fixture.REL+8,0x182)]:
   f=Fixture();f.m.i(p,value)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_manager_kind_token_and_fullowner(self):
  for p,value,fn in [(Fixture.MANAGER+0x14,2,'b'),(Fixture.MANAGER+0x10,0x2747,'i'),(Fixture.MANAGER+0x16,o.POR,'q')]:
   f=Fixture();getattr(f.m,fn)(p,value)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_country_manager_holder_bound_before_fourth_pointer(self):
  for end,cap in [(24,32),(32,24),(32,33),(32,17*8)]:
   f=Fixture();f.m.q(f.FRA+0x1488,f.HOLDER+end);f.m.q(f.FRA+0x1490,f.HOLDER+cap)
   with self.subTest(end=end,cap=cap),self.assertRaises(o.ReadError):f.capture()
   self.assertFalse(any(p==f.HOLDER+0x18 for p,n in f.m.reads))
 def test_reverse_and_wrong_generation(self):
  for p,v in [(Fixture.REL+0x10,o.POR),(Fixture.REL+0x18,o.POR^(3<<56)),(Fixture.MISSION+0x80,o.POR),(Fixture.MISSION+0x88,o.POR^(2<<56)),(Fixture.POR+0x20,o.POR^(1<<56))]:
   f=Fixture();f.m.q(p,v)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_entry_ID_and_mission_backreference(self):
  for p,v,fn in [(Fixture.ENTRY+0x44,-1,'i'),(Fixture.MISSION+0x50,1,'i'),(Fixture.MISSION+0x48,Fixture.ENTRY+8,'q')]:
   f=Fixture();getattr(f.m,fn)(p,v)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_unknown_status_and_null_mission_never_active(self):
  for mode in ('status','mission','relation'):
   f=Fixture()
   if mode=='status':f.m.b(f.ENTRY+0x18,255)
   elif mode=='mission':f.m.q(f.ENTRY+0x10,0)
   else:f.m.q(f.REL+0x30,0)
   self.assertEqual(f.capture()['state']['status'],'unknown_selected_graph')
 def test_absent_index_but_returning_mission_separate(self):
  f=Fixture();f.m.i(f.ROOT+0x164,0);f.m.b(f.ENTRY+0x18,1);r=f.capture();self.assertEqual(r['state']['status'],'index_absent_mission_present');self.assertFalse(r['state']['complete_selected_absence'])
 def test_wrong_task_token_not_curry_graph(self):
  f=Fixture();f.m.i(f.MISSION+0xa8,0x2ddb);self.assertEqual(f.capture()['state']['status'],'unknown_selected_graph')
 def test_future_start_and_nonpositive_start_rejected(self):
  for date in (0,-1,Fixture.DATE+1):
   f=Fixture();f.m.i(f.REL+0x20,date)
   with self.subTest(date=date),self.assertRaises(o.ReadError):f.capture()
 def test_index_limits_before_payload(self):
  for off,value in [(0x160,4097),(0x164,2),(0x164,-1)]:
   f=Fixture();f.m.i(f.ROOT+off,value)
   with self.subTest(off=off),self.assertRaises(o.ReadError):f.capture()
   self.assertFalse(any(p==f.INDEX for p,n in f.m.reads))
 def test_duplicate_or_outside_index_slot(self):
  for mode in ('duplicate','outside','object'):
   f=Fixture();f.m.i(f.ROOT+0x160,2);f.m.i(f.ROOT+0x164,2)
   slot=(o.POR>>32)&65535 if mode=='duplicate' else 300 if mode=='outside' else 46
   f.m.put(f.INDEX+16,struct.pack('<I4xQ',slot,f.REL if mode=='object' else f.REL+0x100))
   with self.subTest(mode=mode),self.assertRaises(o.ReadError):f.capture()
 def test_null_empty_index_and_envoy_vector(self):
  f=Fixture(False);f.m.q(f.ROOT+0x158,0);f.m.i(f.ROOT+0x160,0)
  for off in (0x20,0x28,0x30):f.m.q(f.MANAGER+off,0)
  self.assertTrue(f.capture()['state']['complete_selected_absence'])
 def test_envoy_vector_limits_alignment(self):
  for end in (Fixture.VECTOR-8,Fixture.VECTOR+1,Fixture.VECTOR+4097*8):
   f=Fixture();f.m.q(f.MANAGER+0x28,end)
   with self.subTest(end=end),self.assertRaises(o.ReadError):f.capture()
 def test_duplicate_entry_or_ID(self):
  for mode in ('entry','id'):
   f=Fixture();f.m.q(f.MANAGER+0x28,f.VECTOR+16);f.m.q(f.MANAGER+0x30,f.VECTOR+16);p=f.ENTRY if mode=='entry' else f.ENTRY+0x100
   f.m.q(f.VECTOR+8,p)
   if mode=='id':f.entry(p,0,0,0)
   with self.subTest(mode=mode),self.assertRaises(o.ReadError):f.capture()
 def test_103_entries_bounded(self):
  f=Fixture(False)
  for i in range(103):p=f.ENTRY+i*0x100;f.entry(p,i,0,0);f.m.q(f.VECTOR+i*8,p)
  f.m.q(f.MANAGER+0x28,f.VECTOR+103*8);f.m.q(f.MANAGER+0x30,f.VECTOR+103*8);r=f.capture();self.assertTrue(r['state']['complete_selected_absence']);self.assertLess(r['read_budget']['calls'],8192)
 def test_unselected_index_object_not_dereferenced(self):
  f=Fixture(False);f.m.i(f.ROOT+0x164,1);f.m.put(f.INDEX,struct.pack('<I4xQ',46,0x7fff0000));r=f.capture();self.assertTrue(r['state']['complete_selected_absence']);self.assertFalse(any(p==0x7fff0000 for p,n in f.m.reads))
 def test_two_pass_world_change(self):
  f=Fixture();seen=[0]
  def hook(p,n):
   if p==f.GAME+0x1dd0:
    seen[0]+=1
    if seen[0]==3:f.m.i(p,f.DATE+24)
  f.m.hook=hook
  with self.assertRaises(o.ReadError):f.capture()
 def test_each_loaded_code_or_vtable_pin(self):
  for row in o.contract()['instruction_pins']+o.contract()['vtable_pins']:
   f=Fixture();p=f.BASE+int(row['rva'],16);f.m.data[p]^=1
   with self.subTest(rva=row['rva']),self.assertRaises(o.ReadError):f.capture()
 def test_bad_reset_player_load_countrycount(self):
  for p,v,fn in [(Fixture.GAME+0x7485,1,'b'),(Fixture.GAME+0x74c8,0x77770000,'q'),(Fixture.GAME+0x1e60,o.POR,'q'),(Fixture.DB+0x124,189,'i')]:
   f=Fixture();getattr(f.m,fn)(p,v)
   with self.subTest(p=p),self.assertRaises(o.ReadError):f.capture()
 def test_typed_integer_aliases_in_each_complete_pass(self):
  r=Fixture().capture();paths=[]
  def walk(x,p=()):
   if type(x) is dict:
    for k,v in x.items():walk(v,p+(k,))
   elif type(x) is list:
    for k,v in enumerate(x):walk(v,p+(k,))
   elif type(x) is int:paths.append((p,x))
  walk(r['passes'][0])
  for p,v in paths:
   for which in (0,1,'both'):
    m=copy.deepcopy(r)
    for i in ((0,1) if which=='both' else (which,)):
     obj=m['passes'][i]
     for k in p[:-1]:obj=obj[k]
     obj[p[-1]]=float(v)
    with self.subTest(path=p,which=which),self.assertRaises(o.ReadError):o.inspect_capture(m)
   if v in (0,1):
    m=copy.deepcopy(r)
    for s in m['passes']:
     obj=s
     for k in p[:-1]:obj=obj[k]
     obj[p[-1]]=bool(v)
    with self.subTest(path=p,alias='bool'),self.assertRaises(o.ReadError):o.inspect_capture(m)
 def test_summary_or_flags_cannot_forge_active(self):
  r=Fixture(False).capture()
  for k in o.FALSE_CLAIMS:
   x=copy.deepcopy(r);x[k]=0
   with self.subTest(k=k),self.assertRaises(o.ReadError):o.inspect_capture(x)
  for field in ('atomic','two_pass_equal'):
   x=copy.deepcopy(r);x[field]=int(x[field])
   with self.assertRaises(o.ReadError):o.inspect_capture(x)
  r['state']['active_graph_observed']=True
  with self.assertRaises(o.ReadError):o.inspect_capture(r)
 def test_missing_unknown_keys_or_derived_fields(self):
  f=Fixture(False);f.m.q(f.ENTRY,f.BASE+0x1cac300);r=f.capture()
  for i in (0,1):
   x=copy.deepcopy(r);x['passes'][i]['envoys']['fields']['entries'][0]['fields']={}
   with self.assertRaises(o.ReadError):o.inspect_capture(x)
  x=copy.deepcopy(r);del x['passes'][0]['index']['count']
  with self.assertRaises(o.ReadError):o.inspect_capture(x)
 def test_selected_census_compare_no_causality(self):
  a=Fixture(False).snap();b=Fixture().snap();x=o.compare_snapshots(a,b);self.assertTrue(x['selected_active_graph_appeared']);self.assertFalse(x['effect_verified']);self.assertFalse(x['request_causality_verified'])
  self.assertTrue(o.compare_snapshots(b,a)['selected_index_disappeared'])
 def test_cross_date_census_not_old_effect_matcher(self):
  a=Fixture(False).snap();f=Fixture();f.m.i(f.GAME+0x1dd0,f.DATE+48);b=f.snap();self.assertFalse(o.compare_snapshots(a,b)['effect_verified'])
  with self.assertRaises(o.ReadError):o.compare_snapshots(b,a)
 def test_cross_world_or_country_compare_rejected(self):
  a=Fixture().snap();b=copy.deepcopy(a);b['identity']['game']+=8
  with self.assertRaises(o.ReadError):o.compare_snapshots(a,b)
 def test_capture_comparison_requires_full_held_creation(self):
  a=Fixture(False).capture();b=Fixture().capture()
  with self.assertRaises(o.ReadError):o.compare_captures(a,b)
  for r in (a,b):
   r['source_kind']='held_process_readonly';r['process']=dict(identity=dict(pid=1234,creation_filetime='0102030405060708',exit_filetime=0,module_base=Fixture.BASE),path=str(o.ROOT.parent/'eu4.exe'),disk_exe_sha256=o.EXE_SHA,loaded_full_image_hash_verified=False,rights=['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'])
  self.assertTrue(o.compare_captures(a,b)['selected_active_graph_appeared'])
  for key,v in [('pid',1234.0),('pid',1235),('creation_filetime','0102030405060709'),('creation_filetime',True),('exit_filetime',0.0)]:
   x=copy.deepcopy(b);x['process']['identity'][key]=v
   with self.subTest(key=key,v=v),self.assertRaises(o.ReadError):o.compare_captures(a,x)
 def test_budget_short_read(self):
  f=Fixture();del f.m.data[f.ENTRY+0x10]
  with self.assertRaises(o.ReadError):f.capture()
  b=o.Budget(f.m)
  with self.assertRaises(o.ReadError):b.read(f.ENTRY,65537)
  b.bytes=o.support.MAX_TOTAL
  with self.assertRaises(o.ReadError):b.read(f.ENTRY,1)
 def test_future_wrapper_mock_only_held_identity_and_close(self):
  sys.path.insert(0,str(o.ROOT));from work import probe_diplomacy_current as legacy
  f=Fixture();sig={'timestamp':0x66fe6ab9,'size':0x25e0000};ident=dict(pid=1234,creation_filetime='0102030405060708',exit_filetime=0,module_base=f.BASE)
  with patch.object(o,'dependencies'),patch.object(o.support,'sha',return_value=o.EXE_SHA),patch.object(legacy,'verified_executable',return_value=(None,sig)),patch.object(legacy,'ProcessReader',return_value=f.m) as opened,patch.object(o.support,'held_identity',return_value=ident) as held,patch.object(legacy,'pe_signature',return_value=sig),patch.object(legacy,'verify_module_signature'):
   r=o.sample_process(pid=1234,creation=ident['creation_filetime'],executable=o.ROOT.parent/'eu4.exe');self.assertTrue(f.m.closed);self.assertEqual(r['source_kind'],'held_process_readonly');self.assertEqual(held.call_count,2);opened.assert_called_once()
 def test_wrapper_failure_closes_and_creation_alias_never_opens(self):
  sys.path.insert(0,str(o.ROOT));from work import probe_diplomacy_current as legacy
  with patch.object(legacy,'ProcessReader') as opened:
   for value in (True,1,1.0,'1','0'*16):
    with self.subTest(value=value),self.assertRaises(o.ReadError):o.sample_process(pid=1234,creation=value,executable=o.ROOT.parent/'eu4.exe')
   opened.assert_not_called()
  f=Fixture();sig={'timestamp':0x66fe6ab9,'size':0x25e0000}
  with patch.object(o,'dependencies'),patch.object(o.support,'sha',return_value=o.EXE_SHA),patch.object(legacy,'verified_executable',return_value=(None,sig)),patch.object(legacy,'ProcessReader',return_value=f.m),patch.object(o.support,'held_identity',side_effect=o.ReadError('creation mismatch')):
   with self.assertRaises(o.ReadError):o.sample_process(pid=1234,creation='0102030405060708',executable=o.ROOT.parent/'eu4.exe')
  self.assertTrue(f.m.closed)
if __name__=='__main__':unittest.main()
