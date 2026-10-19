from pathlib import Path
import hashlib,json,ctypes
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/reports/war-peace-api-20261016-r87-dual-frontier-source'
EXEC=ROOT/'work/reports/war-peace-api-20261016-r87-source-build-execution'
MP={'bytes':26330,'sha256':'e40ccf4eba10b12b7d626f0fc00b1bcdac50972d1a0a35559ba3756b64694817'}
READS=[]
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(path,expected=None,phase='retained'):
    path=Path(path);rel=path.relative_to(ROOT).as_posix();assert not rel.startswith('work/deps/')
    size=path.stat().st_size;assert 0<=size<=4194304
    raw=path.read_bytes();READS.append({'phase':phase,'path':rel,**pin(raw)})
    if expected is not None:assert pin(raw)==expected,rel
    assert sum(x['bytes'] for x in READS)<=8388608
    return raw
def save(name,value):
    raw=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode()
    with (HERE/name).open('xb') as f:f.write(raw)
    return {'path':(HERE/name).relative_to(ROOT).as_posix(),**pin(raw)}
def memory():
    class C(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ['peakRSS','RSS','peakPaged','paged','peakNP','NP','committed','peakCommitted']]
    c=C();c.cb=ctypes.sizeof(c);g=ctypes.windll.kernel32.GetCurrentProcess;g.restype=ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(g()),ctypes.byref(c),c.cb)
    assert max(c.RSS,c.committed)<=805306368
    return {'RSS':c.RSS,'committed':c.committed,'peakRSS':c.peakRSS,'peakCommitted':c.peakCommitted}
save('prepared-seal-claim.json',{'schema':'EU4-R87-PREPARED-SEAL-CLAIM/1','source_manifest':MP,
 'actual_producer_or_launcher':False,'oldtests_or_new_cases_reexecuted':False})
mraw=read(HERE/'source-manifest.json',MP,'manifest_before');m=json.loads(mraw)
assert m['sealed']is True and m['actual_authorized']is False and len(m['actual_source_pins'])==32 and len(m['decoder_expected_witness_pins'])==38
assert not any((HERE/n).exists() for n in ['run-authorization.json','claim.json','capture.json','owned-code.json','launcher-claim.json'])
for rel,expected in m['actual_source_pins'].items():read(ROOT/rel,expected,'source_before')
prepare=json.loads(read(HERE/'source-preparation.json'))
cases_raw=read(HERE/'synthetic-receipt.json');cases=json.loads(cases_raw)
run_raw=read(HERE/'synthetic-run.json');run=json.loads(run_raw)
assert cases['passed']is True and len(cases['results'])==4 and all(x['passed']is True and x['runs']==1 for x in cases['results'])
assert cases['failure']is None and cases['source_manifest']==MP
assert run['passed']is True and run['source_manifest']==MP and run['all_shells_collected']is True
job=run['job'];assert job['exit_code']==0 and job['error']is None and job['job_active_processes_final']==0 and job['direct_child_collected']is True and 1<=job['job_total_processes']<=8
assert prepare['tests_run_before_freeze']==0 and prepare['actualproducer_or_launcher_runs']==0
assert all(v['AST_equal'] and v['function_text_equal'] for v in prepare['helpers'].values()) and len(prepare['helpers'])==9
assert cases['producer_or_launcher_main_runs']==cases['Capstone_imports']==cases['PE_game_native_operations']==0
assert run['actualproducer_or_launcher_runs']==run['PE_decoder_game_native_operations']==0
summary=save('source-report.json',{'schema':'EU4-R87-SOURCE-AUTHOR-REPORT/1','sealed':True,'author_report':True,
 'independent_source_ready':False,'source_manifest':{'path':(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),**MP},
 'fixed_raw_window':m['fixed_raw_window'],'metadata_records':list(range(1251,1260)),
 'cc32c_gap_allowed_only_for_exact_syntactic_seed':True,'cc266_exact1253_required':True,
 'seed_semantics':{'0xcc266':'normal_sequential_frontier','0xcc32c':'hypothetical_syntactic_target_not_normal_from_cc220'},
 'semantic_precision':'SAR64(value,3) result cannot equal0x1fffffffffffffff; no normal cc220 reachability claim for cc32c. This source incorporates root clarification before freeze; R86 original remains unchanged.',
 'nine_helpers_exact_text_AST':prepare['helpers'],'new_cases_first_run':{'results':cases['results'],'receipt_pin':pin(cases_raw),'job_receipt_pin':pin(run_raw),'job':job},
 'normal_function_boundary_or_ABI_or_lifetime_proved':False,'future_actual_gates':['R86 full independent review','root R86 acceptance','new raw-frontier review','new complete source peer','new once authorization'],
 'actualproducer_or_launcher_executed':False,'engine_body_opened':False,'PE_open_stat_hash':False,'game_process_native_operations':0,
 'native_ready':False,'callable':False,'reader_adoption_allowed':False,'selected_effect_verified':False,
 'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False,'all_shells_collected':True})
for rel,expected in m['actual_source_pins'].items():read(ROOT/rel,expected,'source_after')
assert pin(read(HERE/'source-manifest.json',MP,'manifest_after'))==MP
source_stage_base=prepare['explicit_source_bytes']+run['source_bytes']+cases['source_bytes']
own=sum(x['bytes'] for x in READS)
account=save('prepared-accounting.json',{'schema':'EU4-R87-PREPARED-ACCOUNTING/1','source_build_explicit':prepare['explicit_source_bytes'],
 'synthetic_parent_source_explicit':run['source_bytes'],'synthetic_child_source_explicit':cases['source_bytes'],
 'seal_explicit_source_reads':READS,'seal_explicit_bytes':own,'combined_explicit_before_finalcheck':source_stage_base+own,
 'manual_scripts_logs_pin_and_finalcheck_allowance':2097152,'combined_source_upper':source_stage_base+own+2097152,
 'source_stage_limit':33554432,'retained_stage_limit':16777216,'ordinary_source_limit':4194304,
 'decoder_engine_body_target_IO':0,'OS_loader_IO_not_complete':True,'memory':memory(),'all_shells_collected':True})
assert source_stage_base+own+2097152<33554432
local={}
for p in sorted(HERE.iterdir()):
    if p.is_file():local[p.relative_to(ROOT).as_posix()]=pin(read(p,phase='pin_closed_local'))
for name in ['build.stdout.txt','build.stderr.txt','cases.stdout.txt','cases.stderr.txt']:
    p=EXEC/name;local[p.relative_to(ROOT).as_posix()]=pin(read(p,phase='pin_closed_execution_log'))
script=Path(__file__).resolve();local[script.relative_to(ROOT).as_posix()]=pin(read(script,phase='pin_sealer'))
flat={**m['actual_source_pins'],**local}
author=save('author-manifest.json',{'schema':'EU4-R87-SOURCE-AUTHOR-MANIFEST/1','sealed':True,'source_build_only':True,
 'independent_source_ready':False,'source_manifest':{'path':(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),**MP},
 'flat_source_and_retained_pins':flat,'flat_pin_count':len(flat),'actual_source_count':32,
 'decoder_expected_witness_pins':m['decoder_expected_witness_pins'],'decoder_metadata_only_count':38,
 'source_report':summary,'prepared_accounting':account,'new_cases_receipt':{'path':(HERE/'synthetic-receipt.json').relative_to(ROOT).as_posix(),**pin(cases_raw)},
 'new_cases_job_receipt':{'path':(HERE/'synthetic-run.json').relative_to(ROOT).as_posix(),**pin(run_raw)},
 'retained_bytes_at_seal':sum(p['bytes'] for rel,p in local.items() if rel.startswith(HERE.relative_to(ROOT).as_posix()+'/')),
 'retained_writes_and_later_metadata_allowance':1048576,'retained_limit':16777216,
 'role':{'author':'/root/war_api','root_grant_and_future_acceptance':'/root','future_full_source_peer':'non-author pending'},
 'native_ready':False,'actual_authorized':False,'callable':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,
 'all_shells_collected':True,'active_seal_stdout_stderr_deliberately_excluded_until_closed':True})
delivery=save('prepared-delivery.json',{'schema':'EU4-R87-PREPARED-SOURCE-DELIVERY/1','sealed':True,'author_manifest':author,
 'source_manifest':{'path':(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),**MP},
 'producer':{'path':(HERE/'produce.py').relative_to(ROOT).as_posix(),**m['actual_source_pins'][(HERE/'produce.py').relative_to(ROOT).as_posix()]},
 'entry_seed':{'path':(HERE/'entry-seed.json').relative_to(ROOT).as_posix(),**m['actual_source_pins'][(HERE/'entry-seed.json').relative_to(ROOT).as_posix()]},
 'cfg_core':{'path':(HERE/'cfg_core.py').relative_to(ROOT).as_posix(),**m['actual_source_pins'][(HERE/'cfg_core.py').relative_to(ROOT).as_posix()]},
 'launcher':{'path':(HERE/'launch_once.py').relative_to(ROOT).as_posix(),**m['actual_source_pins'][(HERE/'launch_once.py').relative_to(ROOT).as_posix()]},
 'source_report':summary,'accounting':account,'first_final_filecheck_pending':True,'independent_source_ready':False,
 'actual_authorized':False,'native_ready':False,'world_lease':False,'all_shells_collected':True})
print(json.dumps({'author_manifest':author,'delivery':delivery,'source_combined_upper':source_stage_base+own+2097152,
 'seal_pin_read_bytes_extra':sum(x['bytes'] for x in READS)-own,'all_shells_collected':True}))
