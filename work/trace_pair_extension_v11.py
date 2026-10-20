"""Bounded disk-only review of eight scalar ordinary-diplomacy families."""
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
OUTPUT = ROOT / 'work/reports/native-pair-extension-v11-1375.json'
INPUTS = {
    'native': ('work/reports/native-diplomacy-1.37.5.json', 'c64df6e043c9e7a498a25082e0e768902764e4a271ab3579f0eaddb2f1391633'),
    'fields': ('work/reports/native-action-fields-1375.json', 'cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96'),
    'modes': ('work/reports/native-diplomacy-modes-1375.json', '1c0fa12b630a134036c32caf826750ce82608c44fab80108e6cfd2b738d06676'),
}
SLOTS = (0, 0x40, 0x48, 0x70, 0x80, 0x98, 0xa8, 0xb0, 0xd0, 0xe0)
EXTRA = (0x4e7470, 0x14003f0, 0x13ffd20, 0xa749f0, 0xa74b90, 0xa74d80,
         0xa74f20, 0xa6a8f0, 0xa6ab70, 0xa6a090, 0xa69c30, 0xa69d30,
         0xa5e130, 0x373880, 0x4f3fe0, 0x3387f0, 0x338540, 0xa658d0,
         0x50e090, 0xa6a7f0, 0xa6a930, 0xa6aa70, 0xa6abb0,
         0x5392c0, 0x53b1a0, 0x57afb0, 0x57d050)


def candidate(positive, negative, role, parameters, reply, limitations):
    return {'positive': positive, 'negative': negative, 'actor_target_roles': role,
            'proposed_parameters': parameters, 'reply_predicate': reply,
            'limitations': limitations, 'runtime_verified': False, 'execution_verified': False}


CANDIDATES = {
    'warningaction': candidate('issue warning', None, 'actor warns target', [], 'false',
        ['No false-mode removal branch in reviewed effect. Do not expose revoke_warning by sharing the setter.']),
    'insultaction': candidate('ordinary insult', None, 'actor insults target',
        [{'name': 'index', 'offset': '0x40', 'representation': 'int32', 'fixed_internal_value': -1, 'public': False}], 'false',
        ['Scornful nonnegative definition indexes require a separate validated selector and are excluded.', 'False is not an undo operation.']),
    'form_coalition': candidate('form or join coalition against target', 'leave coalition against target',
        'actor is coalition member; target is coalition enemy', [], 'false',
        ['Join and form are state-dependent names of one true mode.', 'Cancellation must bind actor.current_coalition_target to the exact target.']),
    'support_independence_action': candidate('ask or offer support, selected by current dependency',
        'end requested or offered support, selected by current dependency',
        'actor is requester; dependent/provider role requires actor overlord and dependency-definition predicate', [], 'value',
        ['Relation fields retain proposal actor/target order; do not assume +10 always means provider.', 'Require valid current subject type, authority and paired relation before cancellation.']),
    'transfer_trade_power': candidate('request target to transfer trade power to actor', 'cancel current trade-power relation',
        'positive actor receives; target transfers',
        [{'name': 'fraction', 'offset': '0x40', 'representation': 'signed_fixed_point_1000', 'percent_conversion': 'internal = percent * 10', 'public': True},
         {'name': 'extra_flag', 'offset': '0x44', 'representation': 'byte', 'fixed_internal_value': 0, 'public': False}], 'value',
        ['Extra flag is cleared by clone; ordinary candidate requires zero and excludes forced/peace variants.',
         'Cancellation effect searches both directions; host must explicitly bind the intended current relation and direction.',
         'Complete UI submission range and engine validity of every amount remain unverified.']),
    'steer_trade': candidate('request target to steer trade toward actor', 'cancel current steering relation',
        'positive actor benefits; target steers', [], 'value',
        ['Parser dummy token is ignored and is not a public parameter.', 'Exclude nonzero persistent relation+40 flag until its variant semantics are reviewed.',
         'Cancellation searches both directions; a pair lookup alone is insufficient to distinguish authority.']),
    'giftaction': candidate('send gift', None, 'actor pays; target receives',
        [{'name': 'amount', 'offset': '0x40', 'representation': 'signed_fixed_point_1000', 'unit': 'ducats', 'public': True}], 'false',
        ['Adapter must bound positive decimal amount and integer overflow; full GUI min/max has not been closed.', 'No refund/false cancellation.']),
    'trade_favors_for_gold': candidate('request gold in exchange for favors', None,
        'target pays; actor receives', [], 'true',
        ['Amount is calculated by native helper from target income; no caller-selected money or favors field.',
         'Acceptance and available favors are native gates; never force state2.', 'False is not cancellation.']),
}


def fact(summary, *anchors):
    return {'summary': summary, 'evidence_rvas': list(map(hex, anchors)), 'runtime_verified': False}


FACTS = {
    'shared_scalar_ownership': fact(
        'All eight use wrapper4e9930, unique-clone predicate+a8=8f450 and plain setter+e0=4e99d0. Five action classes are0x40; insult/gift/transfer are0x48. Derived clone fields are scalar. The existing command destructor owns its cloned action; original remains separately owned. These static slots do not certify new-family native lifecycle or dispatch.',
        0x4e9930, 0x4e7470, 0x4e99d0, 0x8f450, 0x129450, 0x129500),
    'warning_effect': fact(
        'Reviewed warning effect has no action-value test: it calls4ec160 then allocates0x40 relation vt1c7fca0. Relation+10=actor,+18=target,+20=action date; both pair directions register througha6a090. This is issue-warning evidence, not a revocation implementation.',
        0x522a10, 0x522a15, 0x522a84, 0x522aa7, 0x522aab, 0x522aaf, 0x522b0c, 0x522b4d, 0xa6a0af),
    'ordinary_insult': fact(
        'Factory initializes index+40=-1. Effect compares the signed field against zero; nonnegative selects additional definition behavior. Ordinary candidate fixes -1 and excludes arbitrary/scornful indexes. No reviewed effect branch treats value=false as undo.',
        0x35d8a9, 0x35d8bd, 0x53794e, 0x537952, 0x537eb3, 0x537eb7, 0x538b11, 0x538b15, 0x5392c9, 0x5392dc, 0x5392ee),
    'coalition_mode_effect': fact(
        'True mode calls373880 with actor country and target. False first compares actor+18f8 coalition-target slot to action target, then calls the same helper with invalid handle. Helper removes prior membership, writes full new handle+18f8, and for a valid target inserts a0x20 list node under target1910/1918/1920; node full member handle+0,prev8,next10,removed18. Current slot checks must be strengthened to full-handle identity by a future host.',
        0x5893c3, 0x589424, 0x5899ca, 0x5899ec, 0x5899ef, 0x589a0c,
        0x3738ea, 0x3738f2, 0x3738f9, 0x373987, 0x37398a, 0x37398e, 0x373996, 0x3739aa),
    'independence_effect': fact(
        'Value=true/state2 creates0x40 relation via50e090 (vt1c80570), preserving action actor+10 and target+20 as relation+10/+18. Both indexes usea69c30; getter uses root170/count17c. False lookup callsa69d30 thena5e130, base destructor and free0x40. Public ask/offer names depend on current dependency state; relation field order does not independently identify the supporter.',
        0x50ca01, 0x50ca0d, 0x50ce66, 0x50ce85, 0x50e0d8, 0x50ce98, 0x50ce9c,
        0x50ced7, 0x50cf18, 0xa69d3c, 0xa69d43, 0x50da2e, 0x50da39, 0x50da46, 0x50da4b),
    'transfer_effect_and_direction': fact(
        'Accepted transfer creates0x48 relation vt1c571f0: +10=target supplier,+18=actor recipient,+40=amount,+44=extra flag. Activationa749f0 publishes supplier-side root230/count23c througha6a7f0 and recipient-side root248/count254 througha6a930. False effect searches either direction beforea74b90 removes indexes and marks+28=1. Preserve direction instead of pretending inverse actor/target is a different factory.',
        0x579360, 0x57936a, 0x5793eb, 0x57940f, 0x579413, 0x579438, 0x57943f, 0x579430,
        0xa74b29, 0xa74b6a, 0xa6a80f, 0xa6a94f, 0xa6a8fc, 0xa6a903,
        0x5799e6, 0x579a0d, 0x579fa1, 0xa74c2f),
    'transfer_amount_and_flag': fact(
        'Amount token1a1 serializes through the known signed fixed-point x1000 helper. The bounded GUI calculation14003f0 converts an integer percentage to the temporary action+40 as percent*10 (100 percent=1000); float constant1dc1938 is1000. This is a percentage-calculation path, not a recovered complete dialog submit ABI. Clone copies+40 but resets+44=0; do not expose+44 as a preserved public parameter.',
        0x57afb9, 0x57afcc, 0x57afd7, 0x1400491, 0x140049d, 0x14004a6, 0x14004aa, 0x14004cb,
        0x57adbe, 0x57adc1, 0x57adc8),
    'steering_effect_and_direction': fact(
        'Value=true/state2 creates0x48 relation vt1c7d498 with+10=target steering country,+18=actor beneficiary,+40=0. Activationa74d80 publishes steering-country root260/count26c viaa6aa70 and beneficiary root278/count284 viaa6abb0. False effect searches both directions, thena74f20 clears indexes and marks removed. The action itself is0x40 and owns no derived object.',
        0x57b480, 0x57b48a, 0x57b499, 0x57b50a, 0x57b52e, 0x57b532, 0x57b54f, 0x57b553,
        0xa74eb9, 0xa74efa, 0xa6aa8f, 0xa6abcf, 0xa6ab7c, 0xa6ab83,
        0x57bb36, 0x57bb5d, 0x57c0f1, 0xa74fbf),
    'gift_money_direction': fact(
        'Gift amount uses money token2daf and signed fixed-point x1000 parser. Effect passes actor and amount to AddExpense3387f0, then target and same amount to AddIncome338540. These helpers log their names; expense negates amount before3383b0. No inverse/refund mode is established.',
        0x53b1a9, 0x53b1bc, 0x53b1c7, 0x539886, 0x5398b8, 0x5398bd, 0x5398ef,
        0x33885d, 0x3388a4, 0x3388b8, 0x3385a8, 0x3385d3),
    'favor_gold_native_amount': fact(
        'Favor-for-gold has no derived money field. Helper4f3fe0 reads target selected income components, multiplies their sum by12 and native global233f4cc/1000. Only state2 effect spends native-defined favors usinga658d0, charges target through3387f0, and credits actor through338540. +d0 is always true; normal reply remains required. Do not expose chosen amount or treat value=false as cancellation.',
        0x4f3fe0, 0x4f405d, 0x4f4060, 0x4f4063, 0x4f406d, 0x4f4560, 0x4f4912, 0x4f4916,
        0x4f495c, 0x4f4976, 0x4f497b, 0x4f49ad, 0x4f49b2, 0x4f49e4, 0x8f440),
}


def generate():
    source = {}
    for key, (path, expected) in INPUTS.items():
        raw = (ROOT / path).read_bytes()
        if len(raw) > 5*1024*1024 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned input changed: ' + path)
        source[key] = json.loads(raw)
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Wrong executable')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    functions = {}
    decoded = 0

    def include(entry, window=0x4000):
        nonlocal decoded
        key = hex(entry)
        if key in functions:
            return
        if len(functions) >= 100:
            raise ValueError('Function budget exceeded')
        code, edges = bounded_cfg(pe, md, entry, window=window, max_instructions=4000)
        size = sum(i.size for i in code)
        decoded += size
        if decoded > 128*1024:
            raise ValueError('Decode budget exceeded')
        functions[key] = {'prefix32': pe.bytes_at(entry, 32).hex(), 'instructions': rows(pe, code),
                          'edges': edges, 'decoded_bytes': size, 'window_bytes': window}
        check_memory_budget()

    inventory = source['native']['native_actions']
    fields = {a['name']: a for a in source['fields']['actions']}
    actions = []
    for name, proposal in CANDIDATES.items():
        a = next(x for x in inventory['actions'] if x['name'] == name)
        vt = int(a['vtable_rva'], 16)
        pins = {}
        for slot in SLOTS:
            method = int(a['slots'][hex(slot)], 16)
            if pe.u64(pe.to_offset(vt + slot)) - pe.base != method:
                raise ValueError('Vtable mismatch')
            pins[hex(slot)] = hex(method)
            include(method)
        if pins['0x40'] != '0x4e9930' or pins['0xa8'] != '0x8f450' or pins['0xe0'] != '0x4e99d0':
            raise ValueError('Ordinary pair ownership/setter assumptions differ')
        ref = int(a['factory_branch']['reference_rva'], 16)
        alloc = max((x for x in inventory['factory_direct_calls'] if ref-0xa0 < int(x['call_rva'],16) < ref),
                    key=lambda x: int(x['call_rva'],16))
        start = int(alloc['call_rva'],16)-5
        if pe.bytes_at(start,1) != b'\xb9':
            raise ValueError('Allocation boundary mismatch')
        include(start, 0x90)
        actions.append({'name': name, 'token_id': a['token_id'], 'vtable_rva': a['vtable_rva'],
                        'size_bytes': a['clone']['allocation']['size_bytes'], 'slots': pins,
                        'factory_block_rva': hex(start), 'factory_reference_rva': hex(ref),
                        'clone_scalar_reads': a['clone']['source_field_reads'], 'derived_fields': fields[name]['derived_fields'],
                        'proposal': proposal,
                        'prior_mode_evidence': [x for x in source['modes']['actions'] if x.get('native_family') == name],
                        'runtime_verified': False, 'execution_verified': False})
    for entry in EXTRA:
        include(entry)
    lookup = {r['rva']: r for f in functions.values() for r in f['instructions']}
    for key, value in FACTS.items():
        for anchor in value['evidence_rvas']:
            if anchor not in lookup:
                raise ValueError('Missing anchor for ' + key + ': ' + anchor)
    resources = []
    base = ROOT / 'work/runtime/unpacked-1.37.5/base'
    terms = tuple(CANDIDATES) + ('TRANSFER_TRADE_POWERDESC', 'TRANSFER_TRADE_POWER_SELECT_DESC',
        'STEER_TRADE_SELECT_DESC', 'TRADE_FAVORS_FOR_GOLD_', 'GOLD_FAVORS', 'WARNINGDESC')
    for rel in ('common/diplomatic_actions/00_diplomatic_actions.txt',
                'common/new_diplomatic_actions/00_diplomatic_actions.txt', 'common/defines.lua',
                'localisation/diplomacy_l_english.yml', 'localisation/rule_britannia_l_english.yml'):
        path = base / rel
        if path.stat().st_size > 2*1024*1024:
            raise ValueError('Resource file exceeds bound')
        raw = path.read_bytes()
        selected = [{'line': n, 'text': line} for n, line in enumerate(raw.decode('utf-8-sig').splitlines(), 1)
                    if any(term in line for term in terms)]
        resources.append({'path': 'base/' + rel, 'sha256': hashlib.sha256(raw).hexdigest(), 'selected_lines': selected})
    return {'schema': 'native_pair_extension_v11_1375_v1', 'game_sha256': SHA,
            'runtime_verified': False, 'execution_verified': False, 'public_backend_registered': False,
            'input_hashes': {k: {'path': v[0], 'sha256': v[1]} for k,v in INPUTS.items()},
            'actions': actions, 'facts': FACTS, 'functions': functions, 'resources': resources,
            'float_constants': [{'rva': '0x1dc1938', 'bytes': pe.bytes_at(0x1dc1938,4).hex(),
                                 'float32': struct.unpack('<f', pe.bytes_at(0x1dc1938,4))[0]}],
            'unresolved': ['All eight require new runtime lifecycle, preview, command and outcome tests.',
                'Warning/insult/gift/favor-gold false is not an exposed operation.',
                'Complete amount ranges, trade forced variants, all acceptance side effects and economic balance reconciliation remain unverified.',
                'World epoch, player authority, current dependency and exact relation binding remain host requirements.',
                'No catalog, execution declaration, frozen native source or game state is changed.'],
            'limits': {'max_functions': 100, 'actual_functions': len(functions), 'max_window_bytes': 16384,
                       'max_instructions_per_window': 4000, 'max_decoded_bytes': 131072, 'decoded_bytes': decoded,
                       'memory_guard_mib': 768, 'process_access': False}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    report = generate()
    data = (json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != data:
            raise ValueError('Report differs')
    else:
        OUTPUT.write_bytes(data)
    print(json.dumps({'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                      'functions': report['limits']['actual_functions'], 'decoded_bytes': report['limits']['decoded_bytes'],
                      'check': args.check}))


if __name__ == '__main__':
    main()
