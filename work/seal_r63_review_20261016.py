"""Seal/check R63 independent review; only exact files, no author execution."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r63-independent-review'
LIMIT=24*1024*1024
reads=[];peak=0
class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=768*1024*1024

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path):
    guard();a=path.stat();assert a.st_size<=4*1024*1024
    raw=path.read_bytes();b=path.stat()
    assert len(raw)==a.st_size and (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    reads.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),**pin(raw)))
    return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode()
    with (OUT/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def seal():
    snap=json.loads(read(OUT/'retained-sources.json'));supp=json.loads(read(OUT/'supplement-retained.json'))
    sources={**snap['files'],**supp['files']}
    fraw=read(OUT/'findings.json');findings=json.loads(fraw)
    assert findings['sealed'] is True and findings['passed'] is True and findings['blocking_findings']==[]
    assert all(x is False for x in findings['authority'].values())
    report=('R63 independent full retained-file review: PASSED, no blocking discrepancy.\n\n'
        'All49 rows/199B,6 control-transfer records,2 CALL/4 branch sites,1 conditional-normal RET '
        'and15 explicit stores(13 stack,2 output) match retained raw bytes. No PE/engine/decoder or author '
        'program/test/game/native execution occurred.\n\n'
        'Count==1 selects fresh descriptorDATA->firstQWORD->DWORD+30; other counts write0. '
        'RAX returns the savedout pointer. Both outputs precede possible17394f0, so no finalT invariant '
        'or gold-unit/recipient/type meaning follows. Count1 cleanup uses CMP flags across JMP and lacks '
        'the other branch\'s NULL test.\n\n'
        'Before97b8a0, MOVAPS replaces XMM0 with a selector region whose bytes24..27 are not locally '
        'initialized; all128zero is not proved. R9B=1 leaves upper56 unknown. Raw MOVUPS is counted '
        'despite missing decoder write access.\n\n'
        'Producer source17,078,905B + retained upper2,973,458B =20,052,363B, including250,000B '
        'manual-console allowance. PE76,925,435B is separate. Timing433.9122ms/peak22,822,912B '
        'are retained producer witnesses. Callable/effect/reader/lease/retry permissions stayfalse.\n').encode()
    with (OUT/'report.md').open('xb') as f:f.write(report)
    files={path:{x:item[x] for x in ('bytes','sha256')} for path,item in sources.items()}
    own=['work/audit_r63_20261016.py','work/review_r63_retained_20261016.py','work/seal_r63_review_20261016.py',
         'claim.json','retained-sources.json','supplement-retained.json','raw-review.json','findings.json',
         'read-accounting.json','report.md']
    for name in own:
        path=ROOT/name if name.startswith('work/') else OUT/name
        files[str(path.relative_to(ROOT)).replace('\\','/')]=pin(read(path))
    known=findings['independent_resources']['known_explicit_data_read_bytes_before_own_final_seal']+sum(x['bytes'] for x in reads)
    assert known<LIMIT
    ap=write('seal-accounting.json',dict(schema='EU4-R63-INDEPENDENT-SEAL-ACCOUNTING/1',reads=reads,
        known_explicit_data_reads_through_seal=known,source_budget=LIMIT,self_peak=peak,
        not_all_OS_tool_source_interpreter_loader_IO=True,PE_engine_decoder_game_native=0))
    files[str((OUT/'seal-accounting.json').relative_to(ROOT)).replace('\\','/')]=ap
    m=dict(schema='EU4-R63-INDEPENDENT-MANIFEST/1',sealed=True,passed=True,
        subject_manifest=findings['subject_manifest'],subject_contract=findings['subject_contract'],
        source_pins=files,pin_count=len(files),original_source_and_accounting_pins=50,
        engine_witness_metadata_pins_unopened=38,authority=findings['authority'],
        operations=findings['operations'],author_source_unchanged=True,
        author_program_or_tests_reexecuted=False,all_shells_collected=True,new_scope_auto_authorized=False)
    print(json.dumps(dict(manifest=write('manifest.json',m),findings=pin(fraw),pins=len(files),known_bytes=known)))

def check():
    mraw=read(OUT/'manifest.json');m=json.loads(mraw)
    assert len(m['source_pins'])==m['pin_count']
    for path,expected in m['source_pins'].items():assert pin(read(ROOT/path))==expected,path
    accounting=json.loads(read(OUT/'seal-accounting.json'))
    known=accounting['known_explicit_data_reads_through_seal']+sum(x['bytes'] for x in reads)
    assert known<LIMIT
    result=dict(schema='EU4-R63-INDEPENDENT-VERIFICATION/1',sealed=True,passed=True,
        manifest=pin(mraw),pins_checked=m['pin_count'],known_explicit_data_reads_through_check=known,
        source_budget=LIMIT,self_peak=peak,PE_engine_decoder_author_program_tests_game_native=0,
        all_shells_collected=True,authority=m['authority'])
    print(json.dumps(dict(passed=True,verification=write('verification.json',result),known_bytes=known)))

if __name__=='__main__':
    if sys.argv[1:]==['--check']:check()
    else:
        assert not sys.argv[1:];seal()
