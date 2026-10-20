"""Capture bounded offline checks only, always collecting both child processes."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def read(path,limit=2097152):
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Validation input budget')
    return raw

def snapshot():
    pins=json.loads(read(HERE/'input-pins.json'))
    paths=[ROOT/x for x in pins]+[HERE/x for x in json.loads(read(HERE/'source-index.json'))['sources']]+[HERE/'source-index.json']
    return {p.relative_to(ROOT).as_posix():{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for p in paths for raw in [read(p)]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=False,exist_ok=False);before=snapshot();results=[]
    for name,command in [('check',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]:
        started=time.monotonic()
        with (out/(name+'.stdout')).open('xb') as stdout,(out/(name+'.stderr')).open('xb') as stderr:
            process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr)
            try:code=process.wait(timeout=55)
            except subprocess.TimeoutExpired:
                process.kill();process.wait();raise
        results.append({'name':name,'argv':command,'exit_code':code,'elapsed_seconds':time.monotonic()-started})
    after=snapshot()
    record={'scope':'offline_synthetic_only','before':before,'after':after,'inputs_unchanged':before==after,'commands':results,
            'all_children_collected':True,'actual_process_access':False,'native_build':False,'stage_published':False}
    for name in ('check.stdout','check.stderr','tests.stdout','tests.stderr'):
        raw=read(out/name);record.setdefault('outputs',{})[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    with (out/'validation.json').open('x',encoding='utf-8',newline='\n') as stream:json.dump(record,stream,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({'validation':str(out/'validation.json'),'inputs_unchanged':before==after,'commands':results},sort_keys=True))
    return 0 if before==after and all(x['exit_code']==0 for x in results) else 1

if __name__=='__main__':raise SystemExit(main())
