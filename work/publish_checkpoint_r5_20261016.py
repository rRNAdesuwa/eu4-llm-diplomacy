"""Publish accepted retained findings; preserve original docs and historical tail."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/reports/continuation-publication-20261016-r5"
PINS = {}
READS = 0


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(rel, expected=None):
    global READS
    path = ROOT / rel
    assert path.stat().st_size <= 4 * 1024 * 1024
    raw = path.read_bytes()
    READS += len(raw)
    assert READS <= 2 * 1024 * 1024
    actual = pin(raw)
    assert expected is None or actual == expected, rel
    assert rel not in PINS or PINS[rel] == actual
    PINS[rel] = actual
    return raw


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def create(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
    return pin(raw)


assert not OUT.exists()
accepted = {}
for name, folder, fp, mp in (
    ("R71", "war-peace-api-20261016-r71-actual-independent-review", pair(8035, "40dbb7199f02244bcf1f95dba475db87171a81e226b7e0238004f788312cb045"), pair(12660, "9bcd6706361cb07936763b868f9f384e399194f4900f774ef91fe042c2eb3a96")),
    ("balance_R1", "peace-balance-field-crosswalk-independent-review-20261016-r1", pair(6145, "380397c058e3fdbc77ec537f8766766550bc4df10dd25fcde9a72e6539b924ae"), pair(5330, "f55ff73a29b7dc10135cd6672bb44e921797815021ab251e49cd70b1560f1490")),
    ("balance_R2", "peace-balance-field-crosswalk-independent-20261016-r2", pair(8916, "d420b6cc7a3e04e0d723b360c812ed7b69d3e47c23f6e6c82783e3236543caa7"), pair(7333, "b1f6c930a365c7d8b8ba3658d599700c9a82dd6f6862a5ea5c6994c6376e25cc")),
):
    fpath, mpath = "work/reports/" + folder + "/findings.json", "work/reports/" + folder + "/manifest.json"
    findings = json.loads(read(fpath, fp))
    manifest = json.loads(read(mpath, mp))
    assert findings["sealed"] is True and findings["passed"] is True and findings["blocking_findings"] == []
    assert manifest["sealed"] is True
    accepted[name] = {"findings": {"path": fpath, **fp}, "manifest": {"path": mpath, **mp}}
assert json.loads(read(accepted["R71"]["findings"]["path"]))["subject_manifest"] == pair(24771, "df5a1d0e3918347ff95d7199b184adefed4a816b2f08dc3dd2bba4576823777f")
assert json.loads(read(accepted["balance_R1"]["findings"]["path"]))["subject_manifest"] == pair(5900, "cc2500f69b5be7f97105cbbd515e23ce85a60a33fee716fb99aa648790cd1c23")
auth_rel = "work/reports/server-vtable-current-reference-owner-20261016-r2/run-authorization.json"
auth = json.loads(read(auth_rel, pair(3112, "ca80aeecfdce93e3cd4a9bda9909e96061912bf9c7f59724106b53765432bcd8")))
assert auth["sole_executor"] == "validation_audit" and auth["R1_remains_blocked"] is True
docs = {name: read(name) for name in ("HANDOFF.md", "README(agent).md", "docs/war-peace-api-1375.md")}
before = dict(PINS)
for name, expected in before.items():
    read(name, expected)
OUT.mkdir()
for name, raw in docs.items():
    create(OUT / (name.replace("/", "__") + ".before"), raw)
status_texts = {
    "work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/REVIEW_STATUS.md": """# R71 retained fragment accepted

2026-10-16：156B、42条指令的唯一采集与完整非作者审查已通过。[独审](../war-peace-api-20261016-r71-actual-independent-review/findings.json)绑定43 actual pins及38个engine元数据见证。

片段含一次ADD32[currentR14],EBX，以及12B记录追加。993643的非正值出口、993658的先前NULL出口和两个外部callee仍未闭合；一个RET不代表整个函数完成。最终D、金额单位、收款方向、原请求效果均未知。

旧采集源的source_guard采用事后manifest复核；未宣称外部原子性或排除ABA。后续R73采用已审raw-buffer pin先验窄修，不追溯重跑本次采集。执行、重试、宿主守卫修改与新效果权限均false。此文件在冻结作者图之外。
""",
    "work/reports/peace-balance-field-crosswalk-20261016-r1/REVIEW_STATUS.md": """# Balance-field crosswalk R1 accepted

2026-10-16：[非作者独审](../peace-balance-field-crosswalk-independent-review-20261016-r1/findings.json)通过，固定8个来源、14 subject pins。BB0仅在同root、同country对象、接收方传播和正常callee等前提下，对应reader的signed DWORD。BD4是相距0x24的另一字段。

treasury_milli名称、常数1000和raw双国守恒均不证明议和单位或效果；R60只采用已验收合同见证。本轮无PE、游戏、测试或原请求重发。此文件在冻结作者图之外。
""",
    "work/reports/peace-balance-field-crosswalk-20261016-r2/REVIEW_STATUS.md": """# Balance-field crosswalk R2 accepted

2026-10-16：[非作者独审](../peace-balance-field-crosswalk-independent-20261016-r2/findings.json)通过，固定5个业务来源、11 author pins。原request/session记录FRA +457736、SCO -457736，raw总额守恒；未迁移为当前议和效果。

金币body从4f3fe0后fresh DWORD取EBX并传入两个wrapper。可见IMUL1000流向另一helper，之后local又被EBX覆盖，因此不能证明金币或和平金额换算。显式amount、显示值、完整双方handle、初始化、epoch及单位仍未知。此文件在冻结作者图之外。
"""
}
created = {name: create(ROOT / name, text.encode("utf8")) for name, text in status_texts.items()}
handoff = docs["HANDOFF.md"].decode("utf8")
cut = handoff.index("用户已撤回误发的")
new_head = """## 2026-10-16 最新继续点：R71完整独审通过，R72 R2唯一actual已执行、待封存独审

最新调度优先于下方历史发布段。用户要求继续、未完成勿擅停，误发打包已撤回。R71 full已PASS：war-peace-api-20261016-r71-actual-independent-review/findings8035B40dbb7199f02244bcf1f95dba475db87171a81e226b7e0238004f788312cb045、manifest12660B9bcd6706361cb07936763b868f9f384e399194f4900f774ef91fe042c2eb3a96。156B42rows/2CALL4branch1RET；ADD32与12B追加已证，但非最终D/单位/recipient/效果。R71新REVIEW_STATUS位于冻结图外，旧source_guard事后manifest复核局限明确；不追溯重采。

R72 R1永久blocked。R2 source24090Bba3735d3…/producer26805B902a2908…/seed4236B0ad3aeb8…，raw root2114B8d7ed1e0…/4733B23eb03d7…，War full source7896B0d379a3b…/15775B9875840d…均PASS。rawbuffer一次读先bytes/SHA再parse/engine，前后调用均basepin、首次guard前后外check；其余九helper和containing算法保持。root唯一grant3112Bca80aeecfdce93e3cd4a9bda9909e96061912bf9c7f59724106b53765432bcd8、rootreceipt4166B01327b9849e84022fe37453308f569413342c52a5690c331299dec31c5a26a5d；只派Val一次。Val已collected exit0：pdata[10d23c0,10d2bfd)2109B/418rows，anchor10d24e3 LEA RAX,1d5a8c8紧随10d24ea MOV[RDI],RAX。当前仅作者预览待final/fullpeer，不能读取mutable包/重actual/改hostguard；class/mode/layout仍未知。20metadata240B/17unique204B、PE76927357、源17885120、ownpeak27725824；正常close和prepost为作者见证。Val正在retained seal；War稍后完整非作者审。

余额crosswalk R1/R2均完整非作者PASS：R1 Val findings6145B380397c058e3fdbc77ec537f8766766550bc4df10dd25fcde9a72e6539b924ae /manifest5330Bf55ff73a29b7dc10135cd6672bb44e921797815021ab251e49cd70b1560f1490；R2 War findings8916Bd420b6cc7a3e04e0d723b360c812ed7b69d3e47c23f6e6c82783e3236543caa7 /manifest7333Bb1f6c930a365c7d8b8ba3658d599700c9a82dd6f6862a5ea5c6994c6376e25cc。条件BB0对应reader signedDWORD，BD4另字段。原金币request/session raw FRA+457736/SCO-457736守恒；无amount/display/full双方handle，4f3fe0初始化和EBX=457736未知。IMUL1000流另一helper且local被EBX覆盖，不能证明gold/peace单位。没有新效果或请求。

和平下一范围R73仅source/budget准备，D作者：固定[993643,993658)21B，复用R69/pdata_requests/14/index19162 raw433699005836990024dde701，newpdata0、无fallback、不读end993658。proposal manifest6573B695823e4…/proposal9547Bc14b8d0f…已冻。继承R71 JLE9935b2 raw0f8e8b000000的signedlow32<=0路径、S69-58/正常ABI/别名条件，不重置Win64formals、不继承D0。R73采用已审rawbuffer guard窄改，不复制R72containing；需新raw/fullupstream/sourcepeer三gate及root一次grant，当前无actual。无自动callee/数据/其它出口扩展。

以下是较早发布时点，任何pending由上面最新调度覆盖。\n\n"""
new_handoff = (new_head + handoff[cut:]).encode("utf8")
marker = b"## 2026-10-15 "
assert new_handoff[new_handoff.index(marker):] == docs["HANDOFF.md"][docs["HANDOFF.md"].index(marker):]
readme = docs["README(agent).md"].decode("utf8")
title = readme.index("# EU4 单机外交桥接原型")
new_readme = ("2026-10-16 最新：[API lookup v4](work/candidates/war-peace-api-lookup-1375-v4/REVIEW_STATUS.md)58端点/59JSON已验收；[R71](work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/REVIEW_STATUS.md)156B和[余额字段对照](work/reports/peace-balance-field-crosswalk-20261016-r2/REVIEW_STATUS.md)已完整独审。R72 R2单次静态采集已返回、待完整独审，宿主类型与和平队列兼容仍unknown；R73仅21B后继源码准备。48/44/42、稳定15profiles及禁重发不变，全部120未完成，未打包。先读HANDOFF顶部；下文是历史时点。\n\n" + readme[title:]).encode("utf8")
war = docs["docs/war-peace-api-1375.md"].decode("utf8")
end = war.index("新版[结果读取缺口盘点]")
new_war = ("# 宣战与议和 API 原生合同（1.37.5）\n\n2026-10-16最新：[API lookup v4](../work/candidates/war-peace-api-lookup-1375-v4/REVIEW_STATUS.md)已完整独审，58项/59JSON，原54项不变。[R71片段](../work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/REVIEW_STATUS.md)已确认一次32位累加和12B记录追加，仍有两条未读出口与外部callee；R73仅准备21B非正值后继。R72 R2的单次静态采集已返回，正在封存并待完整独审，不能据此修改宿主守卫。宣战和议和执行器尚未完成。\n\n[余额字段对照R2](../work/reports/peace-balance-field-crosswalk-20261016-r2/REVIEW_STATUS.md)已完整独审：BB0对应reader仍有同root、对象和receiver条件；原金币请求记录raw等额增减，但可见×1000不能证明金币或议和单位。当前和平队列兼容仍unknown，未做第二status、保存、重载或新外交请求。下文保留历史研究时点。\n\n" + war[end:]).encode("utf8")
changed = {}
for name, raw in (("HANDOFF.md", new_handoff), ("README(agent).md", new_readme), ("docs/war-peace-api-1375.md", new_war)):
    assert read(name, before[name]) == docs[name]
    (ROOT / name).write_bytes(raw)
    changed[name] = pin(raw)
receipt = {"sealed": True, "passed": True, "blocking_findings": [], "accepted": accepted,
    "input_pins": before, "created_outside_frozen_author_graphs": created, "changed_docs": changed,
    "historical_Oct15_tail_unchanged": True, "selected_read_bytes": READS,
    "maximum": 2 * 1024 * 1024, "PE_engine_decoder_game_accesses": 0, "tests_run": 0,
    "R72_actual_status_is_author_preview_only": True, "new_effects": 0, "new_requests": 0}
result = create(OUT / "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode())
print(json.dumps({"receipt": result, "selected_read_bytes": READS, "changed_docs": changed}, ensure_ascii=True))
