from pathlib import Path
import hashlib,json,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def meta(p):
    with p.open('rb') as f:raw=f.read(4*1024*1024+1)
    assert len(raw)<=4*1024*1024
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def snapshot():
    names=[ROOT/n for n in json.loads((HERE/'input-pins.json').read_text())]+[HERE/n for n in json.loads((HERE/'source-index.json').read_text())['sources']]+[HERE/'source-index.json']
    return {str(p.relative_to(ROOT)).replace('\\','/'):meta(p) for p in names}
def main():
    out=HERE/'validation-results';out.mkdir(exist_ok=False);before=snapshot();results=[]
    for name,cmd in [('check',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]:
        start=time.monotonic()
        with (out/(name+'.stdout.txt')).open('xb') as stdout,(out/(name+'.stderr.txt')).open('xb') as stderr:
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=stdout,stderr=stderr)
            try:code=proc.wait(timeout=55)
            except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
        results.append({'argv':cmd,'exit_code':code,'seconds':time.monotonic()-start,'stdout':meta(out/(name+'.stdout.txt')),'stderr':meta(out/(name+'.stderr.txt'))})
    after=snapshot();record={'commands':results,'inputs_before':before,'inputs_after':after,'inputs_unchanged':before==after,'all_shell_sessions_collected':True,'pure_data_only':True,'new_decode_bytes':0,'formal_sources_modified':False,'production_ready':False}
    with (out/'validation.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'inputs':len(before),'unchanged':before==after,'exit_codes':[x['exit_code'] for x in results],'validation':meta(out/'validation.json')}))
    return 0 if before==after and all(x['exit_code']==0 for x in results) else 1
if __name__=='__main__':raise SystemExit(main())
