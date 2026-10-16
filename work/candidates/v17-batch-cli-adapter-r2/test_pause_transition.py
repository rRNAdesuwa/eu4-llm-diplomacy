"""Actual tick/worker functions with fake Popen and fake read-only processes only."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import adapter as a
import test_adapter as base


class PauseTransitionTests(unittest.TestCase):
    setUp=base.AdapterTests.setUp
    tearDown=base.AdapterTests.tearDown
    run_fake=base.AdapterTests.run_fake

    def publications(self):
        return [v for v in self.engine.calls if '--sequence' in v]

    def install_transition(self):
        original=self.engine.snapshot
        gate={'old_frame':True,'first_speed':None}
        def snapshot(scope):
            box=original(scope)
            speeds=[(s,e) for s,e in self.engine.requests.items() if e['request']['operation']=='speed']
            if speeds and gate['first_speed'] is None:gate['first_speed']=speeds[0][0]
            if gate['old_frame'] and speeds and self.engine.seq==gate['first_speed']:
                box['evidence']['latest_frame']['raw_date']=speeds[0][1]['records'][0]['before_date']
            return box
        self.engine.snapshot=snapshot
        return gate

    def until_known_speed(self):
        for _ in range(180):
            self.engine.now+=200;self.adapter.tick()
            self.assertNotEqual(self.adapter.model.state,'terminal',self.adapter.model.failure)
            if self.adapter.model.expected_health is not None and self.adapter.model.date_leases:
                return
        self.fail('Speed receipt not reached')

    def test_known_speed_old_paused_frame_waits_then_fresh_frame_releases_next_once(self):
        gate=self.install_transition();self.until_known_speed()
        before=len(self.publications());date=self.engine.date
        for _ in range(6):
            self.engine.now+=200;self.adapter.tick()
            self.assertEqual(len(self.publications()),before)
            self.assertNotEqual(self.adapter.model.state,'terminal')
            self.assertEqual(self.adapter.model.last_health_date,date)
        self.assertIsNotNone(self.adapter.model.expected_health)
        h=a.health_from_status(self.adapter.status_box,self.adapter.scope,self.engine.now)
        self.assertFalse(h['paused']);self.assertEqual(h['raw_date'],date)
        gate['old_frame']=False
        for _ in range(8):
            self.engine.now+=200;self.adapter.tick()
            if len(self.publications())>before:break
        self.assertEqual(len(self.publications()),before+1)
        self.assertIsNone(self.adapter.model.expected_health)
        previous=self.publications()[-2];current=self.publications()[-1]
        self.assertEqual(int(current[current.index('--sequence')+1]),int(previous[previous.index('--sequence')+1])+1)

    def test_permanently_nonconverged_pause_hits_existing_timeout_without_republish(self):
        self.install_transition();self.until_known_speed();count=len(self.publications())
        for _ in range(60):
            self.engine.now+=200;self.adapter.tick()
            if self.adapter.model.state=='terminal':break
        self.assertEqual(self.adapter.model.state,'terminal')
        self.assertIn('Paused-ready health did not arrive',self.adapter.model.failure)
        self.assertEqual(len(self.publications()),count)

    def test_observed_live_highwater_cannot_regress_even_with_old_frame(self):
        self.install_transition();self.until_known_speed();count=len(self.publications())
        self.engine.date-=24
        for _ in range(6):
            self.engine.now+=200;self.adapter.tick()
            if self.adapter.model.state=='terminal':break
        self.assertEqual(self.adapter.model.state,'terminal')
        self.assertIn('Date regressed',self.adapter.model.failure)
        self.assertEqual(len(self.publications()),count)

    def test_transition_does_not_mask_world_invalidation_or_revive_terminal(self):
        self.install_transition();self.until_known_speed();count=len(self.publications())
        original=self.engine.snapshot
        def changed(scope):
            box=original(scope);box['evidence']['latest_frame']['world_changed']=True;return box
        self.engine.snapshot=changed
        for _ in range(6):
            self.engine.now+=200;self.adapter.tick()
            if self.adapter.model.state=='terminal':break
        self.assertEqual(self.adapter.model.state,'terminal')
        self.engine.snapshot=original
        for _ in range(6):self.engine.now+=200;self.adapter.tick()
        self.assertEqual(len(self.publications()),count)

    def test_typed_sampler_rejects_aliases_missing_fields_and_temporal_regressions(self):
        original=self.engine.snapshot(self.adapter.scope)
        variants=[('live_before','pid',100.0),('live_after','raw_date',float(self.engine.date)),
            ('pause_after','paused',1),('pause_before','native_speed_index',False),
            ('pause_after','game',float(0x100000)),('live_before','acceptance_flag',False),
            ('live_after','creation','01dd000000000002'),('live_after','player_handle','0x0100002e00474e45'),
            ('pause_after','server',0x200008),('live_after','raw_date',self.engine.date-1),
            ('pause_after','raw_date',self.engine.date-1)]
        for section,key,value in variants:
            with self.subTest(section=section,key=key,value=value),self.assertRaises(ValueError):
                box=deepcopy(original);box[section][key]=value;a.health_from_status(box,self.adapter.scope,self.engine.now)
        for key,value in [('raw_date',self.engine.date+1),('raw_date',float(self.engine.date)),('uptime_ms',False),
                          ('native_speed_index',False),('paused',1),('world_ready',1),('thread',101.0)]:
            with self.subTest(frame=key),self.assertRaises(ValueError):
                box=deepcopy(original);box['evidence']['latest_frame'][key]=value
                a.health_from_status(box,self.adapter.scope,self.engine.now)
        for key in ('live_before','pause_before'):
            with self.subTest(missing=key),self.assertRaises(KeyError):
                box=deepcopy(original);del box[key];a.health_from_status(box,self.adapter.scope,self.engine.now)
        for key in ('pending','lease_pending','input_wait_pending'):
            with self.subTest(evidence=key),self.assertRaises(ValueError):
                box=deepcopy(original);box['evidence'][key]=0
                a.health_from_status(box,self.adapter.scope,self.engine.now)

    def test_internal_samples_moving_forward_are_pending_not_pause_proof(self):
        box=self.engine.snapshot(self.adapter.scope)
        box['live_after']['raw_date']+=24;box['pause_after']['raw_date']+=48
        box['evidence']['latest_frame']['raw_date']+=24
        h=a.health_from_status(box,self.adapter.scope,self.engine.now)
        self.assertFalse(h['paused']);self.assertEqual(h['raw_date'],self.engine.date+48)
        box['evidence']['latest_frame']['raw_date']=self.engine.date+48
        with self.assertRaises(ValueError):a.health_from_status(box,self.adapter.scope,self.engine.now)

    def test_fresh_status_timestamp_cannot_relabel_stale_heartbeat_ready(self):
        box=self.engine.snapshot(self.adapter.scope);self.engine.now=5000
        box['observed_uptime_ms']=5000
        with self.assertRaises(ValueError):a.health_from_status(box,self.adapter.scope,self.engine.now)

    def test_actual_worker_function_retains_old_paused_frame_without_ready_authorization(self):
        from work.native import lab_protocol_v17_1375 as lab
        from work.native import run_lab_speed_v17_1375 as speed
        box=self.engine.snapshot(self.adapter.scope)
        for key in ('live_before','live_after','pause_before','pause_after'):box[key]['raw_date']+=48
        class Process:
            reader=object()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def snapshot(self):return deepcopy(box['live_after'])
        manifest=dict(dll_sha256=self.adapter.scope['dll_sha256'])
        output=self.root/'fake-worker-status.json'
        with patch.object(lab,'verify_build',return_value=(manifest,self.adapter.scope['manifest_sha256'])), \
             patch.object(lab,'verify_installed_fixture',return_value=box['fixture_disk_evidence']), \
             patch.object(lab,'LiveLabProcess',return_value=Process()), \
             patch.object(lab,'session_path',return_value=self.root/'unused-session'), \
             patch.object(lab,'read_session_metadata',return_value=box['metadata']), \
             patch.object(lab,'read_evidence',return_value=dict(box['evidence'],log_bytes=1,log_sha256='a'*64)), \
             patch.object(lab,'uptime_ms',return_value=self.engine.now), \
             patch.object(speed,'paused_state',return_value=box['pause_after']), \
             patch.object(a,'lease_completions',return_value={}):
            a.status_worker(self.adapter.scope_path,output)
        result=a.read_json(output)
        h=a.health_from_status(result,self.adapter.scope,self.engine.now)
        self.assertFalse(h['paused']);self.assertEqual(h['raw_date'],self.engine.date+48)
        self.assertEqual(result['evidence']['latest_frame']['raw_date'],self.engine.date)
        self.assertEqual(self.publications(),[])


if __name__=='__main__':unittest.main()
