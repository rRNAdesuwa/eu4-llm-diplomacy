"""Prepare only an offline v9 fixture candidate from frozen v8 files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "work/candidates/fixture-v8-1375"
sys.path.insert(0, str(ROOT))
from tools.build_diplomacy_catalog import parse_script, scalar

FILES = tuple("mod/llm_diplomacy_test/" + name for name in (
    "descriptor.mod", "common/defines/zz_llm_diplomacy_test.lua", "events/llmt_fixture.txt",
    "common/event_modifiers/llm_diplomacy_test.txt", "common/opinion_modifiers/llmt_fixture.txt"))
EVENTS = FILES[2]
OLD_PROFILE = "68f5c90d63343fd2db64ccd64bd232877409dc43302bf5d40c854c30c84ae918"


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def shape(node):
    return [node.key,node.value,[shape(child) for child in node.children]]


def profile(profile_id,files):
    return {"profile_id":profile_id,"source_sha256":{key:sha(raw).upper() for key,raw in files.items()}}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    before={name:(SOURCE/name).read_bytes() for name in FILES}
    old=profile("1375_test_fixture_v2",before)
    if sha(canonical(old).encode("ascii"))!=OLD_PROFILE:
        raise ValueError("Frozen v8 fixture profile mismatch; refuse rebase")
    text=before[EVENTS].decode("utf-8")
    if text.count("create_alliance = NAV")!=1:
        raise ValueError("Expected exactly the single fixed NAV alliance effect")
    after=dict(before)
    after[EVENTS]=text.replace("create_alliance = NAV","vassalize = NAV").encode("utf-8")
    old_nodes=parse_script(text); new_nodes=parse_script(after[EVENTS].decode("utf-8"))
    expected=[shape(node) for node in old_nodes]
    replaced=0
    old_events=[node for node in old_nodes if node.key=="country_event"]
    new_events=[node for node in new_nodes if node.key=="country_event"]
    if [scalar(node,"id") for node in old_events]!=["llmt.1","llmt.2"]:
        raise ValueError("Unexpected fixed event IDs")
    for node in expected:
        if node[0]!="country_event" or ["id","llmt.1",[]] not in node[2]:continue
        for child in node[2]:
            if child[0]!="immediate":continue
            for effect in child[2]:
                if effect==["create_alliance","NAV",[]]:
                    effect[0]="vassalize";replaced+=1
    if replaced!=1 or expected!=[shape(node) for node in new_nodes]:
        raise ValueError("AST differs beyond llmt.1 immediate create_alliance->vassalize NAV")
    event_checks=[]
    for old_event,new_event in zip(old_events,new_events,strict=True):
        options=[child for child in new_event.children if child.key=="option"]
        if scalar(new_event,"hidden")!="yes" or len(options)!=1 or shape(options[0])!=["option",None,[["name","OK",[]]]]:
            raise ValueError("Exactly one empty OK option must remain")
        event_checks.append({"id":scalar(new_event,"id"),"option_count":1,"option_effect_count":0,
                             "unchanged":shape(old_event)==shape(new_event),
                             "new_ast_sha256":sha(canonical(shape(new_event)).encode("ascii"))})
    new=profile("1375_test_fixture_v3",after)
    report={"purpose":"offline_candidate_only","installed":False,"runtime_verified":False,
            "old_profile":old,"old_profile_sha256":OLD_PROFILE,
            "fixture_profile":new,"fixture_profile_sha256":sha(canonical(new).encode("ascii")),
            "changed_files":[EVENTS],"event_checks":event_checks,
            "ast_only_change":{"event_id":"llmt.1","scope":"immediate","old_key":"create_alliance",
                               "new_key":"vassalize","value":"NAV","replacement_count":1},
            "source_effects_repeated_in_options":False,
            "required_baseline":{"player":"FRA","target":"NAV","target_exists":True,
                                 "target_independent":True,"fra_nav_alliance":False,"bilateral_truce":False},
            "limits":["Candidate alone is not installed/loaded/effect proof",
                      "Use only reviewed original baseline or after_improve save; never positive NAV-vassal save",
                      "fixture_off removes modifiers/opinions but does not dissolve the vassal relation",
                      "Native callback success does not prove relation change or absence of truce",
                      "Independent dependency and bilateral-truce observation is required before cancel testing"],
            "evidence":{"report":"work/reports/native-vassal-effects-1375.json",
                        "report_sha256":"3c47d50e9bda8ced0933f61f4490f9347a9e133e74e7afcfb9f6807311d8eed6"}}
    outputs={HERE/name:raw for name,raw in after.items()}
    outputs[HERE/"fixture-profile.json"]=(json.dumps(report,indent=2,ensure_ascii=False)+"\n").encode()
    for path,raw in outputs.items():
        if args.check:
            if not path.is_file() or path.read_bytes()!=raw:raise ValueError(f"Candidate mismatch: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    if before!={name:(SOURCE/name).read_bytes() for name in FILES}:
        raise ValueError("Frozen v8 candidate changed during generation")
    print(canonical({"fixture_profile_sha256":report["fixture_profile_sha256"],
                     "event_file_sha256":sha(after[EVENTS]).upper(),"check":args.check,
                     "frozen_v8_unchanged":True,"runtime_verified":False}))


if __name__=="__main__":main()
