"""CreateNew offline validation; never installs generated files into bridge/."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def desc(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output=args.output.resolve();args.output.mkdir(exist_ok=False)
    idx=json.loads((HERE/'candidate-index.json').read_bytes())
    tracked={ROOT/p for p in idx['inputs']}|{HERE/'files'/p for p in idx['outputs']}
    tracked|={HERE/n for n in ('prepare.py','validate.py','test_bootstrap.py','test_contract_v2.py','input-pins.json','candidate-index.json','patch.diff','v2-documentation.md')}
    tracked|={ROOT/'work/local_config.py',ROOT/'bridge/native_build.py'}
    def snap():return {p.relative_to(ROOT).as_posix():desc(p)for p in sorted(tracked)}
    before=snap();runs=[]
    for i,cmd in enumerate([[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B',str(HERE/'test_bootstrap.py')]]):
        start=time.monotonic();result=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120);outputs=[]
        for key,b in [('stdout',result.stdout),('stderr',result.stderr)]:
            if len(b)>2*1024*1024:raise ValueError('capture bound')
            out=args.output/f'{i}.{key}.txt'
            with out.open('xb')as f:f.write(b)
            outputs.append({'path':out.relative_to(ROOT).as_posix(),**desc(out)})
        runs.append({'argv':cmd,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-start,'outputs':outputs})
    after=snap();passed=before==after and all(r['exit_code']==0 for r in runs)
    v=dict(schema=1,status='passed'if passed else'failed',before=before,after=after,inputs_unchanged=before==after,runs=runs,formal_materialized=False,game_accessed=False,native_called=False,production_ready=False)
    with(args.output/'validation.json').open('x',encoding='utf-8')as f:json.dump(v,f,indent=2);f.write('\n')
    print(json.dumps({'status':v['status'],'validation':desc(args.output/'validation.json'),'tracked':len(tracked)}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
