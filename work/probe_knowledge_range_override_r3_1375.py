"""Exact observed knowledge-range override RPM supplement; no native call.

Composes the frozen knowledge and guarded remaining-pair readers in this
interpreter without changing their files. All inherited identity, pause,
module, Mod-1, source-pin and shared8192-call/1MiB two-pass guards remain.
"""
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_knowledge_context_r3_1375 as knowledge

ORIGINAL_SAMPLE, ORIGINAL_PINS = knowledge.sample, knowledge.source_pins
guarded = knowledge.guarded
PREFIX = "work/reports/diplomacy-corrective-20261014-r3/knowledge-range-override/"
SOURCES = ("work/probe_knowledge_range_override_r3_1375.py", PREFIX+"override-static.json",
           PREFIX+"override-disassembly.txt", PREFIX+"trace-override.py",
           "work/reports/diplomacy-corrective-20261014-r3/runtime/knowledge-before-test.json")
VT_RVA, SLOT_RVA, CODE_BYTES = 0x1CC9318, 0x8FA860, 199
CODE_SHA = "4297a5191474dab7208ff33a70ccb216e35cec7cd02c84c0d88eaa014cd27e70"


def source_pins():
    pins = ORIGINAL_PINS()
    pins.update({name: {"bytes": len(raw := guarded.read(ROOT/name, 8*1024*1024)),
                        "sha256": guarded.digest(raw)} for name in SOURCES})
    guarded.prior.require(pins["work/probe_knowledge_context_r3_1375.py"]["sha256"] ==
                          "337f916b1a1f1608de66488381e6b0d4c653a5633aad9faccca1cf62b0630ea1",
                          "Frozen knowledge reader changed")
    return pins


def addend_snapshot(reader, context):
    dense, table = reader.byte(context+0x10), reader.qword(context+0x58)
    result = {"context": hex(context), "modifier_id": 0xe1, "dense_raw_10": dense,
              "table": hex(table), "exact_modifier_business_name_not_proven": True}
    if dense:
        address = guarded.pointer(table)+0x70c
        value = reader.integer(address)
        guarded.prior.require(reader.integer(address) == value, "Dense override addend changed")
        result.update(branch="dense table+0x70c", value=value)
    else:
        count = reader.integer(context+0x64)
        guarded.prior.require(-4096 <= count <= 4096, "Override sparse modifier signed count exceeds bound")
        raw = reader.read(guarded.pointer(table), count*8) if count > 0 else b""
        matches = [{"ordinal": i, "value": struct.unpack_from("<i", raw, i*8+4)[0]}
                   for i in range(max(0, count)) if struct.unpack_from("<i", raw, i*8)[0] == 0xe1]
        result.update(branch="sparse firstkey225 else nativezero", count_signed=count,
                      matching_entries=matches, value=matches[0]["value"] if matches else 0,
                      records_sha256=hashlib.sha256(raw).hexdigest())
        guarded.prior.require(reader.integer(context+0x64) == count, "Override sparse count changed")
    guarded.prior.require(reader.byte(context+0x10) == dense and reader.qword(context+0x58) == table,
                          "Override modifier context header changed")
    return result


def sample(reader, base, image_size):
    value = ORIGINAL_SAMPLE(reader, base, image_size)
    sharing = value["knowledge_context_supplement"]
    provider_range = sharing["pairs"][0]["provider_native_range"]
    before = {"233ff2c_raw": reader.byte(base+0x233ff2c), "233fed6_raw": reader.byte(base+0x233fed6)}
    direct_identity = before["233ff2c_raw"] != 0 and before["233fed6_raw"] == 0
    old_modifier = provider_range["modifier_raw"]
    override = int(provider_range["dynamic_override_pointer_2da0"], 16)
    proof = {"schema": "EU4TAG-KNOWLEDGE-RANGE-TYPED-OVERRIDE-RPM/1", "provider": "FRA",
             "gate_raw": before, "direct_global_branch_identity": direct_identity,
             "owner_thread_TLS_read_or_called": False, "initializer_called": False, "native_calls": 0,
             "original_modifier_id": 0x79, "original_modifier_raw": old_modifier,
             "base_range_raw": provider_range["base_range_raw_tech_50"],
             "override_pointer": hex(override), "modifier225": None,
             "possible_effective_modifiers": [], "possible_range_raw_values": [],
             "exact_range_raw_projected": None, "complete_legality_proven": False}
    if override:
        vt = reader.qword(override)
        guarded.prior.require(vt == base+VT_RVA, "Dynamic range override is not the observed fixed vtable")
        table = reader.read(vt, 16)
        guarded.prior.require(struct.unpack("<QQ", table) == (base+0x8f48e0, base+SLOT_RVA),
                              "Typed range override slots differ from fixed table")
        loaded_code = reader.read(base+SLOT_RVA, CODE_BYTES)
        guarded.prior.require(hashlib.sha256(loaded_code).hexdigest() == CODE_SHA,
                              "Loaded observed override code differs from fixed SHA range")
        proof.update(vtable_rva=hex(VT_RVA), slot8_rva=hex(SLOT_RVA), loaded_code_sha256=CODE_SHA,
                     typed_dispatch_and_loaded_code_validated=True, exact_Cpp_class_name_not_proven=True)
        if old_modifier is not None and "modifier_context" in provider_range:
            context = int(provider_range["modifier_context"], 16)
            addend = addend_snapshot(reader, context)
            proof["modifier225"] = addend
            if direct_identity:
                possibles = [old_modifier]
                proof["projection_status"] = "native_direct_global_identity_branch"
            else:
                possibles = sorted({old_modifier, knowledge.signed32(old_modifier+addend["value"])})
                proof["projection_status"] = ("all_TLS_return_branches_same_modifier" if len(possibles) == 1
                                              else "TLS_branch_unknown_bounded_modifier_alternatives")
            proof["possible_effective_modifiers"] = possibles
        else:
            proof["projection_status"] = "original_modifier_context_unknown"
        guarded.prior.require(reader.qword(override) == vt and reader.read(vt, 16) == table,
                              "Typed range override object/table changed")
    else:
        proof["typed_dispatch_and_loaded_code_validated"] = False
        proof["projection_status"] = "native_override_null_branch"
        if old_modifier is not None:
            proof["possible_effective_modifiers"] = [old_modifier]
    ranges = sorted({knowledge.range_arithmetic(proof["base_range_raw"], modifier)
                     for modifier in proof["possible_effective_modifiers"]})
    proof["possible_range_raw_values"] = ranges
    if len(ranges) == 1:
        proof["exact_range_raw_projected"] = ranges[0]
    proof["pair_range_projections"] = []
    for pair in sharing["pairs"]:
        distance = pair["provider_distance"]["distance_milli"]
        outcomes = sorted({distance <= raw_range for raw_range in ranges}) if distance is not None else []
        proof["pair_range_projections"].append({"action": pair["action"], "provider": pair["provider"],
            "recipient": pair["recipient"], "distance_raw": distance, "possible_range_gate_results": outcomes,
            "branch_invariant_range_gate_allows": outcomes[0] if len(outcomes) == 1 else None,
            "range_gate_is_not_complete_native_legality": True})
    provider = int(value["countries"]["FRA"]["address"], 16)
    dynamic_root = int(provider_range["dynamic_root_2358080"], 16)
    guarded.prior.require(reader.integer(provider+0x28c8) == provider_range["modifier_context_state_raw_28c8"]
                          and reader.qword(base+0x2358080) == dynamic_root
                          and reader.qword(dynamic_root+0x2da0) == override
                          and reader.byte(base+0x233ff2c) == before["233ff2c_raw"]
                          and reader.byte(base+0x233fed6) == before["233fed6_raw"]
                          and guarded.prior.roots(reader, base) == value["roots"],
                          "Range override roots/context/global gates changed within pass")
    proof["limitations"] = ["Typed override body may initialize TLS when called; this reader never invokes it.",
                             "Unknown TLS can be eliminated only when all observed return alternatives agree in modifier/range/gate result.",
                             "Modifiers are signed fixed-point raw values; business key mapping225 and exact C++ class name remain unproven.",
                             "The original knowledge_context_supplement is preserved; this separate node supplies new observations.",
                             "No action validity, dispatch, AI acceptance or sharing effect is proven by a range projection."]
    value["knowledge_range_override_supplement"] = proof
    return value


def main():
    old_sample, old_pins = knowledge.sample, knowledge.source_pins
    try:
        knowledge.sample, knowledge.source_pins = sample, source_pins
        return knowledge.main()
    finally:
        knowledge.sample, knowledge.source_pins = old_sample, old_pins


if __name__ == "__main__":
    raise SystemExit(main())
