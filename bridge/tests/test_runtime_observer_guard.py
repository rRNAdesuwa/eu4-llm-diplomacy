"""Regression for bypassing the new wrapper's source pins; no game access."""
import sys
import unittest
from unittest.mock import patch

from tools import eu4_runtime_observer_r2 as entry


class GuardTests(unittest.TestCase):
    def assert_bad_pin_refuses(self, operation):
        argv = ['eu4_runtime_observer_r2.py', operation, 'catalog']
        with patch.object(sys, 'argv', argv), patch.object(entry, 'runtime_source_pins',
            side_effect=RuntimeError('invalid wrapper pin')) as guard, \
            patch('tools.eu4_runtime_observer.main') as delegate:
            with self.assertRaisesRegex(RuntimeError, 'invalid wrapper pin'):
                entry.main()
            guard.assert_called_once_with()
            delegate.assert_not_called()
            self.assertEqual(sys.argv, argv)

    def test_bad_effect_pin_blocks_before_forward(self):
        self.assert_bad_pin_refuses('effects')

    def test_bad_war_pin_blocks_before_forward(self):
        self.assert_bad_pin_refuses('war')

    def test_bad_serve_pin_blocks_before_forward(self):
        self.assert_bad_pin_refuses('serve')

    def test_valid_effect_forward_preserves_all_arguments(self):
        argv = ['eu4_runtime_observer_r2.py', 'effects', '--session-file', 'original.json',
            '--allow-tag-host', 'status', '--request-id', 'original-id']
        with patch.object(sys, 'argv', list(argv)), patch.object(entry, 'runtime_source_pins', return_value={}), \
            patch('tools.observe_diplomacy_live.main', return_value=3) as delegate:
            self.assertEqual(entry.main(), 3)
            delegate.assert_called_once_with()
            self.assertEqual(sys.argv, [argv[0], *argv[2:]])

    def test_valid_war_forward_preserves_all_arguments(self):
        argv = ['eu4_runtime_observer_r2.py', 'war', '--pid', '80340', '--creation',
            '01dd5c075fcf8c26', 'status', '--actor', 'ENG', '--target', 'AMG']
        with patch.object(sys, 'argv', list(argv)), patch.object(entry, 'runtime_source_pins', return_value={}), \
            patch('tools.observe_war_runtime.main', return_value=0) as delegate:
            self.assertEqual(entry.main(), 0)
            delegate.assert_called_once_with()
            self.assertEqual(sys.argv, [argv[0], *argv[2:]])

    def test_real_source_graph_is_file_only(self):
        with patch('bridge.war_state_service.RuntimeCapture', side_effect=AssertionError('process opened')):
            checked = entry.runtime_source_pins()
        self.assertIn('tools/eu4_runtime_observer_r2.py', checked)
        self.assertIn('bridge/diplomacy_live_observer.py', checked)
        self.assertIn('bridge/war_peace_memory_observer_r2.py', checked)


if __name__ == '__main__':
    unittest.main()
