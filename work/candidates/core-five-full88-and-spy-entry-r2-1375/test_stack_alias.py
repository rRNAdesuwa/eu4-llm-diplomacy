import copy,re,struct,unittest
import contract
class StackTests(unittest.TestCase):
 def test_affine_prologue_operand_bytes(self):
  d=contract.document();e=d['stack_alias_repair']['prologue_evidence'];a,b=[bytes.fromhex(x['bytes']) for x in e]
  self.assertEqual(a[:4],bytes.fromhex('488d6c24'));self.assertEqual(b[:3],bytes.fromhex('4881ec'))
  delta=struct.unpack('b',a[4:])[0]+struct.unpack('<i',b[3:])[0]
  self.assertEqual(delta,0xb9);self.assertEqual(0x30-delta,-0x89)
 def test_four_corrected_aliases(self):
  d=contract.document()
  for family in d['stack_alias_repair']['four_families']:
   self.assertEqual(contract.profile(family,False)['original_stack_base'],'rsp+0x30 / rbp-0x89')
   self.assertEqual((-0x79)-(-0x89),0x10);self.assertNotEqual((-0x79)-(-0x81),0x10)
  self.assertEqual(contract.profile('royal_marriage',False)['original_stack_base'],'rbp-0x49')
 def test_actual_saved_stores_match_action_fields(self):
  d=contract.document()
  for family in d['profiles']:
   base=-0x49 if family=='royal_marriage' else -0x89
   fields=set()
   for row in d['instruction_slices'][family]:
    m=re.match(r'mov (qword|dword|word|byte) ptr \[rbp - (0x[0-9a-f]+|[0-9]+)\],',row['instruction'])
    if m:fields.add((-int(m[2],0))-base)
   self.assertTrue({0x10,0x18,0x20,0x28,0x2c,0x30,0x34,0x38,0x3c}<=fields,(family,fields))
 def test_no_ownership_or_runtime_promotion(self):
  d=contract.document();self.assertEqual(d['limits']['new_decode_bytes'],0)
  for family in d['profiles']:
   p=contract.profile(family,False)
   self.assertFalse(p['owned_heap_original_cleanup_normal_caller_proved']);self.assertFalse(p['constructor_authorized'])
   self.assertFalse(p['native_ready']);self.assertFalse(p['production_ready'])
