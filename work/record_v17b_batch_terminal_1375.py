"""Preserve stopped partial batch without a completed-batch or effect claim."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from work.native import lab_protocol_v17_1375 as lab
PID,CREATION=63500,'01dd56c21f9b7c9d'


def desc(path,maximum=4*1024*1024):
 raw=lab.read_bounded(path,maximum)
 return {'path':path.relative_to(ROOT).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def main():
 session=lab.OUTPUT/f'session-{PID}-{CREATION}'
 run=lab.OUTPUT/'batch-63500-20261008-batch36-a'
 exit_path=lab.OUTPUT/'exit-observation-63500.json'
 exited=json.loads(lab.read_bounded(exit_path,65536))
 assert exited['pid']==PID and exited['creation']==CREATION and exited['exit_observed'] is True and exited['exit_code']==0
 meta=lab.read_session_metadata(session,PID,CREATION);e=lab.read_evidence(session,meta)
 assert e['last_sequence']==8 and set(e['requests'])==set(range(1,9))
 assert e['pending'] is False and e['lease_pending'] is False and e['latest_frame']['session_frozen'] is False
 summary=json.loads(lab.read_bounded(run/'summary.json',65536))
 assert summary['state']=='terminal' and summary['native_dispatch_count']==3 and summary['legality_attempt_count']==3
 assert summary['failure']=='Read-only frozen status worker failed' and len(summary['observations'])==1
 assert summary['observations'][0]['boundary']=='initial' and summary['individual_effect_verified'] is False
 for entry in e['requests'].values():
  assert entry['complete'] is not None
  assert all(r.get('freeze_session',False) is False and r.get('ownership_uncertain',False) is False and r.get('exception',0)==0 for r in entry['records'])
 speed=e['requests'][8]
 assert speed['request']['operation']=='speed' and 'lease_complete' in speed
 assert e['latest_frame']['paused'] is True and e['latest_frame']['raw_date']==56457024
 initial=lab.OUTPUT/'batch-63500-20261008-batch36-a-initial-census.json'
 assert desc(initial)['sha256']==summary['observations'][0]['sha256']
 preflight=lab.OUTPUT/'preflight-case-63500/preflight-summary.json'
 assert desc(preflight)['sha256']=='34590412484c4c2f148df04d3e13c06c149f9cb3cb24e4e102d7ea09d734f64a'
 paths=[*sorted(session.iterdir()),*sorted(run.iterdir()),exit_path,initial,preflight,lab.OUTPUT/'batch-plan-63500-a.json',lab.OUTPUT/'batch-63500-20261008-batch36-a-8-speed.json',lab.OUTPUT/'batch-terminal-status-63500.json']
 assert len(paths)<=128
 inventory=[desc(p) for p in paths]
 report={'schema_version':1,'purpose':'stopped_partial_v17_fixed36_batch','pid':PID,'creation':CREATION,
         'status':'terminal_partial_3_of_36','preflight_passed':True,'batch_complete':False,
         'native_dispatch_count':3,'complete_sequence_count':8,'last_sequence':8,
         'stopped_log_bytes':e['log_bytes'],'stopped_log_sha256':e['log_sha256'],
         'failure':'Read-only status worker saw an older paused heartbeat and newer paused live date',
         'native_speed_completed_and_paused':True,'late_known_result_reopened_batch':False,
         'normal_ui_exit_observed':True,'automatic_retry':False,'final_census_present':False,
         'individual_effect_verified':False,'capability_promoted':False,'production_ready':False,
         'artifacts':inventory,'latest_frame':e['latest_frame']}
 assert inventory==[desc(p) for p in paths]
 output=lab.OUTPUT/'batch-terminal-preserved-63500.json'
 with output.open('x',encoding='utf-8',newline='\n') as dst:json.dump(report,dst,indent=2);dst.write('\n')
 print(json.dumps({'output':str(output),'sha256':desc(output)['sha256'],'stopped_log_bytes':e['log_bytes'],'stopped_log_sha256':e['log_sha256'],'batch_complete':False}))


if __name__=='__main__':main()
