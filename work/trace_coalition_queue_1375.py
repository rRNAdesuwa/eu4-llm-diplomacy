"""Bounded disk-only coalition normal AI construction-to-command-queue evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/reports/native-coalition-queue-1375.json'
ENTRIES = (0x12b860, 0x129b60, 0x58a840, 0x4e9930)
FACTS = {
    'normal_ai_constructs_state_two': {
        'summary': 'Reachable coalition branch of normal AI action helper12b860 constructs a stack action at rsp+30 (also rbp-81), writes state+34=2, installs coalition vtable1c7c788. Its cancellation path changes only value+38 to false. Both paths pass this action as RDX to129b60; this is not the legality-only temporary or the direct script effect path.',
        'anchors': (0x12c54f, 0x12c556, 0x12c561, 0x12c568, 0x12c691, 0x12c6ca, 0x12c6cf, 0x12c6d2)},
    'ordinary_wrapper_owned_queue': {
        'summary': '129b60 evaluates native action predicates then invokes virtual+40 at12a6e3. It moves the returned command pointer into AI owner+a68, clears the temporary pointer, deletes the previous owned command when present, and records priority/target/token/inverted-value metadata. This closes normal AI request construction through wrapper into an owned command queue; later network/context submit and actual application are not proved here.',
        'anchors': (0x129da0, 0x129db9, 0x129dcd, 0x12a6d6, 0x12a6d9, 0x12a6e0, 0x12a6e3, 0x12a6e6, 0x12a6ed, 0x12a6f2, 0x12a6f5, 0x12a6f8, 0x12a6fb, 0x12a709, 0x12a722, 0x12a72c, 0x12a739, 0x12a73f, 0x12a745, 0x12a749, 0x12a74c)},
    'wrapper_clone_preserves_state': {
        'summary': 'Coalition vtable+40 is4e9930 and+b0 is58a840. Wrapper calls+b0, writes only clone.last_command_date+2c before placing clone into owned command+50. Coalition clone explicitly copies source state+34 and value+38. It does not normalize state2 to0. These are static initialization/ownership observations, not forced acceptance or runtime proof.',
        'anchors': (0x4e9940, 0x4e995c, 0x4e9991, 0x4e99ba, 0x58a899, 0x58a89c, 0x58a8a0, 0x58a8a4)},
}

def generate():
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Executable identity mismatch')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    functions = {}
    decoded = 0
    for entry in ENTRIES:
        code, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=5000)
        decoded += sum(i.size for i in code)
        if decoded > 32768:
            raise ValueError('Decode budget exceeded')
        functions[hex(entry)] = {'pdata': list(map(hex, pe.function(entry) or ())),
                                 'instructions': rows(pe, code), 'edges': edges}
        check_memory_budget()
    lookup = {row['rva']: row for value in functions.values() for row in value['instructions']}
    facts = {}
    for name, item in FACTS.items():
        facts[name] = {'summary': item['summary'], 'runtime_verified': False,
                       'instructions': [lookup[hex(rva)] for rva in item['anchors']]}
    vtable = {}
    for slot, expected in ((0x40, 0x4e9930), (0xb0, 0x58a840)):
        value = pe.u64(pe.to_offset(0x1c7c788 + slot)) - pe.base
        if value != expected:
            raise ValueError('Vtable mismatch')
        vtable[hex(slot)] = hex(value)
    return {'schema': 'native_coalition_queue_1375_v1', 'game_sha256': SHA,
            'runtime_verified': False, 'execution_verified': False,
            'coalition_vtable_rva': '0x1c7c788', 'vtable_slots': vtable,
            'facts': facts, 'functions': functions,
            'limits': {'functions': len(functions), 'max_window_bytes': 0x4000,
                       'max_instructions_per_function': 5000, 'decoded_bytes': decoded,
                       'max_decoded_bytes': 32768, 'memory_guard_mib': 768, 'process_access': False},
            'unresolved': ['This is the normal AI queue path, not identification of the human GUI click callback.',
                           'Final queue dispatch and runtime effects are outside this static report.',
                           'Native callees may have other side effects; state2 is the observed normal coalition construction contract, not an acceptance override.']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = generate()
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    if args.check:
        if OUTPUT.read_bytes() != raw:
            raise ValueError('Report differs')
    else:
        OUTPUT.write_bytes(raw)
    print(json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                      'decoded_bytes': report['limits']['decoded_bytes'], 'check': args.check}))

if __name__ == '__main__':
    main()
