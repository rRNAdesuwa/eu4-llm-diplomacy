"""Offline only, bounded logs; CreateNew output and pre/post source hashes."""
import argparse,datetime,hashlib,json,subprocess,sys,uuid
from pathlib import Path
from prepare import HERE,ROOT,load,digest
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
 out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
 index=load(HERE/'source-index.json');names=sorted(set(index['inputs'])|set(index['sources'])|{str((HERE/'source-index.json').relative_to(ROOT)).replace('\\','/')})
 before={n:digest(ROOT/n) for n in names};commands=[]
 for label,cmd in [('trace',[sys.executable,'-B',str(HERE/'trace.py'),'--check']),('prepare',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),
                   ('models',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]:
  with (out/(label+'.stdout.txt')).open('xb') as f:
   r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=60,check=False)
  commands.append({'label':label,'argv':cmd,'exit_code':r.returncode,'stdout_sha256':digest(out/(label+'.stdout.txt'))})
 after={n:digest(ROOT/n) for n in names};ok=before==after and all(x['exit_code']==0 for x in commands)
 j={'schema':1,'purpose':'favor_trust_reduce_offline_validation','source_before':before,'source_after':after,
    'source_unchanged':before==after,'commands':commands,'passed':ok,'game_accessed':False,'new_decode_bytes':0,'shells_collected':True}
 with (out/'validation.json').open('x',encoding='utf8') as f:json.dump(j,f,indent=2);f.write('\n')
 print(json.dumps({'passed':ok,'inputs':len(before),'validation_sha256':digest(out/'validation.json'),'output':str(out)}))
 return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
