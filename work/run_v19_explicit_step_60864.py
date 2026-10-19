"""Root operator: one exact reviewed load or fixed stage, never a retry loop."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'work/candidates/v19-spy-bootstrap-lab-1375/build-attempt2'
BOOT = BUILD.parent
CLIENT = ROOT / 'work/candidates/v19-spy-real-client-r2-1375'
PID = 60864
CREATION = '01dd5714af7e8580'
PINS = {
    'work/candidates/v19-spy-bootstrap-lab-1375/review.json': 'bd371a8158064fe38abbf48ea37aa2119e9089e5d98f05aba7c91ca952601884',
    'work/review-results/v19-spy-bootstrap-external-20261008a/review.json': '30d872d4c82a3897e1f5d13bba8a44bcf48368b518254aa18fd86c3001896753',
    'work/candidates/v19-spy-real-client-r2-1375/review.json': '808b490acb3845beefcf8aeb9eb7306bdc028887f9c284136749f2dcac74ed1f',
    'work/review-results/v19-real-client-r2-native-inventory-20261008a/review.json': 'ea4f0ccd9197c968b28d29f5aeedf0eafa711c13a5b120e35cdf6d676025ec2f',
    'work/candidates/v19-spy-real-client-r2-1375/launcher.py': 'a7944c63e044e195a242b417afbea27c001ef2cae1f9d1a721bf3b83352845fe',
}

def bounded(path, limit=131072):
    path = Path(path)
    for node in (path, *path.parents):
        if node.exists() and (node.is_symlink() or getattr(node.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Linked/reparse operator input')
    if path.stat().st_nlink != 1:
        raise ValueError('Hardlinked operator input')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Operator input budget')
    return raw

def write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')
    with path.open('xb') as stream:
        if stream.write(raw) != len(raw):
            raise ValueError('Short operator record write')
        stream.flush()
        os.fsync(stream.fileno())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', choices=('load', 'lifecycle', 'family_preview', 'owned_command', 'send_batch'), required=True)
    args = parser.parse_args()
    for name, sha in PINS.items():
        raw = bounded(ROOT / name)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('Reviewed operator source differs: ' + name)
    review = json.loads(bounded(ROOT / 'work/review-results/v19-real-client-r2-native-inventory-20261008a/review.json'))
    if review['outcome'] != 'approved_for_reviewed_file_and_fake_scope' or review['findings'] or not review['sources_unchanged']:
        raise ValueError('Independent reviewed scope differs')
    output = ROOT / f'work/runtime/v19-explicit-60864-{CREATION}-{args.operation}'
    if output.exists():
        raise ValueError('Permanent operator attempt exists; never retry')
    if args.operation == 'load':
        argv = [sys.executable, '-B', str(BOOT / 'loader.py'), '--build', str(BUILD),
                '--pid', str(PID), '--creation', CREATION, '--ack-disposable-test']
    else:
        loader = json.loads(bounded(BUILD / f'loader-{PID}-{CREATION}.json', 32768))
        identity = loader['identity']
        if identity['pid'] != PID or identity['creation'] != CREATION:
            raise ValueError('Explicit loader identity differs')
        argv = [sys.executable, '-I', '-B', str(CLIENT / 'launcher.py'), '--build', str(BUILD),
                '--pid', str(PID), '--creation', CREATION, '--session', identity['session'],
                'stage', args.operation, '--ack-disposable-research-send']
    output.mkdir()
    start = datetime.now(timezone.utc).isoformat()
    write(output / 'attempt.json', dict(operation=args.operation, argv=argv, pid=PID,
                                      creation=CREATION, pins=PINS, started_utc=start,
                                      retry_allowed=False, automatic_stage_chain=False))
    timed_out = False
    with (output / 'stdout').open('xb') as stdout, (output / 'stderr').open('xb') as stderr:
        try:
            completed = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=55, check=False)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            # subprocess.run terminates and collects its child. Remote game
            # state remains unknown; this does not authorize another attempt.
            timed_out = True
            code = None
    streams = {name: dict(bytes=(output/name).stat().st_size,
                         sha256=hashlib.sha256(bounded(output/name, 1048576)).hexdigest())
               for name in ('stdout', 'stderr')}
    write(output / 'completion.json', dict(operation=args.operation, exit_code=code,
          timed_out=timed_out, child_collected=True, streams=streams,
          completed_utc=datetime.now(timezone.utc).isoformat(), retry_allowed=False,
          effect_verified=False, production_ready=False, native_outcome='read actual receipt separately'))
    print(json.dumps(dict(operation=args.operation, output=str(output), exit_code=code,
                          timed_out=timed_out, child_collected=True), sort_keys=True))
    return 0 if code == 0 else 2

if __name__ == '__main__':
    raise SystemExit(main())
