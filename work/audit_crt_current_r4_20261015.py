"""File-only selected CRT scalar/loaded-getter replay; never calls the producer."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"work"))
from discover_diplomacy import PE,check_memory_budget
REPORT=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-crt-handler-current-r4.json"
PRODUCER=ROOT/"work/capture_crt_handler_current_20261015.py"
PRIOR=ROOT/"work/reports/war-peace-api-20261015-r8-stack-scope/war/live-80340-current-app-r3.json"
PRIOR_AUDIT=ROOT/"work/reports/war-peace-api-20261015-r8-current-app-r3-review/independent-file-audit.json"
CRT_MANIFEST=ROOT/"work/reports/war-peace-api-20261015-r6-crt/manifest.json"
CRT_EVIDENCE=ROOT/"work/reports/war-peace-api-20261015-r6-crt/evidence.json"
OUT=ROOT/"work/reports/war-peace-api-20261015-r8-crt-current-r4-review"
SHA="4c1e082a3f5357615e112cdd5fc7625fd6bb1d0130dda04762c792cc47d26209"
GAME="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw=path.read_bytes()
    assert len(raw)<16*1024*1024
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def rotate_bit_reference(value,count):
    bits=format(value,"064b")
    return int(bits if count==0 else bits[-count:]+bits[:-count],2)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.check:
        result=json.loads((OUT/"independent-file-audit.json").read_bytes())
        for row in result["source_pins"]:assert pin(ROOT/row["path"])==row
        for row in json.loads((OUT/"manifest.json").read_bytes())["files"]:assert pin(ROOT/row["path"])==row
        print(json.dumps(dict(status="passed",source_pins=len(result["source_pins"]),
            selected_decoded_NULL=True,native_ready=False,new_decode=0,game_process_accessed=False)))
        return
    sources={}
    def fixed(path):
        row=pin(path);sources[row["path"]]=row;return row
    assert fixed(REPORT)["sha256"]==SHA
    assert fixed(PRIOR)["sha256"]=="095cb1a85b215e54bfc99a292782dfe21d687abb7bd7c30888d1fbe00f6210a7"
    assert fixed(PRIOR_AUDIT)["sha256"]=="1502e8b625855b0069c1ed1d5892fa9c426cfd4e4f91f04b1106888c6f5b05ac"
    data=json.loads(REPORT.read_bytes());prior=json.loads(PRIOR.read_bytes());prior_audit=json.loads(PRIOR_AUDIT.read_bytes())
    for row in prior_audit["source_pins"]:assert fixed(ROOT/row["path"])==row
    for doc in (data,prior):
        for key in ("source_pins","observer_source_pins"):
            for name,row in doc[key].items():
                got=fixed(ROOT/name)
                assert (got["bytes"],got["sha256"])==(row["bytes"],row["sha256"])
    assert fixed(CRT_MANIFEST)["sha256"]=="f1d167df036525fbb5b29d613168260cc3776829eacf854df6c1cc8d7809ab8f"
    for row in json.loads(CRT_MANIFEST.read_bytes())["files"]:assert fixed(ROOT/row["path"])==row
    evidence=json.loads(CRT_EVIDENCE.read_bytes())
    for row in evidence["source_pins"]:assert fixed(ROOT/row["path"])==row
    pe=PE(ROOT.parent/"eu4.exe")
    assert len(pe.data)==38462504 and hashlib.sha256(pe.data).hexdigest()==GAME
    getter=evidence["reused_getter"]["instructions"]
    cursor=0x1a639ac
    expected=bytearray()
    for row in getter:
        raw=bytes.fromhex(row["bytes"])
        assert int(row["rva"],16)==cursor and pe.bytes_at(cursor,len(raw))==raw
        expected.extend(raw);cursor+=len(raw)
    assert cursor==0x1a639e0 and len(expected)==52
    rows={int(r["rva"],16):r for r in getter}
    assert rows[0x1a639c1]["operands"]=="ecx, ebx"
    assert rows[0x1a639c3]["operands"]=="ecx, 0x3f"
    assert rows[0x1a639cd]["mnemonic"]=="ror" and rows[0x1a639cd]["operands"]=="rbx, cl"
    for at,target in ((0x1a639ba,0x1fc16b8),(0x1a639c6,0x233d0c8)):
        raw=bytes.fromhex(rows[at]["bytes"])
        assert at+len(raw)+struct.unpack_from("<i",raw,len(raw)-4)[0]==target
    tree=ast.parse(PRODUCER.read_text())
    gate=[n for n in tree.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
        and isinstance(n.value.func,ast.Name) and n.value.func.id=="require"]
    load=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=="spec.loader.exec_module"]
    assert len(load)==1 and len(gate)>=5 and all(n.lineno<load[0].lineno for n in gate)
    assert "095cb1a85b215e54bfc99a292782dfe21d687abb7bd7c30888d1fbe00f6210a7" in ast.unparse(gate[0])
    assert "pin(PRODUCER)" in ast.unparse(gate[1])
    assert "f1d167df036525fbb5b29d613168260cc3776829eacf854df6c1cc8d7809ab8f" in ast.unparse(gate[2])
    assert "pin(CRT_EVIDENCE)" in ast.unparse(gate[3])
    rotate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="ror64")
    canonical=ast.parse("""def ror64(value, count):
    require(type(value) is int and 0 <= value < 1 << 64 and type(count) is int and 0 <= count < 64, 'Invalid rotate scalar')
    return ((value >> count) | (value << ((64-count) & 63))) & ((1 << 64)-1)
""").body[0]
    assert ast.dump(rotate)==ast.dump(canonical)
    assert not any(isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Constant) and n.slice.value=="samples" for n in ast.walk(tree))
    math_cases=0
    for value in (0,1,1<<63,(1<<64)-1,0x0123456789abcdef):
        for count in (0,1,31,32,63):
            arithmetic=((value>>count)|(value<<((64-count)&63)))&((1<<64)-1)
            assert arithmetic==rotate_bit_reference(value,count)
            math_cases+=1
    assert data["two_pass_equal"] is True and len(data["samples"])==2 and data["samples"][0]==data["samples"][1]
    assert data["identity"]["pid"]==80340 and data["identity"]["creation"]=="01dd5c075fcf8c26"
    assert data["identity"]["session"]!=prior["identity"]["session"]
    sample_checks=[]
    for number,sample in enumerate(data["samples"],1):
        assert {k:v for k,v in sample.items() if k!="crt_handler"}==prior["samples"][0]
        crt=sample["crt_handler"]
        assert crt["getter_rva"]=="0x1a639ac" and crt["cookie_rva"]=="0x1fc16b8" and crt["encoded_slot_rva"]=="0x233d0c8"
        loaded=bytes.fromhex(crt["getter_code_hex"])
        assert loaded==bytes(expected) and crt["getter_bytes_match"] is True
        assert hashlib.sha256(loaded).hexdigest()==crt["getter_code_sha256"]
        cookies=[bytes.fromhex(v) for v in crt["cookie_reads_hex"]]
        encoded=[bytes.fromhex(v) for v in crt["encoded_reads_hex"]]
        assert len(cookies)==len(encoded)==2 and all(len(v)==8 for v in cookies+encoded)
        assert cookies[0]==cookies[1] and encoded[0]==encoded[1]
        C,E=struct.unpack("<Q",cookies[0])[0],struct.unpack("<Q",encoded[0])[0]
        count=C&63
        decoded=rotate_bit_reference(C^E,count)
        assert crt["rotation_count"]==count and type(crt["rotation_count"]) is int
        assert crt["decoded_pointer"]==hex(decoded) and crt["decoded_null_in_selected_reads"] is (decoded==0)
        assert decoded==0 and C==E
        for key in ("getter_was_called","CRT_lock_was_held","interval_null_proven","allocator_first_attempt_success_proven","callback_authority_proven"):
            assert crt[key] is False
        sample_checks.append(dict(pass_number=number,common_R3_projection_exactly_equal_and_prior_audit_reused=True,
            getter_52B_matches_loaded_raw_and_fixed_PE=True,cookie_two_reads_equal=True,encoded_two_reads_equal=True,
            formula_matches_reference=True,selected_decoded_NULL=True,strict_unsigned_QWORD_lengths=True,
            raw_variables_remain_only_in_pinned_local_receipt=True,CRT_lock_held=False,interval_NULL_proven=False))
    assert data["rpm_budget"]==dict(calls=2*(104+1+4+18),bytes=2*(1588+52+32+105),largest_read=728)
    assert data["rpm_budget"]==dict(calls=254,bytes=3554,largest_read=728)
    for key in ("native_callback_observed","native_stack_sampled","native_lifetime_authority","native_ready","memory_written","injection_performed","new_API_effect_tested","lifetime_or_interval_guarantee"):
        assert data[key] is False
    for key in ("native_calls","requests_published","hooks_installed","saves_written","reloads"):assert data[key]==0
    fixed(Path(__file__))
    result=dict(schema="EU4-CRT-CURRENT-R4-INDEPENDENT-FILE-AUDIT/1",status="selected_current_NULL_formula_and_getter_bytes_consistent",findings=[],
        report_sha256=SHA,source_pins=list(sources.values()),original_source_pin_count=5,observer_source_pin_count=len(data["observer_source_pins"]),
        reused_R3_audit_sha256="1502e8b625855b0069c1ed1d5892fa9c426cfd4e4f91f04b1106888c6f5b05ac",
        getter_replayed_bytes=52,getter_sha256=hashlib.sha256(expected).hexdigest(),sample_checks=sample_checks,
        source_gate=dict(ordered_gate_lines=[n.lineno for n in gate],load_line=load[0].lineno,
            prior_receipt_then_producer_then_CRT_manifest_then_evidence_then_getter_extent_before_import=True,
            historical_samples_not_consumed=True,producer_not_imported_or_executed_by_auditor=True),
        rotate_review=dict(exact_helper_AST_guard_and_expression_checked=True,type_guard_is_exact_int_not_bool=True,
            unsigned_value_bounds="0 <= value < 2**64",count_bounds="0 <= count < 64",
            rotation_zero_checked=True,independent_bitstring_vs_shift_reference_cases=math_cases,
            malformed_scalar_boundaries_rejected_by_inspected_guard=["bool/float/non-int value or count","value<0 or value>=2**64","count<0 or count>=64"],
            actual_producer_rotate_helper_executed=False),
        two_complete_passes_equal=True,shared_RPM_budget_consistent=data["rpm_budget"],duration_ms_reported=data["duration_ms_including_host_and_source_checks"],
        total_selected_raw_bytes_including_reused_R3=2120,selected_decoded_NULL=True,
        limitations=["Current selected cookie/encoded equality and loaded52B getter evidence support only the sampled decodedNULL; no actual getter/handler invocation or CRT lock.",
            "Repeated non-atomic reads can miss intervening mutation/ABA; neither complete pass equality nor common world roots establishes intervalNULL.",
            "R3 common raw projection is exactly equal to the separately audited bytes and that prior file audit is reused; fresh reader source is inspected, not executed here.",
            "Complete game roots/process identity/PE header/modules/final rechecks lack full raw transcripts and remain pinned-reader assertions.",
            "No allocator first-attempt success, handler absence throughout allocation, callback/thread/rawstack/TLS/lifetime authority or native readiness follows.",
            "Getter lock/unlock callees, CRT startup remainder, exception/reentry and arbitrary setter/alias paths are not expanded or discharged.",
            "Raw cookie/encoded variables are not repeated in user-facing output or this summary; they remain in the pinned local input."],
        interval_NULL_proven=False,native_lifetime_authority=False,native_ready=False,new_API_effects_verified=0,
        game_process_accessed=False,native_calls=0,requests_published=0,saves_written=0,reloads=0,frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0,original_PE_data_read_offline_only=True,peak_committed_bytes=check_memory_budget(),memory_limit_bytes=768*1024*1024,shell_sessions_remaining=0))
    OUT.mkdir(parents=True,exist_ok=False)
    with (OUT/"independent-file-audit.json").open("x",encoding="ascii") as f:json.dump(result,f,indent=2)
    with (OUT/"report.md").open("x",encoding="utf-8") as f:
        f.write("# Independent CRT current R4 file audit\n\nThe exact receipt/source pins and52B getter bytes match the fixed PE/retained CRT evidence. Source gates authenticate R3 receipt/producer, CRT manifest/evidence and contiguous getter extent before import. No producer or native getter/handler was executed by this audit.\n\nBoth full samples are equal; their common R3 byte projection exactly matches the separately audited input. Retained cookie/encoded reads and theROR64 formula independently recompute selected decodedNULL=true. The strict-int unsigned/count bounds and zero-rotation expression are correct;25 bitstring-versus-shift reference cases cover0/1/31/32/63 rotations. Raw variables remain in the pinned local input.\n\nAccounting is127reads/1777B each, hence254/3554B/728Bmax; reported982.089ms includes host/source checks. CRTlock was not held, and equality does not prove intervalNULL, no intervening setters/ABA, allocator first-attempt success, callback authority or lease. Missing full roots/identity/PE/modules/final reread bytes remain pinned-reader assertions. No new decode/game access/native call/send/save/reload/effect/readiness. native_ready=false.\n")
    seal=dict(schema="EU4-CRT-CURRENT-R4-REVIEW-MANIFEST/1",files=[pin(Path(__file__)),pin(OUT/"independent-file-audit.json"),pin(OUT/"report.md")])
    with (OUT/"manifest.json").open("x",encoding="ascii") as f:json.dump(seal,f,indent=2)
    print(json.dumps(dict(review=pin(OUT/"independent-file-audit.json"),markdown=pin(OUT/"report.md"),manifest=pin(OUT/"manifest.json"),
        source_pins=len(sources),selected_decoded_NULL=True,native_ready=False,new_decode=0)))


if __name__=="__main__":main()
