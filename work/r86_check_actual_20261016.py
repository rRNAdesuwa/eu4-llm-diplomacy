from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-20261016-r86-cc220-actual-source/actual-sealed-r1'
MANIFEST={'bytes':16602,'sha256':'69e7167005ff08e09ca29e790786f6055512614debecc72f31d3b37d0583df72'}
READS=[]

def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(p,expected):
    assert not str(p).replace('\\','/').startswith(str(ROOT/'work/deps').replace('\\','/'))
    assert p.stat().st_size<=4194304
    b=p.read_bytes();READS.append({'path':p.relative_to(ROOT).as_posix(),**pin(b)})
    assert pin(b)==expected,p
    assert sum(x['bytes'] for x in READS)<1048576
    return b
def save(name,value):
    b=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    with (OUT/name).open('xb') as f:f.write(b)
    return {'path':(OUT/name).relative_to(ROOT).as_posix(),**pin(b)}

raw=read(OUT/'actual-manifest.json',MANIFEST);m=json.loads(raw)
assert m['sealed'] is True and m['independent_full_actual_review_pending'] is True
assert len(m['source_pins'])==31 and len(m['producer_decoder_expected_witness_pins'])==38
for rel,expected in {**m['source_pins'],**m['local_pins']}.items():read(ROOT/rel,expected)
delivery_raw=(OUT/'delivery.json').read_bytes()
assert pin(delivery_raw)=={'bytes':2361,'sha256':'9c105e1af4a8d17ccd93bbb3f5742cc6da85a47bc1f9aadb3c451ac07786b402'}
READS.append({'path':(OUT/'delivery.json').relative_to(ROOT).as_posix(),**pin(delivery_raw)})
d=json.loads(delivery_raw)
assert d['actual_manifest']=={'path':(OUT/'actual-manifest.json').relative_to(ROOT).as_posix(),**MANIFEST}
assert d['first_filecheck_pending'] is True
for flag in ['native_ready','callable','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','further_actual_authorized']:
    assert m[flag] is False and d[flag] is False
accounting_ref=m['read_accounting_pin'];accounting=json.loads((ROOT/accounting_ref['path']).read_bytes())
READS.append({'path':accounting_ref['path'],**{k:accounting_ref[k] for k in ['bytes','sha256']}})
assert sum(x['bytes'] for x in READS)<1048576
check=save('filecheck.json',{'schema':'EU4-R86-ACTUAL-FIRST-FILECHECK/1','sealed':True,'passed':True,
    'actual_manifest':{'path':(OUT/'actual-manifest.json').relative_to(ROOT).as_posix(),**MANIFEST},
    'source_pin_checks':31,'local_pin_checks':len(m['local_pins']),'engine_body_checks':0,
    'explicit_read_bytes':sum(x['bytes'] for x in READS),'reads':READS,
    'combined_sealer_and_filecheck_explicit_source_bytes':accounting['source_explicit_bytes']+sum(x['bytes'] for x in READS),
    'within_original_source_upper':accounting['source_explicit_bytes']+sum(x['bytes'] for x in READS)<=accounting['source_upper_bytes'],
    'first_check_runs':1,'producer_runs_here':0,'PE_reads_here':0,'decoder_imports_here':0,'game_native_operations':0,
    'all_shells_collected':True,'independent_full_actual_review_pending':True,'native_ready':False,
    'precision':'Separate first passed check supersedes seal-time delivery.first_filecheck_pending without rewriting its historical bytes.'})
script=Path(__file__).resolve();script_ref={'path':script.relative_to(ROOT).as_posix(),**pin(script.read_bytes())}
pub=save('publication-manifest.json',{'schema':'EU4-R86-ACTUAL-PUBLICATION/1','sealed':True,
    'author_delivery_only':True,'independent_full_actual_review_pending':True,
    'actual_manifest':d['actual_manifest'],'contract':d['contract'],'capture':d['capture'],'owned':d['owned'],
    'selected_cfg':d['selected_cfg'],'delivery':{'path':(OUT/'delivery.json').relative_to(ROOT).as_posix(),**pin(delivery_raw)},
    'first_filecheck':check,'checker_source':script_ref,'native_ready':False,'callable':False,'world_lease':False,
    'selected_effect_verified':False,'all_shells_collected':True})
print(json.dumps({'passed':True,'first_filecheck':check,'publication':pub,
    'explicit_check_read_bytes':sum(x['bytes'] for x in READS),'combined_explicit_source_bytes':accounting['source_explicit_bytes']+sum(x['bytes'] for x in READS)}))
