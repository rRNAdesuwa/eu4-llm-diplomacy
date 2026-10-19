"""Four new synthetic controller/auth/result cases; no candidate import or status."""
from pathlib import Path
import copy,hashlib,json,sys,types,traceback
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EVENTS=[];RETURNED=0;LIMIT=8388608

def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def require(v,m):
    if not v:raise ValueError(m)
def raw(value):return (json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
def read(path,expected=None):
    global RETURNED
    size=path.stat().st_size
    require(0<=size<=4194304 and RETURNED+size+1<=LIMIT,'Offline source bound')
    with path.open('rb') as f:b=f.read(size+1)
    RETURNED+=len(b);EVENTS.append(dict(path=str(path),requested=size+1,returned=len(b)))
    require(len(b)==size and (expected is None or pin(b)==expected),'Offline source pin')
    return b
def module(name,b,path):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(b,str(path),'exec'),m.__dict__);return m
def expect_error(call,fragment):
    try:call()
    except ValueError as e:
        require(fragment in str(e),'Unexpected refusal');return str(e)
    raise AssertionError('Expected refusal did not occur')

def main():
    require(len(sys.argv)==2,'Exact source manifest SHA')
    mr=read(HERE/'source-manifest.json');require(pin(mr)['sha256']==sys.argv[1],'Frozen graph before cases')
    manifest=json.loads(mr);data={n:read(ROOT/n,p) for n,p in manifest['source_pins'].items()}
    rel=HERE.relative_to(ROOT).as_posix()+'/'
    c=module('_synthetic_support_contract',data[rel+'runtime_contract.py'],HERE/'runtime_contract.py')
    ctl=module('_synthetic_support_controller',data[rel+'controller.py'],HERE/'controller.py')
    build=json.loads(data[c.BUILD]);mapping={str(ROOT/n):b for n,b in data.items()}
    mapping[str(HERE/'source-manifest.json')]=mr
    subjects={'subject_source_manifest':c.triple(rel+'source-manifest.json',mr)}
    subjects.update({key:c.triple(rel+file,data[rel+file]) for key,file in
        [('subject_controller_pin','controller.py'),('subject_child_pin','child.py'),('subject_adapter_pin','text_config_adapter.py')]})
    review=dict(sealed=True,passed=True,blocking_findings=[],**subjects)
    peerpath=rel+'synthetic-peer.json';peer_manifest_path=rel+'synthetic-peer-manifest.json'
    peerraw=raw(review);peerm=raw({'synthetic_only':True})
    auth=dict(schema='EU4-SUPPORT-HEIR-CURRENT-STATUS-ONCE/1',sealed=True,live_authorized=True,
        executor='/root/diplomacy_static',selection=c.SELECTION,maximum_status_attempts=1,automatic_retry=False,
        build_authorization=c.triple(c.BUILD,data[c.BUILD]),budgets=build['future_live_budget_design'],operation='status',
        local_configuration_pin=build['local_configuration_pin_metadata'],**subjects,
        source_peer_review={'findings':c.triple(peerpath,peerraw),'manifest':c.triple(peer_manifest_path,peerm)})
    mapping[str(ROOT/peerpath)]=peerraw;mapping[str(ROOT/peer_manifest_path)]=peerm
    virtual_reads=[]
    def fake_read(path,expected=None):
        key=str(path);require(key in mapping,'No unlisted synthetic read')
        b=mapping[key];require(expected is None or pin(b)==expected,'Synthetic exact pin')
        virtual_reads.append(key);return b
    def verify(value):
        b=raw(value);mapping[str(HERE/'run-authorization.json')]=b
        return c.verify(fake_read,pin(b)['sha256'])
    cap=dict(schema='EU4-SUPPORT-HEIR-CURRENT/1',operation='status',status='selected_task_absent',
        selected_task_present=False,selection=c.SELECTION,errors=[],
        **{k:False for k in c.FLAGS},**{k:0 for k in
        ('requests_published','native_game_calls','game_fields_written','hooks_installed','saves','reloads')},
        selected_two_pass_equal=True,normal_context_exit=True,held_handle_cleared=True,commit_after_context_exit=True,
        close_os_return_checked=False,samples=[{'synthetic':True},{'synthetic':True}],raw_ordered_read_journal=[],
        budget_accounting={'limits':{'calls':4096,'bytes':524288,'single_read':65536},
          'entry_PE_identity_read':{'calls':1,'bytes':8192,'journaled':False},
          'shared':{'calls':0,'bytes':0,'largest':0}})
    game=dict(game_successful_opens=1,game_opens=[dict(closed=True,normal_context_exit=True,full_expected_hash=True)],
        explicit_returned={'game_disk':c.GAME_BYTES})
    results=[]
    cases=[
      ('support_auth_current_result_one_hash',lambda:(
        require(verify(auth)['auth']['selection']==c.SELECTION,'Support auth closure'),
        require(ctl.validate_capture(c,cap,{'exit_code':0})=='selected_task_absent','Support result closure'),
        ctl.validate_game_io(game,c))),
      ('peace_authorization_schema_rejected',lambda:
        expect_error(lambda:verify(dict(auth,schema='EU4-PEACE-V2-CURRENT-STATUS-ONCE/2')),'Distinct future once grant schema')),
      ('mismatched_adapter_peer_rejected',None),
      ('fourth_game_open_cannot_support_success',lambda:
        expect_error(lambda:ctl.validate_game_io(dict(game,game_successful_opens=4),c),'One to three complete intercepted game reads'))]
    def wrong_peer():
        wrong=copy.deepcopy(review);wrong['subject_adapter_pin']['sha256']='0'*64
        b=raw(wrong);mapping[str(ROOT/peerpath)]=b
        a=copy.deepcopy(auth);a['source_peer_review']['findings']=c.triple(peerpath,b)
        try:return expect_error(lambda:verify(a),'Source-peer exact subjects')
        finally:mapping[str(ROOT/peerpath)]=peerraw
    cases[2]=(cases[2][0],wrong_peer)
    failed=None
    for name,call in cases:
        try:call();results.append(dict(name=name,passed=True,runs=1))
        except BaseException as exc:
            failed=dict(name=name,type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
            results.append(dict(name=name,passed=False,runs=1));break
    post={n:pin(read(ROOT/n,p)) for n,p in manifest['source_pins'].items()}
    require(read(HERE/'source-manifest.json')==mr,'Frozen manifest post')
    result=dict(schema='EU4-SUPPORT-CONTROLLER-NEW-OFFLINE-CASES/1',source_manifest=pin(mr),
        cases=results,failure=failed,passed=failed is None and len(results)==4,maximum_cases=4,
        source_prepost_equal=post==manifest['source_pins'],read_events=EVENTS,returned=RETURNED,limit=LIMIT,
        synthetic_contract_read_calls=len(virtual_reads),synthetic_reads_add_physical_bytes=False,
        config_body_read=False,candidate_imports=0,CLI_executions=0,controller_main_executions=0,
        child_executions=0,PE_reads=0,game_process_accesses=0,old_tests=0,native_game_calls=0,
        real_authorization_written=False,automatic_retry=False,selected_effect_verified=False)
    b=raw(result)
    with (HERE/'offline-r1'/'cases.json').open('xb') as f:f.write(b)
    print(json.dumps({'passed':result['passed'],'cases':results,'failure':failed,'receipt':pin(b),'source_returned':RETURNED},ensure_ascii=True))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
