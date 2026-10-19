"""Generate/check disk evidence and pins only; never compile, load or call native code."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

INPUTS = {
    'work/reports/native-owned-peace-1375.json': 'f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d',
    'work/reports/native-peace-gui-send-1375.json': '1aa1be072578a2c3f21e432ba6c0928ab01d9920d85063060a91512e9a882b64',
}
HELPERS = (0xc9b40, 0xcb630, 0x42a770, 0x1136d0, 0x997800, 0x9975d0)
PIN_SPANS = (
    (0x35d210, 24), (0x35d3aa, 0x9e), (0x598af0, 0x6f), (0x59ba40, 0xb1),
    (0x598b60, 32), (0x2c6890, 0xea), (0x2c67a0, 0xa2), (0x975f40, 0x1d8),
    (0x9761c0, 32), (0x976290, 32), (0x976430, 32), (0x997280, 32),
    (0x9975ba, 16), (0x415d80, 32), (0x994280, 32), (0x998290, 32),
    (0x144150, 32), (0xc9b40, 32), (0xcb630, 32), (0x42a770, 32),
    (0x1136d0, 32), (0x997800, 32), (0x9975d0, 32), (0x59ba30, 6),
)
SLOTS = ((0x1c7b840, 0x598b60), (0x1c7b8f0, 0x59ba40), (0x1c7b8d8, 0x59ba30))

def generate():
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Wrong executable')
    inputs = []
    for name, expected in INPUTS.items():
        path = ROOT / name
        if path.stat().st_size > 2 * 1024 * 1024 or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Changed input: ' + name)
        inputs.append({'path': name, 'sha256': expected})
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    helpers = {}; decoded = 0
    for entry in HELPERS:
        code, edges = bounded_cfg(pe, md, entry, window=0x2000, max_instructions=1400)
        decoded += sum(i.size for i in code)
        if decoded > 8192:
            raise ValueError('Decode budget exceeded')
        helpers[hex(entry)] = {'pdata': list(map(hex, pe.function(entry) or ())),
                               'instructions': rows(pe, code), 'edges': edges}
        check_memory_budget()
    pin_rows = [{'rva': hex(rva), 'size': size, 'bytes': pe.bytes_at(rva, size).hex()} for rva, size in PIN_SPANS]
    for address, method in SLOTS:
        if pe.u64(pe.to_offset(address)) - pe.base != method:
            raise ValueError('Method slot changed')
    evidence = {
        'schema': 'owned_peace_default_lifecycle_candidate_v1', 'game_sha256': SHA,
        'runtime_verified': False, 'execution_verified': False, 'inputs': inputs,
        'ownership_instances': [
            {'name': 'factory_temporary', 'ctor': '0x2c6890', 'cleanup_before_return': '0x35d435',
             'observable_by_candidate': False, 'type_bucket_vector_count': 0},
            {'name': 'factory_result_embedded_offer', 'offset': '0x48', 'copy_ctor': '0x975f40',
             'type_bucket_vector_count': 40, 'owned_by_outer_action': True},
            {'name': 'virtual_clone_embedded_offer', 'offset': '0x48', 'clone': '0x59ba40',
             'type_bucket_vector_count': 40, 'owned_by_outer_action': True}],
        'default_contract': {
            'outer_size': 0x210, 'embedded_offer_size': 0x1c0,
            'outer_demand': 1, 'embedded_is_demand': 0, 'outer_diplomats': 1, 'outer_force': 0,
            'actor_original_target_giver_taker': '0x2d2d2d', 'both_action_dates': '0x29c77f8',
            'envoy': -1, 'state': 0, 'value': True, 'id': 0,
            'zero_vector_triples': ['0x28', '0x40', '0x58', '0x70', '0x88', '0xa0', '0xb8'],
            'type_index': {'offset': '0xd0', 'element_bytes': 24, 'count': 40, 'capacity': 40,
                           'allocated_bytes': 0x3c0, 'all_inner_vector_triples_zero': True},
            'self_pointer': 'offer+e8 == offer', 'aux_f0_f4': [0, 0], 'flags_1b8_1b9': [0, 1],
            'hashes': [{'offset': hex(off), 'sentinel_bytes': size, 'size': 0, 'load_factor_bits': '0x3f800000',
                        'mask': 7, 'bucket_count': 8, 'bucket_pointer_count': 16, 'bucket_capacity': 16,
                        'sentinel_next_prev_self': True, 'all_bucket_entries_equal_sentinel': True}
                       for off, size in ((0xf8, 0x30), (0x138, 0x40), (0x178, 0x40))],
            'known_owned_ranges_per_action': 8,
            'read_limits_per_inspection': {'bytes': 8192, 'scalar_reads': 512},
            'uninitialized_padding_not_compared': True},
        'hash_default_copy_closure': {
            'summary': 'Default constructors allocate self-linked empty sentinels, set load1.0,size0,mask7,buckets8 and c9b40 creates16 sentinel-filled pointers. Copy calls initially clone this empty structure.976430 reassigns empty node lists with997800/9975d0;1136d0 returns max(existing bucket count8,ceil(0/1.0),8)=8. cb630/42a770 round that to8, call c9b40 with16 and restore mask7/count8. Existing capacity16 does not grow. Thus every returned default-copy hash has16 initialized sentinel pointers with size/capacity16.',
            'anchors': ['0x1136d6', '0x113734', '0x113743', '0x11375b', '0xcb67c', '0xcb683',
                        '0xcb68c', '0xcb694', '0x42a7bc', '0x42a7c3', '0x42a7cc', '0x42a7d4'],
            'note': 'This is the empty/default path only. No assertion about populated hash payload semantics.'},
        'new_helper_functions': helpers, 'runtime_pins': pin_rows,
        'runtime_slots': [{'address': hex(a), 'method': hex(m)} for a, m in SLOTS],
        'call_plan': ['factory(0x293c,null)', 'virtual_clone(original)', 'deleting_dtor(original,1)', 'deleting_dtor(clone,1)'],
        'no_calls': ['parameterized war-dependent constructor', 'legality/AI preview', 'GUI', 'wrapper', 'submit', 'terms factory'],
        'limits': {'functions': len(HELPERS), 'decoded_bytes': decoded, 'max_decoded_bytes': 8192,
                   'memory_guard_mib': 768, 'process_access': False},
    }
    header = ['#pragma once', '#include <cstddef>', '#include <cstdint>',
              '// Generated by prepare.py from exact-SHA disk evidence; not a callable API.',
              'namespace eu4_owned_peace_lifecycle_1375::generated {',
              'struct Pin { std::uintptr_t rva; const unsigned char* bytes; std::size_t size; };']
    for n, pin in enumerate(pin_rows):
        data = bytes.fromhex(pin['bytes'])
        header.append(f'constexpr unsigned char bytes_{n}[] = {{' + ','.join(f'0x{v:02x}' for v in data) + '};')
    header.append('constexpr Pin pins[] = {')
    for n, pin in enumerate(pin_rows):
        header.append(f'    {{{pin["rva"]}, bytes_{n}, sizeof(bytes_{n})}},')
    header += ['};', 'struct Slot { std::uintptr_t address; std::uintptr_t method; };', 'constexpr Slot slots[] = {']
    header += [f'    {{{hex(a)}, {hex(m)}}},' for a, m in SLOTS]
    header += ['};', '} // namespace eu4_owned_peace_lifecycle_1375::generated', '']
    return evidence, '\n'.join(header).encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    evidence, pins = generate()
    outputs = {'default-layout-evidence.json': (json.dumps(evidence, indent=2) + '\n').encode(), 'pins.h': pins}
    for name, raw in outputs.items():
        path = HERE / name
        if args.check:
            if path.read_bytes() != raw: raise ValueError('Generated output changed: ' + name)
        else:
            path.write_bytes(raw)
    sources = ['prepare.py', 'peace-owned-lifecycle-1375.h', 'peace-owned-lifecycle-1375.cpp',
               'default-contract.h', 'pins.h', 'test_contract.cpp', 'README.md']
    review = {'schema': 'owned_peace_lifecycle_review_v1', 'game_sha256': SHA,
              'compiled': False, 'linked': False, 'process_access': False, 'runtime_verified': False,
              'execution_verified': False,
              'evidence_sha256': hashlib.sha256(outputs['default-layout-evidence.json']).hexdigest(),
              'files': [{'path': name, 'sha256': hashlib.sha256((HERE / name).read_bytes()).hexdigest()} for name in sources]}
    raw = (json.dumps(review, indent=2) + '\n').encode()
    if args.check:
        if (HERE / 'review.json').read_bytes() != raw: raise ValueError('Review changed')
    else: (HERE / 'review.json').write_bytes(raw)
    print(json.dumps({'review_sha256': hashlib.sha256(raw).hexdigest(), 'evidence_sha256': review['evidence_sha256'],
                      'decoded_bytes': evidence['limits']['decoded_bytes'], 'check': args.check,
                      'compiled': False, 'process_access': False}))

if __name__ == '__main__': main()
