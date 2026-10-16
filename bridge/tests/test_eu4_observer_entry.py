"""Public entry cleanup regressions; no game, socket or background thread."""
import sys
import unittest
from unittest.mock import Mock, patch

from tools import eu4_observer as entry


class EntryCleanupTests(unittest.TestCase):
    def exercise_service(self, *, print_error=None, serve_error=None):
        server = Mock(server_port=12345)
        server.serve_forever.side_effect = serve_error
        arguments = ['entry', 'serve', '--pid', '80340', '--creation', '01dd5c075fcf8c26']
        with patch.object(sys, 'argv', arguments), patch.object(entry, 'source_pins', return_value={}), \
            patch('tools.eu4_runtime_observer_r3.compose_server', return_value=server), \
            patch('bridge.war_state_service.WarStateObserver'), \
            patch('bridge.relation_state_service.RelationStateObserver'), \
            patch('builtins.print', side_effect=print_error):
            try:
                result, error = entry.main(), None
            except BaseException as exc:
                result, error = None, exc
        return server, result, error

    def test_broken_stdout_closes_listener_before_reraising(self):
        server, result, error = self.exercise_service(print_error=BrokenPipeError('closed stdout'))
        self.assertIsInstance(error, BrokenPipeError)
        server.serve_forever.assert_not_called()
        server.server_close.assert_called_once_with()

    def test_keyboard_interrupt_closes_listener(self):
        server, result, error = self.exercise_service(serve_error=KeyboardInterrupt())
        self.assertEqual(result, 0)
        self.assertIsNone(error)
        server.server_close.assert_called_once_with()

    def test_service_exception_closes_listener_and_propagates(self):
        server, result, error = self.exercise_service(serve_error=RuntimeError('service failed'))
        self.assertIsInstance(error, RuntimeError)
        server.server_close.assert_called_once_with()

    def test_normal_return_closes_listener(self):
        server, result, error = self.exercise_service()
        self.assertEqual(result, 0)
        self.assertIsNone(error)
        server.server_close.assert_called_once_with()

    def test_bad_entry_pin_refuses_before_all_delegate(self):
        for operation in ('serve', 'effects', 'relations', 'war', 'catalog'):
            with self.subTest(operation=operation), patch.object(sys, 'argv', ['entry', operation]), \
                patch.object(entry, 'source_pins', side_effect=ValueError('bad entry pin')), \
                patch('tools.eu4_runtime_observer_r3.main') as specialist, \
                patch('tools.eu4_runtime_observer_r3.compose_server') as compose:
                with self.assertRaisesRegex(ValueError, 'bad entry pin'):
                    entry.main()
                specialist.assert_not_called()
                compose.assert_not_called()

    def test_nonserve_forward_keeps_arguments_and_return_code(self):
        arguments = ['entry', 'effects', '--session-file', 'original.json', 'status', '--request-id', 'original']
        with patch.object(sys, 'argv', arguments), patch.object(entry, 'source_pins', return_value={}), \
            patch('tools.eu4_runtime_observer_r3.main', return_value=3) as specialist:
            self.assertEqual(entry.main(), 3)
            self.assertEqual(sys.argv, arguments)
            specialist.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
