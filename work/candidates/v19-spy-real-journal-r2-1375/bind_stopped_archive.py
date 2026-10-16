"""Bind the one derived replay's exact copies to the stopped archive; no repeat replay."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
ARCHIVE=ROOT/'work/runtime/v19-stopped-source-archive-60864-20261008a'
CAPTURE=ROOT/'work/review-results/v19-journal-frame-failure-native-inventory-20261008a'
def read(path,limit):
    with path.open('rb') as source:raw=source.read(limit+1)
    assert len(raw)<=limit;return raw
def sha(raw):return hashlib.sha256(raw).hexdigest()
raw=read(ARCHIVE/'archive.json',256*1024);assert sha(raw)=='0530600502b2fe339afb83d1e12bb407f37988ea20a46135caa2f46ba54e4a06'
archive=json.loads(raw);failure=json.loads(read(CAPTURE/'failure.json',128*1024));verified=[]
for name,meta in failure['inputs_before'].items():
    source=meta['source'];pin=archive['files'][source];assert pin==dict(bytes=meta['bytes'],sha256=meta['sha256'])
    stored=ARCHIVE/'files'/source;content=read(stored,2097152);copied=read(CAPTURE/'inputs'/name,2097152)
    assert content==copied and sha(content)==pin['sha256']
    verified.append(dict(original_source=source,archive_path=stored.relative_to(ROOT).as_posix(),copy_path=(CAPTURE/'inputs'/name).relative_to(ROOT).as_posix(),**pin))
original_failure='work/runtime/v19-original-complete-parser-failure-60864.json'
failure_raw=read(ARCHIVE/'files'/original_failure,16384);assert sha(failure_raw)==archive['files'][original_failure]['sha256']
result=dict(archive_path=(ARCHIVE/'archive.json').relative_to(ROOT).as_posix(),archive_sha256=sha(raw),
    root_recorded_exit_filetime=archive['exact_exit_filetime'],recorded_stopped_identity_not_independently_observed=True,
    original_root_failure=dict(archive_path=(ARCHIVE/'files'/original_failure).relative_to(ROOT).as_posix(),sha256=sha(failure_raw)),
    all_replay_inputs_exactly_equal_stopped_archive=True,files=verified,
    replay_repeated=False,archive_claims_run_at_alternate_path=False,game_process_access=False,census_read=False)
with (HERE/'archive-binding.json').open('x',encoding='utf8') as out:json.dump(result,out,indent=2);out.write('\n')
print(json.dumps(dict(verified=len(verified),archive_binding_sha256=sha((HERE/'archive-binding.json').read_bytes()),replay_repeated=False)))
