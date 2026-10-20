"""Build the explicit fixed36 plan only; no process or publication."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PINS={
 'work/candidates/v17-batch-host-review-r3/batch.py':'75a1fdd1657862c1e019cc25e711a45a095909c18eeef1570d2c61db20a8b23e',
 'work/candidates/v17-batch-host-review-r3/review.json':'0096deea8f9eb8fbff7e5bc291aaaa0ea2f0b272ea7e834e976503568fd696fd',
 'work/review-results/v17-batch-host-r3-native-inventory-20261008a/review.json':'4cbcbe1e92c312bc0b860b70a251b4f8a5142bcc2d54255df191de45b30d8dbf',
 'work/candidates/v17-batch-action-matrix-1375/plan.json':'f63080fd20ee949dc44ec76b819deac7b00eae71ae05220cc268f3a715b23a6b',
 'work/candidates/v17-batch-action-matrix-1375/review.json':'1e5554ac4e4d52309f2fbd1b21ace8f486c370226a5557b355a8a754860815a4',
}


def verify():
 for name,digest in PINS.items():
  with (ROOT/name).open('rb') as src:raw=src.read(128*1024+1)
  assert len(raw)<=128*1024 and hashlib.sha256(raw).hexdigest()==digest,name


def main():
 verify()
 spec=importlib.util.spec_from_file_location('fixed_batch_plan',ROOT/'work/candidates/v17-batch-host-review-r3/batch.py')
 batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)
 matrix=json.loads((ROOT/'work/candidates/v17-batch-action-matrix-1375/plan.json').read_bytes())
 plan={'protocol':'EU4LAB/3','purpose':'restricted_pair_lab_1375_v17','pid':63500,
       'creation':'01dd56c21f9b7c9d','world_cookie':'0x23fc93a11e0','window_thread':21668,
       'first_sequence':2,'observation_mode':'initial_final','run_id':'63500-20261008-batch36-a',
       'rows':[{'action':row['action'],'target':row['target']} for row in matrix['rows']]}
 assert batch.validate_plan(plan)==plan
 verify()
 output=ROOT/'work/runtime/native1375-v17/batch-plan-63500-a.json'
 with output.open('x',encoding='utf-8',newline='\n') as dst:json.dump(plan,dst,indent=2);dst.write('\n')
 print(json.dumps({'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                   'rows':36,'first_sequence':2,'game_accessed':False,'publication_performed':False}))


if __name__=='__main__':main()
