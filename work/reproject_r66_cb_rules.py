"""Correct R66 target-evaluation flags from retained native CB events."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from bridge.declarewar_peace_options import project_native_peace_options, validate_native_peace_options
from work.run_peace_consequence_queries import _read_slice_events, _output_paths, _write_json


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    source=args.source.resolve(strict=True)
    report=json.loads(source.read_text(encoding="utf-8"))
    assert report["status"]=="passed", "SOURCE_NATIVE_BATCH_NOT_PASSED"
    output,evidence=_output_paths(args.output)
    report.update(source_report=str(source),mode="offline_python_projection_correction",
                  correction="declared terms retain target-rule evaluation requirement",
                  live_query_replayed=False,query_call_count=0)
    for index,row in enumerate(report["cases"]):
        events=_read_slice_events(Path(row["native_slice"]["path"]))
        raw=next(e for e in events if e.get("event")=="native_declare_war_inspection"
                 and e.get("query_id")==row["native_event"]["query_id"])
        assert validate_native_peace_options(raw["native_peace_options"])
        public=json.loads(Path(row["public_path"]).read_text(encoding="utf-8"))
        public["peace_term_rules"]=project_native_peace_options(raw["native_peace_options"])
        path=evidence/f"case-{index+1:02d}-public.json"
        _write_json(path,public)
        row["source_public_path"]=row["public_path"]
        row["public_path"]=str(path)
        row["offline_reprojected"]=True
        row["checks"]["declared_terms_keep_target_evaluation"]=all(
            not public["peace_term_rules"][side]["records"]
            or public["peace_term_rules"][side]["target_evaluation_required"] is True
            for side in ("attacker_declared","defender_declared"))
    report["checks"]["all_corrected_public_projections_verified"]=all(
        all(row["checks"].values()) for row in report["cases"])
    report["status"]="passed" if all(report["checks"].values()) else "failed"
    _write_json(output,report)
    print(json.dumps({"status":report["status"],"cases":len(report["cases"]),"report":str(output)},ensure_ascii=False))
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
