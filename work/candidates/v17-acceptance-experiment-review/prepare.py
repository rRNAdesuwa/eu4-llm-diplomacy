"""Generate isolated reviewer copies only; no actual case, native or game work."""
from pathlib import Path
import hashlib
import json
import difflib
import argparse

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCES={
    "base.py":("work/candidates/v14-directional-experiment-review-r3/reviewer.py","c5953d10cc354cfacfda1dee2353532260e71b7482b3e651601d7d172dbc6478"),
    "preflight.py":("work/candidates/v14-directional-preflight-review/reviewer.py","25deb003bb940f87d82c92ec88956544231f0b7fe339474ed2138c5f3d478a90")}


def digest(raw):return hashlib.sha256(raw).hexdigest()


def bounded(path):
    with path.open("rb") as stream:raw=stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError("Input budget")
    return raw


def replace(raw,old,new):
    if raw.count(old)!=1:raise ValueError("Expected unique patch: "+old[:90])
    return raw.replace(old,new)


def generate():
    outputs={};diffs={}
    for target,(path,pin) in SOURCES.items():
        original=bounded(ROOT/path)
        if pin and digest(original)!=pin:raise ValueError("Frozen reviewer changed")
        raw=original.decode().replace("v14","v17").replace("V14","V17")
        if target=="base.py":
            start=raw.index('PID, CREATION, THREAD = ');end=raw.index('COUNTS = ',start)
            raw=raw[:start]+('PID = CREATION = THREAD = WORLD = INITIAL_DATE = None\n'
                'DLL_SHA = MANIFEST_SHA = PREFLIGHT_CASE = PREFLIGHT_SUMMARY = None\n'
                'PREFIX_BYTES = PREFIX_SHA = SESSION = None\n')+raw[end:]
            start=raw.index('def dependencies(');end=raw.index('\n\nclass Inputs:',start)
            raw=raw[:start]+'def dependencies(root=ROOT):\n    raise ValueError("Configure through reviewer.py with explicit scope")\n'+raw[end:]
            raw=replace(raw,'"session_files","final_status","requests","effects","annotations","persistence"}',
                '"session_files","final_status","requests","effects","annotations","persistence","acceptance_windows"}')
            raw=replace(raw,'"native_speed_index","last_sequence","lease_deadline_uptime_ms"}',
                '"native_speed_index","last_sequence","lease_deadline_uptime_ms","acceptance_flag","acceptance_origin_sequence","acceptance_submit_sequence","acceptance_off_sequence"}')
            raw=replace(raw,'FRAME_TEXT={"event","fixture_profile_sha256","process_creation_filetime","world_cookie","player_handle"}',
                'FRAME_TEXT={"event","fixture_profile_sha256","process_creation_filetime","world_cookie","player_handle","acceptance_state","acceptance_action","acceptance_target"}')
            raw=replace(raw,'    prefix_requests={};pending_sequence=None',
                '    prefix_requests={};pending_sequence=None\n    acceptance=acceptance_validator.AcceptanceSession({"pid":PID,"process_creation_filetime":CREATION,"window_thread":THREAD})')
            raw=replace(raw,'            strict_frame(event)','            strict_frame(event)\n            acceptance.frame(event)')
            raw=replace(raw,'"lab_lease_complete"},"Unknown/duplicate post-preflight event")',
                '"lab_lease_complete","lab_acceptance_pending"},"Unknown/duplicate post-preflight event")')
            raw=replace(raw,'record={key:event[key] for key in ("pid","sequence","expires","operation","mode","action","actor","target","speed")}',
                'record={key:event[key] for key in lab.FIELDS if key!="creation"}')
            raw=replace(raw,'                record["creation"]=CREATION',
                '                record["creation"]=CREATION\n                acceptance.claim(record,prefix_requests,event.get("claimed_uptime_ms"))')
            raw=replace(raw,'            if name=="lab_native_record" and event.get("lease_pause") is False:',
                '            if name=="lab_acceptance_pending":acceptance.pending_grant(event)\n            if name=="lab_native_record" and event.get("lease_pause") is False:')
            raw=replace(raw,'                prefix_requests[sequence]["records"].append(event["record"])',
                '                prefix_requests[sequence]["records"].append(event["record"])\n                if prefix_requests[sequence]["request"]["operation"]=="accept":acceptance.core(event["record"])')
            raw=replace(raw,'                prefix_requests[sequence]["complete"]=event;pending_sequence=None',
                '                acceptance.complete(event,prefix_requests[sequence]["records"][-1])\n                prefix_requests[sequence]["complete"]=event;pending_sequence=None')
            raw=replace(raw,'                seen.add(status["log_sha256"])',
                '                require(same(status.get("acceptance_window"),acceptance.snapshot()),"Status window borrows future or wrong grant state")\n                seen.add(status["log_sha256"])')
            raw=replace(raw,'    return request_dates,speed_traces',
                '    require(acceptance.pending is None and acceptance.window["state"]=="closed" and last["acceptance_flag"]==0,"Stopped acceptance window not closed")\n    return request_dates,speed_traces')
            raw=replace(raw,'{k:request[k] for k in ("operation","mode","action","actor","target","speed")}',
                '{k:request[k] for k in ("operation","mode","action","actor","target","speed","bound_action","bound_target","bound_submit_sequence")}')
            raw=replace(raw,'            elif request["operation"]=="fixture":',
                '            elif request["operation"]=="accept":validate_acceptance(row,item["outcome"])\n            elif request["operation"]=="fixture":')
            raw=replace(raw,'                require(item["outcome"]=="fixture_callback_returned",',
                '                validate_fixture(row)\n                require(item["outcome"]=="fixture_callback_returned",')
            raw=replace(raw,'    effects=[];seen=set()',
                '    windows=validate_windows(case["acceptance_windows"],rows,ledger,evidence,dates)\n    effects=[];seen=set()')
            raw=replace(raw,'if row["request"]["operation"]=="pair" and row["request"]["mode"]=="submit" and row["request"]["action"] in observer.ACTIONS}',
                'if row["request"]["operation"]=="pair" and row["request"]["mode"]=="submit"}')
            raw=replace(raw,'"phase_case_counts":COUNTS,"default_owned_peace_only":True,',
                '"phase_case_counts":COUNTS,"default_owned_peace_only":True,"acceptance_windows":windows,"forced_test_acceptance_window":True,')
            raw=replace(raw,'"requests":[],"effects":[],"annotations":[],"persistence":[]}',
                '"requests":[],"effects":[],"annotations":[],"persistence":[],"acceptance_windows":[]}')
        else:
            start=raw.index('# Root\'s explicit single-build pins;');end=raw.index('COUNTS = ',start)
            raw=raw[:start]+('BUILD_SHA = DLL_SHA = BRIDGE_START_RVA = EXPECTED_SESSION = None\nPINS = {}\n')+raw[end:]
            start=raw.index('def fixed_build(');end=raw.index('\n\nclass Inventory:',start)
            raw=raw[:start]+'def fixed_build(root=ROOT):\n    raise ValueError("Configure through reviewer.py with explicit scope")\n'+raw[end:]
        raw=raw[:raw.rfind('\nif __name__')]+ '\nif __name__ == "__main__":\n    raise SystemExit("Use reviewer.py with an explicit frozen scope; this is an internal generated module.")\n'
        outputs[target]=raw.encode()
        diffs[target+".diff"]="".join(difflib.unified_diff(original.decode().splitlines(True),raw.splitlines(True),fromfile=path,tofile=target)).encode()
    return outputs|diffs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument("--check",action="store_true");group.add_argument("--generate",action="store_true")
    args=parser.parse_args()
    for name,raw in generate().items():
        path=HERE/name
        if args.check:
            if bounded(path)!=raw:raise ValueError("Generated reviewer differs: "+name)
        else:
            if path.exists() and bounded(path)!=raw:raise ValueError("Refuse overwrite existing proposal")
            if not path.exists():
                with path.open("xb") as stream:stream.write(raw)
    print(json.dumps({"checked":True,"game_accessed":False,"actual_case_read":False}))


if __name__=="__main__":main()
