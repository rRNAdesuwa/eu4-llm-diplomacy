"""Explicit disposable v17 batch adapter. Importing performs no game operation."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
DRIVER=HERE.parent/'v17-batch-host-review-r3'/'batch.py'
spec=importlib.util.spec_from_file_location('reviewed_batch',DRIVER)
batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)
require=batch.require
MAX_JSON=8*1024*1024
MAX_JOURNAL=32*1024*1024
MAX_STATUS=1024


def verify_inputs():
    pins=read_json(HERE/'source-pins.json',65536)
    require(type(pins) is dict and 1<=len(pins)<=64,'Dependency pin count')
    for name,expected in pins.items():
        path=ROOT/name
        require(path.resolve()==path and path.is_relative_to(ROOT),'Noncanonical dependency')
        with path.open('rb') as stream:raw=stream.read(MAX_JSON+1)
        require(len(raw)<=MAX_JSON and expected==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),'Pinned input changed: '+name)


def read_json(path,limit=MAX_JSON):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'Bounded JSON exceeded')
    def unique(pairs):
        value={}
        for k,v in pairs:
            require(k not in value,'Duplicate JSON key');value[k]=v
        return value
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def durable_new(path,value):
    raw=(batch.canonical(value)+'\n').encode('ascii')
    require(len(raw)<=MAX_JSON,'Bounded result exceeded')
    with Path(path).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def bounded_hash(path,limit=MAX_JSON):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'Hash input exceeds bound')
    return hashlib.sha256(raw).hexdigest()


def now_ms():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetTickCount64.restype=ctypes.c_ulonglong
    return kernel.GetTickCount64()


def same_typed(actual,expected,message):
    require(batch.canonical(actual)==batch.canonical(expected),message)


def lease_completions(path,size,expected_sha,arms=None):
    """Retain raw lease arms/finals from the exact already-validated prefix."""
    require(batch.integer(size,1,32*1024*1024),'Native prefix size bound')
    remaining=size;digest=hashlib.sha256();found={}
    with Path(path).open('rb') as stream:
        while remaining:
            line=stream.readline(min(remaining,16385));remaining-=len(line)
            require(line and line.endswith(b'\n') and len(line)<=16384,'Partial native prefix')
            digest.update(line);row=json.loads(line)
            if arms is not None and row.get('event')=='lab_lease_armed':
                seq=row['sequence'];require(type(seq) is int and str(seq) not in arms,'Duplicate lease arm')
                arms[str(seq)]=row;require(len(arms)<=4096,'Lease arm count bound')
            if row.get('event')=='lab_native_record' and row.get('lease_pause') is True and row.get('record',{}).get('event')=='test_speed_complete':
                seq=row['sequence'];require(type(seq) is int and str(seq) not in found,'Duplicate pause completion')
                found[str(seq)]=row['record'];require(len(found)<=4096,'Pause proof count bound')
    require(digest.hexdigest()==expected_sha,'Native prefix changed between validated reads')
    return found


def status_worker(scope_path,output):
    """Only this subprocess reads the game; frozen helpers retain their guards."""
    from work.native import lab_protocol_v17_1375 as lab
    from work.native.run_lab_speed_v17_1375 import paused_state
    verify_inputs()
    scope=read_json(scope_path,65536);plan=batch.validate_plan(scope['plan'])
    manifest,sha=lab.verify_build()
    require(sha==scope['manifest_sha256'] and manifest['dll_sha256']==scope['dll_sha256'],'Pinned build changed')
    fixture_disk=lab.verify_installed_fixture(manifest,plan['pid'],plan['creation'])
    with lab.LiveLabProcess(plan['pid'],expected_creation=plan['creation']) as process:
        session=lab.session_path(lab.OUTPUT,plan['pid'],plan['creation'])
        metadata=lab.read_session_metadata(session,plan['pid'],plan['creation'])
        require(metadata['window_thread']==plan['window_thread'],'Native owner thread changed')
        before=process.snapshot();pause_before=paused_state(process.reader)
        evidence=lab.read_evidence(session,metadata)
        lease_arms={}
        lease_cores=lease_completions(session/'research-1375.jsonl',evidence['log_bytes'],evidence['log_sha256'],lease_arms)
        after=process.snapshot();pause_after=paused_state(process.reader)
        current=lab.uptime_ms()
        result={'purpose':'v17_batch_read_only_status','pid':plan['pid'],'creation':plan['creation'],
            'manifest_sha256':sha,'dll_sha256':manifest['dll_sha256'],'observed_uptime_ms':current,
            'metadata':metadata,'live_before':before,'live_after':after,
            'pause_before':pause_before,'pause_after':pause_after,'evidence':evidence,
            'fixture_disk_evidence':fixture_disk,
            'lease_completions':lease_cores,
            'lease_arms':lease_arms,
            'production_backend_registered':False}
        # An older, still-fresh paused heartbeat is not proof that the newly
        # paused live date is ready. Retain all samples, but do not authorize.
        sampled_readiness(result,scope,current)
    durable_new(output,result)


def sampled_readiness(box,scope,now):
    """Pure strict revalidation; a monotonic sampling transition is not fatal."""
    p=scope['plan'];e=box['evidence'];f=e['latest_frame'];before=box['live_before'];after=box['live_after']
    pb=box['pause_before'];pa=box['pause_after'];metadata=box['metadata']
    require(batch.integer(now) and batch.integer(box['observed_uptime_ms'],max(0,now-2500),now),'Status is not current')
    current=box['observed_uptime_ms']
    require(batch.integer(f['uptime_ms'],max(0,current-2500),current) and now-f['uptime_ms']<=2500,'Stale native frame')
    require(type(metadata['window_thread']) is int and metadata['window_thread']==p['window_thread']
        and type(f['thread']) is int and f['thread']==p['window_thread'],'Status world/thread changed')
    player='0x0100007a00415246'
    for sample in (before,after):
        require(type(sample['pid']) is int and sample['pid']==p['pid'] and sample['creation']==p['creation']
            and sample['world_cookie']==p['world_cookie'] and sample['player_handle']==player,'Read-only world identity changed')
        require(batch.integer(sample['acceptance_flag'],0,1),'Live flag type/range differs')
    require(f['world_cookie']==p['world_cookie'] and f['player_handle']==player,'Native/live roots differ')
    require(batch.integer(f['acceptance_flag'],0,1) and before['acceptance_flag']==after['acceptance_flag']==f['acceptance_flag'],'Live flag mismatch')
    for pause in (pb,pa):
        require(all(batch.integer(pause[k],1) for k in ('game','server','pause_manager','player'))
            and pause['game']==int(p['world_cookie'],16) and pause['player']==int(player,16),'Pause world identity changed')
        require(type(pause['paused']) is bool and batch.integer(pause['native_speed_index'],0,5),'Pause scalar types')
    require(all(pb[k]==pa[k] for k in ('game','server','pause_manager','player')),'Read-only world identity changed')
    dates=[s['raw_date'] for s in (before,pb,after,pa)]
    require(all(batch.integer(date,1,2**31-1) for date in dates) and dates==sorted(dates),'Read-only date regressed or untyped')
    require(batch.integer(f['raw_date'],1,2**31-1) and f['raw_date']<=after['raw_date'],'Native/live date regressed or untyped')
    require(all(type(f[k]) is bool for k in ('paused','world_ready','session_frozen','world_changed','thread_changed','lease_active','mailbox_ready'))
        and batch.integer(f['native_speed_index'],0,5),'Native health scalar types')
    require(all(type(e[k]) is bool for k in ('pending','input_wait_pending','lease_pending'))
        and all(type(e['phases'][k]) is bool for k in ('lifecycle','owned_peace','preview','command'))
        and batch.integer(e['last_sequence']),'Native readiness scalar types')
    ready_pause=all(s['paused'] is True and s['native_speed_index']==0 for s in (f,pb,pa))
    ready_pause=ready_pause and all(date==f['raw_date'] for date in dates)
    # Keep the latest actually observed date even while its heartbeat lags;
    # the unchanged driver's high-water mark must never forget live progress.
    return ready_pause,pa['raw_date']


def health_from_status(box,scope,now):
    p=scope['plan'];e=box['evidence'];f=e['latest_frame'];live=box['live_after'];pause=box['pause_after']
    require(box['purpose']=='v17_batch_read_only_status' and box['production_backend_registered'] is False,'Status provenance schema')
    fixture=box['fixture_disk_evidence']
    require(type(fixture['pid']) is int and fixture['pid']==p['pid'] and fixture['creation']==p['creation']
        and fixture['profile_sha256']==scope['fixture_profile_sha256'] and fixture['fixture_definition_files_verified'] is True
        and fixture['installed_before_process_creation'] is True and fixture['engine_registration_verified'] is False,'Installed fixture evidence differs')
    require(type(box['pid']) is int and box['pid']==p['pid'] and box['creation']==p['creation']
        and box['manifest_sha256']==scope['manifest_sha256'] and box['dll_sha256']==scope['dll_sha256'],'Status build/process changed')
    ready_pause,observed_date=sampled_readiness(box,scope,now)
    return dict(pid=p['pid'],creation=p['creation'],world_cookie=f['world_cookie'],thread=f['thread'],
        raw_date=observed_date,last_sequence=e['last_sequence'],uptime_ms=f['uptime_ms'],
        world_ready=f['world_ready'],lifecycle_passed=e['phases']['lifecycle'],owned_peace_passed=e['phases']['owned_peace'],
        preview_passed=e['phases']['preview'],command_passed=e['phases']['command'],session_frozen=f['session_frozen'],
        world_changed=f['world_changed'],thread_changed=f['thread_changed'],acceptance_flag=f['acceptance_flag'],
        acceptance_state=e['acceptance_window']['state'],paused=ready_pause,native_speed_index=pause['native_speed_index'],
        pending=e['pending'] or e.get('input_wait_pending',False),lease_active=f['lease_active'],
        lease_pending=e['lease_pending'],mailbox_ready=f['mailbox_ready'])


def capture_report(path,command,argv):
    value=read_json(path)
    require(value.get('purpose')=='one_explicit_v17_cli_capture' and value.get('kind')==('request' if command['kind']=='pair' else 'speed')
        and type(value.get('exit_code')) is int and value['exit_code']==0 and value.get('automatic_retry') is False
        and value.get('applied_verified') is False and not value.get('stderr') and 'exception_type' not in value,'Publisher capture failed/unknown')
    i=argv.index('request' if command['kind']=='pair' else 'speed')
    same_typed(value['arguments'],argv[i+1:],'Captured publisher argv differs')
    return value['report']


def native_receipt(command,box,published,supervisor=None):
    """Normalize only a completed frozen-reader result and its fixed publication."""
    c=command;e=box['evidence'];seq=c['sequence'];entry=e['requests'].get(str(seq),e['requests'].get(seq))
    if entry is None or entry['complete'] is None:return None
    request=entry['request'];core=entry['records'][-1];complete=entry['complete']
    expected=dict(pid=c['pid'],creation=c['creation'],sequence=seq,operation=c['kind'],mode=c.get('mode','submit'),
        action=c.get('action','none'),actor=c.get('actor','FRA'),target=c.get('target','FRA'),speed=c.get('speed',0),
        bound_action='none',bound_target='none',bound_submit_sequence=0)
    same_typed({k:request[k] for k in expected},expected,'Exact 13-field request binding differs')
    ttl=60000 if c['kind']=='pair' else 5000
    require(type(request['expires']) is int and batch.integer(request['expires']-ttl,c['issued_uptime_ms'],box['observed_uptime_ms']),
        'Request creation inferred from fixed CLI TTL predates original job or follows status')
    require(complete['sequence']==seq and complete['session_frozen'] is False and complete['retry_allowed'] is False
        and complete['applied_verified'] is False and core['freeze_session'] is False,'Uncertain native completion')
    r={k:c[k] for k in ('pid','creation','world_cookie')}
    r.update(validated_frozen_evidence=True,sequence=seq,audit_complete=True,session_frozen=False,ownership_uncertain=False,exception=0)
    if c['kind']=='pair':
        pub=published['publication']
        require(published['purpose']=='restricted_pair_lab_1375_v17' and published['protocol']=='EU4LAB/3'
            and type(published['pid']) is int and published['pid']==c['pid'] and published['creation']==c['creation']
            and published['manifest_sha256']==box['manifest_sha256'] and published['dll_sha256']==box['dll_sha256']
            and pub['status']=='published' and pub['sequence']==seq and pub['pid']==c['pid'] and pub['creation']==c['creation']
            and pub['native_dispatch_verified'] is False and pub['automatic_retry'] is False,'Publication binding differs')
        from work.native.lab_protocol_v17_1375 import encode_request
        require(pub['request_sha256']==hashlib.sha256(encode_request(request)).hexdigest(),'Published request hash differs from native claim')
        require(core['event']=='pair_engine_complete' and core['world']==c['world_cookie']
            and core['raw_date']==c['raw_date'] and core['thread_id']==box['metadata']['window_thread'],'Pair completion attribution differs')
        require(type(core['original_destroyed']) is bool and type(core['command_destroyed_before_dispatch']) is bool,
            'Missing typed cleanup evidence')
        if core['submit_entered'] is True:
            require(core['original_destroyed'] is True and core['command_destroyed_before_dispatch'] is False,'Dispatched original/command cleanup differs')
        elif core['gate_called'] is True:
            require(core['original_destroyed'] is True and core['command_destroyed_before_dispatch'] is True,'Constructed command cleanup incomplete')
        r.update({k:c[k] for k in ('action','actor','target','mode','raw_date')})
        for k in ('status','reason','preview_called','preview_allowed','gate_called','gate_allowed','submit_entered',
                  'submit_returned','context_submit_return','caller_container_consumed','ownership_uncertain','exception'):
            r[k]=core[k]
        require(type(r['exception']) is int and r['exception']==0 and r['ownership_uncertain'] is False,'Native exception or unknown ownership')
        if r['submit_returned'] is False:
            require(r['context_submit_return'] is None and r['caller_container_consumed'] is None,'Non-returned ownership is non-null')
    else:
        if e['lease_pending'] or 'lease_complete' not in entry:return None
        require(published['status']=='completed_and_paused' and supervisor is not None and len(supervisor)==2,'Speed supervisor incomplete')
        armed,done=supervisor
        for row in supervisor:
            same_typed({k:row[k] for k in ('pid','creation','sequence','speed')},
                dict(pid=c['pid'],creation=c['creation'],sequence=seq,speed=5),'Supervisor identity differs')
            require(row['retry_allowed'] is False,'Supervisor allows retry')
        require(armed['event']=='supervisor_armed' and done['event']=='supervisor_complete'
            and type(armed['deadline_seconds']) is float and armed['deadline_seconds']==12.0
            and type(done['elapsed_seconds']) in (int,float) and 0<=done['elapsed_seconds']<12.0
            and done['after']['paused'] is True and type(done['after']['native_speed_index']) is int
            and done['after']['native_speed_index']==0,'Supervisor outcome differs')
        for key in ('game','server','pause_manager','player'):
            require(type(armed['before'][key]) is int and type(done['after'][key]) is int
                and armed['before'][key]==done['after'][key],'Supervisor roots changed')
        same_typed(done['native_lease_complete'],entry['lease_complete'],'Supervisor/native lease mismatch')
        require(armed['before']['raw_date']==c['before_date']==published['before_date']
            and done['after']['raw_date']==published['after_date'] and done['after']['game']==int(c['world_cookie'],16),'Supervisor world/date differs')
        speed_core(core,5,c['before_date'],box['metadata']['window_thread'])
        pause_core=box['lease_completions'][str(seq)];lease_arm=box['lease_arms'][str(seq)]
        same_typed({k:lease_arm[k] for k in ('event','pid','process_creation_filetime','sequence','initial_raw_date',
            'maximum_raw_date_delta','automatic_pause','reliable_generation_verified')},
            dict(event='lab_lease_armed',pid=c['pid'],process_creation_filetime=c['creation'],sequence=seq,
                initial_raw_date=c['before_date'],maximum_raw_date_delta=48,automatic_pause=True,reliable_generation_verified=False),
            'Native lease start/identity differs')
        require(batch.integer(lease_arm['deadline_uptime_ms'],c['issued_uptime_ms']+5000,request['expires']+4999),
            'Native lease deadline outside the claimed request interval')
        pause_date=pause_core['before_date'];final_date=published['after_date']
        require(batch.integer(pause_date,lease_arm['initial_raw_date']+48,2**31-1)
            and batch.integer(final_date,pause_date,2**31-1),'Unsupported lease pause/final date interval')
        # Native service_lease also has a wall-clock trigger. This batch profile
        # intentionally accepts only the independently provable date-triggered
        # subset; a timer-only <48 pause is unsupported, never guessed valid.
        speed_core(pause_core,0,pause_date,box['metadata']['window_thread'])
        r.update(status='completed_and_paused',supervisor_complete=True,before_date=published['before_date'],after_date=published['after_date'])
    return r


def speed_core(core,speed,date,thread):
    require(type(core.get('before_paused')) is bool,'Speed before-pause type')
    expected={'event':'test_speed_complete','thread_id':thread,'requested_speed':speed,'reason':0,
        'before_date':date,'before_native_index':0 if speed else 4,'before_paused':True if speed else core['before_paused'],
        'after_date':date,'after_native_index':4 if speed else 0,'after_paused':speed==0,
        'exception_code':0,'freeze_session':False,'retry_allowed':False,'diplomacy_submitted':False}
    expected.update({k:True for k in ('write_entered','callback_returned','callback_success','result_destroyed','readback_observed','readback_matches')})
    same_typed({k:core[k] for k in expected},expected,'Speed handler/cleanup/date proof differs')


class Job:
    def __init__(self,argv,stem,spawn=subprocess.Popen):
        self.argv=argv;self.stdout=None;self.stderr=None
        self.process=None
        try:
            self.stdout=Path(str(stem)+'.stdout').open('xb');self.stderr=Path(str(stem)+'.stderr').open('xb')
            self.process=spawn(argv,cwd=ROOT,stdout=self.stdout,stderr=self.stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:self.close();raise
    def poll(self):
        code=self.process.poll()
        if code is not None:self.close()
        return code
    def close(self):
        for stream in (self.stdout,self.stderr):
            if stream is not None and not stream.closed:stream.flush();os.fsync(stream.fileno());stream.close()


class Adapter:
    """One exclusive run; tick() never waits for a CLI or observer future."""
    def __init__(self,plan,observer,*,clock=now_ms,spawn=subprocess.Popen):
        verify_inputs()
        self.plan=batch.validate_plan(plan);self.clock=clock;self.spawn=spawn;self.observer=observer
        require(callable(observer),'Explicit reviewed observer callback required')
        self.output=ROOT/'work/runtime/native1375-v17';self.run_dir=self.output/('batch-'+plan['run_id'])
        require(not self.run_dir.exists(),'Batch already exists; never resume')
        require(self.output.resolve()==self.output,'Linked output directory')
        self.run_dir.mkdir();self.audit=(self.run_dir/'journal.jsonl').open('xb');self.audit_bytes=0
        manifest=read_json(self.output/'build.json',65536)
        self.scope=dict(plan=self.plan,manifest_sha256=bounded_hash(self.output/'build.json',65536),dll_sha256=manifest['dll_sha256'],
            fixture_profile_sha256=hashlib.sha256(batch.canonical(manifest['fixture_profile']).encode('ascii')).hexdigest())
        self.scope_path=self.run_dir/'scope.json';durable_new(self.scope_path,self.scope)
        self.model=batch.Batch(plan,self.record);self.pool=ThreadPoolExecutor(max_workers=1)
        self.work=None;self.status_job=None;self.status_box=None;self.status_count=0;self.next_status=0;self.terminal_recorded=False
        self.status_bytes=0
        self.record(dict(event='batch_opened',scope=self.scope,automatic_retry=False,production=False))

    def finish(self):
        """No retries/republishing; preserve unknown child PIDs in the final audit."""
        require(self.model.state in ('complete','terminal'),'Cannot close a running batch')
        summary=self.model.summary()
        active=[]
        jobs=[self.status_job[0]] if self.status_job else []
        if self.work and 'job' in self.work:jobs.append(self.work['job'])
        for job in jobs:
            if job.poll() is None:active.append(job.process.pid)
            # Closing our inherited-file handles does not cancel a publisher or
            # interfere with its exact-process watchdog.
            job.close()
        if self.status_job and self.status_job[0].process.poll() is None:
            # Only our read-only helper is terminable here; never the game or
            # an outstanding speed watchdog/publisher.
            process=self.status_job[0].process
            process.kill();process.wait(timeout=5)
            active.remove(process.pid)
        summary['still_running_helper_pids']=active
        self.record(dict(event='batch_finished',summary=summary))
        durable_new(self.run_dir/'summary.json',summary)
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.audit.close()
        return summary

    def record(self,value):
        raw=(batch.canonical(value)+'\n').encode('ascii');require(len(raw)<=MAX_JSON and self.audit_bytes+len(raw)<=MAX_JOURNAL,'Audit bound exceeded')
        self.audit.write(raw);self.audit.flush();os.fsync(self.audit.fileno());self.audit_bytes+=len(raw)

    def stop(self,reason):
        self.model.stop(reason)
        if not self.terminal_recorded:
            self.terminal_recorded=True
            self.record(dict(event='batch_terminal',reason=reason,automatic_retry=False,
                active_cli_pid=self.work['job'].process.pid if self.work and 'job' in self.work else None))
        return self.model.summary()

    def tick(self):
        now=self.clock()
        if self.model.state in ('complete','terminal'):return self.model.summary()
        try:
            if self.status_job:
                job,path,started=self.status_job;code=job.poll()
                require(now-started<=10000,'Read-only status worker exceeded deadline')
                if code is not None:
                    require(code==0,'Read-only frozen status worker failed')
                    self.status_box=read_json(path);self.status_job=None;self.next_status=now+350
                    self.status_bytes+=path.stat().st_size
                    require(self.status_bytes<=128*1024*1024,'Aggregate status capture budget exhausted')
                    self.record(dict(event='status_snapshot',path=str(path.relative_to(ROOT)),sha256=bounded_hash(path)))
            if self.status_job is None and now>=self.next_status:
                require(self.status_count<MAX_STATUS,'Read-only poll budget exhausted');self.status_count+=1
                stem=self.run_dir/f'status-{self.status_count:04d}';path=Path(str(stem)+'.json')
                args=[sys.executable,'-B',str(HERE/'adapter.py'),'worker-status','--scope',str(self.scope_path),'--output',str(path)]
                self.status_job=(Job(args,stem,self.spawn),path,now)
            if self.status_box is None:return {'state':'waiting_for_initial_status'}
            # Never issue from a stale cached snapshot while a new reader is running.
            if now-self.status_box['observed_uptime_ms']>2500:
                if self.model.inflight and now>self.model.inflight['deadline_ms']:return self.stop('job_deadline_unknown_no_retry')
                return {'state':'waiting_for_current_status'}
            h=health_from_status(self.status_box,self.scope,now)
            decision=self.model.next(h,now)
            if decision['state']=='terminal':return self.stop(self.model.failure)
            if self.work:
                w=self.work;c=w['command'];result=None
                if 'future' in w:
                    if w['future'].done():result=w['future'].result()
                else:
                    code=w['job'].poll()
                    if code is not None:
                        require(code==0,'Publisher CLI failed; intent retained, no retry')
                        if 'published' not in w:
                            w['published']=capture_report(w['capture'],c,w['job'].argv)
                            with w['capture'].open('r+b') as stream:stream.flush();os.fsync(stream.fileno())
                            self.record(dict(event='publisher_capture',command_id=w['id'],path=str(w['capture'].relative_to(ROOT)),sha256=bounded_hash(w['capture'])))
                        supervisor=None
                        if c['kind']=='speed':
                            path=self.output/f"session-{c['pid']}-{c['creation']}"/f"{c['sequence']:020}.supervisor.jsonl"
                            require(Path(w['published']['report']).resolve()==path.resolve(),'Supervisor output path differs; no external path accepted')
                            with path.open('rb') as stream:raw=stream.read(65537)
                            require(len(raw)<=65536 and raw.endswith(b'\n'),'Bounded complete supervisor log required')
                            supervisor=[json.loads(line) for line in raw.splitlines()]
                        result=native_receipt(c,self.status_box,w['published'],supervisor)
                if result is not None:
                    self.model.receive(w['id'],result,now)
                    if self.model.state=='terminal':return self.stop(self.model.failure)
                    self.work=None
                    self.record(dict(event='batch_progress',completed_rows=self.model.index,total_rows=36,next_sequence=self.model.last_sequence+1,
                        individual_effect_verified=False))
                    print(json.dumps({'completed_rows':self.model.index,'total_rows':36,'state':self.model.state}),flush=True)
                return self.model.summary() if self.model.state in ('complete','terminal') else {'state':'polling'}
            if decision['state']=='start_once':
                c=decision['command'];self.work={'id':decision['command_id'],'command':c}
                if c['kind']=='observe':self.work['future']=self.pool.submit(self.observer,dict(c))
                else:
                    args=batch.argv(c,sys.executable);capture=ROOT/args[args.index('--output')+1]
                    require(not capture.exists(),'Fixed publication capture already exists; no retry')
                    self.record(dict(event='cli_start_once',command_id=decision['command_id'],argv=args,capture=str(capture.relative_to(ROOT))))
                    self.work.update(capture=capture,job=Job(args,self.run_dir/f"publish-{c['sequence']:020}",self.spawn))
            return decision
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as error:return self.stop(str(error))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    worker=sub.add_parser('worker-status');worker.add_argument('--scope',type=Path,required=True);worker.add_argument('--output',type=Path,required=True)
    run=sub.add_parser('run');run.add_argument('--plan',type=Path,required=True);run.add_argument('--ack-disposable',action='store_true',required=True)
    args=parser.parse_args()
    if args.operation=='worker-status':status_worker(args.scope,args.output)
    else:
        verify_inputs()
        observer_path=HERE.parent/'v17-batch-census-r3'/'census.py'
        observer_spec=importlib.util.spec_from_file_location('reviewed_batch_census',observer_path)
        observer=importlib.util.module_from_spec(observer_spec);observer_spec.loader.exec_module(observer)
        adapter=Adapter(read_json(args.plan,65536),observer.sample)
        started=time.monotonic()
        try:
            while adapter.model.state not in ('complete','terminal'):
                if time.monotonic()-started>1800:adapter.stop('total_batch_deadline_no_retry');break
                adapter.tick();time.sleep(0.05)
        except BaseException as error:
            adapter.stop('coordinator_interrupted_unknown_no_retry: '+str(error));raise
        finally:
            if adapter.model.state in ('complete','terminal'):adapter.finish()
        return 0 if adapter.model.state=='complete' else 2


if __name__=='__main__':raise SystemExit(main())
