import importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 assert len(sys.argv)==2 and sys.argv[1].replace('-','').isalnum()
 prep=load('candidate_prepare',HERE/'prepare.py');before=prep.inputs();own=prep.current()
 assert own==json.loads((HERE/'source-index.json').read_bytes())
 out=HERE/sys.argv[1];out.mkdir(exist_ok=False)
 job=load('bounded_job',ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py');job.HERE=HERE;job.ROOT=ROOT
 build=job.run_build(out);stderr=(out/'build/test.stderr').read_text();passed=build['exit_code']==0 and 'Ran 20 tests' in stderr and '\nOK\n' in stderr
 assert prep.inputs()==before and prep.current()==own
 result=dict(passed=passed,build=build,inputs_before=before,inputs_after=prep.inputs(),sources_before=own,sources_after=prep.current(),test_output=stderr,
   new_decode_bytes=0,game_accessed=False,native_called=False,production_ready=False)
 with (out/'validation.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True)
 print(json.dumps(dict(passed=passed,build=build)));raise SystemExit(0 if passed else 1)
if __name__=='__main__':main()
