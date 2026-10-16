import copy,json,unittest
from pathlib import Path
import contract_model as m
HERE=Path(__file__).resolve().parent
A=0x0100007a00415246;B=0x010000c000524f50
def graph():
 return dict(actor=A,target=B,entries=[{'slot':192,'pointer':0x10000}],
  relation={'pointer':0x10000,'vtable':m.RELATION_VT,'marker':0x165,'actor':A,'target':B,'start':56456976,'removed':0,'mission':0x20000},
  mission={'pointer':0x20000,'vtable':m.MISSION_VT,'actor':A,'target':B,'token':m.TOKEN,'entry':0x30000,'envoy':99},
  envoys=[{'pointer':0x30000,'id':99,'status':2,'mission':0x20000}])
class ContractTests(unittest.TestCase):
 def test_default_layout(self):
  x=m.model_action();self.assertEqual((x['size'],x['actor'],x['state'],x['envoy'],x['value']),(64,0x2d2d2d,0,-1,True))
 def test_normal_modes(self):
  for value in [True,False]:
   x=m.model_action(A,B,56456976,value);self.assertEqual(x['original'],A);self.assertEqual(x['envoy'],-1);self.assertEqual(x['state'],0)
 def test_clone_date_reset(self):
  x=m.model_action(A,B,56456976);x['last_command_date']=56456999;x['flag39']=True
  y=m.model_clone(x);self.assertEqual(y['last_command_date'],56456976);self.assertIs(y['flag39'],False);self.assertEqual(x['last_command_date'],56456999)
 def test_layout_type_aliases(self):
  for v in [0,1,1.0,'true',None]:
   with self.subTest(v=v),self.assertRaises(ValueError):m.model_action(A,B,56456976,v)
 def test_full_handle_generations(self):
  for bad in [True,float(A),A&0xffffffff,0,0x0100100000415246]:
   with self.subTest(bad=bad),self.assertRaises(ValueError):m.model_action(bad,B)
 def test_coherent_graph(self):
  r=m.select_graph(**graph());self.assertEqual(r['selected_state'],'active_selected_graph');self.assertEqual(r['cancel_action_envoy'],-1);self.assertEqual(r['observed_existing_envoy'],99);self.assertFalse(r['authorization'])
 def test_reverse_relation(self):
  x=graph();x['relation']['actor']=B;x['relation']['target']=A
  with self.assertRaises(ValueError):m.select_graph(**x)
 def test_stale_generation(self):
  x=graph();x['relation']['actor']+=1<<56
  with self.assertRaises(ValueError):m.select_graph(**x)
 def test_wrong_index_slot_and_pointer(self):
  for k,v in [('slot',121),('pointer',0x12300)]:
   x=graph();x['entries'][0][k]=v
   with self.assertRaises(ValueError):m.select_graph(**x)
 def test_unknown_vtable_without_derived(self):
  for field in ['relation','mission']:
   x=graph();x[field]={'vtable':0x1234}
   with self.assertRaisesRegex(ValueError,'unknown'):m.select_graph(**x)
 def test_removed(self):
  x=graph();x['relation']['removed']=1
  with self.assertRaises(ValueError):m.select_graph(**x)
 def test_wrong_token(self):
  for token in [0x2ddb,0x3378,0x3acb]:
   x=graph();x['mission']['token']=token
   with self.assertRaises(ValueError):m.select_graph(**x)
 def test_mission_actor_target(self):
  for field in ['actor','target']:
   x=graph();x['mission'][field]=(B if field=='actor' else A)
   with self.assertRaises(ValueError):m.select_graph(**x)
 def test_crosslinks(self):
  for obj,field in [('relation','mission'),('mission','entry'),('mission','envoy')]:
   x=graph();x[obj][field]+=1
   with self.assertRaises(ValueError):m.select_graph(**x)
 def test_other_status_not_selected_working_graph(self):
  for status in [0,1,3]:
   x=graph();x['envoys'][0]['status']=status
   with self.assertRaises(ValueError):m.select_graph(**x)
 def test_duplicate_envoy(self):
  x=graph();x['envoys'].append(copy.deepcopy(x['envoys'][0]))
  with self.assertRaises(ValueError):m.select_graph(**x)
 def test_duplicate_slot(self):
  x=graph();x['entries'].append(copy.deepcopy(x['entries'][0]))
  with self.assertRaises(ValueError):m.select_graph(**x)
 def test_bounded_vectors(self):
  x=graph();x['entries']=[{'slot':i,'pointer':0x40000+i*16} for i in range(4097)]
  with self.assertRaises(ValueError):m.select_graph(**x)
 def test_absence_not_rejection(self):
  x=graph();x.update(entries=[],relation=None,mission=None);r=m.select_graph(**x);self.assertEqual(r['selected_state'],'absent');self.assertFalse(r['effect_verified']);self.assertNotIn('rejected',r)
 def test_every_selected_numeric_alias(self):
  x=graph()
  for owner in ['relation','mission']:
   for field,v in x[owner].items():
    for replacement in [float(v),True,False]:
     y=copy.deepcopy(x);y[owner][field]=replacement
     with self.subTest(owner=owner,field=field,v=replacement),self.assertRaises(ValueError):m.select_graph(**y)
 def test_entry_alias(self):
  for field in ['pointer','id','status','mission']:
   x=graph();x['envoys'][0][field]=float(x['envoys'][0][field])
   with self.assertRaises(ValueError):m.select_graph(**x)
 def test_no_effect_promotions(self):
  for a in [True,False]:
   for b in [True,False]:
    p=m.phase_sequence(a,b);self.assertFalse(p['effect_verified']);self.assertFalse(p['production_ready']);self.assertEqual(p['order'][0],'initial_selected_census');self.assertEqual(p['order'][-1],'final_selected_census')
 def test_report_budget_includes_exploration(self):
  r=json.loads((HERE/'report.json').read_text());n=sum(f['decoded_bytes'] for f in r['functions'].values());self.assertEqual(n,19581);self.assertEqual(r['limits']['new_decoded_bytes'],n);self.assertLessEqual(n,65536);self.assertEqual(r['limits']['window_per_cfg'],8192)
 def test_report_actual_cancel_not_ui(self):
  r=json.loads((HERE/'report.json').read_text());facts={f['id']:f for f in r['facts']};a={x['rva'] for x in facts['actual_cancel_effect']['anchors']};self.assertIn('0x5ad7f0',a);self.assertIn('0x5ad7e9',a);self.assertFalse(r['runtime_verified']);self.assertFalse(r['production_ready'])
if __name__=='__main__':unittest.main()
