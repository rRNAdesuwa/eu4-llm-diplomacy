"""Root bounded byte/delta review of the sealed v14 capability increment; no game."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import diplomacy_research_capabilities as cap

REVIEW = 'work/candidates/v14-capability-index-review/review.json'
REVIEW_SHA = '7bfa44044676149aaaa3b509ab92ef43bfd0b588cd65a59bc370d6c4446ab772'
OUTPUT = 'work/review-results/v14-capability-root-20261008a.json'


def raw(path):
    p = ROOT / path
    if not p.resolve().is_relative_to(ROOT.resolve()) or p.is_symlink() or p.is_junction():
        raise ValueError('Nonordinary repository file')
    with p.open('rb') as f:
        data = f.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('Bounded review input exceeded')
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    data = raw(REVIEW)
    assert sha(data) == REVIEW_SHA
    review = json.loads(data)
    checked = {}
    for group in ('source_files', 'prior_frozen_inputs_unchanged'):
        for name, descriptor in review[group].items():
            data = raw(name)
            assert len(data) == descriptor['bytes'] and sha(data) == descriptor['sha256'], name
            checked[name] = descriptor
    validation_path = 'work/candidates/v14-capability-index-review/final-validation.json'
    data = raw(validation_path)
    assert sha(data) == review['validation']['sha256'] and len(data) == review['validation']['bytes']
    validation = json.loads(data)
    assert validation['exit_code'] == 0 and validation['sources_before'] == validation['sources_after']
    assert sha(raw('work/candidates/v14-capability-index-review/final-validation-output.txt')) == validation['output_sha256']
    result = cap.capabilities()
    assert result['summary']['actions_with_reviewed_state_effects'] == 28
    assert result['summary']['production_executable_actions'] == 0
    assert len(result['artifacts']) == 876 and all(a['available'] for a in result['artifacts'].values())
    assert sum(a['size_bytes'] for a in result['artifacts'].values()) == 24263680
    effects = result['historical_effect_reviews'][1]
    persistence = result['historical_persistence_reviews'][0]
    assert effects['selected_effect_count'] == 8 and effects['recorded_unknown_selected_effect_count'] == 1
    assert effects['experimental_summary_save_reload_verified'] is False
    assert [persistence[k] for k in ('selected_state_count', 'serialized_and_typed_reload_count', 'typed_reload_only_count')] == [9, 7, 2]
    assert persistence['experimental_summary_save_reload_verified'] is False
    assert persistence['large_saves_rehashed_in_discovery'] is False
    for action in result['actions']:
        assert action['production']['ready'] is False and action['production']['backend_registered'] is False
    assert all(not a['path'].endswith('.eu4') for a in result['artifacts'].values())
    assert cap.MAX_ARTIFACTS == 1024 and cap.MAX_ARTIFACT == 8388608 and cap.MAX_TOTAL == 33554432
    for name, descriptor in checked.items():
        assert sha(raw(name)) == descriptor['sha256'], name
    record = {
        'purpose': 'root_v14_capability_byte_and_delta_review',
        'review_sha256': REVIEW_SHA, 'validation_sha256': review['validation']['sha256'],
        'source_and_frozen_inputs': checked, 'inputs_unchanged': True,
        'summary': result['summary'], 'artifact_count': 876, 'artifact_bytes': 24263680,
        'effect_count': 8, 'unknown_count': 1, 'persistence_counts': [9, 7, 2],
        'experimental_save_reload_preserved_false': True,
        'status': 'root_offline_bytes_and_delta_review_passed',
        'tests_rerun': False, 'game_accessed': False, 'requests_published': False,
        'large_saves_read': False, 'production_ready': False,
    }
    destination = ROOT / OUTPUT
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(record, f, indent=2);f.write('\n')
    print(json.dumps({'output': OUTPUT, 'sha256': sha(raw(OUTPUT)), 'summary': result['summary']}))


if __name__ == '__main__':
    main()
