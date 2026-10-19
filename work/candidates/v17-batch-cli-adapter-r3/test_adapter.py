"""Synthetic files and fake Popen only; never run a CLI or inspect a process."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import adapter as a
from work.native.lab_protocol_v17_1375 import encode_request


def plan():
    return dict(protocol='EU4LAB/3',purpose='restricted_pair_lab_1375_v17',pid=100,
        creation='01dd000000000001',world_cookie='0x100000',window_thread=101,first_sequence=2,
        observation_mode='initial_final',run_id='synthetic',rows=[dict(action=x,target=y) for x,y in a.batch.MATRIX])


def core_for(c,thread=101):
    entered=c['mode']=='submit'
    return dict(event='pair_engine_complete',world=c['world_cookie'],raw_date=c['raw_date'],thread_id=thread,
        status=2 if entered else 1,reason=0,preview_called=True,preview_allowed=True,gate_called=True,gate_allowed=True,
        submit_entered=entered,submit_returned=entered,context_submit_return=True if entered else None,
        caller_container_consumed=True if entered else None,ownership_uncertain=False,exception=0,
        original_destroyed=True,command_destroyed_before_dispatch=not entered,freeze_session=False)


class FakeEngine:
    def __init__(self,root):
        self.root=root;self.p=plan();self.now=1000;self.date=56456976;self.seq=1;self.calls=[];self.requests={};self.observe=[]
        self.mutate=None;self.hang=False;self.lease_cores={};self.lease_arms={}
    def snapshot(self,scope):
        f=dict(world_cookie=self.p['world_cookie'],player_handle='0x0100007a00415246',thread=101,raw_date=self.date,
            uptime_ms=self.now,world_ready=True,session_frozen=False,world_changed=False,thread_changed=False,
            acceptance_flag=0,paused=True,native_speed_index=0,lease_active=False,mailbox_ready=True)
        live=dict(pid=100,creation=self.p['creation'],world_cookie=self.p['world_cookie'],player_handle='0x0100007a00415246',raw_date=self.date,acceptance_flag=0)
        pause=dict(game=0x100000,server=0x200000,pause_manager=0x300000,player=0x0100007a00415246,
            raw_date=self.date,paused=True,native_speed_index=0)
        e=dict(latest_frame=f,phases={k:True for k in ('lifecycle','owned_peace','preview','command')},
            acceptance_window=dict(state='closed'),last_sequence=self.seq,pending=False,lease_pending=False,
            requests=deepcopy(self.requests),input_wait_pending=False)
        return dict(purpose='v17_batch_read_only_status',production_backend_registered=False,pid=100,
            creation=self.p['creation'],manifest_sha256=scope['manifest_sha256'],dll_sha256=scope['dll_sha256'],
            observed_uptime_ms=self.now,evidence=e,live_before=deepcopy(live),live_after=live,
            pause_before=deepcopy(pause),pause_after=pause,metadata=dict(window_thread=101),lease_completions=deepcopy(self.lease_cores),lease_arms=deepcopy(self.lease_arms),
            fixture_disk_evidence=dict(pid=100,creation=self.p['creation'],profile_sha256=scope['fixture_profile_sha256'],
                fixture_definition_files_verified=True,installed_before_process_creation=True,engine_registration_verified=False))
    def observer(self,c):
        self.observe.append(c['boundary'])
        return dict(validated_frozen_evidence=True,pid=c['pid'],creation=c['creation'],world_cookie=c['world_cookie'],
            boundary=c['boundary'],observation_kind='cross_date_selected_state_census',artifact_sha256='a'*64,
            individual_effect_verified=False,raw_date=c['raw_date'],last_sequence=c['last_sequence'],paused=True,
            two_pass_consistent=True,observed_uptime_ms=c['issued_uptime_ms'],diplomat_count=103,idle_state_zero_count=100)
    def spawn(self,args,**kwargs):
        self.calls.append(args)
        class Process:
            pid=999
            stopped=False
            def poll(s):return None if self.hang else 0
            def kill(s):s.stopped=True
            def wait(s,timeout):return 0
        if 'worker-status' in args:
            scope=a.read_json(args[args.index('--scope')+1]);output=args[args.index('--output')+1]
            a.durable_new(output,self.snapshot(scope));return Process()
        capture=self.root/args[args.index('--output')+1];kind=args[args.index('--output')+2];rest=args[args.index('--output')+3:]
        sequence=int(rest[rest.index('--sequence')+1]);self.seq=sequence
        speed=kind=='speed'
        c=dict(pid=100,creation=self.p['creation'],world_cookie=self.p['world_cookie'],sequence=sequence,
            kind='speed' if speed else 'pair',raw_date=self.date,issued_uptime_ms=self.now)
        if not speed:
            c.update(action=rest[rest.index('pair')+1],actor='FRA',target=rest[rest.index('--target')+1],mode=rest[rest.index('--mode')+1])
        request=dict(pid=100,creation=self.p['creation'],sequence=sequence,expires=self.now+(5000 if speed else 60000),
            operation=c['kind'],mode=c.get('mode','submit'),action=c.get('action','none'),actor='FRA',target=c.get('target','FRA'),
            speed=5 if speed else 0,bound_action='none',bound_target='none',bound_submit_sequence=0)
        complete=dict(sequence=sequence,session_frozen=False,retry_allowed=False,applied_verified=False)
        if not speed:
            core=core_for(c)
            report=dict(purpose=self.p['purpose'],protocol='EU4LAB/3',publication=dict(status='published',sequence=sequence,pid=100,
                creation=self.p['creation'],native_dispatch_verified=False,automatic_retry=False,
                request_sha256=a.hashlib.sha256(encode_request(request)).hexdigest()))
            manifest=self.root/'work/runtime/native1375-v17/build.json'
            report.update(pid=100,creation=self.p['creation'],manifest_sha256=a.hashlib.sha256(manifest.read_bytes()).hexdigest(),dll_sha256='A'*64)
            entry=dict(request=request,records=[core],complete=complete)
        else:
            before=self.date;self.date+=48
            self.lease_arms[str(sequence)]=dict(event='lab_lease_armed',pid=100,process_creation_filetime=self.p['creation'],
                sequence=sequence,initial_raw_date=before,deadline_uptime_ms=self.now+5000,maximum_raw_date_delta=48,
                automatic_pause=True,reliable_generation_verified=False)
            core=dict(event='test_speed_complete',reason=0,write_entered=True,callback_returned=True,readback_matches=True,
                callback_success=True,result_destroyed=True,readback_observed=True,
                exception_code=0,freeze_session=False,thread_id=101,requested_speed=5,before_date=before,after_date=before,
                before_native_index=0,before_paused=True,after_native_index=4,after_paused=False,retry_allowed=False,diplomacy_submitted=False)
            self.lease_cores[str(sequence)]=dict(core,requested_speed=0,before_date=self.date,after_date=self.date,
                before_native_index=4,before_paused=False,after_native_index=0,after_paused=True)
            entry=dict(request=request,records=[core],complete=complete,lease_complete=dict(sequence=sequence,paused_readback=True))
            report=dict(status='completed_and_paused',before_date=before,after_date=self.date)
            common=dict(pid=100,creation=self.p['creation'],sequence=sequence,speed=5,retry_allowed=False)
            roots=dict(game=0x100000,server=0x200000,pause_manager=0x300000,player=0x0100007a00415246)
            log=[dict(common,event='supervisor_armed',deadline_seconds=12.0,before=dict(roots,raw_date=before)),
                 dict(common,event='supervisor_complete',elapsed_seconds=1.0,after=dict(roots,raw_date=self.date,paused=True,native_speed_index=0),native_lease_complete=entry['lease_complete'])]
            session=self.root/'work/runtime/native1375-v17'/f"session-100-{self.p['creation']}";session.mkdir(exist_ok=True)
            (session/f'{sequence:020}.supervisor.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in log),encoding='utf-8')
            report['report']=str(session/f'{sequence:020}.supervisor.jsonl')
        self.requests[sequence]=entry
        value=dict(purpose='one_explicit_v17_cli_capture',kind=kind,arguments=rest,exit_code=0,automatic_retry=False,
            applied_verified=False,stderr='',report=report)
        if self.mutate:self.mutate(value,entry)
        a.durable_new(capture,value)
        return Process()


class ImmediatePool:
    def submit(self,fn,c):
        from concurrent.futures import Future
        f=Future()
        try:f.set_result(fn(c))
        except BaseException as e:f.set_exception(e)
        return f
    def shutdown(self,**kwargs):pass


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        output=self.root/'work/runtime/native1375-v17';output.mkdir(parents=True)
        (output/'build.json').write_text(json.dumps(dict(dll_sha256='A'*64,fixture_profile=dict(profile_id='synthetic',source_sha256={}))))
        self.patches=[patch.object(a,'ROOT',self.root),patch.object(a,'verify_inputs',lambda:None),patch.object(a,'ThreadPoolExecutor',lambda **_:ImmediatePool())]
        self.patches.append(patch('builtins.print'))
        for p in self.patches:p.start()
        self.engine=FakeEngine(self.root);self.adapter=a.Adapter(plan(),self.engine.observer,clock=lambda:self.engine.now,spawn=self.engine.spawn)
    def tearDown(self):
        if self.adapter.model.state not in ('complete','terminal'):self.adapter.stop('test_end')
        self.adapter.finish()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def run_fake(self):
        for _ in range(1500):
            self.engine.now+=200;self.adapter.tick()
            if self.adapter.model.state in ('complete','terminal'):return self.adapter.model.summary()
        self.fail('Fake adapter exceeded finite loop')
    def test_full_36_fake_cli_and_status_batch_only_two_observers(self):
        r=self.run_fake();self.assertEqual(r['state'],'complete',r);self.assertEqual(r['native_dispatch_count'],34)
        self.assertEqual(self.engine.observe,['initial','final']);self.assertEqual(r['legality_attempt_count'],36)
        sequences=[int(x[x.index('--sequence')+1]) for x in self.engine.calls if '--sequence' in x]
        self.assertEqual(sequences,list(range(2,2+len(sequences))));self.assertFalse(r['individual_effect_verified'])
    def test_unknown_ownership_halts_without_second_publish(self):
        def mutate(c,e):
            if e['request']['mode']=='submit':e['records'][-1]['caller_container_consumed']=False
        self.engine.mutate=mutate;r=self.run_fake();self.assertEqual(r['state'],'terminal')
        self.assertEqual(len([x for x in self.engine.calls if '--sequence' in x]),2)
    def test_publication_capture_wrong_argv_is_terminal(self):
        self.engine.mutate=lambda c,e:c['arguments'].append('--unexpected')
        self.assertEqual(self.run_fake()['state'],'terminal')
    def test_published_hash_must_match_claim(self):
        self.engine.mutate=lambda c,e:c['report']['publication'].update(request_sha256='0'*64)
        self.assertEqual(self.run_fake()['state'],'terminal')
    def test_missing_owned_field_cannot_be_normalized(self):
        self.engine.mutate=lambda c,e:e['records'][-1].pop('caller_container_consumed')
        self.assertEqual(self.run_fake()['state'],'terminal')
    def test_existing_run_cannot_resume_or_republish(self):
        with self.assertRaises(ValueError):a.Adapter(plan(),self.engine.observer,clock=lambda:1000,spawn=self.engine.spawn)
        self.assertEqual(self.engine.calls,[])
    def test_nonreturned_context_result_true_rejected(self):
        self.engine.mutate=lambda c,e:e['records'][-1].update(context_submit_return=True)
        self.assertEqual(self.run_fake()['state'],'terminal')
    def test_numeric_alias_thread_rejected(self):
        snapshot=self.engine.snapshot
        def changed(scope):
            box=snapshot(scope);box['evidence']['latest_frame']['thread']=101.0;return box
        self.engine.snapshot=changed;self.assertEqual(self.run_fake()['state'],'terminal')
    def test_status_failure_never_runs_publication(self):
        self.engine.hang=True;self.assertEqual(self.run_fake()['state'],'terminal')
        self.assertFalse(any('--sequence' in c for c in self.engine.calls))
    def test_fsync_failure_prevents_publication(self):
        with patch.object(a.os,'fsync',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.adapter.record(dict(event='new_intent'))
        self.assertEqual(self.engine.calls,[])
    def test_bounded_json_and_duplicate_keys(self):
        p=self.root/'oversize.json';p.write_bytes(b' '*5)
        with self.assertRaises(ValueError):a.read_json(p,4)
        p.write_bytes(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):a.read_json(p)

    def test_pending_fatal_frame_cannot_be_recovered_by_good_ack(self):
        original=self.engine.snapshot
        def changed(scope):
            box=original(scope)
            if self.engine.requests:box['evidence']['latest_frame']['session_frozen']=True
            return box
        self.engine.snapshot=changed
        self.assertEqual(self.run_fake()['state'],'terminal')
        count=len(self.engine.calls);self.engine.snapshot=original
        for _ in range(5):self.adapter.tick()
        self.assertEqual(len(self.engine.calls),count)

    def test_receive_terminal_retains_intent_and_audits_terminal(self):
        self.engine.mutate=lambda c,e:e['records'][-1].update(gate_allowed=False)
        self.assertEqual(self.run_fake()['state'],'terminal')
        self.assertIsNotNone(self.adapter.model.inflight)
        records=[json.loads(s) for s in (self.adapter.run_dir/'journal.jsonl').read_text().splitlines()]
        self.assertTrue(any(r['event']=='batch_terminal' for r in records))

    def test_observer_timeout_is_unknown_not_cancellation_or_resume(self):
        from concurrent.futures import Future
        class PendingPool:
            def submit(self,*args):return Future()
            def shutdown(self,**kwargs):pass
        self.adapter.pool=PendingPool()
        self.assertEqual(self.run_fake()['state'],'terminal')
        self.assertIsNotNone(self.adapter.model.inflight);self.assertEqual(self.engine.observe,[])
        self.assertFalse(any('--sequence' in c for c in self.engine.calls))

    def test_wrong_publisher_build_stops(self):
        self.engine.mutate=lambda c,e:c['report'].update(manifest_sha256='f'*64)
        self.assertEqual(self.run_fake()['state'],'terminal')

    def test_reader_parse_failure_stops_without_publication(self):
        spawn=self.engine.spawn
        def corrupt(args,**kwargs):
            process=spawn(args,**kwargs)
            if 'worker-status' in args:Path(args[args.index('--output')+1]).write_text('{invalid')
            return process
        self.adapter.spawn=corrupt
        self.assertEqual(self.run_fake()['state'],'terminal')
        self.assertFalse(any('--sequence' in c for c in self.engine.calls))

    def test_running_speed_cleanup_false_stops(self):
        def mutate(c,e):
            if e['request']['operation']=='speed':e['records'][-1]['result_destroyed']=False
        self.engine.mutate=mutate;self.assertEqual(self.run_fake()['state'],'terminal')

    def test_typed_speed_contract_rejects_cleanup_date_and_speed_aliases(self):
        core=dict(event='test_speed_complete',thread_id=101,requested_speed=5,reason=0,before_date=123,
            before_native_index=0,before_paused=True,after_date=123,after_native_index=4,after_paused=False,
            exception_code=0,freeze_session=False,retry_allowed=False,diplomacy_submitted=False)
        core.update({k:True for k in ('write_entered','callback_returned','callback_success','result_destroyed','readback_observed','readback_matches')})
        a.speed_core(core,5,123,101)
        for key,value in (('callback_success',False),('result_destroyed',False),('readback_observed',False),('before_date',122),
                          ('after_date',124),('after_date',123.0),('after_native_index',5),('before_paused',False),('exception_code',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):a.speed_core(dict(core,**{key:value}),5,123,101)

    def test_lease_prefix_rehash_rejects_changed_or_truncated_input(self):
        p=self.root/'prefix.jsonl';raw=b'{"event":"research_frame"}\n';p.write_bytes(raw)
        self.assertEqual(a.lease_completions(p,len(raw),a.hashlib.sha256(raw).hexdigest()),{})
        with self.assertRaises(ValueError):a.lease_completions(p,len(raw),'a'*64)
        with self.assertRaises(ValueError):a.lease_completions(p,len(raw)-1,a.hashlib.sha256(raw[:-1]).hexdigest())

    def test_lease_pause_already_paused_is_a_known_set_operation(self):
        core=dict(event='test_speed_complete',thread_id=101,requested_speed=0,reason=0,before_date=123,
            before_native_index=4,before_paused=True,after_date=123,after_native_index=0,after_paused=True,
            exception_code=0,freeze_session=False,retry_allowed=False,diplomacy_submitted=False)
        core.update({k:True for k in ('write_entered','callback_returned','callback_success','result_destroyed','readback_observed','readback_matches')})
        a.speed_core(core,0,123,101)
        with self.assertRaises(ValueError):a.speed_core(dict(core,before_paused=1),0,123,101)


if __name__=='__main__':unittest.main()
