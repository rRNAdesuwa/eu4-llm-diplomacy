"""Accept independent offline v6 evidence and record the separate UI recovery."""
from pathlib import Path
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/continuation-publication-20261016-r15'
LIMIT = 8 * 1024 * 1024
events = []
raws = {}

def pin(b):
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def read(rel, phase):
    p = ROOT / rel
    assert p.stat().st_size <= 4 * 1024 * 1024
    b = p.read_bytes()
    events.append({'path': rel, 'phase': phase, **pin(b)})
    assert sum(e['bytes'] for e in events) + 2 * 1024 * 1024 < LIMIT
    return b

fixed = {
 'work/reports/war-peace-api-lookup-v6-independent-review-20261016-r1/findings.json': (6894, '9faa862891553f821391d2fd81cb472a7bdd85c94fa9e370013a1cc76615d158'),
 'work/reports/war-peace-api-lookup-v6-independent-review-20261016-r1/manifest.json': (30873, 'dfff924ef6bd84a2f7e47937510c4b240e192e7578a8e28fba177e4639fa644a'),
 'work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json': (25179, '9e292ce2c077be0af996bad24ba44dab98ea88566726f88cd36093fc45828765'),
 'work/candidates/war-peace-api-lookup-1375-v6/author-manifest.json': (86208, '4bfd8b13053dfc3880e8190db329f8ce8c343b6c4137198b16c1133a57b9e979'),
 'work/candidates/war-peace-api-lookup-1375-v6/publication-manifest.json': (5910, 'b75c189e30de5ab171e32559d069bc8211cfa65fb48fbce3b229eeb8a68b162c'),
 'work/candidates/war-peace-api-lookup-1375-v6/war_peace_lookup.py': (3602, '7994ff7b4e3454b98f55919e786cd1582b8c320c650e94f01f3c20b078e43c0f'),
 'work/candidates/war-peace-api-lookup-1375-v6/index.json': (221073, 'ad458026ced277c44170ed4ea36773c3c3176a5561a714ad961d713efc525e8f'),
 'work/candidates/war-peace-api-lookup-1375-v6/data-manifest.json': (18868, 'a45e5bda390f83f956e387638607a86509ac1a8a76a966372067accfe38ed778'),
 'work/candidates/war-peace-api-lookup-1375-v5/query_engine.py': (16583, 'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'),
 'work/candidates/war-peace-api-lookup-1375-v5/index.json': (185792, 'a8b70f547513def34f88c1dd19e73e573c63fe209aeced61f397db8b22556e6c'),
 'work/candidates/war-peace-api-lookup-1375-v5/data-manifest.json': (14774, '39efa19ba26675647379f6be182b26be727762d5eaf906f0be822b7ca0dba69c'),
 'work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1/receipt.json': (64309, '20286c76b9037200cb616c4571b5f185c7c531583a27a833ee0893e7f922a79e'),
 'work/reports/war-peace-api-20261016-r82-independent-review/findings.json': (5208, 'ee0bc195fce64d9d6f62271a2e49feeb849d0954f6a7d52fd519adf060e8dcb3'),
 'work/reports/war-peace-api-20261016-r82-independent-review/manifest.json': (24830, '96a251f4bd3bf62bbff02fbbff2a6bb07e89ac85ccf65c3c8ecc0239a3a8077c'),
 'work/reports/war-peace-api-20261016-r82-selector-cached-use-crosswalk/crosswalk.json': (21151, '4a7c8b64ed150a97449abaca1fe868b1c03a3afb5baae27699c4e50e59530ffe'),
 'work/reports/peace-current-pending-observer-live-after-restart-20261016-r2/capture.json': (71780, '6c25eb2b08b220191b7683d9b26f965b37ab14ea5424aab048d0894be5416250'),
 'work/reports/peace-current-pending-observer-live-after-restart-20261016-r2/receipt.json': (6232, '2a82a211a1b048a6bbdf41458bccb64aad25aa681f903eeade24b47106559370'),
 'docs/runtime-capability-map-1375-v5.json': (13350, '30b254ed226e0e073ac65982fde1e145bd3c8d4f8d44a266b279026b61935759'),
}
for rel, expected in fixed.items():
    b = read(rel, 'fixed_before')
    assert (len(b), pin(b)['sha256']) == expected, rel
    raws[rel] = b

def obj(rel):
    return json.loads(raws[rel])

review = obj('work/reports/war-peace-api-lookup-v6-independent-review-20261016-r1/findings.json')
assert review['sealed'] and review['passed'] and review['blocking_findings'] == []
for key, rel in [
    ('subject_source_manifest', 'work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json'),
    ('subject_author_manifest', 'work/candidates/war-peace-api-lookup-1375-v6/author-manifest.json'),
    ('subject_publication_manifest', 'work/candidates/war-peace-api-lookup-1375-v6/publication-manifest.json'),
    ('subject_first_query_receipt', 'work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1/receipt.json'),
    ('subject_wrapper', 'work/candidates/war-peace-api-lookup-1375-v6/war_peace_lookup.py'),
    ('subject_index', 'work/candidates/war-peace-api-lookup-1375-v6/index.json'),
    ('subject_data_manifest', 'work/candidates/war-peace-api-lookup-1375-v6/data-manifest.json'),
]:
    assert review[key] == {'path': rel, **pin(raws[rel])}
assert all(v is True for v in review['checks'].values())
assert all(v is False for v in review['authority'].values())
new = obj('work/candidates/war-peace-api-lookup-1375-v6/index.json')
old = obj('work/candidates/war-peace-api-lookup-1375-v5/index.json')
newrows = {e['id']: e for e in new['entries']}
oldrows = {e['id']: e for e in old['entries']}
assert len(newrows) == 60 and len(oldrows) == 59
assert set(newrows) - set(oldrows) == {'peace.generator_selector_callee'}
gen = 'peace.generator_divisor_source'
assert all(newrows[k] == v for k, v in oldrows.items() if k != gen)
assert set(newrows[gen]) - set(oldrows[gen]) == {'later_checked_context', 'historical_base_scope'}
assert all(newrows[gen][k] == v for k, v in oldrows[gen].items() if k != 'evidence')
assert newrows[gen]['evidence'][:len(oldrows[gen]['evidence'])] == oldrows[gen]['evidence']
data = obj('work/candidates/war-peace-api-lookup-1375-v6/data-manifest.json')
olddata = obj('work/candidates/war-peace-api-lookup-1375-v5/data-manifest.json')
assert len(data['sources']) == 94 and len(olddata['sources']) == 74
assert all(data['sources'][k] == v for k, v in olddata['sources'].items())
source = obj('work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json')
assert len(source['files']) == 125 and source['selected_JSON_sources'] == 94
assert len(obj('work/candidates/war-peace-api-lookup-1375-v6/author-manifest.json')['files']) == 138
assert len(obj('work/candidates/war-peace-api-lookup-1375-v6/publication-manifest.json')['files']) == 28
queries = obj('work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1/receipt.json')
assert queries['sealed'] and queries['passed'] and queries['error'] is None
assert queries['first_only_no_retries'] and queries['command_count'] == 4
assert queries['combined_physical_explicit_bytes'] == 30469489 < 67108864
r82 = obj('work/reports/war-peace-api-20261016-r82-independent-review/findings.json')
assert r82['sealed'] and r82['passed'] and r82['blocking_findings'] == []
assert r82['subject_crosswalk'] == pin(raws['work/reports/war-peace-api-20261016-r82-selector-cached-use-crosswalk/crosswalk.json'])
live = obj('work/reports/peace-current-pending-observer-live-after-restart-20261016-r2/capture.json')
assert live['status'] == 'unknown' and live['samples'] == [] and live['selected_queue_presence'] is None
assert live['commit_after_context_exit'] is False
assert live['rpm_budget']['calls_attempted'] == 120 and live['rpm_budget']['bytes_requested'] == 10371
assert live['raw_ordered_read_journal'][69]['raw_hex'] == '01000000'
assert live['precheck'] == live['postcheck'] and live['code_before'] == live['code_after']

maprel = 'docs/runtime-capability-map-1375-v6.json'
previous = obj('docs/runtime-capability-map-1375-v5.json')
mapping = copy.deepcopy(previous)
mapping['schema'] = 'EU4-READONLY-TOOL-DISCOVERY/6'
mapping['previous_discovery'] = {'path': 'docs/runtime-capability-map-1375-v5.json', **pin(raws['docs/runtime-capability-map-1375-v5.json'])}
mapping['discovery_build_scope'] = 'Exact previous map, accepted offline v6 owner/review files and fixed v5 engine only. Other six tool records unchanged; no CLI/tests/process or recursive native graph reads during this map build.'
lookup = [i for i, x in enumerate(mapping['tools']) if x['id'] == 'war_peace_static_contract_lookup_v5']
assert lookup == [4]
record = mapping['tools'][4]
record.update({
 'id': 'war_peace_static_contract_lookup_v6',
 'entry': 'work/candidates/war-peace-api-lookup-1375-v6/war_peace_lookup.py',
 'entry_pin': pin(raws['work/candidates/war-peace-api-lookup-1375-v6/war_peace_lookup.py']),
 'guide': 'work/candidates/war-peace-api-lookup-1375-v6/REVIEW_STATUS.md',
 'endpoint_count': 60,
 'manifest': 'work/candidates/war-peace-api-lookup-1375-v6/data-manifest.json',
 'manifest_pin': pin(raws['work/candidates/war-peace-api-lookup-1375-v6/data-manifest.json']),
 'manifest_direct_pin_count': 95,
 'source_manifest': 'work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json',
 'source_manifest_pin': pin(raws['work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json']),
 'source_manifest_direct_pin_count': 125,
 'scope': '60 offline retained evidence records / 94 selected JSON sources; file-only check/catalog/search/lookup, no executable diplomacy API promise',
 'source_graph_scope': 'Existing v5 ea030 engine/96cap unchanged. Original58 rows exact; generator receives explicit later R75/R77 context while historical fields persist; one selected97bd30 R80/R81 machine contract entry.',
 'independent_review': {'path': 'work/reports/war-peace-api-lookup-v6-independent-review-20261016-r1/findings.json', **pin(raws['work/reports/war-peace-api-lookup-v6-independent-review-20261016-r1/findings.json'])},
 'previous_file_lookup': {'entry': previous['tools'][4]['entry'], 'entry_pin': previous['tools'][4]['entry_pin']},
 'permission_authority': 'Exact data-manifest/index/evidence and pinned unchanged v5 Python engine guards; this descriptive map grants no runtime or native execution authority.',
})
assert all(mapping['tools'][i] == previous['tools'][i] for i in range(7) if i != 4)
assert mapping['tools'][4]['query_engine'] == previous['tools'][4]['query_engine']

docs = ['HANDOFF.md', 'README(agent).md', 'docs/war-peace-api-1375.md', 'docs/runtime-observer-1375.md']
old_docs = {rel: read(rel, 'document_before') for rel in docs}
marker = '## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf-8')
assert marker in old_docs['HANDOFF.md']
tail = old_docs['HANDOFF.md'][old_docs['HANDOFF.md'].index(marker):]
head = '''## 2026-10-16 最新继续点：已自主重开/载入并暂停；新只读被233e064值校验拒绝；v6完整独审接受

用户说明游戏整天停在成就警告，要求我自行截图点击，并随后明确“切换回正常屏幕了，游戏似乎已经完全卡死，请重开”。已使用 computer-use skill @oai/sky：截图确认旧窗口 warning，若干点击/键盘没有关闭；曾临时最小化独立dsh桌宠尝试排除遮挡，但未证明其是原因。旧PID38076在 Stop-Process 前的 Get-Process 已报不存在，实际Stop未执行；不能说是root杀掉。之后通过sky启动EU4（首次等待窗口超时，但后来出现Steam not detected modal，正常OK后继续）。新正常主屏UI出现主菜单，Continue France1445-05-19，再点成就警告确定，成功载入；最终截图为France1445-05-19/暂停。没有自动化登录、Windows安全设置、外交请求、保存或额外native调用。UI准备是一次用户要求的恢复载入，与只读controller内reloads0分开。不要再让用户守着点击这个提示。

新唯一after-restart只读status已结束且所有shell collected（session6850 exit0，childexit2/Job2active0/directcollected，peak46,116,864）。固定PID98548/create01dd5d0e670312c4，controller9639B27a7696769ac9101c1a15d9f0d33706c27d7e9867e9c10e259d69dc6b9379cc3 / preparation1746Bc263a1c5ad333f98ac4e8cfdf3bbe28686d3ce0049282c7e7555bf7a5e061277。目录peace-current-pending-observer-live-after-restart-20261016-r2/：capture71780B6c25eb2b08b220191b7683d9b26f965b37ab14ea5424aab048d0894be5416250 /receipt6232B2a82a211a1b048a6bbdf41458bccb64aad25aa681f903eeade24b47106559370 /manifest4114Bb4456b4d3d269a08647749a91d3bef940ee4bca99d26369cda28f98a9d3eda35。结果仍unknown/samples[]/presenceNULL/commitfalse，但本次host type/prepost与两次735B code均通过，fresh countcap1380/manualpause1。sample_1第70条读取module+233e064=01000000/signed1；CLI:280 require==-1 抛“Unsupported current Mod”，在array/handles/queue前拒绝。120RPM/10371B均计预算；OS CloseHandle返回仍未验证，normalexit/heldNone只到既有合同。nonce仍不等installedsession，dll/manifest字段只backend文件元数据；没有安装DLL/Frida或重发任何旧动作。旧R1unknown原像保留。不要再运行status/PIDpoll或改guard；War正在16M file-only完整raw/source独审，明确此错误标签不是已证明installedMod/汉化/多人/模式或缺乏队列。字段语义/native writer/consumer仍未知，需先核证据来源。

API lookup v6 已接受完整非作者审查：Val findings6894B9faa862891553f821391d2fd81cb472a7bdd85c94fa9e370013a1cc76615d158 /manifest30873Bdfff924ef6bd84a2f7e47937510c4b240e192e7578a8e28fba177e4639fa644a，157pins。Root这次只验固定review subjects、old/new JSON equality与map更新，不冒称自己重审157flat。candidate source25179B9e292ce2c077be0af996bad24ba44dab98ea88566726f88cd36093fc45828765 /author86208B4bfd8b13053dfc3880e8190db329f8ce8c343b6c4137198b16c1133a57b9e979 /publication5910Bb75c189e30de5ab171e32559d069bc8211cfa65fb48fbce3b229eeb8a68b162c /index221073Bad458026ced277c44170ed4ea36773c3c3176a5561a714ad961d713efc525e8f /data18868Ba45e5bda390f83f956e387638607a86509ac1a8a76a966372067accfe38ed778 /wrapper3602B7994ff7b4e3454b98f55919e786cd1582b8c320c650e94f01f3c20b078e43c0f。60records/94JSON/346refs，不是60可执行API。old58全字段保持、gen仅2newkeys+evidenceappend，新97bd30仅knownCALL局部machine合同。原v5ea030 engine16583B/96cap/原路径不fork不改，wrapper只hash/rev/helpmetadata。四首queries check/catalog/lookup993570/lookup97bd30各一次全PASS，receipt64309B20286c76b9037200cb616c4571b5f185c7c531583a27a833ee0893e7f922a79e；batch30,469,489<64M，build失败+窄修+seal+delivery累计21,516,548<32M，所有首失败/自己的独审修复原像保留。不得重query/tests/fixtures。新REVIEW_STATUS在冻结图外，mapv6只更新lookup record，其余6record及v1-v5原文件保持。

R82 Val完整非作者首PASS：findings5208Bee0bc195fce64d9d6f62271a2e49feeb849d0954f6a7d52fd519adf060e8dcb3 /manifest24830B96a251f4bd3bf62bbff02fbbff2a6bb07e89ac85ccf65c3c8ecc0239a3a8077c；124pins。4uniqueE8 sites/7refs，3extra97beaa/97ed33/97f1a1；R69 +70/+78 base为postCALL R13/input W条件值，不是R12返回。旧native-owned-peace JSON有/functions/0x97bd30/instructions，不能再说缓存无体。失败补摘snapshot1,302,642B在预算内保留，未重跑/未升语义，authorupper7,902,498<8M。REVIEW_STATUS已在冻结图外。

R83 plan7723B0031d9abbf178797c1391e9658f57cc1a2ee08c34b25c18848ae1e1d73d9dd8e /manifest3496B8ce7b755bb8a4cc7dfc486d4501a04d0685cdbec75a5ce3e5f75402f5c2bd5bc，经root纯缓存授权3127B68a4074ecde549ccbf8da226a2737941faab20fa3a095f04ffbeb91e98aacb5f。只8sources两遍2,845,750B，jointupper3,828,790<4M含planning；native-owned-peace精确selector数组≤64rows/2048rawB、97bea0 indices0..12、relation单AST≤100lines，endpointwriter未知不扩search。D新analyzer首exit0，正在封报告：返回类型/完整端点/O写入身份仍不能提前升级；关系结构桥只在native P确为同一typed C且J确为other正slot等前提下成立。等待final后非作者review，不将作者预览作为新readeradoption。

当前新增effects/nativecalls/requests为0，48/44/42/stable15profiles98pins与禁重发保持。全部120及宣战/议和执行器未完成，继续工作，不在里程碑自行停止；打包误发已撤回，未ZIP/release。自动审批拒绝清理tmpi03vucy0（blocked by policy）保留，不换工具再试。以下旧menu/loading、R80/R81 pending、v5accepted和no-second-status是历史状态，由本段覆盖；Oct15尾部字节保持。

'''

def short(prefix):
    return f'''2026-10-16 最新：[离线API查找v6]({prefix}work/candidates/war-peace-api-lookup-1375-v6/REVIEW_STATUS.md)已通过完整非作者审查，60条证据记录/94固定JSON/346引用，四项首次查询通过，原v5引擎不改。[工具选择表v6]({prefix}docs/runtime-capability-map-1375-v6.json)仅更新这一项。游戏已按用户要求自主重开、处理成就提示并载入France1445-05-19暂停；新只读查询通过宿主校验，但在233e064读值1与预期-1的校验处返回unknown，尚未采样队列。错误标签“Unsupported current Mod”不证明字段含义或安装Mod，正进行文件证据诊断。未新增外交请求或效果。下方旧版本/主菜单/pending状态保留为历史。

'''
new_docs = {rel: (head if rel == 'HANDOFF.md' else short('../' if rel.startswith('docs/') else '')).encode('utf-8') + old_docs[rel] for rel in docs}
# Guide links are relative to docs/, whereas the map already resides there.
for rel in ['docs/war-peace-api-1375.md', 'docs/runtime-observer-1375.md']:
    new_docs[rel] = new_docs[rel].replace(b'(../docs/runtime-capability-map-1375-v6.json)', b'(runtime-capability-map-1375-v6.json)', 1)

statuses = {
 'work/candidates/war-peace-api-lookup-1375-v6/REVIEW_STATUS.md': '''# Offline lookup v6 independently accepted

[Complete non-author review](../../reports/war-peace-api-lookup-v6-independent-review-20261016-r1/findings.json) passed157 pins,94 direct JSON sources and346 JSON-pointer references. Root accepted its exact subjects and independently compared the old/new data and descriptive tool map. This accepts60 offline evidence records, not60 executable diplomacy APIs.

Original58 rows are unchanged. The existing generator row preserves its historical fields and evidence prefix, with explicit later R75/R77 context. One97bd30 entry combines selected R80/R81 machine evidence; whole function extent, object types, handles, bounds, lifetime, amount units, recipient and diplomacy effects remain unknown.

The existing v5 ea030 Python query engine and96-source cap are unchanged at their original path. The wrapper changes only frozen hash/revision/help metadata. Four first queries (check, catalog, lookup993570, lookup97bd30) passed once each; outputs and Job receipts are retained, with no old tests or fixtures rerun. The first build failure and one root-approved builder assertion repair remain preserved. Independent review also preserves its own AST-comparison repair.

Author build/failure/repair/seal/delivery upper21,516,548B stays below32MiB; first-query explicit30,469,489B stays below64MiB. These are explicit source bills, not universal OS/loader IO bounds. Engine aggregate32MiB is successful graph acceptance checked after the next bounded read. Pre/post equality does not prove atomicity or exclude ABA; Job cleanup concerns the new CLI tree, not the game.

No native call, game request, reader adoption, original effect, persistence or lease authority follows. Frozen author manifests retain their historical pending labels; this acceptance status is outside those graphs.
''',
 'work/reports/war-peace-api-20261016-r82-selector-cached-use-crosswalk/REVIEW_STATUS.md': '''# R82 cached use-site crosswalk independently accepted

[Complete non-author review](../war-peace-api-20261016-r82-independent-review/findings.json) passed124 pins. Seven retained raw E8 references represent four unique97bd30 sites, including three additional callers. Duplicate fact/function references are not independent votes.

R69 postCALL +70/+78 uses currentR13, conditionally the original input W. The selector return is copied intoR12; those fields cannot be attributed to the returned object. Local97bea0 return use checks nonzero before +48/+50 access, which still does not authenticate WAR type or ownership. Return0 remains ambiguous.

The old native-owned-peace JSON contains a97bd30 instruction record. Full old-body semantics were not supplied by the failed supplemental extractor; that attempt's1,302,642B snapshot, source, error and claim remain preserved with no retry. Total author upper7,902,498B stays below8MiB.

Typed country/root/full handles and returned WAR/global/opponent identity edges remain unresolved. Offset compatibility and relocated old fixtures are not current-world or effect proof. No new PE/decoder/game/native/read adoption authority is granted.
''',
}

for rel in [maprel, *statuses]:
    assert not (ROOT / rel).exists(), rel
for rel in fixed:
    assert read(rel, 'fixed_after') == raws[rel]
for rel in docs:
    assert read(rel, 'document_prewrite') == old_docs[rel]
OUT.mkdir(exist_ok=False)
outputs = {}

def write_new(rel, b):
    with (ROOT / rel).open('xb') as f:
        f.write(b)
    outputs[rel] = pin(b)

map_b = (json.dumps(mapping, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
write_new(maprel, map_b)
for rel, text in statuses.items():
    write_new(rel, text.encode('utf-8'))
for rel, b in new_docs.items():
    (ROOT / rel).write_bytes(b)
    got = read(rel, 'document_after')
    assert got == b and got.endswith(old_docs[rel])
    if rel == 'HANDOFF.md':
        assert got[got.index(marker):] == tail
    outputs[rel] = pin(got)
gotmap = json.loads(read(maprel, 'new_map_check'))
assert all(gotmap['tools'][i] == previous['tools'][i] for i in range(7) if i != 4)
assert read('docs/runtime-capability-map-1375-v5.json', 'old_map_final') == raws['docs/runtime-capability-map-1375-v5.json']
recovery = {'schema': 'EU4-USER-REQUESTED-UI-RECOVERY/1', 'old_PID38076_absent_before_stop': True, 'root_StopProcess_executed': False, 'new_PID':98548,'creation':'01dd5d0e670312c4','UI_observed_date':'1445-05-19','UI_observed_paused':True,'Steam_warning_confirmed':True,'initial_launch_window_timeout_followed_by_existing_window':True,'achievement_confirmation_clicked':True,'normal_UI_loads_for_recovery':1,'controller_reload_count_is_separate':True,'current_readonly_status':'unknown','refusal_raw_global_value':1,'required_value_by_frozen_source':-1,'global_field_semantics_proved':False,'installed_Mod_cause_proved':False,'temporary_dsh_pet_minimize_did_not_establish_cause':True,'new_requests':0,'new_native_calls':0,'new_DLL_install_or_Frida':False,'old_effects_or_ownership_promoted':False,'no_automatic_query_retry':True,'independent_live_review':'pending War file-only review'}
recovery_rel = (OUT/'ui-recovery.json').relative_to(ROOT).as_posix()
write_new(recovery_rel, (json.dumps(recovery, ensure_ascii=True, indent=2)+'\n').encode())
receipt = {'schema':'EU4-CONTINUATION-PUBLICATION/15','passed':True,'fixed_inputs':{r:{'bytes':n,'sha256':s} for r,(n,s) in fixed.items()},'root_review_scope':'Exact independent review subjects and old/new data/map comparisons only; full157-pin v6 and124-pin R82 reviews are fixed non-author witnesses, not recursively re-reviewed here.','outputs':outputs,'old58_exact':True,'generator_only_expected_append':True,'other_six_map_records_exact':True,'old_docs_preserved_as_suffix':True,'Oct15_tail_byteidentical':True,'publication_CLI_tests_PE_process_operations':0,'separate_new_live_query_recorded_not_repeated':True,'read_events':events,'manual_prior_inspection_allowance':1048576,'seal_reserve':1048576,'upper_bytes':sum(e['bytes'] for e in events)+2097152,'limit_bytes':LIMIT}
b=(json.dumps(receipt,ensure_ascii=True,indent=2)+'\n').encode()
with (OUT/'receipt.json').open('xb') as f:
    f.write(b)
print(json.dumps({'passed':True,'receipt':pin(b),'outputs':outputs},ensure_ascii=True))
