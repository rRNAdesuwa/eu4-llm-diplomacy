"""Candidate CLI; no execution before an independently sealed source manifest.

catalog/check/prepare: exit 0 means that local operation succeeded, not an
action completed. status/watch: 0 selected effect, 3 proven waiting, 2 unknown.
No installer, publication, legacy baseline import, HTTP or retry operation.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RELATIVE = HERE.relative_to(ROOT).as_posix()
MANIFEST = HERE/'candidate-cli-manifest.json'
MODULE = RELATIVE+'/relation_request_observer.py'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
NATIVE = 'bridge/native/tag_diplomacy_1375_v31/build-7/build/build.json'
NATIVE_SHA = 'd4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a'
FROZEN_MANIFESTS = {
    'bridge/diplomacy_live_observer_manifest_1375.json': 'f7a2a64aa2c9fbc79a843af0b4c1b81cb7df22e3d09104a3fb718b06306b43ca',
    'bridge/diplomacy_reply_observer_manifest_1375.json': '31f3c1d936b751433ecf1dcbf989fb50e2cb65f529651bd23976060fb1e07580',
    'bridge/diplomacy_observer_manifest_1375.json': 'a75dab49e101ac95f2a714032829c4b52629fd78db04db0bd3896df1ce24143e',
    'bridge/knowledge_effect_reader_v2_manifest_1375.json': '0de127018998d2e1dd6d06b3c9c6651dce037a7fc495a4ab11845c4a89ba8509',
    'bridge/relation_effect_reader_manifest_1375.json': 'a7f49bca379b725e2987d425c849272b6ca05fe9ad6c3aa6579deead2c80e753',
    NATIVE: NATIVE_SHA,
}
REQUIRED_FILES = {RELATIVE+'/'+name for name in (
    'relation_request_cli.py','test_relation_request_cli.py','CLI.md',
    'relation_request_observer.py','test_relation_request_observer.py','README.md')}
ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError)
DEFAULT_STORE = ROOT/'work/runtime/relation-request-candidate-observations'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode(raw):
    def unique(pairs):
        value = {}
        for key,item in pairs:
            require(key not in value, 'Duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('Nonfinite JSON value: '+value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def bounded_read(path, maximum):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum+1)
    require(len(raw) <= maximum, 'File size bound: '+str(path))
    return raw


def source_path(name):
    require(type(name) is str and '\\' not in name and ':' not in name,
            'Source pin must be a relative POSIX path')
    parts = PurePosixPath(name)
    require(not parts.is_absolute() and '..' not in parts.parts and name == parts.as_posix(),
            'Invalid source pin path')
    result = (ROOT/name).resolve()
    require(result.is_relative_to(ROOT.resolve()), 'Source pin escapes project root')
    return result


def file_pin(path, maximum=16*1024*1024):
    total, sha = 0, hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(65536):
            total += len(block)
            require(total <= maximum, 'Source size bound: '+str(path))
            sha.update(block)
    return dict(bytes=total, sha256=sha.hexdigest())


def verify_manifest(manifest_path=MANIFEST):
    """Standard-library bootstrap; does not import bridge/candidate code.

    The private parameter exists for controlled temporary test manifests. There
    is deliberately no command-line override of the production manifest path.
    """
    raw = bounded_read(manifest_path, 262144)
    manifest = decode(raw)
    require(manifest['schema'] == 'EU4-RELATION-REQUEST-CLI-MANIFEST/1'
            and manifest['sealed'] is True and manifest['game_sha256'] == GAME_SHA
            and manifest['native_manifest_sha256'] == NATIVE_SHA,
            'A reviewed, sealed candidate CLI manifest is required')
    pins = manifest['source_pins']
    require(type(pins) is dict and 1 <= len(pins) <= 256
            and REQUIRED_FILES <= set(pins) and set(FROZEN_MANIFESTS) <= set(pins),
            'Candidate CLI source graph incomplete')
    total = 0
    for name, expected in pins.items():
        require(type(expected) is dict and set(expected) == {'bytes','sha256'}
                and type(expected['bytes']) is int and 0 < expected['bytes'] <= 16*1024*1024
                and type(expected['sha256']) is str and re.fullmatch('[0-9a-f]{64}',expected['sha256']),
                'Invalid source pin metadata')
        total += expected['bytes']
        require(total <= 128*1024*1024, 'Total source graph size bound')
        require(file_pin(source_path(name)) == expected, 'Candidate CLI source changed: '+name)
    require(manifest['candidate_module_sha256'] == pins[MODULE]['sha256'], 'Candidate module digest differs')
    # Validate closure before executing candidate imports. Checking only the
    # new wrapper while omitting the frozen reader dependencies is insufficient.
    for name, sha in FROZEN_MANIFESTS.items():
        require(pins[name]['sha256'] == sha, 'Frozen dependency manifest changed: '+name)
        dependency = decode(bounded_read(source_path(name), 1024*1024))
        require(dependency['game_sha256'] == GAME_SHA, 'Frozen game identity differs')
        for dependency_name, expected in dependency['source_pins'].items():
            require(pins.get(dependency_name) == expected, 'Frozen dependency omitted: '+dependency_name)
        if name == NATIVE:
            require(len(dependency['source_pins']) == 44 and len(dependency['actions']) == 120,
                    'Frozen native registry/pin count differs')
            dll_name = str(PurePosixPath(NATIVE).parent/dependency['DLL'])
            require(pins.get(dll_name) == dependency['dll'], 'Frozen DLL omitted from CLI graph')
    return dict(manifest_path=str(Path(manifest_path).resolve()),
                manifest_sha256=hashlib.sha256(raw).hexdigest(), source_pins=pins)


def guard(initial, manifest_path):
    require(verify_manifest(manifest_path) == initial, 'Candidate CLI manifest/source graph changed during operation')


def load_candidate(initial):
    raw = bounded_read(source_path(MODULE), 1024*1024)
    require(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) == initial['source_pins'][MODULE],
            'Candidate module changed immediately before import')
    # Compile the verified source bytes, bypassing an unrelated cached .pyc.
    sys.path.insert(0,str(ROOT))
    try:
        module = types.ModuleType('relation_request_cli_candidate')
        module.__file__ = str(source_path(MODULE))
        exec(compile(raw,module.__file__,'exec'),module.__dict__)
    finally:
        sys.path.pop(0)
    return module


def checked_module(module, initial):
    for name, expected in module.source_pins().items():
        require(initial['source_pins'].get(name) == expected, 'Candidate dependency missing from CLI graph: '+name)


def proven_waiting(value):
    """A text label alone cannot turn uncertainty into exit 3."""
    try:
        command, reply = value['command'], value['reply']
        selected = reply['selected']
        pending = selected['pending']
        matches = pending['selected_matches']
        actor, recipient = selected['actor'], selected['recipient']
        require(value['transport_state'] == 'dispatched' and command['action'] == 'ask_for_march'
                and value['request_state'] == reply['request_state'] == 'waiting_for_recipient'
                and reply['status'] == 'sampled_equal' and selected['identity'] == value['identity']
                and (actor['tag'],recipient['tag']) == (command['actor'],command['target'])
                and type(pending['count']) is int and 1 <= pending['count'] <= 128
                and type(pending['iteration']) is int and pending['iteration'] == 0
                and type(matches) is list and len(matches) == 1,
                'No unique observed pending reply')
        row = matches[0]
        require(type(row['state_raw']) is int and row['state_raw'] == 0
                and row['state_label'] == 'pending_observed'
                and type(row['native_request_id']) is int
                and -(1 << 31) <= row['native_request_id'] < (1 << 31) and row['native_request_id'] != 0
                and type(reply['native_request_id']) is int
                and -(1 << 31) <= reply['native_request_id'] < (1 << 31)
                and reply['native_request_id'] == row['native_request_id']
                and type(row['token']) is int and row['token'] == 0x3021
                and type(row['value_raw']) is int and row['value_raw'] == 1
                and (row['actor_handle'],row['original_actor_handle'],row['recipient_handle'])
                == (actor['handle'],actor['handle'],recipient['handle']), 'Pending reply evidence differs')
        return True
    except ERRORS:
        return False


def result_code(value):
    effect = value.get('effect') or {}
    if (effect.get('selected_effect_verified') is True and effect.get('status') == 'observed'
            and value.get('transport_state') == 'dispatched'):
        return 0
    return 3 if proven_waiting(value) else 2


def compact(value):
    effect = value.get('effect') or {}
    relation = value.get('relation') or {}
    selected = relation.get('snapshot') or {}
    obj = selected.get('object') or {}
    reply = value.get('reply') or {}
    reply_selected = reply.get('selected') or {}
    matches = (reply_selected.get('pending') or {}).get('selected_matches', [])
    knowledge = value.get('knowledge') or {}
    sharing = knowledge.get('selected') or {}
    return dict(schema='EU4-RELATION-REQUEST-CLI-COMPACT/1',
        request_id=value.get('request_id'), command=value.get('command'), identity=value.get('identity'),
        transport_state=value.get('transport_state'), completion_state=value.get('completion_state'),
        request_state=value.get('request_state'), effect_status=effect.get('status'),
        selected_effect_verified=effect.get('selected_effect_verified') is True,
        completion_stage=effect.get('completion_stage'), changes=effect.get('changes',{}),
        relation_status=relation.get('status'), relation_pair=selected.get('pair'),
        relation_direction_matches=obj.get('requested_direction_matches'),
        relation_first_handle=obj.get('first_handle'), relation_second_handle=obj.get('second_handle'),
        relation_object_address=obj.get('address'), relation_two_pass_equal=relation.get('two_pass_equal'),
        pending_requests=[{k:row.get(k) for k in ('native_request_id','state_raw','state_label',
            'actor_handle','recipient_handle')} for row in matches],
        correlated_notifications=reply.get('correlated_notifications',[]),
        knowledge_pair_status=knowledge.get('status'), knowledge_pair=sharing.get('pair'),
        knowledge_provider=sharing.get('provider'), knowledge_recipient=sharing.get('recipient'),
        effect_failure=effect.get('failure'), reply_failure=reply.get('failure'), record=value.get('record'),
        proven_waiting=proven_waiting(value), AI_acceptance_verified=False, persistence_verified=False,
        native_calls=0,requests_published=0,memory_written=False,saves_written=0,automatic_command_retry=False)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--session-file',type=Path)
    result.add_argument('--store',type=Path,default=DEFAULT_STORE)
    result.add_argument('--allow-tag-host',action='store_true')
    operations = result.add_subparsers(dest='operation',required=True)
    operations.add_parser('check',help='Validate sealed files only; no candidate import or process')
    operations.add_parser('catalog',help='Read candidate catalog; no process')
    prepare = operations.add_parser('prepare',help='Fresh local baseline only; exit 0 is not action completion')
    for name in ('request-id','action','actor','target'):
        prepare.add_argument('--'+name,required=True)
    for name in ('status','watch'):
        sub = operations.add_parser(name,help='0 selected effect, 3 proven waiting, 2 unknown')
        sub.add_argument('--request-id',required=True)
        sub.add_argument('--compact',action='store_true')
        if name == 'watch':
            sub.add_argument('--duration-seconds',type=int,default=30)
            sub.add_argument('--interval-ms',type=int,default=1000)
            sub.add_argument('--max-samples',type=int,default=32)
    return result


def emit(value, output):
    raw = json.dumps(value,ensure_ascii=True,allow_nan=False)
    require(len(raw.encode('ascii')) <= 2*1024*1024, 'CLI response bound')
    print(raw,file=output,flush=True)


def main(argv=None, *, _manifest=MANIFEST, _loader=load_candidate,
         _clock=time.monotonic, _sleep=time.sleep, _output=None):
    """Private dependency arguments are for offline tests, never CLI flags."""
    output = sys.stdout if _output is None else _output
    args = parser().parse_args(argv)
    try:
        if args.operation in ('prepare','status','watch'):
            require(args.session_file is not None, '--session-file with original installed identity required')
            require(re.fullmatch('[A-Za-z0-9_.:-]{1,96}',args.request_id), 'Invalid original request ID')
        if args.operation == 'watch':
            require(1 <= args.duration_seconds <= 300 and 250 <= args.interval_ms <= 10000
                    and 1 <= args.max_samples <= 128, 'Watch duration/interval/sample bound')
        initial = verify_manifest(_manifest)
        local = dict(operation=args.operation, selected_effect_verified=False, native_calls=0,
            requests_published=0,memory_written=False,saves_written=0,automatic_command_retry=False,
            cli_manifest_sha256=initial['manifest_sha256'])
        if args.operation == 'check':
            guard(initial,_manifest)
            emit(dict(local,status='verified',source_pins=len(initial['source_pins']),
                      game_process_accessed=False),output)
            return 0
        module = _loader(initial)
        guard(initial,_manifest)
        checked_module(module,initial)
        if args.operation == 'catalog':
            value = module.candidate_catalog()
            guard(initial,_manifest)
            emit(dict(local,status='catalog',catalog=value,game_process_accessed=False),output)
            return 0
        session_raw = bounded_read(args.session_file,32768)
        session = decode(session_raw)
        require('identity_purpose' not in session and 'native_session_installed' not in session,
                'A current-query nonce is not an installed session')
        identity = module.validate_identity(session['identity'])
        observer = module.RelationRequestObserver(identity,store=args.store,allow_tag_host=args.allow_tag_host)
        module.installed_session(observer.backend,identity,ready=args.operation == 'prepare')
        guard(initial,_manifest)
        if args.operation == 'prepare':
            actions = {row['action'] for row in module.candidate_catalog()['profiles']}
            require(args.action in actions, 'No candidate/frozen observation profile for this action')
            guard(initial,_manifest)
            value = observer.prepare(dict(request_id=args.request_id,action=args.action,actor=args.actor,target=args.target))
            require(value['request_id'] == args.request_id, 'Baseline result belongs to another request')
            require(bounded_read(args.session_file,32768) == session_raw, 'Session file changed during preparation')
            guard(initial,_manifest)
            emit(dict(local,status='baseline_recorded',baseline_result=value),output)
            return 0
        deadline = _clock()+(args.duration_seconds if args.operation == 'watch' else 0)
        limit = args.max_samples if args.operation == 'watch' else 1
        previous = None
        for sample in range(1,limit+1):
            guard(initial,_manifest)
            require(bounded_read(args.session_file,32768) == session_raw, 'Session file changed before observation')
            value = observer.observe(args.request_id)
            require(value['request_id'] == value['command']['request_id'] == args.request_id
                    and value['identity'] == identity,
                    'Observer returned another request or session')
            guard(initial,_manifest)
            require(bounded_read(args.session_file,32768) == session_raw, 'Session file changed during observation')
            code = result_code(value)
            summary = compact(value)
            key = json.dumps({k:v for k,v in summary.items() if k != 'record'},sort_keys=True)
            exhausted = sample == limit or _clock() >= deadline
            if key != previous or exhausted or code == 0:
                emitted = summary if args.compact else value
                emit(dict(emitted,operation=args.operation,sample=sample,
                    cli_manifest_sha256=initial['manifest_sha256'],automatic_command_retry=False,
                    watch_bound_reached=(args.operation == 'watch' and exhausted and code != 0)),output)
                previous = key
            if args.operation == 'status' or code == 0 or exhausted:
                return code
            _sleep(min(args.interval_ms/1000,max(0,deadline-_clock())))
        raise RuntimeError('Watch exhausted without a result')
    except ERRORS as exc:
        emit(dict(operation=args.operation,status='unknown',selected_effect_verified=False,
            completion_state='evidence_insufficient',native_calls=0,requests_published=0,
            saves_written=0,memory_written=False,automatic_command_retry=False,
            error=dict(type=type(exc).__name__,message=str(exc))),output)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
