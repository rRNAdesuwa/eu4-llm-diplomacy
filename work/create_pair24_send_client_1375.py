"""Create private fixed six send client with strict ownership-aware audit."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v23-pair-private-client-r2-1375'
HERE=ROOT/'work/candidates/v24-pair-send-private-client-1375'
manifest=ROOT/'work/candidates/v24-pair-send-bootstrap-1375/development-attempt1/build/build.json'
M=hashlib.sha256(manifest.read_bytes()).hexdigest()
index=json.loads((OLD/'source-index.json').read_bytes())
assert all(dict(bytes=(OLD/k).stat().st_size,sha256=hashlib.sha256((OLD/k).read_bytes()).hexdigest())==v for k,v in index.items())
HERE.mkdir(exist_ok=False)
for name in index:
 original=(OLD/name).read_bytes();data=original.decode('ascii')
 data=data.replace('v23-pair-nosend-bootstrap','v24-pair-send-bootstrap').replace('pair23','pair24').replace('_v23','_v24').replace('V23','V24')
 data=data.replace('restricted_pair_nosend','restricted_pair_send').replace('EU4PAIRNOSEND/1','EU4PAIRSEND/1').replace('EU4PAIRBOOT/1','EU4PAIRSENDBOOT/1').replace('EU4PAIR/1','EU4PAIRSEND/1')
 data=data.replace('no_send=1','send=1').replace('no_send=True','no_send=False')
 if name=='client.py':
  data=data.replace('import argparse,ctypes as C,hashlib,json,os,re,secrets,sys,types','import argparse,ctypes as C,hashlib,json,os,re,secrets,sys,types,time')
  data=re.sub(r"MANIFEST_SHA='[0-9a-f]{64}'","MANIFEST_SHA='"+M+"'",data)
  data=data.replace("m['no_send'] is True","m['no_send'] is False").replace("len(m['source_pins'])<=256","len(m['source_pins'])<=512")
  data=data.replace('Fixed no-send build','Fixed private send build')
  start=data.index('def inspect(id):');end=data.index('\ndef loaded(',start)
  inspect=r'''def inspect(id):
 data=raw(session_path(id)/'events.jsonl',2*1024*1024);require(data.endswith(b'\n'),'Incomplete audit line; outcome unknown')
 lines=data.splitlines();require(1<=len(lines)<=4096 and all(0<len(x)<=8192 for x in lines),'Audit bounds')
 rows=[value(x) for x in lines];require(all(type(x)is dict for x in rows),'Audit objects')
 owner=rows[0].get('owner_thread');require(type(owner)is int and 0<owner<=0xffffffff,'Owner')
 require(rows[0].get('event')=='bootstrap_verified','Missing initial bootstrap')
 hooked=False;hook_attempts=0;current=None;call=None;calls=[];returns=[];results=[];stopped=False;clock=0;intent=None;expires=0
 base={'schema','event','pid','creation','session','dll_sha256','manifest_sha256','owner_thread','thread','ordinal','uptime_ms','sequence','no_send','production_ready'}
 fields={
  'bootstrap_verified':{'native_environment_initialized','game_sha256','strict_SP_verified','world_epoch_verified'},
  'hook_attempt':{'detail'},'hook_installed':{'request_limit','automatic_action','hot_unload_supported'},
  'request_claimed':{'action','actor','target','expires'},'native_call_begin':{'call','family'},
  'native_call_return':{'call','normal','boolean','returned_same_slot','exception','slot_consumed'},
  'dispatch_intent':{'command_id','clone_id','original_deleted'},
  'lease_rejected':{'native_call_attempts','unknown_no_retry'},
  'request_result':{'status','reason','adapter_call_attempts','owned_issued','owned_live','quarantined','adapter_fault','known_cleanup_complete',
    'ownership_closed','submitted','transfer_outcome','submit_attempted','submit_returned','submit_value','slot_consumed','submit_exception'},
  'terminal':{'unknown_no_retry'}}
 def uint(x,maximum=0xffffffffffffffff):return type(x)is int and 0<=x<=maximum
 def flag(x):return type(x)is bool
 for i,row in enumerate(rows):
  event=row.get('event');require(event in fields and set(row)==base|fields[event],'Unknown event/fields')
  require(row['schema']=='EU4PAIRSEND/1' and type(row['ordinal'])is int and row['ordinal']==i+1 and type(row['pid'])is int and row['pid']==id['pid'] and row['creation']==id['creation']
   and row['session']==id['session'] and row['dll_sha256']==id['dll_sha256'] and row['manifest_sha256']==MANIFEST_SHA
   and row['no_send'] is False and row['production_ready'] is False and type(row['owner_thread'])is int and row['owner_thread']==owner,'Audit identity/order')
  require(uint(row['thread'],0xffffffff) and row['thread']>0 and uint(row['uptime_ms']) and row['uptime_ms']>=clock and uint(row['sequence'],64),'Audit clock/types');clock=row['uptime_ms']
  if event in {'request_claimed','native_call_begin','native_call_return','dispatch_intent','lease_rejected','request_result'}:require(row['thread']==owner,'Owner mismatch')
  require(not stopped or event=='terminal','Action after terminal/frozen outcome')
  if event=='bootstrap_verified':
   require(i==0 and row['sequence']==0 and row['native_environment_initialized'] is True and row['game_sha256']==GAME_SHA
    and row['strict_SP_verified'] is False and row['world_epoch_verified'] is False,'Bootstrap claims')
  elif event=='hook_attempt':
   require(not hooked and current is None and row['sequence']==0,'Hook order');hook_attempts+=1;require(hook_attempts<=3,'Hook attempt bound')
   detail=row['detail'];require(type(detail)is dict and detail.get('event')=='hook_install_attempt' and detail.get('attempt')==hook_attempts and detail.get('send_supported') is False,'Legacy hook detail')
  elif event=='hook_installed':
   require(not hooked and current is None and row['sequence']==0 and hook_attempts>0 and rows[i-1]['event']=='hook_attempt' and rows[i-1]['detail']['result']==0
    and row['request_limit']==64 and row['automatic_action'] is False and row['hot_unload_supported'] is False,'Hook success/order');hooked=True
  elif event=='request_claimed':
   require(hooked and current is None and call is None and row['sequence']==len(results)+1 and row['sequence']<=6,'Request order/overlap')
   require(row['action']==ACTIONS[row['sequence']-1] and row['actor']=='FRA' and row['target']=='ENG' and uint(row['expires']) and clock<row['expires'],'Fixed batch/expired claim')
   wire=request(id,row['sequence'],row['expires'],row['action']);path=session_path(id)
   require(raw(path/f"{row['sequence']}.claim",1024)==wire and raw(path/f"{row['sequence']}.request",1024)==wire,'Claim/request bytes changed')
   pub=value(raw(path/'positive-six.publisher-intent.json',16384))
   require(pub['identity']==id and pub['actions']==ACTIONS and type(pub['expires'])is int and pub['expires']==row['expires'] and pub['no_send'] is False
    and len(pub['request_sha256'])==6 and pub['request_sha256'][row['sequence']-1]==sha(wire),'Publisher intent mismatch')
   current=row['sequence'];calls=[];returns=[];intent=None;expires=row['expires']
  elif event=='dispatch_intent':
   require(current is not None and row['sequence']==current and call is None and intent is None and calls==[0,1,2,3,4,5],'Dispatch intent order')
   require(all(r['normal'] and not r['exception'] for r in returns) and returns[2]['boolean'] and returns[4]['boolean'],'Dispatch without preview/gate')
   c=row['command_id'];k=row['clone_id']
   require(uint(c) and uint(k) and c!=k and c>>32==k>>32 and c>>32>0 and 0<(c&0xffffffff)<=64 and 0<(k&0xffffffff)<=64 and row['original_deleted'] is True,'Dispatch ledger IDs')
   intent=row
  elif event in {'native_call_begin','native_call_return'}:
   require(current is not None and row['sequence']==current and uint(row['call'],7),'Native call scope')
   if event=='native_call_begin':
    require(call is None and type(row['family'])is int and row['family']==current-1 and len(calls)<7,'Native overlap/family/bound')
    require((row['call'] in (5,6) or clock<expires) and (row['call']!=7 or intent is not None),'Expired work/missing dispatch intent')
    require(intent is None or row['call']==7,'Cleanup or work after dispatch intent')
    call=row['call'];calls.append(call)
   else:
    require(call is not None and row['call']==call and all(flag(row[k]) for k in ['normal','boolean','returned_same_slot','slot_consumed']) and uint(row['exception'],0xffffffff),'Native return mismatch/types')
    require(call==7 or row['slot_consumed'] is False,'Consumed slot outside submission')
    returns.append(row);call=None
  elif event=='lease_rejected':
   require(current is not None and row['sequence']==current and not calls and row['native_call_attempts']==0 and row['unknown_no_retry'] is True,'Lease rejection');stopped=True
  elif event=='request_result':
   require(current is not None and row['sequence']==current and call is None and uint(row['status'],5) and type(row['reason'])is str and 0<len(row['reason'])<=128,'Result scope/types')
   for key in ['adapter_call_attempts','owned_issued','owned_live','quarantined','adapter_fault']:require(uint(row[key],64),'Result counter')
   for key in ['known_cleanup_complete','ownership_closed','submitted','submit_attempted','submit_returned','submit_value','slot_consumed']:require(flag(row[key]),'Result flags')
   require(uint(row['transfer_outcome'],2) and uint(row['submit_exception'],0xffffffff) and row['adapter_call_attempts']==len(calls)==len(returns),'Result count/transfer')
   if row['ownership_closed']:
    require(row['status']!=5 and row['owned_live']==row['quarantined']==row['adapter_fault']==0 and all(x['normal'] and x['exception']==0 for x in returns),'Unproven ownership closure')
    expected={0:([0] if row['reason']=='normal_factory_null' else [0,1,2,3,5]),1:[],2:[0,1,2,5],3:[0,1,2,3,4,5,6],4:[0,1,2,3,4,5,7]}
    require(calls==expected[row['status']],'Missing/reordered ownership operation')
    require(row['owned_issued']==(3 if row['status'] in (3,4) else 1 if row['status']==2 or len(calls)>1 else 0),'Owned object count')
    if row['status']==4:
     require(intent is not None and row['reason']=='normal_dispatch_slot_consumed' and row['submitted'] and row['submit_attempted'] and row['submit_returned'] and row['submit_value'] and row['slot_consumed']
      and row['transfer_outcome']==1 and row['submit_exception']==0 and not row['known_cleanup_complete'],'Unproven dispatch or false cleanup claim')
     require(returns[2]['boolean'] and returns[3]['returned_same_slot'] and returns[4]['boolean'] and returns[-1]['boolean'] and returns[-1]['slot_consumed'],'Native dispatch proof')
    else:
     require(intent is None and row['known_cleanup_complete'] and not any(row[k] for k in ['submitted','submit_attempted','submit_returned','submit_value','slot_consumed']) and row['transfer_outcome']==0 and row['submit_exception']==0,'False cleanup/submission claims')
   else:
    require(row['status']==5 and not row['known_cleanup_complete'] and not row['submitted'] and row['transfer_outcome']!=1,'Frozen ownership claims');stopped=True
   results.append(row);current=None
  else:
   require(row['unknown_no_retry'] is True and row['sequence'] in (0,current or 0,len(results)),'Terminal scope');stopped=True
 return dict(identity=id,owner_thread=owner,rows=rows,audit_sha256=sha(data),audit_bytes=len(data),
  terminal=stopped,complete=hooked and len(results)==6 and current is None and call is None and not stopped,
  pending_sequence=current,pending_native_call=call,results=results,
  dispatched=sum(r['submitted'] for r in results),gameplay_effects_verified=False)

def wait_finished(id,timeout=55):
 require(type(timeout) in (int,float) and 0<=timeout<=55,'Bounded file-only wait')
 started=time.monotonic()
 while True:
  try:data=raw(session_path(id)/'events.jsonl',2*1024*1024)
  except ValueError as exc:
   if str(exc)!='File changed during read':raise
   data=b''
  if data.endswith(b'\n'):
   last=value(data.splitlines()[-1])
   if last.get('event')=='terminal' or last.get('event')=='request_result' and (last.get('sequence')==6 or last.get('status')==5):return inspect(id)
  require(time.monotonic()-started<timeout,'Batch not finished; preserve files, no effects sample or resend')
  time.sleep(0.25)
'''
  data=data[:start]+inspect+data[end:]
  data=data.replace("choices=['check','load','batch','inspect']","choices=['check','load','batch','inspect','finish']")
  data=data.replace("result=batch(id,m,readonly) if a.command=='batch' else inspect(id)","result=batch(id,m,readonly) if a.command=='batch' else wait_finished(id) if a.command=='finish' else inspect(id)")
 elif name=='test_wire_fixture.cpp':
  data=re.sub(r'"e5caf[0-9a-f]+"','"'+M+'"',data)
 elif name=='test_client.py':
  data=data.replace('4:[0,1,2,3,4,5,6]','4:[0,1,2,3,4,5,7]')
  data=data.replace('  for call in calls:\n   self.row',"  for call in calls:\n   if call==7:self.row('dispatch_intent',seq,command_id=(1<<32)|2,clone_id=(1<<32)|3,original_deleted=True)\n   self.row",1)
  data=data.replace('returned_same_slot=True,exception=0)','returned_same_slot=True,exception=0,slot_consumed=call==7)',1)
  data=data.replace("4:'synthetic_lifecycle_no_send'","4:'normal_dispatch_slot_consumed'")
  data=data.replace('known_cleanup_complete=True,submitted=False)',
   'known_cleanup_complete=status!=4,ownership_closed=True,submitted=status==4,transfer_outcome=1 if status==4 else 0,submit_attempted=status==4,submit_returned=status==4,submit_value=status==4,slot_consumed=status==4,submit_exception=0)',1)
  data=data.replace("('submitted',True)","('submitted',False)")
  data=data.replace('status=5,known_cleanup_complete=False,owned_live=3,quarantined=3,adapter_fault=14)',
   'status=5,known_cleanup_complete=False,ownership_closed=False,submitted=False,transfer_outcome=2,owned_live=3,quarantined=3,adapter_fault=14)')
  added=r'''
 def test_dispatched_is_not_cleanup_or_effects(self):
  self.start();self.action(1);self.rows[-1]['known_cleanup_complete']=True
  with self.assertRaises(ValueError):self.inspect()
 def test_unknown_submission_forms_never_complete(self):
  self.start();self.action(1);base=copy.deepcopy(self.rows)
  for normal in (False,True):
   for boolean in (False,True):
    for consumed in (False,True):
     if normal and boolean and consumed:continue
     self.rows=copy.deepcopy(base);self.rows[-2].update(normal=normal,boolean=boolean,slot_consumed=consumed)
     self.rows[-1].update(status=5,known_cleanup_complete=False,ownership_closed=False,submitted=False,transfer_outcome=2,
      submit_returned=normal,submit_value=boolean,slot_consumed=consumed,adapter_fault=11)
     s=self.inspect();self.assertFalse(s['complete']);self.assertTrue(s['terminal']);self.assertEqual(s['dispatched'],0)
 def test_missing_dispatch_intent_refused(self):
  self.start();self.action(1);self.rows=[r for r in self.rows if r['event']!='dispatch_intent']
  for i,r in enumerate(self.rows):r['ordinal']=i+1
  with self.assertRaises(ValueError):self.inspect()
 def test_finish_wait_requires_complete_or_terminal(self):
  self.start();self.inspect()
  with self.assertRaises(ValueError):client.wait_finished(ID,timeout=0)
  for i in range(6):self.action(i+1,[2,4,4,2,4,4][i])
  self.inspect();s=client.wait_finished(ID,timeout=0);self.assertTrue(s['complete']);self.assertEqual(s['dispatched'],4)
  self.assertFalse(s['gameplay_effects_verified'])
'''
  assert "if __name__=='__main__'" in data;data=data.replace("if __name__=='__main__'",added+"\nif __name__=='__main__'",1)
 elif name=='validate.py':
  data=data.replace('Ran 15 tests','Ran 19 tests').replace('tests=15','tests=19')
 elif name=='README.md':
  data='''# V24 fixed six private send client

Full manifest SHA and exact source closure; caller externally pins this source
and runs python -I -B. Load once into a fresh exact PID/creation; publication
intent and six permanent requests once. Only fixed FRA-to-ENG positive actions.
No resend, hot replacement, guessed cleanup or unfreeze. finish polls ONLY files,
then strictly validates full audit. It never reads process/game effects. A
separate root observer must refuse final effects sampling before complete or
terminal. Queue dispatch is distinct from reception and effects. Old hook
send_supported=false is preserved legacy metadata; actual submit records prove
the private send path. No production backend/SP/epoch/receiver/effect claims.
'''
 with (HERE/name).open('xb') as f:f.write(data.encode('ascii'))
print(json.dumps(dict(candidate=HERE.name,manifest_sha256=M)))
