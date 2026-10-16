"""Real frozen validators replay synthetic raw native records and claim bytes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import reviewer as r


class NativeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter,cls.lab,cls.experiment,cls.modules=r.dependencies()
        synthetic=r.load_source('batch_stopped_native_fixture',r.ROOT/'work/candidates/v17-acceptance-experiment-review/synthetic.py')
        cls.fixture=synthetic.Fixture();cls.fixture.setUp();f=cls.fixture
        try:
            cut=next(i for i,e in enumerate(f.events) if e['event']=='research_frame' and e['last_sequence']==1)
            f.events=f.events[:cut+1];f.case['requests']=f.case['requests'][:1];f.submit=-1
            f.append_pair('offer_fleet_basing_rights',False)
            f.append_pair('offer_fleet_basing_rights',True,legality=2)
            f.append_speed();f.write_log()
            names={'session.json','install.claim','research-1375.jsonl'}
            names|={v[1] for v in cls.lab.PHASES.values()}|{v[1]+'.host-intent' for v in cls.lab.PHASES.values()}
            for seq in range(1,5):names|={f'{seq:020}.claim',f'{seq:020}.host-intent'}
            names|={'00000000000000000001.fixture-profile'}
            names|={'00000000000000000004.'+suffix for suffix in ('lease-pause.claim','supervisor.jsonl','publisher-output.txt')}
            cls.files={n:'session/'+n for n in names};cls.raw={cls.files[n]:(f.session/n).read_bytes() for n in names}
            cls.scope=dict(plan=dict(pid=f.b.PID,creation=f.b.CREATION,window_thread=f.b.THREAD))
            cls.base,cls.pre=f.b,f.pre
        except BaseException:f.doCleanups();raise
    @classmethod
    def tearDownClass(cls):cls.fixture.doCleanups()
    def setUp(self):self.raw=deepcopy(self.__class__.raw)
    def replay(self):
        inventory={n:dict(bytes=len(raw),sha256=r.ledger.digest(raw)) for n,raw in self.raw.items()}
        return r.NativeReplay(r.ledger.Artifacts(self.raw,inventory),self.files,self.scope,self.lab,self.adapter,self.base,self.pre)
    def test_stopped_native_complete_phase_claim_and_speed_replay(self):
        native=self.replay()
        try:
            self.assertEqual(native.full['last_sequence'],4);self.assertEqual(len(native.full['phase_proofs']['lifecycle']['lifecycle']),20)
            r.check_claims(native,self.base);self.assertEqual(set(native.speed_traces),{4})
        finally:native.close()
    def test_status_whole_evidence_cannot_borrow_future_request(self):
        native=self.replay()
        try:
            size=len(self.fixture.prefix);sha=r.ledger.digest(self.fixture.prefix)
            (native.directory/'research-1375.jsonl').write_bytes(self.fixture.prefix)
            e=r.json_shape(self.lab.read_evidence(native.directory,native.metadata))
            box=dict(evidence=e,metadata=native.metadata,lease_arms={},lease_completions={})
            native.status(box)
            box['evidence']['requests']['4']=native.full['requests']['4']
            with self.assertRaisesRegex(ValueError,'Cached status differs'):native.status(box)
        finally:native.close()
    def test_missing_claim_or_altered_wire_rejected(self):
        self.raw['session/00000000000000000003.claim']+=b'X'
        with self.assertRaises(ValueError):self.replay()
    def test_foreign_phase_metadata_rejected(self):
        doc=json.loads(self.raw['session/session.json']);doc['process_creation_filetime']='0000000000000001'
        self.raw['session/session.json']=json.dumps(doc).encode()
        with self.assertRaises(ValueError):self.replay()
    def test_exact_prefix_partial_line_and_wrong_hash_rejected(self):
        native=self.replay()
        try:
            box=dict(evidence=deepcopy(native.full),metadata=native.metadata,lease_arms={},lease_completions={})
            box['evidence']['log_bytes']-=1
            with self.assertRaises(ValueError):native.status(box)
            box['evidence']=deepcopy(native.full);box['evidence']['log_sha256']='a'*64
            with self.assertRaises(ValueError):native.status(box)
        finally:native.close()
    def test_cached_raw_arms_cannot_be_omitted(self):
        native=self.replay()
        try:
            arms={};pauses=self.adapter.lease_completions(native.directory/'research-1375.jsonl',len(native.raw),r.ledger.digest(native.raw),arms)
            box=dict(evidence=deepcopy(native.full),metadata=native.metadata,lease_arms=arms,lease_completions=pauses)
            native.status(box);box['lease_arms']={}
            with self.assertRaisesRegex(ValueError,'Cached lease proof'):native.status(box)
        finally:native.close()
    def test_pause_callback_date_can_precede_next_complete_engine_date(self):
        rows=[json.loads(line) for line in self.raw['session/research-1375.jsonl'].splitlines()]
        rows[-1]['raw_date']+=24
        self.raw['session/research-1375.jsonl']=b''.join((json.dumps(x)+'\n').encode() for x in rows)
        native=self.replay()
        try:self.assertEqual(native.speed_traces[4]['final_frame']['raw_date'],native.speed_traces[4]['pause_complete']['after_date']+24)
        finally:native.close()
    def test_under48_date_subgroup_cannot_pass_as_timer_guess(self):
        rows=[json.loads(line) for line in self.raw['session/research-1375.jsonl'].splitlines()]
        start=next(x['initial_raw_date'] for x in rows if x['event']=='lab_lease_armed')
        for row in rows:
            if row['event']=='research_frame' and row['raw_date']>start:row['raw_date']-=24
            if row['event']=='lab_native_record' and row.get('lease_pause'):
                row['record']['before_date']-=24
                if row['record']['after_date']:row['record']['after_date']-=24
        self.raw['session/research-1375.jsonl']=b''.join((json.dumps(x)+'\n').encode() for x in rows)
        with self.assertRaises(ValueError):self.replay()
    def test_entry_glue_replays_preflight_exit_inventory_and_native_sources(self):
        # This is an explicit glue test, not a claim that this four-request
        # fixture is a 36-row batch. The separate ledger suite tests all 36.
        f=self.fixture;prefix_scope=deepcopy(f.scope)
        from test_ledger import fixture as adapter_fixture
        plan=adapter_fixture.plan();plan.update(pid=f.b.PID,creation=f.b.CREATION,world_cookie=f.b.WORLD,window_thread=f.b.THREAD)
        scope=dict(plan=plan,manifest_sha256=f.b.MANIFEST_SHA,dll_sha256=f.b.DLL_SHA.upper(),fixture_profile_sha256=self.lab.FIXTURE_PROFILE_SHA256)
        root=f.root
        self.assertTrue(root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertFalse(root.resolve().is_relative_to(r.ROOT.resolve()))
        for extra in f.session.iterdir():
            if extra.name not in self.files:extra.unlink()
        files={n:f.b.SESSION+'/'+n for n in self.files};raw={files[n]:self.raw[self.files[n]] for n in files}
        pc=json.loads((f.root/prefix_scope['preflight_case']).read_bytes())
        for descriptor in pc['inputs'].values():raw[descriptor['path']]=(f.root/descriptor['path']).read_bytes()
        for name in ('preflight_case','preflight_summary'):raw[prefix_scope[name]]=(f.root/prefix_scope[name]).read_bytes()
        raw['scope.json']=json.dumps(scope).encode();raw['journal.jsonl']=b'{}\n';raw['summary.json']=b'{}'
        raw['exit.json']=(f.root/'exit.json').read_bytes()
        inputs={p:dict(bytes=len(v),sha256=r.ledger.digest(v)) for p,v in raw.items()}
        audit=dict(pid=f.b.PID,creation=f.b.CREATION,process_exit_filetime=json.loads(raw['exit.json'])['process_exit_filetime'],
                   complete_log=inputs[files['research-1375.jsonl']],session_files={n:inputs[p] for n,p in files.items()},stopped=True)
        raw['stopped.json']=json.dumps(audit).encode();inputs['stopped.json']=dict(bytes=len(raw['stopped.json']),sha256=r.ledger.digest(raw['stopped.json']))
        for name,value in raw.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
        case=dict(schema_version=1,purpose='v17_batch_stopped_case_r3',finalized=True,inputs=inputs,batch_scope='scope.json',
                  journal='journal.jsonl',summary='summary.json',exit='exit.json',stopped_audit='stopped.json',session_files=files,preflight_scope=prefix_scope)
        native=self.replay()
        try:
            expected=dict(next_sequence=5,receipt_sources=[dict(sequence=i,request=native.full['requests'][str(i)]) for i in range(2,5)])
        finally:native.close()
        with patch.object(r.ledger,'audit',return_value=expected) as ledger_call, patch.object(r,'dependencies',return_value=(self.adapter,self.lab,self.experiment,self.modules)):
            result=r.review(case,root)
        self.assertEqual(result['status'],'reviewed_stopped_batch');self.assertEqual(ledger_call.call_count,1)
        self.assertFalse(result['actual_completion_elapsed_verified']);self.assertFalse(result['individual_effect_verified'])

    def test_formal_origins_and_no_actual_process_calls(self):
        with patch.object(self.lab,'LiveLabProcess',side_effect=AssertionError('NO GAME')):
            native=self.replay();native.close()
        self.assertEqual(Path(self.lab.__file__).resolve(),r.ROOT/'work/native/lab_protocol_v17_1375.py')


if __name__=='__main__':unittest.main()
