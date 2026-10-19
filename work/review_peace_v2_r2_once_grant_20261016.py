"""Root file-only issuance; never imports a subject or reads real configuration."""
from pathlib import Path
import datetime, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
HERE = 'work/reports/peace-current-pending-v2-live-controller-20261016-r2/'
PEER = 'work/reports/peace-current-pending-v2-live-controller-source-independent-review-20261016-r2/'
BUILD = 'work/reports/peace-current-pending-v2-text-config-source-authorization-20261016-r1/authorization.json'
PREP = 'work/reports/peace-current-pending-v2-config-pin-preparation-20261016-r1/preparation.json'
IDENTITY = 'work/reports/peace-current-pending-v2-live-identity-preparation-20261016-r1/identity.json'
OUT = ROOT/'work/reports/peace-current-pending-v2-root-once-live-authorization-20261016-r2'
CAP = 8388608
MANUAL_ALLOWANCE = 1048576
journal = []
total = 0

def pin(raw):
    return {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}

def read(name, expected=None):
    global total
    p = ROOT/name
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert p.resolve().is_relative_to(ROOT.resolve())
    size = p.stat().st_size
    assert 0 <= size <= 4194304 and total+size+1+MANUAL_ALLOWANCE <= CAP
    with p.open('rb') as f:
        raw = f.read(size+1)
    total += len(raw)
    actual = pin(raw)
    assert len(raw) == size
    if expected is not None:
        assert actual == expected, name
    journal.append({'path':name, **actual})
    return raw

def fixed(name, size, sha):
    return read(name, {'bytes':size, 'sha256':sha})

def triple(name, raw):
    return {'path':name, **pin(raw)}

def parse(raw):
    def pairs(values):
        out = {}
        for k,v in values:
            assert k not in out
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs)

manifest_raw = fixed(HERE+'source-manifest.json',8861,'803d619df53c33b8698e78283c3ad223a61319c87b4a40ccaae732997d225127')
peer_raw = fixed(PEER+'findings.json',5817,'4e38a2083274e8e82825ad63f0e50b7dc7ae3c90858703742341db33e3da31d7')
peer_manifest_raw = fixed(PEER+'manifest.json',13944,'c80ea76a7847b55613672b0a7fbf0fd24dc13d91b8a3e4fba868d68737af1086')
build_raw = fixed(BUILD,6172,'58e3ab5f51a73c47e0b1119f9554712c91e34f5289ca228e339cb0f2c9e33d50')
prep_raw = fixed(PREP,674,'aa9d27c365c756163df0a714cde519b3a8f36ee6a4f1a7c960ec427f0160b7ae')
identity_raw = fixed(IDENTITY,680,'43857801707019c05f1e30387c9b4aa26d8acb6d6f2723c676c9798cbb029bf3')
manifest, peer, build, prep = map(parse,(manifest_raw,peer_raw,build_raw,prep_raw))
assert manifest['sealed'] is True and manifest['schema']=='EU4-PEACE-V2-CONTROLLER-SOURCE/2'
assert peer['sealed'] is True and peer['passed'] is True and peer['blocking_findings']==[]
assert build['source_build_only'] is True and build['runtime_authorized'] is False
assert len(manifest['source_pins'])==34
sources = {name:read(name,p) for name,p in sorted(manifest['source_pins'].items())}
subjects = {'subject_source_manifest':triple(HERE+'source-manifest.json',manifest_raw)}
for field,name in [('subject_controller_pin','controller.py'),('subject_child_pin','child.py'),('subject_adapter_pin','text_config_adapter.py')]:
    subjects[field]=triple(HERE+name,sources[HERE+name])
assert all(peer[k]==v for k,v in subjects.items())
for name,p in build['fixed_inputs'].items():
    assert pin(sources[name])==p
config = {'path':'local.env','bytes':226,'sha256':'84abda5840824badc9fd5daef7f5faedd61e5c2a01e329843b2bd5a5caeb7658'}
assert prep['local_configuration_pin']==config
assert build['selection']=={'pid':98548,'creation':'01dd5d0e670312c4','actor':'FRA','target':'ENG'}

# Exact source and selected witness post-read; no real env/PE/process access.
before = {entry['path']:{k:entry[k] for k in ('bytes','sha256')} for entry in journal}
for name,p in sorted(before.items()):
    read(name,p)
assert total+MANUAL_ALLOWANCE <= CAP
assert not (ROOT/HERE/'run-authorization.json').exists()
assert not OUT.exists()
OUT.mkdir()
authorization = {
 'schema':'EU4-PEACE-V2-CURRENT-STATUS-ONCE/2','sealed':True,'live_authorized':True,
 'executor':'/root/diplomacy_static','operation':'status','maximum_status_attempts':1,'automatic_retry':False,
 'issued_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'selection':build['selection'],'budgets':build['future_live_budget_design'],
 'build_authorization':triple(BUILD,build_raw), **subjects,
 'source_peer_review':{'findings':triple(PEER+'findings.json',peer_raw),'manifest':triple(PEER+'manifest.json',peer_manifest_raw)},
 'local_configuration_pin':config,
 'root_configuration_pin_preparation':triple(PREP,prep_raw),
 'prior_process_metadata_preparation':triple(IDENTITY,identity_raw),
 'UI_preparation':{'normal_main_screen':True,'player':'FRA','date':'1445-05-19','observed_paused':True,'not_a_world_lease':True,'UI_input_in_this_authorization':0},
 'permissions':{'current_readonly_status_once':True,'query_process':True,'game_VM_READ':True,'known_exact_target_disk_hash_and_entry_header':True,'game_write_native_Frida_hooks_requests':False,'UI_saves_reloads_time_advance':False,'PID_TAG_or_directory_substitution_retry':False},
 'root_scope':'New reviewed text configuration adapter profile; original R1 UNKNOWN/zero-RPM attempt and all old action claims remain frozen. This is the first and sole runtime attempt of the new source graph, not a renamed retry of unchanged code.',
 'limitations':[
  'Root checked the fixed source graph and exact non-author findings/subjects; the peer manifest is pinned as a witness, not recursively reaudited here.',
  'Only known intercepted Python read/readinto/readline/iteration routes are metered; read1/raw/fileno-os.read/mmap/native/OS/import/cache and unread initializer coverage are not universally proved. Any required uncovered route must remain unknown.',
  'Exact ROOT/local.env snapshot pin and syntax adapter are separately required; no configuration content/value is recorded or displayed. This is not arbitrary downstream value secrecy or whole-environment compatibility proof.',
  'Job45s/768MiB/output acceptance and byte/request budgets are independent; fail closed without automatic retry or budget expansion.',
  'Previous metadata and screenshots are not a live lease. Frozen CLI must authenticate held process/path/creation/root/code/table/handles/queues freshly.',
  'Presence/absence is selected current inbox only; no original request/effect/AI acceptance/rejection/settlement/peace completion/persistence/retry is proved.',
  'Normal context exit and heldNone do not prove OS CloseHandle return; before/after equality does not prove atomicity or absence of ABA.'
 ]
}

def write_once(path,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
    with path.open('xb') as f:
        f.write(raw)
    return raw

auth_raw=write_once(ROOT/HERE/'run-authorization.json',authorization)
write_once(OUT/'authorization-copy.json',authorization)
receipt={
 'schema':'EU4-ROOT-EXACT-SOURCE-ONCE-GRANT-ISSUANCE/2','sealed':True,'passed':True,
 'authorization':triple(HERE+'run-authorization.json',auth_raw),
 'subject_review':triple(PEER+'findings.json',peer_raw),'subject_manifest':subjects['subject_source_manifest'],
 'source_before_after_equal':True,'source_read_journal':journal,
 'resources':{'formal_returned':total,'prior_small_file_read_allowance':MANUAL_ALLOWANCE,'upper':total+MANUAL_ALLOWANCE,'cap':CAP,'ordinary_file_cap':4194304},
 'operations':{'subject_import_execute':0,'real_env_operations_in_issuance':0,'PE_game_process_UI_native_requests_tests':0,'grant_created':1},
 'limits':'Raw configuration was pinned in the separately retained root preparation stage; this issuance reads only its JSON metadata. This is not a runtime result.'
}
receipt_raw=write_once(OUT/'receipt.json',receipt)
print(json.dumps({'authorization':triple(HERE+'run-authorization.json',auth_raw),'receipt':triple(OUT.relative_to(ROOT).as_posix()+'/receipt.json',receipt_raw),'source_upper':total+MANUAL_ALLOWANCE,'runtime_attempts':0},ensure_ascii=True))
