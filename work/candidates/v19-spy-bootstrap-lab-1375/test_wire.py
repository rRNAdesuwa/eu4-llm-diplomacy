import unittest
import wire

class WireTests(unittest.TestCase):
    def setUp(self):
        self.i={'pid':123,'creation':'01dd500000000001','session':'a'*32,'dll_sha256':'b'*64,'manifest_sha256':'c'*64}
    def test_round_trip(self):
        self.assertEqual(wire.decode_boot(wire.encode_boot(self.i)),self.i)
        for stage in wire.STAGES:
            for expiry in (1,60000,2**64-1):
                x=wire.decode_request(wire.encode_request(self.i,stage,expiry))
                self.assertEqual(x,{'identity':self.i,'stage':stage,'expires':expiry,'sequence':wire.STAGES.index(stage)+1})
    def test_bootstrap_forbids_old_no_send_and_implicit_stage(self):
        raw=wire.encode_boot(self.i)
        for old in (raw.replace(b'EU4SPYBOOT19/1',b'EU4SPYBOOT/1'),raw.replace(b'restricted_spy_send=1',b'no_send=1'),raw+b'stage=send_batch\n'):
            with self.assertRaises(ValueError):wire.decode_boot(old)
    def test_exact_bytes_and_atomic_ascii(self):
        packets=[wire.encode_boot(self.i)]+[wire.encode_request(self.i,s,60000) for s in wire.STAGES]
        for raw in packets:
            decode=wire.decode_boot if raw.startswith(b'EU4SPYBOOT19') else wire.decode_request
            for at in range(len(raw)):
                with self.assertRaises(ValueError):decode(raw[:at]+b'\r'+raw[at+1:])
            for invalid in (raw[:-1],raw+b'\n',raw.replace(b'pid=123',b'pid=0123'),raw.replace(b'creation=01',b'creation=0A')):
                with self.assertRaises(ValueError):decode(invalid)
    def test_fixed_semantics(self):
        raw=wire.encode_request(self.i,'send_batch',60000)
        for a,b in ((b'sequence=4',b'sequence=3'),(b'actor=FRA',b'actor=ENG'),(b'profile=spy5_true_state0_v1',b'profile=anything'),(b'envoy=-1',b'envoy=0'),(b'EU4SPYSEND/1',b'EU4SPYLAB/1')):
            with self.assertRaises(ValueError):wire.decode_request(raw.replace(a,b))
    def test_identity_and_types(self):
        for key in wire.IDENTITY:
            i=dict(self.i);i[key]=True
            with self.assertRaises(ValueError):wire.encode_boot(i)
        for key in ('creation','session','dll_sha256','manifest_sha256'):
            i=dict(self.i);i[key]='0'*len(i[key])
            with self.assertRaises(ValueError):wire.encode_boot(i)
        for expiry in (True,0,-1,2**64,1.5,'60000'):
            with self.assertRaises(ValueError):wire.encode_request(self.i,'send_batch',expiry)
        for stage in ([],None,True,'anything'):
            with self.assertRaises(ValueError):wire.encode_request(self.i,stage,60000)
    def test_children_are_fixed_private_claims(self):
        for item,name in enumerate(wire.FAMILIES,1):
            raw=wire.encode_item(self.i,item,60000)
            self.assertIn(f'item={item}\nfamily={name}\n'.encode(),raw)
            self.assertIn(b'sequence=4\n',raw)
        for item in (True,0,6,-1,[],'1'):
            with self.assertRaises(ValueError):wire.encode_item(self.i,item,60000)

if __name__=='__main__':unittest.main()
