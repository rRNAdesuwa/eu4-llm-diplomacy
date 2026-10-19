"""Deterministic isolated v10 candidate generation. Disk files only, never a process."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from work.native import lab_protocol_v9_1375 as old

REPORT=ROOT/'work/reports/native-pair-extension-v10-1375.json'
REPORT_SHA='0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd'
EFFECTS_REPORT=ROOT/'work/reports/native-pair-extension-effects-v10-1375.json'
EFFECTS_REPORT_SHA='b6f4b69db38f5e3eae0c3cebf1fa5298701b86a98e8299d6f0e9759b84861f62'
DLL_SHA='6C2D8420525E7E3C21F2EB20DFEA9C991B86AF8AC82211F1557F89436FDA896A'
TOOLS=['work/native/lab_protocol_v9_1375.py','work/native/record_lab_v9_build.py',
       'work/native/inject_lab_v9_1375.py','work/native/run_lab_speed_v9_1375.py','tools/request_diplomacy_lab_v9.py']
VERIFIERS=['lifecycle','preview','command']
CORE_IDS=('offer_vassalization','cancel_vassalization','royal_marriage','break_marriage',
          'improve_relations','stop_improving_relations','guarantee','revoke_guarantee',
          'build_spy_network','stop_building_spy_network')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def replace(s,before,after):
    if s.count(before)!=1:raise ValueError(f'Expected one source anchor ({s.count(before)}): {before[:100]}')
    return s.replace(before,after)
def table_append(s,table,rows):
    pos=s.index('\n};',s.index(table))
    return s[:pos]+''.join('\n'+r for r in rows)+s[pos:]

def native_changes(name,s,j):
    actions=j['actions']
    def p(rva):return j['functions'][rva]['prefix32']
    # Pin every new allocation branch, clone, destructor, shared wrapper and setter.
    pins={}
    for a in actions:
        for slot in ('0x0','0x40','0xb0','0xe0'):
            r=a['slots'][slot];pins[r]=p(r)
        r=a['factory_block_rva'];pins[r]=p(r)
    checks='\n'.join(f'    if (!extension_prefix(base + {r}, "{v}")) return false;' for r,v in pins.items())
    for a in actions:
        for slot in ('0x0','0x40','0xb0','0xe0'):
            checks+=f'\n    if (read_at<std::uintptr_t>(base + {a["vtable_rva"]} + {slot}) != base + {a["slots"][slot]}) return false;'
    common='''
// Independently pinned v10 extension ABI; no calls or process writes.
bool extension_prefix(std::uintptr_t address, const char* hex) {
    for (std::size_t i = 0; hex[i * 2] != 0; ++i) {
        const auto digit = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        if (hex[i * 2 + 1] == 0 || read_at<unsigned char>(address + i)
            != static_cast<unsigned char>((digit(hex[i * 2]) << 4) | digit(hex[i * 2 + 1]))) return false;
    }
    return true;
}
bool extension_image_pin(std::uintptr_t base) {
CHECKS
    return true;
}
'''.replace('CHECKS',checks)
    if name.endswith('pair-engine-1375.h'):
        ids=[m['action_id'] for a in actions for m in a['proposed_public_modes']]
        s=replace(s,'build_spy_network, stop_building_spy_network\n','build_spy_network, stop_building_spy_network,\n    '+',\n    '.join(', '.join(ids[i:i+2]) for i in range(0,len(ids),2))+'\n')
        s=s.replace('All ten IDs','All twenty-four IDs').replace('independent v6 lab host','independent v10 lab host')
        s=s.replace('// Exactly "FRA", "ENG", or "POR", followed by NUL.','// Fixed FRA/ENG/POR/NAV/FOI identity, followed by NUL.')
    if any(name.endswith(x) for x in ('pair-engine-1375.cpp','pair-probe-v6-1375.cpp','pair-preview-v6-1375.cpp','pair-command-v6-1375.cpp')):
        rows=[]
        for a in actions:
            q=a['slots'];n=a['name'];t=hex(a['token_id']);v=a['vtable_rva']
            if name.endswith('pair-engine-1375.cpp'):
                rows.append(f'    {{{t}, {hex(a["size"])}, {v}, {q["0xb0"]}, {q["0x0"]}, {q["0x98"]}, {q["0x80"]}, {q["0x100"]}, {q["0x108"]}, {q["0xe0"]},\n     "{p(q["0xb0"])}", "{p(q["0x80"])}"}},')
            elif name.endswith('pair-probe-v6-1375.cpp'):
                rows.append(f'    {{"{n}", {t}, {hex(a["size"])}, {v}, {q["0xb0"]}, {q["0x0"]}, {q["0x98"]}}},')
            elif name.endswith('pair-preview-v6-1375.cpp'):
                rows.append(f'    {{"{n}", {t}, {v}, {q["0x80"]}, {q["0x0"]}, {q["0x98"]}, "{p(q["0x80"])}"}},')
            else:
                rows.append(f'    {{"{n}", {t}, {v}, {q["0xb0"]}, {q["0x0"]}, {q["0x98"]}, {q["0x80"]}, {q["0x100"]}, {q["0x108"]},\n     "{p(q["0xb0"])}", "{p(q["0x80"])}"}},')
        s=table_append(s,'constexpr Action kActions[]',rows)
        imagefn='bool image_pin(' if name.endswith('pair-engine-1375.cpp') else ('bool loaded_image_matches(' if name.endswith('pair-probe-v6-1375.cpp') else 'bool image_matches(')
        pos=s.index(imagefn);s=s[:pos]+common+s[pos:]
        opening=s.index('{',s.index(imagefn))+1
        arg='module' if name.endswith('pair-engine-1375.cpp') else 'base'
        s=s[:opening]+f'\n    if (!extension_image_pin({arg})) return false;'+s[opening:]
    if name.endswith('pair-engine-1375.cpp'):
        ids=[m['action_id'] for a in actions for m in a['proposed_public_modes']]
        s=replace(s,'"build_spy_network", "stop_building_spy_network"','"build_spy_network", "stop_building_spy_network",\n    '+',\n    '.join(', '.join('"'+x+'"' for x in ids[i:i+2]) for i in range(0,len(ids),2)))
        s=s.replace('value < 10','value < 24').replace('i < 10','i < 24').replace('request.action) >= 10','request.action) >= 24')
        s=replace(s,'bool derived_fields(std::uintptr_t object, const Action& action, bool empty_required) {','bool derived_fields(std::uintptr_t object, const Action& action, bool empty_required, bool factory_default = false) {\n    if (action.token == 0x2a25) return read_at<std::int32_t>(object + 0x40) == (factory_default ? 0 : 1000)\n        && read_at<std::int32_t>(object + 0x44) == (factory_default ? 0 : 10);')
        s=replace(s,'&& read_at<std::uint32_t>(object + 0x3c) == 0 && derived_fields(object, action, true);','&& read_at<std::uint32_t>(object + 0x3c) == 0 && derived_fields(object, action, true, true);')
        s=s.replace('void initialize(std::uintptr_t object, const Live& live)', 'void initialize(std::uintptr_t object, const Action& action, const Live& live)').replace('initialize(original_address, live);','initialize(original_address, action, live);')
        s=replace(s,'    // Mode is set by the pinned native setter only after the full identities.',fixed_write()+'\n    // Mode is set by the pinned native setter only after the full identities.')
        s=replace(s,'    // Ordinary native validity handles marriage and improvement relations.',(HERE/'cancel-binding.inc').read_text(encoding='utf-8')+'\n    // Ordinary native validity handles marriage and improvement relations.')
        s=replace(s,'bool definition_name(', (HERE/'relation-helper.inc').read_text(encoding='utf-8')+'\nbool definition_name(')
        s=replace(s,'struct Country {','static_assert(sizeof(kNames) / sizeof(kNames[0]) == 2 * sizeof(kActions) / sizeof(kActions[0]), "pair modes must match families");\nstruct Country {')
        s=replace(s,'    char line[2048]{};','    char line[2048]{};\n    const bool subsidy = request.action == ActionId::give_subsidies || request.action == ActionId::cancel_subsidies;')
        s=replace(s,'\\\"freeze_session\\\":%s,\\\"retry_allowed\\\":false,\\\"applied_verified\\\":false}",','\\\"freeze_session\\\":%s,\\\"retry_allowed\\\":false,\\\"applied_verified\\\":false,"\n        "\\\"fixed_subsidy_amount_milli\\\":%d,\\\"fixed_subsidy_duration_years\\\":%d}",')
        s=replace(s,'yes(result.freeze_session));','yes(result.freeze_session), subsidy ? 1000 : 0, subsidy ? 10 : 0);')
    if name.endswith('pair-probe-v6-1375.cpp'):
        s=s.replace('const Action& action, std::uintptr_t base) {','const Action& action, std::uintptr_t base, bool fixed_subsidy = false) {')
        s=replace(s,'    if (action.size == 0x68) {','    if (action.token == 0x2a25) return read_at<std::int32_t>(object + 0x40) == (fixed_subsidy ? 1000 : 0)\n        && read_at<std::int32_t>(object + 0x44) == (fixed_subsidy ? 10 : 0);\n    if (action.size == 0x68) {')
        s=replace(s,'        if (original_ok) {\n            copy =','        if (original_ok) {\n            if (action.token == 0x2a25) {\n                const std::int32_t amount = 1000, years = 10;\n                std::memcpy(static_cast<unsigned char*>(original) + 0x40, &amount, sizeof(amount));\n                std::memcpy(static_cast<unsigned char*>(original) + 0x44, &years, sizeof(years));\n            }\n            copy =')
        s=s.replace('default_fields_match(reinterpret_cast<std::uintptr_t>(copy), action, base);','default_fields_match(reinterpret_cast<std::uintptr_t>(copy), action, base, true)\n                && default_fields_match(reinterpret_cast<std::uintptr_t>(original), action, base, true);')
        s=s.replace('\\"passed\\":5','\\"passed\\":12')
    if name.endswith('pair-preview-v6-1375.cpp') or name.endswith('pair-command-v6-1375.cpp'):
        s=s.replace('return count == 20;', 'return count == 48;')
        s=replace(s,'    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));','    write_owned(object, 0x3c, static_cast<std::uint32_t>(0));\n'+fixed_write())
        needle='bool initialize_owned(' if name.endswith('pair-preview-v6-1375.cpp') else 'bool fields_match('
        pos=s.index(needle)
        helper='''bool fixed_parameters_match(std::uintptr_t object, const Action& action) {
    return action.token != 0x2a25 || (read_at<std::int32_t>(object + 0x40) == 1000
        && read_at<std::int32_t>(object + 0x44) == 10);
}
'''
        s=s[:pos]+helper+s[pos:]
        if name.endswith('pair-preview-v6-1375.cpp'):
            s=replace(s,'== static_cast<unsigned char>(value ? 1 : 0);','== static_cast<unsigned char>(value ? 1 : 0) && fixed_parameters_match(object, action);')
            s=replace(s,'allowed = reinterpret_cast<Preview>(base + kPreview)(owned, nullptr, false);','allowed = reinterpret_cast<Preview>(base + kPreview)(owned, nullptr, false);\n                initialized = initialized && fixed_parameters_match(address, action);')
        else:
            s=s.replace('bool fields_match(std::uintptr_t object, const State& state, bool value)', 'bool fields_match(std::uintptr_t object, const Action& action, const State& state, bool value)')
            for obj in ('object','clone_address','original_address'):s=s.replace(f'fields_match({obj}, state, value)',f'fields_match({obj}, action, state, value)')
            s=replace(s,'&& read_at<std::uint32_t>(object + 0x3c) == 0;','&& read_at<std::uint32_t>(object + 0x3c) == 0 && fixed_parameters_match(object, action);')
            s=replace(s,'&& action_identity(base, original_address, action);\n                    }','&& action_identity(base, original_address, action)\n                            && fixed_parameters_match(clone_address, action) && fixed_parameters_match(original_address, action);\n                    }')
        s=s.replace('// Retain every derived default, particularly the marriage string/+0x60.','// Retain marriage defaults; only fixed, independently evidenced subsidy scalars differ.')
        s=s.replace('// Derived factory defaults, including marriage EngineString32/+0x60,\n    // remain engine-initialized. No guessed derived fields are written.','// Marriage defaults remain engine-initialized. Subsidy uses fixed research scalars only.')
    if name.endswith('test-lab-request-1375.cpp'):s=s.replace('index < 10','index < 24')
    if name.endswith('pair-probe-v6-1375.cpp'):
        s=replace(s,'"\\\"clone_destroyed\\\":%s,\\\"exception\\\":%lu,\\\"submitted\\\":false}",','"\\\"clone_destroyed\\\":%s,\\\"exception\\\":%lu,\\\"submitted\\\":false,"\n                  "\\\"fixed_subsidy_amount_milli\\\":%d,\\\"fixed_subsidy_duration_years\\\":%d}",')
        s=replace(s,'copy_destroyed ? "true" : "false", exception);','copy_destroyed ? "true" : "false", exception, action.token == 0x2a25 ? 1000 : 0, action.token == 0x2a25 ? 10 : 0);')
    if name.endswith('pair-preview-v6-1375.cpp') or name.endswith('pair-command-v6-1375.cpp'):
        boundary=s.index('} // namespace')
        first=s[:boundary]
        first=replace(first,'\\\"thread_id\\\":%lu,\\\"submitted\\\":false}",','\\\"thread_id\\\":%lu,\\\"submitted\\\":false,"\n        "\\\"fixed_subsidy_amount_milli\\\":%d,\\\"fixed_subsidy_duration_years\\\":%d}",')
        first=replace(first,'GetCurrentThreadId());','GetCurrentThreadId(), action.token == 0x2a25 ? 1000 : 0, action.token == 0x2a25 ? 10 : 0);')
        s=first+s[boundary:]
    return s

def fixed_write():
    return '''    // Fixed research contract: monthly 1.000 ducat, duration 10 YEARS.
    // No external amount, years, offsets or raw fields are accepted.
    if (action.token == 0x2a25) {
        write_owned(object, 0x40, static_cast<std::int32_t>(1000));
        write_owned(object, 0x44, static_cast<std::int32_t>(10));
    }'''

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');args=ap.parse_args()
    if sha(REPORT.read_bytes())!=REPORT_SHA:raise ValueError('Extension report changed')
    if sha(EFFECTS_REPORT.read_bytes())!=EFFECTS_REPORT_SHA:raise ValueError('Cancellation evidence changed')
    j=json.loads(REPORT.read_text(encoding='utf-8'))
    manifest,_=old.verify_build()
    if manifest['dll_sha256']!=DLL_SHA:raise ValueError('Frozen v9 DLL differs')
    frozen={}
    for version in ('v6','v7','v8','v9'):
        for f in (ROOT/f'work/native/{version}').glob('*'):
            if f.is_file():frozen[f.relative_to(ROOT).as_posix()]=sha(f.read_bytes())
        for f in (ROOT/'work/native').glob(f'test-fixture-{version}-1375.*'):frozen[f.relative_to(ROOT).as_posix()]=sha(f.read_bytes())
        for leaf in (f'eu4_pair_lab_{version}_1375.dll','build.json'):
            f=ROOT/f'work/runtime/native1375-{version}/{leaf}'
            if f.exists():frozen[f.relative_to(ROOT).as_posix()]=sha(f.read_bytes())
    for n in old.FIXTURE_SOURCES:
        f=old.fixture_source_path(ROOT,n);frozen[f.relative_to(ROOT).as_posix()]=sha(f.read_bytes())
    snapshot=HERE/'frozen-before.json'
    if snapshot.exists():
        if json.loads(snapshot.read_text())!=frozen:raise ValueError('A frozen native/build/fixture file changed')
    elif args.check:raise ValueError('No frozen snapshot')
    else:snapshot.write_text(json.dumps(frozen,indent=2,sort_keys=True)+'\n')
    candidates={}
    for n in list(old.SOURCES)+TOOLS+['work/native/v9/test-lab-request-1375.cpp','work/native/v9/test-lab-request-1375.cmd']:
        s=(ROOT/n).read_text(encoding='utf-8').replace('v9','v10')
        s=native_changes(n,s,j)
        if n.endswith('lab_protocol_v9_1375.py'):
            s=s.replace('import ACTIONS, _no_links','import _no_links')
            ids=tuple(m['action_id'] for a in j['actions'] for m in a['proposed_public_modes'])
            pos=s.index('\nPROTOCOL =')
            s=s[:pos]+'\n# Frozen v10 request allowlist; future production/backend additions cannot widen it.\nACTIONS = frozenset('+repr(CORE_IDS+ids)+')\nFIXED_RESEARCH_PARAMETERS = {"give_subsidies": {"monthly_amount": "1.000", "duration_years": 10}, "cancel_subsidies": {"monthly_amount": "1.000", "duration_years": 10}}\n'+s[pos:]
            for v in VERIFIERS:s=s.replace('tools.verify_diplomacy_'+v,'tools.verify_diplomacy_'+v+'_v10')
            s=replace(s,'"Pair core record differs from request/world")', '"Pair core record differs from request/world")\n                        subsidy = request["action"] in FIXED_RESEARCH_PARAMETERS\n                        require(type(core.get("fixed_subsidy_amount_milli")) is int and core["fixed_subsidy_amount_milli"] == (1000 if subsidy else 0)\n                                and type(core.get("fixed_subsidy_duration_years")) is int and core["fixed_subsidy_duration_years"] == (10 if subsidy else 0),\n                                "Pair core fixed research parameters differ")')
        if n.endswith('request_diplomacy_lab_v9.py'):
            s=s.replace('Only the ten pair entrypoints and speed control','Reviewed historical entrypoints and speed control; v10 candidate scope is reported separately')
            s=replace(s,'            historical.update(invoked_cli_protocol=lab.PROTOCOL, v10_live_readiness=None)', '            historical.update(invoked_cli_protocol=lab.PROTOCOL, v10_live_readiness=None,\n                v10_candidate={"action_ids": sorted(lab.ACTIONS), "fixed_research_parameters": lab.FIXED_RESEARCH_PARAMETERS,\n                               "runtime_verified": False, "production_backend_registered": False})')
            s=replace(s,'            if args.operation == "fixture":\n                summary', '            if args.operation == "pair":\n                summary["fixed_research_parameters"] = lab.FIXED_RESEARCH_PARAMETERS.get(args.action, {})\n            if args.operation == "fixture":\n                summary')
        candidates[n.replace('v9','v10')]=s.encode('utf-8')
    for v in VERIFIERS:
        n='tools/verify_diplomacy_'+v+'.py';s=(ROOT/n).read_text(encoding='utf-8')
        s=s.replace('verify_diplomacy_lifecycle as lifecycle','verify_diplomacy_lifecycle_v10 as lifecycle').replace('verify_diplomacy_preview as preview','verify_diplomacy_preview_v10 as preview')
        if v=='lifecycle':
            s=replace(s,'"guaranteeaction": 64, "spy_network": 64}', '"guaranteeaction": 64, "spy_network": 64, '+', '.join(repr(a['name'])+': '+str(a['size']) for a in j['actions'])+'}')
            s=s.replace('== 5, "Lifecycle suite passed count must be 5"','== 12, "Lifecycle suite passed count must be 12"').replace('exactly the five required','exactly the twelve required')
            s=replace(s,'            self.lifecycle[action] =', '            self.check(type(event.get("fixed_subsidy_amount_milli")) is int and event["fixed_subsidy_amount_milli"] == (1000 if action == "warsubsidy" else 0), "Fixed subsidy amount evidence differs", line)\n            self.check(type(event.get("fixed_subsidy_duration_years")) is int and event["fixed_subsidy_duration_years"] == (10 if action == "warsubsidy" else 0), "Fixed subsidy years evidence differs", line)\n            self.lifecycle[action] =')
        else:
            s=s.replace('== 20','== 48').replace('<= 20','<= 48').replace('("cases", 20)','("cases", 48)').replace('1..20','1..48').replace('twenty','forty-eight').replace('Twenty','Forty-eight').replace('five-family','twelve-family')
            if v=='preview':s=replace(s,'            date = event.get("current_raw_date")','            self.check(type(event.get("fixed_subsidy_amount_milli")) is int and event["fixed_subsidy_amount_milli"] == (1000 if action == "warsubsidy" else 0), "Fixed subsidy amount evidence differs", line)\n            self.check(type(event.get("fixed_subsidy_duration_years")) is int and event["fixed_subsidy_duration_years"] == (10 if action == "warsubsidy" else 0), "Fixed subsidy years evidence differs", line)\n            date = event.get("current_raw_date")')
        pos=s.index('\ndef main(')
        verify_pos=s.index('\ndef verify(')
        if v=='lifecycle':
            s=s[:verify_pos]+'\n'+(HERE/'verifier-api.inc.py').read_text(encoding='utf-8')+s[pos:]
            s=s.replace('Five distinct lifecycle records are required','Twelve distinct lifecycle records are required')
        else:
            s=s[:verify_pos]+f'\ndef verify(log: Path, pid: int, before: Path, after: Path, build_manifest: Path):\n    return lifecycle.verify_phase("{v}",log,pid,before,after,build_manifest)\n\n'+s[pos:]
        pos=s.index('\ndef main(')
        s=s[:pos]+'''
def main(argv=None):
    """Read an explicitly identified v10 session; never opens a game process."""
    from work.native import lab_protocol_v10_1375 as lab
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid",type=int,required=True)
    parser.add_argument("--creation",required=True)
    args=parser.parse_args(argv)
    try:
        manifest,manifest_sha=lab.verify_build()
        session=lab.session_path(lab.OUTPUT,args.pid,args.creation)
        metadata=lab.read_session_metadata(session,args.pid,args.creation)
        result=lab.read_evidence(session,metadata)
        proof=result["phase_proofs"].get("PHASE")
        print(json.dumps({"purpose":lab.PURPOSE,"phase":"PHASE","proof":proof,
            "dll_sha256":manifest["dll_sha256"],"manifest_sha256":manifest_sha,
            "log_sha256":result["log_sha256"],"game_process_accessed":False,
            "applied_verified":False,"production_backend_registered":False},indent=2))
        return 0 if proof and proof["passed"] else 1
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print(str(error),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
'''.replace('PHASE',v)
        candidates[n.replace('.py','_v10.py')]=s.encode('utf-8')
    for n in old.FIXTURE_SOURCES:
        candidates['work/candidates/fixture-v10-1375/'+n]=old.fixture_source_path(ROOT,n).read_bytes()
    candidates['work/candidates/fixture-v10-1375/fixture-profile.json']=(ROOT/'work/candidates/fixture-v9-1375/fixture-profile.json').read_bytes()
    for n,raw in candidates.items():
        f=ROOT/n
        if args.check:
            if not f.exists() or f.read_bytes()!=raw:raise ValueError('Generated candidate differs: '+n)
        else:
            # Preserve already matching frozen native/DLL-attested files even
            # while updating independent Python-only verification helpers.
            if not f.exists() or f.read_bytes()!=raw:
                if n in {x.replace('v9','v10') for x in old.SOURCES} and (ROOT/'work/runtime/native1375-v10/build.json').exists():
                    raise ValueError('Refusing to rewrite an already built v10 native source: '+n)
                f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
    review={'static_only':True,'frozen_files_unchanged':len(frozen),'candidate_files':len(candidates),'extension_report_sha256':REPORT_SHA,'effects_report_sha256':EFFECTS_REPORT_SHA,'candidate_sha256':{n:sha(b) for n,b in candidates.items()},'native_count':14,'family_count':12,'public_action_count':24,'preview_cases':48,'command_cases':48,'fixed_subsidy':{'monthly_amount_milli':1000,'duration_years':10},'fixture_profile_sha256':old.FIXTURE_PROFILE_SHA256,'no_process_operations':True}
    if not args.check:(HERE/'source-review.json').write_text(json.dumps(review,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in review.items() if k!='candidate_sha256'}))

if __name__=='__main__':main()
