"""Append-only retained delivery of the already completed one-shot status.
No candidate imports, source-graph checker, CLI, tests or target reads.
"""
from pathlib import Path
import ctypes,hashlib,json,os
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIOR_RETURNED=1547859
PRIOR_REQUESTED=1547864
LIMIT=8388608
MANUAL_AND_SHELL_RESERVE=262144
events=[];written={};total=PRIOR_RETURNED
class Counters(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
def memory():
    c=Counters();c.cb=ctypes.sizeof(c)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(c),ctypes.sizeof(c))
    if c.PrivateUsage>=805306368 or c.PeakPagefileUsage>=1073741824:raise MemoryError('Self memory guard')
    return {'private_commit':c.PrivateUsage,'peak_commit':c.PeakPagefileUsage,'soft_limit':805306368,'stop_limit':1073741824,'hard_job_for_sealer':False}
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(name):
    global total
    p=HERE/name;s=p.stat().st_size
    if s>4194304 or total+s+1+MANUAL_AND_SHELL_RESERVE>LIMIT:raise ValueError('Retained pre-read budget')
    event={'path':p.relative_to(ROOT).as_posix(),'requested':s+1,'returned':0};events.append(event)
    with p.open('rb') as f:b=f.read(s+1)
    event['returned']=len(b);event.update(pin(b));total+=len(b)
    if len(b)!=s:raise ValueError('Retained size changed')
    memory()
    return b
def save(name,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
    if len(raw)>4194304:raise ValueError('Output bound')
    with (HERE/name).open('xb') as f:f.write(raw)
    v={'path':(HERE/name).relative_to(ROOT).as_posix(),**pin(raw)};written[name]=v
    return v
names=['run-authorization.json','actual-manifest.json','capture.json','child-io.json','receipt.json',
       'claim.json','child-claim.json','attempt-start.json','child-status-start.json','job.json',
       'source-before.json','source-after.json','stdout.txt','stderr.txt',
       'live-controller-shell.json','live-retained-preview-shell.json','complete_live_delivery.py']
raw={n:read(n) for n in names}
data={n:json.loads(raw[n]) for n in names if n.endswith('.json')}
cap=data['capture.json'];io=data['child-io.json'];r=data['receipt.json'];a=data['actual-manifest.json'];auth=data['run-authorization.json']
triples={n:{'path':(HERE/n).relative_to(ROOT).as_posix(),**pin(raw[n])} for n in names}
samples=cap.get('samples',[])
sample_raw=json.dumps(samples,ensure_ascii=True,sort_keys=True).encode('ascii')
sample_info={'count':len(samples),'two_pass_equal_claim':cap.get('selected_two_pass_equal'),'canonical_json_pin':pin(sample_raw)}
if len(sample_raw)<=32768:sample_info['retained_samples']=samples
else:sample_info['sample_top_keys']=[list(x) if type(x)is dict else type(x).__name__ for x in samples]
capture_info={k:cap.get(k) for k in ('schema','operation','status','selection','errors','selected_task_present','captured_utc',
  'normal_context_exit','held_handle_cleared','commit_after_context_exit','close_os_return_checked')}
capture_info.update(budget_accounting=cap.get('budget_accounting'),samples=sample_info,shared_raw_journal_count=len(cap.get('raw_ordered_read_journal',[])),
                   loaded_code_before=[{k:x.get(k) for k in ('rva','bytes','sha256')} for x in cap.get('code_before',[])],
                   loaded_code_after=[{k:x.get(k) for k in ('rva','bytes','sha256')} for x in cap.get('code_after',[])])
io_info={k:io.get(k) for k in ('explicit_returned','attempted_requested','read_attempts','open_refusals','game_successful_opens','game_opens',
 'text_config','source_prepost_equal','status_attempts','failure','exit_code','ordinary_routes_complete','scope')}
controller={'before_retained_seal_returned':r.get('controller_returned'),'including_controller_seal_returned':a.get('controller_returned_including_seal'),
            'limit':r.get('controller_returned_limit'),'attempted_requested_before_seal':r.get('controller_attempted_requested'),
            'including_seal_requested_from_retained_events':sum(x.get('requested',0) for x in a.get('controller_read_events',[])),
            'including_seal_event_count':len(a.get('controller_read_events',[]))}
flags={k:False for k in ('original_request_correlated','selected_effect_verified','request_effect_verified','AI_acceptance_verified',
 'final_heir_result_verified','native_ready','world_lease','atomic_snapshot','persistence_verified','close_os_return_checked',
 'complete_RPM_journal_claimed','known_normal_IO_closure','authorizes_retry','runtime_authorized_for_another_attempt')}
completion={
 'schema':'EU4-SUPPORT-HEIR-CURRENT-LIVE-COMPLETION/1','sealed':True,'author':'D',
 'authorization_pin':triples['run-authorization.json'],'subject_actual_manifest':triples['actual-manifest.json'],
 'subject_capture_pin':triples['capture.json'],'subject_child_io_pin':triples['child-io.json'],'subject_receipt_pin':triples['receipt.json'],
 'claims':{n:triples[n] for n in ('claim.json','child-claim.json','attempt-start.json','child-status-start.json')},
 'controller_reported':{k:r.get(k) for k in ('control_passed','status','current_state_observed','selected_task_present','status_attempts','maximum_status_attempts','source_prepost_equal','failure')},
 'capture_summary':capture_info,'explicit_io_summary':io_info,'controller_io':controller,'job':r.get('job'),
 'controller_shell':triples['live-controller-shell.json'],'all_execution_shells_collected':True,
 'controller_shell_exit_code':data['live-controller-shell.json'].get('exit_code'),
 'target_existing_game_not_assigned_to_job':True,
 'seal_scope':'Only already-retained local files; no checker, candidate import, CLI, tests, source-graph traversal or additional target read.',
 'limitations':[
  'Current selected FRA-POL support-task absence is not an original request outcome, AI response, final heir result or effect.',
  'Entry PE8192 is the frozen source declaration (one call), separate from shared attempted RPM; it is not an actual raw journal record and is not added as complete measured RPM.',
  'normal_context_exit/held_handle_cleared are the capture claims; OS CloseHandle return remains unverified.',
  'IO ledgers cover intercepted explicit Python routes; no full OS/import/cache/delegated IO, lease, atomicity or type-lifetime proof.',
  'Runtime source guards and captured bytes are producer evidence pending independent retained replay; this append-only delivery does not rerun a verifier.',
  'The first retained preview had overbroad stdout selection and tool-output truncation, exit0; raw artifacts remain complete and untouched. Its exact file-read bytes are included; no runtime retry.',
  'Source/build, child ordinary, fixed host, game-disk, controller and retained publication budgets are separate; no aggregate represents full OS I/O.'
 ],
 'accounting':{
   'source_build_previous_upper_witness':5419256,'source_build_limit':33554432,
   'prior_retained_preview_returned':PRIOR_RETURNED,'prior_retained_preview_requested':PRIOR_REQUESTED,
   'this_sealer_returned':sum(e['returned'] for e in events),'this_sealer_requested':sum(e['requested'] for e in events),
   'retained_cumulative_returned':total,'manual_and_final_shell_allowance':MANUAL_AND_SHELL_RESERVE,
   'retained_cumulative_upper':total+MANUAL_AND_SHELL_RESERVE,'retained_limit':LIMIT,
   'source_build_plus_controller_plus_retained_upper_excludes_child':5419256+a.get('controller_returned_including_seal',0)+total+MANUAL_AND_SHELL_RESERVE,
   'read_events':events,'memory':memory()
 },
 'authority':flags,'native_game_calls':0,'requests_published':0,'game_fields_written':0,'status_attempts_this_profile':1,
 'additional_status_attempts_after_sole_controller':0,'additional_tests_or_checkers_run':0,'independent_live_replay_pending':True
}
cp=save('live-completion.json',completion)
delivery={
 'schema':'EU4-SUPPORT-HEIR-CURRENT-LIVE-APPEND-ONLY-DELIVERY/1','sealed':True,
 'completion':cp,'selected_retained_file_pins':triples,'result':r.get('status'),'control_passed':r.get('control_passed'),
 'status_attempts':r.get('status_attempts'),'all_execution_shells_collected':True,
 'frozen_actual_manifest_not_modified':True,'all_original_sources_unchanged_by_sealer':True,
 'retained_returned':total,'retained_upper_including_manual_and_final_shell':total+MANUAL_AND_SHELL_RESERVE,
 'retained_limit':LIMIT,'authority':flags,'independent_live_replay_pending':True,
 'final_shell_sidecar_will_only_record_this_script_completion':True
}
dp=save('live-delivery.json',delivery)
print(json.dumps({'completion':cp,'delivery':dp,'selected_pins':{n:triples[n] for n in ('actual-manifest.json','capture.json','child-io.json','receipt.json','claim.json','child-claim.json')},
 'status':r.get('status'),'errors':cap.get('errors'),'sample_count':len(samples),'budget_accounting':cap.get('budget_accounting'),
 'explicit_returned':io.get('explicit_returned'),'attempted_requested':io.get('attempted_requested'),'read_attempts':io.get('read_attempts'),
 'game_successful_opens':io.get('game_successful_opens'),'config_snapshots':io.get('text_config',{}).get('opened_snapshots'),
 'controller_io':controller,'retained_returned':total,'retained_upper':total+MANUAL_AND_SHELL_RESERVE,'memory':memory()},ensure_ascii=True))

