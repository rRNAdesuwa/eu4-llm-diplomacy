"""CREATE_NEW snapshot of the exact stopped v14 log prefix declared by status."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v14_1375 as lab

PID, CREATION = 29492, '01dd56a7d38f2649'
OUT = lab.OUTPUT
SESSION = OUT / f'session-{PID}-{CREATION}'
DEST = OUT / f'preflight-prefix-{PID}'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path, limit=2 * 1024 * 1024):
    return lab.decode_json(lab.read_bounded(path, limit).decode())


def create(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    manifest, manifest_sha = lab.verify_build()
    lab.require(manifest_sha == 'aa09084d3d1d7c9adff164b67356d72e2c511b519e79b382e7bc54a80c96ec75'
                and manifest['dll_sha256'] == 'ABFB2E343F7E7332EFA96C45B1DD2B89C00AC2B4085CBD9FC32E8F90DB299296',
                'Fixed v14 build differs')
    exit_path = OUT / f'process-exit-{PID}.json'
    exit_proof = read_json(exit_path, 4096)
    lab.require(exit_proof['pid'] == PID and exit_proof['creation'] == CREATION
                and type(exit_proof['process_creation_filetime']) is int
                and exit_proof['process_creation_filetime'] == int(CREATION, 16)
                and exit_proof['exit_observed'] is True and exit_proof['exit_code'] == 0
                and exit_proof['process_stop_requested_by_observer'] is False
                and exit_proof['method'] == 'held_handle_wait_and_getprocesstimes', 'Exact normal exit is missing')
    metadata = lab.read_session_metadata(SESSION, PID, CREATION)
    full_evidence = lab.read_evidence(SESSION, metadata)
    lab.require(full_evidence['last_sequence'] == 0 and not full_evidence['requests']
                and all(value is True for value in full_evidence['phases'].values())
                and all(full_evidence[k] is False for k in ('pending', 'lease_pending', 'input_wait_pending')),
                'Stopped native evidence contains a request, unknown input, or incomplete phase')
    native_names = {'session.json', 'install.claim', 'research-1375.jsonl'} | {v[1] for v in lab.PHASES.values()}
    expected_names = native_names | {v[1] + '.host-intent' for v in lab.PHASES.values()}
    names = {p.name for p in SESSION.iterdir()}
    lab.require(names == expected_names, 'Stopped session inventory differs')
    status_path = OUT / f'final-status-{PID}.json'
    capture = read_json(status_path)
    lab.require(capture['exit_code'] == 0 and capture['stderr'] == '' and capture['automatic_retry'] is False,
                'Final status query failed')
    status = capture['report']
    lab.require(status['pid'] == PID and status['creation'] == CREATION
                and status['dll_sha256'] == manifest['dll_sha256'] and status['manifest_sha256'] == manifest_sha,
                'Status identity differs')
    log = SESSION / 'research-1375.jsonl'
    stat_before = log.stat()
    lab.require(stat_before.st_size <= 2 * 1024 * 1024, 'Stopped log exceeds bounded read budget')
    hasher, lines, prefix_bytes, matched = hashlib.sha256(), [], 0, False
    with log.open('rb') as stream:
        while True:
            raw = stream.readline(16385)
            if not raw:
                break
            lab.require(len(raw) <= 16384 and raw.endswith(b'\n'), 'Incomplete or oversized log line')
            lines.append(raw)
            hasher.update(raw)
            prefix_bytes += len(raw)
            if hasher.hexdigest() == status['log_sha256']:
                matched = True
                break
    lab.require(matched and lab.decode_json(lines[-1].decode()) == status['latest_frame'],
                'No exact complete-line prefix matches status hash and latest frame')
    stat_after = log.stat()
    lab.require((stat_before.st_size, stat_before.st_mtime_ns) == (stat_after.st_size, stat_after.st_mtime_ns),
                'Stopped log changed during prefix search')
    DEST.mkdir()
    for name in sorted(native_names):
        raw = b''.join(lines) if name == 'research-1375.jsonl' else lab.read_bounded(SESSION / name, 65536)
        create(DEST / name, raw)
    prefix_metadata = lab.read_session_metadata(DEST, PID, CREATION)
    evidence = lab.read_evidence(DEST, prefix_metadata)
    lab.require(evidence['log_sha256'] == status['log_sha256'] and evidence['log_bytes'] == prefix_bytes
                and evidence['latest_frame'] == status['latest_frame'] and evidence['last_sequence'] == 0
                and all(v is True for v in evidence['phases'].values()), 'Created snapshot differs')
    source_paths = [OUT / 'build.json', exit_path, status_path, *(SESSION / name for name in sorted(names))]
    report = {
        'schema_version': 1, 'purpose': 'v14_exact_status_prefix_snapshot', 'passed': True,
        'pid': PID, 'creation': CREATION, 'manifest_sha256': manifest_sha,
        'source_process_exit_observed': True, 'whole_stopped_log_sha256': full_evidence['log_sha256'],
        'whole_stopped_log_bytes': full_evidence['log_bytes'],
        'prefix_bytes': prefix_bytes, 'prefix_lines': len(lines), 'prefix_sha256': evidence['log_sha256'],
        'prefix_ends_at_status_latest_frame': True, 'source_file_unchanged_during_copy': True,
        'source_session_file_count': len(names), 'native_snapshot_file_count': len(native_names),
        'snapshot_file_sha256': {name: digest(DEST / name) for name in sorted(native_names)},
        'source_input_sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in source_paths},
        'verifier_sha256': digest(Path(__file__)), 'native_requests': 0, 'automatic_retry': False,
        'world_epoch_verified': False, 'production_ready': False,
    }
    output = OUT / f'preflight-prefix-snapshot-{PID}.json'
    create(output, (json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps({'output': str(output), 'sha256': digest(output), 'prefix_bytes': prefix_bytes,
                      'prefix_sha256': evidence['log_sha256'], 'whole_log_bytes': full_evidence['log_bytes'],
                      'whole_log_sha256': full_evidence['log_sha256'], 'native_requests': 0}))


if __name__ == '__main__':
    main()
