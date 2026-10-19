"""CreateNew report and exact source inventory; no native decode or actual replay."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=ROOT/'work/candidates/v19-spy-real-journal-1375'
FAIL=ROOT/'work/review-results/v19-journal-frame-failure-native-inventory-20261008a'
REPLAY=ROOT/'work/review-results/v19-journal-r2-captured-replay-native-inventory-20261008a'
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def write(name,value):
    with (HERE/name).open('x',encoding='utf8') as out:json.dump(value,out,indent=2);out.write('\n')
anchors=[]
for name,lo,hi,meaning in (
 ('work/candidates/v19-spy-restricted-host-r2-1375/host.cpp',110,116,'Core Host frame_id receives global status.owner_frames'),
 ('work/candidates/v19-spy-restricted-host-r2-1375/host.cpp',128,158,'Every callback increments global frame; stage3 receipt is saved once; subsequent health is permitted'),
 ('work/candidates/v19-spy-send-core-1375/spy_send_core.cpp',157,163,'Core event.frame is exactly Host.frame_id'),
 ('work/candidates/v19-spy-send-core-1375/spy_send_core.cpp',228,233,'Item owner_frame is the global Host.frame_id'),
 ('work/candidates/v19-spy-bootstrap-lab-1375/bootstrap.cpp',148,171,'Outer records actual controller before/after counters and complete raw segment hash')):
    path=ROOT/name;lines=path.read_text(encoding='utf8').splitlines();anchors.append(dict(path=name,sha256=digest(path),first_line=lo,last_line=hi,text='\n'.join(lines[lo-1:hi]),meaning=meaning))
summary=json.loads((REPLAY/'derived-summary.json').read_bytes());binding=json.loads((HERE/'archive-binding.json').read_bytes())
report=dict(schema='V19_REAL_JOURNAL_FRAME_REPAIR/2',old_review_sha256=digest(OLD/'review.json'),
    scope='Pure full-stream global frame handoff correction; new candidate only',
    failure=dict(path=(FAIL/'failure.json').relative_to(ROOT).as_posix(),sha256=digest(FAIL/'failure.json'),
        old_expected_next_global_frame=67,actual_next_global_frame=85,third_health=66,previous_complete_global_frame=84),
    source_anchors=anchors,new_decoded_bytes=0,changed_runtime_reducer_sources=['interval.py','reader.py'],
    invariants=['Every outer owner begin before-frame equals fully replayed global frame',
      'Every owner return is exactly global+1 with exact raw byte range/hash/ordinal and raw/Core frame equality',
      'First seq4 inherits prior fully paired frame, independently of immutable stage3 proof frame',
      'All raw/Core/item/result absolute frames and timestamps remain unchanged',
      'Derived send-local frame begins at1 and increments exactly once per fully validated owner callback',
      'All original Result/unknown/ownership/claims/final health constraints preserved'],
    tests=dict(inherited_methods=25,new_synthetic_methods=7,actual_replay_count=1),
    derived_replay=dict(path=(REPLAY/'derived-summary.json').relative_to(ROOT).as_posix(),sha256=digest(REPLAY/'derived-summary.json'),
      complete=summary['status']=='complete',raw_rows=355,outer_rows=196,mapping=summary['send_frame_mapping'],
      completed_outcomes=summary['completed_outcomes'],effect_verified=False,production_ready=False,entry_time_invented=False),
    archive_binding=dict(path=(HERE/'archive-binding.json').relative_to(ROOT).as_posix(),sha256=digest(HERE/'archive-binding.json'),
      archive_sha256=binding['archive_sha256'],all15_inputs_exactly_equal_stopped_archive=True,replay_repeated=False),
    actual_process_access=False,actual_native_call=False,actual_publication=False,dll_compile=False,dll_load=False,
    old_source_modified=False,actual_trace_bytes_modified=False,source_bound_origin_verified=False,build_loader_verified=False,
    strict_sp_verified=False,world_epoch_verified=False,runtime_authorized=False,effect_verified=False,production_ready=False)
write('report.json',report)
pins=dict(json.loads((OLD/'source-index.json').read_bytes())['files'])
for path in (OLD/'review.json',OLD/'source-index.json',FAIL/'failure.json',FAIL/'capture_failure.py',REPLAY/'attempt.json',REPLAY/'completion.json',REPLAY/'derived-summary.json'):
    pins[path.relative_to(ROOT).as_posix()]=digest(path)
for anchor in anchors:pins[anchor['path']]=anchor['sha256']
for path in (FAIL/'inputs').iterdir():pins[path.relative_to(ROOT).as_posix()]=digest(path)
archive=ROOT/binding['archive_path'];pins[archive.relative_to(ROOT).as_posix()]=digest(archive)
for value in binding['files']:
    path=ROOT/value['archive_path'];pins[path.relative_to(ROOT).as_posix()]=digest(path)
path=ROOT/binding['original_root_failure']['archive_path'];pins[path.relative_to(ROOT).as_posix()]=digest(path)
for path in HERE.rglob('*'):
    if path.is_file() and path.name not in ('source-index.json','review.json'):pins[path.relative_to(ROOT).as_posix()]=digest(path)
assert len(pins)<=128
write('source-index.json',dict(schema=2,files=pins))
print(json.dumps(dict(report_sha256=digest(HERE/'report.json'),source_index_sha256=digest(HERE/'source-index.json'),files=len(pins))))
