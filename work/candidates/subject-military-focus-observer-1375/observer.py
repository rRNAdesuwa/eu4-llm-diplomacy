"""Fixed FRA/NAV raw read-only candidate. No CLI, engine call or constructor.

Only sample_process explicitly opens a read-only handle; tests mock that entry.
Imported snapshots are typed evidence, not authenticated process observations.
"""
import hashlib, importlib.util, json, re, struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT_SHA='3bc89887cca5cc3c17fdf3dde2354368920481ffd1125e6650b5df9adbc85da9'
DEPENDENCIES_SHA='a4e45a4c2eeb0f65687d7b0635f0c918c4c8d002a17aaa8c84260c18810a70a0'
SUPPORT_PATH='work/candidates/spy-modifier-observer-1375/observer.py'
SUPPORT_SHA='d386524d543d96509fe4230e5fd02b01bc7f404f5419054ae2a84f66fdb13e48'
EXE_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(262144),b''):h.update(b)
 return h.hexdigest()

def bounded(path,limit):
 with Path(path).open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise ValueError('bounded file')
 return b

assert sha(ROOT/SUPPORT_PATH)==SUPPORT_SHA,'frozen RO primitives changed'
spec=importlib.util.spec_from_file_location('_subject_focus_ro_primitives',ROOT/SUPPORT_PATH)
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
assert Path(support.__file__).resolve()==(ROOT/SUPPORT_PATH).resolve() and support.ROOT==ROOT
ReadError=support.ReadError;require=support.require;integer=support.integer;ptr=support.ptr
exact=support.exact;canonical=support.canonical;Budget=support.Budget
FRA=0x0100007a00415246;NAV=0x010000bc0056414e
HANDLES={'FRA':FRA,'NAV':NAV};FOCI=('no_focus','aggressive','supportive','passive','defensive','siege')
MAX_SUBJECTS=256;MAX_INDEX=4096;MAX_DEFINITIONS=4096;MAX_BUCKET_CHAIN=256
FALSE_CLAIMS=('runtime_verified','native_call_authorized','production_ready','complete_native_authority_verified','enum_entitlement_verified','strict_single_player_verified','world_epoch_verified','object_lifetime_verified','paused_verified','request_causality_verified','effect_verified')

def contract():
 b=bounded(HERE/'report.json',4*1024*1024);require(hashlib.sha256(b).hexdigest()==REPORT_SHA,'report pin');return json.loads(b)

def dependencies():
 raw=bounded(HERE/'input-pins.json',65536)
 require(hashlib.sha256(raw).hexdigest()==DEPENDENCIES_SHA,'input index pin')
 row=json.loads(raw)
 for path,h in row.items():require(sha(ROOT/path)==h,'dependency changed: '+path)

def handle(value,count):
 integer(value);slot=(value>>32)&0xffff
 require(value>>56!=0 and (value>>24)&255==0 and slot<count,'full handle generation/slot')
 require(all(65<=(value>>(8*i))&255<=90 for i in range(3)),'three ASCII TAG bytes')
 return slot

def pins(r,base,c):
 for row in c['instruction_pins']:
  b=bytes.fromhex(row['bytes']);require(r.read(base+int(row['rva'],16),len(b))==b,'loaded code pin')
 for row in c['data_pins']:
  b=bytes.fromhex(row['bytes']);require(len(b)%8==0,'vtable pin width')
  for off in range(0,len(b),8):
   expected=struct.unpack_from('<Q',b,off)[0]-0x140000000+base
   require(r.q(base+int(row['rva'],16)+off)==expected,'relocated vtable pin')

def vector(r,begin,end,capacity,limit):
 ptr(begin,True);ptr(end,True);ptr(capacity,True)
 require((begin==end==capacity==0) or (begin!=0 and begin<=end<=capacity and (end-begin)%8==0 and (capacity-begin)%8==0),'vector boundaries')
 n=(end-begin)//8;require(n<=limit and (capacity-begin)//8<=limit,'vector limit')
 data=r.read(begin,n*8) if n else b''
 return {'begin':begin,'end':end,'capacity':capacity,'values':list(struct.unpack('<'+'Q'*n,data)) if n else []}

def subject_vector(r,identity):
 actor=identity['countries']['FRA']['address'];begin=r.q(actor+0x1a18);end=r.q(actor+0x1a20)
 # Capacity is not needed/proven for this country field: only native begin/end.
 ptr(begin,True);ptr(end,True);require((begin==end==0) or (begin and end>=begin and (end-begin)%8==0),'subject vector bounds')
 n=(end-begin)//8;require(n<=MAX_SUBJECTS,'subject count');raw=r.read(begin,n*8) if n else b''
 entries=[];seen=set();objects=set()
 for i in range(n):
  h=struct.unpack_from('<Q',raw,i*8)[0];slot=handle(h,identity['count']);require(h not in seen,'duplicate subject');seen.add(h)
  obj=ptr(r.q(identity['array']+slot*8));require(obj not in objects,'aliased subject');objects.add(obj)
  require(r.q(obj+0x20)==h,'subject full generation');overlord=r.q(obj+0x18f0);require(overlord==FRA,'vector member no longer belongs to FRA')
  entries.append({'handle':h,'slot':slot,'address':obj,'overlord':overlord})
 return {'begin':begin,'end':end,'entries':entries}

def dependency_index(r,identity,owner,other):
 a=identity['countries'][owner];b=identity['countries'][other]
 records=ptr(r.q(a['address']+0x1510));record=records+b['slot']*0x48
 root=ptr(r.q(record));owner_handle=r.q(record+8);counterpart=r.q(record+0x10)
 require(owner_handle==a['handle'] and counterpart==b['handle'],'relation record full handles/direction')
 array=ptr(r.q(root+0x128),True);n=integer(r.i(root+0x134),0,MAX_INDEX)
 require(n==0 or array!=0,'null dependency index');raw=r.read(array,n*16) if n else b''
 entries=[];slots=set()
 for i in range(n):
  slot,obj=struct.unpack_from('<I4xQ',raw,i*16);integer(slot,0,identity['count']-1);ptr(obj)
  require(slot not in slots,'duplicate dependency slot');slots.add(slot);entries.append({'slot':slot,'object':obj})
 return {'records':records,'record':record,'root':root,'owner':owner_handle,'counterpart':counterpart,'array':array,'count':n,'entries':entries}

def fnv1(text):
 h=0x811c9dc5
 for b in text.encode('ascii'):h=((h*0x1000193)^b)&0xffffffff
 return h

def definition(r,base,address):
 ptr(address);vt=r.q(address);require(vt==base+0x1ce7488,'unsupported definition vtable')
 marker=r.i(address+8);require(marker==0x165,'definition type marker')
 name=support.read_name(r,address+0x10);index=integer(r.i(address+0x30),0,MAX_DEFINITIONS-1)
 selfp=r.q(address+0x38);require(selfp==address,'definition self pointer')
 uses=integer(r.b(address+0x14f),0,1);can=integer(r.b(address+0x15a),0,1)
 return {'address':address,'vtable':vt,'type_marker':marker,'name':name,'index':index,'self':selfp,'uses_military_focus':uses,'can_set_mil_focus':can}

def registry(r,base,definition_row):
 address=ptr(r.q(base+0x233ffd8));sentinel=ptr(r.q(address+8));total=integer(r.q(address+0x10),1,MAX_DEFINITIONS)
 buckets=ptr(r.q(address+0x18));mask=integer(r.q(address+0x30),0,MAX_DEFINITIONS-1);bucket_count=integer(r.q(address+0x38),1,MAX_DEFINITIONS)
 require(mask==bucket_count-1 and bucket_count&(bucket_count-1)==0,'hash bucket mask/count')
 v=vector(r,r.q(address+0x40),r.q(address+0x48),r.q(address+0x50),MAX_DEFINITIONS)
 for obj in v['values']:ptr(obj)
 require(len(set(v['values']))==len(v['values'])==total,'registry count/unique definitions')
 d=definition_row;require(d['index']<total and v['values'][d['index']]==d['address'],'definition registry ordinal')
 cache=ptr(r.q(address+0x58),True)
 if d['name']['text']=='vassal':require(cache==d['address'],'vassal named cache')
 elif cache:require(cache in v['values'],'vassal cache outside definition vector')
 h=fnv1(d['name']['text']);bucket=buckets+(h&mask)*16
 first=ptr(r.q(bucket));last=ptr(r.q(bucket+8))
 require(first!=sentinel and last!=sentinel,'selected name not registered')
 rows=[];seen=set();names=set();node=last;later=None
 for _ in range(min(total,MAX_BUCKET_CHAIN)):
  ptr(node);require(node!=sentinel and node not in seen,'hash chain cycle/sentinel');seen.add(node)
  nxt=ptr(r.q(node));previous=ptr(r.q(node+8));key=support.read_name(r,node+0x10);value=ptr(r.q(node+0x30))
  require(later is None or nxt==later,'hash chain reciprocal next')
  require(key['text'] not in names and fnv1(key['text'])&mask==h&mask,'duplicate/wrong hash bucket key');names.add(key['text'])
  require(value in v['values'],'hash value outside registry vector')
  rows.append({'address':node,'next':nxt,'previous':previous,'key':key,'value':value})
  if node==first:break
  later=node;node=previous
 else:raise ReadError('hash chain enumeration limit')
 matches=[x for x in rows if x['key']['text']==d['name']['text']]
 require(len(matches)==1 and matches[0]['value']==d['address'],'name lookup/definition identity')
 return {'address':address,'sentinel':sentinel,'total_count':total,'buckets':buckets,'mask':mask,'bucket_count':bucket_count,'vector':v,'vassal_cache':cache,'lookup':{'hash':h,'bucket':bucket,'first':first,'last':last,'nodes':rows}}

def snapshot(r,base,c):
 identity=support.roots(r,base,'NAV');subjects=subject_vector(r,identity)
 left=dependency_index(r,identity,'FRA','NAV');right=dependency_index(r,identity,'NAV','FRA')
 a=[x['object'] for x in left['entries'] if x['slot']==identity['countries']['NAV']['slot']]
 b=[x['object'] for x in right['entries'] if x['slot']==identity['countries']['FRA']['slot']]
 require(a==b,'bidirectional dependency mismatch')
 present=[x for x in subjects['entries'] if x['handle']==NAV]
 is_subject=identity['countries']['NAV']['overlord']==FRA
 require(bool(a)==bool(present)==is_subject,'subject graph differs across vector/overlord/index')
 relation=defn=reg=None
 if a:
  obj=a[0];vt=r.q(obj);require(vt==base+0x1c81758,'unsupported dependency vtable')
  marker=r.i(obj+8);require(marker==0x165,'dependency type marker')
  owner=r.q(obj+0x10);subject=r.q(obj+0x18);started=r.i(obj+0x20);removed=r.b(obj+0x28)
  require(owner==FRA and subject==NAV and removed==0,'dependency role/full generation/removed')
  address=ptr(r.q(obj+0x40));relation={'address':obj,'vtable':vt,'type_marker':marker,'overlord_handle':owner,'subject_handle':subject,'started_date':started,'removed':removed,'definition':address}
  defn=definition(r,base,address);reg=registry(r,base,defn)
 target=identity['countries']['NAV']['address'];focus=integer(r.i(target+0x2864),0,5)
 gate={'country_field_1344':r.i(target+0x1344),'country_marker_26':r.b(target+0x26)}
 require(gate['country_marker_26']==(NAV>>48)&255,'country marker/full-handle consistency')
 result={'identity':identity,'subjects':subjects,'left':left,'right':right,'relation':relation,'definition':defn,'registry':reg,'focus':focus,'gate_inputs':gate,'scope_status':'direct_subject_graph_observed' if a else 'outside_fixed_direct_subject_scope'}
 require(canonical(support.roots(r,base,'NAV'))==canonical(identity),'roots changed during pass')
 inspect(result);return result

def validate_name(x,address):
 exact(x,'address storage length capacity text');require(type(x['text']) is str and re.fullmatch('[a-z][a-z0-9_]{0,127}',x['text']) is not None,'name identifier')
 support.validate_name(x,address,x['text'])

def validate_vector(v,limit):
 exact(v,'begin end capacity values')
 for k in ('begin','end','capacity'):ptr(v[k],True)
 require(type(v['values']) is list and len(v['values'])<=limit,'vector values')
 begin,end,cap=(v[k] for k in ('begin','end','capacity'))
 require((begin==end==cap==0) or (begin and begin<=end<=cap and (end-begin)%8==0 and (cap-begin)%8==0),'vector bounds')
 require(end-begin==len(v['values'])*8 and cap-begin<=limit*8,'vector lengths')
 for obj in v['values']:ptr(obj)

def inspect(s):
 exact(s,'identity subjects left right relation definition registry focus gate_inputs scope_status')
 z=s['identity'];exact(z,'base database game array count date player reset_flag load_source countries')
 for k in ('base','database','game','array'):ptr(z[k])
 count=integer(z['count'],1,4096);integer(z['date'],1,2**31-1);require(integer(z['player'])==FRA,'player FRA');integer(z['reset_flag'],0,0);integer(z['load_source'],0,0)
 exact(z['countries'],'FRA NAV')
 for tag,h in HANDLES.items():
  row=z['countries'][tag];exact(row,'address handle slot overlord');ptr(row['address']);require(integer(row['handle'])==h and integer(row['slot'],0,count-1)==handle(h,count),'fixed country');integer(row['overlord'])
 require(z['countries']['FRA']['address']!=z['countries']['NAV']['address'],'country alias')
 v=s['subjects'];exact(v,'begin end entries');ptr(v['begin'],True);ptr(v['end'],True);require(type(v['entries']) is list and len(v['entries'])<=MAX_SUBJECTS,'subject entries')
 require((v['begin']==v['end']==0) or (v['begin'] and v['end']>=v['begin']),'subject endpoints');require(v['end']-v['begin']==len(v['entries'])*8,'subject length')
 seen=set();objects=set()
 for row in v['entries']:
  exact(row,'handle slot address overlord');slot=handle(row['handle'],count);require(integer(row['slot'])==slot,'subject slot');ptr(row['address']);require(integer(row['overlord'])==FRA,'subject overlord')
  require(row['handle'] not in seen and row['address'] not in objects,'subject duplicate');seen.add(row['handle']);objects.add(row['address'])
  if row['handle']==NAV:require(row['address']==z['countries']['NAV']['address'],'NAV vector object')
 selected=[]
 for key,owner,other in [('left','FRA','NAV'),('right','NAV','FRA')]:
  x=s[key];exact(x,'records record root owner counterpart array count entries')
  for k in ('records','record','root'):ptr(x[k])
  ptr(x['array'],True);require(integer(x['owner'])==HANDLES[owner] and integer(x['counterpart'])==HANDLES[other],'index direction')
  require(x['record']==x['records']+z['countries'][other]['slot']*0x48,'record slot')
  n=integer(x['count'],0,MAX_INDEX);require(type(x['entries']) is list and len(x['entries'])==n and (not n or x['array']),'index count/null')
  slots=set()
  for row in x['entries']:
   exact(row,'slot object');integer(row['slot'],0,count-1);ptr(row['object']);require(row['slot'] not in slots,'duplicate index');slots.add(row['slot'])
  selected.append([row['object'] for row in x['entries'] if row['slot']==z['countries'][other]['slot']])
 require(selected[0]==selected[1],'bidirectional index');direct=bool(selected[0])
 require(direct==(NAV in seen)==(z['countries']['NAV']['overlord']==FRA),'direct graph binding')
 require(type(s['scope_status']) is str and s['scope_status']==('direct_subject_graph_observed' if direct else 'outside_fixed_direct_subject_scope'),'scope status')
 if not direct:require(s['relation'] is None and s['definition'] is None and s['registry'] is None,'unmatched graph cannot claim definition')
 else:
  x=s['relation'];exact(x,'address vtable type_marker overlord_handle subject_handle started_date removed definition')
  require(ptr(x['address'])==selected[0][0] and ptr(x['vtable'])==z['base']+0x1c81758,'relation object/type');integer(x['type_marker'],0x165,0x165);require(integer(x['overlord_handle'])==FRA and integer(x['subject_handle'])==NAV,'relation roles');integer(x['started_date'],-2**31,2**31-1);integer(x['removed'],0,0);ptr(x['definition'])
  d=s['definition'];exact(d,'address vtable type_marker name index self uses_military_focus can_set_mil_focus')
  require(ptr(d['address'])==x['definition'] and ptr(d['vtable'])==z['base']+0x1ce7488,'definition object/type');integer(d['type_marker'],0x165,0x165);validate_name(d['name'],d['address']+0x10);integer(d['index'],0,MAX_DEFINITIONS-1);require(ptr(d['self'])==d['address'],'self');integer(d['uses_military_focus'],0,1);integer(d['can_set_mil_focus'],0,1)
  g=s['registry'];exact(g,'address sentinel total_count buckets mask bucket_count vector vassal_cache lookup')
  for k in ('address','sentinel','buckets'):ptr(g[k])
  n=integer(g['total_count'],1,MAX_DEFINITIONS);mask=integer(g['mask'],0,MAX_DEFINITIONS-1);buckets=integer(g['bucket_count'],1,MAX_DEFINITIONS);require(mask==buckets-1 and buckets&(buckets-1)==0,'bucket limits');validate_vector(g['vector'],MAX_DEFINITIONS);values=g['vector']['values']
  require(len(set(values))==len(values)==n and d['index']<n and values[d['index']]==d['address'],'vector/index identity');ptr(g['vassal_cache'],True)
  if d['name']['text']=='vassal':require(g['vassal_cache']==d['address'],'vassal cache')
  elif g['vassal_cache']:require(g['vassal_cache'] in values,'cached vector identity')
  q=g['lookup'];exact(q,'hash bucket first last nodes');require(integer(q['hash'],0,0xffffffff)==fnv1(d['name']['text']),'name hash');require(ptr(q['bucket'])==g['buckets']+(q['hash']&mask)*16,'bucket address');ptr(q['first']);ptr(q['last']);require(q['first']!=g['sentinel'] and q['last']!=g['sentinel'],'bucket empty')
  require(type(q['nodes']) is list and 0<len(q['nodes'])<=min(n,MAX_BUCKET_CHAIN),'chain bound');node=q['last'];later=None;seen_nodes=set();names=set();matches=[]
  for row in q['nodes']:
   exact(row,'address next previous key value');require(ptr(row['address'])==node and node!=g['sentinel'] and node not in seen_nodes,'hash node');seen_nodes.add(node);ptr(row['next']);ptr(row['previous']);ptr(row['value']);validate_name(row['key'],node+0x10)
   require(later is None or row['next']==later,'next backlink');require(row['key']['text'] not in names and fnv1(row['key']['text'])&mask==q['hash']&mask,'hash key');names.add(row['key']['text']);require(row['value'] in values,'hash member')
   if row['key']['text']==d['name']['text']:matches.append(row['value'])
   later=node;node=row['previous']
  require(later==q['first'] and matches==[d['address']],'hash name resolution')
 integer(s['focus'],0,5);exact(s['gate_inputs'],'country_field_1344 country_marker_26');integer(s['gate_inputs']['country_field_1344'],-2**31,2**31-1);require(integer(s['gate_inputs']['country_marker_26'],0,255)==(NAV>>48)&255,'marker')
 return True

def capture(reader,base):
 ptr(base);c=contract();r=Budget(reader);pins(r,base,c)
 first=snapshot(r,base,c);second=snapshot(r,base,c);require(canonical(first)==canonical(second),'two-pass selected state changed');pins(r,base,c)
 return {'profile':'subject_military_focus_ro_1375_1','static_report_sha256':REPORT_SHA,'snapshot':first,'two_pass_equal':True,'entitlement':'unsupported_tls_and_lazy_query','source_kind':'injected_reader_not_process_attested','read_budget':{'bytes':r.bytes,'calls':len(r.trace),'max_bytes':support.MAX_TOTAL,'max_calls':support.MAX_READS},'trace':r.trace,**{k:False for k in FALSE_CLAIMS}}

def compare_snapshots(before,after):
 inspect(before);inspect(after)
 for k in set(before)-{'focus'}:require(canonical(before[k])==canonical(after[k]),'comparison binding: '+k)
 require(before['scope_status']=='direct_subject_graph_observed','no direct subject graph')
 return {'evidence_kind':'same_day_selected_focus_difference','before_focus':before['focus'],'after_focus':after['focus'],'changed':before['focus']!=after['focus'],**{k:False for k in FALSE_CLAIMS}}

def sample_process(*,pid,creation,executable):
 """Future explicit read-only entry; never invoked against a process in tests."""
 integer(pid,1,2**32-1);require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) is not None and int(creation,16)>0,'full creation')
 dependencies();c=contract();exe=Path(executable).resolve();require(exe==(ROOT.parent/'eu4.exe').resolve() and sha(exe)==EXE_SHA,'exact disk EXE')
 sys.path.insert(0,str(ROOT));from work import probe_diplomacy_current as legacy
 require(Path(legacy.__file__).resolve()==(ROOT/'work/probe_diplomacy_current.py').resolve() and legacy.ROOT==ROOT,'legacy import provenance')
 _,signature=legacy.verified_executable(exe);require(signature=={'timestamp':c['pe']['timestamp'],'size':c['pe']['image_size']},'exact PE')
 reader=legacy.ProcessReader(pid,exe,signature)
 try:
  first=support.held_identity(reader,pid,int(creation,16));result=capture(reader,reader.base)
  require(support.held_identity(reader,pid,int(creation,16))==first,'held identity changed')
  legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature);require(sha(exe)==EXE_SHA,'disk changed');require(reader.bytes_read<=support.MAX_TOTAL,'including PE guards budget')
  result['source_kind']='held_process_readonly';result['process']={'identity':first,'path':str(exe),'disk_exe_sha256':EXE_SHA,'loaded_full_image_hash_verified':False,'rights':['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ']};return result
 finally:reader.close()
