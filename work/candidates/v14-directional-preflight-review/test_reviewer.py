"""Synthetic process/log/claims; actual frozen validators, never a live process."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import io

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from work.native import lab_protocol_v14_1375 as lab
from work import probe_diplomacy_current as probe

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module

review=load('v14_preflight_reviewer',HERE/'reviewer.py')
CANDIDATE_BINDING=dict(review.EXPECTED_SESSION)
# Only its established synthetic data factory is invoked, never old entrypoints.
fixtures=load('v13_preflight_synthetic_data',ROOT/'work/candidates/v13-host-review/test_candidate.py')


class ReviewTests(unittest.TestCase):
    def setUp(self):
        base=fixtures.CandidateTests();base.setUp();self.addCleanup(base.doCleanups)
        self.f=base.f
        # Run all inherited rule tests with the newly fixed session identity.
        binding=dict(review.EXPECTED_SESSION)
        replacements={(int,self.f.pid):binding['pid'],(str,self.f.creation):binding['creation'],
            (int,int(self.f.creation,16)):int(binding['creation'],16),
            (int,self.f.thread):binding['window_thread'],
            (str,self.f.live['world_cookie']):binding['world_cookie']}
        def rebind(value):
            if type(value) is dict:return {k:rebind(v) for k,v in value.items()}
            if type(value) is list:return [rebind(v) for v in value]
            return replacements.get((type(value),value),value)
        for name in ('metadata','events','live'):setattr(self.f,name,rebind(getattr(self.f,name)))
        self.f.fixture.f.snapshot=rebind(self.f.fixture.f.snapshot)
        self.f.pid=binding['pid'];self.f.creation=binding['creation'];self.f.thread=binding['window_thread']
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.session=self.root/'prefix';self.session.mkdir()
        self.f.metadata['purpose']=lab.PURPOSE
        self.events=deepcopy(self.f.events)
        for event in self.events:
            if event['event']=='research_frame':event['lease_deadline_uptime_ms']=0
        for name in ('session.json','install.claim'):(self.session/name).write_text(json.dumps(self.f.metadata))
        for phase,(_,claim,_) in lab.PHASES.items():(self.session/claim).write_bytes(lab.phase_wire(phase,self.f.metadata))
        self.write_events()
        self.build=json.loads((ROOT/review.BUILD).read_bytes())
        self.before=deepcopy(self.f.fixture.f.snapshot)
        self.before['captured_at_utc']='2026-10-08T23:00:01+00:00'
        self.before['capture_started_at_utc']='2026-10-08T23:00:00+00:00'
        self.before['source'].update(process_creation_filetime=int(self.f.creation,16),process_exit_filetime=0,
            access=['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'],held_identity_verified_before_and_after=True)
        self.before['state'].update(game_pointer=self.f.live['world_cookie'],memory_bytes_requested=5000)
        self.before['read_budget']=dict(per_read_max_bytes=probe.MAX_READ,total_max_bytes=probe.MAX_TOTAL_READ,
            country_slot_max=probe.MAX_SLOTS,diplomat_entry_max=probe.MAX_DIPLOMATS,bytes_requested=5044)
        self.before['offset_profile']=dict(database_pointer_rva=hex(probe.DATABASE_POINTER_RVA),game_pointer_rva=hex(probe.GAME_POINTER_RVA))
        self.before['identity_before_and_after']=[dict(self.f.live),dict(self.f.live)]
        self.after=deepcopy(self.before)
        self.after['capture_started_at_utc']='2026-10-08T23:01:00+00:00'
        self.after['captured_at_utc']='2026-10-08T23:01:01+00:00'
        self.loader=dict(purpose=lab.PURPOSE,pid=self.f.pid,creation=self.f.creation,dll_sha256=review.DLL_SHA.upper(),
            manifest_sha256=review.BUILD_SHA,live_observation=dict(self.f.live),plan_only=False,
            **{k:False for k in ('selftest_automatic','owned_peace_automatic','preview_automatic','command_automatic','submit_automatic','production_backend_registered')},
            installation=dict(pid=self.f.pid,dll=str(self.root/Path(review.BUILD).parent/lab.DLL_NAME),bridge_thread_exit_status='0x0',
                dll_unloaded=False,test_save_acknowledged=True,warnings=[],dll_module_base='0x30000000',bridge_rva='0x59c0',bridge_remote_address='0x300059c0'),
            fixture_disk_evidence=dict(pid=self.f.pid,creation=self.f.creation,profile_sha256=lab.FIXTURE_PROFILE_SHA256,
                fixture_definition_files_verified=True,installed_before_process_creation=True,engine_registration_verified=False))
        self.status=self.make_status()
        self.write_documents()
        self.enterContext(patch.object(lab,'LiveLabProcess',side_effect=AssertionError('Forbidden live process')))
        self.enterContext(patch.object(lab,'publish_research',side_effect=AssertionError('Forbidden publication')))
        # The actual 20/1/72/72 validators are NOT mocked. Only the build's
        # on-disk location is redirected for synthetic evidence in a temp root.
        self.enterContext(patch.object(review,'fixed_build',return_value=self.build))
        self.enterContext(patch.object(lab,'verify_build',return_value=(self.build,review.BUILD_SHA)))
        self.enterContext(patch.object(review,'EXPECTED_SESSION',dict(pid=self.f.pid,creation=self.f.creation,
            world_cookie=self.f.live['world_cookie'],raw_date=self.f.live['raw_date'],window_thread=self.f.thread)))

    def write_events(self):
        (self.session/'research-1375.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in self.events))
    def make_status(self):
        evidence=lab.read_evidence(self.session,self.f.metadata)
        return dict(purpose=lab.PURPOSE,protocol=lab.PROTOCOL,pid=self.f.pid,creation=self.f.creation,
            dll_sha256=review.DLL_SHA.upper(),manifest_sha256=review.BUILD_SHA,latest_frame=evidence['latest_frame'],
            phases=evidence['phases'],last_sequence=0,pending=False,lease_pending=False,log_sha256=evidence['log_sha256'],
            applied_verified=False,production_backend_registered=False,read_only=True)
    def write_documents(self):
        for name in ('before','after','loader','status'):(self.root/(name+'.json')).write_text(json.dumps(getattr(self,name)))
    def case(self):
        paths={name:self.session/name for name in review.FILES}|{name:self.root/(name+'.json') for name in ('before','after','loader','status')}
        inputs={}
        for name,path in paths.items():
            raw=path.read_bytes();inputs[name]=dict(path=path.relative_to(self.root).as_posix(),size_bytes=len(raw),sha256=review.sha(raw))
        return dict(schema_version=1,purpose='fixed_v14_preflight_case',pid=self.f.pid,creation=self.f.creation,
            world_cookie=self.f.live['world_cookie'],raw_date=self.f.live['raw_date'],window_thread=self.f.thread,
            build_manifest_sha256=review.BUILD_SHA,dll_sha256=review.DLL_SHA,
            log_prefix_sha256=inputs['research-1375.jsonl']['sha256'],log_prefix_bytes=inputs['research-1375.jsonl']['size_bytes'],
            reviewer_sha256=review.sha(review.bounded(Path(review.__file__))),inputs=inputs)
    def run_review(self):return review.review(self.case(),root=self.root)

    def test_candidate_is_bound_to_explicit_directional_session(self):
        self.assertEqual(CANDIDATE_BINDING,dict(pid=18356,creation='01dd56aa6f724ea8',
            world_cookie='0x221c8dac040',raw_date=56456976,window_thread=47264))
        result=self.run_review()
        self.assertEqual(result['status'],'passed')
        self.assertEqual(self.case()['pid'],18356)
        self.assertEqual(self.case()['creation'],'01dd56aa6f724ea8')
        self.assertEqual(self.case()['window_thread'],47264)

    def test_full_actual_validator_pipeline_with_synthetic_inputs(self):
        result=self.run_review()
        self.assertEqual(result['status'],'passed');self.assertEqual(result['phase_case_counts'],dict(lifecycle=20,owned_peace=1,preview=72,command=72))
        self.assertTrue(result['status_exact_prefix_verified'])
        for name in ('execution_verified','war_identity_verified','parameterized_offer_verified','white_peace_verified',
                     'heap_release_independently_observed','whole_world_unchanged','world_generation_verified','production_backend_registered'):
            self.assertIs(result[name],False)
        self.assertEqual(result['phases']['owned_peace']['session']['core_record_count'],9)

    def test_core_wrapper_and_following_frame_all_required(self):
        original=deepcopy(self.events)
        for key in ('core','wrapper','health'):
            self.events=deepcopy(original)
            if key=='core':
                e=next(e for e in self.events if e['event']=='owned_peace_core_record');e['core']['freeze_session']=1
            elif key=='wrapper':
                e=next(e for e in self.events if e['event']=='owned_peace_selftest_complete');e['post_guard_ok']=False
            else:
                i=next(i for i,e in enumerate(self.events) if e['event']=='owned_peace_selftest_complete');self.events.pop(i+1)
            self.write_events()
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_review()

    def test_owned_scalar_types_and_no_overclaims(self):
        original=deepcopy(self.events)
        for key,value in (('token',True),('exception',False),('distinct_owned_ranges',True),('submitted',None),('execution_verified',True)):
            self.events=deepcopy(original);e=next(e for e in self.events if e['event']=='owned_peace_core_record');e['core'][key]=value
            self.write_events()
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_review()

    def test_appended_duplicate_or_actual_send_rejected_before_phase_cache(self):
        original=deepcopy(self.events)
        for event in (next(e for e in original if e['event']=='pair_lifecycle'),dict(event='pair_submit_begin',submitted=True),
                      dict(event='owned_peace_selftest_begin'),dict(event='lab_native_record',submitted=False)):
            self.events=deepcopy(original);self.events.insert(-1,deepcopy(event));self.write_events()
            with self.subTest(event=event['event']),self.assertRaises(ValueError):self.run_review()

    def test_status_hash_bytes_frame_and_readonly_binding(self):
        original=deepcopy(self.status)
        changes=[('log_sha256','0'*64),('read_only',False),('last_sequence',True),('pending',True),('dll_sha256','0'*64),('creation',int(self.f.creation,16))]
        for key,value in changes:
            self.status=deepcopy(original);self.status[key]=value;self.write_documents()
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_review()
        self.status=deepcopy(original);self.status['latest_frame']['frames']+=1;self.write_documents()
        with self.assertRaises(ValueError):self.run_review()

    def test_exact_native_claims_not_host_intents(self):
        for phase in lab.PHASES:
            path=self.session/lab.PHASES[phase][1];original=path.read_bytes()
            path.write_bytes(original+b' ')
            with self.subTest(phase=phase),self.assertRaises(ValueError):self.run_review()
            path.write_bytes(original)
        path=self.session/lab.PHASES['owned_peace'][1]
        path.write_bytes(lab.phase_wire('owned_peace',self.f.metadata|{'pid':self.f.pid+1}))
        with self.assertRaises(ValueError):self.run_review()

    def test_status_frame_requires_type_exact_json_not_python_equality(self):
        original=deepcopy(self.status)
        for key,value in (('frames',float(original['latest_frame']['frames'])),('send_enabled',0),('world_ready',1),
                          ('thread',float(self.f.thread)),('last_sequence',False),('raw_date',float(self.f.live['raw_date']))):
            self.status=deepcopy(original);self.status['latest_frame'][key]=value;self.write_documents()
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_review()

    def test_loader_requires_exact_pinned_bridge_export(self):
        original=deepcopy(self.loader)
        for value in ('0x1000','0x59c1',True,False,0x59c0,float(0x59c0),'0x059c0','0X59C0','true','false','22976.0','0x59c0.0','22976'):
            self.loader=deepcopy(original);self.loader['installation']['bridge_rva']=value
            # Wrong string RVAs deliberately have self-consistent base+offset.
            if value in ('0x1000','0x59c1','0x059c0','0X59C0','22976'):
                self.loader['installation']['bridge_remote_address']=hex(0x30000000+int(value,16))
            self.write_documents()
            with self.subTest(value=value),self.assertRaises(ValueError):self.run_review()
        self.loader=deepcopy(original);self.loader['installation']['bridge_remote_address']='0x30001000';self.write_documents()
        with self.assertRaises(ValueError):self.run_review()

    def test_every_postproof_tail_frame_has_strict_scalar_types(self):
        original=deepcopy(self.events)
        integer_fields=('pid','thread','uptime_ms','frames','raw_date','native_speed_index','last_sequence','lease_deadline_uptime_ms')
        bool_fields=('thread_changed','world_ready','world_changed','session_frozen','paused','lifecycle_passed','owned_peace_tested',
                     'owned_peace_passed','preview_passed','command_passed','mailbox_ready','running_speed_enabled','lease_active','send_enabled')
        for key in (*integer_fields,*bool_fields):
            for kind in (('float','bool') if key in integer_fields else ('int','float')):
                self.events=deepcopy(original);tail=deepcopy(original[-1]);tail['frames']+=1;tail['uptime_ms']+=1
                value=tail[key]
                tail[key]=float(value) if kind=='float' else (bool(value) if kind=='bool' else int(value))
                self.events.append(tail);self.write_events()
                # Keep status and hash perfectly synchronized with the bad raw
                # frame: rejection must come from full-prefix typing, not status.
                self.status['latest_frame']=deepcopy(tail)
                self.status['log_sha256']=review.sha((self.session/'research-1375.jsonl').read_bytes());self.write_documents()
                with self.subTest(key=key,kind=kind),self.assertRaises(ValueError):self.run_review()

    def test_tail_frame_unknown_missing_or_contradictory_readiness_rejected(self):
        original=deepcopy(self.events)
        for mutate in (lambda e:e.update(extra=0),lambda e:e.pop('lease_deadline_uptime_ms'),
                       lambda e:e.update(owned_peace_passed=False),lambda e:e.update(mailbox_ready=False),
                       lambda e:e.update(world_cookie='0x21000000'),lambda e:e.update(raw_date=e['raw_date']+1)):
            self.events=deepcopy(original);tail=deepcopy(original[-1]);tail['frames']+=1;tail['uptime_ms']+=1;mutate(tail)
            self.events.append(tail);self.write_events();self.status['latest_frame']=deepcopy(tail)
            self.status['log_sha256']=review.sha((self.session/'research-1375.jsonl').read_bytes());self.write_documents()
            with self.assertRaises(ValueError):self.run_review()

    def test_full_held_ro_envelope_missing_malformed_or_numeric_creation(self):
        original=deepcopy(self.before)
        for mutate in (lambda r:r['source'].pop('held_identity_verified_before_and_after'),
                       lambda r:r['source'].update(process_creation_filetime=float(int(self.f.creation,16))),
                       lambda r:r['source'].update(process_exit_filetime=False),
                       lambda r:r['source']['access'].append('PROCESS_VM_WRITE'),
                       lambda r:r['identity_before_and_after'][1].update(creation=True),
                       lambda r:r['identity_before_and_after'][1].update(world_cookie='0x21000000'),
                       lambda r:r['state'].update(game_pointer='0x21000000'),
                       lambda r:r['read_budget'].update(bytes_requested=True),
                       lambda r:r.pop('offset_profile')):
            self.before=deepcopy(original);mutate(self.before);self.write_documents()
            with self.assertRaises((ValueError,KeyError)):self.run_review()

    def test_snapshot_selected_fields_changed_or_capture_overlap(self):
        original=deepcopy(self.after)
        for mutate in (lambda r:r['state']['relation_cooldown'].update(threshold_raw=43808761),
                       lambda r:r['state']['actor_diplomats']['entries'][0].update(state_raw_18=1,state_zero_available_candidate=False),
                       lambda r:r.update(capture_started_at_utc=self.before['captured_at_utc'])):
            self.after=deepcopy(original);mutate(self.after);self.write_documents()
            with self.assertRaises(ValueError):self.run_review()

    def test_case_full_binding_rejects_pid_world_thread_build_and_prefix_forgery(self):
        for key,value in (('pid',True),('world_cookie','0x21000000'),('raw_date',True),('window_thread',self.f.thread+1),
                          ('build_manifest_sha256','0'*64),('dll_sha256','0'*64),('log_prefix_bytes',True),('log_prefix_sha256','0'*64),
                          ('creation',float(2**56))):
            case=self.case();case[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):review.review(case,root=self.root)

    def test_loader_plan_failure_and_wrong_creation_or_path_rejected(self):
        original=deepcopy(self.loader)
        for mutate in (lambda r:r.update(plan_only=True),lambda r:r.update(creation=True),
                       lambda r:r['installation'].update(bridge_thread_exit_status='0x15'),
                       lambda r:r['installation'].update(dll='C:/wrong.dll'),
                       lambda r:r['fixture_disk_evidence'].update(engine_registration_verified=True),
                       lambda r:r.update(owned_peace_automatic=True)):
            self.loader=deepcopy(original);mutate(self.loader);self.write_documents()
            with self.assertRaises(ValueError):self.run_review()

    def test_duplicate_paths_traversal_oversize_and_changed_evidence(self):
        original=self.case()
        for mutate in (lambda c:c['inputs']['before'].update(path='../escape.json'),
                       lambda c:c['inputs']['before'].update(path=c['inputs']['after']['path']),
                       lambda c:c['inputs']['before'].update(size_bytes=review.MAX_FILE+1),
                       lambda c:c['inputs']['before'].update(size_bytes=True)):
            case=deepcopy(original);mutate(case)
            with self.assertRaises(ValueError):review.review(case,root=self.root)
        (self.root/'before.json').write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError,'Input changed'):review.review(original,root=self.root)

    def test_create_new_never_overwrites_a_result(self):
        out=self.root/'result.json';review.write_new(out,{'test':1})
        with self.assertRaises(OSError):review.write_new(out,{'test':2})
        self.assertEqual(json.loads(out.read_bytes()),{'test':1})

    def test_fixed_parameters_and_bool_native_legality(self):
        original=deepcopy(self.events)
        for field in ('fixed_subsidy_amount_milli','fixed_subsidy_duration_years','fixed_gift_amount_milli',
                      'fixed_transfer_fraction_milli','fixed_insult_index','allowed'):
            self.events=deepcopy(original)
            e=next(e for e in self.events if e['event']=='pair_preview_case')
            e[field]=1 if field=='allowed' else e[field]+1;self.write_events()
            with self.subTest(field=field),self.assertRaises(ValueError):self.run_review()


def main():
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
    print(json.dumps(dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        passed=result.wasSuccessful(),synthetic_game_evidence_only=True,game_accessed=False,details=stream.getvalue())))
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
