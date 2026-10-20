"""Explicit new-process plans only; no game access or publication."""
import hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME='work/runtime/native1375-v17/'
PID,CREATION,WORLD,THREAD=9656,'01dd56cd3782fcca','0x2208d069040',20712

def module(name,path,digest):
 raw=path.read_bytes();assert len(raw)<128*1024 and hashlib.sha256(raw).hexdigest()==digest
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def create(path,value):
 with path.open('x',encoding='utf-8',newline='\n') as dst:json.dump(value,dst,indent=2);dst.write('\n')
 return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 builder=module('explicit_preflight_builder',ROOT/'work/candidates/v17-preflight-next-process-builder/build_case.py','110d26e431ab31591d7f606fc98e067f4e12f8869fe3df148a44e9a16f895c50')
 assert hashlib.sha256((ROOT/'work/candidates/v17-preflight-next-process-builder/review.json').read_bytes()).hexdigest()=='17402eb11cb45622e7e5584f9d04a12043bcc07da6788535ed580e5cbf546c1d'
 cfg=builder.template();output=RUNTIME+'preflight-case-9656';prefix=RUNTIME+'directional-preflight-prefix-9656'
 cfg['scope'].update(pid=PID,creation=CREATION,world_cookie=WORLD,window_thread=THREAD,initial_raw_date=56456976,
                     prefix_bytes=164094,prefix_sha256='d2d247d91d1d2b37b4b1066561ed0e73320888355423b8bb65c0ee7fe1423527',
                     preflight_case=output+'/preflight-case.json',preflight_summary=output+'/preflight-summary.json')
 cfg.update(output_directory=output,prefix_directory=prefix)
 paths={k:prefix+'/'+k for k in builder.FILES}
 paths.update(before=RUNTIME+'baseline-before-injection-9656.json',after=RUNTIME+'after-stages-before-fixture-9656.json',
              loader=RUNTIME+'loader-actual-9656.json',status=RUNTIME+'stage-command-status-9656.json',
              build=RUNTIME+'build.json',snapshot=RUNTIME+'directional-preflight-prefix-snapshot-9656.json')
 assert set(paths)==builder.INPUTS
 for key,name in paths.items():
  raw=builder.bounded(ROOT/name,builder.MAX_FILE)
  cfg['inputs'][key]={'path':name,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 builder.validate_scope(cfg['scope'])
 cfg_sha=create(ROOT/RUNTIME/'preflight-construction-plan-9656.json',cfg)
 batch=module('explicit_batch_driver',ROOT/'work/candidates/v17-batch-host-review-r3/batch.py','75a1fdd1657862c1e019cc25e711a45a095909c18eeef1570d2c61db20a8b23e')
 plan={'protocol':'EU4LAB/3','purpose':'restricted_pair_lab_1375_v17','pid':PID,'creation':CREATION,'world_cookie':WORLD,
       'window_thread':THREAD,'first_sequence':2,'observation_mode':'initial_final','run_id':'9656-20261008-batch36-c',
       'rows':[{'action':a,'target':t} for a,t in batch.MATRIX]}
 assert batch.validate_plan(plan)==plan
 plan_sha=create(ROOT/RUNTIME/'batch-plan-9656-c.json',plan)
 print(json.dumps({'construction_plan_sha256':cfg_sha,'batch_plan_sha256':plan_sha,'pid':PID,'fixture_not_published':True}))

if __name__=='__main__':main()
