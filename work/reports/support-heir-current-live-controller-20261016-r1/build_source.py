"""Source-only freeze: selected ordinary files, AST comparisons, no subject imports."""
from pathlib import Path
import ast,ctypes,hashlib,json,sys,traceback
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BUILD='work/reports/support-heir-current-controller-source-authorization-20261016-r1/authorization.json'
BUILD_PIN={'bytes':10852,'sha256':'79ecd0456ecd8d99a8bc215313e610cc297be2075ae0042d2a12a76415cdd3a9'}
DONOR='work/reports/peace-current-pending-v2-live-controller-20261016-r2/'
METER='work/candidates/peace-current-pending-observer-1375-v2/offline_child.py'
EVENTS=[];TOTAL=54277
# 10,852 grant + 35,679 donor text + 7,746 Meter source bytes already returned
# during this turn before this builder. Retained memory inspections add no file IO.
PRIOR=TOTAL;LIMIT=33554432
def require(v,m):
    if not v:raise ValueError(m)
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(p,expected=None):
    global TOTAL
    size=p.stat().st_size;require(0<size<=4194304 and TOTAL+size+1<=LIMIT,'Build source bound before read')
    with p.open('rb') as f:b=f.read(size+1)
    TOTAL+=len(b);EVENTS.append(dict(path=str(p),requested=size+1,returned=len(b)))
    require(len(b)==size and (expected is None or pin(b)==expected),'Build exact source pin');return b
def put(name,v):
    b=(v if type(v)is str else json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('utf8')
    require(len(b)<=4194304,'Build retained bound')
    with (HERE/name).open('xb') as f:f.write(b)
    return pin(b)
def tree(b):return ast.parse(b)
def node(b,name):return next(n for n in tree(b).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
def dump(n):return ast.dump(n,include_attributes=False)
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
    require(not (HERE/'source-manifest.json').exists(),'Frozen source cannot be replaced')
    buildraw=read(ROOT/BUILD,BUILD_PIN);grant=json.loads(buildraw);require(grant['source_build_only']is True and grant['runtime_authorized']is False,'Source only grant')
    expected=dict(grant['fixed_inputs']);pre={n:read(ROOT/n,v) for n,v in sorted(expected.items())}
    dm=json.loads(pre[DONOR+'source-manifest.json'])
    donors={}
    for name in ['controller.py','child.py','runtime_contract.py']:
        n=DONOR+name;expected[n]=dm['source_pins'][n];donors[name]=read(ROOT/n,expected[n]);pre[n]=donors[name]
    expected[METER]=dm['source_pins'][METER];pre[METER]=read(ROOT/METER,expected[METER])
    newnames=['controller.py','child.py','runtime_contract.py','text_config_adapter.py','test_controller_closure.py','run_new_cases_once.py','build_source.py']
    local={n:read(HERE/n) for n in newnames}
    for b in local.values():tree(b)
    require(pin(local['text_config_adapter.py'])==grant['fixed_inputs'][DONOR+'text_config_adapter.py'],'Byte-identical reviewed adapter')
    require(dump(node(local['child.py'],'game_meter_class'))==dump(node(donors['child.py'],'game_meter_class')),'GameMeter AST unchanged')
    shared={}
    for filename,names in [('controller.py',['require','pin','decode','read','save','validate_io','validate_config_io']),
      ('child.py',['require','pin','decode','read','save','game_meter_class']),
      ('runtime_contract.py',['require','pin','decode','relative','checked_path','exact_pin','triple','read_reference'])]:
        for name in names:
            require(dump(node(local[filename],name))==dump(node(donors[filename],name)),'Donor helper changed '+filename+':'+name)
            shared[filename+':'+name]=True
    require(len(json.loads(pre['work/candidates/frida-entry-observer-1375-v1/host-manifest.json'])['source_pins'])==215,'Host metadata count')
    source_delta=dict(schema='EU4-SUPPORT-CONTROLLER-SOURCE-DELTA/1',donor=expected|{},
        unchanged_helper_AST=shared,unchanged_adapter=pin(local['text_config_adapter.py']),
        unchanged_frozen_reader=grant['fixed_inputs']['work/candidates/support-heir-current-observer-1375-v1/support_heir_current_observer.py'],
        metadata_and_main_changes=['New independent namespace, schema, build grant, support-specific original review field shapes and exact CLI.',
          'New future once authorization with four exact source subjects and mandatory peer; peace authorization is rejected.',
          'Controller reads budget_accounting/shared and preserves separate entry_PE_identity_read declaration, never patches capture or Held.',
          'Support has one explicit disk_identity path; success requires actual N in1..3 complete intercepted hashes and N*38462504 bytes, replacing peace exact3 predicate.',
          'Child METER_DONOR stays exact frozen offline_child definitions; only selected CLI path/contract constants and schema labels change.',
          'Four new synthetic controller-only cases; no candidate/CLI/adapter/old-test execution.'],
        limitations=['Explicit intercepted read accounting is not full OS/import/cache/loader or delegated IO closure.',
          'Prior guard/source observation is not a process/world lease.',
          'Entry8192 remains a source declaration outside the shared raw journal.',
          'OS CloseHandle return is not verified; current task presence is not action/final-heir effect.'],
        all_authority_false=True)
    put('source-delta.json',source_delta)
    put('budget.json',dict(build_limits=grant['build_limits'],future_live=grant['future_live_budget_design'],
        selected_source_preflight_bytes=sum(v['bytes'] for v in expected.values()),new_case_maximum=4,
        expected_case_and_runner_source_passes=4,ordinary_code_only=True,
        future_host_pin_pass_witness=9,future_host_pin_bytes_9pass=2302453278,
        future_host_returned_hardcap=3221225472,host_binary_reads_during_build=0,
        config_real_operations_during_build=0,full_OS_IO_covered=False))
    put('PROTOCOL.md',"""# Support-heir current controller source profile

This directory contains a future once-only current-status controller. Source build and synthetic cases do not authorize any process access. Root must issue a new exact EU4-SUPPORT-HEIR-CURRENT-STATUS-ONCE/1 grant after independent source review. The grant SHA is the sole argument; source_manifest/controller/child/adapter complete triples and a sealed passed peer with empty blockers must match. A peace grant cannot substitute.

The existing support reader, canonical metadata, RuntimeCapture, Held, and all dependency files are unchanged. The adapter is an exact7297-byte copy of reviewed R2 TextConfigAdapter. No real local.env stat/open/hash/read occurs in this preparation. The future grant configuration triple is fixed to build metadata, separately authenticated before binary snapshot decode. No values, invalid raw lines, or environment contents may be logged.

Only selected FRA-to-POL current index state can be reported. Both selected pointers0 can mean absent; identical nonzero selected pointer must pass the frozen reader's profile/endpoint/lifecycle-byte and double-pass guards. This controller does not add a reader, modify guards, or infer final heir, original request acceptance, native action mapping, atomicity, persistence or lifetime.

Entry PE8192 is a source-declared read outside the frozen shared raw journal. Preserve this distinct declaration; do not synthesize raw entry bytes, treat it as measured actual on failure, or claim complete RPM accounting. Shared attempted reads retain4096 calls/512KiB/single64KiB. Source schema budget_accounting replaces the unrelated peace rpm_budget projection.

The unchanged GameMeter permits only the exact game file, size and rb streaming path, at most3 opens. The support source explicitly invokes disk_identity once, so current success accepts actual N=1..3 only when every intercepted open reaches EOF, complete expected SHA and normal close, with returned=N*38462504. It does not add hashes to reach3. This differs from the peace controller's exact3 success predicate; max3 and all Meter code remain unchanged. Ordinary reads reserve the full request, including16MiB+1 bounded helper requests, without shrinking them. Exact226 host paths alone obtain the original streamed exception. Delegated methods/OS/import/cache reads remain outside a complete IO proof.

Only4 new synthetic cases run once after source freeze: valid support auth/result with1 complete hash; reject peace grant schema; reject adapter peer mismatch; reject fourth game open. They execute new controller/contract definitions against in-memory fake references and captures, never candidate/CLI/main/child/adapter or game. Frozen Job helper runs the batch with45s,768MiB,8-process and2MiB stream limits. The first failure is retained and stops; no retry. No old15/2/8/6/31 tests execute.

Future control claims and child claims are exclusive and permanent. Loaded/source/world/typed-country guards stay in the unchanged reader. Only its normal context exit, cleared held handle and final source guards may commit current state; OS CloseHandle return remains unverified. Source/peer/grant checks run before and after, and all child processes must be collected. Full OS IO and process lifetime leases are not claimed.
""")
    put('preparation-notes.json',dict(source_only=True,
      prefreeze_errors=[dict(kind='functions_Javascript_ReferenceError',detail='Source text construction referenced undeclared pos; no filesystem or Python execution occurred. Rebuilt in-memory expressions.'),
        dict(kind='new_source_initial_location',detail='Four owned new files initially written under workspace work directory by apply_patch; explicit exact-path nonrecursive Move-Item placed them in authorized project namespace before any freeze/import/test. No frozen files were altered.')],
      first_new_case_failure=False,old_programs_executed=False,game_or_config_access=False))
    for n in ['source-delta.json','budget.json','PROTOCOL.md','preparation-notes.json']:local[n]=read(HERE/n)
    for name,v in expected.items():require(read(ROOT/name,v)==pre[name],'Build source postguard')
    pins={n:pin(b) for n,b in pre.items()}
    pins[BUILD]=BUILD_PIN
    pins.update({(HERE/n).relative_to(ROOT).as_posix():pin(b) for n,b in local.items()})
    require(len(pins)<=64,'Runtime source graph bound')
    canonical=json.loads(pre['work/candidates/support-heir-current-observer-1375-v1/source-manifest.json'])
    graph=hashlib.sha256(json.dumps(canonical['source_pins'],sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
    mp=put('source-manifest.json',dict(schema='EU4-SUPPORT-HEIR-CONTROLLER-SOURCE/1',sealed=True,
      build_authorization={'path':BUILD,**BUILD_PIN},runtime_grant_required=True,native_ready=False,selected_effect_verified=False,
      fixed_inputs=grant['fixed_inputs'],source_pins=pins,candidate_source_graph_sha256=graph,
      source_graph_sha256=hashlib.sha256(json.dumps(pins,sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest(),
      stage='source frozen; new synthetic cases and independent source review pending',
      controller_or_child_main_executed=False,real_env_operations=0))
    memory_result=memory()
    prep=put('preparation.json',dict(source_manifest=mp,source_pins=len(pins),source_prepost_equal=True,
      read_events=EVENTS,prior_returned=PRIOR,returned=TOTAL,source_limit=LIMIT,memory=memory_result,
      first_run_new_cases_pending=True,actual_authorization_created=False,source_checks='AST/file-only; no controller/child/reader imported',
      native_game_calls=0,PE_reads=0,old_tests=0,config_real_operations=0))
    print(json.dumps({'source_manifest':mp,'source_pins':len(pins),'preparation':prep,'source_returned':TOTAL,'memory':memory_result},ensure_ascii=True))
if __name__=='__main__':main()
