"""Export exact script conditions and compiled native check locations; files only."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import GAME_SHA, TagCommandBackend, decode, digest, encode, read, require
from tools.build_diplomacy_catalog import parse_script
from tools.install_diplomacy_unlock_mod import verify_source

BASE = ROOT / 'work/runtime/unpacked-1.37.5/base'
MOD = ROOT / 'mod/llm_diplomacy_unlock'
OUTPUT = ROOT / 'bridge/tag_action_conditions_1375.json'
LOCAL_INDEX = ROOT / 'work/runtime/tag31-local-condition-index-20261013.json'
RESEARCH_FILES = (
    'work/reports/rea-api-discovery-20261013/prior-four-findings.json',
    'work/reports/rea-api-discovery-20261013/conditions/findings.json',
    'work/reports/rea-api-discovery-20261013/cancellations/findings.json',
)
FILES = ('common/diplomatic_actions/00_diplomatic_actions.txt',
         'common/new_diplomatic_actions/00_diplomatic_actions.txt')


def clause(node):
    result = dict(key=node.key, line=node.line)
    if node.value is not None:
        result['value'] = node.value
    else:
        result['children'] = [clause(n) for n in node.children]
    return result


def research_findings(scope):
    """Retain reviewed observations/inferences with exact, bounded file sources."""
    findings, pins = [], {}
    def pin(name):
        require(type(name) is str and not Path(name).is_absolute()
                and '..' not in Path(name).parts and '\\' not in name,
                'Invalid research evidence path')
        path = ROOT/name
        require(path.resolve().is_relative_to(ROOT.resolve()), 'Research evidence escapes root')
        raw = read(path, 4*1024*1024)
        expected = dict(sha256=digest(raw), bytes=len(raw))
        require(name not in pins or pins[name] == expected, 'Research evidence changed during build')
        pins[name] = expected
        return raw
    for source in RESEARCH_FILES:
        data = decode(pin(source))
        require(data['game_sha256'] == GAME_SHA and type(data['findings']) is list,
                'Research findings have wrong target')
        for f in data['findings']:
            require(set(f) == {'id','actions','kind','summary','rvas','unknowns','evidence_files'}
                    and type(f['id']) is str and re.fullmatch(r'[a-z0-9_-]{1,96}',f['id'])
                    and type(f['actions']) is list and f['actions']
                    and all(type(a) is str and a in scope for a in f['actions'])
                    and len(set(f['actions'])) == len(f['actions'])
                    and f['kind'] in ('observation','inference')
                    and type(f['summary']) is str and f['summary']
                    and type(f['rvas']) is list and f['rvas']
                    and all(type(r) is str and re.fullmatch(r'0x[0-9a-f]+',r) for r in f['rvas'])
                    and type(f['unknowns']) is list
                    and all(type(u) is str and u for u in f['unknowns'])
                    and type(f['evidence_files']) is list and f['evidence_files'],
                    'Malformed native research finding')
            for name in f['evidence_files']:
                pin(name)
            findings.append(dict(f, source=source, evaluated_in_game=False,
                                 native_logic_complete=False, historical_failure_branch_proven=False))
    require(len({f['id'] for f in findings}) == len(findings), 'Duplicate research finding ID')
    return findings, pins


def local_condition_index(backend, profile_source, profiles):
    """Join bounded offline references; never interpret references as predicates."""
    raw = read(LOCAL_INDEX, 1024*1024)
    index = decode(raw)
    require(index['schema'] == 'EU4TAG31-LOCAL-CONDITION-INDEX/1'
            and index['game_sha256'] == GAME_SHA
            and index['file_only'] is True and index['game_process_accessed'] is False
            and index['native_calls'] == 0 and index['runtime_verified'] is False,
            'Unexpected local-condition index provenance')
    require(index['registry_source'] == profile_source
            and index['registry_sha256'] == digest(read(ROOT/profile_source, 1024*1024)),
            'Local-condition index and compiled profiles differ')
    families = {int(f['vtable_rva'], 16):f for f in index['families']}
    require(len(families) == len(index['families']) == 51
            and set(families) == set(profiles), 'Local-condition family set differs')
    for vtable, family in families.items():
        profile = profiles[vtable]
        require(family['vtable_local80_matches_registry'] is True
                and int(family['entry_rva'], 16) == int(profile['local_check_rva'], 16)
                and int(family['full88_rva'], 16) == int(profile['full_check_rva'], 16)
                and family['coverage']['native_logic_complete'] is False
                and all(ref['is_taken_failure_branch_proven'] is False
                        for ref in family['localization_key_references'])
                and all(call['followed'] is False for call in family['direct_calls']),
                'Local-condition locations or completeness changed')
    indexed_actions = {a['action']:a for a in index['actions']}
    require(len(indexed_actions) == len(index['actions']) == 120
            and set(indexed_actions) == set(backend.actions), 'Local-condition action set differs')
    for binding in backend.bindings:
        action = indexed_actions[binding['action']]
        require(action['conditions_complete'] is False, 'Local conditions claim completeness')
        if binding.get('route') == 'independent_command':
            require(action.get('outside_pair_family_index') is True
                    and action['family'] is None and action['local80_rva'] is None,
                    'Independent action unexpectedly has pair-family conditions')
        else:
            require(action['positive_mode'] is binding['mode']
                    and (action.get('script_key') or '') == binding['script_key'],
                    'Local-condition action mode or script key differs')
    return dict(path=LOCAL_INDEX.relative_to(ROOT).as_posix(), sha256=digest(raw), bytes=len(raw)), \
        dict(schema=index['schema'], evaluated_in_game=False, native_logic_complete=False,
             evidence_kind='offline_instruction_references_not_decoded_predicates_or_taken_branches',
             limits=index['limits'], limitations=index['limitations'], statistics=index['statistics'],
             families={f['family']:f for f in families.values()}), indexed_actions, families


def build():
    backend = TagCommandBackend()
    catalog_raw = read(ROOT/'bridge/diplomacy_catalog.json', 4*1024*1024)
    catalog = decode(catalog_raw)
    source_pins = {v['path']:v['sha256'].lower() for v in catalog['sources']}
    catalog = {v['action_id']:v for v in catalog['actions']}
    verify_source(MOD)
    trees, pins = {}, {}
    for kind, root in (('original', BASE), ('configured_test_mod', MOD)):
        trees[kind], pins[kind] = {}, {}
        for name in FILES:
            raw = read(root/name, 1024*1024)
            if kind == 'original':
                require(digest(raw) == source_pins[name], 'Original source differs from catalog')
            nodes = parse_script(raw.decode('utf-8-sig'))
            require(len({n.key for n in nodes}) == len(nodes), 'Duplicate action definition')
            trees[kind][name] = {n.key:n for n in nodes}
            pins[kind][name] = dict(sha256=digest(raw), bytes=len(raw))
    profile_source = next(name for name in backend.manifest['source_pins']
                          if name.endswith('/v24-pair-send-core-r2-1375/pair_send.cpp'))
    text = read(ROOT/profile_source, 1024*1024).decode('utf-8')
    profiles = {}
    for match in re.finditer(r'\{Family::(\w+),((?:0x[0-9a-f]+,){8})FullCallerEvidence::(\w+),(0x[0-9a-f]+)\}', text):
        numbers = [int(v, 16) for v in match[2].strip(',').split(',')]
        profiles[numbers[2]] = dict(local_check_rva=hex(numbers[6]), full_check_rva=hex(numbers[7]),
            vtable_rva=hex(numbers[2]), profile_family=match[1], token_id=numbers[0],
            object_size_bytes=numbers[1], clone_rva=hex(numbers[3]),
            destructor_rva=hex(numbers[4]), setter_rva=hex(numbers[5]),
            command_wrapper_rva=match[4], full_caller_evidence=match[3],
            address_space='rva_for_game_sha256_only')
    require(len(profiles) == 51, 'Compiled native profile count changed')
    index_pin, index, indexed_actions, families = local_condition_index(backend, profile_source, profiles)
    pins['native_local_condition_index'] = {index_pin.pop('path'):index_pin}
    profile_raw = read(ROOT/profile_source, 1024*1024)
    pins['native_profile'] = {profile_source:dict(sha256=digest(profile_raw), bytes=len(profile_raw))}
    header_source = next(name for name in backend.manifest['source_pins']
                         if name.endswith('/v21-core-pair-nosend-r2-1375/pair_component.h'))
    header_raw = read(ROOT/header_source, 1024*1024)
    require(b'token, size, vtable, clone, destructor, setter, local80, full88;' in header_raw,
            'Compiled profile field order changed')
    pins['native_profile'][header_source] = dict(sha256=digest(header_raw), bytes=len(header_raw))
    pins['native_catalog'] = {'bridge/diplomacy_catalog.json':dict(sha256=digest(catalog_raw),bytes=len(catalog_raw))}
    scope = set(backend.actions) | {a['action'] for a in backend.excluded}
    findings, pins['native_research'] = research_findings(scope)
    actions = {}
    for binding in backend.bindings:
        action = binding['action']
        scripted = bool(binding['script_key'])
        name = binding['script_key'] or binding['native_family']
        source = FILES[1 if scripted else 0]
        fields = {'is_visible', 'is_allowed', 'require_acceptance'} if scripted else {'condition'}
        record = dict(binding=binding, complete_legality_documented=False,
                      source_condition_kind='scripted_action' if scripted else 'native_additional_conditions',
                      script_conditions={})
        for kind in trees:
            node = trees[kind][source].get(name)
            record['script_conditions'][kind] = dict(path=source,
                definition_line=node.line if node else None,
                clauses=[clause(c) for c in node.children if c.key in fields] if node else [])
        if binding.get('route') == 'independent_command':
            record['native_check'] = dict(route='independent_command', local_conditions_decoded=False,
                                         local_condition_family=None, native_logic_complete=False)
        else:
            variants = [v for v in catalog[action]['native_mapping']['variants']
                        if v['name'] == binding['native_family']]
            require(len(variants) == 1, 'Native family is ambiguous: '+action)
            vtable = int(variants[0]['vtable_rva'], 16)
            require(vtable in profiles, 'Missing compiled profile: '+action)
            family = families[vtable]
            require(indexed_actions[action]['family'] == family['family']
                    and int(indexed_actions[action]['local80_rva'], 16)
                        == int(profiles[vtable]['local_check_rva'], 16),
                    'Local-condition action family differs: '+action)
            record['native_check'] = dict(profiles[vtable], local_condition_family=family['family'],
                                         native_logic_complete=False)
        actions[action] = record
    require(len(actions) == 120, 'Conditions/action count mismatch')
    return dict(schema='EU4TAG-CONDITIONS/1', game_sha256=GAME_SHA,
        registry_sha256=digest(read(backend.config_path, 1024*1024)),
        native_manifest_sha256=backend.manifest_sha,
        test_mod_manifest_sha256=digest(read(MOD/'unlock-manifest.json', 1024*1024)),
        source_pins=pins, evaluated_in_game=False, complete_legality_documented=False,
        native_logic_complete=False, native_local_condition_index=index,
        native_research_findings=findings,
        limitations=[
            'Script clauses are part of legality, not every native requirement.',
            'Configured test mod means repository files; this does not prove that a running game loaded them.',
            'Native full checks also include country roles, dates, resources, existing relations and local checks.',
            'A failed full check does not reveal which branch rejected the historical request.',
            'Offline localization keys and calls are research leads, not decoded conditions or observed failure branches.',
            'Closed bounded local instruction coverage still omits callees and never proves complete native legality.',
            'No process is opened and no native check or diplomatic action is called.'
        ], common_native_checks=[
            dict(kind='strict_pair_deadline', condition='current raw date > stored pair deadline when the action requires this check',
                 evidence='work/runtime/tag31-cooldown-static-20261013.json'),
            dict(kind='available_envoy_and_costs', condition='The native action decides whether an envoy and its specific costs are required',
                 evidence='docs/native-command-1375.md'),
            dict(kind='family_local_legality', condition='The family local check must also pass; script overrides do not replace it',
                 evidence='work/runtime/tag31-native-rejection-leaf-20261013.json')
        ], actions=actions)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    raw = encode(build())
    if args.check:
        require(read(OUTPUT, 2*1024*1024) == raw, 'Conditions reference is stale')
    else:
        OUTPUT.write_bytes(raw)
    print('120 action condition records; files only, no game evaluation')


if __name__ == '__main__':
    main()
