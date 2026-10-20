"""Sparse memory only. No operating-system reader or native call."""
from copy import deepcopy
import struct
import unittest
import resolver as r
import layout as p

BASE=0x140000000;DB=0x200000000;GAME=0x210000000;ARRAY=0x220000000

def handle(tag,slot,generation=1):return int.from_bytes(tag.encode('ascii'),'little')|(slot<<32)|(generation<<56)
class Sparse:
    def __init__(self):self.data={};self.reads=[];self.before=None
    def put(self,address,raw):
        for n,b in enumerate(raw):self.data[address+n]=b
    def q(self,address,value):self.put(address,struct.pack('<Q',value))
    def i(self,address,value):self.put(address,struct.pack('<i',value))
    def b(self,address,value):self.put(address,bytes([value]))
    def read(self,address,size):
        self.reads.append((address,size))
        if self.before:self.before(self,address,size)
        return bytes(self.data[address+i] for i in range(size))

def fixture(count=8):
    m=Sparse()
    for at,h in p.CODE_PINS:m.put(BASE+at,bytes.fromhex(h))
    m.q(BASE+p.DATABASE_RVA,DB);m.q(BASE+p.GAME_RVA,GAME);m.q(DB+0x118,ARRAY);m.i(DB+0x120,count);m.i(DB+0x124,count)
    m.i(GAME+0x1dd0,56456976);m.q(GAME+0x1e60,handle('FRA',1,9));m.q(GAME+0x1e68,0);m.b(GAME+0x7485,0);m.q(GAME+0x74c8,0)
    m.put(ARRAY,bytes(count*8))
    countries={}
    for slot,tag in [(0,None),(1,'FRA'),(2,'POR'),(3,'ENG'),(4,'D00')]:
        if slot>=count:continue
        address=0x230000000+slot*0x1000;countries[slot]=address;m.q(ARRAY+slot*8,address)
        m.put(address,struct.pack('<QI',BASE+p.COUNTRY_VTABLE_RVA,p.COUNTRY_MARKER));m.q(address+0x20,p.INVALID_HANDLE if slot==0 else handle(tag,slot,9 if slot==1 else 7))
    return m,countries

def resolve(m):return r.resolve(m,BASE,{'tags':['ENG','FRA','D00']})

class ResolverTests(unittest.TestCase):
    def test_current_generation_not_static_handle_and_no_public_pointers(self):
        m,c=fixture();value=resolve(m);view=r.public_result(value)
        self.assertEqual([x['full_handle'] for x in view['bindings']],[f'0x{handle("ENG",3,7):016x}',f'0x{handle("FRA",1,9):016x}',f'0x{handle("D00",4,7):016x}'])
        self.assertFalse(view['runtime_verified']);self.assertFalse(view['aba_excluded']);self.assertFalse(view['gameplay_existence_verified'])
        self.assertNotIn('address',str(view));self.assertTrue(value['passes'][0]['entries'][0]['reserved_sentinel'])
    def test_public_tags_strict_and_extra_raw_control_fields_rejected(self):
        bad=[None,{}, {'tags':'FRA'},{'tags':[]},{'tags':['FRA']*2},{'tags':['fra']},{'tags':['F锛睞']},{'tags':['FRA\x00']},{'tags':[True]},{'tags':[123]},{'tags':['---']},{'tags':['AAAA']},{'tags':['FRA'],'address':BASE},{'tags':['FRA'],'runtime_verified':True},{'tags':['A%02d'%x for x in range(17)]}]
        for x in bad:
            with self.subTest(x=x),self.assertRaises(r.ResolutionError):r.validate_request(x)
    def test_base_alias_and_pointer_overflow(self):
        for base in (True,float(BASE),-1,0,BASE+1,2**47-65536):
            m,_=fixture()
            with self.assertRaises(r.ResolutionError):r.resolve(m,base,{'tags':['FRA']})
        m,_=fixture();m.q(DB+0x118,2**47-8)
        with self.assertRaises(r.ResolutionError):resolve(m)
    def test_count_capacity_negative_reversed_or_over_cap(self):
        for cap,count in [(0,0),(-1,8),(4097,8),(8,9),(8,-1),(8,0),(4096,4097)]:
            m,_=fixture();m.i(DB+0x120,cap);m.i(DB+0x124,count)
            with self.assertRaises(r.ResolutionError):resolve(m)
    def test_unknown_country_vtable_and_marker_stop_before_handle(self):
        for field,value in [(0,BASE+0x1c00000),(8,0x166)]:
            m,c=fixture();address=c[2]
            (m.q if field==0 else m.i)(address+field,value)
            with self.assertRaises(r.Unsupported):resolve(m)
            self.assertNotIn((address+0x20,8),m.reads)
    def test_duplicate_pointer_rejected_before_second_derived_read(self):
        m,c=fixture();m.q(ARRAY+2*8,c[1])
        with self.assertRaises(r.ResolutionError):resolve(m)
        self.assertEqual(m.reads.count((c[1]+0x20,8)),1)
    def test_duplicate_tag_and_wrong_ordinal_generation_reserved_type(self):
        values=[handle('ENG',2),handle('POR',3),handle('POR',2,0),handle('POR',2)|(1<<24),handle('POR',2)|(7<<48),2**64-1]
        for h in values:
            m,c=fixture();m.q(c[2]+0x20,h)
            with self.subTest(handle=h),self.assertRaises(r.ResolutionError):resolve(m)
    def test_slot_zero_exact_sentinel_only_and_nonzero_slot_sentinel_rejected(self):
        for slot,h in [(0,handle('ZZZ',0)),(2,p.INVALID_HANDLE)]:
            m,c=fixture();m.q(c[slot]+0x20,h)
            with self.assertRaises(r.ResolutionError):resolve(m)
    def test_null_slots_and_missing_tag_not_game_nonexistence(self):
        m,c=fixture();m.q(ARRAY+4*8,0)
        with self.assertRaisesRegex(r.ResolutionError,'unavailable'):resolve(m)
        value=r.resolve(m,BASE,{'tags':['FRA']});self.assertIsNone(value['passes'][0]['entries'][4]['handle'])
    def test_unreadable_object_or_short_untyped_reader_not_absent(self):
        m,c=fixture();m.q(ARRAY+2*8,0x240000000)
        with self.assertRaisesRegex(r.ResolutionError,'Unavailable'):resolve(m)
        for raw in (True,b'',bytearray(b'x')):
            class Bad:
                def read(self,address,size):return raw
            with self.assertRaises(r.ResolutionError):resolve(Bad())
    def test_selector_variant7_unsupported_and_byte_overlap_detected(self):
        m,_=fixture();m.q(GAME+0x1e60,handle('FRA',1,9)|(7<<48));m.q(GAME+0x1e68,handle('ENG',3,7))
        with self.assertRaises(r.Unsupported):resolve(m)
        m,_=fixture()
        def mutate(x,a,n):
            if a==GAME+0x1e66:x.b(a,7)
        m.before=mutate
        with self.assertRaises(r.ResolutionError):resolve(m)
    def test_alternate_inactive_full_raw_value_captured_rechecked(self):
        m,_=fixture();m.q(GAME+0x1e68,handle('ENG',3,7));value=resolve(m)
        self.assertEqual(value['passes'][0]['roots']['alternate_raw'],handle('ENG',3,7));self.assertEqual(value['passes'][0]['roots']['effective_player'],handle('FRA',1,9))
    def test_current_player_full_generation_must_match_country(self):
        m,_=fixture();m.q(GAME+0x1e60,handle('FRA',1,8))
        with self.assertRaisesRegex(r.ResolutionError,'Current/effective'):resolve(m)
    def test_known_reset_load_and_date_are_strict(self):
        for offset,width,value in [(0x7485,1,1),(0x74c8,8,0x10000),(0x1dd0,4,0),(0x1dd0,4,-1)]:
            m,_=fixture();(m.b if width==1 else m.q if width==8 else m.i)(GAME+offset,value)
            with self.assertRaises(r.ResolutionError):resolve(m)
    def test_pointer_array_change_within_and_between_passes(self):
        for nth in (2,3):
            m,c=fixture();seen=0
            def mutate(x,a,n):
                nonlocal seen
                if a==ARRAY:
                    seen+=1
                    if seen==nth:x.q(ARRAY+7*8,c[4])
            m.before=mutate
            with self.assertRaises(r.ResolutionError):resolve(m)
    def test_handle_change_between_passes_with_same_roots(self):
        m,c=fixture();seen=0
        def mutate(x,a,n):
            nonlocal seen
            if a==c[3]+0x20:
                seen+=1
                if seen==2:x.q(a,handle('ENG',3,8))
        m.before=mutate
        with self.assertRaisesRegex(r.ResolutionError,'between complete'):resolve(m)
    def test_roots_date_current_and_alternate_change_inside_pass(self):
        for offset,width,value in [(0x1dd0,4,56457000),(0x1e60,8,handle('POR',2,7)),(0x1e68,8,handle('POR',2,7)),(0x74c8,8,0x10000)]:
            m,c=fixture();done=False
            def mutate(x,a,n):
                nonlocal done
                if a==c[4]+0x20 and not done:
                    done=True;(x.i if width==4 else x.q)(GAME+offset,value)
            m.before=mutate
            with self.assertRaises(r.ResolutionError):resolve(m)
    def test_code_pin_changed_or_mutated_after_two_passes(self):
        m,_=fixture();at,raw=p.CODE_PINS[0];m.b(BASE+at,0)
        with self.assertRaisesRegex(r.ResolutionError,'instruction'):resolve(m)
        m,_=fixture();seen=0
        def mutate(x,a,n):
            nonlocal seen
            if a==BASE+at:
                seen+=1
                if seen==2:x.b(a,0)
        m.before=mutate
        with self.assertRaisesRegex(r.ResolutionError,'instruction'):resolve(m)
    def test_result_reinspection_rejects_typed_aliases_false_promotions(self):
        m,_=fixture();value=resolve(m)
        for field,new in [('date',56456976.0),('count',8.0),('selector',False),('reset',False),('current_player',float(handle('FRA',1,9)))]:
            bad=deepcopy(value)
            for one in bad['passes']:one['roots'][field]=new
            with self.assertRaises(r.ResolutionError):r.public_result(bad)
        for field in value['flags']:
            bad=deepcopy(value);bad['flags'][field]=True
            with self.assertRaises(r.ResolutionError):r.public_result(bad)
        bad=deepcopy(value);bad['bindings'][0]['slot']=3.0
        with self.assertRaises(r.ResolutionError):r.public_result(bad)
    def test_slot_order_array_hash_alias_and_unknown_fields_rejected(self):
        m,_=fixture();value=resolve(m)
        for change in ('ordinal','address','hash','extra','marker_bool'):
            bad=deepcopy(value)
            for s in bad['passes']:
                if change=='ordinal':s['entries'][3]['slot']=2
                if change=='address':s['entries'][3]['address']=s['entries'][2]['address']
                if change=='hash':s['array_sha256']='0'*64
                if change=='extra':s['entries'][3]['trusted']=True
                if change=='marker_bool':s['entries'][3]['marker']=True
            with self.assertRaises(r.ResolutionError):r.public_result(bad)
    def test_budget_endpoints_and_type_aliases(self):
        m,_=fixture();b=r.Budget(m);b.calls=p.MAX_CALLS
        with self.assertRaises(r.ResolutionError):b.read(BASE,1)
        b=r.Budget(m);b.bytes=p.MAX_TOTAL
        with self.assertRaises(r.ResolutionError):b.read(BASE,1)
        for a,n in [(True,1),(float(BASE),1),(BASE,True),(BASE,32769),(2**47-1,2)]:
            with self.assertRaises(r.ResolutionError):r.Budget(m).read(a,n)
    def test_max_lookup_size_sparse_and_exact_full_census(self):
        m,_=fixture(4096);value=resolve(m)
        self.assertEqual(len(value['passes'][0]['entries']),4096);self.assertLess(value['read_budget']['calls'],p.MAX_CALLS);self.assertLess(value['read_budget']['bytes'],p.MAX_TOTAL)
    def test_dense_4096_table_stays_inside_one_shared_budget(self):
        m,c=fixture(4096);alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        for slot in range(5,4096):
            tag=alphabet[(slot//1296)%36]+alphabet[(slot//36)%36]+alphabet[slot%36]
            address=0x230000000+slot*0x1000;m.q(ARRAY+slot*8,address)
            m.put(address,struct.pack('<QI',BASE+p.COUNTRY_VTABLE_RVA,p.COUNTRY_MARKER));m.q(address+0x20,handle(tag,slot,255))
        result=resolve(m);self.assertLess(result['read_budget']['calls'],p.MAX_CALLS);self.assertLess(result['read_budget']['bytes'],p.MAX_TOTAL)
        self.assertEqual(result['read_budget']['calls'],52+4*4096+2*len(p.CODE_PINS))
    def test_global_roots_and_lookup_header_mutation_fail_closed(self):
        for address,width,new in [(BASE+p.GAME_RVA,8,0x300000000),(BASE+p.DATABASE_RVA,8,0x300000000),(DB+0x118,8,0x300000000),(DB+0x120,4,9),(DB+0x124,4,7)]:
            m,c=fixture();done=False
            def change(x,a,n):
                nonlocal done
                if a==c[4]+0x20 and not done:
                    done=True;(x.q if width==8 else x.i)(address,new)
            m.before=change
            with self.assertRaises(r.ResolutionError):resolve(m)
    def test_impossible_budget_record_rejected(self):
        m,_=fixture();result=resolve(m)
        for field,value in [('calls',1),('bytes',1),('calls',float(result['read_budget']['calls'])),('bytes',True)]:
            bad=deepcopy(result);bad['read_budget'][field]=value
            with self.assertRaises(r.ResolutionError):r.public_result(bad)
    def test_aba_can_be_invisible_and_is_never_claimed_excluded(self):
        m,c=fixture();original=m.read
        def unseen(a,n):
            # A change and restoration wholly between observed reads cannot be
            # detected; this is deliberately a limitation, not a fake failure.
            old=bytes(m.data[c[3]+0x20+i] for i in range(8));m.q(c[3]+0x20,handle('ENG',3,99));m.put(c[3]+0x20,old)
            return original(a,n)
        m.read=unseen;value=resolve(m);self.assertFalse(value['flags']['aba_excluded']);self.assertFalse(value['flags']['world_epoch_verified'])

if __name__=='__main__':unittest.main()
