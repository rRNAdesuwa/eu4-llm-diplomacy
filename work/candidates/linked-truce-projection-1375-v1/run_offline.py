"""Only new candidate offline tests; bounded collected child, no game/REA."""
import hashlib
import json
from pathlib import Path
import sys
import time
import types

HERE=Path(__file__).resolve().parent


def pin(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def main():
 out=HERE/'offline-r1';out.mkdir(exist_ok=False)
 source={n:pin(HERE/n) for n in ('linked_truce_projection.py','test_linked_truce_projection.py','README.md','source-manifest.json','build_manifest.py','run_offline.py')}
 (out/'claim.json').write_text(json.dumps(dict(source_pins=source,game_process_accesses=0)),encoding='utf-8')
 start=time.perf_counter()
 jobpath=HERE.parents[2]/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
 raw=jobpath.read_bytes()
 assert hashlib.sha256(raw).hexdigest()=='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
 helper=types.ModuleType('_linked_projection_offline_job');helper.__file__=str(jobpath)
 exec(compile(raw,str(jobpath),'exec'),helper.__dict__)
 job=helper.run_cli_tree([sys.executable,'-I','-B',str(HERE/'test_linked_truce_projection.py')],HERE.parents[2],
  out/'stdout.txt',out/'stderr.txt',timeout_seconds=30,memory_limit=768*1024*1024)
 code=job.get('exit_code')
 post={n:pin(HERE/n) for n in source}
 result=dict(exit_code=code,source_unchanged=post==source,source_pins=source,
  duration_seconds=round(time.perf_counter()-start,6),job=job,child_collected=job.get('direct_child_collected') is True,
  stdout=pin(out/'stdout.txt'),stderr=pin(out/'stderr.txt'),game_process_accesses=0,
  native_game_calls=0,old_test_suites_run=0,real_capture_run=False)
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result));return 0 if code==0 and post==source and job.get('error') is None and job.get('job_active_processes_final')==0 else 1


if __name__=='__main__':raise SystemExit(main())
