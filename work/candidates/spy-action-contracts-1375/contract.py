"""Offline, narrowly typed future-observer evidence contract, NOT an executor.

All acceptance results are correlated observations only. This module never
returns native-call permission. It intentionally cannot identify script hooks,
prove exclusivity, validate engine lifetime, or establish strict single-player.
"""

def _integer(v, lo, hi):
    return type(v) is int and lo <= v <= hi

def cost_sufficient(network_centipoints, cost_milli):
    if not _integer(network_centipoints, 0, 10000): raise ValueError('network')
    if not _integer(cost_milli, 0, 21474831): raise ValueError('cost')
    return network_centipoints * 10 >= cost_milli

def debit_centipoints(network_centipoints, cost_milli):
    """Positive normal bounded branch of 4eaadc..4eab20; no overflow allowed."""
    cost_sufficient(network_centipoints, cost_milli)
    # Native scales negative cost by100, subtracts500 then signed /1000;
    # for nonnegative cost this is subtraction rounded half away from zero.
    return max(0, min(10000, network_centipoints - (cost_milli*100+500)//1000))

def correlate(before, after):
    """Validate already-collected *offline* selected fields. No live reader.

    expiry must be the observed DWORD and expected_expiry independently derives
    from the actual runtime duration. Stock defaults are not substituted here.
    Removed-node handling, registry identity, complete-list proof are producer
    obligations, and this schema expressly does not assert them as verified.
    """
    keys={'process_creation','world','date','actor_handle','target_handle',
          'definition','expected_expiry','network_centipoints','cost_milli',
          'modifiers','collection_complete'}
    for s in (before,after):
        if type(s) is not dict or set(s)!=keys: raise ValueError('schema')
        for k in ('process_creation','world','actor_handle','target_handle','definition'):
            if not _integer(s[k],1,2**64-1):raise ValueError(k)
        for k in ('date','expected_expiry'):
            if not _integer(s[k],0,2**31-1):raise ValueError(k)
        for k in ('actor_handle','target_handle'):
            h=s[k]
            if not h>>56 or (h>>24)&255 or (h>>32)&65535>=32768:
                raise ValueError('handle encoding')
            if any(not 65 <= (h>>(8*i))&255 <= 90 for i in range(3)):
                raise ValueError('handle tag')
        if s['collection_complete'] is not True:raise ValueError('incomplete')
        if type(s['modifiers']) is not list or len(s['modifiers'])>256:raise ValueError('list')
        seen=set()
        for m in s['modifiers']:
            if type(m) is not dict or set(m)!={'object','definition','expiry'}:raise ValueError('modifier schema')
            if not _integer(m['object'],1,2**64-1) or m['object'] in seen:raise ValueError('object')
            seen.add(m['object'])
            if not _integer(m['definition'],1,2**64-1) or not _integer(m['expiry'],0,2**31-1):raise ValueError('modifier values')
        cost_sufficient(s['network_centipoints'],s['cost_milli'])
    for k in keys-{'modifiers','network_centipoints'}:
        if before[k]!=after[k]:raise ValueError('binding differs: '+k)
    if before['actor_handle']==before['target_handle']:raise ValueError('self target')
    if any(x['definition']==before['definition'] for x in before['modifiers']):raise ValueError('already present')
    old={x['object'] for x in before['modifiers']}
    new=[m for m in after['modifiers'] if m['object'] not in old and
         m['definition']==after['definition'] and m['expiry']==after['expected_expiry']]
    return {'new_matching_modifier_count':len(new),
            'cost_delta_matches':after['network_centipoints']==debit_centipoints(before['network_centipoints'],before['cost_milli']),
            'evidence_kind':'same_day_correlated_selected_fields',
            'causality_verified':False,'engine_lifetime_verified':False,
            'native_call_authorized':False,'runtime_verified':False}
