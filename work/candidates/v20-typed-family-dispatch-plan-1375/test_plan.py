"""Structural/source-consistency tests of a plan, not native behavior tests."""
import copy
import json
from pathlib import Path
import unittest
import build_plan as build


class PlanContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = build.documents()
        cls.plan = cls.docs['plan.json']
        cls.registry = cls.docs['abi-registry.json']

    def test_exact_counts_and_alias_roles(self):
        self.assertEqual(self.plan['counts'], {'catalog_total': 274, 'catalog_static_mapped': 270,
            'lab_protocol_ids': 36, 'lab_native_families': 20, 'catalog_lab_bindings': 37,
            'formal_v2_typed_extensions': 15, 'separate_ten_family_draft': 10})
        bindings = self.plan['catalog_bindings']
        self.assertEqual(bindings['request_trade_power'], ['transfer_trade_power'])
        self.assertEqual(bindings['cancel_independence_support'], ['cancel_offered_independence_support', 'cancel_requested_independence_support'])
        self.assertEqual(len(self.plan['remaining_without_lab_binding']), 237)

    def test_every_protocol_mode_binds_exactly_once(self):
        modes = [m for f in self.registry['research_families'] for m in f['modes']]
        self.assertEqual(len(modes), 36)
        self.assertEqual(len({m['protocol_id'] for m in modes}), 36)
        self.assertEqual(sum(m['native_value'] is False for m in modes), 16)
        self.assertTrue(all(type(m['native_value']) is bool for m in modes))

    def test_full_preview_is_not_old_generic(self):
        for f in self.registry['research_families']:
            self.assertTrue(f['family_full_0x88_rva'].startswith('0x'))
            self.assertEqual(f['action_wrapper_rva'], '0x4e9930')
            self.assertEqual(f['command_gate_rva'], '0x4e8630')
            self.assertEqual(f['v17_preview_used'], 'generic_0x4e9d00_not_family_full_0x88')
            self.assertFalse(f['native_ready'])

    def test_state_and_marriage_are_not_genericized(self):
        rows = {f['token']: f for f in self.registry['research_families']}
        self.assertEqual(rows['0x2de0']['initial_state'], 2)
        self.assertTrue(all(f['initial_state'] == 0 for k, f in rows.items() if k != '0x2de0'))
        self.assertEqual(rows['0x28df']['size_bytes'], 0x68)
        self.assertEqual(rows['0x28df']['destructor_rva'], '0x4ed5b0')
        self.assertIn('String32', ' '.join(rows['0x28df']['extra_and_cancel_contract']))
        self.assertIn('unique live envoy', ' '.join(rows['0x3378']['extra_and_cancel_contract']))

    def test_subjects_never_use_pair_profile(self):
        groups = {r['group']: r for r in self.registry['supplemental_groups']}
        for name, size in [('subject_focus', 96), ('subject_toggles', 160)]:
            row = groups[name]
            self.assertEqual(row['profile_action'], 'new_command_profile_not_pair_wrapper')
            self.assertEqual(row['descriptor']['size_bytes'], size)
            self.assertIsNone(row['normal_full_preview_caller_closed'])
            self.assertIn('String32', row['extra_rule'])

    def test_ten_schemas_are_exact_sealed_proposals(self):
        source = build.parsed('work/candidates/ten-families-typed-contract-r2-1375/contract.json')['actions']
        groups = {r['group']: r for r in self.registry['supplemental_groups']}
        for name, original in source.items():
            self.assertEqual(groups[name]['public_parameters'], original['parameters'])
            self.assertFalse(groups[name]['public_parameters']['additionalProperties'])
            self.assertFalse(groups[name]['native_ready'])
        self.assertFalse(groups['threaten_war']['normal_full_preview_caller_closed'])
        self.assertNotIn('favors', groups['trade_favors_for_trust']['public_parameters']['properties'])
        self.assertNotIn('war_id', groups['enforce_peace']['public_parameters']['properties'])

    def test_no_permission_or_causal_promotion(self):
        for name in ['production_ready', 'native_ready', 'runtime_calls_made', 'profile_implementation_created',
                     'world_epoch_verified', 'strict_single_player_verified', 'historical_effects_promoted']:
            self.assertIs(self.plan[name], False)
        for group in self.plan['batch_groups']:
            self.assertIs(group['individual_effect_verified'], False)
            self.assertIn('final', group['observation'])
        for group in self.registry['supplemental_groups']:
            self.assertIs(group['production_ready'], False)
        self.assertEqual(len(self.plan['minimum_37_binding_gaps']), 8)

    def test_materialized_document_bytes_and_budgets(self):
        for name, data in self.docs.items():
            self.assertEqual((build.HERE / name).read_bytes(), build.canonical(data))
        pins = build.describe_inputs()
        self.assertLessEqual(len(pins), 64)
        self.assertLessEqual(sum(p['bytes'] for p in pins), 32*1024*1024)
        self.assertEqual(pins, json.loads((build.HERE/'input-pins.json').read_text(encoding='utf-8'))['inputs'])

if __name__ == '__main__': unittest.main()
