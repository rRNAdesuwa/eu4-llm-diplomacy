"""File-only initial preparation receipts. Never imports the observer or runs tests."""
import ast
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def read(p):
 with p.open('rb') as f:b=f.read(4*1024*1024+1)
 assert len(b)<=4*1024*1024;return b

def pin(p):
 b=read(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

def load(p):return json.loads(read(p))

def save(name,value):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def path(name):
 p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and p!=ROOT.parent/'eu4.exe';return p

def main():
 if sys.argv[1:]==['--check']:
  m=load(HERE/'delivery-manifest.json')
  for n,p in m['file_pins'].items():assert pin(path(n))==p,n
  print(json.dumps(dict(status='file_only_delivery_pins_pass',pins=len(m['file_pins']),
   candidate_runtime_authorized=False,tests_run=0,CLI_queries_run=0,PE_reads=0,game_process_accesses=0)))
  return
 assert sys.argv[1:]==[]
 m=load(HERE/'source-manifest.json');assert m['sealed'] is False and m['runtime_capture_authorized'] is False
 for n,p in m['source_pins'].items():assert pin(path(n))==p,n
 r=load(HERE/'offline-r1/receipt.json');assert r['status']=='offline_passed' and r['source_pins']==r['source_post_pins']
 for n,p in r['source_pins'].items():assert pin(HERE/n)==p,n
 assert [x['operation'] for x in r['operations']]==['new_fake_suite','check','catalog']
 ops=[]
 for x in r['operations']:
  j=x['job'];assert x['passed'] is True and x['source_unchanged'] is True and j['exit_code']==0 and j['error'] is None
  assert j['job_active_processes_final']==0 and j['direct_child_collected'] is True and j['memory_limit']==768*1024*1024
  assert pin(HERE/'offline-r1'/str(x['operation']+'-stdout.txt'))==x['stdout']
  assert pin(HERE/'offline-r1'/str(x['operation']+'-stderr.txt'))==x['stderr']
  ops.append(dict(operation=x['operation'],exit_code=0,job_total_processes=j['job_total_processes'],
   job_active_processes_final=0,peak_process_commit=j['peak_process_commit'],peak_job_commit=j['peak_job_commit'],
   seconds=j['seconds'],direct_child_collected=True))
 tests=ast.parse(read(HERE/'test_support_heir_current_observer.py'))
 names=sorted(n.name for n in ast.walk(tests) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
 assert len(names)==15 and b'Ran 15 tests in 0.140s' in read(HERE/'offline-r1/new_fake_suite-stderr.txt')
 for name in ('check','catalog'):
  value=load(HERE/'offline-r1'/str(name+'-stdout.txt'))
  assert value['operation']==name and value['status']=='files_verified' and value['errors']==[]
  assert value['requests_published']==value['native_game_calls']==0
  assert value['source_graph']['candidate']['manifest']==pin(HERE/'source-manifest.json')
  assert value['source_graph']['candidate']['sealed'] is False
  assert value['source_graph']['candidate']['runtime_capture_authorized'] is False
 # Verify selected copied shared code through AST only; no imported RuntimeCapture.
 old=ROOT/'work/candidates/integration-task-observer-1375-v1/integration_task_observer.py'
 oldtree=ast.parse(read(old));newtree=ast.parse(read(HERE/'support_heir_current_observer.py'))
 nodes=lambda tree:{n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 left,right=nodes(oldtree),nodes(newtree)
 unchanged=['require','read','pin','local_path','json_file','selection','JournalPort','SharedView','host_sample_shared']
 for n in unchanged:assert ast.dump(left[n])==ast.dump(right[n]),n
 class DescriptionOnly(ast.NodeTransformer):
  def visit_Constant(self,node):
   if isinstance(node.value,str):node.value=node.value.replace('loaded code/slot before/after','loaded code before/after')
   return node
 assert ast.dump(DescriptionOnly().visit(left['observe']))==ast.dump(right['observe'])
 oldtests=ast.parse(read(ROOT/'work/candidates/integration-task-observer-1375-v1/test_integration_task_observer.py'))
 oldnames={n.name for n in ast.walk(oldtests) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
 assert not oldnames.intersection(names)
 snapshot=HERE/'draft-source-manifest.json'
 with snapshot.open('xb') as f:f.write(read(HERE/'source-manifest.json'))
 assert pin(snapshot)==pin(HERE/'source-manifest.json')
 preparation=dict(schema='EU4-SUPPORT-HEIR-CURRENT-PREPARATION/1',status='source_and_first_offline_ready_for_independent_review',
  draft_snapshot=dict(path=snapshot.relative_to(ROOT).as_posix(),**pin(snapshot)),canonical_manifest_at_preparation=pin(HERE/'source-manifest.json'),
  candidate_sealed=False,runtime_capture_authorized=False,independent_candidate_review='pending',
  static_independent_reviews=m['static_independent_reviews'],source_pins=r['source_pins'],
  unchanged_shared_AST_nodes=unchanged,observe_AST_equal_except_budget_description=True,
  test_method_count=15,test_method_names=names,unit_test_seconds=0.140,old_test_method_names_not_copied=True,
  operations=ops,offline_receipt=pin(HERE/'offline-r1/receipt.json'),
  loaded_profile=dict(blocks=2,per_pass_bytes=4308,pre_post_bytes=8616,
   ranges=[dict(rva='0x595120',bytes=4244),dict(rva='0xa69ab0',bytes=64)],functions_executed=0),
  selected_layout=dict(index_root_offset='0x140',native_count_offset='0x14c',extra_capacity_offset='0x148',stride=16,
   zero_values_allowed=True,zero_pair_means='selected_task_absent under profile; key presence remains separate',
   task_read_bytes=64,profile_vtable_rva='0x1c7c1c8',raw_u32_08_guard=357,raw_byte_28_guard=0,
   endpoints='unlabeled complete handle set',native_getter_has_type_or_removed_guard=False),
  shared_budget=dict(calls=4096,bytes=524288,separate_entry_PE_identity_read_bytes=8192),
  preparation_shell=dict(build_chunk='3b0694',build_exit_code=0,offline_chunk='2530bc',offline_exit_code=0,
   offline_shell_seconds=6.3178464,all_started_shells_collected=True),
  game_process_accesses=0,actual_status_captures=0,PE_binary_reads=0,native_game_calls=0,Frida_calls=0,
  old_suites_run=0,requests_published=0,new_runtime_profiles_promoted=0,
  native_ready=False,selected_effect_verified=False,native_action_mapping_verified=False,
  lifetime_lease=False,atomic_snapshot=False,persistence_verified=False)
 save('preparation.json',preparation)
 pins=dict(m['source_pins'])
 extras=['draft-source-manifest.json','preparation.json','report.md','seal_preparation.py']
 extras+=['offline-r1/'+n for n in ['claim.json','receipt.json']+
  [op+'-'+suffix for op in ('new_fake_suite','check','catalog') for suffix in ('stdout.txt','stderr.txt','receipt.json')]]
 for n in extras:pins[(HERE/n).relative_to(ROOT).as_posix()]=pin(HERE/n)
 save('delivery-manifest.json',dict(schema='EU4-SUPPORT-HEIR-CURRENT-PREPARATION-DELIVERY/1',file_pins=pins,
  integrity_sealed=True,candidate_runtime_authorized=False,independent_review_pending=True,native_ready=False,
  canonical_manifest_note='Preparation pins use exact draft snapshot; a later separately reviewed root production metadata seal is not part of this receipt.'))
 print(json.dumps(dict(preparation=pin(HERE/'preparation.json'),delivery_manifest=pin(HERE/'delivery-manifest.json'),
  report=pin(HERE/'report.md'),draft_snapshot=pin(snapshot),pins=len(pins),PE_reads=0,tests_run=0,CLI_queries_run=0)))

if __name__=='__main__':main()
