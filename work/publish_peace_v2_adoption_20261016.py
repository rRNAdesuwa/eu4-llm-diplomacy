"""Descriptive map/checkpoint adoption of the independent current empty-path review."""
from pathlib import Path
import hashlib,json,copy
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/peace-v2-map-v7-adoption-20261016-r1'
assert not OUT.exists()
journal=[];total=0
CAP=8388608;MANUAL=524288
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(name,p=None):
 global total
 path=ROOT/name;size=path.stat().st_size
 assert 0<=size<=4194304 and total+size+1+MANUAL<=CAP
 with path.open('rb') as f:raw=f.read(size+1)
 total+=len(raw);assert len(raw)==size
 if p is not None:assert pin(raw)==p,name
 journal.append({'path':name,**pin(raw)})
 return raw
def fixed(name,size,sha):return read(name,{'bytes':size,'sha256':sha})
def triple(name,raw):return {'path':name,**pin(raw)}
def parse(raw):return json.loads(raw)
MAP='docs/runtime-capability-map-1375-v6.json'
CAND='work/candidates/peace-current-pending-observer-1375-v2/'
REV='work/reports/peace-current-pending-v2-live-independent-review-20261016-r2/'
LIVE='work/reports/peace-current-pending-v2-live-controller-20261016-r2/'
old_raw=fixed(MAP,13516,'54a7595b07dfa161aa53a5fb59247cf263a6dd9cab18dc72b7cf0d446297fb25')
review_raw=fixed(REV+'findings.json',6495,'dc511e9549891bd56f3d5eade28fd220db7420d8303879918f9b9ca1e3489a7e')
review_manifest=fixed(REV+'manifest.json',16101,'76dc493bc241b6ab7cec22c7acf9ab56012a565d82ba06e109366bee1b41f2ae')
review_check=fixed(REV+'verification.json',13493,'6b5d6ae8b07349ab6f9fd1fae4fa645966c314f9d76ddaf94eb6964fce0424a5')
corr_raw=fixed(REV+'accounting-corrigendum.json',8567,'c8322dd6351dfaf9f5efe889b270abc283c55d03e49d19cfa61d8f06ae220acb')
completion=fixed(REV+'completion.json',1888,'0a4568e28b69d34e39da928d8cdf70ce3d67cabd56fc9bad21220180fb894b6e')
canonical_raw=fixed(CAND+'source-manifest.json',8850,'ece6b12d71aca0743bbac575447e32c333aaf64135ae283a8e0b987e9fbf0f1c')
cli_raw=fixed(CAND+'peace_current_pending.py',24249,'94faa085cc982230717f42b43b24bd777a26493a0cf18d2dc3c2cbfc23a7491d')
receipt_raw=fixed(LIVE+'receipt.json',421298,'44c1eeab3ca7fe25dc54a3087a208dbebd9bce23f5118e372d16ebc1ee435583')
actual_raw=fixed(LIVE+'actual-manifest.json',27958,'ac63b83d63b2e8b469e0db0d568d88fecae96dde7a5ebe466bb80fa64b51f283')
source_raw=fixed(LIVE+'source-manifest.json',8861,'803d619df53c33b8698e78283c3ad223a61319c87b4a40ccaae732997d225127')
build_sup=fixed('work/reports/support-heir-current-controller-source-authorization-20261016-r1/authorization.json',10852,'79ecd0456ecd8d99a8bc215313e610cc297be2075ae0042d2a12a76415cdd3a9')
build_nat=fixed('work/reports/war-peace-api-20261016-r87-root-source-authorization/authorization.json',9003,'5cae443d9a4e7250c083d7b97268e4a57d46da0d714f3cb0c0ca16fe13c75bfe')
old,review,canonical,receipt=map(parse,(old_raw,review_raw,canonical_raw,receipt_raw))
assert review['sealed'] is True and review['passed'] is True and review['blocking_findings']==[]
assert review['status']=='selected_peace_queue_absent' and review['current_selected_queue_state_observed'] is True
assert review['selected_queue_presence'] is False and review['counts']['queue_nodes']==0
assert review['subject_receipt_pin']==triple(LIVE+'receipt.json',receipt_raw)
assert review['subject_actual_manifest']==triple(LIVE+'actual-manifest.json',actual_raw)
assert review['subject_source_manifest']==triple(LIVE+'source-manifest.json',source_raw)
assert receipt['control_passed'] is True and receipt['current_state_observed'] is True
assert canonical['sealed'] is True and canonical['runtime_capture_authorized'] is True
assert len(canonical['source_pins'])==41
assert old['accepted_entry_count']==5 and old['pending_active_world_reader_count']==2 and len(old['tools'])==7
assert old['tools'][-1]['id']=='peace_current_pending_queue_pending_active_world'
new=copy.deepcopy(old)
new.update(schema='EU4-READONLY-TOOL-DISCOVERY/7',accepted_entry_count=6,pending_active_world_reader_count=1,
 previous_discovery=triple(MAP,old_raw),
 discovery_build_scope='Exact previous map, pinned v2 CLI/canonical metadata and completed non-author source/production/live witnesses. Other six tool records remain identical. No CLI/tests/process/PE/real configuration or recursive graph reads during map publication.')
entry=copy.deepcopy(old['tools'][-1])
entry.update(id='peace_current_pending_queue_v2_empty_path_verified',entry=CAND+'peace_current_pending.py',entry_pin=pin(cli_raw),
 manifest=CAND+'source-manifest.json',manifest_pin=pin(canonical_raw),manifest_direct_pin_count=41,
 guide=CAND+'REVIEW_STATUS.md',source_graph_sha256=canonical['source_graph_sha256'],
 maturity='source_production_and_real_empty_recipient_queue_path_reviewed',
 real_capture_scope='One R2 FRA->ENG selected target inbox query on paused1445-05-19; two complete ENG empty-header samples. No node/action body was reached.',
 real_world_empty_queue_path_verified=True,real_world_queue_decoder_verified=False,active_peace_body_observed=False,
 scope='Current selected actor->target inbox presence/absence/unknown profile. Real validation covers empty target queue only; nonempty action decoding has offline evidence, not a positive runtime sample.',
 current_only=True,native_ready=False,original_request_effect_verified=False,peace_completed=False,persistence_verified=False,
 previous_reader={k:old['tools'][-1][k] for k in ('entry','entry_pin','manifest','manifest_pin','guide')},
 independent_live_review=triple(REV+'findings.json',review_raw),independent_live_review_manifest=triple(REV+'manifest.json',review_manifest),
 independent_live_review_verification=triple(REV+'verification.json',review_check),
 independent_live_accounting_corrigendum=triple(REV+'accounting-corrigendum.json',corr_raw),
 actual_capture=review['subject_capture_pin'],actual_receipt=review['subject_receipt_pin'],actual_source_manifest=review['subject_source_manifest'],
 verified_empty_path_counts=review['counts'],
 source_graph_scope='41 canonical source pins; runtime adds two review witnesses. Exact R2 text adapter controller separately binds raw configuration metadata; original v1/R1 attempts remain frozen.',
 runtime_controller_source_manifest=review['subject_source_manifest'],
 limitations=['Current absence is not native rejection, AI response, original effect, settlement or peace completion.',
 'No live node/action body or positive queue decoding validation.',
 'Normal context/heldNone does not prove OS CloseHandle return; lease/ABA/atomic/persistence remain unproved.',
 'Exact intercepted file API coverage only; full OS/import/cache/native/delegated IO closure unknown. Discovery grants no execution permission.'])
# Replace stale v1-only review pointers with the pinned v2 canonical provenance.
entry['independent_source_review']=canonical['independent_source_review']
entry['production_review']=canonical['production_review']
entry.pop('first_production_check',None)
new['tools'][-1]=entry
assert new['tools'][:-1]==old['tools'][:-1]
assert (new['historical_effect_signals'],new['historical_persistence_aggregate'],new['remaining_repair_candidates'])==(48,44,42)
assert new['authoritative_for_permissions'] is False and new['all120_effects_complete'] is False
assert not (ROOT/'docs/runtime-capability-map-1375-v7.json').exists()

handoff='''## 2026-10-16 最新继续点：议和v2当前空队列路径完整独审通过；工具表v7；支持继承人和R87新源码交叉审中

游戏自主重开、处理提示、载入法国1445-05-19暂停已完成，无需再要求用户守候点击或保持前台。R2新配置profile的唯一实机查询已被完整非作者raw/IO/claim审接受：findings6495Bdc511e9549891bd56f3d5eade28fd220db7420d8303879918f9b9ca1e3489a7e，manifest16101B76dc493b…，verification13493B6b5d6ae8…（78flat PASS/all shells collected）。2967条/77718B原始RPM全部独立重放：entryPE1+host46×2+code4×2+sample1433×2；两个1380表及FRA122/ENG46完整handles/type/header绑定均核，目标ENG队列两次全零21B header重读，没有node/action体。只能接受当前empty-target-path，不能声称两国队列都空、阳性body实测、原请求拒绝/AI接受或和平完成。raw scalar1继续meaningunknown。

独审IO重算host2302461254B=9主pass2302453278+两次observer manifest3988；额外请求131074B。game3整hash115387512B/115attempt、文件首8192已含hash，RPM entry8192另账；ordinary92044380/controller含seal4728545；配置只读length/SHA/accepted/closed metadata，无值泄露。独审先前1预览+2正式断言失败全部保留，原findings资源估计不改，新增accounting-corrigendum8567Bc8322dd6…给完整upper19198112<32MiB/retained3869235<8MiB；无重status/作者执行/PE/真实env。OS CloseHandle、fullIO、lease、ABA/atomic仍未知。旧R1 UNKNOWN0RPM永久冻结。

新描述性工具表docs/runtime-capability-map-1375-v7.json只替换peace记录为v2的已验空路径，accepted6/pending1；其他6records与v6逐字段相同，stable15/98pins与48/44/42不变。不是6个新的外交executor或效果。v2 REVIEW_STATUS新增限定current验收，原历史段作为后缀；map不是执行许可，原once claim不能重跑。

root新support source-only grant10852B79ecd045…（support-heir-current-controller-source-authorization-20261016-r1）已由D构建source-manifest16257B3d70675a…/49flat、controller14771Bfc8206ff…/child13435Bb5980332…/contract9160Bf58ae024…、原7297Bb1d44aff adapter逐字节复用。4新增fake各once首PASS，sourceupper5419256<32MiB/Job2active0，两个freeze前准备错误保留，无真实env/PID/CLI。冻结supportreader无233e064==-1限制；entry8192仍源码声明/无rawjournal，与shared4096/512KiB分账；不patch Held。其冻结正常路线只一次disk_identity，因此新控制器按实际1..3次已完整hash/EOF/close门禁，不能凭空写3次。War接完整非作者source/case审；还没有support新实际grant或query。未来选择仅metadata为98548/create01dd5d0e670312c4/FRA-POL，fresh held guard仍必须。

R86实际70B作者合同已封但Val完整非作者actual审仍在进行；native_ready/ownership/wholecallee均false。Val初核新增SAR3值域精度：RAX取值只能在[0,0fffffffffffffff]或[f000000000000000,ffffffffffffffff]，不能等1fffffffffffffff，因此JEcc32c仅语法边，普通顺序不可取；此点待最终独审精度项，旧overapprox不改。root R87 source-only grant9003B5cae443d…明确固定[cc266,cc366)256B、9条pdata1251..1259/108B、cc266 exact1253必要；cc32c仅显式hypothetical/syntactic seed，其pdata gap可记录unknownfunctionmeta而不抑制固定raw采集，非新function/ABI/可达性证明，不泛化其他seed、不search/fallback。九helper保持，新cfg/main/hardJob launcher及4新synthetic首PASS正在封交付，D接非作者source/case审；R86full审+新sourcepeer+root另once actualgrant之前没有新PE/engine/decoder/采集。原R86/R87plan/grant不回写精度历史。

当前没有新增外交请求/native/效果/保存/重载。全部120效果和宣战/议和执行器尚未完成，继续原工作，不打包。原成功/派发/unknown/未闭拥有权禁止重发。发布只接受固定非作者见证与精确subjects，未递归重审host/PE/旧来源图；所有旧文作为后缀、Oct15尾部保持。自动审批此前拒绝tmpi03vucy0清理（blocked by policy），保留不换工具重试。

'''
short='''2026-10-16 更新：议和队列v2的唯一实机空目标队列路径已通过完整原始读数复核；[工具表v7](docs/runtime-capability-map-1375-v7.json)现在列6个已验入口、1个待对局验证入口。FRA→ENG当前目标队列为空，不证明过去请求结果，非空记录尚无阳性实测。支持继承人新控制器和议和helper固定窗口的新源码正交叉审查，尚无新查询/采集许可。游戏重开载入暂停已完成，继续原逆向；历史状态保留，见HANDOFF顶部。\n\n'''
guide='''当前空目标队列路径已通过完整实机原始读数复核。唯一R2查询在法国1445-05-19暂停中读取FRA→ENG目标收件队列，两次header均空，2967条/77718B RPM全部独立重放。非空node/action体未到达，不能当阳性记录解码实测，更不能证明旧请求拒绝、AI接受或议和完成。\n\n新配置适配器的8个新增用例及完整源码审已通过；原reader的6个新增用例、生产审和旧失败历史保持。固定身份/暂停/源码/代码/句柄/队列双遍和退出后提交门禁保留。OS CloseHandle返回、全OS IO、atomic/ABA/lease仍未证。现有R2 once claim已使用，不得重跑；后续读取须独立选择与预算门禁，不要求游戏前台或保存重进。\n\n完整实采独审：../../reports/peace-current-pending-v2-live-independent-review-20261016-r2/findings.json\n工具表：../../../docs/runtime-capability-map-1375-v7.json\n\n下方为此前生产验收时点，保留为历史。\n\n'''
runtime='''2026-10-16 当前验收：议和v2空目标队列的唯一实采及2967条原始读数已完整独审通过，详见[工具表v7](runtime-capability-map-1375-v7.json)。已验入口6/待有效对局入口1；非空议和记录仍只有离线覆盖，当前absence不能回填原请求效果。支持继承人新controller的4新增边界case通过，交叉源码审进行中，无新query。下方为历史时点。\n\n'''
validation='''2026-10-16 当前验收：议和v2的当前空目标队列路径已完成实采和完整raw/IO独审，纳入[工具表v7](runtime-capability-map-1375-v7.json)。该读取没有新增外交效果，120逐行动效果与执行器仍未完成，48/44/42和禁重发保持。支持继承人controller的4新增case通过，尚待源码独审及单次实采授权。下方旧pending记录为历史。\n\n'''
prefixes={'HANDOFF.md':handoff,'README(agent).md':short,CAND+'REVIEW_STATUS.md':guide,'docs/runtime-observer-1375.md':runtime,'docs/unified-diplomacy-validation-1375.md':validation}
updates={}
for name,prefix in prefixes.items():
 expected={'bytes':338872,'sha256':'3bf4439df35c854975f7ef41074c23f967ebe1a43377a0c49c6e97ffc9b280b1'} if name=='HANDOFF.md' else None
 prior=read(name,expected);after=prefix.encode('utf-8')+prior
 assert after.endswith(prior)
 if name=='HANDOFF.md':
  marker='## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf-8')
  assert after[after.index(marker):]==prior[prior.index(marker):]
 updates[name]=(prior,after)
before={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in journal}
for name,p in sorted(before.items()):read(name,p)
assert total+MANUAL<CAP
OUT.mkdir()
map_raw=(json.dumps(new,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
map_path=ROOT/'docs/runtime-capability-map-1375-v7.json'
with map_path.open('xb') as f:f.write(map_raw)
for name,(_,after) in updates.items():
 (ROOT/name).write_bytes(after)
 read(name,pin(after))
read('docs/runtime-capability-map-1375-v7.json',pin(map_raw))
adoption={'schema':'EU4-DESCRIPTIVE-MAP-CURRENT-EMPTY-PATH-ADOPTION/1','sealed':True,'passed':True,
 'map':triple('docs/runtime-capability-map-1375-v7.json',map_raw),'previous':triple(MAP,old_raw),
 'accepted_live_review':triple(REV+'findings.json',review_raw),'accounting_corrigendum':triple(REV+'accounting-corrigendum.json',corr_raw),
 'scope':'Complete non-author live raw review accepted for current empty target queue only; root binds selected source/canonical/receipt subjects, not a repeated recursive source/PE/host audit.',
 'other_six_records_exact':True,'new_effects_requests_native_tests_queries':0,'permission_authority':False,
 'documents':{n:{'before':pin(b),'after':pin(a),'history_exact_suffix':True} for n,(b,a) in updates.items()},
 'Oct15_tail_preserved':True,'source_returned':total,'manual_allowance':MANUAL,'source_upper':total+MANUAL,'source_cap':CAP,'read_journal':journal}
raw=(json.dumps(adoption,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
with (OUT/'receipt.json').open('xb') as f:f.write(raw)
print(json.dumps({'receipt':triple(OUT.relative_to(ROOT).as_posix()+'/receipt.json',raw),'map':triple('docs/runtime-capability-map-1375-v7.json',map_raw),'handoff':pin(updates['HANDOFF.md'][1]),'source_upper':total+MANUAL},ensure_ascii=True))
