"""Replay cached partial provenance and the separate48B continuation, no PE."""
import hashlib
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/war-peace-api-20261016-r81-selector-prefix-tail/'
R80='work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r81-entry-independent-review'
PINS={};READS=[]


def pair(n,sha):return dict(bytes=n,sha256=sha)


def read(rel,expected):
    path=(ROOT/rel).resolve();assert path.is_relative_to(ROOT)and not path.is_relative_to((ROOT/'work/deps').resolve())
    assert path.suffix.lower()not in('.exe','.dll','.pyd')
    a=path.stat();assert a.st_size<=4*1024*1024
    assert sum(r['bytes']for r in READS)+a.st_size+512*1024<4*1024*1024
    raw=path.read_bytes();b=path.stat();pin=pair(len(raw),hashlib.sha256(raw).hexdigest());READS.append(dict(path=rel,**pin))
    assert(len(raw),a.st_size,a.st_mtime_ns)==(b.st_size,b.st_size,b.st_mtime_ns)
    assert pin==expected and(rel not in PINS or PINS[rel]==pin),rel
    PINS[rel]=pin;return json.loads(raw)if rel.endswith('.json')else raw


def save(path,obj):
    raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb')as f:f.write(raw)
    return pair(len(raw),hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT/(BASE+n)).exists()for n in('run-authorization.json','claim.json','capture.json','owned-code.json','failure.json'))
source=read(BASE+'source-manifest.json',pair(23674,'3af48b1a8a938f6ede36d112012ab5f13271a6a231f1fcf87c048f79b2351c64'))
read(BASE+'produce.py',pair(27880,'db69091ea37ee07c7d6aed02fe8aa4e909baecbd6e291849d11595c120546045'))
seed=read(BASE+'entry-seed.json',pair(13487,'0813f0e3e72e3d78e2509c08e7f2ce05401e08140fd71a478f3843bfbc4070b8'))
for n in('produce.py','entry-seed.json'):assert source['source_pins'][BASE+n]==PINS[BASE+n]


def prior(rel):return read(rel,source['source_pins'][rel])


owned=prior(R80+'owned-code.json');capture=prior(R80+'capture.json');selected=prior(R80+'actual-selected-evidence.json')
prior(R80+'actual-manifest.json');prior(R80+'actual-contract.json')
review='work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/'
full=read(review+'findings.json',pair(9252,'81bb504dd809001a9a1549f094e9b9889013808607d16be7e176748ae61d7e18'))
read(review+'manifest.json',pair(15918,'91ed106282413b91fbc5d34a2cd096c7f41f1569a2df4ab0bf33ffa0c571a9c4'))
assert full['sealed']and full['passed']and full['blocking_findings']==[]
for key,name in(('subject_actual_manifest','actual-manifest.json'),('subject_capture_pin','capture.json'),
                 ('subject_contract_pin','actual-contract.json'),('subject_owned_pin','owned-code.json'),('subject_selected_pin','actual-selected-evidence.json')):
    assert full[key]==dict(path=R80+name,**PINS[R80+name])
assert seed['cache_source_owned_pin']==PINS[R80+'owned-code.json']
assert seed['cache_source_capture_pin']==PINS[R80+'capture.json']and seed['cache_source_selected_pin']==PINS[R80+'actual-selected-evidence.json']
raw=bytes.fromhex(owned['raw_hex']);assert owned['window']==['0x97bd30','0x97bd70']and len(raw)==64
assert hashlib.sha256(raw).hexdigest()==owned['sha256']
assert raw[62:]==bytes.fromhex('48c1')and seed['cached_raw_hex']=='48c1'and seed['cached_raw_offset_in_old64']==62
partial=[dict(kind='undecodable_or_partial',rva='0x97bd6e',raw_hex='48c1')]
assert capture['analysis']['terminals']==selected['partial']==seed['partial_terminal']==partial
rows=seed['retained_prefix_rows'];assert rows==capture['analysis']['instructions']==selected['retained_decoder_rows']and len(rows)==13
cursor=0x97bd30
for row in rows:
    body=bytes.fromhex(row['bytes']);assert int(row['rva'],16)==cursor
    assert raw[cursor-0x97bd30:cursor-0x97bd30+len(body)]==body
    assert row['mnemonic']not in('call','ret','push','pop','jmp')and 'rsp'not in row['registers_written']
    cursor+=len(body)
assert cursor==0x97bd6e and raw[cursor-0x97bd30:]==bytes.fromhex('48c1')
assert (seed['entry_rva'],seed['physical_start_rva'],seed['end_exclusive'])==('0x97bd6e','0x97bd70','0x97bda0')
assert(seed['requested_bytes'],seed['cached_bytes'],seed['combined_bytes'])==(48,2,50)
assert 0x97bda0-0x97bd70==48 and 0x97bda0-0x97bd6e==50 and seed['new_pdata_bytes']==0
old=read('work/reports/war-peace-api-20261016-r79-null-selector-callee/capture.json',pair(69473,'97f3cf26d8bac7ad0fa7674da900c8284906e19c9a07033c6a2cba4e47605506'))
assert seed['cache_previous']==old['selected']==old['pdata_requests'][17]
assert seed['cache_next']==old['next']==old['pdata_requests'][19]
for field,index,expected in(('cache_previous',19063,'90bc970021bd9700e4c0e701'),('cache_next',19064,'a0bd97003cbe97001898dc01')):
    item=seed[field];begin,end,unwind=struct.unpack('<III',bytes.fromhex(item['raw_hex']))
    assert item['index']==index and item['raw_hex']==expected
    assert(hex(begin),hex(end),hex(unwind))==(item['begin_rva'],item['end_exclusive'],item['unwind_rva_unfollowed'])
assert int(seed['cache_previous']['end_exclusive'],16)<=0x97bd6e<0x97bd70<0x97bda0==int(seed['cache_next']['begin_rva'],16)
cache=prior('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
plans=[]
for begin,size in((0x97bd6e,50),(0x97bd70,48)):
    matches=[s for s in cache['sections']if int(s['rva'],16)<=begin and begin+size<=int(s['rva'],16)+s['raw_size']]
    assert len(matches)==1 and matches[0]['name']=='.text';sec=matches[0];start=int(sec['rva'],16)
    assert begin+size<=start+sec['virtual_size'];h=bytes.fromhex(sec['section_header_raw_hex'])
    assert len(h)==40 and h[:8].rstrip(b'\0')==b'.text'
    assert struct.unpack_from('<IIII',h,8)==(sec['virtual_size'],start,sec['raw_size'],sec['raw_file_offset'])
    where=sec['raw_file_offset']+begin-start;assert 0<=where<=38462504-size
    plans.append(dict(rva=hex(begin),bytes=size,file_offset=where))
assert plans[0]['file_offset']==seed['cached_combined_mapping_file_offset']==9941358
assert plans[1]['file_offset']==seed['cached_physical_file_offset']==9941360==plans[0]['file_offset']+2
before=dict(PINS)
for rel,p in before.items():read(rel,p)
assert sum(r['bytes']for r in READS)+512*1024+207189+262144<4*1024*1024
OUT.mkdir()
fp=save(OUT/'findings.json',dict(schema='EU4-R81-INDEPENDENT-RAW-CONTINUATION-SEED-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
    scope='cached_partial_continuation_seed_only',subject_source_manifest=PINS[BASE+'source-manifest.json'],
    subject_producer=PINS[BASE+'produce.py'],subject_entry_seed=PINS[BASE+'entry-seed.json'],entry_rva='0x97bd6e',
    physical_start_rva='0x97bd70',end_exclusive='0x97bda0',requested_bytes=48,cached_bytes=2,combined_bytes=50,cached_raw_hex='48c1',
    mapping_plans=plans,retained_prefix_rows=13,cached_raw_offset=62,new_pdata_bytes=0,
    precision_notes=['Own R1 wrongly assumed selected.instructions; actual schema retained_decoder_rows is used in R2. Original source/trace/derived207189B failed reads are preserved separately; no author, PE, decoder or test was repeated.',
        'This is continuation of a partial instruction. The13 old rows/raw64 are retained witnesses, not freshly decoded or reread from EXE.',
        'Only48 new targeted bytes are allowed. Cached2+48 form50 owned decode bytes; both whole-file SHA passes still traverse the complete file.',
        'The retained prefix leaves RSP unchanged under valid ordinary sequential semantics, inheriting S69-60 from the original CALL. Current register expressions are not new Win64 formals or returns.',
        'R80 fullreview is a fixed accepted flat witness. It does not imply an exhaustive global unwind table, wholefunction, no tail writes, units, type, lifetime or effect proof.',
        'Sourcepeer and a separate root once grant are still required; no new code, metadata, PE, engine, decoder or game operation occurred.'],
    resources=dict(selected_read_bytes=sum(r['bytes']for r in READS),manual_inspection_allowance=512*1024,maximum=4*1024*1024,failed_R1_reads_derived_upper=207189,repair_metadata_allowance=262144,combined_source_upper=sum(r['bytes']for r in READS)+512*1024+207189+262144),
    PE_engine_decoder_game_operations=0,author_programs_or_tests_run=0,actual_authorized=False,native_ready=False,callable=False,
    authorizes_retry=False,reader_adoption_allowed=False,selected_effect_verified=False,world_lease=False,atomic_snapshot=False))
mp=save(OUT/'manifest.json',dict(sealed=True,passed=True,pins=before,findings=fp,read_journal=READS,before_after_equal=True,
    scope='selected retained partial/owned/cache/upstream source files only',actual_authorized=False))
print(json.dumps(dict(findings=fp,manifest=mp,read_bytes=sum(r['bytes']for r in READS),files=len(PINS)),ensure_ascii=True))
