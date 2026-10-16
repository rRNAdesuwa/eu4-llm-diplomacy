"""File-only continuation accounting: never load or publish a game command."""
import copy
import unittest

from bridge.tag_command_backend import encode
from work.merge_tag31_integration import combine, extend, sha


class MergeTests(unittest.TestCase):
    def fixture(self):
        a = dict(request_id='first', action='improve_relations', actor='FRA', target='POR')
        b = dict(request_id='second', action='warn', actor='FRA', target='BUR')
        old_a = dict(command=a, state='unknown_no_retry', binding={}, native_result={'status': 5})
        old_b = dict(command=b, state='not_dispatched', binding=None, native_result=None)
        new_b = dict(command=b, state='native_rejected', binding={}, native_result={'status': 1})
        first = dict(identity={'session': 'old'}, audit_sha256='a', terminal=True,
                     file_only=True, planned=2, results=[old_a, old_b],
                     native_call_begins=1, native_exceptions=[])
        last = dict(identity={'session': 'new'}, audit_sha256='b', terminal=False,
                    file_only=True, planned=1, results=[new_b],
                    native_call_begins=4, native_exceptions=[])
        return [a, b], [b], first, last

    def run_merge(self, values):
        original, remaining, first, last = values
        a, b, c, d = map(encode, (original, remaining, first, last))
        review = dict(schema='EU4TAG-CONTINUATION-REVIEW/1', file_only=True,
                      only_unclaimed_commands=True, idempotency_keys_preserved=True,
                      publishes=False, original_commands_file_sha256=sha(a),
                      remaining_commands_sha256=sha(b), captured_evidence_file_sha256=sha(c),
                      original_identity=first['identity'], original_audit_sha256=first['audit_sha256'],
                      original_count=2, remaining_count=1, excluded_count=1,
                      excluded=[dict(command=original[0], state='unknown_no_retry', may_resend=False)])
        return combine(a, b, encode(review), c, d)

    def test_preserves_unknown_and_counts_each_request_once(self):
        result = self.run_merge(self.fixture())
        self.assertEqual(result['states'], {'unknown_no_retry': 1, 'native_rejected': 1})
        self.assertEqual(result['native_call_begins'], 5)
        self.assertFalse(result['gameplay_effects_verified'])
        self.assertFalse(result['automatic_retry'])

    def test_refuses_attempted_request_in_continuation(self):
        values = self.fixture()
        values[2]['results'][1]['binding'] = {'actor_handle': 1}
        with self.assertRaises(ValueError):
            self.run_merge(values)

    def test_refuses_changed_command(self):
        values = self.fixture()
        values[3]['results'][0]['command'] = dict(values[1][0], target='ENG')
        with self.assertRaises(ValueError):
            self.run_merge(values)

    def test_refuses_duplicate_or_running_or_partial_evidence(self):
        for mutation in ('duplicate', 'running', 'partial'):
            with self.subTest(mutation=mutation):
                values = copy.deepcopy(self.fixture())
                if mutation == 'duplicate':
                    values[3]['results'].append(copy.deepcopy(values[3]['results'][0]))
                elif mutation == 'running':
                    values[3]['results'][0]['state'] = 'claimed'
                else:
                    values[3]['partial_audit_tail'] = True
                with self.assertRaises(ValueError):
                    self.run_merge(values)

    def test_extend_does_not_recount_shared_fragment(self):
        parent = self.run_merge(self.fixture())
        shared = copy.deepcopy(parent['fragments'][-1])
        next_fragment = dict(identity={'session': 'third'}, audit_sha256='c',
                             native_call_begins=7, terminal=False)
        segment = dict(schema=parent['schema'], file_only=True, planned=1,
                       results=[copy.deepcopy(parent['results'][1])],
                       fragments=[shared, next_fragment], native_exceptions=[],
                       input_sha256={'first': parent['input_sha256']['last'], 'last': 'new'})
        result = extend(encode(parent), segment)
        self.assertEqual(result['planned'], 2)
        self.assertEqual(result['native_call_begins'], 12)
        self.assertEqual(len(result['fragments']), 3)
        self.assertEqual(result['results'][0]['state'], 'unknown_no_retry')

    def test_extend_refuses_altering_attempted_outcome(self):
        parent = self.run_merge(self.fixture())
        segment = dict(schema=parent['schema'], file_only=True, planned=1,
                       results=[dict(parent['results'][1], state='dispatched')],
                       fragments=[parent['fragments'][-1], dict(native_call_begins=7)],
                       input_sha256={'first': parent['input_sha256']['last']})
        with self.assertRaises(ValueError):
            extend(encode(parent), segment)


if __name__ == '__main__':
    unittest.main()
