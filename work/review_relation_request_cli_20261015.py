"""Offline CLI source/boundary review. No runner, process or native access."""
import argparse
import copy
import difflib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
CAND=ROOT/'work/candidates/relation-request-observer-20261015'
OUT=ROOT/'work/reports/relation-request-cli-review-20261015-r1'
PRE=OUT/'reviewed-preimage'
COUNTER=ROOT/'work/reports/war-peace-api-20261015-r10-checkpoint/cli-pending-scalar-boundary-r1.json'

def pin(path):
    raw=path.read_bytes()
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def check():
    data=json.loads((OUT/'manifest.json').read_bytes())
    for name,wanted in data['source_pins'].items():assert pin(ROOT/name)==wanted,name
    print(json.dumps(dict(status='pass',pins=len(data['source_pins']),process_accessed=False)))

def waiting(native_id):
    identity=dict(pid=77,creation='0000000000000001',session='1'*32,dll_sha256='2'*64,
        manifest_sha256='d4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a')
    actor=dict(tag='ORL',handle='0x1000001004c524f')
    recipient=dict(tag='FRA',handle='0x100000200415246')
    row=dict(state_raw=0,state_label='pending_observed',native_request_id=native_id,
        token=0x3021,value_raw=1,actor_handle=actor['handle'],original_actor_handle=actor['handle'],
        recipient_handle=recipient['handle'])
    return dict(request_id='original-1',identity=identity,
        command=dict(request_id='original-1',action='ask_for_march',actor='ORL',target='FRA'),
        transport_state='dispatched',request_state='waiting_for_recipient',
        effect=dict(status='not_observed',selected_effect_verified=False),
        reply=dict(status='sampled_equal',request_state='waiting_for_recipient',native_request_id=native_id,
            selected=dict(identity=copy.deepcopy(identity),actor=actor,recipient=recipient,
                pending=dict(count=1,iteration=0,selected_matches=[row]))))

def main():
    expected={
        CAND/'relation_request_cli.py':(18008,'cfd3f2459b25bd23449df574b6313cd01ad628aec4dca0d6035cae73b92f9f55'),
        CAND/'test_relation_request_cli.py':(19646,'270fa1dd1cf6f9a5a9031d13cbc8b6189c392ff188a1f438e72296991bf3fc06'),
        CAND/'relation_request_observer.py':(28553,'4bdd6e6454a17d9277885f905559036c3929e39173b9543f172cbaeea7debceb'),
        CAND/'test_relation_request_observer.py':(27042,'200886630b51c05d0b20009acac1fbafd5deb51a5153bb7fd6d80e2e4e69eb86'),
        PRE/'relation_request_cli.py':(17848,'9c23bbc9a182709600df1cb03317d72bc3b6d17b8c2a3e973393a75f07f61f95'),
        COUNTER:(989,'0d2d1496abb36298836045f22eaacc47412ee02ff15cc265e7e199668ef8b7c0'),
    }
    for path,(size,sha) in expected.items():assert pin(path)==dict(bytes=size,sha256=sha),path
    old=load(PRE/'relation_request_cli.py','review_old_cli')
    tests=load(CAND/'test_relation_request_cli.py','review_new_cli_tests')
    cli=tests.c
    assert not cli.MANIFEST.exists(),'Review does not authenticate a future seal'
    rows=[]
    for version,module in [('preimage9c23',old),('patchedcfd3',cli)]:
        for scalar in (19,-1,-2**31,2**31-1,2**31,-2**31-1,2**40,-2**40,0,True,19.0):
            value=waiting(scalar)
            result=module.result_code(value)
            is_valid=type(scalar) is int and -2**31<=scalar<2**31 and scalar!=0
            wanted=3 if (is_valid or (version=='preimage9c23' and type(scalar) is int and scalar!=0)) else 2
            assert result==wanted,(version,scalar,result)
            rows.append(dict(version=version,native_request_id=scalar,scalar_type=type(scalar).__name__,
                proven_waiting=module.proven_waiting(value),exit_code=result))
    mismatches=[]
    for row_id,reply_id in ((19,-1),(-1,19),(19,2**40),(2**40,19)):
        value=waiting(row_id);value['reply']['native_request_id']=reply_id
        assert cli.result_code(value)==2
        mismatches.append(dict(row_id=row_id,reply_id=reply_id,exit_code=2))
    # Source/authentication and lifecycle boundaries with the author's pure mock
    # observer, while verifying real frozen files in a temporary sealed graph.
    tests.CLITests.setUpClass()
    api=[]
    for scenario in ('missing_manifest','post_observe_source_change','session_change','constant_clock_watch','strict_effect_bool'):
        case=tests.CLITests('test_absent_manifest_rejects_before_candidate_import');case.setUp()
        try:
            if scenario=='missing_manifest':
                code,out=case.run_cli(manifest=case.path/'missing.json')
                assert code==2 and not case.loads and not case.calls
            elif scenario=='post_observe_source_change':
                case.values=[case.value(observed=True)]
                def change():
                    case.manifest['sealed']=False;case.write_manifest()
                case.after=change
                code,out=case.run_cli()
                assert code==2 and len(case.calls)==1 and out[-1]['status']=='unknown'
                assert out[-1]['selected_effect_verified'] is False
            elif scenario=='session_change':
                case.values=[case.value(observed=True)]
                case.after=lambda:case.session.write_text('{}')
                code,out=case.run_cli()
                assert code==2 and len(case.calls)==1 and out[-1]['status']=='unknown'
            elif scenario=='constant_clock_watch':
                case.sleep=lambda seconds:case.sleeps.append(seconds)
                code,out=case.run_cli('watch','--compact','--max-samples','3','--duration-seconds','30')
                assert code==2 and len(case.calls)==3 and len(case.sleeps)==2
                assert out[-1]['watch_bound_reached'] is True
            else:
                value=case.value(observed=True);value['effect']['selected_effect_verified']=1
                case.values=[value]
                code,out=case.run_cli()
                assert code==2 and len(case.calls)==1
            assert all(row.get('automatic_command_retry') is False for row in out)
            api.append(dict(case=scenario,exit_code=code,observer_calls=len(case.calls),
                candidate_loader_calls=len(case.loads),automatic_command_retry=False,
                temporary_sealed_graph_only=True))
        finally:case.doCleanups()
    # Direct default entry still refuses unsealed deployment, before module load.
    output=io.StringIO();called=[]
    code=cli.main(['catalog'],_loader=lambda initial:called.append(initial),_output=output)
    assert code==2 and not called and json.loads(output.getvalue())['status']=='unknown'
    new_raw=(CAND/'relation_request_cli.py').read_text().splitlines(True)
    old_raw=(PRE/'relation_request_cli.py').read_text().splitlines(True)
    diff=''.join(difflib.unified_diff(old_raw,new_raw,fromfile='9c23-preimage',tofile='cfd3-patched'))
    assert diff.count('@@')==2
    report=dict(schema='EU4-RELATION-REQUEST-CLI-INDEPENDENT-SOURCE-REVIEW/1',
        status='ready_for_candidate_seal_at_reviewed_pins',findings=[],
        scope='Offline CLI/API source review and targeted pure fake boundaries; no future manifest or runtime authentication',
        fixed_original_finding=dict(priority=3,kind='signed32_pending_native_request_id_bound',
            original_sha256=expected[PRE/'relation_request_cli.py'][1],fixed_sha256=expected[CAND/'relation_request_cli.py'][1],
            frozen_decoder='bridge/diplomacy_reply_observer.py:77 struct.unpack_from(<i, raw,0x3c)',
            legitimate_negative_ids_preserved=True,no_native_authorization_bypass=True),
        narrow_source_diff=diff,scalar_cases=rows,projection_mismatch_cases=mismatches,targeted_API_cases=api,
        default_unsealed_entry=dict(exit_code=2,candidate_imported=False),
        author_test_receipts=dict(original37='cli-test-run.json under9c23 preimage; not independently rerun',
            waiting_delta6='waiting-delta-run.json undercfd3; not independently rerun'),
        source_boundaries=[
            'Fixed production manifest path, standard-library bounded and duplicate-key-safe parsing before candidate imports',
            'Self/test/docs/module pins plus all fixed frozen manifest closures/default44+DLL; POSIX normalized project-local paths',
            'Compile exact rehashed candidate source bytes, post-import closure and repeated manifest/source guards',
            'Original installed session required for prepare/status/watch; fresh baseline remains separate from request publication',
            'Session/command/request identity checked around observer; post-source/session change produces unknown even when fake effect reported observed',
            'check/catalog/prepare management exit0 cannot assert action completion; status/watch effect exit0 requires strict boolean observed/dispatched',
            'Waiting exit3 only unique typed state0 ask_for_march with matching signed32 native ID; unknown or not_observed otherwise exit2, no retry',
            'Watch sample bound terminates even with constant clock; all work remains read-only or local baseline/journal writes',
        ],
        limitations=[
            'No candidate manifest sealed or tested; default deployed entry remains unknown/2 until root installs an independently reviewed graph',
            'Pinned observer output contract supplies typed full handles and source-authenticated snapshots; CLI helper is not a generic validator for arbitrary forged dictionaries',
            'No current hook/process authentication, atomic/world-epoch proof, exact external request causality, AI acceptance or persistence',
            'Single bounded capture may pass watch deadline; polling deadline is not OS-read cancellation',
            'No full37/6 test replay, game sample, request dispatch or native call; old receipts remain associated with exact preimage sources',
        ],process_accessed=False,native_calls=0,requests_published=0,new_API_effects=0,native_ready=False)
    pins=tests.CLITests.graph.copy()
    for path in [*expected,CAND/'CLI.md',CAND/'README.md',CAND/'cli-test-run.json',CAND/'cli-test-run.log',
        CAND/'waiting-delta-run.json',CAND/'waiting-delta-run.log',
        ROOT/'work/reports/relation-request-observer-review-20261015-r1/independent-source-ready.json',
        ROOT/'work/reports/relation-request-observer-review-20261015-r1/manifest.json',Path(__file__),
        *PRE.iterdir()]:
        if path.is_file():pins[path.relative_to(ROOT).as_posix()]=pin(path)
    path=OUT/'independent-source-ready.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    pins[path.relative_to(ROOT).as_posix()]=pin(path)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],scalar_cases=len(rows),projection_mismatches=len(mismatches),
        API_cases=len(api),pins=len(pins),report=pin(path),process_accessed=False)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    if parser.parse_args().check:check()
    else:main()
