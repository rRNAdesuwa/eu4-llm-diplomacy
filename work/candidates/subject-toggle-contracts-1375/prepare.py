"""Candidate integrity only; streamed hashes and bounded JSON. No process access."""
import argparse,hashlib,json
from pathlib import Path
import trace as local_trace
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FILES=['trace.py','find_calls.py','call-candidates.json','contract.json','contract_model.py','test_contract.py','README.md','prepare.py','validate.py','report.json','input-pins.json']
def digest(p):
    h=hashlib.sha256();n=0
    with p.open('rb') as f:
        while raw:=f.read(1024*1024):h.update(raw);n+=len(raw)
    return {'bytes':n,'sha256':h.hexdigest()}
def state():
    return {'candidate_files':{n:digest(HERE/n) for n in FILES},
      'inputs':{n:digest(ROOT/n) for n in local_trace.SOURCES},'exe':digest(ROOT.parent/'eu4.exe')}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
    now=state();assert now['exe']['sha256']==local_trace.SHA
    expected=json.loads(local_trace.bounded(HERE/'input-pins.json'))
    assert expected==[local_trace.rec(n) for n in local_trace.SOURCES]
    p=HERE/'source-index.json'
    if a.check:assert json.loads(local_trace.bounded(p))==now,'candidate/input changed'
    else:
        with p.open('xb') as f:f.write((json.dumps(now,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({'pass':True,'check':a.check,'candidate_files':len(FILES),'inputs':len(now['inputs'])+1}))
if __name__=='__main__':main()
