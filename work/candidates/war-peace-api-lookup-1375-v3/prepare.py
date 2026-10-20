"""Freeze exact v3 source graph before any new CLI query; file-only author receipt."""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MAX=4*1024*1024
reads=[]
peak=0
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

def read(path):
    guard()
    a=path.stat();assert a.st_size<=MAX
    raw=path.read_bytes();b=path.stat()
    assert len(raw)==a.st_size and (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
    reads.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),bytes=len(raw)))
    return raw

def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def write(name,obj):
    raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    with (HERE/name).open('xb') as f:f.write(raw)
    guard()
    return pin(raw)

def main():
    data=json.loads(read(HERE/'data-manifest.json'))
    files=dict(data['sources'])
    old='work/candidates/war-peace-api-lookup-1375-v2/'
    paths=[old+x for x in ('index.json','data-manifest.json','source-manifest.json','war_peace_lookup.py')]
    paths+=['work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py',
            'work/candidates/frida-entry-observer-1375-v1/job_tree.py']
    paths+=[str((HERE/x).relative_to(ROOT)).replace('\\','/') for x in ('index.json','data-manifest.json',
        'war_peace_lookup.py','build_index.py','prepare.py','run_queries.py','budget.json','README.md',
        'lineage-proof.json','source-delta.json','build-claim.json','build-receipt.json',
        'v2-retained-snapshot.json','new-retained-snapshot.json')]
    for path in paths:files[path]=pin(read(ROOT/path))
    for path,expected in data['sources'].items():assert pin(read(ROOT/path))==expected
    for path in ('war_peace_lookup.py','build_index.py','prepare.py','run_queries.py'):
        ast.parse(read(HERE/path))  # Syntax validation only, never imports a tool or test suite.
    v2=json.loads(read(HERE/'v2-retained-snapshot.json'));new=json.loads(read(HERE/'new-retained-snapshot.json'))
    builder=json.loads(read(HERE/'build-receipt.json'))
    # Four new-snapshot inspections and two v2-snapshot inspections before this freezer.
    initial=sum(x['bytes'] for x in v2['source_reads'])+sum(x['bytes'] for x in new['source_reads'])
    previous_owned_reads=4*(HERE/'new-retained-snapshot.json').stat().st_size+2*(HERE/'v2-retained-snapshot.json').stat().st_size
    accounted=initial+previous_owned_reads+builder['explicit_source_read_bytes']+sum(x['bytes'] for x in reads)
    assert accounted<=32*1024*1024
    receipt=write('preparation.json',dict(schema='EU4-LOOKUP-V3-SOURCE-PREPARATION/1',sealed=True,
        data_manifest=files[str((HERE/'data-manifest.json').relative_to(ROOT)).replace('\\','/')],entries=54,selected_sources=44,
        original50_data_equal=True,new_queries_run=0,independent_review_passed=False,
        known_data_analysis_explicit_bytes_before_this_receipt=accounted,
        source_budget=32*1024*1024,read_journal=reads,
        self_peak_from_builder=builder['self_peak_bytes'],
        self_peak_observed=peak,software_memory_guard=768*1024*1024,
        not_all_OS_interpreter_or_tool_source_loading_IO=True,
        PE_decoder_oldCLI_oldtests_game_native=0))
    files[str((HERE/'preparation.json').relative_to(ROOT)).replace('\\','/')]=receipt
    manifest=dict(schema='EU4-WAR-PEACE-LOOKUP-V3-SOURCE-MANIFEST/1',sealed=True,
        stage='author_frozen_file_only_candidate_independent_review_pending',
        game_sha256=data['game_sha256'],files=files,pin_count=len(files),
        query_logic='Frozen Python file-query engine; no Capstone decoder dependency',
        selected_JSON_source_count=44,old_rows_data_equal=50,new_rows=4,
        flat_selected_graph_not_recursive_PE_engine_or_process_authentication=True,
        native_ready=False,callable=False,sender_authorized=False,selected_effect_verified=False,
        world_lease=False,atomic_snapshot=False,authorizes_retry=False)
    print(json.dumps(dict(source_manifest=write('source-manifest.json',manifest),pins=len(files),
        analysis_bytes=accounted,delta_queries_not_yet_run=True)))

if __name__=='__main__':main()
