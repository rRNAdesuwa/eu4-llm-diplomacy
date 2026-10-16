"""File-only additive accounting correction; preserves first inventory/source."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
O='work/reports/runtime-entry-manifest-order-review-20261016-r1/'
B='work/reports/runtime-manifest-order-intake-20261016-r1/'
IO=[];data={}
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path,q=None):
 assert path.startswith((O,B))or path=='work/review_runtime_manifest_order_20261016.py'
 p=ROOT/path;s=p.stat();assert s.st_size<=4*1024*1024;r=p.read_bytes();a=p.stat();assert len(r)==s.st_size==a.st_size and s.st_mtime_ns==a.st_mtime_ns
 if q:assert pin(r)==q
 IO.append(dict(path=path,**pin(r)));return r
def write(name,v):
 r=(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
 with(ROOT/O/name).open('xb')as f:f.write(r)
 return pin(r)
m=json.loads(read(O+'manifest.json',dict(bytes=4240,sha256='fb3c36df1ea20cd6ac992ad755504653cd278d2d9332e68fab8a5267389de016')))
for path,q in m['source_pins'].items():data[path]=read(path,q)
first=json.loads(data[O+'findings.json']);check=json.loads(read(O+'verification.json'))
assert check['passed']and check['pins']==20
names=['03__integration_task_observer.py','05__linked_truce_projection.py','07__direct_truce_cache.py','11__support_heir_current_observer.py','13__peace_current_pending.py']
sizes={n:len(data[B+n])for n in names}
# Exact file-buffer reads in the three source-inspection shell snippets retained in this task.
q1=4201+3606+sum(sizes.values())
q2=6*sum(sizes.values())
counts={n:sum(isinstance(x,ast.Assign)for x in ast.parse(data[B+n]).body)for n in names}
q3=sum((counts[n]+5)*sizes[n]for n in names)+16856+sum(len(data[B+n])for n in ['02__eu4_observer_manifest_1375.json','04__source-manifest.json','06__source-manifest.json','08__source-manifest.json','10__data-manifest.json','12__source-manifest.json','14__source-manifest.json'])
known_manual=q1+q2+q3+4793
assert known_manual<4*1024*1024
corr=dict(sealed=True,scope='additive resource precision only; entry facts and original sealed source unchanged',
 subject_first_findings=pin(data[O+'findings.json']),subject_first_manifest=pin((ROOT/O/'manifest.json').read_bytes()),
 reason='First inventory manual1MiB allowance did not cover repeated read_text calls while extracting each assignment/function. Known shell-source buffer reads are now reconstructed explicitly; no old operation repeated.',
 source_query_buffer_reads=dict(query1=q1,query2=q2,query3=q3,index_getcontent=4793,total=known_manual,top_level_assignment_counts=counts),
 replacement_manual_prior_allowance=4*1024*1024,remaining_allowance_covers_metadata_and_small_reads=True,
 original_1MiB_allowance_superseded_not_added_twice=True,no_OS_IO_claim=True,no_author_tool_or_runtime_execution=True)
corpin=write('resource-corrigendum.json',corr)
final=first.copy();final['resources']=dict(first['resources']);final['resources']['manual_prior_inspection_allowance']=4*1024*1024
final['resources']['known_manual_query_read_bytes']=known_manual
final['resources']['complete_stage_upper']=first['resources']['explicit_owned_file_reads']+4*1024*1024+first['resources']['sealing_check_reserve']
assert final['resources']['complete_stage_upper']<8*1024*1024
final['resource_corrigendum']=corpin;final['supersedes_resource_estimate_only_of_first_findings']=pin(data[O+'findings.json'])
fp=write('final-findings.json',final)
self_raw=Path(__file__).read_bytes();assert len(self_raw)<=4*1024*1024
mp=write('final-manifest.json',dict(sealed=True,passed=True,source_pins=m['source_pins']|{O+'manifest.json':pin((ROOT/O/'manifest.json').read_bytes()),O+'verification.json':pin((ROOT/O/'verification.json').read_bytes()),O+'resource-corrigendum.json':corpin,O+'final-findings.json':fp,'work/finalize_runtime_manifest_order_20261016.py':pin(self_raw)},
 final_findings=fp,scope='owned entry guard-order inventory only',actual_authorized=False))
# Exact new final file pins; old twenty pins were checked above, no entry functions executed.
vr=write('final-verification.json',dict(sealed=True,passed=True,original_twenty_pins_replayed=True,final_manifest=mp,final_findings=fp,resource_corrigendum=corpin,
 finalizer_explicit_read_bytes=sum(x['bytes']for x in IO),manual_query_bytes_reconstructed=known_manual,within_complete_stage_upper=final['resources']['complete_stage_upper'],
 original_entry_manifest_opened=0,author_program_tests_PE_engine_runtime_operations=0,all_shells_collected=True))
print(json.dumps(dict(passed=True,findings=fp,manifest=mp,corrigendum=corpin,verification=vr,complete_stage_upper=final['resources']['complete_stage_upper'],known_manual_reads=known_manual)))
