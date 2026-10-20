"""Check the isolated reviewer candidate, or CreateNew an unfinalized template only."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("directional_experiment_prepare",HERE/"reviewer.py")
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
def main():
    parser=argparse.ArgumentParser(description=__doc__);g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--check",action="store_true");g.add_argument("--template",type=Path)
    args=parser.parse_args()
    if args.template:r.write_new(args.template,r.template());return 0
    report=json.loads(r.bounded(HERE/"review.json",256*1024))
    for name,item in report["source_files"].items():
        raw=r.bounded(HERE/name);r.require(len(raw)==item["size_bytes"] and r.sha(raw)==item["sha256"],"Candidate source changed: "+name)
    for item in report["validation_history"]:
        raw=r.bounded(HERE/item["path"]);r.require(r.sha(raw)==item["sha256"],"Validation history changed")
    r.dependencies()
    contract=json.loads(r.bounded(HERE/"native-contract.json"))
    manifest_raw=r.bounded(r.ROOT/"work/runtime/native1375-v14/build.json")
    r.require(r.sha(manifest_raw)==contract["manifest_sha256"],"Frozen native manifest changed")
    manifest=json.loads(manifest_raw)
    for name,item in contract["sources"].items():
        raw=r.bounded(r.relative(r.ROOT,name))
        r.require(len(raw)==item["size_bytes"] and r.sha(raw)==item["sha256"]
                  and manifest["source_sha256"][name].lower()==item["sha256"],"Frozen native source contract differs")
    for anchor in contract["anchors"]:
        r.require(anchor["file"] in contract["sources"] and type(anchor["line"]) is int,"Unbound native source anchor")
        lines=r.bounded(r.relative(r.ROOT,anchor["file"])).decode().splitlines()
        r.require(1<=anchor["line"]<=len(lines) and lines[anchor["line"]-1]==anchor["text"],"Native source line changed")
    print(json.dumps({"status":"passed","source_files":len(report["source_files"]),"dependencies":len(json.loads((HERE/"pins.json").read_bytes())["files"]),"game_accessed":False,"actual_case_reviewed":False}))
    return 0
if __name__=="__main__":raise SystemExit(main())
