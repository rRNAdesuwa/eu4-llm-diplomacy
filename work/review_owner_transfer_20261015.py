"""Independent file/PE review of bounded rejected outer-owner candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"work"))
from discover_diplomacy import PE,check_memory_budget

SOURCE=ROOT/"work/reports/war-peace-api-20261015-r6-owner-transfer/war"
OUT=ROOT/"work/reports/war-peace-api-20261015-r6-owner-transfer-review"
EXPECTED="97abadb4b9feab944743da6d6278674345ae784d586f1b9c5a3f1e3d45aef57d"
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
        print(json.dumps(dict(status="passed",source_pins=len(result["source_pins"]),findings=len(result["findings"]),
            new_decoded_bytes=0,game_process_accessed=False)))
        return
    sources={}
    def fixed(path):
        row=pin(path)
        sources[row["path"]]=row
        return row
    assert fixed(SOURCE/"manifest.json")["sha256"]==EXPECTED
    manifest=json.loads((SOURCE/"manifest.json").read_bytes())
    for row in manifest["files"]:
        got=fixed(SOURCE/row["path"])
        assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
    data=json.loads((SOURCE/"findings.json").read_bytes())
    assert len(data["source_pins"])==9 and len(data["reused_instructions"])==96
    for name,row in data["source_pins"].items():
        path=ROOT/name
        got=fixed(path)
        assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
        if path.name=="manifest.json":
            for child in json.loads(path.read_bytes())["files"]:
                got=fixed(path.parent/child["path"])
                assert (got["bytes"],got["sha256"])==(child["bytes"],child["sha256"])
    # One reused row cites native-world through the pinned owner-boundary findings.
    prior=json.loads((ROOT/"work/reports/war-peace-api-20261015-r6-owner-boundary/war/findings.json").read_bytes())
    name="work/reports/native-world-epoch-1375.json"
    got=fixed(ROOT/name)
    assert (got["bytes"],got["sha256"])==(prior["source_pins"][name]["bytes"],prior["source_pins"][name]["sha256"])
    rows,regions={},[]
    def replay(items):
        for row in items:
            raw=bytes.fromhex(row["bytes"])
            at=int(row["rva"],16)
            assert pe.bytes_at(at,len(raw))==raw
            if at in rows:
                assert rows[at]["bytes"]==row["bytes"]
            rows[at]=row
    for name in ("disassembly.json","main-cleanup-callback.json"):
        decoded=json.loads((SOURCE/name).read_bytes())
        for region in decoded["regions"]:
            start,size=int(region["entry_rva"],16),region["bytes"]
            assert pe.function(start)[:2]==(start,start+size)
            raw=b"".join(bytes.fromhex(r["bytes"]) for r in region["instructions"])
            assert len(raw)==size and pe.bytes_at(start,size)==raw
            assert hashlib.sha256(raw).hexdigest()==region["raw_sha256"]
            at=start
            for row in region["instructions"]:
                assert int(row["rva"],16)==at
                at+=len(bytes.fromhex(row["bytes"]))
            regions.append((start,start+size))
            replay(region["instructions"])
    regions.sort()
    assert sum(end-start for start,end in regions)==7186
    assert all(a[1]<=b[0] for a,b in zip(regions,regions[1:]))
    replay(data["reused_instructions"])
    startup=json.loads((ROOT/"work/reports/native-startup-continue-1375.json").read_bytes())["functions"]["0x8757e0"]["instructions"]
    replay(startup)
    def ins(at,expected):
        assert rows[at]["instruction"]==expected
    def relative(at,target):
        raw=bytes.fromhex(rows[at]["bytes"])
        assert raw[0] in (0xe8,0xe9) and at+5+struct.unpack_from("<i",raw,1)[0]==target
    def rip(at,target):
        raw=bytes.fromhex(rows[at]["bytes"])
        assert at+len(raw)+struct.unpack_from("<i",raw,len(raw)-4)[0]==target
    ins(0x875803,"xor esi, esi")
    ins(0x877da5,"mov rdx, rax")
    relative(0x877dad,0x878690)
    ins(0x877e28,"mov rbx, qword ptr [rsp + 0x60]")
    ins(0x87823d,"mov qword ptr [rsp + 0x60], rsi")
    relative(0x878292,0x8786d0)
    destinations=[r for r in startup if 0x877e28<int(r["rva"],16)<0x87823d
        and r["instruction"].split(",")[0].split()[-1] in ("rbx","ebx","bx","bl","bh")]
    assert destinations==[]
    ins(0x2003f9,"mov rdi, rcx")
    for at,target in ((0x200666,0x202850),(0x2007c5,0x202850),(0x2007cd,0x202490)):
        relative(at,target)
        ins(at-3,"mov rcx, rdi")
    rip(0x87803c,0x874010)
    ins(0x878032,"mov r8, rbx")
    relative(0x878043,0x17320a0)
    ins(0x87401a,"mov rdi, rcx")
    ins(0x874065,"mov rcx, rdi")
    relative(0x874068,0x200810)
    ins(0x14c0c07,"mov rbx, rcx")
    relative(0x14c2149,0x15057d0)
    ins(0x14c214e,"mov rdi, rax")
    ins(0x14c2197,"lea r8, [rdi + 0x10]")
    relative(0x14c21a5,0x166f2b0)
    ins(0x878220,"mov qword ptr [rsp + 0xe0], rsi")
    ins(0x878228,"lea rdx, [rsp + 0xe0]")
    ins(0x878230,"mov rcx, rbx")
    relative(0x878233,0x20f9d0)
    for at,expected in ((0x20f9d6,"add rcx, 0x370"),(0x20f9e5,"mov rax, qword ptr [rdx]"),
        (0x20f9e8,"mov qword ptr [rdx], 0"),(0x20f9ef,"mov r8, qword ptr [rcx]"),
        (0x20f9f2,"mov qword ptr [rcx], rax"),(0x20f9fa,"mov rax, qword ptr [r8]"),
        (0x20f9fd,"mov edx, 1"),(0x20fa02,"mov rcx, r8"),(0x20fa05,"call qword ptr [rax]")):
        ins(at,expected)
    ins(0x219190,"sub rcx, 0x10")
    relative(0x219194,0x1fee80)
    refs=json.loads((SOURCE/"secondary-candidates.json").read_bytes())
    imports=[]
    def cstring(at,limit=64):
        raw=pe.bytes_at(at,limit)
        assert b"\0" in raw
        return raw.split(b"\0",1)[0].decode("ascii")
    for site in refs["callback_import_sites"]:
        at,iat=int(site["instruction_rva"],16),int(site["iat_rva"],16)
        rip(at,iat)
        record=site["import_record"]
        for label in ("descriptor","lookup","name"):
            raw=bytes.fromhex(record[label+"_bytes"])
            assert pe.bytes_at(int(record[label+"_rva"],16),len(raw))==raw
        descriptor=struct.unpack("<IIIII",bytes.fromhex(record["descriptor_bytes"]))
        original_thunk,_,_,dll_rva,first_thunk=descriptor
        assert (iat-first_thunk)%8==0
        index=(iat-first_thunk)//8
        assert original_thunk+8*index==int(record["lookup_rva"],16)
        name_rva=struct.unpack("<Q",bytes.fromhex(record["lookup_bytes"]))[0]
        assert name_rva==int(record["name_rva"],16) and name_rva<2**31
        assert cstring(dll_rva)==record["dll"]=="steam_api64.dll"
        assert cstring(name_rva+2)==record["name"]
        imports.append(dict(site=site["instruction_rva"],iat=site["iat_rva"],dll=record["dll"],name=record["name"],
            descriptor_and_index_to_lookup_checked=True))
    assert [r["name"] for r in imports]==["SteamInternal_ContextInit","SteamAPI_Shutdown"]
    rip(0x877db2,0x86fbe0)
    relative(0x877db9,0x1a332bc)
    ins(0x86fbf1,"cmp qword ptr [rax], 0")
    ins(0x86fbf5,"je 0x86fc02")
    # Re-run only the exact raw candidate patterns, not any disassembler/xref graph.
    direct,vtrefs,section_hashes=[],[],[]
    pattern=re.compile(rb"(?=([\x48\x4c][\x89\x8b\x8d][\x05\x0d\x15\x1d\x25\x2d\x35\x3d].{4}))",re.S)
    for sec in pe.sections:
        if not sec["flags"]&0x20000000:
            continue
        raw=pe.data[sec["raw"]:sec["raw"]+sec["size"]]
        section_hashes.append(dict(name=sec["name"],rva=hex(sec["rva"]),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        for opcode in (0xe8,0xe9):
            offset=raw.find(bytes([opcode]))
            while offset>=0:
                if offset+5<=len(raw) and sec["rva"]+offset+5+struct.unpack_from("<i",raw,offset+1)[0]==0x219190:
                    direct.append(hex(sec["rva"]+offset))
                offset=raw.find(bytes([opcode]),offset+1)
        for match in pattern.finditer(raw):
            blob=match.group(1)
            at=sec["rva"]+match.start()
            if at+7+struct.unpack_from("<i",blob,3)[0]==0x1c48c80:
                vtrefs.append(hex(at))
    assert section_hashes==refs["sections"]
    assert direct==refs["e8_e9_exact_target_candidates"]==[]
    assert vtrefs==[r["rva"] for r in refs["conventional_REX_MOV_LEA_RIP_vtable_candidates"]]==["0x1fea23","0x1fefcb"]
    needle=struct.pack("<Q",pe.base+0x219190)
    qword_offsets=[]
    at=pe.data.find(needle)
    while at>=0:
        qword_offsets.append(at)
        at=pe.data.find(needle,at+1)
    assert qword_offsets==[int(r["file_offset"],16) for r in refs["preferred_VA_qword_candidates"]]
    assert [pe.to_rva(at) for at in qword_offsets]==[0x1c48c80]
    for at in (0x1fea23,0x1fefcb):
        rip(at,0x1c48c80)
    for key in ("native_ready","owning_recipient_identified","actual_normal_outer_teardown_event_closed",
                "normal_exit_nonnull_outer_delete_proven","return_to_menu_nonnull_outer_delete_proven",
                "definition_reload_nonnull_outer_delete_proven","owner_lifetime_lease_proven"):
        assert data["contract"][key] is False
    fixed(Path(__file__))
    finding=dict(priority="P3",id="receiver_origin_is_not_runtime_alias_disproof",
        source="work/reports/war-peace-api-20261015-r6-owner-transfer/war/findings.json",
        json_pointer="/native_this_binding_findings/5/limitation",line=816,
        quoted_text="The virtual receiver is the child loaded fromouter+370, not outer.",
        evidence="20f9ef loads R8=[outer+370];20fa02 passes that value. No value/type/inequality check establishes [outer+370] != outer.",
        impact="The candidate has no established direct outer receiver, but the wording could be read as proven runtime pointer inequality despite child identity being unknown.",
        recommended_append_only_clarification="Receiver originates in the outer+370 pointer field, not directly from the preserved outer register; it is not established as outer, and runtime self/other aliasing remains unknown.",
        existing_frozen_files_should_remain_unchanged=True,native_ready_impact=False)
    result=dict(schema="EU4-OWNER-TRANSFER-INDEPENDENT-REVIEW/1",review_status="conditional_candidate_exclusions_consistent_with_one_wording_precision_finding",
        target_manifest_sha256=EXPECTED,source_pins=list(sources.values()),original_source_pin_count=9,findings=[finding],
        replay=dict(sealed_retained_bytes=7186,reused_rows=96,exact_pdata_ranges=[dict(start=hex(a),end=hex(b)) for a,b in regions],
            new_decoded_bytes=0,imports=imports,raw_pattern_scan_reexecuted=True,
            raw_exact_E8_E9_incoming_candidates=direct,preferred_VA_qword_RVAs=[hex(pe.to_rva(at)) for at in qword_offsets],
            raw_REX_MOV_LEA_vtable_candidates=vtrefs),
        conclusions=["86fbe0 is a direct Steam ContextInit/conditional Shutdown callback, not an explicit bound outer-destructor path; opaque Steam side effects are not exhaustively excluded.",
            "14c2197 R8=RDI+10 derives from15057d0 return. It is not bound to initial outer this; actual returned-object identity/alias remains unknown.",
            "20fa05 virtual0(1) uses the pointer loaded from outer+370 after the field is replaced from the zero local. It is not an established direct outer-this deletion.",
            "Main holder and RBX continuity are valid under ordinary Win64 nonvolatile ABI, not a recipient ownership proof.",
            "874010 passes incoming RCX to200810, not2003d0. The thread launcher argument bridge, worker body and ownership remain unexpanded in this review.",
            "Zero rawE8/E9 incoming and one exact preferred-VA qword are reproduced bounded encoding negatives, not virtual/computed/encoded/copied alias coverage."],
        unknowns=["Actual owning recipient and normal exit/menu/reload nonempty outer deletion.",
            "Getter-return/outer+370 child identity and possible runtime aliasing, plus callee ownership contracts.",
            "Steam/CRT callbacks, exceptions/reentry, allocator handler behavior and full-interval borrowed lifetime.",
            "All virtual consumers, runtime relocated/copied aliases and reset/load paths."],
        scope_exclusions=["holder/SDL thread bridge","new worker200810 body","new native executor","runtime process observation"],
        native_ready=False,game_process_accessed=False,native_calls=0,requests_published=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,whole_PE_disassembled=False,peak_committed_bytes=check_memory_budget(),
            memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-review.json").open("x",encoding="ascii") as f:
        json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent owner-transfer candidate review\n\n"
            "The7186B exact pdata slices,96 reused rows,9 original source pins and prior owner manifest child files replay correctly. The indirectly cited native-world source is also checked through the pinned owner-boundary findings. Steam import descriptor/IAT index/lookup/name chains independently resolve ContextInit and Shutdown. No new decode.\n\n"
            "Main's holder/RBX chain, Steam callback exclusion, getter-return source at14C2197 and field-loaded receiver at20FA05 are consistent as conditional candidate exclusions. The loading callback passes its incomingRCX to200810; launcher/worker/SDL scope remains unopened. No actual owning recipient or normal exit/menu/reload nonempty outer deletion was established.\n\n"
            "OneP3 wording precision: findings.json line816 says the field-loaded receiver is 'not outer'.20F9EF only establishes its origin as[outer+370], not pointer inequality. Child identity is explicitly unknown, so preserve the file and add a separate clarification: not established as outer; runtime aliasing unknown. The getter-return candidate likewise has no proven identity inequality. This does not change native_ready=false.\n\n"
            "Exact raw pattern scans independently reproduce zeroE8/E9 calls to219190, one preferred-VA qword at1C48C80 and two conventional RIP vtable references. These do not cover virtual/computed/encoded/copied/relocated aliases. No full PE disassembly, game access, native calls, new effects or frozen-source edits. Lifetime, allocator, exception/reentry and reset/load boundaries remain unknown.\n")
    seal=dict(schema="EU4-OWNER-TRANSFER-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-review.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:
        json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-review.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        source_pins=len(sources),findings=1,new_decoded_bytes=0,native_ready=False)))


if __name__=="__main__":
    main()
