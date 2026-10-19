"""Held-port byte graphs and actual loopback routing; no game access."""
import contextlib
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from bridge import relation_state_service as service
from bridge.tag_command_backend import DEFAULT_MANIFEST,decode,read,digest
from bridge.tests.test_effect_observer_memory import (
    HeldMemory,BASE,GAME,COUNTRIES,ACTOR,TARGET,PAUSE,COUNT,FRA,SCO,handle)
from bridge.tests.test_relation_effect_reader import graph,OBJECT

TOKEN='relation-test-token-0123456789'
PINS={'synthetic-pin':dict(bytes=1,sha256='1'*64)}


def backend():
    raw=read(DEFAULT_MANIFEST,1024*1024)
    obj=types.SimpleNamespace(manifest_path=DEFAULT_MANIFEST,build=DEFAULT_MANIFEST.parent,
        manifest=decode(raw),manifest_sha=digest(raw),verify_count=0)
    def verify():obj.verify_count+=1;return obj.manifest
    obj.verify=verify
    return obj


class FakeCapture:
    def __init__(self,memory,modules=None):
        self.held=HeldMemory(memory);self.base=BASE;self.closed=False
        self.modules=modules if modules is not None else self.held.modules()
        self.held.modules=lambda:copy.deepcopy(self.modules)
        self.held.injector=types.SimpleNamespace(_canonical=lambda p:str(Path(p).resolve()).casefold())
        self.initial_pins=copy.deepcopy(PINS)
        self.parsed_headers=[]
        self.header=dict(machine=0x8664,timestamp=0,size_of_image=0)
        def pe_header(raw):self.parsed_headers.append(raw);return self.header
        self.runtime=types.SimpleNamespace(readonly=types.SimpleNamespace(pe_header=pe_header))

    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True


class HeldGraphTests(unittest.TestCase):
    def setUp(self):
        self.no_windows=patch('bridge.diplomacy_effect_observer.WindowsRuntime',
            side_effect=AssertionError('Tests must never access a game process'))
        self.no_windows.start();self.addCleanup(self.no_windows.stop)

    def run_graph(self,memory,action='offer_alliance',actor='FRA',target='SCO',*,
                  modules=None,allow_tag_host=False,change=None,store=None):
        b=backend();cap=FakeCapture(memory,modules)
        observer=service.RelationStateObserver(77,'0000000000000001',backend=b,
            allow_tag_host=allow_tag_host,store=store)
        if change:change(cap,b,observer)
        with patch.object(service,'RuntimeCapture',return_value=cap), \
             patch.object(service,'source_pins',return_value=copy.deepcopy(PINS)), \
             patch.object(service,'effect_pins',return_value=copy.deepcopy(PINS)):
            try:value=observer.observe_pair(action,actor,target)
            finally:self.assertTrue(cap.closed)
        return value,cap,b

    def test_actual_typed_graph_three_profiles_and_absence(self):
        for action in ('offer_alliance','royal_marriage','guarantee'):
            for present in (True,False):
                with self.subTest(action=action,present=present):
                    value,cap,b=self.run_graph(graph(action,present),action)
                    self.assertEqual(value['status'],'current_relation_observed' if present else 'pair_absent_observed')
                    self.assertIs(value['requested_direction_matches'],True if present else None)
                    self.assertTrue(value['two_pass_equal']);self.assertEqual(cap.held.header_calls,0)
                    self.assertEqual(b.verify_count,1);self.assertGreater(cap.held.rpm_calls,0)
                    self.assertIn((COUNTRIES,COUNT*8),cap.held.graph.reads)
                    self.assertEqual(cap.held.graph.reads.count((COUNTRIES,COUNT*8)),2)
                    for flag in ('runtime_effect_verified','global_membership_verified','request_causality_verified',
                        'world_epoch_proven','world_lifetime_lease_proven','atomic_snapshot_proven','native_session_installed'):
                        self.assertFalse(value[flag])

    def test_directional_guarantee_is_not_forward_success(self):
        value,_,_=self.run_graph(graph('guarantee',reverse=True),'guarantee')
        self.assertEqual(value['status'],'reverse_relation_observed')
        self.assertFalse(value['current_relation_observed']);self.assertFalse(value['requested_direction_matches'])
        self.assertEqual(value['object']['first_handle'],hex(SCO))
        self.assertFalse(value['runtime_effect_verified'])

    def test_symmetric_reverse_query_keeps_current(self):
        for action in ('offer_alliance','royal_marriage'):
            value,_,_=self.run_graph(graph(action),action,'SCO','FRA')
            self.assertEqual(value['status'],'current_relation_observed')
            self.assertTrue(value['requested_direction_matches'])
            self.assertEqual(value['pair']['actor_handle'],hex(SCO))

    def test_full_table_scan_detects_duplicate_at_last_slot(self):
        m=graph();extra=0x900000;m.map(extra,0x9B78)
        m.put(extra+0x20,'Q',FRA);m.put(COUNTRIES+(COUNT-1)*8,'Q',extra)
        with self.assertRaisesRegex(ValueError,'Duplicate selected country'):
            self.run_graph(m)

    def test_invalid_complete_selected_handle_refuses(self):
        for bad in (handle('FRA',1,valid=0),handle('FRA',1,kind=1),handle('FRA',0xFFFF),FRA|(1<<24)):
            m=graph();m.put(ACTOR+0x20,'Q',bad)
            with self.subTest(handle=hex(bad)),self.assertRaises(ValueError):self.run_graph(m)

    def test_missing_selected_country_refuses_not_absence(self):
        m=graph();m.put(COUNTRIES+16,'Q',0)
        with self.assertRaisesRegex(ValueError,'Selected country unavailable'):self.run_graph(m)

    def test_paused_world_and_load_cache_guards(self):
        for address,value in ((PAUSE+0x48,0),(GAME+0x2521,1),(GAME+0x7485,1)):
            m=graph();m.put(address,'B',value)
            with self.subTest(address=hex(address)),self.assertRaises(ValueError):self.run_graph(m)

    def test_changed_table_after_selected_lookup_refuses(self):
        m=graph()
        def change(memory,address,size):
            if address==BASE+0xA68D90:memory.put(COUNTRIES+(COUNT-1)*8,'Q',ACTOR)
        m.hook=change
        with self.assertRaisesRegex(ValueError,'country table'):self.run_graph(m)

    def test_short_object_read_remains_unknown_not_absent(self):
        m=graph();m.short.add(OBJECT)
        value,cap,_=self.run_graph(m)
        self.assertEqual(value['status'],'unknown');self.assertIsNone(value['requested_direction_matches'])
        self.assertIsNone(value['object']);self.assertFalse(value['two_pass_equal'])
        self.assertIn('Exact VM_READ unavailable',value['failure']['message']);self.assertTrue(cap.closed)

    def test_changed_module_set_refuses_before_return(self):
        def change(cap,b,o):cap.held.modules=lambda:cap.modules+[(0xA00000,'unrelated/new.dll')]
        with self.assertRaisesRegex(ValueError,'Process modules'):self.run_graph(graph(),change=change)

    def test_changed_process_identity_refuses(self):
        def change(cap,b,o):
            def fail():raise RuntimeError('Held process creation changed')
            cap.held.identity_check=fail
        with self.assertRaisesRegex(RuntimeError,'creation changed'):self.run_graph(graph(),change=change)

    def test_source_change_after_reads_refuses_and_closes(self):
        cap=FakeCapture(graph());b=backend();o=service.RelationStateObserver(77,'0000000000000001',backend=b)
        with patch.object(service,'RuntimeCapture',return_value=cap), \
             patch.object(service,'effect_pins',return_value=PINS), \
             patch.object(service,'source_pins',side_effect=[PINS,{}]):
            with self.assertRaisesRegex(ValueError,'sources changed'):o.capture_pair('offer_alliance','FRA','SCO')
        self.assertTrue(cap.closed)

    def test_source_pin_failure_precedes_process_open(self):
        o=service.RelationStateObserver(77,'0000000000000001',backend=backend())
        with patch.object(service,'RuntimeCapture') as opener, \
             patch.object(service,'source_pins',side_effect=ValueError('Pinned source changed')):
            with self.assertRaisesRegex(ValueError,'Pinned source changed'):o.capture_pair('offer_alliance','FRA','SCO')
        opener.assert_not_called()

    def test_backend_postverification_failure_closes_capture(self):
        def change(cap,b,o):
            def fail():raise ValueError('Default native source changed')
            b.verify=fail
        with self.assertRaisesRegex(ValueError,'Default native source changed'):self.run_graph(graph(),change=change)

    def test_full_table_scan_fault_is_not_pair_absence(self):
        m=graph();m.put(COUNTRIES+(COUNT-1)*8,'Q',0x999000)
        with self.assertRaisesRegex(OSError,'Synthetic unmapped read'):self.run_graph(m)

    def test_nondefault_backend_refuses_before_runtime(self):
        b=backend();b.manifest_path=Path('synthetic/other-build.json')
        with patch.object(service,'RuntimeCapture') as opener,self.assertRaisesRegex(ValueError,'default TAG'):
            service.RelationStateObserver(77,'0000000000000001',backend=b)
        opener.assert_not_called()

    def test_research_host_requires_explicit_exact_default_match(self):
        b=backend();path=b.build/b.manifest['DLL'];base=0xA00000
        for modules,allowed in (([(base,str(path))],False),
            ([(base,'synthetic/tag_diplomacy_other.dll')],True),
            ([(base,str(path)),(base+0x10000,'synthetic/eu4_pair_other.dll')],True)):
            with self.subTest(modules=modules),self.assertRaisesRegex(ValueError,'research module'):
                self.run_graph(graph(),modules=modules,allow_tag_host=allowed)

    def test_optional_default_host_pe_uses_existing_held_rpm_and_parser(self):
        b=backend();base=0xA00000;m=graph();m.map(base,8192)
        def correct(cap,b,o):cap.header=dict(machine=0x8664,timestamp=b.manifest['PE_timestamp'],size_of_image=b.manifest['SizeOfImage'])
        value,cap,_=self.run_graph(m,modules=[(base,str(b.build/b.manifest['DLL']))],allow_tag_host=True,change=correct)
        self.assertEqual(value['status'],'current_relation_observed')
        self.assertEqual([len(x) for x in cap.parsed_headers],[8192]);self.assertEqual(cap.held.header_calls,0)
        with self.assertRaisesRegex(ValueError,'header differs'):
            self.run_graph(m,modules=[(base,str(b.build/b.manifest['DLL']))],allow_tag_host=True)

    def test_local_journal_retains_complete_capture_without_effect_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            value,_,_=self.run_graph(graph(),store=folder)
            p=Path(value['record']['path']);raw=p.read_bytes();saved=json.loads(raw)
            self.assertEqual(value['record']['sha256'],digest(raw));self.assertEqual(saved['passes'][0],saved['passes'][1])
            self.assertEqual(saved['snapshot']['object']['address'],hex(OBJECT))
            self.assertEqual(saved['source_pins'],PINS);self.assertFalse(value['runtime_effect_verified'])

    def test_invalid_request_fields_refuse_before_process_open(self):
        o=object.__new__(service.RelationStateObserver)
        for fields in (('declare_war','FRA','SCO'),('offer_alliance','FRA','FRA'),
                       ('offer_alliance','fra','SCO'),('offer_alliance',True,'SCO')):
            with patch.object(service,'RuntimeCapture') as opener,self.assertRaises(ValueError):o.capture_pair(*fields)
            opener.assert_not_called()


class FakeRelation:
    def __init__(self):self.calls=[];self.fail=False
    def observe_pair(self,action,actor,target):
        self.calls.append((action,actor,target))
        if self.fail:raise RuntimeError('Changing target graph')
        return dict(action=action,status='reverse_relation_observed',requested_direction_matches=False,
            runtime_effect_verified=False,native_calls=0,requests_published=0)


class FakeEffects:
    def __init__(self):self.calls=[]
    def observe(self,request_id):self.calls.append(request_id);return dict(request_id=request_id,effect=dict(status='unknown'))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        from bridge.diplomacy_observer_service import make_server
        self.effects,self.relations=FakeEffects(),FakeRelation()
        self.server=make_server(self.effects,port=0,token=TOKEN)
        original=self.server.RequestHandlerClass
        self.catalog=dict(schema='caller-owned-catalog',profiles=['caller_existing_profile'],effects_complete=False)
        catalog=self.catalog
        class CallerHandler(original):
            def do_GET(self):
                if self.path=='/observer/v1/capabilities':
                    return self.send_json(200,catalog) if self.authorized() else self.send_json(403,dict(error='unauthorized'))
                return super().do_GET()
        self.server.RequestHandlerClass=CallerHandler;self.original=CallerHandler
        self.assertIs(service.make_relation_server(self.relations,self.server),self.server)
        self.assertTrue(issubclass(self.server.RequestHandlerClass,self.original))
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs=dict(poll_interval=0.01));self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.assertFalse(self.thread.is_alive())

    def request(self,path='/observer/v1/relations/guarantee/SAV/FRA',*,method='GET',headers=None,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            connection.request(method,path,headers={'Authorization':'Bearer '+TOKEN} if headers is None else headers,body=body)
            response=connection.getresponse();self.assertEqual(response.getheader('Cache-Control'),'no-store')
            return response.status,json.loads(response.read())
        finally:connection.close()

    def test_relation_route_retains_reverse_direction(self):
        code,value=self.request();self.assertEqual(code,200)
        self.assertEqual(value['status'],'reverse_relation_observed');self.assertFalse(value['requested_direction_matches'])
        self.assertFalse(value['runtime_effect_verified']);self.assertEqual(self.relations.calls,[('guarantee','SAV','FRA')])

    def test_caller_catalog_is_unchanged(self):
        code,value=self.request('/observer/v1/capabilities');self.assertEqual(code,200)
        self.assertEqual(value,self.catalog);self.assertEqual(self.relations.calls,[])

    def test_existing_effect_route_inherits(self):
        code,value=self.request('/observer/v1/effects/original-request')
        self.assertEqual((code,value['request_id']),(200,'original-request'));self.assertEqual(self.effects.calls,['original-request'])
        self.assertEqual(self.relations.calls,[])

    def test_no_or_wrong_auth_and_origin_and_host_never_read(self):
        for headers in ({},{'Authorization':'Bearer wrong'},
            {'Authorization':'Bearer '+TOKEN,'Origin':'http://localhost'},
            {'Authorization':'Bearer '+TOKEN,'Host':'example.org'},
            {'Authorization':'Bearer '+TOKEN,'Host':'localhost:1'}):
            with self.subTest(headers=headers):self.assertEqual(self.request(headers=headers)[0],403)
        self.assertEqual(self.relations.calls,[])

    def test_malformed_or_unsupported_pair_never_reads(self):
        for tail in ('guarantee/SAV/SAV','declare_war/FRA/ENG','offer_alliance/fra/POR',
                     'offer_alliance/%46RA/POR','offer_alliance/FRA/POR/again','guarantee/SAV/FRA?retry=1',
                     'guarantee/SAV/FRA#fragment','offer_alliance/'+('A'*520)+'/POR'):
            with self.subTest(tail=tail):self.assertEqual(self.request('/observer/v1/relations/'+tail)[0],422)
        self.assertEqual(self.relations.calls,[])

    def test_runtime_fault_is_unknown_without_retry(self):
        self.relations.fail=True;code,value=self.request()
        self.assertEqual((code,value['status']),(409,'unknown'));self.assertFalse(value['automatic_command_retry'])
        self.assertEqual(len(self.relations.calls),1)

    def test_all_inherited_write_methods_refuse_without_observation(self):
        for method in ('POST','PUT','PATCH','DELETE'):
            with self.subTest(method=method):
                code,value=self.request(method=method,body='{"send":true}')
                self.assertEqual((code,value['requests_published']),(405,0))
        self.assertEqual(self.relations.calls,[]);self.assertEqual(self.effects.calls,[])

    def test_unrecognized_namespace_delegates_to_404(self):
        self.assertEqual(self.request('/observer/v1/unrecognized')[0],404);self.assertEqual(self.relations.calls,[])


class ServiceSourceTests(unittest.TestCase):
    def test_manifest_graph_and_offline_catalog(self):
        pins=service.source_pins();self.assertIn('bridge/relation_state_service.py',pins)
        catalog=service.relation_capabilities();self.assertEqual(len(catalog['actions']),3)
        self.assertFalse(catalog['runtime_effect_verified']);self.assertFalse(catalog['global_membership_verified'])

    def test_standalone_catalog_has_no_configured_effect_profiles(self):
        from tools.observe_relation_runtime import standalone_server
        server=standalone_server(FakeRelation(),port=0,token=TOKEN)
        thread=threading.Thread(target=server.serve_forever,kwargs=dict(poll_interval=0.01));thread.start()
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        try:
            connection.request('GET','/observer/v1/capabilities',headers={'Authorization':'Bearer '+TOKEN})
            response=connection.getresponse();value=json.loads(response.read());self.assertEqual(response.status,200)
            self.assertEqual(value['profiles'],[]);self.assertFalse(value['request_effect_observer_configured'])
            self.assertEqual(len(value['relation_state']['actions']),3)
        finally:
            connection.close();server.shutdown();server.server_close();thread.join(2)
        self.assertFalse(thread.is_alive())


if __name__=='__main__':unittest.main()
