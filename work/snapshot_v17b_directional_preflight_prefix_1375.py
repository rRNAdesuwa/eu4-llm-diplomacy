"""Preserve one explicitly declared pre-operation prefix of an active v17 log.

Reads files only. Does not require or claim the growing complete log is stopped.
Later requests are excluded by exact SHA/complete-line boundary, never silently
selected as a latest prefix. All outputs are CreateNew.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v17_1375 as lab

PID, CREATION, WORLD = 63500, '01dd56c21f9b7c9d', '0x23fc93a11e0'
OUT = lab.OUTPUT
SESSION = OUT / f'session-{PID}-{CREATION}'
DEST = OUT / f'directional-preflight-prefix-{PID}'
STATUS = OUT / f'stage-command-status-{PID}.json'
MAX_LOG = 2 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def create(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def exact_prefix(path, digest):
    hasher, chunks, total = hashlib.sha256(), [], 0
    with path.open('rb') as stream:
        while total < MAX_LOG:
            raw = stream.readline(16385)
            if not raw:
                break
            total += len(raw)
            lab.require(total <= MAX_LOG and len(raw) <= 16384 and raw.endswith(b'\n'),
                        'Invalid or over-budget complete-line prefix')
            chunks.append(raw)
            hasher.update(raw)
            if hasher.hexdigest() == digest:
                return b''.join(chunks), len(chunks), lab.decode_json(raw.decode())
    raise RuntimeError('No exact declared prefix within bounded read')


def main():
    manifest, manifest_sha = lab.verify_build()
    lab.require(manifest_sha == 'b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d'
                and manifest['dll_sha256'] == 'D8B962B19D489FD366F346416BB72A8958F3DC53B504A29EC835D3B99CAFA1EE',
                'Fixed frozen v17 build changed')
    lab._no_links(SESSION)
    lab._no_links(DEST)
    lab.require(not DEST.exists(), 'Snapshot destination already exists')
    status_raw = lab.read_bounded(STATUS, 65536)
    capture = lab.decode_json(status_raw.decode())
    lab.require(capture['exit_code'] == 0 and capture['stderr'] == ''
                and capture['automatic_retry'] is False, 'Status query failed')
    status = capture['report']
    lab.require(status['pid'] == PID and status['creation'] == CREATION
                and status['read_only'] is True and status['last_sequence'] == 0
                and all(v is True for v in status['phases'].values())
                and status['pending'] is False and status['lease_pending'] is False
                and status['manifest_sha256'] == manifest_sha
                and status['dll_sha256'] == manifest['dll_sha256'], 'Status binding differs')
    frame = status['latest_frame']
    lab.require(frame['world_cookie'] == WORLD and type(frame['raw_date']) is int
                and frame['raw_date'] == 56456976 and frame['paused'] is True
                and frame['session_frozen'] is False and frame['mailbox_ready'] is True,
                'Declared pre-operation frame differs')
    log = SESSION / 'research-1375.jsonl'
    prefix, lines, last = exact_prefix(log, status['log_sha256'])
    lab.require(json.dumps(last, sort_keys=True, allow_nan=False)
                == json.dumps(frame, sort_keys=True, allow_nan=False), 'Exact latest frame differs')
    names = {'session.json', 'install.claim', *(v[1] for v in lab.PHASES.values())}
    source_raw = {name: lab.read_bounded(SESSION / name, 65536) for name in names}
    # Check the exact prefix again while the active log may append later frames.
    prefix_again, _, _ = exact_prefix(log, status['log_sha256'])
    lab.require(prefix_again == prefix and lab.read_bounded(STATUS, 65536) == status_raw
                and all(lab.read_bounded(SESSION / name, 65536) == raw
                        for name, raw in source_raw.items()), 'Selected source bytes changed')
    DEST.mkdir()
    for name, raw in sorted(source_raw.items()):
        create(DEST / name, raw)
    create(DEST / 'research-1375.jsonl', prefix)
    metadata = lab.read_session_metadata(DEST, PID, CREATION)
    evidence = lab.read_evidence(DEST, metadata)
    lab.require(evidence['log_sha256'] == status['log_sha256'] and evidence['log_bytes'] == len(prefix)
                and evidence['last_sequence'] == 0 and not evidence['requests']
                and all(v is True for v in evidence['phases'].values())
                and json.dumps(evidence['latest_frame'], sort_keys=True, allow_nan=False)
                == json.dumps(frame, sort_keys=True, allow_nan=False), 'Snapshot readback differs')
    _, final_manifest_sha = lab.verify_build()
    lab.require(final_manifest_sha == manifest_sha, 'Build changed during snapshot')
    report = {'schema_version': 1, 'purpose': 'active_session_exact_declared_preoperation_prefix',
              'pid': PID, 'creation': CREATION, 'world_cookie': WORLD, 'passed': True,
              'source_process_exit_observed': False, 'whole_active_log_unchanged_verified': False,
              'selected_prefix_bytes_rechecked': True, 'prefix_sha256': sha(prefix),
              'prefix_bytes': len(prefix), 'prefix_lines': lines, 'native_requests_in_prefix': 0,
              'manifest_sha256': manifest_sha, 'status_sha256': sha(status_raw),
              'snapshot_file_sha256': {name: sha(raw) for name, raw in
                                      {**source_raw, 'research-1375.jsonl': prefix}.items()},
              'snapshot_helper_sha256': sha(Path(__file__).read_bytes()),
              'native_execution_verified': False, 'world_epoch_verified': False, 'production_ready': False}
    output = OUT / f'directional-preflight-prefix-snapshot-{PID}.json'
    create(output, (json.dumps(report, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'output': str(output), 'sha256': sha(output.read_bytes()),
                      'prefix_sha256': sha(prefix), 'prefix_bytes': len(prefix), 'native_requests': 0}))


if __name__ == '__main__':
    main()
