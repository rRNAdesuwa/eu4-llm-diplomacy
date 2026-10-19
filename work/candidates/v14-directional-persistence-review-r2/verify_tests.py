"""Run isolated synthetic tests and preserve every exit/output with CreateNew."""
import datetime,hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    paths=[p for p in HERE.iterdir() if p.is_file() and p.suffix in (".py",".json",".md")]
    before={p.name:digest(p) for p in paths}
    directory=HERE/"validation-results"/(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex)
    directory.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    command=[sys.executable,"-B",str(HERE/"test_matcher.py")]
    completed=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    with (directory/"output.txt").open("xb") as f:f.write(completed.stdout)
    after={p.name:digest(p) for p in paths}
    report=dict(schema_version=1,purpose="v14_directional_persistence_r2_synthetic_validation",command=command,exit_code=completed.returncode,
        sources_before=before,sources_after=after,sources_unchanged=before==after,stdout_sha256=digest(directory/"output.txt"),
        game_accessed=False,actual_case_prepared=False,actual_case_reviewed=False,native_built=False)
    with (directory/"validation.json").open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,sort_keys=True);f.write("\n")
    print(completed.stdout.decode(errors="replace"));print(directory/"validation.json")
    return completed.returncode if before==after else 3
if __name__=="__main__":raise SystemExit(main())
