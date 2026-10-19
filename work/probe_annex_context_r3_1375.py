"""Separate guarded two-pass annex RPM supplement; no game call or write.

The delivered remaining-pair reader is reused without editing its file. Its
complete guards, exact process identity, shared8192/1MiB RPM budget and source
checks remain in force. This adds only newly file-proven annex/capital fields.
No task object vtable or computed liberty/range predicate is guessed.
"""
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_remaining_pairs_r3_1375 as guarded

ORIGINAL_SAMPLE = guarded.sample
ORIGINAL_SOURCE_PINS = guarded.source_pins
ADDED_SOURCES = (
    "work/probe_annex_context_r3_1375.py",
    "work/reports/diplomacy-corrective-20261014-r3/annex-checks-static.json",
    "work/reports/diplomacy-corrective-20261014-r3/annex-checks-disassembly.txt",
    "work/reports/diplomacy-corrective-20261014-r3/annex-helpers-static.json",
    "work/reports/diplomacy-corrective-20261014-r3/annex-helpers-disassembly.txt",
)
GLOBALS = {"upper_liberty_clamp_raw": 0x233DBCC, "lower_liberty_clamp_raw": 0x233DDA4,
           "liberty_threshold_raw": 0x233F8B4, "minimum_vassal_years_raw": 0x233F96C}


def source_pins():
    pins = ORIGINAL_SOURCE_PINS()
    pins.update({name: {"bytes": len(raw := guarded.read(ROOT/name, 8*1024*1024)),
                        "sha256": guarded.digest(raw)} for name in ADDED_SOURCES})
    guarded.prior.require(pins["work/probe_remaining_pairs_r3_1375.py"]["sha256"] ==
                          "444d028e17efdafa3d504abc02339eade28666e47aba37a5e09e1edecd389b61",
                          "Delivered guarded reader changed")
    return pins


def complete_country_handle(raw, rows):
    slot = (raw >> 32) & 0xffff
    guarded.prior.require(0 <= slot < len(rows), "Province owner/controller/core handle slot out of table")
    if raw == 0x2d2d2d:
        guarded.prior.require(slot == 0 and rows[0].get("sentinel") is True
                              and int(rows[0]["handle"], 16) == raw,
                              "Sentinel does not match typed country row")
        return {"handle": hex(raw), "slot": slot, "sentinel": True}
    guarded.prior.require(rows[slot].get("identity_valid") is True
                          and int(rows[slot]["handle"], 16) == raw,
                          "Province complete country handle differs from typed identity")
    return {"handle": hex(raw), "slot": slot, "tag": rows[slot]["tag"],
            "selector": rows[slot]["selector"], "complete_identity_validated": True}


def province_snapshot(reader, address, province_array, rows, base, size_of_image):
    """ID+20, owner+468/controller+470 and core+490/+498 are file-proven."""
    guarded.pointer(address)
    delta = address-province_array
    guarded.prior.require(delta >= 0 and delta % 0x2e10 == 0 and delta//0x2e10 < 65536,
                          "Capital/owned province is not within the decoded indexed province array")
    indexed_id = delta//0x2e10
    header = reader.read(address, 0x28)
    vt = struct.unpack_from("<Q", header)[0]
    native_id = struct.unpack_from("<i", header, 0x20)[0]
    guarded.prior.require(base <= vt < base+size_of_image and native_id == indexed_id,
                          "Province indexed ID/vtable module bounds mismatch")
    owner, controller = struct.unpack("<QQ", reader.read(address+0x468, 16))
    begin, end = struct.unpack("<QQ", reader.read(address+0x490, 16))
    if begin == end == 0:
        raw = b""
    else:
        guarded.pointer(begin)
        guarded.pointer(end)
        guarded.prior.require(0 <= end-begin <= 32768 and (end-begin) % 8 == 0,
                              "Province full-core handle vector exceeds bounded profile")
        raw = reader.read(begin, end-begin) if end != begin else b""
    core_handles = [complete_country_handle(item[0], rows) for item in struct.iter_unpack("<Q", raw)]
    guarded.prior.require(reader.read(address, 0x28) == header
                          and reader.read(address+0x468, 16) == struct.pack("<QQ", owner, controller)
                          and reader.read(address+0x490, 16) == struct.pack("<QQ", begin, end),
                          "Province identity/ownership/core vector header changed within sample")
    return {"address": hex(address), "indexed_id": indexed_id, "native_id_raw_20": native_id,
            "province_stride_bytes": 0x2e10, "vtable_rva_observed": hex(vt-base),
            "vtable_exact_type_identity_pinned": False,
            "owner": complete_country_handle(owner, rows), "controller": complete_country_handle(controller, rows),
            "core_handles": core_handles, "core_vector_begin": hex(begin), "core_vector_end": hex(end),
            "core_vector_sha256": hashlib.sha256(raw).hexdigest(), "coring_predicate_evaluated": False}


def annexation_index(reader, outgoing, target, rows):
    root = int(outgoing["root"], 16)
    record = int(outgoing["address"], 16)
    array = reader.qword(root+0x200)
    count = reader.integer(root+0x20c)
    guarded.prior.require(0 <= count <= 4096, "Annexation index signed count exceeds bounded profile")
    raw = reader.read(guarded.pointer(array), count*16) if count else b""
    entries = []
    for i in range(count):
        slot = struct.unpack_from("<i", raw, 16*i)[0]
        object_raw = struct.unpack_from("<Q", raw, 16*i+8)[0]
        guarded.prior.require(0 <= slot < len(rows), "Annexation index counterpart slot outside typed table")
        if object_raw:
            guarded.pointer(object_raw)
        entries.append({"ordinal": i, "counterpart_slot": slot, "object_pointer_raw": hex(object_raw)})
    counterpart = reader.qword(record+0x10)
    wanted = struct.unpack("<h", struct.pack("<H", (counterpart >> 32) & 0xffff))[0]
    matches = [v for v in entries if v["counterpart_slot"] == wanted]
    guarded.prior.require(len(matches) <= 1 and counterpart == int(target["handle"], 16)
                          and reader.qword(record) == root and reader.qword(root+0x200) == array
                          and reader.integer(root+0x20c) == count,
                          "Annexation relation/index changed or selected target is duplicated")
    return {"root": hex(root), "array": hex(array), "count_signed": count, "stride": 16,
            "native_counterpart_signed16": wanted, "counterpart_complete_handle": hex(counterpart),
            "entries": entries, "matching_entries": matches, "index_member_observed": bool(matches),
            "records_sha256": hashlib.sha256(raw).hexdigest(),
            "task_object_dereferenced": False, "task_object_identity_proven": False, "engine_helper_called": False}


def sample(reader, base, size_of_image):
    value = ORIGINAL_SAMPLE(reader, base, size_of_image)
    roots, rows, countries = value["roots"], value["typed_country_rows"], value["countries"]
    game = int(roots["game"], 16)
    province_array = guarded.pointer(reader.qword(game+0x1ca8))
    globals_raw = {key: reader.integer(base+rva) for key, rva in GLOBALS.items()}
    capitals = {}
    for tag in ("FRA", "ORL"):
        address = int(countries[tag]["address"], 16)
        capital = guarded.pointer(reader.qword(address+0x14b0))
        capitals[tag] = province_snapshot(reader, capital, province_array, rows, base, size_of_image)
        guarded.prior.require(reader.qword(address+0x14b0) == capital, "Country capital path changed")
        capitals[tag]["controller_matches_selected_country_full_handle"] = (
            capitals[tag]["controller"]["handle"] == countries[tag]["handle"])
    pair = next(p for p in value["pairs"] if p["action"] == "annex_vassal")
    index = annexation_index(reader, pair["actor_to_target"], countries["ORL"], rows)
    dep = pair["dependency"]["object"]
    dependency_context = {"indexed_dependency_observed": dep is not None, "definition_annex_byte_observed": False}
    if dep is not None:
        definition, object_address = int(dep["type_definition"], 16), int(dep["address"], 16)
        raw = reader.byte(definition+0x149)
        guarded.prior.require(raw in (0, 1) and reader.qword(object_address+0x40) == definition,
                              "Dependency definition/annexability byte changed or outside bool profile")
        years = globals_raw["minimum_vassal_years_raw"]
        boundary = dep["start_date_raw"] + years*0x2238
        guarded.prior.require(0 <= years <= 1000 and 0 <= boundary < 2**31,
                              "Vassal timer arithmetic outside nonoverflow native profile")
        dependency_context.update(definition=hex(definition), definition_annex_byte_observed=True,
            definition_byte_149_raw=raw, native_definition_flag_nonzero=raw != 0,
            definition_flag_name_binding_proven=False, subject_type_name=dep["type_name"],
            dependency_start_raw=dep["start_date_raw"], year_multiplier_raw=0x2238,
            timer_boundary_raw=boundary, now_raw=roots["date"], now_strictly_greater_than_boundary=roots["date"]>boundary)
    orl = int(countries["ORL"]["address"], 16)
    owned, count = reader.qword(orl+0x1338), reader.integer(orl+0x1344)
    guarded.prior.require(0 <= count <= 256, "Selected ORL owned province list exceeds narrow sampling profile")
    raw = reader.read(guarded.pointer(owned), count*4) if count else b""
    ids = [item[0] for item in struct.iter_unpack("<i", raw)]
    guarded.prior.require(all(0 <= i < 65536 for i in ids) and len(set(ids)) == len(ids),
                          "Selected ORL owned province IDs invalid/duplicated")
    provinces = []
    for province_id in ids:
        province = province_snapshot(reader, province_array+province_id*0x2e10, province_array, rows, base, size_of_image)
        guarded.prior.require(province["owner"]["handle"] == countries["ORL"]["handle"],
                              "Selected ORL owned province owner identity mismatch")
        province["target_complete_handle_is_core"] = any(c["handle"] == countries["ORL"]["handle"]
                                                        for c in province["core_handles"])
        provinces.append(province)
    guarded.prior.require(reader.qword(orl+0x1338) == owned and reader.integer(orl+0x1344) == count
                          and reader.qword(game+0x1ca8) == province_array
                          and {key: reader.integer(base+rva) for key, rva in GLOBALS.items()} == globals_raw
                          and guarded.prior.roots(reader, base) == roots,
                          "Annex context roots/ownership/define values changed")
    value["annex_context_supplement"] = {"schema": "EU4TAG-ANNEX-CONTEXT-RPM-SUPPLEMENT/1",
        "raw_globals": globals_raw, "province_array": hex(province_array), "capitals": capitals,
        "annexation_index_FRA_to_ORL": index, "dependency_context": dependency_context,
        "ORL_owned_provinces": provinces, "ORL_owned_province_ids": ids,
        "computed_liberty_desire_evaluated": False, "coring_range_path_context_evaluated": False,
        "DIP_power_live_field_not_guessed": True, "native_calls": 0, "complete_legality_proven": False,
        "limitations": ["New indexed province identity is tied to the decoded array, native ID and full country handles; exact province vtable identity remains unpinned.",
                        "Matching annex index entry does not prove task object type, completion or effect without independent task evidence.",
                        "Target core presence is separate from3819f0 range/path/context eligibility.",
                        "Raw native definition flag and timer observations are not a complete action legality result."]}
    return value


def main():
    # Process-local composition only. Neither the delivered file nor its frozen
    # source pins are changed; the composition source itself is pinned in output.
    old_sample, old_pins = guarded.sample, guarded.source_pins
    try:
        guarded.sample, guarded.source_pins = sample, source_pins
        return guarded.main()
    finally:
        guarded.sample, guarded.source_pins = old_sample, old_pins


if __name__ == "__main__":
    raise SystemExit(main())
