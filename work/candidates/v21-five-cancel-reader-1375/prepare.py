"""Reproducible, bounded, file-only evidence projection. No new disassembly."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAX_FILE = 4 * 1024 * 1024
OWN = ('cancel_reader.h', 'cancel_reader.cpp', 'test_cancel_reader.cpp', 'test_reader_budget.cpp',
       'build_test.cmd', 'validate.py', 'prepare.py', 'seal.py', 'README.md', 'input-pins.json',
       'evidence.json', 'preimages/cancel-reader-root-draft.h', 'preimages/cancel-reader-root-draft.cpp')
EFFECT = 'work/reports/native-pair-effects-1375.json'
CANCEL = 'work/reports/native-pair-cancel-1375.json'
CURRY = 'work/candidates/curry-favors-observer-1375/report.json'
COUNTRY = 'work/candidates/current-country-tag-resolver-1375/report.json'
FIXTURE = 'work/reports/native-test-fixture-1375.json'


def read(path):
    with Path(path).open('rb') as f:
        raw = f.read(MAX_FILE + 1)
    assert len(raw) <= MAX_FILE, path
    return raw


def desc(path):
    raw = read(path)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode('ascii')


def seal(path, value):
    raw = encoded(value)
    with Path(path).open('xb') as f:
        f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def inputs():
    result = json.loads(read(HERE / 'input-pins.json'))['files']
    for name, expected in result.items():
        assert desc(ROOT / name) == expected, name
    return result


def evidence():
    pinned = inputs()
    documents = {p: json.loads(read(ROOT / p)) for p in (EFFECT, CANCEL, CURRY, COUNTRY, FIXTURE)}
    groups = []

    def fact(path, key):
        value = documents[path]['facts'][key]
        groups.append({'source': path, 'json_pointer': '/facts/' + str(key), 'value': value})

    for key in ('relation_lookup', 'relation_common', 'improve_apply', 'improve_cancel',
                'guarantee_apply_cancel', 'marriage_accept_cancel', 'vassal_accept_cancel',
                'overlord_observation', 'envoy_mission_identity', 'envoy_status_limit'):
        fact(EFFECT, key)
    for key in ('improve_cancel_envoy', 'guarantee_cancel_direction', 'marriage_cancel',
                'vassal_cancel', 'subject_definition_identity'):
        fact(CANCEL, key)
    for i in range(5):
        fact(CURRY, i)
    for key in ('country', 'ordinal', 'lookup', 'player', 'research_filters', 'known_limit'):
        fact(COUNTRY, key)
    # Copy only existing instruction records. Every record retains its exact
    # original JSON pointer. No capstone, PE read, address search, or new decode.
    anchors = []

    def instruction(path, function, index):
        row = documents[path]['functions'][function]['instructions'][index]
        anchors.append({'source': path, 'json_pointer': '/functions/' + function + '/instructions/' + str(index),
                        'record': row})

    for key in ('0x6fec50', '0x6fec80', '0x6ff4e0', '0xc9f10', 'country_manager_vector_slice'):
        for i in range(len(documents[CURRY]['functions'][key]['instructions'])):
            instruction(CURRY, key, i)
    # Link allocation and entry/mission identity, not the entire settling CFG.
    for i, row in enumerate(documents[CURRY]['functions']['0x4e7550']['instructions']):
        if 0x4e7550 <= int(row['rva'], 16) < 0x4e7600 or 0x4e771a <= int(row['rva'], 16) <= 0x4e77e0:
            instruction(CURRY, '0x4e7550', i)
    # Country constructor explicitly initializes the holder vector empty before
    # append0/1/2/3. This closes the fourth-manager premise without new decode.
    for i in list(range(16)) + [161, 524, 525, 526, 1137]:
        instruction(FIXTURE, '0x2c9960', i)
    constructors = {k: documents[EFFECT]['vtable_checks'][k]
                    for k in ('improve', 'guarantee', 'marriage', 'vassal', 'mission')}
    profiles = {
        'Vassal': {'left_index': 0x128, 'right_index': 0x128, 'relation_vtable': 0x1c81758,
                   'role': 'actor_overlord_target_subject', 'definition': 'registry58_vassal_or60_client_vassal_plus_exact_name'},
        'Marriage': {'left_index': 0x68, 'right_index': 0x68, 'relation_vtable': 0x1c80be0,
                     'role': 'symmetric_relation_but_observation_normalized_to_requested_actor_target'},
        'Improve': {'left_index': 0x1d0, 'right_index': 0x1e8, 'relation_vtable': 0x1c81658,
                    'role': 'actor_outgoing_target_incoming', 'mission_token': 0x2ddb, 'allowed_entry_states': [1, 2]},
        'Guarantee': {'left_index': 0x1a0, 'right_index': 0x1a0, 'relation_vtable': 0x1c817d8,
                      'role': 'actor_guarantor_target_beneficiary'},
        'Curry': {'left_index': 0x158, 'right_index': None, 'relation_vtable': 0x1c7b178,
                  'role': 'actor_outgoing_only_no_reciprocal_index_assertion', 'mission_token': 0x3acc, 'allowed_entry_states': [2]}}
    assert constructors['improve']['computed_vtable_rva'] == hex(profiles['Improve']['relation_vtable'])
    return {'schema_version': 1, 'purpose': 'five_negative_graph_reader_existing_static_evidence_projection',
            'game_sha256': '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
            'sources': {p: pinned[p] for p in documents}, 'profiles': profiles,
            'facts': groups, 'instruction_anchors': anchors, 'relation_vtable_constructors': constructors,
            'curry_vtable_data': documents[CURRY]['vtable_pins'],
            'country_type_data': documents[COUNTRY]['vtable_data'],
            'reused_instruction_records': len(anchors),
            'reused_instruction_bytes_including_overlap': sum(len(bytes.fromhex(r['record']['bytes'])) for r in anchors),
            'new_decode_bytes': 0, 'executable_read_this_task': False,
            'static_evidence_scope': 'inherited exact-build report bytes; this candidate revalidates source hashes and exact JSON projection, not a fresh PE scan',
            'private_limits': {'index_capacity': 4096, 'envoy_capacity': 256, 'holder_capacity': 16,
                               'name_length': 128, 'single_read_bytes': 32768, 'calls_per_two_pass': 20000,
                               'bytes_per_two_pass': 524288},
            'unsupported': ['SpyNetwork (separate binder)', 'unknown entry/manager/mission/relation subclass or marker',
                            'ordinary-handle profile violations, missing graphs, removed objects, divergent observations',
                            'OS identity/module/exe attestation, current loaded instruction byte verification',
                            'SP/world epoch/lifetime synchronization, no-same-value-ABA guarantee',
                            'legality, cooldown, truce, resource availability, AI acceptance or any native permission'],
            'runtime_verified': False, 'native_ready': False, 'production_ready': False}


def own():
    return {n: desc(HERE / n) for n in OWN}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    before = inputs()
    value = evidence()
    if args.check:
        assert read(HERE / 'evidence.json') == encoded(value)
        assert json.loads(read(HERE / 'source-index.json')) == own()
        if (HERE / 'review.json').exists():
            review = json.loads(read(HERE / 'review.json'))
            for file, key in [('source-index.json', 'source_index_sha256'), ('report.json', 'report_sha256'),
                              ('validation-final/validation.json', 'validation_sha256')]:
                assert desc(HERE / file)['sha256'] == review[key]
    else:
        seal(HERE / 'evidence.json', value)
        seal(HERE / 'source-index.json', own())
    assert before == inputs()
    print(json.dumps({'passed': True, 'input_files': len(before), 'reused_instruction_records': value['reused_instruction_records'],
                      'new_decode_bytes': 0, 'game_process_accessed': False, 'native_called': False}))


if __name__ == '__main__':
    main()
