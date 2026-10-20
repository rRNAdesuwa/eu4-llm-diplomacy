"""R7-r2 regressions retain R7 graphs and the actual loaded flag46 bytes."""
import json
from pathlib import Path
import struct
from unittest.mock import patch

from bridge import war_peace_memory_observer as legacy
from bridge import war_peace_memory_observer_r2 as revised
from bridge import diplomacy_effect_observer as r1
from bridge.tests import test_war_peace_memory_observer as previous
from bridge.tests.test_effect_observer_memory import Memory

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'work/reports/war-peace-api-20261015-r7-r2/observer/retained-layout.json'


def retained_fixture():
    """Keep captured native fields; relocate only missing backing buffers.

    The retained files are not full RAM and were not atomic. This fixture
    reconstructs the observed layout, rather than claiming a recorded lease.
    """
    saved=json.loads(FIXTURE.read_bytes());root=saved['roots'];wars=saved['global_projection']['wars']
    base=previous.BASE;memory=Memory()
    game,db,array,server,pause=(int(root[k],16) for k in ('game','database','array','server','pause'))
    for address,size in ((base+0x233FE78,8),(base+0x233D8D0,8),(game,0x7518),(db,0x800),
                         (array,root['count']*8),(server,0x1000),(pause,0x60)):
        memory.map(address,size)
    memory.put(base+0x233FE78,'Q',game);memory.put(base+0x233D8D0,'Q',db)
    memory.put(game,'Q',base+0x1CB00C8);memory.put(db+0x118,'Qii',array,root['capacity'],root['count'])
    memory.put(game+0x1DD0,'i',root['date']);memory.put(game+0x1E00,'Q',server)
    memory.put(game+0x1E60,'QQ',root['current_player'],root['alternate_player'])
    memory.put(server,'Q',base+0x1CB8460);memory.put(server+0x418,'Q',pause)
    memory.put(pause+0x50,'Q',server);memory.put(pause+0x48,'B',root['manual_pause'])
    for offset,value,fmt in ((0x7485,root['reset'],'B'),(0x74C8,root['load_source'],'Q'),
                             (0x2521,root['recalculating'],'B'),(0x24D0,root['ironman'],'B')):
        memory.put(game+offset,fmt,value)
    countries={}
    for war in wars:
        for view in war['attackers']+war['defenders']:
            countries[int(view['address'],16)]=view
    for row in saved['pair_rows']:
        for name in ('owner','other'):
            view=row[name];countries[int(view['address'],16)]=view
    for address,view in countries.items():
        memory.map(address,0x9B78)
        memory.put(address,'QI',base+0x1C574A0,357);memory.put(address+0x20,'Q',int(view['handle'],16))
        memory.put(array+view['slot']*8,'Q',address)
    for n,row in enumerate(saved['pair_rows']):
        owner,other=row['owner'],row['other'];address=int(owner['address'],16);embedded=address+0x14F8
        record=int(row['record'],16);records=record-other['slot']*0x48
        memory.map(records,root['count']*0x48)
        memory.put(embedded,'QI',base+0x1C4F5F8,357);memory.put(embedded+0x10,'Q',address)
        memory.put(embedded+0x18,'QQQ',records,records+root['count']*0x48,records+root['count']*0x48)
        memory.raw(record,bytes.fromhex(row['record_bytes']))
        index=row['index'];storage=0xC00000+n*0x1000;memory.map(storage,index['capacity']*16)
        memory.put(embedded+0x48,'QQii',base+0x1C3A538,storage,index['capacity'],index['count'])
        for i,entry in enumerate(index['entries']):
            memory.put(storage+i*16,'i4xQ',entry['other_slot'],int(entry['current_war_address'],16))
    global_data=0xD00000;capacity=saved['global_projection']['global_war_capacity']
    memory.map(global_data,capacity*8)
    memory.put(game+0x1E28,'QQii',base+0x1C38348,global_data,capacity,len(wars))
    for n,war in enumerate(wars):
        address=int(war['current_war_address'],16);memory.put(global_data+n*8,'Q',address)
        memory.map(address,0x218);memory.put(address,'QI',base+0x1D1F768,357)
        memory.put(address+0x24,'i',war['started_raw_date'])
        memory.put(address+0x150,'QQQ',int(war['primary_attacker_handle'],16),
                   int(war['primary_defender_handle'],16),int(war['goal_pointer_raw'],16))
        memory.put(address+0x210,'I',war['raw_outcome'])
        for name,field,offset in (('attackers','attacker_vector',0x48),('defenders','defender_vector',0x78)):
            begin,end,cap=(int(value,16) for value in war[field]);memory.map(begin,cap-begin)
            memory.put(address+offset,'QQQ',begin,end,cap)
            memory.put(begin,'Q'*len(war[name]),*(int(view['handle'],16) for view in war[name]))
    actor=saved['pair_rows'][0]['owner'];target=saved['pair_rows'][0]['other']
    return memory,(root,actor,target),saved


class WarPeaceMemoryObserverR2Tests(previous.WarPeaceMemoryObserverTests):
    # The R7 test bundled two real identity guards with the incorrect flag ==
    # membership assumption. Replace that one method; inherit all other guards.
    test_root_owner_full_record_and_war_bit_must_agree=None

    def setUp(self):
        super().setUp()
        version=patch.object(previous,'candidate',revised);version.start();self.addCleanup(version.stop)

    def test_owner_and_complete_record_guards_remain_required(self):
        for at,fmt,value in ((previous.ACTOR+0x14F8+0x10,'Q',previous.TARGET),
                             (previous.RECORDS_A+2*0x48+8,'Q',previous.SCO)):
            with self.subTest(at=hex(at)):
                memory=previous.fixture();memory.put(at,fmt,value);self.unknown(memory)

    def test_actual_loaded_records_zero_flag_reproduce_legacy_failure_and_revised_graph(self):
        memory,(root,actor,target),saved=retained_fixture()
        self.assertEqual((actor['tag'],target['tag']),('ENG','AMG'))
        self.assertTrue(all(bytes.fromhex(row['record_bytes'])[0x46]==0 for row in saved['pair_rows']))
        old=legacy.capture_war_pair(r1.BudgetReader(memory),previous.BASE,root,actor,target)
        self.assertEqual(old['status'],'unknown')
        self.assertEqual(old['failure']['message'],'Pair war flag/index/global graph differs')
        new=revised.capture_war_pair(r1.BudgetReader(memory),previous.BASE,root,actor,target)
        self.assertEqual(new['status'],'observed',new)
        self.assertTrue(new['two_pass_equal'])
        self.assertEqual(new['projection']['global_war_count'],4)
        self.assertEqual(new['projection']['pair_state'],'opponents')
        war=new['projection']['selected_war']
        self.assertEqual(len(war['attackers'])+len(war['defenders']),41)
        for index in new['projection']['relation_indexes']:
            self.assertEqual(index['relation_byte46_raw'],0)
            self.assertFalse(index['relation_byte46_is_war_membership'])
            self.assertEqual(index['native_war_membership_predicate_rva'],'0xa68a00')
            self.assertNotIn('war_flag_bit4',index)

    def test_actual_loaded_graph_reverse_direction_has_same_current_war(self):
        memory,(root,actor,target),saved=retained_fixture()
        value=revised.capture_war_pair(r1.BudgetReader(memory),previous.BASE,root,target,actor)
        self.assertEqual(value['status'],'observed',value)
        self.assertEqual(value['projection']['selected_war']['current_war_address'],saved['pair_rows'][0]['selected'])

    def test_null_setter_can_leave_marker4_without_a_current_war(self):
        memory=previous.fixture();previous.remove_pair_indexes(memory)
        memory.put(previous.GAME+0x1E3C,'i',0)
        for record in (previous.RECORDS_A+2*0x48,previous.RECORDS_B+0x48):memory.put(record+0x46,'B',4)
        value=previous.capture(memory)
        self.assertEqual(value['status'],'observed',value)
        self.assertEqual(value['projection']['pair_state'],'not_currently_opponents')
        self.assertFalse(value['projection']['peace_completion_verified'])

    def test_stable_diagnostic_marker_values_are_not_a_war_predicate(self):
        for forward,reverse in ((0,0),(4,0),(0,4),(255,128)):
            with self.subTest(forward=forward,reverse=reverse):
                memory=previous.fixture()
                memory.put(previous.RECORDS_A+2*0x48+0x46,'B',forward)
                memory.put(previous.RECORDS_B+0x48+0x46,'B',reverse)
                value=previous.capture(memory)
                self.assertEqual(value['status'],'observed',value)
                self.assertEqual(value['projection']['pair_state'],'opponents')

    def test_whole_diagnostic_byte_stability_guard_is_stronger_than_legacy_mask_guard(self):
        memory=previous.fixture();inputs=previous.views(memory)
        def mutate(graph,at,unused):
            if at==previous.WAR:graph.put(previous.RECORDS_A+2*0x48+0x46,'B',0x14)
        memory.hook=mutate
        self.unknown(memory,inputs,reason='diagnostic byte46 changed')

    def test_opposing_global_war_without_pair_keys_is_still_unknown_with_zero_markers(self):
        memory=previous.fixture();previous.remove_pair_indexes(memory)
        self.unknown(memory,reason='Bilateral index/global')


if __name__=='__main__':
    import unittest
    unittest.main()
