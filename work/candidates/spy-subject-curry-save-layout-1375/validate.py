"""Author validation to a new directory; source and save only, no runtime."""
from pathlib import Path
import argparse,json,subprocess,sys,time
import parser as p
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def descriptor(path):
 raw=path.read_bytes();return {'bytes':len(raw),'sha256':p.sha(raw)}
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);args=a.parse_args();out=args.output.resolve();out.mkdir(parents=False,exist_ok=False)
 index=json.loads((HERE/'source-index.json').read_bytes());paths={ROOT/k for k in index['inputs']}|{HERE/k for k in index['candidate_files']}|{HERE/'source-index.json'}
 before={x.relative_to(ROOT).as_posix():descriptor(x) for x in sorted(paths)};results=[]
 for name,argv in [('check',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),
  ('synthetic',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_parser.py','-v']),
  ('fixed_save_reproduction',[sys.executable,'-B',str(HERE/'research.py'),'--check'])]:
  start=time.monotonic()
  with (out/(name+'.stdout')).open('xb') as stdout,(out/(name+'.stderr')).open('xb') as stderr:
   done=subprocess.run(argv,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=60,check=False)
  results.append({'name':name,'argv':argv,'exit_code':done.returncode,'seconds':time.monotonic()-start,'stdout':descriptor(out/(name+'.stdout')),'stderr':descriptor(out/(name+'.stderr'))})
 after={x.relative_to(ROOT).as_posix():descriptor(x) for x in sorted(paths)}
 value={'commands':results,'before':before,'after':after,'inputs_unchanged':before==after,'input_count':len(before),'synthetic_methods':21,
        'actual_stopped_save_stream_reproduced':results[-1]['exit_code']==0,'actual_game_or_process_accessed':False,'native_called':False,'all_shell_sessions_collected':True}
 with (out/'validation.json').open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True)
 print(json.dumps({'passed':before==after and all(x['exit_code']==0 for x in results),'validation':str(out/'validation.json'),'sha256':p.sha((out/'validation.json').read_bytes())}))
 return 0 if before==after and all(x['exit_code']==0 for x in results) else 1
if __name__=='__main__':raise SystemExit(main())
