"""Independent CRT startup/store/decode review of the sealed848B evidence only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget
from trace_crt_new_handler_20261015 import scan

SOURCE = ROOT / "work/reports/war-peace-api-20261015-r6-crt"
OUT = ROOT / "work/reports/war-peace-api-20261015-r6-crt-review"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
MASK = (1 << 64) - 1


def pin(path):
    raw = path.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def ror64(value, count):
    count &= 63
    return ((value >> count) | (value << ((64 - count) & 63))) & MASK


def decode(cookie_at_getter, encoded_at_getter):
    return ror64(cookie_at_getter ^ encoded_at_getter, cookie_at_getter & 63)


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
    assert pin(SOURCE / "manifest.json")["sha256"] == "f1d167df036525fbb5b29d613168260cc3776829eacf854df6c1cc8d7809ab8f"
    manifest = json.loads((SOURCE / "manifest.json").read_bytes())
    for item in manifest["files"]:
        assert pin(ROOT / item["path"]) == item
    evidence = json.loads((SOURCE / "evidence.json").read_bytes())
    assert pin(SOURCE / "evidence.json")["sha256"] == "7b7cfa87ecd29999b98a1e9910dbae5e8208b88983f5cca589e7d2b724b82b6b"
    for row in evidence["source_pins"]:
        assert pin(ROOT / row["path"]) == row
    rows = {}
    total = 0
    for function in evidence["functions"]:
        raw = bytes.fromhex(function["bytes"])
        assert pe.bytes_at(int(function["entry_rva"], 16), len(raw)) == raw
        assert hashlib.sha256(raw).hexdigest() == function["sha256"]
        assert b"".join(bytes.fromhex(i["bytes"]) for i in function["instructions"]) == raw
        rows.update({i["rva"]: i for i in function["instructions"]})
        total += len(raw)
    assert total == evidence["new_unique_decoded_bytes"] == 848
    for row in evidence["reused_getter"]["instructions"]:
        raw = bytes.fromhex(row["bytes"])
        assert pe.bytes_at(int(row["rva"], 16), len(raw)) == raw
        rows[row["rva"]] = row
    nt = struct.unpack_from("<I", pe.data, 0x3c)[0]
    assert struct.unpack_from("<I", pe.data, nt + 24 + 16)[0] == 0x1a337c8
    for address, target in (("0x1a337cc", 0x1a34018), ("0x1a337d5", 0x1a33654),
            ("0x1a33663", 0x1a330c0), ("0x1a330ef", 0x1a63928),
            ("0x1a63936", 0x1a72ebc), ("0x1a6385c", 0x1a63974)):
        raw = bytes.fromhex(rows[address]["bytes"])
        assert raw[0] in (0xe8, 0xe9) and int(address, 16) + 5 + struct.unpack_from("<i", raw, 1)[0] == target
    def rip_target(address):
        raw = bytes.fromhex(rows[address]["bytes"])
        return int(address, 16) + len(raw) + struct.unpack("<i", raw[-4:])[0]
    assert rip_target("0x1a6384a") == rip_target("0x1a639ba") == rip_target("0x1a340a8") == 0x1fc16b8
    assert rip_target("0x1a63974") == rip_target("0x1a639c6") == 0x233d0c8
    assert rows["0x1a6384a"]["operands"].startswith("rbx,")
    assert rows["0x1a63851"]["bytes"] == rows["0x1a63859"]["bytes"] == "488bcb"
    assert rows["0x1a63974"]["bytes"] == "48890d4d978d00" and rows["0x1a6397b"]["bytes"] == "c3"
    assert rows["0x1a639c1"]["bytes"] == "8bcb" and rows["0x1a639c3"]["bytes"] == "83e13f"
    assert rows["0x1a639c6"]["bytes"] == "48331dfb968d00" and rows["0x1a639cd"]["bytes"] == "48d3cb"
    table = evidence["initializer_pairs"]
    raw_table = bytes.fromhex(table["bytes"])
    assert pe.bytes_at(0x1c29de0, 256) == raw_table and hashlib.sha256(raw_table).hexdigest() == table["sha256"]
    pairs = [struct.unpack_from("<QQ", raw_table, offset) for offset in range(0, 256, 16)]
    assert pairs[0] == (pe.base + 0x1a637fc, 0) and pairs[1] == (pe.base + 0x1a63844, 0)
    assert rip_target("0x1a63928") == 0x1c29ee0 and rip_target("0x1a6392f") == 0x1c29de0
    guard = evidence["guard_dispatch"]
    assert pe.bytes_at(0x1b67860, 8).hex() == guard["bytes"]
    assert struct.unpack("<Q", bytes.fromhex(guard["bytes"]))[0] == pe.base + 0x1a79a30
    assert pe.bytes_at(0x1a79a30, 2).hex() == guard["target_bytes"] == "ffe0"
    assert scan(pe) == evidence["scan"]
    # A lookahead independently checks overlapping byte candidates as well.
    # Suffix matches inside retained REX instructions are not new boundaries.
    pattern = re.compile(rb"(?=([\x40-\x4f]?[\x8b\x89\x8d\x33\x31\x87]"
        rb"[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....))", re.S)
    overlapping = []
    for section in pe.sections:
        if not section["flags"] & 0x20000000:
            continue
        for match in pattern.finditer(pe.data, section["raw"], section["raw"] + section["size"]):
            raw = match.group(1)
            rva = pe.to_rva(match.start())
            target = rva + len(raw) + struct.unpack("<i", raw[-4:])[0]
            opcode = raw[1] if 0x40 <= raw[0] <= 0x4f else raw[0]
            if target == 0x233d0c8 or (target == 0x1fc16b8 and opcode in (0x89, 0x87)):
                overlapping.append(dict(rva=hex(rva), target_rva=hex(target), bytes=raw.hex(),
                    retained_instruction_boundary=hex(rva) in rows))
    assert len(overlapping) == 6
    aligned = [r for r in overlapping if r["retained_instruction_boundary"]]
    assert {r["rva"] for r in aligned} == {"0x1a340a8", "0x1a63974", "0x1a639c6"}
    assert {r["rva"] for r in overlapping if not r["retained_instruction_boundary"]} == {
        "0x1a340a9", "0x1a63975", "0x1a639c7"}
    for row in aligned:
        assert rows[row["rva"]]["bytes"] == row["bytes"]
    cases = []
    for cookie in (0, 1, 2, 63, 64, 0x2b992ddfa232, MASK):
        value = decode(cookie, cookie)
        assert value == 0
        cases.append(dict(cookie_capture_C0=hex(cookie), cookie_getter_C=hex(cookie),
            encoded_E=hex(cookie), decoded=hex(value), native_executed=False))
    changed = decode(2, 1)
    assert changed == 0xc000000000000000
    cases.append(dict(cookie_capture_C0="0x1", cookie_changed_before_store_C="0x2", encoded_E="0x1",
        cookie_after_store_unchanged=True, decoded=hex(changed), decoded_NULL=False,
        native_executed=False, conclusion="Cookie stability only after store is insufficient."))
    sources = {r["path"]: r for r in evidence["source_pins"]}
    for path in (SOURCE / "manifest.json", SOURCE / "evidence.json", SOURCE / "disassembly.txt", Path(__file__)):
        row = pin(path)
        sources[row["path"]] = row
    result = dict(schema="EU4-CRT-HANDLER-STARTUP-INDEPENDENT-REVIEW/1", review_status="static_evidence_consistent_conditional_decode_only",
        source_pins=list(sources.values()), source_pin_count=len(sources), original_source_pin_count=5,
        original_manifest_sha256=pin(SOURCE / "manifest.json")["sha256"],
        original_848B_evidence_valid=True, additional_conclusions_files_reviewed=False,
        startup_chain=dict(PE_entrypoint="0x1a337c8", cookie_call="0x1a337cc -> 0x1a34018",
            CRT_tail="0x1a337d5 -> 0x1a33654", CRT_initialize="0x1a33663 -> 0x1a330c0",
            conditional_pair_helper="0x1a330ef -> 0x1a63928 -> 0x1a72ebc",
            pair_table="0x1c29de0..0x1c29ee0 / stride16", selected_pair_ordinal_zero_based=1,
            prior_pair_initializer="0x1a637fc", prior_pair_success_required=True,
            selected_pair="0x1c29df0: init1a63844/uninitNULL",
            cookie_capture_site="0x1a6384a: RBX=C0 from1fc16b8",
            untraced_call_between_capture_and_store="0x1a63854 -> 0x1a41b94",
            setter_call="0x1a63859 RCX=RBX; 0x1a6385c -> 0x1a63974",
            leaf_store="0x1a63974: encoded233d0c8=RCX=C0; RET1a6397b",
            after_store_untraced_calls=["0x1a63864 -> 0x1a57eb8", "0x1a6386c -> 0x1a63a10", "0x1a63874 -> 0x1a4753c"],
            normal_ABI_callee_preserves_RBX_assumed=True, whole_CRT_initializer_side_effects_closed=False),
        decode=dict(getter_rva="0x1a639ac", cookie_read="0x1a639ba -> 1fc16b8",
            encoded_read="0x1a639c6 -> 233d0c8", rotation="0x1a639cd ROR64",
            formula="decoded=ROR64(C_getter XOR E_getter, C_getter &63)",
            necessary_and_sufficient_NULL_condition="E_getter==C_getter",
            startup_store_condition="If E still equals captured C0, decodedNULL iff getter cookie C==C0.",
            precision_requirement="For the simple unchanged-state explanation, cookie stability must start at1a6384a capture, not only after1a63974 store.",
            math_reason="Rotation is a bijection and preserves zero for every masked count.",
            pure_math_cases=cases),
        candidate_scan=dict(original_rip_candidates=evidence["scan"]["rip_candidates"],
            three_candidates_promoted_to_retained_instruction_boundaries=True,
            overlapping_same_form_byte_candidates=overlapping,
            actual_handler_references=2, actual_cookie_write=1,
            E8_and_preferred_VA_candidate_scan_replayed=True,
            setter_alias_or_other_addressing_form_exclusion_proven=False,
            limitation="Conventional byte-pattern scan, not full dataflow/alias or runtime-modified-code coverage."),
        findings=[dict(id="COOKIE-CAPTURE-PRECEDES-UNTRACED-CALL", severity="precision_requirement",
            site="0x1a6384a..0x1a6385c", evidence="Cookie is captured in RBX before untraced1a41b94, then captured RBX is stored.",
            risk="A statement requiring only post-store cookie stability is insufficient. C0=1, cookie becomes2 before store, E remains1: decoded isC000000000000000, notNULL.",
            disposition="Original848B bytes are correct. Correct any prose inference in a separate retained corrigendum; do not mutate the frozen evidence or decode another callee.")],
        residual_unknowns=["Successful execution through preceding CRT setup and the first initializer is not observed.",
            "Untraced1a41b94 can affect globals before the encoded store; subsequent calls and initializer pairs have unclosed side effects.",
            "Traditional RIP candidates do not exclude aliased, indirect, absolute, bulk or differently encoded stores.",
            "DecodedNULL at a getter read is not a lifetime lease or current/call-interval setter/reentrancy exclusion.",
            "Current process cookie, encoded slot, decoded handler and subsequent mutations were not read."],
        runtime_handler_NULL_proven=False, whole_startup_postcondition_handler_NULL_unconditionally_proven=False,
        native_ready=False, new_native_test_authorization=False, game_process_accessed=False, native_calls=0,
        requests_published=0, frozen_sources_modified=False, registry_lifecycle_analysis_performed=False,
        resources=dict(new_decoded_bytes=0, reused_startup_instruction_bytes=848, retained_getter_replayed=True,
            whole_PE_disassembled=False, peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024))
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent-review.json"
    with output.open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    markdown = OUT / "report.md"
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write("# Independent CRT startup handler review\n\n"
            "The frozen848B evidence and reused getter match the fixed PE. Entrypoint1A337C8 calls cookie initializer1A34018 before CRT target1A33654. The successful CRT branch reaches the16B initializer-pair loop; the second pair1C29DF0 invokes1A63844. Reaching it requires the prior initializer's successful return.\n\n"
            "At1A6384A, RBX captures cookieC0. After the untraced call1A41B94 at1A63854, RCX is restored from RBX and leaf1A63974 stores capturedC0 into encoded slot233D0C8. The getter is exactly ROR64(C_getter XOR E_getter, C_getter&63); decodedNULL iff E_getter equals C_getter. If E remainsC0, the current getter cookie must equal capturedC0. Cookie stability only after the store is insufficient: C0=1, changed cookie2 before store and E1 decode toC000000000000000.\n\n"
            "The original conventional RIP scan's2 handler references plus1 cookie write are validated instruction boundaries. An independent overlapping scan adds only their3 interior REX-prefix suffix views, not new instructions. This remains a bounded candidate scan and does not exclude alias/bulk/other-form setters or runtime changes.\n\n"
            "No whole-startup/current/call-interval NULL guarantee follows: preceding and subsequent initializer effects, the4 untraced callees around the store, runtime mutations and setter exclusion remain unknown. Original raw evidence is correct; any prose precision fix belongs in a separate corrigendum. Additional conclusions files were outside this review. Newly decoded0B; no game access, native execution, request, registry investigation or native_ready authorization.\n")
    print(json.dumps(dict(review=pin(output), markdown=pin(markdown), source_pins=len(sources),
        startup_bytes_replayed=848, new_decoded_bytes=0, native_ready=False, game_process_accessed=False)))


if __name__ == "__main__":
    main()
