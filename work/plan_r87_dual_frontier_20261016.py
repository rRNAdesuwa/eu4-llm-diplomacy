from pathlib import Path
import ast
import ctypes
import hashlib
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r87-dual-frontier-source-plan'
R86='work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
SEALED=R86+'actual-sealed-r1/'
PINS={
 R86+'produce.py':{'bytes':27099,'sha256':'0a3c13e779e4da424316b0e3a3ff3f86f49a460243f18b14c91644ca717522b4'},
 R86+'source-manifest.json':{'bytes':22473,'sha256':'74f6c8f8eeeadea9e4216c7b37e2a8034e9fb7967d8dfe7167c7ee1ffd143472'},
 R86+'capture.json':{'bytes':85315,'sha256':'e3a06664b11a14f483705cd3ae4852b0cd562a85ab46ac7395bfc428673bb28f'},
 R86+'owned-code.json':{'bytes':635,'sha256':'65d0c63efdc37f369bb8aa4f0f55a0a5c3d59c79db8bc37e98723a30048fde82'},
 SEALED+'contract.json':{'bytes':5478,'sha256':'ddea250f47187a4b6b47075186a2ca54c09157168b3b2db9d016b3a5b81e5943'},
 SEALED+'selected-cfg.json':{'bytes':15248,'sha256':'d8126c5c08e73e84c3f12df83fe84abe55eccf43f45e976cf2c9cbe54c8f47ab'},
 SEALED+'actual-manifest.json':{'bytes':16602,'sha256':'69e7167005ff08e09ca29e790786f6055512614debecc72f31d3b37d0583df72'},
 R86+'entry-seed.json':{'bytes':5917,'sha256':'905f9599f13f637a93950d61f29bdbccbea3e839c4776fb260f0dcfcdef9dc09'},
 R86+'budget.json':{'bytes':1035,'sha256':'3b22397c57457a13f2c25fecd08eb540f8b9ec0afee87151b5673b254b8736e7'},
 'work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json':{'bytes':12398,'sha256':'0d10e6676653d92a440fe14259729719219e2c1c008a114da42df1d92287b94e'},
 'work/candidates/frida-entry-observer-1375-v1/job_tree.py':{'bytes':8615,'sha256':'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'},
 'work/reports/war-peace-api-20261016-r86-source-independent-review/findings.json':{'bytes':4081,'sha256':'075c2b62c093453b838957669c1872d3a14c20e39a073e13df32ca05d411e2ef'},
 'work/reports/war-peace-api-20261016-r86-source-independent-review/manifest.json':{'bytes':23017,'sha256':'4d16d2851e7796c516c435d504838d4cb93fb1a571a4707fb3c178680a952dc4'},
 'work/reports/war-peace-api-20261016-r86-root-raw-entry-review/findings.json':{'bytes':2606,'sha256':'88e3e3300e041bb3bf48acdccb38e2f6e4e9cbcc502bd629e5d94c5e49c02878'},
 'work/reports/war-peace-api-20261016-r86-root-raw-entry-review/manifest.json':{'bytes':4110,'sha256':'08079d699f8fe50752af7307adb803592178982d937839d958e7571600b341d1'},
 SEALED+'filecheck.json':{'bytes':9951,'sha256':'1510e66afd2daec1c1073e1e40bec775d23d3c73ed043008c3f0b566d4da1b10'},
}
READS=[]
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def ref(path):return {'path':path,**PINS[path]}
def read(path,expected,phase):
 p=ROOT/path
 assert not path.startswith('work/deps/') and p.stat().st_size<=4194304
 raw=p.read_bytes();READS.append({'phase':phase,'path':path,**pin(raw)})
 assert pin(raw)==expected,path
 assert sum(x['bytes'] for x in READS)+49807<8388608
 return raw
def save(name,value):
 b=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode()
 with (OUT/name).open('xb') as f:f.write(b)
 return {'path':(OUT/name).relative_to(ROOT).as_posix(),**pin(b)}
def memory():
 class PMC(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ['peakRSS','RSS','peakPaged','paged','peakNonPaged','nonPaged','committed','peakCommitted']]
 q=PMC();q.cb=ctypes.sizeof(q);get=ctypes.windll.kernel32.GetCurrentProcess;get.restype=ctypes.c_void_p
 assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get()),ctypes.byref(q),q.cb)
 assert max(q.RSS,q.committed)<805306368
 return {'RSS':q.RSS,'committed':q.committed,'peakRSS':q.peakRSS,'peakCommitted':q.peakCommitted}

OUT.mkdir(exist_ok=False)
save('plan-claim.json',{'schema':'EU4-R87-SOURCE-PLAN-CLAIM/1','proposal_only':True,'producer_modified':False,
 'PE_stat_open_hash':False,'decoder_import':False,'actual_claim':False,'preflight_source_bytes':49807})
B={p:read(p,v,'before') for p,v in PINS.items()}
capture=json.loads(B[R86+'capture.json']);owned=json.loads(B[R86+'owned-code.json'])
source=json.loads(B[R86+'source-manifest.json']);contract=json.loads(B[SEALED+'contract.json'])
raw=bytes.fromhex(owned['raw_hex']);rows=capture['analysis']['instructions']
assert raw==bytes.fromhex(''.join(r['bytes'] for r in rows)) and len(raw)==70
assert rows[-1]['rva']=='0xcc263' and rows[-1]['bytes']=='482bca'
branch=next(r for r in rows if r['rva']=='0xcc259');assert branch['bytes']=='0f84cd000000'
assert 0xcc259+6+struct.unpack('<i',bytes.fromhex(branch['bytes'])[2:])[0]==0xcc32c
assert 0xcc263+len(bytes.fromhex(rows[-1]['bytes']))==0xcc266
observed={r['index']:r for r in capture['pdata_requests']}
assert observed[1253]['raw_hex']=='66c20c008cc20c0028dddc01'
assert observed[1258]['raw_hex']=='32c30c0038c30c0090dddc01'
assert int(observed[1253]['begin_rva'],16)<=0xcc32c<int(observed[1258]['begin_rva'],16)
cached=json.loads(B['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'])
sections=cached['sections'];text=next(s for s in sections if s['name']=='.text');pdata=next(s for s in sections if s['name']=='.pdata')
def mapping(rva,size,section):
 assert int(section['rva'],16)<=rva and rva+size<=int(section['rva'],16)+section['raw_size']
 return section['raw_file_offset']+rva-int(section['rva'],16)
span=(0xcc266,0xcc366);seeds=[0xcc266,0xcc32c]
assert span[1]-span[0]==256 and seeds[1]-span[0]==198
file_offset=mapping(span[0],256,text)
metadata=[{'index':i,'rva':hex(int(pdata['rva'],16)+12*i),
 'file_offset':mapping(int(pdata['rva'],16)+12*i,12,pdata),'bytes':12} for i in range(1251,1260)]
tree=ast.parse(B[R86+'produce.py'])
helpers={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
cfg=ast.get_source_segment(B[R86+'produce.py'].decode(),helpers['cfg'])
assert 'queue=[begin]' in cfg and 'end=begin+len(raw)' in cfg and 'if jump:' in cfg
unchanged=[n for n in helpers if n not in ['cfg','main']]
assert unchanged==['require','save','digest','charge','read_source','stream_pin','memory_guard','source_guard','raw_write_review']
job=B['work/candidates/frida-entry-observer-1375-v1/job_tree.py'].decode()
assert 'creationflags=0x00000004 | subprocess.CREATE_NO_WINDOW' in job and 'limits.ProcessMemoryLimit = limits.JobMemoryLimit = memory_limit' in job
assert 'kernel.AssignProcessToJobObject' in job and 'direct_child_collected=child is not None' in job
false={name:False for name in ['actual_authorized','source_build_authorized','native_ready','callable','reader_adoption_allowed',
 'ownership_transfer_verified','class_verified','world_lease','atomic_snapshot','selected_effect_verified','authorizes_retry']}
plan={
 'schema':'EU4-R87-DUAL-FRONTIER-SOURCE-PLAN/1','sealed':True,'proposal_only':True,
 'roles':{'proposal_author':'/root/war_api','upstream_R86_source_and_report_author':'/root/war_api',
  'upstream_R86_actual_executor':'/root','R86_actual_full_non_author_review':'pending; not accepted by this proposal'},
 'source_pins':PINS,'upstream_actual_capture':ref(R86+'capture.json'),'upstream_owned':ref(R86+'owned-code.json'),
 'upstream_author_contract':ref(SEALED+'contract.json'),'template_producer':ref(R86+'produce.py'),
 'source_template_review':ref('work/reports/war-peace-api-20261016-r86-source-independent-review/findings.json'),
 'branch_seed_evidence':{'cc32c':{'source':ref(R86+'capture.json'),'json_pointer':'/analysis/instructions/17',
   'site':'0xcc259','raw_hex':'0f84cd000000','next':'0xcc25f','signed_disp32':205,'target':'0xcc32c'},
  'cc266':{'source':ref(R86+'capture.json'),'json_pointer':'/analysis/instructions/19',
   'site':'0xcc263','raw_hex':'482bca','size':3,'fallthrough':'0xcc266'}},
 'recommended_window':{'kind':'one_explicit_raw_window','rva_begin':'0xcc266','rva_end_exclusive':'0xcc366',
  'physical_code_bytes':256,'cached_file_offset':file_offset,'explicit_decode_seeds':['0xcc266','0xcc32c'],
  'seed_offsets':[0,198],'bytes_after_second_seed':58,'new_metadata_max_records':32,'new_metadata_max_bytes':384,
  'not_a_function_extent':True,'not_proven_sufficient_for_normal_closure':True},
 'smaller_union_comparison':{'ranges':[['0xcc266','0xcc28c'],['0xcc32c','0xcc366']],
  'physical_code_bytes':96,'saving_vs256':160,'reason_not_recommended':'It covers both entry addresses but limits the first frontier to the cached38B descriptor. No retained successor code proves that38B sufficient. Choosing it because of pdata would improperly privilege a function-extent interpretation; it is a valid alternative only as another intentionally truncated plan.',
  'neither_choice_closes_behavior_in_advance':True},
 'metadata_validation_proposal':{'mode':'fixed_nine_records_then_seed_containment; no whole-table scan or fallback',
  'cached_sections_source':ref('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'),
  'cached_text_section':text,'cached_pdata_section':pdata,'exact_new_records':metadata,
  'physical_records':9,'physical_bytes':108,'why_fixed_fence':'R86 fixed records1253.begin=cc266 and1258.begin=cc332 bracket cc32c; new1251..1259 contains all possible predecessor records and immediate neighbors for both explicit seeds if ordering holds.',
  'known_anchors':{str(i):observed[i] for i in [1251,1252,1253,1258]},
  'required_checks':['Exact 12B uint32 begin/end/unwind fields; section raw bounds and fixed record index.',
   'Known1251/1252/1253/1258 raw anchors match retained R86 bytes; all selected records positive span, ascending begin and nonoverlap.',
   'Locate a unique containing record for each seed from this fixed fence; cc266 is expected exactbegin but cc32c must not be required exactbegin.',
   'If containing/ordering/raw mapping fails or a seed lies in a pdata gap: unknown0code under this recommended fail-closed proposal, no search, substitute record, different window or automatic fallback.',
   'Do not read unwind addresses or derive raw-window bounds from any pdata extent.'],
  'gap_policy_requires_explicit_root_acceptance':'This plan recommends gap-not-allowed/unknown0code. A future grant allowing raw seed-gap capture would be a separate explicit policy delta, not inherited from R80/R86.'},
 'decoder_proposal':{'initial_queue':['0xcc266','0xcc32c'],'code_row_cap':256,'unique_instruction_bytes_cap':256,
  'max_lookahead_per_attempt':15,'decoder_input_upper_bytes':3840,'decoder_input_is_not_physical_PE_bytes':True,
  'rules':['Decode only from the two explicit initial seeds and machine fallthrough/direct jump targets inside the fixed window; never from pdata starts or raw unused bytes.',
   'Global occupied byte map plus row-start map deduplicates both seed traversals and internal edges. Existing exact row-start is shared; interior target/overlap records unknown rather than decoding another stream.',
   'External/indirect jumps immediately record an unresolved edge and do not extend the window. A conditional jump may still explore its in-window fallthrough as a separate path.',
   'No callee is queued even if a CALL target is inside the raw window. Its normal-return fallthrough, if retained, is explicitly conditional on the unknown callee returning; no preserved volatile register or alias guarantee is added.',
   'Stop at RET/INT3/UD2/unmodelled terminal or partial tail. Do not decode RET+1 or enqueue data labels.',
   'RIP operands/indirect virtual slots are symbolic records only; no data, literal, vtable, header, unwind or other code is read.'],
  'raw_range_is_not_executed_instruction_coverage':True},
 'inherited_context':{'symbols':'C=R86 incoming RCX,D=incoming RDX,E=incoming R8,Q=R86 callee entryRSP; A/B/V are instruction-time M64[C+8]/M64[C]/M64[C+10]. Validity/alias conditions remain upstream conditional facts, not formals.',
  'common':{'RSP':'Q-0x48','RBX':'C','R15':'D','R13':'E','RDX':'B','RBP':'SAR64((D-B) mod2^64,3)','RAX':'SAR64((A-B) mod2^64,3)','R8':'0x1fffffffffffffff'},
  'cc32c_taken':{'RCX':'C','condition':'RAX equals0x1fffffffffffffff','flags':'CMP equal: ZF1,CF0,SF0,OF0,PF1,AF0'},
  'cc266_unequal':{'RCX':'(V-B) mod2^64','condition':'RAX differs from0x1fffffffffffffff','flags':'From final SUB RCX,RDX; cannot inherit CMP flags or assign constants without V/B.'},
  'opaque_state':'R9/R10/R11/XMM inherited without accesses in R86 selected slice, but initial values unknown. No fabricated C++ entry frame, new ABI or allocator state. No assumption that C/payload is disjoint from four PUSH destinations.'},
 'template_delta_required':{'existing_R86_can_express_plan':False,
  'existing_limits':['cfg(raw,begin,cs) initializes queue=[begin] and represents one extent.',
   'main demands an exact ENTRY pdata begin then reads that selected extent (or2048 prefix); target_read requires rva==ENTRY.',
   'R86 capture hard_Job_installed=false; source memory guard cannot meet a new hard-Job requirement alone.'],
  'new_schema_design_only':['EU4-R87-FIXED-DUAL-SEED-SOURCE/1','EU4-R87-FIXED-DUAL-SEED-ROOT-AUTHORIZATION/1','EU4-R87-FIXED-DUAL-SEED-CAPTURE/1'],
  'new_source_changes':['Replace cfg only with a two-explicit-seed, one-fixed-window traversal/occupancy schema and strict256unique-byte/row bound.',
   'Replace the selected-entry extent acquisition branch with fixed nine-record validation plus a single exact256B .text read; containing checks are diagnostic guards, never window selection.',
   'Bind fixed range, two seeds, fixed metadata indices/gap policy, identities and budgets in a new grant and source-peer subjects.',
   'Add a separate reviewed once launcher for the fixed Python child under the exact job_tree helper; do not modify the frozen helper or any R86 producer.'],
  'nine_other_helpers_reuse_candidates':unchanged,
  'source_guard_requirement':'Keep authorized single raw manifest buffer length/SHA before parse/engine, two base-pin calls and original outer current-pin checks; all source/engine/EXE postguards precede publish after normal target close.',
  'no_source_or_producer_was_modified_here':True},
 'future_hard_job_proposal':{'template':ref('work/candidates/frida-entry-observer-1375-v1/job_tree.py'),
  'helper':'run_cli_tree','memory_limit':805306368,'timeout_seconds':45,'hard_active_processes':8,'cumulative_processes_max':8,
  'stdout_stderr_acceptance_each':2097152,'receipt_acceptance':['exit0','errornull','job_active_processes_final0','direct_child_collectedtrue','1<=job_total_processes<=8','all output files closed and pinned'],
  'implementation_witness':'Existing helper creates suspended/no-window child, assigns exact owned Job before resume, sets process/Job memory limits and kill-on-close, waits/cleans exact child tree.',
  'limitations':['New launcher/source integration not implemented or reviewed yet.', 'The helper output writer may overshoot before refusal; no universal allOS or hard walltime claim.',
   'Only new own analysis child tree is assigned; no game process, existing PID, UI or runtime observer is touched.']},
 'future_budget':{'source_explicit_cap':33554432,'retained_cap':16777216,'ordinary_file_cap':4194304,
  'software_memory':805306368,'stop_memory':1073741824,'hard_Job_memory':805306368,
  'whole_EXE_hash_streams':2,'whole_EXE_hash_bytes':76925008,'code_raw_bytes_max':256,
  'metadata_limit_records':32,'metadata_limit_bytes':384,'recommended_metadata_records':9,'recommended_metadata_bytes':108,
  'recommended_PE_total':76925372,'outer_allowed_PE_upper':76925648,
  'decoder_unique_bytes':256,'decoder_input_upper':3840,'game_process_native_requests_tests':0,
  'estimate':'R86 producer source witness16,772,282B plus new reviewed launcher/small source delta is expected below32MiB; must recompute the concrete new flatgraph/prepost read plan before run. This is not a universal source/OS bound.',
  'root_previous_reads_not_added_to_this_plan_account':True},
 'future_gates':['R86 actual full non-author review with exact accepted capture/owned/contract/manifests; currently absent/pending.',
  'New root raw seed/range/fence review binding both R86 frontiers.',
  'New complete non-author source/CFG/metadata/launcher/hardJob review; single-seed R86 review does not cover this delta.',
  'New root exact once authorization after all new subject pins. No implicit reuse of R86 onceclaim or grant.'],
 **false}
plan_ref=save('plan.json',plan)
report='''# R87 dual-frontier source-only plan\n\nRecommend one explicit raw window [cc266,cc366),256B, with only cc266 and cc32c as initial decode seeds. It covers both proven R86 exits (second seed offset198,58 bytes left) without interpreting pdata as a function boundary. A96B union of [cc266,cc28c) and [cc32c,cc366) saves160B, but no retained bytes show the first38B sufficient; neither choice guarantees normal closure.\n\nThe existing R86 producer cannot express this plan: its CFG has queue=[begin], and main chooses an exact-entry pdata extent. New fixed-window/two-seed schemas plus a small, reviewed CFG/main delta are required. Nine other helpers can remain exact AST/text copies. A separate reviewed launcher must add the hard Job: R86 itself only recorded a software memory guard.\n\nA concrete bounded metadata proposal reads exactly indices1251..1259 (9records/108B), anchored by retained1253.begincc266 and1258.begincc332. It validates unique containing records/neighbors for both seeds without a table search or fallback. cc32c must not require exactbegin. Gap/invalid metadata is recommended unknown0code; allowing a gap needs an explicit different root policy. No raw range is derived from these extents.\n\nOnly machine-reachable in-window paths are decoded; overlap is deduplicated, external edges become unknown immediately, no callee/data/vtable/header/unwind is followed and RET tails are left undecoded. Incoming state is conditional R86 fragment state, not independent Win64 formals.\n\nThis is a War-authored proposal using the War-authored R86 report; R86 full actual non-author review is still pending. No producer was changed or run, and no PE/decoder/process/native/old test was accessed. New source review and root once authorization remain required before any R87 actual work.\n'''
with (OUT/'report.md').open('xb') as f:f.write(report.encode())
for p,v in PINS.items():read(p,v,'after')
actual=sum(x['bytes'] for x in READS)+49807
account=save('read-accounting.json',{'schema':'EU4-R87-PLAN-READ-ACCOUNTING/1','reads':READS,
 'preflight_explicit_bytes':49807,'explicit_source_bytes':actual,'manual_script_and_finalcheck_allowance':524288,
 'source_upper':actual+524288,'source_limit':8388608,'retained_limit':2097152,'memory':memory(),
 'PE_engine_decoder_game_reads':0,'wholeOS_IO_claim':False,'all_shells_collected':True})
local={p.relative_to(ROOT).as_posix():pin(p.read_bytes()) for p in OUT.iterdir() if p.is_file()}
script=Path(__file__).resolve();local[script.relative_to(ROOT).as_posix()]=pin(script.read_bytes())
manifest=save('manifest.json',{'schema':'EU4-R87-SOURCE-PLAN-MANIFEST/1','sealed':True,'proposal_only':True,
 'plan':plan_ref,'source_pins':PINS,'local_pins':local,'source_count':16,'accounting':account,
 'retained_upper':sum(v['bytes'] for v in local.values())+65536,**false})
print(json.dumps({'plan':plan_ref,'manifest':manifest,'source_explicit':actual,'source_upper':actual+524288,
 'source_files':16,'all_shells_collected':True,'no_PE_or_decoder_or_producer':True}))
