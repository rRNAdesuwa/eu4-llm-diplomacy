"""Working bounded disk-only exploration; explicit functions, no call recursion."""
import hashlib,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows

NAMES=('corrupt_officials','sabotage_reputation','sow_discontent','slander_merchants','sabotage_recruitment')

def main():
    pe=PE(ROOT.parent/'eu4.exe')
    assert hashlib.sha256(pe.data).hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
    md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    inventory=json.loads((ROOT/'work/reports/native-diplomacy-1.37.5.json').read_text(encoding='utf-8'))
    actions={a['name']:a for a in inventory['native_actions']['actions'] if a['name'] in NAMES}
    requested=set(int(a['slots'][slot],16) for a in actions.values() for slot in ('0x48','0x80','0x88','0xb0','0xe8','0xd0','0x68'))
    requested.update((0x4f3b00,0x4f3b10,0x4e99d0,0x4ec160))
    functions={};count=0
    for entry in sorted(requested):
        ins,edges=bounded_cfg(pe,md,entry,window=0x4000,max_instructions=4000)
        n=sum(i.size for i in ins);count+=n
        assert count<=64*1024
        functions[hex(entry)]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':n}
    r={'game_sha256':hashlib.sha256(pe.data).hexdigest(),'functions':functions,'decoded_bytes':count,
       'max_decode_bytes':65536,'peak_committed_bytes':check_memory_budget(),'process_accessed':False}
    with (HERE/'exploration.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({'functions':len(functions),'decoded_bytes':count,'peak':r['peak_committed_bytes']}))

if __name__=='__main__':main()
