"""One bounded offline source-bound client validation, then CREATE_NEW seals."""
import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
NAMES=['client.py','test_client.py','test_wire_fixture.cpp','build_test.cmd','validate.py','README.md']
def desc(p):
 assert 0<=p.stat().st_size<=4*1024*1024
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,d):
 with p.open('xb') as f:f.write((json.dumps(d,indent=2,sort_keys=True)+'\n').encode('ascii'))
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def own():return {n:desc(HERE/n) for n in NAMES}
def main():
 assert sys.flags.isolated and len(sys.argv)==2 and sys.argv[1].replace('-','').isalnum()
 out=HERE/sys.argv[1];out.mkdir(exist_ok=False)
 client=load('candidate_client',HERE/'client.py');manifest=client.manifest();graph=client.graph()
 pins={str(Path(k).relative_to(ROOT)).replace('\\','/'):dict(bytes=len(v),sha256=client.sha(v)) for k,v in graph.snapshot.items()}
 pins.update(manifest['source_pins'])
 for p in [client.LAUNCHER,client.LAUNCHER.parent/'inventory.json',client.BUILD/'build.json',client.BUILD/'pair_component.obj',
   ROOT/'work/review-results/v21-pair-r2-action-catalog-20261008a/job_helper.py']:
  pins[str(p.relative_to(ROOT)).replace('\\','/')]=desc(p)
 before=own();put(HERE/'source-index.json',before);put(HERE/'input-pins.json',pins)
 for n in NAMES:
  p=out/'source-preimages'/n;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write((HERE/n).read_bytes())
 job=load('bounded_client_job',ROOT/'work/review-results/v21-pair-r2-action-catalog-20261008a/job_helper.py');job.HERE=HERE;job.ROOT=ROOT
 build=job.run_build(out);after=own();pin_after={k:desc(ROOT/k) for k in pins}
 test=(out/'build/test.stderr').read_text() if (out/'build/test.stderr').exists() else ''
 passed=build['exit_code']==0 and 'Ran 19 tests' in test and test.rstrip().endswith('OK') and before==after and pins==pin_after
 outputs={str(p.relative_to(out)).replace('\\','/'):desc(p) for p in out.rglob('*') if p.is_file()}
 validation=dict(passed=passed,build=build,sources_before=before,sources_after=after,inputs_before=pins,inputs_after=pin_after,outputs=outputs,
  test_output=test,game_accessed=False,DLL_loaded=False,native_game_called=False,production_ready=False,all_shells_collected=True,remaining_sessions=[])
 put(out/'validation.json',validation)
 if passed:put(HERE/'review.json',dict(status='AUTHOR_OFFLINE_PASS',source_index=desc(HERE/'source-index.json'),input_pins=desc(HERE/'input-pins.json'),
  validation=desc(out/'validation.json'),client=desc(HERE/'client.py'),tests=19,independent_review=False,game_accessed=False,DLL_loaded=False,native_game_called=False,production_ready=False))
 print(json.dumps(dict(passed=passed,build=build,client=desc(HERE/'client.py'),review=desc(HERE/'review.json') if passed else None)));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
