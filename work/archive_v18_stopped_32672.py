"""File-only snapshot of this exact stopped no-send session and source lineage.

This copies exact bytes, without altering loader paths or promoting evidence.
The output is a source archive, not a relocated executable installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = 'work/candidates/v18-spy-bootstrap-lab-1375/build-final'
PID = 32672
CREATION = '01dd570cf31aae9d'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(name):
    require(type(name) is str and '\\' not in name, 'Canonical relative name')
    path = (ROOT / name).absolute()
    require(path.resolve().is_relative_to(ROOT), 'Escaped source')
    for item in (path, *path.parents):
        if item.exists():
            require(not item.is_symlink() and not (getattr(item.stat(), 'st_file_attributes', 0) & 0x400), 'Reparse source')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    require(len(raw) <= MAX_FILE, 'Individual archive byte budget')
    return raw


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = {}
    def add(name, expected=None):
        raw = read(name)
        require(expected is None or pin(raw) == expected, 'Source pin changed: ' + name)
        require(name not in files or files[name] == raw, 'Conflicting snapshot source')
        files[name] = raw
        require(len(files) <= 256 and sum(map(len, files.values())) <= MAX_TOTAL, 'Aggregate archive budget')
        return raw
    def mapping(name, local=False):
        data = json.loads(add(name))
        entries = data['sources'] if local else data
        require(type(entries) is dict and len(entries) <= 128, 'Bounded pin inventory')
        prefix = Path(name).parent.as_posix() + '/' if local else ''
        for item, expected in entries.items():
            add(prefix + item, expected)
    for stem in ('v18-spy-coherent-client-r3-1375', 'v18-spy-group-census-1375'):
        directory = 'work/candidates/' + stem + '/'
        mapping(directory + 'input-pins.json')
        mapping(directory + 'source-index.json', local=True)
        add(directory + 'review.json')
    mapping('work/candidates/v18-spy-no-send-contract-1375/source-pins.json')
    mapping('work/candidates/v18-spy-no-send-contract-1375/candidate-index.json')
    manifest = json.loads(add(BUILD + '/build.json'))
    require(manifest['dll_sha256'] == '6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b', 'Frozen DLL identity')
    for name, expected in manifest['sources'].items():
        add(name, expected)
    add(BUILD + '/' + manifest['dll_name'], {'bytes': manifest['dll_bytes'], 'sha256': manifest['dll_sha256']})
    loader = json.loads(add(f'{BUILD}/loader-{PID}-{CREATION}.json'))
    identity = loader['identity']
    require(identity['pid'] == PID and identity['creation'] == CREATION and loader['plan_only'] is False, 'Exact actual loader')
    session = identity['session']
    require(type(session) is str and len(session) == 32 and all(x in '0123456789abcdef' for x in session), 'Session ID')
    add(f'{BUILD}/bootstrap-{PID}-{CREATION}.request')
    directory = f'{BUILD}/spy18-{PID}-{CREATION}-{session}'
    names = {'raw-events.jsonl', 'bootstrap-events.jsonl'} | {f'{n}.{suffix}' for n in (1, 2, 3) for suffix in ('publisher-intent.json', 'request', 'claim')}
    require({p.name for p in (ROOT / directory).iterdir()} == names, 'Exact complete session inventory')
    for name in sorted(names):
        add(directory + '/' + name)
    for name in ('v18-spy5-census-initial-32672.json', 'v18-spy5-census-final-32672.json', 'v18-no-send-complete-r2-32672.json', 'v18-no-send-exit-32672.json', 'test-launch-v18-no-send-20261008c.json'):
        add('work/runtime/' + name)
    exited = json.loads(files['work/runtime/v18-no-send-exit-32672.json'])
    require(exited['pid'] == PID and exited['creation'] == CREATION and exited['exit_observed'] is True and exited['exit_code'] == 0, 'Exact held normal exit')
    complete = json.loads(files['work/runtime/v18-no-send-complete-r2-32672.json'])
    require(complete['identity'] == identity and complete['completed'] is True and complete['completed_stages'] == 3 and complete['send_supported'] is False, 'Complete source-bound no-send capture')
    target = args.output.absolute()
    require(target.resolve().is_relative_to(ROOT / 'work/runtime') and not target.exists(), 'New archive inside work/runtime')
    target.mkdir()
    inventory = {}
    for name, raw in sorted(files.items()):
        destination = target / 'files' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(pin(destination.read_bytes()) == pin(raw), 'Archive postimage differs')
        inventory[name] = pin(raw)
    record = {'kind': 'exact_stopped_v18_source_archive', 'original_root': str(ROOT), 'identity': identity, 'files': inventory, 'total_bytes': sum(map(len, files.values())), 'game_accessed': False, 'records_rewritten': False, 'relocated_execution_supported': False, 'production_ready': False}
    with (target / 'archive.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'archive': str(target), 'files': len(inventory), 'bytes': record['total_bytes'], 'index': pin((target / 'archive.json').read_bytes())}, sort_keys=True))


if __name__ == '__main__':
    main()
