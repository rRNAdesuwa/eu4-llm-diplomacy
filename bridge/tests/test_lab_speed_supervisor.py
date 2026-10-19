"""Supervisor decisions only; no game process or subprocess is opened."""
import copy
import unittest

from work.native.run_lab_speed_1375 import decision, DEADLINE_SECONDS, same_world


class LeaseSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(game=0x10000, server=0x20000, pause_manager=0x30000,
                           player=0x0100007a00415246, raw_date=56456976,
                           paused=True, native_speed_index=0)
        self.after = {**self.before, 'raw_date': 56457024}
        self.evidence = {'requests': {7: {'lease_complete': {'session_frozen': False,
                           'readback_matches': True, 'paused_readback': True}}},
                         'lease_pending': False, 'pending': False, 'latest_frame': {}}

    def test_completed_requires_native_evidence_and_independent_pause(self):
        self.assertEqual(decision(self.evidence, 7, self.before, self.after, 1), 'completed')
        self.after['paused'] = False
        self.assertEqual(decision(self.evidence, 7, self.before, self.after, 1), 'terminate_pause_unverified')

    def test_unrelated_or_missing_completion_is_not_success(self):
        self.assertEqual(decision(self.evidence, 8, self.before, self.after, 1), 'wait')
        self.evidence['requests'].clear()
        self.assertEqual(decision(self.evidence, 7, self.before, self.after, 1), 'wait')

    def test_new_world_and_time_regression_require_termination(self):
        for key in ('game', 'server', 'pause_manager', 'player'):
            after = {**self.after, key: self.after[key] + 1}
            self.assertFalse(same_world(self.before, after))
            self.assertEqual(decision(self.evidence, 7, self.before, after, 1), 'terminate_world_changed')
        after = {**self.after, 'raw_date': self.before['raw_date'] - 1}
        self.assertEqual(decision(self.evidence, 7, self.before, after, 1), 'terminate_world_changed')

    def test_deadline_wins_even_if_native_completion_arrives_late(self):
        self.assertEqual(decision(self.evidence, 7, self.before, self.after, DEADLINE_SECONDS), 'terminate_deadline')

    def test_unknown_ownership_or_pending_lease_never_means_paused_success(self):
        for field in ('session_frozen', 'world_changed', 'thread_changed'):
            evidence = copy.deepcopy(self.evidence)
            evidence['latest_frame'] = {field: True}
            self.assertEqual(decision(evidence, 7, self.before, self.after, 1), 'terminate_session_frozen')
        for field in ('pending', 'lease_pending'):
            evidence = copy.deepcopy(self.evidence)
            evidence[field] = True
            self.assertEqual(decision(evidence, 7, self.before, self.after, 1), 'terminate_pause_unverified')


if __name__ == '__main__':
    unittest.main()
