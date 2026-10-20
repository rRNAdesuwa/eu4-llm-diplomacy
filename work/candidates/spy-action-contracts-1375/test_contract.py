import copy, io, json, unittest
from pathlib import Path
import contract, trace

def sample():
    return dict(process_creation=123,world=0x100000,date=56456976,
                actor_handle=0x0100007a00415246,target_handle=0x0100000100474e45,
                definition=0x123456,expected_expiry=56500776,
                network_centipoints=6000,cost_milli=25000,
                modifiers=[],collection_complete=True)

class ContractTests(unittest.TestCase):
    def test_regular_fee_units(self):
        self.assertTrue(contract.cost_sufficient(2500,25000))
        self.assertFalse(contract.cost_sufficient(2499,25000))
        self.assertEqual(contract.debit_centipoints(6000,25000),3500)

    def test_rounding_and_clamp(self):
        self.assertEqual(contract.debit_centipoints(100,4),100)
        self.assertEqual(contract.debit_centipoints(100,5),99)
        self.assertEqual(contract.debit_centipoints(100,995),0)

    def test_overflow_negative_and_bool(self):
        for a,b in [(True,1),(1,False),(1,1.0),(-1,0),(10001,1),(1,21474832),(1,-1)]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):contract.debit_centipoints(a,b)

    def test_only_correlated_result(self):
        a=sample();b=copy.deepcopy(a);b['network_centipoints']=3500
        b['modifiers']=[dict(object=0x999,definition=a['definition'],expiry=a['expected_expiry'])]
        r=contract.correlate(a,b)
        self.assertEqual(r['new_matching_modifier_count'],1)
        self.assertIs(r['cost_delta_matches'],True)
        for k in ('causality_verified','engine_lifetime_verified','native_call_authorized','runtime_verified'):
            self.assertIs(r[k],False)

    def test_absence_is_not_success(self):
        r=contract.correlate(sample(),sample())
        self.assertEqual(r['new_matching_modifier_count'],0)
        self.assertIs(r['cost_delta_matches'],False)

    def test_identity_date_definition_change(self):
        for k in ('process_creation','world','date','actor_handle','target_handle','definition','expected_expiry','cost_milli'):
            a=sample();b=copy.deepcopy(a);b[k]+=1
            with self.subTest(k=k),self.assertRaises(ValueError):contract.correlate(a,b)

    def test_bool_float_typed_identity(self):
        for k in ('process_creation','world','date','actor_handle','target_handle','definition','expected_expiry'):
            for bad in (True,float(sample()[k])):
                a=sample();a[k]=bad
                with self.subTest(k=k,bad=bad),self.assertRaises(ValueError):contract.correlate(a,a)

    def test_schema_and_incomplete(self):
        for mode in ('missing','extra','incomplete','integer_bool'):
            a=sample()
            if mode=='missing':del a['world']
            if mode=='extra':a['permission']=True
            if mode=='incomplete':a['collection_complete']=False
            if mode=='integer_bool':a['collection_complete']=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):contract.correlate(a,a)

    def test_existing_modifier_and_duplicate(self):
        a=sample();a['modifiers']=[dict(object=11,definition=a['definition'],expiry=a['expected_expiry'])]
        with self.assertRaises(ValueError):contract.correlate(a,a)
        a=sample();b=copy.deepcopy(a);m=dict(object=11,definition=99,expiry=1);b['modifiers']=[m,m]
        with self.assertRaises(ValueError):contract.correlate(a,b)

    def test_handle_encoding_not_bare_tag(self):
        for bad in (1,0x00415246,0x0100800000415246,0x0100007a01615246):
            a=sample();a['actor_handle']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):contract.correlate(a,a)

    def test_budget_actual_read_not_stat(self):
        class P:
            name='fake-padded-input'
            def open(self,mode):return io.BytesIO(b' '*17)
        with self.assertRaises(ValueError):trace.bounded_bytes(P(),16)

    def test_modified_instruction_rejected(self):
        class P:
            def bytes_at(self,rva,size):return b'\x90'*size
        trace.verify_rows(P(),[dict(rva='0x100',bytes='90')])
        with self.assertRaises(ValueError):trace.verify_rows(P(),[dict(rva='0x100',bytes='c3')])
        with self.assertRaises(ValueError):trace.verify_rows(P(),[dict(rva='0x100',bytes='')])

    def test_static_report_not_capability(self):
        r=trace.load(Path(__file__).parent/'report.json')
        self.assertFalse(r['runtime_verified']);self.assertFalse(r['production_ready'])
        self.assertLessEqual(r['limits']['new_decoded_bytes'],40960)
        self.assertEqual(len(r['families']),5)
        for f in r['families']:
            self.assertEqual(f['size'],64);self.assertFalse(f['false_is_undo_verified'])
            self.assertEqual(f['slots']['0x100'],'0x8f450')
            self.assertEqual(f['slots']['0xd0'],'0x8f450')

if __name__=='__main__':unittest.main()
