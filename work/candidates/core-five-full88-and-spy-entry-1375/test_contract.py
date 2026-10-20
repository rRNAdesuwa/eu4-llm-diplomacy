import copy,unittest
import contract
FAMILIES=('vassalaction','royal_marriage','improve_relation','guaranteeaction','spy_network')
ACTOR=0x0100007a00415246
def manager():return dict(vtable_rva=0x1cac380,marker=0x165,token=0x2746,kind=3,owner=ACTOR)
def entry():return dict(vtable_rva=0x1cac2f0,marker=0x165,kind=3,status=2,id=17)
class Tests(unittest.TestCase):
 def test_ten_modes(self):
  for f in FAMILIES:
   for cancel in (False,True):
    p=contract.profile(f,cancel);self.assertEqual(p['selected_mode']['value'],not cancel);self.assertTrue(p['normal_AI_structural_call_chain_proved']);self.assertFalse(p['native_ready']);self.assertFalse(p['constructor_authorized'])
 def test_exact_mode_types(self):
  for x in (0,1,0.,1.,None,'false',[],{}):
   with self.assertRaises(ValueError):contract.profile('spy_network',x)
 def test_family_rejects(self):
  for x in (True,1,None,[],{},'coalition','curry_favors','0x3378'):
   with self.assertRaises(ValueError):contract.profile(x,False)
 def test_distinct_preview(self):
  for f in FAMILIES:
   p=contract.profile(f,False)['full88'];self.assertEqual(p['slot'],'0x88');self.assertEqual(p['sink'],'NULL');self.assertIs(p['mode'],False);self.assertNotEqual(p['rva'],'0x4e9d00')
 def test_fields_and_dates(self):
  for f in FAMILIES:
   q=contract.profile(f,False)['initial_fields'];self.assertEqual(q['state34'],0);self.assertEqual(q['envoy30'],-1);self.assertEqual(q['primary28'],'current game+1dd0');self.assertEqual(q['secondary2c'],'same current game+1dd0')
 def test_spy_mode_is_native_resolved(self):
  self.assertIn('586330',contract.profile('spy_network',True)['selected_mode']['envoy_rule'])
  for f in FAMILIES[:-1]:self.assertEqual(contract.profile(f,True)['selected_mode']['envoy_rule'],'remains -1')
 def test_stack_is_not_heap_cleanup(self):
  for f in FAMILIES:
   p=contract.profile(f,False);self.assertEqual(p['original_storage'],'stack_local');self.assertFalse(p['owned_heap_original_cleanup_normal_caller_proved']);self.assertTrue(p['original_cleanup']['does_not_delete_stack_object'])
 def test_marriage_string(self):
  p=contract.profile('royal_marriage',False);self.assertEqual(p['size'],0x68);self.assertFalse(p['extra_fields']['force60']);self.assertIn('capacity15',p['extra_fields']['String32_at40']);self.assertIn('String32',p['original_cleanup']['kind'])
 def test_no_shared_mutable_profile(self):
  a=contract.profile('vassalaction',False);a['initial_fields']['state34']=2;self.assertEqual(contract.profile('vassalaction',False)['initial_fields']['state34'],0)
 def test_known_entry(self):self.assertTrue(contract.typed_spy_entry(entry(),manager(),ACTOR))
 def test_entry_int_types(self):
  for k,v in entry().items():
   for bad in (float(v),True,False,None,str(v)):
    e=entry();e[k]=bad;self.assertFalse(contract.typed_spy_entry(e,manager(),ACTOR),(k,bad))
 def test_manager_types_roles(self):
  for k,v in manager().items():
   for bad in (float(v),True,None,v+1):
    m=manager();m[k]=bad;self.assertFalse(contract.typed_spy_entry(entry(),m,ACTOR),(k,bad))
 def test_entry_bounds(self):
  for value in (0,0x7fffffff):e=entry();e['id']=value;self.assertTrue(contract.typed_spy_entry(e,manager(),ACTOR))
  for value in (-1,0x80000000,0xffffffff):e=entry();e['id']=value;self.assertFalse(contract.typed_spy_entry(e,manager(),ACTOR))
 def test_unknown_type_no_derived_reads(self):
  class Trap(dict):
   def get(self,k,*a):
    if k!='vtable_rva':raise AssertionError('derived read after unknown type')
    return 0x1c4b2b8
  self.assertFalse(contract.typed_spy_entry(Trap(vtable_rva=0x1c4b2b8),manager(),ACTOR))
 def test_missing_fields(self):
  for k in entry():
   e=entry();del e[k];self.assertFalse(contract.typed_spy_entry(e,manager(),ACTOR))
 def test_generation_not_slot_only(self):
  self.assertFalse(contract.typed_spy_entry(entry(),manager(),0x7a00415246));self.assertFalse(contract.typed_spy_entry(entry(),manager(),ACTOR^(1<<56)))
if __name__=='__main__':unittest.main()
