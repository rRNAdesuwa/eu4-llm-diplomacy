"""Offline CLI boundaries; temporary manifest and mock observer, never EU4."""
import copy
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate_relation_cli',HERE/'relation_request_cli.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def fixture_graph():
    result={name:c.file_pin(c.source_path(name)) for name in c.REQUIRED_FILES}
    for name in c.FROZEN_MANIFESTS:
        result[name]=c.file_pin(c.source_path(name))
        manifest=c.decode(c.bounded_read(c.source_path(name),1024*1024))
        result.update(manifest['source_pins'])
        if name==c.NATIVE:
            result[str(PurePosixPath(name).parent/manifest['DLL'])]=manifest['dll']
    return result


class CLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph=fixture_graph()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.manifest_path=self.path/'controlled-manifest.json'
        self.manifest=dict(schema='EU4-RELATION-REQUEST-CLI-MANIFEST/1',sealed=True,
            game_sha256=c.GAME_SHA,native_manifest_sha256=c.NATIVE_SHA,
            candidate_module_sha256=self.graph[c.MODULE]['sha256'],source_pins=copy.deepcopy(self.graph))
        self.write_manifest()
        self.identity=dict(pid=77,creation='0000000000000001',session='1'*32,
            dll_sha256='2'*64,manifest_sha256=c.NATIVE_SHA)
        self.session=self.path/'original-session.json'
        self.session.write_text(json.dumps(dict(identity=self.identity,experimental=True)))
        self.calls=[];self.loads=[];self.installs=[];self.prepares=[];self.after=None;self.fake_time=0;self.sleeps=[]
        self.values=[self.value()]
        owner=self
        class Observer:
            def __init__(self,identity,**kwargs):
                self.identity=identity;self.backend=object();owner.options=kwargs
            def observe(self,request_id):
                owner.calls.append(request_id)
                value=copy.deepcopy(owner.values[min(len(owner.calls)-1,len(owner.values)-1)])
                if owner.after:owner.after()
                return value
            def prepare(self,command):
                owner.prepares.append(command)
                if owner.after:owner.after()
                return dict(request_id=command['request_id'],baseline='offline-baseline-only',requests_published=0)
        def installed(backend,identity,ready=False):
            self.assertEqual(identity,self.identity)
            self.installs.append(ready)
            return {'installation_record_verified':True},None
        self.module=types.SimpleNamespace(source_pins=lambda:{c.MODULE:self.graph[c.MODULE]},
            candidate_catalog=lambda:{'profiles':[{'action':action} for action in
                ('offer_alliance','royal_marriage','guarantee','knowledge_sharing')],'native_calls':0},
            validate_identity=lambda identity:identity,
            RelationRequestObserver=Observer,installed_session=installed)

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest),encoding='utf-8')

    def value(self,observed=False):
        return dict(request_id='original-1',identity=copy.deepcopy(self.identity),
            command=dict(request_id='original-1',action='offer_alliance',actor='FRA',target='SCO'),
            transport_state='dispatched',request_state='unknown',completion_state='selected_effect_observed' if observed else 'evidence_insufficient',
            effect=dict(status='observed' if observed else 'unknown',selected_effect_verified=observed,completion_stage='selected_indexed_relation_observed'),
            relation=None,native_calls=0,requests_published=0,automatic_command_retry=False)

    def waiting(self):
        value=self.value();value['command']['action']='ask_for_march';value['request_state']='waiting_for_recipient'
        actor=dict(tag='FRA',handle='0x100000100415246')
        recipient=dict(tag='SCO',handle='0x1000002004f4353')
        row=dict(state_raw=0,state_label='pending_observed',native_request_id=19,token=0x3021,value_raw=1,
            actor_handle=actor['handle'],original_actor_handle=actor['handle'],recipient_handle=recipient['handle'])
        value['reply']=dict(status='sampled_equal',request_state='waiting_for_recipient',native_request_id=19,
            selected=dict(identity=self.identity,actor=actor,recipient=recipient,
                pending=dict(count=1,iteration=0,selected_matches=[row])))
        return value

    def loader(self,initial):
        self.loads.append(initial)
        return self.module

    def sleep(self,seconds):
        self.sleeps.append(seconds);self.fake_time+=seconds

    def run_cli(self,operation='status',*extra,session=True,manifest=None,loader=None):
        args=(['--session-file',str(self.session)] if session else [])+[operation]
        if operation in ('status','watch'):args+=['--request-id','original-1']
        args+=list(extra)
        output=io.StringIO()
        code=c.main(args,_manifest=manifest or self.manifest_path,_loader=loader or self.loader,
            _clock=lambda:self.fake_time,_sleep=self.sleep,_output=output)
        return code,[json.loads(line) for line in output.getvalue().splitlines()]

    def test_absent_manifest_rejects_before_candidate_import(self):
        code,rows=self.run_cli(manifest=self.path/'missing.json')
        self.assertEqual(code,2);self.assertEqual(self.loads,[]);self.assertEqual(self.calls,[])
        self.assertFalse(rows[-1]['selected_effect_verified'])

    def test_unsealed_manifest_rejects_before_import(self):
        self.manifest['sealed']=False;self.write_manifest()
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_cli_self_pin_failure_rejects_before_import(self):
        self.manifest['source_pins'][c.RELATIVE+'/relation_request_cli.py']['sha256']='0'*64;self.write_manifest()
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_module_pin_failure_rejects_before_import(self):
        self.manifest['source_pins'][c.MODULE]['sha256']='0'*64;self.write_manifest()
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_module_bytes_changed_between_guard_and_compile_rejected(self):
        initial=c.verify_manifest(self.manifest_path)
        real_read=c.bounded_read
        def read(path,maximum):
            if Path(path)==c.source_path(c.MODULE):return b'raise RuntimeError("must not execute")'
            return real_read(path,maximum)
        with patch.object(c,'bounded_read',side_effect=read),self.assertRaisesRegex(ValueError,'immediately before import'):
            c.load_candidate(initial)

    def test_real_candidate_catalog_is_file_only_and_has_eighteen_profiles(self):
        code,rows=self.run_cli('catalog',session=False,loader=c.load_candidate)
        self.assertEqual(code,0)
        self.assertEqual(len(rows[-1]['catalog']['profiles']),18)
        self.assertFalse(rows[-1]['selected_effect_verified'])
        self.assertEqual(self.calls,[])

    def test_omitted_frozen_dependency_rejects_before_import(self):
        del self.manifest['source_pins']['bridge/tag_command_audit.py'];self.write_manifest()
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_dll_omitted_rejects_before_import(self):
        name=next(name for name in self.manifest['source_pins'] if name.endswith('.dll'))
        del self.manifest['source_pins'][name];self.write_manifest()
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_native_manifest_replacement_rejects_before_import(self):
        self.manifest['native_manifest_sha256']='0'*64;self.write_manifest()
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_source_paths_cannot_escape_project(self):
        for name in ('../bad','C:/bad','/bad','bridge\\tag_command_backend.py','./bridge/tag_command_backend.py'):
            with self.subTest(name=name),self.assertRaises(ValueError):c.source_path(name)

    def test_boolean_length_and_duplicate_manifest_json_rejected(self):
        self.manifest['source_pins'][c.MODULE]['bytes']=True;self.write_manifest()
        self.assertEqual(self.run_cli()[0],2)
        self.manifest_path.write_text('{"sealed":true,"sealed":true}')
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.loads,[])

    def test_source_and_response_bounds(self):
        path=self.path/'large';path.write_bytes(b'12345')
        with self.assertRaises(ValueError):c.file_pin(path,4)
        with self.assertRaises(ValueError):c.bounded_read(path,4)
        with self.assertRaises(ValueError):c.emit({'large':'x'*(2*1024*1024)},io.StringIO())

    def test_post_import_source_guard_precedes_observer_construction(self):
        def loader(initial):
            self.manifest['sealed']=False;self.write_manifest()
            return self.module
        code,rows=self.run_cli(loader=loader)
        self.assertEqual(code,2);self.assertEqual(self.installs,[]);self.assertEqual(self.calls,[])

    def test_lower_module_omitted_pin_is_rejected_before_observation(self):
        self.module.source_pins=lambda:{'unlisted.py':{'bytes':1,'sha256':'0'*64}}
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.calls,[])

    def test_check_is_file_only_success_not_effect(self):
        code,rows=self.run_cli('check',session=False)
        self.assertEqual(code,0);self.assertEqual(self.loads,[]);self.assertEqual(self.calls,[])
        self.assertEqual(rows[-1]['operation'],'check');self.assertFalse(rows[-1]['selected_effect_verified'])
        self.assertEqual(rows[-1]['requests_published'],0)

    def test_catalog_does_not_construct_observer_or_session(self):
        code,rows=self.run_cli('catalog',session=False)
        self.assertEqual(code,0);self.assertEqual(self.installs,[]);self.assertEqual(self.calls,[])
        self.assertFalse(rows[-1]['selected_effect_verified'])

    def test_catalog_post_guard_discards_result_after_source_change(self):
        def catalog():
            self.manifest['sealed']=False;self.write_manifest()
            return {'profiles':[]}
        self.module.candidate_catalog=catalog
        code,rows=self.run_cli('catalog',session=False)
        self.assertEqual(code,2);self.assertNotIn('catalog',rows[-1])

    def test_prepare_is_baseline_only_no_legacy_parameter(self):
        code,rows=self.run_cli('prepare','--request-id','fresh-local-baseline','--action','guarantee','--actor','FRA','--target','SCO')
        self.assertEqual(code,0);self.assertEqual(self.installs,[True]);self.assertEqual(self.calls,[])
        self.assertEqual(self.prepares,[dict(request_id='fresh-local-baseline',action='guarantee',actor='FRA',target='SCO')])
        self.assertEqual(rows[-1]['operation'],'prepare');self.assertFalse(rows[-1]['selected_effect_verified'])

    def test_prepare_rejects_unsupported_profile_without_capture(self):
        code,rows=self.run_cli('prepare','--request-id','fresh-local-baseline','--action','unsupported_action','--actor','FRA','--target','SCO')
        self.assertEqual(code,2);self.assertEqual(self.prepares,[])

    def test_status_requires_session_and_original_request_id(self):
        code,_=self.run_cli(session=False)
        self.assertEqual(code,2);self.assertEqual(self.loads,[])
        with self.assertRaises(SystemExit):c.parser().parse_args(['status'])

    def test_current_nonce_marker_cannot_be_used_as_installed_session(self):
        self.session.write_text(json.dumps(dict(identity=self.identity,native_session_installed=False)))
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.installs,[]);self.assertEqual(self.calls,[])

    def test_installed_session_rejection_precedes_observation(self):
        self.module.installed_session=lambda *args,**kwargs:(_ for _ in ()).throw(ValueError('not installed'))
        self.assertEqual(self.run_cli()[0],2);self.assertEqual(self.calls,[])

    def test_status_selected_effect_true_is_zero(self):
        self.values=[self.value(True)]
        code,rows=self.run_cli('status','--compact')
        self.assertEqual(code,0);self.assertTrue(rows[-1]['selected_effect_verified'])
        self.assertEqual(rows[-1]['operation'],'status');self.assertEqual(self.calls,['original-1'])

    def test_truthy_nonboolean_or_non_observed_effect_never_zero(self):
        value=self.value(True)
        for change in ({'selected_effect_verified':1},{'status':'unknown'}):
            modified=copy.deepcopy(value);modified['effect'].update(change)
            self.assertEqual(c.result_code(modified),2)
        value['transport_state']='published';self.assertEqual(c.result_code(value),2)

    def test_true_typed_waiting_is_three(self):
        self.values=[self.waiting()]
        code,rows=self.run_cli('status','--compact')
        self.assertEqual(code,3);self.assertTrue(rows[-1]['proven_waiting'])
        self.assertEqual(rows[-1]['pending_requests'][0]['native_request_id'],19)

    def test_waiting_label_or_bad_native_identity_is_unknown(self):
        value=self.value();value['request_state']='waiting_for_recipient'
        self.assertEqual(c.result_code(value),2)
        for field,new in (('state_raw',True),('native_request_id',0),('token',1),('recipient_handle','other')):
            value=self.waiting();value['reply']['selected']['pending']['selected_matches'][0][field]=new
            self.assertEqual(c.result_code(value),2)

    def test_waiting_native_id_signed32_boundaries_and_negative_ids(self):
        for native_id in (19,-1,-(1 << 31),(1 << 31)-1):
            with self.subTest(native_request_id=native_id):
                value=self.waiting()
                value['reply']['native_request_id']=native_id
                value['reply']['selected']['pending']['selected_matches'][0]['native_request_id']=native_id
                self.assertTrue(c.proven_waiting(value))
                self.assertEqual(c.result_code(value),3)
                self.values=[value]
                code,rows=self.run_cli('status','--compact')
                self.assertEqual(code,3)
                self.assertEqual(rows[-1]['pending_requests'][0]['native_request_id'],native_id)

    def test_waiting_native_id_overflows_zero_and_nonintegers_are_unknown(self):
        for native_id in (1 << 40,-(1 << 40),1 << 31,-(1 << 31)-1,0,True,19.0):
            with self.subTest(native_request_id=native_id):
                value=self.waiting()
                value['reply']['native_request_id']=native_id
                value['reply']['selected']['pending']['selected_matches'][0]['native_request_id']=native_id
                self.assertFalse(c.proven_waiting(value))
                self.assertEqual(c.result_code(value),2)

    def test_waiting_native_id_row_and_reply_projection_must_match(self):
        for row_id,reply_id in ((19,-1),(-1,19),(19,1 << 40),(1 << 40,19)):
            with self.subTest(row=row_id,reply=reply_id):
                value=self.waiting()
                value['reply']['native_request_id']=reply_id
                value['reply']['selected']['pending']['selected_matches'][0]['native_request_id']=row_id
                self.assertFalse(c.proven_waiting(value))
                self.assertEqual(c.result_code(value),2)

    def test_relation_compact_retains_status_full_pair_and_direction(self):
        value=self.value();value['command']['action']='guarantee'
        pair=dict(actor_tag='FRA',target_tag='SCO',actor_handle='0x1234',target_handle='0x5678')
        value['relation']=dict(status='reverse_relation_observed',two_pass_equal=True,
            snapshot=dict(pair=pair,object=dict(address='0x880000',first_handle='0x5678',second_handle='0x1234',requested_direction_matches=False)))
        compact=c.compact(value)
        self.assertEqual(compact['relation_status'],'reverse_relation_observed')
        self.assertEqual(compact['relation_pair'],pair)
        self.assertIs(compact['relation_direction_matches'],False)
        self.assertEqual(compact['identity'],self.identity)

    def test_source_change_after_observe_cannot_emit_success(self):
        self.values=[self.value(True)]
        def change():self.manifest['sealed']=False;self.write_manifest()
        self.after=change
        code,rows=self.run_cli();self.assertEqual(code,2);self.assertFalse(rows[-1]['selected_effect_verified'])

    def test_session_change_after_observe_is_unknown(self):
        self.values=[self.value(True)];self.after=lambda:self.session.write_text('{}')
        self.assertEqual(self.run_cli()[0],2)

    def test_observer_wrong_session_or_request_is_unknown(self):
        self.values=[self.value(True)];self.values[0]['request_id']='other'
        self.assertEqual(self.run_cli()[0],2)

    def test_observer_command_must_preserve_original_request_id(self):
        self.values=[self.value(True)];self.values[0]['command']['request_id']='other'
        self.assertEqual(self.run_cli()[0],2)

    def test_watch_stops_on_selected_effect_without_retry(self):
        self.values=[self.value(),self.value(True)]
        code,rows=self.run_cli('watch','--duration-seconds','10','--max-samples','8','--compact')
        self.assertEqual(code,0);self.assertEqual(self.calls,['original-1','original-1'])
        self.assertEqual(len(self.sleeps),1);self.assertEqual(self.prepares,[])
        self.assertTrue(rows[-1]['selected_effect_verified'])

    def test_watch_sample_bound_with_frozen_clock(self):
        self.sleep=lambda seconds:self.sleeps.append(seconds)
        code,rows=self.run_cli('watch','--max-samples','3','--duration-seconds','300')
        self.assertEqual(code,2);self.assertEqual(len(self.calls),3);self.assertEqual(len(self.sleeps),2)
        self.assertTrue(rows[-1]['watch_bound_reached'])

    def test_watch_deadline_bound_and_waiting_exit(self):
        self.values=[self.waiting()]
        code,rows=self.run_cli('watch','--duration-seconds','1','--interval-ms','1000','--max-samples','10')
        self.assertEqual(code,3);self.assertEqual(len(self.calls),2);self.assertEqual(self.sleeps,[1.0])
        self.assertTrue(rows[-1]['watch_bound_reached'])

    def test_watch_invalid_bounds_reject_before_import(self):
        for args in (('--duration-seconds','0'),('--duration-seconds','301'),('--interval-ms','249'),('--max-samples','129')):
            code,_=self.run_cli('watch',*args)
            self.assertEqual(code,2)
        self.assertEqual(self.loads,[]);self.assertEqual(self.calls,[])

    def test_watch_guard_rechecked_before_next_sample(self):
        def sleep(seconds):
            self.fake_time+=seconds;self.manifest['sealed']=False;self.write_manifest()
        self.sleep=sleep
        code,rows=self.run_cli('watch','--max-samples','3')
        self.assertEqual(code,2);self.assertEqual(len(self.calls),1)
        self.assertEqual(rows[-1]['status'],'unknown')

    def test_no_serve_publisher_installer_or_legacy_cli_options(self):
        for args in (['serve'],['publish'],['load'],['catalog','--manifest','other'],
            ['prepare','--request-id','x','--action','guarantee','--actor','FRA','--target','SCO','--legacy-probe','old.json']):
            with self.subTest(args=args),self.assertRaises(SystemExit):c.parser().parse_args(args)


if __name__=='__main__':unittest.main()
