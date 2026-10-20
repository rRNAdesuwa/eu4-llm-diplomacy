"""Offline closure of selected registry insertion/clear helpers; no native calls."""
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
from map_diplomacy_fields import bounded_cfg

OUT = ROOT / "work/reports/war-peace-api-20261015-r9-registry-insert/war"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
RANGES = ((0x1b3780, 0x1b381e), (0xc9d60, 0xc9de7), (0x950b0, 0x95108),
          (0x1a35750, 0x1a3577f))
SOURCES = ("work/discover_diplomacy.py", "work/map_diplomacy_fields.py",
           "work/reports/war-peace-api-20261015-r6-registry-lifetime/war/owner-getter.json",
           "work/reports/war-peace-api-20261015-r6-registry-lifetime/war/manifest.json",
           "work/reports/war-peace-api-20261015-r6-registry-lifetime/war/corrigendum-manifest-r2.json",
           "work/reports/war-peace-api-20261015-r6/war/reused-functions.json",
           "work/reports/war-peace-api-20261015-r6/war/disassembly.json",
           "work/trace_goal_registry_insert_20261015.py")
REPORT = """# Registry 首次 vector 追加与 hash 节点的窄语义

本范围补原registry R2明确留下的callee缺口，不修改旧报告或manifest。
固定EXE SHA9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a，
所有地址为RVA。871B新普通Capstone指令；无游戏访问、native调用、安装
或发送。以下正常语义都有有效storage、完整构造和相应分支保持的前提，
不是运行期观测或寿命许可，native_ready=false。

## Hash 插入与清空

1b3780实际从definition内嵌string+18/+28/+30取得名字字节，用signed char
逐字参与32位hash h=61*(h+ch)，除owner+4的bucket count取余。分配10B
node；1b3802写node+0=definition，1b380a写node+8=旧head，1b3812把
新node发布到bucket，1b3816增加owner+0计数。因此它确实构造并链接
保存definition指针的hash节点，不只是把实参传给不明callee。

原da48b0 getter直接写bucket count1ff、分配ff8B bucket storage，并以
length=ff8/byte=0调用1a35e00；本报告不递归展开该zeroing helper。Hash正常
路径要求bucket count非0、storage/名字有效；allocator失败/handler/异常
与插入时重入不在此正常语义保证内，也不据allocator最终返回消除handler。

8eb80的完整本地CFG跨过.pdata拆分prefix，遍历每个bucket的10B链节点，
先读node+8保存next再free(node,10)，然后清head/计数；它不读取node+0
并删除definition。因此这条hash clear只删除节点，不提供definition的
拥有式销毁。定义的virtual0(1)删除仍来自另一个vector消费者488210。

## 第一次 zero-cap vector 追加

原da4aa2捕获definition到private stack，da4acf的RCX=&owner.vector、
RDX=end、R8=&捕获pointer。入口begin=end=cap=0时，cc220完整CFG推得
count=0、insert index=0、new count=1、new capacity=1，950b0以8B尾调
原operator new。新buffer正常返回且相关输入未变时，cc2a3读取捕获pointer，
cc2aa直接写newbuffer[0]=definition。

随后cc2f4调用1a35750(newbuffer,NULL,0)。本报告只解码memmove前缀与
长度0 switch：table2550000[0]=1a3577e，其单字节RET直接返回，不读取
NULL源或覆盖已写pointer，不把整个memmove其他长度称已闭合。

cc305→c9d60在old begin=NULL分支跳过free；c9dbd/c9dc5/c9dd2发布
begin=newbuffer、end=newbuffer+8、cap=newbuffer+8。因此在这些正常稳定
前提下，第一次追加的pointer写与header发布闭合，补齐旧spare-cap之外
的缺口。对已非空/更大vector，本报告只保留CFG/调用，不保证所有元素
移动、allocator异常和异常拥有移交。

## 边界

cc220与8eb80都具有连续拆分.pdata范围，不能把最初70B/27B prefix当
完整函数；本轮本地CFG分别280B/163B。普通calls列为边界，只有明确
必要的allocator veneer950b0、header helperc9d60及memmove长度0另行跟随。
operator new及CRT失败路径复用原R6证据，不新增运行保证。字符串hash
不证明唯一性、重复排除或全部registry语义。

本报告没有证明定义/owner在任何未来原生调用期间存活，没有证明所有
reset/load/退出行为或sentinel60的释放机制。旧条件悬空风险和R2边界补正
保留，native_ready=false；没有新的动作重测许可。

复现：python -B work/trace_goal_registry_insert_20261015.py --check。
check只重放871B保留字节、源pin和table0，不新增解码或访问游戏。
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert sha(pe.data) == SHA and len(pe.data) == 38462504
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_bytes())
        for p in manifest["files"]:
            assert pin(ROOT / p["path"]) == p
        data = json.loads((OUT / "evidence.json").read_bytes())
        for p in data["source_pins"]:
            assert pin(ROOT / p["path"]) == p
        addresses = set()
        for f in data["functions"]:
            for row in f["instructions"]:
                rva = int(row["rva"], 16)
                raw = bytes.fromhex(row["bytes"])
                assert pe.bytes_at(rva, len(raw)) == raw
                assert not addresses.intersection(range(rva, rva + len(raw)))
                addresses.update(range(rva, rva + len(raw)))
        assert len(addresses) == data["new_unique_decoded_bytes"] == 871
        assert pe.bytes_at(0x2550000, 4).hex() == data["memmove_zero_table_entry"]["bytes"]
        assert struct.unpack("<I", pe.bytes_at(0x2550000, 4))[0] == 0x1a3577e
        assert pe.bytes_at(0x1a3577e, 1) == b"\xc3"
        for row in data["reused_initializer_rows"]:
            raw = bytes.fromhex(row["bytes"])
            assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw
        print(json.dumps({"check": "passed", "replayed_bytes": len(addresses), "new_decode_on_check": 0,
                          "source_pins": len(data["source_pins"]), "peak_committed_bytes": check_memory_budget()}))
        return
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    assert md is not None and cs.__version__ == "5.0.7"
    functions = []
    for entry in (0xcc220, 0x8eb80):
        rows, edges = bounded_cfg(pe, md, entry, window=2048, max_instructions=350)
        functions.append({"entry_rva": hex(entry), "method": "local_CFG_across_split_pdata",
                          "edges": edges, "instructions": [
                              {"rva": hex(i.address), "bytes": i.bytes.hex(),
                               "mnemonic": i.mnemonic, "operands": i.op_str} for i in rows]})
    for start, end in RANGES:
        raw = pe.bytes_at(start, end-start)
        rows = list(md.disasm(raw, start))
        assert b"".join(i.bytes for i in rows) == raw
        functions.append({"entry_rva": hex(start), "end_rva": hex(end),
                          "method": "exact_pdata_range" if start != 0x1a35750 else "entry_prefix_and_length0_leaf_only",
                          "instructions": [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                                            "mnemonic": i.mnemonic, "operands": i.op_str} for i in rows]})
    total = sum(len(bytes.fromhex(x["bytes"])) for f in functions for x in f["instructions"])
    assert total == 871 <= 8192
    old = json.loads((ROOT / SOURCES[5]).read_bytes())
    reused = [r for f in old["functions"] for r in f["instructions"] if 0xda4a86 <= int(r["rva"],16) <= 0xda4acf]
    assert len(reused) == 17
    for row in reused:
        raw = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"],16),len(raw)) == raw
    data = {"schema": "eu4-registry-insert-normal-semantics-v1", "game_sha256": SHA,
            "evidence_type": "ordinary_offline_capstone_and_PE_replay_not_runtime",
            "source_pins": [pin(ROOT / p) for p in SOURCES], "functions": functions,
            "memmove_zero_table_entry": {"rva": "0x2550000", "bytes": pe.bytes_at(0x2550000,4).hex(),
                                         "target_rva": "0x1a3577e", "target_bytes": "c3"},
            "reused_initializer_rows": reused, "new_unique_decoded_bytes": total, "decode_budget_bytes": 8192,
            "normal_first_append_preconditions": ["begin=end=cap=0 at entry and inputs remain stable",
                                                  "allocator returns valid buffer; callback/failure behavior not excluded by return alone",
                                                  "captured definition pointer and owner storage are valid"],
            "all_allocator_failure_and_exception_paths_closed": False, "native_ready": False,
            "process_accessed": False, "native_calls": 0, "requests_published": 0,
            "peak_committed_bytes": check_memory_budget()}
    OUT.mkdir(parents=True, exist_ok=False)
    for name, raw in (("evidence.json", (json.dumps(data,indent=2)+"\n").encode()), ("report.md", REPORT.encode())):
        with (OUT/name).open("xb") as f:
            f.write(raw)
    manifest = {"schema": "eu4-registry-insert-manifest-v1", "native_ready": False,
                "files": [pin(OUT/"evidence.json"),pin(OUT/"report.md"),pin(Path(__file__).resolve())]}
    raw = (json.dumps(manifest,indent=2)+"\n").encode()
    with (OUT/"manifest.json").open("xb") as f:
        f.write(raw)
    print(json.dumps({"manifest_sha256":sha(raw),"new_unique_decoded_bytes":total,
                      "peak_committed_bytes":data["peak_committed_bytes"]}))


if __name__ == "__main__":
    main()
