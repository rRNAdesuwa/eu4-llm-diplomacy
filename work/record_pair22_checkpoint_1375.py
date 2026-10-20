"""Record actual V22 terminal and isolated repair results, preserving doc preimages."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/runtime/pair22-checkpoint-20261012a';OUT.mkdir(exist_ok=False)
def raw(p):
 assert p.stat().st_size<=4*1024*1024;return p.read_bytes()
def desc(p):
 b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def new(p,b):
 with p.open('xb') as f:f.write(b if isinstance(b,bytes) else b.encode('utf-8'))
runtime=ROOT/'work/runtime/pair22-session-20261012a'
a=json.loads(raw(runtime/'initial.json'));b=json.loads(raw(runtime/'final.json'));s=json.loads(raw(runtime/'inspect.stdout'))
assert a['equal'] and b['equal'] and a['passes'][0]==b['passes'][0] and s['terminal'] and not s['complete'] and not s['results']
assert [x['sequence'] for x in s['rows'] if x['event']=='request_claimed']==[1] and not any(x['event']=='native_call_begin' for x in s['rows'])
archive=ROOT/'work/runtime/pair22-stopped-archive-r3-50684-20261012a/archive.json';arc=json.loads(raw(archive))
assert len(arc['files'])==441 and arc['late_exact_handle_exit']['normal'] and not arc['held_normal_exit_verified']
report=dict(schema=1,status='V22_TERMINAL_BEFORE_NATIVE_CALLS',identity=s['identity'],owner=s['owner_thread'],initial=desc(runtime/'initial.json'),final=desc(runtime/'final.json'),
 selected_group_equal=True,complete=False,native_call_attempts=0,claimed_sequences=[1],published_sequences=[1,2,3,4,5,6],unclaimed_sequences=[2,3,4,5,6],archive=desc(archive),
 failure='Full-table ordinary-selector restriction rejects 405 passive rows; health diagnostic itself meets selected fields.',held_watcher_timeout_preserved=True,late_exact_exit=arc['late_exact_handle_exit'],
 new_candidates={name:desc(ROOT/'work/candidates'/name/'review.json') for name in ['current-country-tag-cpp-r2-1375','v21-native-pair-guard-r3-1375','v23-pair-nosend-bootstrap-1375','v23-pair-private-client-r2-1375']},
 production_backend_count=0,task_complete=False)
new(OUT/'report.json',json.dumps(report,indent=2,sort_keys=True)+'\n')
text='''**2026-10-12：V22 实际批次在首次原生调用前停止；解析器修复已封存，V23 正在新进程载入基线。** 50684/01dd5a131399ebb8/session60c7109d7d019ebd0fae0ba52e986fd8/owner18544，BridgeStart0，六请求一次性发布；只claim1，lease_rejected、terminal，native_call_begin=0，未发送。初末整组各一次，两遍一致且初末选定状态相同（103外交官全部空闲、11.11、五关系无选定对象）；不据此声称全世界无副作用或外交效果。终止后只读诊断定位1380国家表中405个预留国家handle具有selector1..7，旧whole-table selector0断言过严；暂停/ironman/reset/load/player等选定health字段符合限制。旧文件保留，2..6永不补发。

新 `current-country-tag-cpp-r2-1375` 被动保留并核验selector0..7的完整handle，仍仅允许请求ordinary selector0，26作者组含真实1380句柄的分析内存回放通过；新 Guard R3 23组+3实际sampler分析分配边界组通过。新 V23 DLL SHA9f5525cca18fad63a6216b6318255ab9fba2ac702f1f6d1eed5084bd29366543，manifest e5caf4f66f49453e2cb91663cd531ee1df78b47591c59616293022ea818cf184，226源/19codec组编译通过。V23客户端首轮14/15，C++夹具留旧manifest常量；新R2只修夹具，客户端字节相同，15/15通过（client SHA8091e20aaa67199848c7a6469e9fa693fef52e153c370668c7ea1463b6a99c30）。未做独立复审，不把作者模型当实际原生证明。

旧50684菜单quit及确认已实际点击；55s held watcher先超时保留false，后续精确creation的signaled handle核得exit0/FILETIME134362629543782395，但不是held贯穿退出。完整只读归档441文件/10910762B，`work/runtime/pair22-stopped-archive-r3-50684-20261012a/archive.json` SHAf492b20f9b49677e85f193fa6aecb17798d444d277da6a77b2ce6454a14fae88；早期归档helper过严PID消失判断及空stderr失败/partial R2均保留。新52236/01dd5a1a23ab2258启动，客户端file-only check0，尚无新DLL/请求/初末观测。所有分析shell已收齐。完整任务仍未完成、正式backend0、274描述/270静态映射/历史28选定kind不变，贴吧正文未读。

下方日期段落为历史记录。

'''
for name in ['HANDOFF.md','VALIDATION.md']:
 p=ROOT/name;old=raw(p);new(OUT/(name+'.preimage'),old);idx=old.find(b'\n');p.write_bytes(old[:idx+1]+b'\n'+text.encode('utf-8')+old[idx+1:].lstrip(b'\r\n'))
print(json.dumps(dict(report=desc(OUT/'report.json'),docs=['HANDOFF.md','VALIDATION.md'])))
