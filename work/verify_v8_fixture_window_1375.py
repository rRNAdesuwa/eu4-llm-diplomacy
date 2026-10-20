"""Offline review of selected state around the root-observed v8 event OK click.

UI closure is an explicit human-agent observation, not inferred from these reads.
No game, process, event, injection, or UI calls are made by this reviewer.
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

runtime = ROOT / 'work/runtime'
reports, hashes = {}, {}
for name in ('current-v8-pending-ui-39216.json', 'current-v8-after-ui-39216.json',
             'relations-v8-before-ui-marriage-NAV-39216.json',
             'relations-v8-after-ui-marriage-NAV-39216.json',
             'relations-v8-before-ui-vassal-NAV-39216.json',
             'relations-v8-after-ui-vassal-NAV-39216.json'):
    raw = lab.read_bounded(runtime / name, 1024 * 1024)
    reports[name] = json.loads(raw.decode('utf-8-sig'))
    hashes[name] = hashlib.sha256(raw).hexdigest().upper()

before = reports['current-v8-pending-ui-39216.json']
after = reports['current-v8-after-ui-39216.json']
lab.require(before['read_only'] is after['read_only'] is True, 'Not read-only')
lab.require(before['source'] == after['source'] and after['source']['pid'] == 39216,
            'Process identity changed')
lab.require(before['build'] == after['build'] and after['build']['sha256'] == lab.LOCAL_SHA256,
            'Game build changed')
old, new = before['state'], after['state']
for key in ('game_pointer', 'database_pointer', 'country_array', 'current_raw_date',
            'player', 'actor_diplomats'):
    lab.require(old[key] == new[key], f'Selected state changed: {key}')
lab.require(new['current_raw_date'] == 56457024 and new['actor_diplomats']['entry_count'] == 103,
            'Unexpected date/diplomat count')
relations = {}
for action in ('marriage', 'vassal'):
    prior, prior_state, prior_times = observer.validated_report(
        reports[f'relations-v8-before-ui-{action}-NAV-39216.json'])
    current, current_state, current_times = observer.validated_report(
        reports[f'relations-v8-after-ui-{action}-NAV-39216.json'])
    lab.require(prior_times[1] <= current_times[0], 'Capture order changed')
    lab.require(prior == current and prior_state == current_state
                and current_state['state'] == 'active', f'{action} state changed')
    lab.require(int(reports[f'relations-v8-after-ui-{action}-NAV-39216.json']['source']
                    ['process_creation_filetime']) == int('01dd5681d5d0e053', 16),
                'Wrong process creation')
    relations[action] = current_state

result = {
    'kind': 'v8_fixture_window_selected_state_review', 'schema_version': 1,
    'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
    'pid': 39216, 'creation': '01dd5681d5d0e053',
    'profile_id': lab.FIXTURE_PROFILE_ID, 'profile_sha256': lab.FIXTURE_PROFILE_SHA256,
    'ui_observation': {
        'method': 'root agent observed Computer Use screenshots and clicked once',
        'achievement_warning_ok_clicked': True,
        'pending_llmt_1_ok_button_visible': True,
        'event_closed_after_ok_click': True,
        'paused_map_observed_after_click': True,
        'automated_pixel_verification': False,
    },
    'selected_state_unchanged': True, 'current_raw_date': new['current_raw_date'],
    'actor_diplomat_count': 103, 'relations': relations,
    'input_sha256': hashes,
    'native_pair_submit_in_this_process': False,
    'whole_world_unchanged_verified': False, 'request_id_causality_verified': False,
    'exact_loaded_file_path_verified': False, 'production_execution_verified': False,
}
path = runtime / 'native1375-v8/fixture-window-review-39216.json'
with path.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'output': str(path), 'selected_state_unchanged': True,
                  'diplomats': 103, 'ui_closure_observed': True}))
