"""Bounded compiler and isolated tests. Never invokes BridgeStart or opens EU4."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys
import build_manifest as b

HERE=Path(__file__).resolve().parent
HOST_REVIEW=b.ROOT/'work/review-results/v19-host-r2-native-inventory-20261008a/review.json'
HOST_REVIEW_SHA='09c2a3ed5b07feaa45931d851539fb2c64fc3f259ada372aff2a7d07bf90f80f'

def write_new(path,value):
    with path.open('x',encoding='ascii',newline='\n') as f:f.write(json.dumps(value,sort_keys=True,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);a=p.parse_args()
    b.require(re.fullmatch('build-attempt[1-9][0-9]*|build-final',a.directory),'Fixed private output name')
    out=HERE/a.directory;b.require(not out.exists(),'Never overwrite build output')
    raw=b.bounded(HOST_REVIEW,131072);b.require(b.sha(raw)==HOST_REVIEW_SHA,'Independent Host R2 report changed')
    before=b.sources();proof=HERE/(a.directory+'-before.json');write_new(proof,before)
    # A relative unquoted first token avoids CMD /c's absolute-path ambiguity.
    command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c','build.cmd',str(out)]
    timed_out=False
    with (HERE/(a.directory+'-driver.stdout')).open('xb') as stdout,(HERE/(a.directory+'-driver.stderr')).open('xb') as stderr:
        proc=subprocess.Popen(command,cwd=HERE,stdout=stdout,stderr=stderr)
        try:code=proc.wait(timeout=55)
        except subprocess.TimeoutExpired:
            timed_out=True
            with (HERE/(a.directory+'-timeout-cleanup.stdout')).open('xb') as cleanout,(HERE/(a.directory+'-timeout-cleanup.stderr')).open('xb') as cleanerr:
                subprocess.run(['taskkill.exe','/PID',str(proc.pid),'/T','/F'],stdout=cleanout,stderr=cleanerr,timeout=10,check=True)
            code=proc.wait(timeout=10)
    after=b.sources();write_new(HERE/(a.directory+'-source-check.json'),{'before':before,'after':after,'unchanged':b.exact(before,after)})
    record={'build_exit_code':code,'argv':command,'timed_out':timed_out,'all_spawned_sessions_collected':True,
            'output_directory_created':out.is_dir(),'sources_unchanged':b.exact(before,after),'source_count':len(before),
            'host_independent_review_sha256':HOST_REVIEW_SHA,'game_accessed':False,'bridge_start_called':False,'dll_loaded':False}
    if code==0 and not timed_out:
        b.require(out.is_dir(),'Compiler runner did not create its exact directory')
        unit=subprocess.run([sys.executable,'-B','-m','unittest','test_wire','-v'],cwd=HERE,capture_output=True,timeout=30)
        for name,data in (('wire.stdout',unit.stdout),('wire.stderr',unit.stderr)):
            b.require(len(data)<=65536,'Wire output budget')
            with (out/name).open('xb') as f:f.write(data)
        record['wire_exit_code']=unit.returncode
        if unit.returncode==0 and record['sources_unchanged']:
            manifest,sha=b.write_manifest(out);record.update(manifest_sha256=sha,dll_sha256=manifest['dll_sha256'],pe=manifest['pe'])
    write_new(HERE/(a.directory+'-validation.json'),record);print(json.dumps(record,sort_keys=True))
    return 0 if code==0 and record.get('wire_exit_code')==0 and record['sources_unchanged'] else 1

if __name__=='__main__':raise SystemExit(main())
