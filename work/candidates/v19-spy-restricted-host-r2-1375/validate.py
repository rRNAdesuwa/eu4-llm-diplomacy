"""Bounded isolated MSVC object/mock runner. All exact children are collected."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time
import prepare
import validate_capture
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def snapshot():
    paths={ROOT/n for n in json.loads(prepare.read(HERE/'input-pins.json'))}
    paths.update(HERE/n for n in json.loads(prepare.read(HERE/'source-index.json'))['sources'])
    paths.add(HERE/'source-index.json')
    return {p.relative_to(ROOT).as_posix():prepare.desc(p) for p in sorted(paths)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    out=a.output.resolve()
    if any(c in str(out) for c in '"%!^&|<>\r\n'):raise ValueError('Unsupported command metacharacter in output path')
    out.mkdir(exist_ok=False);before=snapshot();check=prepare.check();started=time.monotonic()
    # Fixed relative first token avoids cmd.exe's quoted absolute /c ambiguity.
    cmd=['cmd.exe','/d','/c','test_host.cmd',str(out/'build')]
    timed_out=False
    with (out/'driver.stdout').open('xb') as stdout,(out/'driver.stderr').open('xb') as stderr:
        proc=subprocess.Popen(cmd,cwd=HERE,stdout=stdout,stderr=stderr)
        try:code=proc.wait(timeout=55)
        except subprocess.TimeoutExpired:
            # Only this exact owned cmd tree (cl/link/mock) is stopped; never EU4.
            timed_out=True
            with (out/'timeout-cleanup.stdout').open('xb') as cleanout,(out/'timeout-cleanup.stderr').open('xb') as cleanerr:
                subprocess.run(['taskkill.exe','/PID',str(proc.pid),'/T','/F'],stdout=cleanout,stderr=cleanerr,timeout=10,check=True)
            code=proc.wait(timeout=10)
    after=snapshot();artifacts={}
    for path in sorted(out.rglob('*')):
        if path.is_file():artifacts[path.relative_to(out).as_posix()]=prepare.desc(path)
    output=prepare.read(out/'build/test.stdout',65536) if (out/'build/test.stdout').exists() else b''
    try:summary=json.loads(output)
    except (ValueError,UnicodeDecodeError):summary=None
    passed=not timed_out and code==0 and before==after and type(summary)is dict and type(summary.get('checks'))is int and summary['checks']>0 and type(summary.get('failures'))is int and summary['failures']==0 and summary.get('mock_only') is True and summary.get('game_access') is False
    capture=validate_capture.verify(out/'build/mock-events.jsonl') if passed else None
    record={'scope':'isolated_host_obj_and_mock_only','capture':capture,'check':check,'argv':cmd,'exit_code':code,'seconds':time.monotonic()-started,
      'before':before,'after':after,'inputs_unchanged':before==after,'artifacts':artifacts,'mock_result':summary,'passed':passed,
      'native_game_calls':False,'dll_built':False,'actual_process_access':False,'timed_out':timed_out,'all_shell_sessions_collected':True}
    with (out/'validation.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({'passed':passed,'inputs':len(before),'exit_code':code,'mock_result':summary,'validation':str(out/'validation.json')}))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
