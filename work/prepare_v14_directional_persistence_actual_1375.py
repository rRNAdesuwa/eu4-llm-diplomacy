"""Root chooses two fixed saves and nine explicit observations; no live access/review."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='work/runtime/native1375-v14/'
PIN='84debe9a44bd2638011ac11ff4c6d7d234c5322cc3f4fa3ac8fd0b55659a3b41'
GROUPS=[
 ('positive',35552,'01dd56b0fafda55d','0x24b15e60070',56457456,[
  ('cancel_military_access','directional-ask-military-setup-after-18356.json','1444.12.1'),
  ('dissolve_alliance','directional-alliance-setup-after-submit-18356.json','1444.11.25'),
  ('cancel_subsidies','directional-give-subsidies-after-18356.json','1444.11.15')]),
 ('final',59012,'01dd56b271750dad','0x1340dcc6010',56457600,[
  ('cancel_military_access','directional-cancel-military-after-18356.json',None),
  ('dissolve_alliance','directional-dissolve-alliance-after-18356.json',None),
  ('cancel_subsidies','directional-cancel-subsidies-after-18356.json',None),
  ('cancel_fleet_basing_rights','directional-cancel-fleet-after-18356.json',None),
  ('revoke_military_access','directional-revoke-military-after-18356.json',None),
  ('revoke_embargo','directional-revoke-embargo-after-18356.json',None)])]

def require(ok,msg):
 if not ok:raise ValueError(msg)
def raw(path):
 with path.open('rb') as f:data=f.read(4*1024*1024+1)
 require(0<len(data)<=4*1024*1024,'Bounded source required');return data
def digest(data):return hashlib.sha256(data).hexdigest()
def main():
 require(digest(raw(ROOT/'work/candidates/v14-directional-persistence-review/matcher.py'))==PIN,'Reviewed matcher changed')
 entries={};paths={}
 def add(key,filename):
  name=BASE+filename
  if name in paths:return paths[name]
  p=ROOT/name;require(p.is_file() and not p.is_symlink() and not p.is_junction(),'Indirect input')
  data=raw(p);entries[key]=dict(path=name,size_bytes=len(data),sha256=digest(data));paths[name]=key;return key
 groups=[]
 for label,pid,creation,world,date,relations in GROUPS:
  group=dict(label=label,binding=dict(pid=pid,creation=creation,world=world,raw_date=date),
   extraction=add(label+'_extraction','directional-'+label+'-save-snapshot-18356.json'),
   launch=add(label+'_launch','directional-'+label+'-cold-reload-launch-20261008a.json'),
   identity=add(label+'_identity','directional-'+label+'-reloaded-identity-'+str(pid)+'.json'),
   exit=add(label+'_exit','directional-'+label+'-cold-reload-exit-'+str(pid)+'.json'),relations=[])
  for action,filename,start in relations:
   group['relations'].append(dict(action=action,prior=add(label+'_'+action+'_prior',filename),
    reloaded=add(label+'_'+action+'_reload','directional-'+label+'-reloaded-'+action+'-'+str(pid)+'.json'),
    expected='active' if label=='positive' else 'absent',start_date=start))
  groups.append(group)
 case=dict(schema_version=1,purpose='v14_directional_persistence_case',finalized=True,inputs=entries,groups=groups)
 for d in entries.values():require(digest(raw(ROOT/d['path']))==d['sha256'],'Evidence changed')
 dest=ROOT/(BASE+'directional-persistence-case-18356.json')
 data=(json.dumps(case,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
 with dest.open('xb') as f:f.write(data);f.flush()
 print(json.dumps(dict(status='explicit_persistence_case_frozen_not_reviewed',path=str(dest),sha256=digest(data),
  input_count=len(entries),observation_count=9,game_accessed=False,capability_promoted=False)))
if __name__=='__main__':main()
