"""New route guard and sessionless capability boundaries; no game process."""
import http.client
import json
import sys
import threading
import unittest
from unittest.mock import patch

from tools import eu4_runtime_observer_r3 as entry


class EntryTests(unittest.TestCase):
    def test_bad_pin_blocks_all_forwarding_and_serve(self):
        for operation in ('effects', 'war', 'relations', 'serve', 'catalog'):
            with self.subTest(operation=operation), patch.object(sys, 'argv', ['entry', operation]), \
                patch.object(entry, 'runtime_source_pins', side_effect=RuntimeError('bad R3 pin')), \
                patch('tools.eu4_runtime_observer_r2.main') as r2, \
                patch('tools.observe_relation_runtime.main') as relations:
                with self.assertRaisesRegex(RuntimeError, 'bad R3 pin'):
                    entry.main()
                r2.assert_not_called()
                relations.assert_not_called()
                self.assertEqual(sys.argv, ['entry', operation])

    def test_effects_delegate_after_guard_without_arg_changes(self):
        argv = ['entry', 'effects', '--session-file', 'existing.json', 'status', '--request-id', 'original']
        with patch.object(sys, 'argv', list(argv)), patch.object(entry, 'runtime_source_pins', return_value={}), \
            patch('tools.eu4_runtime_observer_r2.main', return_value=3) as r2:
            self.assertEqual(entry.main(), 3)
            r2.assert_called_once_with()
            self.assertEqual(sys.argv, argv)

    def test_war_delegate_after_guard_without_arg_changes(self):
        argv = ['entry', 'war', '--pid', '1', '--creation', '1234', 'status', '--actor', 'FRA', '--target', 'ENG']
        with patch.object(sys, 'argv', list(argv)), patch.object(entry, 'runtime_source_pins', return_value={}), \
            patch('tools.eu4_runtime_observer_r2.main', return_value=0) as r2:
            self.assertEqual(entry.main(), 0)
            r2.assert_called_once_with()
            self.assertEqual(sys.argv, argv)

    def test_relation_delegate_preserves_all_specialist_flags(self):
        argv = ['entry', 'relations', '--pid', '80340', '--creation', '01dd5c075fcf8c26',
            'status', '--action', 'guarantee', '--actor', 'SAV', '--target', 'FRA']
        with patch.object(sys, 'argv', list(argv)), patch.object(entry, 'runtime_source_pins', return_value={}), \
            patch('tools.observe_relation_runtime.main', return_value=0) as relations:
            self.assertEqual(entry.main(), 0)
            relations.assert_called_once_with()
            self.assertEqual(sys.argv, [argv[0], *argv[2:]])

    def test_no_session_catalog_has_no_effect_profiles(self):
        value = entry.catalog(effects_enabled=False)
        self.assertEqual(value['profiles'], [])
        self.assertFalse(value['all120_effect_profiles_complete'])
        self.assertFalse(value['current_state_is_request_completion'])
        self.assertIn('current_indexed_relations', value)
        self.assertIn('war_state', value)

    def test_real_source_graph_is_file_only(self):
        with patch('bridge.relation_state_service.RuntimeCapture', side_effect=AssertionError('process opened')):
            checked = entry.runtime_source_pins()
        self.assertIn('tools/eu4_runtime_observer_r3.py', checked)
        self.assertIn('bridge/relation_effect_reader.py', checked)


class CheckedRouteTests(unittest.TestCase):
    def test_bad_source_prevents_delegated_read(self):
        from unittest.mock import Mock
        observer = Mock()
        with patch.object(entry, 'runtime_source_pins', side_effect=RuntimeError('bad source')):
            with self.assertRaisesRegex(RuntimeError, 'bad source'):
                entry.CheckedRoutes(observer).observe_pair('guarantee', 'FRA', 'SAV')
        observer.observe_pair.assert_not_called()

    def test_changed_source_after_read_cannot_return_success(self):
        from unittest.mock import Mock
        observer = Mock()
        observer.observe_pair.return_value = {'status': 'observed'}
        with patch.object(entry, 'runtime_source_pins', side_effect=[{'pin': 'before'}, {'pin': 'after'}]):
            with self.assertRaisesRegex(ValueError, 'changed during read'):
                entry.CheckedRoutes(observer).observe_pair('guarantee', 'FRA', 'SAV')
        observer.observe_pair.assert_called_once_with('guarantee', 'FRA', 'SAV')

    def test_successful_effect_delegate_retains_original_receipt(self):
        from unittest.mock import Mock
        value = {'transport_state': 'dispatched', 'native_receipt': {'known_cleanup_complete': False}}
        observer = Mock()
        observer.observe.return_value = value
        with patch.object(entry, 'runtime_source_pins', return_value={'pin': 'same'}):
            result = entry.CheckedRoutes(observer).observe('original')
        self.assertIs(result, value)
        self.assertFalse(result['native_receipt']['known_cleanup_complete'])


class CombinedHTTPTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        self.war, self.relations = Mock(), Mock()
        self.war.observe_pair.return_value = {'status': 'observed', 'pair_state': 'opponents'}
        self.relations.observe_pair.return_value = {'status': 'reverse_relation_observed',
            'requested_direction_matches': False, 'runtime_effect_verified': False}
        self.guard = patch.object(entry, 'runtime_source_pins', return_value={'pin': 'same'})
        self.guard.start()
        self.token = 'combined-observer-test-token-123456'
        self.server = entry.compose_server(self.war, self.relations, port=0, token=self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=0.01))
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.guard.stop()
        self.assertFalse(self.thread.is_alive())

    def request(self, path, *, token=True, method='GET'):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            client.request(method, path, headers={'Authorization': 'Bearer '+self.token} if token else {})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_relation_and_war_routes_both_reach_correct_delegate(self):
        self.assertEqual(self.request('/observer/v1/wars/ENG/AMG')[0], 200)
        code, value = self.request('/observer/v1/relations/guarantee/SAV/FRA')
        self.assertEqual((code, value['status']), (200, 'reverse_relation_observed'))
        self.assertFalse(value['requested_direction_matches'])
        self.war.observe_pair.assert_called_once_with('ENG', 'AMG')
        self.relations.observe_pair.assert_called_once_with('guarantee', 'SAV', 'FRA')

    def test_host_guard_refusal_is_unknown_and_never_native_rejection(self):
        self.relations.observe_pair.side_effect = ValueError('Expected paused checkpoint')
        code, value = self.request('/observer/v1/relations/guarantee/FRA/SAV')
        self.assertEqual(code, 422)
        self.assertEqual(value['status'], 'unknown')
        self.assertFalse(value['automatic_command_retry'])
        self.assertEqual(value['requests_published'], 0)

    def test_no_auth_and_writes_never_read_state(self):
        self.assertEqual(self.request('/observer/v1/relations/guarantee/FRA/SAV', token=False)[0], 403)
        self.assertEqual(self.request('/observer/v1/wars/ENG/AMG', method='POST')[0], 405)
        self.war.observe_pair.assert_not_called()
        self.relations.observe_pair.assert_not_called()

    def test_sessionless_catalog_and_effects_are_truthful(self):
        code, value = self.request('/observer/v1/capabilities')
        self.assertEqual(code, 200)
        self.assertEqual(value['profiles'], [])
        self.assertIn('current_indexed_relations', value)
        self.assertFalse(value['current_state_is_request_completion'])
        self.assertEqual(self.request('/observer/v1/effects/not-configured')[0], 404)


if __name__ == '__main__':
    unittest.main()
