"""Actual-layout byte graphs and destructive field counterexamples, no EU4."""
import copy
import struct
import unittest

from bridge import relation_effect_reader as reader
from bridge.tests.test_effect_observer_memory import (
    graph as base_graph, BASE, GAME, DB, COUNTRIES, ACTOR, TARGET,
    RECORDS_A, RECORDS_B, DATE, FRA, SCO, IDENTITY, handle)

LEFT, RIGHT, OBJECT, OTHER = 0x880000, 0x881000, 0x890000, 0x891000
# Independent fixture constants transcribed from the fixed native evidence.
LAYOUTS = {
    'offer_alliance': (0x78, 0x1C7A740, 0x48, 0xA68D90,
        '488b11488b411048c1e82098488b8a800000004c63828c00000049c1e0044c03c1493bc8740d3901740c4883c110493bc875f333c0c3488b4108c3'),
    'royal_marriage': (0x60, 0x1C80BE0, 0x40, 0xA68BE0,
        '488b11488b411048c1e82098488b4a684c63427449c1e0044c03c1493bc8740d3901740c4883c110493bc875f333c0c3488b4108c3'),
    'guarantee': (0x198, 0x1C817D8, 0x48, 0xA6A050,
        '488b11488b411048c1e82098488b8aa00100004c6382ac01000049c1e0044c03c1493bc8740d3901740c4883c110493bc875f333c0c3488b4108c3'),
}


def graph(action='offer_alliance', present=True, reverse=False):
    m=base_graph()
    for address,size in ((LEFT,128),(RIGHT,128),(OBJECT,0x48),(OTHER,0x48)):m.map(address,size)
    for name,(offset,vt,size,getter,code) in LAYOUTS.items():
        raw=bytes.fromhex(code);m.map(BASE+getter,len(raw));m.raw(BASE+getter,raw)
        for owner in (ACTOR,TARGET):m.put(owner+0x14F8+offset,'QQii',BASE+0x1C3A538,0,0,0)
    offset,vt,size,_,_=LAYOUTS[action]
    if present:
        m.put(ACTOR+0x14F8+offset,'QQii',BASE+0x1C3A538,LEFT,8,1)
        m.put(TARGET+0x14F8+offset,'QQii',BASE+0x1C3A538,RIGHT,8,1)
        m.put(LEFT,'i4xQ',2,OBJECT);m.put(RIGHT,'i4xQ',1,OBJECT)
        m.put(OBJECT,'QI',BASE+vt,357)
        m.put(OBJECT+0x10,'QQi',*( (SCO,FRA) if reverse else (FRA,SCO)),DATE-15)
    return m


def capture(memory,action='offer_alliance',actor=FRA,target=SCO):
    return reader.read_relation_pair(memory,BASE,action,actor,target,IDENTITY)


def receipt(action='offer_alliance'):
    result=dict(identity=copy.deepcopy(IDENTITY),state='dispatched',sequence=1,audit_sha256='7'*64,
        command=dict(request_id='synthetic-new-relation-1',action=action,actor='FRA',target='SCO'))
    result['binding']=dict(IDENTITY,event='pair_bound',sequence=1,no_send=False,actor_handle=FRA,target_handle=SCO)
    result['native_result']=dict(IDENTITY,event='request_result',sequence=1,no_send=False,status=4,
        reason='normal_dispatch_slot_consumed',submitted=True,submit_attempted=True,submit_returned=True,
        submit_value=True,slot_consumed=True,ownership_closed=True,owned_live=0,quarantined=0,adapter_fault=0,
        submit_exception=0,transfer_outcome=1,adapter_call_attempts=7,owned_issued=3,known_cleanup_complete=False)
    return result


class RelationMemoryGraphTests(unittest.TestCase):
    def assert_unknown(self,m,action='offer_alliance'):
        value=capture(m,action);self.assertEqual(value['status'],'unknown',value)
        self.assertFalse(value['current_relation_observed']);return value

    def test_three_native_layouts_are_current_and_absent(self):
        for action in LAYOUTS:
            for present in (False,True):
                with self.subTest(action=action,present=present):
                    value=capture(graph(action,present),action)
                    self.assertEqual(value['status'],'current_relation_observed' if present else 'pair_absent_observed')
                    self.assertTrue(value['two_pass_equal'])
                    self.assertEqual(value['snapshot']['indexes']['actor']['container'],hex(ACTOR+0x14F8+LAYOUTS[action][0]))

    def test_alliance_and_marriage_are_symmetric_without_initiator_claim(self):
        for action in ('offer_alliance','royal_marriage'):
            with self.subTest(action=action):
                value=capture(graph(action,reverse=True),action)
                self.assertEqual(value['status'],'current_relation_observed')
                self.assertFalse(value['AI_acceptance_verified'])

    def test_reverse_guarantee_does_not_verify_actor_guarantees_target(self):
        value=capture(graph('guarantee',reverse=True),'guarantee')
        self.assertEqual(value['status'],'reverse_relation_observed')
        self.assertFalse(value['current_relation_observed'])

    def test_guarantee_reversed_command_reads_the_same_object_as_forward(self):
        value=capture(graph('guarantee',reverse=True),'guarantee',SCO,FRA)
        self.assertEqual(value['status'],'current_relation_observed')
        self.assertEqual(value['snapshot']['pair']['actor_tag'],'SCO')

    def test_current_state_does_not_claim_global_membership_or_effect(self):
        m=graph();value=capture(m)
        self.assertFalse(value['global_membership_verified'])
        self.assertEqual(value['snapshot']['global_membership_status'],'not_sampled')
        self.assertNotIn((GAME+0x1BB8+0x10,16),m.reads)
        self.assertNotIn('selected_effect_verified',value)
        self.assertFalse(value['world_epoch_proven']);self.assertFalse(value['atomic_snapshot_proven'])

    def test_index_type_must_match_for_empty_and_nonempty(self):
        for present in (False,True):
            m=graph(present=present);m.put(TARGET+0x14F8+0x78,'Q',BASE+0x1C3A538+8)
            self.assert_unknown(m)

    def test_signed_index_capacity_and_count_fail_closed_before_payload(self):
        for cap,count in ((-1,0),(0,-1),(0,1),(4097,0),(4096,257)):
            with self.subTest(cap=cap,count=count):
                m=graph();m.put(ACTOR+0x14F8+0x78+0x10,'ii',cap,count)
                self.assert_unknown(m);self.assertNotIn((LEFT,16),m.reads)

    def test_allocation_null_alignment_and_end_overflow_fail_closed(self):
        for array,cap in ((0,1),(LEFT,0),(LEFT+1,8),(2**47-8,1)):
            with self.subTest(array=array,cap=cap):
                m=graph(present=False)
                m.put(ACTOR+0x14F8+0x78+8,'Qii',array,cap,0);self.assert_unknown(m)

    def test_empty_reserved_index_is_valid_absence(self):
        m=graph(present=False);m.put(ACTOR+0x14F8+0x78+8,'Qii',LEFT,8,0)
        value=capture(m);self.assertEqual(value['status'],'pair_absent_observed')
        self.assertNotIn((LEFT,16),m.reads)

    def test_duplicate_country_key_is_unknown(self):
        m=graph();m.put(ACTOR+0x14F8+0x78+0x14,'i',2);m.put(LEFT+16,'i4xQ',2,OTHER)
        self.assert_unknown(m)

    def test_selected_object_cannot_alias_another_counterpart(self):
        m=graph();m.put(ACTOR+0x14F8+0x78+0x14,'i',2);m.put(LEFT+16,'i4xQ',3,OBJECT)
        self.assert_unknown(m)

    def test_index_signed_slot_outside_country_table_is_unknown(self):
        for slot in (-1,0,1380,32768):
            m=graph();m.put(LEFT,'i',slot);self.assert_unknown(m)

    def test_bilateral_missing_or_different_object_is_unknown(self):
        for corrupt in ('missing','other'):
            m=graph()
            if corrupt=='missing':m.put(TARGET+0x14F8+0x78+0x14,'i',0)
            else:m.put(RIGHT+8,'Q',OTHER)
            self.assert_unknown(m)

    def test_wrong_object_type_or_marker_is_unknown(self):
        for field,fmt,value in ((0,'Q',BASE+0x1C80BE0),(8,'I',358)):
            m=graph();m.put(OBJECT+field,fmt,value);self.assert_unknown(m)

    def test_endpoint_full_generation_and_selector_are_not_slot_matches(self):
        for other in (handle('SCO',2,valid=0),handle('SCO',2,kind=1),handle('ENG',2),handle('SCO',2,valid=2)):
            m=graph();m.put(OBJECT+0x18,'Q',other);self.assert_unknown(m)

    def test_removed_and_failed_insertion_objects_are_unknown(self):
        for offset in (0x28,0x29):
            for value in (1,2):
                m=graph();m.put(OBJECT+offset,'B',value);self.assert_unknown(m)

    def test_invalid_start_date_is_unknown(self):
        for value in (-1,0,DATE+1):
            m=graph();m.put(OBJECT+0x20,'i',value);self.assert_unknown(m)

    def test_dirty_bit_is_diagnostic_not_relation_membership(self):
        m=graph();m.put(RECORDS_A+2*0x48+0x46,'B',0);m.put(RECORDS_B+0x48+0x46,'B',0)
        self.assertEqual(capture(m)['status'],'current_relation_observed')
        m=graph(present=False);m.put(RECORDS_A+2*0x48+0x46,'B',4)
        self.assertEqual(capture(m)['status'],'pair_absent_observed')

    def test_root_vtable_owner_and_full_record_are_guarded(self):
        for address,fmt,value in ((ACTOR+0x14F8,'Q',BASE+0x1C4F5F8+8),
                (ACTOR+0x14F8+0x10,'Q',TARGET),(RECORDS_A+2*0x48+8,'Q',SCO),
                (RECORDS_A+2*0x48+0x10,'Q',handle('SCO',2,valid=2))):
            m=graph();m.put(address,fmt,value);self.assert_unknown(m)

    def test_input_handle_valid_byte_selector_and_signed_slot_are_guarded(self):
        for actor in (handle('FRA',1,valid=0),handle('FRA',1,kind=7),handle('FRA',32768)):
            value=capture(graph(),actor=actor);self.assertEqual(value['status'],'unknown')

    def test_game_loading_reset_cache_and_pause_are_guarded(self):
        for address,fmt,value in ((GAME+0x74C8,'Q',OTHER),(GAME+0x7485,'B',1),
                (GAME+0x2521,'B',1),(GAME+0x1E66,'B',7)):
            m=graph();m.put(address,fmt,value);self.assert_unknown(m)

    def test_loaded_native_getter_mismatch_is_unknown(self):
        m=graph();m.put(BASE+0xA68D90,'B',0x90);self.assert_unknown(m)

    def test_short_reads_in_any_graph_layer_are_unknown(self):
        for address in (LEFT,OBJECT,ACTOR+0x14F8,BASE+0xA68D90):
            m=graph();m.short.add(address);self.assert_unknown(m)

    def test_object_changes_during_its_second_read_are_unknown(self):
        m=graph();seen=0
        def hook(memory,address,size):
            nonlocal seen
            if address==OBJECT:
                seen+=1
                if seen==2:memory.put(OBJECT+0x20,'i',DATE-14)
        m.hook=hook;self.assert_unknown(m)

    def test_header_stable_but_index_entries_change_are_unknown(self):
        m=graph();seen=0
        def hook(memory,address,size):
            nonlocal seen
            if address==LEFT:
                seen+=1
                if seen==2:memory.put(LEFT+8,'Q',OTHER)
        m.hook=hook;self.assert_unknown(m)

    def test_between_pass_change_is_unknown(self):
        m=graph();seen=0
        def hook(memory,address,size):
            nonlocal seen
            if address==BASE+0xA68D90:
                seen+=1
                if seen==2:memory.put(OBJECT+0x20,'i',DATE-14)
        m.hook=hook;self.assert_unknown(m)

    def test_old_pointer_is_never_followed_after_current_indexes_remove_it(self):
        m=graph();self.assertEqual(capture(m)['status'],'current_relation_observed')
        for owner in (ACTOR,TARGET):m.put(owner+0x14F8+0x78,'QQii',BASE+0x1C3A538,0,0,0)
        m.reads.clear();m.short.add(OBJECT)
        self.assertEqual(capture(m)['status'],'pair_absent_observed')
        self.assertFalse(any(address==OBJECT for address,_ in m.reads))

    def test_budget_is_shared_when_caller_supplies_r1_budget_reader(self):
        from bridge.diplomacy_effect_observer import BudgetReader,LIMITS
        r=BudgetReader(graph());r.calls=LIMITS['calls']
        value=reader.read_relation_pair(r,BASE,'offer_alliance',FRA,SCO,IDENTITY)
        self.assertEqual(value['status'],'unknown');self.assertEqual(r.calls,LIMITS['calls'])


class RelationEffectEvidenceTests(unittest.TestCase):
    def values(self,action='offer_alliance'):
        return capture(graph(action,False),action),capture(graph(action),action),receipt(action)

    def test_three_exact_new_relations_with_full_receipts_are_selected_effects(self):
        for action in LAYOUTS:
            b,a,r=self.values(action);value=reader.evaluate_relation_effect(action,b,a,r)
            self.assertEqual(value['status'],'observed',value);self.assertTrue(value['selected_effect_verified'])
            self.assertFalse(value['native_known_cleanup_complete']);self.assertFalse(value['AI_acceptance_verified'])
            self.assertFalse(value['global_membership_verified']);self.assertFalse(value['exclusive_causality_proven'])

    def test_current_present_without_baseline_is_unknown(self):
        _,a,r=self.values();value=reader.evaluate_relation_effect('offer_alliance',None,a,r)
        self.assertEqual(value['status'],'unknown')

    def test_present_to_present_absent_to_absent_and_removal_are_not_new_effect(self):
        b,a,r=self.values()
        for before,after in ((a,a),(b,b),(a,b)):
            value=reader.evaluate_relation_effect('offer_alliance',before,after,r)
            self.assertEqual(value['status'],'not_observed');self.assertFalse(value['selected_effect_verified'])

    def test_reverse_guarantee_does_not_pass_new_effect(self):
        b,_,r=self.values('guarantee');a=capture(graph('guarantee',reverse=True),'guarantee')
        self.assertEqual(reader.evaluate_relation_effect('guarantee',b,a,r)['status'],'not_observed')

    def test_incomplete_faulted_or_not_dispatched_receipts_are_unknown(self):
        changes=[('status',3),('submitted',False),('submit_attempted',False),('submit_returned',False),
                 ('slot_consumed',False),('ownership_closed',False),('owned_live',1),('quarantined',1),
                 ('adapter_fault',1),('submit_exception',1),('transfer_outcome',0),('adapter_call_attempts',6),
                 ('owned_issued',2),('no_send',True),('known_cleanup_complete',None)]
        for key,value in changes:
            b,a,r=self.values();r['native_result'][key]=value
            self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown',key)

    def test_receipt_identity_binding_event_action_audit_and_sequence_are_exact(self):
        cases=[('identity','session','4'*32),('binding','actor_handle',handle('FRA',1,valid=2)),
               ('binding','event','request_result'),('native_result','sequence',2),('native_result','sequence',True),
               ('command','action','guarantee'),
               ('native_result','creation','0000000000000002')]
        for section,key,value in cases:
            b,a,r=self.values();r[section][key]=value
            self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown')
        for key in ('audit_sha256','sequence','binding','native_result'):
            b,a,r=self.values();del r[key]
            self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown')

    def test_inconsistent_or_tampered_snapshot_cannot_supply_effect(self):
        b,a,r=self.values();a['passes'][1]=copy.deepcopy(a['passes'][1]);a['passes'][1]['now_raw']+=1
        self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown')
        b,a,r=self.values();a['snapshot']['object']['first_handle']=hex(SCO)
        self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown')
        b,a,r=self.values();a['snapshot']['indexes']['actor']['capacity_signed']=0
        self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown')

    def test_in_process_world_root_change_is_unknown_not_epoch(self):
        b,a,r=self.values();a['snapshot']['roots']['game']=hex(GAME+0x10000)
        self.assertEqual(reader.evaluate_relation_effect('offer_alliance',b,a,r)['status'],'unknown')

    def test_unsupported_action_is_unknown_without_reading(self):
        m=graph();value=capture(m,'ask_military_access');self.assertEqual(value['status'],'unknown');self.assertEqual(m.reads,[])


if __name__=='__main__':unittest.main()
