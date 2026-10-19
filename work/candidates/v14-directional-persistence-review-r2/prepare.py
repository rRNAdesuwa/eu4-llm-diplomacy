"""Validate isolated candidate pins; never prepare an actual persistence case."""
import argparse,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("directional_persistence_prepare",HERE/"matcher.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def main():
 parser=argparse.ArgumentParser(description=__doc__);g=parser.add_mutually_exclusive_group(required=True);g.add_argument("--check",action="store_true");g.add_argument("--template",type=Path);args=parser.parse_args()
 if args.template:m.write_new(args.template,m.case_template());return 0
 report=json.loads(m.bounded(HERE/"review.json"))
 for name,item in report["source_files"].items():
  raw=m.bounded(HERE/name);m.require(len(raw)==item["size_bytes"] and m.sha(raw)==item["sha256"],"Candidate source changed: "+name)
 for item in report["validation_history"]:m.require(m.sha(m.bounded(HERE/item["path"]))==item["sha256"],"Validation history changed")
 pins,_=m.dependencies();print(json.dumps(dict(status="passed",source_files=len(report["source_files"]),dependency_count=len(pins["files"]),actual_case_prepared=False,actual_case_reviewed=False,game_accessed=False)))
 return 0
if __name__=="__main__":raise SystemExit(main())
