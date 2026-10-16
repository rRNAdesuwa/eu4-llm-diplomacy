"""Build/check only static data contracts and file pins. No OS process access."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES={
 'work/candidates/subject-toggle-contracts-1375/report.json':'ac0853a35387f67af7a1b8c4dcb9173f1efd2c44e438eb1193b9ccd10307b291',
 'work/candidates/subject-military-focus-observer-1375/observer.py':'d03c53ddae7735d4ee2b521dd878fb5bc9045a509a9b56d80ae48f0597367edc',
 'work/candidates/subject-military-focus-observer-1375/report.json':'3bc89887cca5cc3c17fdf3dde2354368920481ffd1125e6650b5df9adbc85da9',
}
REGISTRY='work/reports/native-subject-interactions-1375.json'
def raw(p):
 with p.open('rb') as f:b=f.read(8*1024*1024+1)
 if len(b)>8*1024*1024:raise ValueError('source bound')
 return b
def desc(p):
 h=hashlib.sha256();n=0
 with p.open('rb') as f:
  while b:=f.read(262144):
   n+=len(b);assert n<=64*1024*1024,'streamed input bound';h.update(b)
 return dict(bytes=n,sha256=h.hexdigest())
def encode(x):return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode()
def generate():
 for n,h in SOURCES.items():assert desc(ROOT/n)['sha256']==h
 r=json.loads(raw(ROOT/next(iter(SOURCES))));mil=json.loads(raw(ROOT/'work/candidates/subject-military-focus-observer-1375/report.json'))
 # The selected report itself pins the complete41-family registration source.
 regpin=next(x for x in r['inputs'] if x['path']==REGISTRY)
 assert desc(ROOT/REGISTRY)=={k:regpin[k] for k in ('bytes','sha256')}
 reg=json.loads(raw(ROOT/REGISTRY));assert reg['binary']['sha256']==r['binary_sha256']
 known=[dict(name=x['name'],token=x['token_id'],singleton_rva=x['singleton_rva'],vtable_rva=x['vtable_rva']) for x in reg['actions']]
 assert len(known)==41 and len({x['singleton_rva'] for x in known})==41 and len({x['token'] for x in known})==41
 keys=('constructor','state_getters','gate','definition_allowed_map','normal_ui')
 pins={x['rva']:{k:x[k] for k in ('rva','bytes')} for key in keys for x in r['facts'][key]['evidence']}
 for f in ('0xaf41b0','0x81ee0','0x820f0','0x82720'):
  for x in r['functions'][f]['instructions']:pins[x['rva']]={k:x[k] for k in ('rva','bytes')}
 selected=r['contract']['families'];vts={x['vtable_rva'] for x in selected.values()}
 return dict(schema_version=1,profile='subject_toggle_ro_1375_1',exe_sha256=r['binary_sha256'],pe=mil['pe'],families=selected,known_singletons=known,
  instruction_pins=list(pins.values()),vtable_pins=[x for x in r['data_pins'] if x['rva'] in vts],
  sources={**{n:desc(ROOT/n) for n in SOURCES},REGISTRY:desc(ROOT/REGISTRY)},
  scope='Fixed FRA/NAV selected raw state; no native/TLS/authority/effect proof',
  unsupported=['TLS and visibility getter','full native authority','per-rival embargo effects','scutage modifier definition/value/expiry','trade restoration/government condition','object lifetime/world epoch','runtime execution and production'])
FILES=('prepare.py','observer.py','test_observer.py','contract.json','README.md')
def state():
 c=json.loads(raw(HERE/'contract.json'))
 names=set(c['sources'])|{'work/candidates/subject-military-focus-observer-1375/source-index.json','work/candidates/subject-military-focus-observer-1375/test_observer.py','work/AGENTS.md'}
 names.update(json.loads(raw(ROOT/'work/candidates/subject-military-focus-observer-1375/source-index.json')))
 assert desc(ROOT.parent/'eu4.exe')['sha256']==c['exe_sha256']
 return {'inputs':{n:desc(ROOT/n) for n in sorted(names)},'candidate':{n:desc(HERE/n) for n in FILES}}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--contract-only',action='store_true');a=p.parse_args();c=encode(generate())
 if a.check:assert raw(HERE/'contract.json')==c
 elif (HERE/'contract.json').exists():assert raw(HERE/'contract.json')==c,'existing contract differs'
 else:
  with (HERE/'contract.json').open('xb') as f:f.write(c)
 if not a.contract_only:
  s=state()
  if a.check:assert json.loads(raw(HERE/'source-index.json'))==s
  else:
   with (HERE/'source-index.json').open('xb') as f:f.write(encode(s))
 print(json.dumps(dict(check=a.check,contract_sha256=hashlib.sha256(c).hexdigest(),native_calls=False)))
