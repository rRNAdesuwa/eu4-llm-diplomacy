"""Fixed v18 no-send candidate manifest. Pure file parsing; never loads a DLL."""
from pathlib import Path
import hashlib
import json
import struct

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PURPOSE="restricted_spy_no_send_lab_1375_v18"
GAME_SHA="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
DLL="eu4_spy_no_send_lab_1375_v18.dll"
LOCAL_SOURCES=("bootstrap.cpp","bootstrap_codec.h","scheduler.h","installer.h","installer.cpp","thread_freeze.inc","frame.asm","build.cmd",
               "build_manifest.py","wire.py","loader.py","client.py","real_capture.py","native_trace.py","native_projection.py")
MAX_FILE=2*1024*1024


def require(ok,message):
    if not ok:raise ValueError(message)


def bounded(path,limit):
    with Path(path).open('rb') as stream:data=stream.read(limit+1)
    require(len(data)<=limit,'Hard read budget')
    return data


def sha(data):return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def exact(left,right):return canonical(left)==canonical(right)


def no_links(path):
    path=Path(path).absolute()
    for node in (path,*path.parents):
        if node.exists():require(not node.is_symlink() and not (getattr(node.stat(),'st_file_attributes',0)&0x400),'Reparse/symlink path')
    return path


def json_value(raw):
    def pairs(values):
        out={}
        for key,value in values:require(key not in out,'Duplicate JSON key');out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite')))


def sources():
    pins=json_value(bounded(HERE/'predecessor-pins.json',128*1024))
    require(type(pins)is dict and len(pins)<=96,'Source pin inventory budget')
    paths={name for name in pins}|{(HERE/name).relative_to(ROOT).as_posix() for name in LOCAL_SOURCES}
    result={};total=0
    for name in sorted(paths):
        path=no_links(ROOT/name).resolve();require(path.is_relative_to(ROOT),'Escaped source path')
        raw=bounded(path,MAX_FILE);total+=len(raw);require(total<=16*1024*1024,'Source total budget')
        descriptor={'bytes':len(raw),'sha256':sha(raw)}
        if name in pins:require(exact(descriptor,pins[name]),f'Predecessor source changed: {name}')
        result[name]=descriptor
    return result


def pe_identity(raw):
    require(512<=len(raw)<=16*1024*1024 and raw[:2]==b'MZ','DLL DOS header')
    def u16(at):require(0<=at<=len(raw)-2,'PE bounds');return struct.unpack_from('<H',raw,at)[0]
    def u32(at):require(0<=at<=len(raw)-4,'PE bounds');return struct.unpack_from('<I',raw,at)[0]
    nt=u32(0x3c);require(64<=nt<=4096 and raw[nt:nt+4]==b'PE\0\0' and u16(nt+4)==0x8664,'DLL PE64')
    count=u16(nt+6);size=u16(nt+20);opt=nt+24
    require(1<=count<=32 and 240<=size<=512 and u16(opt)==0x20b,'DLL optional header')
    sections=[]
    for i in range(count):
        at=opt+size+i*40;require(at+40<=len(raw),'DLL section bounds')
        sections.append((u32(at+12),u32(at+16),u32(at+20)))
    def offset(rva,length):
        if rva<u32(opt+60):require(rva+length<=len(raw),'Header RVA');return rva
        for start,n,at in sections:
            if start<=rva and rva+length<=start+n and at+rva-start+length<=len(raw):return at+rva-start
        raise ValueError('Unbacked PE RVA')
    export=u32(opt+112);length=u32(opt+116);require(export and 40<=length<=65536,'Export directory')
    at=offset(export,40);nfunc=u32(at+20);nnames=u32(at+24)
    require(nfunc==nnames==1,'Only BridgeStart export is permitted')
    names=offset(u32(at+32),4);name=offset(u32(names),12)
    require(raw[name:name+12]==b'BridgeStart\0','Fixed BridgeStart export')
    ordinal=u16(offset(u32(at+36),2));require(ordinal==0,'Fixed export ordinal')
    rva=u32(offset(u32(at+28),4));require(not export<=rva<export+length,'Forwarded export forbidden')
    offset(rva,1)
    return {'machine':0x8664,'timestamp':u32(nt+8),'size_of_image':u32(opt+56),'bridge_start_rva':rva}


def make_manifest(directory):
    directory=no_links(directory).resolve();require(directory.is_relative_to(HERE) and directory!=HERE,'Private candidate build directory')
    data=bounded(directory/DLL,16*1024*1024)
    return {'schema':'EU4SPYBUILD/1','purpose':PURPOSE,'game_sha256':GAME_SHA,'dll_name':DLL,
            'dll_bytes':len(data),'dll_sha256':sha(data),'pe':pe_identity(data),'sources':sources(),
            'wire_protocol':'EU4SPYLAB/1','bootstrap_protocol':'EU4SPYBOOT/1','raw_protocol':'EU4SPYHOST/1',
            'outer_protocol':'EU4SPYBOOTSTRAP/1','profile':'spy5_true_state0_v1','stages':['lifecycle','family_preview','owned_command'],
            'actor':'FRA','target':'ENG','send_supported':False,'production_ready':False,
            'strict_single_player_verified':False,'world_epoch_verified':False,'runtime_verified':False,
            'automatic_stage':False,'hot_unload_supported':False}


def verify_build(directory):
    raw=bounded(Path(directory)/'build.json',1024*1024)
    manifest=json_value(raw)
    require(exact(manifest,make_manifest(directory)),'Exact no-send manifest/source/DLL identity mismatch')
    return manifest,sha(raw)


def write_manifest(directory):
    value=make_manifest(directory)
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode('ascii')
    with (Path(directory)/'build.json').open('xb') as stream:stream.write(raw)
    return value,sha(raw)
