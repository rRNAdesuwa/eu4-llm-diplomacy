"""Root's explicit 43-step stopped ledger. Freezes evidence; never reviews or calls game."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/runtime/native1375-v14/'
SESSION = BASE + 'session-18356-01dd56aa6f724ea8/'
PID, CREATION, EXIT = 18356, '01dd56aa6f724ea8', 134358881451683426

# Every sequence, action, capture and known result is chosen explicitly by root.
# Never infer a successful action, most-recent legality, or filename from log rows.
PAIRS = [
    (2,'embargo','legality','published','legality_allowed'),
    (3,'embargo','submit','published','dispatched'),
    (4,'revoke-embargo','legality','published','legality_rejected'),
    (6,'revoke-embargo','legality','published','legality_allowed'),
    (7,'revoke-embargo','submit','published','dispatched'),
    (9,'give-subsidies','legality','published','legality_allowed'),
    (10,'give-subsidies','submit','published','dispatched'),
    (12,'offer-fleet','legality','published','legality_allowed'),
    (13,'offer-fleet','submit','published','dispatched'),
    (15,'ask-fleet','legality','published','legality_allowed'),
    (16,'ask-fleet','submit','published','dispatched'),
    (18,'cancel-fleet','legality','published','legality_allowed'),
    (19,'cancel-fleet','submit','published','dispatched'),
    (21,'offer-military','legality','published','legality_allowed'),
    (22,'offer-military','submit','published','dispatched'),
    (24,'alliance','legality','','legality_allowed'),
    (25,'alliance','submit','','dispatched'),
    (27,'offer-military-after-alliance','legality','','legality_allowed'),
    (28,'offer-military-after-alliance','submit','','dispatched'),
    (30,'revoke-military','legality','','legality_allowed'),
    (31,'revoke-military','submit','','dispatched'),
    (33,'ask-military','legality','','legality_allowed'),
    (34,'ask-military','submit','','dispatched'),
    (36,'cancel-military','legality','','legality_allowed'),
    (37,'cancel-military','submit','','dispatched'),
    (39,'cancel-subsidies','legality','','legality_allowed'),
    (40,'cancel-subsidies','submit','','dispatched'),
    (42,'dissolve-alliance','legality','','legality_allowed'),
    (43,'dissolve-alliance','submit','','dispatched'),
]
ACTIONS = dict(embargo='embargo', **{
    'revoke-embargo':'revoke_embargo', 'give-subsidies':'give_subsidies',
    'offer-fleet':'offer_fleet_basing_rights','ask-fleet':'ask_fleet_basing_rights',
    'cancel-fleet':'cancel_fleet_basing_rights','offer-military':'offer_military_access',
    'offer-military-after-alliance':'offer_military_access','alliance':'offer_alliance',
    'revoke-military':'revoke_military_access','ask-military':'ask_military_access',
    'cancel-military':'cancel_military_access','cancel-subsidies':'cancel_subsidies',
    'dissolve-alliance':'dissolve_alliance'})
SPEEDS = (5,8,11,14,17,20,23,26,29,32,35,38,41)
EFFECTS = ((3,'embargo',True),(7,'revoke-embargo',True),
           (10,'give-subsidies',True),(13,'offer-fleet',False),
           (19,'cancel-fleet',True),(31,'revoke-military',True),
           (37,'cancel-military',True),(40,'cancel-subsidies',True),
           (43,'dissolve-alliance',True))

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def read(name):
    p=ROOT/name
    require(p.resolve().is_relative_to(ROOT.resolve()) and not p.is_symlink(), 'Indirect/outside input')
    with p.open('rb') as f: raw=f.read(8*1024*1024+1)
    require(0<len(raw)<=8*1024*1024,'Input size budget')
    return raw

def descriptor(name):
    raw=read(name)
    return dict(path=name,size_bytes=len(raw),sha256=digest(raw))

def new_json(name,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    with (ROOT/name).open('xb') as f:f.write(raw);f.flush()
    return descriptor(name)

def main():
    inputs={};by_path={}
    def add(key,path,expected=None):
        if path in by_path:return by_path[path]
        d=descriptor(path)
        if expected is not None:require(d==expected,'Pinned preflight evidence changed')
        require(key not in inputs,'Duplicate key')
        inputs[key]=d;by_path[path]=key;return key
    def capture(key,filename):return dict(input=add(key,BASE+filename),select=['report'])
    exit_key=add('exit',BASE+'directional-process-exit-18356.json')
    exit_row=json.loads(read(inputs[exit_key]['path']))
    require(exit_row['pid']==PID and exit_row['creation']==CREATION
            and exit_row['process_exit_filetime']==EXIT and type(exit_row['exit_code']) is int
            and exit_row['exit_code']==0 and exit_row['exit_observed'] is True,'Exact stopped process required')
    files={}
    directory=ROOT/SESSION
    for index,p in enumerate(sorted(directory.iterdir(),key=lambda x:x.name)):
        require(p.is_file() and not p.is_symlink() and not p.is_junction(),'Unexpected session entry')
        files[p.name]=add('session'+str(index),SESSION+p.name)
    audit=dict(pid=PID,creation=CREATION,process_exit_filetime=EXIT,
        complete_log=inputs[files['research-1375.jsonl']],
        session_files={n:inputs[k] for n,k in files.items()},stopped=True)
    audit_path=BASE+'directional-stopped-audit-18356.json'
    require(not (ROOT/audit_path).exists(),'Stopped projection must be new')
    new_json(audit_path,audit);add('stopped_audit',audit_path)
    pre_case=add('preflight_case',BASE+'directional-preflight-case-18356.json')
    add('preflight_summary',BASE+'directional-preflight-summary-18356.json')
    for index,d in enumerate(json.loads(read(inputs[pre_case]['path']))['inputs'].values()):
        add('preinput'+str(index),d['path'],d)
    ledger={1:dict(sequence=1,request=dict(operation='fixture',mode='submit',action='fixture_on',actor='FRA',target='FRA',speed=0),
        outcome='fixture_callback_returned',legality_sequence=None,
        publication=capture('publication1','directional-fixture-published-18356-seq1.json'),
        status=capture('status1','directional-fixture-health-18356-seq1.json'))}
    for seq,name,mode,suffix,outcome in PAIRS:
        stem='directional-'+name+'-'+mode
        pub=stem+('-'+suffix if suffix else '')+'-18356-seq'+str(seq)+'.json'
        status=stem+'-result-18356-seq'+str(seq)+'.json'
        ledger[seq]=dict(sequence=seq,request=dict(operation='pair',mode='submit' if mode=='submit' else 'legality_only',
            action=ACTIONS[name],actor='FRA',target='POR',speed=0),outcome=outcome,
            legality_sequence=seq-1 if mode=='submit' else None,
            publication=capture('publication'+str(seq),pub),status=capture('status'+str(seq),status))
    for seq in SPEEDS:
        ledger[seq]=dict(sequence=seq,request=dict(operation='speed',mode='submit',action='none',actor='FRA',target='FRA',speed=1),
            outcome='completed_and_paused',legality_sequence=None,
            publication=capture('publication'+str(seq),'directional-speed-18356-seq'+str(seq)+'.json'),
            status=capture('status'+str(seq),'directional-health-after-speed-18356-seq'+str(seq)+'.json'))
    require(sorted(ledger)==list(range(1,44)), 'Explicit 43-entry coverage differs')
    effects=[]
    for seq,name,positive in EFFECTS:
        refs={kind:add('effect'+str(seq)+'_'+kind,BASE+'directional-'+name+'-'+kind+'-18356.json')
              for kind in ('before','after','comparison')}
        effects.append(dict(sequence=seq,**refs,expected_observed_effect=positive))
    annotations=[dict(sequence=seq,source='root_ui_annotation',native_evidence=False,text=text)
        for seq,text in ((13,'Root inspected POR refusal notification for offered fleet basing and clicked OK.'),
                         (22,'Root inspected POR refusal notification for offered military access and clicked OK.'),
                         (28,'New proposal after alliance formed; observed granted military access. Does not prove alliance was necessary.'))]
    case=dict(schema_version=1,purpose='v14_directional_finalized_experiment_case',finalized=True,inputs=inputs,
        exit=dict(input=exit_key,select=[]),stopped_audit=dict(input='stopped_audit',select=[]),
        preflight_case='preflight_case',preflight_summary='preflight_summary',session_files=files,
        final_status=capture('final_status','directional-final-health-18356-seq43.json'),
        requests=[ledger[s] for s in range(1,44)],effects=effects,annotations=annotations,persistence=[])
    require(len(inputs)<=512 and sum(d['size_bytes'] for d in inputs.values())<=64*1024*1024,'Inventory budget')
    for d in inputs.values():require(descriptor(d['path'])==d,'Evidence changed before freeze')
    result=new_json(BASE+'directional-finalized-case-18356.json',case)
    print(json.dumps(dict(status='explicit_case_frozen_not_reviewed',case=result,complete_log=audit['complete_log'],
        inputs=len(inputs),session_files=len(files),requests=43,selected_submits=9,expected_selected_effects=8,
        game_accessed=False,capability_promoted=False)))

if __name__=='__main__':main()
