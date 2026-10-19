"""File-only selected initial/final facts and honest operator observations."""
from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'work/runtime'
PID, CREATION = 60864, '01dd5714af7e8580'
FAMILIES = ('corrupt_officials', 'sabotage_reputation', 'sow_discontent',
            'slander_merchants', 'sabotage_recruitment')

def read(name, limit=1048576):
    with (RUNTIME/name).open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw)>limit:
        raise ValueError('Input budget')
    return json.loads(raw), dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def write(name, value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode('ascii')
    with (RUNTIME/name).open('xb') as stream:
        if stream.write(raw)!=len(raw):
            raise ValueError('Short write')
        stream.flush();os.fsync(stream.fileno())
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    initial,ip=read('v19-spy5-census-initial-60864.json')
    final,fp=read('v19-spy5-census-final-60864.json')
    exited,ep=read('v19-send-exit-60864.json',8192)
    assert ip['sha256']=='82e0c163d57096b4f596ace088074ba9a3251dccef074311fbfd084e8baa260c'
    assert fp['sha256']=='f313b3bdd4de4546abc56e87125ffd9228fffd5c610b4821f6fb3861b9994d40'
    for data,phase in ((initial,'initial'),(final,'final')):
        assert (data['pid'],data['creation'],data['phase'],data['family_order'])==(PID,CREATION,phase,list(FAMILIES))
        assert data['native_called'] is False and data['game_written'] is False
    assert initial['selected_identity']==final['selected_identity']
    assert initial['paused_observations']==final['paused_observations']
    assert exited['pid']==PID and exited['creation']==CREATION
    assert exited['exit_observed'] is True and exited['exit_code']==0 and exited['wait_status']==0
    rows=[]
    for family in FAMILIES:
        before=initial['family_reports'][family]
        after=final['family_reports'][family]
        bs=before['before']['snapshot'];fs=after['before']['snapshot']
        bm=before['before']['selected'];fm=after['before']['selected']
        assert before['full_envelope_equal'] is True and after['full_envelope_equal'] is True
        assert len(bm['matching'])==0 and len(fm['matching'])==1
        assert bm['unknown_objects_or_selected_semantics'] is False and fm['unknown_objects_or_selected_semantics'] is False
        assert fm['matching'][0]['active_by_expiry_comparison'] is True
        assert fm['matching'][0]['expiry']==fs['cost']['expected_expiry']
        assert bs['identity']==fs['identity']
        assert before['dense']['final_milli_candidate']==after['dense']['final_milli_candidate']
        rows.append(dict(family=family,initial_selected_matching=bm['matching'],
                         final_selected_matching=fm['matching'],
                         initial_network_centipoints=bs['cost']['network_centipoints'],
                         final_network_centipoints=fs['cost']['network_centipoints'],
                         cost_milli_candidate=after['dense']['final_milli_candidate'],
                         duration_days=fs['cost']['duration_days'],
                         per_action_cost_verified=False,request_causality_verified=False))
    assert {r['initial_network_centipoints'] for r in rows}=={10000}
    assert {r['final_network_centipoints'] for r in rows}=={2125}
    cost=sum(r['cost_milli_candidate'] for r in rows)
    record=dict(kind='v19_selected_initial_final_comparison',pid=PID,creation=CREATION,
                sources=dict(initial=ip,final=fp,exit=ep),selected_identity_equal=True,
                selected_pause_roots_date_equal=True,group_atomic=False,
                rows=rows,network_delta_centipoints=7875,cost_sum_milli_candidate=cost,
                aggregate_arithmetic_corresponds=(7875*10==cost),
                native_receipt_complete_validated=False,
                native_receipt_parser_failure_preserved=True,
                selected_state_observed=True,request_causality_verified=False,
                per_action_cost_verified=False,strict_sp_verified=False,
                world_epoch_verified=False,production_ready=False,
                process_accessed=False,new_census_taken=False)
    result={}
    result['comparison']=write('v19-selected-comparison-60864.json',record)
    result['ui']=write('v19-stopped-ui-60864.json',dict(
        kind='root_operator_ui_observations',pid=PID,creation=CREATION,
        tool='computer-use sky',final_census_preceded_prompt_closure=True,
        five_post_batch_result_prompts_observed=list(FAMILIES),
        each_prompt_closed_once=True,date_observed='1444.11.11',paused_observed=True,
        normal_menu_quit_clicked=True,quit_confirmation_clicked=True,
        held_normal_exit_verified=True,exit_record=ep,
        screenshot_payloads_not_archived=True,game_save_created=False,
        native_request_retried=False,production_ready=False))
    result['failure']=write('v19-original-complete-parser-failure-60864.json',dict(
        kind='original_root_complete_parser_attempt_failed',pid=PID,creation=CREATION,
        command='python -I -B work/read_v19_session_receipt_1375.py --pid 60864 --creation 01dd5714af7e8580 --complete --output work/runtime/v19-receipt-complete-60864.json',
        exit_code=1,error_class='ValueError',error_message='integer range/type',
        location='sealed interval.py:34, integer(frame,self.frame+1,self.frame+1)',
        original_stderr_was_tool_console_only=True,complete_output_created=False,
        old_parser_or_runtime_sources_modified=False,native_resend=False,
        independent_reproduction='work/review-results/v19-journal-frame-failure-native-inventory-20261008a/failure.json',
        corrected_complete_validation_pending=True))
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    main()
