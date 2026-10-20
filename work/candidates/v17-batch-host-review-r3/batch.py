"""Pure finite v17 batch coordinator. No subprocess, game, socket or publication."""
from copy import deepcopy
import hashlib
import json
import re

# Exact projection of the independently reviewed matrix; see source-pins.json.
PAIRS = (
    ('offer_vassalization', 'cancel_vassalization'), ('royal_marriage', 'break_marriage'),
    ('improve_relations', 'stop_improving_relations'), ('guarantee', 'revoke_guarantee'),
    ('build_spy_network', 'stop_building_spy_network'), ('offer_alliance', 'dissolve_alliance'),
    ('ask_military_access', 'cancel_military_access'), ('offer_military_access', 'revoke_military_access'),
    ('ask_fleet_basing_rights', 'cancel_fleet_basing_rights'), ('offer_fleet_basing_rights', 'revoke_fleet_basing_rights'),
    ('embargo', 'revoke_embargo'), ('give_subsidies', 'cancel_subsidies'),
    ('form_coalition', 'leave_coalition'), ('support_independence', 'cancel_independence_support'),
    ('request_trade_power', 'cancel_trade_power_transfer'), ('steer_trade', 'cancel_steer_trade'))
SINGLES = ('send_gift', 'trade_favors_for_gold', 'warn', 'insult')
MATRIX = (
    ('royal_marriage','NAV'), ('offer_alliance','POR'), ('improve_relations','FOI'),
    ('guarantee','POR'), ('give_subsidies','POR'), ('ask_military_access','POR'),
    ('offer_military_access','POR'), ('ask_fleet_basing_rights','POR'),
    ('offer_fleet_basing_rights','POR'), ('request_trade_power','POR'),
    ('cancel_trade_power_transfer','POR'), ('steer_trade','POR'), ('cancel_steer_trade','POR'),
    ('send_gift','POR'), ('trade_favors_for_gold','POR'), ('warn','ENG'), ('insult','ENG'),
    ('embargo','ENG'), ('form_coalition','ENG'), ('build_spy_network','ENG'),
    ('support_independence','NAV'), ('stop_improving_relations','FOI'),
    ('stop_building_spy_network','ENG'), ('revoke_guarantee','POR'), ('cancel_subsidies','POR'),
    ('cancel_military_access','POR'), ('revoke_military_access','POR'),
    ('cancel_fleet_basing_rights','POR'), ('revoke_fleet_basing_rights','POR'),
    ('leave_coalition','ENG'), ('cancel_independence_support','NAV'), ('break_marriage','NAV'),
    ('cancel_vassalization','NAV'), ('dissolve_alliance','POR'), ('revoke_embargo','ENG'),
    ('offer_vassalization','POR'))
ORDER = tuple(a for a, _ in MATRIX)
SURVEY_ONLY = frozenset(('support_independence','cancel_independence_support'))
TAGS = ('ENG', 'POR', 'NAV', 'FOI')
TTL_MS = 60000
MAX_PUBLICATIONS = 128
MAX_DATE_LEASES = 36


def require(ok, message):
    if not ok:
        raise ValueError(message)


def integer(x, lo=0, hi=2**63-1):
    return type(x) is int and lo <= x <= hi


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False)


def command_id(command):
    return hashlib.sha256(canonical(command).encode()).hexdigest()


def validate_plan(plan):
    require(type(plan) is dict and set(plan) == {'protocol', 'purpose', 'pid', 'creation', 'world_cookie',
        'window_thread', 'first_sequence', 'observation_mode', 'run_id', 'rows'}, 'Exact batch plan schema')
    require(plan['protocol'] == 'EU4LAB/3' and plan['purpose'] == 'restricted_pair_lab_1375_v17', 'Fixed v17 only')
    require(integer(plan['pid'], 1, 2**32-1) and integer(plan['window_thread'], 1, 2**32-1)
        and integer(plan['first_sequence'], 1, 2**63-1-MAX_PUBLICATIONS), 'Plan identity/sequence bounds')
    require(type(plan['creation']) is str and re.fullmatch('[0-9a-f]{16}', plan['creation'])
        and int(plan['creation'], 16) > 0, 'Exact creation')
    require(type(plan['world_cookie']) is str and re.fullmatch('0x[0-9a-f]+', plan['world_cookie'])
        and int(plan['world_cookie'], 16) >= 0x10000, 'Explicit world')
    require(plan['observation_mode'] == 'initial_final' and type(plan['run_id']) is str
        and re.fullmatch('[a-z0-9][a-z0-9-]{0,47}', plan['run_id']), 'Observation mode/run id')
    require(type(plan['rows']) is list and len(plan['rows']) == 36, 'Exactly 36 ordered research IDs')
    for (action, target), row in zip(MATRIX, plan['rows']):
        require(type(row) is dict and set(row) == {'action', 'target'} and row['action'] == action
            and row['target'] == target, 'Fixed ordered action/target only; no scalar overrides')
    return deepcopy(plan)


class Batch:
    """One process-local run; cannot resume/retry an uncertain outstanding job.

    journal(record) must return only after durable append. The future trusted
    adapter supplies *validated* frozen CLI evidence, never a public JSON ACK.
    next() and receive() are bounded and nonblocking; the adapter polls jobs.
    """
    def __init__(self, plan, journal):
        self.plan = validate_plan(plan); self.journal = journal
        self.state = 'initial_observation'; self.index = 0; self.mode = 'legality_only'
        self.last_sequence = self.plan['first_sequence'] - 1
        self.inflight = None; self.last_target_attempt = {}; self.date_leases = 0
        self.rows = []; self.observations = []; self.failure = None; self.wait_since = None
        self.last_health_date = None; self.last_now = None
        self.legal = None; self.expected_health = None

    def stop(self, reason):
        self.state = 'terminal'; self.failure = reason
        # Intentionally retain inflight: a missing ACK is never cancellation.
        return {'state': 'terminal', 'reason': reason, 'automatic_retry': False}

    def emit(self, record):
        try:
            self.journal(deepcopy(record))
        except Exception:
            self.stop('durable_batch_audit_failed')
            raise

    def clock(self, now):
        require(integer(now) and (self.last_now is None or now >= self.last_now), 'Invalid/regressed monotonic clock')
        self.last_now = now

    def health(self, h, now):
        require(type(h) is dict and integer(now) and h['pid'] == self.plan['pid']
            and type(h['pid']) is int and h['creation'] == self.plan['creation']
            and h['world_cookie'] == self.plan['world_cookie']
            and type(h['thread']) is int and h['thread'] == self.plan['window_thread'], 'Health identity changed')
        require(integer(h['raw_date'], 1, 2**31-1) and integer(h['last_sequence'])
            and integer(h['uptime_ms'], 0, now) and now-h['uptime_ms'] <= 2500, 'Stale/invalid health')
        require(all(h[k] is True for k in ('world_ready', 'lifecycle_passed', 'owned_peace_passed', 'preview_passed', 'command_passed'))
            and all(h[k] is False for k in ('session_frozen', 'world_changed', 'thread_changed')), 'Terminal native health')
        require(type(h['acceptance_flag']) is int and h['acceptance_flag'] == 0
            and h['acceptance_state'] == 'closed', 'Batch cannot hold or alter an acceptance window')
        require(self.last_health_date is None or h['raw_date'] >= self.last_health_date, 'Date regressed')
        self.last_health_date = h['raw_date']
        require(h['last_sequence'] <= self.last_sequence, 'Another writer consumed a sequence')
        require(type(h['native_speed_index']) is int and all(type(h[k]) is bool for k in
            ('paused','pending','lease_active','lease_pending','mailbox_ready')), 'Readiness scalar types')
        ready = h['last_sequence'] == self.last_sequence and h['paused'] is True and h['native_speed_index'] == 0
        ready = ready and h['pending'] is False and h['lease_active'] is False and h['lease_pending'] is False and h['mailbox_ready'] is True
        if ready and self.expected_health is not None:
            require(h['last_sequence'] == self.expected_health['sequence'] and h['raw_date'] == self.expected_health['raw_date'],
                'Following paused health differs from completed native receipt')
            self.expected_health = None
        if not ready:
            if self.wait_since is None:self.wait_since = now
            require(now-self.wait_since <= 10000, 'Paused-ready health did not arrive')
        else:self.wait_since = None
        return ready

    def next(self, h, now):
        if self.state in ('terminal', 'complete'):
            return {'state': self.state}
        try:self.clock(now)
        except ValueError as e:return self.stop(str(e))
        if self.inflight is not None:
            try:
                require(type(h) is dict and type(h.get('pid')) is int and h['pid']==self.plan['pid']
                    and h.get('creation')==self.plan['creation'] and h.get('world_cookie')==self.plan['world_cookie']
                    and type(h.get('thread')) is int and h['thread']==self.plan['window_thread'], 'Fatal inflight identity change')
                require(all(h.get(k) is False for k in ('session_frozen','world_changed','thread_changed'))
                    and h.get('world_ready') is True and type(h.get('acceptance_flag')) is int
                    and h['acceptance_flag']==0 and h.get('acceptance_state')=='closed', 'Fatal inflight native invalidation')
                require(integer(h.get('raw_date'),1,2**31-1) and h['raw_date']>=self.last_health_date
                    and integer(h.get('last_sequence'),self.last_sequence,
                        self.inflight['command'].get('sequence',self.last_sequence)), 'Foreign inflight sequence/date')
                self.last_health_date=h['raw_date']
            except (ValueError,KeyError,TypeError) as e:return self.stop(str(e))
            if now > self.inflight['deadline_ms']:
                return self.stop('job_deadline_unknown_no_retry')
            return {'state': 'waiting', 'command_id': self.inflight['id']}
        try:
            if not self.health(h, now):return {'state': 'waiting_for_paused_health'}
            if self.state == 'initial_observation':
                command = {'kind': 'observe', 'boundary': 'initial','raw_date':h['raw_date'],'last_sequence':h['last_sequence']}
            elif self.index == len(self.plan['rows']):
                command = {'kind': 'observe', 'boundary': 'final','raw_date':h['raw_date'],'last_sequence':h['last_sequence']}
            else:
                row = self.plan['rows'][self.index]
                previous = self.last_target_attempt.get(row['target'], -1)
                if self.mode == 'legality_only' and h['raw_date'] <= previous:
                    require(self.date_leases < MAX_DATE_LEASES, 'Bounded date-advance budget exhausted')
                    command = {'kind': 'speed', 'speed': 5, 'sequence': self.last_sequence+1,
                               'date_must_exceed': previous, 'before_date': h['raw_date']}
                else:
                    if self.mode == 'submit':
                        require(self.legal is not None and now < self.legal['expires'] and h['raw_date'] == self.legal['raw_date']
                            and (row['action'],row['target']) == self.legal['binding'], 'Fresh legality expired or changed date/binding; no submit')
                    command = {'kind': 'pair', 'action': row['action'], 'actor': 'FRA', 'target': row['target'],
                               'mode': self.mode, 'sequence': self.last_sequence+1, 'ttl_ms': TTL_MS,
                               'raw_date': h['raw_date'], 'issued_uptime_ms': now}
                require(command['sequence']-self.plan['first_sequence'] < MAX_PUBLICATIONS, 'Publication budget exhausted')
            command.update(pid=self.plan['pid'], creation=self.plan['creation'], world_cookie=self.plan['world_cookie'],
                           run_id=self.plan['run_id'], issued_uptime_ms=now)
            ident = command_id(command)
            self.inflight = {'command': command, 'id': ident, 'deadline_ms': now+40000}
            self.emit({'event': 'resolved_intent', 'command_id': ident, 'command': command, 'automatic_retry': False})
            return {'state': 'start_once', 'command_id': ident, 'command': deepcopy(command)}
        except (ValueError, KeyError, TypeError) as e:
            return self.stop(str(e))

    def receive(self, ident, result, now):
        if self.state == 'terminal':return {'state': 'terminal'}
        try:
            self.clock(now)
            require(self.inflight is not None and ident == self.inflight['id'], 'Unknown/duplicate job completion')
            c = self.inflight['command']
            require(integer(now,c['issued_uptime_ms'],self.inflight['deadline_ms']), 'Late/regressed receipt time; no retry')
            require(type(result) is dict and result.get('validated_frozen_evidence') is True, 'Unvalidated adapter output')
            require(type(result.get('pid')) is int and all(result.get(k) == c[k] for k in ('pid', 'creation', 'world_cookie')), 'Result identity differs')
            if c['kind'] == 'observe':
                require(result.get('boundary') == c['boundary'] and result.get('observation_kind') == 'cross_date_selected_state_census'
                    and type(result.get('artifact_sha256')) is str and re.fullmatch('[0-9a-f]{64}', result['artifact_sha256']), 'Aggregate observation receipt')
                require(result.get('individual_effect_verified') is False, 'Batch census cannot certify per-action effect')
                require(type(result.get('raw_date')) is int and result['raw_date']==c['raw_date']
                    and type(result.get('last_sequence')) is int and result['last_sequence']==c['last_sequence']
                    and result.get('paused') is True and result.get('two_pass_consistent') is True
                    and integer(result.get('observed_uptime_ms'),c['issued_uptime_ms'],now), 'Observation freshness/date/sequence differs')
                if c['boundary'] == 'initial':
                    require(integer(result.get('diplomat_count'), 100, 256)
                        and integer(result.get('idle_state_zero_count'),100,result['diplomat_count']),
                        'Initial 100 idle-state-candidate resource premise missing')
                outcome = 'aggregate_state_recorded'
            else:
                require(integer(result.get('sequence'), 1) and result['sequence'] == c['sequence'], 'Result sequence differs')
                require(result.get('audit_complete') is True and result.get('session_frozen') is False
                    and result.get('ownership_uncertain') is False and type(result.get('exception')) is int
                    and result['exception'] == 0, 'Unknown native ownership/audit/exception')
                if c['kind'] == 'speed':
                    require(result.get('status') == 'completed_and_paused' and result.get('supervisor_complete') is True
                        and type(result.get('before_date')) is int and result['before_date']==c['before_date']
                        and integer(result.get('after_date'), c['date_must_exceed']+1), 'Date lease did not complete beyond prior target command')
                    outcome = 'date_advanced_with_supervisor'
                else:
                    require(all(result.get(k) == c[k] for k in ('action', 'actor', 'target', 'mode'))
                        and type(result.get('raw_date')) is int and result['raw_date'] == c['raw_date'], 'Pair result binding/date differs')
                    for k in ('preview_called','preview_allowed','gate_called','gate_allowed','submit_entered','submit_returned'):
                        require(type(result.get(k)) is bool, 'Native bool type differs')
                    require(integer(result.get('status'), 0, 3) and integer(result.get('reason'), 0, 23), 'Native status/reason type')
                    if result['submit_returned'] is False:
                        require(result.get('context_submit_return') is None and result.get('caller_container_consumed') is None,
                            'Unreturned submit cannot report context return or consumed ownership')
                    if result['submit_entered']:
                        require(c['mode'] == 'submit' and result['status'] == 2 and result['reason'] == 0
                            and all(result[k] is True for k in ('preview_called','preview_allowed','gate_called','gate_allowed'))
                            and result['submit_returned'] is True and result.get('context_submit_return') is True
                            and result.get('caller_container_consumed') is True, 'Submit ownership/return unknown')
                        outcome = 'dispatched_not_effect_verified'
                    elif result['status'] == 1 and result['reason'] == 0 and all(result[k] is True for k in ('preview_called','preview_allowed','gate_called','gate_allowed')):
                        require(c['mode'] == 'legality_only' and result['submit_returned'] is False, 'Unexpected no-submit success')
                        outcome = 'legality_allowed'
                    else:
                        require(result['status'] in (0, 1) and result['reason'] > 0 and result['submit_returned'] is False,
                            'Ambiguous non-submission')
                        outcome = 'known_rejection_no_submit'
                completed_date=result['after_date'] if c['kind']=='speed' else result['raw_date']
                require(completed_date>=self.last_health_date,'Completed date precedes already observed native date')
            self.emit({'event': 'completed', 'command_id': ident, 'outcome': outcome,
                       'evidence': result, 'individual_effect_verified': False})
            if c['kind'] == 'observe':
                self.observations.append({'boundary':c['boundary'],'sha256':result['artifact_sha256']})
                if c['boundary'] == 'initial':self.state = 'running'
                else:self.state = 'complete'
            else:
                self.last_sequence = c['sequence']
                self.expected_health = {'sequence':c['sequence'],
                    'raw_date':result['after_date'] if c['kind']=='speed' else result['raw_date']}
                if c['kind'] == 'speed':self.date_leases += 1
                else:
                    self.rows.append({'action':c['action'],'target':c['target'],'mode':c['mode'],'sequence':c['sequence'],
                        'outcome':outcome,'status':result['status'],'reason':result['reason'],'individual_effect_verified':False})
                    if outcome == 'legality_allowed' and c['action'] not in SURVEY_ONLY:
                        self.mode = 'submit'
                        self.legal = {'expires':c['issued_uptime_ms']+TTL_MS,'raw_date':c['raw_date'],'binding':(c['action'],c['target'])}
                    else:
                        self.last_target_attempt[c['target']] = result['raw_date']
                        self.index += 1;self.mode = 'legality_only';self.legal = None
            self.inflight = None
            return {'state':self.state,'outcome':outcome,'next_sequence':self.last_sequence+1}
        except (ValueError, KeyError, TypeError) as e:
            return self.stop(str(e))

    def summary(self):
        return {'state':self.state,'failure':self.failure,'rows':deepcopy(self.rows),'observations':deepcopy(self.observations),
                'next_sequence':self.last_sequence+1,'individual_effect_verified':False,
                'positive_effects_before_cancellation':'unobserved',
                'native_dispatch_count':sum(r['outcome']=='dispatched_not_effect_verified' for r in self.rows),
                'legality_attempt_count':sum(r['mode']=='legality_only' for r in self.rows),
                'guard_survey_only':sorted(SURVEY_ONLY),
                'strict_single_player_verified':False,'world_epoch_verified':False,'production_backend_registered':False,
                'live_adapter_implemented':False,'automatic_retry':False}


def argv(command, python='python'):
    """Compile only fixed run_lab_step argv. Does not execute it."""
    require(command['kind'] in ('pair','speed'), 'Aggregate observer requires separately reviewed adapter')
    common={'kind','pid','creation','world_cookie','run_id','sequence','issued_uptime_ms'}
    expected=common|({'speed','date_must_exceed','before_date'} if command['kind']=='speed' else
        {'action','actor','target','mode','ttl_ms','raw_date','issued_uptime_ms'})
    require(set(command)==expected and integer(command['pid'],1,2**32-1) and integer(command['sequence'],1)
        and type(command['creation']) is str and re.fullmatch('[0-9a-f]{16}',command['creation'])
        and type(command['run_id']) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,47}',command['run_id'])
        and integer(command['issued_uptime_ms']) and type(command['world_cookie']) is str
        and re.fullmatch('0x[0-9a-f]+',command['world_cookie']), 'Exact internal command schema')
    if command['kind']=='pair':
        require((command['action'],command['target']) in MATRIX and command['actor']=='FRA'
            and not(command['action'] in SURVEY_ONLY and command['mode']=='submit')
            and command['mode'] in ('legality_only','submit') and type(command['ttl_ms']) is int
            and command['ttl_ms']==TTL_MS and integer(command['raw_date'],1,2**31-1), 'Finite pair argv; fixed scalar parameters are native-only')
    else:require(type(command['speed']) is int and command['speed']==5 and integer(command['before_date'],1,2**31-1)
        and integer(command['date_must_exceed'],1,2**31-1), 'Fixed supervised speed only')
    base = [python,'-B','work/run_lab_step_v17_1375.py','--output',
            'work/runtime/native1375-v17/batch-'+command['run_id']+'-'+str(command['sequence'])+'-'+command['kind']+'.json']
    identity = ['--pid',str(command['pid']),'--creation',command['creation']]
    if command['kind'] == 'speed':
        return base+['speed']+identity+['--sequence',str(command['sequence']),'--speed','5','--ack-disposable']
    return base+['request']+identity+['pair',command['action'],'--actor','FRA','--target',command['target'],
        '--mode',command['mode'],'--sequence',str(command['sequence']),'--ttl-ms','60000','--publish']
