"""Independent retained-byte review of outer owner identity and empty cleanup."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r6-owner-boundary/war"
OUT = ROOT / "work/reports/war-peace-api-20261015-r6-owner-boundary-review"
MANIFEST = "62463c42ca1938d9a9570f87512186d4e54b3fa5c8fb3993a6305f3deeb688a8"
GAME = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) < 16 * 1024 * 1024
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
    assert pin(SOURCE / "manifest.json")["sha256"] == MANIFEST
    sources = {}
    def fixed(path):
        row = pin(path)
        sources[row["path"]] = row
        return row
    fixed(SOURCE / "manifest.json")
    manifest = json.loads((SOURCE / "manifest.json").read_bytes())
    for row in manifest["files"]:
        got = fixed(SOURCE / row["path"])
        assert (got["bytes"], got["sha256"]) == (row["bytes"], row["sha256"])
    evidence = json.loads((SOURCE / "findings.json").read_bytes())
    assert len(evidence["source_pins"]) == 8
    for name, row in evidence["source_pins"].items():
        got = fixed(ROOT / name)
        assert (got["bytes"], got["sha256"]) == (row["bytes"], row["sha256"])
    rows, intervals, new_bytes = {}, [], 0
    def replay(items):
        for row in items:
            raw = bytes.fromhex(row["bytes"])
            at = int(row["rva"], 16)
            assert pe.bytes_at(at, len(raw)) == raw
            if row["rva"] in rows:
                assert rows[row["rva"]]["bytes"] == row["bytes"]
            rows[row["rva"]] = row
    for name in ("owner-construction", "owner-publication", "owner-exit", "owner-release-path",
                 "owner-driver", "owner-shutdown", "base-owner-destruction"):
        data = json.loads((SOURCE / (name + ".json")).read_bytes())
        for region in data["regions"]:
            at, size = int(region["entry_rva"], 16), region["bytes"]
            raw = b"".join(bytes.fromhex(r["bytes"]) for r in region["instructions"])
            assert len(raw) == size and pe.bytes_at(at, size) == raw
            assert hashlib.sha256(raw).hexdigest() == region["raw_sha256"]
            pos = at
            for row in region["instructions"]:
                assert int(row["rva"], 16) == pos
                pos += len(bytes.fromhex(row["bytes"]))
            intervals.append((at, at + size))
            new_bytes += size
            replay(region["instructions"])
    intervals.sort()
    assert all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:]))
    assert new_bytes == 7395 and len(evidence["reused_instructions"]) == 99
    replay(evidence["reused_instructions"])
    for row in evidence["static_data"]:
        raw = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]

    startup = json.loads((ROOT / "work/reports/native-startup-continue-1375.json").read_bytes())
    world = json.loads((ROOT / "work/reports/native-world-epoch-1375.json").read_bytes())
    main_rows = startup["functions"]["0x8757e0"]["instructions"]
    body_rows = world["functions"]["0x1fefa0"]["instructions"]
    replay(main_rows)
    replay(body_rows)
    prior_teardown = json.loads((ROOT / "work/reports/war-peace-api-20261015-r6-registry-lifetime/war/teardown.json").read_bytes())
    wrapper = next(r for r in prior_teardown["regions"] if r["entry_rva"] == "0x1fee80")
    replay(wrapper["instructions"])
    def ins(at, expected):
        assert rows[hex(at)]["instruction"] == expected
    def relative(at, target):
        raw = bytes.fromhex(rows[hex(at)]["bytes"])
        assert raw[0] in (0xe8, 0xe9) and at + 5 + struct.unpack_from("<i", raw, 1)[0] == target
    def rip(at, target):
        raw = bytes.fromhex(rows[hex(at)]["bytes"])
        assert at + len(raw) + struct.unpack_from("<i", raw, len(raw) - 4)[0] == target
    ins(0x877d7a, "mov ecx, 0x6a8")
    ins(0x877d9c, "mov rcx, rax")
    relative(0x877d9f, 0x1fe8f0)
    ins(0x1fe90d, "mov rsi, rcx")
    ins(0x1fe999, "mov rcx, rsi")
    relative(0x1fe99c, 0x14bfd80)
    ins(0x14bfda0, "mov rbx, rcx")
    rip(0x14bff6f, 0x242bf50)
    rip(0x1fea19, 0x1c48bf8)
    rip(0x1fea23, 0x1c48c80)
    ins(0x1fea20, "mov qword ptr [rsi], rax")
    ins(0x1fea2a, "mov qword ptr [rsi + 0x10], rax")
    ins(0x1fee17, "mov rax, rsi")
    for table, target in ((0x1c48bf8, 0x1fee80), (0x1c48c80, 0x219190), (0x1c64948, 0x4503d0),
                          (0x1c48bf8 + 0x48, 0x955a0), (0x1c48bf8 + 0x50, 0x212b30)):
        assert struct.unpack("<Q", pe.bytes_at(table, 8))[0] == pe.base + target
    ins(0x219190, "sub rcx, 0x10")
    relative(0x219194, 0x1fee80)
    relative(0x1fee8f, 0x1fefa0)
    ins(0x1fee94, "test bl, 1")
    ins(0x1fee99, "mov edx, 0x6a8")
    relative(0x1feea1, 0x17394f0)
    for at, expected in ((0x878696, "mov rbx, qword ptr [rcx]"), (0x878699, "mov qword ptr [rcx], rdx"),
                         (0x87869f, "je 0x8786bb"), (0x8786d6, "mov rbx, qword ptr [rcx]"),
                         (0x8786dc, "je 0x8786f8")):
        ins(at, expected)
    for at in (0x8786a4, 0x8786e1):
        relative(at, 0x1fefa0)
    for at in (0x8786a9, 0x8786e6):
        ins(at, "mov edx, 0x6a8")
    for at in (0x8786b6, 0x8786f3):
        relative(at, 0x17394f0)
    # Inspect every retained main instruction, including partial-register uses,
    # rather than relying only on assemble.py's five-mnemonic destination scan.
    rsi_destinations = [r for r in main_rows if r["instruction"].split(",")[0].split()[-1]
        in ("rsi", "esi", "si", "sil")]
    assert [(r["rva"], r["instruction"]) for r in rsi_destinations] == [
        ("0x8757e6", "push rsi"), ("0x875803", "xor esi, esi"), ("0x8783ae", "pop rsi")]
    assert not any(r["instruction"].startswith("xchg ") and any(reg in r["instruction"].replace(",", " ").split()
        for reg in ("rsi", "esi", "si", "sil")) for r in main_rows)
    assert not any(r["instruction"].split()[0] in ("lodsb", "lodsw", "lodsd", "lodsq", "movsb", "movsw", "movsq", "rep", "repne")
        or (r["instruction"].split()[0] == "movsd" and "xmm" not in r["instruction"]) for r in main_rows)
    ins(0x877d16, "mov qword ptr [rsp + 0x60], rsi")
    ins(0x877da5, "mov rdx, rax")
    ins(0x877da8, "lea rcx, [rsp + 0x60]")
    relative(0x877dad, 0x878690)
    ins(0x877e28, "mov rbx, qword ptr [rsp + 0x60]")
    ins(0x8781b1, "mov rcx, rbx")
    relative(0x8781b4, 0x14c2d00)
    ins(0x87823d, "mov qword ptr [rsp + 0x60], rsi")
    ins(0x87828d, "lea rcx, [rsp + 0x60]")
    relative(0x878292, 0x8786d0)
    assert all("[rsp + 0x60]" not in r["instruction"] for r in main_rows
        if 0x87823d < int(r["rva"], 16) < 0x87828d)
    ins(0x44fa42, "mov ecx, 0x628")
    rip(0x44fa94, 0x1c64948)
    rip(0x44fb0e, 0x242baf0)
    rip(0x20609c, 0x242baf0)
    rip(0x2060a3, 0x242baf0)
    ins(0x2060b7, "call qword ptr [rax]")
    ins(0x20968b, "mov ecx, 0x800")
    relative(0x209698, 0x2812a0)
    rip(0x2096a0, 0x233d8d0)
    relative(0x74ddc3, 0x286250)
    ins(0x74ddc8, "mov edx, 0x800")
    ins(0x14c2d12, "mov rsi, rcx")
    ins(0x14c2dc0, "call qword ptr [rax + 0x48]")
    ins(0x14c2e27, "call qword ptr [rax + 0x50]")
    ins(0x212b37, "mov byte ptr [rax + 0x120], 1")
    ins(0x955a0, "ret 0")
    rip(0x1ff734, 0x242bed0)
    rip(0x1ff73b, 0x242bed0)
    ins(0x1fefdd, "xor r12d, r12d")
    relative(0x1ff747, 0x488210)
    relative(0x200328, 0x14c0010)
    assert evidence["contract"]["normal_exit_outer_destructor_proven"] is False
    assert evidence["contract"]["return_to_menu_outer_destructor_proven"] is False
    assert evidence["contract"]["definition_reload_outer_destructor_proven"] is False
    assert evidence["contract"]["owner_lifetime_lease_proven"] is False
    assert evidence["contract"]["native_ready"] is False
    candidates = json.loads((SOURCE / "owner-slot-candidates.json").read_bytes())
    assert len(candidates["refs"]) == 536
    assert candidates["complete_indirect_alias_or_caller_coverage"] is False
    assert json.loads((SOURCE / "owner-immediate-clear-candidates.json").read_bytes())["complete_alias_coverage"] is False
    fixed(Path(__file__))
    result = dict(schema="EU4-WAR-OUTER-OWNER-INDEPENDENT-REVIEW/1",
        review_status="conditional_type_this_and_empty_branch_claims_consistent", findings=[],
        target_manifest_sha256=MANIFEST, original_source_pin_count=8, source_pins=list(sources.values()),
        replay=dict(new_scope_retained_bytes=7395, reused_selected_rows=99,
            full_retained_main_and_body_rows_replayed=True, prior_52_byte_deleting_wrapper_replayed=True,
            fresh_disassembly_reexecuted=False),
        observed=[
            dict(id="construction_and_publication", chain="877d7a size6a8 ->877d9f ctor1fe8f0; ctor RSI=RCX ->1fe99c base14bfd80; base RBX=RCX ->14bff6f global242bf50", identity="primaryvt1c48bf8, secondaryvt1c48c80 at owner+10"),
            dict(id="secondary_this_adjustment", chain="owner+10 interface slot0=219190; SUB RCX,10 ->1fee80", wrapper="1fee80 calls1fefa0 and conditionally frees size6a8 for flags&1"),
            dict(id="conditional_owning_helpers", chain="878690 replaces holder before deleting old nonNULL;8786d0 only deletes nonNULL current; both1fefa0 then size6a8 free"),
            dict(id="empty_normal_cleanup", chain="875803 RSI=0;877d16 holder initialized0;877dad holder gets ctor result;877e28 RBX gets owner;87823d holder=RSI=0;878292 cleanup follows8786dc empty-return", qualification="Ordinary preserved-register ABI and normal returns; no recursive callee/alias noninterference proof"),
            dict(id="distinct_country_database", identity="233d8d0,size800,ctor2812a0,body286250 differs from242bf50,size6a8,ctor1fe8f0"),
            dict(id="distinct_other_global_object", identity="44fa42 size628,44fa94 vt1c64948,44fb0e publishes242baf0;20609c loads/clears that slot before virtual0", qualification="Observed construction paths differ; not an all-future-rebinding exclusion"),
            dict(id="shutdown_partial_closure", chain="14c2d00 thisRSI; selfvt48 ->955a0 RET0; selfvt50 ->212b30 writes another global object's byte+120", qualification="Other virtual receivers/recursive callees remain unresolved; selected callees do not establish total no-destruction"),
            dict(id="conditional_registry_reclamation", chain="If1fefa0 is invoked and reaches1ff734, old242bed0 is read then cleared1ff73b, nonNULL calls488210; final200328 ->base14c0010", qualification="No actual nonempty normal exit/menu/reload event bound")],
        limits=[
            "Static construction and module slots do not establish a full-interval object lifetime or current runtime values.",
            "The normal local holder store releases local ownership; it is not itself an object destructor, global clear or registry revocation.",
            "The zero-holder cleanup result is conditional on ordinary Win64 callee-saved registers and absence of unproved alias/reentrant modification; no runtime claim.",
            "536 raw MOV/LEA candidates and empty immediate-clear scan are bounded pattern observations, not complete alias/computed-call/virtual/reset-load coverage.",
            "Different observed allocation/type paths exclude this specific alias inference, not arbitrary future global rebinding.",
            "Startup origins, process exit or local holder disappearance cannot replace the unknown nonempty normal exit/menu/reload destruction path.",
            "Allocator failure/handler/reentry, exceptions/unwind, concurrent callbacks, world/module authority and native readiness remain open."],
        scope_exclusions=["new owning-recipient analysis", "root hash/vector callee closure", "runtime captures", "native execution"],
        native_ready=False, native_calls=0, requests_published=0, game_process_accessed=False,
        frozen_sources_modified=False, resources=dict(new_decoded_bytes=0, memory_limit_bytes=768*1024*1024,
            peak_committed_bytes=check_memory_budget(), shell_sessions_remaining=0))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "independent-review.json").open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    with (OUT / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("# Independent outer-owner boundary review\n\n"
            "No contradiction found in the conditional identity/this/empty-branch claims. Replayed the sealed7395B,99 selected reused instructions, full retained main/body records and earlier52B deleting wrapper against the fixed PE. The8 original source pins and21 manifest files match. No new decode.\n\n"
            "The6a8 allocation calls1fe8f0; its unchanged this enters base14bfd80 and is published at242bf50. Derived primaryvt1c48bf8 and secondaryvt1c48c80 at+10 are linked by219190 subtracting10 before1fee80. The deleting wrapper/body and two nonempty holder helpers are genuine conditional destruction paths. CountryDB233d8d0/800 and observed242baf0/628/vt1c64948 are distinct construction paths. This does not exclude future slot rebinding.\n\n"
            "Main RSI stays zero under ordinary preserved-register ABI. It zeros holderRSP+60 at87823d before878292;8786d0 therefore takes its empty return on that retained normal path. Clearing local ownership is not destroying the outer object. Calls between the store and cleanup do not directly address the holder, but recursive alias/reentry noninterference was not proved. No nonempty normal exit/menu/reload destructor event is established.\n\n"
            "Shutdown14c2d00's two selected self slots are RET0 and a write to another global object's state byte. Other child/global virtual receivers and recursive callees remain unresolved. The conditional1fefa0 clear242bed0 then488210 boundary is preserved without turning it into a current lifetime lease. Candidate scans are not all-alias coverage; allocator/exception and full-interval lifetime authority remain unknown. native_ready=false; no game access, native call, send or frozen-source modification.\n")
    seal = dict(schema="EU4-OWNER-BOUNDARY-REVIEW-MANIFEST/1", files=[pin(Path(__file__)),
        pin(OUT / "independent-review.json"), pin(OUT / "report.md")])
    with (OUT / "manifest.json").open("x", encoding="ascii") as stream:
        json.dump(seal, stream, indent=2)
    print(json.dumps(dict(review=pin(OUT / "independent-review.json"), markdown=pin(OUT / "report.md"),
        manifest=pin(OUT / "manifest.json"), source_pins=len(sources), new_decoded_bytes=0, native_ready=False)))


if __name__ == "__main__":
    main()
