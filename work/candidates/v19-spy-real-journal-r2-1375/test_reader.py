from copy import deepcopy
import unittest
from fixture import fixture,encode
from reader import validate_stream,coherent,Tail,sha

class JournalTests(unittest.TestCase):
    def run_fixture(self,last=18):
        r,o,i,c=fixture(last);return validate_stream(encode(r),encode(o),i,c,last==18)
    def test_complete(self):
        s=self.run_fixture();self.assertEqual(s['status'],'complete');self.assertEqual(s['completed_outcomes'],[5]*5)
        self.assertTrue(all(x['entry_uptime'] is None for x in s['intervals']));self.assertFalse(s['production_ready'])
    def test_each_partial_ready_or_progress(self):
        for last in range(1,18):
            with self.subTest(last=last):
                s=self.run_fixture(last);self.assertEqual(s['next_sequence'],last//2+1 if last in (2,4,6) else None)
    def test_install_success_errors(self):
        for k,v in [('error',5),('failure_thread',1),('rip',1),('collected',0)]:
            r,o,i,c=fixture();o[1]['detail'][k]=v
            with self.assertRaises(ValueError):validate_stream(encode(r),encode(o),i,c)
    def test_missing_or_bad_claim(self):
        for key in ('1','3','4','4.item-3'):
            r,o,i,c=fixture();del c[key]
            with self.assertRaises(ValueError):validate_stream(encode(r),encode(o),i,c)
    def test_raw_hash_pairing(self):
        r,o,i,c=fixture();o[4]['raw_segment_sha256']='f'*64
        with self.assertRaises(ValueError):validate_stream(encode(r),encode(o),i,c)
    def test_no_footer_complete(self):
        r,o,i,c=fixture();o.pop()
        with self.assertRaises(ValueError):validate_stream(encode(r),encode(o),i,c,True)
    def test_bool_float_outer(self):
        for key in ('ordinal','uptime_ms','owner_thread','image_base'):
            r,o,i,c=fixture();o[0][key]=float(o[0][key])
            with self.assertRaises(ValueError):validate_stream(encode(r),encode(o),i,c)
    def test_tail_three_reads_bound(self):
        r,o,i,c=fixture(2);partial=encode(o[:-1]);calls=[]
        def read():calls.append(1);return encode(r),partial
        with self.assertRaises(Tail):coherent(read,i,c)
        self.assertEqual(len(calls),3)
    def test_tail_closes_without_trimming(self):
        r,o,i,c=fixture(2);pairs=iter([(encode(r),encode(o[:-1])),(encode(r),encode(o))])
        s=coherent(lambda:next(pairs),i,c);self.assertEqual(s['coherent_reads'],2);self.assertEqual(s['next_sequence'],2)
    def test_raw_first_outer_ahead_health_only(self):
        r1,_,i,c=fixture(1);r2,o2,_,_=fixture(2)
        pairs=iter([(encode(r1),encode(o2)),(encode(r2),encode(o2))])
        s=coherent(lambda:next(pairs),i,c);self.assertEqual(s['next_sequence'],2);self.assertEqual(s['coherent_reads'],2)
    def test_zero_stage_health_ready(self):
        r,o,i,c=fixture(1);r=r[:1];o[3]['request_sequence']=0
        o[4].update(raw_end=len(encode(r)),raw_last_ordinal=1,raw_segment_sha256=sha(encode(r)),claimed_sequence=0,preflight_stages=0,preflight_ready=True)
        s=validate_stream(encode(r),encode(o),i,{});self.assertEqual(s['next_sequence'],1);self.assertEqual(s['authenticated_stages'],0)
    def test_prefix_rewrite_rejected(self):
        r,o,i,c=fixture(2);x=deepcopy(o);x[0]['uptime_ms']=9999
        pairs=iter([(encode(r),encode(o[:-1])),(encode(r),encode(x))])
        with self.assertRaises(ValueError):coherent(lambda:next(pairs),i,c)
    def test_no_coherent_new_claim(self):
        r,o,i,c=fixture(2);r3,o3,_,_=fixture(3);pairs=iter([(encode(r),encode(o[:-1])),(encode(r3),encode(o3))])
        with self.assertRaises(ValueError):coherent(lambda:next(pairs),i,c)

if __name__=='__main__':unittest.main()
