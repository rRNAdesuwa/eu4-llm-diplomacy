"""Bounded disk-only follow-up: candidate enumeration is not a pure constructor.

Reuse and byte-validate the prior 32 CFGs; decode only named downstream routines
and exact switch blocks. No process, build, hook, or engine call interface.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import tempfile
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/native-peace-candidate-boundaries-1375.json'
INPUTS = {
    'work/reports/native-peace-parameters-1375.json': '93dda3790212669bd227cc8a09b50685b6a502402f9a5677baf3e58d962c5677',
    'work/reports/native-action-fields-1375.json': 'cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96',
}
FUNCTIONS = [0x3d79f0, 0x798dc0, 0x7a73c0, 0x7ace30, 0x7b3950,
    0x45b6e0, 0xb22380, 0xd94740, 0x992930, 0x98d2a0, 0x97c300,
    0x36d120, 0xa6ad70, 0x14cf730, 0x1a334c0, 0x7a8090, 0x797e30,
    0x1a33458, 0x2f1c90, 0xd9f0b0, 0xd9a000, 0xd9a020, 0x129270,
    0x9b120, 0x8f440, 0x1a3514c]
BLOCKS = [(0x35a8f0, 0x35a983), (0x35ab1e, 0x35ab7c), (0x35be2e, 0x35be4f),
          (0x7b3973, 0x7b397f), (0x45b70d, 0x45b71d)]
SIX = [0x97cda0, 0x97d130, 0x97d4e0, 0x97e1f0, 0x97e500, 0x97db60]


def fact(summary, *rvas):
    return {'summary': summary, 'anchors': [hex(x) for x in rvas]}


FACTS = {
 'government_fallback_publishes_global': fact(
    '97d4e0 and97db60 read country+1420. If absent they call798dc0. '
    '798dc0 reads global233fe88; if null it allocates438 bytes, constructs a '
    'nogovernment object through797e30, installs1cb2240 and publishes the pointer '
    'to233fe88. This is an engine-global write outside the temporary offer. '
    '797e30 also calls170d410/95110/7ab450; their complete transitive effects are '
    'not established here. The getter contains no lock or pause check.',
    0x97d83a, 0x97d84c, 0x97de68, 0x97de7a, 0x798dc6, 0x798ddb,
    0x798e22, 0x798e61, 0x798e68, 0x798e6b, 0x797e61, 0x797edc, 0x797ef9),
 'secondary_fallback_can_replace_owned_global': fact(
    'If the preceding fallback result is null,97d4e0/97db60 call7a73c0. It reads '
    '242bc80 and lazily allocates8e8 bytes when empty.7a8090 publishes the new '
    'pointer and, when an old pointer exists, destroys embedded members and '
    'frees it. This is not caller-owned offer state. The syntactic null path '
    'is proven; normal successful798dc0 returns its constructed non-null object, '
    'so this report does NOT assert the secondary fallback occurs in ordinary '
    'successful enumeration. Constructor transitive effects remain open.',
    0x97d868, 0x97de8e, 0x97de9b, 0x7a73cc, 0x7a7506,
    0x7a8096, 0x7a809d, 0x7a80b0, 0x7a80b9, 0x7a80cb, 0x7a80d3, 0x7a80e5),
 'tls_is_a_real_thread_dependency_but_callback_range_empty': fact(
    '97e1f0/97e500 conditionally inspect TLS when byte233fed6 is nonzero. They '
    'select GS:[58] array element0, test its+c, call1a334c0 when zero, then '
    'test its+10 to gate candidate enumeration.1a334c0 tail-jumps1a33458(reason2), '
    'which writes byte TLS+c=1 using the module TLS index at233c574. The callers '
    'use literal index0 while the initializer reads that index variable; their '
    'runtime equality is not established here. Both callback range LEAs resolve to1b690e8 '
    'in this exact PE: the indirect callback body is not entered. TLS+10 is not '
    'initialized by this slice. Pausing a world does not establish the same TLS '
    'state on an arbitrary injected thread.',
    0x97e210, 0x97e219, 0x97e222, 0x97e22a, 0x97e230, 0x97e23a,
    0x97ea1a, 0x97ea3a, 0x1a334c0, 0x1a33458,
    0x1a33467, 0x1a33480, 0x1a33487, 0x1a3348c, 0x1a33493, 0x1a334ae),
 'token2940_exact_true_branch_is_read_only_in_closed_helpers': fact(
    '97d8c3 calls35a8f0(country,2940,other_handle,null,arg5=true,arg6=0). '
    'Index2940-28df=61 reads byte6 at35beed, then DWORD35be68=35ab1e. '
    'The true branch calls only3d79f0 and2f1c90; both read country/relation '
    'and dependency-definition fields. Stores on this closed branch are stack '
    'saves only. The false branch and other tokens are not traversed here; '
    'in particular unrelated233ff08 initialization in35a8f0 is not attributed '
    'to peace candidate enumeration. Country-slot bounds and epoch are not '
    'validated by these native helpers.',
    0x97d8a9, 0x97d8b2, 0x97d8c3, 0x35a956, 0x35a96f, 0x35a977,
    0x35ab1e, 0x35ab29, 0x35ab31, 0x35ab70, 0x3d79f0, 0x2f1c94),
 'government_boolean_variant_branch': fact(
    '7ace30 and the inline97db60 path normalize a variant type t to t or ~t. '
    'Their type check uses7b3950 and comparator1a3514c. Type0 resolves232e9c0, '
    'whose RTTI name is ._N (bool); comparison input is232e9c8. '
    '45b6e0 type0 returns variant+8 and callers read one byte. These closed '
    'type0 paths do not write the variant. Invalid types can enter127af0/int3; '
    'unexpected null boolean storage enters45b260/45b280/int3. This is a '
    'specific accepted representation, not a general variant purity proof.',
    0x7ace36, 0x7ace5f, 0x7ace6f, 0x7ace7b, 0x7ace8e,
    0x97dec0, 0x97ded0, 0x97dedc, 0x7b3967, 0x7b3973,
    0x45b701, 0x45b70d, 0x1a3514c),
 'province_script_evaluation_is_dynamic': fact(
    '97cda0 calls97c300 with null reason-output and flag false or true. '
    '97c300 resolves the current war and its effective war-goal definition '
    'through virtual78/70/58, with2340030 fallback goal. It builds stack '
    'country/province contexts (vt1c38158), uses province+20 and offer+taker, '
    'and evaluates condition pointers through virtual30. For the true flag '
    'the definition container is140 or378; for false it is50 or288; each has '
    'pointer at+8 and signed count at+14, stride8. Which side is used depends '
    'on taker membership in war sideA. Null reason-output does not bypass '
    'these script calls. The concrete trigger classes, nested scopes, caching '
    'or transitive writes cannot be inferred from this generic loop.',
    0x97ce62, 0x97ce6e, 0x97d055, 0x97c345, 0x97c388,
    0x97c399, 0x97c39e, 0x97c3b1, 0x97c3bb, 0x97c551,
    0x97c57e, 0x97c5b5, 0x97c5c5, 0x97c5ca, 0x97c5ea,
    0x97c6c3, 0x97c6fa),
 'dependency_script_evaluation_is_dynamic': fact(
    '97db60 callsb22380 on definition global233ffd8+80 with the taker full '
    'handle. b22380 constructs a stack country context, iterates definition '
    '+48 pointer / +54 signed DWORD count (8-byte condition pointers), '
    'invokes virtual30 and short-circuits false. Context cleanup releases '
    'owned scope allocations. No direct definition/country stores occur in '
    'the loop, but unreviewed trigger implementations remain a transitive '
    'world-write/reentrancy boundary. An observed zero count would skip '
    'this one loop only, not prove the whole offer constructor pure.',
    0x97ddf6, 0x97ddfd, 0x97de04, 0x97e092, 0xb22417, 0xb2241e, 0xb22422, 0xb22426, 0xb2243d,
    0xb22442, 0xb22460),
 'one_pinned_wargoal_virtual_family_is_closed': fact(
    'Prior action-fields identifies take_colony factory example vtable1d1fd90. '
    'Its58=9b120 returns this+10 definition;70=d9f0b0 performs world/province '
    'reads;78=8f440 returns true;d8=d9a000 copies this+1c to caller8B output; '
    'f8=d9a020 copies this+50..5f to caller16B output and returns RDX; '
    '108=129270 returns this+40 CB definition. These exact methods have no '
    'calls or non-output stores.97e500 passes stack wrappers to+f8, so '
    '97eaad/97ead1 writes update stack copies when this exact implementation '
    'is used.14cf730 only resolves the wrapper type/id against globals2340158 '
    '/2340160 without stores. Other vtables, including the fallback goal, '
    'must be independently pinned before borrowing this conclusion.',
    0x97ea94, 0x97ea9b, 0x97eaa8, 0x97eaad, 0x97eab8,
    0x97eabf, 0x97ead1, 0xd9a020, 0xd9a024, 0xd9a027,
    0x14cf730, 0x9b120, 0xd9f0b0, 0xd9a000, 0x129270),
 'diagnostic_logging_has_external_effects': fact(
    '97d4e0 and97db60 diagnose incompatible subjugation option pairs. They '
    'build streams, optionally lock global242b8c8 when byte2357b31 is set, '
    'write source peaceoffer.cpp and diagnostic text, then unlock/flush. '
    'The two literals identify BECOME_VASSAL with SUBJUGATE_VASSAL and '
    'BECOME_TRIBUTARY with SUBJUGATE_TRIBUTARY. Logging and its mutex '
    'are observable external effects; this mutex is not an engine lifecycle '
    'lock or proof all script/war accesses are synchronized.',
    0x97d629, 0x97d736, 0x97d75b, 0x97d76c, 0x97d79b,
    0x97dc5f, 0x97dd6c, 0x97dd91, 0x97dda2, 0x97ddd1),
 'temporary_collection_writes_must_not_be_confused_with_country_stores': fact(
    '36d120 reads country province/core data and allocates a deduplicated '
    'linked collection owned by its caller; stores target its destination '
    'header/new nodes.98d2a0 writes a caller-provided8B country-handle result, '
    'and delegates borrowed-war checks tod94740.97cda0 virtual10 at97cee7 '
    'is called on its stack vector object, not a province/country vtable. '
    'These alias distinctions do not close allocator/destructor implementations '
    'or all dynamic methods in the entire constructor.',
    0x36d120, 0x98d2cb, 0x98d2eb, 0x98d320, 0x98d337,
    0x98d418, 0x97cedf, 0x97cee3, 0x97cee7),
}

MATRIX = {
 '0x97cda0': ['97c300 dynamic war-goal / province script conditions', '98d2a0 output-only with d94740 virtual108 boundary', 'owned stack vector / new candidate allocations'],
 '0x97d130': ['borrowed war lookup97bd30', 'direct world reads and owned candidate allocations; no direct script/virtual calls in this CFG'],
 '0x97d4e0': ['government global lazy initialization', 'exact2940 true predicate closed', 'war-goal58/70/78/d8 and d94740 virtual108', 'diagnostic logger / lock', '992930 virtual58 plus unclosed direct helper edges'],
 '0x97e1f0': ['TLS+c initialization and TLS+10 gate', 'a6ad70 read-only leaf', 'owned candidate/list allocation and cleanup'],
 '0x97e500': ['TLS+c initialization and TLS+10 gate', '36d120 owned temporary collection', 'war-goal virtualf8 alias proven only for exact pinned example', '14cf730 read-only registry resolution'],
 '0x97db60': ['government global lazy initialization', 'type0 bool variant read path', 'b22380 dynamic dependency script conditions', 'war-goal58/70/78/d8 and d94740 virtual108', 'diagnostic logger / lock'],
}


def build():
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('wrong game build')
    imported = {}
    loaded = {}
    for path, expected in INPUTS.items():
        blob = (ROOT / path).read_bytes()
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError('input drift: ' + path)
        loaded[path] = json.loads(blob)
    prior = loaded[next(iter(INPUTS))]
    # Reuse, never re-decode, all 32 old CFGs; validate every recorded instruction.
    for key, f in prior['functions'].items():
        for ins in f['instructions']:
            raw = bytes.fromhex(ins['bytes'])
            if pe.bytes_at(int(ins['rva'], 16), len(raw)) != raw:
                raise ValueError('prior instruction drift: ' + ins['rva'])
        imported[key] = {'source': next(iter(INPUTS)), 'json_pointer': '/functions/' + key,
                         'instruction_count': len(f['instructions']), 'decoded_again': False}
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    functions = {}
    for entry in FUNCTIONS:
        window = 0x70 if entry == 0x1a33458 else 0x3000
        code, edges = bounded_cfg(pe, md, entry, window=window, max_instructions=3500)
        ins = rows(pe, code)
        functions[hex(entry)] = {'instructions': ins, 'edges': edges, 'window_bytes': window,
            'max_instructions': 3500, 'decoded_bytes': sum(len(bytes.fromhex(i['bytes'])) for i in ins),
            'coverage': 'bounded direct CFG; call targets not recursively followed; indirect exits explicit'}
        check_memory_budget()
    blocks = {}
    for start, end in BLOCKS:
        code = list(md.disasm(pe.bytes_at(start, end - start), start))
        if sum(x.size for x in code) != end-start:
            raise ValueError('block incomplete')
        blocks[hex(start)] = {'end_exclusive': hex(end), 'instructions': rows(pe, code), 'decoded_bytes': end-start}
    all_rows = {i['rva']: i for f in prior['functions'].values() for i in f['instructions']}
    all_rows.update({i['rva']: i for f in functions.values() for i in f['instructions']})
    all_rows.update({i['rva']: i for f in blocks.values() for i in f['instructions']})
    facts = {}
    for name, value in FACTS.items():
        facts[name] = dict(value, evidence=[all_rows[a] for a in value['anchors']], runtime_verified=False)
    def u32(rva): return struct.unpack('<I', pe.bytes_at(rva,4))[0]
    idx = 0x2940 - 0x28df
    sub = pe.bytes_at(0x35be8c + idx,1)[0]
    target = u32(0x35be50 + sub*4)
    assert (idx, sub, target) == (0x61, 6, 0x35ab1e)
    tables = {'token2940': {'index': idx, 'selector_rva': hex(0x35be8c+idx), 'selector': sub,
        'target_cell_rva': hex(0x35be50+sub*4), 'target_rva': hex(target)},
        'variant_type0': {'type_table_cell': '0x7b3a24', 'type_target': hex(u32(0x7b3a24)),
                         'value_table_cell': '0x45b760', 'value_target': hex(u32(0x45b760))}}
    assert u32(0x7b3a24) == 0x7b3973 and u32(0x45b760) == 0x45b70d
    vtable = {}
    expected_slots = {0x58:0x9b120,0x70:0xd9f0b0,0x78:0x8f440,0xd8:0xd9a000,0xf8:0xd9a020,0x108:0x129270}
    for slot, expected in expected_slots.items():
        raw = pe.bytes_at(0x1d1fd90+slot,8)
        assert struct.unpack('<Q',raw)[0]-pe.base == expected
        vtable[hex(slot)] = {'cell_rva':hex(0x1d1fd90+slot),'bytes':raw.hex(),'method_rva':hex(expected)}
    tls_begin = all_rows['0x1a3348c']['rip_target']
    tls_end = all_rows['0x1a33493']['rip_target']
    assert tls_begin == tls_end == '0x1b690e8'
    strings = {hex(a): pe.bytes_at(a,192).split(b'\0')[0].decode('ascii')
        for a in [0x1cb2108,0x1cd0f30,0x1cd0fa0,0x1cd1060,0x232e9d0]}
    count = sum(f['decoded_bytes'] for f in functions.values()) + sum(b['decoded_bytes'] for b in blocks.values())
    if count > 65536: raise ValueError('new decoded bytes exceed64KiB')
    edges = {hex(a): [{'rva':x['rva'],'instruction':x['instruction']} for x in prior['functions'][hex(a)]['instructions']
                     if x['instruction'].startswith('call ')] for a in SIX}
    return {'schema':'eu4.native.peace_candidate_boundaries/1','game_sha256':SHA,
        'runtime_verified':False,'constructor_pure':False,'parameter_selftest_ready':False,
        'engine_calls_performed':False,'inputs':INPUTS,'prior_cfg_reuse':imported,
        'facts':facts,'candidate_boundary_matrix':MATRIX,'direct_calls_from_six':edges,
        'functions':functions,'exact_blocks':blocks,'switch_evidence':tables,
        'take_colony_example_vtable':{'rva':'0x1d1fd90','scope':'single prior-pinned example, not all goals','slots':vtable},
        'tls_callbacks':{'begin_rva':tls_begin,'end_rva':tls_end,'count':0},'strings':strings,
        'minimum_preconditions_not_an_execution_gate':[
            'Pin exact build, instruction bytes and actual dynamic vtables; do not accept arbitrary war-goal/condition implementations.',
            'Bind real borrowed war, pair full handles, participants, country/province arrays and definitions to one stable world epoch; slot-only native lookups do not supply this.',
            'Observe native UI/game-thread provenance and its TLS+c/+10; paused alone is neither thread proof nor an engine lock.',
            'Prefer already initialized government objects and global fallbacks; reading non-null once does not prevent concurrent replacement or close constructor side effects.',
            'Snapshot the selected war-goal/dependency condition vectors with strict count/identity bounds. Zero counts skip specific loops only. Nonempty lists need concrete transitive trigger review.',
            'Treat logging, allocations, lazy globals and TLS writes as allowed-or-rejected explicit effects. No rollback or exception-safe recovery of partially constructed offers is established by this report.',
            'Before proposing an executable selftest, close remaining dynamic classes and helper edges, arrange non-reentrant same-world lifetime protection, then review bounded owner cleanup. Do not invoke any sender or peace effect.'
        ],
        'unresolved':[
            'No full-program thread/lifecycle synchronization proof; normal GUI call provenance does not prove all callees execute only on one thread.',
            'Concrete runtime script conditions, fallback war-goal vtable and other goal subclasses not inventoried here.',
            'Opaque direct helpers such as allocator/container/stream internals,170d410,7ab450,7b23e0,7a15b0,98840,d94380,3d7b60,d8fcc0 remain transitive boundaries.',
            'No observation of current cache/TLS/war/condition state; no claim a given save reaches any particular branch.',
            'Original constructor also invokes paths outside these six generators; this finite follow-up does not establish whole-constructor purity or safe execution.'
        ],
        'limits':{'new_decoded_bytes':count,'new_decoded_ceiling':65536,'prior_cfg_count_reused':len(imported),
                  'memory_guard_bytes':768*1024*1024,'hard_memory_ceiling_bytes':1024*1024*1024}}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    result=build();blob=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if args.check:
        if OUT.read_bytes()!=blob: raise SystemExit('report differs')
    else: OUT.write_bytes(blob)
    print(json.dumps({'report':str(OUT),'sha256':hashlib.sha256(blob).hexdigest(),
        'bytes':len(blob),'new_decoded_bytes':result['limits']['new_decoded_bytes'],
        'prior_cfg_reused':len(result['prior_cfg_reuse']),'peak_commit_bytes':check_memory_budget(),
        'check':args.check,'runtime_verified':False}))


if __name__=='__main__':main()
