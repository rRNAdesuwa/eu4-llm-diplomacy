"""Publish accepted R74 DATA and the narrowed successor scope."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/reports/continuation-publication-20261016-r8"
PINS = {}
COUNT = 0


def pair(n, sha):
    return {"bytes": n, "sha256": sha}


def read(rel, expected=None):
    global COUNT
    p = ROOT / rel
    assert p.stat().st_size <= 4 * 1024 * 1024
    raw = p.read_bytes()
    COUNT += len(raw)
    assert COUNT <= 2 * 1024 * 1024
    value = pair(len(raw), hashlib.sha256(raw).hexdigest())
    assert expected is None or value == expected, rel
    assert rel not in PINS or PINS[rel] == value
    PINS[rel] = value
    return raw


def create(path, raw):
    with path.open("xb") as f:
        f.write(raw)
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
base = "work/reports/server-current-label-data-actual-independent-review-20261016-r1/"
f = json.loads(read(base + "findings.json", pair(4665, "ca73da61c7a2a39c4bdd8385d2dbcae36e01f06c43c1eb57ae41455974136dec")))
m = json.loads(read(base + "manifest.json", pair(11203, "65497b00cd9c40f94f764e3c19febe7a38b39fc5f705a58eb3497b30ab4dc7f6")))
assert f["sealed"] is True and f["passed"] is True and f["blocking_findings"] == [] and m["sealed"] is True
assert f["subject_data_final_manifest"] == pair(7720, "7f096329cca0943de70d2bfb47ac35cd31f9c6f4233ff65f68f8ae55eda2d55a")
assert f["subject_owned_pin"] == pair(1192, "e755eab8cdf753effb2752ec5571065f8115b14ba973a2af901eed41eea98865")
docs = {n: read(n) for n in ("HANDOFF.md", "README(agent).md", "docs/war-peace-api-1375.md")}
before = dict(PINS)
for rel, expected in before.items():
    read(rel, expected)
OUT.mkdir()
for name, raw in docs.items():
    create(OUT / (name.replace("/", "__") + ".before"), raw)
status_rel = "work/reports/server-current-label-data-20261016-r1/DATA_REVIEW_STATUS.md"
status = """# R74 fixed DATA accepted

2026-10-16：[完整非作者独审](../server-current-label-data-actual-independent-review-20261016-r1/findings.json)通过，53 pins、49 flat文件。

唯一读取的22B为 `696e746572666163652f66726f6e74656e642e677569`，ASCII/UTF8均为 `interface/frontend.gui`，owned范围内无NUL。来源是R72已验收的16+4+2 RIP复制线索；没有读取源byte23或邻域，没有打开该GUI文件。

该文字像相对GUI资源路径属于分析推断，不能证明类名、模式、receiver关联、game+1e00或宿主兼容。producer/source/auth/三review前后与正常文件关闭后提交已核；本审只重放保留文件，没有重复PE、engine、decoder或游戏操作。现有宿主守卫保持，当前和平队列仍unknown。本文件位于冻结作者图之外，不授权后续采集或重试。
""".encode("utf8")
sp = create(ROOT / status_rel, status)
handoff = docs["HANDOFF.md"].decode("utf8")
end = handoff.index("\n")
head = """## 2026-10-16 最新继续点：R74完整独审通过；R75单metadata/最多24B源码，R76对比源码，v5继续

最新调度覆盖下方pending：R74 full PASS，server-current-label-data-actual-independent-review-20261016-r1/findings4665Bca73da61c7a2a39c4bdd8385d2dbcae36e01f06c43c1eb57ae41455974136dec /manifest11203B65497b00cd9c40f94f764e3c19febe7a38b39fc5f705a58eb3497b30ab4dc7f6，53pins/49flat。data-final7720B7f096329…/contract4549B37b9cd32…/owned1192Be755eab8…/capture32305B4497cb7f…都冻结，唯一22B interface/frontend.gui、ownedNULNone；源byte23/邻域/GUI文件均未读。不认class/mode/receiver/game+1e00/hostguardcompatible/effect。source606754、PE76925030、retainedupper1291518、combined1898272；源码三gate/auth734743…与正常close后commit均已审。不重采、不第二游戏status，新DATA_REVIEW_STATUS冻结图外。

R75 Root已明确准Val仅source/budget准备，新war-peace-api-20261016-r75-null-successor-fragment/：继承R69 JE993595 raw0f84bd000000到993658，F=S69-58、RAX/R12全64零，R8非nonnullSAR、R71保存未执行，D0/headerzero不继承。比D原32record提案更紧：唯一新record19163@RVA249d244/file37139012，12B；cachedprev19162@/pdata_requests/14 [993643,993658)、cachednext19164@/13 [993670,9936a7)已D确认。因此candidate必须begin993658/end>begin/两邻disjoint，span最多24B完整读；失败unknown0code，绝不bsearch/prefix/fallback，不新增19164读取/其它code/callee/header/unwind。source_guard授权rawbuffer先验/两basepin+首外check/38engine metadata/source32+seal16/768M1GiBstop/双EXESHA/close后capture保持。未来需要R69full+新rootraw+sourcepeer+oncegrant，当前无R75actual。D会sourcepeer，不能读mutableprep。

D完成R74 full后正准备R76 source/budget-only，新server-expected-vtable-reference-owner-20261016-r1/，唯一R70 rawsite8032de/488d057b514b01→1cb8460。复用R72r2已修rawmanifest guard与containing算法；未来<=32metadata、selected.begin full<=8192else2048，anchor不cover/unreached就unknown/no移窗/单anchorqueue。只问原始引用和opaque receiver；不能命名constructor/class/mode或宿主兼容，不跟另外3candidate/RIPdata/callee/vslots/header/unwind。Val R75先freeze则D优先其peer；R76未actual。Root等待两份freeze做新rawseed独审。

War正在v5离线lookup：59entries/拟74直接JSON，旧58/59原样；新engine copy唯一count64→96明确批准，其余预算/parser不放宽，原d423和v1-v4不改。fixture首batchexit1：97-source与4M+1 expected拒绝已沿真实trace到达，后置Windows反斜杠路径bookkeeping line45失败、percase rawjournal未落；原failed不改、不写3tests passed、不重这些已到达机制。Root批准独立aggregate-only delta首次执行，原source/index/data/engine/wrapper不变、newdelta脚本另在finalauthor manifest pin，physical全部含首failchild5MiB保守+controller2.973M等<=16M，synthetic<=40M单列。4首queries原runner尚未执行可继续；新engine/delta/限定fixture见证需后续非作者完整审裁定。无PE/game/native/requests/ZIP或机器v5发布；accepted仍v4。

以下R73/R72/R71及所有全局限制继续有效；旧authorpreview/pending由本段覆盖。\n"""
changed_raw = {"HANDOFF.md": (head + handoff[end:]).encode("utf8")}
readme = docs["README(agent).md"].decode("utf8")
old = "R74唯一22B已读取、待完整独审"
assert readme.count(old) == 1
changed_raw["README(agent).md"] = readme.replace(old, "[R74资源名数据](work/reports/server-current-label-data-20261016-r1/DATA_REVIEW_STATUS.md)已完整独审").encode("utf8")
war = docs["docs/war-peace-api-1375.md"].decode("utf8")
old = "R74唯一22B数据已读、待完整独审"
assert war.count(old) == 1
changed_raw["docs/war-peace-api-1375.md"] = war.replace(old, "[R74固定22B数据](../work/reports/server-current-label-data-20261016-r1/DATA_REVIEW_STATUS.md)已完整独审").encode("utf8")
marker = b"## 2026-10-15 "
assert changed_raw["HANDOFF.md"][changed_raw["HANDOFF.md"].index(marker):] == docs["HANDOFF.md"][docs["HANDOFF.md"].index(marker):]
changed = {}
for rel, raw in changed_raw.items():
    assert read(rel, before[rel]) == docs[rel]
    (ROOT / rel).write_bytes(raw)
    changed[rel] = pair(len(raw), hashlib.sha256(raw).hexdigest())
receipt = {"sealed": True, "passed": True, "blocking_findings": [], "input_pins": before,
    "created_outside_author_graph": {status_rel: sp}, "changed_docs": changed,
    "historical_Oct15_tail_unchanged": True, "selected_read_bytes": COUNT, "maximum": 2 * 1024 * 1024,
    "PE_engine_decoder_game_operations": 0, "tests_run": 0, "new_effects": 0, "new_requests": 0}
rp = create(OUT / "receipt.json", (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode())
print(json.dumps({"receipt": rp, "selected_read_bytes": COUNT}, ensure_ascii=True))
