"""Construct an explicit frozen v17 preflight case; never run a reviewer or game."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNTIME = 'work/runtime/native1375-v17/'
REVIEWER = 'work/candidates/v17-acceptance-experiment-review/'
FILES = ('session.json', 'install.claim', 'research-1375.jsonl', 'phase-lifecycle.claim',
         'phase-owned-peace-lifecycle.claim', 'phase-preview.claim', 'phase-command.claim')
SCOPE = {'pid', 'creation', 'world_cookie', 'window_thread', 'initial_raw_date', 'dll_sha256',
         'manifest_sha256', 'bridge_start_rva', 'prefix_bytes', 'prefix_sha256', 'preflight_case', 'preflight_summary'}
REQUIRED = set(FILES) | {'before', 'after', 'loader', 'status', 'build', 'snapshot'}
CAPTURES = {'loader_plan', 'health_after_install'} | {
    phase + '_' + kind for phase in ('lifecycle', 'owned_peace', 'preview', 'command') for kind in ('publish', 'status')}
MAX_FILE, MAX_TOTAL = 2 * 1024 * 1024, 8 * 1024 * 1024


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(x, low=0, high=2**64-1):
    return type(x) is int and low <= x <= high


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def wire(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def decode(raw):
    def pairs(rows):
        result = {}
        for k, v in rows:
            require(k not in result, 'Duplicate JSON key')
            result[k] = v
        return result
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    require(type(value) is dict, 'JSON object required')
    return value


def bounded(path, maximum=MAX_FILE):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, 'Read limit exceeded')
    return raw


def relative(root, name):
    require(type(name) is str and '\\' not in name and ':' not in name, 'Canonical relative path required')
    parts = PurePosixPath(name)
    require(parts.parts and not parts.is_absolute() and str(parts) == name
            and all(p not in ('.', '..') and not p.startswith('session-') for p in parts.parts),
            'Unconfined path or growing session path')
    cursor = Path(root).resolve()
    for part in parts.parts:
        cursor /= part
        require(not cursor.is_symlink() and not cursor.is_junction(), 'Linked path forbidden')
    require(cursor.resolve().is_relative_to(Path(root).resolve()), 'Escaped root')
    return cursor


def template():
    descriptor = {'path': None, 'size_bytes': None, 'sha256': None}
    return {'schema_version': 1, 'purpose': 'explicit_v17_preflight_construction_plan',
            'scope': dict.fromkeys(sorted(SCOPE)), 'prefix_directory': None, 'output_directory': None,
            'inputs': {k: dict(descriptor) for k in sorted(REQUIRED)},
            'captures': {k: dict(descriptor) for k in sorted(CAPTURES)}}


def construct(config, root=ROOT):
    require(type(config) is dict and set(config) == set(template()) and type(config['schema_version']) is int
            and config['schema_version'] == 1 and config['purpose'] == 'explicit_v17_preflight_construction_plan', 'Plan schema')
    scope = config['scope']
    require(type(scope) is dict and set(scope) == SCOPE, 'Scope schema')
    require(integer(scope['pid'], 1, 2**32-1) and integer(scope['window_thread'], 1, 2**32-1)
            and integer(scope['initial_raw_date'], 1, 2**31-1) and integer(scope['bridge_start_rva'], 1, 2**32-1)
            and integer(scope['prefix_bytes'], 1, MAX_FILE), 'Scope integer type/bounds')
    require(type(scope['creation']) is str and re.fullmatch('[0-9a-f]{16}', scope['creation'])
            and int(scope['creation'], 16) > 0, 'Exact creation required')
    require(type(scope['world_cookie']) is str and re.fullmatch('0x[0-9a-f]+', scope['world_cookie'])
            and int(scope['world_cookie'], 16) >= 0x10000, 'World identity')
    require(all(type(scope[k]) is str and re.fullmatch('[0-9a-f]{64}', scope[k])
                for k in ('dll_sha256', 'manifest_sha256', 'prefix_sha256')), 'Explicit lowercase SHA required')
    prefix, output = config['prefix_directory'], config['output_directory']
    require(prefix == RUNTIME + f'directional-preflight-prefix-{scope["pid"]}', 'Explicit frozen prefix path')
    require(type(output) is str and output.startswith(RUNTIME) and output != prefix
            and not output.startswith(prefix + '/'), 'Independent output path required')
    require(scope['preflight_case'] == output + '/preflight-case.json'
            and scope['preflight_summary'] == output + '/preflight-summary.json', 'NEW case/summary scope paths')
    relative(root, output)
    require(type(config['inputs']) is dict and set(config['inputs']) == REQUIRED
            and type(config['captures']) is dict and set(config['captures']) == CAPTURES, 'Explicit input/capture inventory')
    descriptors = config['inputs'] | config['captures']
    inventory = set()
    for entry in relative(root, prefix).iterdir():
        require(entry.is_file() and entry.name in FILES and entry.name not in inventory, 'Frozen prefix inventory differs')
        inventory.add(entry.name)
    require(inventory == set(FILES), 'Frozen prefix requires exactly seven files')
    raw = {}; total = 0
    for key, d in descriptors.items():
        require(type(d) is dict and set(d) == {'path', 'size_bytes', 'sha256'}
                and integer(d['size_bytes'], 1, MAX_FILE) and type(d['sha256']) is str
                and re.fullmatch('[0-9a-f]{64}', d['sha256']), 'Missing/invalid explicit descriptor: ' + key)
        # Status and command_status intentionally reference the same fixed capture.
        require(type(d['path']) is str and d['path'].startswith(RUNTIME), 'Input outside explicit v17 runtime')
        if key in FILES:
            require(d['path'] == prefix + '/' + key, 'Prefix file path differs')
        else:
            require(d['path'].endswith('.json'), 'Capture must be JSON')
        value = bounded(relative(root, d['path'])); total += len(value)
        require(total <= MAX_TOTAL and len(value) == d['size_bytes'] and sha(value) == d['sha256'], 'Input bytes/hash differ: ' + key)
        raw[key] = value
    require(config['inputs']['before']['path'] != config['inputs']['after']['path'], 'Before/after must be independent files')
    source_pins = decode(bounded(HERE / 'source-pins.json', 65536))
    for name, d in source_pins.items():
        value = bounded(relative(root, name))
        require(len(value) == d['bytes'] and sha(value) == d['sha256'], 'Sealed reviewer lineage changed')
    build = decode(raw['build']); status = decode(raw['status'])['report']; snapshot = decode(raw['snapshot'])
    require(sha(raw['build']) == scope['manifest_sha256'] and build['purpose'] == 'restricted_pair_lab_1375_v17'
            and build['protocol_version'] == 'EU4LAB/3' and build['dll_sha256'].lower() == scope['dll_sha256']
            and type(build['bridge_start_export_rva']) is int and build['bridge_start_export_rva'] == scope['bridge_start_rva'], 'Build binding')
    log = raw['research-1375.jsonl']
    require(len(log) == scope['prefix_bytes'] and sha(log) == scope['prefix_sha256'] and log.endswith(b'\n'), 'Fixed complete prefix differs')
    for line in log.splitlines(keepends=True):
        require(len(line) <= 16384, 'Prefix line bound')
        e = decode(line)
        require(not e.get('event', '').startswith(('lab_request', 'lab_acceptance', 'lab_lease')), 'Prefix contains requests')
    require(type(snapshot['pid']) is int and snapshot['pid'] == scope['pid'] and snapshot['creation'] == scope['creation']
            and snapshot['prefix_sha256'] == scope['prefix_sha256'] and snapshot['prefix_bytes'] == scope['prefix_bytes']
            and snapshot['source_process_exit_observed'] is False and snapshot['whole_active_log_unchanged_verified'] is False,
            'Snapshot is not the declared prefix')
    require(snapshot['snapshot_file_sha256'] == {k: sha(raw[k]) for k in FILES}, 'Snapshot seven files differ')
    require(type(status['pid']) is int and status['pid'] == scope['pid'] and status['creation'] == scope['creation']
            and type(status['last_sequence']) is int and status['last_sequence'] == 0
            and status['log_sha256'] == scope['prefix_sha256'] and snapshot['status_sha256'] == sha(raw['status']), 'Exact seq0 status')
    before, after = decode(raw['before']), decode(raw['after'])
    for d in (before, after):
        require(d.get('read_only') is True and type(d['source']['pid']) is int and d['source']['pid'] == scope['pid']
                and type(d['source']['process_creation_filetime']) is int
                and d['source']['process_creation_filetime'] == int(scope['creation'], 16)
                and d['source']['held_identity_verified_before_and_after'] is True, 'Full held diagnostic required; status cannot substitute')
        require(d['state']['game_pointer'] == scope['world_cookie']
                and type(d['state']['current_raw_date']) is int and d['state']['current_raw_date'] == scope['initial_raw_date'], 'Diagnostic world/date')
    require(datetime.fromisoformat(before['captured_at_utc']) < datetime.fromisoformat(after['capture_started_at_utc']), 'Independent chronological diagnostics required')
    projection = ('player', 'current_raw_date', 'actor', 'target', 'actor_diplomats', 'relation_cooldown')
    require(wire({k: before['state'][k] for k in projection}) == wire({k: after['state'][k] for k in projection}), 'Selected diagnostic fields differ')
    case = {'schema_version': 1, 'purpose': 'fixed_v17_preflight_case', 'pid': scope['pid'], 'creation': scope['creation'],
            'world_cookie': scope['world_cookie'], 'raw_date': scope['initial_raw_date'], 'window_thread': scope['window_thread'],
            'build_manifest_sha256': scope['manifest_sha256'], 'dll_sha256': scope['dll_sha256'],
            'log_prefix_sha256': scope['prefix_sha256'], 'log_prefix_bytes': scope['prefix_bytes'],
            'reviewer_sha256': source_pins[REVIEWER + 'preflight.py']['sha256'],
            'inputs': {k: config['inputs'][k] for k in (*FILES, 'before', 'after', 'loader', 'status')}}
    # Reread exact declared bytes only; never discover or touch an active session.
    for key, d in descriptors.items():
        require(bounded(relative(root, d['path'])) == raw[key], 'Input changed while constructing')
    return {'scope': scope, 'case': case, 'construction': {'schema_version': 1, 'finalized': False,
            'preflight_only': True, 'formal_review_performed': False, 'request_count_in_selected_prefix': 0,
            'whole_session_stopped': False, 'actual_experiment_case_prepared': False, 'runtime_promoted': False,
            'production_backend_registered': False, 'source_pins': source_pins, 'input_descriptors': descriptors}}


def create(path, value):
    with path.open('xb') as stream:
        stream.write(wire(value)); stream.flush(); os.fsync(stream.fileno())


def publish(config, root=ROOT):
    packet = construct(config, root)
    directory = relative(root, config['output_directory'])
    directory.mkdir(exist_ok=False)
    create(directory / 'scope.json', packet['scope'])
    create(directory / 'preflight-case.json', packet['case'])
    create(directory / 'construction.json', packet['construction'])
    # preflight-summary.json is reserved for root's later independent review.
    return directory


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--template', type=Path); mode.add_argument('--config', type=Path)
    p.add_argument('--create', action='store_true'); args = p.parse_args()
    if args.template:
        require(not args.create, 'Template does not publish a case'); create(args.template, template())
    else:
        config = decode(bounded(args.config, 65536))
        if args.create:
            print(publish(config))
        else:
            construct(config); print('construction inputs checked; no review or output')


if __name__ == '__main__':
    main()
