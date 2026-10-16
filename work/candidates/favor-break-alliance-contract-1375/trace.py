"""Recheck bounded disk evidence, without opening a process or decoding afresh."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SPY='work/candidates/spy-action-contracts-1375/report.json'
CURRY='work/candidates/curry-favors-contract-1375/report.json'
FIELDS='work/reports/native-action-fields-1375.json'
V10='work/reports/native-pair-extension-v10-1375.json'
V11='work/reports/native-pair-extension-v11-1375.json'
INV='work/reports/native-diplomacy-1.37.5.json'
REJECTED={'0x360169':'missing REX prefix; correct entry36015e retained separately','0x35f311':'middle of instruction; correct entry35f2ef retained separately'}
def load(p):
 with p.open('rb') as f:b=f.read(8*1024*1024+1)
 if len(b)>8*1024*1024:raise ValueError('JSON bound')
 return json.loads(b)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def render():
 pins=load(HERE/'input-pins.json')
 for p,s in pins.items():assert digest(ROOT/p)==s,p
 pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
 funcs={};ledger=[];new=0
 for n in ('01','02','03'):
  p=HERE/('exploration-'+n+'.json');d=load(p);assert d['game_sha256']==SHA and d['window']==8192
  for k,f in d['functions'].items():
   new+=f['decoded_bytes'];assert f['decoded_bytes']<=8192
   ledger.append({'entry':k,'source':p.name,'decoded_bytes':f['decoded_bytes'],'adopted':k not in REJECTED,'rejection':REJECTED.get(k)})
   if k not in REJECTED:
    assert k not in funcs;funcs[k]={**f,'source':str(p.relative_to(ROOT)).replace('\\','/'),'source_pointer':'/functions/'+k}
 assert new==13086 and new<=49152
 sources={p:load(ROOT/p) for p in (SPY,CURRY,FIELDS,V10,V11,INV)};imported={}
 for source,section,keys in [(FIELDS,'functions',['0x7c6790','0x7c67d0']),
  (SPY,'functions',['0x4e9930','0x4e8630','0x4e7c50','0x4ea820','0x4e99d0','0x4ebdb0','0x8f440','0x8f450']),
  (SPY,'imported_functions',['0x4e9d00','0x129b60']),
  (CURRY,'functions',['0x4e7470']),(V10,'functions',['0x129500']),(V11,'functions',['0xa658d0'])]:
  for key in keys:imported[key]={**sources[source][section][key],'source':source,'source_pointer':'/'+section+'/'+key}
 known={};verified=0;strings={}
 for f in [*funcs.values(),*imported.values()]:
  for row in f['instructions']:
   raw=bytes.fromhex(row['bytes']);assert pe.bytes_at(int(row['rva'],16),len(raw))==raw,row
   known[row['rva']]=row;verified+=len(raw)
   if 'ascii' in row:
    text=row['ascii'];encoded=text.encode('ascii',errors='strict')+b'\0'
    assert pe.bytes_at(int(row['rip_target'],16),len(encoded))==encoded
    strings[row['rip_target']]={'bytes':encoded.hex(),'text':text}
 facts=load(HERE/'facts.json')
 for fact in facts.values():
  for r in fact.get('anchors',[]):assert r in known,r
 families=[];data=[]
 for name in ('break_alliance_favor','break_alliance'):
  a=next(a for a in sources[INV]['native_actions']['actions'] if a['name']==name);vt=int(a['vtable_rva'],16)
  slots={**a['slots'],'0x130':'0x7c79f0','0x138':'0x8f450' if name=='break_alliance_favor' else '0x8f440'}
  for slot,target in slots.items():
   addr=vt+int(slot,16);raw=pe.bytes_at(addr,8);assert struct.unpack('<Q',raw)[0]==pe.base+int(target,16)
   data.append({'family':name,'slot':slot,'rva':hex(addr),'bytes':raw.hex(),'target':target})
  families.append({'name':name,'token':a['token_id'],'vtable_rva':a['vtable_rva'],'slots':slots})
 stock='work/runtime/unpacked-1.37.5/base/common/defines.lua'
 lines=(ROOT/stock).read_text(encoding='utf-8-sig').splitlines()
 selected=[{'line':i+1,'text':line} for i,line in enumerate(lines) if any(k in line for k in ('BREAK_ALLIANCE_NON_GREAT_POWER_FAVOR_COST','BREAK_ALLIANCE_REQUIRED_OPINION','BREAK_ALLIANCE_ACTION_COOLDOWN','FORCE_BREAK_ALLIANCE_TRUCE_YEARS'))]
 return {'schema':1,'purpose':'favor_break_alliance_static_contract','game_sha256':SHA,'inputs':pins,'families':families,'functions':funcs,'imported_functions':imported,'data_pins':data,'string_pins':strings,'facts':facts,'stock_defines':{'source':stock,'selected_lines':selected,'runtime_global_registration_not_traced':True},
  'limits':{'per_CFG_bytes':8192,'max_new_bytes':49152,'new_bytes_all_exploration':new,'rejected_bytes':253,'ledger':ledger,'verified_instruction_anchors':len(known),'verified_instruction_bytes_including_imports':verified,'vt_slots':len(data),'byte_pattern_search':{'range_start':'0x35d210','range_end':'0x360459','decoded_bytes':0,'result':'Neither token occurs as a literal DWORD in this bounded factory span; do not infer dispatch.'}},
  'unsupported':['Human GUI button visibility/DLC predicate','Factory token-dispatch arithmetic proof beyond existing name/token and ctor call','Raw current full-generation resolution and stable world lifetime','All transitive script/TLS/lazy-cache mutations','Full effect graph and AI eventual response observation','Native execution/submit/SEH cleanup experiment'],
  'raw_observer_implemented':False,'native_adapter_implemented':False,'runtime_verified':False,'execution_verified':False,'effect_verified':False,'production_ready':False,'process_accessed':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 b=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();out=HERE/'report.json'
 if a.check:assert out.read_bytes()==b
 else:
  with out.open('xb') as f:f.write(b)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'committed_bytes':check_memory_budget(),'process_accessed':False}))
if __name__=='__main__':main()
