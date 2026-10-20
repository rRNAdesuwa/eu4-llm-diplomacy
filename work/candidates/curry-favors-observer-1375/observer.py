"""Fixed FRA/POR curry graph; injectable read-only model and future RO wrapper.
No CLI, native getter, process write, engine call or invocation on import.
"""
import hashlib,importlib.util,json,re,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SUPPORT='work/candidates/spy-modifier-observer-1375/observer.py'
SUPPORT_SHA='d386524d543d96509fe4230e5fd02b01bc7f404f5419054ae2a84f66fdb13e48'
REPORT_SHA='95a837d212f8f415c2d9d0714820ae90e2c98ae485710573b19c15d1c58df6b6'
def bounded(p,n):
 with Path(p).open('rb') as f:b=f.read(n+1)
 if len(b)>n:raise ValueError('file budget')
 return b
assert hashlib.sha256(bounded(ROOT/SUPPORT,65536)).hexdigest()==SUPPORT_SHA
spec=importlib.util.spec_from_file_location('_curry_ro_support',ROOT/SUPPORT)
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
assert Path(support.__file__).resolve()==(ROOT/SUPPORT).resolve() and support.ROOT==ROOT
require=support.require;ReadError=support.ReadError;integer=support.integer;ptr=support.ptr;exact=support.exact;canonical=support.canonical;Budget=support.Budget
FRA=support.HANDLES['FRA'];POR=support.HANDLES['POR'];TOKEN=0x3acc;EXE_SHA=support.EXE_SHA
MAX_INDEX=4096;MAX_ENVOYS=4096
FALSE_CLAIMS=support.FALSE_CLAIMS+('effect_verified','favors_amount_verified','cancel_recall_verified','persistence_verified','visibility_verified')

def contract():
 b=bounded(HERE/'report.json',4*1024*1024);require(hashlib.sha256(b).hexdigest()==REPORT_SHA,'report SHA');return json.loads(b)
def dependencies(c):
 for name,d in c['sources'].items():require(support.sha(ROOT/name)==d,'source SHA '+name)
def pins(r,base,c):
 for x in c['instruction_pins']:
  b=bytes.fromhex(x['bytes']);require(r.read(base+int(x['rva'],16),len(b))==b,'loaded code pin')
 for x in c['vtable_pins']:
  expected=struct.unpack('<Q',bytes.fromhex(x['bytes']))[0]-0x140000000+base
  require(r.q(base+int(x['rva'],16))==expected,'relocated vtable pin')

def outgoing(r,z):
 actor=z['countries']['FRA'];target=z['countries']['POR'];records=ptr(r.q(actor['address']+0x1510));record=records+target['slot']*0x48
 root=ptr(r.q(record));owner=r.q(record+8);other=r.q(record+0x10)
 require(owner==FRA and other==POR,'record full direction')
 array=ptr(r.q(root+0x158),True);cap=integer(r.i(root+0x160),0,MAX_INDEX);n=integer(r.i(root+0x164),0,cap)
 require((cap==0 and array==0) or (cap>0 and array!=0),'index allocation/capacity')
 raw=r.read(array,n*16) if n else b'';entries=[]
 for i in range(n):
  slot,obj=struct.unpack_from('<I4xQ',raw,i*16);integer(slot,0,z['count']-1);ptr(obj);entries.append(dict(slot=slot,object=obj))
 require(len({x['slot'] for x in entries})==n and len({x['object'] for x in entries})==n,'duplicate index slot/object')
 return dict(records=records,record=record,root=root,owner=owner,counterpart=other,array=array,capacity=cap,count=n,entries=entries)

def relation(r,address,base):
 vt=ptr(r.q(address));row=dict(address=address,vtable=vt,marker=None,removed=None,fields=None)
 if vt!=base+0x1c7b178:return row
 row['marker']=r.i(address+8);require(row['marker']==0x165,'relation marker');row['removed']=integer(r.b(address+0x28),0,1)
 if row['removed']:return row
 row['fields']=dict(actor=r.q(address+0x10),target=r.q(address+0x18),started=r.i(address+0x20),mission=ptr(r.q(address+0x30),True))
 return row

def mission(r,address,base):
 vt=ptr(r.q(address));row=dict(address=address,vtable=vt,marker=None,fields=None)
 if vt!=base+0x1c4b2b8:return row
 row['marker']=r.i(address+8);require(row['marker']==0x182,'mission marker is182, not165')
 row['fields']=dict(entry=ptr(r.q(address+0x48)),envoy=r.i(address+0x50),actor=r.q(address+0x80),target=r.q(address+0x88),token=r.i(address+0xa8))
 return row

def envoys(r,z):
 base=z['base'];actor=z['countries']['FRA']['address'];holder=ptr(r.q(actor+0x1480));hend=ptr(r.q(actor+0x1488));hcap=ptr(r.q(actor+0x1490))
 require(holder<=hend<=hcap and (hend-holder)%8==0 and (hcap-holder)%8==0 and 4<=(hend-holder)//8<=(hcap-holder)//8<=16,'country manager vector bounds')
 manager=ptr(r.q(holder+0x18));vt=ptr(r.q(manager))
 row=dict(holder=holder,holder_end=hend,holder_capacity=hcap,manager=manager,vtable=vt,marker=None,fields=None)
 if vt!=base+0x1cac380:return row
 row['marker']=r.i(manager+8);require(row['marker']==0x165,'manager marker')
 token=r.i(manager+0x10);kind=r.b(manager+0x14);owner=r.q(manager+0x16)
 require(token==0x2746 and kind==3 and owner==FRA,'diplomat manager token/kind/fullowner')
 begin=ptr(r.q(manager+0x20),True);end=ptr(r.q(manager+0x28),True);cap=ptr(r.q(manager+0x30),True)
 require((begin==end==cap==0) or (begin and begin<=end<=cap and (end-begin)%8==0 and (cap-begin)%8==0),'envoy vector bounds')
 n=(end-begin)//8;require(n<=MAX_ENVOYS and (cap-begin)//8<=MAX_ENVOYS,'envoy vector cap')
 data=r.read(begin,n*8) if n else b'';entries=[]
 for i in range(n):
  obj=ptr(struct.unpack_from('<Q',data,i*8)[0]);vt=ptr(r.q(obj));entry=dict(address=obj,vtable=vt,marker=None,kind=None,fields=None)
  if vt==base+0x1cac2f0:
   entry['marker']=r.i(obj+8);require(entry['marker']==0x165,'envoy entry marker')
   entry['kind']=r.b(obj+0x40)
   if entry['kind']==3:
    mp=ptr(r.q(obj+0x10),True)
    entry['fields']=dict(status=r.b(obj+0x18),envoy=r.i(obj+0x44),mission=mp,mission_object=mission(r,mp,base) if mp else None)
  entries.append(entry)
 row['fields']=dict(token=token,kind=kind,owner=owner,begin=begin,end=end,capacity=cap,entries=entries)
 return row

def snapshot(r,base):
 z=support.roots(r,base,'POR');index=outgoing(r,z);selected=[x['object'] for x in index['entries'] if x['slot']==z['countries']['POR']['slot']]
 rel=relation(r,selected[0],base) if selected else None
 s=dict(identity=z,index=index,relation=rel,envoys=envoys(r,z))
 require(canonical(support.roots(r,base,'POR'))==canonical(z),'world/full handles/date changed inside pass')
 inspect(s);return s

def identity(z):
 exact(z,'base database game array count date player reset_flag load_source countries')
 for key in ('base','database','game','array'):ptr(z[key])
 count=integer(z['count'],1,4096);integer(z['date'],1,2**31-1);require(integer(z['player'])==FRA,'player')
 integer(z['reset_flag'],0,0);integer(z['load_source'],0,0);exact(z['countries'],'FRA POR')
 for tag,h in [('FRA',FRA),('POR',POR)]:
  x=z['countries'][tag];exact(x,'address handle slot overlord');ptr(x['address']);integer(x['overlord'])
  require(integer(x['handle'])==h and integer(x['slot'],0,count-1)==(h>>32)&65535,'full country generation/slot')
 require(z['countries']['FRA']['address']!=z['countries']['POR']['address'],'country alias')

def inspect(s):
 exact(s,'identity index relation envoys');z=s['identity'];identity(z);base=z['base']
 x=s['index'];exact(x,'records record root owner counterpart array capacity count entries')
 for key in ('records','record','root'):ptr(x[key])
 ptr(x['array'],True);cap=integer(x['capacity'],0,MAX_INDEX);n=integer(x['count'],0,cap)
 require((cap==0 and x['array']==0) or (cap>0 and x['array']!=0),'index allocation')
 require(integer(x['owner'])==FRA and integer(x['counterpart'])==POR and x['record']==x['records']+z['countries']['POR']['slot']*0x48,'index direction/record')
 require(type(x['entries']) is list and len(x['entries'])==n,'index count');slots=set();objects=set();selected=[]
 for e in x['entries']:
  exact(e,'slot object');integer(e['slot'],0,z['count']-1);ptr(e['object']);require(e['slot'] not in slots and e['object'] not in objects,'index uniqueness');slots.add(e['slot']);objects.add(e['object'])
  if e['slot']==z['countries']['POR']['slot']:selected.append(e['object'])
 rel=s['relation']
 if not selected:require(rel is None,'unindexed relation')
 else:
  exact(rel,'address vtable marker removed fields');require(ptr(rel['address'])==selected[0],'relation pointer');ptr(rel['vtable'])
  if rel['vtable']!=base+0x1c7b178:require(rel['marker'] is None and rel['removed'] is None and rel['fields'] is None,'unknown relation derived fields')
  else:
   integer(rel['marker'],0x165,0x165);integer(rel['removed'],0,1)
   if rel['removed']:require(rel['fields'] is None,'removed relation must short circuit')
   else:
    f=rel['fields'];exact(f,'actor target started mission');require(integer(f['actor'])==FRA and integer(f['target'])==POR,'relation full direction')
    integer(f['started'],1,z['date']);ptr(f['mission'],True)
 e=s['envoys'];exact(e,'holder holder_end holder_capacity manager vtable marker fields')
 for key in ('holder','holder_end','holder_capacity','manager','vtable'):ptr(e[key])
 h,end,cap=(e[k] for k in ('holder','holder_end','holder_capacity'))
 require(h<=end<=cap and (end-h)%8==0 and (cap-h)%8==0 and 4<=(end-h)//8<=(cap-h)//8<=16,'country manager vector bounds')
 if e['vtable']!=base+0x1cac380:require(e['marker'] is None and e['fields'] is None,'unknown manager derived');return True
 integer(e['marker'],0x165,0x165);v=e['fields'];exact(v,'token kind owner begin end capacity entries')
 integer(v['token'],0x2746,0x2746);integer(v['kind'],3,3);require(integer(v['owner'])==FRA,'manager full owner')
 for key in ('begin','end','capacity'):ptr(v[key],True)
 begin,end,cap=(v[k] for k in ('begin','end','capacity'))
 require((begin==end==cap==0) or (begin and begin<=end<=cap and (end-begin)%8==0 and (cap-begin)%8==0),'vector bounds')
 require(type(v['entries']) is list and len(v['entries'])==(end-begin)//8<=MAX_ENVOYS and (cap-begin)//8<=MAX_ENVOYS,'vector count')
 pointers=set();ids=set();missions=set()
 for row in v['entries']:
  exact(row,'address vtable marker kind fields');a=ptr(row['address']);ptr(row['vtable']);require(a not in pointers,'duplicate entry');pointers.add(a)
  if row['vtable']!=base+0x1cac2f0:
   require(row['marker'] is None and row['kind'] is None and row['fields'] is None,'unknown entry derived');continue
  integer(row['marker'],0x165,0x165);integer(row['kind'],0,255)
  if row['kind']!=3:require(row['fields'] is None,'non-diplomat derived');continue
  f=row['fields'];exact(f,'status envoy mission mission_object');integer(f['status'],0,255);eid=integer(f['envoy'],0,2**31-1)
  require(eid not in ids,'duplicate envoy ID');ids.add(eid);ptr(f['mission'],True)
  m=f['mission_object']
  if not f['mission']:require(m is None,'null mission fields');continue
  require(f['mission'] not in missions,'shared mission');missions.add(f['mission']);exact(m,'address vtable marker fields')
  require(ptr(m['address'])==f['mission'],'entry mission pointer');ptr(m['vtable'])
  if m['vtable']!=base+0x1c4b2b8:require(m['marker'] is None and m['fields'] is None,'unknown mission derived');continue
  integer(m['marker'],0x182,0x182);q=m['fields'];exact(q,'entry envoy actor target token')
  require(ptr(q['entry'])==a and integer(q['envoy'],0,2**31-1)==eid,'mission entry backreference/ID')
  require(integer(q['actor'])==FRA,'mission actor');h=integer(q['target']);slot=(h>>32)&65535
  require(h>>56!=0 and (h>>24)&255==0 and slot<z['count'] and all(65<=((h>>(8*i))&255)<=90 for i in range(3)),'mission target full TAG/slot')
  if slot==z['countries']['POR']['slot']:require(h==POR,'POR mission wrong generation')
  integer(q['token'],0,65535)
 return True

def selected(s):
 inspect(s);rel=s['relation'];v=s['envoys']['fields'];unknown=v is None;matching=[]
 if v:
  for e in v['entries']:
   f=e['fields']
   if f is None:unknown=True;continue
   if f['status'] not in (0,1,2):unknown=True
   m=f['mission_object']
   if m is not None:
    if m['fields'] is None:unknown=True
    elif m['fields']['token']==TOKEN and m['fields']['target']==POR:matching.append(e)
   elif f['status']!=0:unknown=True
 if rel and (rel['fields'] is None or not rel['fields']['mission']):unknown=True
 active=False
 if rel and rel['fields']:
  active=len(matching)==1 and matching[0]['fields']['status']==2 and matching[0]['fields']['mission']==rel['fields']['mission']
  if not active:unknown=True
 status='unknown_selected_graph' if unknown else 'active_relation_mission_graph' if active else 'index_absent_mission_present' if matching else 'selected_index_and_mission_absent'
 return dict(status=status,relation_index_present=rel is not None,active_graph_observed=active and not unknown,
  matching_missions=None if unknown else len(matching),complete_selected_absence=not unknown and rel is None and not matching)

def capture(reader,base):
 ptr(base);c=contract();r=Budget(reader);pins(r,base,c);passes=[snapshot(r,base),snapshot(r,base)]
 require(canonical(passes[0])==canonical(passes[1]),'two full passes changed');pins(r,base,c)
 return dict(profile='curry_favors_fra_por_raw_ro_1375_1',static_report_sha256=REPORT_SHA,passes=passes,state=selected(passes[0]),two_pass_equal=True,atomic=False,
  source_kind='injected_reader_not_process_attested',read_budget=dict(bytes=r.bytes,calls=len(r.trace),max_bytes=support.MAX_TOTAL,max_calls=support.MAX_READS),trace=r.trace,
  **{k:False for k in FALSE_CLAIMS})

def inspect_capture(report):
 require(type(report) is dict,'capture object')
 basekeys='profile static_report_sha256 passes state two_pass_equal atomic source_kind read_budget trace '+' '.join(FALSE_CLAIMS)
 held=report.get('source_kind')=='held_process_readonly';exact(report,basekeys+(' process' if held else ''))
 require(type(report['profile']) is str and report['profile']=='curry_favors_fra_por_raw_ro_1375_1','profile')
 require(report['static_report_sha256']==REPORT_SHA and type(report['static_report_sha256']) is str,'contract binding')
 require(report['two_pass_equal'] is True and report['atomic'] is False,'two-pass flags')
 require(type(report['passes']) is list and len(report['passes'])==2,'two complete passes')
 for s in report['passes']:inspect(s)
 require(canonical(report['passes'][0])==canonical(report['passes'][1]),'typed pass equality')
 require(canonical(report['state'])==canonical(selected(report['passes'][0])),'state recomputation')
 for k in FALSE_CLAIMS:require(report[k] is False,'unsupported authority flag')
 b=report['read_budget'];exact(b,'bytes calls max_bytes max_calls');integer(b['bytes'],0,support.MAX_TOTAL);integer(b['calls'],0,support.MAX_READS)
 integer(b['max_bytes'],support.MAX_TOTAL,support.MAX_TOTAL);integer(b['max_calls'],support.MAX_READS,support.MAX_READS)
 require(type(report['trace']) is list and len(report['trace'])==b['calls'],'trace length');total=0
 for row in report['trace']:
  exact(row,'address size sha256');integer(row['address'],0x10000,0x7fffffffffff);n=integer(row['size'],1,support.MAX_SINGLE);require(row['address']+n<=0x800000000000,'trace address wrap');total+=n
  require(type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']) is not None,'trace digest')
 require(total==b['bytes'],'trace budget')
 if held:
  p=report['process'];exact(p,'identity path disk_exe_sha256 loaded_full_image_hash_verified rights');i=p['identity'];exact(i,'pid creation_filetime exit_filetime module_base')
  integer(i['pid'],1,2**32-1);integer(i['exit_filetime'],0,0);require(type(i['creation_filetime']) is str and re.fullmatch('[0-9a-f]{16}',i['creation_filetime']) is not None and int(i['creation_filetime'],16)>0,'creation')
  require(ptr(i['module_base'])==report['passes'][0]['identity']['base'],'module base binding')
  require(type(p['path']) is str and Path(p['path']).resolve()==(ROOT.parent/'eu4.exe').resolve(),'exact path');require(p['disk_exe_sha256']==EXE_SHA and p['loaded_full_image_hash_verified'] is False,'disk SHA scope')
  require(canonical(p['rights'])==canonical(['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ']),'RO rights')
 else:require(report['source_kind']=='injected_reader_not_process_attested','source kind')
 return True

def compare_snapshots(before,after):
 inspect(before);inspect(after)
 for k in set(before['identity'])-{'date'}:require(canonical(before['identity'][k])==canonical(after['identity'][k]),'same selected world/handles '+k)
 require(after['identity']['date']>=before['identity']['date'],'date rollback');a=selected(before);b=selected(after)
 return dict(evidence_kind='selected_census_difference_not_request_effect',before_date=before['identity']['date'],after_date=after['identity']['date'],before=a,after=b,
  selected_active_graph_appeared=a['complete_selected_absence'] and b['active_graph_observed'],selected_index_disappeared=a['active_graph_observed'] and not b['relation_index_present'] and b['status']!='unknown_selected_graph',
  **{k:False for k in FALSE_CLAIMS})

def compare_captures(before,after):
 """Revalidate full held-identity envelopes and both passes; no authentication claim."""
 inspect_capture(before);inspect_capture(after)
 require(before['source_kind']==after['source_kind']=='held_process_readonly','two held-identity reports required')
 require(canonical(before['process'])==canonical(after['process']),'same held PID/full creation/EXE/module')
 return compare_snapshots(before['passes'][0],after['passes'][0])

def sample_process(*,pid,creation,executable):
 """Future explicitly called RO wrapper. Never invoked against a real process here."""
 integer(pid,1,2**32-1);require(type(creation) is str and re.fullmatch('[0-9a-f]{16}',creation) is not None and int(creation,16)>0,'canonical full creation')
 c=contract();dependencies(c);exe=Path(executable).resolve();require(exe==(ROOT.parent/'eu4.exe').resolve() and support.sha(exe)==EXE_SHA,'exact EXE path/hash')
 sys.path.insert(0,str(ROOT));from work import probe_diplomacy_current as legacy
 require(Path(legacy.__file__).resolve()==(ROOT/'work/probe_diplomacy_current.py').resolve() and legacy.ROOT==ROOT,'RO module origin')
 _,signature=legacy.verified_executable(exe);require(signature=={'timestamp':c['pe']['timestamp'],'size':c['pe']['image_size']},'PE identity')
 reader=legacy.ProcessReader(pid,exe,signature)
 try:
  before=support.held_identity(reader,pid,int(creation,16));result=capture(reader,reader.base)
  require(canonical(support.held_identity(reader,pid,int(creation,16)))==canonical(before),'held identity changed')
  legacy.verify_module_signature(legacy.pe_signature(reader,reader.base),signature);require(support.sha(exe)==EXE_SHA,'disk changed');require(reader.bytes_read<=support.MAX_TOTAL,'including PE read bound')
  result['source_kind']='held_process_readonly';result['process']=dict(identity=before,path=str(exe),disk_exe_sha256=EXE_SHA,loaded_full_image_hash_verified=False,rights=['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'])
  inspect_capture(result);return result
 finally:reader.close()
