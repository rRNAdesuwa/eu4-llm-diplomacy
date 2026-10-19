"""Strict selected serialized layouts; bounded streaming and no runtime APIs."""
from pathlib import Path
import hashlib,json,re,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from work import inspect_diplomacy_save as g

MAX_SAVE=64*1024*1024
COUNTRIES={'FRA','ENG','NAV','POR','BUR'}
MODIFIERS={'corrupt_officials','reputation_sabotaged','discontent_sowed','merchants_slandered','recruitment_sabotaged'}
DIRECT={'ENG':{'modifier'},'FRA':{'rival','enemy','initialized_rivals','historical_rivals','diplomats'},
 'BUR':{'rival','enemy','initialized_rivals','historical_rivals','trade_embargoed_by'},
 'NAV':{'subject_focus','subject_interactions','overlord','trade_embargoes','num_of_trade_embargos','transfer_trade_power_to'},'POR':set()}
SCALARS={'enemy','initialized_rivals','subject_focus','overlord','num_of_trade_embargos','owner','controller'}
PAIRS={('FRA','POR'),('POR','FRA'),('FRA','BUR'),('BUR','FRA'),('NAV','BUR'),('BUR','NAV')}
class Rejected(ValueError):pass
def require(ok,why):
 if not ok:raise Rejected(why)
def integer(value,lo=0,hi=2**31-1):return type(value)is int and lo<=value<=hi
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def number(value,lo=0,hi=2**31-1):
 require(type(value)is str and re.fullmatch(r'0|[1-9][0-9]*',value) is not None,'Canonical nonnegative integer text')
 parsed=int(value);require(lo<=parsed<=hi,'Serialized integer range');return parsed
def date(value):
 require(type(value)is str and re.fullmatch(r'[1-9][0-9]{0,3}\.[1-9][0-9]?\.[1-9][0-9]?',value) is not None,'Date token')
 y,m,d=map(int,value.split('.'));require(1<=m<=12 and 1<=d<=31,'Date range');return value
def tag(value):require(type(value)is str and re.fullmatch('[A-Z][A-Z0-9]{2}',value) is not None,'Country tag');return value
def booltext(value):require(type(value)is str and value in ('yes','no'),'Serialized boolean');return value=='yes'
def scalar(entry):
 require(type(entry)is dict and set(entry)=={'key','value','raw_value','line','byte_offset'},'Scalar source schema')
 require(entry['key'] is None or type(entry['key'])is str,'Scalar key type')
 require(type(entry['value'])is str and type(entry['raw_value'])is str and integer(entry['line'],1) and integer(entry['byte_offset']),'Scalar source types')
 raw=entry['raw_value'];value=raw[1:-1] if raw.startswith('"') and raw.endswith('"') else raw
 require(value==entry['value'],'Value/raw token differ');return value
def block(entry):
 require(type(entry)is dict and set(entry)=={'key','entries','line','byte_offset'} and type(entry['key'])is str
         and type(entry['entries'])is list and len(entry['entries'])<=g.MAX_CAPTURE_NODES
         and integer(entry['line'],1) and integer(entry['byte_offset']),'Block source schema')
 return entry['entries']
def flat(entry,allowed=None):
 result={}
 for child in block(entry):
  value=scalar(child);key=child['key'];require(type(key)is str and key not in result,'Duplicate/bare/nested field');result[key]=value
 require(allowed is None or set(result)==set(allowed),'Selected field keys differ');return result
def atom_list(entry,limit=32):
 children=block(entry);require(len(children)<=limit,'List count bound')
 for child in children:require(child['key'] is None,'Named item in bare list')
 return [scalar(x) for x in children]
class Reader(g.BoundedReader):
 def read(self,count):
  require(integer(count,0,g.CHUNK),'Strict read budget')
  raw=super().read(count);require(self.count<=MAX_SAVE,'Save streaming budget');return raw

def parse_stream(source):
 reader=Reader(source);path=[];capture=None;capture_path=None;records=[];metadata={};containers={x:0 for x in ('countries','provinces','diplomacy')}
 countries={x:0 for x in COUNTRIES};province=0;map_seen=False;map_pending=False;nodes=0;retained=0;scanned=0
 def retain(record,where,end,count,size):
  nonlocal nodes,retained
  nodes+=count;retained+=size
  require(nodes<=g.MAX_RETAINED_NODES and retained<=g.MAX_RETAINED and len(records)<128,'Retained selection budget')
  records.append({'path':where,'record':record,'end_byte':end})
 for event,key,token in g.events(reader):
  if map_pending:
   require(not path and event=='start' and key is None and token[0]=='{' and token[1]==b'{','map_area_data anonymous block')
   key='map_area_data';map_pending=False
  elif not path and event=='bare':
   require(token[0]=='atom' and token[1]==b'map_area_data' and not map_seen,'Unexpected or duplicate top bare token')
   map_seen=True;map_pending=True;continue
  elif not path and (key=='map_area_data' or event=='start' and key is None):raise Rejected('Unsupported top anonymous/assigned map_area_data')
  if path in (['countries'],['provinces'],['diplomacy']) or len(path)==2 and path[0]=='countries' and path[1] in COUNTRIES:
   require(event!='bare' and not(event=='start' and key is None),'Required structural assignments')
  if not path and key in containers:
   require(event=='start','Required container must be block');containers[key]+=1;require(containers[key]==1,'Duplicate container')
  if path==['countries'] and key in COUNTRIES:
   require(event=='start','Selected country must be block');countries[key]+=1;require(countries[key]==1,'Duplicate country')
  if path==['provinces'] and key=='-227':
   require(event=='start','Selected province must be block');province+=1;require(province==1,'Duplicate selected province')
  if capture is not None:
   if capture.add(event,key,token):
    scanned+=1;require(scanned<=4096,'Candidate block scan budget')
    keep=True
    if capture_path[0]=='diplomacy' and capture_path[-1] in ('dependency','transfer_trade_power'):
     fields=flat(capture.root);require('first' in fields and 'second' in fields,'Relation participants missing')
     tag(fields['first']);tag(fields['second'])
     keep=(fields['first'],fields['second'])==(('FRA','NAV') if capture_path[-1]=='dependency' else ('NAV','FRA'))
    if keep:retain(capture.root,capture_path,token[3]+len(token[1]),capture.nodes,capture.bytes)
    capture=None
  else:
   want=(len(path)==2 and path[0]=='countries' and path[1] in COUNTRIES and key in DIRECT[path[1]])
   want|=(len(path)==3 and path[0]=='countries' and path[2]=='active_relations' and (path[1],key) in PAIRS)
   want|=(path==['diplomacy'] and key in ('curry_favors','dependency','transfer_trade_power'))
   want|=(path==['provinces','-227'] and key in ('owner','controller','diplomacy_construction'))
   if want:
    require(event==('scalar' if key in SCALARS else 'start'),'Selected scalar/container shape')
    if event=='start':capture=g.Capture(key,token,None);capture_path=path+[key]
    else:retain(g.scalar_entry(key,token),path+[key],token[3]+len(token[1]),1,len(token[1]))
   if not path and event=='scalar' and key in ('date','player'):
    require(key not in metadata,'Duplicate metadata');metadata[key]=g.scalar_entry(key,token)
  if event=='start':path.append(key)
  elif event=='end':path.pop()
 require(not path and capture is None and not map_pending and all(v==1 for v in containers.values()) and all(v==1 for v in countries.values()) and province==1,'Incomplete required save structure')
 require(set(metadata)=={'date','player'} and scalar(metadata['player'])=='FRA','Metadata/player missing')
 date(scalar(metadata['date']))
 return {'schema':1,'kind':'selected_serialized_spy_subject_curry_layout','parsed_complete':True,'bytes':reader.count,'sha256':reader.sha256.hexdigest(),
         'metadata':metadata,'records':records,'retained_nodes':nodes,'retained_token_bytes':retained,'scanned_candidate_blocks':scanned}

def selected(parsed):
 require(type(parsed)is dict and parsed.get('schema')==1 and type(parsed['schema'])is int and parsed.get('parsed_complete') is True,'Parsed layout expected')
 require(type(parsed.get('records'))is list and len(parsed['records'])<=128,'Selected record budget')
 grouped={}
 for row in parsed['records']:
  require(type(row)is dict and set(row)=={'path','record','end_byte'} and type(row['path'])is list and all(type(x)is str for x in row['path']) and integer(row['end_byte']),'Projection record schema')
  grouped.setdefault(tuple(row['path']),[]).append(row['record'])
 def one(*path):
  found=grouped.get(path,[]);require(len(found)==1,'Missing/duplicate selected path: '+ '/'.join(path));return found[0]
 modifiers={}
 for entry in grouped.get(('countries','ENG','modifier'),[]):
  fields=flat(entry);require('modifier' in fields,'Modifier name missing')
  if fields['modifier'] in MODIFIERS:
   require(set(fields)=={'modifier','date'} and fields['modifier'] not in modifiers,'Duplicate/unknown selected modifier variant')
   modifiers[fields['modifier']]={'date':date(fields['date']),'byte_offset':entry['byte_offset']}
 require(set(modifiers)==MODIFIERS,'Five selected modifiers required; missing is unknown')
 focus=number(scalar(one('countries','NAV','subject_focus')),0,5)
 interactions=[booltext(x) for x in atom_list(one('countries','NAV','subject_interactions'),7)]
 require(len(interactions)==7,'Exact observed seven-entry serialized layout')
 require(tag(scalar(one('countries','NAV','overlord')))=='FRA','Subject overlord differs')
 rivals={};enemies={}
 for country in ('FRA','BUR'):
  require(booltext(scalar(one('countries',country,'initialized_rivals'))) is True,'Rival initialization flag')
  rivals[country]=[];seen=set()
  for entry in grouped.get(('countries',country,'rival'),[]):
   fields=flat(entry,{'country','date'});target=tag(fields['country']);require(target not in seen and target!=country,'Duplicate/self rival');seen.add(target)
   rivals[country].append({'country':target,'date':date(fields['date']),'byte_offset':entry['byte_offset']})
  require(0<len(rivals[country])<=16,'Rival list range')
  enemies[country]=[tag(scalar(x)) for x in grouped.get(('countries',country,'enemy'),[])]
  require(len(enemies[country])<=16 and len(set(enemies[country]))==len(enemies[country]),'Enemy list range/duplicates')
 relation=flat(one('diplomacy','curry_favors'),{'first','second','start_date','envoy'})
 require(relation['first']=='FRA' and relation['second']=='POR','Curry direction differs')
 date(relation['start_date']);envoy_id=number(relation['envoy'])
 envoys=[];ids=set()
 for entry in block(one('countries','FRA','diplomats')):
  require(entry['key']=='envoy','Diplomat child type')
  fields=flat(entry);require(set(fields) in ({'name','type','id'},{'action','name','type','id'}),'Unknown envoy serialization variant')
  eid=number(fields['id']);require(eid not in ids and number(fields['type'])==3,'Duplicate envoy/type');ids.add(eid)
  require(0<len(fields['name'])<=256,'Bounded envoy name')
  action=number(fields['action'],0,2) if 'action' in fields else None
  envoys.append({'id':eid,'type':3,'action_serialized':action,'name':fields['name'],'byte_offset':entry['byte_offset']})
 require(0<len(envoys)<=1024,'Envoy count bound')
 matched=[x for x in envoys if x['id']==envoy_id];require(len(matched)==1 and matched[0]['action_serialized']==2,'Curry envoy reference/action differs')
 mission=flat(one('provinces','-227','diplomacy_construction'),{'start_date','total','original_total','date','envoy','country','actor','recipient','from_province','to_province','once','action_token'})
 require(mission['action_token']=='curry_favors' and mission['country']==mission['actor']=='FRA' and mission['recipient']=='POR'
         and number(mission['to_province'])==227 and number(mission['from_province'],1)>0
         and number(mission['envoy'])==envoy_id and mission['start_date']==relation['start_date'] and booltext(mission['once']) is False,'Curry construction binding differs')
 date(mission['date']);number(mission['total'],1);number(mission['original_total'],1)
 require(scalar(one('provinces','-227','owner'))==scalar(one('provinces','-227','controller'))=='POR','Selected province owner/controller differs')
 dependency=flat(one('diplomacy','dependency'),{'first','second','start_date','subject_type'})
 require(dependency['first']=='FRA' and dependency['second']=='NAV' and dependency['subject_type']=='vassal','Dependency direction/type')
 date(dependency['start_date'])
 trade=flat(one('diplomacy','transfer_trade_power'),{'first','second','start_date','amount','is_enforced'})
 require(trade['first']=='NAV' and trade['second']=='FRA' and re.fullmatch(r'(0\.[0-9]{3}|1\.000)',trade['amount']) is not None,'Trade direction/fixed decimal token')
 date(trade['start_date']);booltext(trade['is_enforced'])
 effects={'trade_embargoes':[tag(x) for x in atom_list(one('countries','NAV','trade_embargoes'))],
          'trade_embargoed_by':[tag(x) for x in atom_list(one('countries','BUR','trade_embargoed_by'))],
          'transfer_trade_power_to':[tag(x) for x in atom_list(one('countries','NAV','transfer_trade_power_to'))]}
 require(number(scalar(one('countries','NAV','num_of_trade_embargos')))==len(effects['trade_embargoes']),'Embargo serialized count differs')
 active={}
 for a,t in sorted(PAIRS):active[a+'->'+t]=flat(one('countries',a,'active_relations',t))
 for fields in active.values():
  for k,v in fields.items():
   require(k in {'trust_value','last_send_diplomat','spy_network','attitude','has_culture_group_claim','is_building_spy_network','is_embargoing','favors'},'Unknown selected relation field')
   if k in {'has_culture_group_claim','is_building_spy_network','is_embargoing'}:booltext(v)
   elif k in {'trust_value','spy_network'}:number(v)
   elif k=='last_send_diplomat':date(v)
   elif k=='favors':require(re.fullmatch(r'(0|[1-9][0-9]*)\.[0-9]{3}',v) is not None,'Favors text')
   else:require(re.fullmatch(r'attitude_[a-z_]+',v) is not None,'Attitude text')
 return {'save_date':date(scalar(parsed['metadata']['date'])),'player':'FRA','spy_modifiers':modifiers,
  'nav':{'subject_focus':focus,'subject_interactions_raw':interactions,'set_positions':[i for i,v in enumerate(interactions) if v],
         'named_bit_order_verified':False,'dependency':dependency,'trade_power':trade,**effects},
  'curry':{'relation':relation,'construction':mission,'envoys':envoys,'linked_envoy_id':envoy_id,'serialized_reference_consistent':True},
  'rivals':rivals,'enemies':enemies,'selected_active_relations':active,
  'serialized_layout_observed':True,'runtime_verified':False,'execution_verified':False,'request_causality_verified':False,
  'persistence_verified':False,'reload_verified':False,'whole_world_unchanged_verified':False,'production_ready':False}
