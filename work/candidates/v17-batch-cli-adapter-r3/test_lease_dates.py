"""Finite fake-publisher pipeline: callback date is not final paused date."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
import adapter as a
import test_adapter as base


class LeaseDateTests(unittest.TestCase):
    setUp=base.AdapterTests.setUp
    tearDown=base.AdapterTests.tearDown
    run_fake=base.AdapterTests.run_fake

    def publications(self):
        return [v for v in self.engine.calls if '--sequence' in v]

    def shift_final_date(self,capture,entry):
        if entry['request']['operation']!='speed':return
        self.engine.date+=24
        report=capture['report'];report['after_date']=self.engine.date
        path=Path(report['report']);rows=[json.loads(x) for x in path.read_text().splitlines()]
        rows[1]['after']['raw_date']=self.engine.date
        path.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8')

    def test_full_36_callback_plus48_final_plus72_pipeline(self):
        self.engine.mutate=self.shift_final_date
        value=self.run_fake()
        self.assertEqual(value['state'],'complete',value)
        self.assertEqual(value['legality_attempt_count'],36)
        self.assertEqual(self.engine.observe,['initial','final'])
        self.assertFalse(value['individual_effect_verified'])
        for seq,pause in self.engine.lease_cores.items():
            self.assertEqual(pause['before_date'],pause['after_date'])
            self.assertEqual(pause['before_date'],self.engine.lease_arms[seq]['initial_raw_date']+48)

    def test_known_completion_still_waits_for_final_date_heartbeat(self):
        self.engine.mutate=self.shift_final_date;original=self.engine.snapshot;gate={'old':True}
        def snapshot(scope):
            box=original(scope);seq=str(self.engine.seq)
            if gate['old'] and seq in self.engine.lease_cores:
                box['evidence']['latest_frame']['raw_date']=self.engine.lease_cores[seq]['after_date']
            return box
        self.engine.snapshot=snapshot
        for _ in range(180):
            self.engine.now+=200;self.adapter.tick()
            self.assertNotEqual(self.adapter.model.state,'terminal',self.adapter.model.failure)
            if self.adapter.model.date_leases and self.adapter.model.expected_health is not None:break
        else:self.fail('Expected known speed receipt')
        count=len(self.publications());expected=self.adapter.model.expected_health
        self.assertEqual(expected['raw_date'],self.engine.date)
        for _ in range(6):
            self.engine.now+=200;self.adapter.tick();self.assertEqual(len(self.publications()),count)
        gate['old']=False
        for _ in range(8):
            self.engine.now+=200;self.adapter.tick()
            if len(self.publications())>count:break
        self.assertEqual(len(self.publications()),count+1)
        self.assertIsNone(self.adapter.model.expected_health)

    def reject_first_speed(self,mutate):
        def action(capture,entry):
            if entry['request']['operation']=='speed':mutate(capture,entry)
        self.engine.mutate=action;value=self.run_fake()
        self.assertEqual(value['state'],'terminal',value)
        calls=self.publications();self.assertEqual(calls[-1][calls[-1].index('--output')+2],'speed')
        return value

    def test_pause_core_internal_date_change_rejected(self):
        def mutation(c,e):self.engine.lease_cores[str(e['request']['sequence'])]['after_date']+=24
        value=self.reject_first_speed(mutation)
        self.assertIn('Speed handler/cleanup/date proof differs',value['failure'])

    def test_pause_core_after_final_paused_date_rejected(self):
        def mutation(c,e):
            p=self.engine.lease_cores[str(e['request']['sequence'])]
            p['before_date']+=24;p['after_date']+=24
        value=self.reject_first_speed(mutation)
        self.assertIn('Unsupported lease pause/final date interval',value['failure'])

    def test_under_two_day_pause_is_not_guessed_timer_triggered(self):
        def mutation(c,e):
            p=self.engine.lease_cores[str(e['request']['sequence'])]
            p['before_date']-=24;p['after_date']-=24
        value=self.reject_first_speed(mutation)
        self.assertIn('Unsupported lease pause/final date interval',value['failure'])

    def test_arm_initial_date_cannot_be_rewritten_to_authorize_short_pause(self):
        def mutation(c,e):self.engine.lease_arms[str(e['request']['sequence'])]['initial_raw_date']-=24
        value=self.reject_first_speed(mutation)
        self.assertIn('Native lease start/identity differs',value['failure'])

    def test_arm_type_aliased_is_rejected(self):
        def mutation(c,e):self.engine.lease_arms[str(e['request']['sequence'])]['maximum_raw_date_delta']=48.0
        value=self.reject_first_speed(mutation)
        self.assertIn('Native lease start/identity differs',value['failure'])

    def test_armed_deadline_outside_original_request_interval_rejected(self):
        def mutation(c,e):self.engine.lease_arms[str(e['request']['sequence'])]['deadline_uptime_ms']=e['request']['expires']+5000
        value=self.reject_first_speed(mutation)
        self.assertIn('Native lease deadline outside',value['failure'])

    def test_arm_wrong_process_identity_rejected(self):
        def mutation(c,e):self.engine.lease_arms[str(e['request']['sequence'])]['pid']+=1
        value=self.reject_first_speed(mutation)
        self.assertIn('Native lease start/identity differs',value['failure'])

    def test_missing_raw_arm_cannot_be_inferred_from_completion(self):
        def mutation(c,e):self.engine.lease_arms.pop(str(e['request']['sequence']))
        value=self.reject_first_speed(mutation)
        self.assertTrue(value['failure'])

    def test_arm_deadline_prior_to_issue_plus5000_rejected(self):
        def mutation(c,e):
            pending=self.adapter.model.inflight['command']
            self.engine.lease_arms[str(e['request']['sequence'])]['deadline_uptime_ms']=pending['issued_uptime_ms']+4999
        value=self.reject_first_speed(mutation)
        self.assertIn('Native lease deadline outside',value['failure'])

    def test_real_deadline_upper_strict_boundary_minus1_accepted(self):
        def mutation(c,e):
            if e['request']['operation']=='speed':
                self.engine.lease_arms[str(e['request']['sequence'])]['deadline_uptime_ms']=e['request']['expires']+4999
        self.engine.mutate=mutation
        value=self.run_fake()
        self.assertEqual(value['state'],'complete',value)

    def test_exact_prefix_preserves_raw_arm_and_rejects_duplicate(self):
        row=dict(event='lab_lease_armed',sequence=9,initial_raw_date=123)
        raw=(json.dumps(row)+'\n').encode();p=self.root/'prefix.jsonl';p.write_bytes(raw)
        arms={};self.assertEqual(a.lease_completions(p,len(raw),a.hashlib.sha256(raw).hexdigest(),arms),{})
        self.assertEqual(arms,{'9':row})
        p.write_bytes(raw+raw)
        with self.assertRaises(ValueError):a.lease_completions(p,len(raw+raw),a.hashlib.sha256(raw+raw).hexdigest(),{})
        p.write_bytes(raw+b'{"event":"not_in_verified_prefix"}\n')
        arms={};a.lease_completions(p,len(raw),a.hashlib.sha256(raw).hexdigest(),arms)
        self.assertEqual(arms,{'9':row})


if __name__=='__main__':unittest.main()
