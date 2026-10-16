"""File-only immutable snapshot of the terminal V24 run and exact sources."""
import hashlib,importlib.util,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
runner=ROOT/'work/run_pair24_session_r2_1375.py'
s=importlib.util.spec_from_file_location('_archive_pair24',runner);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
c=m.verified_client();manifest=c.manifest();g=c.graph()
id=c.identity(m.PID,m.CREATION,'dfd56862d97a41dd56e3595228011b3a',manifest)
a=c.inspect(id);assert a['terminal'] and not a['complete'] and a['dispatched']==0 and a['pending_native_call'] is None
exit=json.loads((m.OUT/'held-exit.json').read_bytes());assert exit['identity']==id and exit['normal_exit_verified'] and exit['exit_code']==0
initial=json.loads((m.OUT/'initial.json').read_bytes());final=json.loads((m.OUT/'final.json').read_bytes())
assert initial['equal'] and final['equal'] and final['completed_or_terminal_audit_sha256']==a['audit_sha256']
OUT=ROOT/'work/runtime/pair24-stopped-archive-11084-20261012a';OUT.mkdir(exist_ok=False)
paths={Path(k) for k in g.snapshot}
paths.update(ROOT/k for k in manifest['source_pins'])
paths.update(ROOT/k for k in json.loads((m.HERE/'input-pins.json').read_bytes()))
paths.update(m.HERE/k for k in json.loads((m.HERE/'source-index.json').read_bytes()))
paths.update(m.HERE/k for k in ['source-index.json','input-pins.json','review.json'])
paths.update(c.BUILD/k for k in ['build.json',manifest['DLL'],f'loader-intent-{m.PID}-{m.CREATION}.json',f'bootstrap-{m.PID}-{m.CREATION}.request',f'loader-{m.PID}-{m.CREATION}.json'])
paths.update(p for p in c.session_path(id).iterdir() if p.is_file())
paths.update(p for p in m.OUT.iterdir() if p.is_file())
paths.update([runner,Path(__file__),ROOT/'work/diagnose_pair24_submission_context_1375.py',ROOT/'work/wait_pair24_exit_1375.py'])
files={};total=0
for p in sorted(paths):
 if p.stat().st_size==0:
  st=p.lstat();assert p.suffix=='.stderr' and p.is_relative_to(m.OUT) and p.resolve()==p and st.st_nlink==1 and not p.is_symlink() and not getattr(st,'st_file_attributes',0)&0x400
  data=p.read_bytes();assert data==b''
 else:data=m.bounded(p,4*1024*1024)
 total+=len(data);assert len(files)<768 and total<=48*1024*1024
 rel=p.relative_to(ROOT).as_posix();target=OUT/'files'/rel;target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as f:f.write(data)
 assert hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(data).digest()
 files[rel]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
report=dict(schema='EU4PAIR24STOPPEDARCHIVE/1',identity=id,files=files,total_bytes=total,terminal=True,complete=False,
 audit_sha256=a['audit_sha256'],audit_rows=len(a['rows']),owner_thread=a['owner_thread'],results=a['results'],
 adapter_entries=sum(r['event']=='native_call_begin' for r in a['rows']),normal_native_returns=sum(r['event']=='native_call_return' and r['normal'] for r in a['rows']),
 dispatched=0,submit_adapter_returned_nonnormal=True,actual_native_submit_entry_not_logged=True,
 claimed_sequences=[1,2],unclaimed_published_sequences=[3,4,5,6],retried=False,held_exit=exit,
 initial_final_selected_samples_equal=initial['passes']==final['passes'],final_after_terminal=True,
 gameplay_effects_verified=False,production_ready=False,archive_relocation_authorization=False)
m.dump_new(OUT/'archive.json',report)
print(json.dumps(dict(files=len(files),bytes=total,archive_sha256=hashlib.sha256((OUT/'archive.json').read_bytes()).hexdigest())))
