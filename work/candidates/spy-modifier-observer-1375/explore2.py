"""Second finite disk-only batch; at most 12 KiB decoded, no call recursion."""
import hashlib,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
pe=PE(ROOT.parent/'eu4.exe')
assert hashlib.sha256(pe.data).hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
functions={};total=0
for entry in (0x8ed850,0x93d750,0x2154c8):
    ins,edges=bounded_cfg(pe,md,entry,window=0x2000,max_instructions=2200)
    total+=sum(i.size for i in ins);assert total<=12288
    functions[hex(entry)]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':sum(i.size for i in ins)}
out=dict(functions=functions,decoded_bytes=total,max_decoded_bytes=12288,peak_bytes=check_memory_budget(),process_accessed=False)
with (HERE/'exploration2.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({'functions':{k:v['decoded_bytes'] for k,v in functions.items()},'total':total,'peak_bytes':out['peak_bytes']}))
