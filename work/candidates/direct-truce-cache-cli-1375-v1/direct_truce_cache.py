"""Current directional pair +0x45 mask1, QUERY/VM_READ only; never an action API."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import struct
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = HERE.relative_to(ROOT).as_posix()
MANIFEST = HERE / 'source-manifest.json'
GAME = ROOT.parent / 'eu4.exe'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
R24 = 'work/capture_direct_truce_flags_20261015.py'
HOST = 'work/candidates/frida-entry-observer-1375-v1/capture_once.py'
HOST_MANIFEST = 'work/candidates/frida-entry-observer-1375-v1/host-manifest.json'
R23 = 'work/reports/war-peace-api-20261015-r23-truce-observation-contract/war/'
FIXED = {
    R24: '1677ccf7f03b93c44d3bb5313bae3350605f51c58855f381f5b516504f4bb904',
    HOST: 'b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e',
    HOST_MANIFEST: 'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166',
    R23 + 'manifest.json': '27173b65e73e13f64c42c0891b7b299602a6a7944b2946f48907d17a3d9f7778',
    'work/reports/war-peace-api-20261015-r23-independent-review/war/findings.json':
        '8d78398749fd0845ff4abbf8c297819aee58ea0ae3ce6ed1cf3c6f233d0017be',
    'work/reports/direct-truce-current-source-review-20261015-r1/independent-source-ready.json':
        '98b673b5e7c823d01b85988839ad1c7479f20439e8254be789b510e740be474b',
}
REQUIRED = {REL + '/' + name for name in ('direct_truce_cache.py', 'test_direct_truce_cache.py', 'README.md')}
RESEARCH_PREFIXES = ('eu4_bridge_', 'eu4_pair_', 'eu4_spy_', 'eu4_tag_command_', 'tag_diplomacy')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path, maximum=16*1024*1024):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, 'Selected file size bound')
    return raw


def pin(path):
    raw = read(path)
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def json_file(path, maximum=1024*1024):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Nonfinite JSON')
    return json.loads(read(path, maximum), object_pairs_hook=unique, parse_constant=invalid)


def local_path(name):
    require(type(name) is str and '\\' not in name and ':' not in name, 'Invalid source path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and name == path.as_posix(), 'Source traversal')
    absolute = (ROOT / name).resolve()
    require(absolute.is_relative_to(ROOT.resolve()), 'Source escapes project')
    return absolute


def verify_sources(path=MANIFEST):
    manifest = json_file(path)
    require(manifest.get('schema') == 'EU4-DIRECT-TRUCE-CACHE-CLI-SOURCE-MANIFEST/1'
            and manifest.get('sealed') is True and manifest.get('game_sha256') == GAME_SHA,
            'Reviewed sealed source manifest required before library import or process access')
    expected = manifest.get('source_pins')
    require(type(expected) is dict and REQUIRED | set(FIXED) <= set(expected)
            and len(expected) <= 64, 'Source graph incomplete or oversized')
    actual, total = {}, 0
    def check(name, value):
        nonlocal total
        require(type(value) is dict and set(value) == {'bytes', 'sha256'}
                and type(value['bytes']) is int and 0 < value['bytes'] <= 16*1024*1024
                and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']),
                'Invalid source pin')
        if name in actual:
            require(actual[name] == value, 'Conflicting source pin')
            return
        total += value['bytes']
        require(total <= 32*1024*1024 and len(actual) < 96, 'Source graph byte/count bound')
        actual[name] = pin(local_path(name))
        require(actual[name] == value, 'Selected source changed: ' + name)
    for name, value in expected.items():
        check(name, value)
    for name, sha in FIXED.items():
        require(actual[name]['sha256'] == sha, 'Frozen source root changed')
    static = json_file(local_path(R23 + 'manifest.json'))
    require(static['sealed'] is True and static['game_sha256'] == GAME_SHA, 'R23 source authority changed')
    for name, value in static['files'].items():
        require(type(name) is str and '/' not in name and '\\' not in name, 'R23 file path')
        check(R23 + name, value)
    for name, value in static['sources'].items():
        check(name, value)
    return dict(manifest=pin(path), source_pins=actual)


def exact_compile(name, expected):
    path = local_path(name)
    raw = read(path, 1024*1024)
    require(dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) == expected,
            'Library changed before exact-source compile')
    module = types.ModuleType('_direct_truce_library_' + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


class Libraries:
    """Reuse old source authentication/sample helpers, never old capture authority."""
    def __init__(self):
        self.initial = verify_sources()
        self.host = exact_compile(HOST, self.initial['source_pins'][HOST])
        self.r24 = exact_compile(R24, self.initial['source_pins'][R24])
        self.frozen = self.host.verify_manifest()
        self.guard()

    def guard(self):
        require(verify_sources() == self.initial, 'CLI/R24/static sources changed')
        require(self.host.verify_manifest() == self.frozen, 'Reused host source closure changed')

    def observer(self):
        self.guard()
        sys.path.insert(0, str(ROOT))
        try:
            module = self.host.load_local('bridge/diplomacy_effect_observer.py', self.frozen)
        finally:
            sys.path.pop(0)
        self.guard()
        return module

    def evidence(self):
        return dict(cli_manifest=self.initial['manifest'], selected_source_pins=self.initial['source_pins'],
            frozen_host_manifest_sha256=self.frozen['manifest_sha256'],
            frozen_host_local_pins=len(self.frozen['source_pins']),
            frozen_host_selected_external_pins=len(self.frozen['selected_external_pins']),
            reused_helpers=['source verification', 'host_sample', 'R24 typed pair/array guards'],
            old_fixed_pid_authority_reused=False, old_capture_executed=False,
            old_registered_argv_executed=False, REA_executed=False, Frida_executed=False)


def selection(pid, creation, actor, target):
    require(type(pid) is int and 0 < pid <= 0xffffffff, 'PID must be a positive DWORD')
    require(type(creation) is str and re.fullmatch('[0-9a-f]{16}', creation)
            and int(creation, 16) != 0, 'Creation must be nonzero 16 lowercase hex FILETIME digits')
    for tag in (actor, target):
        require(type(tag) is str and re.fullmatch('[A-Z0-9]{3}', tag), 'TAG must be exactly three A-Z/0-9 characters')
    require(actor != target, 'Directional pair must contain distinct TAGs')
    return dict(pid=pid, creation=creation, actor=actor, target=target)


def selected_handles(r, observer, root, table, actor, target):
    require(type(table) is bytes and len(table) == root['count']*8, 'Country table byte count')
    wanted = {actor.encode('ascii'): actor, target.encode('ascii'): target}
    selected = {}
    for slot, (address,) in enumerate(struct.iter_unpack('<Q', table)):
        if not address:
            continue
        handle = r.q(observer.ptr(address) + 0x20)
        tag = wanted.get((handle & 0xffffff).to_bytes(3, 'little'))
        if tag is None:
            continue
        parsed, _ = observer.full_handle(handle, root['count'], tag=tag)
        require(type(parsed) is int and 0 < parsed == slot < min(root['count'], 32768)
                and tag not in selected, 'Selected full handle and positive table slot disagree')
        selected[tag] = handle
    require(set(selected) == {actor, target}, 'Selected current TAG unavailable')
    return selected


def base_result(operation):
    return dict(schema='EU4-DIRECT-TRUCE-CACHE-CLI/1', operation=operation, status='unknown',
        game_sha256=GAME_SHA, direct_pair_cache_flag_set=None, selected_effect_verified=False,
        native_truce_helper_evaluated=False, linked_country_predicate_evaluated=False,
        truce_object_verified=False, expiry_verified=False, removed_state_verified=False,
        peace_completion_verified=False, request_effect_verified=False, native_ready=False,
        sender_authorized=False, lifetime_lease=False, atomic_snapshot=False,
        requests_published=0, native_game_calls=0, game_fields_written=0, hooks_installed=0,
        Frida_called=False, saves=0, reloads=0, automatic_retry=False, errors=[])


def observe(chosen, libraries):
    chosen = selection(**chosen)
    result = base_result('status')
    result.update(selection=chosen, captured_utc=datetime.now(timezone.utc).isoformat(),
        direction=chosen['actor'] + '->' + chosen['target'], samples=[], precheck=None, postcheck=None,
        selected_rpm_budget=None, selected_two_pass_equal=False, normal_context_exit=False,
        held_handle_cleared=False, close_os_return_checked=False, commit_after_context_exit=False,
        source_graph=libraries.evidence(), process_rights='QUERY/VM_READ/SYNCHRONIZE',
        evidence_scope='current directional pair cache byte +0x45 mask 1 only')
    started = time.perf_counter()
    try:
        observer = libraries.observer()
        backend = observer.TagCommandBackend()
        identity = dict(pid=chosen['pid'], creation=chosen['creation'], session=secrets.token_hex(16),
            dll_sha256=backend.manifest['dll']['sha256'], manifest_sha256=backend.manifest_sha)
        result['identity'] = identity
        result['identity_purpose'] = 'fresh read-only correlation nonce, not an installed TAG or request session'
        libraries.guard()
        with observer.RuntimeCapture(identity, backend) as cap:
            require(Path(cap.held.injector.GAME).resolve() == GAME.resolve(), 'Exact game path differs')
            require(not any(Path(path).name.lower().startswith(RESEARCH_PREFIXES) for _, path in cap.modules),
                    'Unexpected research module')
            result['precheck'] = libraries.host.host_sample(cap, observer)
            r = observer.BudgetReader(libraries.r24.AlignedPort(observer.HeldRPMPort(cap.held)))
            try:
                root = observer.roots(r, cap.base)
                require(root == result['precheck']['roots'] and root['manual_pause'] == 1, 'Selected paused roots differ')
                table = r.read(int(root['array'], 16), root['count']*8)
                result['country_pointer_table_raw_hex'] = table.hex()
                handles = selected_handles(r, observer, root, table, chosen['actor'], chosen['target'])
                for _ in range(2):
                    current = observer.roots(r, cap.base)
                    require(current == root and current['manual_pause'] == 1, 'Country/date/paused roots changed')
                    pair = libraries.r24.pair_sample(r, observer, cap.base, current, handles,
                                                    chosen['actor'], chosen['target'])
                    result['samples'].append(dict(roots=current,
                        selected_handles={key: hex(value) for key, value in handles.items()}, directional_pairs=[pair]))
                require(result['samples'][0] == result['samples'][1], 'Two directional pair projections differ')
                libraries.r24.check_country_table_binding(result['samples'], table)
                flag = result['samples'][0]['directional_pairs'][0]['direct_pair_cache_flag_set']
                require(type(flag) is bool, 'Cache state must be a strict boolean')
                result['selected_two_pass_equal'] = True
            finally:
                result['selected_rpm_budget'] = dict(calls=r.calls, bytes=r.bytes, largest=r.largest)
                result['postcheck'] = libraries.host.host_sample(cap, observer)
                require(result['precheck'] == result['postcheck'] and observer.pins() == cap.initial_pins,
                        'Host/observer postguards changed')
                libraries.guard()
        result['normal_context_exit'] = True
        require(cap.held.handle is None, 'Held handle not cleared after normal context exit')
        result['held_handle_cleared'] = True
        libraries.guard()
        # No successful state is committed until normal context cleanup and all
        # postguards have returned. Retained partial samples are diagnostics only.
        result['direct_pair_cache_flag_set'] = flag
        result['commit_after_context_exit'] = True
        result['status'] = 'observed_direct_pair_cache_flag'
    except Exception as exc:
        result['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
        result['direct_pair_cache_flag_set'] = None
        result['status'] = 'unknown'
    result['duration_ms_including_guards'] = round((time.perf_counter()-started)*1000, 3)
    return result


def result_code(result):
    if result.get('operation') in ('catalog', 'check'):
        return 0 if result.get('status') == 'files_verified' else 2
    okay = result.get('operation') == 'status' and result.get('status') == 'observed_direct_pair_cache_flag'
    okay = okay and type(result.get('direct_pair_cache_flag_set')) is bool and result.get('errors') == []
    okay = okay and all(result.get(key) is True for key in (
        'selected_two_pass_equal', 'normal_context_exit', 'held_handle_cleared', 'commit_after_context_exit'))
    return 0 if okay else 2


def run(operation, chosen=None, *, library_factory=Libraries):
    result = base_result(operation)
    try:
        require(operation in ('catalog', 'check', 'status'), 'Unsupported operation')
        if operation == 'status':
            require(type(chosen) is dict, 'Exact current selection required')
            chosen = selection(**chosen)
        else:
            require(chosen is None, 'File-only commands accept no process selection')
        libraries = library_factory()
        if operation == 'status':
            return observe(chosen, libraries)
        result['source_graph'] = libraries.evidence()
        if operation == 'catalog':
            result['profiles'] = [dict(id='direct_pair_truce_cache', field='pair+0x45', mask=1,
                direction='actor->target; reverse requires a distinct current read',
                state='strict boolean, including false as a successful observation',
                requirements=['exact PID/creation/path/PE/SHA', 'manual_pause=1', 'no research module',
                              'typed complete handles/positive array slots', 'two equal passes and source/host prepost'],
                unknowns=['complete native linked predicate', 'typed truce object/expiry/removed',
                          'peace request effect or causal completion'])]
        libraries.guard()
        result['status'] = 'files_verified'
    except Exception as exc:
        result['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = Parser(description=__doc__, epilog='Exit 0: files verified or a current boolean cache state observed (false also 0). Exit 2: unknown/invalid. No exit code proves a truce object, expiry, action effect or peace completion.')
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('catalog', help='File-only profile and scope')
    commands.add_parser('check', help='File-only source graph verification')
    status = commands.add_parser('status', help='One held process, two directional current-cache passes')
    status.add_argument('--pid', type=int, required=True)
    status.add_argument('--creation', required=True)
    status.add_argument('--actor', required=True)
    status.add_argument('--target', required=True)
    try:
        args = vars(parser.parse_args(argv))
        operation = args.pop('operation')
        result = run(operation, args if operation == 'status' else None)
    except Exception as exc:
        result = base_result('unknown')
        result['errors'].append(dict(type=type(exc).__name__, message=str(exc)))
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return result_code(result)


if __name__ == '__main__':
    raise SystemExit(main())
