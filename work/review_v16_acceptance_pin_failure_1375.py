"""Audit one fixed stopped no-native v16 refusal; never access a process."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_api import canonical, decode_json
from work.native import lab_protocol_v16_1375 as lab

OUT = ROOT / 'work/runtime/native1375-v16'
SESSION = OUT / 'session-23700-01dd56bb81f60fc9'
PINS = {
    'session-23700-01dd56bb81f60fc9/research-1375.jsonl':
        'b15cc8d0fafa4054bd91dde44da81744b36ce364cdfc609f76b713d24703457f',
    'exit-observation-23700.json':
        'c9cd8d42cbf19f6c360fe83f6d5aec05dd7385d84cffc87a9eed7388ad6f9c19',
    'build.json': 'e5d2dfce8ceba1555a0d082b1dde90b9986fed9b334af5be5adec7cad2171c52',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(name, inputs):
    path = OUT / name
    require(not path.is_symlink() and not path.is_junction(), 'Linked evidence')
    with path.open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'Read budget')
    sha = hashlib.sha256(raw).hexdigest()
    require(name not in PINS or sha == PINS[name], 'Fixed input changed')
    inputs[name] = {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw), 'sha256': sha}
    return raw


def exact(actual, expected, message):
    require(canonical(actual) == canonical(expected), message)


def main():
    inputs = {}
    raw = read(next(iter(PINS)), inputs)
    require(raw.endswith(b'\n'), 'Partial stopped row')
    rows = [decode_json(line.decode('utf-8')) for line in raw.splitlines()]
    counts = Counter(row['event'] for row in rows)
    require(counts['research_hook_installed'] == 1, 'Install count')
    for event, count in [('pair_lifecycle', 20), ('owned_peace_selftest_complete', 1),
                         ('pair_preview_case', 72), ('pair_command_case', 72)]:
        require(counts[event] == count, 'Preflight count differs')
    claims = [row for row in rows if row['event'] == 'lab_request_claimed']
    exact([row['sequence'] for row in claims], [1, 2, 3, 4], 'Claim chain')
    exact([(row['operation'], row['mode'], row['action']) for row in claims],
          [('fixture', 'submit', 'fixture_on'),
           ('pair', 'legality_only', 'offer_fleet_basing_rights'),
           ('pair', 'legality_only', 'offer_fleet_basing_rights'),
           ('accept', 'submit', 'accept_on')], 'Operation chain')
    exact([claims[-1][key] for key in ('bound_action', 'bound_target', 'bound_submit_sequence')],
          ['offer_fleet_basing_rights', 'POR', 5], 'Bound window')
    records = [row for row in rows if row['event'] == 'lab_native_record']
    terminal = [row['record'] for row in records if row['sequence'] == 4]
    require(len(terminal) == 1, 'Unexpected acceptance record count')
    refusal = terminal[0]
    expected = dict(event='test_acceptance_complete', operation='accept_on', reason=6,
        stage=1, before_date=0, after_date=0, before_raw_flag=None, after_raw_flag=None,
        no_native=True, native_invoked=False, callback_returned=False, callback_success=False,
        callback_result_identity=False, zero_arguments_confirmed=False, arguments_unchanged=False,
        result_destroyed=False, world_identity_unchanged=False, readback_observed=False,
        readback_matches=False, exception_code=0, freeze_session=True, audit_complete=True,
        diplomacy_submitted=False, diplomacy_effect_verified=False, retry_allowed=False)
    for key, value in expected.items():
        exact(refusal[key], value, 'Refusal field differs: ' + key)
    require(not any(row['record'].get('submit_entered') is True for row in records),
            'Diplomatic submission occurred')
    require(not any(row['event'] == 'test_acceptance_begin' for row in terminal), 'Unexpected begin')
    completions = [row for row in rows if row['event'] == 'lab_request_complete']
    exact([row['sequence'] for row in completions], [1, 2, 3, 4], 'Completion chain')
    require(completions[-1]['session_frozen'] is True and completions[-1]['native_invoked'] is False,
            'No-native terminal missing')
    frames = [row for row in rows if row['event'] == 'research_frame']
    fixed = dict(pid=23700, process_creation_filetime='01dd56bb81f60fc9', thread=56000,
        world_cookie='0x245c0c6b010', player_handle='0x0100007a00415246', raw_date=56456976,
        paused=True, native_speed_index=0, acceptance_flag=0, lease_active=False,
        world_changed=False, thread_changed=False)
    for frame in frames:
        for key, value in fixed.items():
            exact(frame[key], value, 'Selected frame differs: ' + key)
    require(frames[0]['acceptance_action'] == 'none' and frames[0]['acceptance_target'] == 'none',
            'Initial canonical binding missing')
    require(frames[-1]['acceptance_state'] == 'unknown' and frames[-1]['session_frozen'] is True
            and frames[-1]['last_sequence'] == 4 and frames[-1]['mailbox_ready'] is False,
            'Terminal frozen frame missing')
    for name in ('status-initial-23700.json', 'stage-lifecycle-status-23700.json',
                 'stage-owned-peace-status-23700.json', 'stage-preview-status-23700.json',
                 'stage-command-status-23700.json', 'seq01-fixture-on-status-23700.json',
                 'seq02-offer-fleet-legality-status-23700.json',
                 'seq03-offer-fleet-legality-status-23700.json', 'loader-plan-23700.json',
                 'loader-plan-r2-23700.json', 'loader-actual-23700.json',
                 'seq03-accept-on-publish-23700.json', 'seq03-accept-on-status-23700.json',
                 'seq04-accept-on-status-23700.json', 'seq04-accept-on-status-r2-23700.json',
                 'baseline-before-injection-23700.json', 'after-accept-reader-failure-23700.json',
                 'offer-fleet-before-23700.json', 'build.json'):
        read(name, inputs)
    for name in ('seq04-accept-on-status-23700.json', 'seq04-accept-on-status-r2-23700.json'):
        failed = decode_json((OUT / name).read_text())
        require(failed['exit_code'] == 2 and 'Acceptance core requires exactly one begin and one complete'
                in failed['stderr'], 'Strict reader actual failure differs')
    metadata = lab.read_session_metadata(SESSION, 23700, '01dd56bb81f60fc9')
    try:
        lab.read_evidence(SESSION, metadata)
    except ValueError as error:
        require(str(error) == 'Acceptance core requires exactly one begin and one complete',
                'Stopped strict-reader rejection differs')
        rejection = str(error)
    else:
        raise ValueError('Stopped no-native failure passed success reader')
    exited = decode_json(read('exit-observation-23700.json', inputs).decode())
    require(exited['pid'] == 23700 and exited['creation'] == '01dd56bb81f60fc9'
            and exited['exit_observed'] is True and type(exited['exit_code']) is int
            and exited['exit_code'] == 0 and exited['process_exit_filetime'] == 134358932928897989,
            'Held normal exit differs')
    summary = dict(schema_version=1, purpose='root_v16_stopped_acceptance_no_native_refusal_audit',
        reviewed_at_utc=datetime.now(timezone.utc).isoformat(), input_artifacts=inputs,
        status='stopped_terminal_no_native_image_pin_refusal', pid=23700,
        creation='01dd56bb81f60fc9', event_counts=dict(counts), frame_count=len(frames),
        preflight_counts=[20, 1, 72, 72], native_request_count=4, diplomatic_submit_count=0,
        acceptance_handler_invocation_count=0, refusal=refusal, selected_frame_fields=fixed,
        strict_success_reader_rejection=rejection, held_normal_exit_verified=True,
        initial_canonical_binding_verified=True, runtime_effect_verified=False,
        save_reload_verified=False, natural_ai_acceptance_verified=False,
        whole_world_unchanged_verified=False, strict_single_player_verified=False,
        world_epoch_verified=False, production_ready=False, process_accessed_by_auditor=False,
        limitations=['Complete stopped selected telemetry does not authenticate all world state.',
            'Reason/stage interpretation and exact byte mismatch require the separate static dossier.',
            'Strict success reader remained unchanged and rejected this complete-only refusal.'])
    target = OUT / 'acceptance-pin-failure-summary-23700.json'
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(summary, stream, indent=2); stream.write('\n')
    print(json.dumps({'output': str(target), 'frame_count': len(frames),
        'native_requests': 4, 'diplomatic_submits': 0, 'handler_invocations': 0, 'exit': 0}))


if __name__ == '__main__':
    main()
