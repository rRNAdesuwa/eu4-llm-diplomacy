import dataclasses,struct,unittest
from contract import *

ACTOR=0x0100007a00415246
TARGET=0x0100006000474e45
THIRD=0x0100008800524f50

class Memory:
    def __init__(self):self.data={};self.log=[];self.hook=None
    def put(self,a,b):
        for i,v in enumerate(b):self.data[a+i]=v
    def u64(self,a,v):self.put(a,struct.pack('<Q',v))
    def i32(self,a,v):self.put(a,struct.pack('<i',v))
    def read(self,a,n):
        self.log.append((a,n))
        if self.hook:self.hook(self,a,n)
        return bytes(self.data[a+i] for i in range(n))

def setup():
    c=Context(200,12345,0x140000000,0x20000000,0x21000000,0x22000000,200,ACTOR,56456976,GAME_SHA)
    m=Memory();m.u64(c.module+0x233fe78,c.game);m.u64(c.module+0x233d8d0,c.database)
    m.u64(c.database+0x118,c.array);m.i32(c.database+0x124,c.count)
    m.u64(c.game+0x1e60,c.player);m.i32(c.game+0x1dd0,c.date)
    for i,h in enumerate((ACTOR,TARGET,THIRD)):
        p=0x23000000+i*0x10000;m.u64(c.array+((h>>32)&0xffff)*8,p);m.u64(p+0x20,h)
    m.put(c.module+COST_RVA,struct.pack('<ii',7,3));return m,c

class Tests(unittest.TestCase):
    def test_dynamic_nonstock(self):
        m,c=setup();v=capture_defaults(m.read,c)
        self.assertEqual((v['defaults']['cost_units'],v['defaults']['trust_points'],v['defaults']['favor_milli_candidate']),(7,3,7000))
        self.assertEqual((v['read_calls'],v['read_bytes']),(26,184));self.assertIsNone(v['native_permission'])
    def test_stock_not_fallback(self):
        m,c=setup();del m.data[c.module+COST_RVA]
        with self.assertRaises(KeyError):capture_defaults(m.read,c)
    def test_read_short_type(self):
        for bad in (b'\0',bytearray(8),None,'00000000'):
            with self.subTest(value=repr(bad)),self.assertRaises(ValueError):trust_defaults(bad,bad)
    def test_defaults_mismatch(self):
        with self.assertRaises(ValueError):trust_defaults(struct.pack('<ii',10,5),struct.pack('<ii',10,6))
    def test_zero_explicit_not_cancel(self):
        v=trust_defaults(bytes(8),bytes(8));self.assertEqual(v['favor_milli_candidate'],0);self.assertIsNone(v['native_permission'])
    def test_signed_and_overflow_unknown(self):
        for cost,amount in [(-1,5),(2147484,5),(10,-1),(10,101),(-2147483648,2147483647)]:
            with self.subTest(cost=cost,amount=amount):
                b=struct.pack('<ii',cost,amount);v=trust_defaults(b,b)
                self.assertEqual((v['cost_units'],v['trust_points']),(cost,amount));self.assertIsNone(v['favor_milli_candidate'])
    def test_domain_boundary(self):
        b=struct.pack('<ii',2147483,100);self.assertEqual(trust_defaults(b,b)['favor_milli_candidate'],2147483000)
    def test_changed_global_on_second_capture(self):
        m,c=setup();hits=0
        def change(mem,a,n):
            nonlocal hits
            if a==c.module+COST_RVA:
                hits+=1
                if hits==2:mem.i32(a,8)
        m.hook=change
        with self.assertRaises(ValueError):capture_defaults(m.read,c)
    def test_final_root_changes(self):
        for offset in [0x233fe78,0x233d8d0]:
            m,c=setup();hits=0
            def change(mem,a,n):
                nonlocal hits
                if a==c.module+offset:
                    hits+=1
                    if hits==3:mem.u64(a,0x33330000)
            m.hook=change
            with self.subTest(offset=offset),self.assertRaises(ValueError):capture_defaults(m.read,c)
    def test_final_date_changes(self):
        m,c=setup();hits=0
        def change(mem,a,n):
            nonlocal hits
            if a==c.game+0x1dd0:
                hits+=1
                if hits==3:mem.i32(a,c.date+1)
        m.hook=change
        with self.assertRaises(ValueError):capture_defaults(m.read,c)
    def test_context_strict_types(self):
        m,c=setup()
        for name in ['pid','creation','module','game','database','array','count','player','date']:
            for bad in [True,float(getattr(c,name))]:
                with self.subTest(name=name,bad=bad),self.assertRaises(ValueError):capture_defaults(m.read,dataclasses.replace(c,**{name:bad}))
        self.assertEqual(m.log,[])
    def test_wrong_image(self):
        m,c=setup()
        with self.assertRaises(ValueError):capture_defaults(m.read,dataclasses.replace(c,image_sha256='0'*64))
        self.assertEqual(m.log,[])
    def test_private_third_fullhandle(self):
        m,c=setup();v=third_selection(m.read,c,ACTOR,TARGET,THIRD)
        self.assertEqual(v['action_extension_bytes'],struct.pack('<Q',THIRD))
        self.assertEqual((v['read_calls'],v['read_bytes']),(36,264));self.assertFalse(v['native_predicates_evaluated'])
        self.assertFalse(v['production_ready']);self.assertFalse(v['held_process_implemented'])
    def test_third_bare_tag_or_generation(self):
        for bad in [0x524f50,0x2d2d2d,True,float(THIRD),THIRD^(1<<56)]:
            m,c=setup()
            with self.subTest(bad=bad),self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,bad)
    def test_third_other_generation(self):
        m,c=setup()
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,THIRD+(1<<56))
    def test_recipient_actor_excluded(self):
        for bad in [ACTOR,TARGET,ACTOR+(1<<56)]:
            m,c=setup()
            with self.subTest(bad=bad),self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,bad)
            self.assertEqual(m.log,[])
    def test_wrong_player_actor(self):
        m,c=setup()
        with self.assertRaises(ValueError):third_selection(m.read,c,TARGET,ACTOR,THIRD)
        self.assertEqual(m.log,[])
    def test_slot_upper_bound_before_read(self):
        m,c=setup();bad=(THIRD&~(0xffff<<32))|(c.count<<32)
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,bad)
        self.assertNotIn((c.array+c.count*8,8),m.log)
    def test_third_pointer_move_same_handle(self):
        m,c=setup();address=c.array+((THIRD>>32)&0xffff)*8;hits=0
        def change(mem,a,n):
            nonlocal hits
            if a==address:
                hits+=1
                if hits==2:mem.u64(a,0x24000000);mem.u64(0x24000020,THIRD)
        m.hook=change
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,THIRD)
    def test_player_generation_stale(self):
        m,c=setup();m.u64(0x23000020,ACTOR+(1<<56))
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,THIRD)
    def test_null_country_pointer(self):
        m,c=setup();m.u64(c.array+((THIRD>>32)&0xffff)*8,0)
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,THIRD)
        self.assertNotIn((0x20,8),m.log)
    def test_database_changed(self):
        m,c=setup();m.i32(c.database+0x124,4097)
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,THIRD)
    def test_shared_budget_exact(self):
        r=Reader(lambda a,n:bytes(n))
        for _ in range(48):r.get(0x10000,8)
        with self.assertRaises(ValueError):r.get(0x10000,1)
        self.assertEqual((r.calls,r.bytes),(48,384))
    def test_extent_and_short_reader(self):
        for address,size in [(MAX_POINTER,2),(0x10000,17),(True,8)]:
            with self.subTest(address=address,size=size),self.assertRaises(ValueError):Reader(lambda a,n:bytes(n)).get(address,size)
        with self.assertRaises(ValueError):Reader(lambda a,n:bytes(n-1)).get(0x10000,8)
    def test_final_third_context_check(self):
        m,c=setup();hits=0
        def change(mem,a,n):
            nonlocal hits
            if a==c.module+0x233fe78:
                hits+=1
                if hits==3:mem.u64(a,0x33330000)
        m.hook=change
        with self.assertRaises(ValueError):third_selection(m.read,c,ACTOR,TARGET,THIRD)

if __name__=='__main__':unittest.main()
