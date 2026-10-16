"""Actual isolated v17 reader and temp-file publisher; no process/native calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from test_candidate import HERE, ROOT, lab, verify, core


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


# Reuse old synthetic event data only, never runtime session evidence.
fixture_module=load("v17_synthetic_preflight_data",ROOT/"work/candidates/v13-host-review/test_candidate.py")


class Integration(unittest.TestCase):
    def setUp(self):
        prior=fixture_module.CandidateTests();prior.setUp();self.addCleanup(prior.doCleanups)
        self.f=prior.f
        self.f.metadata["purpose"]=lab.PURPOSE
        self.enterContext(patch.object(lab,"LiveLabProcess",side_effect=AssertionError("No game access")))
        self.enterContext(patch.object(lab,"_private_root",lambda _:None))
        self.events=[]
        for original in self.f.events:
            event=json.loads(json.dumps(original).replace("restricted_pair_lab_1375_v13",lab.PURPOSE))
            if event["event"]=="research_frame":
                event.update(acceptance_flag=0,acceptance_state="closed",acceptance_origin_sequence=0,
                    acceptance_submit_sequence=0,acceptance_off_sequence=0,acceptance_action="none",acceptance_target="none")
            self.events.append(event)
        for name in ("session.json","install.claim"):
            (self.f.session/name).write_text(json.dumps(self.f.metadata),encoding="utf-8")
        for phase,(_,claim,_) in lab.PHASES.items():
            (self.f.session/claim).write_bytes(lab.phase_wire(phase,self.f.metadata))
        self.t=self.events[-1]["uptime_ms"]
        self.last_frame=deepcopy(self.events[-1])
        self.f.live["acceptance_flag"]=0
        self.write()

    def write(self):
        self.f.events=self.events;self.f.write()

    def read(self):
        self.write();return lab.read_evidence(self.f.session,self.f.metadata)

    def event(self,name,seq,**fields):
        return dict(event=name,pid=self.f.metadata["pid"],process_creation_filetime=self.f.metadata["process_creation_filetime"],
                    sequence=seq,**fields)

    def record(self,seq,operation="pair",action="offer_fleet_basing_rights",mode="legality_only",**fields):
        return dict(pid=self.f.metadata["pid"],creation=self.f.metadata["process_creation_filetime"],sequence=seq,
            expires=self.t+60000,operation=operation,mode=mode,action=action,actor="FRA",target="POR" if operation=="pair" else "FRA",
            speed=0,bound_action=fields.get("bound_action","none"),bound_target=fields.get("bound_target","none"),
            bound_submit_sequence=fields.get("bound_submit_sequence",0))

    def claim(self,r):
        (self.f.session/f"{r['sequence']:020}.claim").write_bytes(lab.encode_request(r))
        self.events.append(self.event("lab_request_claimed",r["sequence"],**{k:v for k,v in r.items() if k not in ("pid","creation","sequence")},
            durable_claim=True,retry_allowed=False,claimed_uptime_ms=self.t+r["sequence"]*10))

    def pair(self,seq=1,mode="legality_only"):
        r=self.record(seq,mode=mode);self.claim(r)
        fields=dict(thread_id=self.f.metadata["window_thread"],pid=self.f.metadata["pid"],actor="FRA",target="POR",
            process_creation_filetime=self.f.metadata["process_creation_filetime"],action_id=r["action"],
            world=self.last_frame["world_cookie"],raw_date=self.last_frame["raw_date"],applied_verified=False,retry_allowed=False,
            fixed_subsidy_amount_milli=0,fixed_subsidy_duration_years=0,fixed_gift_amount_milli=0,
            fixed_transfer_fraction_milli=0,fixed_insult_index=0,status=1 if mode=="legality_only" else 2,reason=0,
            submit_entered=mode=="submit",submit_returned=mode=="submit",ownership_uncertain=False,freeze_session=False,
            preview_called=True,preview_allowed=True,gate_called=True,gate_allowed=True,exception=0,
            caller_container_consumed=True if mode=="submit" else None)
        for name in ("pair_engine_begin","pair_engine_complete"):
            self.events.append(self.event("lab_native_record",seq,lease_pause=False,record=dict(fields,event=name)))
        self.events.append(self.event("lab_request_complete",seq,operation="pair",action=r["action"],status=fields["status"],reason=0,
            submit_entered=fields["submit_entered"],submit_returned=fields["submit_returned"],ownership_uncertain=False,
            session_frozen=False,applied_verified=False,retry_allowed=False,audit_complete=True))

    def health(self,seq,state,flag,origin=2):
        f=deepcopy(self.last_frame)
        f.update(last_sequence=seq,frames=f["frames"]+10,uptime_ms=self.t+seq*10+5,
            acceptance_flag=flag,acceptance_state=state,acceptance_origin_sequence=origin,
            acceptance_submit_sequence=3 if origin else 0,acceptance_off_sequence=4 if origin else 0,
            acceptance_action="offer_fleet_basing_rights" if origin else "none",acceptance_target="POR" if origin else "none")
        self.last_frame=f;self.events.append(f)

    def control(self,seq,on):
        r=self.record(seq,"accept","accept_on" if on else "accept_off","submit",bound_action="offer_fleet_basing_rights",bound_target="POR",bound_submit_sequence=3)
        self.claim(r)
        if on:
            self.events.append(self.event("lab_acceptance_pending",seq,bound_action=r["bound_action"],bound_target="POR",bound_submit_sequence=3,
                off_sequence=4,uptime_ms=self.t+seq*10+1,legality_sequence=1,legality_expires=self.t+60000,native_invoked=False,retry_allowed=False))
        complete=core(on)
        complete.update(thread_id=self.f.metadata["window_thread"],before_date=self.last_frame["raw_date"],after_date=self.last_frame["raw_date"])
        begin=deepcopy(complete)
        begin.update(event="test_acceptance_begin",after_raw_flag=None,no_native=True,after_date=0)
        begin.update({k:False for k in verify.SUCCESS_FIELDS});begin.update(stage=verify.BEGIN_STAGE,zero_arguments_confirmed=True)
        for c in (begin,complete):self.events.append(self.event("lab_native_record",seq,lease_pause=False,record=c))
        wrapper={k:v for k,v in complete.items() if k not in ("event","operation","thread_id")}
        wrapper.update(operation="accept",action=r["action"],completion_frame=self.last_frame["frames"]+1,session_frozen=False,
            applied_verified=False,natural_ai_acceptance_verified=False)
        self.events.append(self.event("lab_request_complete",seq,**wrapper))

    def full_window(self):
        self.pair();self.health(1,"closed",0,0)
        self.control(2,True);self.health(2,"armed",1)
        self.pair(3,"submit")
        self.control(4,False);self.health(4,"closed",0)

    def test_actual_four_phase_reader_accepts_new_closed_health(self):
        evidence=self.read()
        self.assertTrue(all(evidence["phases"].values()))
        self.assertEqual(evidence["acceptance_window"],verify.empty_window())

    def test_actual_full_reader_validates_claims_core_wrapper_and_later_reset(self):
        self.full_window();evidence=self.read()
        self.assertEqual(evidence["last_sequence"],4)
        self.assertTrue(verify.verify(evidence)["closed_observed_zero"])

    def test_actual_reader_rejects_missing_pending_event_and_wrong_claim_bytes(self):
        self.full_window()
        saved=deepcopy(self.events)
        self.events=[e for e in self.events if e["event"]!="lab_acceptance_pending"]
        with self.assertRaisesRegex(ValueError,"pending grant"):self.read()
        self.events=saved
        claim=self.f.session/"00000000000000000002.claim"
        claim.write_bytes(claim.read_bytes().replace(b"EU4LAB/3",b"EU4LAB/2"))
        with self.assertRaisesRegex(ValueError,"claim bytes"):self.read()

    def test_actual_reader_rejects_float_flag_in_second_health(self):
        frames=[e for e in self.events if e["event"]=="research_frame"]
        frames[-1]["acceptance_flag"]=0.0
        with self.assertRaisesRegex(ValueError,"canonical integer"):self.read()

    def test_real_temp_publisher_retains_intent_after_recheck_failure(self):
        self.pair();self.health(1,"closed",0,0)
        evidence=self.read();live=dict(self.f.live)
        kwargs=dict(sequence=2,operation="accept",action="accept_on",mode="submit",actor="FRA",target="FRA",speed=0,
                    bound_action="offer_fleet_basing_rights",bound_target="POR",bound_submit_sequence=3,ttl_ms=5000)
        def fail():raise ValueError("synthetic recheck failure")
        with self.assertRaisesRegex(ValueError,"synthetic recheck"):
            lab.publish_research(self.f.session,self.f.metadata,"a"*64,evidence,live,clock=lambda:self.t+20,recheck=fail,**kwargs)
        self.assertTrue((self.f.session/"00000000000000000002.host-intent").exists())
        self.assertFalse((self.f.session/"00000000000000000002.request").exists())
        with self.assertRaises((ValueError,OSError)):
            lab.publish_research(self.f.session,self.f.metadata,"a"*64,evidence,live,clock=lambda:self.t+20,recheck=lambda:(evidence,live),**kwargs)

    def test_temp_publisher_rechecks_legality_expiry_after_durable_intent(self):
        self.pair();self.health(1,"closed",0,0);evidence=self.read();live=dict(self.f.live)
        mutated=deepcopy(evidence);mutated["requests"][1]["request"]["expires"]=self.t+19
        with self.assertRaisesRegex(ValueError,"legality proof expired"):
            lab.publish_research(self.f.session,self.f.metadata,"a"*64,evidence,live,clock=lambda:self.t+20,
                recheck=lambda:(mutated,live),sequence=2,operation="accept",action="accept_on",mode="submit",actor="FRA",target="FRA",
                bound_action="offer_fleet_basing_rights",bound_target="POR",bound_submit_sequence=3)
        self.assertTrue((self.f.session/"00000000000000000002.host-intent").exists())
        self.assertFalse((self.f.session/"00000000000000000002.request").exists())


if __name__=="__main__":unittest.main()
