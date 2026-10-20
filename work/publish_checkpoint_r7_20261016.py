"""Publish accepted R73 and current task ownership; preserve historical docs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/reports/continuation-publication-20261016-r7"
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
    value = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert expected is None or value == expected, rel
    assert rel not in PINS or PINS[rel] == value
    PINS[rel] = value
    return raw


def create(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
review = "work/reports/war-peace-api-20261016-r73-actual-independent-review/"
f = json.loads(read(review + "findings.json", pair(5251, "5794b82df03b9fd1f407d3384f81fb366349f6cc7133c010f50d2206cfa2fd88")))
m = json.loads(read(review + "manifest.json", pair(18044, "49d74153ee25a06a54fa03cb3711647e7fa5939a19a9183f4e7c4cc03f416afb")))
assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
assert f["subject_manifest"] == pair(24623, "a5eb1ebbfe46c9d590aa118729a330499a226d828458248c45530ada0feb987b")
audit = "work/reports/runtime-entry-manifest-order-review-20261016-r1/"
af = json.loads(read(audit + "final-findings.json", pair(4139, "ac6676e8fe41a9d49276bd8da4e2faa4ed23ee5f30f5d52682e18d8db8f02dae")))
am = json.loads(read(audit + "final-manifest.json", pair(5257, "5eec86b233a863be8e92fb8d466a6e92cb676b3e9e334684728bdbe143a3af7b")))
assert af["sealed"] is True and af["passed"] is True and af["blocking_findings"] == [] and am["sealed"] is True
auth_rel = "work/reports/server-current-label-data-20261016-r1/run-authorization.json"
auth = json.loads(read(auth_rel, pair(2938, "734743f37d9ccb01650d636f9710965b36fc3e351ad5082b55a6b1b846879129")))
assert auth["sole_executor"] == "validation_audit" and auth["requested_bytes"] == 22
docs = {n: read(n) for n in ("HANDOFF.md", "README(agent).md", "docs/war-peace-api-1375.md")}
before = dict(PINS)
for rel, expected in before.items():
    read(rel, expected)
OUT.mkdir()
for name, raw in docs.items():
    create(OUT / (name.replace("/", "__") + ".before"), raw)
status_rel = "work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/REVIEW_STATUS.md"
status = """# R73 nonpositive successor accepted

2026-10-16：[完整非作者独审](../war-peace-api-20261016-r73-actual-independent-review/findings.json)通过，56 pins、51 flat文件。唯一21B、9条指令、0 CALL/branch/store，993657正常RET。

片段读取保存的R15，将当前R14复制到RAX，恢复栈后返回。显式[F+78]、五POP及RET共7次QWORD栈读取；返回值是POP前的指针位型。与原D指针的对应需要此前callee正常保持、有效栈与别名条件。片段没有显式D/header解引用，仍不能证明D=0、header不变、金额单位、原请求效果或整个993570函数闭合。NULL993658与外部callee仍未知。

固定rawmanifest先验、两次EXE SHA、正常目标文件关闭后的守卫与唯一采集均通过保留文件审查，未重复PE/engine/decoder或游戏操作。本文件在冻结作者图之外；无后续采集或重试授权。
""".encode("utf8")
status_pin = create(ROOT / status_rel, status)
handoff = docs["HANDOFF.md"].decode("utf8")
line_end = handoff.index("\n")
head = """## 2026-10-16 最新继续点：R73完整独审通过，R74唯一DATA已执行待final，v5新engine窄改

本段优先于下方历史pending。R73 full PASS：r73-actual-independent-review/findings5251B5794b82df03b9fd1f407d3384f81fb366349f6cc7133c010f50d2206cfa2fd88 /manifest18044B49d74153ee25a06a54fa03cb3711647e7fa5939a19a9183f4e7c4cc03f416afb（完整前缀work/reports/war-peace-api-20261016-）。56pins/51flat/38engine metadataonly；21B9rows0CALL/branch/store、7Q/56B栈read，RAX=currentR14在POP前，ADD RSP30重写arithflags。localRET不证明D0/headerzeros/NULL993658/wholefunction/units/effect。author actual-manifest24623Ba5eb1ebb…/contract13212B5eb88b02…/capture73174B362d4112…/owned906B531d218c…全部冻结、禁止重采。rootgrant2698Bc30dfb4b…及rootreceipt4007Bcf7edf7c…已使用；新REVIEW_STATUS冻结图外。下方R73 source-only状态已过时。

R74 pureDATA source和raw已完整通过：server-current-label-data-20261016-r1/source4424Bf698e1c6…/producer18606B3fcd780d…/seed2514B1467f4d8…。rootraw findings2325B40ccc51ed55a4f454bc6c9d603baee3f088731e30ff993e302fffa9d5105d18e /manifest2212B5869c05ce5d39ce4b1919fb263e8a645c36866c43ef529205257a97a3f082c87；Dsourcepeer14578B255e4dacb2a0fd636e16cb951c1d2878eb453ea0374e4ad5c8f2fa21f695daec /7874B934daa1897090fe112d93fbb2c853d62f73757c9130db807ae1e300269017f0a。root新grant2938B734743f37d9ccb01650d636f9710965b36fc3e351ad5082b55a6b1b846879129、rootreceipt4055Bd9bd0c910b3f087645d3a7f9e66b1b02abf2c9939937c8785a11ae6423ccf25c已仅派Val一次并collected exit0。22B raw696e746572666163652f66726f6e74656e642e677569=interface/frontend.gui，owned内无NUL；不读byte23/邻域。当前仅作者预览、Val正在retained seal，不能重actual/读mutable包；caption资源名不证类/模式/hostguard兼容，不跟GUI文件或其它ref。capture作者预览32305B4497cb7f…/65sourceevents606754/PE76925030/peak13619200。D稍后full peer。当前仍无第二游戏status。

War正在离线lookup v5：保留旧58entries/59JSON全部dataequal，仅新993570条目+R71/R73条件fragmentcontext，共59entries；拟15新直接JSON，共74sources。冻结16583Bd4237d98…engine有sources<=64，root已明确准新v5 engine副本唯一常量64→96，旧v1-v4与原engine不改；wrapper新BASE path/SHA及DATA_SHA/revision/help，parser/Io32M/ordinary4M不变。新engine需完整非作者审，不能自称frozenengine相同。准3首次guardfixtures：97-source prebody拒/4MiB+1假file拒/aggregate32MiB用2MiB owned buffer virtualreader跨阈；synthetic≤40M与physicalfixture≤16M分账，不冒32MiB磁盘证明。4首次v5queries check/catalog/lookup993570/search993643，build/seal32M/query64M另账；未ZIP/发布机器v5目录，当前accepted仍v4。

R75 D仅文件proposal已冻：war-peace-api-20261016-r75-null-successor-proposal/manifest4799Ba2f2348b…/proposal6393B155c546a…/seed15329Bc4c90d80…；原JE993595 raw0f84bd000000→993658，20缓存requests/17unique无19163/exactbegin，长度未知。R69NULL继承F=S69-58、RAX/R12全64零、R8不是nonnullSAR、R71保存未执行、D0/headerzero不继承。root拟更紧候选index19163@249d244/file37139012及必要邻19164@249d250/file37139024最多24B，复用prev19162；candidate.begin!=993658或邻不disjoint即unknown0code/no binarysearchfallback，再full<=8192else2048prefix。尚待D缓存数学确认，未准sourceprep或actual。

有限入口guard-order盘点也已完成：runtime-entry-manifest-order-review-20261016-r1/final-findings4139Bac6676e8…/final-manifest5257B5eec86b2…，只index+15ownedcopies，不recursivebase/原program。5entry先parse本manifest、return另读pin；固定sourceanchors/exact_compile/前后graph检查也存在。公共observer同raw返pin但imports先于本entryguard，lookup委托base内部未知。只列未来可选hardening，不判toolblocked/历史/effect失效、不改工具。completeupper6636192<8M，corrigendum另留，全部shell收齐。

以下R72/R71/v4/余额交叉表及全局禁重发保持有效；任何旧pending由本段覆盖。\n"""
changed_raw = {"HANDOFF.md": (head + handoff[line_end:]).encode("utf8")}
readme = docs["README(agent).md"].decode("utf8")
old = "R73仅21B后继源码审查，R74仅22B数据读取器准备。"
assert readme.count(old) == 1
changed_raw["README(agent).md"] = readme.replace(old, "[R73后继](work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/REVIEW_STATUS.md)已完整独审；R74唯一22B已读取、待完整独审；lookup v5正在补新入口。").encode("utf8")
war = docs["docs/war-peace-api-1375.md"].decode("utf8")
old = "R73仅准备21B非正值后继。"
assert war.count(old) == 1
war = war.replace(old, "[R73非正值后继](../work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/REVIEW_STATUS.md)21B已完整独审，仅确认条件返回指针，金额仍未知。")
old = "R74仅准备固定22B身份线索的数据读取，宿主守卫保持。"
assert war.count(old) == 1
war = war.replace(old, "R74唯一22B数据已读、待完整独审，原始资源名interface/frontend.gui不证明类或模式，宿主守卫保持。")
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
    "PE_engine_decoder_game_operations": 0, "tests_run": 0, "new_effects": 0, "new_requests": 0,
    "R74_DATA_status_is_author_preview_only": True, "v5_not_yet_accepted": True}
rp = create(OUT / "receipt.json", (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode())
print(json.dumps({"receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
