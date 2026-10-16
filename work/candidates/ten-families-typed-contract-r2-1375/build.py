"""Reconcile pinned ten-family drafts with sealed trust/reduce source evidence."""
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT = 'TenFamiliesDraft/2'
INPUT_PIN_SHA = '584075a419fd235e67a0cc9f034e4218af9a8fededcbebed9c20551f292bf26c'
OLD = 'work/candidates/ten-families-public-contract-1375'
BINDINGS = 'work/candidates/favor-trust-reduce-bindings-1375'
REVIEW = 'work/review-results/favor-trust-reduce-independent-20261008a'
MAX_SOURCE = 4 * 1024 * 1024


def read(path, limit=MAX_SOURCE):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('bounded source exceeded')
    return raw


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


def verify_inputs():
    raw = read(HERE / 'input-pins.json', 65536)
    if hashlib.sha256(raw).hexdigest() != INPUT_PIN_SHA:
        raise ValueError('fixed input inventory changed')
    pins = json.loads(raw)
    if not 1 <= len(pins) <= 64:
        raise ValueError('input count')
    total = 0
    for name, pin in pins.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('input escape')
        raw = read(path)
        total += len(raw)
        if pin != {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('pinned input changed: ' + name)
        if total > 20 * 1024 * 1024:
            raise ValueError('aggregate source budget')
    return pins


def artifact_ref(pins, name, pointers):
    return {'path': name, **pins[name], 'json_pointers': pointers,
            'evidence_scope': 'sealed_static_or_offline_model_only'}


def build():
    pins = verify_inputs()
    old = json.loads(read(ROOT / OLD / 'contract.json'))
    old_review = json.loads(read(ROOT / OLD / 'review.json'))
    native = json.loads(read(ROOT / BINDINGS / 'report.json'))
    independent = json.loads(read(ROOT / REVIEW / 'report.json'))
    base = json.loads(read(ROOT / 'bridge/diplomacy_catalog.json'))
    extensions = json.loads(read(ROOT / 'bridge/diplomacy_contract_v2_bindings.json'))
    assert old['contract'] == 'TenFamiliesDraft/1'
    assert len(old['actions']) == 10
    assert old_review['restricted_static_parameter_shapes'] == 8
    assert set(old_review['unclosed_bindings']) == {'trade_favors_for_trust', 'reduce_relations_favor'}
    assert sum(row['parameter_binding_closed'] for row in old['actions'].values()) == 8
    assert native['game_sha256'] == old['game_sha256']
    assert native['closures']['trust_original_define_keys'] is True
    assert native['closures']['reduce_normal_gui_third_country_to_qword40'] is True
    assert native['closures']['trust_runtime_values_known'] is False
    assert native['closures']['actual_private_RO_capture'] is False
    assert native['closures']['reduce_GUI_generic80_is_full88'] is False
    assert independent['passed'] is True and independent['source_unchanged'] is True
    assert independent['scope']['held_process_module_image_attestation_implemented'] is False
    assert independent['candidate_report_sha256'] == pins[BINDINGS + '/report.json']['sha256']
    assert independent['candidate_contract_sha256'] == pins[BINDINGS + '/contract.py']['sha256']
    assert independent['candidate_source_index_sha256'] == pins[BINDINGS + '/source-index.json']['sha256']
    assert independent['candidate_review_sha256'] == pins[BINDINGS + '/review.json']['sha256']
    assert independent['validation_sha256'] == pins[REVIEW + '/validation.json']['sha256']

    # Inspect, never import or instantiate, the mutable formal API.
    tree = ast.parse(read(ROOT / 'bridge/diplomacy_contract_v2.py').decode('utf8'))
    schema_function = next(node for node in ast.walk(tree)
                           if isinstance(node, ast.FunctionDef) and node.name == '_schema')
    migrated = []
    for node in ast.walk(schema_function):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == 'action':
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and type(comparator.value) is str:
                    migrated.append(comparator.value)
    assert set(migrated) == {'steal_maps', 'support_rebels'}
    assert not set(old['actions']) & set(extensions['actions'])
    formal = {row['action_id']: row for row in base['actions']}
    assert len(formal) == 274

    contract = deepcopy(old)
    contract.update(contract=CONTRACT,
                    scope='isolated typed proposal; static sources only; no formal API or backend registration',
                    parameter_binding_scope='restricted_static_parameter_shape_and_source_only',
                    restricted_static_parameter_shapes=10,
                    runtime_binding_verified=False, execution_supported=False,
                    formal_protocol='EU4DIPLOMACY-CONTRACT/2 unchanged',
                    request_id_status='not_reserved')
    contract['common_limits'] += [
        'Static binding closure never proves current process/session/module/world/country identity.',
        'Loaded global values, private injected-reader output, extra-field caches and matching snapshots are not OS attestation or runtime proof.',
        'Future private binding must use authenticated current loaded country/define state and owner-thread lifetime/permission checks; no binder is implemented here.',
        'Requests remain unsupported, not reserved, not written, not queued and not submitted.',
    ]
    static_index = {'schema': 1, 'purpose': 'private_static_binding_index_not_public_input',
                    'game_sha256': old['game_sha256'], 'new_decoded_bytes': 0,
                    'runtime_verified': False, 'production_ready': False,
                    'actual_runtime_values': None, 'actions': {}}
    for name, row in contract['actions'].items():
        descriptor = row.pop('native_descriptor')
        static_index['actions'][name] = {
            'native_descriptor': descriptor,
            'evidence': [artifact_ref(pins, row['evidence']['report_path'], row['evidence']['json_pointers'])],
            'runtime_binding_verified': False,
        }
        row.update(parameter_binding_closed=True,
                   parameter_binding_status='restricted_static_shape_and_source_only',
                   parameter_binding_scope='restricted_static_parameter_shape_and_source_only',
                   static_binding_index='static-binding-index.json#/actions/' + name,
                   runtime_binding_verified=False, execution_supported=False,
                   production_ready=False, native_legality_verified=False,
                   live_identity_resolved=False)
    trust = contract['actions']['trade_favors_for_trust']
    trust.update(binding_note='Exactly one native factory step from two loaded signed int32 define globals; caller supplies actor/target only. No caller favors, amount, quantity, trust_points, or stock 10/5 fallback. Arbitrary GUI multi-step amounts are outside this draft.',
                 private_binding_requirements={
                     'source_kind': 'two native loaded signed int32 globals',
                     'define_keys': ['NDefines.NDiplomacy.INCREASE_TRUST_COST',
                                     'NDefines.NDiplomacy.INCREASE_TRUST_AMOUNT'],
                     'cost_encoding': 'observed cost integer multiplied by 1000 only when signed32 encoding is supported',
                     'amount_encoding': 'observed amount integer retained as trust points',
                     'caller_quantity_override': False, 'stock_value_fallback': False,
                     'current_values_observed': False, 'private_OS_reader_implemented': False,
                     'cached_values_are_runtime_proof': False,
                     'supported_encoding_domain_is_native_legality': False,
                     'future_checks': ['authenticated held process/module/exact image/session',
                                       'two exact adjacent int32 captures with context rechecks',
                                       'owner-thread construction and clone/extra-field/date recheck',
                                       'full permissions, costs, lifetime and persistent dispatch'],
                 })
    trust_index = static_index['actions']['trade_favors_for_trust']
    trust_index['evidence'] += [artifact_ref(pins, BINDINGS + '/report.json',
        ['/facts/lua_load_order', '/facts/lua_integer_conversion', '/facts/trust_units',
         '/facts/trust_human_adjustment', '/facts/gui_preview_and_send']),
        artifact_ref(pins, REVIEW + '/report.json', ['/tests', '/scope'])]
    for field, key, rva, units in zip(trust_index['native_descriptor']['derived_fields'],
            ('INCREASE_TRUST_COST', 'INCREASE_TRUST_AMOUNT'),
            ('0x233db7c', '0x233db80'), ('favor_milli', 'integer_trust_points')):
        field.update(native_source_kind='loaded_define_signed_int32_global',
                     native_global_rva=rva, define_key='NDefines.NDiplomacy.' + key,
                     units=units, live_value_observed=False,
                     public_parameter=None, fallback_implemented=False,
                     actual_runtime_value=None)
    reduce = contract['actions']['reduce_relations_favor']
    reduce.update(binding_note='Normal human GUI static country selection is closed. third_country is a public country TAG; a future authenticated loader/private country resolver must obtain its current complete country handle. The injected-reader model accepts already supplied handles and is not a TAG-to-live-identity implementation.',
                  normal_parameterized_caller_closed=True,
                  normal_parameterized_caller_kind='normal human GUI static evidence',
                  private_binding_requirements={
                      'public_selector': 'third_country ASCII country TAG',
                      'native_representation': 'current complete unsigned 64-bit country handle',
                      'resolution_source': 'authenticated current loaded country registry plus private resolver',
                      'private_TAG_to_live_handle_resolver_implemented': False,
                      'injected_full_handle_model_implemented': True,
                      'gui_selection_chain_static_verified': True,
                      'actor_target_third_distinct': True,
                      'cached_handle_is_runtime_proof': False,
                      'ABA_excluded_by_matching_samples': False,
                      'future_checks': ['current full country identity/generation and bounded country database',
                                        'actor/target/third distinct current countries',
                                        'repeat pointer/full-handle resolution and final context/date/player checks',
                                        'owner-thread legality/preview/lifetime and owned command handoff'],
                  })
    reduce_index = static_index['actions']['reduce_relations_favor']
    reduce_index['native_descriptor']['derived_fields'][0].update(
        normal_selection_closed=True, normal_selection_kind='human GUI static path',
        live_resolution_implemented=False)
    reduce_index['evidence'] += [artifact_ref(pins, BINDINGS + '/report.json',
        ['/facts/reduce_dialog_dispatch', '/facts/reduce_selection_full_handle',
         '/facts/gui_preview_and_send', '/facts/gui_independent_original_lifetime']),
        artifact_ref(pins, REVIEW + '/report.json', ['/tests', '/scope'])]
    reduce_index.update(gui_selection_chain=['country+0x20 QWORD full handle', 'dialog+0x210', 'action+0x40'],
                        gui_refresh_slot='0x80 mutable text sink / false mode',
                        independent_AI_full_preview_slot='0x88 NULL sink / false mode',
                        normal_wrapper_submit_target='0x14ca210 static path only; no call permission')

    examples = []
    extra = {'sell_province': {'province_id': 183, 'price_integer': 100},
             'enforce_peace': {'opposing_country': 'POR'},
             'threaten_war': {'province_id': 183, 'taker_country': 'FRA'},
             'reduce_relations_favor': {'third_country': 'POR'}}
    for index, name in enumerate(sorted(contract['actions']), 1):
        examples.append({'contract': CONTRACT, 'request_id': 'ten-draft-' + str(index),
                         'action_id': name, 'parameters': {'actor': 'FRA', 'target': 'ENG', **extra.get(name, {})}})
    example_doc = {'contract': CONTRACT, 'scope': 'syntactic request examples; no country/province existence or permission implied',
                   'expected_status': 'unsupported', 'request_id_status': 'not_reserved', 'requests': examples}
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
              'title': 'TenFamiliesDraft/2 isolated request shape only', 'oneOf': []}
    for name, row in sorted(contract['actions'].items()):
        schema['oneOf'].append({'type': 'object', 'additionalProperties': False,
            'required': ['contract', 'request_id', 'action_id', 'parameters'],
            'properties': {'contract': {'const': CONTRACT}, 'action_id': {'const': name},
                           'request_id': {'type': 'string', 'minLength': 1, 'maxLength': 96,
                                          'pattern': '^[A-Za-z0-9_.:-]+$'},
                           'parameters': deepcopy(row['parameters'])},
            'x-cross-field-constraints': deepcopy(row['constraints'])})
    delta = {'schema': 1, 'from_contract': 'TenFamiliesDraft/1', 'to_contract': CONTRACT,
             'public_parameter_shapes_unchanged_from_previous_draft': True,
             'restricted_static_parameter_shapes_before': 8,
             'restricted_static_parameter_shapes_after': 10,
             'live_parameter_bindings_after': 0, 'production_executable_actions_after': 0,
             'runtime_verified': False, 'production_ready': False, 'actions': {}}
    difference = {'schema': 1, 'formal_protocol': 'EU4DIPLOMACY-CONTRACT/2',
                  'draft_contract': CONTRACT, 'formal_API_modified': False,
                  'formal_schema_special_cases': sorted(migrated),
                  'formal_ten_typed_extensions_present': 0,
                  'application_status': 'proposal_only_requires_separate_versioned_formal_API_change',
                  'automatic_legacy_migration': False, 'actions': {}}
    for name, row in contract['actions'].items():
        previous = old['actions'][name]
        assert previous['parameters'] == row['parameters']
        delta['actions'][name] = {
            'parameter_shape_changed': False,
            'static_binding_before': previous['parameter_binding_closed'],
            'static_binding_after': True,
            'native_descriptor_moved_to_private_static_index': True,
            'runtime_binding_verified': False, 'execution_supported': False,
            'updated_source_binding': name in ('trade_favors_for_trust', 'reduce_relations_favor'),
        }
        formal_schema = formal[name]['parameters']
        draft_schema = row['parameters']
        old_names = set(formal_schema['properties'])
        new_names = set(draft_schema['properties'])
        notes = {'sell_province': 'Replace floating price with explicit bounded whole-currency price_integer; no automatic rounding/unit conversion.',
                 'enforce_peace': 'Replace war_id/defender with explicit opposing_country role; requires private current-war relationship checks, no identifier alias.',
                 'threaten_war': 'Add explicit taker_country==actor; no silent actor insertion; preserve local+80 versus unclosed normal full+88 evidence.',
                 'trade_favors_for_trust': 'Remove legacy favors for a versioned pair-only one-native-step intent; never silently discard favors or infer stock 10/5.',
                 'reduce_relations_favor': 'Keep third_country TAG syntax; add static normal GUI source and private current full-handle resolution requirements.'}
        difference['actions'][name] = {
            'formal_parameters': deepcopy(formal_schema), 'draft_parameters': deepcopy(draft_schema),
            'added_fields': sorted(new_names - old_names), 'removed_fields': sorted(old_names - new_names),
            'schema_changed': formal_schema != draft_schema,
            'migration_note': notes.get(name, 'Pair-only shape retained; native dynamic result/legality/execution remains unresolved.'),
            'formal_typed_binding_present': False, 'execution_supported': False,
        }
    assert sum(row['schema_changed'] for row in difference['actions'].values()) == 4
    return {'contract.json': contract, 'schema.json': schema,
            'request-examples.json': example_doc, 'static-binding-index.json': static_index,
            'contract-delta.json': delta, 'formal-api-diff.json': difference}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    artifacts = build()
    hashes = {}
    for name, value in artifacts.items():
        raw = canonical(value)
        path = HERE / name
        if args.check:
            if read(path, 128 * 1024) != raw:
                raise ValueError('derived artifact changed: ' + name)
        else:
            with path.open('xb') as stream:
                stream.write(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    print(json.dumps({'check': args.check, 'artifacts': hashes,
                      'families': 10, 'static_shapes': 10,
                      'runtime_bindings': 0, 'execution_supported': False}))


if __name__ == '__main__':
    main()
