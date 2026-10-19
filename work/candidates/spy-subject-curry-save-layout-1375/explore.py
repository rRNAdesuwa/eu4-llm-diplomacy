"""Fixed saved-file exploration. Stream events; never capture a whole country."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from work import inspect_diplomacy_save as g

SAVE_SHA='8a8f812ab9a33b8479f36007077e05a870128e79afa90961eac579340f1d8566'
SAVE_SIZE=36756072
COUNTRIES={'FRA','ENG','NAV','POR','BUR'}
KEYS={'ENG':{'modifier'},'FRA':{'rival','enemy','initialized_rivals','historical_rivals','diplomats'},
      'BUR':{'rival','enemy','initialized_rivals','historical_rivals','trade_embargoed_by'},
      'NAV':{'subject_focus','subject_interactions','overlord','trade_embargoes','num_of_trade_embargos','transfer_trade_power_to'},'POR':set()}

def extract(source):
 reader=g.BoundedReader(source);path=[];begins=[];capture=None;capture_path=None;records=[];tokens=[];metadata={};countries={}
 for event,key,token in g.events(reader):
  if reader.count>64*1024*1024:raise g.SaveError('64MiB total bound')
  if capture is not None:
   if capture.add(event,key,token):
    records.append({'path':capture_path,'record':capture.root,'end_byte':token[3]+len(token[1]),'captured_nodes':capture.nodes,'captured_bytes':capture.bytes})
    if len(records)>128 or sum(x['captured_bytes'] for x in records)>g.MAX_RETAINED or sum(x['captured_nodes'] for x in records)>g.MAX_RETAINED_NODES:raise g.SaveError('Retained budget')
    capture=None
  else:
   want=False
   if len(path)==2 and path[0]=='countries' and path[1] in COUNTRIES and key in KEYS[path[1]]:want=True
   if len(path)==3 and path[0]=='countries' and path[2]=='active_relations' and (path[1],key) in {('FRA','POR'),('POR','FRA'),('FRA','BUR'),('BUR','FRA'),('NAV','BUR'),('BUR','NAV')}:want=True
   if path==['diplomacy'] and key in {'curry_favors'}:want=True
   if want:
    if event=='start':capture=g.Capture(key,token,None);capture_path=path+[key]
    elif event=='scalar':records.append({'path':path+[key],'record':g.scalar_entry(key,token),'end_byte':token[3]+len(token[1]),'captured_nodes':1,'captured_bytes':len(token[1])})
   if not path and event=='scalar' and key in {'date','player'}:
    if key in metadata:raise g.SaveError('Duplicate metadata')
    metadata[key]=g.scalar_entry(key,token)
   if path==['countries'] and event=='start' and key in COUNTRIES:
    if key in countries:raise g.SaveError('Duplicate country')
    countries[key]={'line':token[2],'byte_offset':token[3]}
  if event=='scalar' and token[1].strip(b'"')==b'curry_favors':
   tokens.append({'path':path+[key],'token':g.scalar_entry(key,token),'parents':list(begins)})
   if len(tokens)>32:raise g.SaveError('Token hit budget')
  if event=='start':path.append(key);begins.append({'key':key,'line':token[2],'byte_offset':token[3]})
  elif event=='end':path.pop();begins.pop()
 if capture is not None or path or set(countries)!=COUNTRIES:raise g.SaveError('Incomplete required source')
 return {'parsed_complete':True,'bytes':reader.count,'sha256':reader.sha256.hexdigest(),'metadata':metadata,'countries':countries,'records':records,'curry_token_hits':tokens,
         'limits':{'chunk':g.CHUNK,'total':64*1024*1024,'capture':g.MAX_CAPTURE,'capture_nodes':g.MAX_CAPTURE_NODES,'retained':g.MAX_RETAINED,'retained_nodes':g.MAX_RETAINED_NODES,'depth':g.MAX_DEPTH},
         'runtime_verified':False,'request_causality_verified':False,'persistence_verified':False,'reload_verified':False}

def main():
 reportpath=ROOT/'work/runtime/spy-subject-curry-stopped-save-38232.json'
 with reportpath.open('rb') as stream:raw=stream.read(4*1024*1024+1)
 if len(raw)>4*1024*1024:raise g.SaveError('Source report bound')
 report=json.loads(raw);save=Path(report['source']['path']);before=save.stat()
 if before.st_size!=SAVE_SIZE or report['source']['sha256'].lower()!=SAVE_SHA:raise g.SaveError('Fixed source mismatch')
 with save.open('rb') as source:result=extract(source)
 if result['bytes']!=SAVE_SIZE or result['sha256']!=SAVE_SHA:raise g.SaveError('Full stream mismatch')
 after=save.stat()
 if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):raise g.SaveError('File changed')
 result['source']={'path':str(save),'sha256':SAVE_SHA,'bytes':SAVE_SIZE,'stat_unchanged':True,'root_report_sha256':hashlib.sha256(raw).hexdigest()}
 with (HERE/'exploration.json').open('x',encoding='ascii') as stream:json.dump(result,stream,indent=2,sort_keys=True,ensure_ascii=True)
 print(json.dumps({'records':len(result['records']),'curry_token_hits':result['curry_token_hits'],'bytes':result['bytes'],'sha256':result['sha256']},ensure_ascii=True))
if __name__=='__main__':main()
