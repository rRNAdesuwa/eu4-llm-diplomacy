"""Offline pure Python checks, CREATE_NEW seals; no game process or native call."""
import ctypes,hashlib,json,pathlib,subprocess,sys,time
from ctypes import wintypes as w
from prepare import HERE,ROOT,index
from trace import read,desc,check_memory_budget
def save(path,data):
 with path.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False,sort_keys=True)
 return desc(path)
def run(argv,log):
 class Basic(ctypes.Structure):
  _fields_=[('p',ctypes.c_longlong),('j',ctypes.c_longlong),('flags',w.DWORD),('min',ctypes.c_size_t),('max',ctypes.c_size_t),('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('sched',w.DWORD)]
 class IO(ctypes.Structure):_fields_=[('v'+str(i),ctypes.c_ulonglong) for i in range(6)]
 class Extended(ctypes.Structure):_fields_=[('basic',Basic),('io',IO),('process_limit',ctypes.c_size_t),('job_limit',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
 kernel=ctypes.WinDLL('kernel32',use_last_error=True);nt=ctypes.WinDLL('ntdll')
 kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
 kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];kernel.SetInformationJobObject.restype=w.BOOL
 kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];kernel.AssignProcessToJobObject.restype=w.BOOL
 kernel.QueryInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p];kernel.QueryInformationJobObject.restype=w.BOOL
 kernel.TerminateJobObject.argtypes=[w.HANDLE,w.UINT];kernel.CloseHandle.argtypes=[w.HANDLE]
 nt.NtResumeProcess.argtypes=[w.HANDLE];nt.NtResumeProcess.restype=ctypes.c_long
 job=kernel.CreateJobObjectW(None,None);assert job
 limits=Extended();limits.basic.flags=0x100|0x2000;limits.process_limit=768*1024*1024
 assert kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits))
 started=time.monotonic();child=None
 try:
  with log.open('xb') as out:
   child=subprocess.Popen(argv,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,creationflags=4)
   assert kernel.AssignProcessToJobObject(job,w.HANDLE(int(child._handle)))
   assert nt.NtResumeProcess(w.HANDLE(int(child._handle)))==0
   try:code=child.wait(timeout=50)
   except subprocess.TimeoutExpired:kernel.TerminateJobObject(job,124);child.wait(timeout=5);raise
  stats=Extended();assert kernel.QueryInformationJobObject(job,9,ctypes.byref(stats),ctypes.sizeof(stats),None)
  return dict(argv=argv,exit_code=code,seconds=round(time.monotonic()-started,3),peak_process_commit=stats.peak_process,peak_job_commit=stats.peak_job,all_shells_collected=True)
 finally:
  if child is not None and child.poll() is None:kernel.TerminateJobObject(job,125);child.wait(timeout=5)
  kernel.CloseHandle(job)
def main():
 out=HERE/'validation-final';out.mkdir(exist_ok=False)
 expected=json.loads(read(HERE/'source-index.json'));assert index()==expected
 source_pins=json.loads(read(HERE/'report.json'))['source_pins'];before={p:desc(ROOT/p) for p in source_pins};assert before==source_pins
 commands=[run([sys.executable,'-B',str(HERE/'prepare.py'),'--check'],out/'check.stdout'),run([sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'],out/'tests.stdout')]
 save(out/'commands.json',commands)
 after={p:desc(ROOT/p) for p in source_pins};assert before==after and index()==expected
 assert all(c['exit_code']==0 for c in commands)
 limits=dict(runtime_verified=False,native_ready=False,production_ready=False,process_accessed=False,native_called=False,DLL_built=False,raw_sampler_implemented=False,new_decode_bytes=294,all_shells_collected=True,remaining_sessions=[])
 validation=save(out/'validation.json',dict(passed=True,commands=commands,inputs_before=before,inputs_after=after,sources_before=expected,sources_after=index(),unchanged=True,outputs={p.name:desc(p) for p in out.iterdir() if p.is_file()},limits=limits))
 review=save(HERE/'review.json',dict(schema=1,status='sealed_static_supplement_pending_independent_review',passed=True,report=desc(HERE/'report.json'),source_index=desc(HERE/'source-index.json'),validation=validation,input_count=len(before),candidate_sources=len(expected),families=5,modes=10,tests=16,limitations=limits))
 print(json.dumps(dict(review=review,validation=validation,report=desc(HERE/'report.json'),peak_parent_commit=check_memory_budget()),sort_keys=True))
if __name__=='__main__':main()
