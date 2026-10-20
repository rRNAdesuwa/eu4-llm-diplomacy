"""Full-pipeline completion frame mutations with regenerated receipts/hashes."""
from copy import deepcopy
import json
import unittest
from synthetic import Fixture


class CompletionFrameTests(Fixture):
    def interval(self, sequence):
        index = next(i for i, e in enumerate(self.events)
                     if e['event'] == 'lab_request_complete' and e['sequence'] == sequence)
        prior = next(e for e in reversed(self.events[:index]) if e['event'] == 'research_frame')
        following = next(e for e in self.events[index + 1:] if e['event'] == 'research_frame')
        return self.events[index], prior['frames'], following['frames']

    def receipts(self):
        # Use the unchanged production research reader to regenerate exact
        # prefix status, publication, inventory and stopped-audit hashes.
        events = deepcopy(self.events)
        for item in self.case['requests']:
            seq = item['sequence']
            cut = next(i + 1 for i, e in enumerate(events)
                       if e['event'] == 'research_frame' and e['last_sequence'] == seq)
            self.events = deepcopy(events[:cut])
            self.capture('status' + str(seq), self.status(seq))
            if seq < len(self.case['requests']):
                key = 'pub' + str(seq + 1)
                pub = json.loads((self.root / (key + '.json')).read_bytes())
                current = self.status()
                current['publication'] = pub['report']['publication']
                self.capture(key, current)
        self.events = events
        self.refresh()

    def test_original_off_before_prior_health_full_pipeline_rejected(self):
        complete, _, _ = self.interval(5)
        complete['completion_frame'] = 1
        self.receipts()
        with self.assertRaisesRegex(ValueError, 'completion precedes'):
            self.run_review()

    def test_original_on_future_completion_full_pipeline_rejected(self):
        complete, _, _ = self.interval(3)
        complete['completion_frame'] = 999999
        self.receipts()
        with self.assertRaisesRegex(ValueError, 'first following health'):
            self.run_review()

    def test_on_equal_first_following_health_is_not_a_later_boundary(self):
        complete, _, following = self.interval(3)
        complete['completion_frame'] = following
        self.receipts()
        with self.assertRaisesRegex(ValueError, 'first following health'):
            self.run_review()

    def test_on_prior_minus_one_is_rejected_with_exact_receipts(self):
        complete, prior, _ = self.interval(3)
        complete['completion_frame'] = prior - 1
        self.receipts()
        with self.assertRaisesRegex(ValueError, 'completion precedes'):
            self.run_review()

    def test_both_controls_may_complete_in_the_preceding_health_frame(self):
        for sequence in (3, 5):
            complete, prior, _ = self.interval(sequence)
            complete['completion_frame'] = prior
        self.receipts()
        self.assertEqual(self.run_review()['status'], 'reviewed_stopped_session')

    def test_both_controls_may_complete_one_frame_before_following_health(self):
        for sequence in (3, 5):
            complete, _, following = self.interval(sequence)
            complete['completion_frame'] = following - 1
        self.receipts()
        self.assertEqual(self.run_review()['status'], 'reviewed_stopped_session')

    def test_off_equal_following_health_remains_rejected_by_real_reader(self):
        complete, _, following = self.interval(5)
        complete['completion_frame'] = following
        with self.assertRaises(ValueError):
            self.receipts()

    def test_boolean_float_and_out_of_range_completion_remain_rejected(self):
        saved = deepcopy(self.events)
        for value in (True, 521.0, 0, -1, 2**31):
            self.events = deepcopy(saved)
            self.interval(3)[0]['completion_frame'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.receipts()

    def test_first_following_health_cannot_be_bypassed_using_a_later_frame(self):
        complete, _, following = self.interval(3)
        # 539 is before a later health (540), but after the first one (530).
        complete['completion_frame'] = following + 9
        self.receipts()
        with self.assertRaisesRegex(ValueError, 'first following health'):
            self.run_review()


if __name__ == '__main__':
    unittest.main()
