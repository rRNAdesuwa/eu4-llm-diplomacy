"""Independent retained-byte review of conditional thread bridge and holder interval."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"work"))
from discover_diplomacy import PE,check_memory_budget
SOURCE=ROOT/"work/reports/war-peace-api-20261015-r6-main-holder/war"
OUT=ROOT/"work/reports/war-peace-api-20261015-r6-main-holder-review"
MANIFEST="91faf848c8ac2e1f3737d07253015608ddb335422b8054c0e66a56c39d39e13c"
GAME="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw=path.read_bytes()
    assert len(raw)<16*1024*1024
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    pe=PE(ROOT.parent/"eu4.exe")
    assert len(pe.data)==38462504 and hashlib.sha256(pe.data).hexdigest()==GAME
    if args.check:
        result=json.loads((OUT/"independent-review.json").read_bytes())
        for row in result["source_pins"]:
            assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:
            assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(result["source_pins"]),new_decoded_bytes=0,game_process_accessed=False)))
        return
    sources={}
    def fixed(path):
        row=pin(path)
        sources[row["path"]]=row
        return row
    assert fixed(SOURCE/"manifest.json")["sha256"]==MANIFEST
    def children(manifest_path):
        count=0
        for row in json.loads(manifest_path.read_bytes())["files"]:
            path=Path(row["absolute_path"]) if "absolute_path" in row else manifest_path.parent/row["path"]
            got=fixed(path)
            assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
            count+=1
        return count
    own_manifest_children=children(SOURCE/"manifest.json")
    data=json.loads((SOURCE/"findings.json").read_bytes())
    assert len(data["source_pins"])==12 and len(data["reused_instructions"])==137
    for name,row in data["source_pins"].items():
        path=ROOT/name
        got=fixed(path)
        assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
        if path.name=="manifest.json":
            children(path)
    rows,regions={},[]
    def replay(items):
        for row in items:
            at,raw=int(row["rva"],16),bytes.fromhex(row["bytes"])
            assert pe.bytes_at(at,len(raw))==raw
            if at in rows:
                assert rows[at]["bytes"]==row["bytes"]
            rows[at]=row
    for name in data["coverage"]["region_files"]:
        doc=json.loads((SOURCE/name).read_bytes())
        for region in doc["regions"]:
            at,size=int(region["entry_rva"],16),region["bytes"]
            raw=b"".join(bytes.fromhex(r["bytes"]) for r in region["instructions"])
            assert len(raw)==size and pe.bytes_at(at,size)==raw
            assert hashlib.sha256(raw).hexdigest()==region["raw_sha256"]
            pos=at
            for row in region["instructions"]:
                assert int(row["rva"],16)==pos
                pos+=len(bytes.fromhex(row["bytes"]))
            regions.append((at,at+size))
            replay(region["instructions"])
    regions.sort()
    assert sum(b-a for a,b in regions)==3719 and all(a[1]<=b[0] for a,b in zip(regions,regions[1:]))
    replay(data["reused_instructions"])
    main_rows=json.loads((ROOT/"work/reports/native-startup-continue-1375.json").read_bytes())["functions"]["0x8757e0"]["instructions"]
    replay(main_rows)
    def ins(at,expected):
        assert rows[at]["instruction"]==expected
    def relative(at,target):
        raw=bytes.fromhex(rows[at]["bytes"])
        assert raw[0] in (0xe8,0xe9) and at+5+struct.unpack_from("<i",raw,1)[0]==target
    def rip(at,target):
        raw=bytes.fromhex(rows[at]["bytes"])
        assert at+len(raw)+struct.unpack_from("<i",raw,len(raw)-4)[0]==target
    uses=[r for r in main_rows if "[rsp + 0x60]" in r["instruction"]]
    assert len(uses)==9 and uses==data["main_holder_literal_uses"]
    interval=[r for r in main_rows if 0x877dad<int(r["rva"],16)<0x878143]
    assert not any(r["instruction"].startswith(("mov qword ptr [rsp + 0x60],","lea ")) and "[rsp + 0x60]" in r["instruction"] for r in interval)
    assert not any(r["instruction"].split(",")[0].split()[-1] in ("rsp","esp","sp","spl") for r in interval)
    for at,expected in ((0x878032,"mov r8, rbx"),(0x878048,"mov rdi, rax"),(0x878083,"mov rcx, rdi"),
        (0x878081,"xor edx, edx"),(0x878412,"jmp 0x878050"),(0x87823d,"mov qword ptr [rsp + 0x60], rsi"),
        (0x1738d44,"mov rbp, rcx"),(0x1738d47,"mov rsi, r8"),(0x1738df7,"mov qword ptr [rax], rbp"),
        (0x1738dfa,"mov qword ptr [rax + 8], rsi"),(0x1738dfe,"mov qword ptr [rax + 0x10], rbx"),
        (0x1761d12,"mov qword ptr [rax], rbx"),(0x1761d30,"mov r9, rax"),
        (0x1a57c67,"mov qword ptr [rbx], rdi"),(0x1a57c6d,"mov qword ptr [rbx + 8], rsi"),
        (0x1a57ba7,"mov rcx, qword ptr [rbx + 8]"),(0x1a57bab,"mov rax, qword ptr [rbx]"),
        (0x1761cae,"mov rbx, qword ptr [rcx]"),(0x1761cb6,"mov rcx, rbx"),
        (0x173921c,"mov rsi, qword ptr [rcx]"),(0x173921f,"mov rbx, qword ptr [rcx + 8]"),
        (0x1739240,"mov rcx, rbx"),(0x1739243,"call rsi"),(0x1739463,"je 0x17394a7"),
        (0x1761dd9,"mov edx, 0xffffffff"),(0x1761dde,"mov rcx, qword ptr [rcx + 8]")):
        ins(at,expected)
    for at,target in ((0x878043,0x17320a0),(0x878086,0x1735c70),(0x87813e,0x14c0be0),
        (0x1738e3b,0x1761ce0),(0x1761d3e,0x1a57c90),(0x1761cb9,0x1739200),
        (0x874068,0x200810),(0x200ab7,0x202490),(0x202691,0x2043a0),
        (0x1739475,0x1761dd0),(0x1739498,0x175da20),(0x8783c8,0x1735400),(0x878402,0x169a2f0)):
        relative(at,target)
    rip(0x87803c,0x874010)
    rip(0x1761d24,0x1761ca0)
    rip(0x1a57bae,0x1b67860)
    bindings=json.loads((SOURCE/"static-bindings.json").read_bytes())
    for row in bindings["static_cells"]+bindings["strings"]:
        raw=bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"],16),len(raw))==raw and hashlib.sha256(raw).hexdigest()==row["sha256"]
    assert [(r["rva"],r["target_rva"]) for r in bindings["static_cells"]]==[
        ("0x1fb0058","0x172e130"),("0x1fb0db8","0x172cb70"),("0x1b67860","0x1a79a30")]
    for at,cell,target in ((0x17321a7,0x1fb0058,0x1738d30),(0x173390f,0x1fb0db8,0x1739460)):
        rip(at,target)
        rip(at+7,cell)
    for at,cell in ((0x17320a0,0x1fb0058),(0x1735c70,0x1fb0db8),(0x172e165,0x1fb0058),(0x172cb95,0x1fb0db8)):
        rip(at,cell)
    assert pe.bytes_at(0x1a79a30,2)==b"\xff\xe0"
    ins(0x1734d9d,"call rbx")
    ins(0x1734d8b,"mov r8d, 0x1148")
    ins(0x1734d98,"mov ecx, 1")
    rip(0x1734d91,0x1fb0000)
    ins(0x1740cce,"xchg dword ptr [rcx], eax")
    def cstring(at):
        raw=pe.bytes_at(at,80)
        assert b"\0" in raw
        return raw.split(b"\0",1)[0].decode("ascii")
    imports=[]
    truncated_names=[]
    for row in bindings["import_sites"]+data["main_import_sites"]:
        at,iat=int(row["instruction_rva"],16),int(row["iat_rva"],16)
        rip(at,iat)
        record=row["import_record"]
        for label in ("descriptor","lookup","name"):
            raw=bytes.fromhex(record[label+"_bytes"])
            assert pe.bytes_at(int(record[label+"_rva"],16),len(raw))==raw
        original,_,_,dll,first=struct.unpack("<IIIII",bytes.fromhex(record["descriptor_bytes"]))
        assert (iat-first)%8==0 and original+iat-first==int(record["lookup_rva"],16)
        name=struct.unpack("<Q",bytes.fromhex(record["lookup_bytes"]))[0]
        assert name==int(record["name_rva"],16)
        assert cstring(dll)==record["dll"] and cstring(name+2)==record["name"]
        if len(bytes.fromhex(record["name_bytes"]))<2+len(record["name"]):
            truncated_names.append(record["name"])
        imports.append(dict(site=row["instruction_rva"],name=record["name"],dll=record["dll"],full_PE_name_checked=True))
    for k in ("native_ready","holder_retention_proves_pointee_alive","holder_is_world_lease",
        "sentinel_header_lifetime_authority_proven","R4_callback_linked_to_worker_or_main_branch",
        "main_thread_quiescent_during_worker","complete_alias_release_exclusion"):
        assert data["contract"][k] is False
    assert data["dispatch_guard_design"]["current_binding_observed"] is False
    fixed(Path(__file__))
    result=dict(schema="EU4-MAIN-HOLDER-INDEPENDENT-REVIEW/1",review_status="conditional_bridge_and_nonlease_boundaries_consistent",findings=[],
        target_manifest_sha256=MANIFEST,source_pins=list(sources.values()),original_source_pin_count=12,
        own_manifest_child_count=own_manifest_children,reused_rows=137,sealed_retained_bytes=3719,
        import_checks=imports,short_original_import_name_bytes_independently_closed_from_fixed_PE=truncated_names,
        conclusions=["Main retains local holder storage across creator/flag/wait and14c0be0 normal sequence, under ordinary ABI and literal-address limitations.",
            "Builtin successful allocations/CreateThread and fixed CFG give raw borrowed outer via record20 ->platform record10 ->CRT record28 ->1761ca0 ->1739200 ->874010.",
            "The bridge stores/passes raw outer; no selected explicit retain protocol establishes pointee lifetime, and hidden callee/alias cleanup is not excluded.",
            "Worker flag zero is earlier than full thread termination. Main event pump/Sleep loop is not a join and may permit untraced callbacks/reentry.",
            "Builtin nonNULL wait calls WaitForSingleObject(handle,INFINITE), then CloseHandle and threadobject cleanup; wait return is unchecked, so successful join requires valid handle and actual OS success.",
            "Creator/wait cells1fb0058/1fb0db8 are dynamic EXE dispatch pointers, not Windows IAT; file values are lazy stubs. Provider override may replace semantics.",
            "Builtin creator writer and local wait writer are exact, but wait provider entry-to-writer reachability/full provider/interval stability are not closed.",
            "CFG1b67860 file target1a79a30 FF E0 is fixed-byte identity, not a runtime interval guarantee or callback thread binding."],
        unknowns=["R4 callback actual thread/receiver and missing descendant2043a0-to-server chain.",
            "Current slot values and full-interval immutability, alternate provider semantics, successful wait and cleanup completion.",
            "Independent pointee/registry/sentinel retirement, alias writes, exceptions and reentry; local holder retention supplies no lease."],
        scope_exclusions=["new run-callback/14c25a0 analysis","new2043a0 descendants","process reads","native execution"],
        native_ready=False,game_process_accessed=False,native_calls=0,requests_published=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,whole_PE_disassembled=False,peak_committed_bytes=check_memory_budget(),memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-review.json").open("x",encoding="ascii") as f:
        json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent main-holder review\n\n"
            "All3719B slices,137 reused rows,12 original source pins and sealed dependency children match. Main's9 literal holder uses and interval contain no explicit holder reset/address escape/RSP rewrite. This is conditional storage retention, not a pointee/header lease or all-alias exclusion. No new finding.\n\n"
            "Builtin successful allocation/CreateThread and fixed CFG trace raw outer through20B/10B/28B records to1739200 and874010. Worker flag clear precedes remaining thread cleanup. Main pumps helpers/Sleep while waiting, and its termination event is not a join. Builtin wait calls OSINFINITE then CloseHandle; unchecked return/NULL object mean actual join requires valid handle, successful wait and active builtin dispatch.\n\n"
            "EXE creator/wait cells are dynamic SDL pointers, initially lazy; provider can override them. Exact creator/local wait writers and static CFGleaf are confirmed, but full provider reachability/current values/interval stability and R4 callback thread/receiver remain unknown. Complete fixed-PE import names are independently checked, including records whose retained name_bytes only included a partial hint. No noCB/native safety promotion, game access, calls, effects or frozen edits. native_ready=false.\n")
    seal=dict(schema="EU4-MAIN-HOLDER-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-review.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:
        json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-review.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),source_pins=len(sources),new_decoded_bytes=0,native_ready=False)))


if __name__=="__main__":
    main()
