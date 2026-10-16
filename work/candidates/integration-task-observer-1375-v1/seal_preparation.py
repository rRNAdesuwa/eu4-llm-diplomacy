"""File-only delivery evidence seal. Does not alter or authorize the draft."""
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
def save(n,v):
 with (HERE/n).open('x',encoding='utf-8',newline='\n') as f:json.dump(v,f,indent=2);f.write('\n')
def main():
 if sys.argv[1:]==['--check']:
  m=load(HERE/'delivery-manifest.json')
  for n,p in m['file_pins'].items():assert pin(ROOT/n)==p,n
  print(json.dumps(dict(status='file_only_delivery_pins_pass',pins=len(m['file_pins']),candidate_runtime_authorized=False,
   tests_run=0,CLI_queries_run=0,process_accesses=0)));return
 assert sys.argv[1:]==[]
 m=load(HERE/'source-manifest.json');assert m['sealed'] is False and m['runtime_capture_authorized'] is False
 for n,p in m['source_pins'].items():assert pin(ROOT/n)==p,n
 r=load(HERE/'offline-r1/receipt.json');assert r['status']=='offline_passed' and r['source_pins']==r['source_post_pins']
 for n,p in r['source_pins'].items():assert pin(HERE/n)==p,n
 assert [x['operation'] for x in r['operations']]==['new_fake_suite','check','catalog']
 ops=[]
 for x in r['operations']:
  j=x['job'];assert x['passed'] is True and x['source_unchanged'] is True and j['exit_code']==0 and j['error'] is None
  assert j['job_active_processes_final']==0 and j['direct_child_collected'] is True and j['memory_limit']==768*1024*1024
  assert pin(HERE/'offline-r1'/str(x['operation']+'-stdout.txt'))==x['stdout']
  assert pin(HERE/'offline-r1'/str(x['operation']+'-stderr.txt'))==x['stderr']
  ops.append(dict(operation=x['operation'],exit_code=j['exit_code'],job_total_processes=j['job_total_processes'],
   job_active_processes_final=0,peak_process_commit=j['peak_process_commit'],peak_job_commit=j['peak_job_commit'],
   seconds=j['seconds'],direct_child_collected=True))
 methods=sorted(n.name for n in ast.walk(ast.parse(read(HERE/'test_integration_task_observer.py')))
  if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
 assert len(methods)==24 and b'Ran 24 tests in 0.192s' in read(HERE/'offline-r1/new_fake_suite-stderr.txt')
 for name in ('check','catalog'):
  value=load(HERE/'offline-r1'/str(name+'-stdout.txt'))
  assert value['operation']==name and value['status']=='files_verified' and value['requests_published']==0 and value['native_game_calls']==0
  assert value['source_graph']['candidate']['manifest']==pin(HERE/'source-manifest.json')
 pre=load(HERE/'preparation-failure-r1/receipt.json')
 for n,p in pre['source_pins'].items():assert pin(HERE/'preparation-failure-r1'/n)==p
 old=read(HERE/'preparation-failure-r1/integration_task_observer.py').decode('utf-8')
 repaired=old.replace("  for n in (prefix+'contract.json',prefix+'owned-code.json'):",
  "  static_pins=static['file_pins'] if prefix==R44 else static['source_pins']\n  for n in (prefix+'contract.json',prefix+'owned-code.json'):")
 repaired=repaired.replace("static['source_pins'][n]","static_pins[n]").replace("static['source_pins'][R46+'slot.json']","static_pins[R46+'slot.json']")
 assert repaired.encode('utf-8')==read(HERE/'integration_task_observer.py'),'Only scoped R44 field adaptation allowed'
 value=dict(schema='EU4-INTEGRATION-TASK-PREPARATION/1',status='source_and_first_offline_ready_for_independent_review',
  candidate_source_manifest=pin(HERE/'source-manifest.json'),candidate_sealed=False,runtime_capture_authorized=False,
  independent_candidate_review='pending',static_independent_reviews=m['independent_reviews'],
  source_pins=r['source_pins'],test_method_count=24,test_method_names=methods,unit_test_seconds=0.192,
  operations=ops,offline_receipt=pin(HERE/'offline-r1/receipt.json'),
  pretest_failure=dict(receipt=pin(HERE/'preparation-failure-r1/receipt.json'),
   reason=pre['failure'],scope='file-only build self-check, before test/CLI check/catalog/process',
   precise_source_delta_verified=True,old_preimages_preserved=True,old_tests_run=0),
  current_only=True,loaded_profile=dict(per_pass_bytes=2376,both_passes_bytes=4752,blocks=4,
   relocated_slot=True,executed_native_functions=0),
  shared_read_budget=dict(calls=4096,bytes=524288,entry_PE_identity_bytes_separate=8192),
  native_ready=False,selected_effect_verified=False,action_mapping_verified=False,lifetime_lease=False,
  atomic_snapshot=False,persistence_verified=False,new_runtime_profiles_promoted=0,
  actual_status_captures=0,game_process_accesses=0,PE_binary_reads=0,Frida_calls=0,native_game_calls=0,
  requests_published=0,old_suites_run=0,all_started_shells_collected=True,
  compact_runner_peak_alias='Console summary used absent peak_job_memory alias; exact peak_job_commit values above come from preserved raw Job receipts')
 save('preparation.json',value)
 report='''# Integration current-status 候选准备结果

独立 current pair 工具已实现，仍是拒绝实采的draft。源清单21 pins，R44/R45/R46静态合同与两份独立静态审查均固定；候选自身待独立审查，`sealed=false` / `runtime_capture_authorized=false`。没有修改stable/native/已有reader或晋升运行时profile。

24个本模块新fake方法首次全过（0.192s）；check/catalog各首次一次通过。三个Job各45s/768MiB，均exit0、active0、child collected；peak job committed依次36,782,080 / 32,051,200 / 32,083,968 B。测试与文件查询前后源相同，没有旧套件、实际status、进程访问、PE二进制读取、REA/Frida/native调用或新请求。

首次build的文件自检发现R44清单使用`file_pins`而非R45/R46的`source_pins`。失败在任何新test/check/catalog前；6份精确前像与exit1回执保留在`preparation-failure-r1/`。仅修这一固定格式分支；file-only交付检查重放差异证明没有其他源码变更。修后草稿构建成功，随后才首次跑上述测试和两个CLI查询，没有重跑旧结果。

观察状态为`selected_task_present`、`selected_index_absent`或unknown；两侧同P、vtable1c816d8、完整端点及P28零才能presence。其他vtable/单侧/removed/端点错误都unknown，不视为absence。P8不要求357，P20只输出raw u32。冻结relation核root=country+14f8、row完整pair和country+1510映射，root+200索引capacity/unique等是额外reader guard。

loaded guard四块每轮2376B，前后共4752B（2259+103+relocated slot8+leaf6）；完整1380表每遍fresh。host/code/table/selected统一4096calls/512KiB预算并保存ordered raw journal；冻结RuntimeCapture的入口8192B PE身份读取另列。正常with关闭、held.handleNone和最后source guard全部完成才commit；只读nonce不当安装session。

source/test/README草稿已稳定供独审。纯文件复核`python -B work/candidates/integration-task-observer-1375-v1/seal_preparation.py --check`，只查交付pin、不重新运行测试或CLI。`delivery-manifest.json`封的是准备材料完整性，不是生产授权。所有native/effect/mapping/lifetime/atomic/persistence权限保持false。
'''
 with (HERE/'report.md').open('x',encoding='utf-8',newline='\n') as f:f.write(report)
 pins=dict(m['source_pins'])
 extras=['source-manifest.json','preparation.json','report.md','seal_preparation.py']
 extras += ['preparation-failure-r1/'+n for n in list(pre['source_pins'])+['receipt.json']]
 extras += ['offline-r1/'+n for n in ['claim.json','receipt.json']+
   [op+'-'+suffix for op in ('new_fake_suite','check','catalog') for suffix in ('stdout.txt','stderr.txt','receipt.json')]]
 for n in extras:pins[(HERE/n).relative_to(ROOT).as_posix()]=pin(HERE/n)
 save('delivery-manifest.json',dict(schema='EU4-INTEGRATION-TASK-PREPARATION-DELIVERY/1',file_pins=pins,
  integrity_sealed=True,candidate_runtime_authorized=False,independent_review_pending=True,native_ready=False))
 print(json.dumps(dict(preparation=pin(HERE/'preparation.json'),delivery_manifest=pin(HERE/'delivery-manifest.json'),
  report=pin(HERE/'report.md'),pins=len(pins),process_accesses=0,tests_run=0,CLI_queries_run=0)))
if __name__=='__main__':main()
