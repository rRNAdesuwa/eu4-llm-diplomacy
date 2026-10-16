"""One disk executable-section byte pass for four exact rel32 targets; no disassembly."""
import hashlib,json,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE,check_memory_budget
from map_diplomacy_fields import SHA
def generate():
    p=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(p.data).hexdigest()==SHA
    targets={0xaf3860,0xaf3e70,0xaf3e20,0xaf37c0};hits=[];scanned=0
    for s in p.sections:
        if not s['flags']&0x20000000:continue
        start=s['raw'];end=start+s['size'];scanned+=s['size'];at=start
        while True:
            at=p.data.find(b'\xe8',at,end-4)
            if at<0:break
            r=s['rva']+at-start;dst=r+5+struct.unpack_from('<i',p.data,at+1)[0]
            if dst in targets:
                f=p.function(r)
                hits.append({'candidate_rva':hex(r),'target':hex(dst),'bytes':p.data[at:at+5].hex(),
                  'pdata':None if f is None else [hex(x) for x in f],
                  'instruction_alignment_verified':False})
                assert len(hits)<=128
            at+=1
        check_memory_budget()
    return {'binary_sha256':SHA,'raw_candidates_only':True,'scanned_disk_bytes':scanned,
     'decoded_bytes':0,'targets':[hex(x) for x in sorted(targets)],'candidates':hits}
if __name__=='__main__':
    raw=(json.dumps(generate(),sort_keys=True,indent=2)+'\n').encode();p=HERE/'call-candidates.json'
    if '--check' in sys.argv:assert p.read_bytes()==raw
    else:p.write_bytes(raw)
    print(raw.decode())
