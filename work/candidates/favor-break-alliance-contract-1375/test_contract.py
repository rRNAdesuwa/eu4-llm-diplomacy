import unittest
from dataclasses import replace
import contract as c
A=0x100007a00415246;B=0x100004200474e45;C=0x100007b00524f50
class Tests(unittest.TestCase):
 def test_roles(self):
  a=c.request(A,B,C,42);self.assertEqual((a.actor,a.current_actor,a.recipient,a.third_party),(A,A,B,C))
 def test_raw_tags_rejected(self):
  for v in (0x415246,0,A&0x00ffffffffffffff,True,float(A)):
   with self.subTest(v=v),self.assertRaises(ValueError):c.request(v,B,C,42)
 def test_same_roles(self):
  for roles in [(A,A,C),(A,B,A),(A,B,B)]:
   with self.assertRaises(ValueError):c.request(*roles,42)
 def test_generation_same_slot(self):
  with self.assertRaises(ValueError):c.request(A,B,A+(1<<56),42)
 def test_no_false_cancel(self):
  for v in (False,0,1,None):
   with self.assertRaises(ValueError):c.request(A,B,C,42,value=v)
 def test_no_response_force(self):
  for s in (1,2,False,0.0):
   with self.assertRaises(ValueError):c.request(A,B,C,42,state=s)
 def test_date_types(self):
  for x in (-1,2**31,True,42.0):
   with self.assertRaises(ValueError):c.request(A,B,C,x)
 def test_clone_primary_asymmetry(self):
  a=replace(c.request(A,B,C,42),secondary_date=99,flag=1);b=c.clone(a)
  self.assertEqual((b.primary_date,b.secondary_date,b.flag),(42,42,0));self.assertEqual(a.secondary_date,99)
 def test_clone_third_handle(self):
  a=c.request(A,B,C,42);self.assertEqual(c.clone(a).third_party,C)
 def test_wrapper_current_secondary(self):
  a=c.request(A,B,C,42);self.assertEqual(c.wrapped_clone(a,100).secondary_date,100);self.assertEqual(a.secondary_date,42)
 def check_selected(self,**kw):
  args=dict(now=100,entries=[],favors_milli=50000,cost_units=50,opinion=50,required_opinion=50,allied_actor=True,actor_war=False,recipient_war=False);args.update(kw)
  return c.selected_readonly_predicates(**args)
 def test_selected_not_permission(self):
  r=self.check_selected();self.assertTrue(r['selected_pass']);self.assertIsNone(r['full_permission']);self.assertFalse(r['construct_authorized'])
 def test_cooldown_strict(self):
  self.assertTrue(self.check_selected(entries=[(0x3bcb,100)])['selected_pass']);self.assertFalse(self.check_selected(entries=[(0x3bcb,101)])['selected_pass'])
 def test_other_token(self):self.assertTrue(self.check_selected(entries=[(0x3375,1000)])['selected_pass'])
 def test_cooldown_ambiguous(self):
  with self.assertRaises(ValueError):self.check_selected(entries=[(0x3bcb,1),(0x3bcb,2)])
 def test_cooldown_bound(self):
  with self.assertRaises(ValueError):self.check_selected(entries=[(i,0) for i in range(257)])
 def test_cooldown_typed(self):
  for pair in [(True,1),(0x3bcb,100.0),[0x3bcb,1]]:
   with self.assertRaises(ValueError):self.check_selected(entries=[pair])
 def test_favors_scale(self):self.assertFalse(self.check_selected(favors_milli=49999)['selected_pass'])
 def test_opinion_boundary(self):self.assertFalse(self.check_selected(opinion=49)['selected_pass'])
 def test_missing_alliance(self):self.assertFalse(self.check_selected(allied_actor=False)['selected_pass'])
 def test_war(self):
  self.assertFalse(self.check_selected(actor_war=True)['selected_pass']);self.assertFalse(self.check_selected(recipient_war=True)['selected_pass'])
 def test_flag_typed(self):
  with self.assertRaises(ValueError):self.check_selected(allied_actor=1)
 def test_response_distinct(self):
  self.assertEqual(c.effect_classification(0),'pending_no_acceptance_effect');self.assertNotEqual(c.effect_classification(1),c.effect_classification(2))
 def test_response_type(self):
  with self.assertRaises(ValueError):c.effect_classification(True)
 def test_ownership(self):
  o=c.Ownership();o.wrap();o.destroy_original();self.assertTrue(o.clone);o.destroy_command();self.assertFalse(o.clone)
 def test_double_free(self):
  o=c.Ownership();o.wrap();o.destroy_command()
  with self.assertRaises(ValueError):o.destroy_command()
 def test_exception_no_cleanup_guess(self):
  o=c.Ownership();o.wrap();o.exception()
  with self.assertRaises(ValueError):o.destroy_command()
  with self.assertRaises(ValueError):o.destroy_original()
if __name__=='__main__':unittest.main()
