"""Pure finite artifact ledger check; no process, subprocess or game access.

This candidate deliberately has no actual-case CLI. A successful result is
ledger consistency, not independently replayed native evidence or effects.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
MAX_ARTIFACT=8*1024*1024
MAX_JOURNAL=32*1024*1024
MAX_AGGREGATE=160*1024*1024
MAX_FILES=1400
MAX_RECORDS=10000


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def same(a,b):return canonical(a)==canonical(b)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def integer(value,lo=0,hi=2**63-1):return type(value) is int and lo<=value<=hi


def artifact_name(name):
    require(type(name) is str and ':' not in name and '\0' not in name,'Artifact name encoding')
    normalized=name.replace('\\','/')
    require(not PurePosixPath(normalized).is_absolute()
            and all(p not in ('','.','..') for p in normalized.split('/')),'Canonical relative artifact name')
    return normalized


def json_value(raw):
    def unique(pairs):
        out={}
        for key,value in pairs:
            require(key not in out,'Duplicate JSON key');out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=unique,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def load_adapter():
    # Pin BEFORE executing/importing source. No verify_build or LiveLabProcess.
    pins=json_value((HERE/'source-pins.json').read_bytes())
    require(type(pins) is dict and 1<=len(pins)<=128,'Source pin count')
    for name,expected in pins.items():
        path=ROOT/name
        with path.open('rb') as stream:raw=stream.read(MAX_ARTIFACT+1)
        require(len(raw)<=MAX_ARTIFACT and expected=={'bytes':len(raw),'sha256':digest(raw)},'Changed pinned source: '+name)
    path=ROOT/'work/candidates/v17-batch-cli-adapter-r2/adapter.py'
    spec=importlib.util.spec_from_file_location('batch_summary_reviewed_adapter',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class Artifacts:
    """Already captured bytes plus explicit descriptors, never implicit paths."""
    def __init__(self,raw_files,inventory):
        require(type(raw_files) is dict and type(inventory) is dict and set(raw_files)==set(inventory)
                and 1<=len(raw_files)<=MAX_FILES,'Explicit bounded artifact inventory')
        self.raw={};self.used=set();total=0
        for name,raw in raw_files.items():
            require(type(name) is str and '\\' not in name and ':' not in name and '\0' not in name
                    and not PurePosixPath(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')),
                    'Canonical relative artifact name')
            require(type(raw) is bytes and len(raw)<=MAX_ARTIFACT,'Artifact bound/type')
            expected=inventory[name]
            require(type(expected) is dict and set(expected)=={'bytes','sha256'} and integer(expected['bytes'])
                    and expected['bytes']==len(raw) and type(expected['sha256']) is str
                    and expected['sha256']==digest(raw),'Exact frozen artifact descriptor')
            total+=len(raw);require(total<=MAX_AGGREGATE,'Aggregate artifact budget')
            self.raw[name]=raw

    def read(self,name,sha=None):
        name=artifact_name(name)
        require(name in self.raw,'Artifact absent from explicit inventory: '+str(name))
        raw=self.raw[name];self.used.add(name)
        require(sha is None or type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha) and digest(raw)==sha,'Artifact digest mismatch')
        return raw

    def document(self,name,sha=None):return json_value(self.read(name,sha))


def capture_document(value,command,argv):
    kind='request' if command['kind']=='pair' else 'speed'
    require(type(value) is dict and set(value)=={'purpose','kind','arguments','exit_code','automatic_retry','applied_verified','stderr','report'},'Exact CLI capture schema')
    require(value['purpose']=='one_explicit_v17_cli_capture' and value['kind']==kind
            and type(value['exit_code']) is int and value['exit_code']==0
            and value['automatic_retry'] is False and value['applied_verified'] is False
            and value['stderr']=='','CLI failed/unknown')
    require(same(value['arguments'],argv[argv.index(kind)+1:]),'Exact captured argv')
    return value['report']


def audit(scope,journal_raw,summary,artifacts,*,adapter,census_checker):
    """Check one COMPLETE ledger; native/census origin proof is a separate gate.

    census_checker(raw,command,scope) must recompute a frozen census receipt.
    This injected pure seam exists for tests; it is not a public trust flag.
    No actual-case entry point exposes it and every result remains unverified.
    """
    batch=adapter.batch
    require(type(scope) is dict and set(scope)=={'plan','manifest_sha256','dll_sha256','fixture_profile_sha256'},'Exact batch scope')
    plan=batch.validate_plan(scope['plan'])
    require(plan['first_sequence']==2,'Only explicit fixture sequence 1 baseline supported')
    for key in ('manifest_sha256','dll_sha256','fixture_profile_sha256'):
        require(type(scope[key]) is str and re.fullmatch('[0-9a-fA-F]{64}',scope[key]),'Build/profile digest encoding')
    require(type(journal_raw) is bytes and 0<len(journal_raw)<=MAX_JOURNAL and journal_raw.endswith(b'\n'),'Complete bounded journal')
    lines=journal_raw.splitlines(keepends=True)
    require(len(lines)<=MAX_RECORDS,'Journal record bound')
    records=[]
    for line in lines:
        require(line.endswith(b'\n') and len(line)<=MAX_ARTIFACT,'Partial/oversized journal line')
        row=json_value(line);require(type(row) is dict and type(row.get('event')) is str,'Journal event schema');records.append(row)
    require(records[0]=={'event':'batch_opened','scope':scope,'automatic_retry':False,'production':False},'Initial durable scope differs')
    require(same(records[0],{'event':'batch_opened','scope':scope,'automatic_retry':False,'production':False}),'Initial typed scope differs')
    require(type(summary) is dict and summary.get('state')=='complete' and summary.get('failure') is None,'Terminal/incomplete batch cannot pass')
    emitted=[];model=batch.Batch(plan,lambda row:emitted.append(row))
    latest=None;active=None;progress_due=False;finished=False;seen_status=set();seen_intents=set();seen_sequences=[]
    status_count=0;last_observed=0;initial_and_final=[];receipt_sources=[]
    native_prefix_requirements=[]
    for index,row in enumerate(records[1:],1):
        event=row['event']
        require(not finished,'Record after final summary')
        if progress_due:
            expected={'event':'batch_progress','completed_rows':model.index,'total_rows':36,'next_sequence':model.last_sequence+1,'individual_effect_verified':False}
            require(same(row,expected),'Missing/malformed immediate batch progress');progress_due=False;continue
        if event=='status_snapshot':
            require(set(row)=={'event','path','sha256'} and artifact_name(row['path']) not in seen_status,'Duplicate/malformed status record')
            seen_status.add(artifact_name(row['path']));status_count+=1;require(status_count<=1024,'Status capture bound')
            latest=artifacts.document(row['path'],row['sha256'])
            now=latest['observed_uptime_ms'];require(integer(now,last_observed),'Status observation time regressed');last_observed=now
            h=adapter.health_from_status(latest,scope,now)
            if model.inflight is not None:
                decision=model.next(h,max(now,model.last_now or 0))
                require(decision['state']!='terminal','Fatal inflight status: '+str(model.failure))
            else:
                model.health(h,max(now,model.last_now or 0))
            e=latest['evidence']
            # Kept explicit for later stopped-log replay: a saved status is not
            # itself proof that this prefix came from the installed module.
            require(integer(e['log_bytes'],1,32*1024*1024) and type(e['log_sha256']) is str
                    and re.fullmatch('[0-9a-f]{64}',e['log_sha256']),'Status lacks exact native prefix boundary')
            native_prefix_requirements.append({'status':row['path'],'bytes':e['log_bytes'],'sha256':e['log_sha256']})
        elif event=='resolved_intent':
            require(set(row)=={'event','command_id','command','automatic_retry'} and row['automatic_retry'] is False
                    and not active and latest is not None,'Overlapping/unbound intent')
            c=row['command'];ident=row['command_id']
            require(type(ident) is str and ident==batch.command_id(c) and ident not in seen_intents,'Wrong/repeated command identifier')
            seen_intents.add(ident)
            now=c['issued_uptime_ms'];h=adapter.health_from_status(latest,scope,now)
            decision=model.next(h,now)
            require(decision['state']=='start_once' and same(decision['command'],c),'Command differs from fixed ordered matrix/health/legality')
            require(len(emitted)==1 and same(emitted.pop(),row),'Durable intent differs from driver')
            active={'id':ident,'command':c,'argv':None,'capture':None,'published':None}
            if c['kind']!='observe':seen_sequences.append(c['sequence'])
        elif event=='cli_start_once':
            require(set(row)=={'event','command_id','argv','capture'} and active is not None and active['command']['kind']!='observe'
                    and active['argv'] is None and row['command_id']==active['id'],'Repeated/unbound publisher start')
            argv=row['argv'];require(type(argv) is list and len(argv)>0 and type(argv[0]) is str and argv[0],'Publisher executable absent')
            expected=batch.argv(active['command'],argv[0]);require(same(argv,expected),'Publisher argv differs from fixed compiler')
            capture=argv[argv.index('--output')+1];require(artifact_name(row['capture'])==artifact_name(capture),'Publisher capture is not compiler-selected')
            active.update(argv=argv,capture=capture)
        elif event=='publisher_capture':
            require(set(row)=={'event','command_id','path','sha256'} and active is not None and active['argv'] is not None
                    and active['published'] is None and row['command_id']==active['id'] and artifact_name(row['path'])==artifact_name(active['capture']),
                    'Repeated/unbound capture')
            value=artifacts.document(row['path'],row['sha256'])
            active['published']=capture_document(value,active['command'],active['argv'])
        elif event=='completed':
            require(set(row)=={'event','command_id','outcome','evidence','individual_effect_verified'} and active is not None
                    and row['command_id']==active['id'] and row['individual_effect_verified'] is False,'Unbound/overclaimed completion')
            c=active['command'];supervisor=None
            if c['kind']=='observe':
                name=f"work/runtime/native1375-v17/batch-{plan['run_id']}-{c['boundary']}-census.json"
                raw=artifacts.read(name,row['evidence']['artifact_sha256'])
                expected=census_checker(raw,c,scope)
                require(expected['artifact_sha256']==digest(raw),'Census checker did not bind raw artifact')
                initial_and_final.append({'boundary':c['boundary'],'path':name,'sha256':digest(raw)})
            else:
                require(active['published'] is not None and latest is not None,'Native completion before publisher/status evidence')
                if c['kind']=='speed':
                    name=f"work/runtime/native1375-v17/session-{c['pid']}-{c['creation']}/{c['sequence']:020}.supervisor.jsonl"
                    path=active['published']['report'].replace('\\','/')
                    require(path==name or path.endswith('/'+name),'Supervisor report path has wrong session/sequence')
                    raw=artifacts.read(name);require(len(raw)<=65536 and raw.endswith(b'\n'),'Supervisor incomplete/bounded')
                    supervisor=[json_value(line) for line in raw.splitlines()]
                expected=adapter.native_receipt(c,latest,active['published'],supervisor)
                require(expected is not None,'No completed matching native receipt')
                receipt_sources.append({'sequence':c['sequence'],'status_prefix':native_prefix_requirements[-1],
                    'request':deepcopy(latest['evidence']['requests'][str(c['sequence'])]),
                    'native_source_replay_required':True})
            require(same(expected,row['evidence']),'Completion normalized evidence differs from artifact')
            # The original journal lacks completion-tick timestamps. This is
            # a feasible recorded ordering, NOT an independent elapsed proof.
            now=max(last_observed,model.last_now or 0,expected.get('observed_uptime_ms',0))
            model.receive(active['id'],expected,now)
            require(model.state!='terminal','Completion rejected: '+str(model.failure))
            require(len(emitted)==1 and same(emitted.pop(),row),'Completed outcome differs from recomputed driver')
            active=None;progress_due=True
        elif event=='batch_finished':
            require(set(row)=={'event','summary'} and active is None and model.state=='complete'
                    and model.index==36 and len(initial_and_final)==2,'Final summary before exactly 36 rows/two censuses')
            expected=model.summary();expected['still_running_helper_pids']=[]
            require(same(row['summary'],summary) and same(summary,expected),'Summary differs from complete replay or has active helpers')
            finished=True
        else:raise ValueError('Unsupported/terminal journal event: '+event)
    require(finished and not progress_due and not active,'Incomplete durable terminal sequence')
    require(seen_sequences==list(range(2,model.last_sequence+1)),'Published sequence gap/repeat')
    require([c['boundary'] for c in initial_and_final]==['initial','final'],'Wrong census order/count')
    return {'kind':'v17_batch_ledger_consistency','ledger_consistent':True,'matrix_rows':36,
            'native_dispatch_count':summary['native_dispatch_count'],'legality_attempt_count':summary['legality_attempt_count'],
            'guard_survey_only':summary['guard_survey_only'],'next_sequence':summary['next_sequence'],
            'censuses':initial_and_final,'status_prefix_requirements':native_prefix_requirements,'receipt_sources':receipt_sources,
            'native_source_replay_required':True,'native_execution_verified':False,'individual_effect_verified':False,
            'request_causality_verified':False,'strict_single_player_verified':False,'world_epoch_verified':False,
            'production_backend_registered':False,'actual_completion_elapsed_verified':False,
            'unreferenced_artifacts':sorted(set(artifacts.raw)-artifacts.used)}
