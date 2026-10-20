"""Root-SHA-checked isolated private client; fixed six-positive send batch."""
import argparse,ctypes as C,hashlib,json,os,re,secrets,sys,types,time
from ctypes import wintypes as W
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BUILD=ROOT/'work/candidates/v25-pair-send-bootstrap-1375/development-attempt1/build'
MANIFEST_SHA='40738e72bdbf1c6442d9a6b55ef83ac6bf8e6211669db9b83bda41660e8f9929'
LAUNCHER=ROOT/'work/candidates/v19-spy-real-client-r2-1375/launcher.py'
LAUNCHER_SHA='a7944c63e044e195a242b417afbea27c001ef2cae1f9d1a721bf3b83352845fe'
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PURPOSE='restricted_pair_send_1375_v25'
ACTIONS=['offer_vassalization','royal_marriage','improve_relations','guarantee','build_spy_network','curry_favors']
def require(value,why):
 if not value:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw(path,maximum):
 path=Path(path);require(path.is_absolute() and path.is_relative_to(ROOT),'Path outside fixed workspace')
 cursor=path
 while True:
  st=cursor.lstat();require(not getattr(st,'st_file_attributes',0)&0x400 and not cursor.is_symlink(),'Linked source/file')
  if cursor==ROOT:break
  cursor=cursor.parent
 require(path.resolve()==path,'Noncanonical linked path')
 before=path.stat();require(before.st_nlink==1 and 0<before.st_size<=maximum,'Bounded single-link file')
 with path.open('rb') as f:
  a=os.fstat(f.fileno());data=f.read(maximum+1);b=os.fstat(f.fileno())
 require(len(data)==before.st_size and (a.st_dev,a.st_ino)==(before.st_dev,before.st_ino) and (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns),'File changed during read')
 return data
def unique(pairs):
 out={}
 for k,v in pairs:require(k not in out,'Duplicate JSON key');out[k]=v
 return out
def value(data):return json.loads(data,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def encoded(obj):return (json.dumps(obj,indent=2,sort_keys=True)+'\n').encode('ascii')
def write_new(path,data):
 require(path.is_relative_to(BUILD) and not path.exists(),'Existing permanent file; never retry')
 with path.open('xb') as f:require(f.write(data)==len(data),'Short write');f.flush();os.fsync(f.fileno())
def manifest():
 data=raw(BUILD/'build.json',1024*1024);require(sha(data)==MANIFEST_SHA,'Changed fixed manifest')
 m=value(data);require(m['schema']=='EU4PAIRBUILD/1' and m['purpose']==PURPOSE and m['no_send'] is False,'Fixed private send build')
 dll=raw(BUILD/m['DLL'],16*1024*1024);require(dict(bytes=len(dll),sha256=sha(dll))==m['dll'],'Changed DLL')
 require(m['game_sha256']==GAME_SHA and len(m['source_pins'])<=512,'Build identity/bound')
 total=0
 for name,pin in m['source_pins'].items():
  require(type(name)is str and not Path(name).is_absolute() and '..' not in Path(name).parts,'Canonical source pin')
  b=raw(ROOT/name,4*1024*1024);total+=len(b);require(total<=32*1024*1024,'Source budget')
  require(dict(bytes=len(b),sha256=sha(b))==pin,'Changed build source '+name)
 return m
def graph():
 data=raw(LAUNCHER,64*1024);require(sha(data)==LAUNCHER_SHA,'Changed trusted frozen launcher')
 module=types.ModuleType('_pair25_frozen_launcher');module.__file__=str(LAUNCHER)
 exec(compile(data,str(LAUNCHER),'exec'),module.__dict__)
 return module.verified_graph()
def identity(pid,creation,session,m):
 require(type(pid)is int and 0<pid<=0xffffffff,'PID')
 require(type(creation)is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)>0,'Creation')
 require(type(session)is str and re.fullmatch('[0-9a-f]{32}',session) and int(session,16)>0,'Session')
 return dict(pid=pid,creation=creation,session=session,dll_sha256=m['dll']['sha256'],manifest_sha256=MANIFEST_SHA)
def boot(id):
 return (f"EU4PAIRSENDBOOT/1\npurpose={PURPOSE}\ngame_sha256={GAME_SHA}\npid={id['pid']}\ncreation={id['creation']}\nsession={id['session']}\ndll_sha256={id['dll_sha256']}\nmanifest_sha256={MANIFEST_SHA}\ndisposable=1\nsend=1\n").encode('ascii')
def request(id,sequence,expires,action):
 require(type(action)is str and action in ACTIONS and type(sequence)is int and 1<=sequence<=64 and type(expires)is int and 0<expires<=0xffffffffffffffff,'Fixed typed request')
 return (f"EU4PAIRSEND/1\npurpose={PURPOSE}\ngame_sha256={GAME_SHA}\npid={id['pid']}\ncreation={id['creation']}\nsession={id['session']}\ndll_sha256={id['dll_sha256']}\nmanifest_sha256={MANIFEST_SHA}\nsequence={sequence}\nexpires={expires}\naction={action}\nactor=FRA\ntarget=ENG\nsend=1\n").encode('ascii')
def session_path(id):return BUILD/f"pair25-{id['pid']}-{id['creation']}-{id['session']}"
def inspect(id):
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

def loaded(held,m,status):
 held.reads=held.bytes=0;held.identity_check();canonical=held.injector._canonical;modules=held.modules()
 game=[base for base,p in modules if canonical(p)==canonical(held.injector.GAME)]
 dll=[base for base,p in modules if canonical(p)==canonical(BUILD/m['DLL'])]
 research=[p for _,p in modules if Path(p).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_'))]
 require(len(game)==len(dll)==len(research)==1,'Exact single game/research module')
 def pe(data):
  require(data[:2]==b'MZ','PE');nt=int.from_bytes(data[60:64],'little');require(64<=nt<=4096 and nt+264<=len(data),'PE bounds')
  require(data[nt:nt+4]==b'PE\0\0' and int.from_bytes(data[nt+4:nt+6],'little')==0x8664 and int.from_bytes(data[nt+24:nt+26],'little')==0x20b,'PE x64')
  return int.from_bytes(data[nt+8:nt+12],'little'),int.from_bytes(data[nt+80:nt+84],'little')
 require(pe(held.memory(game[0],8192))==(0x66fe6ab9,0x25e0000),'Game loaded headers')
 require(pe(held.memory(dll[0],8192))==(m['PE_timestamp'],m['SizeOfImage']),'DLL loaded headers')
 require(held.window_thread()==status['owner_thread'],'Changed owner thread');held.identity_check()
def load(id,m,g,readonly):
 injector=g.load(ROOT/'work/native/inject_probe.py');held=readonly.Held(id)
 try:
  require(not any(Path(p).name.lower().startswith(('eu4_bridge_','eu4_pair_','eu4_spy_')) for _,p in held.modules()),'Existing research module; restart required')
  intent=BUILD/f"loader-intent-{id['pid']}-{id['creation']}.json";packet=BUILD/f"bootstrap-{id['pid']}-{id['creation']}.request"
  require(not intent.exists() and not packet.exists(),'Permanent load intent/bootstrap exists; never retry')
  write_new(intent,encoded(dict(identity=id,manifest_sha256=MANIFEST_SHA,boot_sha256=sha(boot(id)),no_send=False,native_result_unknown=True)))
  manifest();held.identity_check();write_new(packet,boot(id));held.identity_check()
  installation=injector._run(argparse.Namespace(pid=id['pid'],dll=str(BUILD/m['DLL']),timeout_ms=10000,ack_test_save=True),expected_game_hash=GAME_SHA)
  held.identity_check();report=dict(identity=id,installation=installation,no_send=False,production_ready=False)
  write_new(BUILD/f"loader-{id['pid']}-{id['creation']}.json",encoded(report));return report
 finally:held.close()
def move_new(source,target):
 k=C.WinDLL('kernel32',use_last_error=True);k.MoveFileExW.argtypes=[W.LPCWSTR,W.LPCWSTR,W.DWORD];k.MoveFileExW.restype=W.BOOL
 if not k.MoveFileExW(str(source),str(target),0x8):raise C.WinError(C.get_last_error())
def batch(id,m,readonly):
 status=inspect(id);require(not status['terminal'] and any(x['event']=='hook_installed' for x in status['rows']) and not status['results'],'New ready session only')
 require(not any(x['event']=='request_claimed' for x in status['rows']),'Already claimed; never resend')
 held=readonly.Held(id)
 try:
  loaded(held,m,status);prepared=readonly.now_ms();expires=prepared+60000;path=session_path(id)
  intent=path/'positive-six.publisher-intent.json';require(not intent.exists(),'Permanent batch intent exists')
  packets=[request(id,i+1,expires,a) for i,a in enumerate(ACTIONS)]
  for i in range(1,7):
   for suffix in ['request','claim','publisher-pending']:require(not (path/f'{i}.{suffix}').exists(),'Existing batch artifact; never retry')
  write_new(intent,encoded(dict(identity=id,actions=ACTIONS,expires=expires,prepared=prepared,
   request_sha256=[sha(x) for x in packets],no_send=False,native_result_unknown=True)))
  for i,data in enumerate(packets,1):write_new(path/f'{i}.publisher-pending',data)
  manifest();require(readonly.now_ms()<expires,'Expired before publication')
  highwater=prepared
  for i,data in enumerate(packets,1):
   pending=path/f'{i}.publisher-pending';target=path/f'{i}.request'
   require(raw(pending,1024)==data and not target.exists() and not (path/f'{i}.claim').exists(),'Changed pending/request/claim')
   loaded(held,m,status);now=readonly.now_ms();require(highwater<=now<expires,'Expired/clock rollback after final identity');highwater=now
   move_new(pending,target)
  return dict(identity=id,published_sequences=list(range(1,7)),actions=ACTIONS,expires=expires,no_send=False,native_result=None,production_ready=False)
 finally:held.close()
def main():
 require(sys.flags.isolated==1,'Run python -I -B with externally verified client SHA')
 p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--creation',required=True);p.add_argument('--session')
 p.add_argument('--ack-disposable-test',action='store_true',required=True);p.add_argument('command',choices=['check','load','batch','inspect','finish']);a=p.parse_args()
 m=manifest();g=graph();readonly=g.local('readonly.py');id=identity(a.pid,a.creation,a.session or secrets.token_hex(16),m)
 if a.command=='check':result=dict(build_verified=True,frozen_loader_graph_verified=True,DLL_loaded=False,production_ready=False)
 elif a.command=='load':require(a.session is None,'Loader owns fresh session');result=load(id,m,g,readonly)
 else:
  require(a.session is not None,'Exact session required');result=batch(id,m,readonly) if a.command=='batch' else wait_finished(id) if a.command=='finish' else inspect(id)
 print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,OSError,RuntimeError) as exc:print(f'pair25 refused: {exc}; preserve permanent files, do not retry',file=sys.stderr);raise SystemExit(2)
