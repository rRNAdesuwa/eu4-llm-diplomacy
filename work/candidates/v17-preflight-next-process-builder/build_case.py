"""Explicit-process offline preflight case construction. No process, request or review execution."""
import argparse,hashlib,importlib.util,json,os,re,sys,tempfile,uuid
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
RUNTIME='work/runtime/native1375-v17/'
REVIEWER='work/candidates/v17-acceptance-experiment-review/'
EXPECTED={'dll_sha256':'d8b962b19d489fd366f346416bb72a8958f3dc53b504a29ec835d3b99cafa1ee',
 'manifest_sha256':'b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d','bridge_start_rva':28832}
SESSION_FIELDS={'pid','creation','world_cookie','window_thread','initial_raw_date','prefix_bytes','prefix_sha256'}
FILES=('session.json','install.claim','research-1375.jsonl','phase-lifecycle.claim','phase-owned-peace-lifecycle.claim','phase-preview.claim','phase-command.claim')
INPUTS=set(FILES)|{'before','after','loader','status','build','snapshot'}
MAX_FILE,MAX_TOTAL=2*1024*1024,8*1024*1024

def require(ok,message):
 if not ok:raise ValueError(message)
def integer(v,lo=0,hi=2**64-1):return type(v) is int and lo<=v<=hi
def sha(raw):return hashlib.sha256(raw).hexdigest()
def wire(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def decode(raw):
 def pairs(rows):
  d={}
  for k,v in rows:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 d=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
 require(type(d) is dict,'JSON object required');return d
def bounded(path,maximum=MAX_FILE):
 with Path(path).open('rb') as f:b=f.read(maximum+1)
 require(len(b)<=maximum,'Read budget exceeded');return b
def relative(root,name):
 require(type(name) is str and '\\' not in name and ':' not in name,'Canonical relative path')
 pure=PurePosixPath(name)
 require(pure.parts and not pure.is_absolute() and str(pure)==name and all(x not in ('.','..') and not x.startswith('session-') for x in pure.parts),'Unsafe/growing session path')
 top=Path(root).resolve();p=top
 for item in pure.parts:
  p=p/item;require(not p.is_symlink() and not p.is_junction(),'Linked path')
 require(p.resolve().is_relative_to(top),'Path escaped root');return p

def template():
 return {'schema_version':1,'purpose':'explicit_process_v17_preflight_construction_plan',
  'scope':dict(EXPECTED,**dict.fromkeys(SESSION_FIELDS),preflight_case=None,preflight_summary=None),
  'prefix_directory':None,'output_directory':None,
  'inputs':{k:{'path':None,'size_bytes':None,'sha256':None} for k in sorted(INPUTS)}}

def validate_scope(scope):
 require(type(scope) is dict and set(scope)==set(EXPECTED)|SESSION_FIELDS|{'preflight_case','preflight_summary'},'Scope schema')
 require(wire({k:scope[k] for k in EXPECTED})==wire(EXPECTED),'Wrong fixed build/export or scalar type')
 require(integer(scope['pid'],1,2**32-1) and integer(scope['window_thread'],1,2**32-1)
  and integer(scope['initial_raw_date'],1,2**31-1) and integer(scope['prefix_bytes'],1,MAX_FILE),'Explicit process/date/prefix scalar types')
 require(type(scope['creation']) is str and re.fullmatch('[0-9a-f]{16}',scope['creation']) and int(scope['creation'],16)>0,'Exact explicit process creation')
 require(type(scope['world_cookie']) is str and re.fullmatch('0x[0-9a-f]+',scope['world_cookie'])
  and 0x10000<=int(scope['world_cookie'],16)<2**64,'Exact explicit world')
 require(type(scope['prefix_sha256']) is str and re.fullmatch('[0-9a-f]{64}',scope['prefix_sha256']),'Exact explicit prefix SHA')
 return scope

def checked_sources():
 source=decode(bounded(HERE/'source-pins.json',128*1024));files=source['files'];total=0
 require(type(files) is dict and 1<=len(files)<=256,'Source inventory bound')
 for name,d in files.items():
  require(type(d) is dict and set(d)=={'bytes','sha256'} and integer(d['bytes'],0,8*1024*1024)
   and type(d['sha256']) is str and re.fullmatch('[0-9a-f]{64}',d['sha256']),'Source descriptor')
  b=bounded(relative(ROOT,name),8*1024*1024);total+=len(b)
  require(total<=32*1024*1024 and len(b)==d['bytes'] and sha(b)==d['sha256'],'Frozen source changed: '+name)
 return files

def validators(scope):
 pins=checked_sources();path=ROOT/REVIEWER/'reviewer.py';name='v17_builder_validator_'+uuid.uuid4().hex
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
 _,pre=m.configure(scope)
 return pre,pins

def construct(config,root=ROOT):
 require(type(config) is dict and set(config)==set(template()) and type(config['schema_version']) is int and config['schema_version']==1
  and config['purpose']==template()['purpose'],'Construction plan schema')
 scope=validate_scope(config['scope'])
 prefix=config['prefix_directory'];output=config['output_directory']
 require(prefix==RUNTIME+'directional-preflight-prefix-'+str(scope['pid']),'Exact per-process frozen prefix directory required')
 require(type(output) is str and output.startswith(RUNTIME) and output!=RUNTIME.rstrip('/') and output!=prefix and not output.startswith(prefix+'/'),'Independent output directory')
 require(scope['preflight_case']==output+'/preflight-case.json' and scope['preflight_summary']==output+'/preflight-summary.json','Explicit NEW case/summary paths')
 relative(root,output);directory=relative(root,prefix)
 names=set()
 for entry in directory.iterdir():
  require(entry.is_file() and entry.name in FILES and entry.name not in names,'Exactly seven prefix files required');names.add(entry.name)
 require(names==set(FILES),'Missing prefix file')
 entries=config['inputs'];require(type(entries) is dict and set(entries)==INPUTS,'Need exact thirteen input descriptors')
 raw={};seen=set();total=0
 for key,d in entries.items():
  require(type(d) is dict and set(d)=={'path','size_bytes','sha256'} and integer(d['size_bytes'],1,MAX_FILE)
   and type(d['sha256']) is str and re.fullmatch('[0-9a-f]{64}',d['sha256']),'Input descriptor: '+key)
  name=d['path'];require(type(name) is str and name.startswith(RUNTIME) and name not in seen,'Duplicate/outside input');seen.add(name)
  if key in FILES:require(name==prefix+'/'+key,'Prefix path mismatch')
  else:require(name.endswith('.json'),'JSON capture expected')
  if key=='build':require(name==RUNTIME+'build.json','Fixed build path')
  value=bounded(relative(root,name),d['size_bytes']);total+=len(value)
  require(total<=MAX_TOTAL and len(value)==d['size_bytes'] and sha(value)==d['sha256'],'Input bytes/hash/budget: '+key);raw[key]=value
 require(entries['before']['path']!=entries['after']['path'] and sha(raw['before'])!=sha(raw['after']),'Two different capture files/bytes required')
 build=decode(raw['build'])
 require(sha(raw['build'])==scope['manifest_sha256'] and build['schema_version']==3 and type(build['schema_version']) is int
  and build['purpose']=='restricted_pair_lab_1375_v17' and build['protocol_version']=='EU4LAB/3'
  and type(build['dll_sha256']) is str and build['dll_sha256'].lower()==scope['dll_sha256']
  and type(build['bridge_start_export_rva']) is int and build['bridge_start_export_rva']==scope['bridge_start_rva'],'Fixed build/export mismatch')
 log=raw['research-1375.jsonl'];require(len(log)==scope['prefix_bytes'] and sha(log)==scope['prefix_sha256'] and log.endswith(b'\n'),'Exact prefix bytes/hash/line boundary')
 pre,pins=validators(scope)
 require(wire(pre.fixed_build(root))==wire(build),'Verified disk build differs from captured manifest')
 binding={'pid':scope['pid'],'creation':scope['creation'],'world_cookie':scope['world_cookie'],'raw_date':scope['initial_raw_date'],'window_thread':scope['window_thread']}
 pre.strict_preflight_stream(log,binding)
 before,after=decode(raw['before']),decode(raw['after'])
 held,first,times=pre.diagnostic(before,scope['pid'],scope['creation']);held2,last,times2=pre.diagnostic(after,scope['pid'],scope['creation'])
 require(wire(held)==wire(held2) and held['world_cookie']==scope['world_cookie'] and held['raw_date']==scope['initial_raw_date'],'Held identity/world/date changed')
 require(times[1]<times2[0],'Before/after captures overlap or copied capture')
 projection=('module_base','actor','target','player','current_raw_date','relation_cooldown','actor_diplomats')
 require(wire({k:first[k] for k in projection})==wire({k:last[k] for k in projection}),'Selected diagnostic state changed')
 pre.loader_record(decode(raw['loader']),scope['pid'],scope['creation'],held,root)
 # Parse the already-hashed bytes, never a second potentially changed directory view.
 with tempfile.TemporaryDirectory(prefix='eu4-v17-case-construction-') as temporary:
  frozen=Path(temporary)
  for name in FILES:(frozen/name).write_bytes(raw[name])
  meta=pre.lab.read_session_metadata(frozen,scope['pid'],scope['creation'])
  require(type(meta['window_thread']) is int and meta['window_thread']==scope['window_thread'],'Session thread mismatch')
  evidence=pre.lab.read_evidence(frozen,meta)
  pre.validate_preflight(evidence,held);pre.validate_status(decode(raw['status']),evidence,scope['pid'],scope['creation'])
 snapshot=decode(raw['snapshot'])
 expected_snapshot={'pid':scope['pid'],'creation':scope['creation'],'prefix_sha256':scope['prefix_sha256'],'prefix_bytes':scope['prefix_bytes'],
  'source_process_exit_observed':False,'whole_active_log_unchanged_verified':False,
  'snapshot_file_sha256':{k:sha(raw[k]) for k in FILES},'status_sha256':sha(raw['status'])}
 require(wire({k:snapshot[k] for k in expected_snapshot})==wire(expected_snapshot),'Snapshot identity/hash/types mismatch')
 case={'schema_version':1,'purpose':'fixed_v17_preflight_case','pid':scope['pid'],'creation':scope['creation'],
  'world_cookie':scope['world_cookie'],'raw_date':scope['initial_raw_date'],'window_thread':scope['window_thread'],
  'build_manifest_sha256':scope['manifest_sha256'],'dll_sha256':scope['dll_sha256'],'log_prefix_sha256':scope['prefix_sha256'],
  'log_prefix_bytes':scope['prefix_bytes'],'reviewer_sha256':pins[REVIEWER+'preflight.py']['sha256'],
  'inputs':{k:entries[k] for k in (*FILES,'before','after','loader','status')}}
 for key,d in entries.items():require(bounded(relative(root,d['path']),d['size_bytes'])==raw[key],'Input changed during construction')
 checked_sources()
 require(wire(pre.fixed_build(root))==wire(build),'Disk build changed during construction')
 return {'scope':scope,'case':case,'construction':{'schema_version':1,'finalized':False,'formal_review_performed':False,
  'preflight_only':True,'phase_counts':{'lifecycle':20,'owned_peace':1,'preview':72,'command':72},
  'selected_prefix_request_count':0,'whole_session_stopped':False,'runtime_promoted':False,'execution_verified':False,
  'default_owned_offer_only':True,'war_identity_verified':False,'white_peace_verified':False,'whole_world_unchanged':False,
  'two_held_ro_captures_validated':True,'inputs':entries,'source_pins':pins}}

def create(path,value):
 with path.open('xb') as f:f.write(wire(value));f.flush();os.fsync(f.fileno())
def publish(config,root=ROOT):
 packet=construct(config,root);directory=relative(root,config['output_directory']);directory.mkdir(exist_ok=False)
 for name,key in (('scope.json','scope'),('preflight-case.json','case'),('construction.json','construction')):create(directory/name,packet[key])
 return directory

def main():
 p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
 m.add_argument('--template',type=Path);m.add_argument('--config',type=Path);p.add_argument('--create',action='store_true');a=p.parse_args()
 if a.template:require(not a.create,'Template cannot create case');create(a.template,template())
 else:
  config=decode(bounded(a.config,65536))
  if a.create:print(publish(config))
  else:construct(config);print('Inputs validated; no output or formal review.')
if __name__=='__main__':main()
