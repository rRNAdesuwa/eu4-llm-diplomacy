"""New candidate actual file-only check/catalog in bounded owned jobs; no status."""
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=ROOT/'work/candidates/linked-truce-projection-1375-v1'
OUT=ROOT/'work/reports/linked-truce-projection-candidate-filecheck-20261015-r1'
JOB=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'


def pin(p):
 b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def main():
 OUT.mkdir(exist_ok=False)
 raw=JOB.read_bytes();assert hashlib.sha256(raw).hexdigest()=='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
 helper=types.ModuleType('_linked_filecheck_job');helper.__file__=str(JOB);exec(compile(raw,str(JOB),'exec'),helper.__dict__)
 selected={n:pin(CANDIDATE/n) for n in ('linked_truce_projection.py','test_linked_truce_projection.py','source-manifest.json','README.md','build_manifest.py','run_offline.py')}
 records=[]
 for operation in ('check','catalog'):
  stdout,stderr=OUT/(operation+'.stdout.json'),OUT/(operation+'.stderr.txt')
  job=helper.run_cli_tree([sys.executable,'-I','-B',str(CANDIDATE/'linked_truce_projection.py'),operation],ROOT,
   stdout,stderr,timeout_seconds=30,memory_limit=768*1024*1024)
  result=json.loads(stdout.read_bytes())
  okay=job.get('error') is None and job.get('exit_code')==0 and job.get('job_active_processes_final')==0 and result['status']=='files_verified'
  records.append(dict(operation=operation,passed=okay,job=job,stdout=pin(stdout),stderr=pin(stderr),
   status=result['status'],profile_count=len(result.get('profiles',[])),native_game_calls=result['native_game_calls']))
 final={n:pin(CANDIDATE/n) for n in selected}
 receipt=dict(schema='EU4-LINKED-CANDIDATE-FILECHECK/1',passed=all(x['passed'] for x in records) and selected==final,
  source_unchanged=selected==final,candidate_pins=selected,records=records,producer=pin(Path(__file__)),
  game_process_accesses=0,actual_status_capture_run=False,Frida_operations=0,native_game_calls=0,old_tests_run=0)
 with (OUT/'receipt.json').open('x',encoding='utf-8') as f:f.write(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(dict(passed=receipt['passed'],receipt=pin(OUT/'receipt.json'),records=records)));return 0 if receipt['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
