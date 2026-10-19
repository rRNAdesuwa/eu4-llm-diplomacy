"""One passive, source-bound receipt read; no process/native/publication access.

Uses the reviewed launcher's captured source graph, then the real provenance
reader. Completion does not require a still-fresh live publication boundary.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import types

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / 'work/candidates/v19-spy-real-client-r2-1375/launcher.py'
LAUNCHER_SHA = 'a7944c63e044e195a242b417afbea27c001ef2cae1f9d1a721bf3b83352845fe'
BUILD = ROOT / 'work/candidates/v19-spy-bootstrap-lab-1375/build-attempt2'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--creation', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--complete', action='store_true')
    args = parser.parse_args()
    with LAUNCHER.open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != LAUNCHER_SHA:
        raise ValueError('Reviewed trusted launcher differs')
    module = types.ModuleType('_root_verified_v19_launcher')
    module.__file__ = str(LAUNCHER)
    exec(compile(raw, str(LAUNCHER), 'exec'), module.__dict__)
    graph = module.verified_graph()
    provenance = graph.local('provenance.py')
    loader = BUILD / f'loader-{args.pid}-{args.creation}.json'
    with loader.open('rb') as stream:
        raw_loader = stream.read(32769)
    if len(raw_loader) > 32768:
        raise ValueError('Loader record budget')
    identity = json.loads(raw_loader)['identity']
    if identity['pid'] != args.pid or identity['creation'] != args.creation:
        raise ValueError('Explicit process identity differs')
    result = provenance.inspect(BUILD, identity, args.complete)
    record = dict(kind='passive_source_bound_receipt', complete_requested=args.complete,
                  launcher_sha256=LAUNCHER_SHA, game_accessed=False,
                  request_written=False, native_called=False, receipt=result)
    encoded = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode('ascii')
    if len(encoded) > 65536:
        raise ValueError('Receipt output budget')
    with args.output.open('xb') as stream:
        if stream.write(encoded) != len(encoded):
            raise ValueError('Short receipt write')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(dict(output=str(args.output), sha256=hashlib.sha256(encoded).hexdigest(),
                         session=identity['session'], **{key: result.get(key) for key in
                         ('status', 'next_sequence', 'claimed_sequence', 'preflight_ready',
                          'authenticated_stages', 'completed_items', 'controller_frames',
                          'last_owner_uptime_ms', 'retry_allowed')}), sort_keys=True))

if __name__ == '__main__':
    main()
