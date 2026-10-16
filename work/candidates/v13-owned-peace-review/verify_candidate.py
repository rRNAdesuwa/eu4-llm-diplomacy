"""Compile isolated actual v13 candidate objects and run the shared pure stage test.

No DLL link, materialization, process access, game call, or default-layout rerun.
All validation evidence uses a fresh directory and exclusive file creation.
"""
from __future__ import annotations
import datetime
import hashlib
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GEN = HERE / 'generated/work/native/v13'
FLAGS = ['/nologo','/std:c++17','/EHsc','/O2','/W4','/WX','/MT','/GS','/utf-8','/showIncludes']

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def create(path,raw):
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
def encoded(value): return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()
def descriptor(path): return {'path':path.name,'sha256':digest(path),'bytes':path.stat().st_size}

def main():
    parent=HERE/'validation-results'; parent.mkdir(exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=parent/('candidate-'+stamp+'-'+uuid.uuid4().hex); out.mkdir()
    create(out/'claim.json',encoded({'purpose':'v13_isolated_objects_and_shared_stage_checker','created_utc':stamp,'retry':False}))
    report={'schema':'v13_owned_peace_candidate_validation_v1','created_utc':stamp,'passed':False,
        'compiles':[],'check_count':0,'failure_points':[], 'run_exit':None,
        'game_process_access':False,'native_game_functions_called':False,'dll_built':False,
        'host_or_core_linked':False,'materialized':False,'default_layout_tests_repeated':False,
        'runtime_verified':False,'execution_verified':False}
    try:
        helper_path=ROOT/'work/candidates/owned-peace-lifecycle-review/verify_checker.py'
        spec=importlib.util.spec_from_file_location('review_compiler_helper',helper_path)
        helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        review=json.loads((HERE/'review.json').read_bytes())
        report['review_sha256']=digest(HERE/'review.json')
        report['compiler_helper_sha256']=digest(helper_path)
        report['inputs']=[{'path':item['path'],'sha256':item['sha256']}
                          for item in review['candidate_files']+review['outputs']]
        report['inputs'].append({'path':'review.json','sha256':report['review_sha256']})
        checked=helper.run([sys.executable,'-B',str(HERE/'prepare.py'),'--check'],ROOT)
        create(out/'prepare-check.stdout.txt',checked.stdout);create(out/'prepare-check.stderr.txt',checked.stderr)
        report['prepare_check_exit']=checked.returncode
        if checked.returncode:raise ValueError('Candidate --check failed')
        compiler,env=helper.compiler_environment(out)
        report['compiler']={'path':compiler,'sha256':digest(Path(compiler)),'flags':FLAGS}
        plans=[('host',GEN/'research-lab-1375.cpp',False,
                ['owned-peace-stage-1375.h','owned-peace-host-1375.inc','peace-owned-lifecycle-1375.h','research-lab-bootstrap-1375.inc']),
               ('owned_core',GEN/'peace-owned-lifecycle-1375.cpp',False,
                ['peace-owned-lifecycle-1375.h','default-contract.h','pins.h']),
               ('shared_stage_test',HERE/'test_stage.cpp',True,['owned-peace-stage-1375.h','peace-owned-lifecycle-1375.h'])]
        for name,source,link_test,headers in plans:
            obj=out/(name+'.obj');exe=out/(name+'.exe');pdb=out/(name+'.pdb')
            if any(p.exists() for p in (obj,exe,pdb)):raise FileExistsError('Existing compile output')
            args=[compiler,*FLAGS,*([] if link_test else ['/c']),str(source),'/Fo'+str(obj),'/Fd'+str(pdb)]
            if link_test:args.append('/Fe'+str(exe))
            result=helper.run(args,out,env=env)
            stdout=out/(name+'.stdout.txt');stderr=out/(name+'.stderr.txt')
            create(stdout,result.stdout);create(stderr,result.stderr)
            text=(result.stdout+result.stderr).decode('mbcs',errors='replace')
            includes=text.replace('/','\\').lower()
            item={'name':name,'source':source.relative_to(ROOT).as_posix(),'source_sha256':digest(source),
                'exit':result.returncode,'linked_pure_test_only':link_test,
                'required_headers':{h:str(GEN/h).lower() in includes for h in headers},
                'output':[descriptor(stdout),descriptor(stderr)],
                'diagnostics':[line for line in text.splitlines() if re.search(r'\b(?:warning|error) [A-Z]+\d+',line,re.I)]}
            if obj.exists():item['object']=descriptor(obj)
            if exe.exists():item['pure_test_executable']=descriptor(exe)
            report['compiles'].append(item)
            if result.returncode or not obj.exists() or not all(item['required_headers'].values()):
                raise ValueError('Actual candidate compilation failed: '+name)
        exe=out/'shared_stage_test.exe'
        tested=helper.run([str(exe)],out,timeout=15)
        create(out/'run.stdout.txt',tested.stdout);create(out/'run.stderr.txt',tested.stderr)
        report['run_exit']=tested.returncode
        text=tested.stdout.decode('ascii')
        match=re.fullmatch(r'(?:FAIL: [^\r\n]+\r?\n)*(\d+) synthetic checks; (\d+) failures\r?\n',text)
        if not match:raise ValueError('Unexpected shared stage test output')
        report['check_count'],report['failure_count']=map(int,match.groups())
        report['failure_points']=re.findall(r'^FAIL: (.+)$',text,re.M)
        report['run_output']=[descriptor(out/'run.stdout.txt'),descriptor(out/'run.stderr.txt')]
        if any(out.glob('*.dll')):raise ValueError('Unexpected DLL output')
        if sorted(p.name for p in out.glob('*.exe'))!=['shared_stage_test.exe']:raise ValueError('Unexpected linked executable')
        if any(digest(HERE/i['path'])!=i['sha256'] for i in report['inputs']):raise ValueError('Candidate changed during compile/test')
        final_check=helper.run([sys.executable,'-B',str(HERE/'prepare.py'),'--check'],ROOT)
        create(out/'post-check.stdout.txt',final_check.stdout);create(out/'post-check.stderr.txt',final_check.stderr)
        report['post_check_exit']=final_check.returncode
        report['passed']=tested.returncode==0 and report['failure_count']==0 and report['check_count']>0 and final_check.returncode==0
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
    create(out/'validation.json',encoded(report))
    print(json.dumps({'path':str(out/'validation.json'),'sha256':digest(out/'validation.json'),
        'passed':report['passed'],'compiles':[(c['name'],c['exit']) for c in report['compiles']],
        'checks':report['check_count'],'run_exit':report['run_exit'],'error':report.get('error')}))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
