"""Pin plan inputs and outputs only; no materialization or actual case."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES=[
 'work/AGENTS.md','work/discover_diplomacy.py','work/map_diplomacy_fields.py',
 'work/candidates/spy-action-contracts-1375/report.json',
 'work/candidates/spy-action-contracts-1375/review.json',
 'work/candidates/spy-four-normal-callers-contract-1375/report.json',
 'work/candidates/spy-four-normal-callers-contract-1375/review.json',
 'work/review-results/spy-four-normal-callers-action-catalog-20261008a/review.json',
 'work/candidates/subject-toggle-contracts-1375/report.json',
 'work/reports/native-peace-gui-send-1375.json','work/reports/preview-string-and-transport-1375.json',
 'work/reports/native-preview-1375.json','docs/native-command-1375.md',
 'work/native/v17/pair-engine-1375.cpp','work/native/v17/pair-engine-1375.h',
 'work/candidates/v17-batch-summary-review-r6/pair_contract.py',
 'work/candidates/v17-batch-summary-review-r6/native_stream.py',
 'work/candidates/v18-spy-no-send-core-1375/spy_core.cpp',
 'work/candidates/v18-spy-no-send-core-1375/spy_core.h',
 'work/candidates/v18-spy-no-send-core-1375/contract.json',
 'work/candidates/v18-spy-no-send-core-1375/review.json',
 'work/review-results/v18-spy-core-action-catalog-20261008a/review.json',
 'work/candidates/v18-spy-restricted-host-1375/host.cpp',
 'work/candidates/v18-spy-restricted-host-1375/host.h',
 'work/candidates/v18-spy-restricted-host-1375/contract.json',
 'work/candidates/v18-spy-restricted-host-1375/review.json',
 'work/review-results/v18-spy-host-action-catalog-20261008a/review.json',
 'work/candidates/v18-spy-bootstrap-lab-1375/review.json',
 'work/candidates/v18-spy-bootstrap-lab-1375/build-final/build.json',
 'work/candidates/v18-spy-bootstrap-capture-r2-1375/review.json',
 'work/candidates/v18-spy-client-capture-r2-1375/review.json',
 'work/review-results/v18-spy-bootstrap-capture-r2-action-catalog-20261008a/review.json',
 'work/review-results/v18-spy-client-capture-r2-action-catalog-20261008a/review.json',
]
LOCAL=['README.md','contract.json','model.py','test_model.py','report.json','evidence.py','prepare.py','validate.py']
LOCAL += ['explore.py','explore2.py','explore3.py','explore4.py']+[f'exploration-{i:02}.json' for i in range(1,5)]
def bounded(p):
    with p.open('rb') as f:b=f.read(8*1024*1024+1)
    assert len(b)<=8*1024*1024;return b
def rec(p):
    b=bounded(p);return dict(path=p.relative_to(ROOT).as_posix(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def enc(x):return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode()
def create_or_check(p,raw,check):
    if check:assert bounded(p)==raw,str(p)+' differs'
    else:
        with p.open('xb') as f:f.write(raw)
def main(check):
    assert all('bridge/diplomacy_api.py' not in n for n in SOURCES)
    inputs=[rec(ROOT/n) for n in SOURCES]
    create_or_check(HERE/'source-pins.json',enc(inputs),check)
    report=json.loads(bounded(HERE/'report.json'))
    assert report['resource']['new_decoded_bytes']==2718
    rows=[rec(HERE/n) for n in LOCAL]+[rec(HERE/'source-pins.json')]
    value=dict(schema=1,purpose='v19_spy_send_plan_only',inputs=inputs,outputs=rows,
      game_access=False,native_implementation=False,compiled=False,runtime_verified=False,production_ready=False)
    create_or_check(HERE/'candidate-index.json',enc(value),check)
    print(json.dumps(dict(passed=True,check=check,inputs=len(inputs),outputs=len(rows),
                         index_sha256=hashlib.sha256(enc(value)).hexdigest())))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();main(a.check)
