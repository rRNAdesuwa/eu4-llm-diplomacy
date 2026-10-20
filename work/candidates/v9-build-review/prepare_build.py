"""Create/recheck isolated v9 sources; never installs or contacts a game process."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from work.native import lab_protocol_v8_1375 as old

OLD_PROFILE="68f5c90d63343fd2db64ccd64bd232877409dc43302bf5d40c854c30c84ae918"
NEW_PROFILE="f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507"
OLD_DLL="43BFC582EE15E612410B2CC8D8F9B63CA6D47F2135CBD2301578718901E557A4"
TOOLS=["work/native/lab_protocol_v8_1375.py","work/native/record_lab_v8_build.py",
       "work/native/inject_lab_v8_1375.py","work/native/run_lab_speed_v8_1375.py",
       "tools/request_diplomacy_lab_v8.py"]
PARSER=["work/native/v8/test-lab-request-1375.cpp","work/native/v8/test-lab-request-1375.cmd"]
DISALLOWED_SAVE='    "llm_diplomacy_1375_v7_marriage_vassal_20261008a.eu4": "F6A56C25FD366522C5F625BAFF086B33F02473EDCD34AAE3E3C2984D30436FB8",\n'
BASELINE_PATCH_SHA="395b7fa19fc21a8249e537bc0cb4aee22c6b84a00d7a8ea4a379500855561ee7"


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def changed(raw):
    return raw.replace(b"v8",b"v9").replace(OLD_PROFILE.encode(),NEW_PROFILE.encode())


def baseline_patch(raw):
    payload=(HERE/"fixture-baseline-patch.json").read_bytes()
    if hashlib.sha256(payload).hexdigest()!=BASELINE_PATCH_SHA:raise ValueError("Baseline guard patch changed")
    patch=json.loads(payload)
    if hashlib.sha256(raw).hexdigest()!=patch["source_sha256"]:raise ValueError("Baseline patch source changed")
    for part in reversed(patch["replacements"]):
        offset=part["byte_offset"];before=part["before"].encode();after=part["after"].encode()
        if raw[offset:offset+len(before)]!=before:raise ValueError("Baseline patch context differs")
        raw=raw[:offset]+after+raw[offset+len(before):]
    if hashlib.sha256(raw).hexdigest()!=patch["result_sha256"]:raise ValueError("Baseline patch result differs")
    return raw


def reference_updates(previous,current):
    """Root-authorized offline CLI metadata change; never waives native hashes."""
    if previous.keys()!=current.keys():raise ValueError("Frozen source/build file set changed")
    updates=[]
    for name in previous:
        if previous[name]==current[name]:continue
        if name!="tools/request_diplomacy_lab_v8.py":raise ValueError("Frozen bytes changed: "+name)
        before=b'historical.update(invoked_cli_protocol=lab.PROTOCOL, discovery_source="v6_v7_reviewed_history_only", v8_live_readiness=None)'
        after=b'historical.update(invoked_cli_protocol=lab.PROTOCOL, v8_live_readiness=None)'
        raw=(ROOT/name).read_bytes()
        if raw.count(after)!=1 or before in raw:raise ValueError("Unexpected history CLI edit")
        restored=raw.replace(after,before).replace(b"\r\n",b"\n")
        if hashlib.sha256(restored).hexdigest().upper()!=previous[name]:
            raise ValueError("History CLI changed beyond authorized offline metadata line")
        updates.append({"path":name,"before_sha256":previous[name],"after_sha256":current[name],
                        "scope":"Only inherit shared reviewed-history discovery_source; v8_live_readiness remains None; LF-to-CRLF formatting"})
    return updates


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument("--check",action="store_true")
    mode.add_argument("--refresh-review",action="store_true",help="Check all source bytes and update only source-review.json")
    args=ap.parse_args()
    verify_only=args.check or args.refresh_review
    manifest,_=old.verify_build()
    if manifest["dll_sha256"]!=OLD_DLL:raise ValueError("Unexpected frozen v8 DLL")
    candidate=json.loads((ROOT/"work/candidates/fixture-v9-1375/fixture-profile.json").read_text())
    if candidate["fixture_profile_sha256"]!=NEW_PROFILE:raise ValueError("Unexpected v9 candidate")
    names=list(old.SOURCES)+TOOLS+PARSER
    frozen={}
    for name in names:frozen[name]=digest(ROOT/name)
    for version in ("v6","v7","v8"):
        directory=ROOT/"work/native"/version
        if directory.exists():
            for path in directory.iterdir():
                if path.is_file():frozen[path.relative_to(ROOT).as_posix()]=digest(path)
        for path in (ROOT/"work/native").glob(f"test-fixture-{version}-1375.*"):
            frozen[path.relative_to(ROOT).as_posix()]=digest(path)
        output=ROOT/f"work/runtime/native1375-{version}"
        for leaf in (f"eu4_pair_lab_{version}_1375.dll","build.json"):
            path=output/leaf
            if path.exists():frozen[path.relative_to(ROOT).as_posix()]=digest(path)
    for name in old.FIXTURE_SOURCES:
        for path in (ROOT/name,old.fixture_source_path(ROOT,name)):
            frozen[path.relative_to(ROOT).as_posix()]=digest(path)
    baseline=HERE/"frozen-before.json"
    authorized_updates=[]
    if baseline.exists():
        previous=json.loads(baseline.read_text())
        authorized_updates=reference_updates(previous,frozen)
    elif verify_only:raise ValueError("Missing initial frozen snapshot")
    else:baseline.write_text(json.dumps(frozen,indent=2,sort_keys=True)+"\n")
    mapped=[]
    for name in names:
        raw=(ROOT/name).read_bytes()
        destination=name.replace("v8","v9")
        expected=changed(raw)
        guarded=name=="work/native/test-fixture-v8-1375.cpp"
        if guarded:expected=baseline_patch(expected)
        if name.endswith("lab_protocol_v8_1375.py"):
            text=expected.decode()
            if text.count(DISALLOWED_SAVE)!=1:raise ValueError("Expected unique positive save entry")
            text=text.replace(DISALLOWED_SAVE,"")
            text=text.replace("1375_test_fixture_v2","1375_test_fixture_v3")
            text=text.replace("Only the three audited disposable test saves are accepted",
                              "Only the two audited independent-NAV baseline saves are accepted")
            expected=text.encode()
        path=ROOT/destination
        if verify_only:
            if not path.is_file() or path.read_bytes()!=expected:
                raise ValueError("Unexpected v9 source difference: "+destination)
        else:
            if path.exists():raise ValueError("Refuse to overwrite existing v9 source: "+destination)
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(expected)
        mapped.append({"source":name,"destination":destination,"sha256":hashlib.sha256(expected).hexdigest().upper(),
                       "native_semantics_unchanged":name in old.SOURCES and not guarded})
    if frozen!={name:digest(ROOT/name) for name in frozen}:raise ValueError("Old frozen bytes changed")
    report={"scope":"offline_isolated_v9_build_sources","runtime_verified":False,
            "native_source_count":len(old.SOURCES),"frozen_file_count":len(frozen),
            "native_normalized_diff":"v8->v9 naming/paths and fixed fixture digest; only fixture cpp additionally receives pinned readonly NAV baseline guard",
            "native_baseline_guard_patch_sha256":BASELINE_PATCH_SHA,
            "python_additional_changes":["fixture profile id v2->v3","positive NAV-vassal save removed","two-baseline diagnostic"],
            "sources":mapped,"frozen_unchanged":not authorized_updates,"native_frozen_unchanged":True,
            "authorized_offline_reference_updates":authorized_updates,"candidate_profile_sha256":NEW_PROFILE}
    payload=(json.dumps(report,indent=2)+"\n").encode()
    out=HERE/"source-review.json"
    if args.check:
        if out.read_bytes()!=payload:raise ValueError("Review output differs")
    else:out.write_bytes(payload)
    print(json.dumps({"native_sources":len(old.SOURCES),"mapped_files":len(mapped),"frozen_files":len(frozen),
                      "check":args.check,"frozen_unchanged":not authorized_updates,"native_frozen_unchanged":True,
                      "authorized_offline_reference_updates":len(authorized_updates),"runtime_verified":False}))


if __name__=="__main__":main()
