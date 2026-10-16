"""Prepare an isolated Python v13 host review; never materialize or access a process."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
NATIVE=ROOT/'work/candidates/v13-owned-peace-review'
INPUT_SHA='6aebb6a2b7b3bf78797491e2e99388e3e9b92a78933d30d07aa45d6ed89db75c'
NATIVE_SHA='ceaa1802a0230761ebaf27476c368377d59485cd275f7d8466da5052223a1ef7'
HOST_FILES=(
    'work/native/lab_protocol_v12_1375.py','work/native/inject_lab_v12_1375.py',
    'work/native/run_lab_speed_v12_1375.py','work/native/record_lab_v12_build.py',
    'tools/request_diplomacy_lab_v12.py','tools/verify_diplomacy_lifecycle_v12.py',
    'tools/verify_diplomacy_preview_v12.py','tools/verify_diplomacy_command_v12.py',
    'bridge/diplomacy_lab_http_v12.py','tools/serve_diplomacy_lab_v12.py')
NEW_OWNED='tools/verify_diplomacy_owned_peace_v13.py'
HOST_SOURCES=tuple(p.replace('v12','v13') for p in HOST_FILES)+(NEW_OWNED,)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def bounded(path):
    with Path(path).open('rb') as f:raw=f.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('Bounded source limit exceeded: '+str(path))
    return raw
def encoded(value):return (json.dumps(value,indent=2,ensure_ascii=False,sort_keys=True)+'\n').encode()
def replace(text,old,new,count=1):
    if text.count(old)!=count:raise ValueError(f'Expected {count} anchors, got {text.count(old)}: {old[:100]}')
    return text.replace(old,new)
def audit(root=ROOT):
    raw=bounded(HERE/'input-pins.json')
    if sha(raw)!=INPUT_SHA:raise ValueError('Input pins changed')
    pins=json.loads(raw)['inputs']
    for item in pins:
        path=Path(root)/item['path']
        if path.stat().st_size!=item['bytes'] or sha(bounded(path))!=item['sha256']:
            raise ValueError('Pinned frozen/native input changed: '+item['path'])
    if sha(bounded(Path(root)/'work/candidates/v13-owned-peace-review/review.json'))!=NATIVE_SHA:
        raise ValueError('Native v13 review changed')
    return pins

def protocol(text,pins):
    native=json.loads(bounded(NATIVE/'source-set.json'))['sources']
    expected_native={s['path']:s['sha256'].upper() for s in native}
    support={s['path']:s['sha256'].upper() for s in pins if s['role']=='shared_readonly_dependency'}
    start=text.index('\nSOURCES = ')+1;end=text.index('TEST_SAVES = ',start)
    definitions=('NATIVE_REVIEW_SHA256 = '+repr(NATIVE_SHA)+'\n'
        'EXPECTED_NATIVE_SOURCES = '+repr(expected_native)+'\nSOURCES = tuple(EXPECTED_NATIVE_SOURCES)\n'
        'HOST_SOURCES = '+repr(HOST_SOURCES)+'\nEXPECTED_SUPPORT_SOURCES = '+repr(support)+'\nSUPPORT_SOURCES = tuple(EXPECTED_SUPPORT_SOURCES)\n'
        "OWNED_PEACE_STAGE_CONTRACT = {'stages': ['lifecycle', 'owned_peace', 'preview', 'command'], 'counts': [20, 1, 72, 72], 'requires_following_health': True, 'owned_peace_send': False, 'world_generation_verified': False}\n"
        "PHASES = {\n    'lifecycle': ('pair-selftest.request','phase-lifecycle.claim',b'PAIR_SELFTEST_1375\\n'),\n"
        "    'owned_peace': ('owned-peace-lifecycle.request','phase-owned-peace-lifecycle.claim',None),\n"
        "    'preview': ('pair-preview.request','phase-preview.claim',b'PAIR_PREVIEW_1375\\n'),\n"
        "    'command': ('pair-command.request','phase-command.claim',b'PAIR_COMMAND_1375\\n'),\n}\n")
    text=text[:start]+definitions+text[end:]
    pos=text.index('def encode_request(')
    marker='''def phase_wire(phase, metadata):
    require(phase in PHASES, "Unknown explicit research phase")
    if phase != "owned_peace":
        return PHASES[phase][2]
    require(integer(metadata.get("pid"),1,2**32-1)
        and isinstance(metadata.get("process_creation_filetime"),str)
        and re.fullmatch(r"[0-9a-f]{16}",metadata["process_creation_filetime"])
        and int(metadata["process_creation_filetime"],16)>0,"Invalid owned-peace marker process identity")
    return (f"OWNED_PEACE_LIFECYCLE/1\\npurpose={PURPOSE}\\npid={metadata['pid']}\\n"
        f"creation={metadata['process_creation_filetime']}\\n").encode("ascii")


'''
    text=text[:pos]+marker+text[pos:]
    start=text.index('def record_build(');end=text.index('def verify_test_save(',start)
    text=text[:start]+bounded(HERE/'build_contract.py.inc').decode()+'\n'+text[end:]
    text=replace(text,'    from tools.verify_diplomacy_command_v13 import CommandSession',
        '    from tools.verify_diplomacy_command_v13 import CommandSession\n    from tools.verify_diplomacy_owned_peace_v13 import OwnedPeaceSession, OWNED_EVENTS')
    text=replace(text,'    validators, proofs, complete = {}, {}, set()',
        '    validators, proofs, complete = {}, {}, set()\n    owned = OwnedPeaceSession(metadata)\n    phase_started = set()')
    text=replace(text,'                installed = True',
        '                require(event.get("owned_peace_automatic") is False, "Owned-peace phase must have an explicit marker")\n                installed = True')
    text=replace(text,'                latest = event',
        '                owned.frame(event,line_number)\n                latest = event')
    anchor='            if name in ("lab_input_wait", "lab_input_failed"):'
    added='''            if name in OWNED_EVENTS:
                require(input_wait is None and last_sequence == 0 and not any(p in complete for p in ("preview","command")),
                    "Owned-peace invocation overlaps an input wait or later activity")
                require("lifecycle" in proofs, "Owned-peace requires proved lifecycle and following health")
                require(read_bounded(Path(session)/PHASES["owned_peace"][1],MAX_RECORD)==phase_wire("owned_peace",metadata),
                    "Owned-peace lacks its exact durable PID/creation marker claim")
                owned.accept(event,line_number,lifecycle_proved=True)
                phase_started.add("owned_peace")
                if name == "owned_peace_selftest_complete": complete.add("owned_peace")
                continue
            phase_begins={"pair_selftest_begin":"lifecycle","pair_preview_begin":"preview","pair_command_begin":"command"}
            if name in phase_begins:
                phase=phase_begins[name]
                order=tuple(PHASES)
                require(phase not in phase_started and all(p in proofs for p in order[:order.index(phase)]),
                    "Phase began twice or before all preceding four-stage proofs")
                require(read_bounded(Path(session)/PHASES[phase][1],MAX_RECORD)==phase_wire(phase,metadata),
                    "Phase began without its exact durable marker claim")
                phase_started.add(phase)
            if name == "research_frame" and "owned_peace" in complete and "owned_peace" not in proofs:
                proofs["owned_peace"]=owned.finish()
'''
    text=replace(text,anchor,added+anchor)
    text=replace(text,'read_bounded(Path(session) / PHASES[phase][1], MAX_RECORD) == PHASES[phase][2]',
        'read_bounded(Path(session) / PHASES[phase][1], MAX_RECORD) == phase_wire(phase, metadata)')
    text=replace(text,'                    validator.accept(event, line_number)',
        '                    validator.accept(event, line_number)\n'
        '                    errors = (validator.prior.error_count + validator.command.error_count) if phase == "command" else validator.error_count\n'
        '                    require(errors == 0, "Failed or malformed partial " + phase + " preflight; no retry")')
    text=replace(text,'    return {"latest_frame": latest, "phases": {name: name in proofs for name in PHASES}, "phase_proofs": proofs,',
        '    phase_attempted = {}\n    for phase, (_,claim,_) in PHASES.items():\n'
        '        paths = (Path(session)/claim, Path(session)/(claim+".host-intent"))\n'
        '        for path in paths: _no_links(path)\n'
        '        phase_attempted[phase] = phase in phase_started or any(path.exists() for path in paths)\n'
        '    return {"latest_frame": latest, "phases": {name: name in proofs for name in PHASES}, "phase_proofs": proofs,\n'
        '            "phase_attempted": phase_attempted,')
    text=replace(text,'    frame = evidence["latest_frame"]',
        '    require(isinstance(evidence.get("phases"),dict) and set(evidence["phases"])==set(PHASES)\n'
        '        and all(type(v) is bool for v in evidence["phases"].values()), "Missing exact four-phase diagnostics")\n'
        '    frame = evidence["latest_frame"]\n'
        '    require(type(frame.get("owned_peace_tested")) is bool and type(frame.get("owned_peace_passed")) is bool,\n'
        '        "Missing owned-peace frame diagnostics")')
    text=replace(text,'        index = order.index(phase)',
        '        require(phase in PHASES, "Unknown phase")\n        index = order.index(phase)\n'
        '        require(isinstance(evidence.get("phase_attempted"),dict) and set(evidence["phase_attempted"])==set(PHASES)\n'
        '            and evidence["phase_attempted"][phase] is False, "Phase already claimed, intended or started; no retry")')
    text=text.replace('Three detailed preflight phases','Four detailed preflight phases')
    text=replace(text,'        filename, claim, raw = PHASES[phase]',
        '        filename, claim, _ = PHASES[phase]\n        raw = phase_wire(phase, metadata)')
    return text

def lifecycle(text):
    text=replace(text,'scopes={"lifecycle":"lifecycle_only", "preview":"native_legality_preview", "command":"command_lifecycle_only"}',
        'scopes={"lifecycle":"lifecycle_only", "owned_peace":"default_owned_peace_lifecycle_only", "preview":"native_legality_preview", "command":"command_lifecycle_only"}')
    text=text.replace('v13 fourteen-source','v13 twenty-source')
    text=replace(text,'        if phase != "lifecycle":','        if phase in ("preview", "command"):')
    text=replace(text,'        comparisons={key:',
        '        if phase == "owned_peace":\n'
        '            require(proof["frame_identity"]["raw_date"] == initial["current_raw_date"]\n'
        '                and int(proof["frame_identity"]["player_handle"],16) == initial["player"]["handle"],\n'
        '                "Owned-peace frame identity/date differs from bounded snapshots")\n'
        '        comparisons={key:')
    return text

def read_session_adapter(text,phase):
    start=text.index('def read_session(')
    tree=ast.parse(text);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read_session')
    lines=text.splitlines(True);end=sum(map(len,lines[:node.end_lineno]))
    new='''def read_session(path: Path, pid: int):
    """v13 requires its sibling metadata and permanent phase claims, even offline."""
    from work.native import lab_protocol_v13_1375 as lab
    path=Path(path)
    require(path.name=="research-1375.jsonl","Use the exact private v13 session log")
    raw=lab.decode_json(lab.read_bounded(path.parent/"session.json",4096).decode())
    metadata=lab.read_session_metadata(path.parent,pid,raw.get("process_creation_filetime"))
    evidence=lab.read_evidence(path.parent,metadata)
    proof=evidence["phase_proofs"].get(PHASE)
    require(proof is not None and proof["passed"] is True,"Missing complete v13 phase proof")
    return proof,{"name":path.name,"size_bytes":evidence["log_bytes"],"sha256":evidence["log_sha256"],
        "read_kind":"fixed_size_log_snapshot_with_private_metadata_and_claims"}
'''.replace('PHASE',repr(phase))
    return text[:start]+new+text[end:]

def outputs():
    pins=audit();files={};diff=[];origins={}
    for path in HOST_FILES:
        raw=bounded(ROOT/path);old=raw.decode().replace('\r\n','\n')
        text=old.replace('v12','v13').replace('V12','V13').replace('8769','8770')
        if path.endswith('lab_protocol_v12_1375.py'):text=protocol(text,pins)
        if path.endswith('inject_lab_v12_1375.py'):
            text=replace(text,'parser.add_argument("--creation", help="Optional exact 16-lower-hex process creation identity")',
                'parser.add_argument("--creation", required=True, help="Exact 16-lower-hex process creation identity")')
            text=replace(text,'"selftest_automatic": False, "preview_automatic": False, "command_automatic": False,',
                '"selftest_automatic": False, "owned_peace_automatic": False, "preview_automatic": False, "command_automatic": False,')
        if path.endswith('verify_diplomacy_lifecycle_v12.py'):text=lifecycle(text)
        for phase in ('lifecycle','preview','command'):
            if path.endswith('verify_diplomacy_'+phase+'_v12.py'):text=read_session_adapter(text,phase)
        if path.endswith('diplomacy_lab_http_v12.py'):
            text=replace(text,'        value["input_wait_pending"] = snapshot["evidence"].get("input_wait_pending", False)',
                '        value["input_wait_pending"] = snapshot["evidence"].get("input_wait_pending", False)\n'
                '        value["phase_attempted"] = deepcopy(snapshot["evidence"].get("phase_attempted", {}))')
            text=replace(text,'        value["v13_candidate"] = ',
                '        value["required_native_stages"] = deepcopy(lab.OWNED_PEACE_STAGE_CONTRACT)\n        value["v13_candidate"] = ')
        destination=path.replace('v12','v13');files[destination]=text.encode();origins[destination]=path
        diff.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile=path,tofile=destination))
    files[NEW_OWNED]=bounded(HERE/'owned_verifier.py');origins[NEW_OWNED]='new independent owned-peace validator'
    diff.extend(difflib.unified_diff([],files[NEW_OWNED].decode().splitlines(True),fromfile='/dev/null',tofile=NEW_OWNED))
    for item in pins:
        if item['role']=='frozen_fixture_source':
            name=item['path'].replace('fixture-v12','fixture-v13');files[name]=bounded(ROOT/item['path']);origins[name]=item['path']
    for name,raw in files.items():
        if name.endswith('.py'):ast.parse(raw,filename=name)
    result={'generated/'+name:raw for name,raw in files.items()}
    result['candidate.diff']=''.join(diff).encode()
    result['new-files.json']=encoded({'schema_version':1,'purpose':'restricted_pair_lab_1375_v13',
        'python_sources':list(HOST_SOURCES),'python_source_count':len(HOST_SOURCES),'native_sources_generated':False,
        'files':[{'path':name,'bytes':len(raw),'sha256':sha(raw),'origin':origins[name]} for name,raw in sorted(files.items())]})
    review={'schema_version':1,'purpose':'isolated_v13_host_review','native_review_sha256':NATIVE_SHA,
        'input_pins_sha256':INPUT_SHA,'input_count':len(pins),'python_source_count':11,'fixture_copy_count':5,
        'candidate_sources':[{'path':name,'sha256':sha(bounded(HERE/name))} for name in
            ('prepare.py','input-pins.json','owned_verifier.py','build_contract.py.inc','test_candidate.py','verify_tests.py','README.md')],
        'outputs':[{'path':name,'sha256':sha(raw),'bytes':len(raw)} for name,raw in sorted(result.items())],
        'formal_build_performed':False,'materialized':False,'game_accessed':False,'runtime_verified':False,'execution_verified':False,
        'root_merge_required':['Materialize these 11 host files and 5 byte-identical fixture files only after independent review.',
            'Native build script already calls record_lab_v13_build.py; no native candidate edit is required.',
            'New manifest schema 2: 20 native sources, 11 host sources, 8 pinned shared support sources, native review SHA and four-stage contract.',
            'Shared API, capabilities, frozen v12 and native v13 candidate are not modified.']}
    result['review.json']=encoded(review);audit();return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    expected=outputs()
    for name,raw in expected.items():
        path=HERE/name
        if args.check:
            if not path.is_file() or bounded(path)!=raw:raise ValueError('Stale isolated host candidate: '+name)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    actual={p.relative_to(HERE).as_posix() for p in (HERE/'generated').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if actual!={p for p in expected if p.startswith('generated/')}:raise ValueError('Unexpected generated source')
    print(json.dumps({'checked':args.check,'review_sha256':sha(expected['review.json']),'inputs':len(audit()),'python_sources':11,'fixture_copies':5,
        'native_sources_modified':False,'game_accessed':False,'materialized':False}));return 0

if __name__=='__main__':raise SystemExit(main())
