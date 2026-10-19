"""Host boundary tests. Pure files/fakes; no Windows, REA, Frida or game."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tested_entry_host',HERE/'capture_once.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def envelope():
    script_id = '33333333-4444-4555-8666-777777777777'
    normalized = dict(session_id='11111111-2222-4333-8444-555555555555',device_id='local',state='running',
        target='eu4.exe (pid 80340)',pid=80340,mode='attach',
        scripts=[dict(script_id=script_id,name='rea-'+script_id)],
        messages=[dict(script_id=script_id,type='send',payload={'fixture':'owned only'})],
        messages_truncated=False,source_kind='file',source_path='C:\\owned\\rendered.js',
        source_sha256='a'*64,cleanup_error=None)
    evidence = dict(subject=None,provider=dict(id='frida',name='Frida',version=None),analysis_profile=None,
        predicate_type='rea.frida.instrumentation-observation',operation='instrument_with_frida',
        parameters=dict(session_id=normalized['session_id'],device_id='local',mode='attach',pid=80340),
        raw_result=None,normalized_result=normalized,confidence='observed',authority='external-service',
        environment=None,limitations=['Artifact identity is unavailable for this observation.',
            'The target operating system and architecture were not reported by this observation.'],
        relationship_coverage=None,locations=[],evidence_links=[])
    evidence['evidence_id'] = digest(evidence)
    return dict(ok=True,data=dict(evidence=evidence,cleanup_error=None),
        meta=dict(command='instrument-with-frida',duration='1500ms'))


def digest(evidence):
    semantic = {k:v for k,v in evidence.items() if k not in ('evidence_id','relationship_coverage')}
    return 'ev_'+hashlib.sha256(json.dumps(semantic,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def extract(document, resign=True):
    if resign:
        document['data']['evidence']['evidence_id'] = digest(document['data']['evidence'])
    return host.extract_evidence(json.dumps(document).encode(),{'pid':80340},'C:\\owned\\rendered.js','a'*64)


GOOD_JOB = dict(error=None,exit_code=0,direct_child_collected=True,job_active_processes_final=0,
    existing_target_game_assigned_to_job=False,target_cleanup_proven_by_job=False)


class HostBoundaries(unittest.TestCase):
    def test_real_shape_before_close_is_running(self):
        evidence,payload = extract(envelope())
        self.assertEqual(payload,{'fixture':'owned only'})
        self.assertTrue(evidence['evidence_id'].startswith('ev_'))

    def test_semantic_id_and_null_relationship_projection(self):
        value = envelope()
        value['data']['evidence']['evidence_id'] = 'ev_'+'0'*64
        with self.assertRaisesRegex(ValueError,'semantic identifier'):
            extract(value,False)

    def test_normalized_bindings_and_strict_types(self):
        edits = [('pid',80341),('pid',80340.0),('device_id','socket'),('mode','spawn'),
            ('state','detached'),('source_kind','inline'),('source_path','C:\\other.js'),
            ('source_sha256','b'*64),('messages_truncated',True),('messages_truncated',0),
            ('cleanup_error','failed')]
        for key,wrong in edits:
            with self.subTest(field=key,value=wrong):
                value = envelope()
                value['data']['evidence']['normalized_result'][key] = wrong
                with self.assertRaises(ValueError):
                    extract(value)

    def test_parameters_cross_binding(self):
        for key,wrong in [('pid',80341),('pid',True),('session_id','other'),('device_id','other'),('mode','spawn')]:
            with self.subTest(field=key):
                value = envelope()
                value['data']['evidence']['parameters'][key] = wrong
                with self.assertRaises(ValueError):
                    extract(value)

    def test_source_hash_applies_to_full_rendered_text(self):
        initial = {'source_pins':{host.REL+'/entry_observer.js':host.pin(HERE/'entry_observer.js')}}
        one = host.rendered_script({'observer_nonce':'1'*32},initial)
        two = host.rendered_script({'observer_nonce':'2'*32},initial)
        self.assertNotEqual(hashlib.sha256(one).digest(),hashlib.sha256(two).digest())
        self.assertTrue(one.endswith((HERE/'entry_observer.js').read_bytes()))

    def test_no_error_log_binary_extra_or_truncation(self):
        for mode in ('error','log','binary','extra','missing','wrong_script','wrong_name','extra_key'):
            with self.subTest(mode=mode):
                value = envelope()
                r = value['data']['evidence']['normalized_result']
                if mode in ('error','log'):
                    r['messages'][0]['type'] = mode
                elif mode == 'binary':
                    r['messages'][0]['data'] = '00'
                elif mode == 'extra':
                    r['messages'].append(copy.deepcopy(r['messages'][0]))
                elif mode == 'missing':
                    r['messages'] = []
                elif mode == 'wrong_script':
                    r['messages'][0]['script_id'] = 'other'
                elif mode == 'wrong_name':
                    r['scripts'][0]['name'] = 'other'
                else:
                    r['scripts'][0]['extra'] = True
                with self.assertRaises(ValueError):
                    extract(value)

    def test_provider_and_unavailable_subject_profile(self):
        for key,wrong in [('operation','load_frida_script'),('authority','analyst-inference'),
                ('confidence','inferred'),('provider',{'id':'other','name':'Frida','version':None}),
                ('subject',{}),('environment',{}),('raw_result',{}),('relationship_coverage',{})]:
            with self.subTest(field=key):
                value = envelope()
                value['data']['evidence'][key] = wrong
                with self.assertRaises(ValueError):
                    extract(value)

    def test_cli_error_cleanup_and_output_fields(self):
        for field in ('ok','cleanup','command','extra'):
            with self.subTest(field=field):
                value = envelope()
                if field == 'ok':
                    value['ok'] = 1
                elif field == 'cleanup':
                    value['data']['cleanup_error'] = 'failed'
                elif field == 'command':
                    value['meta']['command'] = 'other'
                else:
                    value['data']['extra'] = True
                with self.assertRaises(ValueError):
                    extract(value)

    def test_duplicate_keys_nonfinite_unicode_float_depth_and_size(self):
        for raw in (b'{"ok":true,"ok":false}',b'{"x":NaN}',b'{"x":1.0}',b'{"x":"\\u4e2d"}',
                    b'['*34+b'0'+b']'*34,b' '* (2*1024*1024+1),b'{"x":9007199254740992}'):
            with self.subTest(raw=raw[:60]):
                with self.assertRaises(ValueError):
                    host.strict_json(raw)

    def test_job_receipt_cannot_claim_target_cleanup(self):
        host.accepted_job(GOOD_JOB)
        for key,wrong in [('exit_code',False),('exit_code',1),('error',{}),('direct_child_collected',False),
                ('job_active_processes_final',False),('job_active_processes_final',1),
                ('existing_target_game_assigned_to_job',True),('target_cleanup_proven_by_job',True)]:
            with self.subTest(field=key):
                value = dict(GOOD_JOB)
                value[key] = wrong
                with self.assertRaises(ValueError):
                    host.accepted_job(value)

    def test_unsealed_manifest_refuses_before_import_or_process(self):
        with tempfile.TemporaryDirectory(prefix='eu4_host_offline_') as tmp:
            path = Path(tmp)/'manifest.json'
            path.write_text(json.dumps(dict(schema='EU4-FRIDA-ENTRY-HOST-MANIFEST/1',sealed=False,
                game_sha256=host.GAME_SHA,fixed_pid=host.PID,fixed_creation=host.CREATION)))
            with patch.object(host,'load_local',side_effect=AssertionError('import forbidden')):
                with self.assertRaisesRegex(ValueError,'Reviewed fixed'):
                    host.verify_manifest(path)

    def test_exclusive_claim_survives_failure_and_blocks_second_attempt(self):
        with tempfile.TemporaryDirectory(prefix='eu4_host_offline_') as tmp:
            initial = {'manifest_sha256':'1'*64}
            with patch.object(host,'OUT',Path(tmp)),patch.object(host,'verify_manifest',return_value=initial),\
                    patch.object(host,'load_local',side_effect=ValueError('fixture import refusal')) as loader:
                result = host.capture(initial)
                self.assertEqual(result['status'],'unknown')
                self.assertFalse(result['attach_may_have_been_attempted'])
                self.assertFalse(result['native_ready'])
                self.assertTrue((Path(tmp)/'claim.json').exists())
                with self.assertRaises(FileExistsError):
                    host.capture(initial)
                self.assertEqual(loader.call_count,1)

    def test_path_traversal_refuses(self):
        for value in ('../outside.py','C:/outside.py','tools\\x.py','/outside.py'):
            with self.subTest(path=value):
                with self.assertRaises(ValueError):
                    host.local_path(value)

    def test_attach_failure_still_checks_prefix_before_changing_world(self):
        class Held:
            def identity_check(self):
                pass
        class Capture:
            base, held = 0x7FF7034B0000, Held()
            modules, initial_pins = [], {}
            closed = False
            def __enter__(self):
                return self
            def __exit__(self,*_):
                self.closed = True
        class Reader:
            def __init__(self,_):
                pass
            def read(self,address,size):
                self_test.assertEqual((address,size),(cap.base+host.ENTRY_RVA,32))
                return host.PREFIX
        self_test, cap = self,Capture()
        backend = types.SimpleNamespace(manifest={'dll':{'sha256':'1'*64}},manifest_sha='2'*64)
        observer = types.SimpleNamespace(TagCommandBackend=lambda:backend,RuntimeCapture=lambda *_:cap,
            BudgetReader=Reader,HeldRPMPort=lambda held:held,pins=lambda:{})
        jobs = types.SimpleNamespace(run_cli_tree=lambda *_:dict(GOOD_JOB,error={'message':'fixture failure'}))
        parser = types.SimpleNamespace(evaluate=lambda *_:self.fail('Failed CLI must not reach parser'))
        def loader(name,_):
            return parser if name.endswith('entry_observation_parser.py') else jobs if name.endswith('job_tree.py') else observer
        with tempfile.TemporaryDirectory(prefix='eu4_host_offline_') as tmp:
            initial = {'manifest_sha256':'1'*64}
            with patch.object(host,'OUT',Path(tmp)),patch.object(host,'verify_manifest',return_value=initial),\
                    patch.object(host,'load_local',side_effect=loader),patch.object(host,'rendered_script',return_value=b'fixture'),\
                    patch.object(host,'registered_argv',return_value=['fixture']),\
                    patch.object(host,'host_sample',side_effect=[{'fixture':'before'},ValueError('world changed')]):
                result = host.capture(initial)
                self.assertEqual(result['status'],'unknown')
                self.assertTrue(result['attach_may_have_been_attempted'])
                self.assertTrue(result['code_restore_verified'])
                self.assertEqual(result['post_prefix32_hex'],host.PREFIX.hex())
                self.assertFalse(result['selected_cleanup_checks_passed'])
                self.assertFalse(result['native_ready'])
                self.assertTrue(cap.closed)
                self.assertEqual([e['stage'] for e in result['errors']],['instrument','postcheck'])

    def test_exact_metadata_target_uuid_and_limitations(self):
        for mode in ('meta_missing','meta_extra','meta_bool','meta_unit','target_name','target_pid',
                     'session_not_uuid','script_not_uuid','missing_limitation'):
            with self.subTest(mode=mode):
                value = envelope()
                e = value['data']['evidence'];r = e['normalized_result']
                if mode == 'meta_missing':
                    del value['meta']['duration']
                elif mode == 'meta_extra':
                    value['meta']['extra'] = True
                elif mode == 'meta_bool':
                    value['meta']['duration'] = False
                elif mode == 'meta_unit':
                    value['meta']['duration'] = '1.5s'
                elif mode == 'target_name':
                    r['target'] = 'other.exe (pid 80340)'
                elif mode == 'target_pid':
                    r['target'] = 'eu4.exe (pid 1)'
                elif mode == 'session_not_uuid':
                    r['session_id'] = e['parameters']['session_id'] = 'fixture'
                elif mode == 'script_not_uuid':
                    r['scripts'][0] = dict(script_id='fixture',name='rea-fixture')
                    r['messages'][0]['script_id'] = 'fixture'
                else:
                    e['limitations'] = e['limitations'][1:]
                with self.assertRaises(ValueError):
                    extract(value)

    def test_non_utf8_or_BOM_is_rejected(self):
        text = '{"ok":true}'
        for raw in (text.encode('utf-16'),text.encode('utf-32'),b'\xef\xbb\xbf'+text.encode()):
            with self.subTest(prefix=raw[:8]):
                with self.assertRaises(ValueError):
                    host.strict_json(raw)
        self.assertEqual(host.strict_json(text.encode()),{'ok':True})
        self.assertEqual(host.strict_json(b'{"timing":1.5}',evidence_scalars=False),{'timing':1.5})

    def test_held_close_failure_cannot_leave_positive_result(self):
        cap = types.SimpleNamespace(base=0x7FF7034B0000,modules=[],initial_pins={},
            held=types.SimpleNamespace(identity_check=lambda:None))
        class Context:
            def __enter__(self):
                return cap
            def __exit__(self,*_):
                raise OSError('fixture held close failed')
        class Reader:
            def __init__(self,_):
                pass
            def read(self,_,size):
                return host.PREFIX
        backend = types.SimpleNamespace(manifest={'dll':{'sha256':'1'*64}},manifest_sha='2'*64)
        observer = types.SimpleNamespace(TagCommandBackend=lambda:backend,RuntimeCapture=lambda *_:Context(),
            BudgetReader=Reader,HeldRPMPort=lambda held:held,pins=lambda:{})
        def run_cli(_,__,out,err):
            Path(out).write_bytes(b'fixture')
            Path(err).write_bytes(b'')
            return dict(GOOD_JOB)
        jobs = types.SimpleNamespace(run_cli_tree=run_cli)
        parser = types.SimpleNamespace(evaluate=lambda *_:{'status':'structural_match'})
        def loader(name,_):
            return parser if name.endswith('entry_observation_parser.py') else jobs if name.endswith('job_tree.py') else observer
        with tempfile.TemporaryDirectory(prefix='eu4_host_offline_') as tmp:
            initial = {'manifest_sha256':'1'*64}
            with patch.object(host,'OUT',Path(tmp)),patch.object(host,'verify_manifest',return_value=initial),\
                    patch.object(host,'load_local',side_effect=loader),patch.object(host,'rendered_script',return_value=b'fixture'),\
                    patch.object(host,'registered_argv',return_value=['fixture']),patch.object(host,'host_sample',return_value={'fixture':'same'}),\
                    patch.object(host,'extract_evidence',return_value=({'evidence_id':'fixture'}, {'temporary_code_hook':True})):
                result = host.capture(initial)
                self.assertEqual(result['status'],'unknown')
                self.assertTrue(result['code_restore_verified'])
                self.assertFalse(result['selected_cleanup_checks_passed'])
                self.assertFalse(result['native_callback_observed'])
                self.assertFalse(result['native_ready'])
                self.assertEqual(result['errors'][-1]['stage'],'host')
                self.assertTrue((Path(tmp)/'claim.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
