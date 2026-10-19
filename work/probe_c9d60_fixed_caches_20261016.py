"""Two exact retained cache key probes; no PE/decoder/target access or body analysis."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r88-c9d60-cache-metadata'
assert not OUT.exists()
used=0;journal=[];CAP=8388608;MANUAL=524288
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(n,p):
 global used
 f=ROOT/n;s=f.stat().st_size
 assert 0<s<=4194304 and used+s+1+MANUAL<=CAP
 with f.open('rb') as h:b=h.read(s+1)
 used+=len(b);assert len(b)==s and pin(b)==p,n
 journal.append({'path':n,**pin(b)});return b
sources={
 'work/reports/native-owned-peace-1375.json':{'bytes':1302642,'sha256':'f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d'},
 'work/reports/native-pair-replies-1375.json':{'bytes':1894144,'sha256':'da3faa061af3d9ee8a3003412151594c6305b765afd8d739b4cb4a4759f63510'},
 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/capture.json':{'bytes':140752,'sha256':'0f4ab901823ec893da60ebdeb9d237c1feec469cf67f4bed223b660a070955ec'},
 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/owned-code.json':{'bytes':1099,'sha256':'dd4d12d21f9903eacfbcaeb1e6769e8ebb8f1bf98715cfdc6f0e0ea7bc125a69'}}
data={n:read(n,p) for n,p in sources.items()}
cap=json.loads(data['work/reports/war-peace-api-20261016-r87-dual-frontier-source/capture.json'])
owned=json.loads(data['work/reports/war-peace-api-20261016-r87-dual-frontier-source/owned-code.json'])
call=[r for r in cap['analysis']['instructions'] if r['rva']=='0xcc305']
assert len(call)==1 and call[0]['bytes']=='e856daffff'
raw=bytes.fromhex(owned['raw_hex']);assert raw[0xcc305-0xcc266:0xcc30a-0xcc266]==bytes.fromhex('e856daffff')
disp=int.from_bytes(bytes.fromhex('56daffff'),'little',signed=True)
assert 0xcc305+5+disp==0xc9d60
probes=[]
for n in list(sources)[:2]:
 obj=json.loads(data[n]);functions=obj.get('functions')
 assert type(functions)is dict
 key='0xc9d60';v=functions.get(key)
 probes.append({'path':n,'source_pin':sources[n],'exact_key':key,'present':key in functions,
   'entry_kind':type(v).__name__,'entry_keys':list(v) if type(v)is dict else None,
   'row_count':len(v['instructions']) if type(v)is dict and type(v.get('instructions'))is list else None})
for n,p in sources.items():read(n,p)
assert used+MANUAL<=CAP
OUT.mkdir()
findings={'schema':'EU4-R88-FIXED-CACHE-METADATA/1','sealed':True,
 'scope':'Two exact function keys and independent raw direct-call arithmetic only, not an accepted full R87 semantic review.',
 'call_seed':{'site':'0xcc305','raw':'e856daffff','signed_disp32':disp,'next':'0xcc30a','target':'0xc9d60','owned_window_slice':[159,164]},
 'probes':probes,'source_before_after_equal':True,'explicit_source_returned':used,'manual_small_metadata_read_allowance':MANUAL,'source_upper':used+MANUAL,'source_cap':CAP,
 'limits':['No alternate key spelling or third cache searched; absent exact keys do not prove repository/global native absence.',
 'JSON parsed only for selected container/key/field names and row-count metadata; no selected or other function business body analyzed.',
 'Current R87 actual full raw/contract review remains a separate gate. No new code acquisition or callee/native execution is authorized here.'],
 'PE_engine_decoder_game_native_requests_tests':0,'native_ready':False,'callable':False,'ownership_transfer_verified':False,'further_actual_authorized':False}
fb=(json.dumps(findings,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
(OUT/'findings.json').write_bytes(fb)
manifest={'schema':'EU4-R88-CACHE-METADATA-MANIFEST/1','sealed':True,'source_pins':sources,'owned_pins':{'findings.json':pin(fb)},'read_journal':journal,'source_before_after_equal':True,'no_target_execution':True}
mb=(json.dumps(manifest,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii');(OUT/'manifest.json').write_bytes(mb)
print(json.dumps({'findings':{'path':OUT.relative_to(ROOT).as_posix()+'/findings.json',**pin(fb)},'manifest':{'path':OUT.relative_to(ROOT).as_posix()+'/manifest.json',**pin(mb)},'probes':probes,'source_upper':used+MANUAL},ensure_ascii=True))
