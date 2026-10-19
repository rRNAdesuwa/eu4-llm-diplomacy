"""Bounded offline evidence for the six subject rows outside the singleton family.

Reads an exact-build PE and local source files only. Never opens a game process.
The output is a research inventory, not native-call instructions or a backend.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_diplomacy_catalog import parse_script, walk  # read-only source parser

MAX_WINDOW = 0x4000
MAX_INSTRUCTIONS = 3000
MAX_TOTAL_CODE = 128 * 1024
COMMANDS = {
    'release_colony': (0x2F39, 0x1C56090, 0xF669E0),
    'set_subject_military_focus': (0x3017, 0x1C54678, 0xF59B70),
    'set_tribute_type': (0x35C0, 0x1C53090, 0xF59D00),
    'government_interaction_command': (0x36FD, 0x1C53288, 0x13B3CA0),
}
EXTRA_ENTRIES = (0x85420, 0x85480, 0x854F0, 0x85560, 0x855D0, 0x85640,
                 0x856A0, 0x85890, 0x858F0, 0x85950, 0x859B0, 0x85A10,
                 0x85A70, 0x85AE0, 0x277310, 0x7BC160, 0x7B6AB0)


def fact(detail, *rvas):
    return {'detail': detail, 'evidence_rvas': [hex(rva) for rva in rvas],
            'runtime_verified': False}


FACTS = {
    'release_payload': fact('The 0x60 command serializes full country handles: +0x50 token from (0x2992), +0x58 token to (0x2993). UI +0x1d0 goes to command +0x50; UI +0x1c8 goes to +0x58. Gate resolves the +0x50 country and checks its dependency definition colonial flag +0x142. +0x50 is the colonial subject; +0x58 is its former overlord in this UI path. The native gate shown here does not prove all caller authorization checks.',
        0x2A1B69, 0x2A1C0A, 0x2A1D00, 0x2A1D53, 0xF66B2F, 0xF66B33, 0x2A2938, 0x2A2952),
    'release_play_as_is_second_command': fact('The first release command is submitted before testing the play checkbox. When selected, UI allocates a second 0x60 command via 0x277310: token 0x29d6 set_controller, target colony handle +0x50, context controller ID +0x58 and three byte flags +0x5c..+0x5e. This is a two-command operation with possible partial completion, not a boolean in release_colony. No atomicity or rollback is proven.',
        0xF66B8D, 0xF66B90, 0xF66BF3, 0xF66C53, 0x277368, 0x277381, 0x277385, 0x277389, 0x277391, 0x277398),
    'focus_payload_and_effect': fact('UI uses the button-array index, puts selected subject full handle at +0x50 and DWORD focus at +0x58. Serializer tokens are subject_country and subject_focus. Native gate only checks country existence/type and unsigned focus <=5; it does not itself establish that the current player is the overlord. Execute writes target country +0x2864. An adapter must separately validate authority and full handles.',
        0xF59C8A, 0xF59C8E, 0x2B291D, 0x2B2950, 0x2B2A09, 0x2B2A5B, 0x2B2B5D, 0x2B28E7),
    'tribute_payload_and_effect': fact('UI puts selected subject full handle at +0x50 and BYTE tribute index at +0x58. Serializer tokens are subject_country and tribute_type. Gate calls subject-definition helper and tribute-amount calculation for nonzero type. Execute first writes target country +0x28a6, then updates timing/messages. This is not the ordinary confirm_tribute_action diplomacy class.',
        0xF59E20, 0xF59E24, 0x2BEE41, 0x2BEE87, 0x2BEF32, 0x2BEF84, 0x2BF09D, 0x2BF0E1, 0x2BE38B),
    'government_payload': fact('UI gets mechanic definition +0x8 ID and interaction definition +0x8 ID, stores actor country full handle +0x50, mechanic DWORD ID +0x58 and interaction DWORD ID +0x5c. Serializer names are country (0x289d), parent (0x87), index (0x20c). The values are definition IDs, not string pointers, public numeric IDs or fixed shogunate source-key token numbers.',
        0x13B3CB2, 0x13B3CC1, 0x13B3D55, 0x13B3D5E, 0x2BFB36, 0x2BFB9F, 0x2BFBC1, 0x2BFC7D, 0x2BFCAB, 0x2BFC92),
    'government_gate_and_dispatch': fact('Gate resolves actor country +0x1420 government-mechanics owner, searches owner vector +0x20..+0x28 for definition +0x8 == command parent, then definition interaction array +0xe0/count DWORD +0xec for interaction +0x8 == command index. It tail-calls trigger/cost/cooldown checker 0x7b6ab0 with no explanatory output. Execute repeats mechanic lookup then calls 0x7bc160, which finds interaction ID, updates cooldown/cost and invokes the embedded effect object at interaction +0x170 virtual slot +0x78. There is no target-subject handle in the command.',
        0x2BFDAD, 0x2BFDB4, 0x2BFDD0, 0x2BFDDB, 0x2BFDE2, 0x2BFDF9, 0x2BFE11, 0x2BFAC7, 0x7BC197, 0x7BC1BC, 0x7BC286, 0x7BC299, 0x7BC2AB),
}


def read_limited(path, limit=4 * 1024 * 1024):
    if path.stat().st_size > limit:
        raise ValueError(f'Input exceeds bounded size: {path.name}')
    return path.read_bytes()


def input_record(path, relative):
    raw = read_limited(path)
    return raw, {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def inventory(catalog, peace):
    unmapped = [a for a in catalog['actions'] if not a.get('native_mapping') and not a.get('native_subject_mapping')]
    native_peace = {a['name']: a for a in peace['peace_components']}
    rows = []
    for a in unmapped:
        component = native_peace.get(a.get('game_key')) if a['surface'] == 'peace_term' else None
        rows.append({k: a.get(k) for k in ('action_id', 'surface', 'game_key', 'game_key_kind', 'parameter_status')} | {
            'evidence': a['evidence'],
            'existing_peace_component_exact_name': None if component is None else {
                'name': component['name'], 'factory_case_index': component['factory_case_index'],
                'factory_branch_rva': component['factory_branch_rva'], 'vtable_rva': component['vtable_rva'],
                'parser_rva': component['parser_rva'], 'fields': component['fields'],
                'evidence_level': 'exact_source_key_match_to_existing_static_component',
                'runtime_verified': False, 'callable': False},
        })
    peace_rows = [r for r in rows if r['surface'] == 'peace_term']
    matched_names = {r['existing_peace_component_exact_name']['name'] for r in peace_rows if r['existing_peace_component_exact_name']}
    return {'unmapped_count': len(rows), 'by_surface': dict(sorted(Counter(a['surface'] for a in rows).items())),
            'peace_component_count': len(native_peace),
            'peace_exact_source_name_matches': sum(r['existing_peace_component_exact_name'] is not None for r in rows),
            'peace_scripted_without_exact_native_name': [r['action_id'] for r in peace_rows if r['game_key_kind'] == 'scripted_action' and not r['existing_peace_component_exact_name']],
            'peace_localization_only_candidates': [r['action_id'] for r in peace_rows if r['game_key'] is None],
            'native_peace_component_names_without_exact_catalog_match': sorted(set(native_peace) - matched_names),
            'rows': rows}


def generate(exe, deps, catalog_path, peace_path, game_root):
    check_memory_budget()
    pe = PE(exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise ValueError('Unsupported executable SHA256')
    md, cs = make_disassembler(deps)
    if md is None:
        raise ValueError('Capstone unavailable')
    tokens = token_descriptors(pe)
    entries = set(EXTRA_ENTRIES)
    commands = {}
    for name, (token, table, ui) in COMMANDS.items():
        slots = {hex(i): pe.u64(pe.to_offset(table) + i) - pe.base for i in range(0, 0x70, 8)}
        if not all(pe.executable(rva) for rva in slots.values()):
            raise ValueError('Non-executable command vtable slot')
        if pe.bytes_at(slots['0x50'], 6) != b'\xb8' + token.to_bytes(4, 'little') + b'\xc3':
            raise ValueError('Command token getter mismatch')
        if [t['name'] for t in tokens.get(token, [])] != [name]:
            raise ValueError('Command token name mismatch')
        # Keep the relevant derived methods. Common no-op/dtor slots are not
        # transitive proof of lifetime or transport ownership.
        entries.update(slots[hex(i)] for i in (0x10, 0x20, 0x40, 0x48, 0x50, 0x60))
        entries.add(ui)
        commands[name] = {'token_id': token, 'token_descriptors': tokens[token], 'vtable_rva': hex(table),
            'slots': {k: hex(v) for k, v in slots.items()}, 'ui_handler_rva': hex(ui),
            'ui_allocation_bytes': 0x60, 'runtime_verified': False, 'ownership_verified': False,
            'execution_verified': False, 'backend_registered': False}
    functions, lookup, decoded, raw_functions = {}, {}, 0, {}
    for entry in sorted(entries):
        instructions, edges = bounded_cfg(pe, md, entry, window=MAX_WINDOW, max_instructions=MAX_INSTRUCTIONS)
        raw_functions[entry] = instructions
        rows = []
        for ins in instructions:
            row = {'rva': hex(ins.address), 'bytes': ins.bytes.hex(), 'instruction': f'{ins.mnemonic} {ins.op_str}'.strip()}
            rows.append(row)
            lookup[hex(ins.address)] = row
        size = sum(i.size for i in instructions)
        decoded += size
        if decoded > MAX_TOTAL_CODE:
            raise ValueError('Total decoded-code budget exceeded')
        functions[hex(entry)] = {'entry_rva': hex(entry), 'decoded_bytes': size, 'instructions': rows, 'edges': edges}
        check_memory_budget()
    facts = json.loads(json.dumps(FACTS))
    for key, value in facts.items():
        if any(rva not in lookup for rva in value['evidence_rvas']):
            raise ValueError(f'Missing exact instruction anchor in {key}')
        value['evidence_instructions'] = [lookup[rva] for rva in value['evidence_rvas']]
    # Reconstruct the GUI-name order from initializers and the copied String32
    # array, rather than assigning enum ordinals from catalog display order.
    literals = {}
    for entry in EXTRA_ENTRIES[:14]:
        target = source = None
        for ins in raw_functions[entry]:
            ops = ins.operands
            if ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == cs.CS_OP_MEM and ops[0].mem.base == cs.x86_const.X86_REG_RIP and ops[1].type == cs.CS_OP_REG and ins.reg_name(ops[1].reg) == 'rax':
                target = ins.address + ins.size + ops[0].mem.disp
            if ins.mnemonic == 'movups' and len(ops) == 2 and ops[1].type == cs.CS_OP_MEM and ops[1].mem.base == cs.x86_const.X86_REG_RIP and source is None:
                source = ins.address + ins.size + ops[1].mem.disp
        if target is not None and source is not None:
            text = pe.bytes_at(source, 96).split(b'\0', 1)[0].decode('ascii')
            literals[target] = {'gui_key': text, 'literal_rva': hex(source), 'initializer_rva': hex(entry)}
    enums = {}
    for name, init, dest_base, prefix in (
        ('military_focus', 0x856A0, 0x1FD6AB0, 'focus_select_button_'),
        ('tribute', 0x85AE0, 0x1FD6C30, 'tribute_select_button_')):
        source = None
        selected = []
        for ins in raw_functions[init]:
            ops = ins.operands
            if ins.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == cs.CS_OP_MEM and ops[1].mem.base == cs.x86_const.X86_REG_RIP:
                addr = ins.address + ins.size + ops[1].mem.disp
                if ins.reg_name(ops[0].reg) == 'rdx' and addr in literals:
                    source = addr
                elif ins.reg_name(ops[0].reg) == 'rcx' and dest_base <= addr < dest_base + 6 * 32:
                    if source is None or (addr - dest_base) % 32:
                        raise ValueError('Enum-copy initializer mismatch')
                    literal = literals[source]
                    if not literal['gui_key'].startswith(prefix):
                        raise ValueError('Wrong enum button family')
                    selected.append({'value': (addr - dest_base) // 32, 'name': literal['gui_key'][len(prefix):],
                        **literal, 'source_string32_rva': hex(source), 'copy_evidence_rva': hex(ins.address)})
        if [s['value'] for s in selected] != list(range(6)):
            raise ValueError('Incomplete or duplicate enum indices')
        enums[name] = selected
    try:
        catalog_relative = catalog_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        catalog_relative = catalog_path.name
    cat_raw, cat_input = input_record(catalog_path, catalog_relative)
    peace_raw, peace_input = input_record(peace_path, 'work/reports/native-action-fields-1375.json')
    script_rel = 'common/government_mechanics/17_shogunate.txt'
    script_raw, script_input = input_record(game_root / script_rel, script_rel)
    script = script_raw.decode('utf-8-sig')
    trees = parse_script(script)
    mechanic = next(n for n in trees if n.key == 'shogunate_mechanic')
    interactions = next(n for n in mechanic.children if n.key == 'interactions')
    scripted = []
    for name in ('expel_ronin', 'sankin_kotai', 'sword_hunt'):
        node = next(n for n in interactions.children if n.key == name)
        effect = next(n for n in node.children if n.key == 'effect')
        every = next(n for n in walk(effect.children) if n.key == 'every_subject_country')
        limit = next(n for n in every.children if n.key == 'limit')
        if not any(n.key == 'is_subject_of_type' and n.value == 'daimyo_vassal' for n in limit.children):
            raise ValueError('Shogunate all-daimyo effect scope changed')
        scripted.append({'catalog_action_id': 'subject.' + name, 'mechanic_key': mechanic.key,
            'interaction_key': name, 'source_path': script_rel, 'line': node.line, 'end_line': node.end_line,
            'source_excerpt': '\n'.join(script.splitlines()[node.line - 1:node.end_line]),
            'scope': 'actor_country_government_mechanic_with_all_matching_daimyo_effects',
            'single_target_parameter_supported': False, 'native_command': 'government_interaction_command',
            'runtime_definition_ids_resolved': False, 'runtime_verified': False,
            'execution_verified': False})
    audit = inventory(json.loads(cat_raw), json.loads(peace_raw))
    return {'schema_version': 1, 'game_sha256': digest,
        'analysis_kind': 'bounded_static_special_subject_commands_and_remaining_inventory',
        'runtime_verified': False, 'execution_verified': False, 'public_backend_registered': False,
        'inputs': [cat_input, peace_input, script_input], 'commands': commands,
        'scripted_government_interactions': scripted, 'enum_bindings': enums, 'facts': facts,
        'inventory': audit, 'functions': functions,
        'remaining_requirements': [
            'Validate lifecycle, clone/command ownership, native gate and transport separately for each new command; no existing ordinary-diplomacy lifecycle result transfers to these classes.',
            'Resolve government mechanic and interaction definition IDs by exact names inside bounded current-state registries; current report does not expose arbitrary numeric IDs or raw pointers.',
            'Replace the three shogunate single-subject request semantics before mapping; preserve compatibility IDs only with a clear actor-wide scope.',
            'Independently validate current-player/overlord authority and full generation-bearing country handles; individual native gates are not an authorization boundary.',
            'Treat release plus play-as as separately observable command steps; no rollback, atomicity or safe player-identity continuation has been proven.',
            'Peace exact-name matches identify component types only. Build an owned offer with war context, limits, orientation and acceptance validation before any public executable mapping.',
            'Localization-only aliases and scripted peace terms still require source/definition correspondence; similarity of labels alone is insufficient.',
        ],
        'limits': {'per_entry_bytes': MAX_WINDOW, 'per_entry_instructions': MAX_INSTRUCTIONS,
                   'total_code_bytes': MAX_TOTAL_CODE, 'input_file_bytes': 4 * 1024 * 1024,
                   'memory_guard_mib': 768, 'recursive_call_following': False},
        'summary': {'bounded_entries': len(functions), 'decoded_bytes': decoded,
            'special_command_classes': len(commands), 'subject_catalog_rows_researched': 6,
            'government_scope_corrections': len(scripted), 'unmapped_catalog_rows': audit['unmapped_count'],
            'peace_exact_source_name_matches': audit['peace_exact_source_name_matches']}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--exe', type=Path, default=ROOT.parent / 'eu4.exe')
    ap.add_argument('--deps-dir', type=Path, required=True)
    ap.add_argument('--game-root', type=Path, default=ROOT.parent)
    # Freeze the pre-integration discovery audit independently: having this
    # report consume a catalog which in turn embeds this report's hash creates
    # an impossible digest cycle. Pass --catalog explicitly for a fresh audit.
    ap.add_argument('--catalog', type=Path, default=ROOT / 'work/reports/subject-special-inventory-baseline-1375.json')
    ap.add_argument('--peace-report', type=Path, default=ROOT / 'work/reports/native-action-fields-1375.json')
    ap.add_argument('--output', type=Path, default=ROOT / 'work/reports/native-subject-special-paths-1375.json')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    report = generate(args.exe, args.deps_dir, args.catalog, args.peace_report, args.game_root)
    payload = (json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != payload:
            raise SystemExit('Special subject report is stale')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    print(json.dumps({'mode': 'check' if args.check else 'write', 'sha256': hashlib.sha256(payload).hexdigest(),
                      'report_bytes': len(payload), **report['summary']}))


if __name__ == '__main__':
    main()
