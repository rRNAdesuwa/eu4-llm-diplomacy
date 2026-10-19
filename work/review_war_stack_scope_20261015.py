"""Independent fixed-byte stack ABI/reduced-path review, never an executor."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope/war"
OUT = ROOT / "work/reports/war-peace-api-20261015-r8-stack-scope-review"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA and len(pe.data) == 38462504
    if args.check:
        result = json.loads((OUT / "independent-review.json").read_text())
        for row in result["source_pins"]:
            assert pin(ROOT / row["path"]) == row
        print(json.dumps(dict(status="passed", source_pins=len(result["source_pins"]),
            new_decoded_bytes=0, game_process_accessed=False)))
        return
    assert pin(SOURCE / "manifest.json")["sha256"] == "f163c624cd1f06f7826ff9a6e05e4e66f5b35093c05adce2d410c7d646abb78f"
    manifest = json.loads((SOURCE / "manifest.json").read_bytes())
    for row in manifest["files"]:
        assert pin(ROOT / row["path"]) == row
    evidence = json.loads((SOURCE / "evidence.json").read_bytes())
    sources = {r["path"]: r for r in evidence["source_pins"]}
    for row in sources.values():
        assert pin(ROOT / row["path"]) == row
    assert len(sources) == 4 and pe.function(0xb096c0)[:2] == (0xb096c0, 0xb09af0)
    caller = evidence["caller"]
    raw = bytes.fromhex(caller["bytes"])
    assert len(raw) == 1072 and pe.bytes_at(0xb096c0, 1072) == raw
    assert hashlib.sha256(raw).hexdigest() == caller["sha256"]
    assert b"".join(bytes.fromhex(r["bytes"]) for r in caller["instructions"]) == raw
    rows = {r["rva"]: r for r in caller["instructions"]}
    for row in caller["instructions"]:
        blob = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(blob)) == blob
    expected_pushes = [("0xb096ca", "rbp"), ("0xb096cb", "rdi"), ("0xb096cc", "r12"),
        ("0xb096ce", "r14"), ("0xb096d0", "r15")]
    assert [(a, rows[a]["operands"]) for a, _ in expected_pushes] == expected_pushes
    assert all(rows[a]["mnemonic"] == "push" for a, _ in expected_pushes)
    assert rows["0xb096d2"]["operands"] == "rbp, [rsp - 0x30]"
    assert rows["0xb096d7"]["operands"] == "rsp, 0x130"
    for lea, call in (("0xb0994f", "0xb09953"), ("0xb099b3", "0xb099b7"), ("0xb099c3", "0xb099c7")):
        assert rows[lea]["bytes"] == "488d4d90"
        target = 0x500480 if call == "0xb09953" else 0x500560
        blob = bytes.fromhex(rows[call]["bytes"])
        assert blob[0] == 0xe8 and int(call, 16) + 5 + struct.unpack_from("<i", blob, 1)[0] == target
    assert rows["0xb099be"]["operands"] == "0xb09a84" and rows["0xb099cc"]["operands"] == "0xb09a80"
    assert rows["0xb09a84"]["operands"] == "r11, [rsp + 0x130]"
    assert rows["0xb09a94"]["operands"] == "rsp, r11"
    assert [rows[a]["operands"] for a in ("0xb09a97", "0xb09a99", "0xb09a9b", "0xb09a9d", "0xb09a9e")] == [
        "r15", "r14", "r12", "rdi", "rbp"]
    # E is entry RSP; this symbolic arithmetic does not allocate or access stack.
    E = 0x100008
    P = E - 5 * 8
    F, RBP = P - 0x130, P - 0x30
    A = RBP - 0x70
    assert A - F == 0x90 and A + 0x98 - F == 0x128 <= 0x130
    assert E % 16 == 8 and F % 16 == A % 16 == 0
    assert E + 8 == P + 0x30 and E + 0x18 == P + 0x40
    assert F + 0x30 <= A and A + 0x98 == P - 8
    assert rows["0xb09922"]["operands"] == "r15, rax"
    assert rows["0xb09925"]["operands"] == "rax, rax" and rows["0xb09928"]["operands"] == "0xb09ada"
    assert rows["0xb0993b"]["operands"] == "qword ptr [rsp + 0x28], r15"
    assert rows["0xb09940"]["operands"] == "dword ptr [rsp + 0x20], eax"
    assert rows["0xb09944"]["operands"] == "r9b, 1"
    assert rows["0xb09963"]["operands"] == "0x508db0" and rows["0xb09979"]["operands"] == "r8"
    assert not any(r["mnemonic"] == "call" and r["operands"] == "0x500520" for r in caller["instructions"])
    paths = evidence["reused_normal_paths"]
    assert {p["name"] for p in paths} == {"construct", "resolve_NULL_goal", "action_body_destructor", "goal_not_owned", "destroy_empty_vector"}
    direct, indirect, path_rows = set(), set(), {}
    for path in paths:
        for row in path["instructions"]:
            blob = bytes.fromhex(row["bytes"])
            assert pe.bytes_at(int(row["rva"], 16), len(blob)) == blob
            path_rows[row["rva"]] = row
            if row["mnemonic"] == "call":
                (direct if row["operands"].startswith("0x") else indirect).add(row["operands"])
    assert direct == {"0xd9aaf0", "0x8eac0"} and indirect == {"qword ptr [rax + 0x78]"}
    assert struct.unpack("<Q", pe.bytes_at(0x1d207f8 + 0x78, 8))[0] == pe.base + 0x8f450
    assert pe.bytes_at(0x8f450, 3).hex() == "32c0c3"
    assert path_rows["0xd9aafc"]["operands"] == "0xd9b03a"
    assert path_rows["0x50057f"]["operands"] == "0x50059f"
    assert path_rows["0x8eacf"]["operands"] == "0x8eb0f"
    assert "0xd9ab08" not in path_rows and "0x500520" not in path_rows and "0x50b8f0" not in path_rows
    assert path_rows["0x50050a"]["operands"] == "qword ptr [rbx + 0x90], rdi"
    assert evidence["reduced_scope"]["normal_PE_allocator_calls_in_selected_branches"] == 0
    assert evidence["reduced_scope"]["normal_PE_definition_payload_reads_in_selected_branches"] == 0
    assert evidence["reduced_scope"]["header_lifetime_authority_proved"] is False and evidence["native_ready"] is False
    for path in (SOURCE / "manifest.json", SOURCE / "evidence.json", SOURCE / "report.md", Path(__file__)):
        row = pin(path)
        sources[row["path"]] = row
    result = dict(schema="EU4-WAR-R8-STACK-SCOPE-INDEPENDENT-REVIEW/1", review_status="conditional_static_storage_and_path_claims_consistent",
        findings=[], source_pins=list(sources.values()), checked_source_pin_count=len(sources), original_source_pin_count=4,
        original_manifest_sha256=pin(SOURCE / "manifest.json")["sha256"], caller_fixed_bytes_replayed=1072,
        stack_derivation=dict(entry_RSP="E", post_push_RSP="P=E-0x28", saved_register_push_count=5,
            pushed_registers=[r for _, r in expected_pushes], RBP="P-0x30", final_RSP="F=P-0x130",
            action_address="A=RBP-0x70=F+0x90=E-0xc8", action_size="0x98",
            action_span_relative_final_RSP="[0x90,0x128)", local_frame_span="[0,0x130)",
            gap_to_saved_registers="0x8", alignment_assumption="Ordinary Win64 entry E mod16=8",
            final_RSP_mod16=0, action_address_mod16=0,
            outgoing_shadow_space_and_stack_argument_span="F+[0,0x30), disjoint from action",
            ctor_fifth_date_argument="F+0x20 DWORD", ctor_sixth_goal_argument="F+0x28 QWORD",
            highest_constructor_field_write="action+0x90 QWORD, ending+0x98"),
        native_caller=dict(constructor="b0994f RCX=RBP-70; b09953→500480",
            body_destructor_alternate_calls=["b099b3/b099b7", "b099c3/b099c7"],
            these_are_two_normal_exits_not_two_calls_per_action=True, deleting_wrapper_called=False,
            supplied_goal="R15=generated RAX with a nonNULL guard, passed on stack6",
            supplied_stability=True, local_check_call="b09963→508db0",
            temporary_goal_virtual_delete="b09979 callR8 after local check",
            real_caller_matches_proposed_reduced_inputs=False,
            whole_caller_is_allocator_free_or_country_read_free=False,
            runtime_execution_observed=False, exceptional_unwind_cleanup_closed=False),
        reduced_scope=dict(operations=["caller-owned aligned stack constructor(NULL,false)", "one body destructor500560"],
            reused_path_count=5, direct_normal_call_targets=sorted(direct), indirect_call_target="goal.vt+78→8f450",
            clone=False, delete_wrapper=False, local_or_full_check=False, execute_or_send=False,
            action_goal_vector_allocator_calls_in_selected_PE_paths=0,
            definition_payload_reads_in_selected_PE_paths=0, country_world_object_payload_reads_in_selected_PE_paths=0,
            vectors="All three initialized zero by constructor; zero begin makes8eac0 return before heap storage",
            NULL_goal_resolution="d9aaf0 NULL branch reads module slot2340030 only",
            borrowed_goal_last_payload_read="500577 goal+0", borrowed_derived_dispatch="50057a vtable+78",
            body_destroy_does_not_free_stack_action_storage=True),
        remaining_requirements=["The returned sentinel must be nonNULL with a live readable header and exact vtable across its actual read/dispatch interval.",
            "Module slot identity, nonNULL and pre/post equality do not prove borrowed-header lifetime or exclude retirement/rebinding.",
            "Correct Win64 ABI, stack ownership/alignment, host/thread/TLS/type/module authority and exceptional fault policy are not runtime-verified.",
            "The selected path excludes allocators conditionally; a different goal type or nonzero vector header selects different callees.",
            "Static caller-owned storage evidence does not authorize an executor, bypass native checks or complete war declaration effects."],
        proposed_reduced_scope_actually_tested=False, native_ready=False, native_execution_or_test_authorized=False,
        game_process_accessed=False, native_calls=0, requests_published=0, frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0, original_caller_decoded_bytes=1072,
            reused_normal_path_count=5, whole_PE_disassembled=False,
            peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024))
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent-review.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    markdown = OUT / "report.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# Independent R8 stack-storage scope review\n\n"
            "Fixed1072B caller and5 retained normal slices replay correctly. EntryE pushes5 registers: P=E-28, RBP=P-30, finalF=P-130. ActionA=RBP-70=F+90; its98B spanF+[90,128) fits the130B local frame, leaves8B before saved registers and is16-byte aligned when ordinary Win64 entryE mod16=8. Outgoing stack args/shadow space do not overlap it.\n\n"
            "B09953 calls the constructor with this stack address. B099B7 andB099C7 are alternate normal body-destructor exits, not two destructor calls per action; neither calls deleting wrapper500520. The real caller passes a generated nonNULL goal/stability1, calls local508DB0 and virtually deletes its temporary goal. Thus it proves storage/cleanup shape, not a NULL,false,no-check live test or a pure whole caller.\n\n"
            "The separately proposed NULL,false constructor→one body destructor scope has only d9aaf0/8eac0 direct calls plus exact sentinel virtual78→8F450. Constructor clears all3 vectors; NULL resolution reads only module slot; false leaf and zero vector branches have no selected PE allocator, definition or country/world object reads. Stack action storage is not freed by body destructor.\n\n"
            "Borrowed sentinel header is still read at500577 and dispatched at50057A. Header lifetime/type/ABI/host/TLS/exception authority remains unverified; nonNULL/vtable/root equality is insufficient. No new finding in the conditional static claims, new decode, game access, native execution, executor or test authorization. native_ready remains false.\n")
    print(json.dumps(dict(review=pin(output), markdown=pin(markdown), source_pins=len(sources),
        new_decoded_bytes=0, native_ready=False, game_process_accessed=False)))


if __name__ == "__main__":
    main()
