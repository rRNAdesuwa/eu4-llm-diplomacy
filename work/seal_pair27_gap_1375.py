"""Seal a fresh gap-only DLL and fixed batch client; no game access."""
import hashlib, json, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'work/candidates/v27-gap-batch-1375'
BUILD = HERE/'development-attempt1/build'
POLICY = ROOT/'work/reports/diplomacy-no-repeat-test-policy-1375.json'
ACTIONS = ['offer_fleet_basing_rights','insult','form_coalition','support_independence','trade_favors_for_gold','stop_currying_favors']
def pin(p):
    b=p.read_bytes(); return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def encode(o): return (json.dumps(o,indent=2,sort_keys=True)+'\n').encode('ascii')
policy=json.loads(POLICY.read_bytes())
assert not set(ACTIONS)&set(policy['blocked_actions'])
pins=json.loads((HERE/'input-pins.json').read_bytes())
for name, expected in list(pins.items()): assert pin(ROOT/name)==expected,name
for name, expected in json.loads((HERE/'source-index.json').read_bytes()).items():
    path=(HERE/name).resolve(); assert path.is_relative_to(ROOT) and pin(path)==expected
    pins[path.relative_to(ROOT).as_posix()]=expected
for path in [HERE/'source-index.json', HERE/'input-pins.json', HERE/'profile-facts.json',
             ROOT/'work/validate_pair27_gap_1375.py', Path(__file__).resolve(),
             ROOT/'tools/plan_diplomacy_gap_tests.py', POLICY]:
    pins[path.relative_to(ROOT).as_posix()]=pin(path)
for name, expected in policy['source_pins'].items():
    path=ROOT/name; assert pin(path)['sha256']==expected
    pins[path.relative_to(ROOT).as_posix()]=pin(path)
validation=HERE/'development-attempt1/validation.json'
assert json.loads(validation.read_bytes())['passed'] is True
dll=BUILD/'eu4_pair_send_lab_1375_v27.dll'; b=dll.read_bytes()
nt=struct.unpack_from('<I',b,60)[0]
assert b[nt:nt+4]==b'PE\0\0' and struct.unpack_from('<H',b,nt+24)[0]==0x20b
count, optional=struct.unpack_from('<H',b,nt+6)[0],struct.unpack_from('<H',b,nt+20)[0]
sections=[]
for i in range(count):
    vs,va,size,raw=struct.unpack_from('<IIII',b,nt+24+optional+i*40+8)
    sections.append((va,max(vs,size),raw))
def offset(rva):
    for va,size,raw in sections:
        if va<=rva<va+size:return raw+rva-va
    raise ValueError('unmapped RVA')
exports=offset(struct.unpack_from('<I',b,nt+24+112)[0])
names_count,functions,names,ordinals=struct.unpack_from('<IIII',b,exports+24)
start=None
for i in range(names_count):
    off=offset(struct.unpack_from('<I',b,offset(names)+4*i)[0])
    if b[off:b.index(b'\0',off)]==b'BridgeStart':
        ordinal=struct.unpack_from('<H',b,offset(ordinals)+2*i)[0]
        start=struct.unpack_from('<I',b,offset(functions)+4*ordinal)[0]
assert start and len(pins)<=512
m=dict(schema='EU4PAIRBUILD/1',purpose='restricted_pair_send_1375_v27',DLL=dll.name,
       BridgeStart_RVA=start,PE_timestamp=struct.unpack_from('<I',b,nt+8)[0],
       SizeOfImage=struct.unpack_from('<I',b,nt+80)[0],dll=pin(dll),no_send=False,
       production_ready=False,strict_SP_verified=False,world_epoch_verified=False,
       game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
       validation=pin(validation),validation_path=validation.relative_to(ROOT).as_posix(),source_pins=pins)
with (BUILD/'build.json').open('xb') as f:f.write(encode(m))
manifest_sha=pin(BUILD/'build.json')['sha256']
source=ROOT/'work/candidates/v25-pair-send-private-client-1375/client.py'
assert pin(source)['sha256']=='9a6b722d725e8090f85b31f82910bee0d856e488598c7c31c5dc362b75a10d15'
client=source.read_text()
changes={
 'fixed six-positive send batch.':'fixed six unverified actions; historical successes forbidden.',
 'v25-pair-send-bootstrap-1375':'v27-gap-batch-1375',
 '40738e72bdbf1c6442d9a6b55ef83ac6bf8e6211669db9b83bda41660e8f9929':manifest_sha,
 'restricted_pair_send_1375_v25':'restricted_pair_send_1375_v27',
 "ACTIONS=['offer_vassalization','royal_marriage','improve_relations','guarantee','build_spy_network','curry_favors']":
    'ACTIONS='+repr(ACTIONS)+"\nTARGETS=['ENG','NAV','SAV','HOL','POR','POR']\nFAMILIES=[6,7,8,9,10,5]",
 'pair25':'pair27',
 'target=ENG':"target={TARGETS[sequence-1]}",
 "row['target']=='ENG'":"row['target']==TARGETS[row['sequence']-1]",
 "row['sequence']<=6":"row['sequence']<=len(ACTIONS)",
 "len(pub['request_sha256'])==6":"len(pub['request_sha256'])==len(ACTIONS)",
 "row['family']==current-1":"row['family']==FAMILIES[current-1]",
 'positive-six.publisher-intent.json':'gap-six.publisher-intent.json',
 'len(results)==6':'len(results)==len(ACTIONS)',
 "last.get('sequence')==6":"last.get('sequence')==len(ACTIONS)",
 'range(1,7)':'range(1,len(ACTIONS)+1)',
 'def batch(id,m,readonly):':'''def no_repeat_policy():
 policy=value(raw(ROOT/'work/reports/diplomacy-no-repeat-test-policy-1375.json',1024*1024))
 require(not set(ACTIONS)&set(policy['blocked_actions']),'Previously successful action forbidden')
 require(len(ACTIONS)==len(set(ACTIONS))==len(TARGETS)==len(FAMILIES),'Fixed unique gap batch')
 for name,expected in policy['source_pins'].items():
  require(sha(raw(ROOT/name,4*1024*1024))==expected,'Changed no-repeat evidence')

def batch(id,m,readonly):
 no_repeat_policy()''',
}
for before,after in changes.items():
    assert before in client,before;client=client.replace(before,after)
assert 'pair25' not in client and 'target=ENG' not in client
compile(client,'v27-client.py','exec')
destination=ROOT/'work/candidates/v27-gap-private-client-1375'
destination.mkdir(exist_ok=False)
with (destination/'client.py').open('xb') as f:f.write(client.encode('utf-8'))
print(json.dumps(dict(manifest_sha256=manifest_sha,client=pin(destination/'client.py'),dll=m['dll'],export=start,source_count=len(pins),actions=ACTIONS)))
