import copy
import unittest
import war_graph_change_oracle as oracle


def handle(tag, slot, generation=1):
    return hex((generation << 56) | (slot << 32) | int.from_bytes(tag.encode('ascii'), 'little'))


AH, TH = handle('FRA', 122), handle('ENG', 46)


def country(tag, slot, address=None, generation=1):
    return {'address': hex(address if address is not None else 0x400000 + slot*0x10000),
            'handle': handle(tag, slot, generation), 'tag': tag, 'slot': slot}


def war(address=0x30000000, attackers=None, defenders=None):
    a = copy.deepcopy(attackers if attackers is not None else [country('FRA',122)])
    d = copy.deepcopy(defenders if defenders is not None else [country('ENG',46)])
    return {'current_war_address':hex(address), 'vtable_rva':'0x1d1f768', 'marker':357,
            'started_raw_date':90, 'primary_attacker_handle':a[0]['handle'],
            'primary_defender_handle':d[0]['handle'], 'goal_pointer_raw':'0x35000000',
            'attackers':a, 'defenders':d, 'raw_outcome':0}


def view(wars=None):
    data=copy.deepcopy(wars if wars is not None else [])
    return {'schema':oracle.VIEW_SCHEMA, 'identity':{'pid':12345,'creation':'0000000000000001'},
            'world':{'game_address':'0x10000000','database_address':'0x11000000',
                     'country_table_address':'0x12000000','now_raw':100,'country_count':1380},
            'actor':country('FRA',122),'target':country('ENG',46),
            'complete_current_global_scan':True,'global_war_count':len(data),'wars':data}


class OracleTests(unittest.TestCase):
    def evaluate(self,a,b):
        out=oracle.evaluate_graph_change(a,b,AH,TH)
        self.assertTrue(all(v is False for v in out['authority'].values()))
        return out

    def unknown(self,a,b,reason=None):
        out=self.evaluate(a,b)
        self.assertEqual(out['status'],'unknown')
        self.assertIsNone(out['pattern'])
        if reason:self.assertEqual(out['failure']['reason'],reason)
        return out

    def test_empty_complete_views_are_only_empty_data_pattern(self):
        out=self.evaluate(view(),view())
        self.assertEqual(out['status'],'observed_data_pattern')
        self.assertEqual(out['pattern']['global_addresses_added_in_view'],[])
        self.assertEqual(out['pattern']['selected_pair_opposing_addresses_after'],[])

    def test_added_global_address_is_never_war_creation(self):
        out=self.evaluate(view(),view([war()]))
        self.assertEqual(out['pattern']['global_addresses_added_in_view'],['0x30000000'])
        self.assertEqual(out['pattern']['selected_pair_opposing_addresses_added_in_view'],['0x30000000'])
        self.assertFalse(out['authority']['war_creation_verified'])
        self.assertNotIn('declare_war_success',out)

    def test_removed_address_is_never_retirement_or_whitepeace(self):
        out=self.evaluate(view([war()]),view())
        self.assertEqual(out['pattern']['global_addresses_removed_in_view'],['0x30000000'])
        self.assertFalse(out['authority']['war_retirement_verified'])
        self.assertFalse(out['authority']['peace_completion_verified'])
        self.assertFalse(out['authority']['terms_verified'])

    def test_global_reorder_has_no_added_or_removed_addresses(self):
        a=war();b=war(0x31000000)
        out=self.evaluate(view([a,b]),view([b,a]))
        self.assertTrue(out['pattern']['global_order_changed'])
        self.assertEqual(out['pattern']['global_addresses_added_in_view'],[])
        self.assertEqual(out['pattern']['same_address_changes'],[])

    def test_multiple_opposing_addresses_are_independent_copied_schema_only(self):
        out=self.evaluate(view([war()]),view([war(),war(0x31000000)]))
        self.assertEqual(out['status'],'observed_data_pattern')
        self.assertEqual(len(out['pattern']['selected_pair_opposing_addresses_after']),2)
        self.assertTrue(out['pattern']['multiple_opposing_addresses_in_copied_data'])
        self.assertFalse(out['pattern']['runtime_reader_multiple_opposing_supported'])
        self.assertTrue(oracle.catalog()['frozen_war_r2_strictly_rejects_multiple_opposing_addresses'])

    def test_unrelated_global_war_does_not_change_selected_pair(self):
        other=war(0x31000000,[country('POR',189)],[country('SCO',7)])
        out=self.evaluate(view(),view([other]))
        self.assertEqual(out['pattern']['global_addresses_added_in_view'],['0x31000000'])
        self.assertEqual(out['pattern']['selected_pair_opposing_addresses_after'],[])

    def test_same_address_changed_raw_payload_is_not_object_continuity(self):
        a=view([war()]);b=copy.deepcopy(a)
        b['wars'][0].update(started_raw_date=99,goal_pointer_raw='0x36000000',raw_outcome=1)
        out=self.evaluate(a,b);change=out['pattern']['same_address_changes'][0]
        self.assertEqual(set(change['changed_raw_payload_fields']),{'started_raw_date','goal_pointer_raw','raw_outcome'})
        self.assertTrue(change['comparison_is_same_address_pattern_only'])
        self.assertFalse(change['continuous_object_identity_verified'])

    def test_same_address_identical_copies_cannot_exclude_invisible_ABA(self):
        a=view([war()]);b=copy.deepcopy(a)
        # These are exactly the data obtainable if a replacement reused all
        # copied values. No hidden event is fabricated in the copied schema.
        out=self.evaluate(a,b)
        self.assertEqual(out['pattern']['same_addresses_unchanged_in_copied_fields'],['0x30000000'])
        self.assertFalse(out['authority']['same_address_continuity_verified'])
        self.assertFalse(out['authority']['world_epoch_proven'])

    def test_same_address_member_removed_can_change_pair_without_removing_war(self):
        a=view([war(defenders=[country('ENG',46),country('POR',189)])]);b=copy.deepcopy(a)
        b['wars'][0]['defenders']=[country('POR',189)]
        b['wars'][0]['primary_defender_handle']=handle('POR',189)
        out=self.evaluate(a,b);pattern=out['pattern']
        self.assertEqual(pattern['global_addresses_removed_in_view'],[])
        self.assertEqual(pattern['selected_pair_opposing_addresses_removed_in_view'],['0x30000000'])
        self.assertEqual(pattern['same_address_changes'][0]['members']['defenders']['handles_removed_in_view'],[TH])

    def test_side_order_change_does_not_add_or_remove_members(self):
        a=view([war(attackers=[country('FRA',122),country('POR',189)])]);b=copy.deepcopy(a)
        b['wars'][0]['attackers'].reverse()
        out=self.evaluate(a,b);change=out['pattern']['same_address_changes'][0]
        self.assertTrue(change['side_order_changed']['attackers'])
        self.assertEqual(change['members']['attackers']['handles_added_in_view'],[])
        self.assertEqual(change['members']['attackers']['handles_removed_in_view'],[])

    def test_process_identity_change_is_unknown(self):
        for key,value in [('pid',12346),('creation','0000000000000002')]:
            b=view();b['identity'][key]=value
            self.unknown(view(),b,'process_identity_metadata_changed')

    def test_equal_process_identity_does_not_prove_no_reload(self):
        out=self.evaluate(view(),view())
        self.assertFalse(out['authority']['world_epoch_proven'])
        self.assertFalse(out['authority']['atomic_snapshot'])
        self.assertFalse(out['authority']['input_authenticated'])

    def test_world_address_or_selected_identity_change_is_unknown(self):
        for key in ('game_address','database_address','country_table_address'):
            b=view();b['world'][key]='0x14000000'
            self.unknown(view(),b,'world_address_metadata_changed')
        b=view();b['actor']['address']='0x15000000'
        self.unknown(view(),b,'selected_country_identity_changed')

    def test_shared_country_generation_or_address_rebinding_is_unknown(self):
        a=view([war(attackers=[country('FRA',122),country('POR',189)])]);b=copy.deepcopy(a)
        b['wars'][0]['attackers'][1]=country('POR',189,generation=2)
        self.unknown(a,b,'shared_country_slot_generation_changed')
        b=copy.deepcopy(a);b['wars'][0]['attackers'][1]['address']='0x16000000'
        self.unknown(a,b,'shared_country_identity_changed')

    def test_raw_date_reversal_and_future_start_are_unknown(self):
        b=view();b['world']['now_raw']=99
        self.unknown(view(),b,'raw_date_order_reversed')
        b=view([war()]);b['wars'][0]['started_raw_date']=101
        self.unknown(view(),b,'integer_type_or_bound')

    def test_incomplete_self_reported_or_raw_capture_receipts_cannot_override_gate(self):
        for value in (False,None,1):
            b=view();b['complete_current_global_scan']=value
            self.unknown(view(),b,'incomplete_global_view')
        for extra in ('input_authenticated','native_ready','status'):
            b=view();b[extra]='unknown' if extra=='status' else True
            self.unknown(view(),b,'unexpected_or_missing_keys')
        self.unknown(view(),{'status':'unknown','projection':None},'unexpected_or_missing_keys')

    def test_duplicate_global_or_side_members_and_overlap_are_unknown(self):
        self.unknown(view(),view([war(),war()]),'duplicate_global_address')
        b=view([war(attackers=[country('FRA',122),country('FRA',122)])])
        self.unknown(view(),b,'duplicate_side_member')
        b=view([war(defenders=[country('ENG',46),country('FRA',122)])])
        self.unknown(view(),b,'overlapping_sides')

    def test_country_slot_address_and_war_country_aliases_are_unknown(self):
        b=view([war(attackers=[country('FRA',122),country('POR',122)])])
        self.unknown(view(),b,'country_slot_alias')
        b=view([war(attackers=[country('FRA',122),country('POR',189,address=int(country('FRA',122)['address'],16))])])
        self.unknown(view(),b,'country_address_alias')
        b=view([war(int(country('FRA',122)['address'],16))])
        self.unknown(view(),b,'war_country_address_alias')

    def test_primary_leader_wrong_side_is_unknown(self):
        b=view([war()]);b['wars'][0]['primary_attacker_handle']=TH
        self.unknown(view(),b,'primary_not_in_side')

    def test_null_invalid_or_noncanonical_pointer_fields_are_unknown(self):
        for pointer in ('0x0','0x010000','0x10001','0x800000000000','0xA0000'):
            b=view([war()]);b['wars'][0]['goal_pointer_raw']=pointer
            self.unknown(view(),b)

    def test_strict_numeric_types_and_bounds(self):
        for key,value in [('pid',True),('pid',1<<32),('pid',1.0)]:
            b=view();b['identity'][key]=value;self.unknown(view(),b)
        for key,value in [('marker',True),('raw_outcome',-1),('raw_outcome',1<<32),('started_raw_date',True)]:
            b=view([war()]);b['wars'][0][key]=value;self.unknown(view(),b)
        b=view();b['global_war_count']=False;self.unknown(view(),b)
        b=view();b['world']['country_count']=1380.0;self.unknown(view(),b)

    def test_invalid_complete_handle_generation_kind_slot_and_tag(self):
        nums=[int(AH,16)&((1<<56)-1),int(AH,16)|(1<<48),int(AH,16)|(1<<24),
              (1<<56)|int.from_bytes(b'FRA','little'),
              (1<<56)|(1380<<32)|int.from_bytes(b'FRA','little'),
              (1<<56)|(122<<32)|int.from_bytes(b'fra','little')]
        for n in nums:
            out=oracle.evaluate_graph_change(view(),view(),hex(n),TH)
            self.assertEqual(out['status'],'unknown')
        self.assertEqual(oracle.evaluate_graph_change(view(),view(),AH,AH)['status'],'unknown')

    def test_max_global_and_side_limits_with_explicit_excess_rejection(self):
        a=view([war(0x30000000+i*0x1000) for i in range(64)])
        self.assertEqual(self.evaluate(a,copy.deepcopy(a))['status'],'observed_data_pattern')
        b=copy.deepcopy(a);b['wars'].append(war(0x40000000));b['global_war_count']=65
        self.unknown(a,b,'integer_type_or_bound')
        side=[country('FRA',122)]+[country('A'+str(i).zfill(2),200+i) for i in range(1,64)]
        b=view([war(attackers=side)])
        self.assertEqual(self.evaluate(b,copy.deepcopy(b))['status'],'observed_data_pattern')
        b['wars'][0]['attackers'].append(country('ZZZ',500))
        self.unknown(view(),b,'side_type_or_bound')

    def test_missing_keys_counts_empty_sides_and_extra_war_fields(self):
        b=view();del b['world']['now_raw'];self.unknown(view(),b)
        b=view([war()]);b['global_war_count']=0;self.unknown(view(),b)
        b=view([war()]);b['wars'][0]['attackers']=[];self.unknown(view(),b)
        b=view([war()]);b['wars'][0]['stable_war_id']=7;self.unknown(view(),b)

    def test_cycles_subclasses_and_deep_wrong_shapes_never_invoke_hooks(self):
        b=view();b['wars']=[b];b['global_war_count']=1;self.unknown(view(),b)
        calls=[]
        class EvilDict(dict):
            def __len__(self):calls.append('len');raise AssertionError('not called')
        class EvilStr(str):
            def __getitem__(self,_):calls.append('getitem');raise AssertionError('not called')
        self.unknown(view(),EvilDict(view()))
        out=oracle.evaluate_graph_change(view(),view(),EvilStr(AH),TH)
        self.assertEqual(out['status'],'unknown');self.assertEqual(calls,[])
        self.unknown(view(),[[[[view()]]]])

    def test_inputs_and_catalog_are_not_mutated_or_returned_as_aliases(self):
        a=view();b=view([war()]);old_a,old_b=copy.deepcopy(a),copy.deepcopy(b)
        out=self.evaluate(a,b);out['pattern']['global_addresses_added_in_view'].append('0x1')
        out['authority']['native_ready']=True
        self.assertEqual(a,old_a);self.assertEqual(b,old_b)
        self.assertFalse(self.evaluate(a,b)['authority']['native_ready'])
        c=oracle.catalog();c['limits']['global_wars']=999;c['strict_keys']['view'].clear()
        self.assertEqual(oracle.catalog()['limits']['global_wars'],64)
        self.assertTrue(oracle.catalog()['strict_keys']['view'])


if __name__=='__main__':
    unittest.main(verbosity=2)
