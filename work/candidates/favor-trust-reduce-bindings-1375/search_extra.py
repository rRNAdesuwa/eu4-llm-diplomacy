from pathlib import Path
import hashlib,json,re,sys,struct
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
patterns={'reduce_token':bytes.fromhex('cd3b0000'),'trust_token':bytes.fromhex('d33b0000')};out={}
for name,needle in patterns.items():
 hits=[]
 for s in pe.sections:
  if s['name']!='.text':continue
  pos=s['raw'];end=pos+s['size']
  while True:
   pos=pe.data.find(needle,pos,end)
   if pos<0:break
   rva=pe.to_rva(pos);f=pe.function(rva);hits.append({'rva':hex(rva),'function':[hex(n) for n in f] if f else None});pos+=1
 out[name]=hits
strings=[]
for s in pe.sections:
 if s['name'] not in ('.rdata','.data'):continue
 for m in re.finditer(rb'[ -~]{5,180}\x00',pe.data[s['raw']:s['raw']+s['size']]):
  value=m.group()[:-1].decode()
  if any(t in value.lower() for t in ('reduce_opinion','reducerelation','reducetrust','reducemodifier','increasetrust','trustdialog','favoraction','favor_action','reduceopinion')):
   strings.append({'rva':hex(pe.to_rva(s['raw']+m.start())),'text':value})
result={'byte_candidates_not_instruction_proof':out,'selected_strings':strings,'new_decode_bytes':0,'committed_bytes':check_memory_budget()}
with (HERE/'search-02.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
