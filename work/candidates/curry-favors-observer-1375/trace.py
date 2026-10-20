"""Reuse sealed evidence and reproduce one30B vector-push closure."""
import argparse,hashlib,json,struct,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget,make_disassembler
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
def raw(p):
 with p.open('rb') as f:b=f.read(8*1024*1024+1)
 if len(b)>8*1024*1024:raise ValueError('input limit')
 return b
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def render():
 paths=['work/candidates/curry-favors-contract-1375/report.json','work/candidates/curry-favors-contract-1375/contract.json',
 'work/candidates/curry-favors-contract-1375/review.json','work/review-results/curry-favors-native-inventory-20261008a/review.json',
 'work/reports/native-test-fixture-1375.json','work/candidates/spy-modifier-observer-1375/observer.py',
 'work/candidates/spy-modifier-observer-1375/input-pins.json']
 paths+=list(json.loads(raw(ROOT/paths[-1])))
 sources={p:digest(ROOT/p) for p in sorted(set(paths))}
 s=json.loads(raw(ROOT/paths[0]));fixture=json.loads(raw(ROOT/'work/reports/native-test-fixture-1375.json'))
 pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
 functions={}
 for k in ['0x6fec50','0x6fec80','0x6ff4e0','0x6ff110']:
  functions[k]={'source':'work/reports/native-test-fixture-1375.json',**fixture['functions'][k]}
 for k in ['0x257a40','0x6ff570','0x4e7550','0x4ea820']:
  functions[k]=s['imported_functions'][k]
 for k in ['0x5ace50','0x5ad74d','0xa69bf0','0xa69af0']:
  if k in s['functions']:functions[k]={'source':paths[0],**s['functions'][k]}
 country=[x for x in fixture['functions']['0x2c9960']['instructions'] if 0x2cb745<=int(x['rva'],16)<0x2cb81d]
 functions['country_manager_vector_slice']={'source':'work/reports/native-test-fixture-1375.json','instructions':country}
 cache=json.loads(raw(HERE/'decode-01.json'));md,version=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
 ins,edges=bounded_cfg(pe,md,0xc9f10,window=8192,max_instructions=2000)
 decoded=rows(pe,ins);assert decoded==cache['functions']['0xc9f10']['instructions'] and edges==cache['functions']['0xc9f10']['edges']
 new_bytes=sum(x.size for x in ins);assert new_bytes==30<=24576
 functions['0xc9f10']={'source':'decode-01.json','instructions':decoded,'edges':edges,'decoded_bytes':new_bytes}
 instructions={}
 for f in functions.values():
  for row in f['instructions']:
   b=bytes.fromhex(row['bytes']);assert pe.bytes_at(int(row['rva'],16),len(b))==b
   instructions[row['rva']]=row
 # The LEA at6ff4ef ends6ff4f6 and names the entry's concrete vtable.
 assert pe.bytes_at(0x6ff4ef,7).hex()=='488d05facd5a01'
 assert 0x6ff4f6+struct.unpack('<i',pe.bytes_at(0x6ff4ef+3,4))[0]==0x1cac2f0
 selected=[0x6fec50,0x6fec57,0x6fec63,0x6fec67,0x6fec6a,0x6fec6e,0x6fed0d,0x6fed2e,0x6fedb9,0x6fedbc,0x6fedc6,0x6fedde,
 0x6ff4ef,0x6ff4f6,0x6ff4fd,0x6ff508,0x6ff510,0x6ff54e,0x6ff55a,0x6ff1ec,0x6ff1f7,
 0x257a42,0x257a58,0x257a9b,0x257afb,0x2cb757,0x2cb75d,0x2cb762,0x2cb818,0xc9f13,0xc9f17,0xc9f23]
 pins=[instructions[hex(x)] for x in selected]
 tables=[]
 for name,vt in [('entry',0x1cac2f0),('manager',0x1cac380),('mission',0x1c4b2b8),('relation',0x1c7b178)]:
  tables.append({'kind':name,'rva':hex(vt),'bytes':pe.bytes_at(vt,8).hex()})
 return {'schema_version':1,'purpose':'curry_favors_raw_ro_entry_type_closure','game_sha256':SHA,'sources':sources,
  'pe':{'timestamp':0x66fe6ab9,'image_size':0x25e0000},'functions':functions,'instruction_pins':pins,'vtable_pins':tables,
  'facts':[
   {'claim':'6fec80 allocates0x48, forwards manager+14 kind into R8B and vector index intoR9D, calls6ff4e0, then inserts returned pointer into owning manager vector.', 'rvas':['0x6fed0d','0x6fed2e','0x6fedb9','0x6fedbc','0x6fedc6','0x6fedde']},
   {'claim':'entry concrete vtable1cac2f0, marker165, mission+10, statusBYTE18, kindBYTE40, IDDWORD44. Constructor writes mission/status0, kind fromR8B, ID fromR9D. Do not use mission vtable as an entry type check.','rvas':['0x6ff4ef','0x6ff4f6','0x6ff508','0x6ff510','0x6ff54e','0x6ff55a']},
   {'claim':'manager concretevtable1cac380/marker165/tokenDWORD10/kindBYTE14/unaligned fullownerQWORD16/vector20,28,30. Fixed diplomat profile is token2746,kind3,ownerFRA; entrykind must also3. Country+1480 vector gets four pointers; the saved2746 manager is appended fourth. c9f10 proves vector+8=end,+10=capacity and stride8; bound country holder1480/1488/1490 before fourth lookup.'},
   {'claim':'mission concretevtable1c4b2b8 has DIFFERENT marker182, entry48/envoyDWORD50/actor80/target88/tokena8. No getter is invoked.'},
   {'claim':'Only actor outgoing curry index158/cap160/count164 is used. Known active relation1c7b178/marker165/removed28=0 links mission30; no reciprocal incoming index is asserted.'}],
  'limits':{'new_decoded_bytes':new_bytes,'all_exploratory_decodes_counted':True,'new_decode_limit':24576,'single_cfg_limit':8192,
   'imported_unique_instruction_bytes':sum(len(bytes.fromhex(x['bytes'])) for x in instructions.values())-new_bytes,'function_or_slice_count':len(functions),'memory_hard_limit':1073741824},
  'runtime_verified':False,'native_call_authorized':False,'process_accessed':False,'production_ready':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();r=render();b=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode()
 if a.check:assert raw(HERE/'report.json')==b,'report mismatch'
 else:
  with (HERE/'report.json').open('xb') as f:f.write(b)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest(),'limits':r['limits'],'committed_bytes':check_memory_budget()}))
if __name__=='__main__':main()
