import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    data=raw(p);return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def seal(p,obj):
    with p.open('xb') as f:f.write((json.dumps(obj,sort_keys=True,indent=2)+'\n').encode('ascii'))
def inputs():
    index=json.loads(raw(HERE/'input-pins.json'));actual={p:desc(ROOT/p) for p in index};assert actual==index;return actual
def sources():
    index=json.loads(raw(HERE/'source-index.json'));actual={p:desc(HERE/p) for p in index};assert actual==index;return actual
def main():
    assert len(sys.argv)==2;label=sys.argv[1];assert label.isascii() and label.replace('-','').isalnum()
    out=HERE/label;out.mkdir(exist_ok=False)
    before=inputs();ownbefore=sources()
    spec=importlib.util.spec_from_file_location('sealed_analysis_job',ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py')
    job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job);job.HERE=HERE;job.ROOT=ROOT
    build=job.run_build(out);after=inputs();ownafter=sources()
    stdout=(out/'build/test.stdout').read_text(encoding='ascii') if (out/'build/test.stdout').exists() else ''
    env_stdout=(out/'build/test-env.stdout').read_text(encoding='ascii') if (out/'build/test-env.stdout').exists() else ''
    passed=build['exit_code']==0 and 'guard_groups=23 native_calls=0 game_access=0' in stdout and 'native_env_type_groups=3 ' in env_stdout and before==after and ownbefore==ownafter
    validation=dict(passed=passed,build=build,inputs_before=before,inputs_after=after,sources_before=ownbefore,sources_after=ownafter,test_stdout=stdout,
        native_environment_type_stdout=env_stdout,native_environment_sample_analysis_allocations_only=True,native_environment_initialize_called=False,
        actual_environment_binding_OBJ_only=True,actual_environment_binding_executed=False,game_process_accessed=False,native_called=False,DLL_built=False,
        world_epoch_verified=False,strict_SP_verified=False,production_ready=False,new_decode_bytes=0,all_shells_collected=True,remaining_sessions=[])
    seal(out/'validation.json',validation);print(json.dumps(dict(passed=passed,build=build,validation=desc(out/'validation.json'))))
    raise SystemExit(0 if passed else 1)
if __name__=='__main__':main()
