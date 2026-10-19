"""Exactly seven first delta file queries in bounded newly-created CLI jobs."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import sys
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v3-delta-20261016-r1'
CLI_SHA='f4b5f7e1fe4e5546cdac66a6f9bb45541ead648d311cc2e2e9023e2b56910979'
JOB=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_SHA='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
FROZEN_ENGINE_BYTES=16583
MAX_FILE=4*1024*1024
BATCH_BUDGET=64*1024*1024
MEMORY=768*1024*1024
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated',
       'selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
COMMANDS=[['check'],['catalog'],['lookup','0x9b46a0'],['lookup','0x3383b0'],
          ['lookup','0x771be0'],['lookup','0x9844d0'],['search','postincrement','--limit','20']]

class PMC(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
        (x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage',
        'PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
peak=0;reads=[];query_bytes=0

def guard():
    global peak
    x=PMC();x.cb=ctypes.sizeof(x)
    assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
    peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage)
    assert peak<=MEMORY

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def read(path):
    guard();a=path.stat();assert a.st_size<=MAX_FILE
    assert sum(x['bytes'] for x in reads)+a.st_size+query_bytes<=BATCH_BUDGET
    raw=path.read_bytes();b=path.stat()
    assert (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns) and len(raw)==a.st_size
    reads.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),**pin(raw)))
    return raw

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    with (REPORT/name).open('xb') as f:f.write(raw)
    return pin(raw)

def sourceguard(expected_manifest=None):
    raw=read(HERE/'source-manifest.json')
    if expected_manifest is not None:assert pin(raw)==expected_manifest
    manifest=json.loads(raw)
    assert manifest['sealed'] is True and manifest['native_ready'] is False
    for path,expected in manifest['files'].items():
        assert pin(read(ROOT/path))==expected,(path,'source_changed')
    return pin(raw)

def main():
    global query_bytes
    REPORT.mkdir(exist_ok=False)
    claim=write('claim.json',dict(schema='EU4-LOOKUP-V3-FIRST-DELTA-CLAIM/1',commands=COMMANDS,
        query_budget=BATCH_BUDGET,file_analysis_budget_separate=32*1024*1024,
        old_CLI_main_or_tests=0,PE_decoder_game_native_requests=0))
    records=[];error=None;sourcepin=None
    try:
        sourcepin=sourceguard()
        assert hashlib.sha256(read(HERE/'war_peace_lookup.py')).hexdigest()==CLI_SHA
        jobraw=read(JOB);assert hashlib.sha256(jobraw).hexdigest()==JOB_SHA
        job=types.ModuleType('_fixed_lookup_v3_owned_job');job.__file__=str(JOB)
        exec(compile(jobraw,str(JOB),'exec'),job.__dict__)
        for index,args in enumerate(COMMANDS):
            stdout=REPORT/f'{index:02d}.stdout.json';stderr=REPORT/f'{index:02d}.stderr.txt'
            argv=[sys.executable,str(HERE/'war_peace_lookup.py'),*args]
            receipt=job.run_cli_tree(argv,str(ROOT),str(stdout),str(stderr),timeout_seconds=45,memory_limit=MEMORY)
            out=read(stdout);err=read(stderr)
            item=dict(argv=argv,job=receipt,stdout=pin(out),stderr=pin(err))
            records.append(item)
            assert receipt['exit_code']==0 and receipt['error'] is None
            assert receipt['job_active_processes_final']==0 and 1<=receipt['job_total_processes']<=8
            assert receipt['direct_child_collected'] is True and receipt['completed_command_descendants_terminated'] is False
            assert receipt['peak_job_commit']<=MEMORY and not err
            value=json.loads(out)
            assert value['status']=='ok' and value['tool_revision']==3
            assert all(value[x] is False for x in FLAGS)
            assert value['native_calls']==value['requests_published']==0
            provenance=value['provenance']
            assert provenance['selected_source_count']==44 and provenance['source_guard_before_and_after'] is True
            explicit=2*provenance['selected_bytes_per_pass']+3*FROZEN_ENGINE_BYTES
            query_bytes+=explicit
            assert sum(x['bytes'] for x in reads)+query_bytes<=BATCH_BUDGET
            item.update(operation=value['operation'],status=value['status'],count=value.get('count'),
                        entry_count=value.get('entry_count'),ids=[x['id'] for x in value.get('entries',[])],
                        selected_bytes_per_pass=provenance['selected_bytes_per_pass'],
                        explicit_query_source_bytes=explicit)
            if args[0]=='check':assert value['entry_count']==54
            elif args[0]=='catalog':assert value['count']==54
            elif args[0]=='lookup':
                assert value['count']==1 and value['entries'][0]['rva']==args[1]
                if args[1]=='0x771be0':
                    row=value['entries'][0]
                    assert row['scope_kind']=='conditional_path' and row['owned_code_unique_bytes']==268
                    assert row['whole_function_closed'] is False and row['independent_fragment_callable'] is False
            else:assert value['count']==1 and value['entries'][0]['id']=='shared.pending_kind_counter_path'
        sourceguard(sourcepin)
    except Exception as exc:
        error=dict(type=type(exc).__name__,detail=str(exc))
    guard()
    result=dict(schema='EU4-LOOKUP-V3-FIRST-DELTA-RECEIPT/1',passed=error is None,
        sealed=True,error=error,claim=claim,source_manifest=sourcepin,records=records,
        command_count=len(records),first_queries_only=True,old_tests_or_old_CLI_main=0,
        query_source_explicit_bytes=query_bytes,controller_read_journal=reads,
        controller_explicit_bytes=sum(x['bytes'] for x in reads),
        combined_delta_explicit_bytes=query_bytes+sum(x['bytes'] for x in reads),
        query_pass_accounting_complete=error is None,
        delta_budget=BATCH_BUDGET,analysis_budget_separate=32*1024*1024,
        self_peak_bytes=peak,all_jobs_and_direct_children_collected=all(
            x['job']['job_active_processes_final']==0 and x['job']['direct_child_collected'] for x in records),
        not_all_OS_interpreter_tool_source_or_loader_IO=True,
        Python_query_engine_not_Capstone_decoder=True,
        PE_decoder_game_native_requests_install_publish=0,
        native_ready=False,callable=False,sender_authorized=False,selected_effect_verified=False,
        world_lease=False,atomic_snapshot=False,authorizes_retry=False)
    resultpin=write('receipt.json',result)
    print(json.dumps(dict(passed=error is None,receipt=resultpin,query_bytes=query_bytes,
        controller_bytes=sum(x['bytes'] for x in reads),self_peak_bytes=peak,error=error)))
    return 0 if error is None else 2

if __name__=='__main__':raise SystemExit(main())
