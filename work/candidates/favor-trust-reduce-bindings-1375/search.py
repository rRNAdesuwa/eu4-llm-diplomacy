"""Finite exact-target disk PE byte search; candidate xrefs are not instructions."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,rip_references,check_memory_budget
pe=PE(ROOT.parent/'eu4.exe');sha=hashlib.sha256(pe.data).hexdigest()
assert sha=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
names=['INCREASE_TRUST_COST','INCREASE_TRUST_AMOUNT','reduce_relations_favor','REDUCE_RELATIONS_FAVOR',
       'ReduceRelations','reduce_relations','NDiplomacy']
matches={};targets={0x233db7c,0x233db80,0x1c7e828}
for name in names:
    needle=name.encode()+b'\0';hits=[]
    for section in pe.sections:
        if section['name'] not in ('.rdata','.data'):continue
        at=section['raw'];end=at+section['size']
        while True:
            at=pe.data.find(needle,at,end)
            if at<0:break
            rva=pe.to_rva(at);hits.append(hex(rva));targets.add(rva);at+=1
    matches[name]=hits
refs=rip_references(pe,targets)
result={'game_sha256':sha,'string_matches':matches,'rip_candidates':{hex(k):v for k,v in refs.items()},
        'candidate_only_not_instruction_proof':True,'new_decode_bytes':0,'committed_bytes':check_memory_budget(),
        'scanned_sections':[{k:s[k] for k in ('name','rva','size')} for s in pe.sections if s['flags']&0x20000000]}
with (HERE/'search-01.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'strings':matches,'rip_candidate_counts':{hex(k):len(v) for k,v in refs.items()},'committed_bytes':result['committed_bytes']}))
