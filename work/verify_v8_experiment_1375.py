"""Offline review of v8 fixture windows and the bounded break-marriage test.

No game/process/UI calls. A selected state transition and serialized result are
not exact request-ID attribution, whole-world invariance, or production readiness.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_relations_v7_1375 as observer
from work.native import lab_protocol_v8_1375 as lab

RUNTIME = ROOT / 'work/runtime'
FILES = {
    'window': 'native1375-v8/fixture-window-review-39216.json',
    'phases': 'native1375-v8/phases-ready-39216.json',
    'off': 'native1375-v8/fixture-off-status-1-39216.json',
    'on': 'native1375-v8/fixture-on-status-3-39216.json',
    'legality': 'native1375-v8/break-marriage-legality-status-4-39216.json',
    'submit': 'native1375-v8/break-marriage-status-5-39216.json',
    'final': 'native1375-v8/final-status-39216.json',
    'before': 'relations-v8-before-break-marriage-NAV-39216.json',
    'after': 'relations-v8-after-break-marriage-NAV-39216.json',
    'comparison': 'relations-v8-break-marriage-NAV-result-39216.json',
    'old_save': 'save-v7-marriage-vassal-20261008a.json',
    'off_save': 'save-v8-fixture-off-39216.json',
    'saved': 'save-v8-break-marriage-39216.json',
    'copy': 'native1375-v8/break-marriage-save-copy-39216.json',
}


def review():
    reports, hashes = {}, {}
    for key, name in FILES.items():
        raw = lab.read_bounded(RUNTIME / name, 1024 * 1024)
        reports[key] = json.loads(raw.decode('utf-8-sig'))
        hashes[name] = hashlib.sha256(raw).hexdigest().upper()
    build, manifest_sha = lab.verify_build()
    for key in ('phases', 'off', 'on', 'legality', 'submit', 'final'):
        result = reports[key]
        lab.require(result['pid'] == 39216 and result['creation'] == '01dd5681d5d0e053'
                    and result['purpose'] == lab.PURPOSE and result['protocol'] == lab.PROTOCOL
                    and result['dll_sha256'] == build['dll_sha256']
                    and result['manifest_sha256'] == manifest_sha,
                    f'Wrong lab identity: {key}')
        lab.require(result['phases'] == {'lifecycle': True, 'preview': True, 'command': True},
                    f'Missing phases: {key}')
    for key, seq, action in (('off', 1, 'fixture_off'), ('on', 3, 'fixture_on')):
        request = reports[key]['request']
        result = request['complete']
        lab.require(request['request']['sequence'] == seq and result['sequence'] == seq
                    and result['action'] == action and result['reason'] == 0,
                    'Wrong fixture result')
        lab.require(all(result[field] is True for field in ('native_invoked', 'callback_returned',
                    'callback_success', 'result_destroyed', 'arguments_unchanged',
                    'callback_flag_restored', 'world_identity_unchanged'))
                    and result['session_frozen'] is False, 'Uncertain fixture callback')
    old, old_state, old_times = observer.validated_report(reports['before'])
    new, new_state, new_times = observer.validated_report(reports['after'])
    lab.require(reports['before']['source'] == reports['after']['source']
                and reports['after']['source']['pid'] == 39216
                and old_times[1] <= new_times[0], 'Wrong observation source/order')
    comparison = observer.compare_reports(reports['before'], reports['after'], 'cancel')
    lab.require(all(reports['comparison'].get(key) == value for key, value in comparison.items())
                and comparison['observed_effect'] is True
                and old_state['state'] == 'active' and new_state['state'] == 'absent',
                'No independently verified marriage removal')
    for key, seq, status in (('legality', 4, 1), ('submit', 5, 2)):
        request = reports[key]['request']
        complete = request['complete']
        core = [row for row in request['records'] if row['event'] == 'pair_engine_complete']
        lab.require(len(core) == 1 and complete['sequence'] == seq
                    and complete['status'] == status and complete['reason'] == 0,
                    'Wrong pair completion')
        core = core[0]
        lab.require(core['action_id'] == 'break_marriage' and core['actor'] == 'FRA'
                    and core['target'] == 'NAV' and core['pid'] == 39216
                    and core['thread_id'] == 34592 and core['exception'] == 0
                    and core['world'] == old['game']
                    and core['raw_date'] == old['current_raw_date'] == 56457072
                    and core['preview_allowed'] is True and core['gate_allowed'] is True
                    and core['ownership_uncertain'] is False and core['freeze_session'] is False,
                    'Wrong core binding or uncertain call')
        if key == 'submit':
            lab.require(all(core[field] is True for field in ('submit_entered', 'submit_returned',
                        'context_submit_return', 'caller_container_consumed')),
                        'Native submit or ownership transfer unproved')
        else:
            lab.require(core['submit_entered'] is False and core['original_destroyed'] is True
                        and core['command_destroyed_before_dispatch'] is True,
                        'Legality query sent or cleanup missing')
    for key in ('old_save', 'off_save', 'saved'):
        saved = reports[key]
        lab.require(saved['parsed_complete'] is True and saved['read_only'] is True
                    and saved['evidence_scope'] == 'serialized_state_only'
                    and lab.file_hash(Path(saved['source']['path'])) == saved['source']['sha256'],
                    'Incomplete or changed save')
    lab.require('modifier' in reports['old_save']['countries']['FRA']['field_inventory']
                and 'modifier' not in reports['off_save']['countries']['FRA']['field_inventory'],
                'Fixture modifier removal not serialized')
    saved = reports['saved']
    selected = []
    for record in saved['global_diplomacy']['records']:
        values = {item['key']: item.get('value') for item in record.get('entries', []) if item.get('key')}
        if {values.get('first'), values.get('second')} == {'FRA', 'NAV'}:
            selected.append({'kind': record['key'], 'fields': values})
    lab.require(not any(row['kind'] == 'royal_marriage' for row in selected), 'Marriage still serialized')
    lab.require(any(row['kind'] == 'dependency' and row['fields'].get('first') == 'FRA'
                and row['fields'].get('subject_type') == 'vassal' for row in selected),
                'Vassal state no longer serialized')
    copy = reports['copy']
    lab.require(copy['byte_identical'] is True and copy['overwrite'] is False
                and copy['sha256'] == saved['source']['sha256']
                and lab.file_hash(Path(copy['source'])) == copy['sha256']
                and lab.file_hash(Path(copy['preserved'])) == copy['sha256'], 'Save copies changed')
    final = reports['final']['latest_frame']
    lab.require(final['paused'] is True and final['last_sequence'] == 6
                and final['raw_date'] == 56457120 and final['world_cookie'] == old['game']
                and final['session_frozen'] is False, 'Wrong final frame')
    return {'schema_version': 1, 'purpose': 'v8_experiment_evidence_review',
            'reviewed_at_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
            'pid': 39216, 'creation': '01dd5681d5d0e053', 'last_sequence': 6,
            'game_sha256': lab.LOCAL_SHA256, 'dll_sha256': build['dll_sha256'],
            'manifest_sha256': manifest_sha, 'fixture_profile_sha256': lab.FIXTURE_PROFILE_SHA256,
            'phase_checks_passed': True, 'fixture_callbacks_completed': ['fixture_off', 'fixture_on'],
            'fixture_off_modifiers_absent_in_save': True,
            'fixture_off_diplomat_pool_shrink_verified': False,
            'pair_submits': 1, 'actions': {'break_marriage': {
                'native_dispatch_completed': True, 'observed_relation_removed': True,
                'saved_result_consistent': True, 'saved_reload_state_consistent': False}},
            'saved_selected_relations': selected, 'save_sha256': copy['sha256'],
            'input_sha256': hashes, 'final_paused': True,
            'request_id_causality_verified': False, 'whole_world_unchanged_verified': False,
            'exact_loaded_file_path_verified': False, 'production_backend_registered': False}


if __name__ == '__main__':
    result = review()
    path = RUNTIME / 'native1375-v8/experiment-summary-39216.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(path), 'pair_submits': result['pair_submits'],
                      'actions': result['actions'], 'final_paused': True}))
