"""Native-origin semantic projection; source authentication belongs to real_capture.py.
Direct use proves only a supplied trace model, never an actual Host origin.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT = HERE
PINS = {'protocol.py': 'c85b1c216a86a76c4cc997aff8cd028049e1d94a09c364978f06dda9fb12ceb4',
        'model.py': '96f0205740025c51f06b90d86c75b96432e338bec0b0d5fe6729b8a9848f18d1'}
MAX_INPUT = 512 * 1024
MAX_RECORDS = 192
MAX_LINE = 8192


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def bounded(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'Read budget')
    return raw


def load_fixed():
    modules = []
    old = sys.modules.get('protocol')
    try:
        for name in ('protocol.py', 'model.py'):
            raw = bounded(CONTRACT / name, 32 * 1024)
            require(hashlib.sha256(raw).hexdigest() == PINS[name], 'Sealed model source changed')
            module = types.ModuleType('_spy_projection_' + name[:-3])
            module.__file__ = str(CONTRACT / name)
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)
            modules.append(module)
            if name == 'protocol.py':
                sys.modules['protocol'] = module
    finally:
        if old is None:
            sys.modules.pop('protocol', None)
        else:
            sys.modules['protocol'] = old
    return modules


p, model = load_fixed()
STAGES = {1: 'lifecycle', 2: 'family_preview', 3: 'owned_command'}
STEPS = {0: 'none', 1: 'factory', 2: 'clone', 3: 'destroy_clone', 4: 'initialize',
         5: 'full_preview', 6: 'wrap_owned', 7: 'destroy_original', 8: 'command_gate', 9: 'destroy_command'}
KINDS = {0: 'stage_begin', 1: 'step_begin', 2: 'step_return', 3: 'case_complete', 4: 'stage_complete', 5: 'fault'}
FIELD_U64 = {'vtable', 'actor', 'controller', 'target'}
FIELD_U32 = {'marker', 'state', 'identifier'}
FIELD_I32 = {'primary_date', 'secondary_date', 'envoy'}
FIELD_U8 = {'value', 'flag39'}
FIELD_KEYS = FIELD_U64 | FIELD_U32 | FIELD_I32 | FIELD_U8
STAMP_PTRS = {'game', 'database', 'countries', 'actor_country', 'target_country', 'server', 'pause_manager'}
STAMP_KEYS = STAMP_PTRS | {'actor', 'target', 'player', 'date'}
CORE_BOOLS = {'call_entered', 'call_returned', 'allowed_observed', 'allowed',
              'original_destroyed', 'clone_destroyed', 'command_destroyed', 'mock_resolver', 'send_supported'}
CORE_INTS = {'kind', 'stage', 'step', 'family', 'token', 'original_id', 'clone_id', 'command_id', 'reason', 'exception_code'}
CORE_KEYS = CORE_BOOLS | CORE_INTS | {'original_fields', 'clone_fields', 'stamp'}
RESULT_INTS = {'stage', 'reason', 'step', 'family', 'cases_complete', 'exception_code', 'reads', 'bytes_read'}
RESULT_BOOLS = {'completed', 'audit_complete', 'freeze_session', 'ownership_uncertain',
                'retry_allowed', 'send_supported', 'runtime_verified', 'production_ready'}
RESULT_KEYS = RESULT_INTS | RESULT_BOOLS | {'allowed_observed', 'allowed'}
ENVELOPE_KEYS = (model.COMMON - {'event', 'ordinal'}) | {'image_base'}
MISSING_HOST = ('exact process creation and session/build identity', 'owner thread and frame capture',
                'monotonic callback uptime', 'durable stage claim and wire bytes',
                'durable per-callback logger result', 'independent pre/post-stage healthy frames',
                'complete Core::run Result after final logger return',
                'country array count and target-overlord profile guard evidence')


def integer(v, low=0, high=2**64-1):
    return type(v) is int and low <= v <= high


def exact(a, b, reason):
    require(model.same(a, b), reason)


def zeros():
    return dict.fromkeys(FIELD_KEYS, 0)


def typed_fields(f):
    require(type(f) is dict and set(f) == FIELD_KEYS, 'Exact raw Fields')
    for keys, low, high in ((FIELD_U64, 0, 2**64-1), (FIELD_U32, 0, 2**32-1),
                            (FIELD_I32, -2**31, 2**31-1), (FIELD_U8, 0, 255)):
        require(all(integer(f[k], low, high) for k in keys), 'Raw field scalar width/type')


def typed_core(e):
    require(type(e) is dict and set(e) == CORE_KEYS, 'Exact private Event shape')
    require(all(type(e[k]) is bool for k in CORE_BOOLS), 'Private Event bool type')
    require(all(integer(e[k], 0, 2**32-1) for k in CORE_INTS), 'Private Event uint32 type')
    require(e['kind'] in KINDS and e['stage'] in STAGES and e['step'] in STEPS and e['family'] < 5,
            'Private Event enum/range')
    require(e['mock_resolver'] is False and e['send_supported'] is False,
            'Native-origin flag required; authentication remains outside this semantic reducer')
    typed_fields(e['original_fields'])
    typed_fields(e['clone_fields'])
    stamp = e['stamp']
    require(type(stamp) is dict and set(stamp) == STAMP_KEYS, 'Exact Stamp')
    require(all(integer(stamp[k]) for k in STAMP_KEYS - {'date'})
            and integer(stamp['date'], -2**31, 2**31-1), 'Stamp exact scalar types')


class Projection:
    """Supplied metadata is not an attestation; only the capture verifier binds actual source files."""
    def __init__(self, identity):
        self.model = model.Session(identity)
        self.identity = deepcopy(identity)
        self.output = []
        self.provenance = []
        self.stage = None
        self.stage_count = 0
        self.family = 0
        self.step_index = 0
        self.case_active = False
        self.wait_return = False
        self.wait_result = None
        self.stamp = None
        self.image_base = None
        self.last_core = None
        self.next_id = 1
        self.source_index = 0
        self.cached = None
        self.closed = False
        self.last_uptime = 0

    def envelope(self, value):
        require(type(value) is dict and set(value) == ENVELOPE_KEYS, 'Missing/extraneous host envelope evidence')
        exact({k: value[k] for k in model.SESSION_FIELDS}, self.identity, 'Envelope process/session/world differs')
        require(integer(value['image_base'], 0x10000, 0x7fffffffffff) and value['image_base'] % 8 == 0,
                'Envelope image base')
        if self.image_base is None:
            self.image_base = value['image_base']
        exact(value['image_base'], self.image_base, 'Changed image base')
        require(integer(value['uptime_ms']) and integer(value['frame'], 1), 'Envelope clock/frame exact')
        require(value['uptime_ms'] >= self.last_uptime and value['frame'] == self.model.frame,
                'Envelope clock regressed or advanced without explicit health')
        self.last_uptime = value['uptime_ms']
        require(value['paused'] is True and value['durable'] is True and value['no_send'] is True,
                'Host pause/durability/no-send assertions missing')
        exact(value['player_handle'], model.FRA, 'Envelope actor identity')
        exact(value['target_handle'], model.ENG, 'Envelope target identity')
        return {k: deepcopy(v) for k, v in value.items() if k != 'image_base'}

    def emit(self, envelope, kind, fields, derived):
        event = dict(envelope, event=kind, ordinal=len(self.output)+1, **fields)
        raw = model.canonical(event).encode('ascii') + b'\n'
        require(len(raw) <= model.MAX_LINE and len(self.output) < model.MAX_EVENTS, 'Model output budget')
        self.model.feed(event)
        self.output.append(raw)
        self.provenance.append({'ordinal': event['ordinal'], 'source_record': self.source_index,
                                'mapping': derived})

    def host(self, e):
        require(type(e) is dict and e.get('event') in ('health', 'claim'), 'Only explicit health/claim host records')
        require(self.stage is None and self.wait_result is None, 'Host metadata interrupted Core::run')
        expected = model.COMMON | model.EXTRA[e['event']]
        require(set(e) == expected - {'ordinal'}, 'Exact host event fields; no supplied output ordinal')
        require(integer(e['uptime_ms'], self.last_uptime), 'Host clock regressed after callback/Result')
        self.last_uptime = e['uptime_ms']
        envelope = {k: e[k] for k in model.COMMON - {'event', 'ordinal'}}
        extra = {k: e[k] for k in model.EXTRA[e['event']]}
        self.emit(envelope, e['event'], extra, 'explicit_unverified_host_fixture')

    def validate_stamp(self, e):
        stamp = e['stamp']
        require(all(integer(stamp[k], 0x10000, 0x7fffffffffff) and stamp[k] % 8 == 0 for k in STAMP_PTRS),
                'Selected root pointers')
        require(stamp['actor_country'] != stamp['target_country'], 'Root country alias')
        exact(stamp['game'], int(self.identity['world_cookie'], 16), 'Core world differs from host')
        exact(stamp['actor'], int(model.FRA, 16), 'Core full actor identity')
        exact(stamp['player'], int(model.FRA, 16), 'Core full player identity')
        exact(stamp['target'], int(model.ENG, 16), 'Core full target identity')
        exact(stamp['date'], self.identity['raw_date'], 'Core date differs')
        if self.stamp is None:
            self.stamp = deepcopy(stamp)
        exact(stamp, self.stamp, 'Changed selected root stamp')

    def fields(self, f):
        typed_fields(f)
        exact(f['marker'], 0x165, 'Action marker')
        expected_rva = model.FAMILY_ROWS[self.family][2]
        exact(f['vtable'], self.image_base + int(expected_rva, 16), 'Family vtable')
        require(f['value'] in (0, 1) and f['flag39'] in (0, 1), 'Action boolean byte is not canonical')
        return dict(size=64, vtable_rva=expected_rva, actor_handle=f"0x{f['actor']:016x}",
                    controller_handle=f"0x{f['controller']:016x}", target_handle=f"0x{f['target']:016x}",
                    date_primary=f['primary_date'], date_secondary=f['secondary_date'], envoy=f['envoy'],
                    state=f['state'], value=f['value'] == 1, flag39=f['flag39'] == 1, identifier=f['identifier'])

    def new_id(self, value):
        exact(value, self.next_id, 'Core object ordinal allocation differs')
        self.next_id += 1
        require(self.next_id <= 129, 'Core object ID budget')

    def binding(self):
        return dict(sequence=self.stage_count+1, stage=self.stage, family=p.FAMILIES[self.family])

    def cache_check(self, e, changes=None):
        desired = deepcopy(self.cached)
        desired.update(changes or {})
        for key, value in desired.items():
            exact(e[key], value, 'Private retained field/ID/destroy flag differs: '+key)
        self.cached = desired

    def result_for(self, step, e):
        c = self.cached
        changes = {}
        if step == 'factory':
            self.new_id(e['original_id'])
            result = dict(object_id=e['original_id'], fields=self.fields(e['original_fields']))
            changes.update(original_id=e['original_id'], original_fields=e['original_fields'])
        elif step == 'initialize':
            result = dict(object_id=c['original_id'], fields=self.fields(e['original_fields']))
            changes['original_fields'] = e['original_fields']
        elif step == 'clone':
            self.new_id(e['clone_id'])
            result = dict(object_id=e['clone_id'], source_id=c['original_id'], fields=self.fields(e['clone_fields']),
                          source_fields=self.fields(e['original_fields']))
            changes['clone_id'] = e['clone_id']
            changes['clone_fields'] = e['clone_fields']
        elif step == 'wrap_owned':
            self.new_id(e['command_id'])
            self.new_id(e['clone_id'])
            result = dict(source_id=c['original_id'], source_fields=self.fields(e['original_fields']),
                          command_id=e['command_id'], clone_id=e['clone_id'], clone_fields=self.fields(e['clone_fields']),
                          command_size=88, command_vtable_rva='0x1c814b0')
            changes.update(command_id=e['command_id'], clone_id=e['clone_id'], clone_fields=e['clone_fields'])
        elif step in ('full_preview', 'command_gate'):
            result = dict(object_id=c['original_id'] if step == 'full_preview' else c['command_id'],
                          returned=True, allowed=e['allowed'], route='action_vtable_0x88' if step == 'full_preview' else 'command_vtable_0x40',
                          function_rva=model.FAMILY_ROWS[self.family][3] if step == 'full_preview' else '0x4e8630')
            if step == 'full_preview':
                result.update(string_output=None, mode=False)
        else:
            ident = {'destroy_original': c['original_id'], 'destroy_clone': c['clone_id'], 'destroy_command': c['command_id']}[step]
            result = dict(object_id=ident, returned=True)
            changes[step.replace('destroy_', '')+'_destroyed'] = True
            if step == 'destroy_command':
                result['owned_clone_id'] = c['clone_id']
                changes['clone_destroyed'] = True
        self.cache_check(e, changes)
        return result

    def core(self, envelope, e):
        env = self.envelope(envelope)
        typed_core(e)
        if KINDS[e['kind']] == 'fault' or e['reason'] != 0 or e['exception_code'] != 0:
            raise ValueError('Terminal core diagnostic; no normal projection or inferred cleanup')
        require(self.wait_result is None, 'Core callback after final callback but before Result')
        self.validate_stamp(e)
        kind = KINDS[e['kind']]
        stage = STAGES[e['stage']]
        step = STEPS[e['step']]
        if kind == 'stage_begin':
            require(self.stage is None and self.stage_count < 3 and stage == p.STAGES[self.stage_count], 'Core stage order')
            require(self.model.pending is not None and self.model.pending['stage'] == stage, 'Missing explicit durable stage claim')
            exact({k: e[k] for k in CORE_INTS}, dict(kind=0, stage=self.stage_count+1, step=0, family=0, token=0,
                  original_id=0, clone_id=0, command_id=0, reason=0, exception_code=0), 'Stage initial scalar defaults')
            require(all(e[k] is False for k in CORE_BOOLS - {'mock_resolver'}), 'Stage initial flag defaults')
            exact(e['original_fields'], zeros(), 'Stage initial original fields')
            exact(e['clone_fields'], zeros(), 'Stage initial clone fields')
            self.stage = stage
            self.family = 0
            self.last_core = deepcopy(e)
            return
        require(self.stage == stage, 'Wrong active core stage')
        if kind == 'stage_complete':
            require(self.family == 5 and not self.case_active and not self.wait_return, 'Incomplete core matrix')
            expected = dict(self.last_core, kind=4)
            exact(e, expected, 'Stage completion retained snapshot differs')
            self.wait_result = (env, deepcopy(e), self.source_index)
            return
        require(self.family < 5 and e['family'] == self.family and e['token'] == model.FAMILY_ROWS[self.family][1],
                'Family index/token mismatch')
        if kind == 'step_begin':
            if not self.case_active:
                require(step == 'factory', 'Missing first factory step')
                self.cached = dict(original_id=0, clone_id=0, command_id=0,
                                   original_fields=zeros(), clone_fields=zeros(),
                                   original_destroyed=False, clone_destroyed=False, command_destroyed=False)
                self.cache_check(e)
                self.emit(env, 'case_begin', self.binding(), 'derived_factory_case_boundary')
                self.case_active = True
                self.step_index = 0
            require(not self.wait_return and step == model.STEPS[self.stage][self.step_index], 'Core step order/reentrancy')
            require(not e['call_entered'] and not e['call_returned'] and not e['allowed_observed'] and not e['allowed'],
                    'Step begin is an intent, not proof of call or return')
            self.cache_check(e)
            self.emit(env, 'step_begin', dict(self.binding(), step=step), 'durable_core_step_intent')
            self.wait_return = True
        elif kind == 'step_return':
            require(self.case_active and self.wait_return and step == model.STEPS[self.stage][self.step_index], 'Unpaired core return')
            exact(e['call_entered'], step != 'initialize', 'Exact call-entered semantics')
            exact(e['call_returned'], step != 'initialize', 'Exact normal-return semantics')
            exact(e['allowed_observed'], step in ('full_preview', 'command_gate'), 'Exact allowed observation')
            if not e['allowed_observed']:
                exact(e['allowed'], False, 'Non-gate cannot report legality')
            result = self.result_for(step, e)
            self.emit(env, 'step_complete', dict(self.binding(), step=step, exception_code=0, result=result),
                      'owned_initialization_completion' if step == 'initialize' else 'known_normal_core_return')
            static_fields = {
                'factory': ['result.fields.size'], 'initialize': ['result.fields.size'],
                'clone': ['result.fields.size', 'result.source_fields.size'],
                'wrap_owned': ['result.command_size', 'result.command_vtable_rva',
                               'result.source_fields.size', 'result.clone_fields.size'],
                'full_preview': ['result.route', 'result.function_rva', 'result.string_output', 'result.mode'],
                'command_gate': ['result.route', 'result.function_rva']}.get(step, [])
            if static_fields:
                self.provenance[-1]['static_core_contract_fields'] = static_fields
            self.step_index += 1
            self.wait_return = False
        elif kind == 'case_complete':
            require(self.case_active and not self.wait_return and self.step_index == len(model.STEPS[self.stage]), 'Incomplete core case')
            exact(e, dict(self.last_core, kind=3), 'Case completion retained snapshot differs')
            self.emit(env, 'case_complete', dict(self.binding(), owned_count=0), 'checked_released_object_graph')
            self.family += 1
            self.case_active = False
        else:
            raise ValueError('Unexpected core callback')
        self.last_core = deepcopy(e)

    def run_result(self, envelope, r):
        env = self.envelope(envelope)
        require(type(r) is dict and set(r) == RESULT_KEYS, 'Complete Core::run Result is required')
        require(all(integer(r[k], 0, 2**32-1) for k in RESULT_INTS - {'bytes_read'})
                and integer(r['bytes_read'], 0, 1048576), 'Result exact scalar widths')
        require(all(type(r[k]) is bool for k in RESULT_BOOLS), 'Result exact booleans')
        for name in ('allowed_observed', 'allowed'):
            require(type(r[name]) is list and len(r[name]) == 5 and all(type(x) is bool for x in r[name]), 'Result exact gate vector')
        require(self.wait_result is not None, 'No paired final core callback')
        callback_env, _, source = self.wait_result
        exact({k: v for k, v in env.items() if k != 'uptime_ms'},
              {k: v for k, v in callback_env.items() if k != 'uptime_ms'},
              'Result must belong to same host callback identity/frame')
        require(env['uptime_ms'] >= callback_env['uptime_ms'], 'Result clock precedes final callback')
        require(r['completed'] and r['audit_complete'] and not r['freeze_session'] and not r['ownership_uncertain'],
                'Final logger/RunStage result did not complete normally')
        require(all(r[k] is False for k in ('retry_allowed', 'send_supported', 'runtime_verified', 'production_ready')), 'Result promoted permissions')
        require(r['stage'] == self.stage_count+1 and r['reason'] == 0 and r['exception_code'] == 0
                and r['family'] == 4 and r['cases_complete'] == 5 and 1 <= r['reads'] <= 8192
                and r['reads'] <= r['bytes_read'] <= r['reads']*64
                and r['step'] == (9 if self.stage == 'owned_command' else 7), 'Result stage completion differs')
        observed = [self.stage != 'lifecycle'] * 5
        allowed = [False] * 5 if self.stage == 'lifecycle' else [self.model.results[self.stage][name] for name in p.FAMILIES]
        exact(r['allowed_observed'], observed, 'Result observed vector differs from callbacks')
        exact(r['allowed'], allowed, 'Result bool vector differs from callbacks')
        self.emit(callback_env, 'stage_complete', dict(sequence=self.stage_count+1, stage=self.stage, case_count=5, owned_count=0),
                  'final_callback_and_successful_run_result')
        self.provenance[-1]['core_final_callback_source'] = source
        self.stage_count += 1
        self.stage = None
        self.wait_result = None

    def feed(self, record):
        require(not self.closed, 'Projection stopped; no retry/resume')
        try:
            require(self.source_index < MAX_RECORDS, 'Input record count budget')
            self.source_index += 1
            require(type(record) is dict and record.get('origin') == 'source_bound_native', 'Explicit native source profile required')
            kind = record.get('kind')
            if kind == 'host':
                require(set(record) == {'origin', 'kind', 'event'}, 'Exact host wrapper')
                self.host(record['event'])
            elif kind == 'core':
                require(set(record) == {'origin', 'kind', 'envelope', 'event'}, 'Exact core wrapper')
                self.core(record['envelope'], record['event'])
            elif kind == 'result':
                require(set(record) == {'origin', 'kind', 'envelope', 'result'}, 'Exact Result wrapper')
                self.run_result(record['envelope'], record['result'])
            else:
                raise ValueError('Missing core/host/Result record')
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            self.closed = True
            raise ValueError(str(exc)) from exc

    def finish(self):
        if self.closed or self.stage is not None or self.wait_result is not None:
            self.closed = True
            raise ValueError('Incomplete or terminal projection')
        self.closed = True  # EOF is final even if subsequent serialization/budget validation fails.
        result = self.model.finish()
        raw = b''.join(self.output)
        require(len(raw) <= model.MAX_LOG, 'Projected log byte budget')
        result.update(input_records=self.source_index, output_events=len(self.output), bytes=len(raw),
                      sha256=hashlib.sha256(raw).hexdigest(), projection_implemented=True,
                      actual_core_log_authenticated=False, host_evidence_authenticated=False,
                      untrusted_caller_envelopes=True, raw_core_only_supported=False,
                      required_missing_host_contract=list(MISSING_HOST), provenance=deepcopy(self.provenance))
        self.closed = True
        return raw, result


def project(records, identity):
    require(type(records) is list and 0 < len(records) <= MAX_RECORDS, 'Bounded explicit record list')
    session = Projection(identity)
    for record in records:
        session.feed(record)
    return session.finish()


def read_records(path):
    raw = bounded(path, MAX_INPUT)
    require(raw and raw.endswith(b'\n'), 'Complete raw projection lines')
    lines = raw.splitlines(keepends=True)
    require(len(lines) <= MAX_RECORDS, 'Raw line count budget')

    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'Duplicate JSON key')
            out[key] = value
        return out

    result = []
    for line in lines:
        require(len(line) <= MAX_LINE, 'Raw line byte budget')
        result.append(json.loads(line, object_pairs_hook=unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON'))))
    return result


def availability():
    return dict(offline_native_trace_projection=True, authenticated_native_log_projection=False,
                raw_event_only_projection=False, missing_host_contract=list(MISSING_HOST),
                native_host_implemented=False, native_call_authorized=False, send_supported=False,
                runtime_verified=False, production_ready=False)
