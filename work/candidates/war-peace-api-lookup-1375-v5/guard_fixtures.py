"""Three NEW offline v5 guard fixtures. Never calls CLI/main or game/native."""
import hashlib,json,sys,tempfile,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v5-guard-fixtures-20261016-r1'
ENGINE_SHA='ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'
LIMIT=16*1024*1024;SYNTHETIC=40*1024*1024
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def raw_json(o):return json.dumps(o,sort_keys=True,separators=(',',':')).encode()
def main():
 assert sys.argv[1:]==[]
 engine=(HERE/'query_engine.py').read_bytes();assert len(engine)==16583 and pin(engine)['sha256']==ENGINE_SHA
 mod=types.ModuleType('_v5_new_guard_fixtures');mod.__file__=str(HERE/'query_engine.py');exec(compile(engine,mod.__file__,'exec'),mod.__dict__)
 original=mod._bounded_read;records=[];physical=len(engine);synthetic=0
 def manifest(sources,index=b'{}'):
  return dict(schema='EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1',version='1.37.5',game_sha256=mod.GAME_SHA256,
   scope='offline_selected_evidence_only',sources=sources,index=pin(index))
 def reject(root,raw,expected,counter):
  try:mod.SourceGraph(root,root,pin(raw)['sha256']).verify(parse=False)
  except mod.LookupFailure as e:assert str(e)==expected;return
  raise AssertionError('Fixture unexpectedly accepted')
 with tempfile.TemporaryDirectory(prefix='owned-v5-guard-',dir=REPORT)as temp:
  root=Path(temp).resolve();assert root.is_relative_to(REPORT.resolve())
  empty=pin(b'{}');calls=[]
  data=raw_json(manifest({f'work/reports/owned/{i}.json':empty for i in range(97)}))
  (root/'data-manifest.json').write_bytes(data)
  def counted(path):
   nonlocal physical
   v=original(path);physical+=len(v);calls.append(dict(path=str(path.relative_to(root)),bytes=len(v)));return v
  mod._bounded_read=counted;reject(root,data,'manifest_sources',calls)
  assert calls==[dict(path='data-manifest.json',bytes=len(data))]
  records.append(dict(id='97_sources_before_index_or_body',passed=True,refusal='manifest_sources',physical_reads=calls,index_and_body_reads=0))
  # Genuine bounded file read sees4MiB+1. The oversized fake evidence is owned and removed by the verified temporary context.
  calls=[];badpath='work/reports/owned/too_large.json';full=root/badpath;full.parent.mkdir(parents=True)
  oversized=b' '*((4*1024*1024)+1);full.write_bytes(oversized);del oversized
  index=b'{}';(root/'index.json').write_bytes(index);data=raw_json(manifest({badpath:dict(bytes=4*1024*1024+1,sha256='0'*64)},index));(root/'data-manifest.json').write_bytes(data)
  def bounded_counted(path):
   nonlocal physical
   try:v=original(path)
   except mod.LookupFailure:
    # _bounded_read's fixed read(MAX_FILE+1) and file-limit rejection proves the returned length exceeded4MiB.
    physical+=mod.MAX_FILE+1;calls.append(dict(path=str(path.relative_to(root)),requested_max=mod.MAX_FILE+1,charged_returned_on_limit=mod.MAX_FILE+1,refused=True));raise
   physical+=len(v);calls.append(dict(path=str(path.relative_to(root)),bytes=len(v)));return v
  mod._bounded_read=bounded_counted;reject(root,data,'file_limit_exceeded',calls)
  assert len(calls)==3 and calls[-1]['path']==badpath and calls[-1]['charged_returned_on_limit']==4194305
  records.append(dict(id='single_owned_fake_file_4MiBplus1',passed=True,refusal='file_limit_exceeded',physical_reads=calls,body_requested_max=4194305))
  # Aggregate uses virtual file reads of one reused2MiB owned byte object. No physical34MiB body read is claimed.
  blob=b' '* (2*1024*1024);bp=pin(blob);sources={f'work/reports/virtual/{i}.json':bp for i in range(17)}
  for name in sources:
   f=root/name;f.parent.mkdir(exist_ok=True,parents=True);f.write_bytes(b'')
  data=raw_json(manifest(sources,index));(root/'data-manifest.json').write_bytes(data);calls=[];body_ids=[]
  def virtual(path):
   nonlocal synthetic
   if path.name=='data-manifest.json':v=data
   elif path.name=='index.json':v=index
   else:v=blob;body_ids.append(id(v))
   synthetic+=len(v);calls.append(dict(path=str(path.relative_to(root)),synthetic_returned_bytes=len(v),OS_body_read=False));return v
  mod._bounded_read=virtual;reject(root,data,'source_graph_limit_exceeded',calls)
  assert len(body_ids)==16 and len(set(body_ids))==1 and sum(x['synthetic_returned_bytes']for x in calls)>32*1024*1024
  assert synthetic<SYNTHETIC and physical<LIMIT
  records.append(dict(id='aggregate_virtual_32MiB_still_refused',passed=True,refusal='source_graph_limit_exceeded',virtual_reads=calls,
   one_reused_owned_buffer_bytes=len(blob),body_buffer_objects=1,physical_body_bytes=0,synthetic_returned_or_charged_bytes=sum(x['synthetic_returned_bytes']for x in calls),not_OS_32MiB_read_proof=True))
  mod._bounded_read=original
  assert root.is_relative_to(REPORT.resolve())
 value=dict(schema='EU4-LOOKUP-V5-NEW-GUARD-FIXTURES/1',sealed=True,passed=True,first_new_methods=3,records=records,
  physical_explicit_read_bytes=physical,physical_limit=LIMIT,synthetic_returned_or_charged_bytes=synthetic,synthetic_limit=SYNTHETIC,
  temporary_fixture_path_verified_inside_report_before_cleanup=True,owned_fixture_context_exited=True,
  old_suites_or_old_CLI_or_main_calls=0,PE_Capstone_game_native_requests=0,native_ready=False,independent_review_passed=False)
 print(json.dumps(value,sort_keys=True,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
