"""Review the fixed stopped v15 initial-status failure; never open a game process."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import decode_json

OUT = ROOT / 'work/runtime/native1375-v15'
SESSION = OUT / 'session-65368-01dd56b7172a900b'
LOG_SHA = 'c069c984d9160bb8dd7a3ed2f856fb195838cd39784fd8a0c323c7a10b246b4e'
EXIT_SHA = 'faea4292605a7a64baf2960dbcb20bba1047e7c143693a9306c41deb60c8cd5a'


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path, expected=None):
    raw = path.read_bytes()
    require(len(raw) <= 2 * 1024 * 1024, 'Evidence read budget exceeded')
    digest = hashlib.sha256(raw).hexdigest()
    require(expected is None or digest == expected, 'Fixed input changed')
    return raw, {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest, 'bytes': len(raw)}


def main():
    raw, log_pin = read(SESSION / 'research-1375.jsonl', LOG_SHA)
    exit_raw, exit_pin = read(OUT / 'process-exit-65368.json', EXIT_SHA)
    exited = decode_json(exit_raw.decode())
    require(exited['exit_observed'] is True and type(exited['exit_code']) is int and exited['exit_code'] == 0
            and exited['pid'] == 65368 and exited['creation'] == '01dd56b7172a900b', 'Held normal exit differs')
    require(raw.endswith(b'\n'), 'Stopped log has a partial row')
    events = [decode_json(line.decode()) for line in raw.splitlines()]
    require(events[0]['event'] == 'research_hook_installed', 'Installation row missing')
    frames = events[1:]
    require(frames and all(e['event'] == 'research_frame' for e in frames), 'Unexpected operation/event')
    fixed = {'pid': 65368, 'process_creation_filetime': '01dd56b7172a900b', 'thread': 30792,
        'world_cookie': '0x201bf780010', 'player_handle': '0x0100007a00415246', 'raw_date': 56456976,
        'world_ready': True, 'paused': True, 'world_changed': False, 'thread_changed': False,
        'session_frozen': False, 'last_sequence': 0, 'native_speed_index': 0,
        'lifecycle_passed': False, 'owned_peace_tested': False, 'owned_peace_passed': False,
        'preview_passed': False, 'command_passed': False, 'mailbox_ready': False,
        'lease_active': False, 'lease_deadline_uptime_ms': 0, 'send_enabled': False,
        'acceptance_flag': 0, 'acceptance_state': 'closed', 'acceptance_origin_sequence': 0,
        'acceptance_submit_sequence': 0, 'acceptance_off_sequence': 0,
        'acceptance_action': '', 'acceptance_target': ''}
    for frame in frames:
        require(all(k in frame and type(frame[k]) is type(v) and frame[k] == v for k, v in fixed.items()),
                'Selected initial health field differs')
    names = {p.name for p in SESSION.iterdir()}
    require(names == {'session.json', 'research-1375.jsonl', 'install.claim'}, 'Session contains a request or unexpected file')
    inputs = {'log': log_pin, 'exit': exit_pin}
    for label, path in (('metadata', SESSION / 'session.json'), ('install_claim', SESSION / 'install.claim'),
                        ('loader', OUT / 'loader-installed-65368.json'), ('failed_status', OUT / 'health-after-install-65368.json'),
                        ('build', OUT / 'build.json')):
        _, inputs[label] = read(path)
    status = decode_json((OUT / 'health-after-install-65368.json').read_text())
    require(status['exit_code'] == 2 and 'acceptance: frame action binding differs' in status['stderr'], 'Actual failure differs')
    result = {'schema_version': 1, 'purpose': 'root_v15_initial_closed_status_failure_review',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'stopped_initial_protocol_mismatch',
        'pid': 65368, 'creation': '01dd56b7172a900b', 'input_artifacts': inputs,
        'frame_count': len(frames), 'selected_fields_consistent': True, 'selected_field_values': fixed,
        'phase_count': 0, 'native_request_count': 0, 'diplomatic_submit_count': 0,
        'initial_native_binding': {'action': '', 'target': ''},
        'python_expected_initial_binding': {'action': 'none', 'target': 'none'},
        'held_normal_exit_verified': True, 'runtime_success_verified': False,
        'production_ready': False, 'game_accessed_by_reviewer': False,
        'whole_world_unchanged_verified': False, 'world_epoch_verified': False,
        'limitations': ['Selected logged fields and complete artifact inventory do not authenticate engine telemetry or all world state.',
            'Zero requests follow from the complete stopped log and exact session inventory, not a successful old read_evidence call.']}
    target = OUT / 'initial-closed-failure-summary-65368.json'
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(target), 'frames': len(frames), 'native_requests': 0, 'normal_exit': True}))


if __name__ == '__main__':
    main()
