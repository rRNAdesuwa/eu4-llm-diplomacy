"""Finite, exact frozen-v17 pair audit contract. No game access or inference."""
from ledger import require, same

# Frozen work/native/v17/pair-engine-1375.cpp kCountries and audit %016llx.
HANDLES = {
    'FRA': '0x0100007a00415246', 'ENG': '0x0100002e00474e45',
    'POR': '0x010000bd00524f50', 'NAV': '0x010000bc0056414e',
    'FOI': '0x0100007900494f46',
}
FLAGS = ('preview_called', 'preview_allowed', 'gate_called', 'gate_allowed',
         'original_destroyed', 'command_destroyed_before_dispatch')


def validate(row, base):
    request, records, wrapper = row['request'], row['records'], row['complete']
    require(request['operation'] == 'pair' and request['mode'] in ('legality_only', 'submit')
            and request['actor'] in HANDLES and request['target'] in HANDLES
            and request['actor'] != request['target'], 'Pair request profile differs')
    require(type(records) is list and len(records) in (2, 3), 'Pair ownership record count differs')
    fixed = dict(
        fixed_subsidy_amount_milli=1000 if request['action'] in ('give_subsidies', 'cancel_subsidies') else 0,
        fixed_subsidy_duration_years=10 if request['action'] in ('give_subsidies', 'cancel_subsidies') else 0,
        fixed_gift_amount_milli=25000 if request['action'] == 'send_gift' else 0,
        fixed_transfer_fraction_milli=500 if request['action'] in ('request_trade_power', 'cancel_trade_power_transfer') else 0,
        fixed_insult_index=-1 if request['action'] == 'insult' else 0)
    for core in records:
        base.strict_pair(core)  # Exact keys, bool/int/null types and no uncertainty.
        require(core['world'] == base.WORLD and core['pid'] == base.PID
                and core['thread_id'] == base.THREAD and core['process_creation_filetime'] == base.CREATION
                and core['actor'] == request['actor'] and core['target'] == request['target']
                and core['action_id'] == request['action'], 'Pair core complete identity differs')
        require(core['actor_handle'] == HANDLES[request['actor']]
                and core['target_handle'] == HANDLES[request['target']], 'Native full country handle differs')
        require(all(core[k] == v for k, v in fixed.items()), 'Fixed native scalar differs')
        # invoke starts at -1; cancellation_binding returns before the copy on
        # failure. Only spy_binding supplies an int32 nonnegative envoy ID.
        resolved_spy = (request['action'] == 'stop_building_spy_network'
                        and core['event'] != 'pair_engine_begin'
                        and (core['phase'], core['reason']) != (3, 13))
        require((0 <= core['envoy_id'] <= 2**31-1) if resolved_spy else core['envoy_id'] == -1,
                'Native action/phase-specific envoy binding differs')
    begin, final = records[0], records[-1]
    require(begin['event'] == 'pair_engine_begin' and begin['phase'] == 2
            and begin['status'] == begin['reason'] == 0 and begin['envoy_id'] == -1
            and all(begin[k] is False for k in base.PAIR_BOOLS)
            and all(begin[k] is None for k in base.PAIR_NULLABLE), 'Pair begin owns future output')
    require(final['event'] == 'pair_engine_complete'
            and all(core['raw_date'] == begin['raw_date'] for core in records),
            'Pair core date/event changes within the bounded native call')
    intent_present = len(records) == 3
    if intent_present:
        intent = records[1]
        require(request['mode'] == 'submit' and intent['event'] == 'pair_engine_dispatch_intent'
                and intent['phase'] == 11 and intent['status'] == intent['reason'] == 0
                and all(intent[k] is True for k in FLAGS[:5])
                and all(intent[k] is False for k in ('submit_entered', 'submit_returned', 'command_destroyed_before_dispatch'))
                and all(intent[k] is None for k in base.PAIR_NULLABLE),
                'Dispatch intent already owns future transfer result')
        require(intent['envoy_id'] == final['envoy_id'], 'Dispatch intent/final envoy binding differs')

    # These outcomes follow execute()'s restored outcome_phase after cleanup.
    # A no-enter submit request retains status=0; only legality_only sets 1.
    entered = final['submit_entered']
    if entered:
        require(request['mode'] == 'submit' and request['actor'] == 'FRA' and intent_present
                and final['phase'] == 13 and final['status'] == 2 and final['reason'] == 0
                and final['submit_returned'] is True
                and final['context_submit_return'] is True and final['caller_container_consumed'] is True,
                'Dispatched phase/status/ownership differs')
        expected_flags = (True, True, True, True, True, False)
    else:
        require(final['submit_returned'] is False and all(final[k] is None for k in base.PAIR_NULLABLE),
                'Non-entered pair owns transfer output')
        phase, reason = final['phase'], final['reason']
        mode_status = 1 if request['mode'] == 'legality_only' else 0
        if (phase, reason) == (3, 13):
            require(not intent_present and final['status'] == 0 and final['envoy_id'] == -1,
                    'Cancellation binding rejection boundary differs')
            expected_flags = (False, False, False, False, False, False)
        elif (phase, reason) == (6, 17):
            require(not intent_present and final['status'] == mode_status, 'Preview rejection boundary differs')
            expected_flags = (True, False, False, False, True, False)
        elif (phase, reason) == (8, 18):
            require(not intent_present and final['status'] == mode_status, 'Gate rejection boundary differs')
            expected_flags = (True, True, True, False, True, True)
        elif (phase, reason) == (8, 0):
            require(request['mode'] == 'legality_only' and not intent_present and final['status'] == 1,
                    'Legality completion cannot stand in for a submit')
            expected_flags = (True, True, True, True, True, True)
        elif (phase, reason) in ((10, 20), (12, 8)):
            require(request['mode'] == 'submit' and final['status'] == 0
                    and intent_present is (phase == 12), 'Pre-transfer context/guard rejection boundary differs')
            expected_flags = (True, True, True, True, True, True)
        else:
            raise ValueError('Unsupported or contradictory native pair terminal phase/reason')
    require(all(final[k] is v for k, v in zip(FLAGS, expected_flags)), 'Pair terminal cleanup/gate fields differ')
    require(same({k: wrapper[k] for k in ('status', 'reason', 'submit_entered', 'submit_returned', 'ownership_uncertain')},
                 {k: final[k] for k in ('status', 'reason', 'submit_entered', 'submit_returned', 'ownership_uncertain')}),
            'Host/native pair completion differs')
    return final
