"""Fixed manual UI batch: bounded files and typed selected-state observations only."""
import argparse
import ast
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PID=38232
CREATION='01dd56e0cbe2c7f7'
WORLD=0x1a0cb39c020
DATE=56456976
INITIAL_SHA='d31f3c1335569659fd42ba59ddb3a70c2d364e8315f003e7d75488822b2b01fb'
PATHS={'before':'work/runtime/subject-and-curry-ui-batch-ro-38232-before_ui.json',
       'after':'work/runtime/subject-and-curry-ui-batch-ro-38232-after_ui.json',
       'journal':'work/runtime/subject-curry-ui-batch-38232.jsonl'}
PLAN=(('set_rival','BUR',True),('military_focus','NAV',5),('embargo_rivals','NAV',True),
      ('scutage','NAV',True),('divert_trade','NAV',True),('curry_favors','POR',True))
WRAPPER='work/sample_subject_and_curry_batch_ro_38232_1375.py'
JOURNAL_HELPER='work/record_subject_curry_ui_batch_38232_1375.py'
MAX_CENSUS=4*1024*1024
FALSE_OUTPUT=('native_request_receipt_verified','native_call_authorized','runtime_verified','execution_verified',
 'individual_effect_verified','request_causality_verified','rival_target_ro_verified','favors_amount_verified',
 'side_effects_verified','strict_single_player_verified','world_epoch_verified','object_lifetime_verified',
 'whole_world_unchanged_verified','save_reload_verified','production_ready')
PINS_SHA='d3301927ba378d89002e0762ea4ddda89d32b1ec65fa02cfb5eb33249628f712'
_DEPS=None

def require(value,message):
    if not value:raise ValueError(message)
def integer(value,lo=0,hi=2**64-1):
    require(type(value)is int and lo<=value<=hi,'strict bounded integer');return value
def exact(value,keys):require(type(value)is dict and set(value)==set(keys.split()),'exact fields')
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def same(a,b,reason):require(canonical(a)==canonical(b),reason)
def digest(value):
    require(type(value)is str and re.fullmatch('[0-9a-f]{64}',value),'SHA256');return value
def bounded(path,limit):
    path=Path(path);require(path.is_file() and not path.is_symlink(),'regular file')
    with path.open('rb')as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'file budget');return raw
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(262144),b''):h.update(block)
    return h.hexdigest()
def decode(raw):
    def pairs(values):
        result={}
        for key,value in values:require(key not in result,'duplicate JSON key');result[key]=value
        return result
    def fail(value):raise ValueError('nonfinite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=fail)
def verify_sources():
    raw=bounded(HERE/'input-pins.json',65536)
    require(hashlib.sha256(raw).hexdigest()==PINS_SHA,'source pin inventory')
    pins=decode(raw);require(type(pins)is dict and 1<=len(pins)<=64,'pin count')
    total=0
    for name,want in pins.items():
        require(type(name)is str and not Path(name).is_absolute() and '..'not in Path(name).parts,'source path')
        raw=bounded(ROOT/name,4*1024*1024);total+=len(raw);require(total<=24*1024*1024,'source total budget')
        require(hashlib.sha256(raw).hexdigest()==digest(want),'changed source '+name)
    return pins
def dependencies():
    global _DEPS
    if _DEPS is None:
        verify_sources();mods={}
        for key,name in [('curry','curry-favors'),('focus','subject-military-focus'),('toggles','subject-toggle')]:
            p=ROOT/f'work/candidates/{name}-observer-1375/observer.py'
            spec=importlib.util.spec_from_file_location('_subject_curry_review_'+key,p)
            m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            require(Path(m.__file__).resolve()==p.resolve() and m.ROOT==ROOT,'dependency origin')
            mods[key]=m
        mods['curry'].dependencies(mods['curry'].contract())
        mods['focus'].dependencies();mods['toggles'].dependencies(mods['toggles'].contract())
        tree=ast.parse(bounded(ROOT/WRAPPER,65536).decode('utf-8'))
        pins=next(ast.literal_eval(n.value)for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name)and x.id=='PINS'for x in n.targets))
        _DEPS=mods,pins
    return _DEPS
def budget(report,support):
    b=report['read_budget'];exact(b,'bytes calls max_bytes max_calls')
    integer(b['bytes'],1,support.MAX_TOTAL);integer(b['calls'],1,support.MAX_READS)
    integer(b['max_bytes'],support.MAX_TOTAL,support.MAX_TOTAL);integer(b['max_calls'],support.MAX_READS,support.MAX_READS)
    trace=report['trace'];require(type(trace)is list and len(trace)==b['calls'],'trace call count')
    total=0
    for row in trace:
        exact(row,'address size sha256');address=integer(row['address'],65536,2**47-1)
        size=integer(row['size'],1,support.MAX_SINGLE);require(address+size<=2**47,'trace span');digest(row['sha256']);total+=size
    require(total==b['bytes'],'trace byte total')
def held(process,base,toggle=False):
    if toggle:
        exact(process,'pid creation before after executable disk_exe_sha256 loaded_full_image_hash_verified rights')
        integer(process['pid'],PID,PID);require(type(process['creation'])is str and process['creation']==CREATION,'held creation')
        same(process['before'],process['after'],'held before/after identities')
        identity=process['before'];path=process['executable']
    else:
        exact(process,'identity path disk_exe_sha256 loaded_full_image_hash_verified rights')
        identity=process['identity'];path=process['path']
    exact(identity,'pid creation_filetime exit_filetime module_base')
    integer(identity['pid'],PID,PID);integer(identity['exit_filetime'],0,0)
    require(type(identity['creation_filetime'])is str and identity['creation_filetime']==CREATION,'exact held creation')
    integer(identity['module_base'],base,base)
    require(type(path)is str and path==str((ROOT.parent/'eu4.exe').resolve()),'exact held EXE path')
    mods,_=dependencies()
    require(process['disk_exe_sha256']==mods['focus'].EXE_SHA and process['loaded_full_image_hash_verified']is False,'disk/loaded hash scope')
    same(process['rights'],['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'],'read-only rights')
    return dict(identity=identity,path=path,disk_exe_sha256=process['disk_exe_sha256'],loaded_full_image_hash_verified=False,rights=process['rights'])
def reports(value):
    mods,_=dependencies();exact(value,'curry military_focus subject_toggles')
    curry,focus,toggle=value['curry'],value['military_focus'],value['subject_toggles']
    mods['curry'].inspect_capture(curry);mods['toggles'].validated_report(toggle)
    exact(focus,'profile static_report_sha256 snapshot two_pass_equal entitlement source_kind read_budget trace process '+' '.join(mods['focus'].FALSE_CLAIMS))
    require(focus['profile']=='subject_military_focus_ro_1375_1' and focus['static_report_sha256']==mods['focus'].REPORT_SHA,'focus profile')
    require(focus['two_pass_equal']is True and focus['entitlement']=='unsupported_tls_and_lazy_query','focus sampled/unsupported fields')
    require(all(focus[k]is False for k in mods['focus'].FALSE_CLAIMS),'focus authority false')
    mods['focus'].inspect(focus['snapshot'])
    identities=[curry['passes'][0]['identity'],focus['snapshot']['identity'],toggle['snapshot']['graph']['identity']]
    proc=[]
    for report,identity,is_toggle in zip((curry,focus,toggle),identities,(False,False,True)):
        require(report['source_kind']=='held_process_readonly','held report required')
        integer(identity['game'],WORLD,WORLD);integer(identity['date'],DATE,DATE)
        budget(report,mods['focus'].support);proc.append(held(report['process'],identity['base'],is_toggle))
    same(proc[0],proc[1],'common held scope');same(proc[0],proc[2],'common held scope')
    for identity in identities[1:]:
        same({k:v for k,v in identities[0].items()if k!='countries'},{k:v for k,v in identity.items()if k!='countries'},'common world/date/fullplayer')
        same(identities[0]['countries']['FRA'],identity['countries']['FRA'],'common full actor')
    require(identities[0]['countries']['POR']['address']!=identities[1]['countries']['NAV']['address'],'different target objects')
    # Same FRA+1510 field across samplers; target-specific record/root remain distinct.
    curry_records=integer(curry['passes'][0]['index']['records'],65536,2**47-1)
    subject_records=integer(focus['snapshot']['left']['records'],65536,2**47-1)
    require(curry_records==subject_records,'common FRA relationship records')
    same(focus['snapshot'],toggle['snapshot']['graph'],'same complete subject graph within census')
    require(focus['snapshot']['scope_status']=='direct_subject_graph_observed','fixed direct subject scope')
    return dict(curry=curry,focus=focus,toggle=toggle,process=proc[0])
def census(value,phase):
    exact(value,'kind phase pid creation world raw_date source_pins capture_helper_sha256 reports group_atomic game_native_calls game_memory_written individual_effect_verified production_ready native_request_receipt initial_reference_sha256 status')
    require(value['kind']=='fixed_subject_and_curry_ui_selected_census' and value['phase']==phase and value['status']=='captured','complete fixed census')
    integer(value['pid'],PID,PID);integer(value['world'],WORLD,WORLD);integer(value['raw_date'],DATE,DATE)
    require(type(value['creation'])is str and value['creation']==CREATION,'fixed creation')
    for key in ('group_atomic','game_native_calls','game_memory_written','individual_effect_verified','production_ready','native_request_receipt'):require(value[key]is False,'unsupported census claim')
    require(value['capture_helper_sha256']==verify_sources()[WRAPPER],'capture helper')
    _,pins=dependencies();same(value['source_pins'],pins,'producer source pins')
    if phase=='before_ui':require(value['initial_reference_sha256']is None,'initial reference must be null')
    else:require(value['initial_reference_sha256']==INITIAL_SHA,'after references exact initial')
    return reports(value['reports'])
def journal(rows):
    require(type(rows)is list and len(rows)==13,'exact six-action journal')
    last=None
    for i,row in enumerate(rows):
        extra='plan'if i==0 else'target requested_value'
        exact(row,'event action note recorded_utc pid creation world initial_sha256 actor source native_request_receipt individual_effect_verified production_ready '+extra)
        integer(row['pid'],PID,PID);require(type(row['creation'])is str and row['creation']==CREATION and row['world']==hex(WORLD),'journal identity')
        require(row['initial_sha256']==INITIAL_SHA and row['actor']=='FRA' and row['source']=='manual_game_ui_observation','manual source/pair')
        for k in ('native_request_receipt','individual_effect_verified','production_ready'):require(row[k]is False,'manual authority false')
        require(type(row['note'])is str and len(row['note'])<=1024,'note bound')
        require(type(row['recorded_utc'])is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?\+00:00',row['recorded_utc']),'UTC timestamp')
        stamp=datetime.fromisoformat(row['recorded_utc']);require(last is None or stamp>=last,'journal ordering');last=stamp
        if i==0:
            require(row['event']=='start' and row['action']is None,'start');same(row['plan'],PLAN,'fixed UI plan')
        else:
            action,target,value=PLAN[(i-1)//2]
            require(row['event']==('intent'if i%2 else'ui_confirmed') and row['action']==action and row['target']==target,'fixed intent/confirmation order')
            same(row['requested_value'],value,'typed requested value')
def review_records(before,after,rows):
    a=census(before,'before_ui');b=census(after,'after_ui');journal(rows);mods,_=dependencies()
    same(a['process'],b['process'],'same before/after held identity')
    focus=mods['focus'].compare_snapshots(a['focus']['snapshot'],b['focus']['snapshot'])
    require(focus['before_focus']==0 and focus['after_focus']==5 and focus['changed']is True,'focus0 to5')
    x,y=a['toggle']['snapshot'],b['toggle']['snapshot']
    for key in ('registrations','permission_map'):same(x[key],y[key],'fixed toggle registration/permission graph')
    # Cannot use old toggle.compare_snapshots: focus and rival_count really changed.
    # Full subject graph changes only focus, proved above and intra-census bound.
    for key in ('actor_presence','actor_marker','subject_at_war'):same(x['raw_fields'][key],y['raw_fields'][key],'unchanged selected local field')
    integer(x['raw_fields']['actor_rival_count'],0,0);integer(y['raw_fields']['actor_rival_count'],1,1)
    require((x['raw_fields']['subject_flags']^y['raw_fields']['subject_flags'])==0x52,'only selected subject bits changed')
    states={}
    for name in ('embargo_rivals','scutage','divert_trade'):
        require(x['states'][name]['current']is False and y['states'][name]['current']is True,'selected flag false totrue')
        require(x['states'][name]['definition_allows']is True and y['states'][name]['definition_allows']is True,'observed definition allows')
        require(y['states'][name]['family_local_condition']is True,'observed final local condition')
        states[name]={'before':False,'after':True,'individual_effect_verified':False,'side_effects_verified':False}
    curry=mods['curry'].compare_captures(a['curry'],b['curry'])
    require(curry['before']['complete_selected_absence']is True and curry['after']['active_graph_observed']is True and curry['after']['matching_missions']==1,'curry absent to unique linked graph')
    integer(b['curry']['passes'][0]['relation']['fields']['started'],DATE,DATE)
    return dict(schema=1,status='reviewed_manual_ui_selected_subject_and_curry_observation',
        identity=dict(pid=PID,creation=CREATION,world=WORLD,raw_date=DATE,actor='FRA'),
        manual_ui_actions=[list(x)for x in PLAN],military_focus=dict(before=0,after=5,individual_effect_verified=False),
        subject_flags=states,rival_count=dict(before=0,after=1,target='BUR',target_evidence='manual_UI_journal_only'),
        curry_graph=dict(before='selected_index_and_mission_absent',after='active_relation_mission_graph',matching_missions=1,individual_effect_verified=False),
        group_atomic=False,**{k:False for k in FALSE_OUTPUT})
def review_case(case_path,expected_sha,output):
    output=Path(output);require(not output.exists(),'CREATE_NEW output required');digest(expected_sha);verify_sources()
    raw=bounded(case_path,32768);require(hashlib.sha256(raw).hexdigest()==expected_sha,'case hash');case=decode(raw)
    exact(case,'schema purpose identity inputs');integer(case['schema'],1,1)
    require(case['purpose']=='fixed_subject_curry_ui_batch_r2_38232','case purpose')
    same(case['identity'],dict(pid=PID,creation=CREATION,world=WORLD,raw_date=DATE,actor='FRA',subject='NAV',curry_target='POR'),'case identity')
    exact(case['inputs'],'before after journal');blobs={}
    for key,path in PATHS.items():
        spec=case['inputs'][key];exact(spec,'path bytes sha256');require(spec['path']==path,'fixed case path');digest(spec['sha256'])
        limit=65536 if key=='journal'else MAX_CENSUS;integer(spec['bytes'],1,limit)
        require((ROOT/path).resolve()==(ROOT/path).absolute(),'no redirected input');data=bounded(ROOT/path,limit)
        require(len(data)==spec['bytes'] and hashlib.sha256(data).hexdigest()==spec['sha256'],'input hash before parse');blobs[key]=data
    require(case['inputs']['before']['sha256']==INITIAL_SHA,'exact initial census')
    require(blobs['journal'].endswith(b'\n') and len(blobs['journal'].splitlines())==13,'complete13 journal lines')
    result=review_records(decode(blobs['before']),decode(blobs['after']),[decode(x)for x in blobs['journal'].splitlines()])
    verify_sources();require(bounded(case_path,32768)==raw,'case unchanged')
    for key,path in PATHS.items():require(sha(ROOT/path)==case['inputs'][key]['sha256'] and (ROOT/path).stat().st_size==case['inputs'][key]['bytes'],'input unchanged')
    result.update(case_sha256=expected_sha,input_pins=case['inputs'],source_pins=verify_sources())
    with output.open('x',encoding='utf-8',newline='\n')as out:json.dump(result,out,sort_keys=True,indent=2,allow_nan=False);out.write('\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',type=Path,required=True);p.add_argument('--case-sha256',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=review_case(args.case,args.case_sha256,args.output);print(json.dumps({'status':result['status'],'summary_sha256':sha(args.output),'production_ready':False}))
