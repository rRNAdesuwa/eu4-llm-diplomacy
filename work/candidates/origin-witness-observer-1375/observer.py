"""Offline event-replay prototype. Never reads a process or authorizes execution.

Events are synthetic or future trusted native-capture output, not requests.
Matching this reducer cannot authenticate a trace or prove hook coverage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

EXE_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
REVOKERS = {
    'application_cleanup': 0x1fefa0, 'reset_game': 0x210000, 'load_game': 0x74b8a0,
    'load_parser': 0x5cf740, 'game_reinitialize': 0x749020, 'game_destructor': 0x74bf70,
    'base_game_clear': 0x74dd50, 'logical_clear': 0x74a260, 'game_construct': 0x74c080,
    'database_construct': 0x2812a0, 'country_block_build': 0x2830a0,
    'database_destructor': 0x286250, 'country_clear': 0x2e1a30,
    'index_reallocate': 0x8f4f0, 'index_clear': 0x8f4c0,
    'context_install': 0x811ab0, 'context_reset': 0x14c9930,
    'context_initialize': 0x14c97e0, 'context_transition': 0x14cd8b0,
    'context_list_clear': 0x14cd4d0, 'context_destructor': 0x14c88f0,
    'context_destructor_body': 0x14c99c0, 'transport2_close': 0x1574fb0,
    'transport0_close': 0x157c620, 'transport1_close': 0x1577280,
    'holder_server_install': 0x14c2530, 'server_destructor': 0x80b420,
    'server_destructor_body': 0x80b570,
}
SITES = {'play': 0x1120dd0, 'fallback': 0x113b350, 'context_ctor': 0x14c8940,
         'context_install': 0x811ab0, 'frontend_update': 0x10da520,
         'server_ctor': 0x803270, 'config_copy': 0x80b4c0,
         'holder_server_install': 0x14c2530, 'opaque_dispatch': 0x14ca360}
MAX_LINE = 16384
INTEGER_FIELDS = frozenset(('seq','uptime_ms','thread','span','parent','rva','return_rva',
    'config_argument5','holder_argument4','object','destination','source','callback',
    'frontend','holder','game','frontend_vtable','mode','context_type','context',
    'vtable','flag54','flag55','transport','transport_vtable','transport_backlink',
    'holder_context','start_pending','server','holder_server','database','block',
    'index','player_handle','same_generation'))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def pointer(value):
    return type(value) is int and 0x10000 <= value < 2**63


def exact_ints(value, expected):
    return type(value) is list and len(value) == len(expected) and all(type(x) is int and x == y for x,y in zip(value,expected))


class Observer:
    def __init__(self):
        self.armed = False
        self.closed = False
        self.sequence = 0
        self.last_ms = 0
        self.thread = None
        self.generation = 0
        self.stack = []
        self.seen_spans = set()
        self.candidate = None
        self.witness = None
        self.reason = 'no_observed_origin'

    def revoke(self, reason, terminal=False):
        self.generation += 1
        self.candidate = self.witness = None
        self.reason = reason
        self.closed |= terminal

    def observe(self, e):
        try:
            require(not self.closed, 'observer_closed')
            require(type(e) is dict, 'event_not_object')
            require(all(type(e[key]) is int for key in INTEGER_FIELDS.intersection(e)), 'noninteger_identity_or_state')
            require(type(e.get('thread')) is int and e['thread'] > 0, 'invalid_event_thread')
            require(type(e.get('seq')) is int and e['seq'] == self.sequence + 1, 'event_gap_or_reorder')
            require(type(e.get('uptime_ms')) is int and e['uptime_ms'] >= self.last_ms, 'event_clock_regressed')
            self.sequence, self.last_ms = e['seq'], e['uptime_ms']
            kind = e['event']
            if kind == 'bootstrap':
                require(not self.armed and self.sequence == 1, 'duplicate_bootstrap')
                require(e['exe_sha256'] == EXE_SHA and e['hooks_before_play'] is True, 'missing_early_capture')
                require(type(e['thread']) is int and e['thread'] > 0, 'invalid_owner_thread')
                self.armed, self.thread = True, e['thread']
                return self.status()
            require(self.armed, 'missing_bootstrap')
            if kind == 'capture_loss':
                self.revoke('capture_loss', True)
                return self.status()
            if kind == 'invalidate':
                require(e['reason'] in REVOKERS and e['rva'] == REVOKERS[e['reason']], 'unknown_invalidation_site')
                # Producer must compare preserved entry RCX with its integer identity;
                # this event never follows a possibly freed pointer to decide scope.
                require(e['bound_identity_match'] is True, 'unbound_invalidation')
                self.revoke(e['reason'] + ('_foreign_thread' if e['thread'] != self.thread else ''))
                return self.status()
            require(e['thread'] == self.thread, 'origin_or_snapshot_on_foreign_thread')
            if self.candidate:
                require(self.last_ms - self.candidate['started_ms'] <= 120000, 'startup_candidate_expired')
            if kind == 'enter':
                self.enter(e)
            elif kind == 'exit':
                self.leave(e)
            elif kind == 'frame_snapshot':
                self.frame(e)
            else:
                raise ValueError('unknown_event')
        except (KeyError, TypeError, ValueError) as error:
            self.revoke(str(error), True)
        return self.status()

    def enter(self, e):
        name, span = e['name'], e['span']
        require(name in SITES and e['rva'] == SITES[name], 'unknown_entry_site')
        require(type(span) is int and span > 0 and span not in self.seen_spans, 'reused_invocation')
        require(e['parent'] == (self.stack[-1]['span'] if self.stack else 0), 'wrong_invocation_parent')
        require(len(self.stack) < 32 and len(self.seen_spans) < 4096, 'invocation_bound')
        self.seen_spans.add(span)
        if name == 'play':
            require(not self.stack, 'reentrant_play')
            self.revoke('new_play_sequence')
            require(e['mode'] == 0 and type(e['mode']) is int, 'not_sp_play')
            require(exact_ints(e['config'], [1,0]), 'stale_network_frontend_config')
            require(all(pointer(e[k]) for k in ('callback','frontend','holder','game')), 'invalid_play_identity')
            require(e['frontend_vtable'] == 0x1d5a8c8, 'not_frontend_controller')
            self.candidate = {k:e[k] for k in ('callback','frontend','holder','game')}
            self.candidate.update(play_span=span, started_ms=self.last_ms, cleared=False,
                                  context=None, installed=False, play_returned=False,
                                  fallback_span=None, context_ctor_span=None,
                                  update_span=None, server_ctor_span=None, copy_span=None,
                                  copied_for_ctor=None, published_for_update=None,
                                  server=None, server_returned=False, published=False)
        elif name == 'opaque_dispatch':
            require(self.witness is not None, 'opaque_scope_without_witness')
            require(e['context'] == self.witness['context'], 'wrong_context_scope')
        else:
            c = self.candidate
            require(c is not None, 'origin_entry_without_candidate')
            parent = self.stack[-1]['name'] if self.stack else None
            if name == 'fallback':
                require(parent == 'play' and e['context_type'] == 2, 'unsupported_startup_profile')
                require(c['cleared'] and c['fallback_span'] is None and c['context'] is None and not c['installed'], 'duplicate_or_misordered_fallback')
                c['fallback_span'] = span
            elif name == 'context_ctor':
                require(parent == 'fallback' and c['cleared'] and e['context_type'] == 2, 'context_not_from_fallback')
                require(e['parent'] == c['fallback_span'] and c['context_ctor_span'] is None and c['context'] is None, 'duplicate_or_unbound_context_ctor')
                require(pointer(e['object']), 'invalid_context_object')
                c['context_ctor_span'] = span
            elif name == 'context_install':
                require(parent == 'play' and e['frontend'] == c['frontend'] and e['holder'] == c['holder'], 'unbound_context_install')
                require(e['context'] in (0,c['context']), 'unexpected_context_install')
            elif name == 'frontend_update':
                require(not self.stack and c['play_returned'] and e['frontend'] == c['frontend'], 'unbound_frontend_update')
                require(c['update_span'] is None, 'duplicate_frontend_update')
                c['update_span'] = span
            elif name == 'server_ctor':
                require(parent == 'frontend_update' and e['return_rva'] == 0x10daeb2, 'unexpected_server_caller')
                require(e['parent'] == c['update_span'] and c['server_ctor_span'] is None, 'duplicate_or_unbound_server_ctor')
                require(e['config_argument5'] == c['frontend'] + 0x400 and e['holder_argument4'] == c['holder'], 'constructor_argument_mismatch')
                require(pointer(e['object']), 'invalid_server_object')
                c['server'] = e['object']
                c['server_ctor_span'] = span
            elif name == 'config_copy':
                require(parent == 'server_ctor' and e['return_rva'] == 0x803d2c, 'unexpected_config_caller')
                require(e['parent'] == c['server_ctor_span'] and c['copy_span'] is None, 'duplicate_or_unbound_config_copy')
                require(e['destination'] == c['server'] + 0x1708 and e['source'] == c['frontend'] + 0x400, 'config_copy_identity_mismatch')
                c['copy_span'] = span
            elif name == 'holder_server_install':
                require(parent == 'frontend_update' and c['server_returned'], 'server_not_constructed')
                require(e['parent'] == c['update_span'] and c['published_for_update'] is None and not c['published'], 'duplicate_or_unbound_server_publish')
                require(e['holder'] == c['holder'] and e['server'] == c['server'], 'unbound_server_install')
        self.stack.append(e)

    def leave(self, e):
        require(bool(self.stack) and e['span'] == self.stack[-1]['span'], 'unbalanced_return')
        entry = self.stack.pop()
        require(e['name'] == entry['name'] and e['normal_return'] is True, 'abnormal_or_wrong_return')
        name, c = entry['name'], self.candidate
        if name == 'opaque_dispatch':
            return
        # Revocation in a descendant cannot be repaired by the enclosing return.
        if c is None:
            return
        if name == 'context_ctor':
            require(e['object'] == entry['object'] and e['vtable'] == 0x1d8c900, 'context_identity_mismatch')
            require(exact_ints([e['context_type'],e['flag54'],e['flag55'],e['transport_vtable']], [2,0,1,0x1d96178]), 'context_profile_mismatch')
            require(pointer(e['transport']) and e['transport_backlink'] == e['object'], 'context_backlink_mismatch')
            c.update(context=e['object'],transport=e['transport'])
        elif name == 'context_install':
            require(e['input_consumed'] is True and e['holder_context'] == entry['context'], 'context_ownership_not_observed')
            if entry['context'] == 0:
                require(c['context'] is None and not c['cleared'], 'late_or_duplicate_clear')
                c['cleared'] = True
            else:
                require(c['context'] is not None and not c['installed'], 'duplicate_install')
                c['installed'] = True
        elif name == 'play':
            require(c['installed'] and exact_ints(e['config'], [1,0]) and type(e['mode']) is int and e['mode'] == 0
                    and type(e['start_pending']) is int and e['start_pending'] == 1, 'play_return_contract')
            c['play_returned'] = True
        elif name == 'fallback':
            require(c['context'] is not None and entry['span'] == c['fallback_span'], 'fallback_missing_context_ctor')
        elif name == 'config_copy':
            require(exact_ints(e['config'], [1,0]), 'network_or_noncanonical_config')
            require(entry['span'] == c['copy_span'] and entry['parent'] == c['server_ctor_span'], 'config_copy_span_mismatch')
            c['copied_for_ctor'] = entry['parent']
        elif name == 'server_ctor':
            require(c['copied_for_ctor'] == entry['span'] == c['server_ctor_span'] and e['object'] == c['server'] and e['vtable'] == 0x1cb8460, 'server_constructor_contract')
            require(e['holder'] == c['holder'] and exact_ints(e['config'], [1,0]), 'server_copy_contract')
            c['server_returned'] = True
        elif name == 'holder_server_install':
            require(e['input_consumed'] is True and e['holder_server'] == c['server'], 'server_ownership_not_observed')
            require(entry['parent'] == c['update_span'], 'server_publish_span_mismatch')
            c['published_for_update'] = entry['parent']
            c['published'] = True
        elif name == 'frontend_update':
            require(c['published'] and c['published_for_update'] == entry['span'] == c['update_span'], 'frontend_update_incomplete')

    def frame(self, e):
        require(not self.stack and e['rva'] == 0x10a6ec0, 'snapshot_inside_native_scope')
        c = self.candidate or self.witness
        require(c is not None and c['published'], 'late_snapshot_cannot_create_origin')
        require(all(e[k] == c[k] for k in ('game','server','holder','context','transport')), 'identity_changed')
        require(exact_ints(e['config'], [1,0]) and type(e['mode']) is int and e['mode'] == 0, 'frame_mode_changed')
        require(exact_ints(e['context_profile'], [2,0,1,0x1d96178]) and e['transport_backlink'] == c['context'], 'frame_context_changed')
        require(e['same_generation'] == self.generation and e['double_snapshot_equal'] is True, 'unstable_generation_or_snapshot')
        require(e['players_complete'] is True and e['only_local_ids'] is True and e['pending_transition'] is False, 'ambiguous_player_or_pending_state')
        require(all(pointer(e[k]) for k in ('database','block','index','player_handle')), 'invalid_world_binding')
        world = tuple(e[k] for k in ('database','block','index','player_handle'))
        if self.witness:
            require(world == self.witness['world_binding'], 'world_storage_or_player_changed')
        else:
            c['world_binding'] = world
            self.witness, self.candidate = c, None
        self.reason = 'complete_type2_origin_sequence_observed'

    def status(self):
        return {'generation':self.generation, 'origin_sequence_observed':self.witness is not None,
                'observation_quiescent':not self.stack, 'closed':self.closed, 'reason':self.reason,
                'production_ready':False, 'native_hook_coverage_verified':False,
                'engine_lifetime_synchronized':False, 'native_invoked':False}

    def finish(self):
        if not self.closed and (self.stack or self.candidate is not None or not self.armed):
            self.revoke('incomplete_trace_at_eof', True)
        return self.status()


def replay(path):
    observer = Observer()
    with Path(path).open('rb') as stream:
        number = 0
        while raw := stream.readline(MAX_LINE + 1):
            number += 1
            require(number <= 10000 and len(raw) <= MAX_LINE, 'trace_bound')
            observer.observe(json.loads(raw.decode('utf-8')))
    return observer.finish()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    print(json.dumps(replay(parser.parse_args().trace),indent=2))
