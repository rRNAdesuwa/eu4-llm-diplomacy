"""Bounded disk-only consumer evidence; never resolves or calls native code."""
import argparse,hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,make_disassembler,check_memory_budget
from map_diplomacy_fields import bounded_cfg
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
def generate():
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    md,cs=make_disassembler(Path(os.environ['TEMP'])/'eu4-native-analysis-deps')
    rows,edges=bounded_cfg(pe,md,0x14ca870,window=8192,max_instructions=2500)
    count=sum(x.size for x in rows);assert count<=8192
    ins=[]
    for i in rows:
        item=dict(rva=hex(i.address),bytes=i.bytes.hex(),instruction=(i.mnemonic+' '+i.op_str).strip())
        for op in i.operands:
            if op.type==cs.CS_OP_MEM and op.mem.base==cs.x86_const.X86_REG_RIP:
                item['rip_target']=hex(i.address+i.size+op.mem.disp)
        ins.append(item)
    check_memory_budget()
    return dict(schema=1,game_sha256=SHA,new_decoded_bytes=count,new_decode_limit=49152,
        all_exploration_recorded=True,per_function_window=8192,recursive_decode=False,
        functions={'0x14ca870':dict(instructions=ins,edges=edges,decoded_bytes=count)},
        process_accessed=False,runtime_verified=False)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
    raw=(json.dumps(generate(),sort_keys=True,indent=2)+'\n').encode();path=HERE/'exploration-01.json'
    if a.check: assert path.read_bytes()==raw
    else:
        with path.open('xb') as f:f.write(raw)
    print(json.dumps(dict(passed=True,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))
