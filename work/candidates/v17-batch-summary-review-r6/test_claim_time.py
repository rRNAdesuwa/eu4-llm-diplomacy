"""Synthetic full native replay; no actual batch or process reads."""
import json
import unittest
import reviewer as r
import native_stream
import test_native as fixture


class ClaimTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.NativeReplayTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.NativeReplayTests.tearDownClass()
    def setUp(self):
        self.case=fixture.NativeReplayTests();self.case.setUp()
        self.rows=[json.loads(x) for x in self.case.raw['session/research-1375.jsonl'].splitlines()]
    def claim(self,seq=2):
        return next(x for x in self.rows if x['event']=='lab_request_claimed' and x['sequence']==seq)
    def neighbors(self,seq=2):
        index=self.rows.index(self.claim(seq))
        return (next(x for x in reversed(self.rows[:index]) if x['event']=='research_frame'),
                next(x for x in self.rows[index+1:] if x['event']=='research_frame'))
    def wire(self):
        # Canonical claim and permanent host intent must track every changed
        # expiry. This prevents a wire mismatch from masking a timing finding.
        for event in self.rows:
            if event['event']!='lab_request_claimed':continue
            stem=f"session/{event['sequence']:020}"
            request=self.case.lab.decode_request(self.case.raw[stem+'.claim'])
            request['expires']=event['expires']
            raw=self.case.lab.encode_request(request)
            self.case.raw[stem+'.claim']=raw
            self.case.raw[stem+'.host-intent']=json.dumps(self.case.fixture.host(raw)).encode()
        armed=next(x for x in self.rows if x['event']=='lab_lease_armed')
        path='session/00000000000000000004.lease-pause.claim'
        doc=json.loads(self.case.raw[path]);doc['deadline_uptime_ms']=armed['deadline_uptime_ms']
        self.case.raw[path]=json.dumps(doc).encode()
        self.case.raw['session/research-1375.jsonl']=b''.join((json.dumps(x)+'\n').encode() for x in self.rows)
    def finish(self,accept):
        self.wire();native=None
        try:
            if accept:
                native=self.case.replay();r.check_claims(native,self.case.base)
            else:
                with self.assertRaises((ValueError,TypeError,KeyError)):
                    native=self.case.replay();r.check_claims(native,self.case.base)
        finally:
            if native is not None:native.close()
    def test_delayed_claim_reproduces_953ms_gap_without_invented_grace(self):
        before,after=self.neighbors();offset=990;at=self.rows.index(after)
        for row in self.rows[at:]:
            for key in ('uptime_ms','claimed_uptime_ms','expires','deadline_uptime_ms','lease_deadline_uptime_ms'):
                if key in row and row[key]!=0:row[key]+=offset
        claim=self.claim();claim['claimed_uptime_ms']=before['uptime_ms']+953
        claim['expires']=claim['claimed_uptime_ms']+59938
        self.assertEqual(claim['expires']-before['uptime_ms'],60891)
        self.finish(True)
    def test_equal_neighbor_clock_ticks_are_admitted(self):
        for which in (0,1):
            with self.subTest(which=which):
                self.setUp();edge=self.neighbors()[which]['uptime_ms']
                self.claim()['claimed_uptime_ms']=edge;self.claim()['expires']=edge+60000
                self.finish(True)
    def test_exact_positive_remaining_one_and_sixty_thousand(self):
        for remain in (1,60000):
            with self.subTest(remain=remain):
                self.setUp();claim=self.claim();claim['expires']=claim['claimed_uptime_ms']+remain
                self.finish(True)  # Later heartbeat need not precede expiry.
    def test_expired_equal_and_over_max_are_rejected(self):
        for remain in (-1,0,60001):
            with self.subTest(remain=remain):
                self.setUp();claim=self.claim();claim['expires']=claim['claimed_uptime_ms']+remain
                self.finish(False)
    def test_claim_exact_int_and_uint64_bound(self):
        for value in (True,1511.0,None,'1511',-1,2**64):
            with self.subTest(value=value):
                self.setUp();self.claim()['claimed_uptime_ms']=value;self.finish(False)
        self.setUp();del self.claim()['claimed_uptime_ms'];self.finish(False)
    def test_expiry_aliases_fail_strict_stream_without_wire_mismatch(self):
        for value in (True,61510.0,None,'61510',-1,2**64):
            with self.subTest(value=value):
                self.setUp();self.claim()['expires']=value
                raw=b''.join((json.dumps(x)+'\n').encode() for x in self.rows)
                with self.assertRaises((ValueError,TypeError,KeyError)):
                    native_stream.strict_stream(raw,self.case.base,self.case.pre)
    def test_claim_cannot_precede_its_actual_preceding_frame(self):
        self.claim()['claimed_uptime_ms']=self.neighbors()[0]['uptime_ms']-1
        self.finish(False)
    def test_claim_cannot_borrow_later_frame_past_first_following_frame(self):
        self.claim()['claimed_uptime_ms']=self.neighbors()[1]['uptime_ms']+1
        self.finish(False)
    def without_middle_frame(self):
        self.rows.remove(self.neighbors()[1])
    def test_multiple_claims_without_intermediate_heartbeat_non_decreasing(self):
        for delta in (0,1):
            with self.subTest(delta=delta):
                self.setUp();self.without_middle_frame()
                self.claim()['claimed_uptime_ms']=1515;self.claim(3)['claimed_uptime_ms']=1515+delta
                self.claim(3)['expires']=self.claim(3)['claimed_uptime_ms']+59990
                self.finish(True)
    def test_multiple_claims_cannot_regress_within_same_heartbeat(self):
        self.without_middle_frame();self.claim()['claimed_uptime_ms']=1515
        self.claim(3)['claimed_uptime_ms']=1514;self.claim(3)['expires']=61504;self.finish(False)
    def test_missing_final_heartbeat_never_closes_stopped_stream(self):
        self.rows.pop();self.finish(False)
    def set_deadline(self,deadline):
        for row in self.rows:
            if row['event']=='lab_lease_armed':row['deadline_uptime_ms']=deadline
            if row['event']=='research_frame' and row['lease_deadline_uptime_ms']:
                row['lease_deadline_uptime_ms']=deadline
                row['uptime_ms']=max(row['uptime_ms'],deadline-4990+row['frames']-540)
    def test_lease_lower_bound_is_recorded_claim_not_old_heartbeat(self):
        claim=self.claim(4);claim['claimed_uptime_ms']+=1
        self.set_deadline(claim['claimed_uptime_ms']+4999);self.finish(False)
        self.setUp();claim=self.claim(4);claim['claimed_uptime_ms']+=1
        self.set_deadline(claim['claimed_uptime_ms']+5000);self.finish(True)
    def test_lease_upper_bound_is_expiry_plus_4999_not_5000(self):
        for delta,accept in ((4999,True),(5000,False)):
            with self.subTest(delta=delta):
                self.setUp();self.set_deadline(self.claim(4)['expires']+delta);self.finish(accept)
    def test_fixed_publish_ttl_sources_are_distinct_and_pinned(self):
        sources=json.loads((r.HERE/'source-pins.json').read_text())
        paths=('work/native/run_lab_speed_v17_1375.py','work/candidates/v17-batch-host-review-r3/batch.py')
        texts=[]
        for name in paths:
            with (r.ROOT/name).open('rb') as stream:raw=stream.read(128*1024+1)
            self.assertLessEqual(len(raw),128*1024)
            self.assertEqual(sources[name],dict(bytes=len(raw),sha256=r.ledger.digest(raw)))
            texts.append(raw.decode('utf-8'))
        self.assertIn("'--ttl-ms', '5000'",texts[0])
        self.assertTrue('TTL_MS = 60000' in texts[1])
        self.assertTrue("'--ttl-ms','60000','--publish'" in texts[1])


if __name__=='__main__':unittest.main()
