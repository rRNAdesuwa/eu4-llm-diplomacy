"""Bounded disk-only checks of actual source pin literals. Never execute native code."""
import hashlib,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE
GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'

def game():
    pe=PE(ROOT.parent/'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest()!=GAME_SHA:raise ValueError('Exact game SHA differs')
    return pe

def code_pins(source):
    if len(source)>128*1024:raise ValueError('Source budget exceeded')
    block=source.split('constexpr Pin kPins[] = {',1)[1].split('\n};',1)[0]
    result=[]
    for name,strings in re.findall(r'\{(kCallback|kDestructor|0x[0-9a-f]+),\s*((?:"[0-9a-f]+"\s*)+)\}',block):
        rva={'kCallback':0xe50180,'kDestructor':0x95660}.get(name)
        if rva is None:rva=int(name,16)
        data=bytes.fromhex(''.join(re.findall(r'"([0-9a-f]+)"',strings)))
        if not 0<len(data)<=1024:raise ValueError('Code pin budget')
        result.append((name,rva,data))
    if [x[1] for x in result]!=[0xe50180,0x95660,0x172b120,0x1721674,0x172175c,0x1721938,0x5349af,0x6e9149]:raise ValueError('Exact 8 pin identities required')
    if [len(x[2]) for x in result]!=[648,94,21,17,20,30,108,7]:raise ValueError('Exact full pin lengths required')
    return result

def check(source,pe=None,require_match=True):
    pe=game() if pe is None else pe
    rows=[]
    for name,rva,wanted in code_pins(source):
        actual=pe.bytes_at(rva,len(wanted))
        changes=[{'offset':i,'rva':hex(rva+i),'source':a,'game':b} for i,(a,b) in enumerate(zip(wanted,actual)) if a!=b]
        rows.append({'name':name,'rva':hex(rva),'bytes':len(wanted),'matches':not changes,'differences':changes,'game_sha256':hashlib.sha256(actual).hexdigest()})
    # image() itself must be the exact inherited guard. Source normalization is
    # checked by prepare/seal; these values cover all its remaining data pins.
    data=[]
    for row in (0x1fcb3a0,0x1fccde0):
        for offset,wanted in ((8,0x1d34aec),(0x30,0x1d34af8),(0x38,0xe50180)):
            actual=struct.unpack('<Q',pe.bytes_at(row+offset,8))[0]-pe.base
            data.append({'rva':hex(row+offset),'type':'relocated pointer target RVA','matches':actual==wanted,'expected':hex(wanted),'actual':hex(actual)})
    for rva,wanted in ((0x1d34aec,b'yesman\0'),(0x1d34af8,b'Toggles AI positive responses\0'),(0x1dc1c90,struct.pack('<Q',0)),(0x1dc1c98,struct.pack('<Q',15)),(0x1d2b970,b'ENABLED\0'),(0x1d2b978,b'DISABLED\0'),(0x1d2bc30,b'AI positive response is now ')):
        actual=pe.bytes_at(rva,len(wanted));data.append({'rva':hex(rva),'type':'exact bytes','matches':actual==wanted,'expected':wanted.hex(),'actual':actual.hex()})
    pos=struct.unpack_from('<I',pe.data,0x3c)[0];opt=pos+24
    headers={'dos':pe.data[:2]==b'MZ','nt':pe.data[pos:pos+4]==b'PE\0\0','machine':struct.unpack_from('<H',pe.data,pos+4)[0]==0x8664,'timestamp':struct.unpack_from('<I',pe.data,pos+8)[0]==0x66fe6ab9,'magic':struct.unpack_from('<H',pe.data,opt)[0]==0x20b,'size_image':struct.unpack_from('<I',pe.data,opt+56)[0]==0x25e0000}
    okay=all(x['matches'] for x in rows+data) and all(headers.values())
    if require_match and not okay:raise ValueError('Source literal/data/header pins differ from exact executable')
    return {'game_sha256':GAME_SHA,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'code_pins':rows,'code_pin_count':len(rows),'code_bytes':sum(x['bytes'] for x in rows),'data_checks':data,'header_checks':headers,'all_match':okay,'process_accessed':False,'native_called':False}
