"""Independent review of sealed registry scope, without fresh decoding or game access."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r6-registry-lifetime/war"
OUT = ROOT / "work/reports/war-peace-api-20261015-r6-registry-lifetime-review"
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
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    if args.check:
        result = json.loads((OUT / "independent-review.json").read_text())
        for name, expected in result["source_pins"].items():
            assert pin(ROOT / name) == expected, name
        print(json.dumps(dict(status="passed", source_pins=len(result["source_pins"]),
            new_decoded_bytes=0, game_process_accessed=False)))
        return
    assert pin(SOURCE / "manifest.json")["sha256"] == "2b07deb736d9607915c5065fd075f438af3627314a4471bf5d6e55fa5b3b5ca9"
    manifest = json.loads((SOURCE / "manifest.json").read_bytes())
    findings = json.loads((SOURCE / "findings.json").read_bytes())
    sources = dict(findings["source_pins"])
    assert len(sources) == 8
    for name, expected in sources.items():
        assert pin(ROOT / name) == expected
    for item in manifest["files"]:
        assert pin(SOURCE / item["path"]) == {k: item[k] for k in ("bytes", "sha256")}
    rows, intervals, region_descriptions = {}, [], []
    for name in ("new-decode.json", "owner-getter.json", "teardown.json", "final-narrow.json", "registration.json"):
        value = json.loads((SOURCE / name).read_bytes())
        for region in value["regions"]:
            start = int(region.get("start_rva", region.get("entry_rva")), 16)
            end = start + region["bytes"]
            assert not any(start < b and a < end for a, b in intervals)
            intervals.append((start, end))
            raw = pe.bytes_at(start, region["bytes"])
            assert hashlib.sha256(raw).hexdigest() == region["raw_sha256"]
            cursor = start
            for row in region["instructions"]:
                raw_row = bytes.fromhex(row["bytes"])
                assert int(row["rva"], 16) == cursor and pe.bytes_at(cursor, len(raw_row)) == raw_row
                cursor += len(raw_row)
                rows[row["rva"]] = row
            assert cursor == end
            region_descriptions.append(dict(source=name, start=hex(start), end_exclusive=hex(end), bytes=end - start))
    assert sum(b - a for a, b in intervals) == 7572
    assert len(findings["reused_instructions"]) == 122
    for row in findings["reused_instructions"]:
        blob = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(blob)) == blob
        rows[row["rva"]] = row
    def rip(address):
        blob = bytes.fromhex(rows[address]["bytes"])
        return int(address, 16) + len(blob) + struct.unpack("<i", blob[-4:])[0]
    def edge(address, target):
        blob = bytes.fromhex(rows[address]["bytes"])
        assert blob[0] in (0xe8, 0xe9)
        assert int(address, 16) + len(blob) + struct.unpack_from("<i", blob, 1)[0] == target
    for address, target in (("0x20e143", 0xda48b0), ("0x20e16b", 0xda4950),
            ("0xda4920", 0x488210), ("0x1ff747", 0x488210), ("0x48829f", 0x17394f0),
            ("0xda489c", 0x17394f0), ("0x84937", 0x1a332bc), ("0x1a332c0", 0x1a33280)):
        edge(address, target)
    assert rows["0x20e148"]["instruction"] == "mov rbx, rax"
    assert rows["0x20e168"]["instruction"] == "mov rcx, rbx"
    assert rows["0x1fefdd"]["instruction"] == "xor r12d, r12d"
    assert rip("0x1ff734") == rip("0x1ff73b") == rip("0xda490d") == rip("0xda4914") == 0x242bed0
    assert rip("0xda49e6") == rip("0xda4a10") == rip("0xda4a93") == rip("0xda4aa2") == 0x2340038
    assert rip("0xda4a74") == 0x2340030
    assert rows["0xda4aba"]["instruction"] == "mov qword ptr [rdx], rax"
    assert rows["0xda4abd"]["instruction"] == "add qword ptr [r13 + 0x18], 8"
    assert rows["0xda4ab8"]["instruction"] == "je 0xda4ac4"
    assert rows["0xda4acf"]["instruction"] == "call 0xcc220"
    assert rows["0xda4a9d"]["instruction"] == "call 0x1b3780"
    assert rows["0xda4901"]["instruction"] == "mov qword ptr [rbx + 0x10], rdi"
    assert rows["0xda4905"]["instruction"] == "mov qword ptr [rbx + 0x18], rdi"
    assert rows["0xda4909"]["instruction"] == "mov qword ptr [rbx + 0x20], rdi"
    assert rows["0xda48d6"]["instruction"] == "xor edi, edi"
    assert rows["0x48825b"]["instruction"] == "mov edx, 1" and rows["0x488260"]["instruction"] == "call qword ptr [rax]"
    assert rows["0xda4894"]["instruction"] == "mov edx, 0x4f0"
    assert rows["0x488297"]["instruction"] == "mov edx, 0x28"
    assert rip("0x1b614b0") == 0x242bed0 and rows["0x1b614ba"]["instruction"] == "jne 0x488210"
    for item in findings["static_data"]:
        blob = bytes.fromhex(item["bytes"])
        assert pe.bytes_at(int(item["rva"], 16), len(blob)) == blob
    assert struct.unpack("<Q", pe.bytes_at(0x1c48bf8, 8))[0] == pe.base + 0x1fee80
    assert struct.unpack("<Q", pe.bytes_at(0x1d20ae0, 8))[0] == pe.base + 0xda4840
    assert struct.unpack("<Q", pe.bytes_at(0x1b68568, 8))[0] == pe.base + 0x84930
    # Two already-retained register-flow facts corroborate caller/clear binding.
    r6 = json.loads((ROOT / "work/reports/war-peace-api-20261015-r6/war/reused-functions.json").read_bytes())
    initializer = next(f for f in r6["functions"] if f["entry_rva"] == "0xda4950")
    owner_binding = next(r for r in initializer["instructions"] if r["rva"] == "0xda4972")
    assert owner_binding["mnemonic"] == "mov" and owner_binding["operands"] == "r13, rcx"
    assert pe.bytes_at(0xda4972, len(bytes.fromhex(owner_binding["bytes"]))).hex() == owner_binding["bytes"]
    world = json.loads((ROOT / "work/reports/native-world-epoch-1375.json").read_bytes())
    teardown = world["functions"]["0x1fefa0"]["instructions"]
    r12_destinations = []
    for row in teardown:
        if 0x1fefdd <= int(row["rva"], 16) <= 0x1ff73b:
            if re.match(r"\w+ r12(?:d|w|b)?(?:,|$)", row["instruction"]):
                blob = bytes.fromhex(row["bytes"])
                assert pe.bytes_at(int(row["rva"], 16), len(blob)) == blob
                r12_destinations.append(row)
    assert [r["rva"] for r in r12_destinations] == ["0x1fefdd"]
    candidates = json.loads((SOURCE / "slot-xref-candidates.json").read_bytes())
    direct_writes = []
    for row in candidates["candidates"]:
        blob = bytes.fromhex(row["bytes"])
        opcode = blob[1] if 0x40 <= blob[0] <= 0x4f else blob[0]
        if opcode == 0x89:
            direct_writes.append(dict(site=row["rva"], slot=row["slot_rva"], bytes=row["bytes"]))
    assert {r["site"] for r in direct_writes} == {"0xda49e6", "0xda4a74"}
    # Scope-negative only: the explicit sealed regions and pinned function
    # records do not include these semantic helper bodies.
    helpers = (0x1b3780, 0xcc220, 0x8eb80, 0xda1a00, 0x1a63740, 0x1a637b4)
    assert not any(a <= h < b for h in helpers for a, b in intervals)
    for path in (ROOT / "work/reports/native-world-epoch-1375.json",
            ROOT / "work/reports/native-startup-continue-1375.json"):
        functions = json.loads(path.read_bytes())["functions"]
        assert not {hex(h) for h in helpers} & set(functions)
    assert not {hex(h) for h in helpers} & {f["entry_rva"] for f in r6["functions"]}
    contract = findings["contract"]
    for key in ("native_ready", "owner_lifetime_authority_implemented", "process_lifetime_pointees_proven",
            "startup_only_or_atexit_only_proven", "all_reset_load_registry_preservation_proven"):
        assert contract[key] is False
    assert findings["coverage"]["direct_xref_inventory_exhaustive"] is False
    for item in manifest["files"]:
        path = SOURCE / item["path"]
        sources[path.relative_to(ROOT).as_posix()] = pin(path)
    for path in (SOURCE / "manifest.json", SOURCE / "verification.json", Path(__file__)):
        sources[path.relative_to(ROOT).as_posix()] = pin(path)
    review = dict(schema="EU4-REGISTRY-LIFETIME-INDEPENDENT-REVIEW/1",
        review_status="raw_evidence_valid_with_precise_callee_and_scan_coverage_gaps",
        source_pins=sources, checked_input_pin_count=len(sources), original_source_pin_count=8,
        original_manifest_sha256=pin(SOURCE / "manifest.json")["sha256"],
        original_retained_row_count=122, original_new_decoded_bytes=7572,
        exact_regions_replayed=region_descriptions,
        confirmed=dict(owner_argument="20e143 obtains owner;20e148 saves RBX;20e168 passes RCX;da4972 retains R13",
            registered_argument_slot="da4a93 andda4aa2 read2340038 definition slot, not2340030 sentinel slot",
            spare_capacity_vector_effect="da4aba writes selected definition pointer andda4abd advances end8",
            clear_before_delete="1ff734 reads old242bed0;1ff73b clears viaR12 zero;1ff747 destroys old owner",
            clear_zero_register_assignment="Only1fefdd writesR12 in retained enclosing body through1ff73b; ordinary ABI-preserving callee returns assumed",
            conditional_vector_element_delete="Existing nonNULL vector member getsvirtual0(1) at488260; typedvt1d20ae0 targetda4840 reachesfree4f0 atda489c on normal return",
            owner_free="48829f frees28 after vector/hash cleanup",
            cleanup_callback="1b614b0 reads current242bed0, nonNULL tail-jumps488210 without a direct slot clear",
            registrar_shape="raw1b68568→84930 passes1b614b0 to1a332bc/1a33280; endpoints1a63740/1a637b4 and table consumer remain unclosed"),
        review_findings=[dict(id="REGISTRY-FIRST-APPEND-CALLEE-GAP", kind="proof_precision_gap",
            evidence_sites=["0xda4901", "0xda4905", "0xda4909", "0xda4ab8", "0xda4acf", "0xda4a9d"],
            observation="New owner initializes begin/end/capacity to0; initializer resets end=begin. The first append therefore takes full-capacitycc220, not the direct spare-capacity store.",
            gap="cc220 and1b3780 bodies are absent from this sealed scope and its explicit pinned function records. Actual first append success and hash insertion semantics are inferred from call/arguments, not independently closed here.",
            retained_conclusion="The selected argument comes from definition slot, not sentinel. Deletion of a vector member with the exact definition type is valid conditionally.",
            followup="Qualify helper effects/ownership as conditional or inferred in a new erratum; any callee proof belongs to a separately scoped source-pinned increment. Frozen sources remain unchanged."),
            dict(id="REGISTRY-SCAN-TEST-WORDING", kind="wording_precision", report_line=87,
                evidence_paths=["scan_slots.py:20", "scan_owner.py:18"],
                observation="Implemented patterns use8B/89/8D/80/83/81/C7. TEST85/F6/F7 is not covered.",
                gap="Report and scan_slots.py comment sayCMP/TEST; TEST coverage is wider than implemented.",
                impact="Does not invalidate the retained2 direct publication stores, but must not support any extra negative coverage claim.",
                followup="Correct coverage wording in a separate retained erratum, without changing this sealed version.")],
        additional_retained_conditional_path=dict(sites=["0xda490d", "0xda4914", "0xda491b", "0xda4920"],
            behavior="After the initialNULL test and allocation calls, getter re-reads old242bed0, publishes new owner, then deletes nonNULL old owner through488210.",
            condition="Slot becomes nonNULL between initialNULL read and re-read, e.g. unclosed reentrancy/concurrent mutation. No such runtime event was observed.",
            meaning="The known code contains this conditional reclamation path as well as outer destructor and cleanup callback; none is proven exit-only."),
        stale_alias_inference=dict(strictly_conditional=True, observed_runtime_dangling_pointer=False,
            direct_published_slots=direct_writes, computed_alias_cleanup_excluded=False,
            exact_condition="If registry vector contains that definition and normal deletion reachesfree, and no unclosed alias cleanup/rebinding updates2340038 or sentinel+10, those old references can retain the freed address.",
            sentinel_free_or_leak_proven=False),
        only_startup_or_atexit_inference_overclaim_found=False,
        all_ordinary_reset_load_preservation_or_rebuild_proven=False,
        outer_owner_identity_increment_reviewed=False, registry_runtime_or_alias_search_expanded=False,
        native_ready=False, new_test_authorization=False, game_process_accessed=False,
        native_calls=0, frozen_sources_modified=False,
        resources=dict(new_decoded_bytes=0, whole_PE_disassembled=False,
            original7572B_and122_rows_replayed=True, reused_owner_register_binding_row=True,
            retained_R12_zero_flow_checked=True, peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024))
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent-review.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(review, stream, indent=2)
    markdown = OUT / "report.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# Independent sealed registry-lifetime review\n\n"
            "The original8 source pins,122 reused rows and7572B regions pass exact PE replay. Owner argument flow20E143→DA48B0→DA4950 is correct; registration arguments read definition slot2340038, not sentinel2340030. Outer teardown clears242BED0 before488210; a vector member with exact definition vt1D20AE0 is normally deleted byDA4840/free4F0.\n\n"
            "Two precision gaps remain. A new owner has begin/end/capacity0, so its first append takesCC220 atDA4ACF; that body and hash helper1B3780 are not retained in the sealed scope. Direct spare-capacity storage is proved, while first append/hash success is a callee-semantics inference. Also report line87 saysTEST scanning, but the implemented opcodes8B/89/8D/80/83/81/C7 excludeTEST85/F6/F7. Existing raw evidence is unchanged; qualify these points in separate retained errata.\n\n"
            "An additional already-retained conditional path is visible in the lazy getter: DA490D re-reads the old owner, DA4914 publishes the new owner, and DA4920 deletes a nonNULL old owner. Reaching that path requires a change after the initialNULL read; no runtime reentrancy/concurrency was observed. It must not be mistaken for an exit-only reclamation path.\n\n"
            "The stale2340038/sentinel+10 risk is correctly conditional on no unclosed alias cleanup/rebinding. Neither actual dangling pointers, sentinel deletion/leak, only-startup/atexit lifetime, nor ordinary reset/load preservation/rebuild is established. Registrar/table shape does not close its CRT consumer or endpoints. No outer-owner identity increment, new decode, process access, native execution, source mutation or readiness authorization was performed.\n")
    print(json.dumps(dict(review=pin(output), markdown=pin(markdown), input_pins=len(sources),
        original_source_pins=8, retained_rows=122, original_bytes=7572,
        new_decoded_bytes=0, native_ready=False, game_process_accessed=False)))


if __name__ == "__main__":
    main()
