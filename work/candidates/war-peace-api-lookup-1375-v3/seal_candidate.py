"""Retain first-query receipts and verify exact files, without rerunning any query."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v3-delta-20261016-r1'
SOURCE_PIN={'bytes':12934,'sha256':'7b8b9323d20190c1c7f4b966c9520d10a4136a8f5c6be3c8957621b4b98fe6d1'}
RECEIPT_PIN={'bytes':43686,'sha256':'974136a0a56c30a78074c9556081491a47cb66ab5ed83c249b5edd510406e840'}
MAX_FILE=4*1024*1024
ANALYSIS_BUDGET=32*1024*1024
MEMORY=768*1024*1024
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
    assert peak<=MEMORY

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path,expected=None):
    guard();a=path.stat();assert a.st_size<=MAX_FILE
    raw=path.read_bytes();b=path.stat()
    assert len(raw)==a.st_size and (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    value=pin(raw)
    if expected is not None:assert value==expected,(path,value,expected)
    reads.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),**value))
    assert sum(x['bytes'] for x in reads)<=ANALYSIS_BUDGET
    return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    assert len(raw)<=MAX_FILE
    with (HERE/name).open('xb') as f:f.write(raw)
    guard();return pin(raw)

def seal():
    source=json.loads(read(HERE/'source-manifest.json',SOURCE_PIN))
    receipt=json.loads(read(REPORT/'receipt.json',RECEIPT_PIN))
    prep=json.loads(read(HERE/'preparation.json'))
    assert receipt['passed'] is True and receipt['error'] is None and receipt['command_count']==7
    assert receipt['query_pass_accounting_complete'] is True
    assert receipt['source_manifest']==SOURCE_PIN
    assert receipt['query_source_explicit_bytes']==29610945
    assert receipt['controller_explicit_bytes']==6284362
    assert receipt['combined_delta_explicit_bytes']==35895307<64*1024*1024
    files=dict(source['files'])
    for path,expected in source['files'].items():read(ROOT/path,expected)
    commands=[]
    for i,r in enumerate(receipt['records']):
        outpath=REPORT/f'{i:02d}.stdout.json';errpath=REPORT/f'{i:02d}.stderr.txt'
        raw=read(outpath,r['stdout']);err=read(errpath,r['stderr'])
        value=json.loads(raw);job=r['job']
        assert not err and value['status']=='ok' and value['tool_revision']==3
        assert job['exit_code']==0 and job['error'] is None and job['job_active_processes_final']==0
        assert job['direct_child_collected'] is True and job['completed_command_descendants_terminated'] is False
        assert 1<=job['job_total_processes']<=8 and job['peak_job_commit']<=MEMORY
        assert r['explicit_query_source_bytes']==2*r['selected_bytes_per_pass']+3*16583
        commands.append(dict(arguments=r['argv'][2:],job=job,status=value['status'],
            count=r['count'],entry_count=r['entry_count'],ids=r['ids']))
        files[str(outpath.relative_to(ROOT)).replace('\\','/')]=r['stdout']
        files[str(errpath.relative_to(ROOT)).replace('\\','/')]=r['stderr']
    for path in (HERE/'source-manifest.json',REPORT/'receipt.json',REPORT/'claim.json',HERE/'seal_candidate.py'):
        files[str(path.relative_to(ROOT)).replace('\\','/')]=pin(read(path))
    status=('EU4 1.37.5 offline API lookup v3: author frozen, independent source review pending\n\n'
        '54 records / 44 selected JSON sources. Original50 records remain data-equal. '
        'Four additions:9b46a0,3383b0,771be0 conditional_path,9844d0. R63 excluded.\n\n'
        'The first7 queries(check,catalog,four new RVA lookups,postincrement search) passed once. '
        'No oldCLI main, oldsuite, game, PE, Capstone decoder, native action, installation or publication. '
        'Exit0 means file lookup succeeded. All callable/ready/effect/lease/retry authorities remain false.\n\n'
        'Query source reads29,610,945B + controller explicit reads6,284,362B =35,895,307B, '
        'under the independent64MiB batch budget. File analysis has its own32MiB budget; '
        'neither ledger is allOS/interpreter/tool-source/loader I/O.\n').encode()
    with (HERE/'STATUS.md').open('xb') as f:f.write(status)
    files[str((HERE/'STATUS.md').relative_to(ROOT)).replace('\\','/')]=pin(status)
    analysis_prior=prep['known_data_analysis_explicit_bytes_before_this_receipt']
    analysis_total=analysis_prior+sum(x['bytes'] for x in reads)
    assert analysis_total<ANALYSIS_BUDGET
    summary=dict(schema='EU4-LOOKUP-V3-AUTHOR-DELIVERY/1',sealed=True,
        stage='frozen_file_only_candidate_pending_non_author_review',
        source_manifest=SOURCE_PIN,delta_receipt=RECEIPT_PIN,entries=54,selected_sources=44,
        original50_data_equal=True,new_rows=4,raw_decoder_dependencies_opened=0,
        queries=commands,query_batch_explicit_source_bytes=35895307,query_batch_budget=64*1024*1024,
        file_analysis_known_explicit_bytes_through_seal=analysis_total,file_analysis_budget=ANALYSIS_BUDGET,
        final_seal_read_journal=reads,controller_peak=receipt['self_peak_bytes'],
        maximum_CLI_job_peak=max(x['job']['peak_job_commit'] for x in receipt['records']),
        seal_self_peak=peak,no_repeated_queries_or_tests=True,all_jobs_shells_children_collected=True,
        substantive_query_guard_logic_changed=False,
        independent_source_review_passed=False,
        not_full_transitive_PE_engine_process_authentication=True,not_all_OS_or_loader_IO=True,
        PE_game_decoder_native_requests_install_publish=0,
        native_ready=False,callable=False,sender_authorized=False,selected_effect_verified=False,
        world_lease=False,atomic_snapshot=False,authorizes_retry=False)
    deliverypin=write('delivery.json',summary)
    files[str((HERE/'delivery.json').relative_to(ROOT)).replace('\\','/')]=deliverypin
    manifest=dict(schema='EU4-WAR-PEACE-LOOKUP-V3-AUTHOR-MANIFEST/1',sealed=True,
        stage='frozen_candidate_independent_source_review_pending',files=files,pin_count=len(files),
        source_manifest=SOURCE_PIN,delta_receipt=RECEIPT_PIN,entries=54,selected_JSON_sources=44,
        old50_data_equal=True,queries_run_once=7,no_old_tests=True,no_old_CLI_main=True,
        game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
        native_ready=False,callable=False,sender_authorized=False,selected_effect_verified=False,
        world_lease=False,atomic_snapshot=False,authorizes_retry=False,independent_source_review_passed=False)
    print(json.dumps(dict(manifest=write('manifest.json',manifest),pins=len(files),delivery=deliverypin,
        file_analysis_bytes=analysis_total,delta_bytes=35895307,max_job_peak=summary['maximum_CLI_job_peak'])))

def check():
    raw=read(HERE/'manifest.json');manifest=json.loads(raw)
    assert len(manifest['files'])==manifest['pin_count']
    for path,expected in manifest['files'].items():read(ROOT/path,expected)
    summary=json.loads(read(HERE/'delivery.json'))
    total=summary['file_analysis_known_explicit_bytes_through_seal']+sum(x['bytes'] for x in reads)
    assert total<ANALYSIS_BUDGET
    result=dict(schema='EU4-LOOKUP-V3-AUTHOR-FILECHECK/1',passed=True,sealed=True,
        manifest=pin(raw),pins_checked=manifest['pin_count'],read_journal=reads,
        known_file_analysis_explicit_bytes_through_check=total,analysis_budget=ANALYSIS_BUDGET,
        delta_explicit_bytes_separate=35895307,delta_budget_separate=64*1024*1024,
        self_peak=peak,author_check_not_independent_review=True,
        query_or_test_reexecution=False,PE_decoder_game_native_requests=0,all_shells_collected=True)
    print(json.dumps(dict(passed=True,filecheck=write('filecheck.json',result),analysis_bytes=total)))

if __name__=='__main__':
    if sys.argv[1:]==['--check']:check()
    else:
        assert not sys.argv[1:];seal()
