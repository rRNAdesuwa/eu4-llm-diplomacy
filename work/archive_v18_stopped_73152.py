"""File-only exact positive-session archive; never claim an unobserved exit."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'work/runtime/v18-stopped-source-archive-32672-20261008a/files'
BUILD = 'work/candidates/v18-spy-bootstrap-lab-1375/build-final'
PID, CREATION = 73152, '01dd57112fab9947'
MAX_FILE, MAX_TOTAL = 4 * 1024 * 1024, 32 * 1024 * 1024


def require(value, reason):
    if not value:
        raise ValueError(reason)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path):
    require(path.resolve().is_relative_to(ROOT), 'Escaped input')
    for item in (path, *path.parents):
        if item.exists():
            require(not item.is_symlink() and not (getattr(item.stat(), 'st_file_attributes', 0) & 0x400), 'Reparse input')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    require(len(raw) <= MAX_FILE, 'Individual byte budget')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files, origins = {}, {}

    def add(name, expected=None, archived=False):
        require(type(name) is str and '\\' not in name, 'Canonical source name')
        source = (OLD if archived else ROOT) / name
        raw = read(source)
        require(expected is None or pin(raw) == expected, 'Changed pin: ' + name)
        require(name not in files or files[name] == raw, 'Conflicting exact source')
        files[name], origins[name] = raw, source.relative_to(ROOT).as_posix()
        require(len(files) <= 256 and sum(map(len, files.values())) <= MAX_TOTAL, 'Aggregate byte budget')
        return raw

    def mapping(name, local=False, historical=False):
        data = json.loads(add(name))
        entries = data['sources'] if local else data
        require(type(entries) is dict and len(entries) <= 128, 'Bounded pin inventory')
        prefix = Path(name).parent.as_posix() + '/' if local else ''
        for item, expected in entries.items():
            full = prefix + item
            # Only the protocol author's obsolete API preimage is historical.
            # The actual DLL/R3 runtime manifest has no mutable API dependency.
            add(full, expected, historical and full == 'bridge/diplomacy_api.py')

    for stem in ('v18-spy-coherent-client-r3-1375', 'v18-spy-group-census-1375'):
        directory = 'work/candidates/' + stem + '/'
        mapping(directory + 'input-pins.json')
        mapping(directory + 'source-index.json', local=True)
        add(directory + 'review.json')
    mapping('work/candidates/v18-spy-no-send-contract-1375/source-pins.json', historical=True)
    mapping('work/candidates/v18-spy-no-send-contract-1375/candidate-index.json')
    manifest = json.loads(add(BUILD + '/build.json'))
    require(manifest['dll_sha256'] == '6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b', 'Frozen DLL')
    for name, expected in manifest['sources'].items():
        add(name, expected)
    add(BUILD + '/' + manifest['dll_name'], {'bytes': manifest['dll_bytes'], 'sha256': manifest['dll_sha256']})
    loader = json.loads(add(f'{BUILD}/loader-{PID}-{CREATION}.json'))
    identity = loader['identity']
    require(identity['pid'] == PID and identity['creation'] == CREATION and loader['plan_only'] is False, 'Exact actual loader')
    require(identity['session'] == '76d14fd2f244b152106ccfb9d4844005', 'Exact positive session')
    add(f'{BUILD}/bootstrap-{PID}-{CREATION}.request')
    directory = f'{BUILD}/spy18-{PID}-{CREATION}-{identity["session"]}'
    names = {'raw-events.jsonl', 'bootstrap-events.jsonl'} | {f'{n}.{suffix}' for n in (1, 2, 3) for suffix in ('publisher-intent.json', 'request', 'claim')}
    require({p.name for p in (ROOT / directory).iterdir()} == names, 'Exact session inventory')
    for name in sorted(names):
        add(directory + '/' + name)
    for name in ('v18-spy5-census-initial-73152.json', 'v18-spy5-census-final-73152.json', 'v18-no-send-complete-r2-73152.json', 'v18-no-send-exit-73152.json', 'v18-positive-fixture-ui-73152.json', 'v18-positive-stopped-ui-73152.json', 'test-launch-v18-positive-20261008a.json'):
        add('work/runtime/' + name)
    complete = json.loads(files['work/runtime/v18-no-send-complete-r2-73152.json'])
    require(complete['identity'] == identity and complete['completed'] is True and complete['completed_stages'] == 3 and complete['send_supported'] is False, 'Complete no-send record')
    require(all(value is True for stage in complete['legality_results'].values() for value in stage.values()), 'Positive full/generic gates')
    stopped = json.loads(files['work/runtime/v18-positive-stopped-ui-73152.json'])
    require(stopped['pid'] == PID and stopped['creation'] == CREATION and stopped['normal_menu_quit_clicked'] is True and stopped['later_pid_absent'] is True and stopped['held_normal_exit_verified'] is False, 'Honest stopped observation')
    timed = json.loads(files['work/runtime/v18-no-send-exit-73152.json'])
    require(timed['pid'] == PID and timed['creation'] == CREATION and timed['exit_observed'] is False and timed['wait_status'] == 258, 'Preserved watcher timeout')
    target = args.output.absolute()
    require(target.resolve().is_relative_to(ROOT / 'work/runtime') and not target.exists(), 'New bounded archive')
    target.mkdir()
    inventory = {}
    for name, raw in sorted(files.items()):
        destination = target / 'files' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(pin(read(destination)) == pin(raw), 'Archive postimage differs')
        inventory[name] = pin(raw)
    record = {'kind': 'stopped_positive_v18_source_archive', 'original_root': str(ROOT), 'identity': identity, 'files': inventory, 'source_origins': origins, 'total_bytes': sum(map(len, files.values())), 'game_accessed': False, 'records_rewritten': False, 'relocated_execution_supported': False, 'normal_menu_exit_ui_observed': True, 'later_pid_absence_observed': True, 'held_normal_exit_verified': False, 'exact_exit_filetime_verified': False, 'production_ready': False}
    with (target / 'archive.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'archive': str(target), 'files': len(inventory), 'bytes': record['total_bytes'], 'index': pin(read(target / 'archive.json'))}, sort_keys=True))


if __name__ == '__main__':
    main()
