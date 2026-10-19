"""File-only independent review of registry first insertion and hash clear."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r9-registry-insert/war"
OUT = ROOT / "work/reports/war-peace-api-20261015-r9-registry-insert-review"
MANIFEST = "7b554338d786e6474bc38388c5588077157fe49cab57e00811810c0ea9fdf480"
GAME = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) < 16 * 1024 * 1024
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert len(pe.data) == 38462504 and hashlib.sha256(pe.data).hexdigest() == GAME
    if args.check:
        result = json.loads((OUT / "independent-review.json").read_bytes())
        for row in result["source_pins"]:
            assert pin(ROOT / row["path"]) == row
        seal = json.loads((OUT / "manifest.json").read_bytes())
        for row in seal["files"]:
            assert pin(ROOT / row["path"]) == row
        print(json.dumps(dict(status="passed", source_pins=len(result["source_pins"]),
            manifest_files=len(seal["files"]), new_decoded_bytes=0, game_process_accessed=False)))
        return
    sources = {}
    def fixed(path):
        row = pin(path)
        sources[row["path"]] = row
        return row
    assert fixed(SOURCE / "manifest.json")["sha256"] == MANIFEST
    manifest = json.loads((SOURCE / "manifest.json").read_bytes())
    for row in manifest["files"]:
        assert fixed(ROOT / row["path"]) == row
    evidence = json.loads((SOURCE / "evidence.json").read_bytes())
    assert len(evidence["source_pins"]) == 8
    for row in evidence["source_pins"]:
        assert fixed(ROOT / row["path"]) == row
    rows, addresses = {}, set()
    functions = {int(f["entry_rva"], 16): f for f in evidence["functions"]}
    for function in functions.values():
        for row in function["instructions"]:
            at, raw = int(row["rva"], 16), bytes.fromhex(row["bytes"])
            assert pe.bytes_at(at, len(raw)) == raw
            assert not addresses.intersection(range(at, at + len(raw)))
            addresses.update(range(at, at + len(raw)))
            rows[at] = row
    assert len(addresses) == evidence["new_unique_decoded_bytes"] == 871
    for row in evidence["reused_initializer_rows"]:
        at, raw = int(row["rva"], 16), bytes.fromhex(row["bytes"])
        assert pe.bytes_at(at, len(raw)) == raw
        rows[at] = row
    assert len(evidence["reused_initializer_rows"]) == 17
    getter = json.loads((ROOT / "work/reports/war-peace-api-20261015-r6-registry-lifetime/war/owner-getter.json").read_bytes())
    for region in getter["regions"]:
        for old in region["instructions"]:
            raw = bytes.fromhex(old["bytes"])
            at = int(old["rva"], 16)
            assert pe.bytes_at(at, len(raw)) == raw
            mnemonic, _, operands = old["instruction"].partition(" ")
            rows[at] = dict(**old, mnemonic=mnemonic, operands=operands)
    def ins(at, mnemonic, operands):
        assert (rows[at]["mnemonic"], rows[at]["operands"]) == (mnemonic, operands)
    def relative(at, target):
        raw = bytes.fromhex(rows[at]["bytes"])
        assert raw[0] in (0xe8, 0xe9) and at + 5 + struct.unpack_from("<i", raw, 1)[0] == target
    def rip(at, target):
        raw = bytes.fromhex(rows[at]["bytes"])
        assert at + len(raw) + struct.unpack_from("<i", raw, len(raw) - 4)[0] == target
    # Independently reconstruct normal local reachability across split pdata.
    cfg_checks = []
    for entry, expected_end in ((0xcc220, 0xcc338), (0x8eb80, 0x8ec23)):
        own = {int(r["rva"], 16): r for r in functions[entry]["instructions"]}
        pending, reached, branch_edges = [entry], set(), []
        while pending:
            at = pending.pop()
            if at in reached:
                continue
            assert at in own
            reached.add(at)
            row = own[at]
            raw = bytes.fromhex(row["bytes"])
            mnemonic, operand = row["mnemonic"], row["operands"]
            if mnemonic in ("ret", "int3"):
                continue
            if mnemonic.startswith("j"):
                target = int(operand, 16)
                if raw[0] == 0xeb or 0x70 <= raw[0] <= 0x7f:
                    actual = at + len(raw) + struct.unpack_from("<b", raw, 1)[0]
                else:
                    assert raw[0] == 0xe9 or (raw[0] == 0x0f and 0x80 <= raw[1] <= 0x8f)
                    actual = at + len(raw) + struct.unpack_from("<i", raw, len(raw)-4)[0]
                assert actual == target and target in own
                pending.append(target)
                branch_edges.append((hex(at), hex(target)))
                if mnemonic == "jmp":
                    continue
            pending.append(at + len(raw))
        assert reached == set(own)
        assert addresses.issuperset(range(entry, expected_end))
        assert sum(len(bytes.fromhex(r["bytes"])) for r in own.values()) == expected_end - entry
        cfg_checks.append(dict(entry=hex(entry), local_bytes=expected_end-entry,
            all_retained_rows_normal_CFG_reachable=True, raw_relative_branches_checked=branch_edges,
            calls_modelled_as_normal_returns_only=True))

    for at, mnemonic, operand in (
        (0x1b378f,"cmp","qword ptr [rdx + 0x30], 0x10"), (0x1b3794,"lea","r10, [rdx + 0x18]"),
        (0x1b3798,"mov","rsi, rdx"), (0x1b379b,"mov","rdi, rcx"),
        (0x1b37a0,"mov","r10, qword ptr [rdx + 0x18]"),
        (0x1b37a4,"movsxd","rdx, dword ptr [rdx + 0x28]"), (0x1b37c0,"movsx","eax, byte ptr [r8 + r10]"),
        (0x1b37c8,"add","eax, r9d"), (0x1b37cb,"imul","r9d, eax, 0x3d"),
        (0x1b37d9,"div","dword ptr [rcx + 4]"), (0x1b37dc,"mov","ecx, 0x10"),
        (0x1b37fe,"mov","rdx, qword ptr [r8 + rcx]"), (0x1b3802,"mov","qword ptr [rax], rsi"),
        (0x1b380a,"mov","qword ptr [rax + 8], rdx"), (0x1b3812,"mov","qword ptr [r8 + rcx], rax"),
        (0x1b3816,"inc","dword ptr [rdi]"), (0x8ebd0,"mov","rbx, qword ptr [rcx + 8]"),
        (0x8ebd4,"mov","edx, 0x10"), (0x8ebec,"mov","qword ptr [r14 + rax], rbp"),
        (0x8ebff,"mov","dword ptr [rdi], ebp")):
        ins(at,mnemonic,operand)
    relative(0x1b37e3,0x1a332d4)
    clear_calls = [r["operands"] for r in functions[0x8eb80]["instructions"] if r["mnemonic"] == "call"]
    assert clear_calls == ["0x17394f0"]
    relative(0x8ebd9,0x17394f0)
    assert not any(r["mnemonic"] == "mov" and r["operands"].endswith("qword ptr [rcx]")
        for r in functions[0x8eb80]["instructions"])
    ins(0xda48da,"mov","dword ptr [rax + 4], 0x1ff")
    ins(0xda48e1,"mov","ecx, 0xff8")
    relative(0xda48fc,0x1a35e00)
    for at in (0xda4901,0xda4905,0xda4909):
        assert rows[at]["operands"].endswith(", rdi")
    rip(0xda4a93,0x2340038)
    rip(0xda4aa2,0x2340038)
    relative(0xda4a9d,0x1b3780)
    relative(0xda4acf,0xcc220)
    ins(0xda4aa9,"mov","qword ptr [rbp + 0x8d8], rax")
    ins(0xda4ac4,"lea","r8, [rbp + 0x8d8]")
    ins(0xda4acb,"lea","rcx, [r13 + 0x10]")
    ins(0xcc241,"sar","rbp, 3")
    ins(0xcc245,"sar","rax, 3")
    ins(0xcc277,"lea","r12, [rax + 1]")
    ins(0xcc27b,"shr","rdx, 1")
    ins(0xcc2c6,"lea","rax, [rdx + rcx]")
    ins(0xcc2ca,"mov","rdi, r12")
    ins(0xcc2d0,"cmovae","rdi, rax")
    ins(0xcc291,"lea","rcx, [rdi*8]")
    relative(0xcc29e,0x950b0)
    ins(0xcc2a3,"mov","rcx, qword ptr [r13]")
    ins(0xcc2aa,"mov","qword ptr [rax + rbp*8], rcx")
    ins(0xcc2bf,"jne","0xcc2db")
    ins(0xcc2c1,"sub","r8, rdx")
    ins(0xcc2c4,"jmp","0xcc2f4")
    relative(0xcc2f4,0x1a35750)
    relative(0xcc305,0xc9d60)
    relative(0x950f0,0x1a332d4)
    ins(0xc9d86,"je","0xc9db9")
    ins(0xc9dbd,"mov","qword ptr [rbx], rdi")
    ins(0xc9dc5,"mov","qword ptr [rbx + 8], rax")
    ins(0xc9dd2,"mov","qword ptr [rbx + 0x10], rax")
    ins(0x1a3575a,"cmp","r8, 0xf")
    ins(0x1a35770,"mov","r9d, dword ptr [r10 + r8*4 + 0x2550000]")
    ins(0x1a3577b,"jmp","r9")
    ins(0x1a3577e,"ret","")
    raw = pe.bytes_at(0x1a35753,7)
    assert 0x1a35753 + 7 + struct.unpack_from("<i",raw,3)[0] == 0
    assert struct.unpack("<I",pe.bytes_at(0x2550000,4))[0] == 0x1a3577e
    assert pe.bytes_at(0x1a3577e,1) == b"\xc3"
    # Arithmetic is a conditional abstract trace of fixed rows, not a native test.
    begin = end = cap = insert = 0
    count, index, capacity = (end-begin)//8,(insert-begin)//8,(cap-begin)//8
    new_count = count+1
    half = capacity>>1
    new_capacity = max(new_count,capacity+half)
    assert (count,index,capacity,new_count,new_capacity,new_capacity*8) == (0,0,0,1,1,8)
    assert insert == end and end-begin == 0
    B,D = 0x200000,0x300000
    new_buffer = {B+index*8:D}
    published = dict(begin=B,end=B+new_count*8,cap=B+new_capacity*8)
    assert new_buffer[B] == D and published == dict(begin=B,end=B+8,cap=B+8)
    assert evidence["all_allocator_failure_and_exception_paths_closed"] is False
    assert evidence["native_ready"] is False
    fixed(Path(__file__))
    result = dict(schema="EU4-REGISTRY-FIRST-INSERT-INDEPENDENT-REVIEW/1",
        review_status="selected_normal_first_append_and_hash_semantics_consistent", findings=[],
        target_manifest_sha256=MANIFEST, original_source_pin_count=8, source_pins=list(sources.values()),
        replay=dict(sealed_new_bytes=871,reused_initializer_rows=17,new_decoded_bytes=0,
            local_CFG=cfg_checks, fresh_disassembly_reexecuted=False),
        conclusions=dict(hash="16-byte node saves definition at+0, oldhead at+8, links node and increments count; signed-char 32-bit h=61*(h+ch) then unsigned bucket remainder",
            hash_clear="Only next-pointer+8 and allocator free(node,16) in local CFG; clears heads/count, no definition-owning deletion",
            zero_capacity_first_append=dict(count=count,index=index,new_count=new_count,new_capacity=new_capacity,
                allocation_bytes=8,captured_input="definition from2340038 captured privately before cc220",
                pointer_write="cc2a3/cc2aa ->newbuffer[0]",memmove="cc2f4(B,NULL,0) ->table2550000[0] RVA1a3577e RET",
                publish="c9d60 old begin NULL skips free;begin=B,end=B+8,cap=B+8",
                abstract_trace_is_runtime_evidence=False),
            prior_gap="Normal first-full-capacity append and concrete hash insertion/clear callees are now closed under explicit valid-storage/stable-input assumptions"),
        limits=["Allocator returning eventually does not exclude failure handlers, callbacks, reentry, exceptions or input mutation before return.",
            "Zeroing helper1a35e00 is only a retained call boundary; table initialized/valid storage is a normal-path precondition.",
            "Only memmove length0 table path is closed, not nonzero copying, whole memmove or CRT exceptional control flow.",
            "Call-return CFG closure assumes ordinary ABI/normal returns and is not an unwind or ownership transfer proof.",
            "Other nonempty vectors, collision/uniqueness/duplicate policy, all registry reset/reload semantics and sentinel release remain open.",
            "Current or future borrowed definition/sentinel/owner lifetime, interval lease and native execution authority are not established."],
        native_ready=False, game_process_accessed=False, native_calls=0, requests_published=0,
        frozen_sources_modified=False, resources=dict(new_decoded_bytes=0,peak_committed_bytes=check_memory_budget(),
            memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-review.json").open("x",encoding="ascii") as f:
        json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent registry insertion review\n\n"
            "The871B fixed bytes,17 retained initializer rows and8 original source pins match. Independent local reachability covers all280B ofCC220 and163B of8EB80 across split pdata, checking each relative branch from its bytes. No new decode or contradiction in the selected conditional claims.\n\n"
            "Hash1B3780 links a16-byte node storing definition+0/next+8 and increments count. Hash clear8EB80 reads next+8, frees16-byte nodes and clears bucket heads/count; its local CFG has no definition payload dereference or owning deletion. Valid initialized buckets/name/allocator results remain prerequisites; zeroing helper1A35E00 was not recursively analysed.\n\n"
            "For stable begin=end=cap=0, captured definition, and valid returned storage, CC220 computes count/index0, new count/capacity1 and requests8B. CC2A3/CC2AA write captured definition to newbuffer[0]. CC2F4 calls memmove(B,NULL,0); module-base-relative table2550000[0] selects1A3577E RET. C9D60 skips oldNULL free and publishes B/B+8/B+8. This closes the original first-growth path gap, rather than extrapolating from spare capacity.\n\n"
            "Only normal valid-storage/stable-input semantics are closed. Allocator handlers/reentry, exceptions, nonzero memmove, larger vectors and all-reset/lifetime/lease authority remain unproved. Existing conditional stale-pointer risk remains; native_ready=false. No game access, native calls, new effects, frozen edits or additional test authority.\n")
    seal=dict(schema="EU4-REGISTRY-INSERT-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-review.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:
        json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-review.json"),markdown=pin(OUT/"report.md"),
        manifest=pin(OUT/"manifest.json"),source_pins=len(sources),new_decoded_bytes=0,native_ready=False)))


if __name__ == "__main__":
    main()
