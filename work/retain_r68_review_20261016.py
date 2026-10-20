"""R68 independent bounded retained-file intake; no author scripts/PE/engine."""
from pathlib import Path
import hashlib,json,ctypes
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];B='work/reports/war-peace-api-20261016-r68-fixed-frame-projection/';O='work/reports/war-peace-api-20261016-r68-independent-review/';OUT=ROOT/O
LIMIT=24*1024*1024;MEMORY=768*1024*1024;peak=0;reads=[];files={}
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path,pn):
 assert 'eu4.exe'not in path.lower()and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024 and sum(x['bytes']for x in reads)+a.st_size<LIMIT
 r=f.read_bytes();z=f.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and pin(r)==pn,(path,pin(r),pn)
 reads.append(dict(path=path,**pn));files[path]=dict(**pn,raw_hex=r.hex());guard();return r
def write(n,x):
 r=(json.dumps(x,indent=2,ensure_ascii=True)+'\n').encode('ascii');assert len(r)<4*1024*1024
 with(OUT/n).open('xb')as f:f.write(r)
 return pin(r)
def main():
 OUT.mkdir(exist_ok=False)
 try:
  m=json.loads(read(B+'manifest.json',dict(bytes=12209,sha256='4076e33975e93c315b4b073d80c7aa26bdafc8b059b48da12132fa58821a7a75')))
  assert len(m['source_pins'])==20 and len(m['local_pins'])==12
  for path,pn in(m['source_pins']|m['local_pins']).items():read(path,pn)
  final=json.loads(read(B+'final-manifest.json',dict(bytes=1952,sha256='bfd0b9abf4790f42de52a7ebd35d7598f7884262e049e16c53db3597cb528685')))
  for key in('source_pins','local_pins','pins'):
   for path,pn in final.get(key,{}).items():
    full=path if path.startswith('work/')else B+path
    if full not in files:read(full,pn)
  rp=write('retained-files.json',dict(schema='EU4-R68-INDEPENDENT-RETAINED/1',files=files,source_reads=reads,source_bytes=sum(x['bytes']for x in reads),
   prior_initial_inspection_bytes=12209+11854,own_peak_bytes=peak,no_PE_engine_decoder_author_program=True,recursive_closure=False))
  print(json.dumps(dict(retained=rp,files=len(files),source_bytes=sum(x['bytes']for x in reads),peak=peak)))
  print('FINAL',json.dumps(final))
  raw=json.loads(bytes.fromhex(files[B+'raw-crosscheck.json']['raw_hex']));print('RAWKEYS',list(raw));print('RAW',json.dumps(raw)[:14500])
  print('PATHS',json.dumps(list(files)))
 except Exception as exc:
  write('retention-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True));raise
if __name__=='__main__':main()
