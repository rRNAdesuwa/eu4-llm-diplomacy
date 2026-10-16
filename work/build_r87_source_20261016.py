from pathlib import Path
import ast,ctypes,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/reports/war-peace-api-20261016-r87-dual-frontier-source'
GRANT='work/reports/war-peace-api-20261016-r87-root-source-authorization/authorization.json'
GP={'bytes':9003,'sha256':'5cae443d9a4e7250c083d7b97268e4a57d46da0d714f3cb0c0ca16fe13c75bfe'}
READS=[]
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(rel,expected=None,phase='build'):
    assert not rel.startswith('work/deps/')
    p=ROOT/rel;size=p.stat().st_size;assert 0<size<=4194304
    with p.open('rb') as f:b=f.read(size+1)
    READS.append({'path':rel,'phase':phase,**pin(b)})
    assert len(b)==size
    if expected is not None:assert pin(b)==expected,rel
    assert sum(x['bytes'] for x in READS)+36102<33554432
    return b
def save(name,value):
    b=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode()
    with (HERE/name).open('xb') as f:f.write(b)
    return pin(b)
def memory():
    class PMC(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ['peakRSS','RSS','peakPaged','paged','peakNP','NP','committed','peakCommitted']]
    c=PMC();c.cb=ctypes.sizeof(c);g=ctypes.windll.kernel32.GetCurrentProcess;g.restype=ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(g()),ctypes.byref(c),c.cb)
    assert max(c.RSS,c.committed)<805306368
    return {'RSS':c.RSS,'committed':c.committed,'peakRSS':c.peakRSS,'peakCommitted':c.peakCommitted}
grant_raw=read(GRANT,GP,'grant_before');grant=json.loads(grant_raw)
assert grant['source_build_only']is True and grant['actual_authorized']is False
assert grant['new_source_namespace']==HERE.relative_to(ROOT).as_posix()
assert grant['fixed_raw_window']=={'begin':'0xcc266','end_exclusive':'0xcc366','bytes':256,'seeds':['0xcc266','0xcc32c']}
save('source-build-claim.json',{'schema':'EU4-R87-SOURCE-BUILD-CLAIM/1','grant':{'path':GRANT,**GP},'PE_decoder_game':False,'actual_authorized':False})
fixed=dict(grant['fixed_inputs'])
for name in ['subject_plan','subject_plan_manifest']:
    ref=grant[name];fixed[ref['path']]={k:ref[k] for k in ['bytes','sha256']}
fixed[GRANT]=GP
buffers={rel:read(rel,p,'fixed_before') for rel,p in fixed.items()}
r86='work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
template=buffers[r86+'produce.py'].decode();tree=ast.parse(template)
names=['require','save','digest','charge','read_source','stream_pin','memory_guard','source_guard','raw_write_review']
nodes={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
helpers='\n\n'.join(ast.get_source_segment(template,nodes[n]) for n in names)+'\n\n'
local=lambda name:HERE.relative_to(ROOT).as_posix()+'/'+name
core=read(local('cfg_core.py'));runtime=read(local('runtime_contract.py'))
launcher=read(local('launch_once.py')).decode();assert launcher.count('__CONTRACT_PIN__')==1
with (HERE/'launch-template.py.inc').open('xb') as f:f.write(launcher.encode())
(HERE/'launch_once.py').write_text(launcher.replace('__CONTRACT_PIN__',repr(pin(runtime))),encoding='utf-8',newline='\n')
header='''"""R87 fixed dual continuation window. Source-only; no actual grant exists."""
import ctypes
from ctypes import wintypes
import hashlib,json,struct,sys,types,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ENTRY=0xcc266
R86='work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
GAME_BYTES=38462504
ANCHORS='work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'
TARGET_CONTEXT_NORMAL_EXIT=False
SOURCE_LIMIT=30*1024*1024
MEMORY_LIMIT=768*1024*1024
SOURCE_IO=[]
PHASE='authorization_preflight'
PE_READS=[]
PE_AUTH=[]
PADATA=[]
MAX_OBSERVED_COMMIT=0
'''
header+='CFG_PIN='+repr(pin(core))+'\nCONTRACT_PIN='+repr(pin(runtime))+'\n\n'
main=read(local('main-template.py.inc')).decode()
produced=(header+helpers+main).encode()
with (HERE/'produce.py').open('xb') as f:f.write(produced)
newtree=ast.parse(produced);newnodes={n.name:n for n in newtree.body if isinstance(n,ast.FunctionDef)}
reuse={}
for name in names:
    assert ast.dump(nodes[name],include_attributes=False)==ast.dump(newnodes[name],include_attributes=False)
    assert ast.get_source_segment(template,nodes[name])==ast.get_source_segment(produced.decode(),newnodes[name])
    reuse[name]={'AST_equal':True,'function_text_equal':True}
cap=json.loads(buffers[r86+'capture.json']);owned=json.loads(buffers[r86+'owned-code.json'])
assert cap['analysis']['instructions'][17]['bytes']=='0f84cd000000' and cap['analysis']['instructions'][19]['bytes']=='482bca'
save('entry-seed.json',{'schema':'EU4-R87-DUAL-FRONTIER-SEED/1','fixed_raw_window':grant['fixed_raw_window'],
    'gap_policy':grant['explicit_gap_policy_delta'],'R86_capture':{'path':r86+'capture.json',**pin(buffers[r86+'capture.json'])},
    'R86_owned':{'path':r86+'owned-code.json',**pin(buffers[r86+'owned-code.json'])},
    'branches':[{'site':'0xcc259','raw':'0f84cd000000','size':6,'signed_displacement':205,'target':'0xcc32c'},
      {'site':'0xcc263','raw':'482bca','size':3,'fallthrough':'0xcc266'}],
    'known_metadata_anchors':{str(v['index']):v for v in cap['pdata_requests'] if v['index']in[1251,1252,1253,1258]},
    'historical_inherited_context_from_plan':json.loads(buffers[grant['subject_plan']['path']])['inherited_context'],
    'seed_semantics':{'0xcc266':'normal_sequential_frontier','0xcc32c':'hypothetical_syntactic_target_not_normal_from_cc220'},
    'precision':'SAR64(value,3) has unsigned bitpattern range [0,0x0fffffffffffffff] union [0xf000000000000000,0xffffffffffffffff]; CMP with0x1fffffffffffffff cannot be equal after normal R86 sequence. cc32c state is counterfactual; raw direct JE encoding and fixed authorized window remain valid source seeds.',
    'not_independent_Win64_entry':True,'R86_full_review_pending':True,'native_ready':False})
save('budget.json',{'schema':'EU4-R87-BUDGET/1','source_stage':33554432,'producer_source':31457280,'launcher_control':2097152,
    'retained_stage':16777216,'ordinary_file':4194304,'soft_memory':805306368,'stop_memory':1073741824,
    'Job':grant['Job'],'code_physical':256,'metadata_physical_max':108,'metadata_records_fixed':list(range(1251,1260)),
    'outer_metadata_cap_records':32,'outer_metadata_cap_bytes':384,'whole_PE_sha_streams':2,'whole_PE_sha_bytes':76925008,
    'recommended_PE_total':76925372,'absolute_PE_upper':76925648,'decoder_unique_bytes':256,'decoder_input_upper':3840,
    'synthetic_parent_source':2097152,'synthetic_child_source':8388608,'new_cases':4,'eachonce':True,
    'conditional_source_estimate':21000000,'estimate_not_universal_or_OS_bound':True})
protocol='''# R87 source-only protocol\n\nOnly fixed raw[cc266,cc366)256 and explicit seeds cc266/cc32c. cc266 is the normal sequential frontier. cc32c is only a hypothetical/syntactic JE target: R86 SAR64(value,3) cannot equal0x1fffffffffffffff, so normal sequential cc220 execution does not take that JE. No dual-seed analysis proves cc32c dynamically or normally reachable. Root's later source instruction clarified this before freeze; the independent R86 full report is still pending. Exactly nine pdata records1251..1259. cc266 must be exact record1253; cc32c missing containment is diagnostic, not a reason to suppress the explicitly fixed raw capture. The gap exception is based on the direct-JE encoding and fixed raw choice, not reachability or a new function entry. Multiple coverage/order/anchor/mapping errors produce unknown0code; no search or fallback. No pdata extent selects code.\n\nR86 nine helper function AST/texts are unchanged; CFG is split into pure cfg_core.run_cfg and a Capstone serialization adapter. Attempted starts and occupied bytes are global/deduplicated. Maximum256 rows/unique bytes and3840 lookahead bytes; external branches stop only their edge, no callee is queued, CALL fallthrough is conditional, RET/INT3/partial stop without decoding data.\n\nNo actual grant exists. Future launch_once.py accepts only a new root grant SHA, verifies raw grant/manifest/source/reviews, and starts only the fixed produce.py under pinned job_tree. Producer also requires own Job membership before engine hashing, but memory limits/collected tree require the final launcher Job receipt. Child30MiB+parent2MiB enforce combined source32MiB; retained16MiB/ordinary4MiB,768MiB Job/software,1GiB stop,45s/8 cumulative process cap. Output writer may overshoot before acceptance refusal. No game process joins this Job.\n\nFuture EU4-R87-FIXED-DUAL-SEED-ROOT-AUTHORIZATION/1 fields: source_manifest/producer_pin/entry_seed_pin/cfg_core_pin/launcher_pin are exact PIN-ONLY bytes+sha. Bind fixed_raw_window, metadata, gap_policy, Job, source_limits exactly to root source-build grant, plus seed_semantics exactly to runtime_contract.SEED_SEMANTICS. operation=one-fixed-dual-frontier-static, sealed/root_explicit_start_received/single_attempt=true. Three pairs upstream_R86_full_review/root_raw_frontier_review/source_peer_review contain findings+manifest fulltriples; add upstream_R86_root_acceptance fulltriple. R86 full findings require subject_actual_manifest/subject_capture_pin/subject_contract_pin/subject_owned_pin fulltriples fixed in runtime_contract.UPSTREAM. Root acceptance requires sealed/accepted=true and exact subject_full_review/subject_actual_manifest. New raw/sourcepeer findings sealed/passed/[] must bind PIN-ONLY subject_source_manifest/subject_producer/subject_entry_seed/subject_cfg_core/subject_launcher. Raw scope=raw_dual_frontier_fixed_range_seed_only plus fixed_raw_window/gap_policy exact. No legacy grant/claim substitutes.\n\nOnly after source-manifest freeze, run_cases_once.py may execute four new predefined fake-decoder cases eachonce under exact owned Job: shared seed, interior seed, external frontier/no call following, partial tail. Fictional worklist edges do not prove R86 reachability. It imports neither producer nor Capstone, opens no PE, and touches no runtime. First failure is retained and stops without repair/retry. Source build does not authenticate R86's still-pending actual semantic report or authorize R87 actual. All API/native/ownership/effect/lease/atomic/retry flags remain false.\n'''
with (HERE/'PROTOCOL.md').open('xb') as f:f.write(protocol.encode())
save('source-delta.json',{'schema':'EU4-R87-SOURCE-DELTA/1','template':{'path':r86+'produce.py',**pin(buffers[r86+'produce.py'])},
    'helpers':reuse,'changed_functions':['cfg','main'],'new_files':['cfg_core.py','runtime_contract.py','launch_once.py','cases_child.py','run_cases_once.py'],
    'explicit_root_policy_delta':grant['explicit_gap_policy_delta'],'source_guard_AST_changed':False,'actualproducer_executed':False})
files=['produce.py','cfg_core.py','runtime_contract.py','launch_once.py','launch-template.py.inc','main-template.py.inc','cases_child.py','run_cases_once.py','entry-seed.json','budget.json','PROTOCOL.md','source-delta.json']
actual=dict(fixed)
for name in files:
    raw=read(local(name));actual[local(name)]=pin(raw)
    if name.endswith('.py') or name in ['main-template.py.inc']:
        compile(raw,str(HERE/name),'exec')  # Syntax only; no code execution or import.
actual[Path(__file__).relative_to(ROOT).as_posix()]=pin(read(Path(__file__).relative_to(ROOT).as_posix()))
oldmanifest=json.loads(buffers[r86+'source-manifest.json']);engine=oldmanifest['decoder_expected_witness_pins']
assert len(engine)==38 and len(actual)<=64
manifest=save('source-manifest.json',{'schema':'EU4-R87-FIXED-DUAL-SEED-SOURCE/1','sealed':True,
    'stage':'source_frozen_before_four_new_cases_and_peer','entry_rva':'0xcc266','entry_semantics':'Inherited fragment start, not independent Win64 function',
    'fixed_raw_window':grant['fixed_raw_window'],'source_build_authorization':{'path':GRANT,**GP},
    'actual_source_pins':actual,'source_pins':{**actual,**engine},'decoder_expected_witness_pins':engine,
    'actual_source_count':len(actual),'engine_metadata_count':38,'engine_files_opened_in_preparation':False,
    'actual_authorized':False,'native_ready':False,'callable':False,'reader_adoption_allowed':False,'selected_effect_verified':False,
    'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False})
for rel,p in fixed.items():read(rel,p,'fixed_after')
save('source-preparation.json',{'schema':'EU4-R87-SOURCE-PREPARATION/1','passed':True,'source_manifest':manifest,
    'actual_source_count':len(actual),'engine_witness_count':38,'helpers':reuse,'source_reads':READS,
    'preflight_source_bytes':36102,'explicit_source_bytes':sum(x['bytes'] for x in READS)+36102,
    'manual_and_seal_allowance_bytes':1048576,'memory':memory(),'actualproducer_or_launcher_runs':0,
    'tests_run_before_freeze':0,'PE_decoder_enginebody_game_operations':0,'all_shells_collected':True})
print(json.dumps({'source_manifest':manifest,'producer':actual[local('produce.py')],'entry_seed':actual[local('entry-seed.json')],
    'cfg_core':actual[local('cfg_core.py')],'launcher':actual[local('launch_once.py')],
    'source_explicit_bytes':sum(x['bytes'] for x in READS)+36102,'actual_sources':len(actual),'engine_metadata_only':38}))
