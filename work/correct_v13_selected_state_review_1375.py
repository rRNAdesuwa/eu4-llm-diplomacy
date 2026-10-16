"""Offline correction of the absent-key comparison in the stopped v13 review.

This supplements the immutable first summary. It does not assert that the
current shared support still matches the historical build manifest.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/runtime/native1375-v13'
PINS = {
    'failed-publication-summary-45844.json': '6878be5b0b355a2773786cdc608a22cbaff312331b07b0744cf2bdfa4368ed4a',
    'preflight-identity-before-45844.json': '289c62839b192653fac0be0644c60bdbfd881333d02826a80e17925b482973f1',
    'preflight-identity-after-failed-publication-45844.json': '545231a9468dc886a998d3497db0e3b7d296756a9bf1fac364ace901494062d4',
    'build.json': '2cac305ddabdae1f1ce3a13cd389cbb9b6b25d6bd7f37e830d8a6ed16ad58389',
}
KEYS = ('countries', 'actor', 'target', 'actor_diplomats', 'relation_cooldown',
        'current_raw_date', 'player', 'database_pointer', 'game_pointer', 'country_array')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def compare_selected(before, after):
    require(type(before) is dict and type(after) is dict, 'State must be an object')
    require(all(key in before and key in after for key in KEYS), 'Required selected field is missing')
    result = {key: before[key] == after[key] and type(before[key]) is type(after[key]) for key in KEYS}
    require(all(result.values()), 'Selected bounded fields changed')
    return result


def main():
    documents = {}
    for name, expected in PINS.items():
        path = OUT / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2 * 1024 * 1024,
                'Input must be a bounded regular file: ' + name)
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'Fixed input changed: ' + name)
        documents[name] = json.loads(raw)
    old = documents['failed-publication-summary-45844.json']
    before, after = (documents[name] for name in (
        'preflight-identity-before-45844.json', 'preflight-identity-after-failed-publication-45844.json'))
    for capture in (before, after):
        require(capture['read_only'] is True, 'Capture was not read-only')
        source = capture['source']
        require(source['pid'] == 45844 and type(source['process_creation_filetime']) is int
                and source['process_creation_filetime'] == int('01dd56a52618bc90', 16)
                and source['process_exit_filetime'] == 0
                and source['held_identity_verified_before_and_after'] is True
                and source['atomic_snapshot'] is False, 'Held process identity differs')
        state = capture['state']
        require(state['game_pointer'] == '0x2460d379030' and state['current_raw_date'] == 56456976
                and state['actor'] == 'FRA' and state['target'] == 'ENG'
                and state['country_identities_verified'] is True, 'Selected scope differs')
        require(state['snapshot_consistency'] == {
            'globals_unchanged': True, 'player_unchanged': True,
            'date_unchanged': True, 'atomic': False}, 'Bounded snapshot consistency differs')
    require('pair' not in before['state'] and 'pair' not in after['state']
            and old['selected_state_comparison']['pair'] is True, 'Historical defect premise differs')
    compared = compare_selected(before['state'], after['state'])
    # Meaningful negative checks: absence and a changed value must both reject.
    for field in KEYS:
        missing = dict(after['state'])
        del missing[field]
        try:
            compare_selected(before['state'], missing)
        except ValueError:
            pass
        else:
            raise ValueError('Missing-field counterexample accepted: ' + field)
    changed = dict(after['state'])
    changed['current_raw_date'] += 24
    try:
        compare_selected(before['state'], changed)
    except ValueError:
        pass
    else:
        raise ValueError('Changed-date counterexample accepted')
    manifest = documents['build.json']
    support = ROOT / 'bridge/diplomacy_lab_http.py'
    current_support_sha = digest(support)
    historical_support_sha = manifest['support_source_sha256']['bridge/diplomacy_lab_http.py'].lower()
    result = {
        'schema_version': 1,
        'purpose': 'v13_stopped_selected_state_review_correction',
        'passed': True, 'pid': 45844, 'creation': '01dd56a52618bc90',
        'supersedes_only': 'selected_state_comparison in failed-publication-summary-45844.json',
        'historical_missing_pair_comparison_valid': False,
        'correction': 'Require each field in both captures; compare indexed values and their exact types.',
        'selected_state_comparison': compared, 'required_field_counterexamples_rejected': len(KEYS),
        'changed_date_counterexample_rejected': True,
        'whole_world_unchanged': False, 'atomic_snapshot': False,
        'world_epoch_verified': False, 'production_ready': False,
        'current_build_reverified': False,
        'historical_support_sha256': historical_support_sha,
        'current_support_sha256': current_support_sha,
        'current_support_matches_historical': current_support_sha == historical_support_sha,
        'input_sha256': {'work/runtime/native1375-v13/' + name: sha for name, sha in PINS.items()},
        'verifier_sha256': digest(Path(__file__)),
    }
    output = OUT / 'failed-publication-selected-state-correction-45844.json'
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(output), 'sha256': digest(output), 'passed': True,
                      'selected_fields': len(KEYS), 'current_build_reverified': False}))


if __name__ == '__main__':
    main()
