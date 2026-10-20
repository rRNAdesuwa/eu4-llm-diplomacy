"""One bounded disk-only exploration, no process access or recursive decode."""
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
for entry in (0x8f58f0,0xb354c0,0x3b9fa0,0x3ba040):
    ins,edges=bounded_cfg(pe,md,entry,window=0x2000,max_instructions=2000)
    total+=sum(i.size for i in ins);assert total<=16384
    functions[hex(entry)]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':sum(i.size for i in ins)}
out=dict(functions=functions,decoded_bytes=total,max_decoded_bytes=16384,peak_bytes=check_memory_budget(),process_accessed=False)
with (HERE/'exploration.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({'functions':{k:v['decoded_bytes'] for k,v in functions.items()},'total':total,'peak_bytes':out['peak_bytes']}))
