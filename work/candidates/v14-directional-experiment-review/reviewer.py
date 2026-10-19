"""Offline finalized v14 directional experiment reviewer. No process access or publishing."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import canonical, decode_json
from work.native import lab_protocol_v14_1375 as lab
from work.probe_diplomacy_current import ProbeError

PID, CREATION, THREAD = 18356, "01dd56aa6f724ea8", 47264
WORLD = "0x221c8dac040"
INITIAL_DATE = 56456976
DLL_SHA = "abfb2e343f7e7332efa96c45b1dd2b89c00ac2b4085cbd9fc32e8f90db299296"
MANIFEST_SHA = "aa09084d3d1d7c9adff164b67356d72e2c511b519e79b382e7bc54a80c96ec75"
PREFLIGHT_CASE = "work/runtime/native1375-v14/directional-preflight-case-18356.json"
PREFLIGHT_SUMMARY = "work/runtime/native1375-v14/directional-preflight-summary-18356.json"
PREFIX_BYTES = 162394
PREFIX_SHA = "d255e57d97bc20deefd11a3475cc81883d4cf182852ed774fa39cb183f98595d"
SESSION = f"work/runtime/native1375-v14/session-{PID}-{CREATION}"
COUNTS = {"lifecycle":20,"owned_peace":1,"preview":72,"command":72}
MAX_FILE, MAX_TOTAL, MAX_ARTIFACTS, MAX_CASE = 8*1024*1024, 64*1024*1024, 512, 512*1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
require = lab.require

def sha(raw): return hashlib.sha256(raw).hexdigest()
def exact_int(value, low=0, high=2**64-1): return type(value) is int and low <= value <= high

def typed(value):
    # JSON's spelling preserves bool/int/float distinctions; no Python == coercion.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

def same(left, right): return typed(left) == typed(right)

def bounded(path, maximum=MAX_FILE):
    with Path(path).open("rb") as stream: raw=stream.read(maximum+1)
    require(len(raw)<=maximum, "File exceeds finite budget")
    return raw

def relative(root, name):
    require(type(name) is str and name and "\\" not in name and ":" not in name, "Non-canonical artifact path")
    parts=PurePosixPath(name).parts
    require(parts and not PurePosixPath(name).is_absolute() and all(x not in (".","..") for x in parts)
            and str(PurePosixPath(name))==name, "Artifact escapes root")
    current=Path(root).resolve()
    for part in parts:
        current=current/part
        require(not current.is_symlink() and not (hasattr(current,"is_junction") and current.is_junction()), "Indirect artifact path")
    require(current.resolve().is_relative_to(Path(root).resolve()), "Artifact outside root")
    return current

def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

# Every dependency is checked before dynamically importing candidate code.
def dependencies(root=ROOT):
    data=decode_json(bounded(HERE/"pins.json",256*1024).decode())
    require(set(data)=={"schema_version","purpose","files"} and exact_int(data["schema_version"],1,1), "Pins schema")
    total=0
    for name,item in data["files"].items():
        raw=bounded(relative(root,name));total+=len(raw)
        require(total<=64*1024*1024 and len(raw)==item["size_bytes"] and sha(raw)==item["sha256"], "Dependency changed: "+name)
    pre=load_module("directional_experiment_preflight",relative(root,"work/candidates/v14-directional-preflight-review/reviewer.py"))
    observer=load_module("directional_experiment_observer",relative(root,"work/candidates/directional-pair-observer-1375/observer.py"))
    observer.verify_contract(root)
    return pre,observer

class Inputs:
    """Freeze all supplied bytes before decoding any evidence; rehash at end."""
    def __init__(self,root,entries):
        require(type(entries) is dict and 1<=len(entries)<=MAX_ARTIFACTS,"Artifact inventory budget")
        self.root,self.entries,self.cache,self.used=root,entries,{},set()
        paths=set();total=0
        for key,item in entries.items():
            require(type(key) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",key) and type(item) is dict
                    and set(item)=={"path","size_bytes","sha256"},"Invalid artifact descriptor")
            require(exact_int(item["size_bytes"],1,MAX_FILE) and type(item["sha256"]) is str and HEX.fullmatch(item["sha256"]),"Invalid size/hash")
            require(item["path"] not in paths,"Duplicate artifact path");paths.add(item["path"])
            raw=bounded(relative(root,item["path"]));total+=len(raw)
            require(total<=MAX_TOTAL and len(raw)==item["size_bytes"] and sha(raw)==item["sha256"],"Frozen input differs: "+key)
            self.cache[key]=raw
    def raw(self,key):
        require(type(key) is str and key in self.cache,"Unknown explicit evidence reference")
        self.used.add(key);return self.cache[key]
    def doc(self,key): return decode_json(self.raw(key).decode("utf-8"))
    def selected(self,ref):
        require(type(ref) is dict and set(ref)=={"input","select"} and type(ref["select"]) is list and len(ref["select"])<=6,"Invalid explicit selector")
        value=self.doc(ref["input"])
        for step in ref["select"]:
            if type(value) is list:
                require(exact_int(step,0,len(value)-1),"Strict list index required");value=value[step]
            else:
                require(type(value) is dict and type(step) is str and step in value,"Missing selected field");value=value[step]
        require(type(value) is dict,"Selected evidence must be object")
        return value
    def finish(self):
        require(self.used==set(self.entries),"Unreferenced evidence is not accepted")
        for key,item in self.entries.items():
            raw=bounded(relative(self.root,item["path"]))
            require(raw==self.cache[key],"Input changed during review: "+key)

def identity(row, creation_key="creation"):
    require(type(row) is dict and type(row.get("pid")) is int and row["pid"]==PID
            and type(row.get(creation_key)) is str and row[creation_key]==CREATION,"Foreign/incomplete process identity")

def validate_exit(row):
    identity(row)
    require(row.get("exit_observed") is True and row.get("method")=="held_handle_wait_and_getprocesstimes"
            and exact_int(row.get("process_exit_filetime"),int(CREATION,16)+1)
            and exact_int(row.get("process_creation_filetime"),int(CREATION,16),int(CREATION,16))
            and all(exact_int(row.get(k),0,0) for k in ("before_exit_filetime","wait_status","exit_code"))
            and row.get("read_only") is True and row.get("process_stop_requested_by_observer") is False
            and row.get("access")=="QUERY_LIMITED_INFORMATION | SYNCHRONIZE"
            and type(row.get("executable_sha256")) is str and row["executable_sha256"].upper()==lab.LOCAL_SHA256.upper(),"Exact held process normal exit required")
    return row

def validate_host(host,wire,row=None):
    identity(host)
    require(set(host)=={"protocol","purpose","pid","creation","manifest_sha256","request_sha256","body_ascii","automatic_retry"}
            and host["protocol"]==lab.PROTOCOL and host["purpose"]==lab.PURPOSE
            and host["manifest_sha256"]==MANIFEST_SHA and host["automatic_retry"] is False
            and type(host["body_ascii"]) is str and host["body_ascii"].encode("ascii")==wire
            and host["request_sha256"]==sha(wire),"Host intent/claim differs")
    if row is not None: require(same(lab.decode_request(wire),row["request"]),"Request wire/native differs")

PAIR_INTS={"pid","thread_id","raw_date","status","reason","phase","envoy_id","exception",
    "fixed_subsidy_amount_milli","fixed_subsidy_duration_years","fixed_gift_amount_milli","fixed_transfer_fraction_milli","fixed_insult_index"}
PAIR_BOOLS={"preview_called","preview_allowed","gate_called","gate_allowed","submit_entered","submit_returned","ownership_uncertain",
    "original_destroyed","command_destroyed_before_dispatch","freeze_session","retry_allowed","applied_verified"}
PAIR_NULLABLE={"context_submit_return","caller_container_consumed"}
PAIR_STRINGS={"event","action_id","actor","target","process_creation_filetime","world","actor_handle","target_handle"}

def strict_pair(record):
    require(type(record) is dict and set(record)==PAIR_INTS|PAIR_BOOLS|PAIR_NULLABLE|PAIR_STRINGS,"Pair record exact schema differs")
    require(all(type(record[k]) is int for k in PAIR_INTS) and all(type(record[k]) is bool for k in PAIR_BOOLS)
            and all(type(record[k]) is str for k in PAIR_STRINGS)
            and all(record[k] is None or type(record[k]) is bool for k in PAIR_NULLABLE),"Pair record exact types differ")
    require(record["exception"]==0 and all(record[k] is False for k in ("ownership_uncertain","freeze_session","retry_allowed","applied_verified")),"Unsafe native pair record")
    require(exact_int(record["raw_date"],INITIAL_DATE,2**31-1),"Pair date invalid")

def validate_pair(row, outcome, observer):
    """A completed legality test is never a diplomatic submit/effect."""
    request, records, complete = row["request"], row["records"], row["complete"]
    identity(request)
    require(request["operation"] == "pair" and outcome in ("dispatched", "legality_allowed", "legality_rejected", "guard_rejected"), "Invalid pair outcome")
    submit = outcome == "dispatched"
    require(request["mode"] == ("submit" if submit else "legality_only"), "Mode/outcome differs")
    require([r.get("event") for r in records] == (["pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete"]
            if submit else ["pair_engine_begin", "pair_engine_complete"]), "Unexpected native ownership boundaries")
    final = records[-1]
    begin=records[0]
    require(begin.get("phase")==2 and begin.get("status")==0 and begin.get("reason")==0
            and all(begin.get(k) is False for k in PAIR_BOOLS)
            and all(k in begin and begin[k] is None for k in PAIR_NULLABLE),"Invalid initial ownership boundary")
    if submit:
        intent=records[1]
        require(intent.get("phase")==11 and intent.get("status")==0 and intent.get("reason")==0
                and all(intent.get(k) is True for k in ("preview_called","preview_allowed","gate_called","gate_allowed","original_destroyed"))
                and all(intent.get(k) is False for k in ("submit_entered","submit_returned","command_destroyed_before_dispatch"))
                and all(k in intent and intent[k] is None for k in PAIR_NULLABLE),"Invalid pre-transfer ownership boundary")
    for record in records:
        strict_pair(record)
        identity(record, "process_creation_filetime")
        require(record.get("thread_id") == THREAD and type(record["thread_id"]) is int and record.get("world") == WORLD
                and record.get("action_id") == request["action"] and record.get("actor") == request["actor"]
                and record.get("target") == request["target"], "Foreign native pair/thread/world")
        for tag, field in ((request["actor"], "actor_handle"), (request["target"], "target_handle")):
            require(int(record[field], 16) == observer.legacy.HANDLES[tag], "Native full country handle differs")
        fixed = {"fixed_subsidy_amount_milli": 1000 if request["action"] in ("give_subsidies", "cancel_subsidies") else 0,
                 "fixed_subsidy_duration_years": 10 if request["action"] in ("give_subsidies", "cancel_subsidies") else 0,
                 "fixed_gift_amount_milli": 25000 if request["action"] == "send_gift" else 0,
                 "fixed_transfer_fraction_milli": 500 if request["action"] in ("request_trade_power", "cancel_trade_power_transfer") else 0,
                 "fixed_insult_index": -1 if request["action"] == "insult" else 0}
        require(all(type(record.get(k)) is int and record[k] == v for k, v in fixed.items()), "Fixed native scalar differs")
    require(type(final.get("exception")) is int and final["exception"] == 0
            and final.get("ownership_uncertain") is False and final.get("freeze_session") is False
            and final.get("applied_verified") is False and final.get("retry_allowed") is False
            and final.get("submit_entered") is submit and final.get("submit_returned") is submit,
            "Uncertain native completion/ownership")
    if outcome == "guard_rejected":
        require(type(final.get("reason")) is int and final["reason"] == 13
                and type(final.get("status")) is int and final["status"] == 0 and final.get("phase") == 3
                and all(final.get(k) is False for k in ("preview_called", "preview_allowed", "gate_called", "gate_allowed",
                                                       "original_destroyed", "command_destroyed_before_dispatch"))
                and final.get("context_submit_return") is None and final.get("caller_container_consumed") is None,
                "Expected bounded pre-allocation guard rejection; no native legality claim")
    elif outcome == "legality_rejected":
        require(type(final.get("reason")) is int and final["reason"] in (17, 18)
                and type(final.get("status")) is int and final["status"] == 1 and final.get("preview_called") is True
                and final.get("original_destroyed") is True
                and final.get("context_submit_return") is None and final.get("caller_container_consumed") is None,
                "Rejection lacks its native boundary")
        require((final["reason"] == 17 and final.get("phase") == 6 and final.get("preview_allowed") is False
                 and final.get("gate_called") is False and final.get("gate_allowed") is False
                 and final.get("command_destroyed_before_dispatch") is False)
                or (final["reason"] == 18 and final.get("phase") == 8 and final.get("preview_allowed") is True
                    and final.get("gate_called") is True and final.get("gate_allowed") is False
                    and final.get("command_destroyed_before_dispatch") is True), "Rejection cleanup/phase differs")
    else:
        require(final["phase"] == (13 if submit else 8) and type(final.get("status")) is int and final["status"] == (2 if submit else 1)
                and type(final.get("reason")) is int and final["reason"] == 0
                and final.get("preview_called") is True and final.get("preview_allowed") is True
                and final.get("gate_called") is True and final.get("gate_allowed") is True
                and final.get("original_destroyed") is True
                and final.get("command_destroyed_before_dispatch") is (not submit)
                and final.get("context_submit_return") is (True if submit else None)
                and final.get("caller_container_consumed") is (True if submit else None), "Dispatch/legality was not completed")
    require(all(type(complete.get(k)) is type(final[k]) and complete[k] == final[k]
                for k in ("status", "reason", "submit_entered", "submit_returned", "ownership_uncertain")),
            "Host/native completion differs")
    return final



def validate_publication(document,host,sequence):
    identity(document)
    require(document.get("research_only") is True and document.get("protocol")==lab.PROTOCOL
            and document.get("status")=="published" and exact_int(document.get("sequence"),sequence,sequence)
            and "phase" in document and document["phase"] is None and document.get("request_sha256")==host["request_sha256"]
            and all(document.get(k) is False for k in ("automatic_retry","native_dispatch_verified","applied_verified","production_backend_registered")),"Publication receipt differs")

def validate_status(status,row=None):
    identity(status)
    require(status.get("purpose")==lab.PURPOSE and status.get("protocol")==lab.PROTOCOL
            and type(status.get("dll_sha256")) is str and status["dll_sha256"].lower()==DLL_SHA
            and status.get("manifest_sha256")==MANIFEST_SHA and status.get("applied_verified") is False
            and status.get("production_backend_registered") is False
            and type(status.get("log_sha256")) is str and HEX.fullmatch(status["log_sha256"])
            and exact_int(status.get("last_sequence"),0,128) and status.get("pending") is False
            and status.get("lease_pending") is False and same(status.get("phases"),dict.fromkeys(COUNTS,True)),"Status binding differs")
    if row is not None: require("request" in status and same(status["request"],row),"Status differs from complete native history")

FRAME_BOOLS={"thread_changed","world_ready","world_changed","session_frozen","paused","lifecycle_passed","owned_peace_tested",
    "owned_peace_passed","preview_passed","command_passed","mailbox_ready","running_speed_enabled","lease_active","send_enabled"}
FRAME_INTS={"pid","thread","uptime_ms","frames","raw_date","native_speed_index","last_sequence","lease_deadline_uptime_ms"}
FRAME_TEXT={"event","fixture_profile_sha256","process_creation_filetime","world_cookie","player_handle"}

def strict_frame(event):
    require(type(event) is dict and set(event)==FRAME_BOOLS|FRAME_INTS|FRAME_TEXT
            and all(type(event[k]) is bool for k in FRAME_BOOLS) and all(type(event[k]) is int for k in FRAME_INTS)
            and all(type(event[k]) is str for k in FRAME_TEXT),"Frame full schema/types differ")
    identity(event,"process_creation_filetime")
    require(event["event"]=="research_frame" and event["thread"]==THREAD and event["world_cookie"]==WORLD
            and event["player_handle"]=="0x0100007a00415246" and event["fixture_profile_sha256"]==lab.FIXTURE_PROFILE_SHA256
            and exact_int(event["raw_date"],INITIAL_DATE,2**31-1) and exact_int(event["native_speed_index"],0,4)
            and exact_int(event["frames"],1,2**31-1) and exact_int(event["uptime_ms"],1)
            and exact_int(event["last_sequence"],0,128) and exact_int(event["lease_deadline_uptime_ms"]),"Frame identity/bounds differ")
    require(event["world_ready"] is True and event["running_speed_enabled"] is True
            and all(event[k] is False for k in ("thread_changed","world_changed","session_frozen")),"Unhealthy frame")
    require(event["lease_active"] or event["paused"] is True and event["native_speed_index"]==0,"Running outside lease")
    require(event["lease_active"] or event["lease_deadline_uptime_ms"]==0,"Inactive lease retains deadline")


def parse_lines(raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_FILE and raw.endswith(b"\n"),"Bounded complete JSONL required")
    result=[]
    for line in raw.splitlines(keepends=True):
        require(len(line)<=lab.MAX_LINE and line.endswith(b"\n"),"Truncated/oversized log line")
        event=decode_json(line.decode("utf-8"));require(type(event) is dict,"JSONL object required");result.append((line,event))
    return result


def strict_stream(raw,statuses,pre):
    require(len(raw)>=PREFIX_BYTES and sha(raw[:PREFIX_BYTES])==PREFIX_SHA and raw[PREFIX_BYTES-1:PREFIX_BYTES]==b"\n","Preflight boundary differs")
    pre.strict_preflight_stream(raw[:PREFIX_BYTES],pre.EXPECTED_SESSION)
    digest=hashlib.sha256();size=0;last=None;seen=set();sequence=0;lease=False;request_dates={}
    for line,event in parse_lines(raw):
        size+=len(line);digest.update(line);name=event.get("event")
        require(type(name) is str,"Missing event")
        if name=="research_frame":
            strict_frame(event)
            if last:
                require(event["frames"]>last["frames"] and event["uptime_ms"]>=last["uptime_ms"]
                        and event["raw_date"]>=last["raw_date"],"Frame/time/date regressed")
                if event["raw_date"]!=last["raw_date"]:require(lease or last["lease_active"],"Date advanced outside reviewed running lease")
            if size>PREFIX_BYTES:
                require(event["last_sequence"]==sequence and event["lease_active"] is lease
                        and all(event[k] is True for k in ("lifecycle_passed","owned_peace_tested","owned_peace_passed","preview_passed","command_passed","mailbox_ready")),"Post-preflight frame gates differ")
            last=event
        elif size>PREFIX_BYTES:
            require(name in {"lab_input_wait","lab_request_claimed","lab_native_record","lab_lease_armed","lab_request_complete","lab_lease_complete"},"Unknown/duplicate post-preflight event")
            identity(event,"process_creation_filetime")
            for key in ("durable_claim","retry_allowed","lease_pause","automatic_pause","reliable_generation_verified","submit_entered","submit_returned",
                        "ownership_uncertain","session_frozen","applied_verified","write_entered","callback_returned","paused_readback","readback_matches"):
                if key in event:require(type(event[key]) is bool,"Host event boolean type differs")
            for key in ("reason","status","deadline_uptime_ms","maximum_raw_date_delta","initial_raw_date"):
                if key in event:require(type(event[key]) is int,"Host event integer type differs")
            require(exact_int(event.get("sequence"),0,128),"Event sequence exact type")
            if name=="lab_request_claimed":
                require(event["sequence"]==sequence+1 and not lease and last is not None and last["paused"] is True,"Claim out of order/while running")
                sequence+=1;request_dates[sequence]=last["raw_date"]
                require(exact_int(event.get("expires"),1) and exact_int(event.get("speed"),0,5),"Claim numeric types")
            else: require(event["sequence"]==sequence,"Event foreign sequence")
            if name=="lab_lease_armed":lease=True
            if name=="lab_lease_complete":lease=False
            if name=="lab_native_record":
                core=event["record"]
                require(type(event.get("lease_pause")) is bool,"Native wrapper lease flag type")
                if core.get("event") in ("test_speed_begin","test_speed_complete"):
                    validate_controls(core,core["requested_speed"])
                for k in ("pid","thread_id","raw_date","before_date","after_date","exception","exception_code","reason","requested_speed"):
                    if k in core:require(type(core[k]) is int,"Native numeric type alias")
                for k in ("freeze_session","ownership_uncertain","retry_allowed","applied_verified"):
                    if k in core:require(core[k] is False,"Native uncertainty")
        for status in statuses:
            if status["log_sha256"]==digest.hexdigest():
                require(last is not None and same(status["latest_frame"],last) and status["last_sequence"]==sequence,"Status is not exact typed prefix")
                seen.add(status["log_sha256"])
    require(seen=={s["log_sha256"] for s in statuses},"Missing status prefix")
    require(name=="research_frame" and last is not None and not lease and last["paused"] is True and last["last_sequence"]==sequence,"Incomplete stopped health")
    return request_dates


def captured(inputs,ref):
    require(type(ref) is dict and ref.get("select")==["report"],"Explicit captured report selector required")
    wrapper=inputs.doc(ref["input"])
    require(type(wrapper) is dict and wrapper.get("purpose")=="one_explicit_v14_cli_capture"
            and wrapper.get("automatic_retry") is False and wrapper.get("applied_verified") is False
            and exact_int(wrapper.get("exit_code"),0,0) and wrapper.get("stderr")==""
            and type(wrapper.get("arguments")) is list and len(wrapper["arguments"])<=32
            and all(type(x) is str and len(x)<=1024 for x in wrapper["arguments"]),"Failed/unknown CLI capture")
    return inputs.selected(ref)


def validate_controls(core,speed):
    ints={"thread_id","requested_speed","reason","before_date","before_native_index","after_date","after_native_index","exception_code"}
    booleans={"before_paused","write_entered","callback_returned","callback_success","result_destroyed","readback_observed","after_paused",
        "readback_matches","freeze_session","retry_allowed","diplomacy_submitted"}
    require(set(core)==ints|booleans|{"event"} and all(type(core[k]) is int for k in ints)
            and all(type(core[k]) is bool for k in booleans),"Controls exact schema/types differ")
    require(exact_int(speed,0,5) and core["thread_id"]==THREAD and exact_int(core["requested_speed"],speed,speed)
            and core["event"] in ("test_speed_begin","test_speed_complete")
            and core["reason"]==0 and core["exception_code"]==0
            and all(core[k] is False for k in ("freeze_session","retry_allowed","diplomacy_submitted")),"Failed/unknown controls operation")
    if core["event"]=="test_speed_complete":
        require(all(core[k] is True for k in ("write_entered","callback_returned","callback_success","result_destroyed","readback_observed","readback_matches"))
                and core["after_paused"] is (speed==0) and core["after_native_index"]==min(speed,4)
                and core["before_date"]==core["after_date"],"Controls callback/readback/cleanup incomplete")


def validate_supervisor(events,row):
    request=row["request"];seq=request["sequence"];speed=request["speed"]
    require(exact_int(speed,1,5) and [e.get("event") for e in events]==["supervisor_armed","supervisor_complete"],"Speed supervisor incomplete/stopped/extra events")
    for e in events:
        identity(e)
        require(exact_int(e.get("sequence"),seq,seq) and exact_int(e.get("speed"),speed,speed) and e.get("retry_allowed") is False,"Supervisor binding differs")
    first,last=events
    require(type(first.get("deadline_seconds")) is float and first["deadline_seconds"]==12.0
            and type(last.get("elapsed_seconds")) is float and 0<=last["elapsed_seconds"]<12.0,"Supervisor deadline differs")
    for state in (first["before"],last["after"]):
        require(type(state) is dict and set(state)=={"game","server","pause_manager","player","raw_date","paused","native_speed_index"}
                and all(type(state[k]) is int for k in state if k!="paused") and state["paused"] is True
                and state["game"]==int(WORLD,16) and state["player"]==int("0100007a00415246",16)
                and state["native_speed_index"]==0 and state["server"]>0 and state["pause_manager"]>0,"Supervisor RO identity/state differs")
    require(all(first["before"][k]==last["after"][k] for k in ("game","server","pause_manager","player"))
            and last["after"]["raw_date"]>=first["before"]["raw_date"]
            and "lease_complete" in row and same(last["native_lease_complete"],row["lease_complete"]),"Pause/world/lease evidence differs")
    require([e["event"] for e in row["records"]]==["test_speed_begin","test_speed_complete"],"Speed callback record sequence differs")
    for core in row["records"]:validate_controls(core,speed)
    return first["before"]["raw_date"],last["after"]["raw_date"]


def validate_legality_link(item,rows,ledger,observer):
    seq=item["sequence"];request=rows[seq]["request"];link=item["legality_sequence"]
    if request["operation"]!="pair" or request["mode"]!="submit":
        require(link is None,"Only pair submits bind legality");return
    require(exact_int(link,1,seq-1) and link==seq-1 and link in rows,"Submit requires explicit adjacent legality sequence")
    prior=rows[link]
    require(ledger[link]["outcome"]=="legality_allowed","Bound prior legality was rejected/unknown")
    validate_pair(prior,"legality_allowed",observer)
    require(all(prior["request"][k]==request[k] for k in ("operation","action","actor","target","speed"))
            and prior["request"]["mode"]=="legality_only","Legality roles/action differ")
    require(prior["records"][-1]["raw_date"]==rows[seq]["records"][-1]["raw_date"],"Legality and submit differ in raw date")


def validate_effect(case,row,before,after,comparison,hashes,observer):
    request=row["request"]
    require(request["action"] in observer.ACTIONS and request["actor"]=="FRA","Selected effect not one of ten directions")
    wanted=observer.binding(request["action"],request["target"])
    samples=[]
    for report in (before,after):
        require(same(report["binding"],wanted) and type(report["expected_pid"]) is int and report["expected_pid"]==PID
                and report["expected_creation"]==CREATION,"Observer direction/identity differs from submit")
        try: sample,_,_=observer.validated_report(report)
        except ProbeError as error: raise lab.LabError("Invalid directional observation: "+str(error)) from error
        require(sample["game"]==WORLD and sample["current_raw_date"]==row["records"][-1]["raw_date"],"Observed world/date differs from native request")
        samples.append(sample)
    computed=observer.compare_reports(before,after);computed["inputs"]=hashes
    require(same(computed,comparison),"Stored comparison is not exact typed recomputation")
    require(type(case["expected_observed_effect"]) is bool and computed["observed_effect"] is case["expected_observed_effect"],"Explicit expected effect differs")
    # Unknown is not a positive proof. Still require valid samples and no structural
    # errors; a missing selected transition does not establish rejection.
    require(not computed["errors"],"Comparison contains invalid/unstable evidence")
    return {"sequence":case["sequence"],"action":request["action"],"target":request["target"],"binding":wanted,
        "observed_effect":computed["observed_effect"],"status":computed["status"],
        "request_causality_verified":False,"ai_acceptance_verified":False,"native_rejection_verified":False}


def validate_annotations(notes,rows):
    require(type(notes) is list and len(notes)<=128,"Annotation budget")
    for note in notes:
        require(type(note) is dict and set(note)=={"sequence","source","text","native_evidence"}
                and exact_int(note["sequence"],1,128) and note["sequence"] in rows
                and note["source"]=="root_ui_annotation" and type(note["text"]) is str and 0<len(note["text"])<=1000
                and note["native_evidence"] is False,"UI annotation cannot become native evidence")
    return notes


def review(case,root=ROOT):
    fields={"schema_version","purpose","finalized","inputs","exit","stopped_audit","preflight_case","preflight_summary",
        "session_files","final_status","requests","effects","annotations","persistence"}
    require(type(case) is dict and set(case)==fields and exact_int(case["schema_version"],1,1)
            and case["purpose"]=="v14_directional_finalized_experiment_case" and case["finalized"] is True,"Explicit finalized case required")
    require(case["persistence"]==[] and type(case["persistence"]) is list,"Save/reload is unsupported by this reviewer; no inherited matcher")
    pre,observer=dependencies(root)
    inputs=Inputs(root,case["inputs"])
    exit_row=validate_exit(inputs.selected(case["exit"]))
    files=case["session_files"]
    pattern=r"(?:session\.json|install\.claim|research-1375\.jsonl|phase-(?:lifecycle|owned-peace-lifecycle|preview|command)\.claim(?:\.host-intent)?|[0-9]{20}\.(?:host-intent|claim|fixture-profile|lease-pause\.claim|supervisor\.jsonl|publisher-output\.txt))"
    require(type(files) is dict and 11<=len(files)<=MAX_ARTIFACTS and all(type(n) is str and re.fullmatch(pattern,n) for n in files),"Unexpected session artifact or pending request")
    for name,key in files.items():
        require(type(key) is str and key in inputs.entries and inputs.entries[key]["path"]==SESSION+"/"+name,"Session artifact rebound")
    actual=list(relative(root,SESSION).iterdir())
    require(len(actual)<=MAX_ARTIFACTS and all(x.is_file() and not x.is_symlink() and not (hasattr(x,"is_junction") and x.is_junction()) for x in actual)
            and {x.name for x in actual}==set(files),"Final inventory hides pending/extra artifacts")
    audit=inputs.selected(case["stopped_audit"])
    require(set(audit)=={"pid","creation","process_exit_filetime","complete_log","session_files","stopped"},"Explicit stopped-audit projection required")
    identity(audit)
    require(audit["stopped"] is True and type(audit["process_exit_filetime"]) is int
            and audit["process_exit_filetime"]==exit_row["process_exit_filetime"]
            and same(audit["complete_log"],inputs.entries[files["research-1375.jsonl"]])
            and same(audit["session_files"],{n:inputs.entries[k] for n,k in files.items()}),"Final stop/log/inventory binding differs")
    for key,path in (("preflight_case",PREFLIGHT_CASE),("preflight_summary",PREFLIGHT_SUMMARY)):
        require(inputs.entries[case[key]]["path"]==path,"Wrong fixed preflight artifact")
    prefix_case=inputs.doc(case["preflight_case"]);summary=inputs.doc(case["preflight_summary"])
    # Register every source read by the fixed preflight reviewer in this frozen
    # input inventory too; no invisible evidence or changing file may pass.
    by_path={v["path"]:k for k,v in inputs.entries.items()}
    for descriptor in prefix_case["inputs"].values():
        require(descriptor["path"] in by_path,"Preflight input missing from frozen inventory")
        key=by_path[descriptor["path"]];require(same(descriptor,inputs.entries[key]),"Preflight descriptor differs");inputs.raw(key)
    replay=pre.review(prefix_case,root=root)
    require(same(replay,summary) and same(summary["phase_case_counts"],COUNTS),"Fixed four-stage proof replay differs")
    items=case["requests"]
    require(type(items) is list and 1<=len(items)<=128,"Request ledger budget")
    item_fields={"sequence","request","outcome","legality_sequence","publication","status"}
    require(all(type(item) is dict and set(item)==item_fields and exact_int(item["sequence"],i,i) for i,item in enumerate(items,1)),"Ledger must contain each exact consecutive sequence")
    ledger={item["sequence"]:item for item in items};statuses=[]
    final=captured(inputs,case["final_status"]);validate_status(final);statuses.append(final)
    raw=inputs.raw(files["research-1375.jsonl"])
    required={"session.json","install.claim","research-1375.jsonl"}|{p[1] for p in lab.PHASES.values()}|{p[1]+".host-intent" for p in lab.PHASES.values()}
    with tempfile.TemporaryDirectory(prefix="v14-directional-offline-") as directory:
        mirror=Path(directory)
        for name,key in files.items(): (mirror/name).write_bytes(inputs.raw(key))
        metadata=lab.read_session_metadata(mirror,PID,CREATION)
        require(type(metadata["window_thread"]) is int and metadata["window_thread"]==THREAD,"Wrong fixed native thread")
        evidence=lab.read_evidence(mirror,metadata);rows=evidence["requests"]
        require(set(rows)==set(ledger) and same(evidence["phases"],dict.fromkeys(COUNTS,True))
                and all(evidence[k] is False for k in ("pending","lease_pending","input_wait_pending")),"Incomplete/unknown native session")
        require(final["last_sequence"]==len(items),"Final status misses requests")
        for phase,(_,claim,_) in lab.PHASES.items():validate_host(inputs.doc(files[claim+".host-intent"]),lab.phase_wire(phase,metadata))
        inventory=[]
        for item in items:
            seq=item["sequence"];row=rows[seq];request=row["request"];stem=f"{seq:020}"
            require(same(item["request"],{k:request[k] for k in ("operation","mode","action","actor","target","speed")}),"Ledger action/role/mode differs")
            required|={stem+".claim",stem+".host-intent"}
            host=inputs.doc(files[stem+".host-intent"]);validate_host(host,inputs.raw(files[stem+".claim"]),row)
            pub=captured(inputs,item["publication"])
            if request["operation"]=="pair":validate_pair(row,item["outcome"],observer)
            elif request["operation"]=="fixture":
                require(item["outcome"]=="fixture_callback_returned","Fixture callback is not a diplomatic effect");required.add(stem+".fixture-profile")
            else:
                require(item["outcome"]=="completed_and_paused","Unsupported speed outcome")
                required|={stem+".lease-pause.claim",stem+".supervisor.jsonl",stem+".publisher-output.txt"}
                events=[e for _,e in parse_lines(inputs.raw(files[stem+".supervisor.jsonl"]))]
                before_date,after_date=validate_supervisor(events,row)
                require(pub.get("status")=="completed_and_paused" and exact_int(pub.get("before_date"),before_date,before_date)
                        and exact_int(pub.get("after_date"),after_date,after_date),"Supervisor receipt differs")
                child=inputs.doc(files[stem+".publisher-output.txt"]);validate_status(child);statuses.append(child)
                validate_publication(child["publication"],host,seq)
            if request["operation"]!="speed":
                validate_status(pub);statuses.append(pub);validate_publication(pub["publication"],host,seq)
            require(item["status"] is not None,"Every request requires independent final status capture")
            status=captured(inputs,item["status"]);validate_status(status,row);statuses.append(status)
            validate_legality_link(item,rows,ledger,observer)
            inventory.append({"sequence":seq,**item["request"],"outcome":item["outcome"],"legality_sequence":item["legality_sequence"],
                "request_sha256":host["request_sha256"],"native_effect_claimed":False})
        require(set(files)==required,"Missing/extra final session files")
        dates=strict_stream(raw,statuses,pre)
        for seq,row in rows.items():
            if row["request"]["operation"]=="pair":require(all(r["raw_date"]==dates[seq] for r in row["records"]),"Request date differs from preceding native frame")
    effects=[];seen=set()
    require(type(case["effects"]) is list and len(case["effects"])<=128,"Effect budget")
    for effect in case["effects"]:
        require(type(effect) is dict and set(effect)=={"sequence","before","after","comparison","expected_observed_effect"}
                and exact_int(effect["sequence"],1,len(items)) and effect["sequence"] not in seen,"Invalid/duplicate selected effect")
        seq=effect["sequence"];seen.add(seq);row=rows[seq];validate_pair(row,"dispatched",observer)
        docs=[inputs.doc(effect[k]) for k in ("before","after","comparison")]
        hashes={k+"_sha256":inputs.entries[effect[k]]["sha256"] for k in ("before","after")}
        effects.append(validate_effect(effect,row,*docs,hashes,observer))
    annotations=validate_annotations(case["annotations"],rows)
    # Every submitted one of the ten directions must be honestly accounted for,
    # including unknown/absent effects; setup actions outside ten remain submits only.
    expected_effects={seq for seq,row in rows.items() if row["request"]["operation"]=="pair" and row["request"]["mode"]=="submit" and row["request"]["action"] in observer.ACTIONS}
    require(seen==expected_effects,"Selected-direction submit missing explicit observed/unknown comparison")
    inputs.finish();dependencies(root)
    return {"schema_version":1,"purpose":"v14_directional_finalized_experiment_review","status":"reviewed_stopped_session",
        "pid":PID,"creation":CREATION,"world_cookie":WORLD,"window_thread":THREAD,"dll_sha256":DLL_SHA,"manifest_sha256":MANIFEST_SHA,
        "phase_case_counts":COUNTS,"default_owned_peace_only":True,"requests":inventory,"effects":effects,"annotations":annotations,
        "observed_effect_count":sum(e["observed_effect"] for e in effects),"complete_log":inputs.entries[files["research-1375.jsonl"]],
        "case_content_sha256":sha(typed(case).encode()),"input_artifacts":inputs.entries,
        "game_process_accessed":False,"production_backend_registered":False,"production_execution_verified":False,
        "war_identity_verified":False,"white_peace_verified":False,"save_reload_verified":False,"request_id_causality_verified":False,
        "native_ai_acceptance_verified":False,"strict_live_single_player_verified":False,"world_epoch_verified":False,
        "limitations":["Frozen records are content-bound, not authenticated engine telemetry.",
            "Default owned empty offer proves no war, peace proposal or white-peace execution.",
            "Same-date two-pass effects do not prove atomicity, exact request attribution or all world state.",
            "UI refusal annotations are not native rejection evidence; missing selected state remains unknown.",
            "Supervised speed proves supplied callback/readback/exit boundaries, not a universal real-time pause guarantee."]}


def template():
    return {"schema_version":1,"purpose":"v14_directional_finalized_experiment_case","finalized":False,"inputs":{},
        "exit":None,"stopped_audit":None,"preflight_case":None,"preflight_summary":None,"session_files":{},"final_status":None,
        "requests":[],"effects":[],"annotations":[],"persistence":[]}


def write_new(path,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()
    with Path(path).open("xb") as stream:stream.write(raw);stream.flush()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    t=sub.add_parser("template");t.add_argument("--output",type=Path,required=True)
    r=sub.add_parser("review");r.add_argument("--case",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="template":write_new(args.output,template())
        else:
            raw=bounded(args.case,MAX_CASE);case=decode_json(raw.decode());result=review(case)
            require(bounded(args.case,MAX_CASE)==raw,"Case changed during review");write_new(args.output,result)
        return 0
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,ProbeError) as error:
        print("Directional experiment review rejected: "+str(error),file=sys.stderr);return 2

if __name__=="__main__":raise SystemExit(main())
