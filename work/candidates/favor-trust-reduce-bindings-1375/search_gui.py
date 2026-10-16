from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,rip_references,check_memory_budget
pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
names=['TradeFavorsForTrustDialog','DefaultDiplomacyDialog','vassal_select_window','vassal_selection_entry','common/defines.lua','defines.lua','NDefines']
matches={};targets=set()
for name in names:
 hits=[];needle=name.encode()+b'\0'
 for s in pe.sections:
  if s['name'] not in ('.rdata','.data'):continue
  pos=s['raw'];end=pos+s['size']
  while True:
   pos=pe.data.find(needle,pos,end)
   if pos<0:break
   rva=pe.to_rva(pos);hits.append(hex(rva));targets.add(rva);pos+=1
 matches[name]=hits
refs=rip_references(pe,targets)
result={'string_matches':matches,'rip_candidates':{hex(k):v for k,v in refs.items()},'new_decode_bytes':0,'candidate_only':True,'committed_bytes':check_memory_budget()}
with (HERE/'search-03.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
