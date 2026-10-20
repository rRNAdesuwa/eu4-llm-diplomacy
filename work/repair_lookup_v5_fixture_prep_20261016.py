"""Preserve failed source assembly; write isolated R2 without old phase execution."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'work/candidates/war-peace-api-lookup-1375-v5'
F=P/'fixture-delta-preparation-failure-r1';F.mkdir(exist_ok=False)
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def save(p,r):
 with p.open('xb')as f:f.write(r)
 return pin(r)
old=(P/'prepare_fixture_delta.py').read_bytes();corr=(P/'fixture-bookkeeping-corrigendum.json').read_bytes()
save(F/'prepare_fixture_delta.py',old);save(F/'fixture-bookkeeping-corrigendum.json',corr)
failure=dict(sealed=True,type='AssertionError',message='seal-claim.json identity occurs twice: claim write and source pin',source_line=53,
 stderr='Traceback: prepare_fixture_delta.py line53 replace("seal-claim.json","seal-r2-claim.json"); line36 assert new.count(a)==1; AssertionError: seal-claim.json',
 failed_source_read_allowance=524288,tool_exit=1,aggregate_and_queries_run=0,PE_game_native=0,
 subsequent_shell_parse_failure=dict(type='PowerShell ParserError',message='Missing argument in parameter list in nested quoted python repair one-liner; parse failed before filesystem statements ran',filesystem_or_child_code_executed=False))
save(F/'failure.json',(json.dumps(failure,indent=2)+'\n').encode())
t=old.decode('utf-8')
a="with(HERE/n).open('xb')as f:f.write(r)"
b="if n=='fixture-bookkeeping-corrigendum.json' and (HERE/n).exists():assert read(HERE/n)==r;return pin(r)\n with(HERE/n).open('xb')as f:f.write(r)"
assert t.count(a)==1;t=t.replace(a,b)
a='replace("\'seal-claim.json\'", "\'seal-r2-claim.json\'")'
b='assert new.count("\'seal-claim.json\'")==2;new=new.replace("\'seal-claim.json\'","\'seal-r2-claim.json\'")'
assert t.count(a)==1;t=t.replace(a,b)
t=t.replace("ast.parse(new);sealpin=",'''new=new.replace("+prep_delta_value['explicit_read_bytes']+sum","+prep_delta_value['explicit_read_bytes']+524288+sum")
ast.parse(new);sealpin=''')
t=t.replace("'seal_candidate_r2.py','prepare_fixture_delta.py'","'seal_candidate_r2.py','prepare_fixture_delta.py','prepare_fixture_delta_r2.py'")
t=t.replace("dm=write('fixture-delta-source-manifest.json'",'''for n in ['prepare_fixture_delta.py','fixture-bookkeeping-corrigendum.json','failure.json']:
 r=read(HERE/'fixture-delta-preparation-failure-r1'/n);pins[rel+'fixture-delta-preparation-failure-r1/'+n]=pin(r)
dm=write('fixture-delta-source-manifest.json' ''')
ast.parse(t);newpin=save(P/'prepare_fixture_delta_r2.py',t.encode())
print(json.dumps(dict(source_only=True,old_source=pin(old),old_corrigendum=pin(corr),new_r2_source=newpin,oldphase_reruns=0)))
