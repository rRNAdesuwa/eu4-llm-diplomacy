"""Independent fixed-PE review of the sealed reduced normal borrowed graph."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, make_disassembler, check_memory_budget

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r6-borrowed/war"
OUT = ROOT / "work/reports/war-peace-api-20261015-r6-borrowed-review"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def pin(path):
    raw = path.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA and len(pe.data) == 38462504
    if args.check:
        report = json.loads((OUT / "independent-review.json").read_text())
        for relative, expected in report["source_pins"].items():
            assert pin(ROOT / relative) == expected, relative
        print(json.dumps(dict(status="passed", input_source_pins=len(report["source_pins"]),
            new_decoded_bytes=0, game_process_accessed=False)))
        return
    assert pin(SOURCE / "manifest.json")["sha256"] == "a68f1bb7c66ffc68159cfdaa0355a113b4262552a15a36d63f3d17a8d1e340bb"
    manifest = json.loads((SOURCE / "manifest.json").read_bytes())
    for row in manifest["files"]:
        assert pin(SOURCE / row["path"]) == {k: row[k] for k in ("bytes", "sha256")}
    table = json.loads((SOURCE / "access-table.json").read_bytes())
    assert pin(SOURCE / "access-table.json")["sha256"] == "dd2a63ef6f8e142113dd5c1c5dff9fa6e971a86bfbe1220784d119f71ef202a5"
    sources = dict(table["source_pins"])
    assert len(sources) == 32
    for relative, expected in sources.items():
        assert pin(ROOT / relative) == expected, relative
    assert len(table["paths"]) == 17 and len(table["explicit_memory_operands"]) == 93
    assert table["boundary"]["native_ready"] is False and table["boundary"]["runtime_verified"] is False
    assert table["scope"]["goal_argument"] is None and table["scope"]["stability"] is False
    assert table["scope"]["execute"] is table["scope"]["checks"] is table["scope"]["send"] is False
    md, cs = make_disassembler(ROOT / "work/deps/capstone-5.0.7")
    assert cs.__version__ == "5.0.7"
    paths = {p["name"]: p for p in table["paths"]}
    entries = {int(p["entry_rva"], 16) for p in table["paths"]}
    actual_memory, direct_edges, indirect_edges, retained_rvas = [], [], [], {}
    for name, path in paths.items():
        # This only replays exact previously retained rows. No fresh range,
        # caller, callee or whole-image disassembly is performed.
        for row in path["instructions"]:
            rva, raw = int(row["rva"], 16), bytes.fromhex(row["bytes"])
            assert pe.bytes_at(rva, len(raw)) == raw
            ins = list(md.disasm(raw, rva))
            assert len(ins) == 1 and ins[0].size == len(raw)
            ins = ins[0]
            assert (ins.mnemonic, ins.op_str) == (row["mnemonic"], row["operands"])
            retained_rvas[rva] = raw
            memory = any(o.type == cs.x86.X86_OP_MEM for o in ins.operands)
            if memory and ins.mnemonic not in ("lea", "nop"):
                actual_memory.append((name, row["rva"]))
            assert ins.mnemonic not in ("rep movsb", "rep movsq", "rep stosb", "rep stosq", "lodsq", "cmpsq")
            if ins.mnemonic == "call" or ins.mnemonic == "jmp":
                op = ins.operands[0]
                if op.type == cs.x86.X86_OP_IMM and ins.mnemonic == "call":
                    assert op.imm in entries, (name, row, hex(op.imm))
                    direct_edges.append(dict(path=name, callsite=row["rva"], target_rva=hex(op.imm)))
                elif op.type != cs.x86.X86_OP_IMM:
                    indirect_edges.append(dict(path=name, site=row["rva"], instruction=ins.mnemonic + " " + ins.op_str))
        # Region endpoints are inclusive instruction starts in the producer.
        # Ensure none of those selected blocks silently skips a middle row.
        for lo, hi in path["regions"]:
            chosen = [r for r in path["instructions"] if int(lo, 16) <= int(r["rva"], 16) <= int(hi, 16)]
            assert int(chosen[0]["rva"], 16) == int(lo, 16)
            assert int(chosen[-1]["rva"], 16) == int(hi, 16)
            assert all(int(a["rva"], 16) + len(bytes.fromhex(a["bytes"])) == int(b["rva"], 16)
                for a, b in zip(chosen, chosen[1:]))
    assert actual_memory == [(r["operation"], r["rva"]) for r in table["explicit_memory_operands"]]
    assert {r["site"] for r in indirect_edges} == {"0xd9ab05", "0xd9ab26", "0x50057a", "0x1a683ba", "0x1a68352"}
    actual_sites = {r["rva"] for r in table["explicit_memory_operands"]
        if r["classification"] in ("borrowed_goal_heap", "borrowed_goal_definition_heap")}
    assert actual_sites == set(table["borrowed_object_dereference_sites"]) == {
        "0xd9ab02", "0x9b120", "0xd9ab08", "0x500577"}
    assert set(table["borrowed_derived_dispatch_sites"]) == {"0xd9ab05", "0x50057a"}
    assert struct.unpack("<Q", pe.bytes_at(0x1d207f8 + 0x58, 8))[0] == pe.base + 0x9b120
    assert struct.unpack("<Q", pe.bytes_at(0x1d207f8 + 0x78, 8))[0] == pe.base + 0x8f450
    assert pe.bytes_at(0x9b120, 5).hex() == "488b4110c3"
    assert pe.bytes_at(0x8f450, 3).hex() == "32c0c3"
    assert struct.unpack("<I", pe.bytes_at(0xd9b048 + 12 * 4, 4))[0] == 0xd9b03a
    # Replay exact branch encodings and the minimal symbolic conditions that
    # select them. These are assumptions of a static path, never live facts.
    branch_witnesses = [
        ("0xd9aafc", "0f8438050000", "constructor argument RCX==0", "taken to d9b03a"),
        ("0xd9aafc", "0f8438050000", "clone source goal RCX!=0", "not taken; source goal vtable read"),
        ("0xd9ab0f", "0f8725050000", "source definition enum==12", "unsigned JA not taken; switch[12] selects d9b03a"),
        ("0x14417e", "7457", "source embedded vector begin==end==0", "taken to1441d7; no element/allocation read"),
        ("0x500537", "740d", "deleting flag bit0==1", "not taken; free owned98"),
        ("0x50057f", "741e", "fixed sentinel virtual78 returns AL0", "taken to50059f; goal-delete branch skipped"),
        ("0x8eacf", "743e", "embedded vector begin==0", "taken to8eb0f; no vector heap access"),
        ("0x1a332f6", "74e7", "malloc attempt returns nonNULL", "not taken; outer new-handler branch skipped"),
        ("0x1a68389", "773c", "allocation size0x98", "oversize branch not taken"),
        ("0x1a683c3", "74d4", "selected HeapAlloc attempt returns nonNULL", "failure branch not taken"),
        ("0x1a6833f", "7437", "owned action pointer nonNULL", "not taken; HeapFree called"),
        ("0x1a6835a", "7517", "HeapFree returns nonzero", "taken to1a68373; error/PTD branch skipped")]
    for address, expected, _, _ in branch_witnesses:
        assert pe.bytes_at(int(address, 16), len(bytes.fromhex(expected))).hex() == expected
    manual = json.loads((ROOT / "work/reports/war-peace-api-20261015-r6/war/manual-boundary.json").read_bytes())
    import_bindings = []
    for item in manual["iat_sites"]:
        if item["name"] not in ("HeapAlloc", "HeapFree"):
            continue
        for rva_key, bytes_key in (("rva", "bytes"), ("descriptor_rva", "descriptor_bytes"),
                ("lookup_rva", "lookup_bytes"), ("name_rva", "name_bytes")):
            raw = bytes.fromhex(item[bytes_key])
            assert pe.bytes_at(int(item[rva_key], 16), len(raw)) == raw
        descriptor = struct.unpack("<5I", bytes.fromhex(item["descriptor_bytes"]))
        assert int(item["lookup_rva"], 16) - descriptor[0] == int(item["iat_rva"], 16) - descriptor[4]
        assert struct.unpack("<Q", bytes.fromhex(item["lookup_bytes"]))[0] == int(item["name_rva"], 16)
        assert bytes.fromhex(item["name_bytes"])[2:] == item["name"].encode("ascii")
        import_bindings.append(dict(site=item["rva"], IAT=item["iat_rva"], dll=item["dll"], name=item["name"],
            PE_import_metadata_replayed=True, OS_implementation_closed=False))
    assert len(import_bindings) == 2
    # Origin rows support heap allocation, not execution of the initializer.
    for row in table["allocation_origin_evidence_not_executed"]:
        raw = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw
    for item in table["module_storage"]:
        rva = int(item["rva"], 16)
        section = next(s for s in pe.sections if s["rva"] <= rva < s["rva"] + max(s["size"], s["virtual_size"]))
        assert item["section"] == section["name"] and item["section_flags"] == hex(section["flags"])
        assert item["file_backed"] is (rva - section["rva"] < section["size"])
        assert item["pointer_pointee_static_lifetime_proven"] is False
    assert all(x["file_backed"] is False for x in table["module_storage"]
        if x["rva"] in ("0x2340030", "0x2340038"))
    for path in (SOURCE / "manifest.json", SOURCE / "access-table.json", SOURCE / "produce.py",
            SOURCE / "report.md", SOURCE / "verification.json", Path(__file__)):
        sources[path.relative_to(ROOT).as_posix()] = pin(path)
    result = dict(schema="EU4-WAR-R6-BORROWED-INDEPENDENT-REVIEW/1", review_status="conditional_static_claims_consistent",
        findings=[], source_pins=sources, checked_input_pin_count=len(sources), original_source_pin_count=32,
        target_game_sha256=SHA, normal_path_slices=17, explicit_memory_operand_rows=93,
        classifications=dict(Counter(x["classification"] for x in table["explicit_memory_operands"])),
        branch_witnesses=[dict(site=a, bytes=b, assumption=c, selected_path=d, runtime_verified=False)
            for a, b, c, d in branch_witnesses],
        selected_normal_direct_call_edges=direct_edges, selected_indirect_edges=indirect_edges,
        selected_normal_PE_callees_unaccounted=[], import_boundaries=import_bindings,
        borrowed_sites=dict(payload=["0xd9ab02", "0x9b120", "0xd9ab08", "0x500577"],
            module_vtable_dispatch=["0xd9ab05", "0x50057a"],
            definition_last_payload_read="0xd9ab08", each_action_goal_last_payload_read="0x500577",
            each_action_goal_last_derived_dispatch="0x50057a",
            virtual58_target="0x9b120 reads goal+10", virtual78_target="0x8f450 returns false without goal payload read"),
        implicit_access_review=dict(string_memory_operations_present=False,
            call_ret_push_pop_scope="Only current ABI stack in the selected instructions",
            handle_fields="Copied scalars in owned action storage; no country lookup or country object access on selected normal PE paths",
            empty_vector_helpers="Three copy invocations and three destructor invocations per action; selected zero headers avoid vector heap storage",
            memory_count_is_dynamic_execution_count=False),
        path_preconditions_not_runtime_proven=["Constructor goal argument NULL and stability false with correct ABI stack arguments.",
            "Source/clone are complete, distinct owned98 allocations; source storage allocation is an external R6 precondition, not added by the17 path slices.",
            "All three source/clone vector triples remain zero through selected helper calls.",
            "Every goal header remains valid with exact sentinel vtable; source goal definition remains readable with enum12.",
            "No allocator failure/recovery/new-handler callback or exceptional unwind occurs along the selected normal traces.",
            "Current module slots may differ between constructor and clone; no pointee-generation or lifetime authority follows from their module addresses."],
        concrete_risks=[dict(id="ALLOCATOR-SUCCESS-IS-NOT-NO-CALLBACK-PROOF",
            sites=["0x1a683c3", "0x1a332f6"],
            risk="A final nonNULL malloc/clone return alone cannot prove the represented handler-free path: malloc can first fail, invoke the dynamic handler and retry successfully.",
            disposition="Already preserved by the report's normal-only assumptions and explicit CRT failure boundaries; no new readiness granted."),
            dict(id="STATIC-SITE-COUNT-NOT-DYNAMIC-COUNT", sites=["0x50b995", "0x50b9a3", "0x50b9b7", "0x500577"],
                risk="93 counts memory rows in17 retained path slices. Shared helpers execute repeatedly; two destructors have separate last-use events even at identical RVAs.",
                disposition="Treat as bounded static inventory, never a runtime call/read count."),
            dict(id="BORROWED-HEADER-AND-DEFINITION-AUTHORITY", sites=["0xd9ab02", "0x9b120", "0xd9ab08", "0x500577", "0x50057a"],
                risk="The exact reads require live borrowed goal/definition objects. Fixed module slots/vtables and same-frame roots do not establish that authority.",
                disposition="Explicitly retained; registry publication/teardown question was not reopened in this review."),
            dict(id="FIRST-ALLOCATION-AND-ERROR-BOUNDARIES", sites=["0x500480", "0x1a68352"],
                risk="Source owned98 allocator compatibility and OS HeapAlloc/HeapFree, failure/PTD/error/unwind behavior remain external prerequisites.",
                disposition="Normal branch closure does not cover these cases or cleanup after lost authority.")],
        module_slot_misidentified_as_pointee_lifetime=False, registry_lifecycle_analysis_repeated=False,
        native_ready=False, native_execution_authorized=False, new_test_authorization_granted=False,
        game_process_accessed=False, native_calls=0, memory_written=False,
        resources=dict(new_decoded_bytes=0, additional_decode_budget_bytes=2048,
            replayed_unique_retained_instruction_bytes=sum(map(len, retained_rvas.values())),
            original_producer_new_decode_bytes=61, whole_PE_disassembled=False,
            peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024))
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent-review.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    markdown = OUT / "report.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# Independent borrowed-access review\n\n"
            "The sealed conditional static claims are consistent. Original32 pins and all sealed files match;17 normal slices and93 explicit memory rows replay against fixed PE bytes. No selected normal PE callee is omitted. The4 payload sites and2 module-vtable dispatch sites are exact: definition last readD9AB08; each action's goal last payload read500577 and last derived dispatch50057A.\n\n"
            "NULL and enum12 goal resolution, zero vector branches, false virtual78 and successful HeapAlloc/HeapFree branches match retained encodings. Virtual58→9B120 reads goal+10; virtual78→8F450 reads no goal payload. Actor/target handles are scalar copies; implicit CALL/RET/PUSH/POP touch the current ABI stack. No additional country/world payload traversal appears in these selected normal paths.\n\n"
            "The qualifications matter:93 is a static inventory, not a dynamic read count; source/clone destructors have separate last-use events. Final nonNULL allocation alone cannot exclude an earlier handler/retry. Source owned98 allocation compatibility, borrowed header/definition authority, OS/error/PTD and C++/SEH unwind remain prerequisites. The module.data slots are correctly distinguished from allocated heap pointees; no lifetime or epoch proof follows from slot identity.\n\n"
            "No new blocking defect was found within the stated conditional graph, and no runtime path selection was observed. The independent review newly decoded0B, reused only retained row bytes and left all frozen sources untouched. It did not reopen registry lifecycle analysis, access the game, allocate game objects, execute native functions or authorize tests/native_ready.\n")
    print(json.dumps(dict(review=pin(output), markdown=pin(markdown), input_pins=len(sources),
        path_slices=17, memory_rows=93, new_decoded_bytes=0, native_ready=False, game_process_accessed=False)))


if __name__ == "__main__":
    main()
