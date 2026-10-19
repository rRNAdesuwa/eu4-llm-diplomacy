"""Bounded strict stopped stream adapted from pinned v17 experiment base."""
import hashlib

def strict_stream(raw,base,pre):
    # Fixed predecessor function with scoped globals and the R3 callback/final
    # date distinction. No original module is mutated.
    require=base.require;sha=base.sha;same=base.same;exact_int=base.exact_int
    PREFIX_BYTES=base.PREFIX_BYTES;PREFIX_SHA=base.PREFIX_SHA
    PID=base.PID;CREATION=base.CREATION;THREAD=base.THREAD
    acceptance_validator=base.acceptance_validator;lab=base.lab
    parse_lines=base.parse_lines;strict_frame=base.strict_frame
    identity=base.identity;validate_controls=base.validate_controls
    statuses=[]
    require(len(raw)>=PREFIX_BYTES and sha(raw[:PREFIX_BYTES])==PREFIX_SHA and raw[PREFIX_BYTES-1:PREFIX_BYTES]==b"\n","Preflight boundary differs")
    pre.strict_preflight_stream(raw[:PREFIX_BYTES],pre.EXPECTED_SESSION)
    digest=hashlib.sha256();size=0;last=None;seen=set();sequence=0;lease=False;request_dates={}
    speed_traces={};current=None;retained_deadline=0;last_claim_uptime=0
    prefix_requests={};pending_sequence=None
    acceptance=acceptance_validator.AcceptanceSession({"pid":PID,"process_creation_filetime":CREATION,"window_thread":THREAD})
    for line,event in parse_lines(raw):
        size+=len(line);digest.update(line);name=event.get("event")
        require(type(name) is str,"Missing event")
        if name=="research_frame":
            strict_frame(event)
            require(event["uptime_ms"]>=last_claim_uptime,"Claim is later than its first following heartbeat")
            acceptance.frame(event)
            require(same(acceptance.snapshot(),acceptance_validator.empty_window()),"Batch contains an acceptance grant")
            if last:
                require(event["frames"]>last["frames"] and event["uptime_ms"]>=last["uptime_ms"]
                        and event["raw_date"]>=last["raw_date"],"Frame/time/date regressed")
                if event["raw_date"]!=last["raw_date"]:
                    require(lease or last["lease_active"] or current is not None and current["stage"]=="await_health",
                            "Date advanced outside reviewed running lease")
            require(event["lease_deadline_uptime_ms"]==retained_deadline,"Frame deadline has no matching most recent armed lease")
            if size>PREFIX_BYTES:
                require(event["last_sequence"]==sequence and event["lease_active"] is lease
                        and all(event[k] is True for k in ("lifecycle_passed","owned_peace_tested","owned_peace_passed","preview_passed","command_passed"))
                        and event["mailbox_ready"] is (not lease),"Post-preflight frame gates differ")
                if current is not None:
                    require(current["stage"] in ("running","await_health"),"Frame interrupts synchronous speed callback boundaries")
                    require(event["uptime_ms"]>=retained_deadline-5000,"Armed deadline implies creation after its following frame")
                    if current["stage"]=="running":
                        require(event["native_speed_index"]==min(current["speed"],4),"Running frame speed differs from callback")
                    else:
                        require(event["raw_date"]>=current["pause_complete"]["after_date"] and event["paused"] is True
                                and event["native_speed_index"]==0,"Pause readback differs from following healthy frame")
                        current["final_frame"]=event;current["stage"]="closed";current=None
            last=event
        elif size>PREFIX_BYTES:
            require(name in {"lab_input_wait","lab_request_claimed","lab_native_record","lab_lease_armed","lab_request_complete","lab_lease_complete","lab_acceptance_pending"},"Unknown/duplicate post-preflight event")
            identity(event,"process_creation_filetime")
            for key in ("durable_claim","retry_allowed","lease_pause","automatic_pause","reliable_generation_verified","submit_entered","submit_returned",
                        "ownership_uncertain","session_frozen","applied_verified","write_entered","callback_returned","paused_readback","readback_matches"):
                if key in event:require(type(event[key]) is bool,"Host event boolean type differs")
            for key in ("reason","status","deadline_uptime_ms","maximum_raw_date_delta","initial_raw_date"):
                if key in event:require(type(event[key]) is int,"Host event integer type differs")
            require(exact_int(event.get("sequence"),0,128),"Event sequence exact type")
            if name=="lab_request_claimed":
                require(event["sequence"]==sequence+1 and not lease and current is None and last is not None and last["paused"] is True,"Claim out of order/while running or before pause health")
                sequence+=1;request_dates[sequence]=last["raw_date"]
                require(pending_sequence is None,"Claim interrupts unfinished prefix request")
                record={key:event[key] for key in lab.FIELDS if key!="creation"}
                record["creation"]=CREATION
                acceptance.claim(record,prefix_requests,event.get("claimed_uptime_ms"))
                prefix_requests[sequence]={"request":record,"records":[],"complete":None}
                pending_sequence=sequence
                # The native log records a fresh clock after durable claim/delete.
                # The preceding heartbeat is a lower bound, not the TTL origin.
                claimed=event.get("claimed_uptime_ms")
                require(exact_int(claimed,max(last["uptime_ms"],last_claim_uptime),2**64-1),
                        "Claim time regressed or predates its preceding heartbeat")
                require(exact_int(event.get("expires"),claimed+1,min(2**64-1,claimed+60000))
                        and exact_int(event.get("speed"),0,5),"Claim expired or exceeds reviewed sixty-second window")
                last_claim_uptime=claimed
                if event.get("operation")=="speed":
                    require(exact_int(event["speed"],1,5),"Only supervised positive speed requests are reviewed")
                    current={"stage":"claimed","sequence":sequence,"speed":event["speed"],"claim_frame":last,"claimed_uptime_ms":claimed,"expires":event["expires"]}
                    speed_traces[sequence]=current
            else: require(event["sequence"]==sequence,"Event foreign sequence")
            if name=="lab_acceptance_pending":acceptance.pending_grant(event)
            if name=="lab_native_record" and event.get("lease_pause") is False:
                require(pending_sequence==sequence,"Native record has no prefix request")
                prefix_requests[sequence]["records"].append(event["record"])
                if prefix_requests[sequence]["request"]["operation"]=="accept":acceptance.core(event["record"])
            if name=="lab_request_complete":
                require(pending_sequence==sequence,"Completion has no prefix request")
                acceptance.complete(event,prefix_requests[sequence]["records"][-1])
                prefix_requests[sequence]["complete"]=event;pending_sequence=None
            if name=="lab_lease_complete":
                require(sequence in prefix_requests,"Lease has no prefix request")
                prefix_requests[sequence]["lease_complete"]=event
            if name=="lab_lease_armed":
                require(current is not None and current["stage"]=="claimed" and not lease
                        and event.get("initial_raw_date")==current["claim_frame"]["raw_date"]
                        and exact_int(event.get("deadline_uptime_ms"),current["claimed_uptime_ms"]+5000,current["expires"]+4999)
                        and event.get("maximum_raw_date_delta")==48 and event.get("automatic_pause") is True
                        and event.get("reliable_generation_verified") is False,"Lease armed is not bound to the claim/date/deadline")
                current["armed"]=event;current["stage"]="armed";lease=True;retained_deadline=event["deadline_uptime_ms"]
            if name=="lab_request_complete" and current is not None:
                require(current["stage"]=="run_complete" and event.get("operation")=="speed","Speed request completed outside callback boundary")
                current["stage"]="running"
            if name=="lab_lease_complete":
                require(current is not None and current["stage"]=="pause_complete" and lease,"Lease completion lacks unique pause callback")
                current["stage"]="await_health";lease=False
            if name=="lab_native_record":
                core=event["record"]
                require(type(event.get("lease_pause")) is bool,"Native wrapper lease flag type")
                if core.get("event") in ("test_speed_begin","test_speed_complete"):
                    validate_controls(core,core["requested_speed"])
                    require(current is not None,"Speed callback has no current lease")
                    pause=event["lease_pause"];begin=core["event"]=="test_speed_begin"
                    field=("pause_" if pause else "run_")+("begin" if begin else "complete")
                    expected={"run_begin":"armed","run_complete":"run_begin","pause_begin":"running","pause_complete":"pause_begin"}
                    require(current["stage"]==expected[field] and core["requested_speed"]==(0 if pause else current["speed"]),
                            "Speed callbacks do not follow armed/run/pause order")
                    if begin:
                        if pause:
                            require(core["before_date"]>=max(last["raw_date"],current["armed"]["initial_raw_date"]+48) and core["before_native_index"]==min(current["speed"],4),
                                    "Pause began before the adjacent running date or with another speed")
                        else:
                            require(core["before_date"]==current["claim_frame"]["raw_date"] and core["before_paused"] is True
                                    and core["before_native_index"]==0,"Speed begin differs from preceding paused claim frame")
                    else:
                        first=current["pause_begin" if pause else "run_begin"]
                        require(all(core[k]==first[k] for k in ("before_date","before_native_index","before_paused")),
                                "Speed completion rewrites its begin snapshot")
                    current[field]=core;current["stage"]=field
                for k in ("pid","thread_id","raw_date","before_date","after_date","exception","exception_code","reason","requested_speed"):
                    if k in core:require(type(core[k]) is int,"Native numeric type alias")
                for k in ("freeze_session","ownership_uncertain","retry_allowed","applied_verified"):
                    if k in core:require(core[k] is False,"Native uncertainty")
        for status in statuses:
            if status["log_sha256"]==digest.hexdigest():
                require(last is not None and same(status["latest_frame"],last) and status["last_sequence"]==sequence,"Status is not exact typed prefix")
                require(status["pending"] is (pending_sequence is not None) and status["lease_pending"] is lease,
                        "Status pending/lease state differs from its exact prefix")
                if "request" in status:
                    selected=status["request"]
                    require(type(selected) is dict and type(selected.get("request")) is dict,
                            "Selected status request is malformed")
                    selected_sequence=selected["request"].get("sequence")
                    require(exact_int(selected_sequence,1,sequence) and selected_sequence in prefix_requests
                            and same(selected,prefix_requests[selected_sequence]),
                            "Selected status request borrows absent/future prefix evidence")
                require(same(status.get("acceptance_window"),acceptance.snapshot()),"Status window borrows future or wrong grant state")
                seen.add(status["log_sha256"])
    require(seen=={s["log_sha256"] for s in statuses},"Missing status prefix")
    require(name=="research_frame" and last is not None and not lease and current is None
            and last["paused"] is True and last["last_sequence"]==sequence,"Incomplete stopped health")
    require(acceptance.pending is None and acceptance.window["state"]=="closed" and last["acceptance_flag"]==0,"Stopped acceptance window not closed")
    return request_dates,speed_traces
