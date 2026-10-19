"""CreateNew or check the fixed offline candidate source index."""
import argparse
import hashlib
import json
from pathlib import Path
import reviewer
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCES=('reviewer.py','test_reviewer.py','README.md','prepare.py','validate.py','input-pins.json')
def render():
    inputs=reviewer.verify_sources()
    sources={str((HERE/name).relative_to(ROOT)).replace('\\','/'):
      dict(bytes=(HERE/name).stat().st_size,sha256=reviewer.sha(HERE/name))for name in SOURCES}
    return dict(schema=1,purpose='fixed_subject_curry_manual_ui_batch_candidate',inputs=inputs,sources=sources,
                actual_review_executed=False,production_ready=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    value=render();raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();out=HERE/'source-index.json'
    if a.check:
        if out.read_bytes()!=raw:raise ValueError('source index changed')
    else:
        with out.open('xb')as f:f.write(raw)
    print(json.dumps(dict(check=a.check,sha256=hashlib.sha256(raw).hexdigest(),inputs=len(value['inputs']))))
