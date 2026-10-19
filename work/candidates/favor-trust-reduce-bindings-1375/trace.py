"""Replay retained slices and predecessor anchors against exact disk PE. No new decode."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PRE='work/candidates/favor-exchanges-contract-1375/report.json'
IMPORTS={
 'functions':['0x360024','0x3601f3','0x36044d','0x133ea0','0x557080','0x5575b0','0x556820','0x556ce0','0x4fe740','0x4fe2a0'],
 'imported_functions':['0x4e9930','0x4e8630','0x129500','0x4e7470','0x4fe7e0','0x7c6790']}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p,maximum=8*1024*1024):
 with p.open('rb') as f:b=f.read(maximum+1)
 if len(b)>maximum:raise ValueError('bounded input')
 return json.loads(b)
def render():
 pins=load(HERE/'input-pins.json')
 for p,h in pins.items():assert digest(ROOT/p)==h,p
 pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
 old=load(ROOT/PRE);functions={};explorations=[];count=0;bytecount=0
 def verify(name,rows,source,pointer):
  nonlocal count,bytecount
  for r in rows:
   b=bytes.fromhex(r['bytes']);a=int(r['rva'],16)
   assert pe.bytes_at(a,len(b))==b,(name,r)
   count+=1;bytecount+=len(b)
  functions[name]={'source':source,'source_pointer':pointer,'instructions':rows}
 for field,entries in IMPORTS.items():
  for key in entries:verify('import:'+key,old[field][key]['instructions'],PRE,'/'+field+'/'+key)
 for path in sorted(HERE.glob('exploration-*.json')):
  j=load(path);assert j['game_sha256']==SHA
  assert all(f['decoded_bytes']<=8192 for f in j['functions'].values())
  rejected=path.name in ('exploration-01.json','exploration-05.json')
  explorations.append({'source':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':digest(path),
   'decoded_bytes':j['new_this_file'],'adopted':not rejected,
   'limitation':'incorrect VA labels / mid-instruction entry, retained but never evidence' if path.name=='exploration-01.json' else
    'token byte patterns were relative-displacement false positives; retained exploration only' if rejected else
    'bounded CFG/slice; not a whole-program closure; off-path tooltip/UI/Lua branches retained',
   'committed_bytes':j['committed_bytes']})
  for key,f in j['functions'].items():
   if path.name=='exploration-01.json':
    for r in f['instructions']:
     b=bytes.fromhex(r['bytes']);assert pe.bytes_at(int(r['rva'],16)-pe.base,len(b))==b
   else:verify(path.name+':'+key,f['instructions'],str(path.relative_to(ROOT)).replace('\\','/'),'/functions/'+key)
 assert sum(x['decoded_bytes'] for x in explorations)<=131072
 facts=load(HERE/'facts.json');index={r['rva'] for f in functions.values() for r in f['instructions']}
 for name,f in facts.items():
  for a in f['anchors']:assert a in index,(name,a)
 slots=[]
 for vt,values in [(0x1d55670,{0:0x1082af0,0x18:0x1082fd0,0x50:0xedfa40}),
                   (0x1d3b390,{0x50:0xeebc10}),
                   (0x1c7e828,{0:0x129500,0x40:0x4e9930,0x80:0x556820,0x88:0x556ce0,0xb0:0x557080}),
                   (0x1c80c60,{0:0x129500,0x40:0x4e9930,0x88:0x4fe2a0,0xb0:0x4fe740})]:
  for off,target in values.items():
   raw=pe.bytes_at(vt+off,8);assert struct.unpack('<Q',raw)[0]==pe.base+target
   slots.append({'rva':hex(vt+off),'target':hex(target),'bytes':raw.hex()})
 strings=[]
 for rva,s in [(0x1c66d58,'common/defines.lua'),(0x1c66d70,'common/defines'),(0x1c66e90,'NDefines'),
               (0x1c672d8,'NDiplomacy'),(0x1c67460,'INCREASE_TRUST_COST'),(0x1c67410,'INCREASE_TRUST_AMOUNT'),
               (0x1d3d438,'TradeFavorsForTrustDialog'),(0x1d55420,'ProvDialog'),(0x1c659a8,'AgreeButton')]:
  raw=s.encode()+b'\0';assert pe.bytes_at(rva,len(raw))==raw;strings.append({'rva':hex(rva),'ascii':s,'bytes':raw.hex()})
 stock=ROOT/'work/runtime/unpacked-1.37.5/base/common/defines.lua'
 with stock.open('r',encoding='utf-8-sig') as f:
  stockrows=[{'line':i,'text':line.strip()} for i,line in enumerate(f,1) if 'INCREASE_TRUST_' in line]
 return {'schema':1,'purpose':'favor_trust_reduce_private_binding_static','game_sha256':SHA,'inputs':pins,
  'functions':functions,'facts':facts,'slot_pins':slots,'string_pins':strings,'stock_define_context':stockrows,
  'explorations':explorations,'limits':{'new_decoded_bytes':sum(x['decoded_bytes'] for x in explorations),
   'new_limit':131072,'per_range_limit':8192,'all_failed_exploration_retained':True,
   'verified_instruction_anchors':count,'verified_instruction_bytes_with_overlap':bytecount,
   'failed_VA_351_bytes_excluded_from_evidence':True,'trace_new_decode_bytes':0,
   'max_recorded_commit':max(x['committed_bytes'] for x in explorations)},
  'closures':{'trust_original_define_keys':True,'trust_runtime_values_known':False,
    'reduce_normal_gui_third_country_to_qword40':True,'reduce_GUI_generic80_is_full88':False,
    'normal_human_wrapper_to_context_submit':True,'actual_private_RO_capture':False},
  'unsupported':['live module/PE/SHA/held-process wrapper is not implemented here',
   'loaded config cannot be inferred from stock10/5; override/difficulty precedence not fully traversed',
   'full country graph/lifetime/ABA/SP/world epoch safety not established by two matching reads',
   'GUI helper557650 and transitive scripted/lazy/TLS side effects are not licensed as RO',
   'no arbitrary paired favor/trust GUI quantity API; native legal preview still required',
   'no new native sender, execution permission, cancel semantics or accepted-effect claim'],
  'runtime_verified':False,'native_adapter_implemented':False,'production_ready':False,'process_accessed':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 j=render();b=(json.dumps(j,ensure_ascii=False,indent=2)+'\n').encode();path=HERE/'report.json'
 if a.check:assert path.read_bytes()==b
 else:
  with path.open('xb') as f:f.write(b)
 print(json.dumps({'check':a.check,'report_sha256':hashlib.sha256(b).hexdigest(),'limits':j['limits'],'current_commit':check_memory_budget()}))
if __name__=='__main__':main()
