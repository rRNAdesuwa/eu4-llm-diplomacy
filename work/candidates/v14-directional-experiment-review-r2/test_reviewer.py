"""Synthetic JSONL, sparse-memory RO fixtures and temp files only; no process access."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
r=load("directional_experiment_review_tested",HERE/"reviewer.py")
pref=load("directional_experiment_prefix_fixtures",ROOT/"work/candidates/v14-directional-preflight-review/test_reviewer.py")
obsfixture=load("directional_experiment_ro_fixtures",ROOT/"work/candidates/directional-pair-observer-1375/test_observer.py")
observer=obsfixture.candidate
lab=r.lab

def data(value):return (json.dumps(value,sort_keys=True)+"\n").encode()
def core(action="embargo",submit=False,event="pair_engine_complete"):
    d={k:0 for k in r.PAIR_INTS}|{k:False for k in r.PAIR_BOOLS}|{k:None for k in r.PAIR_NULLABLE}
    d.update(event=event,action_id=action,actor="FRA",target="POR",pid=r.PID,thread_id=r.THREAD,process_creation_filetime=r.CREATION,
        world=r.WORLD,actor_handle="0x0100007a00415246",target_handle="0x010000bd00524f50",raw_date=r.INITIAL_DATE,envoy_id=-1,
        status=2 if submit else 1,phase=13 if submit else 8,preview_called=True,preview_allowed=True,gate_called=True,gate_allowed=True,
        original_destroyed=True,command_destroyed_before_dispatch=not submit,submit_entered=submit,submit_returned=submit,
        context_submit_return=True if submit else None,caller_container_consumed=True if submit else None)
    if event=="pair_engine_begin":
        for k in r.PAIR_BOOLS:d[k]=False
        d.update(status=0,phase=2,context_submit_return=None,caller_container_consumed=None)
    elif event=="pair_engine_dispatch_intent":d.update(status=0,phase=11,submit_entered=False,submit_returned=False,context_submit_return=None,caller_container_consumed=None)
    return d

def snapshot(action="embargo",active=False,after=False):
    doc=obsfixture.snapshot(action,active,after)
    doc["expected_pid"]=r.PID;doc["expected_creation"]=r.CREATION
    raw=doc["family_snapshot"];raw["source"].update(pid=r.PID,process_creation_filetime=int(r.CREATION,16))
    for sample in raw["observation"]["passes"]:sample.update(game=r.WORLD,current_raw_date=r.INITIAL_DATE)
    return doc

class PipelineTests(unittest.TestCase):
    def setUp(self):
        base=pref.ReviewTests();base.setUp();self.addCleanup(base.doCleanups);self.base=base
        self.root=base.root;self.pre=pref.review
        # Actual four-phase parsers and observer run. Only fixed dependency files
        # and synthetic prefix bytes/locations are redirected, never proof values.
        self.enterContext(patch.object(r,"dependencies",return_value=(self.pre,observer)))
        self.enterContext(patch.object(lab,"LiveLabProcess",side_effect=AssertionError("no process")))
        self.enterContext(patch.object(lab,"publish_research",side_effect=AssertionError("no publish")))
        self.prefix_raw=(base.session/"research-1375.jsonl").read_bytes()
        self.enterContext(patch.object(r,"PREFIX_BYTES",len(self.prefix_raw)))
        self.enterContext(patch.object(r,"PREFIX_SHA",r.sha(self.prefix_raw)))
        self.case=r.template();self.case["finalized"]=True;self.inputs=self.case["inputs"]
        self.session=self.root/r.SESSION;self.session.mkdir(parents=True)
        self.events=deepcopy(base.events)
        for name in self.pre.FILES:(self.session/name).write_bytes((base.session/name).read_bytes())
        self.metadata=base.f.metadata
        self.prefix_case=base.case()
        self.write_artifact("precase",r.PREFLIGHT_CASE,self.prefix_case)
        self.write_artifact("presummary",r.PREFLIGHT_SUMMARY,self.pre.review(self.prefix_case,root=self.root))
        self.case.update(preflight_case="precase",preflight_summary="presummary")
        for i,desc in enumerate(self.prefix_case["inputs"].values()):self.inputs["preinput"+str(i)]=desc
        for phase,(_,claim,_) in lab.PHASES.items():
            (self.session/(claim+".host-intent")).write_bytes(data(self.host(lab.phase_wire(phase,self.metadata))))
        self.case["requests"]=[]
        self.append_request(1,False);self.append_request(2,True)
        self.write_effect()
        exit_row=dict(pid=r.PID,creation=r.CREATION,exit_observed=True,method="held_handle_wait_and_getprocesstimes",process_exit_filetime=int(r.CREATION,16)+1000000,process_creation_filetime=int(r.CREATION,16),before_exit_filetime=0,wait_status=0,exit_code=0,
            read_only=True,process_stop_requested_by_observer=False,access="QUERY_LIMITED_INFORMATION | SYNCHRONIZE",executable_sha256=lab.LOCAL_SHA256)
        self.write_artifact("exit","exit.json",exit_row);self.case["exit"]={"input":"exit","select":[]}
        self.refresh_final()
    def write_artifact(self,key,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value if type(value) is bytes else data(value))
        raw=path.read_bytes();self.inputs[key]=dict(path=name,size_bytes=len(raw),sha256=r.sha(raw));return key
    def host(self,wire):return dict(protocol=lab.PROTOCOL,purpose=lab.PURPOSE,pid=r.PID,creation=r.CREATION,manifest_sha256=r.MANIFEST_SHA,request_sha256=r.sha(wire),body_ascii=wire.decode(),automatic_retry=False)
    def write_log(self):(self.session/"research-1375.jsonl").write_bytes(self.prefix_raw+b"".join(data(e) for e in self.events[len(self.base.events):]))
    def status(self,sequence=None):
        self.write_log();e=lab.read_evidence(self.session,self.metadata)
        s=dict(purpose=lab.PURPOSE,protocol=lab.PROTOCOL,pid=r.PID,creation=r.CREATION,dll_sha256=r.DLL_SHA.upper(),manifest_sha256=r.MANIFEST_SHA,
            latest_frame=e["latest_frame"],phases=e["phases"],last_sequence=e["last_sequence"],pending=False,lease_pending=False,log_sha256=e["log_sha256"],applied_verified=False,production_backend_registered=False,read_only=True)
        if sequence is not None:s["request"]=e["requests"][sequence]
        return s
    def capture(self,key,report):
        self.write_artifact(key,key+".json",dict(purpose="one_explicit_v14_cli_capture",kind="request",arguments=["synthetic"],automatic_retry=False,applied_verified=False,exit_code=0,stderr="",report=report))
        return {"input":key,"select":["report"]}
    def append_request(self,seq,submit):
        pub=self.status()
        req=dict(pid=r.PID,creation=r.CREATION,sequence=seq,expires=pub["latest_frame"]["uptime_ms"]+1000,operation="pair",mode="submit" if submit else "legality_only",action="embargo",actor="FRA",target="POR",speed=0)
        wire=lab.encode_request(req);stem=f"{seq:020}"
        (self.session/(stem+".claim")).write_bytes(wire);(self.session/(stem+".host-intent")).write_bytes(data(self.host(wire)))
        pub["publication"]=dict(research_only=True,protocol=lab.PROTOCOL,status="published",request_sha256=r.sha(wire),pid=r.PID,creation=r.CREATION,sequence=seq,phase=None,native_dispatch_verified=False,applied_verified=False,automatic_retry=False,production_backend_registered=False)
        pubref=self.capture("pub"+str(seq),pub)
        claim={k:v for k,v in req.items() if k!="creation"};claim.update(event="lab_request_claimed",process_creation_filetime=r.CREATION,durable_claim=True,retry_allowed=False)
        self.events.append(claim)
        names=["pair_engine_begin"]+(["pair_engine_dispatch_intent"] if submit else [])+["pair_engine_complete"]
        for name in names:self.events.append(dict(event="lab_native_record",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,lease_pause=False,record=core(submit=submit,event=name)))
        final=core(submit=submit)
        self.events.append(dict(event="lab_request_complete",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,operation="pair",action="embargo",
            **{k:final[k] for k in ("status","reason","submit_entered","submit_returned","ownership_uncertain")},session_frozen=False,applied_verified=False,retry_allowed=False))
        frame=deepcopy(pub["latest_frame"]);frame.update(frames=frame["frames"]+1,uptime_ms=frame["uptime_ms"]+1,last_sequence=seq,send_enabled=True)
        self.events.append(frame);statusref=self.capture("status"+str(seq),self.status(seq))
        self.case["requests"].append(dict(sequence=seq,request={k:req[k] for k in ("operation","mode","action","actor","target","speed")},outcome="dispatched" if submit else "legality_allowed",legality_sequence=seq-1 if submit else None,publication=pubref,status=statusref))
    def append_speed(self,seq=3):
        stem=f"{seq:020}";pub=self.status();start=pub["latest_frame"]["raw_date"];end=start+48
        req=dict(pid=r.PID,creation=r.CREATION,sequence=seq,expires=pub["latest_frame"]["uptime_ms"]+1000,operation="speed",mode="submit",action="none",actor="FRA",target="FRA",speed=5)
        wire=lab.encode_request(req);(self.session/(stem+".claim")).write_bytes(wire);(self.session/(stem+".host-intent")).write_bytes(data(self.host(wire)))
        pub["publication"]=dict(research_only=True,protocol=lab.PROTOCOL,status="published",request_sha256=r.sha(wire),pid=r.PID,creation=r.CREATION,sequence=seq,phase=None,native_dispatch_verified=False,applied_verified=False,automatic_retry=False,production_backend_registered=False)
        (self.session/(stem+".publisher-output.txt")).write_bytes(data(pub))
        claim={k:v for k,v in req.items() if k!="creation"};claim.update(event="lab_request_claimed",process_creation_filetime=r.CREATION,durable_claim=True,retry_allowed=False)
        self.events.append(claim)
        def controls(speed,date,event):
            done=event=="test_speed_complete"
            return dict(event=event,thread_id=r.THREAD,requested_speed=speed,reason=0,before_date=date,before_native_index=0 if speed else 4,before_paused=speed!=0,
                write_entered=done,callback_returned=done,callback_success=done,result_destroyed=done,readback_observed=done,
                after_date=date if done else 0,after_native_index=min(speed,4) if done else 0,after_paused=speed==0 and done,
                readback_matches=done,exception_code=0,freeze_session=False,retry_allowed=False,diplomacy_submitted=False)
        deadline=pub["latest_frame"]["uptime_ms"]+5000
        self.events.append(dict(event="lab_lease_armed",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,deadline_uptime_ms=deadline,maximum_raw_date_delta=48,initial_raw_date=start,automatic_pause=True,reliable_generation_verified=False))
        for name in ("test_speed_begin","test_speed_complete"):
            self.events.append(dict(event="lab_native_record",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,lease_pause=False,record=controls(5,start,name)))
        self.events.append(dict(event="lab_request_complete",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,operation="speed",speed=5,reason=0,write_entered=True,callback_returned=True,readback_matches=True,session_frozen=False,applied_verified=False,retry_allowed=False))
        frame=deepcopy(pub["latest_frame"]);frame.update(frames=frame["frames"]+1,uptime_ms=frame["uptime_ms"]+1,last_sequence=seq,lease_active=True,lease_deadline_uptime_ms=deadline,paused=False,native_speed_index=4)
        self.events.append(frame)
        advanced=deepcopy(frame);advanced.update(frames=frame["frames"]+1,uptime_ms=frame["uptime_ms"]+1,raw_date=end);self.events.append(advanced)
        for name in ("test_speed_begin","test_speed_complete"):
            self.events.append(dict(event="lab_native_record",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,lease_pause=True,record=controls(0,end,name)))
        lease=dict(event="lab_lease_complete",pid=r.PID,process_creation_filetime=r.CREATION,sequence=seq,reason=0,write_entered=True,callback_returned=True,paused_readback=True,readback_matches=True,session_frozen=False,retry_allowed=False)
        self.events.append(lease)
        paused=deepcopy(advanced);paused.update(frames=advanced["frames"]+1,uptime_ms=advanced["uptime_ms"]+1,lease_active=False,lease_deadline_uptime_ms=deadline,paused=True,native_speed_index=0);self.events.append(paused)
        (self.session/(stem+".lease-pause.claim")).write_bytes(data(dict(purpose="bounded_running_lease_pause",pid=r.PID,process_creation_filetime=r.CREATION,origin_sequence=seq,speed=0,deadline_uptime_ms=deadline,maximum_raw_date_delta=48,retry_allowed=False)))
        state=dict(game=int(r.WORLD,16),server=0x123450000,pause_manager=0x123451000,player=int("0100007a00415246",16),raw_date=start,paused=True,native_speed_index=0)
        armed=dict(event="supervisor_armed",pid=r.PID,creation=r.CREATION,sequence=seq,speed=5,retry_allowed=False,deadline_seconds=12.0,before=state)
        complete=dict(event="supervisor_complete",pid=r.PID,creation=r.CREATION,sequence=seq,speed=5,retry_allowed=False,after=dict(state,raw_date=end),elapsed_seconds=4.0,native_lease_complete=lease)
        (self.session/(stem+".supervisor.jsonl")).write_bytes(data(armed)+data(complete))
        receipt=self.capture("speed"+str(seq),dict(status="completed_and_paused",report="synthetic",before_date=start,after_date=end))
        final=self.capture("status"+str(seq),self.status(seq))
        self.case["requests"].append(dict(sequence=seq,request={k:req[k] for k in ("operation","mode","action","actor","target","speed")},outcome="completed_and_paused",legality_sequence=None,publication=receipt,status=final))
        self.refresh_final()
    def write_effect(self,active=True):
        before=snapshot();after=snapshot(active=active,after=True)
        self.write_artifact("before","before-effect.json",before);self.write_artifact("after","after-effect.json",after)
        result=observer.compare_reports(before,after);result["inputs"]={k+"_sha256":self.inputs[k]["sha256"] for k in ("before","after")}
        self.write_artifact("compare","compare.json",result)
        self.case["effects"]=[dict(sequence=2,before="before",after="after",comparison="compare",expected_observed_effect=active)]
    def refresh_final(self):
        self.case["final_status"]=self.capture("final",self.status())
        files={}
        for index,path in enumerate(sorted(self.session.iterdir())):
            key="session"+str(index);files[path.name]=key;raw=path.read_bytes();self.inputs[key]=dict(path=path.relative_to(self.root).as_posix(),size_bytes=len(raw),sha256=r.sha(raw))
        self.case["session_files"]=files
        audit=dict(pid=r.PID,creation=r.CREATION,process_exit_filetime=int(r.CREATION,16)+1000000,complete_log=self.inputs[files["research-1375.jsonl"]],session_files={n:self.inputs[k] for n,k in files.items()},stopped=True)
        self.write_artifact("audit","audit.json",audit);self.case["stopped_audit"]={"input":"audit","select":[]}
    def run_review(self):return r.review(self.case,root=self.root)
    def refresh_speed(self):
        self.capture("status3",self.status(3));self.refresh_final()
    def rebind_expiry(self,expires):
        event=next(e for e in self.events if e.get("event")=="lab_request_claimed" and e["sequence"]==2)
        event["expires"]=expires;stem="00000000000000000002"
        request=lab.decode_request((self.session/(stem+".claim")).read_bytes());request["expires"]=expires
        wire=lab.encode_request(request)
        (self.session/(stem+".claim")).write_bytes(wire);(self.session/(stem+".host-intent")).write_bytes(data(self.host(wire)))
        doc=json.loads((self.root/"pub2.json").read_bytes());doc["report"]["publication"]["request_sha256"]=r.sha(wire)
        self.write_artifact("pub2","pub2.json",doc);self.capture("status2",self.status(2));self.refresh_final()
    def test_expired_and_overlong_canonical_claims_reject(self):
        claim_index=next(i for i,e in enumerate(self.events) if e.get("event")=="lab_request_claimed" and e["sequence"]==2)
        uptime=next(e["uptime_ms"] for e in reversed(self.events[:claim_index]) if e["event"]=="research_frame")
        for expires in (1,uptime,uptime+60001):
            self.rebind_expiry(expires)
            with self.subTest(expires=expires),self.assertRaisesRegex(ValueError,"sixty-second"):
                self.run_review()
    def test_sixty_second_claim_boundary_is_inclusive(self):
        i=next(i for i,e in enumerate(self.events) if e.get("event")=="lab_request_claimed" and e["sequence"]==2)
        uptime=next(e["uptime_ms"] for e in reversed(self.events[:i]) if e["event"]=="research_frame")
        self.rebind_expiry(uptime+60000);self.assertEqual(self.run_review()["status"],"reviewed_stopped_session")
    def test_negative_and_positive_unbound_speed_dates_reject(self):
        self.append_speed();original=deepcopy(self.events)
        for date in (-123,r.INITIAL_DATE+1):
            self.events=deepcopy(original)
            for e in self.events:
                if e.get("event")=="lab_native_record" and e.get("sequence")==3:
                    e["record"]["before_date"]=date
                    if e["record"]["event"]=="test_speed_complete":e["record"]["after_date"]=date
            self.refresh_speed()
            with self.subTest(date=date),self.assertRaisesRegex(ValueError,"snapshot bounds|preceding paused"):
                self.run_review()
    def test_executed_speed_begin_original_counterexample_rejects(self):
        self.append_speed()
        for e in self.events:
            if e.get("event")=="lab_native_record" and e.get("sequence")==3 and e["record"]["event"]=="test_speed_begin":
                for k in ("write_entered","callback_returned","callback_success","result_destroyed","readback_observed","readback_matches"):
                    e["record"][k]=True
        self.refresh_speed()
        with self.assertRaisesRegex(ValueError,"Speed begin already owns"):self.run_review()
    def test_speed_completion_cannot_rewrite_begin_date(self):
        self.append_speed()
        e=next(e for e in self.events if e.get("event")=="lab_native_record" and e.get("sequence")==3
               and e["lease_pause"] and e["record"]["event"]=="test_speed_complete")
        e["record"]["before_date"]+=1;e["record"]["after_date"]+=1;self.refresh_speed()
        with self.assertRaisesRegex(ValueError,"rewrites its begin"):self.run_review()
    def test_pause_callback_must_match_following_frame(self):
        self.append_speed()
        for e in self.events:
            if e.get("event")=="lab_native_record" and e.get("sequence")==3 and e["lease_pause"]:
                e["record"]["before_date"]+=1
                if e["record"]["event"]=="test_speed_complete":e["record"]["after_date"]+=1
        self.refresh_speed()
        with self.assertRaisesRegex(ValueError,"following healthy frame"):self.run_review()
    def test_pause_may_advance_after_last_running_heartbeat(self):
        self.append_speed()
        self.events=[e for e in self.events if not (e["event"]=="research_frame" and e["last_sequence"]==3
                     and e["lease_active"] and e["raw_date"]==r.INITIAL_DATE+48)]
        self.refresh_speed();self.assertEqual(self.run_review()["status"],"reviewed_stopped_session")
    def test_auto_pause_can_precede_any_running_heartbeat(self):
        self.append_speed()
        self.events=[e for e in self.events if not (e["event"]=="research_frame" and e["last_sequence"]==3 and e["lease_active"])]
        self.refresh_speed();self.assertEqual(self.run_review()["status"],"reviewed_stopped_session")
    def test_lease_initial_date_and_arm_order_are_bound(self):
        self.append_speed();original=deepcopy(self.events)
        armed=next(e for e in self.events if e["event"]=="lab_lease_armed");armed["initial_raw_date"]+=1
        self.refresh_speed()
        with self.assertRaisesRegex(ValueError,"Lease armed"):self.run_review()
        self.events=deepcopy(original)
        i=next(i for i,e in enumerate(self.events) if e["event"]=="lab_lease_armed")
        self.events.insert(i+2,self.events.pop(i));self.refresh_speed()
        with self.assertRaisesRegex(ValueError,"armed/run/pause order"):self.run_review()
    def test_supervisor_dates_cannot_disagree_with_native(self):
        self.append_speed();path=self.session/"00000000000000000003.supervisor.jsonl"
        original=path.read_bytes()
        for field,index in (("before",0),("after",1)):
            events=[json.loads(x) for x in original.splitlines()];events[index][field]["raw_date"]+=1
            path.write_bytes(b"".join(data(e) for e in events))
            self.capture("speed3",dict(status="completed_and_paused",report="synthetic",before_date=events[0]["before"]["raw_date"],after_date=events[1]["after"]["raw_date"]))
            self.refresh_final()
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"callback/lease/adjacent frames/supervisor"):
                self.run_review()
    def test_inactive_deadline_must_equal_latest_armed_deadline(self):
        self.append_speed();original=deepcopy(self.events)
        self.assertGreater(self.events[-1]["lease_deadline_uptime_ms"],0)
        for value in (0,self.events[-1]["lease_deadline_uptime_ms"]+1):
            self.events=deepcopy(original);self.events[-1]["lease_deadline_uptime_ms"]=value;self.refresh_speed()
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,"most recent armed lease"):self.run_review()
    def test_consistent_deadline_cannot_be_created_after_following_frame(self):
        self.append_speed()
        for e in self.events:
            if e["event"]=="lab_lease_armed":e["deadline_uptime_ms"]+=500
            if e["event"]=="research_frame" and e["last_sequence"]==3:e["lease_deadline_uptime_ms"]+=500
        path=self.session/"00000000000000000003.lease-pause.claim"
        claim=json.loads(path.read_bytes());claim["deadline_uptime_ms"]+=500;path.write_bytes(data(claim))
        self.refresh_speed()
        with self.assertRaisesRegex(ValueError,"creation after its following frame"):self.run_review()
    def test_unbound_deadline_before_first_lease_rejects(self):
        self.events[-1]["lease_deadline_uptime_ms"]=12345
        self.capture("status2",self.status(2));self.refresh_final()
        with self.assertRaisesRegex(ValueError,"most recent armed lease"):self.run_review()
    def test_multiple_leases_replace_then_retain_only_latest_deadline(self):
        self.append_speed();self.append_speed(4);self.assertEqual(len(self.run_review()["requests"]),4)
        prior=next(e["deadline_uptime_ms"] for e in self.events if e["event"]=="lab_lease_armed" and e["sequence"]==3)
        self.events[-1]["lease_deadline_uptime_ms"]=prior;self.capture("status4",self.status(4));self.refresh_final()
        with self.assertRaisesRegex(ValueError,"most recent armed lease"):self.run_review()
    def test_older_exact_status_with_normal_exit_healthy_tail_is_valid(self):
        old=json.loads((self.root/"final.json").read_bytes());frame=deepcopy(self.events[-1])
        frame["frames"]+=1;frame["uptime_ms"]+=1;self.events.append(frame);self.refresh_final()
        self.write_artifact("final","final.json",old)
        self.assertEqual(self.run_review()["status"],"reviewed_stopped_session")
    def test_real_four_phase_and_typed_observer_pipeline(self):
        result=self.run_review();self.assertEqual(result["observed_effect_count"],1);self.assertEqual(result["phase_case_counts"],r.COUNTS)
        for k in ("production_execution_verified","game_process_accessed","save_reload_verified","white_peace_verified","request_id_causality_verified"):self.assertIs(result[k],False)
    def test_absent_transition_is_unknown_not_ai_rejection(self):
        self.write_effect(False)
        self.case["annotations"]=[dict(sequence=2,source="root_ui_annotation",text="UI refusal noted by root",native_evidence=False)]
        result=self.run_review();self.assertEqual(result["observed_effect_count"],0);self.assertFalse(result["effects"][0]["native_rejection_verified"])
    def test_sequence_bool_and_skipped_request_reject(self):
        original=deepcopy(self.case)
        for value in (True,1.0,2):
            self.case=deepcopy(original);self.case["requests"][0]["sequence"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.run_review()
    def test_legality_requires_explicit_same_pair_and_day(self):
        original=deepcopy(self.case)
        for value in (None,True,1.0,0,2):
            self.case=deepcopy(original);self.case["requests"][1]["legality_sequence"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.run_review()
    def test_hidden_pending_file_and_missing_inventory_fail(self):
        (self.session/"00000000000000000003.request").write_bytes(b"pending")
        with self.assertRaises(ValueError):self.run_review()
    def test_typed_status_alias_rejected(self):
        path=self.root/"status2.json";doc=json.loads(path.read_bytes());doc["report"]["latest_frame"]["last_sequence"]=2.0
        self.write_artifact("status2","status2.json",doc)
        with self.assertRaises(ValueError):self.run_review()
    def test_cached_tail_frame_numeric_alias_reject(self):
        original=deepcopy(self.events)
        for key,value in (("thread",float(r.THREAD)),("last_sequence",2.0),("session_frozen",0),("pid",float(r.PID))):
            self.events=deepcopy(original);self.events[-1][key]=value
            # Frozen host may reject some first, but reviewer must reject all.
            with self.subTest(key=key),self.assertRaises(ValueError):self.refresh_final();self.run_review()
    def test_owned_default_core_cannot_be_removed_from_prefix(self):
        key=self.case["session_files"]["phase-owned-peace-lifecycle.claim"]
        self.inputs[key]["sha256"]="0"*64
        with self.assertRaises(ValueError):self.run_review()
    def test_unknown_ownership_or_missing_nullable_is_rejected(self):
        for key,value in (("ownership_uncertain",True),("exception",False),("phase",13.0)):
            value_row=dict(request=dict(operation="pair",mode="submit",action="embargo",actor="FRA",target="POR",pid=r.PID,creation=r.CREATION),records=[core(submit=True,event=n) for n in ("pair_engine_begin","pair_engine_dispatch_intent","pair_engine_complete")],complete={})
            value_row["records"][-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_pair(value_row,"dispatched",observer)
        record=core();del record["context_submit_return"]
        with self.assertRaises(ValueError):r.strict_pair(record)
    def test_effect_wrong_direction_or_second_pass_alias_reject(self):
        before=json.loads((self.root/"before-effect.json").read_bytes())
        before["family_snapshot"]["observation"]["passes"][1]["embargo"]["outgoing"]["flags_46"]=False
        self.write_artifact("before","before-effect.json",before)
        with self.assertRaises(ValueError):self.run_review()
    def test_ui_note_cannot_supply_effect_or_be_native(self):
        self.case["annotations"]=[dict(sequence=2,source="root_ui_annotation",text="declined",native_evidence=True)]
        with self.assertRaises(ValueError):self.run_review()
    def test_missing_effect_case_is_not_silent_success(self):
        self.case["effects"]=[]
        with self.assertRaises(ValueError):self.run_review()
    def test_save_reload_claim_is_explicitly_unsupported(self):
        self.case["persistence"]=[{"save":"guessed"}]
        with self.assertRaises(ValueError):self.run_review()
    def test_hash_changed_before_read_and_after_freeze(self):
        path=self.root/"before-effect.json";path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaises(ValueError):r.Inputs(self.root,self.inputs)
    def test_duplicate_paths_and_bool_selector_reject(self):
        entries={"a":dict(path="list.json",size_bytes=3,sha256=r.sha(b"[]\n"))};(self.root/"list.json").write_bytes(b"[]\n")
        with self.assertRaises(ValueError):r.Inputs(self.root,entries|{"b":entries["a"]})
        self.write_artifact("list","list.json",[{},{}]);i=r.Inputs(self.root,{"list":self.inputs["list"]})
        for index in (True,0.0,-1,2):
            with self.subTest(index=index),self.assertRaises(ValueError):i.selected({"input":"list","select":[index]})
    def test_supervised_running_lease_full_native_replay(self):
        self.append_speed();result=self.run_review();self.assertEqual(result["requests"][-1]["outcome"],"completed_and_paused")
    def test_supervisor_missing_or_termination_cannot_pass(self):
        self.append_speed();path=self.session/"00000000000000000003.supervisor.jsonl"
        events=[json.loads(line) for line in path.read_bytes().splitlines()];events[-1]["event"]="supervisor_stopped_disposable_process"
        path.write_bytes(b"".join(data(e) for e in events));self.refresh_final()
        with self.assertRaises(ValueError):self.run_review()
    def test_automatic_pause_bool_exception_alias_is_rejected(self):
        self.append_speed()
        event=next(e for e in reversed(self.events) if e["event"]=="lab_native_record" and e["lease_pause"])
        event["record"]["exception_code"]=False
        self.refresh_final()
        with self.assertRaises(ValueError):self.run_review()
    def test_legality_other_target_or_date_does_not_authorize_submit(self):
        self.write_log();rows=lab.read_evidence(self.session,self.metadata)["requests"]
        for field,value in (("target","ENG"),("raw_date",r.INITIAL_DATE+1)):
            changed=deepcopy(rows)
            if field=="target":changed[1]["request"][field]=value
            else:changed[1]["records"][-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):r.validate_legality_link(self.case["requests"][1],changed,{x["sequence"]:x for x in self.case["requests"]},observer)
    def test_exit_pid_reuse_or_bool_exit_code_reject(self):
        original=json.loads((self.root/"exit.json").read_bytes())
        for key,value in (("process_creation_filetime",float(int(r.CREATION,16))),("exit_code",False),("process_stop_requested_by_observer",True),("executable_sha256","0"*64)):
            row=dict(original);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_exit(row)
    def test_original_destroyed_at_begin_is_not_valid_ownership_trace(self):
        self.write_log();row=deepcopy(lab.read_evidence(self.session,self.metadata)["requests"][2]);row["records"][0]["original_destroyed"]=True
        with self.assertRaises(ValueError):r.validate_pair(row,"dispatched",observer)
    def test_all_ten_bindings_all_four_targets_shared_checker(self):
        for action,(_,positive) in observer.ACTIONS.items():
            for target in observer.legacy.TARGETS:
                before=obsfixture.snapshot(action,not positive,target=target);after=obsfixture.snapshot(action,positive,True,target=target)
                self.assertTrue(observer.compare_reports(before,after)["observed_effect"])

class HelperTests(unittest.TestCase):
    def test_speed_begin_all_zero_output_members_and_types(self):
        c=dict(event="test_speed_begin",thread_id=r.THREAD,requested_speed=5,reason=0,before_date=r.INITIAL_DATE,before_native_index=0,before_paused=True,
            write_entered=False,callback_returned=False,callback_success=False,result_destroyed=False,readback_observed=False,after_date=0,after_native_index=0,
            after_paused=False,readback_matches=False,exception_code=0,freeze_session=False,retry_allowed=False,diplomacy_submitted=False)
        r.validate_controls(c,5)
        for k in ("write_entered","callback_returned","callback_success","result_destroyed","readback_observed","readback_matches","after_paused","after_date","after_native_index"):
            bad=dict(c);bad[k]=True if type(c[k]) is bool else 1
            with self.subTest(field=k),self.assertRaisesRegex(ValueError,"Speed begin already owns"):r.validate_controls(bad,5)
        for k in ("before_date","before_native_index","after_date","after_native_index"):
            for v in (float(c[k]),bool(c[k])):
                bad=dict(c);bad[k]=v
                with self.subTest(field=k,value=v),self.assertRaisesRegex(ValueError,"schema/types"):r.validate_controls(bad,5)
    def test_template_is_not_finalized_and_create_new_never_overwrites(self):
        self.assertFalse(r.template()["finalized"])
        with self.assertRaises(ValueError):r.review(r.template())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"out.json";r.write_new(p,{"a":1})
            with self.assertRaises(FileExistsError):r.write_new(p,{"a":2})
    def test_every_frame_scalar_alias_rejected(self):
        base=pref.ReviewTests();base.setUp()
        try:
            frame=base.status["latest_frame"]
            for key in r.FRAME_INTS:
                bad=deepcopy(frame);bad[key]=float(bad[key])
                with self.subTest(key=key),self.assertRaises(ValueError):r.strict_frame(bad)
            for key in r.FRAME_BOOLS:
                bad=deepcopy(frame);bad[key]=int(bad[key])
                with self.subTest(key=key),self.assertRaises(ValueError):r.strict_frame(bad)
        finally:base.doCleanups()
    def test_controls_failure_and_bool_numeric_rejected(self):
        c=dict(event="test_speed_complete",thread_id=r.THREAD,requested_speed=0,reason=0,before_date=r.INITIAL_DATE,before_native_index=4,before_paused=False,write_entered=True,callback_returned=True,callback_success=True,result_destroyed=True,readback_observed=True,after_date=r.INITIAL_DATE,after_native_index=0,after_paused=True,readback_matches=True,exception_code=0,freeze_session=False,retry_allowed=False,diplomacy_submitted=False)
        r.validate_controls(c,0)
        for key,value in (("exception_code",False),("result_destroyed",False),("freeze_session",True),("after_native_index",0.0)):
            bad=dict(c);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_controls(bad,0)

if __name__=="__main__":unittest.main(verbosity=2)
