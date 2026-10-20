from copy import deepcopy
import unittest
from pathlib import Path
import audit_mock as a
HERE=Path(__file__).resolve().parent
class HostJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=a.read_records(HERE/'validation-attempt-7/mock-events.jsonl')
    def test_actual_cpp_mock_full_run(self):
        result=a.inspect(self.rows)
        self.assertTrue(result['mock_host_to_sealed_model_passed'])
        for values in result['legality_results'].values():self.assertTrue(all(v is False for v in values.values()))
        for key in ('actual_host_authenticated','actual_native_log_replayed','runtime_verified','production_ready','send_supported'):self.assertIs(result[key],False)
    def test_real_origin_never_borrows_mock_projection(self):
        rows=deepcopy(self.rows)
        for r in rows:r['mock_environment']=False
        with self.assertRaisesRegex(ValueError,'Unsupported real Host'):a.inspect(rows)
    def test_every_observed_field_has_exact_typed_binding(self):
        for key,value in self.rows[0]['observed'].items():
            for bad in (None,False,True,float(value),str(value)):
                if type(bad)is type(value) and bad==value:continue
                rows=deepcopy(self.rows);rows[1]['observed'][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises((ValueError,TypeError)):a.inspect(rows)
    def test_no_later_health_or_complete_result(self):
        for kind in ('health','run_result'):
            rows=deepcopy(self.rows)
            at=max(i for i,r in enumerate(rows) if r['event']==kind);del rows[at]
            with self.assertRaises(ValueError):a.inspect(rows)
    def test_core_and_host_identity_cannot_be_swapped(self):
        for key,value in [('thread',1),('pid',1),('creation','0000000000000001'),('frame',False),('uptime_ms',True),('ordinal',1.0)]:
            rows=deepcopy(self.rows);rows[10][key]=value
            with self.assertRaises(ValueError):a.inspect(rows)
    def test_claim_expiry_and_stage_are_original_bytes(self):
        for key,value in [('expires',1),('sequence',2),('stage','owned_command'),('claim_created_and_flushed',1)]:
            rows=deepcopy(self.rows);next(r for r in rows if r['event']=='claim')[key]=value
            with self.assertRaises(ValueError):a.inspect(rows)
    def test_intent_is_not_native_enter(self):
        rows=deepcopy(self.rows);row=next(r for r in rows if r['event']=='core_event' and r['core']['kind']==1)
        row['core']['call_entered']=True
        with self.assertRaises(ValueError):a.inspect(rows)
    def test_fault_result_unobserved_is_never_success(self):
        for key,value in [('event','terminal_result'),('current_observation_verified',False),('runtime_verified',True)]:
            rows=deepcopy(self.rows);next(r for r in rows if r['event']=='run_result')[key]=value
            with self.assertRaises(ValueError):a.inspect(rows)
if __name__=='__main__':unittest.main()
