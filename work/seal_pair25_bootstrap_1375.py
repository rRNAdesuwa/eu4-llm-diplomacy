"""Seal the already-built new no-send DLL and exact source closure."""
import hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=ROOT/'work/candidates/v25-pair-send-bootstrap-1375';OUT=HERE/'development-attempt1';BUILD=OUT/'build'
def raw(p):
 assert p.stat().st_size<=16*1024*1024
 return p.read_bytes()
def desc(p):
 b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,d):
 with p.open('xb') as f:f.write((json.dumps(d,indent=2,sort_keys=True)+'\n').encode())
index=json.loads(raw(HERE/'source-index.json'));pins=json.loads(raw(HERE/'input-pins.json'));validation=json.loads(raw(OUT/'validation.json'))
assert validation['passed'] and validation['sources_before']==validation['sources_after']==index and validation['inputs_before']==validation['inputs_after']==pins
assert all(desc(HERE/k)==v for k,v in index.items()) and all(desc(ROOT/k)==v for k,v in pins.items())
assert validation['build']['all_children_collected'] and validation['build']['job_active_processes_final']==0
assert all(desc(OUT/k)==v for k,v in validation['outputs'].items())
dll=BUILD/'eu4_pair_send_lab_1375_v25.dll';data=raw(dll);pe=struct.unpack_from('<I',data,0x3c)[0]
assert data[:2]==b'MZ' and data[pe:pe+4]==b'PE\0\0'
machine,nsects,stamp=struct.unpack_from('<HHI',data,pe+4);opt=struct.unpack_from('<H',data,pe+20)[0]
assert machine==0x8664 and 0<nsects<=32 and struct.unpack_from('<H',data,pe+24)[0]==0x20b
image_size=struct.unpack_from('<I',data,pe+80)[0]
sections=[struct.unpack_from('<IIII',data,pe+24+opt+40*i+8) for i in range(nsects)]
def rva(addr,size):
 matches=[(va,off) for virt,va,n,off in sections if va<=addr and addr-va+size<=n]
 assert 0<size<=65536 and len(matches)==1
 va,off=matches[0];return data[off+addr-va:off+addr-va+size]
export,size=struct.unpack_from('<II',data,pe+24+112);ed=rva(export,40);nfunctions,nnames,functions,names,ordinals=struct.unpack_from('<IIIII',ed,20)
assert 0<nfunctions<=128 and nnames==1
name=struct.unpack('<I',rva(names,4))[0];assert rva(name,12)==b'BridgeStart\0'
ordinal=struct.unpack('<H',rva(ordinals,2))[0];assert ordinal<nfunctions
bridge=struct.unpack('<I',rva(functions+ordinal*4,4))[0];assert bridge<image_size and not export<=bridge<export+size
sources=dict(pins)
for name,pin in index.items():sources[str((HERE/name).relative_to(ROOT)).replace('\\','/')]=pin
for name in ['source-index.json','input-pins-initial.json']:sources[str((HERE/name).relative_to(ROOT)).replace('\\','/')]=desc(HERE/name)
manifest=dict(schema='EU4PAIRBUILD/1',purpose='restricted_pair_send_1375_v25',game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
 DLL=dll.name,dll=desc(dll),PE_timestamp=stamp,SizeOfImage=image_size,BridgeStart_RVA=bridge,source_pins=sources,
 validation=desc(OUT/'validation.json'),validation_path=str((OUT/'validation.json').relative_to(ROOT)).replace('\\','/'),
 no_send=False,production_ready=False,strict_SP_verified=False,world_epoch_verified=False)
put(BUILD/'build.json',manifest)
put(HERE/'report.json',dict(scope='V25 corrected transport-vtable-slot send DLL compiled and linked; codec tests only. Legacy installer send_supported=false is hook metadata. Native send untested.',
 DLL=desc(dll),manifest=desc(BUILD/'build.json'),validation=desc(OUT/'validation.json'),source_files=len(sources),codec_groups=19,
 build=validation['build'],DLL_loaded=False,game_accessed=False,native_game_called=False,production_ready=False,independent_review=False,sealing_helper=desc(Path(__file__))))
put(HERE/'review.json',dict(schema=1,status='AUTHOR_BUILD_PASS',report=desc(HERE/'report.json'),source_index=desc(HERE/'source-index.json'),
 validation=desc(OUT/'validation.json'),manifest=desc(BUILD/'build.json'),DLL=desc(dll),DLL_loaded=False,native_game_called=False,production_ready=False))
print(json.dumps(dict(review=desc(HERE/'review.json'),DLL=desc(dll),manifest=desc(BUILD/'build.json'),BridgeStart_RVA=bridge,sources=len(sources))))
