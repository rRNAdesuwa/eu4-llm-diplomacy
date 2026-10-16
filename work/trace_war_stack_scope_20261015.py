"""Offline native stack-storage evidence and a smaller no-send research scope."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget

OUT = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope/war"
GAME_SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
BORROWED = "work/reports/war-peace-api-20261015-r6-borrowed/war/access-table.json"
SOURCES = (BORROWED,
           "work/reports/war-peace-api-20261015-r6-borrowed/war/manifest.json",
           "work/discover_diplomacy.py", "work/trace_war_stack_scope_20261015.py")
SELECTED = ("construct", "resolve_NULL_goal", "action_body_destructor",
            "goal_not_owned", "destroy_empty_vector")
REPORT = """# 宣战动作的原生栈存储与更小的无发送范围

游戏自身确实在栈上构造0x98宣战动作，随后调用非deleting body destructor。
因此R6‘source必须使用匹配allocator’属于其heap/deleting-wrapper实验，不能
推广到所有原生constructor使用方式。这里单独描述caller-owned stack storage，
不修改R6旧候选，也不开放executor或native_ready。

固定EXE SHA9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a，
所有地址为RVA。普通离线Capstone/PE重放，不是运行观测。新增唯一caller
解码1072B；5个最小正常slice复用固定借用访问表，未重复解码。

## 原生调用现场

已从.pdata入口b096c0连续解码至b09af0，完整核对1072B。该函数的5个push
之后RBP=RSP-30，随后分配130B栈帧；动作位于RBP-70，即最终RSP+90。
0x98对象覆盖当前RSP+[90,128)，位于130B局部帧内，且在普通Win64入口
RSP模16为8的前提下动作地址16字节对齐。构造器最高已证字段为+90的
8字节写，与0x98大小一致。

b0994f以LEA RCX,[RBP-70]，b09953调用500480；b099b3/b099b7及
b099c3/b099c7分别以同一stack address调用500560 body destructor，
未调用500520 deleting wrapper释放stack storage。

该原生caller实际传非NULL生成goal、internal stability=true，且调用local
508db0并删除临时goal；它不是本报告NULL-goal/false/no-check实验的实测，
不能把整个caller当成纯函数，也不能据此绕过普通宣战检查。这里只用它
证明native constructor/body-dtor支持caller stack storage和清理形态。

## 独立更小范围

研究范围仅为：在独占caller-owned、16字节对齐且至少98B storage上调用
500480(actor,target,false,date,NULL)，随后一次500560 body destructor；
不clone、不deleting wrapper、不local/full检查、不execute、不包装或发送。

复用已核正常slice：constructor将NULL传给d9aaf0，NULL分支只从模块槽
2340030取sentinel指针；constructor把三个vector的begin/end/cap全清零。
body dtor读goal+0→vtable+78，要求实际仍为1d207f8.slot78=8f450；其false
叶无payload读取，然后三次8eac0因begin==0直接返回。该特定路径没有
action/goal/vector分配或free，没有CRT allocator/new-handler调用，没有
definition payload读取，也没有国家/world对象解引用。

这是‘特定分支不达allocator’的静态可达性结论，不是运行期已经证明
条件成立。若goal类型、NULL分支或空vector前提不成立，其他路径完全不同。
必须使用body500560；heap deleting wrapper500520不能用于stack。

## 仍然需要的证据

析构仍真实读borrowed sentinel header并通过它分派一次；native_ready继续
false。必须证明该header在原生调用期间有效、槽没有替换/retire以及相应
类型/模块/线程/ABI上下文有效；事前事后相等、nonnull或vtable匹配不能
单独提供该寿命授权。当前owner身份/撤销研究另行进行。

没有实现或运行新native executor，没有分配游戏对象、安装DLL、访问游戏、
发送请求或改变旧no-repeat策略。这个更小实验不能替代clone/full-check/
execute/send/效果和持久化测试，也不证明宣战API已经完成。

复现：python -B work/trace_war_stack_scope_20261015.py --check。
check只核文件pin、固定PE、caller与复用slice字节、stack偏移及分支调用
集合；不重复解码、不访问游戏。source/report/evidence全部独立封存。
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)}


def verify_rows(pe, rows):
    for row in rows:
        raw = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw


def check_shape(data):
    rows = {int(x["rva"], 16): x for x in data["caller"]["instructions"]}
    assert rows[0xb0994f]["bytes"] == "488d4d90"
    assert rows[0xb09953]["bytes"] == "e8286b9fff"
    for lea, call in ((0xb099b3, 0xb099b7), (0xb099c3, 0xb099c7)):
        assert rows[lea]["bytes"] == "488d4d90"
        assert rows[call]["mnemonic"] == "call" and rows[call]["operands"] == "0x500560"
    assert 0x130 - 0x30 - 0x70 == 0x90
    assert 0x90 + 0x98 == 0x128 <= 0x130
    direct, indirect = set(), set()
    for path in data["reused_normal_paths"]:
        for row in path["instructions"]:
            if row["mnemonic"] == "call":
                (direct if row["operands"].startswith("0x") else indirect).add(row["operands"])
    assert direct == {"0xd9aaf0", "0x8eac0"}
    assert indirect == {"qword ptr [rax + 0x78]"}
    assert data["native_ready"] is False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert sha(pe.data) == GAME_SHA and len(pe.data) == 38462504
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_bytes())
        for p in manifest["files"]:
            assert pin(ROOT / p["path"]) == p
        data = json.loads((OUT / "evidence.json").read_bytes())
        for p in data["source_pins"]:
            assert pin(ROOT / p["path"]) == p
        raw = bytes.fromhex(data["caller"]["bytes"])
        assert pe.function(0xb096c0)[:2] == (0xb096c0, 0xb09af0)
        assert len(raw) == 1072 and pe.bytes_at(0xb096c0, 1072) == raw
        assert b"".join(bytes.fromhex(x["bytes"]) for x in data["caller"]["instructions"]) == raw
        verify_rows(pe, data["caller"]["instructions"])
        for p in data["reused_normal_paths"]:
            verify_rows(pe, p["instructions"])
        assert struct.unpack("<Q", pe.bytes_at(0x1d207f8 + 0x78, 8))[0] == pe.base + 0x8f450
        check_shape(data)
        print(json.dumps({"check": "passed", "replayed_caller_bytes": 1072,
                          "reused_paths": 5, "new_decode_on_check": 0,
                          "peak_committed_bytes": check_memory_budget()}))
        return
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    assert md is not None and cs.__version__ == "5.0.7"
    assert pe.function(0xb096c0)[:2] == (0xb096c0, 0xb09af0)
    raw = pe.bytes_at(0xb096c0, 1072)
    ins = list(md.disasm(raw, 0xb096c0))
    assert b"".join(i.bytes for i in ins) == raw
    old = json.loads((ROOT / BORROWED).read_bytes())
    paths = [p for p in old["paths"] if p["name"] in SELECTED]
    assert len(paths) == 5
    for p in paths:
        verify_rows(pe, p["instructions"])
    data = {"schema": "eu4-war-stack-storage-and-constructor-body-dtor-scope-v1",
            "evidence_type": "ordinary_offline_capstone_and_retained_instruction_replay_not_runtime",
            "game_sha256": GAME_SHA, "preferred_base": hex(pe.base),
            "source_pins": [pin(ROOT / p) for p in SOURCES],
            "caller": {"entry_rva": "0xb096c0", "end_rva": "0xb09af0", "bytes": raw.hex(),
                       "sha256": sha(raw), "instructions": [
                           {"rva": hex(i.address), "bytes": i.bytes.hex(),
                            "mnemonic": i.mnemonic, "operands": i.op_str} for i in ins]},
            "native_caller_actual_parameters": {"goal": "nonnull generated object", "internal_stability": True,
                                                "local_check_called": True, "same_as_proposed_reduced_scope": False},
            "stack_storage": {"locals_bytes": 0x130, "rbp_from_post_push_rsp": -0x30,
                              "object_from_rbp": -0x70, "object_from_final_rsp": 0x90,
                              "object_bytes": 0x98, "alignment_under_Win64_entry_rsp_mod16_8": 16},
            "reused_normal_paths": paths,
            "reduced_scope": {"construct": "0x500480", "body_destroy": "0x500560",
                              "goal_arg": None, "internal_stability": False,
                              "clone": False, "delete_wrapper": False, "checks": False, "execute": False,
                              "send": False, "vectors": "constructor initializes all three empty",
                              "normal_PE_allocator_calls_in_selected_branches": 0,
                              "normal_PE_definition_payload_reads_in_selected_branches": 0,
                              "borrowed_goal_header_last_read": "0x500577", "derived_dispatch": "0x50057a",
                              "header_lifetime_authority_proved": False},
            "new_unique_decoded_bytes": 1072, "decode_budget_bytes": 8192, "capstone_version": cs.__version__,
            "native_ready": False, "runtime_verified": False, "process_accessed": False,
            "native_calls": 0, "requests_published": 0, "game_objects_allocated": 0,
            "peak_committed_bytes": check_memory_budget()}
    check_shape(data)
    OUT.mkdir(parents=True, exist_ok=False)
    for name, contents in (("evidence.json", (json.dumps(data, indent=2) + "\n").encode()),
                           ("report.md", REPORT.encode())):
        with (OUT / name).open("xb") as f:
            f.write(contents)
    manifest = {"schema": "eu4-war-stack-scope-manifest-v1", "native_ready": False,
                "files": [pin(OUT / "evidence.json"), pin(OUT / "report.md"), pin(Path(__file__).resolve())]}
    mraw = (json.dumps(manifest, indent=2) + "\n").encode()
    with (OUT / "manifest.json").open("xb") as f:
        f.write(mraw)
    print(json.dumps({"manifest_sha256": sha(mraw), "new_unique_decoded_bytes": 1072,
                      "peak_committed_bytes": data["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
