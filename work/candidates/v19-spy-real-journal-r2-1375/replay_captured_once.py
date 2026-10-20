"""One derived replay of already copied terminal logs; never reads live session/process.
The permanent attempt marker prevents accidental rerun. This is a passive reader,
not an engine request, permission gate, or causal effect review.
"""
from pathlib import Path
import hashlib,json,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
CAPTURE=ROOT/'work/review-results/v19-journal-frame-failure-native-inventory-20261008a'
OUT=ROOT/'work/review-results/v19-journal-r2-captured-replay-native-inventory-20261008a'
OUT.mkdir(exist_ok=False)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(name,value):
    with (OUT/name).open('x',encoding='utf8') as out:json.dump(value,out,indent=2);out.write('\n')
failure_raw=(CAPTURE/'failure.json').read_bytes();assert sha(failure_raw)=='8fcb3b61cc2c7c9c1dfce83f9838a1cd5fba5268f0cced92b4759e29819913f7'
failure=json.loads(failure_raw);expected=failure['inputs_before'];inputs={};before={}
for name,meta in expected.items():
    with (CAPTURE/'inputs'/name).open('rb') as stream:raw=stream.read(2097152+1)
    assert len(raw)==meta['bytes'] and sha(raw)==meta['sha256'];inputs[name]=raw
    before[name]=dict(bytes=len(raw),sha256=sha(raw))
source_before={p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in HERE.rglob('*.py')}
write('attempt.json',dict(schema='V19_CAPTURED_REPLAY_ATTEMPT/1',copied_input_directory=CAPTURE.relative_to(ROOT).as_posix(),
    inputs=before,source_before=source_before,actual_session_directory_read=False,process_access=False,native_operation=False,retry_allowed=False))
result=None;error=None
try:
    from reader import validate_stream
    claims={name[:-6]:raw for name,raw in inputs.items() if name.endswith('.claim')}
    for n in range(1,5):assert inputs[f'{n}.request']==inputs[f'{n}.claim']
    result=validate_stream(inputs['raw-events.jsonl'],inputs['bootstrap-events.jsonl'],failure['identity'],claims,complete=True)
    assert result['status']=='complete' and result['completed_outcomes']==[5]*5
    write('derived-summary.json',result)
except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc());write('failure.json',error)
after={name:dict(bytes=(CAPTURE/'inputs'/name).stat().st_size,sha256=sha((CAPTURE/'inputs'/name).read_bytes())) for name in expected}
source_after={p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in HERE.rglob('*.py')}
assert before==after and source_before==source_after
write('completion.json',dict(passed=error is None,error=error,inputs_unchanged=True,sources_unchanged=True,inputs_after=after,source_after=source_after,
    parsed_raw_rows=len(inputs['raw-events.jsonl'].splitlines()),parsed_outer_rows=len(inputs['bootstrap-events.jsonl'].splitlines()),
    summary_sha256=sha((OUT/'derived-summary.json').read_bytes()) if result else None,
    process_access=False,actual_session_directory_read=False,native_operation=False,effect_verified=False,production_ready=False))
print(json.dumps(dict(passed=error is None,error=error['message'] if error else None,summary_sha256=sha((OUT/'derived-summary.json').read_bytes()) if result else None,
    frame_mapping=result['send_frame_mapping'] if result else None,outcomes=result['completed_outcomes'] if result else None)))
raise SystemExit(0 if error is None else 1)
