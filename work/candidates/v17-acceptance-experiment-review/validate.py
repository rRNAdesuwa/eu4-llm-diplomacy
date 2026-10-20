"""Record bounded offline commands and immutable source hashes; no actual case."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def row(path):
    with path.open("rb") as stream:raw=stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError("Validation source/output bound")
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    pins=json.loads((HERE/"pins.json").read_bytes())["files"]
    names=list(pins)+[p.relative_to(ROOT).as_posix() for p in HERE.iterdir() if p.is_file() and p.suffix in (".py",".json",".md",".diff")]
    before={name:row(ROOT/name) for name in sorted(set(names))}
    out=HERE/"validation-results"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex)
    out.mkdir(parents=True,exist_ok=False);stages=[]
    commands=[[sys.executable,"-B",str(HERE/"prepare.py"),"--check"],
        [sys.executable,"-B","-m","unittest","discover","-s",str(HERE),"-p","test_*.py","-v"]]
    for index,command in enumerate(commands):
        stdout,stderr=out/f"{index}.stdout",out/f"{index}.stderr"
        with stdout.open("xb") as a,stderr.open("xb") as b:
            result=subprocess.run(command,cwd=ROOT,stdout=a,stderr=b,timeout=180,check=False)
        stages.append(dict(argv=command,exit_code=result.returncode,stdout=row(stdout),stderr=row(stderr)))
        if result.returncode:break
    after={name:row(ROOT/name) for name in before}
    result=dict(schema_version=1,purpose="v17_stopped_reviewer_offline_validation",stages=stages,
        source_sha256=before,inputs_unchanged=before==after,game_accessed=False,actual_case_read=False,
        native_built=False,request_published=False,production_backend_registered=False)
    with (out/"validation.json").open("x",encoding="utf-8",newline="\n") as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write("\n")
    print(json.dumps(dict(path=(out/"validation.json").relative_to(ROOT).as_posix(),**row(out/"validation.json"))))
    return 0 if len(stages)==2 and all(s["exit_code"]==0 for s in stages) and result["inputs_unchanged"] else 2

if __name__=="__main__":raise SystemExit(main())
