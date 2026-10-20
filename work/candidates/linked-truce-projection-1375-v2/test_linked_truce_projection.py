"""Only new header61 delta boundaries; no old suite or process observation."""
import copy
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
module = types.ModuleType('_linked_delta_tests')
module.__file__ = str(HERE / 'linked_truce_projection.py')
raw = Path(module.__file__).read_bytes()
assert 0 < len(raw) < 40000
exec(compile(raw, module.__file__, 'exec'), module.__dict__)


def facts():
    return dict(actor_handle='0x10000bd00524f50', target_handle='0x100007e004c524f',
        target_linked_handle='0x100007a00415246', actor_linked_handle='0x2d2d2d',
        dependency_guarded=True, dependency_key='march', definition_byte_11a=1,
        direct_pair_cache_flag_set=False, loaded_K=15,
        definition_header={'0x60': 0, '0x61': 1, '0x62': 0, '0x63': 0})


class Header61Delta(unittest.TestCase):
    def expect_unknown(self, item):
        result = module.project_facts(item)
        self.assertIs(result['supported'], False)
        self.assertIsNone(result['selected_native_return_projection'])
        self.assertIsNone(result['path'])

    def test_captured_shape_has_new_path_without_linked_cache(self):
        item = facts()
        before = copy.deepcopy(item)
        result = module.project_facts(item)
        self.assertIs(result['supported'], True)
        self.assertEqual(result['path'], 'D_independent_actor_header61_nonzero')
        self.assertIs(result['selected_native_return_projection'], False)
        self.assertEqual(item, before)
        self.assertNotIn('actor_linked_cache_flag_set', item)

    def test_direct_cache_true_is_successfully_projected_true(self):
        item = facts()
        item['direct_pair_cache_flag_set'] = True
        result = module.project_facts(item)
        self.assertIs(result['supported'], True)
        self.assertIs(result['selected_native_return_projection'], True)

    def test_unconsumed_other_header_bytes_do_not_force_unknown(self):
        item = facts()
        item['definition_header'].update({'0x60': 255, '0x62': 17, '0x63': 9})
        self.assertIs(module.project_facts(item)['supported'], True)

    def test_nonzero_other_byte_with_zero61_remains_unknown(self):
        item = facts()
        item['definition_header'].update({'0x61': 0, '0x60': 1})
        self.expect_unknown(item)

    def test_boolean_header_is_not_a_raw_byte(self):
        item = facts()
        item['definition_header']['0x61'] = True
        self.expect_unknown(item)

    def test_K16_requires_unresolved_cleanup(self):
        item = facts()
        item['loaded_K'] = 16
        self.expect_unknown(item)

    def test_actor_dependency_does_not_prove_second_getter_NULL(self):
        item = facts()
        item['actor_linked_handle'] = item['target_linked_handle']
        self.expect_unknown(item)

    def test_missing_bilateral_typed_profile_is_unknown(self):
        item = facts()
        item['dependency_guarded'] = False
        self.expect_unknown(item)

    def test_different_generation_at_same_slot_cannot_choose_call_branch(self):
        item = facts()
        item['target_linked_handle'] = '0x20000bd00415246'
        self.expect_unknown(item)

    def test_missing_direct_cache_never_defaults_to_false(self):
        item = facts()
        del item['direct_pair_cache_flag_set']
        self.expect_unknown(item)

    def test_partial_projection_does_not_supply_completion_authority(self):
        base = module.base_result('status')
        self.assertTrue(all(base[key] is False for key in (
            'actual_native_predicate_evaluated', 'selected_effect_verified', 'peace_completion_verified',
            'expiry_verified', 'request_effect_verified', 'native_ready', 'lifetime_lease', 'atomic_snapshot')))
        self.assertTrue(all(base[key] == 0 for key in (
            'native_game_calls', 'requests_published', 'game_fields_written', 'hooks_installed', 'saves', 'reloads')))

    def test_draft_status_refuses_before_library_or_process_construction(self):
        touched = []
        def forbidden(_):
            touched.append(True)
            raise AssertionError('No library/process construction allowed in draft')
        selection = dict(pid=80340, creation='01dd5c075fcf8c26', actor='POR', target='ORL')
        result = module.run('status', selection, library_factory=forbidden)
        self.assertEqual(touched, [])
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['selected_native_return_projection'])
        self.assertIn('production manifest required', result['errors'][0]['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
