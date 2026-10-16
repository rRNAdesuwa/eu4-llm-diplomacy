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
REPORT=ROOT/'work/reports/war-peace-api-lookup-v4-first-queries-20261016-r1'
CLI_SHA='ee60c332fec94ce321acb10e5917ce94369d089a0ceb313d1229781ecfe99c14'
JOB=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_SHA='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
FROZEN_ENGINE_BYTES=16583
MAX_FILE=4*1024*1024
BATCH_BUDGET=64*1024*1024
MEMORY=768*1024*1024
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated',
       'selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
COMMANDS=[['check'],['catalog'],['lookup','0x97b2c0'],['lookup','0x97b8a0'],
          ['lookup','0x994f00'],['lookup','0x1a337f0'],['search','v4 已审合同','--limit','20']]

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
    claim=write('claim.json',dict(schema='EU4-LOOKUP-V4-FIRST-DELTA-CLAIM/1',commands=COMMANDS,
        query_budget=BATCH_BUDGET,file_analysis_budget_separate=24*1024*1024,
        old_CLI_main_or_tests=0,PE_decoder_game_native_requests=0))
    records=[];error=None;sourcepin=None
    try:
        sourcepin=sourceguard()
        assert hashlib.sha256(read(HERE/'war_peace_lookup.py')).hexdigest()==CLI_SHA
        jobraw=read(JOB);assert hashlib.sha256(jobraw).hexdigest()==JOB_SHA
        job=types.ModuleType('_fixed_lookup_v4_owned_job');job.__file__=str(JOB)
        exec(compile(jobraw,str(JOB),'exec'),job.__dict__)
        data_raw=read(HERE/'data-manifest.json');data=json.loads(data_raw)
        per_query_upper=2*(len(data_raw)+sum(v['bytes'] for v in data['sources'].values())+data['index']['bytes'])+3*FROZEN_ENGINE_BYTES
        for index,args in enumerate(COMMANDS):
            assert sum(x['bytes'] for x in reads)+query_bytes+per_query_upper+4*1024*1024<=BATCH_BUDGET
            stdout=REPORT/f'{index:02d}.stdout.json';stderr=REPORT/f'{index:02d}.stderr.txt'
            argv=[sys.executable,str(HERE/'war_peace_lookup.py'),*args]
            receipt=job.run_cli_tree(argv,str(ROOT),str(stdout),str(stderr),timeout_seconds=45,memory_limit=MEMORY)
            out=read(stdout);err=read(stderr)
            item=dict(argv=argv,job=receipt,stdout=pin(out),stderr=pin(err),query_source_reserved_upper_bytes=per_query_upper)
            records.append(item)
            assert receipt['exit_code']==0 and receipt['error'] is None
            assert receipt['job_active_processes_final']==0 and 1<=receipt['job_total_processes']<=8
            assert receipt['direct_child_collected'] is True and receipt['completed_command_descendants_terminated'] is False
            assert receipt['peak_job_commit']<=MEMORY and not err
            value=json.loads(out)
            assert value['status']=='ok' and value['tool_revision']==4
            assert all(value[x] is False for x in FLAGS)
            assert value['native_calls']==value['requests_published']==0
            provenance=value['provenance']
            assert provenance['selected_source_count']==59 and provenance['source_guard_before_and_after'] is True
            explicit=2*provenance['selected_bytes_per_pass']+3*FROZEN_ENGINE_BYTES
            assert explicit<=per_query_upper
            query_bytes+=explicit
            item.update(cumulative_query_source_bytes=query_bytes,cumulative_batch_explicit_bytes=query_bytes+sum(x['bytes'] for x in reads))
            assert sum(x['bytes'] for x in reads)+query_bytes<=BATCH_BUDGET
            item.update(operation=value['operation'],status=value['status'],count=value.get('count'),
                        entry_count=value.get('entry_count'),ids=[x['id'] for x in value.get('entries',[])],
                        selected_bytes_per_pass=provenance['selected_bytes_per_pass'],
                        explicit_query_source_bytes=explicit)
            if args[0]=='check':assert value['entry_count']==58
            elif args[0]=='catalog':assert value['count']==58
            elif args[0]=='lookup':
                assert value['count']==1 and value['entries'][0]['rva']==args[1]
            else:assert value['count']==4 and {x['rva'] for x in value['entries']}=={'0x97b2c0','0x97b8a0','0x994f00','0x1a337f0'}
        sourceguard(sourcepin)
    except Exception as exc:
        error=dict(type=type(exc).__name__,detail=str(exc))
    guard()
    result=dict(schema='EU4-LOOKUP-V4-FIRST-DELTA-RECEIPT/1',passed=error is None,
        sealed=True,error=error,claim=claim,source_manifest=sourcepin,records=records,
        command_count=len(records),first_queries_only=True,old_tests_or_old_CLI_main=0,
        query_source_explicit_bytes=query_bytes,controller_read_journal=reads,
        controller_explicit_bytes=sum(x['bytes'] for x in reads),
        combined_delta_explicit_bytes=query_bytes+sum(x['bytes'] for x in reads),
        query_pass_accounting_complete=error is None,
        delta_budget=BATCH_BUDGET,analysis_budget_separate=24*1024*1024,
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
