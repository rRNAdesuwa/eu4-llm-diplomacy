"""Root binds the complete support controller source peer; no process/config access."""
from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1]
BASE='work/reports/support-heir-current-live-controller-20261016-r1/'
PEER='work/reports/support-heir-current-controller-source-independent-review-20261016-r1/'
BUILD='work/reports/support-heir-current-controller-source-authorization-20261016-r1/authorization.json'
OUT=ROOT/'work/reports/support-heir-current-root-once-authorization-20261016-r1'
assert not OUT.exists() and not (ROOT/BASE/'run-authorization.json').exists()
used=0;journal=[];CAP=8388608;MANUAL=524288
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(n,p=None):
 global used
 path=ROOT/n;s=path.stat().st_size
 assert 0<=s<=4194304 and used+s+1+MANUAL<=CAP
 with path.open('rb') as f:b=f.read(s+1)
 used+=len(b);assert len(b)==s
 if p is not None:assert pin(b)==p,n
 journal.append({'path':n,**pin(b)});return b
def fixed(n,s,h):return read(n,{'bytes':s,'sha256':h})
def triple(n,b):return {'path':n,**pin(b)}
def save(path,o):
 b=(json.dumps(o,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
 with path.open('xb') as f:f.write(b)
 return b
mr=fixed(BASE+'source-manifest.json',16257,'3d70675a5901635a00efd6415ac93ead4b4dcadc726df1a6f4f065b864bb20f7')
pr=fixed(PEER+'findings.json',36102,'99e4496a5362d4b34089a3d9843133c34963ffbc5cd7acee160e88a3ffffd0a8')
pm=fixed(PEER+'manifest.json',33412,'a39124ca367c79ee2a068641da9bb68e2d446917b45af9bb0a879a056a5e3367')
fixed(PEER+'verification.json',25019,'f49e428b1d7f0ffdbce67556585de4999aa4da45815de06d39f78c9448322aa2')
br=fixed(BUILD,10852,'79ecd0456ecd8d99a8bc215313e610cc297be2075ae0042d2a12a76415cdd3a9')
m,p,b=map(json.loads,(mr,pr,br))
assert p['sealed'] is True and p['passed'] is True and p['blocking_findings']==[]
assert m['sealed'] is True and m['runtime_grant_required'] is True and len(m['source_pins'])==49
data={n:read(n,v) for n,v in sorted(m['source_pins'].items())}
subjects={'subject_source_manifest':triple(BASE+'source-manifest.json',mr)}
for field,n in [('subject_controller_pin','controller.py'),('subject_child_pin','child.py'),('subject_adapter_pin','text_config_adapter.py')]:subjects[field]=triple(BASE+n,data[BASE+n])
assert all(p[k]==v for k,v in subjects.items())
assert m['fixed_inputs']==b['fixed_inputs']
assert b['selection']=={'pid':98548,'creation':'01dd5d0e670312c4','actor':'FRA','target':'POL'}
assert b['local_configuration_pin_metadata']=={'path':'local.env','bytes':226,'sha256':'84abda5840824badc9fd5daef7f5faedd61e5c2a01e329843b2bd5a5caeb7658'}
before={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in journal}
for n,v in sorted(before.items()):read(n,v)
assert used+MANUAL<CAP
OUT.mkdir()
auth={'schema':'EU4-SUPPORT-HEIR-CURRENT-STATUS-ONCE/1','sealed':True,'live_authorized':True,
 'executor':'/root/diplomacy_static','issued_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'operation':'status','maximum_status_attempts':1,'automatic_retry':False,
 'selection':b['selection'],'budgets':b['future_live_budget_design'],'build_authorization':triple(BUILD,br),**subjects,
 'source_peer_review':{'findings':triple(PEER+'findings.json',pr),'manifest':triple(PEER+'manifest.json',pm)},
 'local_configuration_pin':b['local_configuration_pin_metadata'],
 'permissions':{'current_readonly_status_once':True,'held_process_QUERY_VM_READ':True,'exact_known_game_disk_stream':True,'native_Frida_write_requests_UI_saves_reloads':False,'PID_TAG_or_directory_substitution_retry':False},
 'limits':['Current FRA-POL support-task index presence/absence only, never original support/stop request, AI response, final heir, effects or persistence.',
 'Fresh held identity/path/creation/paused world/code/country/handles/indices and source prepost checks remain mandatory; prior screenshots/results are not a lease.',
 'Entry8192 is frozen source declaration outside shared raw journal4096/512KiB; do not turn it into an actual raw record or a complete all-RPM claim.',
 'Actual intercepted game hashes N1..3 must each reach full exact SHA/EOF/normal close and returned=N*38462504. Never add reads to manufacture three hashes.',
 'Exact root config snapshot pin is verified before private decode; no contents/values logged. Old config prep metadata is not interval stability or an atomic proof.',
 'OS CloseHandle return and full OS/import/cache/delegated IO/ABA/lease/complete CPP class remain unproved; all unknown outcomes freeze without retry.'],
 'native_ready':False,'selected_effect_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_action_retry':False}
ar=save(ROOT/BASE/'run-authorization.json',auth);save(OUT/'authorization-copy.json',auth)
receipt={'schema':'EU4-SUPPORT-CURRENT-ROOT-ONCE-ISSUANCE/1','sealed':True,'passed':True,
 'authorization':triple(BASE+'run-authorization.json',ar),'accepted_source_peer':triple(PEER+'findings.json',pr),
 'source_before_after_equal':True,'source_returned':used,'prior_small_read_allowance':MANUAL,'source_upper':used+MANUAL,'source_cap':CAP,
 'read_journal':journal,'operations':{'author_import_execute':0,'real_env_PE_engine_process_UI_native_requests_tests':0,'status_attempts_in_issuance':0},
 'scope':'Exact49 source graph and complete independent source-peer subject acceptance; no recursive old-host/PE/source-case reexecution.'}
rr=save(OUT/'receipt.json',receipt)
print(json.dumps({'authorization':triple(BASE+'run-authorization.json',ar),'receipt':triple(OUT.relative_to(ROOT).as_posix()+'/receipt.json',rr),'source_upper':used+MANUAL},ensure_ascii=True))
