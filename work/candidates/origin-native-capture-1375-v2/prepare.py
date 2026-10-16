"""Bounded disk-only site pins and source manifest. Never builds or opens a process."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = ROOT / 'work/candidates/origin-native-capture-1375'
PARENT_REVIEW_SHA = 'dccb4fdf9b0411b327637e49969860922d13ffd3905f2e3f2d0fda5d05ebaa15'
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, make_disassembler, check_memory_budget
from map_diplomacy_fields import SHA

INPUTS = {
    'work/candidates/origin-witness-observer-1375/observer.py': '8baef67aa4d4aa24eeff4eab18de18c56d6e140b7a4d0c897c3ac38a5f9752d4',
    'work/reports/native-origin-witness-observer-1375.json': '1a6808bfe956d7738b1498fd693b099de9acd276a340deb4c93e3f83a0c03517',
    'work/reports/native-epoch-sp-closure-1375.json': '24e112d11e0c3252ce70e1641b835ce160863e3bc72faa13d2b1f44a92662808',
    'work/reports/native-single-player-context-1375.json': '0943d8f4b142daf260cbc4ea407fe4b05d6ad9898aa6c40ba44dc25788162bbf',
}
STORE_CALL_ANCHORS = (
    0x1120f86, 0x1120ff6, 0x1121004, 0x1121685,
    0x10dae6c, 0x10dae97, 0x10dae9c, 0x10daead, 0x10daede,
    0x803d19, 0x803d20, 0x803d27, 0x6e8c15,
    0x14c2542, 0x14c2546, 0x14c2556, 0x14c2559, 0x14c2560,
    0x14c2563, 0x14c2573, 0x14c2575, 0x14c258c,
    0x811add, 0x811afa, 0x14c8969, 0x14c92be, 0x14c92cf,
    0x14c9831, 0x14c9837, 0x14c983d, 0x14c9842, 0x14c9853,
    0x14c98a4, 0x14c98a8,
)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def generate():
    parent_raw = (PARENT/'review.json').read_bytes()
    if digest(parent_raw) != PARENT_REVIEW_SHA: raise ValueError('Parent review changed')
    for name,expected in json.loads(parent_raw)['files'].items():
        if digest((PARENT/name).read_bytes()) != expected: raise ValueError('Parent source changed')
    loaded = {}
    for path, expected in INPUTS.items():
        raw = (ROOT / path).read_bytes()
        if len(raw) > 2 * 1024 * 1024 or digest(raw) != expected:
            raise ValueError('Pinned input changed: ' + path)
        loaded[path] = raw
    syntax = ast.parse(loaded[next(iter(INPUTS))].decode())
    maps = {}
    for statement in syntax.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            name = getattr(statement.targets[0], 'id', '')
            if name in ('SITES', 'REVOKERS'): maps[name] = ast.literal_eval(statement.value)
    if set(maps) != {'SITES', 'REVOKERS'}: raise ValueError('Observer map shape changed')
    enum_text = (HERE / 'capture-core.h').read_text().split('enum class Site : std::uint16_t {',1)[1].split('};',1)[0]
    names = [name.strip() for name in enum_text.split(',') if name.strip()]
    observed = maps['SITES'] | maps['REVOKERS']
    if names[0] != 'none' or names[-1] != 'count' or set(names[1:-1]) != set(observed):
        raise ValueError('Native site enumeration differs from final observer')
    pe = PE(ROOT.parent / 'eu4.exe')
    if digest(pe.data) != SHA: raise ValueError('Wrong executable')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    if md is None: raise ValueError('Capstone unavailable')
    cards, decoded = [], 0
    for ordinal, name in enumerate(names[1:-1], 1):
        rva = observed[name]
        pdata = pe.function(rva)
        limit = min(48, pdata[1] - rva) if pdata is not None and pdata[0] == rva else 48
        instructions = []
        for ins in md.disasm(pe.bytes_at(rva, limit), rva, count=16):
            instructions.append({'rva':hex(ins.address),'bytes':ins.bytes.hex(),
                                 'instruction':ins.mnemonic + ' ' + ins.op_str})
            if ins.address + ins.size >= rva + 32 or ins.mnemonic in ('ret','retf','jmp','int3','ud2'): break
        size = sum(len(bytes.fromhex(row['bytes'])) for row in instructions)
        if size == 0 or size > 47: raise ValueError('Invalid bounded instruction prefix')
        decoded += size
        cards.append({'ordinal':ordinal, 'name':name, 'rva':hex(rva),
            'roles': [role for role, mapping in (('origin_scope',maps['SITES']),('invalidate_entry',maps['REVOKERS'])) if name in mapping],
            'pdata':None if pdata is None else list(map(hex,pdata)),
            'prefix32':pe.bytes_at(rva,32).hex(), 'whole_instruction_prefix':instructions,
            'decoded_prefix_bytes':size, 'identity_pin_extends_past_decoded_prefix':size < 32,
            'entry_matches_pdata_start':pdata is not None and pdata[0] == rva,
            'prefix_is_patch_plan':False, 'entry_patch_supported':False,
            'return_capture_supported':False, 'trampoline_implemented':False,
            'unresolved':['instruction relocation and branch targets','live register/XSTATE preservation',
                          'unwind and exceptional/tail returns','safe installation and teardown/thread quiescence']})
    # Reuse exact full-instruction evidence already decoded in the fixed report.
    rows = {}
    for name,raw in loaded.items():
        if not name.endswith('.json'): continue
        report = json.loads(raw)
        rows.update({int(row['rva'],16):row for row in report.get('selected_prior_anchors',[])})
        for function in report['functions'].values():
            rows.update({int(row['rva'],16):row for row in function['instructions']})
    anchors = []
    for rva in STORE_CALL_ANCHORS:
        row = rows[rva]
        if pe.bytes_at(rva,len(bytes.fromhex(row['bytes']))) != bytes.fromhex(row['bytes']):
            raise ValueError('Anchor bytes changed')
        anchors.append(row | {'inline_patch_supported':False})
    return_sites = []
    for call, result in ((0x10daead,0x10daeb2),(0x803d27,0x803d2c)):
        row = rows[call]
        if not row['instruction'].startswith('call ') or call + len(bytes.fromhex(row['bytes'])) != result:
            raise ValueError('Call/normal return relationship changed')
        return_sites.append({'call_rva':hex(call),'normal_return_rva':hex(result),
                             'bytes_at_normal_return':pe.bytes_at(result,16).hex(),
                             'use':'caller identity only; not a return detour plan',
                             'capture_supported':False})
    if decoded > 4096: raise ValueError('Decode budget exceeded')
    check_memory_budget()
    evidence = {'schema':'origin_native_capture_candidate_v2','game_sha256':SHA,'inputs':INPUTS,
        'parent_review_sha256':PARENT_REVIEW_SHA,
        'sites':cards,'store_call_anchors':anchors,'normal_return_identity_sites':return_sites,
        'frame_snapshot_site':{'rva':'0x10a6ec0','scope':'entry before native callbacks',
                               'memory_read_adapter_implemented':False,'engine_lifetime_safe':False},
        'record_layout':{'header_bytes':64,'payload_bytes':328,'record_bytes':392,
                         'payload_scalar_slots':40,'payload_presence_bits':64,
                         'ring_slots':256,'capture_storage_compile_assert_max_bytes':131072},
        'concurrency':{'producer':'MPSC, one reservation CAS attempt; failure terminal',
                       'consumer':'exactly one, strict ticket order',
                       'publication':'release ready ticket / acquire read',
                       'reuse':'release tail / acquire capacity check',
                       'missing_ticket_timeout_ms':50,'wait_or_spin_in_hook':False,
                       'loss_record':'out-of-band packed first fault and terminal epoch'},
        'boundaries':{'core_implements_hook':False,'register_reader_implemented':False,
                       'event_exporter_implemented':False,'trusted_binding_classifier_implemented':False,
                       'world_snapshot_reader_implemented':False,'origin_reducer_native_port_implemented':False,
                       'production_ready':False,'strict_single_player':False,'engine_lifetime_synchronized':False},
        'validation':{'compiled':False,'synthetic_cpp_executed':False,'linked':False,
                      'hook_installed':False,'game_process_accessed':False},
        'limits':{'site_count':len(cards),'new_prefix_decoded_bytes':decoded,'decode_limit_bytes':4096,
                  'memory_guard_mib':768,'previous_anchor_count':len(anchors)}}
    header = ['#pragma once','#include <cstdint>','#include <cstddef>',
              '// Build identity data only. NONE of these spans is an approved patch length.',
              'namespace eu4_origin_capture_1375::pins {',
              'struct Pin { std::uint16_t site; std::uintptr_t rva; unsigned char bytes[32]; };',
              'constexpr Pin entries[] = {']
    for card in cards:
        values = ','.join(f'0x{byte:02x}' for byte in bytes.fromhex(card['prefix32']))
        header.append(f'    {{{card["ordinal"]}, {card["rva"]}, {{{values}}}}},')
    header += ['};','constexpr bool any_entry_patch_supported = false;','}', '']
    return evidence, '\n'.join(header).encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    evidence,pins = generate()
    outputs = {'sites.json':(json.dumps(evidence,indent=2)+'\n').encode(),'pins.h':pins}
    for name, raw in outputs.items():
        path = HERE / name
        if args.check:
            if path.read_bytes() != raw: raise ValueError('Generated file differs: ' + name)
        else: path.write_bytes(raw)
    files = ['capture-core.h','capture-core.cpp','test_capture_core.cpp','prepare.py','README.md','pins.h','sites.json']
    review = {'schema':'origin_native_capture_review_v2','files':{name:digest((HERE/name).read_bytes()) for name in files},
              'parent_review_sha256':PARENT_REVIEW_SHA,
              'source_validation':'disk-only; C++ synthetic source NOT built or executed',
              'site_count':evidence['limits']['site_count'],'prefix_decoded_bytes':evidence['limits']['new_prefix_decoded_bytes'],
              'synthetic_cpp_test_groups':10,'synthetic_cpp_executed':False,
              'compiled':False,'linked':False,'game_process_accessed':False,'production_ready':False,
              'strict_single_player':False,'engine_lifetime_synchronized':False}
    raw = (json.dumps(review,indent=2)+'\n').encode()
    if args.check:
        if (HERE/'review.json').read_bytes() != raw: raise ValueError('Review manifest changed')
    else: (HERE/'review.json').write_bytes(raw)
    print(json.dumps({'review_sha256':digest(raw),'sites_sha256':digest(outputs['sites.json']),
                      'check':args.check,'site_count':review['site_count'],
                      'prefix_decoded_bytes':review['prefix_decoded_bytes'],
                      'compiled':False,'game_process_accessed':False}))

if __name__ == '__main__': main()
