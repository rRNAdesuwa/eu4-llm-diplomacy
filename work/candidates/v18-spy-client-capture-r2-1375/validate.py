"""Bounded pinned-file and tempfile/fake tests, saving outputs with CREATE_NEW."""
from pathlib import Path
import argparse,json,subprocess,sys,time
from _binding import HERE,ROOT,PINS,read,sha
def descriptor(path):
    raw=read(path);return {'bytes':len(raw),'sha256':sha(raw)}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=False,exist_ok=False)
    index=json.loads(read(HERE/'candidate-index.json',65536))
    paths={ROOT/name for name in PINS}|{HERE/name for name in index['sources']}|{HERE/'candidate-index.json'}
    before={p.relative_to(ROOT).as_posix():descriptor(p) for p in sorted(paths)};results=[]
    for name,argv in [('check',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),('synthetic',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]:
        start=time.monotonic()
        with (out/(name+'.stdout')).open('xb') as stdout,(out/(name+'.stderr')).open('xb') as stderr:
            run=subprocess.run(argv,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=60)
        results.append({'name':name,'argv':argv,'exit_code':run.returncode,'seconds':time.monotonic()-start,'stdout':descriptor(out/(name+'.stdout')),'stderr':descriptor(out/(name+'.stderr'))})
    after={p.relative_to(ROOT).as_posix():descriptor(p) for p in sorted(paths)}
    value={'commands':results,'before':before,'after':after,'inputs_unchanged':before==after,'tracked_count':len(paths),'all_shell_sessions_collected':True,
           'actual_session_accessed':False,'game_process_accessed':False,'native_called':False,'native_recompiled':False}
    with (out/'validation.json').open('x',encoding='ascii') as stream:json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')
    ok=before==after and all(x['exit_code']==0 for x in results)
    print(json.dumps({'passed':ok,'validation':descriptor(out/'validation.json')}));return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
