"""Verify selected save/cold-reload persistence and update a new 120-row overlay."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bridge.tag_command_backend import GAME_SHA, TagCommandBackend, read, decode, require
from bridge.tag_test_policy import historical_dispatch_blocks
from work.validate_current_diplomacy_1375 import committed_peak

OUT = ROOT/'work/reports/diplomacy-corrective-20261014'

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def scalars(entries):
    return {e['key']:e.get('value') for e in entries if 'entries' not in e}

def projection(report):
    p=report['passes'][0]
    return dict(date=p['roots']['date'], player=p['roots']['current_player'],
        war=p['country_war_raw_289b'],
        resources={tag:{**{key:value for key,value in values.items()
                           if key not in ('heir_pointer','action_cooldowns')},
                        'action_cooldown_entries':values['action_cooldowns']['entries']}
                   for tag,values in p['selected_resources'].items()},
        pairs=[dict(action=x['action'],actor=x['actor_tag'],target=x['target_tag'],
            favors=x['target_to_actor']['favors_raw_milli'],trust=x['target_to_actor']['trust_raw_byte'],
            dependency_type=x['dependency']['object']['type_name']['name'] if x['dependency']['object'] else None,
            dependency_direction=x['dependency']['object']['actor_to_target'] if x['dependency']['object'] else None,
            actor_overlord=x['dependency']['actor_overlord_handle'],
            target_overlord=x['dependency']['target_overlord_handle']) for x in p['pairs']])

def build():
    pins={}
    def pin(path):
        path=(ROOT/path).resolve()
        raw=read(path,8*1024*1024)
        pins[path.relative_to(ROOT).as_posix()]={'bytes':len(raw),'sha256':digest(raw)}
        return raw
    def doc(path):
        return decode(pin(path))
    audit=doc(OUT/'runtime-file-audit.json')
    for path,p in audit['source_pins'].items():
        raw=pin(path)
        require(digest(raw)==p['sha256'] and len(raw)==p['bytes'],'Runtime audit source changed: '+path)
    require(audit['selected_effects_observed']==5 and audit['native_call_pairs_verified']==39
        and audit['all_ownership_closed'] and audit['cold_reload_verified'] is False
        and audit['saved_state_verified'] is False,'Original runtime-only audit changed')
    before=doc(OUT/'final-before.json'); after=doc(OUT/'after.json'); cold=doc(OUT/'cold.json')
    launch=doc(OUT/'cold-launch.json'); saved=doc(OUT/'saved-after.json')
    for sample in (before,after,cold):
        require(sample['game_sha256']==GAME_SHA and sample['two_pass_equal']
            and sample['passes'][0]==sample['passes'][1] and sample['native_calls']==0
            and sample['requests_published']==0 and sample['memory_written'] is False,
            'Invalid read-only sample')
        for path,sha in sample['source_pins'].items():
            require(digest(pin(path))==sha,'Observation source changed: '+path)
    require((cold['pid'],cold['creation'])==(launch['new_pid'],launch['creation'])
        and (cold['pid'],cold['creation'])!=(after['pid'],after['creation'])
        and cold['research_modules']==[] and cold['passes'][0]['roots']['manual_pause']==1,
        'Cold observation is not a distinct paused uninstrumented process')
    require(projection(after)==projection(cold),'Cold selected projection differs')
    require(saved['sha256'].lower()==launch['save_sha256'].lower(),'Wrong saved cold source')
    save_hash=hashlib.sha256()
    with Path(saved['path']).open('rb') as f:
        for chunk in iter(lambda:f.read(65536),b''):save_hash.update(chunk)
    require(save_hash.hexdigest()==saved['sha256'],'Saved file changed')
    extracts={stage:doc(OUT/f'selected-save-{stage}.json') for stage in ('before','after')}
    saved_resource_matches=[]
    for stage,sample in (('before',before),('after',after)):
        extract=extracts[stage]
        require(extract['parsed_complete'] and extract['read_only'],'Incomplete save parse')
        if stage=='after':
            require(extract['source']['sha256'].lower()==saved['sha256'],'Wrong serialized after source')
        for path,sha in extract['source_pins'].items():
            require(digest(pin(path))==sha,'Save extractor source changed')
        for tag in ('FRA','SCO'):
            fields=scalars(extract['countries'][tag]['fields'])
            for field in ('treasury','manpower','sailors'):
                value=Decimal(fields[field])*1000
                live=sample['passes'][0]['selected_resources'][tag][field+'_milli']
                require(value==live,'Serialized/live resource mismatch')
                saved_resource_matches.append(dict(stage=stage,tag=tag,field=field,milli=live))
        for expected_type in ('march' if stage=='before' else 'vassal',):
            dependencies=[scalars(r['entries']) for r in extract['global_diplomacy']['records']
                          if r['key']=='dependency']
            selected=[r for r in dependencies if r.get('first')=='FRA' and r.get('second')=='ORL']
            require(len(selected)==1 and selected[0]['subject_type']==expected_type,'Saved dependency mismatch')
        relation=extract['countries']['SCO']['relations']['FRA']['blocks']
        require(len(relation)==1,'Ambiguous saved SCO/FRA relation')
        fields=scalars(relation[0]['entries'])
        require(Decimal(fields['favors'])*1000==sample['passes'][0]['pairs'][0]['target_to_actor']['favors_raw_milli'],
                'Saved favors differ from RPM')
    fields=scalars(extracts['after']['countries']['SCO']['fields'])
    require(fields['prepare_war']=='FRA' and fields['prepare_war_date']=='1446.2.22','Saved war preparation differs')
    fields=scalars(extracts['after']['countries']['FRA']['fields'])
    require(fields['stability']=='2.000' and scalars(extracts['before']['countries']['FRA']['fields'])['stability']=='3.000',
            'Saved march revocation stability observation differs')
    exit_record=doc(OUT/'exit-after-reload.json')
    require(exit_record['pid']==cold['pid'] and exit_record['creation']==cold['creation']
        and exit_record['exit_observed'] and exit_record['exit_code']==0,'Cold exit not verified')
    backend=TagCommandBackend();backend.verify()
    require(len(backend.manifest['source_pins'])==44,'Native source scope changed')
    blocks=historical_dispatch_blocks()
    old=doc(ROOT/'work/reports/unified-validation-20261013/current-action-validation.json')
    rows=[]; receipts={r['command']['action']:r for r in audit['actions']}
    for old_row in old['actions']:
        row=dict(old_row); action=row['action']
        row.update(latest_run_tested=action in receipts,latest_selected_effect_verified=False,
            latest_save_verified=False,latest_cold_reload_verified=False)
        if action in blocks:
            row.update(current_validation_group='historical_dispatch_additional_no_retry',
                development_retry_forbidden=True,remaining_condition_repair_candidate_not_tested=False)
        if action in receipts:
            receipt=receipts[action]
            row['latest_test_receipt']=receipt
            if receipt['state']=='dispatched':
                row.update(current_validation_group='selected_effect_and_cold_reload_20261014_no_retry',
                    development_retry_forbidden=True,remaining_condition_repair_candidate_not_tested=False,
                    latest_selected_effect_verified=True,latest_save_verified=True,latest_cold_reload_verified=True)
            else:
                require(action=='trade_favors_for_heir','Unexpected corrected rejection')
                row.update(current_validation_group='clean_rejection_20261014_requires_condition_repair',
                    development_retry_forbidden=False,remaining_condition_repair_candidate_not_tested=False,
                    remaining_condition_repair_candidate=True)
        rows.append(row)
    require(len(rows)==120 and len({r['action'] for r in rows})==120,'Wrong action scope')
    remaining=[r['action'] for r in rows if r.get('remaining_condition_repair_candidate_not_tested')
               or r.get('remaining_condition_repair_candidate')]
    require(len(remaining)==46 and set(remaining)==set(audit['remaining_repair_actions']),'Candidate overlay differs')
    require(sum(r['latest_selected_effect_verified'] for r in rows)==5,'Wrong new effect count')
    partition=Counter(r['current_validation_group'] for r in rows)
    pin('work/validate_corrective_persistence_20261014.py')
    persistence=dict(schema='EU4TAG-CORRECTIVE-PERSISTENCE/1',file_only=True,
        game_sha256=GAME_SHA,game_calls_by_this_tool=0,requests_published_by_this_tool=0,
        original_runtime_audit_cold_flag_preserved=False,selected_saved_effects=5,
        selected_cold_reload_effects=5,cold_reload_verified=True,new_process_without_research_dll=True,
        commands_resent=0,serialized_resource_matches=saved_resource_matches,
        saved_war_preparation=dict(actor='FRA',date='1446.2.22'),saved_dependency=dict(first='FRA',second='ORL',type='vassal'),
        stability_observed=dict(before='3.000',after='2.000'),projection_after=projection(after),projection_cold=projection(cold),
        tested_identity=audit['identity'],cold_identity=dict(pid=cold['pid'],creation=cold['creation']),
        saved_after=saved,cold_process_exit_code=0,source_pins=pins,
        limitations=['Five selected effects under the installed test Mod, not all120 effects or vanilla balance.',
            'Heir normal false is a proven clean rejection; its first failed condition remains unknown.',
            'The pre-reload process was absent before the exit observer acquired identity; its exit code is unproven.'],
        peak_committed_bytes=committed_peak())
    matrix=dict(schema='EU4TAG-CURRENT-ACTION-VALIDATION-20261014/1',file_only=True,
        game_sha256=GAME_SHA,current_binding_count=120,current_exclusions=27,
        original_batch_states_unchanged={'dispatched':41,'native_rejected':77,'unknown':2},
        latest_tested=6,latest_dispatched=5,latest_clean_rejected=1,latest_saved_and_cold_passed=5,
        bound_actions_with_historical_or_selected_effect_evidence=44,
        remaining_condition_repair_candidates=46,remaining_not_tested_in_latest_batch=45,
        additional_historical_dispatch_exclusions=sorted(blocks),all120_effects_passed=False,
        validation_groups=dict(sorted(partition.items())),actions=rows,source_pins=dict(pins))
    return persistence,matrix

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');a=ap.parse_args()
    persistence,matrix=build()
    for name,value in (('cold-reload-verification.json',persistence),('current-action-validation.json',matrix)):
        path=OUT/name
        if a.check:
            saved=decode(read(path,8*1024*1024));expected=dict(value)
            saved.pop('peak_committed_bytes',None);expected.pop('peak_committed_bytes',None)
            require(saved==expected,'Saved validation changed: '+name)
        else:
            with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=True,indent=2);f.write('\n')
    print(json.dumps(dict(check=a.check,selected_saved_effects=5,selected_cold_effects=5,
        current_bound_selected_effect_evidence=44,remaining_repair_candidates=46,
        source_pins=len(persistence['source_pins']),peak_committed_bytes=persistence['peak_committed_bytes'])))

if __name__=='__main__':
    main()
