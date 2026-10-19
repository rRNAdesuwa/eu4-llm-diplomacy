"""Root raw frontier and source-peer acceptance only. No target/decoder execution."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
PEER='work/reports/war-peace-api-20261016-r87-source-independent-review/'
R86='work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
GRANT='work/reports/war-peace-api-20261016-r87-root-source-authorization/authorization.json'
OUT=ROOT/'work/reports/war-peace-api-20261016-r87-root-raw-frontier-review'
assert not OUT.exists()
journal=[];used=0;CAP=8388608;MANUAL=524288;PRIOR=0
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(name,p=None):
 global used
 path=ROOT/name;size=path.stat().st_size
 assert 0<=size<=4194304 and used+size+1+MANUAL+PRIOR<=CAP
 with path.open('rb') as f:b=f.read(size+1)
 used+=len(b);assert len(b)==size
 if p is not None:assert pin(b)==p,name
 journal.append({'path':name,**pin(b)})
 return b
def fixed(name,size,sha):return read(name,{'bytes':size,'sha256':sha})
def triple(name,b):return {'path':name,**pin(b)}
def encode(o):return (json.dumps(o,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
def save(name,o):
 b=encode(o)
 with (OUT/name).open('xb') as f:f.write(b)
 return b
failure_raw=read('work/reports/war-peace-api-20261016-r87-root-raw-frontier-review-failure-r1/failure.json')
failure=json.loads(failure_raw)
PRIOR=503604+85315+failure['script_pin']['bytes']
manifest_raw=fixed(BASE+'source-manifest.json',26330,'e40ccf4eba10b12b7d626f0fc00b1bcdac50972d1a0a35559ba3756b64694817')
peer_raw=fixed(PEER+'findings.json',6026,'73c9edd7d2447e7535b9d7760a11144071bdd5c9e2b47149d02cc7f4fa6eac68')
peer_manifest=fixed(PEER+'manifest.json',12733,'5201657ca1983b86555b70e1dc91d62f1e7b14aded6550b1ffbeaaf45a8158ce')
peer_verification=fixed(PEER+'verification.json',760,'3d7c6a3914c340f2bfdd5a1e3dd1327d2114a857a2fb444327d90378e2e2a01b')
grant_raw=fixed(GRANT,9003,'5cae443d9a4e7250c083d7b97268e4a57d46da0d714f3cb0c0ca16fe13c75bfe')
manifest,peer,grant=map(json.loads,(manifest_raw,peer_raw,grant_raw))
assert peer['sealed'] is True and peer['passed'] is True and peer['blocking_findings']==[]
assert len(manifest['actual_source_pins'])==32 and len(manifest['decoder_expected_witness_pins'])==38
data={name:read(name,p) for name,p in sorted(manifest['actual_source_pins'].items())}
subjects={'subject_source_manifest':pin(manifest_raw)}
for field,name in [('subject_producer','produce.py'),('subject_entry_seed','entry-seed.json'),('subject_cfg_core','cfg_core.py'),('subject_launcher','launch_once.py')]:
 subjects[field]=pin(data[BASE+name])
assert all(peer[k]==p for k,p in subjects.items())
cap_raw=read(R86+'capture.json',{'bytes':85315,'sha256':'e3a06664b11a14f483705cd3ae4852b0cd562a85ab46ac7395bfc428673bb28f'})
owned_raw=read(R86+'owned-code.json',{'bytes':635,'sha256':'65d0c63efdc37f369bb8aa4f0f55a0a5c3d59c79db8bc37e98723a30048fde82'})
cap=json.loads(cap_raw);owned=json.loads(owned_raw)
rows=cap['analysis']['instructions']
assert len(rows)==20 and rows[17]['bytes']=='0f84cd000000' and rows[19]['bytes']=='482bca'
assert rows[13]['bytes']=='48c1f803' and rows[14]['bytes']=='49b8ffffffffffffff1f'
assert 0xcc259+6+int.from_bytes(bytes.fromhex('cd000000'),'little',signed=True)==0xcc32c
assert 0xcc263+3==0xcc266
normal_max=(1<<60)-1;negative_min=(1<<64)-(1<<60);comparison=(1<<61)-1
assert normal_max<comparison<negative_min
window={'begin':'0xcc266','end_exclusive':'0xcc366','bytes':256,'seeds':['0xcc266','0xcc32c']}
assert manifest['fixed_raw_window']==grant['fixed_raw_window']==window
assert grant['explicit_gap_policy_delta']['cc32c_pdata_gap_allowed'] is True
assert grant['explicit_gap_policy_delta']['cc266_pdata_gap_allowed'] is False
assert grant['metadata']['fixed_indices']==list(range(1251,1260))
assert 1024+(0xcc266-0x1000)==833126
assert 36909056+1251*12==36924068 and (1259-1251+1)*12==108
assert cap['next']['index']==1253 and cap['next']['raw_hex']=='66c20c008cc20c0028dddc01'
assert 0x1000<=0xcc266<0xcc366<=0x1b65e00
before={x['path']:{k:x[k] for k in ('bytes','sha256')} for x in journal}
for name,p in sorted(before.items()):read(name,p)
assert used+MANUAL+PRIOR<CAP
OUT.mkdir()
findings={
 'schema':'EU4-R87-ROOT-RAW-FRONTIER-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
 'scope':'raw_dual_frontier_fixed_range_seed_only',**subjects,'fixed_raw_window':window,'gap_policy':grant['explicit_gap_policy_delta'],
 'source_peer_accepted_for_source_only':True,'subject_source_peer':triple(PEER+'findings.json',peer_raw),
 'subject_upstream_capture':triple(R86+'capture.json',cap_raw),'subject_upstream_owned':triple(R86+'owned-code.json',owned_raw),
 'seed_arithmetic':{'normal_cc266':'Last owned instruction cc263 size3 falls through to cc266.',
  'hypothetical_cc32c':'JE cc259 size6 + signed disp205 =cc32c; encoding target only.',
  'SAR3_unsigned_output_ranges':[['0x0',hex(normal_max)],[hex(negative_min),'0xffffffffffffffff']],
  'comparison':hex(comparison),'normal_JE_taken':False,
  'proof':'SAR64 by3 of any64bit difference yields either[0,2^60-1] or[2^64-2^60,2^64-1]. Subsequent MOVABS R8 and MOV RBX do not modify RAX before CMP. Constant2^61-1 lies strictly between the output ranges, so normal sequential ZF0; no dynamic reachability is claimed for the hypothetical seed.'},
 'static_file_mapping':{'code_file_begin':833126,'code_bytes':256,'metadata_file_begin':36924068,'metadata_records':9,'metadata_bytes':108,'cached_text_mapping_only':True,'pdata1253_expected_raw':'66c20c008cc20c0028dddc01'},
 'source_before_after_equal':True,'resources':{'formal_returned':used,'prior_failed_review_and_metadata_reads':PRIOR,'prior_small_read_allowance':MANUAL,'source_upper':used+MANUAL+PRIOR,'cap':CAP,'ordinary':4194304,'actual_sources':32,'engine_metadata_only':38},
 'limits':['Source peer is accepted as a fixed completed non-author witness; root independently verifies raw seed arithmetic, subjects and fixed range policy, not all peer source semantics a second time.',
 'R86 complete non-author actual acceptance is still a separate gate; this report does not promote its pending semantic/lifetime findings.',
 'Cached PE section/pdata locations are static mappings under the expected image identity; the future producer must freshly authenticate exact PE twice and validate its fixed nine records.',
 'cc32c gap permission is only the explicitly selected syntactic target, not a recovered function entry/extent/ABI or normal reachability.',
 'No new PE, engine body, decoder, game process, native action, request, tests or target program was executed.'],
 'own_prior_failure':{'kind':'Schema KeyError in self reviewer; no target program ran','preserved_record':triple('work/reports/war-peace-api-20261016-r87-root-raw-frontier-review-failure-r1/failure.json',failure_raw),'narrow_fix':'Only actual capture next key, plus cumulative failure accounting.'},
 'actual_authorized':False,'native_ready':False,'callable':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False}
fr=save('findings.json',findings)
sealed={'schema':'EU4-R87-ROOT-RAW-FRONTIER-MANIFEST/1','sealed':True,'source_pins':before,
 'owned_pins':{'findings.json':pin(fr)},'source_before_after_equal':True,'source_peer':triple(PEER+'findings.json',peer_raw),'actual_authorized':False}
mr=save('manifest.json',sealed)
receipt={'schema':'EU4-ROOT-RAW-FRONTIER-REVIEW-RECEIPT/1','sealed':True,'passed':True,'findings':triple(OUT.relative_to(ROOT).as_posix()+'/findings.json',fr),'manifest':triple(OUT.relative_to(ROOT).as_posix()+'/manifest.json',mr),'read_journal':journal,'source_upper':used+MANUAL+PRIOR,'actual_runs':0}
rr=save('receipt.json',receipt)
print(json.dumps({'findings':triple(OUT.relative_to(ROOT).as_posix()+'/findings.json',fr),'manifest':triple(OUT.relative_to(ROOT).as_posix()+'/manifest.json',mr),'receipt':triple(OUT.relative_to(ROOT).as_posix()+'/receipt.json',rr),'source_upper':used+MANUAL+PRIOR,'actual_runs':0},ensure_ascii=True))
