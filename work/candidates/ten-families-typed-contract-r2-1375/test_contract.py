"""Small structural/semantic boundary suite for the new isolated proposal."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from catalog import actions, describe, request, request_json, validate

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


class Tests(unittest.TestCase):
    def test_all_ten_examples_remain_unsupported_nonreserved(self):
        examples = read('request-examples.json')['requests']
        schema = read('schema.json')
        self.assertEqual(len(examples), 10)
        self.assertEqual(len(schema['oneOf']), 10)
        self.assertEqual(sorted(row['action_id'] for row in examples), actions())
        for payload in examples:
            with self.subTest(action=payload['action_id']):
                response = request_json(json.dumps(payload).encode('utf8'))
                self.assertEqual(response['status'], 'unsupported')
                self.assertEqual(response['request_id_status'], 'not_reserved')
                self.assertTrue(response['parameter_binding_closed'])
                self.assertEqual(response['parameter_binding_scope'], 'restricted_static_parameter_shape_and_source_only')
                for field in ('queued', 'submitted', 'request_written', 'native_called',
                              'execution_supported', 'execution_verified', 'runtime_verified',
                              'runtime_binding_verified', 'native_legality_verified',
                              'live_identity_resolved', 'effect_verified', 'production_ready'):
                    self.assertIs(response[field], False)

    def test_trust_and_resource_exchanges_reject_any_caller_quantity(self):
        pair = {'actor': 'FRA', 'target': 'ENG'}
        for action in ('trade_favors_for_trust', 'trade_favors_for_gold',
                       'trade_favors_for_men', 'trade_favors_for_sailors', 'trade_favors_for_war_prep'):
            self.assertEqual(validate(action, pair)['parameters'], pair)
            for field in ('favors', 'amount', 'quantity', 'trust_points', 'favor_milli',
                          'cost_units', 'trust_int', 'loaded_cost', 'loaded_amount'):
                with self.subTest(action=action, field=field), self.assertRaises(ValueError):
                    validate(action, {**pair, field: 10})

    def test_strict_country_tag_and_distinct_third_country(self):
        class StringLike(str):
            pass
        for third in ('FRA', 'ENG', 'por', 'ＰＯＲ', 'POR ', '---',
                      StringLike('POR'), 0x0100008800524f50, True):
            with self.subTest(third=repr(third)), self.assertRaises(ValueError):
                validate('reduce_relations_favor', {'actor': 'FRA', 'target': 'ENG', 'third_country': third})
        self.assertFalse(validate('reduce_relations_favor',
                         {'actor': 'FRA', 'target': 'ENG', 'third_country': 'POR'})['live_identity_resolved'])

    def test_integer_units_boundaries_and_exact_python_types(self):
        class IntLike(int):
            pass
        good = {'actor': 'FRA', 'target': 'ENG', 'province_id': 2147483647, 'price_integer': 2147483}
        self.assertEqual(validate('sell_province', good)['parameters'], good)
        for field, values in (('price_integer', (True, 1.0, -1, 2147484, IntLike(100))),
                              ('province_id', (True, 183.0, 0, 2147483648, IntLike(183)))):
            for bad in values:
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    validate('sell_province', {**good, field: bad})
        self.assertEqual(validate('sell_province', {**good, 'price_integer': 0})['parameters']['price_integer'], 0)

    def test_private_addresses_are_metadata_and_never_public_parameters(self):
        contract = read('contract.json')
        index = read('static-binding-index.json')
        examples = {row['action_id']: row['parameters'] for row in read('request-examples.json')['requests']}
        for action, row in contract['actions'].items():
            self.assertNotIn('native_descriptor', row)
            params = examples[action]
            for field in ('rva', 'pointer', 'full_handle', 'state', 'value', 'envoy_id',
                          'thread', 'TTL', 'cancel', 'native_token', 'module'):
                with self.subTest(action=action, field=field), self.assertRaises(ValueError):
                    validate(action, {**params, field: 0x233db7c})
        fields = index['actions']['trade_favors_for_trust']['native_descriptor']['derived_fields']
        self.assertEqual([row['native_global_rva'] for row in fields], ['0x233db7c', '0x233db80'])
        self.assertTrue(all(row['public_parameter'] is None and row['actual_runtime_value'] is None for row in fields))

    def test_versioned_formal_migration_is_explicit_and_not_automatic(self):
        difference = read('formal-api-diff.json')
        self.assertEqual(sum(row['schema_changed'] for row in difference['actions'].values()), 4)
        self.assertEqual(difference['actions']['trade_favors_for_trust']['removed_fields'], ['favors'])
        self.assertEqual(difference['actions']['enforce_peace']['removed_fields'], ['defender', 'war_id'])
        old_inputs = [('sell_province', {'province_id': 183, 'price': 100}),
                      ('enforce_peace', {'war_id': 'war1', 'defender': 'POR'}),
                      ('threaten_war', {'province_id': 183}),
                      ('trade_favors_for_trust', {'favors': 10})]
        for action, extra in old_inputs:
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate(action, {'actor': 'FRA', 'target': 'ENG', **extra})
        with self.assertRaises(ValueError):
            validate('threaten_war', {'actor': 'FRA', 'target': 'ENG', 'province_id': 183, 'taker_country': 'POR'})

    def test_duplicate_wire_keys_extra_evidence_and_old_version_rejected(self):
        raw = b'{"contract":"TenFamiliesDraft/2","request_id":"d1","action_id":"trade_favors_for_trust","parameters":{"actor":"FRA","target":"ENG","target":"POR"}}'
        with self.assertRaises(ValueError):
            request_json(raw)
        payload = read('request-examples.json')['requests'][0]
        for override in ({'contract': 'TenFamiliesDraft/1'}, {'native_evidence': {}},
                         {'runtime_verified': True}, {'request_id': True}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                request({**payload, **override})
        with self.assertRaises(ValueError):
            request_json(bytes(4097))

    def test_new_static_closure_never_changes_runtime_or_resolver_proof(self):
        delta = read('contract-delta.json')
        self.assertEqual((delta['restricted_static_parameter_shapes_before'], delta['restricted_static_parameter_shapes_after']), (8, 10))
        self.assertEqual(delta['live_parameter_bindings_after'], 0)
        trust = describe('trade_favors_for_trust')['private_binding_requirements']
        self.assertFalse(trust['current_values_observed'])
        self.assertFalse(trust['private_OS_reader_implemented'])
        self.assertFalse(trust['cached_values_are_runtime_proof'])
        self.assertFalse(trust['stock_value_fallback'])
        reduce = describe('reduce_relations_favor')['private_binding_requirements']
        self.assertTrue(reduce['gui_selection_chain_static_verified'])
        self.assertFalse(reduce['private_TAG_to_live_handle_resolver_implemented'])
        self.assertFalse(reduce['cached_handle_is_runtime_proof'])
        self.assertFalse(reduce['ABA_excluded_by_matching_samples'])
        self.assertFalse(describe('threaten_war')['normal_full_preview_caller_closed'])
        payload = read('request-examples.json')['requests'][0]
        first = request(payload)
        payload['parameters']['target'] = 'POR'
        second = request(payload)
        self.assertNotEqual(first['parameters'], second['parameters'])
        self.assertEqual(first['request_id_status'], second['request_id_status'])


if __name__ == '__main__':
    unittest.main()
