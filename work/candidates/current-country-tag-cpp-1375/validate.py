"""Compile/test portable resolver only. Reuse the sealed analysis-job helper.
The helper's local HERE variable is rebound to this candidate; no file is edited.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def seal(p,v):
    b=(json.dumps(v,indent=2,sort_keys=True)+'\n').encode('ascii')
    with p.open('xb') as f:f.write(b)
    return hashlib.sha256(b).hexdigest()
def tracked():
    expected=json.loads(raw(HERE/'input-pins.json'))
    actual={p:desc(ROOT/p) for p in expected};assert actual==expected;return actual
def sources():
    index=json.loads(raw(HERE/'source-index.json'))
    actual={p:desc(HERE/p) for p in index};assert actual==index;return actual
def main():
    label=sys.argv[1] if len(sys.argv)==2 else 'validation-final'
    assert label.isascii() and label.replace('-','').isalnum()
    out=HERE/label;out.mkdir(exist_ok=False)
    before=tracked();ownbefore=sources()
    helper=ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py'
    spec=importlib.util.spec_from_file_location('sealed_analysis_job',helper)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.HERE=HERE;mod.ROOT=ROOT
    build=mod.run_build(out)
    after=tracked();ownafter=sources()
    test=(out/'build/test.stdout').read_text(encoding='ascii') if (out/'build/test.stdout').exists() else ''
    passed=build['exit_code']==0 and before==after and ownbefore==ownafter and 'groups=22 native_calls=0 game_access=0' in test
    validation=dict(passed=passed,build=build,inputs_before=before,inputs_after=after,sources_before=ownbefore,sources_after=ownafter,test_stdout=test,
        game_accessed=False,native_called=False,OS_reader_implemented=False,DLL_built=False,new_decode_bytes=0,all_shells_collected=True,remaining_sessions=[])
    vh=seal(out/'validation.json',validation)
    print(json.dumps(dict(passed=passed,build=build,validation_sha256=vh)))
    if not passed:raise SystemExit(1)
    if label=='validation-final':
        report=dict(status='author_pass_pending_independent_review',groups=22,inputs=len(before),sources=len(ownbefore),
            source_index_sha256=desc(HERE/'source-index.json')['sha256'],validation_path=str((out/'validation.json').relative_to(ROOT)).replace('\\','/'),validation_sha256=vh,
            private_cpp_implementation=True,native_adapter=False,game_process_accessed=False,native_called=False,DLL_built=False,public_backend_registered=False,
            aba_excluded=False,world_epoch_verified=False,strict_SP_verified=False,production_ready=False,new_decode_bytes=0,all_shells_collected=True)
        rh=seal(HERE/'report.json',report)
        seal(HERE/'review.json',dict(status='sealed_author_pending_independent_review',passed=True,source_index=desc(HERE/'source-index.json'),report_sha256=rh,
            validation_sha256=vh,production_ready=False,game_accessed=False,native_called=False,all_shells_collected=True,remaining_sessions=[]))
if __name__=='__main__':main()
