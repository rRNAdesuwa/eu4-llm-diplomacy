import copy,unittest
import prepare as m
class MatrixTests(unittest.TestCase):
 def setUp(self):self.plan,self.pins=m.generate();self.proto=m.fixed_protocol()
 def test_exact36_from_ast_and_twenty_families(self):
  self.assertEqual({r['action'] for r in self.plan['rows']},self.proto['actions']);self.assertEqual(len(m.PAIR_MAP),16)
  self.assertEqual(set(m.PAIR_MAP)|set(m.PAIR_MAP.values())|set(self.plan['positive_only']),self.proto['actions'])
 def test_targets_roles_and_topological_lanes(self):
  seen=set();last={}
  for r in self.plan['rows']:
   self.assertTrue(set(r['after_attempts'])<=seen);self.assertEqual(r['prior_same_target_action'],last.get(r['target']))
   if r['target'] in last:self.assertIn(last[r['target']],r['after_attempts'])
   seen.add(r['action']);last[r['target']]=r['action']
  self.assertEqual(set(last),{'ENG','POR','NAV','FOI'})
 def test_duplicates_missing_and_wrong_actor_reject(self):
  p=copy.deepcopy(self.plan);p['rows'][-1]=copy.deepcopy(p['rows'][0])
  with self.assertRaises(ValueError):m.validate(p,self.proto)
  p=copy.deepcopy(self.plan);p['rows'][0]['actor']='ENG'
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_future_dependency_and_order_bool_reject(self):
  p=copy.deepcopy(self.plan);p['rows'][0]['after_attempts']=['offer_vassalization']
  with self.assertRaises(ValueError):m.validate(p,self.proto)
  p=copy.deepcopy(self.plan);p['rows'][0]['order']=True
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_fixed_numeric_float_parameter_rejected(self):
  p=copy.deepcopy(self.plan);next(r for r in p['rows'] if r['action']=='give_subsidies')['fixed_parameters']['duration_years']=10.0
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_missions_different_targets(self):
  p=copy.deepcopy(self.plan);spy=next(r for r in p['rows'] if r['action']=='build_spy_network');spy['target']='FOI'
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_baseline_nav_is_not_por_roundtrip(self):
  rows={r['action']:r for r in self.plan['rows']};self.assertEqual(rows['cancel_vassalization']['target'],'NAV');self.assertEqual(rows['offer_vassalization']['target'],'POR')
  self.assertNotIn('offer_vassalization',rows['cancel_vassalization']['after_attempts'])
  p=copy.deepcopy(self.plan);next(r for r in p['rows'] if r['action']=='cancel_vassalization')['target']='FOI'
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_own_subject_support_survey_only(self):
  p=copy.deepcopy(self.plan);next(r for r in p['rows'] if r['action']=='support_independence')['submit_policy']='fresh_legality_then_submit_if_allowed'
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_no_effect_promotion_and_final_only_default(self):
  p=copy.deepcopy(self.plan);p['observations']['actual_default']=['initial','positive','final']
  with self.assertRaises(ValueError):m.validate(p,self.proto)
  p=copy.deepcopy(self.plan);p['rows'][0]['effect_verified']=True
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_strict_cooldown_and_no_parallel_request(self):
  p=copy.deepcopy(self.plan);p['scheduler']['same_target_requirement']='current_raw_date >= last_native_target_threshold'
  with self.assertRaises(ValueError):m.validate(p,self.proto)
  p=copy.deepcopy(self.plan);p['scheduler']['max_inflight_requests']=True
  with self.assertRaises(ValueError):m.validate(p,self.proto)
 def test_inputs_bounded_and_no_runtime_identity(self):
  self.assertLess(sum(r['bytes'] for r in self.pins['files'].values()),12*1024*1024)
  self.assertFalse(self.plan['actual_run_authorized']);self.assertNotIn('pid',self.plan);self.assertNotIn('sequence',self.plan['rows'][0])
 def test_fixture_and_foi_provenance(self):
  self.assertIn(b'vassalize = NAV',m.blob(m.ROOT/m.INPUTS[2]))
  history=m.blob(m.ROOT/m.INPUTS[5]);chunk=history.split(b'# France-Foix',1)[1].split(b'}',1)[0]
  self.assertIn(b'subject_type = appanage',chunk);self.assertIn(b'first = FRA',chunk);self.assertIn(b'second = FOI',chunk)
if __name__=='__main__':unittest.main()
