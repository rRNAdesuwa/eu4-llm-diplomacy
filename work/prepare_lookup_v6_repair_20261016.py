"""One root-approved builder-check repair. Original build source/failure stay exact."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'work/candidates/war-peace-api-lookup-1375-v6'
J=[]
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(n):
 p=ROOT/n;assert p.stat().st_size<=4*1024**2
 b=p.read_bytes();J.append(dict(path=n,**pin(b)));return b
def write(n,x):
 b=(json.dumps(x,ensure_ascii=True,indent=2,sort_keys=True)+'\n').encode()
 with(OUT/n).open('xb')as f:f.write(b)
 return pin(b)
oldname='work/build_lookup_v6_20261016.py';old=read(oldname)
failure=read('work/candidates/war-peace-api-lookup-1375-v6/build-failure.json')
claim=read('work/candidates/war-peace-api-lookup-1375-v6/build-claim.json')
grant=read('work/reports/war-peace-api-lookup-v6-root-authorization-20261016-r2/authorization.json')
receipt=read('work/reports/war-peace-api-lookup-v6-root-authorization-20261016-r2/receipt.json')
assert pin(grant)==dict(bytes=6779,sha256='6ff710b74288f303a01df3049aab67901d49f7f1f2fbcfe0a0423251ce237de5')
assert pin(failure)==dict(bytes=27390,sha256='4aa14556a85a1663dbfa0748de6b836aac2995f22c5d485a9245cbf59bf499e6')
assert pin(claim)==dict(bytes=244,sha256='6cec078b3225d5f2d705b30a66e6ec4a208a49d7b9f20227af22cb730a84260e')
f=json.loads(failure);assert f['completed_bytes']==3015196 and f['no_queries_run_by_builder']
charged=sum(e['bytes']for e in J)
forecast=3015196+charged+8*1024**2+2*1024**2+16*1024**2
assert forecast<32*1024**2
ap=write('repair-authorization.json',dict(schema='EU4-LOOKUP-V6-ROOT-BUILDER-REPAIR/1',root_supplement_received=True,
 root_supplement='Allow one builder-only R2 narrow repair and new continuation claim. Preserve original failed source/claim/read journal; old58 fields cannot be added. Align core5false plus existing authority false with the original engine schema. This supplement is static source repair only; do not execute any already successful or attempted query (currently0). Failure+repair+build+seal stay within original32MiB, first4batch remains separate64MiB. Original6779B6ff710 grant unchanged; freeze full failurepins/ASTdelta/cumulative bill. No engine logic/olddata/oldtest/fixture/native/game changes.',
 original_authorization=pin(grant),original_claim=pin(claim),original_failure=pin(failure),original_builder=pin(old),no_query_has_run=True,engine_or_old_row_changes_authorized=False,
 failed_stage_completed_bytes=3015196,repair_explicit_read_bytes=charged,future_builder_conditional_allowance=8*1024**2,manual_allowance=2*1024**2,retained_seal_allowance=16*1024**2,conditional_total_upper=forecast,limit=32*1024**2))
s=old.decode('utf-8')
s=s.replace('P={};C={};READS=[]',f'P={{}};C={{}};READS=[]\nFAILED_STAGE_BYTES=3015196;REPAIR_STAGE_BYTES={charged}')
a="need(sys.argv[1:]==[],'fixed build only');OUT.mkdir(exist_ok=False)"
b="need(sys.argv[1:]==[],'fixed build only');need(OUT.is_dir() and {p.name for p in OUT.iterdir()}=={'build-claim.json','build-failure.json','repair-authorization.json','repair-record.json'},'exact prefreeze failed state only')"
assert s.count(a)==1;s=s.replace(a,b)
a="save('build-claim.json',dict(schema='EU4-LOOKUP-V6-BUILD-CLAIM/1',authorization=P[GRANT+'authorization.json'],single_build=True,no_query_run_yet=True,no_retry=True))"
b="""repairraw=read((OUT/'repair-record.json').relative_to(ROOT).as_posix());repair=json.loads(repairraw)
 need(repair['original_builder_pin']==dict(bytes=__OLDBYTES__,sha256='__OLDSHA__') and repair['failed_stage_completed_bytes']==FAILED_STAGE_BYTES and repair['repair_explicit_read_bytes']==REPAIR_STAGE_BYTES,'fixed root-approved repair accounting')
 for n,q in repair['preserved_inputs'].items():admit(n,q)
 repairname=(OUT/'repair-record.json').relative_to(ROOT).as_posix();P[repairname]=pin(repairraw);C[repairname]=repairraw
 admit((OUT/'repair-authorization.json').relative_to(ROOT).as_posix(),repair['repair_authorization_pin'])
 need(obj((OUT/'build-claim.json').relative_to(ROOT).as_posix())['authorization']==P[GRANT+'authorization.json'],'original claim preserved')
 save('build-continuation-claim.json',dict(schema='EU4-LOOKUP-V6-BUILD-CONTINUATION/1',root_supplement=repair['repair_authorization_pin'],preserved_first_failure=repair['preserved_inputs'],source_only=True,queries_attempted_before=0,original_claim_unchanged=True))""".replace('__OLDBYTES__',str(len(old))).replace('__OLDSHA__',pin(old)['sha256'])
assert s.count(a)==1;s=s.replace(a,b)
a="need(all(row[k]is False for k in FLAGS),'falseauthority')"
b="need(all(row[k]is False for k in FLAGS[:5]) and all(row[k]is False for k in FLAGS if k in row),'core5false and present optionalauthority false; do not modify legacy rows')"
assert s.count(a)==1;s=s.replace(a,b)
s=s.replace('sum(x[\'bytes\']for x in READS)+size+MANUAL+SEAL_RESERVE','sum(x[\'bytes\']for x in READS)+size+FAILED_STAGE_BYTES+REPAIR_STAGE_BYTES+MANUAL+SEAL_RESERVE')
s=s.replace('completed+MANUAL+SEAL_RESERVE','completed+FAILED_STAGE_BYTES+REPAIR_STAGE_BYTES+MANUAL+SEAL_RESERVE')
s=s.replace('sum(x[\'bytes\']for x in READS)+MANUAL+SEAL_RESERVE','sum(x[\'bytes\']for x in READS)+FAILED_STAGE_BYTES+REPAIR_STAGE_BYTES+MANUAL+SEAL_RESERVE')
s=s.replace("'README.md','build-claim.json']", "'README.md','build-claim.json','build-continuation-claim.json']")
s=s.replace('explicit_completed_read_bytes=sum(x[\'bytes\']for x in READS),manual_allowance=MANUAL,',"explicit_completed_read_bytes=sum(x['bytes']for x in READS),failed_stage_completed_bytes=FAILED_STAGE_BYTES,repair_stage_completed_bytes=REPAIR_STAGE_BYTES,build_attempts=2,prefreeze_failures=1,manual_allowance=MANUAL,")
s=s.replace("with(OUT/'build-failure.json').open('x',encoding='utf-8')", "with(OUT/'build-repair-failure.json').open('x',encoding='utf-8')")
ast.parse(s)
oldt=ast.parse(old.decode());newt=ast.parse(s)
unchanged=[]
for n in oldt.body:
 if isinstance(n,ast.FunctionDef) and n.name not in ('main','read'):
  nn=next(x for x in newt.body if isinstance(x,ast.FunctionDef)and x.name==n.name)
  assert ast.dump(n,include_attributes=False)==ast.dump(nn,include_attributes=False);unchanged.append(n.name)
for key in ('RUNNER','SEALER'):
 def val(t):return next(n.value.value for n in t.body if isinstance(n,ast.Assign)and any(isinstance(a,ast.Name)and a.id==key for a in n.targets))
 # RUNNER is a literal followed by replace(); compare full assignment AST.
 aa=next(n for n in oldt.body if isinstance(n,ast.Assign)and any(isinstance(a,ast.Name)and a.id==key for a in n.targets));bb=next(n for n in newt.body if isinstance(n,ast.Assign)and any(isinstance(a,ast.Name)and a.id==key for a in n.targets))
 assert ast.dump(aa,include_attributes=False)==ast.dump(bb,include_attributes=False)
newname='work/build_lookup_v6_r2_20261016.py'
with(ROOT/newname).open('x',encoding='utf-8',newline='\n')as h:h.write(s)
preserved={e['path']:{k:e[k]for k in('bytes','sha256')}for e in J}
write('repair-record.json',dict(schema='EU4-LOOKUP-V6-BUILDER-REPAIR-RECORD/1',sealed=True,root_supplement_received=True,original_builder_pin=pin(old),builder_r2_pin=pin(s.encode()),builder_r2_path=newname,
 repair_authorization_pin=ap,preserved_inputs=preserved,failed_stage_completed_bytes=3015196,repair_explicit_read_bytes=charged,repair_read_journal=J,
 reason="Old rows follow original engine required5authority schema; selected_effect_verified can be absent. R1 assertion was too strict and failed before any index/data/wrapper/query was produced.",
 functional_delta='Only builder core5false plus present optionalauthorityfalse check; original rows/engine unchanged. Other changes preserve failed state/continuation claim and charge cumulative budget.',unchanged_helper_AST=unchanged,RUNNER_SEALER_AST_unchanged=True,
 query_attempts_before_repair=0,old_sources_modified=False,oldtests_fixtures_PE_game_native=0,conditional_cumulative_upper=forecast,limit=32*1024**2))
print(json.dumps(dict(status='root_approved_source_repair_prepared_not_executed',new_builder=pin(s.encode()),repair_read_bytes=charged,failed_stage=3015196,cumulative_conditional_upper=forecast)))
