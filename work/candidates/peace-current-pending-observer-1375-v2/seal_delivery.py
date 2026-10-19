"""Retained files only, first author delivery seal; no test/query reruns."""
from pathlib import Path
import ast, ctypes, hashlib, json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
READS=0
EVENTS=[]
LIMIT=16*1024*1024
class Memory(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('peakws','ws','peakpaged','paged','peaknonpaged','nonpaged','pagefile','peakpagefile','private')]
def guard_memory():
 k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p
 p.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong];p.GetProcessMemoryInfo.restype=ctypes.c_int
 v=Memory();v.cb=ctypes.sizeof(v);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(v),v.cb)
 assert v.private<768*1024*1024 and v.private<1024*1024*1024;return v.private
def read(path):
 global READS
 guard_memory()
 n=path.stat().st_size;assert 0<=n<=4194304 and READS+n<=LIMIT
 b=path.read_bytes();assert len(b)==n;READS+=n;EVENTS.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=n));return b
def bp(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(path):return bp(read(path))
def save(name,v):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(v,f,ensure_ascii=True,sort_keys=True,indent=2);f.write('\n')
def main():
 save('delivery-claim.json',dict(operation='retained_only_first_author_seal',rerun_tests=False,rerun_queries=False,game_access=0))
 source_raw=read(HERE/'source-manifest.json');source=json.loads(source_raw)
 assert read(HERE/'source-manifest.draft.json')==source_raw and source['sealed'] is False and source['runtime_capture_authorized'] is False
 source_pre={n:pin(ROOT/n) for n in source['source_pins']};assert source_pre==source['source_pins']
 prep=json.loads(read(HERE/'preparation.json'));result=json.loads(read(HERE/'offline-r1/receipt.json'))
 assert result['status'] in ('offline_passed','offline_failed_no_retry') and result['new_fake_methods']==6
 passed=result['status']=='offline_passed'
 assert (len(result['operations'])==3 if passed else len(result['operations'])==2)
 assert result['all_direct_children_collected'] is True and result['all_jobs_active_zero'] is True
 assert result['source_manifest']==bp(source_raw)
 delta=json.loads(read(HERE/'source-delta.json'));assert delta['changed_definitions']==['verify_sources','base_result','observe']
 old=read(ROOT/'work/candidates/peace-current-pending-observer-1375-v1/peace_current_pending.py');new=read(HERE/'peace_current_pending.py')
 def defs(raw):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 a,b=defs(old),defs(new);assert [n for n in a if a[n]!=b[n]]==delta['changed_definitions']
 cases={}
 for name in ('minus-one-absent','one-absent','one-present','scalar-change','short-scalar','structural-refusal'):
  raw=read(HERE/'offline-r1'/('fake-'+name+'.json'));d=json.loads(raw)
  cases[name]=dict(pin=bp(raw),status=d['status'],presence=d['selected_queue_presence'],committed=d['commit_after_context_exit'],scalar_samples=[s['unclassified_scalar'] for s in d['samples']],rpm_budget=d['rpm_budget'],errors=d['errors'])
 save('report.json',dict(schema='EU4-PEACE-V2-AUTHOR-SOURCE-READY/1',stage='source_and_first_offline_complete_pending_non_author_review' if passed else 'source_and_six_fakes_complete_first_check_budget_refused',
  sealed_source=True,passed_first_offline=passed,independent_review='pending',production_review='pending',runtime_status_authorized=False,
  subject_cli_pin=source_pre[HERE.relative_to(ROOT).as_posix()+'/peace_current_pending.py'],subject_source_graph_sha256=source['source_graph_sha256'],
  subject_draft_manifest=bp(source_raw),source_delta=delta,fake_cases=cases,
  first_check_catalog='each once passed, genuine unchanged verifier paths under frozen Job; no status' if passed else 'first check returned unknown from read-meter ordinary pre-read budget; catalog never attempted; no automatic retry',
  first_offline_receipt=bp(read(HERE/'offline-r1/receipt.json')),new_fake_methods_passed=6,first_check_exit_code=result['operations'][1]['job']['exit_code'],
  ordinary_batch_bytes=result['explicit_new_read_bytes'],delegated_fixed_host_streamed_bytes=result['delegated_fixed_host_streamed_bytes'],
  accounting_scope='Explicit reads, not total OS/cache/import IO; attempted requested/returned counters separately retained per child',
  scope='Selected current peace queue under exact code/layout/structural guards, not all Mod compatibility',
  unknowns=['global233e064 semantic meaning','live v2 current queue state','original request/AI acceptance/rejection','terms/settlement/completion','class/lifetime/atomicity/persistence'],
  authority=dict(native_ready=False,callable=False,selected_effect_verified=False,peace_completed=False,original_request_correlated=False,world_lease=False,atomic_snapshot=False,authorizes_retry=False),
  old_tests_run=0,game_access=0,PE_target_reads=0,native_game_calls=0,requests_published=0))
 report='''v2 源码及六个新fake完成，候选仍禁止真实status。\n\n六个新fake全部通过。首次check在文件读预算前置检查返回unknown/exit2；catalog未执行，批次停止且没有重试。两个Job均active=0、direct child已收齐。冻结direct来源链另外反复整读既有约4.04MB和1.84MB反汇编JSON，未包含在最初host215+11流式估算里；实际普通读取尚未越64MiB，但下一次原read(16MiB+1)的保守预留不够。该拒绝来自新离线meter，不是已发现的candidate语义/来源错误。不能把本批次称全部通过；后续文件验证需另定有限范围。没有真实status、游戏/PE读取、旧31方法或原请求重发。\n\n唯一采样变化是将233e064的未证signed -1条件改为相同共享4B读取和每遍raw/i32/u32诊断；两遍完整样本相等覆盖此字段。稳定-1与1都可在其它结构检查成立时得到当前队列结果；1→2、短读和tombstone仍unknown。23个既有函数/类AST保持，源与结果schema版本元数据变为2。\n\n旧host215+11固定文件hash闭包单独流式计账，不运行其Frida/main，也不把这些二进制文件hash当游戏访问。本次只完成三遍host哈希，实际767,484,426B=3×255,828,142B；原八遍2,046,625,136B只是计划，不冒称已读。精确requested/returned/EOF/refusal、source前后、Job和fake raw日志见offline-r1。\n\n字段语义、通用Mod兼容及真实v2队列仍unknown。所有原请求效果、AI接受/拒绝、议和完成、native/lease/atomic/persistence权限false；v1历史不修改，原48/44/42和稳定15profiles保持。\n'''
 with (HERE/'report.md').open('x',encoding='utf-8',newline='\n') as f:f.write(report)
 # Flat local artifacts only; do not recurse through historical source graphs.
 selected=['peace_current_pending.py','test_peace_current_pending.py','README.md','prepare_sources.py','build_manifest.py','run_offline.py','offline_child.py',
  'source-delta.json','source-construction.json','budget.json','source-manifest.draft.json','build-claim.json','preparation.json',
  'seal_delivery.py','delivery-claim.json','report.json','report.md']
 selected += [p.relative_to(HERE).as_posix() for p in sorted((HERE/'offline-r1').iterdir()) if p.is_file()]
 for n in ('build-stdout.txt','build-stderr.txt','offline-stdout.txt','offline-stderr.txt','authoring-diagnostics.json'):
  if (HERE/n).exists():selected.append(n)
 local={n:pin(HERE/n) for n in selected}
 owner=dict(schema='EU4-PEACE-V2-AUTHOR-MANIFEST/1',sealed=True,source_ready=passed,six_new_fakes_passed=True,independent_review='pending',production_authorized=False,
  source_pins=source_pre,local_pins=local,canonical_manifest_at_freeze=bp(source_raw),
  canonical_manifest_snapshot='source-manifest.draft.json',closure_scope='Local new artifacts plus direct candidate source graph; delegated215+11 witnessed by first file commands, not recursively rehashed here')
 save('author-manifest.json',owner)
 for n,p in source_pre.items():assert pin(ROOT/n)==p
 for n,p in local.items():assert pin(HERE/n)==p
 assert read(HERE/'source-manifest.json')==source_raw
 save('filecheck.json',dict(schema='EU4-PEACE-V2-AUTHOR-FILECHECK/1',passed=True,source_pins_checked=len(source_pre),local_pins_checked=len(local),
  subject_author_manifest=pin(HERE/'author-manifest.json'),source_prepost_equal=True,all_direct_children_collected=True,all_jobs_active_zero=True,
  no_test_or_query_rerun=True,game_access=0,native_game_calls=0))
 # Includes prior measured build reads and a conservative manual/source-edit reserve.
 manual_reserve=2*1024*1024
 upper=prep['explicit_read_bytes_before_preparation_write']+READS+manual_reserve+256*1024
 assert upper<32*1024*1024
 save('delivery-read-accounting.json',dict(explicit_retained_reads=READS,events=EVENTS,retained_limit=LIMIT,
  measured_build_before_preparation_write=prep['explicit_read_bytes_before_preparation_write'],manual_source_edit_reserve=manual_reserve,
  final_delivery_reserve=256*1024,build_plus_seal_upper=upper,build_plus_seal_limit=32*1024*1024,
  separate_batch=result['explicit_new_read_bytes'],separate_delegated=result['delegated_fixed_host_streamed_bytes'],all_OS_IO_claimed=False,software_private_bytes=guard_memory()))
 roots={n:pin(HERE/n) for n in ('author-manifest.json','report.json','report.md','filecheck.json','delivery-read-accounting.json','source-manifest.draft.json','peace_current_pending.py','test_peace_current_pending.py','offline-r1/receipt.json')}
 save('delivery.json',dict(schema='EU4-PEACE-V2-SOURCE-DELIVERY/1',sealed=True,stage='pending_independent_source_review' if passed else 'retained_first_check_budget_refusal_no_retry',roots=roots,
  runtime_status_authorized=False,game_access=0,native_game_calls=0,all_child_jobs_collected=True))
 print(json.dumps(dict(status='source_ready_pending_independent_review' if passed else 'retained_source_six_fakes_and_first_check_refusal',roots=roots,delivery=pin(HERE/'delivery.json'),explicit_retained_read_bytes=READS,build_plus_seal_upper=upper),ensure_ascii=True))
if __name__=='__main__':main()
