"""Actual file-backed API discovery; no game process or publication is allowed."""
import contextlib
import http.client
import io
import json
import threading
import unittest
from unittest.mock import patch

from bridge.tag_action_conditions import action_conditions
from bridge.tag_action_lookup import lookup_action, search_actions
from bridge.tag_command_backend import ROOT, TagCommandBackend, read, validate_command
from bridge.tag_command_service import make_server


class ActionLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = TagCommandBackend()

    def test_pages_cover_registry_and_exclusions_without_creating_bindings(self):
        rows, offset = [], 0
        with patch.object(self.backend, 'os_runtime', side_effect=AssertionError('No game access')):
            while offset is not None:
                page = search_actions(self.backend, offset=offset, limit=50)
                self.assertEqual(page['total'],147)
                self.assertFalse(page['evaluated_in_game'])
                rows.extend(page['results'])
                offset = page['next_offset']
        self.assertEqual(len(rows),len({r['action'] for r in rows}))
        self.assertEqual({r['action'] for r in rows if r['support']=='bound'},set(self.backend.actions))
        self.assertEqual(sum(r['support']=='excluded' for r in rows),27)

    def test_exact_lookup_distinguishes_clone_from_catalog_accessor(self):
        result = lookup_action(self.backend,'trade_favors_for_trust')
        self.assertEqual(result['native_check']['object_size_bytes'],72)
        self.assertEqual(result['native_check']['clone_rva'],'0x4fe740')
        self.assertEqual(result['native_check']['setter_rva'],'0x4e99d0')
        self.assertEqual(result['native_check']['vtable_rva'],'0x1c80c60')
        self.assertEqual(result['catalog_native_mapping']['variants'][0]['accessor_rva'],'0x4fe4c0')
        findings = result['native_research_findings']
        self.assertTrue(any(f['id']=='four_envoy_id_exclusion' for f in findings))
        self.assertTrue(all(not f['evaluated_in_game'] and not f['historical_failure_branch_proven']
                            for f in findings))
        self.assertEqual(findings,action_conditions(self.backend,'trade_favors_for_trust')['native_research_findings'])

    def test_excluded_lookup_does_not_enable_publishing_and_independent_is_not_pair(self):
        result = lookup_action(self.backend,'cancel_sow_discontent')
        self.assertEqual(result['support'],'excluded')
        self.assertIsNone(result['current_host_binding'])
        self.assertIsNone(result['native_check'])
        self.assertIsNone(result['conditions_endpoint'])
        self.assertTrue(result['native_research_findings'])
        with self.assertRaisesRegex(ValueError,'no native binding'):
            validate_command(dict(request_id='lookup-no-send',actor='FRA',target='ENG',
                                  action=result['action']),self.backend.actions)
        rival = lookup_action(self.backend,'select_rival')
        self.assertEqual(rival['native_check']['route'],'independent_command')
        self.assertNotIn('vtable_rva',rival['native_check'])

    def test_search_preserves_direction_and_exact_match_priority(self):
        page = search_actions(self.backend,query='knowledge_sharing')
        self.assertEqual([r['action'] for r in page['results']],
                         ['knowledge_sharing','ask_knowledge_sharing'])
        excluded = search_actions(self.backend,query='cancel',category='covert',support='excluded')
        self.assertEqual({r['action'] for r in excluded['results']},
                         {'cancel_agitate_for_liberty','cancel_fabricate_claim',
                          'cancel_justify_trade_conflict','cancel_sow_discontent'})
        self.assertEqual(search_actions(self.backend,query='no such native family')['total'],0)

    def test_invalid_selectors_and_changed_evidence_fail_without_game_access(self):
        with patch.object(self.backend,'os_runtime',side_effect=AssertionError('No game access')):
            for params in ({'limit':0},{'offset':-1},{'offset':True},{'category':'war'},
                           {'support':'ready'},{'query':'x'*121}):
                with self.assertRaises(ValueError): search_actions(self.backend,**params)
            with self.assertRaisesRegex(ValueError,'Unknown action'):
                lookup_action(self.backend,'not_a_real_action')
            target = ROOT/'work/reports/rea-api-discovery-20261013/prior-four-findings.json'
            def changed(path,limit):
                data = read(path,limit)
                return data+b'\n' if path==target else data
            with patch('bridge.tag_action_conditions.read',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'documentation source changed'):
                    lookup_action(self.backend,'designate_march')

    def test_cli_lookup_and_search_do_not_construct_runtime(self):
        from tools.tag_command import main
        for arguments,field in [(['lookup','--action','ask_for_march'],'native_check'),
                                (['search','--query','march'],'results')]:
            output = io.StringIO()
            with patch('sys.argv',['tag_command.py',*arguments]), \
                 patch('bridge.tag_command_backend.WindowsRuntime',side_effect=AssertionError('No game access')), \
                 contextlib.redirect_stdout(output):
                self.assertEqual(main(),0)
            self.assertIn(field,json.loads(output.getvalue()))

    def test_http_discovery_auth_queries_and_no_runtime_side_effects(self):
        identity = dict(pid=77,creation='0000000000000001',session='1'*32,
                        manifest_sha256=self.backend.manifest_sha,
                        dll_sha256=self.backend.manifest['dll']['sha256'])
        server = make_server(self.backend,identity,port=0,token='offline-lookup-token')
        thread = threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.01})
        thread.start()
        connection = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        cases = [('/native/v1/actions?q=march',200,True),
                 ('/native/v1/actions?q=knowledge_sharing',200,True),
                 ('/native/v1/actions/cancel_sow_discontent',200,True),
                 ('/native/v1/actions?limit=0',422,True),
                 ('/native/v1/actions?q=march&q=trust',422,True),
                 ('/native/v1/actions?limit=2&actor=FRA',422,True),
                 ('/native/v1/actions?offset=-1',422,True),
                 ('/native/v1/actions/ask_for_march?q=ignored',422,True),
                 ('/native/v1/conditions/ask_for_march?q=ignored',422,True),
                 ('/native/v1/actions?q=march',403,False)]
        try:
            with patch.object(self.backend,'os_runtime',side_effect=AssertionError('No game access')), \
                 patch.object(self.backend,'publish',side_effect=AssertionError('No publication')):
                for path,expected,authorized in cases:
                    headers = {'Authorization':'Bearer offline-lookup-token'} if authorized else {}
                    connection.request('GET',path,headers=headers)
                    response = connection.getresponse(); value = json.loads(response.read())
                    self.assertEqual(response.status,expected,(path,value))
                    if expected==200: self.assertFalse(value['evaluated_in_game'])
        finally:
            connection.close(); server.shutdown(); server.server_close(); thread.join(2)
            self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
