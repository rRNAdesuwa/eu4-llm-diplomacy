from copy import deepcopy
from pathlib import Path
import collections
import json
import unittest
import project as p

HERE = Path(__file__).resolve().parent


def groups():
    out = collections.defaultdict(list)
    for row in p.decode((HERE/'compile-final/build/capture.jsonl').read_bytes()):
        out[row['scenario']].append(row)
    return out


def numbered(rows):
    for n, r in enumerate(rows, 1): r['ordinal'] = n
    return rows


class ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.g = groups()

    def reject(self, rows):
        result = p.project(rows)
        self.assertFalse(result['valid_complete_mock'])
        self.assertEqual(result['model']['state'], 'frozen')
        for k in ('actual_host_format_supported', 'actual_journal_validated', 'runtime_authorized',
                  'effect_verified', 'production_ready', 'retry_allowed', 'native_called_by_projector'):
            self.assertIs(result[k], False)
        return result

    def test_four_normal_actual_core_mock_matrices(self):
        for name in ('dispatched', 'preview_false', 'gate_false', 'mixed'):
            v = p.project(deepcopy(self.g[name])); self.assertTrue(v['valid_complete_mock'], (name, v['error']))
            self.assertEqual(len(v['model']['rows']), 5)
            expected = {'dispatched': ['dispatched']*5, 'preview_false': ['full_preview_rejected']*5,
                        'gate_false': ['command_gate_rejected']*5,
                        'mixed': ['full_preview_rejected', 'command_gate_rejected', 'dispatched',
                                  'full_preview_rejected', 'command_gate_rejected']}[name]
            self.assertEqual([r['outcome'] for r in v['model']['rows']], expected)
            self.assertFalse(v['effect_verified']); self.assertFalse(v['model']['actual_journal_validated'])

    def test_twelve_terminal_real_mock_captures(self):
        for name in set(self.g)-{'dispatched', 'preview_false', 'gate_false', 'mixed'}:
            self.reject(deepcopy(self.g[name]))

    def test_unknown_dispatch_keeps_current_and_no_cleanup_permission(self):
        for name in ('submit_throw', 'submit_false_consumed', 'submit_true_unconsumed',
                     'submit_false_unconsumed', 'logger_return'):
            r = self.reject(deepcopy(self.g[name])); current = r['model']['current_item']
            self.assertEqual(current['family'], 'corrupt_officials')
            self.assertEqual(current['outcome'], 'dispatch_unknown')
            self.assertTrue(current['caller_ownership_relinquished'])
            self.assertFalse(current['cleanup_authorized']); self.assertFalse(current['retry_allowed'])
            self.assertEqual(current['last_recorded_owned_objects'], [])

    def test_work_intervals_preserve_return_after_expiry(self):
        for name, outcome in (('cleanup_expired', 'full_preview_rejected'), ('expire_after_submit', 'dispatched')):
            r = self.reject(deepcopy(self.g[name]))
            self.assertEqual(r['model']['rows'][0]['outcome'], outcome)
            self.assertEqual(len(r['model']['rows']), 1)
            intervals = r['normal_mock_call_intervals']
            self.assertTrue(any(q['entered_uptime'] < 70000 and q['returned_observation_uptime'] == 70000 for q in intervals))
            self.assertEqual(r['error'], 'new work after TTL')

    def test_every_removed_line_rejected_after_renumbering(self):
        original = self.g['dispatched']
        for i in range(len(original)):
            with self.subTest(index=i, kind=original[i]['kind']):
                self.reject(numbered(deepcopy(original[:i]+original[i+1:])))

    def test_duplicate_intents_claims_returns_results_rejected(self):
        original = self.g['dispatched']
        for kind in ('claim', 'core_event', 'mock_call_enter', 'operation_result'):
            i = next(i for i, r in enumerate(original) if r['kind'] == kind)
            changed = deepcopy(original); changed.insert(i, deepcopy(changed[i])); self.reject(numbered(changed))

    def test_every_core_scalar_type_alias_rejected(self):
        rows = self.g['dispatched']
        representatives = {(0, 1), (3, 6), (3, 10), (6, 10)}
        seen = set()
        for index, row in enumerate(rows):
            if row['kind'] != 'core_event': continue
            key = (row['data']['event']['kind'], row['data']['event']['item']['step'])
            if key not in representatives or key in seen: continue
            seen.add(key)
            def leaves(d, path=()):
                for k, v in d.items():
                    if type(v) is dict: yield from leaves(v, path+(k,))
                    elif type(v) in (int, bool): yield path+(k,), v
            for path, value in leaves(row['data']['event']):
                altered = list(rows); altered[index] = deepcopy(row); d = altered[index]['data']['event']
                for k in path[:-1]: d = d[k]
                d[path[-1]] = int(value) if type(value) is bool else float(value)
                self.reject(altered)

    def test_all_result_scalar_types_and_extra_fields_rejected(self):
        rows = self.g['dispatched']
        for idx, r in enumerate(rows):
            if r['kind'] != 'operation_result': continue
            for key, value in r['data']['result'].items():
                if type(value) not in (int, bool): continue
                changed = deepcopy(rows)
                changed[idx]['data']['result'][key] = int(value) if type(value) is bool else float(value)
                self.reject(changed)
            changed = deepcopy(rows); changed[idx]['data']['result']['guessed_cleanup'] = False; self.reject(changed)

    def test_original_clone_fixed_fields_ids_and_direction(self):
        rows = self.g['dispatched']
        ix = next(i for i, r in enumerate(rows) if r['kind'] == 'core_event' and
                  r['data']['event']['kind'] == 3 and r['data']['event']['item']['step'] == 6)
        for object_name in ('original_fields', 'clone_fields'):
            for key, value in rows[ix]['data']['event']['item'][object_name].items():
                changed = deepcopy(rows); changed[ix]['data']['event']['item'][object_name][key] = value+1
                self.reject(changed)
        for key in ('original_id', 'clone_id', 'command_id', 'token', 'family', 'ordinal', 'owner_frame'):
            changed = deepcopy(rows); changed[ix]['data']['event']['item'][key] += 1; self.reject(changed)

    def test_later_health_is_independent_owner_operation(self):
        rows = deepcopy(self.g['dispatched'])
        index = next(i for i, r in enumerate(rows) if r['kind'] == 'operation_begin' and r['data']['operation'] == 3)
        rows[index]['data']['frame'] -= 1
        self.reject(rows)
        rows = deepcopy(self.g['dispatched']); rows[index]['data']['operation'] = 2; self.reject(rows)

    def test_no_submit_entry_inference_from_intent_or_return(self):
        rows = deepcopy(self.g['dispatched'])
        index = next(i for i, r in enumerate(rows) if r['kind'] == 'mock_call_enter' and r['data']['step'] == 10)
        rows.pop(index); self.reject(numbered(rows))
        rows = deepcopy(self.g['submit_throw']); rows = rows[:next(i for i, r in enumerate(rows) if r['kind'] == 'mock_call_enter' and r['data']['step'] == 10)+1]
        r = self.reject(rows)
        self.assertEqual(r['model']['current_item']['outcome'], 'dispatch_unknown')

    def test_entry_ttl_context_and_wrong_rva(self):
        rows = self.g['dispatched']
        ix = next(i for i, r in enumerate(rows) if r['kind'] == 'mock_call_enter' and r['data']['step'] == 10)
        for key, value in (('uptime_ms', 70000), ('context', 0x200080008), ('slot_nonnull', False), ('rva', 0x14ca2d0)):
            changed = deepcopy(rows); changed[ix]['data'][key] = value; self.reject(changed)

    def test_same_stamp_change_and_identity_alias_rejected(self):
        rows = self.g['dispatched']; ix = next(i for i, r in enumerate(rows) if r['kind'] == 'core_event')
        for key, value in rows[ix]['data']['event']['stamp'].items():
            changed = deepcopy(rows); changed[ix]['data']['event']['stamp'][key] = value+1; self.reject(changed)
        for key in ('pid', 'creation_filetime'):
            changed = deepcopy(rows); changed[ix]['data']['event']['identity'][key] = float(changed[ix]['data']['event']['identity'][key]); self.reject(changed)

    def test_unknown_and_actual_origin_are_never_accepted(self):
        for field, value in (('origin', 'actual_host'), ('kind', 'unknown_event')):
            r = deepcopy(self.g['dispatched']); r[3][field] = value; self.reject(r)
        r = deepcopy(self.g['dispatched']); r[0]['data']['preflight_assertions'] = [True, True, 1]; self.reject(r)

    def test_reader_budget_duplicates_and_nonfinite(self):
        for raw in (b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b'{}', b' '*8193+b'\n', b'{}\n'*4097):
            with self.assertRaises(ValueError): p.decode(raw)
        self.reject(deepcopy(self.g['dispatched'])*5)

    def test_missing_end_and_after_complete_fail_permanently(self):
        q = p.Projection(); result = q.replay(deepcopy(self.g['dispatched'])[:-1])
        self.assertFalse(result['valid_complete_mock'])
        self.assertFalse(q.replay(deepcopy(self.g['dispatched']))['valid_complete_mock'])

    def test_terminal_typed_result_is_retained_without_permission(self):
        r = self.reject(deepcopy(self.g['submit_throw']))
        raw = r['final_typed_result_diagnostic_only']['result']
        self.assertEqual(raw['state'], 4); self.assertTrue(raw['freeze_session'])
        self.assertTrue(raw['ownership_uncertain']); self.assertGreater(raw['exception_code'], 0)
        self.assertTrue(raw['current_item']['submit_entered'])
        self.assertFalse(raw['current_item']['submit_returned'])
        self.assertEqual(raw['current_item']['outcome'], 4)

    def test_item_boolean_and_integer_meaning_not_just_type(self):
        rows = self.g['dispatched']
        for step in (6, 10):
            ix = next(i for i, r in enumerate(rows) if r['kind'] == 'core_event' and
                      r['data']['event']['kind'] == 3 and r['data']['event']['item']['step'] == step)
            for key, value in rows[ix]['data']['event']['item'].items():
                if type(value) not in (int, bool): continue
                changed = list(rows); changed[ix] = deepcopy(rows[ix])
                changed[ix]['data']['event']['item'][key] = not value if type(value) is bool else value+1
                self.reject(changed)

    def test_final_result_cannot_replace_callback_or_borrow_future_state(self):
        rows = deepcopy(self.g['dispatched'])
        ix = next(i for i, r in enumerate(rows) if r['kind'] == 'operation_result')
        rows[ix]['data']['completed_outcomes'] = [5]*5; self.reject(rows)
        rows = deepcopy(self.g['dispatched'])
        ix = next(i for i, r in enumerate(rows) if r['kind'] == 'core_event' and r['data']['event']['kind'] == 7)
        del rows[ix]; self.reject(numbered(rows))

    def test_header_list_type_and_terminal_result_type(self):
        rows = deepcopy(self.g['dispatched']); rows[0]['data']['preflight_assertions'] = (True, True, True)
        self.reject(rows)
        rows = deepcopy(self.g['submit_throw'])
        ix = next(i for i in range(len(rows)-1, -1, -1) if rows[i]['kind'] == 'operation_result')
        rows[ix]['data']['result']['current_item']['submit_entered'] = 1; self.reject(rows)


if __name__ == '__main__': unittest.main()
