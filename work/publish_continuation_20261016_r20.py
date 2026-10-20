from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/continuation-publication-20261016-r20'
assert not OUT.exists()
used=0;journal=[];CAP=8388608
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(n,p=None):
 global used
 path=ROOT/n;s=path.stat().st_size
 assert 0<=s<=4194304 and used+s+1<=CAP
 with path.open('rb') as f:b=f.read(s+1)
 used+=len(b);assert len(b)==s
 if p is not None:assert pin(b)==p,n
 journal.append({'path':n,**pin(b)});return b
refs=[
 ('work/reports/support-heir-current-live-controller-20261016-r1/receipt.json',422909,'11a394513bef7b810b9262b5373610207991ecd10cc7e9d9440c2767997b75b3'),
 ('work/reports/support-heir-current-live-controller-20261016-r1/actual-manifest.json',34688,'83fe5ba2a6aa40eaffabd92f6a64aec4deb76dfc7b29bdfc998e2f4c1e4f94ce'),
 ('work/reports/support-heir-current-live-controller-20261016-r1/live-completion-corrigendum.json',2391,'e50f7135d51eac5ca000c29eeac0651625cc396f2d837fdb5db0a11b225e3ac6'),
 ('work/reports/war-peace-api-20261016-r87-dual-frontier-source/launcher-receipt.json',26964,'b5386af3613ed128d1aed7bcf26b2282ba7a49999e6ee10cf82db99ff659ee13'),
 ('work/reports/war-peace-api-20261016-r87-dual-frontier-source/actual-sealed-r1/actual-manifest.json',34662,'71e766158fdaf6f80a2dc55bf5c4fb8177bfcfcdaee35f1f7860c1fec0828b0d'),
 ('work/reports/war-peace-api-20261016-r87-dual-frontier-source/actual-sealed-r1/contract.json',7679,'5e114f5c0efd47cbf92279bdf0d638732a40ae3b8a9d0f554d56c51df2304845'),
 ('work/reports/war-peace-api-20261016-r86-root-actual-acceptance/findings.json',1102,'219391521cb71ca196cf318ed2525680db114ead6a94036f81565724e2342d59'),
 ('work/reports/war-peace-api-20261016-r88-c9d60-cache-metadata/findings.json',1900,'37b737b926ca54c0a750e17038c1625851edfce8860eba396be0349d01cba43a'),
 ('work/reports/war-peace-api-20261016-r89-root-source-authorization/authorization.json',9647,'c6e844b1d6f8e635d673caab18c5c2eade3c7faa2fa8109810f3bb95f003f012')]
data={n:read(n,{'bytes':s,'sha256':h}) for n,s,h in refs}
support=json.loads(data[refs[0][0]]);job=json.loads(data[refs[3][0]])
assert support['status']=='selected_task_absent' and support['control_passed'] is True and support['status_attempts']==1
assert job['passed'] is True and job['all_shells_collected'] is True
text='''## 2026-10-16 最新继续点：两个当前读取均成功；peace已完整独审/工具表v7；support与R87实际交叉独审中；R89仅source构建授权

用户要求重开已处理完成：当前98548/create01dd5d0e670312c4，法国1445-05-19暂停，window78056306。原38076在Stop前已不存在，root未实际kill。已自主确认成就提示，不能再要求用户守候点击，也不需游戏保持前台。没有后续UI输入、保存、冷重载或时间推进。

Peace v2唯一R2 current查询已完整非作者接受，工具表v7已发布：17565B137abeb35de8f6040cdcd3c5debe6d20ce91e4a3fdf149bed7b5bab7964591cc；accepted6/pending1，其他6条记录与v6一致，阳性node/action body未实测。FRA→ENG目标队列两次全零header，2967RPM/77718B；findings6495Bdc511e95…/78pin verification13493B6b5d6ae8…，完整独审账上界由corrigendum8567Bc8322dd6…校正为19198112<32M，历史估计/所有失败保留。Map/root adoption receipt11623B2cca5dfb…（peace-v2-map-v7-adoption-20261016-r1）。当前absence不证明原请求拒绝、AI回应、和平完成或效果；原R1配置文本拒绝UNKNOWN0RPM与旧v1全部冻结。

Support新controller source已完整非作者PASS：War findings36102B99e4496a…/manifest33412Ba39124ca…/verification25019Bf49e428b…，49flat源前后；root只读授权4573B102fa82e2ce6da0ae393c53940defe9f265edee7d410766951119dc7aa3a6cde已由D唯一使用。目录support-heir-current-live-controller-20261016-r1：capture708665Ba974a7e1…/childio377024B5e82ca39…/receipt422909B11a39451…/actualmanifest34688B83fe5ba2…。结果selected_task_absent/errors[]/两样本相等、context正常/heldNone后commit。共享2990RPM/55844B/最大11040；entry1×8192仅冻结源码声明、未journal，不能补造或当完整总RPM。Val当前初核两方向140容器count/cap0且key_present=false，是missing_key，非matchedNULL，也没有P64B body阳性验证。normalOS CloseHandle返回仍未知。

Support普通69093511B/host2302461254B(9主pass+2extra3988)/game38462504B恰1完整hash、配置1snapshot226B只记length/SHA/closed。Controller含seal4606571<32M；Job2active0exit0/peak48107520/all shell collected。作者retained reads3889171+262144reserve=4151315<8M；sourcebuild5419256另账。Completion16575Bb949815e…/delivery5356B23901de8…及corrigendum2391Be50f7135…/finalsummary1018B886efb07…均已封。preview工具截断、sealer执行完后JS.then尾错均留痕未重执行；自有sealer memory API返回0未校验，corrigendum明确null/未验证，不混真实Job峰。Val正在新support-heir-current-live-independent-review-20261016-r1 fullraw/IO审；完成前mapv7不升pending计数，当前任务缺席不加继承人/原请求效果。

R86 actual70B完整非作者PASS已被root接受：Val findings5580B550c1edf…/manifest12748B5af832bd…/61pin pincheck14219Be67988e3…，precision1713B2c4fab90…；rootacceptance1102B21939152…。SAR3正常值域排除1fffffffffffffff，JEcc32c不正常可取，旧语法overapprox不改。原slice无RET/wholecalleefalse，接受是raw合同与精度，非native许可。

R87新source经D完整非作者PASS62pins，root rawfrontier review5243B3cf18ea8…/manifest7876Bb01c759c…（root自己的next_pdata_record KeyError已保存failure-r1、只改实际next键和累计账upper2034174<8M，无target重试）。新root一次静态grant6091Be987bf04dd347227af77bcf0db5cf850b9d953bc208f95652c5df16375014439已由root唯一launch_once执行，chunkc57ad6 exit0/.9564s/no session，完整outer tool result另存exec-tool-witness。Producer原stdout/stderr这次已retained。capture140752B0f4ab901…/owned1099Bdd4d12d2…，raw256 SHA0e0232ea…；launcherreceipt26964Bb5386af3…passed/Job2active0exit0/.594s/peak25493504/parent1058487+child17772050=18830537<32M；PE双SHA+108metadata+256raw=76925372。61rows210decoded、915lookahead224union691overlap，46B[cc338,cc366)未解码，1RETcc32b/INT3cc331与cc337、6CALL5targets。1257实际覆盖cc32c6B，本次未用gap例外；它仍只是假设seed，不证明从R86正常可达。

R87作者actual-sealed-r1已封：actualmanifest34662B71e76615…/contract7679B5e114f5c…/selectedCFG47217B659b8046…/rawreplay13889B9de0e073…/filecheck20081B232a2b1e…。作者首次sealer review_pins flat-schema KeyError已保存source/工具stderr和1310720B失败读账，仅窄修封存映射，不改任何producer/capture或重actual；own sourceupper5784217/retained1215906<16M。三零header+D0可在ABI/有效S/栈/noalias/noheader mutation等前提下推950b0(RCX8)正常返回S后MOV[S]=freshM64[E]，再1a35750(S,0,0)，最后c9d60(C,S,1,1)。950b0只是unknown allocation candidate；1a35750即使R8=0也不证无副作用；c9d60 header/ownership仍未知。RAX取slot后restoreR14、home保存F+20/50/58/60与四POP/RET到Q+8都保留条件，原localCFG/wholecallee/native/ownership false。D当前在r87-actual-independent-review做完整非作者raw/合同审，不能先升级。

R88只在两个固定cache functions字典查exactkey0xc9d60均absent，findings1900B37b737b9…/manifest2625Be3aa44d7…，sourceupper7201562<8M；不证明其他key/cache或整个binary不存在，也未语义读取callee体。Raw E8 cc305/nextcc30a−9642→c9d60/owned[159,164)已独立复算。D新R89 proposal15747B5aa951e2…/manifest4689B89068eef…14小源前后、upper1753609<8M，无PE/engine/大cache重读。rootsourcegrant9647Bc6e844b1d6f8e635d673caab18c5c2eade3c7faa2fa8109810f3bb95f003f012/receipt7712B42d43b23…已准War仅构建r89-c9d60-source：固定[c9d60,c9e60)256单seed，<=29search+3diagnostic pdata<=32/384仅诊断、不从extent选窗；valid ordered gap可按新显式政策记unknownfunctionmeta，invalid/incomplete仍unknown0code，禁止fallback/新窗/追callee/data/unwind。九helper与CFG/Job继承，旧cc32c语义不得沿用。最多4新synthetic metadata/单seed case freeze后各once；最终上游门禁须等真实R87 fullfindings schema再冻结，不伪造fullreview。R89无actual授权/PE/decoder/游戏访问。

当前并行：Val fullSupport actual；D fullR87 actual；War R89 source构建（待真实R87 review schema），root发布/门禁与下一步。根目录源码只新建有界脚本/报告，stable15/98pins、48effects/44historical persistence/42repair保持；原120逐行动效果、宣战/议和executor未完成。没有外交请求/native调用/新效果，原成功/派发/unknown/未闭拥有权禁重发，不打包/不建自动化。不因里程碑停工。全文历史作为后缀、Oct15尾部不变；自动审批曾拒绝tmpi03vucy0清理（blocked by policy），保留不换工具重试。

'''
short='''2026-10-16 更新：重开载入暂停已完成，议和队列v2空路径完整独审通过，[工具表v7](docs/runtime-capability-map-1375-v7.json)为6已验/1待实采验收。支持继承人当前缺项读取也已成功，正在独立raw复核，尚不增加效果。静态逆向取得正常返回与条件载荷写入，最终header/ownership更新仍待c9d60；新256B前缀采集器只在源码构建，无新实际许可。详情见HANDOFF顶部，旧状态保留。\n\n'''
war='''2026-10-16 最新：R86 raw与SAR值域精度已完整独审接受。R87固定256B新采集成功并封作者合同，正常RET、R14保存恢复及三零header下条件payload写入已定位，最终c9d60 header/ownership仍未知；完整raw审进行中，native_ready保持false。R89固定[c9d60,c9e60)256单seed仅source构建授权，不从pdata extent选窗、不自动追callee。当前两个只读查询成功，无外交请求或新native调用。\n\n'''
runtime='''2026-10-16 最新：议和v2空目标队列完整独审通过；支持继承人FRA-POL当前双向140索引missing-key两样本读取也成功，共享2990/55844B，entry8192只是独立源码声明非journal，阳性body未读。Support完整raw审进行中，目录仍为[工具表v7](runtime-capability-map-1375-v7.json)的6已验/1待验。当前缺席不回填原请求或最终heir效果；不需前台/保存重进。\n\n'''
updates={}
for n,prefix in {'HANDOFF.md':text,'README(agent).md':short,'docs/war-peace-api-1375.md':war,'docs/runtime-observer-1375.md':runtime}.items():
 expected={'bytes':343002,'sha256':'19d95848d0957d090fcf2762c9246944b0e1d60095ecee4d58dabecc142a6ac0'} if n=='HANDOFF.md' else None
 old=read(n,expected);new=prefix.encode('utf-8')+old;assert new.endswith(old)
 if n=='HANDOFF.md':
  marker='## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf-8');assert new[new.index(marker):]==old[old.index(marker):]
 updates[n]=(old,new)
before={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in journal}
for n,p in sorted(before.items()):read(n,p)
for n,(_,new) in updates.items():(ROOT/n).write_bytes(new);read(n,pin(new))
OUT.mkdir()
receipt={'schema':'EU4-CONTINUATION-CHECKPOINT/20','sealed':True,'passed':True,'selected_refs':[{'path':n,'bytes':s,'sha256':h} for n,s,h in refs],
 'documents':{n:{'before':pin(b),'after':pin(a),'history_exact_suffix':True} for n,(b,a) in updates.items()},
 'source_returned':used,'source_cap':CAP,'Oct15_tail_preserved':True,'target_queries_tests_native_requests_in_publication':0,
 'scope':'Selected producer and accepted-review witness checkpoint only; support and R87 full raw review still pending. No repeated PE/engine/host/cache/candidate audit.'}
raw=(json.dumps(receipt,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii');(OUT/'receipt.json').write_bytes(raw)
print(json.dumps({'receipt':{'path':OUT.relative_to(ROOT).as_posix()+'/receipt.json',**pin(raw)},'handoff':pin(updates['HANDOFF.md'][1]),'source_returned':used},ensure_ascii=True))
