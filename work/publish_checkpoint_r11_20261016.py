"""Publish accepted R78 sample and latest source-only R80 continuation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/continuation-publication-20261016-r11'
PINS = {}; COUNT = 0


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(rel, expected=None):
    global COUNT
    p = ROOT / rel; a = p.stat(); assert a.st_size <= 4 * 1024 * 1024
    raw = p.read_bytes(); b = p.stat(); COUNT += len(raw)
    assert (len(raw), a.st_size, a.st_mtime_ns) == (b.st_size, b.st_size, b.st_mtime_ns)
    assert COUNT <= 4 * 1024 * 1024
    value = pin(raw); assert expected is None or expected == value, rel
    assert rel not in PINS or PINS[rel] == value
    PINS[rel] = value; return raw


def create(path, raw):
    with path.open('xb') as f:
        f.write(raw)
    return pin(raw)


assert not OUT.exists()
review = 'work/reports/server-expected-owner-sample-data-actual-independent-review-20261016-r78/'
f = json.loads(read(review + 'findings.json', dict(bytes=5499, sha256='af6dbcd868c394095c4c15d412cf9cee2f7dfb10f77bada085d860e92905b8ac')))
m = json.loads(read(review + 'manifest.json', dict(bytes=12195, sha256='8ef7a86e86e50a796b14ff23abdfbada2a279f063870220f934d8a1a2a0c2d57')))
assert f['sealed'] and f['passed'] and f['blocking_findings'] == [] and m['sealed']
base = 'work/reports/server-expected-owner-sample-data-20261016-r78/'
for name, key in (('data-final-manifest.json','subject_data_final_manifest'), ('capture.json','subject_capture_pin'),
                  ('data-contract.json','subject_contract_pin'), ('data-owned.json','subject_owned_pin')):
    read(base + name, f[key])
docs = {r: read(r) for r in ('HANDOFF.md','README(agent).md','docs/war-peace-api-1375.md','docs/runtime-observer-1375.md')}
before = dict(PINS)
for rel, expected in before.items():
    read(rel, expected)
OUT.mkdir()
for rel, raw in docs.items():
    create(OUT / (rel.replace('/','__') + '.before'), raw)
status_rel = base + 'DATA_REVIEW_STATUS.md'
status = '''# R78 six-byte sample independently accepted

[Complete non-author review](../server-expected-owner-sample-data-actual-independent-review-20261016-r78/findings.json) passed59 pins. The sole targeted DATA sample [1caa8f0,1caa8f6), file30055152, is `646573657274` (`desert` in ASCII/UTF8). No NUL occurs within the six owned bytes. No targeted byte7 or terminator search was performed; whole-PE SHA passes naturally cover the file outside the sample too.

Six is the selected sample budget, not a proved consumption length. LEA computes an address; R8D6 and the unfollowed95110 call do not prove string semantics, class, mode, receiver identity or host compatibility. Host guards remain unchanged.

Source attempts89/3,481,090B, retained successful bill3,817,233B and combined7,298,323B were independently replayed; PE76,925,014B is separate. Retained4MiB is a successful post-read bill, not a failure-path pre-read hard stop. Exact source/review/auth gates, normal close before final guards/capture and exclusive one attempt passed. No actual, author program, decoder, game, tests or native action was repeated by review. No further scope or execution permission follows.
'''.encode('utf8')
sp = create(ROOT / status_rel, status)
head = '''## 2026-10-16 最新继续点：R78完整独审PASS；R79 unknown包已封待Val full；R80新固定64B仅source准备

R78 full PASS：server-expected-owner-sample-data-actual-independent-review-20261016-r78/findings5499Baf6dbcd868c394095c4c15d412cf9cee2f7dfb10f77bada085d860e92905b8ac /manifest12195B8ef7a86e86e50a796b14ff23abdfbada2a279f063870220f934d8a1a2a0c2d57，59pins/55flat。唯一targeted6B646573657274=desert，ownedNULNone；不认完整Cstring/消费长度/class/mode/receiver/host。89source attempts3481090/retained成功3817233/combined7298323/PE76925014分账已重放；targetedbyte7未读不等于wholeSHA全局不读。retained4M为成功post-read账单，不是失败突变路径前置硬停。War为sourcepeer及旧R75/R69角色、非D actualauthor，三gate/rootgrant/normalclose前后/sourceauth一致；不重actual。DATA_REVIEW_STATUS冻结图外，宿主守卫不变。

R79 final canonical已冻：war-peace-api-20261016-r79-null-selector-callee/actual-manifest15510B7ca8e3bc5f0280b5a908ad624e03be91d2be85f2465f7da5ef98fee95b264523 /contract3281B52d792d5… /selected10307Bca882c2f… /capture69473B97f3cf26d8bac7ad0fa7674da900c8284906e19c9a07033c6a2cba4e47605506，41flat首checkPASS。20pdata physical240/17unique204，选19063 raw90bc970021bd9700e4c0e701 [97bc90,97bd21)，next19064 rawa0bd97003cbe97001898dc01 [97bda0,97be3c)，CALL97bd30在gap127B内offset15/to-next112。explicit owned_code_pin:null/analysis:null/decoder_loaded:false，0code不是凭缺文件推断；unknown不证函数不存在/纯返回/D0/header。Val正在完整非作者full审；4个顶层subject将是subject_actual_manifest/subject_capture_pin/subject_contract_pin/subject_selected_pin，各为{path,bytes,sha256}而非仅pin。读账source16954369/PE76925248/retainedupper6554077<16M/combined23508446<48M另账；1次actual和所有shell已收齐禁止重试。

Root已另准D准备R80 source/budget-only：war-peace-api-20261016-r80-unregistered-call-prefix/，新问题唯一固定64B[97bd30,97bd70) CALL-known未登记入口前缀/newpdata0。gap前15B/后48B不读；不叫R79fallback/wholefunction，R79unknown原样。用已冻R69 CALL/R79两12B缓存fence/R27唯一.text映射，cachedfence或mapping失败unknown0code；CFG只ownedwindow，不跟callee/RIPdata/vslot/header/unwind/邻code，不追加suffix。两SHA/单claim/新raw-source-R79full三gates+新rootoncegrant/normalclosefinalguards/source32+seal16/768M1Gstop。R79 full尚未封，D已写草稿但等待真实4subjectshape锁定后首次prepare/check/freeze，当前无R80auth/claim/actual。Root随后做新raw，sourcepeer另派；不读mutable草稿/旧tests/引擎body/PE。

v5/rootr9接受结论与mapv5保持：59entries/74JSON/264refs/144flat，old58/59不变；其他6工具record相同。1次peace status仍unknown/samples0；不改hostguard/不新游戏query/UI/save/reload/request。48/44/42/稳定15profiles与禁重发保持；全部120/宣战议和executor未完成，继续工作，误发打包撤回。下方历史pending按本段覆盖；Oct15尾部保持。

'''
changed = {'HANDOFF.md': head.encode('utf8') + docs['HANDOFF.md']}
readme = docs['README(agent).md'].decode('utf8')
old = 'R78六字节样本与R79未知callee仅源码冻结待新审/授权。'
assert readme.count(old) == 1
changed['README(agent).md'] = readme.replace(old,'[R78六字节样本](work/reports/server-expected-owner-sample-data-20261016-r78/DATA_REVIEW_STATUS.md)已完整独审；R79严格入口为unknown0code待full，R80新64B仅源码准备。').encode('utf8')
war = docs['docs/war-peace-api-1375.md'].decode('utf8')
old = 'R78固定6B样本与R79入口97bd30仅源码准备待新独审/授权。'
assert war.count(old) == 1
changed['docs/war-peace-api-1375.md'] = war.replace(old,'[R78固定6B样本](../work/reports/server-expected-owner-sample-data-20261016-r78/DATA_REVIEW_STATUS.md)desert已完整独审，不能认类型/模式；R79 exact入口查找unknown0code待full，R80新64B仅源码准备。').encode('utf8')
guide = docs['docs/runtime-observer-1375.md'].decode('utf8')
pos = guide.index('\n\n') + 2
new_paragraph = '''[R78固定六字节样本](../work/reports/server-expected-owner-sample-data-20261016-r78/DATA_REVIEW_STATUS.md)已完整独审：targeted内容为desert，样本内无NUL。它不证明完整字符串、消费长度、类或模式，不改变宿主守卫或读取器实机验收状态。\n\n'''
changed['docs/runtime-observer-1375.md'] = (guide[:pos] + new_paragraph + guide[pos:]).encode('utf8')
marker = '## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf8')
assert changed['HANDOFF.md'][changed['HANDOFF.md'].index(marker):] == docs['HANDOFF.md'][docs['HANDOFF.md'].index(marker):]
changed_pins = {}
for rel, raw in changed.items():
    assert read(rel, before[rel]) == docs[rel]
    (ROOT / rel).write_bytes(raw); changed_pins[rel] = pin(raw)
read(status_rel, sp)
receipt = dict(sealed=True, passed=True, input_pins=before, changed_docs=changed_pins,
    created_outside_frozen_author_graph={status_rel: sp}, historical_Oct15_tail_unchanged=True,
    source_read_bytes=COUNT, manual_inspection_allowance=131072, source_limit=4 * 1024 * 1024,
    PE_engine_decoder_game_tests_native=0, new_effects=0, new_requests=0, packaged=False)
assert COUNT + 131072 <= 4 * 1024 * 1024
raw = (json.dumps(receipt, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
print(json.dumps(dict(receipt=create(OUT / 'receipt.json',raw), selected_read_bytes=COUNT),ensure_ascii=True))
