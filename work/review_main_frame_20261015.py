"""Independent fixed-byte current-app relay and selected stack arithmetic review."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"work"))
from discover_diplomacy import PE,check_memory_budget
SOURCE=ROOT/"work/reports/war-peace-api-20261015-r6-main-frame/war"
OUT=ROOT/"work/reports/war-peace-api-20261015-r6-main-frame-review"
MANIFEST="91048604c9c02c1a5529eedd1526ef8525b0025af464e28c9422eec9a8ed1ca0"
GAME="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw=path.read_bytes()
    assert len(raw)<16*1024*1024
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def normalize(r):
    return dict(rva=r["rva"],bytes=r["bytes"],instruction=r.get("instruction",(r.get("mnemonic","")+" "+r.get("operands","")).rstrip()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    pe=PE(ROOT.parent/"eu4.exe")
    assert len(pe.data)==38462504 and hashlib.sha256(pe.data).hexdigest()==GAME
    if args.check:
        data=json.loads((OUT/"independent-review.json").read_bytes())
        for row in data["source_pins"]:
            assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:
            assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(data["source_pins"]),new_decoded_bytes=0,game_process_accessed=False)))
        return
    sources={}
    def fixed(path):
        row=pin(path)
        sources[row["path"]]=row
        return row
    assert fixed(SOURCE/"manifest.json")["sha256"]==MANIFEST
    def children(path):
        for row in json.loads(path.read_bytes())["files"]:
            child=Path(row["absolute_path"]) if "absolute_path" in row else path.parent/row["path"]
            got=fixed(child)
            assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
    children(SOURCE/"manifest.json")
    evidence=json.loads((SOURCE/"findings.json").read_bytes())
    assert len(evidence["source_pins"])==12 and len(evidence["reused_instructions"])==65
    for name,row in evidence["source_pins"].items():
        path=ROOT/name
        got=fixed(path)
        assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
        if path.name=="manifest.json":
            children(path)
    rows,regions,relay={ },[],[]
    def replay(items):
        for old in items:
            r=normalize(old)
            at,raw=int(r["rva"],16),bytes.fromhex(r["bytes"])
            assert pe.bytes_at(at,len(raw))==raw
            if at in rows:
                assert rows[at]["bytes"]==r["bytes"]
            rows[at]=r
    for name in evidence["coverage"]["region_files"]:
        data=json.loads((SOURCE/name).read_bytes())
        for region in data["regions"]:
            at,size=int(region["entry_rva"],16),region["bytes"]
            raw=b"".join(bytes.fromhex(r["bytes"]) for r in region["instructions"])
            assert len(raw)==size and pe.bytes_at(at,size)==raw
            assert hashlib.sha256(raw).hexdigest()==region["raw_sha256"]
            assert pe.function(at)[:2]==(at,at+size)
            pos=at
            for r in region["instructions"]:
                assert int(r["rva"],16)==pos
                pos+=len(bytes.fromhex(r["bytes"]))
            regions.append((at,at+size))
            relay.extend(region["instructions"])
            replay(region["instructions"])
    regions.sort()
    assert regions==[(0x14c25a0,0x14c26bc),(0x14c26bc,0x14c2789),(0x14c2789,0x14c2a4a)]
    assert sum(b-a for a,b in regions)==1194
    relay.sort(key=lambda r:int(r["rva"],16))
    replay(evidence["reused_instructions"])
    r4=json.loads((ROOT/"work/reports/war-peace-api-20261015-r4/war/disassembly.json").read_bytes())
    old={f["entry_rva"]:f["instructions"] for f in r4["functions"]}
    loop=json.loads((ROOT/"work/reports/war-peace-api-20261015-r6-owner-boundary/war/owner-shutdown.json").read_bytes())["regions"][0]["instructions"]
    main_rows=json.loads((ROOT/"work/reports/native-startup-continue-1375.json").read_bytes())["functions"]["0x8757e0"]["instructions"]
    inventories={}
    body_sizes={}
    for name,selected,stop,push_count,allocation in (("wrapper",old["0x10a6d00"],0x10a6d5c,1,0x30),
        ("server",old["0x8137c0"],0x815829,8,0x2e8),("relay",relay,0x14c2815,1,0x70),
        ("main_loop",loop,0x14c2e13,3,0x30)):
        selected=[normalize(r) for r in selected if int(r["rva"],16)<=stop]
        replay(selected)
        writes=[]
        for row in selected:
            op,_,args=row["instruction"].partition(" ")
            if op in ("push","pop","leave","enter") or args.split(",")[0] in ("rsp","esp","sp","spl"):
                writes.append(row)
            assert not (op=="xchg" and any(v.strip() in ("rsp","esp","sp","spl") for v in args.split(",")))
        assert len([r for r in writes if r["instruction"].startswith("push ")])==push_count
        assert writes[-1]["instruction"]=="sub rsp, "+hex(allocation)
        assert len(writes)==push_count+1
        assert writes==evidence["stack_affecting_instruction_inventories"][name]
        inventories[name]=writes
        body_sizes[name]=push_count*8+allocation
    replay(main_rows)
    main_writes=[]
    for old_row in main_rows:
        if int(old_row["rva"],16)>0x8781b4:
            continue
        row=normalize(old_row)
        op,_,args=row["instruction"].partition(" ")
        if op in ("push","pop","leave","enter") or args.split(",")[0] in ("rsp","esp","sp","spl"):
            main_writes.append(row)
    assert all(r["instruction"].startswith(("push ","sub rsp, ")) for r in main_writes)
    def ins(at,expected):
        assert rows[at]["instruction"]==expected
    def relative(at,target):
        raw=bytes.fromhex(rows[at]["bytes"])
        assert raw[0] in (0xe8,0xe9) and at+5+struct.unpack_from("<i",raw,1)[0]==target
    for at,expected in ((0x8781b1,"mov rcx, rbx"),(0x14c2d12,"mov rsi, rcx"),
        (0x14c2e0e,"mov dl, 1"),(0x14c2e10,"mov rcx, rsi"),(0x14c25c3,"mov rdi, rcx"),
        (0x14c2600,"lea rsi, [rdi + 0x40]"),(0x14c27ee,"mov rcx, qword ptr [rsi]"),
        (0x14c280e,"mov rax, qword ptr [rcx]"),(0x14c2811,"movzx edx, r14b"),
        (0x14c2815,"call qword ptr [rax + 0x20]"),(0x14c2839,"lea rbx, [rdi + 0x78]"),
        (0x14c2842,"mov rax, qword ptr [rsi]"),(0x14c2845,"mov qword ptr [rsi], rbp"),
        (0x14c284b,"mov qword ptr [rbx], rax"),(0x14c2890,"lea rcx, [rdi + 0x70]"),
        (0x14c2899,"mov rax, qword ptr [rcx]"),(0x14c289c,"mov qword ptr [rcx], rbp"),
        (0x14c28a2,"mov qword ptr [rsi], rax"),(0x74b91c,"mov rcx, qword ptr [rsi + 0x1e00]"),
        (0x81580f,"mov rax, qword ptr [r13 + 0x330]"),(0x815816,"mov r9, r13"),
        (0x815822,"mov rcx, qword ptr [rax + 0x360]"),(0x10a6d26,"mov rbx, r9"),
        (0x10a6d53,"mov r8, rbx")):
        ins(at,expected)
    relative(0x8781b4,0x14c2d00)
    relative(0x14c2e13,0x14c25a0)
    relative(0x815829,0x10a6d00)
    relative(0x10a6d5c,0x10a6ec0)
    for row in evidence["static_vtable_slots"]:
        raw=bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"],16),8)==raw and hashlib.sha256(raw).hexdigest()==row["sha256"]
        assert struct.unpack("<Q",raw)[0]==pe.base+int(row["target_rva"],16)
    assert struct.unpack("<Q",pe.bytes_at(0x1cb8460+0x20,8))[0]==pe.base+0x8137c0
    Q=0x100008
    wrapper_entry=Q+8+body_sizes["wrapper"]
    server_entry=wrapper_entry+8+body_sizes["server"]
    relay_entry=server_entry+8+body_sizes["relay"]
    loop_entry=relay_entry+8+body_sizes["main_loop"]
    main_rsp=loop_entry+8
    deltas=[0,wrapper_entry-Q,server_entry-Q,relay_entry-Q,loop_entry-Q,main_rsp+0x60-Q]
    assert deltas==[0,0x40,0x370,0x3f0,0x440,0x4a8]
    witness=evidence["guard_design"]["stack_witness"]
    for key in ("observed_runtime","unwind_or_return_address_authentication_implemented","arbitrary_thread_stack_scan_is_authority","lifetime_lease"):
        assert witness[key] is False
    assert evidence["contract"]["native_ready"] is False
    fixed(Path(__file__))
    result=dict(schema="EU4-MAIN-FRAME-INDEPENDENT-REVIEW/1",review_status="conditional_current_app_chain_and_stack_witness_consistent",findings=[],
        target_manifest_sha256=MANIFEST,source_pins=list(sources.values()),original_source_pin_count=12,
        sealed_retained_bytes=1194,pdata_fragments=3,reused_rows=65,
        stack_checks=dict(selected_stack_write_inventories=inventories,main_explicit_stack_changes_before_call=main_writes,
            body_sizes_hex={k:hex(v) for k,v in body_sizes.items()},
            entry_Q_is_symbolic_only=True,return_offsets_hex=[hex(v) for v in deltas[:5]],holder_address_offset_hex=hex(deltas[5]),
            equations=["wrapper_entry=Q+8+0x38=Q+0x40","server_entry=wrapper_entry+8+0x328=Q+0x370",
                "relay_entry=server_entry+8+0x78=Q+0x3f0","loop_entry=relay_entry+8+0x48=Q+0x440",
                "holder_address=loop_entry+8+0x60=Q+0x4a8"]),
        conclusions=["Outer current+0x40 feeds virtual+0x20. Pending+0x70 and previous+0x78 are separate move/cleanup holders, not interchangeable current identities.",
            "Selected server chain requires current pointee=read64(game+0x1e00) with exactvt1cb8460 and slot20=8137c0; game+0x1e00 is the field address, not the pointee.",
            "Main8781b4->loop14c2e13->relay14c2815->typedserver8137c0->815829->wrapper10a6d00->10a6ec0 is conditional static normal control flow.",
            "1194B spans all three contiguous pdata fragments; selected direct branches remain within them. External callees/virtualcallbacks are not recursively closed.",
            "14c2d00 contains a frame loop before cleanup; historical shutdown filename does not establish shutdown-only behavior.",
            "Symbolic stack deltas and holder-address witness are valid for exact prologues/normal ABI, not observed runtime Q/stack/thread, lease, epoch or all-caller proof."],
        unknowns=["Actual callback/register/thread/raw-stack capture, exact caller selection and TLS/exception authority.",
            "Virtual transition callback/reentry, alias retirement, SDL dispatch interval, allocator failures and borrowed header lifetime.",
            "Any native action/no-send execution safety or readiness."],
        native_ready=False,runtime_callback_observed=False,header_lease_proven=False,game_process_accessed=False,native_calls=0,requests_published=0,
        frozen_sources_modified=False,resources=dict(new_decoded_bytes=0,peak_committed_bytes=check_memory_budget(),memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-review.json").open("x",encoding="ascii") as f:json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent main-frame review\n\nThe1194B/3pdata fragments,65 reused rows,12 original pins and sealed dependency children match. Current+0x40 feeds virtual+0x20; pending+0x70/previous+0x78 are distinct move holders. Typed current must equal the pointer read from game+0x1e00, not that field address. The selected normal main-loop->relay->server->R4 chain is consistent under those conditions.\n\nIndependent full selected RSP-write inventories give wrapper/server/relay/loop sizes0x38/0x328/0x78/0x48. With each CALL's8-byte return push, return slots are Q+0,Q+0x40,Q+0x370,Q+0x3f0,Q+0x440; main holder address is Q+0x4a8. Main has only its fixed pushes/sub before the selected call. All values are static symbolic derivations, not captured Q/raw stack/thread.\n\nNo new finding, decode, game access or call. Transition virtualcallbacks, reentry/aliases, exceptions, lifetime/TLS and full-interval dispatch authority remain open. The historical shutdown filename does not make14c2d00 shutdown-only. No current sample or holder witness supplies a lease/native readiness. native_ready=false.\n")
    seal=dict(schema="EU4-MAIN-FRAME-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-review.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-review.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),source_pins=len(sources),new_decode=0,native_ready=False)))


if __name__=="__main__":main()
