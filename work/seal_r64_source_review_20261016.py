"""Seal/check only the independently reviewed R64 prep text; no actual access."""
from pathlib import Path
import json
import sys
import review_r64_source_20261016_r2 as helper

ROOT=helper.ROOT
OUT=helper.OUT
LIMIT=24*1024*1024

def read(path):return helper.read(str(path.relative_to(ROOT)).replace('\\','/'))

def seal():
    raw=read(OUT/'retained-source.json');snapshot=json.loads(raw)
    fraw=read(OUT/'findings.json');findings=json.loads(fraw)
    assert findings['sealed'] is True and findings['passed'] is True and findings['blocking_findings']==[]
    assert all(x is False for x in findings['authority'].values())
    report=('R64 independent source-peer review PASSED. No blocking discrepancy; author files need no change.\n\n'
        'The ten acquisition helpers are exactAST-equal to sealedR63. Main and global differences are solely '
        'namespace/entry/upstream subject/caller bytes and the correct XMM padding boundary; targeted substitutions '
        'also reproduce the full prepared producer bytes. Three independent review groups plus a new root grant '
        'precede engine/target access. Exclusive x-mode claim precedes target open. Exactpdata/8192-full-or2048-prefix, '
        '32metadata and noautofollow/normal-close-before-publication rules remain.\n\n'
        'RDX is a raw descriptor, not originalout inRBX; R9 onlybyte1 is known. MOVAPS consumes padding24..27, '
        'so XMM0 is not proven allzero. No enum0, gold units or C++ type is established.\n\n'
        'R1 audit wrongly demanded xb rather than equally exclusive x text mode; source/failure are retained, '
        'R2 corrects that check and accounting-schema key only. No author producer/test, actual/auth/claim, PE stat/open, '
        'engine/decoder or game/native operation was executed. This receipt grants no actual or runtime authority.\n').encode()
    with (OUT/'report.md').open('xb') as f:f.write(report)
    pins={p:{k:x[k] for k in ('bytes','sha256')} for p,x in snapshot['files'].items()}
    own=['work/audit_r64_source_20261016.py','work/review_r64_source_20261016.py',
        'work/review_r64_source_20261016_r2.py','work/seal_r64_source_review_20261016.py',
        'review-start.json','retained-source.json','source-review-r1.py','source-review-failure.json',
        'source-proof.json','findings.json','read-accounting.json','report.md']
    for name in own:
        path=ROOT/name if name.startswith('work/') else OUT/name
        pins[str(path.relative_to(ROOT)).replace('\\','/')]=helper.pin(read(path))
    known=findings['independent_resources']['known_explicit_data_reads_before_final_seal']+sum(x['bytes'] for x in helper.reads)
    assert known<LIMIT
    account=helper.write('seal-accounting.json',dict(schema='EU4-R64-SOURCE-PEER-SEAL-READS/1',
        reads=helper.reads,known_explicit_data_reads_through_seal=known,budget=LIMIT,
        self_peak=helper.peak,not_all_OS_interpreter_tool_source_loading_IO=True,
        target_PE_engine_decoder_producer_tests_actual_auth_claim_game_native=0))
    pins[str((OUT/'seal-accounting.json').relative_to(ROOT)).replace('\\','/')]=account
    manifest=dict(schema='EU4-R64-INDEPENDENT-SOURCE-MANIFEST/1',sealed=True,passed=True,
        subject_source_manifest=findings['subject_source_manifest'],
        subject_producer=findings['subject_producer'],subject_entry_seed=findings['subject_entry_seed'],
        source_pins=pins,pin_count=len(pins),selected_prep_upstream_text_pins=28,
        engine_witness_metadata_pins_unopened=38,authority=findings['authority'],
        operations=findings['operations'],all_shells_collected=True,
        actual_authorized=False,new_scope_auto_authorized=False)
    print(json.dumps(dict(manifest=helper.write('manifest.json',manifest),findings=helper.pin(fraw),
        pins=len(pins),known_bytes=known)))

def check():
    raw=read(OUT/'manifest.json');manifest=json.loads(raw)
    assert len(manifest['source_pins'])==manifest['pin_count']
    for p,expected in manifest['source_pins'].items():assert helper.pin(read(ROOT/p))==expected,p
    account=json.loads(read(OUT/'seal-accounting.json'))
    known=account['known_explicit_data_reads_through_seal']+sum(x['bytes'] for x in helper.reads)
    assert known<LIMIT
    result=dict(schema='EU4-R64-SOURCE-PEER-VERIFICATION/1',sealed=True,passed=True,
        manifest=helper.pin(raw),pins_checked=manifest['pin_count'],known_explicit_data_reads_through_check=known,
        budget=LIMIT,self_peak=helper.peak,operations=manifest['operations'],authority=manifest['authority'],
        all_shells_collected=True,actual_authorized=False)
    print(json.dumps(dict(passed=True,verification=helper.write('verification.json',result),known_bytes=known)))

if __name__=='__main__':
    if sys.argv[1:]==['--check']:check()
    else:
        assert not sys.argv[1:];seal()
