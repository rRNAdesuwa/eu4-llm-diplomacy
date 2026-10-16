"""Retained file-only seal; never invokes a lookup CLI or any historic producer."""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v4-first-queries-20261016-r1'
SOURCE_PIN=dict(bytes=16303,sha256='65760adaec1a818d8cefa1b29dafd42ca77bd04202e5c8bf00100aa477fcf97e')
RECEIPT_PIN=dict(bytes=52483,sha256='6d84cdb7171a68dbfcee59ab6f27c1fa16f416f8bef4f36e9afbb1fb1bb755ff')
MAX_FILE=4*1024*1024;BUDGET=24*1024*1024;MEMORY=768*1024*1024
reads=[];cache={};peak=0;prior_upper=8511217
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in
 ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
 peak=max(peak,x.PrivateUsage,x.PeakPagefileUsage,x.WorkingSetSize,x.PeakWorkingSetSize);assert peak<=MEMORY
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def rel(p):return p.relative_to(ROOT).as_posix()
def read(p,expected=None):
 guard();s=p.stat();assert s.st_size<=MAX_FILE
 assert prior_upper+sum(v['bytes'] for v in reads)+s.st_size<=BUDGET
 b=p.read_bytes();z=p.stat();assert (s.st_size,s.st_mtime_ns)==(z.st_size,z.st_mtime_ns) and len(b)==s.st_size
 if expected is not None:assert pin(b)==expected,(rel(p),'pin changed')
 reads.append(dict(path=rel(p),**pin(b)));cache[rel(p)]=b;return b
def write(n,j):
 b=(json.dumps(j,ensure_ascii=True,indent=2,sort_keys=True)+'\n').encode()
 with (HERE/n).open('xb') as f:f.write(b)
 return pin(b)
def pointer(j,s):
 for token in s.split('/')[1:]:
  token=token.replace('~1','/').replace('~0','~');j=j[int(token)] if type(j) is list else j[token]
 return j
def main():
 write('seal-claim.json',dict(single_attempt=True,scope='file_only_seal',source_manifest=SOURCE_PIN,
  queries_executed_here=0,source_budget=BUDGET,query_batch_accounting_separate=True))
 try:
  source=json.loads(read(HERE/'source-manifest.json',SOURCE_PIN))
  for name,expected in source['files'].items():read(ROOT/name,expected)
  dm=json.loads(cache[rel(HERE/'data-manifest.json')]);idx=json.loads(cache[rel(HERE/'index.json')])
  oldpath='work/candidates/war-peace-api-lookup-1375-v3/'
  oldidx=json.loads(cache[oldpath+'index.json']);olddm=json.loads(cache[oldpath+'data-manifest.json'])
  byid={r['id']:r for r in idx['entries']};oldids={r['id'] for r in oldidx['entries']}
  assert len(idx['entries'])==58 and len(oldids)==54 and len(dm['sources'])==59
  assert all(byid[r['id']]==r for r in oldidx['entries'])
  assert all(dm['sources'][name]==v for name,v in olddm['sources'].items())
  added=[r for r in idx['entries'] if r['id'] not in oldids]
  assert {r['rva'] for r in added}=={'0x97b2c0','0x97b8a0','0x994f00','0x1a337f0'}
  refs=0;used=set()
  for row in idx['entries']:
   for ref in row['evidence']:
    assert dm['sources'][ref['path']]=={k:ref[k] for k in ('bytes','sha256')}
    pointer(json.loads(cache[ref['path']]),ref['json_pointer']);refs+=1;used.add(ref['path'])
  assert used==set(dm['sources'])
  for row in added:
   assert row['stage']=='static'
   for field in ('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','runtime_capture_authorized'):
    assert row[field] is False
  r68=json.loads(cache['work/reports/war-peace-api-20261016-r68-independent-review/findings.json'])
  assert r68['subject_projection']==dm['sources']['work/reports/war-peace-api-20261016-r68-fixed-frame-projection/projection.json']
  cli=cache[rel(HERE/'war_peace_lookup.py')].decode()
  restored=cli.replace(pin(cache[rel(HERE/'data-manifest.json')])['sha256'],pin(cache[oldpath+'data-manifest.json'])['sha256']).replace('tool_revision=4','tool_revision=3').replace('revision 4;','revision 3;')
  assert restored==cache[oldpath+'war_peace_lookup.py'].decode()
  assert ast.dump(ast.parse(restored),include_attributes=False)==ast.dump(ast.parse(cache[oldpath+'war_peace_lookup.py']),include_attributes=False)
  receipt=json.loads(read(REPORT/'receipt.json',RECEIPT_PIN))
  assert receipt['passed'] is True and receipt['error'] is None and receipt['command_count']==7
  assert receipt['source_manifest']==SOURCE_PIN and receipt['all_jobs_and_direct_children_collected'] is True
  assert receipt['combined_delta_explicit_bytes']==receipt['query_source_explicit_bytes']+receipt['controller_explicit_bytes']<=64*1024*1024
  querypins={rel(REPORT/'receipt.json'):RECEIPT_PIN};commands=[];maxjob=0
  for i,item in enumerate(receipt['records']):
   commands.append(item['argv'][2:]);job=item['job'];maxjob=max(maxjob,job['peak_job_commit'])
   assert job['exit_code']==0 and job['error'] is None and job['job_active_processes_final']==0
   assert job['direct_child_collected'] is True and job['completed_command_descendants_terminated'] is False
   assert 1<=job['job_total_processes']<=8 and job['peak_job_commit']<=MEMORY
   for suffix,key in [('stdout.json','stdout'),('stderr.txt','stderr')]:
    pth=REPORT/f'{i:02d}.{suffix}';b=read(pth,item[key]);querypins[rel(pth)]=pin(b);assert len(b)<=2*1024*1024
    if key=='stdout':
     value=json.loads(b);assert value['status']=='ok' and value['tool_revision']==4
     assert value['native_calls']==value['requests_published']==0
     for flag in ('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry'):assert value[flag] is False
     assert value['provenance']['selected_source_count']==59 and value['provenance']['source_guard_before_and_after'] is True
    else:assert not b
  assert commands==[['check'],['catalog'],['lookup','0x97b2c0'],['lookup','0x97b8a0'],['lookup','0x994f00'],['lookup','0x1a337f0'],['search','v4 已审合同','--limit','20']]
  querypins[rel(REPORT/'claim.json')]=pin(read(REPORT/'claim.json'))
  for name in ['repair.stdout.txt','repair.stderr.txt','first-queries.stdout.txt','first-queries.stderr.txt','seal_candidate.py','seal-claim.json']:
   read(HERE/name)
  report='''# API lookup v4 作者交付

58 条合同、59 个固定 JSON 来源。原 v3 的 54 条记录逐条 data-equal；原 44 个来源 pin 不变。新增 R63 97b2c0、R64 97b8a0、R66 994f00 和 R67 1a337f0。R68 仅作为 994f00 的后来条件上下文，原 R66 历史未知原文保持。

七个首次 v4 文件查询通过：check、catalog、四个新增 RVA lookup 与组合 search。每个 Job exit0、active0，direct child 已收；每流不超过 2 MiB。query 只是文件验证，不代表任何端点可调用或游戏效果。旧 CLI main、旧测试、PE/engine/decoder/game/native/request 全部零新增。

首次构建的 runner 换行匹配断言失败，发生在任何查询前。build_index.py、claim、failure、stdout/stderr 都原样保留；repair_runner.py 仅生成新 runner 并完成来源封存，既有 index/data/CLI 字节不改。没有重跑 builder 或任何旧已通过方法；七个查询均为首次且没有失败。另一个最初 PowerShell 路径语法错误在执行前即停止，原 tool 回执在 build-failure 的读账之外，以 1 MiB 手工检查 allowance 覆盖。

新 wrapper 与 v3 的差异仅 DATA_SHA、tool_revision 和帮助版本文案；逻辑 AST 可精确还原相等。固定 v1 引擎的路径、文件大小、source 数、前后 pin、地址算术与权限守卫保持。新增数据非运行时 API，无外部 root/manifest 或进程执行选项。

R63 不认 DWORD+30 币种/单位或最终值保持；R64 不认 F0 枚举、虚调用返回类或唯一集合；R66/R68 不认排序/守恒/free，保留正常返回、GS alias、fresh H/T、六参低 BYTE 等界限；R67 不按 CRT 名字推行为，寄存器保持不是 pointee 保持或调用安全。所有效果、运行时、租约及重试权限 false。

状态：SOURCE-READY，等待 root 非作者完整文件审查。旧稳定观察器、v1/v2/v3、48/44/42 与 15 profiles 未改；R69/R70 未加入。账目明确区分分析/封存 24 MiB 与首次查询批次 64 MiB，不声称全 OS I/O。
'''
  with (HERE/'report.md').open('xb') as f:f.write(report.encode())
  read(HERE/'report.md')
  # Final flat pre/post pin checks; no recursive manifest interpretation.
  allpins={name:pin(raw) for name,raw in cache.items()}
  for name,expected in allpins.items():read(ROOT/name,expected)
  metrics=dict(original54_dataequal=True,old44pins_unchanged=True,entries=58,selected_JSON_sources=59,evidence_JSONpointers=refs,
   seven_first_queries_passed=True,query_source_bytes=receipt['query_source_explicit_bytes'],query_controller_bytes=receipt['controller_explicit_bytes'],
   query_batch_explicit_bytes=receipt['combined_delta_explicit_bytes'],query_batch_budget=64*1024*1024,maximum_query_Job_peak=maxjob,
   analysis_prior_upper=prior_upper,seal_explicit_bytes=sum(x['bytes'] for x in reads),analysis_upper_before_manifest=prior_upper+sum(x['bytes'] for x in reads),
   analysis_budget=BUDGET,self_peak_bytes=peak,not_all_OS_IO=True,
   new_PE_decoder_game_native_requests_tests=0,all_shells_collected=True)
  mp=write('author-manifest.json',dict(schema='EU4-LOOKUP-V4-AUTHOR-MANIFEST/1',sealed=True,
   status='SOURCE_READY_PENDING_ROOT_INDEPENDENT_REVIEW',subject_source_manifest=SOURCE_PIN,
   local_and_selected_source_pins=dict(sorted(allpins.items())),pin_count=len(allpins),
   metrics=metrics,source_graph_and_query_outputs_prepost_equal=True,
   authority={f:False for f in ('callable','native_ready','selected_effect_verified','runtime_capture_authorized','world_lease','atomic_snapshot','authorizes_retry')}))
  # File check of the new author manifest itself. Its file set was just checked above.
  mb=read(HERE/'author-manifest.json',mp)
  vp=write('verification.json',dict(sealed=True,passed=True,author_manifest=pin(mb),pins_verified=len(allpins),
   source_manifest=SOURCE_PIN,query_receipt=RECEIPT_PIN,metrics=metrics,
   final_analysis_upper=prior_upper+sum(x['bytes'] for x in reads),reads=reads))
  dp=write('delivery.json',dict(sealed=True,status='SOURCE_READY_PENDING_ROOT_INDEPENDENT_REVIEW',
   source_manifest=SOURCE_PIN,author_manifest=mp,verification=vp,query_receipt=RECEIPT_PIN,
   cli=pin(cache[rel(HERE/'war_peace_lookup.py')]),data_manifest=pin(cache[rel(HERE/'data-manifest.json')]),index=pin(cache[rel(HERE/'index.json')]),
   all_shells_collected=True,new_queries=7,old_tests=0,PE_game_native_requests=0,source_will_not_change=True))
  print(json.dumps(dict(passed=True,author_manifest=mp,verification=vp,delivery=dp,
   pins=len(allpins),metrics=metrics,final_analysis_upper=prior_upper+sum(x['bytes'] for x in reads))))
 except BaseException as exc:
  write('seal-failure.json',dict(error=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,retry_authorized=False));raise
if __name__=='__main__':main()
