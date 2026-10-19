"""Offline adapter: bind frozen validator imports to the reviewed formal root."""
import argparse,hashlib,importlib,importlib.util,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BUILDER=ROOT/'work/candidates/v17-preflight-case-builder-action-catalog'
REVIEWER=ROOT/'work/candidates/v17-acceptance-experiment-review'
MIRROR=ROOT/'work/candidates/v17-acceptance-pin-review/files'
BUILD=ROOT/'work/runtime/native1375-v17/build.json'
BUILD_SHA='b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d'
PINS={'build_case.py':'f76050952fbef82f9c4d5ce82e38e44ca8d1f145830af8efd1af207f90bfab76','source-pins.json':'041e3fc5ee45a68b9a000b5cda2540191c8a03a363b3dd380a7a1c9cd3bcd09e'}
MODULES=('work.native.lab_protocol_v17_1375','tools.verify_diplomacy_lifecycle_v17','tools.verify_diplomacy_preview_v17','tools.verify_diplomacy_command_v17','tools.verify_diplomacy_owned_peace_v17','tools.verify_diplomacy_acceptance_v17')
def require(ok,message):
 if not ok:raise ValueError(message)
def bounded(p,limit):
 with Path(p).open('rb') as f:b=f.read(limit+1)
 require(len(b)<=limit,'File budget exceeded');return b
def digest(b):return hashlib.sha256(b).hexdigest()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
def source_context():
 for name,expected in PINS.items():require(digest(bounded(BUILDER/name,128*1024))==expected,'Frozen builder dependency changed: '+name)
 b=load('fixed_v17_preflight_builder_for_adapter',BUILDER/'build_case.py');b.checked_sources()
 manifest_raw=bounded(BUILD,65536);require(digest(manifest_raw)==BUILD_SHA,'Fixed formal manifest changed');manifest=b.decode(manifest_raw)
 return b,manifest
def origin(module,name):
 expected=ROOT/(name.replace('.','/')+'.py')
 require(Path(module.__file__).resolve()==expected.resolve(),'Nonformal cached module: '+name)
 return expected

def configured():
 b,manifest=source_context()
 # Insert the formal repository before any frozen reviewer's mirror side effect.
 sys.path.insert(0,str(ROOT))
 loaded={}
 for name in MODULES:
  expected=b.relative(ROOT,name.replace('.','/')+'.py');relative=expected.relative_to(ROOT).as_posix()
  raw=bounded(expected,128*1024);expected_hash=manifest['host_source_sha256'][relative]
  require(digest(raw)==expected_hash.lower(),'Formal module bytes differ: '+name)
  module=importlib.import_module(name);origin(module,name);loaded[name]=module
 lab=loaded[MODULES[0]]
 reviewer=load('fixed_v17_frozen_reviewer_for_adapter',REVIEWER/'reviewer.py')
 # Late imports must also resolve to the formal root. No frozen source/object
 # constants or verification functions are patched, and no missing files copied.
 sys.path[:]=[entry for entry in sys.path if Path(entry or '.').resolve()!=MIRROR.resolve()]
 sys.path.insert(0,str(ROOT))
 for name,module in loaded.items():require(sys.modules[name] is module,'Cached module replaced');origin(module,name)
 require(reviewer.lab is lab,'Frozen reviewer did not reuse formal protocol')
 verified,h=lab.verify_build(output=BUILD.parent)
 require(h==BUILD_SHA and verified==manifest,'Formal default-root verification differs')
 b.checked_sources()
 return b,reviewer,loaded

def inspect_imports():
 b,r,modules=configured()
 return {'schema_version':1,'purpose':'offline_formal_import_origin_check','passed':True,'manifest_sha256':BUILD_SHA,
  'module_origins':{name:str(Path(module.__file__).relative_to(ROOT).as_posix()) for name,module in modules.items()},
  'default_protocol_root':str(r.lab.ROOT),'mirror_in_sys_path':any(Path(x or '.').resolve()==MIRROR.resolve() for x in sys.path),
  'build_verification_mocked':False,'actual_case_read':False,'process_accessed':False,'proof_conditions_changed':False}

def preflight(case_name,scope_name,output_name):
 b,r,modules=configured()
 paths=[b.relative(ROOT,n) for n in (case_name,scope_name,output_name)]
 require(len({p.resolve() for p in paths})==3,'Case/scope/output paths must be distinct')
 case_path,scope_path,output=paths
 require(not output.exists(),'Output already exists')
 scope_raw=bounded(scope_path,8192);case_raw=bounded(case_path,512*1024)
 scope=b.decode(scope_raw);case=b.decode(case_raw)
 require(b.wire({k:scope[k] for k in b.EXPECTED})==b.wire(b.EXPECTED),'Wrong fixed 63500 scope')
 require(scope['preflight_case']==case_name and scope['preflight_summary']==output_name,'Scope output binding differs')
 _,pre=r.configure(scope)
 for name,module in modules.items():origin(module,name)
 result=pre.review(case,root=ROOT)
 require(bounded(scope_path,8192)==scope_raw and bounded(case_path,512*1024)==case_raw,'Case/scope changed')
 r.dependencies();b.checked_sources()
 require(not output.exists(),'Output appeared during review')
 r.write_new(output,result)
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('check-imports','preflight'))
 p.add_argument('--case');p.add_argument('--scope');p.add_argument('--output',required=True);a=p.parse_args()
 if a.command=='check-imports':
  require(a.case is None and a.scope is None,'No case inputs for import check');result=inspect_imports();path=Path(a.output)
  with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
 else:
  require(a.case is not None and a.scope is not None,'Explicit case/scope required');preflight(a.case,a.scope,a.output)
if __name__=='__main__':main()
