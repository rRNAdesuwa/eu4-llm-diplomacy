"""Complete fake-adapter runs and terminal boundaries; never invoke any CLI."""
from copy import deepcopy
import unittest
import batch as b


def plan(mode='initial_final'):
    return dict(protocol='EU4LAB/3',purpose='restricted_pair_lab_1375_v17',pid=100,
        creation='01dd000000000001',world_cookie='0x100000',window_thread=101,first_sequence=2,
        observation_mode=mode,run_id='synthetic',rows=[{'action':a,'target':t} for a,t in b.MATRIX])


class Fake:
    def __init__(self, mode='initial_final', rejects=()):
        self.audit=[];self.model=b.Batch(plan(mode),self.audit.append);self.now=1000;self.rejects=set(rejects)
        self.h=dict(pid=100,creation='01dd000000000001',world_cookie='0x100000',thread=101,raw_date=56456976,
            last_sequence=1,uptime_ms=1000,world_ready=True,lifecycle_passed=True,owned_peace_passed=True,
            preview_passed=True,command_passed=True,session_frozen=False,world_changed=False,thread_changed=False,
            acceptance_flag=0,acceptance_state='closed',paused=True,native_speed_index=0,pending=False,
            lease_active=False,lease_pending=False,mailbox_ready=True)
        self.calls=[]

    def next(self):
        self.now+=10;self.h['uptime_ms']=self.now
        return self.model.next(self.h,self.now)

    def result(self,c):
        r={k:c[k] for k in ('pid','creation','world_cookie')};r['validated_frozen_evidence']=True
        if c['kind']=='observe':
            r.update(boundary=c['boundary'],observation_kind='cross_date_selected_state_census',artifact_sha256='a'*64,
                     diplomat_count=103,idle_state_zero_count=100,individual_effect_verified=False,
                     raw_date=c['raw_date'],last_sequence=c['last_sequence'],paused=True,two_pass_consistent=True,
                     observed_uptime_ms=self.now)
        else:
            r.update(sequence=c['sequence'],audit_complete=True,session_frozen=False,ownership_uncertain=False,exception=0)
            if c['kind']=='speed':r.update(status='completed_and_paused',supervisor_complete=True,before_date=c['before_date'],after_date=c['before_date']+24)
            else:
                allowed=c['action'] not in self.rejects;submit=c['mode']=='submit' and allowed
                r.update({k:c[k] for k in ('action','actor','target','mode','raw_date')})
                r.update(status=2 if submit else 1,reason=0 if allowed else 17,preview_called=True,preview_allowed=allowed,
                    gate_called=allowed,gate_allowed=allowed,submit_entered=submit,submit_returned=submit,
                    context_submit_return=True if submit else None,caller_container_consumed=True if submit else None)
        return r

    def finish(self,decision,result=None):
        c=decision['command'];r=self.result(c) if result is None else result
        self.calls.append(c);out=self.model.receive(decision['command_id'],r,self.now)
        if out['state']!='terminal' and c['kind']!='observe':
            self.h['last_sequence']=c['sequence']
            if c['kind']=='speed':self.h['raw_date']=r['after_date']
        return out

    def run(self):
        for _ in range(400):
            d=self.next()
            if d['state'] in ('complete','terminal'):return self.model.summary()
            if d['state']=='start_once':self.finish(d)
        raise AssertionError('Unbounded fake batch')

    def until_kind(self, kind):
        for _ in range(400):
            d=self.next()
            if d['state']!='start_once':raise AssertionError(d)
            if d['command']['kind']==kind:return d
            self.finish(d)
        raise AssertionError('Missing fake command kind')


class BatchTests(unittest.TestCase):
    def test_all_36_native_paths_default_only_initial_final_census(self):
        f=Fake();r=f.run()
        self.assertEqual(r['state'],'complete');self.assertEqual(len(r['rows']),70)
        self.assertEqual(r['native_dispatch_count'],34);self.assertEqual(r['legality_attempt_count'],36)
        self.assertEqual([x['action'] for x in r['rows'] if x['mode']=='legality_only'],list(b.ORDER))
        self.assertFalse(any(x['action'] in b.SURVEY_ONLY and x['mode']=='submit' for x in r['rows']))
        self.assertEqual([x['boundary'] for x in r['observations']],['initial','final'])
        self.assertTrue(all(x['individual_effect_verified'] is False for x in r['rows']))
        self.assertEqual(r['positive_effects_before_cancellation'],'unobserved')
        seq=[c['sequence'] for c in f.calls if c['kind']!='observe']
        self.assertEqual(seq,list(range(2,2+len(seq))))
        self.assertLessEqual(len(seq),128);self.assertFalse(r['production_backend_registered'])

    def test_all_legality_rejected_skip_submit_without_sequence_holes(self):
        f=Fake(rejects=b.ORDER);r=f.run()
        self.assertEqual(r['state'],'complete');self.assertEqual(len(r['rows']),36)
        self.assertTrue(all(c.get('mode')!='submit' for c in f.calls))
        seq=[c['sequence'] for c in f.calls if c['kind']!='observe']
        self.assertEqual(seq,list(range(2,2+len(seq))))
        self.assertTrue(all(x['outcome']=='known_rejection_no_submit' for x in r['rows']))

    def test_cancellation_is_legality_checked_even_positive_not_dispatched(self):
        f=Fake(rejects=[p[0] for p in b.PAIRS]);r=f.run()
        for _,cancel in b.PAIRS:
            self.assertTrue(any(x['action']==cancel and x['mode']=='legality_only' for x in r['rows']))

    def test_poll_does_not_repeat_publication_while_job_running(self):
        f=Fake();d=f.next();n=len(f.audit)
        for _ in range(5):self.assertEqual(f.next()['state'],'waiting')
        self.assertEqual(len(f.audit),n);self.assertEqual(f.model.inflight['id'],d['command_id'])

    def test_timeout_is_terminal_and_late_ack_cannot_resume(self):
        f=Fake();d=f.next();f.now+=50000
        self.assertEqual(f.next()['state'],'terminal')
        self.assertEqual(f.finish(d)['state'],'terminal');self.assertEqual(f.next()['state'],'terminal')

    def test_unknown_ownership_stops_before_next_request(self):
        f=Fake();f.finish(f.next());f.finish(f.next());d=f.next();r=f.result(d['command'])
        r['caller_container_consumed']=False
        self.assertEqual(f.finish(d,r)['state'],'terminal');self.assertEqual(f.next()['state'],'terminal')

    def test_real_world_or_sequence_interference_stops(self):
        for key,value in (('world_cookie','0x200000'),('creation','01dd000000000002'),('last_sequence',9),('session_frozen',True)):
            f=Fake();f.h[key]=value
            with self.subTest(key=key):self.assertEqual(f.next()['state'],'terminal')

    def test_stale_or_alias_readiness_rejected(self):
        for key,value in (('native_speed_index',False),('last_sequence',True),('acceptance_flag',False),('thread',101.0)):
            f=Fake();f.h[key]=value
            with self.subTest(key=key):self.assertEqual(f.next()['state'],'terminal')

    def test_completed_speed_still_waits_for_latest_lease_false(self):
        f=Fake();d=f.until_kind('speed');f.finish(d)
        f.h.update(lease_active=True,lease_pending=True,mailbox_ready=False)
        count=len(f.audit);self.assertEqual(f.next()['state'],'waiting_for_paused_health');self.assertEqual(len(f.audit),count)
        f.h.update(lease_active=False,lease_pending=False,mailbox_ready=True)
        self.assertEqual(f.next()['command']['kind'],'pair')

    def test_date_lease_without_progress_cannot_be_retried(self):
        f=Fake();d=f.until_kind('speed');r=f.result(d['command'])
        r['after_date']=d['command']['before_date']
        self.assertEqual(f.finish(d,r)['state'],'terminal');self.assertEqual(f.next()['state'],'terminal')

    def test_expired_or_changed_date_legality_does_not_publish_submit(self):
        for change_date in (False,True):
            f=Fake();f.finish(f.next());f.finish(f.next())
            if change_date:f.h['raw_date']+=24
            else:f.now+=60000
            with self.subTest(change_date=change_date):self.assertEqual(f.next()['state'],'terminal')

    def test_initial_resource_guard_and_aggregate_nonpromotion(self):
        f=Fake();d=f.next();r=f.result(d['command']);r['diplomat_count']=3
        self.assertEqual(f.finish(d,r)['state'],'terminal')
        f=Fake();d=f.next();r=f.result(d['command']);r['individual_effect_verified']=True
        self.assertEqual(f.finish(d,r)['state'],'terminal')

    def test_no_acceptance_window_can_be_held_by_batch(self):
        f=Fake();f.h.update(acceptance_state='armed',acceptance_flag=1)
        self.assertEqual(f.next()['state'],'terminal')

    def test_durable_intent_failure_prevents_command_return(self):
        f=Fake()
        def fail(_):raise OSError('disk full')
        f.model.journal=fail
        with self.assertRaises(OSError):f.next()
        self.assertEqual(f.model.state,'terminal');self.assertEqual(f.calls,[])

    def test_argv_uses_existing_capture_and_watchdog_only(self):
        f=Fake();f.finish(f.next());d=f.next();a=b.argv(d['command'])
        self.assertIn('work/run_lab_step_v17_1375.py',a);self.assertEqual(a[-3:],['--ttl-ms','60000','--publish'])
        with self.assertRaises(ValueError):b.argv(dict(d['command'],amount=25000))
        f.finish(d);d=f.until_kind('speed');a=b.argv(d['command'])
        self.assertIn('--ack-disposable',a);self.assertNotIn('tools/request_diplomacy_lab_v17.py',a)

    def test_wrong_result_request_identity_and_numeric_types(self):
        for key,value in (('sequence',True),('action','console'),('raw_date',56456976.0),('exception',False)):
            f=Fake();f.finish(f.next());d=f.next();r=f.result(d['command']);r[key]=value
            with self.subTest(key=key):self.assertEqual(f.finish(d,r)['state'],'terminal')

    def test_plan_rejects_unimplemented_or_scalar_extension(self):
        p=plan();p['rows'][0]['action']='declare_war'
        with self.assertRaises(ValueError):b.validate_plan(p)

    def test_late_ack_without_intervening_poll_is_terminal(self):
        f=Fake();d=f.next();f.now+=40001
        self.assertEqual(f.finish(d)['state'],'terminal')

    def test_speed_before_date_and_next_paused_health_are_bound(self):
        f=Fake();d=f.until_kind('speed');r=f.result(d['command'])
        r['before_date']+=24
        self.assertEqual(f.finish(d,r)['state'],'terminal')
        f=Fake();d=f.until_kind('speed');f.finish(d)
        f.h['raw_date']+=24
        self.assertEqual(f.next()['state'],'terminal')

    def test_large_pool_does_not_imply_100_idle_candidates(self):
        f=Fake();d=f.next();r=f.result(d['command']);r['idle_state_zero_count']=3
        self.assertEqual(f.finish(d,r)['state'],'terminal')
        p=plan();p['rows'][0]['amount']=1000
        with self.assertRaises(ValueError):b.validate_plan(p)

    def test_fixed_target_order_and_single_observation_mode(self):
        for mutate in (lambda p:p['rows'][0].update(target='POR'),
                       lambda p:p['rows'].reverse(),lambda p:p.update(observation_mode='positive_boundary')):
            p=plan();mutate(p)
            with self.assertRaises(ValueError):b.validate_plan(p)

    def test_dispatch_with_failed_or_uncalled_legality_is_contradictory(self):
        for key in ('preview_called','preview_allowed','gate_called','gate_allowed'):
            f=Fake();f.finish(f.next());f.finish(f.next());d=f.next();r=f.result(d['command']);r[key]=False
            with self.subTest(key=key):self.assertEqual(f.finish(d,r)['state'],'terminal')

    def test_observation_is_bound_to_requested_date_sequence_and_sample_time(self):
        for key,value in (('raw_date',56456977),('raw_date',56456976.0),('last_sequence',0),
                          ('last_sequence',True),('observed_uptime_ms',1),('two_pass_consistent',False),('paused',False)):
            f=Fake();d=f.next();r=f.result(d['command']);r[key]=value
            with self.subTest(key=key):self.assertEqual(f.finish(d,r)['state'],'terminal')

    def test_monotonic_clock_cannot_regress_between_commands(self):
        f=Fake();f.finish(f.next());f.now-=100
        self.assertEqual(f.next()['state'],'terminal')

    def test_survey_only_cannot_compile_submit_even_with_internal_command(self):
        f=Fake()
        for _ in range(200):
            d=f.next()
            self.assertEqual(d['state'],'start_once')
            if d['command'].get('action')=='support_independence':break
            f.finish(d)
        with self.assertRaises(ValueError):b.argv(dict(d['command'],mode='submit'))
        f.finish(d);self.assertEqual(f.model.mode,'legality_only')
        self.assertEqual(f.model.plan['rows'][f.model.index]['action'],'stop_improving_relations')

    def test_same_target_attempts_are_new_date_even_if_rejected(self):
        f=Fake(rejects=b.ORDER);self.assertEqual(f.run()['state'],'complete')
        seen={}
        for c in f.calls:
            if c['kind']=='pair':
                self.assertGreater(c['raw_date'],seen.get(c['target'],0));seen[c['target']]=c['raw_date']

    def test_finite_matrix_matches_reviewed_plan_without_extra_actions(self):
        import hashlib,json
        from pathlib import Path
        raw=(Path(__file__).resolve().parent.parent/'v17-batch-action-matrix-1375'/'plan.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'f63080fd20ee949dc44ec76b819deac7b00eae71ae05220cc268f3a715b23a6b')
        rows=json.loads(raw)['rows']
        self.assertEqual([(r['action'],r['target']) for r in rows],list(b.MATRIX))
        self.assertEqual({r['action'] for r in rows if r['submit_policy']=='guard_survey_only'},b.SURVEY_ONLY)
        self.assertEqual(len(set(b.ORDER)),36)

    def test_inflight_fatal_health_is_latched_before_later_good_ack(self):
        for key,value in (('session_frozen',True),('world_changed',True),('thread_changed',True),
                          ('world_cookie','0x200000'),('pid',101),('creation','01dd000000000002'),
                          ('thread',102),('acceptance_flag',1),('world_ready',False)):
            f=Fake();f.finish(f.next());d=f.next();saved=dict(f.h);f.h[key]=value
            with self.subTest(key=key):
                self.assertEqual(f.next()['state'],'terminal')
                f.h=saved;self.assertEqual(f.finish(d)['state'],'terminal');self.assertEqual(f.next()['state'],'terminal')

    def test_inflight_own_consumed_sequence_running_lease_is_allowed(self):
        f=Fake();d=f.until_kind('speed');f.h.update(last_sequence=d['command']['sequence'],paused=False,
            native_speed_index=5,pending=True,lease_active=True,lease_pending=True,mailbox_ready=False)
        self.assertEqual(f.next()['state'],'waiting')

    def test_unreturned_ownership_fields_must_be_null(self):
        for mode in ('allowed','rejected'):
            for key in ('context_submit_return','caller_container_consumed'):
                f=Fake(rejects=[] if mode=='allowed' else b.ORDER);f.finish(f.next());d=f.next();r=f.result(d['command']);r[key]=True
                with self.subTest(mode=mode,key=key):self.assertEqual(f.finish(d,r)['state'],'terminal')


if __name__=='__main__':unittest.main()
