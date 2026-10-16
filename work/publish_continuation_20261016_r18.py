"""Append-only checkpoint publication from selected pinned witnesses."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/continuation-publication-20261016-r18'
assert not OUT.exists()
used=0
journal=[]
def pin(raw): return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(name,expected=None):
    global used
    p=ROOT/name
    size=p.stat().st_size
    assert size<=4194304 and used+size+1<=8388608
    with p.open('rb') as f: raw=f.read(size+1)
    used+=len(raw)
    assert len(raw)==size
    if expected is not None: assert pin(raw)==expected,name
    journal.append({'path':name,**pin(raw)})
    return raw
refs=[
 ('work/reports/peace-current-pending-v2-live-controller-source-independent-review-20261016-r2/findings.json',5817,'4e38a2083274e8e82825ad63f0e50b7dc7ae3c90858703742341db33e3da31d7'),
 ('work/reports/peace-current-pending-v2-root-once-live-authorization-20261016-r2/receipt.json',18622,'e0ee6634c900d78de7cc8c3ae23156036c0337bd721ab7aa7530ffee6aa02334'),
 ('work/reports/peace-current-pending-v2-live-controller-20261016-r2/receipt.json',421298,'44c1eeab3ca7fe25dc54a3087a208dbebd9bce23f5118e372d16ebc1ee435583'),
 ('work/reports/peace-current-pending-v2-live-controller-20261016-r2/actual-manifest.json',27958,'ac63b83d63b2e8b469e0db0d568d88fecae96dde7a5ebe466bb80fa64b51f283'),
 ('work/reports/peace-current-pending-v2-live-controller-20261016-r2/live-completion.json',11530,'5ebf44c93ee61f31fec00503cdf153c96260b540bd6cd19416322b36880962bb'),
 ('work/reports/war-peace-api-20261016-r86-cc220-actual-source/capture.json',85315,'e3a06664b11a14f483705cd3ae4852b0cd562a85ab46ac7395bfc428673bb28f'),
 ('work/reports/war-peace-api-20261016-r86-cc220-actual-source/owned-code.json',635,'65d0c63efdc37f369bb8aa4f0f55a0a5c3d59c79db8bc37e98723a30048fde82'),
]
data={name:read(name,{'bytes':size,'sha256':sha}) for name,size,sha in refs}
peer=json.loads(data[refs[0][0]])
result=json.loads(data[refs[2][0]])
assert peer['passed'] is True and peer['blocking_findings']==[]
assert result['status']=='selected_peace_queue_absent' and result['control_passed'] is True
assert result['current_state_observed'] is True and result['status_attempts']==1
assert result['selected_queue_presence'] is False and result['original_request_correlated'] is False
assert result['job']['job_active_processes_final']==0 and result['job']['direct_child_collected'] is True

short='''2026-10-16 更新：游戏已自主重开、处理成就提示并载入法国1445-05-19暂停。新v2配置适配器通过8项新增测试与完整源码独审，唯一实机只读查询已成功读取两次样本，当前FRA→ENG选定议和收件队列absent；原始内存/IO完整独审正在进行，尚不升级工具表。当前absence不证明过去请求拒绝、AI接受或议和完成。R86新70B仅pdata片段，两个外部后继未覆盖、无RET，API执行器仍未完成。48/44/42及禁重发保持；详情见HANDOFF顶部，下方旧状态保留为历史。\n\n'''
handoff='''## 2026-10-16 最新继续点：重开完成；v2新配置profile唯一实采成功，待完整raw独审；R86取得70B开放片段

用户最新要求重开已完成，不能重复重开或要求用户守着成就提示。旧38076在Stop前已不存在，root未实际kill；当前98548/create01dd5d0e670312c4，窗口78056306。再次截图法国1445-05-19暂停；画面有用户其他窗口遮挡，无新UI输入。直接内存读取不要求游戏前台。

R1原唯一v2 status因local.env文本read profile在context_or_source拒绝，UNKNOWN/0RPM，真实readonly流已打开并fstat后拒绝、未读内容。其capture17942B8b6d9fe…、receipt391493Bd1119fe…与完整非作者审findings7676B4afdd351…均冻结；不重跑R1、不改旧Meter/reader。新R2是独立代码适配修复：固定ROOT/local.env、raw size/SHA先于UTF8sig解码、KEY同语法/通用换行、错误脱敏、size+1请求预留与16snapshot/64KiB上界。8个新增fictional case各once PASS，旧6/31未重跑。R2完整source peer findings5817B4e38a2083274e8e82825ad63f0e50b7dc7ae3c90858703742341db33e3da31d7/manifest13944Bc80ea76a7847b55613672b0a7fbf0fd24dc13d91b8a3e4fba868d68737af1086已接受为SOURCE-READY；四精确subjects为source8861B803d619d…/controller13431Be0807ad1…/child13495B8f807abd…/adapter7297Bb1d44aff…。source grant6172B58e3ab5f…与root真实配置独立raw pin preparation674Baa9d27c…（仅226B长度/SHA，无解码值）分开，作者build没有读取真实env。

root新R2 once grant5615Be0c3af80e785c385ea0c65e2f719e0cfa9570a6c83b2de8c84afd3749180c1d7已被D唯一使用，root issuance receipt18622Be0ee6634…，34源+peer subjects前后相等upper1745634<8MiB。D已执行唯一R2 status并收齐session71009：selected_peace_queue_absent/control_passed/current_state_observed true、CLI/controller exit0、Job2/active0/direct_child_collected，10.985s，peak45178880/46456832B。目录peace-current-pending-v2-live-controller-20261016-r2，capture929944B482f13ffcf7f54177bd736795153f9e8996921c361af429dd15f98d5122f4c9e/childio382278B2c15a378…/receipt421298B44c1eeab…/actualmanifest27958Bac63b83d…/completion11530B5ebf44c9…/delivery4621B153139e5…。生产记录2967RPM/77718B、两样本相等、source/code前后守卫与context后commit；配置1snapshot227requested/226returned且binary/virtual正常关闭；普通92044380B/固定host2302461254B/EXE115387512B三整hash/controller含seal4728545B。Val正做完整非作者raw/IO审，未完成前只采用producer当前状态，不改mapv6为accepted。作者封存摘要器自设1MiB拒绝449256B已保留；随后原8MiB预算内读取固定三文件，retained累计2331610B，无重query/checker/tests。

当前FRA→ENG选定inbox absent仅说明当次有界暂停样本没有匹配项，不证明原请求发送/接受/拒绝/效果/和平完成/持久化。normal_context_exit/heldNone不证明OS CloseHandle返回；world lease/ABA/atomic及read1/raw/fileno-os.read/mmap/native/OS/import/cache完整IO仍未知。旧原120/成功/派发/unknown/未闭所有权不能重发。48 effects/44 historical persistence/42 repair、stable15/98pins保持；支持继承人新PID读取还未实采。

R86 cc220 source peers/root raw seed已核后，root唯一执行produce.py（工具chunk c2313d exit0/1.217s，无pending shell，原stdout没有另存tee，执行事实是root工具记录见证）。capture85315Be3a06664…/owned635B65d0c63e…，selected pdata[cc220,cc266)70B20条，raw SHA9d8e24e09bdad5bfaa81fc990ed02c3cc7a81e75cfdd8c85582aa0088d0fe8cd。入口RCX/RDX/R8的条件机器模型尚无对象类型证明；4 PUSH会写栈。JEcc259→cc32c与末尾fallthroughcc266均外部，0CALL/0RET，local CFG未闭，不能称完整helper、返回身份或ownership转移。producer source_journal16772282<32MiB，2整PE认证与稀疏pdata/70B分账；没有新游戏native/请求/保存重载。War在仅缓存原始产物封actual合同和delivery，之后Val完整raw独审，任何后继采集须另立精确范围/source gate，不自动跟随。R83/R84已接受条件模型保持，v6查找60证据/94JSON/346refs不是60可执行API。

本次发布仅固定选择witness/pin和状态，不冒称root重做全部raw/host/PE/flat审。原历史全文作为后缀、Oct15尾部不变。不打包、不创建自动化/新会话，继续原统一验证和宣战/议和逆向。自动审批此前拒绝tmpi03vucy0清理（blocked by policy），保留不换工具重试。

'''
runtime='''2026-10-16 增量：v2真实只读读取已成功，法国1445-05-19暂停时FRA→ENG选定议和收件队列在两次样本中均absent。新增文本配置适配修复已完成8个首次测试与完整源码复核；原R1零RPM失败冻结。唯一R2采样2967RPM/77718B，原始capture/IO完整独审正在进行；当前absence不能回填原请求效果，OS close/fullIO/atomic/lease仍未知。见HANDOFF顶部和work/reports/peace-current-pending-v2-live-controller-20261016-r2/，不重复查询或重载。\n\n'''
war='''2026-10-16 增量：R86首次精确入口采集取得[cc220,cc266)70B/20条。该pdata片段JE→cc32c、末尾fallthrough→cc266均在已拥有范围之外，无CALL/RET，局部控制流未闭；不能作为完整helper或可调用API。原始产物正在仅文件封存和独审，未跟随后继、未调用游戏函数。直接议和队列读取v2的唯一新实采成功，当前FRA→ENG选定inbox absent；仍待完整raw审，且不等于原请求或和平完成。\n\n'''
validation='''2026-10-16 增量：游戏自主重开载入暂停后，v2修复了配置读取的精确profile，8项新增离线测试和完整源码审已通过；唯一新实机只读采样成功，当前FRA→ENG选定议和收件队列absent，完整raw审进行中。此结果不新增外交效果或补齐原120动作结果；48/44/42与全部禁重发规则保持。宣战/议和执行器尚未完成。\n\n'''
prefixes={'HANDOFF.md':handoff,'README(agent).md':short,'docs/runtime-observer-1375.md':runtime,'docs/war-peace-api-1375.md':war,'docs/unified-diplomacy-validation-1375.md':validation}
updates={}
for name,prefix in prefixes.items():
    expected={'bytes':334382,'sha256':'7b72fd86e5f1913bef846d85a9924cc407bc3c9897ed42cbb94ed338b21095d1'} if name=='HANDOFF.md' else None
    old=read(name,expected)
    new=prefix.encode('utf-8')+old
    assert new.endswith(old)
    if name=='HANDOFF.md':
        marker='## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf-8')
        assert marker in old and new[new.index(marker):]==old[old.index(marker):]
    updates[name]=(old,new)
for name,(old,new) in updates.items():
    assert read(name,pin(old))==old
for name,(old,new) in updates.items():
    (ROOT/name).write_bytes(new)
    assert read(name,pin(new))==new
OUT.mkdir()
receipt={'schema':'EU4-CONTINUATION-CHECKPOINT/18','sealed':True,'passed':True,'refs':[{'path':n,'bytes':s,'sha256':h} for n,s,h in refs], 'documents':{n:{'before':pin(o),'after':pin(v),'whole_history_exact_suffix':True} for n,(o,v) in updates.items()},'source_returned':used,'source_cap':8388608,'new_tests_queries_native_requests':0,'scope':'Selected witness acceptance and descriptive checkpoint only; live raw review pending, no recursive flat/host/PE recertification.','Oct15_tail_preserved':True}
raw=(json.dumps(receipt,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
(OUT/'receipt.json').write_bytes(raw)
print(json.dumps({'receipt':{'path':OUT.relative_to(ROOT).as_posix()+'/receipt.json',**pin(raw)},'source_returned':used,'handoff':pin(updates['HANDOFF.md'][1])},ensure_ascii=True))
