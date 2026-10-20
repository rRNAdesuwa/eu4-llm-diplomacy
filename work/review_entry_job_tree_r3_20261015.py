"""Source and pure-fake review; never executes a CLI or any job WinAPI."""
import argparse
import ctypes
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/frida-entry-job-review-20261015-r1'
HERE=ROOT/'work/candidates/frida-entry-observer-1375-v1'
DIAG=ROOT/'work/reports/war-peace-api-20261015-r11-job-diagnostic'

def pin(path):
    raw=path.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def load(path):return json.loads(path.read_bytes())
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value
def check():
    graph=load(OUT/'manifest.json')['source_pins']
    for name,wanted in graph.items():assert pin(ROOT/name)==wanted,name
    print(json.dumps(dict(status='pass',pins=len(graph),real_children_started=0,game_accessed=False)))

def main():
    required={
        HERE/'job_tree.py':(8615,'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'),
        HERE/'test_job_tree.py':(3188,'21a4975f33f1a35ab58a48712f6631c3f6a58b04ef318b6b7d118ed6db7ef76a'),
        OUT/'boundary-counterexamples-r2.json':(3702,'93ebd01ac96bd5c5dff19b171111eb7c571d9d40177283cb5b650e65d5c56494'),
    }
    pins={}
    def fixed(path,wanted=None):
        value=pin(path)
        if wanted is not None:assert value==wanted,path
        pins[path.relative_to(ROOT).as_posix()]=value
    for path,(size,sha) in required.items():fixed(path,dict(bytes=size,sha256=sha))
    probe=module(ROOT/'work/probe_job_tree_boundaries_offline_20261015.py','review_pure_job_probe')
    current=module(HERE/'job_tree.py','review_job_r3')
    cases=dict(normal=probe.probe(current),fast_oversize=probe.probe(current,output_bytes=2*1024*1024+1),
        query_failure=probe.probe(current,query_failure=True))
    assert cases['normal']['helper_result']['error'] is None
    assert cases['fast_oversize']['helper_result']['error']['type']=='RuntimeError'
    assert cases['query_failure']['helper_result'] is None and cases['query_failure']['exception']
    for value in cases.values():
        assert value['source_enforced_active_cap'] is True
        assert value['explicit_child_handle_closes']==value['job_closes']==1
        order=value['events']
        assert order.index('limits_set')<order.index('spawn_suspended')<order.index('assigned')<order.index('resumed')
    assert cases['query_failure']['events'][-2:]==['child_handle_close','job_closed']
    assert (ctypes.sizeof(current.BasicLimit),ctypes.sizeof(current.Extended),ctypes.sizeof(current.Accounting))==(64,144,48)
    prior=load(OUT/'boundary-counterexamples-r2.json')
    assert prior['cases']['new_query_failure']['explicit_child_handle_closes']==0
    for directory in ('reviewed-preimage','reviewed-r2-preimage'):
        for path in (OUT/directory).iterdir():
            if path.is_file():fixed(path)
    r2path=OUT/'reviewed-r2-preimage/job_tree.py'
    source_diff=''.join(difflib.unified_diff(r2path.read_text().splitlines(True),(HERE/'job_tree.py').read_text().splitlines(True),
        fromfile='df2eee-r2-preimage',tofile='5fca5b-r3'))
    for name in ('job-tests-r2.json','job-tests-r2.log','job-r3-normal.json','receipt.json',
        'first-test-preimage/receipt.json','first-test-preimage/job_tree.py','first-test-preimage/test_job_tree.py',
        'immediate/receipt.json','immediate/stdout.txt','immediate/stderr.txt'):
        fixed(DIAG/name)
    r2=load(DIAG/'job-tests-r2.json');r3=load(DIAG/'job-r3-normal.json')
    assert pin(DIAG/'job-tests-r2.json')['sha256']=='e36af3eab9c8d74827cd98eedc9ae671e0a4d60c4386f3b3213d76622b9c2530'
    assert pin(DIAG/'job-r3-normal.json')['sha256']=='adba7314a9cf49a229d1d7bcc841fc32e4f837930cf2995d19ba4cb4c455586f'
    assert r2['passed'] and r2['tests']==5 and r3['passed'] and r3['tests']==1
    # Old test source pins refer to the independently preserved r2, not current r3.
    assert r2['source_pins'][(HERE/'job_tree.py').relative_to(ROOT).as_posix()]==pin(r2path)
    assert r3['source_pins'][(HERE/'job_tree.py').relative_to(ROOT).as_posix()]==pin(HERE/'job_tree.py')
    first=load(DIAG/'first-test-preimage/receipt.json');immediate=load(DIAG/'immediate/receipt.json')
    assert (first['first_tests_passed'],first['first_tests_failed'],first['first_tests_error'])==(1,1,1)
    assert immediate['actual_child_wait_state']==0 and immediate['job_active_processes_final']==0
    # Reuse the immediately preceding stable98/native44 file verification graph.
    previous=ROOT/'work/reports/relation-request-cli-postseal-review-20261015-r1/manifest.json'
    fixed(previous)
    for name,wanted in load(previous)['source_pins'].items():fixed(ROOT/name,wanted)
    for path in (Path(__file__),Path(probe.__file__)):fixed(path)
    report=dict(schema='EU4-ENTRY-JOB-TREE-INDEPENDENT-SOURCE-REVIEW/1',
        status='ready_at_reviewed_r3_source_pins',findings=[],
        adopted_source=dict(path=(HERE/'job_tree.py').relative_to(ROOT).as_posix(),**pin(HERE/'job_tree.py')),
        resolved_findings=[
            dict(priority=2,kind='missing_active_process_hard_limit',original='5f716a5e',fixed='df2eee0f',
                proof='old flags0x2300/ActiveProcessLimit0; new flags0x2308/ActiveProcessLimit8 before child startup'),
            dict(priority=2,kind='fast_exit_bypassed_final_output_bound',original='5f716a5e',fixed='df2eee0f',
                proof='Pure fake2097153B exited child accepted in r1; r2/r3 retain explicit final-output RuntimeError'),
            dict(priority=3,kind='query_failure_skipped_explicit_child_handle_close',original='df2eee0f',fixed='5fca5b41',
                proof='Repeated QueryInformationJobObject failure: r2 jobclose1/childclose0; r3 bothclose1 with exception preserved'),
        ],r3_narrow_diff=source_diff,pure_fake_cases=cases,
        Windows_layout_sizes=dict(BasicLimit=64,Extended=144,Accounting=48),
        source_guards=[
            'Only exact newly created Popen handle assigned; CREATE_SUSPENDED before assign, resume only after limits and assignment',
            'Unnamed own job, process+job768MiB maximum, hard concurrent8, cumulative>8 refusal, KILL_ON_JOB_CLOSE',
            'No inherited target PID enumeration or existing-game assignment; arbitrary argv is trusted reviewed-caller input, not a public untrusted service',
            'Per-stream2MiB acceptance check during loop and after wait; overshoot can occur before refusal, not a disk-write hard cap',
            'Normal parent completion with remaining descendants triggers own-job termination; direct child wait and active-member accounting remain separate',
            'Final statistics failure still closes direct process handle and outer job handle; failure never proves active0',
        ],
        historical_tests=dict(initial=dict(passed=1,failed=1,error=1,preserved=True),
            r2_own_child_tests=5,r3_normal_own_child_tests=1,independently_reexecuted=False,
            original_timeout_child_WaitForSingleObject_zero_retained=True),
        limitations=[
            'This review invoked no real child/WinAPI, Frida, REA, game or native entry; own-child receipts are retained parent evidence',
            'Hostcapture_once/FridaJS/attachment/detach and target memory cleanup are outside this source scope',
            'Caller must require errorNone, acceptable exit code, job_active_processes_final0 and valid source graph before treating a CLI run as clean',
            'Main polling deadline45s is separate from bounded child wait/cleanup and OS setup calls; not a hard whole-function interrupt',
            'Cumulative8 is retrospective refusal; active8 and memory limits are OS enforced; output can exceed its acceptance threshold before polling/refusal',
            'No claim that job limits govern an injected agent in an existing target; target_cleanup_proven_by_job remains false',
            'CloseHandle API return is not recorded; query/cleanup errors propagate without fabricating an all-members-zero receipt',
            'First audit producer attempt tried hashing generated __pycache__ as a file; corrected file-only enumeration before writing receipt, no helper failure',
            'Previously denied old Ctemp log deletion was not retried; only fresh pure-fake TemporaryDirectory files were created and removed'],
        real_children_started=0,job_WinAPI_called=False,game_accessed=False,Frida_called=False,native_game_calls=0,
        new_API_effects=0,native_ready=False)
    output=OUT/'independent-r3-source-ready.json'
    with output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    fixed(output)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-REVIEW-MANIFEST/1',source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],report=pin(output),pins=len(pins),real_children_started=0,game_accessed=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true')
    if p.parse_args().check:check()
    else:main()
