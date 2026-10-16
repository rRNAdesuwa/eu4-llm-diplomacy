"""Recompute the two fixed census receipts from their saved raw passes only."""
import ledger

require=ledger.require
same=ledger.same
integer=ledger.integer


def strict_legacy_report(module, report, command, identity, target, action, flow=None):
    """Do not inherit the old validators' Python bool/int pass equality."""
    raw, state, _=module.validated_report(report)
    require(report['actor']=='FRA' and report['target']==target and report['action']==action,
            'Census family/target differs from its fixed label')
    if flow is not None:
        require(report['trade_direction']==raw['trade_direction']==flow,'Census trade flow differs')
    obs=report['observation'];passes=obs['passes']
    require(type(passes) is list and len(passes)==2 and same(passes[0],passes[1]),'Census typed passes differ')
    states=[module.inspect_state(value) for value in passes]
    require(same(states[0],states[1]) and same(states[0],obs['state']) and same(state,states[0]),
            'Census stored state differs from each raw pass')
    for value in passes:
        require(value['target']==target and value['action']==action,'Second pass family differs')
        if flow is not None:require(value['trade_direction']==flow,'Second pass flow differs')
        source=report['source']
        require(integer(source['pid'],command['pid'],command['pid'])
                and integer(source['process_creation_filetime'],int(command['creation'],16),int(command['creation'],16))
                and integer(source['process_exit_filetime'],0,0),'Census source PID/creation/exit differs')
        require(value['game']==command['world_cookie'] and integer(value['current_raw_date'],command['raw_date'],command['raw_date'])
                and source['module_base']==value['module_base']==identity['module_base']
                and same(value['player'],identity['player']),'Census source world/base/player/date differs')
    return states[0]


def recompute(raw, command, scope, modules, native_frames):
    """No injectable verifier: modules are fixed, pinned imports in reviewer.py."""
    census,core,extension,advanced,insult=modules
    census.validate_command(command)
    document=ledger.json_value(raw)
    keys={'schema_version','kind','command','diagnostic_passes','reports','selected','identity_before_after',
          'health_before_after','atomic_snapshot','individual_effect_verified','request_causality_verified',
          'strict_single_player_verified','world_epoch_verified','production_ready','observed_uptime_ms'}
    require(type(document) is dict and set(document)==keys and integer(document['schema_version'],1,1)
            and document['kind']=='cross_date_selected_state_census' and same(document['command'],command),
            'Exact raw census contract differs')
    require(all(document[k] is False for k in ('atomic_snapshot','individual_effect_verified','request_causality_verified',
            'strict_single_player_verified','world_epoch_verified','production_ready')),'Census overclaims effects')
    observed=document['observed_uptime_ms']
    require(integer(observed,command['issued_uptime_ms'],command['issued_uptime_ms']+40000),'Census time bound')
    identities=document['identity_before_after'];diagnostics=document['diagnostic_passes'];health=document['health_before_after']
    require(all(type(x) is list and len(x)==2 for x in (identities,diagnostics,health)) and same(*identities),
            'Two full held boundary identities required')
    live=identities[0]
    require(integer(live['pid'],command['pid'],command['pid']) and live['creation']==command['creation']
            and live['world_cookie']==command['world_cookie'] and integer(live['raw_date'],command['raw_date'],command['raw_date'])
            and integer(live['acceptance_flag'],0,0),'Held census outer identity differs')
    player=diagnostics[0]['player'];core.base.validated_identity(player,core.HANDLES['FRA'])
    census.same_handle(live['player_handle'],player['handle'])
    identity={'module_base':document['reports']['core:NAV:royal_marriage']['source']['module_base'],'player':player}
    for diagnostic in diagnostics:census.diagnostic_binding(diagnostic,command,identity)
    count,idle=census.resource_fields(*diagnostics)
    previous_frame=0
    for frame in health:
        encoded=ledger.canonical(frame)
        require(encoded in native_frames,'Census heartbeat is absent from the fixed native log')
        require(integer(frame['frames'],previous_frame) and integer(frame['uptime_ms'],max(1,observed-2500),observed),
                'Census heartbeat time/order differs');previous_frame=frame['frames']
        require(integer(frame['last_sequence'],command['last_sequence'],command['last_sequence'])
                and integer(frame['raw_date'],command['raw_date'],command['raw_date'])
                and frame['world_cookie']==command['world_cookie'] and frame['paused'] is True
                and integer(frame['native_speed_index'],0,0) and frame['mailbox_ready'] is True
                and frame['lease_active'] is False and frame['acceptance_state']=='closed'
                and integer(frame['acceptance_flag'],0,0),'Census boundary not a ready paused frame')
        require(frame['player_handle']==live['player_handle'] and frame['thread']==scope['plan']['window_thread'],
                'Census heartbeat player/thread differs')
    selected={};reports=document['reports']
    require(type(reports) is dict and type(document['selected']) is dict,'Census reports and states must be objects')
    for group,module,items in (('core',core,census.CORE),('extension',extension,census.EXTENSION),('advanced',advanced,census.ADVANCED)):
        for item in items:
            target,action=item[:2];flow=item[2] if len(item)==3 else None
            label=group+':'+target+':'+action+(':'+str(flow) if group=='advanced' else '')
            selected[label]=strict_legacy_report(module,reports[label],command,identity,target,action,flow)
    label='ordinary-insult:ENG';report=reports[label];sample,state=insult.validated_report(report)
    require(sample['target']=='ENG','Ordinary insult target differs')
    source=report['source']
    for key in ('before','after'):
        held=source[key]
        require(integer(held['pid'],command['pid'],command['pid'])
                and integer(held['creation_filetime'],int(command['creation'],16),int(command['creation'],16))
                and integer(held['exit_filetime'],0,0) and held['module_base']==identity['module_base'],
                'Ordinary insult held process differs')
    require(sample['identity']['world']==command['world_cookie'] and integer(sample['identity']['raw_date'],command['raw_date'],command['raw_date'])
            and sample['identity']['module_base']==identity['module_base'],'Ordinary insult world/date differs')
    census.same_handle(sample['identity']['player_handle'],live['player_handle']);selected[label]=state
    require(set(reports)==set(selected) and same(document['selected'],selected),'Incomplete/extra/stale selected census states')
    return dict(validated_frozen_evidence=True,pid=command['pid'],creation=command['creation'],world_cookie=command['world_cookie'],
        boundary=command['boundary'],observation_kind='cross_date_selected_state_census',artifact_sha256=ledger.digest(raw),
        raw_date=command['raw_date'],last_sequence=command['last_sequence'],paused=True,two_pass_consistent=True,
        observed_uptime_ms=observed,diplomat_count=count,idle_state_zero_count=idle,individual_effect_verified=False)
