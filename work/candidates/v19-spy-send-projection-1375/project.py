"""Strict isolated-mock Event projection. Actual Host captures are unsupported."""
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODEL = ROOT/'work/candidates/v19-spy-send-plan-r2-1375/model.py'
MODEL_SHA = '8066d08ed1a077eebefc537d8ecac02badd8fd46cbbf41543933e3615697c86d'
assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == MODEL_SHA
spec = importlib.util.spec_from_file_location('_sealed_send_model_r2_projection', MODEL)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
FAMILIES = model.FAMILIES
TOKENS = (0x337c, 0x2ddd, 0x2ddf, 0x337b, 0x33bf)
VTS = (0x1c7c4a8, 0x1c7cfd8, 0x1c7c9e8, 0x1c7c378, 0x1c7c5d8)
PREVIEWS = (0x582730, 0x57e900, 0x585020, 0x580260, 0x581450)
CALLS = {3: 0x35d210, 6: 0x4e9930, 7: 0x4e8630, 8: 0x129450, 9: 0x4e7470, 10: 0x14ca210}
FRA, ENG = 0x0100007a00415246, 0x0100002e00474e45
UINT = 2**64-1
FIELD_U = 'vtable marker actor controller target state value flag39 identifier'.split()
FIELD_I = 'primary_date secondary_date envoy'.split()
ITEM_U = 'ordinal family token original_id clone_id command_id owner_frame step outcome'.split()
ITEM_B = ('claimed call_entered call_returned preview_observed preview_allowed gate_observed gate_allowed '
          'original_destroyed command_destroyed clone_destroyed submit_entered submit_returned '
          'submit_value_observed submit_value slot_observed slot_consumed has_local_original '
          'has_local_command has_local_clone current').split()
STAMP_PTR = 'game database countries actor_country target_country server pause_manager holder context transport'.split()
STAMP_U = 'actor target player actor_overlord target_overlord effective_player country_count context_ready55 context_ready80d'.split()
EVENT_U = 'kind operation request_sequence completed exception_code frame uptime_ms expires_uptime_ms reason state'.split()
EVENT_B = 'mock_resolver production_ready strict_sp_verified epoch_verified effect_verified'.split()
RESULT_U = 'state reason completed exception_code read_calls bytes_read'.split()
RESULT_B = ('accepted_call audit_complete freeze_session ownership_uncertain retry_allowed runtime_verified '
            'production_ready effect_verified strict_sp_verified epoch_verified').split()


def require(ok, why):
    if not ok:
        raise ValueError(why)


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'exact fields '+str(keys))


def integer(value, lo=0, hi=UINT):
    require(type(value) is int and lo <= value <= hi, 'integer range/type')
    return value


def boolean(value):
    require(type(value) is bool, 'strict boolean')
    return value


def same(a, b):
    require(type(a) is type(b), 'typed equality')
    if type(a) is dict:
        require(set(a) == set(b), 'typed dictionary keys')
        for key in a: same(a[key], b[key])
    elif type(a) is list:
        require(len(a) == len(b), 'typed list length')
        for left, right in zip(a, b): same(left, right)
    else:
        require(type(a) in (str, int, bool, type(None)) and a == b, 'typed scalar equality')


def digest(value, n=64):
    require(type(value) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}', value) and int(value, 16), 'nonzero hex')


def pointer(value):
    integer(value, 0x10000, 0x7fffffffffff)
    require(value % 8 == 0, 'pointer alignment')


def identity(d):
    exact(d, 'pid creation_filetime session dll_sha256 manifest_sha256'.split())
    integer(d['pid'], 1, 2**32-1); integer(d['creation_filetime'], 1)
    for key, n in (('session', 32), ('dll_sha256', 64), ('manifest_sha256', 64)):
        digest(d[key], n)
    require(d['dll_sha256'] != model.OLD_DLL, 'v18 DLL cannot send')


def stamp(d):
    exact(d, STAMP_PTR+STAMP_U+['date', 'native_speed_index'])
    for k in STAMP_PTR: pointer(d[k])
    for k in STAMP_U: integer(d[k])
    integer(d['date'], 1, 2**31-1); integer(d['native_speed_index'], 0, 4)
    integer(d['country_count'], 123, 4096)
    for k in ('context_ready55', 'context_ready80d'): integer(d[k], 0, 255)
    require(d['context_ready55'] or d['context_ready80d'], 'readiness byte OR')
    for k in ('actor', 'player', 'effective_player'): require(d[k] == FRA, 'FRA full handle')
    require(d['target'] == ENG and d['actor_country'] != d['target_country'], 'ENG direction')
    require(d['actor_overlord'] < 2**56 and d['target_overlord'] < 2**56, 'independent fixed pair')


def fields(d):
    exact(d, FIELD_U+FIELD_I)
    for k in FIELD_U: integer(d[k])
    for k in FIELD_I: integer(d[k], -2**31, 2**31-1)
    for k in ('marker', 'state', 'identifier'): integer(d[k], 0, 2**32-1)
    for k in ('value', 'flag39'): integer(d[k], 0, 255)


def item(d):
    exact(d, ITEM_U+ITEM_B+['original_fields', 'clone_fields'])
    for k in ITEM_U: integer(d[k])
    for k in ITEM_B: boolean(d[k])
    for k in ('original_fields', 'clone_fields'): fields(d[k])
    integer(d['ordinal'], 0, 5); integer(d['family'], 0, 4)
    integer(d['step'], 0, 10); integer(d['outcome'], 0, 5)
    for k in ('token', 'original_id', 'command_id', 'clone_id'): integer(d[k], 0, 2**32-1)


def typed_result(d):
    """Retain terminal diagnostics without converting them to authority."""
    exact(d, ['result', 'completed_outcomes']); r = d['result']
    exact(r, RESULT_U+RESULT_B+['current_item'])
    for key in RESULT_U: integer(r[key])
    for key in RESULT_B: boolean(r[key])
    integer(r['state'], 0, 4); integer(r['reason'], 0, 18)
    integer(r['completed'], 0, 5); integer(r['exception_code'], 0, 2**32-1)
    integer(r['read_calls'], 0, 8192); integer(r['bytes_read'], r['read_calls'], 1048576)
    item(r['current_item'])
    require(type(d['completed_outcomes']) is list and len(d['completed_outcomes']) == 5, 'five outcomes')
    for value in d['completed_outcomes']: integer(value, 0, 5)
    for key in ('retry_allowed', 'runtime_verified', 'production_ready', 'effect_verified', 'strict_sp_verified', 'epoch_verified'):
        require(r[key] is False, 'terminal diagnostic cannot grant permission')
    return deepcopy(d)


def zero_item():
    return dict(**{k: 0 for k in ITEM_U}, **{k: False for k in ITEM_B},
                original_fields={k: 0 for k in FIELD_U+FIELD_I}, clone_fields={k: 0 for k in FIELD_U+FIELD_I})


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 4*1024*1024 and raw.endswith(b'\n'), 'bounded complete capture')
    def pairs(items):
        d = {}
        for k, v in items:
            require(k not in d, 'duplicate JSON key'); d[k] = v
        return d
    lines = raw.splitlines()
    require(len(lines) <= 4096, 'file row budget')
    rows = []
    for line in lines:
        require(0 < len(line) <= 8192, 'line budget')
        rows.append(json.loads(line, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite'))))
    return rows


class Projection:
    def __init__(self):
        self.batch = None; self.binding = None; self.header = None
        self.locked = None; self.op = None; self.phase = 'header'
        self.current = zero_item(); self.claimed = None; self.completed = 0
        self.state = 0; self.next_id = 0; self.last_frame = 3; self.now = 0
        self.pending_step = None; self.next_step = None; self.outcomes = [0]*5
        self.fault = None; self.raw_current = None; self.end = False; self.events = 0
        self.entry = None; self.intervals = []

    def guard_time(self, now):
        integer(now); require(now >= self.now, 'clock rollback'); self.now = now

    def bind(self, d):
        identity(d['identity']); stamp(d['stamp']); same(d['identity'], self.header['identity'])
        if self.locked is not None: same(d['stamp'], self.locked)
        else:
            self.locked = deepcopy(d['stamp'])
            self.binding = {k: d['stamp'][k] for k in model.COOKIES if k != 'world'}
            self.binding['world'] = d['stamp']['game']
            self.binding.update(pid=d['identity']['pid'], creation=f"{d['identity']['creation_filetime']:016x}",
                                thread=self.header['thread'], date=d['stamp']['date'],
                                session=d['identity']['session'], dll_sha256=d['identity']['dll_sha256'],
                                manifest_sha256=d['identity']['manifest_sha256'], actor_handle=f'{FRA:016x}',
                                target_handle=f'{ENG:016x}', player_handle=f'{FRA:016x}')
            self.batch = model.Batch(self.binding)
            for n in range(1, 4):
                self.batch.phase(n, self.binding, n, 0, core_passed=True, later_clean_health=True)

    def event(self, name, at=None, **kwargs):
        self.batch.event(name, self.binding, self.op['frame'], self.now if at is None else at, **kwargs)

    def expected_fields(self, initialized):
        f = {k: 0 for k in FIELD_U+FIELD_I}
        f.update(vtable=self.header['image_base']+VTS[self.current['family']], marker=0x165,
                 actor=FRA if initialized else 0x2d2d2d, controller=FRA if initialized else 0x2d2d2d,
                 target=ENG if initialized else 0x2d2d2d, primary_date=self.locked['date'] if initialized else 43808760,
                 secondary_date=self.locked['date'] if initialized else 43808760, envoy=-1, value=1)
        return f

    def consume(self, kind, d):
        if kind == 'scenario_begin':
            require(self.phase == 'header', 'one header')
            exact(d, 'identity image_base thread expires preflight_assertions initial_sha256'.split())
            identity(d['identity']); pointer(d['image_base']); integer(d['thread'], 1, 2**32-1)
            integer(d['expires'], 1); digest(d['initial_sha256'])
            same(d['preflight_assertions'], [True]*3)
            self.header = deepcopy(d); self.phase = 'idle'; return
        require(self.header is not None and not self.end, 'no before header/after end')
        if kind == 'operation_begin':
            require(self.phase == 'idle', 'operation overlap or missing result')
            exact(d, ['operation', 'frame', 'uptime_ms']); integer(d['operation'], 1, 3)
            integer(d['frame'], self.last_frame+1); self.guard_time(d['uptime_ms'])
            wanted = 1 if self.state == 0 else 2 if self.state == 1 else 3 if self.state == 2 else None
            require(d['operation'] == wanted, 'operation/state order')
            self.op = deepcopy(d); self.last_frame = d['frame']; self.phase = 'inside'
            self.claimed = None; self.next_step = None; self.pending_step = None
            if wanted == 2: require(self.now < self.header['expires'], 'new work after TTL')
            return
        if kind == 'scenario_end':
            require(self.phase == 'idle' and self.state == 3, 'incomplete/frozen capture')
            exact(d, 'frame uptime_ms final_sha256 abi_errors invalid_reads invalid_writes mock_only game_accessed'.split())
            integer(d['frame'], self.last_frame+1); self.guard_time(d['uptime_ms']); digest(d['final_sha256'])
            for k in ('abi_errors', 'invalid_reads', 'invalid_writes'): integer(d[k], 0, 0)
            require(d['mock_only'] is True and d['game_accessed'] is False, 'mock boundary')
            self.batch.observe_final(self.binding, d['frame'], self.now, d['final_sha256'])
            self.end = True; return
        require(self.phase == 'inside', 'outside invocation')
        if kind == 'claim':
            exact(d, 'sequence item_ordinal durable frame uptime_ms identity stamp'.split())
            integer(d['sequence'], 4, 4); same(d['frame'], self.op['frame']); self.guard_time(d['uptime_ms'])
            integer(d['item_ordinal'], 0, 5); boolean(d['durable'])
            require(self.claimed is None and self.op['operation'] in (1, 2), 'duplicate/unexpected claim')
            require(d['item_ordinal'] == (0 if self.op['operation'] == 1 else self.completed+1), 'claim item order')
            self.bind(d); require(d['durable'] is True, 'failed durable claim')
            require(self.now < self.header['expires'], 'claim expired')
            self.claimed = deepcopy(d); return
        if kind == 'mock_call_enter':
            exact(d, 'step rva frame uptime_ms context slot_nonnull'.split())
            integer(d['step'], 3, 10); integer(d['rva']); integer(d['context']); boolean(d['slot_nonnull'])
            same(d['frame'], self.op['frame']); self.guard_time(d['uptime_ms'])
            step = d['step']; require(step != 4 and self.entry is None, 'native entry once; initialize is not native')
            require(self.pending_step == ('dispatch' if step == 10 else step), 'entry requires matching intent')
            require(self.current['step'] == step, 'entry step')
            same(d['rva'], PREVIEWS[self.current['family']] if step == 5 else CALLS[step])
            if step not in (8, 9): require(self.now < self.header['expires'], 'actual mock work entry after expiry')
            if step == 10:
                same(d['context'], self.locked['context']); require(d['slot_nonnull'] is True, 'mock owned slot entry')
                self.event('submit_enter', guard_passed=True)
                self.current.update(has_local_command=False, has_local_clone=False, call_entered=True,
                                    submit_entered=True, outcome=4)
                self.pending_step = 'submit_return'
            else:
                same(d['context'], 0); require(d['slot_nonnull'] is False, 'only sender has context/slot')
            self.entry = deepcopy(d); return
        if kind == 'core_event':
            exact(d, ['durable', 'event']); boolean(d['durable'])
            e = d['event']; exact(e, EVENT_U+EVENT_B+['identity', 'stamp', 'item'])
            for k in EVENT_U: integer(e[k])
            for k in EVENT_B: boolean(e[k])
            item(e['item']); self.raw_current = deepcopy(e['item'])
            integer(e['kind'], 0, 8); integer(e['state'], 0, 4); integer(e['reason'], 0, 18)
            integer(e['exception_code'], 0, 2**32-1); self.bind(e)
            same(e['operation'], self.op['operation']); same(e['frame'], self.op['frame'])
            same(e['request_sequence'], 4); same(e['expires_uptime_ms'], self.header['expires'])
            self.guard_time(e['uptime_ms']); same(e['completed'], self.completed)
            require(e['mock_resolver'] is True, 'mock resolver only')
            require(all(e[k] is False for k in EVENT_B if k != 'mock_resolver'), 'no grants')
            self.events += 1; require(self.events <= 256, 'core budget')
            require(d['durable'] is True, 'failed durable log append')
            require(e['kind'] != 8 and e['reason'] == 0 and e['exception_code'] == 0, 'core fault freezes')
            same(e['state'], self.state)
            self.core(e)
            same(e['item'], self.current)
            return
        if kind == 'operation_result':
            exact(d, ['result', 'completed_outcomes']); r = d['result']
            exact(r, RESULT_U+RESULT_B+['current_item'])
            for k in RESULT_U: integer(r[k])
            for k in RESULT_B: boolean(r[k])
            item(r['current_item']); self.raw_current = deepcopy(r['current_item'])
            require(type(d['completed_outcomes']) is list and len(d['completed_outcomes']) == 5, 'five results')
            for n in d['completed_outcomes']: integer(n, 0, 5)
            same(d['completed_outcomes'], self.outcomes)
            require(self.pending_step is None and self.next_step == 'returned', 'missing core completion or call return')
            integer(r['read_calls'], 1, 8192); integer(r['bytes_read'], r['read_calls'], 1048576)
            for k in ('accepted_call', 'audit_complete'): require(r[k] is True, 'successful result')
            for k in RESULT_B:
                if k not in ('accepted_call', 'audit_complete'): require(r[k] is False, 'result no grants/freeze')
            same(r['reason'], 0); same(r['exception_code'], 0)
            if self.op['operation'] == 1: self.state = 1
            elif self.op['operation'] == 2: self.state = 2
            same(r['state'], self.state); same(r['completed'], self.completed); same(r['current_item'], self.current)
            self.phase = 'idle'; return
        raise ValueError('unknown record kind')

    def core(self, e):
        k, got = e['kind'], e['item']
        if k == 0:
            require(self.op['operation'] == 1 and self.claimed is not None and self.next_step is None, 'batch claim proof')
            self.current['step'] = 1
            r = {k: self.binding[k] for k in ('pid', 'creation', 'session', 'dll_sha256', 'manifest_sha256')}
            r.update(protocol=model.PROTOCOL, purpose=model.PURPOSE, game_sha256=model.GAME, sequence=4,
                     expires=self.header['expires'], operation='submit_fixed_spy5', actor='FRA', target='ENG',
                     profile='spy5_true_state0_envoy_minus1_v19')
            self.batch.claim(model.encode_request(r), self.binding, self.op['frame'], self.now,
                             exclusive_durable=True, initial_sha256=self.header['initial_sha256'])
            self.next_step = 'returned'; return
        if k == 1:
            require(self.op['operation'] == 2 and self.claimed is not None and self.next_step is None, 'item claim proof')
            self.current = zero_item(); self.current.update(ordinal=self.completed+1, family=self.completed,
                token=TOKENS[self.completed], owner_frame=self.op['frame'], outcome=1, step=2, current=True, claimed=True)
            self.event('item_claim', family=FAMILIES[self.completed], durable=True); self.next_step = 3; return
        if k == 2:
            step = got['step']; require(self.pending_step is None and step == self.next_step, 'step intent order')
            require(self.entry is None, 'previous native entry must return')
            if step not in (8, 9): require(self.now < self.header['expires'], 'intent work TTL')
            self.current.update(step=step, call_entered=False, call_returned=False)
            if step in (8, 9) and self.next_step != 10:
                if not self.current['preview_allowed']: self.current['outcome'] = 2
                elif not self.current['gate_allowed']: self.current['outcome'] = 3
            self.pending_step = step; return
        if k == 4:
            require(self.pending_step == 10, 'dispatch after submit intent')
            self.event('dispatch_intent', durable=True); self.pending_step = 'dispatch'; return
        if k == 3:
            step = got['step']; require(self.pending_step == (step if step != 10 else 'submit_return'), 'return requires exact intent/entry')
            require((self.entry is None) == (step == 4), 'explicit mock entry needed for each native return')
            if self.entry is not None:
                same(self.entry['step'], step)
                self.intervals.append({'step': step, 'family': self.current['family'], 'frame': self.op['frame'],
                                       'entered_uptime': self.entry['uptime_ms'], 'returned_observation_uptime': self.now})
            # The sealed abstract model has a single work event rather than
            # entry/return pairs. Feed its work guard the explicit mock entry
            # time, only after a normal return is known. Preserve both times
            # above; no timestamp is borrowed from a pre-call audit intent.
            started = self.now if self.entry is None else self.entry['uptime_ms']
            self.current.update(call_entered=step != 4, call_returned=step != 4)
            if step == 3:
                self.next_id += 1; self.current.update(original_id=self.next_id, has_local_original=True,
                                                     original_fields=self.expected_fields(False))
                self.event('factory', at=started, verified=True); self.next_step = 4
            elif step == 4:
                self.current['original_fields'] = self.expected_fields(True)
                self.event('initialize', verified=True); self.next_step = 5
            elif step == 5:
                self.current.update(preview_observed=True, preview_allowed=got['preview_allowed'])
                self.event('preview', at=started, allowed=got['preview_allowed']); self.next_step = 6 if got['preview_allowed'] else 8
            elif step == 6:
                self.current.update(command_id=self.next_id+1, clone_id=self.next_id+2, has_local_command=True,
                                    has_local_clone=True, clone_fields=self.expected_fields(True)); self.next_id += 2
                self.event('wrapper', at=started, verified=True); self.next_step = 7
            elif step == 7:
                self.current.update(gate_observed=True, gate_allowed=got['gate_allowed'])
                self.event('gate', at=started, allowed=got['gate_allowed']); self.next_step = 8 if got['gate_allowed'] else 9
            elif step == 9:
                self.current.update(command_destroyed=True, clone_destroyed=True, has_local_command=False, has_local_clone=False)
                self.event('destroy_command', returned=True); self.next_step = 8
            elif step == 8:
                self.current.update(original_destroyed=True, has_local_original=False)
                self.event('destroy_original', returned=True); self.next_step = 10 if self.current['gate_allowed'] else 'item_return'
            elif step == 10:
                self.current.update(submit_returned=True, submit_value_observed=True, slot_observed=True,
                                    submit_value=got['submit_value'], slot_consumed=got['slot_consumed'])
                self.event('submit_result', returned=True, accepted=got['submit_value'], consumed=got['slot_consumed'])
                self.next_step = 'item_return'
            else: raise ValueError('unsupported returned step')
            self.pending_step = None; self.entry = None; return
        if k == 5:
            require(self.pending_step is None and self.next_step == 'item_return', 'item completion')
            if self.current['outcome'] == 4: self.current['outcome'] = 5
            self.next_step = 'returned'; return
        if k == 6:
            require(self.op['operation'] == 3 and self.next_step is None, 'independently later health operation')
            self.event('health', healthy=True); self.next_step = 'returned'
            # Event itself precedes the core's increment/current=false writes.
            same(got, self.current)
            self.outcomes[self.completed] = self.current['outcome']; self.completed += 1
            self.state = 3 if self.completed == 5 else 1
            if self.completed == 5: self.next_step = 'batch_complete'
            self._after_health = deepcopy(self.current); self._after_health['current'] = False
            return
        if k == 7:
            require(self.op['operation'] == 3 and self.completed == 5 and self.next_step == 'batch_complete', 'last batch completion')
            same(got, self.current); self.next_step = 'returned'; return
        raise ValueError('unexpected core event')

    def replay(self, rows):
        error = None; scenario = None; final_result = None
        try:
            require(type(rows) is list and 1 <= len(rows) <= 512, 'scenario row budget')
            # Diagnostics after a semantic failure are retained as typed data.
            # They do not reset the model or authorize ownership/cleanup.
            for row in rows:
                exact(row, ['origin', 'scenario', 'ordinal', 'kind', 'data'])
                if row['kind'] == 'operation_result': final_result = typed_result(row['data'])
            for n, row in enumerate(rows, 1):
                exact(row, ['origin', 'scenario', 'ordinal', 'kind', 'data'])
                require(type(row['origin']) is str and row['origin'] == 'isolated_mock_cpp', 'actual captures unsupported')
                require(type(row['scenario']) is str and re.fullmatch('[a-z_]{1,64}', row['scenario']), 'scenario label')
                scenario = row['scenario'] if scenario is None else scenario; same(row['scenario'], scenario)
                integer(row['ordinal'], n, n); require(type(row['kind']) is str, 'kind string')
                self.consume(row['kind'], row['data'])
                if hasattr(self, '_after_health'):
                    self.current = self._after_health; del self._after_health
            require(self.end and self.batch.state == 'complete', 'truncated capture/no final census')
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            error = str(exc)
            if self.batch:
                self.batch.frozen = True; self.batch.state = 'frozen'
        summary = self.batch.summary() if self.batch else {'state': 'frozen', 'current_item': None, 'rows': []}
        return {'origin': 'isolated_mock_projection', 'valid_complete_mock': error is None, 'error': error,
                'model': summary, 'last_typed_core_item_record': self.raw_current,
                'final_typed_result_diagnostic_only': final_result,
                'normal_mock_call_intervals': self.intervals,
                'actual_host_format_supported': False, 'actual_journal_validated': False,
                'runtime_authorized': False, 'effect_verified': False, 'production_ready': False,
                'retry_allowed': False, 'native_called_by_projector': False}


def project(rows):
    return Projection().replay(rows)
