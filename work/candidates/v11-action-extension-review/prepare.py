"""Generate isolated review copies and a diff; never edits native/v11 or v10."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'work'))
from discover_diplomacy import PE, check_memory_budget
from map_diplomacy_fields import SHA

REPORTS = {
    'native-pair-extension-v11-1375.json': 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344',
    'native-pair-extension-effects-v11-1375.json': 'aa93b84c2ae1af3652134b49c80453aabfb4a51006e4ec20b9c6c7196eb1888a',
}
BASES = {
    'pair-engine-1375.h': '0b2d5d0a725481e4e8086e9cb8ce72141dcbfc992be44f5e6c07acd5415bbbab',
    'pair-engine-1375.cpp': '2058e53ae08d86c630b1d0bd44d44f180ac2d67305d3c59550aa901796ab6c8b',
    'pair-probe-v6-1375.cpp': '2e73afa74108a5929e4a5fcd69a1f472809195943c19af3b7910972eb638ae64',
    'pair-preview-v6-1375.cpp': '363b5485d98df0746691533a9b6217845928093ad4a783a122cca7ca593f0a08',
    'pair-command-v6-1375.cpp': 'e6e3d2df457e70c3e3ee3abe291e3019a0639e44d2b0ca0e31821818d3042b0b',
}
# Append IDs without changing the first24 ordinals. No fabricated false variants.
MODES = [('warn',12,True), ('insult',13,True), ('form_coalition',14,True), ('leave_coalition',14,False),
         ('support_independence',15,True), ('cancel_independence_support',15,False),
         ('request_trade_power',16,True), ('cancel_trade_power_transfer',16,False),
         ('steer_trade',17,True), ('cancel_steer_trade',17,False), ('send_gift',18,True), ('trade_favors_for_gold',19,True)]


def digest(data): return hashlib.sha256(data).hexdigest()


def replace(text, old, new):
    if text.count(old) != 1: raise ValueError(f'Expected unique source anchor ({text.count(old)}): {old[:90]}')
    return text.replace(old,new)


def append_table(text, marker, rows):
    pos=text.index('\n};',text.index(marker))
    return text[:pos]+''.join('\n'+row for row in rows)+text[pos:]


def generate():
    documents={}
    for name, expected in REPORTS.items():
        raw=(ROOT/'work/reports'/name).read_bytes()
        if len(raw)>4*1024*1024 or digest(raw)!=expected: raise ValueError('Report changed: '+name)
        documents[name]=json.loads(raw)
    evidence=documents['native-pair-extension-v11-1375.json']
    pe=PE(ROOT.parent/'eu4.exe')
    if digest(pe.data)!=SHA: raise ValueError('Wrong executable')
    actions=evidence['actions']
    if len(actions)!=8: raise ValueError('Expected eight new families')
    slots=(0,0x40,0x48,0x70,0x80,0x98,0xa8,0xb0,0xd0,0xe0,0x100,0x108)
    checked_slots=[];pinmap={}
    for action in actions:
        vt=int(action['vtable_rva'],16)
        for slot in slots:
            method=pe.u64(pe.to_offset(vt+slot))-pe.base
            expected=action['slots'].get(hex(slot))
            if expected is not None and int(expected,16)!=method: raise ValueError('Method slot changed')
            if slot in (0x100,0x108) and method != (0x8f440 if slot==0x100 else 0x8f450): raise ValueError('Extra predicate differs')
            action['slots'][hex(slot)]=hex(method)
            size=3 if method in (0x8f440,0x8f450) else 4 if method==0x4e99d0 else 5 if method==0x4e4d50 else 6 if slot==0x98 else 32
            pinmap[hex(method)]=pe.bytes_at(method,size).hex()
            checked_slots.append({'vtable':hex(vt),'slot':hex(slot),'method':hex(method)})
        getter=int(action['slots']['0x98'],16)
        if pe.bytes_at(getter,6) != b'\xb8'+action['token_id'].to_bytes(4,'little')+b'\xc3': raise ValueError('Getter not exact token leaf')
        for row in evidence['functions'][action['factory_block_rva']]['instructions']:
            blob=bytes.fromhex(row['bytes'])
            if pe.bytes_at(int(row['rva'],16),len(blob))!=blob: raise ValueError('Factory bytes mismatch')
        entry=int(action['factory_block_rva'],16);pinmap[hex(entry)]=pe.bytes_at(entry,32).hex()
    # Shared factory tail proves state/value/date/ID defaults; scalar defaults
    # come from the reviewed factory branches (gift/transfer qword+3c=0).
    pinmap['0x36044d']=pe.bytes_at(0x36044d,0x2b).hex()
    common='\nbool v11_image_pin(std::uintptr_t base) {\n'
    common+=''.join(f'    if (!extension_prefix(base + {r}, "{b}")) return false;\n' for r,b in pinmap.items())
    common+=''.join(f'    if (read_at<std::uintptr_t>(base + {r["vtable"]} + {r["slot"]}) != base + {r["method"]}) return false;\n' for r in checked_slots)
    common+='    return true;\n}\n'
    fields=(HERE/'fixed-fields.inc').read_text(encoding='utf-8')
    binding=(HERE/'binding-helpers.inc').read_text(encoding='utf-8')
    mode_rows=[(i//2,i%2==0) for i in range(24)]+[(family,positive) for _,family,positive in MODES]
    mapping='struct ModeMapping { unsigned family; bool positive; };\nconstexpr ModeMapping kModes[] = {\n'
    mapping+=''.join(f'    {{{family}, {str(positive).lower()}}},\n' for family,positive in mode_rows)+'};\n'
    outputs={};diffs=[]
    for name,expected in BASES.items():
        raw=(ROOT/'work/native/v10'/name).read_bytes()
        if digest(raw)!=expected: raise ValueError('Frozen base differs: '+name)
        old=raw.decode('utf-8').replace('\r\n','\n');s=old
        if name.endswith('.h'):
            s=replace(s,'    give_subsidies, cancel_subsidies\n','    give_subsidies, cancel_subsidies,\n    '+',\n    '.join(x[0] for x in MODES)+'\n')
            s=s.replace('twenty-four IDs','thirty-six IDs').replace('independent v10 lab host','unmerged v11 action-extension candidate')
        else:
            table=[]
            for a in actions:
                q=a['slots'];n=a['name'];t=hex(a['token_id']);v=a['vtable_rva'];size=hex(a['size_bytes'])
                p=lambda key:pe.bytes_at(int(q[key],16),32).hex()
                if name=='pair-engine-1375.cpp':
                    table.append(f'    {{{t}, {size}, {v}, {q["0xb0"]}, {q["0x0"]}, {q["0x98"]}, {q["0x80"]}, {q["0x100"]}, {q["0x108"]}, {q["0xe0"]},\n     "{p("0xb0")}", "{p("0x80")}"}},')
                elif name=='pair-probe-v6-1375.cpp': table.append(f'    {{"{n}", {t}, {size}, {v}, {q["0xb0"]}, {q["0x0"]}, {q["0x98"]}}},')
                elif name=='pair-preview-v6-1375.cpp': table.append(f'    {{"{n}", {t}, {v}, {q["0x80"]}, {q["0x0"]}, {q["0x98"]}, "{p("0x80")}"}},')
                else: table.append(f'    {{"{n}", {t}, {v}, {q["0xb0"]}, {q["0x0"]}, {q["0x98"]}, {q["0x80"]}, {q["0x100"]}, {q["0x108"]},\n     "{p("0xb0")}", "{p("0x80")}"}},')
            s=append_table(s,'constexpr Action kActions[]',table)
            imagefn='bool image_pin(' if name=='pair-engine-1375.cpp' else 'bool loaded_image_matches(' if name=='pair-probe-v6-1375.cpp' else 'bool image_matches('
            pos=s.index(imagefn);s=s[:pos]+common+s[pos:]
            opening=s.index('{',s.index(imagefn))+1
            arg='module' if name=='pair-engine-1375.cpp' else 'base'
            s=s[:opening]+f'\n    if (!v11_image_pin({arg})) return false;'+s[opening:]
            helper=fields if name in ('pair-preview-v6-1375.cpp','pair-command-v6-1375.cpp') else fields[:fields.index('unsigned v11_mode_count')]
            pos=s.index('bool derived_fields(' if name=='pair-engine-1375.cpp' else 'bool default_fields_match(' if name=='pair-probe-v6-1375.cpp' else 'bool fixed_parameters_match(')
            s=s[:pos]+helper+'\n'+s[pos:]
            if name=='pair-engine-1375.cpp':
                s=replace(s,'    "give_subsidies", "cancel_subsidies"','    "give_subsidies", "cancel_subsidies",\n    '+',\n    '.join('"'+m[0]+'"' for m in MODES))
                s=replace(s,'static_assert(sizeof(kNames) / sizeof(kNames[0]) == 2 * sizeof(kActions) / sizeof(kActions[0]), "pair modes must match families");',mapping+'static_assert(sizeof(kNames)/sizeof(kNames[0]) == sizeof(kModes)/sizeof(kModes[0]), "explicit modes must match IDs");')
                s=replace(s,'    std::uintptr_t entry, mission, task;','    std::uintptr_t entry, mission, task;\n    std::uint64_t scope[8]{}; // new-family comparison-only relation/dependency binding')
                pos=s.index('bool spy_list(');s=s[:pos]+binding+'\n'+s[pos:]
                s=replace(s,'    binding = {-1, 0, 0, 0};\n    std::uintptr_t object = 0;\n    if (id == ActionId::stop_building_spy_network)',
                    '    binding = {-1, 0, 0, 0};\n    const unsigned mode_index = static_cast<unsigned>(id);\n    if (mode_index >= 36) return false;\n    if (mode_index >= 24) return v11_binding(module, live, actor, target, kModes[mode_index].family, kModes[mode_index].positive, binding);\n    std::uintptr_t object = 0;\n    if (id == ActionId::stop_building_spy_network)')
                s=replace(s,'return a.envoy == b.envoy && a.entry == b.entry && a.mission == b.mission && a.task == b.task;',
                    'return a.envoy == b.envoy && a.entry == b.entry && a.mission == b.mission && a.task == b.task\n        && std::memcmp(a.scope, b.scope, sizeof(a.scope)) == 0;')
                s=replace(s,'    const Action& action = kActions[index / 2];\n    const bool positive = index % 2 == 0;',
                    '    const Action& action = kActions[kModes[index].family];\n    const bool positive = kModes[index].positive;')
                s=replace(s,'bool derived_fields(std::uintptr_t object, const Action& action, bool empty_required, bool factory_default = false) {',
                    'bool derived_fields(std::uintptr_t object, const Action& action, bool empty_required, bool factory_default = false) {\n    if (!v11_fixed_fields(object, action.token, factory_default)) return false;')
                s=replace(s,'    // Mode is set by the pinned native setter only after the full identities.',
                    '    v11_initialize_fixed(object, action.token);\n    // Mode is set by the pinned native setter only after the full identities.')
                s=replace(s,'\\"fixed_subsidy_duration_years\\":%d}",',
                    '\\"fixed_subsidy_duration_years\\":%d,"\n        "\\"fixed_gift_amount_milli\\":%d,\\"fixed_transfer_fraction_milli\\":%d,\\"fixed_insult_index\\":%d}",')
                s=replace(s,'subsidy ? 1000 : 0, subsidy ? 10 : 0);',
                    'subsidy ? 1000 : 0, subsidy ? 10 : 0, request.action == ActionId::send_gift ? 25000 : 0,\n        (request.action == ActionId::request_trade_power || request.action == ActionId::cancel_trade_power_transfer) ? 500 : 0,\n        request.action == ActionId::insult ? -1 : 0);')
                s=s.replace('value < 24','value < 36').replace('i < 24','i < 36').replace('request.action) >= 24','request.action) >= 36')
            elif name=='pair-probe-v6-1375.cpp':
                s=replace(s,'    if (action.token == 0x2a25) return read_at<std::int32_t>(object + 0x40)',
                    '    if (!v11_fixed_fields(object, action.token, !fixed_subsidy)) return false;\n    if (action.token == 0x2a25) return read_at<std::int32_t>(object + 0x40)')
                s=replace(s,'        if (original_ok) {\n','        if (original_ok) {\n            v11_initialize_fixed(reinterpret_cast<std::uintptr_t>(original), action.token);\n')
                s=s.replace('\\"passed\\":12','\\"passed\\":20')
            else:
                s=replace(s,'    return action.token != 0x2a25 || (','    if (!v11_fixed_fields(object, action.token, false)) return false;\n    return action.token != 0x2a25 || (')
                s=replace(s,'    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));',
                    '    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));\n    v11_initialize_fixed(object, action.token);')
                s=replace(s,'for (unsigned mode = 0; mode < 2; ++mode)','for (unsigned mode = 0; mode < v11_mode_count(action.token); ++mode)')
                s=replace(s,'return count == 48;','return count == 72;')
            # Trace the fixed new derived fields explicitly in each case audit.
            if name != 'pair-engine-1375.cpp':
                s=replace(s,'\\"fixed_subsidy_duration_years\\":%d}",',
                    '\\"fixed_subsidy_duration_years\\":%d,"\n        "\\"fixed_gift_amount_milli\\":%d,\\"fixed_transfer_fraction_milli\\":%d,\\"fixed_insult_index\\":%d}",')
                s=replace(s,'action.token == 0x2a25 ? 10 : 0);',
                    'action.token == 0x2a25 ? 10 : 0, action.token == 0x2948 ? 25000 : 0, action.token == 0x2e09 ? 500 : 0, action.token == 0x2947 ? -1 : 0);')
                s=s.replace('char line[512]','char line[1024]').replace('char line[768]','char line[1024]')
        outputs['generated/'+name]=s.encode()
        diffs.extend(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='v10/'+name,tofile='candidate/'+name))
    outputs['action-extension.diff']=''.join(diffs).encode()
    outputs['mode-matrix.json']=(json.dumps({'schema':1,'families':20,'ids':36,'lifecycle_count':20,'preview_count':72,'command_count':72,
        'new_modes':[{'id':m[0],'ordinal':24+i,'family_index':m[1],'value':m[2]} for i,m in enumerate(MODES)],
        'cases':[{'target':target,'family_index':family,'value':positive} for target in ('ENG','POR') for family,positive in mode_rows],
        'runtime_verified':False,'execution_verified':False},indent=2)+'\n').encode()
    review={'schema':1,'purpose':'unmerged_action_extension_review_only','game_sha256':SHA,'source_v10_hashes':BASES,
        'input_report_hashes':REPORTS,'helper_hashes':{n:digest((HERE/n).read_bytes()) for n in ('binding-helpers.inc','fixed-fields.inc')},
        'method_slots':checked_slots,'prefixes':pinmap,'generated_hashes':{k:digest(v) for k,v in outputs.items()},
        'constructors':{a['name']:{'factory_block':a['factory_block_rva'],'size':a['size_bytes'],'clone':a['slots']['0xb0'],
            'destructor':a['slots']['0x0'],'token_getter':a['slots']['0x98']} for a in actions},
        'known_restrictions':['Support independence only resolves known overlord TAGs and registry vassal/client_vassal with definition11a enabled.',
            'Trade cancellation requires a single unambiguous ordinary direction; transfer ratio must be500.',
            'Insult effect observer remains unsupported; lifecycle-only research is not outcome evidence.',
            'No DLL or host or mailbox/CLI/parser/verifier integration is generated. Host matrices and whitelist must be merged independently.'],
        'runtime_verified':False,'execution_verified':False,'process_access':False}
    outputs['review.json']=(json.dumps(review,indent=2)+'\n').encode()
    check_memory_budget()
    return outputs


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');args=ap.parse_args()
    outputs=generate()
    for rel,data in outputs.items():
        path=HERE/rel
        if args.check:
            if not path.is_file() or path.read_bytes()!=data:raise ValueError('Candidate differs: '+rel)
        else:
            path.parent.mkdir(exist_ok=True);path.write_bytes(data)
    print(json.dumps({'files':len(outputs),'review_sha256':digest(outputs['review.json']),'families':20,'ids':36,'preview_cases':72,'check':args.check}))


if __name__=='__main__': main()
