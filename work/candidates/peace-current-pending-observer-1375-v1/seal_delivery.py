"""Retain first offline deliverables, without running any CLI or tests again."""
from pathlib import Path
import hashlib
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def pin(path):
 b=path.read_bytes();assert len(b)<=4194304;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(name,value):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=True,indent=2);f.write('\n')
def main():
 raw=(HERE/'source-manifest.json').read_bytes();m=json.loads(raw)
 assert m['sealed'] is False and m['runtime_capture_authorized'] is False
 for name,expected in m['source_pins'].items():assert pin(ROOT/name)==expected
 with (HERE/'draft-source-manifest.json').open('xb') as f:f.write(raw)
 receipt=json.loads((HERE/'offline-r1/receipt.json').read_bytes())
 assert receipt['status']=='offline_passed' and len(receipt['operations'])==3
 for item in receipt['operations']:
  assert item['passed'] is True and item['job']['exit_code']==0 and item['job']['job_active_processes_final']==0 and item['job']['direct_child_collected'] is True
  for suffix in ('stdout','stderr'):assert pin(HERE/'offline-r1'/(item['operation']+'-'+suffix+'.txt'))==item[suffix]
 suite=json.loads((HERE/'offline-r1/new_fake_suite-stdout.txt').read_bytes())
 assert (suite['run'],suite['failures'],suite['errors'],suite['passed'])==(31,0,0,True)
 names=['peace_current_pending.py','test_peace_current_pending.py','README.md','build_manifest.py','run_offline.py',
  'draft-source-manifest.json','preparation.json','report.md','seal_delivery.py']
 names+=['offline-r1/'+n for n in ['claim.json','receipt.json']]
 for op in ('new_fake_suite','check','catalog'):names += ['offline-r1/'+op+s for s in ('-receipt.json','-stdout.txt','-stderr.txt')]
 pins={n:pin(HERE/n) for n in names}
 value=dict(schema='EU4-PEACE-PENDING-CANDIDATE-DELIVERY/1',sealed=True,stage='draft_source_offline_passed_waiting_non_author_source_review',
  files=pins,source_pins=m['source_pins'],canonical_source_manifest_pin_at_delivery=pin(HERE/'source-manifest.json'),
  canonical_note='Exact draft snapshot retained separately; future root metadata promotion must not overwrite this historical first-run receipt.',
  source_graph_sha256=m['source_graph_sha256'],tests_first_run=31,old_tests_run=0,
  file_commands_run_once=['check','catalog'],real_status_runs=0,PE_game_native_requests=0,
  new_reader_source_review='pending',production_review='pending',runtime_capture_authorized=False,
  native_ready=False,selected_effect_verified=False,all_shells_collected=True)
 save('delivery-manifest.json',value)
 print(json.dumps(dict(status='draft_delivery_pinned',delivery_manifest=pin(HERE/'delivery-manifest.json'),files=len(pins),source_pins=len(m['source_pins']),real_status_runs=0)))
if __name__=='__main__':main()
