"""One new synthetic case batch under the exact frozen Job helper; no live route."""
from pathlib import Path
import hashlib,json,sys,types,traceback
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EVENTS=[];TOTAL=0;LIMIT=8388608
def require(v,m):
    if not v:raise ValueError(m)
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(p,expected=None):
    global TOTAL
    size=p.stat().st_size;require(0<=size<=4194304 and TOTAL+size+1<=LIMIT,'Runner ordinary pre-reserve')
    with p.open('rb') as f:b=f.read(size+1)
    TOTAL+=len(b);EVENTS.append(dict(path=str(p),requested=size+1,returned=len(b)))
    require(len(b)==size and (expected is None or pin(b)==expected),'Runner exact pin');return b
def save(name,v):
    b=(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
    require(len(b)<=4194304,'Runner retained bound')
    with (HERE/'offline-r1'/name).open('xb') as f:f.write(b)
    return pin(b)
def main():
    require(len(sys.argv)==2,'Frozen source SHA only')
    mr=read(HERE/'source-manifest.json');require(pin(mr)['sha256']==sys.argv[1],'Frozen source manifest')
    m=json.loads(mr);pre={n:pin(read(ROOT/n,p)) for n,p in m['source_pins'].items()}
    require(pre==m['source_pins'],'Frozen inputs')
    out=HERE/'offline-r1';out.mkdir(exist_ok=False)
    save('claim.json',{'maximum_new_cases':4,'batch_attempts':1,'automatic_retry':False,'source_manifest':pin(mr),'runtime_authorized':False})
    j='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
    code=read(ROOT/j,m['source_pins'][j])
    jobs=types.ModuleType('_support_new_cases_job');jobs.__file__=str(ROOT/j)
    exec(compile(code,jobs.__file__,'exec'),jobs.__dict__)
    job=jobs.run_cli_tree([sys.executable,'-I','-B',str(HERE/'test_controller_closure.py'),sys.argv[1]],
        ROOT,out/'stdout.txt',out/'stderr.txt',timeout_seconds=45,memory_limit=805306368)
    save('job.json',job)
    failure=None
    try:
        stdout=read(out/'stdout.txt');stderr=read(out/'stderr.txt')
        require(len(stdout)<=2097152 and len(stderr)<=2097152,'Job output bound')
        require(job['error']is None and job['exit_code']==0 and job['job_active_processes_final']==0
            and job['direct_child_collected']is True,'New case batch failed; no retry')
        cases=json.loads(read(out/'cases.json'));require(cases['passed']is True and len(cases['cases'])==4,'Four new cases')
        post={n:pin(read(ROOT/n,p)) for n,p in m['source_pins'].items()}
        require(post==pre and read(HERE/'source-manifest.json')==mr,'Source postguards')
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
        save('failure.json',failure)
    receipt=save('receipt.json',dict(passed=failure is None,failure=failure,job=job,read_events=EVENTS,
        source_returned=TOTAL,limit=LIMIT,maximum_cases=4,old_tests=0,candidate_CLI_executions=0,
        game_process_accesses=0,real_env_operations=0,PE_reads=0,native_game_calls=0,automatic_retry=False))
    print(json.dumps({'passed':failure is None,'receipt':receipt,'job':job,'source_returned':TOTAL},ensure_ascii=True))
    return 0 if failure is None else 1
if __name__=='__main__':raise SystemExit(main())
