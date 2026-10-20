"""CreateNew offline evidence. Executes only prepare --check and Python tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from candidate_guard import HERE, ROOT
from prepare import frozen_inputs, encoded


def sha(raw):return hashlib.sha256(raw).hexdigest()


def sources():
    result={}
    for path in HERE.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or any(p.startswith("validation-results") for p in path.parts):
            continue
        if path.suffix in (".py", ".h", ".cpp", ".asm", ".cmd", ".inc", ".json", ".md", ".diff", ".lua", ".txt", ".mod"):
            raw=path.read_bytes();result[path.relative_to(HERE).as_posix()]={"sha256":sha(raw),"bytes":len(raw)}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--create",action="store_true",required=True)
    parser.add_argument("--output-name",choices=("validation-results","validation-results-r2"),default="validation-results")
    args=parser.parse_args()
    frozen_before,_=frozen_inputs();before=sources()
    out=HERE/args.output_name;out.mkdir(exist_ok=False)
    commands=[("prepare-check",[sys.executable,"-B",str(HERE/"prepare.py"),"--check"]),
              ("python-tests",[sys.executable,"-B","-m","unittest","discover","-s",str(HERE),"-p","test_*.py","-v"])]
    runs=[]
    for name,argv in commands:
        result=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
        outputs={}
        for kind,raw in (("stdout",result.stdout),("stderr",result.stderr)):
            path=out/(name+"."+kind+".txt")
            with path.open("xb") as stream:stream.write(raw)
            outputs[kind]={"path":path.relative_to(HERE).as_posix(),"sha256":sha(raw),"bytes":len(raw)}
        runs.append({"name":name,"argv":argv,"exit_code":result.returncode,"outputs":outputs})
        if result.returncode:break
    frozen_after,_=frozen_inputs();after=sources()
    report={"schema_version":1,"purpose":"v15_unbuilt_candidate_offline_validation",
        "completed_at_utc":datetime.now(timezone.utc).isoformat(),"runs":runs,
        "candidate_inputs":before,"candidate_inputs_unchanged":before==after,
        "frozen_v14_inputs_unchanged":frozen_before==frozen_after,"frozen_input_count":49,
        "all_stages_exit_zero":len(runs)==2 and all(r["exit_code"]==0 for r in runs),
        "native_window_mock_source":"test_window.cpp","native_window_mock_compiled":False,
        "native_built":False,"materialized":False,"game_process_accessed":False,
        "server_started":False,"game_request_published":False,
        "native_host_independently_reviewed":False,"production_backend_registered":False}
    with (out/"validation.json").open("xb") as stream:stream.write(encoded(report))
    print(json.dumps({k:report[k] for k in ("all_stages_exit_zero","candidate_inputs_unchanged","frozen_v14_inputs_unchanged","native_built","materialized","game_process_accessed")}))
    return 0 if report["all_stages_exit_zero"] and before==after else 1


if __name__=="__main__":raise SystemExit(main())
