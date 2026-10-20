"""Synthetic temp-file evidence; never a process handle or actual session log."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
r=load("v17_exp_reviewer_under_test",HERE/"reviewer.py");lab=r.lab
old=load("v17_exp_prior_synthetic_data",ROOT/"work/candidates/v14-directional-preflight-review/test_reviewer.py")
directional=load("v17_exp_directional_synthetic_data",ROOT/"work/candidates/directional-pair-observer-1375/test_observer.py")
insult=load("v17_exp_insult_synthetic_data",ROOT/"work/candidates/ordinary-insult-observer-1375/test_observer.py")
accept_fixture=load("v17_exp_acceptance_synthetic_data",ROOT/"work/candidates/v17-acceptance-pin-review/test_candidate.py")
def data(x):return (json.dumps(x,sort_keys=True)+"\n").encode()


class Fixture(unittest.TestCase):
    def setUp(self):
        # Only the predecessor's synthetic data factory is used. It reads its
        # frozen disk build as a fixture seed, never an actual case/session log.
        seed=old.ReviewTests();seed.setUp();self.addCleanup(seed.doCleanups)
        self.root=seed.root;self.seed=seed
        self.metadata=deepcopy(seed.f.metadata);self.metadata["purpose"]=lab.PURPOSE
        self.events=deepcopy(seed.events)
        for e in self.events:
            if e["event"]=="research_frame":e.update(acceptance_flag=0,acceptance_state="closed",acceptance_origin_sequence=0,
                acceptance_submit_sequence=0,acceptance_off_sequence=0,acceptance_action="none",acceptance_target="none")
        prefix=b"".join(data(e) for e in self.events);self.prefix=prefix;self.prefix_count=len(self.events)
        self.scope=dict(pid=self.metadata["pid"],creation=self.metadata["process_creation_filetime"],
            world_cookie=self.events[-1]["world_cookie"],window_thread=self.metadata["window_thread"],initial_raw_date=self.events[-1]["raw_date"],
            dll_sha256="a"*64,manifest_sha256="b"*64,bridge_start_rva=0x59c0,prefix_bytes=len(prefix),prefix_sha256=r.digest(prefix),
            preflight_case="work/runtime/native1375-v17/synthetic-preflight-case.json",preflight_summary="work/runtime/native1375-v17/synthetic-preflight-summary.json")
        self.b,self.pre=r.configure(self.scope)
        build=dict(seed.build,purpose=lab.PURPOSE,schema_version=3,protocol_version=lab.PROTOCOL,dll_sha256="A"*64,
            bridge_start_export_rva=0x59c0,source_sha256=dict.fromkeys(lab.SOURCES,"c"*64),
            host_source_sha256=dict.fromkeys(lab.HOST_SOURCES,"d"*64),support_source_sha256=dict.fromkeys(lab.SUPPORT_SOURCES,"e"*64))
        self.enterContext(patch.object(lab,"verify_build",return_value=(build,"b"*64)))
        self.enterContext(patch.object(lab,"LiveLabProcess",side_effect=AssertionError("No game access")))
        self.enterContext(patch.object(lab,"publish_research",side_effect=AssertionError("No publication")))
        self.enterContext(patch.object(r,"configure",side_effect=self.configured))
        self.case=r.template();self.case.update(finalized=True,scope=deepcopy(self.scope));self.inputs=self.case["inputs"]
        self.session=self.root/self.b.SESSION;self.session.mkdir(parents=True)
        self.prefix_dir=self.root/"prefix-v17";self.prefix_dir.mkdir()
        for path in (self.session,self.prefix_dir):
            for name in ("session.json","install.claim"):(path/name).write_bytes(data(self.metadata))
            for phase,(_,claim,_) in lab.PHASES.items():(path/claim).write_bytes(lab.phase_wire(phase,self.metadata))
            (path/"research-1375.jsonl").write_bytes(prefix)
        for phase,(_,claim,_) in lab.PHASES.items():
            (self.session/(claim+".host-intent")).write_bytes(data(self.host(lab.phase_wire(phase,self.metadata))))
        before,after=deepcopy(seed.before),deepcopy(seed.after)
        loader=deepcopy(seed.loader);loader.update(purpose=lab.PURPOSE,dll_sha256="A"*64,manifest_sha256="b"*64)
        loader["installation"]["dll"]=str(self.root/"work/runtime/native1375-v17"/lab.DLL_NAME)
        pref_inputs={}
        for name in self.pre.FILES:
            raw=(self.prefix_dir/name).read_bytes();pref_inputs[name]=dict(path="prefix-v17/"+name,size_bytes=len(raw),sha256=r.digest(raw))
        for name,value in (("before",before),("after",after),("loader",loader),("status",self.status())):
            raw=data(value);(self.root/("prefix-"+name+".json")).write_bytes(raw)
            pref_inputs[name]=dict(path="prefix-"+name+".json",size_bytes=len(raw),sha256=r.digest(raw))
        pc=dict(schema_version=1,purpose="fixed_v17_preflight_case",pid=self.b.PID,creation=self.b.CREATION,world_cookie=self.b.WORLD,
            raw_date=self.b.INITIAL_DATE,window_thread=self.b.THREAD,build_manifest_sha256="b"*64,dll_sha256="a"*64,
            log_prefix_sha256=r.digest(prefix),log_prefix_bytes=len(prefix),reviewer_sha256=r.digest((HERE/"preflight.py").read_bytes()),inputs=pref_inputs)
        self.write_artifact("precase",self.scope["preflight_case"],pc)
        self.write_artifact("presummary",self.scope["preflight_summary"],self.pre.review(pc,root=self.root))
        self.case.update(preflight_case="precase",preflight_summary="presummary")
        for i,desc in enumerate(pref_inputs.values()):self.inputs["preinput"+str(i)]=desc
        self.on=3;self.submit=4;self.off=5
        self.append_fixture()
        self.append_pair("offer_fleet_basing_rights",False)
        self.append_control(True)
        self.append_pair("offer_fleet_basing_rights",True,legality=2)
        self.append_control(False)
        self.case["acceptance_windows"]=[dict(legality_sequence=2,on_sequence=3,submit_sequence=4,off_sequence=5,
            action="offer_fleet_basing_rights",target="POR")]
        self.add_effect(4,"offer_fleet_basing_rights")
        exit_row=dict(pid=self.b.PID,creation=self.b.CREATION,exit_observed=True,method="held_handle_wait_and_getprocesstimes",
            process_exit_filetime=int(self.b.CREATION,16)+1000000,process_creation_filetime=int(self.b.CREATION,16),before_exit_filetime=0,
            wait_status=0,exit_code=0,read_only=True,process_stop_requested_by_observer=False,
            access="QUERY_LIMITED_INFORMATION | SYNCHRONIZE",executable_sha256=lab.LOCAL_SHA256)
        self.write_artifact("exit","exit.json",exit_row);self.case["exit"]={"input":"exit","select":[]}
        self.refresh()

    def configured(self,scope):
        r.validate_scope(scope);r.require(r.same(scope,self.scope),"Synthetic case changed scope")
        return self.b,self.pre
    def write_artifact(self,key,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);raw=value if type(value) is bytes else data(value);path.write_bytes(raw)
        self.inputs[key]=dict(path=name,size_bytes=len(raw),sha256=r.digest(raw));return key
    def host(self,wire):return dict(protocol=lab.PROTOCOL,purpose=lab.PURPOSE,pid=self.b.PID,creation=self.b.CREATION,
        manifest_sha256=self.b.MANIFEST_SHA,request_sha256=r.digest(wire),body_ascii=wire.decode(),automatic_retry=False)
    def event(self,name,seq,**fields):return dict(event=name,pid=self.b.PID,process_creation_filetime=self.b.CREATION,sequence=seq,**fields)
    def write_log(self):(self.session/"research-1375.jsonl").write_bytes(b"".join(data(e) for e in self.events))
    def status(self,sequence=None):
        self.write_log();e=lab.read_evidence(self.session,self.metadata)
        s=dict(purpose=lab.PURPOSE,protocol=lab.PROTOCOL,pid=self.b.PID,creation=self.b.CREATION,dll_sha256="A"*64,manifest_sha256="b"*64,
            latest_frame=e["latest_frame"],phases=e["phases"],last_sequence=e["last_sequence"],pending=e["pending"],lease_pending=e["lease_pending"],
            acceptance_window=e["acceptance_window"],log_sha256=e["log_sha256"],applied_verified=False,production_backend_registered=False,read_only=True)
        if sequence is not None:s["request"]=e["requests"][sequence]
        return s
    def capture(self,key,report):
        self.write_artifact(key,key+".json",dict(purpose="one_explicit_v17_cli_capture",kind="request",arguments=["synthetic"],
            automatic_retry=False,applied_verified=False,exit_code=0,stderr="",report=report))
        return {"input":key,"select":["report"]}
    def start(self,operation,action,mode="submit",**fields):
        seq=len(self.case["requests"])+1;pub=self.status();frame=pub["latest_frame"]
        request=dict(pid=self.b.PID,creation=self.b.CREATION,sequence=seq,expires=frame["uptime_ms"]+60000,
            operation=operation,mode=mode,action=action,actor="FRA",target="POR" if operation=="pair" else "FRA",speed=0,
            bound_action="none",bound_target="none",bound_submit_sequence=0);request.update(fields)
        wire=lab.encode_request(request);stem=f"{seq:020}"
        (self.session/(stem+".claim")).write_bytes(wire);(self.session/(stem+".host-intent")).write_bytes(data(self.host(wire)))
        pub["publication"]=dict(research_only=True,protocol=lab.PROTOCOL,status="published",request_sha256=r.digest(wire),pid=self.b.PID,
            creation=self.b.CREATION,sequence=seq,phase=None,native_dispatch_verified=False,applied_verified=False,automatic_retry=False,production_backend_registered=False)
        pubref=self.capture("pub"+str(seq),pub)
        self.events.append(self.event("lab_request_claimed",seq,**{k:v for k,v in request.items() if k not in ("pid","creation","sequence")},
            durable_claim=True,retry_allowed=False,claimed_uptime_ms=frame["uptime_ms"]+1))
        return request,frame,pubref
    def health(self,seq,prior,state=None,flag=None):
        f=deepcopy(prior);f.update(last_sequence=seq,frames=f["frames"]+10,uptime_ms=f["uptime_ms"]+10,send_enabled=True)
        if state is not None:
            f.update(acceptance_flag=flag,acceptance_state=state,acceptance_origin_sequence=self.on,acceptance_submit_sequence=self.submit,
                acceptance_off_sequence=self.off,acceptance_action="offer_fleet_basing_rights",acceptance_target="POR")
        self.events.append(f)
    def finish(self,request,pubref,outcome,legality=None):
        seq=request["sequence"]
        self.case["requests"].append(dict(sequence=seq,request={k:request[k] for k in lab.FIELDS[4:]},outcome=outcome,legality_sequence=legality,
            publication=pubref,status=self.capture("status"+str(seq),self.status(seq))))
    def core(self,action,submit,event,date):
        b=self.b;d={k:0 for k in b.PAIR_INTS}|{k:False for k in b.PAIR_BOOLS}|{k:None for k in b.PAIR_NULLABLE}
        d.update(event=event,action_id=action,actor="FRA",target="POR",pid=b.PID,thread_id=b.THREAD,process_creation_filetime=b.CREATION,
            world=b.WORLD,actor_handle="0x0100007a00415246",target_handle="0x010000bd00524f50",raw_date=date,envoy_id=-1,
            status=2 if submit else 1,phase=13 if submit else 8,preview_called=True,preview_allowed=True,gate_called=True,gate_allowed=True,
            original_destroyed=True,command_destroyed_before_dispatch=not submit,submit_entered=submit,submit_returned=submit,
            context_submit_return=True if submit else None,caller_container_consumed=True if submit else None,
            fixed_insult_index=-1 if action=="insult" else 0)
        if event=="pair_engine_begin":
            d.update({k:False for k in b.PAIR_BOOLS});d.update(status=0,phase=2,context_submit_return=None,caller_container_consumed=None)
        elif event=="pair_engine_dispatch_intent":d.update(status=0,phase=11,submit_entered=False,submit_returned=False,
            command_destroyed_before_dispatch=False,context_submit_return=None,caller_container_consumed=None)
        return d
    def append_pair(self,action,submit,legality=None):
        req,frame,pub=self.start("pair",action,"submit" if submit else "legality_only");seq=req["sequence"]
        names=["pair_engine_begin"]+(["pair_engine_dispatch_intent"] if submit else [])+["pair_engine_complete"]
        for name in names:self.events.append(self.event("lab_native_record",seq,lease_pause=False,record=self.core(action,submit,name,frame["raw_date"])))
        final=self.events[-1]["record"]
        self.events.append(self.event("lab_request_complete",seq,operation="pair",action=action,
            **{k:final[k] for k in ("status","reason","submit_entered","submit_returned","ownership_uncertain")},
            session_frozen=False,applied_verified=False,retry_allowed=False,audit_complete=True))
        self.health(seq,frame,"submitted_known" if seq==self.submit else None,1 if seq==self.submit else None)
        self.finish(req,pub,"dispatched" if submit else "legality_allowed",legality)
    def append_control(self,on):
        req,frame,pub=self.start("accept","accept_on" if on else "accept_off",bound_action="offer_fleet_basing_rights",bound_target="POR",bound_submit_sequence=self.submit)
        seq=req["sequence"]
        if on:
            self.events.append(self.event("lab_acceptance_pending",seq,bound_action=req["bound_action"],bound_target="POR",bound_submit_sequence=self.submit,
                off_sequence=self.off,uptime_ms=frame["uptime_ms"]+2,legality_sequence=self.on-1,legality_expires=self.case_request(self.on-1)["expires"],native_invoked=False,retry_allowed=False))
        complete=accept_fixture.core(on);complete.update(thread_id=self.b.THREAD,before_date=frame["raw_date"],after_date=frame["raw_date"])
        begin=deepcopy(complete);begin.update(event="test_acceptance_begin",after_raw_flag=None,no_native=True,after_date=0)
        begin.update({k:False for k in r.acceptance.SUCCESS_FIELDS});begin.update(stage=r.acceptance.BEGIN_STAGE,zero_arguments_confirmed=True)
        for c in (begin,complete):self.events.append(self.event("lab_native_record",seq,lease_pause=False,record=c))
        wrapper={k:v for k,v in complete.items() if k not in ("event","operation","thread_id")}
        wrapper.update(operation="accept",action=req["action"],completion_frame=frame["frames"]+1,session_frozen=False,
            applied_verified=False,natural_ai_acceptance_verified=False)
        self.events.append(self.event("lab_request_complete",seq,**wrapper));self.health(seq,frame,"armed" if on else "closed",1 if on else 0)
        self.finish(req,pub,"acceptance_enabled" if on else "acceptance_disabled")
    def case_request(self,seq):return lab.decode_request((self.session/f"{seq:020}.claim").read_bytes())
    def append_fixture(self):
        req,frame,pub=self.start("fixture","fixture_on");seq=req["sequence"]
        (self.session/f"{seq:020}.fixture-profile").write_bytes(lab.fixture_proof_wire(self.metadata,seq))
        flags=("native_invoked","callback_returned","callback_success","arguments_unchanged","result_destroyed","world_identity_unchanged","callback_flag_restored")
        c=dict(thread_id=self.b.THREAD,fixture_event="llmt.1",target="FRA",fixture_profile_sha256=lab.FIXTURE_PROFILE_SHA256,
            reason=0,before_date=frame["raw_date"],after_date=frame["raw_date"],exception_code=0,freeze_session=False,retry_allowed=False,
            fixture_effect_verified=False,diplomacy_submitted=False,**dict.fromkeys(flags,True))
        for core in (dict(c,event="test_fixture_begin",after_date=0,**dict.fromkeys(flags,False)),dict(c,event="test_fixture_complete")):
            self.events.append(self.event("lab_native_record",seq,lease_pause=False,record=core))
        self.events.append(self.event("lab_request_complete",seq,operation="fixture",action="fixture_on",reason=0,
            session_frozen=False,fixture_effect_verified=False,applied_verified=False,retry_allowed=False,**dict.fromkeys(flags,True)))
        self.health(seq,frame);self.finish(req,pub,"fixture_callback_returned")
    def append_speed(self):
        req,frame,pubref=self.start("speed","none",speed=5);seq=req["sequence"];stem=f"{seq:020}"
        start=frame["raw_date"];end=start+48;deadline=frame["uptime_ms"]+5001
        publication=json.loads((self.root/("pub"+str(seq)+".json")).read_bytes())["report"]
        (self.session/(stem+".publisher-output.txt")).write_bytes(data(publication))
        del self.inputs["pub"+str(seq)]
        def core(speed,date,event):
            done=event=="test_speed_complete"
            return dict(event=event,thread_id=self.b.THREAD,requested_speed=speed,reason=0,before_date=date,
                before_native_index=0 if speed else 4,before_paused=speed!=0,write_entered=done,callback_returned=done,callback_success=done,
                result_destroyed=done,readback_observed=done,after_date=date if done else 0,after_native_index=min(speed,4) if done else 0,
                after_paused=speed==0 and done,readback_matches=done,exception_code=0,freeze_session=False,retry_allowed=False,diplomacy_submitted=False)
        self.events.append(self.event("lab_lease_armed",seq,deadline_uptime_ms=deadline,maximum_raw_date_delta=48,
            initial_raw_date=start,automatic_pause=True,reliable_generation_verified=False))
        for name in ("test_speed_begin","test_speed_complete"):self.events.append(self.event("lab_native_record",seq,lease_pause=False,record=core(5,start,name)))
        self.events.append(self.event("lab_request_complete",seq,operation="speed",speed=5,reason=0,write_entered=True,callback_returned=True,
            readback_matches=True,session_frozen=False,applied_verified=False,retry_allowed=False))
        running=deepcopy(frame);running.update(frames=frame["frames"]+10,uptime_ms=frame["uptime_ms"]+10,last_sequence=seq,
            lease_active=True,lease_deadline_uptime_ms=deadline,paused=False,native_speed_index=4,mailbox_ready=False)
        self.events.append(running)
        advanced=deepcopy(running);advanced.update(frames=running["frames"]+1,uptime_ms=running["uptime_ms"]+1,raw_date=end);self.events.append(advanced)
        for name in ("test_speed_begin","test_speed_complete"):self.events.append(self.event("lab_native_record",seq,lease_pause=True,record=core(0,end,name)))
        lease=self.event("lab_lease_complete",seq,reason=0,write_entered=True,callback_returned=True,paused_readback=True,readback_matches=True,session_frozen=False,retry_allowed=False)
        self.events.append(lease)
        paused=deepcopy(advanced);paused.update(frames=advanced["frames"]+1,uptime_ms=advanced["uptime_ms"]+1,lease_active=False,
            paused=True,native_speed_index=0,mailbox_ready=True);self.events.append(paused)
        (self.session/(stem+".lease-pause.claim")).write_bytes(data(dict(purpose="bounded_running_lease_pause",pid=self.b.PID,
            process_creation_filetime=self.b.CREATION,origin_sequence=seq,speed=0,deadline_uptime_ms=deadline,maximum_raw_date_delta=48,retry_allowed=False)))
        state=dict(game=int(self.b.WORLD,16),server=0x123450000,pause_manager=0x123451000,player=int("0100007a00415246",16),raw_date=start,paused=True,native_speed_index=0)
        armed=dict(event="supervisor_armed",pid=self.b.PID,creation=self.b.CREATION,sequence=seq,speed=5,retry_allowed=False,deadline_seconds=12.0,before=state)
        complete=dict(event="supervisor_complete",pid=self.b.PID,creation=self.b.CREATION,sequence=seq,speed=5,retry_allowed=False,
            after=dict(state,raw_date=end),elapsed_seconds=4.0,native_lease_complete=lease)
        (self.session/(stem+".supervisor.jsonl")).write_bytes(data(armed)+data(complete))
        receipt=self.capture("speed"+str(seq),dict(status="completed_and_paused",report="synthetic",before_date=start,after_date=end))
        self.finish(req,receipt,"completed_and_paused")
    def add_effect(self,seq,action,positive=True):
        date=self.status(seq)["request"]["records"][-1]["raw_date"]
        if action=="insult":
            docs=[insult.Fixture(active=False,trust=50).report(),insult.Fixture(active=True,trust=45 if positive else 50).report()]
            for doc in docs:
                doc["source"]["expected_creation"]=self.b.CREATION
                for key in ("before","after"):doc["source"][key].update(pid=self.b.PID,creation_filetime=int(self.b.CREATION,16))
                for p in doc["observation"]["passes"]:p["snapshot"]["identity"].update(world=self.b.WORLD,raw_date=date)
            compare=insult.o.compare_reports
        else:
            value=directional.candidate.ACTIONS[action][1]
            docs=[directional.snapshot(action,not value),directional.snapshot(action,value if positive else not value,True)]
            for doc in docs:
                doc["expected_pid"]=self.b.PID;doc["expected_creation"]=self.b.CREATION
                raw=doc["family_snapshot"];raw["source"].update(pid=self.b.PID,process_creation_filetime=int(self.b.CREATION,16))
                for sample in raw["observation"]["passes"]:
                    sample.update(game=self.b.WORLD,current_raw_date=date)
                    obj=sample.get("relation",{}).get("object")
                    if obj is not None:obj["started_raw_date"]=date
                raw["observation"]["state"]=directional.candidate.legacy.inspect_state(raw["observation"]["passes"][0])
            compare=directional.candidate.compare_reports
        keys=[]
        for label,doc in zip(("before","after"),docs):keys.append(self.write_artifact(label+str(seq),label+str(seq)+".json",doc))
        comparison=compare(*docs)
        comparison["input_hashes" if action=="insult" else "inputs"]={label if action=="insult" else label+"_sha256":self.inputs[key]["sha256"] for label,key in zip(("before","after"),keys)}
        key=self.write_artifact("compare"+str(seq),"compare"+str(seq)+".json",comparison)
        self.case["effects"]=[e for e in self.case["effects"] if e["sequence"]!=seq]+[dict(sequence=seq,before=keys[0],after=keys[1],comparison=key,expected_observed_effect=positive)]
    def refresh(self):
        self.case["final_status"]=self.capture("final",self.status());files={}
        for i,path in enumerate(sorted(self.session.iterdir())):
            key="session"+str(i);files[path.name]=key;raw=path.read_bytes();self.inputs[key]=dict(path=path.relative_to(self.root).as_posix(),size_bytes=len(raw),sha256=r.digest(raw))
        self.case["session_files"]=files
        audit=dict(pid=self.b.PID,creation=self.b.CREATION,process_exit_filetime=int(self.b.CREATION,16)+1000000,
            complete_log=self.inputs[files["research-1375.jsonl"]],session_files={n:self.inputs[k] for n,k in files.items()},stopped=True)
        self.write_artifact("audit","audit.json",audit);self.case["stopped_audit"]={"input":"audit","select":[]}
    def run_review(self):return r.review(self.case,root=self.root)
