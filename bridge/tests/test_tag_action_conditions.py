"""Condition documentation never opens a game process or performs a preview."""
import contextlib
import http.client
import io
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.tag_action_conditions import action_conditions
from bridge.tag_command_backend import ROOT, TagCommandBackend, decode, digest, encode, read
from bridge.tag_command_service import make_server
from tools.build_tag_action_conditions import LOCAL_INDEX, OUTPUT, build


class ConditionReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = TagCommandBackend()

    def test_all_bound_actions_have_exact_reproducible_conditions(self):
        actual = decode(read(OUTPUT, 2*1024*1024))
        self.assertEqual(actual, build())
        self.assertEqual(set(actual['actions']), set(self.backend.actions))
        self.assertFalse(actual['complete_legality_documented'])
        self.assertEqual(sum(bool(x['binding']['script_key']) for x in actual['actions'].values()), 39)

    def test_original_and_configured_mod_conditions_remain_distinct(self):
        with patch.object(self.backend, 'os_runtime', side_effect=AssertionError('No game access')):
            result = action_conditions(self.backend, 'create_pronoia')
        scripts = result['record']['script_conditions']
        original = next(c for c in scripts['original']['clauses'] if c['key'] == 'is_allowed')
        changed = next(c for c in scripts['configured_test_mod']['clauses'] if c['key'] == 'is_allowed')
        self.assertNotEqual(original['children'], changed['children'])
        self.assertEqual([(x['key'],x['value']) for x in changed['children']], [('always','yes')])
        self.assertFalse(result['evaluated_in_game'])

    def test_local_evidence_preserves_partial_coverage_and_independent_routes(self):
        document = decode(read(OUTPUT, 2*1024*1024))
        index = document['native_local_condition_index']
        self.assertEqual(len(index['families']), 51)
        pins = document['source_pins']['native_local_condition_index']
        self.assertEqual(pins[LOCAL_INDEX.relative_to(ROOT).as_posix()]['sha256'],
                         digest(read(LOCAL_INDEX, 1024*1024)))
        with patch.object(self.backend, 'os_runtime', side_effect=AssertionError('No game access')):
            vassal = action_conditions(self.backend, 'offer_vassalization')
            scripted = action_conditions(self.backend, 'create_pronoia')
            rival = action_conditions(self.backend, 'select_rival')
        family = vassal['native_local_condition_evidence']['family']
        self.assertTrue(any(r['key'] == 'NO_VASSAL_ABOVE_DEV'
                            for r in family['localization_key_references']))
        self.assertTrue(family['direct_calls'])
        self.assertFalse(family['coverage']['native_logic_complete'])
        self.assertTrue(all(r['is_taken_failure_branch_proven'] is False
                            for r in family['localization_key_references']))
        self.assertTrue(all(c['followed'] is False for c in family['direct_calls']))
        self.assertTrue(scripted['native_local_condition_evidence']['family']['coverage']['truncated'])
        self.assertIsNone(rival['native_local_condition_evidence']['family'])
        self.assertFalse(vassal['native_logic_complete'])
        self.assertFalse(vassal['native_local_condition_evidence']['evaluated_in_game'])

    def test_changed_offline_report_is_rejected_without_native_access(self):
        def changed(path, limit):
            raw = read(path, limit)
            return raw+b'\n' if path == LOCAL_INDEX else raw
        with patch('bridge.tag_action_conditions.read', side_effect=changed), \
             patch.object(self.backend, 'os_runtime', side_effect=AssertionError('No game access')):
            with self.assertRaisesRegex(ValueError, 'documentation source changed'):
                action_conditions(self.backend, 'offer_vassalization')

    def test_changed_subject_helper_is_rejected_even_with_unchanged_manifest(self):
        helper = ROOT/'mod/llm_diplomacy_unlock/common/scripted_effects/01_scripted_effects_for_diplomacy.txt'
        def changed(path, limit):
            raw = read(path, limit)
            return raw+b'\n' if path == helper else raw
        with patch('bridge.tag_action_conditions.read', side_effect=changed), \
             patch.object(self.backend, 'os_runtime', side_effect=AssertionError('No game access')):
            with self.assertRaisesRegex(ValueError, 'Configured test Mod bytes changed'):
                action_conditions(self.backend, 'create_pronoia')

    def test_generator_refuses_index_for_different_compiled_profile(self):
        def changed(path, limit):
            raw = read(path, limit)
            if path == LOCAL_INDEX:
                value = decode(raw)
                value['registry_sha256'] = '0'*64
                return encode(value)
            return raw
        with patch('tools.build_tag_action_conditions.read', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'compiled profiles differ'):
                build()

    def test_excluded_action_is_refused_without_runtime_access(self):
        with self.assertRaisesRegex(ValueError, 'no native binding'):
            action_conditions(self.backend, 'send_gift')

    def test_cli_reads_conditions_without_a_session_or_runtime(self):
        from tools.tag_command import main
        output = io.StringIO()
        with patch('sys.argv', ['tag_command.py','conditions','--action','royal_marriage']), \
             patch('bridge.tag_command_backend.WindowsRuntime', side_effect=AssertionError('No game access')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertEqual(json.loads(output.getvalue())['action'], 'royal_marriage')

    def test_http_conditions_need_no_game_methods(self):
        backend = SimpleNamespace(purpose=self.backend.purpose, actions=self.backend.actions,
                                  config_path=self.backend.config_path, manifest_sha=self.backend.manifest_sha)
        identity = dict(pid=77, creation='0000000000000001', session='1'*32,
                        manifest_sha256=self.backend.manifest_sha, dll_sha256=self.backend.manifest['dll']['sha256'])
        server = make_server(backend, identity, port=0, token='offline-conditions-test')
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':0.01})
        thread.start()
        connection = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        try:
            for action, expected in [('offer_vassalization',200),('send_gift',422)]:
                connection.request('GET','/native/v1/conditions/'+action,
                                   headers={'Authorization':'Bearer offline-conditions-test'})
                response = connection.getresponse()
                value = json.loads(response.read())
                self.assertEqual(response.status,expected)
                if expected == 200:
                    self.assertFalse(value['evaluated_in_game'])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(2)
            self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
