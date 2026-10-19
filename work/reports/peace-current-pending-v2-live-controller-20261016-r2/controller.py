"""Future one contained current-status attempt; build grant alone never runs it."""
from pathlib import Path
import hashlib,json,re,sys,time,traceback,types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
READ_LIMIT=33554432
READ_EVENTS=[]
RETURNED=0

def require(ok,why):
    if not ok:raise ValueError(why)

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def decode(raw):
    def pairs(items):
        out={}
        for k,v in items:
            require(k not in out,'Duplicate JSON');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Nonfinite JSON'))

def read(path,expected=None,maximum=4194304):
    global RETURNED
    path=Path(path);size=path.stat().st_size;require(0<=size<=maximum<=4194304,'Controller ordinary bound')
    requested=size+1;e={'path':str(path),'requested':requested,'returned':0,'completed':False};READ_EVENTS.append(e)
    require(RETURNED+requested<=READ_LIMIT,'Controller pre-read full-request reserve')
    try:
        with path.open('rb') as f:raw=f.read(requested)
        e.update(returned=len(raw),completed=True);RETURNED+=len(raw)
        require(len(raw)==size,'Controller file size changed')
        if expected is not None:require(pin(raw)==expected,'Exact controller source/reference pin')
        return raw
    except BaseException as exc:e['error']=type(exc).__name__+': '+str(exc);raise

def save(name,value):
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
    require(len(raw)<=4194304,'Controller retained JSON bound')
    with (HERE/name).open('xb') as f:f.write(raw)
    return pin(raw)

def bootstrap(sha):
    require(re.fullmatch('[0-9a-f]{64}',sha),'Only future once grant SHA')
    raw=read(HERE/'run-authorization.json');require(pin(raw)['sha256']==sha,'Future grant raw SHA before parse');a=decode(raw)
    p=a['subject_source_manifest'];require(p['path']==(HERE/'source-manifest.json').relative_to(ROOT).as_posix(),'Fixed controller source manifest')
    mr=read(HERE/'source-manifest.json',{k:p[k] for k in ('bytes','sha256')});m=decode(mr)
    name=(HERE/'runtime_contract.py').relative_to(ROOT).as_posix();code=read(HERE/'runtime_contract.py',m['source_pins'][name])
    module=types.ModuleType('_peace_v2_once_contract_controller');module.__file__=str(HERE/'runtime_contract.py')
    exec(compile(code,module.__file__,'exec'),module.__dict__)
    return module,module.verify(read,sha)

def validate_capture(contract,capture,job):
    require(type(capture)is dict and capture.get('operation')=='status','Frozen CLI status JSON only')
    require(all(capture.get(k)is False for k in contract.FLAGS),'Current-only authority flags')
    require(all(type(capture.get(k))is int and capture[k]==0 for k in ('requests_published','native_game_calls','game_fields_written','hooks_installed','saves','reloads')),'No side effects')
    if 'selection' in capture:require(capture['selection']==contract.SELECTION,'CLI selection changed')
    state=capture.get('status');require(state in ('unknown','selected_peace_queue_present','selected_peace_queue_absent'),'Fixed current result states')
    if state=='unknown':
        require(job['exit_code']==2 and capture.get('selected_queue_presence')is None and capture.get('commit_after_context_exit',False)is False,'Unknown cannot commit')
    else:
        require(job['exit_code']==0 and capture.get('errors')==[],'Selected observation exit/errors')
        require(type(capture.get('selected_queue_presence'))is bool and capture['selected_queue_presence']is (state=='selected_peace_queue_present'),'Strict boolean presence')
        require(all(capture.get(k)is True for k in ('selected_two_pass_equal','normal_context_exit','held_handle_cleared','commit_after_context_exit')),'Normal close/final guard commit')
    if 'close_os_return_checked' in capture:require(capture['close_os_return_checked']is False,'OS CloseHandle return remains unverified')
    rpm=capture.get('rpm_budget')
    if rpm is not None:
        require(rpm['limits']=={'calls':4096,'bytes':524288,'single_read':65536},'RPM unchanged')
        require(type(rpm['calls_attempted'])is int and 0<=rpm['calls_attempted']<=4096,'RPM calls')
        require(type(rpm['bytes_requested'])is int and 0<=rpm['bytes_requested']<=524288,'RPM byte requests')
    return state

def validate_io(contract,value,budgets,sha):
    require(value['authorization_sha256']==sha and value['source_prepost_equal']is True and value['failure']is None,'Child auth/source closure')
    require(value['status_attempts']==1 and type(value['status_attempts'])is int,'Exactly one child status')
    require(value['budgets']==budgets,'Child budgets unchanged')
    limits={'ordinary':budgets['ordinary_child_returned'],'delegated_fixed_host':budgets['fixed_host_returned'],'game_disk':budgets['game_disk_returned_with_one_chunk_reservation']}
    for k,limit in limits.items():
        n=value['explicit_returned'][k];require(type(n)is int and 0<=n<=limit,'Child returned-byte cap')
    for k,limit in [('delegated_fixed_host',budgets['fixed_host_attempts']),('game_disk',budgets['game_disk_attempts'])]:
        n=value['read_attempts'][k];require(type(n)is int and 0<=n<=limit,'Child attempts cap')
    require(type(value['game_successful_opens'])is int and 0<=value['game_successful_opens']<=3,'Game open cap')
    require(all(value.get(k)is False for k in ('automatic_retry','Frida_called')),'No child retry/Frida')
    require(all(type(value.get(k))is int and value[k]==0 for k in ('native_game_calls','requests_published','game_fields_written','tests_run')),'No child native/test operations')


def validate_config_io(value,expected,observed=False):
    require(type(value)is dict and value.get('schema')=='EU4-EXACT-CONFIG-SNAPSHOT/1','New configuration ledger required')
    require(value['expected_pin']=={k:expected[k] for k in ('bytes','sha256')},'Configuration exact grant pin')
    require(value['maximum_bytes']==65536 and value['maximum_snapshots']==16,'Configuration bounds')
    require(type(value['opened_snapshots'])is int and 0<=value['opened_snapshots']<=16,'Configuration snapshot limit')
    require(value['physical_category']=='ordinary' and value['virtual_reads_add_physical_bytes']is False,'Configuration physical accounting')
    require(value['configuration_values_logged']is False and value['real_path_override_argument']is False,'Configuration redaction/path contract')
    if observed:
        require(1<=value['opened_snapshots']<=16 and value['events'],'Selected status requires pinned configuration snapshot')
        require(all(e.get('accepted')is True and e.get('binary_closed')is True and e.get('virtual_closed')is True and e.get('virtual_normal_exit')is True and e.get('raw_pin')==value['expected_pin'] and e.get('error')is None for e in value['events']),'Configuration accepted/closed snapshots only')

def main():
    require(len(sys.argv)==2,'Only one future grant SHA; no overrides')
    require(not any((HERE/n).exists() for n in ('claim.json','receipt.json','control-failure.json','actual-manifest.json','attempt-start.json')),'Prior attempt/history is permanent; no retry')
    sha=sys.argv[1];started=time.monotonic();contract=None;before=None;after=None;job=None;capture=None;child_io=None
    failure=None;attempts=0;post_attempted=False;observed=False;state='unknown';claim_created=False
    try:
        contract,before=bootstrap(sha)
        argv=[sys.executable,'-I','-B',str(HERE/'child.py'),sha]
        save('claim.json',{'schema':'EU4-PEACE-V2-CONTROLLER-ONCE-CLAIM/1','exclusive':True,'authorization_sha256':sha,
            'source_manifest':before['auth']['subject_source_manifest'],'selection':contract.SELECTION,'argv':argv,'maximum_status_attempts':1,'automatic_retry':False})
        claim_created=True
        save('source-before.json',before['fingerprint'])
        code=before['data'][contract.JOB]
        jobs=types.ModuleType('_peace_v2_once_frozen_job');jobs.__file__=str(ROOT/contract.JOB)
        exec(compile(code,jobs.__file__,'exec'),jobs.__dict__)
        save('attempt-start.json',{'authorization_sha256':sha,'status_attempts_from':0,'status_attempts_to':1,'selection':contract.SELECTION,'argv':argv,'no_retry':True})
        attempts=1
        job=jobs.run_cli_tree(argv,ROOT,HERE/'stdout.txt',HERE/'stderr.txt',timeout_seconds=45,memory_limit=805306368)
        save('job.json',job)
        post_attempted=True;after=contract.verify(read,sha);save('source-after.json',after['fingerprint'])
        require(before['fingerprint']==after['fingerprint'],'Controller source/grant/reviews changed')
        stdout=read(HERE/'stdout.txt',maximum=2097152);stderr=read(HERE/'stderr.txt',maximum=2097152)
        require(job['error']is None and job['exit_code']in (0,2) and job['job_active_processes_final']==0 and job['direct_child_collected']is True,'Job not cleanly collected')
        child_io=decode(read(HERE/'child-io.json'));validate_io(contract,child_io,before['budgets'],sha)
        require(child_io['exit_code']==job['exit_code'],'Child receipt exit differs')
        validate_config_io(child_io['text_config'],before['auth']['local_configuration_pin'])
        capture=decode(stdout.decode('ascii'))
        with (HERE/'capture.json').open('xb') as f:f.write(stdout)
        state=validate_capture(contract,capture,job)
        if state!='unknown':
            validate_config_io(child_io['text_config'],before['auth']['local_configuration_pin'],observed=True)
            require(child_io['game_successful_opens']==3 and len(child_io['game_opens'])==3,'Expected three disk paths completed')
            require(all(x.get('closed')is True and x.get('normal_context_exit')is True and x.get('full_expected_hash')is True for x in child_io['game_opens']),'All exact game hashes closed')
            require(child_io['explicit_returned']['game_disk']==115387512,'Expected three complete disk byte totals')
            observed=True
    except BaseException as exc:
        failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()};state='unknown';observed=False
        # An existing claim/failure is never overwritten; no second child or retry.
        if not (HERE/'control-failure.json').exists():save('control-failure.json',failure)
    finally:
        if before is not None and not post_attempted:
            try:
                post_attempted=True;after=contract.verify(read,sha)
                if claim_created:save('source-after.json',after['fingerprint'])
                require(before['fingerprint']==after['fingerprint'],'Failure-path source postguard differs')
            except BaseException as exc:
                failure=failure or {'type':type(exc).__name__,'message':str(exc)};observed=False;state='unknown'
    result={'schema':'EU4-PEACE-V2-CURRENT-STATUS-CONTROL/2','control_passed':failure is None,'status':state,
        'current_state_observed':observed,'selected_queue_presence':capture.get('selected_queue_presence') if observed else None,
        'status_attempts':attempts,'maximum_status_attempts':1,'authorization_sha256':sha,'selection':None if contract is None else contract.SELECTION,
        'failure':failure,'job':job,'source_prepost_equal':before is not None and after is not None and before['fingerprint']==after['fingerprint'],
        'capture_is_accepted_only_when_control_passed':True,'child_io':child_io,'controller_read_events':READ_EVENTS,
        'controller_returned':RETURNED,'controller_returned_limit':READ_LIMIT,'controller_attempted_requested':sum(x['requested'] for x in READ_EVENTS),
        'known_normal_IO_closure':False,'OS_import_cache_IO_excluded':True,'independent_live_replay_pending':True,
        'close_os_return_checked':False,'automatic_retry':False,'native_game_calls':0,'requests_published':0,'game_fields_written':0,
        'selected_effect_verified':False,'original_request_correlated':False,'AI_acceptance_verified':False,'peace_completed':False,
        'native_ready':False,'world_lease':False,'atomic_snapshot':False,'persistence_verified':False,'seconds':round(time.monotonic()-started,6)}
    rp=save('receipt.json',result)
    # File pins are bounded ordinary reads, separate from child/target/RPM ledgers.
    names=['claim.json','attempt-start.json','source-before.json','source-after.json','job.json','stdout.txt','stderr.txt','child-claim.json','child-status-start.json','child-io.json','capture.json','control-failure.json','receipt.json']
    retained={}
    for n in names:
        if (HERE/n).is_file():retained[n]=pin(read(HERE/n))
    mp=save('actual-manifest.json',{'schema':'EU4-PEACE-V2-CURRENT-STATUS-DELIVERY/2','sealed':True,'retained':retained,
        'authorization_sha256':sha,'control_passed':failure is None,'current_state_observed':observed,'status_attempts':attempts,
        'source_prepost_equal':result['source_prepost_equal'],'controller_returned_including_seal':RETURNED,'controller_read_events':READ_EVENTS,
        'native_ready':False,'selected_effect_verified':False,'authorizes_retry':False,'independent_live_replay_pending':True})
    print(json.dumps({'status':state,'control_passed':failure is None,'current_state_observed':observed,'receipt':rp,'manifest':mp,'status_attempts':attempts,'job':job},ensure_ascii=True))
    return 0 if failure is None else 1

if __name__=='__main__':raise SystemExit(main())
