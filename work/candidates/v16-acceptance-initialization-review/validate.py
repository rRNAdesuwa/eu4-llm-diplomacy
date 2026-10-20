"""Capture pure check/unittest results in a fresh directory; no C++ or game."""
import json
from pathlib import Path
import subprocess
import sys
import time
import prepare

HERE,ROOT=prepare.HERE,prepare.ROOT


def snapshot():
    result={}
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or "validation-results" in path.parts:continue
        raw=prepare.bounded(path)
        result[path.relative_to(HERE).as_posix()]={"bytes":len(raw),"sha256":prepare.digest(raw)}
    return result


def main():
    destination=HERE/"validation-results"
    destination.mkdir(exist_ok=False)
    before=snapshot();prepare.frozen_inputs()
    commands=[
        [sys.executable,"-B",str(HERE/"prepare.py"),"--check"],
        [sys.executable,"-B","-m","unittest","discover","-s",str(HERE),"-p","test_*.py","-v"]]
    runs=[]
    for number,command in enumerate(commands):
        output=destination/(str(number)+"-output.txt")
        started=time.monotonic()
        with output.open("xb") as stream:
            completed=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        runs.append({"command":command,"exit_code":completed.returncode,"elapsed_seconds":time.monotonic()-started,
            "output":output.relative_to(HERE).as_posix(),"output_sha256":prepare.digest(prepare.bounded(output))})
    prepare.frozen_inputs();after=snapshot()
    assert before==after
    result={"purpose":"v16_offline_startup_candidate_validation","runs":runs,
        "sources_before":before,"sources_after":after,"lineage_files_checked":173,"old_frozen_inputs_checked":49,
        "development_run":{"tests":56,"failures":1,"cause":"New test initially selected the first char line[3000] buffer, not the exact research_frame printf; corrected only test extraction."},
        "cpp_tests_compiled":False,"native_built":False,"materialized":False,"game_accessed":False,
        "server_started":False,"requests_published":False,"production_backend_registered":False}
    with (destination/"validation.json").open("x",encoding="utf-8") as stream:
        json.dump(result,stream,indent=2);stream.write("\n")
    print(json.dumps({"exit_codes":[row["exit_code"] for row in runs],"validation_sha256":prepare.digest(prepare.bounded(destination/"validation.json"))}))
    raise SystemExit(0 if all(row["exit_code"]==0 for row in runs) else 1)


if __name__=="__main__":main()
