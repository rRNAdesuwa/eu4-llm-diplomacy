"""Recheck v10 extension pin bytes and mapping against exact disk PE. No disassembly or process I/O."""
from pathlib import Path
import hashlib,json,re,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE

def main():
    game=ROOT.parent/'eu4.exe'
    with game.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a':raise ValueError('Wrong disk executable')
    pe=PE(game);checked=0;vt_checked=0
    for leaf in ('pair-engine-1375.cpp','pair-probe-v6-1375.cpp','pair-preview-v6-1375.cpp','pair-command-v6-1375.cpp'):
        s=(ROOT/'work/native/v10'/leaf).read_text(encoding='utf-8')
        pins=re.findall(r'extension_prefix\(base \+ (0x[0-9a-f]+), "([0-9a-f]+)"\)',s)
        if len(pins)!=18:raise ValueError('Missing extension pins')
        for rva,raw in pins:
            value=bytes.fromhex(raw)
            if pe.bytes_at(int(rva,16),len(value))!=value:raise ValueError(f'{leaf} pin {rva} differs')
            checked+=1
        for vt,slot,fn in re.findall(r'read_at<std::uintptr_t>\(base \+ (0x[0-9a-f]+) \+ (0x[0-9a-f]+)\) != base \+ (0x[0-9a-f]+)',s):
            if int.from_bytes(pe.bytes_at(int(vt,16)+int(slot,16),8),'little')!=pe.base+int(fn,16):raise ValueError('Wrong virtual slot')
            vt_checked+=1
    result={'executable_sha256':digest,'function_prefixes_checked':checked,'virtual_slots_checked':vt_checked,
            'process_accessed':False,'native_calls':False,'runtime_verified':False}
    print(json.dumps(result))
    (HERE/'pin-verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
