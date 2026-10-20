"""Seal already completed bounded fake validations without rebuilding."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def raw(p):
    assert p.stat().st_size<=16*1024*1024
    return p.read_bytes()
def desc(p):
    b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,obj):
    with p.open('xb') as f:f.write((json.dumps(obj,indent=2,sort_keys=True)+'\n').encode('ascii'))
for directory,attempt,kind in [
 ('v21-native-pair-port-r2-1375','development-attempt1','native-port-r2'),
 ('v21-native-pair-guard-1375','development-attempt2','guard-draft')]:
    here=ROOT/'work/candidates'/directory
    assert not (here/'review.json').exists()
    index=json.loads(raw(here/'source-index.json'));pins=json.loads(raw(here/'input-pins.json'))
    assert all(desc(here/name)==pin for name,pin in index.items())
    assert all(desc(ROOT/name)==pin for name,pin in pins.items())
    validation=json.loads(raw(here/attempt/'validation.json'))
    assert validation['passed'] and validation['build']['exit_code']==0
    assert validation['build']['all_children_collected'] and validation['build']['job_active_processes_final']==0
    if kind=='native-port-r2':
        assert validation['before']==validation['after']==index
        assert validation['inputs_before']==validation['inputs_after']==pins
        for name,pin in validation['outputs'].items():assert desc(here/attempt/name)==pin
        heap=raw(here/attempt/'build/r2.stdout').decode('ascii')
        integration=raw(here/attempt/'build/r3.stdout').decode('ascii')
        assert 'heap_groups=8 ' in heap and 'r3_groups=37 ' in integration
        scope={'old_author_suite':validation['tests'],'heap_regression':heap,'R3_integration':integration,
            'fix':'Reject every heap String32 before pointer reads/deleting destructors; inline capacity must be 15.',
            'heap_allocator_ownership_supported':False,'component':'exact sealed R3 implementation; unchanged R2/R3 declaration',
            'real_platform':'OBJ compiled separately, never linked or executed by fake tests'}
    else:
        assert validation['sources_before']==validation['sources_after']==index
        assert validation['inputs_before']==validation['inputs_after']==pins
        assert 'guard_groups=16 ' in validation['test_stdout']
        scope={'test_stdout':validation['test_stdout'],'component':'sealed R2; stop-spy explicitly unsupported',
            'actual_environment_binding':'compiled OBJ only; not linked or executed in fake tests',
            'adapter_dependency':'original port source declarations only; original adapter independently FAIL; no native use authorized by this report',
            'prior_compile_failure_preserved':True}
    report={'schema':1,'candidate':str(here.relative_to(ROOT)).replace('\\','/'),'passed':True,
        'scope':'Author source-bound compile and fake regression only; not an independent review.',
        'source_count':len(index),'input_count':len(pins),'same_before_after':True,'validation':attempt+'/validation.json',
        'build':validation['build'],'checks':scope,'sealing_helper':desc(Path(__file__)),
        'limitations':dict(game_accessed=False,native_called=False,DLL_built=False,strict_SP_verified=False,
            world_epoch_verified=False,atomic_lifetime_lock=False,production_ready=False,public_backend_registered=False,
            independently_reviewed=False,new_decode_bytes=0,all_shells_collected=True,remaining_sessions=[])}
    put(here/'report.json',report)
    put(here/'review.json',dict(schema=1,status='AUTHOR_FAKE_PASS',report=desc(here/'report.json'),
        validation_path=attempt+'/validation.json',validation=desc(here/attempt/'validation.json'),source_index=desc(here/'source-index.json'),
        source_before_after_same=True,game_accessed=False,native_called=False,production_ready=False))
    print(json.dumps(dict(candidate=directory,review=desc(here/'review.json'))))
