import argparse,json,pathlib,hashlib
from trace import HERE,ROOT,read,desc,build,canonical
FILES=['explore.py','exploration-01.json','trace.py','contract.py','test_contract.py','README.md','prepare.py','report.json','validate.py','preimages/report-draft-01.json','preimages/report-draft-02.json','preimages/test-contract-first.py','preimages/validate-first.py','preimages/source-index-first.json','validation/check.stdout','validation/tests.stdout']
def index():return {p:desc(HERE/p) for p in FILES}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();assert a.check
 expected=json.loads(read(HERE/'source-index.json'));assert index()==expected
 report=build();report['limits'].pop('peak_commit',None);assert canonical(report)==read(HERE/'report.json')
 assert report['limits']['new_decode_bytes']==294
 print(json.dumps({'check':True,'files':len(expected),'families':5,'modes':10,'new_decode_bytes':294,'runtime_verified':False}))
if __name__=='__main__':main()
