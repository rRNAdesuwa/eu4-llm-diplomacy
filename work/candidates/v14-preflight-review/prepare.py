"""Record/check the isolated offline reviewer; no game access or native build."""
import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
DRAFT='work/verify_v13_preflight_1375.py'
DRAFT_SHA='3a437fb96ba0db42f91954fa93c2061624f971c2ccd0c8a4b8a925d6e76d036e'
FILES=('reviewer.py','test_reviewer.py','prepare.py','verify_tests.py','README.md','runtime-pins.json')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bounded(path):
    with Path(path).open('rb') as stream:raw=stream.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('Input budget exceeded')
    return raw
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def render():
    spec=importlib.util.spec_from_file_location('preflight_review_candidate',HERE/'reviewer.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    build=module.fixed_build()
    runtime=json.loads(bounded(HERE/'runtime-pins.json'))
    if runtime.get('ready') is not True or runtime.get('dll_sha256')!=module.DLL_SHA or runtime.get('build_manifest_sha256')!=module.BUILD_SHA:
        raise ValueError('Runtime pins have not been explicitly fixed to root build')
    old=bounded(ROOT/DRAFT)
    if sha(old)!=DRAFT_SHA:raise ValueError('Original paused v13 draft changed')
    old=old.decode().replace('v13','v14').replace('ROOT = Path(__file__).resolve().parents[1]','ROOT = Path(__file__).resolve().parents[3]')
    inputs={DRAFT:DRAFT_SHA,module.BUILD:module.BUILD_SHA,
        'work/runtime/native1375-v14/'+module.lab.DLL_NAME:module.DLL_SHA,**module.PINS}
    for section in ('source_sha256','host_source_sha256','support_source_sha256'):
        inputs.update({p:d.lower() for p,d in build[section].items()})
    # Bind the synthetic fixture implementation and its already-reviewed data inputs.
    fixture_root=ROOT/'work/candidates/v13-host-review'
    if sha(bounded(fixture_root/'input-pins.json'))!='6aebb6a2b7b3bf78797491e2e99388e3e9b92a78933d30d07aa45d6ed89db75c':raise ValueError('Fixture pins changed')
    old_review=json.loads(bounded(fixture_root/'review.json'))
    test=next(r for r in old_review['candidate_sources'] if r['path']=='test_candidate.py')
    inputs['work/candidates/v13-host-review/test_candidate.py']=test['sha256']
    for row in json.loads(bounded(fixture_root/'input-pins.json'))['inputs']:
        if row['role']=='offline_fixture_dependency':inputs[row['path']]=row['sha256']
    for path,digest in inputs.items():
        if sha(bounded(ROOT/path))!=digest:raise ValueError('Pinned dependency changed: '+path)
    sources=[]
    for name in FILES:
        raw=bounded(HERE/name)
        if name.endswith('.py'):ast.parse(raw)
        sources.append(dict(path=name,bytes=len(raw),sha256=sha(raw)))
    diff=''.join(difflib.unified_diff(old.splitlines(True),bounded(HERE/'reviewer.py').decode().splitlines(True),
        fromfile=DRAFT+' (version/path normalized)',tofile='work/candidates/v14-preflight-review/reviewer.py')).encode()
    review={'schema_version':1,'purpose':'v14_four_stage_offline_preflight_review_candidate','sources':sources,
        'input_pins':inputs,'input_count':len(inputs),'source_counts':{'native':20,'host':11,'support':8},
        'expected_session':module.EXPECTED_SESSION,
        'phase_case_counts':{'lifecycle':20,'owned_peace':1,'preview':72,'command':72},
        'diff_sha256':sha(diff),'original_v13_draft_unchanged':True,'actual_game_evidence_collected':False,
        'game_accessed':False,'native_build_performed':False,'production_execution_verified':False,
        'owned_peace_scope':'default_owned_object_lifecycle_only'}
    return {'candidate.diff':diff,'review.json':encoded(review)}
def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args(argv)
    outputs=render()
    for name,raw in outputs.items():
        p=HERE/name
        if args.check:
            if bounded(p)!=raw:raise ValueError('Candidate needs regeneration: '+name)
        else:p.write_bytes(raw)
    print(json.dumps(dict(check=args.check,review_sha256=sha(outputs['review.json']),game_accessed=False,built=False)))
    return 0
if __name__=='__main__':raise SystemExit(main())
