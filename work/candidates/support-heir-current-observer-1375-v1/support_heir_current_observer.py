"""Current bilateral support-heir task index profile; external QUERY/VM_READ only."""
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
R48='work/reports/dynastic-support-reader-static-20261015-r48/'
R50='work/reports/dynastic-support-reader-entry-20261015-r50/'
R48_REVIEW='work/reports/dynastic-support-reader-r48-independent-20261015-r1/findings.json'
R50_REVIEW='work/reports/dynastic-support-reader-r50-independent-20261015-r1/findings.json'
CROSSWALK='work/reports/support-heir-handle-crosswalk-20261015-r1/findings.json'
VT=0x1c7c1c8
FIXED={
 DIRECT:'5429932a8f4fb81180c566caa0905008d60880f51f7c5868dd7568b4040fe518',
 DIRECT_MANIFEST:'47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8',
 OBSERVER:'9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1',
 JOB:'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011',
 'work/candidates/integration-task-observer-1375-v1/integration_task_observer.py':'ec576a21a4018fa1b91d0864990b281a7a075ed3761404d9bdd7559de8b25cb9',
 'work/candidates/integration-task-observer-1375-v1/test_integration_task_observer.py':'1f81280856c9728cfeb0b0c2834516604dc11e881c7a2b7c22d16ca9353a8e96',
 'work/reports/integration-task-observer-source-review-20261015-r1/independent-source-ready.json':'14662f7d78556103252f3f52f30a398d570ce246e56bb17948127249ebc10cc4',
 R48+'manifest.json':'00b98e57bc9ca3c69feae82695717db9851bafb05e7148be5e33426a6fa9ee3b',
 R48+'contract.json':'973a776a00ed95ac61e71b68cf33ac8fad799f18fb2f928de72c1bf07204ef4c',
 R48+'owned-code.json':'d392ac87b59dee56bd77f75f2e41243efbea7def5c1a1819d1df3c1ced42b197',
 R50+'manifest.json':'b09a9795d4f9ca2b9a4f330f39b695720705aad76c4bb5ec452341999260e304',
 R50+'contract.json':'ddc97d4bfd011ade3778ded05c643b9aba7c450eeba50b9162757a25353583f2',
 R50+'owned-code.json':'14cbfd7e2ce8bb4de4992e9f71bef4e5430fb75b11d95424ff5054ddbd4687fd',
 R48_REVIEW:'02df6084e3dac269d4f970c091fe6dee85d9dba9c19b2caec4689b062aa764ed',
 R50_REVIEW:'fe6a9188e2d6be6b55d545505ca19c70c244bcf15ea38e32ce4edc80c0dfc7d9',
 CROSSWALK:'f25d2760d0a2d6afac77d590aff36f165f95b45750542ccb243e25d7ad805abe'}


REQUIRED={REL+'/'+n for n in ('support_heir_current_observer.py','test_support_heir_current_observer.py','README.md','build_manifest.py','run_offline.py','prepare_source.py')}
RESEARCH_PREFIXES=('eu4_bridge_','eu4_pair_','eu4_spy_','eu4_tag_command_','tag_diplomacy')
FALSE_FLAGS=('selected_effect_verified','request_effect_verified','final_heir_result_verified','native_action_mapping_verified',
 'AI_acceptance_verified','native_predicate_executed','native_ready','sender_authorized','lifetime_lease','atomic_snapshot','persistence_verified','complete_cpp_class_verified')

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
 require(m.get('schema')=='EU4-SUPPORT-HEIR-OBSERVER-MANIFEST/1' and m.get('game_sha256')==GAME_SHA
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
 for prefix in (R48,R50):
  static=json_file(local_path(prefix+'manifest.json'))
  for n in (prefix+'contract.json',prefix+'owned-code.json'):
   require(static['file_pins'][n]==actual[n],'Static selected output pin linkage')
 if runtime or m['runtime_capture_authorized']:
  require(m['sealed'] is True and m['runtime_capture_authorized'] is True,'Independent source-ready production seal required before process access')
  review=m.get('independent_source_review')
  require(type(review) is dict and set(review)=={'path','bytes','sha256'},'Independent source review pin required')
  check(review['path'],{k:review[k] for k in ('bytes','sha256')})

 return dict(manifest=pin(MANIFEST),source_pins={n:actual[n] for n in expected},sealed=m['sealed'],runtime_capture_authorized=m['runtime_capture_authorized'])

def exact_compile(name,expected):
 path=local_path(name);b=read(path);require(dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())==expected,'Library exact-source compile guard')
 module=types.ModuleType('_support_heir_current_'+path.stem);module.__file__=str(path)
 exec(compile(b,str(path),'exec'),module.__dict__);return module

def code_buffers():
 a=json_file(local_path(R48+'owned-code.json'));b=json_file(local_path(R50+'owned-code.json'))
 raw_a=bytes.fromhex(a['raw_hex']);raw_b=bytes.fromhex(b['raw_hex'])
 require(a['window']==['0x595120','0x5961b4'] and b['window']==['0xa69ab0','0xa69af0']
  and [len(raw_a),len(raw_b)]==[4244,64],'Fixed loaded code spans')
 require(hashlib.sha256(raw_a).hexdigest()==a['sha256'] and hashlib.sha256(raw_b).hexdigest()==b['sha256'],'Owned code digest')
 return [(0x595120,raw_a),(0xa69ab0,raw_b)]

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
   static_output_scope='selected exact pinned R48/R50 outputs and independent static reviews; producer dependencies not re-executed')

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
  require(type(expected) is bytes,'Code bytes required')
  raw=r.read(base+offset,len(expected));require(raw==expected,'Loaded code mismatch at '+hex(offset))
  out.append(dict(rva=hex(offset),bytes=len(raw),raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest()))
 return out


def nullable_index(r,observer,root,other_slot,count):
 """R50 key/value projection plus explicit reader bounds; zero values are legal."""
 require(type(other_slot) is int and 0<other_slot<min(count,32768),'Selected positive slot')
 header=r.read(root+0x140,16);array,capacity,used=struct.unpack('<Qii',header)
 require(0<=used<=256 and used<=capacity<=4096,'Signed index count/capacity bound')
 require((capacity==0 and array==0) or
  (capacity>0 and array%8==0 and 0x10000<=array<array+capacity*16<=2**47),'Index allocation metadata mismatch')
 raw=r.read(observer.ptr(array),used*16) if used else b''
 entries=[]
 for key,value in struct.iter_unpack('<i4xQ',raw):
  require(0<key<min(count,32768),'Index country slot invalid')
  if value:require(observer.ptr(value)%8==0,'Index value pointer alignment')
  entries.append((key,value))
 require(len({k for k,_ in entries})==len(entries),'Duplicate indexed country')
 require(r.read(root+0x140,16)==header,'Index header changed within sample')
 selected=[v for k,v in entries if k==other_slot]
 return dict(count=used,capacity=capacity,array=hex(array),header_raw_hex=header.hex(),
  records_raw_hex=raw.hex(),records_sha256=hashlib.sha256(raw).hexdigest(),
  key_present=bool(selected),selected_pointer=selected[0] if selected else 0,
  lookup_zero_reason=('matched_null_value' if selected and selected[0]==0 else 'missing_key' if not selected else None))

def sample_selected(r,observer,r24,base,root,table,handles,actor,target):
 require(root['count']==1380 and type(table) is bytes and len(table)==1380*8,'Full1380 table required')
 forward=r24.pair_sample(r,observer,base,root,handles,actor,target)
 reverse=r24.pair_sample(r,observer,base,root,handles,target,actor)
 pairs=[forward,reverse];r24.check_country_table_binding([dict(directional_pairs=pairs)],table)
 require(forward['actor']['address']!=forward['target']['address'],'Country pointer alias')
 left=nullable_index(r,observer,int(forward['relation_root'],16),forward['target']['slot'],1380)
 right=nullable_index(r,observer,int(reverse['relation_root'],16),reverse['target']['slot'],1380)
 require(left['selected_pointer']==right['selected_pointer'],'One-sided or mismatched selected task pointer')
 address=left['selected_pointer'];task=None
 if address:
  body=r.read(observer.ptr(address),0x40)
  first,second=struct.unpack_from('<QQ',body,0x10)
  require(struct.unpack_from('<Q',body)[0]==base+VT and struct.unpack_from('<I',body,8)[0]==357,
   'Other task vtable/marker; unknown, not absence')
  require(body[0x28]==0,'Nonzero raw byte at P+28; unknown, not absence')
  require({first,second}=={handles[actor],handles[target]},'Task full endpoint set differs')
  task=dict(address=hex(address),body_raw_hex=body.hex(),vtable_rva=hex(VT),
   endpoint1_at_10=hex(first),endpoint2_at_18=hex(second),
   raw_u32_at_08=struct.unpack_from('<I',body,8)[0],
   raw_u32_at_20=struct.unpack_from('<I',body,0x20)[0],raw_u32_at_24=struct.unpack_from('<I',body,0x24)[0],
   raw_byte_at_28=body[0x28],raw_u64_at_30=hex(struct.unpack_from('<Q',body,0x30)[0]),
   raw_u32_at_38=struct.unpack_from('<I',body,0x38)[0],raw_u32_at_3c=struct.unpack_from('<I',body,0x3c)[0],
   endpoint_business_roles_verified=False,complete_cpp_class_verified=False)
  state='selected_task_present'
 else:state='selected_task_absent'
 for item in (forward['actor'],forward['target']):
  fresh=r24.owned_country(r,observer,base,root,int(item['handle'],16),item['tag'])
  require(fresh==item and struct.unpack_from('<Q',table,item['slot']*8)[0]==int(item['address'],16),'Country/table changed within pass')
 require(observer.roots(r,base)==root,'Roots changed within pass')
 return dict(state=state,selected_task_present=bool(address),directional_pairs=pairs,
  forward_index=left,reverse_index=right,task=task,
  absence_scope='Both selected native-lookup values are zero; missing keys and matched NULL values remain separate facts.',
  extra_reader_guards_not_native_getter_checks=['Qii capacity at root+148','positive bounded unique keys',
   'canonical aligned nonzero pointers','both directions same selected value','typed vtable and raw357',
   'complete endpoint set','P+28 byte zero'],
  native_getter_does_not_check=['vtable','raw357','endpoints','P+28','capacity','uniqueness','full_handle'])

def base_result(operation):
 return dict(schema='EU4-SUPPORT-HEIR-CURRENT/1',operation=operation,status='unknown',game_sha256=GAME_SHA,selected_task_present=None,
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
     scope='host before/after, loaded code before/after, two fresh full tables and all selected reads; attempted counts include failures')
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
 states={'selected_task_present':True,'selected_task_absent':False}
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
  if operation=='catalog':out['profiles']=[dict(id='current_bilateral_support_heir_task',
   actions_for_reference=['support_heir','stop_supporting_heir'],current_only=True,states=['selected_task_present','selected_task_absent','unknown'],
   raw_fields_semantics='20/24/30/38/3c unknown; no date or progress; endpoints are unlabeled raw handles',profile_vtable_rva=hex(VT),
   unknowns=['complete class/lifecycle','request causality or acceptance','final heir result','persistent state'])]
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
