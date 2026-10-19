"""Exact-build, bounded offline inventory of subject interaction registrations.

No process access or executable mutation. A registered singleton is not a
callable public backend; parameter and ownership verification is still required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, encode_function, token_descriptors

CORE_ENTRIES = (0xAF37C0, 0xAF3860, 0xAF3AF0, 0xAF3B70, 0xAF3BC0,
                0xAF3CD0, 0xAF3E20, 0xAF3E70, 0xAF3F80, 0xAF4030,
                0xAF41B0, 0xA7040, 0xA7070, 0xA7180)


def generate(exe: Path, deps: Path | None):
    pe = PE(exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise ValueError("Unsupported executable SHA256")
    md, error = make_disassembler(deps)
    if md is None:
        raise ValueError(error)
    import capstone as cs

    tokens = token_descriptors(pe)
    actions, functions = [], {}
    # This exact region contains the 41 adjacent static registration functions.
    # Each is decoded independently, with a 512-byte/150-instruction ceiling.
    for entry in range(0x81C20, 0x83850, 0xB0):
        instructions, edges = bounded_cfg(pe, md, entry, window=512, max_instructions=150)
        token = singleton = table = store = None
        for ins in instructions:
            ops = ins.operands
            if ins.mnemonic == "mov" and ins.op_str.startswith("eax, ") and ops[1].type == cs.CS_OP_IMM:
                token = ops[1].imm
            if ins.mnemonic == "lea" and len(ops) == 2 and ops[1].type == cs.CS_OP_MEM and ops[1].mem.base == cs.x86_const.X86_REG_RIP:
                target = ins.address + ins.size + ops[1].mem.disp
                if ops[0].reg == cs.x86_const.X86_REG_R9:
                    singleton = target
                if ops[0].reg == cs.x86_const.X86_REG_RAX and 0x1CE6300 <= target <= 0x1CE6F30:
                    table = target
            if ins.mnemonic == "mov" and len(ops) == 2 and ops[0].type == cs.CS_OP_MEM and ops[0].mem.base == cs.x86_const.X86_REG_RIP and ops[1].type == cs.CS_OP_REG and ops[1].reg == cs.x86_const.X86_REG_RAX:
                store = ins.address + ins.size + ops[0].mem.disp
        if token is None or table is None or singleton != store:
            raise ValueError(f"Registration contract changed: {entry:#x}")
        if pe.u32(pe.to_offset(singleton) + 8) != token:
            raise ValueError("Static token does not match registration")
        names = tokens.get(token, [])
        if len(names) != 1:
            raise ValueError("Ambiguous token name")
        slots = {hex(i): hex(pe.u64(pe.to_offset(table) + i) - pe.base) for i in range(0, 0x48, 8)}
        if slots['0x0'] != '0xaf5130' or not all(pe.executable(int(v, 16)) for v in slots.values()):
            raise ValueError("Invalid singleton vtable")
        name_entry = int(slots['0x10'], 16)
        name_code, _ = bounded_cfg(pe, md, name_entry, window=256, max_instructions=100)
        labels = []
        for ins in name_code:
            if ins.mnemonic == 'lea' and ins.op_str.startswith('rdx, [rip '):
                target = ins.address + ins.size + ins.operands[1].mem.disp
                raw = pe.bytes_at(target, 100).split(b'\0', 1)[0]
                if raw and all(c in b'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in raw):
                    labels.append({'key': raw.decode(), 'rva': hex(target)})
        actions.append({
            'name': names[0]['name'], 'token_id': token,
            'token_descriptor_rva': names[0]['descriptor_rva'],
            'registration_rva': hex(entry), 'singleton_rva': hex(singleton),
            'singleton_size': 16, 'vtable_rva': hex(table), 'vtable_slots': slots,
            'effect_rva': slots['0x8'], 'legality_rva': slots['0x28'],
            'localization_keys': labels, 'runtime_verified': False,
            'public_parameter_binding_verified': False,
        })
        functions[hex(entry)] = {
            'entry_rva': hex(entry), 'decoded_bytes': sum(i.size for i in instructions),
            'instructions': [{'rva': hex(i.address), 'bytes': i.bytes.hex(),
                              'instruction': f'{i.mnemonic} {i.op_str}'.rstrip()} for i in instructions],
            'edges': edges,
        }
        functions[hex(name_entry)] = encode_function(pe, md, name_entry)
    if len(actions) != 41 or len({a['name'] for a in actions}) != 41:
        raise ValueError("Expected 41 unique registrations")
    for entry in CORE_ENTRIES:
        containing = pe.function(entry)
        if containing is not None and containing[0] != entry:
            raise ValueError("Entry is inside a different unwind function")
        functions[hex(entry)] = encode_function(pe, md, entry)
    expected_slots = {0: 0xA7180, 0x10: 0xAF3BC0, 0x20: 0xAF3CD0,
                      0x40: 0xAF3E20, 0x48: 0xAF3AF0, 0x50: 0xAF3F80,
                      0x60: 0xAF3B70}
    for offset, value in expected_slots.items():
        if pe.u64(pe.to_offset(0x1C3A650) + offset) != pe.base + value:
            raise ValueError("Subject command vtable changed")
    fields = [
        ('overlord', 0x2CB6, 0x50, 8, 'country_handle', 0xAF3D67),
        ('subject', 0x31D8, 0x58, 8, 'country_handle', 0xAF3DFC),
        ('third_party', 0x3228, 0x60, 8, 'country_handle', 0xAF3DA6),
        ('index', 0x20C, 0x68, 4, 'signed_integer_action_dependent', 0xAF3D39),
        ('token_15', 15, 0x70, 32, 'engine_string32_action_dependent', 0xAF3D50),
        ('cancel', 0x28E9, 0x90, 1, 'boolean_current_state_snapshot', 0xAF3D0B),
        ('interaction', 0x31DB, 0x98, 8, 'borrowed_static_singleton', 0xAF3DE5),
    ]
    return {
        'schema_version': 1, 'status': 'reviewed_static_only',
        'binary': {'sha256': digest, 'size_bytes': len(pe.data)},
        'registry': {'lookup_rva': '0xaf41b0', 'bucket_count_rva': '0x1fd522c',
                     'buckets_rva': '0x1fd5230', 'entry_count_rva': '0x1fd5228',
                     'enumeration_vector_rva': '0x23581c8',
                     'ownership': 'borrow singleton; do not allocate or destroy it'},
        'actions': actions,
        'command': {
            'token_id': 0x31D8, 'vtable_rva': '0x1c3a650', 'size_bytes': 0xA0,
            'constructor_rva': '0xaf3860',
            'constructor_arguments': ['allocated_command_storage', 'borrowed_interaction_singleton', 'overlord_full_handle', 'subject_full_handle'],
            'constructor_note': 'Calls af4030 to derive current cancel state. Other fields need action-specific UI evidence.',
            'virtual_slots': {hex(k): hex(v) for k, v in expected_slots.items()},
            'fields': [{'name': n, 'token_id': t, 'offset': hex(o), 'width_bytes': w,
                        'representation': r, 'parser_evidence_rva': hex(e)} for n, t, o, w, r, e in fields],
            'gate': 'af3e20 checks singleton visibility +0x30 then af3e70; af3e70 checks current overlord identity, subject type support, cancel snapshot, then singleton legality +0x28',
            'execute': 'af3af0 delegates to singleton virtual +0x8 with command as second argument',
            'lifecycle_runtime_verified': False, 'dispatch_runtime_verified': False,
        },
        'limitations': [
            'No live calls. Static registration is neither runtime availability nor execution support.',
            'Do not pass these tokens to the ordinary diplomacy factory at 35d210.',
            'Index/string/third-party bindings must be verified separately for every interaction.',
            'Cancel is captured from subject flag state at construction; it is not an arbitrary caller mode.',
            'Three source-only keys expel_ronin/sankin_kotai/sword_hunt and three GUI candidates remain outside these registrations.',
        ],
        'analysis': {'bounded_entries': len(functions),
                     'decoded_bytes': sum(v['decoded_bytes'] for v in functions.values()),
                     'peak_commit_guard_bytes': 768 * 1024 * 1024},
        'functions': functions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--deps-dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = generate(args.exe, args.deps_dir)
    check_memory_budget()
    payload = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(json.dumps({'actions': len(report['actions']), **report['analysis'],
                      'report_sha256': hashlib.sha256(payload).hexdigest()}))


if __name__ == '__main__':
    main()
