import copy,struct,unittest
import constructor_model as m
A=0x0100007a00415246;B=0x0100003300474e45;DATE=56456976

class ConstructorTests(unittest.TestCase):
 def test_every_independent_constructor(self):
  for name in m.NAMES:
   with self.subTest(name=name):self.assertTrue(m.inspect(name,m.replay(name,A,B,DATE),A,B,DATE)['normal_constructor_model_matches'])
 def test_score_mode_never_value_false(self):
  for name in m.NAMES:self.assertEqual(m.replay(name,A,B,DATE,False),m.replay(name,A,B,DATE,True))
 def test_all_semantic_bytes_mutated_rejected(self):
  offsets=[*range(0,12),*range(16,58),*range(60,64)]
  for name in m.NAMES:
   raw=m.replay(name,A,B,DATE)
   for offset in offsets:
    b=bytearray(raw);b[offset]^=1
    with self.subTest(name=name,offset=offset),self.assertRaises(ValueError):m.inspect(name,bytes(b),A,B,DATE)
 def test_padding_not_constrained(self):
  for name in m.NAMES:
   b=bytearray(m.replay(name,A,B,DATE))
   for offset in [12,13,14,15,58,59]:b[offset]^=0xff
   m.inspect(name,bytes(b),A,B,DATE)
 def test_stale_generation_rejected(self):
  for name in m.NAMES:
   b=m.replay(name,A,B,DATE)
   with self.assertRaises(ValueError):m.inspect(name,b,A+(1<<56),B,DATE)
 def test_wrong_date_rejected(self):
  for name in m.NAMES:
   with self.assertRaises(ValueError):m.inspect(name,m.replay(name,A,B,DATE),A,B,DATE+24)
 def test_numeric_aliases(self):
  for bad in [True,False,float(A),A&0xffffffff]:
   with self.assertRaises(ValueError):m.replay('sow_discontent',bad,B,DATE)
  for bad in [True,float(DATE),0,-1,2**31]:
   with self.assertRaises(ValueError):m.replay('sow_discontent',A,B,bad)
 def test_score_type(self):
  for bad in [0,1,1.0,None]:
   with self.assertRaises(ValueError):m.replay('slander_merchants',A,B,DATE,bad)
 def test_explicit_store_value_mutation_detected(self):
  for name in m.NAMES:
   seq=copy.deepcopy(m.family(name)['initialization_instructions'])
   selected=next(x for x in seq if x['instruction'].startswith('mov word ptr'))
   selected['instruction']=selected['instruction'].rsplit(', ',1)[0]+', 0'
   with self.assertRaises(ValueError):m.inspect(name,m.replay(name,A,B,DATE,instructions=seq),A,B,DATE)
 def test_outside_action_write_fails_closed(self):
  seq=copy.deepcopy(m.family('sow_discontent')['initialization_instructions'])
  seq.append({'rva':'0x0','bytes':'90','instruction':'mov dword ptr [rsp + 0x100], 0'})
  with self.assertRaisesRegex(ValueError,'outside'):m.replay('sow_discontent',A,B,DATE,instructions=seq)
 def test_unknown_instruction_not_simulated(self):
  seq=[{'rva':'0x0','bytes':'90','instruction':'call rax, rax'}]
  with self.assertRaisesRegex(ValueError,'unsupported'):m.replay('sow_discontent',A,B,DATE,instructions=seq)
 def test_no_runtime_or_authority(self):
  for name in m.NAMES:
   out=m.inspect(name,m.replay(name,A,B,DATE),A,B,DATE)
   for key in ['native_call_authorized','runtime_verified','production_ready']:self.assertIs(out[key],False)
 def test_token_vtable_not_interchangeable(self):
  a=m.replay('sow_discontent',A,B,DATE)
  with self.assertRaises(ValueError):m.inspect('sabotage_recruitment',a,A,B,DATE)
 def test_unknown_family(self):
  for bad in ['spy_network','sow_discontent_false','',False,None]:
   with self.assertRaises(ValueError):m.replay(bad,A,B,DATE)
 def test_bounded_payload(self):
  for raw in [bytes(63),bytes(65),bytearray(64),None]:
   with self.assertRaises(ValueError):m.inspect('sow_discontent',raw,A,B,DATE)
 def test_budget(self):
  limits=m.report()['limits'];self.assertEqual(limits['new_cfg_decoded_bytes'],1664)
  self.assertEqual(limits['total_new_code_bytes'],1694);self.assertEqual(limits['window_per_cfg'],8192)
if __name__=='__main__':unittest.main()
