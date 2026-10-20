"""Repair only the stored static stack aliases; no PE reads or disassembly."""
import copy,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/core-five-full88-and-spy-entry-1375'
REVIEW=ROOT/'work/review-results/core-five-full88-and-spy-entry-action-catalog-20261008a'
HERE=ROOT/'work/candidates/core-five-full88-and-spy-entry-r2-1375'
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(name,b):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(b)
assert desc(OLD/'review.json')['sha256']=='4a89957edf48bdaa7db355d08341c65ec9d59c074fa31a393997e42a3d33787e'
assert desc(REVIEW/'review.json')['sha256']=='6bb88653ea5cfb17b6a2c1319aadc1b3e8a35afdcfd23930356031322b22bcf5'
assert all(desc(OLD/k)==v for k,v in json.loads(raw(OLD/'source-index.json')).items())
original=json.loads(raw(OLD/'report.json'));counter=json.loads(raw(REVIEW/'counterexamples.json'))
for evidence in counter['evidence']:
    stored=[r for r in original['instruction_slices']['dispatcher_header'] if r['rva']==evidence['rva']]
    assert len(stored)==1 and all(stored[0][k]==evidence[k] for k in ['bytes','instruction','source','json_pointer'])
first,second=[bytes.fromhex(e['bytes']) for e in counter['evidence']]
assert first[:4]==bytes.fromhex('488d6c24') and second[:3]==bytes.fromhex('4881ec')
rbp_from_current=struct.unpack('b',first[4:])[0]+struct.unpack('<i',second[3:])[0]
base=0x30-rbp_from_current;assert rbp_from_current==0xb9 and base==-0x89
report=copy.deepcopy(original)
for case in counter['cases']:
    p=report['profiles'][case['family']];assert p['original_stack_base']==case['report_value']
    p['original_stack_base']=case['expected_text']
pins=dict(original['source_pins'])
for directory,names in [(OLD,['report.json','review.json','contract.py','test_contract.py']),
 (REVIEW,['review.json','counterexamples.json'])]:
    for name in names:pins[str((directory/name).relative_to(ROOT)).replace('\\','/')]=desc(directory/name)
pins['work/create_core_static_r2_1375.py']=desc(Path(__file__))
assert all(desc(ROOT/k)==v for k,v in pins.items())
report['source_pins']=pins;report['purpose']='static supplement R2: repaired four stack aliases, unchanged finite call-chain evidence'
report['limits']['inherited_exploration_decode_bytes']=report['limits']['new_decode_bytes'];report['limits']['new_decode_bytes']=0
report['stack_alias_repair']={'rbp_from_current_rsp':rbp_from_current,'base_from_rbp':base,
    'prologue_evidence':counter['evidence'],'four_families':[c['family'] for c in counter['cases']],
    'new_disassembly':False,'PE_reopened':False,'uses_saved_instruction_annotations':True}
HERE.mkdir(exist_ok=False)
for name in ['contract.py','test_contract.py']:
    put(name,raw(OLD/name));put('preimages/'+name,raw(OLD/name))
put('preimages/report.json',raw(OLD/'report.json'))
put('report.json',(json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
put('input-pins.json',(json.dumps(pins,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps(dict(created=str(HERE),inputs=len(pins),new_decode_bytes=0)))
