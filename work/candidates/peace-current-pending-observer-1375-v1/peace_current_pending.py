"""Current selected peace inbox only. Read-only candidate; never request/effect proof."""
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
DESIGN='work/reports/peace-current-pending-reader-design-20261016-r1/'
REVIEW='work/reports/peace-current-pending-reader-design-independent-review-20261016-r1/'
DIRECT='work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py'
DIRECT_MANIFEST='work/candidates/direct-truce-cache-cli-1375-v1/source-manifest.json'
OBSERVER='bridge/diplomacy_effect_observer.py'
JOB='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
VT=0x1c7b840
FIXED={
 DESIGN+'manifest.json':'cdf18bdd8e36eaca11db2d80b7f94b7f6cd444e09731e924f03868d81c6f4b03',
 DESIGN+'design.json':'8656c12a1fa9bcbcf8be5a2d5f378fab8324500da1eca5b7b50a2ac975562140',
 DESIGN+'loaded-code-candidates.json':'49a201eb2649bac908c2e370bfb5819cc3961d52e28454a2669bfd2702ad36be',
 REVIEW+'findings.json':'229908a7d5933b065ff18707df19f3e4a303f25b34050e53b7690d49772401e5',
 REVIEW+'manifest.json':'0b1ff8d258ef59b52b3a1c71feba2fd3b13e47b13ce23fa5f21f967bf901c01a',
 DIRECT:'5429932a8f4fb81180c566caa0905008d60880f51f7c5868dd7568b4040fe518',
 DIRECT_MANIFEST:'47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8',
 OBSERVER:'9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1',
 JOB:'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'}
OWN_NAMES=('peace_current_pending.py','test_peace_current_pending.py','README.md','build_manifest.py','run_offline.py')
REQUIRED={REL+'/'+n for n in OWN_NAMES}
RESEARCH_PREFIXES=('eu4_bridge_','eu4_pair_','eu4_spy_','eu4_tag_command_','tag_diplomacy')
FALSE_FLAGS=('selected_effect_verified','original_request_correlated','AI_acceptance_verified','AI_rejection_verified',
 'peace_completed','native_action_mapping_verified','native_ready','callable','world_lease','atomic_snapshot',
 'persistence_verified','native_getter_called','authorizes_retry')

def require(ok,message):
 if not ok:raise ValueError(message)

def read(path,maximum=4*1024*1024):
 with Path(path).open('rb') as f:b=f.read(maximum+1)
 require(0<len(b)<=maximum,'Source file bound');return b

def digest(b):return hashlib.sha256(b).hexdigest()
def pin(path):
 b=read(path);return dict(bytes=len(b),sha256=digest(b))

def local_path(name):
 require(type(name) is str and '\\' not in name and ':' not in name,'Source path encoding')
 p=PurePosixPath(name)
 require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==name,'Source path traversal')
 q=(ROOT/name).resolve();require(q.is_relative_to(ROOT.resolve()),'Source outside root');return q

def json_file(path):
 def unique(pairs):
  d={}
  for k,v in pairs:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 def invalid(_):raise ValueError('Nonfinite JSON')
 return json.loads(read(path).decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid)

def graph_digest(pins):return digest(json.dumps(pins,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii'))

def verify_sources(*,runtime=False):
 m=json_file(MANIFEST)
 require(m.get('schema')=='EU4-PEACE-CURRENT-PENDING-MANIFEST/1' and m.get('game_sha256')==GAME_SHA
  and type(m.get('sealed')) is bool and type(m.get('runtime_capture_authorized')) is bool,'Candidate manifest identity')
 expected=m.get('source_pins');require(type(expected) is dict and REQUIRED|set(FIXED)<=set(expected) and len(expected)<=96,'Source graph incomplete')
 actual={};total=0
 def check(name,p):
  nonlocal total
  require(type(p) is dict and set(p)=={'bytes','sha256'} and type(p['bytes']) is int and 0<p['bytes']<=4194304
   and type(p['sha256']) is str and re.fullmatch('[0-9a-f]{64}',p['sha256']),'Exact source pin shape')
  if name in actual:require(actual[name]==p,'Conflicting source pin');return
  total+=p['bytes'];require(total<=16*1024*1024,'Owner source graph bound')
  actual[name]=pin(local_path(name));require(actual[name]==p,'Source changed: '+name)
 for n,p in expected.items():check(n,p)
 for n,h in FIXED.items():require(actual[n]['sha256']==h,'Frozen source changed: '+n)
 owner=json_file(local_path(DESIGN+'manifest.json'))
 require(owner['sealed'] is True and owner['game_sha256']==GAME_SHA,'Design owner identity')
 for section in ('local_pins','captured_source_pins'):
  for n,p in owner[section].items():require(expected.get(n)==p,'Design owner source omitted or changed: '+n)
 review=json_file(local_path(REVIEW+'findings.json'))
 require(review.get('sealed') is True and review.get('passed') is True and review.get('blocking_findings')==[]
  and review.get('subject_manifest')==expected[DESIGN+'manifest.json'] and review.get('subject_design')==expected[DESIGN+'design.json'],
  'Independent design review subject differs')
 g=graph_digest(expected);require(m.get('source_graph_sha256')==g,'Source graph digest')
 if runtime or m['runtime_capture_authorized']:
  require(m['sealed'] is True and m['runtime_capture_authorized'] is True,'Source-ready and production review required before libraries/process')
  for key in ('independent_source_review','production_review'):
   rp=m.get(key);require(type(rp) is dict and set(rp)=={'path','bytes','sha256'},'Review path/pin required: '+key)
   check(rp['path'],{k:rp[k] for k in ('bytes','sha256')});v=json_file(local_path(rp['path']))
   require(v.get('sealed') is True and v.get('passed') is True and v.get('blocking_findings')==[]
    and v.get('subject_cli_pin')==expected[REL+'/peace_current_pending.py'] and v.get('subject_source_graph_sha256')==g,'Review exact subject: '+key)
   if key=='production_review':require(v.get('approved_for_current_readonly_status') is True,'Current read-only production approval required')
 return dict(manifest=pin(MANIFEST),source_pins=actual,source_graph_sha256=g,sealed=m['sealed'],runtime_capture_authorized=m['runtime_capture_authorized'])

def exact_compile(name,expected):
 p=local_path(name);b=read(p);require(dict(bytes=len(b),sha256=digest(b))==expected,'Exact library bytes changed')
 m=types.ModuleType('_peace_current_'+p.stem);m.__file__=str(p);exec(compile(b,str(p),'exec'),m.__dict__);return m

def code_buffers():
 d=json_file(local_path(DESIGN+'loaded-code-candidates.json'))
 require(d['game_sha256']==GAME_SHA and d['bytes_per_pass']==735 and d['bytes_pre_plus_post']==1470,'Loaded code profile identity')
 result=[]
 for row,expected in zip(d['ranges'],[(0x598af0,111),(0x59ba40,177),(0x4e8205,254),(0x360970,193)]):
  raw=bytes.fromhex(row['raw_hex']);rva=int(row['start_rva'],16)
  require((rva,len(raw))==expected and digest(raw)==row['sha256'],'Exact loaded code range');result.append((rva,raw))
 require(len(d['ranges'])==len(result)==4,'Exactly four loaded ranges');return result

class Libraries:
 def __init__(self,initial):
  self.initial=initial;self.direct=exact_compile(DIRECT,initial['source_pins'][DIRECT])
  self.frozen=self.direct.Libraries();self.host=self.frozen.host;self.r24=self.frozen.r24
  self.codes=code_buffers();self.guard()
 def guard(self):
  require(verify_sources()==self.initial,'Candidate source graph changed');self.frozen.guard()
 def observer(self):
  require(verify_sources(runtime=True)==self.initial,'Runtime source/production gates changed')
  self.guard();return self.frozen.observer()
 def disk_guard(self):
  before=GAME.stat();require(before.st_size==38462504,'Exact game disk size')
  h=hashlib.sha256();n=0
  with GAME.open('rb') as f:
   while b:=f.read(1024*1024):n+=len(b);require(n<=38462504,'Game disk grew');h.update(b)
  after=GAME.stat();require(n==before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns and h.hexdigest()==GAME_SHA,'Exact game disk SHA changed')
  return dict(bytes=n,sha256=h.hexdigest(),path=str(GAME.resolve()))
 def evidence(self):
  return dict(candidate=self.initial,reused_direct=self.frozen.evidence(),old_main_executed=False,
   old_fixed_pid_authority_reused=False,old_capture_executed=False,registered_argv_executed=False,
   runtime_entry_adapter='inherits frozen RuntimeCapture init/exit; same entry identity steps, PE8192 moved into shared budget/journal')

def selection(pid,creation,actor,target):
 require(type(pid) is int and 0<pid<=0xffffffff,'PID positive DWORD')
 require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)!=0,'Creation nonzero16hex')
 require(all(type(t) is str and re.fullmatch('[A-Z0-9]{3}',t) for t in (actor,target)) and actor!=target,'Distinct exact TAGs')
 return dict(pid=pid,creation=creation,actor=actor,target=target)

def pointer(p):require(type(p) is int and 0x10000<=p<2**47,'Canonical pointer lower bound');return p

class SharedReader:
 """One attempted-read budget from entry PE header through final host sample."""
 def __init__(self):
  self.raw=None;self.aligned=None;self.calls=self.bytes=self.largest=self.returned_bytes=0;self.entries=[];self.stage='entry'
 def bind(self,raw,aligned):self.raw=raw;self.aligned=aligned
 def _read(self,address,size,code=False):
  pointer(address);require(type(size) is int and 0<size<=65536 and address+size<=2**47,'Read span/size')
  require(self.calls<4096 and self.bytes+size<=512*1024,'Shared attempted-read budget exhausted')
  self.calls+=1;self.bytes+=size;self.largest=max(self.largest,size)
  row=dict(ordinal=self.calls,stage=self.stage,address=hex(address),requested_bytes=size,code_bytes=code,status='pending');self.entries.append(row)
  try:
   require(self.raw is not None and self.aligned is not None,'Read port not bound')
   b=(self.raw if code else self.aligned).read(address,size)
   require(type(b) is bytes,'RPM did not return bytes');self.returned_bytes+=len(b);row['returned_bytes']=len(b);row['raw_hex']=b.hex()
   require(len(b)==size,'Short RPM read');row['status']='complete';return b
  except BaseException as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
 def read(self,address,size):return self._read(address,size)
 def code(self,address,size):return self._read(address,size,True)
 def q(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def i(self,a):return struct.unpack('<i',self.read(a,4))[0]
 def b(self,a):return self.read(a,1)[0]

def capture_class(observer,libraries,r):
 class BudgetedCapture(observer.RuntimeCapture):
  def __enter__(self):
   self.backend.verify();self.runtime=observer.WindowsRuntime();self.held=self.runtime.readonly.Held(self.identity)
   try:
    self.held.identity_check();self.modules=self.held.modules();canonical=self.held.injector._canonical
    require(Path(self.held.injector.GAME).resolve()==GAME.resolve(),'Exact game path differs')
    require(not any(Path(p).name.lower().startswith(RESEARCH_PREFIXES) for _,p in self.modules),'Unexpected research module')
    games=[b for b,p in self.modules if canonical(p)==canonical(self.held.injector.GAME)]
    require(len(games)==1,'Exact single main module');self.base=pointer(games[0])
    raw=observer.HeldRPMPort(self.held);r.bind(raw,libraries.r24.AlignedPort(raw));r.stage='entry_PE'
    disk=self.runtime.readonly.disk_identity(self.held.injector.GAME)
    require(self.runtime.readonly.pe_header(r.read(self.base,8192))==disk,'Loaded main PE differs')
    self.initial_pins=observer.pins();return self
   except BaseException:
    self.held.close();self.held=None;raise
 return BudgetedCapture

class SharedView:
 def __init__(self,r):self.r=r;self.calls=self.bytes=self.largest=0
 def read(self,a,n):
  b=self.r.read(a,n);self.calls+=1;self.bytes+=n;self.largest=max(self.largest,n);return b
 def q(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def i(self,a):return struct.unpack('<i',self.read(a,4))[0]
 def b(self,a):return self.read(a,1)[0]

def host_sample(libraries,cap,observer,r):
 view=SharedView(r)
 return libraries.host.host_sample(cap,types.SimpleNamespace(roots=observer.roots,ptr=observer.ptr,BudgetReader=lambda _:view,HeldRPMPort=lambda _:None))

def code_guard(r,base,codes):
 out=[]
 for off,expected in codes:
  got=r.code(base+off,len(expected));require(got==expected,'Loaded code mismatch at '+hex(off));out.append(dict(rva=hex(off),bytes=len(got),raw_hex=got.hex(),sha256=digest(got)))
 return out

def queue_sample(r,base,recipient,actor_handle,target_handle):
 header_address=pointer(int(recipient['address'],16))+0x18d8
 header=r.read(header_address,21);head,tail,count,iteration=struct.unpack('<QQIB',header)
 require(iteration==0 and count<=128,'Unsupported iteration byte/count')
 require(bool(head)==bool(tail)==bool(count),'Head/tail/count mismatch')
 nodes=[];selected=[];seen_nodes=set();seen_actions=set();current=head;previous=0
 for _ in range(count):
  pointer(current);require(current not in seen_nodes,'Node cycle');seen_nodes.add(current)
  raw=r.read(current,25);action,prev,nxt,deleted=struct.unpack('<QQQB',raw)
  require(deleted==0,'Tombstone: action must not be dereferenced')
  require(prev==previous,'Previous link mismatch');pointer(action)
  require(action not in seen_actions,'Active action pointer alias');seen_actions.add(action)
  vt_raw=r.read(action,8);vt=struct.unpack('<Q',vt_raw)[0]
  node=dict(address=hex(current),node_raw_hex=raw.hex(),action=hex(action),vtable_raw_hex=vt_raw.hex(),type_match=vt==base+VT)
  if vt!=base+VT:
   require(r.read(action,8)==vt_raw,'Foreign vtable changed')
  else:
   body=r.read(action,64);require(body[:8]==vt_raw and struct.unpack_from('<I',body,8)[0]==357,'Peace vtable/marker changed')
   require(r.read(action,64)==body,'Peace prefix changed')
   a,o,t=struct.unpack_from('<QQQ',body,0x10)
   require(t==target_handle,'Peace recipient differs from queue owner')
   match=a==actor_handle or o==actor_handle
   if match:require(a==o==actor_handle,'Only one actor/original endpoint matches')
   node.update(body_raw_hex=body.hex(),selected=match)
   if match:
    ident=struct.unpack_from('<I',body,0x3c)[0]
    selected.append(dict(node=hex(current),action=hex(action),actor_handle=hex(a),original_actor_handle=hex(o),recipient_handle=hex(t),
     native_id_raw_u32=ident,native_id_raw_hex=body[0x3c:0x40].hex(),native_id_signed_projection=struct.unpack_from('<i',body,0x3c)[0],
     state_raw_u32=struct.unpack_from('<I',body,0x34)[0],field28_raw_u32=struct.unpack_from('<I',body,0x28)[0],
     field2c_raw_u32=struct.unpack_from('<I',body,0x2c)[0],field30_raw_u32=struct.unpack_from('<I',body,0x30)[0],
     field38_raw_byte=body[0x38],field39_raw_byte=body[0x39],prefix_raw_hex=body.hex()))
  require(r.read(current,25)==raw,'Node changed during action read')
  nodes.append(node);previous,current=current,nxt
 require(current==0 and previous==tail and len(nodes)==count,'Complete chain/tail/count mismatch')
 require(r.read(header_address,21)==header,'Queue header changed')
 return dict(header_raw_hex=header.hex(),head=hex(head),tail=hex(tail),declared_count_raw_u32=count,branch_byte=iteration,
  physical_count=len(nodes),active_count=len(nodes),nodes=nodes,selected=selected,selected_queue_presence=bool(selected),
  count_guard_scope='Supported no-tombstone/iteration0 profile, not a universal native active-count invariant')

def sample_selected(r,observer,libraries,base,root,table,handles,actor,target):
 require(root['count']==1380 and len(table)==1380*8,'Complete1380 table')
 a=libraries.r24.owned_country(r,observer,base,root,handles[actor],actor)
 t=libraries.r24.owned_country(r,observer,base,root,handles[target],target)
 require(a['address']!=t['address'],'Selected country alias')
 for item in (a,t):require(struct.unpack_from('<Q',table,item['slot']*8)[0]==int(item['address'],16),'Selected table binding')
 queue=queue_sample(r,base,t,handles[actor],handles[target])
 for item in (a,t):require(libraries.r24.owned_country(r,observer,base,root,int(item['handle'],16),item['tag'])==item,'Country changed after queue')
 require(r.read(int(root['array'],16),1380*8)==table,'Country table changed after queue')
 require(observer.roots(r,base)==root,'Root changed after queue')
 return dict(actor=a,target=t,roots=root,country_pointer_table_raw_hex=table.hex(),queue=queue)

def base_result(operation):
 return dict(schema='EU4-PEACE-CURRENT-PENDING/1',operation=operation,status='unknown',game_sha256=GAME_SHA,
  selected_queue_presence=None,**{k:False for k in FALSE_FLAGS},requests_published=0,native_game_calls=0,
  game_fields_written=0,hooks_installed=0,Frida_called=False,saves=0,reloads=0,automatic_retry=False,errors=[])

def observe(chosen,libraries):
 out=base_result('status');r=SharedReader();started=time.perf_counter()
 out.update(selection=selection(**chosen),captured_utc=datetime.now(timezone.utc).isoformat(),source_graph=libraries.evidence(),
  samples=[],precheck=None,postcheck=None,code_before=None,code_after=None,selected_two_pass_equal=False,
  normal_context_exit=False,held_handle_cleared=False,close_os_return_checked=False,commit_after_context_exit=False,
  process_rights='QUERY/VM_READ/SYNCHRONIZE')
 try:
  observer=libraries.observer();backend=observer.TagCommandBackend()
  identity=dict(pid=chosen['pid'],creation=chosen['creation'],session=secrets.token_hex(16),dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
  out.update(identity=identity,identity_purpose='Fresh readonly nonce, not installed session or original request')
  libraries.guard();out['disk_before']=libraries.disk_guard()
  with capture_class(observer,libraries,r)(identity,backend) as cap:
   try:
    r.stage='host_before';out['precheck']=host_sample(libraries,cap,observer,r)
    r.stage='code_before';out['code_before']=code_guard(r,cap.base,libraries.codes)
    for number in (1,2):
     r.stage='sample_'+str(number);root=observer.roots(r,cap.base)
     require(root==out['precheck']['roots'] and root['count']==1380 and root['manual_pause']==1,'Fresh paused root mismatch')
     require(r.i(cap.base+0x233e064)==-1,'Unsupported current Mod')
     table=r.read(int(root['array'],16),1380*8)
     handles=libraries.direct.selected_handles(r,observer,root,table,chosen['actor'],chosen['target'])
     out['samples'].append(sample_selected(r,observer,libraries,cap.base,root,table,handles,chosen['actor'],chosen['target']))
    require(out['samples'][0]==out['samples'][1],'Two complete passes differ');out['selected_two_pass_equal']=True
   except Exception as exc:out['errors'].append(dict(stage='sample',type=type(exc).__name__,message=str(exc)))
   finally:
    try:r.stage='code_after';out['code_after']=code_guard(r,cap.base,libraries.codes)
    except Exception as exc:out['errors'].append(dict(stage='code_after',type=type(exc).__name__,message=str(exc)))
    try:
     r.stage='host_after';out['postcheck']=host_sample(libraries,cap,observer,r)
     require(out['postcheck']==out['precheck'] and observer.pins()==cap.initial_pins,'Host/observer coherence changed');libraries.guard()
    except Exception as exc:out['errors'].append(dict(stage='host_sources_after',type=type(exc).__name__,message=str(exc)))
  out['normal_context_exit']=True
  require(cap.held is not None and cap.held.handle is None,'Held handle not cleared');out['held_handle_cleared']=True
  out['disk_after']=libraries.disk_guard();require(out['disk_after']==out['disk_before'],'Game disk identity changed');libraries.guard()
  if not out['errors'] and out['selected_two_pass_equal']:
   present=out['samples'][0]['queue']['selected_queue_presence']
   require(type(present) is bool,'Presence must be strict boolean')
   out.update(status='selected_peace_queue_present' if present else 'selected_peace_queue_absent',selected_queue_presence=present,commit_after_context_exit=True)
 except Exception as exc:
  out['errors'].append(dict(stage='context_or_source',type=type(exc).__name__,message=str(exc)))
  out.update(status='unknown',selected_queue_presence=None,commit_after_context_exit=False)
 out['raw_ordered_read_journal']=r.entries
 out['rpm_budget']=dict(calls_attempted=r.calls,bytes_requested=r.bytes,bytes_returned=r.returned_bytes,largest=r.largest,
  limits=dict(calls=4096,bytes=512*1024,single_read=65536),scope='Includes entryPE8192, host/code prepost, both tables/queues and every selected RPM attempt')
 out['duration_ms_including_guards']=round((time.perf_counter()-started)*1000,3);return out

def result_code(out):
 if out.get('operation') in ('check','catalog'):return 0 if out.get('status')=='files_verified' and out.get('errors')==[] else 2
 states={'selected_peace_queue_present':True,'selected_peace_queue_absent':False}
 okay=out.get('operation')=='status' and out.get('status') in states and type(out.get('selected_queue_presence')) is bool
 okay=okay and out['selected_queue_presence'] is states[out['status']] and out.get('errors')==[]
 okay=okay and all(out.get(k) is True for k in ('selected_two_pass_equal','normal_context_exit','held_handle_cleared','commit_after_context_exit'))
 okay=okay and all(out.get(k) is False for k in FALSE_FLAGS)
 return 0 if okay else 2

def run(operation,chosen=None,*,library_factory=Libraries):
 out=base_result(operation)
 try:
  require(operation in ('check','catalog','status'),'Unsupported operation')
  if operation=='status':require(type(chosen) is dict,'Exact selected PID/creation required');chosen=selection(**chosen)
  else:require(chosen is None,'File-only commands take no selection')
  initial=verify_sources(runtime=operation=='status');libraries=library_factory(initial)
  if operation=='status':return observe(chosen,libraries)
  out['source_graph']=libraries.evidence()
  if operation=='catalog':out['profiles']=[dict(id='current_selected_peace_queue',direction='actor->target inbox',current_only=True,
   states=['selected_peace_queue_present','selected_peace_queue_absent','unknown'],vtable_rva=hex(VT),action_prefix_bytes=64,
   raw_ID0_and_duplicates_allowed=True,raw_state_only=True,tombstone_before_action=True,
   unknowns=['request correlation','acceptance/rejection','terms/application/completion','queue deferred flush','class/lifetime/epoch'])]
  libraries.guard();out['status']='files_verified'
 except Exception as exc:out['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
 return out

class Parser(argparse.ArgumentParser):
 def error(self,message):raise ValueError(message)

def main(argv=None):
 p=Parser(description=__doc__,epilog='Exit0 means files verified or current presence/absence observed, never action success. Exit2 unknown/unsupported. No retry.')
 sub=p.add_subparsers(dest='operation',required=True);sub.add_parser('check');sub.add_parser('catalog')
 s=sub.add_parser('status');s.add_argument('--pid',type=int,required=True);s.add_argument('--creation',required=True);s.add_argument('--actor',required=True);s.add_argument('--target',required=True)
 try:
  args=vars(p.parse_args(argv));op=args.pop('operation');out=run(op,args if op=='status' else None)
 except Exception as exc:out=base_result('unknown');out['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
 print(json.dumps(out,ensure_ascii=True,sort_keys=True,indent=2));return result_code(out)

if __name__=='__main__':raise SystemExit(main())
