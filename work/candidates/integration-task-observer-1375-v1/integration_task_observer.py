"""Current bilateral integration-task index profile; external QUERY/VM_READ only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import struct
import sys
import time
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REL=HERE.relative_to(ROOT).as_posix()
MANIFEST=HERE/'source-manifest.json'
GAME=ROOT.parent/'eu4.exe'
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
DIRECT='work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py'
DIRECT_MANIFEST='work/candidates/direct-truce-cache-cli-1375-v1/source-manifest.json'
OBSERVER='bridge/diplomacy_effect_observer.py'
JOB='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
R44='work/reports/integration-reader-static-20261015-r44/'
R45='work/reports/integration-reader-index-20261015-r45/'
R46='work/reports/integration-reader-type-20261015-r46/'
VT,SLOT,LEAF=0x1c816d8,0x1c81720,0xa72f50
FIXED={
 DIRECT:'5429932a8f4fb81180c566caa0905008d60880f51f7c5868dd7568b4040fe518',
 DIRECT_MANIFEST:'47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8',
 OBSERVER:'9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1',
 JOB:'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011',
 R44+'manifest.json':'30a7959646a6f8d37b8ea3d441e92c877dfdb41d73554534bd0c72917dffffd4',
 R44+'contract.json':'816a3b4b2a613214ed6814b3cf32b74b9fe4b22baa5a09e6d091af302090c162',
 R44+'owned-code.json':'6f55b2e44c57ccdc803dd63a808fafe5b7864246637c7c35e2549b289775a85c',
 R45+'manifest.json':'f4fca5087e63feed44f1d23e12016ec8a62511b2fc05519eb15c6a820e79edf9',
 R45+'contract.json':'5137937c6be8a52a258380d6745f6f07aa9fc19bcabb2030eab4bd5045350be4',
 R45+'owned-code.json':'6444597184d9803535b7736156c8c31f35dfe434784ef58ab627cc9442e9a9d4',
 R46+'manifest.json':'7f1f5660041e2834d18d09cb91d9c84d406ab6c4dc7a1f4c6456bc789be83347',
 R46+'contract.json':'7bd02a49639bd6ff5acc7b9ff645710f9dd3c535f715223d374e74d5f1e174aa',
 R46+'owned-code.json':'d5b88e82010f84866519a461c20a6e4b551d8900911580dd45d57485932750dd',
 R46+'slot.json':'3e9500729654cf52f413294826cb4bf1ff18a843999891791a631b19da34df45',
 'work/reports/integration-reader-r44-r45-independent-20261015-r1/findings.json':'4bce2319e38a0d8844aaf03365d7cd45c63c34328fab4e24cc811cec39979a15',
 'work/reports/integration-reader-r46-independent-20261015-r1/findings.json':'72e009de857739ab9b2f25ce7caf35d68b8d091970e314c7f1d8f0986eeb5bf9'}
REQUIRED={REL+'/'+n for n in ('integration_task_observer.py','test_integration_task_observer.py','README.md','build_manifest.py','run_offline.py')}
RESEARCH_PREFIXES=('eu4_bridge_','eu4_pair_','eu4_spy_','eu4_tag_command_','tag_diplomacy')
FALSE_FLAGS=('selected_effect_verified','request_effect_verified','integration_completed','native_action_mapping_verified',
 'native_predicate_executed','native_ready','sender_authorized','lifetime_lease','atomic_snapshot','persistence_verified','complete_cpp_class_verified')

def require(value,message):
 if not value:raise ValueError(message)

def read(path,limit=4*1024*1024):
 with Path(path).open('rb') as f:b=f.read(limit+1)
 require(0<len(b)<=limit,'Selected file bound');return b

def pin(path):
 b=read(path);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

def local_path(name):
 require(type(name) is str and '\\' not in name and ':' not in name,'Invalid source path')
 p=PurePosixPath(name);require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==name,'Source traversal')
 absolute=(ROOT/name).resolve();require(absolute.is_relative_to(ROOT.resolve()),'Source escapes root');return absolute

def json_file(path):
 def unique(pairs):
  d={}
  for k,v in pairs:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 def invalid(_):raise ValueError('Nonfinite JSON')
 return json.loads(read(path).decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid)

def verify_sources(*,runtime=False):
 m=json_file(MANIFEST)
 require(m.get('schema')=='EU4-INTEGRATION-TASK-OBSERVER-MANIFEST/1' and m.get('game_sha256')==GAME_SHA
  and type(m.get('sealed')) is bool and type(m.get('runtime_capture_authorized')) is bool,'Candidate manifest identity')
 expected=m.get('source_pins');require(type(expected) is dict and REQUIRED|set(FIXED)<=set(expected) and len(expected)<=64,'Candidate source graph')
 actual={};total=0
 def check(n,p):
  nonlocal total
  require(type(p) is dict and set(p)=={'bytes','sha256'} and type(p['bytes']) is int and 0<p['bytes']<=4*1024*1024
   and type(p['sha256']) is str and re.fullmatch('[0-9a-f]{64}',p['sha256']),'Pin shape')
  total+=p['bytes'];require(total<=16*1024*1024,'Source graph bound')
  value=pin(local_path(n));require(value==p,'Source changed: '+n);actual[n]=value
 for n,p in expected.items():check(n,p)
 for n,sha in FIXED.items():require(actual[n]['sha256']==sha,'Frozen source changed')
 for prefix in (R44,R45,R46):
  static=json_file(local_path(prefix+'manifest.json'))
  require(static['sealed'] is True and static['game_sha256']==GAME_SHA,'Static profile manifest identity')
  static_pins=static['file_pins'] if prefix==R44 else static['source_pins']
  for n in (prefix+'contract.json',prefix+'owned-code.json'):
   require(static_pins[n]==actual[n],'Static selected output pin linkage')
  if prefix==R46:require(static_pins[R46+'slot.json']==actual[R46+'slot.json'],'Slot static linkage')
 if runtime or m['runtime_capture_authorized']:
  require(m['sealed'] is True and m['runtime_capture_authorized'] is True,'Independent source-ready and root production seal required before process access')
  reviews=m.get('independent_reviews');require(type(reviews) is dict and set(reviews)=={'R44','R45','R46','candidate'},'Four independent review pins required')
  for role,entry in reviews.items():
   require(type(entry) is dict and set(entry)=={'path','bytes','sha256'},'Review pin shape')
   if role in ('R44','R45'):
    require(entry['path']=='work/reports/integration-reader-r44-r45-independent-20261015-r1/findings.json','R44/R45 fixed review')
   elif role=='R46':require(entry['path']=='work/reports/integration-reader-r46-independent-20261015-r1/findings.json','R46 fixed review')
   if role!='candidate':require(entry['sha256']==FIXED[entry['path']],'Fixed static review SHA')
   check(entry['path'],{k:entry[k] for k in ('bytes','sha256')})
 return dict(manifest=pin(MANIFEST),source_pins={n:actual[n] for n in expected},sealed=m['sealed'],runtime_capture_authorized=m['runtime_capture_authorized'])

def exact_compile(name,expected):
 path=local_path(name);b=read(path);require(dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())==expected,'Library exact-source compile guard')
 module=types.ModuleType('_integration_task_'+path.stem);module.__file__=str(path)
 exec(compile(b,str(path),'exec'),module.__dict__);return module

def code_buffers():
 a=json_file(local_path(R44+'owned-code.json'));b=json_file(local_path(R45+'owned-code.json'))
 c=json_file(local_path(R46+'owned-code.json'));slot=json_file(local_path(R46+'slot.json'))
 getter=next(x for x in b['helpers'] if x['entry']=='0xa6a780')
 rawA=bytes.fromhex(a['raw_hex']);rawB=bytes.fromhex(getter['raw_hex']);rawC=bytes.fromhex(c['raw_hex'])[:6]
 require(a['window']==['0x51b6e0','0x51bfb3'] and getter['end_exclusive']=='0xa6a7e7'
  and c['rva']=='0xa72f50' and [len(rawA),len(rawB),len(rawC)]==[2259,103,6],'Fixed code spans')
 require(rawC==bytes.fromhex('b8d52d0000c3') and slot['rva']==hex(SLOT)
  and struct.unpack('<Q',bytes.fromhex(slot['raw_hex']))[0]-int(slot['preferred_image_base'],16)==LEAF,'Fixed slot/leaf semantics')
 return [(0x51b6e0,rawA),(0xa6a780,rawB),(SLOT,None),(LEAF,rawC)]

class Libraries:
 def __init__(self,initial):
  self.initial=initial;self.direct=exact_compile(DIRECT,initial['source_pins'][DIRECT])
  self.frozen=self.direct.Libraries();self.host,self.r24=self.frozen.host,self.frozen.r24
  self.codes=code_buffers();self.guard()
 def guard(self):
  require(verify_sources()==self.initial,'Candidate sources changed');self.frozen.guard()
 def observer(self):
  require(verify_sources(runtime=True)==self.initial,'Reviewed runtime source graph required')
  self.guard();return self.frozen.observer()
 def evidence(self):
  return dict(candidate=self.initial,reused_direct=self.frozen.evidence(),old_main_executed=False,
   old_fixed_pid_authority_reused=False,old_capture_executed=False,registered_argv_executed=False,
   static_output_scope='selected exact pinned R44/R45/R46 outputs; static producer dependencies not re-executed')

def selection(pid,creation,actor,target):
 require(type(pid) is int and 0<pid<=0xffffffff,'PID positive DWORD')
 require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)!=0,'Creation nonzero lowercase FILETIME')
 require(all(type(t) is str and re.fullmatch('[A-Z0-9]{3}',t) for t in (actor,target)) and actor!=target,'Distinct exact TAG pair')
 return dict(pid=pid,creation=creation,actor=actor,target=target)

class JournalPort:
 def __init__(self,port):self.port=port;self.entries=[];self.stage='unassigned'
 def read(self,address,size):
  row=dict(ordinal=len(self.entries)+1,stage=self.stage,address=hex(address),bytes=size,status='pending');self.entries.append(row)
  try:
   b=self.port.read(address,size);require(type(b) is bytes and len(b)==size,'Exact journal read')
   row.update(status='complete',raw_hex=b.hex());return b
  except Exception as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc));raise

class SharedView:
 """Host's per-sample counters over the same global BudgetReader, without mutation."""
 def __init__(self,reader):self.reader=reader;self.calls=self.bytes=self.largest=0
 def read(self,address,size):
  # Counters are only committed after shared validation/read; failures remain in
  # the shared reader/journal and cannot lead to a successful observation.
  raw=self.reader.read(address,size);self.calls+=1;self.bytes+=size;self.largest=max(self.largest,size);return raw
 def q(self,address):return struct.unpack('<Q',self.read(address,8))[0]
 def i(self,address):return struct.unpack('<i',self.read(address,4))[0]
 def b(self,address):return self.read(address,1)[0]

def host_sample_shared(libraries,cap,observer,r):
 view=SharedView(r)
 proxy=types.SimpleNamespace(roots=observer.roots,ptr=observer.ptr,
  BudgetReader=lambda _:view,HeldRPMPort=lambda _:None)
 return libraries.host.host_sample(cap,proxy)

def code_guard(r,base,codes):
 out=[]
 for offset,expected in codes:
  if offset==SLOT:require(expected is None,'Relocated slot expected');expected=struct.pack('<Q',base+LEAF)
  require(type(expected) is bytes,'Code bytes required')
  raw=r.read(base+offset,len(expected));require(raw==expected,'Loaded code/slot mismatch at '+hex(offset))
  out.append(dict(rva=hex(offset),bytes=len(raw),raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest(),
   runtime_relocation_applied=offset==SLOT))
 return out

def sample_selected(r,observer,r24,base,root,table,handles,actor,target):
 require(root['count']==1380 and type(table) is bytes and len(table)==1380*8,'Full1380 table required')
 forward=r24.pair_sample(r,observer,base,root,handles,actor,target)
 reverse=r24.pair_sample(r,observer,base,root,handles,target,actor)
 pairs=[forward,reverse];r24.check_country_table_binding([dict(directional_pairs=pairs)],table)
 require(forward['actor']['address']!=forward['target']['address'],'Country pointer alias')
 left=observer.index(r,int(forward['relation_root'],16),0x200,forward['target']['slot'],1380)
 right=observer.index(r,int(reverse['relation_root'],16),0x200,reverse['target']['slot'],1380)
 require(type(left['member']) is bool and type(right['member']) is bool,'Strict indexed membership')
 require(left['member']==right['member'] and left['object']==right['object'],'One-sided or mismatched selected indexes')
 task=None
 if left['member']:
  require(type(left['object']) is int and left['object']%8==0,'Aligned selected task pointer')
  address=observer.ptr(left['object']);body=r.read(address,0x48)
  first,second=struct.unpack_from('<QQ',body,0x10)
  require(struct.unpack_from('<Q',body)[0]==base+VT and body[0x28]==0,'Other task vtable or removed state; unknown, not absence')
  require({first,second}=={handles[actor],handles[target]},'Task full endpoints differ')
  task=dict(address=hex(address),body_raw_hex=body.hex(),vtable_rva=hex(VT),
   endpoint_10=hex(first),endpoint_18=hex(second),raw_u32_at_20=struct.unpack_from('<I',body,0x20)[0],
   raw_byte_at_28=body[0x28],marker_357_required=False,complete_cpp_class_verified=False)
  state='selected_task_present'
 else:
  require(left['object'] is None and right['object'] is None,'Absent index pointer mismatch');state='selected_index_absent'
 for item in (forward['actor'],forward['target']):
  fresh=r24.owned_country(r,observer,base,root,int(item['handle'],16),item['tag'])
  require(fresh==item and struct.unpack_from('<Q',table,item['slot']*8)[0]==int(item['address'],16),'Country/table changed within pass')
 require(observer.roots(r,base)==root,'Roots changed within pass')
 return dict(state=state,selected_task_present=left['member'],directional_pairs=pairs,
  forward_index=left,reverse_index=right,task=task,
  extra_reader_guards_not_native_getter_checks=['Qii capacity','positive bounded unique keys','canonical aligned pointers','both directions same P','complete endpoints','P+28 zero'])

def base_result(operation):
 return dict(schema='EU4-INTEGRATION-TASK-CURRENT/1',operation=operation,status='unknown',game_sha256=GAME_SHA,selected_task_present=None,
  **{k:False for k in FALSE_FLAGS},requests_published=0,native_game_calls=0,game_fields_written=0,hooks_installed=0,
  Frida_called=False,saves=0,reloads=0,automatic_retry=False,errors=[])

def observe(chosen,libraries):
 chosen=selection(**chosen);out=base_result('status');out.update(selection=chosen,samples=[],raw_ordered_read_journal=[],
  captured_utc=datetime.now(timezone.utc).isoformat(),source_graph=libraries.evidence(),precheck=None,postcheck=None,
  code_before=None,code_after=None,selected_two_pass_equal=False,normal_context_exit=False,held_handle_cleared=False,
  close_os_return_checked=False,commit_after_context_exit=False,process_rights='QUERY/VM_READ/SYNCHRONIZE',
  budget_accounting=dict(limits={'calls':4096,'bytes':512*1024,'single_read':65536},
   entry_PE_identity_read=dict(calls=1,bytes=8192,journaled=False,scope='frozen RuntimeCapture.__enter__; separate from shared selected/host budget')))
 started=time.perf_counter()
 try:
  observer=libraries.observer();backend=observer.TagCommandBackend()
  identity=dict(pid=chosen['pid'],creation=chosen['creation'],session=secrets.token_hex(16),
   dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
  out.update(identity=identity,identity_purpose='fresh readonly nonce; not installed session or original request authority')
  libraries.guard()
  with observer.RuntimeCapture(identity,backend) as cap:
   require(Path(cap.held.injector.GAME).resolve()==GAME.resolve(),'Exact game path differs')
   require(not any(Path(p).name.lower().startswith(RESEARCH_PREFIXES) for _,p in cap.modules),'Unexpected research module')
   journal=JournalPort(libraries.r24.AlignedPort(observer.HeldRPMPort(cap.held)));r=observer.BudgetReader(journal)
   try:
    journal.stage='host_before';out['precheck']=host_sample_shared(libraries,cap,observer,r)
    journal.stage='code_before';out['code_before']=code_guard(r,cap.base,libraries.codes)
    for number in (1,2):
     journal.stage='sample_'+str(number);root=observer.roots(r,cap.base)
     require(root==out['precheck']['roots'] and root['count']==1380 and root['manual_pause']==1,'Fresh paused roots/host differ')
     table=r.read(int(root['array'],16),1380*8)
     handles=libraries.direct.selected_handles(r,observer,root,table,chosen['actor'],chosen['target'])
     sample=sample_selected(r,observer,libraries.r24,cap.base,root,table,handles,chosen['actor'],chosen['target'])
     sample.update(roots=root,country_pointer_table_raw_hex=table.hex(),selected_handles={k:hex(v) for k,v in handles.items()})
     out['samples'].append(sample)
    require(out['samples'][0]==out['samples'][1],'Two complete selected passes differ')
    out['selected_two_pass_equal']=True
   except Exception as exc:out['errors'].append(dict(stage='selected',type=type(exc).__name__,message=str(exc)))
   finally:
    try:journal.stage='code_after';out['code_after']=code_guard(r,cap.base,libraries.codes)
    except Exception as exc:out['errors'].append(dict(stage='code_after',type=type(exc).__name__,message=str(exc)))
    try:
     journal.stage='host_after';out['postcheck']=host_sample_shared(libraries,cap,observer,r)
     require(out['postcheck']==out['precheck'] and observer.pins()==cap.initial_pins,'Host/observer postguards differ');libraries.guard()
    except Exception as exc:out['errors'].append(dict(stage='host_source_after',type=type(exc).__name__,message=str(exc)))
    out['raw_ordered_read_journal']=journal.entries
    out['budget_accounting']['shared']=dict(calls=r.calls,bytes=r.bytes,largest=r.largest,
     scope='host before/after, loaded code/slot before/after, two fresh full tables and all selected reads; attempted counts include failures')
  out['normal_context_exit']=True
  require(cap.held is not None and cap.held.handle is None,'Held handle not cleared after normal context exit')
  out['held_handle_cleared']=True;libraries.guard()
  if not out['errors'] and out['selected_two_pass_equal']:
   sample=out['samples'][0];out.update(status=sample['state'],selected_task_present=sample['selected_task_present'],commit_after_context_exit=True)
 except Exception as exc:
  out['errors'].append(dict(stage='context_or_source',type=type(exc).__name__,message=str(exc)))
  out.update(status='unknown',selected_task_present=None,commit_after_context_exit=False)
 out['duration_ms_including_guards']=round((time.perf_counter()-started)*1000,3);return out

def result_code(out):
 if out.get('operation') in ('check','catalog'):return 0 if out.get('status')=='files_verified' and out.get('errors')==[] else 2
 states={'selected_task_present':True,'selected_index_absent':False}
 okay=out.get('operation')=='status' and out.get('status') in states and type(out.get('selected_task_present')) is bool
 okay=okay and out['selected_task_present'] is states[out['status']] and out.get('errors')==[]
 okay=okay and all(out.get(k) is True for k in ('selected_two_pass_equal','normal_context_exit','held_handle_cleared','commit_after_context_exit'))
 okay=okay and all(out.get(k) is False for k in FALSE_FLAGS)
 return 0 if okay else 2

def run(operation,chosen=None,*,library_factory=Libraries):
 out=base_result(operation)
 try:
  require(operation in ('check','catalog','status'),'Unsupported operation')
  if operation=='status':require(type(chosen) is dict,'Exact selected identity required');chosen=selection(**chosen)
  else:require(chosen is None,'File-only operation takes no identity')
  initial=verify_sources(runtime=operation=='status');libraries=library_factory(initial)
  if operation=='status':return observe(chosen,libraries)
  out['source_graph']=libraries.evidence()
  if operation=='catalog':out['profiles']=[dict(id='current_bilateral_integration_task',
   actions_for_reference=['integrate_union','cancel_integration'],current_only=True,states=['selected_task_present','selected_index_absent','unknown'],
   raw_field_20_semantics='unknown; not a date or progress',profile_vtable_rva=hex(VT),
   unknowns=['complete class/lifecycle','request causality or acceptance','integration completion','persistent state'])]
  libraries.guard();out['status']='files_verified'
 except Exception as exc:out['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
 return out

class Parser(argparse.ArgumentParser):
 def error(self,message):raise ValueError(message)

def main(argv=None):
 parser=Parser(description=__doc__,epilog='Exit0: files verified, or current selected presence/absence observed. Never action success/completion. Exit2: unknown/unsupported. No retry.')
 sub=parser.add_subparsers(dest='operation',required=True);sub.add_parser('check');sub.add_parser('catalog')
 status=sub.add_parser('status');status.add_argument('--pid',type=int,required=True);status.add_argument('--creation',required=True)
 status.add_argument('--actor',required=True);status.add_argument('--target',required=True)
 try:
  args=vars(parser.parse_args(argv));operation=args.pop('operation');out=run(operation,args if operation=='status' else None)
 except Exception as exc:out=base_result('unknown');out['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
 print(json.dumps(out,ensure_ascii=True,sort_keys=True,indent=2));return result_code(out)

if __name__=='__main__':raise SystemExit(main())
