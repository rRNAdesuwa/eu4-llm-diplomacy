"""Seal/check the R64 nonauthor full actual-file review, no further analysis scope."""
from pathlib import Path
import json
import sys
import review_r64_actual_20261016_r2 as helper

ROOT=helper.ROOT;OUT=helper.OUT;LIMIT=24*1024*1024
def read(path):return helper.read(str(path.relative_to(ROOT)).replace('\\','/'))

def seal():
    snapshot=json.loads(read(OUT/'retained-source.json'));supp=json.loads(read(OUT/'supplement-retained.json'))
    source={**snapshot['files'],**supp['files']};assert len(source)==49
    fraw=read(OUT/'findings.json');findings=json.loads(fraw)
    assert findings['passed'] is True and findings['sealed'] is True and findings['blocking_findings']==[]
    assert all(x is False for x in findings['authority'].values())
    report=('R64 independent full retained-result review PASSED, no blocking discrepancy. Author files need no change.\n\n'
        'All266 rows/1003B,14 CALL sites(12 direct/2 virtual78),35 branches/49 control-transfer records, '
        'one conditional-normal RET and11 explicit stores(4 stack/4 Pheader/3 Pdata) match retained raw bytes.\n\n'
        'Flag-gated self-call withflag0 obtains the base path before A append and B first-pointer removal. '
        'F8nonzero uses Q=Wd0 then3a8/3b0 pointers and QWORD E30 equality; F8zero uses fresh unsignedF0 '
        'and24Brecords directly throughfresh Wd0. These bases and read widths are not interchangeable. '
        'Virtual78 K layout, helper bodies, aliases, loop termination and allocation failures remain unknown. '
        'No uniformRAX, count1, finalT, enum0gold, currency unit, recipient or runtime effect follows.\n\n'
        'Growth MUL takes8 and zeroextended32cap, so its local64bit overflow fallback is infeasible, '
        'although CMOVO instructions are retained literally. This does not prove allocator success.\n\n'
        'Producer source17,126,736B + retained upper3,606,604B =20,733,340B includes250,000B manual allowance. '
        'PE76,926,251B is separate; elapsed471.0191ms/peak26,136,576B are retained producer witnesses.\n\n'
        'R1 audit cache omitted verify_actual.py, which is pinned in delivery rather than original38; '
        'the source/failure are preserved and R2 adds exactly that2749B text/accounting supplement. '
        'No author/PE/engine/decoder/test/game/native action was rerun. All permissions remainfalse.\n').encode()
    with (OUT/'report.md').open('xb') as f:f.write(report)
    pins={path:{x:item[x] for x in ('bytes','sha256')} for path,item in source.items()}
    own=['work/audit_r64_actual_20261016.py','work/review_r64_actual_20261016.py',
        'work/review_r64_actual_20261016_r2.py','work/seal_r64_actual_review_20261016.py',
        'review-start.json','retained-source.json','supplement-retained.json','review-r1-source.py',
        'review-failure.json','raw-replay.json','findings.json','read-accounting.json','report.md']
    for name in own:
        path=ROOT/name if name.startswith('work/') else OUT/name
        pins[str(path.relative_to(ROOT)).replace('\\','/')]=helper.pin(read(path))
    known=findings['independent_resources']['known_explicit_data_reads_before_final_seal']+sum(x['bytes'] for x in helper.reads)
    assert known<LIMIT
    ap=helper.write('seal-accounting.json',dict(schema='EU4-R64-ACTUAL-INDEPENDENT-SEAL-READS/1',
        reads=helper.reads,known_explicit_data_reads_through_seal=known,budget=LIMIT,self_peak=helper.peak,
        not_all_OS_interpreter_or_tool_source_loading_IO=True,PE_engine_decoder_author_program_tests_game_native=0))
    pins[str((OUT/'seal-accounting.json').relative_to(ROOT)).replace('\\','/')]=ap
    manifest=dict(schema='EU4-R64-ACTUAL-INDEPENDENT-MANIFEST/1',sealed=True,passed=True,
        subject_manifest=findings['subject_manifest'],subject_contract=findings['subject_contract'],
        subject_capture=findings['subject_capture'],source_pins=pins,pin_count=len(pins),
        actual_subject_and_accounting_pins=49,engine_witness_metadata_pins_unopened=38,
        authority=findings['authority'],operations=findings['operations'],author_source_unchanged=True,
        all_shells_collected=True,new_scope_auto_authorized=False)
    print(json.dumps(dict(manifest=helper.write('manifest.json',manifest),findings=helper.pin(fraw),pins=len(pins),known_bytes=known)))

def check():
    raw=read(OUT/'manifest.json');manifest=json.loads(raw)
    assert len(manifest['source_pins'])==manifest['pin_count']
    for path,expected in manifest['source_pins'].items():assert helper.pin(read(ROOT/path))==expected,path
    acc=json.loads(read(OUT/'seal-accounting.json'))
    known=acc['known_explicit_data_reads_through_seal']+sum(x['bytes'] for x in helper.reads)
    assert known<LIMIT
    value=dict(schema='EU4-R64-ACTUAL-INDEPENDENT-VERIFICATION/1',sealed=True,passed=True,
        manifest=helper.pin(raw),pins_checked=manifest['pin_count'],known_explicit_data_reads_through_check=known,
        budget=LIMIT,self_peak=helper.peak,authority=manifest['authority'],operations=manifest['operations'],
        all_shells_collected=True,new_scope_auto_authorized=False)
    print(json.dumps(dict(passed=True,verification=helper.write('verification.json',value),known_bytes=known)))

if __name__=='__main__':
    if sys.argv[1:]==['--check']:check()
    else:
        assert not sys.argv[1:];seal()
