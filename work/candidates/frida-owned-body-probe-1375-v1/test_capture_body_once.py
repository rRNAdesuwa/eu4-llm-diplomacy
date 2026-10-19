"""New pure host checks; no process/provider/game access."""
import importlib.util
from pathlib import Path
import struct
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('body_host_under_test',HERE/'capture_body_once.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class Reader:
    def __init__(self,port):
        self.port = port
        self.calls = self.bytes = self.largest = 0

    def read(self,at,size):
        self.calls += 1
        self.bytes += size
        self.largest = max(self.largest,size)
        value = self.port[at]
        if len(value) != size:
            raise ValueError('Short fake RPM')
        return value


class BodyHostTests(unittest.TestCase):
    def fake(self,base):
        profile = host.code_profile()
        memory = {base+rva:raw for rva,raw in profile}
        memory[base+0x1d20870] = struct.pack('<Q',base+0x8f450)
        observer = types.SimpleNamespace(BudgetReader=Reader,HeldRPMPort=lambda held:held)
        return profile,memory,observer,types.SimpleNamespace(base=base,held=memory)

    def test_loaded_bytes_and_relocated_slot(self):
        for base in (0x140000000,0x7ff7034b0000):
            profile,memory,observer,cap = self.fake(base)
            value = host.loaded_sample(cap,observer,profile)
            self.assertEqual(value['rpm_budget'],dict(calls=4,bytes=211,largest=109))
            self.assertEqual(int(value['slot']['value'],16),base+0x8f450)
            self.assertEqual([r['size'] for r in value['code']],[109,91,3])

    def test_each_function_mismatch_refused(self):
        for index in range(3):
            profile,memory,observer,cap = self.fake(host.BASE)
            at = cap.base+profile[index][0]
            memory[at] = bytes([memory[at][0]^1])+memory[at][1:]
            with self.assertRaisesRegex(ValueError,'function bytes differ'):
                host.loaded_sample(cap,observer,profile)

    def test_preferred_VA_slot_not_accepted_at_ASLR_base(self):
        profile,memory,observer,cap = self.fake(host.BASE)
        memory[cap.base+0x1d20870] = struct.pack('<Q',0x14008f450)
        with self.assertRaisesRegex(ValueError,'virtual slot differs'):
            host.loaded_sample(cap,observer,profile)

    def test_file_bound_and_short_read(self):
        profile,memory,observer,cap = self.fake(host.BASE)
        memory[cap.base+0x500560] = memory[cap.base+0x500560][:-1]
        with self.assertRaisesRegex(ValueError,'Short fake RPM'):
            host.loaded_sample(cap,observer,profile)
        with self.assertRaisesRegex(ValueError,'File bound'):
            host.read_bound(HERE/'capture_body_once.py',1)

    def test_main_refusal_does_not_capture(self):
        with patch.object(host,'verify',side_effect=ValueError('unsealed')), \
             patch.object(host,'capture') as capture, \
             patch('sys.argv',['capture_body_once.py','capture']), \
             patch('builtins.print'):
            self.assertEqual(host.main(),2)
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
