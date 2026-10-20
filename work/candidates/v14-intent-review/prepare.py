"""Deterministic isolated v14 repair candidate; never materialize/build/inject."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUT_SHA = "b6fe7b9cf921ef582efbd3926495f1d6cac1dd87117de9f551bd8991900376a4"
CANDIDATE_SOURCES = ("prepare.py", "owned_intent.py.inc", "publisher_tail.py.inc", "test_candidate.py", "verify_tests.py", "README.md")


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
def bounded(path):
    with Path(path).open("rb") as stream: raw = stream.read(2*1024*1024+1)
    if len(raw)>2*1024*1024: raise ValueError("Source/artifact budget exceeded: " + str(path))
    return raw
def version(raw): return raw.replace(b"v13",b"v14").replace(b"V13",b"V14")
def replace(text, old, new):
    if text.count(old) != 1: raise ValueError("Expected unique anchor: " + old[:100])
    return text.replace(old,new)


def audit():
    if sha(bounded(HERE/"input-pins.json"))!="71d19968cf55ebc92156dfb432996be7ae9b8b0ae5660136b904cc914e86112a":
        raise ValueError("Original failed pin inventory changed")
    raw=bounded(HERE/"input-pins-v14-support.json")
    if sha(raw)!=INPUT_SHA: raise ValueError("Input pins changed")
    pins=json.loads(raw)["inputs"]
    for row in pins:
        raw=bounded(ROOT/row["path"])
        if len(raw)!=row["bytes"] or sha(raw)!=row["sha256"]: raise ValueError("Frozen input changed: "+row["path"])
    return pins


def support_delta(pins):
    current=bounded(ROOT/'bridge/diplomacy_lab_http.py')
    text=current.decode()
    text=replace(text,'from bridge.diplomacy_research_capabilities import DISCOVERY_CATALOG_ACTIONS, V12_CATALOG_BINDINGS',
        'from bridge.diplomacy_research_capabilities import DISCOVERY_CATALOG_ACTIONS')
    text=replace(text,'        catalog_ids = {name for action in lab.ACTIONS for name in V12_CATALOG_BINDINGS.get(action, [action])}\n        rows = [row for row in rows if row["action_id"] in catalog_ids]',
        '        rows = [row for row in rows if row["action_id"] in lab.ACTIONS]')
    old=text.encode()
    expected='08e91a343f7e1f0b06190d423db78cb852e9f5052865b722efa6b2b9c738b84e'
    if sha(old)!=expected: raise ValueError('Support delta exceeds the two approved discovery changes')
    return {'path':'bridge/diplomacy_lab_http.py','v13_sha256':expected,'v14_sha256':sha(current),
        'changes':['capabilities imports V12_CATALOG_BINDINGS','capabilities filters explicit catalog alias IDs'],
        'reverse_exact_two_changes_reconstructs_v13_pin':True,'v13_manifest_modified':False,
        'v13_current_support_verification_passes':False,'dispatch_or_status_logic_changed':False}


def fixture_pins():
    path=ROOT/'work/candidates/v13-host-review/input-pins.json'
    if sha(bounded(path))!='6aebb6a2b7b3bf78797491e2e99388e3e9b92a78933d30d07aa45d6ed89db75c':raise ValueError('Offline fixture pin source changed')
    rows=[r for r in json.loads(bounded(path))['inputs'] if r['role']=='offline_fixture_dependency']
    old_review=json.loads(bounded(ROOT/'work/candidates/v13-host-review/review.json'))
    test=next(r for r in old_review['candidate_sources'] if r['path']=='test_candidate.py')
    rows.append(test|{'path':'work/candidates/v13-host-review/test_candidate.py'})
    for row in rows:
        if sha(bounded(ROOT/row['path']))!=row['sha256']:raise ValueError('Offline fixture changed: '+row['path'])
    return rows


def protocol(raw, native, native_review_sha, support):
    text=raw.decode()
    start=text.index("NATIVE_REVIEW_SHA256 = ");end=text.index("SOURCES = tuple(EXPECTED_NATIVE_SOURCES)",start)
    text=text[:start]+("NATIVE_REVIEW_SHA256 = "+repr(native_review_sha)+"\nEXPECTED_NATIVE_SOURCES = "+repr(native)+"\n")+text[end:]
    start=text.index("EXPECTED_SUPPORT_SOURCES = ");end=text.index("SUPPORT_SOURCES = tuple(EXPECTED_SUPPORT_SOURCES)",start)
    text=text[:start]+"EXPECTED_SUPPORT_SOURCES = "+repr(support)+"\n"+text[end:]
    old='''    phase_attempted = {}
    for phase, (_,claim,_) in PHASES.items():
        paths = (Path(session)/claim, Path(session)/(claim+".host-intent"))
        for path in paths: _no_links(path)
        phase_attempted[phase] = phase in phase_started or any(path.exists() for path in paths)
'''
    new='''    phase_attempted, phase_attempt_sources = {}, {}
    for phase, (_,claim,_) in PHASES.items():
        paths = (Path(session)/claim, Path(session)/(claim+".host-intent"))
        for path in paths: _no_links(path)
        source = {"native_started": phase in phase_started, "native_claim": paths[0].exists(), "host_intent": paths[1].exists()}
        phase_attempt_sources[phase] = source
        phase_attempted[phase] = any(source.values())
'''
    text=replace(text,old,new)
    text=replace(text,'            "phase_attempted": phase_attempted,','            "phase_attempted": phase_attempted, "phase_attempt_sources": phase_attempt_sources,')
    marker="def publish_research("
    text=replace(text,marker,bounded(HERE/"owned_intent.py.inc").decode()+marker)
    start=text.index('    publish_exclusive(intent_path, (canonical(intent) + "\\n").encode())')
    end=text.index('    return {"research_only": True',start)
    text=text[:start]+bounded(HERE/"publisher_tail.py.inc").decode()+text[end:]
    # Public fail-closed contract is byte-identical apart from version naming.
    old_tree,new_tree=ast.parse(raw.decode()),ast.parse(text)
    for name in ("check_ready","prepare_request"):
        old_node=next(n for n in old_tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        new_node=next(n for n in new_tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        if ast.dump(old_node)!=ast.dump(new_node): raise ValueError("Unexpected public readiness/request delta")
    return text.encode()


def render():
    pins=audit(); test_pins=fixture_pins(); outputs={}; entries=[]; natives=[]; diffs=[]
    for row in pins:
        if row["role"] not in ("frozen_native","frozen_host","frozen_fixture"): continue
        dest=row["path"].replace("v13","v14")
        raw=bounded(ROOT/row["path"])
        value=raw if row["role"]=="frozen_fixture" else version(raw)
        if row["role"]=="frozen_native":
            # Exact replacement, not semantic guess: record zero non-version delta.
            if value!=version(raw): raise ValueError("Native non-version delta")
            natives.append({"path":dest,"bytes":len(value),"sha256":sha(value),"origin":row["path"],"origin_sha256":row["sha256"],"non_version_delta":False})
        outputs["generated/"+dest]=value
        entries.append({"path":dest,"origin":row["path"],"role":row["role"]})
    native_review={"schema_version":1,"purpose":"v14_native_version_only_source_review","input_pins_sha256":INPUT_SHA,
        "source_count":20,"sources":natives,"native_logic_changed":False,"formal_build_performed":False,"materialized":False}
    native_raw=encoded(native_review);outputs["native-source-review.json"]=native_raw
    expected={r["path"]:r["sha256"].upper() for r in natives}
    name="generated/work/native/lab_protocol_v14_1375.py"
    support={r['path']:r['sha256'].upper() for r in pins if r['role']=='shared_support'}
    outputs[name]=protocol(outputs[name],expected,sha(native_raw),support)
    for entry in entries:
        value=outputs["generated/"+entry["path"]]
        if entry["path"].endswith(".py"): ast.parse(value)
        entry.update(bytes=len(value),sha256=sha(value))
        old=bounded(ROOT/entry["origin"]).decode()
        new=value.decode()
        if old!=new:
            diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=entry["origin"],tofile=entry["path"]))
    counts={r:sum(e["role"]==r for e in entries) for r in ("frozen_native","frozen_host","frozen_fixture")}
    if counts!={"frozen_native":20,"frozen_host":11,"frozen_fixture":5}: raise ValueError("Source set differs")
    outputs["new-files.json"]=encoded({"schema_version":1,"files":entries,"counts":counts,"materialized":False})
    outputs["candidate.diff"]="".join(diffs).encode()
    outputs["support-delta.json"]=encoded(support_delta(pins))
    own=[{"path":p,"bytes":len(bounded(HERE/p)),"sha256":sha(bounded(HERE/p))} for p in CANDIDATE_SOURCES]
    review={"schema_version":1,"purpose":"v14_minimal_owned_phase_intent_repair","input_pins_sha256":INPUT_SHA,
        "input_count":len(pins),"native_source_review_sha256":sha(native_raw),"candidate_sources":own,
        "offline_fixture_inputs":test_pins,
        "outputs":[{"path":p,"bytes":len(v),"sha256":sha(v)} for p,v in sorted(outputs.items())],
        "phase_counts":[20,1,72,72],"action_ids":36,"native_logic_changed":False,
        "public_check_ready_changed":False,"public_override_parameter_added":False,
        "materialized":False,"formal_build_performed":False,"game_accessed":False,"execution_verified":False,
        "scope":"Only current CREATE_NEW held intent can be recognized during same invocation's fresh stage recheck. Old intents never retry."}
    outputs["review.json"]=encoded(review)
    return outputs


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--check",action="store_true");args=parser.parse_args(argv)
    values=render()
    for name,raw in values.items():
        path=HERE/name
        if args.check:
            if not path.is_file() or bounded(path)!=raw: raise ValueError("Stale/missing candidate: "+name)
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(json.dumps({"check":args.check,"inputs":54,"new_files":36,"native_version_only":True,"review_sha256":sha(values['review.json']),
        "native_review_sha256":sha(values['native-source-review.json']),"materialized":False,"built":False}))
    return 0
if __name__=="__main__":raise SystemExit(main())
