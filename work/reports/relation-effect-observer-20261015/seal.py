"""Seal the additive relation reader/contract without editing R1/R2/live."""
import hashlib,json,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
from bridge import relation_effect_reader as reader
from bridge.tag_command_backend import DEFAULT_MANIFEST,GAME_SHA
from work.discover_diplomacy import check_memory_budget


def main():
    static=json.loads((OUT/'static.json').read_text())
    current=json.loads((ROOT/'work/reports/diplomacy-corrective-20261014/current-action-validation.json').read_text())
    historical={r['action']:r for r in current['actions']}
    save=json.loads((ROOT/'work/reports/diplomacy-corrective-20261014-r3/runtime/batch-after-save-selected.json').read_text())
    recommendations=[]
    wanted={'alliance':('FRA','POR'),'royal_marriage':('ORL','BRI'),'guarantee':('FRA','SAV')}
    for record in save['global_diplomacy']['records']:
        fields={x['key']:x.get('value') for x in record['entries']}
        if record['key'] in wanted and (fields.get('first'),fields.get('second'))==wanted[record['key']]:
            recommendations.append({'relation':record['key'],'record':record,'serialized_source':save['source'],
                                    'runtime_current_state_verified':False,'new_request_effect_verified':False})
    assert len(recommendations)==3
    profiles={}
    for action,p in reader.PROFILES.items():
        assert historical[action]['historical_success_evidence']
        profiles[action]={'index_container_offset':hex(p['index']),'index_data_offset':hex(p['index']+8),
            'index_capacity_offset':hex(p['index']+16),'index_count_offset':hex(p['index']+20),
            'index_vtable_rva':hex(reader.INDEX_VT),'object_vtable_rva':hex(p['object_vt']),
            'object_size_bytes':p['size'],'symmetric':p['symmetric'],
            'full_direction':'unordered actor/target endpoints' if p['symmetric'] else 'object+10 actor guarantor; object+18 target guaranteed',
            'getter':static['loaded_getter_pins'][action], 'reply_required_positive':p['reply_required'],
            'reply_slot':static['reply_slot_bytes'][action],
            'historical_success_evidence':historical[action]['historical_success_evidence'],
            'historical_action_remains_no_retry':True}
    contract={'schema':'EU4DIPLOMACY-RELATION-READER-CONTRACT/1','game_sha256':GAME_SHA,
        'profile_actions':list(reader.ACTIONS),'profiles':profiles,
        'read_entry':'read_relation_pair(reader,base,action,actor_handle,target_handle,identity)',
        'evaluate_entry':'evaluate_relation_effect(action,before,after,receipt)',
        'root':{'country_embedded_offset':'0x14f8','vtable_rva':'0x1c4f5f8','marker':'0x165','owner_pointer_offset':'0x10',
                'record_begin_end_capacity_offsets':['0x18','0x20','0x28'],'record_stride':'0x48'},
        'index':{'bytes':24,'entry_stride':16,'vtable_qword':0,'data_qword':8,'signed_capacity_dword':16,
                 'signed_count_dword':20,'signed_counterpart_slot':0,'object_pointer':8,'maximum_used':256,'maximum_capacity':4096,
                 'typed_allocation_metadata_guarded':True,'actual_allocator_extent_or_world_lease_verified':False},
        'object':{'vtable':0,'marker':8,'first_complete_handle':'0x10','second_complete_handle':'0x18',
                  'start_signed_raw_date':'0x20','removed_zero':'0x28','shared_global_insert_failure_zero':'0x29',
                  'full_payload_repeated_read':True},
        'selected_effect':'Exact pair_absent_observed to current_relation_observed plus complete original status4 V31 receipt',
        'receipt':{'event':'request_result','status':4,'reason':'normal_dispatch_slot_consumed','adapter_calls':7,
                   'owned_issued':3,'transfer_outcome':1,'complete_identity_and_sequence_binding':True,
                   'audit_digest_required':True,'known_cleanup_complete_preserved_not_promoted':True},
        'global_membership':{'sampled':False,'verified':False,'scope':'current native bilateral indexed relation only'},
        'reply':{'pending_and_notification_decoding_supported':False,'AI_acceptance_verified':False,
                 'missing_relation_or_pending_disappearance_is_not_rejection':True},
        'runtime_flags':{'native_calls':0,'memory_written':False,'requests_published':0,'process_handle_opened':False,
                         'world_epoch_proven':False,'atomic_snapshot_proven':False,'production_execution_ready':False},
        'read_only_positive_recommendations':recommendations,'newly_decoded_bytes':16,
        'limitations':['Caller must supply an identity-verified read-only held port and trusted pre-dispatch baseline journal.',
                       'Two complete equal passes cannot prove an atomic snapshot, ABA exclusion or world lifetime lease.',
                       'Selected indexed relation changes do not establish exclusive request causality, global registration, complete lifecycle, save/reload or AI acceptance.',
                       'No historical dispatched/successful/unknown action is authorized to repeat.']}
    (OUT/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    paths=[*static['source_pins'],
        'bridge/relation_effect_reader.py','bridge/tests/test_relation_effect_reader.py',
        'bridge/tests/test_effect_observer_memory.py','bridge/diplomacy_effect_observer.py',
        'bridge/tag_command_backend.py','bridge/tag_actions_1375_v31.json','bridge/tag_action_conditions_1375.json',
        'bridge/diplomacy_research_evidence.json',
        'work/reports/diplomacy-corrective-20261014/current-action-validation.json',
        'work/reports/diplomacy-corrective-20261014-r3/runtime/batch-after-save-selected.json',
        'work/reports/diplomacy-corrective-20261014-r3/runtime/first-two-results.json',
        'bridge/native/tag_diplomacy_1375_v31/src/work/candidates/v24-pair-send-core-r2-1375/pair_send.h',
        'work/deps/capstone-5.0.7.receipt.json','work/discover_diplomacy.py',
        *(str((OUT/n).relative_to(ROOT)).replace('\\','/') for n in ('static.json','report.md','contract.json','prepare_static.py','verify.py','seal.py'))]
    pins={}
    for name in paths:
        data=(ROOT/name).read_bytes();pins[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        check_memory_budget()
    manifest={'schema':'EU4DIPLOMACY-RELATION-READER-MANIFEST/1','game_sha256':GAME_SHA,
              'native_manifest_sha256':hashlib.sha256(DEFAULT_MANIFEST.read_bytes()).hexdigest(),
              'source_pins':pins,'actions':list(reader.ACTIONS),'memory_guard_bytes':768*1024*1024,
              'newly_decoded_bytes':16,'maximum_newly_decoded_bytes':16384,'native_calls':0,'game_process_accessed':False}
    (ROOT/'bridge/relation_effect_reader_manifest_1375.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'source_pins':len(pins),'profiles':len(profiles),'positive_pair_recommendations':len(recommendations),
                      'newly_decoded_bytes':16,'peak_committed_bytes':check_memory_budget()}))


if __name__=='__main__':main()
