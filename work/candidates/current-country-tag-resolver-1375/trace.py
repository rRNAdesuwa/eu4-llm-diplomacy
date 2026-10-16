"""Reproduce selected existing exact-PE anchors, no new disassembly."""
from pathlib import Path
import argparse,hashlib,json,struct
import layout
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def read(path,limit):
    with Path(path).open('rb') as f:b=f.read(limit+1)
    if len(b)>limit:raise ValueError('file budget')
    return b

def digest(path):
    h=hashlib.sha256();n=0
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            n+=len(b)
            if n>256*1024*1024:raise ValueError('hash budget')
            h.update(b)
    return h.hexdigest()

class PE:
    def __init__(self,path):
        self.f=Path(path).open('rb');self.size=Path(path).stat().st_size
        head=self.at(0,4096);assert head[:2]==b'MZ';nt=struct.unpack_from('<I',head,0x3c)[0];assert 64<=nt<=2048
        assert head[nt:nt+4]==b'PE\0\0';machine,n,t,_,_,os,_=struct.unpack_from('<HHIIIHH',head,nt+4)
        assert machine==0x8664 and 0<n<32 and t==0x66fe6ab9 and struct.unpack_from('<H',head,nt+24)[0]==0x20b
        assert struct.unpack_from('<Q',head,nt+48)[0]==0x140000000 and struct.unpack_from('<I',head,nt+80)[0]==0x25e0000
        self.sections=[]
        for i in range(n):
            o=nt+24+os+40*i;name,vs,rva,rs,off=struct.unpack_from('<8sIIII',head,o);self.sections.append((rva,rs,off))
    def at(self,off,size):
        assert type(off)is int and 0<=off and 0<size<=65536 and off+size<=self.size
        self.f.seek(off);raw=self.f.read(size);assert len(raw)==size;return raw
    def offset(self,rva,size):
        found=[off+rva-start for start,n,off in self.sections if start<=rva and rva+size<=start+n]
        assert len(found)==1;return found[0]
    def rva(self,rva,size):return self.at(self.offset(rva,size),size)
    def close(self):self.f.close()

def render():
    inputs=json.loads(read(HERE/'input-pins.json',65536));sources={}
    for name,sha in inputs.items():
        assert digest(ROOT/name)==sha,name
    specs=json.loads(read(HERE/'slices.json',65536));groups=[];seen={};total=0
    for spec in specs:
        name=spec['source']
        if name not in sources:sources[name]=json.loads(read(ROOT/name,8*1024*1024))
        fn=sources[name]['functions'][spec['function']];lo=int(spec['first_rva'],16);hi=int(spec['last_rva'],16)
        rows=[z for z in fn['instructions'] if lo<=int(z['rva'],16)<=hi];assert rows and int(rows[0]['rva'],16)==lo and int(rows[-1]['rva'],16)==hi
        for row in rows:
            at=int(row['rva'],16);raw=bytes.fromhex(row['bytes'])
            if at in seen:assert seen[at]==raw
            else:seen[at]=raw;total+=len(raw)
        groups.append(dict(spec,rows=rows))
    exe=ROOT.parent/'eu4.exe';assert digest(exe)==layout.EXE_SHA256
    pe=PE(exe)
    try:
        for g in groups:
            for row in g['rows']:
                at=int(row['rva'],16);raw=bytes.fromhex(row['bytes']);assert pe.rva(at,len(raw))==raw
                row['file_offset']=pe.offset(at,len(raw))
        for at,h in layout.CODE_PINS:assert at in seen and seen[at]==bytes.fromhex(h)
        # Verify the constructor RIP target and the two referenced globals.
        rel=lambda at:at+7+struct.unpack('<i',pe.rva(at+3,4))[0]
        assert rel(0x2c9986)==layout.COUNTRY_VTABLE_RVA
        assert rel(0x28970b)==layout.DATABASE_RVA and rel(0x522ba7)==layout.GAME_RVA
        slots=[dict(rva=hex(layout.COUNTRY_VTABLE_RVA+i*8),raw=pe.rva(layout.COUNTRY_VTABLE_RVA+i*8,8).hex()) for i in range(2)]
    finally:pe.close()
    return dict(schema='EU4COUNTRYTAGSTATIC/1',exe_sha256=layout.EXE_SHA256,input_hashes=inputs,groups=groups,country_header_vtable=hex(layout.COUNTRY_VTABLE_RVA),vtable_data=slots,
      reused_instruction_count=len(seen),reused_instruction_bytes=total,new_decoded_bytes=0,new_decode_attempts=0,
      facts={'tag':'2897c0..e5 copies a bucket QWORD into stack storage and compares exactly its first three bytes to the input; selected public syntax is stricter uppercase ASCII/alphanumeric.','ordinal':'4ea87f..895 reads the country DB pointer and +118 array, shifts the complete handle by32 then sign-extends its low WORD as an8-byte index. The slot is not computed from TAG ASCII.','lookup':'749207 passes DB+110 to74e8e0;74e939 reads signed DWORD+14 count,74e9f0 loads+8 pointer and indexes*8. DB+120 capacity comes from28314a/151.','country':'2c997f..999b sets marker165, vtable1c574a0, and stores the constructor QWORD unchanged at country+20.','sentinel':'28318d..1b2 constructs the first country with exactly0x2d2d2d; loop starts1. Only slot0 exact sentinel accepted by this profile.','player':'522ba7..bea chooses alternate+1e68 only selector+1e66==7 and alternate byte+1e6f!=0; ordinaryselector0 only is supported here.','research_filters':'4096cap,16requested TAGs, uppercase/digits, highbyte nonzero, byte3/typebyte zero are conservative research filters. Highbyte is preserved as part of the full identity, not a proved monotonic lifetime counter.','known_limit':'CCountry clear/reuse can preserve addresses and handles; two equal passes do not establish epoch or exclude ABA.'},
      production_ready=False,runtime_verified=False,native_authorized=False,process_accessed=False)

def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');args=a.parse_args();out=encoded(render());path=HERE/'report.json'
    if args.check:assert read(path,512*1024)==out
    else:
        with path.open('xb') as f:f.write(out)
    print(json.dumps({'sha256':hashlib.sha256(out).hexdigest(),'bytes':len(out),'new_decode_bytes':0}))
