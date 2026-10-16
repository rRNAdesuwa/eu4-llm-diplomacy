"""Offline preservation of exactly the stopped 55580 partial second batch.

Reads fixed files only. Never launches a CLI, opens a process, calls native code,
retries an operation, or promotes a partial batch to a completed/effect result.
"""
import argparse,collections,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from work.native import lab_protocol_v17_1375 as lab
PID=55580;CREATION='01dd56c88c83e81a';THREAD=24672;WORLD='0x27c9a889070'
PLAYER='0x0100007a00415246';EXIT_TIME=134359002654451230
RUN='batch-55580-20261008-batch36-b'
SPEEDS=(8,11,14,17)
PAIRS=((2,3,'royal_marriage','NAV'),(4,5,'offer_alliance','POR'),(6,7,'improve_relations','FOI'),
       (9,10,'guarantee','POR'),(12,13,'give_subsidies','POR'),(15,16,'ask_military_access','POR'))
FULL_SHA='99dc9e1593b02195c3f2a5d607f19c562c2d3bb0e100dee7befe354957b9d4f4'
MANIFEST_SHA='b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d'

def require(ok,text):
 if not ok:raise ValueError(text)
def same(a,b,text):require(canonical(a)==canonical(b),text)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def typed_eq(value,expected,text):require(type(value) is type(expected) and value==expected,text)
def raw(path,limit=4*1024*1024):return lab.read_bounded(path,limit)
def load(path,limit=4*1024*1024):return lab.decode_json(raw(path,limit).decode('utf-8'))
def desc(path):
 blob=raw(path);return {'path':path.relative_to(ROOT).as_posix(),'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}
def create(path,value):
 with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')
def bools(x,expected):
 for k,v in expected.items():typed_eq(x[k],v,k)
def parse_lines(path,maximum=4096):
 result=[];size=path.stat().st_size;require(0<size<=4*1024*1024,'JSONL file bound')
 with path.open('rb') as f:
  while line:=f.readline(lab.MAX_LINE+1):
   require(line.endswith(b'\n') and len(line)<=lab.MAX_LINE and len(result)<maximum,'JSONL line/count bound')
   result.append(lab.decode_json(line.decode('utf-8')))
 return result
def frame_contract(x):
 fixed={'pid':PID,'process_creation_filetime':CREATION,'thread':THREAD,'world_cookie':WORLD,'player_handle':PLAYER,
        'world_ready':True,'thread_changed':False,'world_changed':False,'session_frozen':False,
        'acceptance_flag':0,'acceptance_state':'closed','acceptance_origin_sequence':0,'acceptance_submit_sequence':0,
        'acceptance_off_sequence':0,'acceptance_action':'none','acceptance_target':'none'}
 for k,v in fixed.items():typed_eq(x[k],v,'frame '+k)
 for key in ('paused','lease_active','mailbox_ready','running_speed_enabled','send_enabled','lifecycle_passed','owned_peace_tested','owned_peace_passed','preview_passed','command_passed'):
  require(type(x[key]) is bool,'frame bool '+key)
 for key,lo,hi in [('raw_date',56456976,56457192),('last_sequence',0,17),('native_speed_index',0,4),('frames',1,2**31-1),('uptime_ms',1,2**64-1),('lease_deadline_uptime_ms',0,2**64-1)]:
  require(type(x[key]) is int and lo<=x[key]<=hi,'frame integer '+key)
 require(x['native_speed_index'] in (0,4),'unexpected speed index')
def speed_core(x,speed,date,begin=False):
 keys='event thread_id requested_speed reason before_date before_native_index before_paused write_entered callback_returned callback_success result_destroyed readback_observed after_date after_native_index after_paused readback_matches exception_code freeze_session retry_allowed diplomacy_submitted'
 require(set(x)==set(keys.split()),'speed core exact keys')
 for k,v in {'event':'test_speed_begin' if begin else 'test_speed_complete','thread_id':THREAD,'requested_speed':speed,'reason':0,'before_date':date,'before_native_index':0 if speed==5 else 4,'exception_code':0}.items():typed_eq(x[k],v,'speed '+k)
 require(type(x['before_paused']) is bool,'speed before paused type')
 if speed==5:typed_eq(x['before_paused'],True,'running begins paused')
 bools(x,{k:not begin for k in ('write_entered','callback_returned','callback_success','result_destroyed','readback_observed','readback_matches')})
 bools(x,{'freeze_session':False,'retry_allowed':False,'diplomacy_submitted':False})
 for k,v in {'after_date':0 if begin else date,'after_native_index':0 if begin or speed==0 else 4,'after_paused':False if begin else speed==0}.items():typed_eq(x[k],v,'speed result '+k)
def checked_path(value):
 require(type(value) is str,'artifact path type');p=(ROOT/value).resolve()
 require(p.is_relative_to(lab.OUTPUT.resolve()) and p.is_file() and not p.is_symlink(),'artifact path escaped');return p

def review():
 require(lab.ROOT==ROOT and lab.OUTPUT==ROOT/'work/runtime/native1375-v17','formal frozen reader provenance')
 session=lab.OUTPUT/f'session-{PID}-{CREATION}';run=lab.OUTPUT/RUN
 # The stopped input ledger covers this exact session/run, not new concurrent runs.
 paths=set(session.iterdir())|set(run.iterdir())
 paths.update([lab.OUTPUT/'exit-observation-55580.json',lab.OUTPUT/'batch-terminal-status-55580.json',
  lab.OUTPUT/f'{RUN}-initial-census.json',lab.OUTPUT/'batch-plan-55580-b.json',lab.OUTPUT/'preflight-case-55580/preflight-summary.json',
  lab.OUTPUT/'build.json',ROOT/'work/record_v17b_batch_terminal_1375.py',ROOT/'work/runtime/native1375-v17/batch-terminal-preserved-63500.json',Path(__file__)])
 journal=parse_lines(run/'journal.jsonl',512)
 for row in journal:
  if row['event'] in ('status_snapshot','publisher_capture'):
   p=checked_path(row['path']);require(desc(p)['sha256']==row['sha256'],'journal artifact hash');paths.add(p)
  if row['event']=='cli_start_once':paths.add(checked_path(row['capture']))
 manifest=load(lab.OUTPUT/'build.json');require(desc(lab.OUTPUT/'build.json')['sha256']==MANIFEST_SHA,'frozen manifest')
 # Only host sources used by the frozen reader are rechecked, no build/process API.
 for name,expected in manifest['host_source_sha256'].items():
  p=ROOT/name;require(desc(p)['sha256']==expected.lower(),'frozen host input');paths.add(p)
 paths=sorted(paths,key=lambda p:p.as_posix());require(len(paths)<=256 and all(p.is_file() and not p.is_symlink() for p in paths),'inventory bound/type')
 inventory_before=[desc(p) for p in paths];require(sum(p['bytes'] for p in inventory_before)<=32*1024*1024,'aggregate input budget')
 exited=load(lab.OUTPUT/'exit-observation-55580.json',65536)
 for k,v in {'pid':PID,'creation':CREATION,'process_creation_filetime':int(CREATION,16),'process_exit_filetime':EXIT_TIME,'exit_observed':True,'exit_code':0,'before_exit_filetime':0,'process_stop_requested_by_observer':False,'read_only':True}.items():typed_eq(exited[k],v,'exit '+k)
 require(exited['method']=='held_handle_wait_and_getprocesstimes','exit evidence method')
 meta=lab.read_session_metadata(session,PID,CREATION);typed_eq(meta['window_thread'],THREAD,'session thread')
 e=lab.read_evidence(session,meta);typed_eq(e['last_sequence'],17,'strict final sequence');require(set(e['requests'])==set(range(1,18)),'complete strict-next sequence set')
 require(e['requests'][1]['request']['operation']=='fixture' and e['requests'][1]['request']['action']=='fixture_on','sequence1 fixed fixture')
 bools(e,{'pending':False,'lease_pending':False,'input_wait_pending':False});require(e['log_sha256']==FULL_SHA and e['log_bytes']==1582824,'stopped native log hash/size')
 require(all(v is True for v in e['phases'].values()) and set(e['phases'])=={'lifecycle','owned_peace','preview','command'},'four phase proof')
 require(e['phase_proofs']['preview']['case_count']==72 and e['phase_proofs']['command']['case_count']==72 and e['phase_proofs']['owned_peace']['core_record_count']==9,'phase counts')
 summary=load(run/'summary.json',65536);typed_eq(summary['state'],'terminal','batch state');typed_eq(summary['failure'],'Speed handler/cleanup/date proof differs','original failure preserved')
 for k,v in {'native_dispatch_count':6,'legality_attempt_count':6,'next_sequence':17,'automatic_retry':False,'individual_effect_verified':False,'production_backend_registered':False,'strict_single_player_verified':False,'world_epoch_verified':False}.items():typed_eq(summary[k],v,'summary '+k)
 same(summary['still_running_helper_pids'],[],'host reports no outstanding helpers');require(len(summary['rows'])==12 and len(summary['observations'])==1,'partial row/observation count')
 same(summary['observations'],[{'boundary':'initial','sha256':desc(lab.OUTPUT/f'{RUN}-initial-census.json')['sha256']}],'initial census only')
 require(not (lab.OUTPUT/f'{RUN}-final-census.json').exists(),'unexpected final census')
 scope=load(run/'scope.json',65536);same(scope['plan'],load(lab.OUTPUT/'batch-plan-55580-b.json',65536),'fixed plan binding');require(len(scope['plan']['rows'])==36 and scope['plan']['first_sequence']==2,'fixed 36 plan')
 same(journal[0]['scope'],scope,'opened scope');same(journal[-1],{'event':'batch_finished','summary':summary},'durable terminal summary')
 terminals=[x for x in journal if x['event']=='batch_terminal'];require(len(terminals)==1 and terminals[0]['reason']==summary['failure'] and terminals[0]['automatic_retry'] is False,'one terminal event')
 starts=[x for x in journal if x['event']=='cli_start_once'];intents={x['command_id']:x['command'] for x in journal if x['event']=='resolved_intent'}
 require(len(starts)==16 and len(intents)==17 and len({x['command_id'] for x in starts})==16,'one CLI start per native request, no resume')
 for ident,command in intents.items():require(hashlib.sha256(canonical(command).encode()).hexdigest()==ident,'durable intent id')
 completed=[x for x in journal if x['event']=='completed'];require(len(completed)==16 and all(x['individual_effect_verified'] is False for x in completed),'completed journal count/effect boundary')
 pair_records=[]
 for row_index,(legal,submit,action,target) in enumerate(PAIRS):
  same(scope['plan']['rows'][row_index],{'action':action,'target':target},'six fixed rows')
  for seq,mode in ((legal,'legality_only'),(submit,'submit')):
   item=e['requests'][seq];request=item['request'];core=item['records'][-1];host=item['complete'];sending=mode=='submit'
   for k,v in {'operation':'pair','actor':'FRA','action':action,'target':target,'mode':mode,'pid':PID,'creation':CREATION,'sequence':seq}.items():typed_eq(request[k],v,'pair request '+k)
   same([x['event'] for x in item['records']],['pair_engine_begin']+(['pair_engine_dispatch_intent'] if sending else [])+['pair_engine_complete'],'pair record boundaries')
   for x in item['records']:
    bools(x,{'freeze_session':False,'ownership_uncertain':False,'retry_allowed':False,'applied_verified':False});typed_eq(x['exception'],0,'pair exception')
   bools(core,{'preview_called':True,'preview_allowed':True,'gate_called':True,'gate_allowed':True,'original_destroyed':True,'submit_entered':sending,'submit_returned':sending,'command_destroyed_before_dispatch':not sending})
   for k in ('context_submit_return','caller_container_consumed'):typed_eq(core[k],True if sending else None,'pair ownership '+k)
   typed_eq(core['status'],2 if sending else 1,'pair status');typed_eq(core['reason'],0,'pair reason');typed_eq(host['audit_complete'],True,'pair audit')
   row=next(x for x in summary['rows'] if x['sequence']==seq)
   same(row,{'action':action,'target':target,'mode':mode,'sequence':seq,'status':core['status'],'reason':0,'outcome':'dispatched_not_effect_verified' if sending else 'legality_allowed','individual_effect_verified':False},'summary selected pair')
   jf=next(x for x in completed if x['evidence'].get('sequence')==seq);receipt=jf['evidence']
   for key in ('status','reason','submit_entered','submit_returned','context_submit_return','caller_container_consumed','ownership_uncertain','preview_called','preview_allowed','gate_called','gate_allowed','exception','raw_date'):
    same(receipt[key],core[key],'journal/native pair '+key)
   pair_records.append({**row,'raw_date':core['raw_date'],'audit_complete':True,'native_ownership_known':True})
 # Parse fixed native bytes once to bind both status snapshots to exact historical
 # prefixes and retain the automatic pause cores omitted by read_evidence.
 status25=load(run/'status-0025.json');terminal=load(lab.OUTPUT/'batch-terminal-status-55580.json',65536)
 bools(terminal,{'automatic_retry':False,'applied_verified':False});typed_eq(terminal['exit_code'],0,'terminal capture exit');require(terminal['stderr']=='','terminal capture stderr')
 same(terminal['arguments'],['--pid',str(PID),'--creation',CREATION,'status','--sequence','17'],'terminal exact argv')
 final=terminal['report'];require(final['pid']==PID and final['creation']==CREATION and final['manifest_sha256']==MANIFEST_SHA,'terminal report identity')
 for obj in (status25,status25['live_before'],status25['live_after']):
  typed_eq(obj['pid'],PID,'status25 pid');typed_eq(obj['creation'],CREATION,'status25 creation')
 same(status25['live_before'],status25['live_after'],'status25 RO identity stable');same(status25['pause_before'],status25['pause_after'],'status25 pause stable')
 same(status25['evidence']['requests'],{str(k):v for k,v in e['requests'].items()},'status25 entire request set')
 same(final['request'],e['requests'][17],'terminal sequence17 exact record')
 for obj in (final,status25['evidence']):bools(obj,{'pending':False,'lease_pending':False});typed_eq(obj['last_sequence'],17,'status last sequence')
 wanted={status25['evidence']['log_sha256']:'status25',final['log_sha256']:'terminal'};prefixes={};pausecores={};leases={};counts=collections.Counter();last=None;h=hashlib.sha256();offset=0;claimed=0;pending=False;lease=False;last_complete=0
 logpath=session/'research-1375.jsonl'
 with logpath.open('rb') as f:
  while line:=f.readline(lab.MAX_LINE+1):
   require(line.endswith(b'\n') and len(line)<=lab.MAX_LINE,'native log bounded line');x=lab.decode_json(line.decode());counts[x['event']]+=1;offset+=len(line);h.update(line)
   name=x['event']
   if name=='research_frame':last=x;frame_contract(x)
   elif name=='lab_request_claimed':claimed=x['sequence'];pending=True
   elif name=='lab_request_complete':pending=False;last_complete=x['sequence']
   elif name=='lab_lease_armed':lease=True;leases[x['sequence']]=x
   elif name=='lab_lease_complete':lease=False
   elif name=='lab_native_record' and x['lease_pause'] is True:pausecores.setdefault(x['sequence'],[]).append(x['record'])
   if h.hexdigest() in wanted:
    key=wanted[h.hexdigest()];source=status25['evidence'] if key=='status25' else final
    require(key not in prefixes,'duplicate prefix hash');same(source['latest_frame'],last,'status exact prefix latest frame');require(claimed==last_complete==17 and pending is False and lease is False,'status prefix complete boundary')
    if key=='status25':typed_eq(source['log_bytes'],offset,'status25 exact prefix length')
    prefixes[key]={'bytes':offset,'sha256':h.hexdigest(),'last_sequence':claimed,'last_frame_sequence':last['last_sequence'],'last_frame_raw_date':last['raw_date']}
 require(set(prefixes)=={'status25','terminal'} and offset==e['log_bytes'] and h.hexdigest()==FULL_SHA,'both prefixes exist inside full stopped log')
 same(last,e['latest_frame'],'stopped last frame');frame_contract(last);bools(last,{'paused':True,'lease_active':False,'mailbox_ready':True});typed_eq(last['last_sequence'],17,'stopped frame sequence');typed_eq(last['raw_date'],56457192,'stopped frame date');typed_eq(last['native_speed_index'],0,'stopped paused native index')
 require(counts['pair_lifecycle']==20 and counts['pair_preview_case']==72 and counts['pair_command_case']==72 and counts['owned_peace_core_record']==9,'20/1/72/72 direct phase count')
 require(counts['lab_request_claimed']==counts['lab_request_complete']==17 and counts['lab_lease_complete']==4,'native complete counts')
 require(counts['lab_session_frozen']==counts['lab_host_exception']==counts['lab_input_failed']==0,'no native fault event')
 speed_rows=[]
 for index,seq in enumerate(SPEEDS):
  item=e['requests'][seq];initial=56456976+48*index;pause=initial+48;require(item['request']['operation']=='speed' and item['request']['speed']==5,'four speed requests');require(len(item['records'])==2 and len(pausecores[seq])==2,'two normal speed audit pairs')
  speed_core(item['records'][0],5,initial,True);speed_core(item['records'][1],5,initial)
  speed_core(pausecores[seq][0],0,pause,True);speed_core(pausecores[seq][1],0,pause)
  same(status25['lease_completions'][str(seq)],pausecores[seq][1],'status25 original pause core')
  supervisor=parse_lines(session/f'{seq:020}.supervisor.jsonl',2);require(len(supervisor)==2,'supervisor exact two events');armed,finished=supervisor
  for obj in supervisor:
   for k,v in {'pid':PID,'creation':CREATION,'sequence':seq,'speed':5,'retry_allowed':False}.items():typed_eq(obj[k],v,'supervisor '+k)
  require(armed['event']=='supervisor_armed' and finished['event']=='supervisor_complete','supervisor state order');require(type(armed['deadline_seconds']) in (int,float) and armed['deadline_seconds']==12.0,'supervisor bounded deadline')
  require(type(finished['elapsed_seconds']) in (int,float) and 0<=finished['elapsed_seconds']<12,'supervisor elapsed bound')
  same(finished['native_lease_complete'],item['lease_complete'],'supervisor/native pause completion');before=armed['before'];after=finished['after'];typed_eq(before['raw_date'],initial,'supervisor initial date');typed_eq(after['raw_date'],pause if seq!=17 else pause+24,'supervisor final observed date')
  for key in ('game','pause_manager','player','server'):same(before[key],after[key],'supervisor world identity '+key)
  typed_eq(after['game'],int(WORLD,16),'supervisor world');typed_eq(after['player'],int(PLAYER,16),'supervisor player');bools(after,{'paused':True});typed_eq(after['native_speed_index'],0,'supervisor speed')
  cap=load(lab.OUTPUT/f'{RUN}-{seq}-speed.json',65536);typed_eq(cap['exit_code'],0,'speed publisher capture');same(cap['report']['after_date'],after['raw_date'],'capture supervisor date')
  require(cap['report']['status']=='completed_and_paused','speed capture status')
  speed_rows.append({'sequence':seq,'initial_raw_date':initial,'pause_core_raw_date':pause,'supervisor_final_raw_date':after['raw_date'],'supervisor_after_pause_delta':after['raw_date']-pause,'native_controls_normal':True,'native_lease_closed':True,'batch_driver_accepted':seq!=17})
 # Each command is an explicitly owned one-shot argv; no terminal reopening.
 for start in starts:
  command=intents[start['command_id']];seq=command['sequence'];request=e['requests'][seq]['request'];capture=load(checked_path(start['capture']),65536)
  require(start['argv'][:3]==[sys.executable,'-B','work/run_lab_step_v17_1375.py'],'fixed CLI command')
  require(start['argv'][3]=='--output' and checked_path(start['argv'][4])==checked_path(start['capture']),'CLI capture ownership')
  same(start['argv'][6:],capture['arguments'],'captured exact CLI arguments');require(start['argv'][5]==capture['kind'],'capture kind')
  typed_eq(capture['exit_code'],0,'capture exit');bools(capture,{'automatic_retry':False,'applied_verified':False})
  for key in ('action','actor','target','mode'):
   if command['kind']=='pair':same(command[key],request[key],'intent/native '+key)
  require(command['pid']==PID and command['creation']==CREATION and command['world_cookie']==WORLD,'command world scope')
 terminal_index=next(i for i,x in enumerate(journal) if x['event']=='batch_terminal');require(all(x['event']=='batch_finished' for x in journal[terminal_index+1:]),'no late result reopened driver')
 require(not any(p.suffix=='.request' for p in session.iterdir()),'no pending request files')
 inventory_after=[desc(p) for p in paths];same(inventory_after,inventory_before,'inputs changed during review')
 return {'schema_version':1,'purpose':'stopped_partial_v17_second_fixed36_batch','pid':PID,'creation':CREATION,
  'status':'terminal_partial_6_of_36','batch_complete':False,'completed_action_rows':6,'pair_request_count':12,'legality_attempt_count':6,'native_dispatch_count':6,
  'complete_sequence_count':17,'last_sequence':17,'fixture_request_count':1,'speed_request_count':4,'preflight_counts':{'lifecycle':20,'default_owned_peace_lifecycle':1,'preview':72,'command':72},
  'stopped_log_bytes':e['log_bytes'],'stopped_log_sha256':e['log_sha256'],'historical_status_prefixes':prefixes,'native_event_counts':dict(counts),
  'failure_original':summary['failure'],'failure_evidence':'Sequence17 native pause core date56457168 differs from supervisor/live paused date56457192; host rejected its stricter equality contract.',
  'date_difference_mechanism_proved':False,'speed_records':speed_rows,'pair_records':pair_records,'latest_stopped_frame':last,
  'normal_exit_observation':exited,'normal_ui_exit_reported_by_root':True,'process_accessed_by_reviewer':False,
  'late_known_result_reopened_batch':False,'automatic_retry':False,'native_session_frozen':False,'pending_request':False,'lease_pending':False,'final_census_present':False,
  'individual_effect_verified':False,'positive_effects_before_cancellation':'unobserved','capability_promoted':False,'production_ready':False,
  'strict_single_player_verified':False,'world_epoch_verified':False,'summary_original':summary,'artifacts':inventory_after}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 result=review();output=lab.OUTPUT/'batch-terminal-preserved-55580.json'
 if args.check:same(load(output),result,'preserved report repeatability')
 else:create(output,result)
 print(json.dumps({'output':str(output),'sha256':desc(output)['sha256'],'check':args.check,'batch_complete':False,'completed_rows':6,'stopped_log_sha256':FULL_SHA,'all_shells_in_this_helper_synchronous':True}))
if __name__=='__main__':main()
