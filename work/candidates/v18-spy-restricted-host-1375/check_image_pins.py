"""Finite disk PE check, no process or full disassembly. CREATE_NEW report."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import prepare


def verify():
    exe=prepare.ROOT.parent/'eu4.exe'
    digest=hashlib.sha256();size=0
    with exe.open('rb') as stream:
        while chunk:=stream.read(65536):
            size+=len(chunk)
            if size>268435456:raise ValueError('Executable byte budget')
            digest.update(chunk)
        if digest.hexdigest()!='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a':raise ValueError('Executable differs')
        def read(offset,count):
            if offset<0 or count>4096 or offset+count>size:raise ValueError('Bounded PE range')
            stream.seek(offset);raw=stream.read(count)
            if len(raw)!=count:raise ValueError('Short PE range')
            return raw
        dos=read(0,64);pe=struct.unpack_from('<I',dos,0x3c)[0]
        if dos[:2]!=b'MZ' or not 1<=pe<=4096:raise ValueError('DOS header')
        nt=read(pe,264);machine,count,timestamp=struct.unpack_from('<HHI',nt,4)
        opt=struct.unpack_from('<H',nt,20)[0]
        if nt[:4]!=b'PE\0\0' or machine!=0x8664 or timestamp!=0x66fe6ab9 or not 1<=count<=32 or opt!=240:raise ValueError('PE header')
        if struct.unpack_from('<H',nt,24)[0]!=0x20b or struct.unpack_from('<I',nt,80)[0]!=0x25e0000:raise ValueError('PE64 size')
        sections=read(pe+24+opt,count*40)
        def rva_read(rva,n):
            for i in range(count):
                virtual,va,rawsize,offset=struct.unpack_from('<IIII',sections,i*40+8)
                if va<=rva and rva-va+n<=rawsize:return read(offset+rva-va,n)
            raise ValueError('RVA not raw-backed')
        text=prepare.bounded(prepare.ROOT/'work/candidates/v18-spy-no-send-core-1375/pins.h',16384).decode('ascii')
        codes=re.findall(r'\{(0x[0-9a-f]+), "([0-9a-f]+)"\}',text)
        slots=re.findall(r'\{(0x[0-9a-f]+), (0x[0-9a-f]+)\}',text)
        if len(codes)!=21 or len(slots)!=52:raise ValueError('Exact sealed pin counts')
        checked=[]
        for rva,hexd in codes:
            actual=rva_read(int(rva,16),len(hexd)//2)
            if actual.hex()!=hexd:raise ValueError('Code differs '+rva)
            checked.append(dict(rva=rva,kind='code',bytes=len(actual),hex=hexd))
        preferred=struct.unpack_from('<Q',nt,48)[0]
        for rva,target in slots+[(hex(0x1cb84e0),hex(0x811aa0)),(hex(0x1cb8560),hex(0x8024d0)),(hex(0x1cb8778),hex(0x80ff80))]:
            actual=rva_read(int(rva,16),8)
            if struct.unpack('<Q',actual)[0]!=preferred+int(target,16):raise ValueError('Slot differs '+rva)
            checked.append(dict(rva=rva,kind='slot',bytes=8,target=target))
    return dict(game_sha256=digest.hexdigest(),file_bytes=size,checked=checked,selected_bytes=sum(x['bytes'] for x in checked),
                new_disassembly_bytes=0,process_access=False,native_calls=False,production_ready=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=verify()
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='checked'},sort_keys=True))
