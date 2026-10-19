"""Offline counterexamples for the finalized v12 reviewer; no process access."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from work import verify_v12_experiment_1375 as review
from bridge.tests import test_pair_extension_v11_probe as samples


def pair(action="request_trade_power", outcome="dispatched", target="POR"):
    submit = outcome == "dispatched"
    request = dict(pid=review.PID, creation=review.CREATION, sequence=3, expires=12345,
        operation="pair", mode="submit" if submit else "legality_only", action=action, actor="FRA", target=target, speed=0)
    final = dict(event="pair_engine_complete", pid=review.PID, process_creation_filetime=review.CREATION,
        thread_id=review.THREAD, world=review.WORLD, actor="FRA", target=target, action_id=action,
        actor_handle=hex(review.observer.HANDLES["FRA"]), target_handle=hex(review.observer.HANDLES[target]), raw_date=samples.DATE,
        fixed_subsidy_amount_milli=0, fixed_subsidy_duration_years=0,
        fixed_gift_amount_milli=25000 if action == "send_gift" else 0,
        fixed_transfer_fraction_milli=500 if action in ("request_trade_power", "cancel_trade_power_transfer") else 0,
        fixed_insult_index=-1 if action == "insult" else 0,
        status=2 if submit else 1, reason=0, phase=13 if submit else 8, exception=0,
        original_destroyed=True, ownership_uncertain=False, freeze_session=False, applied_verified=False, retry_allowed=False,
        submit_entered=submit, submit_returned=submit, command_destroyed_before_dispatch=not submit,
        preview_called=True, preview_allowed=True, gate_called=True, gate_allowed=True,
        context_submit_return=True if submit else None, caller_container_consumed=True if submit else None)
    if outcome == "legality_rejected":
        final.update(reason=17, phase=6, preview_allowed=False, gate_called=False, gate_allowed=False, command_destroyed_before_dispatch=False)
    if outcome == "guard_rejected":
        final.update(status=0, reason=13, phase=3, preview_called=False, preview_allowed=False, gate_called=False,
                     gate_allowed=False, original_destroyed=False, command_destroyed_before_dispatch=False)
    names = ["pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete"] if submit else ["pair_engine_begin", "pair_engine_complete"]
    return dict(request=request, records=[dict(final, event=name) for name in names],
        complete={k: final[k] for k in ("status", "reason", "submit_entered", "submit_returned", "ownership_uncertain")})


def observed(action, active, after=False, gift_amount=25000):
    mem = samples.fixture(action, active=active, target="POR")
    if action == "giftaction" and after:
        mem.write_fixture(samples.FRA+0xBB0, 100000-gift_amount, 4)
        mem.write_fixture(samples.TARGET+0xBB0, 200000+gift_amount, 4)
    value = samples.report(mem, action, target="POR", after=after)
    value["source"].update(pid=review.PID, process_creation_filetime=int(review.CREATION, 16))
    for sample in value["observation"]["passes"]:
        sample["game"] = review.WORLD
    return value


def comparison(before, after, action):
    family, direction = review.EFFECTS[action]
    expected = {"expected_fraction_milli": 500} if family == "transfer_trade_power" else {"expected_amount_milli": 25000} if action == "send_gift" else {}
    hashes = dict(before_sha256="a"*64, after_sha256="b"*64)
    result = dict(review.observer.compare_reports(before, after, direction, **expected), inputs=hashes)
    return {"expected": expected}, result, hashes


def held_reload_documents(observed):
    sample=observed["observation"]["passes"][0];source=observed["source"]
    creation=f'{source["process_creation_filetime"]:016x}'
    bound=dict(pid=source["pid"],creation=creation,world_cookie=sample["game"],player_handle=sample["player"]["handle"],raw_date=sample["current_raw_date"])
    identity=dict(schema_version=1,read_only=True,build=dict(sha256=review.lab.LOCAL_SHA256),
        offset_profile=dict(database_pointer_rva="0x233d8d0",game_pointer_rva="0x233fe78"),
        source=dict(kind="live_process",pid=source["pid"],process_creation_filetime=source["process_creation_filetime"],process_exit_filetime=0,
            access=["PROCESS_QUERY_INFORMATION","PROCESS_VM_READ"],held_identity_verified_before_and_after=True,module_base=source["module_base"]),
        state=dict(status="bounded_snapshot",game_pointer=sample["game"],database_pointer=sample["database"],country_array=sample["country_array"],
            current_raw_date=sample["current_raw_date"],player=sample["player"],countries=list(sample["pair"].values()),
            snapshot_consistency=dict(globals_unchanged=True,player_unchanged=True,date_unchanged=True,atomic=False)),
        identity_before_and_after=[deepcopy(bound),deepcopy(bound)],capture_started_at_utc=observed["capture_started_at"],captured_at_utc=observed["capture_finished_at"])
    stopped=dict(pid=source["pid"],creation=creation,process_creation_filetime=source["process_creation_filetime"],kind="exact_process_exit_observation",
        read_only=True,method="held_handle_wait_and_getprocesstimes",exit_observed=True,
        process_exit_filetime=review.timestamp_filetime("2026-10-08T11:00:00+00:00"),before_exit_filetime=0,wait_status=0,exit_code=0,
        executable_sha256=review.lab.LOCAL_SHA256,access="QUERY_LIMITED_INFORMATION | SYNCHRONIZE",process_stop_requested_by_observer=False)
    return identity,stopped


class V12ReviewTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(review.lab, "LiveLabProcess", side_effect=AssertionError("No live process")))

    def test_unfinalized_refuses_before_any_evidence_or_build_read(self):
        with patch.object(review.lab, "verify_build", side_effect=AssertionError("Must not inspect build")):
            for value in (False, None, 1, "true"):
                with self.assertRaises(ValueError):
                    review.review({"schema_version": 1, "purpose": "v12_finalized_experiment_case_manifest", "finalized": value})

    def test_exit_requires_exact_identity_and_held_handle_observation(self):
        row = dict(pid=review.PID, creation=review.CREATION, process_exit_filetime=int(review.CREATION,16)+10,
                   exit_observed=True, method="held_handle_wait_and_getprocesstimes")
        self.assertEqual(review.validate_exit({"exact_process_exit_observation":row}), row)
        for key, value in (("pid", review.PID+1), ("creation", "01dd56989186135d"), ("exit_observed",1),
                           ("method","operator_observation"), ("process_exit_filetime",True),
                           ("process_exit_filetime",int(review.CREATION,16))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                review.validate_exit(dict(row, **{key:value}))

    def test_artifacts_are_bounded_unique_content_addressed_and_confined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"one.json").write_bytes(b'{"x":1}')
            row=dict(path="one.json",size_bytes=7,sha256=review.sha(b'{"x":1}'))
            inputs=review.Inputs(root,{"one":row})
            self.assertEqual(inputs.doc("one"),{"x":1})
            (root/"one.json").write_bytes(b'{"x":2}')
            with self.assertRaises(ValueError): inputs.raw("one")
            for bad in (dict(row,path="../one.json"),dict(row,path="C:/one.json"),dict(row,path="one//two.json"),
                        dict(row,size_bytes=True),dict(row,size_bytes=review.lab.MAX_LOG+1),dict(row,sha256="A"*64)):
                with self.assertRaises(ValueError): review.Inputs(root,{"one":bad})
            with self.assertRaises(ValueError): review.Inputs(root,{"one":row,"two":row})
            with self.assertRaises(ValueError): review.Inputs(root,{str(i):dict(row,path=f"{i}.json") for i in range(review.MAX_ARTIFACTS+1)})

    def test_guard_rejection_does_not_claim_native_legality_or_cleanup(self):
        row=pair("support_independence","guard_rejected")
        review.validate_pair(row,"guard_rejected")
        for field,value in (("preview_called",True),("original_destroyed",True),("reason",17),("status",1),("submit_entered",True)):
            altered=deepcopy(row);altered["records"][-1][field]=value
            with self.assertRaises(ValueError): review.validate_pair(altered,"guard_rejected")
        with self.assertRaises(ValueError): review.validate_pair(row,"legality_rejected")

    def test_legality_rejection_keeps_status_one_reason_seventeen(self):
        row=pair("form_coalition","legality_rejected")
        review.validate_pair(row,"legality_rejected")
        for field,value in (("status",0),("reason",0),("command_destroyed_before_dispatch",True),("gate_called",True)):
            altered=deepcopy(row);altered["records"][-1][field]=value
            with self.assertRaises(ValueError): review.validate_pair(altered,"legality_rejected")

    def test_native_consumption_required_and_cannot_reclassify_legality(self):
        review.validate_pair(pair(),"dispatched")
        review.validate_pair(pair("insult","legality_allowed"),"legality_allowed")
        for field,value in (("caller_container_consumed",False),("ownership_uncertain",True),
                           ("command_destroyed_before_dispatch",True),("fixed_transfer_fraction_milli",50),
                           ("exception",True),("thread_id",True),("world","0x123456")):
            row=pair();row["records"][-1][field]=value
            with self.assertRaises(ValueError): review.validate_pair(row,"dispatched")
        with self.assertRaises(ValueError): review.validate_pair(pair(outcome="legality_allowed"),"dispatched")

    def test_trade_effect_fixed_500_not_percent_or_postcomputed(self):
        before=observed("transfer_trade_power",False);after=observed("transfer_trade_power",True,True)
        case,comp,hashes=comparison(before,after,"request_trade_power")
        review.validate_effect(case,pair(),before,after,comp,hashes)
        for expected in ({},{"expected_fraction_milli":50},{"expected_fraction_milli":True},{"expected_fraction_milli":500,"derived":True}):
            with self.assertRaises(ValueError):review.validate_effect({"expected":expected},pair(),before,after,comp,hashes)

    def test_cancel_requires_active_before_and_rejects_absent_absent(self):
        before=observed("transfer_trade_power",True);after=observed("transfer_trade_power",False,True)
        case,comp,hashes=comparison(before,after,"cancel_trade_power_transfer")
        row=pair("cancel_trade_power_transfer")
        review.validate_effect(case,row,before,after,comp,hashes)
        before=observed("transfer_trade_power",False)
        case,comp,hashes=comparison(before,after,"cancel_trade_power_transfer")
        with self.assertRaises(ValueError):review.validate_effect(case,row,before,after,comp,hashes)

    def test_gift_expected_is_25000_before_observations_not_the_measured_delta(self):
        before=observed("giftaction",False);after=observed("giftaction",False,True)
        case,comp,hashes=comparison(before,after,"send_gift")
        review.validate_effect(case,pair("send_gift"),before,after,comp,hashes)
        wrong=observed("giftaction",False,True,24000)
        derived=dict(review.observer.compare_reports(before,wrong,expected_amount_milli=24000),inputs=hashes)
        with self.assertRaises(ValueError):review.validate_effect({"expected":{"expected_amount_milli":24000}},pair("send_gift"),before,wrong,derived,hashes)
        row=pair("trade_favors_for_gold")
        with self.assertRaises(ValueError):review.validate_effect(case,row,before,after,comp,hashes)

    def test_saved_absence_needs_complete_container_and_active_direction_is_exact(self):
        doc=dict(parsed_complete=True,read_only=True,evidence_scope="serialized_state_only",runtime_effects_verified=False,
                 actor="FRA",targets=["POR"],global_diplomacy=dict(container_found=True,records=[]))
        review.validate_saved_relation(doc,"steer_trade","POR","absent",None)
        for path in ("container", "complete"):
            bad=deepcopy(doc)
            if path=="container":bad["global_diplomacy"]["container_found"]=False
            else:bad["parsed_complete"]=False
            with self.assertRaises(ValueError):review.validate_saved_relation(bad,"steer_trade","POR","absent",None)
        values=dict(first="POR",second="FRA",start_date="1444.11.11",is_enforced="no",amount="0.500")
        doc["global_diplomacy"]["records"]=[dict(key="transfer_trade_power",entries=[dict(key=k,value=v) for k,v in values.items()])]
        review.validate_saved_relation(doc,"transfer_trade_power","POR","active","1444.11.11")
        with self.assertRaises(ValueError):review.validate_saved_relation(doc,"transfer_trade_power","POR","absent",None)
        doc["global_diplomacy"]["records"]*=2
        with self.assertRaises(ValueError):review.validate_saved_relation(doc,"transfer_trade_power","POR","active","1444.11.11")

    def test_persistence_compares_identity_not_process_addresses(self):
        state=observed("transfer_trade_power",True)["observation"]["state"]
        changed=deepcopy(state);changed["object"]["address"]="0x555555";changed["object"]["vtable"]="0x777777"
        self.assertEqual(review.semantic_state(state),review.semantic_state(changed))
        changed["object"]["first_handle"]="0x100002e00474e45"
        self.assertNotEqual(review.semantic_state(state),review.semantic_state(changed))
        with self.assertRaises(ValueError):review.semantic_state({"state":"unknown"})

    def test_warning_serialized_key_and_outgoing_direction_are_not_trade_flow(self):
        doc=dict(parsed_complete=True,read_only=True,evidence_scope="serialized_state_only",runtime_effects_verified=False,
                 actor="FRA",targets=["POR"],global_diplomacy=dict(container_found=True,records=[dict(key="warning",
                     entries=[dict(key=k,value=v) for k,v in dict(first="FRA",second="POR",start_date="1444.12.3").items()])]))
        review.validate_saved_relation(doc,"warningaction","POR","active","1444.12.3")
        for kind in ("key","reverse","extra","date"):
            altered=deepcopy(doc);record=altered["global_diplomacy"]["records"][0]
            if kind=="key":record["key"]="warningaction"
            if kind=="reverse":record["entries"][0]["value"],record["entries"][1]["value"]="POR","FRA"
            if kind=="extra":record["entries"].append(dict(key="is_enforced",value="no"))
            if kind=="date":record["entries"][2]["value"]="1444.12.2"
            with self.assertRaises(ValueError):review.validate_saved_relation(altered,"warningaction","POR","active","1444.12.3")

    def test_save_hash_stream_is_bounded_and_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"save.eu4";data=b"x"*150000;p.write_bytes(data)
            review.stream_save_hash(p,len(data),review.sha(data))
            with self.assertRaises(ValueError):review.stream_save_hash(p,len(data)-1,review.sha(data))
            with self.assertRaises(ValueError):review.stream_save_hash(p,len(data),"0"*64)

    def test_actual_streaming_save_and_independent_reload_path_can_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); filename="llm_diplomacy_1375_v12_synthetic.eu4"
            raw=b'EU4txt\ndate=1444.11.11 player="FRA" countries={FRA={} POR={}} diplomacy={transfer_trade_power={first="POR" second="FRA" start_date=1444.11.11 amount=0.500 is_enforced=no}}'
            (root/filename).write_bytes(raw)
            saved=review.inspect_save(root/filename,targets=("POR",))
            after=observed("transfer_trade_power",True,True)
            pre=deepcopy(after);pre.update(capture_started_at="2026-10-08T10:00:02+00:00",capture_finished_at="2026-10-08T10:00:02+00:00")
            reloaded=deepcopy(pre)
            reloaded.update(capture_started_at="2026-10-08T10:00:03+00:00",capture_finished_at="2026-10-08T10:00:03+00:00")
            new_creation=f"{int(review.CREATION,16)+100:016x}"
            reloaded["source"].update(pid=review.PID+1,process_creation_filetime=int(new_creation,16))
            for sample in reloaded["observation"]["passes"]:sample["game"]="0x55555000"
            launch=dict(purpose="disposable_1375_test_restart",plan_only=False,new_pid=review.PID+1,
                executable_sha256=review.lab.LOCAL_SHA256,save_sha256=review.sha(raw),save=str(root/filename),loaded_save_verified=False)
            identity,stopped=held_reload_documents(reloaded)
            docs={"save":saved,"pre":pre,"reload":reloaded,"launch":launch,"identity":identity,"exit":stopped}
            entries={}
            for key,value in docs.items():
                data=json.dumps(value).encode();(root/(key+".json")).write_bytes(data)
                entries[key]=dict(path=key+".json",size_bytes=len(data),sha256=review.sha(data))
            inputs=review.Inputs(root,entries)
            spec=dict(filename=filename,size_bytes=len(raw),sha256=review.sha(raw),report="save",pre_save="pre",saved_date="1444.11.11",start_date="1444.11.11",
                reload=dict(snapshot="reload",launch="launch",identity="identity",exit="exit",pid=review.PID+1,creation=new_creation,world="0x55555000",raw_date=samples.DATE))
            result=review.validate_persistence(spec,{},pair(),after,inputs,root)
            self.assertTrue(result["saved_reload_state_consistent"])
            self.assertFalse(result["exact_loaded_file_path_verified"])
            for key,value in (("pid",review.PID),("creation",review.CREATION),("raw_date",samples.DATE+24)):
                bad=deepcopy(spec);bad["reload"][key]=value
                with self.assertRaises(ValueError):review.validate_persistence(bad,{},pair(),after,inputs,root)
            spec["reload"]=None
            self.assertFalse(review.validate_persistence(spec,{},pair(),after,inputs,root)["saved_reload_state_consistent"])

    def test_reload_identity_exit_bounds_and_selected_roots_cannot_be_borrowed(self):
        report=observed("steer_trade",True,True)
        identity,stopped=held_reload_documents(report)
        reload=dict(pid=review.PID,creation=review.CREATION,world=review.WORLD,raw_date=samples.DATE)
        review.validate_reload_identity(identity,stopped,report,reload)
        for mutate in (lambda d:d["source"].update(process_creation_filetime=True),
                       lambda d:d["state"].update(database_pointer="0x123456"),
                       lambda d:d["identity_before_and_after"][-1].update(raw_date=samples.DATE+24),
                       lambda d:d["state"].update(countries=[]),
                       lambda d:d.update(captured_at_utc="2026-10-08T12:00:00+00:00")):
            bad=deepcopy(identity);mutate(bad)
            with self.assertRaises(ValueError):review.validate_reload_identity(bad,stopped,report,reload)
        for key,value in (("pid",review.PID+1),("exit_code",1),("wait_status",True),("process_stop_requested_by_observer",True)):
            with self.assertRaises(ValueError):review.validate_reload_identity(identity,dict(stopped,**{key:value}),report,reload)

    def test_copy_provenance_is_separate_and_cold_launch_uses_complete_creation(self):
        spec=dict(filename="llm_diplomacy_1375_v12_synthetic.eu4",size_bytes=12,sha256="a"*64)
        saved=dict(source=dict(path=spec["filename"]),copy_evidence=dict(source="original.eu4",destination_create_new=True,
            source_identity_before_after_equal=True,size_bytes=12,sha256="A"*64,source_stat=[12,123,456]))
        review.validate_save_copy(saved,spec)
        for key,value in (("destination_create_new",False),("sha256","b"*64),("size_bytes",13),("source_stat",[True,123,456])):
            bad=deepcopy(saved);bad["copy_evidence"][key]=value
            with self.assertRaises(ValueError):review.validate_save_copy(bad,spec)
        reload=dict(pid=review.PID+1,creation=f"{int(review.CREATION,16)+100:016x}")
        launch=dict(schema_version=1,purpose="disposable_save_cold_reload_read_only",new_pid=reload["pid"],
            executable_sha256=review.lab.LOCAL_SHA256,save_sha256=spec["sha256"],save=spec["filename"],loaded_save_verified=False,
            previous_eu4_process_absent=True,native_injected=False,creation=reload["creation"],process_creation_filetime=int(reload["creation"],16))
        review.validate_launch(launch,spec,reload)
        for key,value in (("creation",review.CREATION),("process_creation_filetime",True),
                          ("native_injected",True),("previous_eu4_process_absent",False),("loaded_save_verified",True)):
            with self.assertRaises(ValueError):review.validate_launch(dict(launch,**{key:value}),spec,reload)

    def test_http_replay_uses_same_canonical_intent_and_never_second_write(self):
        row=pair();wire=review.lab.encode_request(row["request"]);host={"request_sha256":review.sha(wire)}
        request={k:row["request"][k] for k in ("pid","creation","sequence","mode","action","actor","target")}
        request.update(protocol=review.lab.PROTOCOL,ttl_ms=5000)
        intent=dict(kind="eu4_lab_v12_research_http",request=request,request_sha256=review.sha(review.canonical(request).encode("ascii")),
                    manifest_sha256=review.MANIFEST_SHA,automatic_retry=False)
        base=dict(pid=review.PID,creation=review.CREATION,purpose=review.lab.PURPOSE,protocol=review.lab.PROTOCOL,
                  production=False,research_only=True,production_backend_registered=False,applied_verified=False,
                  sequence=3,request_sha256=host["request_sha256"])
        done=dict(base,native=row,request=row["request"],state="native_completed")
        responses=[base,dict(base,request_written=True,replayed=False),done,dict(done,request_written=False,replayed=True)]
        steps=[("GET","/research/v12/status",200),("POST","/research/v12/pair",202),("GET","/research/v12/requests/3",200),("POST","/research/v12/pair",200)]
        report=dict(request=request,server_closed=True,server_thread_joined=True,automatic_retry=False,token_written_to_disk=False,
                    effect_verified=False,ai_acceptance_verified=False,exit_code=0,
                    steps=[dict(method=m,route=r,http_status=s,response=v) for (m,r,s),v in zip(steps,responses)])
        review.validate_http(report,row,intent,host)
        for mutate in (lambda r:r["steps"][-1]["response"].update(request_written=True),
                       lambda r:r["steps"][-1]["response"].update(native={}),
                       lambda r:r["request"].update(action="steer_trade"),
                       lambda r:r.update(server_thread_joined=False)):
            bad=deepcopy(report);mutate(bad)
            with self.assertRaises(ValueError):review.validate_http(bad,row,intent,host)

    def test_speed_has_its_own_pause_proof_and_cannot_be_a_pair(self):
        row=pair();row["request"].update(operation="speed",action="none",speed=5)
        row["lease_complete"]={"sequence":3,"paused_readback":True}
        shared=dict(pid=review.PID,creation=review.CREATION,sequence=3,speed=5,retry_allowed=False)
        sample=dict(game=int(review.WORLD,16),player=review.observer.HANDLES["FRA"],paused=True,native_speed_index=0)
        events=[dict(shared,event="supervisor_armed",before=sample),dict(shared,event="supervisor_complete",after=sample,native_lease_complete=row["lease_complete"])]
        review.validate_supervisor(events,row)
        with self.assertRaises(ValueError):review.validate_pair(row,"dispatched")
        bad=deepcopy(events);bad[-1]["after"]["paused"]=False
        with self.assertRaises(ValueError):review.validate_supervisor(bad,row)
        bad=deepcopy(events);bad[-1]["creation"]="01dd56989186135d"
        with self.assertRaises(ValueError):review.validate_supervisor(bad,row)

    def test_full_orchestration_replays_fixed_preflight_and_synthetic_owned_request(self):
        """Real offline validators, immutable preflight input, synthetic postflight.

        Only verify_build is stubbed because this fixture is a temporary evidence
        repository, not a second copied DLL/source checkout. Never reads live log.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries={}
            def add(key,name,data):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                entries[key]=dict(path=name,size_bytes=len(data),sha256=review.sha(data));return key
            def doc(key,name,value):return add(key,name,json.dumps(value).encode())
            pre_rel="work/runtime/native1375-v12/preflight-summary-17676.json"
            pre_raw=review.bounded(review.ROOT/pre_rel);pre=json.loads(pre_raw)
            add("preflight",pre_rel,pre_raw)
            for i,name in enumerate(pre["input_sha256"]):
                name=name.replace("\\","/");add(f"prefix{i}",name,review.bounded(review.ROOT/name))
            session_rel=f"work/runtime/native1375-v12/session-{review.PID}-{review.CREATION}"
            files={}
            prefix_dir=root/"work/runtime/native1375-v12/preflight-only-17676"
            for name in ("session.json","install.claim",*[x[1] for x in review.lab.PHASES.values()]):
                files[name]=add("session-"+name,session_rel+"/"+name,(prefix_dir/name).read_bytes())
            def host(wire):
                return dict(protocol=review.lab.PROTOCOL,purpose=review.lab.PURPOSE,pid=review.PID,creation=review.CREATION,
                    manifest_sha256=review.MANIFEST_SHA,request_sha256=review.sha(wire),body_ascii=wire.decode("ascii"),automatic_retry=False)
            for _,claim,wire in review.lab.PHASES.values():
                name=claim+".host-intent";files[name]=doc("session-"+name,session_rel+"/"+name,host(wire))
            prefix=(prefix_dir/"research-1375.jsonl").read_bytes()
            frame=next(json.loads(line) for line in reversed(prefix.splitlines()) if json.loads(line)["event"]=="research_frame")
            row=pair();row["request"].update(sequence=1,expires=frame["uptime_ms"]+5000)
            for core in row["records"]:core["raw_date"]=frame["raw_date"]
            bound=dict(pid=review.PID,process_creation_filetime=review.CREATION,sequence=1)
            events=[dict(bound,event="lab_request_claimed",**{k:v for k,v in row["request"].items() if k not in ("pid","creation","sequence")},durable_claim=True,retry_allowed=False)]
            events.extend(dict(bound,event="lab_native_record",lease_pause=False,record=core) for core in row["records"])
            row["complete"].update(bound,event="lab_request_complete",operation="pair",action="request_trade_power",session_frozen=False,applied_verified=False,retry_allowed=False)
            events.append(row["complete"])
            frame=dict(frame,last_sequence=1,send_enabled=True,frames=frame["frames"]+100,uptime_ms=frame["uptime_ms"]+100)
            events.append(frame)
            log=prefix+b"".join(json.dumps(e,separators=(",",":")).encode()+b"\n" for e in events)
            files["research-1375.jsonl"]=add("complete-log",session_rel+"/research-1375.jsonl",log)
            wire=review.lab.encode_request(row["request"])
            files["00000000000000000001.claim"]=add("claim",session_rel+"/00000000000000000001.claim",wire)
            files["00000000000000000001.host-intent"]=doc("host",session_rel+"/00000000000000000001.host-intent",host(wire))
            status=dict(pid=review.PID,creation=review.CREATION,purpose=review.lab.PURPOSE,protocol=review.lab.PROTOCOL,
                dll_sha256=review.DLL_SHA,manifest_sha256=review.MANIFEST_SHA,applied_verified=False,production_backend_registered=False,
                log_sha256=review.sha(log),latest_frame=frame,last_sequence=1,pending=False,lease_pending=False,request=row)
            doc("status","status.json",status)
            publication=dict(research_only=True,protocol=review.lab.PROTOCOL,status="published",sequence=1,phase=None,pid=review.PID,
                creation=review.CREATION,request_sha256=review.sha(wire),automatic_retry=False,native_dispatch_verified=False,
                applied_verified=False,production_backend_registered=False)
            doc("publication","publication.json",publication)
            doc("exit","exit.json",dict(pid=review.PID,creation=review.CREATION,process_exit_filetime=int(review.CREATION,16)+100000000,
                exit_observed=True,method="held_handle_wait_and_getprocesstimes"))
            selected=lambda key:dict(input=key,select=[])
            manifest=dict(schema_version=1,purpose="v12_finalized_experiment_case_manifest",finalized=True,inputs=entries,
                exit="exit",preflight="preflight",session_files=files,final_status=selected("status"),cases=[],
                requests=[dict(sequence=1,request={k:row["request"][k] for k in ("operation","mode","action","actor","target","speed")},
                    outcome="dispatched",publication=dict(kind="cli",evidence=selected("publication")),status=selected("status"))])
            build=json.loads(review.bounded(review.ROOT/"work/runtime/native1375-v12/build.json"))
            with patch.object(review.lab,"verify_build",return_value=(build,review.MANIFEST_SHA)):
                result=review.review(manifest,root=root)
                self.assertEqual(result["pair_submits"],1);self.assertEqual(result["selected_effect_count"],0)
                self.assertFalse(result["production_execution_verified"])
                extra=root/session_rel/"00000000000000000002.request";extra.write_bytes(wire)
                with self.assertRaisesRegex(ValueError,"inventory hides"):
                    review.review(manifest,root=root)
                extra.unlink()
                bad=deepcopy(manifest);bad["requests"][0]["request"]["speed"]=False
                with self.assertRaisesRegex(ValueError,"inventory differs"):
                    review.review(bad,root=root)
                bad=deepcopy(manifest);bad["requests"][0]["status"]=None
                with self.assertRaisesRegex(ValueError,"per-request status"):
                    review.review(bad,root=root)

    def test_cli_create_new_and_check_never_overwrite_or_ignore_other_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); manifest=p/"manifest.json";output=p/"out.json";manifest.write_text("{}")
            result=dict(reviewed_at_utc="one",review_status="reviewed_stopped_session",pair_submits=1,selected_effect_count=1)
            args=["--manifest",str(manifest),"--output",str(output)]
            with patch.object(review,"review",return_value=result),contextlib.redirect_stdout(io.StringIO()):
                review.main(args)
                with self.assertRaises(FileExistsError):review.main(args)
                result["reviewed_at_utc"]="two";review.main(args+["--check"])
                result["pair_submits"]=2
                with self.assertRaises(ValueError):review.main(args+["--check"])
            self.assertEqual(json.loads(output.read_text())["pair_submits"],1)


if __name__ == "__main__":
    unittest.main()
