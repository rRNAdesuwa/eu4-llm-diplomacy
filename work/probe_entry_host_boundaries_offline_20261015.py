"""Minimal file/fake host counterexamples. No process, REA or Frida call."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/frida-entry-host-review-20261015-r1'
HERE=ROOT/'work/candidates/frida-entry-observer-1375-v1'

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value
def pin(path):
    raw=path.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def encoding_cases(host):
    rows=[]
    for codec in ('utf-8','utf-16','utf-32','utf-8-sig'):
        try:host.strict_json('{"x":1}'.encode(codec));accepted=True;error=None
        except (ValueError,UnicodeError) as exc:accepted=False;error=type(exc).__name__+': '+str(exc)
        rows.append(dict(encoding=codec,accepted=accepted,error=error))
    return rows

def close_case(host):
    events=[]
    class Held:
        def identity_check(self):events.append('identity')
    class Cap:
        base=0x7ff7034b0000;held=Held();modules=[];initial_pins={};exits=0
        def __enter__(self):events.append('held_enter');return self
        def __exit__(self,*_):
            self.exits+=1;events.append('held_exit_error');raise OSError('purefake held close failure')
    cap=Cap()
    class Reader:
        def __init__(self,_):pass
        def read(self,address,size):
            assert (address,size)==(cap.base+host.ENTRY_RVA,32)
            events.append('independent_prefix');return host.PREFIX
    backend=types.SimpleNamespace(manifest={'dll':{'sha256':'1'*64}},manifest_sha='2'*64)
    observer=types.SimpleNamespace(TagCommandBackend=lambda:backend,RuntimeCapture=lambda *_:cap,
        BudgetReader=Reader,HeldRPMPort=lambda held:held,pins=lambda:{})
    parser=types.SimpleNamespace(evaluate=lambda *_:{'status':'structural_match'})
    def run(argv,cwd,out,err):
        events.append('fake_cli');Path(out).write_bytes(b'{}');Path(err).write_bytes(b'')
        return dict(error=None,exit_code=0,direct_child_collected=True,job_active_processes_final=0,
            existing_target_game_assigned_to_job=False,target_cleanup_proven_by_job=False)
    jobs=types.SimpleNamespace(run_cli_tree=run)
    def local(name,_):
        return parser if name.endswith('entry_observation_parser.py') else jobs if name.endswith('job_tree.py') else observer
    def sample(*_):events.append('world_sample');return {'world':'same'}
    initial={'manifest_sha256':'1'*64,'source_pins':{host.REL+'/entry_observer.js':host.pin(HERE/'entry_observer.js')}}
    with tempfile.TemporaryDirectory(dir=OUT,prefix='purefake-host-close-') as tmp:
        with patch.object(host,'OUT',Path(tmp)),patch.object(host,'verify_manifest',return_value=initial), \
             patch.object(host,'load_local',side_effect=local),patch.object(host,'host_sample',side_effect=sample), \
             patch.object(host,'registered_argv',return_value=['never-executed']), \
             patch.object(host,'extract_evidence',return_value=({'evidence_id':'ev_'+'f'*64},{'temporary_code_hook':True})):
            result=host.capture(initial)
        return dict(status=result['status'],errors=result['errors'],
            selected_cleanup_checks_passed=result['selected_cleanup_checks_passed'],
            code_restore_verified=result['code_restore_verified'],context_exit_calls=cap.exits,
            main_status_implied_exit_code=0 if result['status']=='structural_match' else 2,
            claim_exists_before_temp_cleanup=(Path(tmp)/'claim.json').exists(),events=events)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
    source=OUT/'reviewed-r3-preimage/capture_once.py'
    assert pin(source)['sha256']=='8dee2f61a658bb032f2d426d6a40182fae859c351f4f36807754030cb4f94cb8'
    old=load(source,'replay_host_r3_preimage')
    record=dict(schema='EU4-ENTRY-HOST-INDEPENDENT-ENCODING-CLOSE-COUNTEREXAMPLES/2',
        source=pin(source),encoding_cases=encoding_cases(old),held_exit_failure=close_case(old),
        corrects='encoding-close-counterexamples-r3.json: claim was measured after TemporaryDirectory removal; corrected before cleanup here. No candidate claim defect.',
        real_children_started=0,REA_invoked=False,Frida_loaded=False,game_accessed=False,
        producer=pin(Path(__file__)))
    assert record['held_exit_failure']['claim_exists_before_temp_cleanup'] is True
    if args.record:
        path=OUT/'encoding-close-counterexamples-r3-v2.json'
        with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(record,stream,indent=2);stream.write('\n')
        print(json.dumps(dict(path=path.relative_to(ROOT).as_posix(),**pin(path))))
    else:print(json.dumps(record,indent=2))
