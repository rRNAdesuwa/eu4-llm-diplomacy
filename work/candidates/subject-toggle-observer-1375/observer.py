"""Fixed FRA/NAV raw readonly subject-toggle observer. No CLI or native calls."""
import hashlib,importlib.util,json,re,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
MIL_PATH='work/candidates/subject-military-focus-observer-1375/observer.py'
MIL_SHA='d03c53ddae7735d4ee2b521dd878fb5bc9045a509a9b56d80ae48f0597367edc'
CONTRACT_SHA='718f128f5656c056f1944d2715bd7a2db9004da57c2b9a02fd4eba97fd331241'
def bounded(p,n):
 with Path(p).open('rb') as f:b=f.read(n+1)
 if len(b)>n:raise ValueError('bounded source')
 return b
raw=bounded(ROOT/MIL_PATH,65536);assert hashlib.sha256(raw).hexdigest()==MIL_SHA
spec=importlib.util.spec_from_file_location('_toggle_frozen_mil',ROOT/MIL_PATH)
mil=importlib.util.module_from_spec(spec);spec.loader.exec_module(mil)
assert Path(mil.__file__).resolve()==(ROOT/MIL_PATH).resolve() and mil.ROOT==ROOT
require=mil.require;integer=mil.integer;ptr=mil.ptr;exact=mil.exact;canonical=mil.canonical;ReadError=mil.ReadError;Budget=mil.Budget
FRA=mil.FRA;NAV=mil.NAV;EXE_SHA=mil.EXE_SHA;MAX_CHAIN=256;MAX_BUCKETS=4096
FALSE_CLAIMS=mil.FALSE_CLAIMS+('visibility_verified','side_effects_verified','permission_map_authorizes_native')
def contract():
 b=bounded(HERE/'contract.json',1024*1024);require(hashlib.sha256(b).hexdigest()==CONTRACT_SHA,'contract pin');return json.loads(b)
def dependencies(c):
 mil.dependencies()
 for p,d in c['sources'].items():
  b=bounded(ROOT/p,8*1024*1024);require(len(b)==d['bytes'] and hashlib.sha256(b).hexdigest()==d['sha256'],'source pin '+p)
def known(c,base):return {base+int(x['singleton_rva'],16):x for x in c['known_singletons']}
def pins(r,base,c):
 mil.pins(r,base,mil.contract())
 for row in c['instruction_pins']:
  b=bytes.fromhex(row['bytes']);require(r.read(base+int(row['rva'],16),len(b))==b,'toggle code pin')
 for row in c['vtable_pins']:
  raw=bytes.fromhex(row['bytes']);require(len(raw)==72,'singleton vtable width')
  for off in range(0,len(raw),8):
   expected=struct.unpack_from('<Q',raw,off)[0]-0x140000000+base
   require(r.q(base+int(row['rva'],16)+off)==expected,'toggle relocated vtable')
def token_hash(token):
 integer(token,0,0xffffffff);v=0xcbf29ce484222325
 for x in token.to_bytes(4,'little'):v=((v^x)*0x100000001b3)&0xffffffffffffffff
 return v
def object_row(r,address,base,allow):
 ptr(address);require(address in allow,'unknown registered singleton')
 expected=allow[address];vt=r.q(address);require(vt==base+int(expected['vtable_rva'],16),'unregistered singleton vtable')
 token=r.i(address+8);require(token==expected['token'],'singleton token differs')
 return dict(address=address,vtable=vt,token=token)
def registrations(r,base,c):
 allow=known(c,base);count=integer(r.i(base+0x1fd5228),3,len(allow));bcount=integer(r.i(base+0x1fd522c),1,MAX_BUCKETS)
 buckets=ptr(r.q(base+0x1fd5230));v=mil.vector(r,r.q(base+0x23581c8),r.q(base+0x23581d0),r.q(base+0x23581d8),256)
 require(len(v['values'])==count and len(set(v['values']))==count and set(v['values'])<=set(allow),'registration enumeration')
 lookups={};singletons={}
 for name,f in c['families'].items():
  address=base+int(f['singleton_rva'],16);require(address in v['values'],'selected singleton not enumerated')
  obj=object_row(r,address,base,allow);enabled=integer(r.b(address+12),1,1);direct=integer(r.b(address+13),0,0)
  singletons[name]={**obj,'uses_command':enabled,'direct_effect':direct}
  bucket=buckets+(f['token']%bcount)*8;head=ptr(r.q(bucket),True);node=head;nodes=[];seen=set()
  while node:
   require(len(nodes)<min(count,MAX_CHAIN) and node not in seen,'singleton chain limit/cycle');seen.add(node)
   member=ptr(r.q(node));nxt=ptr(r.q(node+8),True);obj=object_row(r,member,base,allow)
   require(member in v['values'] and obj['token']%bcount==f['token']%bcount,'singleton wrong bucket/member')
   nodes.append(dict(address=node,next=nxt,object=obj));node=nxt
  require([x['object']['address'] for x in nodes if x['object']['token']==f['token']]==[address],'selected singleton missing/duplicate')
  lookups[name]=dict(bucket=bucket,head=head,nodes=nodes)
 return dict(entry_count=count,bucket_count=bcount,buckets=buckets,vector=v,singletons=singletons,lookups=lookups)
def permission_map(r,definition,c):
 sentinel=ptr(r.q(definition+0x470));size=integer(r.q(definition+0x478),0,4096)
 v=mil.vector(r,r.q(definition+0x480),r.q(definition+0x488),r.q(definition+0x490),MAX_BUCKETS*2)
 count=integer(r.q(definition+0x4a0),1,MAX_BUCKETS);mask=integer(r.q(definition+0x498),0,MAX_BUCKETS-1)
 require(mask==count-1 and count&(count-1)==0 and len(v['values'])==count*2,'permission bucket vector/count/mask')
 for p in v['values']:ptr(p)
 if size==0:require(all(p==sentinel for p in v['values']),'empty permission map with nodes')
 allow={x['token'] for x in c['known_singletons']};lookups={}
 for name,f in c['families'].items():
  h=token_hash(f['token']);index=h&mask;first,last=v['values'][index*2:index*2+2];nodes=[]
  require((first==sentinel)==(last==sentinel),'permission half-empty bucket')
  if first!=sentinel:
   node=last;seen=set();later=None
   while True:
    require(node!=sentinel and node not in seen and len(nodes)<min(size,MAX_CHAIN),'permission chain limit/cycle');seen.add(node)
    nxt=ptr(r.q(node));previous=ptr(r.q(node+8));token=integer(r.i(node+16),0,0xffffffff);value=integer(r.b(node+20),0,1)
    require(token in allow and token_hash(token)&mask==index,'unknown/wrong-bucket permission token')
    require(later is None or nxt==later,'permission backlink')
    nodes.append(dict(address=node,next=nxt,previous=previous,token=token,allowed=value))
    if node==first:break
    later=node;node=previous
  require(len({x['token'] for x in nodes})==len(nodes),'duplicate permission token')
  matching=[x for x in nodes if x['token']==f['token']]
  lookups[name]=dict(hash=h,bucket=v['begin']+index*16,first=first,last=last,nodes=nodes,found=bool(matching),allowed=bool(matching and matching[0]['allowed']))
 return dict(address=definition+0x468,sentinel=sentinel,size=size,vector=v,mask=mask,bucket_count=count,lookups=lookups)
def selected_states(base,raw,pmap,c):
 direct=base['identity']['countries']['NAV']['overlord']>>56!=0
 return {n:dict(token=f['token'],mask=f['mask'],current=bool(direct and raw['subject_flags']&f['mask']),definition_allows=pmap['lookups'][n]['allowed'],
  family_local_condition=(raw['subject_at_war']==0 if n=='scutage' else (bool(raw['subject_flags']&f['mask']) or raw['actor_rival_count']!=0) if n=='embargo_rivals' else True)) for n,f in c['families'].items()}
def snapshot(r,base,c):
 graph=mil.snapshot(r,base,mil.contract());reg=pmap=fields=states=None
 if graph['scope_status']=='direct_subject_graph_observed':
  reg=registrations(r,base,c);pmap=permission_map(r,graph['definition']['address'],c)
  actor=graph['identity']['countries']['FRA']['address'];target=graph['identity']['countries']['NAV']['address']
  fields=dict(subject_flags=r.i(target+0x78)&0xffffffff,actor_presence=r.i(actor+0x1344),actor_marker=r.b(actor+0x26),actor_rival_count=r.i(actor+0x2258),subject_at_war=r.b(target+0x289b))
  states=selected_states(graph,fields,pmap,c)
 result=dict(graph=graph,registrations=reg,permission_map=pmap,raw_fields=fields,states=states)
 require(canonical(mil.support.roots(r,base,'NAV'))==canonical(graph['identity']),'roots changed during toggle pass')
 inspect(result,c);return result
def inspect(s,c=None):
 c=c or contract();exact(s,'graph registrations permission_map raw_fields states');mil.inspect(s['graph']);graph=s['graph'];base=graph['identity']['base']
 if graph['scope_status']!='direct_subject_graph_observed':
  require(all(s[k] is None for k in ('registrations','permission_map','raw_fields','states')),'outside graph cannot claim toggle state');return True
 allow=known(c,base);reg=s['registrations'];exact(reg,'entry_count bucket_count buckets vector singletons lookups')
 count=integer(reg['entry_count'],3,len(allow));bc=integer(reg['bucket_count'],1,MAX_BUCKETS);ptr(reg['buckets']);mil.validate_vector(reg['vector'],256);values=reg['vector']['values']
 require(len(values)==len(set(values))==count and set(values)<=set(allow),'registration vector count/type')
 exact(reg['singletons'],' '.join(c['families']));exact(reg['lookups'],' '.join(c['families']));all_nodes={};members=set()
 def check_object(x):
  exact(x,'address vtable token');address=ptr(x['address']);require(address in allow,'unknown singleton');row=allow[address]
  require(ptr(x['vtable'])==base+int(row['vtable_rva'],16) and integer(x['token'],0,0xffffffff)==row['token'],'singleton identity')
 for name,f in c['families'].items():
  obj=reg['singletons'][name];exact(obj,'address vtable token uses_command direct_effect');check_object({k:obj[k] for k in ('address','vtable','token')})
  expected=base+int(f['singleton_rva'],16);require(obj['address']==expected and expected in values,'selected singleton binding');integer(obj['uses_command'],1,1);integer(obj['direct_effect'],0,0)
  q=reg['lookups'][name];exact(q,'bucket head nodes');require(ptr(q['bucket'])==reg['buckets']+(f['token']%bc)*8,'singleton bucket');node=ptr(q['head'],True);require(type(q['nodes']) is list and len(q['nodes'])<=min(count,MAX_CHAIN),'singleton nodes')
  seen=set();tokens=set();matches=[]
  for x in q['nodes']:
   exact(x,'address next object');require(ptr(x['address'])==node and node not in seen,'singleton chain');seen.add(node);check_object(x['object']);obj=x['object'];token=obj['token']
   require(obj['address'] in values and token%bc==f['token']%bc and token not in tokens,'singleton bucket duplicate/type');tokens.add(token)
   if token==f['token']:matches.append(obj['address'])
   if node in all_nodes:require(canonical(all_nodes[node])==canonical(x),'repeated singleton node differs')
   all_nodes[node]=x;members.add(obj['address']);node=ptr(x['next'],True)
  require(node==0 and matches==[expected],'singleton chain incomplete or missing')
 require(len(all_nodes)<=count and len(members)==len(all_nodes),'singleton selected enumeration mismatch')
 p=s['permission_map'];exact(p,'address sentinel size vector mask bucket_count lookups');require(ptr(p['address'])==graph['definition']['address']+0x468,'permission definition binding');ptr(p['sentinel']);size=integer(p['size'],0,4096);bc=integer(p['bucket_count'],1,MAX_BUCKETS);mask=integer(p['mask'],0,MAX_BUCKETS-1)
 require(mask==bc-1 and bc&(bc-1)==0,'permission mask/count');mil.validate_vector(p['vector'],MAX_BUCKETS*2);values=p['vector']['values'];require(len(values)==bc*2,'permission vector count')
 if size==0:require(all(x==p['sentinel'] for x in values),'empty permission table')
 exact(p['lookups'],' '.join(c['families']));allowed_tokens={x['token'] for x in c['known_singletons']};all_nodes={};all_tokens={}
 for name,f in c['families'].items():
  q=p['lookups'][name];exact(q,'hash bucket first last nodes found allowed');h=token_hash(f['token']);index=h&mask
  require(integer(q['hash'])==h and ptr(q['bucket'])==p['vector']['begin']+index*16,'permission hash/bucket');require(ptr(q['first'])==values[index*2] and ptr(q['last'])==values[index*2+1],'permission endpoints')
  require((q['first']==p['sentinel'])==(q['last']==p['sentinel']),'half-empty permission bucket')
  require(type(q['nodes']) is list and len(q['nodes'])<=min(size,MAX_CHAIN),'permission chain bound');node=q['last'];later=None;seen=set();tokens=set();matching=[]
  for x in q['nodes']:
   exact(x,'address next previous token allowed');require(ptr(x['address'])==node and node!=p['sentinel'] and node not in seen,'permission node identity/cycle');seen.add(node);ptr(x['next']);ptr(x['previous']);token=integer(x['token'],0,0xffffffff);integer(x['allowed'],0,1)
   require(token in allowed_tokens and token not in tokens and token_hash(token)&mask==index,'permission key type/hash/duplicate');tokens.add(token)
   require(later is None or x['next']==later,'permission backlink')
   if token==f['token']:matching.append(x)
   if node in all_nodes:require(canonical(all_nodes[node])==canonical(x),'repeated permission node differs')
   require(token not in all_tokens or all_tokens[token]==node,'permission token aliases nodes');all_nodes[node]=x;all_tokens[token]=node;later=node;node=x['previous']
  require((not q['nodes'] and q['first']==p['sentinel']) or (q['nodes'] and later==q['first']),'permission chain incomplete')
  require(type(q['found']) is bool and q['found']==bool(matching) and type(q['allowed']) is bool and q['allowed']==bool(matching and matching[0]['allowed']),'permission summary')
 require(len(all_nodes)<=size,'permission selected count exceeds map size')
 fields=s['raw_fields'];exact(fields,'subject_flags actor_presence actor_marker actor_rival_count subject_at_war');integer(fields['subject_flags'],0,0xffffffff);integer(fields['actor_presence'],-2**31,2**31-1);require(integer(fields['actor_marker'],0,255)==(FRA>>48)&255,'actor marker/full handle');integer(fields['actor_rival_count'],0,4096);integer(fields['subject_at_war'],0,1)
 require(canonical(s['states'])==canonical(selected_states(graph,fields,p,c)),'derived current/allowed/local predicate differs');return True
def capture(reader,base):
 ptr(base);c=contract();r=Budget(reader);pins(r,base,c);first=snapshot(r,base,c);second=snapshot(r,base,c)
 require(canonical(first)==canonical(second),'two-pass toggle state changed');pins(r,base,c)
 return dict(profile=c['profile'],contract_sha256=CONTRACT_SHA,passes=[first,second],snapshot=first,two_pass_equal=True,atomic=False,source_kind='injected_reader_not_process_attested',
  unsupported=c['unsupported'],read_budget=dict(bytes=r.bytes,calls=len(r.trace),max_bytes=mil.support.MAX_TOTAL,max_calls=mil.support.MAX_READS),trace=r.trace,**{k:False for k in FALSE_CLAIMS})
def validated_report(x):
 keys='profile contract_sha256 passes snapshot two_pass_equal atomic source_kind unsupported read_budget trace '+' '.join(FALSE_CLAIMS)
 if type(x) is dict and 'process' in x:keys+=' process'
 exact(x,keys);c=contract();require(x['profile']==c['profile'] and x['contract_sha256']==CONTRACT_SHA,'profile/contract');require(x['two_pass_equal'] is True and x['atomic'] is False,'two-pass flags')
 require(type(x['passes']) is list and len(x['passes'])==2,'two complete passes')
 for s in x['passes']:inspect(s,c)
 require(canonical(x['passes'][0])==canonical(x['passes'][1])==canonical(x['snapshot']),'complete typed pass equality')
 require(all(x[k] is False for k in FALSE_CLAIMS) and canonical(x['unsupported'])==canonical(c['unsupported']),'unsupported/authentication claims')
 b=x['read_budget'];exact(b,'bytes calls max_bytes max_calls');integer(b['bytes'],1,mil.support.MAX_TOTAL);integer(b['calls'],1,mil.support.MAX_READS);integer(b['max_bytes'],mil.support.MAX_TOTAL,mil.support.MAX_TOTAL);integer(b['max_calls'],mil.support.MAX_READS,mil.support.MAX_READS)
 require(type(x['trace']) is list and len(x['trace'])==b['calls'],'trace count');total=0
 for row in x['trace']:
  exact(row,'address size sha256');integer(row['address'],0x10000,0x7fffffffffff);integer(row['size'],1,65536);require(row['address']+row['size']<=0x800000000000 and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),'trace bytes');total+=row['size']
 require(total==b['bytes'],'trace byte budget')
 if 'process' not in x:require(x['source_kind']=='injected_reader_not_process_attested','source kind')
 else:
  require(x['source_kind']=='held_process_readonly','source kind');p=x['process'];exact(p,'pid creation before after executable disk_exe_sha256 loaded_full_image_hash_verified rights')
  integer(p['pid'],1,2**32-1);require(type(p['creation']) is str and re.fullmatch('[0-9a-f]{16}',p['creation']) and int(p['creation'],16)>0,'creation');require(canonical(p['before'])==canonical(p['after']),'held identities differ')
  for identity in (p['before'],p['after']):
   exact(identity,'pid creation_filetime exit_filetime module_base');require(integer(identity['pid'],1,2**32-1)==p['pid'] and type(identity['creation_filetime']) is str and identity['creation_filetime']==p['creation'],'held identity');integer(identity['exit_filetime'],0,0);require(ptr(identity['module_base'])==x['snapshot']['graph']['identity']['base'],'held module identity')
  require(type(p['executable']) is str and p['executable']==str((ROOT.parent/'eu4.exe').resolve()) and p['disk_exe_sha256']==EXE_SHA and p['loaded_full_image_hash_verified'] is False and p['rights']==['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'],'process envelope')
 return True
def compare_snapshots(before,after):
 """Same-day selected raw-bit correlation only; never an applied-effect claim."""
 inspect(before);inspect(after)
 require(before['graph']['scope_status']=='direct_subject_graph_observed','no direct subject graph')
 for key in ('graph','registrations','permission_map'):require(canonical(before[key])==canonical(after[key]),'comparison binding '+key)
 for key in set(before['raw_fields'])-{'subject_flags'}:require(canonical(before['raw_fields'][key])==canonical(after['raw_fields'][key]),'comparison gate '+key)
 selected={n:dict(before=before['states'][n]['current'],after=after['states'][n]['current']) for n in contract()['families']}
 other=(before['raw_fields']['subject_flags']^after['raw_fields']['subject_flags'])&(~0x52&0xffffffff)
 return dict(evidence_kind='same_day_selected_subject_flags',states=selected,other_flag_bits_changed=other,**{k:False for k in FALSE_CLAIMS})
def sample_process(*,pid,creation,executable):
 """Future explicit RO entry; author/tests never call OS process APIs."""
 integer(pid,1,2**32-1);require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)>0,'full creation')
 c=contract();dependencies(c);exe=Path(executable).resolve();require(exe==(ROOT.parent/'eu4.exe').resolve() and mil.sha(exe)==EXE_SHA,'exact disk EXE')
 sys.path.insert(0,str(ROOT));from work import probe_diplomacy_current as legacy
 require(Path(legacy.__file__).resolve()==(ROOT/'work/probe_diplomacy_current.py').resolve() and legacy.ROOT==ROOT,'legacy import provenance')
 _,signature=legacy.verified_executable(exe);require(signature==dict(timestamp=c['pe']['timestamp'],size=c['pe']['image_size']),'exact PE')
 reader=legacy.ProcessReader(pid,exe,signature)
 try:
  before=mil.support.held_identity(reader,pid,int(creation,16));result=capture(reader,reader.base);after=mil.support.held_identity(reader,pid,int(creation,16));require(canonical(before)==canonical(after),'held identity changed')
  legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature);require(mil.sha(exe)==EXE_SHA,'disk changed');require(reader.bytes_read<=mil.support.MAX_TOTAL,'PE included budget')
  result['source_kind']='held_process_readonly';result['process']=dict(pid=pid,creation=creation,before=before,after=after,executable=str(exe),disk_exe_sha256=EXE_SHA,loaded_full_image_hash_verified=False,rights=['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'])
  validated_report(result);return result
 finally:reader.close()
