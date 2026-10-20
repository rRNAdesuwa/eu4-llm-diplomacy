"""Publish accepted R72 disk-only findings, preserving historical doc bytes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/reports/continuation-publication-20261016-r6"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected=None):
    global COUNT
    path = ROOT / rel
    assert path.stat().st_size <= 4 * 1024 * 1024
    raw = path.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    actual = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert expected is None or actual == expected, rel
    assert rel not in PINS or PINS[rel] == actual
    PINS[rel] = actual
    return raw


def create(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
review = "work/reports/server-vtable-current-reference-owner-actual-independent-review-20261016-r2/"
f = json.loads(read(review + "findings.json", pair(5882, "d368133f4b8a96a6e93ad23ba53961180986654950021a99e372abfdabb7f492")))
m = json.loads(read(review + "manifest.json", pair(20508, "3929aa5ea3936212bfd530b5609fe301a7201ec03b57c2715a866893eade24ce")))
assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
assert f["subject_manifest"] == pair(15979, "889424b7f74e7fb825a2947f48f7b2a6f61d4955d4d0a668c356046108f2d201")
assert f["subject_capture"] == pair(456041, "86cab6aa6f70acc0ffeae2ce712b2b7d7259012119cca487af069f43625a7c26")
assert f["subject_contract"] == pair(5949, "8a477105e79df45d96f1d2aeae8fb795ef6efdb82f6f06f8356b5ed85a3bc456")
docs = {name: read(name) for name in ("HANDOFF.md", "README(agent).md", "docs/war-peace-api-1375.md")}
before = dict(PINS)
for rel, value in before.items():
    read(rel, value)
OUT.mkdir()
for name, raw in docs.items():
    create(OUT / (name.replace("/", "__") + ".before"), raw)
status = """# R72 R2 bounded static reference accepted

2026-10-16：[完整非作者独审](../server-vtable-current-reference-owner-actual-independent-review-20261016-r2/findings.json)通过。唯一[10d23c0,10d2bfd)2109B、418条指令，66 pins、56 flat files；38个engine文件只采用身份元数据见证。

从selected.begin的条件CFG可达10d24e3：LEA RAX,1d5a8c8，随后10d24ea MOV[RDI],RAX。RDI对应entryRCX需要此前外部CALL遵守正常非易失寄存器及栈约定。RET与INT3均在有限CFG内，整体正常路径未闭合。184处raw显式内存写包含16处缺少Capstone write flag的MOVUPS，不能把仅统计flag当作完整写集合。

这些证据不证明构造函数、类名、游戏模式、完整布局、宿主兼容或原请求效果。现有runtime host guard保持；未新增status、游戏调用或外交请求。R1 source继续blocked，R2的raw-buffer pin先验与前后检查不排除外部ABA。本文件位于冻结作者图外。
""".encode("utf8")
status_rel = "work/reports/server-vtable-current-reference-owner-20261016-r2/ACTUAL_REVIEW_STATUS.md"
status_pin = create(ROOT / status_rel, status)
handoff = docs["HANDOFF.md"].decode("utf8")
line_end = handoff.index("\n")
head = """## 2026-10-16 最新继续点：R72 R2完整独审通过，继续R73/R74

最新调度：R72 R2 full实际独审PASS，server-vtable-current-reference-owner-actual-independent-review-20261016-r2/findings5882Bd368133f4b8a96a6e93ad23ba53961180986654950021a99e372abfdabb7f492 /manifest20508B3929aa5ea3936212bfd530b5609fe301a7201ec03b57c2715a866893eade24ce，66pins/56flat/38engine metadataonly。2109B418rows/184rawstores/16MOVUPS漏flag/20pdata17unique全部文件重放，无新PE或采集。selected.begin条件CFG可达LEA1d5a8c8→[RDI]，RDIentryRCX有normalABI前提；RET+INT3不normalclosed，class/mode/layout/hostguard/adoption/effect恒false。R1仍blocked。新ACTUAL_REVIEW_STATUS位于冻结图外。下方r5的“R72待final/peer”已由本段覆盖。

War现在仅审D的R73 source：固定[993643,993658)21B/newpdata0。source24203B7d06b37f…/producer23386Bd23bc486…/seed21609B34014d40…/final14947Bc967a839…；rootraw已PASS2515B7fb5775b39a1c715f2d44a4475fda1d52b23fcacac2f4e117615f9b02b0b03f4 /2649B2dafb89a56acab3bf03c2be22f9b3385f2e7d6ee9f40cb2972a11020117545e4。scope raw_inherited_branch_fragment_seed_only/JLE9935b2 raw0f8e8b000000/cached433699005836990024dde701。正确保存是MOV[F+78],R15，F+78=S69+20只是地址等价，不能解释成额外memoryread；entry/D/别名条件保留。当前无R73auth/actual。

Val现在仅准备R74纯DATA：server-current-label-data-20261016-r1，唯一[1d5a190,1d5a1a6)22B，不加NUL/邻域、不读metadata/decoder。R72已冻指令16+4+2复制/SIL0/scan只提供C-string-shaped线索，内容尚未读，不证类名/模式。proposal server-vtable-owner-comparison-proposal-20261016-r1/manifest3568B6a76acb4…/proposal5488B27dc26dc…/rawseed27201Bfe553073…已冻；R27cache未来唯一filebacked非.text映射否则unknown0DATA，双EXESHA另账。D等R74exactfinal做sourcepeer，root待新rawseed/fullR72gate，R74无actualgrant。

Root另做纯文件guard-order intake：runtime-manifest-order-intake-20261016-r1/index4793B8ea620fe4cbbec454e21a80c5fa6c8c7835b5f0e57e02f6e70fb456a6823e36f，仅v4 map+7entry+7manifest/335150B前后pin。不是完整closure审查或新阻断，不改任何运行工具，不重测试/进程；当前主线仍R73/R74。以下r5其余记录继续适用。\n"""
changed_raw = {"HANDOFF.md": (head + handoff[line_end:]).encode("utf8")}
readme = docs["README(agent).md"].decode("utf8")
rest = readme[readme.index("\n\n"):]
changed_raw["README(agent).md"] = ("2026-10-16 最新：[API lookup v4](work/candidates/war-peace-api-lookup-1375-v4/REVIEW_STATUS.md)58端点/59JSON已验收；[R71](work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/REVIEW_STATUS.md)、[余额字段对照](work/reports/peace-balance-field-crosswalk-20261016-r2/REVIEW_STATUS.md)及[R72静态引用](work/reports/server-vtable-current-reference-owner-20261016-r2/ACTUAL_REVIEW_STATUS.md)均已完整独审。宿主类型与和平队列兼容仍unknown；R73仅21B后继源码审查，R74仅22B数据读取器准备。48/44/42、稳定15profiles及禁重发不变，全部120未完成，未打包。先读HANDOFF顶部；下文是历史时点。" + rest).encode("utf8")
war = docs["docs/war-peace-api-1375.md"].decode("utf8")
old = "R72 R2的单次静态采集已返回，正在封存并待完整独审，不能据此修改宿主守卫。"
assert war.count(old) == 1
war = war.replace(old, "[R72静态引用](../work/reports/server-vtable-current-reference-owner-20261016-r2/ACTUAL_REVIEW_STATUS.md)已完整独审：1d5a8c8地址被写入[RDI]，对象身份和宿主兼容仍未知。R74仅准备固定22B身份线索的数据读取，宿主守卫保持。")
changed_raw["docs/war-peace-api-1375.md"] = war.encode("utf8")
marker = b"## 2026-10-15 "
assert changed_raw["HANDOFF.md"][changed_raw["HANDOFF.md"].index(marker):] == docs["HANDOFF.md"][docs["HANDOFF.md"].index(marker):]
changed = {}
for rel, raw in changed_raw.items():
    assert read(rel, before[rel]) == docs[rel]
    (ROOT / rel).write_bytes(raw)
    changed[rel] = pair(len(raw), hashlib.sha256(raw).hexdigest())
receipt = {"sealed": True, "passed": True, "blocking_findings": [], "input_pins": before,
    "created_outside_author_graph": {status_rel: status_pin}, "changed_docs": changed,
    "historical_Oct15_tail_unchanged": True, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024,
    "PE_engine_decoder_game_operations": 0, "tests_run": 0, "new_effects": 0, "new_requests": 0}
data = (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
rp = create(OUT / "receipt.json", data)
print(json.dumps({"receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
