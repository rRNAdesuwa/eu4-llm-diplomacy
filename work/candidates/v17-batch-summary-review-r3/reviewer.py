"""Explicit stopped-batch file review. No process reader, publisher or callback option."""
from copy import deepcopy
import argparse
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import re
import sys
import tempfile
import ledger
import census_replay
import native_stream

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
require=ledger.require
same=ledger.same
integer=ledger.integer
PREFIX_REPLAY_BUDGET=512*1024*1024
COUNTS={'lifecycle':20,'owned_peace':1,'preview':72,'command':72}
SESSION_PATTERN=r'(?:session\.json|install\.claim|research-1375\.jsonl|phase-(?:lifecycle|owned-peace-lifecycle|preview|command)\.claim(?:\.host-intent)?|[0-9]{20}\.(?:host-intent|claim|fixture-profile|lease-pause\.claim|supervisor\.jsonl|publisher-output\.txt))'


def bounded(path,limit=ledger.MAX_ARTIFACT):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'File read budget exceeded');return raw


def safe_path(root,name):
    require(ledger.artifact_name(name)==name and '\\' not in name,'Noncanonical input path')
    path=Path(root)
    for part in name.split('/'):
        path=path/part
        require(not path.is_symlink() and not path.is_junction(),'Linked input path')
    require(path.resolve().is_relative_to(Path(root).resolve()),'Escaped input root');return path


def load_source(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def dependencies():
    """Pin before import and insist canonical formal origins/default roots."""
    adapter=ledger.load_adapter()
    names=['work.native.lab_protocol_v17_1375']+['tools.verify_diplomacy_'+p+'_v17' for p in
        ('lifecycle','owned_peace','preview','command','acceptance')]
    sys.path.insert(0,str(ROOT));modules={}
    for name in names:
        module=importlib.import_module(name)
        require(Path(module.__file__).resolve()==ROOT/(name.replace('.','/')+'.py'),'Foreign formal module origin: '+name)
        modules[name]=module
    lab=modules[names[0]]
    require(lab.ROOT==ROOT and lab.OUTPUT==ROOT/'work/runtime/native1375-v17'
            and inspect.signature(lab.verify_build).parameters['root'].default==ROOT
            and inspect.signature(lab.LiveLabProcess).parameters['output'].default==lab.OUTPUT,
            'Formal module defaults rebound to candidate mirror')
    old_path=sys.path[:]
    try:experiment=load_source('batch_r3_fixed_experiment',ROOT/'work/candidates/v17-acceptance-experiment-review/reviewer.py')
    finally:sys.path[:]=old_path
    census=load_source('batch_r3_fixed_census',ROOT/'work/candidates/v17-batch-census-r3/census.py')
    insult=load_source('batch_r3_fixed_insult',ROOT/'work/candidates/ordinary-insult-observer-1375/observer.py')
    return adapter,lab,experiment,(census,census.core,census.extension,census.advanced,insult)


def json_shape(value):return ledger.json_value(json.dumps(value,allow_nan=False).encode())


class NativeReplay:
    """Fixed private byte mirrors; a prefix cannot borrow later native records."""
    def __init__(self,artifacts,files,scope,lab,adapter,base,pre):
        self.a=artifacts;self.files=files;self.scope=scope;self.lab=lab;self.adapter=adapter
        self.temp=tempfile.TemporaryDirectory(prefix='v17-batch-offline-');self.directory=Path(self.temp.name)
        try:
            for name,path in files.items():(self.directory/name).write_bytes(artifacts.read(path))
            self.raw=artifacts.read(files['research-1375.jsonl'])
            self.metadata=lab.read_session_metadata(self.directory,scope['plan']['pid'],scope['plan']['creation'])
            require(integer(self.metadata['window_thread'],scope['plan']['window_thread'],scope['plan']['window_thread']),
                    'Native owner thread differs')
            self.full=json_shape(lab.read_evidence(self.directory,self.metadata))
            require(same(self.full['phases'],dict.fromkeys(COUNTS,True)) and all(self.full[k] is False for k in
                    ('pending','lease_pending','input_wait_pending')),'Incomplete stopped native evidence')
            require(len(self.full['phase_proofs']['lifecycle']['lifecycle'])==20
                    and self.full['phase_proofs']['owned_peace']['core_record_count']==9
                    and self.full['phase_proofs']['preview']['case_count']==72
                    and self.full['phase_proofs']['command']['case_count']==72,'Exact 20/1/72/72 proof matrix differs')
            self.dates,self.speed_traces=native_stream.strict_stream(self.raw,base,pre)
            self.frames={ledger.canonical(row) for line,row in base.parse_lines(self.raw) if row['event']=='research_frame'}
            self.cache={};self.replay_bytes=0
        except BaseException:self.close();raise

    def close(self):self.temp.cleanup()

    def status(self,box):
        evidence=box['evidence'];size=evidence['log_bytes'];sha=evidence['log_sha256']
        require(integer(size,1,len(self.raw)) and self.raw[size-1:size]==b'\n'
                and ledger.digest(self.raw[:size])==sha,'Status has no complete matching native prefix')
        key=(size,sha)
        if key not in self.cache:
            self.replay_bytes+=size;require(self.replay_bytes<=PREFIX_REPLAY_BUDGET,'Aggregate native prefix replay budget exceeded')
            (self.directory/'research-1375.jsonl').write_bytes(self.raw[:size])
            replay=json_shape(self.lab.read_evidence(self.directory,self.metadata));arms={}
            pauses=self.adapter.lease_completions(self.directory/'research-1375.jsonl',size,sha,arms)
            self.cache[key]=(replay,arms,pauses)
        replay,arms,pauses=self.cache[key]
        require(same(evidence,replay),'Cached status differs from complete frozen native prefix replay')
        require(same(box['lease_arms'],arms) and same(box['lease_completions'],pauses),
                'Cached lease proof borrowed/altered outside native prefix')
        require(same(box['metadata'],self.metadata),'Status metadata differs from frozen session')
        return replay


def session_inventory(artifacts,files,scope,root):
    directory=f"work/runtime/native1375-v17/session-{scope['plan']['pid']}-{scope['plan']['creation']}"
    require(type(files) is dict and 11<=len(files)<=ledger.MAX_FILES
            and all(type(name) is str and re.fullmatch(SESSION_PATTERN,name) and path==directory+'/'+name
                    for name,path in files.items()),'Invalid session inventory or unresolved request file')
    path=safe_path(root,directory)
    actual=list(path.iterdir())
    require(len(actual)==len(files) and {p.name for p in actual}==set(files)
            and all(p.is_file() and not p.is_symlink() and not p.is_junction() for p in actual),
            'Stopped inventory hides added/pending session files')
    for path in files.values():artifacts.read(path)


def check_claims(native,base):
    lab=native.lab;files=native.files;a=native.a;requests=native.full['requests']
    require(requests and set(requests)=={str(n) for n in range(1,native.full['last_sequence']+1)},'Incomplete native sequence inventory')
    required={'session.json','install.claim','research-1375.jsonl'}
    for phase,(_,claim,_) in lab.PHASES.items():
        required|={claim,claim+'.host-intent'}
        base.validate_host(a.document(files[claim+'.host-intent']),lab.phase_wire(phase,native.metadata))
    for key,row in requests.items():
        seq=int(key);stem=f'{seq:020}';request=row['request'];required|={stem+'.claim',stem+'.host-intent'}
        base.validate_host(a.document(files[stem+'.host-intent']),a.read(files[stem+'.claim']),row)
        require(row['complete'] is not None,'Unfinished native request')
        if seq==1:
            require(same({k:request[k] for k in ('operation','mode','action','actor','target','speed')},
                    dict(operation='fixture',mode='submit',action='fixture_on',actor='FRA',target='FRA',speed=0)),
                    'Only fixture_on may precede the batch')
            required.add(stem+'.fixture-profile')
        elif request['operation']=='speed':
            require(request['speed']==5,'Batch speed profile differs')
            required|={stem+'.lease-pause.claim',stem+'.supervisor.jsonl',stem+'.publisher-output.txt'}
            for core in row['records']:base.validate_controls(core,5)
        else:
            require(request['operation']=='pair','Batch cannot contain fixture/acceptance/other operations')
            for core in row['records']:
                base.strict_pair(core)
                require(core['world']==base.WORLD and core['pid']==base.PID and core['thread_id']==base.THREAD
                        and core['process_creation_filetime']==base.CREATION
                        and all(core[k]==request[k] for k in ('actor','target'))
                        and core['action_id']==request['action'],'Pair core complete identity differs')
            begin=row['records'][0]
            require(begin['event']=='pair_engine_begin' and begin['phase']==2 and begin['status']==begin['reason']==0
                    and all(begin[k] is False for k in base.PAIR_BOOLS)
                    and all(begin[k] is None for k in base.PAIR_NULLABLE),'Pair begin owns future output')
            entered=row['records'][-1]['submit_entered']
            require([c['event'] for c in row['records']]==(['pair_engine_begin','pair_engine_dispatch_intent','pair_engine_complete']
                    if entered else ['pair_engine_begin','pair_engine_complete']),'Missing/extra native pair ownership record')
            if entered:
                intent=row['records'][1]
                require(intent['phase']==11 and intent['status']==intent['reason']==0
                        and all(intent[k] is True for k in ('preview_called','preview_allowed','gate_called','gate_allowed','original_destroyed'))
                        and all(intent[k] is False for k in ('submit_entered','submit_returned','command_destroyed_before_dispatch'))
                        and all(intent[k] is None for k in base.PAIR_NULLABLE),'Dispatch intent already owns future transfer result')
    require(set(files)==required,'Missing/extra stopped phase/request artifacts')


def review(case,root=ROOT):
    fields={'schema_version','purpose','finalized','inputs','batch_scope','journal','summary','exit','stopped_audit',
            'session_files','preflight_scope'}
    require(type(case) is dict and set(case)==fields and integer(case['schema_version'],1,1)
            and case['purpose']=='v17_batch_stopped_case_r3' and case['finalized'] is True,'Explicit finalized batch case required')
    adapter,lab,experiment,census_modules=dependencies()
    require(type(case['inputs']) is dict and 1<=len(case['inputs'])<=ledger.MAX_FILES,'Explicit bounded inputs required')
    raw_files={};total=0
    for name,expected in case['inputs'].items():
        raw=bounded(safe_path(root,name));total+=len(raw);require(total<=ledger.MAX_AGGREGATE,'Aggregate file budget')
        raw_files[name]=raw
    artifacts=ledger.Artifacts(raw_files,case['inputs'])
    scope=artifacts.document(case['batch_scope']);plan=adapter.batch.validate_plan(scope['plan'])
    ps=case['preflight_scope'];base,pre=experiment.configure(ps)
    require(all(plan[k]==ps[k] for k in ('pid','creation','world_cookie','window_thread'))
            and scope['manifest_sha256']==ps['manifest_sha256'] and scope['dll_sha256'].lower()==ps['dll_sha256']
            and scope['fixture_profile_sha256']==lab.FIXTURE_PROFILE_SHA256,'Batch/preflight scope differs')
    exit_row=base.validate_exit(artifacts.document(case['exit']))
    session_inventory(artifacts,case['session_files'],scope,root)
    stop=artifacts.document(case['stopped_audit']);files=case['session_files']
    require(same(stop,dict(pid=plan['pid'],creation=plan['creation'],process_exit_filetime=exit_row['process_exit_filetime'],
            complete_log=case['inputs'][files['research-1375.jsonl']],
            session_files={n:case['inputs'][p] for n,p in files.items()},stopped=True)),
            'Stopped audit/held normal exit/log inventory differs')
    prefix_case=artifacts.document(ps['preflight_case']);prefix_summary=artifacts.document(ps['preflight_summary'])
    for descriptor in prefix_case['inputs'].values():
        require(same(case['inputs'][descriptor['path']],dict(bytes=descriptor['size_bytes'],sha256=descriptor['sha256'])),
                'Preflight input omitted/rebound in complete inventory');artifacts.read(descriptor['path'])
    require(same(pre.review(prefix_case,root=Path(root)),prefix_summary),'Independent preflight summary replay differs')
    native=NativeReplay(artifacts,files,scope,lab,adapter,base,pre)
    try:
        check_claims(native,base)
        journal=artifacts.read(case['journal']);summary=artifacts.document(case['summary'])
        for line in journal.splitlines():
            row=ledger.json_value(line)
            if row.get('event')=='status_snapshot':native.status(artifacts.document(row['path'],row['sha256']))
        # The callback is fixed here, not a caller-supplied trust seam.
        result=ledger.audit(scope,journal,summary,artifacts,adapter=adapter,
            census_checker=lambda raw,c,s:census_replay.recompute(raw,c,s,census_modules,native.frames))
        require(native.full['last_sequence']==result['next_sequence']-1
                and {r['sequence'] for r in result['receipt_sources']}==set(range(2,result['next_sequence'])),
                'Complete ledger does not cover each stopped native request')
        for source in result['receipt_sources']:
            require(same(source['request'],native.full['requests'][str(source['sequence'])]),
                    'Ledger selected request differs from complete stopped native record')
        # The public meaning stays selected batch state and native call records;
        # there is still no per-action independent effect or timing attestation.
        result.update(kind='v17_batch_stopped_review_r3',status='reviewed_stopped_batch',native_source_replay_required=False,
            native_log_claim_replay_verified=True,census_raw_passes_recomputed=True,
            actual_completion_elapsed_verified=False,individual_effect_verified=False,
            natural_ai_acceptance_verified=False,whole_world_verified=False,production_backend_registered=False,
            native_execution_verified=False,stopped_normal_exit=deepcopy(exit_row),input_artifacts=deepcopy(case['inputs']),
            reviewed_status_prefixes=len(native.cache),native_prefix_replay_bytes=native.replay_bytes,
            preflight_counts=COUNTS,case_content_sha256=ledger.digest(ledger.canonical(case).encode()))
        for name in artifacts.raw:
            require(bounded(safe_path(root,name))==artifacts.raw[name],'Input changed during offline review')
        ledger.load_adapter() # Recheck all 200+ pinned sources, not only adapter dependencies.
        return result
    finally:native.close()


def template():
    return dict(schema_version=1,purpose='v17_batch_stopped_case_r3',finalized=False,inputs={},batch_scope=None,
        journal=None,summary=None,exit=None,stopped_audit=None,session_files={},preflight_scope={})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('template','review','check'))
    parser.add_argument('--case',type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if args.command=='template':result=template()
    else:
        require(args.case is not None,'Explicit case path required');result=review(ledger.json_value(bounded(args.case,512*1024)))
    if args.command=='check':
        require(same(result,ledger.json_value(bounded(args.output))),'Stored review differs');print('matched');return
    with args.output.open('xb') as stream:stream.write((json.dumps(result,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({'output':str(args.output),'status':result.get('status'),'production':False}))


if __name__=='__main__':main()
