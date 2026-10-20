"""Exact root one-attempt grant; fixed files, reviewer byte/SHA supplied by root."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r80-root-authorization'
PINS = {}; READS = []


def pair(n,sha):
    return dict(bytes=n,sha256=sha)


def read(rel,expected):
    path=(ROOT/rel).resolve()
    assert path.is_relative_to(ROOT) and not path.is_relative_to((ROOT/'work/deps').resolve())
    assert path.suffix.lower() not in ('.exe','.dll','.pyd')
    a=path.stat();assert a.st_size<=4*1024*1024
    assert sum(r['bytes']for r in READS)+a.st_size+262144<2*1024*1024
    raw=path.read_bytes();b=path.stat();p=pair(len(raw),hashlib.sha256(raw).hexdigest())
    READS.append(dict(path=rel,**p))
    assert (len(raw),a.st_size,a.st_mtime_ns)==(b.st_size,b.st_size,b.st_mtime_ns)
    assert p==expected and (rel not in PINS or PINS[rel]==p),rel
    PINS[rel]=p
    return json.loads(raw) if rel.endswith('.json')else raw


def save(path,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb')as f:f.write(raw)
    return pair(len(raw),hashlib.sha256(raw).hexdigest())


assert len(sys.argv)==5
assert all(re.fullmatch('[0-9a-f]{64}',sys.argv[i])for i in (2,4))
peer_fp=pair(int(sys.argv[1]),sys.argv[2]);peer_mp=pair(int(sys.argv[3]),sys.argv[4])
assert 0<peer_fp['bytes']<=1024*1024 and 0<peer_mp['bytes']<=1024*1024
assert not OUT.exists()
assert not any((ROOT/(BASE+n)).exists()for n in('run-authorization.json','claim.json','capture.json','failure.json','owned-code.json'))
source=read(BASE+'source-manifest.json',pair(24123,'42b2d958a64df12ea3083402db08519226218876c51d526dae3285cc95bf5ce2'))
read(BASE+'produce.py',pair(24738,'60009c332eedc75f766200e611930a299d1ec0dcb04f161dd8917c9a7c359c90'))
read(BASE+'entry-seed.json',pair(10512,'a48da80c1e754b13033d0733656e27d0f13ec51d1146bec76675e41185e58384'))
shape=read(BASE+'upstream-review-shape.json',source['source_pins'][BASE+'upstream-review-shape.json'])
for n in('produce.py','entry-seed.json'):
    assert source['source_pins'][BASE+n]==PINS[BASE+n]
groups={}
for label,folder,fp,mp in(
    ('root_raw_entry_review','war-peace-api-20261016-r80-entry-independent-review',
     pair(2604,'91e942aa27bb11618ce0f2f54b266eed5d35bc388e3f412c3c4911eb76cfc302'),
     pair(8565,'05acc4a73652d08f51c0e27d588ed31e46cb5c9f09ae0347429381c6c1a99ef5')),
    ('upstream_actual_review','war-peace-api-20261016-r79-actual-independent-review',
     pair(9030,'8d2277950f717a9d5769bb20c8bb0fe9ce699180247c51dc63b8bccd24fbdf9b'),
     pair(11402,'aaca888b33d4cce78f1781448c76526b7a034be82fb0aea152ad1d972e009211')),
    ('source_peer_review','war-peace-api-20261016-r80-source-independent-review',peer_fp,peer_mp)):
    fpath='work/reports/'+folder+'/findings.json';mpath='work/reports/'+folder+'/manifest.json'
    f=read(fpath,fp);m=read(mpath,mp)
    assert f['sealed']and f['passed']and f['blocking_findings']==[]and m['sealed']
    if label=='upstream_actual_review':
        assert all(f[k]==v for k,v in shape['subject_fields'].items())
    else:
        assert f['subject_source_manifest']==PINS[BASE+'source-manifest.json']
        assert f['subject_producer']==PINS[BASE+'produce.py']and f['subject_entry_seed']==PINS[BASE+'entry-seed.json']
        if label=='root_raw_entry_review':
            assert f['scope']=='raw_known_CALL_prefix_seed_only'and f['entry_rva']=='0x97bd30'and f['end_exclusive']=='0x97bd70'
            assert f['call_site_rva']=='0x99358a'and f['raw_call_hex']=='e8a187feff'and f['requested_bytes']==64
    groups[label]=dict(findings=dict(path=fpath,**fp),manifest=dict(path=mpath,**mp))
for rel,p in dict(PINS).items():read(rel,p)
auth=dict(schema='EU4-R80-ROOT-AUTHORIZATION/1',sealed=True,root_explicit_start_received=True,single_attempt=True,
    operation='one-fixed-known-CALL-prefix-64B',entry_rva='0x97bd30',end_exclusive='0x97bd70',requested_bytes=64,
    call_site_rva='0x99358a',raw_call_hex='e8a187feff',source_manifest=PINS[BASE+'source-manifest.json'],
    producer_pin=PINS[BASE+'produce.py'],entry_seed_pin=PINS[BASE+'entry-seed.json'],sole_executor='diplomacy_static',
    source_bytes_limit=32*1024*1024,retained_bytes_limit=16*1024*1024,software_memory_limit=768*1024*1024,
    stop_at_or_above_1GiB=True,authorizes_retry=False,native_ready=False,reader_adoption_allowed=False,
    selected_effect_verified=False,world_lease=False,atomic_snapshot=False,host_guard_change_authorized=False,
    scope='One64B targeted code prefix only/newpdata0. Cached R69 CALL and R79 two descriptor fences/unique cached.text mapping; invalidunknown0code, no fallback/sliding/suffix/callee/RIPdata/vslot/header/unwind/othercode/process/UI/game/native/request/test. Two full EXE SHA passes separate and allsource/engine/auth/review checks before-after; exclusiveclaim, normal targetclose before finalguard capture. KnownCALL prefix is not wholefunction/globalunwindabsence/leaf proof; no formal/unit/finalD/header/lifetime/effect inference. All three reviews must match exact subjects; no reuse of previous attempt authorization.',
    **groups)
OUT.mkdir()
ap=save(ROOT/(BASE+'run-authorization.json'),auth)
rp=save(OUT/'receipt.json',dict(sealed=True,passed=True,blocking_findings=[],input_pins=PINS,read_journal=READS,
    before_after_equal=True,authorization=ap,selected_read_bytes=sum(r['bytes']for r in READS),
    manual_inspection_allowance=262144,source_limit=2*1024*1024,actual_runs=0,
    PE_engine_decoder_game_tests_native=0,sole_executor='diplomacy_static'))
print(json.dumps(dict(authorization=ap,receipt=rp,selected_read_bytes=sum(r['bytes']for r in READS)),ensure_ascii=True))
