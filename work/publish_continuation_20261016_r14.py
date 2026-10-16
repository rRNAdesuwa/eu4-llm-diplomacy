from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/continuation-publication-20261016-r14'
LIMIT = 8 * 1024 * 1024
events = []

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
 'work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/findings.json': (9252, '81bb504dd809001a9a1549f094e9b9889013808607d16be7e176748ae61d7e18'),
 'work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/manifest.json': (15918, '91ed106282413b91fbc5d34a2cd096c7f41f1569a2df4ab0bf33ffa0c571a9c4'),
 'work/reports/war-peace-api-20261016-r81-actual-independent-review/findings.json': (10070, '88b77deb6932d216717adcff1edebd5eecfce6ddf1bc0137c0c1fcbec5302847'),
 'work/reports/war-peace-api-20261016-r81-actual-independent-review/manifest.json': (14590, '10d2348d4c5d1292576f5e05f04e55e5816d32bfb6b7d281ad4d2a847a68a703'),
 'work/reports/war-peace-api-lookup-v6-root-authorization-20261016-r2/authorization.json': (6779, '6ff710b74288f303a01df3049aab67901d49f7f1f2fbcfe0a0423251ce237de5'),
 'work/reports/war-peace-api-lookup-v6-root-authorization-20261016-r2/receipt.json': (6648, 'e2eb2bdad426c40d08d2ba958e7ab24d4f0819ea829bd6c85e1262586949f7fc'),
}
for rel, expected in fixed.items():
    b = read(rel, 'fixed_before')
    assert (len(b), pin(b)['sha256']) == expected
    if rel.endswith('findings.json'):
        o = json.loads(b)
        assert o['sealed'] and o['passed'] and o['blocking_findings'] == []

docs = ['HANDOFF.md', 'README(agent).md', 'docs/war-peace-api-1375.md']
old = {rel: read(rel, 'document_before') for rel in docs}
marker = '## 2026-10-15 新进程门禁与继承人核心字段'.encode('utf-8')
assert marker in old['HANDOFF.md']
tail = old['HANDOFF.md'][old['HANDOFF.md'].index(marker):]

handoff = '''## 2026-10-16 最新继续点：R80/R81 完整独审已通过；v6 R2 已准构建；用户确认主菜单或载入中

本段覆盖下方旧的 R80 full-pending、R81 source-only 和 v6 waiting-tail 状态；旧文与 Oct15 尾部原样保留。用户撤回打包并要求继续；最新回答当前 EU4 为“主菜单或载入中”。这是用户状态信息，不是运行时类型、valid-world 或原请求效果证明。唯一 peace status 仍 UNKNOWN/samples0/commitfalse，原 host guard 不改，无第二 game query、PID polling、UI、Frida、保存、重载或新请求。

R80 固定[97bd30,97bd70)64B actual 已由 War 完整非作者审查通过：findings9252B81bb504dd809001a9a1549f094e9b9889013808607d16be7e176748ae61d7e18 / manifest15918B91ed106282413b91fbc5d34a2cd096c7f41f1569a2df4ab0bf33ffa0c571a9c4，74pins。13rows/62B、partial97bd6e48c1、8QWORDloads、0CALL/branch/RET/explicitstore；RAX partial load 不是返回值。原 actual 不重跑，历史 partial 记录不改。新 REVIEW_STATUS.md 在冻结 source graph 外。

R81 仅 new physical[97bd70,97bda0)48B + R80 cached[97bd6e,97bd70)2B，合50B。actual-manifest16550Beb8f4a1171c388c1805093a0c41143e1f5f2bc54c08602b235d6ad15850c78c3 / contract6046Be2196dd433efbe68d57a1c37ed4b74242a4bfb5f0d00a910e732390ca29fc558 / capture79710B9ed8dcd8f053ed9749d9786443ea90b806538f8c062eb5ccdec072671635b5f8 / owned1260B38a6c1dd3c614d1cddbb9fec77faf0ca7e07e4fa3bfd1e34d110883872119687 / selected17878B480b65763ec022ea2bbde70dcca9435ac713e67e4816852c3fc51be8a134dc3c。War full 首轮PASS68pins：findings10070B88b77deb6932d216717adcff1edebd5eecfce6ddf1bc0137c0c1fcbec5302847 / manifest14590B10d2348d4c5d1292576f5e05f04e55e5816d32bfb6b7d281ad4d2a847a68a703。17rows46decodedB，尾4CC owned但RET后不解码；3rel8分支含backedge，两RET97bd96/97bd9b，0CALL/explicitstore。先 SHR64/CWDE32 得32bit key，查 current R8+50/5c 的16B记录，首DWORD匹配返回record+8；end/no-match返回0，匹配value也可0。count负值、容量、有效地址、终止、唯一键、完整handle、对象类型/寿命/units/recipient/effect仍未知；每条RET正常读8B控制栈并RSP+8。仅局部条件CFG闭合，不证明函数整体extent或安全可调用。两SHA仍覆盖全PE，不混淆targeted48/cache2/combined50。所有 actual shell 收齐、无retry。

v6 R2 proposal6338B5c01dca5b49738fa099484e8bd93886f89d0bcb5d1d1fc24bf5acb6f2d02ff81 / manifest6526B271c8daf02b8a30a7c9fd913dac3407a686cccded75f0db5644f9ddbb6596155，经 Val 条件审查PASS：findings4707Bdbd27562f95e85c951a8ab487fb3a0bcfb4bd0c6525ea7ef630a8c4a9b6cf6ab / manifest10026B5cc68caf6281bb58224e1d0794b574986703c0c1fa1db17cf7c2c0e289e48cae。Root 新授权 war-peace-api-lookup-v6-root-authorization-20261016-r2/authorization6779B6ff710b74288f303a01df3049aab67901d49f7f1f2fbcfe0a0423251ce237de5 / receipt6648Be2eb2bdad426c40d08d2ba958e7ab24d4f0819ea829bd6c85e1262586949f7fc，owner War。仅60entries/94directJSON：old74+R75/R77十+R80/R81十；old58逐字段相同，generator只append R75/R77 later_checked_context/evidence及historical_base_scope，新97bd30为机器合同。复用 v5 原路径ea030 engine16583B/96cap，wrapper仅hash/revision/help必要BASE metadata，逻辑AST不变。build+seal32MiB，first4 batch64MiB，check/catalog/lookup993570/lookup97bd30各一次；任何失败保留不得重跑。不得引入R82、旧tests/fixtures、新guardtests、PE/decoder/game/native、ZIP或公开map。冻结后仍需 root 完整非作者审查，当前 accepted lookup/map 仍v5。R81五roles exact JSON已由War冻结于 lookup-source-roles1522Bab5a636933ed3e0e5a55591dcc588456fb1159b6c118c7f1e91c719d8f5a47ca。

D 正做 R82 cached-use/layout crosswalk（源与分析总8MiB）：仅v5原74固定JSON、R80/R81合同/selected/指定witness、R27 anchors和精确R7 observer布局文件，不开PE/decoder或旧程序。不提前接收其未封结果，完成后交 Val 非作者审查。特别注意R69 postCALL +70/+78来自R13（原输入W的条件保存值），不是R12返回值；返回对象与 typed global WAR 的identity edge尚缺，不凭offset相似命名CWar。

48effects/44历史persistence/42候选，stable15profiles/98pins和所有禁止重发保持。本轮新增effects/nativecalls/requests为0，全部120和宣战/议和执行器未完成。继续工作，不在索引/审查里程碑自行结束。自动审批拒绝清理tmpi03vucy0（blocked by policy），保留，不换工具重试。

'''

def short(prefix):
    return f'''2026-10-16 最新继续点：[R80 固定前缀]({prefix}work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/REVIEW_STATUS.md)与[R81 尾段]({prefix}work/reports/war-peace-api-20261016-r81-selector-prefix-tail/REVIEW_STATUS.md)均已通过完整非作者审查。已确认条件查找与两条返回路径；返回对象类型、有效范围、终止、单位、收款方和外交效果仍未知。v6 的60项/94来源索引正在构建，完整审查前 accepted 仍为v5。用户确认游戏当前在主菜单或载入中；唯一运行时查询仍为unknown，进入对局前不重复查询或改变守卫。下方旧source-only/pending状态为历史记录。

'''

new = {'HANDOFF.md': handoff.encode('utf-8') + old['HANDOFF.md'], 'README(agent).md': short('').encode('utf-8') + old['README(agent).md'], 'docs/war-peace-api-1375.md': short('../').encode('utf-8') + old['docs/war-peace-api-1375.md']}

statuses = {
 'work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/REVIEW_STATUS.md': '''# R80 fixed64B prefix independently accepted

[Complete non-author review](../war-peace-api-20261016-r80-actual-independent-review-r3/findings.json) passed74 pins. The fixed64B CALL-known prefix has13 complete rows/62B and partial48c1 at97bd6e. Eight QWORD loads are supported; LEA is not another read. No decoded CALL, branch, RET or explicit memory store appears in this selected prefix.

The retained RAX is a current load, not a proved return value. The selected index arithmetic distinguishes sign-extension to64 from sign-extension to32 followed by zero upper32. Full function extent, object types, bounds, aliases, D/header final contents, units, recipient, lifetime and gameplay effects remain unknown.

Two complete EXE SHA passes plus64 targeted bytes total76,925,072B. New metadata is0. Decoder lookahead185B covers64 unique owned bytes, overlapping121B. Source17,127,251B and retained upper3,040,742B were reviewed separately. Software memory guards are not a hard Job claim. Reviewer repairs were confined to its own report logic and preserved; no author/native run was repeated.

The later separately authorized R81 continuation supplies conditional return context. This historical prefix/partial evidence stays unchanged. Acceptance grants no native invocation or broader byte scope.
''',
 'work/reports/war-peace-api-20261016-r81-selector-prefix-tail/REVIEW_STATUS.md': '''# R81 cached2B plus new48B independently accepted

[Complete non-author review](../war-peace-api-20261016-r81-actual-independent-review/findings.json) passed68 pins on its first pass. Only48 new targeted bytes [97bd70,97bda0) were acquired; cached R80 bytes48c1 at97bd6e supply2B for the50B decode input. Two whole-file SHA passes still cover the entire executable. No new pdata or targeted reread of the prior64B occurred.

Seventeen rows consume46 combined bytes. Three local branches include a backedge; alternative RETs are97bd96/97bd9b, with four owned CC bytes left undecoded after RET. There are no CALLs or explicit memory stores. Each normal RET reads8B control stack and advances RSP8.

Under inherited R80 state and valid stable memory, the suffix derives a32bit key, reads a base/count at currentR8+50/+5c, and searches16B records by the first DWORD. It returns the first matching record+8 value, or0 at the end. A matching value may itself be0. Negative counts, capacity, useful termination, full handles, uniqueness, type, ownership/lifetime, aliases and original D/header contents are not proved.

The producer used17,331,379B source reads; retained successful upper3,186,678B and full PE SHA+new48 total76,925,056B remain separate. Overlapping decoder inputs230B represent50 unique owned bytes. Normal target close precedes final guards/capture. All actual shells were collected with one attempt and zero retries. Local conditional CFG closure does not establish whole function extent, a typed war object, native-call safety, amount units, recipient or diplomacy completion.

The reviewer discloses its R80 review/R79 author/v5 author roles. Five lookup JSON roles are frozen in lookup-source-roles.json outside this author graph. v6 lookup needs its own frozen build and non-author acceptance; no runtime or new native authority follows here.
''',
}

for rel in statuses:
    assert not (ROOT / rel).exists(), rel
for rel in fixed:
    b = read(rel, 'fixed_after')
    assert (len(b), pin(b)['sha256']) == fixed[rel]
for rel in docs:
    assert read(rel, 'document_prewrite') == old[rel]

OUT.mkdir(exist_ok=False)
outputs = {}
for rel, text in statuses.items():
    b = text.encode('utf-8')
    with (ROOT / rel).open('xb') as f:
        f.write(b)
    outputs[rel] = pin(b)
for rel, b in new.items():
    (ROOT / rel).write_bytes(b)
    got = read(rel, 'document_after')
    assert got == b
    assert got.endswith(old[rel])
    if rel == 'HANDOFF.md':
        assert got[got.index(marker):] == tail
    outputs[rel] = pin(got)

note = {'schema': 'EU4-USER-REPORTED-MODE-CONTEXT/1', 'source': 'direct user async answer', 'questionItemId': '["request_user_input_async","call_6501926ed4e14aeb9e2147bf91ab4634",0]', 'answer': '主菜单或载入中', 'meaning': 'user reported current menu/loading; not runtime type proof or valid-world sample', 'prior_capture_rewritten': False, 'second_game_query_executed': False, 'guard_override': False, 'effects_added': 0}
note_b = (json.dumps(note, ensure_ascii=True, indent=2) + '\n').encode()
(OUT / 'user-mode-context.json').write_bytes(note_b)
outputs[str((OUT / 'user-mode-context.json').relative_to(ROOT)).replace('\\', '/')] = pin(note_b)
receipt = {'schema': 'EU4-CONTINUATION-PUBLICATION/14', 'passed': True, 'fixed_inputs': {p:{'bytes':n,'sha256':s} for p,(n,s) in fixed.items()}, 'outputs': outputs, 'old_documents_preserved_as_suffix': True, 'Oct15_handoff_tail_byteidentical': True, 'new_actual_or_queries_or_tests': 0, 'accepted_lookup_capability_map': 'v5 unchanged', 'read_events': events, 'manual_prior_schema_allowance_bytes': 1048576, 'seal_reserve_bytes': 1048576, 'upper_bytes': sum(e['bytes'] for e in events)+2097152, 'limit_bytes': LIMIT}
b = (json.dumps(receipt, ensure_ascii=True, indent=2) + '\n').encode()
with (OUT/'receipt.json').open('xb') as f:
    f.write(b)
print(json.dumps({'passed':True,'receipt':pin(b),'outputs':outputs}, ensure_ascii=True))
