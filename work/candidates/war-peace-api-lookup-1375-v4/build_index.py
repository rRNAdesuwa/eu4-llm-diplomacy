"""Build a new retained-only v4 index; no previous CLI/producer execution."""
from pathlib import Path
import ast
import copy
import ctypes
from ctypes import wintypes
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/war-peace-api-lookup-1375-v3'
MAX_FILE=4*1024*1024
BUDGET=24*1024*1024
MEMORY=768*1024*1024
MANUAL_ALLOWANCE=1024*1024
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
OLD_PINS={
 'source-manifest.json':(12934,'7b8b9323d20190c1c7f4b966c9520d10a4136a8f5c6be3c8957621b4b98fe6d1'),
 'data-manifest.json':(8733,'8f849152e150b3f3918b10bb427cfa39457e4774db83c4dac42f82da04c3c212'),
 'index.json':(138061,'4bcd07e34e50aeb1336632a4914d4e0e0f8f39a1aa6367541354d37f0b800a58'),
 'war_peace_lookup.py':(3606,'f4b5f7e1fe4e5546cdac66a6f9bb45541ead648d311cc2e2e9023e2b56910979'),
 'run_queries.py':(7633,'8a8e11932e33a2562a2eafc19a087329f1db2953773d224d1a8b9ff4c63a1b9e')}
EXTRA={
 'r63-gold-scalar-source/contract.json':(7894,'e515d681b968f8f30f5aad8df900a97b38f0ee44aa8286e1e5c22d399fbc48f0'),
 'r63-independent-review/findings.json':(4385,'80418ecca9b71e5d98dc26ac102b9304fd8d3732deb7754f618473f33db2b8ac'),
 'r63-independent-review/manifest.json':(13129,'439846e7b3ba478585f90aa02c891fe3055619284fe43cd4caf97987a81e7149'),
 'r64-gold-element-selection/contract.json':(9119,'737775651b93f23b69fe70059e8c424fa22ca0a48cbadc8bea7573da390d50ef'),
 'r64-independent-review/findings.json':(6608,'ea1ebea456742277c663a7d0ae200d4b463a7d34d2774037f5fc30611757778f'),
 'r64-independent-review/manifest.json':(13709,'750267e0b3f657c1c3cc8e33c3c0d052153f922b71e05e4e1a7639d26b668ef8'),
 'r66-generated-record-postprocess/contract.json':(8319,'1440ddf1b3da152a643899a64d1c02226da8becd9080a4204fa1beaf6d10dc2e'),
 'r66-independent-review/findings.json':(5711,'9f4f95352be92800da6c7e1d93a237f7875f45ca7a6ed4d3d0ec2ecc163c0005'),
 'r66-independent-review/manifest.json':(13196,'29faa23e023e72f12d63a3a990b8dedfd6f93dee6e58d369785b8c4dc274726f'),
 'r67-entry-helper-register-contract/contract.json':(6922,'af029d3cd895116e69cbc45a8b78a2ad8fde7773b7ef18f621b719b140ddfb56'),
 'r67-actual-independent-review/findings.json':(5833,'fcbacb45bbe9647c9a01d77f57f3ced70f4d77ac5497ec82c3a82acddf223a39'),
 'r67-actual-independent-review/manifest.json':(11693,'a1788deb8c2fe81f19999a20d8c68b88a6424d0ff800cd98751d4f75ebd5c905'),
 'r68-fixed-frame-projection/projection.json':(11854,'dd77472acae9252cf604d52af2f4ee318517abe9a7bad175deb5814ee1d3fc60'),
 'r68-independent-review/findings.json':(5100,'9ecf5a7f93726b780a395ae4ccc392467ddcda77e1f15008035dd08fa266c3f2'),
 'r68-independent-review/manifest.json':(11144,'fb7fa6311c7be601316c8db964cb4ccf78c7baccc5633ffb6f36697f34f7f414')}
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated',
 'selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','runtime_capture_authorized',
 'peace_completion_verified','amount_units_verified','recipient_direction_verified','object_ownership_verified')
ENGINE='work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py'
ENGINE_PIN=(16583,'d4237d98c58e89be9419ff736f01d97f5fde0129c07c5c7f778baf010071746e')
JOB='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_PIN=(8615,'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011')

class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in
 ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
 'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
reads=[];peak=0;cache={};sourcepins={}

def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c)
 assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(c),c.cb)
 peak=max(peak,c.PrivateUsage,c.WorkingSetSize,c.PeakWorkingSetSize,c.PeakPagefileUsage)
 assert peak<=MEMORY

def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def rel(p):return p.relative_to(ROOT).as_posix()
def read(path,expected=None,source=True):
 guard();a=path.stat();assert a.st_size<=MAX_FILE
 assert MANUAL_ALLOWANCE+sum(i['bytes'] for i in reads)+a.st_size<=BUDGET
 b=path.read_bytes();z=path.stat();assert (a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns) and len(b)==a.st_size
 actual=pin(b)
 if expected is not None:
  want=expected if type(expected) is dict else dict(zip(('bytes','sha256'),expected))
  assert actual==want,(rel(path),'changed')
 reads.append(dict(path=rel(path),**actual));cache[rel(path)]=b
 if source:sourcepins[rel(path)]=actual
 return b
def write(name,obj):
 b=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
 with (HERE/name).open('xb') as f:f.write(b)
 return pin(b)
def text(name,s):
 b=s.encode('utf-8')
 with (HERE/name).open('xb') as f:f.write(b)
 return pin(b)
def path(key):return 'work/reports/war-peace-api-20261016-'+key
def ptr(doc,selector):
 for key in selector.split('/')[1:]:
  key=key.replace('~1','/').replace('~0','~');doc=doc[int(key)] if type(doc) is list else doc[key]
 return doc

def main():
 write('build-claim.json',dict(schema='EU4-LOOKUP-V4-BUILD-CLAIM/1',single_attempt=True,
  analysis_budget=BUDGET,manual_text_allowance=MANUAL_ALLOWANCE,query_batch_separate=64*1024*1024,
  PE_decoder_game_native_tests=0))
 try:
  old={n:read(OLD/n,v) for n,v in OLD_PINS.items()}
  dm=json.loads(old['data-manifest.json']);index=json.loads(old['index.json']);prior=copy.deepcopy(index['entries'])
  assert len(prior)==54 and len(dm['sources'])==44 and dm['game_sha256']==GAME
  documents={name:json.loads(read(ROOT/name,v)) for name,v in dm['sources'].items()}
  sources=copy.deepcopy(dm['sources'])
  for short,expected in EXTRA.items():
   name=path(short);raw=read(ROOT/name,expected);sources[name]=pin(raw);documents[name]=json.loads(raw)
  assert len(sources)==59 and sum(x['bytes'] for x in sources.values())<=BUDGET
  for n,owner in [(63,'gold-scalar-source'),(64,'gold-element-selection'),(66,'generated-record-postprocess'),(67,'entry-helper-register-contract')]:
   rev=f'r{n}-'+('actual-independent-review' if n==67 else 'independent-review')
   j=documents[path(rev+'/findings.json')]
   assert j['sealed'] is True and j['passed'] is True and j['blocking_findings']==[]
   assert j['subject_contract']==sources[path(f'r{n}-{owner}/contract.json')]
  review68=documents[path('r68-independent-review/findings.json')]
  assert review68['sealed'] is True and review68['passed'] is True and review68['blocking_findings']==[]
  read(ROOT/ENGINE,ENGINE_PIN);read(ROOT/JOB,JOB_PIN)
  def refs(short,*selectors):
   name=path(short)
   for selector in selectors:ptr(documents[name],selector)
   return [dict(path=name,json_pointer=selector,**sources[name]) for selector in selectors]
  def reviewed(n):
   d=f'r{n}-'+('actual-independent-review' if n==67 else 'independent-review')
   return refs(d+'/findings.json','/machine_contract','/precision_notes','/subject_contract')+refs(d+'/manifest.json','/sealed')
  def row(identifier,rva,title,summary,params,returns,owned,borrowed,sites,unknown,evidence,aliases):
   return dict(id=identifier,rva=rva,title=title,summary='v4 已审合同：'+summary,actions=['peace'],aliases=aliases,
    kind='function',stage='static',stage_scope='固定 1.37.5 磁盘保留字节及完整非作者审查；不是现场调用、最终效果或可执行 API。',
    signature=dict(complete_prototype='unknown',status='partial_static',parameters=params,returns=returns),
    ownership=dict(owned=owned,borrowed=borrowed),call_sites=[dict(rva=a,relationship=b) for a,b in sites],
    unresolved=unknown,evidence=evidence,**{flag:False for flag in FLAGS})
  c63='r63-gold-scalar-source/contract.json';c64='r64-gold-element-selection/contract.json'
  c66='r66-generated-record-postprocess/contract.json';c67='r67-entry-helper-register-contract/contract.json'
  rows=[]
  rows.append(row('peace.selected_element_scalar_output','0x97b2c0','选定元素 DWORD 输出路径（R63）',
   '199B 正常路径：调用 97b8a0 后若 descriptor count==1，从 fresh data 首元素读取 DWORD+30 写到借用输出地址，否则写零；RAX 正常返回输出指针。金额单位与最终值保持未知。',
   ['RCX=opaque W，转交 97b8a0；没有国家/货币类型证明。','RDX=借用 DWORD 输出地址，保存于 RBX；固定 R62 caller 指向 Q62+0x18。','97b8a0 的 RDX=&steady+30 descriptor，R8=&steady+20 原始 16B，R9B=1；上 56 位未知。','selector DWORD0/QWORD8 为零，padding4..7 未初始化；传入 XMM0 不可称全零。'],
   '正常 ABI/内存前提下 RAX=原输出指针，不是标量 T；显式输出写之后可能调用 17394f0，最终 pointee 保持仍需其别名/返回条件。',
   ['局部栈 descriptor/inline storage 和 raw selector；仅机器栈存储，不证明完整 C++ 类或分配所有权。'],
   ['opaque W、输出 DWORD 地址、postcall descriptor data 及首元素；外部 cleanup 语义/生命周期未知。'],
   [('0x97b31f','向 97b8a0 转交 W、局部 descriptor、raw selector 和 R9B1。')],
   ['R64 已另列 97b8a0 正常本体；未跟 virtual78/77e640 等具体目标。','17394f0 别名、错误与最终输出保持未知。','元素类、DWORD+30 单位、正值保证、收付款方向、当前值、议和完成未知。'],
   refs(c63,'/entry','/inputs','/stack','/first_call','/output_paths','/return','/writes','/data_provenance')+reviewed(63),
   ['r63_scalar_output','选定元素标量输出']))
  rows.append(row('peace.element_pointer_selection','0x97b8a0','原始元素指针筛选与集合修改（R64）',
   '1003B 正常 CFG：先清 P+14；低 R9B 与 W 两个跨度决定 flag0 自调用及 A 追加/B 首匹配移除。base 分支按 F+8 分开；virtual78、容量调用及 77e640 仍未跟，不认证业务枚举。',
   ['RCX=W，RDX=P descriptor，R8=F 原始16B；P+8 data、P+10 DWORD capacity-like、P+14 DWORD count-like，只是算术角色。','只测试 R9B；选定 caller 为1。局部 selfcall 传 R9D0，只排除 child 的本地递归分支，不证明全局终止。','A/B stride8 元素 virtual78 返回 opaque K；比较 DWORD[K]==fresh DWORD[F] 且 QWORD[K+8]==0。','F+8 非零：W+d0→Q，遍历 Q+3a8/+3b0，比较 QWORD[E+30]；F+8 零：fresh uint32 F0 选 W+d0 的24B记录 begin/end。'],
   '无统一 RAX 赋值/语义；R63 忽略它并 fresh 读取 P count/data。',
   ['局部 F 的16B拷贝与临时元素 QWORD 槽；不证明任何 heap 分配拥有权。'],
   ['W/P/F、所选 spans、元素 E/K 及 P.data；可别名，外调可修改，非只读函数。'],
   [('0x97b31f','R63 的固定调用现场；RDX 是 descriptor，非旧输出 DWORD 地址。'),('0x97b90f','自身入口调用，同 W/P、F 拷贝、R9D0。'),('0x97bc68','77e640(P,EDX=fresh Pcount,R8=&temporary E)；仅参数，不认 append 实现。')],
   ['virtual78 具体目标和 K 类型未证；F0=0 不能命名金币枚举。','1c20d0/77e640/8f4f0/1a33310 内容、容量成功、终止与异常未知。','unsigned span 与 signed count 算术不是边界认证；A 允许重复，B 每次删除首 pointer match。','F8 非零比较 QWORD E+30，不同于 R63 DWORD E+30；没有金额单位、唯一 count1、最终 T 或效果证明。'],
   refs(c64,'/entry','/formal_machine_inputs','/common_write','/outer_overlay_gate','/A_append_path','/B_remove_path','/base_branch_F8_nonzero','/base_branch_F8_zero','/return','/writes')+reviewed(64),
   ['r64_element_selection','元素指针筛选']))
  r66=row('peace.generated_record_postprocess','0x994f00','生成结果后处理的条件路径（R66/R68）',
   '190B 历史 R66 本体保留 first-helper 未知；后来 R67/R68 只在正常返回及有效内存条件下给出 F=Q-1048。fresh BYTE[T] 与 H0/H8 后按 signed N<=32 或 >32 分流，后续内容/单位/最终 T 仍未知。',
   ['固定 R62 所选可达 complex 路径：RCX=保存的原 H，RDX=当前借用 DWORD 地址 Q62+18；simple 与 complex D<=0 均可绕过。','后来的 R68 条件：Q=R66入口RSP，F=Q-1048；原 T 地址=Q+a8，寄存器身份不证明 pointee 内容保持。','helper 后依次 fresh BYTE[T]、QWORD[H+8]、QWORD[H]；N=low64(SAR64(end-begin mod64,2)*aaaaaaaaaaaaaaab)，非无条件除12。','大分支传 RCX begin/RDX end/R8 N/R9 fresh local30，stack arg5 fresh local38，arg6仅 low BYTE BL；上7字节未知。'],
   '条件正常返回下 RAX 是最后到达的 998d50/998e10/175da20 返回值；没有统一 bool/金额/结果含义。',
   ['固定帧的局部30/38地址为 Q-1018/Q-1010；本体无预初始化/分配定义证明。'],
   ['opaque H/current T、begin/end spans、外调产出的临时值；GS 派生写可别名 H/T、保存槽、返回槽。'],
   [('0x9846d5','R62所选 complex reachable 路径；早期正值门不保证后续 fresh H/T 不变。'),('0x994f15','调用 1a337f0，EAX=1040hex；R67/R68 提供独立条件上下文。'),('0x994f8a','998e10 六机器参数位置，仅第六低字节已初始化。')],
   ['R66 历史合同原样保留；R68 只补 first-helper 寄存器/固定 frame 的条件未知。','正常返回、GS 值、页面写权限/有限循环、alias 排除、saved/return 内容仍未知。','998d50/998e10/46a3b0/175da20 未跟；不认 sort/free、守恒、单位或收款方向。','fresh H/T、完整布局/拥有权、最终记录/最终 T、生命周期、现场执行与议和效果未知。'],
   refs(c66,'/entry','/caller_scope','/first_call_boundary','/stack_profile_conditional','/machine_reads','/small_path','/large_path','/return','/unresolved')+reviewed(66)+
   refs('r68-fixed-frame-projection/projection.json','/hypotheses','/findings','/address_table','/machine_argument_locations','/GS_alias','/R62_reachability','/remaining_unknowns')+
   refs('r68-independent-review/findings.json','/passed')+refs('r68-independent-review/manifest.json','/sealed'),
   ['r66_postprocess','r68_fixed_frame_context','生成结果后处理'])
  r66['historical_contract']=dict(path=path(c66),sha256=sources[path(c66)]['sha256'],unchanged=True,
   meaning='历史 R66 first-helper unknown 保持原文，不以新上下文重写历史证据。')
  r66['later_conditional_context']=dict(path=path('r68-fixed-frame-projection/projection.json'),
   sha256=sources[path('r68-fixed-frame-projection/projection.json')]['sha256'],
   condition='R67 正常有效返回、code/stack/alias 等 hypotheses；不是 runtime execution proof。',
   fixed_frame='F=Q-0x1048',fresh_H_T_required=True,pointee_immutability_proved=False)
  rows.append(r66)
  rows.append(row('shared.page_step_register_helper','0x1a337f0','GS 派生逐页写与具体寄存器合同（R67）',
   '78B、19行、无 CALL：保留具体 RCX/RDX/RAX；GS:[10] 控制可能的逐0x1000步 BYTE0 写。正常返回保持固定 caller RAX1040，不证明 H/T 内容不变、任意输入终止或可调用。',
   ['S=入口RSP，N=入口RAX；固定 R66 CALL 的 N=0x1040。RCX=opaque H/RDX=当前 T 借用地址。','candidate=(S+8)-N mod64，unsigned borrow 则置零；B=QWORD GS:[10]。candidate>=B 则跳恢复，否则 L=candidate&fffffffffffff000。','循环每次 R11-=1000hex 并 BYTE[R11]=0，直至 L；无任意 GS 值终止/写权限证明。'],
   '正常路径 RAX=入口RAX，RCX/RDX/R8/R9/XMM 无写；R10/R11 从保存槽恢复，其内容相等需无别名覆盖。RET前RSP=S，RET后S+8；算术 flags 来自最后 ADD，DF未写。',
   ['本体临时保存 R10/R11 的两个栈 QWORD 槽；不证明 GS 派生目标是自有栈。'],
   ['GS:[10] 值与派生写地址、保存槽与返回槽；可与 H/T 等别名，不是 pure/read-only 或 lifetime 证明。'],
   [('0x994f15','固定 R66 CALL，EAX1040hex；正常返回前提下供后续 SUB RSP,RAX 使用。')],
   ['业务/CRT 名称未知；不按名字假设契约。','任意 GS 对齐、映射、异常/故障、循环终止及 return target 内容未证。','寄存器不变不代表 H/T/saved-memory 不变；不证明完整生命周期、金额/效果或安全调用。'],
   refs(c67,'/entry','/normal_instruction_dataflow','/register_contract','/memory_accesses','/conditional_termination_example','/R66_conditional_crosswalk','/limits')+reviewed(67),
   ['r67_register_contract','gs_page_step','具体寄存器保持']))
  index['entries']=sorted(prior+rows,key=lambda r:r['id'])
  assert len(index['entries'])==58 and len({r['id'] for r in index['entries']})==58
  now={r['id']:r for r in index['entries']}
  assert all(now[r['id']]==r for r in prior)
  used=set()
  for r in index['entries']:
   for ref in r['evidence']:
    assert {k:ref[k] for k in ('bytes','sha256')}==sources[ref['path']]
    ptr(documents[ref['path']],ref['json_pointer']);used.add(ref['path'])
  assert used==set(sources)
  for r in rows:assert all(r[x] is False for x in FLAGS)
  ip=write('index.json',index)
  newdm=copy.deepcopy(dm);newdm.update(index=ip,sources=dict(sorted(sources.items())))
  dp=write('data-manifest.json',newdm)
  cli=old['war_peace_lookup.py'].decode().replace(OLD_PINS['data-manifest.json'][1],dp['sha256']).replace('tool_revision=3','tool_revision=4').replace('revision 3;','revision 4;')
  cp=text('war_peace_lookup.py',cli)
  restored=cli.replace(dp['sha256'],OLD_PINS['data-manifest.json'][1]).replace('tool_revision=4','tool_revision=3').replace('revision 4;','revision 3;')
  assert restored==old['war_peace_lookup.py'].decode()
  assert ast.dump(ast.parse(restored),include_attributes=False)==ast.dump(ast.parse(old['war_peace_lookup.py']),include_attributes=False)
  proof=write('lineage-proof.json',dict(schema='EU4-LOOKUP-V4-LINEAGE/1',old_index=pin(old['index.json']),
   original_entries=54,all_original_entries_dataequal=True,added_ids=[r['id'] for r in rows],new_count=58,
   old_data_sources_44_unchanged=all(sources[k]==v for k,v in dm['sources'].items()),new_sources=15,
   wrapper_exact_restore_equal=True,wrapper_AST_logic_unchanged=True,
   allowed_changes=['DATA_SHA','tool_revision 3 to4','help revision3 to4'],
   native_or_effect_escalation=False,source_only_pending_root_review=True,
   per_old_entry=[dict(id=r['id'],canonical_sha256=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()) for r in prior]))
  write('source-delta.json',dict(schema='EU4-LOOKUP-V4-SOURCE-DELTA/1',prior_cli=pin(old['war_peace_lookup.py']),current_cli=cp,
    wrapper_AST_logic_unchanged=True,original_engine=sourcepins[ENGINE],data_manifest=dp,index=ip,lineage=proof,
    original_records_unchanged=54,added_records=4,selected_JSON_sources=59,R69_R70_included=False))
  # Generate a new first-query runner; the v3 runner is only read as source.
  runner=old['run_queries.py'].decode()
  runner=runner.replace('lookup-v3-delta-20261016-r1','lookup-v4-first-queries-20261016-r1')
  runner=runner.replace(OLD_PINS['war_peace_lookup.py'][1],cp['sha256']).replace('V3','V4').replace('_v3_','_v4_')
  runner=runner.replace('file_analysis_budget_separate=32*1024*1024','file_analysis_budget_separate=24*1024*1024').replace('analysis_budget_separate=32*1024*1024','analysis_budget_separate=24*1024*1024')
  runner=runner.replace("COMMANDS=[['check'],['catalog'],['lookup','0x9b46a0'],['lookup','0x3383b0'],\r\n          ['lookup','0x771be0'],['lookup','0x9844d0'],['search','postincrement','--limit','20']]", "COMMANDS=[['check'],['catalog'],['lookup','0x97b2c0'],['lookup','0x97b8a0'],\r\n          ['lookup','0x994f00'],['lookup','0x1a337f0'],['search','v4 已审合同','--limit','20']]")
  runner=runner.replace("value['tool_revision']==3","value['tool_revision']==4").replace("provenance['selected_source_count']==44","provenance['selected_source_count']==59").replace("value['entry_count']==54","value['entry_count']==58").replace("value['count']==54","value['count']==58")
  begin=runner.index("                if args[1]=='0x771be0':")
  end=runner.index('        sourceguard(sourcepin)',begin)
  runner=runner[:begin]+"            else:assert value['count']==4 and {x['rva'] for x in value['entries']}=={'0x97b2c0','0x97b8a0','0x994f00','0x1a337f0'}\r\n"+runner[end:]
  assert "['lookup','0x97b2c0']" in runner and "postincrement'" not in runner
  text('run_queries.py',runner)
  # Postcheck all selected source identities without following any manifest closure.
  for name,expected in list(sourcepins.items()):read(ROOT/name,expected)
  local_names=['README.md','build_index.py','budget.json','index.json','data-manifest.json','war_peace_lookup.py','run_queries.py','lineage-proof.json','source-delta.json','build-claim.json']
  files=dict(sourcepins)
  for name in local_names:files[rel(HERE/name)]=pin(read(HERE/name,source=False))
  receipt=write('build-receipt.json',dict(schema='EU4-LOOKUP-V4-BUILD-RECEIPT/1',passed=True,sealed=True,
   selected_source_count=59,selected_source_bytes=sum(x['bytes'] for x in sources.values()),
   old54_dataequal=True,source_prepost_equal=True,reads=reads,explicit_bytes=sum(x['bytes'] for x in reads),
   manual_inspection_allowance=MANUAL_ALLOWANCE,analysis_upper=sum(x['bytes'] for x in reads)+MANUAL_ALLOWANCE,
   analysis_budget=BUDGET,query_budget_separate=64*1024*1024,self_peak_bytes=peak,
   PE_engine_decoder_game_native_requests_tests_oldCLI=0,
   shell_preflight_error_retained='08daab: PowerShell rejected unsupported brace path syntax before executing any statement; exit1. Corrected metadata command7dec9d exit0; no artifact/native/query was attempted.',
   authority={x:False for x in FLAGS}))
  files[rel(HERE/'build-receipt.json')]=receipt
  sp=write('source-manifest.json',dict(schema='EU4-LOOKUP-V4-SOURCE-MANIFEST/1',sealed=True,
   status='SOURCE_READY_PENDING_ROOT_INDEPENDENT_REVIEW',native_ready=False,callable=False,
   game_sha256=GAME,entry_count=58,selected_JSON_sources=59,files=dict(sorted(files.items())),
   dependency_scope='flat selected sources only; nested historical/engine references are metadata, not recursively opened',
   fixed_query_engine=sourcepins[ENGINE],first_queries_pending=True,
   build_analysis_budget=BUDGET,first_query_batch_budget=64*1024*1024,authority={x:False for x in FLAGS}))
  print(json.dumps(dict(passed=True,source_manifest=sp,index=ip,data_manifest=dp,cli=cp,source_count=59,
   build_upper=sum(x['bytes'] for x in reads)+MANUAL_ALLOWANCE,self_peak=peak)))
 except BaseException as exc:
  write('build-failure.json',dict(error=type(exc).__name__,detail=str(exc),reads=reads,self_peak=peak,
   retries_authorized=False,PE_engine_decoder_game_native_requests_tests=0))
  raise

if __name__=='__main__':main()
