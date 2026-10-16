"""Disk-only, bounded evidence for war-bound peace offers and native reset.

No process API, native invocation, injection, build, or sender.  Calls are not
recursively followed.  The formatter is deliberately only a prefix CFG.
"""
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
OUTPUT = ROOT / 'work/reports/native-peace-parameters-1375.json'
INPUTS = (
    ('work/reports/native-owned-peace-1375.json', 'f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d'),
    ('work/reports/native-peace-gui-send-1375.json', '1aa1be072578a2c3f21e432ba6c0928ab01d9920d85063060a91512e9a882b64'),
    ('work/reports/native-action-fields-1375.json', 'cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96'),
    ('work/runtime/unpacked-1.37.5/base/interface/peaceview.gui', '821c09cc2cc83dd1239a6a2fe0302f1cca74210b5619448dc85b974c80980e18'),
)
# entry, window, maximum instructions.  No whole-program disassembly.
ENTRIES = [(a, 0x3000, 3000) for a in (
    0x975d40, 0x97bd30, 0x97bea0, 0x978cd0,
    0x97a790, 0x97a670, 0x97a8d0, 0x97ae50,
    0x97b390, 0x97b2c0, 0x97b7b0, 0x97b8a0, 0x981b30,
    0x99aff0, 0x9b4140, 0x9b41b0, 0x9b43f0, 0x9b4440,
    0x59ae00, 0x59b450, 0x1306a10, 0x28d990, 0x97bda0, 0xd8fd60,
    0x97cda0, 0x97d130, 0x97d4e0, 0x97e1f0, 0x97e500, 0x97db60,
)] + [(0x97ed00, 0x3000, 3000), (0x9851f0, 0x6a0, 900)]


def fact(summary, *anchors):
    return {'summary': summary, 'anchors': anchors}


FACTS = {
    'constructor_abi_and_sequence': fact(
        '975d40 is an in-place constructor: RCX=unconstructed 0x1c0 destination, RDX=taker full handle, R8=giver full handle, R9B=is_demand. It sets giver+10/taker+18/demand+20, initializes owned containers through2c67a0, sets flags1b8=0/1b9=1, resolves participants97bea0, constructs40 type buckets, initializes auxiliary state978cd0, then enumerates candidate components97ed00. There is no war pointer, war ID or date argument in this signature.',
        0x975d5d, 0x975d60, 0x975d67, 0x975d71, 0x975d75, 0x975d79,
        0x975e0e, 0x975e14, 0x975e20, 0x975e44, 0x975ed2, 0x975ef0,
        0x975ef3, 0x975ef7, 0x975efb, 0x975f0c, 0x975f14, 0x975f1a),
    'pair_war_lookup_is_borrowed_and_slot_based': fact(
        '97bd30 uses signed16(slot(handle>>32)) for taker and giver. It indexes database233d8d0+118 for taker, then taker+1510+giver_slot*48. That 48-byte relation entry contains root at+0 and counterpart full handle at+10. It scans root+50 with signed DWORD count root+5c in16-byte records, compares record DWORD+0 to the counterpart signed slot, and returns first matching record QWORD+8, otherwise null. It does not compare full handles, bound indices, prove uniqueness, pin an epoch, or copy/own the war object. The key here is a country slot, NOT a recovered numerical war ID.',
        0x97bd30, 0x97bd34, 0x97bd38, 0x97bd3c, 0x97bd40, 0x97bd47,
        0x97bd4b, 0x97bd52, 0x97bd56, 0x97bd5a, 0x97bd5e, 0x97bd65,
        0x97bd69, 0x97bd73, 0x97bd77, 0x97bd7b, 0x97bd87, 0x97bd94, 0x97bd97),
    'generic_index_lookup_matches_inline_lookup': fact(
        '28d990(RCX=root+48,RDX=counterpart handle) performs the same16-byte-array lookup using wrapper+8/root+50 and wrapper+14/root+5c. The peace text formatter9851f0 obtains its war through that helper, separately from offer construction. This closes two uses of the same relation index; neither turns its record key into a war ID.',
        0x28d990, 0x28d994, 0x28d998, 0x28d99c, 0x28d99f, 0x28d9b0,
        0x28d9bd, 0x28d9c0, 0x985240, 0x98525e, 0x985266, 0x98526d,
        0x985271, 0x985275, 0x98527a, 0x985283),
    'war_sides_and_negotiating_participants': fact(
        '97bea0 calls97bd30. With a non-null war it tests taker slot membership in war+48..50 (side A,8-byte full handles). If present, offer.war_givers+28 copies war side B+78 and war_takers+40 copies A; otherwise orientation reverses. Actual takers+70 include the complete taker-side vector when taker matches its first element; otherwise taker itself plus same-side direct subjects whose dependency definition+121 is nonzero. Actual givers+58 follow the same rule on the opposite side. Member comparison is slot-only; vectors retain full8-byte handles. These slices do not independently establish attacker/defender names or a stable serialized war identity.',
        0x97beaa, 0x97beb5, 0x97bebb, 0x97bec8, 0x97bef0, 0x97bef7,
        0x97bf0f, 0x97bf1e, 0x97bf23, 0x97bf31, 0x97bf3c, 0x97bf41,
        0x97bf51, 0x97bf91, 0x97bf9b, 0x97bfa9, 0x97bfac, 0x97bfb3,
        0x97bff0, 0x97c013, 0x97c076, 0x97c09b, 0x97c0a2, 0x97c0d8,
        0x97c0ea, 0x97c105, 0x97c112, 0x97c11b, 0x97c147, 0x97c14e,
        0x97c180, 0x97c1a0, 0x97c202, 0x97c227, 0x97c264, 0x97c26e, 0x97c282),
    'missing_war_is_not_constructor_failure': fact(
        'If lookup is null,97bea0 merely appends giver to actual_givers and returns; it does not fabricate complete war sides or set an error result.97ed00 also returns immediately on null war. Thus a non-null returned offer pointer, valid vtable, initialized containers or init flag do not establish a currently valid war-bound proposal.',
        0x97beb5, 0x97c2b9, 0x97c2bd, 0x97c2cb, 0x97c2ce, 0x97c2e3,
        0x97ed33, 0x97ed38, 0x97ed3b, 0x981118, 0x981132),
    'auxiliary_state_depends_on_live_country_data': fact(
        '978cd0 builds a temporary union-like handle collection from actual_givers, war_givers and each actual giver country+1a18..1a20, de-duplicates by signed country slot, and initializes offer+e8 state with99d920(country handle) and99d9d0(DWORD IDs from country+1338/count1344 and country+9a78 secondary list). It finally sets offer+1b8=1. This flag marks completion of this auxiliary pass, not evidence of a valid war. The domain names of all auxiliary records and all transitive helper side effects remain unclosed.',
        0x978d1d, 0x978d25, 0x978d40, 0x978d44, 0x978d53,
        0x978d99, 0x978da0, 0x978dab, 0x978db9, 0x978dff, 0x978e17,
        0x978ef2, 0x978ef8, 0x978f13, 0x978f1a, 0x978f33, 0x978f38,
        0x978f46, 0x978f52, 0x978f56, 0x978fb3, 0x978fe3),
    'candidate_pool_and_selected_index_are_different': fact(
        '97ed00 calls six world-dependent candidate helpers and allocates candidate components into owned offer+88. Direct component constructors here and in those helpers write selected byte+20=0; the full candidate pool must not be interpreted as enacted or selected treaty terms. Candidate helpers themselves call country/war/script/virtual methods, retained as unresolved call edges rather than declared pure. At the end97ed00 allocates a distinct po_gold component and explicitly selects it.',
        0x97ed44, 0x97ed4c, 0x97ed54, 0x97ee55, 0x97ee68, 0x97eea2,
        0x97eeaa, 0x97ef10, 0x980d8d, 0x97cf7b, 0x97d098, 0x97d437,
        0x97dab8, 0x97e3ee, 0x97eb2a, 0x97e10d, 0x981089, 0x981112),
    'constructor_selects_zero_gold': fact(
        'The final component has vt1cd2440 (pinned po_gold), size38, giver/taker full handles+10/+18, selected0 at first, affected-country handle+22=giver, and signed value+30=0. The zero is proven by all three reaching R15 definitions in the bounded CFG, not only the lexically nearest xor.97a790 sets selected+20=1, retrieves descriptor(type0,definition0) through99aff0, appends the pointer to type bucket0, and calls component virtual118 to update auxiliary offer state. Default war-bound construction therefore has a selected zero-money component; empty +88 or zero selected count is the wrong white-peace contract.',
        0x9803c5, 0x980453, 0x980b90, 0x981089, 0x98109d, 0x9810a1,
        0x9810ac, 0x9810b0, 0x9810b4, 0x9810b8, 0x9810bc, 0x9810c6,
        0x981106, 0x981109, 0x981112, 0x97a7ab, 0x97a7ce, 0x97a7d1,
        0x97a7d3, 0x97a7de, 0x97a7ed, 0x97a81b, 0x99aff0, 0x99aff2, 0x99aff4),
    'native_reset_binding_and_semantics': fact(
        'peaceview.gui reset_button binds GUI+3f8 listener, whose owner+400 and callback+408 point to GUI/1306a10. That callback selects GUI+48 or+208 by+660 and calls97ae50. Reset gathers selected components via97b7b0, deselects every descriptor other than(type0,definition0) via97a8d0, then calls97b390 with a pointer to DWORD0. It preserves the money component and sets its value to zero with auxiliary undo/reapply virtual118 calls. This is the normal UI reset contract, not authorization to memset vectors or delete every candidate.',
        0x1309459, 0x1309460, 0x1309467, 0x130946e, 0x130a076,
        0x130a07d, 0x130a084, 0x130a0b4, 0x130a0b7, 0x1306a23,
        0x1306a2a, 0x1306a30, 0x97ae94, 0x97aec1, 0x97aec6,
        0x97aed9, 0x97aee7, 0x97aefd, 0x97b810, 0x97a8e4,
        0x97a921, 0x97b3fb, 0x97b405, 0x97b412, 0x97b42c, 0x97b435, 0x97b44d),
    'native_white_peace_predicate_is_not_empty_vector': fact(
        '981b30(offer,false) first reads effective money through97b2c0 and rejects positive values. It enumerates registry242bd80 descriptors through97b8a0 and allows selected descriptor type0; every other type rejects when its second argument is false. The true variant additionally permits type0xb, which this report does not treat as ordinary white peace. The formatter9851f0 calls this predicate with false and can select literal WHITE_PEACE at1cd1360; a separate war+18 branch produces another special-case text. This is a display/predicate link, not an acceptance or application test. A conservative minimal contract uses exactly one selected type0/definition0/value0 and zero other effective selections, stronger than the native predicate that also allows nonpositive/ambiguous money results.',
        0x981b49, 0x981b57, 0x981b5c, 0x981b61, 0x981b8f,
        0x981bae, 0x981bbe, 0x981bf0, 0x981bf2, 0x981bf4, 0x981bf9,
        0x981bfc, 0x981c12, 0x981c1c, 0x97b324, 0x97b333, 0x97b34b,
        0x985340, 0x985345, 0x98534c, 0x985360, 0x985365, 0x98565a),
    'effective_selection_includes_overlay_vectors': fact(
        '97b8a0(...,include_overlays=true) starts from type buckets+d0, includes matching pointers in+a0 and removes pointers in+b8. A scripted descriptor with non-null definition uses type39 bucket and filters component+30 by definition identity. Therefore checking only component+20 or only bucket0 is insufficient when overlays are nonempty. Reset and white-peace predicate use this effective-selection helper. The borrowed aliases in these indexes are not independent component owners.',
        0x97b8c9, 0x97b8d2, 0x97b8e6, 0x97b90f, 0x97b96c,
        0x97b997, 0x97b9a1, 0x97ba21, 0x97ba98, 0x97bac5,
        0x97bb21, 0x97bb30, 0x97bb47, 0x97bb89, 0x97bb8c,
        0x97bc34, 0x97bc3c, 0x97bc43, 0x97bc47),
    'direction_and_cache_are_native_gui_inputs': fact(
        'Actor A and recipient B remain unchanged in the outer request. Demand uses975d40(dst,A,B,true): giver B,taker A,sourceGUI+48. Offer uses975d40(dst,B,A,false): giver A,taker B,sourceGUI+208. GUI maintains separate cached vectors at+3c8/+3e0, stride1c0, matched only by selected target slot; it can deep-copy previous selected terms instead of constructing fresh offers. Copying a cached GUI offer does not establish a reset/zero-terms proposal.',
        0x13067d5, 0x13067fb, 0x1306805, 0x1306847, 0x1306857,
        0x1306863, 0x1306866, 0x1306871, 0x13068a9, 0x13068b2,
        0x13068e9, 0x13068f8, 0x130690a, 0x1306911, 0x1306947,
        0x1306962, 0x1306965, 0x1306970, 0x130699d, 0x13069a9),
    'date_and_owner_are_outer_request_properties': fact(
        'GUI send obtains current raw date from game+1dd0, passes it as constructor argument6, and598af0 stores it at request+28/+2c. It deep-copies source offer to request+48; wrapper4e9930 independently clones that request and refreshes clone+2c before command+50 takes ownership. CPeaceOffer constructor has no date or owned war object field established here. Cloning participants and terms does not freeze the relation-index war identity subsequently resolved by legality.',
        0x130f1d8, 0x130f1df, 0x130f217, 0x130f21e, 0x130f228,
        0x130f22f, 0x598b04, 0x598b08, 0x598b0c, 0x598b21,
        0x598b26, 0x598b45, 0x598b4a, 0x4e9940, 0x4e9957,
        0x4e995c, 0x4e9991),
    'legality_resolves_war_again_and_has_independent_rejections': fact(
        '59b450 independently resolves actor->recipient relation-index war; null/missing pointer returnsfalse. It calls59ae00(actor,target,war,reasons,early_return_flag), then additional component/province checks and base legality4ebdb0.59ae00 contains native refusal texts for unconditional surrender, forbidden separate peace(subject/overlord/coalition), lesser-partner peace and succession separate peace. Those are independent of the zero-terms predicate. Full current handles, correct direction and reset terms do not prove legality, AI agreement or final execution.',
        0x59b4b1, 0x59b4b5, 0x59b4c7, 0x59b4d2, 0x59b4f1,
        0x59b4f5, 0x59b50f, 0x59b545, 0x59b5d0,
        0x59b0ac, 0x59b10b, 0x59b183, 0x59b1c9, 0x59b1ed,
        0x59b212, 0x59b231, 0x59b2c3, 0x59b35c, 0x59b3c4),
}


def scalar_reaching_definitions(function, target):
    """Exact intra-CFG backwards check for the final nonvolatile R15 value.

    Does not symbolically execute calls or treat an ABI as runtime verified.
    Explicitly rejects indirect control transfer in this chosen function.
    """
    instructions = function['instructions']
    nodes = {int(x['rva'], 16): x for x in instructions}
    predecessors = {a: [] for a in nodes}
    for address, row in nodes.items():
        mnemonic = row['instruction'].split()[0]
        destinations = []
        if mnemonic not in ('ret', 'retf', 'int3', 'ud2'):
            if mnemonic.startswith('j'):
                value = row['instruction'].split()[-1]
                if not value.startswith('0x'):
                    raise ValueError('Reaching-definition function has an indirect branch')
                destinations.append(int(value, 16))
                if mnemonic != 'jmp':
                    destinations.append(address + len(bytes.fromhex(row['bytes'])))
            else:
                destinations.append(address + len(bytes.fromhex(row['bytes'])))
        for destination in destinations:
            if destination in predecessors:
                predecessors[destination].append(address)
    pending = predecessors[target][:]
    seen = set(); definitions = []
    while pending:
        address = pending.pop()
        if address in seen:
            continue
        seen.add(address)
        ins = nodes[address]['instruction']
        if ins.startswith(('mov r15,', 'mov r15d,', 'xor r15d,', 'lea r15,', 'pop r15')):
            definitions.append(nodes[address])
        else:
            if not predecessors[address]:
                raise ValueError('Reached entry without a definition')
            pending.extend(predecessors[address])
    definitions.sort(key=lambda row: int(row['rva'], 16))
    if [row['rva'] for row in definitions] != ['0x9803c5', '0x980453', '0x980b90']:
        raise ValueError('Unexpected reaching definitions')
    if any(row['instruction'] != 'xor r15d, r15d' for row in definitions):
        raise ValueError('Money zero is not proven')
    return {'register': 'r15d', 'target_store_rva': hex(target), 'all_definitions': definitions,
            'value': 0, 'scope': 'bounded direct CFG; Win64 nonvolatile register convention; not runtime execution'}


def generate():
    inputs = []; previous = {}
    for name, expected in INPUTS:
        path = ROOT / name
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Input size limit')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned input changed: ' + name)
        inputs.append({'path': name, 'sha256': expected})
        if name.endswith('.json'):
            obj = json.loads(raw)
            for key, function in obj.get('functions', {}).items():
                for row in function['instructions']:
                    previous[row['rva']] = (name, key, row)
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Executable identity mismatch')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    functions = {}; decoded = 0
    for entry, window, instruction_limit in ENTRIES:
        code, edges = bounded_cfg(pe, md, entry, window=window, max_instructions=instruction_limit)
        size = sum(ins.size for ins in code); decoded += size
        if decoded > 64 * 1024 or len(functions) >= 40:
            raise ValueError('Decode/function limit')
        encoded = rows(pe, code)
        functions[hex(entry)] = {
            'pdata_fragment': list(map(hex, pe.function(entry) or ())),
            'window_bytes': window, 'max_instructions': instruction_limit,
            'decoded_bytes': size, 'prefix32_hex': pe.bytes_at(entry, 32).hex(),
            'instructions': encoded, 'edges': edges,
            'calls': [x for x in encoded if x['instruction'].startswith('call ')],
            'coverage': 'bounded_direct_CFG_calls_not_followed',
        }
        check_memory_budget()
    lookup = {row['rva']: row for f in functions.values() for row in f['instructions']}
    facts = {}
    for name, value in FACTS.items():
        evidence = []
        for address in value['anchors']:
            key = hex(address)
            if key in lookup:
                row = dict(lookup[key]); row['source'] = 'this_report'
            else:
                source, function, original = previous[key]
                row = dict(original); row['source'] = source
                row['json_pointer'] = '/functions/' + function + '/instructions'
            raw = bytes.fromhex(row['bytes'])
            if pe.bytes_at(address, len(raw)) != raw:
                raise ValueError('Evidence bytes mismatch: ' + key)
            evidence.append(row)
        facts[name] = {'summary': value['summary'], 'runtime_verified': False, 'instructions': evidence}
    vtable = 0x1cd2440
    slots = {0x50: 0x8f450, 0x78: 0x99aff0, 0x118: 0x9b4140, 0x120: 0x9b41b0}
    for slot, expected in slots.items():
        if pe.u64(pe.to_offset(vtable + slot)) - pe.base != expected:
            raise ValueError('Money method mismatch')
    strings = {}
    for key in ('0x130a07d', '0x98565a'):
        row = next(x for f in facts.values() for x in f['instructions'] if x['rva'] == key)
        address = int(row['rip_target'], 16)
        strings[hex(address)] = pe.bytes_at(address, 80).split(b'\0')[0].decode('ascii')
    if set(strings.values()) != {'reset_button', 'WHITE_PEACE'}:
        raise ValueError('Source string mismatch')
    definitions = scalar_reaching_definitions(functions['0x97ed00'], 0x9810c6)
    field_sources = [
        {'object': 'offer', 'offset': '+10/+18', 'width': 'QWORD each', 'source': '975d40 R8=giver / RDX=taker; full handles', 'fact': 'constructor_abi_and_sequence'},
        {'object': 'offer', 'offset': '+20', 'width': 'BYTE', 'source': '975d40 R9B; native direction', 'fact': 'direction_and_cache_are_native_gui_inputs'},
        {'object': 'offer', 'offset': '+28/+40', 'width': '24-byte vectors of8-byte handles', 'source': 'borrowed war side vectors+48/+78 oriented by taker membership', 'fact': 'war_sides_and_negotiating_participants'},
        {'object': 'offer', 'offset': '+58/+70', 'width': '24-byte vectors of8-byte handles', 'source': 'leader/all-side versus negotiator/qualifying direct subjects', 'fact': 'war_sides_and_negotiating_participants'},
        {'object': 'offer', 'offset': '+88', 'width': '24-byte owning pointer vector', 'source': 'candidate terms; selected byte is per component+20', 'fact': 'candidate_pool_and_selected_index_are_different'},
        {'object': 'offer', 'offset': '+a0/+b8/+d0', 'width': 'borrowed aliases in owned vector buffers', 'source': 'effective selection overlay and per-type index', 'fact': 'effective_selection_includes_overlay_vectors'},
        {'object': 'offer', 'offset': '+e8 / +1b8 / +1b9', 'width': 'ownerQWORD / BYTE / BYTE', 'source': 'owned lifecycle self-pointer / auxiliary initialized / apply_penalties=1', 'fact': 'auxiliary_state_depends_on_live_country_data'},
        {'object': 'po_gold', 'offset': '+20/+30', 'width': 'BYTE/DWORD', 'source': 'selected1; value0 after parameter construction/reset', 'fact': 'constructor_selects_zero_gold'},
        {'object': 'requestpeace', 'offset': '+10/+18/+20/+28/+2c/+41/+48', 'width': 'threeQWORD/twoDWORD/BYTE/embedded1c0', 'source': 'actor/originalactor/recipient/currentdate/currentdate/demand/deep-copyoffer', 'fact': 'date_and_owner_are_outer_request_properties'},
    ]
    return {
        'schema': 'native_peace_parameters_1375_v1', 'game_sha256': SHA,
        'runtime_verified': False, 'execution_verified': False, 'sender_implemented': False,
        'inputs': inputs, 'facts': facts, 'field_sources': field_sources,
        'functions': functions, 'money_vtable': {'rva': hex(vtable), 'name': 'po_gold',
            'slots': {hex(k): hex(v) for k, v in slots.items()}},
        'strings': strings, 'money_zero_reaching_definitions': definitions,
        'bounded_minimum_contract': {
            'status': 'static proposal for future observation; not callable API or proven accepted treaty',
            'outer_actor_target': 'A=current authorized actor full handle; B=recipient full handle',
            'demand': {'constructor_args': ['destination', 'A', 'B', True], 'giver': 'B', 'taker': 'A'},
            'offer': {'constructor_args': ['destination', 'B', 'A', False], 'giver': 'A', 'taker': 'B'},
            'war': 'borrowed current pair lookup must exist; current-world full handles/sides/roles must be independently checked',
            'terms': 'exactly one effective selected po_gold descriptor(type0,definition0), value0; no other effective selections; aliases/owned storage remain intact',
            'date': 'outer request current game+1dd0, refreshed cloned date by normal wrapper',
            'force': 'do not expose or fabricate force208; separate native legality and acceptance remain required',
            'ownership': 'parameter offer owned by caller; constructor copies into original; wrapper copies into command-owned clone; no owned war pointer',
        },
        'unresolved': [
            'No live war offer, constructor/reset/preview/clone/send invocation or gameplay test was performed.',
            'No numeric war ID schema or globally unique serialized war identity is recovered; the relation-index key is a country slot and first-match semantics are explicit.',
            'War object owner, removal/epoch synchronization, duplicate-key policy and all multi-war/separate-peace cases are not closed. Pointer/date/same-address are not lifetime proof.',
            'No exhaustive full-handle validation exists inside the traced lookup; native slot comparisons do not authorize bare TAG/slot public input.',
            'SideA/B fields are observed without independently naming attacker/defender. First vector element is a native negotiation role test, not universal leader proof.',
            'All transitive candidate script/virtual calls, exceptional allocation unwinding and complete auxiliary record meanings are not proven pure or safe for a no-send preview.',
            '97a670 and97a8d0 have retained indirect-switch edges; this report documents reset call/selection contract but does not implement or claim exhaustive switch-effect closure.',
            '9851f0 is deliberately only its first0x6a0 bounded CFG; unrelated text rendering branches are outside scope.',
            'White-peace predicate/display, legal request, transport dispatch, recipient acceptance and applied/persistent peace are different facts; none imply the latter stages.',
        ],
        'limits': {'functions': len(functions), 'decoded_bytes': decoded, 'max_decoded_bytes': 65536,
                   'max_window_bytes': 0x3000, 'memory_guard_mib': 768,
                   'process_access': False, 'compiled': False, 'native_calls': False},
    }


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
                      'functions': report['limits']['functions'],
                      'decoded_bytes': report['limits']['decoded_bytes'],
                      'peak_committed_bytes': check_memory_budget(), 'check': args.check}))


if __name__ == '__main__':
    main()
