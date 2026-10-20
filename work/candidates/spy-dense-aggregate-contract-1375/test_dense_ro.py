import copy,struct,unittest
import dense_ro as d
BASE=0x140000000;ACTOR=0x20000000;ROOT=0x30000000;DATA=0x40000000;A=ACTOR+0x28d0
class Memory:
    def __init__(self):self.data={};self.calls=[];self.hook=None
    def put(self,p,raw):self.data.update({p+i:b for i,b in enumerate(raw)})
    def q(self,p,v):self.put(p,struct.pack('<Q',v))
    def i(self,p,v):self.put(p,struct.pack('<i',v))
    def read(self,p,n):
        self.calls.append((p,n))
        if self.hook:self.hook(self,p,n)
        return bytes(self.data[p+i] for i in range(n))
def fixture():
    m=Memory();c=d.report()
    for f in c['facts'].values():
        for i in f['evidence']:m.put(BASE+int(i['rva'],16),bytes.fromhex(i['bytes']))
    m.q(BASE+0x1c427b8,BASE+0x8e6190)
    m.i(ACTOR+0x28c8,2);m.q(BASE+0x2358080,ROOT);m.q(ROOT+0xe4a0,0)
    for f in c['families'].values():m.i(BASE+f['base_cost_rva'],8000)
    m.q(A,BASE+0x1c42770);m.i(A+8,0x165);m.put(A+0x10,b'\1')
    m.q(A+0x50,BASE+0x1c37fa0);m.q(A+0x58,DATA);m.i(A+0x60,694);m.i(A+0x64,694)
    m.put(DATA+d.SELECTED*8,struct.pack('<ii',d.EMPTY,0));return m
def run(m=None,family='corrupt_officials'):return d.capture(m or fixture(),BASE,ACTOR,family)
class Tests(unittest.TestCase):
    def test_empty_sentinel_is_not_index(self):
        x=run();self.assertEqual(x['final_milli_candidate'],8000)
        self.assertEqual(x['before']['aggregate']['selected_record']['id'],0x286)
        self.assertTrue(all(v is False for v in x['claims'].values()))
    def test_indexed_signed_values(self):
        for v,expected in [(-1000,0),(-125,7000),(0,8000),(1,8008),(250,10000)]:
            with self.subTest(v=v):
                m=fixture();m.put(DATA+d.SELECTED*8,struct.pack('<ii',d.SELECTED,v));self.assertEqual(run(m)['final_milli_candidate'],expected)
    def test_noninteger_division(self):
        m=fixture();m.i(BASE+d.report()['families']['corrupt_officials']['base_cost_rva'],1001)
        m.put(DATA+d.SELECTED*8,struct.pack('<ii',d.SELECTED,1));self.assertEqual(run(m)['final_milli_candidate'],1002)
    def test_five_fixed_families(self):
        for index,f in enumerate(d.report()['families']):
            with self.subTest(f=f):
                m=fixture();m.i(BASE+d.report()['families'][f]['base_cost_rva'],1000+index);self.assertEqual(run(m,f)['final_milli_candidate'],1000+index)
    def test_count_is_not_hardcoded(self):
        for count in (610,647,694,4096):
            m=fixture();m.i(A+0x60,count);m.i(A+0x64,count);self.assertEqual(run(m)['final_milli_candidate'],8000)
    def test_vector_bounds_do_not_read_data(self):
        for count,cap in ((609,694),(695,694),(-1,694),(694,-1),(4097,4097),(694,4097)):
            with self.subTest(count=count,cap=cap):
                m=fixture();m.i(A+0x64,count);m.i(A+0x60,cap);x=run(m)
                self.assertEqual(x['before']['status'],'unsupported_vector_bounds');self.assertIsNone(x['final_milli_candidate'])
                self.assertNotIn((DATA+d.SELECTED*8,8),m.calls)
    def test_null_vector_does_not_read_data(self):
        m=fixture();m.q(A+0x58,0);self.assertEqual(run(m)['before']['status'],'unsupported_vector_bounds')
    def test_vector_span_overflow(self):
        m=fixture();m.q(A+0x58,0x7ffffffffff8)
        with self.assertRaises(d.ReadError):run(m)
    def test_record_identity_unknown(self):
        for ident,value in ((1,0),(0x286,1),(-1,0)):
            m=fixture();m.put(DATA+d.SELECTED*8,struct.pack('<ii',ident,value));x=run(m)
            self.assertIsNone(x['final_milli_candidate']);self.assertEqual(x['before']['status'],'unsupported_record_identity')
    def test_modifier_outside_narrow_range(self):
        for value in (-1001,1000001,-2147483648,2147483647):
            m=fixture();m.put(DATA+d.SELECTED*8,struct.pack('<ii',d.SELECTED,value));self.assertEqual(run(m)['before']['status'],'unsupported_modifier_range')
    def test_base_range_and_final_overflow(self):
        p=BASE+d.report()['families']['corrupt_officials']['base_cost_rva']
        for value in (-1,d.MAX_COST+1):
            m=fixture();m.i(p,value);self.assertEqual(run(m)['before']['status'],'unsupported_base_range')
        m=fixture();m.i(p,d.MAX_COST);m.put(DATA+d.SELECTED*8,struct.pack('<ii',d.SELECTED,1));self.assertEqual(run(m)['before']['status'],'unsupported_cost_range')
    def test_unknown_cache_no_aggregate_or_transform(self):
        for state in (-1,0,1,3,2147483647):
            m=fixture();m.i(ACTOR+0x28c8,state);x=run(m);self.assertEqual(x['before']['status'],'unsupported_cache_state')
            self.assertNotIn((A,8),m.calls);self.assertNotIn((BASE+0x2358080,8),m.calls)
    def test_missing_transform_root(self):
        m=fixture();m.q(BASE+0x2358080,0);x=run(m);self.assertEqual(x['before']['status'],'unknown_transform_root');self.assertNotIn((A,8),m.calls)
    def test_transform_not_dereferenced(self):
        m=fixture();m.q(ROOT+0xe4a0,0x50000000);x=run(m)
        self.assertEqual(x['before']['status'],'unsupported_dynamic_transform');self.assertNotIn((0x50000000,8),m.calls);self.assertNotIn((A,8),m.calls)
    def test_unknown_vtable_no_body(self):
        m=fixture();m.q(A,BASE+0x99);x=run(m);self.assertEqual(x['before']['status'],'unsupported_aggregate_vtable');self.assertNotIn((A+8,4),m.calls)
    def test_other_layout_no_data(self):
        for offset,raw in ((8,struct.pack('<i',0)),(0x10,b'\0'),(0x10,b'\2'),(0x50,struct.pack('<Q',BASE+0x99))):
            m=fixture();m.put(A+offset,raw);x=run(m);self.assertEqual(x['before']['status'],'unsupported_aggregate_layout');self.assertNotIn((A+0x58,8),m.calls)
    def test_two_pass_changes_reject(self):
        for p,raw in ((A+0x64,struct.pack('<i',693)),(ACTOR+0x28c8,struct.pack('<i',1)),(DATA+d.SELECTED*8,struct.pack('<ii',d.SELECTED,1)),(ROOT+0xe4a0,struct.pack('<Q',0x50000000))):
            with self.subTest(p=p):
                m=fixture();seen=0
                def hook(mem,address,n):
                    nonlocal seen
                    if address==p:
                        seen+=1
                        if seen==2:mem.put(p,raw)
                m.hook=hook
                with self.assertRaises(d.ReadError):run(m)
    def test_input_type_and_fixed_scope(self):
        for base,actor,family in ((True,ACTOR,'corrupt_officials'),(float(BASE),ACTOR,'corrupt_officials'),(BASE,float(ACTOR),'corrupt_officials'),(BASE,ACTOR,True),(BASE,ACTOR,'cancel_corrupt_officials'),(BASE,ACTOR,'__all__')):
            m=fixture()
            with self.assertRaises(d.ReadError):d.capture(m,base,actor,family)
            self.assertEqual(m.calls,[])
    def test_misaligned_pointer(self):
        for offset in (1,4):
            with self.assertRaises(d.ReadError):d.capture(fixture(),BASE,ACTOR+offset,'corrupt_officials')
    def test_loaded_pin_failure_before_state(self):
        m=fixture();first=min(int(v['rva'],16) for f in d.report()['facts'].values() for v in f['evidence']);m.put(BASE+first,b'\xcc')
        with self.assertRaises(d.ReadError):run(m)
        self.assertNotIn((ACTOR+0x28c8,4),m.calls)
    def test_loaded_vslot_failure(self):
        m=fixture();m.q(BASE+0x1c427b8,BASE+0x8e6191)
        with self.assertRaises(d.ReadError):run(m)
    def test_short_or_typed_reader(self):
        class Bad:
            def __init__(self,result):self.result=result
            def read(self,p,n):return self.result
        for data in (b'',bytearray(b'\0'),None):
            with self.assertRaises(d.ReadError):run(Bad(data))
    def test_budget_and_bounds(self):
        m=fixture();r=d.Budget(m)
        for p,n in ((True,1),(A,True),(float(A),1),(A,65),(0x7fffffffffff,2)):
            with self.assertRaises(d.ReadError):r.read(p,n)
        r.bytes=d.MAX_BYTES
        with self.assertRaises(d.ReadError):r.read(A,1)
        r=d.Budget(m);r.reads=[None]*d.MAX_READS
        with self.assertRaises(d.ReadError):r.read(A,1)
    def test_reads_only_selected_record(self):
        x=run();datareads=[v for v in x['reads'] if DATA<=v['address']<DATA+4096*8]
        self.assertEqual([(v['address'],v['size']) for v in datareads],[(DATA+d.SELECTED*8,8)]*2)
        self.assertLess(x['read_bytes'],2048)
    def test_no_claim_of_identity_or_cache_freshness(self):
        x=run();self.assertEqual(set(x['claims']),set(d.FALSE_CLAIMS));self.assertTrue(all(type(v) is bool and not v for v in x['claims'].values()))
if __name__=='__main__':unittest.main()
