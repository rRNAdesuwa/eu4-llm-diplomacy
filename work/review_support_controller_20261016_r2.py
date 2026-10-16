from pathlib import Path
import ast,ctypes,hashlib,json,sys,difflib
ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/support-heir-current-live-controller-20261016-r1/'
OUT=ROOT/'work/reports/support-heir-current-controller-source-independent-review-20261016-r1'
START={BASE+'source-manifest.json':{'bytes':16257,'sha256':'3d70675a5901635a00efd6415ac93ead4b4dcadc726df1a6f4f065b864bb20f7'},
 BASE+'author-manifest.json':{'bytes':13982,'sha256':'bceb0b923a5183a15b3ebd7bfd14014ec773df2088e94475c64226f9f219cd8c'},
 BASE+'delivery.json':{'bytes':3880,'sha256':'605ba540aa1125f0d009cd9cfd7fb3caaa0a6325a11cd5619c3f313638c59763'},
 BASE+'file-check.json':{'bytes':13206,'sha256':'212feaf476cf27a5f93d8dbba7233f2c775f97978d2c22e00ad2a465215b1081'}}
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def save(name,value):
 b=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode()
 with (OUT/name).open('xb') as f:f.write(b)
 return pin(b)
def memory():
 class C(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ['peakRSS','RSS','peakPaged','paged','peakNP','NP','committed','peakCommitted']]
 c=C();c.cb=ctypes.sizeof(c);g=ctypes.windll.kernel32.GetCurrentProcess;g.restype=ctypes.c_void_p
 assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(g()),ctypes.byref(c),c.cb)
 assert max(c.RSS,c.committed)<=805306368
 return {'RSS':c.RSS,'committed':c.committed,'peakRSS':c.peakRSS,'peakCommitted':c.peakCommitted}
def intake():
 OUT.mkdir(exist_ok=False);snap=OUT/'snapshots';snap.mkdir();reads=[];buffers={};locations={}
 def read(rel,p):
  assert not rel.startswith('work/deps/') and not rel.endswith('/local.env')
  path=ROOT/rel;assert path.stat().st_size<=4194304
  b=path.read_bytes();reads.append({'phase':'source_before','path':rel,**pin(b)});assert pin(b)==p,rel
  name=f'{len(locations):03d}-'+path.name
  with (snap/name).open('xb') as f:f.write(b)
  locations[rel]=(snap/name).relative_to(ROOT).as_posix();buffers[rel]=b
  assert sum(x['bytes'] for x in reads)+34119<33554432
 for rel,p in START.items():read(rel,p)
 source=json.loads(buffers[BASE+'source-manifest.json']);author=json.loads(buffers[BASE+'author-manifest.json'])
 assert len(source['source_pins'])==49
 pins={**author['file_pins'],**START}
 for rel,p in source['source_pins'].items():assert pins[rel]==p
 for rel,p in pins.items():
  if rel not in buffers:read(rel,p)
 for rel,b in buffers.items():
  if rel.endswith('.py'):ast.parse(b.decode('utf-8-sig'),filename=rel)
 save('intake.json',{'schema':'EU4-SUPPORT-CONTROLLER-INDEPENDENT-INTAKE/1','source_pins':pins,'snapshot_paths':locations,
  'source_count':49,'flat_subject_count':len(pins),'reads':reads,'explicit_before_bytes':sum(x['bytes'] for x in reads),
  'preflight_explicit_source_bytes':34119,'source_budget':33554432,'retained_budget':8388608,
  'memory':memory(),'author_code_executed':False,'old_tests_or_newcases_executed':False,'PE_engine_game_env_access':False})
 print(json.dumps({'flat':len(pins),'source':49,'before_bytes':sum(x['bytes'] for x in reads),'memory':memory()}))
def seal():
 ir=(OUT/'intake.json').read_bytes();i=json.loads(ir);owned_reads=[{'path':(OUT/'intake.json').relative_to(ROOT).as_posix(),'bytes':len(ir)}]
 def raw(rel):
  p=ROOT/i['snapshot_paths'][rel];b=p.read_bytes();owned_reads.append({'path':p.relative_to(ROOT).as_posix(),'bytes':len(b)})
  assert pin(b)==i['source_pins'][rel];return b
 def data(rel):return json.loads(raw(rel))
 def text(rel):return raw(rel).decode('utf-8-sig')
 source=data(BASE+'source-manifest.json');author=data(BASE+'author-manifest.json');delivery=data(BASE+'delivery.json')
 grant=data(source['build_authorization']['path'])
 assert source['fixed_inputs']==grant['fixed_inputs'] and source['build_authorization']=={'path':source['build_authorization']['path'],**pin(raw(source['build_authorization']['path']))}
 assert grant['source_build_only']is True and grant['runtime_authorized']is False
 old='work/reports/peace-current-pending-v2-live-controller-20261016-r2/'
 same={};changed={};delta={};texts={}
 for name in ['controller.py','child.py','runtime_contract.py']:
  a=text(old+name);b=text(BASE+name);texts[name]=b
  aa={n.name:n for n in ast.parse(a).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  bb={n.name:n for n in ast.parse(b).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  same[name]=[n for n in aa if ast.dump(aa[n],include_attributes=False)==ast.dump(bb.get(n),include_attributes=False)]
  changed[name]=[n for n in aa if n not in same[name]]
  delta[name]=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=old+name,tofile=BASE+name))
 assert sum(map(len,same.values()))==21
 assert 'game_meter_class' in same['child.py']
 a=ast.parse(text(old+'child.py'));b=ast.parse(texts['child.py'])
 fn=lambda tree,name:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 assert ast.get_source_segment(text(old+'child.py'),fn(a,'game_meter_class'))==ast.get_source_segment(texts['child.py'],fn(b,'game_meter_class'))
 assert raw(BASE+'text_config_adapter.py')==raw(old+'text_config_adapter.py')
 def literal(source_text,name):
  for n in ast.parse(source_text).body:
   if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets):return ast.literal_eval(n.value)
  raise ValueError('Missing literal '+name)
 contract=texts['runtime_contract.py'];selection=literal(contract,'SELECTION');flags=literal(contract,'FLAGS')
 assert selection==grant['selection'] and selection=={'pid':98548,'creation':'01dd5d0e670312c4','actor':'FRA','target':'POL'}
 assert "EU4-SUPPORT-HEIR-CURRENT-STATUS-ONCE/1" in contract
 assert contract.index('Future grant raw hash before parse')<contract.index('auth=decode(auth_raw)')
 assert contract.index('manifest_raw=read_reference')<contract.index('pins=manifest[')
 assert "for field in ('subject_source_manifest','subject_controller_pin','subject_child_pin','subject_adapter_pin')" in contract
 cand='work/candidates/support-heir-current-observer-1375-v1/'
 canonical=data(cand+'source-manifest.json');draft=data(cand+'draft-source-manifest.json');cli=text(cand+'support_heir_current_observer.py')
 assert canonical['source_pins']==draft['source_pins'] and len(canonical['source_pins'])==22
 graph=hashlib.sha256(json.dumps(canonical['source_pins'],sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
 assert source['candidate_source_graph_sha256']==graph
 assert set(literal(cli,'FALSE_FLAGS'))<=set(flags)
 assert set(flags)-set(literal(cli,'FALSE_FLAGS'))=={'Frida_called','automatic_retry'}
 src_review=data('work/reports/support-heir-current-observer-source-review-20261015-r1/independent-source-ready.json')
 prod=data('work/reports/support-heir-current-observer-production-review-20261015-r1/production-passed.json')
 assert src_review['status']=='SOURCE-READY' and src_review['candidate_source_ready']is True and src_review['blocking_findings']==[]
 assert src_review['subject']=={'path':cand+'support_heir_current_observer.py',**i['source_pins'][cand+'support_heir_current_observer.py']}
 assert prod['source']==i['source_pins'][cand+'support_heir_current_observer.py'] and prod['production']==i['source_pins'][cand+'source-manifest.json']
 assert prod['draft_snapshot']==i['source_pins'][cand+'draft-source-manifest.json'] and prod['unchanged_source_pins']==22
 host=data('work/candidates/frida-entry-observer-1375-v1/host-manifest.json')
 assert len(host['source_pins'])==215 and len(host['selected_external_pins'])==11
 assert sum(v['bytes'] for v in host['source_pins'].values())+sum(v['bytes'] for v in host['selected_external_pins'].values())==255828142
 cases=data(BASE+'offline-r1/cases.json');receipt=data(BASE+'offline-r1/receipt.json');job=data(BASE+'offline-r1/job.json')
 assert cases['passed']is True and cases['failure']is None and len(cases['cases'])==4
 assert all(v['passed']is True and v['runs']==1 for v in cases['cases'])
 assert cases['source_manifest']==i['source_pins'][BASE+'source-manifest.json'] and cases['source_prepost_equal']is True
 assert cases['returned']==sum(e['returned'] for e in cases['read_events'])==1080960
 assert receipt['passed']is True and receipt['failure']is None and receipt['job']==job
 assert receipt['source_returned']==sum(e['returned'] for e in receipt['read_events'])==1114334
 assert job['exit_code']==0 and job['error']is None and job['job_active_processes_final']==0 and job['direct_child_collected']is True and 1<=job['job_total_processes']<=8
 assert job['peak_job_commit']==13545472
 assert cases['synthetic_reads_add_physical_bytes']is False and cases['synthetic_contract_read_calls']==110
 assert all(cases[k]==0 for k in ['CLI_executions','PE_reads','candidate_imports','child_executions','controller_main_executions','game_process_accesses','native_game_calls','old_tests'])
 prepare=data(BASE+'preparation.json');account=data(BASE+'delivery-accounting.json');notes=data(BASE+'preparation-notes.json')
 p_events=sum(e['returned'] for e in prepare['read_events'])
 assert prepare['returned'] in (p_events,p_events+prepare['prior_returned'])
 assert prepare['returned']==1009498 and account['source_measured_before_seal']==1009498+1080960+1114334==3204792
 assert len(notes['prefreeze_errors'])==2 and notes['first_new_case_failure']is False
 assert delivery['source_cumulative_upper']==5419256<33554432 and delivery['retained_upper_including_final_transport_allowance']==1509570<8388608
 assert delivery['runtime_authorized']is False and delivery['OS_CloseHandle_return_verified']is False and delivery['entry_PE_raw_journaled']is False
 ctl=texts['controller.py']
 assert "1<=count<=3" in ctl and "count*contract.GAME_BYTES" in ctl
 assert "entry['bytes']==8192" in ctl and "entry.get('journaled')is False" in ctl
 assert "all(capture.get(k)is True" in ctl and "commit_after_context_exit" in ctl
 assert "builtins.open=METER.open;io.open=METER.open" in texts['child.py']
 assert not any(s in texts['child.py'] for s in ['Held.memory=', 'Held.memory =','ReadProcessMemory=','ReadProcessMemory ='])
 replay=save('static-replay.json',{'schema':'EU4-SUPPORT-CONTROLLER-INDEPENDENT-STATIC-REPLAY/1',
  'method':'AST/text/JSON/pin arithmetic only; no author function/module execution.',
  'helpers_exact_AST':same,'helper_count':21,'changed_top_level_functions':changed,
  'GameMeter_function_text_equal':True,'adapter_bytes_equal_accepted_R2':True,
  'new_selection':selection,'support_candidate22_unchanged':True,'candidate_source_graph':graph,
  'source_and_production_real_fields_verified':True,'new_runtime_schema':'EU4-SUPPORT-HEIR-CURRENT-STATUS-ONCE/1',
  'four_new_cases_retained':cases['cases'],'cases_reexecuted':0,'synthetic_physical_bytes':cases['returned'],
  'runner_physical_bytes':receipt['source_returned'],'synthetic_virtual_contract_read_calls':110,'virtual_reads_add_physical_bytes':False,
  'Job':job,'prep_event_returned_sum':p_events,'prep_prior_returned':prepare['prior_returned'],'prep_returned':prepare['returned'],
  'author_source_before_seal':3204792,'author_source_upper':5419256,'author_retained_upper':1509570,
  'prefreeze_error_notes':notes['prefreeze_errors'],'legacy_host_metadata':{'local':215,'external':11,'aggregate_bytes':255828142,'bodies_reopened_here':False},
  'source_line_scopes':{'controller_capture':[53,82],'config_and_game_closure':[98,116],'controller_once_and_commit':[118,185],
   'runtime_new_grant_raw_and_four_subjects':[62,102],'support_true_source_and_production_fields':[103,117],
   'CLI_current_capture_and_result':[236,295]},
  'readiness_boundary':'New controller source/retained cases only; does not authorize a process query or authenticate any self-reported current state.'})
 with (OUT/'controller-child-contract.diff').open('xb') as f:f.write('\n'.join(delta.values()).encode())
 after=[]
 for rel,expected in i['source_pins'].items():
  p=ROOT/rel;assert p.stat().st_size<=4194304
  value=p.read_bytes();assert pin(value)==expected,rel;after.append({'phase':'source_after','path':rel,**pin(value)})
 inspections=[]
 for name in ['inspection-main.json','inspection-cases.json','inspection-closure.json','inspection-reader.json','inspection-accounting.json']:
  p=OUT/name;b=p.read_bytes();owned_reads.append({'path':p.relative_to(ROOT).as_posix(),'bytes':len(b)});inspections.append(json.loads(b))
 failed_raw=(OUT/'reviewer-seal-failure-r1.json').read_bytes();failed=json.loads(failed_raw)
 owned_reads.append({'path':(OUT/'reviewer-seal-failure-r1.json').relative_to(ROOT).as_posix(),'bytes':len(failed_raw)})
 prior_review_upper=failed['failed_attempt_owned_read_upper_bytes']+failed['repair_inspection_read_bytes']
 explicit=i['explicit_before_bytes']+i['preflight_explicit_source_bytes']+sum(x['bytes'] for x in after)+sum(x['bytes'] for x in owned_reads)+sum(v['bytes'] for v in inspections)
 subjects={key:author[key] for key in ['subject_source_manifest','subject_controller_pin','subject_child_pin','subject_adapter_pin']}
 findings={'schema':'EU4-SUPPORT-HEIR-CONTROLLER-INDEPENDENT-SOURCE/1','sealed':True,'passed':True,'blocking_findings':[],
  'scope':'Complete frozen controller49flat source and retained four new synthetic cases; no runtime query.',
  'source_ready':True,'runtime_authorized':False,**subjects,
  'subject_author_manifest':{'path':BASE+'author-manifest.json',**i['source_pins'][BASE+'author-manifest.json']},
  'subject_delivery':{'path':BASE+'delivery.json',**i['source_pins'][BASE+'delivery.json']},
  'source_checks':{'source_graph_files':49,'flat_sources_and_retained':69,'source_before_after_equal':True,
   'source_and_auth_raw_pin_before_parse':True,'new_four_full_subjects_and_distinct_support_grant':True,
   'candidate_source_production_actual_fields':True,'old21_helpers_AST_equal':True,'GameMeter_unchanged':True,
   'adapter_accepted_pin_unchanged':True,'held_memory_or_RPM_methods_patched':False},
  'selected_status_and_IO':{'positive_and_negative_current_states':['selected_task_present','selected_task_absent'],
   'unknown_requires_exit2_presenceNone_no_commit':True,'observed_requires_exit0_equal_passes_noerrors_normal_context_heldNone_finalguards':True,
   'game_disk_hashes':'Validate actual1..3 complete closes and count*38462504; no added reads to force3. RuntimeCapture source invokes disk_identity once.',
   'entry_header':'Separate source declaration: one Held.memory(base,8192) invocation, no entry raw journal; shared4096/512KiB/single64KiB counts host/code/full-table/selected attempts.',
   'scope':'Current selected indexed task only; not action success, acceptance, final heir, complete class, lifetime or persistence.'},
  'retained_cases':{'count':4,'eachonce':True,'names':[v['name'] for v in cases['cases']],'reexecuted_by_reviewer':False,
   'job_exit0_active0_total2':True,'job_peak_bytes':13545472,'all_shells_collected_retained':True},
  'reviewer_failure':{'retained_pin':{'path':(OUT/'reviewer-seal-failure-r1.json').relative_to(ROOT).as_posix(),**pin(failed_raw)},'own_failed_seal_runs':1,'author_fault':False,'correction':'Candidate false flags are a subset; controller adds only Frida_called/automatic_retry, both required false.'},
  'precision_notes':['Before/after hashes and two sample equality do not prove atomicity, a world lease or exclusion of ABA.',
   'The215local/11external legacy host closure is metadata/accepted-source witness here; no large body or transitive historical graph was opened.',
   'Four synthetic cases test new grant/result/hash-count closure, not typed world or real RPM replay. Synthetic read callbacks use owned JSON and add0 physical bytes.',
   'Two pre-freeze preparation errors are retained as fixed author notes: JavaScript undeclared variable before file/execution, and explicit relocation of new unfrozen sources. Their tool/raw filesystem history is author witness, not independently replayed here; no case failed or repeated.',
   'Handle-cleared/context-exit are software observations; OS CloseHandle return remains explicitly unchecked.',
   'Old candidate_review_status pending wording is informational; actual production sealed/runtime gate and exact source/production subjects were verified.'],
  'roles':{'reviewer':'/root/war_api','author':'/root/diplomacy_static','reviewer_prior_role':'Limited peaceR2 adapter peer and other war RE author/reviewer; not author of this support controller or its four cases.'},
  'source_accounting':{'explicit_source_and_owned_bytes':explicit,'manual_own_scripts_and_finalcheck_allowance':2097152,
   'prior_review_upper_bytes':prior_review_upper,'source_upper_bytes':explicit+prior_review_upper+2097152,'source_limit':33554432,'retained_limit':8388608,'scope':'Explicit original/snapshot reviewer reads; not allOS/loader/cache IO.'},
  'source_pins':i['source_pins'],'source_after':after,'static_replay_pin':{'path':(OUT/'static-replay.json').relative_to(ROOT).as_posix(),**replay},
  'memory':memory(),'all_shells_collected':True,'author_modules_or_helpers_executed':0,'author_tests_executed':0,
  'candidate_CLI_executed':0,'PE_engine_decoder_access':0,'real_env_access':False,'PID_UI_process_access':0,
  'native_game_calls':0,'requests':0,'native_ready':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False}
 assert explicit+prior_review_upper+2097152<33554432
 findings_pin=save('findings.json',findings)
 report='''# Support-heir controller independent source review\n\nPassed with no blocking findings. All49 frozen controller source pins and69 selected source/retained files matched before and after. Twenty-one shared helpers and the entire GameMeter function retain oldR2 AST/text; adapter bytes remain the accepted b1d44aff profile. New support grant schema/four full subjects, fixed selection/config metadata and true support source/production review fields are bound before execution.\n\nSelected current states require exit0, equal complete passes, no errors, normal context exit, held-handle cleared and final guards. Unknown stays exit2/None/no commit. Actual1..3 complete intercepted disk hashes are counted rather than forcing three; the frozen RuntimeCapture source makes one disk_identity call. The8192 entry identity read is a separate source declaration, without raw journal, while shared host/code/selected RPM uses4096calls/512KiB/single64KiB. No Held or RPM method was changed.\n\nFour new retained fake cases passed once in a collected Job. This review did not run them or execute any author/controller/CLI/helper, read real config, open PE/engine bodies or access a process. The first reviewer seal failed on an overstrict equality check of false-flag sets; its exact source and stderr are retained, and the corrected check accepts only the two additional false claims. No author file or case was changed or rerun. Source readiness does not authorize live capture and does not establish task/request success, AI acceptance, final heir, class/lifetime/lease or persistence. Two pre-freeze errors remain author-note witnesses with bounded accounting; OS CloseHandle return and fullOS IO remain unverified.\n'''
 with (OUT/'report.md').open('xb') as f:f.write(report.encode())
 local={}
 for p in sorted(OUT.rglob('*')):
  if p.is_file():local[p.relative_to(ROOT).as_posix()]=pin(p.read_bytes())
 script=Path(__file__).resolve();local[script.relative_to(ROOT).as_posix()]=pin(script.read_bytes())
 retained=sum(v['bytes'] for name,v in local.items() if name.startswith(OUT.relative_to(ROOT).as_posix()+'/'))
 assert retained+131072<8388608
 manifest=save('manifest.json',{'schema':'EU4-SUPPORT-CONTROLLER-INDEPENDENT-SOURCE-MANIFEST/1','sealed':True,
  'source_pins':i['source_pins'],'local_pins':local,'findings_pin':{'path':(OUT/'findings.json').relative_to(ROOT).as_posix(),**findings_pin},
  'retained_upper_bytes':retained+131072,'runtime_authorized':False,'native_ready':False,'all_shells_collected':True})
 print(json.dumps({'findings':findings_pin,'manifest':manifest,'source_upper':explicit+prior_review_upper+2097152,'retained_upper':retained+131072,
  'all_shells_collected':True,'passed':True}))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in['intake','seal'];{'intake':intake,'seal':seal}[sys.argv[1]]()
