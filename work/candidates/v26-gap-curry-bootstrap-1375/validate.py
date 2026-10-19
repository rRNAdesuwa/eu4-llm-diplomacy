import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def desc(p):
 h=hashlib.sha256();size=0
 with p.open('rb') as f:
  while b:=f.read(1024*1024):size+=len(b);h.update(b)
 return dict(bytes=size,sha256=h.hexdigest())
def load(name,p):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
 assert len(sys.argv)==2 and sys.argv[1].replace('-','').isalnum();out=HERE/sys.argv[1];out.mkdir(exist_ok=False)
 prep=load('candidate_prepare',HERE/'prepare.py');pins=prep.inputs();before=prep.current();assert before==json.loads((HERE/'source-index.json').read_bytes())
 for name in before:
  p=out/'source-preimages'/name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write((HERE/name).read_bytes())
 job=load('bounded_analysis_job',ROOT/'work/candidates/v21-core-pair-nosend-1375/validate.py');job.HERE=HERE;job.ROOT=ROOT
 build=job.run_build(out);after=prep.current();pin_after=prep.inputs()
 test=(out/'build/test.stdout').read_text() if (out/'build/test.stdout').exists() else ''
 dll=out/'build/eu4_pair_send_lab_1375_v26.dll'
 passed=build['exit_code']==0 and 'codec_groups=19 ' in test and dll.is_file() and before==after and pins==pin_after
 outputs={str(p.relative_to(out)).replace('\\','/'):desc(p) for p in out.rglob('*') if p.is_file()}
 result=dict(passed=passed,build=build,sources_before=before,sources_after=after,inputs_before=pins,inputs_after=pin_after,outputs=outputs,test_stdout=test,
  DLL_built=dll.is_file(),DLL_loaded=False,game_accessed=False,native_game_called=False,production_ready=False,all_shells_collected=True,remaining_sessions=[])
 with (out/'validation.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True)
 print(json.dumps(dict(passed=passed,build=build,DLL=desc(dll) if dll.is_file() else None)));raise SystemExit(0 if passed else 1)
if __name__=='__main__':main()
