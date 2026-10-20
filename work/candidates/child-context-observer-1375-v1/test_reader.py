"""Meaningful read boundaries using owned byte fixtures; no process APIs."""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('child_context_pure_reader',Path(__file__).with_name('reader.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Fixture:
    def __init__(self):
        self.base = 0x7FF7034B0000
        self.values = dict(base=self.base,outer=0x197C24C95B0,game=0x198481E35A0,
            current=0x1978E323010,server=0x1978E323010,holder=0x197C24C95B0,
            map_pointer=0x1987D6EC0B0,context=0x19860000000,transport=0x19860001000)
        self.values['transport_context_backlink'] = self.values['context']
        self.data,self.calls = {},[]
        self.locations = {}
        for name,receiver,offset,size,kind,expected in module.PLAN:
            if expected is not None:
                value = self.base+expected
            elif name in self.values:
                value = self.values[name]
            elif kind == 'int32':
                value = -1
            elif kind == 'uint32':
                value = 0xFFFFFFFF
            else:
                value = 1
            self.values[name] = value
            address = self.values[receiver]+offset
            raw = struct.pack('<i' if kind == 'int32' else '<I' if size == 4 else '<Q' if size == 8 else '<B',value)
            self.data[address,size] = raw
            self.locations[name] = (address,size)
    def read(self,address,size):
        self.calls.append((address,size))
        return self.data[address,size]
    def replace_q(self,name,value):
        self.data[self.locations[name]] = struct.pack('<Q',value)


class ReaderBoundaries(unittest.TestCase):
    def test_full_typed_chain_raw_budgets_and_signed_diagnostics(self):
        f = Fixture();before = copy.deepcopy(f.data)
        result = module.sample(f,f.base)
        self.assertEqual(result['status'],'typed_context_transport_observed')
        self.assertEqual((len(f.calls),sum(n for _,n in f.calls)),(25,164))
        self.assertEqual(result['fields']['command_word_source68'],-1)
        self.assertEqual(result['fields']['command_dword_source8c'],0xFFFFFFFF)
        self.assertEqual(result['fields']['sender_flag55'],1)
        self.assertFalse(result['sender_authorized'])
        self.assertFalse(result['native_ready'])
        self.assertFalse(result['lifetime_lease'])
        self.assertFalse(result['endpoint_code_bytes_verified'])
        self.assertEqual(f.data,before)
        self.assertTrue(all(bytes.fromhex(r['raw_hex']) == before[int(r['address'],16),r['size']] for r in result['reads']))

    def test_each_null_child_stops_before_dereference(self):
        for name,count in [('context',11),('transport',13)]:
            with self.subTest(name=name):
                f = Fixture();f.replace_q(name,0)
                result = module.sample(f,f.base)
                self.assertEqual(result['status'],name+'_absent')
                self.assertEqual(len(f.calls),count)
                self.assertTrue(all(a >= module.MIN for a,_ in f.calls))

    def test_types_endpoints_and_backlinks_refuse_before_following(self):
        for name,count in [('context_vtable',12),('transport_vtable',14),
                ('holder',9),('server',7),('transport_context_backlink',15),('transport_submit_endpoint',19)]:
            with self.subTest(name=name):
                f = Fixture();f.replace_q(name,0x19600001000)
                result = module.sample(f,f.base)
                self.assertEqual(result['status'],'unknown')
                self.assertEqual(len(f.calls),count)
                self.assertFalse(result['sender_authorized'])

    def test_invalid_pointer_base_and_short_reads_stop(self):
        for base in (True,1.0,0,module.MAX-8):
            f = Fixture();result = module.sample(f,base)
            self.assertEqual(result['status'],'unknown')
            self.assertEqual(len(f.calls),0)
        self.assertEqual(module.span(module.MAX-8,8),module.MAX-8)
        f = Fixture();f.replace_q('context',module.MAX)
        result = module.sample(f,f.base)
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(len(f.calls),11)
        f = Fixture();f.data[f.locations['transport']] = b'\0'
        result = module.sample(f,f.base)
        self.assertEqual(result['status'],'unknown')
        self.assertEqual((result['requested_reads'],result['exact_bytes']),(13,96))


if __name__ == '__main__':
    unittest.main(verbosity=2)
