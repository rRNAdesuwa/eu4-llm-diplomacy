"""Real frozen native replay + exact claim checks; synthetic bytes only."""
from copy import deepcopy
import json
import unittest
import reviewer as r
import test_native as fixture


class PairContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.NativeReplayTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.NativeReplayTests.tearDownClass()
    def setUp(self):
        self.case=fixture.NativeReplayTests();self.case.setUp()
        self.rows=[json.loads(line) for line in self.case.raw['session/research-1375.jsonl'].splitlines()]
    def finish(self,accepted):
        self.case.raw['session/research-1375.jsonl']=b''.join((json.dumps(row)+'\n').encode() for row in self.rows)
        native=None
        try:
            if accepted:
                native=self.case.replay();r.check_claims(native,self.case.base)
            else:
                with self.assertRaises((ValueError,KeyError,TypeError)):
                    native=self.case.replay();r.check_claims(native,self.case.base)
        finally:
            if native is not None:native.close()
    def cores(self,seq=3):
        return [row['record'] for row in self.rows if row['event']=='lab_native_record' and row['sequence']==seq]
    def request(self,**fields):
        path='session/00000000000000000003.claim'
        req=self.case.lab.decode_request(self.case.raw[path]);req.update(fields)
        wire=self.case.lab.encode_request(req);self.case.raw[path]=wire
        self.case.raw['session/00000000000000000003.host-intent']=json.dumps(self.case.fixture.host(wire)).encode()
        for row in self.rows:
            if row['event']=='lab_request_claimed' and row['sequence']==3:
                row.update({k:v for k,v in req.items() if k not in ('pid','creation','sequence')})
        return req
    def wrapper(self):
        final=self.cores()[-1]
        for row in self.rows:
            if row['event']=='lab_request_complete' and row['sequence']==3:
                row.update({k:final[k] for k in ('status','reason','submit_entered','submit_returned','ownership_uncertain')})
    def noenter(self,mode,phase,reason):
        self.request(mode=mode)
        if phase!=12:
            self.rows=[row for row in self.rows if not(row['event']=='lab_native_record' and row['sequence']==3
                       and row['record']['event']=='pair_engine_dispatch_intent')]
        flags={3:(False,False,False,False,False,False),6:(True,False,False,False,True,False),
               8:(True,True,True,reason!=18,True,True),10:(True,True,True,True,True,True),12:(True,True,True,True,True,True)}
        final=self.cores()[-1]
        final.update(phase=phase,reason=reason,status=1 if mode=='legality_only' and phase in (6,8) else 0,
                     submit_entered=False,submit_returned=False,context_submit_return=None,caller_container_consumed=None)
        final.update(zip(r.pair_contract.FLAGS,flags[phase]));self.wrapper()

    def test_original_three_independent_counterexamples_rejected(self):
        for field,value in [('target_handle','0x0'),('actor_handle','0x0100002e00474e45'),('phase',999)]:
            with self.subTest(field=field):
                self.setUp()
                for core in self.cores():
                    if field!='phase' or core['event']=='pair_engine_complete':core[field]=value
                self.finish(False)

    def test_each_begin_intent_final_full_handle_is_bound_not_only_tags(self):
        for index in range(3):
            for field in ('actor_handle','target_handle'):
                for value in ('0x0','0x0100002e00474e45','0x000000bd00524f50','0x010000bc00524f50',0,False,'0x10000bd00524f50',' 0x010000bd00524f50'):
                    with self.subTest(index=index,field=field,value=value):
                        self.setUp();self.cores()[index][field]=value;self.finish(False)

    def test_all_five_fixed_native_country_identities_accept_when_bound(self):
        for target,handle in r.pair_contract.HANDLES.items():
            if target=='FRA':continue
            with self.subTest(target=target):
                self.setUp();self.request(target=target)
                for core in self.cores():core.update(target=target,target_handle=handle)
                self.finish(True)

    def test_valid_noenter_mode_specific_status_and_cleanup_paths(self):
        for mode in ('legality_only','submit'):
            for phase,reason in ((3,13),(6,17),(8,18)):
                with self.subTest(mode=mode,phase=phase):
                    self.setUp();self.noenter(mode,phase,reason);self.finish(True)
        self.setUp();self.noenter('legality_only',8,0);self.finish(True)
        for phase,reason in ((10,20),(12,8)):
            with self.subTest(mode='submit',phase=phase):
                self.setUp();self.noenter('submit',phase,reason);self.finish(True)

    def test_legal_rejection_never_becomes_status_one_in_submit_mode(self):
        for phase,reason in ((6,17),(8,18)):
            for mode,badstatus in (('submit',1),('legality_only',0)):
                with self.subTest(phase=phase,mode=mode):
                    self.setUp();self.noenter(mode,phase,reason)
                    self.cores()[-1]['status']=badstatus;self.wrapper();self.finish(False)

    def test_every_terminal_phase_rejects_wrong_integer_bool_float_or_bounds(self):
        for phase,reason in ((3,13),(6,17),(8,18),(8,0),(10,20),(12,8),(13,0)):
            for bad in tuple(p for p in range(16) if p!=phase)+(-1,999,2**32,True,float(phase)):
                with self.subTest(phase=phase,bad=bad):
                    self.setUp()
                    if phase!=13:self.noenter('submit' if phase in (10,12) else 'legality_only',phase,reason)
                    self.cores()[-1]['phase']=bad;self.finish(False)

    def test_begin_and_intent_phases_and_future_flags_are_exact(self):
        for index in (0,1):
            for field,bad in [('phase',999),('phase',True),('phase',2.0 if index==0 else 11.0),('status',True),
                              ('submit_entered',True),('submit_returned',True),('context_submit_return',False),
                              ('command_destroyed_before_dispatch',True)]:
                with self.subTest(index=index,field=field,bad=bad):
                    self.setUp();self.cores()[index][field]=bad;self.finish(False)
        self.setUp();self.cores()[0]['envoy_id']=0;self.finish(False)

    def test_phase_reason_and_mode_cannot_cross_product_to_false_success(self):
        for phase,reason in ((3,13),(6,17),(8,18),(8,0),(10,20),(12,8)):
            for field,bad in [('reason',999),('reason',False),('reason',float(reason)),('submit_entered',True),
                              ('submit_returned',True),('context_submit_return',False),('caller_container_consumed',True)]:
                with self.subTest(phase=phase,field=field):
                    self.setUp();self.noenter('submit' if phase in (10,12) else 'legality_only',phase,reason)
                    self.cores()[-1][field]=bad;self.wrapper();self.finish(False)
        self.setUp();self.noenter('submit',8,0);self.finish(False)
        self.setUp();self.request(mode='legality_only');self.finish(False)

    def test_each_cleanup_or_gate_bool_must_match_native_branch(self):
        for phase,reason in ((3,13),(6,17),(8,18),(8,0),(10,20),(12,8),(13,0)):
            for field in r.pair_contract.FLAGS:
                with self.subTest(phase=phase,field=field):
                    self.setUp()
                    if phase!=13:self.noenter('submit' if phase in (10,12) else 'legality_only',phase,reason)
                    final=self.cores()[-1];final[field]=not final[field];self.finish(False)

    def test_each_boundary_rejects_scalar_alias_and_fixed_parameter_tamper(self):
        for index in range(3):
            for field,bad in [('envoy_id',False),('raw_date',True),('pid',True),('thread_id',True),
                              ('exception',False),('fixed_subsidy_amount_milli',False),('fixed_insult_index',0.0),
                              ('fixed_gift_amount_milli',25000),('fixed_transfer_fraction_milli',500)]:
                with self.subTest(index=index,field=field):
                    self.setUp();self.cores()[index][field]=bad;self.finish(False)

    def test_core_boundaries_cannot_change_date_or_post_resolution_envoy(self):
        for index in (1,2):
            with self.subTest(index=index):
                self.setUp();self.cores()[index]['raw_date']+=24;self.finish(False)
        self.setUp();self.cores()[1]['envoy_id']=1;self.finish(False)

    def test_all_records_cannot_shift_to_a_different_adjacent_frame_date(self):
        for delta in (-24,24):
            with self.subTest(delta=delta):
                self.setUp()
                for core in self.cores():core['raw_date']+=delta
                self.finish(False)

    def test_final_status_boolean_cleanup_alias_and_nullable_integer_rejected(self):
        for mode,phase,reason in (('legality_only',3,13),('legality_only',6,17),('legality_only',8,0),
                                  ('submit',6,17),('submit',8,18),('submit',12,8),('submit',13,0)):
            for field in ('status','original_destroyed','command_destroyed_before_dispatch','context_submit_return','caller_container_consumed'):
                with self.subTest(mode=mode,phase=phase,field=field):
                    self.setUp()
                    if phase!=13:self.noenter(mode,phase,reason)
                    final=self.cores()[-1]
                    final[field]=(bool(final[field]) if field=='status' else int(bool(final[field])))
                    self.wrapper();self.finish(False)

    def test_noenter_context_and_final_guard_require_exact_intent_presence(self):
        self.setUp();self.noenter('submit',12,8)
        self.rows=[row for row in self.rows if not(row['event']=='lab_native_record' and row['sequence']==3
                   and row['record']['event']=='pair_engine_dispatch_intent')]
        self.finish(False)
        self.setUp();intent=deepcopy(self.cores()[1]);self.noenter('submit',10,20)
        at=next(i for i,row in enumerate(self.rows) if row['event']=='lab_native_record' and row['sequence']==3
                and row['record']['event']=='pair_engine_complete')
        wrapper=deepcopy(self.rows[at]);wrapper['record']=intent;self.rows.insert(at,wrapper);self.finish(False)

    def test_frozen_kcountries_and_audit_encoding_source_contract(self):
        raw=r.bounded(r.ROOT/'work/native/v17/pair-engine-1375.cpp').decode()
        slots={'FRA':122,'ENG':46,'POR':189,'NAV':188,'FOI':121}
        for tag,handle in r.pair_contract.HANDLES.items():
            self.assertIn('{"'+tag+'", '+str(slots[tag])+', '+handle+'ULL}',raw)
        self.assertIn('actor_handle\\\":\\\"0x%016llx',raw)
        self.assertIn('target_handle\\\":\\\"0x%016llx',raw)


if __name__=='__main__':unittest.main()
