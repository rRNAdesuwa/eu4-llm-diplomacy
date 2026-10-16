"""Aggregate initial/final selected-state census. No engine calls or comparisons."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_current as probe
from work import probe_diplomacy_relations_v7_1375 as core
from work import probe_pair_extension_v10_1375 as extension
from work import probe_pair_extension_v11_1375 as advanced
from work.native import lab_protocol_v17_1375 as lab

PINS = {
    'work/probe_diplomacy_current.py': 'a5a0b775a701466cf5f4c85db671e37f81c165daf5fddd2080b71ed6f147bb38',
    'work/probe_diplomacy_relations_v7_1375.py': 'ff28f8bbcac46411d3405cc76e501e0984fd592c72c9196d5abbe005f3529805',
    'work/probe_pair_effects_1375.py': 'e5ae9d341c57e7cc79169b708c1d37ccf79ac3d09e88c953e1d4bcbb3ab1cf67',
    'work/probe_pair_extension_v10_1375.py': 'b29a9352df4ad26dd87b5087bdd98d95476dda70b735b3492d3c068b3f85deef',
    'work/probe_pair_extension_v11_1375.py': 'ab60e44f1ebdbf79cf276f62b0e3b76b5fbdc90dd6092fb7289f010527b04e5b',
    'work/candidates/ordinary-insult-observer-1375/observer.py': '708adae32bf5f16db3678b70ffedb6e855ff8755fd0456044f666db1b4595638',
    'work/native/lab_protocol_v17_1375.py': '5bce16b8c951850cbbdc47c88e1edb0cd5b565d3dae2f9785246a92656afa202',
}
CORE = (('NAV','royal_marriage'), ('NAV','vassalaction'), ('FOI','improve_relation'),
        ('POR','guaranteeaction'), ('ENG','spy_network'))
EXTENSION = (('POR','allianceaction'), ('POR','milaccess'), ('POR','offermilaccess'),
             ('POR','fleet_access'), ('POR','offer_fleet_access'), ('POR','warsubsidy'), ('ENG','embargoaction'))
ADVANCED = (('ENG','warningaction',None), ('NAV','support_independence_action',None),
            ('ENG','form_coalition',None), ('POR','transfer_trade_power','target_to_actor'),
            ('POR','transfer_trade_power','actor_to_target'), ('POR','steer_trade','target_to_actor'),
            ('POR','steer_trade','actor_to_target'), ('POR','giftaction',None), ('POR','trade_favors_for_gold',None))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def verify_pins():
    for name, expected in PINS.items():
        path = ROOT / name
        lab._no_links(path)
        raw = lab.read_bounded(path, 128 * 1024)
        require(hashlib.sha256(raw).hexdigest() == expected, 'Census dependency changed: ' + name)
    manifest, digest = lab.verify_build()
    require(digest == 'b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d'
            and manifest['dll_sha256'] == 'D8B962B19D489FD366F346416BB72A8958F3DC53B504A29EC835D3B99CAFA1EE',
            'Exact frozen v17 build required')


def validate_command(command):
    fields = {'kind','boundary','raw_date','last_sequence','pid','creation','world_cookie','run_id','issued_uptime_ms'}
    require(type(command) is dict and set(command) == fields, 'Exact internal observe command')
    require(command['kind'] == 'observe' and command['boundary'] in ('initial','final'), 'Only batch boundaries')
    for key, low in (('pid',1),('raw_date',1),('last_sequence',0),('issued_uptime_ms',0)):
        require(type(command[key]) is int and low <= command[key] <= 2**63-1, 'Invalid integer: '+key)
    require(type(command['creation']) is str and re.fullmatch('[0-9a-f]{16}',command['creation'])
            and int(command['creation'],16)>0, 'Exact creation')
    require(type(command['world_cookie']) is str and re.fullmatch('0x[0-9a-f]+',command['world_cookie'])
            and int(command['world_cookie'],16)>=0x10000, 'Exact world')
    require(type(command['run_id']) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,47}',command['run_id']), 'Safe run name')


def resource_fields(first, second):
    # Budget counters depend on cumulative reader traffic, not the selected state.
    a, b = dict(first), dict(second)
    a.pop('memory_bytes_requested',None); b.pop('memory_bytes_requested',None)
    require(canonical(a) == canonical(b), 'Full diagnostic state changed between boundary passes')
    require(a['status'] == 'bounded_snapshot' and a['country_identities_verified'] is True, 'Incomplete diagnostic')
    diplomats = a['actor_diplomats']
    count, idle, entries = diplomats['entry_count'], diplomats['state_zero_count'], diplomats['entries']
    require(type(count) is int and 0 <= count <= 256 and type(idle) is int and 0 <= idle <= count
            and type(entries) is list and len(entries) == count, 'Diplomat vector bounds')
    require(all(type(e['state_raw_18']) is int and 0 <= e['state_raw_18'] <= 255
                and type(e['state_zero_available_candidate']) is bool
                and e['state_zero_available_candidate'] == (e['state_raw_18'] == 0) for e in entries), 'Diplomat state types')
    require(idle == sum(e['state_raw_18'] == 0 for e in entries), 'Diplomat state count mismatch')
    return count, idle


def binding(raw, source, command, identity):
    require(type(source['pid']) is int and source['pid'] == command['pid']
            and type(source['process_creation_filetime']) is int
            and source['process_creation_filetime'] == int(command['creation'],16)
            and type(source['process_exit_filetime']) is int and source['process_exit_filetime'] == 0,
            'Sub-observer process identity differs')
    require(source['module_base'] == raw['module_base'] == identity['module_base'], 'Sub-observer module differs')
    require(raw['game'] == command['world_cookie'] and type(raw['current_raw_date']) is int
            and raw['current_raw_date'] == command['raw_date'], 'Sub-observer world/date differs')
    require(canonical(raw['player']) == canonical(identity['player']), 'Sub-observer full player differs')


def health(evidence, live, command):
    require(evidence['last_sequence'] == command['last_sequence'] and type(evidence['last_sequence']) is int,
            'Unexpected writer at observation boundary')
    frame = evidence['latest_frame']
    require(frame['raw_date'] == command['raw_date'] and type(frame['raw_date']) is int
            and frame['world_cookie'] == command['world_cookie'] and frame['paused'] is True
            and type(frame['native_speed_index']) is int and frame['native_speed_index'] == 0,
            'Boundary is not the selected paused date')
    lab.check_ready(evidence,live,lab.uptime_ms(),operation='pair')
    require(frame['acceptance_state'] == 'closed' and type(frame['acceptance_flag']) is int
            and frame['acceptance_flag'] == 0, 'Acceptance window active at census')


def sample(command):
    validate_command(command); verify_pins()
    output = lab.OUTPUT / ('batch-'+command['run_id']+'-'+command['boundary']+'-census.json')
    lab._no_links(output)
    require(not output.exists(), 'Census evidence path exists; never overwrite or retry')
    # Reserve before any memory access; a failed census remains a visible failure.
    with output.open('x',encoding='utf-8',newline='\n') as destination:
        reports, selected = {}, {}
        with lab.LiveLabProcess(command['pid'],expected_creation=command['creation']) as process:
            session = lab.session_path(lab.OUTPUT,command['pid'],command['creation'])
            metadata = lab.read_session_metadata(session,command['pid'],command['creation'])
            first_identity = process.snapshot()
            prior_health = lab.read_evidence(session,metadata)
            health(prior_health,first_identity,command)
            first = probe.inspect_state(process.reader,process.reader.base,slots=256,actor='FRA',target='ENG')
            identity = {'module_base':hex(process.reader.base),'player':core.read_identity(process.reader,process.reader.base,'ENG')['player']}
            executable = ROOT.parent / 'eu4.exe'
            def capture(label,module,target,action,flow=None):
                report = module.sample_process(command['pid'],executable,target,action) if flow is None else module.sample_process(command['pid'],executable,target,action,flow)
                raw,state,_ = module.validated_report(report)
                binding(raw,report['source'],command,identity)
                reports[label],selected[label] = report,state
            for target, action in CORE:
                capture('core:'+target+':'+action,core,target,action)
            for target, action in EXTENSION:
                capture('extension:'+target+':'+action,extension,target,action)
            for target, action, flow in ADVANCED:
                capture('advanced:'+target+':'+action+':'+str(flow),advanced,target,action,flow)
            spec = importlib.util.spec_from_file_location('batch_census_ordinary_insult',ROOT/'work/candidates/ordinary-insult-observer-1375/observer.py')
            insult = importlib.util.module_from_spec(spec); spec.loader.exec_module(insult)
            report = insult.sample_process(command['pid'],command['creation'],executable,'ENG')
            raw,state = insult.validated_report(report)
            require(raw['identity']['world'] == command['world_cookie'] and raw['identity']['raw_date'] == command['raw_date']
                    and raw['identity']['module_base'] == identity['module_base']
                    and raw['identity']['player_handle'] == first_identity['player_handle'], 'Insult identity/world/date differs')
            reports['ordinary-insult:ENG'],selected['ordinary-insult:ENG'] = report,state
            second = probe.inspect_state(process.reader,process.reader.base,slots=256,actor='FRA',target='ENG')
            count,idle = resource_fields(first,second)
            final_identity = process.snapshot(); following_health = lab.read_evidence(session,metadata)
            require(canonical(first_identity) == canonical(final_identity), 'Held boundary world/date/player changed')
            health(following_health,final_identity,command)
            observed = lab.uptime_ms()
            require(command['issued_uptime_ms'] <= observed <= command['issued_uptime_ms']+40000, 'Census deadline exceeded')
            verify_pins()
            aggregate = {'schema_version':1,'kind':'cross_date_selected_state_census','command':command,
                         'diagnostic_passes':[first,second],'reports':reports,'selected':selected,
                         'identity_before_after':[first_identity,final_identity],
                         'health_before_after':[prior_health['latest_frame'],following_health['latest_frame']],
                         'atomic_snapshot':False,'individual_effect_verified':False,'request_causality_verified':False,
                         'strict_single_player_verified':False,'world_epoch_verified':False,'production_ready':False,
                         'observed_uptime_ms':observed}
            raw = (json.dumps(aggregate,indent=2)+'\n').encode()
            require(len(raw) <= 8*1024*1024, 'Aggregate census exceeds bounded artifact budget')
            destination.write(raw.decode()); destination.flush(); os.fsync(destination.fileno())
    return {'validated_frozen_evidence':True,'pid':command['pid'],'creation':command['creation'],
            'world_cookie':command['world_cookie'],'boundary':command['boundary'],
            'observation_kind':'cross_date_selected_state_census','artifact_sha256':hashlib.sha256(raw).hexdigest(),
            'raw_date':command['raw_date'],'last_sequence':command['last_sequence'],'paused':True,
            'two_pass_consistent':True,'observed_uptime_ms':observed,'diplomat_count':count,
            'idle_state_zero_count':idle,'individual_effect_verified':False}
