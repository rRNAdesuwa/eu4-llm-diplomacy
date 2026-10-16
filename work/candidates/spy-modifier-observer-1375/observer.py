"""Bounded RO candidate. Import/capture never opens a process or calls engine code.

sample_process is a future explicitly invoked RO entry, with no CLI. All current
validation uses sparse mocks. No sample grants native construction/submission.
"""
import hashlib,json,re,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT_SHA='e385e400841d9e012a4be2ed0261ae2dab311c5bf396f42c588d74f5508575d4'
DEPENDENCIES_SHA='99cf1414b7aeaf8beaba7947c776f708281c76f4d009b0eeef50f445e2c6752e'
EXE_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
MAX_TOTAL=16*1024*1024;MAX_SINGLE=65536;MAX_READS=8192;MAX_MODIFIERS=256
HANDLES={'FRA':0x0100007a00415246,'ENG':0x0100002e00474e45,'POR':0x010000bd00524f50,'NAV':0x010000bc0056414e,'FOI':0x0100007900494f46}
FALSE_CLAIMS=('native_call_authorized','production_ready','runtime_verified','native_legality_verified','request_causality_verified','strict_single_player_verified','world_epoch_verified','object_lifetime_verified','whole_world_unchanged_verified','paused_verified')
class ReadError(ValueError):pass
def require(ok,message):
 if not ok:raise ReadError(message)
def integer(v,lo=0,hi=2**64-1):
 require(type(v) is int and lo<=v<=hi,'exact bounded integer');return v
def ptr(v,nullable=False):
 integer(v,0,0x7fffffffffff)
 require((nullable and v==0) or (v>=0x10000 and v%8==0),'aligned pointer');return v
def exact(x,keys):require(type(x) is dict and set(x)==set(keys.split()),'missing/extra keys')
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(262144),b''):h.update(block)
 return h.hexdigest()
def bounded(path,limit):
 with Path(path).open('rb') as f:raw=f.read(limit+1)
 require(len(raw)<=limit,'file bound');return raw
def contract():
 raw=bounded(HERE/'report.json',4*1024*1024)
 require(hashlib.sha256(raw).hexdigest()==REPORT_SHA,'static report pin');return json.loads(raw)
def verify_dependencies():
 raw=bounded(HERE/'input-pins.json',65536);require(hashlib.sha256(raw).hexdigest()==DEPENDENCIES_SHA,'dependency index pin')
 for name,expected in json.loads(raw).items():require(sha(ROOT/name)==expected,'dependency changed: '+name)
class Budget:
 def __init__(self,reader):self.reader=reader;self.bytes=0;self.trace=[]
 def read(self,address,size):
  integer(address,0x10000,0x7fffffffffff);integer(size,1,MAX_SINGLE)
  require(address+size<=0x800000000000 and self.bytes+size<=MAX_TOTAL and len(self.trace)<MAX_READS,'read budget')
  self.bytes+=size;raw=self.reader.read(address,size)
  require(type(raw) is bytes and len(raw)==size,'short/missing read')
  self.trace.append({'address':address,'size':size,'sha256':hashlib.sha256(raw).hexdigest()});return raw
 def q(self,p):return struct.unpack('<Q',self.read(p,8))[0]
 def i(self,p):return struct.unpack('<i',self.read(p,4))[0]
 def b(self,p):return self.read(p,1)[0]
def read_name(r,p):
 raw=r.read(p,32);length,capacity=struct.unpack_from('<QQ',raw,16)
 integer(length,1,128);integer(capacity,length,4096)
 if capacity<16:require(length<16,'inline name');storage=p;data=raw[:16]
 else:storage=ptr(struct.unpack_from('<Q',raw)[0]);data=r.read(storage,length+1)
 require(data[length]==0,'name terminator')
 try:text=data[:length].decode('ascii')
 except UnicodeError as e:raise ReadError('name encoding') from e
 require(re.fullmatch('[a-z][a-z0-9_]{0,127}',text) is not None,'definition identifier')
 return {'address':p,'storage':storage,'length':length,'capacity':capacity,'text':text}
def validate_name(x,address,name):
 exact(x,'address storage length capacity text');require(ptr(x['address'])==address,'name address');ptr(x['storage'])
 n=integer(x['length'],1,128);cap=integer(x['capacity'],n,4096)
 require(type(x['text']) is str and x['text']==name and len(name)==n,'exact definition name')
 if cap<16:require(n<16 and x['storage']==address,'inline name binding')
def in_ro(c,base,address,width):
 return any(s['rva']<=address-base and address-base+width<=s['rva']+s['virtual_size'] and s['flags']&0x40000000 and not s['flags']&0xa0000000 for s in c['sections'])
def code_pins(r,base,c):
 for row in c['instruction_pins']:
  data=bytes.fromhex(row['bytes']);require(r.read(base+int(row['rva'],16),len(data))==data,'loaded code pin')
def roots(r,base,target):
 db=ptr(r.q(base+0x233d8d0));game=ptr(r.q(base+0x233fe78));array=ptr(r.q(db+0x118));count=integer(r.i(db+0x124),1,4096)
 date=integer(r.i(game+0x1dd0),1,2**31-1);player=r.q(game+0x1e60);require(player==HANDLES['FRA'],'player must be FRA')
 # These flags are known reset/load exclusions, not a complete world epoch.
 require(r.b(game+0x7485)==0 and r.q(game+0x74c8)==0,'known reset/load active')
 countries={}
 for tag in ('FRA',target):
  h=HANDLES[tag];slot=(h>>32)&65535;require(slot<count,'country slot count')
  p=ptr(r.q(array+slot*8));require(r.q(p+0x20)==h,'complete country handle')
  countries[tag]={'address':p,'handle':h,'slot':slot,'overlord':r.q(p+0x18f0)}
 require(countries['FRA']['address']!=countries[target]['address'],'country alias')
 return {'base':base,'database':db,'game':game,'array':array,'count':count,'date':date,'player':player,'reset_flag':0,'load_source':0,'countries':countries}
def cost_result(x):
 """A static arithmetic projection, never the actual native legality result."""
 if x['cache_state']==1:return 'unknown_lazy_or_thread_fallback',None
 if x['transform_root']==0 or x['transform']!=0:return 'unknown_dynamic_transform',None
 a=x['aggregate']
 if a['dense']!=0:return 'unsupported_dense_storage',None
 values=[row[1] for row in a['entries'] if row[0]==0x261]
 modifier=values[0] if values else 0
 if not -1000<=modifier<=1000000:return 'unsupported_modifier_range',None
 value=x['base_milli']*(1000+modifier)//1000
 if not 0<=value<=21474831:return 'unsupported_cost_range',None
 return 'static_nonlazy_sparse_null_transform_candidate',value
def read_cost(r,base,actor,target,config,date):
 relations=ptr(r.q(actor['address']+0x1510));record=relations+target['slot']*0x48
 owner=r.q(record+8);counterpart=r.q(record+0x10)
 require(owner==actor['handle'] and counterpart==target['handle'],'bilateral relation direction')
 network=integer(struct.unpack('<h',r.read(record+0x18,2))[0],0,10000)
 basecost=integer(r.i(base+config['base_cost_rva']),0,21474831)
 duration=integer(r.i(base+config['duration_rva']),1,36500)
 days=duration*config['duration_to_days'];expiry=integer(date+days*24,1,2**31-1)
 state=r.i(actor['address']+0x28c8);globalp=ptr(r.q(base+0x2358080),True)
 transform=ptr(r.q(globalp+0xe4a0),True) if globalp else None
 aggregate=None
 if state!=1:
  a=actor['address']+0x28d0;dense=integer(r.b(a+0x10),0,1);data=ptr(r.q(a+0x58),True);count=integer(r.i(a+0x64),0,4096)
  entries=[]
  # Dense array length semantics are not proved by this caller: don't index it.
  if dense==0:
   require(count==0 or data!=0,'null sparse aggregate')
   raw=r.read(data,count*8) if count else b''
   entries=[list(struct.unpack_from('<ii',raw,i*8)) for i in range(count)]
   require(len({v[0] for v in entries})==count,'duplicate sparse id')
  aggregate={'address':a,'dense':dense,'data':data,'count':count,'entries':entries}
 x={'base_milli':basecost,'duration_setting':duration,'duration_days':days,'expected_expiry':expiry,'relations':relations,'record':record,'owner':owner,'counterpart':counterpart,'network_centipoints':network,'cache_state':state,'transform_root':globalp,'transform':transform,'aggregate':aggregate}
 x['status'],x['final_milli_candidate']=cost_result(x);return x
def snapshot(r,base,family,target,c):
 config=c['families'][family];identity=roots(r,base,target);actor=identity['countries']['FRA'];recipient=identity['countries'][target]
 require(recipient['overlord']>>56==0,'unsupported subject target resolver')
 registry=ptr(r.q(base+0x242bd08));sentinel=ptr(r.q(base+0x2458c68));slot=registry+config['registry_slot'];definition=ptr(r.q(slot));flag=r.b(slot+8)
 require(flag==1 and definition!=sentinel,'unresolved/default modifier definition')
 vt=ptr(r.q(definition));require(in_ro(c,base,vt,0x98),'definition vtable outside readonly module')
 method=r.q(vt+0x90);require(method==base+0x8f440,'unsupported definition virtual90; never called')
 name=read_name(r,definition+0x158);validate_name(name,definition+0x158,config['definition_key'])
 reg={'address':registry,'sentinel':sentinel,'slot':slot,'initialized_flag':flag,'definition':definition,'vtable':vt,'method90':method,'name':name}
 cap=ptr(r.q(actor['address']+0x2440),True);capvalue=integer(r.b(cap+config['capability_offset']),0,1) if cap else None
 capability={'address':cap,'offset':config['capability_offset'],'raw':capvalue}
 cost=read_cost(r,base,actor,recipient,config,identity['date'])
 head=ptr(r.q(recipient['address']+0x1f0),True);tail=ptr(r.q(recipient['address']+0x1f8),True);count=integer(r.i(recipient['address']+0x200),0,MAX_MODIFIERS)
 require((count==0 and head==tail==0) or (count>0 and head and tail),'list endpoint/count')
 nodes=[];seen=set();objects=set();node=head;previous=0
 for _ in range(count):
  ptr(node);require(node not in seen,'modifier cycle');seen.add(node)
  blob=r.read(node,0x19);obj,prev,nxt=struct.unpack_from('<QQQ',blob);flag=blob[0x18]
  require(prev==previous and flag==0,'modifier prev/unknown removed flag');ptr(nxt,True);ptr(obj)
  require(obj not in objects,'duplicate modifier object');objects.add(obj)
  vt=ptr(r.q(obj));fields=None;marker=None
  if vt==base+0x1ce8040:
   marker=r.i(obj+8);require(marker==0x165,'known modifier type marker')
   d=ptr(r.q(obj+0x30));assoc=ptr(r.q(obj+0x38),True);expiry=r.i(obj+0x44)
   fields={'definition':d,'associated':assoc,'expiry':expiry}
  nodes.append({'address':node,'object':obj,'previous':prev,'next':nxt,'flag':flag,'vtable':vt,'type_marker':marker,'fields':fields})
  previous=node;node=nxt
 require(node==0 and previous==tail,'list count/tail mismatch')
 result={'family':family,'target':target,'identity':identity,'registry':reg,'capability':capability,'cost':cost,'modifiers':{'head':head,'tail':tail,'count':count,'nodes':nodes}}
 require(canonical(roots(r,base,target))==canonical(identity),'world identity changed in pass')
 inspect(result,c);return result
def inspect(s,c=None):
 c=c or contract();exact(s,'family target identity registry capability cost modifiers')
 f=s['family'];target=s['target'];require(type(f) is str and f in c['families'],'family');require(type(target) is str and target in HANDLES and target!='FRA','target');p=c['families'][f]
 z=s['identity'];exact(z,'base database game array count date player reset_flag load_source countries')
 for key in ('base','database','game','array'):ptr(z[key])
 count=integer(z['count'],1,4096);date=integer(z['date'],1,2**31-1);require(integer(z['player'])==HANDLES['FRA'],'player')
 integer(z['reset_flag'],0,0);integer(z['load_source'],0,0);exact(z['countries'],'FRA '+target)
 for tag in ('FRA',target):
  a=z['countries'][tag];exact(a,'address handle slot overlord');ptr(a['address']);integer(a['overlord']);require(integer(a['handle'])==HANDLES[tag] and integer(a['slot'],0,count-1)==(HANDLES[tag]>>32)&65535,'country identity')
 actor=z['countries']['FRA'];t=z['countries'][target];require(actor['address']!=t['address'] and t['overlord']>>56==0,'alias/subject');base=z['base']
 d=s['registry'];exact(d,'address sentinel slot initialized_flag definition vtable method90 name')
 for k in ('address','sentinel','slot','definition','vtable','method90'):ptr(d[k])
 require(d['slot']==d['address']+p['registry_slot'] and integer(d['initialized_flag'],1,1)==1 and d['definition']!=d['sentinel'],'registry binding')
 require(in_ro(c,base,d['vtable'],0x98) and d['method90']==base+0x8f440,'definition method binding');validate_name(d['name'],d['definition']+0x158,p['definition_key'])
 a=s['capability'];exact(a,'address offset raw');ptr(a['address'],True);require(integer(a['offset'])==p['capability_offset'],'capability offset')
 if a['address']:integer(a['raw'],0,1)
 else:require(a['raw'] is None,'null capability unknown')
 x=s['cost'];exact(x,'base_milli duration_setting duration_days expected_expiry relations record owner counterpart network_centipoints cache_state transform_root transform aggregate status final_milli_candidate')
 integer(x['base_milli'],0,21474831);integer(x['duration_setting'],1,36500);integer(x['duration_days'],1,36500*30);integer(x['expected_expiry'],1,2**31-1)
 require(x['duration_days']==x['duration_setting']*p['duration_to_days'] and x['expected_expiry']==date+x['duration_days']*24,'expiry arithmetic')
 ptr(x['relations']);require(ptr(x['record'])==x['relations']+t['slot']*0x48,'relation slot')
 require(integer(x['owner'])==actor['handle'] and integer(x['counterpart'])==t['handle'],'relation direction');integer(x['network_centipoints'],0,10000);integer(x['cache_state'],-2**31,2**31-1);ptr(x['transform_root'],True)
 if not x['transform_root']:require(x['transform'] is None,'missing transform root')
 else:ptr(x['transform'],True)
 a=x['aggregate']
 if x['cache_state']==1:require(a is None,'lazy aggregate unsupported')
 else:
  exact(a,'address dense data count entries');require(ptr(a['address'])==actor['address']+0x28d0,'aggregate address');integer(a['dense'],0,1);ptr(a['data'],True);n=integer(a['count'],0,4096);require(type(a['entries']) is list,'entries')
  require(len(a['entries'])==(n if a['dense']==0 else 0),'entry count')
  if a['dense']==0:require(n==0 or a['data']!=0,'sparse data')
  ids=set()
  for row in a['entries']:
   require(type(row) is list and len(row)==2,'sparse row');integer(row[0],-2**31,2**31-1);integer(row[1],-2**31,2**31-1);require(row[0] not in ids,'duplicate id');ids.add(row[0])
 status,value=cost_result(x);require(type(x['status']) is str and x['status']==status,'cost status')
 if value is None:require(x['final_milli_candidate'] is None,'unknown cost')
 else:require(integer(x['final_milli_candidate'],0,21474831)==value,'cost arithmetic')
 m=s['modifiers'];exact(m,'head tail count nodes');ptr(m['head'],True);ptr(m['tail'],True);n=integer(m['count'],0,MAX_MODIFIERS);require(type(m['nodes']) is list and len(m['nodes'])==n,'node count');prev=0;node=m['head'];seen=set();objects=set()
 for v in m['nodes']:
  exact(v,'address object previous next flag vtable type_marker fields');require(ptr(v['address'])==node and node not in seen,'node link/cycle');seen.add(node);ptr(v['object']);require(v['object'] not in objects,'object alias');objects.add(v['object']);require(integer(v['previous'])==prev,'prev link');ptr(v['next'],True);integer(v['flag'],0,0);ptr(v['vtable'])
  if v['vtable']==base+0x1ce8040:
   integer(v['type_marker'],0x165,0x165)
   q=v['fields'];exact(q,'definition associated expiry');ptr(q['definition']);ptr(q['associated'],True);integer(q['expiry'],-2**31,2**31-1)
  else:require(v['fields'] is None and v['type_marker'] is None,'unknown vtable fields')
  prev=node;node=v['next']
 require(node==0 and prev==m['tail'],'list terminal')
 return True
def selected(s):
 d=s['registry']['definition'];date=s['identity']['date'];rows=[];unknown=False
 for n in s['modifiers']['nodes']:
  f=n['fields']
  if f is None:unknown=True;continue
  if f['definition']==d:
   if f['associated']!=0 or f['expiry']<=0:unknown=True
   rows.append({'object':n['object'],'node':n['address'],**f,'active_by_expiry_comparison':f['expiry']>=date})
 return {'matching':rows,'complete_selected_absence_supported':not unknown and not rows,'unknown_objects_or_selected_semantics':unknown}
def capture(reader,base,*,family='corrupt_officials',target='ENG',value=True):
 require(value is True,'positive only; false is not cancel');c=contract();require(type(family) is str and family in c['families'] and type(target) is str and target in HANDLES and target!='FRA','fixed family/target');ptr(base)
 r=Budget(reader);code_pins(r,base,c);first=snapshot(r,base,family,target,c);second=snapshot(r,base,family,target,c);require(canonical(first)==canonical(second),'two-pass selected fields differ');code_pins(r,base,c)
 return {'profile':'spy_modifier_selected_ro_1375_1','static_report_sha256':REPORT_SHA,'snapshot':first,'two_pass_equal':True,'selected':selected(first),'read_budget':{'bytes':r.bytes,'calls':len(r.trace),'max_bytes':MAX_TOTAL,'max_calls':MAX_READS},'trace':r.trace,'source_kind':'injected_readonly_reader_identity_not_attested',**{k:False for k in FALSE_CLAIMS}}
def compare_snapshots(before,after):
 """Typed imported snapshots: same-day correlation only, not authentication."""
 inspect(before);inspect(after)
 for key in ('family','target','identity','registry','capability'):
  require(canonical(before[key])==canonical(after[key]),'comparison binding: '+key)
 for key in set(before['cost'])-{'network_centipoints'}:require(canonical(before['cost'][key])==canonical(after['cost'][key]),'cost binding: '+key)
 b=selected(before);a=selected(after);require(not b['unknown_objects_or_selected_semantics'] and not a['unknown_objects_or_selected_semantics'],'unknown modifier semantics')
 oldobjects={n['object'] for n in before['modifiers']['nodes']};oldnodes={n['address'] for n in before['modifiers']['nodes']}
 new=[x for x in a['matching'] if x['object'] not in oldobjects and x['node'] not in oldnodes and x['associated']==0 and x['expiry']==after['cost']['expected_expiry']]
 cost=before['cost']['final_milli_candidate'];start=before['cost']['network_centipoints'];end=after['cost']['network_centipoints']
 debit=None if cost is None else max(0,min(10000,start-(cost*100+500)//1000))
 return {'evidence_kind':'same_day_selected_correlation','before_absent':b['complete_selected_absence_supported'],'new_exact_expiry_count':len(new),'network_delta_centipoints':end-start,'static_cost_delta_matches':None if debit is None else end==debit,'refresh_or_stacking_verified':False,**{k:False for k in FALSE_CLAIMS}}
def held_identity(reader,pid,creation):
 import ctypes as C
 from ctypes import wintypes as W
 k=reader.kernel;k.GetProcessId.argtypes=[W.HANDLE];k.GetProcessId.restype=W.DWORD
 k.GetProcessTimes.argtypes=[W.HANDLE]+[C.POINTER(W.FILETIME)]*4;k.GetProcessTimes.restype=W.BOOL
 require(k.GetProcessId(reader.handle)==pid,'held PID');ts=[W.FILETIME() for _ in range(4)]
 if not k.GetProcessTimes(reader.handle,*(C.byref(t) for t in ts)):raise C.WinError(C.get_last_error())
 values=[t.dwHighDateTime<<32|t.dwLowDateTime for t in ts];require(values[0]==creation and values[1]==0,'held creation/exit')
 return {'pid':pid,'creation_filetime':f'{creation:016x}','exit_filetime':0,'module_base':reader.base}
def sample_process(*,pid,creation,executable,family='corrupt_officials',target='ENG'):
 """Future explicit RO entry. No CLI; current validation replaces all OS reads."""
 integer(pid,1,2**32-1);require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) and int(creation,16)>0,'full creation')
 c=contract();verify_dependencies();require(type(family) is str and family in c['families'] and type(target) is str and target in HANDLES and target!='FRA','family/target')
 exe=Path(executable).resolve();require(exe==(ROOT.parent/'eu4.exe').resolve() and sha(exe)==EXE_SHA,'exact executable path/SHA')
 sys.path.insert(0,str(ROOT));from work import probe_diplomacy_current as legacy
 require(Path(legacy.__file__).resolve()==(ROOT/'work/probe_diplomacy_current.py').resolve() and legacy.ROOT==ROOT,'legacy import provenance')
 _,signature=legacy.verified_executable(exe);require(signature=={'timestamp':c['pe']['timestamp'],'size':c['pe']['image_size']},'PE identity')
 reader=legacy.ProcessReader(pid,exe,signature)
 try:
  before=held_identity(reader,pid,int(creation,16));result=capture(reader,reader.base,family=family,target=target)
  require(held_identity(reader,pid,int(creation,16))==before,'held identity changed')
  legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature);require(sha(exe)==EXE_SHA,'disk executable changed')
  require(reader.bytes_read<=MAX_TOTAL,'including PE guards byte bound')
  result['source_kind']='held_process_readonly';result['process']={'identity':before,'path':str(exe),'disk_exe_sha256':EXE_SHA,'loaded_full_image_hash_verified':False,'rights':['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ']};return result
 finally:reader.close()
