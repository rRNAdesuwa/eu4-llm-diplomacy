"""File-only scoped bookkeeping correction; old frozen sources remain unchanged."""
import ast,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];IO=[]
MASTER=dict(bytes=19355,sha256='1c1b0acd82b7ad100c8e6085deb5e994b92defd8212bf61d2a3a5db2b6cdf27f')
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(p,q=None):
 p=p.resolve();assert p.is_relative_to(ROOT);s=p.stat();assert s.st_size<=4*1024*1024;r=p.read_bytes();a=p.stat();assert(len(r),s.st_size,s.st_mtime_ns)==(a.st_size,a.st_size,a.st_mtime_ns)
 if q:assert pin(r)==q
 IO.append(dict(path=p.relative_to(ROOT).as_posix(),**pin(r)));return r
def write(n,v,text=False):
 r=v.encode()if text else(json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
 if n=='fixture-bookkeeping-corrigendum.json' and (HERE/n).exists():assert read(HERE/n)==r;return pin(r)
 with(HERE/n).open('xb')as f:f.write(r)
 return pin(r)
master=json.loads(read(HERE/'source-manifest.json',MASTER));rel=HERE.relative_to(ROOT).as_posix()+'/'
failed_dir=ROOT/'work/reports/war-peace-api-lookup-v5-guard-fixtures-20261016-r1'
fr=read(failed_dir/'receipt.json',dict(bytes=23438,sha256='46fb580a17e4a62cb173f7cbd7135213b15e9ffe53a7e3f50044b5a55c43a58d'));failed=json.loads(fr)
assert failed['passed']is False and failed['combined_physical_explicit_bytes']==2973221 and len(failed['records'])==1
j=failed['records'][0]['job'];assert j['exit_code']==1 and j['job_active_processes_final']==0 and j['direct_child_collected']and j['error']is None
stdout=read(failed_dir/'00.stdout.json',failed['records'][0]['stdout']);stderr=read(failed_dir/'00.stderr.txt',failed['records'][0]['stderr']);assert stdout==b''and b'line 45'in stderr
fixture=read(HERE/'guard_fixtures.py',master['files'][rel+'guard_fixtures.py']).decode();assert fixture.splitlines()[44].strip().startswith('assert len(calls)==3')
assert fixture.index("reject(root,data,'manifest_sources',calls)")<fixture.index('assert calls==')<fixture.index("reject(root,data,'file_limit_exceeded',calls)")<fixture.index('assert len(calls)==3')
pins={p.relative_to(ROOT).as_posix():pin(r)for p,r in [(failed_dir/'receipt.json',fr),(failed_dir/'00.stdout.json',stdout),(failed_dir/'00.stderr.txt',stderr)]}
claim=read(failed_dir/'claim.json',failed['claim']);pins[(failed_dir/'claim.json').relative_to(ROOT).as_posix()]=pin(claim)
corr=write('fixture-bookkeeping-corrigendum.json',dict(sealed=True,root_explicitly_authorized_narrow_followup=True,old_batch_passed=False,old_batch_exit_code=1,
 old_receipt=pin(fr),old_stderr=pin(stderr),original_frozen_fixture=master['files'][rel+'guard_fixtures.py'],original_manifest=MASTER,
 scoped_witnesses=[dict(case='97-source count',claim='expected manifest_sources rejection and following exact one-read assertion reached before later failure',proof='Frozen source order plus actual traceback reachedline45',per_case_rawjournal_published=False,clean_batch_pass=False),
 dict(case='4MiB+1 fakefile',claim='reject() returned only after exact file_limit_exceeded check; later Windows relative-path bookkeeping assertion failed',proof='Frozen source/reject helper and real traceback atline45',per_case_rawjournal_published=False,clean_batch_pass=False)],
 cause='str(path.relative_to(root)) uses Windows backslashes; comparison with forwardslash badpath is false. No queryengine/index/data/wrapper change is required.',
 no_prior_case_reexecution=True,next_execution='First aggregate fixture only; two earlier cases are not rerun or presented as clean batchpass',
 old_failed_child_physical_charge_upper=5*1024*1024,old_controller_physical=2973221,cumulative_fixture_limit=16*1024*1024,
 root_acceptance_needed_for_scoped_witness=False,independent_review_still_required=True,whole_clean_three_fixture_receipt_available=False,PE_game_native=0))
oldseal=read(HERE/'seal_candidate.py',master['files'][rel+'seal_candidate.py']).decode('utf-8');new=oldseal
def replace(a,b):
 global new
 assert new.count(a)==1,a[:100];new=new.replace(a,b)
replace("assert len(sys.argv)==3;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2]);assert len(expected['sha256'])==64", "assert len(sys.argv)==5;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2]);delta_expected=dict(bytes=int(sys.argv[3]),sha256=sys.argv[4]);assert len(expected['sha256'])==len(delta_expected['sha256'])==64")
replace("cache={path:read(ROOT/path,q)for path,q in m['files'].items()}","cache={path:read(ROOT/path,q)for path,q in m['files'].items()}\n delta_raw=read(HERE/'fixture-delta-source-manifest.json',delta_expected);delta_manifest=json.loads(delta_raw)\n for path,q in delta_manifest['files'].items():cache[path]=read(ROOT/path,q)\n assert delta_manifest['prior_batch_still_failed']")
replace("for phase,label in [('fixtures','guard-fixtures'),('queries','first-queries')]", "for phase,label in [('aggregate','aggregate-delta'),('queries','first-queries')]")
replace("assert receipt['passed']and receipt['error']is None and receipt['source_manifest']==expected and receipt['first_only_no_retries']and receipt['all_jobs_and_direct_children_collected']", "assert receipt['passed']and receipt['error']is None and receipt['all_jobs_and_direct_children_collected']\n  if phase=='aggregate':assert receipt['delta_manifest']==delta_expected and receipt['no_cases97_or_largefile_repeated']and receipt['prior_batch_still_failed']and receipt['clean_three_fixture_batch_passed']is False\n  else:assert receipt['source_manifest']==expected and receipt['first_only_no_retries']")
replace("assert receipt['command_count']==(1 if phase=='fixtures'else 4)","assert len(receipt['records'])==(1 if phase=='aggregate'else 4)")
replace("assert receipt['combined_physical_explicit_bytes']<=receipt['physical_limit']", "assert (receipt['cumulative_fixture_physical_upper']<16*1024*1024)if phase=='aggregate'else(receipt['combined_physical_explicit_bytes']<=receipt['physical_limit'])")
replace("if phase=='fixtures':assert value['first_new_methods']==3 and value['passed']and value['synthetic_returned_or_charged_bytes']<40*1024*1024", "if phase=='aggregate':assert value['first_aggregate_only']and value['passed']and value['synthetic_returned_or_charged_bytes']<40*1024*1024 and value['prior_failed_batch_still_failed']and value['clean_three_fixture_batch_passed']is False")
replace("for path,q in m['files'].items():read(ROOT/path,q)","for path,q in (m['files']|delta_manifest['files']).items():read(ROOT/path,q)")
replace("read(HERE/'source-manifest.json',expected)\n upper", "read(HERE/'source-manifest.json',expected);read(HERE/'fixture-delta-source-manifest.json',delta_expected)\n upper")
replace("upper=build['build_stage_upper']+sum(x['bytes']for x in reads)+1024*1024", "prep_delta=read(HERE/'fixture-delta-preparation-receipt.json');prep_delta_value=json.loads(prep_delta)\n upper=build['build_stage_upper']+prep_delta_value['explicit_read_bytes']+sum(x['bytes']for x in reads)+1024*1024")
replace("new_guard_fixture_methods_first_only=3", "first_clean_aggregate_methods=1,prior_expected_rejection_witnesses_only=2,clean_three_fixture_batch_passed=False")
replace("receipts['fixtures']['combined_physical_explicit_bytes']", "receipts['aggregate']['cumulative_fixture_physical_upper']")
replace("receipts['fixtures']['synthetic_fixture_bytes_separate']", "receipts['aggregate']['synthetic_bytes_separate']")
replace("sourcepins=m['files']|", "sourcepins=m['files']|delta_manifest['files']|{rel+'fixture-delta-source-manifest.json':delta_expected,rel+'fixture-delta-preparation-receipt.json':pin(prep_delta)}|")
replace("first_guard_methods=3", "first_clean_aggregate_methods=1,prior_expected_rejection_witnesses_only=2,prior_fixture_batch_passed=False")
replace("'seal_candidate.py'", "'seal_candidate_r2.py'")if "'seal_candidate.py'"in new else None
assert new.count("'seal-claim.json'")==2;new=new.replace("'seal-claim.json'","'seal-r2-claim.json'")
replace("'seal-failure-r1.json'", "'seal-failure-r2.json'")if new.count("'seal-failure-r1.json'")==1 else None
# The old failure handler has two identical filename literals; both are identity-only in the new file.
new=new.replace("'seal-failure-r1.json'","'seal-failure-r2.json'")
new=new.replace("+prep_delta_value['explicit_read_bytes']+sum","+prep_delta_value['explicit_read_bytes']+524288+sum")
ast.parse(new);sealpin=write('seal_candidate_r2.py',new,text=True)
pins[rel+'fixture-bookkeeping-corrigendum.json']=corr
for name in ['guard_aggregate.py','run_fixture_delta.py','seal_candidate_r2.py','prepare_fixture_delta.py','prepare_fixture_delta_r2.py']:
 r=read(HERE/name);ast.parse(r);pins[rel+name]=pin(r)
for name in ['source-manifest.json','guard_fixtures.py','run_first.py','seal_candidate.py','build-receipt.json']:
 original=read(HERE/name);copy=read(HERE/'fixture-failure-preimage-r1'/name);assert original==copy
 pins[rel+'fixture-failure-preimage-r1/'+name]=pin(copy)
for name in ['source-manifest.json','query_engine.py']:
 r=read(HERE/name,MASTER if name=='source-manifest.json'else master['files'][rel+name]);pins[rel+name]=pin(r)
for n in ['prepare_fixture_delta.py','fixture-bookkeeping-corrigendum.json','failure.json']:
 r=read(HERE/'fixture-delta-preparation-failure-r1'/n);pins[rel+'fixture-delta-preparation-failure-r1/'+n]=pin(r)
dm=write('fixture-delta-source-manifest.json' ,dict(sealed=True,prior_batch_still_failed=True,original_canonical_manifest=MASTER,files=pins,first_aggregate_only=True,
 source_engine_index_data_wrapper_changed=False,prior_cases_rerun=False,clean_three_case_pass_claimed=False,independent_review_passed=False,fixture_cumulative_physical_limit=16*1024*1024,synthetic_limit=40*1024*1024))
receipt=write('fixture-delta-preparation-receipt.json',dict(sealed=True,passed=True,delta_manifest=dm,new_r2_sealer=sealpin,explicit_read_bytes=sum(x['bytes']for x in IO),reads=IO,
 original_source_manifest_unchanged=MASTER,source_only=True,aggregate_or_queries_run=0,old_failed_phase_repeated=False,independent_review_passed=False))
print(json.dumps(dict(passed=True,delta_manifest=dm,r2_sealer=sealpin,preparation_receipt=receipt,explicit_read_bytes=sum(x['bytes']for x in IO))))
