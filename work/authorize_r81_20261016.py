"""Root one-attempt cached2/new48 continuation grant; no target execution."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/war-peace-api-20261016-r81-selector-prefix-tail/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r81-root-authorization'
PINS={};READS=[]


def pair(n,sha):return dict(bytes=n,sha256=sha)


def read(rel,expected):
    path=(ROOT/rel).resolve();assert path.is_relative_to(ROOT)and not path.is_relative_to((ROOT/'work/deps').resolve())
    assert path.suffix.lower()not in('.exe','.dll','.pyd');a=path.stat();assert a.st_size<=4*1024*1024
    assert sum(r['bytes']for r in READS)+a.st_size+262144<2*1024*1024
    raw=path.read_bytes();b=path.stat();p=pair(len(raw),hashlib.sha256(raw).hexdigest());READS.append(dict(path=rel,**p))
    assert(len(raw),a.st_size,a.st_mtime_ns)==(b.st_size,b.st_size,b.st_mtime_ns)
    assert p==expected and(rel not in PINS or PINS[rel]==p),rel
    PINS[rel]=p;return json.loads(raw)if rel.endswith('.json')else raw


def save(path,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb')as f:f.write(raw)
    return pair(len(raw),hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT/(BASE+n)).exists()for n in('run-authorization.json','claim.json','capture.json','failure.json','owned-code.json'))
source=read(BASE+'source-manifest.json',pair(23674,'3af48b1a8a938f6ede36d112012ab5f13271a6a231f1fcf87c048f79b2351c64'))
read(BASE+'produce.py',pair(27880,'db69091ea37ee07c7d6aed02fe8aa4e909baecbd6e291849d11595c120546045'))
read(BASE+'entry-seed.json',pair(13487,'0813f0e3e72e3d78e2509c08e7f2ce05401e08140fd71a478f3843bfbc4070b8'))
shape=read(BASE+'upstream-review-shape.json',source['source_pins'][BASE+'upstream-review-shape.json'])
for n in('produce.py','entry-seed.json'):assert source['source_pins'][BASE+n]==PINS[BASE+n]
groups={}
for label,folder,fp,mp in(
    ('root_raw_entry_review','war-peace-api-20261016-r81-entry-independent-review',
     pair(2664,'52a0702193d800977527a9fdaec16d2b89e3e6f9390b04d5cd1d3837a21a2f7f'),
     pair(7947,'13a927675aea85e377abe36a5498259d4967630656098ce4341ebf45a47b6621')),
    ('upstream_actual_review','war-peace-api-20261016-r80-actual-independent-review-r3',
     pair(9252,'81bb504dd809001a9a1549f094e9b9889013808607d16be7e176748ae61d7e18'),
     pair(15918,'91ed106282413b91fbc5d34a2cd096c7f41f1569a2df4ab0bf33ffa0c571a9c4')),
    ('source_peer_review','war-peace-api-20261016-r81-source-independent-review',
     pair(7240,'fe7757a2c60fc33c4827a4ea7ab6254f2a99a84abf91428c656ab37ae8bb679f'),
     pair(10927,'757b1e0e5c31c05dcf4fd32796d6a2e30f2cf0e30c18e3b8fd903cf59ac513f5'))):
    fpath='work/reports/'+folder+'/findings.json';mpath='work/reports/'+folder+'/manifest.json'
    f=read(fpath,fp);m=read(mpath,mp)
    assert f['sealed']and f['passed']and f['blocking_findings']==[]and m['sealed']
    if label=='upstream_actual_review':
        assert len(shape['subject_fields'])==5 and all(f[k]==v for k,v in shape['subject_fields'].items())
    else:
        assert f['subject_source_manifest']==PINS[BASE+'source-manifest.json']
        assert f['subject_producer']==PINS[BASE+'produce.py']and f['subject_entry_seed']==PINS[BASE+'entry-seed.json']
        if label=='root_raw_entry_review':
            assert f['scope']=='cached_partial_continuation_seed_only'
            assert(f['entry_rva'],f['physical_start_rva'],f['end_exclusive'])==('0x97bd6e','0x97bd70','0x97bda0')
            assert(f['requested_bytes'],f['cached_bytes'],f['combined_bytes'],f['cached_raw_hex'])==(48,2,50,'48c1')
    groups[label]=dict(findings=dict(path=fpath,**fp),manifest=dict(path=mpath,**mp))
for rel,p in dict(PINS).items():read(rel,p)
auth=dict(schema='EU4-R81-ROOT-AUTHORIZATION/1',sealed=True,root_explicit_start_received=True,single_attempt=True,
    operation='one-fixed-cached2-plus-new48B-continuation',entry_rva='0x97bd6e',physical_start_rva='0x97bd70',
    end_exclusive='0x97bda0',requested_bytes=48,cached_bytes=2,combined_bytes=50,cached_raw_hex='48c1',
    source_manifest=PINS[BASE+'source-manifest.json'],producer_pin=PINS[BASE+'produce.py'],entry_seed_pin=PINS[BASE+'entry-seed.json'],
    sole_executor='diplomacy_static',source_bytes_limit=32*1024*1024,retained_bytes_limit=16*1024*1024,
    software_memory_limit=768*1024*1024,stop_at_or_above_1GiB=True,authorizes_retry=False,native_ready=False,
    reader_adoption_allowed=False,selected_effect_verified=False,world_lease=False,atomic_snapshot=False,host_guard_change_authorized=False,
    scope='One new48B targeted continuation only/no newmetadata. Cache2B exactly48c1 from accepted R80 owned offset62; combined50B starts97bd6e, fixedend97bda0. No targeted old64/cache2 reread, no suffix/callee/RIPdata/vslot/header/unwind/othercode/process/UI/game/native/request/test/fallback. Both completeEXESHA passes still cover wholefile. Exact source/cache/three review/auth subjects before-after; exclusiveclaim, normal targetclose before finalguards/capture. Continuation keeps prior symbolic state under valid sequential-memory/controlstack premises, never resets Win64formals or assumes returns/wholefunction/units/finalD/header/lifetime/effect.',
    **groups)
OUT.mkdir();ap=save(ROOT/(BASE+'run-authorization.json'),auth)
rp=save(OUT/'receipt.json',dict(sealed=True,passed=True,blocking_findings=[],input_pins=PINS,read_journal=READS,
    before_after_equal=True,authorization=ap,selected_read_bytes=sum(r['bytes']for r in READS),manual_inspection_allowance=262144,
    source_limit=2*1024*1024,actual_runs=0,PE_engine_decoder_game_tests_native=0,sole_executor='diplomacy_static'))
print(json.dumps(dict(authorization=ap,receipt=rp,read_bytes=sum(r['bytes']for r in READS)),ensure_ascii=True))
