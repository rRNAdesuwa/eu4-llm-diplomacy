"""Prepare a separate native host for the TAG-only diplomacy scope. No game access."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE

OLD = ROOT / 'bridge/native/tag_command_1375'
OUT = ROOT / 'bridge/native/tag_diplomacy_1375_v31'
CATEGORIES = {'alliance', 'influence', 'relations', 'dynasty', 'covert', 'economy', 'access', 'favors'}


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    OUT.mkdir(exist_ok='--resume-preparation' in sys.argv)
    shutil.copytree(OLD / 'src', OUT / 'src', dirs_exist_ok='--resume-preparation' in sys.argv)
    shutil.copyfile(OLD / 'build_test.cmd', OUT / 'build_test.cmd')
    origins = {str(p.relative_to(ROOT)).replace('\\', '/'): pin(p)
               for p in [*(OLD / 'src').rglob('*'), OLD / 'build_test.cmd'] if p.is_file()}
    (OUT / 'origin-pins.json').write_text(json.dumps(origins, indent=2) + '\n')
    src = OUT / 'src/work/candidates'
    host = src / 'v26-gap-curry-bootstrap-1375'
    for path in [*host.iterdir(), OUT / 'build_test.cmd']:
        if path.is_file():
            text = path.read_text()
            for a, b in [('tagcommand30', 'tagcommand31'), ('_v30', '_v31')]:
                text = text.replace(a, b)
            path.write_text(text, newline='\n')
    catalog = json.loads((ROOT / 'bridge/diplomacy_catalog.json').read_text(encoding='utf-8'))['actions']
    native = json.loads((ROOT / 'work/reports/native-diplomacy-1.37.5.json').read_text())['native_actions']['actions']
    by_name = {x['name']: x for x in native}
    modes = {x['action_id']: x for x in json.loads((ROOT / 'work/reports/native-diplomacy-modes-1375.json').read_text())['actions']}
    old_names = re.search(r'Names\{\{(.*?)\}\};', (host / 'codec.h').read_text(), re.S).group(1)
    old_names = re.findall(r'"([a-z0-9_]+)"', old_names)
    old_families = ['Vassal', 'Marriage', 'Improve', 'Guarantee', 'SpyNetwork', 'Curry', 'FleetOffer',
                    'Insult', 'Coalition', 'Independence', 'FavorGold', 'FavorMen', 'FavorSailors', 'FavorTrust', 'FavorWarPrep']
    old_family = dict(zip(['vassalaction', 'royal_marriage', 'improve_relation', 'guaranteeaction', 'spy_network',
                          'curry_favors', 'offer_fleet_access', 'insultaction', 'form_coalition',
                          'support_independence_action', 'trade_favors_for_gold', 'trade_favors_for_men',
                          'trade_favors_for_sailors', 'trade_favors_for_trust', 'trade_favors_for_war_prep'], old_families))
    bindings = {}
    excluded = []
    for x in catalog:
        if x['category'] not in CATEGORIES:
            continue
        name = x['action_id']
        variants = x.get('native_mapping', {}).get('variants', [])
        family = variants[0]['name'] if len(variants) == 1 else None
        extra = set(x['parameters']['properties']) - {'actor', 'target'}
        mode_info = modes.get(name, {})
        if name in old_names:
            extra = set()  # Existing no-parameter V30 bindings remain compatible.
        if name == 'scornful_insult':
            reason = 'deferred_insult_definition_selector'
        elif extra:
            reason = 'deferred_parameterized_action'
        elif not family:
            reason = 'independent_command' if name in {'select_rival', 'remove_rival', 'create_vassal'} else 'no_valid_native_direction'
        elif mode_info.get('classification') == 'native_ui_cancel_mode_effect_unverified':
            reason = 'legacy_cancel_label_without_verified_cancel_semantics'
        elif family in {'condottieri_action', 'support_rebels', 'fabricate_claim'}:
            reason = 'deferred_existing_unit_faction_or_province_binding'
        else:
            row = by_name[family]
            size = row['clone']['allocation']['size_bytes']
            if size == 64 or family in {'royal_marriage', 'insultaction', 'trade_favors_for_trust',
                                       'scriptable_diplomatic_action', 'invite_to_federation',
                                       'invite_to_trade_league', 'tributary_state_action',
                                       'warsubsidy', 'transfer_trade_power'}:
                bindings[name] = dict(action=name, category=x['category'], native_family=family,
                                      mode=mode_info.get('mode', {}).get('value', not (name in {
                                          'cancel_vassalization', 'break_marriage', 'stop_improving_relations',
                                          'revoke_guarantee', 'stop_building_spy_network'})),
                                      script_key=x['game_key'] if family == 'scriptable_diplomatic_action' else '')
                continue
            reason = 'deferred_owned_extra_fields'
        excluded.append(dict(action=name, category=x['category'], reason=reason))
    actions = old_names + sorted(set(bindings) - set(old_names))
    families = list(old_family)
    families += sorted({v['native_family'] for v in bindings.values()} - set(families))
    enum_family = {n: old_family.get(n, 'N_' + n) for n in families}
    core = src / 'v24-pair-send-core-r2-1375/pair_send.cpp'
    header = src / 'v21-core-pair-nosend-r2-1375/pair_component.h'
    text = header.read_text()
    text = text.replace('FullCallerEvidence full_caller;', 'FullCallerEvidence full_caller;\n    std::uint32_t wrapper{0x4e9930};')
    text = text.replace('FavorWarPrep };', 'FavorWarPrep, ' + ', '.join(enum_family[n] for n in families[15:]) + ' };')
    text = text.replace('FavorWarPrep\n};', 'FavorWarPrep,\n    ' + ', '.join('N_' + n for n in actions[21:]) + '\n};')
    text = text.replace('std::array<Profile, 15>', f'std::array<Profile, {len(families)}>')
    text = text.replace('bool positive(Action action) noexcept;',
        'bool positive(Action action) noexcept;\nbool legacy_cancel(Action action) noexcept;\n'
        'const char* script_key(Action action) noexcept;\n'
        f'inline constexpr unsigned ActionCount={len(actions)};')
    header.write_text(text, newline='\n')
    text = core.read_text()
    start = text.index('constexpr std::array<Profile, 15> registry')
    end = text.index('bool tag(', start)
    registry = []
    for family in families:
        x = by_name[family]; slots = x['slots']
        fields = [x['token_id'], x['clone']['allocation']['size_bytes'], int(x['vtable_rva'], 16)]
        fields += [int(slots[k], 16) for k in ('0xb0', '0x0', '0xe0', '0x80', '0x88')]
        registry.append('    {Family::' + enum_family[family] + ',' + ','.join(hex(v) for v in fields)
                        + ',FullCallerEvidence::StaticSlotOnly,' + slots['0x40'] + '}')
    generated = f'constexpr std::array<Profile, {len(families)}> registry{{{{\n' + ',\n'.join(registry) + '\n}};\n'
    generated += f'constexpr std::array<std::string_view, {len(actions)}> names{{{{' + ','.join('"'+n+'"' for n in actions) + '}};\n'
    generated += 'struct Binding {Family family;bool mode;const char* script;};\n'
    generated += f'constexpr std::array<Binding,{len(actions)}> bindings{{{{\n'
    generated += ',\n'.join(' {Family::' + enum_family[bindings[n]['native_family']] + ','
                           + str(bindings[n]['mode']).lower() + ',"' + bindings[n]['script_key'] + '"}' for n in actions) + '\n}};\n'
    text = text[:start] + generated + text[end:]
    text = text.replace('std::array<Profile, 15>', f'std::array<Profile, {len(families)}>')
    text = text.replace('if (i>=21)', 'if (i>=ActionCount)').replace('return registry[i<12?i/2:i-6];',
        'for(const auto& p:registry)if(p.family==bindings[i].family)return p;\n    throw std::out_of_range("family");')
    text = re.sub(r'bool positive\(Action action\) noexcept \{.*?\}',
        'bool positive(Action action) noexcept {const auto i=static_cast<unsigned>(action);return i<ActionCount&&bindings[i].mode;}\n'
        'bool legacy_cancel(Action action) noexcept {return static_cast<unsigned>(action)<12&&!positive(action);}\n'
        'const char* script_key(Action action) noexcept {const auto i=static_cast<unsigned>(action);return i<ActionCount?bindings[i].script:"";}', text)
    text = text.replace('request.action)>=21', 'request.action)>=ActionCount')
    text = text.replace('if (mode) return true;', 'if (mode || !legacy_cancel(request.action)) return true;')
    text = text.replace('    case Family::SpyNetwork: return false; // exclusively private raw graph binder',
                        '    case Family::SpyNetwork: return false; // exclusively private raw graph binder\n    default:return false;')
    core.write_text(text, newline='\n')
    codec = host / 'codec.h'; text = codec.read_text()
    text = re.sub(r'inline constexpr std::array<const char\*,21> Names\{\{.*?\}\};',
                  f'inline constexpr std::array<const char*,{len(actions)}> Names{{{{' + ','.join('"'+n+'"' for n in actions) + '}};', text, flags=re.S)
    codec.write_text(text, newline='\n')
    test = host / 'test_codec.cpp'; text = test.read_text().replace('action<21', 'action<v21pair::ActionCount').replace('p.sequence=action+1', 'p.sequence=action%64+1')
    test.write_text(text, newline='\n')
    guard = src / 'v21-native-pair-guard-r3-1375/native_guard.cpp'
    text = guard.read_text().replace('action>=21', 'action>=v21pair::ActionCount')
    text = text.replace('if(!cleanup&&!v21pair::positive(request_.action))', 'if(!cleanup&&v21pair::legacy_cancel(request_.action))')
    guard.write_text(text, newline='\n')
    # Exact per-function code pins for every new registered family, from the pinned image.
    pe = PE(ROOT.parent / 'eu4.exe')
    assert hashlib.sha256(pe.data).hexdigest() == '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
    addresses = set()
    for family in families:
        addresses.update(int(by_name[family]['slots'][k], 16) for k in ('0x0', '0x40', '0x80', '0x88', '0xb0', '0xe0'))
    lines = ['#pragma once', '#include <cstdint>', 'namespace v24port {',
             'struct CodePin {std::uint32_t rva;const char* hex;};', 'inline constexpr CodePin kCodePins[]={']
    addresses.update((0x35d210, 0x4e7470, 0x4e8630, 0x4e9930))
    lines += [' {' + hex(a) + ',"' + pe.bytes_at(a, 16).hex() + '"},' for a in sorted(addresses)]
    lines += ['};', '}']
    (src / 'v24-pair-send-port-r2-1375/native_pins.h').write_text('\n'.join(lines)+'\n')
    config = {'schema': 'EU4TAGACTIONS/1', 'purpose': 'tag_command_1375_v31', 'session_prefix': 'tagcommand31',
              'actions': actions, 'bindings': [bindings[n] for n in actions], 'excluded': excluded,
              'categories': sorted(CATEGORIES), 'runtime_verified': False}
    (ROOT / 'bridge/tag_actions_1375_v31.json').write_text(json.dumps(config, indent=2)+'\n')
    print(json.dumps({'actions':len(actions), 'families':len(families), 'excluded':len(excluded), 'game_accessed':False}))


if __name__ == '__main__':
    main()
