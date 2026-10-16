"""Pure synthetic decoded-query envelopes; no process, native code or fixture writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
import observer

CONTRACT = (Path(__file__).parent/'static-contract.json').read_bytes()
STATIC = json.loads(CONTRACT)


def country_handle(tag, slot):
    return f'0x{0x0100000000000000 | slot << 32 | int.from_bytes(tag.encode(), "little"):016x}'


def vector(owner, offset, entries=None):
    entries = entries or []
    return {'owner': owner, 'container_offset': offset, 'data': '0x650000' if entries else None,
            'count': len(entries), 'entries': entries}


def fixture():
    a, b = country_handle('FRA', 1), country_handle('ENG', 2)
    boolean = {'pointer': '0x620000', 'raw_type': 0, 'storage_byte': 1}
    government = {'instance': '0x610000', 'definition': '0x618000',
                  'variant_170': boolean, 'variant_110': dict(boolean, pointer='0x621000')}
    goal = {'kind': 'take_colony', 'pointer': '0x710000', 'vtable_rva': '0x1d1fd90',
        'methods': dict(observer.GOAL_METHODS), 'definition': '0x720000', 'province_index': 1,
        'province': '0x810000', 'province_marker': 1, 'game_provinces_begin': '0x900000',
        'game_provinces_end': '0x900050', 'game_province_blocks': '0xa00000',
        'province_block_field_address': hex(0xa00000 + 0x2e10 + 0x560), 'province_block_pointer': '0x810000',
        'conditions': {offset: vector('0x720000', offset) for offset in ('0x50','0x140','0x288','0x378')}}
    snapshot = {'roots': {'game':'0x200000','database':'0x210000','country_array':'0x220000','country_count':3,'raw_date':56456976},
        'countries': [{'handle':a,'slot':1,'tag':'FRA','pointer':'0x300000','government':deepcopy(government)},
                      {'handle':b,'slot':2,'tag':'ENG','pointer':'0x400000','government':deepcopy(government)}],
        'relations': [
            {'owner_handle':a,'counterpart_handle':b,'root':'0x510000','data':'0x511000','count':1,
             'entries':[{'country_slot':2,'war_pointer':'0x700000'}]},
            {'owner_handle':b,'counterpart_handle':a,'root':'0x520000','data':'0x521000','count':1,
             'entries':[{'country_slot':1,'war_pointer':'0x700000'}]}],
        'war': {'pointer':'0x700000','vtable_rva':'0x100000','side_a':{'begin':'0x701000','end':'0x701008','handles':[a]},
                'side_b':{'begin':'0x702000','end':'0x702008','handles':[b]},'goal':goal},
        'caches': {'nogovernment':None,'secondary':None,'goal_fallback':'0x730000','dependency_registry':'0x740000'},
        'dependency': {'definition':'0x750000','conditions':vector('0x750000','0x40')},
        'tls': {'thread_id':123,'gate_a':0,'gate_b':0,'gs58_array':'0xb00000','slot0_pointer':'0xb10000',
                'module_index':0,'indexed_pointer':'0xb10000','slot0_initialized_byte':1,'slot0_gate_byte':1,'indexed_initialized_byte':1},
        'paused_observed':True}
    return {'schema_version':1,'purpose':'peace_preconditions_offline_queries_v1','source_kind':'synthetic',
        'exe_sha256':observer.EXE_SHA,'static_contract_sha256':observer.CONTRACT_SHA,
        'identity':{'pid':1,'creation_filetime':'0100000000000001','module_base':'0x140000000',
                    'image_size':STATIC['pe']['image_size'],'image_timestamp':STATIC['pe']['timestamp']},
        'binding':{'actor_handle':a,'recipient_handle':b,'direction':'demand'},
        'passes':[{'sequence':0,'started_tick':10,'ended_tick':11,'snapshot':deepcopy(snapshot)},
                  {'sequence':1,'started_tick':12,'ended_tick':13,'snapshot':deepcopy(snapshot)}]}


def encode(value): return (json.dumps(value, sort_keys=True)+'\n').encode()


def decode(value): return observer.parse(encode(value), CONTRACT)


def mutate_both(value, mutate):
    for capture in value['passes']: mutate(capture['snapshot'])


class Tests(unittest.TestCase):
    def test_recognized_graph_never_authorizes_constructor(self):
        result = decode(fixture())
        self.assertTrue(result['structural_query_validation_passed'])
        self.assertTrue(result['selected_fields_equal_two_pass'])
        self.assertEqual(result['observation']['selected_province_condition_offsets'], ['0x50','0x140'])
        for name in ('parameter_constructor_authorized','parameter_selftest_ready','condition_purity_verified',
                     'constructor_purity_verified','engine_thread_provenance_verified','world_epoch_verified','execution_verified','production_ready'):
            self.assertIs(result[name], False)

    def test_concede_reverses_taker_without_relabeling_war_sides(self):
        data=fixture();data['binding']['direction']='concede'
        result=decode(data)['observation']
        self.assertEqual(result['taker_handle'],data['binding']['recipient_handle'])
        self.assertEqual(result['taker_side'],'B')
        self.assertEqual(result['selected_province_condition_offsets'],['0x288','0x378'])

    def test_duplicate_ambiguous_war_index_is_rejected(self):
        data=fixture()
        def mutate(s):
            row=s['relations'][0];row['count']=2;row['entries']*=2
        mutate_both(data,mutate)
        with self.assertRaises(ValueError):decode(data)

    def test_war_index_key_is_not_an_arbitrary_war_id(self):
        for key in (56456976,-1,3,True,2.0):
            data=fixture();mutate_both(data,lambda s:s['relations'][0]['entries'][0].update(country_slot=key))
            with self.subTest(key=key),self.assertRaises(ValueError):decode(data)

    def test_missing_wrong_direction_or_different_reciprocal_war(self):
        for mutate in (lambda s:s['relations'].pop(),lambda s:s['relations'][1].update(owner_handle=s['relations'][0]['owner_handle']),
                       lambda s:s['relations'][1]['entries'][0].update(war_pointer='0x780000')):
            data=fixture();mutate_both(data,mutate)
            with self.assertRaises(ValueError):decode(data)

    def test_side_handle_conflicts_and_incomplete_inventory(self):
        for mutate in (lambda s:s['war']['side_b'].update(handles=s['war']['side_a']['handles']),
                       lambda s:s['war']['side_a'].update(end='0x701010'),lambda s:s['countries'].pop(),
                       lambda s:s['countries'][0].update(tag='POR'),lambda s:s['countries'][0].update(slot=2)):
            data=fixture();mutate_both(data,mutate)
            with self.assertRaises(ValueError):decode(data)

    def test_government_offsets_are_170_and_110_not_138_or_condition_object(self):
        data=fixture()
        def mutate(s):
            g=s['countries'][0]['government'];g['variant_138']=g.pop('variant_170')
        mutate_both(data,mutate)
        with self.assertRaises(ValueError):decode(data)
        paths=STATIC['government_variant_paths']
        self.assertEqual(paths['instance_variant_pointer_offsets'],['0x170','0x110'])
        self.assertEqual(paths['nogovernment_variant_pointer_offsets'],['0x1b0','0x150'])
        self.assertIs(paths['is_script_condition_pointer'],False)

    def test_absent_government_stays_missing_despite_global_cache(self):
        data=fixture()
        def mutate(s):
            s['caches']['nogovernment']='0x600000'
            s['countries'][0]['government']=dict.fromkeys(('instance','definition','variant_170','variant_110'))
        mutate_both(data,mutate)
        self.assertIn('government_missing_requires_fallback:FRA',decode(data)['observation']['gaps'])

    def test_variant_negative_type_zero_and_unknown_are_distinguished(self):
        data=fixture();mutate_both(data,lambda s:s['countries'][0]['government']['variant_170'].update(raw_type=-1))
        self.assertNotIn('unreviewed_variant_type:FRA:variant_170',decode(data)['observation']['gaps'])
        mutate_both(data,lambda s:s['countries'][0]['government']['variant_170'].update(raw_type=1))
        self.assertIn('unreviewed_variant_type:FRA:variant_170',decode(data)['observation']['gaps'])

    def test_complete_tls_gate_truth_table_catches_old_single_flag_summary(self):
        for a,b,active in ((0,0,True),(0,1,True),(1,0,False),(1,1,True),(255,0,False)):
            data=fixture();mutate_both(data,lambda s:s['tls'].update(gate_a=a,gate_b=b))
            self.assertIs(decode(data)['observation']['tls_branch_would_be_entered'],active)
        self.assertEqual(STATIC['tls']['gate_a_rva'],'0x233ff94')

    def test_tls_uninitialized_and_index_divergence_are_not_preheated(self):
        data=fixture();mutate_both(data,lambda s:s['tls'].update(slot0_initialized_byte=0,indexed_initialized_byte=0))
        self.assertIn('native_tls_initializer_would_run',decode(data)['observation']['gaps'])
        mutate_both(data,lambda s:s['tls'].update(module_index=1,indexed_pointer='0xb20000'))
        self.assertIn('caller_index_zero_differs_from_initializer_index',decode(data)['observation']['gaps'])

    def test_partial_tls_or_zero_index_alias_inconsistency_rejected(self):
        for change in ({'gs58_array':None},{'indexed_pointer':'0xb20000'},{'indexed_initialized_byte':0}):
            data=fixture();mutate_both(data,lambda s:s['tls'].update(change))
            with self.assertRaises(ValueError):decode(data)

    def test_goal_fallback_registry_and_validity_are_not_dependency_registry(self):
        self.assertEqual(STATIC['goal']['fallback_global_rva'],'0x2340030')
        self.assertEqual(STATIC['goal']['dependency_registry_global_rva'],'0x233ffd8')
        data=fixture()
        def mutate(s):s['war']['goal'].update(province_marker=0,conditions=None)
        mutate_both(data,mutate)
        result=decode(data)['observation']
        self.assertIsNone(result['selected_province_condition_offsets'])
        self.assertIn('effective_goal_is_fallback_virtual_family_unreviewed',result['gaps'])

    def test_goal_invalid_cannot_smuggle_original_definition_conditions(self):
        data=fixture();mutate_both(data,lambda s:s['war']['goal'].update(province_marker=0))
        with self.assertRaises(ValueError):decode(data)

    def test_goal_province_index_arithmetic_and_method_family(self):
        for change in ({'province_block_field_address':'0xa03378'},{'province_index':-1},{'vtable_rva':'0x1d1fd98'}):
            data=fixture();mutate_both(data,lambda s:s['war']['goal'].update(change))
            with self.assertRaises(ValueError):decode(data)

    def test_unknown_goal_class_is_inventory_not_faked_getter(self):
        data=fixture();mutate_both(data,lambda s:s['war'].update(goal={'kind':'unrecognized','pointer':'0x710000','vtable_rva':'0x1d1fd98'}))
        self.assertIn('goal_dynamic_class_unreviewed',decode(data)['observation']['gaps'])

    def test_concrete_conditions_record_virtual30_without_evaluating_it(self):
        data=fixture();entry={'object':'0xc00000','vtable_rva':'0x1c38158','method30_rva':'0x123000'}
        mutate_both(data,lambda s:s['war']['goal']['conditions'].update({'0x50':vector('0x720000','0x50',[entry])}))
        result=decode(data)
        self.assertEqual(result['observation']['condition_instance_count'],1)
        self.assertIn('concrete_condition_virtual30_bodies_unreviewed',result['observation']['gaps'])
        self.assertIs(result['condition_purity_verified'],False)

    def test_condition_count_owner_offset_and_alias_mismatch(self):
        mutations=(lambda s:s['dependency']['conditions'].update(count=65),
            lambda s:s['dependency']['conditions'].update(owner='0x760000'),
            lambda s:s['dependency']['conditions'].update(container_offset='0x48'))
        for mutate in mutations:
            data=fixture();mutate_both(data,mutate)
            with self.assertRaises(ValueError):decode(data)

    def test_aliased_condition_instance_cannot_change_virtual_identity(self):
        data=fixture()
        def mutate(s):
            first={'object':'0xc00000','vtable_rva':'0x1c38158','method30_rva':'0x123000'}
            second=dict(first,method30_rva='0x124000')
            s['war']['goal']['conditions']['0x50']=vector('0x720000','0x50',[first])
            s['dependency']['conditions']=vector('0x750000','0x40',[second])
        mutate_both(data,mutate)
        with self.assertRaises(ValueError):decode(data)

    def test_strict_scalars_reject_equal_bool_float_identity_values(self):
        for key,value in (('pid',True),('pid',1.0),('image_size',float(STATIC['pe']['image_size'])),('creation_filetime',1)):
            data=fixture();data['identity'][key]=value
            with self.assertRaises(ValueError):decode(data)
        for path in ('country_count','raw_date'):
            for kind in (float,bool):
                data=fixture();mutate_both(data,lambda s:s['roots'].update({path:kind(s['roots'][path])}))
                with self.assertRaises(ValueError):decode(data)
        for value in (1,1.0):
            data=fixture();mutate_both(data,lambda s:s.update(paused_observed=value))
            with self.assertRaises(ValueError):decode(data)

    def test_missing_unknown_and_forged_authorization_keys(self):
        for mutate in (lambda d:d.update(parameter_constructor_authorized=True),lambda d:d['passes'][0]['snapshot']['roots'].pop('country_count'),
                       lambda d:d.update(source_kind='live_verified'),lambda d:d['binding'].update(direction='force')):
            data=fixture();mutate(data)
            with self.assertRaises(ValueError):decode(data)

    def test_second_pass_change_and_overlap_are_rejected(self):
        for mutate in (lambda d:d['passes'][1]['snapshot']['roots'].update(raw_date=56456977),
                       lambda d:d['passes'][1]['snapshot']['roots'].update(game='0x280000'),
                       lambda d:d['passes'][1].update(started_tick=11),lambda d:d['passes'][1].update(sequence=True)):
            data=fixture();mutate(data)
            with self.assertRaises(ValueError):decode(data)

    def test_static_contract_cannot_be_self_consistently_replaced(self):
        data=fixture();bad=deepcopy(STATIC);bad['goal']['fallback_global_rva']='0x233ffd8';raw=encode(bad)
        data['static_contract_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):observer.parse(encode(data),raw)

    def test_bounded_json_duplicate_keys_float_and_infinite_values_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":1.0}',b'{"a":NaN}',b'{"a":Infinity}',b' '* (observer.MAX_FILE+1),b'{'):
            with self.assertRaises(ValueError):observer.parse(raw,CONTRACT)

    def test_false_pause_and_equal_snapshots_never_grant_execution(self):
        data=fixture();mutate_both(data,lambda s:s.update(paused_observed=False))
        result=decode(data)
        self.assertIs(result['parameter_constructor_authorized'],False)
        self.assertIs(result['tls_source_authenticated'],False)
        self.assertIs(result['object_lifetime_verified'],False)


if __name__ == '__main__': unittest.main(verbosity=2)
