"""Candidate file/pin check only; never builds or reads a process."""
import argparse, hashlib, json
from pathlib import Path
import trace as local_trace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(path):
    h=hashlib.sha256();n=0
    with path.open('rb') as f:
        while raw:=f.read(1024*1024):h.update(raw);n+=len(raw)
    return {'bytes':n,'sha256':h.hexdigest()}
def state():
    names=['trace.py','contract.json','contract_model.py','test_contract.py','README.md','prepare.py','validate.py',
      'report.json','discovery.json','explore.json','parser-linear.json']
    return {'candidate_files':{n:digest(HERE/n) for n in names},
      'input_files':{n:digest(ROOT/n) for n in local_trace.SOURCES},
      'exe':digest(ROOT.parent/'eu4.exe')}
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    now=state();assert now['exe']['sha256']==local_trace.SHA
    path=HERE/'source-index.json'
    if args.check:assert json.loads(local_trace.bounded(path))==now,'candidate/input mutation'
    else:
        with path.open('xb') as f:f.write((json.dumps(now,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({'pass':True,'check':args.check,'candidate_files':len(now['candidate_files']),'inputs':len(now['input_files'])+1}))
if __name__=='__main__':main()
