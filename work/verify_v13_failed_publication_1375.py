"""Read-only replay of the stopped v13 own-intent recheck failure."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v13_1375 as lab

PID, CREATION = 45844, '01dd56a52618bc90'
OUT = lab.OUTPUT
SESSION = OUT / f'session-{PID}-{CREATION}'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    build, manifest_sha = lab.verify_build()
    lab.require(build['dll_sha256'] == 'B8D42242E5600BB1A18EF3115668B3F21C15913397E8E13CA799929C30F2500F'
                and manifest_sha == '2cac305ddabdae1f1ce3a13cd389cbb9b6b25d6bd7f37e830d8a6ed16ad58389', 'Frozen v13 build differs')
    metadata = lab.read_session_metadata(SESSION, PID, CREATION)
    evidence = lab.read_evidence(SESSION, metadata)
    names = {p.name for p in SESSION.iterdir()}
    lab.require(names == {'session.json', 'install.claim', 'research-1375.jsonl', 'phase-lifecycle.claim.host-intent'}, 'Unexpected later publication/session file')
    lab.require(evidence['last_sequence'] == 0 and not evidence['requests']
                and all(v is False for v in evidence['phases'].values())
                and evidence['phase_attempted'] == {'lifecycle': True, 'owned_peace': False, 'preview': False, 'command': False}
                and all(evidence[k] is False for k in ('pending', 'lease_pending', 'input_wait_pending')), 'A native phase/request or unknown input exists')
    frame = evidence['latest_frame']
    lab.require(frame['world_cookie'] == '0x2460d379030' and frame['raw_date'] == 56456976
                and frame['paused'] is True and frame['session_frozen'] is False
                and frame['mailbox_ready'] is False and frame['thread_changed'] is False
                and frame['world_changed'] is False, 'Final frame differs')
    failure = lab.decode_json(lab.read_bounded(OUT / 'lifecycle-published-45844.json', 65536).decode())
    lab.require(failure['exit_code'] == 2 and failure['stderr'] == 'request_diplomacy_lab_v13: Phase already claimed, intended or started; no retry\n'
                and failure['stdout_raw'] == '' and failure['automatic_retry'] is False, 'Failure capture differs')
    intent = lab.decode_json(lab.read_bounded(SESSION / 'phase-lifecycle.claim.host-intent', 4096).decode())
    wire = lab.phase_wire('lifecycle', metadata)
    lab.require(intent == {'protocol': lab.PROTOCOL, 'purpose': lab.PURPOSE, 'pid': PID, 'creation': CREATION,
                'manifest_sha256': manifest_sha, 'request_sha256': hashlib.sha256(wire).hexdigest(),
                'body_ascii': wire.decode('ascii'), 'automatic_retry': False}, 'Retained host intent differs')
    exit_proof = lab.decode_json(lab.read_bounded(OUT / 'process-exit-45844.json', 4096).decode())
    lab.require(exit_proof['pid'] == PID and exit_proof['creation'] == CREATION
                and exit_proof['process_creation_filetime'] == int(CREATION, 16)
                and exit_proof['exit_observed'] is True and exit_proof['exit_code'] == 0
                and exit_proof['process_exit_filetime'] > int(CREATION, 16)
                and exit_proof['method'] == 'held_handle_wait_and_getprocesstimes', 'Exact process exit differs')
    for event in [lab.decode_json(raw.decode()) for raw in lab.read_bounded(SESSION / 'research-1375.jsonl', 2*1024*1024).splitlines()]:
        lab.require(event['event'] in ('research_hook_installed', 'research_frame'), 'Native operation or phase began')
    before_path, after_path = (OUT / n for n in ('preflight-identity-before-45844.json', 'preflight-identity-after-failed-publication-45844.json'))
    before, after = [lab.decode_json(lab.read_bounded(p, 2*1024*1024).decode()) for p in (before_path, after_path)]
    keys = ('countries', 'pair', 'current_raw_date', 'player', 'database_pointer', 'game_pointer', 'country_array')
    equal = {k: before['state'].get(k) == after['state'].get(k) for k in keys}
    lab.require(all(equal.values()), 'Selected bounded state changed')
    paths = [OUT / 'build.json', OUT / 'lifecycle-published-45844.json', OUT / 'process-exit-45844.json',
             before_path, after_path, *(SESSION / n for n in sorted(names))]
    result = {'schema_version': 1, 'purpose': 'v13_stopped_own_intent_failure_review', 'passed': True,
              'pid': PID, 'creation': CREATION, 'dll_sha256': build['dll_sha256'], 'manifest_sha256': manifest_sha,
              'log_bytes': evidence['log_bytes'], 'log_sha256': evidence['log_sha256'],
              'native_phase_started': False, 'native_requests': 0, 'fixture_invocations': 0,
              'host_intent_retained': True, 'request_file_published': False, 'native_claim_created': False,
              'selected_state_comparison': equal, 'whole_world_unchanged': False,
              'automatic_retry': False, 'world_epoch_verified': False, 'production_ready': False,
              'input_sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}}
    path = OUT / 'failed-publication-summary-45844.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps({'output': str(path), 'sha256': digest(path), 'passed': True, 'native_operations': 0, 'log_bytes': evidence['log_bytes']}))

if __name__ == '__main__':
    main()
