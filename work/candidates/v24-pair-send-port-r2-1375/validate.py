import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def desc(p):
 b=p.read_bytes();assert len(b)<=4*1024*1024;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def own():return {p.name:desc(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('source-index.json','review.json')}
def inputs():
 d=json.loads((HERE/'input-pins.json').read_bytes());assert all(desc(ROOT/k)==v for k,v in d.items());return d
def main():
 assert sys.flags.isolated==1 and len(sys.argv)==2 and sys.argv[1].replace('-','').isalnum()
 out=HERE/sys.argv[1];out.mkdir(exist_ok=False);before=own();pins=inputs()
 spec=importlib.util.spec_from_file_location('bounded_job',ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py')
 job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job);job.HERE=HERE;job.ROOT=ROOT
 build=job.run_build(out);after=own();after_pins=inputs()
 log=(out/'build/test.stdout').read_text() if (out/'build/test.stdout').exists() else ''
 passed=build['exit_code']==0 and 'transfer_groups=8 ' in log and before==after and pins==after_pins
 report=dict(passed=passed,build=build,sources_before=before,sources_after=after,inputs_before=pins,inputs_after=after_pins,
  test_stdout=log,game_accessed=False,native_game_called=False,DLL_built=False,production_ready=False)
 with (out/'validation.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
 print(json.dumps(dict(passed=passed,build=build)));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
