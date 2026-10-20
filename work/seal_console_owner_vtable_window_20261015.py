"""Bounded4KiB fixed-PE data-only search for a keyconsumer owner binding."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget

OUT = ROOT / "work/reports/console-owner-vtable-window-20261015-r1"
BRIDGE = ROOT / "work/reports/console-bridge-negative-20261015-r1"
OWNER = ROOT / "work/reports/console-consumer-owner-20261015-r1"
SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
START, SIZE = 0x1cb8000, 4096


def pin(path):
    raw = path.read_bytes()
    assert len(raw) <= 16 * 1024 * 1024
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def search_all(raw, needle):
    hits, position = [], 0
    while True:
        found = raw.find(needle, position)
        if found < 0:
            return hits
        hits.append(hex(START + found))
        position = found + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pe = PE(ROOT.parent / "eu4.exe")
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    raw = pe.bytes_at(START, SIZE)
    assert len(raw) == SIZE
    section = next(s for s in pe.sections if s["rva"] <= START < s["rva"] + s["size"])
    assert section["name"] == ".rdata" and START + SIZE <= section["rva"] + section["size"]
    if args.check:
        manifest = json.loads((OUT / "manifest.json").read_text())
        for relative, expected in manifest["source_pins"].items():
            assert pin(ROOT / relative) == expected
        findings = json.loads((OUT / "findings.json").read_text())
        assert findings["window"]["raw_hex"] == raw.hex()
        assert findings["window"]["sha256"] == hashlib.sha256(raw).hexdigest()
        print(json.dumps(dict(status="passed", source_pins=len(manifest["source_pins"]),
            replayed_data_bytes=SIZE, new_decoded_bytes=0)))
        return
    assert pin(BRIDGE / "manifest.json")["sha256"] == "eb86e6351fe819c59f11210540f2ba5bf22d6f62d5aaeec8688f35a18317e91d"
    assert pin(OWNER / "manifest.json")["sha256"] == "d3d579b43b4563112c60872c56dc34748727500d90fc92a3ab39f70a443aae99"
    for directory in (BRIDGE, OWNER):
        for relative, expected in json.loads((directory / "manifest.json").read_text())["source_pins"].items():
            assert pin(ROOT / relative) == expected
    targets = {}
    for name, target in (("keyconsumer_primary_entry", 0x816ad0), ("keyconsumer_chained_body", 0x816af6),
            ("previous_negative_bridge", 0x816ab0), ("prior_other_filter", 0x14ea150),
            ("prior_other_toggle", 0x1253d80), ("known_server_frame_anchor", 0x8137c0),
            ("known_server_context_getter_anchor", 0x811aa0), ("known_server_root_reset_anchor", 0x80fc90)):
        targets[name] = dict(target_rva=hex(target), absolute_VA=hex(pe.base + target),
            byte_aligned_hits=search_all(raw, struct.pack("<Q", pe.base + target)))
    assert targets["keyconsumer_primary_entry"]["byte_aligned_hits"] == []
    assert targets["keyconsumer_chained_body"]["byte_aligned_hits"] == []
    assert targets["known_server_frame_anchor"]["byte_aligned_hits"] == ["0x1cb8480"]
    assert targets["known_server_context_getter_anchor"]["byte_aligned_hits"] == ["0x1cb84e0"]
    assert targets["known_server_root_reset_anchor"]["byte_aligned_hits"] == ["0x1cb8470"]
    code_runs, run_start = [], None
    valid_noncode_pointers = []
    for offset in range(0, SIZE, 8):
        value = struct.unpack_from("<Q", raw, offset)[0]
        rva = value - pe.base
        executable = pe.executable(rva)
        if executable and run_start is None:
            run_start = START + offset
        if not executable and run_start is not None:
            code_runs.append(dict(start=hex(run_start), end_exclusive=hex(START + offset),
                vtable_boundary_proven=False))
            run_start = None
        if not executable and any(s["rva"] <= rva < s["rva"] + s["size"] for s in pe.sections):
            valid_noncode_pointers.append(dict(at=hex(START + offset), value=hex(value), rva=hex(rva)))
    if run_start is not None:
        code_runs.append(dict(start=hex(run_start), end_exclusive=hex(START + SIZE), vtable_boundary_proven=False))
    assert valid_noncode_pointers == []
    preceding = struct.unpack_from("<Q", raw, 0x1cb8458 - START)[0]
    assert preceding == pe.base + 0x149ae60 and pe.executable(preceding - pe.base)
    result = dict(schema="EU4-CONSOLE-OWNER-VTABLE-WINDOW-FINDINGS/1", game_sha256=SHA,
        status="bounded_unknown_no_keyconsumer_pointer_in_selected_window", evidence_kind="fixed_PE_raw_data_only",
        window=dict(section=".rdata", start_rva=hex(START), end_exclusive_rva=hex(START + SIZE),
            bytes=SIZE, raw_hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest()),
        exact_pointer_searches=targets,
        boundary_observations=dict(known_vtable_start_rva="0x1cb8460", preceding_qword_rva="0x1cb8458",
            preceding_value_rva="0x149ae60", preceding_value_executable=True,
            preceding_qword_is_standard_MSVC_COL_pointer=False,
            aligned_in_PE_noncode_pointer_candidates=valid_noncode_pointers,
            maximal_executable_qword_runs=code_runs,
            runs_are_proven_vtables=False, exact_known_server_vtable_end_proven=False,
            rtti_type_name_proven=False, any_post_400_slot_assigned_to_server=False,
            note="Contiguous executable qwords can span adjacent vtables. This window provides no valid in-PE noncode COL-pointer candidate; no table identity is inferred from adjacency."),
        keyconsumer_this_equals_known_server_proven=False, forwarding_candidate_selected=False,
        current_gate_value=None, gate_business_meaning="unknown",
        unresolved="816ad0 entryRCX=this is proven separately, but this limited raw metadata window cannot tie it to game+1e00/server-vt1cb8460.",
        resources=dict(additional_raw_metadata_bytes=SIZE, raw_metadata_limit_bytes=4096,
            new_decoded_bytes=0, conditional_new_decode_limit_bytes=128,
            previous_sealed_decode_scope_unchanged=True, peak_committed_bytes=check_memory_budget()),
        game_process_accessed=False, native_calls=0, keys_sent=0, memory_written=False)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "findings.json").open("x", encoding="ascii") as stream:
        json.dump(result, stream, indent=2)
    (OUT / "README.md").write_text(
        "# Limited keyconsumer owner metadata check\n\n"
        "The exact4KiB .rdata window1CB8000..1CB9000 contains no full absolute function pointer to816AD0 or816AF6, even with an unaligned byte search. Known server anchors8137C0/811AA0/80FC90 are present at1CB8480/1CB84E0/1CB8470; their presence does not bind the separate keyconsumer owner.\n\n"
        "The qword immediately before known vt1CB8460 points to executable149AE60, not a standard COL. No aligned qword in this window points into valid PE noncode data as a COL candidate. Consecutive function-pointer runs are not asserted to be one vtable, and no post400 slot is assigned across an unproved boundary.\n\n"
        "Result remains bounded unknown. No forwarding candidate was selected, no instruction was newly decoded, and no process/UI/native operation occurred. Existing8192B and32B evidence scopes remain unchanged.\n", encoding="utf-8")
    files = [OUT / "findings.json", OUT / "README.md", Path(__file__), ROOT / "work/discover_diplomacy.py",
        OWNER / "manifest.json", OWNER / "findings.json", BRIDGE / "manifest.json", BRIDGE / "findings.json"]
    manifest = dict(schema="EU4-CONSOLE-OWNER-VTABLE-WINDOW-MANIFEST/1", game_sha256=SHA,
        source_pins={p.relative_to(ROOT).as_posix(): pin(p) for p in files},
        raw_metadata_bytes=4096, new_decoded_bytes=0, game_process_accessed=False)
    with (OUT / "manifest.json").open("x", encoding="ascii") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps(dict(manifest=pin(OUT / "manifest.json"), findings=pin(OUT / "findings.json"))))


if __name__ == "__main__":
    main()
