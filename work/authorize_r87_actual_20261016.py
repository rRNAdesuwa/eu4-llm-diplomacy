"""Root accepts R86's completed raw review and binds one new static R87 job."""
from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
REV='work/reports/war-peace-api-20261016-r86-actual-independent-review/'
RAW='work/reports/war-peace-api-20261016-r87-root-raw-frontier-review/'
PEER='work/reports/war-peace-api-20261016-r87-source-independent-review/'
BUILD='work/reports/war-peace-api-20261016-r87-root-source-authorization/authorization.json'
OUT=ROOT/'work/reports/war-peace-api-20261016-r87-root-actual-authorization'
ACC=ROOT/'work/reports/war-peace-api-20261016-r86-root-actual-acceptance'
assert not OUT.exists() and not ACC.exists() and not (ROOT/BASE/'run-authorization.json').exists()
used=0;journal=[];CAP=8388608;MANUAL=524288
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(name,p=None):
 global used
 path=ROOT/name;size=path.stat().st_size
 assert 0<=size<=4194304 and used+size+1+MANUAL<=CAP
 with path.open('rb') as f:b=f.read(size+1)
 used+=len(b);assert len(b)==size
 if p is not None:assert pin(b)==p,name
 journal.append({'path':name,**pin(b)});return b
def fixed(n,s,h):return read(n,{'bytes':s,'sha256':h})
def triple(n,b):return {'path':n,**pin(b)}
def save(path,o):
 b=(json.dumps(o,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
 with path.open('xb') as f:f.write(b)
 return b
full_raw=fixed(REV+'findings.json',5580,'550c1edf7beee1ea7e5ae8e85f40c7ef556ede12bb27e2e6a4c8b1e5c2bad726')
full_manifest=fixed(REV+'manifest.json',12748,'5af832bd1e1be4d3a4cf7656d51b905f799e5d06215cd75ecb078798656d49dc')
fixed(REV+'precision-corrigendum.json',1713,'2c4fab900dd774369a40507a0414fb6a81c2d1cf451505d9b91c5726ebb83304')
fixed(REV+'pincheck.json',14219,'e67988e368d3858516ab96c513a8a89fff277f961532ddd04898770b57c6c0d8')
fixed(REV+'completion.json',2283,'2157141f8c2f2d932e63188e6b7425f0308d40400a5c5220296192ac48aa0af7')
raw_review=fixed(RAW+'findings.json',5243,'3cf18ea8a747889196e2fd7135d57f59812624b58dc9e938805c86a5c2b8059c')
raw_manifest=fixed(RAW+'manifest.json',7876,'b01c759c350e13d9fbe9949286e10fa2a452f3a098edb911a973e84be474d477')
peer_raw=fixed(PEER+'findings.json',6026,'73c9edd7d2447e7535b9d7760a11144071bdd5c9e2b47149d02cc7f4fa6eac68')
peer_manifest=fixed(PEER+'manifest.json',12733,'5201657ca1983b86555b70e1dc91d62f1e7b14aded6550b1ffbeaaf45a8158ce')
build_raw=fixed(BUILD,9003,'5cae443d9a4e7250c083d7b97268e4a57d46da0d714f3cb0c0ca16fe13c75bfe')
manifest_raw=fixed(BASE+'source-manifest.json',26330,'e40ccf4eba10b12b7d626f0fc00b1bcdac50972d1a0a35559ba3756b64694817')
full,raw,peer,build,manifest=map(json.loads,(full_raw,raw_review,peer_raw,build_raw,manifest_raw))
for r in (full,raw,peer):assert r['sealed'] is True and r['passed'] is True and r['blocking_findings']==[]
assert full['native_ready'] is False and full['ownership_transfer_verified'] is False
for field in ('subject_actual_manifest','subject_capture_pin','subject_contract_pin','subject_owned_pin'):
 ref=full[field];read(ref['path'],{k:ref[k] for k in ('bytes','sha256')})
data={n:read(n,p) for n,p in sorted(manifest['actual_source_pins'].items())}
subjects={'subject_source_manifest':pin(manifest_raw)}
for field,n in [('subject_producer','produce.py'),('subject_entry_seed','entry-seed.json'),('subject_cfg_core','cfg_core.py'),('subject_launcher','launch_once.py')]:subjects[field]=pin(data[BASE+n])
assert all(peer[k]==p and raw[k]==p for k,p in subjects.items())
assert raw['scope']=='raw_dual_frontier_fixed_range_seed_only'
assert raw['fixed_raw_window']==manifest['fixed_raw_window']==build['fixed_raw_window']
assert raw['gap_policy']==build['explicit_gap_policy_delta']
before={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in journal}
for n,p in sorted(before.items()):read(n,p)
assert used+MANUAL<CAP
ACC.mkdir();OUT.mkdir()
acceptance={'schema':'EU4-R86-ROOT-COMPLETE-ACTUAL-ACCEPTANCE/1','sealed':True,'accepted':True,
 'subject_full_review':triple(REV+'findings.json',full_raw),'subject_actual_manifest':full['subject_actual_manifest'],
 'accepted_scope':'Exact70B/20-row fragment and independent SAR3 precision; source/metadata/close-order producer witnesses. Normal path exits at unread cc266, hypothetical JE not value-feasible.',
 'independent_raw_review_used':True,'root_did_not_repeat_full_flat_PE_engine_review':True,
 'native_ready':False,'callable':False,'reader_adoption_allowed':False,'ownership_transfer_verified':False,'world_lease':False,'atomic_snapshot':False,'further_actual_authorized_by_this_acceptance':False}
acc_raw=save(ACC/'findings.json',acceptance)
auth={'schema':'EU4-R87-FIXED-DUAL-SEED-ROOT-AUTHORIZATION/1','sealed':True,'root_explicit_start_received':True,'single_attempt':True,
 'operation':'one-fixed-dual-frontier-static','issued_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'source_manifest':subjects['subject_source_manifest'],'producer_pin':subjects['subject_producer'],'entry_seed_pin':subjects['subject_entry_seed'],
 'cfg_core_pin':subjects['subject_cfg_core'],'launcher_pin':subjects['subject_launcher'],
 'source_build_authorization':triple(BUILD,build_raw),'fixed_raw_window':build['fixed_raw_window'],
 'seed_semantics':{'0xcc266':'normal_sequential_frontier','0xcc32c':'hypothetical_syntactic_target_not_normal_from_cc220'},
 'metadata':build['metadata'],'gap_policy':build['explicit_gap_policy_delta'],'Job':build['Job'],'source_limits':build['source_limits'],
 'target_limits':build['future_target_limits'],
 'upstream_R86_full_review':{'findings':triple(REV+'findings.json',full_raw),'manifest':triple(REV+'manifest.json',full_manifest)},
 'upstream_R86_root_acceptance':triple(ACC.relative_to(ROOT).as_posix()+'/findings.json',acc_raw),
 'root_raw_frontier_review':{'findings':triple(RAW+'findings.json',raw_review),'manifest':triple(RAW+'manifest.json',raw_manifest)},
 'source_peer_review':{'findings':triple(PEER+'findings.json',peer_raw),'manifest':triple(PEER+'manifest.json',peer_manifest)},
 'execution_boundary':'Root launches only exact launch_once.py with this sole SHA argument under its reviewed owned Job; source full SHA guards and permanent launcher/producer claims apply. No retry or alternate directory/seed/range.',
 'limits':['Only fixed binary file reads and ordinary locked Capstone acquisition; not a native game call or REA deep-engine EvidenceID.',
 'cc32c is hypothetical/syntactic only and not normally reached after R86 SAR3. Pdata gap exception grants no function/ABI/extent or lifetime proof.',
 'All external/indirect edges and callee effects remain conditional/unknown. No following callees/data/vtables/header/unwind or new range.',
 'Known intercepted source/engine reads and exact PE accounting only; incomplete OS/loader/partial failure IO remains disclosed. Job writer may overshoot before refusal.'],
 'native_ready':False,'callable':False,'reader_adoption_allowed':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,
 'game_process_accesses_authorized':False,'Frida_native_requests_UI_saves_reloads_authorized':False,'automatic_retry':False}
auth_raw=save(ROOT/BASE/'run-authorization.json',auth)
save(OUT/'authorization-copy.json',auth)
receipt={'schema':'EU4-R87-ROOT-ONCE-GRANT-ISSUANCE/1','sealed':True,'passed':True,
 'authorization':triple(BASE+'run-authorization.json',auth_raw),'upstream_acceptance':triple(ACC.relative_to(ROOT).as_posix()+'/findings.json',acc_raw),
 'source_before_after_equal':True,'source_returned':used,'manual_allowance':MANUAL,'upper':used+MANUAL,'cap':CAP,'read_journal':journal,'target_actual_executions_in_issuance':0}
rr=save(OUT/'receipt.json',receipt)
print(json.dumps({'authorization':triple(BASE+'run-authorization.json',auth_raw),'R86_acceptance':triple(ACC.relative_to(ROOT).as_posix()+'/findings.json',acc_raw),'receipt':triple(OUT.relative_to(ROOT).as_posix()+'/receipt.json',rr),'source_upper':used+MANUAL},ensure_ascii=True))
