"""New offline entry only: explicit Python file-read meter, never status.

The unchanged CLI and frozen delegated verifiers execute normally. This meter
does not replace their source/hash checks. Import machinery/OS cache reads are
outside the explicit application-read accounting. No target process is opened.
"""
from pathlib import Path
import builtins, hashlib, io, json, os, sys, time, traceback, types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LIMIT=4*1024*1024
OPEN=builtins.open
IOOPEN=io.open

class Meter:
 def __init__(self,host_paths,ordinary_limit,delegated_limit,delegated_attempt_limit):
  self.host_paths=host_paths;self.limits={'ordinary':ordinary_limit,'delegated_fixed_host':delegated_limit}
  self.totals={k:0 for k in self.limits};self.requested={k:0 for k in self.limits};self.files={};self.open_refusals=[]
  self.attempts={k:0 for k in self.limits};self.delegated_attempt_limit=delegated_attempt_limit
 def entry(self,key,category):
  return self.files.setdefault(category+'|'+key,dict(path=key,category=category,bytes=0,attempted_requested_bytes=0,read_attempts=0,read_completions=0,short_reads_including_EOF=0,refused_before_read=0,read_errors=0))
 def open(self,file,mode='r',*args,**kwargs):
  if isinstance(file,int):return OPEN(file,mode,*args,**kwargs)
  path=Path(file).resolve();key=str(path).lower()
  if path.name.lower()=='eu4.exe':raise ValueError('Offline runner forbids target EXE access')
  stream=OPEN(file,mode,*args,**kwargs)
  if 'r' not in mode and '+' not in mode:return stream
  try:
   size=os.fstat(stream.fileno()).st_size
   category='delegated_fixed_host' if key in self.host_paths else 'ordinary'
   if category=='ordinary' and size>LIMIT:raise ValueError('Ordinary file exceeds4MiB')
   if category=='delegated_fixed_host' and size!=self.host_paths[key]['bytes']:raise ValueError('Fixed host metadata size changed')
   if 'b' not in mode:raise ValueError('Explicit source reads must be binary for exact accounting')
   return ReadPort(self,stream,key,category,size)
  except BaseException as exc:
   stream.close();self.open_refusals.append(dict(path=key,error=type(exc).__name__+': '+str(exc)));raise
 def before(self,key,category,size,stream,n):
  assert type(n) is int and n>=0
  v=self.entry(key,category);v['read_attempts']+=1;v['attempted_requested_bytes']+=n;self.requested[category]+=n;self.attempts[category]+=1
  if category=='delegated_fixed_host' and (n>1048576 or self.attempts[category]>self.delegated_attempt_limit):
   v['refused_before_read']+=1;raise ValueError('Fixed host stream requested size/attempt bound')
  if self.totals[category]+n>self.limits[category]:
   v['refused_before_read']+=1;raise ValueError('Offline explicit byte budget before read: '+category)
 def charge(self,key,category,b,n):
  count=len(b);self.totals[category]+=count
  v=self.entry(key,category);v['bytes']+=count;v['read_completions']+=1;v['short_reads_including_EOF']+=int(count<n)
  if self.totals[category]>self.limits[category]:raise ValueError('Offline explicit byte budget after read')

class ReadPort:
 def __init__(self,meter,stream,key,category,size):self.m=meter;self.s=stream;self.key=key;self.category=category;self.size=size
 def __getattr__(self,name):return getattr(self.s,name)
 def __enter__(self):return self
 def __exit__(self,*args):return self.s.__exit__(*args)
 def category_for(self,n):
  # Whole small-source reads are ordinary, even if the path is also in the old
  # host graph. Only the exact path AND <=1MiB read can use streamed allowance.
  return 'ordinary' if self.category=='delegated_fixed_host' and n>1048576 and self.size<=LIMIT else self.category
 def read(self,n=-1):
  bounded=max(0,self.size-self.s.tell())+1 if n<0 else n
  category=self.category_for(bounded);self.m.before(self.key,category,self.size,self.s,bounded)
  try:b=self.s.read(bounded)
  except BaseException:self.m.entry(self.key,category)['read_errors']+=1;raise
  self.m.charge(self.key,category,b,bounded);return b
 def readinto(self,buffer):
  b=self.read(len(buffer));buffer[:len(b)]=b;return len(b)
 def readline(self,n=-1):
  bounded=max(0,self.size-self.s.tell())+1 if n<0 else n
  category=self.category_for(bounded);self.m.before(self.key,category,self.size,self.s,bounded)
  try:b=self.s.readline(bounded)
  except BaseException:self.m.entry(self.key,category)['read_errors']+=1;raise
  self.m.charge(self.key,category,b,bounded);return b
 def __iter__(self):return self
 def __next__(self):
  line=self.readline()
  if not line:raise StopIteration
  return line

def main():
 assert len(sys.argv)==5 and sys.argv[1] in ('new_fake_suite','check','catalog')
 operation=sys.argv[1];ordinary=int(sys.argv[2]);delegated=int(sys.argv[3]);attempt_limit=int(sys.argv[4])
 assert ordinary>=LIMIT+1+43988 and delegated>0
 budget_path=HERE/'budget.json';assert 0<budget_path.stat().st_size<=LIMIT
 with budget_path.open('rb') as f:budget_raw=f.read(LIMIT+1)
 assert 0<len(budget_raw)<=LIMIT;budget=json.loads(budget_raw)
 assert 0<ordinary<=budget['batch_new_explicit_limit'] and 0<delegated<=budget['batch_delegated_fixed_host_limit']
 assert 0<attempt_limit<=budget['batch_delegated_read_attempt_limit']
 p=ROOT/'work/candidates/frida-entry-observer-1375-v1/host-manifest.json';assert p.stat().st_size==43987
 with p.open('rb') as f:raw=f.read(43988)
 assert len(raw)==43987 and hashlib.sha256(raw).hexdigest()=='e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166'
 host=json.loads(raw);host_paths={str((ROOT/n).resolve()).lower():v for n,v in host['source_pins'].items()}
 host_paths.update({str(Path(n).resolve()).lower():v for n,v in host['selected_external_pins'].items()})
 meter=Meter(host_paths,ordinary,delegated,attempt_limit);bootstrap=len(raw)+len(budget_raw)
 meter.totals['ordinary']=bootstrap;meter.requested['ordinary']=LIMIT+1+43988
 code=1;error=None;started=time.perf_counter();old_main=sys.modules.get('__main__')
 try:
  builtins.open=meter.open;io.open=meter.open
  script=HERE/('test_peace_current_pending.py' if operation=='new_fake_suite' else 'peace_current_pending.py')
  sys.argv=[str(script)]+([] if operation=='new_fake_suite' else [operation])
  tested=types.ModuleType('__main__');tested.__file__=str(script);sys.modules['__main__']=tested
  exec(compile(script.read_bytes(),str(script),'exec'),tested.__dict__)
  code=0
 except SystemExit as exc:code=exc.code if type(exc.code) is int else (0 if exc.code is None else 1)
 except BaseException as exc:error=dict(type=type(exc).__name__,message=str(exc));traceback.print_exc()
 finally:
  builtins.open=OPEN;io.open=IOOPEN
  if old_main is not None:sys.modules['__main__']=old_main
  receipt=dict(schema='EU4-PEACE-V2-OFFLINE-EXPLICIT-READS/1',operation=operation,exit_code=code,error=error,
   explicit_read_bytes=meter.totals,explicit_attempted_requested_bytes=meter.requested,limits=meter.limits,bootstrap_bytes=bootstrap,
   bootstrap_attempts=2,bootstrap_requested_bytes=LIMIT+1+43988,read_attempts=meter.attempts,delegated_attempt_limit=attempt_limit,per_path=meter.files,open_refusals=meter.open_refusals,
   duration_seconds=round(time.perf_counter()-started,6),scope='Explicit Python application source/hash reads including delegated fixed host paths; not all OS/import/cache IO. Limits bound returned bytes with full requested-byte reservation before each read. Requested aggregate includes normal short/EOF reads and is reported separately.',
   target_EXE_reads=0,real_status_captures=0,old_test_methods_run=0,native_game_calls=0)
  with (HERE/'offline-r1'/(operation+'-io.json')).open('x',encoding='utf-8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=True,sort_keys=True,indent=2);f.write('\n')
 return code
if __name__=='__main__':raise SystemExit(main())
