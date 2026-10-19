"""Seal the already successful C++ resolver validation without repeating it."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
HERE=ROOT/'work/candidates/current-country-tag-cpp-1375'
def raw(path):
    assert path.stat().st_size<=4*1024*1024
    return path.read_bytes()
def desc(path):
    data=raw(path);return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def seal(path,obj):
    data=(json.dumps(obj,sort_keys=True,indent=2)+'\n').encode('ascii')
    with path.open('xb') as stream:stream.write(data)
    return desc(path)
validation_path=HERE/'development-attempt1/validation.json'
validation=json.loads(raw(validation_path))
assert validation['passed'] is True and validation['build']['exit_code']==0
assert validation['build']['all_children_collected'] is True and validation['build']['job_active_processes_final']==0
assert validation['build']['per_process_commit_limit']==768*1024*1024
assert validation['inputs_before']==validation['inputs_after'] and validation['sources_before']==validation['sources_after']
inputs=json.loads(raw(HERE/'input-pins.json'));sources=json.loads(raw(HERE/'source-index.json'))
assert inputs==validation['inputs_before'] and sources==validation['sources_before']
assert {name:desc(ROOT/name) for name in inputs}==inputs
assert {name:desc(HERE/name) for name in sources}==sources
assert 'groups=22 native_calls=0 game_access=0' in validation['test_stdout']
report=dict(status='author_pass_pending_independent_review',groups=22,inputs=len(inputs),sources=len(sources),
    source_index=desc(HERE/'source-index.json'),validation_path=str(validation_path.relative_to(ROOT)).replace('\\','/'),validation=desc(validation_path),
    private_cpp_implementation=True,source_inputs_unchanged=True,all_children_collected=True,all_shells_collected=True,remaining_sessions=[],
    final_seal_reuses_completed_validation=True,repeated_author_build=False,seal_helper=desc(Path(__file__)),
    OS_reader_implemented=False,game_process_accessed=False,native_called=False,DLL_built=False,public_backend_registered=False,
    aba_excluded=False,lifetime_lock_verified=False,world_epoch_verified=False,strict_SP_verified=False,production_ready=False,new_decode_bytes=0)
rd=seal(HERE/'report.json',report)
review=dict(status='sealed_author_pending_independent_review',passed=True,report=rd,source_index=desc(HERE/'source-index.json'),
    validation=desc(validation_path),seal_helper=desc(Path(__file__)),all_shells_collected=True,remaining_sessions=[],
    game_accessed=False,native_called=False,production_ready=False)
print(json.dumps(dict(review=seal(HERE/'review.json',review),report=rd,source_index=desc(HERE/'source-index.json'))))
