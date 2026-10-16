"""Bounded offline serialization-field evidence; never attaches to a process.

The reviewed mapping below is exact-build evidence, not an executable schema.
Control-flow discovery follows only branches within 16 KiB of each entry point;
calls and non-local tail branches remain explicit evidence edges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler

SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"


def field(name, offset, width, representation, *refs, note=None):
    return {"token_name": name, "object_offset": None if offset is None else hex(offset),
            "width_bytes": width, "representation": representation,
            "parser_evidence_rvas": [hex(r) for r in refs], "note": note,
            "evidence_level": "reviewed_static_serialization_mapping",
            "runtime_verified": False, "public_parameter_schema_complete": False}


# Names come from exact-build token descriptors, not localization guesses.
# References identify the comparison/dispatch and destination write/address.
# Unknown enum values, public units, constraints and ownership remain unknown.
PARSER_FIELDS = {
    0x5ac780: [field("curia_treasury", 0x40, 1, "boolean_byte", 0x5ac789, 0x5ac79c, 0x5ac7a7)],
    0x7c67d0: [field("third_party", 0x40, 8, "country_handle", 0x7c67d3, 0x7c67e0, 0x7c67e7)],
    0x552b80: [field("province", 0x44, 4, "signed_integer", 0x552b89, 0x552b92, 0x552bb3),
               field("amount", 0x40, 4, "signed_integer", 0x552b98, 0x552ba1, 0x552bb3)],
    0x5769e0: [field("province", 0x40, 8, "province_object_pointer", 0x5769e9, 0x576a17, 0x576a2a,
                     note="Serialized province ID is resolved through DB+0x1ca8 + id*0x2e10. Do not write the ID into this pointer.")],
    0x5a18a0: [field("cost", 0x40, 4, "signed_fixed_point_1000", 0x5a18ac, 0x5a18fa, 0x5a1905),
               field("unit", 0x48, 16, "unit_reference_wrapper", 0x5a18b4, 0x5a18e9, 0x5a18f5,
                     note="Helper 0xcd990 writes a 16-byte wrapper: null cached pointer plus 8-byte serialized object identity. Serializer refreshes cached pointer from +0x50; not a plain unit pointer."),
               field("subunit_limit", 0x5c, 4, "signed_integer", 0x5a18b9, 0x5a18ce, 0x5a18e0)],
    0x5a66b0: [field("tribute", 0x40, 32, "embedded_serializable_object", 0x5a66b0, 0x5a66bd, 0x5a66c5,
                     note="Embedded vtable 0x1c7b340; nested parser 0xb1d8a0. Width describes reserved object storage, not serialized payload bytes.")],
    0x56a6b0: [field("province_id", 0x40, 4, "signed_integer", 0x56a6b9, 0x56a6cc, 0x56a6de)],
    0x572f80: [field("enforce_peace", 0x40, 8, "country_handle", 0x572f90, 0x572fdf, 0x572fec,
                     note="Token matches action name; handle role needs gameplay validation, do not rename to war ID.")],
    0x53b1a0: [field("money", 0x40, 4, "signed_fixed_point_1000", 0x53b1a9, 0x53b1bc, 0x53b1c7)],
    0x5392c0: [field("index", 0x40, 4, "signed_integer", 0x5392c9, 0x5392dc, 0x5392ee,
                     note="Index meaning and valid range are not established by serialization.")],
    0x7c6710: [field("intervene_in_war", 0x40, 8, "country_handle", 0x7c6720, 0x7c676f, 0x7c677c,
                     note="Handle, not proven war numeric ID.")],
    0x58f320: [field("name", 0x40, 32, "engine_string32", 0x58f323, 0x58f32d, 0x58f334)],
    0x5476e0: [field("amount", 0x40, 4, "signed_integer", 0x5476e9, 0x5476f2, 0x547710),
               field("duration", 0x48, 4, "signed_integer", 0x5476f8, 0x5476fe, 0x547710,
                     note="Time unit and legal bounds are not proven here."),
               field("interest", 0x44, 4, "signed_fixed_point_1000", 0x547726, 0x54772f, 0x54773a)],
    0x59bde0: [field("force", 0x208, 1, "boolean_byte", 0x59bdec, 0x59be34, 0x59be42),
               field("diplomats", 0x40, 1, "boolean_byte", 0x59bdf5, 0x59be2e, 0x59be42),
               field("terms", 0x48, 448, "embedded_peace_offer", 0x59bdfe, 0x59be1d, 0x59be2a,
                     note="Embedded object owns nested containers/components. Vtable 0x1c578b8; parser 0x981170. Storage extent 0x1c0 inferred from next field +0x208."),
               field("demand", 0x41, 1, "boolean_byte", 0x59be07, 0x59be17, 0x59be42)],
    0x555540: [field("province", 0x40, 4, "signed_integer", 0x555549, 0x555576, 0x555588),
               field("tag", 0x44, 8, "country_handle", 0x555552, 0x555565, 0x555571,
                     note="Unaligned 8-byte full country handle at +0x44.")],
    0x4f08d0: [field("force", 0x60, 1, "boolean_byte", 0x4f08d9, 0x4f08ec, 0x4f08f7,
                     note="Internal force flag; not an ordinary public request parameter.")],
    0xac65a0: [field("action_type", 0x40, 8, "scripted_definition_pointer", 0xac65ae, 0xac65d2, 0xac66f8,
                     note="Registry 0x5b6b80 resolves exact action name through hashed string lookup. Factory RDX takes definition pointer, not token/string. Missing-name sentinel is not a valid definition.")],
    0x55b890: [field("unit", 0x48, 16, "unit_reference_wrapper", 0x55b899, 0x55b8a2, 0x55b8ae),
               field("amount", 0x40, 4, "signed_integer", 0x55b8b3, 0x55b8bc, 0x55b8ce)],
    0x54ee40: [field("region", 0x40, 4, "signed_integer", 0x54ee49, 0x54ee52, 0x54ee64,
                     note="Serialized integer; region enumeration/lookup and bounds remain unresolved.")],
    0x57d050: [field("dummy", None, None, "accepted_ignored_token", 0x57d050, 0x57d05d)],
    0x584420: [field("rebel", 0x40, 8, "target_rebel_faction_pointer", 0x58442c, 0x584453, 0x5844a4, 0x5844aa, 0x5844c1,
                     note="Parses two-DWORD identity, searches recipient country+0xe68..0xe70 for matching faction+0x10/+0x14, then stores faction pointer. Not a rebel type string.")],
    0x54cb20: [field("province", 0x40, 4, "signed_integer", 0x54cb30, 0x54cb39, 0x54cb4b),
               field("taker", 0x44, 8, "country_handle", 0x54cb66, 0x54cba6, 0x54cbae)],
    0x4fe890: [field("favors", 0x40, 4, "signed_fixed_point_1000", 0x4fe89c, 0x4fe8d1, 0x4fe8dc),
               field("trust_value", 0x44, 4, "signed_integer", 0x4fe8a4, 0x4fe8b6, 0x4fe8c8)],
    0x57afb0: [field("amount", 0x40, 4, "signed_fixed_point_1000", 0x57afb9, 0x57afcc, 0x57afd7,
                     note="Fixed-point representation is confirmed; mapping UI percentage to this value is not established here.")],
    0x5a5430: [field("reason", 0x40, 4, "integer_enum_values_unknown", 0x5a5440, 0x5a5473, 0x5a548d)],
    0x549480: [field("duration", 0x44, 4, "signed_integer", 0x549489, 0x54948f, 0x5494a1,
                     note="Time unit and legal bounds are not established by serialization."),
               field("amount", 0x40, 4, "signed_fixed_point_1000", 0x5494b7, 0x5494c0, 0x5494cb)],
    0x543b90: [field("versus", 0x40, 8, "country_handle", 0x543bc8, 0x543d60, 0x543d68),
               field("replace", 0x49, 1, "boolean_byte", 0x543bd1, 0x543cfd, 0x543d01),
               field("call_ally_type", 0x4c, 4, "integer_enum_values_unknown", 0x543ba6, 0x543e20, 0x543e38),
               field("defensive_war_with", 0x48, 1, "inverted_boolean_byte", 0x543be9, 0x543c0b, 0x543c0d,
                     note="Serializer 0x543a70/sete: text true corresponds to stored zero."),
               field("union", 0x52, 1, "inverted_boolean_byte", 0x543bbc, 0x543d96, 0x543d98),
               field("full_ally", 0x51, 1, "inverted_boolean_byte", 0x543e4f, 0x544080, 0x544082),
               field("promised_land", 0x53, 1, "inverted_boolean_byte", 0x543e67, 0x543f53, 0x543f55),
               field("autojoin", 0x50, 1, "inverted_boolean_byte", 0x543e5b, 0x543fd5, 0x543fd7),
               field("ignore", 0x56, 1, "inverted_boolean_byte", 0x543bdd, 0x543c8d, 0x543c8f),
               field("specific_enemies", 0x58, 24, "country_handle_vector", 0x543e70, 0x543eb1, 0x543ef7,
                     note="Owned vector begin/end/capacity; element width 8, not a single third-country handle.")],
    0x50bc10: [field("stability", 0x40, 1, "boolean_byte", 0x50bc3b, 0x50bcf8, 0x50bc63),
               field("succession", 0x41, 1, "boolean_byte", 0x50bc4c, 0x50bc5f, 0x50bc63),
               field("colonialwar", 0x42, 1, "boolean_byte", 0x50bd4b, 0x50be36, 0x50bc63),
               field("attacker", 0x50, 24, "country_handle_vector", 0x50bc47, 0x50bccd, 0x50bcd0, 0x50bce8),
               field("promised_land", 0x68, 24, "country_handle_vector", 0x50bd57, 0x50be0e, 0x50be26),
               field("full_ally", 0x80, 24, "country_handle_vector", 0x50bd3f, 0x50be8e, 0x50bea9),
               field("attacker_call_all", None, None, "accepted_ignored_boolean", 0x50bc25, 0x50bd0f, 0x50bd2a,
                     note="Parser validates yes/no without a field write in this path; serializer does not emit this token."),
               field(None, 0x48, 8, "polymorphic_war_goal_pointer", 0x50bd5f, 0x50bd6b, 0x50bd70, 0x50bda7,
                     note="Token->enum mapper 0xd9b740, factory 0xd9b080, nested virtual +0x18 parser. Dynamic selector; never a plain casus belli string pointer. Lifetime rules require separate verification.")],
}

NESTED_FIELDS = {
    0xb1d8a0: [field("type", 0x18, 1, "integer_enum_values_unknown", 0xb1d8b0, 0xb1d981, 0xb1d986),
               field("amount", 0x1c, 4, "signed_fixed_point_1000", 0xb1d8bd, 0xb1d92f, 0xb1d93a),
               field("subject", 0x10, 8, "country_handle", 0xb1d8c6, 0xb1d918, 0xb1d920)],
    0x981170: [field("giver", 0x10, 8, "country_handle", 0x9811ad, 0x981447, 0x98144f),
               field("taker", 0x18, 8, "country_handle", 0x9811b9, 0x98138a, 0x98138d,
                     note="Parser accepts country tag and legacy integer slot paths."),
               field("is_demand", 0x20, 1, "boolean_byte", 0x9811c2, 0x981267, 0x981272),
               field("givers", 0x58, 24, "country_handle_vector", 0x9811cb, 0x9811e6, 0x9811ed),
               field("takers", 0x70, 24, "country_handle_vector", 0x98118b, 0x981538, 0x98153f),
               field("war_givers", 0x28, 24, "country_handle_vector", 0x981574, 0x981652, 0x981668),
               field("war_takers", 0x40, 24, "country_handle_vector", 0x981580, 0x98164c, 0x981668),
               field("apply_penalties", 0x1b9, 1, "boolean_byte", 0x981591, 0x9815c5, 0x9815d3),
               field("index", None, 4, "component_index_in_group", 0x9811a1, 0x98146a, 0x981520,
                     note="Indexes latest component into grouped vector at offer+0xd0; not a standalone scalar field."),
               field(None, 0x88, 24, "peace_component_pointer_vector", 0x9815a4, 0x981607, 0x98161c, 0x981620,
                     note="Dynamic token registry 0x9d3650 resolves type descriptor, factory 0x99ff90 dispatches 40 cases; scriptable token 0x3662 has dedicated descriptor.")],
    0x99b400: [field("giver", 0x22, 8, "country_handle", 0x99b410, 0x99b533, 0x99b53b,
                     note="Unaligned full country handle at +0x22, distinct from offer_giver."),
               field("is_selected", 0x20, 1, "boolean_byte", 0x99b41d, 0x99b4d6, 0x99b4e1),
               field("offer_giver", 0x10, 8, "country_handle", 0x99b427, 0x99b4bf, 0x99b4c7),
               field("offer_taker", 0x18, 8, "country_handle", 0x99b42d, 0x99b471, 0x99b479)],
    0x9b43f0: [field("value", 0x30, 4, "signed_fixed_point_1000", 0x9b43f9, 0x9b440c, 0x9b4417)],
    0x99e590: [field("taker", 0x30, 8, "country_handle", 0x99e5a0, 0x99e5ef, 0x99e5fc)],
    0x9a3830: [field("tribal", 0x40, 1, "boolean_byte", 0x9a3840, 0x9a392b, 0x9a3936),
               field("province_id", 0x38, 8, "province_object_pointer", 0x9a384d, 0x9a390e, 0x9a391c),
               field("taker", 0x30, 8, "country_handle", 0x9a3856, 0x9a38a5, 0x9a38ad)],
    0x99e6d0: [field("province_id", 0x38, 8, "province_object_pointer", 0x99e6e0, 0x99e7a1, 0x99e7af),
               field("taker", 0x30, 8, "country_handle", 0x99e6e9, 0x99e738, 0x99e740)],
    0x9c9d70: [field("region", 0x30, 8, "colonial_region_definition_pointer", 0x9c9d7c, 0x9c9dc4, 0x9c9dc9,
                     note="String lookup through global definition registry; not a numeric region index.")],
    0xac9a30: [field("type", 0x30, 8, "scripted_peace_definition_pointer", 0xac9a39, 0xac9a68, 0xac9b8a,
                     note="Different registry/field from top-level action_type at action+0x40. Missing lookup leaves null.")],
    0xd9c0d0: [field("type", 0x10, 8, "war_goal_definition_pointer", 0xd9c10d, 0xd9c34d, 0xd9c391, 0xd9c396),
               field("province", 0x18, 4, "signed_integer", 0xd9c11a, 0xd9c33f, 0xd9c344),
               field("casus_belli", 0x40, 8, "casus_belli_definition_pointer", 0xd9c127, 0xd9c2aa, 0xd9c2ee, 0xd9c2f3,
                     note="Name resolved via registry 0x1f9210 and lookup 0x1fa0a0. Not a raw script string pointer."),
               field("continent", 0x30, 8, "continent_definition_pointer", 0xd9c134, 0xd9c13e, 0xd9c254),
               field("tag", 0x1c, 8, "country_handle", 0xd9c0fa, 0xd9c3d8, 0xd9c3e0),
               field("subjects", 0x38, 8, "country_handle", 0xd9c403, 0xd9c5ee, 0xd9c5f6,
                     note="Despite plural token, this parser stores one full handle. Not a subject type enum."),
               field("rebel_faction", 0x50, 16, "object_reference_wrapper", 0xd9c3f6, 0xd9c5ff, 0xd9c606),
               field("region", 0x28, 8, "region_definition_pointer", 0xd9c3e9, 0xd9c610, 0xd9c724)],
}


def token_descriptors(pe):
    records = defaultdict(list)
    pattern = re.compile(rb"[a-z][a-z0-9_]{0,100}\x00")
    for section in pe.sections:
        if section["name"] != ".data":
            continue
        for match in pattern.finditer(pe.data, section["raw"], section["raw"] + section["size"]):
            value = pe.u32(match.start() - 4)
            if 0 < value < 0x10000 and pe.data[match.end():match.end() + 16] == bytes(16):
                records[value].append({"name": match.group()[:-1].decode(),
                                       "descriptor_rva": hex(pe.to_rva(match.start() - 4))})
    return records


def bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000):
    """Decode reachable instructions, including split pdata fragments.

    No recursive callee traversal. A local jmp may be a tail-call, so the report
    labels this a reachable bounded graph, not a proven complete function body.
    """
    pending, seen, edges = [entry], {}, []
    while pending:
        pc = pending.pop()
        while pc not in seen:
            if not entry <= pc < entry + window or not pe.executable(pc):
                edges.append({"target_rva": hex(pc), "kind": "outside_bounded_window"})
                break
            if len(seen) >= max_instructions:
                raise ValueError(f"Instruction bound exceeded at {entry:#x}")
            decoded = list(md.disasm(pe.bytes_at(pc, 15), pc, count=1))
            if not decoded:
                break
            ins = decoded[0]
            seen[pc] = ins
            next_pc = pc + ins.size
            if ins.mnemonic in ("ret", "retf", "int3", "ud2"):
                break
            if ins.mnemonic.startswith("j"):
                operand = ins.operands[0]
                if operand.type == 2:
                    target = operand.imm
                    local = entry <= target < entry + window and pe.executable(target)
                    edges.append({"source_rva": hex(pc), "target_rva": hex(target),
                                  "kind": "branch", "followed": local})
                    if local:
                        pending.append(target)
                else:
                    edges.append({"source_rva": hex(pc), "kind": "indirect_branch",
                                  "operand": ins.op_str})
                if ins.mnemonic == "jmp":
                    break
            pc = next_pc
        check_memory_budget()
    return [seen[k] for k in sorted(seen)], edges


def encode_function(pe, md, entry):
    instructions, edges = bounded_cfg(pe, md, entry)
    return {"entry_rva": hex(entry), "prefix16_hex": pe.bytes_at(entry, 16).hex(),
            "decoded_bytes": sum(ins.size for ins in instructions),
            "instructions": [{"rva": hex(ins.address), "bytes": ins.bytes.hex(),
                              "instruction": f"{ins.mnemonic} {ins.op_str}".rstrip()}
                             for ins in instructions],
            "edges": edges, "runtime_verified": False}


def peace_factories(pe, md, cs, tokens):
    cases = []
    for index in range(40):
        table_rva = 0x9a0f98 + index * 4
        entry = pe.u32(pe.to_offset(table_rva))
        instructions, _ = bounded_cfg(pe, md, entry)
        candidates, allocations = [], []
        last_ecx = None
        for ins in instructions:
            ops = ins.operands
            if ins.mnemonic == "mov" and len(ops) == 2 and ops[0].type == cs.x86.X86_OP_REG and ins.reg_name(ops[0].reg) == "ecx" and ops[1].type == cs.x86.X86_OP_IMM:
                last_ecx = ops[1].imm
            if ins.mnemonic == "call" and ops[0].type == cs.x86.X86_OP_IMM and ops[0].imm == 0x1a332d4:
                allocations.append({"call_rva": hex(ins.address), "size_bytes_candidate": last_ecx})
            if ins.mnemonic != "lea" or len(ops) != 2 or ops[1].type != cs.x86.X86_OP_MEM or ops[1].mem.base != cs.x86.X86_REG_RIP:
                continue
            vtable = ins.address + ins.size + ops[1].mem.disp
            off = pe.to_offset(vtable + 0xa0)
            if off is None:
                continue
            getter = pe.u64(off) - pe.base
            if not pe.executable(getter):
                continue
            code = pe.bytes_at(getter, 6)
            if len(code) != 6 or code[0] != 0xb8 or code[5] != 0xc3:
                continue
            token = int.from_bytes(code[1:5], "little")
            if token not in tokens:
                continue
            candidates.append({"name": tokens[token][0]["name"], "token_id": token,
                               "token_hex": hex(token), "token_descriptors": tokens[token],
                               "vtable_rva": hex(vtable), "token_getter_rva": hex(getter),
                               "vtable_reference_rva": hex(ins.address),
                               "serializer_rva": hex(pe.u64(pe.to_offset(vtable + 0x10)) - pe.base),
                               "parser_rva": hex(pe.u64(pe.to_offset(vtable + 0x20)) - pe.base)})
        if len(candidates) != 1:
            raise ValueError(f"Expected one reviewed component vtable for switch case {index}")
        cases.append({"factory_case_index": index, "switch_table_entry_rva": hex(table_rva),
                      "factory_branch_rva": hex(entry), "allocations": allocations,
                      **candidates[0], "runtime_verified": False})
    return cases


def build_report(pe, md, cs, args, tokens, digest):
    inventory_bytes = args.inventory.read_bytes()
    inventory = json.loads(inventory_bytes)
    sources = inventory["native_actions"]["actions"]
    if len(sources) != 88:
        raise ValueError("Expected pinned inventory with 88 native actions")
    functions = {}

    def include(entry):
        key = hex(entry)
        if key not in functions:
            functions[key] = encode_function(pe, md, entry)
        return functions[key]

    name_to_tokens = defaultdict(list)
    for value, records in tokens.items():
        for record in records:
            name_to_tokens[record["name"]].append((value, record))

    def resolve_fields(parser, serializer, definitions):
        body = include(parser)
        serialized = include(serializer)
        addresses = {ins["rva"] for ins in body["instructions"]}
        results = []
        for spec in definitions:
            item = dict(spec)
            missing = set(item["parser_evidence_rvas"]) - addresses
            if missing:
                raise ValueError(f"Missing bounded parser evidence {missing} in {parser:#x}")
            item["parser_rva"] = hex(parser)
            item["serializer_rva"] = hex(serializer)
            candidates = name_to_tokens.get(item["token_name"], [])
            if item["token_name"] is not None and len(candidates) != 1:
                raise ValueError(f"Ambiguous/missing descriptor {item['token_name']}")
            if candidates:
                value, descriptor = candidates[0]
                item.update(token_id=value, token_hex=hex(value), token_descriptor=descriptor)
                item["serializer_token_evidence_rvas"] = [ins["rva"] for ins in serialized["instructions"]
                    if ins["instruction"] == f"mov edx, {value:#x}"]
            else:
                item.update(token_id=None, token_hex=None, token_descriptor=None,
                            serializer_token_evidence_rvas=[])
            results.append(item)
        return results

    actions = []
    core_names = {"vassalaction", "royal_marriage", "improve_relation", "guaranteeaction", "spy_network"}
    for source in sources:
        parser = int(source["slots"]["0x20"], 16)
        serializer = int(source["slots"]["0x10"], 16)
        fields = resolve_fields(parser, serializer, PARSER_FIELDS.get(parser, []))
        known_intervals = [(int(f["object_offset"], 16), int(f["object_offset"], 16) + f["width_bytes"])
                           for f in fields if f["object_offset"] is not None and f["width_bytes"] is not None]
        unmapped = []
        for read in source["clone"]["source_field_reads"]:
            offset = int(read["offset"], 16)
            width = read["width_bytes"]
            if offset >= 0x40 and not any(low <= offset and offset + width <= high for low, high in known_intervals):
                unmapped.append(read)
        unmapped_writes = []
        for write in source["clone"]["memory_writes"]:
            offset, width = int(write["offset"], 16), write["width_bytes"]
            if write["base_register"] not in ("rsp", "rbp") and offset >= 0x40 and not any(low <= offset and offset + width <= high for low, high in known_intervals):
                unmapped_writes.append(write)
        actions.append({"name": source["name"], "token_id": source["token_id"],
                        "vtable_rva": source["vtable_rva"], "allocation_size": source["layout"]["allocation_size_candidate"],
                        "part_of_prior_five_core": source["name"] in core_names,
                        "parser_rva": hex(parser), "serializer_rva": hex(serializer),
                        "base_fields_ref": "#/base_fields",
                        "derived_fields": fields,
                        "unmapped_clone_reads": unmapped,
                        "unmapped_clone_nonstack_writes_candidates": unmapped_writes,
                        "clone_access_list_is_not_exhaustive": True,
                        "value_mode_candidates": [v for v in inventory["native_actions"].get("static_variants", [])
                                                   if v["native_action_name"] == source["name"]],
                        "no_derived_fields_observed": not fields,
                        "no_derived_fields_does_not_mean_parameterless": True,
                        "runtime_verified": False, "execution_status": "not_changed_by_this_report"})

    nested = []
    for name, parser, serializer, vtable, parent, offset in [
        ("tribute", 0xb1d8a0, 0xb1d7c0, 0x1c7b340, "confirm_tribute_action", 0x40),
        ("peace_offer", 0x981170, 0x981690, 0x1c578b8, "requestpeace", 0x48),
    ]:
        nested.append({"name": name, "parent_action": parent, "parent_offset": hex(offset),
                       "vtable_rva": hex(vtable), "parser_rva": hex(parser), "serializer_rva": hex(serializer),
                       "fields": resolve_fields(parser, serializer, NESTED_FIELDS[parser]),
                       "runtime_verified": False})
    components = peace_factories(pe, md, cs, tokens)
    for component in components:
        parser, serializer = int(component["parser_rva"], 16), int(component["serializer_rva"], 16)
        component["fields"] = resolve_fields(parser, serializer, NESTED_FIELDS[parser])
        component["base_fields_ref"] = "#/peace_component_base_fields" if parser != 0x99b400 else None
        component["public_parameter_schema_complete"] = False
        include(int(component["factory_branch_rva"], 16))
    war_goal_object = {
        "name": "war_goal_common", "parent_action": "declarewar", "parent_pointer_offset": "0x48",
        "reviewed_example_vtable_rva": "0x1d1fd90", "example_factory_case": "take_colony/index0",
        "example_factory_branch_rva": "0xd9b0a3", "example_factory_vtable_write_rva": "0xd9b129",
        "parser_rva": "0xd9c0d0", "serializer_rva": "0xd9bea0",
        "fields": resolve_fields(0xd9c0d0, 0xd9bea0, NESTED_FIELDS[0xd9c0d0]),
        "all_war_goal_vtables_verified": False,
        "runtime_verified": False,
        "note": "Shared-looking parser reviewed from exact take_colony vtable; do not assume every goal subclass has identical full lifetime/schema.",
    }
    include(0xd9b0a3)

    # Exact reviewed helper bodies justify storage encodings; they are never called.
    helpers = {
        "signed_fixed_point_parser": (0x170f620, "DWORD signed decimal*1000; 0x170f670 and 0x170f6f7 multiply by 1000."),
        "signed_fixed_point_serializer": (0x246bc0, "DWORD divided into signed integer quotient and 3 decimal places, multiplier 1000 at 0x246bf1."),
        "boolean_parser": (0x170f720, "Writes one byte: yes=1/no=0; 0x170f744 and 0x170f767."),
        "country_handle_parser": (0x2896d0, "Resolves tag to full 8-byte handle; writes QWORD at 0x289814."),
        "unit_reference_parser": (0xcd990, "Writes 16 bytes at 0xcd9f7: cache pointer=0, followed by parsed 8-byte identity."),
        "peace_component_factory": (0x99ff90, "40-entry switch table at 0x9a0f98; each case independently traversed."),
        "peace_token_registry_lookup": (0x9d3650, "Token hash map -> 16-byte descriptor; no match returns index -1, pointer 0."),
        "war_goal_token_mapper": (0xd9b740, "Jump table at 0xd9b7b0 plus blockade_ports token0x2f7a; not a casus-belli registry."),
        "war_goal_factory": (0xd9b080, "13-case allocation switch at 0xd9b674; dynamic nested pointer at declarewar+0x48."),
        "server_context_getter": (0x811aa0, "Returns *( *(server+0x330) +0x370 ). Static three-instruction getter only."),
    }
    helper_report = {}
    for name, (entry, description) in helpers.items():
        include(entry)
        helper_report[name] = {"rva": hex(entry), "description": description,
                               "prefix16_hex": pe.bytes_at(entry, 16).hex(), "runtime_verified": False}

    # Explicitly read the bounded war-goal token switch. Indirect branches are
    # not guessed by the generic CFG walker.
    war_goal_tokens = []
    for token, target in [(0x2de7 + i, pe.u32(pe.to_offset(0xd9b7b0 + i * 4))) for i in range(19)] + [(0x2f7a, 0xd9b7a4)]:
        code = pe.bytes_at(target, 6)
        index = 0 if code.startswith(b"\x33\xc0\xc3") else int.from_bytes(code[1:5], "little") if code[0] == 0xb8 and code[5] == 0xc3 else None
        if index is None:
            raise ValueError(f"Unexpected mapper leaf {target:#x}")
        if index == 12:
            continue
        include(target)
        war_goal_tokens.append({"token_id": token, "token_hex": hex(token), "descriptors": tokens[token],
                                "factory_case_index": index, "mapper_leaf_rva": hex(target), "runtime_verified": False})

    base = [{"token_name": name, "object_offset": hex(offset), "width_bytes": width,
             "representation": representation, "token_id": name_to_tokens[name][0][0],
             "runtime_verified": False}
            for name, offset, width, representation in [
                ("actor", 0x10, 8, "country_handle"), ("original", 0x18, 8, "country_handle"),
                ("recipient", 0x20, 8, "country_handle"), ("date", 0x28, 4, "engine_raw_date"),
                ("last_command_date", 0x2c, 4, "engine_raw_date"), ("envoy", 0x30, 4, "signed_integer"),
                ("type", 0x34, 4, "integer_enum_action_specific_unknown"),
                ("value", 0x38, 1, "boolean_byte_action_specific_mode"), ("id", 0x3c, 4, "signed_integer")]]
    report = {
        "schema_version": 1, "analysis_kind": "bounded_offline_serialization_field_evidence",
        "binary": {"path": str(args.exe), "sha256": digest, "size_bytes": len(pe.data)},
        "source_inventory": {"path": args.inventory.as_posix(), "sha256": hashlib.sha256(inventory_bytes).hexdigest()},
        "scope": {"native_action_count": len(actions), "remaining_after_prior_five": sum(not a["part_of_prior_five_core"] for a in actions),
                  "actions_above_base_size": sum(a["allocation_size"] > 0x40 for a in actions),
                  "actions_with_derived_token_evidence": sum(bool(a["derived_fields"]) for a in actions),
                  "peace_component_factory_cases": len(components), "bounded_functions": len(functions),
                  "decoded_instruction_bytes_including_shared_paths": sum(f["decoded_bytes"] for f in functions.values())},
        "limits": ["Offsets and widths are evidence, not a safe executable public schema.",
                   "No running process was read, written, injected or called by this analysis.",
                   "No action execution or runtime verification is established by this report.",
                   "Per-function CFG follows branches within 16 KiB; indirect branches remain unresolved except explicitly reviewed tables.",
                   "No derived serialization fields does not prove no parameters; base type/id/value and transient caches may carry state.",
                   "Scalar storage encoding does not prove valid ranges, units, current ownership, actor authority, legal combinations or game-thread safety.",
                   "Fields absent from serializers may be caches, ignored flags, or non-persistent state; absence is not permission to zero them."],
        "base_fields": base, "base_parser_rva": "0x4e8b40", "base_serializer_rva": "0x4e87b0",
        "actions": actions, "embedded_objects": nested, "war_goal_object": war_goal_object,
        "peace_component_base_fields": resolve_fields(0x99b400, 0x99b550, NESTED_FIELDS[0x99b400]),
        "peace_components": components, "war_goal_token_cases": war_goal_tokens,
        "helpers": helper_report, "functions": functions, "runtime_verified": False,
        "analysis_memory_guard_bytes": 768 * 1024 * 1024,
    }
    report["scope"]["bounded_functions"] = len(functions)
    report["scope"]["decoded_instruction_bytes_including_shared_paths"] = sum(f["decoded_bytes"] for f in functions.values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=Path("../eu4.exe"))
    parser.add_argument("--inventory", type=Path, default=Path("work/reports/native-diplomacy-1.37.5.json"))
    parser.add_argument("--deps-dir", type=Path)
    parser.add_argument("--print-rva", action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path("work/reports/native-action-fields-1375.json"))
    args = parser.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise ValueError("Reviewed field map requires exact 1.37.5 executable SHA256")
    md, cs = make_disassembler(args.deps_dir)
    if not md:
        raise ValueError("Capstone is required")
    tokens = token_descriptors(pe)
    if args.print_rva:
        for value in args.print_rva:
            entry = int(value, 0)
            print(f"\n{entry:#x}")
            instructions, edges = bounded_cfg(pe, md, entry)
            for ins in instructions:
                suffix = []
                if ins.mnemonic in ("cmp", "sub", "mov"):
                    for operand in ins.operands:
                        if operand.type == cs.x86.X86_OP_IMM and operand.imm in tokens:
                            suffix.extend(x["name"] for x in tokens[operand.imm])
                print(f"{ins.address:x} {ins.mnemonic} {ins.op_str}" +
                      (" | token candidate: " + ",".join(suffix) if suffix else ""))
        return
    report = build_report(pe, md, cs, args, tokens, digest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output.as_posix(), "scope": report["scope"],
                      "peak_commit_bytes": check_memory_budget(), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
