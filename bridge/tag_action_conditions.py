"""Read condition documentation without inspecting or invoking the game."""
from bridge.tag_command_backend import GAME_SHA, ROOT, decode, digest, read, require


def verify_pinned_sources(document):
    roots = {'original':ROOT/'work/runtime/unpacked-1.37.5/base',
             'configured_test_mod':ROOT/'mod/llm_diplomacy_unlock',
             'native_local_condition_index':ROOT, 'native_profile':ROOT,
             'native_catalog':ROOT, 'native_research':ROOT}
    require(set(document['source_pins']) == set(roots), 'Condition source pin groups differ')
    for kind, root in roots.items():
        for relative, pin in document['source_pins'][kind].items():
            path = root/relative
            require(path.resolve().is_relative_to(root.resolve()), 'Condition source escapes its root')
            raw = read(path, (4 if kind in ('native_catalog','native_research') else 1)*1024*1024)
            require(len(raw) == pin['bytes'] and digest(raw) == pin['sha256'],
                    'Condition documentation source changed: '+relative)
    # The manifest pin covers all generated files, including the special-subject
    # helper. Verify its files too: an unchanged manifest alone cannot prove that
    # the configured test Mod still contains those bytes.
    mod_root = roots['configured_test_mod']
    raw = read(mod_root/'unlock-manifest.json', 1024*1024)
    require(document['test_mod_manifest_sha256'] == digest(raw),
            'Configured test Mod conditions changed; regenerate reference')
    manifest = decode(raw)
    require(manifest['exe_sha256'] == GAME_SHA and manifest['runtime_verified'] is False,
            'Unexpected configured test Mod provenance')
    for relative, pin in manifest['files'].items():
        path = mod_root/relative
        require(path.resolve().is_relative_to(mod_root.resolve()), 'Mod source escapes its root')
        content = read(path, 1024*1024)
        require(len(content) == pin['bytes'] and digest(content) == pin['sha256'],
                'Configured test Mod bytes changed: '+relative)
    actual = {p.relative_to(mod_root).as_posix() for p in mod_root.rglob('*') if p.is_file()}
    require(actual == set(manifest['files']) | {'unlock-manifest.json'},
            'Unexpected configured test Mod files')


def load_condition_document(backend):
    """Own the verified file reference shared by condition and API lookup views."""
    require(backend.purpose == 'tag_command_1375_v31', 'Conditions are documented for V31 only')
    document = decode(read(ROOT/'bridge/tag_action_conditions_1375.json', 2*1024*1024))
    require(document['schema'] == 'EU4TAG-CONDITIONS/1' and document['game_sha256'] == GAME_SHA
            and document['registry_sha256'] == digest(read(backend.config_path, 1024*1024))
            and document['native_manifest_sha256'] == backend.manifest_sha,
            'Condition documentation and native build differ')
    verify_pinned_sources(document)
    return document


def action_conditions(backend, action):
    require(action in backend.actions, 'Action has no native binding in this host')
    document = load_condition_document(backend)
    family = document['actions'][action]['native_check']['local_condition_family']
    index = document['native_local_condition_index']
    evidence = dict(evaluated_in_game=False, native_logic_complete=False,
                    evidence_kind=index['evidence_kind'], limits=index['limits'],
                    limitations=index['limitations'],
                    family=index['families'][family] if family else None)
    return dict(action=action, evaluated_in_game=False, complete_legality_documented=False,
                native_logic_complete=False, native_local_condition_evidence=evidence,
                native_research_findings=[f for f in document['native_research_findings']
                                          if action in f['actions']],
                common_native_checks=document['common_native_checks'],
                limitations=document['limitations'], record=document['actions'][action],
                source_pins=document['source_pins'])
