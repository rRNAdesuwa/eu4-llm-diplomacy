"""Candidate source inventory; --check only reads files."""
import argparse
import hashlib
import json
from pathlib import Path
import reviewer

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCES=('reviewer.py','test_reviewer.py','README.md','input-pins.json','prepare.py','validate.py','test_shared_budget.py','lineage.json','repair.diff')

def render():
    pins=reviewer.verify_sources()
    sources={str((HERE/name).relative_to(ROOT)).replace('\\','/'):
             {'sha256':reviewer.sha(HERE/name),'bytes':(HERE/name).stat().st_size} for name in SOURCES}
    return dict(schema=1,purpose='spy5_manual_ui_batch_offline_review_candidate_r2',
                inputs=pins,sources=sources,actual_review_executed=False,production_ready=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    value=render();raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();path=HERE/'source-index.json'
    if a.check:
        if path.read_bytes()!=raw:raise ValueError('source index differs')
    else:
        with path.open('xb')as out:out.write(raw)
    print(json.dumps({'check':a.check,'sha256':hashlib.sha256(raw).hexdigest(),'inputs':len(value['inputs'])}))

if __name__=='__main__':main()
