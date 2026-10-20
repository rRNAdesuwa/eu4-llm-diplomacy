"""Retained-only source/case delivery; no controller, candidate, or tests run."""
from pathlib import Path
import ctypes,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
EVENTS=[];TOTAL=0;LIMIT=8388608;WRITTEN=0
def require(v,m):
    if not v:raise ValueError(m)
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(p,expected=None):
    global TOTAL
    size=p.stat().st_size;require(0<=size<=4194304 and TOTAL+size+1<=LIMIT,'Retained pre-reserve')
    with p.open('rb') as f:b=f.read(size+1)
    TOTAL+=len(b);EVENTS.append(dict(path=p.relative_to(ROOT).as_posix(),requested=size+1,returned=len(b)))
    require(len(b)==size and (expected is None or pin(b)==expected),'Retained pin');return b
def put(name,value):
    global WRITTEN
    b=(value if type(value)is str else json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('utf8')
    require(len(b)<=4194304 and TOTAL+WRITTEN+len(b)<=LIMIT,'Retained read/write total cap')
    with (HERE/name).open('xb') as f:f.write(b)
    WRITTEN+=len(b);return {'path':(HERE/name).relative_to(ROOT).as_posix(),**pin(b)}
def memory():
    class PM(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
          ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
           'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p
    v=PM();v.cb=ctypes.sizeof(v);ps=ctypes.WinDLL('psapi')
    ps.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    require(ps.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(v),v.cb),'Self memory counter')
    require(v.PrivateUsage<=805306368 and v.PeakPagefileUsage<=1073741824,'Source memory guard')
    return dict(private_bytes=v.PrivateUsage,peak_pagefile_bytes=v.PeakPagefileUsage,scope='Current source-building process only; no hard Job claimed')
def main():
    memory_before=memory()
    mr=read(HERE/'source-manifest.json',{'bytes':16257,'sha256':'3d70675a5901635a00efd6415ac93ead4b4dcadc726df1a6f4f065b864bb20f7'})
    manifest=json.loads(mr)
    pre={n:read(ROOT/n,v) for n,v in manifest['source_pins'].items()}
    names=['preparation.json','prepare.stdout.txt','prepare.stderr.txt','prepare-shell.json',
      'new-cases-shell.stdout.txt','new-cases-shell.stderr.txt','new-cases-shell.json',
      'offline-r1/claim.json','offline-r1/cases.json','offline-r1/job.json',
      'offline-r1/stdout.txt','offline-r1/stderr.txt','offline-r1/receipt.json','seal_delivery.py']
    retained={n:read(HERE/n) for n in names}
    prep=json.loads(retained['preparation.json']);cases=json.loads(retained['offline-r1/cases.json'])
    runner=json.loads(retained['offline-r1/receipt.json']);job=json.loads(retained['offline-r1/job.json'])
    require(cases['passed']is True and cases['failure']is None and len(cases['cases'])==4
      and all(x['passed']is True and x['runs']==1 for x in cases['cases']),'Four retained once cases')
    require(runner['passed']is True and runner['failure']is None and job['exit_code']==0
      and job['job_active_processes_final']==0 and job['direct_child_collected']is True,'Collected offline Job')
    require(job['memory_limit']==805306368 and job['hard_active_process_limit']==8
      and job['per_stream_output_acceptance_bound']==2097152,'Frozen Job bounds')
    for n in ['prepare-shell.json','new-cases-shell.json']:
        v=json.loads(retained[n]);require(v['exit_code']==0 and v['direct_child_collected']is True,'Collected author shell')
    require(not (HERE/'run-authorization.json').exists() and not (HERE/'claim.json').exists(),'No live authorization/claim')
    require(cases['source_prepost_equal']is True,'Offline source guards')
    for n,b in pre.items():require(read(ROOT/n,manifest['source_pins'][n])==b,'Delivery source postguard')
    require(read(HERE/'source-manifest.json')==mr,'Source manifest postguard')
    memory_after=memory()
    source_measured=prep['returned']+cases['returned']+runner['source_returned']
    # This sealing pass has a separate8MiB retained cap. Include earlier source
    # totals and a1MiB author/manual/publication allowance under the32MiB grant.
    source_upper=source_measured+TOTAL+1048576
    require(source_upper<33554432,'Cumulative source and manual upper')
    report="""# Source-ready for independent review

The new support-heir controller source is frozen. Four genuinely new synthetic controller/auth/result cases each ran once and passed under the frozen45-second/768MiB Job. No support CLI, reader, child-main, game/PID/UI/PE, real local.env, old test or diplomacy request ran.

The support reader21780/8b2eba84 and canonical5506/f8442eef remain unchanged. TextConfigAdapter7297/b1d44aff is byte-identical to reviewed R2. Shared GameMeter and21 named helper AST nodes remain unchanged. Only support identity/schema/selected CLI, existing support source/production review shapes, result projection and actual1..3 disk-open success accounting differ. See source-delta.json for exact comparisons.

The successful synthetic result is not a runtime sample. The support reader's8192-byte entry PE declaration remains outside its shared raw journal;4096/512KiB/single64KiB belongs to the shared selected/host/code reads. No raw entry evidence is invented. Normal context/heldNone do not certify the OS CloseHandle return. Full OS/import/cache/delegated IO and object lifetime remain unproven.

This source seal requires a new non-author peer and separate root once grant before any actual status. Future selection FRA→POL/PID98548/creation01dd5d0e670312c4 is only metadata. No prior peace grant or historical PID observation grants a lease. Current task presence/absence never means support-heir/stop-support request success, AI acceptance, final heir, persistence or native readiness.

Two pre-freeze preparation errors are retained in preparation-notes.json: an in-memory JavaScript variable error with no file effects, and explicit relocation of four newly owned files into the project directory before freeze. No case failed or repeated. No frozen source changed.
"""
    report_pin=put('SOURCE_READY.md',report)
    accounting=put('delivery-accounting.json',dict(schema='EU4-SUPPORT-CONTROLLER-DELIVERY-ACCOUNTING/1',
      prepare_returned=prep['returned'],new_case_returned=cases['returned'],runner_returned=runner['source_returned'],
      source_measured_before_seal=source_measured,seal_returned_at_accounting=TOTAL,seal_written_before_accounting=WRITTEN,
      source_plus_seal_and_manual_upper=source_upper,manual_publication_allowance=1048576,
      source_limit33554432=33554432,retained_limit8388608=LIMIT,events=EVENTS,
      scope='Explicit returned file bytes through author/read helpers; stdout transport and OS/import/cache IO not claimed; synthetic fake reads add0physical',
      memory_before=memory_before,memory_after=memory_after,
      source_prepost_equal=True,all_shells_collected=True,case_batch_attempts=1,case_runs=4,
      prior_tests=0,CLI_status_executions=0,host_binary_reads=0,target_PE_reads=0,real_config_operations=0,
      native_game_calls=0,requests=0,source_only=True))
    allpins=dict(manifest['source_pins'])
    allpins[(HERE/'source-manifest.json').relative_to(ROOT).as_posix()]=pin(mr)
    allpins.update({(HERE/n).relative_to(ROOT).as_posix():pin(b) for n,b in retained.items()})
    for x in [report_pin,accounting]:allpins[x['path']]={k:x[k] for k in ('bytes','sha256')}
    author=put('author-manifest.json',dict(schema='EU4-SUPPORT-CONTROLLER-SOURCE-DELIVERY/1',sealed=True,
      stage='SOURCE-READY pending independent source/case review; no live grant',file_pins=allpins,
      subject_source_manifest={'path':(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),**pin(mr)},
      **{field:{'path':(HERE/name).relative_to(ROOT).as_posix(),**manifest['source_pins'][(HERE/name).relative_to(ROOT).as_posix()]}
         for field,name in [('subject_controller_pin','controller.py'),('subject_child_pin','child.py'),('subject_adapter_pin','text_config_adapter.py')]},
      runtime_authorized=False,native_ready=False,selected_effect_verified=False,authorizes_retry=False))
    # First own file check uses the already-pinned graph buffers; newly written
    # report/accounting/manifest are read once. No donor program executes.
    checks={}
    for n,p in allpins.items():
        if n in pre:checks[n]=pin(pre[n])
        elif n==(HERE/'source-manifest.json').relative_to(ROOT).as_posix():checks[n]=pin(mr)
        elif n in {(HERE/x).relative_to(ROOT).as_posix() for x in retained}:
            checks[n]=pin(retained[str((ROOT/n).relative_to(HERE)).replace('\\','/')])
        else:checks[n]=pin(read(ROOT/n,p))
    require(checks==allpins,'Own retained file check')
    require(pin(read(ROOT/author['path']))=={k:author[k] for k in ('bytes','sha256')},'Author manifest pin')
    verification=put('file-check.json',dict(passed=True,pin_count=len(checks),file_pins=checks,
      author_manifest=author,source_prepost_equal=True,old_checker_executions=0,
      seal_returned=TOTAL,seal_written=WRITTEN,all_shells_collected=True))
    delivery=put('delivery.json',dict(schema='EU4-SUPPORT-CONTROLLER-SOURCE-DELIVERY-SUMMARY/1',
      source_manifest={'path':(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),**pin(mr)},
      author_manifest=author,file_check=verification,accounting=accounting,report=report_pin,
      **{field:{'path':(HERE/name).relative_to(ROOT).as_posix(),**manifest['source_pins'][(HERE/name).relative_to(ROOT).as_posix()]}
        for field,name in [('controller','controller.py'),('child','child.py'),('adapter','text_config_adapter.py'),('contract','runtime_contract.py'),('new_cases','test_controller_closure.py')]},
      offline_receipt={'path':(HERE/'offline-r1/receipt.json').relative_to(ROOT).as_posix(),**pin(retained['offline-r1/receipt.json'])},
      offline_cases={'path':(HERE/'offline-r1/cases.json').relative_to(ROOT).as_posix(),**pin(retained['offline-r1/cases.json'])},
      four_new_cases_passed_once=True,job=job,source_measured_before_seal=source_measured,
      seal_returned=TOTAL,seal_written_before_delivery=WRITTEN,source_cumulative_upper=source_upper,
      retained_upper_including_final_transport_allowance=TOTAL+WRITTEN+262144,
      runtime_authorized=False,real_config_operations=0,native_ready=False,selected_effect_verified=False,
      full_OS_IO_closed=False,entry_PE_raw_journaled=False,OS_CloseHandle_return_verified=False,all_shells_collected=True))
    print(json.dumps({'delivery':delivery,'author_manifest':author,'file_check':verification,
      'source_manifest':pin(mr),'source_cumulative_upper':source_upper,'seal_returned':TOTAL,'seal_written':WRITTEN,
      'cases':pin(retained['offline-r1/cases.json']),'receipt':pin(retained['offline-r1/receipt.json']),
      'subjects':{n:pin(pre[(HERE/n).relative_to(ROOT).as_posix()]) for n in ['controller.py','child.py','runtime_contract.py','text_config_adapter.py']},
      'all_shells_collected':True},ensure_ascii=True))
if __name__=='__main__':main()
