"""Accept fixed independent file reviews, without executing reviewed programs."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/continuation-publication-20261016-r16'
LIMIT = 8 * 1024 * 1024
events = []
raws = {}

def pin(b):
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def read(rel, phase):
    p = ROOT / rel
    assert p.resolve().is_relative_to(ROOT.resolve())
    assert p.stat().st_size <= 4 * 1024 * 1024
    b = p.read_bytes()
    events.append({'path': rel, 'phase': phase, **pin(b)})
    assert sum(x['bytes'] for x in events) + 2 * 1024 * 1024 < LIMIT
    return b

reviews = {
 'r83': ('work/reports/war-peace-api-20261016-r83-independent-review/findings.json', 6771, 'cfbef2c4826caf38af20615f5c1557639c87831737f9989d4620a47e613f4559'),
 'proposal': ('work/reports/peace-current-pending-guard-proposal-independent-review-20261016-r1/findings.json', 5769, 'b03b4b840ddd30cd01458497813d6cb82f8ff81cd52df156296900a0a3985187'),
 'live': ('work/reports/peace-current-pending-observer-live-after-restart-independent-review-20261016-r2-review2/findings.json', 8290, 'e4473e6cee3abb2a740a97ca8a9159e01c458e8bb22ae01575ac3437fd5f235d'),
 'cached_field': ('work/reports/current-mod-field-cached-source-independent-20261016-r1/findings.json', 2907, 'f93dfff90c96d0d85535cf8d309cec468668993f1b5360a23eac3acab909d1bc'),
}
accepted = {}
for name, (rel, n, h) in reviews.items():
    b = read(rel, 'review_before')
    assert pin(b) == {'bytes': n, 'sha256': h}, rel
    raws[rel] = b
    v = json.loads(b)
    assert v['sealed'] and v['passed'] and v['blocking_findings'] == []
    assert all(x is False for x in v['authority'].values())
    subjects = {}
    for key, value in v.items():
        if key.startswith('subject_') and isinstance(value, dict) and set(value) == {'path', 'bytes', 'sha256'}:
            path = value['path']
            got = read(path, 'exact_review_subject') if path not in raws else raws[path]
            assert pin(got) == {k: value[k] for k in ('bytes', 'sha256')}, (name, key)
            raws[path] = got
            subjects[key] = value
    assert subjects
    accepted[name] = {'review': {'path': rel, **pin(b)}, 'subjects': subjects}

live = json.loads(raws[reviews['live'][0]])
assert live['field_diagnosis']['raw_hex'] == '01000000'
assert live['author_resources']['RPMcalls'] == 120
assert live['author_resources']['RPMbytes'] == 10371
r83 = json.loads(raws[reviews['r83'][0]])
assert r83['source_preservation']['source8_before_after_equal']
proposal = json.loads(raws[reviews['proposal'][0]])
assert proposal['conditional_recommendation']['option'] == 'B-layout-profile-plus-raw-diagnostic'
field = json.loads(raws[reviews['cached_field'][0]])
assert field['source_count'] == 4 and field['flat_pin_count'] == 26

docs = ['HANDOFF.md', 'README(agent).md', 'docs/war-peace-api-1375.md', 'docs/runtime-observer-1375.md']
old = {r: read(r, 'document_before') for r in docs}
marker = '## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf-8')
assert marker in old['HANDOFF.md']
tail = old['HANDOFF.md'][old['HANDOFF.md'].index(marker):]
head = '''## 2026-10-16 最新继续点：重开后的unknown已完整独审；v2六新fake与增量文件查询通过，等待完整源审及生产门禁

游戏已按用户要求自主重开、确认Steam/成就提示并载入France1445-05-19暂停。旧PID38076在Stop前已不存在，root没有实际杀掉它；当前已绑定PID98548/create01dd5d0e670312c4。不要再要求用户守候点击。after-restart-r2唯一v1 status保持UNKNOWN/samples[]/presenceNULL/commitfalse：120RPM/10371B，四段735B code和host/root前后相等，在sample1第70条module+233e064读01000000/i32=1，冻结CLI280要求-1而停止，未读国家表/队列。War完整非作者review2 findings8290Be4473e6cee3abb2a740a97ca8a9159e01c458e8bb22ae01575ac3437fd5f235d/manifest12367Bae29f9b691bc476a94d3b4701411f0230442d6f6f9c1a9ed35628f71c79f257d已被root接受；55flat、34实际源pin，首轮审查误以32pin失败历史保留。host图与OS事实是固定producer witness，OS CloseHandle返回仍未检查；相等不证明atomic/ABA/lease。此值的“Mod”只是旧源错误标签，不证明installedMod、汉化、多人与native枚举，也不证明队列缺席或原动作失败。旧capture与guard原像保留。

只读工具改进选择B，经完整非作者设计审查接受为设计：proposal13232Bba2b0931280bb38087c686b8bf6e47688c49d68178c8a8183815cd604e4030e7；review5769Bb03b4b840ddd30cd01458497813d6cb82f8ff81cd52df156296900a0a3985187。AST证实旧signed值仅用于require控制谓词，不传入所选布局；4B读本身仍有预算/短读/journal影响，不能删除。新独立v2记录raw/i32/u32/meaningunknown，并把它加入两样本一致性；其余23原定义和root/暂停/国家表/句柄/queue/close/source守卫保持。局部分离不是全Mod兼容定理。

v2源码冻结在work/candidates/peace-current-pending-observer-1375-v2：CLI24249B94faa085cc982230717f42b43b24bd777a26493a0cf18d2dc3c2cbfc23a7491d /source8428B6a4c081d3709d734eee90b9c19f9da535620cd56665e4fcb02cc6270871ab2a0 /graph5df0dcb56da6629ebbe9f3585ff6f10d120d66d903354be05887dcea9dc67a82 /41pins。6个新增fake各一次全PASS：stable-1absent、stable1absent、stable1present、1->2mismatch、shortscalar、其他结构守卫拒绝；旧31与历史120均未重跑。首check因IO meter在read前为完整16777217B请求预留而拒绝，catalog当时0；失败receipt6232B418e8578f06a4dc72c2b1651aaebddfb8008f785aa8cd7864d29aa2f499acf47保持。root新的192MiB ordinary/3GiB固定host累计budget delta后，新namespace execution-r1 check及首次catalog各一次PASS，冻结manifest9187B3c03b1c8b17f9135e0008c46035dedb67ae169baab2a3539dc0cdc0e15de6c73/receipt37301B027cf7d867c4f2c436d3b9355a1cb139c15dc7cf2572442ac2ad9c88ff39de2d。普通累计保守upper134955989<201326592；固定215+11 host hash累计2814109562B=11pass、7535attempt<24576，只原1MiB流式hash例外，其他R23/direct小文件及16MiB+1请求不绕过。构建源预算32MiB仍不扩；没有隐藏首失败或复跑6fake。Val正在完成source/fakes/delta全审；canonical仍draft/runtimefalse，尚未source-ready/production/live，不自行status。D只预检下一次live所需controller/IO；完整正常status host主hash路线初步为9pass，不能沿用check/catalog的4pass。所有已完成Job active0，shell收齐。

R83已完整非作者接受：cachedmanifest4851Be7780dd93f81c523ba9b1b5d001cb7e6388c0cf5e1a2200b29e16a6d29aa93fa /contract9627B64f4f0b29eac243ea2c935fc6ae5d3fba7aaa7797f84f70470939b895bac3a58 /review6771Bcfbef2c4826caf38af20615f5c1557639c87831737f9989d4620a47e613f4559。旧selector30rows108B、97bea0用点13rows49B、relation AST21lines；只有native P==同一typed C且J==已验证正other.slot<32768等条件才得到C+1510/72B row结构桥。O+10/+18 writers、P/O/returnWAR类型、全局WAR/对手边与存活/并发仍未知；返回0可能empty/miss/matchedNULL。作者8源/2pass2845750B，联合upper3828790<4MiB；Val37flat full/50pins，自己的文件名/路径预检失败保留。无新PE/decoder/native/game，未采纳新reader或升级效果。

233e064旧缓存四源搜索也已完整非作者接受：author manifest4715B9004f4db1e24f286c2c7f65856c13f60091529ca5b77a9bcbd2705045e5d620c/findings5964B6d0fcca5f4c45a995b450ee3a73226d1627e53cc8ffb70e365c334b241a371b3；root review2907Bf93dfff90c96d0d85535cf8d309cec468668993f1b5360a23eac3acab909d1bc/manifest18045Bcc469e83214c336665989287a62a2f5ecafd8808c7f80e6d74e91cc343c635e8。4源原文finite匹配explicit RVA/preferredVA/decimal全0，base仅由static.image_base140000000证明；这不覆盖RIP、alias、indirect或整PE，也未证明native字段语义或批准B。旧launcher引号错误未启动extractor，首次实际extractor仅一次通过，原失败/单次窄launcher续行保留；root26flat/两遍source与独立regex复算，upper4312115<8MiB。禁止运行旧trace/native55或扩PE全局搜索。

本发布只核固定非作者findings与精确subjects，不声称重做其所有flat/host/PE审查；状态写在冻结图外。v6离线lookup60records/94JSON已接受，mapv6保持；48effects/44historical persistence/42repair/stable15profiles98pins保持，新增requests/native/effects0。用户已撤销误发打包，继续完成验证与宣战/议和执行器，不在里程碑自行停止。自动审批拒绝tmpi03vucy0清理（blocked by policy），保留且不换工具再试。下方旧pending/menu/no-query说明为历史，由本段限定更新；Oct15尾部字节保持。

'''
short = '''2026-10-16 更新：游戏已自主重开、处理成就提示并载入暂停。重开后只读unknown已完整独审，阻塞来自233e064旧值限制，字段语义仍未知。独立v2保留raw与两次一致性；6个新fake、增量check及首次catalog通过，原预算失败保留，完整源审/生产门禁仍进行中，尚未实机运行v2。R83缓存结构桥与四源字段搜索已完整独审，均不升级类型、原请求或效果证明。48/44/42及禁重发保持；下方旧状态为历史，详情见HANDOFF顶部。

'''
statuses = {
 'work/reports/war-peace-api-20261016-r83-cached-source-plan/REVIEW_STATUS.md': 'R83 cached conditional structure accepted after complete non-author review. Exact P=C, validated positive J and stable valid-memory premises are required. O writers, native classes, returned WAR/global/opponent identity, lifetime and effects remain unknown. No reader adoption, native execution or repeat authority. Review: ../war-peace-api-20261016-r83-independent-review/findings.json\n',
 'work/reports/peace-current-pending-guard-proposal-20261016-r1/REVIEW_STATUS.md': 'Option B is independently accepted as source design only: retain four-byte raw diagnostic and two-pass coherence with all structural/identity guards. This proves no enum or general Mod compatibility and authorizes no runtime. Review: ../peace-current-pending-guard-proposal-independent-review-20261016-r1/findings.json\n',
 'work/reports/peace-current-pending-observer-live-after-restart-20261016-r2/REVIEW_STATUS.md': 'Complete non-author review accepted this UNKNOWN capture. Raw scalar1 caused frozen signed-value guard refusal before selected country/queue samples. Current queue presence, original request, acceptance, effect and completion are unproved. No query repeated by this publication. Review: ../peace-current-pending-observer-live-after-restart-independent-review-20261016-r2-review2/findings.json\n',
 'work/reports/current-mod-field-cached-source-20261016-r1/REVIEW_STATUS.md': 'Complete non-author retained-file review passed26 flat pins and independently repeated the finite explicit-address text search. Zero matches in four selected cached sources does not prove native absence, field semantics or Mod compatibility. Original launcher failure is preserved. No PE/decoder/old trace/runtime operation. Review: ../current-mod-field-cached-source-independent-20261016-r1/findings.json\n',
}
for rel in statuses:
    assert not (ROOT / rel).exists(), rel
assert not OUT.exists()
for rel, b in raws.items():
    assert read(rel, 'fixed_after') == b
for rel, b in old.items():
    assert read(rel, 'document_prewrite') == b
OUT.mkdir()
outputs = {}
for rel, value in statuses.items():
    b = value.encode('utf-8')
    with (ROOT / rel).open('xb') as f:
        f.write(b)
    outputs[rel] = pin(b)
for rel, before in old.items():
    b = (head if rel == 'HANDOFF.md' else short).encode('utf-8') + before
    (ROOT / rel).write_bytes(b)
    got = read(rel, 'document_after')
    assert got == b and got.endswith(before)
    if rel == 'HANDOFF.md':
        assert got[got.index(marker):] == tail
    outputs[rel] = pin(got)
receipt = {'schema': 'EU4-CONTINUATION-PUBLICATION/16', 'sealed': True, 'passed': True,
 'accepted_fixed_reviews': accepted, 'outputs': outputs, 'read_events': events,
 'root_scope': 'Exact fixed non-author subjects; no full recursive recertification or program execution.',
 'old_documents_preserved_as_suffix': True, 'Oct15_tail_byteidentical': True,
 'map_v6_or_candidate_manifest_mutations': 0, 'v2_production_or_live_authority': False,
 'programs_tests_game_PE_native_operations': 0,
 'upper_bytes': sum(x['bytes'] for x in events) + 2097152, 'limit_bytes': LIMIT}
b = (json.dumps(receipt, ensure_ascii=True, indent=2) + '\n').encode()
with (OUT / 'receipt.json').open('xb') as f:
    f.write(b)
print(json.dumps({'passed': True, 'receipt': pin(b), 'outputs': outputs}, ensure_ascii=True))
