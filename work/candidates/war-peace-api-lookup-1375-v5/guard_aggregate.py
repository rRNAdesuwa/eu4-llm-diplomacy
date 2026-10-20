"""First aggregate fixture only. Earlier two refusals are not rerun or relabeled."""
import hashlib,json,sys,tempfile,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v5-aggregate-delta-20261016-r1'
EXPECTED='ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def main():
 assert sys.argv[1:]==[]
 engine=(HERE/'query_engine.py').read_bytes();assert len(engine)==16583 and pin(engine)['sha256']==EXPECTED
 m=types.ModuleType('_v5_first_aggregate');m.__file__=str(HERE/'query_engine.py');exec(compile(engine,m.__file__,'exec'),m.__dict__)
 blob=b' '*(2*1024*1024);bp=pin(blob);index=b'{}'
 manifest=dict(schema='EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1',version='1.37.5',game_sha256=m.GAME_SHA256,
  scope='offline_selected_evidence_only',sources={f'work/reports/virtual/{i}.json':bp for i in range(17)},index=pin(index))
 raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode();journal=[];ids=[]
 with tempfile.TemporaryDirectory(prefix='owned-v5-aggregate-',dir=REPORT)as temp:
  root=Path(temp).resolve();assert root.is_relative_to(REPORT.resolve())
  for path in manifest['sources']:
   f=root/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'')
  def virtual(path):
   if path.name=='data-manifest.json':value=raw
   elif path.name=='index.json':value=index
   else:value=blob;ids.append(id(value))
   journal.append(dict(path=path.relative_to(root).as_posix(),synthetic_returned_or_charged_bytes=len(value),sha256=pin(value)['sha256'],OS_body_read=False));return value
  m._bounded_read=virtual
  try:m.SourceGraph(root,root,pin(raw)['sha256']).verify(parse=False)
  except m.LookupFailure as exc:assert str(exc)=='source_graph_limit_exceeded';reason=str(exc)
  else:raise AssertionError('aggregate unexpectedly accepted')
  assert len(ids)==16 and len(set(ids))==1 and sum(x['synthetic_returned_or_charged_bytes']for x in journal)>32*1024*1024
  assert root.is_relative_to(REPORT.resolve())
 synthetic=sum(x['synthetic_returned_or_charged_bytes']for x in journal);assert synthetic<40*1024*1024
 value=dict(schema='EU4-LOOKUP-V5-FIRST-AGGREGATE-FIXTURE/1',sealed=True,passed=True,first_aggregate_only=True,earlier_cases_or_old_suite_rerun=False,
  refusal=reason,input_manifest_raw_hex=raw.hex(),input_index_raw_hex=index.hex(),owned_repeated_buffer=bp,owned_buffer_objects=1,journal=journal,
  synthetic_returned_or_charged_bytes=synthetic,synthetic_limit=40*1024*1024,physical_explicit_read_bytes=len(engine),physical_OS_body_read_bytes=0,
  not_32MiB_OS_read_proof=True,owned_temporary_context_exited=True,prior_failed_batch_still_failed=True,clean_three_fixture_batch_passed=False,
  PE_Capstone_game_native_oldprogram_or_tests=0,independent_review_passed=False)
 print(json.dumps(value,sort_keys=True,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
