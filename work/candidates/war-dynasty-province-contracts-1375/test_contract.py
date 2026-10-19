import unittest
from copy import deepcopy
import contract as c

FRA=0x0100007a00415246;ENG=0x0100008200474e45;POR=0x0100008b00524f50
TABLE={122:FRA,130:ENG,139:POR};DATE=56456976
PARAMS={'claim_throne':{},'sell_province':{'price_integer':2000,'province_id':183},'enforce_peace':{'opposing_country':POR},'threaten_war':{'province_id':183,'taker_country':FRA}}

class ContractTests(unittest.TestCase):
 def action(self,name):return c.initialize(name,FRA,ENG,DATE,deepcopy(PARAMS[name]),TABLE)
 def test_factory_sizes_tokens_defaults(self):
  self.assertEqual([x['token'] for x in c.PROFILES.values()],[0x2949,0x2a29,0x2dda,0x3307])
  for n,p in c.PROFILES.items():
   b=c.factory(n);self.assertEqual(len(b),p['size']);self.assertEqual(c.get(b,8,'I'),0x165)
   for off in (0x10,0x18,0x20):self.assertEqual(c.get(b,off,'Q'),c.INVALID_HANDLE)
   self.assertEqual(c.get(b,0x28,'i'),c.DEFAULT_DATE);self.assertEqual(c.get(b,0x2c,'i'),c.DEFAULT_DATE)
   self.assertEqual(c.get(b,0x30,'i'),-1);self.assertEqual(c.get(b,0x34,'i'),0);self.assertEqual(b[0x38:0x3a],b'\1\0')
 def test_derived_defaults_are_not_valid_params(self):
  self.assertEqual(c.get(c.factory('sell_province'),0x40,'i'),-1)
  self.assertEqual(c.get(c.factory('sell_province'),0x44,'i'),-1)
  self.assertEqual(c.get(c.factory('enforce_peace'),0x40,'Q'),c.INVALID_HANDLE)
  self.assertEqual(c.get(c.factory('threaten_war'),0x44,'Q'),c.INVALID_HANDLE)
 def test_normal_base_fields(self):
  for n in c.PROFILES:
   b=self.action(n)
   self.assertEqual([c.get(b,x,'Q') for x in (0x10,0x18,0x20)],[FRA,FRA,ENG])
   self.assertEqual([c.get(b,x,'i') for x in (0x28,0x2c)],[DATE,DATE])
   self.assertEqual(c.get(b,0x34,'i'),0)
 def test_strict_country_types(self):
  for bad in (True,float(FRA),'FRA',122,None):
   with self.subTest(bad=bad),self.assertRaises(ValueError):c.initialize('claim_throne',bad,ENG,DATE,{},TABLE)
 def test_full_generation_not_slot_only(self):
  with self.assertRaises(ValueError):c.initialize('claim_throne',FRA^(1<<48),ENG,DATE,{},TABLE)
 def test_target_full_identity(self):
  with self.assertRaises(ValueError):c.initialize('claim_throne',FRA,ENG^(1<<48),DATE,{},TABLE)
 def test_mock_table_wrong_slot_rejected(self):
  for t in ({True:FRA}, {122:float(FRA)}, {121:FRA}, {122:FRA,130:ENG,5000:POR}):
   with self.subTest(table=t),self.assertRaises(ValueError):c.initialize('claim_throne',FRA,ENG,DATE,{},t)
 def test_actor_target_different(self):
  with self.assertRaises(ValueError):c.initialize('claim_throne',FRA,FRA,DATE,{},TABLE)
 def test_no_false_cancel_mode(self):
  for value in (False,0,1,None):
   with self.assertRaises(ValueError):c.initialize('claim_throne',FRA,ENG,DATE,{},TABLE,value=value)
 def test_no_external_reply_state(self):
  with self.assertRaises(ValueError):c.initialize('claim_throne',FRA,ENG,DATE,{'state':2},TABLE)
 def test_dates_strict(self):
  for d in (True,1.0,0,-1,2**31):
   with self.assertRaises(ValueError):c.initialize('claim_throne',FRA,ENG,d,{},TABLE)
 def test_sell_integer_unit(self):
  b=self.action('sell_province');self.assertEqual(c.get(b,0x40,'i'),2000);self.assertEqual(c.treasury_milli(2000),2000000)
 def test_sell_milli_alias_not_accepted(self):
  with self.assertRaises(ValueError):c.initialize('sell_province',FRA,ENG,DATE,{'amount_milli':2000,'province_id':183},TABLE)
 def test_sell_overflow_boundary(self):
  self.assertEqual(c.treasury_milli(2147483),2147483000)
  for n in (2147484,-1,True,0.5):
   with self.assertRaises(ValueError):c.treasury_milli(n)
 def test_province_ids_strict(self):
  for name in ('sell_province','threaten_war'):
   for value in (0,-1,True,1.0,2**31):
    p=deepcopy(PARAMS[name]);p['province_id']=value
    with self.subTest(name=name,value=value),self.assertRaises(ValueError):c.initialize(name,FRA,ENG,DATE,p,TABLE)
 def test_enforce_not_war_id(self):
  with self.assertRaises(ValueError):c.initialize('enforce_peace',FRA,ENG,DATE,{'war_id':139},TABLE)
  with self.assertRaises(ValueError):c.initialize('enforce_peace',FRA,ENG,DATE,{'opposing_country':139},TABLE)
 def test_enforce_full_third_identity(self):
  self.assertEqual(c.get(self.action('enforce_peace'),0x40,'Q'),POR)
  for h in (FRA,ENG,POR^(1<<48)):
   with self.assertRaises(ValueError):c.initialize('enforce_peace',FRA,ENG,DATE,{'opposing_country':h},TABLE)
 def test_threaten_unaligned_taker(self):
  b=self.action('threaten_war');self.assertEqual(c.get(b,0x44,'Q'),FRA);self.assertNotEqual(c.get(b,0x48,'Q'),FRA)
 def test_threaten_only_proven_taker_profile(self):
  p=deepcopy(PARAMS['threaten_war']);p['taker_country']=POR
  with self.assertRaises(ValueError):c.initialize('threaten_war',FRA,ENG,DATE,p,TABLE)
 def test_clone_uses_primary_twice_not_secondary(self):
  for n in c.PROFILES:
   b=self.action(n);c.put(b,0x2c,'i',DATE-120);b[0x39]=1
   out=c.clone(n,b);self.assertIsNot(out,b);self.assertEqual(c.get(out,0x2c,'i'),DATE);self.assertEqual(out[0x39],0)
   self.assertEqual(c.get(b,0x2c,'i'),DATE-120);self.assertEqual(b[0x39],1)
 def test_clone_nonzero_parameters_preserved(self):
  for n in c.PROFILES:
   b=self.action(n);self.assertEqual(c.serialized_parameters(n,c.clone(n,b)),c.serialized_parameters(n,b))
 def test_exact_buffer_and_vtable(self):
  for n in c.PROFILES:
   b=self.action(n)
   with self.assertRaises(ValueError):c.clone(n,b+b'\0')
   c.put(b,0,'Q',0)
   with self.assertRaises(ValueError):c.clone(n,b)
 def test_serialized_tokens(self):
  self.assertEqual(c.serialized_parameters('sell_province',self.action('sell_province')),{0x1a1:2000,0x2843:183})
  self.assertEqual(c.serialized_parameters('enforce_peace',self.action('enforce_peace')),{0x2dda:POR})
  self.assertEqual(c.serialized_parameters('threaten_war',self.action('threaten_war')),{0x2843:183,0x314d:FRA})
 def test_wrapper_secondary_date_is_current(self):
  m=c.OwnedModel('enforce_peace',self.action('enforce_peace'));m.wrap(DATE+24)
  self.assertEqual(c.get(m.command_clone,0x28,'i'),DATE);self.assertEqual(c.get(m.command_clone,0x2c,'i'),DATE+24)
  self.assertEqual(c.get(m.original,0x2c,'i'),DATE)
 def test_original_and_owned_clone_cleanup_independent(self):
  m=c.OwnedModel('claim_throne',self.action('claim_throne'));m.wrap(DATE);m.destroy_original()
  self.assertFalse(m.clone_destroyed);m.destroy_command();self.assertTrue(m.clone_destroyed)
 def test_command_first_cleanup(self):
  m=c.OwnedModel('claim_throne',self.action('claim_throne'));m.wrap(DATE);m.destroy_command()
  self.assertFalse(m.original_destroyed);m.destroy_original()
 def test_double_destruction_and_wrapper_rejected(self):
  m=c.OwnedModel('claim_throne',self.action('claim_throne'));m.wrap(DATE)
  with self.assertRaises(ValueError):m.wrap(DATE)
  m.destroy_command()
  with self.assertRaises(ValueError):m.destroy_command()
  m.destroy_original()
  with self.assertRaises(ValueError):m.destroy_original()
 def test_exception_is_terminal_not_cleanup_permission(self):
  m=c.OwnedModel('claim_throne',self.action('claim_throne'));m.wrap(DATE);m.exception()
  for fn in (m.destroy_original,m.destroy_command,lambda:m.wrap(DATE),m.send):
   with self.assertRaises(ValueError):fn()
 def test_preview_false_is_normal_no_send_permission(self):
  for a in (False,True):
   for b in (False,True):
    for g in (False,True):self.assertFalse(c.gate_observation(a,b,g)['send_permission'])
  with self.assertRaises(ValueError):c.gate_observation(1,True,True)
 def test_claim_unilateral_not_accept_state(self):
  self.assertEqual(c.reply_branch('claim_throne',0),c.reply_branch('claim_throne',2))
 def test_declined_enforcement_can_join_war(self):self.assertEqual(c.reply_branch('enforce_peace',1),'may_execute_join_war')
 def test_declined_threat_can_declare_war(self):self.assertEqual(c.reply_branch('threaten_war',1),'may_execute_declare_war')
 def test_pending_does_not_claim_absence(self):self.assertEqual(c.reply_branch('sell_province',0),'pending_or_unhandled_no_effect_conclusion')
 def test_claim_observer_mask_and_direction(self):
  self.assertTrue(c.claim_record_bit(FRA,ENG,TABLE,FRA,ENG,5));self.assertFalse(c.claim_record_bit(FRA,ENG,TABLE,FRA,ENG,4))
  for owner,target in ((ENG,FRA),(FRA,POR),(float(FRA),ENG)):
   with self.assertRaises(ValueError):c.claim_record_bit(FRA,ENG,TABLE,owner,target,1)
 def test_no_unknown_family_or_native_operation(self):
  with self.assertRaises(ValueError):c.factory('declare_war')
  with self.assertRaises(ValueError):c.OwnedModel('claim_throne',self.action('claim_throne')).send()

if __name__=='__main__':unittest.main()
