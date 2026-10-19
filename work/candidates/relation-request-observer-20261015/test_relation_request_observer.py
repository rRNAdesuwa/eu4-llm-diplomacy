"""Candidate integration tests: retained-file audit + native-layout byte graph.

No Windows process is opened. No host load, publication or native call is
allowed. Request/audit fixtures are written directly under TemporaryDirectory.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from bridge import diplomacy_effect_observer as frozen_observer
from bridge.tag_command_backend import TagCommandBackend, SCHEMA, encode, wire, boot, digest, decode
from bridge.tests.test_relation_effect_reader import graph, receipt, LEFT, RIGHT, OBJECT, OTHER, LAYOUTS
from bridge.tests.test_effect_observer_memory import (
    BASE, ACTOR, TARGET, COUNTRIES, FRA, SCO, PAUSE, GAME, handle)

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('relation_request_candidate', HERE/'relation_request_observer.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
DLL_BASE = 0x190000000


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        build = self.path/'build'
        build.mkdir()
        manifest_raw = c.DEFAULT_MANIFEST.read_bytes()
        manifest = decode(manifest_raw)
        (build/'build.json').write_bytes(manifest_raw)
        (build/manifest['DLL']).write_bytes((c.DEFAULT_MANIFEST.parent/manifest['DLL']).read_bytes())
        self.patch(patch.object(c, 'DEFAULT_MANIFEST', build/'build.json'))
        self.backend = TagCommandBackend(build/'build.json')
        self.identity = dict(pid=77,creation='0000000000000001',session='1'*32,
            dll_sha256=manifest['dll']['sha256'],manifest_sha256=digest(manifest_raw))
        self.session = self.backend.session(self.identity)
        self.session.mkdir()
        self.report_path = build/'session-77-0000000000000001.json'
        self.report_path.write_bytes(encode(dict(identity=self.identity,experimental=True,installation=dict(
            pid=77,dll=str(build/manifest['DLL']),bridge_thread_exit_status='0x0',
            test_save_acknowledged=True,dll_unloaded=False))))
        (build/'loader-intent-77-0000000000000001.json').write_bytes(encode(dict(
            identity=self.identity,outcome='unknown_until_loader_returns')))
        (build/'bootstrap-77-0000000000000001.request').write_bytes(boot(self.identity,purpose=self.backend.purpose))
        self.rows = []
        # Real installation rows are emitted by the loader thread; requests by owner.
        self.event('bootstrap_verified',0,thread=99,native_environment_initialized=True)
        self.event('hook_installed',0,thread=99)
        self.command = dict(request_id='offline-relation-1',action='offer_alliance',actor='FRA',target='SCO')
        self.present = False
        self.reverse = False
        self.host = True
        self.transform = None
        self.after_capture = None
        self.captures = []
        self.closes = []
        self.patch(patch.object(TagCommandBackend,'load',side_effect=AssertionError('No installation allowed')))
        self.patch(patch.object(TagCommandBackend,'publish',side_effect=AssertionError('No publication allowed')))
        self.patch(patch.object(frozen_observer,'WindowsRuntime',side_effect=AssertionError('No process access allowed')))
        self.patch(patch.object(c,'HeldRPMPort',side_effect=lambda held: held.port))
        owner = self

        class SyntheticCapture(c.RelationRequestCapture):
            def __enter__(inner):
                inner.request_pins = c.source_pins()
                inner.installation, _ = c.installed_session(inner.backend, inner.identity)
                inner.initial_pins = c.effect_pins()
                inner.base = BASE
                inner.modules = [(BASE,str(owner.path/'eu4.exe'))]
                if owner.host:
                    inner.modules.append((DLL_BASE,str(owner.backend.build/owner.backend.manifest['DLL'])))
                inner.runtime = types.SimpleNamespace(readonly=types.SimpleNamespace(pe_header=lambda raw: dict(
                    machine=0x8664,timestamp=owner.backend.manifest['PE_timestamp'],
                    size_of_image=owner.backend.manifest['SizeOfImage'])))
                inner.held = types.SimpleNamespace(
                    injector=types.SimpleNamespace(_canonical=lambda path: str(Path(path).resolve()).casefold()),
                    identity_check=lambda: None, modules=lambda: inner.modules,
                    close=lambda: owner.closes.append(True))
                return inner

            def capture_relation(inner, command, binding=None):
                memory = graph(command['action'],owner.present,owner.reverse)
                memory.map(DLL_BASE,8192)
                if owner.transform:
                    owner.transform(memory)
                inner.held.port = memory
                owner.captures.append(dict(command=copy.deepcopy(command),binding=copy.deepcopy(binding),memory=memory))
                value = super().capture_relation(command,binding)
                if owner.after_capture:
                    owner.after_capture(value)
                return value

        self.factory = SyntheticCapture
        self.observer = c.RelationRequestObserver(self.identity,backend=self.backend,store=self.path/'observations',
            allow_tag_host=True,relation_capture_factory=self.factory)

    def patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def event(self, name, seq, **fields):
        row=dict(schema=SCHEMA,event=name,**self.identity,ordinal=len(self.rows)+1,
            production_ready=False,no_send=False,owner_thread=12,thread=12,sequence=seq)
        row.update(fields)
        self.rows.append(row)
        self.write_audit()

    def write_audit(self):
        (self.session/'events.jsonl').write_bytes(b''.join(
            json.dumps(row,sort_keys=True).encode('ascii')+b'\n' for row in self.rows))

    def baseline_path(self):
        return self.observer.directory(self.command['request_id'])/'relation-request-baseline.json'

    def prepare(self):
        return self.observer.prepare(self.command)

    def dispatch_files(self):
        """Create only offline request bytes, never call the real publisher."""
        packet = wire(self.identity,1,60100,self.command,purpose=self.backend.purpose,
                      actions=self.backend.actions,limit=self.backend.limit)
        intent = dict(identity=self.identity,command=self.command,sequence=1,expires=60100,wire_sha256=digest(packet))
        self.backend.key_path(self.session,self.command['request_id']).write_bytes(encode(intent))
        (self.session/'1.request').write_bytes(packet)
        (self.session/'1.claim').write_bytes(packet)
        self.event('request_claimed',1,action=self.command['action'],actor='FRA',target='SCO',expires=60100)
        self.event('pair_bound',1,actor_handle=FRA,target_handle=SCO,human_player_handle=FRA,actor_is_human_player=True)
        self.event('dispatch_intent',1)
        self.event('native_call_return',1,call=7,normal=True,boolean=True,slot_consumed=True,exception=0)
        fields = receipt(self.command['action'])['native_result']
        fields = {k:v for k,v in fields.items() if k not in self.identity and k not in ('event','sequence','no_send')}
        self.event('request_result',1,**fields)

    def ready(self, action='offer_alliance'):
        self.command['action'] = action
        self.prepare()
        self.dispatch_files()
        self.present = True

    def observe(self):
        return self.observer.observe(self.command['request_id'],record=False)

    def unknown(self, result):
        self.assertEqual(result['effect']['status'],'unknown',result)
        self.assertFalse(result['effect']['selected_effect_verified'])
        self.assertEqual(result['completion_state'],'evidence_insufficient')
        self.assertFalse(result['automatic_command_retry'])
        return result

    def test_actual_byte_graph_and_original_audit_all_three_actions(self):
        for action in c.ACTIONS:
            with self.subTest(action=action):
                self.command['request_id'] = 'offline-'+action
                self.command['action'] = action
                self.present = False
                # A separate installation nonce is unnecessary; each synthetic
                # subcase clears only our own temporary request/audit fixture.
                self.rows = self.rows[:2]
                self.write_audit()
                self.prepare()
                self.dispatch_files()
                self.present = True
                result = self.observe()
                self.assertEqual(result['effect']['status'],'observed',result)
                self.assertEqual(result['completion_state'],'selected_effect_observed')
                self.assertEqual(result['native_receipt']['state'],'dispatched')
                self.assertEqual(result['relation']['snapshot']['pair']['actor_handle'],hex(FRA))
                self.assertFalse(result['AI_acceptance_verified'])
                self.assertFalse(result['effect']['exact_external_request_id_causality_verified'])
                self.assertFalse(result['effect']['global_membership_verified'])
                self.assertFalse(result['persistence_verified'])
                self.assertEqual(result['native_calls'],0)
                self.assertEqual(len(self.captures),len(self.closes))
                self.assertLessEqual(result['relation']['rpm_budget']['bytes'],512*1024)
                self.assertLessEqual(result['relation']['rpm_budget']['calls'],4096)

    def test_guarantee_reverse_is_not_requested_effect(self):
        self.ready('guarantee');self.reverse=True
        result=self.observe()
        self.assertEqual(result['effect']['status'],'not_observed',result)
        self.assertEqual(result['relation']['status'],'reverse_relation_observed')
        self.assertFalse(result['effect']['selected_effect_verified'])

    def test_symmetric_reverse_marriage_is_indexed_not_acceptance(self):
        self.ready('royal_marriage');self.reverse=True
        result=self.observe()
        self.assertEqual(result['effect']['status'],'observed',result)
        self.assertFalse(result['AI_acceptance_verified'])

    def test_unchanged_absence_is_not_observed_or_rejected(self):
        self.ready();self.present=False
        result=self.observe()
        self.assertEqual(result['effect']['status'],'not_observed',result)
        self.assertEqual(result['transport_state'],'dispatched')
        self.assertEqual(result['request_state'],'unknown')

    def test_existing_baseline_is_never_overwritten(self):
        self.prepare();raw=self.baseline_path().read_bytes();count=len(self.captures)
        with self.assertRaisesRegex(ValueError,'never replace'):self.prepare()
        self.assertEqual(self.baseline_path().read_bytes(),raw)
        self.assertEqual(len(self.captures),count)

    def test_exclusive_journal_write_handles_race_without_overwrite(self):
        path=self.path/'race.json'
        c.write_journal(path,{'first':True})
        raw=path.read_bytes()
        with self.assertRaises(FileExistsError):c.write_journal(path,{'second':True})
        self.assertEqual(path.read_bytes(),raw)

    def test_current_relation_cannot_be_retroactive_baseline(self):
        self.present=True
        with self.assertRaisesRegex(ValueError,'Fresh absent'):self.prepare()
        self.assertFalse(self.baseline_path().exists())

    def test_legacy_probe_cannot_create_relation_baseline(self):
        with self.assertRaisesRegex(ValueError,'fresh true-session'):
            self.observer.prepare(self.command,legacy_probe={})
        self.assertEqual(self.captures,[])

    def test_published_original_request_never_gets_retroactive_baseline(self):
        self.dispatch_files()
        with self.assertRaisesRegex(ValueError,'reserved'):self.prepare()
        self.assertEqual(self.captures,[])
        self.assertFalse(self.baseline_path().exists())

    def test_publisher_lock_before_baseline_refuses_without_capture(self):
        (self.session/'publisher.lock').write_bytes(b'offline lock')
        with self.assertRaisesRegex(ValueError,'publisher locked'):self.prepare()
        self.assertEqual(self.captures,[])

    def test_intent_appearing_during_capture_prevents_baseline(self):
        self.after_capture=lambda value: self.backend.key_path(self.session,self.command['request_id']).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'during baseline'):self.prepare()
        self.assertFalse(self.baseline_path().exists())
        self.assertEqual(len(self.closes),1)

    def test_lock_appearing_during_capture_prevents_baseline(self):
        self.after_capture=lambda value: (self.session/'publisher.lock').write_bytes(b'locked')
        with self.assertRaisesRegex(ValueError,'during baseline'):self.prepare()
        self.assertFalse(self.baseline_path().exists())

    def test_final_prewrite_guard_catches_late_lock(self):
        real_mkdir=Path.mkdir
        wanted=self.observer.directory(self.command['request_id'])
        def mkdir(path,*args,**kwargs):
            result=real_mkdir(path,*args,**kwargs)
            if path==wanted:(self.session/'publisher.lock').write_bytes(b'late lock')
            return result
        with patch.object(Path,'mkdir',mkdir),self.assertRaisesRegex(ValueError,'before baseline write'):
            self.prepare()
        self.assertFalse(self.baseline_path().exists())

    def test_publication_during_baseline_write_leaves_unusable_orphan(self):
        real_write=c.write_journal
        def late_publish(path,value):
            record=real_write(path,value)
            if path.name=='relation-request-baseline.json':
                self.dispatch_files()
            return record
        with patch.object(c,'write_journal',side_effect=late_publish):
            with self.assertRaisesRegex(ValueError,'during baseline write'):self.prepare()
        self.assertTrue(self.baseline_path().exists())
        self.assertFalse(self.baseline_path().with_name('relation-request-baseline-commit.json').exists())
        self.present=True;self.unknown(self.observe())
        self.assertEqual(len(self.captures),1)
        with self.assertRaisesRegex(ValueError,'never replace'):self.prepare()

    def test_missing_baseline_commit_is_unknown_without_current_capture(self):
        self.ready()
        self.baseline_path().with_name('relation-request-baseline-commit.json').unlink()
        self.unknown(self.observe());self.assertEqual(len(self.captures),1)

    def test_commit_tamper_during_status_is_unknown(self):
        self.ready()
        self.after_capture=lambda value:self.baseline_path().with_name('relation-request-baseline-commit.json').write_bytes(b'{}')
        self.unknown(self.observe())

    def test_missing_baseline_does_not_open_process(self):
        self.dispatch_files()
        self.unknown(self.observe())
        self.assertEqual(self.captures,[])

    def test_missing_installation_report_rejects_before_capture(self):
        self.report_path.unlink()
        with self.assertRaises(OSError):self.prepare()
        self.assertEqual(self.captures,[])

    def test_installation_loader_thread_dword_overflow_rejected(self):
        for row in self.rows:row['thread']=(1<<32)+99
        self.write_audit()
        with self.assertRaisesRegex(ValueError,'identity/thread encoding'):
            c.installed_session(self.backend,self.identity,ready=True)
        self.assertEqual(self.captures,[])

    def test_installation_owner_thread_dword_overflow_rejected(self):
        for row in self.rows:row['owner_thread']=(1<<32)+12
        self.write_audit()
        with self.assertRaisesRegex(ValueError,'owner thread exceeds DWORD'):
            c.installed_session(self.backend,self.identity,ready=True)
        self.assertEqual(self.captures,[])

    def test_installation_nonzero_sequence_thread_must_be_owner(self):
        self.event('offline_fixture_event',1,thread=99)
        with self.assertRaisesRegex(ValueError,'Non-owner native audit'):
            c.installed_session(self.backend,self.identity,ready=True)
        self.assertEqual(self.captures,[])

    def test_installation_legitimate_loader_thread_differs_from_owner(self):
        proof,audit=c.installed_session(self.backend,self.identity,ready=True)
        self.assertTrue(proof['installation_record_verified'])
        self.assertFalse(proof['live_hook_proven'])
        self.assertEqual(audit.rows[0]['thread'],99)
        self.assertEqual(audit.summary['owner_thread'],12)
        self.assertEqual(self.captures,[])

    def test_random_current_query_nonce_not_relabelled_as_tag_session(self):
        identity=dict(self.identity,session='9'*32)
        observer=c.RelationRequestObserver(identity,backend=self.backend,store=self.path/'nonce',
            relation_capture_factory=self.factory)
        with self.assertRaisesRegex(ValueError,'Installed session identity'):observer.prepare(self.command)
        self.assertEqual(self.captures,[])

    def test_current_only_capture_markers_rejected_even_with_real_identity(self):
        self.after_capture=lambda value:value['state'].update(
            identity_purpose='Read-only observation nonce; not a TAG installation or request',native_session_installed=False)
        with self.assertRaisesRegex(ValueError,'not original-session'):self.prepare()
        self.assertFalse(self.baseline_path().exists())

    def test_bootstrap_packet_wrong_nonce_rejected(self):
        path=self.backend.build/'bootstrap-77-0000000000000001.request'
        path.write_bytes(boot(dict(self.identity,session='9'*32),purpose=self.backend.purpose))
        with self.assertRaisesRegex(ValueError,'bootstrap packet'):self.prepare()
        self.assertEqual(self.captures,[])

    def test_missing_hook_and_partial_audit_reject_before_capture(self):
        self.rows.pop();self.write_audit()
        with self.assertRaisesRegex(ValueError,'installed-session audit'):self.prepare()
        self.event('hook_installed',0)
        with (self.session/'events.jsonl').open('ab') as stream:stream.write(b'{')
        with self.assertRaisesRegex(ValueError,'complete audit'):self.prepare()
        self.assertEqual(self.captures,[])

    def test_terminal_installed_session_cannot_prepare(self):
        self.event('terminal',0)
        with self.assertRaisesRegex(ValueError,'terminal'):self.prepare()
        self.assertEqual(self.captures,[])

    def test_no_loaded_host_cannot_prepare_but_original_status_can_observe(self):
        self.host=False
        with self.assertRaisesRegex(ValueError,'host to be present'):self.prepare()
        self.host=True;self.ready();self.host=False
        self.assertEqual(self.observe()['effect']['status'],'observed')

    def test_explicit_tag_host_permission_required(self):
        self.observer.allow_tag_host=False
        with self.assertRaisesRegex(ValueError,'research module'):self.prepare()

    def test_wrong_original_full_binding_rejects_before_second_capture(self):
        self.ready()
        bound=next(row for row in self.rows if row['event']=='pair_bound')
        bound['actor_handle']=handle('FRA',1,valid=2)
        bound['human_player_handle']=bound['actor_handle']
        self.write_audit()
        self.unknown(self.observe())
        self.assertEqual(len(self.captures),1)

    def test_incomplete_receipt_rejects_before_second_capture(self):
        self.ready();del self.rows[-1]['submit_attempted'];self.write_audit()
        self.unknown(self.observe())
        self.assertEqual(len(self.captures),1)

    def test_non_dispatched_receipt_never_reads_current_relation(self):
        self.ready()
        self.rows[-1].update(submitted=False,status=2,reason='full88_normal_false')
        self.write_audit()
        result=self.unknown(self.observe())
        self.assertEqual(result['transport_state'],'native_rejected')
        self.assertEqual(len(self.captures),1)

    def test_raw_request_tampering_is_unknown_without_capture(self):
        self.ready();(self.session/'1.request').write_bytes(b'changed')
        self.unknown(self.observe());self.assertEqual(len(self.captures),1)

    def test_audit_change_during_prepare_refuses_baseline(self):
        self.after_capture=lambda value:self.event('read_only_fixture_event',0)
        with self.assertRaisesRegex(ValueError,'audit or sources changed'):self.prepare()
        self.assertFalse(self.baseline_path().exists())

    def test_audit_change_during_status_closes_to_unknown(self):
        self.ready();self.after_capture=lambda value:self.event('read_only_fixture_event',0)
        self.unknown(self.observe())

    def test_installation_change_during_status_closes_to_unknown(self):
        self.ready()
        def change(value):
            data=decode(self.report_path.read_bytes());data['new_unknown_field']=True
            self.report_path.write_bytes(encode(data))
        self.after_capture=change
        self.unknown(self.observe())

    def test_baseline_change_during_status_closes_to_unknown(self):
        self.ready();self.after_capture=lambda value:self.baseline_path().write_bytes(b'{}')
        self.unknown(self.observe())

    def test_sources_change_after_capture_closes_to_unknown(self):
        self.ready()
        actual=c.source_pins
        def change(value):
            changed=actual();changed['synthetic-change']={'bytes':1,'sha256':'0'*64}
            self.patch(patch.object(c,'source_pins',return_value=changed))
        self.after_capture=change
        self.unknown(self.observe())

    def test_source_guard_failure_never_enters_capture(self):
        self.ready()
        with patch.object(c,'source_pins',side_effect=ValueError('changed sources')):
            result=self.unknown(self.observe())
            self.assertEqual(result['native_receipt']['state'],'dispatched')
        self.assertEqual(len(self.captures),1)

    def test_baseline_source_or_provenance_mutation_refuses_before_capture(self):
        self.ready();path=self.baseline_path();raw=path.read_bytes()
        for mutate in (lambda x:x['source_pins'].clear(),
            lambda x:x['provenance'].update(publisher_lock_absent_before=False),
            lambda x:x['provenance'].update(audit_sha256_before='0'*64,audit_sha256_after='0'*64),
            lambda x:x['capture']['state']['passes'][0]['indexes']['actor'].update(entries_hex='00')):
            data=decode(raw);mutate(data);path.write_bytes(encode(data))
            self.unknown(self.observe());self.assertEqual(len(self.captures),1)

    def test_country_full_handle_change_and_table_change_are_unknown(self):
        self.ready()
        self.transform=lambda m:m.put(ACTOR+0x20,'Q',handle('FRA',1,valid=2))
        self.unknown(self.observe())
        def changed_table(m):
            count=[0]
            def hook(mem,address,size):
                if address==COUNTRIES and size==1380*8:
                    count[0]+=1
                    if count[0]==2:mem.put(COUNTRIES+24,'Q',TARGET)
            m.hook=hook
        self.transform=changed_table
        self.unknown(self.observe())

    def test_bilateral_typed_index_and_raw_object_corruption_are_unknown(self):
        self.ready()
        changes=[(TARGET+0x14F8+0x78,'Q',BASE+0x1C3A538+8),
                 (RIGHT+8,'Q',OTHER),(OBJECT+0x28,'B',1),
                 (OBJECT+0x18,'Q',handle('SCO',2,valid=2))]
        for address,fmt,value in changes:
            with self.subTest(address=hex(address)):
                self.transform=lambda m,a=address,f=fmt,v=value:m.put(a,f,v)
                self.unknown(self.observe())

    def test_two_pass_mutation_and_short_read_are_unknown(self):
        self.ready()
        def changing(m):
            count=[0]
            def hook(mem,address,size):
                if address==OBJECT and size==0x48:
                    count[0]+=1
                    if count[0]==3:mem.put(OBJECT+0x20,'i',56468208-14)
            m.hook=hook
        self.transform=changing;self.unknown(self.observe())
        self.transform=lambda m:m.short.add(OBJECT);self.unknown(self.observe())

    def test_manual_pause_required_and_handles_close(self):
        self.transform=lambda m:m.put(PAUSE+0x48,'B',0)
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(len(self.captures),len(self.closes))

    def test_recorded_capture_journal_failure_clears_new_success(self):
        self.ready()
        with patch.object(c,'write_journal',side_effect=OSError('synthetic disk full')):
            result=self.unknown(self.observer.observe(self.command['request_id']))
        self.assertIn('record_failure',result)

    def test_status_journals_are_append_only_and_keep_raw_capture(self):
        self.ready()
        first=self.observer.observe(self.command['request_id'])
        second=self.observer.observe(self.command['request_id'])
        self.assertNotEqual(first['record']['path'],second['record']['path'])
        path=Path(first['relation']['capture_record']['path'])
        value=decode(path.read_bytes())
        self.assertEqual(value['state']['snapshot']['object']['raw_object_hex'],
                         first['relation']['snapshot']['object']['raw_object_hex'])

    def test_frozen_fifteen_actions_delegate_without_changing_profile_logic(self):
        self.command['action']='knowledge_sharing'
        with patch.object(c.LiveDiplomacyObserver,'prepare',return_value={'delegated':True}) as parent:
            self.assertEqual(self.prepare(),{'delegated':True})
            parent.assert_called_once()

    def test_frozen_action_status_delegates(self):
        self.command['action']='knowledge_sharing';self.dispatch_files()
        with patch.object(c.LiveDiplomacyObserver,'observe',return_value={'delegated':True}) as parent:
            self.assertEqual(self.observe(),{'delegated':True})
            parent.assert_called_once_with(self.command['request_id'],record=False)

    def test_capture_projection_tampering_is_replayed_not_trusted(self):
        self.ready('guarantee')
        self.after_capture=lambda value:value['state']['snapshot']['object'].update(requested_direction_matches=False)
        self.unknown(self.observe())

    def test_catalog_is_only_eighteen_candidate_profiles_and_zero_new_runtime_effects(self):
        catalog=c.candidate_catalog()
        self.assertEqual(len(catalog['profiles']),18)
        self.assertEqual(catalog['stable_public_request_profile_count'],15)
        self.assertTrue(catalog['candidate_unsealed'])
        self.assertEqual(catalog['new_runtime_effects_verified'],0)
        self.assertEqual(len(self.backend.actions),120)
        self.assertEqual(len(self.backend.manifest['source_pins']),44)
        self.assertEqual(self.captures,[])


if __name__ == '__main__':
    unittest.main()
