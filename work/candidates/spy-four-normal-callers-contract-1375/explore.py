"""Bounded disk-only targeted exploration; no recursive calls or process access."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
from trace_change_subject_type import rows
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--round',type=int,choices=[1,2],default=1)
    round_number=parser.parse_args().round
    entries={1:[0x13ade0,0x13a1f0],2:[0x57ed60,0x580730]}[round_number]
    pe=PE(ROOT.parent/'eu4.exe')
    assert hashlib.sha256(pe.data).hexdigest()==SHA
    md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    out={};total=0
    for entry in entries:
        ins,edges=bounded_cfg(pe,md,entry,window=8192,max_instructions=2500)
        n=sum(i.size for i in ins);total+=n
        assert total<=65536
        out[hex(entry)]={'instructions':rows(pe,ins),'edges':edges,'decoded_bytes':n}
    origin={1:'Saved spy report13b810 calls13ade0@13c360 and13a1f0@13c3d4',
            2:'Saved spy report13b810 calls57ed60@13c26e and580730@13c341 before129b60'}[round_number]
    existing=sum(json.loads(p.read_bytes())['decoded_bytes'] for p in HERE.glob('exploration-*.json'))
    assert total+existing<=65536
    data=(json.dumps({'schema':1,'game_sha256':SHA,'entry_source':origin,
           'functions':out,'window_per_cfg':8192,'decoded_bytes':total,
           'memory_committed_bytes':check_memory_budget()},indent=2)+'\n').encode()
    with (HERE/f'exploration-{round_number:02d}.json').open('xb') as f:f.write(data)
    print(json.dumps({'entries':entries,'decoded_bytes':total,'sha256':hashlib.sha256(data).hexdigest()}))
if __name__=='__main__':main()
