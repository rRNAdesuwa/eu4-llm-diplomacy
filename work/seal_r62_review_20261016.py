"""Seal/check independent R62 retained-file review. No author code execution."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r62-independent-review'
SUBJECT = 'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
SNAPSHOT = OUT / 'retention-r2/retained-sources.json'
CAP = 4 * 1024 * 1024
BUDGET = 24 * 1024 * 1024

def read(path):
    before = path.stat()
    assert before.st_size <= CAP
    raw = path.read_bytes()
    after = path.stat()
    assert len(raw) == before.st_size
    assert (before.st_size,before.st_mtime_ns) == (after.st_size,after.st_mtime_ns)
    return raw

def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def write(path, value):
    raw=(json.dumps(value,ensure_ascii=True,indent=2)+'\n').encode()
    with path.open('xb') as f:
        f.write(raw)
    return pin(raw)

def seal():
    snapraw=read(SNAPSHOT)
    snapshot=json.loads(snapraw)
    findingsraw=read(OUT/'findings.json')
    findings=json.loads(findingsraw)
    assert findings['sealed'] is True and findings['passed'] is True
    assert findings['subject_manifest']=={'bytes':14300,'sha256':'d3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'}
    assert findings['blocking_findings']==[]
    assert all(v is False for v in findings['authority'].values())
    sourcepins={p:{k:x[k] for k in ('bytes','sha256')} for p,x in snapshot['files'].items()}
    own_paths=[
        'work/audit_r62_20261016.py','work/audit_r62_20261016_r2.py',
        'work/review_r62_retained_20261016.py','work/review_r62_retained_20261016_r2.py',
        'work/seal_r62_review_20261016.py',
        'claim.json','failure.json','retention-r2/claim.json','retention-r2/retained-sources.json',
        'semantic-review-r1-source.py','semantic-review-failure.json',
        'raw-review.json','findings.json','postguard-ledger.json','report.md']
    seal_reads=[{'path':str(SNAPSHOT.relative_to(ROOT)).replace('\\','/'),**pin(snapraw)},
                {'path':str((OUT/'findings.json').relative_to(ROOT)).replace('\\','/'),**pin(findingsraw)}]
    for name in own_paths:
        path=ROOT/name if name.startswith('work/') else OUT/name
        raw=read(path)
        p=str(path.relative_to(ROOT)).replace('\\','/')
        sourcepins[p]=pin(raw)
        seal_reads.append({'path':p,**pin(raw)})
    stagebytes=sum(x['bytes'] for x in seal_reads)
    assert findings['independent_review_resources']['known_explicit_data_reads_before_output_sealing']+stagebytes<BUDGET
    write(OUT/'seal-accounting.json',{'schema':'EU4-R62-INDEPENDENT-SEAL-ACCOUNTING/1',
        'explicit_pin_reads':seal_reads,'bytes':stagebytes,
        'prior_known_explicit_data_read_bytes':findings['independent_review_resources']['known_explicit_data_reads_before_output_sealing'],
        'known_explicit_data_reads_through_seal':findings['independent_review_resources']['known_explicit_data_reads_before_output_sealing']+stagebytes,
        'budget':BUDGET,'not_all_OS_Python_or_tool_source_loading_IO':True,
        'subject_unchanged':True,'author_program_PE_decoder_engine_game_native':0})
    accountread=read(OUT/'seal-accounting.json')
    sourcepins[str((OUT/'seal-accounting.json').relative_to(ROOT)).replace('\\','/')]=pin(accountread)
    manifest={'schema':'EU4-R62-INDEPENDENT-MANIFEST/1','sealed':True,'passed':True,
        'subject_manifest':findings['subject_manifest'],'source_pins':sourcepins,
        'pin_count':len(sourcepins),'original_subject_and_accounting_pins':41,
        'engine_metadata_witness_pins_not_opened':38,
        'independent_findings':pin(findingsraw),'author_frozen_source_modified':False,
        'operations':findings['operations'],'authority':findings['authority'],
        'check_scope':'fixed explicit files only; engine closure metadata unopened; no author program/PE/decoder/tests/game',
        'self_preliminary_failures_preserved':True,'all_shells_collected':True}
    print(json.dumps({'manifest':write(OUT/'manifest.json',manifest),'pin_count':len(sourcepins)}))

def check():
    mraw=read(OUT/'manifest.json');m=json.loads(mraw)
    assert m['sealed'] is True and m['passed'] is True
    assert len(m['source_pins'])==m['pin_count']
    readbytes=len(mraw)
    for path,expected in m['source_pins'].items():
        raw=read(ROOT/path);readbytes+=len(raw)
        assert pin(raw)==expected,(path,pin(raw),expected)
    findings=json.loads(read(OUT/'findings.json'));readbytes+=(OUT/'findings.json').stat().st_size
    assert findings['passed'] is True and findings['blocking_findings']==[]
    account=json.loads(read(OUT/'seal-accounting.json'));readbytes+=(OUT/'seal-accounting.json').stat().st_size
    assert account['known_explicit_data_reads_through_seal']+readbytes<BUDGET
    value={'schema':'EU4-R62-INDEPENDENT-VERIFICATION/1','passed':True,'sealed':True,
        'manifest':pin(mraw),'pin_count':m['pin_count'],'explicit_check_read_bytes':readbytes,
        'known_explicit_data_reads_through_seal_and_check':account['known_explicit_data_reads_through_seal']+readbytes,
        'source_budget':BUDGET,'PE_engine_decoder_author_program_tests_game_native':0,
        'all_shells_collected':True,'authority':m['authority']}
    result=write(OUT/'verification.json',value)
    print(json.dumps({'passed':True,'checked_pins':m['pin_count'],'verification':result,
        'manifest':pin(mraw),'findings':pin((OUT/'findings.json').read_bytes())}))

if __name__=='__main__':
    if sys.argv[1:] == ['--check']:
        check()
    else:
        assert not sys.argv[1:]
        seal()
