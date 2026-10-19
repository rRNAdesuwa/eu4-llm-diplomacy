"""R2 full-pipeline budget regressions, fake-memory inputs only."""
import copy
import struct
import unittest
import test_reviewer as t

r=t.r

def required(record):
    c=t.DENSE.report()
    pins={row['rva']:row for fact in c['facts'].values() for row in fact['evidence']}
    calls=len(record['before']['trace'])+len(record['dense']['reads'])+len(record['after']['trace'])+len(pins)+1
    size=record['before']['read_budget']['bytes']+record['dense']['read_bytes']+record['after']['read_budget']['bytes']+sum(len(bytes.fromhex(row['bytes']))for row in pins.values())+8
    return calls,size

class SharedBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=t.records()
    def inputs(self):return copy.deepcopy(self.original)
    def reject(self,values):
        with self.assertRaises(ValueError):r.review_records(*values)
    def test_reported_sum_of_nested_calls_above_shared8192(self):
        values=self.inputs();record=values[0]['spy_reports'][r.ORDER[0]]
        for side in ('before','after'):
            record[side]['trace']=[dict(address=0x10000,size=1,sha256='0'*64)for _ in range(8192)]
            record[side]['read_budget'].update(calls=8192,bytes=8192)
        record['read_budget'].update(calls=1,bytes=16384+record['dense']['read_bytes'])
        self.reject(values)
        record['read_budget'].update(calls=8192,bytes=required(record)[1])
        self.reject(values)
    def test_reported_outer_calls_one_each_family_and_phase(self):
        for phase in (0,1):
            for family in r.ORDER:
                with self.subTest(phase=phase,family=family):
                    values=self.inputs();values[phase]['spy_reports'][family]['read_budget']['calls']=1
                    self.reject(values)
    def test_exact_known_lower_bound_accepted(self):
        values=self.inputs()
        for phase in values[:2]:
            for record in phase['spy_reports'].values():
                calls,size=required(record)
                self.assertEqual(record['read_budget']['calls'],calls)
                self.assertEqual(record['read_budget']['bytes'],size)
                record['read_budget'].update(calls=calls,bytes=size)
        self.assertEqual(r.review_records(*values)['status'],'reviewed_manual_ui_batch_selected_observation')
    def test_missing_final_pins_or_one_call_rejected(self):
        for shortage in (1,2):
            values=self.inputs();record=values[0]['spy_reports'][r.ORDER[0]]
            record['read_budget']['calls']=required(record)[0]-shortage
            self.reject(values)
        values=self.inputs();record=values[0]['spy_reports'][r.ORDER[0]]
        record['read_budget']['calls']=len(record['before']['trace'])+len(record['dense']['reads'])+len(record['after']['trace'])
        self.reject(values)
    def test_final_pin_bytes_are_required(self):
        for shortage in (1,8):
            values=self.inputs();record=values[1]['spy_reports'][r.ORDER[-1]]
            record['read_budget']['bytes']=required(record)[1]-shortage
            self.reject(values)
    def test_cap_is_not_increased_and_typed_counts(self):
        values=self.inputs();record=values[0]['spy_reports'][r.ORDER[0]]
        record['read_budget']['calls']=8192
        self.assertFalse(r.review_records(*values)['production_ready'])
        for bad in (8193,True,False,8192.0,'8192'):
            record['read_budget']['calls']=bad;self.reject(values)
    def test_pinned_final_read_count_matches_actual_pure_helper(self):
        c=t.DENSE.report();base=t.FIXTURE.MOCK.Fixture.BASE
        pins={int(row['rva'],16):(bytes.fromhex(row['bytes']))for fact in c['facts'].values()for row in fact['evidence']}
        class Reader:
            def read(self,address,size):
                if address==base+0x1c427b8:
                    assert size==8;return struct.pack('<Q',base+0x8e6190)
                raw=pins[address-base];assert len(raw)==size;return raw
        budget=t.DENSE.Budget(Reader());t.DENSE.code_pins(budget,base,c)
        self.assertEqual(len(budget.reads),len(pins)+1)
        self.assertEqual(budget.bytes,sum(map(len,pins.values()))+8)

if __name__=='__main__':unittest.main()
