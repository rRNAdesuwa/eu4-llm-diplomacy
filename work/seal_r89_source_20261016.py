from pathlib import Path
import ast,ctypes,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/war-peace-api-20261016-r89-c9d60-source/'
OUT=ROOT/BASE
READS=[]
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(relative,expected=None):
 path=ROOT/relative;assert 0<=path.stat().st_size<=4194304
 raw=path.read_bytes();value=pin(raw);READS.append({'path':relative,**value})
 assert sum(v['bytes']for v in READS)<33554432
 if expected is not None:assert value==expected,relative
 return raw
def save(name,value):
 raw=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode()
 with(OUT/name).open('xb')as f:f.write(raw)
 return {'path':BASE+name,**pin(raw)}
def memory():
 class C(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in ['peakRSS','RSS','peakPaged','paged','peakNP','NP','committed','peakCommitted']]
 c=C();c.cb=ctypes.sizeof(c);g=ctypes.windll.kernel32.GetCurrentProcess;g.restype=ctypes.c_void_p
 assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(g()),ctypes.byref(c),c.cb)
 assert max(c.RSS,c.committed)<=805306368
 return {'RSS':c.RSS,'commit':c.committed,'peakRSS':c.peakRSS,'peakCommit':c.peakCommitted}
def seal():
 source_raw=read(BASE+'source-manifest.json',{'bytes':29452,'sha256':'208d34192f5aed513bcf0586c607eb6a4397a59693575d0014745ee48780d8fd'})
 source=json.loads(source_raw);actual=source['actual_source_pins'];owned={}
 assert source['sealed']is True and source['actual_authorized']is False and len(actual)==38
 assert len(source['decoder_expected_witness_pins'])==38
 assert not any((OUT/n).exists()for n in ['claim.json','capture.json','owned-code.json','launcher-claim.json','run-authorization.json','failure.json'])
 for relative,p in actual.items():owned[relative]=read(relative,p)
 source_graph_before={n:pin(b)for n,b in owned.items()}
 def owned_json(relative):return json.loads(owned[relative])
 prep=json.loads(read(BASE+'source-preparation.json'))
 cases_raw=read(BASE+'cases.json');cases=json.loads(cases_raw)
 runner_raw=read(BASE+'cases-run.json');runner=json.loads(runner_raw)
 stderr=read(BASE+'cases.stderr.txt');stdout=read(BASE+'cases.stdout.txt')
 read(BASE+'cases-run-claim.json');read(BASE+'cases-claim.json')
 assert cases['passed']is True and cases['failure']is None and len(cases['cases'])==4
 assert all(v['passed']is True and v['runs']==1 for v in cases['cases'])
 assert cases['source_manifest']==pin(source_raw) and cases['source_prepost_equal']is True
 assert cases['source_bytes']==sum(v['bytes']for v in cases['source_reads'])
 assert runner['passed']is True and runner['failure']is None and runner['all_shells_collected']is True
 assert runner['source_manifest']==pin(source_raw) and runner['child_source_bytes']==cases['source_bytes']
 assert runner['runner_source_bytes']==sum(v['bytes']for v in runner['runner_source_reads'])
 job=runner['Job'];assert job['exit_code']==0 and job['error']is None and job['job_active_processes_final']==0
 assert job['direct_child_collected']is True and 1<=job['job_total_processes']<=8
 assert job['memory_limit']==805306368 and not stderr and json.loads(stdout)['passed']is True
 assert all(cases[k]==0 for k in ['Capstone_imports','PE_reads','producer_main_executions','old_cases_or_tests','game_process_accesses','native_game_calls'])
 parent='work/reports/war-peace-api-20261016-r87-root-actual-acceptance/'
 acceptance_raw=read(parent+'findings.json',{'bytes':1439,'sha256':'c8d6d6512c997855716564e2ab98ae3eca92562fd4469621fdd0956a752c5f0c'})
 acceptance_receipt_raw=read(parent+'receipt.json',{'bytes':4384,'sha256':'ce5f62e43a5197e8d7af4cc1671fc37776b209026dd0e74fa78f94a829a850e4'})
 acceptance=json.loads(acceptance_raw);assert acceptance['sealed']is True and acceptance['accepted']is True
 assembled=json.loads(read(BASE+'assembled-inputs.json'))
 assert acceptance['subject_full_review']==assembled['upstream_review_pair']['findings']
 assert acceptance['subject_actual_manifest']==assembled['upstream_subjects']['subject_actual_manifest']
 new_producer=owned[BASE+'produce.py'].decode();old_producer=owned['work/reports/war-peace-api-20261016-r87-dual-frontier-source/produce.py'].decode()
 def functions(text):return {n.name:(n,ast.get_source_segment(text,n))for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
 old=functions(old_producer);new=functions(new_producer)
 helpers=['require','save','digest','charge','read_source','stream_pin','memory_guard','source_guard','raw_write_review']
 for name in helpers:
  assert new[name][1]==old[name][1] and ast.dump(new[name][0],include_attributes=False)==ast.dump(old[name][0],include_attributes=False)
 runtime=owned[BASE+'runtime_contract.py'].decode()
 assert runtime.index('Authorized manifest buffer before parse')<runtime.index('manifest=decode(manifest_raw)')
 assert "'EU4-R89-C9D60-FIXED-PREFIX-ROOT-AUTHORIZATION/1'"in runtime
 assert "'subject_metadata_core':auth['metadata_core_pin']"in runtime
 assert "acceptance.get('subject_full_review')==upstream_findings"in runtime
 assert new_producer.count('base,pins=source_guard(base_pin)')==1 and new_producer.count('_,post=source_guard(base_pin)')==1
 assert "target.read(256)"in new_producer and 'extent<=8192'not in new_producer and 'else 2048'not in new_producer
 component_files={'subject_source_manifest':'source-manifest.json','subject_producer':'produce.py','subject_entry_seed':'entry-seed.json',
  'subject_cfg_core':'cfg_core.py','subject_metadata_core':'metadata_core.py','subject_launcher':'launch_once.py'}
 subjects={key:pin(source_raw)if file=='source-manifest.json'else actual[BASE+file] for key,file in component_files.items()}
 paths={key:{'path':BASE+file,**subjects[key]}for key,file in component_files.items()}
 def virtual_metadata_bytes(value):
  if isinstance(value,dict):return sum(len(bytes.fromhex(v['raw_hex']))for v in value.get('callback_reads',[]))+sum(virtual_metadata_bytes(v)for k,v in value.items()if k!='callback_reads')
  return sum(virtual_metadata_bytes(v)for v in value)if isinstance(value,list)else 0
 virtual=virtual_metadata_bytes(cases['cases'])
 verification=save('source-verification.json',{'schema':'EU4-R89-AUTHOR-SOURCE-VERIFICATION/1','nine_helper_names':helpers,'nine_helper_text_AST_equal':True,
  'source_manifest_raw_buffer_before_parse':True,'two_base_pin_source_guards_and_outer_checks':True,
  'fixed_window_not_extent_chosen':source['fixed_raw_window'],'diagnostic29plus3_policy':source['metadata_policy'],
  'upstream_R87_five_real_subjects':assembled['upstream_subjects'],'upstream_full_review':assembled['upstream_review_pair'],
  'root_acceptance_extra_after_source_freeze':{'path':parent+'findings.json',**pin(acceptance_raw)},
  'root_acceptance_binding':'Future exact once-grant must pin this reference; existing frozen runtime requires accepted/sealed and exact dd62 full-findings/71e7 actual-manifest subjects. Canonical source/cases were not changed after this acceptance arrived.',
  'six_new_peer_subjects_PIN_ONLY':subjects,'six_full_path_references':paths,
  'new_case_names':[v['name']for v in cases['cases']],'new_cases_runs':1,'new_case_count':4,
  'new_synthetic_metadata_returned_bytes':virtual,'synthetic_callback_physical_IO':0,
  'case_Job':job,'old_cases_reexecuted':0,'actual_producer_or_launcher_executed':0,
  'PE_engine_decoder_game_access':0,'author_is_not_source_peer':True,'native_ready':False,'all_shells_collected':True})
 before={v['path']:{k:v[k]for k in ('bytes','sha256')}for v in READS}
 after=[]
 for relative,p in before.items():
  raw=read(relative,p);after.append({'path':relative,**pin(raw)})
 assert all(actual[n]==pin(owned[n])for n in actual)
 case_source=cases['source_bytes']+runner['runner_source_bytes']
 source_upper=prep['source_upper']+case_source+sum(v['bytes']for v in READS)+4194304
 assert source_upper<33554432
 accounting=save('final-accounting.json',{'schema':'EU4-R89-AUTHOR-SOURCE-ACCOUNTING/1','prepared_source_upper':prep['source_upper'],
  'new_case_child_source':cases['source_bytes'],'new_case_controller_source':runner['runner_source_bytes'],
  'new_case_physical_combined':case_source,'seal_current_source_reads':READS,'seal_current_source_bytes':sum(v['bytes']for v in READS),
  'sealer_and_first_filecheck_manual_allowance':4194304,'combined_source_upper':source_upper,'source_limit':33554432,
  'retained_limit':16777216,'source_before_after_equal':True,'engine38_metadata_only':True,
  'no_OS_loader_complete_IO_claim':True,'unexpected_source_or_case_failures':0,'memory':memory()})
 file_pins={}
 for path in sorted(OUT.rglob('*')):
  if path.is_file():file_pins[path.relative_to(ROOT).as_posix()]=pin(path.read_bytes())
 own=Path(__file__).resolve();file_pins[own.relative_to(ROOT).as_posix()]=pin(own.read_bytes())
 for relative,p in before.items():file_pins[relative]=p
 retained=sum(v['bytes']for n,v in file_pins.items()if n.startswith(BASE))
 retained_upper=retained+262144;assert retained_upper<16777216
 manifest=save('author-manifest.json',{'schema':'EU4-R89-AUTHOR-SOURCE-AND-FOUR-CASES/1','sealed':True,
  **subjects,'subject_path_references':paths,'subject_canonical_source_manifest':paths['subject_source_manifest'],
  'file_pins':file_pins,'actual_source_graph':actual,'engine_metadata_witness_pins':source['decoder_expected_witness_pins'],
  'source_verification_pin':verification,'accounting_pin':accounting,'source_upper':source_upper,'retained_upper':retained_upper,
  'source_peer_ready_claimed_by_author':False,'source_peer_required':True,'actual_authorized':False,'native_ready':False,
  'ownership_transfer_verified':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False,
  'old_tests_or_cases':0,'PE_engine_decoder_game_access':0,'all_shells_collected':True})
 delivery=save('prepared-delivery.json',{'schema':'EU4-R89-PREPARED-DELIVERY/1','sealed':True,'author_manifest_pin':manifest,
  'source_manifest_pin':paths['subject_source_manifest'],'six_subjects_PIN_ONLY':subjects,'subject_path_references':paths,
  'case_receipt_pin':{'path':BASE+'cases-run.json',**pin(runner_raw)},'new_cases_pin':{'path':BASE+'cases.json',**pin(cases_raw)},
  'source_verification_pin':verification,'accounting_pin':accounting,'source_upper':source_upper,'retained_upper':retained_upper,
  'actual_authorized':False,'independent_source_review_pending':True,'native_ready':False,'all_shells_collected':True})
 print(json.dumps({'author_manifest':manifest,'delivery':delivery,'verification':verification,'accounting':accounting,
  'subjects':paths,'source_upper':source_upper,'retained_upper':retained_upper,'case_Job':job,'virtual_metadata_bytes':virtual,'all_shells_collected':True}))
def check():
 manifest_raw=read(BASE+'author-manifest.json');manifest=json.loads(manifest_raw)
 for relative,p in manifest['file_pins'].items():read(relative,p)
 source_raw=read(BASE+'source-manifest.json',manifest['subject_source_manifest'])
 source=json.loads(source_raw);assert source['actual_source_pins']==manifest['actual_source_graph']
 assert manifest['actual_authorized']is False and manifest['source_peer_ready_claimed_by_author']is False
 delivery_raw=read(BASE+'prepared-delivery.json');delivery=json.loads(delivery_raw)
 assert delivery['author_manifest_pin']=={'path':BASE+'author-manifest.json',**pin(manifest_raw)}
 total=sum(v['bytes']for v in READS);assert total<4194304
 verified=save('prepared-filecheck.json',{'schema':'EU4-R89-AUTHOR-FIRST-FILECHECK/1','sealed':True,'passed':True,
  'author_manifest_pin':delivery['author_manifest_pin'],'checked_file_pins':len(manifest['file_pins']),
  'read_journal':READS,'read_bytes':total,'charge':'Within retained sealer firstcheck4MiB allowance.',
  'PE_engine_decoder_game_access':0,'new_tests_reexecuted':0,'actual_authorized':False,'native_ready':False,'all_shells_collected':True,'memory':memory()})
 publication=save('publication.json',{'schema':'EU4-R89-AUTHOR-PREPARED-PUBLICATION/1','sealed':True,
  'author_manifest_pin':delivery['author_manifest_pin'],'prepared_delivery_pin':{'path':BASE+'prepared-delivery.json',**pin(delivery_raw)},
  'first_filecheck_pin':verified,'source_upper':manifest['source_upper'],'retained_upper':manifest['retained_upper'],
  'source_peer_required':True,'actual_authorized':False,'native_ready':False,'all_shells_collected':True})
 print(json.dumps({'filecheck':verified,'publication':publication,'read_bytes':total,'all_shells_collected':True}))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in['seal','check'];{'seal':seal,'check':check}[sys.argv[1]]()
