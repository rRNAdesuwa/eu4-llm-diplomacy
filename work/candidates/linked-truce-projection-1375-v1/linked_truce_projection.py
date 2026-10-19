"""Three bounded external normal-path projections; never executes a game predicate."""
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
SENTINEL=0x2d2d2d
P='work/reports/'
FIXED={
 'work/candidates/frida-entry-observer-1375-v1/job_tree.py':'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011',
 DIRECT:'5429932a8f4fb81180c566caa0905008d60880f51f7c5868dd7568b4040fe518',
 DIRECT_MANIFEST:'47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8',
 'bridge/diplomacy_effect_observer.py':'9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1',
 P+'war-peace-api-20261015-r23-truce-observation-contract/war/selected-decode.json':'e38c687f4f6d4f3321cddad7c7910112350491acb19cd2090fe8f74e868c08bc',
 P+'war-peace-api-20261015-r26-linked-truce-tails/war/selected-decode.json':'e59486834e38e541a243353b73673fb0e1170724282f258c86cb106ad2b5fb52',
 P+'war-peace-api-20261015-r37-linked-leaf-entry/war/selected-cfg.json':'fdd76416a42c5cc2b000707909eb6a0afcdd4a1aaca990c2c957d1207f83bb00',
 P+'war-peace-api-20261015-r38-dependency-crosswalk/war/crosswalk.json':'aab78fe19dddd2197e6acd3eb98f06da41537eb6cf89da2cec9bf54fd8102d7e',
 P+'war-peace-api-20261015-r38-independent-review/war/findings.json':'07308a07a4e38fdafa736247928f91c763eac37729e270a379f6ff79eefaa7fd',
 P+'war-peace-api-20261015-r40-linked-condition-closure/war/selected-cfg.json':'880152447a23b8a9b8878d466e2089aaace05cb5785b3a4d394eb5d1782c752e',
 P+'war-peace-api-20261015-r42-empty-linked-condition/war/projection.json':'5e7cd6bf875abc427d5bfd46a37a6683486fa3c0779ab0e1bccc26c1598047b8',
 P+'war-peace-api-20261015-r43-linked-cleanup-constant/war/capture.json':'2feef2cdb8fb7b2e8db3d0321f86505eef941eaa9ad9a0515a05b5cbbda279c5',
 P+'war-peace-api-20261015-r43-linked-cleanup-constant/war/delta.json':'d0239818c0496409ee535cf99a409acc8eb39ba205354a522a859a44a2b1a999',
 P+'war-peace-api-20261015-r43-independent-review/war/findings.json':'f1bda10a358ce338165a5031462cd8b6a753a9b4beed8f2e2c2a07118fafc6be'}
REQUIRED={REL+'/'+n for n in ('linked_truce_projection.py','test_linked_truce_projection.py','README.md','build_manifest.py','run_offline.py')}
RESEARCH_PREFIXES=('eu4_bridge_','eu4_pair_','eu4_spy_','eu4_tag_command_','tag_diplomacy')
PATH_ADDRESSES={
 'A_target_exact_sentinel':['3d79f0','3d79f7->3d7a45','3d7a47','2f15aa->2f160b','2f1612','506dcf->506e16','506e2a','506e42|506e54'],
 'B_linked_actor_byte11a_nonzero':['3d79f0 conditionalR38','2f15ac','2f15dd','2f15e8','2f15eb->2f160b','2f1612','506dd3->506e16','506e2a','506e42|506e54'],
 'C_independent_actor_zero_header_clear_linked_cache':['2f15ed','2f15f4','b1e066','b1e114->b1e6c3','b1e788','b1e841','b1e991','b1ebd2','b1ebe0->b1ec0f','b1ec32','2f1603','2f160a','506de8','506ded->506e16','506e2a','506e42|506e54']}


def require(value,message):
 if not value:raise ValueError(message)


def read(path,limit=4*1024*1024):
 with Path(path).open('rb') as f:b=f.read(limit+1)
 require(0<len(b)<=limit,'Selected file size bound');return b


def pin(path):
 b=read(path);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def local_path(name):
 require(type(name) is str and '\\' not in name and ':' not in name,'Source path type')
 p=PurePosixPath(name)
 require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==name,'Source path traversal')
 absolute=(ROOT/name).resolve();require(absolute.is_relative_to(ROOT.resolve()),'Source escape');return absolute


def json_file(path):
 def unique(pairs):
  out={}
  for k,v in pairs:require(k not in out,'Duplicate JSON key');out[k]=v
  return out
 def invalid(_):raise ValueError('Nonfinite JSON')
 return json.loads(read(path).decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid)


def verify_sources(path=MANIFEST,*,runtime=False):
 m=json_file(path)
 require(m.get('schema')=='EU4-LINKED-TRUCE-PROJECTION-MANIFEST/1' and m.get('game_sha256')==GAME_SHA
  and type(m.get('sealed')) is bool,'Candidate manifest identity')
 values=m.get('source_pins');require(type(values) is dict and REQUIRED|set(FIXED)<=set(values) and len(values)<=64,'Candidate source graph')
 actual={};total=0
 for n,wanted in values.items():
  require(type(wanted) is dict and set(wanted)=={'bytes','sha256'} and type(wanted['bytes']) is int
   and 0<wanted['bytes']<=4*1024*1024 and type(wanted['sha256']) is str and re.fullmatch('[0-9a-f]{64}',wanted['sha256']),'Source pin shape')
  total+=wanted['bytes'];require(total<=16*1024*1024,'Candidate source total bound')
  actual[n]=pin(local_path(n));require(actual[n]==wanted,'Candidate source changed: '+n)
 for n,h in FIXED.items():require(actual[n]['sha256']==h,'Frozen source root changed: '+n)
 if runtime:
  require(m['sealed'] is True and m.get('runtime_capture_authorized') is True,'Independent source-ready production manifest required before process observation')
  review=m.get('independent_source_review');require(type(review) is dict and set(review)=={'path','bytes','sha256'},'Independent source review pin required')
  require(pin(local_path(review['path']))=={k:review[k] for k in ('bytes','sha256')},'Independent source review changed')
 return dict(manifest=pin(path),source_pins=actual,sealed=m['sealed'],runtime_capture_authorized=m.get('runtime_capture_authorized') is True)


def exact_compile(name,expected):
 p=local_path(name);b=read(p)
 require(dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())==expected,'Exact-source library changed')
 module=types.ModuleType('_linked_projection_'+p.stem);module.__file__=str(p)
 exec(compile(b,str(p),'exec'),module.__dict__);return module


def code_buffers():
 r23=json_file(local_path(P+'war-peace-api-20261015-r23-truce-observation-contract/war/selected-decode.json'))
 r26=json_file(local_path(P+'war-peace-api-20261015-r26-linked-truce-tails/war/selected-decode.json'))
 r37=json_file(local_path(P+'war-peace-api-20261015-r37-linked-leaf-entry/war/selected-cfg.json'))
 r40=json_file(local_path(P+'war-peace-api-20261015-r40-linked-condition-closure/war/selected-cfg.json'))
 k=json_file(local_path(P+'war-peace-api-20261015-r43-linked-cleanup-constant/war/capture.json'))
 function=next(f for f in r26['complete_functions'] if f['entry_rva']=='0x2f1590')
 rows=function['instructions'];cursor=0x2f1590;joined=b''
 for row in rows:
  b=bytes.fromhex(row['bytes']);require(int(row['rva'],16)==cursor,'Retained2f rows not continuous');joined+=b;cursor+=len(b)
 require(cursor==0x2f1613,'Retained2f extent')
 result=[(0x506d70,bytes.fromhex(r23['selected_instruction_bytes_hex'])),(0x2f1590,joined),
  (0x3d79f0,bytes.fromhex(r37['raw_hex'])),(0xb1e020,bytes.fromhex(r40['prefix_raw_hex_reused']+r40['suffix_raw_hex'])),
  (0x1dc1c98,bytes.fromhex(k['target_raw_hex']))]
 require([len(b) for _,b in result]==[229,131,128,3421,8] and result[-1][1]==struct.pack('<Q',15),'Retained fixed code/K profile changed')
 return result


class Libraries:
 def __init__(self,initial):
  self.initial=initial
  self.direct=exact_compile(DIRECT,initial['source_pins'][DIRECT])
  self.frozen=self.direct.Libraries()
  self.host,self.r24=self.frozen.host,self.frozen.r24
  self.codes=code_buffers();self.guard()
 def guard(self):
  require(verify_sources()==self.initial,'Candidate source guards changed')
  self.frozen.guard()
 def observer(self):
  require(verify_sources(runtime=True)==self.initial,'Reviewed runtime sources required before observer construction')
  self.guard();return self.frozen.observer()
 def evidence(self):
  return dict(candidate=self.initial,direct_v1=self.frozen.evidence(),old_main_executed=False,
   old_fixed_pid_authority_reused=False,definition_exact_class_proven=False)


def selection(pid,creation,actor,target):
 require(type(pid) is int and 0<pid<=0xffffffff,'PID positive DWORD')
 require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)!=0,'Creation FILETIME')
 require(all(type(t) is str and re.fullmatch('[A-Z0-9]{3}',t) for t in (actor,target)) and actor!=target,'Distinct exact TAGs')
 return dict(pid=pid,creation=creation,actor=actor,target=target)


def ordinary_handle(value):
 require(type(value) is str and re.fullmatch('0x[0-9a-f]+',value),'Hex full handle required')
 h=int(value,16);slot=(h>>32)&0xffff
 require(0<h<2**64 and h>>56!=0 and (h>>48)&255==0 and (h>>24)&255==0 and 0<slot<1380
  and re.fullmatch(rb'[A-Z0-9]{3}',(h&0xffffff).to_bytes(3,'little')),'Ordinary positive full handle')
 return h


def project_facts(facts):
 out=dict(supported=False,path=None,selected_native_return_projection=None,reason=None)
 try:
  require(type(facts) is dict,'Projection facts object')
  a=ordinary_handle(facts['actor_handle']);t=ordinary_handle(facts['target_handle']);require(a!=t,'Distinct full pair')
  direct=facts['direct_pair_cache_flag_set'];require(type(direct) is bool,'Direct cache must be explicit boolean')
  linked=facts['target_linked_handle']
  if linked==hex(SENTINEL):path='A_target_exact_sentinel'
  else:
   linked_value=ordinary_handle(linked);require(linked_value!=t,'Target selflinked unsupported')
   require(facts.get('dependency_guarded') is True,'Bilateral typed dependency/profile unproved')
   require(type(facts.get('dependency_key')) is str and re.fullmatch('[a-z0-9_]{1,96}',facts['dependency_key']),'Dependency key')
   flag=facts.get('definition_byte_11a');require(type(flag) is int and 0<=flag<=255,'Definition raw byte missing')
   if flag!=0 and linked_value==a:path='B_linked_actor_byte11a_nonzero'
   else:
    require(facts.get('actor_linked_handle')==hex(SENTINEL),'Actor independent exact sentinel required')
    require(linked_value!=a,'C actor-linked selfpair unsupported')
    h=facts.get('definition_header');require(type(h) is dict and set(h)=={'0x60','0x61','0x62','0x63'},'Four explicit header bytes required')
    require(all(type(v) is int and v==0 for v in h.values()),'Unsupported nonempty raw header')
    require(type(facts.get('loaded_K')) is int and facts['loaded_K']==15,'LoadedK15 profile missing')
    cache=facts.get('actor_linked_cache_flag_set');require(type(cache) is bool and cache is False,'Actor-linked cache must be observed clear; external7ae unsupported')
    path='C_independent_actor_zero_header_clear_linked_cache'
  out.update(supported=True,path=path,selected_native_return_projection=direct,
   retained_instruction_path=PATH_ADDRESSES[path],path_is_external_hypothesis_not_executed_trace=True)
 except (ValueError,KeyError,TypeError) as exc:out['reason']=str(exc)
 return out


class JournalPort:
 def __init__(self,port):self.port=port;self.entries=[];self.stage='unassigned'
 def read(self,address,size):
  item=dict(ordinal=len(self.entries)+1,stage=self.stage,address=hex(address),bytes=size,status='pending');self.entries.append(item)
  try:
   raw=self.port.read(address,size);require(type(raw) is bytes and len(raw)==size,'Exact journal read')
   item.update(status='complete',raw_hex=raw.hex());return raw
  except Exception as exc:item.update(status='failed',error=type(exc).__name__+': '+str(exc));raise


def guarded_country(r,observer,r24,base,root,table,handle,tag=None):
 slot,actual=observer.full_handle(handle,root['count'],tag=tag)
 item=r24.owned_country(r,observer,base,root,handle,actual)
 require(struct.unpack_from('<Q',table,slot*8)[0]==int(item['address'],16),'Country current pointer-table binding differs')
 return item


def sample_selected(r,observer,r24,base,root,table,handles,actor,target,*,loaded_K):
 require(root['count']==1380 and len(table)==1380*8,'Complete1380 country table required')
 direct=r24.pair_sample(r,observer,base,root,handles,actor,target)
 r24.check_country_table_binding([dict(directional_pairs=[direct])],table)
 a,t=direct['actor'],direct['target'];require(a['address']!=t['address'],'Country address alias')
 target_link=r.q(int(t['address'],16)+0x18f0)
 facts=dict(actor_handle=a['handle'],target_handle=t['handle'],target_linked_handle=hex(target_link),
  direct_pair_cache_flag_set=direct['direct_pair_cache_flag_set'])
 sample=dict(facts=facts,directional_pairs=[direct],countries=[a,t],dependency=None,definition_exact_class_proven=False)
 if target_link!=SENTINEL:
  linked=guarded_country(r,observer,r24,base,root,table,target_link)
  require(linked['handle']!=t['handle'] and linked['address']!=t['address'],'Selflinked target unsupported')
  if linked['handle']!=a['handle']:require(linked['slot']!=a['slot'] and linked['address']!=a['address'],'Linked/actor identity alias')
  chosen={actor:int(a['handle'],16),target:int(t['handle'],16),linked['tag']:target_link}
  forward=r24.pair_sample(r,observer,base,root,chosen,target,linked['tag'])
  reverse=r24.pair_sample(r,observer,base,root,chosen,linked['tag'],target)
  sample['directional_pairs'] += [forward,reverse];sample['countries'].append(linked)
  left=observer.index(r,int(forward['relation_root'],16),0x128,linked['slot'],root['count'])
  right=observer.index(r,int(reverse['relation_root'],16),0x128,t['slot'],root['count'])
  require(left['member'] is True and right['member'] is True and left['object']==right['object'] and left['object'] is not None,'Bilateral dependency absent/mismatch')
  obj=left['object'];body=r.read(obj,0x48);first,second=struct.unpack_from('<QQ',body,0x10)
  require(struct.unpack_from('<Q',body)[0]==base+observer.DEPENDENCY_VT and body[0x28]==0
   and {first,second}=={int(t['handle'],16),target_link},'Dependency vtable/full endpoints/removed mismatch')
  definition=struct.unpack_from('<Q',body,0x40)[0];key=observer.dependency_key(r,definition)
  flag=r.b(definition+0x11a)
  facts.update(dependency_guarded=True,dependency_key=key,definition_byte_11a=flag)
  sample['dependency']=dict(forward_index=left,reverse_index=right,object=hex(obj),body_raw_hex=body.hex(),
   definition_pointer=hex(definition),definition_key=key,definition_exact_class_size_vtable_proven=False,
   source_pointer_path='target linked full country; bilateral root+0x128; same typedP; QWORD[P+0x40] only')
  if not (flag!=0 and linked['handle']==a['handle']):
   actor_link=r.q(int(a['address'],16)+0x18f0);facts['actor_linked_handle']=hex(actor_link)
   if actor_link==SENTINEL and linked['handle']!=a['handle']:
    facts['definition_header']={hex(off):r.b(definition+0x1c8+off) for off in (0x61,0x60,0x62,0x63)}
    facts['loaded_K']=loaded_K
    if all(v==0 for v in facts['definition_header'].values()):
     extra=r24.pair_sample(r,observer,base,root,chosen,actor,linked['tag'])
     sample['directional_pairs'].append(extra);facts['actor_linked_cache_flag_set']=extra['direct_pair_cache_flag_set']
  r24.check_country_table_binding([sample],table)
 for item in sample['countries']:
  current=guarded_country(r,observer,r24,base,root,table,int(item['handle'],16),item['tag'])
  require(current==item,'Selected country changed within sample')
 require(observer.roots(r,base)==root,'Roots changed within sample')
 sample['projection']=project_facts(facts)
 return sample


def code_guard(r,base,codes):
 out=[]
 for offset,expected in codes:
  raw=r.read(base+offset,len(expected));require(raw==expected,'Loaded code/K fixed profile mismatch at '+hex(offset))
  out.append(dict(rva=hex(offset),bytes=len(raw),raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest()))
 return out


def base_result(operation):
 return dict(schema='EU4-LINKED-TRUCE-PROJECTION/1',operation=operation,status='unknown',
  selected_native_return_projection=None,actual_native_predicate_evaluated=False,
  selected_effect_verified=False,peace_completion_verified=False,expiry_verified=False,request_effect_verified=False,
  truce_object_verified=False,native_ready=False,lifetime_lease=False,atomic_snapshot=False,
  native_game_calls=0,requests_published=0,game_fields_written=0,hooks_installed=0,Frida_called=False,
  saves=0,reloads=0,automatic_retry=False,errors=[])


def observe(chosen,libraries):
 chosen=selection(**chosen);out=base_result('status');out.update(selection=chosen,samples=[],raw_ordered_read_journal=[],
  captured_utc=datetime.now(timezone.utc).isoformat(),source_graph=libraries.evidence(),
  precheck=None,postcheck=None,code_before=None,code_after=None,selected_two_pass_equal=False,
  normal_context_exit=False,held_handle_cleared=False,close_os_return_checked=False,commit_after_context_exit=False,
  process_rights='QUERY/VM_READ/SYNCHRONIZE',budget_accounting={'entry_PE_identity_bytes_excluded_from_selected':8192})
 start=time.perf_counter()
 try:
  observer=libraries.observer();backend=observer.TagCommandBackend()
  identity=dict(pid=chosen['pid'],creation=chosen['creation'],session=secrets.token_hex(16),
   dll_sha256=backend.manifest['dll']['sha256'],manifest_sha256=backend.manifest_sha)
  out['identity']=identity;out['identity_purpose']='fresh readonly correlation nonce, no installedsession/request authority'
  libraries.guard()
  with observer.RuntimeCapture(identity,backend) as cap:
   require(Path(cap.held.injector.GAME).resolve()==GAME.resolve(),'Exact target game path')
   require(not any(Path(p).name.lower().startswith(RESEARCH_PREFIXES) for _,p in cap.modules),'Unexpected research module')
   out['precheck']=libraries.host.host_sample(cap,observer)
   journal=JournalPort(libraries.r24.AlignedPort(observer.HeldRPMPort(cap.held)))
   r=observer.BudgetReader(journal)
   try:
    journal.stage='code_before';out['code_before']=code_guard(r,cap.base,libraries.codes)
    for number in (1,2):
     journal.stage='sample_'+str(number)
     root=observer.roots(r,cap.base);require(root==out['precheck']['roots'] and root['manual_pause']==1,'Paused roots/host differ')
     table=r.read(int(root['array'],16),root['count']*8)
     handles=libraries.direct.selected_handles(r,observer,root,table,chosen['actor'],chosen['target'])
     observed_K=struct.unpack('<Q',bytes.fromhex(out['code_before'][-1]['raw_hex']))[0]
     sample=sample_selected(r,observer,libraries.r24,cap.base,root,table,handles,chosen['actor'],chosen['target'],loaded_K=observed_K)
     sample.update(roots=root,country_pointer_table_raw_hex=table.hex(),selected_handles={k:hex(v) for k,v in handles.items()})
     out['samples'].append(sample)
    require(out['samples'][0]==out['samples'][1],'Two complete selected passes differ')
    out['selected_two_pass_equal']=True
   except Exception as exc:out['errors'].append(dict(stage='selected',type=type(exc).__name__,message=str(exc)))
   finally:
    try:journal.stage='code_after';out['code_after']=code_guard(r,cap.base,libraries.codes)
    except Exception as exc:out['errors'].append(dict(stage='code_after',type=type(exc).__name__,message=str(exc)))
    out['raw_ordered_read_journal']=journal.entries
    out['budget_accounting']['selected']=dict(calls=r.calls,bytes=r.bytes,largest=r.largest,
     scope='shared BudgetReaderattempts including orderedcode/K+2fresh1380tables+selected objects; incomplete read not OSsuccess')
    try:
     out['postcheck']=libraries.host.host_sample(cap,observer)
     require(out['postcheck']==out['precheck'] and observer.pins()==cap.initial_pins,'Host/source postguards differ')
     libraries.guard()
    except Exception as exc:out['errors'].append(dict(stage='host_source_after',type=type(exc).__name__,message=str(exc)))
  out['normal_context_exit']=True
  require(cap.held is not None and cap.held.handle is None,'Held handle not cleared after context exit')
  out['held_handle_cleared']=True;libraries.guard()
  out['budget_accounting']['host_pre_and_post']=dict(pre=out['precheck'].get('rpm_budget'),post=out['postcheck'].get('rpm_budget'))
  if not out['errors'] and out['selected_two_pass_equal']:
   projected=out['samples'][0]['projection']
   if projected['supported'] is True and type(projected['selected_native_return_projection']) is bool:
    out.update(status='computed_selected_native_return_projection',selected_native_return_projection=projected['selected_native_return_projection'],
     path=projected['path'],commit_after_context_exit=True)
   else:out['unsupported_reason']=projected['reason']
 except Exception as exc:
  out['errors'].append(dict(stage='context_or_source',type=type(exc).__name__,message=str(exc)))
  out['status']='unknown';out['selected_native_return_projection']=None;out['commit_after_context_exit']=False
 out['duration_ms_including_guards']=round((time.perf_counter()-start)*1000,3)
 return out


def result_code(out):
 if out.get('operation') in ('check','catalog'):return 0 if out.get('status')=='files_verified' else 2
 okay=out.get('status')=='computed_selected_native_return_projection' and type(out.get('selected_native_return_projection')) is bool and out.get('errors')==[]
 okay=okay and all(out.get(k) is True for k in ('selected_two_pass_equal','normal_context_exit','held_handle_cleared','commit_after_context_exit'))
 return 0 if okay else 2


def run(operation,chosen=None,*,library_factory=Libraries):
 out=base_result(operation)
 try:
  require(operation in ('check','catalog','status'),'Unsupported operation')
  if operation=='status':require(type(chosen) is dict,'Exact selection required');chosen=selection(**chosen)
  else:require(chosen is None,'File-only operation takes no selection')
  initial=verify_sources(runtime=operation=='status')
  libraries=library_factory(initial)
  if operation=='status':return observe(chosen,libraries)
  out['source_graph']=libraries.evidence()
  if operation=='catalog':out['profiles']=[dict(id=x,selected_return='direct actor->target cache',actual_native_predicate_evaluated=False) for x in ('A_target_exact_sentinel','B_linked_actor_byte11a_nonzero','C_independent_actor_zero_header_clear_linked_cache')]
  libraries.guard();out['status']='files_verified'
 except Exception as exc:out['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
 return out


class Parser(argparse.ArgumentParser):
 def error(self,message):raise ValueError(message)


def main(argv=None):
 parser=Parser(description=__doc__,epilog='Exit0 includes computedtrue or computedfalse, never action completion. Exit2 unknown/unsupported; never retry automatically.')
 sub=parser.add_subparsers(dest='operation',required=True);sub.add_parser('check');sub.add_parser('catalog')
 status=sub.add_parser('status');status.add_argument('--pid',type=int,required=True);status.add_argument('--creation',required=True)
 status.add_argument('--actor',required=True);status.add_argument('--target',required=True)
 try:
  args=vars(parser.parse_args(argv));operation=args.pop('operation');out=run(operation,args if operation=='status' else None)
 except Exception as exc:out=base_result('unknown');out['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
 print(json.dumps(out,ensure_ascii=True,sort_keys=True,indent=2));return result_code(out)


if __name__=='__main__':raise SystemExit(main())
