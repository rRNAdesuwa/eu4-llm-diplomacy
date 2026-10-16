"""Offline v16 stopped-session review. No process, publication or native API."""
from copy import deepcopy
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MIRROR=ROOT/"work/candidates/v16-acceptance-initialization-review/files"
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(MIRROR))
from work.native import lab_protocol_v16_1375 as lab
from tools import verify_diplomacy_acceptance_v16 as acceptance

require=lab.require
SELECTED=frozenset(("offer_fleet_basing_rights","revoke_fleet_basing_rights","insult"))
COUNTS={"lifecycle":20,"owned_peace":1,"preview":72,"command":72}
SCOPE_KEYS={"pid","creation","world_cookie","window_thread","initial_raw_date","dll_sha256","manifest_sha256",
    "bridge_start_rva","prefix_bytes","prefix_sha256","preflight_case","preflight_summary"}


def bounded(path,maximum=8*1024*1024):
    with Path(path).open("rb") as stream:raw=stream.read(maximum+1)
    require(len(raw)<=maximum,"Bounded file limit")
    return raw


def digest(raw):return hashlib.sha256(raw).hexdigest()
def integer(value,low=0,high=2**64-1):return type(value) is int and low<=value<=high
def typed(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
def same(a,b):return typed(a)==typed(b)


def load(path):
    name="v16_offline_"+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def dependencies():
    pins=json.loads(bounded(HERE/"pins.json",512*1024));total=0
    require(type(pins.get("files")) is dict and 1<=len(pins["files"])<=256,"Dependency inventory bound")
    for name,row in pins["files"].items():
        require(type(name) is str and "\\" not in name and ":" not in name and str(PurePosixPath(name))==name
            and not PurePosixPath(name).is_absolute() and all(p not in (".","..") for p in PurePosixPath(name).parts),"Dependency path")
        require(type(row) is dict and set(row)=={"bytes","sha256"} and integer(row["bytes"],1,8*1024*1024)
            and type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",row["sha256"]),"Dependency descriptor")
        path=ROOT
        for part in PurePosixPath(name).parts:
            path=path/part;require(not path.is_symlink() and not path.is_junction(),"Linked dependency")
        require(path.resolve().is_relative_to(ROOT.resolve()),"Escaped dependency")
        raw=bounded(path);total+=len(raw)
        require(total<=32*1024*1024 and len(raw)==row["bytes"] and digest(raw)==row["sha256"],"Changed frozen dependency: "+name)
    directional=load(ROOT/"work/candidates/directional-pair-observer-1375/observer.py");directional.verify_contract(ROOT)
    insult=load(ROOT/"work/candidates/ordinary-insult-observer-1375/observer.py");insult.load_contract()
    return directional,insult


def validate_scope(scope):
    require(type(scope) is dict and set(scope)==SCOPE_KEYS,"Exact explicit v16 scope required")
    require(integer(scope["pid"],1,2**32-1) and integer(scope["window_thread"],1,2**32-1)
        and type(scope["creation"]) is str and re.fullmatch(r"[0-9a-f]{16}",scope["creation"]) and int(scope["creation"],16)>0,"Exact process/thread identity")
    require(type(scope["world_cookie"]) is str and re.fullmatch(r"0x[0-9a-f]+",scope["world_cookie"])
        and int(scope["world_cookie"],16)>=0x10000 and integer(scope["initial_raw_date"],1,2**31-1),"World/date bound")
    require(integer(scope["bridge_start_rva"],1,2**32-1) and integer(scope["prefix_bytes"],1,8*1024*1024)
        and all(type(scope[k]) is str and re.fullmatch(r"[0-9a-f]{64}",scope[k]) for k in ("dll_sha256","manifest_sha256","prefix_sha256")),"Build/prefix binding")
    for name in ("preflight_case","preflight_summary"):
        require(type(scope[name]) is str and scope[name].startswith("work/runtime/native1375-v16/")
            and ".." not in Path(scope[name]).parts and "\\" not in scope[name] and ":" not in scope[name],"Explicit v16 preflight path")


def configure(scope):
    """Fresh modules per review; never mutate any imported frozen predecessor."""
    validate_scope(scope);directional,insult=dependencies()
    base=load(HERE/"base.py");pre=load(HERE/"preflight.py")
    base.lab=pre.lab=lab;base.acceptance_validator=acceptance
    for key,value in {"PID":scope["pid"],"CREATION":scope["creation"],"THREAD":scope["window_thread"],
        "WORLD":scope["world_cookie"],"INITIAL_DATE":scope["initial_raw_date"],"DLL_SHA":scope["dll_sha256"],
        "MANIFEST_SHA":scope["manifest_sha256"],"PREFLIGHT_CASE":scope["preflight_case"],
        "PREFLIGHT_SUMMARY":scope["preflight_summary"],"PREFIX_BYTES":scope["prefix_bytes"],"PREFIX_SHA":scope["prefix_sha256"],
        "SESSION":f"work/runtime/native1375-v16/session-{scope['pid']}-{scope['creation']}"}.items():setattr(base,key,value)
    pre.BUILD="work/runtime/native1375-v16/build.json";pre.BUILD_SHA=scope["manifest_sha256"]
    pre.DLL_SHA=scope["dll_sha256"];pre.BRIDGE_START_RVA=scope["bridge_start_rva"]
    pre.EXPECTED_SESSION={"pid":scope["pid"],"creation":scope["creation"],"world_cookie":scope["world_cookie"],
        "raw_date":scope["initial_raw_date"],"window_thread":scope["window_thread"]}
    pre.PINS={name:row["sha256"] for name,row in json.loads(bounded(HERE/"pins.json"))["files"].items()}
    def fixed_build(root=ROOT):
        manifest,h=lab.verify_build(root=Path(root),output=Path(root)/"work/runtime/native1375-v16")
        require(h==scope["manifest_sha256"] and manifest["dll_sha256"].lower()==scope["dll_sha256"]
            and type(manifest["bridge_start_export_rva"]) is int and manifest["bridge_start_export_rva"]==scope["bridge_start_rva"]
            and manifest["schema_version"]==3 and manifest["purpose"]==lab.PURPOSE and manifest["protocol_version"]=="EU4LAB/3",
            "Explicit v16 manifest/DLL/export binding differs")
        require((len(manifest["source_sha256"]),len(manifest["host_source_sha256"]),len(manifest["support_source_sha256"]))==(22,12,8)
            and len(lab.ACTIONS)==36 and tuple(lab.PHASES)==tuple(COUNTS),"Source/stage inventory differs")
        return manifest
    pre.fixed_build=fixed_build
    original_prefix=pre.strict_preflight_stream
    def prefix(raw,binding):
        replay=acceptance.AcceptanceSession({"pid":binding["pid"],"process_creation_filetime":binding["creation"],"window_thread":binding["window_thread"]})
        legacy=[]
        for line,event in base.parse_lines(raw):
            if event.get("event")=="research_frame":
                require(set(event)==base.FRAME_BOOLS|base.FRAME_INTS|base.FRAME_TEXT,"Preflight exact frame fields differ")
                replay.frame(event)
                require(same(replay.snapshot(),acceptance.empty_window()),"Preflight acceptance grant is not pristine")
                event={k:v for k,v in event.items() if not k.startswith("acceptance_")}
                # The old exact schema below rejects any other added field.
                legacy.append((typed(event)+"\n").encode())
            else:legacy.append(line)
        return original_prefix(b"".join(legacy),binding)
    pre.strict_preflight_stream=prefix
    original_status=pre.validate_status
    def prefix_status(document,evidence,pid,created):
        status=pre.captured_report(document,"request")
        require("acceptance_window" in status and same(status["acceptance_window"],evidence["acceptance_window"])
            and same(status["acceptance_window"],acceptance.empty_window()),"Preflight status acceptance differs")
        return original_status({k:v for k,v in status.items() if k!="acceptance_window"},evidence,pid,created)
    pre.validate_status=prefix_status
    base.dependencies=lambda root=ROOT:(dependencies() and (pre,directional))
    original_stream=base.strict_stream
    def stream(raw,statuses,preflight):
        result=original_stream(raw,statuses,preflight)
        latest=None;recorded_time=0
        for _,event in base.parse_lines(raw):
            name=event.get("event")
            if name=="research_frame":
                require(event["uptime_ms"]>=recorded_time,"Following health precedes its recorded claim/pending time")
                latest=event
            elif name in ("lab_request_claimed","lab_acceptance_pending"):
                value=event["claimed_uptime_ms" if name=="lab_request_claimed" else "uptime_ms"]
                require(latest is not None and integer(value,max(latest["uptime_ms"],recorded_time)),"Recorded claim/pending time regressed")
                recorded_time=value
        return result
    base.strict_stream=stream
    original_pair=base.validate_pair
    def pair(row,outcome,observer):
        if outcome=="dispatched":require(row["request"]["action"] in SELECTED,"Unreviewed submit action")
        return original_pair(row,outcome,observer)
    base.validate_pair=pair
    def controls(row,outcome):
        r=row["request"]
        require(r["operation"]=="accept" and outcome==("acceptance_enabled" if r["action"]=="accept_on" else "acceptance_disabled"),"Explicit control outcome differs")
        require([c["event"] for c in row["records"]]==["test_acceptance_begin","test_acceptance_complete"],"Control event order")
        c=row["records"][-1]
        require(c["reason"]==0 and c["no_native"] is False and all(c[k] is True for k in acceptance.SUCCESS_FIELDS),"No-native/unknown control is not a transition")
    base.validate_acceptance=controls
    def fixture(row):
        flags={"native_invoked","callback_returned","callback_success","arguments_unchanged","result_destroyed","world_identity_unchanged","callback_flag_restored"}
        false={"freeze_session","retry_allowed","fixture_effect_verified","diplomacy_submitted"}
        ints={"thread_id","reason","before_date","after_date","exception_code"}
        strings={"event","fixture_event","target","fixture_profile_sha256"}
        records=row["records"]
        require([c.get("event") for c in records]==["test_fixture_begin","test_fixture_complete"],"Fixture exact callback boundaries")
        for i,c in enumerate(records):
            require(set(c)==flags|false|ints|strings and all(type(c[k]) is bool for k in flags|false)
                and all(type(c[k]) is int for k in ints) and all(type(c[k]) is str for k in strings),"Fixture exact typed core schema")
            require(c["thread_id"]==scope["window_thread"] and c["reason"]==c["exception_code"]==0
                and c["before_date"]>=scope["initial_raw_date"] and c["after_date"]==(c["before_date"] if i else 0)
                and all(c[k] is bool(i) for k in flags) and all(c[k] is False for k in false),"Fixture begin/complete lifecycle differs")
        require(records[0]["before_date"]==records[1]["before_date"],"Fixture date changed")
    base.validate_fixture=fixture
    old_link=base.validate_legality_link
    def link(item,rows,ledger,observer):
        seq=item["sequence"];r=rows[seq]["request"]
        if r["operation"]=="pair" and r["mode"]=="submit" and seq>1 and rows[seq-1]["request"]["operation"]=="accept":
            on=rows[seq-1]["request"];prior=item["legality_sequence"]
            require(integer(prior,1,seq-2) and prior==seq-2 and on["action"]=="accept_on"
                and on["bound_submit_sequence"]==seq and on["bound_action"]==r["action"] and on["bound_target"]==r["target"],"Forced submit does not follow one bound on/legality")
            proof=rows[prior]
            require(ledger[prior]["outcome"]=="legality_allowed","Pre-on legality is not allowed")
            base.validate_pair(proof,"legality_allowed",observer)
            require(all(proof["request"][k]==r[k] for k in ("operation","action","actor","target","speed"))
                and proof["request"]["mode"]=="legality_only"
                and proof["records"][-1]["raw_date"]==rows[seq]["records"][-1]["raw_date"],"Pre-on legality action/role/date differs")
        else:old_link(item,rows,ledger,observer)
    base.validate_legality_link=link
    def windows(declared,rows,ledger,evidence,dates):
        require(type(declared) is list and len(declared)==1,"Exactly one explicit forced acceptance experiment")
        w=declared[0];keys={"legality_sequence","on_sequence","submit_sequence","off_sequence","action","target"}
        require(type(w) is dict and set(w)==keys and all(integer(w[k],1,128) for k in keys if k.endswith("sequence")),"Window schema")
        n=w["legality_sequence"]
        require((w["on_sequence"],w["submit_sequence"],w["off_sequence"])==(n+1,n+2,n+3)
            and w["action"]=="offer_fleet_basing_rights" and w["target"] in lab.TAGS and w["target"]!="FRA","Window bound order/action/target")
        require(set(seq for seq,r in rows.items() if r["request"]["operation"]=="accept")=={n+1,n+3},"Extra/unlisted acceptance control")
        fixtures=[(seq,row["request"]["action"]) for seq,row in rows.items() if row["request"]["operation"]=="fixture"]
        require(fixtures and fixtures[0]==(1,"fixture_on") and len(fixtures)<=2
            and (len(fixtures)==1 or fixtures[1][1]=="fixture_off" and fixtures[1][0]>n+3),"Explicit initial fixture and optional post-window cleanup only")
        for seq in (n,n+1,n+2,n+3):require(seq in rows,"Missing window request")
        for seq in (n,n+2):
            r=rows[seq]["request"]
            require(r["operation"]=="pair" and r["action"]==w["action"] and r["target"]==w["target"] and r["actor"]=="FRA","Window pair binding")
        require(ledger[n]["outcome"]=="legality_allowed" and ledger[n+2]["outcome"]=="dispatched"
            and ledger[n+2]["legality_sequence"]==n,"Window outcomes")
        for seq,action in ((n+1,"accept_on"),(n+3,"accept_off")):
            r=rows[seq]["request"]
            require(r["action"]==action and r["bound_action"]==w["action"] and r["bound_target"]==w["target"]
                and r["bound_submit_sequence"]==n+2,"Control changed immutable grant")
        require(len({dates[s] for s in (n,n+1,n+2,n+3)})==1,"Window date changed")
        final=evidence["acceptance_window"]
        require(final["state"]=="closed" and final["on_sequence"]==n+1 and final["submit_sequence"]==n+2
            and final["off_sequence"]==n+3 and final["action"]==w["action"] and final["target"]==w["target"],"Final window history not retained")
        for seq,row in rows.items():
            r=row["request"]
            if r["operation"]=="pair" and r["mode"]=="submit" and r["action"]=="revoke_fleet_basing_rights":
                require(seq>n+3 and dates[seq]>dates[n+2] and r["target"]==w["target"],"Offered fleet revoke requires later date and same direction")
        return [dict(w,forced_test_acceptance_window=True,reset_observed=True,natural_ai_acceptance_verified=False,
            asynchronous_override_use_verified=False,request_causality_verified=False)]
    base.validate_windows=windows
    old_effect=base.validate_effect
    def effect(case,row,before,after,comparison,hashes,observer):
        r=row["request"];require(r["action"] in SELECTED,"Selected effect unsupported")
        if r["action"]!="insult":
            result=old_effect(case,row,before,after,comparison,hashes,observer)
        else:
            for doc in (before,after):
                sample,state=insult.validated_report(doc)
                require(doc["source"]["before"]["pid"]==scope["pid"] and doc["source"]["expected_creation"]==scope["creation"]
                    and sample["identity"]["world"]==scope["world_cookie"] and sample["identity"]["raw_date"]==row["records"][-1]["raw_date"]
                    and sample["target"]==r["target"] and r["actor"]=="FRA","Insult world/identity/direction/date differs")
            computed=insult.compare_reports(before,after);computed["input_hashes"]={k:hashes[k+"_sha256"] for k in ("before","after")}
            require(same(computed,comparison) and not computed["errors"] and type(case["expected_observed_effect"]) is bool
                and computed["observed_effect"] is case["expected_observed_effect"],"Insult independent comparison differs")
            result={"sequence":case["sequence"],"action":"insult","target":r["target"],"observed_effect":computed["observed_effect"],
                "status":computed["status"],"request_causality_verified":False,"ai_acceptance_verified":False,"native_rejection_verified":False}
        result["forced_test_acceptance_window"]=r["action"]=="offer_fleet_basing_rights"
        return result
    base.validate_effect=effect
    return base,pre


def review(case,root=ROOT):
    require(type(case) is dict and "scope" in case,"Explicit scope required")
    source_names=("reviewer.py","base.py","preflight.py","prepare.py","pins.json")
    sources={name:digest(bounded(HERE/name)) for name in source_names}
    base,pre=configure(case["scope"])
    result=base.review({k:v for k,v in case.items() if k!="scope"},root)
    dependencies();result["scope"]=deepcopy(case["scope"])
    result["case_content_sha256"]=digest(typed(case).encode())
    result["natural_ai_acceptance_verified"]=False
    require(all(digest(bounded(HERE/name))==value for name,value in sources.items()),"Reviewer sources changed during review")
    result["reviewer_sources_sha256"]=sources
    return result


def template():
    return {"schema_version":1,"purpose":"v16_directional_finalized_experiment_case","finalized":False,
        "scope":{k:None for k in sorted(SCOPE_KEYS)},"inputs":{},"exit":None,"stopped_audit":None,
        "preflight_case":None,"preflight_summary":None,"session_files":{},"final_status":None,"requests":[],
        "effects":[],"acceptance_windows":[],"annotations":[],"persistence":[]}


def write_new(path,value):
    with Path(path).open("xb") as stream:stream.write((json.dumps(value,sort_keys=True,indent=2)+"\n").encode())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("template","preflight","review","check"))
    parser.add_argument("--case",type=Path);parser.add_argument("--scope",type=Path);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="template":result=template()
        else:
            raw=bounded(args.case,512*1024);case=lab.decode_json(raw.decode())
            if args.command=="preflight":
                scope_raw=bounded(args.scope,8192);scope=lab.decode_json(scope_raw.decode());_,pre=configure(scope);result=pre.review(case,root=ROOT)
                require(bounded(args.scope,8192)==scope_raw,"Scope changed during review");dependencies()
            else:result=review(case)
            require(bounded(args.case,512*1024)==raw,"Case changed during review")
        if args.command=="check":require(same(result,lab.decode_json(bounded(args.output).decode())),"Stored review differs")
        else:write_new(args.output,result)
        return 0
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:
        print("v16 experiment review rejected: "+str(error),file=sys.stderr);return 2


if __name__=="__main__":raise SystemExit(main())
