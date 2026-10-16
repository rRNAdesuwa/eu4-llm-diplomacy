"""File-only postseal replay. Does not run CLI operations or touch processes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CAND=ROOT/'work/candidates/relation-request-observer-20261015'
OUT=ROOT/'work/reports/relation-request-cli-postseal-review-20261015-r1'
BASE=ROOT/'work/reports/war-peace-api-20261015-r10-checkpoint'

def pin(path):
    raw=path.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def load(path):return json.loads(path.read_bytes())

def check():
    graph=load(OUT/'manifest.json')['source_pins']
    for name,wanted in graph.items():assert pin(ROOT/name)==wanted,name
    print(json.dumps(dict(status='pass',pins=len(graph),process_accessed=False)))

def main():
    manifest=CAND/'candidate-cli-manifest.json'
    assert pin(manifest)==dict(bytes=24443,sha256='103c3b69f3c2f5d2bc69356ffaab06e1039d1c0dd3d5a876e38fd3232abe06ea')
    source=CAND/'relation_request_cli.py'
    assert pin(source)==dict(bytes=18008,sha256='cfd3f2459b25bd23449df574b6313cd01ad628aec4dca0d6035cae73b92f9f55')
    spec=importlib.util.spec_from_file_location('review_postseal_cli',source)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    verified=cli.verify_manifest() # standard library graph verification; no candidate import
    assert len(verified['source_pins'])==125
    pins=verified['source_pins'].copy()
    pins[manifest.relative_to(ROOT).as_posix()]=pin(manifest)
    path=BASE/'relation-cli-sealed-verification.json'
    assert pin(path)==dict(bytes=2222,sha256='d90d0ca5d878650d01829043f5f44e5a282267f502cd83bcb0234c4b66dee8d1')
    actual=load(path);pins[path.relative_to(ROOT).as_posix()]=pin(path)
    assert actual['manifest_sha256']==verified['manifest_sha256'] and actual['source_pins']==125
    cases=[]
    for row in actual['cases']:
        for role in ('stdout','stderr'):
            item=row[role];p=ROOT/item['path'];wanted={k:item[k] for k in ('bytes','sha256')}
            assert pin(p)==wanted;pins[item['path']]=wanted
        assert row['stderr']['bytes']==0
        value=load(ROOT/row['stdout']['path'])
        assert value['selected_effect_verified'] is False and value['native_calls']==0
        assert value['requests_published']==0 and value['automatic_command_retry'] is False
        assert value['status']==row['status']
        if row['case']=='check':
            assert row['exit_code']==0 and value['source_pins']==125 and value['operation']=='check'
        elif row['case']=='catalog':
            assert row['exit_code']==0 and value['operation']=='catalog'
            actions=[profile['action'] for profile in value['catalog']['profiles']]
            assert len(actions)==len(set(actions))==18
            assert {'offer_alliance','royal_marriage','guarantee'}<=set(actions)
            assert value['catalog']['native_calls']==0
        else:
            assert row['case']=='current-nonce-refusal' and row['exit_code']==2
            assert value['operation']=='status' and value['completion_state']=='evidence_insufficient'
            assert value['error']==dict(type='ValueError',message='A current-query nonce is not an installed session')
        cases.append(dict(case=row['case'],exit_code=row['exit_code'],status=value['status'],
            selected_effect_verified=False,profile_count=row['profile_count']))
    stable=ROOT/'bridge/eu4_observer_manifest_1375.json'
    assert pin(stable)['sha256']=='23c6831a861425c5f3012b583c93c6c1ccf7d10c769f9a23389474d389c9b361'
    stable_data=load(stable);assert len(stable_data['source_pins'])==4
    pins[stable.relative_to(ROOT).as_posix()]=pin(stable)
    for name,wanted in stable_data['source_pins'].items():assert pin(ROOT/name)==wanted;pins[name]=wanted
    public_path=ROOT/'tools/eu4_observer.py'
    public_spec=importlib.util.spec_from_file_location('review_stable_public_graph',public_path)
    public=importlib.util.module_from_spec(public_spec);public_spec.loader.exec_module(public)
    stable_graph=public.source_pins() # file-only recursive closure; not main()
    assert len(stable_graph)==98
    for name,wanted in stable_graph.items():assert pin(ROOT/name)==wanted;pins[name]=wanted
    native=ROOT/cli.NATIVE;data=load(native)
    assert pin(native)['sha256']==cli.NATIVE_SHA and len(data['source_pins'])==44
    assert actual['process_opened'] is False and actual['native_calls']==0
    assert actual['requests_published']==actual['new_API_effects_verified']==0
    source_text=source.read_text()
    nonce=source_text.index("'A current-query nonce is not an installed session'")
    assert nonce<source_text.index('identity = module.validate_identity(session[\'identity\'])')
    assert nonce<source_text.index('observer = module.RelationRequestObserver(')
    report=dict(schema='EU4-RELATION-CLI-INDEPENDENT-POSTSEAL-REVIEW/1',status='pass',findings=[],
        reviewed_manifest=dict(path=manifest.relative_to(ROOT).as_posix(),**pin(manifest),pins=125),
        source_byte_identity=dict(cli_cfd3_unchanged=True,module_4bdd_unchanged=True),
        actual_output_replay=cases,stable_manifest98_unchanged=True,native_manifest44_and_DLL_unchanged=True,
        nonce_refusal_boundary='Candidate module is imported earlier, but the current-only nonce marker is rejected before validate_identity, observer construction or process capture',
        evidence_limits=[
            'Only retained output bytes and pinned code paths replayed; no check/catalog/status child reexecuted',
            'Original argv/current-nonce input path and OS child-handle telemetry are not in this receipt; collection/process-open booleans remain parent-producer assertions',
            'Catalog18 is candidate-only capability metadata; stable public98 and native120 registry are unchanged',
            'First auditor assertion mistook four direct public manifest entries for its98-entry recursive closure; corrected before writing this artifact, no candidate/producer failure',
            'No new request baseline, API effect, AI acceptance, callback authentication, persistence or native readiness'],
        process_accessed=False,native_calls=0,requests_published=0,new_API_effects=0,native_ready=False)
    OUT.mkdir(exist_ok=False)
    output=OUT/'independent-file-audit.json'
    with output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    for p in (output,Path(__file__)):pins[p.relative_to(ROOT).as_posix()]=pin(p)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='pass',report=pin(output),pins=len(pins),process_accessed=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true')
    if p.parse_args().check:check()
    else:main()
