"""Sparse bytes only. Never call sample_process or open a real process."""
import copy
import json
import struct
import sys
import unittest
from unittest.mock import patch
import raw_observer as raw

BASE=0x140000000
FRA=0x0100000100415246
ENG=0x0100000200474e45


class Sparse:
    def __init__(self):self.cells={};self.reads=[];self.on_read=None;self.bytes_read=0
    def write(self,address,blob):
        for offset,byte in enumerate(blob):self.cells[address+offset]=byte
    def put(self,address,fmt,*values):self.write(address,struct.pack(fmt,*values))
    def q(self,address,value):self.put(address,'<Q',value)
    def i(self,address,value):self.put(address,'<i',value)
    def b(self,address,value):self.put(address,'<B',value)
    def read(self,address,size):
        self.reads.append((address,size))
        self.bytes_read+=size
        if self.on_read:self.on_read(self,address,size)
        try:return bytes(self.cells[address+i] for i in range(size))
        except KeyError as error:raise raw.ReadError(f'Sparse memory hole at {error.args[0]:#x}') from error


def fixture():
    pins=raw.load_pins();m=Sparse()
    for row in pins['instruction_pins']:m.write(BASE+int(row['rva'],16),bytes.fromhex(row['bytes']))
    for row in pins['take_colony_vtable']['slots'].values():m.q(BASE+int(row['cell_rva'],16),BASE+int(row['method_rva'],16))
    m.q(BASE+0x233d8d0,0x200000);m.q(BASE+0x233fe78,0x210000)
    m.q(0x200118,0x220000);m.i(0x200124,3);m.i(0x211dd0,56456976)
    m.q(0x220008,0x300000);m.q(0x220010,0x400000)
    for country,handle,relations,gov,variant in ((0x300000,FRA,0x500000,0x600000,0x620000),(0x400000,ENG,0x510000,0x610000,0x630000)):
        m.q(country+0x20,handle);m.q(country+0x1510,relations);m.q(country+0x1420,gov)
        m.q(gov,BASE+0x1cb2240);m.q(gov+0x10,0x640000)
        for offset,v in ((0x170,variant),(0x110,variant+0x100)):
            m.q(gov+offset,v);m.i(v,0);m.b(v+8,1)
    for record,counter,root,data,key in ((0x500000+2*0x48,ENG,0x520000,0x540000,2),(0x510000+0x48,FRA,0x530000,0x550000,1)):
        m.q(record,root);m.q(record+0x10,counter);m.q(root+0x50,data);m.i(root+0x5c,1)
        m.put(data,'<i4xQ',key,0x700000)
    m.q(0x700000,BASE+0x1c7a740);m.put(0x700048,'<QQ',0x710000,0x710008);m.q(0x710000,FRA)
    m.put(0x700078,'<QQ',0x711000,0x711008);m.q(0x711000,ENG);m.q(0x700160,0x720000)
    m.q(0x720000,BASE+0x1d1fd90);m.q(0x720010,0x730000);m.i(0x720018,1);m.q(0x720030,0x740000)
    m.put(0x210000+0x1c90,'<QQ',0x750000,0x750080);m.q(0x210000+0x1ca8,0x800000)
    m.i(0x740024,1);m.q(0x800000+0x2e10+0x560,0x740000)
    for offset in (0x50,0x140,0x288,0x378):m.q(0x730000+offset+8,0);m.i(0x730000+offset+0x14,0)
    for rva,value in ((0x233fe88,0),(0x242bc80,0),(0x2340030,0x760000),(0x233ffd8,0x770000)):m.q(BASE+rva,value)
    m.q(0x770080,0x780000);m.q(0x780048,0);m.i(0x780054,0)
    m.b(BASE+0x233ff94,0);m.b(BASE+0x233fed6,0);m.i(BASE+0x233c574,0)
    return m


def capture(m,direction='demand'):return raw.capture(m,BASE,FRA,ENG,direction)


class Tests(unittest.TestCase):
    def test_complete_raw_graph_is_still_partial_and_no_permission(self):
        m=fixture();report=capture(m);snapshot=report['passes'][0]['snapshot']
        self.assertEqual(report['status'],'borrowed_war_observed_partial_preconditions')
        self.assertEqual(snapshot['war']['goal']['resolution'],'direct_definition_observed')
        self.assertEqual(snapshot['countries'][0]['government']['variants']['0x170']['field_address'],'0x600170')
        self.assertEqual(snapshot['dependency']['conditions']['container_offset'],'0x40')
        self.assertFalse(report['schema_projection']['available'])
        self.assertFalse(report['parameter_constructor_authorized'])
        self.assertFalse(report['world_epoch_verified'])
        self.assertLess(report['read_budget']['bytes_requested'],16*1024*1024)

    def test_concede_selects_other_side_without_mutating_memory(self):
        m=fixture();before=copy.deepcopy(m.cells);report=capture(m,'concede')
        self.assertEqual(m.cells,before)
        self.assertEqual(report['passes'][0]['snapshot']['negotiating_roles']['selected_condition_offsets'],['0x288','0x378'])

    def test_absent_war_is_explicit_not_default_offer_or_white_peace(self):
        m=fixture()
        for root in (0x520000,0x530000):m.q(root+0x50,0);m.i(root+0x5c,0)
        m.cells.pop(0x770080)  # No need to dereference dependency without a war.
        report=capture(m)
        self.assertEqual(report['status'],'no_matching_war')
        self.assertIsNone(report['passes'][0]['snapshot']['war'])
        self.assertFalse(any(address==0x700000 for address,size in m.reads))
        self.assertFalse(any(address==0x770080 for address,size in m.reads))

    def test_missing_index_page_is_not_absence(self):
        m=fixture();del m.cells[0x540000]
        with self.assertRaises(raw.ReadError):capture(m)

    def test_short_read_does_not_become_zero(self):
        m=fixture();original=m.read
        def short(address,size):
            blob=original(address,size)
            return blob[:-1] if address==0x540000 else blob
        m.read=short
        with self.assertRaises(raw.ReadError):capture(m)

    def test_signed_country_and_index_counts_reject_before_array_access(self):
        for address,value,forbidden in ((0x200124,-1,0x220008),(0x200124,4097,0x220008),(0x52005c,-1,0x540000),(0x52005c,65,0x540000)):
            m=fixture();m.i(address,value)
            with self.subTest(address=address,value=value),self.assertRaises(raw.ReadError):capture(m)
            self.assertFalse(any(a==forbidden for a,n in m.reads))

    def test_full_country_and_counterpart_handles_are_required(self):
        for address in (0x300020,0x500000+2*0x48+0x10):
            m=fixture();m.q(address,0x0101000100415246)
            with self.assertRaises(raw.ReadError):capture(m)

    def test_duplicate_key_is_not_first_match_success(self):
        m=fixture();m.i(0x52005c,2);m.put(0x540010,'<i4xQ',2,0x790000)
        with self.assertRaises(raw.ReadError):capture(m)

    def test_reciprocal_disagreement_or_unbounded_member_vector_rejected(self):
        for address,value in ((0x550008,0x790000),(0x700050,0x710000+65*8),(0x711000,FRA)):
            m=fixture();m.q(address,value)
            with self.assertRaises(raw.ReadError):capture(m)

    def test_government_138_is_never_read(self):
        m=fixture();report=capture(m)
        self.assertFalse(any(address in (0x600138,0x610138) for address,size in m.reads))
        self.assertEqual(report['passes'][0]['snapshot']['countries'][0]['government']['vtable']['class_status'],'unreviewed_dynamic_class')

    def test_null_government_does_not_call_or_read_fallback_object(self):
        m=fixture();m.q(0x301420,0);m.q(BASE+0x233fe88,0xc00000)
        report=capture(m)
        self.assertEqual(report['passes'][0]['snapshot']['countries'][0]['government']['status'],'missing_instance_no_getter_called')
        self.assertFalse(any(address==0xc00000 for address,size in m.reads))

    def test_unknown_variant_never_reads_assumed_boolean_storage(self):
        m=fixture();m.i(0x620000,1);del m.cells[0x620008]
        report=capture(m)
        variant=report['passes'][0]['snapshot']['countries'][0]['government']['variants']['0x170']
        self.assertEqual(variant['status'],'unreviewed_variant_type')
        self.assertIsNone(variant['storage_byte'])
        self.assertFalse(any(address==0x620008 for address,size in m.reads))

    def test_unknown_goal_class_never_uses_take_colony_layout(self):
        m=fixture();m.q(0x720000,BASE+0x1cb2240);del m.cells[0x720010]
        report=capture(m)
        self.assertEqual(report['passes'][0]['snapshot']['war']['goal']['status'],'unrecognized_goal_class')
        self.assertFalse(any(address==0x720010 for address,size in m.reads))

    def test_failed_goal_predicate_does_not_dereference_fallback(self):
        m=fixture();m.i(0x740024,0);del m.cells[0x800000+0x2e10+0x560]
        report=capture(m)
        goal=report['passes'][0]['snapshot']['war']['goal']
        self.assertEqual(goal['resolution'],'fallback_virtual_family_unreviewed')
        self.assertIsNone(goal['conditions'])
        self.assertFalse(any(address==0x760000 for address,size in m.reads))

    def test_negative_or_out_of_range_goal_index_avoids_province_deref(self):
        for index in (-1,16):
            m=fixture();m.i(0x720018,index);del m.cells[0x720030]
            self.assertEqual(capture(m)['passes'][0]['snapshot']['war']['goal']['resolution'],'fallback_virtual_family_unreviewed')
            self.assertFalse(any(address==0x720030 for address,size in m.reads))

    def test_conditions_only_read_vtable_slot_not_body(self):
        m=fixture();m.q(0x730058,0xc10000);m.i(0x730064,1);m.q(0xc10000,0xc20000)
        m.q(0xc20000,BASE+0x1cb2240);m.q(BASE+0x1cb2240+0x30,BASE+0x123000)
        report=capture(m);entry=report['passes'][0]['snapshot']['war']['goal']['conditions']['0x50']['entries'][0]
        self.assertEqual(entry['vtable']['method30_rva'],'0x123000')
        self.assertFalse(entry['purity_verified'])
        self.assertFalse(any(address==BASE+0x123000 for address,size in m.reads))

    def test_unknown_condition_vtable_outside_module_not_dereferenced(self):
        m=fixture();m.q(0x780048,0xc10000);m.i(0x780054,1);m.q(0xc10000,0xc20000);m.q(0xc20000,0xc30000)
        report=capture(m);entry=report['passes'][0]['snapshot']['dependency']['conditions']['entries'][0]
        self.assertEqual(entry['vtable']['class_status'],'unsupported_vtable_outside_readonly_module_section')
        self.assertFalse(any(address==0xc30030 for address,size in m.reads))

    def test_condition_counts_fail_before_entries_and_missing_is_not_empty(self):
        for count in (-1,65):
            m=fixture();m.i(0x780054,count)
            with self.assertRaises(raw.ReadError):capture(m)
        m=fixture();del m.cells[0x780054]
        with self.assertRaises(raw.ReadError):capture(m)

    def test_tls_is_globals_only_even_when_required(self):
        m=fixture();m.b(BASE+0x233ff94,0);m.b(BASE+0x233fed6,0);report=capture(m)
        tls=report['passes'][0]['snapshot']['tls']
        self.assertEqual(tls['status'],'unsupported_subject_thread_gs_provenance')
        self.assertNotIn('thread_id',tls)
        self.assertNotIn('gs58_array',tls)

    def test_root_change_inside_pass_stops(self):
        m=fixture();seen=0
        def change(mem,address,size):
            nonlocal seen
            if address==0x211dd0:
                seen+=1
                if seen==2:mem.i(address,56456977)
        m.on_read=change
        with self.assertRaises(raw.ReadError):capture(m)

    def test_government_changed_only_on_second_pass_stops(self):
        m=fixture();seen=0
        def change(mem,address,size):
            nonlocal seen
            if address==0x620008:
                seen+=1
                if seen==2:mem.b(address,0)
        m.on_read=change
        with self.assertRaises(raw.ReadError):capture(m)

    def test_bad_loaded_code_or_virtual_slot_stops_before_world(self):
        for address in (BASE+0x97bd30,BASE+0x1d1fde8):
            m=fixture();m.cells[address]^=1
            with self.assertRaises(raw.ReadError):capture(m)
            self.assertFalse(any(a==BASE+0x233d8d0 for a,n in m.reads))

    def test_loaded_code_change_after_two_passes_is_rejected(self):
        m=fixture();seen=0
        def change(mem,address,size):
            nonlocal seen
            if address==BASE+0x97bd30:
                seen+=1
                if seen==2:mem.cells[address]^=1
        m.on_read=change
        with self.assertRaises(raw.ReadError):capture(m)

    def test_budget_enforces_cumulative_and_request_ceiling(self):
        m=Sparse();m.write(0x100000,b'a'*16);budget=raw.Budget(m);budget.bytes=raw.MAX_TOTAL-1
        with self.assertRaises(raw.ReadError):budget.read(0x100000,2,'test')
        self.assertEqual(m.reads,[])
        budget=raw.Budget(m);budget.trace=[{}]*raw.MAX_READS
        with self.assertRaises(raw.ReadError):budget.read(0x100000,1,'test')

    def test_pure_request_validation_rejects_before_pin_or_process_helpers(self):
        for a,b,direction in ((True,ENG,'demand'),(float(FRA),ENG,'demand'),(FRA,FRA,'demand'),(FRA,ENG,'force')):
            with patch.object(raw,'load_pins',side_effect=AssertionError('must not load/open')):
                with self.assertRaises(raw.ReadError):raw.capture(Sparse(),BASE,a,b,direction)
                with self.assertRaises(raw.ReadError):raw.sample_process(pid=1,creation='0100000000000001',executable='unused',actor=a,recipient=b,direction=direction)

    def test_future_process_wrapper_closes_mock_handle_on_creation_failure(self):
        sys.path.insert(0,str(raw.ROOT))
        from work import probe_diplomacy_current as legacy
        m=fixture();m.base=BASE;m.closed=False
        m.close=lambda:setattr(m,'closed',True)
        signature={'timestamp':raw.load_pins()['pe']['timestamp'],'size':raw.load_pins()['pe']['image_size']}
        with patch.object(legacy,'ProcessReader',return_value=m) as opened, \
             patch.object(legacy,'verified_executable',return_value=({},signature)), \
             patch.object(raw,'held_identity',side_effect=raw.ReadError('expected creation differs')):
            with self.assertRaises(raw.ReadError):raw.sample_process(pid=1,creation='0100000000000001',executable=raw.ROOT.parent/'eu4.exe',actor=FRA,recipient=ENG,direction='demand')
        self.assertEqual(opened.call_count,1);self.assertTrue(m.closed);self.assertEqual(m.reads,[])

    def test_future_process_wrapper_checks_creation_after_mock_capture(self):
        sys.path.insert(0,str(raw.ROOT))
        from work import probe_diplomacy_current as legacy
        m=fixture();m.base=BASE;m.closed=False;m.close=lambda:setattr(m,'closed',True)
        signature={'timestamp':raw.load_pins()['pe']['timestamp'],'size':raw.load_pins()['pe']['image_size']}
        with patch.object(legacy,'ProcessReader',return_value=m), \
             patch.object(legacy,'verified_executable',return_value=({},signature)), \
             patch.object(raw,'held_identity',side_effect=[{'pid':1},raw.ReadError('process exited')]) as identity:
            with self.assertRaises(raw.ReadError):raw.sample_process(pid=1,creation='0100000000000001',executable=raw.ROOT.parent/'eu4.exe',actor=FRA,recipient=ENG,direction='demand')
        self.assertEqual(identity.call_count,2);self.assertTrue(m.closed);self.assertGreater(m.bytes_read,0)


if __name__=='__main__':unittest.main(verbosity=2)
