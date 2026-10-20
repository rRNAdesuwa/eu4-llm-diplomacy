"""Seal the compiled gap-only candidate and derive its single-action client."""
import hashlib, json, runpy, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/v26-gap-curry-bootstrap-1375'
BUILD = HERE / 'development-attempt1/build'
def pin(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
def encode(obj): return (json.dumps(obj, indent=2, sort_keys=True)+'\n').encode('ascii')
prepare = runpy.run_path(str(HERE/'prepare.py'))
pins = prepare['inputs']()
assert prepare['current']() == json.loads((HERE/'source-index.json').read_bytes())
for name in [*prepare['FILES'], 'source-index.json']:
    p = HERE/name
    pins[p.relative_to(ROOT).as_posix()] = pin(p)
dll = BUILD/'eu4_pair_send_lab_1375_v26.dll'
b = dll.read_bytes(); nt = struct.unpack_from('<I', b, 60)[0]
assert b[nt:nt+4] == b'PE\0\0' and struct.unpack_from('<H', b, nt+24)[0] == 0x20b
sections = []
count, optional = struct.unpack_from('<H', b, nt+6)[0], struct.unpack_from('<H', b, nt+20)[0]
for i in range(count):
    off = nt+24+optional+i*40
    vs, va, size, raw = struct.unpack_from('<IIII', b, off+8)
    sections.append((va, max(vs,size), raw))
def offset(rva):
    for va,size,raw in sections:
        if va <= rva < va+size: return raw+rva-va
    raise ValueError('Unmapped RVA')
exports = offset(struct.unpack_from('<I', b, nt+24+112)[0])
names_count, functions, names, ordinals = struct.unpack_from('<IIII', b, exports+24)
start = None
for i in range(names_count):
    nameoff = offset(struct.unpack_from('<I', b, offset(names)+4*i)[0])
    name = b[nameoff:b.index(b'\0', nameoff)]
    if name == b'BridgeStart':
        ordinal = struct.unpack_from('<H', b, offset(ordinals)+2*i)[0]
        start = struct.unpack_from('<I', b, offset(functions)+4*ordinal)[0]
assert start
validation = HERE/'development-attempt1/validation.json'
m = dict(schema='EU4PAIRBUILD/1', purpose='restricted_pair_send_1375_v26', DLL=dll.name,
    BridgeStart_RVA=start, PE_timestamp=struct.unpack_from('<I',b,nt+8)[0],
    SizeOfImage=struct.unpack_from('<I',b,nt+80)[0], dll=pin(dll), no_send=False,
    production_ready=False, strict_SP_verified=False, world_epoch_verified=False,
    game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
    validation=pin(validation), validation_path=validation.relative_to(ROOT).as_posix(), source_pins=pins)
with (BUILD/'build.json').open('xb') as f: f.write(encode(m))
manifest_sha = pin(BUILD/'build.json')['sha256']
client = (ROOT/'work/candidates/v25-pair-send-private-client-1375/client.py').read_text()
changes = {
    'fixed six-positive send batch.':'single unverified curry-favors request.',
    'v25-pair-send-bootstrap-1375':'v26-gap-curry-bootstrap-1375',
    '40738e72bdbf1c6442d9a6b55ef83ac6bf8e6211669db9b83bda41660e8f9929':manifest_sha,
    'restricted_pair_send_1375_v25':'restricted_pair_send_1375_v26',
    "ACTIONS=['offer_vassalization','royal_marriage','improve_relations','guarantee','build_spy_network','curry_favors']":"ACTIONS=['curry_favors']",
    'pair25':'pair26', 'target=ENG':'target=POR', "row['target']=='ENG'":"row['target']=='POR'",
    "row['sequence']<=6":"row['sequence']<=len(ACTIONS)",
    "len(pub['request_sha256'])==6":"len(pub['request_sha256'])==len(ACTIONS)",
    "row['family']==current-1":"row['family']==5",
    'positive-six.publisher-intent.json':'gap-curry.publisher-intent.json',
    'len(results)==6':'len(results)==len(ACTIONS)',
    "last.get('sequence')==6":"last.get('sequence')==len(ACTIONS)",
    'range(1,7)':'range(1,len(ACTIONS)+1)',
}
for before,after in changes.items():
    assert before in client, before
    client = client.replace(before,after)
assert 'pair25' not in client and 'target=ENG' not in client
assert "ACTIONS=['curry_favors']" in client
destination = ROOT/'work/candidates/v26-gap-curry-private-client-1375'
destination.mkdir(exist_ok=False)
with (destination/'client.py').open('xb') as f: f.write(client.encode('utf-8'))
print(json.dumps(dict(manifest_sha256=manifest_sha, client=pin(destination/'client.py'), dll=m['dll'], export=start)))
